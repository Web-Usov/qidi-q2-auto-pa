# QIDI Q2 Adaptive PA — production

Production-oriented load-cell calibration workflow for **QIDI Q2** + Orca Slicer.

This branch is intentionally different from `master`:

- `master` is the research/lab snapshot with captures, failed experiments and one-off scripts;
- `production` contains only the runtime, calibration pipeline, documentation and agent skill needed to perform a new calibration safely.

## What this branch produces

A complete calibration run performs physical load-cell measurements and finishes with a ready-to-paste Orca **Adaptive Pressure Advance** list in the form:

```text
PA,volumetric_flow,acceleration
```

The actual output omits the `PA` label, for example:

```text
0.0665,3.91,7200
```

The pipeline also stores the raw capture paths, per-capture bootstrap/QC reports, final model JSON and `orca_adaptive_pa.txt` under `/home/mks/printer_data/autopa/apa-runs/<timestamp>/`.

## Measurement model

The production protocol is based only on the parts of the Q2 research that proved usable:

1. QIDI's stock nozzle force sensor is read through `probe_air` by `runtime/klipper/q2_loadcell.py`.
2. The validated standard `AUTOPA_SWEEP` method measures PA response at several flow conditions.
3. Low/mid flow anchors are measured directly.
4. The high-flow `15.6 mm³/s` anchor is calculated from the validated upper equal-ΔVFR trend because the direct centered high-baseline protocol was not repeatable on the ~38 SPS Q2 sensor path.
5. Three additional standard Sweep measurements at `1800 / 3600 / 7200 mm/s²` provide a **relative empirical acceleration proxy**.
6. The proxy is normalized at 3600 and applied multiplicatively to the flow anchors to produce a calculated 3×3 Orca grid.

This is a calculated APA model from load-cell measurements. It is **not** a claim that the Q2 stock sensor directly measured nine real-print `PA(flow, acceleration)` cells. See [docs/MODEL.md](docs/MODEL.md).

## Safety-first workflow

The production runner is deliberately **stepwise**. Before every extrusion Sweep an operator/agent must inspect the build volume/nozzle and pass `--confirm-clear`. Each physical step:

- requires Klipper `ready`;
- rejects printing/paused state;
- requires detected filament;
- requires AutoPA idle and a working load cell;
- runs a fresh Q2 sensor-rate/error test;
- homes only after the physical-clear confirmation;
- uses `Z=220` and a separate XY dump position;
- runs `AUTOPA_SWEEP` with `APPLY=0`;
- applies deterministic QC and allows at most one retry;
- restores the original PA;
- turns the hotend target to `0` in `finally`.

If any required capture fails twice, **no final APA list is generated**.

Read [docs/SAFETY.md](docs/SAFETY.md) before installation or the first run.

## Install

On the Q2, from a checkout of this `production` branch:

```bash
./install.sh
sudo systemctl restart klipper
/home/qidi/klippy-env/bin/python tools/q2_apa_pipeline.py preflight
```

The installer refuses to continue if the tested QIDI paths are missing, NumPy is unavailable, or `[extruder] max_extrude_cross_section` is below the production protocol requirement. It never silently weakens that Klipper safety guard.

Full instructions: [docs/INSTALL.md](docs/INSTALL.md).

## Run manually

Start a run after physically checking the printer:

```bash
/home/qidi/klippy-env/bin/python tools/q2_apa_pipeline.py start \
  --temperature 245 --material PETG --brand FDPLAST --confirm-clear
```

The command prints the run directory. Before each following step inspect the nozzle/bed again, then run:

```bash
/home/qidi/klippy-env/bin/python tools/q2_apa_pipeline.py step \
  --run /home/mks/printer_data/autopa/apa-runs/<timestamp> --confirm-clear
```

Repeat until the pipeline prints the final Orca list.

See [docs/CALIBRATION.md](docs/CALIBRATION.md).

## Run through an agent

This repository includes:

- [`AGENTS.md`](AGENTS.md) — repository-wide rules;
- [`.agents/skills/qidi-q2-apa/SKILL.md`](.agents/skills/qidi-q2-apa/SKILL.md) — complete Q2 APA operator skill.

With a compatible coding agent opened in this repository, the intended request is simply:

> Сделай тест APA на QIDI Q2 для PETG при 245 °C.

The skill requires camera/visual verification before authorizing motion/extrusion. If the agent cannot inspect the printer, it must stop and request a human visual confirmation instead of running blind.

## Documentation split

### Current implementation

- [INSTALL.md](docs/INSTALL.md) — install/upgrade/rollback
- [IMPLEMENTATION.md](docs/IMPLEMENTATION.md) — runtime architecture and pipeline
- [CALIBRATION.md](docs/CALIBRATION.md) — exact production procedure
- [MODEL.md](docs/MODEL.md) — calculation and QC rules
- [SAFETY.md](docs/SAFETY.md) — mandatory safety gates
- [LIMITATIONS.md](docs/LIMITATIONS.md) — what the result does and does not prove

### Research/history

- [HISTORY.md](docs/HISTORY.md) — the experimental campaign, successful and failed approaches, and evidence that led to the production protocol.

The history document is evidence/provenance. It is not the operator manual.

## Runtime provenance

The Sweep engine is derived from `G0BL1N/autopa` (AGPL-3.0-or-later) with QIDI-Q2-specific integration and the validated constant-zero normalization fix. Algorithmic lineage also includes `CNCKitchen/PrusaPATuner` as credited by upstream AutoPA.

See [CREDITS.md](CREDITS.md) and [LICENSE](LICENSE).
