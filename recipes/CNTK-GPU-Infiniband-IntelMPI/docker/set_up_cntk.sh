#!/usr/bin/env bash

set -e
set -o pipefail

# get number of GPUs on machine
ngpus=$(nvidia-smi -L | wc -l)
echo "num gpus: $ngpus"

if [ $ngpus -eq 0 ]; then
    echo "No GPUs detected."
    exit 1
fi

# get number of nodes
IFS=',' read -ra HOSTS <<< "$AZ_BATCH_HOST_LIST"
nodes=${#HOSTS[@]}

# print configuration
echo "num nodes: $nodes"
echo "hosts: ${HOSTS[@]}"

# activate cntk environment
source /cntk/activate-cntk

# source intel mpi vars
source /opt/intel/compilers_and_libraries/linux/mpi/bin64/mpivars.sh

# compute number of processors
np=$(($nodes * $ngpus))
echo "num mpi processes: $np"

# export parameters
export np
export ngpus
