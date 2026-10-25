#!/bin/bash
# Emit a VEGPARM.TBL with NLCD40 class 32 (Shrub/Scrub) roughness overridden.
#
# WRF ships Z0MIN/Z0MAX = 0.01/0.05 m for this class.  Measured against the five
# LGW masts that is far too smooth: raising it to 0.20/0.20 cut the 80 m
# long-term bias from +1.14 to +0.50 m/s and the hourly mast bias from +1.21 to
# +0.58, with u* rising 0.419 -> 0.535.  Flat (Z0MIN == Z0MAX) so the realised
# z0 is not greenness-interpolated and matches Noah-MP's single Z0MVT.
#
# Generated from the live stock table rather than kept as a frozen copy, so a
# WRF upgrade's other VEGPARM changes are picked up automatically.
#
# usage: make_vegparm_shrub_z0.sh <z0_m> <stock_VEGPARM.TBL> <output>
set -euo pipefail
Z0=${1:?z0 in metres, e.g. 0.20}
SRC=${2:?path to stock VEGPARM.TBL}
OUT=${3:?output path}
[[ -f $SRC ]] || { echo "make_vegparm: no such table: $SRC" >&2; exit 1; }

awk -v z0="$Z0" '
  /^[A-Z][A-Z0-9_]*$/ { blk = $0 }            # block marker, e.g. USGS, NLCD40
  blk == "NLCD40" && $1 == "32," {
      $15 = sprintf("%.2f,", z0); $16 = sprintf("%.2f,", z0); hit++
  }
  { print }
  END { if (hit != 1) { printf("make_vegparm: expected 1 NLCD40 class-32 row, got %d\n", hit) > "/dev/stderr"; exit 1 } }
' "$SRC" > "$OUT.tmp" && mv "$OUT.tmp" "$OUT"

echo "  VEGPARM.TBL -> $OUT  (NLCD40 class 32 Z0MIN=Z0MAX=$Z0 m)"
grep -m1 "^32," "$OUT" | sed 's/^/    /'
