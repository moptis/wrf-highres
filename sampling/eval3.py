"""Evaluate block-sampling strategies against the long-term ERA5 climate."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from wrfhr import cfg, path

ROOT = cfg["CASE_ROOT"]

import sys, time
import numpy as np, pandas as pd
sys.path.insert(0, path("CASE_ROOT", "tmy"))
from sampler3 import (load, bins, featurise, normalise, stack, build_blocks,
                      design, select, NSECT, NSPD, NSTAB, PC_U, PC_P)

TV = lambda p, q: 50.0 * np.abs(p - q).sum()      # total variation, in %


def hists(B, rows_list, w):
    """Weighted mixture of per-block histograms."""
    acc = None
    for rows, wi in zip(rows_list, w):
        g, n = featurise(B, rows)
        gn = [a / a.sum() if a.sum() > 0 else a for a in g[:-1]] + [g[-1] / n]
        acc = [wi * a for a in gn] if acc is None else [x + wi * a for x, a in zip(acc, gn)]
    return acc


def ref_hists(B, rows):
    g, n = featurise(B, rows)
    return [a / a.sum() if a.sum() > 0 else a for a in g[:-1]] + [g[-1] / n]


def metrics(h, r):
    dsF = h[0].reshape(NSECT, NSPD); dsF_r = r[0].reshape(NSECT, NSPD)
    dsE = h[1].reshape(NSECT, NSPD); dsE_r = r[1].reshape(NSECT, NSPD)
    secF, secF_r = dsF.sum(1), dsF_r.sum(1)
    secE, secE_r = dsE.sum(1), dsE_r.sum(1)
    mids = np.array([1.5, 4.5, 7.5, 10.5, 13.5, 18.0])
    sub = (dsF * mids).sum(1) / np.maximum(secF, 1e-12)
    ref = (dsF_r * mids).sum(1) / np.maximum(secF_r, 1e-12)
    occ = secF_r > 0.01
    ds = h[2].reshape(NSECT, NSTAB); ds_r = r[2].reshape(NSECT, NSTAB)
    return dict(
        roseF=TV(secF, secF_r), roseE=TV(secE, secE_r),
        joint=TV(h[0], r[0]), jointE=TV(h[1], r[1]),
        secWS=100 * np.abs(sub[occ] / ref[occ] - 1).mean(),
        stab=TV(ds.sum(0), ds_r.sum(0)), dirstab=TV(h[2], r[2]),
        month=TV(h[4], r[4]), hour=TV(h[5], r[5]),
        ws=100 * (h[6][0] / r[6][0] - 1), en=100 * (h[6][1] / r[6][1] - 1),
        cf=100 * (h[6][2] / r[6][2] - 1))


HDR = (f"{'method':<26s} {'roseF':>6} {'roseE':>6} {'joint':>6} {'secWS':>6} "
       f"{'stab':>6} {'dir*st':>7} {'month':>6} {'hour':>6} {'ws%':>6} {'en%':>6} {'ESS':>5}")


def show(label, h, r, ess=None):
    m = metrics(h, r)
    print(f"{label:<26s} {m['roseF']:6.2f} {m['roseE']:6.2f} {m['joint']:6.2f} "
          f"{m['secWS']:6.2f} {m['stab']:6.2f} {m['dirstab']:7.2f} {m['month']:6.2f} "
          f"{m['hour']:6.2f} {m['ws']:+6.2f} {m['en']:+6.2f} "
          f"{'' if ess is None else f'{ess:5.1f}'}")
    return m


if __name__ == "__main__":
    df = load(); B = bins(df)
    all_rows = np.arange(len(df))
    R = ref_hists(B, all_rows)
    ref_sc = R[6].copy()
    t = stack(R[:6] + [np.ones(3)])
    print(f"record {df.index[0].date()} .. {df.index[-1].date()}  n={len(df)}\n")

    print("NOISE FLOOR -- how well the record even defines its own target\n")
    print(HDR); print("-" * len(HDR))
    for name, m1 in (("first half vs second", df.index.year < 2012),
                     ("even vs odd years", df.index.year % 2 == 0)):
        a, b = np.where(m1)[0], np.where(~m1)[0]
        show(name, ref_hists(B, a), ref_hists(B, b))

    print("\n\nIN-SAMPLE (target = full 24 yr record)\n")
    print(HDR); print("-" * len(HDR))
    rng = np.random.default_rng(0)
    for L, K in ((3, 10), (3, 14)):
        blocks = build_blocks(df, B, L)
        A = design(blocks, B, ref_sc)
        for wt, tag in ((False, "equal-wt"), (True, "weighted")):
            t0 = time.time()
            ch, w, d = select(blocks, A, t, K, weighted=wt)
            ess = 1.0 / np.sum(w ** 2)
            show(f"{tag} {K:2d}x{L}d", hists(B, [blocks[j]["rows"] for j in ch], w), R, ess)
            print(f"{'':26s}   ({time.time()-t0:.0f}s, {K*L} days)")
        for trial in range(2):
            sel, used = [], set()
            while len(sel) < K:
                j = int(rng.integers(len(blocks)))
                if j in sel or used & blocks[j]["dset"]:
                    continue
                sel.append(j); used |= blocks[j]["dset"]
            show(f"random  {K:2d}x{L}d #{trial+1}",
                 hists(B, [blocks[j]["rows"] for j in sel], np.full(K, 1.0 / K)), R, K)
