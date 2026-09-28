"""Per-timestep weights for the WRG, aligned with the h5 time axis.

The 40 blocks are a weighted sample of the climate, not a contiguous record, so
each block carries a weight from the selection (0.0096-0.0704 against 0.025 for
equal).  A block's weight is spread evenly over its retained sample hours, so

    weight(timestep) = w_block / n_timesteps_in_that_block

Blocks are identified by date: every sample day is distinct, so a timestamp maps
to exactly one block.
"""
import sys
import h5py
import numpy as np
import pandas as pd

ROOT = "/scratch/moptis/c2wind/wsw_high"
H5 = f"{ROOT}/processed/wsw_high.h5"
OUT = f"{ROOT}/tmy/wrg_weights.npy"


def build(h5_file=H5, manifest=f"{ROOT}/tmy/run_manifest.csv", out=OUT):
    man = pd.read_csv(manifest, parse_dates=["sample_start"])
    with h5py.File(h5_file, "r") as f:
        t = pd.to_datetime([s.decode() if isinstance(s, bytes) else s
                            for s in f["time_index"][:]], utc=True)
    day = t.tz_localize(None).normalize()

    w = np.zeros(len(t))
    unmatched = 0
    for _, r in man.iterrows():
        m = day == r.sample_start.normalize()
        if not m.any():
            print(f"  WARNING: no timesteps for {r.run} ({r.sample_start.date()})")
            continue
        w[m] = r.weight / m.sum()
    unmatched = int((w == 0).sum())

    print(f"timesteps in h5: {len(t)}   expected: {len(man)*24}")
    print(f"  span {t.min()} .. {t.max()}")
    print(f"  distinct days: {day.nunique()}   blocks in manifest: {len(man)}")
    print(f"  timesteps with no block match: {unmatched}")
    print(f"  weights sum to {w.sum():.6f} (should be 1.0)")
    print(f"  per-timestep weight range {w[w>0].min():.6e} .. {w.max():.6e}")
    print(f"  effective sample size {1.0/np.sum((w/w.sum())**2):.1f} of {len(t)}")
    if unmatched:
        raise SystemExit("ERROR: unmatched timesteps -- weights would be wrong")
    np.save(out, w)
    print(f"wrote {out}")
    return w


if __name__ == "__main__":
    build(*(sys.argv[1:] or []))
