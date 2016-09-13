#!/usr/bin/env bash

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
if [ ! -z $AZ_BATCH_IS_CURRENT_NODE_MASTER ]; then
    # master node
    ti=${task_index[$master]}
    echo "master node: $ipaddress task index: $ti"
    python /sw/mnist_replica.py --ps_hosts=$ps_hosts --worker_hosts=$worker_hosts --job_name=ps --task_index=$ti --data_dir=./master $* > ps-$ti.log 2>&1 &
fi
# launch worker nodes
for node in "${HOSTS[@]}"
do
    ti=${task_index[$node]}
    echo "worker node: $node task index: $ti"
    if [ $node == $master ]; then
        python /sw/mnist_replica.py --ps_hosts=$ps_hosts --worker_hosts=$worker_hosts --job_name=worker --task_index=$ti --data_dir=./worker-$ti $* > worker-$ti.log 2>&1 &
    else
        ssh $node "export LD_LIBRARY_PATH=/usr/local/nvidia/lib64:/usr/local/cuda/lib64 && python /sw/mnist_replica.py --ps_hosts=$ps_hosts --worker_hosts=$worker_hosts --job_name=worker --task_index=$ti --data_dir=$AZ_BATCH_TASK_WORKING_DIR/worker-$ti $* > $AZ_BATCH_TASK_WORKING_DIR/worker-$ti.log 2>&1 &"
    fi
done
