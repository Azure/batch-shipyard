# Batch Shipyard Platform Image Support
The following table is a list of supported platform images for the Batch
Shipyard release that is tied to the version of this documentation. Note that
support outlined in this document is only for Batch Shipyard and is a subset
of Marketplace images supported by the core Azure Batch service.

**Native container support notes:**

* `Native Only` denotes that the platform image can only be used in native
container mode.
* `Native Convert` denotes that the specified platform image is compatible
with `native` set to `true` in the pool configuration and will automatically
be converted to the native equivalent on pool provisioning.

Please see the [FAQ](97-faq.md) for more information about native mode
container pools.

### CentOS

| Publisher             | Offer                 | Sku | GPU | IB/RDMA | Native Only | Native Convert |
|-----------------------|-----------------------|-----|:---:|:-------:|:-----------:|:--------------:|
| microsoft-azure-batch | centos-container      | 7-4 |  X  |         |      X      |                |
| microsoft-azure-batch | centos-container      | 7-6 |  X  |         |      X      |                |
| microsoft-azure-batch | centos-container      | 7-7 |  X  |         |      X      |                |
| microsoft-azure-batch | centos-container-rdma | 7-4 |  X  |  X (4)  |      X      |                |
| microsoft-azure-batch | centos-container-rdma | 7-6 |  X  |  X (5)  |      X      |                |
| microsoft-azure-batch | centos-container-rdma | 7-7 |  X  |  X (5)  |      X      |                |
| OpenLogic             | CentOS                | 7.4 |  X  |         |             |        X       |
| OpenLogic             | CentOS                | 7.6 |  X  |         |             |        X       |
| OpenLogic             | CentOS                | 7.7 |  X  |         |             |        X       |
| OpenLogic             | CentOS-HPC            | 7.4 |  X  |  X (4)  |             |        X       |
| OpenLogic             | CentOS-HPC            | 7.6 |  X  |  X (5)  |             |        X       |
| OpenLogic             | CentOS-HPC            | 7.7 |  X  |  X (5)  |             |        X       |

### Debian

| Publisher | Offer  | Sku | GPU | IB/RDMA | Native Only | Native Convert |
|-----------|--------|-----|:---:|:-------:|:-----------:|:--------------:|
| Credativ  | Debian | 9   |     |         |             |                |

### SLES

SLES is not supported at this time.

### Ubuntu

| Publisher             | Offer                        | Sku         | GPU |  IB/RDMA  | Native Only | Native Convert |
|-----------------------|------------------------------|-------------|:---:|:---------:|:-----------:|:--------------:|
| Canonical             | UbuntuServer                 | 16.04-LTS   |  X  |  X (1)    |             |     X (2,4)    |
| Canonical             | UbuntuServer                 | 18.04-LTS   |  X  |  X (1)    |             |                |
| microsoft-azure-batch | ubuntu-server-container      | 16-04-lts   |  X  |           |      X      |                |
| microsoft-azure-batch | ubuntu-server-container-rdma | 16-04-lts   |  X  |  X (3,4)  |      X      |                |

### Windows

| Publisher              | Offer                   | Sku                                            | GPU | IB/RDMA | Native Only | Native Convert |
|------------------------|-------------------------|------------------------------------------------|:---:|:-------:|:-----------:|:--------------:|
| MicrosoftWindowsServer | WindowsServer           | 2016-Datacenter-with-Containers                |     |         |      X      |                |
| MicrosoftWindowsServer | WindowsServer           | 2019-Datacenter-with-Containers                |     |         |      X      |                |
| MicrosoftWindowsServer | WindowsServer           | 2019-Datacenter-with-Containers-smalldisk      |     |         |      X      |                |
| MicrosoftWindowsServer | WindowsServer           | 2019-Datacenter-Core-with-Containers           |     |         |      X      |                |
| MicrosoftWindowsServer | WindowsServer           | 2019-Datacenter-Core-with-Containers-smalldisk |     |         |      X      |                |
| MicrosoftWindowsServer | WindowsServer           | Datacenter-Core-1903-with-Containers-smalldisk |     |         |      X      |                |
| MicrosoftWindowsServer | WindowsServerSemiAnnual | Datacenter-Core-1809-with-Containers-smalldisk |     |         |      X      |                |

## Notes
1. IB/RDMA is supported for this host OS with a custom image unless
utilizing the native conversion option. Please see the
[packer](../contrib/packer) scripts and consult the
[custom image guide](63-batch-shipyard-custom-images.md) for information
on how to create a compliant custom image.
2. Native conversion of this platform image will enable IB/RDMA automatically.
3. The Intel MPI runtime is not present by default on this image, however,
it is automatically installed through Batch Shipyard for Network Direct
IB/RDMA VM sizes.
4. Only supported on Network Direct IB/RDMA VM sizes.
5. Only supported on SR-IOV IB/RDMA VM sizes.
