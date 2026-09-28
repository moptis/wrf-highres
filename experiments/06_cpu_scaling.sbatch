#!/bin/bash
#SBATCH --job-name=wswhigh-scal
#SBATCH --output=/scratch/moptis/c2wind/wsw_high/scaling-%j.out
#SBATCH --nodes=1
#SBATCH --ntasks=104
#SBATCH --exclusive
#SBATCH --account=clusterwakes
#SBATCH --partition=standard
#SBATCH --time=02:30:00

# CPU strong-scaling test for the 5-domain wsw_high nest: 8 / 16 / 32 / 64 ranks.
#
# Every configuration starts from the same wrfinput/wrfbdy with a FIXED time
# step (40 s on d01, 0.494 s on d05) and history output disabled, so the only
# difference between runs is the decomposition.  Wall budgets are scaled by
# 1/ranks so each configuration completes a comparable number of d01 steps --
# one d01 step is 81 d05 steps, so the slow configurations need longer.

module load PrgEnv-gnu/8.5.0 cray-mpich/8.1.28 cray-libsci/23.12.5 netcdf/4.9.3-cray-mpich-gcc
export MPICH_OFI_NIC_POLICY=NUMA
export OMP_NUM_THREADS=1

ROOT=/scratch/moptis/c2wind/wsw_high

run_one () {
    local N=$1 BUDGET=$2
    local D=$ROOT/wrf_runs/scal_n$(printf %02d $N)
    echo "================ $N ranks (budget ${BUDGET}s) ================"
    cd $D || return
    rm -f rsl.* wrfout_*
    t0=$SECONDS
    timeout ${BUDGET}s srun -n $N ./wrf.exe > /dev/null 2>&1
    echo "$N ranks: used $((SECONDS-t0))s, $(grep -c 'on domain   1' rsl.error.0000 2>/dev/null) d01 steps"
}

run_one 64 600
run_one 32 900
run_one 16 1500
run_one  8 2400

echo "================ RESULTS ================"
python3 - <<'PY'
import re, os
root = "/scratch/moptis/c2wind/wsw_high/wrf_runs"
pat = re.compile(r"Timing for main \(dt=\s*([0-9.]+)\): time \S+ on domain\s+(\d+):\s+([0-9.]+) elapsed")

print(f"{'ranks':>6} {'d01 steps':>10} {'wall/model':>11} {'speedup':>8} {'par eff':>8} "
      f"{'d05 s/step':>11} {'d05 speedup':>12}")
res = {}
for n in (8, 16, 32, 64):
    f = f"{root}/scal_n{n:02d}/rsl.error.0000"
    if not os.path.exists(f):
        print(f"{n:>6}  (no rsl.error.0000)"); continue
    rows = [(float(a), b, float(c)) for a, b, c in pat.findall(open(f, errors="ignore").read())]
    d1 = [(dt, el) for dt, dom, el in rows if dom == "1"][1:]   # drop first (init/IO)
    d5 = sorted(el for dt, dom, el in rows if dom == "5")
    ratio = sum(el for _, el in d1) / sum(dt for dt, _ in d1) if d1 else None
    med5 = d5[len(d5) // 2] if d5 else None
    res[n] = (len(d1), ratio, med5)

b_ratio = res.get(8, (0, None, None))[1]
b_med = res.get(8, (0, None, None))[2]
for n, (k, ratio, med5) in sorted(res.items()):
    r = f"{ratio:11.3f}" if ratio else f"{'n/a':>11}"
    sp = f"{b_ratio/ratio:8.2f}" if ratio and b_ratio else f"{'n/a':>8}"
    pe = f"{100*(b_ratio/ratio)/(n/8):7.0f}%" if ratio and b_ratio else f"{'n/a':>8}"
    m = f"{med5:11.3f}" if med5 else f"{'n/a':>11}"
    ms = f"{b_med/med5:12.2f}" if med5 and b_med else f"{'n/a':>12}"
    print(f"{n:>6} {k:>10} {r} {sp} {pe} {m} {ms}")

print("\nwall/model  = wall-clock seconds per simulated second, all 5 domains (lower is better)")
print("d05 s/step  = median wall seconds for one d05 step (the dominant cost)")
print("speedup / parallel efficiency are relative to 8 ranks")
print("NOTE: history output is disabled here, so production throughput will be")
print("      somewhat slower than these numbers.")
PY
