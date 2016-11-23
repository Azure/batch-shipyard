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
* [Keras+Theano-CPU](../recipes/Keras+Theano-CPU)
* [MXNet-CPU](../recipes/MXNet-CPU)
* [TensorFlow-CPU](../recipes/TensorFlow-CPU)
* [Torch-CPU](../recipes/Torch-CPU)

The example MNIST training sample will be used on one Azure Batch compute node
regardless of which Deep Learning framework you prefer for the following.

1. All
[pre-requisites and installation of Batch Shipyard](01-batch-shipyard-installation.md)
to your local machine has been completed. Please note that while Batch
Shipyard works on Windows, some functionality may be disabled. It is
recommended for the best experience to run Batch Shipyard on Linux.
2. Create a directory to hold your configuration files. For this quickstart
guide, create a directory named `config`.
3. Copy the sample configuration files from the Deep Learning framework recipe
of your choice to the `config` directory:
  * [CNTK-CPU-OpenMPI](../recipes/CNTK-CPU-OpenMPI/config/singlenode/)
  * [Caffe-CPU](../recipes/Caffe-CPU/config/)
  * [Keras+Theano-CPU](../recipes/Keras+Theano-CPU/config/)
  * [MXNet-CPU](../recipes/MXNet-CPU/config/singlenode/)
  * [TensorFlow-CPU](../recipes/TensorFlow-CPU/config/)
  * [Torch-CPU](../recipes/Torch-CPU/config/)
4. Edit the `config/credentials.json` file and populate it with your Azure
Batch and Azure Storage credentials. If you do not have an Azure Batch account,
you can create one via the
[Azure Portal](https://azure.microsoft.com/en-us/documentation/articles/batch-account-create-portal/),
[Azure CLI](https://azure.microsoft.com/en-us/documentation/articles/xplat-cli-install/), or
[Azure PowerShell](https://azure.microsoft.com/en-us/documentation/articles/batch-powershell-cmdlets-get-started/).
You can create a standard general purpose
[Azure Storage account](https://docs.microsoft.com/en-us/azure/storage/storage-create-storage-account#create-a-storage-account)
using any of the methods as with the Azure Batch account.
5. Edit the `config/config.json` file and edit the following settings:
  * `storage_account_settings` to link to the storage account named in step 4.
6. In the main `batch-shipyard` directory (which should contain the
`shipyard` helper script if on Linux), run the following commands:
```shell
# The following assumes installation on Linux via the install.sh script. If
# on a different operating system, you can invoke by passing the script to
# the Python interpreter, e.g., python shipyard.py <command> <subcommand> ...
# Or if on Windows, e.g., C:\Python35\python.exe shipyard.py <command> <subcommand> ...

# create the compute pool
./shipyard pool add --configdir config

# ... wait for pool to allocate ...

# add the training job and tail the output
# if CNTK-CPU-OpenMPI or Caffe-CPU
./shipyard jobs add --configdir config --tail stderr.txt
# if Keras+Theano-CPU, MXNet-CPU, TensorFlow-CPU, or Torch-CPU
./shipyard jobs add --configdir config --tail stdout.txt
```
The `--tail` option of the `jobs add` command will stream the stderr or stdout
file to your local console which will provide you progress information about
your job.

Once you are finished interacting with your jobs, tasks and pool, you can
remove them with the following commands:
```shell
# ... done interacting with jobs/tasks/pool
./shipyard jobs del --configdir config --wait
./shipyard pool del --configdir config
```

## Commandline Usage Guide
[Batch Shipyard Usage](20-batch-shipyard-usage.md) contains explanations for
all of the actions available with commandline interface.

## In-Depth Configuration Guide
[Batch Shipyard Configuration](10-batch-shipyard-configuration.md) contains
explanations of all of the Batch Shipyard configuration options within the
config files.

## Graphical Interfaces
You can also use the [Azure Portal](https://portal.azure.com) or
[Batch Explorer](https://github.com/Azure/azure-batch-samples) for Windows to
view more properties of your Azure Batch accounts, pools, nodes, jobs and
tasks. You can view your Azure Storage accounts on Azure Portal or with
[Microsoft Azure Storage Explorer](http://storageexplorer.com/).
