import json, numpy as np, os, sys, copy
sys.path.insert(0, os.getcwd())
from autopa_local.adaptive_matrix import analyse_adaptive_capture
from autopa_local import sweep_analysis as sa
p='capture_20260828-014917.npz'
d=np.load(p, allow_pickle=False)
meta=json.loads(str(d['meta']))
arr=np.asarray(d['samples'], dtype=float)
res=analyse_adaptive_capture(arr, meta, bootstrap=0)
print('A full status', res['status'], res.get('reason'), 'K', res.get('k_opt'), 'disc', res.get('discrete_k'))
full_rows=res['per_k']
for r in full_rows:
    print('A %.4f %.6f %d/%d' % (r['k'], r['cost'] if r['cost'] is not None else float('nan'), r['included'], r['total']))
# Rebuild BdKResult from per_k raw medians for B/C.
def rows_to_bd(rows):
    out=[]
    for row in rows:
        med={n: float('nan') for n in sa.BD_METRIC_NAMES}
        for k,v in row.items():
            if k in med and v is not None: med[k]=float(v)
        out.append(sa.BdKResult(k=float(row['k']), n_segments_total=int(row['total']), n_segments_included=int(row['included']), medians=med))
    return out
subset=[r for r in full_rows if 0.0575-1e-9 <= r['k'] <= 0.0725+1e-9]
# B subset renormalized on subset
b=rows_to_bd(subset)
sa._bd_compute_normalised(b)
bcost=sa._bd_compute_cost(b, sa.BD_DEFAULT_WEIGHTS)
ks=np.array([x.k for x in b])
ok=np.isfinite(bcost)
print('B subset-renorm K', sa._argmin_with_parabolic(ks[ok], bcost[ok]), 'disc', float(ks[ok][np.argmin(bcost[ok])]))
for r,c in zip(b,bcost): print('B %.4f %.6f %d/%d' % (r.k, c if np.isfinite(c) else float('nan'), r.n_segments_included, r.n_segments_total))
# C subset with full-grid denominators: compute normalised full, then take subset
full_bd=rows_to_bd(full_rows)
sa._bd_compute_normalised(full_bd)
full_norm_by_k={r.k: r.normalised for r in full_bd}
c=[]
for row in subset:
    med={n: float('nan') for n in sa.BD_METRIC_NAMES}
    rr=sa.BdKResult(k=float(row['k']), n_segments_total=int(row['total']), n_segments_included=int(row['included']), medians=med)
    rr.normalised=dict(full_norm_by_k[float(row['k'])])
    c.append(rr)
ccost=sa._bd_compute_cost(c, sa.BD_DEFAULT_WEIGHTS)
cks=np.array([x.k for x in c]); cok=np.isfinite(ccost)
print('C subset-fullnorm K', sa._argmin_with_parabolic(cks[cok], ccost[cok]), 'disc', float(cks[cok][np.argmin(ccost[cok])]))
for r,cost in zip(c,ccost): print('C %.4f %.6f %d/%d' % (r.k, cost if np.isfinite(cost) else float('nan'), r.n_segments_included, r.n_segments_total))
