#!/usr/bin/env python3

# stdlib imports
import argparse
import copy
import datetime
import json
import os
import subprocess
import sys
# non-stdlib imports
import azure.storage.table as azuretable

# global defines
_STORAGEACCOUNT = os.getenv('STORAGEACCOUNT')
_STORAGEACCOUNTKEY = os.getenv('STORAGEACCOUNTKEY')
_BATCHACCOUNT = None
_POOLID = None
_PARTITION_KEY = None
_TABLE_NAME = None


def _create_credentials(config: dict):
    """Create authenticated clients
    :param dict config: configuration dict
    :rtype: azure.storage.table.TableService
    :return: table client
    """
    global _STORAGEACCOUNT, _STORAGEACCOUNTKEY, _BATCHACCOUNT, _POOLID, \
        _PARTITION_KEY, _TABLE_NAME
    ssel = config['credentials']['shipyard_storage']
    _STORAGEACCOUNT = config['credentials']['storage'][ssel]['account']
    _STORAGEACCOUNTKEY = config['credentials']['storage'][ssel]['account_key']
    _BATCHACCOUNT = config['credentials']['batch']['account']
    _POOLID = config['pool_specification']['id']
    _PARTITION_KEY = '{}${}'.format(_BATCHACCOUNT, _POOLID)
    _TABLE_NAME = config['storage_entity_prefix'] + 'perf'
    table_client = azuretable.TableService(
        account_name=_STORAGEACCOUNT,
        account_key=_STORAGEACCOUNTKEY,
        endpoint_suffix=config['credentials']['storage'][ssel]['endpoint'])
    return table_client


def _compute_delta_t(data, nodeid, event1, event1_pos, event2, event2_pos):
    # attempt to get directly recorded diff
    try:
        return data[nodeid][event2][event2_pos]['message']['diff']
    except (TypeError, KeyError):
        return (data[nodeid][event2][event2_pos]['timestamp'] -
                data[nodeid][event1][event1_pos]['timestamp']).total_seconds()


def _parse_message(event, msg):
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


def _diff_events(data, nodeid, event, end_event, timing, prefix, sizes=None):
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


def coalesce_data(table_client):
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
    for nodeid in data:
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
        data[nodeid]['start'] = data[
            nodeid]['nodeprep:start'][0]['timestamp'].timestamp()
        data[nodeid].pop('nodeprep:start')
        data[nodeid].pop('nodeprep:end')
        data[nodeid].pop('privateregistry:start', None)
        data[nodeid].pop('privateregistry:end', None)
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
    return data, sizes


def graph_data(data, sizes):
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
            'NodePrepStartTime NodeId DockerInstall PrivateRegistrySetup '
            'GlobalResourcesLoad TotalPull TotalSave TotalLoad '
            'TotalTorrent\n')
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
                '{0} {1} {2} {3} {4} {5:.5f} {6:.5f} {7:.5f} {8:.5f}\n'.format(
                    datetime.datetime.fromtimestamp(start).strftime(
                        '%Y-%m-%d-%H:%M:%S.%f'),
                    nodeid,
                    data[nodeid]['timing']['docker_install'],
                    data[nodeid]['timing']['private_registry_setup'],
                    data[nodeid]['timing']['global_resources_loaded'],
                    pull,
                    save,
                    load,
                    torrent))
            total_gr += data[nodeid]['timing']['global_resources_loaded']
    print('total gr: {} avg: {}'.format(total_gr, total_gr / len(data)))
    print('total acq: {} avg: {}'.format(total_ac, total_ac / len(data)))
    # create plot file
    plot_fname = _PARTITION_KEY.replace('$', '-') + '.plot'
    with open(plot_fname, 'w') as f:
        f.write('set terminal pngcairo enhanced transparent crop\n')
        f.write('set key top left outside horizontal autotitle columnhead\n')
        f.write('set xtics rotate by 45 right font ", 8"\n')
        f.write('set ytics\n')
        f.write('set xlabel "Node Prep Start Time"\n')
        f.write('set ylabel "Seconds"\n')
        f.write('set format x "%H:%M:%.3S"\n')
        f.write('set xdata time\n')
        f.write('set timefmt "%Y-%m-%d-%H:%M:%S"\n')
        f.write('set style fill solid border -1\n')
        f.write('set boxwidth {0:.5f} absolute\n'.format(
            (maxtime - mintime) / 100.0))
        f.write('plot "{}" using 1:($3+$4+$5) with boxes lc rgb "red", \\\n'.format(
            dat_fname))
        f.write('\t"" using 1:($3+$4) with boxes lc rgb "yellow", \\\n')
        f.write('\t"" using 1:3 with boxes lc rgb "green"\n')
    png_fname = _PARTITION_KEY.replace('$', '-') + '.png'
    subprocess.check_call(
        'gnuplot {} > {}'.format(plot_fname, png_fname), shell=True)


def merge_dict(dict1, dict2):
    """Recursively merge dictionaries: dict2 on to dict1. This differs
    from dict.update() in that values that are dicts are recursively merged.
    Note that only dict value types are merged, not lists, etc.

    Code adapted from:
    https://www.xormedia.com/recursively-merge-dictionaries-in-python/

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
    data, sizes = coalesce_data(table_client)
    graph_data(data, sizes)


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
