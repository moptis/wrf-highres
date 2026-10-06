# tools/ — building the Copernicus terrain dataset

```
fetch_cop30.sh      stage Copernicus GLO-30 for CONUS + Canada (3531 tiles, 75 GB)
fetch_3dep.sh       stage USGS 3DEP 1-arcsec, CONUS (bare-earth reference, 48 GB)
verify_dem.py       open and pixel-decode every tile -- a truncated GeoTIFF
                    passes a header check and fails later as a silent hole
make_wps_topo.py    GeoTIFF mosaic -> WPS binary geogrid tiles
```

Both fetch scripts run on the **login node** on purpose: this is I/O, not
compute, so it costs no allocation — which matters on a small one.

## Why Copernicus and not 3DEP

3DEP is bare earth and Copernicus is a surface model, so Copernicus sits high
over forest. Measured on matching tiles: **+0.29 m** over NM high desert,
**+11.55 m** over dense Oregon conifer — but gradients only 1.06-1.07x and
*identical* fine-scale spectral content. The bias is a smooth offset, not
spurious structure, so it does not inject fake terrain forcing, and wind is
diagnosed relative to the model surface anyway.

Mixing them would be worse: a 3DEP/Copernicus seam at 49N puts a ~12 m terrain
step through forested border states, plus a NAVD88/EGM2008 datum offset. One
dataset, no seam, and it extends beyond North America later.

Alaska is **not** included (west of -142): 569 tiles, ~12 GB, same pipeline.
