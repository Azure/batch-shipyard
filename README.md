[![Build Status](https://azurebatch.visualstudio.com/batch-shipyard/_apis/build/status/batch-shipyard-CI)](https://azurebatch.visualstudio.com/batch-shipyard/_build/latest?definitionId=11)
[![Build Status](https://travis-ci.org/Azure/batch-shipyard.svg?branch=master)](https://travis-ci.org/Azure/batch-shipyard)
[![Build status](https://ci.appveyor.com/api/projects/status/3a0j0gww57o6nkpw/branch/master?svg=true)](https://ci.appveyor.com/project/alfpark/batch-shipyard)
[![Docker Pulls](https://img.shields.io/docker/pulls/alfpark/batch-shipyard.svg)](https://hub.docker.com/r/alfpark/batch-shipyard)
[![Image Layers](https://images.microbadger.com/badges/image/alfpark/batch-shipyard:latest-cli.svg)](http://microbadger.com/images/alfpark/batch-shipyard)

# Batch Shipyard
<img src="https://azurebatchshipyard.blob.core.windows.net/github/README-dash.gif" alt="dashboard" width="1024" />

[Batch Shipyard](https://github.com/Azure/batch-shipyard) is a tool to help
provision, execute, and monitor container-based batch processing and HPC
workloads on
[Azure Batch](https://azure.microsoft.com/services/batch/). Batch Shipyard
supports both [Docker](https://www.docker.com) and
[Singularity](https://www.sylabs.io) containers. No experience with the
[Azure Batch SDK](https://github.com/Azure/azure-batch-samples) is needed; run
your containers with easy-to-understand configuration files. All Azure
regions are supported, including non-public Azure regions.

Additionally, Batch Shipyard provides the ability to provision and manage
entire [standalone remote file systems (storage clusters)](https://batch-shipyard.readthedocs.io/en/latest/65-batch-shipyard-remote-fs/)
in Azure, independent of any integrated Azure Batch functionality.

## Major Features
### Container Runtime and Image Management
* Support for multiple container runtimes including
[Docker](https://docker.com), [Singularity](https://www.sylabs.io), and
[Kata Containers](https://katacontainers.io/) tuned for Azure Batch
compute nodes
* Automated deployment of container images required for tasks to compute nodes
* Transparent support for GPU-accelerated container applications on both
[Docker](https://github.com/NVIDIA/nvidia-docker) and Singularity
on [Azure N-Series VM instances](https://docs.microsoft.com/azure/virtual-machines/linux/sizes-gpu)
* Support for Docker Registries including
[Azure Container Registry](https://azure.microsoft.com/services/container-registry/),
other Internet-accessible public and private registries, and support for
the [Singularity Hub](https://singularity-hub.org/) Container Registry

### Data Management and Shared File Systems
* Comprehensive [data movement](https://batch-shipyard.readthedocs.io/en/latest/70-batch-shipyard-data-movement/)
support: move data easily between locally accessible storage systems, remote
filesystems, Azure Blob or File Storage, and compute nodes
* [Standalone Remote Filesystem Provisioning](https://batch-shipyard.readthedocs.io/en/latest/65-batch-shipyard-remote-fs/)
with integration to auto-link these filesystems to compute nodes with
support for [NFS](https://en.wikipedia.org/wiki/Network_File_System) and
[GlusterFS](https://www.gluster.org/) distributed network file system
* Automatic shared data volume support for linking to
[Remote Filesystems](https://batch-shipyard.readthedocs.io/en/latest/65-batch-shipyard-remote-fs/),
[Azure File](https://azure.microsoft.com/services/storage/files/)
via SMB, [Azure Blob](https://azure.microsoft.com/services/storage/blobs/)
via [blobfuse](https://github.com/Azure/azure-storage-fuse),
[GlusterFS](https://www.gluster.org/) provisioned directly on compute nodes,
and custom Linux mount support (fstab)
* Support for automated on-demand, per-job distributed scratch space
provisioning via [BeeGFS BeeOND](https://www.beegfs.io/wiki/BeeOND)

### Monitoring
* Automated, integrated
[resource monitoring](https://batch-shipyard.readthedocs.io/en/latest/66-batch-shipyard-resource-monitoring/)
with [Prometheus](https://prometheus.io/) and [Grafana](https://grafana.com/)
for Batch pools and RemoteFS storage clusters
* Support for [Batch Insights](https://github.com/Azure/batch-insights)

### Open Source Scheduler Integration
* Support for [elastic cloud bursting](https://batch-shipyard.readthedocs.io/en/latest/69-batch-shipyard-slurm/)
on [Slurm](https://slurm.schedmd.com/) to Batch pools with automated
RemoteFS shared file system linking

### Azure Ecosystem Integration
* Support for
[serverless execution](https://batch-shipyard.readthedocs.io/en/latest/60-batch-shipyard-site-extension/)
binding with Azure Functions
* Support for credential management through
[Azure KeyVault](https://azure.microsoft.com/services/key-vault/)

### Azure Batch Integration and Enhancements
* [Federation](https://batch-shipyard.readthedocs.io/en/latest/68-batch-shipyard-federation/)
support: enables unified, constraint-based scheduling to collections of
heterogeneous pools, including across multiple Batch accounts and Azure
regions
* Support for simple, scenario-based [pool autoscale](https://batch-shipyard.readthedocs.io/en/latest/30-batch-shipyard-autoscale/)
and autopool to dynamically scale and control computing resources on-demand
* Support for [Task Factories](https://batch-shipyard.readthedocs.io/en/latest/35-batch-shipyard-task-factory-merge-task/)
with the ability to generate tasks based on parametric (parameter) sweeps,
randomized input, file enumeration, replication, and custom Python code-based
generators
* Support for
[multi-instance tasks](https://batch-shipyard.readthedocs.io/en/latest/80-batch-shipyard-multi-instance-tasks/)
to accommodate MPI and multi-node cluster applications packaged as Docker or
Singularity containers on compute pools with automatic job completion and
task termination
* Transparent assist for running Docker and Singularity containers utilizing
Infiniband/RDMA for MPI on HPC low-latency Azure VM instances including
[A-Series](https://docs.microsoft.com/azure/virtual-machines/linux/sizes-hpc),
[H-Series](https://docs.microsoft.com/azure/virtual-machines/linux/sizes-hpc),
and [N-Series](https://docs.microsoft.com/azure/virtual-machines/linux/sizes-gpu)
* Seamless integration with Azure Batch job, task and file concepts along with
full pass-through of the
[Azure Batch API](https://azure.microsoft.com/documentation/articles/batch-api-basics/)
to containers executed on compute nodes
* Support for [Azure Batch task dependencies](https://azure.microsoft.com/documentation/articles/batch-task-dependencies/)
allowing complex processing pipelines and DAGs
* Support for merge or final task specification that automatically depends
on all other tasks within the job
* Support for job schedules and recurrences for automatic execution of
tasks at set intervals
* Support for live job and job schedule migration between pools
* Support for [Low Priority Compute Nodes](https://docs.microsoft.com/azure/batch/batch-low-pri-vms)
* Support for deploying Batch compute nodes into a specified
[Virtual Network](https://batch-shipyard.readthedocs.io/en/latest/64-batch-shipyard-byovnet/)
* Automatic setup of SSH or RDP users to all nodes in the compute pool and
optional creation of SSH tunneling scripts to Docker Hosts on compute nodes
* Support for [custom host images](https://batch-shipyard.readthedocs.io/en/latest/63-batch-shipyard-custom-images/)
* Support for [Windows Containers](https://docs.microsoft.com/virtualization/windowscontainers/about/)
on compliant Windows compute node pools with the ability to activate
[Azure Hybrid Use Benefit](https://azure.microsoft.com/pricing/hybrid-benefit/)
if applicable

## Installation
### Local Installation
Please see [the installation guide](https://batch-shipyard.readthedocs.io/en/latest/01-batch-shipyard-installation/)
for more information regarding the various local installation options and
requirements.

### Azure Cloud Shell
Batch Shipyard is integrated directly into
[Azure Cloud Shell](https://docs.microsoft.com/azure/cloud-shell/overview)
and you can execute any Batch Shipyard workload using your web browser or
the Microsoft Azure [Android](https://play.google.com/store/apps/details?id=com.microsoft.azure&hl=en)
and [iOS](https://itunes.apple.com/us/app/microsoft-azure/id1219013620?mt=8)
app.

Simply request a Cloud Shell session and type `shipyard` to invoke the CLI;
no installation is required. Try Batch Shipyard now from your browser:
[![Launch Cloud Shell](https://shell.azure.com/images/launchcloudshell.png "Launch Cloud Shell")](https://shell.azure.com)

## Documentation and Recipes
Please refer to the
[Batch Shipyard Documentation on Read the Docs](https://batch-shipyard.readthedocs.io/).

Visit the
[Batch Shipyard Recipes](https://github.com/Azure/batch-shipyard/blob/master/recipes)
section for various sample container workloads using Azure Batch and Batch
Shipyard.

## Batch Shipyard Compute Node Host OS Support
Batch Shipyard is currently compatible with popular Azure Batch supported
[Marketplace Linux VMs](https://docs.microsoft.com/azure/virtual-machines/linux/endorsed-distros),
[compliant Linux custom images](https://batch-shipyard.readthedocs.io/en/latest/63-batch-shipyard-custom-images/),
and native Azure Batch
[Windows Server with Containers](https://azuremarketplace.microsoft.com/marketplace/apps/Microsoft.WindowsServer?tab=Overview)
VMs. Please see the
[platform image support](https://batch-shipyard.readthedocs.io/en/latest/25-batch-shipyard-platform-image-support/)
documentation for more information specific to Batch Shipyard support of
compute node host operating systems.

## Change Log
Please see the
[Change Log](https://batch-shipyard.readthedocs.io/en/latest/CHANGELOG/)
for project history.

* * *
Please see this project's [Code of Conduct](CODE_OF_CONDUCT.md) and
[Contributing](CONTRIBUTING.md) guidelines.
