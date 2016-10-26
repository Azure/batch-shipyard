# Dockerfile for mxnet-cpu for use with Batch Shipyard on Azure Batch

FROM ubuntu:16.04
MAINTAINER Fred Park <https://github.com/Azure/batch-shipyard>

# install base system
COPY ssh_config /root/.ssh/config
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential git libssl-dev libcurl4-openssl-dev wget curl unzip \
        openssh-server openssh-client ca-certificates && \
    apt-get install -y --no-install-recommends \
        python-pip python-setuptools && \
    apt-get install -y --no-install-recommends \
        gfortran libopenblas-dev && \
    apt-get install -y --no-install-recommends \
        libopencv-core-dev && \
    apt-get install -y --no-install-recommends \
        libopencv-dev && \
    apt-get install -y --no-install-recommends \
        python-numpy python-opencv && \
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

# install Microsoft R Open
RUN curl -L --retry 10 --retry-max-time 0 https://mran.microsoft.com/install/mro/3.3.1/microsoft-r-open-3.3.1.tar.gz | tar -zxvpf - && \
    cd microsoft-r-open && \
    ./install.sh -a -u && \
    cd .. && \
    rm -rf microsoft-r-open && \
    Rscript -e "install.packages(c('devtools'), repo = 'https://cran.rstudio.com')" && \
    Rscript -e "install.packages(c('argparse', 'Rcpp', 'DiagrammeR', 'data.table', 'jsonlite', 'magrittr', 'stringr', 'roxygen2'), repos = 'https://cran.rstudio.com')"

# install mxnet with both python and R backends
ENV PYTHONPATH /mxnet/python
RUN git clone --recursive https://github.com/dmlc/mxnet/ && \
    cd mxnet && \
    cp make/config.mk . && \
    echo "USE_BLAS=openblas" >> config.mk && \
    echo "USE_DIST_KVSTORE=1" >> config.mk && \
    make -j$(nproc) && \
    cd R-package && \
    Rscript -e "library(devtools); library(methods); options(repos=c(CRAN='https://cran.rstudio.com')); install_deps(dependencies = TRUE)" && \
    cd .. && \
    make rpkg && \
    R CMD INSTALL mxnet_*.tar.gz && \
    cd python && \
    python setup.py install

# copy in sample run script
COPY run_mxnet.sh /mxnet

# set ssh command
EXPOSE 23
CMD ["/usr/sbin/sshd", "-D", "-p", "23"]
