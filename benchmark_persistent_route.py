"""Paired comparison of raw routers on deterministic synthetic circuits."""
from collections import defaultdict
from benchmark_qf02 import make_circuits
from qforge import compare
from qforge_compiler import route_line, route_line_persistent, metrics
import json


def main():
    summary = defaultdict(lambda: {'cases': 0, 'old_cx': 0, 'new_cx': 0, 'regressions': 0})
    for label, _, circuit in make_circuits(seed=7251, cases=50):
        old, _ = route_line(circuit)
        new, _ = route_line_persistent(circuit)
        if not compare(circuit, new)['equivalent_up_to_global_phase']:
            raise AssertionError('inequivalent routed circuit')
        a, b = metrics(old)['cx'], metrics(new)['cx']
        row = summary[label]
        row['cases'] += 1
        row['old_cx'] += a
        row['new_cx'] += b
        row['regressions'] += b > a
    print(json.dumps(dict(summary), indent=2))


if __name__ == '__main__':
    main()
