# Batch Shipyard Slurm Configuration
This page contains in-depth details on how to configure a
[Slurm](https://slurm.schedmd.com/) configuration file for Batch Shipyard.

## Schema
The Slurm schema is as follows:

```yaml
slurm:
  storage_account_settings: mystorageaccount
  location: <Azure region, e.g., eastus>
  resource_group: my-slurm-rg
  cluster_id: slurm
  controller:
    ssh:
      username: shipyard
      ssh_public_key: /path/to/rsa/publickey.pub
      ssh_public_key_data: ssh-rsa ...
      ssh_private_key: /path/to/rsa/privatekey
      generated_file_export_path: null
    public_ip:
      enabled: true
      static: false
    virtual_network:
      name: myvnet
      resource_group: my-vnet-resource-group
      existing_ok: false
      address_space: 10.0.0.0/16
      subnet:
        name: my-slurm-controller-subnet
        address_prefix: 10.0.1.0/24
    network_security:
      ssh:
      - '*'
      custom_inbound_rules:
        myrule:
          destination_port_range: 5000-5001
          protocol: '*'
          source_address_prefix:
          - 1.2.3.4
          - 5.6.7.0/24
    vm_size: STANDARD_D2_V2
    vm_count: 2
    accelerated_networking: false
    additional_prep_script: /path/to/some/script-controller.sh
  login:
    ssh:
      username: shipyard
      ssh_public_key: /path/to/rsa/publickey.pub
      ssh_public_key_data: ssh-rsa ...
      ssh_private_key: /path/to/rsa/privatekey
      generated_file_export_path: null
    public_ip:
      enabled: true
      static: false
    virtual_network:
      name: myvnet
      resource_group: my-vnet-resource-group
      existing_ok: false
      address_space: 10.0.0.0/16
      subnet:
        name: my-slurm-login-subnet
        address_prefix: 10.0.2.0/24
    network_security:
      ssh:
      - '*'
      custom_inbound_rules:
        myrule:
          destination_port_range: 5000-5001
          protocol: '*'
          source_address_prefix:
          - 1.2.3.4
          - 5.6.7.0/24
    vm_size: STANDARD_D4_V2
    vm_count: 1
    accelerated_networking: false
    additional_prep_script: /path/to/some/script-login.sh
  shared_data_volumes:
    nfs_server:
      mount_path: /shared
      store_slurmctld_state: true
  slurm_options:
    idle_reclaim_time: 00:15:00
    elastic_partitions:
      partition_1:
        batch_pools:
          mypool1:
            account_service_url: https://...
            compute_node_type: dedicated
            max_compute_nodes: 32
            weight: 0
            features:
            - arbitrary_constraint_1
            reclaim_exclude_num_nodes: 8
          mypool2:
            account_service_url: https://...
            compute_node_type: low_priority
            max_compute_nodes: 128
            weight: 1
            features:
            - arbitrary_constraint_2
            reclaim_exclude_num_nodes: 0
        max_runtime_limit: null
        default: true
        preempty_type: preempt/partition_prio
        preempt_mode: requeue
        over_subscribe: no
        priority_tier: 10
        other_options: []
      partition_2:
        batch_pools:
          mypool3:
            account_service_url: https://...
            compute_node_type: low_priority
            max_compute_nodes: 256
            weight: 2
            features: []
            reclaim_exclude_num_nodes: 0
        max_runtime_limit: 1.12:00:00
        default: false
    unmanaged_partitions:
      - partition: 'PartitionName=onprem Nodes=onprem-[0-31] Default=No MaxTime=INFINITE State=UP'
        nodes:
          - 'NodeName=onprem-[0-31] CPUs=512 Sockets=1 CoresPerSocket=8 ThreadsPerCore=2 RealMemory=512128 State=UNKNOWN'
```

The `slurm` property has the following members:

* (required) `storage_account_settings` is the storage account link to store
all Slurm metadata. Any `slurm` command that must store metadata or
actions uses this storage account.
* (required) `location` is the Azure region name for the resources, e.g.,
`eastus` or `northeurope`.
* (required) `resource_group` this is the resource group to use for the
Slurm resources.
* (required) `cluster_id` is the name of the Slurm cluster to create. This
is also the DNS label prefix to apply to each virtual machine and resource
allocated for the Slurm cluster. It should be unique.

There are two required sections for resources that comprise the Slurm
cluster: `controller` and `login`. The `controller` section specifies the VM
configuration which hosts the Slurm controller (and possibly the Slurm DBD).
The `login` section specifies the VM configuration which hosts the login nodes
for the Slurm cluster.

Both the `controller` and `login` sections have the following identical
configuration properties:

* (required) `ssh` is the SSH admin user to create on the machine.
If you are running Batch Shipyard on Windows, please refer to
[these instructions](85-batch-shipyard-ssh-docker-tunnel.md#ssh-keygen)
on how to generate an SSH keypair for use with Batch Shipyard.
    * (required) `username` is the admin user to create on all virtual machines
    * (optional) `ssh_public_key` is the path to a pre-existing ssh public
      key to use. If this is not specified, an RSA public/private key pair will
      be generated for use in your current working directory (with a
      non-colliding name for auto-generated SSH keys for compute pools, i.e.,
      `id_rsa_shipyard_remotefs`). On Windows only, if this is option is not
      specified, the SSH keys are not auto-generated (unless `ssh-keygen.exe`
      can be invoked in the current working directory or is in `%PATH%`).
      This option cannot be specified with `ssh_public_key_data`.
    * (optional) `ssh_public_key_data` is the raw RSA public key data in
      OpenSSH format, e.g., a string starting with `ssh-rsa ...`. Only one
      key may be specified. This option cannot be specified with
      `ssh_public_key`.
    * (optional) `ssh_private_key` is the path to an existing SSH private key
      to use against either `ssh_public_key` or `ssh_public_key_data` for
      connecting to storage nodes and performing operations that require SSH
      such as cluster resize and detail status. This option should only be
      specified if either `ssh_public_key` or `ssh_public_key_data` are
      specified.
    * (optional) `generated_file_export_path` is an optional path to specify
      for where to create the RSA public/private key pair.
* (optional) `public_ip` are public IP properties for the virtual machine.
    * (optional) `enabled` designates if public IPs should be assigned. The
      default is `true`. Note that if public IP is disabled, then you must
      create an alternate means for accessing the Slurm resource virtual
      machine through a "jumpbox" on the virtual network. If this property
      is set to `false` (disabled), then any action requiring SSH, or the
      SSH command itself, will occur against the private IP address of the
      virtual machine.
    * (optional) `static` is to specify if static public IPs should be assigned
      to each virtual machine allocated. The default is `false` which
      results in dynamic public IP addresses. A "static" FQDN will be provided
      per virtual machine, regardless of this setting if public IPs are
      enabled.
* (required) `virtual_network` is the virtual network to use for the
Slurm resource.
    * (required) `name` is the virtual network name
    * (optional) `resource_group` is the resource group for the virtual
      network. If this is not specified, the resource group name falls back
      to the resource group specified in the Slurm resource.
    * (optional) `existing_ok` allows use of a pre-existing virtual network.
      The default is `false`.
    * (required if creating, optional otherwise) `address_space` is the
      allowed address space for the virtual network.
    * (required) `subnet` specifies the subnet properties.
        * (required) `name` is the subnet name.
        * (required) `address_prefix` is the subnet address prefix to use for
          allocation of the Slurm resource virtual machine to.
* (required) `network_security` defines the network security rules to apply
to the Slurm resource virtual machine.
    * (required) `ssh` is the rule for which address prefixes to allow for
      connecting to sshd port 22 on the virtual machine. In the example, `"*"`
      allows any IP address to connect. This is an array property which allows
      multiple address prefixes to be specified.
    * (optional) `grafana` rule allows grafana HTTPS (443) server port to be
      exposed to the specified address prefix. Multiple address prefixes
      can be specified.
    * (optional) `prometheus` rule allows the Prometheus server port to be
      exposed to the specified address prefix. Multiple address prefixes
      can be specified.
    * (optional) `custom_inbound_rules` are custom inbound rules for other
      services that you need to expose.
        * (required) `<rule name>` is the name of the rule; the example uses
          `myrule`. Each rule name should be unique.
            * (required) `destination_port_range` is the ports on each virtual
              machine that will be exposed. This can be a single port and
              should be a string.
            * (required) `source_address_prefix` is an array of address
              prefixes to allow.
        * (required) `protocol` is the protocol to allow. Valid values are
          `tcp`, `udp` and `*` (which means any protocol).
* (required) `vm_size` is the virtual machine instance size to use.
* (required) `vm_count` is the number of virtual machines to allocate of
this instance type. For `controller`, a value greater than `1` will create
a HA Slurm cluster. Additionally, a value of greater than `1` will
automatically place the VMs in an availability set.
* (optional) `accelerated_networking` enables or disables
[accelerated networking](https://docs.microsoft.com/azure/virtual-network/create-vm-accelerated-networking-cli).
The default is `false` if not specified.
* (optional) `additional_prep_script` property specifies a local file which
will be uploaded then executed for additional prep/configuration that should
be applied to each Slurm resource.

There are two required sections for specifying how the Slurm
cluster is configured: `shared_data_volumes` and `slurm_options` sections.
The `shared_data_volumes` section configures shared file systems (or
RemoteFS clusters as provisioned by Batch Shipyard). The `slurm_options`
section configures the Slurm partitions.

The following describes the `shared_data_volumes` configuration:

* (required) Storage cluster id is a named dictionary key that refers
to a defined storage cluster in the global configuration file (and
subsequently the RemoteFS configuration).
    * (required) `mount_path` is the mount path across all Slurm resources
      and compute nodes.
    * (required) `store_slurmctld_state` designates this shared data volume
      as the volume that hosts the slurmctld state for HA failover.

The following describes the `slurm_options` configuration:

* (required) `idle_reclaim_time` specifies the amount of time required to
pass while nodes are idle for them to be reclaimed (or suspended) by Slurm.
The format for this property is a timedelta with a string
representation of "d.HH:mm:ss". "HH:mm:ss" is required but "d" is optional.
* (required) `elastic_partitions` specifies the Slurm partitions to create
  for elastic cloud bursting onto Azure Batch
    * (required) Unique name of the partition
        * (required) `batch_pools` specifies the Batch pools which will be
          dynamically sized by Batch Shipyard and Slurm. All Batch pools
          should be pre-allocated (unless using the `orchestrate` command
          in conjunction with using one pool) with 0 nodes.
            * (required) Batch Pool Id
                * (optional) `account_service_url` is the Batch account
                  service URL associated with this Batch pool. Currently,
                  this is restricted to the service url specified in the
                  credentials file.
                * (required) `compute_node_type` is the compute node type
                  to allocate, can be either `dedicated` or `low_priority`.
                * (required) `max_compute_nodes` is the maximum number of
                  compute nodes that can be allocated.
                * (required) `weight` is this weight for this Batch pool in
                  this partition. See the Slurm documentation for more details.
                * (optional) `features` are additional features labeled on
                  this partition.
                * (optional) `reclaim_exclude_num_nodes` is the number of
                  nodes to exclude from reclaiming for this Batch pool.
        * (optional) `max_runtime_limit` imposes a maximum runtime limit
          for this partition. The format for this property is a timedelta
          with a string representation of "d.HH:mm:ss". "HH:mm:ss" is
          required but "d" is optional.
        * (required) `default` designates this partition as the default
          partition.
        * (optional) `preempt_type` is the PreemptType setting for preemption
        * (optional) `preempt_mode` is the PreemptMode setting for preemption
        * (opation) `over_subscribe` is the OverSubscribe setting associated
          with preemption
        * (optional) `priority_tier` is the PriorityTier setting for preemption
        * (optional) `other_options` is a sequence of other options to
          specify on the partition
* (optional) `unmanaged_partitions` specifies partitions which are not
managed by Batch Shipyard but those that you wish to join to the Slurm
controller. This is useful for joining on-premises nodes within the same
Virtual Network (or peered) to the Slurm cluster. Each sequence member
has the properties:
    * (required) `partition` specifies the partition entry in the Slurm
      configuration file.
    * (required) `nodes` is a sequence of Slurm node entries in the Slurm
      configuration file as it relates to the partition.

## Slurm with Batch Shipyard Guide
Please see the [full guide](69-batch-shipyard-slurm.md) for
relevant terminology and information on how this feature works in Batch
Shipyard.

## Full template
A full template of a Slurm cluster configuration file can be found
[here](https://github.com/Azure/batch-shipyard/tree/master/config_templates).
Note that these templates cannot be used as-is and must be modified to fit
your scenario.
