#!/bin/bash
# Stage Copernicus GLO-30 (30 m DSM) for CONUS + Canada.
#
# One dataset across the border on purpose: a 3DEP/Copernicus seam at 49N would
# put a ~12 m terrain step through forested border regions. Measured DSM-vs-
# bare-earth bias is a smooth offset (+0.3 m desert, +11.6 m dense conifer) with
# no extra small-scale structure, so it does not inject spurious terrain forcing.
#
# Login node on purpose: I/O, not compute, so it costs no allocation.
# Re-running is safe -- tiles already present are skipped.
set -u
DEM=/scratch/moptis/dem/cop30_na
SRC=s3://copernicus-dem-30m
LIST=/scratch/moptis/dem/cop30_na_tiles.txt
mkdir -p "$DEM"
grab() {
  t=$1; f="$DEM/${t}.tif"
  [ -s "$f" ] && return 0
  /home/moptis/bin/aws s3 cp --no-sign-request --only-show-errors \
      "$SRC/${t}/${t}.tif" "$f" || echo "FAILED $t" >> /scratch/moptis/dem/cop30_failed.txt
}
export -f grab; export DEM SRC
xargs -a "$LIST" -P 8 -I{} bash -c 'grab {}'
echo "done: $(ls "$DEM"/*.tif 2>/dev/null | wc -l) tiles, $(du -sh "$DEM" | cut -f1)"
