"""Does the wind ROSE carry over under block subsampling?

The supervised selector optimises resource level and the spatial pattern of
mean speed / AEP.  Nothing in that objective mentions direction -- yet a WRG
stores, per grid point and per sector, a frequency and a speed distribution.
Sector structure is the deliverable, so it has to be measured, not assumed.

Metrics are PER GRID POINT (terrain channels flow differently point to point),
then aggregated over points:
  * sector frequency error, in percentage points
  * sector energy-share error, in percentage points
  * total-variation distance between the normalised 12-sector roses
"""
import numpy as np, pandas as pd, sys

NPZ = "/scratch/moptis/c2wind/wsw_high/tmy/wrf_tmy_100m.npz"
NSECT, NPT = 12, None

d = np.load(NPZ, allow_pickle=True)
t = pd.to_datetime([s.replace("_", " ") for s in d["time"]]).tz_convert(None)
o = np.argsort(t.values)
t, ws, wd = t[o], d["ws"][o], d["wd"][o]
day = t.normalize()
NPT = ws.shape[1]

sect = (((wd + 180.0 / NSECT) % 360) // (360 / NSECT)).astype(np.int8)
ws3 = ws.astype(np.float64) ** 3
PC_U = np.arange(0, 31.0)
PC_P = np.clip((PC_U**3)/(12.0**3), 0, 1)*(PC_U >= 3)*(PC_U <= 25)
aep_t = np.interp(ws, PC_U, PC_P)

_pt = np.arange(NPT, dtype=np.int64) * NSECT


def rose(rows):
    """Per-point (NPT x NSECT) sector counts and sector energy sums."""
    idx = (_pt[None, :] + sect[rows]).ravel()
    c = np.bincount(idx, minlength=NPT * NSECT).reshape(NPT, NSECT)
    e = np.bincount(idx, weights=ws3[rows].ravel(),
                    minlength=NPT * NSECT).reshape(NPT, NSECT)
    return c.astype(np.float64), e


def norm(a):
    s = a.sum(1, keepdims=True)
    return np.divide(a, s, out=np.zeros_like(a), where=s > 0)


full_c, full_e = rose(np.arange(len(t)))
full_fc, full_fe = norm(full_c), norm(full_e)
full_mean = ws.mean(0); full_aep = aep_t.mean(0)
full_pat = full_mean / full_mean.mean()


def score_rose(rows, label):
    c, e = rose(rows)
    fc, fe = norm(c), norm(e)
    m = ws[rows].mean(0); a = aep_t[rows].mean(0)
    # sector mean speed, only where the full record has a meaningful sector
    occupied = full_fc > 0.01
    sms_full = np.divide(full_e, full_c, out=np.zeros_like(full_e), where=full_c > 0) ** (1/3)
    sms_sub = np.divide(e, c, out=np.zeros_like(e), where=c > 0) ** (1/3)
    sms_err = np.abs(sms_sub[occupied] / sms_full[occupied] - 1) * 100
    print(f"{label:<28s} {100*np.abs(fc-full_fc).mean():7.3f} {100*np.abs(fc-full_fc).max():7.2f} "
          f"{100*np.abs(fe-full_fe).mean():7.3f} {100*np.abs(fe-full_fe).max():7.2f} "
          f"{100*(0.5*np.abs(fc-full_fc).sum(1)).mean():7.2f} "
          f"{100*(0.5*np.abs(fe-full_fe).sum(1)).mean():7.2f} "
          f"{sms_err.mean():7.2f} "
          f"{100*(m.mean()/full_mean.mean()-1):+6.2f} "
          f"{100*np.sqrt((((m/m.mean())/full_pat-1)**2).mean()):6.2f}")


HDR = (f"{'selection':<28s} {'secF':>7} {'secFmx':>7} {'secE':>7} {'secEmx':>7} "
       f"{'roseTV':>7} {'roseTVe':>7} {'secWS%':>7} {'mean%':>6} {'pRMS%':>6}")
LEG = """
  secF/secE   mean |error| in per-point sector frequency / energy share (%pts)
  secFmx      worst single point-sector frequency error (%pts)
  roseTV      total-variation distance between per-point roses (%, 0 = identical)
  secWS%      mean |error| in sector-wise mean speed, occupied sectors only
  mean%/pRMS% resource level and spatial-pattern error, as before
"""

# ----------------------------------------------------------------- selection
days = pd.DatetimeIndex(np.unique(day))
ordi = np.array([x.toordinal() for x in days])
rows_by_day = {i: np.where(day == days[i])[0] for i in range(len(days))}


def blocks_of(L):
    out = []
    for i in range(len(days) - L + 1):
        if ordi[i+L-1] - ordi[i] != L - 1:
            continue
        r = np.concatenate([rows_by_day[j] for j in range(i, i + L)])
        c, e = rose(r)
        out.append(dict(start=days[i], end=days[i+L-1], rows=r, n=float(len(r)),
                        sws=ws[r].sum(0).astype(np.float64),
                        saep=aep_t[r].sum(0).astype(np.float64),
                        c=c, e=e, dset=set(ordi[i:i+L].tolist())))
    return out


def make_cost(w_dir):
    """w_dir = 0 reproduces the original level+pattern objective."""
    def cost(acc):
        n = acc["n"]
        if n == 0:
            return np.inf
        m, a = acc["sws"]/n, acc["saep"]/n
        lvl = abs(m.mean()/full_mean.mean()-1) + abs(a.mean()/full_aep.mean()-1)
        pat = np.sqrt((((m/m.mean())/full_pat-1)**2).mean())
        d = lvl + 2.0*pat
        if w_dir:
            fc, fe = norm(acc["c"]), norm(acc["e"])
            d += w_dir * (0.5*np.abs(fc-full_fc).sum(1).mean()
                          + 0.5*np.abs(fe-full_fe).sum(1).mean())
        return d
    return cost


def add(a, b):
    return dict(n=a["n"]+b["n"], sws=a["sws"]+b["sws"], saep=a["saep"]+b["saep"],
                c=a["c"]+b["c"], e=a["e"]+b["e"])


ZERO = dict(n=0.0, sws=np.zeros(NPT), saep=np.zeros(NPT),
            c=np.zeros((NPT, NSECT)), e=np.zeros((NPT, NSECT)))


def pick(L, K, w_dir, B=None):
    B = B if B is not None else blocks_of(L)
    cost = make_cost(w_dir)
    chosen, used, acc = [], set(), ZERO
    while len(chosen) < K:
        bj, bc = None, np.inf
        for j, b in enumerate(B):
            if j in chosen or used & b["dset"]:
                continue
            c = cost(add(acc, b))
            if c < bc:
                bj, bc = j, c
        if bj is None:
            break
        chosen.append(bj); used |= B[bj]["dset"]; acc = add(acc, B[bj])
    improved = True
    while improved:
        improved = False
        for pos in range(len(chosen)):
            rest = [c for c in chosen if c != chosen[pos]]
            base = ZERO
            for c in rest:
                base = add(base, B[c])
            busy = set().union(*[B[c]["dset"] for c in rest]) if rest else set()
            cur = chosen[pos]
            bj, bc = cur, cost(add(base, B[cur]))
            for j, b in enumerate(B):
                if j in rest or busy & b["dset"]:
                    continue
                c = cost(add(base, b))
                if c < bc - 1e-12:
                    bj, bc = j, c
            if bj != cur:
                chosen[pos] = bj; improved = True
    return np.sort(np.concatenate([B[j]["rows"] for j in chosen])), chosen, B


if __name__ == "__main__":
    print("Does the wind rose survive block subsampling?\n")
    print(HDR); print("-"*len(HDR))
    rng = np.random.default_rng(11)
    cache = {}
    for L, K in ((2, 14), (3, 10), (3, 14), (2, 21)):
        cache[L] = cache.get(L) or blocks_of(L)
        rows, _, B = pick(L, K, 0.0, cache[L])
        score_rose(rows, f"level+pattern  {K:2d}x{L}d")
    print()
    for L, K in ((2, 14), (3, 10), (3, 14), (2, 21)):
        rows, _, B = pick(L, K, 3.0, cache[L])
        score_rose(rows, f"+directional   {K:2d}x{L}d")
    print()
    for L, K in ((2, 14), (3, 14)):
        B = cache[L]
        for trial in range(3):
            sel, used = [], set()
            while len(sel) < K:
                j = int(rng.integers(len(B)))
                if j in sel or used & B[j]["dset"]:
                    continue
                sel.append(j); used |= B[j]["dset"]
            score_rose(np.sort(np.concatenate([B[j]["rows"] for j in sel])),
                       f"random         {K:2d}x{L}d #{trial+1}")
    print(LEG)
