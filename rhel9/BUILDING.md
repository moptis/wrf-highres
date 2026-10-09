# Building our own WRF on Kestrel RHEL9

Goal: one all-RHEL9 toolchain, Cray-based, carrying our Fitch modifications,
so we stop depending on the prebuilt `wrf/4.8.0-craype-gnu` module (which
cannot load its own dependencies) and on the RHEL8 WPS (whose metgrid we still
need because the RHEL9 one writes empty files).  See README.md for both defects.

Status: **planned, not yet attempted.**  Everything below is reconnaissance.

## 1. WRF 4.8.0 already has the axial induction correction

This is the headline, and it removes most of the porting work.

Stock WRF 4.8.0 `phys/module_wind_fitch.F` contains the BAMS induction scheme
natively -- the same two-iteration formulation as our local patch, with the
same comments:

    INTEGER :: induction_correction
    REAL    :: a_ind                          ! axial induction factor
    a_ind = 0.25                              ! first guess
    a_ind = 0.5 * (1 - sqrt(1 - thrcof))      ! second guess

and it is switchable from the namelist:

    Registry.EM_COMMON:3055
    rconfig integer windfarm_induction namelist,physics 1 1 rh
            "Fitch axial induction correction"

So `wind_fitch_custom.patch` is **upstreamed** -- do not port it.  Set
`windfarm_induction = 1` in `&physics` instead.  Note the upstreamed block
carries a Fraunhofer licence (`doc/licenses/fraunhofer_license.txt`); check it
before redistributing anything built from it.

Not upstreamed: the **air-density** modification.  Stock 4.8.0's Fitch has zero
references to `rho`; it still uses a constant density.  `density_adjustment.patch`
plumbs `RHO=rho` through `module_pbl_driver.F` into Fitch and interpolates to
hub height:

    roo = rho(i,kbot,j) + ((rho(i,ktop,j)-rho(i,kbot,j))/(z2-z1)) * (hubheight(kt)-z1)

## 2. Which patches to apply

| patch | verdict |
|---|---|
| `wind_fitch_custom.patch` | **skip** -- upstreamed in 4.8.0, use `windfarm_induction = 1` |
| `pbl_driver_rho.patch` | **skip** -- superseded; its one hunk is contained in the next |
| `density_adjustment.patch` | **apply** (needs rebasing) |
| `wind_fitch_vollmer.patch` | optional -- adds a `thrust` state variable and Registry entry for diagnostic output; unrelated to induction |

They were written against 4.6.1 and will not apply cleanly:
`module_wind_fitch.F` changed by ~245 of 600 lines between 4.6.1 and 4.8.0,
and `module_pbl_driver.F` by ~110.  Expect a real rebase, not an offset shift.
Treat the density change as a reimplementation against the 4.8.0 Fitch, using
the patch as the specification.

## 3. Toolchain

The NLR recipe (`/home/moptis/temp/compile_wrf.sh`) is RHEL8 and every module
in it is gone on RHEL9:

    PrgEnv-gnu/8.5.0  cray-mpich/8.1.28  cray-libsci/23.12.5
    netcdf/4.9.3-cray-mpich-gcc  jasper/1.900.1-cray-mpich-gcc      <- all MISSING

RHEL9 equivalents, reached through the Lmod hierarchy (nothing is visible until
`cpe-stack` is loaded):

    module load cpe-stack/25.03
    module load PrgEnv-gnu/8.6.0 craype-x86-spr
    # exposes: netcdf/1.12.3.17, hdf5/1.14.3.5, parallel-netcdf/1.12.3.17
    # jasper is top-level: jasper/4.2.8   (was 1.900.1 -- major API change)

**The known risk:** `PrgEnv-gnu/8.6.0` ships **gfortran 13.3.1**, and NREL's own
build notes say that compiler hits an internal compiler error on several WRF 4.8
physics modules (`module_bl_fogdes`, `module_ra_eclipse`, various `noahmp/*`).
That is why they did not use it.

Their workaround keeps Cray for everything that matters and swaps only the
compiler:

    cray-mpich 8.1.32 (Slingshot/CXI) + spack gcc/14.2.0
    PATH=/nopt/nlr/apps/kestrel-cpu/gcc/14.2.0/bin:$PATH
    # so Cray's mpifort/mpicc call gcc 14.2.0, not gcc-toolset-13

Suggested order: try pure Cray PrgEnv first -- it is quick to falsify, it either
ICEs or it does not -- and fall back to Cray MPICH + gcc 14.2.0 if it does.

Other deltas from the pasted recipe:
  * `salloc`/`sbatch` must come from **kl3**, or you get RHEL8 nodes.
  * `./configure` option **35 will not be 35** -- the prebuilt used 34.  Read
    the menu; do not trust the number.
  * Drop `export PATH=/usr/bin:$PATH` and the `/usr/lib64` line initially;
    they are RHEL8 workarounds.  Add back only if something fails.

## 4. Source

Already on disk, no download needed:

    /nopt/nlr/apps/kestrel-cpu/software/wrfRHEL9/wrf-4.8.0-craype-gnu/build/
        WRFV4.8.0/          unpacked source
        v4.8.0.tar.gz       tarball
        build_wrf480_craype_gnu_rhel9.sh    NREL's own build script -- read it
        compile_wrf.log                      and its log

NREL's build script and log are the most useful reference we have; read them
before writing our own.

## 5. WPS

Lower priority.  The RHEL8 WPS works and `geo_em`/`met_em` are netCDF, hence
OS-portable -- RHEL9's real.exe reads RHEL8-made `met_em` without complaint.
Rebuilding WPS on RHEL9 also means confronting jasper 1.900 -> 4.2.8, whose
GRIB2 API changed.  Defer until WRF itself builds, then revisit so the whole
chain is RHEL9.
