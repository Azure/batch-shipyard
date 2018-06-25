# Batch Shipyard Federation Configuration
This page contains in-depth details on how to configure the federation
configuration file for Batch Shipyard.

## Schema
The federation schema is as follows:

```yaml
federation:
  storage_account_settings: mystorageaccount
  location: <Azure region, e.g., eastus>
  resource_group: my-federation-proxy-rg
  hostname_prefix: fed
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
      name: my-federation-proxy-subnet
      address_prefix: 10.0.0.0/24
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
  accelerated_networking: false
  proxy_options:
    polling_interval:
      federations: 15
      jobs: 5
    logging:
      persistence: true
      level: debug
      filename: fedproxy.log
    scheduling:
      after_success:
        blackout_interval: 15
        evaluate_autoscale: true
```

The `federation` property has the following members:

* (required) `storage_account_settings` is the storage account link to store
all federation metadata. Any `fed` command that must store metadata or
actions uses this storage account. The federation proxy created with this
configuration file will also utilize this storage account.
* (required) `location` is the Azure region name for the resources, e.g.,
`eastus` or `northeurope`.
* (required) `resource_group` this is the resource group to use for the
federation proxy.
* (required) `hostname_prefix` is the DNS label prefix to apply to each
virtual machine and resource allocated for the federation proxy. It should
be unique.
* (required) `ssh` is the SSH admin user to create on the machine. This is not
optional in this configuration as it is in the pool specification. If you are
running Batch Shipyard on Windows, please refer to
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
      create an alternate means for accessing the federation proxy virtual
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
federation proxy.
    * (required) `name` is the virtual network name
    * (optional) `resource_group` is the resource group for the virtual
      network. If this is not specified, the resource group name falls back
      to the resource group specified in the federation proxy.
    * (optional) `existing_ok` allows use of a pre-existing virtual network.
      The default is `false`.
    * (required if creating, optional otherwise) `address_space` is the
      allowed address space for the virtual network.
    * (required) `subnet` specifies the subnet properties.
        * (required) `name` is the subnet name.
        * (required) `address_prefix` is the subnet address prefix to use for
          allocation of the federation proxy virtual machine to.
* (required) `network_security` defines the network security rules to apply
to the federation proxy virtual machine.
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
* (optional) `accelerated_networking` enables or disables
[accelerated networking](https://docs.microsoft.com/azure/virtual-network/create-vm-accelerated-networking-cli).
The default is `false` if not specified.
* (optional) `proxy_options` are the federation proxy specific properties
    * (optional) `polling_interval` specifies different polling interval
      lengths
        * (optional) `federations` specifies the amount of time in seconds
          between checking for federation updates. The default, if not
          specified, is `15`.
        * (optional) `jobs` specifies the amount of time in seconds between.
          checking for federation action queued messages. The default, if not
          specified, is `5`.
    * (optional) `logging` specifies various logging options
        * (optional) `persistence` specifies if logs should be persisted to
          Azure File storage. The default, if not specified, is `true`.
        * (optional) `level` specifies the level to log including all "higher"
          levels. The default, if not specified, is `debug`.
        * (optional) `filename` is a log filename schema where the `level` is
          injected as part of the filename. At most two files will be
          created initially, which is a file containing the specified `level`
          and the `error` level. The default, if not specified,
          is `fedproxy.log`. If the `level` specified is `debug`, then
          the log files `fedproxy-debug.log` and `fedproxy-error.log` will
          be created. Log files are automatically rotated after 32MiB of
          data has been written.
    * (optional) `scheduling` specifies federation proxy wide scheduling
      options to use while processing actions.
        * (optional) `after_success` apply to actions which have been
          successfully scheduled.
            * (optional) `blackout_interval` specifies the scheduling blackout
              interval to apply to the target pool in seconds. The default,
              if not specified, is `15`.
            * (optional) `evaluate_autoscale` specifies if the autoscale
              formula should be immediately applied to the target pool after
              a task group has been successfully scheduled. This option only
              applies to autoscale-enabled pools. The default, if not
              specified, is `true`.

## Federations with Batch Shipyard Guide
Please see the [full guide](68-batch-shipyard-federation.md) for
relevant terminology and information on how this feature works in Batch
Shipyard.

## Full template
A full template of a federation configuration file can be found
[here](https://github.com/Azure/batch-shipyard/tree/master/config_templates).
Note that these templates cannot be used as-is and must be modified to fit
your scenario.
