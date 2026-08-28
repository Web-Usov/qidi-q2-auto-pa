# Production limitations

This file describes limitations of the **current production result**. For the full experimental history, see `HISTORY.md`.

## 1. Q2 stock sensor path is ~38 SPS

Although the adapter is configured for 40 Hz, successful Q2 captures consistently deliver about 37–38 useful samples/s.

That rate is sufficient for the validated standard Sweep flow-step estimator, but it was not sufficient for a stable direct measurement of short real-print acceleration transients at the target 1800/3600/7200 mm/s².

## 2. The output is calculated APA, not nine direct cells

The 3×3 output combines:

- direct load-cell flow anchors at 3.91 and 7.82;
- a short high-flow extrapolation to 15.6 from validated midpoint 10/14 equal-step measurements;
- relative acceleration factors derived from three standard tiny-wobble Sweep runs.

Therefore the result is best described as:

> **a deterministic empirical APA model derived from Q2 load-cell measurements**

not:

> nine independently measured real-trajectory `PA(flow, acceleration)` values.

## 3. Sweep ACCEL is only a proxy

In standard AutoPA Sweep, PA is enabled by a tiny composite X/Y+E wobble. `ACCEL` changes the dynamics of that small gate movement; it is not the same motion profile as printing a normal line at the same acceleration.

Production uses its measured influence only as a **relative factor normalized at 3600**. This is the least assumption-heavy way found to retain material-specific acceleration information without importing manual data from another filament, but it remains an empirical approximation.

## 4. High-flow 15.6 is extrapolated

The direct centered `13.6→17.6` protocol produced technically clean captures but failed the research repeatability rule and disagreed with the stable monotonic flow trend.

Production therefore measures midpoints 10 and 14 with the validated equal-ΔVFR=8 protocol and extrapolates only 1.6 mm³/s to 15.6.

If future sensor/runtime improvements make a direct 15.6 anchor repeatable, the model should be revised rather than preserving this extrapolation by convention.

## 5. Material and temperature specificity

Do not copy a 3×3 table from another PETG/PLA/brand/temperature into a new filament profile and call it calibrated. The entire point of this workflow is to derive the numbers from the current material.

A new material or materially different nozzle/temperature/extrusion system should get a new run.

## 6. No automatic visual safety

The Python runner can verify printer state, sensor state and capture quality, but it cannot determine from telemetry whether a PETG pile has physically curled back onto the nozzle.

That is why physical/camera confirmation remains a hard checkpoint before each step. An agent may automate that check only if it actually has access to a current image and can inspect it.

## 7. Expanded extrusion guard

The tiny-wobble method requires an enlarged `max_extrude_cross_section`. This weakens a global Klipper safety guard and is a real operational tradeoff. See `SAFETY.md`.

## 8. Production candidate status

The underlying Q2 adapter, Sweep runtime, estimator and measurement parameters were validated during the research campaign. The new **stepwise orchestration code** packages those proven pieces into a production workflow and should receive a smoke test on the actual Q2 after installation before being treated as immutable infrastructure.

A smoke test should first run `preflight`, then a single controlled calibration step with camera supervision, verify capture/QC output, PA restoration and hotend target zero, and only then proceed with a full material run.
