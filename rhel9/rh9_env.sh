# Environment for the prebuilt WRF 4.8.0 on Kestrel RHEL9.
#
# The `wrf/4.8.0-craype-gnu` module is BROKEN: its .lua loads the Cray
# PrgEnv-gnu/8.6.0 hierarchy, but spack only exposes netcdf-c/hdf5/
# parallel-netcdf under gcc+mpich, gcc+openmpi or oneapi.  The dep loads fail,
# so the module aborts before setting PATH/WRF_DIR and wrf.exe is never found.
# We therefore reproduce the README's toolchain by hand.
#
# Three details that each cost an hour:
#   - gcc 14.2.0's lib64 is required, or libpnetcdf fails on GLIBCXX_3.4.32
#     against the system /lib64/libstdc++.so.6.
#   - there are SEVEN hdf5-1.14.6-* spack prefixes.  Only evwkamyz/gavht6my are
#     BOTH parallel (export H5Pset_all_coll_metadata_ops, needed by libnetcdf)
#     AND carry the Fortran bindings.  A serial one links fine but dies at
#     runtime with "undefined symbol: H5Pset_all_coll_metadata_ops".
#   - netCDF-Fortran comes from the WRF install's own deps/, not spack.
WRF_RH9=/nopt/nlr/apps/kestrel-cpu/software/wrfRHEL9/wrf-4.8.0-craype-gnu
WRF_RH9_BIN=$WRF_RH9/install/WRF-4.8.0/main
_SP=/nopt/nlr/apps/kestrel-cpu/spack/envs/sw26.05/opt/gcc-14.2.0
_GCC=/nopt/nlr/apps/kestrel-cpu/gcc/14.2.0

module purge >/dev/null 2>&1
module load cpe-stack/25.03 PrgEnv-gnu/8.6.0 craype-x86-spr >/dev/null 2>&1

export LD_LIBRARY_PATH=$WRF_RH9/install/deps/netcdf-fortran-4.6.2/lib:\
$_SP/netcdf-c-4.9.3-rr2yugmlatm7qul7l47ovsqnbyt24ko7/lib:\
$_SP/hdf5-1.14.6-evwkamyz6vpuukkv7yirrz4ru34drgzn/lib:\
$_SP/parallel-netcdf-1.14.1-hsapzqmdrnqdj2b746rjpu677nle45l5/lib:\
$_GCC/lib64:$LD_LIBRARY_PATH
export MPICH_OFI_NIC_POLICY=NUMA
export OMP_NUM_THREADS=1
