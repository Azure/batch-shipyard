# Low Priority Compute Node Considerations
Please read the following carefully concerning pools allocated with low-
priority compute nodes. You may also want to read the
[Azure Batch Low Priority Compute Node](https://docs.microsoft.com/en-us/azure/batch/batch-low-pri-vms)
documentation.

### Pool Allocation and Resizing
* Low priority compute nodes can only be allocated with Batch Service
(i.e., not User Subscription) Batch accounts.
* Pool and compute node allocation may take up to the full resize timeout
and not reach full allocation with low priority if a low priority node is
pre-empted and the target number of low priority nodes cannot be reached.
* Pool allocation is considered successful if the target number of dedicated
nodes is reached. If the number of low priority nodes cannot be reached,
a resize error will be logged, but the allocation will continue such as
continuing with SSH user provisioning and data ingress.
* An SSH user is recommended to be provisioned so commands that rely on
SSH access for low-priority nodes such as `pool udi` are able to be run.

### Command Behavior
* Certain commands may timeout and fail with low priority nodes. As nodes
can be pre-empted at any time, commands that rely on interacting with the
node such as direct SSH access, task termination, etc. may not complete
successfully.
* `pool udi` command will only run as a Batch job if a compute pool is
completely comprised of dedicated nodes. For pools with any low-priority
nodes, images will be updated individually on each node via SSH, thus
requiring an SSH user to be active and allocated on the nodes.

### Shared Filesystems
* GlusterFS on compute can only be used on pure dedicated Batch pools.
Allocation will fail if such a shared data volume is specified on a pool with
low priority nodes or if a resize to include low priority nodes is attempted
with a GlusterFS on compute shared data volume.
