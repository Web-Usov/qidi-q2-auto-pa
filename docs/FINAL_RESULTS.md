# Final calibration result

This document records the final practical calibration model produced by the QIDI Q2 AutoPA research campaign.

## Provenance

The final Orca Adaptive PA table is **hybrid**:

- the absolute PA-vs-flow baseline comes from Q2 load-cell AutoPA experiments;
- the acceleration correction comes from an earlier manual 3×3 Adaptive PA calibration;
- the stock Q2 load cell did **not** directly measure the acceleration axis reliably.

This distinction is important. The result below is useful and internally consistent, but it must not be described as a fully automatic 3×3 acceleration calibration.

## Final flow anchors

Target Orca flows:

```text
3.91
7.82
15.6 mm³/s
```

Accepted anchors:

| Flow | Source | PA_FLOW |
|---:|---|---:|
| 3.91 | direct final AutoPA Sweep, bootstrap median | 0.06935 |
| 7.82 | direct final AutoPA Sweep, bootstrap median | 0.05725 |
| 15.6 | offline extrapolation from validated equal-step flow series | 0.05053 |

### Why 15.6 is extrapolated

The direct centered `13.6→17.6` high-baseline protocol produced technically clean captures but did not behave as a trustworthy direct anchor:

- run 1: `K_opt=0.06056`, bootstrap median `0.05730`;
- run 2: `K_opt=0.06251`, bootstrap median `0.06149`;
- bootstrap medians differed by `0.00419`, exceeding the pre-declared `0.003` repeatability criterion;
- both results also conflicted with the previously validated monotonic decrease of K with increasing absolute flow level.

Those captures are retained as evidence of a high-baseline protocol limitation, not used in the final flow model.

The accepted high-flow anchor is therefore obtained from the validated equal-step (`ΔVFR=8`) series:

| Midpoint flow | K_opt |
|---:|---:|
| 6 | 0.060011 |
| 10 | 0.055150 |
| 14 | 0.051851 |

Local linear extrapolation of the upper `10→14` segment to `15.6` gives:

```text
slope = (0.051851 - 0.055150) / 4
      = -0.00082475 K / (mm³/s)

K(15.6) = 0.051851 + slope * 1.6
        = 0.0505314
```

A linear least-squares fit over midpoint `6/10/14` gives about `0.04996`; a robust three-point fit lands around `0.0502`. The selected anchor is therefore:

```text
PA_FLOW_15.6 = 0.05053
```

with a practical uncertainty band of approximately:

```text
0.0485 .. 0.0525
```

## Acceleration correction

The earlier manual Adaptive PA matrix was:

| Flow ≈ | PA @ 1800 | PA @ 3600 | PA @ 7200 |
|---:|---:|---:|---:|
| 3.86 | 0.080 | 0.050 | 0.040 |
| 7.71 | 0.065 | 0.045 | 0.038 |
| 15.4 | 0.050 | 0.040 | 0.035 |

`3600 mm/s²` is used as the reference acceleration. Only the **relative correction** is carried forward:

| Final flow | ΔPA @ 1800 | ΔPA @ 3600 | ΔPA @ 7200 |
|---:|---:|---:|---:|
| 3.91 | +0.030 | 0.000 | -0.010 |
| 7.82 | +0.020 | 0.000 | -0.007 |
| 15.6 | +0.010 | 0.000 | -0.005 |

No additional regression or smoothing is applied.

## Final 3×3 APA table

Using the final flow anchors as the `3600` reference row:

| Flow | PA @ 1800 | PA @ 3600 | PA @ 7200 |
|---:|---:|---:|---:|
| 3.91 | 0.09935 | 0.06935 | 0.05935 |
| 7.82 | 0.07725 | 0.05725 | 0.05025 |
| 15.6 | 0.06053 | 0.05053 | 0.04553 |

Sanity checks pass:

- for each flow: `PA(1800) > PA(3600) > PA(7200)`;
- for each acceleration: `PA(3.91) > PA(7.82) > PA(15.6)`.

The `3.91 / 1800` value is high (`~0.099`), but this follows directly from the previously measured `+0.030` acceleration correction applied to the newer absolute flow anchor. It is not clipped or manually adjusted.

## Orca Slicer block

Using the full-precision model values:

```text
0.05935,3.91,7200
0.05025,7.82,7200
0.04553,15.6,7200
0.06935,3.91,3600
0.05725,7.82,3600
0.05053,15.6,3600
0.09935,3.91,1800
0.07725,7.82,1800
0.06053,15.6,1800
```

Rounded to four decimal places using the underlying unrounded anchors where available:

```text
0.0593,3.91,7200
0.0502,7.82,7200
0.0455,15.6,7200
0.0693,3.91,3600
0.0572,7.82,3600
0.0505,15.6,3600
0.0993,3.91,1800
0.0772,7.82,1800
0.0605,15.6,1800
```

## Interpretation

This final table should be described as:

> QIDI Q2 AutoPA flow calibration combined with an independently measured manual acceleration correction.

It should **not** be described as:

> nine acceleration/flow cells directly measured automatically by the stock Q2 load cell.

The attempted direct real-trajectory acceleration estimator was explicitly rejected because the stock sensor path delivers only ~37–38 SPS and did not produce a stable acceleration-dependent optimum.
