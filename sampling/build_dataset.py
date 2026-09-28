"""Merge the 100 m wind product with the extracted surface-layer state."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from wrfhr import cfg, path

ROOT = cfg["CASE_ROOT"]

import numpy as np, pandas as pd

F = path("CASE_ROOT", "tmy", "era5_forcing_3h.csv")
C = path("CASE_ROOT", "era5.csv")
OUT = path("CASE_ROOT", "tmy", "site_forcing.csv")

# Ri_B class edges: anchored on neutrality rather than quantiles, so the classes
# mean the same thing at any site.
RI_EDGES = [-np.inf, -0.1, -0.01, 0.01, 0.1, np.inf]
RI_NAMES = ["v.unstable", "unstable", "neutral", "stable", "v.stable"]

f = pd.read_csv(F, index_col=0, parse_dates=True)
c = pd.read_csv(C, index_col=0, parse_dates=True, skiprows=1)
c.columns = ["ws", "wd", "t2_h", "psfc_h"]

df = f.join(c[["ws", "wd"]], how="inner")
df = df[np.isfinite(df.ws) & np.isfinite(df.wd) & np.isfinite(df.ri_b)]
df["ri_class"] = np.clip(np.digitize(df.ri_b, RI_EDGES[1:-1]), 0, 4)

print(f"merged: {df.index[0]} .. {df.index[-1]}  n={len(df)}  "
      f"({len(df)/(365.25*8):.1f} yr at 3-hourly)\n")
print("stability class populations:")
for i, nm in enumerate(RI_NAMES):
    m = df.ri_class == i
    print(f"  {i} {nm:<11s} {100*m.mean():5.1f}%   mean ws {df.ws[m].mean():5.2f} m/s"
          f"   mean dT {df.dT[m].mean():+6.2f} K")
print("\nstability by hour (UTC; local = UTC-7):")
tab = pd.crosstab(df.index.hour, df.ri_class, normalize="index") * 100
tab.columns = [RI_NAMES[i] for i in tab.columns]
print(tab.round(1).to_string())
print("\nstability by season:")
tab = pd.crosstab(df.index.month % 12 // 3, df.ri_class, normalize="index") * 100
tab.index = ["DJF", "MAM", "JJA", "SON"]; tab.columns = [RI_NAMES[i] for i in tab.columns]
print(tab.round(1).to_string())
df.to_csv(OUT, float_format="%.4f")
print(f"\nwrote {OUT}")
