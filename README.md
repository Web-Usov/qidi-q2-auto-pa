# QIDI Q2 AutoPA

Experimental automatic Pressure Advance calibration for the **QIDI Q2** using the printer's stock nozzle load cell.

This repository documents and packages the work needed to make [`G0BL1N/autopa`](https://github.com/G0BL1N/autopa) work with QIDI's stock Klipper fork, where the nozzle force sensor is exposed through QIDI's proprietary `probe_air` stack instead of mainline Klipper's `[load_cell]` / `[load_cell_probe]` API.

> **Project status:** research-complete for Q2 load-cell integration and flow-dependent AutoPA. Packaging is still being cleaned up. The repository currently contains both runtime code and the raw research snapshot used to validate it.

## What works

- Read the stock Q2 nozzle load cell through `probe_air.sensor_helper.read_origin_data()` without replacing QIDI's probing implementation.
- Expose that sensor through a small compatibility object that behaves like the subset of Klipper's load-cell API required by autopa.
- Run upstream-style `AUTOPA_SWEEP` on Q2.
- Save and replay `.npz` captures offline.
- Use Q2-specific quality thresholds for the real ~37–38 SPS data stream.
- Reproduce a static/effective PA optimum across independent runs.
- Measure a clear dependence of effective PA on volumetric-flow level.
- Bootstrap sweep segments to estimate uncertainty.

## What does **not** work reliably

Direct automatic measurement of **acceleration-dependent** PA using real 50/100/200 mm/s XY+E trajectories was investigated and rejected in its current form.

The stock Q2 sensor path delivers only about **37–38 samples/s**. A single sample therefore arrives roughly every 26–27 ms, while many of the target acceleration transients at 1800–7200 mm/s² are of comparable or shorter duration. Per-leg analysis, dry mechanical-reference subtraction, fixed-grid analysis, and equivalent-time phase folding were tested; the resulting bootstrap distributions remained broad and X+/X− optima were inconsistent.

The failed real-trajectory method is preserved as **research code**, not as the recommended calibration path. See [docs/LIMITATIONS.md](docs/LIMITATIONS.md).

## Current practical strategy

The validated Q2 path is the regular slow/fast in-air `AUTOPA_SWEEP`:

1. keep the PA-gate axis wobble small;
2. measure load-cell response across a K grid;
3. use the bd-pressure cost estimator;
4. bootstrap individual sweep segments;
5. use the result to characterize PA versus volumetric-flow level.

For the final Orca Adaptive PA table used during this research, flow anchors are measured automatically and acceleration correction is kept separate from the stock-load-cell measurement. The provenance of each value must remain explicit; the project does **not** claim that the Q2 stock sensor directly measured the acceleration axis.

## Q2-specific integration

The central compatibility layer is [`q2_loadcell.py`](q2_loadcell.py).

It:

- resolves QIDI's existing `[probe_air]` object;
- polls `sensor_helper.read_origin_data()` synchronously;
- timestamps samples in Klipper print time via the sensor MCU;
- provides a collector API compatible with the parts of autopa used by Sweep;
- performs a median tare before each acquisition;
- leaves the stock QIDI probe implementation in control of the ADC and Z probing.

The working configuration used during validation was equivalent to:

```ini
[q2_loadcell]
poll_hz: 40
samples_per_second: 40
tare_time: 0.35

[autopa]
capture_dir: /home/mks/printer_data/autopa/captures
profile_path: /home/mks/printer_data/autopa/profiles.json
save_captures: True
sweep_min_segment_samples: 12
sweep_min_segment_rate_hz: 35
```

The configured rate is 40 Hz; successful captures consistently measured an actual incoming rate around 37–38 Hz.

## Important estimator patch

The research found an edge case in the upstream bd-pressure normalization: if a weighted metric is finite and exactly zero for every K (for example `overshoot == 0` over the entire grid), its normalization denominator is zero. Treating that as `NaN` poisons the entire composite cost.

The Q2 snapshot changes the semantics to:

```text
finite value + denom > 0  -> value / denom
finite value + denom = 0  -> 0.0
non-finite value           -> NaN
```

This is intentionally minimal: a metric that is identically zero contains no information for choosing K, so it contributes zero instead of invalidating the sweep.

## Repository state

The current `master` is a **research snapshot**, not yet a clean installable distribution. It intentionally contains:

- runtime copies from the printer;
- duplicate before/after files used during debugging;
- experimental analysis scripts;
- valid and invalid captures;
- camera snapshots;
- a full printer configuration snapshot.

Do not assume every root-level Python file is production code.

The planned cleanup is documented in [docs/REPOSITORY_LAYOUT.md](docs/REPOSITORY_LAYOUT.md).

## Documentation

- [Architecture](docs/ARCHITECTURE.md)
- [Experiment history and evidence](docs/EXPERIMENTS.md)
- [Known limitations](docs/LIMITATIONS.md)
- [Repository cleanup / code review](docs/CODE_REVIEW.md)
- [Repository layout](docs/REPOSITORY_LAYOUT.md)
- [Credits and provenance](CREDITS.md)

## Safety

AutoPA moves the toolhead and extrudes hot filament in open air. Treat all commands as experimental.

- Keep `APPLY=0` while validating a new configuration.
- Do not bypass Klipper's physical extrusion checks just to make a test run.
- Use a large safe Z gap for in-air extrusion.
- Watch the nozzle for a PETG blob growing back onto the hotend.
- Use different dump positions between complete sweeps when running a batch.
- Preserve the original PA and restore it after aborts.
- Do not treat the archived `printer.cfg.q2stage` as a drop-in configuration file.

## Upstream projects

This work is based on / informed by:

- [`G0BL1N/autopa`](https://github.com/G0BL1N/autopa) — load-cell-driven PA calibration engine and bd-pressure Sweep estimator.
- [`CNCKitchen/PrusaPATuner`](https://github.com/CNCKitchen/PrusaPATuner) — algorithmic lineage used by upstream autopa Sweep.
- Mark Struchkov's independent QIDI Q2 Auto-PA research, which documented access to the stock `probe_air` sensor path and practical low-rate polling constraints.

See [CREDITS.md](CREDITS.md) for attribution details.

## License

The derived autopa code is subject to **GNU AGPL-3.0-or-later**, matching upstream autopa. A full license file and preserved upstream notices are required before treating a cleaned release branch as distributable.
