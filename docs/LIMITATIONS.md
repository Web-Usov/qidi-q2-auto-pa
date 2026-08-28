# Known limitations

## Stock Q2 sensor rate

The dominant hardware limitation is the effective QIDI load-cell update rate of approximately **37–38 Hz**.

That is sufficient for the slower `AUTOPA_SWEEP` flow-step protocol, but not for directly resolving many normal printing acceleration transients.

For example, acceleration time `t = V / A` gives:

| Speed | Accel | Accel time |
|---:|---:|---:|
| 50 mm/s | 1800 mm/s² | 27.8 ms |
| 100 mm/s | 1800 mm/s² | 55.6 ms |
| 200 mm/s | 1800 mm/s² | 111.1 ms |
| 50 mm/s | 3600 mm/s² | 13.9 ms |
| 100 mm/s | 3600 mm/s² | 27.8 ms |
| 200 mm/s | 3600 mm/s² | 55.6 ms |
| 50 mm/s | 7200 mm/s² | 6.9 ms |
| 100 mm/s | 7200 mm/s² | 13.9 ms |
| 200 mm/s | 7200 mm/s² | 27.8 ms |

At ~37.5 Hz, one sample interval is about 26.7 ms.

## `samples_per_second` is nominal

`q2_loadcell.py` exposes a configured nominal sample rate for compatibility, but analysis must prefer the sample rate derived from capture timestamps.

Do not infer that changing `samples_per_second` makes the QIDI sensor physically sample faster.

## `AUTOPA_SWEEP ACCEL` is not an Adaptive-PA acceleration axis

The normal Sweep uses a tiny XY wobble only to enable Klipper's PA gate on a composite move. Its `ACCEL` setting governs the tiny reversal transition.

It must not be interpreted as a calibrated `PA(print acceleration)` measurement.

## Flow result is an effective result for a transition

A Sweep always excites a slow/high transition. Experiments showed that the midpoint/absolute flow level dominates over ΔVFR for the tested range, but the estimator still observes a transition rather than a perfectly static flow state.

For final flow anchors, keep the step amplitude consistent so comparisons are meaningful.

## Wobble affects extrusion safety guards

Because Sweep legs are composite XY+E moves, Klipper's `max_extrude_cross_section` applies.

At high `VFR_LOW` with a long `WARMUP`, a very small wobble can imply an extremely large E/XY ratio even though the physical goal is only an in-air calibration.

The preferred response is to calculate and increase `WOBBLE` with margin, then validate that the new wobble is neutral. Do not casually increase `max_extrude_cross_section` just to make a test pass.

## PETG waste / nozzle blob risk

Long calibration batches can create a large hanging extrusion that curls back toward the nozzle.

The validated mitigation is:

- use a large Z clearance;
- spread complete sweeps over different XY dump positions;
- keep a camera/operator watch on the nozzle;
- abort if the extrudate starts accumulating back onto the hotend.

## Full printer config is archival

`printer.cfg.q2stage` is a snapshot of one working printer and contains many unrelated QIDI settings.

It is **not** a minimal installation file and should not be copied wholesale to another Q2.

## `adaptive_matrix.py` is archived research

The real-motion matrix estimator is preserved because it documents an important negative result, but it is not considered production-ready.

Its first validation cell showed broad bootstrap uncertainty and the offline phase-fold reconstruction did not fix direction consistency or bin sensitivity.

## Exact QIDI CS1237 internals are proprietary

The integration intentionally treats `probe_air.sensor_helper.read_origin_data()` as the stable point of contact and does not attempt to own/reconfigure the ADC.

Comments about internal QIDI ADC configuration should be treated as implementation observations unless independently verified from QIDI source/documentation.
