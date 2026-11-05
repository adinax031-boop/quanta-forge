import random
import unittest
from qforge import Circuit, Gate, compare
from qforge_compiler import route_line_persistent, route_line, route_line_best, metrics


class PersistentRoutingTests(unittest.TestCase):
    def test_all_short_cx_sequences(self):
        import itertools
        for n in range(2, 5):
            pairs = list(itertools.permutations(range(n), 2))
            for seq in itertools.product(pairs, repeat=2):
                original = Circuit(n, tuple(Gate('cx', p) for p in seq))
                routed, _ = route_line_persistent(original)
                self.assertTrue(compare(original, routed)['equivalent_up_to_global_phase'])
                self.assertTrue(all(abs(g.qubits[0] - g.qubits[1]) == 1 for g in routed.gates))

    def test_mixed_random_circuits(self):
        rng = random.Random(603)
        for n in range(2, 6):
            for _ in range(30):
                gates = []
                for _ in range(20):
                    if rng.randrange(2):
                        gates.append(Gate('cx', tuple(rng.sample(range(n), 2))))
                    else:
                        gates.append(Gate('h', (rng.randrange(n),)))
                original = Circuit(n, tuple(gates))
                routed, _ = route_line_persistent(original)
                self.assertTrue(compare(original, routed)['equivalent_up_to_global_phase'])

    def test_repeated_remote_gate_reduces_cost(self):
        original = Circuit(5, tuple(Gate('cx', (0, 4)) for _ in range(8)))
        old, _ = route_line(original)
        new, _ = route_line_persistent(original)
        self.assertLess(metrics(new)['cx'], metrics(old)['cx'])
        self.assertTrue(compare(original, new)['equivalent_up_to_global_phase'])

    def test_adaptive_is_never_larger_than_either_router(self):
        from benchmark_qf02 import make_circuits
        for _, _, circuit in make_circuits(seed=7251, cases=50):
            old, _ = route_line(circuit)
            new, _ = route_line_persistent(circuit)
            best, _ = route_line_best(circuit)
            self.assertLessEqual(len(best.gates), min(len(old.gates), len(new.gates)))
            self.assertTrue(compare(circuit, best)['equivalent_up_to_global_phase'])
