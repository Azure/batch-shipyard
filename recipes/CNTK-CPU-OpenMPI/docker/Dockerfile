# Dockerfile for CNTK-CPU-OpenMPI for use with Batch Shipyard on Azure Batch

FROM microsoft/cntk:2.1-cpu-python3.5
MAINTAINER Fred Park <https://github.com/Azure/batch-shipyard>

COPY ssh_config /root/.ssh/config
RUN apt-get update && apt-get install -y --no-install-recommends \
        openssh-client \
        openssh-server \
        iproute2 \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* \
    # configure ssh server and keys
    && mkdir /var/run/sshd \
    && ssh-keygen -A \
    && sed -i 's/PermitRootLogin without-password/PermitRootLogin yes/' /etc/ssh/sshd_config \
    && sed 's@session\s*required\s*pam_loginuid.so@session optional pam_loginuid.so@g' -i /etc/pam.d/sshd \
    && ssh-keygen -f /root/.ssh/id_rsa -t rsa -N '' \
    && chmod 600 /root/.ssh/config \
    && chmod 700 /root/.ssh \
    && cp /root/.ssh/id_rsa.pub /root/.ssh/authorized_keys

# make sshd listen on 23 and run by default
EXPOSE 23
CMD ["/usr/sbin/sshd", "-D", "-p", "23"]
