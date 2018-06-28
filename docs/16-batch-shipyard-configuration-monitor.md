# Batch Shipyard Resource Monitoring Configuration
This page contains in-depth details on how to configure the resource
monitoring configuration file for Batch Shipyard.

## Schema
The monitoring schema is as follows:

```yaml
monitoring:
  location: <Azure region, e.g., eastus>
  resource_group: my-prom-server-rg
  hostname_prefix: prom
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
      name: my-server-subnet
      address_prefix: 10.0.0.0/24
  network_security:
    ssh:
    - '*'
    grafana:
    - 1.2.3.0/24
    - 2.3.4.5
    prometheus:
    - 2.3.4.5
  vm_size: STANDARD_D2_V2
  accelerated_networking: false
  services:
    resource_polling_interval: 15
    lets_encrypt:
      enabled: true
      use_staging_environment: true
    prometheus:
      port: 9090
      scrape_interval: 10s
    grafana:
      additional_dashboards: {}
```

The `monitoring` property has the following members:

* (required) `location` is the Azure region name for the resources, e.g.,
`eastus` or `northeurope`. The `location` specified must match the same
region as your Azure Batch account if monitring compute pools and/or within
the same region if monitoring storage clusters.
* (required) `resource_group` this is the resource group to use for the
monitoring resource.
* (required) `hostname_prefix` is the DNS label prefix to apply to each
virtual machine and resource allocated for the monitoring resource. It should
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
      create an alternate means for accessing the resource monitor virtual
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
resource monitor.
    * (required) `name` is the virtual network name
    * (optional) `resource_group` is the resource group for the virtual
      network. If this is not specified, the resource group name falls back
      to the resource group specified in the resource monitor.
    * (optional) `existing_ok` allows use of a pre-existing virtual network.
      The default is `false`.
    * (required if creating, optional otherwise) `address_space` is the
      allowed address space for the virtual network.
    * (required) `subnet` specifies the subnet properties. This subnet should
      be exclusive to the resource monitor and cannot be shared with other
      resources, including Batch compute nodes. Batch compute nodes and storage
      clusters can co-exist on the same virtual network, but should be in
      separate subnets. It's recommended that the monitor VM be in a separate
      subnet as well.
        * (required) `name` is the subnet name.
        * (required) `address_prefix` is the subnet address prefix to use for
          allocation of the resource monitor virtual machine to.
* (required) `network_security` defines the network security rules to apply
to the resource monitoring virtual machine.
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
* (required) `services` defines the behavior of the services that run on
the monitoring resource virtual machine.
    * (optional) `resource_polling_interval` is the polling interval in
      seconds for monitored resource discovery. The default is `15` seconds.
    * (optional) `lets_encrypt` defines options for enabling
      [Let's Encrypt](https://letsencrypt.org/) on the
      [nginx](https://www.nginx.com/) reverse proxy for TLS encryption. This
      can only be enabled if the `public_ip` is enabled.
        * (required) `enabled` controls if Let's Encrypt is enabled or not.
          The default is `true`.
        * (optional) `use_staging_environment` forces the certificate request
          to happen against Let's Encrypt's staging servers. Although this
          will enable encryption over HTTP, since the CA is fake, warnings
          will appear with most browsers when attempting to connect to the
          service endpoints on the resource monitoring VM. This is useful
          to ensure your configuration is correct before switching to a
          production certificate. The default is `true`.
    * (optional) `prometheus` configures the Prometheus server endpoint on the
      resource monitoring VM. Note that it is not required to define this
      section. If it is omitted, then the Prometheus server is not exposed.
        * (optional) `port` is the port to use. If this is value is omitted,
          the Prometheus server is not exposed.
        * (optional) `scrape_interval` is the collector scrape interval to
          use. The default is `10s`. Note that valid values are Prometheus
          [duration strings](https://prometheus.io/docs/prometheus/latest/configuration/configuration/#%3Cduration%3E).
    * (optional) `grafana` configures the Grafana endpoint on the resource
      monitoring VM
        * (optional) `additional_dashboards` is a dictionary of additional
          Grafana dashboards to provision. The format of the dictionary is
          `filename.json: URL`. For example,
          `my_custom_dash.json: https://some.url`.

## Resource Monitoring with Batch Shipyard Guide
Please see the [full guide](66-batch-shipyard-resource-monitoring.md) for
information on how this feature works in Batch Shipyard.

## Full template
A full template of a resource monitoring configuration file can be found
[here](https://github.com/Azure/batch-shipyard/tree/master/config_templates).
Note that these templates cannot be used as-is and must be modified to fit
your scenario.
