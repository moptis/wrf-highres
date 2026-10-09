#!/bin/bash
# NOTE: #SBATCH directives cannot read site.env (sbatch parses them before the
# shell runs). Set the *_PLACEHOLDER values below, or submit with explicit flags:
#   sbatch -A $SLURM_ACCOUNT -p $PART_CPU --qos=$SLURM_QOS ...
#SBATCH --job-name=wrf
#SBATCH --output=wrf-%j.out
#SBATCH --ntasks=64
#SBATCH --nodes=1
#SBATCH --account=SLURM_ACCOUNT_PLACEHOLDER
#SBATCH --partition=PART_CPU_PLACEHOLDER
#SBATCH --qos=SLURM_QOS_PLACEHOLDER
#SBATCH --exclusive
#SBATCH --time=48:00:00

. "$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)/common.sh"

# See 03_real.sbatch for why the rank count is capped at 64.

module load PrgEnv-gnu/8.5.0 cray-mpich/8.1.28 cray-libsci/23.12.5 netcdf/4.9.3-cray-mpich-gcc
export MPICH_OFI_NIC_POLICY=NUMA
export OMP_NUM_THREADS=1

cd ${CASE_ROOT}/wrf_runs/$n
ln -sf namelist.input.wrf namelist.input
srun -n 64 ./wrf.exe
