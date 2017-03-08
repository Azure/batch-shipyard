#!/usr/bin/env bash

set -o pipefail

DEBIAN_FRONTEND=noninteractive

# vars
mountpath=
raid_level=-1
server_type=

# begin processing
while getopts "h?m:r:s:" opt; do
    case "$opt" in
        h|\?)
            echo "shipyard_remotefs_stat.sh parameters"
            echo ""
            echo "-m [mountpoint] mountpoint"
            echo "-r [RAID level] RAID level"
            echo "-s [server type] server type"
            echo ""
            exit 1
            ;;
        m)
            mountpath=$OPTARG
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
declare -a data_disks
all_disks=($(lsblk -l -d -n -p -I 8 -o NAME))
for disk in "${all_disks[@]}"; do
    # ignore os and ephemeral disks
	if [ $disk != "/dev/sda" ] && [ $disk != "/dev/sdb" ]; then
        data_disks=("${data_disks[@]}" "$disk")
    fi
done
unset all_disks
numdisks=${#data_disks[@]}

echo "Detected $numdisks data disks: ${data_disks[@]}"
echo ""

# check server_type software
if [ $server_type == "nfs" ]; then
    echo "NFS service status:"
    systemctl status nfs-kernel-server.service
    echo ""
    echo "/etc/exports last line:"
    tail -n1 /etc/exports
else
    echo "$server_type not supported."
    exit 1
fi
echo ""

# check if mount is active
mount=$(mount | grep $mountpath)
if [ $? -eq 0 ]; then
    echo "Mount information:"
    echo $mount
else
    echo "$mountpath not mounted"
    exit 1
fi
echo ""

# get filesystem type from mount
formatted_as=$(echo $mount | cut -d" " -f5)

# get raid status
if [ $raid_level -ge 0 ]; then
    if [ $formatted_as == "btrfs" ]; then
        echo "btrfs device status:"
        for disk in "${data_disks[@]}"; do
            btrfs device stats ${disk}1
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
        target=($(find /dev/md* -maxdepth 0 -type b))
        if [ ${#target[@]} -ne 1 ]; then
            echo "Could not determine md target"
            exit 1
        fi
        target=${target[0]}
        echo "mdadm detail:"
        mdadm --detail $target
    fi
fi
