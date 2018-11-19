# Batch Shipyard Recipes
Batch Shipyard can accommodate most containerized Batch and HPC workloads.
This directory contains recipes and sample container workloads. Please note
that all recipes have sample configurations that you can use to quickly get
going, however, some of the config files cannot be used as-is as they may
need to be modified for specific values (such as the `credentials.yaml`
file which needs to be populated with your Batch and Storage account
credentials). Please review each config file you are planning on using and
modify accordingly. As these recipe configuration are intended to show
example usage, you will need to modify and configure them for your actual
workloads.

If you would like to contribute your recipe, please take a look at
[this guide](../docs/98-contributing-recipes.md) before submitting a
pull request.

## Recipe Collections
Use the following links to quickly navigate to recipe collections:

1. [Benchmarks](#benchmarks)
2. [Computational Fluid Dynamics (CFD)](#cfd)
3. [Deep Learning](#deeplearning)
4. [Molecular Dynamics (MD)](#md)
5. [RemoteFS](#remotefs)
6. [Video Processing](#video)

## <a name="benchmarks"></a>Benchmarks
#### [HPCG-Infiniband-IntelMPI](./HPCG-Infiniband-IntelMPI)
This HPCG-Infiniband-IntelMPI recipe contains information on how to
containerize [HPCG](http://www.hpcg-benchmark.org/index.html)
across Infiniband/RDMA Azure VMs with Intel MPI.

#### [HPLinpack-Infiniband-IntelMPI](./HPLinpack-Infiniband-IntelMPI)
This HPLinpack-Infiniband-IntelMPI recipe contains information on how to
containerize [HPLinpack (HPL)](http://www.netlib.org/benchmark/hpl/)
across Infiniband/RDMA Azure VMs with Intel MPI.

## <a name="cfd"></a>Computational Fluid Dynamics (CFD)
#### [OpenFOAM-Infiniband-IntelMPI](./OpenFOAM-Infiniband-IntelMPI)
This OpenFOAM-Infiniband-IntelMPI recipe contains information on how to
containerize distributed [OpenFOAM](http://www.openfoam.org/) across
Infiniband/RDMA Azure VMs with Intel MPI.

#### [OpenFOAM-TCP-OpenMPI](./OpenFOAM-TCP-OpenMPI)
This OpenFOAM-TCP-OpenMPI recipe contains information on how to containerize
distributed [OpenFOAM](http://www.openfoam.org/) across multiple Azure Batch
compute nodes.

## <a name="deeplearning"></a>Deep Learning
#### [Caffe-CPU](./Caffe-CPU)
This Caffe-CPU recipe contains information on how to containerize
[Caffe](http://caffe.berkeleyvision.org/) for use on Azure Batch compute nodes.

#### [Caffe-GPU](./Caffe-GPU)
This Caffe-GPU recipe contains information on how to containerize
[Caffe](http://caffe.berkeleyvision.org/) on GPUs for use with N-Series Azure
VMs.

#### [Caffe2-CPU](./Caffe2-CPU)
This Caffe2-CPU recipe contains information on how to containerize
[Caffe2](https://caffe2.ai/) for use on Azure Batch compute nodes.

#### [Caffe2-GPU](./Caffe2-GPU)
This Caffe2-GPU recipe contains information on how to containerize
[Caffe2](https://caffe2.ai/) on GPUs for use with N-Series Azure VMs.

#### [Chainer-CPU](./Chainer-CPU)
This Chainer-CPU recipe contains information on how to containerize
[Chainer](http://chainer.org/) for use on Azure Batch compute nodes.

#### [Chainer-GPU](./Chainer-GPU)
This Chainer-GPU recipe contains information on how to containerize
[Chainer](http://chainer.org/) on GPUs for use with N-Series Azure VMs.

#### [CNTK-CPU-Infiniband-IntelMPI](./CNTK-CPU-Infiniband-IntelMPI)
This CNTK-CPU-Infiniband-IntelMPI recipe contains information on how to
containerize [CNTK](https://cntk.ai/) for CPUs, including execution across
multiple Infiniband/RDMA Azure VMs with multi-instance tasks.

#### [CNTK-CPU-OpenMPI](./CNTK-CPU-OpenMPI)
This CNTK-CPU-OpenMPI recipe contains information on how to containerize
[CNTK](https://cntk.ai/) for CPUs, including execution across multiple
compute nodes with multi-instance tasks.

#### [CNTK-GPU-Infiniband-IntelMPI](./CNTK-GPU-Infiniband-IntelMPI)
This CNTK-GPU-Infiniband-IntelMPI recipe contains information on how to
containerize [CNTK](https://cntk.ai/) on GPUs for use with N-Series Azure VMs,
including execution across multiple Infiniband/RDMA Azure VMs with
multi-instance tasks.

#### [CNTK-GPU-OpenMPI](./CNTK-GPU-OpenMPI)
This CNTK-GPU-OpenMPI recipe contains information on how to containerize
[CNTK](https://cntk.ai/) on GPUs for use with N-Series Azure VMs, including
execution across multiple compute nodes and multiple GPUs with multi-instance
tasks.

#### [HPMLA-CPU-OpenMPI](./HPMLA-CPU-OpenMPI)
This recipe contains information on how to containerize the Microsoft High
Performance ML Algorithms (HPMLA) for use across multiple compute
nodes.

#### [Keras+Theano-CPU](./Keras+Theano-CPU)
This Keras+Theano-CPU recipe contains information on how to containerize
[Keras](https://keras.io/) with the
[Theano](http://www.deeplearning.net/software/theano/) backend for use on
Azure Batch compute nodes.

#### [Keras+Theano-GPU](./Keras+Theano-GPU)
This Keras+Theano-GPU recipe contains information on how to containerize
[Keras](https://keras.io/) with the
[Theano](http://www.deeplearning.net/software/theano/) backend for use with
N-Series Azure VMs.

#### [MXNet-CPU](./MXNet-CPU)
This MXNet-CPU recipe contains information on how to containerize
[MXNet](http://mxnet.io/) for use on Azure Batch compute nodes, including
execution across multiple compute nodes with multi-instance tasks.

#### [MXNet-GPU](./MXNet-GPU)
This MXNet-GPU recipe contains information on how to containerize
[MXNet](http://mxnet.io/) on GPUs for use with N-Series Azure VMs, including
execution across multiple compute nodes and multiple GPUs with multi-instance
tasks.

#### [PyTorch-CPU](./PyTorch-CPU)
This PyTorch-CPU recipe contains information on how to containerize
[PyTorch](https://pytorch.org) for use on Azure Batch compute nodes.

#### [PyTorch-GPU](./PyTorch-GPU)
This Torch-GPU recipe contains information on how to containerize
[PyTorch](https://pytorch.org) on GPUs for use with N-series Azure VMs.

#### [TensorFlow-CPU](./TensorFlow-CPU)
This TensorFlow-CPU recipe contains information on how to containerize
[TensorFlow](https://www.tensorflow.org/) for use on Azure Batch compute nodes.

#### [TensorFlow-Distributed](./TensorFlow-Distributed)
This TensorFlow-Distributed recipe contains information on how to containerize
[TensorFlow](https://www.tensorflow.org/) on GPUs for use with N-series Azure
VMs or across multiple CPU nodes.

#### [TensorFlow-GPU](./TensorFlow-GPU)
This TensorFlow-GPU recipe contains information on how to containerize
[TensorFlow](https://www.tensorflow.org/) on GPUs for use with N-series Azure
VMs.

#### [Torch-CPU](./Torch-CPU)
This Torch-CPU recipe contains information on how to containerize
[Torch](http://torch.ch) for use on Azure Batch compute nodes.

#### [Torch-GPU](./Torch-GPU)
This Torch-GPU recipe contains information on how to containerize
[Torch](http://torch.ch) on GPUs for use with N-series Azure VMs.

## <a name="md"></a>Molecular Dynamics (MD)
#### [NAMD-GPU](./NAMD-GPU)
This NAMD-GPU recipe contains information on how to containerize
[NAMD](http://www.ks.uiuc.edu/Research/namd/) on GPUs for use with N-Series
Azure VMs.

#### [NAMD-Infiniband-IntelMPI](./NAMD-Infiniband-IntelMPI)
This NAMD-Infiniband-IntelMPI recipe contains information on how to
containerize distributed [NAMD](http://www.ks.uiuc.edu/Research/namd/) across
Infiniband/RDMA Azure VMs with Intel MPI.

#### [NAMD-TCP](./NAMD-TCP)
This NAMD-TCP recipe contains information on how to containerize distributed
[NAMD](http://www.ks.uiuc.edu/Research/namd/) across multiple Azure Batch
compute nodes using TCP.

## <a name="remotefs"></a>RemoteFS Provisioning
#### [RemoteFS-GlusterFS](./RemoteFS-GlusterFS)
This RemoteFS-GlusterFS recipe contains information on how to provision a
sample multi-VM GlusterFS storage cluster.

#### [RemoteFS-GlusterFS+BatchPool](./RemoteFS-GlusterFS+BatchPool)
This RemoteFS-GlusterFS+BatchPool recipe contains information on how to
provision a Batch pool and automatically link it against a provisioned
GlusterFS storage cluster.

#### [RemoteFS-NFS](./RemoteFS-NFS)
This RemoteFS-NFS recipe contains information on how to provision a sample
single VM NFS server.

## <a name="video"></a>Video Processing
#### [FFmpeg-GPU](./FFmpeg-GPU)
This recipe contains information on how to use containerize
[FFmpeg](https://ffmpeg.org/) on GPUs for use with the N-series Azure VMs.
