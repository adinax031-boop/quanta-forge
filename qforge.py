"""QuantaForge: validated circuit IR, conservative rewrites, and numerical checks.

Qubit zero is the least significant computational-basis bit.
"""
from dataclasses import dataclass
import argparse
import json
import math
from pathlib import Path
import sys

import numpy as np

ARITY = {"h": 1, "x": 1, "z": 1, "rx": 1, "rz": 1, "cx": 2}
ROTATIONS = {"rx", "rz"}
INVOLUTIONS = {"h", "x", "z", "cx"}
MAX_QUBITS = 8


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


def commutes(left: Gate, right: Gate) -> bool:
    """Sound commutation rules; intentionally incomplete rather than speculative.

    These rules support commuting *identical* gates as well as same-axis
    rotations through Z/X and selected CX patterns. CX control/target order
    is respected throughout.
    """
    if not set(left.qubits).intersection(right.qubits):
        return True
    if left.op == right.op and left.qubits == right.qubits:
        return True
    if left.op == "cx" and right.op == "cx":
        return left.qubits[0] == right.qubits[0] or left.qubits[1] == right.qubits[1]
    if left.op == "cx" or right.op == "cx":
        cx, single = (left, right) if left.op == "cx" else (right, left)
        if len(single.qubits) != 1:
            return False
        return ((single.op in ("z", "rz") and single.qubits[0] == cx.qubits[0]) or
                (single.op in ("x", "rx") and single.qubits[0] == cx.qubits[1]))
    if len(left.qubits) == len(right.qubits) == 1 and left.qubits == right.qubits:
        return ((left.op in ("z", "rz") and right.op in ("z", "rz")) or
                (left.op in ("x", "rx") and right.op in ("x", "rx")))
    return False


def optimize(circuit: Circuit) -> tuple[Circuit, dict]:
    """Cancel involutions and fuse equal-axis rotations across commuting gates.

    No general quantum algebra is assumed: only explicit, checked identities.
    Rotation addition is floating-point and can therefore round.
    """
    out: list[Gate] = []
    stats = {"pairs_cancelled": 0, "rotations_fused": 0}
    for gate in circuit.gates:
        if gate.op in ROTATIONS and gate.angle == 0:
            continue
        match = None
        for i in range(len(out) - 1, -1, -1):
            prev = out[i]
            if prev.op == gate.op and prev.qubits == gate.qubits:
                match = i
                break
            if not commutes(prev, gate):
                break
        if match is None:
            out.append(gate)
        elif gate.op in INVOLUTIONS:
            out.pop(match)
            stats["pairs_cancelled"] += 1
        else:
            combined = out[match].angle + gate.angle
            # Finite inputs can overflow; retain both rather than make invalid IR.
            if not math.isfinite(combined):
                out.append(gate)
                continue
            out.pop(match)
            if combined != 0:
                out.append(Gate(gate.op, gate.qubits, combined))
            stats["rotations_fused"] += 1
    return Circuit(circuit.qubits, tuple(out)), stats


def unitary(circuit: Circuit):
    """Exhaustive numerical unitary, exponential in circuit width."""
    if circuit.qubits > MAX_QUBITS:
        raise ValueError(f"dense verification limited to {MAX_QUBITS} qubits")
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
        if g.op == "h":
            m = np.array([[1, 1], [1, -1]], dtype=complex) / math.sqrt(2)
        elif g.op == "x":
            m = np.array([[0, 1], [1, 0]], dtype=complex)
        elif g.op == "z":
            m = np.diag([1, -1]).astype(complex)
        elif g.op == "rx":
            c, s = math.cos(g.angle / 2), math.sin(g.angle / 2)
            m = np.array([[c, -1j*s], [-1j*s, c]], dtype=complex)
        elif g.op == "rz":
            m = np.diag([np.exp(-0.5j*g.angle), np.exp(0.5j*g.angle)])
        else:
            raise ValueError(f"unsupported gate: {g.op}")
        bit = 1 << g.qubits[0]
        for i in range(n):
            if not i & bit:
                j = i | bit
                u[[i, j], :] = m @ u[[i, j], :]
    return u


def compare(a: Circuit, b: Circuit, atol: float = 1e-10) -> dict:
    """Small: dense verification; large affine-diagonal: sufficient phase check.

    For unsupported large circuits or unproved phase identities fail *closed*.
    This is numerical evidence, not computer-assisted formal proof.
    """
    if a.qubits != b.qubits:
        raise ValueError("circuit sizes differ")
    if isinstance(atol, bool) or not isinstance(atol, (int, float)) or not math.isfinite(atol) or atol <= 0:
        raise ValueError("atol must be positive and finite")
    if a.qubits > MAX_QUBITS:
        from qforge_phase import compare_affine_phase
        return compare_affine_phase(a, b, atol)
    ua, ub = unitary(a), unitary(b)
    inner = np.vdot(ua, ub)
    phase = inner / abs(inner) if abs(inner) else 1.0
    maximum = float(np.max(np.abs(ub - phase * ua)))
    return {"equivalent_up_to_global_phase": maximum <= atol, "max_entry_error": maximum, "tolerance": atol, "method": "full-unitary basis comparison"}


def main():
    parser = argparse.ArgumentParser(prog="qforge")
    commands = parser.add_subparsers(dest="command", required=True)
    opt = commands.add_parser("optimize")
    opt.add_argument("input")
    opt.add_argument("output")
    opt.add_argument("--verify", action="store_true")
    comp = commands.add_parser("compile", help="Compile JSON or OpenQASM 2 circuits")
    comp.add_argument("input")
    comp.add_argument("output")
    comp.add_argument("--input-format", choices=("auto", "json", "qasm"), default="auto")
    comp.add_argument("--output-format", choices=("auto", "json", "qasm"), default="auto")
    comp.add_argument("--topology", choices=("all", "line"), default="all")
    comp.add_argument("--verify", action="store_true")
    ver = commands.add_parser("verify")
    ver.add_argument("original")
    ver.add_argument("candidate")
    args = parser.parse_args()
    try:
        if args.command == "optimize":
            original = Circuit.read(args.input)
            candidate, stats = optimize(original)
            report = {"input_gates": len(original.gates), "output_gates": len(candidate.gates), **stats}
            if args.verify:
                report["verification"] = compare(original, candidate)
                if not report["verification"]["equivalent_up_to_global_phase"]:
                    print(json.dumps(report, indent=2))
                    return 1
            candidate.write(args.output)
        elif args.command == "compile":
            from qforge_compiler import compile_circuit
            from qforge_qasm import parse_qasm, emit_qasm
            def file_format(path, selected):
                if selected != "auto":
                    return selected
                suffix = Path(path).suffix.lower()
                if suffix == ".json": return "json"
                if suffix == ".qasm": return "qasm"
                raise ValueError("auto format requires .json or .qasm extension")
            input_format = file_format(args.input, args.input_format)
            output_format = file_format(args.output, args.output_format)
            raw = Path(args.input).read_text(encoding="utf-8")
            original = Circuit.from_dict(json.loads(raw)) if input_format == "json" else parse_qasm(raw)
            candidate, report = compile_circuit(original, topology=args.topology, verify=args.verify)
            output = (json.dumps(candidate.to_dict(), indent=2, allow_nan=False) + "\n"
                      if output_format == "json" else emit_qasm(candidate))
            # File is not touched if compilation or verification fails.
            # Atomic replacement prevents partially-written outputs.
            import os
            import tempfile
            dest = Path(args.output)
            fd, temp = tempfile.mkstemp(prefix=".qforge-", dir=dest.parent, text=True)
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    f.write(output)
                os.replace(temp, dest)
            finally:
                if os.path.exists(temp): os.unlink(temp)
        else:
            report = compare(Circuit.read(args.original), Circuit.read(args.candidate))
        print(json.dumps(report, indent=2))
        return 0 if report.get("equivalent_up_to_global_phase", True) else 1
    except (ValueError, OSError, TypeError, KeyError) as exc:
        print(f"qforge: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
