#Dockerfile for HPMLA (Microsoft High Performance ML Algorithms)

FROM ubuntu:16.04
MAINTAINER Saeed Maleki Todd Mytkowicz Madan Musuvathi Dany rouhana https://github.com/saeedmaleki/Distributed-Linear-Learner
ENV DEBIAN_FRONTEND=noninteractive

#install base system
RUN apt-get update && apt-get install -y --no-install-recommends \
        openssh-client \
        openssh-server \
		libopenblas-dev \
		libatlas-base-dev \
		liblapacke-dev \
		openmpi-bin \
		openmpi-common \
		libopenmpi-dev && \
		apt-get clean && \
		rm -rf /var/lib/apt/lists/*

# configure ssh server and keys
RUN mkdir -p /root/.ssh && \
    echo "Host *\n\tPort 23\n\tStrictHostKeyChecking no\n\tUserKnownHostsFile /dev/null" > /root/.ssh/config && \
    mkdir /var/run/sshd && \
    ssh-keygen -A && \
    sed -i 's/PermitRootLogin without-password/PermitRootLogin yes/' /etc/ssh/sshd_config && \
    sed 's@session\s*required\s*pam_loginuid.so@session optional pam_loginuid.so@g' -i /etc/pam.d/sshd && \
    ssh-keygen -f /root/.ssh/id_rsa -t rsa -N '' && \
    chmod 600 /root/.ssh/config && \
    chmod 700 /root/.ssh && \
    cp /root/.ssh/id_rsa.pub /root/.ssh/authorized_keys

# set parasail dir
WORKDIR /parasail

# to create your own image, first download the supersgd from the link supplied in the read me file,
# and the put it in the same dir as this file.
COPY supersgd /parasail
COPY run_parasail.sh /parasail

# remove romio314 bits
RUN rm -rf /usr/lib/openmpi/lib/openmpi/mca_io_romio.so

#make sshd listen on 23 and run by default
EXPOSE 23
CMD ["/usr/sbin/sshd", "-D", "-p", "23"]
