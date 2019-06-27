# Custom Images with Batch Shipyard
The focus of this article is to explain how to provision an custom image
and then deploy it with Batch Shipyard as the VM image to use for
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
a [Shared Image Gallery resource](https://docs.microsoft.com/azure/virtual-machines/windows/shared-image-galleries)
or an [Azure Managed Image resource](https://docs.microsoft.com/azure/virtual-machines/windows/capture-image-resource).
Using an Azure Managed Image resource for a Batch pool **is no longer
recommended.** You can create Azure Managed Images using Packer, existing
page blob VHDs or exporting managed disks. If using an Azure Managed Image
resource directly, you must create the Image in the same subscription and
region as your Batch account. For Shared Image Gallery resources, the image
must be replicated (and have completed replication) to the same region as
your Batch account.

### Shared Image Gallery vs. Azure Managed Image
It is **strongly recommended** to use Shared Image Gallery resources instead
of directly using an Azure Managed Image for increased reliability, robustness
and performance of scale out (i.e., pool allocation with target node counts
and resize up) operations with Azure Batch pools. These improvements hold even
for Shared Image Gallery resource with a replica count of 1.

This guide will focus on creating Shared Image Gallery resources for use with
Azure Batch and Batch Shipyard.

## Azure Active Directory Authentication Required
Azure Active Directory authentication is required for the `batch` account
regardless of the account mode. This means that the
[credentials configuration file](11-batch-shipyard-configuration-credentials.md)
must include an `aad` section with the appropriate options, including the
authentication method of your choosing.

For Shared Image Gallery access your service principal requires at least
`Contributor` role permission or a
[custom role with the actions](https://docs.microsoft.com/azure/active-directory/role-based-access-control-custom-roles):

* `Microsoft.Compute/galleries/read`
* `Microsoft.Compute/galleries/images/read`
* `Microsoft.Compute/galleries/images/versions/read`

For Azure Managed Image (not recommended) access your service principal
requires at least `Contributor` role permission or a
[custom role with the actions](https://docs.microsoft.com/azure/active-directory/role-based-access-control-custom-roles):

* `Microsoft.Compute/disks/beginGetAccess/action`
* `Microsoft.Compute/images/read`

## Creating Images for use with Azure Batch and Batch Shipyard
It is recommended to either use the
[Azure Image Builder](https://docs.microsoft.com/azure/virtual-machines/windows/image-builder-overview)
service or to use [Packer](https://packer.io/) to create a custom
image that is Shared Image Gallery resource (or a Azure Managed Image resource)
compatible with Azure Batch and Batch Shipyard. You will need to create a
preparation script and install all of the [required software](#provision) as
outlined in the following sections of this guide. For the remainder of this
guide, we will use Packer to showcase creating custom images.

### Creating a Shared Image Gallery Resource with Packer
The [contrib](https://github.com/Azure/batch-shipyard/tree/master/contrib)
area of the repository contain example `packer` scripts to create a Shared
Image Gallery resource from an existing Marketplace platform image. In order
to create a Shared Image Gallery resource directly with Packer, you will
need Packer version 1.4.2 or later.

#### Step 0: Create a Shared Image Gallery
You will need to create a Shared Image Gallery. You can do this either
in the [Portal](https://docs.microsoft.com/azure/virtual-machines/linux/shared-images-portal#create-an-image-gallery)
or via the [Azure CLI](https://docs.microsoft.com/azure/virtual-machines/linux/shared-images#create-an-image-gallery).

Make note of the Shared Image Gallery name and the associated resource group.

#### Step 1: Create an Image Definition
After selecting your Shared Image Gallery, create a new image definition
by selecting `+ Add new image defintion`:

![63-custom-images-sig-1-0.png](https://azurebatchshipyard.blob.core.windows.net/github/63-custom-images-sig-1-0.png)

Fill out the required properties in the blade, ensuring that you select
the proper OS type and desired `Image definition name`. Take note of this
as it will be used later.

![63-custom-images-sig-1-1.png](https://azurebatchshipyard.blob.core.windows.net/github/63-custom-images-sig-1-1.png)

Hit the `Review + create` button to complete the process.

You can also perform this process using the
[Azure CLI](https://docs.microsoft.com/azure/virtual-machines/linux/shared-images#create-an-image-definition).

#### Step 2: Edit the Packer Build Definition
In the Packer JSON build file for Shared Image Gallery (i.e.,
`build-sig.json` if using the contributed Packer scripts), ensure that you
have defined all of the `variables` at the top of the file. Properties of
note are:

* `image_name` is the Image Definition name from Step 1. This will also
be the name of the Azure Managed Image for which the Shared Gallery Image
is sourced from.
* `sig_name` is the Shared Image Gallery name from Step 0.
* `sig_replication_regions` is a comma-separated list of region names to
replicate the image to.
* `sig_resource_group` is the SHared Image Gallery resource group from Step 0.

The `sig_replication_regions` should include regions where you intend to
deploy this image that is in the same region as your Batch account.

When this process completes, Packer will output the results of the build:

```
==> Builds finished. The artifacts of successful builds are:
--> azure-arm: Azure.ResourceManagement.VMImage:

OSType: Linux
ManagedImageResourceGroupName: myrg
ManagedImageName: myimage
ManagedImageId: /subscriptions/01234567-89ab-cdef-0123-456789abcdef/resourceGroups/myrg/providers/Microsoft.Compute/images/myimage
ManagedImageLocation: eastus
ManagedImageSharedImageGalleryId: /subscriptions/01234567-89ab-cdef-0123-456789abcdef/resourceGroups/myrg/providers/Microsoft.Compute/galleries/mysig/images/myimage/versions/1.0.0
```

It is important to note the `ManagedImageSharedGalleryId` as this is used
to populate the `arm_image_id` in the pool configuration file. If you
missed this output and need to retrieve it again, see Step 4.

#### Step 3: Adjust Region Replica Counts (Optional)
To achieve robustness at higher scale, it is recommended to increase the number
of replicas in the region you're intending to deploy to. You can adjust
the replica count in the Portal. Navigate to your Shared Image Gallery and
select your image. Select the `Image versions` under `Settings` and select
the appropriate image version corresponding to your build. Select
`Update replication` under `Settings` to modify the regional replica
counts:

![63-custom-images-sig-3-0.png](https://azurebatchshipyard.blob.core.windows.net/github/63-custom-images-sig-3-0.png)

You can optionally add more regions for replication here as well.

Hit the `Save` button with your changes. It will take some time for the
replication process to complete. You must wait for this process to complete
before attempting to deploy a Batch pool using the Shared Image Gallery
resource.

#### Step 4: Retrieve the Shared Image Gallery Resource Id
If you missed retrieving the Packer output for the Shared Image Gallery
Resource id, you can retrieve it again via the Portal or Azure CLI.
Through the Portal, navigate to your Shared Image Gallery and select your
image. Select the `Image versions` under `Settings` and select the
appropriate image version corresponding to your build. Select `Properties`
under `Settings` and copy the `Resource ID`. Use this id to populate the
`arm_image_id` in the pool configuration file.

#### Step 5: Delete the Azure Managed Image Resource (Optional)
Packer does not automatically delete the Managed Image resource created as
part of the Shared Image Gallery resource creation. You can safely delete
the Managed Image resource if you **do not intend to replicate your image
further** and after the Packer process completes successfully.

## <a name="provision"></a>Provisioning a Custom Image
You will need to ensure that your custom image is sufficiently prepared
before using it as a source image for Batch Shipyard. The following
sub-section will detail the reasons and requisites.

### Inbound Traffic and Ports
Azure Batch requires communication with each compute node for basic
functionality such as task scheduling and health monitoring. If you have
a software firewall enabled on your custom image, please ensure that inbound
TCP traffic is allowed on destination ports 29876 and 29877. Destination port
22 or port 3389 for TCP traffic should also be allowed for SSH or RDP,
respectively, if needed by your scenario. Note that Azure Batch will apply the
necessary inbound security rules to ports 29876 and 29877 through a Network
Security Group on either the virtual network or each network interface of the
compute nodes to block traffic that does not originate from the Azure Batch
service. Port 22 or 3389, however, will be allowed from any source address in
the Network Security Group by default. You can optionally reduce the allowable
inbound address space for SSH and RDP in your software firewall rules or
through the appropriate `remote_access_control` property in the pool
configuration file.

For more information about Batch pools, virtual networks and NSG rules, please
see [this guide](https://docs.microsoft.com/azure/batch/batch-virtual-network).

### Outbound Traffic and Ports
Azure Batch compute nodes must be able to communicate with Azure Storage
servers. Please ensure that oubound TCP traffic is allowed on destination
port 443 for HTTPS connections to in-region Azure Storage services. Note that
any other outbound requests, e.g., for accessing resource files or container
images, will need to be permitted on this port as well.

For more information about Batch pools, virtual networks and NSG rules, please
see [this guide](https://docs.microsoft.com/azure/batch/batch-virtual-network).

### Ephemeral (Temporary) Disk
Azure VMs have ephemeral temporary local disks attached to them which are
not persisted back to Azure Storage. Azure Batch utilizes this space for some
system data and also to store task data for execution. It is important
not to change this location and leave the default as-is (i.e., do not
change the value of `ResourceDisk.MountPoint` in `waagent.conf` or modify
the ephemeral disk via cloud-init).

### SELinux
SELinux controls can prevent a node from starting or performing necessary
required actions correctly. The Azure Batch Node Agent performs tasks which
may not be permitted under certain SELinux policies. In the case where you
want to enforce SELinux controls, it is recommended to first create a
custom image with SELinux set to permissive mode. Use the image to run
a representative scenario or workload, then log into the machine and view
the system audit logs. Afterwards, craft policies to allow these actions
to occur within the context of the Batch node agent. Apply these policies
to a new custom image and set the mode to enforcing.

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
mount on the node local temporary disk, then you must disable the
service to run on boot due to potential races with the disk not being
set up before the service starts. Batch Shipyard will take care of properly
starting the service on boot.

#### SSH Server
An SSH server should be installed and operational on port 22. You can
limit inbound connections through the Batch service deployed NSG on the
virtual network or network interface (and/or through the software firewall
on the host).

#### GPU-enabled Compute Nodes
In order to utilize the GPUs available on compute nodes that have them
(e.g., N-series VMs), the NVIDIA driver must be installed and loaded upon
boot.

Additionally, [nvidia-docker2](https://github.com/NVIDIA/nvidia-docker)
must be installed.

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

### Azure Blob Shared Data Volume
If mounting an Azure Blob Storage container, you will need to install the
[blobfuse](https://github.com/Azure/azure-storage-fuse) software.

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

## Allocating a Pool with a Custom Image
When allocating a compute pool with a custom image, you must ensure the
following:

1. The Shared Gallery Image has been replicated to the same region as your
   Batch account.
2. You are specifying the proper `aad` settings in your credentials
   configuration file for `batch` (or "globally" in the credentials file).
3. Your pool specification has the proper `vm_configuration` settings
   for `custom_image`.

    * The `arm_image_id` points to a valid Shared Gallery Image resource
    * `node_agent` is populated with the correct node agent sku id which
      corresponds to the distribution used in the custom image. For instance,
      if your custom image is based on Ubuntu 18.04, you would use
      `batch.node.ubuntu 18.04` as the `node_agent` value. You can view a
      complete list of supported node agent sku ids with the `account images`
      command.

### Azure Shared Image Gallery Retention Requirements
Ensure that the Shared Image Gallery resource exists for the lifetimes of any
pool referencing the image. Failure to do so can result in pool allocation
failures and/or resize failures.
