"""Build a compact analysis h5 for the 40 sampled blocks, straight from the npz.

Why not the stock wrf-to-h5: it allocates a full synthetic calendar year (2019)
and fills only the timesteps you have.  For a 12-month TMY that tiles the year
that is fine; for 40 scattered days it produced a 428 GB file that was 98% zeros,
and two blocks sharing a month-day collided in the 2019 index.

This writes exactly the 960 real timesteps -- no synthetic calendar, no zero
padding, no collisions -- and only the variables the WRG needs.  ~4.9 GB.
Chunked (ntime, 64) because create-wrg reads whole per-pixel columns -- but that
makes a row-at-a-time write pathological (each row touches every chunk, as a
read-modify-write).  So the arrays are assembled in memory and each variable is
written in ONE call, so every chunk is written exactly once.  ~4.9 GB of buffer.

  python build_compact_h5.py [--heights 80,100,120,160]
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from wrfhr import cfg, path

import argparse
import glob
import os
from multiprocessing import Pool

import h5py
import netCDF4 as nc
import numpy as np
import pandas as pd

ROOT = cfg["CASE_ROOT"]
OUT = f"{ROOT}/processed/wsw_high_compact.h5"
GEO = f"{ROOT}/wps/geo_em.d05.nc"
VARS = None  # set in main


def _load(path):
    with np.load(path) as d:
        return [d[v].astype(np.float32) for v in VARS]


def main(heights, out=OUT, workers=64):
    global VARS
    VARS = [f"{k}_{h}m" for h in heights for k in ("wind_speed", "wind_direction")]

    man = pd.read_csv(f"{ROOT}/tmy/run_manifest.csv", parse_dates=["sample_start"])
    rows = []
    for _, r in man.iterrows():
        fs = sorted(glob.glob(f"{ROOT}/npz/wrfout_d05_"
                              f"{r.sample_start.strftime('%Y-%m-%d')}_*.npz"))
        assert len(fs) == 24, f"{r.run}: {len(fs)} npz"
        # a block's weight is spread evenly over its retained sample hours
        rows += [(f, r.run, r.weight / len(fs)) for f in fs]
    rows.sort(key=lambda t: os.path.basename(t[0]))
    files = [r[0] for r in rows]
    weights = np.array([r[2] for r in rows])
    stamps = [os.path.basename(f)[11:-4] for f in files]
    print(f"{len(files)} timesteps from {man.shape[0]} blocks; "
          f"weights sum {weights.sum():.6f}")

    with nc.Dataset(GEO) as g:
        lat = np.asarray(g["XLAT_M"][0]).ravel().astype(np.float32)
        lon = np.asarray(g["XLONG_M"][0]).ravel().astype(np.float32)
        elev = np.asarray(g["HGT_M"][0]).ravel().astype(np.float32)
        shape = tuple(np.asarray(g["XLAT_M"][0]).shape)
    npt = lat.size
    print(f"grid {shape} = {npt} points")

    os.makedirs(os.path.dirname(out), exist_ok=True)
    with h5py.File(out, "w") as h5:
        h5.attrs["domain_shape"] = np.array(shape)
        h5.attrs["resolution"] = 0.1                      # km, d05
        h5.create_dataset("time_index", data=np.array(stamps, dtype="S25"))
        h5.create_dataset("coordinates",
                          data=np.column_stack([lat, lon]).astype(np.float32))
        h5.create_dataset("elevation", data=elev)
        buf = {v: np.empty((len(files), npt), dtype=np.float32) for v in VARS}
        with Pool(workers) as p:
            for i, arrs in enumerate(p.imap(_load, files, chunksize=4)):
                for v, a in zip(VARS, arrs):
                    buf[v][i, :] = a
                if i % 200 == 0:
                    print(f"  read {i}/{len(files)}", flush=True)
        for v in VARS:
            print(f"  writing {v}", flush=True)
            h5.create_dataset(v, data=buf[v], chunks=(len(files), 64))
            del buf[v]

    np.save(f"{ROOT}/tmy/wrg_weights.npy", weights)
    gb = os.path.getsize(out) / 1e9
    print(f"wrote {out}  ({gb:.2f} GB)")
    print(f"wrote {ROOT}/tmy/wrg_weights.npy  "
          f"(ESS {1/np.sum((weights/weights.sum())**2):.1f} of {len(weights)})")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--heights", default="80,100,120,160")
    a = ap.parse_args()
    main([int(h) for h in a.heights.split(",")])
