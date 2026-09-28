"""What did 100 m buy over the 1 km baseline?

Both WRGs are UTM 13N.  Aggregate the 100 m mean-speed field onto the 1 km grid
over the overlap: the difference in means is the LEVEL change, and the variance
the 100 m field carries within each 1 km cell is the terrain detail that the
coarse run cannot represent at all.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from wrfhr import cfg, path

ROOT = cfg["CASE_ROOT"]

import sys
import numpy as np
sys.path.insert(0, cfg["CASE_ROOT"])
from wrg_meanws_map import read_wrg, grid
from math import gamma

HI = sys.argv[1] if len(sys.argv) > 1 else path(
    "CASE_ROOT", "deliverables", "wrg", "wsw_high_100m.wrg")
LO = sys.argv[2] if len(sys.argv) > 2 else os.environ.get("COARSE_WRG", "")
if not LO:
    raise SystemExit("usage: compare_to_1km.py <fine.wrg> <coarse.wrg>")

def mean_field(p):
    h, x, y, z, A, k, _ = read_wrg(p)
    u = A * np.array([gamma(1 + 1 / kk) if kk > 0 else np.nan for kk in k])
    return h, x, y, z, u

hh, hx, hy, hz, hu = mean_field(HI)
lh, lx, ly, lz, lu = mean_field(LO)
print(f"100 m : {hh['nx']}x{hh['ny']} @ {hh['res']} m,  {len(hu)} pts")
print(f"  1 km: {lh['nx']}x{lh['ny']} @ {lh['res']} m,  {len(lu)} pts")

# map each 100 m point onto its enclosing 1 km cell
res = lh["res"]
key_hi = ((hx - lx.min()) // res).astype(int) * 100000 + ((hy - ly.min()) // res).astype(int)
key_lo = ((lx - lx.min()) // res).astype(int) * 100000 + ((ly - ly.min()) // res).astype(int)

import collections
agg = collections.defaultdict(list)
for kk, v in zip(key_hi, hu):
    agg[kk].append(v)
lo_map = dict(zip(key_lo, lu))
common = [k for k in agg if k in lo_map and len(agg[k]) >= 50]
hi_agg = np.array([np.mean(agg[k]) for k in common])
lo_val = np.array([lo_map[k] for k in common])
sub_sd = np.array([np.std(agg[k]) for k in common])

print(f"\noverlap: {len(common)} 1 km cells "
      f"({np.mean([len(agg[k]) for k in common]):.0f} 100 m pts each)")
print(f"\nLEVEL")
print(f"  1 km  mean {lo_val.mean():6.3f} m/s")
print(f"  100 m mean {hi_agg.mean():6.3f} m/s   -> {100*(hi_agg.mean()/lo_val.mean()-1):+.2f}%")
print(f"  per-cell bias: mean {np.mean(hi_agg-lo_val):+.3f}  rms {np.sqrt(np.mean((hi_agg-lo_val)**2)):.3f} m/s")
print(f"  correlation of the two coarse-scale patterns: {np.corrcoef(hi_agg, lo_val)[0,1]:.4f}")
print(f"\nDETAIL THE 1 km RUN CANNOT SEE")
print(f"  spatial sd across 1 km cells      : {lo_val.std():.3f} m/s")
print(f"  mean sd WITHIN a 1 km cell (100 m): {sub_sd.mean():.3f} m/s")
print(f"  full 100 m field range            : {hu.min():.2f}-{hu.max():.2f} m/s")
print(f"  1 km field range (overlap)        : {lo_val.min():.2f}-{lo_val.max():.2f} m/s")
print(f"  -> sub-kilometre variance is {100*sub_sd.mean()/lo_val.std():.0f}% of the "
      f"variance the coarse run resolves")
