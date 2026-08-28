# Repository layout

The current `master` is an intentional research dump. For a usable public project, separate what users install from what documents the R&D process.

## Proposed layout

```text
qidi-q2-auto-pa/
├── README.md
├── LICENSE
├── CREDITS.md
├── config/
│   └── q2-autopa.example.cfg
├── runtime/
│   ├── q2_loadcell.py
│   └── autopa-patches/
│       └── 0001-constant-zero-normalisation.patch
├── tools/
│   ├── analyse_capture.py
│   └── final_flow_analysis.py
├── docs/
│   ├── ARCHITECTURE.md
│   ├── EXPERIMENTS.md
│   ├── LIMITATIONS.md
│   ├── CODE_REVIEW.md
│   └── INSTALL.md
└── research/
    ├── adaptive-matrix/
    │   ├── adaptive_matrix.py
    │   ├── phase_fold_adaptive_offline.py
    │   └── reports/
    ├── captures/
    │   ├── README.md
    │   └── *.npz
    ├── images/
    └── config-snapshots/
        └── printer.cfg.q2stage
```

## Runtime boundary

A user who only wants working Q2 AutoPA should need very little:

- `q2_loadcell.py` installed into Klipper extras;
- upstream autopa at a known revision;
- the small analysis normalization patch if not yet upstream;
- the two Q2 config sections;
- numpy in Klipper's venv.

Everything else is optional evidence/tooling.

## Research boundary

The following belong under `research/`, not in the normal installation path:

- `adaptive_matrix.py` and its replay scripts;
- phase-fold reconstruction experiments;
- before/after estimator copies;
- invalid captures;
- camera snapshots;
- the full QIDI `printer.cfg` snapshot;
- one-off inspection scripts.

## Capture index

Instead of leaving dozens of `.npz` files unexplained, add a small index such as:

```csv
file,status,purpose,vfr_low,vfr_high,wobble,k_opt,notes
capture_20260827-150617.npz,valid,fine base validation,2,18,0.05,0.054045,normalisation bug replayed
capture_20260828-120949.npz,invalid,real-motion APA validation,,,,0.047613,broad bootstrap
```

This makes the raw evidence useful to other contributors.

## Why not rewrite history now

The existing snapshot is valuable because it records exactly what was tested. Cleanup should happen as a new commit/PR that moves files, rather than deleting the research trail before the final flow-anchor campaign is complete.
