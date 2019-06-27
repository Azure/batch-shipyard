# Dockerfile for Linpack-Intel-Infiniband for use with Batch Shipyard on Azure Batch

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

# copy in intel c++, mpi and benchmark redistributables
ENV INTEL_CPP_VER=2018.5.274 \
    INTEL_MPI_VER=2018.5.288 \
    INTEL_MKL_VER=2018.3.011
ADD l_comp_lib_${INTEL_CPP_VER}_comp.cpp_redist.tgz l_mpi_${INTEL_MPI_VER}.tgz l_mklb_p_${INTEL_MKL_VER}.tgz /tmp/
RUN cd /tmp/l_comp_lib_${INTEL_CPP_VER}_comp.cpp_redist \
    && ./install.sh -i /opt/intel2 -e \
    && cd .. \
    && rm -rf l_comp_lib_${INTEL_CPP_VER}_comp.cpp_redist \
    && cd l_mpi_${INTEL_MPI_VER} \
    && sed -i -e 's/^ACCEPT_EULA=decline/ACCEPT_EULA=accept/g' silent.cfg \
    && sed -i -e 's,^PSET_INSTALL_DIR=.*,PSET_INSTALL_DIR=/opt/intel2,g' silent.cfg \
    && sed -i -e 's,^COMPONENTS=.*,COMPONENTS=ALL,g' silent.cfg \
    && sed -i -e 's,^ARCH_SELECTED=.*,ARCH_SELECTED=INTEL64,g' silent.cfg \
    && ./install.sh -s silent.cfg \
    && cd .. \
    && rm -rf l_mpi_${INTEL_MPI_VER} \
    && cp -r l_mklb_p_${INTEL_MKL_VER}/benchmarks_2018/linux/mkl /opt/intel2 \
    && rm -rf l_mklb_p_${INTEL_MKL_VER}

# set up sshd on port 23
EXPOSE 23
CMD ["/usr/sbin/sshd", "-D", "-p", "23"]
