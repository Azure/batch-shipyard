#!/usr/bin/env bash
set -e
set -o pipefail

# args: volume type, temp disk mount point, total nodes, ip address of "master", ip addresses of new nodes
voltype=$1
shift
mntpath=$1
shift
numnodes=$1
numpeers=$(($numnodes - 1))
shift
masterip=$1
shift
echo "num nodes: $numnodes"
echo "num peers: $numpeers"
echo "temp disk mountpoint: $mntpath"
echo "master ip: $masterip"

# get my ip address
ipaddress=`ip addr list eth0 | grep "inet " | cut -d' ' -f6 | cut -d/ -f1`
echo "ip address: $ipaddress"

# check if my ip address is a new node
domount=0
for i in "$@"
do
    if [ $i == $ipaddress ]; then
		domount=1
		break
    fi
done
echo "mount: $domount"

# master peers and adds the bricks
if [ $masterip == $ipaddress ]; then
    # probe new nodes
    bricks=
    for node in "$@"
    do
        bricks+=" $node:$mntpath/gluster/brick"
        echo "probing $node"
        gluster peer probe $node
    done

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

    # add bricks to volume
    gluster volume add-brick $voltype $numnodes gv0$bricks

    # get volume info
    gluster volume info
fi

# poll for new number of bricks in volume
echo "waiting for gv0 volume..."
set +e
while :
do
        numbricks=`gluster volume info gv0 | grep -e '^Number of Bricks:' | cut -d' ' -f4`
        if [ "$numbricks" == "$numnodes" ]; then
            # delay to wait for subvolumes
            sleep 5
            break
        fi
    sleep 1
done
set -e

# mount volume if a new node
if [ $domount -eq 1 ]; then
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
fi

# touch file noting success
touch .glusterfs_success
