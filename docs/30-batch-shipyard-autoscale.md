# Batch Shipyard and Pool Autoscaling
The focus of this article is to describe the Azure Batch Pool autoscaling
feature and how Batch Shipyard exposes the functionality.

## Azure Batch Pool Autoscale
Azure Batch has the ability to automatically scale your pool up or down
depending upon criteria that you specify. Remember, that you are only charged
in Azure Batch for the compute resources that are used (e.g., VM hours,
disk and network egress), thus by automatically scaling your resources
on-demand, you can use Azure resources more efficiently and potentially
reduce your costs.

Azure Batch exposes metrics that can be queried as historical sample data.
These metrics include usage information such as CPU, memory and disk as well
as node counts and task counts. These metrics can then be used to determine
what the proper target node counts should be. The logic for what the target
node counts should be is expressed as an autoscale formula.

Azure Batch periodically evaluates an autoscale formula as specified by
the evaluation interval timespan which can be as frequent as every 5 minutes.
If the evaluated target node counts are different after evaluation, the
pool automatically resizes to these target node counts without any
intervention needed by the user.

For more information about Azure Batch Autoscale, please visit this
[document](https://docs.microsoft.com/en-us/azure/batch/batch-automatic-scaling).

## Batch Shipyard and Pool Autoscale
Batch Shipyard exposes pool autoscale functionality in the pool configuration
file under the property `autoscale`. There are two approaches to specifying
how to apply autoscale to a compute pool. Scenario-based autoscaling is
a simple way to specify autoscale for a pool without needing to be an expert
in creating an autoscale formula. There are named autoscale scenarios that
you can select from. Formula-based autoscaling is for users that want
to specify their own custom autoscale formula.

### Scenario-based Autoscaling
Scenario-based autoscaling allows you to pick from a set of common autoscale
scenarios and then Batch Shipyard automatically applies the appropriate
transformations to the formula to apply to your pool. These scenarios are:
* `active_tasks` will autoscale the pool using metrics for the number of
active (i.e., queued) tasks for the pool.
* `pending_tasks` will autoscale the pool using metrics for the number of
pending (i.e., active + running) tasks for the pool.
* `workday` will autoscale the pool according to Monday-Friday workdays.
* `workday_with_offpeak_max_low_priority` will autoscale the pool according
to Monday-Friday workdays and for off work time, use maximum number of
low priority nodes.
* `weekday` will autoscale the pool if it is a weekday.
* `weekend` will autoscale the pool if it is a weekend.

You can specify a scenario-based autoscale on a pool by populating the
property `autoscale`:`scenario`:`name` with one of the scenarios above.

You will also need to specify a `autoscale`:`scenario`:`maximum_vm_count`
property which can contain both `dedicated` and `low_priority` counts to
ensure that the formulas cannot evaluate to a target node count higher
than some threshold that you specify. Specifying a negative value for
the count will effectively set the maximum to no limit. Note that the
`vm_count` specified at the `pool_specification` level are automatically
inferred as minimum VM counts. These counts can be set to 0 to allow the
pool to resize down to zero nodes.

Additionally, there are options that can modify and fine-tune these scenarios
as needed:
* `node_deallocation_option` which specify when a node is targeted for
deallocation but has a running task, what should be the action applied to
the task: `requeue`, `terminate`, `taskcompletion`, and `retaineddata`.
Please see [this doc](https://docs.microsoft.com/en-us/azure/batch/batch-automatic-scaling#variables)
for more information about these options. This option applies to all scenarios.
* `sample_lookback_interval` is the time interval to lookback for past history
for certain scenarios such as autoscale based on active and pending tasks.
This option applies only to `active_tasks` and `pending_tasks` scenarios.
* `required_sample_percentage` is the required percentage of samples that
must be present during the `sample_lookback_interval`. This option applies
only to `active_tasks` and `pending_tasks` scenarios.
* `bias_last_sample` will bias the autoscale scenario to use the last sample
during history computation and metric weighting. This can be enabled to more
quickly respond to changes in history with respect to averages. This option
applies only to `active_tasks` and `pending_tasks` scenarios.
* `bias_node_type` will bias the the autoscale scenario to favor one type of
node over the other when making a decision on how many of each node to
allocate. By default, allocation is equal-weighted but can be selected to
favor either `dedicated` or `low_priority`. This applies to all scenarios.

An example autoscale specification in the pool configuration may be:
```json
        "autoscale": {
            "evaluation_interval": "00:05:00",
            "scenario": {
                "name": "active_tasks",
                "maximum_vm_count": {
                    "dedicated": 16,
                    "low_priority": 8
                }
            }
        }
```

This example would apply the `active_tasks` scenario to the associated
pool with an evaluation interval of every 5 minutes. This means that the
autoscale formula is evaluated by the service and can have updates applied
every 5 minutes. Note that having a small evaluation interval may result
in undesirable behavior of the pool being resized constantly (or even
resize failures if the prior resize is still ongoing when the autoscale
evaluation happens again and results in a different target node count).
The `active_tasks` scenario also includes a `maximum_vm_count` to ensure that
the autoscale formula does not result in target node counts that exceed
16 dedicated and 8 low priority nodes.

### Formula-based Autoscaling
Formula-based autoscaling allows users with expertise in creating autoscale
formulas to create their own formula and apply it to a Batch Shipyard pool.

For more information about how to create your own custom autoscale formula,
please visit this
[document](https://docs.microsoft.com/en-us/azure/batch/batch-automatic-scaling).
