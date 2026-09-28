"""Map mean wind speed derived from a WRG's Weibull parameters.

The WRG stores, per grid point, an overall Weibull scale A and shape k.  The
mean of a two-parameter Weibull is

    <U> = A * Gamma(1 + 1/k)

so the map is computed from the delivered parameters rather than re-read from
the timeseries -- it shows exactly what a WRG consumer would see.

Writes a PNG (and a GeoTIFF if rasterio is available) beside the .wrg file.

  python wrg_meanws_map.py <file.wrg> [more.wrg ...]
"""
import os
import sys
from math import gamma

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap

# Single-hue sequential ramp, light -> dark (magnitude encoding).
# Never a rainbow: lightness must be monotonic so the map reads as one scale.
BLUE = ["#cde2fb", "#b7d3f6", "#9ec5f4", "#86b6ef", "#6da7ec", "#5598e7",
        "#3987e5", "#2a78d6", "#256abf", "#1c5cab", "#184f95", "#104281", "#0d366b"]
CMAP = LinearSegmentedColormap.from_list("seq_blue", BLUE)
SURFACE, INK, INK2 = "#fcfcfb", "#0b0b0b", "#52514e"


def read_wrg(path):
    """Parse a WAsP .wrg into (header, x, y, elev, height, A, k, pd)."""
    with open(path) as fh:
        head = fh.readline().split()
        nx, ny, x0, y0, res = (int(float(v)) for v in head[:5])
        # Two dialects in the wild: ours prefixes each row with "GridPoint",
        # Vortex omits it, shifting every column by one.  Detect per row.
        # Rows with elevation 0 and A=1.0/k=1.5 are nodata fill -- masked to NaN
        # so they cannot drag the statistics.
        x, y, z, A, k, pd_ = [], [], [], [], [], []
        for line in fh:
            f = line.split()
            if len(f) < 8:
                continue
            o = 1 if f[0] == "GridPoint" else 0
            try:
                xi, yi, zi = float(f[o]), float(f[o + 1]), float(f[o + 2])
                Ai, ki, pi = float(f[o + 4]), float(f[o + 5]), float(f[o + 6])
            except ValueError:
                continue
            if zi == 0.0 and Ai == 1.0 and ki == 1.5:
                Ai = ki = pi = np.nan
            x.append(xi); y.append(yi); z.append(zi)
            A.append(Ai); k.append(ki); pd_.append(pi)
    return (dict(nx=nx, ny=ny, x0=x0, y0=y0, res=res),
            *(np.array(v) for v in (x, y, z, A, k, pd_)))


def grid(x, y, v, res):
    """Scatter of regular grid points -> 2-D array (NaN where absent)."""
    xs = np.arange(x.min(), x.max() + res / 2, res)
    ys = np.arange(y.min(), y.max() + res / 2, res)
    g = np.full((ys.size, xs.size), np.nan)
    j = np.rint((y - y.min()) / res).astype(int)
    i = np.rint((x - x.min()) / res).astype(int)
    g[j, i] = v
    return xs, ys, g


def make_map(path, out_dir=None):
    h, x, y, z, A, k, pd_ = read_wrg(path)
    mean_u = A * np.array([gamma(1 + 1 / kk) if kk > 0 else np.nan for kk in k])
    xs, ys, U = grid(x, y, mean_u, h["res"])
    _, _, Z = grid(x, y, z, h["res"])

    base = os.path.splitext(os.path.basename(path))[0]
    out_dir = out_dir or os.path.dirname(path)
    xk, yk = (xs - xs.min()) / 1000.0, (ys - ys.min()) / 1000.0

    fig, ax = plt.subplots(figsize=(8.6, 7.2), facecolor=SURFACE)
    ax.set_facecolor(SURFACE)
    # robust limits so a couple of extreme cells do not flatten the whole ramp
    lo, hi = np.nanpercentile(U, [1, 99])
    im = ax.pcolormesh(xk, yk, U, cmap=CMAP, vmin=lo, vmax=hi, shading="nearest")

    # terrain, recessive -- present to show the terrain/resource relationship,
    # not to be read quantitatively
    if np.isfinite(Z).any():
        ax.contour(xk, yk, Z, levels=10, colors="#52514e",
                   linewidths=0.35, alpha=0.32)

    # extend arrows: the scale is clipped to 1-99th percentile so a few extreme
    # cells cannot flatten the ramp, and the arrows say so
    cb = fig.colorbar(im, ax=ax, pad=0.02, fraction=0.045, extend="both")
    cb.set_label("Mean wind speed (m/s)", color=INK2, fontsize=10)
    cb.ax.tick_params(colors=INK2, labelsize=9, length=0)
    cb.outline.set_visible(False)

    ax.set_aspect("equal")
    ax.set_xlabel(f"Easting (km from {h['x0']:.0f} m E)", color=INK2, fontsize=10)
    ax.set_ylabel(f"Northing (km from {h['y0']:.0f} m N)", color=INK2, fontsize=10)
    hub = base.split("_")[-1]
    # title sits clear of the subtitle: pad in points, subtitle just off the axes
    ax.set_title(f"{base.rsplit('_', 1)[0]} — mean wind speed at {hub}",
                 color=INK, fontsize=13, pad=30, loc="left")
    ax.text(0.0, 1.008,
            f"Weibull A·Γ(1+1/k) · {h['res']} m grid · {np.isfinite(U).sum()} pts"
            f" · scale 1–99 pct (range {np.nanmin(mean_u):.1f}–{np.nanmax(mean_u):.1f})",
            transform=ax.transAxes, color=INK2, fontsize=9, va="bottom")
    ax.tick_params(colors=INK2, labelsize=9, length=0)
    for s in ax.spines.values():
        s.set_visible(False)

    png = os.path.join(out_dir, f"{base}_meanws.png")
    fig.savefig(png, dpi=160, bbox_inches="tight", facecolor=SURFACE)
    plt.close(fig)

    tif = None
    try:
        import rasterio
        from rasterio.transform import from_origin
        tif = os.path.join(out_dir, f"{base}_meanws.tif")
        with rasterio.open(
            tif, "w", driver="GTiff", height=U.shape[0], width=U.shape[1],
            count=1, dtype="float32", crs="EPSG:32613",
            transform=from_origin(xs.min() - h["res"] / 2,
                                  ys.max() + h["res"] / 2, h["res"], h["res"]),
            nodata=np.nan,
        ) as dst:
            dst.write(np.flipud(U).astype("float32"), 1)
    except Exception as e:
        print(f"    (no GeoTIFF: {e})")

    return png, tif, mean_u


if __name__ == "__main__":
    for p in sys.argv[1:]:
        png, tif, mu = make_map(p)
        print(f"{os.path.basename(p)}: mean {np.nanmean(mu):.2f} m/s  "
              f"range {np.nanmin(mu):.2f}-{np.nanmax(mu):.2f}")
        print(f"    {png}")
        if tif:
            print(f"    {tif}")
