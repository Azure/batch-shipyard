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

### Enabling `microsoft-azure-batch` Native Images
For Batch-managed pool allocation Batch accounts, no action is needed to
enable use of `microsoft-azure-batch` published `native` images. For User
Subscription pool allocation Batch accounts, you will need to explicitly
accept Marketplace terms for each image and image version. Periodically new
image versions will be published and you will need to accept terms
individually for each image version. If you do not accept Marketplace terms
for these images and attempt to deploy a Batch pool with a
`microsoft-azure-batch` `native` image using a User subscription pool
allocation Batch account, you will observe a Resize Error on your pool with
the error `AllocationFailed: Desired number of dedicated nodes could not be
allocated`. The error details will have the message: `Reason: Allocation
failed due to marketplace purchase eligibilty check returned errors`.

You can accept Marketplace terms for `microsoft-azure-batch` published
`native` images using the Azure CLI:

1. Ensure that you are on the correct subscription id of the Batch account
in the Azure CLI.
2. Run `az vm image list --all --publisher microsoft-azure-batch`
3. Find the correlated VM image using the tables provided below. Locate
the `urn` of that image in the JSON object in the output of the command.
4. Run `az vm image accept-terms --urn <corresponding-urn>` for the
corresponding `urn` to accept the terms for the image.

## Image Support Matrix for Batch Shipyard

### CentOS

| Publisher             | Offer                 | Sku | GPU | IB/RDMA | Native Only | Native Convert |
|-----------------------|-----------------------|-----|:---:|:-------:|:-----------:|:--------------:|
| microsoft-azure-batch | centos-container      | 7-4 |  X  |         |      X      |                |
| microsoft-azure-batch | centos-container      | 7-7 |  X  |         |      X      |                |
| microsoft-azure-batch | centos-container-rdma | 7-4 |  X  |  X (4)  |      X      |                |
| microsoft-azure-batch | centos-container-rdma | 7-7 |  X  |  X (5)  |      X      |                |
| OpenLogic             | CentOS                | 7.4 |  X  |         |             |        X       |
| OpenLogic             | CentOS                | 7.7 |  X  |         |             |        X       |
| OpenLogic             | CentOS                | 8.0 |  X  |         |             |                |
| OpenLogic             | CentOS-HPC            | 7.4 |  X  |  X (4)  |             |        X       |
| OpenLogic             | CentOS-HPC            | 7.7 |  X  |  X (5)  |             |        X       |

### Debian

| Publisher | Offer     | Sku | GPU | IB/RDMA | Native Only | Native Convert |
|-----------|-----------|-----|:---:|:-------:|:-----------:|:--------------:|
| Debian    | Debian-10 | 10  |     |         |             |                |

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
