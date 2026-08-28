# Architecture

## Overview

The QIDI Q2 integration is deliberately split into two layers:

1. **QIDI compatibility layer** — adapts the proprietary `probe_air` sensor path to the subset of Klipper's load-cell API expected by autopa.
2. **autopa calibration layer** — runs the upstream-style Sweep routine and analyses force response versus Pressure Advance K.

The goal is to avoid replacing or reconfiguring QIDI's stock probing stack.

## QIDI sensor path

On the tested Q2 firmware, the stock nozzle load cell is owned by `[probe_air]`. The useful raw-reader path is:

```python
probe = printer.lookup_object('probe_air')
helper = probe.sensor_helper
raw = helper.read_origin_data()
```

`q2_loadcell.py` resolves that object on `klippy:ready`, retains the helper MCU, and exposes a `load_cell` object only if no native one already exists.

### Polling

The adapter uses a reactor timer and synchronous `read_origin_data()` calls. During successful captures the observed incoming sample rate was consistently ~37–38 Hz even though configuration advertises 40 Hz.

The effective rate from timestamps is therefore the authoritative rate for analysis.

### Tare

Before every collector acquisition, the adapter samples while stationary for `tare_time` and stores the median raw count as the tare. Each emitted sample contains:

```text
[print_time, force, raw_counts, tare_counts]
```

where the compatibility-layer force signal is the signed raw-count difference. No physical gram calibration is required by the Sweep estimator.

## AutoPA Sweep motion

Klipper Pressure Advance is gated off for pure-E moves in the tested firmware path. Upstream autopa therefore couples each extrusion leg to a very small X or Y movement (`WOBBLE`) so that the move is composite XY+E and PA is active.

Each leg duration is set by the requested slow/fast phase duration. The axis feedrate is chosen so the wobble distance takes exactly that time, while E is slaved over the same move.

Consequences:

- `WOBBLE` is a PA-enable mechanism, not a simulation of normal printing motion.
- the `ACCEL` argument in normal `AUTOPA_SWEEP` controls how quickly the tiny wobble reverses; it must **not** be interpreted as a direct measurement of `PA(acceleration)` for regular printed trajectories.
- because XY and E are combined, Klipper's `max_extrude_cross_section` guard applies. The safe fix is to increase WOBBLE when necessary, not to silently raise physical printer limits.

## Q2 analysis thresholds

Upstream defaults assume a faster load-cell stream. Q2 validation used:

```ini
sweep_min_segment_samples: 12
sweep_min_segment_rate_hz: 35
```

These were selected because valid captures consistently measured roughly 37–38 Hz.

## bd-pressure cost

The Sweep analysis computes robust per-K medians over several force-response metrics, normalizes each metric across the K grid, then combines weighted normalized metrics into a cost.

The Q2 snapshot includes one important semantic fix:

- if a metric is finite but identically zero across every K, its normalization denominator is zero;
- that metric now normalizes to `0.0`, rather than `NaN`.

This prevents a non-informative constant-zero metric such as overshoot from invalidating the entire composite cost.

## Captures

Sweep captures are `.npz` files containing raw samples plus JSON metadata/stats. Offline replay uses the same analysis implementation, allowing estimator changes to be evaluated without consuming filament.

Important metadata includes:

- K grid;
- slow/high volumetric flow;
- phase timings;
- cycle count;
- wobble parameters;
- estimated and measured sample rates;
- load-cell error count;
- transition/window print times.

## Experimental real-motion APA path

`adaptive_matrix.py` is an R&D module that attempted true XY+E line trajectories at 50/100/200 mm/s and 1800/3600/7200 mm/s².

It added:

- dry mechanical-reference trajectories;
- direction-specific dry subtraction;
- line-specific response metrics;
- fixed-grid and bootstrap analysis.

This path is **not validated** and should remain separated from the recommended runtime path. See `LIMITATIONS.md` for why the method was abandoned with the stock sensor.
