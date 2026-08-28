# Production calibration procedure

This is the operator procedure for generating a new Orca Adaptive PA model on a QIDI Q2. For implementation details see `IMPLEMENTATION.md`; for research history see `HISTORY.md`.

## Before starting

The calibration is material- and temperature-specific. Load the exact filament you want to calibrate and choose its actual printing temperature.

Expected filament consumption for 1.75 mm filament is about **8.1 m (~20 cm³, roughly 25 g of PETG)** when all seven captures pass on the first attempt. A failed quality gate can add one repeat of that particular Sweep.

Mandatory conditions:

- build volume visibly clear;
- nozzle visually clean enough that an in-air extrusion pile cannot immediately climb back onto the heater block;
- filament detected;
- Klipper `ready`;
- no active or paused print;
- production runtime installed;
- `[extruder] max_extrude_cross_section` satisfies `docs/SAFETY.md`;
- enough filament remains for the run.

## 1. Preflight

```bash
/home/qidi/klippy-env/bin/python tools/q2_apa_pipeline.py preflight
```

Do not continue if this command fails.

## 2. Start the run

After a fresh camera/visual check:

```bash
/home/qidi/klippy-env/bin/python tools/q2_apa_pipeline.py start \
  --temperature 245 \
  --material PETG \
  --brand FDPLAST \
  --confirm-clear
```

Replace the temperature/material/brand with the filament being calibrated.

`start`:

1. performs the software preflight;
2. homes only after `--confirm-clear`;
3. moves to the high-Z calibration area;
4. performs a five-second Q2 load-cell transport test;
5. records original PA and printer state;
6. creates a timestamped run directory.

It does **not** heat/extrude the seven test Sweeps yet.

The command prints a path such as:

```text
RUN=/home/mks/printer_data/autopa/apa-runs/20260828-190000
```

## 3. Run each measurement step

Before every step, inspect the camera/physical printer again. Remove old hanging filament/piles only when it is safe to do so; never send the nozzle down to wipe itself against the bed.

Then run:

```bash
/home/qidi/klippy-env/bin/python tools/q2_apa_pipeline.py step \
  --run /home/mks/printer_data/autopa/apa-runs/20260828-190000 \
  --confirm-clear
```

One `step` command performs exactly one measurement attempt. It:

1. re-checks printer state and filament;
2. re-homes if Klipper lost homing state;
3. moves to a separate XY dump location at `Z=220`;
4. runs a fresh sensor test;
5. heats to the run temperature and holds briefly;
6. executes one `AUTOPA_SWEEP` with `APPLY=0`;
7. analyzes the new capture with bootstrap/QC;
8. restores the original PA;
9. sets hotend target to `0`.

If accepted, the next invocation advances to the next planned measurement.

If QC says `RETRY REQUIRED`, visually inspect the printer again and run the same command once more. The pipeline will not allow more than two attempts for one planned measurement.

If the second attempt fails, the run becomes `failed` and the program intentionally refuses to create an APA list.

## 4. Check status at any time

```bash
/home/qidi/klippy-env/bin/python tools/q2_apa_pipeline.py status \
  --run /home/mks/printer_data/autopa/apa-runs/20260828-190000
```

## 5. Final result

After the seventh accepted measurement, the final step automatically calls the model builder and prints:

```text
ORCA ADAPTIVE PA
----------------
0.xxxx,3.91,7200
0.xxxx,7.82,7200
0.xxxx,15.6,7200
0.xxxx,3.91,3600
0.xxxx,7.82,3600
0.xxxx,15.6,3600
0.xxxx,3.91,1800
0.xxxx,7.82,1800
0.xxxx,15.6,1800
```

The same text is saved as:

```text
<run-dir>/orca_adaptive_pa.txt
```

Full provenance and statistics are saved in:

```text
<run-dir>/result.json
<run-dir>/*_attempt*.json
<run-dir>/state.json
```

Copy only `orca_adaptive_pa.txt` into Orca's Adaptive PA range field.

The runner also prints a general-PA fallback and a bridge-PA starting value. These are convenience outputs; the core calibrated artifact is the Adaptive PA list.

## Abort

If you need to stop between steps:

```bash
/home/qidi/klippy-env/bin/python tools/q2_apa_pipeline.py abort \
  --run /home/mks/printer_data/autopa/apa-runs/20260828-190000
```

This requests PA restoration and `M104 S0`, then marks the run aborted.

If there is an immediate physical hazard while the printer is moving/extruding, use the printer's normal emergency-stop mechanism instead of waiting for the pipeline.
