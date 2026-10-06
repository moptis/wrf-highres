"""Convert the Copernicus GLO-30 mosaic into WPS binary geogrid tiles.

Three things make this non-trivial:

  * Copernicus reduces longitudinal sampling with latitude (3600 cols below
    50N, then 2400/1800/1200/720 going north).  WPS needs a uniform regular_ll
    grid, so everything is resampled to a uniform 1 arcsec VRT first.
  * WPS tile filenames carry 5-digit cell indices, so no dataset may exceed
    99999 cells on a side.  North America at 1 arcsec is 327600 x 216000, so it
    is split into pieces -- the same reason NLCD2025 ships as 16 pieces.
  * Tile files include the halo: each holds (tile+2*bdr)^2 values, verified
    against the shipped GMTED tiles.

Output matches the GMTED conventions already in WPS_GEOG: big-endian signed
int16, metres, row_order bottom_top, tile_bdr 3.
"""
import argparse, os, sys
import numpy as np
import rasterio
from rasterio.windows import Window

VRT = "/scratch/moptis/dem/cop30_na.vrt"
OUT = "/projects/aiweather/WPS_GEOG"
TILE, BDR = 1200, 3
PIECE = 60          # tiles per piece side -> 72000 cells, inside the 5-digit limit
NODATA = -9999      # written where no source tile exists; geogrid falls back


def source_cells(filelist):
    """Integer degree (lat, lon) SW corners that actually have a source tile."""
    import re
    s = set()
    for line in open(filelist):
        m = re.search(r'_(N|S)(\d\d)_00_(E|W)(\d\d\d)_00_', line)
        if m:
            s.add((int(m.group(2)) * (1 if m.group(1) == 'N' else -1),
                   int(m.group(4)) * (1 if m.group(3) == 'E' else -1)))
    return s


def main(a):
    src = source_cells("/scratch/moptis/dem/cop30_filelist.txt")
    with rasterio.open(VRT) as d:
        T, W, H = d.transform, d.width, d.height
        dx, dy = T.a, -T.e
        left, top = T.c, T.f
    bottom = top - H * dy
    nxt, nyt = W // TILE, H // TILE
    print(f"VRT {W}x{H}  dx={dx:.12f}  lon {left:.6f}..{left+W*dx:.6f}  "
          f"lat {bottom:.6f}..{top:.6f}")
    print(f"tiles {nxt} x {nyt}  pieces of {PIECE}x{PIECE}")

    jobs = []
    for pr in range((nyt + PIECE - 1) // PIECE):
        for pc in range((nxt + PIECE - 1) // PIECE):
            name = f"topo_cop30_1s_r{pr}c{pc}"
            tx0, ty0 = pc * PIECE, pr * PIECE                      # tile origin, bottom_top
            tx1, ty1 = min(tx0 + PIECE, nxt), min(ty0 + PIECE, nyt)
            # which tiles in this piece touch a source degree cell?
            live = []
            for ty in range(ty0, ty1):
                for tx in range(tx0, tx1):
                    la0 = bottom + ty * TILE * dy
                    lo0 = left + tx * TILE * dx
                    if any((int(np.floor(la0 + k * (TILE * dy) / 2)),
                            int(np.floor(lo0 + j * (TILE * dx) / 2))) in src
                           for k in (0, 1, 2) for j in (0, 1, 2)):
                        live.append((tx, ty))
            if live:
                jobs.append((name, tx0, ty0, tx1, ty1, live,
                             bottom + ty0 * TILE * dy, left + tx0 * TILE * dx))
    tot = sum(len(j[5]) for j in jobs)
    print(f"{len(jobs)} pieces, {tot} tiles with data "
          f"({tot * (TILE+2*BDR)**2 * 2 / 1e9:.1f} GB)")
    if a.dry_run:
        for n, *_ , live, la, lo in jobs:
            print(f"  {n}: {len(live):5d} tiles  origin lat {la:.4f} lon {lo:.4f}")
        return

    sel = [j for j in jobs if (not a.piece or j[0].endswith(a.piece))]
    if a.near:
        nla, nlo = (float(v) for v in a.near.split(','))
        keep = []
        for name, tx0, ty0, tx1, ty1, live, la0, lo0 in sel:
            sub = [(tx, ty) for tx, ty in live
                   if abs(bottom + (ty + .5) * TILE * dy - nla) < 1
                   and abs(left + (tx + .5) * TILE * dx - nlo) < 1]
            if sub:
                keep.append((name, tx0, ty0, tx1, ty1, sub, la0, lo0))
        sel = keep
    with rasterio.open(VRT) as d:
        for name, tx0, ty0, tx1, ty1, live, la0, lo0 in sel:
            pdir = os.path.join(OUT, name)
            os.makedirs(pdir, exist_ok=True)
            with open(os.path.join(pdir, "index"), "w") as f:
                f.write(
                    "type = continuous\nsigned = yes\nprojection = regular_ll\n"
                    f"dx = {dx:.12f}\ndy = {dy:.12f}\n"
                    "known_x = 1.0\nknown_y = 1.0\n"
                    f"known_lat = {la0 + dy/2:.12f}\nknown_lon = {lo0 + dx/2:.12f}\n"
                    "wordsize = 2\nendian = big\nrow_order = bottom_top\n"
                    f"tile_x = {TILE}\ntile_y = {TILE}\ntile_z = 1\ntile_bdr = {BDR}\n"
                    f"missing_value = {NODATA}.\nscale_factor = 1.0\n"
                    'units = "meters MSL"\n'
                    f'description = "Copernicus GLO-30 1-arcsec topography, piece {name[-4:]}"\n')
            n = 0
            for tx, ty in live:
                # VRT rows run north->south; WPS bottom_top wants south-up
                col0 = (tx - tx0) * TILE + tx0 * TILE - BDR
                rowtop = H - ((ty + 1) * TILE) - BDR
                win = Window(col0, rowtop, TILE + 2*BDR, TILE + 2*BDR)
                arr = d.read(1, window=win, boundless=True, fill_value=np.nan)
                arr = np.flipud(arr)                       # -> south-up
                out = np.where(np.isfinite(arr), np.rint(arr), NODATA)
                out = np.clip(out, -32768, 32767).astype(">i2")
                xs, xe = (tx - tx0) * TILE + 1, (tx - tx0 + 1) * TILE
                ys, ye = (ty - ty0) * TILE + 1, (ty - ty0 + 1) * TILE
                fn = f"{xs:05d}-{xe:05d}.{ys:05d}-{ye:05d}"
                out.tofile(os.path.join(pdir, fn))
                n += 1
            print(f"  {name}: {n} tiles", flush=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--piece", default=None, help="only this piece, e.g. r0c2")
    p.add_argument("--near", default=None, help="LAT,LON -- only tiles within ~1 deg, for testing")
    main(p.parse_args())
