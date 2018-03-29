#!/usr/bin/env bash

set -o pipefail

export DEBIAN_FRONTEND=noninteractive

# constants
gluster_brick_mountpath=/gluster/brick

# vars
samba=0
filesystem=
mountpath=
gluster_volname=
raid_level=-1
server_type=

# begin processing
while getopts "h?cf:m:n:r:s:" opt; do
    case "$opt" in
        h|\?)
            echo "shipyard_remotefs_stat.sh parameters"
            echo ""
            echo "-c samba enabled"
            echo "-f [filesystem] filesystem"
            echo "-m [mountpoint] mountpoint"
            echo "-n [volume name] volume name"
            echo "-r [RAID level] RAID level"
            echo "-s [server type] server type"
            echo ""
            exit 1
            ;;
        c)
            samba=1
            ;;
        f)
            filesystem=${OPTARG,,}
            ;;
        m)
            mountpath=$OPTARG
            ;;
        n)
            gluster_volname=$OPTARG
            ;;
        r)
            raid_level=$OPTARG
            ;;
        s)
            server_type=${OPTARG,,}
            ;;
    esac
done
shift $((OPTIND-1))
[ "$1" = "--" ] && shift

# get all data disks
mapfile -t all_disks < <(lsblk -l -d -n -p -I 8,65,66,67,68 -o NAME)
for disk in "${all_disks[@]}"; do
    # ignore os and ephemeral disks
	if [ "$disk" != "/dev/sda" ] && [ "$disk" != "/dev/sdb" ]; then
        data_disks=("${data_disks[@]}" "$disk")
    fi
done
unset all_disks
numdisks=${#data_disks[@]}

echo "Detected $numdisks data disks: ${data_disks[*]}"
echo ""

# check server_type software
if [ "$server_type" == "nfs" ]; then
    echo "NFS service status:"
    systemctl status nfs-kernel-server.service
    echo ""
    echo "exportfs:"
    exportfs -v
    echo ""
    echo "nfsstat:"
    nfsstat -s -4
    echo ""
    echo "connected clients:"
    netstat -tn | grep :2049
elif [ "$server_type" == "glusterfs" ]; then
    echo "glusterfs service status:"
    systemctl status glusterfs-server
    echo ""
    gluster volume info all
    echo ""
    gluster volume status all detail
    echo ""
    gluster volume status all clients
    echo ""
    set +e
    gluster volume rebalance "$gluster_volname" status 2>&1
    if gluster volume heal "$gluster_volname" info 2>&1; then
        gluster volume heal "$gluster_volname" info healed 2>&1
        gluster volume heal "$gluster_volname" info heal-failed 2>&1
        gluster volume heal "$gluster_volname" info split-brain 2>&1
    fi
    set -e
    echo ""
    # set mountpath to brick
    mountpath=$gluster_brick_mountpath
else
    echo "$server_type not supported."
    exit 1
fi
echo ""

# check if mount is active
echo "Mount information:"
if ! mount | grep $mountpath; then
    echo "$mountpath not mounted"
    exit 1
fi

# dump mounted filesystems
df -h

# get raid status
if [ "$raid_level" -ge 0 ]; then
    echo ""
    if [ "$filesystem" == "btrfs" ]; then
        echo "btrfs device status:"
        for disk in "${data_disks[@]}"; do
            btrfs device stats "${disk}"1
        done
        echo ""
        echo "btrfs filesystem:"
        btrfs filesystem show
        btrfs filesystem usage -h $mountpath
    else
        echo "/proc/mdstat:"
        cat /proc/mdstat
        echo ""
        # find md target
        mapfile -t target < <(find /dev/md* -maxdepth 0 -type b)
        if [ ${#target[@]} -ne 1 ]; then
            echo "Could not determine md target"
            exit 1
        fi
        echo "mdadm detail:"
        mdadm --detail "${target[0]}"
    fi
fi

# get samba status
if [ $samba -eq 1 ]; then
    echo ""
    echo "smbd service status:"
    systemctl status smbd.service
    echo ""
    echo "smbstatus:"
    smbstatus
fi
