"""A/B comparison against the exact v0.1 rewrite algorithm.

Both workloads are synthetic. The mixed workload reproduces benchmark.py;
the structured workload intentionally exercises new commuting CX identities.
The old implementation here is a frozen comparison fixture, not an alternative
shipping optimizer.
"""
import argparse
import json
import math
import random
import time

from qforge import Circuit, Gate, optimize, compare, INVOLUTIONS, ROTATIONS


def v01_optimize(circuit):
    out = []
    for gate in circuit.gates:
        if gate.op in ROTATIONS and gate.angle == 0:
            continue
        support = set(gate.qubits)
        match = None
        for i in range(len(out) - 1, -1, -1):
            if support.intersection(out[i].qubits):
                if out[i].op == gate.op and out[i].qubits == gate.qubits:
                    match = i
                break
        if match is None:
            out.append(gate)
        elif gate.op in INVOLUTIONS:
            out.pop(match)
        else:
            combined = out[match].angle + gate.angle
            if not math.isfinite(combined):
                out.append(gate)
                continue
            out.pop(match)
            if combined != 0:
                out.append(Gate(gate.op, gate.qubits, combined))
    return Circuit(circuit.qubits, tuple(out))


def mixed_cases(seed, cases):
    rng = random.Random(seed)
    for _ in range(cases):
        gates = []
        for _ in range(25):
            op = rng.choice(('h', 'x', 'z', 'rx', 'rz', 'cx'))
            g = (Gate(op, tuple(rng.sample(range(3), 2))) if op == 'cx'
                 else Gate(op, (rng.randrange(3),), rng.uniform(-3, 3) if op in ('rx', 'rz') else None))
            gates.append(g)
            if rng.random() < .3:
                gates.append(Gate(op, g.qubits, -g.angle if g.angle is not None else None))
        yield Circuit(3, tuple(gates))


def structured_cases(seed, cases):
    rng = random.Random(seed)
    for _ in range(cases):
        n = 16
        gates = []
        for _ in range(40):
            ctrl, targ = rng.sample(range(n), 2)
            # Deliberately require a nontrivial CX commutation to simplify.
            axis = rng.choice(('rz', 'z', 'x'))
            if axis == 'rz':
                g = Gate('rz', (ctrl,), rng.uniform(-2.5, 2.5))
                inverse = Gate('rz', (ctrl,), -g.angle)
            elif axis == 'z':
                g = inverse = Gate('z', (ctrl,))
            else:
                g = inverse = Gate('x', (targ,))
            gates += [g, Gate('cx', (ctrl, targ)), inverse]
        yield Circuit(n, tuple(gates))


def run(name, circuits):
    before = old = new = verified = 0
    start = time.perf_counter()
    for c in circuits:
        old_c = v01_optimize(c)
        new_c, _ = optimize(c)
        before += len(c.gates)
        old += len(old_c.gates)
        new += len(new_c.gates)
        verified += bool(compare(c, new_c)['equivalent_up_to_global_phase'])
    elapsed = time.perf_counter() - start
    return {"workload": name, "input_gates": before, "v01_output_gates": old,
            "v02_output_gates": new, "additional_gates_removed": old - new,
            "verified_cases": verified, "cases": len(circuits), "seconds": round(elapsed, 3)}


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--seed', type=int, default=2026)
    p.add_argument('--cases', type=int, default=100)
    args = p.parse_args()
    if args.cases < 1:
        p.error('--cases must be positive')
    workloads = [("mixed_inverse_pairs", list(mixed_cases(args.seed, args.cases))),
                 ("structured_commuting_cx", list(structured_cases(args.seed, args.cases)))]
    results = [run(name, circuits) for name, circuits in workloads]
    print(json.dumps({'seed': args.seed, 'results': results,
                      'disclaimer': 'synthetic test workloads; not hardware benchmarks'}, indent=2))
    if any(r['verified_cases'] != r['cases'] for r in results):
        raise SystemExit(1)


if __name__ == '__main__':
    main()
