#!/bin/bash
# real.exe for every block against the prebuilt WRF 4.8.0 on RHEL9.
# 8 ranks / 40G ran one block in 63 s during validation.
set -u
CASE=/scratch/moptis/c2wind/wsw_high_v2
for d in $CASE/wrf_runs_rh9/b[0-9][0-9][0-9]; do
  r=$(basename $d)
  [ -f $d/wrfinput_d05 ] && [ -f $d/wrfbdy_d01 ] && { echo "SKIP $r"; continue; }
  sbatch --parsable -J "r9-$r" -p short -N1 -n8 --mem=40G -t 00:25:00 -A aiweather \
    -o $d/real-%j.out \
    --wrap "source $CASE/rh9_env.sh; cd $d && srun --overlap -n 8 ./real.exe"
done
