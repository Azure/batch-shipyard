# Current Limitations
Please read the following carefully concerning current limitations with
Batch Shipyard and Docker-enabled compute pools.

The following Azure Batch actions should only be performed through Batch
Shipyard when deploying your workload through this toolkit as Batch
Shipyard needs to take special actions or ensure the intended outcome:
* Pool resize: use `pool resize`
* Task termination (if task is running): use `jobs termtasks`
* Task deletion (if task is running): use `jobs deltasks`
* Job termination (if any tasks are running in the job): use the
  `--termtasks` option with `jobs term`
* Job deletion (if any tasks are running in the job): use the
  `--termtasks` option with `jobs del`

The following are general limitations or restrictions:
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
