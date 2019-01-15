# RemoteFS-GlusterFS
This recipe shows how to create an GlusterFS storage cluster with multiple
premium storage VMs with multiple premium disks.

## Configuration
Please see refer to this [set of sample configuration files](./config) for
this recipe.

### Credentials Configuration
The credentials configuration should have `management` Azure Active Directory
credentials defined along with a valid storage account. The `management`
section can be supplied through environment variables instead if preferred.

### FS Configuration
The remote fs configuration file requires modification. Properties to
modify are:
* `resource_group` all resource groups should be modified to fit your
scenario.
* `location` should be modified to the Azure region where you would like
the storage cluster created. If linking against Azure Batch compute nodes,
it should be in the same region as your Azure Batch account.
* `managed_disks` should be modified for the number, size and type of
managed disks to allocate for the file server.
* `storage_clusters` should be modified to have a unique name instead of
`mystoragecluster` if you prefer.
* `hostname_prefix` should be modified to your perferred resource name
prefix.
* `virtual_network` should be modified for the address prefixes and subnet
properties that you prefer.
* `network_security` should be modified for inbound network security rules
to apply for SSH and external glusterfs client mounts. If no glusterfs clients
external to the virtual network are needed, then the entire `glusterfs`
security rule can be omitted.
* `file_server` options such as `mountpoint` and `mount_options` should be
modified to your scenario. Type should not be modified from `glusterfs`.
`server_options` can be modified for additional performance tuning options
or changing the gluster volume name.
* `vm_count` should match the number of VMs to provision for GlusterFS
storage cluster scale out. This must be `2` or greater for GlusterFS.
* `vm_size` can be modified for the file server depending upon your scenario.
If using premium managed disks, then a premium VM size must be selected
here.
* `vm_disk_map` contains all of the disks used for each VM. For `glusterfs`,
there are at least 2 VMs, thus disks should be mapped in their respective
cardinal entry.

### Commands to create the GlusterFS storage cluster
After modifying the configuration files as required, you can orchestrate
the entire GlusterFS shared file system with `fs cluster orchestrate`. The
`orchestrate` command wraps up the disk allocation (`fs disks add`) and file
server creation (`fs cluster add`) into one command. The commands can be
invoked separately if desired. The following assumes the configuration files
are in the current working directory.

```shell
SHIPYARD_CONFIGDIR=. ./shipyard fs cluster orchestrate mystoragecluster
```

This assumes that the storage cluster id is `mystoragecluster`. After the
file server is provisioned, you can login to perform administrative tasks
through SSH with:

```shell
SHIPYARD_CONFIGDIR=. ./shipyard fs cluster ssh mystoragecluster
```

This will SSH into the first VM in the storage cluster.

To delete the file server, you can issue:

```shell
# keep the data disks, resource group and virtual network
SHIPYARD_CONFIGDIR=. ./shipyard fs cluster del mystoragecluster

# keep the resource group and virtual network
SHIPYARD_CONFIGDIR=. ./shipyard fs cluster del mystoragecluster --delete-data-disks

# delete everything in the resource group
SHIPYARD_CONFIGDIR=. ./shipyard fs cluster del mystoragecluster --delete-resource-group
```

If you encounter a partial failure during creation or deletion and the
virtual machine resources can no longer be enumerated, you can issue:

```shell
SHIPYARD_CONFIGDIR=. ./shipyard fs cluster del mystoragecluster --generate-from-prefix
```

Which would attempt to delete resources based off the `fs.yaml` hostname
prefix (resources) specification.
