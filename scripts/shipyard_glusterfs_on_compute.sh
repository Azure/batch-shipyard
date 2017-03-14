#!/usr/bin/env bash
set -e
set -o pipefail

# args: voltype, temp disk mount path
voltype=$1
mntpath=$2

# get my ip address
ipaddress=`ip addr list eth0 | grep "inet " | cut -d' ' -f6 | cut -d/ -f1`

# if master, peer and create volume
if [ $AZ_BATCH_IS_CURRENT_NODE_MASTER == "true" ]; then
    # construct brick locations
    IFS=',' read -ra HOSTS <<< "$AZ_BATCH_HOST_LIST"
    bricks=
    for node in "${HOSTS[@]}"
    do
        bricks+=" $node:$mntpath/gluster/brick"
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
    # delay to wait for peers to connect
    sleep 5
    # create volume
    echo "creating gv0 ($bricks)"
    gluster volume create gv0 $voltype $numnodes transport tcp$bricks
    # modify volume properties: the uid/gid mapping is UNDOCUMENTED behavior
    gluster volume set gv0 storage.owner-uid `id -u _azbatch`
    gluster volume set gv0 storage.owner-gid `id -g _azbatch`
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
        # delay to wait for subvolumes
        sleep 5
        break
    fi
    sleep 1
done
set -e

# add gv0 to /etc/fstab for auto-mount on reboot
mountpoint=$AZ_BATCH_NODE_SHARED_DIR/.gluster/gv0
mkdir -p $mountpoint
chmod 775 $mountpoint
echo "adding $mountpoint to fstab"
echo "$ipaddress:/gv0 $mountpoint glusterfs defaults,_netdev 0 0" >> /etc/fstab

# mount it
echo "mounting $mountpoint"
START=$(date -u +"%s")
set +e
while :
do
    mount $mountpoint
    if [ $? -eq 0 ]; then
        break
    else
        NOW=$(date -u +"%s")
        DIFF=$((($NOW-$START)/60))
        # fail after 5 minutes of attempts
        if [ $DIFF -ge 5 ]; then
            echo "could not mount gluster volume: $mountpoint"
            exit 1
        fi
        sleep 1
    fi
done
set -e
chmod 775 $mountpoint

# touch file noting success
touch .glusterfs_success
