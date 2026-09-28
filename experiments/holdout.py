"""Spatial hold-out test.

The supervised selector optimises against the same 1 km field it is then
scored on, so its error is optimistic by construction.  If the block set works
by capturing flow REGIMES it will transfer to grid points it never saw; if it
works by fitting point-specific noise it will not.  That distinction is what
decides whether the selection carries over to a 100 m grid.

Select using a random half of the grid points, score on the held-out half.
"""
import numpy as np, pandas as pd, sys
sys.path.insert(0, "/scratch/moptis/c2wind/wsw_high/tmy")
import select_supervised as S

full_mean, full_aep = S.full_mean, S.full_aep
rng = np.random.default_rng(7)
npts = len(full_mean)
train = np.zeros(npts, bool)
train[rng.choice(npts, npts // 2, replace=False)] = True
test = ~train
print(f"{train.sum()} training points, {test.sum()} held-out points\n")


def cost_masked(sws, saep, n, mask):
    m, a = sws[mask]/n, saep[mask]/n
    fm, fa = full_mean[mask], full_aep[mask]
    fp, fap = fm/fm.mean(), fa/fa.mean()
    lvl = abs(m.mean()/fm.mean()-1) + abs(a.mean()/fa.mean()-1)
    pat = (np.sqrt((((m/m.mean())/fp-1)**2).mean())
           + np.sqrt((((a/a.mean())/fap-1)**2).mean()))
    return 100*(lvl + 2.0*pat)


def evaluate(sws, saep, n, mask):
    m, a = sws[mask]/n, saep[mask]/n
    fm, fa = full_mean[mask], full_aep[mask]
    fp, fap = fm/fm.mean(), fa/fa.mean()
    return (100*(m.mean()/fm.mean()-1), 100*(a.mean()/fa.mean()-1),
            np.corrcoef(m/m.mean(), fp)[0, 1],
            100*np.sqrt((((m/m.mean())/fp-1)**2).mean()),
            100*np.sqrt((((a/a.mean())/fap-1)**2).mean()))


def pick_masked(L, K, mask):
    B = S.blocks_of(L)
    chosen, used = [], set()
    acc = [np.zeros(npts), np.zeros(npts), 0.0]
    while len(chosen) < K:
        bj, bc = None, np.inf
        for j, b in enumerate(B):
            if j in chosen or used & b["dset"]:
                continue
            c = cost_masked(acc[0]+b["sws"], acc[1]+b["saep"], acc[2]+b["n"], mask)
            if c < bc:
                bj, bc = j, c
        if bj is None:
            break
        chosen.append(bj); used |= B[bj]["dset"]
        acc = [acc[0]+B[bj]["sws"], acc[1]+B[bj]["saep"], acc[2]+B[bj]["n"]]
    improved = True
    while improved:
        improved = False
        for pos in range(len(chosen)):
            rest = [c for c in chosen if c != chosen[pos]]
            base = [sum(B[c]["sws"] for c in rest), sum(B[c]["saep"] for c in rest),
                    sum(B[c]["n"] for c in rest)] if rest else [np.zeros(npts), np.zeros(npts), 0.0]
            busy = set().union(*[B[c]["dset"] for c in rest]) if rest else set()
            cur = chosen[pos]
            bj, bc = cur, cost_masked(base[0]+B[cur]["sws"], base[1]+B[cur]["saep"],
                                      base[2]+B[cur]["n"], mask)
            for j, b in enumerate(B):
                if j in rest or busy & b["dset"]:
                    continue
                c = cost_masked(base[0]+b["sws"], base[1]+b["saep"], base[2]+b["n"], mask)
                if c < bc-1e-12:
                    bj, bc = j, c
            if bj != cur:
                chosen[pos] = bj; improved = True
    fin = [sum(B[c]["sws"] for c in chosen), sum(B[c]["saep"] for c in chosen),
           sum(B[c]["n"] for c in chosen)]
    return fin


hdr = (f"{'selection':<16s} {'days':>5} | {'TRAIN half':>26s} | {'HELD-OUT half':>26s}")
print(hdr)
print(f"{'':<16s} {'':>5} | {'mean%':>6} {'AEP%':>6} {'pRMS%':>6} {'aRMS%':>5} | "
      f"{'mean%':>6} {'AEP%':>6} {'pRMS%':>6} {'aRMS%':>5}")
print("-"*len(hdr))
for L, K in ((2, 7), (2, 14), (3, 10), (3, 14), (2, 21)):
    fin = pick_masked(L, K, train)
    tr = evaluate(*fin, train); te = evaluate(*fin, test)
    print(f"supervised {K:2d}x{L}d{'':<2s} {K*L:5d} | {tr[0]:+6.2f} {tr[1]:+6.2f} "
          f"{tr[3]:6.2f} {tr[4]:5.2f} | {te[0]:+6.2f} {te[1]:+6.2f} {te[3]:6.2f} {te[4]:5.2f}")
