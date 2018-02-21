#!/usr/bin/env bash

set -e
set -o pipefail

dockerversion=$1
shift

# install LIS
curl -fSsL http://download.microsoft.com/download/6/8/F/68FE11B8-FAA4-4F8D-8C7D-74DA7F2CFC8C/lis-rpms-4.2.3-5.tar.gz | tar -zxvpf -
cd LISISO
./install.sh
cd ..
rm -rf LISISO
shutdown -r now

# install docker
yum install -y yum-utils device-mapper-persistent-data lvm2
yum-config-manager --add-repo https://download.docker.com/linux/centos/docker-ce.repo
yum makecache -y fast
yum install -y docker-ce-${dockerversion}

# prep docker
set +e
systemctl stop docker.service
set -e
mkdir -p /mnt/resource/docker-tmp
sed -i -e 's,.*export DOCKER_TMPDIR=.*,export DOCKER_TMPDIR="/mnt/resource/docker-tmp",g' /etc/default/docker || echo export DOCKER_TMPDIR=\"/mnt/resource/docker-tmp\" >> /etc/default/docker
sed -i -e '/^DOCKER_OPTS=.*/,${s||DOCKER_OPTS=\"-H tcp://127.0.0.1:2375 -H unix:///var/run/docker.sock -g /mnt/resource/docker\"|;b};$q1' /etc/default/docker || echo DOCKER_OPTS=\"-H tcp://127.0.0.1:2375 -H unix:///var/run/docker.sock -g /mnt/resource/docker\" >> /etc/default/docker
sed -i '/^\[Service\]/a EnvironmentFile=/etc/default/docker' /lib/systemd/system/docker.service
sed -i '/^ExecStart=/ s/$/ $DOCKER_OPTS/' /lib/systemd/system/docker.service
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
    yum erase -y xorg-x11-drv-nouveau
    rmmod nouveau
    set -e
cat > /etc/modprobe.d/blacklist-nouveau.conf << EOF
blacklist nouveau
blacklist lbm-nouveau
options nouveau modeset=0
alias nouveau off
alias lbm-nouveau off
EOF
    kernel_devel_package="kernel-devel-$(uname -r)"
    curl -fSsLO http://vault.centos.org/7.3.1611/updates/x86_64/Packages/${kernel_devel_package}.rpm
    rpm -Uvh ${kernel_devel_package}.rpm
    yum install -y gcc binutils make
    # install driver
    chmod 755 $nvdriver
    $nvdriver -s
    # install nvidia-docker
    yum-config-manager --add-repo https://nvidia.github.io/nvidia-docker/centos7/x86_64/nvidia-docker.repo
    yum makecache -y fast
    yum install -y nvidia-docker2
    pkill -SIGHUP dockerd
    nvidia-docker version
fi
set -e
