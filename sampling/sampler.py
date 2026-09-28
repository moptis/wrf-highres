"""Block sampling as a quadrature problem.

Choose a small set of contiguous multi-day blocks (and optionally weights) whose
weighted empirical distribution approximates the long-term climate over the
variables that condition the downscaling: direction, speed and stability
JOINTLY, plus season and time of day.

Two solvers share one objective:
  * equal-weight greedy + swap      -- selection only, K degrees of freedom of
                                       the "which blocks" kind
  * weighted OMP (bounded NNLS)     -- selection AND weights; weights are free
                                       downstream since the WRG is a weighted
                                       histogram either way
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from wrfhr import cfg, path

ROOT = cfg["CASE_ROOT"]

import numpy as np, pandas as pd
from scipy.optimize import lsq_linear

DATA = path("CASE_ROOT", "tmy", "site_forcing.csv")

NSECT = 12
SPEED_EDGES = np.array([0, 3, 6, 9, 12, 15, np.inf])
NSPD = len(SPEED_EDGES) - 1
NSTAB = 5
PC_U = np.arange(0, 31.0)
PC_P = np.clip((PC_U ** 3) / (12.0 ** 3), 0, 1) * (PC_U >= 3) * (PC_U <= 25)

# Group weights.  The rose (frequency and energy) is the deliverable, so it
# dominates; stability and season are shape constraints on top of it.
GROUPS = [("dir x spd  freq", 3.0), ("dir x spd  enrg", 3.0),
          ("dir x stab freq", 1.0), ("spd x stab freq", 0.5),
          ("month", 0.5), ("hour", 0.5), ("scalars", 2.0)]


def load(path=DATA):
    df = pd.read_csv(path, index_col=0, parse_dates=True)
    return df[np.isfinite(df.ws) & np.isfinite(df.wd) & np.isfinite(df.ri_class)]


def bins(df):
    sect = (((df.wd.values + 180.0 / NSECT) % 360) // (360 / NSECT)).astype(int)
    spd = np.clip(np.digitize(df.ws.values, SPEED_EDGES) - 1, 0, NSPD - 1)
    stab = df.ri_class.values.astype(int)
    return dict(sect=sect, spd=spd, stab=stab,
                month=df.index.month.values - 1,
                hour=(df.index.hour.values // 3),
                ws=df.ws.values, ws3=df.ws.values ** 3,
                cf=np.interp(df.ws.values, PC_U, PC_P))


def featurise(B, rows):
    """Unnormalised per-group feature counts for a set of row indices."""
    s, p, st = B["sect"][rows], B["spd"][rows], B["stab"][rows]
    n = float(len(rows))
    g = [np.bincount(s * NSPD + p, minlength=NSECT * NSPD).astype(float),
         np.bincount(s * NSPD + p, weights=B["ws3"][rows], minlength=NSECT * NSPD),
         np.bincount(s * NSTAB + st, minlength=NSECT * NSTAB).astype(float),
         np.bincount(p * NSTAB + st, minlength=NSPD * NSTAB).astype(float),
         np.bincount(B["month"][rows], minlength=12).astype(float),
         np.bincount(B["hour"][rows], minlength=8).astype(float),
         np.array([B["ws"][rows].sum(), B["ws3"][rows].sum(), B["cf"][rows].sum()])]
    return g, n


def normalise(g, n, ref_scalars=None):
    """Each histogram group -> sums to 1; scalars -> ratio against the target."""
    out = []
    for k, a in enumerate(g[:-1]):
        s = a.sum()
        out.append(a / s if s > 0 else a)
    sc = g[-1] / n
    out.append(sc / ref_scalars if ref_scalars is not None else sc)
    return out


def stack(groups):
    """Flatten groups into one vector, scaled so L2 respects the group weights."""
    return np.concatenate([np.sqrt(w) * a for (_, w), a in zip(GROUPS, groups)])


def build_blocks(df, B, L, stride=1):
    day = df.index.normalize()
    days = pd.DatetimeIndex(np.unique(day))
    ordi = np.array([d.toordinal() for d in days])
    pos = np.searchsorted(days.to_numpy(), day.to_numpy())
    order = np.argsort(pos, kind="stable")
    bnd = np.searchsorted(pos[order], np.arange(len(days) + 1))
    rows_by_day = [order[bnd[i]:bnd[i + 1]] for i in range(len(days))]

    out = []
    for i in range(0, len(days) - L + 1, stride):
        if ordi[i + L - 1] - ordi[i] != L - 1:
            continue
        rows = np.concatenate(rows_by_day[i:i + L])
        if len(rows) < 6 * L:                 # near-complete 3-hourly coverage
            continue
        out.append(dict(start=days[i], end=days[i + L - 1], rows=rows,
                        dset=set(ordi[i:i + L].tolist())))
    return out


def design(blocks, B, ref_scalars):
    """Feature matrix: one column per candidate block."""
    cols = []
    for b in blocks:
        g, n = featurise(B, b["rows"])
        cols.append(stack(normalise(g, n, ref_scalars)))
    return np.array(cols).T


def solve_weights(A_sub, t, wmax):
    """Bounded NNLS with the weights constrained to a simplex (soft)."""
    k = A_sub.shape[1]
    lam = 50.0
    Aa = np.vstack([A_sub, lam * np.ones((1, k))])
    ta = np.concatenate([t, [lam]])
    r = lsq_linear(Aa, ta, bounds=(0.0, wmax), method="bvls")
    return r.x, float(np.linalg.norm(A_sub @ r.x - t))


def select(blocks, A, t, K, weighted=True, wmax=None, screen=250, refine=True):
    """Greedy forward selection, then swap refinement."""
    wmax = wmax if wmax is not None else 3.0 / K
    chosen, used = [], set()

    def fit(idx):
        if weighted:
            return solve_weights(A[:, idx], t, wmax)
        w = np.full(len(idx), 1.0 / len(idx))
        return w, float(np.linalg.norm(A[:, idx] @ w - t))

    for _ in range(K):
        resid = t - (A[:, chosen] @ fit(chosen)[0] if chosen else 0)
        # cheap screen: blocks whose columns align best with what is missing
        score = A.T @ resid
        cand = [j for j in np.argsort(-score)
                if j not in chosen and not (used & blocks[j]["dset"])][:screen]
        best, bd, bw = None, np.inf, None
        for j in cand:
            w, d = fit(chosen + [j])
            if d < bd:
                best, bd, bw = j, d, w
        if best is None:
            break
        chosen.append(best); used |= blocks[best]["dset"]

    if refine:
        improved = True
        while improved:
            improved = False
            for pos in range(len(chosen)):
                rest = [c for c in chosen if c != chosen[pos]]
                busy = set().union(*[blocks[c]["dset"] for c in rest]) if rest else set()
                cur, bd = chosen[pos], fit(chosen)[1]
                resid = t - A[:, rest] @ fit(rest)[0] if rest else t
                score = A.T @ resid
                for j in [x for x in np.argsort(-score)
                          if x not in rest and not (busy & blocks[x]["dset"])][:screen]:
                    _, d = fit(rest + [j])
                    if d < bd - 1e-12:
                        cur, bd = j, d
                if cur != chosen[pos]:
                    chosen[pos] = cur; improved = True

    w, d = fit(chosen)
    w = w / w.sum()
    return chosen, w, d
