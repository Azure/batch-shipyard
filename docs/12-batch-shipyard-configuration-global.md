# Batch Shipyard Global Configuration
This page contains in-depth details on how to configure the global
json file for Batch Shipyard.

## Schema
The global config schema is as follows:

```json
{
    "batch_shipyard": {
        "storage_account_settings": "mystorageaccount",
        "storage_entity_prefix": "shipyard",
        "generated_sas_expiry_days": 90,
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
                        "dirmode=0777"
                    ]
                },
                "glustervol": {
                    "volume_driver": "glusterfs_on_compute",
                    "container_path": "$AZ_BATCH_NODE_SHARED_DIR/gfs",
                    "volume_type": "replica",
                    "volume_options": [
                        "performance.cache-size 1 GB",
                        "performance.cache-max-file-size 10 MB",
                        "performance.cache-refresh-timeout 61",
                    ]
                },
                "nfs_server": {
                    "volume_driver": "storage_cluster",
                    "container_path": "$AZ_BATCH_NODE_SHARED_DIR/nfs_server",
                    "mount_options": [
                    ]
                },
                "glusterfs_cluster": {
                    "volume_driver": "storage_cluster",
                    "container_path": "$AZ_BATCH_NODE_SHARED_DIR/glusterfs_cluster",
                    "mount_options": [
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
    to a private registry backed by Azure Storage blobs and where the
    private registry instances are hosted on the compute nodes themselves.
    * (required) `storage_account_settings` is a link to the alias of the
      storage account specified that stores the private registry blobs.
    * (required) `container` property is the name of the Azure Blob
      container holding the private registry blobs.
  * (optional) `allow_public_docker_hub_pull_on_missing` property allows
    pass-through of Docker image retrieval to public Docker Hub if it is
    missing in the private registry. This defaults to `false` if not
    specified. Note that this setting does not apply to a missing Docker
    image that is allowed to run via the job property
    `allow_run_on_missing_image`.

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

The `global_resources` property contains information regarding required
Docker images, volume configuration and data ingress information. This
property is required.

`docker_images` is an array of docker images that should be installed on
every compute node when this configuration file is supplied while creating
a compute pool. Image tags are supported. Image names should not include
private registry server names, as these will be automatically prepended. For
instance, if you have an image `abc/mytag` on your private registry
`myregistry-myorg.azurecr.io`, your image should be named in the
`docker_images` array as `abc/mytag` and not
`myregistry-myorg.azurecr.io/abc/mytag`. If this property is empty or
is not specified, no Docker images are pre-loaded on to compute nodes which
may increase scheduling latency. It is highly recommended not to leave this
property empty if possible. Note that if you do not specify Docker
images to preload, you must specify `allow_run_on_missing_image` as `true`
in your job specification.

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
`glusterfs_on_compute`. Note that `glusterfs_on_compute` is not a true Docker
Volume Driver. For this volume (`shipyardvol`), as this is an Azure File
shared volume, the `volume_driver` should be set as `azurefile`.
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
`glusterfs_on_compute` are GlusterFS volumes co-located on the VM's temporary
local disk space which is a shared resource. Sizes of the local temp disk for
each VM size can be found
[here](https://azure.microsoft.com/en-us/documentation/articles/virtual-machines-windows-sizes/).
If specifying a `glusterfs_on_compute` volume, you must enable internode
communication in the pool configuration file. These volumes have the following
properties:
* (required) `volume_driver` property should be set as `glusterfs_on_compute`.
* (required) `container_path` is the path in the container to mount.
* (optional) `volume_type` property defines the GlusterFS volume type.
Currently, `replica` is the only supported type.
* (optional) `volume_options` property defines additional GlusterFS volume
options to set.

`glusterfs_on_compute` volumes are mounted on the host at
`$AZ_BATCH_NODE_SHARED_DIR/.gluster/gv0`. Batch Shipyard will automatically
replace container path references in direct and storage-based data
ingress/egress with their host path equivalents.

Note that when resizing a pool with a `glusterfs_on_compute` shared file
systems that you must resize with the `pool resize` command in `shipyard.py`
and not with Azure Portal, Batch Labs or any other tool.

The third shared volume, `nfs_server` is an NFS server that is to be
mounted on to compute node hosts. The name `nfs_server` should match the
`remote_fs`:`storage_cluster`:`id` specified as your NFS server. These NFS
servers can be configured using the `fs` command in Batch Shipyard. These
volumes have the following properties:
* (required) `volume_driver` property should be set as `storage_cluster`.
* (required) `container_path` is the path in the container to mount.
* (optional) `mount_options` property defines additional mount options
to pass when mounting this file system to the compute node.

The fourth shared volume, `glusterfs_cluster` is a GlusterFS cluster that is
mounted on to compute node hosts. The name `glusterfs_cluster` should match
the `remote_fs`:`storage_cluster`:`id` specified as your GlusterFS cluster.
These GlusterFS clusters can be configured using the `fs` command in Batch
Shipyard. These volumes have the following properties:
* (required) `volume_driver` property should be set as `storage_cluster`.
* (required) `container_path` is the path in the container to mount.
* (optional) `mount_options` property defines additional mount options
to pass when mounting this file system to the compute node.

Finally, note that all `docker_volumes` can be omitted completely along with
one or all of `data_volumes` and `shared_data_volumes` if you do not require
this functionality.

## Full template
An full template of a credentials file can be found
[here](../config\_templates/config.json). Note that this template cannot
be used as-is and must be modified to fit your scenario.
