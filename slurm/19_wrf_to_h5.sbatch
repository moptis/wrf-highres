#!/bin/bash
# NOTE: #SBATCH directives cannot read site.env (sbatch parses them before the
# shell runs). Set the *_PLACEHOLDER values below, or submit with explicit flags:
#   sbatch -A $SLURM_ACCOUNT -p $PART_CPU --qos=$SLURM_QOS ...
#SBATCH --job-name=wswhigh-h5
#SBATCH --output=${CASE_ROOT}/h5-%j.out
#SBATCH --nodes=1
#SBATCH --ntasks=104
#SBATCH --exclusive
#SBATCH --account=SLURM_ACCOUNT_PLACEHOLDER
#SBATCH --qos=SLURM_QOS_PLACEHOLDER
#SBATCH --partition=PART_DEBUG_PLACEHOLDER
#SBATCH --time=04:00:00

# Assemble d05 output into the analysis h5.
#
# Reads d05_ingest/, NOT wrf_runs/ -- get_file_dirs() uses os.walk, so pointing
# it at wrf_runs would also pull in the 26 benchmark directories AND each
# block's attempt_dt1p333/ subdir, which holds the blown-up fixed-timestep
# output on the same dates as the good runs.
#
# spinup_time=6 drops each block's first 6 h, leaving exactly its 24 sample hours.

. "${WRFHR_REPO}/slurm/common.sh"
. "$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)/common.sh"
ROOT=$CASE_ROOT
wakemap_processor wrf-to-h5 \
  --h5_file=$ROOT/processed/wsw_high.h5 \
  --wrf_dir=$ROOT/d05_ingest/ \
  --file_prefix=wrfout_d05 \
  --dt=1h \
  --spinup_time=6 \
  --npz_dir=$ROOT/npz/ \
  --max_workers=104 \
  --clobber
echo "EXIT=$?"
