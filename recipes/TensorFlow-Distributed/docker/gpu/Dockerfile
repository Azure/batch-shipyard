# Dockerfile for TensorFlow-GPU-Distributed for use with Batch Shipyard on Azure Batch

FROM alfpark/tensorflow:1.0.0-gpu-base
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

COPY launcher.sh mnist_replica.py /sw/

EXPOSE 23
CMD ["/usr/sbin/sshd", "-D", "-p", "23"]
