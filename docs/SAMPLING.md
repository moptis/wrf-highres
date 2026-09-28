# Representative-period sampling — algorithm and results

Built from ERA5 alone, independent of any existing TMY or WRF run.

## Framing

Choosing which periods to simulate is a **quadrature problem**: pick nodes
(blocks) and weights so the weighted empirical distribution approximates the
climate. Two consequences follow immediately, and both were being left on the
table before:

* **weights are free** — the WRG is a weighted histogram either way, so nothing
  forces equal weighting of the sampled hours;
* **the objective should be a distance between measures**, evaluated on the
  variables that condition the downscaling.

## Data

`extract_forcing.py` pulls a site timeseries straight from the local WPS
intermediate files — no new downloads. 3-hourly, 1999-2025, 75 488 files, ~5
minutes on 64 cores (the reader seeks past unwanted slabs, 0.004 s/file instead
of 0.07 s).

| source | variables |
|--------|-----------|
| `ERA5_SURF` (local) | `SKINTEMP`, `TT` (2 m), `UU`/`VV` (10 m), `PSFC`, `SNOW` |
| `era5.csv` (hourly) | 100 m wind speed and direction |

Stability is a bulk Richardson number from the skin-to-air temperature
difference and the 10 m wind:

```
Ri_B = -g z (T_skin - T_2m) / (T_2m U10^2),   z = 10 m
```

binned on neutrality rather than quantiles, so the classes mean the same thing
at any site. The result is physically coherent, which is the check that matters:

| class | share | mean ws | mean dT |
|-------|-------|---------|---------|
| v.unstable | 17.7% | 3.97 | +12.03 K |
| unstable | 23.8% | 8.51 | +5.41 K |
| neutral | 14.9% | 10.88 | -0.05 K |
| stable | 34.8% | 8.71 | -2.46 K |
| v.stable | 8.8% | 4.07 | -3.47 K |

Neutral carries the strongest winds (mechanical mixing), 11:00 local is 54%
very unstable, 02:00 local is 86% stable or very stable, DJF is 45% stable and
JJA 34% very unstable.

## Objective

Matching marginals is not enough: the terrain response is conditioned on
direction, speed and stability **jointly** — stable southwesterly flow over a
mesa behaves nothing like unstable southwesterly flow. But the full 3-way joint
(12 x 6 x 5 = 360 cells) is far too sparse for a ~40-day sample, so the
objective matches a hierarchy of pairwise joints instead:

| group | size | weight |
|-------|------|--------|
| direction x speed, frequency | 72 | 3.0 |
| direction x speed, energy (U^3) | 72 | 3.0 |
| direction x stability | 60 | 1.0 |
| speed x stability | 30 | 0.5 |
| month | 12 | 0.5 |
| hour of day | 8 | 0.5 |
| scalars (mean U, mean U^3, capacity factor) | 3 | 2.0 |

Each group is normalised to sum to 1 per block, so any convex combination of
blocks is itself a valid distribution. Scalars enter as ratios to target.

**Whole-day blocks make the diurnal match exact.** Every metric table below
shows `hour = 0.00`: a whole number of days contains every 3-hourly slot
equally, so the diurnal cycle — and with it much of the stability cycle — is
matched by construction rather than by fitting.

## Solver

Greedy forward selection with bounded NNLS weights, then swap refinement.
Weights live in `[0, 6/K]` and are renormalised to sum to 1. A cheap
correlation screen keeps only the 250 best-aligned candidates per step, so the
full 4383-candidate search takes seconds.

Three things were tested and found **not** to matter:

* **Simulated annealing over the block set changed nothing** — objective
  0.0430 before and after, identical metrics. Greedy+swap is already at a local
  optimum that SA cannot escape, so there is no case for MILP or a GA. The
  residual error is a capacity limit, not an optimiser limit.
* **The weight bound barely binds.** Varying `wmax` from 1.5/K to 20/K moves
  roseF only 2.11 -> 1.53 and never degenerates (ESS stays ~32/40). The data
  wants mild weights on its own.
* **Reweighting the objective trades rather than wins.** Boosting the
  direction x stability group 1.0 -> 3.0 improves that metric 7.54 -> 5.96 but
  costs roseF 1.67 -> 1.88. A genuine Pareto front — you are at the capacity of
  40 blocks.

## Results

All total-variation distances in %, out-of-sample: blocks selected on
2000-2011, scored against 2012-2024.

The **noise floor** is the honest reference — the TV between two disjoint
12-year halves of the record. It is how well 24 years even defines its own
target, and chasing error below it is meaningless.

| | roseF | roseE | dir x stab | secWS | month | ws% | en% |
|---|---|---|---|---|---|---|---|
| **noise floor** | **1.29** | **2.02** | **4.14** | **2.70** | **1.96** | -0.36 | -0.01 |
| equal-weight 40 x 1d | 2.91 | 4.29 | 10.46 | 5.25 | 6.09 | -0.40 | +0.90 |
| **weighted 40 x 1d** | **1.67** | **2.70** | **7.54** | 6.80 | 1.20 | -0.29 | +0.09 |
| weighted 14 x 3d | 2.35 | 4.12 | 13.97 | 6.64 | 4.76 | -0.02 | +0.68 |
| weighted 30 x 2d (60 d) | 1.59 | 2.64 | 7.84 | 5.76 | 2.20 | -0.24 | +0.00 |

**Weighting is worth roughly a factor of two** on nearly every metric, at no
extra compute. **Shorter blocks win decisively** — 40 one-day blocks beat 14
three-day blocks at the same day count, because degrees of freedom matter more
than block length.

### Cost-matched, since short blocks pay spin-up more often

Budget 50 day-equivalents = `blocks x (length + spin-up)`:

| spin-up | 1-day | 2-day | 3-day | 5-day |
|---------|-------|-------|-------|-------|
| 6 h | **1.87 / 1.91** (40 d) | 3.09 / 2.66 (44 d) | 3.38 / 5.05 (45 d) | 4.69 / 7.14 (45 d) |
| 12 h | **1.77 / 3.11** (33 d) | 2.29 / 2.47 (40 d) | 2.84 / 2.34 (42 d) | 4.69 / 7.14 (45 d) |

(roseF / roseE). At 6 h spin-up 1-day blocks win outright. At 12 h the
advantage largely evaporates and 1-3 day blocks are comparable — so **the
spin-up assumption is the pivotal engineering question**, not the statistics.

## Recommended configuration

40 one-day blocks, weighted, selected against the full 24-year record
(`selected_blocks.csv`). In-sample: roseF 1.90, roseE 1.04, dir x stab 4.87,
mean wind -0.10%, energy +0.28%, ESS 31.5/40, weights 0.0096-0.0704 against
0.025 for equal.

Seasonal coverage emerged without being imposed — 2-5 blocks in every calendar
month — which is why the soft seasonal term is preferred over a hard quota:
it leaves the degrees of freedom for the rose.

## Caveats

* **Weights require pipeline support.** `create-wrg` must accumulate a weighted
  histogram. Without it you fall back to equal weights and lose the factor of two.
* Validation is in ERA5 forcing space. The earlier wsw_nlcd work showed that
  matching the forcing does not automatically carry to the downscaled field —
  which is exactly why stability is now in the objective, but it remains
  untested at 100 m.
* `dir x stab` (7.54 vs a 4.14 floor) is the weakest metric and the one that
  most wants more blocks.
