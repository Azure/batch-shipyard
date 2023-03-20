# Troubleshooting Guide
This guide is to help in the event you encounter issues while using Batch
Shipyard. You can also visit the [FAQ](97-faq.md) for other questions
that do not fall in to the categories below.

## Table of Contents
1. [Installation Issues](#install)
2. [Azure Batch Service Issues](#batchservice)
3. [Compute Node Issues](#computenode)
4. [Job/Task Execution Issues](#task)
5. [Container Issues](#container)

## <a name="install"></a>Installation Issues
#### Anaconda Python Environments
[Anaconda](https://continuum.io) Python environments are structured
differently than standard [CPython](https://python.org) environments.
Anaconda has isolated environments which are conceptually equivalent to
[Virtual Environments](https://pypi.python.org/pypi/virtualenv) and also
have separate packaging mechanisms than packages traditionally found on
PyPI. As such, special attention should be given when installing Batch
Shipyard into an Anaconda environment. It is highly recommended to use
an Anaconda environment that provides Python 3.5 or higher if using Anaconda.
In general, it is recommended to use [CPython](https://python.org) especially
when installing into virtual environments (the recommended installation
method) as the command lag can be much shorter.

However, if you do plan to use Anaconda, then it is recommended to use the
`install.sh` script to install on an Anaconda environment on Linux and
the `install.cmd` command file to install on an Anaconda environment on
Windows.

## <a name="batchservice"></a>Azure Batch Service Issues
#### Check Azure Batch Service Status
If you suspect possible Azure Batch service issues, you can check the status
of Azure services [at this website](https://azure.microsoft.com/status/).

## <a name="computenode"></a>Compute Pool and Node Issues
#### Resize Error is encounted with pool
Resize errors with a pool can happen any time a pool is growing or shrinking.
Remember that when you issue `pool add`, a pool starts with zero compute nodes
and then grows to the target number of nodes specified. You can query the
pools in your account with the `pool list` command and any resize errors
will be displayed. You can also query this information using Azure Portal
or Batch Labs. If it appears that the resize error was transient,
you can try to issue `pool resize` to begin the pool grow or shrink process
again, or alternatively you can opt to recreate the pool.

There are typically three common reasons for Resize Errors:

1. Insufficient core quota: Non-UserSubscription Batch accounts by default
have 20 cores associated with them. These core quota are managed independently
of any core quota on the associated subscription. UserSubscription Batch
Accounts have core quota that is associated with the subscription. Please
follow [this guide](https://docs.microsoft.com/azure/batch/batch-quota-limit)
for submitting a support request to increase your core quota.
2. Operation(s) took longer than expected: Resizing the pool to a different
target VM count may take longer than the specified timeout. In these cases,
re-issue the resize command.
3. Not enough IPs in the virtual network subnet: When creating a pool with
a UserSubscription Batch account with a virtual network, you must ensure
that there are sufficient number of available IPs in your subnet. Batch
Shipyard will attempt to validate this on your behalf if you specify the
subnet's address range in the configuration. You can attempt to change the
address range of the subnet indpendently (if pre-created) and issue the
resize command again if you encounter this issue.

#### Compute Node appears to be stuck in `starting` state
If you are using pools with `native` container support, compute nodes that
appear to be "stuck" in `starting` state may not really be stuck. During this
phase, all Docker images specified in the `global_resources` are preloaded
on to compute nodes. Thus, it may take a while for your compute nodes to
transition to `idle` from this state.

If you are not using pools with `native` container support, then there may
be an issue allocating the node from the Azure Cloud. Azure Batch
automatically tries to recover from this state, but may not be able to
on occasion. In these circumstances, you can delete the affected nodes
with `pool nodes del --all-starting` and then `pool resize` to scale the
pool back to your desired amount.

#### Compute Node appears to be stuck in `waiting_for_start_task` state
Compute nodes that appear to be "stuck" in waiting for start task may not
really be stuck. If you are not using pools with `native` container support
and are specifying that nodes should block for all Docker images to
be present on the node before allowing scheduling and your Docker images are
large, it may take a while for your compute nodes to transition from waiting
for start task to idle. Additionally, if your Docker images are sourced from
Docker Hub then Docker Hub may apply throttling or outright reject requests
from your pool as compute nodes are attempting to retrieve your images. It
is recommended to isolate from potential Docker Hub issues by provisioning
your own Azure Container Registry within the region of your Batch account
to reduce latency and improve bandwidth. Premium Azure Container Registries
may be an appropriate option for very large pools.

If you are certain the above is not the cause for this behavior, then it
may indicate a regression in the Batch Shipyard code, a new Docker release
that is causing interaction issues (e.g., with nvidia-docker) or some other
problem that was not caught during testing. You can retrieve the compute
node start task stdout and stderr files to diagnose further and report an
issue on GitHub if it appears to be a defect.

#### Compute Node enters `start_task_failed` state
For pools thare are allocated without `native` container support, Batch
Shipyard installs the Docker Host Engine and other requisite software
when the compute node starts. Even with pools with `native` container support,
some additional software is installed along with integrity checks of the
compute node. There is a possibility for the start task to fail due to
transient network faults when issuing system software updates or other
issues. You can turn on automatic rebooting where Batch Shipyard can
attempt to mitigate the issue on your behalf in the `pool.yaml` config file.
Alternatively, you can issue the command
`pool nodes reboot --all-start-task-failed` which will attempt to reboot the
nodes that have entered this state.

If the compute node fails to start properly, Batch Shipyard will automatically
download the compute node's `stdout.txt`, `stderr.txt` and `wd/cascade*.log`
files for the start task into the directory where you ran `shipyard`. The files
will be placed in `<pool name>/<node id>/startup/`. You can examine these
files to see what the possible culprit for the issue is. If it appears to be
transient, you can try to create the pool again. If it appears to be a Batch
Shipyard issue, please report the issue on GitHub.

Additionally, if you have specified an SSH or RDP user for your pool and there
is a start task failure, you can still issue the command `pool user add` to
add the pool remote user and then `pool ssh` to SSH into the node to debug
further, or manually RDP on Windows.

Please note that the start task requires downloading some files that are
uploaded to your Azure Storage account with the command `pool add`. These
files have SAS tokens which allow the Batch compute node to authenticate
with the Azure Storage service to download the files. These SAS tokens are
bound to the storage account key for which they were generated with. If you
change/regenerate your storage account key that these SAS tokens were
originally generated with, then the compute nodes will fail to start as
these files as the SAS tokens bound to these files will no longer be valid.
You will need to recreate your pool in these situations.

#### Compute Node enters `unusable` state
If compute nodes enter `unusable` state then this indicates that there was
an issue allocating the node from the Azure Cloud or that the Azure Batch
service can no longer communicate with the compute node. Azure Batch
automatically tries to recover from such situations, but may not be able to
on occasion. In these circumstances, you can delete the affected nodes
with `pool nodes del --all-unusable` and then resize back up with `pool resize`
or recreate the pool.

Another potential problem for nodes that may enter into this state are
pools which are part of a virtual network. Improper NSG rules can prevent
communication between the compute nodes and the Batch service which will
result in `unusable` nodes.

#### Pool creation fails due to `Could not find an Azure Batch Node Agent Sku`
If you are using a `platform_image`, you may encounter an error such as:

```
RuntimeError: Could not find an Azure Batch Node Agent Sku for this
offer=abc publisher=def sku=xyz. You can list the valid and available
Marketplace images with the command: account images
```

This problem can happen if you are specifying a `sku` that is not listed
by the `account images` command. You will need to update your `sku` field
to one that is listed.

## <a name="task"></a>Job/Task Execution Issues
#### Task is submitted but doesn't run
There are various reasons why this would happen:

1. There are insufficient compute nodes to service the job
2. The task is multi-instance and there are not enough compute nodes to
run the job as specified
3. `jobs.yaml` file was submitted with the wrong `pool.yaml` file causing
a mismatch in the target pool for the jobs
4. `jobs.yaml` file was submitted with the wrong `config.yaml` file causing
an infinite wait on a Docker image to be present that may not exist

#### Task runs and completes but fails with a non-zero exit code or scheduling error
In Azure Batch, a task that completes is independent of if the task is
considered a success or failure. The `jobs tasks list` command will list
the status of all tasks for the jobs specified including exit codes and
any scheduling errors. You can use this information in combination with the
task's stdout and stderr files to determine what went wrong if your task
has completed but has failed.

## <a name="container"></a>Container Issues
#### `pool images update` command doesn't run
The `pool images update` command runs as a normal job if your pool is
comprised entirely of dedicated compute nodes. Thus, your compute
nodes must be able to accommodate this update job and task. If your pool only
has one node in it, it will run as a single task under a job. If the node in
this pool is busy and the `task_slots_per_node` in your `pool.yaml` is either
unspecified or set to 1, then it will be blocked behind the running task.

For pools with more than 1 node, then the update images command will run
as a multi-instance task to guarantee that all nodes in the pool have updated
the specified container image to latest or the given hash. The multi-instance
task will be run on the current number of nodes in the pool at the time
the `pool images update` command is issued. If before the task can be
scheduled, the pool is resized down and the number of nodes decreases, then
the update container images job will not be able to execute and will stay
active until the number of compute nodes reaches the prior number.
Additionally, if `task_slots_per_node` is set to 1 or unspecified in
`pool.yaml` and any task is running on any node, the update container images
job will be blocked until that task completes.

You can work around this behavior by providing the `--ssh` option to the
`pool images update` command. This will use an SSH side-channel to upgrade the
container images on the pool. Please note that this requires a provisioned SSH
user and `ssh` or `ssh.exe` available.

`pool images update` will always use the SSH side-channel method for pools
containing a positive number of low priority nodes or pools which are
`native` mode enabled.
