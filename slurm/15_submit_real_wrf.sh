#!/bin/bash
# Resubmit real -> wrf for staged blocks whose met_em is already built.
set -u
. "$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)/common.sh"
ROOT=$CASE_ROOT
SCEN=wsw_high
for d in $ROOT/wrf_runs/b[0-9][0-9][0-9]; do
    RUN=$(basename $d)
    ls $d/met_em.d05.* >/dev/null 2>&1 || { echo "SKIP $RUN (no met_em)"; continue; }
    grep -qs "SUCCESS COMPLETE WRF" $d/rsl.error.0000 && { echo "SKIP $RUN (done)"; continue; }
    r=$(sbatch --parsable -J "r-$RUN" --export=ALL,domain=$SCEN,n=$RUN $ROOT/scripts/03_real.sbatch)
    w=$(sbatch --parsable --dependency=afterok:$r -J "w-$RUN" --export=ALL,domain=$SCEN,n=$RUN $ROOT/scripts/04_wrf_cpu.sbatch)
    echo "$RUN real=$r wrf=$w"
done
