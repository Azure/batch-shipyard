#!/usr/bin/env bash

set -e
set -o pipefail

dockerversion=$1
shift
nvdriver=$1
shift
intel_mpi=$1
shift

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
mkdir -p /mnt/docker-tmp
sed -i -e 's,.*export DOCKER_TMPDIR=.*,export DOCKER_TMPDIR="/mnt/docker-tmp",g' /etc/default/docker || echo export DOCKER_TMPDIR=\"/mnt/docker-tmp\" >> /etc/default/docker
sed -i -e '/^DOCKER_OPTS=.*/,${s||DOCKER_OPTS=\"-H tcp://127.0.0.1:2375 -H unix:///var/run/docker.sock -g /mnt/docker\"|;b};$q1' /etc/default/docker || echo DOCKER_OPTS=\"-H tcp://127.0.0.1:2375 -H unix:///var/run/docker.sock -g /mnt/docker\" >> /etc/default/docker
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
    curl -OfSsL https://github.com/NVIDIA/nvidia-docker/releases/download/v1.0.1/nvidia-docker_1.0.1-1_amd64.deb
    dpkg -i nvidia-docker_1.0.1-1_amd64.deb
    rm nvidia-docker_1.0.1-1_amd64.deb
    # do not auto-enable nvidia docker service
    systemctl disable nvidia-docker.service
    systemctl start nvidia-docker.service
    systemctl status nvidia-docker.service
    # get driver version
    nvdriverver=`cat /proc/driver/nvidia/version | grep "Kernel Module" | cut -d ' ' -f 9`
    echo nvidia driver version $nvdriverver detected
    # create the docker volume now to avoid volume driver conflicts for
    # tasks. run this in a loop as it can fail if triggered too quickly
    # after start
    NV_START=$(date -u +"%s")
    set +e
    while :
    do
        echo "Attempting to create nvidia-docker volume with version $nvdriverver"
        docker volume create -d nvidia-docker --name nvidia_driver_$nvdriverver
        if [ $? -eq 0 ]; then
            break
        else
            NV_NOW=$(date -u +"%s")
            NV_DIFF=$((($NV_NOW-$NV_START)/60))
            # fail after 5 minutes of attempts
            if [ $NV_DIFF -ge 5 ]; then
                echo "could not create nvidia-docker volume"
                exit 1
            fi
            sleep 1
        fi
    done
    set -e
fi
set -e

# install userland IB requirements
apt-get install -y -q -o Dpkg::Options::="--force-confnew" --no-install-recommends \
    libdapl2 libmlx4-1
# enable RDMA in agent conf
sed -i 's/^# OS.EnableRDMA=.*/OS.EnableRDMA=y/g' /etc/waagent.conf
sed -i 's/^# OS.UpdateRdmaDriver=.*/OS.UpdateRdmaDriver=y/g' /etc/waagent.conf
# allow unlimited memlock for intel mpi
echo "" >> /etc/security/limits.conf
echo "* hard memlock unlimited" >> /etc/security/limits.conf
echo "* soft memlock unlimited" >> /etc/security/limits.conf
# enable ptrace for non-root non-debugger processes for intel mpi
echo 0 | tee /proc/sys/kernel/yama/ptrace_scope
# install intel mpi runtime
if [ ! -f $intel_mpi ]; then
    echo "ERROR: Intel MPI Runtime installer not present: $intel_mpi"
    exit 1
fi
mkdir -p /tmp/intel
tar zxvpf $intel_mpi -C /tmp/intel
cd /tmp/intel/l_mpi-rt*
sed -i -e 's/^ACCEPT_EULA=decline/ACCEPT_EULA=accept/g' silent.cfg
sed -i -e 's,^PSET_INSTALL_DIR=.*,PSET_INSTALL_DIR=/opt/intel,g' silent.cfg
./install.sh -s silent.cfg
cd /opt/intel
ls -alF
rm -rf /tmp/intel
