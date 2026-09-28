"""Choose blocks by directly optimising against the 1 km TMY field.

The 1 km TMY run already exists, so the block set can be scored on exactly the
quantities the WRG cares about -- resource level AND the normalised spatial
pattern -- instead of on an ERA5 proxy.  Only then are those days rerun at
100 m.  The assumption reduces to "a block set that reproduces the 1 km
pattern also reproduces the 100 m pattern", which is far weaker than assuming
the ERA5 forcing distribution carries all the way down.

Per-block sums are precomputed, so scoring a candidate set is a few vector adds.
"""
import numpy as np, pandas as pd, sys

d = np.load("/scratch/moptis/c2wind/wsw_high/tmy/wrf_tmy_100m.npz", allow_pickle=True)
t = pd.to_datetime([s.replace("_", " ") for s in d["time"]]).tz_convert(None)
order = np.argsort(t.values)
t, ws = t[order], d["ws"][order]
day = t.normalize()

PC_U = np.arange(0, 31.0)
PC_P = np.clip((PC_U**3)/(12.0**3), 0, 1)*(PC_U >= 3)*(PC_U <= 25)
aep_t = np.interp(ws, PC_U, PC_P)

full_mean = ws.mean(0); full_pat = full_mean/full_mean.mean()
full_aep = aep_t.mean(0); full_aep_pat = full_aep/full_aep.mean()

days = pd.DatetimeIndex(np.unique(day))
ordi = np.array([x.toordinal() for x in days])
rows_by_day = {i: np.where(day == days[i])[0] for i in range(len(days))}


def blocks_of(L):
    out = []
    for i in range(len(days)-L+1):
        if ordi[i+L-1]-ordi[i] != L-1:
            continue
        r = np.concatenate([rows_by_day[j] for j in range(i, i+L)])
        out.append(dict(start=days[i], end=days[i+L-1],
                        sws=ws[r].sum(0), saep=aep_t[r].sum(0), n=len(r),
                        dset=set(ordi[i:i+L].tolist())))
    return out


def cost(sws, saep, n):
    """Level error + pattern error, both in percent, pattern weighted 2x
    because the terrain signal is what the high-res run is for."""
    m = sws/n; a = saep/n
    lvl = abs(m.mean()/full_mean.mean()-1) + abs(a.mean()/full_aep.mean()-1)
    pat = (np.sqrt((((m/m.mean())/full_pat-1)**2).mean())
           + np.sqrt((((a/a.mean())/full_aep_pat-1)**2).mean()))
    return 100*(lvl + 2.0*pat)


def pick(L, K, restarts=6, seed=0):
    B = blocks_of(L)
    rng = np.random.default_rng(seed)
    best_overall = None
    for rs in range(restarts):
        chosen = [] if rs == 0 else [int(rng.integers(len(B)))]
        used = set() if rs == 0 else set(B[chosen[0]]["dset"])
        acc = [np.zeros_like(full_mean), np.zeros_like(full_aep), 0.0]
        for c in chosen:
            acc = [acc[0]+B[c]["sws"], acc[1]+B[c]["saep"], acc[2]+B[c]["n"]]
        while len(chosen) < K:
            bj, bc = None, np.inf
            for j, b in enumerate(B):
                if j in chosen or used & b["dset"]:
                    continue
                c = cost(acc[0]+b["sws"], acc[1]+b["saep"], acc[2]+b["n"])
                if c < bc:
                    bj, bc = j, c
            if bj is None:
                break
            chosen.append(bj); used |= B[bj]["dset"]
            acc = [acc[0]+B[bj]["sws"], acc[1]+B[bj]["saep"], acc[2]+B[bj]["n"]]
        # swap refinement
        improved = True
        while improved:
            improved = False
            for pos in range(len(chosen)):
                rest = [c for c in chosen if c != chosen[pos]]
                base = [sum(B[c]["sws"] for c in rest), sum(B[c]["saep"] for c in rest),
                        sum(B[c]["n"] for c in rest)] if rest else [0, 0, 0.0]
                busy = set().union(*[B[c]["dset"] for c in rest]) if rest else set()
                cur = chosen[pos]
                bj, bc = cur, cost(base[0]+B[cur]["sws"], base[1]+B[cur]["saep"], base[2]+B[cur]["n"])
                for j, b in enumerate(B):
                    if j in rest or busy & b["dset"]:
                        continue
                    c = cost(base[0]+b["sws"], base[1]+b["saep"], base[2]+b["n"])
                    if c < bc-1e-12:
                        bj, bc = j, c
                if bj != cur:
                    chosen[pos] = bj; improved = True
        fin = [sum(B[c]["sws"] for c in chosen), sum(B[c]["saep"] for c in chosen),
               sum(B[c]["n"] for c in chosen)]
        c = cost(*fin)
        if best_overall is None or c < best_overall[0]:
            best_overall = (c, list(chosen), fin, B)
    return best_overall


if __name__ == "__main__":
    print(f"{'selection':<16s} {'days':>5} {'cost_d':>7} | {'mean%':>6} {'AEP%':>7} | "
          f"{'patt r':>7} {'pattRMS%':>8} {'AEPrms%':>8}")
    print("-"*72)
    keep = {}
    for L, K in ((2, 7), (2, 10), (2, 14), (3, 10), (2, 21), (3, 14), (3, 20)):
        c, chosen, fin, B = pick(L, K)
        m, a = fin[0]/fin[2], fin[1]/fin[2]
        pat, apat = m/m.mean(), a/a.mean()
        print(f"supervised {K:2d}x{L}d{'':<2s} {K*L:5d} {K*(L+0.25):7.1f} | "
              f"{100*(m.mean()/full_mean.mean()-1):+6.2f} "
              f"{100*(a.mean()/full_aep.mean()-1):+7.2f} | "
              f"{np.corrcoef(pat, full_pat)[0,1]:7.4f} "
              f"{100*np.sqrt(((pat/full_pat-1)**2).mean()):8.2f} "
              f"{100*np.sqrt(((apat/full_aep_pat-1)**2).mean()):8.2f}")
        keep[(L, K)] = (chosen, B)

    chosen, B = keep[(2, 14)]
    print("\n14 x 2d (28 days) selected blocks:")
    for j in sorted(chosen, key=lambda j: B[j]["start"]):
        print(f"    {B[j]['start'].date()} .. {B[j]['end'].date()}")
