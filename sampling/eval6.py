"""Cost-matched geometry comparison.

Days simulated is not the cost -- each block also pays spin-up that gets
discarded.  Short blocks buy degrees of freedom but pay that toll more often,
so the honest comparison holds COST fixed, not days.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from wrfhr import cfg, path

ROOT = cfg["CASE_ROOT"]

import sys
import numpy as np
sys.path.insert(0, path("CASE_ROOT", "tmy"))
from sampler3 import load, bins, stack, build_blocks, design, select
from eval3 import hists, ref_hists, metrics, HDR, show

if __name__ == "__main__":
    df = load(); B = bins(df)
    tr = df.index.year < 2012
    dtr, dte = df[tr], df[~tr]
    Btr, Bte = bins(dtr), bins(dte)
    Rtr, Rte = ref_hists(Btr, np.arange(len(dtr))), ref_hists(Bte, np.arange(len(dte)))
    ttr = stack(Rtr[:6] + [np.ones(3)])
    cache = {}
    print(HDR.replace("ESS", "days ESS")); print("-" * (len(HDR) + 5))
    show("target drift (floor)", Rtr, Rte)

    for spin in (0.25, 0.5):
        for budget in (50.0,):
            print(f"\nspin-up {spin*24:.0f} h, budget {budget:.0f} day-equivalents")
            for L in (1, 2, 3, 5):
                K = int(budget // (L + spin))
                if K < 4:
                    continue
                if L not in cache:
                    bl = build_blocks(dtr, Btr, L)
                    cache[L] = (bl, design(bl, Btr, Rtr[6]))
                blocks, A = cache[L]
                ch, w, _ = select(blocks, A, ttr, K, weighted=True, wmax=6.0 / K)
                m = metrics(hists(Btr, [blocks[j]["rows"] for j in ch], w), Rte)
                print(f"  wt {K:2d}x{L}d{'':13s} {m['roseF']:6.2f} {m['roseE']:6.2f} "
                      f"{m['joint']:6.2f} {m['secWS']:6.2f} {m['stab']:6.2f} "
                      f"{m['dirstab']:7.2f} {m['month']:6.2f} {m['hour']:6.2f} "
                      f"{m['ws']:+6.2f} {m['en']:+6.2f} {K*L:4d} "
                      f"{1/np.sum(w**2):5.1f}")
