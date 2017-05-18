# Current Limitations
Please read the following carefully concerning current limitations with
Batch Shipyard and Docker-enabled compute pools.

### Azure Batch and Batch Shipyard Command Restrictions
The following Azure Batch actions should only be performed through Batch
Shipyard when deploying your workload through this toolkit as Batch
Shipyard needs to take special actions or ensure the intended outcome:
* Task termination (if task is running): use `jobs termtasks`
* Task deletion (if task is running): use `jobs deltasks`
* Job termination (if any tasks are running in the job): use the
  `--termtasks` option with `jobs term`
* Job deletion (if any tasks are running in the job): use the
  `--termtasks` option with `jobs del`
* Pool resize: use `pool resize`
* Pool deletion: use `pool del`

Additionally, you cannot add Batch Shipyard tasks to a non-Batch Shipyard
allocated pool since all of the preparation for each compute node will not
be present in those pools. Please use `pool add` with your pool specification
to create compute resources to execute your Batch Shipyard jobs against.

### General Limitations and Restrictions
* SSH tunnel script generation is only compatible with non-Windows machines.
* Data movement support on Windows is restricted to scp. Both `ssh.exe` and
`scp.exe` must be found through `%PATH%` or in the current working directory.
Rsync is not supported in Windows.
* `pool ssh` support in Windows is only available if `ssh.exe` is found
through `%PATH%` or is in the current working directory.
* Credential encryption support in Windows is available only if `openssl.exe`
is found through `%PATH%` or is in the current working directory.
* Compute pool resize down (i.e., removing nodes from a pool) is not supported
when peer-to-peer transfer is enabled.
* The maximum number of compute nodes with peer-to-peer enabled is currently
40 for Linux pools for non-UserSubscription Batch accounts. This check is
no longer performed before a pool is created and will instead result in
a ResizeError on the pool if not all compute nodes can be allocated.
* Data movement between Batch tasks as defined by `input_data`:`azure_batch`
is restricted to Batch accounts with keys (non-AAD).
* Virtual network support in Batch pools can only be used with
UserSubscription Batch accounts.
* Custom images with UserSubscription Batch accounts are not supported (yet).
* Windows Server 2016, Clear Linux, and Oracle Linux are not supported with
Batch Shipyard at this time.
* Task dependencies are incompatible with multi-instance tasks. This is a
current limitation of the underlying Azure Batch service.
* Only Intel MPI can be used in conjunction Infiniband/RDMA on Azure Linux VMs.
This is a current limitation of the underlying VM and host drivers.
* Adding tasks to the same job across multiple, concurrent Batch Shipyard
invocations may result in failure if task ids for these jobs are
auto-generated.

### Special Considerations for Low-Priority Compute Nodes
* Pool and compute node allocation may take up to the full resize timeout
and not reach full allocation with low priority if a low priority node is
pre-empted and the target number of low priority nodes cannot be reached.
* Pool allocation is considered successful if the target number of dedicated
nodes is reached. If the number of low priority nodes cannot be reached,
a resize error will be logged, but the allocation will continue such as
continuing with SSH user provisioning and data ingress.
* Certain commands may timeout and fail with low priority nodes. As nodes
can be pre-empted at any time, commands that rely on interacting with the
node such as direct SSH access, task termination, etc. may not complete
successfully.
* `pool udi` command will only run as a Batch job if a compute pool is
completely comprised of dedicated nodes. For pools with any low-priority
nodes then images will be updated individually on each node via SSH, thus
requiring an SSH user to be active and allocated on the nodes.
* GlusterFS on compute can only be used on pure dedicated Batch pools.
Allocation will fail if such a shared data volume is specified on a pool with
low priority nodes or if a resize to include low priority nodes is attempted
with a GlusterFS on compute shared data volume.
