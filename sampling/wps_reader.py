"""Minimal reader for WPS intermediate-format files (big-endian sequential
unformatted Fortran).

Only needs to pull a handful of single-point values, so it skips the data slab
whenever the field is not wanted rather than unpacking it.
"""
import struct, numpy as np

HEAD = ">i"                      # Fortran record length marker


def _records(fh):
    """Yield raw record payloads."""
    while True:
        h = fh.read(4)
        if len(h) < 4:
            return
        n = struct.unpack(HEAD, h)[0]
        payload = fh.read(n)
        fh.read(4)               # trailing marker
        yield payload


def _read_rec(fh):
    h = fh.read(4)
    if len(h) < 4:
        return None
    n = struct.unpack(HEAD, h)[0]
    p = fh.read(n)
    fh.read(4)
    return p


def _skip_rec(fh):
    h = fh.read(4)
    if len(h) < 4:
        return False
    n = struct.unpack(HEAD, h)[0]
    fh.seek(n + 4, 1)            # seek past payload + trailing marker
    return True


def read_fields(path, wanted=None, point=None):
    """Return ({field:level -> value}, grid) reading only the wanted slabs.

    Unwanted data slabs are seeked past rather than read, which cuts the I/O
    per file by roughly the fraction of fields not requested -- the difference
    between 11.7 MB and a few hundred kB when pulling a handful of variables.
    """
    out, grid = {}, {}
    with open(path, "rb") as fh:
        while True:
            if _read_rec(fh) is None:                       # version
                break
            h = _read_rec(fh)
            if h is None:
                break
            hdate = h[:24].decode().strip()
            off = 24 + 4 + 32
            field = h[off:off + 9].decode().strip()
            off += 9 + 25 + 46
            xlvl, nx, ny, iproj = struct.unpack(">fiii", h[off:off + 16])
            proj = _read_rec(fh)                            # projection
            _skip_rec(fh)                                   # wind flag
            if wanted is None or field in wanted:
                slab = _read_rec(fh)
                a = np.frombuffer(slab, dtype=">f4", count=nx * ny)
                key = f"{field}:{xlvl:.0f}"
                out[key] = float(a[point]) if point is not None else a.reshape(ny, nx)
            else:
                _skip_rec(fh)
            if not grid:
                sl, slon, dlat, dlon = struct.unpack(">ffff", proj[8:24])
                grid = dict(nx=nx, ny=ny, startlat=sl, startlon=slon,
                            dlat=dlat, dlon=dlon, hdate=hdate, iproj=iproj)
    return out, grid


def point_index(grid, lat, lon):
    """Flat index of the grid cell nearest (lat, lon)."""
    lons = grid["startlon"] + np.arange(grid["nx"]) * grid["dlon"]
    lats = grid["startlat"] + np.arange(grid["ny"]) * grid["dlat"]
    lon = lon % 360 if lons.max() > 180 else lon
    i = int(np.abs(lons - lon).argmin())
    j = int(np.abs(lats - lat).argmin())
    return j * grid["nx"] + i, float(lats[j]), float(lons[i])
