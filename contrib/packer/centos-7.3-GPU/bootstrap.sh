#!/usr/bin/env bash

set -e
set -o pipefail

dockerversion=$1
shift

USER_MOUNTPOINT=/mnt/resource

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

# prep docker
systemctl stop docker.service
rm -rf /var/lib/docker
mkdir -p /etc/docker
echo "{ \"graph\": \"$USER_MOUNTPOINT/docker\", \"hosts\": [ \"unix:///var/run/docker.sock\", \"tcp://127.0.0.1:2375\" ] }" > /etc/docker/daemon.json.merge
python -c "import json;a=json.load(open('/etc/docker/daemon.json.merge'));b=json.load(open('/etc/docker/daemon.json'));a.update(b);f=open('/etc/docker/daemon.json','w');json.dump(a,f);f.close();"
rm -f /etc/docker/daemon.json.merge
sed -i 's|^ExecStart=/usr/bin/dockerd.*|ExecStart=/usr/bin/dockerd|' /lib/systemd/system/docker.service
systemctl daemon-reload
# do not auto-enable docker to start due to temp disk issues
systemctl disable docker.service
systemctl start docker.service
systemctl status docker.service
