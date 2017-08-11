# Batch Shipyard Pool Configuration
This page contains in-depth details on how to configure the pool
json file for Batch Shipyard.

## Schema
The pool schema is as follows:

```json
{
    "pool_specification": {
        "id": "dockerpool",
        "vm_configuration": {
            "platform_image": {
                "publisher": "Canonical",
                "offer": "UbuntuServer",
                "sku": "16.04-LTS"
            },
            "custom_image": {
                "image_uris": [
                    "https://mystorageaccount.blob.core.windows.net/myvhds/mycustomimg.vhd"
                ],
                "node_agent": "batch.node.ubuntu 16.04"
            }
        },
        "vm_size": "STANDARD_H16R",
        "vm_count": {
            "dedicated": 8,
            "low_priority": 0
        },
        "resize_timeout": "00:20:00",
        "max_tasks_per_node": 1,
        "node_fill_type": "pack",
        "autoscale": {
            "evaluation_interval": "00:05:00",
            "scenario": {
                "name": "active_tasks",
                "maximum_vm_count": {
                    "dedicated": 16,
                    "low_priority": 8
                },
                "node_deallocation_option": "taskcompletion",
                "sample_lookback_interval": "00:10:00",
                "required_sample_percentage": 70,
                "bias_last_sample": true,
                "bias_node_type": "low_priority"
            },
            "formula": ""
        },
        "inter_node_communication_enabled": true,
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
        "resource_files": [
            {
                "file_path": "",
                "blob_source": "",
                "file_mode": ""
            }
        ],
        "virtual_network": {
            "name": "myvnet",
            "resource_group": "vnet-in-another-rg",
            "create_nonexistant": false,
            "address_space": "10.0.0.0/16",
            "subnet": {
                "name": "subnet-for-batch-vms",
                "address_prefix": "10.0.0.0/20"
            }
        },
        "ssh": {
            "username": "docker",
            "expiry_days": 30,
            "ssh_public_key": "/path/to/rsa/publickey.pub",
            "ssh_public_key_data": "ssh-rsa ...",
            "ssh_private_key": "/path/to/rsa/privatekey",
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
* (required) `vm_configuration` specifies the image configuration for the
VM. Either `platform_image` or `custom_image` must be specified. You cannot
specify both. If using a custom image, please see the
[Custom Image Guide](63-batch-shipyard-custom-images.md) first.
  * (required for platform image) `platform_image` defines the Marketplace
    platform image to use:
    * (required for platform image) `publisher` is the publisher name of the
      Marketplace VM image.
    * (required for platform image) `offer` is the offer name of the
      Marketplace VM image.
    * (required for platform image) `sku` is the sku name of the Marketplace
      VM image.
  * (required for custom image) `custom_image` defines the custom image to
    use:
    * (required for custom image) `image_uris` defines a list of page blob
      VHDs to use for the pool. These should be bare URLs without SAS keys.
    * (required for custom image) `node_agent` is the node agent sku id to
      use with this custom image. You can view supported base images and
      their node agent sku ids with the `pool listskus` command.
* (required) `vm_size` is the
[Azure Virtual Machine Instance Size](https://azure.microsoft.com/en-us/pricing/details/virtual-machines/).
Please note that not all regions have every VM size available.
* (required) `vm_count` is the number of compute nodes to allocate. You may
specify a mixed number of compute nodes in the following properties:
  * (optional) `dedicated` is the number of dedicated compute nodes to
    allocate. These nodes cannot be pre-empted. The default value is `0`.
  * (optional) `low_priority` is the number of low-priority compute nodes to
    allocate. These nodes may be pre-empted at any time. Workloads that
    are amenable to `low_priority` nodes are those that do not have strict
    deadlines for pickup and completion. Optimally, these types of jobs would
    checkpoint their progress and be able to recover when re-scheduled.
    The default value is `0`.
* (optional) `resize_timeout` is the amount of time allowed for resize
operations (note that creating a pool resizes from 0 to the specified number
of nodes). The format for this property is a timedelta with a string
representation of "d.HH:mm:ss". "HH:mm:ss" is required, but "d" is optional,
if specified. If not specified, the default is 15 minutes.
* (optional) `max_tasks_per_node` is the maximum number of concurrent tasks
that can be running at any one time on a compute node. This defaults to a
value of 1 if not specified. The maximum value for the property that Azure
Batch will accept is `4 x <# cores per compute node>`. For instance, for a
`STANDARD_F2` instance, because the virtual machine has 2 cores, the maximum
allowable value for this property would be `8`.
* (optional) `node_fill_type` is the task scheduling compute node fill type
policy to apply. `pack`, which is the default, attempts to pack the
maximum number of tasks on a node (controlled through `max_tasks_per_node`
before scheduling tasks to another node). `spread` will schedule tasks
evenly across compute nodes before packing.
* (optional) `autoscale` designates the autoscale settings for the pool. If
specified, the `vm_count` becomes the minimum number of virtual machines for
each node type for `scenario` based autoscale.
  * (optional) `evaluation_interval` is the time interval between autoscale
    evaluations performed by the service. The format for this property is a
    timedelta with a string representation of "d.HH:mm:ss". "HH:mm:ss" is
    required, but "d" is optional, if specified. If not specified, the default
    is 15 minutes. The smallest value that can be specified is 5 minutes.
  * (optional) `scenario` is a pre-set autoscale scenario where a formula
    will be generated with the parameters specified within this property.
    * (required) `name` is the autoscale scenario name to apply. Valid
      values are `active_tasks`, `pending_tasks`, `workday`,
      `workday_with_offpeak_max_low_priority`, `weekday`, `weekend`.
      Please see the [autoscale guide](30-batch-shipyard-autoscale.md) for
      more information about these scenarios.
    * (required) `maximum_vm_count` is the maximum number of compute nodes
      that can be allocated from an autoscale evaluation. It is useful to
      have these limits in place as to control the top-end scale of the
      autoscale scenario. Specifying a negative value for either of the
      following properties will result in effectively no maximum limit.
      * (optional) `dedicated` is the maximum number of dedicated compute
        nodes that can be allocated.
      * (optional) `low_priority` is the maximum number of low priority
        compute nodes that can be allocated.
    * (optional) `node_deallocation_option` is the node deallocation option
      to apply. When a pool is resized down and a node is selected for
      removal, what action is performed for the running task is specified
      with this option. The valid values are: `requeue`, `terminate`,
      `taskcompletion`, and `retaineddata`. The default is `taskcompletion`.
      Please see [this doc](https://docs.microsoft.com/en-us/azure/batch/batch-automatic-scaling#variables) for more information.
    * (optional) `sample_lookback_interval` is the time interval to lookback
      for past history for certain scenarios such as autoscale based on
      active and pending tasks. The format for this property is a timedelta
      with a string representation of "d.HH:mm:ss". "HH:mm:ss" is required,
      but "d" is optional, if specified. If not specified, the default is
      10 minutes.
    * (optional) `required_sample_percentage` is the required percentage of
      samples that must be present during the `sample_lookback_interval`.
      If not specified, the default is 70.
    * (optional) `bias_last_sample` will bias the autoscale scenario, if
      applicable, to use the last sample during history computation. This can
      be enabled to more quickly respond to changes in history with respect
      to averages. The default is `true`.
    * (optional) `bias_node_type` will bias the the autoscale scenario, if
      applicable, to favor one type of node over the other when making a
      decision on how many of each node to allocate. The default is `auto`
      or equal weight to both `dedicated` and `low_priority` nodes. Valid
      values are `null` (or omitting the property), `dedicated`, or
      `low_priority`.
    * (optional) `rebalance_preemption_percentage` will rebalance the compute
      nodes to bias for dedicated nodes when the pre-empted node count reaches
      the indicated threshold percentage of the total current dedicated and
      low priority nodes. The default is `null` or no rebalancing is performed.
  * (optional) `formula` is a custom autoscale formula to apply to the pool.
    If both `formula` and `scenario` are specified, then `formula` is used.
* (optional) `inter_node_communication_enabled` designates if this pool is set
up for inter-node communication. This must be set to `true` for any containers
that must communicate with each other such as MPI applications. This
property cannot be enabled if there are positive values for both
`dedicated and `low_priority` compute nodes specified above. This property
will be force enabled if peer-to-peer replication is enabled.
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
* (optional) `resource_files` is an array of resource files that should be
downloaded as part of the compute node's preparation. Each array entry
contains the following information:
  * `file_path` is the path within the node prep task working directory to
    place the file on the compute node. This directory can be referenced
    by the `$AZ_BATCH_NODE_STARTUP_DIR/wd` path.
  * `blob_source` is an accessible HTTP/HTTPS URL. This need not be an Azure
    Blob Storage URL.
  * `file_mode` if the file mode to set for the file on the compute node.
    This is optional.
* (optional) `virtual_network` is the property for specifying an ARM-based
virtual network resource for the pool. This is only available for
UserSubscription Batch accounts.
  * (required) `name` is the name of the virtual network
  * (optional) `resource_group` containing the virtual network. If
    the resource group name is not specified here, the `resource_group`
    specified in the `batch` credentials will be used instead.
  * (optional) `create_nonexistant` specifies if the virtual network and
    subnet should be created if not found. If not specified, this defaults
    to `false`.
  * (required if creating, optional otherwise) `address_space` is the
    allowed address space for the virtual network.
  * (required) `subnet` specifies the subnet properties.
    * (required) `name` is the subnet name.
    * (required) `address_prefix` is the subnet address prefix to use for
      allocation Batch compute nodes to. The maximum number of compute nodes
      a subnet can support is 4096 which maps roughly to a CIDR mask of
      20-bits.
* (optional) `ssh` is the property for creating a user to accomodate SSH
sessions to compute nodes. If this property is absent, then an SSH user is not
created with pool creation. If you are running Batch Shipyard on Windows,
please refer to [these instructions](85-batch-shipyard-ssh-docker-tunnel.md#ssh-keygen)
on how to generate an SSH keypair for use with Batch Shipyard.
  * (required) `username` is the user to create on the compute nodes.
  * (optional) `expiry_days` is the number of days from now for the account on
    the compute nodes to expire. The default is 30 days from invocation time.
  * (optional) `ssh_public_key` is the path to an existing SSH public key to
    use. If not specified, an RSA public/private keypair will be automatically
    generated if `ssh-keygen` or `ssh-keygen.exe` can be found on the `PATH`.
    This option cannot be specified with `ssh_public_key_data`.
  * (optional) `ssh_public_key_data` is the raw RSA public key data in OpenSSH
    format, e.g., a string starting with `ssh-rsa ...`. Only one key may be
    specified. This option cannot be specified with `ssh_public_key`.
  * (optional) `ssh_private_key` is the path to an existing SSH private key
    to use against either `ssh_public_key` or `ssh_public_key_data` for
    connecting to compute nodes. This option should only be specified
    if either `ssh_public_key` or `ssh_public_key_data` are specified.
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
* (optional) `gpu` property defines additional information for NVIDIA
GPU-enabled VMs. If not specified, Batch Shipyard will automatically download
the driver for the `vm_size` specified.
  * `nvidia_driver` property contains the following required members:
    * `source` is the source url to download the driver.
* (optional) `additional_node_prep_commands` is an array of additional commands
to execute on the compute node host as part of node preparation. This can
be empty or omitted.

## Full template
A full template of a credentials file can be found
[here](../config\_templates/pool.json). Note that this template cannot
be used as-is and must be modified to fit your scenario.
