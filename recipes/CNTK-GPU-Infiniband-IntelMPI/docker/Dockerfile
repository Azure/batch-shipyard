# Dockerfile for CNTK-GPU-Infiniband-IntelMPI for use with Batch Shipyard on Azure Batch

FROM nvidia/cuda:8.0-cudnn6-devel-ubuntu16.04
MAINTAINER Fred Park <https://github.com/Azure/batch-shipyard>

# install base system
COPY ssh_config /root/.ssh/config
RUN apt-get update && apt-get install -y --no-install-recommends \
        autotools-dev \
        build-essential \
        cmake \
        git \
        gfortran-multilib \
        libavcodec-dev \
        libavformat-dev \
        libjasper-dev \
        libjpeg-dev \
        libpng-dev \
        liblapacke-dev \
        libswscale-dev \
        libtiff-dev \
        pkg-config \
        wget \
        zlib1g-dev \
        # Protobuf
        ca-certificates \
        curl \
        unzip \
        # For Kaldi
        python-dev \
        automake \
        libtool \
        autoconf \
        subversion \
        # For Kaldi's dependencies
        libapr1 libaprutil1 libltdl-dev libltdl7 libserf-1-1 libsigsegv2 libsvn1 m4 \
        # For Java Bindings
        openjdk-9-jdk-headless \
        # For SWIG
        libpcre3-dev \
        libpcre++-dev && \
    apt-get install -y --no-install-recommends \
        # Infiniband/RDMA
        cpio \
        libmlx4-1 \
        libmlx5-1 \
        librdmacm1 \
        libibverbs1 \
        libmthca1 \
        libdapl2 \
        dapl2-utils \
        # batch-shipyard deps
        openssh-server \
        openssh-client && \
    rm -rf /var/lib/apt/lists/* && \
    # configure ssh server and keys
    mkdir /var/run/sshd && \
    ssh-keygen -A && \
    sed -i 's/PermitRootLogin without-password/PermitRootLogin yes/' /etc/ssh/sshd_config && \
    sed 's@session\s*required\s*pam_loginuid.so@session optional pam_loginuid.so@g' -i /etc/pam.d/sshd && \
    ssh-keygen -f /root/.ssh/id_rsa -t rsa -N '' && \
    chmod 600 /root/.ssh/config && \
    chmod 700 /root/.ssh && \
    cp /root/.ssh/id_rsa.pub /root/.ssh/authorized_keys

# build and install libzip, cub, boost, openblas, opencv, protobuf
RUN LIBZIP_VERSION=1.1.3 && \
    wget -q -O - http://nih.at/libzip/libzip-${LIBZIP_VERSION}.tar.gz | tar -xzf - && \
    cd libzip-${LIBZIP_VERSION} && \
    ./configure --prefix=/usr/local && \
    make -j"$(nproc)" install && \
    ldconfig /usr/local/lib && \
    cd .. && \
    rm -rf /libzip-${LIBZIP_VERSION} && \
    # boost
    BOOST_VERSION=1_60_0 && \
    BOOST_DOTTED_VERSION=$(echo $BOOST_VERSION | tr _ .) && \
    wget -q -O - https://sourceforge.net/projects/boost/files/boost/${BOOST_DOTTED_VERSION}/boost_${BOOST_VERSION}.tar.gz/download | tar -xzf - && \
    cd boost_${BOOST_VERSION} && \
    ./bootstrap.sh --prefix=/usr/local --with-libraries=filesystem,system,test  && \
    ./b2 -d0 -j"$(nproc)" install && \
    ldconfig /usr/local/lib && \
    cd .. && \
    rm -rf /boost_${BOOST_VERSION} && \
    # cub
    wget -q -O - https://github.com/NVlabs/cub/archive/1.4.1.tar.gz | tar -C /usr/local -xzf - && \
    # openblas
    OPENBLAS_VERSION=0.2.19 && \
    wget -q -O - https://github.com/xianyi/OpenBLAS/archive/v${OPENBLAS_VERSION}.tar.gz | tar -xzf - && \
    cd OpenBLAS-${OPENBLAS_VERSION} && \
    make -j"$(nproc)" USE_OPENMP=1 | tee make.log && \
    grep -qF 'OpenBLAS build complete. (BLAS CBLAS LAPACK LAPACKE)' make.log && \
    grep -qF 'Use OpenMP in the multithreading.' make.log && \
    make PREFIX=/usr/local/openblas install && \
    ldconfig /usr/local/openblas && \
    cd .. && \
    rm -rf /OpenBLAS-${OPENBLAS_VERSION} && \
    # opencv
    OPENCV_VERSION=3.1.0 && \
    wget -q -O - https://github.com/opencv/opencv/archive/${OPENCV_VERSION}.tar.gz | tar -xzf - && \
    cd opencv-${OPENCV_VERSION} && \
    cmake -DWITH_CUDA=OFF -DCMAKE_BUILD_TYPE=RELEASE -DCMAKE_INSTALL_PREFIX=/usr/local/opencv-${OPENCV_VERSION} . && \
    make -j"$(nproc)" install && \
    ldconfig /usr/local/lib && \
    cd .. && \
    rm -rf /opencv-${OPENCV_VERSION} && \
    # protocol buffers
    PROTOBUF_VERSION=3.1.0 \
    PROTOBUF_STRING=protobuf-$PROTOBUF_VERSION && \
    wget -O - --no-verbose https://github.com/google/protobuf/archive/v${PROTOBUF_VERSION}.tar.gz | tar -xzf - && \
    cd $PROTOBUF_STRING && \
    ./autogen.sh && \
    ./configure CFLAGS=-fPIC CXXFLAGS=-fPIC --disable-shared --prefix=/usr/local/$PROTOBUF_STRING && \
    make -j $(nproc) install && \
    cd .. && \
    rm -rf $PROTOBUF_STRING

# set env vars
ENV KALDI_VERSION=c024e8aa
ENV NCCL_VERSION=1.3.0-1
ENV PATH=/root/anaconda3/envs/cntk-py36/bin:/usr/local/bin:/cntk/build-mkl/gpu/release/bin:${PATH} \
    KALDI_PATH=/usr/local/kaldi-$KALDI_VERSION \
    BLAS=/usr/local/openblas/lib/libopenblas.so \
    LAPACK=/usr/local/openblas/lib/libopenblas.so \
    NCCL_PATH=/usr/local/nccl-${NCCL_VERSION} \
    MKL_PATH=/usr/local/CNTKCustomMKL \
    PYTHONPATH=/cntk/bindings/python:$PYTHONPATH \
    LD_LIBRARY_PATH=/usr/local/openblas/lib:/cntk/bindings/python/cntk/libs:$LD_LIBRARY_PATH

# install cntk custom mkl, kaldi, swig and anaconda
RUN CNTK_CUSTOM_MKL_VERSION=3 && \
    mkdir ${MKL_PATH} && \
    wget --no-verbose -O - https://www.cntk.ai/mkl/CNTKCustomMKL-Linux-$CNTK_CUSTOM_MKL_VERSION.tgz | \
    tar -xzf - -C ${MKL_PATH} && \
    # kaldi
    mkdir $KALDI_PATH && \
    wget --no-verbose -O - https://github.com/kaldi-asr/kaldi/archive/$KALDI_VERSION.tar.gz | tar -xzf - --strip-components=1 -C $KALDI_PATH && \
    cd $KALDI_PATH/tools && \
    perl -pi -e 's/^# (OPENFST_VERSION = 1.4.1)$/\1/' Makefile && \
    #/bin/bash extras/check_dependencies.sh && \
    #make -j $(nproc) all && \
    make -j $(nproc) sph2pipe atlas sclite openfst && \
    cd ../src && \
    ./configure --openblas-root=/usr/local/openblas --shared && \
    make -j $(nproc) depend && \
    make -j $(nproc) all && \
    find $KALDI_PATH -name '*.o' -print0 | xargs -0 rm && \
    for dir in $KALDI_PATH/src/*bin; do make -C $dir clean; done && \
    # SWIG
    SWIG_VERSION=3.0.10 && \
    cd /root && \
    wget -q http://prdownloads.sourceforge.net/swig/swig-${SWIG_VERSION}.tar.gz -O - | tar xvfz - && \
    cd swig-${SWIG_VERSION} && \
    ./configure --without-alllang && \
    make -j$(nproc) && \
    make install && \
    cd .. && \
    rm -rf swig-${SWIG_VERSION} && \
    # NCCL
    git clone --depth=1 -b v${NCCL_VERSION} https://github.com/NVIDIA/nccl.git && \
    cd nccl && \
    make CUDA_HOME=/usr/local/cuda PREFIX=$NCCL_PATH install && \
    rm -rf /nccl && \
    # Anaconda
    wget -q https://repo.continuum.io/archive/Anaconda3-4.4.0-Linux-x86_64.sh && \
    bash Anaconda3-4.4.0-Linux-x86_64.sh -b && \
    rm -f Anaconda3-4.4.0-Linux-x86_64.sh && \
    # set paths for CNTK
    mkdir -p /usr/local/cudnn/cuda/include && \
    ln -s /usr/include/cudnn.h /usr/local/cudnn/cuda/include/cudnn.h && \
    mkdir -p /usr/local/cudnn/cuda/lib64 && \
    ln -s /etc/alternatives/libcudnn_so /usr/local/cudnn/cuda/lib64/libcudnn.so && \
    ln -s /usr/local/cuda/lib64/stubs/libnvidia-ml.so /usr/local/cuda/lib64/stubs/libnvidia-ml.so.1 && \
    # update ldconfig
    ldconfig /usr/local/lib

# set cntk dir
WORKDIR /cntk

# add intel mpi library and build cntk
ENV MANPATH=/usr/share/man:/usr/local/man \
    COMPILERVARS_ARCHITECTURE=intel64 \
    COMPILERVARS_PLATFORM=linux \
    INTEL_MPI_PATH=/opt/intel/compilers_and_libraries/linux/mpi
ADD l_mpi_2017.2.174.tgz /tmp
COPY USE_SERVER.lic /tmp/l_mpi_2017.2.174/
RUN sed -i -e 's/^ACCEPT_EULA=decline/ACCEPT_EULA=accept/g' /tmp/l_mpi_2017.2.174/silent.cfg && \
    sed -i -e 's|^#ACTIVATION_LICENSE_FILE=|ACTIVATION_LICENSE_FILE=/tmp/l_mpi_2017.2.174/USE_SERVER.lic|g' /tmp/l_mpi_2017.2.174/silent.cfg && \
    sed -i -e 's/^ACTIVATION_TYPE=exist_lic/ACTIVATION_TYPE=license_server/g' /tmp/l_mpi_2017.2.174/silent.cfg && \
    cd /tmp/l_mpi_2017.2.174 && \
    ./install.sh -s silent.cfg && \
    cd .. && \
    rm -rf l_mpi_2017.2.174 && \
    # cntk makefiles use non-standard mpic++, symlink to mpicxx
    ln -s ${INTEL_MPI_PATH}/${COMPILERVARS_ARCHITECTURE}/bin/mpicxx ${INTEL_MPI_PATH}/${COMPILERVARS_ARCHITECTURE}/bin/mpic++ && \
    # build cntk
    CNTK_VERSION=v2.1 && \
    cd /cntk && \
    git clone --depth=1 --recursive -b ${CNTK_VERSION} --single-branch https://github.com/Microsoft/CNTK.git . && \
    # set Anaconda environment
    /root/anaconda3/bin/conda env create -p /root/anaconda3/envs/cntk-py36/ \
        --file /cntk/Scripts/install/linux/conda-linux-cntk-py36-environment.yml && \
    # source intel mpi vars
    . /opt/intel/bin/compilervars.sh && \
    . /opt/intel/compilers_and_libraries/linux/mpi/bin64/mpivars.sh && \
    # build gpu-mkl only
    CONFIGURE_OPTS="\
      --1bitsgd=yes \
      --with-mpi=${INTEL_MPI_PATH}/${COMPILERVARS_ARCHITECTURE} \
      --with-cuda=/usr/local/cuda \
      --with-gdk-include=/usr/local/cuda/include \
      --with-gdk-nvml-lib=/usr/local/cuda/lib64/stubs \
      --with-kaldi=${KALDI_PATH} \
      --with-py36-path=/root/anaconda3/envs/cntk-py36 \
      --with-cudnn=/usr/local/cudnn \
      --with-nccl=${NCCL_PATH}" && \
    mkdir -p build-mkl/gpu/release && \
    cd build-mkl/gpu/release && \
    ../../../configure $CONFIGURE_OPTS --with-mkl=${MKL_PATH} && \
    make -j"$(nproc)" all && \
    # clean up
    rm -rf /cntk/build-mkl/gpu/release/.build && \
    rm -rf /cntk/.git && \
    /root/anaconda3/bin/conda clean --all --yes && \
    # create activate script
    echo "source /root/anaconda3/bin/activate /root/anaconda3/envs/cntk-py36" > /cntk/activate-cntk && \
    # add cntk activate to root bashrc
    echo "source /cntk/activate-cntk" >> /root/.bashrc && \
    # add LD_LIBRARY_PATH to root bashrc
    echo LD_LIBRARY_PATH=${LD_LIBRARY_PATH}:'$LD_LIBRARY_PATH' >> /root/.bashrc && \
    # remove intel components (runtime will be mounted from the host)
    rm -rf /opt/intel

# set sshd command
EXPOSE 23
CMD ["/usr/sbin/sshd", "-D", "-p", "23"]
