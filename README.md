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
| Terrain upgraded to Copernicus GLO-30 | done |
| **Wind field smoother than Vortex** | **OPEN — physics, not inputs** |

### Where the resolution actually goes — corrected 2026-10-06

Our 100 m WRF field is visibly smoother than a Vortex 100 m WRG over the same
box. Comparing mean-speed and terrain spectra (nodata filled by nearest
neighbour — see the warning below):

| | sd | sub-2 km variance | <400 m |
|---|---|---|---|
| terrain, Vortex | 71.1 | 3.2% | 0.41% |
| terrain, ours | 75.8 | 2.9% | 0.44% |
| **wind, Vortex** | 0.51 | **11.6%** | **5.22%** |
| **wind, ours** | 0.48 | **2.1%** | **0.19%** |

**The terrain is not the difference — the wind is.** Vortex carries ~5x our
sub-2 km wind variance and ~27x below 400 m, from terrain no finer than ours.

The leading suspect is the physics, not the inputs: **MYNN at 100 m sits in the
turbulence grey zone and over-mixes**, which smooths exactly these scales.
`diff_opt=2` / `km_opt=4` numerical diffusion and the vertical grid are the
other candidates. An LES configuration on d04/d05 is the obvious experiment,
and was flagged as an open question when the physics was first set up.

**A retracted claim.** An earlier version of this file said the cause was
terrain resolution — that our 100 m nest ran on ~900 m GMTED while Vortex had
something far finer, citing "55.4% vs 2.7%" sub-km terrain variance. That was
an artifact: 267 nodata cells in the Vortex WRG sit at elevation 0 amid ~1900 m
terrain, and the spectrum code filled only non-finite values, so those 1900 m
delta functions survived and dominated the high-wavenumber bands. The 0.996
correlation between the two terrain fields should have been treated as
contradicting the spectra, and was not.

The terrain was nonetheless upgraded to Copernicus GLO-30 (see below) and that
is worth keeping — 30 m source is the correct input for a 100 m grid and p99
gradients went 90.8 -> 244.5 m/km — but it does **not** close the wind gap.

### Terrain: Copernicus GLO-30 (done)

`/projects/aiweather/WPS_GEOG` now holds the full geog tree plus
`topo_cop30_1s_r{0-2}c{0-4}` — Copernicus GLO-30 at 1 arcsec over CONUS and
Canada, 32,504 tiles, 89 GB, registered as resolution `cop30` in `GEOGRID.TBL`
at priorities above the GMTED 30 s fallback. Set with
`geog_data_res = 'cop30+nlcd2025+default'`.

Three things that bite when building it, all handled in
`tools/make_wps_topo.py`:

- Copernicus reduces longitudinal sampling with latitude (3600 columns below
  50N, then 2400/1800/1200/720). WPS needs uniform `regular_ll`, so everything
  is resampled through a uniform 1-arcsec VRT first.
- WPS tile filenames carry 5-digit cell indices, capping a dataset at 99999
  cells per side. North America at 1 arcsec is 327600 x 216000, hence 15
  pieces — the same reason NLCD2025 ships as 16.
- Tile files include the halo: `(tile+2*bdr)^2` values, verified against the
  shipped GMTED tiles.

Verified: geogrid output matches the raw mosaic sampled at the same grid points
to 1.18 m rms, so no detail is lost in conversion.

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
