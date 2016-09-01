# Dockerfile for NAMD-TCP

FROM centos:7.1.1503

# set up base and ssh keys
COPY ssh_config /root/.ssh/
RUN yum swap -y fakesystemd systemd \
    && yum install -y openssh-clients openssh-server net-tools curl tar \
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

# export environment
ENV NAMD_VER=NAMD_2.10_Linux-x86_64-TCP
ENV NAMD_DIR=/sw/$NAMD_VER NAMD_SCRIPT=/sw/run_namd.sh

# add software
ADD ${NAMD_VER}.tar.gz /sw
ADD apoa1.tar.gz stmv.tar.gz /sw/${NAMD_VER}/
COPY run_namd.sh /sw/

# set up sshd on port 23
EXPOSE 23
CMD ["/usr/sbin/sshd", "-D", "-p", "23"]
