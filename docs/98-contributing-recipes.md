# Contributing Recipes
First, thank you for considering to contribute your recipe to the wider
community! Below are some general guidelines to follow when contributing
a recipe to Batch Shipyard.

### Follow the Directory Structure of Existing Recipes
Please follow the existing recipe directory structure for the recipe that
you wish to add. Each recipe directory structure typically has the following
structure:

```
  recipes/
    SOFTWARE-NAME/
      README.md
      config/
        config.yaml
        credentials.yaml
        jobs.yaml
        pool.yaml
      docker/
        README.md
        Dockerfile
        ...
```

The `docker` directory is optional if your Docker image is an automated
build on public Docker Hub, however, please read the other requirements
regarding links to licenses.

### Provide a Clear README File
Each recipe should contain a clear README.md file that links to the
application website and steps through each configuration file (pool, global,
jobs). Provide links to configuration files within the README.md file
as sample configurations users can utilize to get started with your
recipe.

Provide any additional pointers or thinge to look out for when running
the Docker image and the application. For instance, if running a
Multi-Instance task with MPI and the application expects a shared file
system for output files, then explicitly mention this with an example
or reference on how to set this up properly within Batch Shipyard.

### Provide a Sample Execution
Each recipe should provide a sample execution to validate that Batch
Shipyard works with the provided Docker image. It is preferable to
embed a sample in the Docker image which you can then use during your
jobs configuration text in the README.md file to explain how to launch
a job.

### Create Generic Configuration Files
Create a set of generic configuration files without specific links to
credential names, aliases or other sensitive info. The credentials config
file should not contain any pre-filled information except for a storage
account endpoint. Please take a look at the pre-existing recipe sample
config files to see an example.

### Use YAML Syntax for Configuration Files
Configuration files should use YAML syntax rather than JSON.

### Docker Image References
If you are providing your own Docker image reference in the global
configuration and jobs config files, then the Dockerfile must be publically
accessible. The docker image can be hosted as an automated build on
public Docker Hub which will automatically upload the Dockerfile to your
repository, or you will need to explicitly provide a link in Docker Hub
and in the README for the recipe to the Dockerfile which can be viewable by
anyone.

Ensuring transparency in the Docker images used for recipes will create
a more open and better experience for all users that wish to use your recipe.

### Provide Links to Licenses
You must provide links to licenses used by the application in the recipe
README and the associated `docker` directory, if provided.

### Optimize Dockerfiles
If possible, try to create Docker images with the minimal amount of layers.
This involves coalescing multiple `RUN` or other statements together.
Reducing the number of layers can potentially reduce the size of the
Docker image which is of concern for image replication to compute nodes.

If you are able to completely remove the source files of your application,
then it is recommended to do so after the binaries are installed on the
system (e.g., through `make install`). Additionally, if some software is
only needed to build the application and can be safely removed, then it is
recommended to do so. For instance, if your software requires development
headers to compile, these can be removed after the binary is produced.
Similarly, temporary files as a result of the build process (e.g., `.o` or
`.dep` files) can be removed to reduce the size of the final Docker image.

### Multi-Instance (MPI) Recipes
Please ensure that the necessary SSH, MPI runtime, or other software is
installed into the Docker image (if licensing allows) such that Multi-Instance
tasks can be run on them without requiring users to import your image and add
them later. Please refer to the
[Multi-Instance doc](80-batch-shipyard-multi-instance-tasks.md) for more
information.

There are sample recipes which showcase MPI on Batch Shipyard, please
reference those as examples.

## Existing Recipes
Please see [this directory](../recipes) for existing recipes.
