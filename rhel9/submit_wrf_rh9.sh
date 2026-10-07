#!/bin/bash
# 40 blocks on RHEL9, each as 3 chained standby legs of 23 h.
# standby honours the small aiweather allocation; standard-stdby caps at 24 h
# and a block needs ~30 h, so legs are chained with --dependency=afterany.
# Each leg runs the same idempotent script and exits in seconds if the block is
# already complete, so surplus legs cost nothing.
set -u
CASE=/scratch/moptis/c2wind/wsw_high_v2
for d in $CASE/wrf_runs_rh9/b[0-9][0-9][0-9]; do
  r=$(basename $d)
  [ -f $d/wrfinput_d05 ] || { echo "SKIP $r (no wrfinput)"; continue; }
  prev=""
  for leg in 1 2 3; do
    dep=""; [ -n "$prev" ] && dep="--dependency=afterany:$prev"
    prev=$(sbatch --parsable -J "x$leg-$r" -p standard --qos=standby \
            -N1 -n64 --exclusive -t 23:00:00 -A aiweather \
            -o $d/wrf-leg${leg}-%j.out $dep \
            --wrap "$CASE/run_wrf_leg_rh9.sh $d")
  done
  echo "$r -> $prev"
done
