# Custom Images with Batch Shipyard
The focus of this article is to explain how to provision an ARM Image
resource and then deploy it with Batch Shipyard as the VM image to use for
your compute node hosts.

## Background: Azure Resources and Azure Batch Custom Images
Azure Batch allows provisioning compute nodes with custom images with both
Batch Service and User Subscription Batch accounts. This allows users to
customize the compute node with software, settings, etc. that fit their use
case. With containerization, this requirement is weakened but some users may
still want to customize the host compute node environment with particular
versions of software such as the Docker Host engine or pre-install and embed
certain software.

Azure Batch only supports creating compute nodes from custom images through
ARM Image resources. You can create ARM Images using existing page blob VHDs
or exporting managed disks. You must create the Image in the same subscription
and region as your Batch account.

### Creating an ARM Image via Azure Portal
The following will step you through creating an ARM Image from an existing
page blob VHD source through the [Azure Portal](https://portal.azure.com/).

#### Step 1: Navigate to the ARM Image Blade
On the left, you should see an `Images` option. If you do not, hit
`More services >` on the bottom left and type `Images` in the search box.

![63-custom-images-arm-image-1.png](https://azurebatchshipyard.blob.core.windows.net/github/63-custom-images-arm-image-1.png)

#### Step 2: Create an Image
Select `+ Add` to bring up the create image blade:

![63-custom-images-arm-image-2.png](https://azurebatchshipyard.blob.core.windows.net/github/63-custom-images-arm-image-2.png)

In the Create image blade, assign a `Name` to your image. Ensure that
the `Subscription` and `Location` associated with this image is in the same
subscription and location as your Batch account. Select the proper `OS type`
and then click `Browse` to select the source Storage blob. If you do not
see the Storage Account with your source VHD, you must copy it into an ARM
Storage Account within the same `Location` that you have selected.
You can use [blobxfer](https://github.com/Azure/blobxfer) or
[AzCopy](https://azure.microsoft.com/en-us/documentation/articles/storage-use-azcopy/)
to copy your page blob VHDs if they are in a different region than your
Batch account. Select the proper `Account type` if you are using HDD or
SSD backed VMs and then hit `Create` to finish the process.

![63-custom-images-arm-image-3.png](https://azurebatchshipyard.blob.core.windows.net/github/63-custom-images-arm-image-3.png)

#### Step 3: Retrieve the ARM Image Resource Id
After the Image has been created, navigate to the `Images` blade, select
your image and then click on `Overview`. In the Overview blade, at the
bottom, you should see a `RESOURCE ID`. Click on the copy button to copy
the ARM Image Resource Id into your clipboard. This is the value you should
use for the `arm_image_id` in the pool configuration file.

![63-custom-images-arm-image-4.png](https://azurebatchshipyard.blob.core.windows.net/github/63-custom-images-arm-image-4.png)

### Azure Active Directory Authentication Required
Azure Active Directory authentication is required for the `batch` account
regardless of the account mode. This means that the
[credentials configuration file](11-batch-shipyard-configuration-credentials.md)
must include an `aad` section with the appropriate options, including the
authentication method of your choosing.

Your service principal requires at least `Contributor`
role permission or a
[custom role with the actions](https://docs.microsoft.com/en-us/azure/active-directory/role-based-access-control-custom-roles):

* `Microsoft.Compute/disks/beginGetAccess/action`
* `Microsoft.Compute/images/read`

## Provisioning a Custom Image
You will need to ensure that your custom image is sufficiently prepared
before using it as a source VHD for Batch Shipyard. The following
sub-section will detail the reasons and requisites.

### Inbound Traffic and Ports
Azure Batch requires communication with each compute node for basic
functionality such as task scheduling and health monitoring. If you have
a software firewall enabled on your custom image, please ensure that inbound
TCP traffic is allowed on ports 29876 and 29877. Port 22 for TCP traffic
should also be allowed for SSH. Note that Azure Batch will apply the
necessary inbound security rules to ports 29876 and 29877 through a Network
Security Group on either the virtual network or each network interface of the
compute nodes to block traffic that does not originate from the Azure Batch
service. Port 22, however, will be allowed from any source address in the
Network Security Group. You can optionally reduce the allowable inbound
address space for SSH on your software firewall rules or through the Azure
Batch created Network Security Group applied to compute nodes.

### Outbound Traffic and Ports
Azure Batch compute nodes must be able to communicate with Azure Storage
servers. Please ensure that oubound TCP traffic is allowed on port 443 for
HTTPS connections.

### Ephemeral (Temporary) Disk
Azure VMs have ephemeral temporary local disks attached to them which are
not persisted back to Azure Storage. Azure Batch utilizes this space for some
system data and also to store task data for execution. It is important
not to change this location and leave the default as-is (i.e., do not
change the value of `ResourceDisk.MountPoint` in `waagent.conf`).

### Batch Shipyard Node Preparation and Custom Images
For non-custom images (i.e., platform images or Marketplace images), Batch
Shipyard takes care of preparing the compute node with the necessary
software in order for tasks to run with Batch Shipyard.

Because custom images can muddy the assumptions with what is available or
not in the operating system, Batch Shipyard requires that the user prepare
the custom image with the necessary software and only attempts to modify
items that are needed for functionality. Software that is required is
checked during compute node preparation.

### Base Required Software
#### Docker Host Engine
The [Docker](https://docker.com) host engine must be installed and must
be invocable as root with default path and permissions. The Docker socket
(`/var/run/docker.sock`) must be available (it is available by default).

**Important Note:** If you have modified the Docker Root directory to
mount on the node local temporary disk, then you must not enable the
service to run on boot due to potential races with the disk not being
set up properly before the service starts.

#### SSH Server
An SSH server should be installed and operational on port 22. You can
limit inbound connections through the Batch service deployed NSG on the
virtual network or network interface (and/or through the software firewall
on the host).

#### GPU-enabled Compute Nodes
In order to utilize the GPUs available on compute nodes that have them
(e.g., N-series VMs), the NVIDIA driver must be installed and loaded upon
boot.

Additionally, [nvidia-docker](https://github.com/NVIDIA/nvidia-docker)
must be installed.

**Important Note:** If you have modified the Docker Root directory to
mount on the node local temporary disk, then you must not enable the
nvidia-docker service to run on boot due to potential races with the disk
not being set up properly before the service starts.

#### Infiniband/RDMA-enabled Compute Nodes
The host VM Infiniband/RDMA stack must be enabled with the proper drivers
and the required user-land software for Infiniband installed. It is best to
base a custom image off of the existing Azure platform images that support
Infiniband/RDMA.

#### Storage Cluster Auto-Linking and Mounting
If mounting a storage cluster, the required NFSv4 or GlusterFS client tooling
must be installed and invocable such that the auto-link mount functionality
is operable. Both clients need not be installed unless you are mounting
both types of storage clusters.

#### GlusterFS On Compute
If a GlusterFS on compute shared data volume is required, then GlusterFS
server and client tooling must be installed and invocable so the shared
data volume can be created amongst the compute nodes.

### Installed/Configured Software
Batch Shipyard may install and/or configure a minimal amount of software
to enusre that components and directives work as intended.

#### Encryption Certificates and Credential Decryption
If employing credential encryption, Batch Shipyard will exercise the necessary
logic to decrypt any encrypted field if credential encryption is enabled.
Properties in the global configuration should be enabled as per requirements
as if deploying a non-Custom Image-based compute node.

#### Batch Shipyard Docker Images
Batch Shipyard Docker images required for functionality on the compute node
will be automatically installed.

#### Singularity Container Runtime
Batch Shipyard will install and configure the Singularity Continer Runtime
on Ubuntu and CentOS/RHEL hosts.

### Packer Samples
The [contrib](https://github.com/Azure/batch-shipyard/tree/master/contrib)
area of the repository contain example `packer` scripts to create a custom
image from an existing Marketplace platform image.

## Allocating a Pool with a Custom Image
When allocating a compute pool with a custom image, you must ensure the
following:

1. The ARM Image is in the same subscription and region as your Batch account.
2. You are specifying the proper `aad` settings in your credentials
   configuration file for `batch` (or "globally" in the credentials file).
3. Your pool specification has the proper `vm_configuration` settings
   for `custom_image`.
   * The `arm_image_id` points to a valid ARM Image resource
   * `node_agent` is populated with the correct node agent sku id which
     corresponds to the distribution used in the custom image. For instance,
     if your custom image is based on Ubuntu 16.04, you would use
     `batch.node.ubuntu 16.04` as the `node_agent` value. You can view a
     complete list of supported node agent sku ids with the `pool listskus`
     command.
