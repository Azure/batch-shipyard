FROM centos:7

# set up base and ssh keys
COPY ssh_config /root/.ssh/config
RUN yum install -y \
        gcc gcc-c++ make ca-certificates wget openssh-server openssh-clients \
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

# download and install Intel MPI
RUN intel_mpi_version=l_mpi_2018.4.274 \
    && wget -q -O - http://registrationcenter-download.intel.com/akdlm/irc_nas/tec/13651/$intel_mpi_version.tgz | tar -xzf - \
    && wget https://raw.githubusercontent.com/szarkos/AzureBuildCentOS/master/config/azure/IntelMPI-v2018.x-silent.cfg \
    && mv -f ./IntelMPI-v2018.x-silent.cfg ./$intel_mpi_version/silent.cfg \
    && cd ./$intel_mpi_version \
    && ./install.sh --silent ./silent.cfg

# install
RUN export MANPATH=/usr/share/man \
    && source /opt/intel/compilers_and_libraries_2018/linux/mpi/bin64/mpivars.sh \
    && cd /mpiBench \
    && make

# set up sshd on port 23
EXPOSE 23
CMD ["/usr/sbin/sshd", "-D", "-p", "23"]
