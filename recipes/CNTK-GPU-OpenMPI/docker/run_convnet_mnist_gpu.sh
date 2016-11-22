#!/usr/bin/env bash

set -e
set -o pipefail

# get number of GPUs on machine
ngpus=`nvidia-smi -L | wc -l`
echo "num gpus: $ngpus"

if [ $ngpus -eq 0 ]; then
    echo "No GPUs detected."
    exit 1
elif [ $ngpus -eq 1 ]; then
    # set cntk file
    cntkfile=/cntk/Examples/Image/Classification/ConvNet/BrainScript/ConvNet_MNIST.cntk
    # execute job
    /cntk/build-mkl/gpu/release/bin/cntk configFile=$cntkfile rootDir=. \
        dataDir=/cntk/Examples/Image/DataSets/MNIST outputDir=. $*
else
    shared=$1
    shift
    # set cntk file
    cntkfile=/cntk/Examples/Image/Classification/ConvNet/BrainScript/ConvNet_MNIST_Parallel.cntk
    # get nodes and compute number of processors
    IFS=',' read -ra HOSTS <<< "$AZ_BATCH_HOST_LIST"
    nodes=${#HOSTS[@]}
    np=$(($nodes * $ngpus))
    # if # of nodes is 1, then this is a multigpu singlenode execution
    # don't use internal IP address, use loopback instead so SSH is avoided
    if [ $nodes -eq 1 ]; then
        HOSTS=("127.0.0.1")
    fi
    # create hostfile
    touch hostfile
    >| hostfile
    for node in "${HOSTS[@]}"
    do
        echo $node slots=$ngpus max-slots=$ngpus >> hostfile
    done
    echo "num nodes: $nodes"
    echo "hosts: ${HOSTS[@]}"
    echo "num mpi processes: $np"
    # execute mpi job
    mpirun --allow-run-as-root --mca btl_tcp_if_exclude docker0 -np $np \
        --hostfile hostfile -x LD_LIBRARY_PATH \
        /cntk/build-mkl/gpu/release/bin/cntk configFile=$cntkfile rootDir=. \
        dataDir=/cntk/Examples/Image/DataSets/MNIST outputDir=$shared/Output \
        parallelTrain=true $*
fi
