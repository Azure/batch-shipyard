FROM ubuntu:18.04

# set up base and ssh keys
COPY ssh_config /root/.ssh/config
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential ca-certificates wget openssh-client openssh-server \
        mpich libmpich-dev \
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

# download and untar
RUN wget -q -O - https://codeload.github.com/LLNL/mpiBench/tar.gz/master | tar -xzf - \
    && mv ./mpiBench-master /mpiBench
    
# install
RUN cd /mpiBench \
    && make

# clean
RUN rm -rf /var/lib/apt/lists/* \
    && apt-get remove -y libmpich-dev \
	&& apt-get clean

# set up sshd on port 23
EXPOSE 23
CMD ["/usr/sbin/sshd", "-D", "-p", "23"]
