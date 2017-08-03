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

# set cntk related vars
script=
workdir=

# set options
while getopts "h?s:w:" opt; do
    case "$opt" in
        h|\?)
            echo "run_cntk.sh parameters"
            echo ""
            echo "-s [script] python script to execute"
            echo "-w [working dir] working directory"
            echo ""
            exit 1
            ;;
        s)
            script=${OPTARG}
            ;;
        w)
            workdir="--wdir ${OPTARG}"
            ;;
    esac
done
shift $((OPTIND-1))
[ "$1" = "--" ] && shift

if [ -z $script ]; then
    echo "script not specified!"
    exit 1
fi

# activate cntk environment
source /cntk/activate-cntk

# special path for non-mpi job with single gpu
if [ $nodes -le 1 ] && [ $ngpus -eq 1 ]; then
    python -u $script $*
else
    # if # of nodes is <= 1, then this is a multigpu singlenode execution
    # don't use internal IP address, use loopback instead so SSH is avoided
    if [ $nodes -le 1 ]; then
        HOSTS=("127.0.0.1")
    fi
    # create hostfile
    touch hostfile
    >| hostfile
    for node in "${HOSTS[@]}"; do
        echo $node slots=$ngpus max-slots=$ngpus >> hostfile
    done
    # compute number of processors
    np=$(($nodes * $ngpus))
    echo "num mpi processes: $np"
    # execute mpi job
    /root/openmpi/bin/mpirun --allow-run-as-root --mca btl_tcp_if_exclude docker0 \
        -np $np --hostfile hostfile -x LD_LIBRARY_PATH $workdir \
        /bin/bash -i -c "python -u $script $*"
fi
