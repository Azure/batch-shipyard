# Multi-Instance Tasks and Batch Shipyard
The focus of this article is to explain how multi-instance tasks work in
the context of Azure Batch, Docker, and Batch Shipyard.

## Overview
Multi-instance tasks are a special type of task in Azure Batch that are
primarily targeted for an execution that requires multiple compute nodes in
order to run. The typical use case for multi-instance tasks are MPI jobs.
MPI jobs are typically run on a cluster of nodes where each node participates
in the execution by performing computation on a part of the problem and
coordinates with other nodes to reach a solution.

Batch Shipyard helps users execute Dockerized MPI workloads by performing
the necessary steps to stage the Docker container for the MPI job.

## In-depth Concepts
### MPI Runtime
Most popular MPI runtimes can operate with or without an integrated
distributed resource manager (launcher). In the case of Azure Batch on Linux,
the launcher is via remote shell. As the use of `rsh` is generally deprecated,
launchers typically default to `ssh`. The master node (i.e., the node from
where `mpirun` was invoked), will remote shell to all of the other compute
node hosts in the compute pool. In order for the master node to know which
nodes to connect to, runtimes typically require a host or node list.

Once all of the nodes have been contacted and initialization of the MPI runtime
is complete across all of the nodes, then the MPI application can execute.

### Dockerized MPI Applications
Docker images for MPI applications are nearly the same as other non-MPI
applications. Outside of installing the necessary software required for
MPI to run, the difference is that images that use MPI must also install
SSH client/server software and enable the SSH server as the `CMD` with a
port exposed to the host. Remember, the container will be running isolated
from the host, so the SSH server running on the host will attempt to
initialize with an MPI runtime that doesn't exist.

### Mental Model
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
and detach it with the SSH server running. Then the `mpirun` command will
be executed inside the running container using `docker exec`.

### Azure Batch Compute Nodes and SSH
By default Azure Batch compute nodes have an SSH server running on them so
users can connect remotely to their compute nodes. Internally, the system
default SSH server is running on port 22. (However, this port is not mapped
through the load balancer as an instance endpoint on port 22). This can lead
to conflicts as described in the next section.

### Dockerized MPI Applications and Azure Batch Compute Nodes
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

### SSH User and Options
Because Docker requires running containers as root, all Batch Shipyard
jobs are invoked with elevated permissions. A side effect is that this
makes setting up the SSH passwordless authentication a bit easier.

Docker images should contain the proper directives to generate an SSH
RSA public/private key pair (or alternatively `COPY` a pair) and an
`authorized_keys` file corresponding to the public key for the root user
within the Docker container. Additionally, ssh clients need to be transparently
directed to connect to the alternate port and ignore input prompts since these
programs will be run in non-interactive mode. If you cannot override your MPI
runtime remote shell options, you can use an SSH config file stored in the root
user's `.ssh` directory alongside the keys:

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

### Multi-Instance Task Coordination Command
In an Azure Batch multi-instance task, a coordination command is executed on
all compute nodes of the task before the application command is run. As
described in the mental model above, a combination of `docker run` and
`docker exec` is used to execute an MPI job on Azure Batch with Docker.
The coordination command is the `docker run` part of the process which creates
a running instance of the Docker image. If the `CMD` directive in the Docker
image is not set (i.e., SSH server to execute), then an actual coordination
command should be supplied to Batch Shipyard.

### Multi-Instance Task Application Command
The application command is the `docker exec` portion of the Docker MPI
job execution with Batch Shipyard. This is typically a call to `mpirun`
or a wrapper script that launches `mpirun`.

### Cleanup
As the Docker image is run in detached mode with `docker run`, the container
will still be running after the application command completes. Currently,
there is no "clean" way to do perform cleanup from the Azure Batch API.
However, by using the job auto-complete and job release facilities provided
by Azure Batch, Batch Shipyard can automatically stop and remove the Docker
container. By default, multi-instance tasks are now cleaned up using this
method, but limits the number of multi-instance tasks per job to 1.

If you require or prefer more than 1 multi-instance task per job, you can
override the default cleanup behavior by specifying
`multi_instance_auto_complete` to `false` in the
[job specification](02-batch-shipyard-configuration.md) of each job.
To manually cleanup after multi-instance tasks, there are helper methods in
the Batch Shipyard toolkit. These methods will aid in cleaning up compute nodes
involved in multi-instance tasks if they are needed to be reused for
additional jobs. Please refer to `cleanmijobs` and `delcleanmijobs` actions
in the [Batch Shipyard Usage](03-batch-shipyard-usage.md) doc.

### Automation!
Nearly all of the Docker runtime complexities are taken care of by the Batch
Shipyard tooling. The user just needs to ensure that their MPI Docker images
are either constructed with the aforementioned accommodations or are able
to provide sufficient commands to the coordination/application commands to
work with the Azure Batch compute node environment.

### More Information
For more general information about MPI and Azure Batch, please visit
[this page](https://azure.microsoft.com/en-us/documentation/articles/batch-mpi/).

## Example recipes and samples
Please visit the [recipes directory](../recipes) for multi-instance task
samples.
