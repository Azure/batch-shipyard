# Virtual Networks, Public IPs and Batch Shipyard
The focus of this article is to explain how to bring your own Virtual Network
and/or public IPs with Batch Shipyard. This will allow you to deploy Batch
compute nodes into a subnet within the Virtual Network that you specify and/or
specify your own public IPs for the load balancers for the deployments
underlying the Batch pool.

## Batch Account Modes, Configuration and Settings
The following sections will describe the different account modes along with
configuration and settings to enable you to deploy Batch compute nodes to
an existing Virtual Network and/or public IPs.

### Choose Your Batch Account Mode
You can bring your own virtual network and/or public IPs with either Batch
Service and User Subscription Batch accounts. Outside of management of the
resources deployed to the subnets, there is no difference in Batch-level
functionality. However, it may be more convenient or compliant to use one
mode over the other.

### Azure Active Directory Authentication Required
Azure Active Directory authentication is required for the `batch` account
regardless of the account mode. This means that the
[credentials configuration file](11-batch-shipyard-configuration-credentials.md)
must include an `aad` section with the appropriate options, including the
authentication method of your choosing.

To bring your own virtual network to a pool, your service principal requires
at least the `Virtual Machine Contributor` role permission or a
[custom role with the action](https://docs.microsoft.com/azure/active-directory/role-based-access-control-custom-roles):

* `Microsoft.Network/virtualNetworks/subnets/join/action`

To bring your own public IPs to a pool, your service principal requires
at least the `Virtual Machine Contributor` role permission or a
[custom role with the action](https://docs.microsoft.com/azure/active-directory/role-based-access-control-custom-roles):

* `Microsoft.Network/virtualNetworks/read`
* `Microsoft.Network/virtualNetworks/subnets/join/action`
* `Microsoft.Network/publicIPAddresses/read`
* `Microsoft.Network/publicIPAddresses/join/action`

## Virtual Networks

### `virtual_network` Pool configuration
To deploy Batch compute nodes into a subnet within a Virtual Network that
you specify, you will need to define the `virtual_network` property in the
pool configuration file. The template is:

```yaml
  virtual_network:
    arm_subnet_id: /subscriptions/<subscription_id>/resourceGroups/<resource_group>/providers/Microsoft.Network/virtualNetworks/<virtual_network_name>/subnets/<subnet_name>
    name: myvnet
    resource_group: resource-group-of-vnet
    create_nonexistant: false
    address_space: 10.0.0.0/16
    subnet:
      name: subnet-for-batch-vms
      address_prefix: 10.0.0.0/20
```

If you specify an `arm_subnet_id`, then all other options within
the `virtual_network` property are ignored. Ensure that the `arm_subnet_id`
includes the subnet postfix of the virtual network resource id. **Your Batch
account must reside within the same subscription and region as the Virtual
Network.**

If you do not specify an `arm_subnet_id`, then you will need to specify
the individual components of the Virtual Network and Subnet in the other
properties. You can also allow Batch Shipyard to create the Virtual Network
on your behalf.

**Note:** It is recommended to deploy Batch compute nodes in their own
exclusive subnet.

If you provide `management` credentials, then Batch Shipyard will
automatically validate that the subnet has enough logical IP address space
to fit the desired number of target dedicated and low priority compute nodes.
Note that this calculation does not consider autoscale where the number of
nodes can exceed the specified targets.

### Forced Tunneling and User-Defined Routes
If you are redirecting Internet-bound traffic from the subnet back to
on-premises, then you may have to add
[user-defined routes](https://docs.microsoft.com/azure/virtual-network/virtual-networks-udr-overview)
to that subnet. Please follow the instructions found in this
[document](https://docs.microsoft.com/azure/batch/batch-virtual-network#user-defined-routes-for-forced-tunneling).

## Public IPs
For pools that are not internode communication enabled, more than 1 public IP
and load balancer may be created for the pool. If you are not bringing your
own public IPs, they are allocated in the subscription that has allocated the
virtual network. If you are not bringing your own public IPs, ensure that
the sufficient Public IP quota has been granted for the subscription of the
virtual network (and is sufficient for any pool resizes that may occur).

If you are bringing your own public IPs, you must supply a sufficient number
of public IPs in the pool configuration for the maximum number of compute
nodes you intend to deploy for the pool. The current requirements are
1 public IP per 100 nodes.

Note that enabling internode communication is not recommended unless
running MPI (multinstance) jobs as this will restrict the upper-bound
scalability of the pool.

### `public_ips` Pool configuration
To deploy Batch compute nodes with pre-defined public IPs that
you specify, you will need to define the `public_ips` property in the
pool configuration file. The template is:

```yaml
  public_ips:
    - /subscriptions/<subscription_id>/resourceGroups/<resource_group>/providers/Microsoft.Network/publicIPAddresses/<public_ip_name1>
    # ... more as needed
```

The subscription and region for which the public IPs have been allocated
must match the subscription and region of the Batch account.

Public IPs that you specify for the Batch pool:

* Must not already be attached to another resource
* Must have a DNS name label specified

Batch Shipyard will perform basic validation of the public IPs given but will
not check if the IP address has already been associated with another resource.

## Network Security
Azure provides a resource called a Network Security Group that allows you
to define security rules to restrict inbound and outbound network traffic
on to the associated resources. A Network Security Group can be attached
to one more resources and more than one Network Security Group can work
in concert with another Network Security Group operating on a different
set of resources within the deployment.

When specifying your own Virtual Network for Batch compute nodes to deploy
into, Azure Batch does not modify or create a Network Security Group at the
Virtual Network level (associated with subnets). Instead, Azure Batch creates
necessary Network Security Groups and attaches them to the individual
Network Interfaces for each VM instance within a VM ScaleSet. The Network
Security Group that Batch creates will deny any external IP traffic bound for
the two required open ports on Azure Batch Virtual Machine configuration
compute nodes (the node types used by Batch Shipyard) except for packets
originating from the Azure Batch service. Therefore, any external traffic
that is routed by the load balancer to the backend NAT pool of virtual
machines will be ultimately filtered by this Network Security Group bound for
the two required ports.

### Network Security Group on the Virtual Network
If you have specified a Network Security Group on the Virtual Network at the
subnet level, then you will need to create a single `Inbound Security Rule`
to allow traffic in at the Virtual Network level for Batch compute nodes to
successfully operate.

Ports `29876` and `29877` must allow `TCP` traffic from the
`Source service tag` of `BatchNodeManagement` (or
`BatchNodeManagement.[Region]`) to `Any` Destination as shown below:

![64-byovnet-nsg-inbound-rule.png](https://azurebatchshipyard.blob.core.windows.net/github/64-byovnet-nsg-inbound-rule.png)

This will prevent external traffic bound for those ports from entering your
Virtual Network.

If you wish to apply additional inbound security rules for the remote access
port (i.e., `SSH`), then you can create either utilize the
`remote_access_control` property in the pool configuration file or manually
add another `Inbound Security Rule` with the destination port range to be `22`
and protocol of `TCP` for SSH or a destination port range of `3389` and
protocol of `TCP` for RDP access. The source IP address space can be whatever
your situation requires. You can even create a deny rule (either
automatically through `remote_access_control` in the pool configuration or
manually) for this port if you do not want to expose this port and do not
want to configure a software firewall.

**Note:** Batch compute nodes must be able to communicate with Azure Storage
servers. If you are restricting outbound network traffic through the Network
Security Group, please ensure that oubound `TCP` traffic is allowed on port
`443` for HTTPS connections. If you are using `Destination Service Tags` to
restrict outbound network traffic, ensure that you have either the generic
`Storage` service tag or the correct `Storage.<region>` service tag.
Additionally, ensure that if you are specifying the destination port that
you provide sufficient rules to cover all outbound requests over port `443`
including potential requests to other storage regions or any application
logic that may use port `443`.

## Additional Configuration Documentation
Please see the [pool configuration guide](13-batch-shipyard-configuration-pool.md)
for a full explanation of each pool configuration option. Please see the
[credentials configuration guide](11-batch-shipyard-configuration-credentials.md)
for a full explanation of each credential configuration option.
