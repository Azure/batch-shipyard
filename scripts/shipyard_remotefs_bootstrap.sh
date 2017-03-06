#!/usr/bin/env bash

set -e
set -o pipefail

DEBIAN_FRONTEND=noninteractive

# always copy scripts to well known location
mkdir -p /opt/batch-shipyard
cp shipyard_remotefs_*.sh /opt/batch-shipyard

# vars
rebalance_btrfs=0
numdisks_verify=
format_as=
server_type=
mountpath=
optimize_tcp=0
premium_storage=0
raid_type=-1

# begin processing
while getopts "h?bd:f:m:npr:s:" opt; do
    case "$opt" in
        h|\?)
            echo "shipyard_remotefs_bootstrap.sh parameters"
            echo ""
            echo "-b rebalance btrfs data on resize"
            echo "-d [num] num disks"
            echo "-f [format as] format as"
            echo "-m [mountpoint] mountpoint"
            echo "-n Tune TCP parameters"
            echo "-p premium storage disks"
            echo "-r [raid type] raid type"
            echo "-s [server type] server type"
            echo ""
            exit 1
            ;;
        b)
            rebalance_btrfs=1
            ;;
        d)
            numdisks_verify=$OPTARG
            ;;
        f)
            format_as=${OPTARG,,}
            ;;
        m)
            mountpath=$OPTARG
            ;;
        n)
            optimize_tcp=1
            ;;
        p)
            premium_storage=1
            ;;
        r)
            raid_type=$OPTARG
            ;;
        s)
            server_type=${OPTARG,,}
            ;;
    esac
done
shift $((OPTIND-1))
[ "$1" = "--" ] && shift

echo "Parameters:"
echo "  Rebalance btrfs: $rebalance_btrfs"
echo "  Num data disks: $numdisks_verify"
echo "  Format as: $format_as"
echo "  Mountpath: $mountpath"
echo "  Tune TCP parameters: $optimize_tcp"
echo "  Premium storage: $premium_storage"
echo "  RAID type: $raid_type"
echo "  Server type: $server_type"

# optimize network TCP settings
if [ $optimize_tcp -eq 1 ]; then
    sysctlfile=/etc/sysctl.d/60-azure-batch-shipyard-remotefs.conf
    if [ ! -e $sysctlfile ] || [ ! -s $sysctlfile ]; then
cat > $sysctlfile << EOF
net.core.rmem_default=16777216
net.core.wmem_default=16777216
net.core.rmem_max=16777216
net.core.wmem_max=16777216
net.core.netdev_max_backlog=30000
net.ipv4.tcp_max_syn_backlog=80960
net.ipv4.tcp_mem=16777216 16777216 16777216
net.ipv4.tcp_rmem=4096 87380 16777216
net.ipv4.tcp_wmem=4096 65536 16777216
net.ipv4.tcp_slow_start_after_idle=0
net.ipv4.tcp_tw_reuse=1
net.ipv4.tcp_abort_on_overflow=1
net.ipv4.route.flush=1
EOF
    fi
    # reload settings
    service procps reload
fi

# install required server_type software
apt-get update
if [ $server_type == "nfs" ]; then
    apt-get install -y --no-install-recommends nfs-kernel-server
    systemctl enable nfs-kernel-server.service
    systemctl start nfs-kernel-server.service
else
    echo "server_type $server_type not supported."
    exit 1
fi

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

# validate number of data disks found
numdisks=${#data_disks[@]}
echo "found $numdisks data disks: ${data_disks[@]}"
if [ $numdisks -ne $numdisks_verify ]; then
    echo "anticipated data disk count of $numdisks_verify does not match $numdisks disks found!"
    exit 1
fi
unset numdisks_verify

# check if data disks are already partitioned
declare -a skipped_part
for disk in "${data_disks[@]}"; do
    part1=$(partprobe -d -s $disk | cut -d' ' -f4)
    if [ -z $part1 ]; then
        echo "$disk: partition 1 not found. Partitioning $disk..."
        echo -e "n\np\n1\n\n\nw" | fdisk $disk
    else
        echo "$disk: partition 1 found. Skipping partitioning."
        skipped_part=("${skipped_part[@]}" "$disk")
    fi
done

# set format target
target=
target_uuid=
format_target=1
# check if there was only one skipped disk during partitioning
if [ ${#skipped_part[@]} -eq $numdisks ] && [ $numdisks -eq 1 ]; then
    target=${skipped_part[0]}
    read target_uuid target_fs < <(blkid -u filesystem $target | awk -F "[= ]" '{print $3" "$5}'|tr -d "\"")
    if [ ! -z $target_fs ]; then
        format_target=0
    fi
fi

# check if disks are already in raid set
raid_resized=0
if [ $raid_type -ge 0 ]; then
    format_target=0
    if [ $format_as == "btrfs" ]; then
        if [ $raid_type -ne 0 ]; then
            echo "btrfs with non-RAID 0 is not supported."
            exit 1
        fi
    else
        target=/dev/md0
    fi
    declare -a raid_array
    declare -a all_raid_disks
    set +e
    for disk in "${data_disks[@]}"; do
        if [ $format_as == "btrfs" ]; then
            btrfs device scan "${disk}1"
        else
            mdadm --detail "${disk}1"
        fi
        if [ $? -ne 0 ]; then
            raid_array=("${raid_array[@]}" "${disk}1")
        fi
        all_raid_disks=("${all_raid_disks[@]}" "${disk}1")
    done
    set -e
    no_raid_count=${#raid_array[@]}
    if [ $no_raid_count -eq 0 ]; then
        echo "No disks require RAID setup"
    elif [ $no_raid_count -eq $numdisks ]; then
        echo "$numdisks data disks require RAID setup: ${raid_array[@]}"
        if [ $format_as == "btrfs" ]; then
            if [ $raid_type -eq 0 ]; then
                mkfs.btrfs -d raid0 ${raid_array[@]}
            else
                mkfs.btrfs -m raid${raid_type} ${raid_array[@]}
            fi
        else
            mdadm --create --verbose $target --level=$raid_type --raid-devices=$numdisks ${raid_array[@]}
        fi
    else
        echo "Mismatch of non-RAID disks $no_raid_count to total disks $numdisks."
        echo "Will resize underlying RAID array with devices: ${raid_array[@]}"
        if [ $raid_type -ne 0 ]; then
            echo "Cannot resize with RAID type of $raid_type."
            exit 1
        fi
        if [ $format_as == "btrfs" ]; then
            # add new block devices first
            btrfs device add ${raid_array[@]} $mountpath
            # resize btrfs volume
            echo "Resizing filesystem at $mountpath..."
            btrfs filesystem resize max $mountpath
            # rebalance data and metadata across all devices
            if [ $rebalance_btrfs -eq 1]; then
                echo "Rebalancing btrfs on $mountpath..."
                btrfs filesystem balance $mountpath
                echo "Rebalance of btrfs on $mountpath complete."
            fi
            raid_resized=0
        else
            # add new block device first
            mdadm --add --verbose $target ${raid_array[@]}
            # grow the array
            mdadm --grow --verbose $target --raid-devices=$numdisks
            raid_resized=1
        fi
    fi
    if [ $format_as == "btrfs" ]; then
        read target_uuid < <(blkid ${all_raid_disks[0]} | awk -F "[= ]" '{print $3}' | sed 's/\"//g')
        btrfs filesystem show
    else
        read target_uuid < <(blkid ${target} | awk -F "[= ]" '{print $3}' | sed 's/\"//g')
        cat /proc/mdstat
        mdadm --detail $target
    fi
fi

# create filesystem on target device
if [ $format_target -eq 1 ]; then
    if [ -z $target ]; then
        echo "Target not specified for format"
        exit 1
    fi
    echo "Creating filesystem on $target..."
    if [ $format_as == "btrfs" ]; then
        mkfs.btrfs $target
    elif [ $format_as == ext* ]; then
        mkfs.${format_as} -m 0 $target
    else
        echo "Unknown format as: $format_as"
        exit 1
    fi
    read target_uuid < <(blkid ${target} | awk -F "[= ]" '{print $3}' | sed 's/\"//g')
fi

# check if filesystem is mounted (active array)
mounted=0
set +e
mountpoint -q $mountpath
if [ $? -eq 0 ]; then
    mounted=1
fi
set -e

# add fstab entry and mount
if [ $mounted -eq 0 ]; then
    if [ -z $target_uuid ]; then
        echo "Target UUID not populated!"
        exit 1
    fi
    # check if fstab entry exists
    add_fstab=0
    set +e
    grep "^UUID=${target_uuid}" /etc/fstab
    if [ $? -ne 0 ]; then
        add_fstab=1
    fi
    set -e
    # add fstab entry
    if [ $add_fstab -eq 1 ]; then
        echo "Adding $target_uuid to mountpoint $mountpath to /etc/fstab"
        if [ $premium_storage -eq 1 ]; then
            # disable barriers due to RO cache
            if [ $format_as == "btrfs" ]; then
                mo=",nobarrier"
            else
                mo=",barrier=0"
            fi
        else
            # enable discard to save cost on standard storage
            mo=",discard"
        fi
        echo "UUID=$target_uuid $mountpath $format_as defaults,noatime${mo} 0 2" >> /etc/fstab
    fi
    # create mountpath
    mkdir -p $mountpath
    # mount
    mount $mountpath
    # ensure proper permissions
    chmod 1777 $mountpath
fi

# grow underlying filesystem if required
if [ $raid_resized -eq 1 ]; then
    echo "Resizing filesystem at $mountpath..."
    if [ $format_as == "btrfs" ]; then
        btrfs filesystem resize max $mountpath
    elif [ $format_as == ext* ]; then
        resize2fs $mountpath
    else
        echo "Unknown format as: $format_as"
        exit 1
    fi
fi

# log mount
mount | grep $mountpath

# set up server_type software
if [ $server_type == "nfs" ]; then
    # edit /etc/exports
    add_exports=0
    set +e
    grep "^${mountpath}" /etc/exports
    if [ $? -ne 0 ]; then
        add_exports=1
    fi
    if [ $add_exports -eq 1 ]; then
        # note that the * address/hostname allow is ok since we block nfs
        # inbound traffic at the network security group except for allowed
        # ip addresses as specified in the remotefs.json file
        echo "${mountpath} *(rw,sync,root_squash,no_subtree_check,mountpoint=${mountpath})" >> /etc/exports
        systemctl reload nfs-kernel-server.service
    fi
    systemctl status nfs-kernel-server.service
    if [ $? -ne 0 ]; then
        set -e
        # attempt to start
        systemctl restart nfs-kernel-server.service
    fi
    set -e
else
    echo "server_type $server_type not supported."
    exit 1
fi
