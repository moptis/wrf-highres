"""Does matching the ERA5 forcing distribution preserve the DOWNSCALED WRG?

Uses the existing 1 km TMY run as ground truth: 366 days of 100 m wind at 456
grid points.  Subsample those days with the ERA5-space block sampler, recompute
the WRG-relevant statistics, and compare against all 366 days.

The metric that matters is not the domain mean -- it is the spatial pattern of
the resource, since capturing terrain effects is the entire reason for running
at high resolution.
"""
import numpy as np, pandas as pd, sys, math
sys.path.insert(0, "/scratch/moptis/c2wind/wsw_high/tmy")
from sampling import load_era5
from sampler2 import select, prep, target_stats, NSECT

NPZ = "/scratch/moptis/c2wind/wsw_high/tmy/wrf_tmy_100m.npz"

# generic IEC-II-ish power curve, only used as an AEP weighting
PC_U = np.arange(0, 31.0)
PC_P = np.clip((PC_U**3) / (12.0**3), 0, 1) * (PC_U >= 3) * (PC_U <= 25)


def wrf_stats(ws, wd):
    """Per-grid-point statistics over the supplied timestamps."""
    return dict(
        mean=ws.mean(0),
        energy=(ws ** 3).mean(0),
        aep=np.interp(ws, PC_U, PC_P).mean(0),
    )


def compare(sub, full, label, extra=""):
    out = {}
    for key in ("mean", "energy", "aep"):
        r = 100 * (sub[key] / full[key] - 1)
        out[key] = r
    # spatial pattern: normalise out the domain mean, then see if the terrain
    # signal survives
    ps, pf = sub["mean"] / sub["mean"].mean(), full["mean"] / full["mean"].mean()
    corr = np.corrcoef(ps, pf)[0, 1]
    rms = 100 * np.sqrt(((ps - pf) ** 2).mean())
    print(f"{label:<26s} {out['mean'].mean():+7.2f} {np.abs(out['mean']).max():7.2f} "
          f"{out['energy'].mean():+8.2f} {out['aep'].mean():+7.2f} "
          f"{np.abs(out['aep']).max():7.2f} {corr:8.4f} {rms:7.2f}  {extra}")
    return corr, rms


if __name__ == "__main__":
    d = np.load(NPZ, allow_pickle=True)
    # WRF stamps are tz-aware UTC, ERA5 is naive UTC -- align them
    t = pd.to_datetime([s.replace("_", " ") for s in d["time"]]).tz_convert(None)
    ws, wd = d["ws"], d["wd"]
    print(f"WRF TMY: {len(t)} times, {ws.shape[1]} points, "
          f"{t[0].date()} .. {t[-1].date()}, {len(np.unique(t.normalize()))} days")

    full = wrf_stats(ws, wd)
    print(f"domain mean 100 m wind: {full['mean'].mean():.3f} m/s   "
          f"spatial range {full['mean'].min():.2f}-{full['mean'].max():.2f} m/s\n")

    # ERA5 restricted to the TMY's own days -> selection space
    era = load_era5()
    tmy_days = pd.DatetimeIndex(np.unique(t.normalize()))
    era_tmy = era[era.index.normalize().isin(tmy_days)]
    print(f"ERA5 hours on TMY days: {len(era_tmy)}\n")
    P = prep(era_tmy); tgt = target_stats(P)

    wrf_day = t.normalize()
    hdr = (f"{'selection':<26s} {'mean%':>7} {'|mx|%':>7} {'energy%':>8} "
           f"{'AEP%':>7} {'|mx|%':>7} {'patt r':>8} {'pattRMS%':>7}")
    print(hdr); print("-" * len(hdr))

    rng = np.random.default_rng(1)
    for L, K in ((2, 14), (3, 10), (3, 14), (5, 6)):
        sub_era, spans = select(era_tmy, L, K, tgt, P=P)
        days = pd.DatetimeIndex(np.unique(sub_era.index.normalize()))
        m = wrf_day.isin(days)
        compare(wrf_stats(ws[m], wd[m]), full, f"greedy {K} x {L}d ({m.sum()//144} d)")

    # control: random blocks of the same size
    for L, K in ((2, 14), (3, 10)):
        accum = []
        for _ in range(15):
            starts = rng.choice(len(tmy_days) - L, K, replace=False)
            days = pd.DatetimeIndex(sorted({tmy_days[s + i] for s in starts for i in range(L)}))
            m = wrf_day.isin(days)
            if m.sum() < 100:
                continue
            s = wrf_stats(ws[m], wd[m])
            ps, pf = s["mean"] / s["mean"].mean(), full["mean"] / full["mean"].mean()
            accum.append((100 * (s["mean"] / full["mean"] - 1).mean(),
                          100 * (s["energy"] / full["energy"] - 1).mean(),
                          100 * (s["aep"] / full["aep"] - 1).mean(),
                          np.corrcoef(ps, pf)[0, 1],
                          100 * np.sqrt(((ps - pf) ** 2).mean())))
        a = np.abs(np.array(accum)).mean(0)
        r = np.array(accum)[:, 3].mean()
        print(f"{'random '+str(K)+'x'+str(L)+'d (15 draws,|e|)':<26s} {a[0]:7.2f} {'':>7} "
              f"{a[1]:8.2f} {a[2]:7.2f} {'':>7} {r:8.4f} {a[4]:7.2f}")
