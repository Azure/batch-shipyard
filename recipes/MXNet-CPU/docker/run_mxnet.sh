#!/usr/bin/env bash

set -e
set -o pipefail

net=${1,,}
shift
loc=$1
shift

# get nodes and compute number of processors
IFS=',' read -ra HOSTS <<< "$AZ_BATCH_HOST_LIST"
nodes=${#HOSTS[@]}
if [ $nodes -eq 1 ]; then
    # execute job directly
    if [ $net == "cifar-10-r" ]; then
        cd $loc
        wget --progress=dot:giga https://mxnetstorage.blob.core.windows.net/blog1/MXNet_AzureVM_install_test.tar.gz -O - | tar xzf -
        cd MXNet_AzureVM_install_test
        Rscript train_resnet_dynamic_reload.R --cpu T $*
    elif [ $net == "cifar-10-py" ]; then
        cd /mxnet/example/image-classification
        python train_cifar10_resnet.py $*
    elif [ $net == "mnist-r" ]; then
        cd /mxnet/example/image-classification
        Rscript train_mnist.R $*
    elif [ $net == "mnist-py" ]; then
        cd /mxnet/example/image-classification
        python train_mnist.py $*
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
        pushd $loc
        wget --progress=dot:giga https://mxnetstorage.blob.core.windows.net/blog1/MXNet_AzureVM_install_test.tar.gz -O - | tar xzf -
        popd
cat > $runscript << EOF
#!/usr/bin/env bash
set -e
cd $loc/MXNet_AzureVM_install_test
Rscript train_resnet_dynamic_reload.R --cpu T --kv-store dist_sync $*
EOF
    elif [ $net == "cifar-10-py" ]; then
cat > $runscript << EOF
#!/usr/bin/env bash
set -e
cd /mxnet/example/image-classification
python train_cifar10_resnet.py --kv-store dist_sync $*
EOF
    elif [ $net == "mnist-r" ]; then
cat > $runscript << EOF
#!/usr/bin/env bash
set -e
cd /mxnet/example/image-classification
Rscript train_mnist.R --kv-store dist_sync $*
EOF
    elif [ $net == "mnist-py" ]; then
cat > $runscript << EOF
#!/usr/bin/env bash
set -e
cd /mxnet/example/image-classification
python train_mnist.py --kv-store dist_sync $*
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

