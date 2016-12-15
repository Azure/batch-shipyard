# SSH, Interactive Sessions, Tunneling, Docker Daemon and Batch Shipyard
The focus of this article is to explain how Azure Batch compute nodes exist
with an Azure deployment, interactive SSH, and the concept of SSH tunneling
to a Docker Host on an Azure Batch compute node from your local machine.

## Azure Batch Deployments and Port Exposure
Azure Batch compute nodes which comprise a pool are behind a NAT/load balancer
which have certain endpoints exposed on the public IP of the deployment to
specific instances (i.e., compute nodes).

For instance, port 12345 may map to port 22 of the first instance of a
compute node in the pool for the public IP address 1.2.3.4. The next compute
node in the pool may have port 22 mapped to 12346 on the load balancer.

This allows many compute nodes to sit behind one public IP address.

## Interactive SSH
By adding an SSH user to the pool (which can be automatically done for you
via the `ssh` block in the pool config), you can interactively log in to
compute nodes in the pool and execute any command on the remote machine,
including Docker commands via `sudo`.

You can utilize the `pool ssh` command to automatically connect to any
compute node in the pool without having to manually resort to `pool grls`
and issuing the `ssh` command with the appropriate parameters. If you have
the SSH private key in the default location or as specified in the
`generated_file_export_path`, then an interactive SSH session will be
created to the compute node specified.

`pool ssh` requires either the option `--cardinal` or the option `--nodeid`.
If using `--cardinal` it requires the natural counting number from zero
associated with the list of nodes as enumerated by `pool grls`. If using
`--nodeid`, then the exact compute node id within the pool specified in
the pool config must be used.

## Securely Connecting to the Docker Socket Remotely via SSH Tunneling
To take advantage of this feature, you must install Docker locally on your
machine and have `ssh` available. You can find guides to install Docker
on various operating systems [here](https://docs.docker.com/engine/installation/).

The typical recommendation is to secure the Docker daemon if being
accessed remotely via certificates and TLS. Because SSH is already configured
on all of the nodes with authorized users to use the Docker daemon with
Batch Shipyard, we can simply use SSH tunneling instead which simplifies
the process and is less likely to be blocked in outbound firewall rules.
This method is secure as the tunnel is opened and encrypted via `ssh` with
a public/private RSA key pair. Please note that the Docker daemon port
is not mapped on the NAT/load balancer, so it is impossible to connect to
the port remotely without an SSH tunnel.

By specifying `generate_docker_tunnel_script` as `true` in the `ssh`
configuration block in the pool config, a file named
`ssh_docker_tunnel_shipyard.sh` will be generated on `pool add` if an
SSH user is specified, on `pool asu` when a pool user is added, on
`pool resize` when a pool is resized, or on `pool grls` when a pool's
remote login settings are listed.

This script simplifies creating an SSH tunnel to the Docker socket from
your local machine. It accepts a cardinal number of the node to connect
to, similar to the `--cardinal` option for `pool ssh`. So if you were
connecting to the first node in the pool, you would execute the docker
tunnel script as:

```shell
./ssh_docker_tunnel_shipyard.sh 0
```

This will background the SSH tunnel to the remote Docker daemon and output
something similar to the following:

```
tunneling to docker daemon on tvm-2522076272_3-20161214t213502z at 1.2.3.4:12345
ssh tunnel pid is 22204
execute docker commands with DOCKER_HOST=: or with option: -H :
```

Now you can run the `docker` command locally but have these actions
work remotely through the tunnel on the compute node with the appropriate
`-H` option as noted above. For instance:

```shell
docker -H : run --rm -it busybox
```

would place the current shell context inside the busybox container running
remotely on the Batch compute node.

Alternatively you can export an environment variable named `DOCKER_HOST`
which will work for all `docker` invocations until the environment variable
is unset. For example:

```shell
export DOCKER_HOST=:
docker run --rm -it busybox
```

would create a busybox container on the remote similar to the prior command.

To run a CUDA/GPU enabled docker image remotely with nvidia-docker, first you
must install
[nvidia-docker locally](https://github.com/NVIDIA/nvidia-docker/wiki/Installation)
in addition to docker as per the initial requirement. You can install
nvidia-docker locally even without an Nvidia GPU or CUDA installed. It is
simply required for the local command execution. You can then launch your
CUDA-enabled Docker image on the remote compute node on N-series the same
as any other Docker image except invoking with `nvidia-docker` instead:

```shell
DOCKER_HOST=: nvidia-docker run --rm -it nvidia/cuda nvidia-smi
```

Once you are finished with running your `docker` and/or `nvidia-docker`
commands remotely, you can terminate the SSH tunnel by sending a SIGTERM to
the SSH tunnel process. In this example, the pid is 22204 as displayed by
the script, thus we would terminate the SSH tunnel with the following:

```shell
kill 22204
# unset DOCKER_HOST if exported
unset DOCKER_HOST
```

Finally, please remember that the `ssh_docker_tunnel_shipyard.sh` script
is refreshed and is specific for the pool at the time of pool creation,
resize, when an SSH user is added or when the remote login settings are
listed.
