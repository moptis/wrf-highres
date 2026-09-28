#!/bin/bash
# NOTE: #SBATCH directives cannot read site.env (sbatch parses them before the
# shell runs). Set the *_PLACEHOLDER values below, or submit with explicit flags:
#   sbatch -A $SLURM_ACCOUNT -p $PART_CPU --qos=$SLURM_QOS ...
#SBATCH --job-name=wrf-gpu
#SBATCH --output=wrf-%j.out
#SBATCH --gpus=4
#SBATCH --nodes=1
#SBATCH --account=SLURM_ACCOUNT_PLACEHOLDER
#SBATCH --exclusive
#SBATCH --partition=gpu-h100
#SBATCH --time=24:00:00

. "$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)/common.sh"

# AceCast path.  4 GPUs decompose 2 x 2, so the 10-cells-per-patch rule that
# caps the CPU run at 64 ranks is not a constraint here.
# Requires the run dir to be linked against the AceCast build, i.e. set
# wrf_root = ${ACECAST_RUN_DIR} in
# 03_prepare_runs.py before staging the runs.

. "${ACECAST_ENV}"
export ACECAST_USE_UNSUPPORTED_OPTIONS=1

cd ${CASE_ROOT}/wrf_runs/$n
ln -sf namelist.input.wrf namelist.input
mpirun -n 4 ./gpu-launch.sh ./acecast.exe
