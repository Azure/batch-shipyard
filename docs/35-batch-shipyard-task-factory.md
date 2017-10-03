# Batch Shipyard and Task Factories
The focus of this article is to describe the task factory concept and how it
can be utilized to generate arbitrary task arrays. This is particularly useful
in creating parameter (parametric) sweeps, replicated/repeated tasks, or
assigning generated parameters for tasks.

# Task Factory
The normal configuration structure for a job in Batch Shipyard is through the
definition of a `tasks` array which contain individual task specifications.
Sometimes it is necessary to create a set of tasks where the base task
specification is the same (e.g., the run options, input, etc.) but the
arguments and options for the `command` must vary between tasks. This can
become tedious and error-prone to perform by hand or requires auxillary
code to generate the jobs configuration.

A task factory is simply a task generator for a job. With this functionality,
you can direct Batch Shipyard to generate a set of tasks given a
`task_factory` property. If applicable, parameters specified in the
`task_factory` are then applied to the `command` resulting in a transformed
task.

Note that you can attach only one `task_factory` specification to one
task specification within the `tasks` array. However, you can have multiple
task specifications in the `tasks` array thus allowing for multiple and
potentially different types of task factories per job.

Now we'll dive into each type of task factory available in Batch Shipyard.

#### Quick Navigation
1. [Parametric Sweep: Product](#ps-product)
2. [Parametric Sweep: Combinations](#ps-combinations)
3. [Parametric Sweep: Permutations](#ps-permutations)
4. [Parametric Sweep: Zip](#ps-zip)
5. [Random](#random)
6. [Repeat](#repeat)
7. [File](#file)
8. [Custom](#custom)

## Parametric (Parameter) Sweep
A `parametric_sweep` will generate parameters to apply to the `command`
according to the type of sweep.

### <a name="ps-product"></a>Product
A `product` `parametric_sweep` can perform nested or unnested parameter
generation. For example, if you need to generate a range of integers from
0 to 9 with a step size of 1 (thus 10 integers total), you would specify this
as:

```yaml
task_factory:
  parametric_sweep:
    product:
    - start: 0
      step: 1
      stop: 10
command: /bin/bash -c "sleep {0}"
```

As shown above, the associated `command` requires either `{}` or `{0}`
Python-style string formatting to specify where to substitute the generated
argument value within the `command` string.

This `task_factory` example specified above would create 10 tasks:

```
  Task 0:
  /bin/bash -c "sleep 0"

  Task 1:
  /bin/bash -c "sleep 1"

  Task 2:
  /bin/bash -c "sleep 2"

  ...

  Task 9:
  /bin/bash -c "sleep 9"
```

As mentioned above, `product` can generate nested parameter sets. To do this
one would create two or more `start`, `stop`, `step` objects in the
`product` array. For example:

```yaml
task_factory:
  parametric_sweep:
    product:
    - start: 0
      step: 1
      stop: 3
    - start: 100
      step: -1
      stop: 97
command: /bin/bash -c "sleep {0}; sleep {1}"
```

would generate 9 tasks (i.e., `3 * 3` sets of parameters):

```
  Task 0:
  /bin/bash -c "sleep 0; sleep 100"

  Task 1:
  /bin/bash -c "sleep 0; sleep 99"

  Task 2:
  /bin/bash -c "sleep 0; sleep 98"

  Task 3:
  /bin/bash -c "sleep 1; sleep 100"

  Task 4:
  /bin/bash -c "sleep 1; sleep 99"

  Task 5:
  /bin/bash -c "sleep 1; sleep 98"

  Task 6:
  /bin/bash -c "sleep 2; sleep 100"

  Task 7:
  /bin/bash -c "sleep 2; sleep 99"

  Task 8:
  /bin/bash -c "sleep 2; sleep 98"
```

You can nest an arbitrary number of parameter sets within the `product`
array.

### <a name="ps-combinations"></a>Combinations
The `combinations` `parametric_sweep` generates `length` subsequences of
parameters from the `iterable`. Combinations are emitted in lexicographic
sort order. Combinations with replacement can be specified by setting the
`replacement` option to `true`. For example:

```yaml
task_factory:
  parametric_sweep:
    combinations:
      iterable:
      - abc
      - '012'
      - def
      length: 2
      replacement: false
command: /bin/bash -c "echo {0}; echo {1}"
```

would generate 3 tasks:

```
  Task 0:
  /bin/bash -c "echo abc; echo 012"

  Task 1:
  /bin/bash -c "echo abc; echo def"

  Task 2:
  /bin/bash -c "echo 012; echo def"
```

### <a name="ps-permutations"></a>Permutations
The `permutations` `parametric_sweep` generates `length` permutations of
parameters from the `iterable`. Permutations are emitted in lexicographic
sort order. For example:

```yaml
task_factory:
  parametric_sweep:
    permutations:
      iterable:
      - abc
      - '012'
      - def
      length: 2
command: /bin/bash -c "echo {0}; echo {1}"
```

would generate 6 tasks:

```
  Task 0:
  /bin/bash -c "echo abc; echo 012"

  Task 1:
  /bin/bash -c "echo abc; echo def"

  Task 2:
  /bin/bash -c "echo 012; echo abc"

  Task 3:
  /bin/bash -c "echo 012; echo def"

  Task 4:
  /bin/bash -c "echo def; echo abc"

  Task 5:
  /bin/bash -c "echo def; echo 012"
```

### <a name="ps-zip"></a>Zip
The `zip` `parametric_sweep` generates parameters where the i-th parameter
contains the i-th element from each iterable. For example:

```yaml
task_factory:
  parametric_sweep:
    zip:
    - abc
    - '012'
    - def
command: /bin/bash -c "echo {0}; echo {1}; echo {2}"
```

would generate 3 tasks:

```
  Task 0:
  /bin/bash -c "echo a; echo 0; echo d"

  Task 1:
  /bin/bash -c "echo b; echo 1; echo e"

  Task 2:
  /bin/bash -c "echo c; echo 2; echo f"
```

## <a name="random"></a>Random
A `random` task factory will generate random values for the `command` up to
N times as specified by the `generate` property. The `random` task factory
can generate both integral and floating point (real) values.

For example:

```yaml
task_factory:
  random:
    generate: 3
    integer:
      start: 0
      step: 1
      stop: 10
command: /bin/bash -c "sleep {}"
```

will generate 3 tasks with random integral sleep times ranging from 0 to 9.

To generate floating point values, you can use the `distribution`
functionality as required by your scenario. For example:

```yaml
task_factory:
  random:
    distribution:
      uniform:
        a: 0.0
        b: 1.0
    generate: 3
command: /bin/bash -c "sleep {}"
```

will generate 3 tasks with random floating point values pulled from a
uniform distribution between 0.0 and 1.0.

The following distributions are available:

* `uniform`
* `triangular`
* `beta`
* `exponential`
* `gamma`
* `gauss`
* `lognormal`
* `pareto`
* `weibull`

For more information, please see the
[distribution](https://docs.python.org/3.6/library/random.html#real-valued-distributions)
property explanations.

## Repeat
A `repeat` task factory simply replicates the `command` N number of times.
For example:

```yaml
task_factory:
  repeat: 3
command: /bin/bash -c "sleep 1"
```

would create three tasks with identical commands of `/bin/bash -c "sleep 1"`.

## <a name="file"></a>File
A `file` task factory will generate tasks by enumerating a target storage
container or file share for entities and then applying any specified keyword
arguments to the `command`.

For example, let's assume that we want to generate a task for every blob
found in the container `mycontainer` in the storage account link named
`mystorageaccount`. The task factory for this could be:

```yaml
task_factory:
  file:
    azure_storage:
      storage_account_settings: mystorageaccount
      container: mycontainer
    task_filepath: file_path
command: /bin/bash -c "echo url={url} full_path={file_path_with_container} file_path={file_path} file_name={file_name} file_name_no_extension={file_name_no_extension}"
```

As you can see from the `command` above, there are keyword formatters
available:

* `url` is the full URL of the blob resource including the SAS. This is not
available for files on file shares.
* `file_path_with_container` is the path of the blob or file (with all
virtual directories) prepended with the container or file share name
* `file_path` is the path of the blob or file (with all virtual directories)
* `file_name` is the blob or file name without the virtual directories
* `file_name_no_extension` is just the blob or file name without the
virtual directories and file extension

Let's assume that `mycontainer` contains the following blobs:
```
test0.bin
test1.bin
archived\old0.bin
archived\old1.bin
```

This would generate 4 tasks:
```
  Task 0:
  /bin/bash -c "echo url=<full blob url with sas> full_path=mycontainer/test0.bin file_path=test0.bin file_name=test0.bin file_name_no_extension=test0"

  Task 1:
  /bin/bash -c "echo url=<full blob url with sas> full_path=mycontainer/test1.bin file_path=test1.bin file_name=test1.bin file_name_no_extension=test1"

  Task 2:
  /bin/bash -c "echo url=<full blob url with sas> full_path=mycontainer/archived/old0.bin file_path=archived/old0.bin file_name=old0.bin file_name_no_extension=old0"

  Task 3:
  /bin/bash -c "echo url=<full blob url with sas> full_path=mycontainer/archived/old1.bin file_path=archived/old1.bin file_name=old1.bin file_name_no_extension=old1"
```

Each task would automatically download each blob "assigned" to it
automatically in the task's working directory as specified by the
`task_filepath` property. This property has the following valid values,
similar to the keyword arguments above:

* `file_path_with_container` is the path of the blob or file (with all
virtual directories) prepended with the container or file share name
* `file_path` is the path of the blob or file (with all virtual directories)
* `file_name` is the blob or file name without the virtual directories
* `file_name_no_extension` is just the blob or file name without the
virtual directories and file extension

For the example above, the files would be downloaded to the compute node
as follows, given the `task_filepath` being set to `file_path`:
```
  Task 0:
  wd/test0.bin

  Task 1:
  wd/test1.bin

  Task 2:
  wd/archived/old0.bin

  Task 3:
  wd/archived/old1.bin
```

Please note that a point in time listing of the blob container or file share
is performed when the `jobs add` is called. Any modification of the
container or file share during `jobs add` will result in non-deterministic
behavior or even potentially unstable execution of the submission process.

## <a name="custom"></a>Custom
A `custom` task factory will generate tasks by calling a custom Python-based
generator function named `generate` supplied by the user. This is accomplished
by importing a user-defined Python module which has a defined `generate`
generator function.

For example, suppose we create a directory named `foo` in our Batch Shipyard
installation directory and have our custom generator as follows:

```
batch-shipyard
|-- foo
    |-- __init__.py
    +-- generator.py
```

Inside the `foo` directory we have a bare `__init__.py` file and a file named
`generator.py` which will contain our logic to generate parameters. Note that
the custom task factory does not have to reside within your Batch Shipyard
installation directory, but must be resolvable by `importlib.import_module()`.

Inside `generator.py` resides our logic to generate parameters for the
task factory. The one required function to implement must be named
`generate`. For example, let's suppose we want to generate a range of
parameters for each argument given:

```python
# in file generator.py

def generate(*args, **kwargs):
    for arg in args:
        for x in range(0, arg):
            yield (x,)
```

The `generate` function acceps two variadic parameters: `*args` and `**kwargs`
which correspond to the configuration `input_args` and `input_kwargs`,
respectively. If using `input_kwargs`, then the dictionary specified
must have only string-based keys. You can use any combination of `input_args`
and `input_kwargs` or no input if not required. In this example, for each
positional argument (i.e., `*args`), we are creating a range from `0` to that
argument value and `yield`ing the result as a iterable (tuple). Yielding
the result as an iterable is mandatory as the return value is unpacked and
applied to the `command`. This allows for multiple parameters to be generated
and applied for each generated task. An example corresponding configuration
may be similar to the following:

```yaml
task_factory:
  custom:
    input_args:
    - 1
    - 2
    - 3
    module: foo.generator
command: /bin/bash -c "sleep {}"
```

which would result in 6 tasks:
```
  Task 0:
  /bin/bash -c "sleep 0"

  Task 1:
  /bin/bash -c "sleep 0"

  Task 2:
  /bin/bash -c "sleep 1"

  Task 3:
  /bin/bash -c "sleep 0"

  Task 4:
  /bin/bash -c "sleep 1"

  Task 5:
  /bin/bash -c "sleep 2"
```

Of course, this example is contrived and custom task factory logic will
invariably be more complex. Your generator function can be dependent upon
any Python package that is needed to accomodate complex task factory parameter
generation scenarios. Please note that if you have installed your Batch
Shipyard environment into a virtual environment and your dependencies are
non-local (i.e., not in the Batch Shipyard directory), then you need to
ensure that your dependencies are properly installed in the correct
environment.

## Configuration guide
Please see the [jobs configuration guide](14-batch-shipyard-configuration-jobs.md)
for more information on configuration for jobs and tasks.
