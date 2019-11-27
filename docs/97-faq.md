# General Guidelines and Frequently Asked Questions

## General Guidelines
* Reducing the size of container images to pre-load will minimize the pool
spin up (allocation time). It is recommended to coalesce layers together or
use multi-stage builds if using Docker images.
* Please keep in mind that pool allocation speed is dependent upon a lot of
factors that Batch Shipyard has no control over.

## Frequently Asked Questions
#### I have an issue or a problem...
* Visit the [troubleshooting guide](96-troubleshooting-guide.md) first;
  your issue may already be cataloged with possible solutions.
* If you checked the troubleshooting guide and your issue is not listed,
  where do I post an issue about it?
    * If it appears to be a Batch Shipyard issue, you can open an
      [issue](https://github.com/Azure/batch-shipyard/issues).
    * If it appears to be an Azure Batch issue, then please create a
      support ticket in the Azure Portal, or open an issue
      [here](https://github.com/Azure/Batch/issues).

#### I don't have enough core (or other) quota. How do I increase it?
* Please see this [page](https://docs.microsoft.com/azure/batch/batch-quota-limit).

#### How do new versions and backward compatiblity work?
* Versioning follows `MAJOR.MINOR.PATCH`:
    * `MAJOR`-level changes typically will be very large modifications for
      supporting new features that may fundamentally change how Batch
      Shipyard works. Expect breaking changes at this level. Prior
      deprecation paths may be removed.
    * `MINOR`-level changes typically will be small to significant changes
      for supporting new features introduced at the Azure Batch level or
      integration efforts and features that supplement the current feature
      set. While breaking changes may happen, we will try to minimize the
      impact for these changes by providing a deprecation path forward if
      feasible.
    * `PATCH`-level changes are typically hotfixes or non-breaking
      additions.
* We realize that introducing breaking changes are inconvenient and
  often burdensome for users. However, we need to achieve a balance of
  iterating quickly to deliver new solutions and features not only
  encompassing core Azure Batch and other Azure services but extending
  to include other technologies at the intersection of cloud Batch
  processing, HPC, containerization and Big Compute.
* You can always lock in your deployments to a specific version by
  using a specific release archive, checking out to a specific release
  tag if using the git repository for consuming releases, or using a
  specific release tag for the Batch Shipyard CLI Docker image. This will
  allow you to upgrade on your schedule and at your own convenience.
* At most two versions of a host operating system are supported at any
  one time.

#### Feature X is missing. Can you add support for it?
* Please open an [issue](https://github.com/Azure/batch-shipyard/issues)
  regarding your request. Pull requests are always welcome!

#### How do I contribute a recipe?
* Please see this [guide](98-contributing-recipes.md).

#### What is `native` under pool `platform_image` and `custom_image`?
`native` designates to Batch Shipyard to attempt to create the pool such
that the pool works under native Docker mode where the compute nodes
"natively" understand how to launch and execute Docker containers. Please
understand that only a subset of `platform_image` combinations are compatible
with `native` mode. You can refer to the
[Batch Shipyard Platform Image support doc](25-batch-shipyard-platform-image-support.md)
for more information. Compliant
[custom images](63-batch-shipyard-custom-images.md) are compatible with
`native` mode.

Advantages of `native` mode are:

* Batch Shipyard with a provisioned SSH user is no longer necessary to
perform actions such as terminating tasks where tasks are still running or
deleting jobs with running tasks in cases where normal Batch task termination
fails to properly end the Docker container processes.
* Direct execution of container tasks by the Batch node agent itself which
lends to cleaner container execution lifecycle management.
* Multi-instance task execution (e.g., MPI job) is cleaner. If your workload
is predominantly multi-instance, then it is strongly recommended to use
`native` mode.

Disadvantages of `native` mode are:

* Singularity containers are not supported.
* `input_data` of any kind at the task-level is not possible; you must either
use `resource_files` or build your own solution.
* `output_data` options are limited and egress to `azure_storage` Azure Files
(i.e., file shares) is not possible. Additionally, there is only limited
resolution of environment variables in output file path specfications.
* `per_job_auto_scratch` (and `auto_scratch`) is not compatible.
* Less aggressive retries of compute node provisioning steps. This can
potentially lead to a greater occurrence of `unusable` nodes.
* Other experimental features may not be supported.

#### Does Batch Shipyard support Linux custom images?
* Yes, please see [the guide](63-batch-shipyard-custom-images.md).

#### Does Batch Shipyard support Windows Server Containers?
* Yes, but with some feature, configuration, and CLI limitations. Please see
the [current limitations](99-current-limitations.md) doc for more information.
* If you receive OS compatibility mismatches when running your Windows
containers, please ensure you have the correct `--isolation` parameter set,
if required. You can view the Windows container compatibility matrix
[here](https://docs.microsoft.com/virtualization/windowscontainers/deploy-containers/version-compatibility).
To learn more about Hyper-V isolation, please see
[this article](https://docs.microsoft.com/virtualization/windowscontainers/manage-containers/hyperv-container).
