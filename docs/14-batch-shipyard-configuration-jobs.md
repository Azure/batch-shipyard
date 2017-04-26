# Batch Shipyard Jobs Configuration
This page contains in-depth details on how to configure the jobs
json file for Batch Shipyard.

## Schema
The jobs schema is as follows:

```json
{
    "job_specifications": [
        {
            "id": "dockerjob",
            "auto_complete": false,
            "environment_variables": {
                "abc": "xyz"
            },
            "environment_variables_keyvault_secret_id": "https://myvault.vault.azure.net/secrets/myjobenv",
            "max_task_retries": 3,
            "allow_run_on_missing_image": false,
            "user_identity": {
                "default_pool_admin": true,
                "specific_user": {
                    "uid": 1000,
                    "gid": 1000
                }
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
                        "taskid-a", "taskid-b", "taskid-c"
                    ],
                    "depends_on_range": [
                        1, 10
                    ],
                    "image": "busybox",
                    "name": null,
                    "labels": [],
                    "environment_variables": {
                        "def": "123"
                    },
                    "environment_variables_keyvault_secret_id": "https://myvault.vault.azure.net/secrets/mytaskenv",
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
                    "shm_size": "256m",
                    "additional_docker_run_options": [
                    ],
                    "infiniband": false,
                    "gpu": false,
                    "max_task_retries": 3,
                    "retention_time": "1.12:00:00",
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
* (optional) `auto_complete` enables auto-completion of the job for which
the specified tasks are run under. When run with multi-instance tasks, this
performs automatic cleanup of the Docker container which is run in detached
mode. The default is `false`.
* (optional) `environment_variables` under the job are environment variables
which will be applied to all tasks operating under the job. Note that
environment variables are not expanded and are passed as-is. You will need
to source the environment file `$AZ_BATCH_TASK_WORKING_DIR/.shipyard.envlist`
in a shell within the docker `command` or `entrypoint` if you want any
environment variables to be expanded.
* (optional) `environment_variables_keyvault_secret_id` under the job are
environment variables stored in KeyVault that should be applied to all tasks
operating under the job. The secret stored in KeyVault must be a valid json
string, e.g., `{ "env_var_name": "env_var_value" }`.
* (optional) `max_task_retries` sets the maximum number of times that
Azure Batch should retry all tasks in this job for. By default, Azure Batch
does not retry tasks that fail (i.e. `max_task_retries` is 0).
* (optional) `allow_run_on_missing_image` allows tasks with a Docker image reference
that was not pre-loaded on to the compute node via
`global_resources`:`docker_images` in the global configuration to be able to
run. Note that you should attempt to specify all Docker images that you intend
to run in the `global_resources`:`docker_images` property in the global
configuration to minimize scheduling to task execution latency.
* (optional) `user_identity` property is to define which user to run the
container as. By default, if this property is not defined, the container will
be run as the root user. However, it may be required to run the container
with a different user, especially if integrating with storage cluster and
shared file systems. All first-level properties within `user_identity` are
mutually exclusive of one another.
  * (optional) `default_pool_admin` specifies if the container should be
    run with the default pool (compute node) administrator user that Azure
    Batch automatically configures upon compute node start. This user will
    have passwordless sudo access.
  * (optional) `specific_user` specifies to run the container as a specific
    user.
    * (required) `uid` is the user id of the user
    * (required) `gid` is the group id of the user
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
    formatted as `dockertask-NNNNN` where `NNNNN` starts from `00000` and is
    increased by 1 for each task added to the same job. If there are more
    than `99999` autonamed tasks in a job then the numbering is not
    padded for tasks exceeding 5 digits.
  * (optional) `depends_on` is an array of task ids for which this container
    invocation (task) depends on and must run to successful completion prior
    to this task executing.
  * (optional) `depends_on_range` is an array with exactly two integral
    elements containing a task `id` range for which this task is dependent
    upon, i.e., the start `id` and the end `id` for which this task depends
    on. Although task `id`s are always strings, the dependent task `id`s for
    ranges must be expressed by their integral representation for this
    property. This also implies that task `id`s for which this task depends
    on must be integral in nature. For example, if `depends_on_range` is set
    to `[1, 10]` (note the integral members), then there should be task
    `id`s of `"1"`, `"2"`, ... `"10"` within the job. Once these dependent
    tasks complete successfully, then this specified task will execute.
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
  * (optional) `environment_variables_keyvault_secret_id` are any additional
    task-specific environment variables that should be applied to the
    container but are stored in KeyVault. The secret stored in KeyVault must
    be a valid json string, e.g., `{ "env_var_name": "env_var_value" }`.
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
  * (optional) `shm_size` property specifies the size of `/dev/shm` in
    the container. The default is `64m`. The postfix unit can be designated
    as `b` (bytes), `k` (kilobytes), `m` (megabytes), or `g` (gigabytes). This
    value may need to be increased from the default of `64m` for certain
    Docker applications, including multi-instance tasks using Intel MPI
    (see [issue #8](https://github.com/Azure/batch-shipyard/issues/8)).
  * (optional) `additional_docker_run_options` is an array of addition Docker
    run options that should be passed to the Docker daemon when starting this
    container.
  * (optional) `infiniband` designates if this container requires access to the
    Infiniband/RDMA devices on the host. Note that this will automatically
    force the container to use the host network stack. If this property is
    set to `true`, ensure that the `pool_specification` property
    `inter_node_communication_enabled` is set to `true`.
  * (optional) `gpu` designates if this container requires access to the GPU
    devices on the host. If this property is set to `true`, Docker containers
    are instantiated via `nvidia-docker`. This requires N-series VM instances.
  * (optional) `max_task_retries` sets the maximum number of times that
    Azure Batch should retry this task for. This overrides the job-level task
    retry count. By default, Azure Batch does not retry tasks that fail
    (i.e. `max_task_retries` is 0).
  * (optional) `retention_time` sets the timedelta to retain the task
    directory on the compute node where it ran after the task completes.
    The format for this property is a timedelta with a string representation
    of "d.HH:mm:ss". For example, "1.12:00:00" would allow the compute node
    to clean up this task's directory 36 hours after the task completed. The
    default, if unspecified, is effectively infinite - i.e., task data is
    retained forever on the compute node that ran the task.
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

## Full template
An full template of a credentials file can be found
[here](../config\_templates/jobs.json). Note that this template cannot
be used as-is and must be modified to fit your scenario.
