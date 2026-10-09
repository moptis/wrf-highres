"""Produce the recommended block set against the full 24-year record."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from wrfhr import cfg, path

ROOT = cfg["CASE_ROOT"]

import numpy as np, pandas as pd
# sampler/eval3 live beside this file in the repo, not in the case directory.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sampler import load, bins, stack, build_blocks, design, select
from eval3 import hists, ref_hists, metrics

L, K = 1, 40
df = load(); B = bins(df)
R = ref_hists(B, np.arange(len(df)))
t = stack(R[:6] + [np.ones(3)])
blocks = build_blocks(df, B, L)
A = design(blocks, B, R[6])
ch, w, _ = select(blocks, A, t, K, weighted=True, wmax=6.0 / K)
m = metrics(hists(B, [blocks[j]["rows"] for j in ch], w), R)
print(f"{K} x {L}d  roseF {m['roseF']:.2f}  roseE {m['roseE']:.2f}  "
      f"dir*stab {m['dirstab']:.2f}  ws {m['ws']:+.2f}%  energy {m['en']:+.2f}%  "
      f"ESS {1/np.sum(w**2):.1f}/{K}\n")

rows = sorted(zip([blocks[j]["start"] for j in ch], w), key=lambda x: x[0])
out = pd.DataFrame({"start": [r[0].date() for r in rows],
                    "days": L, "weight": [round(float(r[1]), 5) for r in rows]})
out.to_csv(path("CASE_ROOT", "tmy", "selected_blocks.csv"), index=False)
print(out.to_string(index=False))
print(f"\nweight range {w.min():.4f} - {w.max():.4f} (equal would be {1/K:.4f})")
print("month coverage:", np.bincount([r[0].month for r in rows], minlength=13)[1:])
