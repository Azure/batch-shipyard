# Batch Shipyard Usage
This page contains in-depth details on how to use the Batch Shipyard tool.

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
The script requires configuration json files described the
[previous doc](01-batch-shipyard-configuration.md) to be passed in as
arguments.

Explanation of arguments:
* `--credentials path/to/credentials.json` is required for all actions.
* `--config path/to/config.json` is required for all actions.
* `--pool path/to/pool.json` is required for most actions.
* `--jobs path/to/jobs.json` is required for job-related actions.
* `--nodeid <compute batch nodeid>` is only required for the `delnode` action.

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
jobs specified in the jobs configuration file.
* `termjobs`: terminate jobs as specified in the jobs configuration file.
* `deljobs`: delete jobs as specified in the jobs configuration file.
* `delcleanmijobs`: delete jobs used to clean up multi-instance jobs.
* `delalljobs`: delete all jobs under the Batch Account.
* `delpool`: delete pool as specified in the pool configuration file.
* `grls`: get remote login settings as specified in the pool configuration
file.
* `streamfile`: stream a file from a live compute node.
* `clearstorage`: clear storage containers as specified in the configuration
files.
* `delstorage`: delete storage containers as specified in the configuration
files.

## Example Invocations
```
python shipyard.py --credentials credentials.json --config config.json --pool pool.json addpool
```
The above invocation will add the pool specified to the Batch account.

```
python shipyard.py --credentials credentials.json --config config.json --pool pool.json --jobs jobs.json addjobs
```
The above invocation will add the jobs specified to the designated pool.

```
python shipyard.py --credentials credentials.json --config config.json --pool pool.json --jobs jobs.json cleanmijobs
```
The above invocation will clean up all multi-instance tasks in all of the jobs specified.

## Explore Recipes and Samples
Visit the [recipes directory](../recipes) for different sample Docker
workloads using Azure Batch and Batch Shipyard.

## Need Help?
[Open an issue](https://github.com/Azure/batch-shipyard/issues) on the GitHub
project page.
