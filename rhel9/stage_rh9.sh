#!/bin/bash
# Stage every block against the prebuilt WRF 4.8.0 (RHEL9) in a separate tree,
# leaving the rh8 wrf_runs/ intact as a fallback.  met_em and the 4.8.0 static
# tables are symlinked; only namelist.input is a real file.
set -u
CASE=/scratch/moptis/c2wind/wsw_high_v2
RH9=/nopt/nlr/apps/kestrel-cpu/software/wrfRHEL9/wrf-4.8.0-craype-gnu/install/WRF-4.8.0
n=0
for s in $CASE/wrf_runs/b[0-9][0-9][0-9]; do
  r=$(basename $s)
  d=$CASE/wrf_runs_rh9/$r
  mkdir -p "$d"
  find "$d" -mindepth 1 -maxdepth 1 -delete 2>/dev/null
  for f in $RH9/run/*; do ln -sf "$f" "$d"/ 2>/dev/null; done
  find "$d" -maxdepth 1 -name 'namelist.input' -delete 2>/dev/null
  find "$d" -maxdepth 1 -name '*.exe' -delete 2>/dev/null
  ln -sf $RH9/main/real.exe "$d"/real.exe
  ln -sf $RH9/main/wrf.exe  "$d"/wrf.exe
  for f in $s/met_em.d0*.nc; do ln -sf "$f" "$d"/; done
  # start from the pristine namelist, never one a restart leg has rewritten
  cp "$s/namelist.input.fresh" "$d/namelist.input"
  cp "$CASE/myoutfields.txt" "$d"/ 2>/dev/null
  n=$((n+1))
done
echo "staged $n blocks under $CASE/wrf_runs_rh9"
