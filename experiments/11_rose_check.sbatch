#!/bin/bash
#SBATCH --job-name=wswhigh-rose
#SBATCH --output=/scratch/moptis/c2wind/wsw_high/rose-%j.out
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --mem=48G
#SBATCH --account=clusterwakes
#SBATCH --partition=shared
#SBATCH --time=01:30:00
/home/moptis/miniconda3/envs/default/bin/python /scratch/moptis/c2wind/wsw_high/tmy/rose_check.py
