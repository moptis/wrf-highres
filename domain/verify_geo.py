"""Check the geo_em files against the requested WRG box."""
import numpy as np, netCDF4 as nc
from pyproj import Transformer

WRG = dict(nx=326, ny=341, x0=446805.0, y0=3785491.0, res=100.0, epsg=32613)

t = Transformer.from_crs(f"EPSG:{WRG['epsg']}", "EPSG:4326", always_xy=True)
x1 = WRG['x0'] + (WRG['nx'] - 1) * WRG['res']
y1 = WRG['y0'] + (WRG['ny'] - 1) * WRG['res']
corners = [t.transform(*p) for p in
           [(WRG['x0'], WRG['y0']), (x1, WRG['y0']), (x1, y1), (WRG['x0'], y1)]]

print(f"{'dom':>4} {'nx':>5} {'ny':>5} {'dx':>7} {'lat range':>17} {'lon range':>19} "
      f"{'terr m':>14} {'water%':>7}")
for k in range(1, 6):
    f = nc.Dataset(f"wps/geo_em.d0{k}.nc")
    lat, lon = f['XLAT_M'][0], f['XLONG_M'][0]
    hgt, lm = f['HGT_M'][0], f['LANDMASK'][0]
    print(f"d0{k} {lat.shape[1]:5d} {lat.shape[0]:5d} {f.DX:7.0f} "
          f"{lat.min():7.3f}..{lat.max():7.3f} {lon.min():9.3f}..{lon.max():9.3f} "
          f"{hgt.min():6.0f}..{hgt.max():6.0f} {100*(1-lm.mean()):6.1f}")
    if k == 5:
        d5 = (lat, lon, f)          # keep d05 open for the checks below
    else:
        f.close()

lat, lon, f5 = d5
print(f"\nd05 grid: MMINLU={f5.MMINLU} NUM_LAND_CAT={f5.NUM_LAND_CAT} "
      f"ISWATER={f5.ISWATER}")

# every WRG corner must sit inside d05, with margin measured in grid cells
print("\nWRG corner containment in d05 (distance to nearest d05 edge):")
ok = True
for (clon, clat), name in zip(corners, ["SW", "SE", "NE", "NW"]):
    d = np.hypot(lat - clat, lon - clon)
    j, i = np.unravel_index(d.argmin(), d.shape)
    edge = min(i, lat.shape[1] - 1 - i, j, lat.shape[0] - 1 - j)
    inside = (lat.min() < clat < lat.max()) and (lon.min() < clon < lon.max())
    ok &= inside and edge >= 20
    print(f"  {name} ({clat:.4f}, {clon:.4f}) -> d05 cell (i={i}, j={j}), "
          f"{edge} cells from edge  {'OK' if inside and edge >= 20 else 'TOO CLOSE'}")

lu = f5['LU_INDEX'][0]
cats, cnt = np.unique(lu.astype(int), return_counts=True)
order = np.argsort(-cnt)[:6]
print("\nd05 dominant NLCD40 categories: " +
      ", ".join(f"{cats[i]}:{100*cnt[i]/lu.size:.1f}%" for i in order))
print(f"\nOVERALL: {'PASS' if ok else 'FAIL'}")
f5.close()
