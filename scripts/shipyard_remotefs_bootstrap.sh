#!/usr/bin/env bash

set -e
set -o pipefail

DEBIAN_FRONTEND=noninteractive

# constants
gluster_brick_mountpath=/gluster/brick
gluster_brick_location=$gluster_brick_mountpath/brick0
ipaddress=$(ip addr list eth0 | grep "inet " | cut -d' ' -f6 | cut -d/ -f1)

# vars
attach_disks=0
rebalance=0
samba_options=
hostname_prefix=
filesystem=
peer_ips=
server_type=
mountpath=
optimize_tcp=0
server_options=
premium_storage=0
raid_level=-1
mount_options=

# functions
wait_for_device() {
    local device=$1
    local START=$(date -u +"%s")
    echo "Waiting for device $device..."
    while [ ! -b $device ]; do
        local NOW=$(date -u +"%s")
        local DIFF=$((($NOW-$START)/60))
        # fail after 5 minutes of waiting
        if [ $DIFF -ge 5 ]; then
            echo "Could not find device $device"
            exit 1
        fi
        sleep 1
    done
}

setup_nfs() {
    # amend /etc/exports if needed
    add_exports=0
    set +e
    grep "^${mountpath}" /etc/exports
    if [ $? -ne 0 ]; then
        add_exports=1
    fi
    if [ $add_exports -eq 1 ]; then
        # note that the * address/hostname allow is ok since we block nfs
        # inbound traffic at the network security group except for allowed
        # ip addresses as specified in the fs.json file
        echo "${mountpath} *(rw,sync,root_squash,no_subtree_check,mountpoint=${mountpath})" >> /etc/exports
        systemctl reload nfs-kernel-server.service
        exportfs -v
    fi
    systemctl status nfs-kernel-server.service
    if [ $? -ne 0 ]; then
        set -e
        # attempt to start
        systemctl start nfs-kernel-server.service
    fi
    set -e
}

gluster_peer_probe() {
    echo "Attempting to peer with $1"
    peered=0
    local START=$(date -u +"%s")
    set +e
    while :
    do
        # attempt to ping before peering
        ping -c 2 $1 > /dev/null
        if [ $? -eq 0 ]; then
            gluster peer probe $1
            if [ $? -eq 0 ]; then
                peered=1
            fi
        fi
        if [ $peered -eq 1 ]; then
            break
        else
            local NOW=$(date -u +"%s")
            local DIFF=$((($NOW-$START)/60))
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
    local numnodes=$1
    local numpeers=$(($numnodes - 1))
    echo "Waiting for $numpeers peers to reach connected state..."
    # get peer info
    set +e
    while :
    do
        local numready=$(gluster peer status | grep -e '^State: Peer in Cluster' | wc -l)
        if [ $numready == $numpeers ]; then
            break
        fi
        sleep 1
    done
    set -e
    echo "$numpeers host(s) joined peering"
    # delay wait after peer connections
    sleep 5
}

gluster_poll_for_volume() {
    echo "Waiting for gluster volume $1"
    local START=$(date -u +"%s")
    set +e
    while :
    do
        gluster volume info $1
        if [ $? -eq 0 ]; then
            echo $gv_info
            # delay to wait for subvolumes
            sleep 5
            break
        else
            local NOW=$(date -u +"%s")
            local DIFF=$((($NOW-$START)/60))
            # fail after 15 minutes of attempts
            if [ $DIFF -ge 15 ]; then
                echo "Could not connect to gluster volume $1"
                exit 1
            fi
            sleep 2
        fi
    done
    set -e

}

flush_glusterfs_firewall_rules() {
    iptables -F INPUT
    iptables -L INPUT
}

setup_glusterfs() {
    # parse server options in the format: volname,voltype,transport,key:value,...
    IFS=',' read -ra so <<< "$server_options"
    local gluster_volname=${so[0]}
    # create peer ip array
    IFS=',' read -ra peers <<< "$peer_ips"
    # create vm hostnames array
    # we don't need to add these to /etc/hosts because the local DNS
    # resolver will resolve them to the proper private ip addresses
    local myhostname=
    local i=0
    declare -a hosts
    set +e
    for ip in "${peers[@]}"; do
        local host=${hostname_prefix}-vm$i
        hosts=("${hosts[@]}" "$host")
        if [ ${peers[$i]} == $ipaddress ]; then
            myhostname=$host
        fi
        i=$(($i + 1))
    done
    set -e
    if [ -z $myhostname ]; then
        echo "Could not determine own hostname from prefix"
        exit 1
    fi
    # master (first host) performs peering
    if [ ${peers[0]} == $ipaddress ]; then
        # construct brick locations
        local bricks=
        for host in "${hosts[@]}"
        do
            bricks+=" $host:$gluster_brick_location"
            # probe peer
            if [ $host != $myhostname ]; then
                gluster_peer_probe $host
            fi
        done
        # wait for connections
        local numnodes=${#peers[@]}
        gluster_poll_for_connections $numnodes
        local voltype=${so[1],,}
        local volarg=
        if [ "$voltype" == "replica" ] || [ "$voltype" == "stripe" ]; then
            volarg="$voltype $numnodes"
        elif [ "$voltype" != "distributed" ]; then
            # allow custom replica and/or stripe counts
            volarg=$voltype
        fi
        local transport=${so[2],,}
        if [ -z $transport ]; then
            transport="tcp"
        fi
        # check if volume exists
        local start_only=0
        local force=
        set +e
        gluster volume info $gluster_volname 2>&1 | grep "does not exist"
        if [ $? -ne 0 ]; then
            gluster volume info $gluster_volname 2>&1 | grep "Volume Name: $gluster_volname"
            if [ $? -eq 0 ]; then
                start_only=1
            else
                force="force"
            fi
        fi
        set -e
        # create volume
        if [ $start_only -eq 0 ]; then
            echo "Creating gluster volume $gluster_volname $volarg ($force$bricks)"
            gluster volume create $gluster_volname $volarg transport $transport$bricks $force
            # modify volume properties as per input
            for e in "${so[@]:3}"; do
                IFS=':' read -ra kv <<< "$e"
                echo "Setting volume option ${kv[@]}"
                gluster volume set $gluster_volname "${kv[0]}" "${kv[1]}"
            done
        fi
        # start volume
        echo "Starting gluster volume $gluster_volname"
        gluster volume start $gluster_volname
        # heal volume if force created with certain volume types
        if [ ! -z $force ]; then
            if [[ "$voltype" == replica* ]] || [[ "$voltype" == disperse* ]]; then
                echo "Checking if gluster volume $gluster_volname needs healing"
                set +e
                gluster volume heal $gluster_volname info
                if [ $? -eq 0 ]; then
                    gluster volume heal $gluster_volname
                    # print status after heal
                    gluster volume heal $gluster_volname info healed
                    gluster volume heal $gluster_volname info heal-failed
                    gluster volume heal $gluster_volname info split-brain
                fi
                set -e
            fi
        fi
    fi

    # poll for volume created
    gluster_poll_for_volume $gluster_volname

    # check if volume is mounted
    local mounted=0
    set +e
    mountpoint -q $mountpath
    if [ $? -eq 0 ]; then
        mounted=1
    fi
    set -e
    # add fstab entry and mount
    if [ $mounted -eq 0 ]; then
        # check if fstab entry exists
        add_fstab=0
        set +e
        grep "$mountpath glusterfs" /etc/fstab
        if [ $? -ne 0 ]; then
            add_fstab=1
        fi
        set -e
        # add fstab entry
        if [ $add_fstab -eq 1 ]; then
            echo "Adding $gluster_volname to mountpoint $mountpath to /etc/fstab"
            # user systemd automount, boot time mount has a race between
            # mounting and the glusterfs-server being ready
            echo "$myhostname:/$gluster_volname $mountpath glusterfs defaults,_netdev,noauto,x-systemd.automount,fetch-attempts=10 0 2" >> /etc/fstab
        fi
        # create mountpath
        mkdir -p $mountpath
        # mount it
        echo "Mounting gluster volume $gluster_volname locally to $mountpath"
        local START=$(date -u +"%s")
        set +e
        while :
        do
            mount $mountpath
            if [ $? -eq 0 ]; then
                break
            else
                local NOW=$(date -u +"%s")
                local DIFF=$((($NOW-$START)/60))
                # fail after 5 minutes of attempts
                if [ $DIFF -ge 5 ]; then
                    echo "Could not mount gluster volume $gluster_volume to $mountpath"
                    exit 1
                fi
                sleep 1
            fi
        done
        set -e
        # ensure proper permissions on mounted directory
        chmod 1777 $mountpath
    fi
}

# begin processing
while getopts "h?abc:d:f:i:m:no:pr:s:t:" opt; do
    case "$opt" in
        h|\?)
            echo "shipyard_remotefs_bootstrap.sh parameters"
            echo ""
            echo "-a attach mode"
            echo "-b rebalance filesystem on resize"
            echo "-c [share_name:username:password:uid:gid:ro:create_mask:directory_mask] samba options"
            echo "-d [hostname/dns label prefix] hostname prefix"
            echo "-f [filesystem] filesystem"
            echo "-i [peer IPs] peer IPs"
            echo "-m [mountpoint] mountpoint"
            echo "-n Tune TCP parameters"
            echo "-o [server options] server options"
            echo "-p premium storage disks"
            echo "-r [RAID level] RAID level"
            echo "-s [server type] server type"
            echo "-t [mount options] mount options"
            echo ""
            exit 1
            ;;
        a)
            attach_disks=1
            ;;
        b)
            rebalance=1
            ;;
        c)
            IFS=':' read -ra samba_options <<< "$OPTARG"
            ;;
        d)
            hostname_prefix=${OPTARG,,}
            ;;
        f)
            filesystem=${OPTARG,,}
            ;;
        i)
            peer_ips=${OPTARG,,}
            ;;
        m)
            mountpath=$OPTARG
            ;;
        n)
            optimize_tcp=1
            ;;
        o)
            server_options=$OPTARG
            ;;
        p)
            premium_storage=1
            ;;
        r)
            raid_level=$OPTARG
            ;;
        s)
            server_type=${OPTARG,,}
            ;;
        t)
            mount_options=$OPTARG
            ;;
    esac
done
shift $((OPTIND-1))
[ "$1" = "--" ] && shift

# TODO required parameter checks

echo "Parameters:"
echo "  Attach mode: $attach_disks"
echo "  Samba options: ${samba_options[@]}"
echo "  Rebalance filesystem: $rebalance"
echo "  Filesystem: $filesystem"
echo "  Mountpath: $mountpath"
echo "  Tune TCP parameters: $optimize_tcp"
echo "  Premium storage: $premium_storage"
echo "  RAID level: $raid_level"
echo "  Server type: $server_type"
echo "  Server options: $server_options"
echo "  Hostname prefix: $hostname_prefix"
echo "  Peer IPs: $peer_ips"
echo "  IP address of VM: $ipaddress"

# first start prep
if [ $attach_disks -eq 0 ]; then
    # always copy scripts to well known location
    mkdir -p /opt/batch-shipyard
    cp shipyard_remotefs_*.sh /opt/batch-shipyard
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
        apt-get install -y --no-install-recommends nfs-kernel-server nfs4-acl-tools
        # patch buggy nfs-mountd.service unit file
        # https://bugs.launchpad.net/ubuntu/+source/nfs-utils/+bug/1590799
        set +e
        grep "^After=network.target local-fs.target" /lib/systemd/system/nfs-mountd.service
        if [ $? -eq 0 ]; then
            set -e
            sed -i -e "s/^After=network.target local-fs.target/After=rpcbind.target/g" /lib/systemd/system/nfs-mountd.service
        fi
        set -e
        # reload unit files
        systemctl daemon-reload
        # enable and start nfs server
        systemctl enable nfs-kernel-server.service
        # start service if not started
        set +e
        systemctl status nfs-kernel-server.service
        if [ $? -ne 0 ]; then
            set -e
            systemctl start nfs-kernel-server.service
            systemctl status nfs-kernel-server.service
        fi
        set -e
    elif [ $server_type == "glusterfs" ]; then
        # to prevent a race where the master (aka prober) script execution
        # runs well before the child, we should block all gluster connection
        # requests with iptables. we should not remove the filter rules
        # until all local disk setup has been completed.
        iptables -A INPUT -p tcp --destination-port 24007:24008 -j REJECT
        iptables -A INPUT -p tcp --destination-port 49152:49215 -j REJECT
        # install glusterfs server
        apt-get install -y -q --no-install-recommends glusterfs-server
        # enable gluster service
        systemctl enable glusterfs-server
        # start service if not started
        set +e
        systemctl status glusterfs-server
        if [ $? -ne 0 ]; then
            set -e
            systemctl start glusterfs-server
            systemctl status glusterfs-server
        fi
        set -e
        iptables -L INPUT
    else
        echo "server_type $server_type not supported."
        exit 1
    fi
fi

# get all data disks
declare -a data_disks
all_disks=($(lsblk -l -d -n -p -I 8,65,66,67,68 -o NAME))
for disk in "${all_disks[@]}"; do
    # ignore os and ephemeral disks
	if [ $disk != "/dev/sda" ] && [ $disk != "/dev/sdb" ]; then
        data_disks=("${data_disks[@]}" "$disk")
    fi
done
unset all_disks
numdisks=${#data_disks[@]}
echo "found $numdisks data disks: ${data_disks[@]}"

# check if data disks are already partitioned
declare -a skipped_part
for disk in "${data_disks[@]}"; do
    part1=$(partprobe -d -s $disk | cut -d' ' -f4)
    if [ -z $part1 ]; then
        echo "$disk: partition 1 not found. Partitioning $disk."
        parted -a opt -s $disk mklabel gpt mkpart primary 0% 100%
        part1=$(partprobe -d -s $disk | cut -d' ' -f4)
        if [ -z $part1 ]; then
            echo "$disk: partition 1 not found after partitioning."
            exit 1
        fi
        # wait for block device
        wait_for_device $disk$part1
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
if [ $raid_level -ge 0 ]; then
    # redirect mountpath if gluster for bricks
    saved_mp=$mountpath
    if [ $server_type == "glusterfs" ]; then
        mountpath=$gluster_brick_mountpath
    fi
    format_target=0
    md_preexist=0
    if [ $filesystem == "btrfs" ]; then
        if [ $raid_level -ne 0 ]; then
            echo "btrfs with non-RAID 0 is not supported."
            exit 1
        fi
    else
        # find any pre-existing targets
        set +e
        mdadm --detail --scan
        if [ $? -eq 0 ]; then
            target=($(find /dev/md* -maxdepth 0 -type b))
            if [ ${#target[@]} -ne 0 ]; then
                target=${target[0]}
                md_preexist=1
                echo "Existing array found: $target"
                # refresh target uuid to md target
                read target_uuid < <(blkid ${target} | awk -F "[= ]" '{print $3}' | sed 's/\"//g')
            else
                echo "No pre-existing md target could be found"
            fi
        fi
        set -e
        if [ -z $target ]; then
            target=/dev/md0
            echo "Setting default target: $target"
        fi
    fi
    declare -a raid_array
    declare -a all_raid_disks
    set +e
    for disk in "${data_disks[@]}"; do
        if [ $filesystem == "btrfs" ]; then
            btrfs device scan "${disk}1"
        else
            mdadm --examine "${disk}1"
        fi
        if [ $? -ne 0 ]; then
            raid_array=("${raid_array[@]}" "${disk}1")
        fi
        all_raid_disks=("${all_raid_disks[@]}" "${disk}1")
    done
    set -e
    no_raid_count=${#raid_array[@]}
    # take action depending upon no raid count
    if [ $no_raid_count -eq 0 ]; then
        echo "No disks require RAID setup"
    elif [ $no_raid_count -eq $numdisks ]; then
        echo "$numdisks data disks require RAID setup: ${raid_array[@]}"
        if [ $filesystem == "btrfs" ]; then
            if [ $raid_level -eq 0 ]; then
                mkfs.btrfs -d raid0 ${raid_array[@]}
            else
                mkfs.btrfs -m raid${raid_level} ${raid_array[@]}
            fi
        else
            set +e
            # first check if this is a pre-existing array
            mdadm_detail=$(mdadm --detail --scan)
            if [ -z $mdadm_detail ]; then
                set -e
                mdadm --create --verbose $target --level=$raid_level --raid-devices=$numdisks ${raid_array[@]}
                format_target=1
            else
                if [ $md_preexist -eq 0 ]; then
                    echo "Could not determine pre-existing md target"
                    exit 1
                fi
                echo "Not creating a new array since pre-exsting md target found: $target"
            fi
            set -e
        fi
    else
        echo "Mismatch of non-RAID disks $no_raid_count to total disks $numdisks."
        if [ $raid_level -ne 0 ]; then
            echo "Cannot resize with RAID level of $raid_level."
            exit 1
        fi
        if [ $filesystem == "btrfs" ]; then
            # add new block devices first
            echo "Adding devices ${raid_array[@]} to $mountpath"
            btrfs device add ${raid_array[@]} $mountpath
            raid_resized=1
        else
            # add new block device first
            echo "Adding devices ${raid_array[@]} to $target"
            mdadm --add $target ${raid_array[@]}
            # grow the array
            echo "Growing array $target to a total of $numdisks devices"
            mdadm --grow --raid-devices=$numdisks $target
            raid_resized=1
        fi
    fi
    # dump diagnostic info
    if [ $filesystem == "btrfs" ]; then
        btrfs filesystem show
    else
        cat /proc/mdstat
        mdadm --detail $target
    fi
    # get uuid of first disk as target uuid if not populated
    if [ -z $target_uuid ]; then
        read target_uuid < <(blkid ${all_raid_disks[0]} | awk -F "[= ]" '{print $3}' | sed 's/\"//g')
    fi
    # restore mountpath
    mountpath=$saved_mp
    unset saved_mp
fi

# create filesystem on target device
if [ $format_target -eq 1 ]; then
    if [ -z $target ]; then
        echo "Target not specified for format"
        exit 1
    fi
    echo "Creating filesystem on $target."
    if [ $filesystem == "btrfs" ]; then
        mkfs.btrfs $target
    elif [[ $filesystem == ext* ]]; then
        mkfs.${filesystem} -m 0 $target
    else
        echo "Unknown filesystem: $filesystem"
        exit 1
    fi
    # refresh target uuid
    read target_uuid < <(blkid ${target} | awk -F "[= ]" '{print $3}' | sed 's/\"//g')
fi

# mount filesystem
if [ $attach_disks -eq 0 ]; then
    # redirect mountpath if gluster for bricks
    saved_mp=$mountpath
    if [ $server_type == "glusterfs" ]; then
        mountpath=$gluster_brick_mountpath
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
            # construct mount options
            if [ -z $mount_options ]; then
                mount_options="defaults"
            else
                mount_options="defaults,$mount_options"
            fi
            if [ $premium_storage -eq 1 ]; then
                # disable barriers due to cache
                if [ $filesystem == "btrfs" ]; then
                    # also enable ssd optimizations on btrfs
                    mount_options+=",nobarrier,ssd"
                else
                    mount_options+=",barrier=0"
                fi
            else
                # enable discard to save cost on standard storage
                mount_options+=",discard"
            fi
            echo "UUID=$target_uuid $mountpath $filesystem ${mount_options} 0 2" >> /etc/fstab
        fi
        # create mountpath
        mkdir -p $mountpath
        # mount
        mount $mountpath
        if [ $server_type == "nfs" ]; then
            # ensure proper permissions
            chmod 1777 $mountpath
        elif [ $server_type == "glusterfs" ]; then
            # create the brick location
            mkdir -p $gluster_brick_location
        fi
    fi
    # log mount
    mount | grep $mountpath
    # restore mountpath
    mountpath=$saved_mp
    unset saved_mp
fi


# grow underlying filesystem if required
if [ $raid_resized -eq 1 ]; then
    # redirect mountpath if gluster for bricks
    saved_mp=$mountpath
    if [ $server_type == "glusterfs" ]; then
        mountpath=$gluster_brick_mountpath
    fi
    echo "Resizing filesystem at $mountpath."
    if [ $filesystem == "btrfs" ]; then
        btrfs filesystem resize max $mountpath
        # rebalance data and metadata across all devices
        if [ $rebalance -eq 1 ]; then
            echo "Rebalancing btrfs on $mountpath."
            btrfs filesystem balance $mountpath
            echo "Rebalance of btrfs on $mountpath complete."
        fi
    elif [[ $filesystem == ext* ]]; then
        resize2fs $mountpath
    else
        echo "Unknown filesystem: $filesystem"
        exit 1
    fi
    # restore mountpath
    mountpath=$saved_mp
    unset saved_mp
fi

# set up server_type software
if [ $attach_disks -eq 0 ]; then
    if [ $server_type == "nfs" ]; then
        setup_nfs
    elif [ $server_type == "glusterfs" ]; then
        flush_glusterfs_firewall_rules
        setup_glusterfs
    else
        echo "server_type $server_type not supported."
        exit 1
    fi
    # setup samba server if specified
    if [ ! -z $samba_options ]; then
        # install samba
        apt-get install -y -q --no-install-recommends samba
        # parse options
        # [share_name:username:password:uid:gid:ro:create_mask:directory_mask]
        smb_share=${samba_options[0]}
        smb_username=${samba_options[1]}
        smb_password=${samba_options[2]}
        smb_uid=${samba_options[3]}
        smb_gid=${samba_options[4]}
        smb_ro=${samba_options[5]}
        smb_create_mask=${samba_options[6]}
        smb_directory_mask=${samba_options[7]}
        # add some common bits to share def
cat >> /etc/samba/smb.conf << EOF

[$smb_share]
  path = $mountpath
  read only = $smb_ro
  create mask = $smb_create_mask
  directory mask = $smb_directory_mask
EOF
        if [ $smb_username != "nobody" ]; then
            # create group
            groupadd -o -g $smb_gid $smb_username
            # create user (disable login)
            useradd -N -g $smb_gid -p '!' -o -u $smb_uid -s /bin/bash -m -d /home/$smb_username $smb_username
            # add user to smb tdbsam
            echo -ne "${smb_password}\n${smb_password}\n" | smbpasswd -a -s $smb_username
            smbpasswd -e $smb_username
            # modify smb.conf global
            sed -i "/^\[global\]/a load printers = no\nprinting = bsd\nprintcap name = /dev/null\ndisable spoolss = yes\nsecurity = user\nserver signing = auto\nsmb encrypt = auto" /etc/samba/smb.conf
            # modify smb.conf share
cat >> /etc/samba/smb.conf << EOF
  guest ok = no
  browseable = no
  valid users = $smb_username
EOF
        else
            # modify smb.conf global
            sed -i "/^\[global\]/a load printers = no\nprinting = bsd\nprintcap name = /dev/null\ndisable spoolss = yes\nsecurity = user\nserver signing = auto\nsmb encrypt = auto\nguest account = $smb_username" /etc/samba/smb.conf
            # modify smb.conf share
cat >> /etc/samba/smb.conf << EOF
  guest ok = yes
  browseable = yes
EOF
        fi
        # reload unit files
        systemctl daemon-reload
        # add fix to attempt samba service restarts in case of failures.
        # note that this will get overwritten if the systemd-sysv-generator
        # is re-run (e.g., systemctl daemon-reload).
        sed -i -e "s/^Restart=no/Restart=yes/g" /run/systemd/generator.late/smbd.service
        sed -i "/^Restart=yes/a RestartSec=2" /run/systemd/generator.late/smbd.service
        # restart samba service
        systemctl restart smbd.service
    fi
fi
