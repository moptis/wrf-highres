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

## The rh9 metgrid binary is ALSO broken

The WPS 4.6.0 `metgrid.exe` in this install writes met_em files containing
nothing but an empty `Times` variable -- **15,457 bytes for every domain**,
d01 and d05 alike -- and still prints "Successful completion of metgrid".
real.exe then fails with the misleading

    ---- ERROR: Could not find matching time in input file met_em.d01....

Same block, same namelist.wps, same METGRID.TBL, same geo_em, same ERA5 input:

| binary | d01 | d05 |
|---|---|---|
| rh9 WPS 4.6.0 | 15,457 B | 15,457 B |
| rh8 WPS 4.6.0 | 6,307,675 B | 23,781,781 B |

**Run metgrid on RHEL8.** met_em is netCDF and OS-portable -- rh9's real.exe
reads rh8-made met_em without complaint. Mechanism unconfirmed; the likeliest
suspect is the PnetCDF-linked I/O layer, since this build's own README warns
that `io_form=13` is broken on the WRF side. Testing `io_form_metgrid = 11`
on one block would confirm it.

When checking whether metgrid succeeded, test **file size, not file count** --
the broken run still produces the full 55 files per block.

## Vertical CFL: give the adaptive scheme somewhere to go

A nest's step is `parent_dt / n` with `n = ceil(parent_dt / own_dt)`, and
`own_dt` is floored by `min_time_step`, which is in **whole seconds**.  If the
parent sits on a round cap (d04 pinned at 3.0 s) and d05's floor is 1 s, then
n <= 3 and **d05 cannot go below 1.0 s however high the CFL climbs**.
`target_cfl` has nothing left to give and `w_damping` may not save it.

LGW b029 blew up exactly this way: `W: NaN, w-cfl 4.63, 3164 points exceeded
v_cfl = 2`.  Four of 64 ranks died; the surviving 60 spun in
`futex_wait_queue` for 8 hours while Slurm still reported RUNNING.

    min_time_step_den = 1, 1, 1, 2, 4     ! d04 floor 0.5 s, d05 floor 0.25 s

Note for monitoring: a partial rank death is invisible if you only grep rank
0's log.  Count live ranks, or check that rsl.error.0000 is still being
written to.

## Restarting costs 4.5-6x, so do not restart by reflex

Measured on wsw_high_v2: the same blocks on the same nodes went from 0.77 to
3.45 s/step after a restart, flat from the first step.  Ruled out: hardware,
node, memory tier, NUMA placement, CPU binding, `--overlap`, clock speed,
denormals, weather and directory file count.  A controlled test -- same block,
same model hour, clean directory -- gave 0.51 s/step cold vs 3.23 restarted,
so it is the restart itself.  Mechanism still unknown.

`run_wrf_leg_rh9.sh` therefore chooses: cold redoes `T_total` at 1x while
resuming does `T_remaining` at ~6x, so cold wins whenever
`T_remaining > T_total / 6` -- 5 model-hours for a 30 h block.
