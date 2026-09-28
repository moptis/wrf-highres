# Porting to another HPC system

## 1. Fill in `site.env`

Copy `site.env.example`. Everything the code needs is in there; nothing else in
`domain/`, `sampling/`, `pipeline/`, `analysis/` or `slurm/` hardcodes a path
(`experiments/` does — it is provenance, not tooling).

Environment variables override `site.env`, so a one-off run can be redirected
without editing:

```bash
CASE_ROOT=/scratch/me/testcase python domain/design_domains.py
```

## 2. What must exist on the new system

| | notes |
|---|---|
| WRF build (`wrf.exe`, `real.exe`) | 4.6-compatible; the nest uses 5 domains |
| WPS build (`geogrid.exe`, `metgrid.exe`) | plus `GEOGRID.TBL` / `METGRID.TBL` |
| WPS_GEOG | **see the terrain note in the README before reusing a tree** |
| ERA5 in WPS intermediate format | 3-hourly `ERA5_SURF` / `ERA5_PRES` |
| Python env | numpy, pandas, scipy, netCDF4, h5py, matplotlib, pyproj, rasterio |
| `wakemap_processor` | with `patches/wakemap-weighted-wrg.patch` applied |

`sampling/extract_forcing.py` reads the WPS intermediate files directly
(`sampling/wps_reader.py`), so no extra download is needed for the stability
variables — `SKINTEMP`, `TT`, `UU`, `VV` are already in `ERA5_SURF`.

## 3. Scheduler differences

`#SBATCH` directives cannot read `site.env` — sbatch parses them before any
shell runs. The scripts carry `*_PLACEHOLDER` values in those lines. Either
edit them once, or submit with explicit flags:

```bash
sbatch -A "$SLURM_ACCOUNT" -p "$PART_CPU" --qos "$SLURM_QOS" slurm/04_wrf_cpu.sbatch
```

Everything *below* the directive block does read `site.env`, via
`slurm/common.sh`.

Partition roles assumed: `PART_CPU` full-node exclusive for WRF, `PART_SHARED`
short single-task jobs (metgrid, real, analysis), `PART_DEBUG` quick turnaround.

## 4. Re-measure these before trusting them

The numbers in `docs/FINDINGS.md` are machine-specific. On new hardware:

- **Rank scaling and the binding effect.** `experiments/10_binding_test.sbatch`
  compares `srun -n N` against `--exact --cpu-bind=cores`. The 1.9x penalty for
  one-core-per-rank is a memory-bandwidth property of the node.
- **Throughput.** `analysis/profile_run.py <rsl.error.0000>` gives wall-seconds
  per simulated second and the per-domain cost split. Set `WRF_WALLTIME` from
  it with real headroom.
- **Time step.** The adaptive scheme settles on its own, but confirm no
  `exceeded v_cfl` messages appear:
  `grep -c 'exceeded v_cfl' <rundir>/rsl.error.*`

## 5. Things that bit us, so they do not bite again

- **`get_file_dirs()` in `wakemap_processor` uses `os.walk`.** Pointing
  `wrf-to-h5` at a directory containing benchmark runs or an `attempt_*/`
  subdirectory silently ingests them. `pipeline/build_compact_h5.py` sidesteps
  this by reading an explicit file list.
- **`wrf_to_h5` maps all timestamps onto a synthetic year 2019.** Two sampled
  days sharing a month-day collide, and the duplicate guard does not catch it
  (it checks real dates, the index uses the 2019 slots). The compact builder
  avoids the whole mechanism. If you use the stock path instead, constrain the
  sampler to unique month-days.
- **Copying onto a symlink writes through it.** `03_prepare_runs.py` does
  `ln -sf $WRF_RUN_DIR/*` then `cp namelist.input`, clobbering the file in the
  shared WRF build. `pipeline/stage_blocks.py` removes the symlinks first.
- **HDF5 chunk shape must match the dominant access pattern.** Chunking
  `(ntime, 64)` for fast column reads makes a row-at-a-time write ~100x slower.
  Buffer and write once.
- **Restarted runs were ~6x slower per step** than fresh ones, cause not
  established. Budget for it if you rely on checkpoint/restart.
