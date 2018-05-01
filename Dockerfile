#Dockerfile for MDL (Microsoft Distributed Learners)

FROM ubuntu:16.04
MAINTAINER Saeed Maleki Todd Mytkowicz Madan Musuvathi Dany rouhana <https://github.com/Azure/batch-shipyard>
ENV DEBIAN_FRONTEND=noninteractive

#install base system
RUN apt-get update && apt-get install -y --no-install-recommends \
		build-essential \
		apt-utils \
		wget \
        openssh-client \
        openssh-server \
        iproute2 \
		git \
		gcc \
		make \
		emacs \
		iotop \
		gfortran \
		libopenblas-dev \
		libatlas-base-dev \
		liblapacke-dev \
		cpio \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* 
	
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

#set environment variables
ENV COMPILERVARS_ARCHITECTURE=intel64 \
    INTEL_MPI_PATH=/opt/intel/compilers_and_libraries/linux/mpi


RUN cd /tmp && \
    # download and install intel mkl library
    wget -q http://registrationcenter-download.intel.com/akdlm/irc_nas/tec/12414/l_mpi_2018.1.163.tgz && \
    tar -xzf l_mpi_2018.1.163.tgz && cd l_mpi_2018.1.163 && \
    sed -i -e 's/^ACCEPT_EULA=decline/ACCEPT_EULA=accept/g' silent.cfg && \
    ./install.sh -s silent.cfg && \
    # download and install intel mkl library
    cd .. && \
    wget -q http://registrationcenter-download.intel.com/akdlm/irc_nas/tec/12414/l_mkl_2018.1.163.tgz && \
    tar -xzf l_mkl_2018.1.163.tgz && cd l_mkl_2018.1.163 && \
    sed -i 's/ACCEPT_EULA=decline/ACCEPT_EULA=accept/g' silent.cfg && \
    ./install.sh -s silent.cfg && \
    cd .. && rm -rf *

# Create training folders and copy data
RUN mkdir /parasail/rcv1-00000
RUN mkdir /parasail/rcv1-test-00000
COPY rcv1-00000 /parasail/rcv1-00000
COPY rcv1-test-00000 /parasail/rcv1-test-00000

#Copy MADL binary and mpirun helper script to working directory
COPY supersgd /parasail
COPY run_parasail.sh /parasail

#make sshd listen on 23 and run by default
EXPOSE 23
CMD ["/usr/sbin/sshd", "-D", "-p", "23"]