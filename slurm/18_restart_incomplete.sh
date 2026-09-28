#!/bin/bash
# Resume blocks that timed out, from their latest restart dump.
#
# restart_interval=180 means a full model state is written every 3 model-hours,
# so a timed-out run resumes from at most 3 h back instead of redoing ~24 h.
# io_form_restart=102 writes one file per rank, so the restart MUST use the
# same 64 ranks it was written with.
#
#   scripts/18_restart_incomplete.sh [--dry] [blocks...]
set -u
. "$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)/common.sh"
ROOT=$CASE_ROOT
DRY=""; [ "${1:-}" = "--dry" ] && { DRY=1; shift; }
blocks=("$@")
if [ ${#blocks[@]} -eq 0 ]; then
    mapfile -t blocks < <(for d in $ROOT/wrf_runs/b[0-9][0-9][0-9]; do
        b=$(basename $d); n=$(ls $d/wrfout_d05_* 2>/dev/null | wc -l)
        [ "$n" -gt 0 ] && [ "$n" -lt 30 ] && \
          ! squeue -u $USER -h -n "w-$b" -o %T | grep -q . && echo $b; done)
fi

for RUN in "${blocks[@]}"; do
    d=$ROOT/wrf_runs/$RUN
    # latest restart time present for ALL five domains
    t=$(for dom in 1 2 3 4 5; do
            ls $d/wrfrst_d0${dom}_* 2>/dev/null | sed "s|.*wrfrst_d0${dom}_||; s|_[0-9]*$||" | sort -u
        done | sort | uniq -c | awk '$1==5 {print $2}' | sort | tail -1)
    [ -z "$t" ] && { echo "SKIP $RUN (no complete restart set)"; continue; }
    y=${t:0:4}; mo=${t:5:2}; dy=${t:8:2}; hh=${t:11:2}; mi=${t:14:2}
    echo "$RUN: resume from $t  ($(ls $d/wrfout_d05_* 2>/dev/null | wc -l)/30 frames done)"
    [ -n "$DRY" ] && continue

    python3 - "$d/namelist.input.wrf" "$y" "$mo" "$dy" "$hh" "$mi" <<'PY'
import sys
p, y, mo, dy, hh, mi = sys.argv[1:7]
five = lambda v: ", ".join([str(v)] * 5)
out = []
for line in open(p).read().splitlines():
    t = line.strip()
    if   t.startswith("restart "):      out.append(" restart                             = .true.,")
    elif t.startswith("start_year"):    out.append(f" start_year                          = {five(y)}")
    elif t.startswith("start_month"):   out.append(f" start_month                         = {five(mo)}")
    elif t.startswith("start_day"):     out.append(f" start_day                           = {five(dy)}")
    elif t.startswith("start_hour"):    out.append(f" start_hour                          = {five(hh)}")
    elif t.startswith("start_minute"):  out.append(f" start_minute                        = {five(mi)}")
    else: out.append(line)
open(p, "w").write("\n".join(out) + "\n")
PY
    w=$(sbatch --parsable -J "w-$RUN" --export=ALL,domain=wsw_high,n=$RUN $ROOT/scripts/04_wrf_cpu.sbatch)
    echo "   resubmitted wrf=$w"
done
