#!/bin/bash
# Stage USGS 3DEP 1-arcsec (30 m, bare-earth) GeoTIFFs for CONUS.
# Login node on purpose: this is I/O, not compute, so it costs no allocation.
# 8 streams keeps it polite; re-running skips tiles already present.
set -u
DEM=/scratch/moptis/dem/3dep_1arcsec
SRC=s3://prd-tnm/StagedProducts/Elevation/1/TIFF/current
mkdir -p "$DEM"
fetch() {
  t=$1; f="$DEM/USGS_1_${t}.tif"
  [ -s "$f" ] && return 0
  /home/moptis/bin/aws s3 cp --no-sign-request --only-show-errors \
      "$SRC/$t/USGS_1_${t}.tif" "$f" || echo "FAILED $t" >> "$DEM/../failed.txt"
}
export -f fetch; export DEM SRC
xargs -a /scratch/moptis/dem/conus_tiles.txt -P 8 -I{} bash -c 'fetch {}'
echo "done: $(ls $DEM/*.tif 2>/dev/null | wc -l) tiles, $(du -sh $DEM | cut -f1)"
