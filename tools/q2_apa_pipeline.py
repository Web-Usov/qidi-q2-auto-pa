#!/usr/bin/env python3
"""Safe, stepwise QIDI Q2 load-cell APA calibration orchestrator.

The default workflow is intentionally stepwise so an operator/agent can inspect
QIDI's camera between extrusion sweeps. Every physical step requires
--confirm-clear, heats only for that step, and turns the hotend off in finally.

Typical agent workflow:
  q2_apa_pipeline.py start --temperature 245 --material PETG --confirm-clear
  q2_apa_pipeline.py step  --run <run-dir> --confirm-clear   # repeat until done
  q2_apa_pipeline.py status --run <run-dir>

When all seven accepted captures exist, the last step automatically builds and
prints an Orca Adaptive PA list. See docs/CALIBRATION.md and docs/SAFETY.md.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve()
ANALYSIS = HERE.with_name("q2_apa_analysis.py")
DEFAULT_MOONRAKER = "http://127.0.0.1"
DEFAULT_CAPTURE_DIR = Path("/home/mks/printer_data/autopa/captures")
DEFAULT_RUN_ROOT = Path("/home/mks/printer_data/autopa/apa-runs")
SAFE_Z = 220.0
POSITIONS = [(200, 140), (175, 140), (150, 140), (125, 140),
             (100, 140), (75, 140), (50, 140)]
PLAN = [
    {"name": "flow391", "kind": "flow", "vfr_low": 1.91, "vfr": 5.91, "accel": 1000},
    {"name": "flow782", "kind": "flow", "vfr_low": 5.82, "vfr": 9.82, "accel": 1000},
    {"name": "mid10", "kind": "flow", "vfr_low": 6.0, "vfr": 14.0, "accel": 1000},
    {"name": "mid14", "kind": "flow", "vfr_low": 10.0, "vfr": 18.0, "accel": 1000},
    {"name": "acc1800", "kind": "accel", "vfr_low": 2.0, "vfr": 18.0, "accel": 1800},
    {"name": "acc3600", "kind": "accel", "vfr_low": 2.0, "vfr": 18.0, "accel": 3600},
    {"name": "acc7200", "kind": "accel", "vfr_low": 2.0, "vfr": 18.0, "accel": 7200},
]


class PipelineError(RuntimeError):
    pass


class Moonraker:
    def __init__(self, base: str, timeout: float = 900.0):
        self.base = base.rstrip("/")
        self.timeout = timeout

    def _request(self, method: str, path: str, payload: Any = None) -> Any:
        data = None
        headers = {"Accept": "application/json"}
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(self.base + path, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                body = r.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")
            raise PipelineError(f"Moonraker HTTP {e.code}: {detail}") from e
        except Exception as e:
            raise PipelineError(f"Moonraker request failed: {e}") from e
        try:
            return json.loads(body) if body else {}
        except json.JSONDecodeError as e:
            raise PipelineError(f"Moonraker returned non-JSON: {body[:300]}") from e

    def gcode(self, script: str) -> Any:
        return self._request("POST", "/printer/gcode/script", {"script": script})

    def query(self, *objects: str) -> dict[str, Any]:
        qs = "&".join(urllib.parse.quote(x, safe="") for x in objects)
        raw = self._request("GET", "/printer/objects/query?" + qs)
        try:
            return raw["result"]["status"]
        except Exception as e:
            raise PipelineError(f"unexpected object query response: {raw}") from e


def dump(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def printer_status(m: Moonraker) -> dict[str, Any]:
    return m.query("webhooks", "print_stats", "toolhead", "extruder",
                   "filament_switch_sensor filament_switch_sensor",
                   "q2_loadcell", "autopa")


def preflight(m: Moonraker, require_filament: bool = True) -> dict[str, Any]:
    s = printer_status(m)
    web = s.get("webhooks", {})
    if web.get("state") != "ready":
        raise PipelineError(f"Klipper is not ready: {web.get('state')} {web.get('state_message','')}")
    pstate = str(s.get("print_stats", {}).get("state", "")).lower()
    if pstate in {"printing", "paused"}:
        raise PipelineError(f"printer is busy: print_stats.state={pstate}")
    ap = s.get("autopa", {})
    if not ap.get("has_load_cell", False):
        raise PipelineError("AutoPA does not see a load cell")
    if ap.get("activity", {}).get("state", "idle") != "idle":
        raise PipelineError(f"AutoPA is busy: {ap.get('activity')}")
    if require_filament:
        fs = s.get("filament_switch_sensor filament_switch_sensor", {})
        detected = fs.get("filament_detected")
        if detected is not True:
            raise PipelineError(f"filament sensor does not report filament_detected=true: {fs}")
    return s


def sensor_test(m: Moonraker, seconds: float = 5.0) -> dict[str, Any]:
    before = m.query("q2_loadcell").get("q2_loadcell", {})
    n0 = int(before.get("new_readings", 0) or 0)
    e0 = int(before.get("errors", 0) or 0)
    started = time.monotonic()
    m.gcode(f"QPA_SENSOR_TEST TIME={seconds:.1f}")
    elapsed = time.monotonic() - started
    after = m.query("q2_loadcell").get("q2_loadcell", {})
    dn = int(after.get("new_readings", 0) or 0) - n0
    de = int(after.get("errors", 0) or 0) - e0
    effective_lower = dn / max(seconds + 0.35, 0.1)
    out = {"new_readings": dn, "new_errors": de, "wall_s": elapsed,
           "conservative_rate_hz": effective_lower}
    if de != 0:
        raise PipelineError(f"load-cell sensor test produced {de} read errors")
    if effective_lower < 35.0:
        raise PipelineError(f"load-cell rate too low: {effective_lower:.2f} Hz (<35 Hz)")
    return out


def k_count(kstart: float = 0.030, kend: float = 0.085, kstep: float = 0.0025) -> int:
    return int(round((kend - kstart) / kstep)) + 1


def filament_budget(vfr_low: float, vfr: float, area: float, cycles: int = 10,
                    tslow: float = 1.0, tfast: float = 0.5, warmup: float = 4.0,
                    prime: float = 15.0) -> float:
    slow = vfr_low / area
    fast = vfr / area
    slow_mm = slow * tslow
    fast_mm = fast * tfast
    per_k = slow_mm + cycles * (fast_mm + slow_mm)
    return per_k * k_count() + (warmup - 1.0) * slow_mm + prime


def newest_capture(capture_dir: Path, before: set[Path], started_wall: float) -> Path:
    candidates = [p for p in capture_dir.glob("capture_*.npz")
                  if p not in before and p.stat().st_mtime >= started_wall - 2]
    if not candidates:
        raise PipelineError(f"no new AutoPA capture appeared in {capture_dir}")
    return max(candidates, key=lambda p: p.stat().st_mtime)


def run_analysis(capture: Path, kind: str, out: Path) -> dict[str, Any]:
    cmd = [sys.executable, str(ANALYSIS), "analyse", str(capture), "--kind", kind]
    cp = subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        data = json.loads(cp.stdout)
    except Exception as e:
        raise PipelineError(f"analysis failed to return JSON\nstdout={cp.stdout}\nstderr={cp.stderr}") from e
    dump(out, data)
    if cp.returncode not in (0, 2):
        raise PipelineError(f"analysis process failed ({cp.returncode}): {cp.stderr}")
    return data


def safe_shutdown(m: Moonraker, original_pa: float | None = None) -> list[str]:
    errors = []
    scripts = ([f"SET_PRESSURE_ADVANCE ADVANCE={original_pa:.6f}"]
               if original_pa is not None else []) + ["M104 S0"]
    for script in scripts:
        try:
            m.gcode(script)
        except Exception as e:
            errors.append(f"{script}: {e}")
    return errors


def create_run(args, m: Moonraker) -> Path:
    if not args.confirm_clear:
        raise PipelineError("physical safety gate: inspect bed/nozzle/camera and pass --confirm-clear")
    s = preflight(m)
    homed = str(s.get("toolhead", {}).get("homed_axes", ""))
    if not all(a in homed for a in "xyz"):
        m.gcode("G28")
    m.gcode(f"G90\nG1 X{POSITIONS[0][0]} Y{POSITIONS[0][1]} Z{SAFE_Z:.1f} F12000")
    test = sensor_test(m, 5.0)
    s2 = preflight(m)
    pa = float(s2.get("extruder", {}).get("pressure_advance", 0.0) or 0.0)
    orig_accel = float(s2.get("toolhead", {}).get("max_accel", 0.0) or 0.0)
    area = float(s2.get("autopa", {}).get("filament_area", math.pi*(1.75/2)**2))
    stamp = time.strftime("%Y%m%d-%H%M%S")
    root = Path(args.run_root).expanduser()
    run = root / stamp
    run.mkdir(parents=True, exist_ok=False)
    state = {
        "version": 1, "created": stamp,
        "temperature": float(args.temperature), "material": args.material,
        "brand": args.brand, "moonraker": args.moonraker,
        "capture_dir": str(Path(args.capture_dir).expanduser()),
        "original_pa": pa, "original_max_accel": orig_accel,
        "filament_area": area, "sensor_test": test,
        "status": "running", "next_index": 0,
        "plan": [dict(x, attempts=[]) for x in PLAN],
    }
    dump(run / "state.json", state)
    print(f"RUN={run}")
    print(f"sensor test OK: conservative rate {test['conservative_rate_hz']:.2f} Hz, errors=0")
    print("Ready for first sweep. Inspect nozzle/bed, then run:"
          f"\n  {Path(sys.argv[0]).name} step --run {run} --confirm-clear")
    return run


def execute_step(args, m: Moonraker) -> Path:
    run = Path(args.run).expanduser().resolve()
    state_path = run / "state.json"
    st = load(state_path)
    if st.get("status") not in {"running", "retry"}:
        raise PipelineError(f"run state is {st.get('status')}; no physical step allowed")
    idx = int(st.get("next_index", 0))
    if idx >= len(st["plan"]):
        finalize(run)
        return run
    if not args.confirm_clear:
        raise PipelineError("physical safety gate: inspect camera/nozzle/bed and pass --confirm-clear")
    s = preflight(m)
    original_pa = float(st["original_pa"])
    item = st["plan"][idx]
    attempts = item.setdefault("attempts", [])
    if len(attempts) >= 2:
        st["status"] = "failed"
        dump(state_path, st)
        raise PipelineError(f"{item['name']} already failed two attempts")

    homed = str(s.get("toolhead", {}).get("homed_axes", ""))
    try:
        if not all(a in homed for a in "xyz"):
            m.gcode("G28")
        x, y = POSITIONS[idx]
        m.gcode(f"G90\nG1 X{x} Y{y} Z{SAFE_Z:.1f} F12000")
        sensor = sensor_test(m, 3.0)
        m.gcode(f"M109 S{float(st['temperature']):.1f}\nG4 P10000")
        live = preflight(m)
        area = float(live.get("autopa", {}).get("filament_area", st["filament_area"]))
        budget = filament_budget(float(item["vfr_low"]), float(item["vfr"]), area)
        max_fil = math.ceil(budget * 1.10 / 10.0) * 10.0
        if max_fil > 2500:
            raise PipelineError(f"computed filament budget {budget:.0f} mm exceeds production hard cap")
        capdir = Path(st["capture_dir"]).expanduser()
        capdir.mkdir(parents=True, exist_ok=True)
        before = set(capdir.glob("capture_*.npz"))
        started_wall = time.time()
        cmd = (
            "AUTOPA_SWEEP "
            f"VFR_LOW={item['vfr_low']} VFR={item['vfr']} "
            "TSLOW=1 TFAST=0.5 CYCLES=10 "
            "KSTART=0.030 KEND=0.085 KSTEP=0.0025 "
            "WARMUP=4 PRIME=15 RETRACT=6 "
            "WOBBLEAXIS=X WOBBLE=0.14 "
            f"ACCEL={item['accel']} APPLY=0 MAXFILAMENT={max_fil:.0f}"
        )
        m.gcode(cmd)
        capture = newest_capture(capdir, before, started_wall)
        attempt_no = len(attempts) + 1
        analysis_path = run / f"{idx+1:02d}_{item['name']}_attempt{attempt_no}.json"
        analysis = run_analysis(capture, item["kind"], analysis_path)
        rec = {"attempt": attempt_no, "capture": str(capture),
               "analysis": str(analysis_path), "sensor_test": sensor,
               "quality": analysis.get("quality", {}), "accepted": False}
        attempts.append(rec)
        if analysis.get("quality", {}).get("ok"):
            rec["accepted"] = True
            item["accepted_capture"] = str(capture)
            item["accepted_analysis"] = str(analysis_path)
            st["next_index"] = idx + 1
            st["status"] = "running"
            print(f"ACCEPTED {item['name']}: K_opt={analysis.get('k_opt')} boot={analysis.get('bootstrap',{}).get('median')}")
        elif attempt_no < 2:
            st["status"] = "retry"
            print(f"RETRY REQUIRED for {item['name']}: {json.dumps(analysis.get('quality'), sort_keys=True)}")
            print("Inspect nozzle/bed before retry, then run the same step command again.")
        else:
            st["status"] = "failed"
            print(f"FAILED {item['name']} after two attempts; final APA list will NOT be generated.")
        dump(state_path, st)
    finally:
        shutdown_errors = safe_shutdown(m, original_pa)
        if shutdown_errors:
            print("WARNING: safe-shutdown errors: " + "; ".join(shutdown_errors), file=sys.stderr)

    st = load(state_path)
    if st.get("status") == "running" and int(st.get("next_index", 0)) >= len(st["plan"]):
        finalize(run)
    elif st.get("status") == "running":
        nxt = st["plan"][int(st["next_index"])]
        print(f"Next: {nxt['name']}. Inspect camera/nozzle/bed, then run step again.")
    return run


def finalize(run: Path) -> dict[str, Any]:
    st = load(run / "state.json")
    if int(st.get("next_index", 0)) < len(st["plan"]):
        raise PipelineError("cannot finalize: not all planned sweeps are accepted")
    paths = {x["name"]: x.get("accepted_capture") for x in st["plan"]}
    if not all(paths.values()):
        raise PipelineError("cannot finalize: accepted capture path missing")
    out = run / "result.json"
    cmd = [sys.executable, str(ANALYSIS), "model"]
    for name in ("flow391", "flow782", "mid10", "mid14", "acc1800", "acc3600", "acc7200"):
        cmd += [f"--{name}", str(paths[name])]
    cmd += ["--out", str(out)]
    cp = subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if cp.returncode != 0:
        st["status"] = "failed"
        st["finalize_error"] = cp.stderr or cp.stdout
        dump(run / "state.json", st)
        raise PipelineError(f"final model failed: {cp.stderr or cp.stdout}")
    payload = json.loads(cp.stdout)
    result = payload["result"]
    (run / "orca_adaptive_pa.txt").write_text("\n".join(result["orca_list"]) + "\n", encoding="utf-8")
    st["status"] = "complete"
    st["result"] = str(out)
    dump(run / "state.json", st)
    print("\nORCA ADAPTIVE PA\n----------------")
    print("\n".join(result["orca_list"]))
    print(f"\nGeneral PA fallback: {result['general_pa_fallback']:.4f}")
    print(f"Bridge PA starting value: {result['bridge_pa_start']:.4f}")
    print(f"Saved: {out}")
    return payload


def show_status(run: Path) -> None:
    st = load(run / "state.json")
    print(json.dumps({
        "run": str(run), "status": st.get("status"),
        "temperature": st.get("temperature"), "material": st.get("material"),
        "next_index": st.get("next_index"),
        "steps": [{"name": x["name"], "attempts": len(x.get("attempts", [])),
                   "accepted": bool(x.get("accepted_capture"))} for x in st.get("plan", [])],
        "result": st.get("result"),
    }, indent=2))


def abort_run(run: Path, m: Moonraker) -> None:
    st = load(run / "state.json")
    errs = safe_shutdown(m, float(st.get("original_pa", 0.0)))
    st["status"] = "aborted"
    if errs:
        st["shutdown_errors"] = errs
    dump(run / "state.json", st)
    print(f"aborted {run}; hotend-off/PA-restore requested")


def parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser()
    ap.add_argument("--moonraker", default=DEFAULT_MOONRAKER)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("start")
    s.add_argument("--temperature", type=float, required=True)
    s.add_argument("--material", required=True)
    s.add_argument("--brand", default="")
    s.add_argument("--capture-dir", default=str(DEFAULT_CAPTURE_DIR))
    s.add_argument("--run-root", default=str(DEFAULT_RUN_ROOT))
    s.add_argument("--confirm-clear", action="store_true")
    x = sub.add_parser("step")
    x.add_argument("--run", required=True)
    x.add_argument("--confirm-clear", action="store_true")
    q = sub.add_parser("status")
    q.add_argument("--run", required=True)
    f = sub.add_parser("finalize")
    f.add_argument("--run", required=True)
    a = sub.add_parser("abort")
    a.add_argument("--run", required=True)
    p = sub.add_parser("preflight")
    p.add_argument("--no-filament-check", action="store_true")
    return ap


def main() -> int:
    args = parser().parse_args()
    m = Moonraker(args.moonraker)
    try:
        if args.cmd == "preflight":
            print(json.dumps(preflight(m, not args.no_filament_check), indent=2, sort_keys=True))
        elif args.cmd == "start":
            create_run(args, m)
        elif args.cmd == "step":
            execute_step(args, m)
        elif args.cmd == "status":
            show_status(Path(args.run).expanduser().resolve())
        elif args.cmd == "finalize":
            finalize(Path(args.run).expanduser().resolve())
        elif args.cmd == "abort":
            abort_run(Path(args.run).expanduser().resolve(), m)
        return 0
    except PipelineError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
