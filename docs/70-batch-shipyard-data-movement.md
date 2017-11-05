# Data Movement and Batch Shipyard
The focus of this article is to explain how to move data between on-premises,
Azure storage and Batch compute nodes in the context of Batch Shipyard. Please
refer to the [installation doc](01-batch-shipyard-installation.md) for
information regarding required software in order to take advantage of the
data movement features of Batch Shipyard.

## Overview
Most HPC applications and simulations require some form of input data. For
example, a simulation may require various input parameters and definitions of
physical systems in order to produce meaningful output. Such input data may
not be scriptable and could be binary data files. In another scenario,
Deep learning frameworks may need millions of images and labels to perform
training. Typical on premises cluster systems have a shared file system for
which nodes of a cluster have access to for retrieving programs and data.

In the cloud, the *data movement* problem is a universal issue, especially
for many workloads that are amenable to batch-style processing. How do I get
my data which exists somewhere, perhaps on premises, into the cloud such that
my virtual machines have access to them? This problem is even more acute for
services which deliver resources on-demand such as Azure Batch. How do I get
my data to nodes which may be ephemeral? And on the flip-side, how do I get
my data from nodes after completion of a task?

Before diving into ingress and egress support specifics, let's examine a
high level overview of the data movement support provided by Batch Shipyard.

```
                      (I)           +-------------------------------------------------------------------------+
        +-------------------------> |                                                                         |
        |                           |                      Azure Storage (Blob and File)                      |
        |        +------------------+                                                                         |
        |        |                  +------------+-------------------------------------------+----------------+
        |        |                               |                                           |
        |        | (E)                           | (I)         ^                             | (I)    ^
        |        |                               v             | (E)                         v        | (E)
        |        |                                             |                                      |
        |        v                  +--------------------------+-------------+         +--------------+-------+
        |                           |                                        |         |                      |
    +---+-------------+      (E)    |          Azure Batch Pool "A"          |         | Azure Batch Pool "B" |
    |                 | <-----------+                                        |         |                      |
    |                 |             | +----------------+  +----------------+ |         |  +----------------+  |
    |  Local Machine  |             | |                |  |                | |    (I)  |  |                |  |
    |                 |    (I)      | | Compute Node 0 |  | Compute Node 1 | | <-------+  | Compute Node 0 |  |
    |                 +-----------> | |  [GlusterFS]   |  |  [GlusterFS]   | |         |  |                |  |
    +---+-------------+             | |                |  |                | |         |  +----------------+  |
        |                           | +----------------+  +----------------+ |         |                      |
        |         ^                 |                                        |         |  +----------------+  |
        v         |                 | +----------------+  +----------------+ |  (I)    |  |                |  |
                  |                 | |                |  |                | +-------> |  | Compute Node 1 |  |
+-----------------+-------+         | | Compute Node 2 |  | Compute Node 3 | |         |  |                |  |
|                         |         | |  [GlusterFS]   |  |  [GlusterFS]   | |         |  +----------------+  |
|  Shared File System(s)  |         | |                |  |                | |         |                      |
|                         |         | +----------------+  +----------------+ |         +----------------------+
+-------------------------+         |                                        |
                                    +----------------------------------------+
```

Arrows marked `(I)` are ingress actions with respect to the destination, and
arrows marked `(E)` are egress actions with respect to the source.

On the left-hand side of the diagram above containing the `Local Machine`
and `Shared File System(s)`, we will consider this as on premises for the
purposes of this document. "On premises" is where you would be invoking
`shipyard.py` actions. The machine that can invoke `shipyard.py` has
access to your local machine file system and can also access local shared
file systems.

From on premises, you can ingress your data to both Azure Storage and
Azure Batch Pools directly. You can also egress data from Azure Batch Pools
and Azure Storage (via [blobxfer](https://github.com/Azure/blobxfer) or
[AzCopy](https://azure.microsoft.com/en-us/documentation/articles/storage-use-azcopy/))
back to your local machine.

Within Azure, you can ingress data from Azure Storage to Azure Batch pools,
as well as egress data back out to Azure Storage when tasks complete.
You may also ingress data from other Azure Batch Tasks which may or may
not be in the same pool as input data for subsequent Azure Batch Tasks.

The rest of the document will explain each ingress and egress data movement
operation in detail.

## Data Ingress
Batch Shipyard provides multiple paths for ingressing data to ultimately
be used by your job and tasks. Data ingress can be invoked automatically
with certain configuration options or through the command `data ingress`
specified to `shipyard.py`.

### From On Premises
You'll need to decide if all or part of your data is long-lived, i.e., will
it be required for many jobs and tasks in the future, or if it is short-lived,
i.e., it will only be used for this one job and task. Even if your job is
long-lived, is the data small enough such that data ingress is not a large
burden for each job and task that references it?

If your answer to these questions is that the data is either short-lived or
is small enough such that data ingress is not a large burden, then you may
opt for Batch Shipyard's direct to GlusterFS or compute node data ingress
capability. With this feature, your files accessible on premises will be
directly ingressed to compute node(s), bypassing the hops to and from Azure
storage. You can define these files under the global configuration file
property `global_resources`:`files`. The `destination` member should include
a property named `shared_data_volume` which references your GlusterFS volume.
Alternatively, if your pool only contains one compute node, you should not
define a GlusterFS volume and instead only define a
`relative_destination_path` property which will ingress data directly to that
path on the compute node. Any files in the `source` path (matching the
optional `include` and `exclude`) filters will then be ingressed into the
compute nodes using the `data ingress` command or by specifying
`transfer_files_on_pool_creation` as `true` in the pool
configuration file. There are many configuration options under the
`data_transfer` member which may help optimize for your particular scenario.
The following transfer methods from on premises are available:

* `scp`: secure copy to a single node in the pool
* `multinode_scp`: secure copy to multiple nodes simultaneously in the pool
* `rsync+ssh`: rsync over ssh to a single node in the pool
* `multinode_rsync+ssh`: rsync over ssh to multiple nodes simultaneously in
the pool

In the case where your data is long-lived or is too large to be repeatedly
transferred for each job and task that requires it, you may be better off
ingressing this data to Azure Storage first. By doing so, you pay for the
"long hop" once and can then leverage the potentially lower-latency and
higher-bandwidth intra-datacenter transfer for subsequent jobs and tasks that
require this data. This is a two-step process with Batch Shipyard. Define the
files required under the `global_resources`:`files` property where the
`destination` member includes a property named `storage_account_settings`
where the value is a link to a storage account from your credentials config
file. Within the `data_transfer` property, you will need to specify either
`container` or `file_share` depending upon if you want to send your files to
Azure Blob or File Storage, respectively. Please note that there can be
significant difference in performance between the two, please visit
[this page](https://azure.microsoft.com/en-us/documentation/articles/storage-scalability-targets/)
for more information. The second step is outlined in the next section.

Note that `files` is an array, therefore, Batch Shipyard accepts any number
of `source`/`destination` pairings and even mixed GlusterFS and Azure Storage
ingress objects.

Data ingress from on-premises to Windows pools is not supported.

### From Azure Storage (Blob and File)
Data from Azure Storage can be ingressed to compute nodes in many different
ways with Batch Shipyard. The recommended method when using Batch Shipyard
is to take advantage of the `input_data` property for configuration objects
at the pool, job, and task-level.

For pool-level ingress, the `input_data` property is specified in the pool
property under `pool_specification`. To transfer from Azure Storage,
you would specify the `azure_storage` property under `input_data` and within
`azure_storage` multiple Azure storage sources can be specified. At the
pool-level, `remote_path` data is ingressed to all compute nodes
to the specified `local_path` location as part of pool creation if the
`transfer_files_on_pool_creation` property is `true`. To ingress from an
Azure File Share, specify `is_file_share` as `true`. Note that the pool must
be ready in order for the `data ingress` command to work. Additionally,
although you can combine on premises ingress to Azure Storage and then ingress
to compute node, if there is a possiblity of overlap, it is recommended to
separate these two processes by ingressing data from `files` with the
`data ingress` command first. After that action completes, create the pool
with `transfer_files_on_pool_creation` to `false` (so the data that was
ingressed with `data ingress` is not ingressed again) and specify `input_data`
with the appropriate properties from the data that was just ingressed with
the `data ingress` command.

`input_data` for each job in `job_specifications` will ingress data to any
compute node running the specified job once and only once. Any `input_data`
defined for the job will be downloaded for this job which can be run on any
number of compute nodes depending upon the number of constituent tasks and
repeat invocations. However, `input_data` is only downloaded once per job
invocation on a compute node. For example, if `job-1`:`task-1` is run on
compute node A and then `job-1`:`task-2` is run on compute node B, then
this `input_data` is ingressed to both compute node A and B. However, if
`job-1`:`task-3` is then run on compute node A after `job-1`:`task-1`, then
the `input_data` is not transferred again.

`input_data` for each task in the task array for each job will ingress data
to the compute node running the specified task. Note that for task-level
`input_data`, the `local_path` property is optional. If not specified,
data will be ingressed to the `$AZ_BATCH_TASK_WORKING_DIR` by default.
For multi-instance tasks, the download only applies to the compute node
running the application command. Data is not ingressed with the coordination
command which is run on all nodes.

There is one additional method of ingressing data from Azure Storage, which is
through Azure Batch resource files. In the jobs config file, you can specify
resource files through the `resource_files` property within each task.
However, this can be quite restrictive: (1) HTTP/HTTPS endpoints only,
(2) resource files must be manually defined one-at-a-time, (3) limit on the
number of resource files that can be defined for each task. It is recommended
to use `input_data` if you have many files that you need to download from a
container or file share.

### From Azure Batch Tasks
Data from previously run Azure Batch tasks, including those run by Batch
Shipyard, can be ingressed into compute nodes with the `input_data` property
for properties at the pool, job, and task-level. Note that the compute node
where the task was run must still be active and must not have been removed
or deleted.

To transfer from a previous Azure Batch Task that has completed, you would
specify the `azure_batch` property under `input_data`. As with Azure
Storage in the previous section, you can specify multiple properties within
the `azure_batch` array to reference multiple different tasks.

`job_id` is the job id of the task and `task_id` is the id of that task for
which to ingress files generated by the task. `include` and `exclude` filters
are optional but can be specified to reduce the scope of the transfer.
The `destination` property is needed if this is not a task-level `input_data`
property. If omitted at the task-level, the default will be
`$AZ_BATCH_TASK_WORKING_DIR`, similar to the default for Azure Storage
ingress with `input_data` above.

The behavior at pool-level, job-level and task-level are nearly identical
with Azure Storage ingress with `input_data` above except that instead of
transferring from Azure Storage, data is transferred from another compute
node that has run the specified task.

Note that `azure_batch` and `azure_storage` may be specified within the same
`input_data` properties if required.

## Data Egress
Batch Shipyard provides the ability to egress from compute nodes to various
locations.

### To On Premises
`shipyard.py` provides actions to help egress data off a compute node back to
on premises. These actions are:

1. `data files task`: get a single file or all files from a compute node
using a job id, task id and a file name.
2. `data files node`: get a single file or all files from a compute node
using a node id and file path.
3. `data files stream`: stream a text file (decoded as UTF-8) back to the
local console or stream a file back to local disk. This is particularly
useful for progress monitoring via a file or tailing an output.

### To Azure Storage
If you need to egress data from a compute node and persist it to Azure
Storage, Batch Shipyard provides the `output_data` property on tasks of a
job in `job_specifications`. `local_path` defines which directory within the
task directory to egress data from; if nothing is specified for `local_path`
then the default is `$AZ_BATCH_TASK_DIR` (which contains files like
`stdout.txt` and `stderr.txt`). Note that you can specify a source
originating from the shared directory here as well, e.g.,
`$AZ_BATCH_NODE_SHARED_DIR`, there is no restriction that limits you to
just the task directory. `include` defines an optional include filter to
be applied across the `source` files. Finally, define the `remote_path`
property to egress to the path specified, and optionally `is_file_share`
set to `true` if you wish to egress to Azure File Storage instead of
Azure Blob.

## Configuration and Usage Documentation
Please see [this page](10-batch-shipyard-configuration.md) for a full
explanation of each data movement configuration option. Please see
[this page](20-batch-shipyard-usage.md) for documentation on `data`
command usage.
