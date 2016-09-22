# Dockerfile for OpenFOAM-TCP-OpenMPI for use with Batch Shipyard on Azure Batch

FROM centos:7.1.1503

# set up base and ssh keys
COPY ssh_config /root/.ssh/config
RUN yum update -y \
    && yum swap -y fakesystemd systemd \
    && yum install -y epel-release \
    && yum groupinstall -y 'Development Tools' \
    && yum install -y \
        openssh-clients openssh-server net-tools cmake gnuplot mpfr-devel \
        openmpi-devel qt qt-devel qt-assistant qt-x11 qtwebkit-devel \
        libGLU-devel \
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

# set env vars for openfoam
ENV OPENFOAM_VER=v1606+ FOAM_INST_DIR=/opt/OpenFOAM PATH=${PATH}:/usr/lib64/qt4/bin
ENV OPENFOAM_DIR=${FOAM_INST_DIR}/OpenFOAM-${OPENFOAM_VER}

# download openfoam and untar
RUN mkdir -p ${FOAM_INST_DIR} \
    && curl -L --retry 10 --retry-max-time 0 https://sourceforge.net/projects/openfoamplus/files/${OPENFOAM_VER}/OpenFOAM-${OPENFOAM_VER}.tgz | tar -zxvpf - -C ${FOAM_INST_DIR} \
    && curl -L --retry 10 --retry-max-time 0 https://sourceforge.net/projects/openfoamplus/files/${OPENFOAM_VER}/ThirdParty-${OPENFOAM_VER}.tgz | tar -zxvpf - -C ${FOAM_INST_DIR}

# install paraview and openfoam
RUN source /etc/profile.d/modules.sh \
    && module add mpi/openmpi-x86_64 \
    && source ${OPENFOAM_DIR}/etc/bashrc \
    && export WM_NCOMPROCS=`nproc` \
    && cd ${FOAM_INST_DIR}/ThirdParty-${OPENFOAM_VER} \
    && ./makeParaView \
    && cd ${OPENFOAM_DIR} \
    && USER=root \
    && bin/foamSystemCheck \
    && ./Allwmake \
    && bin/foamInstallationTest

# copy sample run script
COPY run_sample.sh ${FOAM_INST_DIR}

# set up sshd on port 23
EXPOSE 23
CMD ["/usr/sbin/sshd", "-D", "-p", "23"]
