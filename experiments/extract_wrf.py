"""Pull hub-height wind from the 1 km TMY run so subsampling can be tested in
the space that actually matters: the downscaled WRG field, not the ERA5 forcing.

Subsamples grid points (the spatial pattern is smooth at 1 km) but keeps every
timestamp, then caches to npz.
"""
import h5py, numpy as np

H5 = "/scratch/moptis/c2wind/wsw_nlcd/processed/wsw_nlcd.h5"
OUT = "/scratch/moptis/c2wind/wsw_high/tmy/wrf_tmy_100m.npz"
CSTRIDE = 24          # 10944 / 24 = 456 grid points
TCHUNK = 4000

with h5py.File(H5, "r") as f:
    print("datasets:", [k for k in f.keys() if "wind_speed" in k][:8])
    t = np.array([s.decode() for s in f["time_index"][:]])
    ncol = f["wind_speed_100m"].shape[1]
    cols = np.arange(0, ncol, CSTRIDE)
    coords = f["coordinates"][:][cols]
    elev = f["elevation"][:][cols]
    print(f"times {len(t)}  cols {len(cols)} of {ncol}")

    ws = np.empty((len(t), len(cols)), np.float32)
    wd = np.empty((len(t), len(cols)), np.float32)
    for i in range(0, len(t), TCHUNK):
        j = min(i + TCHUNK, len(t))
        ws[i:j] = f["wind_speed_100m"][i:j, ::CSTRIDE]
        wd[i:j] = f["wind_direction_100m"][i:j, ::CSTRIDE]
        print(f"  {j}/{len(t)}", flush=True)

np.savez_compressed(OUT, time=t, ws=ws, wd=wd, coords=coords, elev=elev)
print("wrote", OUT, ws.shape)
