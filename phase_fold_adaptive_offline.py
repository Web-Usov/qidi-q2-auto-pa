import json
import math
import os
import sys
from collections import defaultdict

import numpy as np

sys.path.insert(0, os.getcwd())
from autopa_local import sweep_analysis as sa


BIN_S = float(os.environ.get("PF_BIN_S", "0.005"))
WINDOW_PRE = 0.050
WINDOW_POST = 0.150
MIN_WET_LEGS_PER_BIN = int(os.environ.get("PF_MIN_WET_LEGS", "3"))
MIN_DRY_LEGS_PER_BIN = int(os.environ.get("PF_MIN_DRY_LEGS", "2"))


def robust_sigma(x):
    x = np.asarray(x, dtype=float)
    x = x[np.isfinite(x)]
    if len(x) == 0:
        return float("nan")
    med = float(np.median(x))
    mad = float(np.median(np.abs(x - med)))
    return 1.4826 * mad


def load_capture(path):
    d = np.load(path, allow_pickle=False)
    meta = json.loads(str(d["meta"]))
    arr = np.asarray(d["samples"], dtype=float)
    t = arr[:, 0]
    force = -(arr[:, 2] - arr[:, 3])
    return arr, meta, t, force


def leg_duration(meta):
    return abs(float(meta["x1"]) - float(meta["x0"])) / float(meta["speed"]) + float(meta["speed"]) / float(meta["accel"])


def phase_points(t, y, legs, rel_lo, rel_hi, leg_indices=None):
    rows = []
    if leg_indices is None:
        leg_indices = list(range(len(legs)))
    for out_idx, li in enumerate(leg_indices):
        leg = legs[int(li)]
        t0 = float(leg["t0"])
        mask = (t >= t0 + rel_lo) & (t <= t0 + rel_hi)
        if not int(mask.sum()):
            continue
        rel = t[mask] - t0
        for rr, yy in zip(rel, y[mask]):
            rows.append((float(rr), float(yy), int(out_idx), int(li)))
    if not rows:
        return np.empty((0, 4), dtype=float)
    return np.asarray(rows, dtype=float)


def fold_points(points, rel_lo, rel_hi, bin_s, min_legs):
    edges = np.arange(rel_lo, rel_hi + bin_s * 1.5, bin_s)
    centers = (edges[:-1] + edges[1:]) * 0.5
    out = []
    for bi, c in enumerate(centers):
        lo, hi = edges[bi], edges[bi + 1]
        m = (points[:, 0] >= lo) & (points[:, 0] < hi)
        if not int(m.sum()):
            continue
        vals = points[m, 1]
        legs = set(int(v) for v in points[m, 2])
        if len(legs) < min_legs:
            continue
        med = float(np.median(vals))
        out.append({
            "t": float(c),
            "median": med,
            "sigma": robust_sigma(vals),
            "n": int(len(vals)),
            "legs": int(len(legs)),
        })
    return out


def coverage_for(meta, t, legs, rel_lo=-0.050, rel_hi=0.150, accel_only=False):
    if accel_only:
        rel_lo, rel_hi = 0.0, float(meta["speed"]) / float(meta["accel"])
    pts = phase_points(t, t * 0.0, legs, rel_lo, rel_hi)
    if len(pts) == 0:
        return {}
    phases = np.mod(pts[:, 0], 1.0 / float(meta.get("sps", 40.0)))
    # Unique temporal positions at 2ms and 5ms granularity.
    rel = pts[:, 0]
    return {
        "legs": len(legs),
        "samples": int(len(pts)),
        "rel_min": float(np.min(rel)),
        "rel_max": float(np.max(rel)),
        "phase_p05_ms": float(np.percentile(phases, 5) * 1000),
        "phase_p50_ms": float(np.percentile(phases, 50) * 1000),
        "phase_p95_ms": float(np.percentile(phases, 95) * 1000),
        "unique_2ms": int(len(set(np.floor((rel - rel_lo) / 0.002).astype(int)))),
        "unique_5ms": int(len(set(np.floor((rel - rel_lo) / 0.005).astype(int)))),
    }


def build_composite(t, force, legs, rel_lo, rel_hi, min_legs, leg_indices=None):
    pts = phase_points(t, force, legs, rel_lo, rel_hi, leg_indices=leg_indices)
    folded = fold_points(pts, rel_lo, rel_hi, BIN_S, min_legs)
    return pts, folded


def dict_by_bin(folded):
    return {round(r["t"], 6): r for r in folded}


def corrected_waveform(wet_fold, dry_fold):
    wet = dict_by_bin(wet_fold)
    dry = dict_by_bin(dry_fold)
    keys = sorted(set(wet) & set(dry))
    rows = []
    for k in keys:
        w = wet[k]
        d = dry[k]
        rows.append({
            "t": k,
            "y": float(w["median"] - d["median"]),
            "wet_sigma": w["sigma"],
            "dry_sigma": d["sigma"],
            "wet_n": w["n"],
            "dry_n": d["n"],
            "wet_legs": w["legs"],
            "dry_legs": d["legs"],
        })
    return rows


def composite_metrics(rows, meta, k, direction, idx, require_bins=True):
    metrics = {name: float("nan") for name in sa.BD_METRIC_NAMES}
    reasons = []
    if len(rows) < 8:
        return sa.BdSegment(k=float(k), seg_idx=int(idx), t_start=0, t_rise=0,
                            t_fall=0, t_end=0, n_samples=len(rows),
                            metrics=metrics, excluded=True,
                            exclusion_reasons=["too few composite bins"])
    lt = np.asarray([r["t"] for r in rows], dtype=float)
    y = np.asarray([r["y"] for r in rows], dtype=float)
    order = np.argsort(lt)
    lt, y = lt[order], y[order]
    speed = float(meta["speed"])
    accel = float(meta["accel"])
    duration = leg_duration(meta)
    t_acc = speed / accel
    t_dec0 = duration - t_acc
    base_mask = (lt >= -0.050) & (lt < -0.005)
    if int(base_mask.sum()) < 3:
        base_mask = (lt >= 0.0) & (lt <= min(0.015, t_acc))
        reasons.append("baseline from early accel bins")
    baseline = float(np.median(y[base_mask])) if int(base_mask.sum()) else float("nan")
    noise = robust_sigma(y[base_mask]) if int(base_mask.sum()) >= 3 else 0.0
    metrics["baseline_median"] = baseline
    metrics["baseline_noise_std"] = 0.0 if not np.isfinite(noise) else float(noise)
    y0 = y - baseline if np.isfinite(baseline) else y
    cruise_lo = t_acc + max(0.030, 0.15 * (t_dec0 - t_acc))
    cruise_hi = t_dec0 - max(0.030, 0.15 * (t_dec0 - t_acc))
    plat_mask = (lt >= cruise_lo) & (lt <= cruise_hi)
    if int(plat_mask.sum()) < 5:
        return sa.BdSegment(k=float(k), seg_idx=int(idx), t_start=0, t_rise=0,
                            t_fall=0, t_end=0, n_samples=len(rows),
                            metrics=metrics, excluded=True,
                            exclusion_reasons=["too few cruise bins"] + reasons)
    high = float(np.median(y0[plat_mask]))
    metrics["high_level"] = high + (baseline if np.isfinite(baseline) else 0.0)
    if high <= 0 or not np.isfinite(high):
        return sa.BdSegment(k=float(k), seg_idx=int(idx), t_start=0, t_rise=0,
                            t_fall=0, t_end=0, n_samples=len(rows),
                            metrics=metrics, excluded=True,
                            exclusion_reasons=["nonpositive high"] + reasons)
    if lt[plat_mask][-1] > lt[plat_mask][0] and int(plat_mask.sum()) >= 4:
        slope, _ = np.polyfit(lt[plat_mask], y0[plat_mask], 1)
        metrics["plateau_slope"] = float(slope)
        metrics["plateau_creep"] = float(abs(slope) * (lt[plat_mask][-1] - lt[plat_mask][0]))
    rise_mask = (lt >= 0.0) & (lt <= min(duration, t_acc + 0.100))
    if int(rise_mask.sum()) >= 3:
        rt = lt[rise_mask]
        ry = y0[rise_mask]
        target = np.minimum(high, high * rt / max(t_acc, 1e-9))
        metrics["rise_error_area"] = float(np.trapezoid(np.abs(target - ry), rt))
        above = np.where(ry >= 0.90 * high)[0]
        # Quantise to bin resolution; do not claim sub-bin precision.
        metrics["rise_delay"] = float(round((rt[int(above[0])] if len(above) else t_acc) / BIN_S) * BIN_S)
        peak = float(np.max(ry))
        metrics["overshoot"] = max(0.0, peak - high - 2.0 * max(metrics["baseline_noise_std"], 1e-9))
    else:
        reasons.append("too few rise bins")
    fall_mask = (lt >= max(0.0, t_dec0 - 0.050)) & (lt <= min(duration + 0.100, duration + WINDOW_POST))
    if int(fall_mask.sum()) >= 3:
        ft = lt[fall_mask]
        fy = y0[fall_mask]
        target = np.where(ft <= duration, high * np.maximum(0.0, (duration - ft) / max(duration - t_dec0, 1e-9)), 0.0)
        metrics["fall_error_area"] = float(np.trapezoid(np.abs(target - fy), ft))
        below = np.where(fy <= 0.10 * high)[0]
        metrics["fall_delay"] = float(round((max(0.0, ft[int(below[0])] - t_dec0) if len(below) else max(0.0, duration - t_dec0)) / BIN_S) * BIN_S)
        trough = float(np.min(fy))
        metrics["undershoot"] = max(0.0, -trough)
        tail_mask = ft >= t_dec0
        if int(tail_mask.sum()) >= 3:
            metrics["tail_area"] = float(np.trapezoid(np.abs(fy[tail_mask]), ft[tail_mask]))
            tol = max(3.0 * metrics["baseline_noise_std"], 1e-9)
            ok = np.abs(fy[tail_mask]) < tol
            settle = max(0.0, duration - t_dec0)
            tt = ft[tail_mask]
            start = None
            for i, good in enumerate(ok):
                if not good:
                    start = None
                elif start is None:
                    start = i
                elif tt[i] - tt[start] >= 0.025:
                    settle = max(0.0, tt[start] - t_dec0)
                    break
            metrics["settling_time"] = float(round(settle / BIN_S) * BIN_S)
    else:
        reasons.append("too few fall bins")
    excluded = any(not np.isfinite(metrics[n]) for n in ("rise_error_area", "fall_error_area", "tail_area", "rise_delay", "fall_delay", "settling_time"))
    if excluded:
        reasons.append("nonfinite required metric")
    return sa.BdSegment(k=float(k), seg_idx=int(idx), t_start=0, t_rise=0,
                        t_fall=0, t_end=0, n_samples=len(rows),
                        metrics=metrics, excluded=excluded,
                        exclusion_reasons=reasons)


def analyse_phase_fold(path, bootstrap=0, seed=12345):
    arr, meta, t, force = load_capture(path)
    k_values = [float(x) for x in meta["k_values"]]
    wet_by_k_dir = {(k, d): [] for k in k_values for d in (-1, 1)}
    for i, leg in enumerate(meta["wet_legs"]):
        wet_by_k_dir[(float(leg["k"]), int(leg["dir"]))].append(i)
    dry_by_dir = {d: [i for i, leg in enumerate(meta["dry_legs"]) if int(leg["dir"]) == d] for d in (-1, 1)}
    duration = leg_duration(meta)
    rel_lo = -WINDOW_PRE
    rel_hi = duration + WINDOW_POST
    dry_composites = {}
    dry_points = {}
    for d in (-1, 1):
        legs = [meta["dry_legs"][i] for i in dry_by_dir[d]]
        pts, fold = build_composite(t, force, legs, rel_lo, rel_hi, MIN_DRY_LEGS_PER_BIN)
        dry_points[d] = pts
        dry_composites[d] = fold
    segs_by_k = {k: [] for k in k_values}
    direction_rows = {-1: [], 1: []}
    composites = {}
    idx = 0
    for k in k_values:
        for d in (-1, 1):
            indices = wet_by_k_dir[(k, d)]
            legs = [meta["wet_legs"][i] for i in indices]
            pts, wet_fold = build_composite(t, force, legs, rel_lo, rel_hi, MIN_WET_LEGS_PER_BIN)
            corr = corrected_waveform(wet_fold, dry_composites[d])
            seg = composite_metrics(corr, meta, k, d, idx)
            segs_by_k[k].append(seg)
            if not seg.excluded and np.isfinite(seg.metrics.get("high_level", np.nan)) and np.isfinite(seg.metrics.get("baseline_median", np.nan)):
                direction_rows[d].append((k, seg.metrics["high_level"] - seg.metrics["baseline_median"], seg.metrics))
            composites[(k, d)] = {"points": pts, "wet_fold": wet_fold, "corrected": corr, "segment": seg}
            idx += 1
    per_k = sa._bd_aggregate_per_k(segs_by_k)
    by = {r.k: r for r in per_k}
    per_k = [by.get(k, sa.BdKResult(k=k, n_segments_total=0, n_segments_included=0, medians={n: float("nan") for n in sa.BD_METRIC_NAMES})) for k in k_values]
    sa._bd_compute_normalised(per_k)
    cost = sa._bd_compute_cost(per_k, sa.BD_DEFAULT_WEIGHTS)
    ok = np.isfinite(cost) & np.array([r.n_segments_included >= 1 for r in per_k])
    if ok.any():
        ks_ok = np.asarray(k_values)[ok]
        c_ok = cost[ok]
        discrete = float(ks_ok[int(np.argmin(c_ok))])
        k_opt = sa._argmin_with_parabolic(ks_ok, c_ok)
    else:
        discrete = None
        k_opt = None
    boot = None
    if bootstrap:
        rng = np.random.default_rng(seed)
        opts = []
        wins = defaultdict(int)
        dry_leg_lists = {d: [meta["dry_legs"][i] for i in dry_by_dir[d]] for d in (-1, 1)}
        for _ in range(int(bootstrap)):
            b_dry = {}
            for d in (-1, 1):
                src = dry_leg_lists[d]
                picks = rng.integers(0, len(src), len(src))
                pts, fold = build_composite(t, force, [src[int(j)] for j in picks], rel_lo, rel_hi, MIN_DRY_LEGS_PER_BIN)
                b_dry[d] = fold
            bmap = {k: [] for k in k_values}
            bi = 0
            for k in k_values:
                for d in (-1, 1):
                    src_indices = wet_by_k_dir[(k, d)]
                    src = [meta["wet_legs"][i] for i in src_indices]
                    picks = rng.integers(0, len(src), len(src))
                    pts, wet_fold = build_composite(t, force, [src[int(j)] for j in picks], rel_lo, rel_hi, MIN_WET_LEGS_PER_BIN)
                    corr = corrected_waveform(wet_fold, b_dry[d])
                    bmap[k].append(composite_metrics(corr, meta, k, d, bi))
                    bi += 1
            bper = sa._bd_aggregate_per_k(bmap)
            bby = {r.k: r for r in bper}
            bper = [bby.get(k, sa.BdKResult(k=k, n_segments_total=0, n_segments_included=0, medians={n: float("nan") for n in sa.BD_METRIC_NAMES})) for k in k_values]
            sa._bd_compute_normalised(bper)
            bc = sa._bd_compute_cost(bper, sa.BD_DEFAULT_WEIGHTS)
            bok = np.isfinite(bc) & np.array([r.n_segments_included >= 1 for r in bper])
            if not bok.any():
                continue
            bks = np.asarray(k_values)[bok]
            bcost = bc[bok]
            dk = float(bks[int(np.argmin(bcost))])
            wins[dk] += 1
            ko = sa._argmin_with_parabolic(bks, bcost)
            if ko is not None and np.isfinite(ko):
                opts.append(float(ko))
        if opts:
            oa = np.asarray(opts)
            boot = {
                "n": int(len(oa)),
                "median": float(np.percentile(oa, 50)),
                "mean": float(np.mean(oa)),
                "std": float(np.std(oa)),
                "p5": float(np.percentile(oa, 5)),
                "p95": float(np.percentile(oa, 95)),
                "wins": {f"{k:.4f}": int(v) for k, v in sorted(wins.items())},
            }
    cov = {"wet": {}, "dry": {}}
    for d in (-1, 1):
        cov["dry"][str(d)] = {
            "window": coverage_for(meta, t, [meta["dry_legs"][i] for i in dry_by_dir[d]], -0.050, 0.150),
            "accel": coverage_for(meta, t, [meta["dry_legs"][i] for i in dry_by_dir[d]], accel_only=True),
        }
    for k in k_values:
        cov["wet"][f"{k:.4f}"] = {}
        for d in (-1, 1):
            legs = [meta["wet_legs"][i] for i in wet_by_k_dir[(k, d)]]
            cov["wet"][f"{k:.4f}"][str(d)] = {
                "window": coverage_for(meta, t, legs, -0.050, 0.150),
                "accel": coverage_for(meta, t, legs, accel_only=True),
            }
    per_k_out = []
    for r, c in zip(per_k, cost):
        row = {"k": r.k, "cost": float(c) if np.isfinite(c) else None, "included": int(r.n_segments_included), "total": int(r.n_segments_total)}
        for name in ("rise_error_area", "overshoot", "undershoot", "tail_area", "plateau_slope", "rise_delay", "fall_delay", "settling_time", "baseline_noise_std", "high_level"):
            v = r.medians.get(name, float("nan"))
            row[name] = float(v) if np.isfinite(v) else None
        per_k_out.append(row)
    composite_out = {}
    for k in k_values:
        composite_out[f"{k:.4f}"] = {}
        for d in (-1, 1):
            item = composites[(k, d)]
            seg = item["segment"]
            corr = item["corrected"]
            composite_out[f"{k:.4f}"][str(d)] = {
                "raw_points": int(len(item["points"])),
                "wet_bins": int(len(item["wet_fold"])),
                "corrected_bins": int(len(corr)),
                "excluded": bool(seg.excluded),
                "reasons": list(seg.exclusion_reasons),
                "n_samples": int(seg.n_samples),
                "high": float(seg.metrics.get("high_level")) if np.isfinite(seg.metrics.get("high_level", np.nan)) else None,
                "baseline": float(seg.metrics.get("baseline_median")) if np.isfinite(seg.metrics.get("baseline_median", np.nan)) else None,
                "noise": float(seg.metrics.get("baseline_noise_std")) if np.isfinite(seg.metrics.get("baseline_noise_std", np.nan)) else None,
            }
    dir_out = {}
    for d in (-1, 1):
        dsegs_by_k = {k: [composites[(k, d)]["segment"]] for k in k_values}
        dper = sa._bd_aggregate_per_k(dsegs_by_k)
        dby = {r.k: r for r in dper}
        dper = [dby.get(k, sa.BdKResult(k=k, n_segments_total=0, n_segments_included=0, medians={n: float("nan") for n in sa.BD_METRIC_NAMES})) for k in k_values]
        sa._bd_compute_normalised(dper)
        dc = sa._bd_compute_cost(dper, sa.BD_DEFAULT_WEIGHTS)
        dok = np.isfinite(dc) & np.array([r.n_segments_included >= 1 for r in dper])
        if dok.any():
            dks = np.asarray(k_values)[dok]
            dcost = dc[dok]
            dir_out[str(d)] = {"discrete": float(dks[int(np.argmin(dcost))]), "k_opt": sa._argmin_with_parabolic(dks, dcost), "cost": [float(x) if np.isfinite(x) else None for x in dc]}
        else:
            dir_out[str(d)] = {"discrete": None, "k_opt": None, "cost": [None for _ in dc]}
    return {"meta": meta, "duration": duration,
            "t_acc": float(meta["speed"]) / float(meta["accel"]),
            "coverage": cov, "composites": composite_out,
            "dry_bins": {str(d): int(len(dry_composites[d])) for d in (-1, 1)},
            "k_opt": k_opt, "discrete_k": discrete,
            "per_k": per_k_out, "bootstrap": boot, "direction": dir_out}


def main():
    path = sys.argv[1]
    res = analyse_phase_fold(path, bootstrap=int(sys.argv[2]) if len(sys.argv) > 2 else 0)
    print(json.dumps(res, indent=2, sort_keys=True, allow_nan=True))


if __name__ == "__main__":
    main()
