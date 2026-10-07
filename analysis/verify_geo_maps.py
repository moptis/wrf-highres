"""Verify that a geo_em file really inherited its high-resolution static data.

Checks the data source recorded by geogrid, then measures whether the field
actually varies at the model grid scale -- a coarse source interpolated onto a
fine grid passes the header check but produces smooth plateaus.  Optionally
compares against a second geo_em file (e.g. the previous GMTED/MODIS build) and
plots both.

Usage:
    python verify_geo_maps.py NEW_GEO [--ref OLD_GEO] [--out DIR] [--label-new L]
"""
import argparse, os
import numpy as np
import netCDF4 as nc
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import BoundaryNorm, ListedColormap

# NLCD40 names and roughness (cm) from WRF's LANDUSE.TBL, SUMMER block.
NLCD40 = {
    1: ("evergreen needleleaf", 100.), 2: ("evergreen broadleaf", 100.),
    3: ("deciduous needleleaf", 100.), 4: ("deciduous broadleaf", 100.),
    5: ("mixed forest", 100.), 6: ("closed shrubland", 15.),
    7: ("open shrubland", 15.), 8: ("woody savanna", 25.),
    9: ("savanna", 15.), 10: ("grassland", 7.),
    11: ("permanent wetland", 20.), 12: ("cropland", 10.),
    13: ("urban", 80.), 14: ("crop/natural mosaic", 30.),
    15: ("snow and ice", 1.2), 16: ("barren", 5.),
    17: ("IGBP water", 0.01), 18: ("unclassified", 0.01),
    19: ("fill value", 0.01), 20: ("unclassified", 0.01),
    21: ("Open Water", 0.01), 22: ("Perennial Ice/Snow", 1.2),
    23: ("Developed Open Space", 30.), 24: ("Developed Low Intensity", 40.),
    25: ("Developed Medium Intensity", 60.), 26: ("Developed High Intensity", 100.),
    27: ("Barren Land", 5.), 28: ("Deciduous Forest", 100.),
    29: ("Evergreen Forest", 100.), 30: ("Mixed Forest", 100.),
    31: ("Dwarf Scrub", 10.), 32: ("Shrub/Scrub", 15.),
    33: ("Grassland/Herbaceous", 7.), 34: ("Sedge/Herbaceous", 7.),
    35: ("Lichens", 5.), 36: ("Moss", 5.),
    37: ("Pasture/Hay", 7.), 38: ("Cultivated Crops", 10.),
    39: ("Woody Wetlands", 55.), 40: ("Emergent Herbaceous Wetlands", 11.),
}


def load(path):
    f = nc.Dataset(path)
    d = dict(hgt=np.asarray(f["HGT_M"][0], float),
             lu=np.asarray(f["LU_INDEX"][0], float),
             lat=np.asarray(f["XLAT_M"][0], float),
             lon=np.asarray(f["XLONG_M"][0], float),
             dx=float(f.DX), mminlu=f.MMINLU, ncat=int(f.NUM_LAND_CAT))
    f.close()
    return d


def terrain_stats(hgt, dx):
    """Grid-scale variability diagnostics for a terrain field."""
    gy, gx = np.gradient(hgt, dx, dx)
    slope = np.hypot(gx, gy) * 1000.0                      # m per km
    # Lag-1 correlation of the first difference.  A field resolved at the grid
    # scale decorrelates fast; a coarse field interpolated to a fine grid keeps
    # its differences nearly constant across neighbouring cells.
    d = np.diff(hgt, axis=1)
    r1 = np.corrcoef(d[:, :-1].ravel(), d[:, 1:].ravel())[0, 1]
    # Fraction of cells whose 3x3 neighbourhood is perfectly flat -- the
    # signature of a plateau left by nearest-neighbour upsampling.
    flat = np.mean([(np.abs(hgt[1:-1, 1:-1] - hgt[1 + i:, 1 + j:][: hgt.shape[0] - 2,
                     : hgt.shape[1] - 2]) < 1e-6)
                    for i, j in [(-1, 0), (1, 0), (0, -1), (0, 1)]], axis=0)
    return dict(slope_p50=np.percentile(slope, 50),
                slope_p99=np.percentile(slope, 99),
                slope_max=slope.max(),
                diff_lag1=r1,
                plateau_frac=float((flat == 1.0).mean()),
                std=hgt.std(), rng=(hgt.min(), hgt.max()))


def radial_spectrum(a, dx):
    a = a - a.mean()
    n = min(a.shape)
    a = a[:n, :n] * np.outer(np.hanning(n), np.hanning(n))
    p = np.abs(np.fft.fftshift(np.fft.fft2(a))) ** 2
    ky, kx = np.meshgrid(np.fft.fftshift(np.fft.fftfreq(n, dx)),
                         np.fft.fftshift(np.fft.fftfreq(n, dx)), indexing="ij")
    k = np.hypot(kx, ky)
    kb = np.logspace(np.log10(1.0 / (n * dx)), np.log10(0.5 / dx), 40)
    idx = np.digitize(k.ravel(), kb)
    ps = np.array([p.ravel()[idx == i].mean() if (idx == i).any() else np.nan
                   for i in range(1, len(kb))])
    return kb[:-1], ps


def lu_report(lu, dx, label):
    vals, cnt = np.unique(lu.astype(int), return_counts=True)
    frac = 100.0 * cnt / lu.size
    z0 = sum(NLCD40.get(v, ("?", np.nan))[1] * f / 100.0 for v, f in zip(vals, frac))
    print(f"\n  {label}: {len(vals)} categories present, "
          f"area-weighted z0 = {z0:.2f} cm")
    for v, f in sorted(zip(vals, frac), key=lambda t: -t[1])[:8]:
        name, z = NLCD40.get(v, ("unknown", np.nan))
        print(f"    {v:3d}  {name:<30s} {f:5.1f}%   z0={z:6.2f} cm")
    # Patch granularity: fraction of cells differing from all four neighbours.
    c = lu[1:-1, 1:-1]
    iso = ((c != lu[:-2, 1:-1]) & (c != lu[2:, 1:-1]) &
           (c != lu[1:-1, :-2]) & (c != lu[1:-1, 2:]))
    edge = ((c != lu[:-2, 1:-1]) | (c != lu[2:, 1:-1]) |
            (c != lu[1:-1, :-2]) | (c != lu[1:-1, 2:]))
    print(f"    isolated single-cell patches: {100*iso.mean():.2f}% of cells")
    print(f"    cells on a category boundary: {100*edge.mean():.1f}% "
          f"(higher = finer mosaic)")
    return z0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("new")
    ap.add_argument("--ref")
    ap.add_argument("--out", default=".")
    ap.add_argument("--label-new", default="new")
    ap.add_argument("--label-ref", default="reference")
    ap.add_argument("--zoom-km", type=float, default=6.0)
    a = ap.parse_args()

    runs = [(a.label_new, load(a.new))]
    if a.ref:
        runs.append((a.label_ref, load(a.ref)))

    print("=" * 74)
    for lab, d in runs:
        print(f"{lab:>12s}: {d['lu'].shape[1]}x{d['lu'].shape[0]} @ {d['dx']:.0f} m  "
              f"MMINLU={d['mminlu']} NUM_LAND_CAT={d['ncat']}")
    print("=" * 74)
    print("\nTERRAIN")
    print(f"  {'':12s} {'std':>7} {'range m':>14} {'slope p50':>10} {'slope p99':>10} "
          f"{'slope max':>10} {'diff lag1':>10} {'plateau':>8}")
    for lab, d in runs:
        s = terrain_stats(d["hgt"], d["dx"])
        print(f"  {lab:12s} {s['std']:7.1f} {s['rng'][0]:6.0f}..{s['rng'][1]:6.0f} "
              f"{s['slope_p50']:10.1f} {s['slope_p99']:10.1f} {s['slope_max']:10.1f} "
              f"{s['diff_lag1']:10.3f} {100*s['plateau_frac']:7.2f}%")
    print("    slope in m/km; 'diff lag1' near 0 = resolved at grid scale, "
          "near 1 = upsampled;\n    'plateau' = cells identical to all 4 neighbours")

    print("\nLAND USE")
    for lab, d in runs:
        lu_report(d["lu"], d["dx"], lab)

    # ---- figure ----
    nruns = len(runs)
    fig = plt.figure(figsize=(6.2 * nruns + 1.5, 13.5))
    gs = fig.add_gridspec(4, nruns, height_ratios=[1.25, 1.0, 1.0, 0.85],
                          hspace=0.30, wspace=0.16)

    cats = sorted(set(np.unique(runs[0][1]["lu"].astype(int)))
                  | set(np.unique(runs[-1][1]["lu"].astype(int))))
    lucm = ListedColormap(plt.cm.tab20(np.linspace(0, 1, max(len(cats), 2))))
    lunorm = BoundaryNorm(np.array(cats + [cats[-1] + 1]) - 0.5, lucm.N)

    for j, (lab, d) in enumerate(runs):
        ext = [d["lon"].min(), d["lon"].max(), d["lat"].min(), d["lat"].max()]
        ny, nx = d["hgt"].shape
        half = int(a.zoom_km * 1000 / d["dx"] / 2)
        sl = (slice(ny // 2 - half, ny // 2 + half),
              slice(nx // 2 - half, nx // 2 + half))

        ax = fig.add_subplot(gs[0, j])
        im = ax.imshow(d["hgt"], origin="lower", extent=ext, cmap="terrain",
                       aspect="auto")
        ax.add_patch(plt.Rectangle(
            (d["lon"][sl[0].start, sl[1].start], d["lat"][sl[0].start, sl[1].start]),
            d["lon"][sl[0].start, sl[1].stop] - d["lon"][sl[0].start, sl[1].start],
            d["lat"][sl[0].stop, sl[1].start] - d["lat"][sl[0].start, sl[1].start],
            fc="none", ec="red", lw=1.4))
        ax.set_title(f"{lab} — HGT_M, d05 @ {d['dx']:.0f} m", fontsize=11)
        ax.set_ylabel("lat"); fig.colorbar(im, ax=ax, label="m")

        ax = fig.add_subplot(gs[1, j])
        im = ax.imshow(d["hgt"][sl], origin="lower", cmap="terrain", aspect="equal",
                       interpolation="nearest")
        ax.set_title(f"{lab} — terrain zoom, {a.zoom_km:.0f} km box", fontsize=11)
        ax.set_xticks([]); ax.set_yticks([]); fig.colorbar(im, ax=ax, label="m")

        ax = fig.add_subplot(gs[2, j])
        im = ax.imshow(d["lu"][sl], origin="lower", cmap=lucm, norm=lunorm,
                       aspect="equal", interpolation="nearest")
        ax.set_title(f"{lab} — LU_INDEX zoom ({d['mminlu']})", fontsize=11)
        ax.set_xticks([]); ax.set_yticks([])
        cb = fig.colorbar(im, ax=ax, ticks=cats)
        cb.ax.set_yticklabels([f"{c} {NLCD40.get(c, ('?',))[0][:18]}" for c in cats],
                              fontsize=7)

    ax = fig.add_subplot(gs[3, 0])
    for lab, d in runs:
        k, ps = radial_spectrum(d["hgt"], d["dx"])
        ax.loglog(1.0 / k / 1000.0, ps, label=lab)
    ax.axvline(0.9, color="grey", ls=":", lw=1)
    ax.text(0.92, 0.04, "900 m (GMTED)", transform=ax.get_xaxis_transform(),
            fontsize=8, color="grey", rotation=90, va="bottom")
    ax.invert_xaxis()
    ax.set_xlabel("wavelength (km)"); ax.set_ylabel("terrain power")
    ax.set_title("Terrain variance spectrum", fontsize=11); ax.legend(fontsize=9)
    ax.grid(alpha=0.3, which="both")

    if nruns > 1:
        ax = fig.add_subplot(gs[3, 1])
        for lab, d in runs:
            gy, gx = np.gradient(d["hgt"], d["dx"], d["dx"])
            ax.hist(np.hypot(gx, gy).ravel() * 1000, bins=120, range=(0, 400),
                    histtype="step", density=True, label=lab)
        ax.set_xlabel("terrain slope (m/km)"); ax.set_ylabel("density")
        ax.set_title("Slope distribution", fontsize=11)
        ax.legend(fontsize=9); ax.set_yscale("log"); ax.grid(alpha=0.3)

    os.makedirs(a.out, exist_ok=True)
    p = os.path.join(a.out, "geo_em_d05_verification.png")
    fig.savefig(p, dpi=135, bbox_inches="tight")
    print(f"\nwrote {p}")


if __name__ == "__main__":
    main()
