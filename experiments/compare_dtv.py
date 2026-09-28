"""Compare d05 fields across time-step configurations.

The question is not whether a larger dt crashes -- with w_damping=1 it will not
-- but whether it changes the answer.  Two failure modes matter:
  * damped vertical velocity (terrain updrafts clipped)
  * grid-scale numerical noise (energy piling up at 2*dx)
Both show up in the vertical-velocity field and its spatial spectrum.
"""
import numpy as np, netCDF4 as nc, glob, os, sys

ROOT = "/scratch/moptis/c2wind/wsw_high/wrf_runs"
CFGS = [("A", 0.889), ("B", 1.333), ("C", 2.222), ("D", 2.667)]
LEV = 5                      # ~100 m AGL given the 45-level set


def read(path):
    with nc.Dataset(path) as f:
        u = f["U"][0, LEV]; v = f["V"][0, LEV]; w = f["W"][0, LEV]
        u = 0.5 * (u[:, :-1] + u[:, 1:])
        v = 0.5 * (v[:-1, :] + v[1:, :])
        return np.hypot(u, v), w


def hf_energy(a):
    """Fraction of 2-D spectral variance above half-Nyquist -- grid-scale noise."""
    A = np.abs(np.fft.fftshift(np.fft.fft2(a - a.mean()))) ** 2
    ny, nx = a.shape
    yy, xx = np.mgrid[:ny, :nx]
    r = np.hypot((yy - ny / 2) / (ny / 2), (xx - nx / 2) / (nx / 2))
    return A[r > 0.5].sum() / A.sum()


if __name__ == "__main__":
    have = {}
    for name, dt in CFGS:
        fs = sorted(glob.glob(f"{ROOT}/dtv_{name}/wrfout_d05_*"))
        have[name] = fs
        print(f"dtv_{name} (d05 dt={dt:5.3f} s): {len(fs)} frames"
              + (f"  last={os.path.basename(fs[-1])[11:]}" if fs else ""))
    # only configs that got past the initial frame are comparable; a blown-up
    # run leaves just wrfout at t=0, and including it would collapse the
    # common-timestamp set to the initial condition (identical by construction)
    live = {k: v for k, v in have.items() if len(v) > 1}
    if len(live) < 2:
        print("\nfewer than two configs advanced past t=0 -- nothing to compare")
        sys.exit(0)
    common = set.intersection(*[{os.path.basename(f)[11:] for f in v}
                                for v in live.values()])
    stamp = sorted(common)[-1]
    print(f"\ncomparable configs: {', '.join(sorted(live))}"
          f"  (others blew up at t=0)")
    print(f"\ncomparing at {stamp}, model level {LEV}\n")

    ref_s, ref_w = read(f"{ROOT}/dtv_A/wrfout_d05_{stamp}")
    hdr = (f"{'cfg':>4} {'d05 dt':>7} {'mean|V|':>8} {'dV bias':>8} {'dV rms':>7} "
           f"{'w rms':>7} {'w p99':>7} {'max|w|':>7} {'HF frac':>8}")
    print(hdr); print("-" * len(hdr))
    for name, dt in CFGS:
        if name not in live:
            continue
        p = f"{ROOT}/dtv_{name}/wrfout_d05_{stamp}"
        if not os.path.exists(p):
            continue
        s, w = read(p)
        print(f"{name:>4} {dt:7.3f} {s.mean():8.3f} "
              f"{100*(s.mean()/ref_s.mean()-1):+7.2f}% {np.sqrt(((s-ref_s)**2).mean()):7.3f} "
              f"{np.sqrt((w**2).mean()):7.3f} {np.percentile(np.abs(w),99):7.3f} "
              f"{np.abs(w).max():7.3f} {hf_energy(s):8.4f}")
    print("\ndV bias/rms are vs config A (smallest dt).  A falling w rms or p99 means")
    print("updrafts are being damped; a rising HF frac means grid-scale noise.")
