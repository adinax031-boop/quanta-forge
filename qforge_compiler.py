"""Reproducible pass pipeline, conservative topology routing, and metrics."""
from __future__ import annotations
from collections import Counter
from dataclasses import dataclass
from typing import Callable
from qforge import Circuit, Gate, compare, optimize

MAX_ROUTED_GATES = 250_000


@dataclass(frozen=True)
class PassResult:
    name: str
    before: dict
    after: dict
    details: dict


def metrics(circuit: Circuit) -> dict:
    """Logical gate and ASAP depth counts; not calibrated device latency."""
    counts = Counter(g.op for g in circuit.gates)
    per_qubit = [0] * circuit.qubits
    for gate in circuit.gates:
        level = 1 + max(per_qubit[q] for q in gate.qubits)
        for q in gate.qubits:
            per_qubit[q] = level
    return {'qubits': circuit.qubits, 'gates': len(circuit.gates),
            'cx': counts['cx'], 'single_qubit': len(circuit.gates) - counts['cx'],
            'depth': max(per_qubit, default=0),
            'gate_counts': dict(sorted(counts.items()))}


def route_line(circuit: Circuit) -> tuple[Circuit, dict]:
    """Move the control along a line, CX adjacent, then restore logical layout.

    Every physical CX has |control-target|==1. This is conservative and can
    increase gate count enormously; no claim of optimal placement is made.
    """
    out: list[Gate] = []
    swap_count = 0
    remote_count = 0
    predicted = sum((6 * (abs(g.qubits[0] - g.qubits[1]) - 1) + 1) if g.op == 'cx' else 1 for g in circuit.gates)
    if predicted > MAX_ROUTED_GATES:
        raise ValueError(f'line routing would emit {predicted} gates; limit {MAX_ROUTED_GATES}')
    def swap(a, b):
        nonlocal swap_count
        out.extend((Gate('cx', (a, b)), Gate('cx', (b, a)), Gate('cx', (a, b))))
        swap_count += 1
    for gate in circuit.gates:
        if gate.op != 'cx' or abs(gate.qubits[0] - gate.qubits[1]) == 1:
            out.append(gate)
            continue
        remote_count += 1
        control, target = gate.qubits
        step = 1 if target > control else -1
        edges = [(q, q + step) for q in range(control, target - step, step)]
        for a, b in edges: swap(a, b)
        out.append(Gate('cx', (target - step, target)))
        for a, b in reversed(edges): swap(a, b)
    result = Circuit(circuit.qubits, tuple(out))
    return result, {'remote_cx_routed': remote_count, 'swaps_inserted': swap_count}


def route_line_persistent(circuit: Circuit) -> tuple[Circuit, dict]:
    """Route on a line, tracking swaps and restoring the final wire layout."""
    out = []
    logical_at = list(range(circuit.qubits))
    physical_of = list(range(circuit.qubits))
    swaps = 0
    def emit(g):
        if len(out) >= MAX_ROUTED_GATES:
            raise ValueError('line routing exceeds gate limit')
        out.append(g)
    def swap(a, b):
        nonlocal swaps
        for x, y in ((a,b), (b,a), (a,b)):
            emit(Gate('cx', (x,y)))
        la, lb = logical_at[a], logical_at[b]
        logical_at[a], logical_at[b] = lb, la
        physical_of[la], physical_of[lb] = b, a
        swaps += 1
    for gate in circuit.gates:
        qs = gate.qubits
        if gate.op == 'cx':
            control, target = physical_of[qs[0]], physical_of[qs[1]]
            step = 1 if target > control else -1
            while abs(target - control) > 1:
                swap(control, control + step)
                control += step
            emit(Gate('cx', (control, target)))
        else:
            emit(Gate(gate.op, tuple(physical_of[q] for q in qs), gate.angle))
    for dest in range(circuit.qubits):
        pos = physical_of[dest]
        while pos > dest:
            swap(pos - 1, pos)
            pos -= 1
    return Circuit(circuit.qubits, tuple(out)), {'swaps_inserted': swaps, 'final_layout': 'identity'}


def route_line_best(circuit: Circuit) -> tuple[Circuit, dict]:
    """Choose the smaller raw routed circuit, falling back if one exceeds its cap."""
    candidates = []
    for name, router in (('persistent', route_line_persistent), ('restore', route_line)):
        try:
            candidate, details = router(circuit)
        except ValueError as exc:
            if 'limit' not in str(exc):
                raise
            continue
        candidates.append((len(candidate.gates), name, candidate, details))
    if not candidates:
        raise ValueError('both line routers exceed the gate limit')
    _, name, result, details = min(candidates, key=lambda x: x[0])
    return result, {**details, 'selected_router': name}


class PassManager:
    """Ordered passes returning transformed circuits and audit records."""
    def __init__(self):
        self.passes: list[tuple[str, Callable[[Circuit], tuple[Circuit, dict]]]] = []

    def append(self, name: str, transformation: Callable[[Circuit], tuple[Circuit, dict]]):
        if not name or any(p[0] == name for p in self.passes):
            raise ValueError('pass names must be unique and nonempty')
        self.passes.append((name, transformation))
        return self

    def run(self, original: Circuit) -> tuple[Circuit, tuple[PassResult, ...]]:
        circuit = original
        history: list[PassResult] = []
        for name, transform in self.passes:
            before = metrics(circuit)
            candidate, details = transform(circuit)
            if not isinstance(candidate, Circuit) or candidate.qubits != circuit.qubits:
                raise ValueError(f'pass {name} violated the circuit width contract')
            history.append(PassResult(name, before, metrics(candidate), dict(details)))
            circuit = candidate
        return circuit, tuple(history)


def compile_circuit(original: Circuit, *, topology: str = 'all', verify: bool = False) -> tuple[Circuit, dict]:
    if topology not in ('all', 'line'):
        raise ValueError('unsupported topology (expected all or line)')
    pm = PassManager().append('local-and-commuting-rewrites', optimize)
    if topology == 'line':
        pm.append('adaptive-line-routing', route_line_best)
        pm.append('post-routing-rewrites', optimize)
    result, history = pm.run(original)
    if topology == 'line' and any(g.op == 'cx' and abs(g.qubits[0] - g.qubits[1]) != 1 for g in result.gates):
        raise AssertionError('routing emitted a non-adjacent CX')
    report = {'topology': topology, 'input': metrics(original), 'output': metrics(result),
              'passes': [{'name': p.name, 'before': p.before, 'after': p.after, 'details': p.details} for p in history]}
    if verify:
        report['verification'] = compare(original, result)
        if not report['verification']['equivalent_up_to_global_phase']:
            raise ValueError('compiled circuit failed independent equivalence check')
    else:
        report['verification'] = {'status': 'not_run'}
    return result, report
