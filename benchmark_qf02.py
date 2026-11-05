"""QF-02 reproducible synthetic compiler evaluation; not a hardware/SOTA benchmark.

Reports raw paired samples, verification and environment. Intentionally contains
rewrite-friendly cases. No selection using evaluation outputs.
"""
import argparse
import json
import math
import os
from pathlib import Path
import platform
import random
import statistics
import time

from qforge import Circuit, Gate, compare
from qforge_compiler import compile_circuit, metrics


def make_circuits(seed, cases):
    rng = random.Random(seed)
    specs = (('mixed_4q', 4, 35, ('h','x','z','rx','rz','cx')),
             ('routing_5q', 5, 30, ('h','x','rz','cx','cx','cx')),
             ('affine_20q', 20, 70, ('x','z','rz','cx','cx')))
    for label, n, length, ops in specs:
        for case in range(cases):
            gates = []
            for _ in range(length):
                op = rng.choice(ops)
                if op == 'cx':
                    q = tuple(rng.sample(range(n), 2))
                    g = Gate(op, q)
                else:
                    q = (rng.randrange(n),)
                    g = Gate(op,q,rng.uniform(-2,2) if op in ('rx','rz') else None)
                gates.append(g)
                if rng.random() < .22:
                    inverse = Gate(op,q,-g.angle if g.angle is not None else None)
                    gates.append(inverse)
            yield label, case, Circuit(n,tuple(gates))


def run(seed=2026, cases=50):
    rows = []
    for workload, case, original in make_circuits(seed, cases):
        for topology in ('all','line'):
            t0 = time.perf_counter_ns()
            compiled, report = compile_circuit(original,topology=topology,verify=False)
            t1 = time.perf_counter_ns()
            verification = compare(original,compiled)
            t2 = time.perf_counter_ns()
            row = {'workload':workload,'case':case,'topology':topology,
                   'before':metrics(original),'after':metrics(compiled),
                   'verified':bool(verification['equivalent_up_to_global_phase']),
                   'verify_method':verification['method'],
                   'compile_ms':(t1-t0)/1e6,'verify_ms':(t2-t1)/1e6,
                   'passes':report['passes']}
            rows.append(row)
    aggregates = []
    for workload in ('mixed_4q','routing_5q','affine_20q'):
        for topology in ('all','line'):
            r = [row for row in rows if row['workload']==workload and row['topology']==topology]
            aggregates.append({'workload':workload,'topology':topology,'circuits':len(r),
                  'input_gates':sum(x['before']['gates'] for x in r),
                  'output_gates':sum(x['after']['gates'] for x in r),
                  'input_cx':sum(x['before']['cx'] for x in r),
                  'output_cx':sum(x['after']['cx'] for x in r),
                  'mean_input_depth':round(statistics.mean(x['before']['depth'] for x in r),2),
                  'mean_output_depth':round(statistics.mean(x['after']['depth'] for x in r),2),
                  'verified':sum(x['verified'] for x in r),
                  'compile_ms_median':round(statistics.median(x['compile_ms'] for x in r),3),
                  'verify_ms_median':round(statistics.median(x['verify_ms'] for x in r),3)})
    return {'suite':'QF-02 synthetic seeded compilation', 'seed':seed,'cases_per_workload':cases,
            'environment':{'python':platform.python_version(),'platform':platform.platform(),
                           'processor':platform.processor(),'cpu_count':os.cpu_count()},
            'disclaimer':'Synthetic inputs include injected inverse pairs; not real circuit/SOTA results. Routing increases gate count to satisfy line adjacency.',
            'summary':aggregates,'samples':rows}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--seed',type=int,default=2026)
    parser.add_argument('--cases',type=int,default=50)
    parser.add_argument('--output',type=Path,default=Path('qf02-benchmark.json'))
    args=parser.parse_args()
    if not 1<=args.cases<=10000: parser.error('cases must be between 1 and 10000')
    report=run(args.seed,args.cases)
    args.output.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    print(json.dumps({'output':str(args.output),'summary':report['summary']},indent=2))
    return 0 if all(x['verified']==x['circuits'] for x in report['summary']) else 1

if __name__=='__main__': raise SystemExit(main())
