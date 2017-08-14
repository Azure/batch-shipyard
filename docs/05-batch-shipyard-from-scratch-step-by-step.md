# Batch Shipyard From Scratch: Step-by-Step Guide
The following document aims to create a set of configuration files to
illustrate how to construct and submit a job executing on Batch Shipyard, from
scratch. We will perform a trivial task of counting the number of user
groups available in `/etc/group` with the `busybox` Docker image.

Please ensure that you have followed the
[Batch Shipyard installation guide](01-batch-shipyard-installation.md)
and have completed the installation (or pulled the Batch Shipyard Docker CLI
image) to your machine or are using Batch Shipyard on Azure Cloud Shell.

### Step 0: Azure Batch and Azure Storage Accounts
You will need to create an Azure Batch and a general purpose Azure Storage
account in order to use Batch Shipyard. If you do not have an Azure Batch
account, you can create one via the
[Azure Portal](https://azure.microsoft.com/en-us/documentation/articles/batch-account-create-portal/),
[Azure CLI 2.0](https://docs.microsoft.com/en-us/cli/azure/install-azure-cli), or
[Azure PowerShell](https://azure.microsoft.com/en-us/documentation/articles/batch-powershell-cmdlets-get-started/).
Note the account service URL and account key after creating your Batch account.

You can create a standard general purpose
[Azure Storage account](https://docs.microsoft.com/en-us/azure/storage/storage-create-storage-account#create-a-storage-account)
using any of the aforementioned methods similar to creating an Azure Batch
account. Note the storage account name and account key after creating your
Storage account.

### Step 1: Create a directory to hold your configuration files
Create a directory to hold your json configuration files. After you have
created a directory, change to that directory. For the purposes of this
sample, we will assume that we created a directory named `config` and have
changed to the directory.

### Step 2: Create a `credentials.json` file
You will need to create a credentials.json file with the Azure Batch
and Azure Storage accounts that you may have created in Step 0. Copy and
paste the following JSON into your `credentials.json` file.

```json
{
    "credentials": {
        "batch": {
            "account_key": "<batch account key>",
            "account_service_url": "<batch account service url>"
        },
        "storage": {
            "mystorageaccount": {
                "account": "<storage account name>",
                "account_key": "<storage account key>",
                "endpoint": "core.windows.net"
            }
        }
    }
}
```

Now, replace the text `<batch account key>` with the Batch account key and
the text `<batch account service url>` with the Batch account service url.
If you do now know these values, you can retrieve them from the
[Azure Portal](https://portal.azure.com/#blade/HubsExtension/Resources/resourceType/Microsoft.Batch%2FbatchAccounts)
under Batch Accounts.

Next, replace the text `<storage account name>` with the Storage account name
and `<storage account key>` with the Storage account key.
If you do now know these values, you can retrieve them from the
[Azure Portal](https://portal.azure.com/#blade/HubsExtension/Resources/resourceType/Microsoft.Storage%2FStorageAccounts)
under Storage Accounts.

What we have done here is created references to your Batch account
and Storage account for Batch Shipyard to use when provisioning pools and
saving metadata and resource files to Azure Storage as required.

### Step 3: Create a `config.json` file
The `config.json` specifies basic settings for which Storage account to
reference and Docker images to load. Copy and paste the following JSON into
your `config.json` file.

```json
{
    "batch_shipyard": {
        "storage_account_settings": "mystorageaccount"
    },
    "global_resources": {
        "docker_images": [
            "busybox"
        ]
    }
}
```

There is no text that needs to be replaced in this configuration. This
configuration is directing Batch Shipyard to write metadata and resource
files needed by Batch Shipyard to the storage account alias `mystorageaccount`
which you may have noticed was in the `credentials.json` file. The
`global_resources` property directs Batch Shipyard to load the listed
`docker_images` on to the compute pools.

### Step 4: Create a `jobs.json` file
The `jobs.json` file specifies the jobs to execute. For this sample
walkthrough, this is where we specify the command to count the number of
groups in the `/etc/group` file. Copy the following JSON into your `jobs.json`
file.

```json
{
    "job_specifications": [
        {
            "id": "myjob",
            "tasks": [
                {
                    "image": "busybox",
                    "command": "wc -l /etc/group"
                }
            ]
        }
    ]
}
```

Here, we assign a job ID `myjob` and this job has an associated task array.
A job can have multiple tasks assigned to it, however, for this sample we
only need to execute one command. First, we must reference the correct
Docker image to use when executing the job, which is `busybox`. Notice that
this name matches exactly to that of the image name specified under
`docker_images` in the `config.json` file. Finally, the `command` is set
to `wc -l /etc/group` which counts the number of lines found in the
`/etc/group` file.

### Step 5: Create a `pool.json` file
The `pool.json` is used to construct the computing resource needed for
executing the jobs found in the `jobs.json` file. Copy and paste the
following JSON into your `pool.json` file.

```json
{
    "pool_specification": {
        "id": "mypool",
        "vm_configuration": {
            "platform_image": {
                "publisher": "Canonical",
                "offer": "UbuntuServer",
                "sku": "16.04-LTS"
            }
        },
        "vm_size": "STANDARD_D1_V2",
        "vm_count": {
            "dedicated": 1,
            "low_priority": 0
        }
    }
}
```

Here, we want to create a pool with an ID `mypool` that is an Ubuntu 16.04
VM. We have also indicated that the Azure VM size should be `STANDARD_D1_V2`
with a count of `1` dedicated node. Note that Azure Batch supports
[`low_priority` nodes](https://docs.microsoft.com/en-us/azure/batch/batch-low-pri-vms)
as well.

### Step 6: Submit your work
Now that you have all 4 configuration files created, we can now submit our
work to Azure Batch via Batch Shipyard. For the following, we assume that
the current directory has the `shipyard` file to execute (as installed by
the helper installation scripts) and the `config` directory is at the same
level which contains all of the JSON configuration files created in prior
steps.

First, let's create the pool.

For Linux, Mac OS X, WSL:
```shell
SHIPYARD_CONFIGDIR=config ./shipyard pool add
```

For Windows:
```Batchfile
shipyard.cmd pool add --configdir config
```

After the pool has been created, then we simply add the jobs. Here we will
interactively tail the output of the task.

For Linux, Mac OS X, WSL:
```shell
SHIPYARD_CONFIGDIR=config ./shipyard jobs add --tail stdout.txt
```

For Windows:
```Batchfile
shipyard.cmd jobs add --configdir config --tail stdout.txt
```

Once you're done with your job, it's best to delete them so it does not
count against your active job quota.

For Linux, Mac OS X, WSL:
```shell
SHIPYARD_CONFIGDIR=config ./shipyard jobs del -y --wait
```

For Windows:
```Batchfile
shipyard.cmd jobs del --configdir config -y --wait
```

Finally, delete your pool so you don't incur charges for the virtual machine
while not in use.

For Linux, Mac OS X, WSL:
```shell
SHIPYARD_CONFIGDIR=config ./shipyard pool del -y
```

For Windows:
```Batchfile
shipyard.cmd pool del --configdir config -y
```

### Closing Words and Next Steps
This concludes the step-by-step guide in using the Batch Shipyard system.
Of course, your use case will invariably be more complicated than the trivial
sample shown here. Please refer to the following resources for more
information.

#### Batch Shipyard Guide Contents
Please see the [top-level README](README.md) for the table of contents for
all guides and documentation.

#### In-Depth Configuration Guide
[Batch Shipyard Configuration](10-batch-shipyard-configuration.md) contains
explanations of all of the Batch Shipyard configuration options within the
config files.

#### Commandline Usage Guide
[Batch Shipyard Usage](20-batch-shipyard-usage.md) contains explanations for
all of the actions available with commandline interface.

#### Recipes
Please visit the [recipes directory](../recipes) for more sample configuration
files for different types of jobs.
