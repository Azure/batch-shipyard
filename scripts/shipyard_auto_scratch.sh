#!/usr/bin/env bash
set -e
set -o pipefail

# args: action, job id, offset (start only)
action="$1"
job_id="$2"

commondir="$AZ_BATCH_NODE_SHARED_DIR/.auto_scratch/${job_id}"
nodefile="$commondir/nodefile"
data_dir="$AZ_BATCH_NODE_ROOT_DIR/mounts/.auto_scratch_data/${job_id}"
mountpoint="$AZ_BATCH_NODE_ROOT_DIR/mounts/auto_scratch/${job_id}"
infofile="/var/tmp/beeond-${job_id}.tmp"

if [ "$action" == "setup" ]; then
    # create nodefile
    IFS=',' read -ra HOSTS <<< "$AZ_BATCH_HOST_LIST"
    mkdir -p "$commondir"
    rm -f "$nodefile"
    touch "$nodefile"
    for node in "${HOSTS[@]}"
    do
        echo "$node" >> "$nodefile"
    done
    echo "Nodefile:"
    cat "$nodefile"

    echo "Creating directories"
    mkdir -p "$data_dir"
    mkdir -p "$mountpoint"

    echo "Preparing ssh/sshd"
    # copy ssh info
    mkdir -p /root/.ssh
    chmod 700 /root/.ssh
    pushd /root/.ssh
    cp ~_azbatch/.ssh/authorized_keys .
    cp ~_azbatch/.ssh/intra_pool_rsa id_rsa
    chmod 600 authorized_keys id_rsa
    popd

    # allow root login
    sed -i 's/PermitRootLogin.*/PermitRootLogin yes/' /etc/ssh/sshd_config
    systemctl reload sshd
fi

if [ "$action" == "start" ]; then
    offset="$3"

    # create configs
    echo "Creating configs"
    if_file="$commondir/intefaces.conf"
    nf_file="$commondir/netfilter.conf"
    echo "eth0" > "$if_file"
    echo "10.0.0.0/8" > "$nf_file"

    metaconf="$commondir/beegfs-meta.conf"
    storageconf="$commondir/beegfs-storage.conf"
    mgmtdconf="$commondir/beegfs-mgmtd.conf"
    helperdconf="$commondir/beegfs-helperd.conf"
    clientconf="$commondir/beegfs-client.conf"
cat > "$clientconf" << EOF
connInterfacesFile = $if_file
connNetFilterFile = $nf_file
EOF

    cp "$clientconf" "$metaconf"
    cp "$clientconf" "$storageconf"
    cp "$clientconf" "$mgmtdconf"
    cp "$clientconf" "$helperdconf"

    echo "Starting BeeGFS Beeond at $mountpoint with port offset $offset"
    beeond start -n "$nodefile" -d "$data_dir" -c "$mountpoint" -f "$commondir" -p "$offset" -i "$infofile"
    df -h
    echo "BeeGFS Beeond setup complete."
fi

if [ "$action" == "stop" ]; then
    echo "Stopping BeeGFS Beeond service"
    beeond stop -n "$nodefile" -P -L -d -c -i "$infofile"
    df -h
fi
