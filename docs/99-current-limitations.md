# Current Limitations
Please read the following carefully concerning current limitations with
Batch Shipyard and Docker-enabled compute pools.

* Compute pool resize down (i.e., removing nodes from a pool) is not supported
when peer-to-peer transfer is enabled.
* Compute pool resize up (i.e., adding nodes to a pool) is not supported with
GlusterFS network file shares.
* The maximum number of compute nodes with peer-to-peer enabled is currently
40 for Linux pools. This limit will be removed in a future release.
* Oracle Linux is not supported with Batch Shipyard at this time.
* Task dependencies are incompatible with multi-instance tasks. This is a
current limitation of the underlying Azure Batch service.
* Only Intel MPI can be used in conjunction Infiniband/RDMA on Azure Linux VMs.
This is a current limitation of the underlying VM and host drivers.
* On-premise Docker private registries are not supported at this time due to
VNet requirements.
