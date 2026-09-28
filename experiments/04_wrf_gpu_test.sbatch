#!/bin/bash
#SBATCH --job-name=wswhigh-gpu
#SBATCH --output=/scratch/moptis/c2wind/wsw_high/wrf_runs/0001_gpu/gputest-%j.out
#SBATCH --gpus=1
#SBATCH --nodes=1
#SBATCH --ntasks=8
#SBATCH --mem=80G
#SBATCH --account=clusterwakes
#SBATCH --partition=debug-gpu
#SBATCH --time=01:00:00

# AceCast (GPU) benchmark for the 5-domain wsw_high nest, to compare against
# the 64-rank CPU run in wrf_runs/0001.

RUNDIR=/scratch/moptis/c2wind/wsw_high/wrf_runs/0001_gpu
CPUDIR=/scratch/moptis/c2wind/wsw_high/wrf_runs/0001

source /scratch/moptis/nvhpc/acecast_env.sh
export ACECAST_USE_UNSUPPORTED_OPTIONS=1

cd $RUNDIR || exit 1
rm -f rsl.* wrfout_* wrfinput_d0* wrfbdy_d01 wrflowinp_d0*

echo "=============== GPU / scaling advisor ==============="
nvidia-smi --query-gpu=name,memory.total --format=csv 2>&1
./acecast-advisor.sh --tool scaling-advisor --namelist-file ./namelist.input 2>&1 \
    | sed 's/\x1b\[[0-9;]*m//g' | grep -iE "Minimum|Maximum|GPU Name|namelist " 

echo "=============== real.exe ==============="
ln -sf namelist.input.real namelist.input
t0=$SECONDS
mpirun -n 1 ./gpu-launch.sh ./real.exe
rc=$?
echo "real.exe exit=$rc  wall=$((SECONDS-t0))s"

if [ ! -f wrfinput_d05 ]; then
    echo "AceCast real.exe did not produce wrfinput_d05 -- falling back to the"
    echo "CPU real.exe output from $CPUDIR so the WRF timing test can proceed."
    cp $CPUDIR/wrfinput_d0* $CPUDIR/wrfbdy_d01 $CPUDIR/wrflowinp_d0* . || exit 1
fi

echo "=============== acecast.exe ==============="
ln -sf namelist.input.wrf namelist.input
t0=$SECONDS
mpirun -n 1 ./gpu-launch.sh ./acecast.exe
echo "acecast.exe exit=$?  wall=$((SECONDS-t0))s"

echo "=============== timing summary ==============="
grep "on domain   1" rsl.error.0000 2>/dev/null | tail -5
echo "model time reached:"; grep "on domain   1" rsl.error.0000 2>/dev/null | tail -1 | grep -oE "time [0-9_:-]+"
