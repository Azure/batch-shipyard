# RNASeq-CPU
This recipe shows how to run a proof-of-concept RNA-Seq pipeline on a single
node using Azure Batch. This recipe uses task dependencies to ensure each
step of the pipeline is executed in the proper order and only if each
step completes successfully.

## Configuration
Please see refer to this [set of sample configuration files](./config) for
this recipe.

### Pool Configuration
Pool properties such as `publisher`, `offer`, `sku`, `vm_size` and
`vm_count` should be set to your desired values.

Because this example requires data files which are not part of the Docker
images and need to be shared between tasks, we will utilize `resource_files`
at the pool-level to ingress required data. Normally, `shared_data_volumes`
in the global configuration would be used for this purpose (e.g., NFS or
objects in Azure Storage).

### Global Configuration
The global configuration should set the following properties:

```yaml
batch_shipyard:
  storage_account_settings: mystorageaccount
global_resources:
  docker_images:
    - quay.io/biocontainers/bowtie2:2.3.4.3--py36h2d50403_0
    - quay.io/biocontainers/tophat:2.1.1--py27_1
    - quay.io/biocontainers/cufflinks:2.2.1--py36_2
```

The `docker_images` array contains references to each of the tools
required for the sequencing pipeline.

### Jobs Configuration
The pipeline will take advantage of task dependencies to ensure tasks
are processed one after the next after successful completion of each.
Please see the [jobs configuration](./config/jobs.yaml) for the full
example.
