# Remote Filesystems with Batch Shipyard
The focus of this article is to explain how to provision a standalone
file server or storage cluster for use as a shared file system.

**Notabene:** Creating a standalone remote filesystem with Batch Shipyard is
independent of Azure Batch and all Batch related functionality in Batch
Shipyard. You may create a filesystem in Azure with Batch Shipyard and
manage it with the tooling in Batch Shipyard or in the Azure Portal without
having to create an Azure Batch account. However, if you do want to use
this filesystem with the Azure Batch service, many convenience features
are present to make using such filesystems relatively painless with your
jobs and tasks.

## Overview
The ability to have a shared file system that all compute nodes can access
is vital to many HPC and batch processing workloads. Azure Batch provides
simple mechanisms for scaling a workload, but most non-trivial compute
tasks often require access to shared data, whether that is as simple as
configuration files to more complicated scenarios such as shared model files
or shared output for validation.

Some scenarios are natively handled by Azure Batch through resource files
or through Batch Shipyard with data ingress. However, there are many
scenarios where this is insufficient and only a real shared file system will
suffice.

Batch Shipyard includes support for automatically provisioning an entire
file server with attached disks or a GlusterFS storage cluster for both
scale up and scale out scenarios.

## Major Features
* Support for multiple file server types: NFS or GlusterFS
* Support for SMB/CIFS on top of NFS or GlusterFS mountpoints to enable
file sharing to Windows clients
* Automatic provisioning of all required resources for the storage cluster
including managed disks, virtual networks, subnets, network interfaces, IP
addresses and DNS labels, network security groups, availability sets, virtual
machines and extensions
* Suite of commandline tooling for cluster management including
zero-downtime disk array expansion and storage cluster resize (scale out),
status queries tailored to file server types and hassle-free SSH for
administration
* Support for cluster suspension (deallocation) and restart
* Support for definining and managing multiple clusters simultaneously
* Support for [btrfs](https://en.wikipedia.org/wiki/Btrfs) along with
ext4, ext3 and ext2 filesystems
* Automatic disk array construction via RAID-0 through btrfs or Linux
software RAID (mdadm)
* Consistent private IP address allocation per virtual machine and virtual
machine to disk mapping
* Automatic network security rule configuration based on file server type,
if requested
* Automatic placement in an availability set for GlusterFS virtual machines
* Support for [accelerated networking](https://docs.microsoft.com/en-us/azure/virtual-network/create-vm-accelerated-networking-cli)
* Automatic SSH keypair provisioning and setup for all file servers in
storage cluster
* Configuration-driven data ingress support via scp and rsync+ssh, including
concurrent multi-node parallel transfers with GlusterFS storage clusters

## Azure Batch Integration Features
* Automatic linking between Azure Batch pools (compute nodes)
and Batch Shipyard provisioned remote filesystems
* Support for mounting multiple disparate Batch Shipyard provisioned remote
filesystems concurrently to the same pool and compute nodes
* Automatic failover for HA GlusterFS volume file lookups (compute node client
mount) through remote filesystem deployment walk to find disparate upgrade and
fault domains of the GlusterFS servers
* Automatic volume mounting of remote filesystems into a Docker container
executed through Batch Shipyard

## Overview and Mental Model
A Batch Shipyard provisioned remote filesystem is built on top of different
resources in Azure. These resources are from networking, storage and
compute. To more readily explain the concepts that form a Batch Shipyard
standalone storage cluster, let's start with a high-level conceptual
layout of all of the components and possible interacting actors.

```
                          +------------------------------------------------------------+
                          |                                                            |
                          | +-------------------------------+                          |
                          | |                               |                          |
                          | | +---------------------------+ |                          |
                          | | |           +-------------+ | |                          |
                          | | |           | Data | Data | | |   +--------------------+ |
                          | | |           | Disk | Disk | | |   |        Subnet B    | |
                          | | | Virtual   |  00  |  01  | | |   |        10.1.0.0/16 | |
                          | | | Machine A +-------------+ | |   | +----------------+ | |
                          | | |           | Data | Data | | |   | |                | | |
                          | | | GlusterFS | Disk | Disk | | |   | | Azure Batch    | | |
                          | | | Server 0  |  02  |  ..  | | |   | | Compute Node X | | |
                          | | |           +------+------+ | |   | |                | | |
                          | | |             RAID-0 Array  | |   | +------------+   | | |
+--------------+   Mount  | | +-----------+  +------------+ |   | | Private IP |   | | |
| External     <--------------> Public IP |  | Private IP <-------> 10.1.0.4   |   | | |
| Client       |   Brick  | | | 1.2.3.4   |  | 10.0.0.4   | |   | +------------+---+ | |
| Mount        |   Data   | | +-----------+--+-----^------+ |   |                    | |
| (if allowed) |          | |                      |        |   +--------------------+ |
+------^-------+          | |                      |        |                          |
       |                  | |                      |        |   +--------------------+ |
       |                  | | +-----------+--+-----v------+ |   |                    | |
       +----------------------> Public IP |  | Private IP | |   | +------------+---+ | |
           Brick Data     | | | 1.2.3.5   |  | 10.0.0.5   <-------> Private IP |   | | |
                          | | +---------------------------+ |   | | 10.2.1.4   |   | | |
                          | | |           +-------------+ | |   | +------------+   | | |
                          | | |           | Data | Data | | |   | |                | | |
                          | | |           | Disk | Disk | | |   | | Azure Virtual  | | |
                          | | | Virtual   |  00  |  01  | | |   | | Machine Y      | | |
                          | | | Machine B +-------------+ | |   | |                | | |
                          | | |           | Data | Data | | |   | +----------------+ | |
                          | | | GlusterFS | Disk | Disk | | |   |        Subnet C    | |
                          | | | Server 1  |  02  |  ..  | | |   |        10.2.1.0/24 | |
                          | | |           +------+------+ | |   +--------------------+ |
                          | | |             RAID-0 Array  | |                          |
                          | | +---------------------------+ |                          |
                          | |                   Subnet A    |                          |
                          | |                   10.0.0.0/24 |                          |
                          | +-------------------------------+                          |
                          |                                            Virtual Network |
                          |                                            10.0.0.0/8      |
                          +------------------------------------------------------------+
```

The base layer for all of the resources within a standalone provisioned
filesystem is an Azure Virtual Network. This virtual network can be shared
amongst other network-level resources such as network interfaces. The virtual
network can be "partitioned" into sub-address spaces through the use of
subnets. In the example above, we have three subnets where
`Subnet A 10.0.0.0/24` hosts the GlusterFS infrastructure,
`Subnet B 10.1.0.0/16` contains a pool of Azure Batch compute nodes, and
`Subnet C 10.2.1.0/24` contains other Azure virtual machines. No resource
in `Subnet B` or `Subnet C` is required for the Batch Shipyard provisioned
filesystem to work, it is just to illustrate that other resources can
access the filesystem within the same virtual network if configured to do
so.

If your configuration is NFS instead, then the above illustration would be
simplified to a single virtual machine (`Virtual Machine A` in
`Subnet A 10.0.0.0/24`) only. However, other non-GlusterFS specific
concepts still apply regarding other Azure resources.

The storage cluster depicted is a 2-node GlusterFS distributed file
system with attached disks. Each node has a number of managed disks attached
to it arranged in a RAID-0 disk array. The array (and ultimately the
filesystem sitting on top of the disk array) holds the GlusterFS brick for
the virtual machine. Because the managed disks are backed to Azure Storage
LRS (locally redundant storage), there is no practical need to for mirroring
or striping at this level.

For each Azure Virtual Machine hosting a brick of the GlusterFS server, two
IP addresses are provisioned, in addition to a fully qualified domain name
that resolves to the public IP address. The public IP address allows for
external clients to SSH into the virtual machine for diagnostic, maintenance,
debugging, data transfer and other tasks. The SSH inbound network security
rule can be tightened according to your requirements in the configuration
file. Additionally, inbound network rules can be applied to allow the
filesystem to be mounted externally as well. The private IP address is an
address that is only internally routable on the virtual network. Resources
that are on the virtual network will/should use these IP addresses for access
to the filesystem.

And finally, when provisioning GlusterFS servers, rather than NFS servers,
Batch Shipyard automatically places the virtual machines in an availability
set along with maximally spreading virtual machines across update and fault
domains. Single instance NFS servers will not be placed in an availbility
set, however, if using a premium storage virtual machine size along with
all premium disks, then you may qualify for
[single instance SLA](https://azure.microsoft.com/en-us/support/legal/sla/virtual-machines).

## Configuration and Usage Documentation
Please see [this page](15-batch-shipyard-configuration-fs.md) for a full
explanation of each remote filesystem and storage cluster configuration
option. Please see [this page](20-batch-shipyard-usage.md) for documentation
on `fs` command usage.

You can find information regarding User Subscription Batch accounts and how
to create them at this
[blog post](https://docs.microsoft.com/en-us/azure/batch/batch-account-create-portal#user-subscription-mode).

## Sample Recipes
Sample recipes for RemoteFS storage clusters of NFS and GlusterFS types can
be found in the
[recipes](https://github.com/Azure/batch-shipyard/tree/master/recipes) area.
