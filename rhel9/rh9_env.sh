# Environment for running WRF on Kestrel RHEL9.
#
# Source this, then run $WRF_BIN/wrf.exe (or ./wrf.exe in a staged run dir).
# Submit from kl3 -- kl4 is still RHEL8 and does not even have these modules.
#
# HISTORY / why this is now short.  This file used to hand-wire LD_LIBRARY_PATH
# to pinned spack prefixes because the wrf/4.8.0-craype-gnu module was believed
# broken.  It is not: it loads cleanly on kl3 and exports the correct deps.  The
# earlier failures were measured from kl4 (RHEL8), where the module is absent.
# The hand-wired list was also pinned to the gcc-14.2.0 spack prefixes, while
# our build links the gcc-13.2.1 ones -- so it was actively wrong for this
# binary.  Letting the module set the paths removes that whole class of bug.
#
# Do NOT 'module purge' here: on Kestrel it strips MODULEPATH and the rh9
# hierarchy can no longer be resolved.

unset LD_PRELOAD
source /nopt/nlr/apps/kestrel-cpu/init/profile 2>/dev/null || source /etc/profile 2>/dev/null
module load wrf/4.8.0-craype-gnu >/dev/null 2>&1

# The module is loaded ONLY for its dependency environment (netcdf-c, hdf5,
# parallel-netcdf, netcdf-fortran, cray-mpich).  The executables and data
# tables come from our own build, which carries the Fitch density correction
# and the NLCD40 shrub z0 = 0.20 VEGPARM.
WRF_BUILD=${WRF_BUILD:-/home/moptis/WRF}
export WRF_BIN=$WRF_BUILD/main
export WRF_TABLES=$WRF_BUILD/run
export PATH=$WRF_BIN:$PATH

export MPICH_OFI_NIC_POLICY=NUMA
export OMP_NUM_THREADS=1
