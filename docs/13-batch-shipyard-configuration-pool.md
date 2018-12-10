# Batch Shipyard Pool Configuration
This page contains in-depth details on how to configure the pool
configuration file for Batch Shipyard.

## Schema
The pool schema is as follows:

```yaml
pool_specification:
  id: batch-shipyard-pool
  vm_configuration:
    platform_image:
      publisher: Canonical
      offer: UbuntuServer
      sku: 16.04-LTS
      version: latest
      native: false
      license_type: null
    custom_image:
      arm_image_id: /subscriptions/<subscription_id>/resourceGroups/<resource_group>/providers/Microsoft.Compute/images/<image_name>
      node_agent: <node agent sku id>
      native: false
      license_type: null
  vm_size: STANDARD_D2_V2
  vm_count:
    dedicated: 4
    low_priority: 8
  max_tasks_per_node: 1
  resize_timeout: 00:20:00
  node_fill_type: pack
  autoscale:
    evaluation_interval: 00:15:00
    scenario:
      name: active_tasks
      maximum_vm_count:
        dedicated: 16
        low_priority: 8
      maximum_vm_increment_per_evaluation:
        dedicated: 4
        low_priority: -1
      node_deallocation_option: taskcompletion
      sample_lookback_interval: 00:10:00
      required_sample_percentage: 70
      bias_last_sample: true
      bias_node_type: low_priority
      rebalance_preemption_percentage: 50
      time_ranges:
        weekdays:
          start: 1
          end: 5
        work_hours:
          start: 8
          end: 17
    formula: null
  inter_node_communication_enabled: false
  per_job_auto_scratch: false
  reboot_on_start_task_failed: false
  attempt_recovery_on_unusable: false
  upload_diagnostics_logs_on_unusable: true
  block_until_all_global_resources_loaded: true
  transfer_files_on_pool_creation: false
  input_data:
    azure_batch:
    - destination: $AZ_BATCH_NODE_SHARED_DIR/jobonanotherpool
      exclude:
      - '*.txt'
      include:
      - wd/*.dat
      job_id: jobonanotherpool
      task_id: mytask
    azure_storage:
    - storage_account_settings: mystorageaccount
      remote_path: poolcontainer/dir
      local_path: $AZ_BATCH_NODE_SHARED_DIR/pooldata
      is_file_share: false
      exclude:
      - '*.tmp'
      include:
      - pooldata*.bin
      blobxfer_extra_options: null
  resource_files:
  - blob_source: https://some.url
    file_mode: '0750'
    file_path: path/in/wd/file.bin
  ssh:
    username: shipyard
    expiry_days: 30
    ssh_public_key: /path/to/rsa/publickey.pub
    ssh_public_key_data: ssh-rsa ...
    ssh_private_key: /path/to/rsa/privatekey
    generate_docker_tunnel_script: true
    generated_file_export_path:
    hpn_server_swap: false
    allow_docker_access: false
  rdp:
    username: shipyard
    password: null
    expiry_days: 30
  remote_access_control:
    starting_port: 49000
    allow:
    - 1.2.3.4
    deny:
    - '*'
  virtual_network:
    arm_subnet_id: /subscriptions/<subscription_id>/resourceGroups/<resource_group>/providers/Microsoft.Network/virtualNetworks/<virtual_network_name>/subnets/<subnet_name>
    name: myvnet
    resource_group: resource-group-of-vnet
    create_nonexistant: false
    address_space: 10.0.0.0/16
    subnet:
      name: subnet-for-batch-vms
      address_prefix: 10.0.0.0/20
  certificates:
    sha1-thumbprint:
      visibility:
      - task
      - start_task
      - remote_user
  gpu:
    nvidia_driver:
      source: https://some.url
  additional_node_prep_commands:
    pre: []
    post: []
  prometheus:
    node_exporter:
      enabled: false
      port: 9100
      options: []
    cadvisor:
      enabled: false
      port: 8080
      options: []
  container_runtimes:
    install:
      - kata_containers
      - singularity
    default: null
```

The `pool_specification` property has the following members:

* (required) `id` is the compute pool ID.
* (required) `vm_configuration` specifies the image configuration for the
VM. Either `platform_image` or `custom_image` must be specified. You cannot
specify both. Please see the
[Batch Shipyard Platform Image support doc](25-batch-shipyard-platform-image-support.md)
for more information on which Marketplace images are supported. If using a
custom image, please see the
[Custom Image Guide](63-batch-shipyard-custom-images.md) first.
    * (required for platform image) `platform_image` defines the Marketplace
      platform image to use:
        * (required for platform image) `publisher` is the publisher name of
          the Marketplace VM image.
        * (required for platform image) `offer` is the offer name of the
          Marketplace VM image.
        * (required for platform image) `sku` is the sku name of the
          Marketplace VM image.
        * (optional) `version` is the image version to use. The default is
          `latest`.
        * (optional) `native` will convert the platform image to use native
          Docker container support for Azure Batch, if possible. This can
          provide better task management (such as job and task termination
          while tasks are running) and potentially lead to faster compute
          node provisioning (although not guaranteed), in exchange for some
          features that are not available in this mode such Singularity
          containers, task-level data ingress or task-level data
          egress that is not bound for Azure Storage Blobs, among others.
          If there is no `native` conversion equivalent for the specified
          `publisher`, `offer`, `sku` then no conversion is performed and
          this option will be force disabled. Note that `native` mode is
          not compatible with Singularity containers. The default is `false`.
          Please see the [FAQ](97-faq.md) for more information.
        * (optional) `license_type` specifies the type of on-premises license
          to be used when deploying the operating system. This activates the
          [Azure Hybrid Use Benefit](https://azure.microsoft.com/pricing/hybrid-benefit/)
          for qualifying license holders. This only applies to Windows OS
          types. You must comply with the terms set forth by this program;
          please consult the [FAQ](https://azure.microsoft.com/pricing/hybrid-benefit/faq/)
          for further information. The only valid value is `windows_server`.
    * (required for custom image) `custom_image` defines the custom image to
      use. AAD `batch` credentials are required to use custom images for both
      Batch service and User Subscription modes.
        * (required for custom image) `arm_image_id` defines the ARM image id
          to use as the OS image for the pool. The ARM image must be in the
          same subscription and region as the Batch account.
        * (required for custom image) `node_agent` is the node agent sku id to
          use with this custom image. You can view supported base images and
          their node agent sku ids with the `pool listskus` command.
        * (optional) `native` will opt to use native Docker container support
          if possible. This provides better task management (such as job and
          task termination while tasks are running), in exchange for some other
          features that are not available in this mode such as task-level data
          ingress or task-level data egress that is not bound for Azure Storage
          Blobs. The default is `false`.
        * (optional) `license_type` specifies the type of on-premises license
          to be used when deploying the operating system. This activates the
          [Azure Hybrid Use Benefit](https://azure.microsoft.com/pricing/hybrid-benefit/)
          for qualifying license holders. This only applies to Windows OS
          types. You must comply with the terms set forth by this program;
          please consult the [FAQ](https://azure.microsoft.com/pricing/hybrid-benefit/faq/)
          for further information. The only valid value is `windows_server`.
* (required) `vm_size` is the
[Azure Virtual Machine Instance Size](https://azure.microsoft.com/pricing/details/virtual-machines/).
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
if specified. If not specified, the default is 15 minutes. This should not
be specified (and is ignored) for `autoscale` enabled pools.
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
      required, but "d" is optional, if specified. If not specified, the
      default is 15 minutes. The smallest value that can be specified is 5
      minutes. Use caution when specifying a small `evaluation_interval`
      values which can cause pool resizing errors and instability with
      volatile target counts.
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
        * (optional) `maximum_vm_increment_per_evaluation` is the maximum
          amount of VMs to increase per evaluation. Specifying a non-positive
          value (i.e., less than or equal to `0`) for either of the following
          properties will result in effectively no increment limit.
            * (optional) `dedicated` is the maximum increase in VMs per
              evaluation.
            * (optional) `low_priority` is the maximum increase in VMs per
              evaluation.
        * (optional) `node_deallocation_option` is the node deallocation option
          to apply. When a pool is resized down and a node is selected for
          removal, what action is performed for the running task is specified
          with this option. The valid values are: `requeue`, `terminate`,
          `taskcompletion`, and `retaineddata`. The default is `taskcompletion`.
          Please see [this doc](https://docs.microsoft.com/azure/batch/batch-automatic-scaling#variables) for more information.
        * (optional) `sample_lookback_interval` is the time interval to
          lookback for past history for certain scenarios such as autoscale
          based on active and pending tasks. The format for this property is
          a timedelta with a string representation of "d.HH:mm:ss". "HH:mm:ss"
          is required, but "d" is optional, if specified. If not specified,
          the default is 10 minutes.
        * (optional) `required_sample_percentage` is the required percentage of
          samples that must be present during the `sample_lookback_interval`.
          If not specified, the default is 70.
        * (optional) `bias_last_sample` will bias the autoscale scenario, if
          applicable, to use the last sample during history computation. This
          can be enabled to more quickly respond to changes in history with
          respect to averages. The default is `true`.
        * (optional) `bias_node_type` will bias the the autoscale scenario, if
          applicable, to favor one type of node over the other when making a
          decision on how many of each node to allocate. The default is `auto`
          or equal weight to both `dedicated` and `low_priority` nodes. Valid
          values are `null` (or omitting the property), `dedicated`, or
          `low_priority`.
        * (optional) `rebalance_preemption_percentage` will rebalance the
          compute nodes to bias for dedicated nodes when the pre-empted node
          count reaches the indicated threshold percentage of the total
          current dedicated and low priority nodes. The default is `null`
          or no rebalancing is performed.
        * (optional) `time_ranges` defines the time ranges for the day-of-week
          based scenarios.
            * (optional) `weekdays` defines the days of the week which should
              be considered weekdays, where `1` = Monday.
                * (optional) `start` defines the inclusive start weekday day
                  of the week as an integer. The default is `1`.
                * (optional) `end` defines the inclusive end weekday day
                  of the week as an integer. The default is `5`.
            * (optional) `work_hours` defines the hours of the day in the
              work day with a range from `0` to `23`, inclusive.
                * (optional) `start` defines the inclusive start hour of
                  the work day as an integer. The default is `8`.
                * (optional) `end` defines the inclusive end hour of
                  the work day as an integer. The default is `17`.
    * (optional) `formula` is a custom autoscale formula to apply to the pool.
      If both `formula` and `scenario` are specified, then `formula` is used.
* (optional) `inter_node_communication_enabled` designates if this pool is set
up for inter-node communication. This must be set to `true` for any containers
that must communicate with each other such as MPI applications. This
property cannot be enabled if there are positive values for both
`dedicated and `low_priority` compute nodes specified above. This property
will be force enabled if peer-to-peer replication is enabled.
* (optional) `per_job_auto_scratch` will enable on-demand distributed scratch
space creation across all dedicated or low priority nodes in a pool for a job.
This scratch will be available at the location
`$AZ_BATCH_TASK_DIR/auto_scratch` within the container. The scratch drive
is cleaned up automatically on job termination or deletion. This option
requires setting the property `inter_node_communication_enabled` to `true`.
Note that SSH and
[BeeGFS communication](https://www.beegfs.io/wiki/NetworkTuning) must be
allowed on the virtual network between nodes. Thus if specifying a
`virtual_network` and/or `remote_access_control` rules, you must ensure that
the internal network traffic is not blocked by NSG rules.
This option is only available on a subset of supported Linux distributions.
The default, if not specified, is `false`.
* (optional) `reboot_on_start_task_failed` allows Batch Shipyard to reboot the
compute node in case there is a transient failure in node preparation (e.g.,
network timeout, resolution failure or download problem). This defaults to
`false`.
* (optional) `attempt_recovery_on_unusable` allows Batch Shipyard to attempt
to recover nodes that enter `unusable` state automatically. Note that
enabling this option can lead to infinite wait on `pool add` or `pool resize`
with `--wait`. This defaults to `false` and is ignored for `custom_image`
where the behavior is always `false`.
* (optional) `upload_diagnostics_logs_on_unusable` allows Batch Shipyard
to attempt upload of diagnostics logs for nodes that have entered unusable
state during provisioning to the storage account designated under the
`batch_shipyard`:`storage_account_settings` global configuration property.
Note that this typically will only result in one set of logs being uploaded
even if multiple nodes eventually enter this state. These logs can be
referenced in conjunction with a support request to provide additional
insight into why a compute node failed to provision properly. This defaults
to `true`. Note that by setting this property to `true`, these diagnostics
logs are not automatically sent to Microsoft and must be included, either
indirectly via the SAS URL generated or directly, with support requests.
* (optional) `block_until_all_global_resources_loaded` will block the node
from entering ready state until all Docker images are loaded. This defaults
to `true`. This option has no effect on `native` container support pools (the
behavior will effectively reflect `true` for this property on `native`
container support pools).
* (optional) `transfer_files_on_pool_creation` will ingress all `files`
specified in the `global_resources` section of the global configuration file
when the pool is created. If files are to be ingressed to Azure Blob or File
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
          as defined in the credentials config.
        * (required) `remote_path` is required when downloading from Azure
          Storage. This path on Azure includes either the container or file
          share path along with all virtual directories.
        * (required) `local_path` is required when downloading from Azure
          Storage. This specifies where the files should be downloaded to on
          the compute node. Please note that you should not specify a
          destination that is on a shared file system. If you
          require ingressing to a shared file system location like a GlusterFS
          volume, then use the global configuration `files` property and the
          `data ingress` command.
        * (optional) `is_file_share` denotes if the `remote_path` is on a
          file share. This defaults to `false`.
        * (optional) `include` property defines optional include filters.
        * (optional) `exclude` property defines optional exclude filters.
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
virtual network resource for the pool. AAD `batch` credentials are required
for both Batch service and User Subscription modes. Please see the
[Virtual Network guide](64-batch-shipyard-byovnet.md) for more information.
    * (required/optional) `arm_subnet_id` is the full ARM resource id to the
      subnet on the virtual network. This virtual network must already exist
      and must exist within the same region and subscription as the Batch
      account. If this value is specified, the other properties of
      `virtual_network` are ignored. AAD `management` credentials are not
      strictly required for this case but is recommended to be filled to
      allow address space validation checks.
    * (required/optional) `name` is the name of the virtual network. If
      `arm_subnet_id` is not specified, this value is required. Note that this
      requires AAD `management` credentials.
    * (optional) `resource_group` containing the virtual network. If
      the resource group name is not specified here, the `resource_group`
      specified in the `batch` credentials will be used instead.
    * (optional) `create_nonexistant` specifies if the virtual network and
      subnet should be created if not found. If not specified, this defaults
      to `false`.
    * (required if creating, optional otherwise) `address_space` is the
      allowed address space for the virtual network.
    * (required/optional) `subnet` specifies the subnet properties. This is
      required if `arm_subnet_id` is not specified, i.e., the virtual network
      `name` is specified instead.
      * (required) `name` is the subnet name.
      * (required) `address_prefix` is the subnet address prefix to
        use for allocation Batch compute nodes to. The maximum number of
        compute nodes a subnet can support is 4096 which maps roughly to
        a CIDR mask of 20-bits.
* (optional) `ssh` is the property for creating a user to accomodate SSH
sessions to compute nodes. If this property is absent, then an SSH user is not
created with pool creation. If you are running Batch Shipyard on Windows,
please refer to [these instructions](85-batch-shipyard-ssh-docker-tunnel.md#ssh-keygen)
on how to generate an SSH keypair for use with Batch Shipyard. This property
is ignored for Windows-based pools.
    * (required) `username` is the user to create on the compute nodes.
    * (optional) `expiry_days` is the number of days from now for the account
      on the compute nodes to expire. The default is 30 days from invocation
      time.
    * (optional) `ssh_public_key` is the path to an existing SSH public key
      to use. If not specified, an RSA public/private keypair will be
      automatically generated if `ssh-keygen` or `ssh-keygen.exe` can be
      found on the `PATH`. This option cannot be specified with
      `ssh_public_key_data`.
    * (optional) `ssh_public_key_data` is the raw RSA public key data in
      OpenSSH format, e.g., a string starting with `ssh-rsa ...`. Only one
      key may be specified. This option cannot be specified with
      `ssh_public_key`.
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
    * (optional) `allow_docker_access` allows this SSH user access to the
      Docker daemon. The default is `false`.
* (optional) `rdp` is the property for creating a user to accomodate RDP login
sessions to compute nodes. If this property is absent, then an RDP user is not
created with pool creation. This property is ignored for Linux-based pools.
    * (required) `username` is the user to create on the compute nodes.
    * (optional) `expiry_days` is the number of days from now for the account
      on the compute nodes to expire. The default is 30 days from invocation
      time.
    * (optional) `password` is the password to associate with the user.
      Passwords must meet the minimum complexity requirements as required
      by Azure Batch. If left omitted, unspecified or set to `null`, then
      a random password is generated and logged during any `pool add` call
      with this section defined, or `pool user add`.
* (optional) `remote_access_control` is a property to control access to the
remote access port (SSH or RDP). If this section is omitted, then the Batch
service defaults are applied which do not apply any network security
rules on these ports.
    * (optional) `starting_port` is the starting port for each SSH port
      on each node to map to the "front-end" load balancer. The default value
      is `49000` if not specified. Ports from `50000` to `55000` are
      reserved by the Batch service. You must specify enough space for
      1000 ports; e.g., `49500` would not be valid since the range would
      overlap into the reserved range.
    * (optional) `allow` is a list of allowable address prefixes in CIDR
      format.
    * (optional) `deny` is a list of address prefixes in CIDR format to
      deny. `deny` rules have lower priority than `allow` rules. Therefore,
      you can specify a set of allowable address prefixes and then specify
      a single deny rule of `*` to deny all other IP addresses from
      connecting to the remote access port. Take care when specifying
      `deny` rules when your nodes must make use of SSH or RDP to perform
      actions between compute nodes.
* (optional) `certificates` property defines any certificate references to
add on this pool. These certificates must already be present on the Batch
account and are only applied to new pool allocations.
    * (required) `sha1-thumbprint` is the actual SHA-1 thumbprint of the
      certificate to add to the pool.
        * (required) `visibility` is a list of visibility settings to apply
          to the certificate. Valid values are `node_prep`, `remote_user`,
          and `task`.
* (optional) `gpu` property defines additional information for NVIDIA
GPU-enabled VMs. If not specified, Batch Shipyard will automatically download
the driver for the `vm_size` specified.
    * `nvidia_driver` property contains the following required members:
        * `source` is the source url to download the driver. This should be
          the silent-installable driver package.
* (optional) `additional_node_prep_commands` contains the following members:
    * (optional) `pre` is an array of additional commands to execute on the
      compute node host as part of node preparation which occur prior to
      the Batch Shipyard node preparation steps. This is particularly useful
      for preparing platform images with software for custom Linux mounts.
    * (optional) `post` is an array of additional commands to execute on the
      compute node host as part of node preparation which occur after the
      Batch Shipyard node preparation steps.
* (optional) `prometheus` properties are to control if collectors for metrics
to export to [Prometheus](https://prometheus.io/) monitoring are enabled.
Note that all exporters do not have their ports mapped (NAT) on the load
balancer pool. This means that the Prometheus instance itself must reside
on, or peered with, the virtual network that the compute nodes are in. This
ensures that external parties cannot scrape exporter metrics from compute
node instances.
    * (optional) `node_exporter` contains options for the
      [Node Exporter](https://github.com/prometheus/node_exporter) metrics
      exporter.
        * (optional) `enabled` property enables or disables this exporter.
          Default is `false`.
        * (optional) `port` is the port for Prometheus to connect to scrape.
          This is the internal port on the compute node.
        * (optional) `options` is a list of options to pass to the
          node exporter instance running on all nodes. The following
          collectors are force disabled, in addition to others disabled by
          default: textfile, mdadm, wifi, xfs, zfs. The infiniband collector
          is enabled if on an IB/RDMA instance, automatically. The nfs
          collector is enabled if mounting an NFS RemoteFS storage cluster,
          automatically.
    * (optional) `cadvisor` contains options for the
      [cAdvisor](https://github.com/google/cadvisor) metrics exporter.
        * (optional) `enabled` property enables or disables this exporter.
          Default is `false`.
        * (optional) `port` is the port for Prometheus to connect to scrape.
          This is the internal port on the compute node.
        * (optional) `options` is a list of options to pass to the
          cAdvisor instance running on all nodes.
* (optional) `container_runtimes` properties control container runtime
behavior on the pool compute nodes.
    * (optional) `install` controls which optional container runtimes to
      install. A list of valid values for this option are `kata_containers`
      and `singularity`. Note that the `runc` container runtime is always
      installed. The `nvidia` container runtime is automatically installed
      when allocating a pool with GPUs. `singularity` must be specified if
      running Singularity containers.
    * (optional) `default` is the default container runtime to use for
      running Docker containers. This option has no effect on `singularity`
      containers.

## Full template
A full template of a credentials file can be found
[here](https://github.com/Azure/batch-shipyard/tree/master/config_templates).
Note that these templates cannot be used as-is and must be modified to fit
your scenario.
