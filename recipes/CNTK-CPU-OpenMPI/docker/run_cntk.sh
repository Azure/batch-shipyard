#!/usr/bin/env bash

set -e
set -o pipefail

# get number of nodes
IFS=',' read -ra HOSTS <<< "$AZ_BATCH_HOST_LIST"
nodes=${#HOSTS[@]}

# create hostfile
touch hostfile
>| hostfile
for node in "${HOSTS[@]}"
do
    echo $node slots=1 max-slots=1 >> hostfile
done

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

# execute mpi job
/root/openmpi/bin/mpirun --allow-run-as-root --mca btl_tcp_if_exclude docker0 \
    -np $nodes --hostfile hostfile -x LD_LIBRARY_PATH $workdir \
    /bin/bash -c "source /cntk/activate-cntk; python -u $script $*"
