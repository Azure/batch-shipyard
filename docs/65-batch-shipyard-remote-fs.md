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
* Support for [btrfs](https://en.wikipedia.org/wiki/Btrfs),
[XFS](https://en.wikipedia.org/wiki/XFS), ext4, ext3 and ext2 filesystems
* Automatic disk array construction via RAID-0 through btrfs or Linux
software RAID (mdadm)
* Consistent private IP address allocation per virtual machine and virtual
machine to disk mapping
* Automatic network security rule configuration based on file server type,
if requested
* Automatic placement in an availability set for GlusterFS virtual machines
* Support for [accelerated networking](https://docs.microsoft.com/azure/virtual-network/create-vm-accelerated-networking-cli)
* Automatic boot diagnostics enablement and support for serial console access
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

## Mental Model
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
[single instance SLA](https://azure.microsoft.com/support/legal/sla/virtual-machines).

## Configuration
In order to create storage clusters, there are a few configuration changes
that must be made to enable this feature.

### Azure Active Directory Authentication Required
Azure Active Directory authentication is required to create storage clusters.
Additionally, if leveraging integration features with Batch pools, then the
virtual network shared between the storage cluster and the Batch pool must
be the same.

Your service principal requires at least `Contributor` role permission in
order to create the resources required for the storage cluster.

#### Credentials Configuration
The following is an example for Azure Active Directory authentication in the
credentials configuration.

```yaml
credentials:
  # management settings required with aad auth
  management:
    aad:
      # valid aad settings (or at the global level)
    subscription_id: # subscription id required
  # ... other required settings
```

### RemoteFS Configuration
Please see [this page](15-batch-shipyard-configuration-fs.md) for a full
explanation of each remote filesystem and storage cluster configuration
option.

The following will step through and explain the major configuration
portions. The RemoteFS configuration file has four top-level properties:

```yaml
remote_fs:
  resource_group: # resource group for all resources, can be overridden
  location: # Azure region for all storage cluster resources
  managed_disks:
    # disk settings
  storage_clusters:
    # storage cluster settings
```

It is important to specify a location that is appropriate for your storage
cluster and if joining to a Batch pool, must be within the same region.

#### Managed Disks Configuration
The `managed_disks` section describes disks to be created for use with
storage clusters.

```yaml
  managed_disks:
    resource_group: # optional resource group just for the disks
    # premium disks have provisioned IOPS and can provide higher throughput
    # and lower latency with consistency. If selecting premium disks,
    # you must use a premium storage compatible vm_size.
    premium: true
    disk_size_gb: # size of the disk, please see Azure Manage Disk docs
    disk_names:
      - # list of disk names
```

#### Storage Cluster Configuration
The `storage_clusters` section describes one or more storage clusters to
create and manage.

```yaml
  storage_clusters:
    # unique name of the storage cluster, this is the "storage cluster id"
    mystoragecluster:
      resource_group: # optional resource group just for the storage cluster
      hostname_prefix: # hostname prefix and prefix for all resources created
      ssh:
        # ssh settings
      public_ip:
        enabled: # true or false for enabling public ip. If public ip is not
                 # enabled, then it is only accessible via the private network.
        static: # true or false if public ip should be static
      virtual_network:
        # virtual network settings. If joining to a Batch pool, ensure that
        # the virtual network resides in the same region and subscription
        # as the Batch account. It is recommended that the storage cluster
        # is in a different subnet than that of the Batch pool.
      network_security:
        # network security rules, only "ssh" is required. All other settings
        # are for external access and not needed for joining with Batch pools
        # as traffic remains private/internal only for that scenario.
      file_server:
        type: # nfs or glusterfs
        mountpoint: # the mountpoint on the storage cluster nodes
        mount_options:
          - # fstab mount options in list format
        server_options:
          glusterfs: # this section is only needed for "glusterfs" type
            transport: tcp # tcp is only supported for now
            volume_name: # name of the gluster volume
            volume_type: # type of volume to create. This must be compatible
                         # with the number of bricks.
            # other key:value pair tuning options can be specified here
          nfs: # this section is only needed for "nfs" type
            # key:value (where value is a list) mapping of /etc/exports options
        samba:
          # optional section, if samba server setup is required
      vm_count: # 1 for nfs, 2+ for glusterfs
      vm_size: # Azure VM size to use. This must a premium storage compatible
               # size if using premium managed disks.
      fault_domains: # optional tuning for the number of fault domains
      accelerated_networking: # true to enable accelerated networking
      vm_disk_map:
        # cardinal mapping of VMs to their disk arrays, e.g.:
        '0': # note that this key must be a string
          disk_array:
            - # list of disks in this disk array
          filesystem: # filesystem to use, see documentation on available kinds
          raid_level: # this should be set to 0 if disk_array has more than 1
                      # disk. If disk_array has only 1 disk, then this property
                      # should be omitted.
      prometheus:
        # optional monitoring settings
```

### Batch Pool Integration
If you wish to use your storage cluster in conjunction with a Batch pool, then
you will need to modify the credentials, global, pool, and jobs configuration
files.

#### Credentials Configuration
Azure Active Directory authentication for Batch is required for joining a
storage cluster with a [Batch pool](64-batch-shipyard-byovnet.md).

```yaml
credentials:
  # batch aad settings required if monitoring batch pools
  batch:
    aad:
      # valid aad settings (or at the global level)
    account_service_url: # valid batch service url
    resource_group: # batch account resource group
  management:
    aad:
      # valid aad settings (or at the global level)
    subscription_id: # subscription id required
  # ... other required settings
```

#### Global Configuration
You must specify the storage cluster under `global_resources` such that
bound Batch pools will provision the correct software to mount the storage
cluster.

```yaml
# ... other global configuration settings
global_resources:
  # ... other global resources settings
  volumes:
    shared_data_volumes:
      mystoragecluster: # this name must match exactly with the storage cluster
                        # id from the RemoteFS configuration that you intend
                        # to link
        volume_driver: storage_cluster
        container_path: # that path to mount this storage cluster in
                        # containers when jobs/tasks execute
        mount_options: # optional fstab mount options
        bind_options: # optional bind options to the container, default is "rw"
```

#### Pool Configuration
The pool configuration file must specify a valid virtual network. Because
of this requirement, you must use Azure Active Directory authentication for
Batch.

```yaml
pool_specification:
  # ... other pool settings
  virtual_network:
    # virtual network settings must have the same virtual network as the
    # RemoteFS configuration. However, it is strongly recommended to have
    # the Batch pool compute nodes reside in a different subnet.
```

#### Jobs Configuration
The jobs configuration must refer to the shared data volume such that
it understands to mount the volume into the container for the task or all
tasks under a job.

```yaml
job_specifications:
  - id: # job id
    shared_data_volumes:
      # this name must match exactly with the global_resources
      # shared_data_volumes name. If specified at the job level, then all
      # tasks under the job will mount this volume.
      - mystoragecluster
    # ... other job settings
    tasks:
      - shared_data_volumes:
          - # storage cluster can be specified for fine grained control at
            # a per task level
        # ... other task settings
```

## Usage Documentation
The workflow for creating a storage cluster is first creating the managed
disks, then the storage cluster itself. Below is an example command usage.

```shell
# create managed disks
shipyard fs disks add

# create storage cluster
shipyard fs cluster add <storage-cluster-id>
```

If there were provisioning errors during `fs cluster add` but the provisioning
had not yet reached the VM creation phase, you can remove the orphaned
resources with:

```shell
# clean up a failed provisioning that did not reach VM creation
shipyard fs cluster del <storage-cluster-id> --generate-from-prefix
```

If any VMs were created and the provisioning failed after that, you can
delete normally (without `--generate-from-prefix`).


After there is no need for the storage cluster, you can either suspend
the storage cluster or delete it. Note that suspending a glusterfs
storage cluster is considered experimental.

```shell
# suspend a storage cluster
shipyard fs cluster suspend <storage-cluster-id>

# restart a suspended storage cluster
shipyard fs cluster start <storage-cluster-id>

# delete a storage cluster
shipyard fs cluster del <storage-cluster-id>
```

Please see [this page](20-batch-shipyard-usage.md) for detailed documentation
on `fs` command usage.

### Usage with Batch Pools
If joining to a Batch pool, the storage cluster must be created first.
After which, commands such as `pool add` and `jobs add` should work
normally with the storage cluster mounted into containers if configuration
is correct.

## Sample Recipes
Sample recipes for RemoteFS storage clusters of NFS and GlusterFS types can
be found in the
[recipes](https://github.com/Azure/batch-shipyard/tree/master/recipes) area.
