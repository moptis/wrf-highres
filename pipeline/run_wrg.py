"""Create weighted WRGs from the compact h5, one per hub height."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from wrfhr import cfg, path

import sys
import numpy as np
sys.path.insert(0, cfg["WAKEMAP_REPO"])
from wakemap_processor.create_wrg import CreateWrg

ROOT = cfg["CASE_ROOT"]
H5 = f"{ROOT}/processed/wsw_high_compact.h5"
W = np.load(f"{ROOT}/tmy/wrg_weights.npy")
print(f"weights: n={len(W)} sum={W.sum():.6f} "
      f"range {W.min():.3e}-{W.max():.3e}  ESS {1/np.sum((W/W.sum())**2):.1f}")

for hh in (80, 100, 120, 160):
    out = f"{ROOT}/deliverables/wrg/wsw_high_{hh}m.wrg"
    print(f"\n=== {hh} m -> {out}", flush=True)
    CreateWrg.run(H5, wrg_file=out, hub_height=hh, bin_size=22.5,
                  max_workers=96, buffer=0.05, weights=W)
