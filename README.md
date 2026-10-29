# Quanta Forge

**A small quantum-circuit optimization laboratory with a numerical equivalence gate.** Designed for reproducible experiments, transparent limitations, and studying compiler rewrites—not as an entry to a competition by itself.

```sh
python -m pip install .
qforge optimize demo.json /tmp/optimized.json --verify
qforge verify demo.json /tmp/optimized.json
python -m unittest -v
python benchmark.py --seed 2026 --cases 100
```

## What it does

The optimizer cancels pairs of H, X, Z and CX and fuses adjacent same-axis RX/RZ rotations. It can cross intervening gates only if the gates act on disjoint qubits. The verifier constructs the full unitary by evolving every computational-basis input and compares the matrices up to global phase. Qubit zero is the least significant basis bit. Inputs and outputs are explicit JSON; rotation angles are radians.

```json
{"qubits": 2, "gates": [
  {"op": "h", "qubits": [0]},
  {"op": "cx", "qubits": [0, 1]},
  {"op": "rz", "qubits": [1], "angle": 0.5}
]}
```

## Results and evidence

On the bundled synthetic generator, seed 2026, 100 three-qubit circuits: **3,260 input gates → 1,462 output gates**, with **100/100** equivalent under the numerical check (tolerance 1e-10). The generator deliberately injects inverse pairs, so the 55.2% reduction is a sanity check for the rewrite rules, **not a representative hardware benchmark or competition score**. Runtime depends on hardware and includes full-unitary verification. Re-run with the command above.

Tests cover blocked rewrites, control/target direction, input validation, known identities, JSON round trips, and 100 seeded random circuits. Passing tests provide evidence rather than proof. A production comparison would require held-out real circuits, standard compiler baselines, hardware-specific cost functions, and independent verification.

## Trust boundary

- The verifier is exponential in qubit count and limited to 8 qubits. It uses floating-point arithmetic and a tolerance; it is not a formal proof. Same-axis rotation fusion also uses floating-point addition.
- The JSON model supports only the listed unitary gates. No measurement, classical control, qubit allocation, QASM, topology mapping, magic-state cost or fault-tolerant decomposition is implemented.
- This repository has not been integrated with the Google Quantum AI competition verifier or workloads. No leaderboard impact is claimed.
- `--verify` verifies before writing output and returns nonzero on failure. Without it, optimization is not independently checked.

## Design

`qforge.py` defines the IR, rewrite engine, and dense matrix checker. `benchmark.py` records seed, workload, gate counts and verification results. `test_qforge.py` includes deterministic correctness checks.

Potential research directions: compare against established compilers on held-out workloads; add a proper competition-format adapter; introduce exact symbolic phase polynomials; explore rewrite scheduling and fault-tolerant cost models. Each needs independent correctness checks and measured gains.

MIT licensed.
