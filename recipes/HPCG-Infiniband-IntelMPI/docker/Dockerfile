# Dockerfile for Linpack-Intel-Infiniband for use with Batch Shipyard on Azure Batch

FROM centos:7.1.1503
MAINTAINER Fred Park <https://github.com/Azure/batch-shipyard>

# set up base and ssh keys
COPY ssh_config /root/.ssh/config
RUN yum swap -y fakesystemd systemd \
    && yum install -y epel-release \
    && yum install -y \
        openssh-clients openssh-server net-tools numactl \
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

# copy in intel c++, mpi and benchmark redistributables
ADD l_comp_lib_2017.0.098_comp.cpp_redist.tgz l_mpi-rt_p_5.1.3.223.tgz l_mklb_p_2017.0.010.tgz /tmp/
RUN cd /tmp/l_comp_lib_2017.0.098_comp.cpp_redist \
    && ./install.sh -i /opt/intel2 -e \
    && cd .. \
    && rm -rf l_comp_lib_2017.0.098_comp.cpp_redist \
    && cd l_mpi-rt_p_5.1.3.223 \
    && sed -i -e 's/^ACCEPT_EULA=decline/ACCEPT_EULA=accept/g' silent.cfg \
    && sed -i -e 's,^PSET_INSTALL_DIR=.*,PSET_INSTALL_DIR=/opt/intel2,g' silent.cfg \
    && ./install.sh -s silent.cfg \
    && cd .. \
    && rm -rf l_mpi-rt_p_5.1.3.223 \
    && cp -r l_mklb_p_2017.0.010/benchmarks_2017/linux/mkl /opt/intel2 \
    && rm -rf l_mklb_p_2017.0.010

# copy in scripts
COPY findpq.py run_hplinpack.sh run_hpcg.sh /sw/

# set up sshd on port 23
EXPOSE 23
CMD ["/usr/sbin/sshd", "-D", "-p", "23"]
