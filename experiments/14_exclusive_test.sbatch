#!/bin/bash
#SBATCH --job-name=wswhigh-excl
#SBATCH --output=/scratch/moptis/c2wind/wsw_high/exclusive-%j.out
#SBATCH --nodes=1
#SBATCH --ntasks=104
#SBATCH --exclusive
#SBATCH --account=clusterwakes
#SBATCH --partition=standard
#SBATCH --time=01:00:00

# Is --exclusive worth it, or should production use `shared` with 64 cores?
#
# With --exclusive the 64 ranks spread over all 8 NUMA domains and get the whole
# node's memory bandwidth, even though 40 cores run nothing.  On `shared` you
# bill 64/104 of a node but the ranks are confined to 64 cores.  WRF here is
# bandwidth-bound, so the question is whether the confinement penalty exceeds
# the 1.6x billing saving.

module load PrgEnv-gnu/8.5.0 cray-mpich/8.1.28 cray-libsci/23.12.5 netcdf/4.9.3-cray-mpich-gcc
export MPICH_OFI_NIC_POLICY=NUMA
export OMP_NUM_THREADS=1
ROOT=/scratch/moptis/c2wind/wsw_high
cd $ROOT/wrf_runs/pack_a

run () {
    echo "================ $1 ================"
    rm -f rsl.*
    timeout 900s $2 ./wrf.exe > /dev/null 2>&1
    echo -n "  "
    /home/moptis/miniconda3/envs/default/bin/python $ROOT/profile_run.py rsl.error.0000 2>&1 | tail -1
}

run "64 ranks, whole node (what production uses)" "srun -n 64"
run "64 ranks confined to 64 cores (= shared)"    "srun --exact --cpu-bind=cores -n 64"
