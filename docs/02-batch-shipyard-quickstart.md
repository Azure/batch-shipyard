# Batch Shipyard Quickstart
It is recommended to review the full
[in-depth configuration guide](10-batch-shipyard-configuration.md) for
explanations of all of the configuration options available for Batch Shipyard.
However, for those wanting to jump in and deploy an application quickly,
this doc will provide step-by-step instructions. For the following
quickstart example, you may select any of the following Deep Learning
frameworks to quickly get started:
* [CNTK-CPU-OpenMPI](../recipes/CNTK-CPU-OpenMPI)
* [Caffe-CPU](../recipes/Caffe-CPU)
* [TensorFlow-CPU](../recipes/TensorFlow-CPU)
* [Torch-CPU](../recipes/Torch-CPU)

The example MNIST training sample will be used on one Azure Batch compute node
regardless of which Deep Learning framework you prefer for the following.

1. All
[pre-requisites and installation of Batch Shipyard](01-batch-shipyard-installation.md)
to your local machine has been completed. Please note that while Batch
Shipyard works on Windows, some functionality may be disabled. It is
recommended for the best experience to run Batch Shipyard on Linux.
2. Create a directory to hold your configuration files, for example: `config`
3. Copy the sample configuration files from the Deep Learning framework recipe
of your choice to the `config` directory:
  * [CNTK-CPU-OpenMPI](../recipes/CNTK-CPU-OpenMPI/config/singlenode/)
  * [Caffe-CPU](../recipes/Caffe-CPU/config/)
  * [TensorFlow-CPU](../recipes/TensorFlow-CPU/config/)
  * [Torch-CPU](../recipes/Torch-CPU/config/)
4. Edit the `config/credentials.json` file and populate it with your Azure
Batch and Azure Storage credentials. If you do not have an Azure Batch account,
you can create one via the
[Azure Portal](https://azure.microsoft.com/en-us/documentation/articles/batch-account-create-portal/),
[Azure CLI](https://azure.microsoft.com/en-us/documentation/articles/xplat-cli-install/), or
[Azure PowerShell](https://azure.microsoft.com/en-us/documentation/articles/batch-powershell-cmdlets-get-started/).
5. Edit the `config/config.json` file and edit the following settings:
  * `storage_account_settings` to link to the storage account named in step 4.
6. In the main `batch-shipyard` directory (which should contain `shipyard.py`),
run the following commands:
```shell
# create the compute pool
python shipyard.py --configdir config addpool

# ... wait for pool to allocate ...

# add the training job
python shipyard.py --configdir config addjobs

# stream the stdout or stderr file back to local console to monitor progress
# if CNTK-CPU-OpenMPI:
python shipyard.py --configdir config streamfile --filespec cntkjob:dockertask-000:stderr.txt
# if Caffe-CPU:
python shipyard.py --configdir config streamfile --filespec caffejob:dockertask-000:stderr.txt
# if TensorFlow-CPU:
python shipyard.py --configdir config streamfile --filespec tensorflowjob:dockertask-000:stdout.txt
# if Torch-CPU:
python shipyard.py --configdir config streamfile --filespec torchjob:dockertask-000:stdout.txt
```
The last command will stream the stderr or stdout file to your local console
which will provide you progress information about your job.

You can also use the [Azure Portal](https://portal.azure.com) or
[Batch Explorer](https://github.com/Azure/azure-batch-samples) to view more
properties of your Azure Batch accounts, pools, nodes, jobs and tasks.

## In-Depth Configuration Guide
[Batch Shipyard Configuration](10-batch-shipyard-configuration.md) contains
explanations of all of the Batch Shipyard configuration options within the
config files.

## Commandline Usage Guide
[Batch Shipyard Usage](20-batch-shipyard-usage.md) contains explanations for
all of the actions available with the `shipyard.py` tool.
