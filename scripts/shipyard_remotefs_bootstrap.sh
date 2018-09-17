#!/usr/bin/env bash

set -e
set -o pipefail

export DEBIAN_FRONTEND=noninteractive

# constants
GLUSTER_VERSION=4.1
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
ne_opts=

# functions
wait_for_device() {
    local device=$1
    local START
    START=$(date -u +"%s")
    echo "Waiting for device $device..."
    while [ ! -b "$device" ]; do
        local NOW
        NOW=$(date -u +"%s")
        local DIFF=$(((NOW-START)/60))
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
    if ! grep "^${mountpath}" /etc/exports; then
        add_exports=1
    fi
    if [ $add_exports -eq 1 ]; then
        # parse server options for export mappings
        set -f
        IFS=';' read -ra so <<< "$server_options"
        for host in "${so[@]}"; do
            IFS='%' read -ra he <<< "$host"
            echo "${mountpath} ${he[0]}(${he[1]},mountpoint=${mountpath})" >> /etc/exports
        done
        set +f
        systemctl reload nfs-kernel-server.service
    fi
    if ! systemctl --no-pager status nfs-kernel-server.service; then
        set -e
        # attempt to start
        systemctl start nfs-kernel-server.service
        systemctl --no-pager status nfs-kernel-server.service
    fi
    set -e
    exportfs -v
}

gluster_peer_probe() {
    echo "Attempting to peer with $1"
    peered=0
    local START
    START=$(date -u +"%s")
    set +e
    while :
    do
        # attempt to ping before peering
        if ping -c 2 "$1" > /dev/null; then
            if gluster peer probe "$1"; then
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
    local numnodes=$1
    local numpeers=$((numnodes - 1))
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
    # delay wait after peer connections
    sleep 5
}

gluster_poll_for_volume() {
    echo "Waiting for gluster volume $1"
    local START
    START=$(date -u +"%s")
    set +e
    while :
    do
        if gluster volume info "$1"; then
            # delay to wait for subvolumes
            sleep 5
            break
        else
            local NOW
            NOW=$(date -u +"%s")
            local DIFF=$(((NOW-START)/60))
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
    while [ $i -lt ${#peers[@]} ]; do
        local host
        host=${hostname_prefix}-vm$(printf %03d $i)
        hosts=("${hosts[@]}" "$host")
        if [ "${peers[$i]}" == "$ipaddress" ]; then
            myhostname=$host
        fi
        i=$((i + 1))
    done
    set -e
    if [ -z "$myhostname" ]; then
        echo "Could not determine own hostname from prefix"
        exit 1
    fi
    # master (first host) performs peering
    if [ "${peers[0]}" == "$ipaddress" ]; then
        # construct brick locations
        local bricks
        for host in "${hosts[@]}"; do
            bricks+=" $host:$gluster_brick_location"
            # probe peer
            if [ "$host" != "$myhostname" ]; then
                gluster_peer_probe "$host"
            fi
        done
        # wait for connections
        local numnodes=${#peers[@]}
        gluster_poll_for_connections "$numnodes"
        local voltype=${so[1],,}
        local volarg
        if [ "$voltype" == "replica" ] || [ "$voltype" == "stripe" ]; then
            volarg="$voltype $numnodes"
        elif [ "$voltype" != "distributed" ]; then
            # allow custom replica and/or stripe counts
            volarg=$voltype
        fi
        local transport=${so[2],,}
        if [ -z "$transport" ]; then
            transport="tcp"
        fi
        # check if volume exists
        local start_only=0
        local force
        set +e
        if ! gluster volume info "$gluster_volname" 2>&1 | grep "does not exist"; then
            if gluster volume info "$gluster_volname" 2>&1 | grep "Volume Name: $gluster_volname"; then
                start_only=1
            else
                force="force"
            fi
        fi
        set -e
        # create volume
        if [ $start_only -eq 0 ]; then
            echo "Creating gluster volume $gluster_volname $volarg ($force$bricks)"
            # shellcheck disable=SC2086
            gluster volume create "$gluster_volname" ${volarg} transport "${transport}"${bricks} $force
            # modify volume properties as per input
            for e in "${so[@]:3}"; do
                IFS=':' read -ra kv <<< "$e"
                echo "Setting volume option ${kv[*]}"
                gluster volume set "$gluster_volname" "${kv[0]}" "${kv[1]}"
            done
        fi
        # start volume
        echo "Starting gluster volume $gluster_volname"
        gluster volume start "$gluster_volname"
        # heal volume if force created with certain volume types
        if [ -n "$force" ]; then
            if [[ "$voltype" == replica* ]] || [[ "$voltype" == disperse* ]]; then
                echo "Checking if gluster volume $gluster_volname needs healing"
                set +e
                if gluster volume heal "$gluster_volname" info; then
                    gluster volume heal "$gluster_volname"
                    # print status after heal
                    gluster volume heal "$gluster_volname" info healed
                    gluster volume heal "$gluster_volname" info heal-failed
                    gluster volume heal "$gluster_volname" info split-brain
                fi
                set -e
            fi
        fi
    fi

    # poll for volume created
    gluster_poll_for_volume "$gluster_volname"

    # check if volume is mounted
    local mounted=0
    set +e
    if mountpoint -q "$mountpath"; then
        mounted=1
    fi
    set -e
    # add fstab entry and mount
    if [ $mounted -eq 0 ]; then
        # check if fstab entry exists
        add_fstab=0
        set +e
        if ! grep "$mountpath glusterfs" /etc/fstab; then
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
        local START
        START=$(date -u +"%s")
        set +e
        while :
        do
            if mount "$mountpath"; then
                break
            else
                local NOW
                NOW=$(date -u +"%s")
                local DIFF=$(((NOW-START)/60))
                # fail after 5 minutes of attempts
                if [ $DIFF -ge 5 ]; then
                    echo "Could not mount gluster volume $gluster_volname to $mountpath"
                    exit 1
                fi
                sleep 1
            fi
        done
        set -e
        # ensure proper permissions on mounted directory
        chmod 1777 "$mountpath"
    fi
}

install_and_start_node_exporter() {
    if [ -z "${ne_opts}" ]; then
        echo "Prometheus node exporter disabled."
        return
    else
        echo "Installing Prometheus node exporter"
    fi
    # install
    tar zxvpf node_exporter.tar.gz
    cp node_exporter-*.linux-amd64/node_exporter .
    rm -rf node_exporter-*.linux-amd64
    chmod +x node_exporter
    mv node_exporter /usr/sbin
    # configure
    local nfs
    nfs="--no-collector.nfs"
    if [ "${server_type}" == "nfs" ]; then
        nfs="--collector.nfs --collector.mountstats"
    fi
    local ne_port
    local pneo
    IFS=',' read -ra pneo <<< "$ne_opts"
    ne_port=${pneo[0]}
    pneo=("${pneo[@]:1}")
cat << EOF > /etc/node_exporter.conf
OPTIONS="$nfs --no-collector.textfile --no-collector.wifi --no-collector.zfs --web.listen-address=\":${ne_port}\" ${pneo[@]}"
EOF
cat << 'EOF' > /etc/systemd/system/node-exporter.service
[Unit]
Description=Node Exporter

[Service]
Restart=always
EnvironmentFile=/etc/node_exporter.conf
ExecStart=/usr/sbin/node_exporter $OPTIONS

[Install]
WantedBy=multi-user.target
EOF
    # start
    systemctl daemon-reload
    systemctl start node-exporter
    systemctl enable node-exporter
    systemctl --no-pager status node-exporter
    echo "Prometheus node exporter enabled."
}

# begin processing
while getopts "h?abc:d:e:f:i:m:no:pr:s:t:" opt; do
    case "$opt" in
        h|\?)
            echo "shipyard_remotefs_bootstrap.sh parameters"
            echo ""
            echo "-a attach mode"
            echo "-b rebalance filesystem on resize"
            echo "-c [share_name:username:password:uid:gid:ro:create_mask:directory_mask] samba options"
            echo "-d [hostname/dns label prefix] hostname prefix"
            echo "-e [node exporter port and opts] ne_port,opts"
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
        e)
            ne_opts=$OPTARG
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
echo "  Samba options: ${samba_options[*]}"
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
echo "  Node exporter: $ne_opts"

# start prometheus collectors
install_and_start_node_exporter

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
    if [ "$server_type" == "nfs" ]; then
        apt-get install -y --no-install-recommends nfs-kernel-server nfs4-acl-tools
        # enable and start nfs server
        systemctl enable nfs-kernel-server.service
        # start service if not started
        set +e
        if ! systemctl --no-pager status nfs-kernel-server.service; then
            set -e
            systemctl start nfs-kernel-server.service
            systemctl --no-pager status nfs-kernel-server.service
        fi
        set -e
    elif [ "$server_type" == "glusterfs" ]; then
        # to prevent a race where the master (aka prober) script execution
        # runs well before the child, we should block all gluster connection
        # requests with iptables. we should not remove the filter rules
        # until all local disk setup has been completed.
        iptables -A INPUT -p tcp --destination-port 24007:24008 -j REJECT
        iptables -A INPUT -p tcp --destination-port 49152:49215 -j REJECT
        # install glusterfs server from ppa
        add-apt-repository ppa:gluster/glusterfs-${GLUSTER_VERSION}
        apt-get update
        apt-get install -y -q --no-install-recommends glusterfs-server
        # enable gluster service
        systemctl --no-pager status glustereventsd
        systemctl enable glusterd
        # start service if not started
        set +e
        if ! systemctl --no-pager status glusterd; then
            set -e
            systemctl start glusterd
            systemctl --no-pager status glusterd
        fi
        set -e
        # list iptables filtering rules
        iptables -L INPUT
    else
        echo "server_type $server_type not supported."
        exit 1
    fi
fi

# get all data disks
declare -a data_disks
mapfile -t all_disks < <(lsblk -l -d -n -p -I 8,65,66,67,68 -o NAME)
for disk in "${all_disks[@]}"; do
    # ignore os and ephemeral disks
	if [ "$disk" != "/dev/sda" ] && [ "$disk" != "/dev/sdb" ]; then
        data_disks=("${data_disks[@]}" "$disk")
    fi
done
unset all_disks
numdisks=${#data_disks[@]}
echo "found $numdisks data disks: ${data_disks[*]}"

# check if data disks are already partitioned
declare -a skipped_part
for disk in "${data_disks[@]}"; do
    part1=$(partprobe -d -s "$disk" | cut -d' ' -f4)
    if [ -z "$part1" ]; then
        echo "$disk: partition 1 not found. Partitioning $disk."
        parted -a opt -s "$disk" mklabel gpt mkpart primary 0% 100%
        part1=$(partprobe -d -s "$disk" | cut -d' ' -f4)
        if [ -z "$part1" ]; then
            echo "$disk: partition 1 not found after partitioning."
            exit 1
        fi
        # wait for block device
        wait_for_device "${disk}""${part1}"
    else
        echo "$disk: partition 1 found. Skipping partitioning."
        skipped_part=("${skipped_part[@]}" "$disk")
    fi
done

# set format target
target_md=
target_uuid=
format_target=1
# check if there was only one skipped disk during partitioning
if [ ${#skipped_part[@]} -eq "$numdisks" ] && [ "$numdisks" -eq 1 ]; then
    target_md=${skipped_part[0]}
    read -r target_uuid target_fs < <(blkid -u filesystem "$target_md" | awk -F "[= ]" '{print $3" "$5}'|tr -d "\"")
    if [ -n "$target_fs" ]; then
        format_target=0
    fi
fi

# check if disks are already in raid set
raid_resized=0
if [ "$raid_level" -ge 0 ]; then
    # redirect mountpath if gluster for bricks
    saved_mp=$mountpath
    if [ "$server_type" == "glusterfs" ]; then
        mountpath=$gluster_brick_mountpath
    fi
    format_target=0
    md_preexist=0
    if [ "$filesystem" == "btrfs" ]; then
        if [ "$raid_level" -ne 0 ]; then
            echo "btrfs with non-RAID 0 is not supported."
            exit 1
        fi
    else
        # find any pre-existing targets
        set +e
        if mdadm --detail --scan; then
            mapfile -t target < <(find /dev/md* -maxdepth 0 -type b)
            if [ ${#target[@]} -ne 0 ]; then
                md_preexist=1
                target_md=${target[0]}
                echo "Existing array found: $target_md"
                # refresh target uuid to md target
                read -r target_uuid < <(blkid "$target_md" | awk -F "[= ]" '{print $3}' | sed 's/\"//g')
            else
                echo "No pre-existing md target could be found"
            fi
        fi
        set -e
        if [ -z "$target_md" ]; then
            target_md=/dev/md0
            echo "Setting default target: $target_md"
        fi
    fi
    declare -a raid_array
    declare -a all_raid_disks
    set +e
    for disk in "${data_disks[@]}"; do
        if [ "$filesystem" == "btrfs" ]; then
            btrfs device scan "${disk}1"
            rc=$?
        else
            mdadm --examine "${disk}1"
            rc=$?
        fi
        if [ $rc -ne 0 ]; then
            raid_array=("${raid_array[@]}" "${disk}1")
        fi
        all_raid_disks=("${all_raid_disks[@]}" "${disk}1")
    done
    set -e
    no_raid_count=${#raid_array[@]}
    # take action depending upon no raid count
    if [ "$no_raid_count" -eq 0 ]; then
        echo "No disks require RAID setup"
    elif [ "$no_raid_count" -eq "$numdisks" ]; then
        echo "$numdisks data disks require RAID setup: ${raid_array[*]}"
        if [ "$filesystem" == "btrfs" ]; then
            if [ "$raid_level" -eq 0 ]; then
                mkfs.btrfs -d raid0 "${raid_array[@]}"
            else
                mkfs.btrfs -m raid"${raid_level}" "${raid_array[@]}"
            fi
        else
            set +e
            # first check if this is a pre-existing array
            mdadm_detail=$(mdadm --detail --scan)
            if [ -z "$mdadm_detail" ]; then
                set -e
                mdadm --create --verbose $target_md --level="$raid_level" --raid-devices="$numdisks" "${raid_array[@]}"
                format_target=1
            else
                if [ $md_preexist -eq 0 ]; then
                    echo "Could not determine pre-existing md target"
                    exit 1
                fi
                echo "Not creating a new array since pre-exsting md target found: $target_md"
            fi
            set -e
        fi
    else
        echo "Mismatch of non-RAID disks $no_raid_count to total disks $numdisks."
        if [ "$raid_level" -ne 0 ]; then
            echo "Cannot resize with RAID level of $raid_level."
            exit 1
        fi
        if [ "$filesystem" == "btrfs" ]; then
            # add new block devices first
            echo "Adding devices ${raid_array[*]} to $mountpath"
            btrfs device add "${raid_array[@]}" $mountpath
            raid_resized=1
        else
            # increase raid rebuild/resync/reshape speed
            oldmin=$(cat /proc/sys/dev/raid/speed_limit_min)
            oldmax=$(cat /proc/sys/dev/raid/speed_limit_max)
            echo 100000 > /proc/sys/dev/raid/speed_limit_min
            echo 500000 > /proc/sys/dev/raid/speed_limit_max
            # add new block device and grow
            echo "Growing array $target_md to a total of $numdisks devices: ${raid_array[*]}"
            mdadm --grow "$target_md" --raid-devices="$numdisks" --add "${raid_array[@]}"
            sleep 5
            mdadm --detail --scan
            # wait until reshape completes
            set +e
            while :
            do
                if ! mdadm --detail --scan | grep "spares="; then
                    break
                fi
                sleep 10
            done
            # ensure array is back to RAID-0
            if ! mdadm --detail "$target_md" | grep "Raid Level : raid0"; then
                mdadm --grow --level 0 "$target_md"
            fi
            set -e
            echo "$oldmin" > /proc/sys/dev/raid/speed_limit_min
            echo "$oldmax" > /proc/sys/dev/raid/speed_limit_max
            raid_resized=1
        fi
    fi
    # dump diagnostic info
    if [ "$filesystem" == "btrfs" ]; then
        btrfs filesystem show
    else
        cat /proc/mdstat
        mdadm --detail "$target_md"
    fi
    # get uuid of first disk as target uuid if not populated
    if [ -z "$target_uuid" ]; then
        read -r target_uuid < <(blkid "${all_raid_disks[0]}" | awk -F "[= ]" '{print $3}' | sed 's/\"//g')
    fi
    # restore mountpath
    mountpath=$saved_mp
    unset saved_mp
fi

# create filesystem on target device
if [ $format_target -eq 1 ]; then
    if [ -z "$target_md" ]; then
        echo "Target not specified for format"
        exit 1
    fi
    sleep 5
    echo "Creating filesystem on $target_md"
    if [ "$filesystem" == "btrfs" ]; then
        mkfs.btrfs "$target_md"
    elif [ "$filesystem" == "xfs" ]; then
        mdadm --detail --scan
        set +e
        # let mkfs.xfs automatically select the appropriate su/sw
        if ! mkfs.xfs "$target_md"; then
            # mkfs.xfs can sometimes fail because it can't query the
            # underlying device, try to re-assemble and retry format
            set -e
            mdadm --verbose --assemble "$target_md" "${raid_array[@]}"
            mdadm --detail --scan
            mkfs.xfs "$target_md"
        fi
        set -e
    elif [[ $filesystem == ext* ]]; then
        mkfs."${filesystem}" -m 0 "$target_md"
    else
        echo "Unknown filesystem: $filesystem"
        exit 1
    fi
    # refresh target uuid
    read -r target_uuid < <(blkid "${target_md}" | awk -F "[= ]" '{print $3}' | sed 's/\"//g')
fi

# mount filesystem
if [ $attach_disks -eq 0 ]; then
    # redirect mountpath if gluster for bricks
    saved_mp=$mountpath
    if [ "$server_type" == "glusterfs" ]; then
        mountpath=$gluster_brick_mountpath
    fi
    # check if filesystem is mounted (active array)
    mounted=0
    set +e
    if mountpoint -q $mountpath; then
        mounted=1
    fi
    set -e
    # add fstab entry and mount
    if [ $mounted -eq 0 ]; then
        if [ -z "$target_uuid" ]; then
            echo "Target UUID not populated!"
            exit 1
        fi
        # check if fstab entry exists
        add_fstab=0
        set +e
        if ! grep "^UUID=${target_uuid}" /etc/fstab; then
            add_fstab=1
        fi
        set -e
        # add fstab entry
        if [ $add_fstab -eq 1 ]; then
            echo "Adding $target_uuid to mountpoint $mountpath to /etc/fstab"
            # construct mount options
            if [ -z "$mount_options" ]; then
                mount_options="defaults"
            else
                mount_options="defaults,$mount_options"
            fi
            if [ $premium_storage -eq 1 ]; then
                # disable barriers due to cache
                if [ "$filesystem" == "btrfs" ]; then
                    # also enable ssd optimizations on btrfs
                    mount_options+=",nobarrier,ssd"
                elif [ "$filesystem" == "xfs" ]; then
                    mount_options+=",nobarrier"
                elif [[ $filesystem == ext* ]]; then
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
        if [ "$server_type" == "nfs" ]; then
            # ensure proper permissions
            chmod 1777 $mountpath
        elif [ "$server_type" == "glusterfs" ]; then
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
    if [ "$server_type" == "glusterfs" ]; then
        mountpath=$gluster_brick_mountpath
    fi
    echo "Resizing filesystem at $mountpath."
    if [ "$filesystem" == "btrfs" ]; then
        btrfs filesystem resize max $mountpath
        # rebalance data and metadata across all devices
        if [ $rebalance -eq 1 ]; then
            echo "Rebalancing btrfs on $mountpath."
            btrfs filesystem balance $mountpath
            echo "Rebalance of btrfs on $mountpath complete."
        fi
    elif [ "$filesystem" == "xfs" ]; then
        xfs_growfs $mountpath
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
    if [ "$server_type" == "nfs" ]; then
        setup_nfs
    elif [ "$server_type" == "glusterfs" ]; then
        flush_glusterfs_firewall_rules
        setup_glusterfs
    else
        echo "server_type $server_type not supported."
        exit 1
    fi
    # setup samba server if specified
    if [ -n "$samba_options" ]; then
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
        if [ "$smb_username" != "nobody" ]; then
            # create group
            groupadd -o -g "$smb_gid" "$smb_username"
            # create user (disable login)
            useradd -N -g "$smb_gid" -p '!' -o -u "$smb_uid" -s /bin/bash -m -d /home/"${smb_username}" "$smb_username"
            # add user to smb tdbsam
            echo -ne "${smb_password}\\n${smb_password}\\n" | smbpasswd -a -s "$smb_username"
            smbpasswd -e "$smb_username"
            # modify smb.conf global
            sed -i "/^\\[global\\]/a load printers = no\\nprinting = bsd\\nprintcap name = /dev/null\\ndisable spoolss = yes\\nsecurity = user\\nserver signing = auto\\nsmb encrypt = auto" /etc/samba/smb.conf
            # modify smb.conf share
cat >> /etc/samba/smb.conf << EOF
  guest ok = no
  browseable = no
  valid users = $smb_username
EOF
        else
            # modify smb.conf global
            sed -i "/^\\[global\\]/a load printers = no\\nprinting = bsd\\nprintcap name = /dev/null\\ndisable spoolss = yes\\nsecurity = user\\nserver signing = auto\\nsmb encrypt = auto\\nguest account = $smb_username" /etc/samba/smb.conf
            # modify smb.conf share
cat >> /etc/samba/smb.conf << EOF
  guest ok = yes
  browseable = yes
EOF
        fi
        # add auto-restart
        sed -i "/^\\[Service\\]/aRestart=yes\\nRestartSec=2" /lib/systemd/system/smbd.service
        # reload unit files
        systemctl daemon-reload
        # restart samba service
        systemctl restart smbd.service
        systemctl --no-pager status smbd.service
    fi
fi
