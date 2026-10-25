"""Read mean wind speed from a WAsP .wrg resource grid.

THE TRAP THIS EXISTS TO PREVENT: field 5 of a .wrg data line is the Weibull
**A** parameter, not the mean wind speed.  Reading it as the mean overstates
speed by ~13% (A/U = 1/0.886 for k~2.1), and because A is stored to one
decimal the values look suspiciously round -- 9.50, 9.30, 9.00 -- which is the
tell.  Mean speed must be derived from the Weibull parameters.

Line layout:
    [label]  E  N  elev  height  A  k  power_density  nsectors  then nsectors
    triplets of  freq*1000  A*10  k*100

The leading label is a 10-char text field in the WAsP spec.  It is BLANK in the
Vortex exports -- so whitespace splitting drops it and the easting lands at
index 0 -- but WakeMap writes "GridPoint" there, which shifts every field by one
and would otherwise be read as elevation->A.  So a non-numeric first token is
discarded explicitly rather than relying on the label being empty.

Two defensible means:
  all-sector   A * Gamma(1 + 1/k)                     from the omnidirectional fit
  sector-wt    sum_i f_i * A_i * Gamma(1 + 1/k_i)     DEFAULT -- what WAsP reports
They agree to <0.09 m/s at the LGW/WSW masts, and sector-weighted is preferred.

Masked nodes carry A=1.0, k=1.50 with all sectors identical (331 of 111,166 at
WSW, 17 of 57,352 at LGW).  They are excluded from nearest-node matching, else a
mast near the domain edge silently snaps to a 1 m/s node.
"""
import numpy as np
from math import gamma


def _isnum(s):
    try:
        float(s)
        return True
    except ValueError:
        return False


def load_wrg(path):
    """-> (E, N, A, K, PD, recs) with recs[i] = (freq[], A[], k[]) per sector."""
    E, N, A, K, PD, recs = [], [], [], [], [], []
    with open(path) as fh:
        fh.readline()                      # "nx ny x0 y0 dx"
        for line in fh:
            q = line.split()
            # drop a text label ("GridPoint"); blank labels vanish in the split
            if q and not _isnum(q[0]):
                q = q[1:]
            if len(q) < 8:
                continue
            ns = int(q[7])
            sec = q[8:8 + 3 * ns]
            if len(sec) < 3 * ns:
                continue
            E.append(float(q[0])); N.append(float(q[1]))
            A.append(float(q[4])); K.append(float(q[5])); PD.append(float(q[6]))
            recs.append((
                np.array([float(sec[3 * i]) for i in range(ns)]) / 1000.0,
                np.array([float(sec[3 * i + 1]) for i in range(ns)]) / 10.0,
                np.array([float(sec[3 * i + 2]) for i in range(ns)]) / 100.0,
            ))
    return (np.array(E), np.array(N), np.array(A), np.array(K), np.array(PD), recs)


def masked(A, K):
    """Sentinel nodes: A<=1.0 with k exactly 1.50."""
    return (A <= 1.0) & (np.abs(K - 1.5) < 1e-9)


def mean_speed(A, K, recs, how="sector"):
    if how == "sector":
        return np.array([float(np.sum(f * a * np.array([gamma(1 + 1 / x) for x in k])))
                         for (f, a, k) in recs])
    if how == "allsector":
        return A * np.array([gamma(1 + 1 / k) for k in K])
    raise ValueError(how)


def at_points(path, epsg, points, how="sector", max_dist=500.0):
    """points: {name: (lat, lon)} -> {name: (U, dist_m, A, k)}.  Needs pyproj."""
    from pyproj import Transformer
    E, N, A, K, PD, recs = load_wrg(path)
    U = mean_speed(A, K, recs, how)
    bad = masked(A, K)
    t = Transformer.from_crs("EPSG:4326", epsg, always_xy=True)
    out = {}
    for name, (la, lo) in points.items():
        e, n = t.transform(lo, la)
        d2 = np.where(bad, np.inf, (E - e) ** 2 + (N - n) ** 2)
        i = int(np.argmin(d2))
        d = float(np.sqrt(d2[i]))
        if d > max_dist:
            raise SystemExit(f"{name}: nearest unmasked WRG node is {d:.0f} m away")
        out[name] = (float(U[i]), d, float(A[i]), float(K[i]))
    return out
