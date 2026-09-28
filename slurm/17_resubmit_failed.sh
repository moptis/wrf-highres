#!/bin/bash
# Rerun affected blocks under ADAPTIVE time stepping.
#
# The fixed step (d05 = 1.333 s) blew up on 14/40 blocks and damped 7 more.
# Under adaptive, each domain derives its own step from its own Courant number
# -- including d05, which is the one that ran away -- so parent_time_step_ratio
# becomes advisory and no hand-tuned constant has to hold across 24 years of
# conditions.  Starting step is dropped to 40 s so the first minutes are
# conservative: every failure occurred within ~4 minutes of model time.
#
#   scripts/17_resubmit_failed.sh [blocks...]      (default: tmy/rerun_blocks.txt)
set -u
. "$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)/common.sh"
ROOT=$CASE_ROOT
blocks=("$@")
[ ${#blocks[@]} -eq 0 ] && mapfile -t blocks < <(grep -v '^$' $ROOT/tmy/rerun_blocks.txt)

for RUN in "${blocks[@]}"; do
    d=$ROOT/wrf_runs/$RUN
    [ -f "$d/wrfinput_d05" ] || { echo "SKIP $RUN (no wrfinput)"; continue; }
    squeue -u $USER -h -n "w-$RUN" -o %T | grep -q . && { echo "SKIP $RUN (still queued)"; continue; }

    # keep the bad attempt rather than overwrite it -- the damped runs are the
    # only way to measure how much the damping actually distorted statistics
    a="$d/attempt_dt1p333"
    if ls $d/wrfout_d0*_* >/dev/null 2>&1 || ls $d/rsl.* >/dev/null 2>&1; then
        mkdir -p "$a"; mv $d/wrfout_d0*_* $d/rsl.* "$a/" 2>/dev/null
    fi

    python3 - "$d/namelist.input.wrf" <<'PY'
import sys
p = sys.argv[1]; out = []
for line in open(p).read().splitlines():
    t = line.strip()
    if   t.startswith("use_adaptive_time_step"): out.append(" use_adaptive_time_step              = .true.,")
    elif t.startswith("time_step "):             out.append(" time_step                           = 40,")
    elif t.startswith("parent_time_step_ratio"): out.append(" parent_time_step_ratio              = 1, 3, 3, 3, 3,")
    else: out.append(line)
open(p, "w").write("\n".join(out) + "\n")
PY
    w=$(sbatch --parsable -J "w-$RUN" --export=ALL,domain=wsw_high,n=$RUN $ROOT/scripts/04_wrf_cpu.sbatch)
    echo "$RUN wrf=$w"
done
