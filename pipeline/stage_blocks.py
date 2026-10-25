"""Stage WRF run directories for an arbitrary list of sampled blocks.

03_prepare_runs.py builds fixed 3-day chunks out of whole TMY months, so it
cannot express "these 40 particular days, each with a weight".  This does the
same job for a block list: one run directory per block, spin-up prepended, a
manifest carrying the weights through to post-processing.

  python stage_blocks.py --spinup 6 [--submit]
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from wrfhr import cfg, path

import argparse, os, re, shutil, subprocess
import pandas as pd

ROOT = cfg["CASE_ROOT"]
MET = cfg["MET_DIR"]
WRF = cfg["WRF_RUN_DIR"]


def has_output(d):
    """Any model output or restart files in this block dir?"""
    import glob as _g
    return bool(_g.glob(f"{d}/wrfout_*") or _g.glob(f"{d}/wrfrst_*"))


def stage(row, n, spinup, force=False):
    start = row.start - pd.Timedelta(hours=spinup)
    start = start.floor("3h")                      # ERA5 cadence
    # End at the NEXT MIDNIGHT, not 23:00.  ERA5 is 3-hourly, so an end of
    # 23:00 makes date_range(start, end, freq="3h") stop at 21:00; real.exe
    # then writes a wrfbdy that ends at 21:00 and WRF dies at that hour with
    # "Ran out of valid boundary conditions in file wrfbdy_d01".  Ending on a
    # 3-hourly boundary costs one model hour and keeps the 21:00-23:00 frames,
    # which is where the nocturnal bias we care about actually lives.
    end = row.start + pd.Timedelta(days=int(row.days))
    d = f"{ROOT}/wrf_runs/b{n:03d}"
    # NEVER rmtree a block that holds model output.  Doing so once destroyed 39
    # completed AZW blocks AND the wrfrst files that would have let them resume
    # in ~20 min instead of an 11 h re-run.  Deleting simulation data needs the
    # user's explicit approval, which is what --force represents.
    if os.path.isdir(d) and has_output(d) and not force:
        return None, None, None
    os.makedirs(d, exist_ok=True)

    # Refresh links in place rather than wiping the directory.  Only symlinks
    # and regenerable inputs are replaced; real files are left alone.
    for f in os.listdir(WRF):
        t = f"{d}/{f}"
        if os.path.islink(t) or not os.path.exists(t):
            if os.path.islink(t):
                os.unlink(t)
            os.symlink(f"{WRF}/{f}", t)
    for f in ("namelist.input", "namelist.wps"):
        if os.path.islink(f"{d}/{f}"):
            os.unlink(f"{d}/{f}")

    for f in os.listdir(f"{ROOT}/wps"):
        if f.startswith("geo_em.d0"):
            shutil.copy(f"{ROOT}/wps/{f}", d)   # regenerable input, safe to refresh
    shutil.copy(os.path.realpath(f"{ROOT}/wps/metgrid.exe"), f"{d}/metgrid.exe")
    os.chmod(f"{d}/metgrid.exe", 0o755)
    shutil.copy(f"{ROOT}/myoutfields.txt", d)

    wps = open(f"{ROOT}/namelist.wps").read()
    wps = wps.replace("$START_DATE", start.strftime("%Y-%m-%d_%H:%M:%S"))
    wps = wps.replace("$END_DATE", end.strftime("%Y-%m-%d_%H:%M:%S"))
    open(f"{d}/namelist.wps", "w").write(wps)

    nml = open(f"{ROOT}/namelist.input").read()
    for k, v in (("yst", start.year), ("mst", f"{start.month:02d}"),
                 ("dst", f"{start.day:02d}"), ("hst", f"{start.hour:02d}"),
                 ("yend", end.year), ("mend", f"{end.month:02d}"),
                 ("dend", f"{end.day:02d}"), ("hend", f"{end.hour:02d}"),
                 ("miend", "00")):
        nml = nml.replace(k, str(v))
    open(f"{d}/namelist.input.real", "w").write(nml)
    # WRF stops 10 min before the real.exe end so the final history write lands
    # inside the run.  Substitute the WHOLE date: when the block ends at the
    # next midnight and the sampled day is the last of a month, end rolls into
    # the next month while wrf_end rolls back, so patching only end_day gives
    # an impossible date like 2009-09-31.
    wrf_end = end - pd.Timedelta(minutes=10)
    nml_w = nml
    for key, val in (("end_year", wrf_end.year), ("end_month", f"{wrf_end.month:02d}"),
                     ("end_day", f"{wrf_end.day:02d}"), ("end_hour", f"{wrf_end.hour:02d}"),
                     ("end_minute", f"{wrf_end.minute:02d}")):
        nml_w = re.sub(rf"^ {key}(\s*)=.*$",
                       lambda m, k=key, v=val: f" {k}{m.group(1)}= " + ", ".join([str(v)]*5),
                       nml_w, count=1, flags=re.M)
    open(f"{d}/namelist.input.wrf", "w").write(nml_w)
    open(f"{d}/namelist.input", "w").write(nml)

    for t in pd.date_range(start, end, freq="3h"):
        s = t.strftime("%Y-%m-%d_%H")
        for k in ("SURF", "PRES"):
            src = f"{MET}/ERA5_{k}:{s}"
            if not os.path.exists(src):
                raise FileNotFoundError(src)
            dst = f"{d}/ERA5_{k}:{s}"
            if os.path.islink(dst):
                os.unlink(dst)
            if not os.path.exists(dst):
                os.symlink(src, dst)
    return d, start, end


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--spinup", type=int, default=6)
    ap.add_argument("--blocks", default=f"{ROOT}/tmy/selected_blocks.csv")
    ap.add_argument("--submit", action="store_true")
    ap.add_argument("--force", action="store_true",
                    help="re-stage blocks that already hold wrfout/wrfrst. "
                         "THIS DELETES SIMULATION DATA -- only with the user's approval.")
    a = ap.parse_args()

    sel = pd.read_csv(a.blocks, parse_dates=["start"])
    man = []; skipped = []
    for n, (_, row) in enumerate(sel.iterrows(), start=1):
        d, st, en = stage(row, n, a.spinup, force=a.force)
        if d is None:
            skipped.append(f"b{n:03d}")
            continue
        man.append(dict(run=f"b{n:03d}", start=st, end=en,
                        sample_start=row.start, days=row.days, weight=row.weight))
        print(f"b{n:03d}  {st:%Y-%m-%d_%H} -> {en:%Y-%m-%d_%H}  w={row.weight:.5f}")
    if skipped:
        print(f"\n  SKIPPED {len(skipped)} block(s) that already hold output: "
              f"{' '.join(skipped)}")
        print("  Their manifest rows are preserved from the existing file; pass "
              "--force to re-stage them (this deletes that output).")
    m = pd.DataFrame(man)
    if skipped and os.path.exists(f"{ROOT}/tmy/run_manifest.csv"):
        old = pd.read_csv(f"{ROOT}/tmy/run_manifest.csv")
        m = pd.concat([m, old[old.run.isin(skipped)]]).sort_values("run")
    m.to_csv(f"{ROOT}/tmy/run_manifest.csv", index=False)
    print(f"\nstaged {len(m)} runs, spin-up {a.spinup} h -> tmy/run_manifest.csv")
    print(f"weights sum to {m.weight.sum():.4f}")
