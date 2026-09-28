"""Block-geometry sweep + out-of-sample validation."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from wrfhr import cfg, path

ROOT = cfg["CASE_ROOT"]

import sys, time
import numpy as np, pandas as pd
sys.path.insert(0, path("CASE_ROOT", "tmy"))
from sampler3 import (load, bins, featurise, stack, build_blocks, design, select)
from eval3 import hists, ref_hists, metrics, HDR, show

SPINUP = 0.25

if __name__ == "__main__":
    df = load(); B = bins(df)
    R = ref_hists(B, np.arange(len(df)))
    ref_sc = R[6].copy()
    t = stack(R[:6] + [np.ones(3)])

    print("BLOCK GEOMETRY at a ~40-day budget (in-sample)\n")
    print(HDR.replace("method", "geometry").replace("ESS", "cost_d ESS"))
    print("-" * (len(HDR) + 7))
    cache = {}
    for L, K in ((1, 40), (2, 20), (3, 14), (5, 8), (1, 60), (2, 30), (3, 20)):
        if L not in cache:
            bl = build_blocks(df, B, L)
            cache[L] = (bl, design(bl, B, ref_sc))
        blocks, A = cache[L]
        for wt, tag in ((False, "eq"), (True, "wt")):
            ch, w, d = select(blocks, A, t, K, weighted=wt)
            ess = 1.0 / np.sum(w ** 2)
            m = metrics(hists(B, [blocks[j]["rows"] for j in ch], w), R)
            print(f"{tag} {K:2d}x{L}d ({K*L:3d}d){'':6s} {m['roseF']:6.2f} {m['roseE']:6.2f} "
                  f"{m['joint']:6.2f} {m['secWS']:6.2f} {m['stab']:6.2f} {m['dirstab']:7.2f} "
                  f"{m['month']:6.2f} {m['hour']:6.2f} {m['ws']:+6.2f} {m['en']:+6.2f} "
                  f"{K*(L+SPINUP):6.1f} {ess:5.1f}")

    print("\n\nOUT-OF-SAMPLE: select on 2000-2011, score against 2012-2024\n")
    tr = df.index.year < 2012
    dtr, dte = df[tr], df[~tr]
    Btr, Bte = bins(dtr), bins(dte)
    Rtr = ref_hists(Btr, np.arange(len(dtr)))
    Rte = ref_hists(Bte, np.arange(len(dte)))
    ttr = stack(Rtr[:6] + [np.ones(3)])
    print(HDR); print("-" * len(HDR))
    show("target drift (floor)", Rtr, Rte)
    for L, K in ((1, 40), (2, 20), (3, 14), (2, 30)):
        blocks = build_blocks(dtr, Btr, L)
        A = design(blocks, Btr, Rtr[6])
        for wt, tag in ((False, "eq"), (True, "wt")):
            ch, w, _ = select(blocks, A, ttr, K, weighted=wt)
            h = hists(Btr, [blocks[j]["rows"] for j in ch], w)
            show(f"{tag} {K:2d}x{L}d ({K*L}d)", h, Rte, 1.0 / np.sum(w ** 2))
