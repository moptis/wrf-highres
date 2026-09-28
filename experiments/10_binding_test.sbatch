#!/bin/bash
#SBATCH --job-name=wswhigh-bind
#SBATCH --output=/scratch/moptis/c2wind/wsw_high/binding-%j.out
#SBATCH --nodes=1
#SBATCH --ntasks=104
#SBATCH --exclusive
#SBATCH --account=clusterwakes
#SBATCH --partition=standard
#SBATCH --time=01:30:00

# Why does `srun -n 32` (scaling test, 1.763 wall/model) beat
# `srun --exact --cpu-bind=cores -n 32` (packing test, 3.673) by 2x for the
# same 32 ranks on the same hardware?
#
# Hypothesis: without --exact, Slurm gives each rank ~3 CPUs spread over all
# NUMA domains, so each rank gets far more memory bandwidth.  WRF here is
# bandwidth-bound, so that would explain both this gap AND the poor 32->64
# scaling.  If true, packing jobs onto a node cannot preserve the efficiency
# that made 32 ranks look cheap.
#
# Same run dir, same budget, three launch styles.

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

run "srun -n 32 (implicit spread)"            "srun -n 32"
run "srun --exact --cpu-bind=cores -n 32"     "srun --exact --cpu-bind=cores -n 32"
run "srun --exact -n 32 -c 3 (3 CPUs/rank)"   "srun --exact -n 32 -c 3"
