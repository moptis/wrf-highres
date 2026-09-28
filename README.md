# wrf-highres

Five-domain WRF nest down to **100 m** for wind-resource (WRG) production, with a
weighted block-sampling method that replaces a 12-month TMY with ~40 simulated
days at comparable statistical fidelity.

Developed for the WSW site in central New Mexico (Sept 2026). Every
machine-specific path lives in `site.env`, so porting is editing one file.

---

## Status

| | |
|---|---|
| 5-domain nest 8100/2700/900/300/100 m | built, validated |
| 40-day weighted sample from 24 yr ERA5 | built, validated out-of-sample |
| 40 WRF runs | complete, 960 sample hours, zero CFL events |
| Weighted WRG at 80/100/120/160 m | produced |
| **Terrain resolution** | **BLOCKING — see below** |

### The one thing to fix before trusting the output

The 100 m nest was run on **GMTED2010 30-arcsecond (~900 m) terrain**, because
`geog_data_res = '...+default'` resolves to `topo_gmted2010_30s` for `HGT_M`.
Measured against a Vortex 100 m WRG over the same box:

| | >2 km | 0.8-2 km | 400-800 m | <400 m |
|---|---|---|---|---|
| terrain, Vortex | 44.6% | 9.9% | 15.1% | **30.4%** |
| terrain, ours | 97.3% | 1.6% | 0.6% | **0.4%** |
| wind, Vortex | 88.3% | 3.6% | 2.8% | **5.4%** |
| wind, ours | 98.0% | 1.5% | 0.3% | **0.2%** |

The two terrain fields correlate at 0.996 — same mountain, ours with everything
below ~2 km erased. The wind field inherits exactly that. **The resolution was
never the limitation; the terrain input was.** Note the asymmetry: 30 m NLCD
land cover was fed to the same domain that got 900 m topography.

Fixing it needs a high-resolution DEM (USGS 3DEP / SRTM) for the domain,
converted to WPS binary format, a `rel_path`/`interp_option` entry added to
`GEOGRID.TBL`, `geog_data_res` changed on d04/d05, geogrid rerun, and the 40
blocks rerun. `topo_srtm_1_3s` exists in some WPS_GEOG trees at ~10 m but the
copy used here covered Oklahoma, not the site — check extent before assuming.
Also consider reducing `smooth_passes` on the fine nests.

---

## Layout

```
site.env.example   copy to site.env and edit -- the only machine-specific file
wrfhr/config.py    loads site.env; env vars override it
domain/            nest design + geogrid verification
sampling/          the 40-day selection algorithm (see docs/SAMPLING.md)
pipeline/          stage runs -> compact h5 -> weighted WRG
analysis/          profiling, maps, WRG comparison
slurm/             job scripts (all read site.env via slurm/common.sh)
namelists/         the namelists actually used, plus the 1 km parent for reference
patches/           weighted-WRG patch for wakemap_processor
data/              selected blocks + run manifest + myoutfields
docs/              findings, sampling method, porting notes
experiments/       one-off benchmarks; HARDCODED PATHS, kept as provenance
```

---

## Workflow

```bash
cp site.env.example site.env && $EDITOR site.env

# 1. design the nest (writes namelist.wps + namelist.input into CASE_ROOT)
python domain/design_domains.py
sbatch slurm/01_geogrid.sbatch
python domain/verify_geo.py            # checks the WRG box sits inside d05

# 2. select the sample days  (docs/SAMPLING.md)
python sampling/extract_forcing.py     # site forcing from local WPS files
python sampling/build_dataset.py       # + 100 m wind, Richardson stability classes
python sampling/final_selection.py     # -> data/selected_blocks.csv (40 days + weights)

# 3. run
python pipeline/stage_blocks.py --spinup 6
bash   slurm/13_submit_blocks.sh
bash   analysis/check_blocks.sh        # progress / failures

# 4. post-process
python pipeline/build_compact_h5.py    # npz -> compact h5 + weight vector
python pipeline/run_wrg.py             # weighted WRG at each hub height
python analysis/wrg_meanws_map.py deliverables/wrg/*.wrg
```

Step 4 requires `patches/wakemap-weighted-wrg.patch` applied to
`wakemap_processor` — without it `create-wrg` ignores the weights.

---

## Settings that are not arbitrary

Each of these was measured; changing one without re-measuring is how this
campaign lost ~1,400 node-hours.

- **`WRF_RANKS=64`** — WRF needs >=10 cells per MPI patch and d01/d02 are 80/81
  cells, so 64 is the ceiling. Raising it means enlarging the outer domains
  (`MIN_CELLS` in `design_domains.py`).
- **Adaptive time stepping, not fixed** — a fixed d05 step validated on one day
  blew up on 14 of 40 blocks and damped 7 more. Under adaptive, each domain
  derives its step from its own vertical Courant number.
- **`--exclusive`** — WRF here is memory-bandwidth-bound; confining ranks to one
  core each costs 1.9x. The node ceiling is ~1.37 node-s per simulated second
  however you arrange ranks.
- **40 h walltime** — a 30 h block needs ~26 h under adaptive.
- **Hourly d05 output** — the integral timescale is ~5 h, so 10-minute output is
  ~99% redundant and costs 6x the disk.

See `docs/FINDINGS.md` for the measurements behind each.
