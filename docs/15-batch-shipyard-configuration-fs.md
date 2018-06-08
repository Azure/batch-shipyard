# Batch Shipyard Remote Filesystem Configuration
This page contains in-depth details on how to configure the remote filesystem
configuration file for Batch Shipyard.

## Schema
The remote filesystem schema is as follows:

```yaml
remote_fs:
  resource_group: my-resource-group
  location: <Azure region, e.g., eastus>
  managed_disks:
    resource_group: my-disk-resource-group
    premium: true
    disk_size_gb: 128
    disk_names:
    - p10-disk0a
    - p10-disk1a
    - p10-disk0b
    - p10-disk1b
  storage_clusters:
    mystoragecluster:
      resource_group: my-server-resource-group
      hostname_prefix: mystoragecluster
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
        nfs:
        - 1.2.3.0/24
        - 2.3.4.5
        glusterfs:
        - 1.2.3.0/24
        - 2.3.4.5
        smb:
        - 6.7.8.9
        custom_inbound_rules:
          myrule:
            destination_port_range: 5000-5001
            protocol: '*'
            source_address_prefix:
            - 1.2.3.4
            - 5.6.7.0/24
      file_server:
        type: glusterfs
        mountpoint: /data
        mount_options:
        - noatime
        - nodiratime
        server_options:
          glusterfs:
            performance.cache-size: 1 GB
            transport: tcp
            volume_name: gv0
            volume_type: distributed
          nfs:
            '*':
            - rw
            - sync
            - root_squash
            - no_subtree_check
        samba:
          share_name: data
          account:
            username: myuser
            password: userpassword
            uid: 1002
            gid: 1002
          read_only: false
          create_mask: '0700'
          directory_mask: '0700'
      vm_count: 2
      vm_size: STANDARD_F16S
      fault_domains: 2
      accelerated_networking: false
      vm_disk_map:
        '0':
          disk_array:
          - p10-disk0a
          - p10-disk1a
          filesystem: btrfs
          raid_level: 0
        '1':
          disk_array:
          - p10-disk0b
          - p10-disk1b
          filesystem: btrfs
          raid_level: 0
      prometheus:
        node_exporter:
          enabled: false
          port: 9100
          options: []
```

## Details
The remote fs schema is constructed from two portions. The first section
specifies
[Azure Managed Disks](https://docs.microsoft.com/azure/storage/storage-managed-disks-overview)
to use in the storage cluster. The second section defines the storage cluster
itself, including networking and virtual machine to disk mapping.

There are two properties which reside outside of these sections:

* (optional) `resource_group` this is the default resource group to use
for both the `managed_disks` and `storage_clusters` sections. This setting
is only used if `resource_group` is not explicitly set in their respective
configuration blocks.
* (required) `location` is the Azure region name for the resources, e.g.,
`eastus` or `northeurope`. The `location` specified must match the same
region as your Azure Batch account if linking a compute pool with a storage
cluster.

### Managed Disks: `managed_disks`
This section defines the disks used by the file server as specified in the
`storage_clusters` section. Not all disks specified here need to be used by
the storage cluster, but every disk in the storage cluster should be
defined in this section.

* (optional) `resource_group` this is the resource group to use for the
disks. If this is not specified, then the `resource_group` specified in
the parent is used. At least one `resource_group` must be defined.
* (optional) `premium` defines if
[premium managed disks](https://docs.microsoft.com/azure/storage/storage-premium-storage)
should be created. Premium storage provisions a
[guaranteed level of IOPS and bandwidth](https://docs.microsoft.com/azure/storage/storage-premium-storage#premium-storage-scalability-and-performance-targets)
that scales with disk size. The default is `false` which creates
standard managed disks. Regardless of the type of storage used to back
managed disks, all data written is durable and persistent backed to Azure
Storage.
* (required) `disk_size_gb` is an integral value defining the size of the
data disks to create. Note that for managed disks, you are billed rounded
up to the nearest provisioned size. If you are unfamiliar with
how Azure prices managed disks with regard to the size of disk chosen,
please refer to
[this link](https://docs.microsoft.com/azure/storage/storage-managed-disks-overview#pricing-and-billing).
* (required) `disk_names` is an array of disk names to create. All disks
will be created identically with the properties defined in the `managed_disks`
section.

### Storage Clusters: `storage_clusters`
This section defines the storage clusters containing the file server
specification and disk mapping. This section cross-references the
`managed_disks` section so both sections must be populated when performing
`fs cluster` actions.

You can specify multiple storage clusters in the `storage_clusters` section.
Each key in the `storage_clusters` dictionary is a unique id for the
storage cluster that you intend to create. This storage cluster id should be
used as the `STORAGE_CLUSTER_ID` argument for all `fs cluster`
actions in the CLI along with any configuration specified for linking against
Azure Batch pools, if specified, for `pool add`. `data ingress` will also
take this storage cluster id as a parameter if transfering to the file
system. Each storage cluster id (key) is paired with a property
specifying the following properties:

* (optional) `resource_group` this is the resource group to use for the
storage cluster. If this is not specified, then the `resource_group`
specified in the parent is used. At least one `resource_group` must be
defined.
* (required) `hostname_prefix` is the DNS label prefix to apply to each
virtual machine and resource allocated for the storage cluster. It should
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
* (optional) `public_ip` are public IP properties for each virtual machine.
    * (optional) `enabled` designates if public IPs should be assigned. The
      default is `true`. Note that if public IP is disabled, then you must
      create an alternate means for accessing the storage cluster virtual
      machines through a "jumpbox" on the virtual network. If this property
      is set to `false` (disabled), then any action requiring SSH, or the
      SSH command itself, will occur against the private IP address of the
      virtual machine.
    * (optional) `static` is to specify if static public IPs should be assigned
      to each virtual machine allocated. The default is `false` which
      results in dynamic public IP addresses. A "static" FQDN will be provided
      per virtual machine, regardless of this setting if public IPs are
      enabled.
* (required) `virtual_network` is the virtual network to use for the
storage cluster.
    * (required) `name` is the virtual network name
    * (optional) `resource_group` is the resource group for the virtual
      network. If this is not specified, the resource group name falls back
      to the resource group specified in the storage cluster or its parent.
    * (optional) `existing_ok` allows use of a pre-existing virtual network.
      The default is `false`.
    * (required if creating, optional otherwise) `address_space` is the
      allowed address space for the virtual network.
    * (required) `subnet` specifies the subnet properties. This subnet must
      be exclusive to the storage cluster and cannot be shared with other
      resources, including Batch compute nodes. Batch compute nodes and storage
      clusters can co-exist on the same virtual network, but should be in
      separate subnets.
        * (required) `name` is the subnet name.
        * (required) `address_prefix` is the subnet address prefix to use for
          allocation of the storage cluster file server virtual machines to.
* (required) `network_security` defines the network security rules to apply
to each virtual machine in the storage cluster.
    * (required) `ssh` is the rule for which address prefixes to allow for
      connecting to sshd port 22 on the virtual machine. In the example, `"*"`
      allows any IP address to connect. This is an array property which allows
      multiple address prefixes to be specified.
    * (optional) `nfs` rule allows the NFSv4 server port to be exposed to the
      specified address prefix. Multiple address prefixes can be specified.
      This property is ignored for glusterfs clusters.
    * (optional) `glusterfs` rule allows the various GlusterFS management and
      brick ports to be exposed to the specified address prefix. Multiple
      address prefixes can be specified. This property is ignored for nfs
      clusters.
    * (optional) `smb` rule allows the the direct host SMB port to be exposed
      if a `samba` configuration is specified under `file_server`. This
      requires Windows 2000 or later. Please note the name of this rule is
      `smb` which refers to the protocol rather than the `samba`
      implementation for providing this service on a non-Windows host.
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
* (required) `file_server` is the file server specification.
    * (required) `type` is the type of file server to provision. Valid values
      are `nfs` and `glusterfs`. `nfs` will provision an
      [NFSv4 server](https://en.wikipedia.org/wiki/Network_File_System).
      `glusterfs` will provision a [GlusterFS server](https://www.gluster.org/).
    * (required) `mountpoint` is the path to mount the filesystem. This will
      also be the export path from the server for NFS. Note that with
      GlusterFS, if the cluster is suspended then restarted or machines are
      rebooted, the local gluster volume mount will not automatically mount
      upon boot, but will mount upon first use. This only applies to local
      access to the gluster volume mountpath directly on the virtual machine
      itself.
    * (optional) `mount_options` are mount options as an array to specify when
      mounting the filesystem. The examples here `noatime` and `nodiratime`
      reduce file metadata updates for access times on files and directories.
    * (optional) `server_options` is a key-value array of server options with
      the key of the file server `type`.
        * (optional) `glusterfs` are server options for `glusterfs` file
          server `type`.
            * (optional) `volume_name` is the name of the gluster volume. The
              default is `gv0`.
            * (optional) `volume_type` is the type of volume to create. If not
              specified, the default is the gluster default of a distributed
              volume. Please note that the `volume_type` specified here will
              have significant impact on performance and data availability
              delivered by GlusterFS for your workload. It is imperative to
              understand your data I/O and access patterns and selecting the
              proper volume type to maximize performance and/or availability.
              Although written data is durable due to managed disks, VM
              availability can cause reliability issues if a virtual machine
              fails or becomes unavailable thus resulting in unavailability of
              the brick hosting the data. You can view all of the available
              GlusterFS volume types
              [here](https://gluster.readthedocs.io/en/latest/Quick-Start-Guide/Architecture/#types-of-volumes).
            * (optional) `transport` is the transport type to use. The default
              and only valid value is `tcp`.
            * (optional) Other GlusterFS tuning options can be further
              specified here as key-value pairs. You can find all of the
              tuning options
              [here](https://gluster.readthedocs.io/en/latest/Administrator%20Guide/Managing%20Volumes/#tuning-volume-options).
              Please note that nfs-related options for glusterfs, although
              they can be enabled, are not inherently supported by Batch
              Shipyard. Batch Shipyard automatically provisions the proper
              GlusterFS FUSE client on compute nodes that require access to
              GlusterFS-based storage clusters.
        * (optional) `nfs` are server options for `nfs` file server `type`.
          Each dictionary defined maps a host entry to the
          [/etc/exports](https://linux.die.net/man/5/exports) options for
          the NFS exported volume. Note that this can be omitted for the
          default of allowing all hosts within the Virtual Network (`*`) to
          access the share with options `rw,sync,root_squash,no_subtree_check`.
            * (optional) `*` or any IP address or resolvable hostname. Note
              that `*` is safe to specify here assuming the default
              `network_security` rules are in place for `nfs` and you don't
              need to restrict access to VMs on your Virtual Network.
                * (optional) List of export options for this volume. Please
                  refer to any `/etc/exports` guide for applicable options
                  or [this link](https://linux.die.net/man/5/exports).
    * (optional) `samba` defines properties required for enabling
      [SMB](https://msdn.microsoft.com/library/windows/desktop/aa365233(v=vs.85).aspx)
      support on storage cluster nodes. This support is accomplished by
      running [Samba](https://www.samba.org/) alongside the NFS or GlusterFS
      server software. If this section is omitted, SMB access will be disabled.
        * (required) `share_name` name of the share. The path of this share is
          automatically mapped.
        * (optional) `account` is a user identity to mount the file share as.
          If this is not specified, the share will be created with guest access
          allowed and files and directories will be created and modified by the
          `nobody` account on the server.
            * (required) `username` is the username
            * (required) `password` is the password for the user. This cannot
              be null or empty.
            * (required) `uid` is the desired uid for the username
            * (required) `gid` is the desired gid for the username's group
        * (optional) `read_only` designates that the share is read only if this
          property is set to `true`. The default is `false`.
        * (optional) `create_mask` is the file creation mask as an octal
          string. The default is `"0700"`.
        * (optional) `directory_mask` is the directory creation mask as an
          octal string. The default is `"0700"`.
* (required) `vm_count` is the number of virtual machines to allocate for
the storage cluster. For `nfs` file servers, the only valid value is 1.
pNFS is not supported at this time. For `glusterfs` storage clusters, this
value must be at least 2.
* (required) `vm_size` is the virtual machine instance size to use. To attach
premium managed disks, you must use a
[premium storage compatible virtual machine size](https://docs.microsoft.com/azure/storage/storage-premium-storage#premium-storage-supported-vms).
* (optional) `fault_domains` is the number of fault domains to configure for
the availability set. This only applies to `vm_count` > `1` and must be
in the range [2, 3]. The default is `2` if not specified. Note that some
regions do not support 3 fault domains.
* (optional) `accelerated_networking` enables or disables
[accelerated networking](https://docs.microsoft.com/azure/virtual-network/create-vm-accelerated-networking-cli).
The default is `false` if not specified.
* (required) `vm_disk_map` is the virtual machine to managed disk mapping.
The number of entries in this map must match the `vm_count`.
    * (required) `<instance number>` is the virtual machine instance number.
      This value must be a string (although it is integral in nature).
        * (required) `disk_array` is the listing of managed disk names to
          attach to this instance. These disks must be provisioned before
          creating the storage cluster.
        * (required) `filesystem` is the filesystem to use. Valid values are
          `btrfs`, `ext4`, `ext3` and `ext2`. `btrfs` is generally stable for
          RAID-0, with better features and data integrity protection. `btrfs`
          also allows for RAID-0 expansion and is the only filesystem
          compatible with the `fs cluster expand` command.
        * (optional for single disk, required for multiple disks) `raid_level`
          is the RAID level to apply to the disks in the `disk_array`. The
          only valid value for multiple disks is `0`. Note that if you wish
          to expand the number of disks in the array in the future, you must
          use `btrfs` as the filesystem. At least two disks per virtual
          machine are required for RAID-0.
* (optional) `prometheus` properties are to control if collectors for metrics
to export to [Prometheus](https://prometheus.io/) monitoring are enabled.
Note that all exporters do not have their ports exposed to the internet by
default. This means that the Prometheus instance itself must reside
on, or peered with, the virtual network that the storage cluster is in. This
ensures that external parties cannot scrape exporter metrics from storage
cluster VMs.
    * (optional) `node_exporter` contains options for the
      [Node Exporter](https://github.com/prometheus/node_exporter) metrics
      exporter.
        * (optional) `enabled` property enables or disables this exporter.
          Default is `false`.
        * (optional) `port` is the port for Prometheus to connect to scrape.
          This is the internal port on the storage cluster VM.
        * (optional) `options` is a list of options to pass to the
          node exporter instance running on all nodes. The following
          collectors are force disabled, in addition to others disabled by
          default: textfile, wifi, xfs, zfs. The nfs collector is enabled if
          the file server is NFS, automatically.

## Remote Filesystems with Batch Shipyard Guide
Please see the [full guide](65-batch-shipyard-remote-fs.md) for information
on how this feature works in Batch Shipyard.

## Full template
A full template of a RemoteFS configuration file can be found
[here](https://github.com/Azure/batch-shipyard/tree/master/config_templates).
Note that these templates cannot be used as-is and must be modified to fit
your scenario.

## Sample Recipes
Sample recipes for both NFS and GlusterFS can be found in the
[recipes](https://github.com/Azure/batch-shipyard/tree/master/recipes) area.
