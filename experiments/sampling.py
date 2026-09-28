"""
Representative-period selection for WRG-oriented WRF downscaling.

The question: the current TMY is 12 whole months (~365 days) chosen by ranking
each calendar month's ERA5 distribution against the long-term record.  For a
WRG deliverable we only need the *distribution* of hub-height wind to be right,
not the chronology -- so can a much shorter sample do the same job?

Constraint that shapes everything: WRF needs spin-up, so the sample must be
made of contiguous BLOCKS, not scattered hours.  A 6 h spin-up on a 3-day block
is 8% overhead; on single days it would be 25%.

Everything here is computed on ERA5 100 m wind, which is the forcing the nest
sees.  Whether matching in forcing space is enough to reproduce the downscaled
100 m WRG is tested separately in validate_wrf.py.
"""
import numpy as np, pandas as pd

ERA5 = "/scratch/moptis/c2wind/wsw_high/era5.csv"
NSECT = 12                       # 30 deg direction sectors
SPEED_EDGES = np.array([0, 3, 6, 9, 12, 15, 20, 100.0])
HOUR_BINS = [0, 6, 12, 18, 24]   # night / morning / afternoon / evening


def load_era5(path=ERA5):
    df = pd.read_csv(path, index_col=0, parse_dates=True, skiprows=1)
    df.columns = ["ws", "wd", "temp", "pres"]
    df = df[np.isfinite(df["ws"]) & np.isfinite(df["wd"])]
    # full calendar years only, so the seasonal cycle is not double-counted
    full = [y for y, g in df.groupby(df.index.year) if len(g) > 8700]
    return df[df.index.year.isin(full)]


def features(df):
    """Bin assignments used by every distance metric below."""
    sect = (((df["wd"].values + 180.0 / NSECT) % 360) // (360 / NSECT)).astype(int)
    sbin = np.clip(np.digitize(df["ws"].values, SPEED_EDGES) - 1, 0, len(SPEED_EDGES) - 2)
    hbin = np.digitize(df.index.hour.values, HOUR_BINS) - 1
    return sect, sbin, hbin, df.index.month.values - 1, df["ws"].values


def histograms(df):
    """Frequency and energy-weighted joint (sector x speed) histograms, plus
    month and hour-of-day marginals.  All normalised to sum to 1."""
    sect, sbin, hbin, mon, ws = features(df)
    ns, nb = NSECT, len(SPEED_EDGES) - 1
    flat = sect * nb + sbin
    freq = np.bincount(flat, minlength=ns * nb).astype(float)
    ener = np.bincount(flat, weights=ws ** 3, minlength=ns * nb)
    month = np.bincount(mon, minlength=12).astype(float)
    hour = np.bincount(hbin, minlength=len(HOUR_BINS) - 1).astype(float)
    out = []
    for h in (freq, ener, month, hour):
        s = h.sum()
        out.append(h / s if s > 0 else h)
    return out


WEIGHTS = (1.0, 1.0, 0.3, 0.3)   # freq, energy, month, hour


def distance(hs, target):
    return sum(w * np.abs(a - b).sum() for w, a, b in zip(WEIGHTS, hs, target))


# ---------------------------------------------------------------- selection
def block_index(df, block_days):
    """Contiguous candidate blocks of block_days, one per possible start day.

    Returns (start, end, row_indices, day_ordinals) so the greedy search can
    test overlap with integer sets instead of rebuilding date ranges.
    """
    day = df.index.normalize()
    days = pd.DatetimeIndex(sorted(day.unique()))
    ordinal = days.map(pd.Timestamp.toordinal).to_numpy()
    # row indices per day, in one pass
    pos = {d: [] for d in range(len(days))}
    day_of_row = np.searchsorted(days.to_numpy(), day.to_numpy())
    for r, d in enumerate(day_of_row):
        pos[d].append(r)
    pos = {d: np.array(v) for d, v in pos.items()}

    blocks = []
    for i in range(len(days) - block_days + 1):
        if ordinal[i + block_days - 1] - ordinal[i] != block_days - 1:
            continue                                  # crosses a data gap
        rows = np.concatenate([pos[j] for j in range(i, i + block_days)])
        if len(rows) >= 20 * block_days:              # near-complete hours
            blocks.append((days[i], days[i + block_days - 1], rows,
                           ordinal[i:i + block_days]))
    return blocks


def greedy_select(df, target, block_days, n_blocks, verbose=False):
    """Forward-greedy: repeatedly add the block that most reduces the distance
    between the accumulated sample and the long-term target."""
    blocks = block_index(df, block_days)
    sect, sbin, hbin, mon, ws = features(df)
    ns, nb = NSECT, len(SPEED_EDGES) - 1
    flat = sect * nb + sbin

    def raw(idx):
        return (np.bincount(flat[idx], minlength=ns * nb).astype(float),
                np.bincount(flat[idx], weights=ws[idx] ** 3, minlength=ns * nb),
                np.bincount(mon[idx], minlength=12).astype(float),
                np.bincount(hbin[idx], minlength=len(HOUR_BINS) - 1).astype(float))

    cache = [raw(b[2]) for b in blocks]
    acc = [np.zeros_like(c) for c in cache[0]]
    chosen, used_days = [], set()

    for step in range(n_blocks):
        best, best_d = None, np.inf
        for j, blk in enumerate(blocks):
            if j in chosen or used_days.intersection(blk[3].tolist()):
                continue
            cand = [a + c for a, c in zip(acc, cache[j])]
            d = distance([x / x.sum() if x.sum() > 0 else x for x in cand], target)
            if d < best_d:
                best, best_d = j, d
        if best is None:
            break
        chosen.append(best)
        acc = [a + c for a, c in zip(acc, cache[best])]
        used_days.update(blocks[best][3].tolist())
        if verbose:
            print(f"    block {step+1}: {blocks[best][0].date()} .. "
                  f"{blocks[best][1].date()}  D={best_d:.4f}")

    idx = np.concatenate([blocks[j][2] for j in chosen])
    spans = [(blocks[j][0], blocks[j][1]) for j in sorted(chosen, key=lambda j: blocks[j][0])]
    return df.iloc[np.sort(idx)], spans


def emd_tmy_months(df):
    """Reproduce the current 03_prepare_runs.py selection: for each calendar
    month, the year whose distribution is closest to the long-term one."""
    import scipy.stats as ss
    years = sorted(df.index.year.unique())
    picks = []
    for m in range(1, 13):
        allm = df[df.index.month == m]
        best, bd = None, np.inf
        for y in years:
            sub = allm[allm.index.year == y]
            if len(sub) < 600:
                continue
            d = (ss.wasserstein_distance(allm["ws"], sub["ws"]) / allm["ws"].std()
                 + ss.wasserstein_distance(allm["wd"], sub["wd"]) / allm["wd"].std()
                 + ss.wasserstein_distance(allm["temp"], sub["temp"]) / allm["temp"].std())
            if d < bd:
                best, bd = y, d
        picks.append((best, m))
    mask = np.zeros(len(df), bool)
    for y, m in picks:
        mask |= (df.index.year == y) & (df.index.month == m)
    return df[mask], picks
