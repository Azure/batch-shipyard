#!/usr/bin/env bash

set -e
set -o pipefail

dockerversion=$1
shift

OS=ubuntu18.04
OS_CODENAME=bionic
USER_MOUNTPOINT=/mnt

# install docker
apt-get update
apt-get install -y -q -o Dpkg::Options::="--force-confnew" --no-install-recommends \
    apt-transport-https ca-certificates curl gnupg2 software-properties-common
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | apt-key add -
add-apt-repository "deb [arch=amd64] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable"
apt-get update
apt-get install -y -q -o Dpkg::Options::="--force-confnew" --no-install-recommends \
    docker-ce="5:${dockerversion}~3-0~ubuntu-${OS_CODENAME}" \
    docker-ce-cli="5:${dockerversion}~3-0~ubuntu-${OS_CODENAME}"

# prep docker
systemctl stop docker.service
rm -rf /var/lib/docker
mkdir -p /etc/docker
echo "{ \"data-root\": \"$USER_MOUNTPOINT/docker\", \"hosts\": [ \"unix:///var/run/docker.sock\", \"tcp://127.0.0.1:2375\" ] }" > /etc/docker/daemon.json
sed -i 's|^ExecStart=/usr/bin/dockerd.*|ExecStart=/usr/bin/dockerd|' /lib/systemd/system/docker.service
systemctl daemon-reload
# do not auto-enable docker to start due to temp disk issues
systemctl disable docker.service
systemctl start docker.service
systemctl status --no-pager docker.service

# install pre-reqs
apt-get install -y -q -o Dpkg::Options::="--force-confnew" --no-install-recommends \
    build-essential libnuma-dev binutils binutils-dev zlib1g zlib1g-dev environment-modules dkms

# path setup
INSTALL_PREFIX=/opt
MODULEFILES_PATH=/usr/share/modules/modulefiles/mpi
mkdir -p $MODULEFILES_PATH

# install Mellanox OFED
OFED_VERSION=4.7-1.0.0.1
pushd /tmp
curl -fSsL http://content.mellanox.com/ofed/MLNX_OFED-${OFED_VERSION}/MLNX_OFED_LINUX-${OFED_VERSION}-${OS}-x86_64.tgz | tar -zxpf -
cd MLNX_OFED_LINUX*
./mlnxofedinstall --force --without-fw-update -vv
popd

# install HPC-X
HPCX_VERSION=v2.5.0
pushd ${INSTALL_PREFIX}
curl -fSsL http://content.mellanox.com/hpc/hpc-x/v2.5/hpcx-${HPCX_VERSION}-gcc-MLNX_OFED_LINUX-${OFED_VERSION}-${OS}-x86_64.tbz | tar -jxpf -
HPCX_PATH=${INSTALL_PREFIX}/hpcx-${HPCX_VERSION}-gcc-MLNX_OFED_LINUX-${OFED_VERSION}-${OS}-x86_64
ls ${HPCX_PATH}
HCOLL_PATH=${HPCX_PATH}/hcoll
ls ${HCOLL_PATH}
UCX_PATH=${HPCX_PATH}/ucx
ls ${UCX_PATH}
popd
# create module file
cat << EOF >> ${MODULEFILES_PATH}/hpcx-${HPCX_VERSION}
#%Module 1.0
#
#  HPCx ${HPCX_VERSION}
#
conflict        mpi
module load ${INSTALL_PREFIX}/hpcx-${HPCX_VERSION}-gcc-MLNX_OFED_LINUX-${OFED_VERSION}-${OS}-x86_64/modulefiles/hpcx
EOF
ln -s ${MODULEFILES_PATH}/hpcx-${HPCX_VERSION} ${MODULEFILES_PATH}/hpcx

# Add sharp lib to ld library path
SHARP_LIB_PATH=/opt/mellanox/sharp/lib
echo "$SHARP_LIB_PATH" > /etc/ld.so.conf.d/mellanox.conf
ldconfig

# install MPICH
MPICH_VERSION=3.3.2
pushd /tmp
curl -fSsL http://www.mpich.org/static/downloads/${MPICH_VERSION}/mpich-${MPICH_VERSION}.tar.gz | tar -zxpf -
cd mpich-${MPICH_VERSION}
# need to add sharp lib so it can find HCOLL
LD_LIBRARY_PATH=${HCOLL_PATH}/lib:${SHARP_LIB_PATH}:${LD_LIBRARY_PATH} ./configure --prefix=${INSTALL_PREFIX}/mpich-${MPICH_VERSION} --with-ucx=${UCX_PATH} --with-hcoll=${HCOLL_PATH} --enable-g=none --enable-fast=yes --with-device=ch4:ucx
make
make install
popd
# create module file
cat << EOF >> ${MODULEFILES_PATH}/mpich-${MPICH_VERSION}
#%Module 1.0
#
#  MPICH ${MPICH_VERSION}
#
conflict        mpi
prepend-path    PATH            ${INSTALL_PREFIX}/mpich-${MPICH_VERSION}/bin
prepend-path    LD_LIBRARY_PATH ${INSTALL_PREFIX}/mpich-${MPICH_VERSION}/lib
prepend-path    MANPATH         ${INSTALL_PREFIX}/mpich-${MPICH_VERSION}/share/man
setenv          MPI_BIN         ${INSTALL_PREFIX}/mpich-${MPICH_VERSION}/bin
setenv          MPI_INCLUDE     ${INSTALL_PREFIX}/mpich-${MPICH_VERSION}/include
setenv          MPI_LIB         ${INSTALL_PREFIX}/mpich-${MPICH_VERSION}/lib
setenv          MPI_MAN         ${INSTALL_PREFIX}/mpich-${MPICH_VERSION}/share/man
setenv          MPI_HOME        ${INSTALL_PREFIX}/mpich-${MPICH_VERSION}
EOF
ln -s ${MODULEFILES_PATH}/mpich-${MPICH_VERSION} ${MODULEFILES_PATH}/mpich

# install OpenMPI
OMPI_VERSION=4.0.2
pushd /tmp
curl -fSsL https://download.open-mpi.org/release/open-mpi/v4.0/openmpi-${OMPI_VERSION}.tar.gz | tar -zxpf -
cd openmpi-${OMPI_VERSION}
# need to add sharp lib so it can find HCOLL
LD_LIBRARY_PATH=${HCOLL_PATH}/lib:${SHARP_LIB_PATH}:${LD_LIBRARY_PATH} ./configure --prefix=${INSTALL_PREFIX}/openmpi-${OMPI_VERSION} --with-ucx=${UCX_PATH} --with-hcoll=${HCOLL_PATH} --enable-mpirun-prefix-by-default --with-platform=contrib/platform/mellanox/optimized
make -j
make install
popd
# create module file
cat << EOF >> ${MODULEFILES_PATH}/openmpi-${OMPI_VERSION}
#%Module 1.0
#
#  OpenMPI ${OMPI_VERSION}
#
conflict        mpi
prepend-path    PATH            ${INSTALL_PREFIX}/openmpi-${OMPI_VERSION}/bin
prepend-path    LD_LIBRARY_PATH ${INSTALL_PREFIX}/openmpi-${OMPI_VERSION}/lib
prepend-path    MANPATH         ${INSTALL_PREFIX}/openmpi-${OMPI_VERSION}/share/man
setenv          MPI_BIN         ${INSTALL_PREFIX}/openmpi-${OMPI_VERSION}/bin
setenv          MPI_INCLUDE     ${INSTALL_PREFIX}/openmpi-${OMPI_VERSION}/include
setenv          MPI_LIB         ${INSTALL_PREFIX}/openmpi-${OMPI_VERSION}/lib
setenv          MPI_MAN         ${INSTALL_PREFIX}/openmpi-${OMPI_VERSION}/share/man
setenv          MPI_HOME        ${INSTALL_PREFIX}/openmpi-${OMPI_VERSION}
EOF
ln -s ${MODULEFILES_PATH}/openmpi-${OMPI_VERSION} ${MODULEFILES_PATH}/openmpi

# install MVAPICH
MVAPICH_VERSION=2.3.2
pushd /tmp
curl -fSsL http://mvapich.cse.ohio-state.edu/download/mvapich/mv2/mvapich2-${MVAPICH_VERSION}.tar.gz | tar -zxpf -
cd mvapich2-${MVAPICH_VERSION}
./configure --prefix=${INSTALL_PREFIX}/mvapich2-${MVAPICH_VERSION} --enable-g=none --enable-fast=yes
make -j
make install
popd
# create module file
cat << EOF >> ${MODULEFILES_PATH}/mvapich2-${MVAPICH_VERSION}
#%Module 1.0
#
#  MVAPICH2 ${MVAPICH_VERSION}
#
conflict        mpi
prepend-path    PATH            ${INSTALL_PREFIX}/mvapich2-${MVAPICH_VERSION}/bin
prepend-path    LD_LIBRARY_PATH ${INSTALL_PREFIX}/mvapich2-${MVAPICH_VERSION}/lib
prepend-path    MANPATH         ${INSTALL_PREFIX}/mvapich2-${MVAPICH_VERSION}/share/man
setenv          MPI_BIN         ${INSTALL_PREFIX}/mvapich2-${MVAPICH_VERSION}/bin
setenv          MPI_INCLUDE     ${INSTALL_PREFIX}/mvapich2-${MVAPICH_VERSION}/include
setenv          MPI_LIB         ${INSTALL_PREFIX}/mvapich2-${MVAPICH_VERSION}/lib
setenv          MPI_MAN         ${INSTALL_PREFIX}/mvapich2-${MVAPICH_VERSION}/share/man
setenv          MPI_HOME        ${INSTALL_PREFIX}/mvapich2-${MVAPICH_VERSION}
EOF
ln -s ${MODULEFILES_PATH}/mvapich2-${MVAPICH_VERSION} ${MODULEFILES_PATH}/mvapich2

# install intel mpi 2018 runtime
IMPI_2018_VERSION=l_mpi_2018.5.288
pushd /tmp
curl -fSsL http://registrationcenter-download.intel.com/akdlm/irc_nas/tec/15614/${IMPI_2018_VERSION}.tgz | tar -zxpf -
cd ./${IMPI_2018_VERSION}
sed -i -e 's/^ACCEPT_EULA=.*/ACCEPT_EULA=accept/g' silent.cfg
sed -i -e 's,^ARCH_SELECTED=.*,ARCH_SELECTED=INTEL64,g' silent.cfg
./install.sh --silent silent.cfg
# enable ptrace for non-root non-debugger processes for intel mpi
echo 0 | tee /proc/sys/kernel/yama/ptrace_scope
popd
# create module file
cat << EOF >> ${MODULEFILES_PATH}/impi_${IMPI_2018_VERSION}
#%Module 1.0
#
#  Intel MPI ${IMPI_2018_VERSION}
#
conflict        mpi
prepend-path    PATH            ${INSTALL_PREFIX}/intel/impi/${IMPI_2018_VERSION}/intel64/bin
prepend-path    LD_LIBRARY_PATH ${INSTALL_PREFIX}/intel/impi/${IMPI_2018_VERSION}/intel64/lib
prepend-path    MANPATH         ${INSTALL_PREFIX}/intel/impi/${IMPI_2018_VERSION}/man
setenv          MPI_BIN         ${INSTALL_PREFIX}/intel/impi/${IMPI_2018_VERSION}/intel64/bin
setenv          MPI_INCLUDE     ${INSTALL_PREFIX}/intel/impi/${IMPI_2018_VERSION}/intel64/include
setenv          MPI_LIB         ${INSTALL_PREFIX}/intel/impi/${IMPI_2018_VERSION}/intel64/lib
setenv          MPI_MAN         ${INSTALL_PREFIX}/intel/impi/${IMPI_2018_VERSION}/man
setenv          MPI_HOME        ${INSTALL_PREFIX}/intel/impi/${IMPI_2018_VERSION}/intel64
EOF
ln -s ${MODULEFILES_PATH}/impi_${IMPI_2018_VERSION} ${MODULEFILES_PATH}/impi

# install intel mpi 2019 runtime
IMPI_2019_VERSION=l_mpi_2019.5.281
pushd /tmp
curl -fSsL http://registrationcenter-download.intel.com/akdlm/irc_nas/tec/15838/${IMPI_2019_VERSION}.tgz | tar -zxpf -
cd ./${IMPI_2019_VERSION}
sed -i -e 's/^ACCEPT_EULA=.*/ACCEPT_EULA=accept/g' silent.cfg
sed -i -e 's,^ARCH_SELECTED=.*,ARCH_SELECTED=INTEL64,g' silent.cfg
./install.sh --silent silent.cfg
popd
# create module file
cat << EOF >> ${MODULEFILES_PATH}/impi_${IMPI_2019_VERSION}
#%Module 1.0
#
#  Intel MPI ${IMPI_2019_VERSION}
#
conflict        mpi
prepend-path    PATH            ${INSTALL_PREFIX}/intel/impi/${IMPI_2019_VERSION}/intel64/bin
prepend-path    LD_LIBRARY_PATH ${INSTALL_PREFIX}/intel/impi/${IMPI_2019_VERSION}/intel64/lib
prepend-path    MANPATH         ${INSTALL_PREFIX}/intel/impi/${IMPI_2019_VERSION}/man
setenv          MPI_BIN         ${INSTALL_PREFIX}/intel/impi/${IMPI_2019_VERSION}/intel64/bin
setenv          MPI_INCLUDE     ${INSTALL_PREFIX}/intel/impi/${IMPI_2019_VERSION}/intel64/include
setenv          MPI_LIB         ${INSTALL_PREFIX}/intel/impi/${IMPI_2019_VERSION}/intel64/lib
setenv          MPI_MAN         ${INSTALL_PREFIX}/intel/impi/${IMPI_2019_VERSION}/man
setenv          MPI_HOME        ${INSTALL_PREFIX}/intel/impi/${IMPI_2019_VERSION}/intel64
EOF
ln -s ${MODULEFILES_PATH}/impi_${IMPI_2019_VERSION} ${MODULEFILES_PATH}/impi-2019

# enable RDMA in agent conf
sed -i 's/^# OS.EnableRDMA=.*/OS.EnableRDMA=y/g' /etc/waagent.conf
sed -i 's/^# AutoUpdate.Enabled=.*/AutoUpdate.Enabled=y/g' /etc/waagent.conf

# adjust limits
echo "" >> /etc/security/limits.conf
echo "* hard memlock unlimited" >> /etc/security/limits.conf
echo "* soft memlock unlimited" >> /etc/security/limits.conf
echo "* hard nofile 65535" >> /etc/security/limits.conf
echo "* soft nofile 65535" >> /etc/security/limits.conf

# enable zone reclaim mode
echo "vm.zone_reclaim_mode = 1" >> /etc/sysctl.conf
sysctl -p

# cleanup apt
apt autoremove -y
