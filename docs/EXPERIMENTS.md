# Experiment history

This document records the main conclusions from the QIDI Q2 AutoPA validation campaign. It is not a complete lab notebook; the repository contains the raw captures and helper scripts used during the work.

## 1. Basic Q2 load-cell integration

The Q2 stock sensor was accessed through QIDI's `probe_air.sensor_helper.read_origin_data()` path and wrapped in `q2_loadcell.py`.

Repeated diagnostic runs established an effective incoming rate around **37–38 Hz** with zero read errors in successful captures.

This rate, rather than the nominal 40 Hz configuration value, is used when judging data quality.

## 2. First broad Sweep

A representative PETG test at 245 °C used:

```text
VFR_LOW=2
VFR=18
TSLOW=1.0
TFAST=0.5
CYCLES=10
K=0.03..0.08 step 0.01
WARMUP=4
PRIME=15
RETRACT=6
WOBBLEAXIS=X
WOBBLE=0.05
ACCEL=1000
APPLY=0
```

The first successful broad run produced an optimum around `K ≈ 0.0507` with an actual sample rate around 37.85 Hz and no collector errors.

Two further repeats shifted modestly upward, motivating more detailed repeatability work rather than accepting one broad run as final.

## 3. Diagnostic repeated-K sequence

A special diagnostic sequence repeated the same K values in one continuous thermal/melt-state run.

The important observation was that the stock sensor could physically distinguish neighboring PA values:

- `K=0.05` showed no consistent real undershoot;
- `K=0.06` repeatedly produced measurable undershoot.

Absolute baseline drifted during the sequence, but the dynamic high-low response stayed comparatively stable. This supported the conclusion that the collector/load-cell path itself was usable.

## 4. Constant-zero normalization bug

A fine-grid run exposed a pure analysis bug: if a weighted metric was exactly zero for all K, normalization produced NaN and poisoned the entire composite cost.

The patch now maps a finite value to `0.0` when the normalization denominator is zero.

Replaying old captures after this patch preserved results when the old estimator had already been valid.

## 5. Fine-grid repeatability at 2→18 mm³/s

Three independent fine runs around the optimum produced approximately:

```text
0.054045
0.052272
0.053588
```

Summary:

```text
mean   ≈ 0.05330
median ≈ 0.05359
sample std ≈ 0.00092
```

This was the key validation that regular AutoPA Sweep on Q2 is reproducible enough to be useful.

## 6. Why normal Sweep ACCEL is not print acceleration

A temporary series varied `ACCEL=1800/3600/7200` in the standard tiny-wobble Sweep and produced different K values.

Source review of `sweep.py` showed why these must **not** be interpreted as `PA(acceleration)`:

- the wobble distance is tiny;
- ACCEL only needs to make the reversal much shorter than PA smoothing time;
- the force waveform is dominated by the PA-smoothed extrusion step, not a representative printed-line acceleration profile.

Those runs are retained only as diagnostics.

## 7. Flow dependence: 2→VFR series

Keeping `VFR_LOW=2` while changing `VFR_HIGH` showed a clear trend toward lower K as high flow increased.

Representative fine results:

```text
2→6   ≈ 0.0690
2→10  ≈ 0.058–0.061 across repeats
2→14  ≈ 0.0582
2→18  ≈ 0.0536
```

Because both absolute flow level and step amplitude changed, this was interpreted as an effective K for a transition, not yet as a pure `K(flow)` law.

## 8. WOBBLE validation

Higher baseline-flow experiments could not pass the standard composite-move extrusion guard with `WOBBLE=0.05` while keeping `WARMUP=4`.

Rather than increasing `max_extrude_cross_section`, the wobble was raised to `0.10` and validated on an already-known `2→10` transition.

Results:

```text
old WOBBLE=0.05: K ≈ 0.0581 and 0.0613
new WOBBLE=0.10: K ≈ 0.0600
```

The new result sat inside normal run-to-run variability, so `WOBBLE=0.10` was accepted as experimentally neutral for the subsequent flow-level tests.

## 9. Equal-step experiment: ΔVFR = 8

To separate absolute flow level from step amplitude, three transitions all used the same ΔVFR=8:

| Transition | Midpoint | K_opt |
|---|---:|---:|
| 2→10 | 6 | 0.060011 |
| 6→14 | 10 | 0.055150 |
| 10→18 | 14 | 0.051851 |

The optimum decreased as the entire equal-sized step moved upward in absolute flow.

The first-undershoot crossover also moved downward:

```text
0.0525 → 0.0500 → 0.0475
```

This strongly supports absolute flow level as a dominant variable.

## 10. Fixed-midpoint experiment: midpoint = 10

To isolate step amplitude, three transitions held the midpoint at 10 while changing ΔVFR:

| Transition | ΔVFR | K_opt |
|---|---:|---:|
| 8→12 | 4 | 0.053693 |
| 6→14 | 8 | 0.055150 |
| 2→18 | 16 | 0.055334 |

The differences were small relative to bootstrap/run-to-run uncertainty. The physical signal amplitude changed strongly with ΔVFR, but the estimated optimum did not move nearly as much as it did when the absolute flow level changed.

Practical conclusion:

> For the validated Sweep method, absolute/midpoint flow is the dominant variable. ΔVFR is a secondary influence and also affects signal quality.

## 11. Real-trajectory Adaptive PA matrix attempt

A separate `AUTOPA_ADAPTIVE_MATRIX` mode attempted to measure acceleration-dependent PA directly using real composite XY+E lines at:

```text
speeds: 50 / 100 / 200 mm/s
flows:  3.91 / 7.82 / 15.6 mm³/s
accel:  1800 / 3600 / 7200 mm/s²
```

The first validation cell (`100 mm/s`, `7.82 mm³/s`, `3600 mm/s²`) failed the stability criterion despite clean collector health.

A representative fixed-grid validation produced:

```text
K_opt ≈ 0.0476
bootstrap median ≈ 0.0498
bootstrap std ≈ 0.0124
p5–p95 ≈ 0.0298–0.0698
```

Bootstrap winners were spread across most of the K grid.

## 12. Equivalent-time phase-fold attempt

Because the stock sensor provides only ~37–38 samples/s, repeated real-motion legs were phase-aligned offline to reconstruct a denser equivalent-time waveform.

Coverage existed, but the result remained highly sensitive to bin policy and dry-reference coverage. In the most favorable tested 10 ms variant:

```text
K_opt ≈ 0.0502
bootstrap median ≈ 0.0552
bootstrap std ≈ 0.0127
p5–p95 ≈ 0.0300–0.0740
```

Direction-specific optima also disagreed materially (`X− ≈ 0.0675`, `X+ ≈ 0.0500`).

The phase-fold method therefore did not improve uncertainty enough to justify a 3×3 physical matrix.

## 13. Final flow-anchor campaign

The final practical calibration strategy returned to the validated regular Sweep and targets the exact Orca working flows:

```text
3.91
7.82
15.6 mm³/s
```

with a common small step (`ΔVFR=4`) around each midpoint.

At the time this document was first created, the `7.82` anchor had been captured and analyzed:

```text
VFR_LOW = 5.82
VFR_HIGH = 9.82
midpoint = 7.82
WOBBLE = 0.14
K_opt = 0.056113
bootstrap median = 0.057250
p5–p95 = 0.053188–0.061478
actual SPS = 37.764
segments = 230/230
errors = 0
```

The remaining final anchors may be committed later; the final summary should be updated from the corresponding analysis JSON rather than copied from chat logs.
