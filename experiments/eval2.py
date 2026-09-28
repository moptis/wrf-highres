"""Block-geometry sweep + out-of-sample check."""
import numpy as np, pandas as pd, sys, math
sys.path.insert(0, "/scratch/moptis/c2wind/wsw_high/tmy")
from sampling import load_era5, emd_tmy_months
from sampler2 import select, prep, target_stats, NSECT

SPINUP = 0.25          # days of spin-up discarded per block (6 h)

def wbl(ws):
    m, s = ws.mean(), ws.std()
    k = (s / m) ** -1.086
    return m / math.exp(math.lgamma(1 + 1 / k)), k

def metrics(sub, ref):
    A_s, k_s = wbl(sub["ws"].values); A_r, k_r = wbl(ref["ws"].values)
    sc = lambda d: (((d["wd"].values + 180.0/NSECT) % 360)//(360/NSECT)).astype(int)
    es = np.bincount(sc(sub), weights=sub["ws"].values**3, minlength=NSECT)
    er = np.bincount(sc(ref), weights=ref["ws"].values**3, minlength=NSECT)
    es, er = es/es.sum(), er/er.sum()
    fs = np.bincount(sc(sub), minlength=NSECT)/len(sub)
    fr = np.bincount(sc(ref), minlength=NSECT)/len(ref)
    return dict(ws=100*(sub["ws"].mean()/ref["ws"].mean()-1),
                en=100*((sub["ws"]**3).mean()/(ref["ws"]**3).mean()-1),
                A=100*(A_s/A_r-1), k=100*(k_s/k_r-1),
                sF=100*np.abs(fs-fr).mean(), sE=100*np.abs(es-er).mean(),
                sEx=100*np.abs(es-er).max())

def row(label, m, days, cost, extra=""):
    print(f"{label:<26s} {days:5.0f} {cost:7.1f} {m['ws']:+7.2f} {m['en']:+8.2f} "
          f"{m['A']:+6.2f} {m['k']:+6.2f} {m['sF']:6.2f} {m['sE']:6.2f} {m['sEx']:7.2f} {extra}")

if __name__ == "__main__":
    df = load_era5()
    P = prep(df); tgt = target_stats(P)
    hdr = (f"{'strategy':<26s} {'days':>5} {'cost_d':>7} {'ws%':>7} {'energy%':>8} "
           f"{'A%':>6} {'k%':>6} {'sectF':>6} {'sectE':>6} {'sectEmx':>7}")
    print("IN-SAMPLE (target = full 24-yr record)\n"); print(hdr); print("-"*len(hdr))

    tmy, _ = emd_tmy_months(df)
    row("current 12-month TMY", metrics(tmy, df), len(tmy)/24, 122*(3+SPINUP))

    best = []
    for L in (1, 2, 3, 4, 5, 7):
        for K in (6, 10, 14, 20):
            if not (24 <= K*L <= 50):
                continue
            sub, spans = select(df, L, K, tgt, P=P)
            m = metrics(sub, df)
            cost = K*(L+SPINUP)
            row(f"greedy+swap {K:2d} x {L}d", m, K*L, cost)
            best.append((cost, abs(m['en']), L, K, m, spans))

    print("\nOUT-OF-SAMPLE (select on even years, score against odd years)\n")
    print(hdr); print("-"*len(hdr))
    ev = df[df.index.year % 2 == 0]; od = df[df.index.year % 2 == 1]
    Pe = prep(ev); tge = target_stats(Pe)
    tmy_e, _ = emd_tmy_months(ev)
    row("current 12-month TMY", metrics(tmy_e, od), len(tmy_e)/24, 122*(3+SPINUP))
    for L, K in ((3, 10), (3, 14), (2, 14), (2, 20), (5, 6)):
        sub, _ = select(ev, L, K, tge, P=Pe)
        row(f"greedy+swap {K:2d} x {L}d", metrics(sub, od), K*L, K*(L+SPINUP))

    print("\nrecommended selection (best in-sample energy match near 30-45 d):")
    best.sort(key=lambda b: (b[1], b[0]))
    cost, en, L, K, m, spans = best[0]
    print(f"  {K} x {L}d  = {K*L} days, {cost:.1f} day-equivalents incl. spin-up")
    for a, b in spans:
        print(f"    {a.date()} .. {b.date()}")
