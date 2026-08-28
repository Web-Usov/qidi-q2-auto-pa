#!/usr/bin/env python3
"""Offline analysis and model building for QIDI Q2 Adaptive PA calibration.

This tool replays AUTOPA_SWEEP captures with the same sweep_analysis module used
on the printer, bootstraps segments, applies deterministic quality gates and
builds the calculated Orca Adaptive PA list used by this project.

The acceleration axis is an empirical *proxy* derived from standard tiny-wobble
AUTOPA_SWEEP runs. It is not a direct measurement of normal print acceleration.
See docs/MODEL.md and docs/HISTORY.md.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import math
import os
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np

HERE = Path(__file__).resolve()
REPO = HERE.parents[1]
SA_PATH = REPO / "runtime" / "autopa" / "sweep_analysis.py"
_spec = importlib.util.spec_from_file_location("q2_prod_sweep_analysis", SA_PATH)
if _spec is None or _spec.loader is None:
    raise RuntimeError(f"cannot load {SA_PATH}")
sa = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sa)
WEIGHTS = dict(sa.BD_DEFAULT_WEIGHTS)


def finite(v: Any) -> float | None:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def error_count(value: Any) -> int:
    """Normalize Q2/AutoPA error metadata (int, tuple/list, nested) to a count."""
    if value is None:
        return 0
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, np.integer)):
        return max(0, int(value))
    if isinstance(value, float):
        return max(0, int(value)) if math.isfinite(value) else 1
    if isinstance(value, (list, tuple)):
        return sum(error_count(x) for x in value)
    if isinstance(value, dict):
        return sum(error_count(x) for x in value.values())
    try:
        return max(0, int(value))
    except Exception:
        return 1


def load_capture(path: str | Path):
    path = Path(path)
    with np.load(path, allow_pickle=False) as z:
        arr = np.asarray(z["samples"], dtype=float)
        meta = json.loads(str(z["meta"]))
        stats = json.loads(str(z["stats"])) if "stats" in z.files else {}
    return arr, meta, stats


def bootstrap(res, n: int = 1000, seed: int = 12345) -> dict[str, Any]:
    rng = np.random.default_rng(seed)
    ks = [float(x.k) for x in res.bd_per_k]
    segs_by_k = {
        k: [s for s in res.bd_segments
            if abs(float(s.k) - k) < 1e-9 and not s.excluded]
        for k in ks
    }
    vals: list[float] = []
    wins: Counter[str] = Counter()
    for _ in range(n):
        boot_by_k = {}
        for k in ks:
            segs = segs_by_k[k]
            if not segs:
                boot_by_k[k] = []
                continue
            idx = rng.integers(0, len(segs), size=len(segs))
            boot_by_k[k] = [segs[int(i)] for i in idx]
        bd = sa._bd_aggregate_per_k(boot_by_k)
        bd_map = {float(x.k): x for x in bd}
        bd = [bd_map.get(
            k,
            sa.BdKResult(
                k=k, n_segments_total=0, n_segments_included=0,
                medians={name: float("nan") for name in sa.BD_METRIC_NAMES},
            ),
        ) for k in ks]
        sa._bd_compute_normalised(bd)
        cost = sa._bd_compute_cost(bd, WEIGHTS)
        quality_mask = np.asarray([x.n_segments_included >= 4 for x in bd], dtype=bool)
        mask = np.isfinite(cost) & quality_mask
        if not mask.any():
            continue
        kk = np.asarray(ks, dtype=float)[mask]
        cc = np.asarray(cost, dtype=float)[mask]
        winner = float(kk[int(np.argmin(cc))])
        wins[f"{winner:.4f}"] += 1
        opt = sa._argmin_with_parabolic(kk, cc)
        if opt is not None and math.isfinite(float(opt)):
            vals.append(float(opt))
    a = np.asarray(vals, dtype=float)
    if not len(a):
        return {"n": 0, "wins": dict(wins)}
    return {
        "n": int(len(a)),
        "median": float(np.median(a)),
        "mean": float(np.mean(a)),
        "std": float(np.std(a, ddof=1)) if len(a) > 1 else 0.0,
        "p5": float(np.percentile(a, 5)),
        "p25": float(np.percentile(a, 25)),
        "p50": float(np.percentile(a, 50)),
        "p75": float(np.percentile(a, 75)),
        "p95": float(np.percentile(a, 95)),
        "wins": dict(sorted(wins.items())),
    }


def analyse(path: str | Path, bootstrap_n: int = 1000) -> dict[str, Any]:
    arr, meta, stats = load_capture(path)
    if arr.ndim != 2 or arr.shape[1] < 4 or len(arr) < 2:
        raise ValueError(f"invalid sample matrix in {path}")
    t_rel = arr[:, 0] - float(meta["t0"])
    force = -(arr[:, 2] - arr[:, 3])
    area = float(meta["filament_area"])
    slow_v = float(meta["vfr_low"]) / area
    fast_v = float(meta["vfr"]) / area
    res = sa.analyse_sweep_segments(
        t_rel, force, meta["ks"], meta["windows"], meta["transitions"],
        slow_v=slow_v, fast_v=fast_v,
        slow_half_s=float(meta["tslow"]), fast_half_s=float(meta["tfast"]),
        cycle_period_s=float(meta["tslow"]) + float(meta["tfast"]),
        min_segment_samples=int(meta.get("min_segment_samples", 12)),
        min_segment_rate_hz=float(meta.get("min_segment_rate_hz", 35.0)),
    )
    cost = np.asarray(sa._bd_compute_cost(res.bd_per_k, WEIGHTS), dtype=float)
    ks = np.asarray([float(x.k) for x in res.bd_per_k], dtype=float)
    good = np.asarray([x.n_segments_included >= 4 for x in res.bd_per_k])
    mask = np.isfinite(cost) & good
    discrete = float(ks[mask][int(np.argmin(cost[mask]))]) if mask.any() else None
    included = int(sum(x.n_segments_included for x in res.bd_per_k))
    total = int(sum(x.n_segments_total for x in res.bd_per_k))
    boot = bootstrap(res, n=bootstrap_n)
    kopt = finite(res.bd_k_opt)
    kstart = float(meta["ks"][0])
    kend = float(meta["ks"][-1])
    kstep = float(meta.get("kstep", ks[1] - ks[0] if len(ks) > 1 else 0.0))
    edge = bool(kopt is None or kopt <= kstart + 0.5*kstep or kopt >= kend - 0.5*kstep)
    return {
        "file": Path(path).name,
        "path": str(Path(path).resolve()),
        "vfr_low": float(meta["vfr_low"]),
        "vfr": float(meta["vfr"]),
        "midpoint": 0.5 * (float(meta["vfr_low"]) + float(meta["vfr"])),
        "delta_vfr": float(meta["vfr"]) - float(meta["vfr_low"]),
        "accel": finite(meta.get("accel")),
        "wobble": finite(meta.get("wobble")),
        "actual_sps": float(res.sample_rate_hz),
        "errors": error_count(meta.get("errs", meta.get("errors", 0))),
        "segments_included": included,
        "segments_total": total,
        "segment_ratio": included / total if total else 0.0,
        "kstart": kstart,
        "kend": kend,
        "kstep": kstep,
        "discrete_min": discrete,
        "k_opt": kopt,
        "edge_minimum": edge,
        "bootstrap": boot,
        "stats": stats,
        "notes": list(res.notes),
    }


def quality(summary: dict[str, Any], kind: str = "flow") -> dict[str, Any]:
    b = summary.get("bootstrap", {})
    k = summary.get("k_opt")
    med = finite(b.get("median"))
    p5 = finite(b.get("p5"))
    p95 = finite(b.get("p95"))
    n = int(b.get("n", 0) or 0)
    width = p95 - p5 if p5 is not None and p95 is not None else math.inf
    delta = abs(k - med) if k is not None and med is not None else math.inf
    max_delta = 0.0035 if kind == "flow" else 0.0045
    max_width = 0.012 if kind == "flow" else 0.015
    checks = {
        "errors_zero": summary.get("errors") == 0,
        "sample_rate": float(summary.get("actual_sps", 0)) >= 35.0,
        "segment_ratio": float(summary.get("segment_ratio", 0)) >= 0.95,
        "internal_minimum": not bool(summary.get("edge_minimum")),
        "bootstrap_n": n >= 800,
        "k_vs_bootstrap": delta <= max_delta,
        "bootstrap_width": width <= max_width,
    }
    return {
        "ok": all(checks.values()),
        "kind": kind,
        "checks": checks,
        "k_bootstrap_delta": finite(delta),
        "p5_p95_width": finite(width),
    }


def model(flow391: dict[str, Any], flow782: dict[str, Any], mid10: dict[str, Any],
          mid14: dict[str, Any], acc1800: dict[str, Any], acc3600: dict[str, Any],
          acc7200: dict[str, Any]) -> dict[str, Any]:
    """Build the project's calculated 3x3 APA model from accepted captures."""
    f391 = float(flow391["bootstrap"]["median"])
    f782 = float(flow782["bootstrap"]["median"])
    k10 = float(mid10["k_opt"])
    k14 = float(mid14["k_opt"])
    f156 = k14 + ((k14 - k10) / (14.0 - 10.0)) * (15.6 - 14.0)

    ka = {
        1800: float(acc1800["k_opt"]),
        3600: float(acc3600["k_opt"]),
        7200: float(acc7200["k_opt"]),
    }
    if ka[3600] <= 0:
        raise ValueError("invalid 3600 acceleration anchor")
    factors = {a: k / ka[3600] for a, k in ka.items()}
    flows = {3.91: f391, 7.82: f782, 15.6: f156}
    matrix = {a: {f: flows[f] * factors[a] for f in flows} for a in (1800, 3600, 7200)}

    for a in matrix:
        vals = [matrix[a][f] for f in (3.91, 7.82, 15.6)]
        if not (vals[0] >= vals[1] >= vals[2]):
            raise ValueError(f"non-monotonic PA(flow) at acceleration {a}: {vals}")
    for f in flows:
        vals = [matrix[a][f] for a in (1800, 3600, 7200)]
        if not (vals[0] >= vals[1] >= vals[2]):
            raise ValueError(f"non-monotonic PA(accel) at flow {f}: {vals}")

    order = [(7200, 3.91), (7200, 7.82), (7200, 15.6),
             (3600, 3.91), (3600, 7.82), (3600, 15.6),
             (1800, 3.91), (1800, 7.82), (1800, 15.6)]
    orca = [f"{matrix[a][f]:.4f},{f:g},{a}" for a, f in order]
    return {
        "flow_anchors": {"3.91": f391, "7.82": f782, "15.6": f156},
        "high_flow_method": "local linear extrapolation from midpoint 10 and 14 equal-DeltaVFR=8 K_opt",
        "acceleration_proxy_k": {str(a): ka[a] for a in ka},
        "acceleration_factors": {str(a): factors[a] for a in factors},
        "matrix": {str(a): {str(f): matrix[a][f] for f in flows} for a in matrix},
        "orca_list": orca,
        "general_pa_fallback": f782,
        "bridge_pa_start": f782 / 2.0,
        "limitations": [
            "flow axis is load-cell measured except 15.6, which is extrapolated from validated upper-flow trend",
            "acceleration axis is a relative tiny-wobble AUTOPA_SWEEP proxy, not direct real-trajectory acceleration measurement",
        ],
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("analyse")
    p.add_argument("capture")
    p.add_argument("--kind", choices=["flow", "accel"], default="flow")
    p.add_argument("--bootstrap", type=int, default=1000)
    m = sub.add_parser("model")
    for name in ("flow391", "flow782", "mid10", "mid14", "acc1800", "acc3600", "acc7200"):
        m.add_argument(f"--{name}", required=True)
    m.add_argument("--out")
    args = ap.parse_args()

    if args.cmd == "analyse":
        s = analyse(args.capture, args.bootstrap)
        s["quality"] = quality(s, args.kind)
        print(json.dumps(s, indent=2, sort_keys=True))
        return 0 if s["quality"]["ok"] else 2

    summaries = {name: analyse(getattr(args, name)) for name in
                 ("flow391", "flow782", "mid10", "mid14", "acc1800", "acc3600", "acc7200")}
    for name, s in summaries.items():
        kind = "accel" if name.startswith("acc") else "flow"
        q = quality(s, kind)
        if not q["ok"]:
            raise SystemExit(f"capture {name} failed quality gate: {json.dumps(q, sort_keys=True)}")
        s["quality"] = q
    result = model(**summaries)
    payload = {"inputs": summaries, "result": result}
    text = json.dumps(payload, indent=2, sort_keys=True)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
