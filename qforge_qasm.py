"""Deliberately strict OpenQASM 2 subset frontend and emitter.

Allowed: qreg q[N], h/x/z/s/sdg/t/tdg, rx/rz, u1/p and cx.
The u1/p/S/T family is represented as RZ up to an input-independent
(global) phase. This is valid only for the project's unitary-up-to-phase
semantic contract; it is not a controlled-global-phase preserving mapping.
"""
from __future__ import annotations

import ast
import math
import re

from qforge import Circuit, Gate

MAX_QASM_CHARS = 10_000_000
MAX_QUBITS = 100_000
MAX_GATES = 1_000_000
_SINGLE = re.compile(r'(h|x|z|s|sdg|t|tdg)\s+q\[(\d+)\]', re.I)
_ROTATE = re.compile(r'(rx|rz|u1|p)\s*\(\s*([^()]*)\s*\)\s*q\[(\d+)\]', re.I)
_CX = re.compile(r'cx\s+q\[(\d+)\]\s*,\s*q\[(\d+)\]', re.I)
_QREG = re.compile(r'qreg\s+q\[(\d+)\]', re.I)
_INCLUDE = re.compile(r'include\s+"qelib1\.inc"', re.I)


def angle_value(expression: str) -> float:
    """Parse a bounded numeric/pi expression; never execute Python code."""
    if not expression or len(expression) > 128:
        raise ValueError('empty or oversized QASM angle')
    try:
        tree = ast.parse(expression, mode='eval')
    except SyntaxError as e:
        raise ValueError('invalid QASM angle expression') from e

    def walk(node, depth=0):
        if depth > 16:
            raise ValueError('QASM angle expression too deep')
        if isinstance(node, ast.Constant) and type(node.value) in (float, int):
            value = float(node.value)
        elif isinstance(node, ast.Name) and node.id == 'pi':
            value = math.pi
        elif isinstance(node, ast.UnaryOp) and type(node.op) in (ast.USub, ast.UAdd):
            value = walk(node.operand, depth + 1)
            if isinstance(node.op, ast.USub):
                value = -value
        elif isinstance(node, ast.BinOp) and type(node.op) in (ast.Add, ast.Sub, ast.Mult, ast.Div):
            left, right = walk(node.left, depth + 1), walk(node.right, depth + 1)
            if isinstance(node.op, ast.Add): value = left + right
            elif isinstance(node.op, ast.Sub): value = left - right
            elif isinstance(node.op, ast.Mult): value = left * right
            else:
                if right == 0: raise ValueError('division by zero in QASM angle')
                value = left / right
        else:
            raise ValueError('unsupported QASM angle syntax')
        if not math.isfinite(value) or abs(value) > 1e9:
            raise ValueError('nonfinite or excessive QASM angle')
        return value

    return walk(tree.body)


def parse_qasm(source: str) -> Circuit:
    if not isinstance(source, str) or len(source) > MAX_QASM_CHARS:
        raise ValueError('QASM input must be text of at most 10 million characters')
    # Only comment removal is performed: all other unsupported statements fail.
    source = re.sub(r'/\*[\s\S]*?\*/', '', source)
    source = re.sub(r'//[^\n]*', '', source)
    if source.strip() and not source.rstrip().endswith(';'):
        raise ValueError('OpenQASM statements must terminate with semicolons')
    statements = [s.strip() for s in source.split(';') if s.strip()]
    if not statements or statements.pop(0).lower() != 'openqasm 2.0':
        raise ValueError('expected OPENQASM 2.0 header')
    if statements and _INCLUDE.fullmatch(statements[0]):
        statements.pop(0)
    if not statements or not (match := _QREG.fullmatch(statements.pop(0))):
        raise ValueError('expected exactly one qreg q[N]')
    n = int(match.group(1))
    if not (1 <= n <= MAX_QUBITS):
        raise ValueError('qreg size outside supported 1..100000 range')
    if len(statements) > MAX_GATES:
        raise ValueError('too many QASM gate statements')
    gates = []
    phase_angles = {'s': math.pi / 2, 'sdg': -math.pi / 2,
                    't': math.pi / 4, 'tdg': -math.pi / 4}
    for index, statement in enumerate(statements, start=1):
        if match := _SINGLE.fullmatch(statement):
            op, q = match.group(1).lower(), int(match.group(2))
            gates.append(Gate('rz', (q,), phase_angles[op]) if op in phase_angles else Gate(op, (q,)))
        elif match := _CX.fullmatch(statement):
            gates.append(Gate('cx', (int(match.group(1)), int(match.group(2)))))
        elif match := _ROTATE.fullmatch(statement):
            op, expr, q = match.group(1).lower(), match.group(2), int(match.group(3))
            gates.append(Gate('rz' if op in ('u1', 'p') else op, (q,), angle_value(expr)))
        else:
            raise ValueError(f'unsupported QASM statement #{index}: {statement[:100]!r}')
    return Circuit(n, tuple(gates))


def emit_qasm(circuit: Circuit) -> str:
    lines = ['OPENQASM 2.0;', 'include "qelib1.inc";', f'qreg q[{circuit.qubits}];']
    for gate in circuit.gates:
        if gate.op == 'cx':
            lines.append(f'cx q[{gate.qubits[0]}],q[{gate.qubits[1]}];')
        elif gate.op in ('rx', 'rz'):
            # 17 significant digits preserve every finite binary64 angle.
            lines.append(f'{gate.op}({format(float(gate.angle), ".17g")}) q[{gate.qubits[0]}];')
        else:
            lines.append(f'{gate.op} q[{gate.qubits[0]}];')
    return '\n'.join(lines) + '\n'
