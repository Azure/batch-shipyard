#!/usr/bin/env bash

set -e
set -o pipefail

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
            workdir="-wdir ${OPTARG}"
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

# special path for non-mpi job
if [ $nodes -le 1 ]; then
    python -u $script $*
else
    # source intel mpi vars
    source /opt/intel/compilers_and_libraries/linux/mpi/bin64/mpivars.sh
    echo "num mpi processes: $nodes"
    # execute mpi job
    mpirun -np $nodes -ppn 1 -hosts $AZ_BATCH_HOST_LIST $workdir \
       /bin/bash -i -c "python -u $script $*"
fi
