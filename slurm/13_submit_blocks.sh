#!/bin/bash
# Submit the sampled blocks: metgrid -> real -> wrf, chained per block.
#
#   scripts/13_submit_blocks.sh              # all runs in the manifest
#   scripts/13_submit_blocks.sh b001 b005    # a subset
#   DRYRUN=1 scripts/13_submit_blocks.sh     # print without submitting
#
# Each block is independent, so these fan out as wide as the queue allows;
# wall-clock for the whole set is one run (~17 h), not the sum.
set -u
. "$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)/common.sh"
ROOT=$CASE_ROOT
SCEN=wsw_high
MAN=$ROOT/tmy/run_manifest.csv

runs=("$@")
if [ ${#runs[@]} -eq 0 ]; then
    mapfile -t runs < <(tail -n +2 "$MAN" | cut -d, -f1)
fi

sub () {  # sub <script> <jobname> <dependency-or-empty>
    local dep=""
    [ -n "$3" ] && dep="--dependency=afterok:$3"
    if [ -n "${DRYRUN:-}" ]; then echo "    sbatch $dep -J $2 $1" >&2; echo "0"; return; fi
    sbatch --parsable $dep -J "$2" --export=ALL,domain=$SCEN,n=$RUN "$1"
}

n_ok=0
for RUN in "${runs[@]}"; do
    d=$ROOT/wrf_runs/$RUN
    if [ ! -f "$d/namelist.input.wrf" ]; then
        echo "SKIP $RUN -- not staged (run stage_blocks.py first)"; continue
    fi
    if ls "$d"/wrfout_d05_* >/dev/null 2>&1; then
        echo "SKIP $RUN -- already has d05 output"; continue
    fi
    m=$(sub $ROOT/scripts/02_metgrid.sbatch "m-$RUN" "")
    r=$(sub $ROOT/scripts/03_real.sbatch    "r-$RUN" "$m")
    w=$(sub $ROOT/scripts/04_wrf_cpu.sbatch "w-$RUN" "$r")
    echo "$RUN  metgrid=$m real=$r wrf=$w"
    n_ok=$((n_ok+1))
done
echo "submitted $n_ok chains"
