"""Sparse affine/phase-polynomial analysis for the H-free X/CX/Z/RZ fragment.

Every supported circuit maps |x> to exp(i f(x)) |A x xor b>, up to a
constant global phase. f(x) is a sum of real angles times binary parities.

This offers a sufficient (not complete) scalable numerical check when the
original dense verifier is infeasible. No formal proof is claimed for floats.
"""
from collections import defaultdict
from dataclasses import dataclass
import math
import random

SUPPORTED = frozenset(("x", "cx", "z", "rz"))
# Avoid asserting floating-point phase identities after catastrophic angle reduction.
MAX_ABS_ROTATION = 1e6
TAU = 2.0 * math.pi


@dataclass(frozen=True)
class PhaseSignature:
    rows: tuple[int, ...]
    offsets: tuple[int, ...]
    coefficients: tuple[tuple[int, float], ...]


def affine_phase_signature(circuit):
    if any(g.op not in SUPPORTED for g in circuit.gates):
        raise ValueError("phase verifier supports only X, CX, Z, RZ; H/RX require dense verification (<=8 qubits)")
    rows = [1 << i for i in range(circuit.qubits)]
    offsets = [0] * circuit.qubits
    contributions = defaultdict(list)
    for gate in circuit.gates:
        if gate.op == "x":
            offsets[gate.qubits[0]] ^= 1
        elif gate.op == "cx":
            c, t = gate.qubits
            rows[t] ^= rows[c]
            offsets[t] ^= offsets[c]
        else:
            q = gate.qubits[0]
            angle = math.pi if gate.op == "z" else float(gate.angle)
            if abs(angle) > MAX_ABS_ROTATION:
                raise ValueError("phase verifier rejects rotations above 1e6 radians: argument reduction is unreliable")
            contributions[rows[q]].append(-angle if offsets[q] else angle)
    coefficients = tuple(sorted((mask, math.fsum(angles)) for mask, angles in contributions.items()))
    return PhaseSignature(tuple(rows), tuple(offsets), coefficients)


def _angle(coeffs, x):
    return math.fsum(angle for mask, angle in coeffs if (mask & x).bit_count() & 1)


def compare_affine_phase(a, b, atol=1e-10):
    """Numerically sufficient check; unknown cases raise instead of claiming failure.

    Coincident affine maps plus matching parity coefficients (mod 2pi) bound
    the relative phase error by the sum of absolute coefficient residuals.
    Distinct affine maps, or a phase witness on a basis input, prove unequal.
    """
    if a.qubits != b.qubits:
        raise ValueError("circuit sizes differ")
    if not math.isfinite(atol) or atol <= 0:
        raise ValueError("atol must be positive and finite")
    sa, sb = affine_phase_signature(a), affine_phase_signature(b)
    if sa.rows != sb.rows or sa.offsets != sb.offsets:
        return {"equivalent_up_to_global_phase": False, "max_entry_error": 1.0,
                "tolerance": atol, "method": "affine output map mismatch"}

    ca, cb = dict(sa.coefficients), dict(sb.coefficients)
    residuals = [abs(math.remainder(ca.get(mask, 0.0) - cb.get(mask, 0.0), TAU))
                 for mask in ca.keys() | cb.keys()]
    angle_bound = math.fsum(residuals)
    if angle_bound <= atol:
        return {"equivalent_up_to_global_phase": True, "max_entry_error": min(2.0, angle_bound),
                "tolerance": atol, "method": "affine phase-polynomial numerical bound",
                "phase_error_bound_radians": angle_bound,
                "note": "sufficient numerical check; not a formal proof"}

    # An actual basis witness establishes inequivalence. Failure to find one
    # cannot be interpreted as evidence of equivalence.
    n = a.qubits
    probes = [1 << i for i in range(n)]
    probes.extend((1 << i) | (1 << (i + 1)) for i in range(n - 1))
    rng = random.Random(0x51464F)
    probes.extend(rng.getrandbits(n) for _ in range(128))
    for x in probes:
        phase_diff = math.remainder(_angle(sa.coefficients, x) - _angle(sb.coefficients, x), TAU)
        error = 2 * abs(math.sin(phase_diff / 2))
        if error > atol:
            return {"equivalent_up_to_global_phase": False, "max_entry_error": error,
                    "tolerance": atol, "method": "affine phase-polynomial basis witness",
                    "witness_input": x}
    raise ValueError("phase-polynomial check inconclusive; no equivalence claim made")
