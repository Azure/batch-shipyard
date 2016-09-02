# Dockerfile for NAMD-Infiniband for use with Batch Shipyard on Azure Batch

FROM centos:7.1.1503

# set up base
COPY ssh_config /root/.ssh/
RUN yum swap -y fakesystemd systemd \
    && yum install -y openssh-clients openssh-server net-tools libmlx4 librdmacm libibverbs dapl rdma \
    && yum clean all \
    && mkdir -p /var/run/sshd \
    && ssh-keygen -A \
    && sed -i 's/UsePAM yes/UsePAM no/g' /etc/ssh/sshd_config \
    && sed -i 's/#PermitRootLogin yes/PermitRootLogin yes/g' /etc/ssh/sshd_config \
    && sed -i 's/#RSAAuthentication yes/RSAAuthentication yes/g' /etc/ssh/sshd_config \
    && sed -i 's/#PubkeyAuthentication yes/PubkeyAuthentication yes/g' /etc/ssh/sshd_config \
    && ssh-keygen -f /root/.ssh/id_rsa -t rsa -N '' \
    && chmod 600 /root/.ssh/ssh_config \
    && chmod 700 /root/.ssh \
    && cp /root/.ssh/id_rsa.pub /root/.ssh/authorized_keys \
    && mv /root/.ssh/ssh_config /root/.ssh/config

# add software
ADD NAMD_2.10_Linux-x86_64-MPI-icc-mkl.tar.gz /sw
ADD apoa1.tar.gz stmv.tar.gz /sw/namd/
COPY run_namd.sh /sw/

# export environment
ENV NAMD_DIR=/sw/namd NAMD_SCRIPT=/sw/run_namd.sh
# intel mpi infiniband vars will be automatically set by Batch Shipyard
#ENV I_MPI_FABRICS=shm:dapl I_MPI_DAPL_PROVIDER=ofa-v2-ib0 I_MPI_DYNAMIC_CONNECTION=0 MANPATH=/usr/share/man:/usr/local/man

# set up sshd on port 23
EXPOSE 23
CMD ["/usr/sbin/sshd", "-D", "-p", "23"]
