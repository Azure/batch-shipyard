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
40 for Linux pools. This limit will be removed in a future release.
* Windows Server 2016, Clear Linux, and Oracle Linux are not supported with
Batch Shipyard at this time.
* Task dependencies are incompatible with multi-instance tasks. This is a
current limitation of the underlying Azure Batch service.
* Only Intel MPI can be used in conjunction Infiniband/RDMA on Azure Linux VMs.
This is a current limitation of the underlying VM and host drivers.
* On-premise Docker private registries are not supported at this time due to
VNet requirements.
