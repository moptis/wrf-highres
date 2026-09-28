# experiments/

One-off scripts from the benchmarking and method-development work. **These
contain hardcoded paths** and are kept as provenance for the numbers in
`docs/FINDINGS.md`, not as tools. Port them only if you need to re-measure.

| | what it established |
|---|---|
| `06_cpu_scaling.sbatch` | 8/16/32/64-rank scaling; 32->64 is only 1.29x |
| `07_packing_test.sbatch` | packing 3x32 ties 1x64 -- no gain |
| `10_binding_test.sbatch` | one-core-per-rank costs 1.9x (memory bandwidth) |
| `14_exclusive_test.sbatch` | whether `--exclusive` pays for itself |
| `09_dtv_*.sbatch` | time-step ladder; d05 dt 2.0 s and above blow up |
| `12_spin_*.sbatch` | spin-up convergence (3/6/12/24 h) |
| `04_wrf_gpu_test.sbatch`, `16_cadence100.sbatch` | AceCast benchmark; output cadence |
| `11_rose_check.py`, `rose_check.py` | wind-rose fidelity under subsampling |
| `select_supervised.py`, `holdout.py`, `select_in_wrf.py` | earlier selection method, supervised against the 1 km field -- superseded by the ERA5-only sampler |
| `sampling.py`, `sampler2.py`, `eval_era5.py`, `eval2.py` | earlier sampler iterations |
| `validate_wrf.py`, `scaling_curve.py`, `extract_wrf.py` | does ERA5-space matching survive downscaling |
| `cadence_test.py`, `compare_dtv.py` | output cadence; time-step field comparison |
| `05_process_d05.sbatch.legacy` | stock post-processing path -- **unweighted**, would silently produce a wrong WRG |
