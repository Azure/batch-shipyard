# Batch Shipyard Configuration
This page contains in-depth details on how to configure the Batch Shipyard
toolkit.

## Configuration Files
Batch Shipyard is driven by the following json configuration files:

1. [Credentials](#cred) - credentials for Azure Batch and Storage accounts
2. [Global config](#global) - Batch Shipyard and Docker-specific configuration
settings
3. [Pool](#pool) - Azure Batch pool configuration
4. [Jobs](#jobs) - Azure Batch jobs and tasks configuration

Note that all potential properties are described here and that specifying
all such properties may result in invalid configuration as some properties
may be mutually exclusive. Please read the following document carefully when
crafting your configuration files.

Each property is marked with required or optional. Properties marked with
experimental should be considered as features for testing only.

Example config templates can be found in [this directory](../config\_templates)
of the repository. Each sample recipe also has a set of configuration files
that can be modified to your particular scenario.

### <a name="cred"></a>Credentials
The credentials schema is as follows:

```json
{
    "credentials": {
        "batch": {
            "account": "awesomebatchaccountname",
            "account_key": "batchaccountkey",
            "account_service_url": "https://awesomebatchaccountname.<region>.batch.azure.com/"
        },
        "storage": {
            "mystorageaccount": {
                "account": "awesomestorageaccountname",
                "account_key": "storageaccountkey",
                "endpoint": "core.windows.net"
            }
        },
        "docker_registry": {
            "hub": {
                "username": "myhublogin",
                "password": "myhubpassword"
            },
            "myserver-myorg.azurecr.io": {
                "username": "azurecruser",
                "password": "mypassword"
            }
        }
    }
}
```

The `credentials` property is where Azure Batch and Storage credentials
are defined.
* (required) The `batch` property defines the Azure Batch account. Members
under the `batch` property can be found in the
[Azure Portal](https://portal.azure.com) under your Batch account.
* (required) Multiple storage properties can be defined which references
different Azure Storage account credentials under the `storage` property. This
may be needed for more flexible configuration in other configuration files. In
the example above, we only have one storage account defined which is aliased
by the property name `mystorageaccount`. The alias (or storage account link
name) can be the same as the storage account name itself.
* (optional) `docker_registry` property defines logins for Docker registry
servers. This property does not need to be defined if you are using only
public repositories on Docker Hub. However, this is required if pulling from
authenticated private registries such as a secured Azure Container Registry
or private repositories on Docker Hub.
  * (optional) `hub` defines the login property to Docker Hub:
    * (optional) `username` username to log in to Docker Hub
    * (optional) `password` password associated with the username
  * (optional) `myserver-myorg.azurecr.io` is an example property that
    defines a private container registry to connect to. This is an example to
    connect to the [Azure Container Registry service](https://azure.microsoft.com/en-us/services/container-registry/).
    The private registry defined here should be defined as the `server`
    property in the `docker_registry`:`private` json object in the global
    configuration.
    * (optional) `username` username to log in to this registry
    * (optional) `password` password associated with this username

An example credential json template can be found
[here](../config\_templates/credentials.json).

### <a name="global"></a>Global Config
The global config schema is as follows:

```json
{
    "batch_shipyard": {
        "storage_account_settings": "mystorageaccount",
        "storage_entity_prefix": "shipyard",
        "generated_sas_expiry_days": 90,
        "use_shipyard_docker_image": true,
        "encryption" : {
            "enabled": true,
            "pfx": {
                "filename": "encrypt.pfx",
                "passphrase": "mysupersecretpassword",
                "sha1_thumbprint": "123456789..."
            },
            "public_key_pem": "encrypt.pem"
        }
    },
    "docker_registry": {
        "private": {
            "allow_public_docker_hub_pull_on_missing": true,
            "server": "myserver-myorg.azurecr.io",
            "azure_storage": {
                "storage_account_settings": "mystorageaccount",
                "container": "mydockerregistry"
            }
        }
    },
    "data_replication": {
        "peer_to_peer": {
            "enabled": true,
            "compression": true,
            "concurrent_source_downloads": 10,
            "direct_download_seed_bias": null
        },
        "non_peer_to_peer_concurrent_downloading": true
    },
    "global_resources": {
        "docker_images": [
            "busybox",
            "redis:3.2.3-alpine",
        ],
        "files": [
            {
                "source": {
                    "path": "/some/local/path/dir",
                    "include": ["*.dat"],
                    "exclude": ["*.bak"]
                },
                "destination": {
                    "shared_data_volume": "glustervol",
                    "relative_destination_path": "myfiles",
                    "data_transfer": {
                        "method": "multinode_scp",
                        "ssh_private_key": "id_rsa_shipyard",
                        "scp_ssh_extra_options": "-C -c aes256-gcm@openssh.com",
                        "rsync_extra_options": "",
                        "split_files_megabytes": 500,
                        "max_parallel_transfers_per_node": 2
                    }
                }
            },
            {
                "source": {
                    "path": "/some/local/path/bound/for/blob",
                    "include": ["*.bin"]
                },
                "destination": {
                    "storage_account_settings": "mystorageaccount",
                    "data_transfer": {
                        "container": "mycontainer",
                        "blobxfer_extra_options": "--no-computefilemd5"
                    }
                }
            },
            {
                "source": {
                    "path": "/another/local/path/dir",
                    "include": [],
                    "exclude": []
                },
                "destination": {
                    "relative_destination_path": "relpath/on/host",
                    "data_transfer": {
                        "method": "rsync+ssh",
                        "ssh_private_key": "id_rsa_shipyard",
                        "scp_ssh_extra_options": "-c aes256-gcm@openssh.com",
                        "rsync_extra_options": "-v"
                    }
                }
            }
        ],
        "docker_volumes": {
            "data_volumes": {
                "abcvol": {
                    "host_path": null,
                    "container_path": "/abc"
                },
                "hosttempvol": {
                    "host_path": "/tmp",
                    "container_path": "/hosttmp"
                }
            },
            "shared_data_volumes": {
                "shipyardvol": {
                    "volume_driver": "azurefile",
                    "storage_account_settings": "mystorageaccount",
                    "azure_file_share_name": "shipyardshared",
                    "container_path": "$AZ_BATCH_NODE_SHARED_DIR/azfile",
                    "mount_options": [
                        "filemode=0777",
                        "dirmode=0777",
                        "nolock=true"
                    ]
                },
                "glustervol": {
                    "volume_driver": "glusterfs",
                    "container_path": "$AZ_BATCH_NODE_SHARED_DIR/gfs",
                    "volume_type": "replica",
                    "volume_options": [
                        "performance.cache-size 1 GB",
                        "performance.cache-max-file-size 10 MB",
                        "performance.cache-refresh-timeout 61",
                    ]
                }
            }
        }
    }
}
```

The `batch_shipyard` property is used to set settings for the tool.
* (required) `storage_account_settings` is a link to the alias of the storage
account specified, in this case, it is `mystorageaccount`. Batch shipyard
requires a storage account for storing metadata in order to execute across a
distributed environment.
* (optional) `storage_entity_prefix` property is used as a generic qualifier
to prefix storage containers (blob containers, tables, queues) with. If not
specified, defaults to `shipyard`.
* (optional) `generated_sas_expiry_days` property is used to set the number of
days any generated SAS key by Batch Shipyard is valid for. The default is 30
days. This is useful if you have long-lived pools and want to ensure that
SAS keys are valid for longer periods of time.
* (optional) `use_shipyard_docker_image` property is used to direct the toolkit
to use the Batch Shipyard docker image instead of installing software manually
in order to run the backend portion on the compute nodes. It is strongly
recommended to omit this or to set to `true`. This can only be set to `false`
for Ubuntu 16.04 or higher. This is defaulted to `true`.
* (optional) `encryption` object is used to define credential encryption which
contains the following members:
  * (required) `enabled` property enables or disables this feature.
  * (required) `pfx` object defines the PFX certificate
    * (required) `filename` property is the full path and name to the PFX
      certificate
    * (required) `passphrase` property is the passphrase for the PFX
      certificate. This cannot be empty.
    * (optional) `sha1_thumbprint` is the SHA1 thumbprint of the
      certificate. If the PFX file is created using the `cert create` command,
      then the SHA1 thumbprint is output. It is recommended to populate this
      property such that it does not have to be generated when needed for
      encryption.
  * (optional) `public_key_pem` property is the full path and name to the
    RSA public key in PEM format. If the PFX file is created using the
    `cert create` command, then this file is generated along with the PFX
    file. It is recommended to populate this property with the PEM file path
    such that it does not have to be generated when needed for encryption.

The `docker_registry` property is used to configure Docker image distribution
options from public/private Docker hub and private registries.
* (optional) `private` property controls settings for interacting with private
registries. There are three kinds of private registries that are supported:
(1) private registries hosted on Docker Hub, (2) Internet accessible
registries such as those hosted by the
[Azure Container Registry](https://azure.microsoft.com/en-us/services/container-registry/)
service and (3) [private registry instances backed to
Azure Blob Storage](https://azure.microsoft.com/en-us/documentation/articles/virtual-machines-linux-docker-registry-in-blob-storage/)
and are run on compute nodes. To use private registries hosted on Docker Hub,
no additional properties need to be specified here, instead, specify your
Docker Hub login information in the credentials json. To specify a private
registry other than on Docker Hub, a json property named `server` should be
defined. To use a private registry backed by Azure Blob Storage, define a
json object named `azure_storage`. Note that a maximum of only one of these
three types private registries may be specified at once. The following
describes members of the non-Docker Hub private registries supported:
  * (optional) `server` object is a property that is the fully-qualified host
    name to a private registry server. A specific port other than 80 can be
    specified using a `:` separator, e.g.,
    `mydockerregistry.com:8080`. Port 80 is the default if no port is
    specified. The value of this property should have an associated login
    in the credentials json file.
  * (optional) `azure_storage` object is to define settings for connecting
    to a private registry backed by Azure Storate blobs and where the
    private registry instances are hosted on the compute nodes themselves.
    * (required) `storage_account_settings` is a link to the alias of the
      storage account specified that stores the private registry blobs.
    * (required) `container` property is the name of the Azure Blob
      container holding the private registry blobs.
  * (optional) `allow_public_docker_hub_pull_on_missing` property allows
    pass-through of Docker image retrieval to public Docker Hub if it is
    missing in the private registry. This defaults to `false` if not
    specified.

The `data_replication` property is used to configure the internal image
replication mechanism between compute nodes within a compute pool. The
`non_peer_to_peer_concurrent_downloading` property specifies if it is ok
to allow unfettered concurrent downloading from the source registry among
all compute nodes. The following options apply to `peer_to_peer` data
replication options:
* (optional) `enabled` property enables or disables private peer-to-peer
transfer. Note that for compute pools with a relatively small number of VMs,
peer-to-peer transfer may not provide any benefit and is recommended to be
disabled in these cases. Compute pools with large number of VMs and especially
in the case of an Azure Storage-backed private registry can benefit from
peer-to-peer image replication.
* `compression` property enables or disables compression of image files. It
is strongly recommended to keep this enabled.
* `concurrent_source_downloads` property specifies the number of
simultaneous downloads allowed to each image.
* `direct_download_seed_bias` property sets the number of direct download
seeds to prefer per image before switching to peer-to-peer transfer.

The `global_resources` is a required property that contains the Docker image
and volume configuration. `docker_images` is an array of docker images that
should be installed on every compute node when this configuration file is
supplied with the tool for creating a compute pool. Note that tags are
supported.

`files` is an optional property that specifies data that should be ingressed
from a location accessible by the local machine (i.e., machine invoking
`shipyard.py` to a shared file system location accessible by compute nodes
in the pool or Azure Blob or File Storage). `files` is a json list of objects,
which allows for multiple sources to destinations to be ingressed during the
same invocation. Note that no Azure Batch environment variables
(i.e., `$AZ_BATCH_`-style environment variables) are available as path
arguments since ingress actions performed within `files` are done locally
on the machine invoking `shipyard.py`. Each object within the `files` list
contains the following members:
* (required) `source` property contains the following members:
  * (required) `path` is a local path. A single file or a directory
    can be specified. Filters below will be ignored if `path` is a file and
    not a directory.
  * (optional) `include` is an array of
    [Unix shell-style wildcard filters](https://docs.python.org/3.5/library/fnmatch.html)
    where only files matching a filter are included in the data transfer.
    Filters specified in `include` have precedence over `exclude` described
    next. `include` can only have a maximum of 1 filter for ingress to Azure
    Blob Storage. In this example, all files ending in `.dat` are ingressed.
  * (optional) `exclude` is an array of
    [Unix shell-style wildcard filters](https://docs.python.org/3.5/library/fnmatch.html)
    where files matching a filter are excluded from the data transfer. Filters
    specified in `include` have precedence over filters specified in
    `exclude`. `exclude` cannot be specified for ingress into Azure Blob
    Storage. In this example, all files ending in `.bak` are skipped for
    ingress.
* (required) `destination` property contains the following members:
  * (required or optional) `shared_data_volume` or `storage_account_settings`
    for data ingress to a GlusterFS volume or Azure Blob or File Storage. If
    you are ingressing to a pool with only one compute node, you may omit
    `shared_data_volume`. Otherwise, you may specify one or the other, but
    not both in the same object. Please see below in the
    `shared_data_volumes` for information on how to set up a GlusterFS share.
  * (required or optional) `relative_destination_path` specifies a relative
    destination path to place the files, with respect to the target root.
    If transferring to a `shared_data_volume` then this is relative to the
    GlusterFS volume root. If transferring to a pool with one single node in
    it, thus, no `shared_data_volume` is specified in the prior property, then
    this is relative to
    [$AZ_BATCH_NODE_ROOT_DIR](https://azure.microsoft.com/en-us/documentation/articles/batch-api-basics/#files-and-directories).
    To place files directly in `$AZ_BATCH_NODE_ROOT_DIR` (not recommended),
    you can specify this property as empty string when not ingressing to
    a `shared_data_volume`. Note that if `scp` is selected while attempting
    to transfer directly to this aforementioned path, then `scp` will fail
    with exit code of 1 but the transfer will have succeeded (this is due
    to some of the permission options). If this property is not specified for
    a `shared_data_volume`, then files will be placed directly in the
    GlusterFS volume root. This property cannot be specified for a Azure
    Storage destination (i.e., `storage_account_settings`).
  * (required) `data_transfer` specifies how the transfer should take place.
    The following list contains members for GlusterFS ingress when a GlusterFS
    volume is provided for `shared_data_volume` (see below for ingressing to
    Azure Blob or File Storage):
    * (required) `method` specified which method should be used to ingress
      data, which should be one of: `scp`, `multinode_scp`, `rsync+ssh` or
      `multinode_rsync+ssh`. `scp` will use secure copy to copy a file or a
      directory (recursively) to the remote share path. `multinode_scp` will
      attempt to simultaneously transfer files to many compute nodes using
      `scp` at the same time to speed up data transfer. `rsync+ssh` will
      perform an rsync of files through SSH. `multinode_rsync+ssh` will
      attempt to simultaneously transfer files using `rsync` to many compute
      nodes at the same time to speed up data transfer with. Note that you may
      specify the `multinode_*` methods even with only 1 compute node in a
      pool which will allow you to take advantage of
      `max_parallel_transfers_per_node` below.
    * (optional) `ssh_private_key` location of the SSH private key for the
      username specified in the `pool_specification`:`ssh` section when
      connecting to compute nodes. The default is `id_rsa_shipyard`, if
      omitted, which is automatically generated if no SSH key is specified
      when an SSH user is added to a pool.
    * (optional) `scp_ssh_extra_options` are any extra options to pass to
      `scp` or `ssh` for `scp`/`multinode_scp` or
      `rsync+ssh`/`multinode_rsync+ssh` methods, respectively. In the example
      above, `-C` enables compression and `-c aes256-gcm@openssh.com`
      is passed to `scp`, which can potentially increase the transfer speed by
      selecting the `aes256-gcm@openssh.com` cipher which can exploit Intel
      AES-NI.
    * (optional) `rsync_extra_options` are any extra options to pass to
      `rsync` for the `rsync+ssh`/`multinode_rsync+ssh` transfer methods. This
      property is ignored for non-rsync transfer methods.
    * (optional) `split_files_megabytes` splits files into chunks with the
      specified size in MiB. This can potentially help with very large files.
      This option forces the transfer `method` to `multinode_scp`.
      Note that the destination file system must be able to accommodate
      up to 2x the size of files which are split. Additionally, transfers
      involving files which are split will incur reconstruction costs after
      the transfer is complete, which will increase the total end-to-end
      ingress time. However, in certain scenarios, by splitting files and
      transferring chunks in parallel along with reconstruction may end up
      being faster than transferring a large file without chunking.
    * (optional) `max_parallel_transfers_per_node` is the maximum number of
      parallel transfer to invoke per node with the
      `multinode_scp`/`multinode_rsync+ssh` methods. For example, if there
      are 3 compute nodes in the pool, and `2` is given for this option, then
      there will be up to 2 scp sessions in parallel per compute node for a
      maximum of 6 concurrent scp sessions to the pool. The default is 1 if
      not specified or omitted.
  * (required) `data_transfer` specifies how the transfer should take place.
    When Azure Blob or File Storage is selected as the destination for data
    ingress, [blobxfer](https://github.com/Azure/blobxfer) is invoked. The
    following list contains members for Azure Blob or File Storage ingress
    when a storage account link is provided for `storage_account_settings`:
    * (required) `container` or `file_share` is required when uploading to
      Azure Blob Storage or Azure File Storage, respectively. `container`
      specifies which container to upload to for Azure Blob Storage while
      `file_share` specifies which file share to upload to for Azure File
      Storage. Only one of these properties can be specified per
      `data_transfer` object. The container or file share need not be created
      beforehand.
    * (optional) `blobxfer_extra_options` are any extra options to pass to
      `blobxfer`. In the example above, `--no-computefilemd5` will force
      `blobxfer` to skip MD5 calculation on files ingressed.

`docker_volumes` is an optional property that can consist of two
different types of volumes: `data_volumes` and `shared_data_volumes`.
`data_volumes` can be of two flavors depending upon if `host_path` is set to
null or not. In the former, this is typically used with the `VOLUME` keyword
in Dockerfiles to initialize a data volume with existing data inside the
image. If `host_path` is set, then the path on the host is mounted in the
container at the path specified with `container_path`.

`shared_data_volumes` is an optional property for initializing persistent
shared storage volumes. In the first shared volume, `shipyardvol` is the alias
of this volume:
* `volume_driver` property specifies the Docker Volume Driver to use.
Currently Batch Shipyard only supports the `volume_driver` as `azurefile` or
`glusterfs`. Note that `glusterfs` is not a true Docker Volume Driver. For
this volume (`shipyardvol`), as this is an Azure File shared volume, the
`volume_driver` should be set as `azurefile`.
* `storage_account_settings` is a link to the alias of the storage account
specified that holds this Azure File Share.
* `azure_file_share_name` is the name of the share name on Azure Files. Note
that the Azure File share must be created beforehand, the toolkit does not
create Azure File shares, it only mounts them to the compute nodes.
* `container_path` is the path in the container to mount.
* `mount_options` are the mount options to pass to the mount command. Supported
options are documented
[here](https://github.com/Azure/azurefile-dockervolumedriver). It is
recommended to use `0777` for both `filemode` and `dirmode` as the `uid` and
`gid` cannot be reliably determined before the compute pool is allocated and
this volume will be mounted as the root user.

Note that when using `azurefile` for a shared data volume, the storage account
that holds the file share must reside within the same Azure region as the
Azure Batch compute pool. Attempting to mount an Azure File share that is
cross-region will result in failure as current Linux Samba clients do not
support share level encryption at this time.

The second shared volue, `glustervol`, is a
[GlusterFS](https://www.gluster.org/) network file system. Please note that
GlusterFS volumes are located on the VM's temporary local disk space which is
a shared resource. Sizes of the local temp disk for each VM size can be found
[here](https://azure.microsoft.com/en-us/documentation/articles/virtual-machines-windows-sizes/).
If specifying a GlusterFS volume, you must enable internode communication
in the pool configuration file. These volumes have the following properties:
* (required) `volume_driver` property should be set as `glusterfs`.
* (required) `container_path` is the path in the container to mount.
* (optional) `volume_type` property defines the GlusterFS volume type.
Currently, `replica` is the only supported type.
* (optional) `volume_options` property defines additional GlusterFS volume
options to set.

Note that when resizing a pool with a GlusterFS shared file system, that
you must resize with the `pool resize` command in `shipyard.py` and not with
Azure Portal, Batch Explorer or any other tool.

Finally, note that all `docker_volumes` can be omitted completely along with
one or all of `data_volumes` and `shared_data_volumes` if you do not require
this functionality.

An example global config json template can be found
[here](../config\_templates/config.json).

### <a name="pool"></a>Pool
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
    the compute nodes to expire. The default is 7 days from invocation time.
  * (optional) `ssh_public_key` is the path to an existing SSH public key to
    use. If not specified, an RSA public/private keypair will be automatically
    generated only on Linux. If this is `null` or not specified on Windows,
    the SSH user is not created.
  * (optional) `generate_docker_tunnel_script` property directs script to
    generate an SSH tunnel script that can be used to connect to the remote
    Docker engine running on a compute node.
  * (optional) `generated_file_export_path` is the path to export the
    generated RSA keypair and docker tunnel script to. If omitted, the
    current directory is used.
  * (experimental) `hpn_server_swap` property enables an OpenSSH server with
    [HPN patches](http://www.psc.edu/index.php/hpn-ssh) to be swapped with the
    standard distribution OpenSSH server. This is not supported on all
    Linux distributions and may be force disabled.
* (required for `STANDARD_NV` instances, optional for `STANDARD_NC` instances)
`gpu` property defines additional information for NVIDIA GPU-enabled VMs:
  * `nvidia_driver` property contains the following required members:
    * `source` is the source url to download the driver.
* (optional) `additional_node_prep_commands` is an array of additional commands
to execute on the compute node host as part of node preparation. This can
be empty or omitted.

An example pool json template can be found
[here](../config\_templates/pool.json).

### <a name="jobs"></a>Jobs
The jobs schema is as follows:

```json
{
    "job_specifications": [
        {
            "id": "dockerjob",
            "multi_instance_auto_complete": true,
            "environment_variables": {
                "abc": "xyz"
            },
            "input_data": {
                "azure_batch": [
                    {
                        "job_id": "someotherjob",
                        "task_id": "task-a",
                        "include": ["wd/*.dat"],
                        "exclude": ["*.txt"],
                        "destination": null
                    }
                ],
                "azure_storage": [
                    {
                        "storage_account_settings": "mystorageaccount",
                        "container": "jobcontainer",
                        "include": ["jobdata*.bin"],
                        "destination": "$AZ_BATCH_NODE_SHARED_DIR/jobdata",
                        "blobxfer_extra_options": null
                    }
                ]
            },
            "tasks": [
                {
                    "id": null,
                    "depends_on": [
                    ],
                    "image": "busybox",
                    "name": null,
                    "labels": [],
                    "environment_variables": {
                        "def": "123"
                    },
                    "ports": [],
                    "data_volumes": [
                        "contdatavol",
                        "hosttempvol"
                    ],
                    "shared_data_volumes": [
                        "azurefilevol"
                    ],
                    "resource_files": [
                        {
                            "file_path": "",
                            "blob_source": "",
                            "file_mode": ""
                        }
                    ],
                    "input_data": {
                        "azure_batch": [
                            {
                                "job_id": "previousjob",
                                "task_id": "mytask1",
                                "include": ["wd/output/*.bin"],
                                "exclude": ["*.txt"],
                                "destination": null
                            }
                        ],
                        "azure_storage": [
                            {
                                "storage_account_settings": "mystorageaccount",
                                "container": "taskcontainer",
                                "include": ["taskdata*.bin"],
                                "destination": "$AZ_BATCH_NODE_SHARED_DIR/taskdata",
                                "blobxfer_extra_options": null
                            }
                        ]
                    },
                    "output_data": {
                        "azure_storage": [
                            {
                                "storage_account_settings": "mystorageaccount",
                                "container": "output",
                                "source": null,
                                "include": ["**/out*.dat"],
                                "blobxfer_extra_options": null
                            }
                        ]
                    },
                    "remove_container_after_exit": true,
                    "additional_docker_run_options": [
                    ],
                    "infiniband": false,
                    "gpu": false,
                    "multi_instance": {
                        "num_instances": "pool_current_dedicated",
                        "coordination_command": null,
                        "resource_files": [
                            {
                                "file_path": "",
                                "blob_source": "",
                                "file_mode": ""
                            }
                        ]
                    },
                    "entrypoint": null,
                    "command": ""
                }
            ]
        }
    ]
}
```

`job_specifications` array consists of jobs to create.
* (required) `id` is the job id to create. If the job already exists, the
specified `tasks` under the job will be added to the existing job.
* (optional) `multi_instance_auto_complete` enables auto-completion of the job
for which a multi-task instance is run. This allows automatic cleanup of the
Docker container in multi-instance tasks. This is defaulted to `true` when
multi-instance tasks are specified.
* (optional) `environment_variables` under the job are environment variables
which will be applied to all tasks operating under the job. Note that
environment variables are not expanded and are passed as-is. You will need
to source the environment file `$AZ_BATCH_TASK_WORKING_DIR/.shipyard.envlist`
in a shell within the docker `command` or `entrypoint` if you want any
environment variables to be expanded.
* (optional) `input_data` is an object containing data that should be
ingressed for the job. Any `input_data` defined at this level will be
downloaded for this job which can be run on any number of compute nodes
depending upon the number of constituent tasks and repeat invocations. However,
`input_data` is only downloaded once per job invocation on a compute node.
For example, if `job-1`:`task-1` is run on compute node A and then
`job-1`:`task-2` is run on compute node B, then this `input_data` is ingressed
to both compute node A and B. However, if `job-1`:`task-3` is then run on
compute node A after `job-1`:`task-1`, then the `input_data` is not
transferred again. This object currently supports `azure_batch` and
`azure_storage` as members.
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
* (required) `tasks` is an array of tasks to add to the job.
  * (optional) `id` is the task id. Note that if the task `id` is null or
    empty then a generic task id will be assigned. The generic task id is
    formatted as `dockertask-NNN` where `NNN` starts from `000` and is
    increased by 1 for each task added to the same job.
  * (optional) `depends_on` is an array of task ids for which this container
    invocation (task) depends on and must run to successful completion prior
    to this task executing.
  * (required) `image` is the Docker image to use for this task
  * (optional) `name` is the name to assign to the container. If not
    specified, the value of the `id` property will be used for `name`.
  * (optional) `labels` is an array of labels to apply to the container.
  * (optional) `environment_variables` are any additional task-specific
    environment variables that should be applied to the container. Note that
    environment variables are not expanded and are passed as-is. You will
    need to source the environment file
    `$AZ_BATCH_TASK_WORKING_DIR/.shipyard.envlist` in a shell within the
    docker `command` or `entrypoint` if you want any environment variables
    to be expanded.
  * (optional) `ports` is an array of port specifications that should be
    exposed to the host.
  * (optional) `data_volumes` is an array of `data_volume` aliases as defined
    in the global configuration file. These volumes will be mounted in the
    container.
  * (optional) `shared_data_volumes` is an array of `shared_data_volume`
    aliases as defined in the global configuration file. These volumes will be
    mounted in the container.
  * (optional) `resource_files` is an array of resource files that should be
    downloaded as part of the task. Each array entry contains the following
    information:
    * `file_path` is the path within the task working directory to place the
      file on the compute node.
    * `blob_source` is an accessible HTTP/HTTPS URL. This need not be an Azure
      Blob Storage URL.
    * `file_mode` if the file mode to set for the file on the compute node.
      This is optional.
  * (optional) `input_data` is an object containing data that should be
    ingressed for this specific task. This object currently supports
    `azure_batch` and  `azure_storage` as members. Note for multi-instance
    tasks, transfer of `input_data` is only applied to the task running the
    application command.
    * `azure_batch` contains the following members:
      * (required) `job_id` the job id of the task
      * (required) `task_id` the id of the task to fetch files from
      * (optional) `include` is an array of include filters
      * (optional) `exclude` is an array of exclude filters
      * (optional) `destination` is the destination path to place the files.
        If `destination` is not specified at this level, then files are
        defaulted to download into `$AZ_BATCH_TASK_WORKING_DIR`.
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
      * (optional) `destination` property defines where to place the
        downloaded files on the host file system. Unlike the job-level
        version of `input_data`, this `destination` property can be ommitted.
        If `destination` is not specified at this level, then files are
        defaulted to download into `$AZ_BATCH_TASK_WORKING_DIR`. Please note
        that you should not specify a destination that is on a shared file
        system. If you require ingressing to a shared file system location
        like a GlusterFS volume, then use the global configuration `files`
        property and the `data ingress` command.
      * (optional) `blobxfer_extra_options` are any extra options to pass to
        `blobxfer`.
  * (optional) `output_data` is an object containing data that should be
    egressed for this specific task if and only if the task completes
    successfully. This object currently only supports `azure_storage` as a
    member. Note for multi-instance tasks, transfer of `output_data` is only
    applied to the task running the application command.
    * `azure_storage` contains the following members:
      * (required) `storage_account_settings` contains a storage account link
        as defined in the credentials json.
      * (required) `container` or `file_share` is required when uploading to
        Azure Blob Storage or Azure File Storage, respectively. `container`
        specifies which container to upload to for Azure Blob Storage while
        `file_share` specifies which file share to upload to for Azure File
        Storage. Only one of these properties can be specified per
        `data_transfer` object.
      * (optional) `source` property defines which directory to upload to
        Azure storage. If `source` is not specified, then `source` is
        defaulted to `$AZ_BATCH_TASK_DIR`.
      * (optional) `include` property defines an optional include filter.
        Although this property is an array, it is only allowed to have 1
        maximum filter.
      * (optional) `blobxfer_extra_options` are any extra options to pass to
        `blobxfer`.
  * (optional) `remove_container_after_exit` property specifies if the
    container should be automatically removed/cleaned up after it exits. This
    defaults to `false`.
  * (optional) `additional_docker_run_options` is an array of addition Docker
    run options that should be passed to the Docker daemon when starting this
    container.
  * (optional) `infiniband` designates if this container requires access to the
    Infiniband/RDMA devices on the host. Note that this will automatically
    force the container to use the host network stack. If this property is
    set to `true`, ensure that the `pool_specification` property
    `inter_node_communication_enabled` is set to `true`. If you are
    selecting `SUSE SLES-HPC` Marketplace images, then you will need to
    ensure that the Intel MPI redistributable that is used to build the
    application is present in the container. The Intel MPI libraries that
    are present by default on the `SUSE SLES-HPC` Marketplace images are
    not current and may cause issues if used directly with Infiniband-enabled
    Docker images. If you still wish to use the host Intel MPI libraries,
    then specify `-v /opt/intel:/opt/intel:ro` under
    `additional_docker_run_options`.
  * (optional) `gpu` designates if this container requires access to the GPU
    devices on the host. If this property is set to `true`, Docker containers
    are instantiated via `nvidia-docker`. This requires N-series VM instances.
  * (optional) `multi_instance` is a property indicating that this task is a
    multi-instance task. This is required if the Docker image is an MPI
    program. Additional information about multi-instance tasks and Batch
    Shipyard can be found
    [here](80-batch-shipyard-multi-instance-tasks.md). Do not define this
    property for tasks that are not multi-instance. Additional members of this
    property are:
    * `num_instances` is a property setting the number of compute node
      instances are required for this multi-instance task. This can be any one
      of the following:
      1. An integral number
      2. `pool_current_dedicated` which is the instantaneous reading of the
         target pool's current dedicated count during this function invocation.
      3. `pool_specification_vm_count` which is the `vm_count` specified in the
         pool configuration.
    * `coordination_command` is the coordination command this is run by each
      instance (compute node) of this multi-instance task prior to the
      application command. This command must not block and must exit
      successfully for the multi-instance task to proceed. This is the command
      passed to the container in `docker run` for multi-instance tasks. This
      docker container instance will automatically be daemonized. This is
      optional and may be null.
    * `resource_files` is an array of resource files that should be downloaded
      as part of the multi-instance task. Each array entry contains the
      following information:
        * `file_path` is the path within the task working directory to place
          the file on the compute node.
        * `blob_source` is an accessible HTTP/HTTPS URL. This need not be an
          Azure Blob Storage URL.
        * `file_mode` if the file mode to set for the file on the compute node.
          This is optional.
  * (optional) `entrypoint` is the property that can override the Docker image
    defined `ENTRYPOINT`.
  * (optional) `command` is the command to execute in the Docker container
    context. If this task is a regular non-multi-instance task, then this is
    the command passed to the container context during `docker run`. If this
    task is a multi-instance task, then this `command` is the application
    command and is executed with `docker exec` in the running Docker container
    context from the `coordination_command` in the `multi_instance` property.
    This property may be null.

An example jobs json template can be found
[here](../config\_templates/jobs.json).

## Batch Shipyard Usage
Continue on to [Batch Shipyard Usage](20-batch-shipyard-usage.md).
