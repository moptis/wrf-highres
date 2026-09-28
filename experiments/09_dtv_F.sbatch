#!/bin/bash
#SBATCH --job-name=dtv-F
#SBATCH --output=/scratch/moptis/c2wind/wsw_high/wrf_runs/dtv_F/dtv-%j.out
#SBATCH --nodes=1
#SBATCH --ntasks=64
#SBATCH --exclusive
#SBATCH --account=clusterwakes
#SBATCH --partition=standard
#SBATCH --time=06:00:00
# Does a larger d05 time step change the ANSWER, not just the speed?
# Config A: d01 dt=72 s, parent_time_step_ratio=[1, 3, 3, 3, 3] -> d05 dt=0.889 s.
# Runs 3 h of model time from a common initial state, d05 written hourly, so
# the fields can be differenced against config A.
module load PrgEnv-gnu/8.5.0 cray-mpich/8.1.28 cray-libsci/23.12.5 netcdf/4.9.3-cray-mpich-gcc
export MPICH_OFI_NIC_POLICY=NUMA
export OMP_NUM_THREADS=1
cd /scratch/moptis/c2wind/wsw_high/wrf_runs/dtv_F
srun -n 64 ./wrf.exe
echo "EXIT=$?  d05 frames: $(ls wrfout_d05_* 2>/dev/null | wc -l)"
