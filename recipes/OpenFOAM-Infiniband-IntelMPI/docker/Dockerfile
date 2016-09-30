# Dockerfile for OpenFOAM-Infiniband-IntelMPI for use with Batch Shipyard on Azure Batch

FROM centos:7.1.1503
MAINTAINER Fred Park <https://github.com/Azure/batch-shipyard>

# set up base and ssh keys
COPY ssh_config /root/.ssh/config
RUN yum swap -y fakesystemd systemd \
    && yum install -y epel-release \
    && yum install -y \
        openssh-clients openssh-server net-tools gnuplot mpfr-devel \
        qt-devel qt-assistant qt-x11 qtwebkit-devel libGLU-devel boost-devel \
        libmlx4 librdmacm libibverbs dapl rdma \
    && yum clean all \
    && mkdir -p /var/run/sshd \
    && ssh-keygen -A \
    && sed -i 's/UsePAM yes/UsePAM no/g' /etc/ssh/sshd_config \
    && sed -i 's/#PermitRootLogin yes/PermitRootLogin yes/g' /etc/ssh/sshd_config \
    && sed -i 's/#RSAAuthentication yes/RSAAuthentication yes/g' /etc/ssh/sshd_config \
    && sed -i 's/#PubkeyAuthentication yes/PubkeyAuthentication yes/g' /etc/ssh/sshd_config \
    && ssh-keygen -f /root/.ssh/id_rsa -t rsa -N '' \
    && chmod 600 /root/.ssh/config \
    && chmod 700 /root/.ssh \
    && cp /root/.ssh/id_rsa.pub /root/.ssh/authorized_keys

# add intel redistributables
ADD l_comp_lib_2016.4.258_comp.cpp_redist.tgz l_comp_lib_2016.4.258_comp.for_redist.tgz /tmp/
RUN cd /tmp/l_comp_lib_2016.4.258_comp.cpp_redist \
    && ./install.sh -i /opt/intel2 -e \
    && cd /tmp/l_comp_lib_2016.4.258_comp.for_redist \
    && ./install.sh -i /opt/intel2 -e \
    && rm -rf /tmp/l_comp_lib_2016.4.258_comp.cpp_redist /tmp/l_comp_lib_2016.4.258_comp.for_redist
ENV INTELCOMPILERVARS=/opt/intel2/bin/compilervars.sh

# add openfoam with env vars
ADD openfoam-4.0-icc-intelmpi.tar.gz /opt/OpenFOAM
ENV OPENFOAM_VER=4.0 FOAM_INST_DIR=/opt/OpenFOAM PATH=${PATH}:/usr/lib64/qt4/bin
ENV OPENFOAM_DIR=${FOAM_INST_DIR}/OpenFOAM-${OPENFOAM_VER}

# copy sample run script
COPY run_sample.sh ${FOAM_INST_DIR}

# set up sshd on port 23
EXPOSE 23
CMD ["/usr/sbin/sshd", "-D", "-p", "23"]
