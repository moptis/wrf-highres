"""How much terrain detail does Vortex resolve that we do not?

Both are 100 m WRF-derived WRGs over the same box, so a spectral decomposition
of the mean-speed field isolates the question: at what spatial scales does each
field actually carry variance?
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from wrfhr import cfg, path

ROOT = cfg["CASE_ROOT"]

import sys
from math import gamma
import numpy as np
from scipy.interpolate import RegularGridInterpolator
sys.path.insert(0, cfg["CASE_ROOT"])
from wrg_meanws_map import read_wrg, grid

D = path("CASE_ROOT", "deliverables", "wrg")
REF = sys.argv[1] if len(sys.argv) > 1 else f"{D}/vortex.080.0.wrg"
OURS = sys.argv[2] if len(sys.argv) > 2 else f"{D}/wsw_high_80m.wrg"


def field(p):
    h, x, y, z, A, k, _ = read_wrg(p)
    u = A * np.array([gamma(1 + 1 / kk) if np.isfinite(kk) and kk > 0 else np.nan
                      for kk in k])
    xs, ys, U = grid(x, y, u, h["res"])
    _, _, Z = grid(x, y, z, h["res"])
    return xs, ys, U, Z


vx, vy, VU, VZ = field(REF)
ox, oy, OU, OZ = field(OURS)
print(f"vortex nodata cells: {np.isnan(VU).sum()} of {VU.size}")
print(f"vortex : {VU.shape}  {vx.min():.0f}-{vx.max():.0f}E  mean {np.nanmean(VU):.2f} m/s")
print(f"ours   : {OU.shape}  {ox.min():.0f}-{ox.max():.0f}E  mean {np.nanmean(OU):.2f} m/s")

# our grid is offset half a cell from theirs -> interpolate onto the Vortex grid
gi = RegularGridInterpolator((oy, ox), OU, bounds_error=False, fill_value=np.nan)
gz = RegularGridInterpolator((oy, ox), OZ, bounds_error=False, fill_value=np.nan)
YY, XX = np.meshgrid(vy, vx, indexing="ij")
OUi = gi((YY, XX)); OZi = gz((YY, XX))
m = np.isfinite(OUi) & np.isfinite(VU)
print(f"\ncommon points: {m.sum()} of {VU.size}")


def spectrum(F, label):
    F = np.where(np.isfinite(F), F, np.nanmean(F))
    A = np.abs(np.fft.fftshift(np.fft.fft2(F - F.mean()))) ** 2
    ny, nx = F.shape
    yy, xx = np.mgrid[:ny, :nx]
    # radial wavenumber normalised so r=1 is Nyquist (=200 m wavelength at 100 m)
    r = np.hypot((yy - ny / 2) / (ny / 2), (xx - nx / 2) / (nx / 2))
    bands = [(">2 km", 0, 0.1), ("0.8-2 km", 0.1, 0.25),
             ("400-800 m", 0.25, 0.5), ("<400 m", 0.5, 2.0)]
    out = {lab: 100 * A[(r >= lo) & (r < hi)].sum() / A.sum() for lab, lo, hi in bands}
    g = np.hypot(*np.gradient(F, 100.0))
    print(f"{label:10s} sd {F.std():5.3f}  " +
          "  ".join(f"{k} {v:5.2f}%" for k, v in out.items()) +
          f"   |grad| p99 {np.percentile(g,99)*1000:5.1f} (m/s)/km")
    return out


print(f"\n{'':10s} {'':11s} share of spatial variance by scale")
sv = spectrum(VU, "vortex U")
so = spectrum(OUi, "ours U")
print()
sz_v = spectrum(VZ, "vortex Z")
sz_o = spectrum(OZi, "ours Z")

print(f"\ncorrelation of the two mean-speed fields: "
      f"{np.corrcoef(VU[m], OUi[m])[0,1]:.4f}")
print(f"correlation of the two terrain fields    : "
      f"{np.corrcoef(VZ[m], OZi[m])[0,1]:.4f}")
print(f"\nsub-km variance (<2 km) — vortex {100-sv['>2 km']:.1f}%  ours {100-so['>2 km']:.1f}%"
      f"   -> we carry {(100-so['>2 km'])/(100-sv['>2 km']):.2f}x theirs")
print(f"terrain sub-km variance — vortex {100-sz_v['>2 km']:.1f}%  ours {100-sz_o['>2 km']:.1f}%")
