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

If you installed for Python3, you can alternatively invoke the script
directly as:
```shell
./shipyard.py
```
If on Windows, you will need to invoke the Python interpreter and pass
the script as an argument. For example:
```
C:\Python35\python.exe shipyard.py
```
The `-h` or `--help` option will list the available options, which are
explained below.

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

## Commands
`shipyard` (and `shipyard.py`) script contains the following top-level
commands:
```
  cert     Certificate actions
  data     Data actions
  jobs     Jobs actions
  pool     Pool actions
  storage  Storage actions
```
* `cert` commands deal with certificates to be used with Azure Batch
* `data` commands deal with data ingress and egress from Azure
* `jobs` commands deal with Azure Batch jobs and tasks
* `pool` commands deal with Azure Batch pools
* `storage` commands deal with Batch Shipyard metadata on Azure Storage

## Certificate Command
The `cert` command has the following sub-commands:
```
  add     Add a certificate to a Batch account
  create  Create a certificate to use with a Batch...
  del     Add a certificate to a Batch account
  list    List all certificates in a Batch account
```
* `add` will add a certificate to the Batch account
* `create` will create a certificate locally for use with the Batch account.
You must edit your `config.json` to incorporate the generated certificate and
then invoked the `cert add` command. Please see the
[credential encryption](75-batch-shipyard-credential-encryption.md) guide for more information.
* `del` will delete a certificate from the Batch account
* `list` will list certificates in the Batch account

## Data Command
The `data` command has the following sub-commands:
```
  getfile      Retrieve file(s) from a job/task
  getfilenode  Retrieve file(s) from a compute node
  ingress      Ingress data into Azure
  listfiles    List files for all tasks in jobs
  stream       Stream a text file to the local console
```
* `getfile` will retrieve a file with job, task, filename semantics
  * `-all --filespec <jobid>,<taskid>,<include pattern>` can be given to
    download all files for the job and task with an optional include pattern
  * `--filespec <jobid>,<taskid>,<filename>` can be given to download one
    specific file from the job and task. If `<taskid>` is set to
    `@FIRSTRUNNING`, then the first running task within the job of `<jobid>`
    will be used to locate the `<filename>`.
* `getfilenode` will retrieve a file with node id and filename semantics
  * `-all --filespec <nodeid>,<include pattern>` can be given to download
    all files from the compute node with the optional include pattern
  * `--filespec <nodeid>,<filename>` can be given to download one
    specific file from compute node
* `ingress` will ingress data as specified in configuration files
* `listfiles` will list files for all tasks in jobs
* `stream` will stream a file as text (UTF-8 decoded) to the local console
  * `--filespec <jobid>,<taskid>,<filename>` can be given to stream a
    specific file. If `<taskid>` is set to `@FIRSTRUNNING`, then the first
    running task within the job of `<jobid>` will be used to locate the
    `<filename>`.

## Jobs Command
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
* `cmi` will cleanup any stale multi-instance tasks and jobs. Note that this
sub-command is typically not required if `multi_instance_auto_complete` is
set to `true` in the job specification for the job.
  * `--delete` will delete any stale cleanup jobs
* `del` will delete jobs specified in the jobs configuration file
  * `--all` will delete all jobs found in the Batch account
  * `--jobid` force termination scope to just this job id
  * `--wait` will wait for deletion to complete
* `deltasks` will delete tasks within jobs specified in the jobs
configuration file. Active or running tasks will be terminated first.
  * `--jobid` force deletion scope to just this job id
  * `--taskid` force deletion scope to just this task id
  * `--wait` will wait for deletion to complete
* `list` will list all jobs in the Batch account
* `listtasks` will list tasks from jobs specified in the jobs configuration
file
* `term` will terminate jobs found in the jobs configuration file
  * `--all` will terminate all jobs found in the Batch account
  * `--jobid` force termination scope to just this job id
  * `--wait` will wait for termination to complete
* `termtasks` will terminate tasks within jobs specified in the jobs
configuration file. Termination of running tasks requires a valid SSH
user.
  * `--jobid` force termination scope to just this job id
  * `--taskid` force termination scope to just this task id
  * `--wait` will wait for termination to complete

## Pool Command
The `pool` command has the following sub-commands:
```
  add        Add a pool to the Batch account
  asu        Add an SSH user to all nodes in pool
  del        Delete a pool from the Batch account
  delnode    Delete a node from a pool
  dsu        Delete an SSH user from all nodes in pool
  grls       Get remote login settings for all nodes in...
  list       List all pools in the Batch account
  listnodes  List nodes in pool
  resize     Resize a pool
```
* `add` will add the pool defined in the pool configuration file to the
Batch account
* `asu` will add the SSH user defined in the pool configuration file to
all nodes in the specified pool
* `del` will delete the pool defined in the pool configuration file from
the Batch account along with associated metadata in Azure Storage used by
Batch Shipyard
  * `--wait` will wait for deletion to complete
* `delnode` will delete the specified node from the pool
* `dsu` will delete the SSH user defined in the pool configuration file
from all nodes in the specified pool
* `grls` will retrieve all of the remote login settings for every node
in the specified pool
* `list` will list all pools in the Batch account
* `listnodes` will list all nodes in the specified pool
* `resize` will resize the pool to the `vm_count` specified in the pool
configuration file

## Storage Command
The `storage` command has the following sub-commands:
```
  clear  Clear Azure Storage containers used by Batch...
  del    Delete Azure Storage containers used by Batch...
```
* `clear` will clear the Azure Storage containers used by Batch Shipyard
for metadata purposes
* `del` will delete the Azure Storage containers used by Batch Shipyard
for metadata purposes

## Shared Options
There are a set of shared options which are used for every sub-command.
These options must be specified after the command and sub-command. These are:
```
  -y, --yes           Assume yes for all confirmation prompts
  -v, --verbose       Verbose output
  --configdir TEXT    Configuration directory where all configuration files
                      can be found. Each json config file must be named
                      exactly the same as the regular switch option, e.g.,
                      pool.json for --pool. Individually specified config
                      options take precedence over this option.
  --credentials TEXT  Credentials json config file
  --config TEXT       Global json config file
  --pool TEXT         Pool json config file
  --jobs TEXT         Jobs json config file
```
* `--configdir path` can be used instead of the individual config switches
below if all configuration json files are in one directory and named after
their switch. For example, if you have a directory named `config` and under
that directory you have the files `credentials.json`, `config.json`,
`pool.json` and `jobs.json`, then you can use this argument instead of the
following:
  * `--credentials path/to/credentials.json` is required for all actions.
  * `--config path/to/config.json` is required for all actions.
  * `--pool path/to/pool.json` is required for most actions.
  * `--jobs path/to/jobs.json` is required for job-related actions.
* `-v` or `--verbose` is for verbose output
* `-y` or `--yes` is to assume yes for all confirmation prompts

## Example Invocations
```shell
shipyard pool add --credentials credentials.json --config config.json --pool pool.json

# ... or if all config files are in the current working directory named as above ...

shipyard pool add --configdir .
```
The above invocation will add the pool specified to the Batch account. Notice
that the options and shared options are given after the command and
sub-command and not before.

```shell
shipyard jobs add --configdir .
```
The above invocation will add the jobs specified in the jobs.json file to
the designated pool.

```shell
shipyard data stream --configdir . --filespec job1,dockertask-000,stdout.txt
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
docker run --rm -it -v /home/user/batch-shipyard-configs:/configs alfpark/batch-shipyard:cli-latest <command> <subcommand> --configdir /configs <options...>
```

Notice that we specified the `--configdir` argument to match the container
path of the volume mount.

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
