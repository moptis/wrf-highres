"""How does WRG fidelity scale with sample size, and which part of the answer
is fragile -- the resource LEVEL or the terrain PATTERN?"""
import numpy as np, pandas as pd, sys
sys.path.insert(0, "/scratch/moptis/c2wind/wsw_high/tmy")
from sampling import load_era5
from sampler2 import select, prep, target_stats

d = np.load("/scratch/moptis/c2wind/wsw_high/tmy/wrf_tmy_100m.npz", allow_pickle=True)
t = pd.to_datetime([s.replace("_", " ") for s in d["time"]]).tz_convert(None)
ws, elev = d["ws"], d["elev"]
day = t.normalize()

full_mean = ws.mean(0)
full_pat = full_mean / full_mean.mean()
PC_U = np.arange(0, 31.0); PC_P = np.clip((PC_U**3)/(12.0**3), 0, 1)*(PC_U >= 3)*(PC_U <= 25)
full_aep = np.interp(ws, PC_U, PC_P).mean(0)
full_aep_pat = full_aep / full_aep.mean()

era = load_era5()
tmy_days = pd.DatetimeIndex(np.unique(day))
era_tmy = era[era.index.normalize().isin(tmy_days)]
P = prep(era_tmy); tgt = target_stats(P)

print(f"{'sample':<16s} {'days':>5} {'cost_d':>7} | {'LEVEL':>14s} | {'PATTERN (terrain signal)':>30s}")
print(f"{'':<16s} {'':>5} {'':>7} | {'mean%':>6} {'AEP%':>7} | {'r':>7} {'RMS%':>7} "
      f"{'p95%':>7} {'AEPr':>7} {'AEPrms%':>8}")
print("-"*96)

rng = np.random.default_rng(3)
for L, K in ((2, 7), (2, 14), (3, 10), (3, 14), (2, 30), (3, 20), (3, 30), (5, 24)):
    sub, _ = select(era_tmy, L, K, tgt, P=P)
    days = pd.DatetimeIndex(np.unique(sub.index.normalize()))
    m = day.isin(days)
    if m.sum() < 100:
        continue
    s = ws[m].mean(0); pat = s / s.mean()
    a = np.interp(ws[m], PC_U, PC_P).mean(0); apat = a / a.mean()
    err = 100*(pat/full_pat - 1)
    print(f"greedy {K:2d} x {L}d{'':<5s} {m.sum()//144:5d} {K*(L+0.25):7.1f} | "
          f"{100*(s.mean()/full_mean.mean()-1):+6.2f} {100*(a.mean()/full_aep.mean()-1):+7.2f} | "
          f"{np.corrcoef(pat, full_pat)[0,1]:7.4f} {np.sqrt((err**2).mean()):7.2f} "
          f"{np.percentile(np.abs(err),95):7.2f} "
          f"{np.corrcoef(apat, full_aep_pat)[0,1]:7.4f} "
          f"{100*np.sqrt(((apat/full_aep_pat-1)**2).mean()):8.2f}")

print("\nper-point AEP error distribution, greedy 14 x 3d (42 d):")
sub, _ = select(era_tmy, 3, 14, tgt, P=P)
m = day.isin(pd.DatetimeIndex(np.unique(sub.index.normalize())))
a = np.interp(ws[m], PC_U, PC_P).mean(0)
e = 100*(a/full_aep - 1)
for q in (5, 25, 50, 75, 95, 100):
    print(f"   p{q:<3d} {np.percentile(e, q):+7.2f}%")
print(f"   correlation of |error| with elevation: {np.corrcoef(np.abs(e), elev)[0,1]:+.3f}")
