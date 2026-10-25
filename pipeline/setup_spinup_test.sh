#!/bin/bash
# Build the 6 h vs 12 h spinup experiment for one TMY block.
#
#   setup_spinup_test.sh <case_root> <block> <template_run_dir> <era5_dir>
#
# Two runs over the SAME calendar day, ending at the same hour, differing only
# in start time:
#     spin06  starts 18 UTC   6 h spinup   18 h sim
#     spin12  starts 12 UTC  12 h spinup   24 h sim
# Both retain 00-12 UTC, so the comparison is hour-for-hour on identical
# weather and spinup length is the only free variable.
#
# This is the control the "discard the first N retained hours" test cannot be:
# that one removes specific LOCAL hours (run-age and local hour are perfectly
# aliased inside a block), so it confounds spinup with the diurnal cycle.
#
# Everything except the eight date lines is inherited from the template run
# dir, so physics cannot drift between the experiment and the campaign.
set -eu
ROOT=$1; BLOCK=$2; TMPL=$3; ERA5=$4
S=$ROOT/spinup_test
[ -d "$TMPL" ] || { echo "no template run dir $TMPL" >&2; exit 1; }

read -r START < <(awk -F, -v b="$BLOCK" '$1==b{print $2}' "$ROOT/tmy/run_manifest.csv")
[ -n "${START:-}" ] || { echo "$BLOCK not in manifest" >&2; exit 1; }
D0=${START%% *}; Y=${D0%%-*}; MO=$(echo "$D0" | cut -d- -f2); DY=${D0##*-}
D1=$(date -u -d "$D0 +1 day" +%F); Y1=${D1%%-*}; MO1=$(echo "$D1" | cut -d- -f2); DY1=${D1##*-}
echo "$BLOCK: block start $START -> test start ${D0} 12:00 UTC, both end ${D1} 12:00 UTC"

# --- metgrid over the widened window (12 UTC day0 .. 12 UTC day1) -----------
mkdir -p "$S/metgrid"
cd "$S/metgrid"
ln -sfn "$ROOT/wps/metgrid.exe" metgrid.exe
[ -e "$ROOT/wps/metgrid" ] && ln -sfn "$ROOT/wps/metgrid" metgrid
for f in "$ROOT"/wps/geo_em.d0*.nc; do ln -sfn "$f" .; done
# BOTH streams.  Linking only ERA5_PRES leaves NUM_METGRID_SOIL_LEVELS = 0 while
# metgrid still reports success; real.exe then fails much later and obscurely.
n=0
for t in 12 15 18 21; do for p in ERA5_PRES ERA5_SURF; do
  ln -sfn "$ERA5/${p}:${D0}_${t}" . && n=$((n+1)); done; done
for t in 00 03 06 09 12; do for p in ERA5_PRES ERA5_SURF; do
  ln -sfn "$ERA5/${p}:${D1}_${t}" . && n=$((n+1)); done; done
echo "  ERA5 linked: $n (expect 18)"
sed -e "s/ start_date = .*/ start_date = $(printf "'%s_12:00:00', " "$D0" "$D0" "$D0" "$D0" "$D0")/" \
    -e "s/ end_date   = .*/ end_date   = $(printf "'%s_12:00:00', " "$D1" "$D1" "$D1" "$D1" "$D1")/" \
    "$TMPL/namelist.wps" > namelist.wps

# --- the two run dirs -------------------------------------------------------
mk () {  # $1=name  $2=start hour  $3=start day
  d=$S/$1; mkdir -p "$d"
  for e in "$TMPL"/*; do b=$(basename "$e")
    case $b in met_em.*|wrfout_*|wrfinput_*|wrfbdy_*|wrflowinp_*|wrfrst_*|rsl.*|namelist.input|*.out|*.log) continue;; esac
    cp -a "$e" "$d/"
  done
  sed -e "s/^ start_year .*/ start_year                          = $Y, $Y, $Y, $Y, $Y/" \
      -e "s/^ start_month .*/ start_month                         = $MO, $MO, $MO, $MO, $MO/" \
      -e "s/^ start_day .*/ start_day                           = $3, $3, $3, $3, $3/" \
      -e "s/^ start_hour .*/ start_hour                          = $2, $2, $2, $2, $2/" \
      -e "s/^ end_year .*/ end_year                            = $Y1, $Y1, $Y1, $Y1, $Y1/" \
      -e "s/^ end_month .*/ end_month                           = $MO1, $MO1, $MO1, $MO1, $MO1/" \
      -e "s/^ end_day .*/ end_day                             = $DY1, $DY1, $DY1, $DY1, $DY1/" \
      -e "s/^ end_hour .*/ end_hour                            = 12, 12, 12, 12, 12/" \
      "$TMPL/namelist.input" > "$d/namelist.input"
  echo "  $1: start ${3} ${2}:00 UTC"
}
mk spin06 18 "$DY"
mk spin12 12 "$DY"
echo "physics identical to template: $(diff <(sed -n '/&physics/,/^\//p' "$TMPL/namelist.input") \
  <(sed -n '/&physics/,/^\//p' "$S/spin12/namelist.input") >/dev/null && echo yes || echo NO)"
echo "next: run metgrid in $S/metgrid, link met_em into each run dir, then real+wrf"
