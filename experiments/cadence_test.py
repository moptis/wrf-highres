"""Does 10-minute output buy anything over hourly for WRG statistics?

Sample COUNT is not the question -- sample INDEPENDENCE is.  Decimate the
10-minute 1 km TMY to hourly and 3-hourly and see whether the per-point WRG
statistics actually move, alongside the autocorrelation that explains why.
"""
import numpy as np, pandas as pd

d = np.load("/scratch/moptis/c2wind/wsw_high/tmy/wrf_tmy_100m.npz", allow_pickle=True)
t = pd.to_datetime([s.replace("_", " ") for s in d["time"]]).tz_convert(None)
o = np.argsort(t.values)
t, ws, wd = t[o], d["ws"][o], d["wd"][o]
NS = 12

# ---- autocorrelation, within contiguous 10-min segments only
gap = np.diff(t.values).astype("timedelta64[m]").astype(int)
brk = np.where(gap != 10)[0]
seg = np.split(np.arange(len(t)), brk + 1)
seg = [s for s in seg if len(s) > 2000]
print(f"{len(seg)} contiguous segments, longest {max(len(s) for s in seg)} steps "
      f"({max(len(s) for s in seg)*10/1440:.0f} days)\n")

lags = np.arange(0, 19)
acf = np.zeros(len(lags))
for k, lag in enumerate(lags):
    num = den = 0.0
    for s in seg:
        a = ws[s]
        a = a - a.mean(0)
        if lag == 0:
            num += (a * a).sum(); den += (a * a).sum()
        else:
            num += (a[:-lag] * a[lag:]).sum(); den += (a * a).sum()
    acf[k] = num / den
print("lag-autocorrelation of 100 m wind speed:")
for k in (1, 3, 6, 12, 18):
    print(f"  {k*10:3d} min  r = {acf[k]:.3f}")
tau = 10 * (1 + 2 * acf[1:].sum())
print(f"\nintegral timescale ~ {tau:.0f} min -> samples closer than that are "
      f"largely redundant")

# ---- does decimation actually change the WRG statistics?
def stats(step):
    s, w = ws[::step], wd[::step]
    sect = (((w + 180.0 / NS) % 360) // (360 / NS)).astype(int)
    pt = np.arange(s.shape[1]) * NS
    idx = (pt[None, :] + sect).ravel()
    f = np.bincount(idx, minlength=s.shape[1] * NS).reshape(-1, NS).astype(float)
    e = np.bincount(idx, weights=(s ** 3).ravel(),
                    minlength=s.shape[1] * NS).reshape(-1, NS)
    f /= f.sum(1, keepdims=True); e /= e.sum(1, keepdims=True)
    return s.mean(0), (s ** 3).mean(0), f, e, s.shape[0]

m0, e0, f0, en0, n0 = stats(1)
print(f"\n{'cadence':<12s} {'samples':>9} {'mean%':>7} {'energy%':>8} "
      f"{'roseF TV':>9} {'roseE TV':>9}")
print("-" * 58)
for step, lab in ((1, "10 min"), (3, "30 min"), (6, "hourly"), (18, "3-hourly")):
    m, e, f, en, n = stats(step)
    print(f"{lab:<12s} {n:>9d} {100*(m.mean()/m0.mean()-1):+7.3f} "
          f"{100*(e.mean()/e0.mean()-1):+8.3f} "
          f"{50*np.abs(f-f0).sum(1).mean():9.3f} {50*np.abs(en-en0).sum(1).mean():9.3f}")
print("\nTV in %, averaged over the 456 grid points, vs the full 10-min record.")
print("For scale: block-sampling error is roseF ~1.7 and the 24-yr noise floor ~1.3")
