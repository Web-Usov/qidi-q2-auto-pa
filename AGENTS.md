# Agent rules — QIDI Q2 APA production

This repository controls a physical 3D printer. Treat calibration commands as hardware operations.

## Primary skill

When the user asks to calibrate/test/run Adaptive Pressure Advance / APA / PA matrix on a **QIDI Q2**, read and follow:

```text
.agents/skills/qidi-q2-apa/SKILL.md
```

Do not invent a separate calibration workflow when that skill applies.

## Hard rules

1. Never run physical motion/heating/extrusion blind.
2. `--confirm-clear` may be passed only after a current camera/physical check.
3. If no current image can be inspected, ask the human to confirm the printer is clear before continuing.
4. Never run while `print_stats.state` is `printing` or `paused`.
5. Never disable or bypass the pipeline's sensor/QC checks.
6. Never increase `max_extrude_cross_section` automatically. Installation may only proceed when the operator has deliberately configured an acceptable value after reading `docs/SAFETY.md`.
7. Never substitute PA/APA values from another filament or brand.
8. Never use the research `AUTOPA_ADAPTIVE_MATRIX`/real-trajectory experiment as production calibration.
9. Never visually pick a PA value “by eye” for this workflow.
10. If a capture fails the production quality gate twice, stop. Do not average or force a final table.
11. Always verify hotend target is 0 and AutoPA is idle after completion/abort.
12. Preserve the user's original Pressure Advance; production Sweeps use `APPLY=0`.

## Repository branches

- `production` — operational runtime, tools, docs and agent skill.
- `master` — research evidence/history; do not deploy it wholesale to a printer.

Do not copy `printer.cfg` snapshots or experimental Python files from `master` into production runtime.

## Canonical runtime paths on validated QIDI Q2

```text
/home/mks/klipper
/home/qidi/klippy-env
/home/mks/printer_data/config/printer.cfg
/home/mks/printer_data/autopa/captures
/home/mks/printer_data/autopa/apa-runs
```

## Model integrity

The production 3×3 model is defined only in `docs/MODEL.md` and `tools/q2_apa_analysis.py`.

Do not silently change:

- flow targets;
- Sweep timing/grid;
- bootstrap/QC thresholds;
- high-flow extrapolation formula;
- acceleration-proxy normalization;
- monotonicity checks.

A change to those is an algorithm change and requires explicit review plus new validation evidence.
