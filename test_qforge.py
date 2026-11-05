import json
import math
import random
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
from qforge import Circuit, Gate, optimize, compare, commutes, unitary
from qforge_phase import affine_phase_signature


class BaselineTests(unittest.TestCase):
    def test_disjoint_cancellation_and_blocker(self):
        a = Circuit(2, (Gate('h', (0,)), Gate('x', (1,)), Gate('h', (0,))))
        b, stats = optimize(a)
        self.assertEqual(b.gates, (Gate('x', (1,)),))
        self.assertEqual(stats['pairs_cancelled'], 1)
        blocked = Circuit(2, (Gate('h', (0,)), Gate('cx', (0, 1)), Gate('h', (0,))))
        self.assertEqual(optimize(blocked)[0], blocked)

    def test_rotation_fusion(self):
        a = Circuit(1, (Gate('rz', (0,), 0.25), Gate('rz', (0,), -0.25)))
        self.assertEqual(optimize(a)[0].gates, ())

    def test_cx_direction(self):
        a = Circuit(2, (Gate('cx', (0, 1)), Gate('cx', (1, 0))))
        self.assertEqual(optimize(a)[0], a)
        self.assertFalse(compare(Circuit(2, (a.gates[0],)), Circuit(2, (a.gates[1],)))['equivalent_up_to_global_phase'])

    def test_input_validation(self):
        for f in (lambda: Gate('rx', (0,), float('nan')),
                  lambda: Gate('cx', (0, 0)),
                  lambda: Circuit(1, (Gate('h', (1,)),)),
                  lambda: Gate('h', (True,))):
            with self.assertRaises(ValueError):
                f()
        with self.assertRaises(ValueError):
            unitary(Circuit(9, ()))

    def test_known_h_squared(self):
        self.assertTrue(compare(Circuit(1, (Gate('h', (0,)), Gate('h', (0,)))), Circuit(1, ()))['equivalent_up_to_global_phase'])
        self.assertFalse(compare(Circuit(1, (Gate('x', (0,)),)), Circuit(1, ()))['equivalent_up_to_global_phase'])

    def test_seeded_random_circuits(self):
        rng = random.Random(731)
        for _ in range(100):
            gates = []
            for _ in range(35):
                op = rng.choice(('h', 'x', 'z', 'rx', 'rz', 'cx'))
                if op == 'cx':
                    gates.append(Gate(op, tuple(rng.sample(range(3), 2))))
                else:
                    gates.append(Gate(op, (rng.randrange(3),), rng.uniform(-3, 3) if op in ('rx', 'rz') else None))
            a = Circuit(3, tuple(gates)); b, _ = optimize(a)
            self.assertTrue(compare(a, b)['equivalent_up_to_global_phase'])
            self.assertLessEqual(len(b.gates), len(a.gates))

    def test_json_roundtrip(self):
        a = Circuit(2, (Gate('rx', (1,), math.pi),))
        self.assertEqual(a, Circuit.from_dict(a.to_dict()))


class ExtendedCommutationTests(unittest.TestCase):
    def test_diagonal_on_control_across_cx(self):
        a = Circuit(2, (Gate('rz', (0,), .4), Gate('cx', (0, 1)), Gate('rz', (0,), -.4)))
        b, stats = optimize(a)
        self.assertEqual(b.gates, (Gate('cx', (0, 1)),))
        self.assertEqual(stats['rotations_fused'], 1)
        self.assertTrue(compare(a, b)['equivalent_up_to_global_phase'])

    def test_rx_on_target_across_cx(self):
        a = Circuit(2, (Gate('rx', (1,), .4), Gate('cx', (0, 1)), Gate('rx', (1,), -.4)))
        b, _ = optimize(a)
        self.assertEqual(b.gates, (Gate('cx', (0, 1)),))
        self.assertTrue(compare(a, b)['equivalent_up_to_global_phase'])

    def test_z_and_x_involution_across_cx(self):
        for gate in (Gate('z', (0,)), Gate('x', (1,))):
            a = Circuit(2, (gate, Gate('cx', (0, 1)), gate))
            self.assertEqual(optimize(a)[0].gates, (Gate('cx', (0, 1)),))
            self.assertTrue(compare(a, optimize(a)[0])['equivalent_up_to_global_phase'])

    def test_cx_matching_control_or_target(self):
        for left, middle in ((Gate('cx', (0, 1)), Gate('cx', (0, 2))),
                             (Gate('cx', (0, 2)), Gate('cx', (1, 2)))):
            a = Circuit(3, (left, middle, left))
            self.assertEqual(optimize(a)[0].gates, (middle,))
            self.assertTrue(compare(a, optimize(a)[0])['equivalent_up_to_global_phase'])

    def test_exhaustive_declared_commutations(self):
        gates = [Gate(op, (q,), 0.37 if op in ("rx", "rz") else None)
                 for op in ("h", "x", "z", "rx", "rz") for q in range(3)]
        gates += [Gate("cx", (a, b)) for a in range(3) for b in range(3) if a != b]
        for left in gates:
            for right in gates:
                if commutes(left, right):
                    a = Circuit(3, (left, right))
                    b = Circuit(3, (right, left))
                    self.assertTrue(compare(a, b)["equivalent_up_to_global_phase"], (left, right))

    def test_noncommuting_cx_must_block(self):
        a = Circuit(3, (Gate('cx', (0, 1)), Gate('cx', (1, 2)), Gate('cx', (0, 1))))
        self.assertEqual(optimize(a)[0], a)
        self.assertFalse(commutes(a.gates[0], a.gates[1]))

    def test_z_and_rz_commute(self):
        a = Circuit(1, (Gate('rz', (0,), .25), Gate('z', (0,)), Gate('rz', (0,), -.25)))
        b, _ = optimize(a)
        self.assertEqual(b.gates, (Gate('z', (0,)),))
        self.assertTrue(compare(a, b)['equivalent_up_to_global_phase'])

    def test_random_large_rewrites_have_phase_witness(self):
        rng = random.Random(63219)
        for _ in range(70):
            n = rng.randint(9, 28)
            gs = []
            for _ in range(50):
                op = rng.choice(('cx', 'x', 'z', 'rz'))
                q = tuple(rng.sample(range(n), 2)) if op == 'cx' else (rng.randrange(n),)
                g = Gate(op, q, rng.uniform(-3, 3) if op == 'rz' else None)
                gs.append(g)
                if rng.random() < .25:
                    gs.append(Gate(op, q, -g.angle if op == 'rz' else None))
            a = Circuit(n, tuple(gs)); b, _ = optimize(a)
            result = compare(a, b)
            self.assertTrue(result['equivalent_up_to_global_phase'], result)
            self.assertIn('phase-polynomial', result['method'])


class PhaseVerifierTests(unittest.TestCase):
    def test_large_equivalent(self):
        a = Circuit(40, (Gate('x', (0,)), Gate('rz', (1,), .3), Gate('cx', (0, 1)), Gate('rz', (1,), -.3)))
        # Canceling these two RZ gates is *not* valid when the target is changed by CX.
        self.assertFalse(compare(a, Circuit(40, (Gate('x', (0,)), Gate('cx', (0, 1)))) )['equivalent_up_to_global_phase'])
        b = Circuit(40, (Gate('rz', (2,), .3), Gate('rz', (2,), -.3)))
        self.assertTrue(compare(b, Circuit(40, ()))['equivalent_up_to_global_phase'])

    def test_large_affine_mismatch(self):
        a = Circuit(30, (Gate('cx', (0, 5)),))
        self.assertFalse(compare(a, Circuit(30, ()))['equivalent_up_to_global_phase'])

    def test_phase_identity_large(self):
        a = Circuit(20, (Gate('z', (0,)), Gate('z', (1,))))
        b = Circuit(20, (Gate('cx', (0, 1)), Gate('z', (1,)), Gate('cx', (0, 1))))
        # Numerically equal modulo phase but different parity expansion.
        # An inconclusive signature is allowed to fail closed, not to claim equality.
        try:
            report = compare(a, b)
        except ValueError as exc:
            self.assertIn('inconclusive', str(exc))
        else:
            self.assertTrue(report['equivalent_up_to_global_phase'])

    def test_huge_angle_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "above 1e6"):
            compare(Circuit(9, (Gate("rz", (0,), 1e100),)), Circuit(9, ()))

    def test_unsupported_large_fails_closed(self):
        with self.assertRaisesRegex(ValueError, 'only X, CX, Z, RZ'):
            compare(Circuit(9, (Gate('h', (0,)),)), Circuit(9, ()))

    def test_symbolic_phase_matches_dense_up_to_global(self):
        rng = random.Random(1199)
        for _ in range(40):
            gates = []
            for _ in range(25):
                op = rng.choice(('x', 'cx', 'z', 'rz'))
                q = tuple(rng.sample(range(3), 2)) if op == 'cx' else (rng.randrange(3),)
                gates.append(Gate(op, q, rng.uniform(-2, 2) if op == 'rz' else None))
            a = Circuit(3, tuple(gates))
            sig = affine_phase_signature(a)
            u = unitary(a)
            base_phase = None
            for x in range(8):
                y = 0
                for j, (row, off) in enumerate(zip(sig.rows, sig.offsets)):
                    y |= (((row & x).bit_count() & 1) ^ off) << j
                predicted = sum(angle for mask, angle in sig.coefficients if ((mask & x).bit_count() & 1))
                ratio = u[y, x] / np.exp(1j * predicted)
                if base_phase is None:
                    base_phase = ratio
                self.assertAlmostEqual(abs(ratio - base_phase), 0, places=10)
                self.assertAlmostEqual(abs(u[y, x]), 1.0, places=10)

    def test_cli_does_not_write_on_unsupported_verify(self):
        with tempfile.TemporaryDirectory() as tmp:
            p, out = Path(tmp) / 'in.json', Path(tmp) / 'out.json'
            Circuit(9, (Gate('h', (0,)),)).write(p)
            proc = subprocess.run([sys.executable, 'qforge.py', 'optimize', str(p), str(out), '--verify'],
                                  capture_output=True, text=True)
            self.assertEqual(proc.returncode, 2)
            self.assertFalse(out.exists())


if __name__ == '__main__':
    unittest.main()
