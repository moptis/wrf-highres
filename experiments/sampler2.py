"""Block sampler v2.

Changes over v1:
  * the objective carries explicit scalar terms for mean wind speed and mean
    U^3, so the sample is pinned to the right *level* and not just the right
    distribution shape (v1 left a -3% energy bias);
  * a swap-refinement pass after the greedy pass;
  * an out-of-sample mode, so a selection made on one half of the record can
    be scored against the other half.
"""
import numpy as np, pandas as pd

NSECT = 12
SPEED_EDGES = np.array([0, 3, 6, 9, 12, 15, 20, 100.0])
HOUR_BINS = [0, 6, 12, 18, 24]
NB = len(SPEED_EDGES) - 1

# freq-hist, energy-hist, month, hour, mean-U, mean-U^3, capacity factor
#
# The capacity-factor term matters: mean-U^3 can be matched by a handful of
# very windy hours, but those all sit at rated power, so a sample that matches
# U^3 can still bias AEP high by several percent.  Pinning a power-curve
# transform as well removes that.
WEIGHTS = (1.0, 1.0, 0.3, 0.3, 3.0, 3.0, 4.0)

_PC_U = np.arange(0, 31.0)
_PC_P = np.clip((_PC_U ** 3) / (12.0 ** 3), 0, 1) * (_PC_U >= 3) * (_PC_U <= 25)


def prep(df):
    """Per-hour bin assignments and the raw quantities the objective needs."""
    wd, ws = df["wd"].values, df["ws"].values
    sect = (((wd + 180.0 / NSECT) % 360) // (360 / NSECT)).astype(int)
    sbin = np.clip(np.digitize(ws, SPEED_EDGES) - 1, 0, NB - 1)
    return dict(flat=sect * NB + sbin,
                hour=np.digitize(df.index.hour.values, HOUR_BINS) - 1,
                month=df.index.month.values - 1,
                ws=ws, ws3=ws ** 3, cf=np.interp(ws, _PC_U, _PC_P))


def accumulate(P, idx):
    """Unnormalised sufficient statistics for a set of rows."""
    return (np.bincount(P["flat"][idx], minlength=NSECT * NB).astype(float),
            np.bincount(P["flat"][idx], weights=P["ws3"][idx], minlength=NSECT * NB),
            np.bincount(P["month"][idx], minlength=12).astype(float),
            np.bincount(P["hour"][idx], minlength=len(HOUR_BINS) - 1).astype(float),
            P["ws"][idx].sum(), P["ws3"][idx].sum(), float(len(idx)),
            P["cf"][idx].sum())


def add(a, b):
    return tuple(x + y for x, y in zip(a, b))


def target_stats(P):
    return accumulate(P, np.arange(len(P["ws"])))


def score(acc, tgt):
    """Weighted distance between a candidate sample and the target."""
    if acc[6] == 0:
        return np.inf
    d = 0.0
    for w, a, t in zip(WEIGHTS[:4], acc[:4], tgt[:4]):
        sa, st = a.sum(), t.sum()
        if sa > 0:
            d += w * np.abs(a / sa - t / st).sum()
    for w, i in ((WEIGHTS[4], 4), (WEIGHTS[5], 5), (WEIGHTS[6], 7)):
        d += w * abs((acc[i] / acc[6]) / (tgt[i] / tgt[6]) - 1)
    return d


def block_index(df, L):
    day = df.index.normalize()
    days = pd.DatetimeIndex(sorted(day.unique()))
    ordi = np.array([d.toordinal() for d in days])
    day_of_row = np.searchsorted(days.to_numpy(), day.to_numpy())
    order = np.argsort(day_of_row, kind="stable")
    bounds = np.searchsorted(day_of_row[order], np.arange(len(days) + 1))
    rows_by_day = [order[bounds[i]:bounds[i + 1]] for i in range(len(days))]

    blocks = []
    for i in range(len(days) - L + 1):
        if ordi[i + L - 1] - ordi[i] != L - 1:
            continue
        rows = np.concatenate(rows_by_day[i:i + L])
        if len(rows) >= 20 * L:
            blocks.append(dict(start=days[i], end=days[i + L - 1], rows=rows,
                               days=set(ordi[i:i + L].tolist())))
    return blocks


def select(df, L, K, tgt=None, refine=True, P=None):
    P = P or prep(df)
    tgt = tgt if tgt is not None else target_stats(P)
    blocks = block_index(df, L)
    stats = [accumulate(P, b["rows"]) for b in blocks]
    zero = tuple(np.zeros_like(s) if isinstance(s, np.ndarray) else 0.0 for s in stats[0])

    chosen, used, acc = [], set(), zero
    for _ in range(K):
        best, bd = None, np.inf
        for j, b in enumerate(blocks):
            if j in chosen or used & b["days"]:
                continue
            s = score(add(acc, stats[j]), tgt)
            if s < bd:
                best, bd = j, s
        if best is None:
            break
        chosen.append(best); used |= blocks[best]["days"]; acc = add(acc, stats[best])

    if refine:
        improved = True
        while improved:
            improved = False
            for pos in range(len(chosen)):
                cur = chosen[pos]
                rest = [c for c in chosen if c != cur]
                base = zero
                for c in rest:
                    base = add(base, stats[c])
                busy = set().union(*[blocks[c]["days"] for c in rest]) if rest else set()
                bj, bd = cur, score(add(base, stats[cur]), tgt)
                for j, b in enumerate(blocks):
                    if j in rest or busy & b["days"]:
                        continue
                    s = score(add(base, stats[j]), tgt)
                    if s < bd - 1e-12:
                        bj, bd = j, s
                if bj != cur:
                    chosen[pos] = bj
                    used = set().union(*[blocks[c]["days"] for c in chosen])
                    improved = True

    idx = np.sort(np.concatenate([blocks[j]["rows"] for j in chosen]))
    spans = sorted([(blocks[j]["start"], blocks[j]["end"]) for j in chosen])
    return df.iloc[idx], spans
