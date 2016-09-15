#!/usr/bin/env bash
set -e
set -o pipefail

# args: temp disk mount path

# get my ip address
ipaddress=`ip addr list eth0 | grep "inet " | cut -d' ' -f6 | cut -d/ -f1`

# if master, peer and create volume
if [ $AZ_BATCH_IS_CURRENT_NODE_MASTER == "true" ]; then
    # construct brick locations
    IFS=',' read -ra HOSTS <<< "$AZ_BATCH_HOST_LIST"
    bricks=
    for node in "${HOSTS[@]}"
    do
        bricks+=" $node:$1/gluster/brick"
        # probe peer
        if [ $node != $ipaddress ]; then
            echo "probing $node"
            gluster peer probe $node
        fi
    done
    numnodes=${#HOSTS[@]}
    numpeers=$(($numnodes - 1))
    echo "waiting for $numpeers peers to reach connected state..."
    # get peer info
    set +e
    while :
    do
        numready=`gluster peer status | grep -e '^State: Peer in Cluster' | wc -l`
        if [ $numready == $numpeers ]; then
            break
        fi
        sleep 1
    done
    set -e
    echo "$numpeers joined peering"
    sleep 5
    # create volume
    echo "creating gv0 ($bricks)"
    gluster volume create gv0 replica $numnodes transport tcp$bricks
    # start volume
    echo "starting gv0"
    gluster volume start gv0
fi

# poll for volume created
echo "waiting for gv0 volume..."
set +e
while :
do
        gluster volume info gv0
        if [ $? -eq 0 ]; then
            break
        fi
    sleep 1
done
set -e

# add gv0 to /etc/fstab for auto-mount on reboot
mountpoint=$1/gluster/gv0
mkdir -p $mountpoint
echo "adding $mountpoint to fstab"
echo "$ipaddress:/gv0 $mountpoint glusterfs defaults,_netdev 0 0" >> /etc/fstab

# mount it
echo "mounting $mountpoint"
mount $mountpoint

# touch file noting success
touch .glusterfs_success
