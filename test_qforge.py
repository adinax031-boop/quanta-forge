import math
import random
import unittest
from qforge import Circuit, Gate, optimize, compare
from qforge import unitary

class Tests(unittest.TestCase):
    def test_disjoint_cancellation_and_blocker(self):
        a = Circuit(2,(Gate('h',(0,)),Gate('x',(1,)),Gate('h',(0,))))
        b, stats = optimize(a)
        self.assertEqual(b.gates,(Gate('x',(1,)),))
        self.assertEqual(stats['pairs_cancelled'],1)
        blocked = Circuit(2,(Gate('h',(0,)),Gate('cx',(0,1)),Gate('h',(0,))))
        self.assertEqual(optimize(blocked)[0],blocked)
    def test_rotation_fusion(self):
        a = Circuit(1,(Gate('rz',(0,),0.25),Gate('rz',(0,),-0.25)))
        self.assertEqual(optimize(a)[0].gates,())
    def test_cx_direction(self):
        a=Circuit(2,(Gate('cx',(0,1)),Gate('cx',(1,0))))
        self.assertEqual(optimize(a)[0],a)
        self.assertFalse(compare(Circuit(2,(a.gates[0],)),Circuit(2,(a.gates[1],)))['equivalent_up_to_global_phase'])
    def test_input_validation(self):
        for f in (lambda: Gate('rx',(0,),float('nan')), lambda: Gate('cx',(0,0)), lambda: Circuit(1,(Gate('h',(1,)),)), lambda: Gate('h',(True,))):
            with self.assertRaises(ValueError): f()
        with self.assertRaises(ValueError): unitary(Circuit(9,()))
    def test_known_h_squared(self):
        self.assertTrue(compare(Circuit(1,(Gate('h',(0,)),Gate('h',(0,)))),Circuit(1,()))['equivalent_up_to_global_phase'])
        self.assertFalse(compare(Circuit(1,(Gate('x',(0,)),)),Circuit(1,()))['equivalent_up_to_global_phase'])
    def test_seeded_random_circuits(self):
        rng=random.Random(731)
        for _ in range(100):
            gates=[]
            for _ in range(35):
                op=rng.choice(('h','x','z','rx','rz','cx'))
                if op=='cx': gates.append(Gate(op,tuple(rng.sample(range(3),2))))
                else: gates.append(Gate(op,(rng.randrange(3),),rng.uniform(-3,3) if op in ('rx','rz') else None))
            a=Circuit(3,tuple(gates)); b,_=optimize(a)
            self.assertTrue(compare(a,b)['equivalent_up_to_global_phase'])
            self.assertLessEqual(len(b.gates),len(a.gates))
    def test_json_roundtrip(self):
        a=Circuit(2,(Gate('rx',(1,),math.pi),))
        self.assertEqual(a,Circuit.from_dict(a.to_dict()))
if __name__=='__main__': unittest.main()
