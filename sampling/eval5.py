"""Is greedy+swap good enough?  Do the weight bounds overfit?  Does reweighting
the objective fix the weakest metric (the direction x stability joint)?"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from wrfhr import cfg, path

ROOT = cfg["CASE_ROOT"]

import sys
import numpy as np
sys.path.insert(0, path("CASE_ROOT", "tmy"))
import sampler as S
from sampler import load, bins, stack, build_blocks, design, select, solve_weights
from eval3 import hists, ref_hists, metrics, HDR, show


def anneal(blocks, A, t, K, chosen, wmax, iters=4000, seed=0):
    """Simulated annealing over the block set, re-solving weights each move."""
    rng = np.random.default_rng(seed)
    cur = list(chosen)
    used = set().union(*[blocks[c]["dset"] for c in cur])
    best_w, best_d = solve_weights(A[:, cur], t, wmax)
    cur_d, best = best_d, list(cur)
    T0, T1 = 0.05 * best_d, 1e-4 * best_d
    for it in range(iters):
        T = T0 * (T1 / T0) ** (it / iters)
        pos = int(rng.integers(len(cur)))
        rest = [c for c in cur if c != cur[pos]]
        busy = set().union(*[blocks[c]["dset"] for c in rest]) if rest else set()
        j = int(rng.integers(len(blocks)))
        if j in rest or (busy & blocks[j]["dset"]):
            continue
        cand = rest + [j]
        _, d = solve_weights(A[:, cand], t, wmax)
        if d < cur_d or rng.random() < np.exp(-(d - cur_d) / max(T, 1e-12)):
            cur, cur_d = cand, d
            used = set().union(*[blocks[c]["dset"] for c in cur])
            if d < best_d:
                best, best_d = list(cur), d
    return best, best_d


if __name__ == "__main__":
    df = load(); B = bins(df)
    tr = df.index.year < 2012
    dtr, dte = df[tr], df[~tr]
    Btr, Bte = bins(dtr), bins(dte)
    Rtr, Rte = ref_hists(Btr, np.arange(len(dtr))), ref_hists(Bte, np.arange(len(dte)))
    ttr = stack(Rtr[:6] + [np.ones(3)])
    L, K = 1, 40
    blocks = build_blocks(dtr, Btr, L)
    A = design(blocks, Btr, Rtr[6])
    print(f"{len(blocks)} candidate {L}-day blocks, choose {K}\n")
    print(HDR); print("-" * len(HDR))
    show("target drift (floor)", Rtr, Rte)

    ch, w, d0 = select(blocks, A, ttr, K, weighted=True)
    show("greedy+swap", hists(Btr, [blocks[j]["rows"] for j in ch], w), Rte, 1/np.sum(w**2))
    sa, dsa = anneal(blocks, A, ttr, K, ch, 3.0 / K)
    wsa, _ = solve_weights(A[:, sa], ttr, 3.0 / K); wsa /= wsa.sum()
    show("  + annealing", hists(Btr, [blocks[j]["rows"] for j in sa], wsa), Rte,
         1/np.sum(wsa**2))
    print(f"{'':26s}   objective {d0:.4f} -> {dsa:.4f}")

    print("\nweight bound (overfitting check)")
    for mult in (1.5, 3.0, 6.0, 20.0):
        ch, w, _ = select(blocks, A, ttr, K, weighted=True, wmax=mult / K)
        show(f"  wmax = {mult:4.1f}/K", hists(Btr, [blocks[j]["rows"] for j in ch], w),
             Rte, 1/np.sum(w**2))

    print("\nobjective reweighting (dir x stab is the weakest metric)")
    base = list(S.GROUPS)
    for label, gw in (("baseline", None),
                      ("dir*stab 1.0 -> 3.0", {2: 3.0}),
                      ("dir*stab 3.0, roseF 5.0", {0: 5.0, 2: 3.0})):
        S.GROUPS = [(n, gw.get(i, w) if gw else w) for i, (n, w) in enumerate(base)]
        A2 = design(blocks, Btr, Rtr[6])
        t2 = stack(Rtr[:6] + [np.ones(3)])
        ch, w, _ = select(blocks, A2, t2, K, weighted=True)
        show(f"  {label}", hists(Btr, [blocks[j]["rows"] for j in ch], w), Rte,
             1/np.sum(w**2))
    S.GROUPS = base
