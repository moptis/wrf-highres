"""Select representative blocks from the 1 km WRF output itself.

The ERA5-space selection leaves a persistent +2..8% level bias: matching the
forcing at one ERA5 cell does not pin the domain-mean response of the nest.
But the 1 km TMY run already exists and is cheap, so the blocks can be chosen
from ITS fields instead -- removing the ERA5->WRF transfer error entirely.
"""
import numpy as np, pandas as pd, sys
sys.path.insert(0, "/scratch/moptis/c2wind/wsw_high/tmy")
from sampler2 import select, prep, target_stats

d = np.load("/scratch/moptis/c2wind/wsw_high/tmy/wrf_tmy_100m.npz", allow_pickle=True)
t = pd.to_datetime([s.replace("_", " ") for s in d["time"]]).tz_convert(None)
ws, wd, elev = d["ws"], d["wd"], d["elev"]
day = t.normalize()

# domain-aggregate series used as the selection features
u = -np.sin(np.deg2rad(wd)) * ws
v = -np.cos(np.deg2rad(wd)) * ws
dom = pd.DataFrame(
    {"ws": ws.mean(1),
     "wd": (np.rad2deg(np.arctan2(-u.mean(1), -v.mean(1))) + 360) % 360},
    index=t).sort_index()

full_mean = ws.mean(0); full_pat = full_mean / full_mean.mean()
PC_U = np.arange(0, 31.0); PC_P = np.clip((PC_U**3)/(12.0**3), 0, 1)*(PC_U >= 3)*(PC_U <= 25)
full_aep = np.interp(ws, PC_U, PC_P).mean(0); full_aep_pat = full_aep/full_aep.mean()

P = prep(dom); tgt = target_stats(P)
print(f"{'selection':<18s} {'days':>5} {'cost_d':>7} | {'mean%':>6} {'AEP%':>7} | "
      f"{'patt r':>7} {'pattRMS%':>8} {'AEPrms%':>8}")
print("-"*74)
for L, K in ((2, 7), (2, 14), (3, 10), (3, 14), (2, 21), (3, 20), (3, 30)):
    sub, spans = select(dom, L, K, tgt, P=P)
    days = pd.DatetimeIndex(np.unique(sub.index.normalize()))
    m = day.isin(days)
    if m.sum() < 100:
        continue
    s = ws[m].mean(0); pat = s/s.mean()
    a = np.interp(ws[m], PC_U, PC_P).mean(0); apat = a/a.mean()
    print(f"greedy {K:2d} x {L}d{'':<7s} {m.sum()//144:5d} {K*(L+0.25):7.1f} | "
          f"{100*(s.mean()/full_mean.mean()-1):+6.2f} "
          f"{100*(a.mean()/full_aep.mean()-1):+7.2f} | "
          f"{np.corrcoef(pat, full_pat)[0,1]:7.4f} "
          f"{100*np.sqrt(((pat/full_pat-1)**2).mean()):8.2f} "
          f"{100*np.sqrt(((apat/full_aep_pat-1)**2).mean()):8.2f}")

sub, spans = select(dom, 3, 14, tgt, P=P)
print("\nrecommended 14 x 3d blocks selected on 1 km WRF fields:")
for a_, b_ in spans:
    print(f"    {a_.date()} .. {b_.date()}")
