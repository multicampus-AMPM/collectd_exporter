from prometheus_client.core import GaugeMetricFamily, CounterMetricFamily
from datetime import datetime, timedelta
import re
from threading import Thread
from threading import RLock


def new_name(vl, idx):
    if vl['plugin'] == vl['type']:
        name = 'collectd_' + vl['type']
    else:
        name = 'collectd_' + vl['plugin'] + '_' + vl['type']
    if vl['dsnames'][idx] != 'value':
        name += '_' + vl['dsnames'][idx]
    if vl['dstypes'][idx] == 'derive' or vl['dstypes'][idx] == 'counter':
        name += '_total'
    return re.sub(r"[^a-zA-Z0-9_:]", "_", name)


def new_label(vl):
    labels = dict()
    if vl['plugin_instance'] != "":
        labels[vl['plugin']] = vl['plugin_instance']
    if vl['type_instance'] != "":
        if vl['plugin_instance'] == "":
            labels[vl['plugin']] = vl['type_instance']
        else:
            labels["type"] = vl['type_instance']
    labels['instance'] = vl['host']
    return labels


def new_desc(vl, idx):
    return f"Collectd_exporter: '{vl['plugin']}'  Type: '{vl['type']}' Dstype: '{vl['dstypes'][idx]}' Dsname: '{vl['dsnames'][idx]}'"


def new_metric(vl, idx, wrapper):
    name = new_name(vl, idx)
    labels = new_label(vl)
    try:
        metric = wrapper[name]
    except KeyError:
        desc = new_desc(vl, idx)
        dstype = vl['dstypes'][idx]
        if dstype == 'gauge':
            wrapper[name] = GaugeMetricFamily(name=name, documentation=desc, labels=labels.keys())
        elif dstype == 'derive' or dstype == 'counter':
            wrapper[name] = CounterMetricFamily(name=name, documentation=desc, labels=labels.keys())
        metric = wrapper[name]
    metric.add_metric(labels.values(), vl['values'][idx])


def make_identifier(vl):
    vl_id = f"{vl['host']}/{vl['plugin']}"
    if vl['plugin_instance'] != '':
        vl_id += '-' + vl['plugin_instance']
    vl_id += '/' + vl['type']
    if vl['type_instance'] != '':
        vl_id += '-' + vl['type_instance']
    return vl_id


class CollectdExporter(object):
    """ Convertor data from collectd to metrics which prometheus supports """

    timeout = 2

    def __init__(self, collector):
        self.collector = collector

    def collect(self):
        value_lists = self.collector.get_value_lists()
        wrapper = dict()
        now = datetime.now()
        for vl_id in value_lists:
            vl = value_lists[vl_id]
            time = datetime.fromtimestamp(float(vl['time']))
            valid_until = time + timedelta(seconds=(CollectdExporter.timeout * vl['interval']))
            if valid_until < now :
                continue
            for idx in range(len(vl['values'])):
                new_metric(vl, idx, wrapper)
        for metric in wrapper:
            yield wrapper[metric]


class CollectdCollector(Thread):
    """ Thread to hold data from collectd """

    def __init__(self, group=None, target=None, name=None, args=None, *kwargs, daemon=None):
        super().__init__(group=group, target=target, name=name, args=args, kwargs=kwargs, daemon=daemon)
        self.value_lists = dict()
        self.lock = RLock()

    def run(self):
        print(" * CollectdCollector Starts.")

    def set_value_lists(self, value_list):
        with self.lock:
            # TODO : 시간 지난값 value_lists에서 삭제 필요한지 확인
            for vl in value_list:
                id = make_identifier(vl)
                self.value_lists[id] = vl

    def get_value_lists(self):
        with self.lock:
            value_lists = self.value_lists.copy()
        return value_lists