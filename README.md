# QuantaForge

A small, reproducible **quantum compiler research laboratory** with conservative gate rewrites and independently checked numerical equivalence. QuantaForge is an independent open-source GitHub project; it is **not** a Kaggle competition entry.

**Status: v0.3.0 research prototype**, not a fault-tolerant production compiler or formal-verification system.

## Quickstart

Requires Python 3.10+ and NumPy.

```sh
python -m pip install .
qforge optimize demo.json /tmp/optimized.json --verify
qforge verify demo.json /tmp/optimized.json
python -m unittest -v
python benchmark.py --seed 2026 --cases 100
python benchmark_commutation.py --seed 2026 --cases 100
```

A circuit is a JSON object containing `qubits` and `gates`:

```json
{"qubits": 2, "gates": [
  {"op": "h", "qubits": [0]},
  {"op": "cx", "qubits": [0, 1]},
  {"op": "rz", "qubits": [1], "angle": 0.5}
]}
```

The supported gates are **H, X, Z, RX, RZ, CX**. Rotation angles are radians. Qubit zero is the least significant basis bit. All registers are allocated up front. JSON is strict and checked at import.

## Compiler passes

- Cancel involutory gates (H, X, Z, CX) when separated exclusively by commuting gates.
- Merge same-axis RX and RZ rotations; a zero-angle result is removed.
- Recognize **Z/RZ on CX's control** and **X/RX on CX's target** as commuting.
- Recognize CX–CX commutation when both gates share their control or their target.
- Recognize same-axis single-qubit gates as commuting (Z with RZ, X with RX).
- Use conservative blockers for all other overlapping gate supports. Neither arbitrary gate permutation nor phase-sensitive algebra is assumed.

The optimizer performs floating-point rotation addition. It is not a complete circuit superoptimizer.

## Verification and trust boundary

`qforge verify` compares circuit unitaries **up to global phase**:

- At **8 qubits or fewer**, the verifier evolves every basis state and compares dense unitary matrices numerically. This is exponential-time evidence, not a mathematical proof.
- At **more than 8 qubits**, a special verifier supports only H-free `{X, CX, Z, RZ}` circuits. It represents the output as an affine transformation of basis states plus a sparse parity-phase polynomial. Identical affine maps with sufficiently close phase coefficients yield a conservative *sufficient* numerical bound. Counterexamples in the output map or phase evaluations can demonstrate non-equivalence.
- For other large circuits, ambiguous phase identities, or unsupported gate sets, verification **fails closed**, returning a nonzero exit code. The special verifier deliberately does not claim completeness or formal proof. Rotations exceeding 1e6 radians are rejected in this mode due to floating-point phase reduction.
- `optimize --verify` verifies **before writing output**. An unknown or failing result leaves the destination unwritten. Running `optimize` without `--verify` does not produce an independent verification result.

The large-circuit mode is limited to a monomial unitary fragment; H/RX and circuits containing interference require denser verification or future general-purpose methods.

## Measured results

Local Python execution, seed `2026`, 100 cases per workload. Reproduce with `python benchmark_commutation.py --seed 2026 --cases 100`.

| Synthetic workload | Gates in | v0.1 gates out | v0.2 gates out | Verified |
| --- | ---: | ---: | ---: | ---: |
| Mixed inverse-pair injection (3 qubits) | 3,260 | 1,462 | **1,388** | 100/100 dense |
| Structured CX-commutation workload (16 qubits) | 12,000 | 11,006 | **3,772** | 100/100 phase-polynomial |

The mixed workload intentionally injects inverse pairs. The structured workload intentionally puts useful commutation opportunities into circuits. These are **synthetic regression/feature tests**, not unbiased hardware, production, or competing compiler benchmarks. The historical 3,260 → 1,462 result is reproduced using the frozen v0.1 rewrite logic in `benchmark_commutation.py`.

The tests cover numerical identities, commutation safety, blocked rewrites, control/target ordering, JSON round trips, 100 mixed random circuits, 70 seeded larger-circuit rewrites, a dense-versus-phase-polynomial cross-check, and failure-closed CLI behavior.

## Repository design

- `qforge.py` — strict IR, commutation-aware optimization, dense checker, CLI.
- `qforge_phase.py` — sparse affine and parity-phase numerical checker for the restricted gate fragment.
- `benchmark.py` — original v0.1 synthetic generator, preserved for continuity.
- `benchmark_commutation.py` — reproducible v0.1/v0.2 comparison with explicit workload labels.
- `test_qforge.py` — deterministic regression and property tests.
- `.github/workflows/ci.yml` — Python 3.10/3.12 test and benchmark checks.


## QF-02: OpenQASM interoperability and compiler passes (v0.3.0)

QF-02 builds on the v0.2 optimizer. It adds a strict OpenQASM 2.0 frontend and
emitter, a named pass pipeline, conservative linear nearest-neighbor routing,
resource/depth metrics, and reproducible paired benchmarks.

```bash
python -m pip install .
qforge compile examples/phase-demo.qasm /tmp/compiled.qasm --verify
qforge compile examples/qrewrite-compat.qasm /tmp/routed.json --topology line --verify
qforge compile demo.json /tmp/demo.qasm --verify
python -m unittest -v
python benchmark_qf02.py --seed 2026 --cases 50 --output /tmp/qf02.json
```

The QASM frontend supports `OPENQASM 2.0`, optional `qelib1.inc`, one `qreg q[N]`,
`h`, `x`, `z`, `s`, `sdg`, `t`, `tdg`, `rx(angle)`, `rz(angle)`, `u1(angle)`,
`p(angle)` and `cx`. Numeric angle expressions may contain `pi`, finite
numbers and bounded `+ - * /` arithmetic. Unsupported operations fail closed.
`p/u1/S/T` are converted to `RZ` **up to a global phase**; this does not preserve
a global phase under arbitrary controlled-subroutine embedding.
No measurements, custom gates, classical control, OpenQASM 3 or full-spec QASM
support is claimed.

`--topology line` inserts reversible SWAP decompositions (3 CNOTs each) around
nonadjacent CNOTs, restoring the original logical-to-physical layout. This
provides a correctness baseline rather than optimal routing. Topology constraints
are preserved even after a post-routing optimization pass. Compilation refuses
to emit more than 250,000 gates during routing.

Compiler passes are recorded with before/after gate counts, CNOT counts, ASAP
logical depth, and transformation-specific metadata. Depth assumes unit gate
duration, unconstrained parallelism on disjoint qubits, and no hardware timing.
`--verify` compares small circuits using a dense numerical unitary (<=8 qubits),
or large circuits in the H-free X/CX/Z/RZ fragment using a conservative
phase-polynomial numerical checker. Unsupported large verifications fail closed.
Verified CLI writes are atomic; an invalid candidate never overwrites the
requested output. Verification up to global phase is **not a formal proof**.

The QASM and routing direction was informed by the existing [`qrewrite`](https://github.com/adinax031-boop/qrewrite)
prototype in the same account. The QF-02 implementation uses QuantaForge's
existing radians-based IR and independently tests the shared sample circuit.

See `docs/QF02_EXECUTION_REPORT.md` for the actual result. This is compiler
infrastructure; no SOTA or hardware improvement is claimed.

## Research roadmap

1. Add a typed, multi-pass compiler architecture with pass-specific acceptance gates.
2. Build OpenQASM import/export, strict semantic validation, and end-to-end roundtrips.
3. Add exact/symbolic certificates for narrower gatesets; maintain numerical checker separately.
4. Introduce resource estimation (depth, topology constraints, T/Toffoli counts) and **external**, held-out baseline comparison.
5. Optimize memory/time before choosing Rust/C++ backends; profile before rewriting.

External competition workloads may be useful as *optional* independent benchmarks, but do not define QuantaForge's mission.

MIT licensed.
