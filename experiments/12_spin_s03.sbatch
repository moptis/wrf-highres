#!/bin/bash
#SBATCH --job-name=spin-s03
#SBATCH --output=/scratch/moptis/c2wind/wsw_high/wrf_runs/spin_s03/spin-%j.out
#SBATCH --nodes=1
#SBATCH --ntasks=64
#SBATCH --exclusive
#SBATCH --account=clusterwakes
#SBATCH --partition=standard
#SBATCH --time=40:00:00
# Spin-up convergence: run s03 ends at the same valid time as the others but
# starts earlier/later, so differencing d05 over 2018-09-05 00Z..12Z shows how
# much of the field is still remembering its initial condition.
module load PrgEnv-gnu/8.5.0 cray-mpich/8.1.28 cray-libsci/23.12.5 netcdf/4.9.3-cray-mpich-gcc
export MPICH_OFI_NIC_POLICY=NUMA
export OMP_NUM_THREADS=1
cd /scratch/moptis/c2wind/wsw_high/wrf_runs/spin_s03
srun -n 1 ./metgrid.exe > metgrid.log 2>&1 || { echo "METGRID FAILED"; exit 1; }
srun -n 64 ./real.exe    > real.log    2>&1 || { echo "REAL FAILED"; exit 1; }
srun -n 64 ./wrf.exe
echo "EXIT=$?  d05 frames: $(ls wrfout_d05_* 2>/dev/null | wc -l)"
