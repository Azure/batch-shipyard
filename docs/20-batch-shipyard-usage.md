# Batch Shipyard Usage
This page contains in-depth details on how to use the Batch Shipyard tool.
Please see the [Batch Shipyard Docker Image CLI](#docker-cli) section for
information regarding how to use the `alfpark/batch-shipyard:cli-latest`
image if not invoking the Python script directly.

## shipyard.py Invocation
If you are invoking the script with a python3 interpreter, you can simply
run the script as:

```
./shipyard.py
```

With python2 invoke as:
```
python shipyard.py
```

The `-h` option will list the available options, which are explained below.

## Options
The script requires configuration json files described by the
[previous doc](10-batch-shipyard-configuration.md) to be passed in as
arguments.

Explanation of arguments:
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
* `--filespec jobid:taskid:filename` is to specify the file location to
stream or retrieve for the actions `streamfile` or `gettaskfile` respectively.
For `gettaskallfiles`, the argument becomes `jobid:taskid:include` where
`include` is a filter like `*.txt` which would only download files ending in
`.txt`. Note that you must prevent your shell from interpreting wildcards,
thus it is recommended to quote the argument when including such a filter.
If `taskid` is `@FIRSTRUNNING` then the first running task in the job is
retrieved. If the `filespec` argument is not supplied, the script will prompt
for input.
* `--nodeid <compute node id>` is only required for the `delnode` and
`getnodefile` action.
* `-v` is for verbose output
* `-y` is to assume yes for all confirmation prompts

The required positional argument to the script is `action`. Here are a list
of actions and their intended effect:
* `addpool`: creates a pool as specified in the configuration files.
* `addjobs`: adds jobs as specified in the jobs configuration file.
* `addsshuser`: adds an SSH tunnel user as specified in the pool configuration
file. This action is automatically invoked during `addpool` if enabled in the
pool configuration file.
* `cleanmijobs`: perform clean up action on multi-instance Docker tasks.
Because the multi-instance coordination command (i.e, the daemonized
container via `docker run`) is left running even after the multi-instance
task completes (i.e., application command `docker exec`), subsequent tasks
on the same compute nodes may fail on the coordination command due to
resources in use. This will clean up any multi-instance tasks detected within
jobs specified in the jobs configuration file. Note that you can enable
job auto-completion for these tasks via configuration instead of manually
cleaning up these types of jobs.
* `termjobs`: terminate jobs as specified in the jobs configuration file.
* `deljobs`: delete jobs as specified in the jobs configuration file.
* `deljobswait`: delete jobs and wait for successful deletion as specified
in the jobs configuration file.
* `delcleanmijobs`: delete jobs used to clean up multi-instance jobs.
* `delalljobs`: delete all jobs under the Batch Account.
* `delpool`: delete pool as specified in the pool configuration file.
* `grls`: get remote login settings as specified in the pool configuration
file.
* `streamfile`: stream a file from a live compute node.
* `gettaskfile`: retrieve a file with job id/task id from a live compute node.
* `gettaskallfiles`: retrieve all files with job id/task id from a live
compute node. `--filespec` can be used with this action as described above.
* `getnodefile`: retrieve a file with pool id/node id from a live compute node.
* `ingressdata`: ingress data as specified in the `files` property of the
global configuration file.
* `listjobs`: list all jobs under the Batch account.
* `listtasks`: list tasks under jobs specified in the jobs configuraiton file.
* `createcert`: create certificate and public key required for credential
encryption.
* `addcert`: add PFX certificate to the Batch account.
* `delcert`: delete a PFX certificate from a Batch account. Any pool or task
referencing the certificate must be deleted first before issuing this action.
* `clearstorage`: clear storage containers as specified in the configuration
files.
* `delstorage`: delete storage containers as specified in the configuration
files.

## Example Invocations
```shell
python shipyard.py --credentials credentials.json --config config.json --pool pool.json addpool

# ... or if all config files are in the current working directory named as above ...

python shipyard.py --configdir . addpool
```
The above invocation will add the pool specified to the Batch account.

```shell
python shipyard.py --credentials credentials.json --config config.json --pool pool.json --jobs jobs.json addjobs

# ... or if all config files are in the current working directory named as above ...

python shipyard.py --configdir . addjobs
```
The above invocation will add the jobs specified to the designated pool.

```shell
python shipyard.py --credentials credentials.json --config config.json --pool pool.json --jobs jobs.json streamfile

# ... or if all config files are in the current working directory named as above ...

python shipyard.py --configdir . streamfile
```
The above invocation will stream a file from a live compute node with
interactive prompts from the script.

## <a name="docker-cli"></a>Batch Shipyard Docker Image CLI Invocation
If using the [alfpark/batch-shipyard:cli-latest](https://hub.docker.com/r/alfpark/batch-shipyard)
Docker image, then you would invoke the tool as:

```shell
docker run --rm -it alfpark/batch-shipyard:cli-latest <action> <options...>
```

where `<action>` is the action as described above and `<options...>` are any
additional options to pass to the `<action>`.

Invariably, you will need to pass config files to the tool which reside
on the host and not in the container by default. Please use the `-v` volume
mount option to mount host directories inside the container. For example,
if your Batch Shipyard configs are stored in the host path
`/home/user/batch-shipyard-configs` you could modify the docker run command
as:

```shell
docker run --rm -it -v /home/user/batch-shipyard-configs:/configs alfpark/batch-shipyard:cli-latest <action> --configdir /configs <options...>
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
