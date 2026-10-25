#!/bin/bash
# Stage every block against the prebuilt WRF 4.8.0 (RHEL9) in a separate tree,
# leaving the rh8 wrf_runs/ intact as a fallback.  met_em and the 4.8.0 static
# tables are symlinked; only namelist.input is a real file.
set -u
REPO=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
[ -f "$REPO/site.env" ] && . "$REPO/site.env"        # picks up SHRUB_Z0
CASE=/scratch/moptis/c2wind/wsw_high_v2
# Our own build: Fitch density correction + NLCD40 shrub z0 0.20 baked into
# run/VEGPARM.TBL.  The /nopt module install is still needed at RUNTIME for
# the netcdf/hdf5/mpich libraries this binary links against, but no longer
# supplies executables or tables.
RH9=${WRF_BUILD:-/home/moptis/WRF}
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
  # Roughness override.  The symlink loop above pulls in the stock VEGPARM.TBL,
  # which gives NLCD40 class 32 (Shrub/Scrub) Z0MIN/Z0MAX = 0.01/0.05 m -- far
  # too smooth at LGW.  rm the symlink first: cp would try to write through it
  # into the read-only WRF install.
  if [ -n "${SHRUB_Z0:-}" ]; then
    rm -f "$d/VEGPARM.TBL"
    "$REPO/tools/make_vegparm_shrub_z0.sh" "$SHRUB_Z0" "$RH9/run/VEGPARM.TBL" \
        "$d/VEGPARM.TBL" >/dev/null
  fi
  n=$((n+1))
done
echo "staged $n blocks under $CASE/wrf_runs_rh9"
