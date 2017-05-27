# Batch Shipyard Usage
This page contains in-depth details on how to use the Batch Shipyard tool.
Please see the [Batch Shipyard Docker Image CLI](#docker-cli) section for
information regarding how to use the `alfpark/batch-shipyard:cli-latest`
Docker image if not invoking the Python script directly.

## Batch Shipyard Invocation
If you installed Batch Shipyard using the `install.sh` script, then
you can invoke as:
```shell
# Change directory to batch-shipyard installed directory
./shipyard
```
You can also invoke `shipyard` from any directory if given the full path
to the script.

If on Windows or Mac, you will need to invoke the Python interpreter and pass
the script as an argument. For example:
```
C:\Python36\python.exe shipyard.py
```
The `-h` or `--help` option will list the available options, which are
explained below.

## Note about interoperability with Azure Tooling and Azure Batch APIs
Nearly all REST calls or commands that are issued against the normal Azure
Batch APIs and tooling such as the Azure Portal or Azure CLI will work fine
against Azure Batch Shipyard created resources. However, there are some
notable exceptions:

1. All pools must be created with Batch Shipyard if you intend to use any
Batch Shipyard functionality.
2. Please note all of the
[current limitations for other actions](99-current-limitations.md).
3. Batch Shipyard pools that are deleted outside of Batch Shipyard will not
have their associated metadata (in Azure Storage) cleaned up. Please use
the `pool del` functionality. You can use the `storage` command to clean up
orphaned data if you accidentially deleted Batch Shipyard pools outside of
Batch Shipyard.

## Commands and Sub-commands
`shipyard` (and `shipyard.py`) is invoked with a command and a sub-command as
positional arguments, i.e.:
```shell
shipyard <command> <subcommand> <options>
```
For instance:
```shell
shipyard pool add --configdir config
```
Would create a pool on the Batch account as specified in the config files
found in the `config` directory. Please note that `<options>` must be
specified after the command and subcommand.

You can issue the `-h` or `--help` option at every level to view all
available options for that level and additional help text. For example:
```shell
shipyard -h
shipyard pool -h
shipyard pool add -h
```

## Shared Options
There are a set of shared options which are used between most sub-commands.
These options must be specified after the command and sub-command. These are:
```
  -y, --yes                       Assume yes for all confirmation prompts
  --show-config                   Show configuration
  -v, --verbose                   Verbose output
  --configdir TEXT                Configuration directory where all
                                  configuration files can be found. Each json
                                  config file must be named exactly the same
                                  as the regular switch option, e.g.,
                                  pool.json for --pool. Individually specified
                                  config options take precedence over this
                                  option.
  --credentials TEXT              Credentials json config file
  --config TEXT                   Global json config file
  --fs TEXT                       Filesystem json config file
  --pool TEXT                     Pool json config file
  --jobs TEXT                     Jobs json config file
  --subscription-id TEXT          Azure Subscription ID
  --keyvault-uri TEXT             Azure KeyVault URI
  --keyvault-credentials-secret-id TEXT
                                  Azure KeyVault credentials secret id
  --aad-endpoint TEXT             Azure Active Directory endpoint
  --aad-directory-id TEXT         Azure Active Directory directory (tenant) id
  --aad-application-id TEXT       Azure Active Directory application (client)
                                  id
  --aad-auth-key TEXT             Azure Active Directory authentication key
  --aad-user TEXT                 Azure Active Directory user
  --aad-password TEXT             Azure Active Directory password
  --aad-cert-private-key TEXT     Azure Active Directory private key for X.509
                                  certificate
  --aad-cert-thumbprint TEXT      Azure Active Directory certificate SHA1
                                  thumbprint
```
* `-y` or `--yes` is to assume yes for all confirmation prompts
* `--show-config` will output the merged configuration prior to execution
* `-v` or `--verbose` is for verbose output
* `--configdir path` can be used instead of the individual config switches
below if all configuration json files are in one directory and named after
their switch. For example, if you have a directory named `config` and under
that directory you have the files `credentials.json`, `config.json`,
`pool.json` and `jobs.json`, then you can use this argument instead of the
following:
  * `--credentials path/to/credentials.json` is required for all actions
    except for a select few `keyvault` commands.
  * `--config path/to/config.json` is required for all actions.
  * `--pool path/to/pool.json` is required for most actions.
  * `--jobs path/to/jobs.json` is required for job-related actions.
  * `--fs path/to/fs.json` is required for fs-related actions and some pool
    actions.
* `--subscription-id` is the Azure Subscription Id associated with the
Batch account or Remote file system resources. This is only required for
creating pools with a virtual network specification or with `fs` commands.
* `--keyvault-uri` is required for all `keyvault` commands.
* `--keyvault-credentials-secret-id` is required if utilizing a credentials
json stored in Azure KeyVault
* `--aad-endpoint` is the Active Directory endpoint for the resource. Note
that this can cause conflicts for actions that require multiple endpoints
for different resources. It is better to specify endpoints explicitly in
the credential file.
* `--aad-directory-id` is the Active Directory Directory Id (or Tenant Id)
* `--aad-application-id` is the Active Directory Application Id (or Client Id)
* `--aad-auth-key` is the authentication key for the application (or client)
* `--aad-user` is the Azure Active Directory user
* `--aad-password` is the Azure Active Directory password for the user
* `--aad-cert-private-key` is the Azure Active Directory Service Principal
RSA private key corresponding to the X.509 certificate for certificate-based
auth
* `--aad-cert-thumbprint` is the X.509 certificate thumbprint for Azure Active
Directory certificate-based auth

Note that only one of Active Directory Service Principal or User/Password can
be specified at once, i.e., `--aad-auth-key`, `--aad-password`, and
`--aad-cert-private-key` are mutually exclusive.

Note that the following options can be specified as environment variables
instead:
* `SHIPYARD_CONFIGDIR` in lieu of `--configdir`
* `SHIPYARD_CREDENTIALS_JSON` in lieu of `--credentials`
* `SHIPYARD_CONFIG_JSON` in lieu of `--config`
* `SHIPYARD_POOL_JSON` in lieu of `--pool`
* `SHIPYARD_JOBS_JSON` in lieu of `--jobs`
* `SHIPYARD_FS_JSON` in lieu of `--fs`
* `SHIPYARD_SUBSCRIPTION_ID` in lieu of `--subscription-id`
* `SHIPYARD_KEYVAULT_URI` in lieu of `--keyvault-uri`
* `SHIPYARD_KEYVAULT_CREDENTIALS_SECRET_ID` in lieu of
`--keyvault-credentials-secret-id`
* `SHIPYARD_AAD_ENDPOINT` in lieu of `--aad-endpoint`
* `SHIPYARD_AAD_DIRECTORY_ID` in lieu of `--aad-directory-id`
* `SHIPYARD_AAD_APPLICATION_ID` in lieu of `--aad-application-id`
* `SHIPYARD_AAD_AUTH_KEY` in lieu of `--aad-auth-key`
* `SHIPYARD_AAD_USER` in lieu of `--aad-user`
* `SHIPYARD_AAD_PASSWORD` in lieu of `--aad-password`
* `SHIPYARD_AAD_CERT_PRIVATE_KEY` in lieu of `--aad-cert-private-key`
* `SHIPYARD_AAD_CERT_THUMBPRINT` in lieu of `--aad-cert-thumbprint`

## Commands
`shipyard` (and `shipyard.py`) script contains the following top-level
commands:
```
  cert      Certificate actions
  data      Data actions
  fs        Filesystem in Azure actions
  jobs      Jobs actions
  keyvault  KeyVault actions
  misc      Miscellaneous actions
  pool      Pool actions
  storage   Storage actions
```
* `cert` commands deal with certificates to be used with Azure Batch
* `data` commands deal with data ingress and egress from Azure
* `fs` commands deal with Batch Shipyard provisioned remote filesystems in
Azure
* `jobs` commands deal with Azure Batch jobs and tasks
* `keyvault` commands deal with Azure KeyVault secrets for use with Batch
Shipyard
* `misc` commands are miscellaneous commands that don't fall into other
categories
* `pool` commands deal with Azure Batch pools
* `storage` commands deal with Batch Shipyard metadata on Azure Storage

## `cert` Command
The `cert` command has the following sub-commands:
```
  add     Add a certificate to a Batch account
  create  Create a certificate to use with a Batch...
  del     Deletes a certificate from the Batch account
  list    List all certificates in a Batch account
```
* `add` will add a certificate to the Batch account
* `create` will create a certificate locally for use with the Batch account.
You must edit your `config.json` to incorporate the generated certificate and
then invoked the `cert add` command. Please see the
[credential encryption](75-batch-shipyard-credential-encryption.md) guide for more information.
* `del` will delete a certificate from the Batch account
* `list` will list certificates in the Batch account

## `data` Command
The `data` command has the following sub-commands:
```
  getfile      Retrieve file(s) from a job/task
  getfilenode  Retrieve file(s) from a compute node
  ingress      Ingress data into Azure
  listfiles    List files for tasks in jobs
  stream       Stream a text file to the local console
```
* `getfile` will retrieve a file with job, task, filename semantics
  * `--all --filespec <jobid>,<taskid>,<include pattern>` can be given to
    download all files for the job and task with an optional include pattern
  * `--filespec <jobid>,<taskid>,<filename>` can be given to download one
    specific file from the job and task. If `<taskid>` is set to
    `@FIRSTRUNNING`, then the first running task within the job of `<jobid>`
    will be used to locate the `<filename>`.
* `getfilenode` will retrieve a file with node id and filename semantics
  * `--all --filespec <nodeid>,<include pattern>` can be given to download
    all files from the compute node with the optional include pattern
  * `--filespec <nodeid>,<filename>` can be given to download one
    specific file from compute node
* `ingress` will ingress data as specified in configuration files
  * `--to-fs <STORAGE_CLUSTER_ID>` transfers data as specified in
    configuration files to the specified remote file system storage cluster
    instead of Azure Storage
* `listfiles` will list files for all tasks in jobs
  * `--jobid` force scope to just this job id
  * `--taskid` force scope to just this task id
* `stream` will stream a file as text (UTF-8 decoded) to the local console
or binary if streamed to disk
  * `--disk` will write the streamed data as binary to disk instead of output
    to local console
  * `--filespec <jobid>,<taskid>,<filename>` can be given to stream a
    specific file. If `<taskid>` is set to `@FIRSTRUNNING`, then the first
    running task within the job of `<jobid>` will be used to locate the
    `<filename>`.

## `fs` Command
The `fs` command has the following sub-commands which work on two different
parts of a remote filesystem:
```
  cluster  Filesystem storage cluster in Azure actions
  disks    Managed disk actions
```

### `fs cluster` Command
`fs cluster` command has the following sub-commands:
```
  add      Create a filesystem storage cluster in Azure
  del      Delete a filesystem storage cluster in Azure
  expand   Expand a filesystem storage cluster in Azure
  resize   Resize a filesystem storage cluster in Azure.
  ssh      Interactively login via SSH to a filesystem...
  start    Starts a previously suspended filesystem...
  status   Query status of a filesystem storage cluster...
  suspend  Suspend a filesystem storage cluster in Azure
```
As the `fs.json` configuration file can contain multiple storage cluster
definitions, all `fs cluster` commands require the argument
`STORAGE_CLUSTER_ID` after any option below is specified targeting the
storage cluster to perform actions against.

* `add` will create a remote fs cluster as defined in the fs config file
* `del` will delete a remote fs cluster as defined in the fs config file
  * `--delete-resource-group` will delete the entire resource group that
    contains the server. Please take care when using this option as any
    resource in the resoure group is deleted which may be other resources
    that are not Batch Shipyard related.
  * `--delete-data-disks` will delete attached data disks
  * `--delete-virtual-network` will delete the virtual network and all of
    its subnets
  * `--generate-from-prefix` will attempt to generate all resource names
    using conventions used. This is helpful when there was an issue with
    cluster deletion and the original virtual machine(s) resources can no
    longer by enumerated. Note that OS disks and data disks cannot be
    deleted with this option. Please use `fs disks del` to delete disks
    that may have been used in the storage cluster.
  * `--no-wait` does not wait for deletion completion. It is not recommended
    to use this parameter.
* `expand` expands the number of disks used by the underlying filesystems on
the file server.
  * `--no-rebalance` rebalances the data and metadata among the disks for
    better data spread and performance after the disk is added to the array.
* `resize` resizes the storage cluster with additional virtual machines as
specified in the configuration. This is an experimental feature.
* `ssh` will interactively log into a virtual machine in the storage cluster.
If neither `--cardinal` or `--hostname` are specified, `--cardinal 0` is
assumed.
  * `COMMAND` is an optional argument to specify the command to run. If your
    command has switches, preface `COMMAND` with double dash as per POSIX
    convention, e.g., `fs cluster ssh mycluster -- df -h`.
  * `--cardinal` is the zero-based cardinal number of the virtual machine in
    the storage cluster to connect to.
  * `--hostname` is the hostname of the virtual machine in the storage cluster
    to connect to
  * `--tty` allocates a pseudo-terminal
* `start` will start a previously suspended storage cluster
  * `--no-wait` does not wait for the restart to complete. It is not
    recommended to use this parameter.
* `status` displays the status of the storage cluster
  * `--detail` reports in-depth details about each virtual machine in the
    storage cluster
  * `--hosts` will output the public IP to hosts mapping for mounting a
    `glusterfs` based remote filesystem locally. `glusterfs` must be
    allowed in the network security rules for this to work properly.
* `suspend` suspends a storage cluster
  * `--no-wait` does not wait for the suspension to complete. It is not
    recommended to use this parameter.

### `fs disks` Command
`fs disks` command has the following sub-commands:
```
  add   Create managed disks in Azure
  del   Delete managed disks in Azure
  list  List managed disks in resource group
```
* `add` creates managed disks as specified in the fs config file
* `del` deletes managed disks as specified in the fs config file
  * `--all` deletes all managed disks found in a specified resource group
  * `--name` deletes a specific named disk in a resource group
  * `--no-wait` does not wait for disk deletion to complete. It is not
    recommended to use this parameter.
  * `--resource-group` deletes one or more managed disks in this resource group
* `list` lists managed disks found in a resource group
  * `--resource-group` lists disks in this resource group only
  * `--restrict-scope` lists disks only if found in the fs config file

## `jobs` Command
The `jobs` command has the following sub-commands:
```
  add        Add jobs
  cmi        Cleanup multi-instance jobs
  del        Delete jobs
  deltasks   Delete specified tasks in jobs
  list       List jobs
  listtasks  List tasks within jobs
  term       Terminate jobs
  termtasks  Terminate specified tasks in jobs
```
* `add` will add all jobs and tasks defined in the jobs configuration file
to the Batch pool
  * `--recreate` will recreate any completed jobs with the same id
  * `--tail` will tail the specified file of the last job and task added
    with this command invocation
* `cmi` will cleanup any stale multi-instance tasks and jobs. Note that this
sub-command is typically not required if `multi_instance_auto_complete` is
set to `true` in the job specification for the job.
  * `--delete` will delete any stale cleanup jobs
* `del` will delete jobs specified in the jobs configuration file
  * `--all` will delete all jobs found in the Batch account
  * `--jobid` force deletion scope to just this job id
  * `--termtasks` will manually terminate tasks prior to deletion. Termination
    of running tasks requires a valid SSH user.
  * `--wait` will wait for deletion to complete
* `deltasks` will delete tasks within jobs specified in the jobs
configuration file. Active or running tasks will be terminated first.
  * `--jobid` force deletion scope to just this job id
  * `--taskid` force deletion scope to just this task id
  * `--wait` will wait for deletion to complete
* `list` will list all jobs in the Batch account
* `listtasks` will list tasks from jobs specified in the jobs configuration
file
  * `--jobid` force scope to just this job id
  * `--poll-until-tasks-complete` will poll until all tasks have completed
* `term` will terminate jobs found in the jobs configuration file
  * `--all` will terminate all jobs found in the Batch account
  * `--jobid` force termination scope to just this job id
  * `--termtasks` will manually terminate tasks prior to termination.
    Termination of running tasks requires a valid SSH user.
  * `--wait` will wait for termination to complete
* `termtasks` will terminate tasks within jobs specified in the jobs
configuration file. Termination of running tasks requires a valid SSH
user.
  * `--force` force send docker kill signal regardless of task state
  * `--jobid` force termination scope to just this job id
  * `--taskid` force termination scope to just this task id
  * `--wait` will wait for termination to complete

## `keyvault` Command
The `keyvault` command has the following sub-commands:
```
  add   Add a credentials json as a secret to Azure...
  del   Delete a secret from Azure KeyVault
  list  List secret ids and metadata in an Azure...
```
The following subcommands require `--keyvault-*` and `--aad-*` options in
order to work. Alternatively, you can specify these in the `credentials.json`
file, but these options are mutually exclusive of other properties.
Please refer to the
[Azure KeyVault and Batch Shipyard guide](74-batch-shipyard-azure-keyvault.md)
for more information.
* `add` will add the specified credentials json as a secret to an Azure
KeyVault. A valid credentials json must be specified as an option.
  * `NAME` argument is required which is the name of the secret associated
    with the credentials json to store in the KeyVault
* `del` will delete a secret from the Azure KeyVault
  * `NAME` argument is required which is the name of the secret to delete
    from the KeyVault
* `list` will list all secret ids and metadata in an Azure KeyVault

## `misc` Command
The `misc` command has the following sub-commands:
```
  tensorboard  Create a tunnel to a Tensorboard instance for...
```
* `tensorboard` will create a tunnel to the compute node that is running
or has run the specified task
  * `--jobid` specifies the job id to use. If this is not specified, the first
    and only jobspec is used from jobs.json.
  * `--taskid` specifies the task id to use. If this is not specified, the
    last run or running task for the job is used.
  * `--logdir` specifies the TensorFlow logs directory generated by summary
    operations
  * `--image` specifies an alternate TensorFlow image to use for Tensorboard.
    The `tensorboard.py` file must be in the expected location in the Docker
    image as stock TensorFlow images. If not specified, Batch Shipyard will
    attempt to find a suitable TensorFlow image from Docker images in the
    global resource list or will acquire one on demand for this command.

## `pool` Command
The `pool` command has the following sub-commands:
```
  add         Add a pool to the Batch account
  asu         Add an SSH user to all nodes in pool
  del         Delete a pool from the Batch account
  delnode     Delete a node from a pool
  dsu         Delete an SSH user from all nodes in pool
  grls        Get remote login settings for all nodes in...
  list        List all pools in the Batch account
  listimages  List Docker images in the pool
  listnodes   List nodes in pool
  listskus    List available VM configurations available to...
  rebootnode  Reboot a node or nodes in a pool
  resize      Resize a pool
  ssh         Interactively login via SSH to a node in the...
  udi         Update Docker images in a pool
```
* `add` will add the pool defined in the pool configuration file to the
Batch account
* `asu` will add the SSH user defined in the pool configuration file to
all nodes in the specified pool
* `del` will delete the pool defined in the pool configuration file from
the Batch account along with associated metadata in Azure Storage used by
Batch Shipyard. It is recommended to use this command instead of deleting
a pool directly from the Azure Portal, Batch Labs, or other tools as
this action can conveniently remove all associated Batch Shipyard metadata on
Azure Storage.
  * `--poolid` will delete the specified pool instead of the pool from the
    pool configuration file
  * `--wait` will wait for deletion to complete
* `delnode` will delete the specified node from the pool
* `dsu` will delete the SSH user defined in the pool configuration file
from all nodes in the specified pool
* `grls` will retrieve all of the remote login settings for every node
in the specified pool
* `list` will list all pools in the Batch account
* `listimages` will query the nodes in the pool for Docker images. Common
and mismatched images will be listed. Requires a provisioned SSH user and
private key.
* `listnodes` will list all nodes in the specified pool
* `rebootnode` will reboot a specified node in the pool
  * `--all-start-task-failed` will reboot all nodes in the start task
    failed state
  * `--nodeid` is the node id to reboot
* `resize` will resize the pool to the `vm_count` specified in the pool
configuration file
  * `--wait` will wait for resize to complete
* `ssh` will interactively log into a compute node via SSH. If neither
`--cardinal` or `--nodeid` are specified, `--cardinal 0` is assumed.
  * `COMMAND` is an optional argument to specify the command to run. If your
    command has switches, preface `COMMAND` with double dash as per POSIX
    convention, e.g., `pool ssh -- sudo docker ps -a`.
  * `--cardinal` is the zero-based cardinal number of the compute node in
    the pool to connect to as listed by `grls`
  * `--nodeid` is the node id to connect to in the pool
  * `--tty` allocates a pseudo-terminal
* `udi` will update Docker images on all compute nodes of the pool. This
command requires a valid SSH user.
  * `--image` will restrict the update to just the image or image:tag
  * `--digest` will restrict the update to just the image or image:tag and
    a specific digest

## `storage` Command
The `storage` command has the following sub-commands:
```
  clear  Clear Azure Storage containers used by Batch...
  del    Delete Azure Storage containers used by Batch...
```
* `clear` will clear the Azure Storage containers used by Batch Shipyard
for metadata purposes
* `del` will delete the Azure Storage containers used by Batch Shipyard
for metadata purposes

## Example Invocations
```shell
shipyard pool add --credentials credentials.json --config config.json --pool pool.json

# ... or if all config files are in the current working directory named as above ...

shipyard pool add --configdir .

# ... or use environment variables instead

SHIPYARD_CONFIGDIR=. shipyard pool add
```
The above invocation will add the pool specified to the Batch account. Notice
that the options and shared options are given after the command and
sub-command and not before.

```shell
shipyard jobs add --configdir .

# ... or use environment variables instead

SHIPYARD_CONFIGDIR=. shipyard jobs add
```
The above invocation will add the jobs specified in the jobs.json file to
the designated pool.

```shell
shipyard data stream --configdir . --filespec job1,dockertask-000,stdout.txt

# ... or use environment variables instead

SHIPYARD_CONFIGDIR=. shipyard data stream --filespec job1,dockertask-000,stdout.txt
```
The above invocation will stream the stdout.txt file from the job `job1` and
task `task1` from a live compute node. Because all portions of the
`--filespec` option are specified, the tool will not prompt for any input.

## <a name="docker-cli"></a>Batch Shipyard Docker Image CLI Invocation
If using the [alfpark/batch-shipyard:cli-latest](https://hub.docker.com/r/alfpark/batch-shipyard)
Docker image, then you would invoke the tool as:

```shell
docker run --rm -it alfpark/batch-shipyard:cli-latest <command> <subcommand> <options...>
```

where `<command> <subcommand>` is the command and subcommand as described
above and `<options...>` are any additional options to pass to the
`<subcommand>`.

Invariably, you will need to pass config files to the tool which reside
on the host and not in the container by default. Please use the `-v` volume
mount option with `docker run` to mount host directories inside the container.
For example, if your Batch Shipyard configs are stored in the host path
`/home/user/batch-shipyard-configs` you could modify the docker run command
as:

```shell
docker run --rm -it -v /home/user/batch-shipyard-configs:/configs -e SHIPYARD_CONFIGDIR=/configs alfpark/batch-shipyard:cli-latest <command> <subcommand> <options...>
```

Notice that we specified a Docker environment variable via
`-e SHIPYARD_CONFIGDIR` to match the container path of the volume mount.

Additionally, if you wish to ingress data from locally accessible file
systems using Batch Shipyard, then you will need to map additional volume
mounts as appropriate from the host to the container.

Batch Shipyard may generate files with some actions, such as adding a SSH
user or creating a pool with an SSH user. In this case, you will need
to create a volume mount with the `-v` option and also ensure that the
pool specification `ssh` object has a `generated_file_export_path` property
set to the volume mount path. This will ensure that generated files will be
written to the host and persisted after the docker container exits. Otherwise,
the generated files will only reside within the docker container and
will not be available for use on the host (e.g., SSH into compute node with
generated RSA private key or use the generated SSH docker tunnel script).

## Remote Filesystem Support
For more information regarding remote filesystems and Batch Shipyard,
please see [this page](65-batch-shipyard-remote-fs.md).

## Data Movement
For more information regarding data movement with respect to Batch Shipyard,
please see [this page](70-batch-shipyard-data-movement.md).

## Multi-Instance Tasks
For more information regarding Multi-Instance Tasks and/or MPI jobs using
Batch Shipyard, please see [this page](80-batch-shipyard-multi-instance-tasks.md).

## Current Limitations
Please see [this page](99-current-limitations.md) for current limitations.

## Explore Recipes and Samples
Visit the [recipes directory](../recipes) for different sample Docker
workloads using Azure Batch and Batch Shipyard.

## Need Help?
[Open an issue](https://github.com/Azure/batch-shipyard/issues) on the GitHub
project page.
