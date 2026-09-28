#!/bin/bash
# NOTE: #SBATCH directives cannot read site.env (sbatch parses them before the
# shell runs). Set the *_PLACEHOLDER values below, or submit with explicit flags:
#   sbatch -A $SLURM_ACCOUNT -p $PART_CPU --qos=$SLURM_QOS ...
#SBATCH --job-name=metgrid
#SBATCH --output=metgrid-%j.out
#SBATCH --ntasks=1
#SBATCH --nodes=1
#SBATCH --account=SLURM_ACCOUNT_PLACEHOLDER
#SBATCH --partition=PART_SHARED_PLACEHOLDER
#SBATCH --mem=60G
#SBATCH --time=01:00:00

. "$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)/common.sh"

# Expects $domain (scenario name) and $n (4-digit run dir) in the environment,
# matching the convention used by 03_prepare_runs.py / launch_runs.sh.

module load PrgEnv-gnu/8.5.0 cray-mpich/8.1.28 cray-libsci/23.12.5 netcdf/4.9.3-cray-mpich-gcc
export MPICH_OFI_NIC_POLICY=NUMA
export OMP_NUM_THREADS=1

cd ${CASE_ROOT}/wrf_runs/$n
srun -n 1 ./metgrid.exe
