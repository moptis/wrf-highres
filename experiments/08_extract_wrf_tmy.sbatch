#!/bin/bash
#SBATCH --job-name=wswhigh-extract
#SBATCH --output=/scratch/moptis/c2wind/wsw_high/extract-%j.out
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --mem=80G
#SBATCH --account=clusterwakes
#SBATCH --partition=shared
#SBATCH --time=03:00:00
/home/moptis/miniconda3/envs/default/bin/python /scratch/moptis/c2wind/wsw_high/tmy/extract_wrf.py
