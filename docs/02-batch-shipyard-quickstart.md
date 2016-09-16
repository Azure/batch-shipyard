# Batch Shipyard Quickstart
It is recommended to look over the full
[in-depth configuration guide](10-batch-shipyard-configuration.md) for
explanations of all of the configuration options available for Batch Shipyard.

However, for those wanting to jump in and deploy an application quickly,
this doc will provide step-by-step instructions. For the following example,
we will execute the
[CNTK-CPU-OpenMPI recipe](../recipes/CNTK-CPU-OpenMPI) on one machine using
the example MNIST training sample.

1. All
[pre-requisites and installation of Batch Shipyard](01-batch-shipyard-installation.md)
to your local machine has been completed.
2. Create a directory to hold your configuration files, for example: `config`
3. Copy the [credentials.json](../config_templates/credentials.json) to the
`config` directory
4. Edit the `config/credentials.json` file and populate it with your Azure
Batch and Azure Storage credentials. If you do not have an Azure Batch account,
you can create one via the
[Azure Portal](https://azure.microsoft.com/en-us/documentation/articles/batch-account-create-portal/),
[Azure CLI](https://azure.microsoft.com/en-us/documentation/articles/xplat-cli-install/), or
[Azure PowerShell](https://azure.microsoft.com/en-us/documentation/articles/batch-powershell-cmdlets-get-started/).
5. Copy the [sample configuration files](../recipes/CNTK-CPU-OpenMPI/config/singlenode/)
to the `config` directory
6. Edit the `config/pool.json` file and edit the following settings:
  * `id` modify to `mycntkpool`
  * `vm_size` modify to `STANRDARD_F1`
7. Edit the `config/config.json` file and edit the following settings:
  * `storage_account_settings` to link to the storage account named in step 4.
8. In the main `batch-shipyard` directory (which should contain `shipyard.py`),
run the following commands:
```
python shipyard.py --configdir config addpool

... wait for pool to allocate ...

python shipyard.py --configdir config addjobs
python shipyard.py --configdir config streamfile --filespec cntk:dockertask-000:stderr.txt
```
The last command will stream the standard error file to your local console
which will provide you progress information about your job.

You can also use the [Azure Portal](https://portal.azure.com) or
[Batch Explorer](https://github.com/Azure/azure-batch-samples) to view more
properties of your accounts, pools, nodes, jobs and tasks.

## In-Depth Configuration Guide
[Batch Shipyard Configuration](10-batch-shipyard-configuration.md) contains
explanations of all of the Batch Shipyard configuration options within the
config files.
