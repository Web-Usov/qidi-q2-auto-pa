import json, numpy as np, sys, os
sys.path.insert(0, os.getcwd())
from autopa_local.adaptive_matrix import analyse_adaptive_capture
p='capture_20260828-014917.npz'
d=np.load(p, allow_pickle=False)
meta=json.loads(str(d['meta']))
arr=np.asarray(d['samples'], dtype=float)
res=analyse_adaptive_capture(arr, meta, bootstrap=1000)
print('status', res.get('status'), res.get('reason'))
print('K', res.get('k_opt'), 'disc', res.get('discrete_k'))
print('segs', res.get('segments_included'), '/', res.get('segments_total'), 'dry_ratio', res.get('dry_ratio'), 'dir_div', res.get('direction_divergence'))
print('boot', res.get('bootstrap'))
for r in res['per_k']:
    print('%.4f cost=%s incl=%d/%d over=%s under=%s tail=%s settle=%s noise=%s high=%s' % (r['k'], r['cost'], r['included'], r['total'], r['overshoot'], r['undershoot'], r['tail_area'], r['settling_time'], r['baseline_noise_std'], r['high_level']))
