#!/bin/bash
# One leg of a chained WRF run.  Idempotent, so every leg can use this script:
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
    # Restart dumps do NOT land on round times under adaptive dt -- LGW writes
    # them at e.g. 19:00:49 -- and WRF builds the wrfrst filename from the
    # namelist start time.  Omitting start_second makes it look for ..._19:00:00
    # and abort with "error opening wrfrst_d01_... for reading".
    elif s.startswith("start_second"): out.append(f" start_second                        = {five(ss)}")
    else: out.append(line)
open(p, "w").write("\n".join(out) + "\n")
PY
else
  echo "$(basename $d): fresh start (target $END)"
  sed -i 's/^ restart  *= .*/ restart                             = .false.,/' namelist.input
fi

module load PrgEnv-gnu/8.5.0 cray-mpich/8.1.28 cray-libsci/23.12.5 netcdf/4.9.3-cray-mpich-gcc
export MPICH_OFI_NIC_POLICY=NUMA
export OMP_NUM_THREADS=1
srun -n 64 ./wrf.exe
