# Credits and provenance

## G0BL1N/autopa

This project is a QIDI Q2 adaptation of [`G0BL1N/autopa`](https://github.com/G0BL1N/autopa), an automatic Pressure Advance calibration system for Klipper driven by a toolhead load cell.

The production runtime derives from / closely tracks upstream AutoPA concepts and code, including:

- the `AUTOPA_SWEEP` command and motion protocol;
- capture persistence/schema concepts;
- the bd-pressure step-response estimator;
- the normalization/cost framework used by offline replay.

Upstream AutoPA is released under **GNU AGPL-3.0-or-later**. Derived files retain upstream notices and this repository is distributed under the same license terms.

## CNCKitchen / PrusaPATuner

Upstream AutoPA documents Sweep's algorithmic lineage to [`CNCKitchen/PrusaPATuner`](https://github.com/CNCKitchen/PrusaPATuner). The production `sweep_analysis.py` keeps that attribution in its source header.

## QIDI Q2 adaptation

Q2-specific work includes:

- `runtime/klipper/q2_loadcell.py`, adapting QIDI's stock `probe_air` path to the load-cell subset required by AutoPA;
- Q2-specific lower-rate quality gates for the measured ~37–38 SPS stream;
- Q2-specific in-air wobble/safety validation;
- the constant-zero cost-normalization fix found during Q2 capture replay;
- the deterministic flow/acceleration-proxy APA model;
- the safe stepwise physical calibration pipeline;
- negative-result research documenting why direct real-trajectory 2D APA was not accepted on the stock sensor path.

## QIDI firmware

QIDI's stock `probe_air` implementation and firmware are not copied into this repository. The adapter calls the existing runtime Python object exposed by the installed QIDI Klipper fork.

## Research provenance

Raw captures, camera snapshots, failed experiments and one-off scripts remain on the `master` research branch. The `production` branch intentionally contains only the operational package plus `docs/HISTORY.md` as an evidence summary.

## AI-assisted development

A substantial part of the investigation, code iteration, analysis and documentation was produced with AI coding assistants under human direction and checked against physical QIDI Q2 runs. Experimental conclusions are based on recorded printer captures/results rather than model output alone.
