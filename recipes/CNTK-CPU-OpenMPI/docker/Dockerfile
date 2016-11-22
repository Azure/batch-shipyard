# Dockerfile for CNTK-CPU-OpenMPI for use with Batch Shipyard on Azure Batch

FROM ubuntu:14.04
MAINTAINER Fred Park <https://github.com/Azure/batch-shipyard>

# install base system
COPY ssh_config /root/.ssh/config
RUN apt-get update && apt-get install -y --no-install-recommends \
        autotools-dev \
        build-essential \
        cmake \
        git \
        g++-multilib \
        gcc-multilib \
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
        autoconf \
        automake \
        libtool \
        python-dev \
        subversion \
        # For Kaldi's dependencies
        libapr1 libaprutil1 libltdl-dev libltdl7 libserf-1-1 libsigsegv2 libsvn1 m4 \
        # For SWIG
        libpcre++-dev \
        # batch-shipyard deps
        openssh-server \
        openssh-client && \
    rm -rf /var/lib/apt/lists/* && \
    curl -fSsL https://bootstrap.pypa.io/get-pip.py | python && \
    # configure ssh server and keys
    mkdir /var/run/sshd && \
    ssh-keygen -A && \
    sed -i 's/PermitRootLogin without-password/PermitRootLogin yes/' /etc/ssh/sshd_config && \
    sed 's@session\s*required\s*pam_loginuid.so@session optional pam_loginuid.so@g' -i /etc/pam.d/sshd && \
    ssh-keygen -f /root/.ssh/id_rsa -t rsa -N '' && \
    chmod 600 /root/.ssh/config && \
    chmod 700 /root/.ssh && \
    cp /root/.ssh/id_rsa.pub /root/.ssh/authorized_keys

# build and install libzip, openmpi, boost, opencv, openblas, protobuf
RUN LIBZIP_VERSION=1.1.3 && \
    wget -q -O - http://nih.at/libzip/libzip-${LIBZIP_VERSION}.tar.gz | tar -xzf - && \
    cd libzip-${LIBZIP_VERSION} && \
    ./configure --prefix=/usr/local && \
    make -j"$(nproc)" install && \
    ldconfig /usr/local/lib && \
    cd .. && \
    rm -rf /libzip-${LIBZIP_VERSION} && \
    # openmpi
    OPENMPI_VERSION=1.10.4 && \
    wget -q -O - https://www.open-mpi.org/software/ompi/v1.10/downloads/openmpi-${OPENMPI_VERSION}.tar.gz | tar -xzf - && \
    cd openmpi-${OPENMPI_VERSION} && \
    ./configure --prefix=/usr/local && \
    make -j"$(nproc)" install && \
    ldconfig /usr/local/lib && \
    cd .. && \
    rm -rf /openmpi-${OPENMPI_VERSION} && \
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
    cmake -DCMAKE_BUILD_TYPE=RELEASE -DCMAKE_INSTALL_PREFIX=/usr/local/opencv-${OPENCV_VERSION} . && \
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
ENV PATH=/root/anaconda3/envs/cntk-py34/bin:/usr/local/bin:/usr/local/mpi/bin:/cntk/build/cpu-mkl/release/bin:${PATH} \
    KALDI_PATH=/usr/local/kaldi-$KALDI_VERSION \
    BLAS=/usr/local/openblas/lib/libopenblas.so \
    LAPACK=/usr/local/openblas/lib/libopenblas.so \
    PYTHONPATH=/cntk/bindings/python:$PYTHONPATH \
    LD_LIBRARY_PATH=/usr/local/openblas/lib:/cntk/bindings/python/cntk/libs:$LD_LIBRARY_PATH

# install cntk custom mkl, kaldi, swig and anaconda
RUN mkdir /usr/local/CNTKCustomMKL && \
    wget --no-verbose -O - https://www.cntk.ai/mkl/CNTKCustomMKL-Linux-2.tgz | \
    tar -xzf - -C /usr/local/CNTKCustomMKL && \
    # kaldi
    mkdir $KALDI_PATH && \
    wget --no-verbose -O - https://github.com/kaldi-asr/kaldi/archive/$KALDI_VERSION.tar.gz | tar -xzf - --strip-components=1 -C $KALDI_PATH && \
    cd $KALDI_PATH/tools && \
    perl -pi -e 's/^# (OPENFST_VERSION = 1.4.1)$/\1/' Makefile && \
    /bin/bash extras/check_dependencies.sh && \
    make -j $(nproc) all && \
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
    ./configure --without-java --without-perl5 && \
    make -j$(nproc) && \
    make install && \
    cd .. && \
    rm -rf swig-${SWIG_VERSION} && \
    # Anaconda
    wget -q https://repo.continuum.io/archive/Anaconda3-4.2.0-Linux-x86_64.sh && \
    bash Anaconda3-4.2.0-Linux-x86_64.sh -b && \
    rm -f Anaconda3-4.2.0-Linux-x86_64.sh && \
    # update ldconfig
    ldconfig /usr/local/lib

# build cntk
WORKDIR /cntk
RUN CNTK_VERSION=v2.0.beta4.0 && \
    git clone --depth=1 --recursive -b ${CNTK_VERSION} https://github.com/Microsoft/CNTK.git . && \
    # set Anaconda environment
    /root/anaconda3/bin/conda env create -p /root/anaconda3/envs/cntk-py34/ \
		--file /cntk/Scripts/install/linux/conda-linux-cntk-py34-environment.yml && \
    # build cpu-mkl only
    CONFIGURE_OPTS="\
      --1bitsgd=yes \
      --with-kaldi=${KALDI_PATH} \
      --with-py34-path=/root/anaconda3/envs/cntk-py34" && \
    mkdir -p build-mkl/cpu/release && \
    cd build-mkl/cpu/release && \
    ../../../configure $CONFIGURE_OPTS --with-mkl=/usr/local/CNTKCustomMKL && \
    make -j"$(nproc)" all && \
    rm -rf /cntk/build-mkl/cpu/release/.build && \
    # add LD_LIBRARY_PATH to root
    echo LD_LIBRARY_PATH=${LD_LIBRARY_PATH}:'$LD_LIBRARY_PATH' >> /root/.bashrc

# set ssh command
EXPOSE 23
CMD ["/usr/sbin/sshd", "-D", "-p", "23"]
