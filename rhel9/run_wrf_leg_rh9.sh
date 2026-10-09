#!/bin/bash
# One leg of a chained WRF run, RHEL9 / prebuilt WRF 4.8.0 build.  Idempotent, so every leg can use this script:
#   - block already finished        -> exit 0 without burning the allocation
#   - a complete restart set exists -> resume from the latest one
#   - otherwise                     -> fresh start
#
# standby QOS caps at 24 h but a block needs ~30 h, so legs are chained with
# --dependency=afterany.  restart_interval=180 means a leg loses at most 3
# model-hours.  io_form_restart=102 writes one file per rank, so every leg MUST
# use the same 64 ranks.
set -u
d=$1
cd "$d" || exit 1

# Completion test: the wrfout_d05 frame for the namelist's END time.  end_* is
# stable across restarts (only start_* is rewritten), so this stays correct.
g() { grep -E "^ *$1 " namelist.input | head -1 | sed 's/.*= *//' | cut -d, -f1 | tr -d ' '; }
# Values are already zero-padded in the namelist, so concatenate as strings --
# printf "%02d" would abort on "08"/"09" as an invalid octal number.
END="$(g end_year)-$(g end_month)-$(g end_day)_$(g end_hour):$(g end_minute):00"
if [ -f "wrfout_d05_${END}" ]; then
  echo "$(basename $d): already complete through ${END}"; exit 0
fi

# Latest restart time written for ALL five domains (a partial set is unusable).
t=$(for dom in 1 2 3 4 5; do
      ls wrfrst_d0${dom}_* 2>/dev/null | sed "s|.*wrfrst_d0${dom}_||; s|_[0-9]*$||" | sort -u
    done | sort | uniq -c | awk '$1==5 {print $2}' | sort | tail -1)

# Restarting costs 4.5-6x per step (measured on wsw_high_v2: 0.77 -> 3.45 s/step
# for the same blocks, same nodes, same binary).  So resuming is only worth it
# when little work remains.  Cold redoes T_total at 1x; resuming does
# T_remaining at ~6x, so cold wins whenever T_remaining > T_total/6.
if [ -n "$t" ]; then
  _secs() { date -u -d "$(echo $1 | sed 's/_/ /')" +%s 2>/dev/null; }
  _start=$(grep -E "^ *start_" namelist.input.fresh | sed 's/.*= *//' | cut -d, -f1 | tr -d ' ' | paste -sd' ' - | awk '{printf "%s-%s-%s_%s:%s:00",$1,$2,$3,$4,$5}')
  _tot=$(( ($(_secs "$END") - $(_secs "$_start")) ))
  _rem=$(( ($(_secs "$END") - $(_secs "$t")) ))
  if [ "$_tot" -gt 0 ] && [ "$_rem" -gt $(( _tot / 6 )) ]; then
    echo "$(basename $d): $(( _rem/3600 ))h of $(( _tot/3600 ))h remain (> 1/6) -- COLD restart beats a 6x resume"
    mkdir -p _superseded_rst
    find . -maxdepth 1 -name 'wrfrst_*' -exec mv -t _superseded_rst {} + 2>/dev/null
    t=""
  fi
fi

if [ -n "$t" ]; then
  echo "$(basename $d): resuming from $t (target $END)"
  python3 - namelist.input "$t" <<'PY'
import sys
p, t = sys.argv[1], sys.argv[2]
y, mo, dy, hh, mi = t[0:4], t[5:7], t[8:10], t[11:13], t[14:16]
five = lambda v: ", ".join([v] * 5)
out = []
for line in open(p).read().splitlines():
    s = line.strip()
    if   s.startswith("restart "):     out.append(" restart                             = .true.,")
    elif s.startswith("start_year"):   out.append(f" start_year                          = {five(y)}")
    elif s.startswith("start_month"):  out.append(f" start_month                         = {five(mo)}")
    elif s.startswith("start_day"):    out.append(f" start_day                           = {five(dy)}")
    elif s.startswith("start_hour"):   out.append(f" start_hour                          = {five(hh)}")
    elif s.startswith("start_minute"): out.append(f" start_minute                        = {five(mi)}")
    else: out.append(line)
open(p, "w").write("\n".join(out) + "\n")
PY
else
  echo "$(basename $d): fresh start (target $END)"
  sed -i 's/^ restart  *= .*/ restart                             = .false.,/' namelist.input
fi

# RHEL9: the wrf/4.8.0-craype-gnu module is broken (see rh9_env.sh), so the
# environment is reproduced by hand.  --overlap is required per the build README.
source /scratch/CASE/rh9_env.sh
srun --overlap -n 64 ./wrf.exe
