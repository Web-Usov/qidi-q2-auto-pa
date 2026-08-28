# APA model and quality rules

This document defines the **current production calculation**. It is deliberately separate from `HISTORY.md`, which explains how we arrived here.

## Output target

The production tool builds a 3×3 Orca Adaptive Pressure Advance grid for:

```text
volumetric flow: 3.91 / 7.82 / 15.6 mm³/s
acceleration:    1800 / 3600 / 7200 mm/s²
```

## 1. Flow axis

### Flow 3.91

Measured by standard AutoPA Sweep:

```text
VFR_LOW=1.91
VFR=5.91
ACCEL=1000
```

Production value:

```text
PA_FLOW(3.91) = bootstrap median
```

### Flow 7.82

Measured by:

```text
VFR_LOW=5.82
VFR=9.82
ACCEL=1000
```

Production value:

```text
PA_FLOW(7.82) = bootstrap median
```

### Flow 15.6

The direct centered `13.6→17.6` high-baseline Sweep was clean at the collector level but failed repeatability during the research campaign and contradicted the stable monotonic upper-flow trend. Production therefore does not use that protocol.

Instead it measures two validated equal-step upper-flow points:

```text
6→14   midpoint 10
10→18  midpoint 14
```

and locally extrapolates their `K_opt` values:

```text
slope = (K14 - K10) / (14 - 10)
PA_FLOW(15.6) = K14 + slope * (15.6 - 14)
```

This is intentionally a short local extrapolation (1.6 mm³/s past the last measured midpoint), not a global arbitrary curve fit.

## 2. Acceleration proxy

Three additional standard `AUTOPA_SWEEP` measurements use the same `2→18 mm³/s` flow transition and differ only in Sweep `ACCEL`:

```text
K1800
K3600
K7200
```

The Q2 research established that Sweep `ACCEL` controls the tiny PA-gate wobble and is **not equivalent to a normal printed-line acceleration trajectory**. Therefore these measurements are not treated as direct PA values for Orca acceleration cells.

They are used only as a relative empirical correction:

```text
F1800 = K1800 / K3600
F3600 = 1
F7200 = K7200 / K3600
```

Then:

```text
APA(flow, accel) = PA_FLOW(flow) * Faccel
```

The normalization at 3600 means the acceleration proxy cannot change the absolute scale established by the flow measurements.

This choice is a production engineering model, not a claim of a universal PA law.

## 3. Estimator choices

The protocol intentionally preserves the estimator choices from the validated campaign:

- direct `3.91` and `7.82` anchors: bootstrap median;
- upper-flow extrapolation points `midpoint=10` and `14`: `K_opt`;
- acceleration proxy: `K_opt` ratios.

Changing these choices is a model change and must not be done casually in the agent skill.

## 4. Per-capture quality gates

Every capture is replayed offline with the same `sweep_analysis.py` estimator and bootstrapped 1000 times using a deterministic seed.

Required for a **flow** capture:

```text
capture errors            = 0
actual sample rate         >= 35 Hz
included segment ratio     >= 0.95
K optimum                  not on grid edge
successful bootstrap draws >= 800
|K_opt - bootstrap median| <= 0.0035
bootstrap p5–p95 width     <= 0.012
```

For an acceleration-proxy capture, the final two uncertainty gates are slightly wider because it is used only as a ratio:

```text
|K_opt - bootstrap median| <= 0.0045
bootstrap p5–p95 width     <= 0.015
```

The remaining gates are identical.

A failed capture gets **one** repeat attempt. A second failure aborts the model; no 3×3 output is generated.

## 5. Final sanity gates

Before writing `orca_adaptive_pa.txt`, the calculated grid must satisfy the expected qualitative monotonic directions:

At fixed acceleration:

```text
PA(3.91) >= PA(7.82) >= PA(15.6)
```

At fixed flow:

```text
PA(1800) >= PA(3600) >= PA(7200)
```

If either direction is violated, the program raises an error instead of silently reordering, smoothing or clipping the values.

## 6. No hidden manual correction

The production tool does **not**:

- visually choose a PA line;
- mix in an APA table from another filament;
- clip a high PA because it “looks too large”;
- average a failed anchor into a valid one;
- force a preselected Orca table.

All nine output values are deterministic functions of the accepted current-material captures and the formula above.

## 7. Current-material example from the research campaign

For the PETG campaign that led to this implementation, the accepted/derived flow anchors were approximately:

```text
3.91  -> 0.06935
7.82  -> 0.05725
15.6  -> 0.05053
```

and the acceleration-proxy Sweeps were approximately:

```text
1800 -> 0.06043
3600 -> 0.05553
7200 -> 0.05327
```

Applying the production calculation produced approximately:

```text
0.0665,3.91,7200
0.0549,7.82,7200
0.0485,15.6,7200
0.0694,3.91,3600
0.0573,7.82,3600
0.0505,15.6,3600
0.0755,3.91,1800
0.0623,7.82,1800
0.0550,15.6,1800
```

These numbers are an example/provenance check only. A new filament run must calculate its own values.
