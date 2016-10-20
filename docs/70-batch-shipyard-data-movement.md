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
my data from nodes after completion of a task? A data movement solution is
half-baked if it solves only one part of the problem. Let's begin with the
input data problem.

## Data Ingress
Batch Shipyard provides multiple paths for ingressing data to ultimately
be used by your job and tasks. Let us define "on premises" as where you
are invoking `shipyard.py`. The machine that can invoke `shipyard.py` has
access to your local machine file system and can also access local shared
file systems.

### From On Premises
You'll need to decide if all or part of your data is long-lived, i.e., will
it be required for many jobs and tasks in the future, or if it is short-lived,
i.e., it will only be used for this one job and task. Even if your job is
long-lived, is the data small enough such that data ingress is not a large
burden for each job and task that references it?

If your answer to these questions is that the data is either short-lived or
is small enough such that data ingress is not a large burden, then you may
opt for Batch Shipyard's direct to GlusterFS data ingress feature. With this
feature, your files accessible on premises will be directly ingressed to
the compute nodes, bypassing the hops to and from Azure storage. You can
define these files under the global configuration json file property
`global_resources`:`files`. The `destination` member should include a property
named `shared_data_volume` which references your GlusterFS volume. Any files
in the `source` path (matching the optional `include` and `exclude`) filters
will then be ingressed into the compute nodes using the `ingressdata` action
or by specifying `transfer_files_on_pool_creation` as `true` in the pool
configuration json. There are many configuration options under the
`data_transfer` member which may help optimize for your particular scenario.

In the case where your data is long-lived or is too large to be repeatedly
transferred for each job and task that requires it, you may be better off
ingressing this data to Azure Storage first. By doing so, you pay for the
"long hop" once and can then leverage the potentially lower-latency and
higher-bandwidth intra-datacenter transfer for subsequent jobs and tasks that
require this data. This is a two-step process with Batch Shipyard. Define the
files required under the `global_resources`:`files` property where the
`destination` member includes a property named `storage_account_settings`
where the value is a link to a storage account from your credentials json
file. Within the `data_transfer` property, you will need to specify either
`container` or `file_share` depending upon if you want to send your files to
Azure Blob or File Storage, respectively. Please note that there can be
significant difference in performance between the two, please visit
[this page](https://azure.microsoft.com/en-us/documentation/articles/storage-scalability-targets/)
for more information. The second step is outlined in the next section.

Note that `files` is an array, therefore, Batch Shipyard accepts any number
of source/destination pairings and even mixed GlusterFS and Azure Storage
ingress objects.

### From Azure Storage
Data from Azure Storage can be ingressed to compute nodes in many different
ways with Batch Shipyard. The recommended method when using Batch Shipyard
is to take advantage of the `input_data` property for json objects in
the pool, job, and task-level.

For pool-level ingress, the `input_data` property is specified in the pool
json object under `pool_specification`. `input_data` currently supports
`azure_storage` as a property and within `azure_storage`, multiple Azure
storage sources can be specified. At the pool-level, `container` or
`file_share` data is ingressed to all compute nodes to the specified
destination location as part of pool creation if the
`transfer_files_on_pool_creation` property is `true`. Note that the pool must
be ready in order for the `ingressdata` action to work. Additionally, although
you can combine on premises ingress to Azure Storage and then ingress to
compute node, if there is a possiblity of overlap, it is recommended to
separate these two processes by ingressing data from `files` with the
`ingressdata` action first. After that action completes, create the pool with
`transfer_files_on_pool_creation` to `false` (so the data that was ingressed
with `ingressdata` is not ingressed again) and specify `input_data` with
the appropriate properties from the data that was just ingressed with
`ingressdata`.

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
`input_data`, the `destination` property is optional. If not specified,
data will be ingressed to the `$AZ_BATCH_TASK_WORKING_DIR` by default.
For multi-instance tasks, the download only applies to the compute node
running the application command. Data is not ingressed with the coordination
command which is run on all nodes.

There is one additional method of ingressing data from Azure Storage, which is
through Azure Batch resource files. In the jobs json file, you can specify
resource files through the `resource_files` property within each task.
However, this can be quite restrictive: (1) HTTP/HTTPS endpoints only,
(2) resource files must be manually defined one-at-a-time, (3) limit on the
number of resource files that can be defined for each task. It is recommended
to use `input_data` if you have many files that you need to download from a
container or file share.

## Data Egress
Batch Shipyard provides the ability to egress from compute nodes to various
locations.

### To On Premises
`shipyard.py` provides actions to help egress data off a compute node back to
on premises. These actions are:

1. `gettaskfile`: get a single file from a compute node using a job id,
task id and a file name.
2. `getnodefile`: get a single file from a compute node using a node id and
file path.
3. `gettaskallfiles`: get all files generated by a task from a compute node
using a job id, task id and optional include filter.
4. `streamfile`: stream a file (decoded as UTF-8) back to the local console.
This is particularly useful for progress monitoring or tailing an output.

### To Azure Storage
If you need to egress data from a compute node and persist it to Azure
Storage, Batch Shipyard provides the `output_data` property on tasks of a
job in `job_specifications`. `source` defines which directory within the
task directory to egress data from; if nothing is specified for `source` then
the default is `$AZ_BATCH_TASK_DIR` (which contains files like `stdout.txt`
and `stderr.txt`). Note that you can specify a source originating from the
shared directory here as well, e.g., `$AZ_BATCH_NODE_SHARED_DIR`, there is
no restriction that limits you to just the task directory. `include` defines
an optional include filter to be applied across the `source` files. Finally,
define the `container` or `file_share` property to egress to Azure Blob
or File Storage, respectively.

## Configuration Documentation
Please see [this page](10-batch-shipyard-configuration.md) for a full
explanation of each data movement configuration option.
