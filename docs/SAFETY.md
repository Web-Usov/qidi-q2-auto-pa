# Safety requirements

This calibration deliberately heats the nozzle and extrudes filament **in open air**. Treat it as a physical machine operation, not as a harmless analysis script.

## Mandatory preconditions

Do not authorize a physical step unless all of the following are true:

- the printer/camera view has been checked immediately before the step;
- there is no printed object, tool, hand or loose object in the movement volume;
- the nozzle/heater block is not carrying a large PETG blob;
- filament is actually loaded and the Q2 filament sensor reports it;
- Klipper is `ready`;
- no print is active or paused;
- AutoPA is `idle`;
- the load-cell adapter is available;
- a fresh `QPA_SENSOR_TEST` has zero new read errors and a conservative effective rate of at least 35 Hz.

The pipeline requires `--confirm-clear` before any command that may home or extrude. That flag means a real visual check has just happened. It must never be added automatically without such a check.

## High-Z / dump positions

Production uses `Z=220` and separate XY positions for the seven Sweeps:

```text
X200 Y140
X175 Y140
X150 Y140
X125 Y140
X100 Y140
X75  Y140
X50  Y140
```

These locations were selected for the Q2 work envelope and keep successive filament piles separated.

No production code drives the hot nozzle down to the bed to wipe or detach an extrusion blob.

## Blob/curl abort rule

In-air PETG can curl upward and stick to the nozzle. If a pile starts climbing toward the heater block, **do not start the next step**. Remove it safely only after motion has stopped and the hardware is in a safe state.

If an immediate hazard develops while the printer is moving/extruding, use the printer's normal emergency-stop mechanism.

## Klipper `max_extrude_cross_section`

The AutoPA Sweep must use a tiny X/Y wobble because Klipper applies Pressure Advance only to composite X/Y+E moves in this tested path. Such moves look like an enormous printed cross-section to Klipper's normal extrusion guard.

The validated production protocol uses:

```text
WOBBLE=0.14
```

and requires:

```ini
[extruder]
max_extrude_cross_section: 320   # or higher
```

The research printer currently used a still higher value. `320` is the production minimum for the defined VFR/timing grid with margin.

**This setting weakens a real Klipper safety check globally.** For that reason:

- `install.sh` never edits it automatically;
- the installer refuses to proceed if it is missing or below 320;
- only trusted G-code should be run on a printer configured this way;
- do not interpret `MAXFILAMENT` as a replacement for this guard.

If you are not comfortable changing this protection, do not install/run this calibration protocol.

## Filament budget

The pipeline computes expected filament use for each Sweep from the live filament area, adds 10%, and passes that value as `MAXFILAMENT`.

It also has a hard cap of **2500 mm filament per single Sweep**. If a requested measurement would exceed that, it aborts before extrusion.

## Pressure Advance safety

Every Sweep is run with:

```text
APPLY=0
```

The Sweep runtime already restores the original PA and acceleration in `finally`.

The outer pipeline also records pre-run PA and requests:

```text
SET_PRESSURE_ADVANCE ADVANCE=<original>
M104 S0
```

after every physical step, including failure paths.

## Heater policy

The stepwise workflow intentionally turns the hotend target off after each measurement. This is slower than keeping a nozzle at calibration temperature for an unattended batch, but gives a safe state if the agent/operator stops between steps.

The next step reheats and holds briefly before measurement.

## Retries

A quality failure is not permission to immediately extrude again blindly.

Production behaviour:

1. first bad capture -> `retry` state;
2. camera/visual inspection is required again;
3. exactly one repeat is allowed;
4. second failure -> run `failed`, no APA output.

## Camera unavailable

An agent must not infer that the printer is physically clear from software status alone. If it cannot obtain/inspect a current camera image, it must ask the human operator to confirm the build volume/nozzle before passing `--confirm-clear`.
