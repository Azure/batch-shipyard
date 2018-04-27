# Batch Shipyard Platform Image Support
The following table is a list of supported platform images for the Batch
Shipyard release that is tied to the version of this documentation. Note that
support outlined in this document is only for Batch Shipyard and is a subset
of Marketplace images supported by the core Azure Batch service.

### CentOS

| Publisher | Offer      | Sku | GPU | IB/RDMA |
|-----------|------------|-----|:---:|:-------:|
| OpenLogic | CentOS     | 7.3 |  X  |         |
| OpenLogic | CentOS     | 7.4 |     |         |
| OpenLogic | CentOS-HPC | 7.1 |     |    X    |
| OpenLogic | CentOS-HPC | 7.3 |  X  |    X    |

### Debian

| Publisher | Offer  | Sku | GPU | IB/RDMA |
|-----------|--------|-----|:---:|:-------:|
| Credativ  | Debian | 8   |     |         |
| Credativ  | Debian | 9   |     |         |

### SLES

SLES is not supported at this time.

### Ubuntu

| Publisher | Offer        | Sku         | GPU | IB/RDMA |
|-----------|--------------|-------------|:---:|:-------:|
| Canonical | UbuntuServer | 16.04-LTS   |  X  |  X (1)  |

**(1)** IB/RDMA for Ubuntu is only supported with a custom image. Please
see the [packer](../contrib/packer) scripts and consult the
[custom image guide](63-batch-shipyard-custom-images.md) for information
on how to create a compliant custom image.

### Windows

| Publisher              | Offer                   | Sku                                            | GPU | IB/RDMA |
|------------------------|-------------------------|------------------------------------------------|:---:|:-------:|
| MicrosoftWindowsServer | WindowsServer           | 2016-Datacenter-with-Containers                |     |         |
| MicrosoftWindowsServer | WindowsServerSemiAnnual | Datacenter-Core-1709-with-Containers-smalldisk |     |         |
