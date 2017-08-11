# Copyright (c) Microsoft Corporation
#
# All rights reserved.
#
# MIT License
#
# Permission is hereby granted, free of charge, to any person obtaining a
# copy of this software and associated documentation files (the "Software"),
# to deal in the Software without restriction, including without limitation
# the rights to use, copy, modify, merge, publish, distribute, sublicense,
# and/or sell copies of the Software, and to permit persons to whom the
# Software is furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED *AS IS*, WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
# FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
# DEALINGS IN THE SOFTWARE.

# compat imports
from __future__ import (
    absolute_import, division, print_function, unicode_literals
)
from builtins import (  # noqa
    bytes, dict, int, list, object, range, str, ascii, chr, hex, input,
    next, oct, open, pow, round, super, filter, map, zip)
# stdlib imports
import collections
# non-stdlib imports
# local imports
from . import util

# global defines
_UNBOUND_MAX_NODES = 16777216
AutoscaleMinMax = collections.namedtuple(
    'AutoscaleMinMax', [
        'max_tasks_per_node',
        'min_target_dedicated',
        'min_target_low_priority',
        'max_target_dedicated',
        'max_target_low_priority',
    ]
)


def _formula_tasks(pool):
    # type: (settings.PoolSettings) -> str
    """Generate an autoscale formula for tasks scenario
    :param settings.PoolSettings pool: pool settings
    :rtype: str
    :return: autoscale formula
    """
    minmax = _get_minmax(pool)
    if pool.autoscale.scenario.name == 'active_tasks':
        task_type = 'Active'
    elif pool.autoscale.scenario.name == 'pending_tasks':
        task_type = 'Pending'
    else:
        raise ValueError('autoscale scenario name invalid: {}'.format(
            pool.autoscale.scenario.name))
    if pool.autoscale.scenario.bias_last_sample:
        req_vms = [
            'sli = TimeInterval_Second * {}'.format(
                pool.autoscale.scenario.sample_lookback_interval.
                total_seconds()),
            'samplepercent = ${}Tasks.GetSamplePercent(sli)'.format(task_type),
            'lastsample = val(${}Tasks.GetSample(1), 0)'.format(task_type),
            'samplevecavg = avg(${}Tasks.GetSample(sli))'.format(task_type),
            ('{}TaskAvg = samplepercent < {} ? max(0, lastsample) : '
             '(lastsample < samplevecavg ? avg(lastsample, samplevecavg) : '
             'max(lastsample, samplevecavg))').format(
                 task_type,
                 pool.autoscale.scenario.required_sample_percentage,
            ),
            'reqVMs = {}TaskAvg / maxTasksPerNode'.format(task_type),
        ]
        if pool.autoscale.scenario.rebalance_preemption_percentage is not None:
            req_vms.extend([
                'preemptsamplepercent = '
                '$PreemptedNodeCount.GetSamplePercent(sli)',
                'lastpreemptsample = val($PreemptedNodeCount.GetSample(1), 0)',
                'preemptedavg = avg($PreemptedNodeCount.GetSample(sli))',
                ('preemptcount = preemptsamplepercent < {} ? '
                 'max(0, lastpreemptsample) : (lastpreemptsample > '
                 'preemptedavg ? avg(lastpreemptsample, preemptedavg) : '
                 'min(lastpreemptsample, preemptedavg))').format(
                     pool.autoscale.scenario.required_sample_percentage),
            ])
    else:
        req_vms = [
            'sli = TimeInterval_Second * {}'.format(
                pool.autoscale.scenario.sample_lookback_interval.
                total_seconds()),
            '{}TaskAvg = avg(${}Tasks.GetSample(sli, {}))'.format(
                task_type, task_type,
                pool.autoscale.scenario.required_sample_percentage),
            'reqVMs = {}TaskAvg / maxTasksPerNode'.format(task_type),
            'reqVMs = ({}TaskAvg > 0 && reqVMs < 1) ? 1 : reqVMs'.format(
                task_type),
        ]
        if pool.autoscale.scenario.rebalance_preemption_percentage is not None:
            req_vms.extend([
                'preemptcount = avg($PreemptedNodeCount.GetSample('
                'sli, {}))'.format(
                    pool.autoscale.scenario.required_sample_percentage),
            ])
    if pool.autoscale.scenario.rebalance_preemption_percentage is not None:
        req_vms.extend([
            'currenttotal = $CurrentDedicatedNodes + '
            '$CurrentLowPriorityNodes',
            'preemptedpercent = currenttotal > 0 ? '
            'preemptcount / currenttotal : 0',
            'rebalance = preemptedpercent >= {}'.format(
                pool.autoscale.scenario.rebalance_preemption_percentage),
        ])
    else:
        req_vms.extend([
            'preemptcount = 0',
            'rebalance = 0 == 1',
        ])
    req_vms = ';\n'.join(req_vms)
    if pool.autoscale.scenario.bias_node_type == 'auto':
        target_vms = [
            'divisor = (maxTargetDedicated == 0 || '
            'maxTargetLowPriority == 0) ? 1 : 2',
            'dedicatedVMs = max(minTargetDedicated, reqVMs / divisor)',
            'dedicatedVMs = min(maxTargetDedicated, '
            '(dedicatedVMs > 0 && dedicatedVMs < 1) ? 1 : dedicatedVMs)',
            'remainingVMs = reqVMs - dedicatedVMs',
            'redistVMs = rebalance ? '
            'min(preemptcount, remainingVMs) : 0',
            'dedicatedVMs = min(maxTargetDedicated, dedicatedVMs + redistVMs)',
            'lowPriVMs = min(maxTargetLowPriority, reqVMs - dedicatedVMs)',
            '$TargetDedicatedNodes = dedicatedVMs',
            '$TargetLowPriorityNodes = max(minTargetLowPriority, lowPriVMs)',
        ]
    elif pool.autoscale.scenario.bias_node_type == 'dedicated':
        target_vms = [
            'dedicatedVMs = min(maxTargetDedicated, '
            'max(minTargetDedicated, reqVMs))',
            '$TargetDedicatedNodes = dedicatedVMs',
            '$TargetLowPriorityNodes = max(minTargetLowPriority, '
            'min(maxTargetLowPriority, reqVMs - dedicatedVMs))',
        ]
    elif pool.autoscale.scenario.bias_node_type == 'low_priority':
        target_vms = [
            'lowPriVMs = min(maxTargetLowPriority, '
            'max(minTargetLowPriority, reqVMs))',
            'remainingVMs = min(maxTargetDedicated, reqVMs - lowPriVMs)',
            'redistVMs = rebalance ? '
            'min(preemptcount, lowPriVMs) : 0',
            'lowPriVMs = min(maxTargetLowPriority, '
            'max(minTargetLowPriority, max(0, reqVMs - redistVMs)))',
            'remainingVMs = min(maxTargetDedicated, reqVMs - lowPriVMs)',
            '$TargetLowPriorityNodes = lowPriVMs',
            '$TargetDedicatedNodes = max(minTargetDedicated, remainingVMs)',
        ]
    else:
        raise ValueError(
            'autoscale scenario bias node type invalid: {}'.format(
                pool.autoscale.scenario.bias_node_type))
    target_vms = ';\n'.join(target_vms)
    formula = [
        'maxTasksPerNode = {}'.format(minmax.max_tasks_per_node),
        'minTargetDedicated = {}'.format(minmax.min_target_dedicated),
        'minTargetLowPriority = {}'.format(minmax.min_target_low_priority),
        'maxTargetDedicated = {}'.format(minmax.max_target_dedicated),
        'maxTargetLowPriority = {}'.format(minmax.max_target_low_priority),
        req_vms,
        target_vms,
        '$NodeDeallocationOption = {}'.format(
            pool.autoscale.scenario.node_deallocation_option),
    ]
    return ';\n'.join(formula) + ';'


def _formula_day_of_week(pool):
    # type: (settings.PoolSettings) -> str
    """Generate an autoscale formula for a day of the week scenario
    :param settings.PoolSettings pool: pool settings
    :rtype: str
    :return: autoscale formula
    """
    minmax = _get_minmax(pool)
    if pool.autoscale.scenario.name == 'workday':
        target_vms = [
            'now = time()',
            'isWorkHours = now.hour >= 8 && now.hour < 18',
            'isWeekday = now.weekday >= 1 && now.weekday <= 5',
            'isPeakTime = isWeekday && isWorkHours',
        ]
    elif (pool.autoscale.scenario.name ==
          'workday_with_offpeak_max_low_priority'):
        target_vms = [
            'now = time()',
            'isWorkHours = now.hour >= 8 && now.hour < 18',
            'isWeekday = now.weekday >= 1 && now.weekday <= 5',
            'isPeakTime = isWeekday && isWorkHours',
            '$TargetLowPriorityNodes = maxTargetLowPriority',
        ]
        if pool.autoscale.scenario.bias_node_type == 'low_priority':
            target_vms.append('$TargetDedicatedNodes = minTargetDedicated')
        else:
            target_vms.append(
                '$TargetDedicatedNodes = isPeakTime ? '
                'maxTargetDedicated : minTargetDedicated')
    elif pool.autoscale.scenario.name == 'weekday':
        target_vms = [
            'now = time()',
            'isPeakTime = now.weekday >= 1 && now.weekday <= 5',
        ]
    elif pool.autoscale.scenario.name == 'weekend':
        target_vms = [
            'now = time()',
            'isPeakTime = now.weekday >= 6 && now.weekday <= 7',
        ]
    else:
        raise ValueError('autoscale scenario name invalid: {}'.format(
            pool.autoscale.scenario.name))
    if pool.autoscale.scenario.name != 'workday_with_offpeak_max_low_priority':
        if pool.autoscale.scenario.bias_node_type == 'auto':
            target_vms.append(
                '$TargetDedicatedNodes = isPeakTime ? '
                'maxTargetDedicated : minTargetDedicated')
            target_vms.append(
                '$TargetLowPriorityNodes = isPeakTime ? '
                'maxTargetLowPriority : minTargetLowPriority')
        elif pool.autoscale.scenario.bias_node_type == 'dedicated':
            target_vms.append(
                '$TargetDedicatedNodes = isPeakTime ? '
                'maxTargetDedicated : minTargetDedicated')
            target_vms.append('$TargetLowPriorityNodes = minTargetLowPriority')
        elif pool.autoscale.scenario.bias_node_type == 'low_priority':
            target_vms.append('$TargetDedicatedNodes = minTargetDedicated')
            target_vms.append(
                '$TargetLowPriorityNodes = isPeakTime ? '
                'maxTargetLowPriority : minTargetLowPriority')
        else:
            raise ValueError(
                'autoscale scenario bias node type invalid: {}'.format(
                    pool.autoscale.scenario.bias_node_type))
    target_vms = ';\n'.join(target_vms)
    formula = [
        'maxTasksPerNode = {}'.format(minmax.max_tasks_per_node),
        'minTargetDedicated = {}'.format(minmax.min_target_dedicated),
        'minTargetLowPriority = {}'.format(minmax.min_target_low_priority),
        'maxTargetDedicated = {}'.format(minmax.max_target_dedicated),
        'maxTargetLowPriority = {}'.format(minmax.max_target_low_priority),
        target_vms,
        '$NodeDeallocationOption = {}'.format(
            pool.autoscale.scenario.node_deallocation_option),
    ]
    return ';\n'.join(formula) + ';'


def _get_minmax(pool):
    # type: (settings.PoolSettings) -> AutoscaleMinMax
    """Get the min/max settings for autoscale spec
    :param settings.PoolSettings pool: pool settings
    :rtype: AutoscaleMinMax
    :return: autoscale min max object
    """
    min_target_dedicated = pool.vm_count.dedicated
    min_target_low_priority = pool.vm_count.low_priority
    max_target_dedicated = pool.autoscale.scenario.maximum_vm_count.dedicated
    if max_target_dedicated < 0:
        max_target_dedicated = _UNBOUND_MAX_NODES
    max_target_low_priority = (
        pool.autoscale.scenario.maximum_vm_count.low_priority
    )
    if max_target_low_priority < 0:
        max_target_low_priority = _UNBOUND_MAX_NODES
    if min_target_dedicated > max_target_dedicated:
        raise ValueError(
            'min target dedicated {} > max target dedicated {}'.format(
                min_target_dedicated, max_target_dedicated))
    if min_target_low_priority > max_target_low_priority:
        raise ValueError(
            'min target low priority {} > max target low priority {}'.format(
                min_target_low_priority, max_target_low_priority))
    return AutoscaleMinMax(
        max_tasks_per_node=pool.max_tasks_per_node,
        min_target_dedicated=min_target_dedicated,
        min_target_low_priority=min_target_low_priority,
        max_target_dedicated=max_target_dedicated,
        max_target_low_priority=max_target_low_priority,
    )


_AUTOSCALE_SCENARIOS = {
    'active_tasks': _formula_tasks,
    'pending_tasks': _formula_tasks,
    'workday': _formula_day_of_week,
    'workday_with_offpeak_max_low_priority': _formula_day_of_week,
    'weekday': _formula_day_of_week,
    'weekend': _formula_day_of_week,
}


def get_formula(pool):
    # type: (settings.PoolSettings) -> str
    """Get or generate an autoscale formula according to settings
    :param settings.PoolSettings pool: pool settings
    :rtype: str
    :return: autoscale formula
    """
    if util.is_not_empty(pool.autoscale.formula):
        return pool.autoscale.formula
    else:
        return _AUTOSCALE_SCENARIOS[pool.autoscale.scenario.name](pool)
