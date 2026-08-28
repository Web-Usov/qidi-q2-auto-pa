# Installation on QIDI Q2

> This guide describes the **validated Sweep path**, not the experimental `AUTOPA_ADAPTIVE_MATRIX` research module.

The repository is still being cleaned up. Until a packaged release exists, treat installation as a manual integration and keep backups.

## Assumed Q2 paths

The tested machine used:

```text
Klipper source:       /home/mks/klipper
Klipper Python venv:  /home/qidi/klippy-env
Printer config:       /home/mks/printer_data/config/printer.cfg
AutoPA checkout:      /home/mks/autopa
Captures:             /home/mks/printer_data/autopa/captures
```

Confirm paths on your printer before copying anything.

## 1. Back up the working configuration

At minimum, copy `printer.cfg` before editing it.

Also keep a copy of any Klipper extra that you replace or modify.

## 2. Install upstream autopa

Use [`G0BL1N/autopa`](https://github.com/G0BL1N/autopa) as the base calibration engine.

The Q2 work was developed against the upstream 0.2-era code. A future cleaned release of this repository should pin the exact upstream commit; until that is documented, do not blindly assume later upstream versions are patch-compatible.

The web UI is not required for calibration. The printer-side G-code path is sufficient.

## 3. Ensure numpy exists in Klipper's venv

The Sweep analysis requires numpy. On the tested Q2, Klipper uses:

```text
/home/qidi/klippy-env
```

Verify numpy imports in that interpreter before restarting Klipper.

## 4. Install the Q2 load-cell adapter

Copy the reviewed `q2_loadcell.py` into Klipper extras, for example:

```text
/home/mks/klipper/klippy/extras/q2_loadcell.py
```

The adapter does not replace QIDI's `[probe_air]`; it looks up the already-running `probe_air` object and exposes a compatibility `load_cell` object for autopa.

## 5. Add the minimal configuration

Use [`config/q2-autopa.example.cfg`](../config/q2-autopa.example.cfg) as the reference.

Validated values:

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

Do **not** copy `printer.cfg.q2stage` as a replacement printer configuration. It is an archival snapshot of one printer.

## 6. Install the analysis patch

The Q2 campaign found a generic bd-pressure normalization edge case. The required behavior is:

```python
if denom > 0 and np.isfinite(v):
    normalised = v / denom
elif denom == 0.0 and np.isfinite(v):
    normalised = 0.0
else:
    normalised = NaN
```

A cleaned release should provide this as a small patch against a pinned upstream autopa revision. In the current research snapshot, the fixed implementation can be found in the copied `sweep_analysis.py` variants.

## 7. Restart the Klipper service

A normal G-code `RESTART` does not load a newly added Python extra. Restart the Klipper service/process so `q2_loadcell.py` is imported from disk.

After restart, verify Klipper reaches `ready` before proceeding.

## 8. Sensor smoke test

Run the Q2 adapter's no-motion diagnostic:

```text
QPA_SENSOR_TEST TIME=5
```

Expected characteristics on the tested machine:

- roughly 37–38 effective samples/s;
- no read errors;
- non-empty raw data;
- stable stationary tare/noise.

A nominal `samples_per_second: 40` does not guarantee exactly 40 timestamped samples/s.

If the smoke test fails, do not run an extrusion calibration.

## 9. First safe Sweep

Before a new setup is trusted:

- load filament;
- move to a large safe Z clearance;
- heat the nozzle to the filament's working temperature;
- home the selected wobble axis;
- use `APPLY=0`;
- watch the nozzle during the run.

A representative validated PETG command family is:

```text
AUTOPA_SWEEP \
  VFR_LOW=2 VFR=18 \
  TSLOW=1.0 TFAST=0.5 CYCLES=10 \
  KSTART=0.035 KEND=0.075 KSTEP=0.0025 \
  WARMUP=4 PRIME=15 RETRACT=6 \
  WOBBLEAXIS=X WOBBLE=0.10 \
  ACCEL=1000 APPLY=0
```

This is an example, not a universal filament profile.

If the command refuses to run because the composite XY+E leg exceeds `max_extrude_cross_section`, calculate a larger safe WOBBLE. Do not treat increasing the printer's physical extrusion limit as the default solution.

## 10. Validate the result

For a trustworthy capture check:

- `q2_loadcell.errors == 0`;
- actual sample rate is near the validated Q2 range;
- enough segments are included;
- K minimum is not on the search-grid edge;
- bootstrap is concentrated around the nominal optimum;
- the cost valley is physically plausible.

Do not apply a value just because a command printed one.

## Updating

This repository currently contains derived copies from a specific research session rather than a stable update-manager integration. Do not automatically overwrite upstream autopa files from `master` until the runtime tree is cleaned and the exact upstream base revision is pinned.

## Rollback

If anything behaves unexpectedly:

1. stop calibration and turn off the hotend;
2. restore the previous PA value;
3. remove/comment the `[q2_loadcell]` and Q2-specific `[autopa]` additions;
4. restore any modified upstream autopa analysis file from backup or git;
5. remove `q2_loadcell.py` if desired;
6. restore the backed-up `printer.cfg`;
7. restart Klipper.

The QIDI stock `[probe_air]` code is not replaced by this adapter, so removing the adapter should return the printer to the original probing path.
