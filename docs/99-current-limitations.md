# Current Limitations
Please read the following carefully concerning current limitations with
Batch Shipyard and Docker-enabled compute pools. If using low-priority
compute nodes, please also refer to the
[Low Priority Compute Node Considerations](95-low-priority-considerations.md)
document.

### Azure Batch and Batch Shipyard Command Restrictions
The following Azure Batch actions should only be performed through Batch
Shipyard when deploying your workload through this toolkit as Batch
Shipyard needs to take special actions or ensure the intended outcome:

* Non-`native` container pools only:
    * Task termination (if task is running): use `jobs tasks term`
    * Task deletion (if task is running): use `jobs tasks del`
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
* Tasks can have a maximum run time of 7 days (including time spent for
data movement). This is a current fundamental limitation in the Azure Batch
service.
* For non-`native` container pools, it is recommended to provision an SSH
user to aid in client-side assisted task termination and other tasks that
may require direct SSH access.
* SSH tunnel script generation is only compatible with non-Windows machines.
* Data movement support on Windows is restricted to scp. Both `ssh.exe` and
`scp.exe` must be found through `%PATH%` or in the current working directory.
Rsync is not supported in Windows.
* `pool ssh` support in Windows is only available if `ssh.exe` is found
through `%PATH%` or is in the current working directory.
* `pool images list` currently only lists Docker images.
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
* Clear Linux and Oracle Linux are not supported with Batch Shipyard at this
time.
* Certain features, configuration options and usage commands are not
supported with Windows compute node pools such as on-premises to compute
node direct data ingress, storage cluster mounting, and credential
encryption support.
* Task dependencies are incompatible with multi-instance tasks. This is a
current limitation of the underlying Azure Batch service.
* Only Intel MPI (or polling-based IB uverbs) can be used in conjunction
Infiniband/RDMA on Azure Linux VMs. This is a current limitation of the
underlying VM and host drivers.
* Adding tasks to the same job across multiple, concurrent Batch Shipyard
invocations may result in failure if task ids for these jobs are
auto-generated.
