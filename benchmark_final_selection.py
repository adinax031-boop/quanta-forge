"""Paired raw-selection vs post-rewrite selection on seeded synthetic circuits."""
import json, platform
from benchmark_qf02 import make_circuits
from qforge import optimize
from qforge_compiler import metrics, route_line, route_line_persistent, route_line_best

rows = []
for name, _, original in make_circuits(seed=7251, cases=50):
    original, _ = optimize(original)
    old, _ = route_line(original)
    new, _ = route_line_persistent(original)
    raw = min((new, old), key=lambda c: len(c.gates))
    best, info = route_line_best(original)
    old, _ = optimize(old); new, _ = optimize(new)
    raw, _ = optimize(raw); best, _ = optimize(best)
    rows.append({'workload':name,'legacy_cx':metrics(old)['cx'], 'persistent_cx':metrics(new)['cx'],
                 'raw_selected_cx':metrics(raw)['cx'],'new_selected_cx':metrics(best)['cx'],
                 'selected':info['selected_router']})
print(json.dumps({'seed':7251,'cases':len(rows),'python':platform.python_version(),
 'totals':{k:sum(r[k] for r in rows) for k in ('legacy_cx','persistent_cx','raw_selected_cx','new_selected_cx')},
 'new_beats_raw':sum(r['new_selected_cx']<r['raw_selected_cx'] for r in rows),
 'new_worse_raw':sum(r['new_selected_cx']>r['raw_selected_cx'] for r in rows),
 'rows':rows},indent=2))
