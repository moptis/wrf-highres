#!/bin/bash
#SBATCH --job-name=cad10
#SBATCH --output=/scratch/moptis/c2wind/wsw_high/wrf_runs/cad10/cad-%j.out
#SBATCH --nodes=1
#SBATCH --ntasks=64
#SBATCH --exclusive
#SBATCH --account=clusterwakes
#SBATCH --partition=standard
#SBATCH --qos=high
#SBATCH --time=24:00:00
# One block rerun with 10-minute d05 output, so the hourly-vs-10-min question
# can be answered AT 100 m rather than extrapolated from the 1 km TMY.
module load PrgEnv-gnu/8.5.0 cray-mpich/8.1.28 cray-libsci/23.12.5 netcdf/4.9.3-cray-mpich-gcc
export MPICH_OFI_NIC_POLICY=NUMA
export OMP_NUM_THREADS=1
cd /scratch/moptis/c2wind/wsw_high/wrf_runs/cad10
ln -sf namelist.input.real namelist.input
srun -n 32 ./real.exe > real.log 2>&1 || { echo "REAL FAILED"; exit 1; }
ln -sf namelist.input.wrf namelist.input
srun -n 64 ./wrf.exe
echo "EXIT=$?  d05 frames: $(ls wrfout_d05_* 2>/dev/null | wc -l)"
