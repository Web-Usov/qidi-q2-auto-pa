import argparse
import json
import math
import os
import sys
from collections import Counter

import numpy as np

sys.path.insert(0, os.path.abspath("."))
from autopa_local import sweep_analysis as sa  # noqa: E402


WEIGHTS = dict(sa.BD_DEFAULT_WEIGHTS)


def finite_or_none(v):
    try:
        f = float(v)
    except Exception:
        return None
    return f if math.isfinite(f) else None


def load_capture(path):
    z = np.load(path, allow_pickle=True)
    arr = np.asarray(z["samples"], dtype=float)
    meta = json.loads(str(z["meta"]))
    stats = json.loads(str(z["stats"])) if "stats" in z.files else {}
    return arr, meta, stats


def analyse(path):
    arr, meta, stats = load_capture(path)
    t_rel = arr[:, 0] - meta["t0"]
    force = -(arr[:, 2] - arr[:, 3])
    area = float(meta["filament_area"])
    slow_v = float(meta["vfr_low"]) / area
    fast_v = float(meta["vfr"]) / area
    res = sa.analyse_sweep_segments(
        t_rel,
        force,
        meta["ks"],
        meta["windows"],
        meta["transitions"],
        slow_v=slow_v,
        fast_v=fast_v,
        slow_half_s=float(meta["tslow"]),
        fast_half_s=float(meta["tfast"]),
        cycle_period_s=float(meta["tslow"]) + float(meta["tfast"]),
        min_segment_samples=int(meta.get("min_segment_samples", 12)),
        min_segment_rate_hz=float(meta.get("min_segment_rate_hz", 35.0)),
    )
    cost = sa._bd_compute_cost(res.bd_per_k, WEIGHTS)
    ks = np.asarray([float(x.k) for x in res.bd_per_k])
    quality = np.asarray([x.n_segments_included >= 4 for x in res.bd_per_k], dtype=bool)
    finite = np.isfinite(cost) & quality
    discrete = float(ks[finite][int(np.argmin(cost[finite]))]) if finite.any() else None

    per_k = []
    first_under = None
    stable_under = None
    for i, bd in enumerate(res.bd_per_k):
        segs = [s for s in res.bd_segments if abs(float(s.k) - float(bd.k)) < 1e-9 and not s.excluded]
        under_vals = [float(s.metrics.get("undershoot", float("nan"))) for s in segs]
        noise_vals = [float(s.metrics.get("baseline_noise_std", float("nan"))) for s in segs]
        pairs = [(u, n) for u, n in zip(under_vals, noise_vals) if math.isfinite(u) and math.isfinite(n)]
        under_count = sum(1 for u, _ in pairs if u > 0.0)
        three_sigma_count = sum(1 for u, n in pairs if n > 0.0 and u > 3.0 * n)
        med_under = float(np.median([u for u, _ in pairs])) if pairs else None
        med_noise = float(np.median([n for _, n in pairs])) if pairs else None
        if first_under is None and under_count > 0:
            first_under = float(bd.k)
        stable = False
        if med_under is not None and med_noise is not None and med_noise > 0 and med_under > 3.0 * med_noise:
            stable = True
        if three_sigma_count >= 7:
            stable = True
        if stable_under is None and stable:
            stable_under = float(bd.k)
        row = {
            "k": float(bd.k),
            "cost": finite_or_none(cost[i]),
            "segments_included": int(bd.n_segments_included),
            "segments_total": int(bd.n_segments_total),
            "overshoot": finite_or_none(bd.medians.get("overshoot", float("nan"))),
            "undershoot": finite_or_none(bd.medians.get("undershoot", float("nan"))),
            "baseline_noise_std": finite_or_none(bd.medians.get("baseline_noise_std", float("nan"))),
            "median_segment_undershoot": med_under,
            "undershoot_segments": int(under_count),
            "three_sigma_undershoot_segments": int(three_sigma_count),
        }
        per_k.append(row)

    boot = bootstrap(res, n=1000)
    summary = {
        "file": os.path.basename(path),
        "path": path,
        "meta": {
            "vfr_low": float(meta["vfr_low"]),
            "vfr": float(meta["vfr"]),
            "midpoint": 0.5 * (float(meta["vfr_low"]) + float(meta["vfr"])),
            "delta_vfr": float(meta["vfr"]) - float(meta["vfr_low"]),
            "temp": finite_or_none(meta.get("hotend_temp")),
            "target": finite_or_none(meta.get("hotend_target")),
            "wobble": finite_or_none(meta.get("wobble")),
            "wobble_axis": meta.get("wobble_axis"),
            "sps_meta": finite_or_none(meta.get("sps")),
            "errors": int(meta.get("errs", -1)),
            "cycles": int(meta.get("cycles", 0)),
            "kstart": float(meta["ks"][0]),
            "kend": float(meta["ks"][-1]),
            "kstep": float(meta.get("kstep", 0)),
        },
        "actual_sps": float(res.sample_rate_hz),
        "segments_included": int(sum(x.n_segments_included for x in res.bd_per_k)),
        "segments_total": int(sum(x.n_segments_total for x in res.bd_per_k)),
        "discrete_min": discrete,
        "k_opt": finite_or_none(res.bd_k_opt),
        "bootstrap": boot,
        "first_undershoot": first_under,
        "stable_undershoot": stable_under,
        "per_k": per_k,
        "stats": stats,
        "notes": res.notes,
    }
    return summary


def bootstrap(res, n=1000, seed=12345):
    rng = np.random.default_rng(seed)
    ks = [float(x.k) for x in res.bd_per_k]
    segs_by_k = {}
    for k in ks:
        segs_by_k[k] = [s for s in res.bd_segments if abs(float(s.k) - k) < 1e-9 and not s.excluded]
    vals = []
    wins = Counter()
    for _ in range(n):
        boot_by_k = {}
        for k in ks:
            segs = segs_by_k[k]
            if not segs:
                boot_by_k[k] = []
            else:
                idx = rng.integers(0, len(segs), size=len(segs))
                boot_by_k[k] = [segs[int(i)] for i in idx]
        bd = sa._bd_aggregate_per_k(boot_by_k)
        bd_map = {float(x.k): x for x in bd}
        bd = [
            bd_map.get(k, sa.BdKResult(k=k, n_segments_total=0, n_segments_included=0,
                                       medians={name: float("nan") for name in sa.BD_METRIC_NAMES}))
            for k in ks
        ]
        sa._bd_compute_normalised(bd)
        cost = sa._bd_compute_cost(bd, WEIGHTS)
        qual = np.asarray([x.n_segments_included >= 4 for x in bd], dtype=bool)
        finite = np.isfinite(cost) & qual
        if not finite.any():
            continue
        kk = np.asarray(ks)[finite]
        cc = cost[finite]
        win = float(kk[int(np.argmin(cc))])
        wins[f"{win:.4f}"] += 1
        opt = sa._argmin_with_parabolic(kk, cc)
        if opt is not None and math.isfinite(float(opt)):
            vals.append(float(opt))
    arr = np.asarray(vals, dtype=float)
    if len(arr) == 0:
        return {"n": 0, "wins": dict(wins)}
    return {
        "n": int(len(arr)),
        "median": float(np.median(arr)),
        "mean": float(np.mean(arr)),
        "std": float(np.std(arr, ddof=1)) if len(arr) > 1 else 0.0,
        "p5": float(np.percentile(arr, 5)),
        "p25": float(np.percentile(arr, 25)),
        "p50": float(np.percentile(arr, 50)),
        "p75": float(np.percentile(arr, 75)),
        "p95": float(np.percentile(arr, 95)),
        "wins": dict(sorted(wins.items())),
    }


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("captures", nargs="+")
    ap.add_argument("--out")
    args = ap.parse_args()
    data = [analyse(p) for p in args.captures]
    text = json.dumps(data, indent=2, sort_keys=True)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(text + "\n")
    print(text)
