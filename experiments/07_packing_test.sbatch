#!/bin/bash
#SBATCH --job-name=wswhigh-pack2
#SBATCH --output=/scratch/moptis/c2wind/wsw_high/packing2-%j.out
#SBATCH --nodes=1
#SBATCH --ntasks=104
#SBATCH --exclusive
#SBATCH --account=clusterwakes
#SBATCH --partition=standard
#SBATCH --time=01:30:00

# Does packing several 32-rank jobs onto one node multiply throughput, or does
# memory bandwidth contention eat the gain?
#
# v2: no per-step --mem (three 100G requests stopped the third job launching),
# and explicit --cpu-bind=cores, which the first attempt lacked -- it ran ~2x
# slower per job than the plain `srun -n 32` used in the scaling test.

module load PrgEnv-gnu/8.5.0 cray-mpich/8.1.28 cray-libsci/23.12.5 netcdf/4.9.3-cray-mpich-gcc
export MPICH_OFI_NIC_POLICY=NUMA
export OMP_NUM_THREADS=1

ROOT=/scratch/moptis/c2wind/wsw_high
BUDGET=600

for CONC in 1 2 3; do
    echo "================ $CONC concurrent x 32 ranks ================"
    dirs=$(echo a b c | cut -d' ' -f1-$CONC)
    for p in $dirs; do rm -f $ROOT/wrf_runs/pack_$p/rsl.* ; done
    for p in $dirs; do
        ( cd $ROOT/wrf_runs/pack_$p && \
          timeout ${BUDGET}s srun --exact --cpu-bind=cores -n 32 ./wrf.exe \
              > srun.log 2>&1 ) &
    done
    wait
    for p in $dirs; do
        echo -n "  pack_$p: "
        if [ -f $ROOT/wrf_runs/pack_$p/rsl.error.0000 ]; then
            /home/moptis/miniconda3/envs/default/bin/python $ROOT/profile_run.py \
                $ROOT/wrf_runs/pack_$p/rsl.error.0000 2>&1 | tail -1
        else
            echo "DID NOT LAUNCH: $(tail -1 $ROOT/wrf_runs/pack_$p/srun.log 2>/dev/null)"
        fi
    done
done
