# Batch Shipyard Recipes
This directory contains recipes and sample batch-style Docker workloads for
use with Batch Shipyard on Azure Batch. Please note that all recipes have
sample configurations that you can use to quickly get going, however, some
of the config files cannot be used as-is as they may need to be modified for
specific values (such as the `credentials.json` file which needs to be
populated with your Batch and Storage account credentials). Please review each
config file you are planning on using and modify accordingly. As the config
samples are bare examples only, you will need to configure them to your liking
for actual workloads.

If you would like to contribute your recipe, please take a look at
[this guide](../docs/98-contributing-recipes.md) before submitting a
pull request.

## Recipe Collections
Use the following links to quickly navigate to recipe collections:

1. [Benchmarks](#benchmarks)
2. [Computational Fluid Dynamics (CFD)](#cfd)
3. [Deep Learning](#deeplearning)
4. [Molecular Dynamics (MD)](#md)
5. [Video Processing](#video)

## <a name="benchmarks"></a>Benchmarks
#### [HPCG-Infiniband-IntelMPI](./HPCG-Infiniband-IntelMPI)
This HPCG-Infiniband-IntelMPI recipe contains information on how to
Dockerize [HPCG](http://www.hpcg-benchmark.org/index.html)
across Infiniband/RDMA Azure VMs with Intel MPI.

#### [HPLinpack-Infiniband-IntelMPI](./HPLinpack-Infiniband-IntelMPI)
This HPLinpack-Infiniband-IntelMPI recipe contains information on how to
Dockerize [HPLinpack (HPL)](http://www.netlib.org/benchmark/hpl/)
across Infiniband/RDMA Azure VMs with Intel MPI.

## <a name="cfd"></a>Computational Fluid Dynamics (CFD)
#### [OpenFOAM-Infiniband-IntelMPI](./OpenFOAM-Infiniband-IntelMPI)
This OpenFOAM-Infiniband-IntelMPI recipe contains information on how to
Dockerized distributed [OpenFOAM](http://www.openfoam.org/) across
Infiniband/RDMA Azure VMs with Intel MPI.

#### [OpenFOAM-TCP-OpenMPI](./OpenFOAM-TCP-OpenMPI)
This OpenFOAM-TCP-OpenMPI recipe contains information on how to Dockerized
distributed [OpenFOAM](http://www.openfoam.org/) across multiple Azure Batch
compute nodes.

## <a name="deeplearning"></a>Deep Learning
#### [CNTK-CPU-Infiniband-IntelMPI](./CNTK-CPU-Infiniband-IntelMPI)
This CNTK-CPU-Infiniband-IntelMPI recipe contains information on how to
Dockerize [CNTK](https://cntk.ai/) for CPUs, including execution across
multiple Infiniband/RDMA Azure VMs with multi-instance tasks.

#### [CNTK-CPU-OpenMPI](./CNTK-CPU-OpenMPI)
This CNTK-CPU-OpenMPI recipe contains information on how to Dockerize
[CNTK](https://cntk.ai/) for CPUs, including execution across multiple
compute nodes with multi-instance tasks.

#### [CNTK-GPU-OpenMPI](./CNTK-GPU-OpenMPI)
This CNTK-GPU-OpenMPI recipe contains information on how to Dockerize
[CNTK](https://cntk.ai/) on GPUs for use with N-Series Azure VMs, including
execution across multiple compute nodes and multiple GPUs with multi-instance
tasks.

#### [Caffe-CPU](./Caffe-CPU)
This Caffe-CPU recipe contains information on how to Dockerize
[Caffe](http://caffe.berkeleyvision.org/) for use on Azure Batch compute nodes.

#### [Caffe-GPU](./Caffe-GPU)
This Caffe-GPU recipe contains information on how to Dockerize
[Caffe](http://caffe.berkeleyvision.org/) on GPUs for use with N-Series Azure
VMs.

#### [Keras+Theano-CPU](./Keras+Theano-CPU)
This Keras+Theano-CPU recipe contains information on how to Dockerize
[Keras](https://keras.io/) with the
[Theano](http://www.deeplearning.net/software/theano/) backend for use on
Azure Batch compute nodes.

#### [Keras+Theano-GPU](./Keras+Theano-GPU)
This Keras+Theano-GPU recipe contains information on how to Dockerize
[Keras](https://keras.io/) with the
[Theano](http://www.deeplearning.net/software/theano/) backend for use with
N-Series Azure VMs.

#### [MXNet-CPU](./MXNet-CPU)
This MXNet-CPU recipe contains information on how to Dockerize
[MXNet](http://mxnet.io/) for use on Azure Batch compute nodes, including
execution across multiple compute nodes with multi-instance tasks.

#### [MXNet-GPU](./MXNet-GPU)
This MXNet-GPU recipe contains information on how to Dockerize
[MXNet](http://mxnet.io/) on GPUs for use with N-Series Azure VMs, including
execution across multiple compute nodes and multiple GPUs with multi-instance
tasks.

#### [TensorFlow-CPU](./TensorFlow-CPU)
This TensorFlow-CPU recipe contains information on how to Dockerize
[TensorFlow](https://www.tensorflow.org/) for use on Azure Batch compute nodes.

#### [TensorFlow-Distributed](./TensorFlow-Distributed)
This TensorFlow-Distributed recipe contains information on how to Dockerize
[TensorFlow](https://www.tensorflow.org/) on GPUs for use with N-series Azure
VMs or across multiple CPU nodes.

#### [TensorFlow-GPU](./TensorFlow-GPU)
This TensorFlow-GPU recipe contains information on how to Dockerize
[TensorFlow](https://www.tensorflow.org/) on GPUs for use with N-series Azure
VMs.

#### [Torch-CPU](./Torch-CPU)
This Torch-CPU recipe contains information on how to Dockerize
[Torch](http://torch.ch) for use on Azure Batch compute nodes.

#### [Torch-GPU](./Torch-GPU)
This Torch-GPU recipe contains information on how to Dockerize
[Torch](http://torch.ch) on GPUs for use with N-series Azure VMs.

## <a name="md"></a>Molecular Dynamics (MD)
#### [NAMD-GPU](./NAMD-GPU)
This NAMD-GPU recipe contains information on how to Dockerize
[NAMD](http://www.ks.uiuc.edu/Research/namd/) on GPUs for use with N-Series
Azure VMs.

#### [NAMD-Infiniband-IntelMPI](./NAMD-Infiniband-IntelMPI)
This NAMD-Infiniband-IntelMPI recipe contains information on how to Dockerize
distributed [NAMD](http://www.ks.uiuc.edu/Research/namd/) across
Infiniband/RDMA Azure VMs with Intel MPI.

#### [NAMD-TCP](./NAMD-TCP)
This NAMD-TCP recipe contains information on how to Dockerize distributed
[NAMD](http://www.ks.uiuc.edu/Research/namd/) across multiple Azure Batch
compute nodes using TCP.

## <a name="video"></a>Video Processing
#### [FFmpeg-GPU](./FFmpeg-GPU)
This recipe contains information on how to use Dockerized
[FFmpeg](https://ffmpeg.org/) on GPUs for use with the N-series Azure VMs.
