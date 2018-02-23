#!/usr/bin/env bash

set -e
set -o pipefail

dockerversion=$1
shift
nvdriver=$1
shift

USER_MOUNTPOINT=/mnt

# install docker
apt-get update
apt-get install -y -q -o Dpkg::Options::="--force-confnew" --no-install-recommends \
    apt-transport-https ca-certificates curl software-properties-common cgroup-lite
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | apt-key add -
add-apt-repository "deb [arch=amd64] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable"
apt-get update
apt-get install -y -q -o Dpkg::Options::="--force-confnew" --no-install-recommends \
    docker-ce=$dockerversion

# prep docker
systemctl stop docker.service
rm -rf /var/lib/docker
mkdir -p /etc/docker
echo "{ \"graph\": \"$USER_MOUNTPOINT/docker\", \"hosts\": [ \"unix:///var/run/docker.sock\", \"tcp://127.0.0.1:2375\" ] }" > /etc/docker/daemon.json
sed -i 's|^ExecStart=/usr/bin/dockerd.*|ExecStart=/usr/bin/dockerd|' /lib/systemd/system/docker.service
systemctl daemon-reload
# do not auto-enable docker to start due to temp disk issues
systemctl disable docker.service
systemctl start docker.service
systemctl status docker.service

# install nvidia driver/nvidia-docker
set +e
out=$(lspci)
echo "$out" | grep -i nvidia > /dev/null
if [ $? -ne 0 ]; then
    echo $out
    echo "ERROR: No Nvidia card(s) detected!"
else
    if [ ! -f $nvdriver ]; then
        echo "ERROR: Nvidia driver not present: $nvdriver"
        exit 1
    fi
    set +e
    apt-get --purge remove xserver-xorg-video-nouveau
    rmmod nouveau
    set -e
cat > /etc/modprobe.d/blacklist-nouveau.conf << EOF
blacklist nouveau
blacklist lbm-nouveau
options nouveau modeset=0
alias nouveau off
alias lbm-nouveau off
EOF
    apt-get install -y -q --no-install-recommends \
            build-essential
    # install driver
    chmod 755 $nvdriver
    $nvdriver -s
    # install nvidia-docker
    curl -fSsL https://nvidia.github.io/nvidia-docker/gpgkey | apt-key add -
    curl -fSsL https://nvidia.github.io/nvidia-docker/ubuntu16.04/amd64/nvidia-docker.list | \
        tee /etc/apt/sources.list.d/nvidia-docker.list
    apt-get update
    apt-get install nvidia-docker2
    pkill -SIGHUP dockerd
    nvidia-docker version
fi
set -e
