# wsw_high — performance and sampling findings

Everything below is measured on the built 5-domain nest (8100/2700/900/300/100 m,
d05 = 391 x 409), not estimated. Model setup and validation are in README.md.

---

## 1. Where the time goes

Exclusive cost per domain, 64 ranks:

| dom | dx | exclusive share | s/step |
|-----|------|-----------------|--------|
| d01 | 8100 | 5.7% | 33.8 |
| d02 | 2700 | ~0% | 10.6 |
| d03 | 900  | 2.2% | 4.5 |
| d04 | 300  | 20.2% | 1.33 |
| d05 | 100  | **72.8%** | 0.52 |

d04+d05 are 93% of runtime. Optimising the outer domains is pointless — which
is why making d01 648 km to unlock more MPI ranks was free.

---

## 2. CPU vs GPU — stay on CPU

| | wall-s per simulated s | d05 s/step |
|---|---|---|
| CPU, 64 ranks | 0.89 | 0.52 |
| AceCast, 1x H100 (full 57 min) | 2.29 | 1.67 |

AceCast keeps speeding up for far longer than a normal warm-up: over 1729 d05
steps the expensive half of the step pair fell from 3.59 s to 1.59 s (the cheap
half held at 0.32 s throughout), taking the run from 2.65 to 2.29 wall-s per
model-s. It had plateaued by the end. Short GPU benchmarks on this model will
read pessimistically -- do not judge it on the first ten minutes.

Cost per simulated second, in CPU-node-seconds (GPU node = 10x CPU node):

* CPU: `0.89 x 64/104 = 0.547`
* GPU: `2.29 x 1/4 x 10 = 5.73`

**CPU is ~10.5x more cost-effective.** Break-even needs 1 GPU at 0.22 wall-s per
model-s — 10.5x faster than measured, 4x faster than 64 CPU cores.

More GPUs do not fix this: under proportional charging, 4 GPUs at perfect
scaling costs exactly what 1 GPU costs. You buy wall-clock, not allocation.

### The GPU result is pathological, not merely slow

d05 step cost alternates dead-regularly between **1.59 s and 0.32 s** once
warmed up. The expensive step is the one taking lateral boundaries from d04 —
nest-coupling overhead, not compute. The 0.32 s figure is what the H100 can
actually do, and that is **1.6x faster than 64 CPU cores**. d05 is 86% of GPU
runtime (vs 73% on CPU), i.e. the penalty lands squarely on the domain that
matters.

Your 1 km 3-domain production runs will not show this: five domains at ratio 3
generate far more nest-coupling events per simulated second. Even so, fixing it
entirely would give ~1.1 vs 0.547 CPU-node-s — still ~2x worse. The 10x node
price is too big a multiplier.

AceCast's `real.exe` was 2x faster than the CPU build (32 s vs ~60 s), and its
`acecast-advisor.sh --tool support-check` passes the namelist clean.

---

## 3. Rank count and node packing

Fixed dt=40 s, history off, so only the decomposition varies:

| ranks | wall-s per model-s | step speedup | node-s per model-s | h per 3-day chunk |
|-------|--------------------|--------------|--------------------|-------------------|
| 8  | 4.944 | —     | 0.380 | 356 |
| 16 | 3.233 | 1.53x | 0.497 | 233 |
| 32 | 1.763 | 1.83x | 0.542 | 127 |
| 64 | 1.369 | 1.29x | 0.842 |  99 |

16 -> 32 is nearly ideal (1.83x of a possible 2x); 32 -> 64 collapses to 1.29x.
Allocation cost per simulated second rises monotonically with rank count, so
*fewer* ranks are always cheaper — but 8 ranks needs 356 h per chunk, which is
7 restarts against the 48 h limit. 32 ranks is the practical balance.

Doubling 32 -> 64 buys **1.29x, i.e. 64% parallel efficiency**. Uniform across
domains (d05 1.29x, d04 1.32x) and d05 patches are still 49x51 cells at 64
ranks, so this is memory-bandwidth saturation, not decomposition starvation.

Per simulated second: 32 ranks costs `1.763 x 32/104 = 0.543` node-s, 64 ranks
costs `1.369 x 64/104 = 0.843`. **32 ranks is 1.55x cheaper.**


### Packing does NOT beat simply using more ranks

| concurrent x 32 | mean wall/model | per-job slowdown | node-s per model-s |
|-----------------|-----------------|------------------|--------------------|
| 1 | 3.673 | — | 3.673 |
| 2 | 3.926 | 1.07x | 1.963 |
| 3 | 4.127 | 1.12x | **1.376** |

Three packed 32-rank jobs give 1.376 node-s per simulated second — identical to
a single 64-rank job at 1.369. The apparent 1.55x advantage of 32 ranks was an
artefact: it compared a *spread* 32-rank run against a 64-rank run and assumed
packing would preserve that efficiency. It does not.

### Why: WRF needs ~3 cores' worth of memory bandwidth per rank

Same 32 ranks, same node, three launch styles:

| launch | wall/model |
|--------|-----------|
| `srun -n 32` (implicit spread, ~3 CPUs/rank) | 1.831 |
| `srun --exact --cpu-bind=cores -n 32` (confined, 1 CPU/rank) | 3.304 |
| `srun --exact -n 32 -c 3` (3 CPUs/rank) | 1.748 |

Confining ranks to one core each costs **1.9x**. Giving them 3 CPUs recovers it
fully. This single mechanism explains the poor 32->64 scaling *and* the packing
result: the node has a memory-bandwidth ceiling of **~1.37 node-s per simulated
second**, and how you arrange ranks barely matters once you are using the whole
node. Packing cannot beat it, because 3 jobs x 32 ranks x 3 CPUs would need 288
cores on a 104-core node.

**Use 64 ranks, one job per node.** It reaches the ceiling with no packing
complexity, and 64 is the maximum this nest allows anyway.

**64 ranks is a hard ceiling** regardless: WRF needs >=10 cells per patch and
d01/d02 are 80/81 cells. Raising it means raising `MIN_CELLS` in
`design_domains.py`.

---

## 4. Time-step headroom

d05 runs at dt ~0.89 s on a 100 m grid — advective CFL ~0.22 against a 0.7
target. Two reasons it sits so low:

1. The adaptive scheme ramps at +5%/step and had only reached 45 s when the
   test ended.

   **Correction (2026-09-24):** an earlier version of this document claimed
   `adaptation_domain = 1` means d05's CFL is never checked.  That is wrong.
   `adapt_timestep_em.F` runs per domain and each grid derives its step from
   its OWN `max_vert_cfl` / `max_horiz_cfl` (lines 143-160), reduced across
   that domain's tiles (line 257).  Under adaptive stepping d05 therefore
   adapts on d05's own vertical Courant number.  Separately,
   `adaptation_domain > 1` is gated on `max_dom == 2` (line 370), so in a
   5-domain run it is a no-op -- child-driven adaptation of the parent step is
   only supported for two domains.
2. WRF's `reasonable_time_step_ratio` defaults to **6 s/km**, which caps d01
   near 48 s. It is a namelist guard, not a stability limit, and it is why the
   adaptive scheme never explores further. Overriding it is required to test
   anything larger.

### The speedup is sublinear, by construction

`solve_em.F:441` sets acoustic substeps as
`max(2*(INT(300*dt/dx - 0.01)+1), 4)` — so at dx=100 m, dt=0.889 gives 6
substeps and dt=2.0 gives 12. **Total acoustic work per simulated second is
invariant to dt**; only the large-step work shrinks.

Measured: d05 costs **0.50 s/step at dt=0.889** (6 substeps) vs **0.65 s/step
at dt=2.0** (12 substeps) — per-step cost up 1.3x while dt rose 2.25x, so net
**1.73x throughput**.

### The limit is the VERTICAL CFL, and it bites sooner than expected

Configs run for 3 h of model time from a common initial state:

| cfg | d01 dt | time ratios | d05 dt | result |
|-----|--------|-------------|--------|--------|
| A | 72 s | 1,3,3,3,3 | 0.889 s | **clean** — 3 h, zero `v_cfl` exceedances |
| B | 72 s | 1,3,3,3,2 | 1.333 s | **clean** — 3 h, zero `v_cfl` exceedances |
| F | 72 s | 1,3,3,2,2 | 2.000 s | **segfault** — W reached 366 m/s, w-cfl 27.6 |
| C | 120 s | 1,3,3,3,2 | 2.222 s | **segfault** (d01 also raised, confounded) |
| D | 72 s | 1,3,3,3,1 | 2.667 s | **segfault** — W 66 m/s, w-cfl 13.7 |

With d01 fixed at 72 s the achievable ladder is {0.889, 1.333, 2.0, 2.667}, so
the ceiling sits between 1.333 and 2.0 s. **Use 1.333 s** — a clean 1.5x, with
margin. Chasing an intermediate value would buy ~1.2x more while sitting on the
edge of a blowup, which is a bad trade for a long campaign.

### 1.333 s gives the same answer, not just a surviving run

d05 fields after 3 h of model time from a common initial state, model level 5
(~100 m AGL):

| cfg | d05 dt | mean \|V\| | bias vs A | rms diff | w rms | w p99 | HF frac |
|-----|--------|----------|-----------|----------|-------|-------|---------|
| A | 0.889 s | 10.611 | — | — | 0.434 | 1.271 | 0.0043 |
| B | 1.333 s | 10.612 | +0.01% | 0.090 m/s | 0.438 | 1.278 | 0.0044 |

Mean speed is unchanged. The 0.090 m/s point-wise rms (0.85% of the mean) is
ordinary chaotic divergence between two runs after 3 h, not a systematic shift.
Critically, **vertical velocity is not being damped** — B's w rms and 99th
percentile are marginally *higher*, not lower — and the high-frequency spectral
fraction is flat (0.0044 vs 0.0043), so no grid-scale noise is accumulating.
Both failure modes that `w_damping = 1` could have hidden are ruled out.

D is the diagnostic one -- d01 stayed at a safe 72 s, so only d05/d04 changed.
It blew up within 72 s of model time:

```
2587 points exceeded v_cfl = 2 in domain d05
Max   W:  147 230 34   W:  65.99   w-cfl:  5.58
Max   W:  145 234 36   W:  11.55   w-cfl: 13.72
```

That is the **vertical** Courant number, not the horizontal one. The binding
constraint is `w*dt/dz` with dz ~19 m in the rotor layer over the mesas -- the
advective CFL of ~0.2 was never the limit. Buying more time step would mean
coarsening the vertical grid exactly where the WRG needs it, so this is a hard
ceiling, not a tuning knob.

Practical headroom is therefore **1.5x**, not the 2-3x the horizontal CFL
suggested.

Note also that a time ratio of 2 under a grid ratio of 3 runs fine (config B),
so `parent_time_step_ratio` is a usable knob independent of
`parent_grid_ratio`.

---

## 5. Representative-period sampling

The current TMY is 12 whole months (366 days, ~396 day-equivalents including
6 h spin-up per 3-day chunk). For a WRG only the *distribution* needs to be
right, not the chronology.

Cost is quoted as **day-equivalents** = `blocks x (block_length + 0.25)`,
charging 6 h of spin-up per block — which is what makes short blocks expensive
per useful day and drives the geometry choice.

### Naive short sampling is unsafe

Random 30 days (ERA5, vs the 24-yr record): mean speed error 6-8%, **energy
error 18%**. Not usable.

### Matching the ERA5 forcing distribution is not enough

Greedy block selection matching the ERA5 joint (sector x speed) distribution,
month, hour, mean U and mean U^3 gets ERA5-space error to ~0.5% — and holds up
out-of-sample (select on even years, score on odd). But scored against the
**downscaled** 1 km TMY field it leaves a persistent **+2 to +8% AEP level
bias**. The bias is a coherent domain-wide shift (p5 +1.7%, p50 +6.8%,
p95 +11.4%, zero correlation with elevation), not scatter.

Matching the forcing at one ERA5 cell does not pin the domain-mean response of
the nest.

### Selecting against the 1 km run itself works

The 1 km TMY already exists and is cheap, so score candidate blocks directly on
its fields — resource level *and* normalised spatial pattern — then rerun only
those days at 100 m:

| selection | days | cost_d | mean% | AEP% | pattern r | pattern RMS% |
|-----------|------|--------|-------|------|-----------|--------------|
| full TMY | 366 | 396.5 | — | — | — | — |
| supervised 7 x 2d | 14 | 15.8 | -0.02 | -0.17 | 0.9876 | 1.65 |
| supervised 14 x 2d | 28 | 31.5 | +0.04 | +0.00 | 0.9945 | 1.23 |
| supervised 10 x 3d | 30 | 32.5 | +0.06 | +0.64 | 0.9956 | 1.02 |
| **supervised 14 x 3d** | **42** | **45.5** | **-0.14** | **-0.02** | **0.9968** | **0.84** |
| supervised 21 x 2d | 42 | 47.2 | -0.02 | +0.06 | 0.9981 | 0.75 |
| supervised 20 x 3d | 60 | 65.0 | -0.17 | -0.05 | 0.9987 | 0.70 |

28 days reproduces the full-TMY resource level to <0.1% and the spatial pattern
to 1.2% RMS, at **12.6x less compute**. 42 days gets pattern RMS to 0.84% at
8.7x less.

### It is not overfitting

The selector is optimised against the field it is scored on, so a spatial
hold-out was run — choose blocks using a random half of the grid points, score
on the other half:

| selection | days | train pattern RMS% | held-out pattern RMS% |
|-----------|------|--------------------|-----------------------|
| 7 x 2d | 14 | 1.80 | 1.83 |
| 14 x 2d | 28 | 1.50 | 1.55 |
| 10 x 3d | 30 | 1.15 | 1.21 |
| 14 x 3d | 42 | 0.90 | 0.93 |
| 21 x 2d | 42 | 0.88 | 0.92 |

Train and held-out errors are identical. The selection works by capturing flow
**regimes**, not by fitting point-specific noise — which is the evidence needed
that it transfers to a grid it has never seen.

### Remaining assumption

Validation is at 1 km. The step of faith is that a block set reproducing the
1 km pattern also reproduces the 100 m pattern. The hold-out result makes this
reasonable — it transfers across unseen points — but it is untested across
unseen *scales*, and 100 m resolves terrain features 1 km cannot. Sub-grid
features at 100 m may respond to regimes the 1 km selection does not
distinguish.

A cheap check once the 100 m runs exist: run one extra block beyond the selected
set and confirm it does not move the pattern.

### Other findings

* **More, shorter blocks beat fewer, longer ones** for a fixed day budget —
  synoptic diversity matters more than block length. 21 x 2d beats 6 x 5d
  clearly, even paying more spin-up overhead.
* Matching mean U^3 alone biases AEP high: a few very windy hours satisfy the
  U^3 constraint but sit at rated power. An explicit capacity-factor term in
  the objective fixes it.
* Level and pattern are separately controllable. If you would rather keep the
  full TMY level, anchor it to the 1 km run and use the short 100 m sample only
  for the terrain speed-up ratio.

---

## 6. Recommended configuration

1. **CPU, not GPU** — ~12x cheaper on allocation.
2. **32 ranks per job, 3 jobs per node** — 1.55x cheaper than 64 ranks, and
   packing showed no contention.
3. **Sample ~14 x 3d or 21 x 2d blocks** selected against the existing 1 km TMY
   via `tmy/select_supervised.py`, instead of all 12 months. ~9x less compute
   for <1% level error and <1% pattern RMS.
4. **Hourly d05 output** (applied) — WRG needs a distribution, not a timeseries.
   6x less I/O and disk.
5. **`tke_budget = 0`** (applied) — the pipeline reads QKE, never the budget terms.
6. **d05 time step 1.333 s** (`parent_time_step_ratio = 1,3,3,3,2`) — validated
   clean over 3 h with zero `v_cfl` exceedances. 2.0 s and above blow up on
   vertical CFL.

### Measured production throughput (64 ranks)

| d05 dt | wall-s per model-s | h per 3-day block | h per 2-day block |
|--------|--------------------|-------------------|-------------------|
| 0.889 s | 0.747 | 53.8 (needs restart) | 35.9 |
| **1.333 s** | **0.578** | **41.6 (fits 48 h)** | 27.7 |

The dt gain is 1.29x for a 1.50x step — the acoustic-substep penalty costs
1.16x, as predicted. Note 1.333 s brings a 3-day block inside the 48 h limit,
removing restart handling entirely.

### Campaign cost

| campaign | blocks | node-hours |
|----------|--------|-----------|
| full TMY, dt 0.889 (baseline) | 122 | 6560 |
| full TMY, dt 1.333 | 122 | 5080 |
| **14 x 3d sample, dt 1.333** | **14** | **583** |
| 14 x 2d sample, dt 1.333 | 14 | 388 |

**~11x total reduction** versus the baseline, most of it from sampling rather
than from tuning.

---

## Scripts

```
tmy/sampling.py           ERA5 loader, v1 histogram matcher, EMD TMY reproduction
tmy/sampler2.py           block sampler: scalar level terms + swap refinement
tmy/eval_era5.py          ERA5-space strategy comparison
tmy/eval2.py              block-geometry sweep + even/odd out-of-sample test
tmy/extract_wrf.py        pull 100 m wind from the 1 km TMY h5 (456 points)
tmy/validate_wrf.py       does ERA5-space matching survive downscaling?
tmy/scaling_curve.py      fidelity vs sample size; level/pattern decomposition
tmy/select_supervised.py  RECOMMENDED selector, scored on the 1 km field
tmy/holdout.py            spatial hold-out test
profile_run.py            per-domain exclusive cost from rsl.error.0000
```
