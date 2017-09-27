# FFmpeg-GPU
This recipe shows how to run [FFmpeg](https://ffmpeg.org/) for using
hardware-accelerated encoding/transcoding on GPUs using N-series Azure VM
instances in an Azure Batch compute pool.

## Configuration
Please see refer to this [set of sample configuration files](./config) for
this recipe.

### Pool Configuration
The pool configuration should enable the following properties:
* `vm_size` must be a GPU enabled VM size. Because FFmpeg is for
transcoding audio/video, you should choose an `NV` VM instance size.
* `vm_configuration` is the VM configuration
  * `platform_image` specifies to use a platform image
    * `publisher` should be `Canonical` or `OpenLogic`.
    * `offer` should be `UbuntuServer` for Canonical or `CentOS` for OpenLogic.
    * `sku` should be `16.04-LTS` for Ubuntu or `7.3` for CentOS.

### Global Configuration
The global configuration should set the following properties:
* `docker_images` array must have a reference to a valid FFmpeg NVENC
GPU-enabled Docker image. The
[alfpark/ffmpeg:3.2.1-nvenc](https://hub.docker.com/r/alfpark/ffmpeg)
can be used for this recipe.

### Jobs Configuration
The jobs configuration should set the following properties within the `tasks`
array which should have a task definition containing:
* `image` should be the name of the Docker image for this container invocation,
e.g., `alfpark/ffmpeg:3.2.1-nvenc`
* `command` should contain the command to pass to the Docker run invocation.
The following command takes an mp4 video file and transcodes it to H.265/HEVC
using NVENC transcode offload on to the GPU:
`"-i samplevideo.mp4 -c:v hevc_nvenc -preset default output.mp4"`
  * `samplevideo.mp4` should be a file that is accessible by the task. You
    can utilize the `resource_files` on the
    [task configuration](../../docs/10-batch-shipyard-configuration.md) for
    any number of files to be available to the task for processing.
  * `hevc_nvenc` informs FFmpeg to use the H.256/HEVC NVENC encoder. To
    encode with H.264 using NVENC specify `h264_nvenc` instead.
* `gpu` can be set to `true`, however, it is implicitly enabled by Batch
Shipyard when executing on a GPU-enabled compute pool.

## Dockerfile and supplementary files
The `Dockerfile` for the Docker image referenced above can be found
[here](https://github.com/alfpark/docker-ffmpeg/blob/master/nvenc/).
