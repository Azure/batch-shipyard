#!/usr/bin/env bash

set -e
set -o pipefail

# get number of GPUs on machine
ngpus=`nvidia-smi -L | wc -l`
echo "num gpus: $ngpus"

if [ $ngpus -eq 0 ]; then
    echo "No GPUs detected."
    exit 1
fi

# get my ip address
ipaddress=`ip addr list eth0 | grep "inet " | cut -d' ' -f6 | cut -d/ -f1`

# create ps master var
IFS=':' read -ra master <<< "$AZ_BATCH_MASTER_NODE"
master=${master[0]}
ps_hosts="$master:2222"

# create worker hosts list and assign task index
IFS=',' read -ra HOSTS <<< "$AZ_BATCH_HOST_LIST"
worker_hosts=
index=1
declare -A task_index
for node in "${HOSTS[@]}"
do
    # allow parameter server to be part of cluster
    worker_hosts+="$node:2223,"
    if [ $node == $master ]; then
        task_index[$node]=0
    else
        task_index[$node]=$index
        index=$((index+1))
    fi
done
worker_hosts=${worker_hosts::-1}

echo "num nodes: ${#HOSTS[@]}"
echo "master node: $master"
echo "ps hosts: $ps_hosts"
echo "worker hosts: $worker_hosts"

# master node acts as parameter server
masterpid=
if [ $AZ_BATCH_IS_CURRENT_NODE_MASTER == "true" ]; then
    # master node
    ti=${task_index[$master]}
    echo "master node: $ipaddress task index: $ti"
    python /sw/mnist_replica.py --ps_hosts=$ps_hosts --worker_hosts=$worker_hosts --job_name=ps --task_index=$ti --data_dir=./master --num_gpus=$ngpus $* > ps-$ti.log 2>&1 &
    masterpid=$!
fi

declare -a waitpids

# launch worker nodes
for node in "${HOSTS[@]}"
do
    ti=${task_index[$node]}
    echo "worker node: $node task index: $ti"
    if [ $node == $master ]; then
        python /sw/mnist_replica.py --ps_hosts=$ps_hosts --worker_hosts=$worker_hosts --job_name=worker --task_index=$ti --data_dir=./worker-$ti --num_gpus=$ngpus $* > worker-$ti.log 2>&1 &
        waitpids=("${waitpids[@]}" "$!")
    else
        # note that we need to export LD_LIBRARY_PATH since the environment
        # will not be inherited with ssh sessions to worker nodes
        ssh $node "/bin/bash -c \"export LD_LIBRARY_PATH=$LD_LIBRARY_PATH; python /sw/mnist_replica.py --ps_hosts=$ps_hosts --worker_hosts=$worker_hosts --job_name=worker --task_index=$ti --data_dir=$AZ_BATCH_TASK_WORKING_DIR/worker-$ti --num_gpus=$ngpus $* > $AZ_BATCH_TASK_WORKING_DIR/worker-$ti.log 2>&1\"" &
        waitpids=("${waitpids[@]}" "$!")
    fi
done

# because the grpc server does not automatically exit, we need to
# wait for all of the child processes in waitpids to complete first
declare -a donepids
while :
do
    for pid in "${waitpids[@]}"; do
        kill -0 $pid
        if [ $? -ne 0 ]; then
            donepids=("${donepids[@]}" "$pid")
        fi
    done
    if [ ${#waitpids[@]} -eq ${#donepids[@]} ]; then
        break
    else
        sleep 1
    fi
done

# kill master process
kill -9 $masterpid
