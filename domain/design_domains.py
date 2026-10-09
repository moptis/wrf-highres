"""
Design a 5-domain WRF nest (8100/2700/900/300/100 m) for the wsw_high run.

The innermost domain (d05, 100 m) is sized to cover the requested WRG
rectangle plus a spin-up margin:

    nx=326  ny=341  x0=446805  y0=3785491  res=100   (UTM 13N / EPSG:32613)

Writes namelist.wps and namelist.input into CASE_ROOT (see site.env).
Placeholders ($START_DATE/$END_DATE, yst/mst/... ) are left in place so the
existing 03_prepare_runs.py can fill them per run chunk.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from wrfhr import cfg, path

import numpy as np
from pyproj import CRS, Transformer

SCENARIO = os.path.basename(cfg["CASE_ROOT"])
ROOT = cfg["CASE_ROOT"]
WPS_ROOT = f"{ROOT}/wps"

# ---------------------------------------------------------------- WRG target
WRG_EPSG = 32613          # UTM 13N, confirmed against the existing 1 km WRG
WRG_NX, WRG_NY = 326, 341
WRG_X0, WRG_Y0 = 446805.0, 3785491.0
WRG_RES = 100.0

# ------------------------------------------------------------- nest settings
RATIO = 3
DX = [8100.0, 2700.0, 900.0, 300.0, 100.0]

# Extra margin (m, each side) around the WRG box on d05, for nest spin-up.
D05_MARGIN = 3000.0

# Minimum number of PARENT cells between a nest edge and its parent's edge.
# Index i is for domain i+2 sitting inside domain i+1.
MIN_BUFFER = [12, 15, 20, 25]     # d02-in-d01, d03-in-d02, d04-in-d03, d05-in-d04

# WRF refuses a decomposition with fewer than 10 cells per patch in either
# direction, so the SMALLEST domain sets the MPI rank ceiling for the whole
# run.  Floor every domain at 80 cells to allow an 8 x 8 = 64 rank job.  The
# outer domains are cheap (d01 is ~0.04x the cost of d05 per step), so buying
# parallelism here costs almost nothing.
MIN_CELLS = 80

# ------------------------------------------------------------------ vertical
ETA = [
    1.00000, 0.99734, 0.99469, 0.99203, 0.98938, 0.98674, 0.98410, 0.98146,
    0.97883, 0.97621, 0.97359, 0.97065, 0.96736, 0.96367, 0.95953, 0.95489,
    0.94969, 0.94385, 0.93731, 0.92998, 0.92176, 0.91255, 0.90222, 0.89064,
    0.87765, 0.86309, 0.84677, 0.82847, 0.80796, 0.78496, 0.75918, 0.73027,
    0.69786, 0.66153, 0.62079, 0.57512, 0.52392, 0.46652, 0.40217, 0.33002,
    0.24913, 0.15845, 0.05678, 0.02500, 0.00000,
]


def ceil_to_multiple(n, m):
    return int(np.ceil(n / m) * m)


def wrg_corners_lonlat():
    t = Transformer.from_crs(f"EPSG:{WRG_EPSG}", "EPSG:4326", always_xy=True)
    x1 = WRG_X0 + (WRG_NX - 1) * WRG_RES
    y1 = WRG_Y0 + (WRG_NY - 1) * WRG_RES
    pts = [(WRG_X0, WRG_Y0), (x1, WRG_Y0), (x1, y1), (WRG_X0, y1)]
    ctr = ((WRG_X0 + x1) / 2, (WRG_Y0 + y1) / 2)
    return [t.transform(*p) for p in pts], t.transform(*ctr)


def lcc_crs(ref_lat, ref_lon, truelat1, truelat2):
    """WRF's Lambert conformal grid, sphere of radius 6370 km."""
    return CRS.from_proj4(
        f"+proj=lcc +lat_1={truelat1} +lat_2={truelat2} +lat_0={ref_lat} "
        f"+lon_0={ref_lon} +x_0=0 +y_0=0 +a=6370000 +b=6370000 +units=m +no_defs"
    )


def build_nest():
    corners, (ctr_lon, ctr_lat) = wrg_corners_lonlat()

    ref_lat, ref_lon = round(ctr_lat, 4), round(ctr_lon, 4)
    truelat1, truelat2 = round(ref_lat + 1, 4), round(ref_lat - 1, 4)
    stand_lon = ref_lon

    # WRG box in WRF projection coordinates (origin = d01 centre)
    to_lcc = Transformer.from_crs(
        "EPSG:4326", lcc_crs(ref_lat, ref_lon, truelat1, truelat2), always_xy=True
    )
    xy = np.array([to_lcc.transform(lon, lat) for lon, lat in corners])

    # d05 is snapped to the d04 grid, so allow half a d04 cell of slack on top
    # of the requested margin.
    pad = D05_MARGIN + DX[3] / 2.0
    need = {
        "xmin": xy[:, 0].min() - pad, "xmax": xy[:, 0].max() + pad,
        "ymin": xy[:, 1].min() - pad, "ymax": xy[:, 1].max() + pad,
    }

    # --- d05: smallest grid covering the padded box, cells divisible by RATIO
    n5x = ceil_to_multiple((need["xmax"] - need["xmin"]) / DX[4], RATIO)
    n5y = ceil_to_multiple((need["ymax"] - need["ymin"]) / DX[4], RATIO)

    # --- work outward.  n[k] = number of grid CELLS (e_we - 1) on domain k+1.
    n = [None] * 5
    n[4] = (n5x, n5y)
    for k in (3, 2, 1, 0):
        cx, cy = n[k + 1]
        fx, fy = cx // RATIO, cy // RATIO           # child footprint in parent cells
        bx = by = MIN_BUFFER[k]
        px, py = max(fx + 2 * bx, MIN_CELLS), max(fy + 2 * by, MIN_CELLS)
        if k > 0:                                    # parent must host a ratio-3 child
            while px % RATIO:
                px += 1
            while py % RATIO:
                py += 1
        n[k] = (px, py)

    # --- placement.  d01 is centred on the projection origin; every nest is
    # then centred on the WRG box itself (not on its parent) so the snapping
    # error stays below half a parent cell instead of accumulating.
    cx = (xy[:, 0].min() + xy[:, 0].max()) / 2.0
    cy = (xy[:, 1].min() + xy[:, 1].max()) / 2.0

    e_we = [c[0] + 1 for c in n]
    e_sn = [c[1] + 1 for c in n]

    istart, jstart = [1], [1]
    x0 = [-n[0][0] * DX[0] / 2.0]
    y0 = [-n[0][1] * DX[0] / 2.0]
    for k in range(1, 5):
        i = int(round((cx - n[k][0] * DX[k] / 2.0 - x0[k - 1]) / DX[k - 1])) + 1
        j = int(round((cy - n[k][1] * DX[k] / 2.0 - y0[k - 1]) / DX[k - 1])) + 1
        # keep at least MIN_BUFFER parent cells of parent on every side
        b = MIN_BUFFER[k - 1]
        i = min(max(i, 1 + b), n[k - 1][0] - n[k][0] // RATIO + 1 - b)
        j = min(max(j, 1 + b), n[k - 1][1] - n[k][1] // RATIO + 1 - b)
        istart.append(i)
        jstart.append(j)
        x0.append(x0[k - 1] + (i - 1) * DX[k - 1])
        y0.append(y0[k - 1] + (j - 1) * DX[k - 1])
    x1 = [x0[k] + n[k][0] * DX[k] for k in range(5)]
    y1 = [y0[k] + n[k][1] * DX[k] for k in range(5)]

    return dict(
        ref_lat=ref_lat, ref_lon=ref_lon, truelat1=truelat1, truelat2=truelat2,
        stand_lon=stand_lon, n=n, e_we=e_we, e_sn=e_sn, istart=istart,
        jstart=jstart, x0=x0, x1=x1, y0=y0, y1=y1, need=need, wrg_xy=xy,
    )


def report(d):
    print(f"projection centre : {d['ref_lat']}N {d['ref_lon']}E  "
          f"(truelat {d['truelat2']}/{d['truelat1']})")
    print()
    hdr = f"{'dom':>4} {'dx(m)':>7} {'e_we':>6} {'e_sn':>6} {'i_par':>6} {'j_par':>6} " \
          f"{'width(km)':>10} {'height(km)':>11} {'points':>10}"
    print(hdr); print("-" * len(hdr))
    for k in range(5):
        print(f"d0{k+1:d} {DX[k]:7.0f} {d['e_we'][k]:6d} {d['e_sn'][k]:6d} "
              f"{d['istart'][k]:6d} {d['jstart'][k]:6d} "
              f"{d['n'][k][0]*DX[k]/1000:10.1f} {d['n'][k][1]*DX[k]/1000:11.1f} "
              f"{d['e_we'][k]*d['e_sn'][k]:10d}")
    print()

    # nest containment
    for k in range(1, 5):
        gap = min(d['x0'][k] - d['x0'][k-1], d['x1'][k-1] - d['x1'][k],
                  d['y0'][k] - d['y0'][k-1], d['y1'][k-1] - d['y1'][k])
        ok = "OK " if gap >= MIN_BUFFER[k-1] * DX[k-1] * 0.999 else "FAIL"
        print(f"  {ok} d0{k+1} inset in d0{k}: min gap {gap/1000:6.1f} km "
              f"= {gap/DX[k-1]:.0f} parent cells")

    ranks = min(c[0] // 10 for c in d['n']) * min(c[1] // 10 for c in d['n'])
    print(f"\n  max MPI decomposition: {min(c[0]//10 for c in d['n'])} x "
          f"{min(c[1]//10 for c in d['n'])} = {ranks} ranks "
          f"(WRF needs >= 10 cells per patch)\n")

    # WRG coverage by d05
    xy, need = d['wrg_xy'], d['need']
    pad = min(xy[:, 0].min() - d['x0'][4], d['x1'][4] - xy[:, 0].max(),
              xy[:, 1].min() - d['y0'][4], d['y1'][4] - xy[:, 1].max())
    ok = "OK " if pad >= D05_MARGIN * 0.999 else "FAIL"
    print(f"  {ok} WRG box inside d05: min margin {pad/1000:.2f} km "
          f"({pad/DX[4]:.0f} cells at 100 m)")
    print(f"      WRG box {(xy[:,0].max()-xy[:,0].min())/1000:.1f} x "
          f"{(xy[:,1].max()-xy[:,1].min())/1000:.1f} km in WRF projection")



# --------------------------------------------------------------- namelists
# d01 base step: 40 s at 8.1 km (~5 s per km, and 600 s / 40 s is exact so the
# 10-minute history on d05 lands on a step).  Nests inherit 40/3^k, i.e. 0.49 s
# on d05.
TIME_STEP = 40

# Per-domain history interval (minutes).  The deliverable is WRG statistics,
# not timeseries, so d05 is sampled hourly: ~8760 samples/point/year is ample
# for sector-wise speed distributions, and it cuts d05 output volume 6x versus
# 10-minute frames.  The outer domains are kept only for sanity checks.
HIST = [720, 720, 720, 720, 60]


def _f(vals, fmt="{}"):
    return ", ".join(fmt.format(v) for v in vals)


def write_namelist_wps(d, path):
    txt = f"""&share
 wrf_core = 'ARW',
 max_dom = 5,
 start_date = {_f(["'$START_DATE'"] * 5)},
 end_date   = {_f(["'$END_DATE'"] * 5)},
 interval_seconds = 10800,
 io_form_geogrid = 2,
/

&geogrid
 parent_id         = {_f([1, 1, 2, 3, 4], "{:6d}")},
 parent_grid_ratio = {_f([1, 3, 3, 3, 3], "{:6d}")},
 i_parent_start    = {_f(d['istart'], "{:6d}")},
 j_parent_start    = {_f(d['jstart'], "{:6d}")},
 e_we              = {_f(d['e_we'], "{:6d}")},
 e_sn              = {_f(d['e_sn'], "{:6d}")},
 !
 ! 30 m terrain (Copernicus GLO-30, 'cop30') AND 30 m land cover (NLCD 2025)
 ! on every domain.  'default' stays last as the fallback for every other
 ! field and for anywhere the 30 m data does not reach.
 !
 ! All five domains must use the same land-cover dataset: mixing NLCD with
 ! MODIS 'default' would mix 40- and 21-category land use, and num_land_cat
 ! takes only one value.
 !
 ! NOTE: if GEOGRID.TBL lacks the cop30/nlcd2025 entries, geogrid does NOT
 ! error -- it silently falls back to 900 m GMTED terrain and MODIS land use.
 ! See tools/GEOGRID.TBL.cop30-fragment.
 !
 geog_data_res = {_f(["'cop30+nlcd2025+default'"] * 5)},
 dx = {DX[0]},
 dy = {DX[0]},
 map_proj = 'lambert',
 ref_lat   = {d['ref_lat']},
 ref_lon   = {d['ref_lon']},
 truelat1  = {d['truelat1']},
 truelat2  = {d['truelat2']},
 stand_lon = {d['stand_lon']},
 geog_data_path = '{cfg["WPS_GEOG"]}'
 opt_geogrid_tbl_path = '{WPS_ROOT}/geogrid'
/

&ungrib
 out_format = 'WPS',
 prefix = 'ERA5_SURF',
/

&metgrid
 fg_name = 'ERA5_PRES', 'ERA5_SURF',
 io_form_metgrid = 2,
 opt_metgrid_tbl_path = '{WPS_ROOT}/metgrid'
/
"""
    open(path, "w").write(txt)
    print(f"wrote {path}")


def write_namelist_input(d, path):
    five = lambda v: _f([v] * 5)
    eta = "\n".join(
        "                                       " + " ".join(f"{e:.5f}," for e in ETA[i:i + 4])
        for i in range(0, len(ETA), 4)
    ).lstrip()

    txt = f"""&time_control
 start_year                          = {five('yst')}
 start_month                         = {five('mst')}
 start_day                           = {five('dst')}
 start_hour                          = {five('hst')}
 start_minute                        = {five('00')}
 start_second                        = {five('00')}
 end_year                            = {five('yend')}
 end_month                           = {five('mend')}
 end_day                             = {five('dend')}
 end_hour                            = {five('hend')}
 end_minute                          = {five('miend')}
 end_second                          = {five('00')}
 interval_seconds                    = 10800
 input_from_file                     = {five('.true.')}
 history_interval                    = {_f(HIST)},
 frames_per_outfile                  = {five(1)}
 restart                             = .false.,
 restart_interval                    = 180,
 io_form_history                     = 2,
 io_form_restart                     = 102,
 io_form_input                       = 2,
 auxinput4_inname                    = "wrflowinp_d<domain>",
 auxinput4_interval                  = {five(180)}
 io_form_auxinput4                   = 2,
 iofields_filename                   = {five('"myoutfields.txt"')}
 ignore_iofields_warning             = .true.,
 force_use_old_data                  = .true.,
/

&domains
 time_step                           = {TIME_STEP},
 use_adaptive_time_step              = .true.,
 adaptation_domain                   = 1,
 step_to_output_time                 = .true.,
 max_step_increase_pct               = 5, 51, 51, 51, 51,
 min_time_step                       = {five(1)}
 target_cfl                          = {five(0.7)}
 max_dom                             = 5,
 e_we                                = {_f(d['e_we'])},
 e_sn                                = {_f(d['e_sn'])},
 e_vert                              = {five(len(ETA))}
 p_top_requested                     = 10000,
 num_metgrid_levels                  = 38,
 num_metgrid_soil_levels             = 4,
 dx                                  = {_f(DX, "{:.1f}")},
 dy                                  = {_f(DX, "{:.1f}")},
 grid_id                             = 1, 2, 3, 4, 5,
 parent_id                           = 0, 1, 2, 3, 4,
 i_parent_start                      = {_f(d['istart'])},
 j_parent_start                      = {_f(d['jstart'])},
 parent_grid_ratio                   = 1, 3, 3, 3, 3,
 parent_time_step_ratio              = 1, 3, 3, 3, 3,
 feedback                            = 0,
 smooth_option                       = 0,
 eta_levels                          = {eta}
/

&physics
 mp_physics                          = {five(8)}
 ra_lw_physics                       = {five(4)}
 ra_sw_physics                       = {five(4)}
 radt                                = {five(8)}
 sf_sfclay_physics                   = {five(5)}
 sf_surface_physics                  = {five(2)}
 bl_pbl_physics                      = {five(5)}
 bldt                                = {five(0)}
 tke_budget                          = {five(0)}
 bl_mynn_mixlength                   = 0,
 bl_mynn_tkeadvect                   = {five('.true.')}
 windfarm_opt                        = {five(0)}
 windfarm_tke_factor                 = 1.0,
 windfarm_ij                         = 0,
 cu_physics                          = 1, 0, 0, 0, 0,
 cudt                                = {five(0)}
 isfflx                              = 1,
 ifsnow                              = 1,
 icloud                              = 1,
 surface_input_source                = 3,
 num_soil_layers                     = 4,
 num_land_cat                        = 40,
 sf_urban_physics                    = {five(0)}
 cu_rad_feedback                     = .true.,
 sst_update                          = 1,
/

&dynamics
 w_damping                           = 1,
 diff_opt                            = {five(2)}
 km_opt                              = {five(4)}
 diff_6th_opt                        = {five(0)}
 diff_6th_factor                     = {five(0.12)}
 base_temp                           = 290.
 damp_opt                            = 3,
 zdamp                               = {five('6000.')}
 dampcoef                            = {five(0.2)}
 khdif                               = {five(0)}
 kvdif                               = {five(0)}
 c_s                                 = {five(0.25)}
 c_k                                 = {five(0.10)}
 mix_isotropic                       = {five(0)}
 non_hydrostatic                     = {five('.true.')}
 moist_adv_opt                       = {five(1)}
 scalar_adv_opt                      = {five(1)}
 epssm                               = 0.1, 0.1, 0.3, 0.5, 0.5,
/

&bdy_control
 spec_bdy_width                      = 5,
 spec_zone                           = 1,
 relax_zone                          = 4,
 specified                           = .true., .false., .false., .false., .false.,
 nested                              = .false., .true., .true., .true., .true.,
/

&grib2
/

&namelist_quilt
 nio_tasks_per_group = 0,
 nio_groups = 1,
/
"""
    open(path, "w").write(txt)
    print(f"wrote {path}")


if __name__ == "__main__":
    d = build_nest()
    report(d)
    print()
    write_namelist_wps(d, f"{ROOT}/namelist.wps")
    write_namelist_input(d, f"{ROOT}/namelist.input")
