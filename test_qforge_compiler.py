"""QF-02: independent semantic, QASM, routing and pipeline regression tests."""
import math
import random
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

from qforge import Circuit, Gate, compare, unitary
from qforge_qasm import parse_qasm, emit_qasm, angle_value
from qforge_compiler import metrics, PassManager, compile_circuit, route_line


def independent_dense_matrix(circuit):
    """Separate gate-embedding oracle; does not call qforge.unitary/compare."""
    size = 1 << circuit.qubits
    u = np.eye(size, dtype=np.complex128)
    for gate in circuit.gates:
        if gate.op == 'cx':
            c, t = gate.qubits
            perm = np.zeros((size, size), dtype=np.complex128)
            for i in range(size):
                perm[i ^ ((1 << t) if ((i >> c) & 1) else 0), i] = 1
            u = perm @ u
            continue
        if gate.op == 'h':
            local = np.array([[1, 1], [1, -1]], dtype=complex) / math.sqrt(2)
        elif gate.op == 'x':
            local = np.array([[0,1],[1,0]], dtype=complex)
        elif gate.op == 'z':
            local = np.diag([1,-1]).astype(complex)
        elif gate.op == 'rx':
            c,s = math.cos(gate.angle/2), math.sin(gate.angle/2)
            local = np.array([[c,-1j*s],[-1j*s,c]], dtype=complex)
        elif gate.op == 'rz':
            local = np.diag([np.exp(-.5j*gate.angle),np.exp(.5j*gate.angle)])
        else:
            raise AssertionError('unexpected gate')
        operators = [local if q == gate.qubits[0] else np.eye(2) for q in reversed(range(circuit.qubits))]
        full = operators[0]
        for part in operators[1:]:
            full = np.kron(full,part)
        u = full @ u
    return u


class IndependentOracleTests(unittest.TestCase):
    def test_random_qasm_compilation_matches_independent_matrix(self):
        rng = random.Random(97731)
        for _ in range(60):
            n = rng.randint(2,4)
            gates = []
            for _ in range(16):
                op = rng.choice(('h','x','z','rx','rz','cx'))
                if op == 'cx': gates.append(Gate(op,tuple(rng.sample(range(n),2))))
                else: gates.append(Gate(op,(rng.randrange(n),),rng.uniform(-2,2) if op in ('rx','rz') else None))
            original = Circuit(n,tuple(gates))
            imported = parse_qasm(emit_qasm(original))
            for topology in ('all','line'):
                candidate, _ = compile_circuit(imported,topology=topology,verify=True)
                np.testing.assert_allclose(independent_dense_matrix(original), independent_dense_matrix(candidate), atol=1e-10, rtol=0)


class QASMTests(unittest.TestCase):
    def test_known_p_gate_global_phase(self):
        c = parse_qasm('OPENQASM 2.0; include "qelib1.inc"; qreg q[1]; p(pi/4) q[0];')
        self.assertAlmostEqual(c.gates[0].angle, math.pi / 4)
        actual = unitary(c)
        expected = np.diag([1.0, np.exp(1j * math.pi/4)])
        phase = np.vdot(actual, expected) / abs(np.vdot(actual, expected))
        self.assertLess(np.max(np.abs(expected - phase * actual)), 1e-12)

    def test_s_and_t_gates_have_correct_relative_phase(self):
        for op, theta in [('s',math.pi/2), ('sdg',-math.pi/2), ('t',math.pi/4), ('tdg',-math.pi/4)]:
            c = parse_qasm(f'OPENQASM 2.0; qreg q[1]; {op} q[0];')
            expected = np.diag([1, np.exp(1j * theta)])
            actual = unitary(c)
            phase = np.vdot(actual, expected) / abs(np.vdot(actual, expected))
            self.assertLess(np.max(np.abs(expected - phase * actual)), 1e-12, op)

    def test_supported_arithmetic_and_angle_roundtrip(self):
        self.assertAlmostEqual(angle_value('pi/2+pi/4'), 3*math.pi/4)
        self.assertAlmostEqual(angle_value('-(3*pi)/4'), -3*math.pi/4)
        self.assertEqual(angle_value('.25'), 0.25)
        for theta in [0.0, -0.0, math.pi/2, 1e-19, -1e7, 1.23456789012345]:
            original = Circuit(2, (Gate('rx', (0,), theta), Gate('rz', (1,), -theta)))
            restored = parse_qasm(emit_qasm(original))
            self.assertEqual(restored, original)

    def test_reject_unsupported_and_harmful_syntax(self):
        invalid = [
            'OPENQASM 2.0; qreg q[2]; measure q[0] -> c[0];',
            'OPENQASM 2.0; qreg q[2]; barrier q;',
            'OPENQASM 2.0; qreg q[2]; qreg q[3];',
            'OPENQASM 2.0; qreg q[2]; cx q[1],q[1];',
            'OPENQASM 2.0; qreg q[2]; h q[2];',
            'OPENQASM 2.0; qreg q[2]; rz(1/0) q[0];',
            'OPENQASM 2.0; qreg q[2]; rz(__import__("os")) q[0];',
            'OPENQASM 2.0; qreg q[2]; rx(10**100) q[0];',
            'OPENQASM 2.0; qreg q[2]; rx(1e500) q[0];',
            'OPENQASM 2.0; qreg q[0]; h q[0];',
            'OPENQASM 2.0; qreg q[2]; h q[0]',
            'OPENQASM 3.0; qubit[2] q;',
            'OPENQASM 2.0; include "private.inc"; qreg q[2];',
        ]
        for program in invalid:
            with self.subTest(program=program), self.assertRaises(ValueError):
                parse_qasm(program)

    def test_comments_and_reject_nonfinite_rotation(self):
        c = parse_qasm('OPENQASM 2.0; // hello\n include "qelib1.inc"; /*hi*/ qreg q[2]; cx q[0],q[1];')
        self.assertEqual(c, Circuit(2, (Gate('cx', (0, 1)),)))
        with self.assertRaises(ValueError):
            angle_value('1e999')

    def test_import_random_units_and_circuit_roundtrip(self):
        rng = random.Random(2202)
        for _ in range(100):
            n = rng.randint(2, 6)
            gates = []
            for _ in range(25):
                op = rng.choice(['h','x','z','rx','rz','cx'])
                if op == 'cx': gates.append(Gate(op, tuple(rng.sample(range(n), 2))))
                else: gates.append(Gate(op, (rng.randrange(n),), rng.uniform(-5,5) if op in ('rx','rz') else None))
            original = Circuit(n, tuple(gates))
            restored = parse_qasm(emit_qasm(original))
            self.assertEqual(original, restored)
            self.assertTrue(compare(original, restored)['equivalent_up_to_global_phase'])


class RoutingTests(unittest.TestCase):
    def test_all_directed_pairs_2_through_6_qubits(self):
        for n in range(2,7):
            for control in range(n):
                for target in range(n):
                    if control == target: continue
                    original = Circuit(n,(Gate('h',(control,)),Gate('cx',(control,target)), Gate('rz',(target,),0.75)))
                    routed, stats = route_line(original)
                    self.assertTrue(all(abs(g.qubits[0]-g.qubits[1]) == 1 for g in routed.gates if g.op == 'cx'))
                    self.assertTrue(compare(original,routed)['equivalent_up_to_global_phase'],(n,control,target))
                    self.assertEqual(stats['remote_cx_routed'], int(abs(control-target)>1))

    def test_random_entangled_circuits(self):
        rng = random.Random(2718)
        for _ in range(75):
            n = rng.randint(2,6)
            gates = []
            for _ in range(14):
                op = rng.choice(('h','rx','rz','cx','x'))
                if op == 'cx': gates.append(Gate(op, tuple(rng.sample(range(n),2))))
                else: gates.append(Gate(op,(rng.randrange(n),),rng.uniform(-2,2) if op in ('rx','rz') else None))
            original = Circuit(n,tuple(gates))
            candidate,report = compile_circuit(original,topology='line',verify=True)
            self.assertTrue(report['verification']['equivalent_up_to_global_phase'])
            self.assertTrue(all(abs(g.qubits[0]-g.qubits[1]) == 1 for g in candidate.gates if g.op == 'cx'))

    def test_reject_expensive_line_routing(self):
        original = Circuit(60_000,(Gate('cx',(0,59_999)),))
        with self.assertRaisesRegex(ValueError,'would emit'):
            route_line(original)

    def test_large_affine_routing_and_phase_verifier(self):
        c = Circuit(20,(Gate('cx',(0,19)),Gate('x',(10,)),Gate('rz',(0,),0.23),Gate('cx',(18,9))))
        candidate,report = compile_circuit(c,topology='line',verify=True)
        self.assertTrue(report['verification']['equivalent_up_to_global_phase'])
        self.assertIn('phase-polynomial', report['verification']['method'])
        self.assertGreater(report['output']['cx'],report['input']['cx'])


class PipelineTests(unittest.TestCase):
    def test_depth_counts_parallel_gates(self):
        circuit = Circuit(3,(Gate('h',(0,)),Gate('x',(1,)),Gate('cx',(0,2)),Gate('rz',(1,),.3)))
        self.assertEqual(metrics(circuit)['depth'],2)
        self.assertEqual(metrics(circuit)['cx'],1)

    def test_pass_names_are_unique(self):
        pm = PassManager().append('id',lambda c:(c,{}))
        with self.assertRaisesRegex(ValueError,'unique'):
            pm.append('id',lambda c:(c,{}))
        c = Circuit(1,())
        result,history = pm.run(c)
        self.assertEqual(result,c)
        self.assertEqual(len(history),1)

    def test_compiler_rejects_change_of_width(self):
        pm = PassManager().append('broken',lambda c:(Circuit(c.qubits+1,()),{}))
        with self.assertRaisesRegex(ValueError,'width'):
            pm.run(Circuit(1,()))

    def test_cli_qasm_to_json_compilation(self):
        with tempfile.TemporaryDirectory() as d:
            source, target = Path(d)/'in.qasm',Path(d)/'out.json'
            source.write_text('OPENQASM 2.0; qreg q[3]; h q[0]; cx q[0],q[2]; cx q[0],q[2];')
            cmd = [sys.executable, '-m','qforge', 'compile',str(source),str(target),'--topology','line','--verify']
            proc = subprocess.run(cmd, capture_output=True,text=True)
            self.assertEqual(proc.returncode,0,proc.stderr)
            c = Circuit.read(target)
            self.assertEqual(c.gates,(Gate('h',(0,)),))

    def test_cli_failure_cannot_overwrite_existing(self):
        with tempfile.TemporaryDirectory() as d:
            source, target = Path(d)/'in.qasm',Path(d)/'out.qasm'
            source.write_text('OPENQASM 2.0; qreg q[9]; h q[0];')
            target.write_text('preserve this')
            cmd = [sys.executable,'-m','qforge','compile',str(source),str(target),'--verify']
            proc = subprocess.run(cmd,capture_output=True,text=True)
            self.assertEqual(proc.returncode,2)
            self.assertEqual(target.read_text(),'preserve this')
            self.assertIn('supports only',proc.stderr)

    def test_compiler_verifier_propagates_failure(self):
        a = Circuit(2,(Gate('h',(0,)),Gate('cx',(0,1))))
        c,report = compile_circuit(a,topology='all',verify=True)
        self.assertTrue(report['verification']['equivalent_up_to_global_phase'])
        self.assertEqual(c.qubits,2)

    def test_sample_qasm_line_output_is_roundtrippable(self):
        a = parse_qasm('OPENQASM 2.0; qreg q[4]; s q[0]; cx q[0],q[3]; t q[3];')
        b,report = compile_circuit(a,topology='line',verify=True)
        self.assertEqual(b,parse_qasm(emit_qasm(b)))
        self.assertEqual(report['passes'][1]['details']['swaps_inserted'],4)


if __name__ == '__main__':
    unittest.main()
