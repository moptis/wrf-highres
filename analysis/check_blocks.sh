#!/bin/bash
# Progress and failure summary for the 40-block campaign.
. "$(cd "$(dirname "$0")/../slurm" && pwd)/common.sh"
ROOT=$CASE_ROOT
done_=0; running=0; pend=0; fail=0; failed=""
for d in $ROOT/wrf_runs/b[0-9][0-9][0-9]; do
    r=$(basename $d)
    nf=$(ls $d/wrfout_d05_* 2>/dev/null | wc -l)
    st=$(squeue -u $USER -h -n "w-$r" -o %T 2>/dev/null | head -1)
    if grep -qs "SUCCESS COMPLETE WRF" $d/rsl.error.0000 2>/dev/null; then
        done_=$((done_+1))
    elif [ "$st" = RUNNING ]; then running=$((running+1))
    elif [ -n "$st" ]; then pend=$((pend+1))
    else fail=$((fail+1)); failed="$failed $r($nf)"; fi
done
echo "complete=$done_  running=$running  pending=$pend  no-job-and-incomplete=$fail"
[ -n "$failed" ] && echo "needs attention:$failed"
exit 0
