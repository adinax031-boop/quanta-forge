"""Strict circuit data model and JSON interchange."""
from dataclasses import dataclass
import json
import math
from pathlib import Path

ARITY = {"h": 1, "x": 1, "z": 1, "rx": 1, "rz": 1, "cx": 2}
ROTATIONS = {"rx", "rz"}

@dataclass(frozen=True)
class Gate:
    op: str
    qubits: tuple[int, ...]
    angle: float | None = None

    def __post_init__(self):
        if self.op not in ARITY or len(self.qubits) != ARITY[self.op]:
            raise ValueError(f"unsupported gate or incorrect arity: {self.op}")
        if any(type(q) is not int or q < 0 for q in self.qubits):
            raise ValueError("qubit indices must be nonnegative integers")
        if len(set(self.qubits)) != len(self.qubits):
            raise ValueError("gate qubits must be distinct")
        if self.op in ROTATIONS:
            if isinstance(self.angle, bool) or not isinstance(self.angle, (float, int)) or not math.isfinite(self.angle):
                raise ValueError("rotation requires a finite numeric angle")
        elif self.angle is not None:
            raise ValueError("non-rotation gates cannot have an angle")

@dataclass(frozen=True)
class Circuit:
    qubits: int
    gates: tuple[Gate, ...]

    def __post_init__(self):
        if type(self.qubits) is not int or self.qubits < 1:
            raise ValueError("qubit count must be a positive integer")
        if any(q >= self.qubits for g in self.gates for q in g.qubits):
            raise ValueError("qubit index out of range")

    @classmethod
    def from_dict(cls, obj):
        if not isinstance(obj, dict) or set(obj) != {"qubits", "gates"} or not isinstance(obj["gates"], list):
            raise ValueError("expected object with qubits and gates")
        gates = []
        for g in obj["gates"]:
            if not isinstance(g, dict) or not {"op", "qubits"} <= set(g) or set(g) - {"op", "qubits", "angle"} or not isinstance(g["qubits"], list):
                raise ValueError("invalid gate object")
            gates.append(Gate(g["op"], tuple(g["qubits"]), g.get("angle")))
        return cls(obj["qubits"], tuple(gates))

    def to_dict(self):
        return {"qubits": self.qubits, "gates": [dict(op=g.op, qubits=list(g.qubits), **({"angle": g.angle} if g.angle is not None else {})) for g in self.gates]}

    @classmethod
    def read(cls, path):
        return cls.from_dict(json.loads(Path(path).read_text()))

    def write(self, path):
        Path(path).write_text(json.dumps(self.to_dict(), indent=2, allow_nan=False) + "\n")

"""Semantics-preserving local rewrites across disjoint operations."""

INVOLUTIONS = {"h", "x", "z", "cx"}

def optimize(circuit: Circuit) -> tuple[Circuit, dict]:
    """Cancel inverse pairs or fuse equal-axis rotations across disjoint gates.

    A gate can commute left across intervening gates only if their supports are
    disjoint. Each scan terminates at the first gate touching either operand.
    Rotation addition is subject to ordinary floating-point rounding.
    """
    out: list[Gate] = []
    stats = {"pairs_cancelled": 0, "rotations_fused": 0}
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
            stats["pairs_cancelled"] += 1
        else:
            combined = out[match].angle + gate.angle
            # Finite inputs can overflow: retain both rather than create invalid IR.
            import math
            if not math.isfinite(combined):
                out.append(gate)
                continue
            out.pop(match)
            if combined != 0:
                out.append(Gate(gate.op, gate.qubits, combined))
            stats["rotations_fused"] += 1
    return Circuit(circuit.qubits, tuple(out)), stats

"""Exhaustive statevector comparison over computational basis states.

This is numerical evidence, not a formal proof; exponential in qubit count.
Qubit 0 is the least significant basis bit.
"""
import math
import numpy as np

MAX_QUBITS = 8

def unitary(circuit: Circuit):
    if circuit.qubits > MAX_QUBITS:
        raise ValueError(f"verification limited to {MAX_QUBITS} qubits")
    n = 1 << circuit.qubits
    u = np.eye(n, dtype=np.complex128)
    for g in circuit.gates:
        if g.op == "cx":
            control, target = g.qubits
            for i in range(n):
                if (i >> control) & 1 and not (i >> target) & 1:
                    j = i | (1 << target)
                    u[[i, j], :] = u[[j, i], :]
            continue
        if g.op == "h": m = np.array([[1, 1], [1, -1]], dtype=complex) / math.sqrt(2)
        elif g.op == "x": m = np.array([[0, 1], [1, 0]], dtype=complex)
        elif g.op == "z": m = np.diag([1, -1]).astype(complex)
        elif g.op == "rx":
            c, s = math.cos(g.angle / 2), math.sin(g.angle / 2)
            m = np.array([[c, -1j*s], [-1j*s, c]], dtype=complex)
        elif g.op == "rz": m = np.diag([np.exp(-0.5j*g.angle), np.exp(0.5j*g.angle)])
        else: raise ValueError(f"unsupported gate: {g.op}")
        bit = 1 << g.qubits[0]
        for i in range(n):
            if not i & bit:
                j = i | bit
                u[[i, j], :] = m @ u[[i, j], :]
    return u

def compare(a: Circuit, b: Circuit, atol: float = 1e-10) -> dict:
    if a.qubits != b.qubits: raise ValueError("circuit sizes differ")
    if not math.isfinite(atol) or atol <= 0: raise ValueError("atol must be positive and finite")
    ua, ub = unitary(a), unitary(b)
    inner = np.vdot(ua, ub)
    phase = inner / abs(inner) if abs(inner) else 1.0
    maximum = float(np.max(np.abs(ub - phase * ua)))
    return {"equivalent_up_to_global_phase": maximum <= atol, "max_entry_error": maximum, "tolerance": atol, "method": "full-unitary basis comparison"}

import argparse
import json
import sys

def main():
    parser = argparse.ArgumentParser(prog="qforge")
    commands = parser.add_subparsers(dest="command", required=True)
    opt = commands.add_parser("optimize")
    opt.add_argument("input"); opt.add_argument("output")
    opt.add_argument("--verify", action="store_true")
    ver = commands.add_parser("verify")
    ver.add_argument("original"); ver.add_argument("candidate")
    args = parser.parse_args()
    try:
        if args.command == "optimize":
            original = Circuit.read(args.input)
            candidate, stats = optimize(original)
            report = {"input_gates": len(original.gates), "output_gates": len(candidate.gates), **stats}
            if args.verify:
                report["verification"] = compare(original, candidate)
                if not report["verification"]["equivalent_up_to_global_phase"]:
                    print(json.dumps(report, indent=2)); return 1
            candidate.write(args.output)
        else:
            report = compare(Circuit.read(args.original), Circuit.read(args.candidate))
        print(json.dumps(report, indent=2))
        return 0 if report.get("equivalent_up_to_global_phase", True) else 1
    except (ValueError, OSError, TypeError, KeyError) as exc:
        print(f"qforge: {exc}", file=sys.stderr); return 2
if __name__ == "__main__": sys.exit(main())
