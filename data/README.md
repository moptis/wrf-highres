# data/

| file | what it is |
|---|---|
| `selected_blocks.csv` | the 40 sampled days with weights, from `sampling/final_selection.py` |
| `run_manifest.csv` | block -> run dir -> weight, written by `pipeline/stage_blocks.py`. `synthetic_start` is a workaround for the stock h5 path's 2019 calendar and is unused by the compact pipeline |
| `myoutfields.txt` | WRF `iofields_filename` -- trims the history stream |

Weights range 0.0096-0.0704 against 0.025 for equal, ESS 756 of 960 hours.
