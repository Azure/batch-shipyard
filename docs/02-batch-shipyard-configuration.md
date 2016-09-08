# Batch Shipyard Configuration
This page contains in-depth details on how to configure the Batch Shipyard
tool.

## Configuration Files
The Batch Shipyard tool is driven by json configuration files:

1. Credentials - credentials for Azure Batch and Storage accounts
2. Global config - Batch Shipyard and Docker-specific configuration settings
3. Pool - Azure Batch pool configuration
4. Jobs - Azure Batch jobs and tasks configuration

Example config templates can be found in [this directory](../config\_templates)
of the repository.

### Credentials
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
        }
    }
}
```

The `credentials` property is where Azure Batch and Storage credentials
are defined.
* The `batch` property defines the Azure Batch account. Members under the
`batch` property can be found in the [Azure Portal](https://portal.azure.com)
under your Batch account.
* Multiple storage properties can be defined which references different Azure
Storage account credentials under the `storage` property. This may be needed
for more flexible configuration in other configuration files. In the example
above, we only have one storage account defined which is aliased by the
property name `mystorageaccount`.

An example credential json template can be found
[here](../config\_templates/credentials.json).

### Global Config
The global config schema is as follows:

```json
{
    "batch_shipyard": {
        "storage_account_settings": "mystorageaccount",
        "storage_entity_prefix": "shipyard",
        "use_shipyard_docker_image": true
    },
    "docker_registry": {
        "login": {
            "username": null,
            "password": null
        },
        "private": {
            "enabled": true,
            "storage_account_settings": "mystorageaccount",
            "container": "docker-private-registry",
            "docker_save_registry_file": "resources/docker-registry-v2.tar.gz",
            "docker_save_registry_image_id": "c6c14b3960bd",
            "allow_public_docker_hub_pull_on_missing": false
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
                    "container_path": "/shipyardvol",
                    "mount_options": [
                        "filemode=0777",
                        "dirmode=0777",
                        "nolock=true"
                    ]
                }
            }
        }
    }
}
```

The `batch_shipyard` property is used to set settings for the tool.
* `storage_account_settings` is a link to the alias of the storage account
specified, in this case, it is `mystorageaccount`. Batch shipyard requires a
storage account for storing metadata in order to execute across a distributed
environment.
* `storage_entity_prefix` property is used as a generic qualifier
to prefix storage containers (blob containers, tables, queues) with.
* `use_shipyard_docker_image` property is used to direct the tool to use
the Batch Shipyard docker image instead of installing software manually
in order to run the backend portion on the compute nodes. This can only
be set to `false` for Ubuntu 16.04 or higher.

The `docker_registry` property is used to configure Docker image distribution
options from public/private Docker hub and private registries.
* `login` controls docker login settings
* `private` property controls settings for private registries that are to be
run on compute nodes.
  * `enabled` property enables or disables the private registry
  * `storage_account_settings` is a link to the alias of the storage account
    specified that stores the private registry blobs.
  * `container` propery is the name of the Azure Blob container holding the
    private registry blobs.
  * `docker_save_registry_file` property represents a filesystem path to
    a gzipped tarball of the Docker registry:2 image as dumped by
    `docker save`. This is optional.
  * `docker_save_Registry_image_id` property represents the image id hash
    of the corresponding Docker registry:2 image. This is optional.
  * `allow_public_docker_hub_pull_on_missing` property allows pass through
    of Docker image retrieval to public Docker Hub if it is missing in the
    private registry.

The `data_replication` property is used to configure the internal image
replication mechanism between compute nodes within a compute pool. The
`non_peer_to_peer_concurrent_downloading` property specifies if it is ok
to allow unfettered concurrent downloading from the source registry among
all compute nodes. The following options apply to `peer_to_peer` data
replication options:
* `enabled` property enables or disables private peer-to-peer transfer. Note
that for compute pools with a relatively small number of VMs, peer-to-peer
transfer may not provide any benefit.
* `compression` property enables or disables compression of image files. It
is strongly recommended to keep this enabled.
* `concurrent_source_downloads` property specifies the number of
simultaneous downloads allowed to each image.
* `direct_download_seed_bias` property sets the number of direct download
seeds to prefer per image before switching to peer-to-peer transfer.

The `global_resources` property contains the Docker image and volume
configuration. `docker_images` is an array of docker images that should
be installed on every compute node when this configuration file is supplied
with the tool for creating a compute pool. Note that tags are supported.
`docker_volumes` property can consist of two different types of volumes:
`data_volumes` and `shared_data_volumes`. `data_volumes` can be of two
flavors, `host_path` is set to null or not. In the former, this is typically
used with the `VOLUME` keyword in Dockerfiles to initialize a data volume
with existing data inside the image. If `host_path` is set, then the path
on the host is mounted in the container at the path specified with
`container_path`.

`shared_data_volumes` property is for initializing persistent shared storage
volumes. In this example, `shipyardvol` is the alias of this volume:
* `volume_driver` property specifies the Docker Volume Driver to use.
Currently Batch Shipyard only supports the `volume_driver` as `azurefile`.
* `storage_account_settings` is a link to the alias of the storage account
specified that holds this Azure File Share.
* `azure_file_share_name` is the name of the share name on Azure Files.
* `container_path` is the path in the container to mount.
* `mount_options` are the mount options to pass to the mount command. Supported
options are documented
[here](https://github.com/Azure/azurefile-dockervolumedriver). It is
recommended to use `0777` for both `filemode` and `dirmode` as the `uid` and
`gid` cannot be reliably determined before the compute pool is allocated and
this volume will be mounted as the root user.

An example global config json template can be found
[here](../config\_templates/config.json).

### Pool
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
        "ssh_docker_tunnel": {
            "username": "docker",
            "ssh_public_key": null,
            "generate_tunnel_script": true
        },
        "gpu": {
            "nvidia_driver": {
                "version": "361.69",
                "source": "https://some.url"
            }
        },
        "additional_node_prep_commands": [
        ]
    }
}
```

The `pool_specification` property has the following members:
* `id` is the compute pool ID.
* `vm_size` is the
[Azure Virtual Machine Instance Size](https://azure.microsoft.com/en-us/pricing/details/virtual-machines/).
Please note that not all regions have every VM size available.
* `vm_count` is the number of compute nodes to allocate.
* `max_tasks_per_node` is the maximum number of concurrent tasks that can be
running at any one time on a compute node. This is optional and defaults to
a value of 1.
* `inter_node_communication_enabled` designates if this pool is set up for
inter-node communication. This must be set to `true` for any containers that
must communicate with each other such as MPI applications. This property
will be force enabled if peer-to-peer replication is enabled.
* `publisher` is the publisher name of the Marketplace VM image.
* `offer` is the offer name of the Marketplace VM image.
* `sku` is the sku name of the Marketplace VM image.
* `reboot_on_start_task_failed` allows Batch Shipyard to reboot the compute
node if there is a potential transient failure in node preparation.
* `block_until_all_global_resources_loaded` will block the node from entering
ready state until all Docker images are loaded.
* `ssh_docker_tunnel` is the property for creating a user to accomodate SSH
tunneling to the Docker Host>
  * `username` is the user to create on the compute nodes.
  * `ssh_public_key` is the path to an existing ssh public key to use. If not
    specified, a public/private key pair will be automatically generated.
  * `generate_tunnel_script` property directs script to generate an SSH tunnel
script for use with the compute nodes in the pool.
* `gpu` property defines additional information for nVidia GPU-enabled VMs:
  * `nvidia_driver` property contains the following required members:
    * `version` is the version number of the driver. This can be determined
      by the filename or from nVidia's website.
    * `source` is the source url to download the driver.
* `additional_node_prep_commands` is an array of additional commands to
execute on the compute node host as part of node preparation.

An example pool json template can be found
[here](../config\_templates/pool.json).

### Jobs
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
                    "remove_container_after_exit": true,
                    "additional_docker_run_options": [
                    ],
                    "infiniband": false,
                    "gpu": false,
                    "multi_instance": {
                        "num_instances": "pool_specification_vm_count",
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
* `id` is the job id to create. If the job already exists, the specified
`tasks` under the job will be added to the existing job.
* `multi_instance_auto_complete` enables auto-completion of the job for
which a multi-task instance is run. This allows automatic cleanup of the
Docker container in multi-instance tasks. This is defaulted to `true` and
is optional.
* `environment_variables` under the job are environment variables which will
be applied to all tasks operating under the job.
* `tasks` is an array of tasks to add to the job.
  * `id` is the task id. Note that if the task `id` is null then a generic
    task id will be assigned.
  * `depends_on` is an array of task ids for which this container invocation
    (task) depends on and must run to successful completion prior to this
    task executing.
  * `image` is the Docker image to use for this task
  * `name` is the name to assign to the container. This is optional if not
    instantiating a multi-instance task.
  * `labels` is an array of labels to apply to the container.
  * `environment_variables` are any additional task-specific environment
    variables that should be applied to the container.
  * `ports` is an array of port specifications that should be exposed to the
    host.
  * `data_volumes` is an array of `data_volume` aliases as defined in the
    global configuration file. These volumes will be mounted in the container.
  * `shared_data_volumes` is an array of `shared_data_volume` aliases as
    defined in the global configuration file. These volumes will be mounted
    in the container.
  * `resource_files` is an array of resource files that should be downloaded
    as part of the task. Each array entry contains the following information:
    * `file_path` is the path within the task working directory to place the
      file on the compute node.
    * `blob_source` is an accessible HTTP/HTTPS URL. This need not be an Azure
      Blob Storage URL.
    * `file_mode` if the file mode to set for the file on the compute node.
      This is optional.
  * `remove_container_after_exit` property specifies if the container should be
    automatically removed/cleaned up after it exits.
  * `additional_docker_run_options` is an array of addition Docker run options
    that should be passed to the Docker daemon when starting this container.
  * `infiniband` designates if this container requires access to the
    Infiniband/RDMA devices on the host. Note that this will automatically
    force the container to use the host network stack. If this property is
    set to `true`, ensure that the `pool_specification` property
    `inter_node_communication_enabled` is set to `true`.
  * `gpu` designates if this container requires access to the GPU devices on
    the host. If this property is set to `true`, Docker containers are
    instantiated via `nvidia-docker`.
  * `multi_instance` is a property indicating that this task is a
    multi-instance task. Additional information about multi-instance tasks
    and Batch Shipyard can be found
    [here](80-batch-shipyard-multi-instance-tasks.md). Do not define this
    property for tasks that are not multi-instance. Additional members of this
    property are:
    * `num_instances` is a property setting the number of compute node
      instances are required for this multi-instance task. This can be any one
      of the following:
      1. An integral number
      2. `pool_specification_vm_count` which is the `vm_count` specified in the
         pool configuration.
      3. `pool_current_dedicated` which is the instantaneous reading of the
         target pool's current dedicated count during this function invocation.
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
  * `entrypoint` is the property that can override the Docker image defined
    `ENTRYPOINT`. This is optional.
  * `command` is the command to execute in the Docker container context. If
    this task is a regular non-multi-instance task, then this is the command
    passed to the container context during `docker run`. If this task is a
    multi-instance task, then `command` is the application command and is
    executed with `docker exec` in the running Docker container context from
    the `coordination_command`. This is optional and may be null.

An example jobs json template can be found
[here](../config\_templates/jobs.json).

## Batch Shipyard Usage
Continue on to [Batch Shipyard Usage](03-batch-shipyard-usage.md).
