# Multi-Instance Tasks and Batch Shipyard
The focus of this article is to explain how multi-instance tasks work in
the context of Azure Batch, Containers in both the
[Docker](https://www.docker.com/) and [Singularity](https://www.sylabs.io)
contexts, and Batch Shipyard.

## Overview
Multi-instance tasks are a special type of task in Azure Batch that are
primarily targeted for an execution that requires multiple compute nodes in
order to run. The canonical use case for multi-instance tasks are MPI jobs.
MPI jobs are typically run on a cluster of nodes where each node participates
in the execution by performing computation on a part of the problem and
coordinates with other nodes to reach a solution.

Batch Shipyard helps users execute containerized MPI workloads by performing
the necessary steps to stage either a Docker or Singularity container for
the multi-instance (MPI) job.

## MPI Runtime
Most popular MPI runtimes can operate with or without an integrated
distributed resource manager (launcher). In the case of Azure Batch on Linux,
the launcher is via remote shell. As the use of `rsh` is generally deprecated,
launchers typically default to `ssh`. The master node (i.e., the node from
where `mpirun` or `mpiexec` was invoked), will remote shell to all of the
other compute node hosts in the compute pool. In order for the master node to
know which nodes to connect to, runtimes typically require a host or node
list.

Once all of the nodes have been contacted and initialization of the MPI runtime
is complete across all of the nodes, then the MPI application can execute.

### Seamless MPI Runtime Integration
Batch Shipyard, as of version `3.8.0`, provides seamless MPI launch
integration for popular MPI runtimes, including OpenMPI, MPICH, MVAPICH,
and Intel MPI. Users can now specify simply the runtime they wish to use
and if the environment contains the proper runtime, the commandlines for
launching will automatically be populated. In the case of RDMA VMs,
complexity of certain requirements such as exposing the IB PKEY are
automatically handled.

Please see the
[jobs configuration documentation](14-batch-shipyard-configuration-jobs.md)
for more information about the MPI interface available in Batch Shipyard.

## Singularity Containers and MPI
[Singularity](https://www.sylabs.io) containers are built for common
HPC scenarios. Thus, executing an MPI application works seamlessly with
the host - as if you are executing any other program.

### Singularity and MPI Mental Model
Since Singularity containers work as though you are executing any other
distributed program via MPI, there are no extra concepts to grasp.

```
+---------------+
|  MPI Program  |  << Singularity Container
+---------------+
+---------------+------------+
|  MPI Runtime  | SSH Server |
+---------------+------------+
+===============+============+
|     Operating System       |
+============================+
|  Host or Virtual Machine   |
+============================+
```

The MPI program in the Singularity container would be executed using
the host's `mpirun` (or `mpiexec`) command. Thus, the launcher would
take advantage of the host's SSH server and network stack allowing MPI
jobs to run within Singularity containers as if they were running on
the host OS.

## Docker Containers and MPI
Docker images for MPI applications must be carefully crafted such that
the MPI runtime is able to communicate properly with other compute nodes.
Outside of installing the necessary software required for MPI to run, the
difference is that images that use MPI must also install SSH client/server
software and enable the SSH server as the `CMD` with a port exposed to the
host. Remember, the container will be running isolated from the host, so if
you attempt to connect to the SSH server running on the host, the launcher
will attempt to initialize on the host with an MPI runtime that doesn't
exist.

### Docker and MPI Mental Model
With the basics reviewed above, we can construct a mental model of the layout
of how a Dockerized MPI program will execute.

The typical Docker package, distribute, deploy model usually ends up with an
image being run with `docker run`. This is fine for a large majority of  use
cases. However, for multi-instance tasks and MPI jobs in particular, a simple
`docker run` is insufficient because most (all?) MPI runtimes do not know how
to connect and initialize MPI running within a container on other compute
nodes.

```
+---------------+
|  MPI Program  |
|  MPI Runtime  |  << Docker Container
|  SSH Server   |
+---------------+
+---------------+------------+
| Docker Daemon | SSH Server |
+---------------+------------+
+===============+============+
|     Operating System       |
+============================+
|  Host or Virtual Machine   |
+============================+
```

The above layout shows the software stack from the host up through to the
Docker container. The MPI application running inside the container will need
to connect to other identical containers on other compute nodes.

Dockerized multi-instance tasks will use a combination of `docker run` and
`docker exec`. `docker run` will create a running instance of the Docker image
and detach it with the SSH server running. Then the `mpirun` or `mpiexec`
command will be executed inside the running container using `docker exec`.

### Azure Batch Compute Nodes and SSH
By default Azure Batch compute nodes have an SSH server running on them so
users can connect remotely to their compute nodes. Internally, the system
default SSH server is running on port 22. (However, this port is not mapped
through the load balancer as an instance endpoint on port 22). This can lead
to conflicts as described in the next section.

#### Dockerized MPI Applications and Azure Batch Compute Nodes
Because the internally mapped Docker container IP address is dynamic and
unknown to the Azure Batch service at job run time, the Docker image must
be run using the host networking stack so the host IP address is visible
to the running Docker container. This allows Docker MPI applications to
use `AZ_BATCH_HOST_LIST` which the Azure Batch service populates with all
of the IP addresses of other compute nodes involved in the multi-instance
task.

Because of this host networking requirement, there will be a conflict
on the default SSH server port of 22. Thus, in the Dockerfile, the
SSH server in the `CMD` command should be bound to an alternate port such
as port 23, along with the corresponding `EXPOSE` directive.

#### SSH User and Options
Because Docker requires running containers as root, all Batch Shipyard
jobs are invoked with elevated permissions. A side effect is that this
makes setting up the SSH passwordless authentication a bit easier.

The Docker container context, at runtime, should have the proper SSH keys
in the root or user context (if using user identities). These can be either
mounted in from the host OS, copied into the Docker image during build time
via `COPY`, or generated during build time. Note that if you copy or generate
the keys into your Docker image, publishing your Docker image will expose
your private RSA key. Although external users will not be able to SSH into
these running instances by default as this SSH port is not exposed externally,
it can still be a security risk if a compute node is compromised. If this is
an unacceptable risk for your scenario, you should be mounting in a private
key into the Docker image at runtime which is not published as part of the
image build process.

Additionally, an `authorized_keys` file corresponding to the public key for
the user that will execute the task should be present within the Docker
container. SSH clients will also need to be transparently directed to
connect to the alternate port and ignore input prompts since these
programs will be run in non-interactive mode. If you cannot override your MPI
runtime remote shell options, you can use an SSH `config` file stored in the
respective root or user's `.ssh` directory alongside the keys:

```
Host 10.*
  Port 23
  StrictHostKeyChecking no
  UserKnownHostsFile /dev/null
```

Note the host wildcard, if the virtual network subnet for the Azure Batch
compute nodes does not start with 10.\* then this must be modified. In this
example port 23 is forced as the default for any ssh client connections to
destination hosts of 10.\* which would match the `EXPOSE` port in the Docker
image.

## Containers and Azure Batch Multi-Instance Tasks
Batch Shipyard supports Docker containers in `native` container supported
pools, in non-`native` pools and Singularity containers in non-`native`
pools for multi-instance tasks.

For `native` container supported pools and Singularity containers, Batch
Shipyard executes these tasks as normal multi-instance tasks would as either
Azure Batch natively understands how to handle these executions or that
they work the same as if the task is executing a multi-instance task on
the host.

For non-`native` container supported pools and Docker containers, Batch
Shipyard performs transformations to ensure that such executions are
possible. The following sub-sections explains the details for these
types of executions.

### Multi-Instance Task Coordination Command for non-`native` Docker containers
In an Azure Batch multi-instance task, a coordination command is executed on
all compute nodes of the task before the application command is run. As
described in the mental model above, a combination of `docker run` and
`docker exec` is used to execute an MPI job on Azure Batch with Docker.
The coordination command is the `docker run` part of the process which creates
a running instance of the Docker image. If the `CMD` directive in the Docker
image is not set (i.e., SSH server to execute), then an actual coordination
command should be supplied to Batch Shipyard.

### Multi-Instance Task Application Command for non-`native` Docker containers
The application command is the `docker exec` portion of the Docker MPI
job execution with Batch Shipyard. This is typically a call to `mpirun`
or `mpiexec` or a wrapper script that launches either `mpirun` or `mpiexec`.

### Cleanup for non-`native` Docker containers
As the Docker image is run in detached mode with `docker run`, the container
will still be running after the application command completes. Currently,
there is no "clean" way to perform cleanup from the Azure Batch API.
However, by using the job auto-complete and job release facilities provided
by Azure Batch, Batch Shipyard can automatically stop and remove the Docker
container. By default, this behavior is not enabled automatically, however,
by specifying the `auto_complete` property for your job to `true`, your
multi-instance task will automatically be cleaned up for you, but limits
the number of multi-instance tasks per job to 1.

If you require or prefer more than one multi-instance task per job, you can
keep the `auto_complete` setting to `false`
[job specification](14-batch-shipyard-configuration-jobs.md) of each job.
To manually cleanup after multi-instance tasks, there are helper methods in
the Batch Shipyard toolkit. These methods will aid in cleaning up compute nodes
involved in multi-instance tasks if they are needed to be reused for
additional jobs. Please refer to `jobs cmi` and `jobs cmi --delete` actions
in the [Batch Shipyard Usage](20-batch-shipyard-usage.md) doc.

## Automation!
Nearly all of the Docker or Singularity runtime complexities are taken care of
by Batch Shipyard. The user just needs to ensure that their MPI container
images are either constructed with the aforementioned accommodations and/or
are able to provide sufficient commands to the coordination/application
commands to work with the Azure Batch compute node environment.

As referred to earlier in this guide, Batch Shipyard now provides seamless
MPI runtime integration with popular frameworks.

## Which to choose for MPI? Docker or Singularity?
In the context of Batch Shipyard, both approaches are somewhat similar as
Batch Shipyard takes care of a lot of the complexity. However, if you are
using a Docker image, then you need to ensure that your image contains the
directives to install and start an SSH server (or whatever mechanism your
MPI runtime requires as a launcher).

Since Singularity is inherently easier to use in conjunction with MPI programs,
it may be beneficial to use Singularity to containerize your MPI application
instead of Docker. There is no need to package a launcher with your image
and is handled more elegantly in Batch Shipyard without the need to split
the execution and deal with potential cleanup artifacts if executing in
non-`native` mode. Additionally, there has been
[published research](https://arxiv.org/abs/1709.10140) to indicate that
Singularity outperforms other OS virtualization approaches for certain
benchmarks and is more amenable for HPC applications.

### More Information
For more general information about MPI and Azure Batch, please visit
[this page](https://azure.microsoft.com/documentation/articles/batch-mpi/).

## Example recipes and samples
Please visit the
[recipes directory](https://github.com/Azure/batch-shipyard/tree/master/recipes)
for multi-instance task samples.
