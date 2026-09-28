#!/bin/bash
# NOTE: #SBATCH directives cannot read site.env (sbatch parses them before the
# shell runs). Set the *_PLACEHOLDER values below, or submit with explicit flags:
#   sbatch -A $SLURM_ACCOUNT -p $PART_CPU --qos=$SLURM_QOS ...
#SBATCH --job-name=real
#SBATCH --output=real-%j.out
#SBATCH --nodes=1
#SBATCH --ntasks=32
#SBATCH --mem=150G
#SBATCH --account=SLURM_ACCOUNT_PLACEHOLDER
#SBATCH --partition=PART_SHARED_PLACEHOLDER
#SBATCH --time=00:20:00

. "$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)/common.sh"

# real.exe takes ~1 minute for this nest.  Asking for an exclusive node for an
# hour made it unschedulable behind a depleted fairshare -- it could not
# backfill into idle nodes because it wanted a whole node for a whole hour.
# 32 ranks on `shared` for 20 min backfills almost anywhere.
# (32 ranks is 8x4 on d01's 80 cells -- still above WRF's 10-cells-per-patch rule.)

module load PrgEnv-gnu/8.5.0 cray-mpich/8.1.28 cray-libsci/23.12.5 netcdf/4.9.3-cray-mpich-gcc
export MPICH_OFI_NIC_POLICY=NUMA
export OMP_NUM_THREADS=1

cd ${CASE_ROOT}/wrf_runs/$n
ln -sf namelist.input.real namelist.input
srun -n 32 ./real.exe
