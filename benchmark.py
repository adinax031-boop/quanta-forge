"""Deterministic synthetic benchmark; no claim about real-world workloads."""
import argparse, json, random, time
from qforge import Circuit, Gate, optimize, compare

def main():
    p=argparse.ArgumentParser(); p.add_argument('--seed',type=int,default=2026); p.add_argument('--cases',type=int,default=100); args=p.parse_args()
    if args.cases < 1: p.error('--cases must be positive')
    rng=random.Random(args.seed); before=after=verified=0; start=time.perf_counter()
    for _ in range(args.cases):
        gates=[]
        for _ in range(25):
            op=rng.choice(('h','x','z','rx','rz','cx'))
            if op=='cx': g=Gate(op,tuple(rng.sample(range(3),2)))
            else: g=Gate(op,(rng.randrange(3),),rng.uniform(-3,3) if op in ('rx','rz') else None)
            gates.append(g)
            # Deliberately inject cancellable pairs in a controlled synthetic workload.
            if rng.random()<0.3:
                gates.append(Gate(op,g.qubits,-g.angle if g.angle is not None else None))
        c=Circuit(3,tuple(gates)); out,_=optimize(c)
        before+=len(c.gates); after+=len(out.gates)
        verified+=compare(c,out)['equivalent_up_to_global_phase']
    print(json.dumps({'seed':args.seed,'cases':args.cases,'before':before,'after':after,'reduction_fraction':(before-after)/before,'verified':verified,'seconds':round(time.perf_counter()-start,3),'workload':'synthetic injected inverse pairs'},indent=2))
if __name__=='__main__': main()
