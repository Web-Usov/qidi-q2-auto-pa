# Production implementation

This document describes **how the production code works**. Experimental history and alternative theories belong in `HISTORY.md`.

## Components

### `runtime/klipper/q2_loadcell.py`

Compatibility adapter for QIDI Q2's stock nozzle force sensor.

QIDI exposes the sensor through the proprietary `probe_air` object. The adapter reads:

```python
printer.lookup_object('probe_air').sensor_helper.read_origin_data()
```

and exposes the subset of Klipper load-cell behaviour required by AutoPA Sweep.

It does not replace QIDI probing logic or reconfigure the CS1237 ADC.

Validated configuration:

```ini
[q2_loadcell]
poll_hz: 40
samples_per_second: 40
tare_time: 0.35
```

The configured rate is 40 Hz; real successful captures on Q2 are normally about **37–38 samples/s**.

`QPA_SENSOR_TEST` is used before calibration to verify fresh sensor reads and read-error behaviour.

### `runtime/autopa/`

Production Sweep runtime.

The canonical production paths are:

- `__init__.py` — tested AutoPA 0.2.0-era core from the Q2 campaign;
- `sweep.py` — validated `AUTOPA_SWEEP` implementation;
- `sweep_analysis.py` — validated bd-pressure estimator with the constant-zero normalization fix;
- `capture.py`, `decay.py`, `profiles.py` — compatibility mixins. Production intentionally registers only Sweep; Decay and single-PA profile management are not part of the APA workflow.

The important estimator fix is:

```text
finite metric + denominator > 0 -> metric / denominator
finite metric + denominator = 0 -> 0.0
non-finite metric               -> NaN
```

A metric that is identically zero across the K grid contains no selection information and therefore contributes zero instead of invalidating the entire cost.

### `tools/q2_apa_pipeline.py`

Stateful physical calibration orchestrator.

It communicates with Moonraker at `http://127.0.0.1` by default and stores each run at:

```text
/home/mks/printer_data/autopa/apa-runs/<timestamp>/
```

A run consists of seven accepted Sweep captures:

| Name | VFR low→high | Midpoint/use | Sweep ACCEL |
|---|---|---|---:|
| `flow391` | 1.91→5.91 | direct flow 3.91 | 1000 |
| `flow782` | 5.82→9.82 | direct flow 7.82 | 1000 |
| `mid10` | 6→14 | upper-flow trend | 1000 |
| `mid14` | 10→18 | upper-flow trend | 1000 |
| `acc1800` | 2→18 | relative acceleration proxy | 1800 |
| `acc3600` | 2→18 | proxy reference | 3600 |
| `acc7200` | 2→18 | relative acceleration proxy | 7200 |

Every production Sweep uses the same fixed K grid and timing:

```text
TSLOW=1
TFAST=0.5
CYCLES=10
KSTART=0.030
KEND=0.085
KSTEP=0.0025
WARMUP=4
PRIME=15
RETRACT=6
WOBBLEAXIS=X
WOBBLE=0.14
APPLY=0
```

`MAXFILAMENT` is calculated from the actual filament cross-sectional area and the requested VFR/timing, padded by 10%, with a hard pipeline ceiling of 2500 mm per Sweep. This limit controls total calibration consumption; it is not a substitute for Klipper's extrusion safety checks.

The runner is intentionally stepwise. It does not silently perform seven hot extrusion experiments in one unattended call. The agent/operator inspects the printer between steps and explicitly passes `--confirm-clear`.

### `tools/q2_apa_analysis.py`

Offline deterministic analyzer.

It:

1. loads `.npz` captures with `allow_pickle=False`;
2. replays the same `sweep_analysis.py` estimator used on the printer;
3. normalizes capture error metadata robustly whether stored as an integer, tuple/list or nested structure;
4. performs a deterministic 1000-sample bootstrap (`seed=12345`);
5. applies quality gates;
6. calculates the flow anchors and acceleration proxy factors;
7. rejects non-monotonic final models;
8. writes the Orca list.

## State machine

`start` creates `state.json` and records:

- temperature/material/brand;
- original PA;
- original max acceleration;
- filament area;
- sensor-test result;
- seven-step plan.

`step` processes exactly one currently pending measurement attempt.

A step can end in:

- **accepted** — advance to next planned measurement;
- **retry** — the same measurement may be attempted once more after another visual check;
- **failed** — second failure; no final APA model is produced.

When all seven measurements are accepted, `finalize` is called automatically.

## Safe state restoration

The underlying `AUTOPA_SWEEP` already restores its original PA, acceleration, gcode state and collector subscription in `finally` blocks.

The production runner adds an outer safety layer after every physical step:

```text
SET_PRESSURE_ADVANCE ADVANCE=<pre-run PA>
M104 S0
```

This is attempted even if analysis or capture handling fails.

## Why no production `AUTOPA_ADAPTIVE_MATRIX`

The research branch contains an experimental real-trajectory 2D measurement method. It is not included here because the stock Q2 data path (~38 SPS) did not provide enough time resolution for stable `PA(real acceleration)` measurements at the target accelerations. See `HISTORY.md` and `LIMITATIONS.md`.
