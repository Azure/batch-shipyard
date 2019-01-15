# Slurm+NFS
This recipe shows how to orchestrate a Slurm on Batch cluster with a single
Batch pool providing compute node VMs for Slurm workloads along with a shared
NFS filesystem.

## Configuration
Please see refer to this [set of sample configuration files](./config) for
this recipe.

### Credentials Configuration
The credentials configuration should have `management` Azure Active Directory
credentials defined along with a valid storage account. The `management`
section can be supplied through environment variables instead if preferred.
The `batch` section should also be populated which associates all of the
Batch pools used by Slurm partitions. Additionally, a `slurm` section with the
`db_password` must be defined.

### Pool Configuration
The pool configuration can be modified as necessary for the requisite OS
and other tooling that should be installed. The `vm_count` should be kept
as `0` for both `dedicated` and `low_priority` during the initial allocation
as Slurm's elastic cloud bursting will size the pools appropriately.

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
to apply for SSH and external NFSv4 client mounts. If no NFSv4 clients
external to the virtual network are needed, then the entire `nfs` security
rule can be omitted.
* `file_server` options such as `mountpoint` and `mount_options` should be
modified to your scenario. Type should not be modified from `nfs`.
* `vm_size` can be modified for the file server depending upon your scenario.
If using premium managed disks, then a premium VM size must be selected
here.
* `vm_disk_map` contains all of the disks used for each VM. For `nfs`, there
is only a single VM, thus all disks should be mapped in the `"0"` entry.

### Slurm Configuration
The Slurm configuration should include the appropriate location and virtual
network settings for the controller and login nodes, in addition to defining
the appropriate elastic partitions. Please see the
[Slurm on Batch](../../docs/69-batch-shipyard-slurm.md) guide and the
[Slurm configuration](../../docs/18-batch-shipayrd-slurm.md) document for more
information on each option.

### Commands to orchestrate the Slurm cluster
After modifying the configuration files as required, you can orchestrate
the entire Slurm cluster creation with `slurm cluster orchestrate`. The
`orchestrate` command wraps up the NFS disk allocation (`fs disks add`), NFS
file server creation (`fs cluster add`), Batch pool allocation (`pool add`),
and Slurm controller/login creation (`slurm cluster create`) into one command.
The commands can be invoked separately if desired. The following assumes the
configuration files are in the current working directory.

```shell
# ensure all configuration files are in the appropriate directory
export SHIPYARD_CONFIGDIR=.

# orchestrate the Slurm cluster
./shipyard slurm cluster orchestrate --storage-cluster-id nfs -y
```

You can log into the login nodes by issuing the command:

```shell
./shipyard slurm ssh login
```

which will default to logging into the first login node (since this cluster
only has one login node, it is the only possible node to log in to).

There you will be able to run your Slurm commands such as `sbatch`, `squeue`,
`salloc`, `srun`, etc..

To delete the Slurm cluster:

```shell
# delete the Batch pool providing Slurm compute nodes
./shipyard pool del -y

# delete the Slurm controller and login nodes
./shipyard slurm cluster destroy -y

# delete the RemoteFS shared file system
./shipyard fs cluster del nfs -y --delete-data-disks
```
