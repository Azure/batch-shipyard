# Batch Shipyard Jobs Configuration
This page contains in-depth details on how to configure the jobs
configuration file for Batch Shipyard.

## Schema
The jobs schema is as follows:

```yaml
job_specifications:
- id: containerjob
  auto_complete: true
  environment_variables:
    abc: xyz
  environment_variables_keyvault_secret_id: https://myvault.vault.azure.net/secrets/myjobenv
  max_task_retries: 1
  max_wall_time: 02:00:00
  retention_time: 1.12:00:00
  priority: 0
  user_identity:
    default_pool_admin: true
    specific_user:
      gid: 1001
      uid: 1001
  auto_pool:
    keep_alive: false
    pool_lifetime: job
  recurrence:
    schedule:
      do_not_run_after: null
      do_not_run_until: null
      recurrence_interval: 00:05:00
      start_window: null
    job_manager:
      allow_low_priority_node: true
      monitor_task_completion: false
      run_exclusive: false
  allow_run_on_missing_image: false
  remove_container_after_exit: true
  shm_size: 256m
  infiniband: false
  gpu: false
  data_volumes:
  - joblevelvol
  shared_data_volumes:
  - joblevelsharedvol
  input_data:
    azure_batch:
    - job_id: someotherjob
      task_id: task-a
      exclude:
      - '*.txt'
      include:
      - wd/*.dat
      destination: null
    azure_storage:
    - storage_account_settings: mystorageaccount
      container: jobcontainer
      include:
      - jobdata*.bin
      destination: $AZ_BATCH_NODE_SHARED_DIR/jobdata
      blobxfer_extra_options: null
  tasks:
  - task_factory:
      parametric_sweep:
        combinations:
          iterable:
          - ABC
          - '012'
          length: 2
          replacement: false
        permutations:
          iterable: ABCDEF
          length: 3
        product:
        - start: 0
          step: 1
          stop: 10
        zip:
        - ab
        - '01'
      random:
        distribution:
          beta:
            alpha: 1
            beta: 1
          exponential:
            lambda: 2
          gamma:
            alpha: 1
            beta: 1
          gauss:
            mu: 1
            sigma: 0.1
          lognormal:
            mu: 1
            sigma: 0.1
          pareto:
            alpha: 1
          triangular:
            high: 1
            low: 0
            mode:
          uniform:
            a: 0
            b: 1
          weibull:
            alpha: 1
            beta: 1
        generate: 3
        integer:
          start: 0
          step: 1
          stop: 10
        seed:
      file:
        azure_storage:
          container: somecontainer
          exclude: []
          include: []
          storage_account_settings: mystorageaccount
        task_filepath: file_name
      custom:
        input_args:
        - a
        - b
        - c
        input_kwargs:
          abc: '012'
          def: '345'
        module: mypkg.mymodule
        package: null
      repeat: 3
    id: null
    image: busybox
    name:
    labels: []
    environment_variables:
      def: '123'
    environment_variables_keyvault_secret_id: https://myvault.vault.azure.net/secrets/mytaskenv
    ports: []
    data_volumes:
    - contdatavol
    - hosttempvol
    shared_data_volumes:
    - azurefilevol
    resource_files:
    - blob_source: https://some.url
      file_mode: '0750'
      file_path: some/path/in/wd/file
    input_data:
      azure_batch:
      - job_id: previousjob
        task_id: mytask1
        exclude:
        - '*.txt'
        include:
        - wd/output/*.bin
        destination: null
      azure_storage:
      - storage_account_settings: mystorageaccount
        container: taskcontainer
        include:
        - taskdata*.bin
        destination: $AZ_BATCH_NODE_SHARED_DIR/taskdata
        blobxfer_extra_options: null
    output_data:
      azure_storage:
      - blobxfer_extra_options:
        container: output
        include:
        - '**/out*.dat'
        source: null
        storage_account_settings: mystorageaccount
    remove_container_after_exit: true
    shm_size: 256m
    additional_docker_run_options: []
    infiniband: false
    gpu: false
    depends_on:
    - taskid-a
    - taskid-b
    - taskid-c
    depends_on_range:
    - 1
    - 10
    max_task_retries: 1
    max_wall_time: 03:00:00
    retention_time: 1.12:00:00
    multi_instance:
      coordination_command:
      num_instances: pool_current_dedicated
      resource_files:
      - blob_source: https://some.url
        file_mode: '0750'
        file_path: some/path/in/sharedtask/file
    entrypoint: null
    command: mycommand
```

`job_specifications` array consists of jobs to create.
* (required) `id` is the job id to create. If the job already exists, the
specified `tasks` under the job will be added to the existing job.
* (optional) `auto_complete` enables auto-completion of the job for which
the specified tasks are run under. When run with multi-instance tasks, this
performs automatic cleanup of the Docker container which is run in detached
mode. The default is `false`. If creating a job `recurrence`, utilizing
`auto_complete` is one way to have recurrent job instances created from a
schedule to complete such that the next job recurrence can be created.
* (optional) `environment_variables` under the job are environment variables
which will be applied to all tasks operating under the job. Note that
environment variables are not expanded and are passed as-is. You will need
to source the environment file `$AZ_BATCH_TASK_WORKING_DIR/.shipyard.envlist`
in a shell within the docker `command` or `entrypoint` if you want any
environment variables to be expanded.
* (optional) `environment_variables_keyvault_secret_id` under the job are
environment variables stored in KeyVault that should be applied to all tasks
operating under the job. The secret stored in KeyVault must be a valid
YAML/JSON string, e.g., `{ "env_var_name": "env_var_value" }`.
* (optional) `max_task_retries` sets the maximum number of times that
Azure Batch should retry all tasks in this job for. By default, Azure Batch
does not retry tasks that fail (i.e. `max_task_retries` is 0).
* (optional) `max_wall_time` sets the maximum wallclock time that the job
can stay active for (i.e., time period after it has been created). By
default, or if not set, the job may stay active for an infinite period. The
format for this property is a timedelta with a string representation of
"d.HH:mm:ss". Note that the job will transition to completed state after the
the maximum wall clock time is reached along with termination of any
running tasks.
* (optional) `retention_time` sets the timedelta to retain any tasks
directories under the job on the compute node where it ran after the task
completes. The format for this property is a timedelta with a string
representation of "d.HH:mm:ss". For example, "1.12:00:00" would allow the
compute node to clean up all of the task directories under this job
36 hours after the task completed. The default, if unspecified, is
effectively infinite - i.e., task data is retained forever on the compute
node that ran the task.
* (optional) `priority` is an integral number that indicates the job priority.
Tasks within jobs with higher priority are run ahead of those with lower
priority, however, tasks that are already running with lower priority are
not preempted. Valid values are within the range of [-1000, 1000] and the
default is `0`.
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
* (optional) `auto_pool` will create a compute pool on demand for
the job as specified in the pool configuration. Note that storage resources
required by Batch Shipyard may not be automatically cleaned up when using
autopools. Utilizing `jobs term` or `jobs del` without any jobid scoping
will attempt to clean up storage resources. Otherwise, you will need to use
`storage del` or `storage clear` to clean up storage resources manually.
  * (optional) `pool_lifetime` specifies the lifetime of the pool. Valid
    values are `job` and `job_schedule`. `job_schedule` is only valid if
    the `recurrence` property is also specified. The default is `job`.
  * (optional) `keep_alive` specifies if the pool should be kept even after
    its lifetime expires. The default is `false`. Note that setting this
    value to `false` and setting `auto_complete` to `true` will automatically
    delete the compute pool once all tasks under the job complete.
* (optional) `recurrence` will create a schedule to run the job and tasks at
a set interval.
  * (required) `schedule` is the recurring schedule specification
    * (optional) `do_not_run_until` is a datetime specification that prevents
      the job from running until this date and time is reached. This string
      should be in a
      [parseable date time format](http://dateutil.readthedocs.io/en/stable/parser.html).
      The default is to run immediately (i.e., `null`).
    * (optional) `do_not_run_after` is a datetime specification that prevents
      the job from running after this date and time is reached. This string
      should be in a
      [parseable date time format](http://dateutil.readthedocs.io/en/stable/parser.html).
      The default has no limit (i.e., `null`).
    * (optional) `start_window` is the time window for when the job should
      be created according to this schedule to the maximum delta for which
      the job can be created. This is essentially the scheduling window for
      the job. If this property is non-`null` and the job cannot be created
      within this time window, then the job scheduling opportunity is
      forfeit until the next recurrence. The default is no limit
      (i.e., `null`). If the `start_window` exceeds the `recurrence_interval`
      then this is logically equivalent to setting the `start_window` to
      `null`. The format for this property is a timedelta with a string
      representation of "d.HH:mm:ss".
    * (required) `recurrence_interval` is the recurrence interval for the
      job. The format for this property is a timedelta with a string
      representation of "d.HH:mm:ss". The minimum value is `00:01:00` or
      1 minute. Note that a recurring job schedule can only have at most
      one active job. If a prior recurrence of the job is still active when
      the next recurrence fires, no new job is created. An important
      implication is that even if you set this property to a minimum value
      of 1 minute, there may be delays in completing the job and triggering
      the next which may artificially increase the time between recurrences.
      It is important to set either the `auto_complete` or the
      `job_manager`:`monitor_task_completion` setting to `true` if your
      tasks have no logic to terminate or delete the parent job.
  * (optional) `job_manager` property controls the job manager execution. The
    job manager is the task that is automatically created and run on a compute
    node that submits the `tasks` at the given `recurrence_interval`.
    * (optional) `allow_low_priority_node` allows the job manager to run
      on a low priority node. The default is `true`. Sometimes it is necessary
      to guarantee that the job manager is not preempted, if so, set this
      value to `false` and ensure that your pool has dedicated nodes
      provisioned.
    * (optional) `run_exclusive` forces the job manager to run on a compute
      node where there are no other tasks running. The default is `false`.
      This is only relevant when the pool's `max_tasks_per_node` setting is
      greater than 1.
    * (optional) `monitor_task_completion` allows the job manager to monitor
      the tasks in the job for completion instead of relying on
      `auto_complete`. The advantage for doing so is that the job can move
      much more quickly into completed state thus allowing the next job
      recurrence to be created for very small values of `recurrence_interval`.
      In order to properly utilize this feature, you must either set
      your pool's `max_tasks_per_node` to greater than 1 or have more than
      one compute node in your pool. If neither of these conditions are met,
      then the tasks that the job manager creates will be blocked as there
      will be no free scheduling slots to accommodate them (since the job
      manager task occupies a scheduling slot itself). The default is
      `false`. Setting both this value and `auto_complete` to `true` will
      result in `auto_complete` as `true` behavior.
* (optional) `allow_run_on_missing_image` allows tasks with a Docker image
reference that was not pre-loaded on to the compute node via
`global_resources`:`docker_images` in the global configuration to be able to
run. Note that you should attempt to specify all Docker images that you intend
to run in the `global_resources`:`docker_images` property in the global
configuration to minimize scheduling to task execution latency.
* (optional) `remove_container_after_exit` property specifies if all
containers under the job should be automatically removed/cleaned up after
the task exits. Note that this only cleans up the Docker container and not
the associated Batch task. This defaults to `true`.
* (optional) `shm_size` property specifies the size of `/dev/shm` in all
containers under the job. The default is `64m`. The postfix unit can be
designated as `b` (bytes), `k` (kilobytes), `m` (megabytes), or `g`
(gigabytes). This value may need to be increased from the default of `64m`
for certain Docker applications, including multi-instance tasks using Intel
MPI (see [issue #8](https://github.com/Azure/batch-shipyard/issues/8)).
* (optional) `infiniband` designates if all tasks under the job require
access to the Infiniband/RDMA devices on the host. Note that this will
automatically force containers to use the host network stack. If this
property is set to `true`, ensure that the `pool_specification` property
`inter_node_communication_enabled` is set to `true`. If this property is
not set, it will default to `true` if the task is destined for an RDMA-enabled
compute pool and `inter_node_communication_enabled` is set to `true`. This
option has no effect on `native` container support pools as it is
automtically enabled by the system.
* (optional) `gpu` designates if all containers under the job require access
to the GPU devices on the host. If this property is set to `true`, Docker
containers are instantiated via `nvidia-docker`. This requires N-series VM
instances. If this property is not set, it will default to `true` if the task
is destined for a compute pool with GPUs. This option has no effect on
`native` container support pools as it is automatically enabled by the
system.
* (optional) `data_volumes` is an array of `data_volume` aliases as defined
in the global configuration file. These volumes will be mounted in
all containers under the job.
* (optional) `shared_data_volumes` is an array of `shared_data_volume`
aliases as defined in the global configuration file. These volumes will be
mounted in all containers under the job.
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
      as defined in the credentials config.
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
  * (optional) `task_factory` is a way to dyanmically generate tasks. This
    enables parameter sweeps and task repetition without having to
    explicitly generate a task array with different parameters for the
    `command`. Please see the
    [Task Factory Guide](35-batch-shipyard-task-factory.md) for more
    information.
    * (optional) `parametric_sweep` is a parameter sweep task factory. This
      has multiple modes of task generation and only one may be specified.
      * (optional) `product` is a potentially nested parameter generator.
        If one set of `start` (inclusive), `stop` (exclusive), `step`
        properties are specified (all required parameters), then a simple
        range of values are generated. In the example above, the integers 0
        to 9 are provided as arguments to the `command` property. If another
        set of `start`, `stop`, `step` properties are specified, then these
        are nested within the prior set.
      * (optional) `combinations` generates `length` subsequences of
        parameters from the `iterable`. Combinations are emitted in
        lexicographic sort order.
        * (required) `iterable` is the iterable to generate parameters from
        * (required) `length` is the subsequence "r" length
        * (optional) `replacement` allows individual elements to be
          repeated more than once.
      * (optional) `permutations` generates `length` permutations of
        parameters from the `iterable`. Permutations are emitted in
        lexicographic sort order.
        * (required) `iterable` is the iterable to generate parameters from
        * (required) `length` is the subsequence "r" length
      * (optional) `zip` generates parameters where the i-th parameter
        contains the i-th element from each iterable.
    * (optional) `random` is a random task factory. This has multiple
      modes of task generation and only one may be specified.
      * (required) `generate` will generate N number of random values and
        thus N number of tasks
      * (optional) `seed` will initialize the internal state to the specified
        seed
      * (optional) `integer` will generate random integers
        * (required) `start` is the inclusive beginning of the random range
        * (required) `stop` is the exclusive end of the random range
        * (required) `step` is the stepping between potential random numbers
          within the range
      * (optional) `distribution` will generate random floating point values
        given a distribution. The
        [distribution](https://docs.python.org/3.6/library/random.html#real-valued-distributions)
        can be one of (please refer to the docs for required properties):
        * (optional) `uniform` for uniform distribution
        * (optional) `triangular` for triangular distribution
        * (optional) `beta` for beta distribution
        * (optional) `exponential` for exponential distribution
        * (optional) `gamma` for gamma distribution
        * (optional) `gauss` for Gaussian distribution
        * (optional) `lognormal` for Log normal distribution
        * (optional) `pareto` for Pareto distribution
        * (optional) `weibull` for Weibull distribution
    * (optional) `file` is a file-based task factory. This will generate a
      task for each file enumerated. The `command` should be keyword
      formatted with any combination of: `file_path`,
      `file_path_with_container`, `file_name`, or `file_name_no_extension`.
      Please see the
      [Task Factory Guide](35-batch-shipyard-task-factory.md) for more
      information.
      * (required) `azure_storage` specifies the azure storage settings to
        use for the file task factory.
        * (required) `storage_account_settings` is the storage account link to
          enumerate files from
        * (required) `container` or `file_share` specifies either a container
          or a file share to enumerate files from. These are mutually
          exclusive.
        * (optional) `include` are include filters
        * (optional) `exclude` are exclude filters
      * (required) `task_filepath` specifies how to place the file relative
        to the task working directory (i.e., `$AZ_BATCH_TASK_WORKING_DIR`).
        This can be one of: `file_path`, `file_path_with_container`,
        `file_name`, or `file_name_no_extension`.
    * (optional) `custom` is a custom task factory where the logic for
      parameter generation exists in a custom Python module that can be
      imported at runtime. Please see the
      [Task Factory Guide](35-batch-shipyard-task-factory.md) for more
      information.
      * (required) `module` specifies the Python module to import. This must
        be valid and resolvable by `importlib`. This module must define a
        `generate` generator function that is callable with `*args` and
        `**kwargs`. The `generate` generator function must yield an iterable
        to pass to the `command` for transformation.
      * (optional) `package` is required if `module` is specified in
        relative terms (i.e., the anchor for package resolution).
      * (optional) `input_args` are positional arguments to pass to the
        `generate` generator function.
      * (optional) `input_kwargs` are keyword arguments to pass to the
        `generate` generator function. This should be a dictionary where
        all keys are strings.
    * (optional) `repeat` will create N number of identical tasks.
  * (optional) `id` is the task id. Note that if the task `id` is null or
    empty then a generic task id will be assigned. The generic task id is
    formatted as dictated by the `autogenerated_task_id` setting in the
    global configuration; if this setting is not set, then by default the
    task id will be formatted as `task-NNNNN` where `NNNNN` starts from
    `00000` and is increased by 1 for each task added to the same job. If
    there are more than `99999` autonamed tasks in a job then the numbering
    is not padded for tasks exceeding 5 digits. This behavior can be
    controlled by the `autogenerated_task_id` setting in the global
    configuration. `id` should not be specified in conjunction with the
    `task_factory` property as `id`s will be automatically generated. A
    task `id` may not exceed 64 characters in length.
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
    be a valid YAML/JSON string, e.g., `{ "env_var_name": "env_var_value" }`.
  * (optional) `ports` is an array of port specifications that should be
    exposed to the host.
  * (optional) `data_volumes` is an array of `data_volume` aliases as defined
    in the global configuration file. These volumes will be mounted in the
    container. Volumes specified here will be merged with any job-level
    volumes specified.
  * (optional) `shared_data_volumes` is an array of `shared_data_volume`
    aliases as defined in the global configuration file. These volumes will be
    mounted in the container. Volumes specified here will be merged with any
    job-level volumes specified.
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
        as defined in the credentials config.
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
        as defined in the credentials config.
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
    defaults to `false`. This overrides the job-level property, if set.
  * (optional) `shm_size` property specifies the size of `/dev/shm` in
    the container. The default is `64m`. The postfix unit can be designated
    as `b` (bytes), `k` (kilobytes), `m` (megabytes), or `g` (gigabytes). This
    value may need to be increased from the default of `64m` for certain
    Docker applications, including multi-instance tasks using Intel MPI
    (see [issue #8](https://github.com/Azure/batch-shipyard/issues/8)). This
    overrides the job-level property, if set.
  * (optional) `additional_docker_run_options` is an array of addition Docker
    run options that should be passed to the Docker daemon when starting this
    container.
  * (optional) `infiniband` designates if this container requires access to the
    Infiniband/RDMA devices on the host. Note that this will automatically
    force the container to use the host network stack. If this property is
    set to `true`, ensure that the `pool_specification` property
    `inter_node_communication_enabled` is set to `true`. This overrides the
    job-level property, if set. It follows the same default behavior as the
    job-level property if not set.
  * (optional) `gpu` designates if this container requires access to the GPU
    devices on the host. If this property is set to `true`, Docker containers
    are instantiated via `nvidia-docker`. This requires N-series VM instances.
    This overrides the job-level property, if set. It follows the same default
    behavior as the job-level property if not set.
  * (optional) `max_task_retries` sets the maximum number of times that
    Azure Batch should retry this task for. This overrides the job-level task
    retry count. By default, Azure Batch does not retry tasks that fail
    (i.e. `max_task_retries` is 0).
    * (optional) `max_wall_time` sets the maximum wallclock time for this task.
    Please note that if this is greater than the job-level constraint, then
    the job-level contraint takes precendence. By default, or if not set, this
    is infinite, however, please note that tasks can only run for a maximum
    of 7-days due to an Azure Batch limitation. The format for this property
    is a timedelta with a string representation of "d.HH:mm:ss".
  * (optional) `retention_time` sets the timedelta to retain the task
    directory on the compute node where it ran after the task completes.
    The format for this property is a timedelta with a string representation
    of "d.HH:mm:ss". For example, "1.12:00:00" would allow the compute node
    to clean up this task's directory 36 hours after the task completed. The
    default, if unspecified, is effectively infinite - i.e., task data is
    retained forever on the compute node that ran the task. This overrides the
    job-level property.
  * (optional) `multi_instance` is a property indicating that this task is a
    multi-instance task. This is required if the Docker image is an MPI
    program. Additional information about multi-instance tasks and Batch
    Shipyard can be found
    [here](80-batch-shipyard-multi-instance-tasks.md). Do not define this
    property for tasks that are not multi-instance. Additional members of this
    property are:
    * `num_instances` is a property setting the number of compute node
      instances are required for this multi-instance task. Note that it is
      generally recommended not to use low priority nodes for multi-instance
      tasks as compute nodes may be pre-empted at any time. This property
      can be any one of the following:
      1. An integral number. Note that if there are insufficient nodes to
         matching this number, the task will be blocked.
      2. `pool_current_dedicated` which is the instantaneous reading of the
         target pool's current dedicated count during this function invocation.
      3. `pool_current_low_priority` which is the instantaneous reading of the
         target pool's current low priority count during this function
         invocation.
      4. `pool_specification_vm_count_dedicated` which is the
         `vm_count`:`dedicated` specified in the pool configuration.
      5. `pool_specification_vm_count_low_priority` which is the
         `vm_count`:`low_priority` specified in the pool configuration.
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
    This property may be null. Note that if you are using a `task_factory`
    for the specification, then task factory arguments are applied to the
    `command`. Therefore, Python-style string formatting options (excluding
    keyword formatting) are required for certain task factories that generate
    parameters to modify the `command`: `{}` positional, `{0}` numbering
    style, or `{keyword}` keyword style formatters are required depending
    upon the `task_factory` used. Please see the
    [Task Factory Guide](35-batch-shipyard-task-factory.md) for more
    information.

## Full template
A full template of a credentials file can be found
[here](../config\_templates/jobs.yaml). Note that this template cannot
be used as-is and must be modified to fit your scenario.
