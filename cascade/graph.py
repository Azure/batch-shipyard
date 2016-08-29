#!/usr/bin/env python3

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

# stdlib imports
import argparse
import copy
import datetime
import json
import subprocess
import sys
# non-stdlib imports
import azure.storage.table as azuretable

# global defines
_PARTITION_KEY = None
_TABLE_NAME = None


def _create_credentials(config: dict) -> azuretable.TableService:
    """Create authenticated clients
    :param dict config: configuration dict
    :rtype: azure.storage.table.TableService
    :return: table client
    """
    global _PARTITION_KEY, _TABLE_NAME
    _PARTITION_KEY = '{}${}'.format(
        config['credentials']['batch']['account'],
        config['pool_specification']['id'])
    _TABLE_NAME = config['storage_entity_prefix'] + 'perf'
    ssel = config['credentials']['shipyard_storage']
    table_client = azuretable.TableService(
        account_name=config['credentials']['storage'][ssel]['account'],
        account_key=config['credentials']['storage'][ssel]['account_key'],
        endpoint_suffix=config['credentials']['storage'][ssel]['endpoint'])
    return table_client


def _compute_delta_t(
        data: dict, nodeid: str, event1: str, event1_pos: int, event2: str,
        event2_pos: int) -> float:
    """Compute time delta between two events
    :param dict data: data
    :param str nodeid: node id
    :param str event1: event1
    :param int event1_pos: event1 position in stream
    :param str event2: event2
    :param int event2_pos: event2 position in stream
    :rtype: float
    :return: delta t of events
    """
    # attempt to get directly recorded diff
    try:
        return data[nodeid][event2][event2_pos]['message']['diff']
    except (TypeError, KeyError):
        return (data[nodeid][event2][event2_pos]['timestamp'] -
                data[nodeid][event1][event1_pos]['timestamp']).total_seconds()


def _parse_message(event: str, msg: str) -> dict:
    """Parse message
    :param str event: event
    :param str msg: message
    :rtype: dict
    :return: dict of message entries
    """
    parts = msg.split(',')
    m = {}
    for part in parts:
        tmp = part.split('=')
        if tmp[0] == 'size':
            if event == 'cascade:pull-end':
                sz = tmp[1].split()
                sz[0] = float(sz[0])
                if sz[1] == 'kB':
                    sz[0] *= 1024
                elif sz[1] == 'MB':
                    sz[0] *= 1024 * 1024
                elif sz[1] == 'GB':
                    sz[0] *= 1024 * 1024 * 1024
                elif sz[1] == 'TB':
                    sz[0] *= 1024 * 1024 * 1024 * 1024
                tmp[1] = sz[0]
            m[tmp[0]] = int(tmp[1])
        elif tmp[0] == 'nglobalresources':
            m[tmp[0]] = int(tmp[1])
        elif tmp[0] == 'diff':
            m[tmp[0]] = float(tmp[1])
        else:
            m[tmp[0]] = tmp[1]
    return m


def _diff_events(
        data: dict, nodeid: str, event: str, end_event: str, timing: dict,
        prefix: str, sizes: dict=None) -> None:
    """Diff start and end event
    :param dict data: data
    :param str nodeid: node id
    :param str event: start event
    :param str end_event: end event
    :param dict timing: timing dict
    :param str prefix: prefix
    :param dict sizes: sizes dict
    """
    for i in range(0, len(data[nodeid][event])):
        # torrent start -> load start may not always exist due to pull
        if (event == 'cascade:torrent-start' and
                end_event == 'cascade:load-start' and
                end_event not in data[nodeid]):
            return
        # find end event for this img
        subevent = data[nodeid][event][i]
        img = subevent['message']['img']
        found = False
        for j in range(0, len(data[nodeid][end_event])):
            pei = data[
                nodeid][end_event][j]['message']['img']
            if pei == img:
                timing[prefix + img] = _compute_delta_t(
                    data, nodeid, event, i, end_event, j)
                if sizes is not None and img not in sizes:
                    try:
                        if event == 'cascade:load-start':
                            sizes[img] = data[
                                nodeid][event][j]['message']['size']
                        else:
                            sizes[img] = data[
                                nodeid][end_event][j]['message']['size']
                    except KeyError:
                        pass
                found = True
                break
        if not found and event != 'cascade:torrent-start':
            raise RuntimeError(
                'could not find corresponding event for {}:{}'.format(
                    event, img))


def coalesce_data(table_client: azuretable.TableService) -> tuple:
    """Coalesce perf data from table
    :param azure.storage.table.TableService table_client: table client
    :rtype: tuple
    :return: (timing, sizes, offer, sku)
    """
    print('graphing data from {} with pk={}'.format(
        _TABLE_NAME, _PARTITION_KEY))
    entities = table_client.query_entities(
        _TABLE_NAME, filter='PartitionKey eq \'{}\''.format(_PARTITION_KEY))
    data = {}
    # process events
    for ent in entities:
        nodeid = ent['NodeId']
        event = ent['Event']
        if nodeid not in data:
            data[nodeid] = {}
        if event not in data[nodeid]:
            data[nodeid][event] = []
        ev = {
            'timestamp': datetime.datetime.fromtimestamp(
                float(ent['RowKey'])),
        }
        try:
            ev['message'] = _parse_message(event, ent['Message'])
        except KeyError:
            ev['message'] = None
        data[nodeid][event].append(ev)
    del entities
    sizes = {}
    offer = None
    sku = None
    for nodeid in data:
        if offer is None:
            offer = data[nodeid]['nodeprep:start'][0]['message']['offer']
            sku = data[nodeid]['nodeprep:start'][0]['message']['sku']
        # calculate dt timings
        timing = {
            'nodeprep': _compute_delta_t(
                data, nodeid, 'nodeprep:start', 0, 'nodeprep:end', 0),
            'global_resources_loaded': _compute_delta_t(
                data, nodeid, 'cascade:start', 0, 'cascade:gr-done', 0),
        }
        try:
            timing['docker_install'] = _compute_delta_t(
                data, nodeid, 'nodeprep:start', 0, 'privateregistry:start', 0)
        except KeyError:
            # when no private registry setup exists, install time is
            # equivalent to nodeprep time
            timing['docker_install'] = timing['nodeprep']
        try:
            timing['private_registry_setup'] = _compute_delta_t(
                data, nodeid, 'privateregistry:start', 0,
                'privateregistry:end', 0)
        except KeyError:
            timing['private_registry_setup'] = 0
        try:
            timing['docker_shipyard_container_pull'] = _compute_delta_t(
                data, nodeid, 'shipyard:pull-start', 0,
                'shipyard:pull-end', 0)
        except KeyError:
            timing['docker_shipyard_container_pull'] = 0
        data[nodeid]['start'] = data[
            nodeid]['nodeprep:start'][0]['timestamp'].timestamp()
        data[nodeid].pop('nodeprep:start')
        data[nodeid].pop('nodeprep:end')
        data[nodeid].pop('privateregistry:start', None)
        data[nodeid].pop('privateregistry:end', None)
        data[nodeid].pop('shipyard:pull-start', None)
        data[nodeid].pop('shipyard:pull-end', None)
        data[nodeid].pop('cascade:start')
        data[nodeid].pop('cascade:gr-done')
        for event in data[nodeid]:
            # print(event, data[nodeid][event])
            if event == 'cascade:pull-start':
                _diff_events(
                    data, nodeid, event, 'cascade:pull-end', timing, 'pull:',
                    sizes)
            elif event == 'cascade:save-start':
                _diff_events(
                    data, nodeid, event, 'cascade:save-end', timing, 'save:',
                    sizes)
            elif event == 'cascade:torrent-start':
                _diff_events(
                    data, nodeid, event, 'cascade:load-start', timing,
                    'torrent:')
            elif event == 'cascade:load-start':
                _diff_events(
                    data, nodeid, event, 'cascade:load-end', timing,
                    'load:', sizes)
        data[nodeid].pop('cascade:pull-start', None)
        data[nodeid].pop('cascade:pull-end', None)
        data[nodeid].pop('cascade:save-start', None)
        data[nodeid].pop('cascade:save-end', None)
        data[nodeid].pop('cascade:torrent-start', None)
        data[nodeid].pop('cascade:load-start', None)
        data[nodeid].pop('cascade:load-end', None)
        data[nodeid]['timing'] = timing
    return data, sizes, offer, sku


def graph_data(data: dict, sizes: dict, offer: str, sku: str):
    """Graph data via gnuplot
    :param dict data: timing data
    :param dict sizes: size data
    :param str offer: offer
    :param str sku: sku
    """
    print(sizes)
    # create data file
    dat_fname = _PARTITION_KEY.replace('$', '-') + '.dat'
    mintime = float(sys.maxsize)
    maxtime = 0.0
    rdata = {}
    for nodeid in data:
        start = data[nodeid]['start']
        if start in rdata:
            raise RuntimeError('cannot create reverse mapping')
        rdata[start] = nodeid
        if start < mintime:
            mintime = start
        if start > maxtime:
            maxtime = start
    print('delta:', maxtime - mintime)
    total_gr = 0
    total_ac = 0
    with open(dat_fname, 'w') as f:
        f.write(
            'NodePrepStartTime NodeId NodePrep+DockerInstall '
            'PrivateRegistrySetup ShipyardContainerPull GlobalResourcesLoad '
            'TotalPull TotalSave TotalLoad TotalTorrent\n')
        for start in sorted(rdata):
            nodeid = rdata[start]
            pull = 0
            save = 0
            load = 0
            torrent = 0
            for event in data[nodeid]['timing']:
                if event.startswith('pull:'):
                    pull += data[nodeid]['timing'][event]
                elif event.startswith('save:'):
                    save += data[nodeid]['timing'][event]
                elif event.startswith('load:'):
                    load += data[nodeid]['timing'][event]
                elif event.startswith('torrent:'):
                    torrent += data[nodeid]['timing'][event]
            acquisition = pull + torrent + load
            total_ac += acquisition
            print(nodeid, data[nodeid]['timing'])
            f.write(
                ('{0} {1} {2} {3} {4} {5} {6:.5f} {7:.5f} {8:.5f} '
                 '{9:.5f}\n').format(
                     datetime.datetime.fromtimestamp(start).strftime(
                         '%Y-%m-%d-%H:%M:%S.%f'),
                     nodeid,
                     data[nodeid]['timing']['docker_install'],
                     data[nodeid]['timing']['private_registry_setup'],
                     data[nodeid]['timing']['docker_shipyard_container_pull'],
                     data[nodeid]['timing']['global_resources_loaded'],
                     pull,
                     save,
                     load,
                     torrent)
            )
            total_gr += data[nodeid]['timing']['global_resources_loaded']
    print('total gr: {} avg: {}'.format(total_gr, total_gr / len(data)))
    print('total acq: {} avg: {}'.format(total_ac, total_ac / len(data)))
    # create plot file
    plot_fname = _PARTITION_KEY.replace('$', '-') + '.plot'
    with open(plot_fname, 'w') as f:
        f.write('set terminal pngcairo enhanced transparent crop\n')
        f.write(
            ('set title "Shipyard Performance for {} ({} {})" '
             'font ", 10" \n').format(
                 _PARTITION_KEY.split('$')[-1], offer, sku))
        f.write(
            'set key top right horizontal autotitle columnhead '
            'font ", 7"\n')
        f.write('set xtics rotate by 45 right font ", 7"\n')
        f.write('set ytics font ", 8"\n')
        f.write('set xlabel "Node Prep Start Time" font ", 8"\n')
        f.write('set ylabel "Seconds" font ", 8"\n')
        f.write('set format x "%H:%M:%.3S"\n')
        f.write('set xdata time\n')
        f.write('set timefmt "%Y-%m-%d-%H:%M:%S"\n')
        f.write('set style fill solid\n')
        f.write('set boxwidth {0:.5f} absolute\n'.format(
            (maxtime - mintime) / 100.0))
        f.write('plot "{}" using 1:($3+$4+$5+$6) with boxes, \\\n'.format(
            dat_fname))
        f.write('\t"" using 1:($3+$4+$5) with boxes, \\\n')
        f.write('\t"" using 1:($3+$4) with boxes, \\\n')
        f.write('\t"" using 1:3 with boxes\n')
    png_fname = _PARTITION_KEY.replace('$', '-') + '.png'
    subprocess.check_call(
        'gnuplot {} > {}'.format(plot_fname, png_fname), shell=True)


def merge_dict(dict1: dict, dict2: dict) -> dict:
    """Recursively merge dictionaries: dict2 on to dict1. This differs
    from dict.update() in that values that are dicts are recursively merged.
    Note that only dict value types are merged, not lists, etc.

    :param dict dict1: dictionary to merge to
    :param dict dict2: dictionary to merge with
    :rtype: dict
    :return: merged dictionary
    """
    if not isinstance(dict1, dict) or not isinstance(dict2, dict):
        raise ValueError('dict1 or dict2 is not a dictionary')
    result = copy.deepcopy(dict1)
    for k, v in dict2.items():
        if k in result and isinstance(result[k], dict):
            result[k] = merge_dict(result[k], v)
        else:
            result[k] = copy.deepcopy(v)
    return result


def main():
    """Main function"""
    # get command-line args
    args = parseargs()

    if args.credentials is None:
        raise ValueError('credentials json not specified')
    if args.config is None:
        raise ValueError('config json not specified')

    with open(args.credentials, 'r') as f:
        config = json.load(f)
    with open(args.config, 'r') as f:
        config = merge_dict(config, json.load(f))
    with open(args.pool, 'r') as f:
        config = merge_dict(config, json.load(f))

    # create storage credentials
    table_client = _create_credentials(config)
    # graph data
    data, sizes, offer, sku = coalesce_data(table_client)
    graph_data(data, sizes, offer, sku)


def parseargs():
    """Parse program arguments
    :rtype: argparse.Namespace
    :return: parsed arguments
    """
    parser = argparse.ArgumentParser(
        description='Shipyard perf graph generator')
    parser.add_argument(
        '--credentials', help='credentials json config')
    parser.add_argument(
        '--config', help='general json config for option')
    parser.add_argument(
        '--pool', help='pool json config')
    return parser.parse_args()

if __name__ == '__main__':
    main()
