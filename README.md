[![Build Status](https://travis-ci.org/Azure/batch-shipyard.svg?branch=master)](https://travis-ci.org/Azure/batch-shipyard)
[![Docker Pulls](https://img.shields.io/docker/pulls/alfpark/batch-shipyard.svg)](https://hub.docker.com/r/alfpark/batch-shipyard)
[![Image Layers](https://images.microbadger.com/badges/image/alfpark/batch-shipyard.svg)](http://microbadger.com/images/alfpark/batch-shipyard)

# Batch Shipyard
[Batch Shipyard](https://github.com/Azure/batch-shipyard) is a tool to help
provision and execute batch-style Docker workloads on
[Azure Batch](https://azure.microsoft.com/en-us/services/batch/) compute
pools. No experience with the
[Azure Batch SDK](https://github.com/Azure/azure-batch-samples) is needed; run
your Dockerized tasks with easy-to-understand configuration files!

## Major Features
* Automated [Docker Host Engine](https://www.docker.com) installation tuned
for Azure Batch compute nodes
* Automated deployment of required Docker images to compute nodes
* Accelerated Docker image deployment at scale to compute pools consisting of
a large number of VMs via private peer-to-peer distribution of Docker images
among the compute nodes
* Automated Docker Private Registry instance creation on compute nodes with
Docker images backed to Azure Storage if specified
* Automatic shared data volume support for:
  * [Azure File Docker Volume Driver](https://github.com/Azure/azurefile-dockervolumedriver)
    installation and share setup for SMB/CIFS backed to Azure Storage if
    specified
  * [GlusterFS](https://www.gluster.org/) distributed network file system
    installation and setup if specified
* Seamless integration with Azure Batch job, task and file concepts along with
full pass-through of the
[Azure Batch API](https://azure.microsoft.com/en-us/documentation/articles/batch-api-basics/)
to containers executed on compute nodes
* Support for
[Azure Batch task dependencies](https://azure.microsoft.com/en-us/documentation/articles/batch-task-dependencies/)
allowing complex processing pipelines and graphs with Docker containers
* Transparent support for
[GPU accelerated Docker applications](https://github.com/NVIDIA/nvidia-docker)
on [Azure N-Series VM instances](https://azure.microsoft.com/en-us/blog/azure-n-series-preview-availability/)
([Preview](http://gpu.azure.com/))
* Support for multi-instance tasks to accommodate Dockerized MPI and multi-node
cluster applications on compute pools with automatic job cleanup
* Transparent assist for running Docker containers utilizing Infiniband/RDMA
for MPI on
[HPC low-latency Azure VM instances](https://azure.microsoft.com/en-us/documentation/articles/virtual-machines-windows-a8-a9-a10-a11-specs/)
(i.e., STANDARD\_A8 and STANDARD\_A9)
* Automatic setup of SSH tunneling to Docker Hosts on compute nodes if
specified

## Installation
Simply clone the repository:

```
git clone https://github.com/Azure/batch-shipyard.git
```

or [download the latest release](https://github.com/Azure/batch-shipyard/releases).

Please see [this page](docs/01-batch-shipyard-installation.md) for more
information regarding installation and requirements.

## Batch Shipyard Compute Node OS Support
Batch Shipyard is currently only compatible with
[Azure Batch supported Marketplace Linux VMs](https://azure.microsoft.com/en-us/documentation/articles/batch-linux-nodes/#list-of-virtual-machine-images).

## Documentation
Please refer to
[this guide](https://github.com/Azure/batch-shipyard/blob/master/docs)
for a complete primer on concepts, usage and a quickstart guide.

Please visit the
[recipes directory](https://github.com/Azure/batch-shipyard/blob/master/recipes)
for different sample Docker workloads using Azure Batch and Batch Shipyard
after you have completed the primer.

## ChangeLog
See the [CHANGELOG.md](https://github.com/Azure/batch-shipyard/blob/master/CHANGELOG.md)
file.

* * *
This project has adopted the
[Microsoft Open Source Code of Conduct](https://opensource.microsoft.com/codeofconduct/).
For more information see the
[Code of Conduct FAQ](https://opensource.microsoft.com/codeofconduct/faq/) or
contact [opencode@microsoft.com](mailto:opencode@microsoft.com) with any
additional questions or comments.
