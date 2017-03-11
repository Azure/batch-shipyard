# Batch Shipyard Pool Configuration
This page contains in-depth details on how to configure the pool
json file for Batch Shipyard.

## Schema
The pool schema is as follows:

```json
{
    "pool_specification": {
        "id": "dockerpool",
        "vm_size": "STANDARD_A9",
        "vm_count": 10,
        "max_tasks_per_node": 1,
        "inter_node_communication_enabled": true,
        "publisher": "OpenLogic",
        "offer": "CentOS-HPC",
        "sku": "7.1",
        "reboot_on_start_task_failed": true,
        "block_until_all_global_resources_loaded": true,
        "transfer_files_on_pool_creation": false,
        "input_data": {
            "azure_batch": [
                {
                    "job_id": "jobonanotherpool",
                    "task_id": "mytask",
                    "include": ["wd/*.dat"],
                    "exclude": ["*.txt"],
                    "destination": "$AZ_BATCH_NODE_SHARED_DIR/jobonanotherpool"
                }
            ],
            "azure_storage": [
                {
                    "storage_account_settings": "mystorageaccount",
                    "container": "poolcontainer",
                    "include": ["pooldata*.bin"],
                    "destination": "$AZ_BATCH_NODE_SHARED_DIR/pooldata",
                    "blobxfer_extra_options": null
                }
            ]
        },
        "ssh": {
            "username": "docker",
            "expiry_days": 7,
            "ssh_public_key": null,
            "generate_docker_tunnel_script": true,
            "generated_file_export_path": null,
            "hpn_server_swap": false
        },
        "gpu": {
            "nvidia_driver": {
                "source": "https://some.url"
            }
        },
        "additional_node_prep_commands": [
        ]
    }
}
```

The `pool_specification` property has the following members:
* (required) `id` is the compute pool ID.
* (required) `vm_size` is the
[Azure Virtual Machine Instance Size](https://azure.microsoft.com/en-us/pricing/details/virtual-machines/).
Please note that not all regions have every VM size available.
* (required) `vm_count` is the number of compute nodes to allocate.
* (optional) `max_tasks_per_node` is the maximum number of concurrent tasks
that can be running at any one time on a compute node. This defaults to a
value of 1 if not specified.
* (optional) `inter_node_communication_enabled` designates if this pool is set
up for inter-node communication. This must be set to `true` for any containers
that must communicate with each other such as MPI applications. This property
will be force enabled if peer-to-peer replication is enabled.
* (required) `publisher` is the publisher name of the Marketplace VM image.
* (required) `offer` is the offer name of the Marketplace VM image.
* (required) `sku` is the sku name of the Marketplace VM image.
* (optional) `reboot_on_start_task_failed` allows Batch Shipyard to reboot the
compute node in case there is a transient failure in node preparation (e.g.,
network timeout, resolution failure or download problem). This defaults to
`false`.
* (optional) `block_until_all_global_resources_loaded` will block the node
from entering ready state until all Docker images are loaded. This defaults
to `true`.
* (optional) `transfer_files_on_pool_creation` will ingress all `files`
specified in the `global_resources` section of the configuration json when
the pool is created. If files are to be ingressed to Azure Blob or File
Storage, then data movement operations are overlapped with the creation of the
pool. If files are to be ingressed to a shared file system on the compute
nodes, then the files are ingressed after the pool is created and the shared
file system is ready. Files can be ingressed to both Azure Blob Storage and a
shared file system during the same pool creation invocation. If this property
is set to `true` then `block_until_all_global_resources_loaded` will be force
disabled. If omitted, this property defaults to `false`.
* (optional) `input_data` is an object containing data that should be
ingressed to all compute nodes as part of node preparation. It is
important to note that if you are combining this action with `files` and
are ingressing data to Azure Blob or File storage as part of pool creation,
that the blob containers or file shares defined here will be downloaded as
soon as the compute node is ready to do so. This may result in the blob
container/blobs or file share/files not being ready in time for the
`input_data` transfer. It is up to you to ensure that these two operations do
not overlap. If there is a possibility of overlap, then you should ingress
data defined in `files` prior to pool creation and disable the option above
`transfer_files_on_pool_creation`. This object currently supports
`azure_batch` and `azure_storage` as members.
  * `azure_batch` contains the following members:
    * (required) `job_id` the job id of the task
    * (required) `task_id` the id of the task to fetch files from
    * (optional) `include` is an array of include filters
    * (optional) `exclude` is an array of exclude filters
    * (required) `destination` is the destination path to place the files
  * `azure_storage` contains the following members:
    * (required) `storage_account_settings` contains a storage account link
      as defined in the credentials json.
    * (required) `container` or `file_share` is required when downloading
      from Azure Blob Storage or Azure File Storage, respectively.
      `container` specifies which container to download from for Azure Blob
      Storage while `file_share` specifies which file share to download from
      for Azure File Storage. Only one of these properties can be specified
      per `data_transfer` object.
    * (optional) `include` property defines an optional include filter.
      Although this property is an array, it is only allowed to have 1
      maximum filter.
    * (required) `destination` property defines where to place the
      downloaded files on the host file system. Please note that you should
      not specify a destination that is on a shared file system. If you
      require ingressing to a shared file system location like a GlusterFS
      volume, then use the global configuration `files` property and the
      `data ingress` command.
    * (optional) `blobxfer_extra_options` are any extra options to pass to
      `blobxfer`.
* (optional) `ssh` is the property for creating a user to accomodate SSH
sessions to compute nodes. If this property is absent, then an SSH user is not
created with pool creation.
  * (required) `username` is the user to create on the compute nodes.
  * (optional) `expiry_days` is the number of days from now for the account on
    the compute nodes to expire. The default is 30 days from invocation time.
  * (optional) `ssh_public_key` is the path to an existing SSH public key to
    use. If not specified, an RSA public/private keypair will be automatically
    generated only on Linux. If this is `null` or not specified on Windows,
    the SSH user is not created.
  * (optional) `generate_docker_tunnel_script` property directs script to
    generate an SSH tunnel script that can be used to connect to the remote
    Docker engine running on a compute node. This script can only be used on
    non-Windows systems.
  * (optional) `generated_file_export_path` is the path to export the
    generated RSA keypair and docker tunnel script to. If omitted, the
    current directory is used.
  * (experimental) `hpn_server_swap` property enables an OpenSSH server with
    [HPN patches](https://www.psc.edu/index.php/using-joomla/extensions/templates/atomic/636-hpn-ssh)
    to be swapped with the standard distribution OpenSSH server. This is not
    supported on all Linux distributions and may be force disabled.
* (required for `STANDARD_NV` instances, optional for `STANDARD_NC` instances)
`gpu` property defines additional information for NVIDIA GPU-enabled VMs:
  * `nvidia_driver` property contains the following required members:
    * `source` is the source url to download the driver.
* (optional) `additional_node_prep_commands` is an array of additional commands
to execute on the compute node host as part of node preparation. This can
be empty or omitted.

## Full template
An full template of a credentials file can be found
[here](../config\_templates/pool.json). Note that this template cannot
be used as-is and must be modified to fit your scenario.
