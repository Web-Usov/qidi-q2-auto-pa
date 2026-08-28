---
name: qidi-q2-apa
description: Safely install, run, validate, and report the production load-cell Adaptive Pressure Advance calibration workflow on a QIDI Q2. Use when the user asks to run/test/calibrate APA, Adaptive PA, or a PA flow/acceleration matrix on QIDI Q2.
---

# QIDI Q2 APA operator skill

Use the repository's **production pipeline**. Do not recreate the research workflow from memory.

## Goal

Starting from the currently loaded filament, perform the full physical Q2 load-cell calibration, quality-control every capture, calculate the material-specific 3×3 model, and return the exact Orca-ready list plus result artifact paths.

## Required inputs

Resolve before physical calibration:

- filament material (for example `PETG`);
- calibration/printing temperature in °C;
- optional brand/name;
- SSH host for the QIDI Q2.

Do not guess material or temperature. If they are not available from the user's current request/context/profile, ask.

Resolve the host in this order:

1. environment variable `QIDI_HOST`;
2. repository-local `.qidi-host` if present (do not commit it);
3. an existing SSH config alias clearly pointing to the QIDI printer;
4. otherwise ask the user once.

Default SSH user for the validated Q2 is `mks` unless the user's SSH configuration provides another user.

## Read first

Before touching the printer, read:

```text
docs/SAFETY.md
docs/CALIBRATION.md
docs/MODEL.md
```

For implementation troubleshooting also read `docs/IMPLEMENTATION.md`.

## Phase 1 — connectivity and current printer state

1. Confirm the local repository is on `production` or contains the production files from that branch.
2. SSH to the Q2.
3. Verify these paths exist:

```text
/home/mks/klipper
/home/qidi/klippy-env/bin/python
/home/mks/printer_data/config/printer.cfg
```

4. Verify Moonraker responds locally on the printer.
5. Check the printer is not printing or paused before any installation/restart/calibration.

If connectivity or state cannot be verified, stop.

## Phase 2 — sync and runtime verification

Preferred deployment directory on Q2:

```text
/home/mks/q2-apa-production
```

Sync the current production working tree from the agent machine using `rsync` or `scp`; do not depend on GitHub being reachable from the printer.

Example:

```bash
rsync -az --delete --exclude .git ./ mks@${QIDI_HOST}:/home/mks/q2-apa-production/
```

First try the production preflight remotely:

```bash
cd /home/mks/q2-apa-production
/home/qidi/klippy-env/bin/python tools/q2_apa_pipeline.py preflight
```

If the runtime is missing/incompatible, install it:

```bash
cd /home/mks/q2-apa-production
chmod +x install.sh
./install.sh
sudo systemctl restart klipper
```

Wait until Klipper is `ready`, then run `preflight` again.

Never edit `max_extrude_cross_section` automatically if `install.sh` rejects it. Report the requirement and stop so a human can make the deliberate safety-setting change described in `docs/SAFETY.md`.

## Phase 3 — visual safety check

Before `start` and before **every** `step`, obtain a current camera image if camera access is available.

Try the printer's configured camera source/known Moonraker webcam first. Common snapshot paths may include:

```text
http://<QIDI_HOST>/webcam/?action=snapshot
http://<QIDI_HOST>/webcam?action=snapshot
```

Do not assume a URL works; verify the returned file is an actual current image.

Inspect for:

- clear build/motion volume;
- no object/tool/hand in the way;
- no large filament mass already wrapped around the nozzle/heater block;
- enough space around the current high-Z extrusion pile.

Only after this real check may you add `--confirm-clear`.

If you cannot obtain/inspect a current image, ask the user to visually confirm the printer is clear. Do not run blind.

## Phase 4 — start calibration

Run remotely:

```bash
cd /home/mks/q2-apa-production
/home/qidi/klippy-env/bin/python tools/q2_apa_pipeline.py start \
  --temperature <TEMP> \
  --material <MATERIAL> \
  --brand '<BRAND>' \
  --confirm-clear
```

Capture the printed `RUN=/home/mks/printer_data/autopa/apa-runs/<timestamp>` value exactly.

The start command performs homing/high-Z positioning and a 5-second sensor test but does not run the seven hot Sweep measurements.

## Phase 5 — measurement loop

Repeat until the run is complete or failed:

1. Perform a fresh camera/visual check.
2. If safe, run exactly one step:

```bash
cd /home/mks/q2-apa-production
/home/qidi/klippy-env/bin/python tools/q2_apa_pipeline.py step \
  --run '<RUN>' \
  --confirm-clear
```

3. Read the output.

If it says `ACCEPTED`, continue after another visual check.

If it says `RETRY REQUIRED`, do not immediately repeat. Inspect the nozzle/bed again, then run the same step command once. The state file ensures this is the second and final attempt.

If it says `FAILED`, stop. Do not create/guess/average an APA table.

After each step, the production runner attempts to restore the original PA and set hotend target to zero. Still verify the printer state if anything unusual happened.

## Phase 6 — final result

The seventh accepted step automatically finalizes the model.

Read:

```text
<RUN>/orca_adaptive_pa.txt
<RUN>/result.json
<RUN>/state.json
```

Report to the user:

- the exact nine-line Orca block from `orca_adaptive_pa.txt`;
- the general-PA fallback printed/stored by the model;
- the bridge-PA starting value printed/stored by the model;
- run directory;
- whether any steps required retry;
- any limitations/warnings recorded in `result.json`.

Do not re-round or recalculate the Orca values yourself; return the file output.

If the user explicitly asks you to edit a local Orca filament profile and you can identify the exact intended profile unambiguously, you may apply the generated block. Otherwise provide the paste-ready result and do not guess which Orca profile to change.

## Phase 7 — final safety verification

Before declaring success, verify via Moonraker/printer state that:

```text
Klipper = ready
AutoPA activity = idle
hotend target = 0
```

Also verify current PA equals the value recorded as `original_pa` in `<RUN>/state.json`.

If those checks fail, run the pipeline's abort/safe-shutdown path where applicable and report the failure instead of claiming completion.

## On error or interruption

Between steps, abort with:

```bash
/home/qidi/klippy-env/bin/python tools/q2_apa_pipeline.py abort --run '<RUN>'
```

If there is an immediate physical hazard during active motion/extrusion, use the printer's emergency-stop mechanism instead.

## Forbidden shortcuts

Never:

- use APA values from another filament as the result;
- visually pick PA by eye;
- replace a rejected capture with a hand-entered number;
- use the research real-motion `AUTOPA_ADAPTIVE_MATRIX` path;
- reinterpret tiny-wobble Sweep `ACCEL` as nine directly measured real-print cells;
- bypass capture QC or monotonicity checks;
- silently change the model formula/thresholds;
- pass `--confirm-clear` without a current visual check.

## Expected user-level invocation

When the user says something like:

> Сделай тест APA на QIDI Q2 для PETG при 245 °C

perform this skill end-to-end. Only ask for genuinely missing material/temperature/host information or a required human visual confirmation when camera inspection is unavailable.
