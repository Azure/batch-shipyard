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

**NOTE: Some recipes are not complete, but are forthcoming.**

## Deep Learning
### CNTK-CPU-Infiniband-IntelMPI
TBC.

### [CNTK-CPU-OpenMPI](./CNTK-CPU-OpenMPI)
This CNTK-CPU-OpenMPI recipe contains information on how to Dockerize
[CNTK](https://cntk.ai/) for CPUs, including execution across multiple
compute nodes with multi-instance tasks.

### [CNTK-GPU-OpenMPI](./CNTK-GPU-OpenMPI)
This CNTK-GPU-OpenMPI recipe contains information on how to Dockerize
[CNTK](https://cntk.ai/) on GPUs for use with N-Series Azure VMs, including
execution across multiple compute nodes and multiple GPUs with multi-instance
tasks.

### [Caffe-CPU](./Caffe-CPU)
This Caffe-CPU recipe contains information on how to Dockerize
[Caffe](http://caffe.berkeleyvision.org/) for use on Azure Batch compute nodes.

### [Caffe-GPU](./Caffe-GPU)
This Caffe-GPU recipe contains information on how to Dockerize
[Caffe](http://caffe.berkeleyvision.org/) GPU for use with N-Series Azure VMs.

### [TensorFlow-CPU](./TensorFlow-CPU)
This TensorFlow-CPU recipe contains information on how to Dockerize
[TensorFlow](https://www.tensorflow.org/) for use on Azure Batch compute nodes.

### [TensorFlow-Distributed](./TensorFlow-Distributed)
This TensorFlow-Distributed recipe contains information on how to Dockerize
[TensorFlow](https://www.tensorflow.org/) on GPUs for use with N-series Azure
VMs or across multiple CPU nodes.

### [TensorFlow-GPU](./TensorFlow-GPU)
This TensorFlow-GPU recipe contains information on how to Dockerize
[TensorFlow](https://www.tensorflow.org/) on GPUs for use with N-series Azure
VMs.

## Computational Fluid Dynamics (CFD) and Molecular Dynamics (MD)
### [NAMD-Infiniband-IntelMPI](./NAMD-Infiniband-IntelMPI)
This NAMD-Infiniband-IntelMPI recipe contains information on how to Dockerize
distributed [NAMD](http://www.ks.uiuc.edu/Research/namd/) across
Infiniband/RDMA Azure VMs with Intel MPI.

### [NAMD-TCP](./NAMD-TCP)
This NAMD-TCP recipe contains information on how to Dockerize distributed
[NAMD](http://www.ks.uiuc.edu/Research/namd/) across multiple Azure Batch
compute nodes using TCP.

### OpenFOAM-Infiniband-IntelMPI
TBC.
[OpenFoam](http://www.openfoam.com/)

### [OpenFOAM-TCP-OpenMPI](./OpenFOAM-TCP-OpenMPI)
This OpenFOAM-TCP-OpenMPI recipe contains information on how to Dockerized
distributed [OpenFoam](http://www.openfoam.com/) across multiple Azure Batch
compute nodes.

## Video Processing
### [FFmpeg-GPU](./FFmpeg-GPU)
This recipe contains information on how to use Dockerized
[FFmpeg](https://ffmpeg.org/) on GPUs for use with the N-series Azure VMs.
