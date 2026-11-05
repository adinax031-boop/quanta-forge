# QF-01: GitHub-first execution report

**Date:** 2026-10-31  
**Baseline repository:** `adinax031-boop/quanta-forge` at `e2aaa9c3d41dd67309fb55ddb3dc33478b9964dd`  
**Session output:** QuantaForge 0.2.0 working-tree snapshot. GitHub branch/PR not published because the current integration returned HTTP 403 on both branch and blob creation.

## Baseline audit

Existing v0.1: a strict JSON model, six unitary gates, conservative local cancellation/fusion, 8-qubit dense numerical checker, seeded synthetic benchmark, 7 test methods, CLI, packaging, and CI. Maintained the CLI commands and JSON schema.

## Implemented

- Generalized sound commutation rules around CX (control Z/RZ, target X/RX, CX-CX with shared control or target) and same-axis Z/RZ and X/RX.
- Affine/phase-polynomial representation of H-free X/CX/Z/RZ circuits with sparse binary parity masks, for a numerically sufficient >8-qubit equivalence check.
- Fail-closed behavior for unsupported or inconclusive large-circuit verification; no claim of symbolic completeness or formal proof.
- Comprehensive adversarial and randomized tests including declared commutation-pair checks and dense/phase semantic cross-checks.
- Reproducible head-to-head benchmark against a frozen transcription of the v0.1 algorithm. Updated README, CI, package metadata.

## Actual executed measurements

`python -m unittest -v`: 22 passing test methods on local Python 3.13, including 100 pre-existing seeded dense random circuits and 70 new randomized 9-28-qubit phase-circuit equivalence cases. Python 3.10/3.12 GitHub Actions was NOT executed locally.

`python benchmark_commutation.py --seed 2026 --cases 100`:

| Synthetic workload | Total input gates | v0.1 output | v0.2 output | Numeric verification |
|---|---:|---:|---:|---:|
| Mixed injected inverse pairs, 3 qubits | 3,260 | 1,462 | 1,388 | 100/100 |
| Structured CX commutations, 16 qubits | 12,000 | 11,006 | 3,772 | 100/100 |

`qforge optimize demo.json /tmp/optimized.json --verify` (equivalent local path used): 7 gates -> 1, dense verifier max-entry error `3.33e-16`.

These workloads deliberately favor specific rewrite rules. They are NOT neutral comparative quantum compiler performance results, production workload results, or hardware measurements.

## Review / promotion gate

- [x] Backward-compatible JSON and CLI.
- [x] Existing and new tests pass locally.
- [x] Regression comparison with old implementation.
- [x] Deterministic benchmark records and verification.
- [ ] Python 3.10/3.12 GitHub CI green on a published commit.
- [ ] Merge after GitHub write permission is available.

## QF-02 target

**Goal:** External-circuit interoperability without sacrificing correctness.

1. Implement a strict OpenQASM 2.0 parser/exporter for the supported gate subset with explicit rejection of unsupported constructs.
2. Add roundtrip tests and independent statevector cross-checks on held-out circuits.
3. Add a pass manager and proper quantum resource/depth analysis. Do not claim hardware cost without a hardware target.
4. Benchmark on a held-out, explicitly sourced test set; compare against an established open-source compiler with pinned versions.

Acceptance: zero semantic regressions on tested circuits, all unsupported input rejected, paired comparisons documented, and GitHub CI green. No model-specific Kaggle dependency.
