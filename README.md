[![Build Status](https://travis-ci.org/Azure/batch-shipyard.svg?branch=master)](https://travis-ci.org/Azure/batch-shipyard)
[![Docker Pulls](https://img.shields.io/docker/pulls/alfpark/batch-shipyard.svg)](https://hub.docker.com/r/alfpark/batch-shipyard)
[![Image Layers](https://images.microbadger.com/badges/image/alfpark/batch-shipyard.svg)](http://microbadger.com/images/alfpark/batch-shipyard)

Batch Shipyard
==============
[Batch Shipyard](https://github.com/Azure/batch-shipyard) is a tool to help
provision and execute Dockerized workloads on
[Azure Batch](https://azure.microsoft.com/en-us/services/batch/) compute
pools. No experience with the Azure Batch SDK is needed; run your batch-style
Docker tasks through easy-to-understand configuration files!

Major Features
--------------
* Automated [Docker Host Engine](https://docker.io) installation on compute
nodes
* Automated deployment of required Docker images to compute nodes
* Accelerated Docker image deployment at scale to compute pools consisting of
a large number of compute nodes via peer-to-peer distribution of Docker
images among the VMs
* Automated Docker Private Registry instance creation on compute nodes backed
to Azure Storage if specified
* Automated
[Azure File Docker Volume Driver](https://github.com/Azure/azurefile-dockervolumedriver)
installation and share setup for SMB/CIFS backed to Azure Storage if
specified
* Seamless integration with Azure Batch job, task and file concepts along with
full pass-through of the Azure Batch API to containers executed on compute
nodes
* Support for task dependencies to allow for complex processing pipelines with
Docker containers
* Support for multi-instance tasks to accomodate Dockerized MPI applications
on compute pools
* Transparent assist for creating Docker containers utilizing Infiniband/RDMA
for MPI on
[HPC low-latency Azure VM instances](https://azure.microsoft.com/en-us/documentation/articles/virtual-machines-windows-a8-a9-a10-a11-specs/)
(STANDARD\_A8 and STANDARD\_A9)
* Automatic set up of SSH tunneling to Docker Hosts on compute nodes if
specified

Installation
------------
Simply clone the repository:

```
git clone https://github.com/Azure/batch-shipyard.git
```

or [download the latest release](https://github.com/Azure/batch-shipyard/releases).

Requirements
------------
The Batch Shipyard tool is written in Python. The client script is compatible
with Python 2.7 or 3.3+. You will also need to install the
[Azure Batch](https://pypi.python.org/pypi/azure-batch) and
[Azure Storage](https://pypi.python.org/pypi/azure-storage) python packages.
Installation can be performed using the [requirements.txt](./requirements.txt)
file via the command `pip install --user -r requirements.txt` (or via `pip3`
for python3).

Host OS (Compute Node) Support
------------------------------
Batch Shipyard is currently only compatible with Linux Batch Compute Pools
configured via
[VirtualMachineConfiguration](http://azure-sdk-for-python.readthedocs.io/en/latest/_modules/azure/batch/models/virtual_machine_configuration.html).
Please see the list of
[Azure Batch supported Marketplace Linux VMs](https://azure.microsoft.com/en-us/documentation/articles/batch-linux-nodes/#list-of-virtual-machine-images)
for use with Batch Shipyard.

Documentation
-------------
Please refer to
[this guide](https://github.com/Azure/batch-shipyard/blob/master/docs/00-introduction.md)
for a complete primer on concepts and usage.

Limitations
-----------
* Oracle Linux is not supported with Batch Shipyard at this time.
* Task dependencies are incompatible with multi-instance tasks. This is a
  current limitation of the underlying Azure Batch service.
* Only Intel MPI can be used in conjunction Infiniband/RDMA on Azure Linux VMs.
  This is a current limitation of the underlying VM and host drivers.

ChangeLog
---------
See the [CHANGELOG.md](https://github.com/Azure/batch-shipyard/blob/master/CHANGELOG.md)
file.

* * *
This project has adopted the
[Microsoft Open Source Code of Conduct](https://opensource.microsoft.com/codeofconduct/).
For more information see the
[Code of Conduct FAQ](https://opensource.microsoft.com/codeofconduct/faq/) or
contact [opencode@microsoft.com](mailto:opencode@microsoft.com) with any
additional questions or comments.
