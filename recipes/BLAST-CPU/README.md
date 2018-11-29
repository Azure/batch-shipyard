# BLAST-CPU
This recipe shows how to run a parallelized BLAST pipeline by chunking an
input fasta file and running multiple tasks in parallel using Azure Batch.

## Configuration
Please see refer to this [set of sample configuration files](./config) for
this recipe.

### Pool Configuration
Pool properties such as `publisher`, `offer`, `sku`, `vm_size` and
`vm_count` should be set to your desired values.

The example pool configuration file utilizes 5 low priority VMs which can
be adjusted to your scenario requirements.

### Global Configuration
The global configuration should set the following properties:

```yaml
batch_shipyard:
  storage_account_settings: mystorageaccount
global_resources:
  docker_images:
    - python:3-alpine
    - quay.io/biocontainers/blast:2.7.1--h4422958_6
```

The `docker_images` array contains references to the tools required for the
BLAST pipeline.

### Job/Task Execution Model and Configuration
The pipeline will take advantage of task dependencies to ensure tasks
are processed one after the next after successful completion of each.
The first stage, represented in `jobs-split.yaml` will take an input
fasta file and chunk them into individual query files. These chunks are
then uploaded to the specified storage account to be retrieved by the
parallelized BLAST stage. In the parallelized BLAST stage, represented
by the `jobs-blast.yaml` file, each individual query file is run
across its own individual task. If multiple compute nodes (or
nodes with a larger `max_tasks_per_node` setting that are able to
accommodate the tasks) are available, then the requisite blast commands
are run in parallel. Batch Shipyard automatically generates the correct
number of parallel tasks via a `task_factory` that iterates over the
chunked query fasta files generated in the earlier stage. Finally, a
`merge_task` is run which collates all of the top-10 hits for each
individual chunk into a results text file.

Please see the [jobs configuration](./config) for the full example.

## Execution
The following outlines a sample execution based on this recipe's configuration:

```shell
# create the pool
shipyard pool add

# add the fasta splitter task to create chunked queries for parallelization
shipyard jobs add --jobs jobs-split.yaml --tail stdout.txt

# add the parallelized blast executions with result merge
shipyard jobs add --jobs jobs-blast.yaml

# poll the merge task until it completes
shipyard jobs tasks list --jobid blast --taskid merge-task-00001 --poll-until-tasks-complete

# optionally egress the results.txt file from the compute node to local machine
shipyard data files task --filespec blast,merge-task-00001,wd/results.txt

# clean-up
shipyard jobs del -y --wiat jobs-blast.yaml
shipyard pool del -y
```
