# QF-02 — QuantaForge v0.3.0 execution report

**Date:** 31 October 2026
**Project:** https://github.com/adinax031-boop/quanta-forge
**GitHub baseline observed:** `main` at `e2aaa9c3d41dd67309fb55ddb3dc33478b9964dd` (v0.1)
**Immediate implementation baseline:** locally archived v0.2.0 from QF-01; **not present on remote main**. All v0.2 files were retained.
**Provenance:** `qrewrite` repository inspected, including strict `compiler.py` and `example.qasm`, used as architectural references and as a compatibility test input. QF-02 code uses QuantaForge's existing radians and gate semantics, not QRewrite's exact rational-angle representation.

## Objective and actual execution

Extend the existing proven optimizer rather than restart it. Delivered:

1. `qforge_qasm.py`: strict subset OpenQASM 2 frontend + deterministic emitter; safe bounded angle-expression AST, phase-family conversion up to global phase, malformed/unsupported input rejection.
2. `qforge_compiler.py`: ordered pass manager; per-pass before/after records; adjacency-constrained line-topology CNOT routing with restored layout; gate-count/CX/depth accounting; routing output guard.
3. Extended `qforge.py` CLI: `qforge compile IN OUT --topology all|line --verify`, JSON ↔ QASM support, atomic output replacement following successful verification.
4. `test_qforge_compiler.py`: 18 new tests, preserving all 22 QF-01 tests. Covers malicious/invalid syntax, QASM phase conventions and roundtrips, directed CNOT pairs, entangled randomized tests, independent matrix oracle, failure-closed output, and 20-qubit affine-phase verification.
5. `benchmark_qf02.py`: deterministic paired compilation/verification for three synthetic workloads, with every sample stored alongside resource metrics, pass details and timings.
6. CI checks for QASM compilation and the benchmark; wheel build and installed-CLI smoke test performed locally.

## Reproducible test/packaging results

- `python -m unittest -v`: **40 tests passed**, 2.959 seconds on the execution environment.
- `python benchmark_qf02.py --seed 2026 --cases 50`: **300 / 300 compilation/verification pairs passed** (50 circuits × 3 workloads × 2 topology modes).
- `python -m pip wheel --no-build-isolation --no-deps . -w dist`: **built** `quanta_forge-0.3.0-py3-none-any.whl`.
- Wheel installed in a separate virtual environment and CLI used to compile/verify the QRewrite QASM example: **passed**.
- `qforge compile demo.json … --verify`: **passed**.
- Tests have *not* yet run on all GitHub Actions runner versions for QF-02; the new CI workflow is local-only until changes are uploaded.

## Aggregate synthetic benchmark

| Workload | Topology | Circuits checked | Gates input | Gates output | CX input | CX output | Median compile time |
|---|---|---:|---:|---:|---:|---:|---:|
| Mixed 4q | all | 50/50 | 2,149 | 1,048 | 360 | 198 | 0.104 ms |
| Mixed 4q | line | 50/50 | 2,149 | 1,750 | 360 | 900 | 0.221 ms |
| CX-heavy 5q | all | 50/50 | 1,834 | 972 | 882 | 494 | 0.094 ms |
| CX-heavy 5q | line | 50/50 | 1,834 | 3,504 | 882 | 3,026 | 0.334 ms |
| Affine-phase 20q | all | 50/50 | 4,289 | 2,320 | 1,681 | 1,023 | 0.339 ms |
| Affine-phase 20q | line | 50/50 | 4,289 | 37,308 | 1,681 | 36,011 | 3.009 ms |

The **37,308 vs 2,320** gap for the same 20-qubit workloads is a warning that restoring the original wire layout after every remote CNOT is extraordinarily expensive on the line. It is a correctness-first baseline, not an optimization win. The sampled tasks deliberately include injected inverse pairs and do not establish SOTA or representative hardware performance. Compilation and verification timers are separated in the raw file. Hardware/OS/Python metadata and per-case data are in `evidence/QF02_benchmark_seed2026_50.json`.

## Verification semantics and unresolved issues

- Dense 8-qubit-or-fewer verification uses floating-point full-unitary comparison up to global phase.
- The large-circuit phase-polynomial checker supports only X, CX, Z and RZ and is sufficient-but-incomplete, not a general proof.
- QASM 2 import is a **strict subset**, not a standards-complete frontend. P/U1/S/T map to RZ only up to global phase; source-program semantics must not be treated as controlled-subroutine exact.
- Line routing assumes undirected adjacent CNOT support, not asymmetric hardware gate calibration. There are no physical error-rate models.
- Pass-manager metrics are idealized ASAP logical depth with unit gate duration, not backend execution latency.
- No cross-compiler competitive comparison, statistically sampled real-world circuit corpus or peer baseline has been executed yet.
- Remote GitHub `main` does **not** contain QF-01/QF-02; upload needs write access, and no CI status is claimed for these local commits.

## QF-03 next experimentally grounded target

**Topology-aware routing with persistent logical-to-physical mapping.** Hypothesis: allowing the mapping to evolve across CNOTs can avoid repeated SWAP reversal and reduce the CNOT explosion on line topologies.

Acceptance:
1. Preserve all 40 current tests and add exhaustive small-width truth tests.
2. Add per-circuit exact output-permutation tracking and/or final mapping repair so externally observed circuit semantics remain unchanged.
3. Compare against the v0.3 restore-layout router on identical held-out routed circuits and hardware assumptions.
4. Report total CX count, depth, peak memory and compile time, and fail any inequivalent candidate.
5. Stop if the measured reduction is absent or regression risk is unacceptable.

## Execution artifacts

- `evidence/QF02_unittest_40.log` — actual local test log
- `evidence/QF02_benchmark_seed2026_50.json` — raw case-level and summary measurements
- `evidence/QF02_wheel_smoke.json` — installed package CLI result
- `dist/quanta_forge-0.3.0-py3-none-any.whl` — locally built wheel
- `test_qforge_compiler.py`, `benchmark_qf02.py` — reproduction tools
