# General Guidelines and Frequently Asked Questions

## General Guidelines
* You can try to use the smallest distribution available on Azure to minimize
pool spin up (allocation) time. `Credativ Debian` distribution would be a
good choice if you do not require specialized hardware (i.e., GPU or
Infiniband) support. However, please keep in mind that pool allocation speed
is dependent upon a lot of factors that Batch Shipyard has no control over.

## Frequently Asked Questions
* I have an issue or a problem, where do I post an issue about it?
  * If it appears to be a Batch Shipyard issue, you can open an
    [issue](https://github.com/Azure/batch-shipyard/issues). If it appears
    to be an Azure Batch issue, then please create a support ticket in the
    Azure Portal, or post your question
    [here](https://social.msdn.microsoft.com/Forums/azure/en-US/home?forum=azurebatch).
* I don't have enough core (or other) quota. How do I increase it?
  * Please see this [page](https://docs.microsoft.com/en-us/azure/batch/batch-quota-limit).
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
