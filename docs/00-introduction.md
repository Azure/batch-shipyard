# Batch Shipyard Introduction
This page is the starting point for those unfamiliar with either Azure Batch
and/or Docker concepts.

## Azure Batch
[Azure Batch](https://azure.microsoft.com/en-us/services/batch/) is a scalable
job scheduling system leveraging the
[Microsoft Azure Cloud](https://azure.microsoft.com). Users can specify what
their jobs are (e.g., executing a binary to process text data), when to run
them, where to run them, and on what VM resources they are run on. The Azure
Batch service takes care of the rest including: compute resource provisioning,
task scheduling, automatic task recovery and retry on failure, automatic
scaling of resources if specified, and many other complexities that exist
at cloud-scale. **There is no extra cost to use Azure Batch** - Azure Batch
is provided as a free value-added service on top of compute resources in
Azure. Costs are incurred only for compute resources consumed and any
assoicated datacenter data egress and storage costs, i.e., the same cost
as if consuming
[Virtual Machines](https://azure.microsoft.com/en-us/pricing/details/virtual-machines/)
or [Cloud Services](https://azure.microsoft.com/en-us/pricing/details/cloud-services/)
directly.

Azure Batch can handle workloads on any point of the parallel and distributed
processing spectrum, from embarassingly parallel workloads all the way to
tightly-coupled message passing codes such as MPI jobs on Infiniband/RDMA.

### Concepts
Azure Batch has well-defined hierarchies of objects exposed to the user to
schedule work on machines.

Compute resources:
```
Azure Subscription --> Batch Account --> Compute Pool --> Compute Nodes
```

Batch accounts are provisioned from a valid Azure Subscription. With a
Batch account, users can provision Compute Pools of varying type such as
Windows or Linux. Pools are comprised of a target number of compute nodes
which are identical VMs provisioned from the Azure cloud. Multiple Batch
accounts can be provisioned per Azure Subscription, and multiple compute
pools can be provisioned per Batch account. Please refer to
[this page](https://docs.microsoft.com/en-us/azure/batch/batch-quota-limit)
for default service limits, including separate core quota limits that only
apply to the Batch service.

Compute jobs:
```
Job --> Tasks --> Subtasks (or tasklets)
```

Jobs are run on compute pools for which tasks are scheduled on to compute
nodes, either individually or as part of a group within a multi-instance
task (for which there are subtasks). Jobs can also be defined as part of a
Job Schedule in which users can specify times for when a job should run or
as part of any recurring schedule.

Files required as part of a task or generated as a side-effect of a task
can be referenced using a compute job heirarchy or a compute node heirarchy
(if the absolute file location is known). Files existing on compute nodes can
be transferred to any accessible endpoint, including Azure Storage. Files
may also be fetched from live compute nodes (i.e., nodes that have not yet
been deleted).

A high level overview of Azure Batch service basics can be found
[here](https://azure.microsoft.com/en-us/documentation/articles/batch-technical-overview/).
Further in-depth treatment of Azure Batch concepts can be found
[here](https://azure.microsoft.com/en-us/documentation/articles/batch-api-basics/).

## Docker
The Docker ecosystem is a comprehensive suite of userland tooling and
implementation of operating system-level virtualization where with the aid of
the underlying OS kernel can enforce isolation between groups of running
software. In contrast to hypervisor-based virtual machines, Docker is
lightweight, leveraging a shared kernel for fast and consistent application
deployments. More information about Docker can be found
[here](https://www.docker.com/what-docker).

### Concepts
* A Docker image contains all of the necessary software to run an application
  and exists only in read-only form. Can be thought of as a template for a
  container.
* Docker containers are instances of an image, with everything needed for
  the containerized application to run.
* Registries contain repositories of Docker images which can be later
  retrieved or updated.

Further in-depth treatment of Docker can be found
[here](https://docs.docker.com/engine/understanding-docker/).

## Docker+Azure Batch
By leveraging the Docker ecosystem, tooling and packaging, users can spend
less time hassling with the underlying infrastructure, VM application state
consistency, potential dependency interaction side effects and spend more
time on things that actually matter for their batch workloads: the job and
task results themselves. And with Azure Batch, you can scale your workload up
and only pay for the compute resources you use. The Batch Shipyard toolkit
provides a way to combine both with ease!

## Batch Shipyard Installation
Continue on to
[Batch Shipyard Installation](01-batch-shipyard-installation.md).
