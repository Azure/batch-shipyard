# General Guidelines and Frequently Asked Questions

## General Guidelines
* Smaller, widely-used platform (Marketplace) images typically will result
in minimizing pool spin up (allocation) time. Reducing the size of the Docker
images to load will also reduce the time to create a pool.
* Please keep in mind that pool allocation speed is dependent upon a lot of
factors that Batch Shipyard has no control over.

## Frequently Asked Questions
* I have an issue or a problem...
  * Visit the [troubleshooting guide](96-troubleshooting-guide.md) first;
    your issue may already be cataloged with possible solutions.
  * If you checked the troubleshooting guide and your issue is not listed,
    where do I post an issue about it?
    * If it appears to be a Batch Shipyard issue, you can open an
      [issue](https://github.com/Azure/batch-shipyard/issues).
    * If it appears to be an Azure Batch issue, then please create a support
      ticket in the Azure Portal, or post your question
      [here](https://social.msdn.microsoft.com/Forums/azure/en-US/home?forum=azurebatch).
* I don't have enough core (or other) quota. How do I increase it?
  * Please see this [page](https://docs.microsoft.com/en-us/azure/batch/batch-quota-limit).
* How do new versions and backward compatiblity work?
  * Versioning follows `MAJOR.MINOR.PATCH`:
    * `MAJOR`-level changes typically will be very large modifications for
      supporting new features that may fundamentally change how Batch
      Shipyard works. Expect breaking changes at this level. Prior deprecation
      paths may be removed.
    * `MINOR`-level changes typically will be small to significant changes for
      supporting new features introduced at the Azure Batch level or
      integration efforts and features that supplement the current feature
      set. While breaking changes may happen, we will try to minimize the
      impact for these changes by providing a deprecation path forward if
      feasible.
    * `PATCH`-level changes are typically hotfixes or non-breaking additions.
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
* Feature X is missing. Can you add support for it?
  * Please open an [issue](https://github.com/Azure/batch-shipyard/issues)
    regarding your request. Pull requests are always welcome!
* How do I contribute a recipe?
  * Please see this [guide](98-contributing-recipes.md).
* Does Batch Shipyard support Windows Server Containers?
  * Not at this time, we are tracking the issue
    [here](https://github.com/Azure/batch-shipyard/issues/7).
* Does Batch Shipyard support Clear Linux?
  * Not at this time. We are investigating bringing support for Clear Linux
    and Clear Containers to Batch Shipyard.
