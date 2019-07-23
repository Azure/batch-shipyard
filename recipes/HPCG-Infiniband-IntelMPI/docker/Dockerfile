# Dockerfile for HPCG and HPLinpack for use with Batch Shipyard on Azure Batch

FROM centos:7.6.1810
MAINTAINER Fred Park <https://github.com/Azure/batch-shipyard>

# set up base and ssh config
COPY ssh_config /root/.ssh/config
RUN yum install -y epel-release \
    && yum install -y \
        openssh-clients openssh-server net-tools numactl \
        libmlx4 libmlx5 librdmacm libibverbs dapl rdma \
    && yum clean all \
    && mkdir -p /var/run/sshd \
    && ssh-keygen -A \
    && sed -i 's/UsePAM yes/UsePAM no/g' /etc/ssh/sshd_config \
    && sed -i 's/#PermitRootLogin yes/PermitRootLogin yes/g' /etc/ssh/sshd_config \
    && sed -i 's/#RSAAuthentication yes/RSAAuthentication yes/g' /etc/ssh/sshd_config \
    && sed -i 's/#PubkeyAuthentication yes/PubkeyAuthentication yes/g' /etc/ssh/sshd_config \
    # NOTE that this is not best practice to distribute the SSH keypair in
    # the Docker image itself. It's recommended to map in the appropriate
    # key at runtime.
    && ssh-keygen -f /root/.ssh/id_rsa -t rsa -N '' \
    && chmod 600 /root/.ssh/config \
    && chmod 700 /root/.ssh \
    && cp /root/.ssh/id_rsa.pub /root/.ssh/authorized_keys

# copy in intel mpi and mkl redistributables
ENV INTEL_MPI_VER=2018.5.288 \
    INTEL_MKL_VER=2018.4.274
ADD l_mpi_${INTEL_MPI_VER}.tgz l_mkl_${INTEL_MKL_VER}.tgz /tmp/
RUN cd /tmp/l_mkl_${INTEL_MKL_VER} \
    && sed -i -e 's/^ACCEPT_EULA=.*/ACCEPT_EULA=accept/g' silent.cfg \
    && sed -i -e 's,^PSET_INSTALL_DIR=.*,PSET_INSTALL_DIR=/opt/intel2,g' silent.cfg \
    && sed -i -e 's,^ARCH_SELECTED=.*,ARCH_SELECTED=INTEL64,g' silent.cfg \
    && ./install.sh -s silent.cfg \
    && rm -rf /opt/intel2/compilers_and_libraries/linux/mkl/lib/ia32* \
    && cd .. \
    && rm -rf l_mkl_${INTEL_MKL_VER} \
    && cd l_mpi_${INTEL_MPI_VER} \
    && sed -i -e 's/^ACCEPT_EULA=.*/ACCEPT_EULA=accept/g' silent.cfg \
    && sed -i -e 's,^PSET_INSTALL_DIR=.*,PSET_INSTALL_DIR=/opt/intel2,g' silent.cfg \
    && sed -i -e 's,^COMPONENTS=.*,COMPONENTS=ALL,g' silent.cfg \
    && sed -i -e 's,^ARCH_SELECTED=.*,ARCH_SELECTED=INTEL64,g' silent.cfg \
    && ./install.sh -s silent.cfg \
    && cd .. \
    && rm -rf l_mpi_${INTEL_MPI_VER}

# copy findpq script
COPY findpq.py /opt/

# set up sshd on port 23
EXPOSE 23
CMD ["/usr/sbin/sshd", "-D", "-p", "23"]
