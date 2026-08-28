# Credits and provenance

## G0BL1N/autopa

This project is a QIDI Q2 adaptation of [`G0BL1N/autopa`](https://github.com/G0BL1N/autopa), an automatic Pressure Advance calibration system for Klipper driven by a toolhead load cell.

The following parts in this repository are derived from or closely track upstream autopa code and concepts:

- the `AUTOPA_SWEEP` command and motion protocol;
- capture persistence/schema concepts;
- the bd-pressure step-response analysis;
- profile/capture plumbing present in copied upstream modules;
- the normalisation/cost framework used by the offline tools.

Upstream autopa is released under **GNU AGPL-3.0-or-later**. Derived source files in this repository retain AGPL notices and must continue to comply with that license.

## CNCKitchen / PrusaPATuner

Upstream autopa's Sweep method documents its algorithmic lineage to [`CNCKitchen/PrusaPATuner`](https://github.com/CNCKitchen/PrusaPATuner). The copied/derived Sweep source in this repository preserves that attribution in file headers.

## QIDI Q2 adaptation

The Q2-specific work in this repository includes:

- `q2_loadcell.py`, which adapts QIDI's stock `probe_air` sensor path to the load-cell interface expected by autopa;
- lower-rate Sweep quality gates validated against the Q2's ~37–38 SPS effective stream;
- Q2-specific safety/wobble validation;
- the constant-zero cost-normalisation fix discovered during Q2 replay analysis;
- diagnostic and offline replay scripts;
- the real-motion Adaptive PA experiments and their negative-result documentation.

## QIDI firmware

QIDI's stock `probe_air` implementation and the underlying firmware are not part of this repository. The adapter intentionally calls the existing public-at-runtime Python object exposed by the installed QIDI Klipper fork and does not copy or redistribute QIDI firmware code.

## Research provenance

The raw `.npz` captures and camera snapshots committed to the research snapshot are measurements from the QIDI Q2 used during the August 2026 validation campaign. They are kept as evidence for reproducibility and estimator review; they are not required by the runtime integration.

## AI-assisted development

A substantial portion of the investigation, code iteration, offline analysis, and documentation was produced with AI coding assistants under human direction and validated against physical printer runs. Experimental conclusions in the documentation are based on the recorded captures/results, not on model output alone.
