# Code review notes

Review target: research snapshot through commit `ff757e82d6dd2913fcf5bd5645b18bc7f5a4b9bb`.

This document distinguishes **runtime concerns** from **repository-packaging concerns**. The research snapshot is valuable evidence, but it is not yet shaped like a releasable project.

## High priority

### 1. Separate production runtime from archived experiments

The current root mixes:

- active runtime copies;
- duplicate copies of the same autopa modules;
- before/after patch files;
- experimental `adaptive_matrix.py`;
- offline scripts;
- captures;
- camera images;
- full printer config.

Recommended cleanup:

```text
runtime/
  q2_loadcell.py
  autopa-patches/
research/
  adaptive-matrix/
  scripts/
  captures/
  images/
docs/
config/
  q2-autopa.example.cfg
```

Do not delete the research evidence; move it under an explicit archive/research path.

### 2. Pick one canonical autopa code representation

The snapshot currently includes several overlapping copies such as:

- `autopa_init.py`
- `__init__.py.remote`
- `autopa_sweep.py`
- `qidi_sweep.py`
- `qidi_sweep_latest.py`
- `autopa_sweep_analysis.py`
- `printer_sweep_analysis_current.py`
- `sweep_analysis.py.after.patch`
- `sweep_analysis.py.before.patch`
- `autopa_local/sweep_analysis.py`

For a release, users need one clear answer to: **which files do I install?**

Recommended approach: keep the upstream autopa repository as a dependency/reference and publish a small patch set plus the Q2 compatibility extra, or vendor one clearly identified derived tree. Avoid multiple root-level copies.

### 3. Add full AGPL license and upstream notices

The derived autopa files already carry AGPL headers, but the repository needs a top-level `LICENSE` and preserved attribution before a release is advertised.

### 4. Do not ship `adaptive_matrix.py` as a normal feature

The real-motion matrix estimator is intentionally experimental and failed the validation criterion. Keep it under `research/` or gate it clearly as unsupported.

The normal recommended path should remain `AUTOPA_SWEEP`.

## Runtime review

### `q2_loadcell.py`

The compatibility approach is sound for the tested Q2:

- it does not replace `[probe_air]`;
- it resolves QIDI's existing `sensor_helper`;
- it timestamps in MCU print time;
- it provides per-acquisition tare;
- it only registers the conventional `load_cell` name if one is absent.

Recommended improvements before release:

1. **Clarify nominal versus actual SPS.** `configured_sps` is compatibility metadata, while the actual capture rate is lower. Document this prominently.
2. **Avoid overclaiming ADC internals.** The source comment that `CS1237 config 0x3c selects 1280Hz conversion` should be independently verified or softened. The adapter itself does not need this claim to work.
3. **Expose clearer health telemetry.** Keep `poll_calls`, `new_readings`, `duplicate_reads`, and `read_errors`; they were useful during validation.
4. **Document synchronous-query cost.** `read_origin_data()` is a synchronous QIDI command path. Keep polling conservative and avoid presenting `poll_hz` as freely scalable.

### Sweep Q2 thresholds

The added configuration knobs for minimum segment sample count/rate are a good compatibility improvement because they preserve upstream defaults while allowing Q2-specific overrides.

Validated Q2 values:

```ini
sweep_min_segment_samples: 12
sweep_min_segment_rate_hz: 35
```

### Constant-zero normalization patch

The patch in `_bd_compute_normalised()` is technically well-motivated:

```python
elif denom == 0.0 and np.isfinite(v):
    r.normalised[name] = 0.0
```

This fixes the case where a metric is finite and identically zero across the whole K grid. It should be proposed upstream separately because it is not Q2-specific.

### Sweep guard wording

The current guard message suggests adding a larger `max_extrude_cross_section` **or** raising WOBBLE. For Q2 documentation, prefer raising/calculating WOBBLE and preserving printer safety limits. The runtime error text can remain general, but the README should not recommend increasing physical limits as the default fix.

## Research-method review

### Standard Sweep acceleration experiments

The repository preserves acceleration-labelled tiny-wobble sweeps. Documentation must state that they are diagnostic only and are not measurements of normal print acceleration dependence.

### Real-motion matrix

The implementation correctly attempted to address obvious confounders:

- true composite XY+E moves;
- real `SET_VELOCITY_LIMIT ACCEL` values;
- dry mechanical reference;
- direction-specific subtraction;
- bootstrap analysis;
- fixed-grid validation.

The method was stopped for the right reason: the first validation cell did not produce a concentrated bootstrap distribution, and subsequent phase-fold analysis remained unstable.

This negative result is worth preserving as documentation, not hiding.

## Repository data hygiene

### Captures

The many `.npz` files are useful research evidence but make the root difficult to navigate. Move them under `research/captures/` and add an index CSV/Markdown with:

- filename;
- test purpose;
- valid/invalid status;
- flow range;
- acceleration argument;
- wobble;
- K grid;
- K result;
- notes.

### Images

Move camera snapshots under `research/images/` and keep only images that establish a meaningful state (nozzle clear, blob failure, pre/post run).

### Full printer config

Move `printer.cfg.q2stage` to `research/config-snapshots/` and add a warning header. Create a separate minimal example containing only `[q2_loadcell]` and `[autopa]` settings.

## Missing release pieces

Before calling this installable, add:

- `LICENSE`
- `CREDITS.md`
- minimal config example
- installation instructions for copying/symlinking `q2_loadcell.py`
- precise upstream autopa revision this snapshot was based on
- rollback/uninstall instructions
- a smoke-test procedure using `QPA_SENSOR_TEST`
- an example `AUTOPA_SWEEP ... APPLY=0` command

## Suggested release boundary

A first useful release does **not** need the failed Adaptive Matrix feature.

A clean v0.1-Q2 release can be only:

1. Q2 load-cell compatibility adapter;
2. Q2 threshold/config instructions;
3. constant-zero normalization patch (or upstream dependency containing it);
4. validated Sweep workflow;
5. offline analysis helpers;
6. documented limitations.
