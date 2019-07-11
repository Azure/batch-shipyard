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

# if # of nodes is <= 1, then this is a multigpu singlenode execution
# don't use internal IP address, use loopback instead so SSH is avoided
if [ $nodes -le 1 ]; then
    HOSTS=("127.0.0.1")
fi

# create hostfile
hostfile="hostfile"
touch $hostfile
>| $hostfile
for node in "${HOSTS[@]}"; do
    echo $node slots=$ngpus max-slots=$ngpus >> $hostfile
done

# compute number of processors
np=$(($nodes * $ngpus))
echo "num mpi processes: $np"

# export parameters
export np
export hostfile
