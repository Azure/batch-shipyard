# RemoteFS-GlusterFS+BatchPool
This recipe shows how to provision and link a Batch Pool with a GlusterFS
storage cluster.

## Configuration
Please see refer to this [set of sample configuration files](./config) for
this recipe.

### Credentials Configuration
The credentials configuration should have `management` Azure Active Directory
credentials defined along with a valid storage account. The `management`
section can be supplied through environment variables instead if preferred.

Additionally, `batch` Azure Active Directory credentials with a valid
[UserSubscription Batch account](https://docs.microsoft.com/en-us/azure/batch/batch-account-create-portal#user-subscription-mode)
should be supplied.

### FS Configuration and GlusterFS storage cluster creation
Please follow the explanations as presented in vanilla
[RemoteFS-GlusterFS recipe](../RemoteFS-GlusterFS). The RemoteFS storage
cluster should be created first prior to creating the Batch pool.

### Pool Configuration
Pool configuration would follow like most other standard non-linked pools
except you will need a virtual network specification which would be the
same virtual network hosting the RemoteFS file servers. The
`virtual_network` property will require:
* `name` is the name of the virtual network to use
* `resource_group` is the resource group name containing the virtual network
* `address_space` is the address space of the virtual network
* `subnet` is the subnet for the compute nodes of this pool
  * `name` is the subnet name
  * `address_prefix` is the set of addresses for the batch nodes. This subnet
    space must be large enough to accommodate the number of compute nodes
    being allocated. Do not share subnets between RemoteFS storage clusters
    and Batch compute nodes.

### Global Configuration
The global configuration is where the RemoteFS storage cluster is linked
to the Batch pool through `shared_data_volumes` in `volumes` under
`global_resources`. `shared_data_volumes` dictionary would have a key
that is the storage cluster id key in FS configuration. For this example,
this would be `mystoragecluster`. This property contains the following
members:
* `volume_driver` should be set to `storage_cluster` to link the RemoteFS
storage cluster to our Batch pool
* `container_path` is the container path to map the storage cluster mountpoint
* `mount_options` are any additional mount options to pass and can be empty
or unspecified

### Batch Shipyard Commands
After you have created your RemoteFS GlusterFS storage cluster via
`fs cluster add`, then you can issue `pool add` with the above config
which will create a Batch pool and automatically link your GlusterFS
storage cluster against your Batch pool. You can then use data placed on
the storage cluster in your containerized workloads.
