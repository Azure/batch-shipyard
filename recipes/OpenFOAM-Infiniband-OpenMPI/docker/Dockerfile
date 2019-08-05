FROM centos:7.6.1810
 
# set up base
COPY ssh_config /root/.ssh/config
RUN yum install -y epel-release \
    && yum groupinstall -y "Development tools" \
    && yum install -y \
        ca-certificates wget openssh-server openssh-clients net-tools \
        numactl-devel gtk2 atk cairo tcsh libnl3 tcl libmnl tk cmake3 \
        libXt-devel qt-devel qt5-qtbase-devel qt5-qtx11extras-devel \
        qt5-qttools-devel
ENV PATH=$PATH:/usr/lib64/qt5/bin

# configure cmake alias
RUN alternatives --install /usr/local/bin/cmake cmake /usr/bin/cmake3 10 \
        --slave /usr/local/bin/ctest ctest /usr/bin/ctest3 \
        --slave /usr/local/bin/cpack cpack /usr/bin/cpack3 \
        --slave /usr/local/bin/ccmake ccmake /usr/bin/ccmake3 \
        --family cmake

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

# download and install mlnx 
RUN wget -q -O - http://www.mellanox.com/downloads/ofed/MLNX_OFED-4.6-1.0.1.1/MLNX_OFED_LINUX-4.6-1.0.1.1-rhel7.6-x86_64.tgz | tar -xzf - \
    && ./MLNX_OFED_LINUX-4.6-1.0.1.1-rhel7.6-x86_64/mlnxofedinstall --user-space-only --without-fw-update --all --force \
    && rm -rf MLNX_OFED_LINUX-4.6-1.0.1.1-rhel7.6-x86_64

# download and install HPC-X
ENV HPCX_VERSION="v2.4.1"
RUN cd /opt && \
    wget -q -O - ftp://bgate.mellanox.com/uploads/hpcx-${HPCX_VERSION}-gcc-MLNX_OFED_LINUX-4.6-1.0.1.1-redhat7.6-x86_64.tbz | tar -xjf - \
    && HPCX_PATH=/opt/hpcx-${HPCX_VERSION}-gcc-MLNX_OFED_LINUX-4.6-1.0.1.1-redhat7.6-x86_64 \
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

# download and isntall OpenFOAM
RUN mkdir -p /opt/OpenFOAM \
    && cd /opt/OpenFOAM \
    && wget -q -O - http://dl.openfoam.org/source/7 | tar xz \
    && wget -q -O - http://dl.openfoam.org/third-party/7 | tar xz \
    && mv OpenFOAM-7-version-7 OpenFOAM-7 \
    && mv ThirdParty-7-version-7 ThirdParty-7 \
    && sed -i 's/FOAM_INST_DIR=$HOME\/\$WM_PROJECT/FOAM_INST_DIR=\/opt\/\$WM_PROJECT/' /opt/OpenFOAM/OpenFOAM-7/etc/bashrc \
    && source /opt/OpenFOAM/OpenFOAM-7/etc/bashrc \
    # install OpenFOAM dependency - Scotch/PT-Scotch
    && /opt/OpenFOAM/ThirdParty-7/Allwmake \
    # install OpenFOAM dependency - ParaView
    && /opt/OpenFOAM/ThirdParty-7/makeParaView -config \
    && sed -i '/DOCUMENTATION_DIR "\${CMAKE_CURRENT_SOURCE_DIR}\/doc"/d' /opt/OpenFOAM/ThirdParty-7/ParaView-5.6.0/Plugins/MOOSETools/CMakeLists.txt \
    && sed -i '/DOCUMENTATION_DIR "\${CMAKE_CURRENT_SOURCE_DIR}\/doc"/d' /opt/OpenFOAM/ThirdParty-7/ParaView-5.6.0/Plugins/SurfaceLIC/CMakeLists.txt \
    && /opt/OpenFOAM/ThirdParty-7/makeParaView \
    # install OpenFOAM
    && wmRefresh \
    && /opt/OpenFOAM/OpenFOAM-7/Allwmake -j \
    # hack to make sure that sourcing /opt/OpenFOAM/OpenFOAM-7/etc/bashrc does not fail with `set -e` 
    && sed -i 's/unalias wmRefresh 2> \/dev\/null/unalias wmRefresh 2> \/dev\/null || true/' /opt/OpenFOAM/OpenFOAM-7/etc/config.sh/aliases \ 
    # remove intermediate build files
    && rm -rf \
        /opt/OpenFOAM/OpenFOAM-7/platforms/*/applications \
        /opt/OpenFOAM/OpenFOAM-7/platforms/*/src \
        /opt/OpenFOAM/ThirdParty-7/build \
        /opt/OpenFOAM/ThirdParty-7/gcc-* \
        /opt/OpenFOAM/ThirdParty-7/gmp-* \
        /opt/OpenFOAM/ThirdParty-7/mpfr-* \
        /opt/OpenFOAM/ThirdParty-7/binutils-* \
        /opt/OpenFOAM/ThirdParty-7/boost* \
        /opt/OpenFOAM/ThirdParty-7/ParaView-* \
        /opt/OpenFOAM/ThirdParty-7/qt-*

# set up sshd on port 23
EXPOSE 23
CMD ["/usr/sbin/sshd", "-D", "-p", "23"]
