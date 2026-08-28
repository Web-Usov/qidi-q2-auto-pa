# autopa - real-motion Adaptive PA matrix calibration
#
# This is intentionally isolated from AUTOPA_SWEEP.  Sweep's ACCEL parameter is
# only the tiny wobble transition guard; this module uses real composite XY+E
# lines with SET_VELOCITY_LIMIT ACCEL=... so pressure advance acts on the same
# kind of moves Orca's Adaptive PA matrix is meant to model.
import json, logging, math

import numpy as np

from . import sweep_analysis as sa


LINE_LENGTH_MM = 40.0
DEFAULT_X0 = 80.0
DEFAULT_X1 = 120.0
DEFAULT_Z = 220.0
DEFAULT_TEMP = 245.0
BASE_PA = 0.032

MATRIX_ORDER = (
    # mixed physical run order: (speed_mm_s, flow_mm3_s, accel_mm_s2)
    (100.0, 7.82, 3600.0),
    (200.0, 15.6, 1800.0),
    (50.0, 3.91, 7200.0),
    (200.0, 15.6, 7200.0),
    (50.0, 3.91, 1800.0),
    (100.0, 7.82, 1800.0),
    (50.0, 3.91, 3600.0),
    (200.0, 15.6, 3600.0),
    (100.0, 7.82, 7200.0),
)

ORCA_ORDER = (
    (50.0, 3.91, 7200.0),
    (100.0, 7.82, 7200.0),
    (200.0, 15.6, 7200.0),
    (50.0, 3.91, 3600.0),
    (100.0, 7.82, 3600.0),
    (200.0, 15.6, 3600.0),
    (50.0, 3.91, 1800.0),
    (100.0, 7.82, 1800.0),
    (200.0, 15.6, 1800.0),
)


def _frange_inclusive(start, end, step):
    n = int(math.floor((end - start) / step + 0.5))
    vals = [round(start + i * step, 10) for i in range(n + 1)]
    return [v for v in vals if v <= end + 1e-9]


def _as_float_list(x):
    return [float(v) for v in x]


def _compute_cost(per_k):
    sa._bd_compute_normalised(per_k)
    return sa._bd_compute_cost(per_k, sa.BD_DEFAULT_WEIGHTS)


def _line_metric_segment(t, y, k, seg_idx, t0, t1, speed, accel,
                         min_segment_samples=8, min_segment_rate_hz=20.0):
    metrics = {name: float("nan") for name in sa.BD_METRIC_NAMES}
    excluded = False
    reasons = []
    mask = (t >= t0) & (t <= t1)
    lt = np.asarray(t[mask], dtype=float) - float(t0)
    ly = np.asarray(y[mask], dtype=float)
    n = int(len(lt))
    duration = max(float(t1) - float(t0), 1e-9)
    if n < min_segment_samples:
        excluded = True
        reasons.append("only %d samples in line leg" % n)
        return sa.BdSegment(k=float(k), seg_idx=int(seg_idx),
            t_start=float(t0), t_rise=float(t0), t_fall=float(t1),
            t_end=float(t1), n_samples=n, metrics=metrics,
            excluded=excluded, exclusion_reasons=reasons)
    rate = n / duration
    if rate < min_segment_rate_hz:
        excluded = True
        reasons.append("low sample rate %.1fHz" % rate)

    # Geometry of the real line move.  For our 40 mm lines all requested
    # combinations are trapezoidal, but clamp for robustness.
    t_acc = min(float(speed) / max(float(accel), 1e-9), duration * 0.45)
    t_dec0 = max(t_acc, duration - t_acc)
    cruise_lo = min(duration, t_acc + max(0.010, 0.10 * (t_dec0 - t_acc)))
    cruise_hi = max(cruise_lo, t_dec0 - max(0.010, 0.10 * (t_dec0 - t_acc)))
    if cruise_hi <= cruise_lo + 1e-6:
        cruise_lo = duration * 0.35
        cruise_hi = duration * 0.65

    # The line has no explicit pre-leg dwell.  Use the first samples as the
    # local baseline, then judge the acceleration/deceleration transient against
    # the dry-subtracted cruise plateau.
    # The line has no pre-leg dwell; keep this window very narrow so it does
    # not swallow the acceleration transient.  On 40 Hz captures this can mean a
    # near-zero local noise estimate, which is still preferable to excluding
    # good line legs because acceleration itself was counted as "noise".
    base_mask = lt <= max(0.010, min(0.20 * t_acc, 0.030))
    if int(base_mask.sum()) < 2:
        base_mask = lt <= min(duration, max(duration * 0.08, 0.015))
    baseline = float(np.median(ly[base_mask])) if int(base_mask.sum()) else float("nan")
    noise = float(np.std(ly[base_mask])) if int(base_mask.sum()) > 1 else 0.0
    metrics["baseline_median"] = baseline
    metrics["baseline_noise_std"] = noise
    y0 = ly - baseline if np.isfinite(baseline) else ly

    plat_mask = (lt >= cruise_lo) & (lt <= cruise_hi)
    if int(plat_mask.sum()) < 3:
        excluded = True
        reasons.append("too few cruise samples")
        high = float("nan")
    else:
        high = float(np.median(y0[plat_mask]))
        metrics["high_level"] = high + (baseline if np.isfinite(baseline) else 0.0)
        if int(plat_mask.sum()) >= 4 and lt[plat_mask][-1] > lt[plat_mask][0]:
            slope, _b = np.polyfit(lt[plat_mask], y0[plat_mask], 1)
            metrics["plateau_slope"] = float(slope)
            metrics["plateau_creep"] = float(abs(slope) *
                                             (lt[plat_mask][-1] - lt[plat_mask][0]))

    if np.isfinite(high) and high > 0:
        rise_mask = lt <= min(duration, t_acc + 0.10)
        fall_mask = lt >= max(0.0, t_dec0 - 0.05)
        if int(rise_mask.sum()) >= 2:
            rt = lt[rise_mask]
            ry = y0[rise_mask]
            target = np.minimum(high, high * rt / max(t_acc, 1e-9))
            metrics["rise_error_area"] = float(np.trapezoid(np.abs(target - ry), rt))
            above = np.where(ry >= 0.90 * high)[0]
            metrics["rise_delay"] = float(rt[int(above[0])]) if len(above) else float(t_acc)
            peak = float(np.max(ry))
            metrics["overshoot"] = max(0.0, peak - high - 2.0 * max(noise, 1e-9))
            metrics["rise_slope"] = peak / max(metrics["rise_delay"], 1e-9)
        if int(fall_mask.sum()) < 2:
            fall_mask = lt >= max(0.0, 0.75 * duration)
        if int(fall_mask.sum()) >= 2:
            ft = lt[fall_mask]
            fy = y0[fall_mask]
            target = high * np.maximum(0.0, (duration - ft) / max(duration - t_dec0, 1e-9))
            metrics["fall_error_area"] = float(np.trapezoid(np.abs(target - fy), ft))
            below = np.where(fy <= 0.10 * high)[0]
            metrics["fall_delay"] = (
                max(0.0, float(ft[int(below[0])] - t_dec0)) if len(below)
                else max(0.0, duration - t_dec0))
            trough = float(np.min(fy))
            metrics["undershoot"] = max(0.0, -trough)
            tail_mask = lt >= max(0.0, min(t_dec0, 0.75 * duration))
            if int(tail_mask.sum()) >= 2:
                metrics["tail_area"] = float(np.trapezoid(np.abs(y0[tail_mask]), lt[tail_mask]))
                tol = max(3.0 * noise, 1e-9)
                ok = np.abs(y0[tail_mask]) < tol
                settle = float("nan")
                tt = lt[tail_mask]
                start = None
                for i, good in enumerate(ok):
                    if not good:
                        start = None
                    elif start is None:
                        start = i
                    elif tt[i] - tt[start] >= 0.025:
                        settle = float(tt[start] - t_dec0)
                        break
                if not np.isfinite(settle):
                    settle = max(0.0, duration - t_dec0)
                metrics["settling_time"] = float(settle)
            else:
                # Keep the composite cost finite on sparse 40 Hz captures.  A
                # missing tail sample is a sampling limitation of this real-line
                # protocol, not an invalid physical segment; penalise it by the
                # available decel duration instead of poisoning the whole K.
                metrics["tail_area"] = 0.0
                metrics["settling_time"] = max(0.0, duration - t_dec0)
    else:
        excluded = True
        reasons.append("dry-subtracted cruise level not positive")

    if np.isfinite(metrics["high_level"]) and noise > 0:
        delta = float(high)
        if delta <= 0:
            excluded = True
            reasons.append("line response %.1f not positive" % delta)
        elif noise > 2.0 * abs(delta):
            excluded = True
            reasons.append("baseline noise %.1f > 200%% of line response %.1f" %
                           (noise, delta))

    return sa.BdSegment(k=float(k), seg_idx=int(seg_idx),
        t_start=float(t0), t_rise=float(t0), t_fall=float(t1), t_end=float(t1),
        n_samples=n, metrics=metrics, excluded=excluded,
        exclusion_reasons=reasons)


def analyse_adaptive_capture(arr, meta, bootstrap=0, seed=12345):
    arr = np.asarray(arr, dtype=float)
    if len(arr) < 10:
        return {"status": "INVALID", "reason": "too few samples"}
    t_abs = arr[:, 0]
    force = -(arr[:, 2] - arr[:, 3])
    if not np.all(np.diff(t_abs) >= 0):
        return {"status": "INVALID", "reason": "timestamps not monotonic"}
    speed = float(meta["speed"])
    accel = float(meta["accel"])
    k_values = [float(x) for x in meta["k_values"]]
    dry_legs = meta.get("dry_legs", [])
    wet_legs = meta.get("wet_legs", [])
    if not dry_legs or not wet_legs:
        return {"status": "INVALID", "reason": "missing dry/wet legs"}

    # Direction-specific dry median on normalized leg time.
    grid = np.linspace(0.0, 1.0, 101)
    dry_by_dir = {}
    dry_amp_by_dir = {}
    for direction in (-1, 1):
        curves = []
        for leg in dry_legs:
            if int(leg["dir"]) != direction:
                continue
            t0, t1 = float(leg["t0"]), float(leg["t1"])
            mask = (t_abs >= t0) & (t_abs <= t1)
            if int(mask.sum()) < 3:
                continue
            rel = (t_abs[mask] - t0) / max(t1 - t0, 1e-9)
            yy = force[mask]
            yy = yy - float(np.median(yy[:max(1, min(3, len(yy)))]))
            curves.append(np.interp(grid, rel, yy))
        if curves:
            med = np.median(np.asarray(curves), axis=0)
            dry_by_dir[direction] = med
            dry_amp_by_dir[direction] = float(np.percentile(med, 95) -
                                              np.percentile(med, 5))
        else:
            dry_by_dir[direction] = np.zeros_like(grid)
            dry_amp_by_dir[direction] = float("nan")

    corrected = np.array(force, copy=True)
    for leg in wet_legs:
        direction = int(leg["dir"])
        t0, t1 = float(leg["t0"]), float(leg["t1"])
        mask = (t_abs >= t0) & (t_abs <= t1)
        if not int(mask.sum()):
            continue
        rel = (t_abs[mask] - t0) / max(t1 - t0, 1e-9)
        corrected[mask] = corrected[mask] - np.interp(
            rel, grid, dry_by_dir.get(direction, np.zeros_like(grid)))

    segs_by_k = {float(k): [] for k in k_values}
    dir_level = {-1: [], 1: []}
    seg_idx = 0
    for leg in wet_legs:
        k = float(leg["k"])
        seg = _line_metric_segment(t_abs, corrected, k, seg_idx,
                                   float(leg["t0"]), float(leg["t1"]),
                                   speed, accel)
        segs_by_k.setdefault(k, []).append(seg)
        if not seg.excluded and np.isfinite(seg.metrics.get("high_level", np.nan)):
            base = seg.metrics.get("baseline_median", 0.0)
            dir_level[int(leg["dir"])].append(seg.metrics["high_level"] - base)
        seg_idx += 1

    per_k = sa._bd_aggregate_per_k(segs_by_k)
    by_k = {r.k: r for r in per_k}
    per_k = [by_k.get(float(k), sa.BdKResult(
        k=float(k), n_segments_total=0, n_segments_included=0,
        medians={n: float("nan") for n in sa.BD_METRIC_NAMES}))
        for k in k_values]
    cost = _compute_cost(per_k)
    quality = np.asarray([r.n_segments_included >= max(4, int(0.5 * r.n_segments_total))
                          for r in per_k], dtype=bool)
    finite_quality = np.isfinite(cost) & quality
    if finite_quality.any():
        ks_q = np.asarray(k_values, dtype=float)[finite_quality]
        c_q = cost[finite_quality]
        k_opt = sa._argmin_with_parabolic(ks_q, c_q)
        discrete = float(ks_q[int(np.argmin(c_q))])
        edge = discrete in (float(k_values[0]), float(k_values[-1]))
    else:
        k_opt = None
        discrete = None
        edge = True

    levels = []
    for r in per_k:
        base = r.medians.get("baseline_median", float("nan"))
        high = r.medians.get("high_level", float("nan"))
        if np.isfinite(base) and np.isfinite(high):
            levels.append(high - base)
    wet_level = float(np.nanmedian(levels)) if levels else float("nan")
    dry_amp = float(np.nanmedian([v for v in dry_amp_by_dir.values()
                                  if np.isfinite(v)])) if dry_amp_by_dir else float("nan")
    dry_ratio = (dry_amp / wet_level) if (np.isfinite(dry_amp) and
                                          np.isfinite(wet_level) and wet_level > 0) else float("nan")
    direction_divergence = float("nan")
    if len(dir_level[-1]) >= 2 and len(dir_level[1]) >= 2:
        a = float(np.median(dir_level[-1]))
        b = float(np.median(dir_level[1]))
        direction_divergence = abs(a - b) / max(abs((a + b) * 0.5), 1e-9)

    boot = None
    if bootstrap and finite_quality.any():
        rng = np.random.default_rng(int(seed))
        wins = {float(k): 0 for k in k_values}
        opts = []
        for _i in range(int(bootstrap)):
            bmap = {}
            for k in k_values:
                src = segs_by_k.get(float(k), [])
                if not src:
                    bmap[float(k)] = []
                    continue
                picks = rng.integers(0, len(src), len(src))
                bmap[float(k)] = [src[int(j)] for j in picks]
            bper = sa._bd_aggregate_per_k(bmap)
            bby = {r.k: r for r in bper}
            bper = [bby.get(float(k), sa.BdKResult(
                k=float(k), n_segments_total=0, n_segments_included=0,
                medians={n: float("nan") for n in sa.BD_METRIC_NAMES}))
                for k in k_values]
            bc = _compute_cost(bper)
            bq = np.asarray([r.n_segments_included >= max(4, int(0.5 * r.n_segments_total))
                             for r in bper], dtype=bool)
            ok = np.isfinite(bc) & bq
            if not ok.any():
                continue
            bks = np.asarray(k_values, dtype=float)[ok]
            bcost = bc[ok]
            dk = float(bks[int(np.argmin(bcost))])
            wins[dk] = wins.get(dk, 0) + 1
            ko = sa._argmin_with_parabolic(bks, bcost)
            if ko is not None and np.isfinite(ko):
                opts.append(float(ko))
        if opts:
            oa = np.asarray(opts, dtype=float)
            boot = {
                "n": int(len(oa)),
                "median": float(np.percentile(oa, 50)),
                "mean": float(np.mean(oa)),
                "std": float(np.std(oa)),
                "p5": float(np.percentile(oa, 5)),
                "p95": float(np.percentile(oa, 95)),
                "wins": {("%.4f" % k): int(v) for k, v in sorted(wins.items()) if v},
            }

    per_k_out = []
    for r, c in zip(per_k, cost):
        row = {"k": float(r.k), "cost": float(c) if np.isfinite(c) else None,
               "included": int(r.n_segments_included),
               "total": int(r.n_segments_total)}
        for name in ("rise_error_area", "overshoot", "undershoot", "tail_area",
                     "plateau_slope", "rise_delay", "fall_delay",
                     "settling_time", "baseline_noise_std", "high_level"):
            v = r.medians.get(name, float("nan"))
            row[name] = float(v) if np.isfinite(v) else None
        per_k_out.append(row)

    status = "VALID"
    reason = None
    if k_opt is None:
        status, reason = "INVALID", "no finite cost"
    elif edge:
        status, reason = "INVALID", "minimum on grid edge"
    elif np.isfinite(dry_ratio) and dry_ratio > 0.75:
        status, reason = "INVALID", "dry mechanical signal dominates"

    return {"status": status, "reason": reason, "k_opt": k_opt,
            "discrete_k": discrete, "per_k": per_k_out,
            "bootstrap": boot, "sps": float(meta.get("sps", 0.0)),
            "dry_amp": dry_amp, "wet_level": wet_level,
            "dry_ratio": dry_ratio,
            "direction_divergence": direction_divergence,
            "segments_included": int(sum(r.n_segments_included for r in per_k)),
            "segments_total": int(sum(r.n_segments_total for r in per_k))}


class AdaptiveMatrixMixin:
    def _register_adaptive_matrix_commands(self):
        self.gcode.register_command(
            "AUTOPA_ADAPTIVE_MATRIX", self.cmd_AUTOPA_ADAPTIVE_MATRIX,
            desc=self.cmd_AUTOPA_ADAPTIVE_MATRIX_help)

    cmd_AUTOPA_ADAPTIVE_MATRIX_help = (
        "Real-motion Adaptive PA matrix/cell. Optional SPEED/FLOW/ACCEL runs "
        "one cell grid; without them runs the mixed 3x3 coarse+fine batch.")

    def _adaptive_run_grid(self, gcmd, speed, flow, accel, k_values, cycles,
                           x0, x1, y, z, temp, dry_cycles, maxfilament):
        lc = self._get_load_cell(gcmd)
        toolhead = self.printer.lookup_object("toolhead")
        self._check_extrude_temp(gcmd)
        area = self._filament_area()
        length = abs(float(x1) - float(x0))
        if length <= 0:
            raise gcmd.error("adaptive matrix: X0/X1 must define a line")
        e_per_xy = float(flow) / (float(speed) * area)
        e_leg = length * e_per_xy
        total_e = e_leg * 2.0 * float(cycles) * len(k_values)
        total_e += gcmd.get_float("PRIME", 15.0, minval=0.0, maxval=2000.0)
        if total_e > float(maxfilament):
            raise gcmd.error("adaptive matrix: filament budget %.1fmm exceeds "
                             "MAXFILAMENT=%.1f" % (total_e, float(maxfilament)))

        old_pa = self._get_pa()
        old_accel = None
        try:
            old_accel = toolhead.get_status(self.reactor.monotonic()).get("max_accel")
        except Exception:
            old_accel = None
        meta = self._base_meta(lc, "adaptive_matrix", gcmd)
        meta.update({
            "speed": float(speed), "flow": float(flow), "accel": float(accel),
            "line_length": float(length), "x0": float(x0), "x1": float(x1),
            "y": float(y), "z": float(z), "e_per_xy": float(e_per_xy),
            "e_leg": float(e_leg), "k_values": _as_float_list(k_values),
            "cycles": int(cycles), "dry_cycles": int(dry_cycles),
            "dry_legs": [], "wet_legs": [], "maxfilament": float(maxfilament),
            "old_pa": float(old_pa), "target_pa_restore": BASE_PA,
        })

        collector = lc.get_collector()
        dry_legs = meta["dry_legs"]
        wet_legs = meta["wet_legs"]
        prime = gcmd.get_float("PRIME", 15.0, minval=0.0, maxval=2000.0)
        retract = gcmd.get_float("RETRACT", 6.0, minval=0.0, maxval=200.0)
        feed = float(speed) * 60.0
        expected_s = (length / float(speed)) * (2 * dry_cycles + 2 * cycles * len(k_values)) + 20.0
        self._set_busy("adaptive_matrix", expected_s)
        self._save_gcode_state("autopa_adaptive")
        arr = None
        errs = None
        try:
            self.gcode.run_script_from_command("G90")
            self.gcode.run_script_from_command("M83")
            self.gcode.run_script_from_command("SET_VELOCITY_LIMIT ACCEL=%.3f" % float(accel))
            self.gcode.run_script_from_command("G1 Z%.3f F12000" % float(z))
            self.gcode.run_script_from_command("G1 X%.3f Y%.3f F18000" % (float(x0), float(y)))
            toolhead.wait_moves()
            t0 = toolhead.get_last_move_time()
            meta["t0"] = float(t0)
            collector.start_collecting(min_time=t0)

            cur_x = float(x0)
            for i in range(int(dry_cycles) * 2):
                nxt = float(x1) if cur_x == float(x0) else float(x0)
                t_start = toolhead.get_last_move_time()
                self.gcode.run_script_from_command("G1 X%.3f F%.1f" % (nxt, feed))
                t_end = toolhead.get_last_move_time()
                dry_legs.append({"t0": float(t_start), "t1": float(t_end),
                                 "dir": 1 if nxt > cur_x else -1})
                cur_x = nxt

            if prime > 0:
                self.gcode.run_script_from_command("G1 E%.5f F300" % prime)
            for k in k_values:
                self._set_pa(float(k))
                for c in range(int(cycles) * 2):
                    nxt = float(x1) if cur_x == float(x0) else float(x0)
                    t_start = toolhead.get_last_move_time()
                    self.gcode.run_script_from_command(
                        "G1 X%.3f E%.6f F%.1f" % (nxt, e_leg, feed))
                    t_end = toolhead.get_last_move_time()
                    wet_legs.append({"t0": float(t_start), "t1": float(t_end),
                                     "dir": 1 if nxt > cur_x else -1,
                                     "k": float(k)})
                    cur_x = nxt
            if retract > 0:
                self.gcode.run_script_from_command("G1 E-%.5f F1800" % retract)
            t_end = toolhead.get_last_move_time()
            meta["t_end"] = float(t_end)
            samples, errs = collector.collect_until(t_end)
            arr = np.asarray(samples, dtype=float)
        finally:
            if collector.is_started:
                try:
                    samples, errs = collector.stop_collecting()
                    arr = np.asarray(samples, dtype=float)
                except Exception:
                    logging.exception("autopa adaptive: collector stop failed")
            self._set_pa(BASE_PA)
            if old_accel:
                self.gcode.run_script_from_command("SET_VELOCITY_LIMIT ACCEL=%.3f" % float(old_accel))
            self._restore_gcode_state("autopa_adaptive", move=False)
            self._clear_busy()

        meta["errors"] = errs if errs else 0
        result = analyse_adaptive_capture(arr, meta, bootstrap=0)
        stats = dict(kind="adaptive_matrix", **result)
        saved_path = None
        if self.save_captures:
            saved = self._run_off_reactor(self._write_capture, arr, meta, stats)
            saved_path = self._register_capture(saved)
        return result, saved_path, meta

    def cmd_AUTOPA_ADAPTIVE_MATRIX(self, gcmd):
        temp = gcmd.get_float("TEMP", DEFAULT_TEMP, minval=0.0, maxval=350.0)
        x0 = gcmd.get_float("X0", DEFAULT_X0)
        x1 = gcmd.get_float("X1", DEFAULT_X1)
        y = gcmd.get_float("Y", 100.0)
        z = gcmd.get_float("Z", DEFAULT_Z)
        dry_cycles = gcmd.get_int("DRY_CYCLES", 5, minval=2, maxval=50)
        maxfilament = gcmd.get_float("MAXFILAMENT", 5000.0, minval=1.0)
        # Heating is part of the safety envelope for the standalone batch.
        if temp > 0:
            self.gcode.run_script_from_command("M109 S%.1f" % temp)

        if gcmd.get("SPEED", None) is not None:
            speed = gcmd.get_float("SPEED")
            flow = gcmd.get_float("FLOW")
            accel = gcmd.get_float("ACCEL")
            cycles = gcmd.get_int("CYCLES", 5, minval=1, maxval=50)
            kstart = gcmd.get_float("KSTART", 0.025, minval=0.0)
            kend = gcmd.get_float("KEND", 0.090, minval=0.0)
            kstep = gcmd.get_float("KSTEP", 0.005, above=0.0)
            ks = _frange_inclusive(kstart, kend, kstep)
            result, path, meta = self._adaptive_run_grid(
                gcmd, speed, flow, accel, ks, cycles, x0, x1, y, z, temp,
                dry_cycles, maxfilament)
            self._last = {"method": "adaptive_matrix", "result": result,
                          "capture": path, "meta": meta}
            self._invalidate_status()
            gcmd.respond_info("AUTOPA_ADAPTIVE_MATRIX cell %gmm/s %.3gmm3/s "
                              "A=%g: %s K=%s discrete=%s capture=%s" %
                              (speed, flow, accel, result.get("status"),
                               result.get("k_opt"), result.get("discrete_k"),
                               path))
            return

        # Full batch: one fixed grid for all nine cells.  Do not do a coarse+
        # fine search here: the bd composite cost normalises metrics within the
        # current grid, so changing grids can move the minimum even on identical
        # raw per-K metrics.  Keep every cell on the same full grid and normalise
        # once per cell.
        outputs = []
        xys = [(80, 80), (140, 80), (200, 80), (80, 140), (140, 140),
               (200, 140), (80, 200), (140, 200), (200, 200)]
        for idx, (speed, flow, accel) in enumerate(MATRIX_ORDER):
            cx, cy = xys[idx % len(xys)]
            fixed_ks = _frange_inclusive(0.025, 0.085, 0.0025)
            result, path, _meta = self._adaptive_run_grid(
                gcmd, speed, flow, accel, fixed_ks, 8, cx, cx + LINE_LENGTH_MM,
                cy, z, temp, dry_cycles, maxfilament)
            if result.get("status") != "VALID":
                outputs.append({"speed": speed, "flow": flow, "accel": accel,
                                "status": result.get("status"),
                                "reason": result.get("reason"),
                                "capture": path})
                break
            outputs.append({"speed": speed, "flow": flow, "accel": accel,
                            "status": "VALID", "capture": path,
                            "k_opt": result.get("k_opt"),
                            "discrete_k": result.get("discrete_k")})

        self._set_pa(BASE_PA)
        self.gcode.run_script_from_command("M104 S0")
        self._last = {"method": "adaptive_matrix", "cells": outputs}
        self._invalidate_status()
        lines = ["AUTOPA_ADAPTIVE_MATRIX batch:"]
        for r in outputs:
            lines.append("  speed=%g flow=%.3g accel=%g %s K=%s capture=%s" %
                         (r["speed"], r["flow"], r["accel"], r["status"],
                          r.get("k_opt"), r.get("capture")))
            if r.get("reason"):
                lines.append("    reason: %s" % r["reason"])
        gcmd.respond_info("\n".join(lines))
