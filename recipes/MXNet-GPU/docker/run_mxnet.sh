#!/usr/bin/env bash

set -e
set -o pipefail

# get number of GPUs on machine
ngpus=`nvidia-smi -L | wc -l`
echo "num gpus: $ngpus"

net=${1,,}
shift
loc=$1
shift

if [ $ngpus -eq 0 ]; then
    echo "No GPUs detected."
    exit 1
fi

# create gpu param
gpus=
maxgpu=$(($ngpus - 1))
for i in `seq 0 $maxgpu`
do
    if [ $i -eq 0 ]; then
        gpus+=$i
    else
        gpus+=,$i
    fi
done
echo "gpus: $gpus"

# get nodes and compute number of processors
IFS=',' read -ra HOSTS <<< "$AZ_BATCH_HOST_LIST"
nodes=${#HOSTS[@]}
if [ $nodes -eq 1 ]; then
    # execute job directly
    if [ $net == "cifar-10-r" ]; then
        cd $loc
        wget --progress=dot:giga https://mxnetstorage.blob.core.windows.net/blog1/MXNet_AzureVM_install_test.tar.gz -O - | tar xzf -
        cd MXNet_AzureVM_install_test
        Rscript train_resnet_dynamic_reload.R --gpus $gpus $*
    elif [ $net == "cifar-10-py" ]; then
        cd /mxnet/example/image-classification
        python train_cifar10_resnet.py --gpus $gpus $*
    elif [ $net == "mnist-r" ]; then
        cd /mxnet/example/image-classification
        Rscript train_mnist.R --gpus $gpus $*
    elif [ $net == "mnist-py" ]; then
        cd /mxnet/example/image-classification
        python train_mnist.py --gpus $gpus $*
    else
        echo "unknown training: $net"
        exit 1
    fi
else
    # create hostfile
    touch hostfile
    >| hostfile
    for node in "${HOSTS[@]}"
    do
        echo $node:23 >> hostfile
    done
    echo "num nodes: $nodes"
    echo "hosts: ${HOSTS[@]}"
    runscript=$loc/mxnet-$net.sh
    if [ $net == "cifar-10-r" ]; then
cat > $runscript << EOF
#!/usr/bin/env bash
set -e
cd $loc/MXNet_AzureVM_install_test
Rscript train_resnet_dynamic_reload.R --gpus $gpus --kv-store dist_sync $*
EOF
    elif [ $net == "cifar-10-py" ]; then
cat > $runscript << EOF
#!/usr/bin/env bash
set -e
export PYTHONPATH=$PYTHONPATH
cd /mxnet/example/image-classification
python train_cifar10_resnet.py --gpus $gpus --kv-store dist_sync $*
EOF
    elif [ $net == "mnist-r" ]; then
cat > $runscript << EOF
#!/usr/bin/env bash
set -e
cd /mxnet/example/image-classification
Rscript train_mnist.R --gpus $gpus --kv-store dist_sync $*
EOF
    elif [ $net == "mnist-py" ]; then
cat > $runscript << EOF
#!/usr/bin/env bash
set -e
export PYTHONPATH=$PYTHONPATH
cd /mxnet/example/image-classification
python train_mnist.py --gpus $gpus --kv-store dist_sync $*
EOF
    else
        echo "unknown training: $net"
        exit 1
    fi
    chmod 755 $runscript
    # execute job
    export DMLC_INTERFACE=eth0
    /mxnet/tools/launch.py -n $nodes -H $AZ_BATCH_TASK_WORKING_DIR/hostfile $runscript
fi

