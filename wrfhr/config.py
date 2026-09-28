"""Site configuration.

Every machine-specific path lives in site.env at the repo root (copy
site.env.example).  Nothing else in the repo should hardcode one, so porting to
a new HPC system is editing one file.

    from wrfhr import cfg, path
    root = cfg["CASE_ROOT"]
    nml  = path("CASE_ROOT", "namelist.input")

Environment variables win over site.env, so a single run can be redirected
without editing anything:  CASE_ROOT=/tmp/test python pipeline/stage_blocks.py
"""
import os
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

REQUIRED = ("CASE_ROOT", "WRF_RUN_DIR", "WPS_DIR", "WPS_GEOG", "MET_DIR",
            "PYTHON", "SLURM_ACCOUNT")


def _load():
    f = Path(os.environ.get("WRFHR_SITE", REPO / "site.env"))
    out = {}
    if f.exists():
        for line in f.read_text().splitlines():
            line = line.split("#", 1)[0].strip()
            if "=" in line:
                k, v = line.split("=", 1)
                out[k.strip()] = v.strip().strip('"').strip("'")
    else:
        raise SystemExit(
            f"No site config at {f}.\n"
            f"Copy {REPO}/site.env.example to {REPO}/site.env and edit it."
        )
    out.update({k: v for k, v in os.environ.items() if k in out or k in REQUIRED})
    missing = [k for k in REQUIRED if not out.get(k)]
    if missing:
        raise SystemExit(f"site.env is missing required keys: {', '.join(missing)}")
    return out


cfg = _load()


def path(key, *parts):
    """Path under a configured root, e.g. path('CASE_ROOT', 'wrf_runs', run)."""
    return str(Path(cfg[key]).joinpath(*[str(p) for p in parts]))
