#!/bin/bash
# NOTE: #SBATCH directives cannot read site.env (sbatch parses them before the
# shell runs). Set the *_PLACEHOLDER values below, or submit with explicit flags:
#   sbatch -A $SLURM_ACCOUNT -p $PART_CPU --qos=$SLURM_QOS ...
#SBATCH --job-name=geo-wswhigh
#SBATCH --output=geogrid-%j.out
#SBATCH --ntasks=1
#SBATCH --nodes=1
#SBATCH --account=SLURM_ACCOUNT_PLACEHOLDER
#SBATCH --partition=PART_SHARED_PLACEHOLDER
#SBATCH --mem=40G
#SBATCH --time=01:00:00

. "$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)/common.sh"

# Builds geo_em.d01..d05 for the 5-domain wsw_high nest.
# Only needs to be run once, or after design_domains.py changes the grid.

module load PrgEnv-gnu/8.5.0 cray-mpich/8.1.28 cray-libsci/23.12.5 netcdf/4.9.3-cray-mpich-gcc
export MPICH_OFI_NIC_POLICY=NUMA
export OMP_NUM_THREADS=1

cd ${CASE_ROOT}/wps
cp ${CASE_ROOT}/namelist.wps .
srun -n 1 ./geogrid.exe
