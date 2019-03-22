# Slurm on Batch with Batch Shipyard
The focus of this article is to explain the Slurm on Batch functionality
in Batch Shipyard and how to effectively deploy your workload for
traditional lift-and-shift scheduling while leveraging some
Platform-as-a-Service capabilities of Azure Batch.

## Overview
The [Slurm](https://slurm.schedmd.com/) workload manager is an open-source
job scheduler that is widely used among many institutional and supercomputing
sites. Azure Batch provides an abstraction for managing lower-layer VM
complexities and automated recovery through Batch pools. Batch Shipyard
provides an integration between Slurm and Batch pools where the Slurm cluster
controller and login nodes are provisioned and connected to compute nodes in
Batch pools in an on-demand fashion.

### Why?
Why is this feature useful when you can use
[Azure Batch](https://azure.microsoft.com/services/batch/) natively as a job
scheduler or leverage
[Azure CycleCloud](https://azure.microsoft.com/features/azure-cyclecloud/)?

Some users or organizations may prefer the use of Slurm native
tooling and execution workflows which are not currently possible with Azure
Batch; either due to workflow familiarity or existing investments in the
ecosystem. Additionally, Azure Batch may not provide some of the rich job
scheduling and accounting functionality available in Slurm that may be
required for some organizational workflows. Moreover, some requirements such
as standing up a separate VM for CycleCloud or managing the underlying
Slurm compute node infrastructure may not be an amenable solution for some
users or organizations.

Slurm on Batch with Batch Shipyard attempts to mix the advantages of both
worlds by combining the Slurm scheduler with platform benefits of Azure Batch
compute node orchestration and management.

## Major Features
* Simple and automated Slurm cluster deployment and management including
support for on-demand suspend and restart of cluster resources
* Automatic HA support of Slurm controllers and the ability to create
multiple login nodes
* Ability to specify arbitrary elastic partitions which may be comprised of a
hetergeneous mixture of Batch pools
* Automatic linking of shared file systems (RemoteFS clusters) between
all Slurm resources
* Support for concurrent dedicated and low priority compute nodes within
partitions
* Automatic feature tagging of nodes, including VM size and capabilities
* Automatic generic resource configuration for GPU VMs
* Automatic on-demand resizing of compute node resources including
user-specified idle reclaim timeouts and node reclaim exclusion filters
* Support for custom preparation scripts on all Slurm resources
* Goal-seeking engine to recover from compute node allocation failures
* Default cluster user SSH is linked to login nodes and compute nodes for
easy logins and file access across non-controller resources
* Supports most Batch Shipyard configuration options on the pool, including
distributed scratch, container runtime installations, monitoring integration,
shared file system mounting, automatic GPU setup, etc.
* Supports joining pre-existing partitions and nodes which may be on-premises
with elastic on-demand nodes

## Mental Model
### Slurm Dynamic Node Allocation and Deallocation
A Slurm cluster on Batch with Batch Shipyard utilizes the
[Slurm Elastic Computing (Cloud Bursting)](https://slurm.schedmd.com/elastic_computing.html)
functionality which is based on Slurm's
[Power Save](https://slurm.schedmd.com/power_save.html) capabilities.
In a nutshell, Slurm will `resume` nodes when needed to process jobs and
`suspend` nodes once there is no need for the nodes to run (i.e., relinquish
them back to the cloud).

When Slurm decides that new nodes should be provisioned, the `resume`
command triggers the `Batch Shipyard Slurm Helper` which allocates compute
nodes on the appropriate Batch pool targeting a specific Azure region.
Batch Shipyard handles the complexity of node name assignment, host DNS
registration, and ensuring the controller updates the node information with
the appropriate IP address.

When Slurm decides that nodes should be removed via `suspend`, the
`Batch Shipyard Slurm Helper` will deallocate these nodes in their
respective pools and release the node names back for availability.

### Batch Pools as Slurm Compute Nodes
A Batch Shipyard provisioned Slurm cluster is built on top of different
resources in Azure. To more readily explain the concepts that form a Batch
Shipyard Slurm cluster, let's start with a high-level conceptual
layout of all of the components and possible interactions.

```
                                   +---------------+
                                   |               |
   +----------+  +-----------------> Azure Storage <----------------+
   |          |  |                 |               |                |
   | Azure    |  |                 +---------------+                |
   | Resource |  |                                                  |
   | Manager  |  |                  +-------------+                 |
   |          |  |                  |             |                 |
   +------^---+  |    +-------------> Azure Batch +------------+    |
          |      |    |             |             |            |    |
      MSI |  MSI |    | MSI         +-------------+            |    |
          |      |    |                                        |    |
+-------------------------------------------------------------------------------+
|         |      |    |                                        |    |           |
|         |      |    |                                   +----v----+--------+  |
|  +------------------------+                             |                  |  |
|  |      |      |    |     |                             |    +--------+    |  |
|  |   +--+------+----+-+   |                             |    |        |    |  |
|  |   |                |   <----------------------------->    | slurmd |    |  |
|  |   | Batch Shipyard |   |                             |    |        |    |  |
|  |   | Slurm Helper   |   |                             |    +--------+    |  |
|  |   |                |   |                             |                  |  |
|  |   +----------------+   |      +----------------+     | +--------------+ |  |
|  |                        |      |                |     | |              | |  |
|  |     +-----------+      |      | Batch Shipyard |     | | Slurm client | |  |
|  |     |           |      |      | Remote FS VMs  |     | | tools        | |  |
|  |     | slurmctld |      |      |                |     | |              | |  |
|  |     |           |      +------>    Subnet A    <-----+ +--------------+ |  |
|  |     +-----------+      |      |    10.0.1.0/24 |     |                  |  |
|  |                        |      +-------^--------+     |  Azure Batch     |  |
|  | Slurm Controller Nodes |              |              |  Compute Nodes   |  |
|  |                        |              |              |                  |  |
|  |            Subnet B    |              |              |      Subnet D    |  |
|  |            10.0.2.0/24 |              |              |      10.1.0.0/16 |  |
|  +----------^-------------+              |              +------------------+  |
|             |                   +--------+---------+                          |
|             |                   |                  |                          |
|             |                   | +--------------+ |                          |
|             |                   | |              | |                          |
|             +-------------------+ | Slurm client | |                          |
|                                 | | tools        | |                          |
|                                 | |              | |                          |
|                                 | +--------------+ |                          |
|                                 |                  |                          |
|                                 |   Login Nodes    |                          |
|                                 |                  |                          |
|                                 |      Subnet C    |                          |
|                                 |      10.0.3.0/24 |                          |
| Virtual Network                 +---------^--------+                          |
| 10.0.0.0/8                                |                                   |
+-------------------------------------------------------------------------------+
                                            |
                                        SSH |
                                            |
                                    +-------+------+
                                    |              |
                                    | Cluster User |
                                    |              |
                                    +--------------+
```

The base layer for all of the resources within a Slurm cluster on Batch is
an Azure Virtual Network. This virtual network can be shared
amongst other network-level resources such as network interfaces. The virtual
network can be "partitioned" into sub-address spaces through the use of
subnets. In the example above, we have four subnets where
`Subnet A 10.0.1.0/24` hosts the Batch Shipyard RemoteFS shared file system,
`Subnet B 10.0.2.0/24` contains the Slurm controller nodes,
`Subnet C 10.0.3.0/24` contains the login nodes,
and `Subnet D 10.1.0.0/16` contains a pool or a collection of pools of
Azure Batch compute nodes to serve as dynamically allocated Slurm
compute nodes.

One (or more) RemoteFS shared file systems can be used as a common file system
between login nodes and the Slurm compute nodes (provisioned as Batch compute
nodes). One of these file systems is also designated to store `slurmctld`
state for HA/failover for standby Slurm controller nodes. Cluster users
login to the Slurm cluster via the login nodes where the shared file system
is mounted and the Slurm client tools are installed which submit to the
controller nodes.

Slurm configuration and munge keys are propagated to the provisioned compute
nodes in Batch pools along with mounting the appropriate RemoteFS shared
file systems. Once these nodes are provisioned and idle, the node information
is updated on the controller nodes to be available for Slurm job scheduling.

When Slurm signals that nodes are no longer needed, the Batch Shipyard
Slurm helper will then translate the Slurm node names back to Batch compute
node ids and deprovision appropriately.

Some Slurm logs, notably the `Batch Shipyard Slurm Helper`, Slurm power
save logs, and `slurmd` logs are stored on an Azure File Share for easy
viewing to debug issues. `slurmctld` logs are stored locally with each
controller node.

## Walkthrough
The following is a brief walkthrough of configuring a Slurm on Batch cluster
with Batch Shipyard.

### Azure Active Directory Authentication Required
Azure Active Directory authentication is required to create a Slurm cluster.
When executing either the `slurm cluster create` or `slurm cluster orchestrate`
command, your service principal must be at least `Owner` or a
[custom role](https://docs.microsoft.com/azure/active-directory/role-based-access-control-custom-roles)
that does not prohibit the following action along with the ability to
create/read/write resources for the subscription:

* `Microsoft.Authorization/*/Write`

This action is required to enable
[Azure Managed Service Identity](https://docs.microsoft.com/azure/active-directory/managed-service-identity/overview)
on the Batch Shipyard Slurm Helper which runs on controller nodes.

### Configuration
The configuration for a Slurm cluster with Batch Shipyard is generally
composed of two major parts: the Slurm configuration the normal global and
pool configurations.

#### Slurm Cluster Configuration
The Slurm cluster configuration is defined by a Slurm configuration
file. Please refer to the full
[Slurm cluster configuration documentation](18-batch-shipyard-configuration-slurm.md)
for more detailed explanations of each option and for those not shown below.

Conceptually, this file consists of five major parts:

```yaml
slurm:
  # 1. define general settings
  storage_account_settings: mystorageaccount
  location: <Azure region, e.g., eastus>
  resource_group: my-slurm-rg
  cluster_id: slurm
  # 2. define controller node settings
  controller:
    ssh:
      # SSH access/user to the controller nodes, independent of other resources
    public_ip:
      # ...
    virtual_network:
      # Virtual Network should be the same for all resources, with a differing subnet
    network_security:
      # Optional, but recommended network security rules
    vm_size: # appropriate VM size
    vm_count: # Number greater than 1 will create an HA Slurm cluster
  # 3. define login node settings
  login:
    ssh:
      # The cluster user SSH and username settings
    public_ip:
      # ...
    virtual_network:
      # Virtual Network should be the same for all resources, with a differing subnet
    network_security:
      # Optional, but recommended network security rules
    vm_size: # appropriate VM size
    vm_count: # Number greater than 1 will create multiple login nodes
  # 4. define shared file systems
  shared_data_volumes:
    nfs_server: # Batch Shipyard RemoteFS storage cluster id
      mount_path: # The mount path across all Slurm resources
      store_slurmctld_state: # at least one shared data volume must set this to true
  # 5. define Slurm options
  slurm_options:
    idle_reclaim_time: # amount of idle time before Slurm issues suspend on nodes
    elastic_partitions: # define Slurm elastic cloud bursting partitions
      partition_1: # name of partition
        batch_pools:
          mypool1: # pool id, must be pre-allocated with zero nodes
            account_service_url: https://... # currently this must be the same as the Batch account specified in config.yaml
            compute_node_type: # dedicated or low_priority nodes
            max_compute_nodes: # maximum number of VMs to allocate
            weight: # Slurm weight
            features:
              # arbitrary constraint sequence
            reclaim_exclude_num_nodes: # number of nodes to exclude from idle reclaim.
                                       # Once allocated, these number of nodes are not reclaimed.
          # can define multiple pools
        max_runtime_limit: # maximum runtime for jobs in this partition
        default: # is the default partition, one partition must have this set to true
    unmanaged_partitions:
      # for pre-existing partitions (or on-prem partitions)
```

#### Global Configuration
[Global configuration](12-batch-shipyard-configuration-global.md) should
contain the appropriate RemoteFS shared file system/data volumes that are
to be used across all Slurm resources under
`global_resources`:`volumes`:`shared_data_volumes`. More than one RemoteFS
shared data volume can be specified.

Optionally, if your workload will be container driven, you can specify
image pre-loads here as per normal convention under `global_resources`.

#### Pool Configuration
[Pool configuration](13-batch-shipyard-configuration-pool.md) should
be used to create all necessary pools used for Slurm elastic partitions
beforehand. This file is not explicitly used for `slurm cluster create` and
only for `slurm cluster orchestrate` if orchestrating a Slurm cluster with
one pool. If not utilizing the orchestrate command, then it is required
to create pools individually before issuing `slurm cluster create`.

Most pool properties apply with no modifications for Slurm clusters. By
default, all Slurm nodes have Docker installed. Do not use `native` mode
for Slurm compute nodes.

### Limitations
This is a non-exhaustive list of potential limitations while using
the Slurm on Batch feature in Batch Shipyard.

* All pools must reside under the Batch account linked to the global
configuration. This limitation will be lifted at a later date.
* Shared file system (shared data volume) support is currently limited
to supported RemoteFS provisioned storage clusters: NFS and GlusterFS.
* LDAP for centralized user control is not implemented, but can be
customized per the `additional_prep_script` option on the `controller` and
`login` section of the Slurm configuration file and using
`additional_node_prep` for compute nodes.
* PAM-based auth restrictions for preventing users from logging into
compute nodes without a running job is not yet implemented.
* An action aggregator in the `Batch Shipyard Slurm Helper` that would
improve resize operation performance is not yet implemented.

### Notes
* Network Security Groups (NSGs) should permit communication between
Slurm resources for all required communication channels and ports.
* Ensure that you have sufficient core and pool quota for your Batch account.
Please note that *all* quotas (except for the number of Batch accounts
per region per subscription) apply to each individual Batch account
separately. User subscription based Batch accounts share the underlying
subscription regional core quotas.

## Sample Usage
Please see the sample [Slurm recipe](../recipes/Slurm+NFS) for a working
example.
