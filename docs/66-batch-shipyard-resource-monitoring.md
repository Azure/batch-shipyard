# Resource Monitoring with Batch Shipyard
The focus of this article is to explain how to provision a resource monitor
for monitoring Batch pools and RemoteFS clusters.

<img src="https://azurebatchshipyard.blob.core.windows.net/github/README-dash.gif" alt="dashboard" width="1024" />

## Overview
For many scenarios, it is often desirable to have visibility into a set of
machines to gain insights through certain metrics over time. A global
monitoring resource is valuable to avail per-machine and aggregate
metrics for Batch processing workloads as jobs are processed for measurements
such as CPU, memory and network usage. As Batch Shipyard's execution model
is based on containers, insights into container behavior is also desirable
in addition to host-level metrics.

Creating a monitoring system that can monitor ephemeral resources such
as Batch nodes that may autoscale up or down at any moment and across
disparate resources such as Batch pools and RemoteFS clusters can be
challenging. Securing these resources adds additional complexity.
Fortunately, Batch Shipyard has commands that can help setup such monitoring
resources quickly.

*Nota bene:* if you want a simple, non-realtime, host-only based
monitoring solution restricted to Batch pools, you can enable
[Batch Insights](https://github.com/Azure/batch-insights) instead of
the solution described below. You can view the monitored Batch pools
through [Batch Explorer](https://github.com/Azure/BatchExplorer). Please
see the pool and credentials documentation for more information.

## Major Features
* Supports monitoring Azure Batch Pools and Batch Shipyard provisioned
storage clusters
* Automatic service discovery of compute nodes and RemoteFS VMs capable of
adding and removing monitored resources even through Batch pool
autoscale/resize and storage cluster resizes
* Automated installs of all required collectors and services on supported
resources, including Batch pools and RemoteFS VMs
* Fully automated setup of nginx reverse proxy to Grafana (and optionally
Prometheus server) with automatic provisioning of Let's Encrypt TLS
certificates for encrypted HTTP access
* Automatic set up of network security rules for exposed services
* Rich default dashboard for monitoring Batch Shipyard resources out-of-the
box
* Support for monitoring resource VM suspension (deallocation) and restart
* Support for accelerated networking, boot diagnostics and serial console
access
* Automatic SSH keypair provisioning and setup

## Mental Model
A Batch Shipyard provisioned monitoring resource is built on top of different
resources in Azure. To more readily explain the concepts that form a Batch
Shipyard monitoring resource, let's start with a high-level conceptual
layout of all of the components and possible interacting actors.

```
                                  +-------------+  +------------------------+
                                  |             |  |                        |
                                  | Azure Batch |  | Azure Resource Manager |
                                  |             |  |                        |
                                  +---------^---+  +----^-------------------+
                                            |           |
                                            |           |
              +-------------------------------------------------------------------------------------+
              |                             |           |                                           |
              | |-----------------------------------------------------|                             |
              | |                           |           |             |                             |
              | | --------------------------------------------------- |                             |
              | | |                         |           |           | |     +---------------------+ |
+---------+   | | |  +-----------+          | MSI       | MSI       | |     | +-----------------+ | |
|         |   | | |  |           |          |           |           | |     | |                 | | |
| Let's   |   | | |  | Let's     |        +-+-----------+--+        | |     | | Batch Shipyard  | | |
| Encrypt <----------+ Encrypt   |        |                |        | |     | | RemoteFS VM Y   | | |
| CA      |   | | |  | TLS Certs |        | Batch Shipyard |        | |     | |                 | | |
|         |   | | |  |           |        | Heimdall       |        | |     | +---------------+ | | |
+---------+   | | |  +----+------+        |                |     +------------> Node Exporter | | | |
              | | |       |               +-------+--------+     |  | |     | +---------------+ | | |
              | | |       |                       |              |  | |     | |                 | | |
              | | | +-----v--+                    |              |  | |     | +------------+    | | |
              | | | |        |                    |              |  | |     | | Private IP |    | | |
              | | | | nginx  |   +-----------+    | Automated    |  | |     | | 10.2.0.4   |    | | |
              | | | |        |   |           |    | Service      |  | |     | +------------+----+ | |
              | | | +------+ |   |  Grafana  |    | Discovery    |  | |     |         Subnet C    | |
+---------+   | | | | Port +----->           |    |              |  | |     |         10.2.0.0/24 | |
|         +---------> 443  | |   +--------+--+    |              |  | |     +---------------------+ |
| Web     |   | | | +------+ |            |       |              |  | |                             |
| Browser |   | | | | Port | |         +--v-------v-----+        |  | |     +---------------------+ |
|         +---------> 9090 +----------->                |        |  | |     | +-----------------+ | |
+---------+   | | | +------+ |         |   Prometheus   +--------+  | |     | |                 | | |
              | | | |        |         |                |           | |     | | Azure Batch     | | |
              | | | +--------+         +---------+------+           | |     | | Compute Node X  | | |
              | | |                              |                  | |     | |                 | | |
              | | |                              |                  | |     | +---------------+ | | |
              | | +-----------+------------+     |                  | |  +----> Node Exporter | | | |
              | | | Public IP | Private IP |     +-----------------------+  | +----------+----+ | | |
              | | | 1.2.3.4   | 10.0.0.4   |                        | |  +----> cAdvisor |      | | |
              | | +-----------+------------+------------------------+ |     | +----------+      | | |
              | |                                         Subnet A    |     | |                 | | |
              | |                                         10.0.0.0/24 |     | +------------+    | | |
              | +-----------------------------------------------------+     | | Private IP |    | | |
              |                                                             | | 10.1.0.4   |    | | |
              |                                                             | +------------+----+ | |
              |                                                             |         Subnet B    | |
              | Virtual Network                                             |         10.1.0.0/24 | |
              | 10.0.0.0/8                                                  +---------------------+ |
              +-------------------------------------------------------------------------------------+
```

The base layer for all of the resources within a monitoring resource is
an Azure Virtual Network. This virtual network can be shared
amongst other network-level resources such as network interfaces. The virtual
network can be "partitioned" into sub-address spaces through the use of
subnets. In the example above, we have three subnets where
`Subnet A 10.0.0.0/24` hosts the resource monitor,
`Subnet B 10.1.0.0/16` contains a pool of Azure Batch compute nodes to
monitor, and `Subnet C 10.2.0.0/24` contains a Batch Shipyard RemoteFS
cluster to monitor. No resource in `Subnet B` or `Subnet C` is strictly
required for the Batch Shipyard monitoring resource to work, although you
will want either one or the other at the minimum so you have some resource
to monitor.

When provisioning Batch pools or RemoteFS storage clusters, you are able
to specify `prometheus` compatible collectors to install. If configured,
Batch Shipyard takes care of installing these packages to the resources and
are immediately ready to be scraped by the Prometheus server.

When the resource monitor virtual machine is created, the bootstrap
process automatically contacts the Let's Encrypt CA to provision TLS
certificates for nginx. Nginx is configured to reverse proxy requests to
Grafana over the standard HTTPS port (443) and, optionally, to the Prometheus
server on the specified port. Grafana is automatically provisioned with
the correct data source and a rich default dashboard for monitoring Batch
Shipyard resources. Internally, a Batch Shipyard process runs alongside
Grafana and the Prometheus server to enumerate any resources that have
been specified to monitor. The "Batch Shipyard Heimdall" container
encapsulates this functionality by either querying the Azure Batch service
or Azure Resource Manager endpoints for the requested resources to monitor.
No sensitive credentials are passed to the resource monitoring virtual
machine. Instead, Batch Shipyard Heimdall uses Azure MSI to authenticate
with Azure Active Directory using a service principal with least privilege
to enumerate the specified resources to monitor. This information is then
used to populate Prometheus service discovery. Once the Prometheus server
begins to scrape metrics, then this data is available for visualization
in Grafana.

## Configuration
In order to enable resource monitoring, there are a few configuration changes
that must be made to enable this feature. You must enable a resource or
set of resources to be monitored and then create the monitoring resource.

### Azure Active Directory Authentication Required
Azure Active Directory authentication is required to enable monitoring.
Additionally, in order to monitor a Batch pool, that pool must be joined
to the same virtual network as the monitoring resource VM and thus must
join a virtual network upon provisioning.

When executing the `monitor create` command, your service principal must
be at least `Owner` or a
[custom role](https://docs.microsoft.com/azure/active-directory/role-based-access-control-custom-roles)
that does not prohibit the following action along with the ability to
create/read/write resources for the subscription:

* `Microsoft.Authorization/*/Write`

This action is required to enable
[Azure Managed Service Identity](https://docs.microsoft.com/azure/active-directory/managed-service-identity/overview)
on the resource monitoring VM.

### Monitored Resource Configuration
Batch pools and RemoteFS storage clusters can be monitored. Below explains
the configuration required to enable each.

#### Pool Configuration
The following is a sample snippet for a Batch pool to be monitored. Note that
this configuration must be applied prior to creation.

```yaml
pool_specification:
  # ... other settings
  virtual_network:
    # virtual network settings must be set
  prometheus:
    node_exporter:
      enabled: true
    cadvisor:
      enabled: true
```

A `virtual_network` must be specified so the resource monitor can connect
to the compute nodes in the Batch pool. Please see the
[virtual network guide](64-batch-shipyard-byovnet.md) for more information.

The `prometheus` section enables the Prometheus-compatible collectors to
be automatically installed and configured. For Batch pools, two collectors
are available:

1. [Node Exporter](https://github.com/prometheus/node_exporter)
2. [cAdvisor](https://github.com/google/cadvisor)

It is recommended to enable both of these collectors if utilizing
resource monitoring with Batch pool targets. Other `prometheus` options and
more information can be found in the
[Pool configuration doc](13-batch-shipyard-configuration-pool.md).

#### RemoteFS Configuration
The following is a sample snippet for a RemoteFS storage cluster to be
monitored. Note that this configuration must be applied prior to creation.

```yaml
remote_fs:
  # ... other settings
  virtual_network:
    # virtual network settings must be set
  prometheus:
    node_exporter:
      enabled: true
```

The `prometheus` section enables the Prometheus-compatible collectors to
be automatically installed and configured. Only the
[Node Exporter](https://github.com/prometheus/node_exporter) collector is
currently available for RemoteFS clusters. Other `prometheus` options and
more information can be found in the
[RemoteFS configuration doc](15-batch-shipyard-configuration-fs.md).

### Resource Monitor Configuration
The resource monitoring virtual machine requires configuration to provision.

#### Credentials Configuration
Specifying the Grafana admin credentials are required in the credentials
configuration. Below is a sample:

```yaml
credentials:
  # management settings required with aad auth
  management:
    aad:
      # valid aad settings (or at the global level)
    subscription_id: # subscription id required
  # batch aad settings required if monitoring batch pools
  batch:
    aad:
      # valid aad settings (or at the global level)
    account_service_url: # valid batch service url
    resource_group: # batch account resource group
  # ... other required settings
  monitoring:
    grafana:
      admin:
        username: admin
        password: admin
```

Note that you can also use a KeyVault secret id for the `password` or store
the credentials entirely within KeyVault. Please see the
[credentials](11-batch-shipyard-configuration-credentials.md) configuration
guide for more information.

Additionally, Azure Active Directory authentication is required under
`management` and a valid `subscription_id` must be provided. Moreover,
if monitoring Batch pools, Batch authentication must be through Azure
Active Directory for joining a [virtual network](64-batch-shipyard-byovnet.md).

#### Monitor Configuration
The resource monitor must be configured according to the
[monitor configuration doc](16-batch-shipyard-configuration-monitor.md).
Please refer to that guide for a full explanation of each monitoring
configuration option.

## Usage Documentation
The workflow for standing up a monitoring resource is creation followed by
adding an applicable resources to monitor. Below is an example, assuming
monitoring has been properly configured as per prior section guidance.

```shell
# create a resource monitor
shipyard monitor create
# note the FQDN emitted in the log at the end of the provisioning process

# create a Batch pool where work is to be performed
# this hypothetical pool id is mybatchpool
shipyard pool add

# add the Batch pool above as a resource to monitor
shipyard monitor add --poolid mybatchpool
```

After the monitor is added, you can point your web browser at the
monitoring resource FQDN emitted above. Note that there will be a delay
between `monitor add` and the resource showing up in Grafana.

You can remove individual resources to monitor with the command
`monitor remove`. Once you have no need for your monitoring resource, you
can either suspend it or destroy it entirely.

```shell
# remove the prior Batch pool monitor
shipyard monitor remove --poolid mybatchpool

# destroy the monitoring resource entirely
shipyard monitor destroy
```

Please see [this page](20-batch-shipyard-usage.md) for in-depth documentation
on `monitor` command usage.
