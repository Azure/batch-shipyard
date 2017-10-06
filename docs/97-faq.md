# General Guidelines and Frequently Asked Questions

## General Guidelines
* Smaller, widely-used platform (Marketplace) images typically will result
in minimizing pool spin up (allocation) time. Reducing the size of the Docker
images to load will also reduce the time to create a pool.
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
      support ticket in the Azure Portal, or post your question
      [here](https://social.msdn.microsoft.com/Forums/azure/en-US/home?forum=azurebatch).

#### I don't have enough core (or other) quota. How do I increase it?
* Please see this [page](https://docs.microsoft.com/en-us/azure/batch/batch-quota-limit).

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

#### Feature X is missing. Can you add support for it?
* Please open an [issue](https://github.com/Azure/batch-shipyard/issues)
  regarding your request. Pull requests are always welcome!

#### How do I contribute a recipe?
* Please see this [guide](98-contributing-recipes.md).

#### What is `native` under pool `platform_image` and `custom_image`?
`native` designates to Batch Shipyard to attempt to create the pool such
that the pool works under native Docker mode where the compute nodes
understand how to launch and execute Docker containers. Please understand
that only a subset of `platform_image` combinations are compatible with
`native` mode.

Advantages of `native` mode are:
* Batch Shipyard with a provisioned SSH user is no longer necessary to
perform actions such as terminating tasks where tasks are still running or
deleting jobs with running tasks.
* Multi-instance task execution is cleaner. You can execute multiple
multi-instance tasks per job.
* Potentially faster provisioning times, particularly pools with GPU devices.

Disadvantages of `native` mode are:
* `input_data` of any kind at the task-level is not possible.
* `output_data` to `azure_storage` Azure Files (i.e., file shares) is not
possible.
* Peer-to-peer distribution of Docker images is not possible.

#### Does Batch Shipyard support Linux custom images?
* Yes, please see [the guide](63-batch-shipyard-custom-images.md).

#### Does Batch Shipyard support Windows Server Containers?
* Not at this time, we are tracking the issue
  [here](https://github.com/Azure/batch-shipyard/issues/7).
