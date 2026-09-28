# The 40-day selection algorithm

Full method, results and validation: `SAMPLING.md`. This is the operational
summary — what runs, in what order, and what each step produces.

## Idea

Choosing which periods to simulate is a **quadrature problem**: pick nodes
(blocks) and weights so the weighted empirical distribution approximates the
climate. Two consequences that the usual TMY approach leaves on the table:

- **weights are free** — a WRG is a weighted histogram either way, so nothing
  forces each sampled hour to count equally;
- the objective is a **distance between measures** over the variables that
  condition the downscaling, not a proxy like monthly mean wind speed.

## Pipeline

```
sampling/wps_reader.py       reads WPS intermediate files (no new downloads)
        |
sampling/extract_forcing.py  -> CASE_ROOT/tmy/era5_forcing_3h.csv
        |                       SKINTEMP, TT, UU, VV, PSFC, SNOW at the site,
        |                       3-hourly over the full record
sampling/build_dataset.py    -> CASE_ROOT/tmy/site_forcing.csv
        |                       + 100 m wind; bulk Richardson -> 5 stability classes
sampling/sampler.py          the objective and the solver (library, not a script)
        |
sampling/final_selection.py  -> data/selected_blocks.csv   40 x 1 day + weights
```

Evaluation/validation scripts: `eval3.py` (strategy comparison against the
noise floor), `eval4.py` (block geometry + out-of-sample), `eval5.py`
(optimiser quality, weight bounds, objective reweighting), `eval6.py`
(cost-matched geometry).

## Objective

Terrain response is conditioned on direction, speed and stability **jointly**,
but the full 3-way joint is far too sparse for ~40 days. The objective matches
a hierarchy of pairwise joints instead:

| group | size | weight |
|---|---|---|
| direction x speed, frequency | 72 | 3.0 |
| direction x speed, energy (U^3) | 72 | 3.0 |
| direction x stability | 60 | 1.0 |
| speed x stability | 30 | 0.5 |
| month | 12 | 0.5 |
| hour of day | 8 | 0.5 |
| scalars (mean U, mean U^3, capacity factor) | 3 | 2.0 |

Whole-day blocks make the diurnal match exact by construction — every metric
table shows `hour = 0.00`.

## Solver

Greedy forward selection with bounded NNLS weights, then swap refinement.
Weights live in `[0, 6/K]`, renormalised to sum to 1.

Simulated annealing over the block set changed the objective by nothing
(0.0430 before and after), so the residual is a capacity limit of 40 blocks,
not a search failure. No case for MILP or a GA.

## Result

Out-of-sample (select on 2000-2011, score against 2012-2024), total-variation
distances in %:

| | roseF | roseE | dir x stab | en% |
|---|---|---|---|---|
| noise floor (two 12-yr halves) | 1.29 | 2.02 | 4.14 | -0.01 |
| equal-weight 40 x 1d | 2.91 | 4.29 | 10.46 | +0.90 |
| **weighted 40 x 1d** | **1.67** | **2.70** | **7.54** | **+0.09** |

Weighting is worth ~2x on nearly every metric at no extra compute, and shorter
blocks beat longer ones at equal cost — degrees of freedom matter more than
block length.

## Known gap

The sampler does not constrain sampled days to unique month-days. That is
harmless here but collides with `wakemap_processor`'s synthetic-2019 time index
(see `PORTING.md`). Adding the constraint costs essentially nothing — 40 days
chosen from ~8,700 candidates.
