# Dockerfile for CNTK-CPU-OpenMPI for use with Batch Shipyard on Azure Batch

FROM ubuntu:14.04

# install base system
COPY ssh_config /root/.ssh/
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
        python-dev \
        python-numpy \
        python-pip \
        python-yaml \
        wget \
        zlib1g-dev \
        openssh-server \
        openssh-client \
        #For Kaldi
        automake \
        libtool \
        autoconf \
        subversion \
        #For Kaldi's dependencies
        libapr1 libaprutil1 libltdl-dev libltdl7 libserf-1-1 libsigsegv2 libsvn1 m4 && \
    rm -rf /var/lib/apt/lists/* && \
    pip install pytest sphinx-rtd-theme Pillow && \
    # configure ssh server and keys
    mkdir /var/run/sshd && \
    ssh-keygen -A && \
    sed -i 's/PermitRootLogin without-password/PermitRootLogin yes/' /etc/ssh/sshd_config && \
    sed 's@session\s*required\s*pam_loginuid.so@session optional pam_loginuid.so@g' -i /etc/pam.d/sshd && \
    ssh-keygen -f /root/.ssh/id_rsa -t rsa -N '' && \
    chmod 600 /root/.ssh/ssh_config && \
    chmod 700 /root/.ssh && \
    cp /root/.ssh/id_rsa.pub /root/.ssh/authorized_keys && \
    mv /root/.ssh/ssh_config /root/.ssh/config

# install libzip, openmpi, boost, opencv, and openblas
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
    # opencv
    OPENCV_VERSION=3.1.0 && \
    wget -q -O - https://github.com/Itseez/opencv/archive/${OPENCV_VERSION}.tar.gz | tar -xzf - && \
    cd opencv-${OPENCV_VERSION} && \
    cmake -DCMAKE_BUILD_TYPE=RELEASE -DCMAKE_INSTALL_PREFIX=/usr/local/opencv-${OPENCV_VERSION} . && \
    make -j"$(nproc)" install && \
    ldconfig /usr/local/lib && \
    cd .. && \
    rm -rf /opencv-${OPENCV_VERSION} && \
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
    rm -rf /OpenBLAS-${OPENBLAS_VERSION}

# set env vars
ENV KALDI_VERSION=c024e8aa
ENV PATH=${PATH}:/usr/local/bin:/cntk/build/cpu/release/bin \
    KALDI_PATH=/usr/local/kaldi-$KALDI_VERSION \
    BLAS=/usr/local/openblas/lib/libopenblas.so \
    LAPACK=/usr/local/openblas/lib/libopenblas.so \
    LD_LIBRARY_PATH=/usr/local/openblas/lib:$LD_LIBRARY_PATH

# install cntk custom mkl, scipy and kaldi
RUN mkdir /usr/local/CNTKCustomMKL && \
    wget --no-verbose -O - https://www.cntk.ai/mkl/CNTKCustomMKL-Linux-1.tgz | \
    tar -xzf - -C /usr/local/CNTKCustomMKL && \
    # scipy
    SCIPY_VERSION=0.18.0 && \
    wget -q -O - https://github.com/scipy/scipy/releases/download/v${SCIPY_VERSION}/scipy-${SCIPY_VERSION}.tar.gz | tar -zxf - && \
    cd scipy-${SCIPY_VERSION} && \
    python setup.py build && \
    python setup.py install && \
    cd .. && \
    rm -rf scipy-${SCIPY_VERSION} && \
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
    for dir in $KALDI_PATH/src/*bin; do make -C $dir clean; done

# build cntk
WORKDIR /cntk
RUN git clone --recursive https://github.com/Microsoft/cntk/ . && \
    ldconfig /usr/local/lib && CONFIGURE_OPTS="\
      --with-kaldi=${KALDI_PATH} \
      --1bitsgd=yes" && \
    mkdir -p build/cpu/release && \
    cd build/cpu/release && \
    ../../../configure $CONFIGURE_OPTS --with-openblas=/usr/local/openblas && \
    make -j"$(nproc)" all && \
    cd ../../.. && \
    mkdir -p build-mkl/cpu/release && \
    cd build-mkl/cpu/release && \
    ../../../configure $CONFIGURE_OPTS --with-mkl=/usr/local/CNTKCustomMKL && \
    make -j"$(nproc)" all && \
    rm -rf /cntk/build/cpu/release/.build && \
    rm -rf /cntk/build-mkl/cpu/release/.build && \
    # add LD_LIBRARY_PATH to root
    echo LD_LIBRARY_PATH=${LD_LIBRARY_PATH}:'$LD_LIBRARY_PATH' >> /root/.bashrc

# retrieve example data
RUN cd /cntk/Examples/Image/Miscellaneous/CIFAR-10 && \
    python CifarDownload.py && \
    python CifarConverter.py cifar-10-batches-py && \
    cd ../../../.. && \
    cd Examples/Image/MNIST/AdditionalFiles && \
    python mnist_convert.py

# set ssh command
EXPOSE 23
CMD ["/usr/sbin/sshd", "-D"]
