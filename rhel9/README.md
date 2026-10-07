# Running on Kestrel RHEL9

Kestrel is migrating RHEL8 -> RHEL9 (began Oct 2026, completing ~Nov 2026).
As of 2026-10-07 the rh8 pool was 1664 nodes with **0 idle**, while rh9 had 512
nodes with **478 idle**. Moving the campaign to rh9 took all 40 blocks from
"queued for hours, never started" to "all 40 running within 60 s".

## The OS is chosen by the login node, not a flag

`--constraint=rh9` is rejected:

    Sorry, overriding the rh8 and rh9 features is not allowed.
    Please submit jobs from a appropriate RHEL 8 or 9 node

A site lua `job_submit` plugin stamps `Features=rh8|rh9` from the login node's
OS. **Submit from `kl3.hpc.nlr.gov`** (RHEL9 CPU login; kl5 is the GPU one).
When jobs sit at `Reason=Resources` while `sinfo` shows idle nodes, check
`scontrol show job <id> | grep Features` before anything else.

## `~/.bashrc` must not load rh8 modules unconditionally

Loading `PrgEnv-gnu/8.5.0` etc. on an rh9 login fails and leaves Lmod in a
state where the rh9 hierarchy will not resolve. Guard them:

    if grep -q 'release 8' /etc/redhat-release 2>/dev/null; then
        module load PrgEnv-gnu/8.5.0 ...
    fi

## The `wrf/4.8.0-craype-gnu` module is broken

Its `.lua` loads the Cray `PrgEnv-gnu/8.6.0` hierarchy and then asks for
`netcdf-c/4.9.3-mpi`, `hdf5/1.14.6-mpi`, `parallel-netcdf/1.14.1-mpi` -- but
spack only exposes those under `gcc+mpich`, `gcc+openmpi` or `oneapi`. The dep
loads fail, the module aborts before setting `PATH`/`WRF_DIR`, and `wrf.exe`
is never found. `rh9_env.sh` reproduces the README toolchain by hand.

Three traps, each of which cost an hour:

1. gcc 14.2.0's `lib64` is required or `libpnetcdf` fails on `GLIBCXX_3.4.32`
   against the system `/lib64/libstdc++.so.6`.
2. There are **seven** `hdf5-1.14.6-*` spack prefixes. Only `evwkamyz` and
   `gavht6my` are BOTH parallel (export `H5Pset_all_coll_metadata_ops`, which
   `libnetcdf` needs) AND carry the Fortran bindings. A serial one links fine
   and dies at runtime with `undefined symbol: H5Pset_all_coll_metadata_ops`.
   Pin the exact hash; never glob and take `head -1`.
3. netCDF-Fortran comes from the WRF install's own `deps/`, not spack.

`srun --overlap` is required per the build README.

## Validation (2026-10-07, block b001)

`real.exe` 4.8.0 against met_em built by our WPS 4.6.0 (the module ships WPS
4.6.0 too), compared with our rh8 WRF 4.6.x output:

| | rh9 / 4.8.0 | rh8 / 4.6.x |
|---|---|---|
| variables | 187 | 187 |
| MMINLU | NLCD40 | NLCD40 |
| U | 1.96..42.91 | 1.96..42.91 |
| HGT | 1699..2166 | 1699..2166 |

terrain `max|rh9-rh8| = 0.0000 m`, `LU_INDEX` bitwise identical.

`wrf.exe`: 1126 steps over 5 domains, 0 errors, per-domain adaptive dt matching
rh8 (d05 median 0.76-0.90 against its 1 s cap).

## VERIFIED: 4.8.0 removed MYNN scale-awareness entirely

The static fields validate exactly, but the physics is a different vintage and
the difference is material. Source is shipped under `build/WRFV4.8.0`, so this
was checked directly rather than assumed.

In 4.6.x the mixing-length cases applied the Honnert/Ito grey-zone factor
`Psig_bl`; in 4.8.0 **none of them do**:

| `bl_mynn_mixlength` | 4.6.x applies Psig_bl | 4.8.0 applies Psig_bl |
|---|---|---|
| 0 | no  | no |
| 1 | yes | **no** |
| 2 | yes | **no** |

`SCALE_AWARE` still exists in 4.8.0 and still computes `Psig_bl`
(module_bl_mynnedmf.F:8304-8356), but no case consumes it. The two closing
lines of 4.6.x CASE 2 are simply gone:

    el_les = MIN(els/(1. + (els/12.)), elb_mf)
    el(k)  = el(k)*Psig_bl + (1.-Psig_bl)*el_les

**This was the whole reason option 2 was chosen.** At dx=100 m with a 1 km PBL
`Psig_bl` is 0.65, and 0.30 for a 3 km PBL -- under 4.8.0 option 2 applies the
full mesoscale mixing length with no taper.

Other real CASE 2 changes 4.6.x -> 4.8.0: `alp3` 2.0 -> 2.5 (buoyancy
enhancement of elb, +25%), and the PBLH floor 300 m -> 200 m (matters at this
site, which is 35% stable + 9% very stable). Renames (`zi`->`pblh`, literals
to `_kind_phys` named constants) are cosmetic.

### What this means for the v1 -> v2 comparison

Partly self-cancelling: v1 ran 4.6.x with `mixlength = 0`, which never applied
`Psig_bl` either. So **both v1 and v2 lack scale-awareness**, and the
comparison is not contaminated by that axis. What still differs beyond terrain
is the rest of CASE 2 -- the eddy-turnover `tau_cloud` length in place of the
`q/N` buoyancy length, and the different alp constants.

For a clean isolation of the terrain upgrade, v2 should run `mixlength = 0`
to match v1. To actually test grey-zone mixing, our own 4.6 tree has to be
rebuilt on rh9 -- the prebuilt 4.8.0 cannot do it at any setting.

Also: this build is made for PnetCDF (`io_form_history = 11`) and warns that
`io_form=13` is broken. We stayed on `io_form_history = 2` to keep v2 output
consistent with v1 and the existing post-processing.
