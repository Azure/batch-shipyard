# Federations with Batch Shipyard
The focus of this article is to explain the federation concept in Batch
Shipyard and effectively deploying your workload across multiple pools that
may span multiple Azure regions across the world.

## Overview
In Azure Batch, each pool within a Batch account is considered a logical
boundary for related work. Thus jobs and job schedules can only target
a single Batch pool for execution. However, it may be desirable to have
workloads that span multiple pools as there may be a need for a heterogenous
mix of compute nodes types, or the ability to manage a distribution of pools,
logically, as a unified resource. Moreover, there should be no restriction
for such a logical grouping to be limited to a single Batch account, or
even a single region unless data residency, data hydration sensitivity
or other requirements prohibit such collections.

To enable multi-pool collections across any number of Batch accounts and
regions, Batch Shipyard defines the concept of a federation. Federations are
collections of pools that can be provisioned as entirely different
configurations but grouped together as a single resource. This enables
scenarios such as hybrid VM composition and load balancing workloads by
routing jobs to regions where specific capabilities may be available and
necessary. Federations also enable rich constraint matching while maintaining
important cloud-native features of core Azure Batch such as autoscaling
capabilities of the underlying pools.

## Major Features
* Full suite of federation, federated pool and federated job management
commands through the CLI
* Simple management of federations through user-defined IDs
* Multi-region support within a single federation
* Ability to dynamically add and remove pools from federations on-demand
* Support for multiple federations simultaneously using a single federation
proxy
* Fully automated federation proxy deployment and management including
on-demand suspend and restart
* Automatic persisted federation proxy logging to Azure File Storage for
diagnostics
* Support for job recurrences (job schedules)
* FIFO ordering of actions within a job or job schedule
* Leverages Azure MSI to eliminate credential passing and backing to a store
* Federation proxies can be run in HA mode

## Mental Model
The following picture describes how commands issued through Batch Shipyard
affect metadata stores and processing by the federation proxy to ultimately
issue Batch service API calls for job scheduling.

### Terminology
Below are some helpful terms that are referenced throughout this guide that
are not common to core Azure Batch. It is recommended to review this list
before examining the mental model picture.

* Federation: a collection of pools that are logically grouped together.
* Action: a directive for the federation proxy to process. Actions are
enqueued on a federation queue.
* Federation proxy: a server which processes actions.
* Federation queue: contains enqueued actions. Actions across multiple jobs
or job schedules are not guaranteed to be processed in FIFO order. Actions
within a single job or job schedule are guaranteed to be processed in FIFO
order.
* Task group: a set of tasks within a job associated with an action.
* Constraint: a condition placed on a job to be applied by the federation
proxy when selecting a target pool to schedule to.
* Scheduling slot: Each compute node can contain up to max tasks per node
scheduling slots as specified during pool allocation.
* Available scheduling slots: the number of compute nodes within a pool that
can run a task. The formula representing this metric is:
`(nodes in idle state + nodes in running state) * max_tasks_per_node`.

```
                                                                         +-------------+
                                                                         | Azure Files |
                                                                         +------+------+
                                                                                ^
                        +----------------------------+                          | logging
                        |   Federation Metadata in   |   master                 |
                        | Azure Storage Blob & Table |   election  +------------+--------------+
                        |                            | <-----------+     Federation Proxy      |
                        | +----------+  +----------+ |             | +------------+ +--------+ |
                        | | Job      |  | Pool     | |             | |Dynamic     | |Task    | |
+----------+            | | Metadata |  | Metadata | |             | |Resource    | |Re-write| |
|          |   push     | +----------+  +----------+ |   fetch     | |Conditioning| |Engine  | |
| Batch    +----------> |                            +-----------> | +------------+ +--------+ |
| Shipyard |            +----------------------------+             | +-----------+ +---------+ |
| "fed"    |                                                       | |Constraint | |Service  | |
| commands | enqueue action  +------------------+ dequeue action   | |Matching   | |Proxy &  | |
|          +---------------> |                  +----------------> | |Engine     | |MSI Auth | |
+----------+                 | Federation Queue |                  | +-----------+ +---------+ |
                             |                  |                  +---------------------------+
                             +------------------+                       |
                                                                        | schedule
                                                                        |
            +-----------------------------------------------------------v-------+
            |                         Batch Federation                          |
            | +-------------------+ +-------------------+ +-------------------+ |
            | | Region A          | | Region B          | | Region C          | |
            | | +------+ +------+ | | +------+ +------+ | | +------+ +------+ | |
            | | |Pool 0| |Pool 1| | | |Pool 3| |Pool 4| | | |Pool 7| |Pool 8| | |
            | | +------+ +------+ | | +------+ +------+ | | +------+ +------+ | |
            | | +------+          | | +------+ +------+ | |                   | |
            | | |Pool 2|          | | |Pool 5| |Pool 6| | |                   | |
            | | +------+          | | +------+ +------+ | |                   | |
            | +-------------------+ +-------------------+ +-------------------+ |
            +-------------------------------------------------------------------+
```

## Walkthrough
The following is a brief walkthrough of configuring a Batch Shipyard
federation and simple usage commands for creating a federation proxy and
submitting actions against federations.

### Configuration
The configuration for a Batch Shipyard federation is generally composed of
two major parts: the federation proxy and the normal global config, pool, and
jobs configuration.

#### Federation Proxy
The federation proxy configuration is defined by a federation configuration
file.

```yaml
federation:
  storage_account_settings: # storage account link name where all
                            # federation metadata is stored
  # ... other settings
  proxy_options:
    polling_interval:
      federations: # interval in seconds
      actions: # interval in seconds
    logging:
      persistence: # automatically persist logs in real-time to Azure File Storage
      level: # logging level, defaults to "debug"
      filename: # filename schema
    scheduling:
      after_success:
        blackout_interval: # scheduling blackout interval for target pool
                           # after success in seconds
        evaluate_autoscale: # immediately evaluate autoscale after scheduling
                            # success if target pool was autoscale enabled
```

Please refer to the full
[federation proxy configuration documentation](17-batch-shipyard-configuration-federation.md)
for more detailed explanations of each option, including other options not
shown here.

#### Global Configuration
Special care should be taken with the
[global configuration](12-batch-shipyard-configuration-global.md)
while provisioning pools that will take part of a federation. Any task that requires
a login for a container registry or a shared data volume must have
such configuration applied to all pools within the federation.

If it is known beforehand that a set of container images will be required
for all task groups submitted to the federation, then they should be
specified for all pools that will be part of the federation under
`global_resources`:`docker_images`. Any images that require logins, should
be defined in the credentials configuration.

If task container images will not be known beforehand, then it is imperative
that the `global_resources`:`additional_registries` contains a list of all
private registry servers required by container images that are referenced by
any task within a task group. The corresponding login information for these
registries should be present in the credentials configuration, including
a private Docker Hub login, if necessary.

Any tasks within task groups referencing `shared_data_volumes` should have
pools allocated with the proper `shared_data_volumes` before joining the
federation. Special care must be taken here to ensure that any pools that
are in different Batch accounts or regions conform to the same naming
scheme for these volumes used by tasks in task groups.

#### Federated Job Constraints
Note that none of the `federation_constraints` properties are required. They
are provided to allow for specified user requirements and optimizations on
job/task group placement within the federation.

```yaml
job_specifications:
- id: # job id
  # ... other settings
  federation_constraints:
    pool:
      autoscale:
        allow: # allow job to be scheduled on an autoscale pool
        exclusive: # exclusively schedule job on an autoscale pool
      low_priority_nodes:
        allow: # allow job to be best-effort scheduled on a pool with low priority nodes
        exclusive: # best-effort schedule job on a pool with exclusively low priority nodes
      native: # job must be scheduled on a native container pool
      windows: # job requires a windows pool
      location: # job should be routed to a particular Azure region, must be a proper ARM name
      container_registries:
        private_docker_hub: # any task in task group with Docker Hub references
                            # refer to a private Docker repository
        public:
        - # list of public registries that don't require a login for referenced
          # container images for all tasks in task group
      max_active_task_backlog: # limit scheduling a job with queued backlog of tasks
        ratio: # maximum backlog ratio allowed represented as (active tasks / schedulable slots).
        autoscale_exempt: # if autoscale pools are exempt from this ratio requirement if there
                          # are no schedulable slots and their allocation state is steady
      custom_image_arm_id: # job must schedule on a pool with the specified custom image ARM image id
      virtual_network_arm_id: # job must schedule on a pool with the specified virtual network ARM subnet id
    compute_node:
      vm_size: # job must match the named Azure Batch supported Azure VM SKU size exactly
      cores:
        amount: # job requires at least this many cores
        schedulable_variance: # maximum "over-provisioned" core capacity allowed
      memory:
        amount: # job requires at least this much memory (allowable suffixes: b, k, m, g, t)
        schedulable_variance: # maximum "over-provisioned" memory capacity allowed
      exclusive: # tasks in the task group must run exclusively on the compute node
                 # and cannot potentially be co-scheduled with other running tasks
      gpu: # job must be scheduled on a compute node with a GPU,
           # job/task-level requirements override this option
      infiniband: # job must be scheduled on a compute node with RDMA/IB,
                  # job/task-level requirements override this option
  tasks:
    # ... other settings
```

It is strongly recommended to review the
[jobs documentation](14-batch-shipyard-configuration-jobs.md) which contains
more extensive explanations for each `federation_constraints` property and
for other general job and task options not shown here.

Important notes on job configuration behavioral modifications due to
`federation_constraints`:

* Specifying task dependencies under `depends_on` will result in task ids
being modified with a postfix containing a subset of the unique id
for federations that do not require unique job ids.
* Container registry credential information should be provided at provisioning
time to all pools that may potentially execute that container on-behalf of
the federation. Please see the `container_registries` constraint for more
information.
* Be mindful of any `shared_data_volumes` or job-level `input_data` that are
specified in the job or corresponding tasks, and if the job should be subject
to constraints such as `location` or `virtual_network_arm_id`.

#### Federated Pool Configuration
Pools that comprise the federation will have certain
[configuration options](13-batch-shipyard-configuration-pool.md)
applied to them that will naturally limit which task groups can target them
for scheduling within the federation. The following is a non-exhaustive,
but perhaps the most important, list of pool options that can affect task
group scheduling.

* `native` under `vm_configuration`:`platform_image` will have a large impact
on task group placement routing as task groups can only be scheduled on pools
provisioned as their respective configuration of native or non-native. In
general, it is recommended to use `native` container pools; however, native
container pools may not be appropriate for all situations. Please see
[this FAQ item](97-faq.md#what-is-native-under-pool-platform_image-and-custom_image)
for more information on native vs non-native container pools. For maximum
federated scheduling efficacy, it is recommended to pick native or
non-native and use the same setting consistently across all pools and all job
`federation_constraints` within the federation.
* `arm_image_id` under `vm_configuration`:`custom_image` will allow
routing of task groups with `custom_image_arm_id` constraints.
* `vm_size` will be impacted by `compute_node` job constraints.
* `max_tasks_per_node` will impact available scheduling slots and the
`compute_node`:`exclusive` constraint.
* `autoscale` changes behavior of scheduling across various constraints.
* `inter_node_communication` enabled pools will allow tasks that contain
multi-instance tasks.
* `virtual_network` proeprties will allow routing of task groups with
`virtual_network_arm_id` constraints.

### Limitations
This is a non-exhaustive list of potential limitations while using
the federation feature in Batch Shipyard.

* All Batch accounts within a federation must reside under the same
subscription.
* All task dependencies must be self-contained within the task group.
* `depends_on_range` based task dependencies are not allowed, currently.
* `input_data`:`azure_batch` has restrictions. At the job-level it is not
allowed and at the task-level it must be self-contained within the task group.
No validation is performed at the task-level to ensure self-containment
of input data from other Batch tasks within the task group. Pool-level
`input_data`:`azure_batch` is not validated.
* A maximum of 14625 actions can be actively queued per unique job id.
Actions already processed by the federation proxy do not count towards this
limit. This limit only applies to federations that allow non-unique job ids
for job submissions (i.e., `fed jobs add`).
* Low priority/dedicated compute node constraints are best-effort. If a task
group is scheduled to a pool with dedicated-only nodes due to a specified
constraint, but the pool later resizes with low priority nodes, portions of
the task group may get scheduled to these nodes.
* Constraints restricting low priority or dedicated execution may be
subject to the autoscale formula supplied. It is assumed that an autoscale
formula will scale up/down both low priority and dedicated nodes.
* Each pool in a federation should only be associated with one and only one
federation. Adding a pool to multiple federations simultaneously will result
in undefined behavior.
* Singularity containers are not fully supported in federations.

### Quotas
Ensure that you have sufficient active job/job schedule quota for each
Batch account. You may also consider increasing your pool quota if you
intend on having many pools within a Batch account that comprise a
federation.

Please note that *all* quotas (except for the number of Batch accounts
per region per subscription) apply to each individual Batch account
separately. User subscription based Batch accounts share the underlying
subscription regional core quotas.

### Usage
The following will describe many of the federation commands available in
the CLI for managing the federation proxy, federations and action submission.
Federation-related commands are grouped under the `fed` sub-command.

Note that most federation commands have the `--raw` option available which
allows callers to consume the result of a command invocation in JSON
format.

Please refer to the [usage documentation](20-batch-shipyard-usage.md) for
a full listing of federation commands and further explanation of each
command and options not documented here.

#### Federation Setup
The following list shows a typical set of steps to setup a federation. Please
ensure that you've reviewed the prior sections and any relevant configuration
documentation before proceeding.

1. Construct the `federation.yaml` configuration file and optionally add
a different `storage` credential section link to store federation metadata
in a separate region or storage account than that of normal Batch Shipyard
metadata.
2. Deploy pools that will comprise the federation. These can be
autoscale-enabled pools.
3. Deploy the federation proxy: `fed proxy create`
4. Verify proxy: `fed proxy status`
5. Create a federation:
    * With unique job id requirement: `fed create <fed-id>`
    * Without unique job id requirement: `fed create <fed-id> --no-unique-job-ids`
6. Add pools to the federation:
    * With a pool configuration file: `fed pool add <fed-id>`
    * Without a pool configuration file: `fed pool add <fed-id> --pool-id <pool-id> --batch-service-url <batch-service-url>`
7. Verify federation: `fed list`

A federation with a unique job id requirement means that all jobs
submitted to the federation must have unique job ids. Job submissions which
collide with a pre-existing job with the same job id in the federation will
be actively rejected. This mode is recommended when federations are shared
resources amongst a team. A federation without a unique job id requirement
allows jobs to be submitted even if a job with the same id exists in the
federation. The federation proxy will attempt to dynamically condition the
action such that it can actively co-locate task groups among similarly named
jobs. Because this requires specific unique id tracking to disambiguate task
groups within the same job on potentially the same target pool, tracking
task group submissions can become confusing with a team sharing a federation.
This non-unique job id mode is only recommended for a federation with a
single user.

Conversly, teardown of a federation would generally follow these steps:

1. Ensure all federation jobs have been deleted.
2. Destroy the federation proxy: `fed proxy destroy`
3. Destroy the federation: `fed destroy <fed-id>`

If you do not need to destroy the federation, but would like to minimze
the cost of a federation proxy when no jobs will be submitted (e.g., off
work), you can instead suspend the proxy and re-start it at a later time
through the `fed proxy suspend` and `fed proxy start` commands. In that
case you would not destroy the federation metadata with the
`fed destroy <fed-id>` command.

#### Job Lifecycle
Federation jobs have the following commands available:

* Add jobs: `fed jobs add <fed-id>`
* List jobs: `fed jobs list <fed-id>`
* Terminate jobs: `fed jobs term <fed-id> --job-id <job-id>`
* Delete jobs: `fed jobs del <fed-id> --job-id <job-id>`

When adding jobs, the specified jobs configuration and pool configuration
(e.g., pool.yaml) are consumed. If specific `federation_constraints`
overrides are not specified, then the federation job is created with
settings as read from the pool configuration file. It is important
to define job `federation_constraints` to override settings read from
the pool configuration, if necessary.

To inspect federation jobs and associated task groups, you can typically
follow this pattern:

1. Locate the job: `fed jobs list <fed-id> --job-id <job-id>`
2. Use location info to interact with job/task groups:
    * Use Batch Explorer or Azure Portal to graphically manage.
    * Directly use Batch Shipyard commands if you have the correct Batch
      account credentials populated targeting the region with the pool
      listed in the job location.

Sometimes a job/task group is submitted which can "block" other actions for
the same specified job if an improper constraint or other incorrect
configuration is specified (this can be particularly acute for non-unique job
id federations). In this case, it is necessary to remove such problematic
actions to unblock processing. This can be done with the command:
`fed jobs zap <fed-id> --unique-id <uid>`. Note that there is no recovery
after a unique id is removed; the action will need to be re-submitted
(with the corrected parameters to prevent the blocking behavior which
required the use of `fed jobs zap` in the first place).
