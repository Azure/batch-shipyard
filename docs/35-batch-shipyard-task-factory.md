# Batch Shipyard and Task Factories
The focus of this article is to describe the task factory concept and how it
can be utilized to generate arbitrary task arrays. This is particularly useful
in creating parameter (parametric) sweeps or repeated tasks.

## Task Factory
The normal configuration structure for a job in Batch Shipyard is through the
definition of a `tasks` array which contain individual task specifications.
Sometimes it is necessary to create a set of tasks where the base task
specification is the same (e.g., the run options, input, etc.) but the
arguments and options for the `command` must vary between tasks. This can
become tedious and error-prone to perform by hand or requires auxillary
code to generate the jobs JSON configuration.

A task factory is simply a task generator for a job. With this functionality,
you can direct Batch Shipyard to generate a set of tasks given a
`task_factory` property which is then transforms the `command`, if applicable.

Note that you can attach only one `task_factory` specification to one
task specification within the `tasks` array. However, you can have multiple
task specifications in the `tasks` array thus allowing for multiple and
potentially different types of task factories per job.

Now we'll dive into each type of task factory available in Batch Shipyard.

### Repeat
A `repeat` task factory simply replicates the `command` N number of times.
For example:

```json
    "task_factory": {
        "repeat": 3
    },
    "command": "/bin/bash -c \"sleep 1\""
```

would create three tasks with identical commands of `/bin/bash -c "sleep 1"`.

### Parametric (Parameter) Sweep
A `parametric_sweep` will generate parameters to apply to the `command`
according to the type of sweep.

#### Product
A `product` `parametric_sweep` can perform nested or unnested parameter
generation. For example, if you need to generate a range of integers from
0 to 9 with a step size of 1 (thus 10 integers total), you would specify this
as:

```json
    "task_factory": {
        "parametric_sweep": {
            "product": [
                {
                    "start": 0,
                    "stop": 10,
                    "step": 1
                }
            ]
        }
    },
    "command": "/bin/bash -c \"sleep {0}\""
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

```json
    "task_factory": {
        "parametric_sweep": {
            "product": [
                {
                    "start": 0,
                    "stop": 3,
                    "step": 1
                },
                {
                    "start": 100,
                    "stop": 97,
                    "step": -1
                }
            ]
        }
    },
    "command": "/bin/bash -c \"sleep {0}; sleep {1}\""
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

#### Combinations
The `combinations` `parametric_sweep` generates `length` subsequences of
parameters from the `iterable`. Combinations are emitted in lexicographic
sort order. Combinations with replacement can be specified by setting the
`replacement` option to `true`. For example:

```json
    "task_factory": {
        "parametric_sweep": {
            "combinations": {
               "iterable": ["abc", "012", "def"],
               "length": 2,
               "replacement": false
            }
        }
    },
    "command": "/bin/bash -c \"echo {0}; echo {1}\""
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

#### Permutations
The `permutations` `parametric_sweep` generates `length` permutations of
parameters from the `iterable`. Permutations are emitted in lexicographic
sort order. For example:

```json
    "task_factory": {
        "parametric_sweep": {
            "permutations": {
               "iterable": ["abc", "012", "def"],
               "length": 2
            }
        }
    },
    "command": "/bin/bash -c \"echo {0}; echo {1}\""
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

#### Zip
The `zip` `parametric_sweep` generates parameters where the i-th parameter
contains the i-th element from each iterable. For example:

```json
    "task_factory": {
        "parametric_sweep": {
            "zip": ["abc", "012", "def"]
        }
    },
    "command": "/bin/bash -c \"echo {0}; echo {1}; echo {2}\""
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

## Configuration guide
Please see the [jobs configuration guide](14-batch-shipyard-configuration-jobs.md)
for more information on configuration for jobs and tasks.
