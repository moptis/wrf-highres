"""Integrity check on the staged DEM tiles.

A truncated or half-written GeoTIFF opens fine at the header but fails on read,
which would surface much later as a hole in the WPS dataset. Check every tile
opens, has the expected 1-degree geometry, and that a sample of pixels reads.
"""
import glob, sys
import numpy as np, rasterio
from concurrent.futures import ProcessPoolExecutor

def check(f):
    try:
        with rasterio.open(f) as d:
            if d.count != 1:
                return f, f"bands={d.count}"
            b = d.bounds
            if not (0.98 < (b.right - b.left) < 1.02 and 0.98 < (b.top - b.bottom) < 1.02):
                return f, f"not 1 deg: {b.right-b.left:.3f}x{b.top-b.bottom:.3f}"
            a = d.read(1, out_shape=(64, 64))          # forces decode of real data
            if not np.isfinite(a).any():
                return f, "no finite data"
    except Exception as e:
        return f, f"{type(e).__name__}: {str(e)[:60]}"
    return None

for name, pat in (("COP30", "cop30_na/*.tif"), ("3DEP", "3dep_1arcsec/*.tif")):
    fs = sorted(glob.glob(pat))
    with ProcessPoolExecutor(16) as ex:
        bad = [r for r in ex.map(check, fs, chunksize=8) if r]
    print(f"{name}: {len(fs)} tiles, {len(bad)} bad")
    for f, why in bad[:5]:
        print(f"    {f.split('/')[-1]}: {why}")
