FROM centos:7.6.1810
 
# set up base
COPY ssh_config /root/.ssh/config
RUN yum install -y epel-release \
    && yum groupinstall -y "Development tools" \
    && yum install -y \
        ca-certificates wget openssh-server openssh-clients net-tools \
        numactl-devel gtk2 atk cairo tcsh libnl3 tcl libmnl tk

# set up ssh keys
RUN mkdir -p /var/run/sshd \
    && ssh-keygen -A \
    && sed -i 's/UsePAM yes/UsePAM no/g' /etc/ssh/sshd_config \
    && sed -i 's/#PermitRootLogin yes/PermitRootLogin yes/g' /etc/ssh/sshd_config \
    && sed -i 's/#RSAAuthentication yes/RSAAuthentication yes/g' /etc/ssh/sshd_config \
    && sed -i 's/#PubkeyAuthentication yes/PubkeyAuthentication yes/g' /etc/ssh/sshd_config \
    && ssh-keygen -f /root/.ssh/id_rsa -t rsa -N '' \
    && chmod 600 /root/.ssh/config \
    && chmod 700 /root/.ssh \
    && cp /root/.ssh/id_rsa.pub /root/.ssh/authorized_keys

# set up workdir
ENV INSTALL_PREFIX=/opt
WORKDIR /tmp/mpi

# download and install mlnx 
RUN wget -q -O - http://www.mellanox.com/downloads/ofed/MLNX_OFED-4.6-1.0.1.1/MLNX_OFED_LINUX-4.6-1.0.1.1-rhel7.6-x86_64.tgz | tar -xzf - \
    && ./MLNX_OFED_LINUX-4.6-1.0.1.1-rhel7.6-x86_64/mlnxofedinstall --user-space-only --without-fw-update --all --force \
    && rm -rf MLNX_OFED_LINUX-4.6-1.0.1.1-rhel7.6-x86_64

# download and install HPC-X
ENV HPCX_VERSION="v2.4.1"
RUN cd ${INSTALL_PREFIX} && \
    wget -q -O - ftp://bgate.mellanox.com/uploads/hpcx-${HPCX_VERSION}-gcc-MLNX_OFED_LINUX-4.6-1.0.1.1-redhat7.6-x86_64.tbz | tar -xjf - \
    && HPCX_PATH=${INSTALL_PREFIX}/hpcx-${HPCX_VERSION}-gcc-MLNX_OFED_LINUX-4.6-1.0.1.1-redhat7.6-x86_64 \
    && HCOLL_PATH=${HPCX_PATH}/hcoll \
    && UCX_PATH=${HPCX_PATH}/ucx

# download and install OpenMPI
ENV OMPI_VERSION="4.0.1"
RUN wget -q -O - https://download.open-mpi.org/release/open-mpi/v4.0/openmpi-${OMPI_VERSION}.tar.gz | tar -xzf - \
    && cd openmpi-${OMPI_VERSION} \
    && ./configure --with-ucx=${UCX_PATH} --with-hcoll=${HCOLL_PATH} --enable-mpirun-prefix-by-default \
    && make -j 8 && make install \
    && cd .. \
    && rm -rf openmpi-${OMPI_VERSION}

# download and install mpiBench
RUN wget -q -O - https://codeload.github.com/LLNL/mpiBench/tar.gz/master | tar -xzf - \
    && mv ./mpiBench-master /mpiBench \
    && cd /mpiBench \
    && make

# set up sshd on port 23
EXPOSE 23
CMD ["/usr/sbin/sshd", "-D", "-p", "23"]
