"""Extract a site forcing timeseries from the local ERA5 WPS files.

Gives the large-scale state that conditions the downscaling: 10 m wind, 2 m and
skin temperature (surface-layer stability), pressure and snow.  3-hourly,
1999-2025.  Hub-height wind comes from the hourly ERA5 100 m product and is
merged separately.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from wrfhr import cfg, path

ROOT = cfg["CASE_ROOT"]

import os, sys, glob, re
import numpy as np, pandas as pd
from multiprocessing import Pool
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wps_reader import read_fields, point_index

MET = cfg["MET_DIR"]
OUT = path("CASE_ROOT", "tmy", "era5_forcing_3h.csv")
# Site cell for the forcing extraction.  Must match the ERA5 cell era5.csv was
# drawn from, or the stability state and the hub wind describe different places.
SITE_LAT = float(cfg.get("SITE_LAT", 34.5))
SITE_LON = float(cfg.get("SITE_LON", -105.5))
WANT = {"SKINTEMP", "TT", "UU", "VV", "PSFC", "SNOW"}
_IDX = None


def _init(idx):
    global _IDX
    _IDX = idx


def _one(path):
    try:
        out, _ = read_fields(path, wanted=WANT, point=_IDX)
    except Exception:
        return None
    m = re.search(r"ERA5_SURF:(\S+)", os.path.basename(path))
    return (m.group(1), out.get("TT:200100"), out.get("SKINTEMP:200100"),
            out.get("UU:200100"), out.get("VV:200100"),
            out.get("PSFC:200100"), out.get("SNOW:200100"))


if __name__ == "__main__":
    files = sorted(glob.glob(f"{MET}/ERA5_SURF:*"))
    print(f"{len(files)} SURF files")
    _, grid = read_fields(files[0], wanted={"TT"})
    idx, la, lo = point_index(grid, SITE_LAT, SITE_LON)
    print(f"site cell: {la:.2f} {lo:.2f} (flat index {idx})")

    with Pool(64, initializer=_init, initargs=(idx,)) as p:
        rows = [r for r in p.map(_one, files, chunksize=64) if r]
    print(f"{len(rows)} rows read")

    df = pd.DataFrame(rows, columns=["stamp", "t2", "tskin", "u10", "v10", "psfc", "snow"])
    df["time"] = pd.to_datetime(df["stamp"], format="%Y-%m-%d_%H")
    df = df.drop(columns="stamp").set_index("time").sort_index()
    df = df[~df.index.duplicated()]

    # surface-layer stability.  dT > 0 means the ground is warmer than the air
    # (unstable); the bulk Richardson number folds in the wind that mixes it.
    df["u10s"] = np.hypot(df.u10, df.v10)
    df["dT"] = df.tskin - df.t2
    g, z = 9.81, 10.0
    df["ri_b"] = -g * z * df.dT / (df.t2 * np.maximum(df.u10s, 0.5) ** 2)

    df.to_csv(OUT, float_format="%.4f")
    print(f"wrote {OUT}  {df.index[0]} .. {df.index[-1]}  n={len(df)}")
    print(df[["t2", "tskin", "dT", "u10s", "ri_b", "snow"]].describe().round(3).to_string())
