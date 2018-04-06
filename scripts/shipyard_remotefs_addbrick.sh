#!/usr/bin/env bash

set -e
set -o pipefail

export DEBIAN_FRONTEND=noninteractive

# constants
gluster_brick_mountpath=/gluster/brick
gluster_brick_location=$gluster_brick_mountpath/brick0
ipaddress=$(ip addr list eth0 | grep "inet " | cut -d' ' -f6 | cut -d/ -f1)

# vars
vm_count=
hostnames=
peer_ips=
gluster_volname=
volume_type=

gluster_peer_probe() {
    # detach peer if it was connected already
    set +e
    gluster peer detach "$1" 2>&1
    set -e
    echo "Attempting to peer with $1"
    peered=0
    local START
    START=$(date -u +"%s")
    set +e
    while :
    do
        # attempt to ping before peering
        if ping -c 2 "$1" > /dev/null; then
            if gluster peer probe "$1" 2>&1; then
                peered=1
            fi
        fi
        if [ $peered -eq 1 ]; then
            break
        else
            local NOW
            NOW=$(date -u +"%s")
            local DIFF=$(((NOW-START)/60))
            # fail after 15 minutes of attempts
            if [ $DIFF -ge 15 ]; then
                echo "Could not probe peer $1"
                exit 1
            fi
            sleep 1
        fi
    done
    set -e
    echo "Peering successful with $1"
}

gluster_poll_for_connections() {
    local numpeers=$((vm_count - 1))
    echo "Waiting for $numpeers peers to reach connected state..."
    # get peer info
    set +e
    while :
    do
        local numready
        numready=$(gluster peer status | grep -c '^State: Peer in Cluster')
        if [ "$numready" == "$numpeers" ]; then
            break
        fi
        sleep 1
    done
    set -e
    echo "$numpeers host(s) joined peering"
    # delay to wait for after peer connections
    sleep 5
}

gluster_add_bricks() {
    # create peers array
    IFS=',' read -ra peers <<< "$peer_ips"
    # create vm hostnames array
    IFS=',' read -ra hosts <<< "$hostnames"
    # cross-validate length
    if [ ${#peers[@]} -ne ${#hosts[@]} ]; then
        echo "${peers[*]} length does not match ${hosts[*]} length"
        exit 1
    fi
    # construct brick locations
    local bricks=
    for host in "${hosts[@]}"
    do
        bricks+=" $host:$gluster_brick_location"
        # probe peer
        gluster_peer_probe "$host"
    done
    # wait for connections
    gluster_poll_for_connections
    echo "Waiting 30 seconds for new nodes to complete their gluster setup..."
    sleep 30
    local volarg=
    if [ "$volume_type" == "stripe" ]; then
        echo "Not changing the stripe count"
    elif [ "$volume_type" == "replica" ]; then
        volarg="$volume_type $vm_count"
    elif [ "$volume_type" != "distributed" ]; then
        # allow custom replica and/or stripe counts
        volarg=$volume_type
    fi
    # add brick
    echo "Adding bricks to gluster volume $gluster_volname $volarg ($bricks)"
    if [[ "$volume_type" == stripe* ]]; then
        # this should be gated by remotefs.py
        # shellcheck disable=SC2086
        echo -e "y\\n" | gluster volume add-brick $gluster_volname ${volarg} ${bricks}
    else
        # shellcheck disable=SC2086
        gluster volume add-brick $gluster_volname ${volarg} ${bricks}
    fi
    # get info and status
    gluster volume info $gluster_volname
    gluster volume status $gluster_volname detail
    # rebalance
    echo "Rebalancing gluster volume $gluster_volname"
    set +e
    if gluster volume rebalance $gluster_volname start; then
        sleep 5
        gluster volume rebalance $gluster_volname status
    fi
    set -e
}

# begin processing
while getopts "h?c:d:i:n:v:" opt; do
    case "$opt" in
        h|\?)
            echo "shipyard_remotefs_addbrick.sh parameters"
            echo ""
            echo "-c [total VM count] total number of VMs"
            echo "-d [hostname/dns label prefix] hostnames"
            echo "-i [peer IPs] peer IPs"
            echo "-n [volume name] volume name"
            echo "-v [volume type] volume type"
            echo ""
            exit 1
            ;;
        c)
            vm_count=$OPTARG
            ;;
        d)
            hostnames=${OPTARG,,}
            ;;
        i)
            peer_ips=${OPTARG,,}
            ;;
        n)
            gluster_volname=$OPTARG
            ;;
        v)
            volume_type=${OPTARG,,}
            ;;
    esac
done
shift $((OPTIND-1))
[ "$1" = "--" ] && shift

# TODO validate required parameters

echo "Parameters:"
echo "  VM Count: $vm_count"
echo "  Gluster Volume Name: $gluster_volname"
echo "  Gluster Volume Type: $volume_type"
echo "  Peer Hostnames: $hostnames"
echo "  Peer IPs: $peer_ips"
echo "  IP address of VM: $ipaddress"

gluster_add_bricks
