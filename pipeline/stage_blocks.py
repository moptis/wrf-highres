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

import argparse, os, shutil, subprocess
import pandas as pd

ROOT = cfg["CASE_ROOT"]
MET = cfg["MET_DIR"]
WRF = cfg["WRF_RUN_DIR"]


def stage(row, n, spinup, tstep=72, ratios="1, 3, 3, 3, 2"):
    start = row.start - pd.Timedelta(hours=spinup)
    start = start.floor("3h")                      # ERA5 cadence
    end = row.start + pd.Timedelta(days=int(row.days))
    d = f"{ROOT}/wrf_runs/b{n:03d}"
    shutil.rmtree(d, ignore_errors=True)
    os.makedirs(d)

    # link the WRF run dir, then REMOVE the namelist symlinks before writing our
    # own -- copying onto them writes through into the shared build directory
    for f in os.listdir(WRF):
        os.symlink(f"{WRF}/{f}", f"{d}/{f}")
    for f in ("namelist.input", "namelist.wps"):
        if os.path.islink(f"{d}/{f}"):
            os.unlink(f"{d}/{f}")

    for f in os.listdir(f"{ROOT}/wps"):
        if f.startswith("geo_em.d0"):
            shutil.copy(f"{ROOT}/wps/{f}", d)
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
    out = []
    for line in nml.splitlines():
        s = line.strip()
        if s.startswith("time_step "):
            out += [f" time_step                           = {tstep},",
                    " reasonable_time_step_ratio          = 24.0,"]
        elif s.startswith("use_adaptive_time_step"):
            out.append(" use_adaptive_time_step              = .false.,")
        elif s.startswith("parent_time_step_ratio"):
            out.append(f" parent_time_step_ratio              = {ratios},")
        else:
            out.append(line)
    nml = "\n".join(out) + "\n"
    # The pipeline's convention: real.exe ends on the hour, wrf.exe ends 10 min
    # earlier.  Keeping it means 03_real.sbatch / 04_wrf_cpu.sbatch work
    # unmodified -- they do `ln -sf namelist.input.real namelist.input`, which
    # would otherwise replace a lone namelist.input with a dangling symlink.
    # It also yields exactly 24 hourly d05 frames per sampled day rather than 25.
    open(f"{d}/namelist.input.real", "w").write(nml)
    wrf_end = end - pd.Timedelta(minutes=10)
    nml_w = nml.replace(f" end_hour                            = {end.hour:02d},"
                        f" {end.hour:02d}, {end.hour:02d}, {end.hour:02d}, {end.hour:02d}",
                        f" end_hour                            = {wrf_end.hour:02d},"
                        f" {wrf_end.hour:02d}, {wrf_end.hour:02d}, {wrf_end.hour:02d},"
                        f" {wrf_end.hour:02d}")
    nml_w = nml_w.replace(" end_minute                          = 00, 00, 00, 00, 00",
                          " end_minute                          = 50, 50, 50, 50, 50")
    nml_w = nml_w.replace(f" end_day                             = {end.day:02d},"
                          f" {end.day:02d}, {end.day:02d}, {end.day:02d}, {end.day:02d}",
                          f" end_day                             = {wrf_end.day:02d},"
                          f" {wrf_end.day:02d}, {wrf_end.day:02d}, {wrf_end.day:02d},"
                          f" {wrf_end.day:02d}")
    open(f"{d}/namelist.input.wrf", "w").write(nml_w)
    open(f"{d}/namelist.input", "w").write(nml)

    for t in pd.date_range(start, end, freq="3h"):
        s = t.strftime("%Y-%m-%d_%H")
        for k in ("SURF", "PRES"):
            src = f"{MET}/ERA5_{k}:{s}"
            if not os.path.exists(src):
                raise FileNotFoundError(src)
            os.symlink(src, f"{d}/ERA5_{k}:{s}")
    return d, start, end


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--spinup", type=int, default=6)
    ap.add_argument("--blocks", default=f"{ROOT}/tmy/selected_blocks.csv")
    ap.add_argument("--submit", action="store_true")
    a = ap.parse_args()

    sel = pd.read_csv(a.blocks, parse_dates=["start"])
    man = []
    for n, (_, row) in enumerate(sel.iterrows(), start=1):
        d, st, en = stage(row, n, a.spinup)
        man.append(dict(run=f"b{n:03d}", start=st, end=en,
                        sample_start=row.start, days=row.days, weight=row.weight))
        print(f"b{n:03d}  {st:%Y-%m-%d_%H} -> {en:%Y-%m-%d_%H}  w={row.weight:.5f}")
    m = pd.DataFrame(man)
    m.to_csv(f"{ROOT}/tmy/run_manifest.csv", index=False)
    print(f"\nstaged {len(m)} runs, spin-up {a.spinup} h -> tmy/run_manifest.csv")
    print(f"weights sum to {m.weight.sum():.4f}")
