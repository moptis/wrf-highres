"""Compare candidate sampling strategies against the long-term ERA5 record."""
import numpy as np, pandas as pd, sys
sys.path.insert(0, "/scratch/moptis/c2wind/wsw_high/tmy")
from sampling import (load_era5, histograms, distance, greedy_select,
                      emd_tmy_months, NSECT, SPEED_EDGES)

def weibull(ws):
    """Method-of-moments Weibull fit (adequate for a bias comparison)."""
    m, s = ws.mean(), ws.std()
    k = (s / m) ** -1.086
    return m / np.exp(np.log(1 + 1 / k) * 0 + __import__("math").lgamma(1 + 1 / k)), k

def metrics(sub, ref):
    """WRG-relevant error of `sub` against the long-term record `ref`."""
    A_s, k_s = weibull(sub["ws"].values); A_r, k_r = weibull(ref["ws"].values)
    sect = lambda d: (((d["wd"].values + 180.0/NSECT) % 360)//(360/NSECT)).astype(int)
    fs, fr = np.bincount(sect(sub), minlength=NSECT)/len(sub), np.bincount(sect(ref), minlength=NSECT)/len(ref)
    es = np.bincount(sect(sub), weights=sub["ws"].values**3, minlength=NSECT)
    er = np.bincount(sect(ref), weights=ref["ws"].values**3, minlength=NSECT)
    es, er = es/es.sum(), er/er.sum()
    return dict(
        days=len(sub)/24.0,
        ws_bias=100*(sub["ws"].mean()/ref["ws"].mean()-1),
        energy_bias=100*((sub["ws"]**3).mean()/(ref["ws"]**3).mean()-1),
        A_bias=100*(A_s/A_r-1), k_bias=100*(k_s/k_r-1),
        sect_freq_mae=100*np.abs(fs-fr).mean(),
        sect_energy_mae=100*np.abs(es-er).mean(),
        sect_energy_max=100*np.abs(es-er).max(),
    )

def show(name, sub, ref, extra=""):
    m = metrics(sub, ref)
    print(f"{name:<34s} {m['days']:6.0f} {m['ws_bias']:+7.2f} {m['energy_bias']:+8.2f} "
          f"{m['A_bias']:+7.2f} {m['k_bias']:+7.2f} {m['sect_freq_mae']:8.2f} "
          f"{m['sect_energy_mae']:9.2f} {m['sect_energy_max']:8.2f}  {extra}")
    return m

if __name__ == "__main__":
    df = load_era5()
    print(f"ERA5 record: {df.index[0].date()} .. {df.index[-1].date()}  "
          f"({len(df)} h, {len(df)/8766:.1f} yr)\n")
    target = histograms(df)

    hdr = (f"{'strategy':<34s} {'days':>6} {'ws%':>7} {'energy%':>8} {'A%':>7} "
           f"{'k%':>7} {'sectF':>8} {'sectE':>9} {'sectEmx':>8}")
    print(hdr); print("-"*len(hdr))
    print("  (bias vs the 24-yr record; sectF/sectE are mean abs errors in "
          "sector frequency / energy share, %pts)\n")

    tmy, picks = emd_tmy_months(df)
    show("current: 12-month EMD TMY", tmy, df,
         " ".join(f"{y}-{m:02d}" for y, m in picks[:4]) + " ...")

    rng = np.random.default_rng(0)
    for L, K in ((3, 10), (5, 6)):
        rows = []
        for t in range(40):
            days = np.array(sorted(df.index.normalize().unique()))
            starts = rng.choice(len(days)-L, K, replace=False)
            m = np.zeros(len(df), bool)
            for s in starts:
                m |= (df.index.normalize() >= days[s]) & (df.index.normalize() <= days[s+L-1])
            rows.append(metrics(df[m], df))
        avg = {k: np.mean([r[k] for r in rows]) for k in rows[0]}
        ab = {k: np.mean([abs(r[k]) for r in rows]) for k in rows[0]}
        print(f"{'random '+str(K)+'x'+str(L)+'d (40 draws, mean |err|)':<34s} "
              f"{avg['days']:6.0f} {ab['ws_bias']:7.2f} {ab['energy_bias']:8.2f} "
              f"{ab['A_bias']:7.2f} {ab['k_bias']:7.2f} {ab['sect_freq_mae']:8.2f} "
              f"{ab['sect_energy_mae']:9.2f} {ab['sect_energy_max']:8.2f}")

    print()
    for L, K in ((3, 10), (5, 6), (3, 14), (5, 10)):
        sub, spans = greedy_select(df, target, L, K)
        show(f"greedy {K} x {L}d blocks", sub, df,
             f"{len(spans)} blocks")
    print()
    sub, spans = greedy_select(df, target, 3, 10)
    print("greedy 10 x 3d selected blocks:")
    for a, b in spans:
        print(f"    {a.date()} .. {b.date()}")
