import json, numpy as np, os, sys
sys.path.insert(0, os.getcwd())
from autopa_local.adaptive_matrix import analyse_adaptive_capture
from autopa_local import sweep_analysis as sa
p='capture_20260828-014917.npz'
d=np.load(p, allow_pickle=False); meta=json.loads(str(d['meta'])); arr=np.asarray(d['samples'], dtype=float)
res=analyse_adaptive_capture(arr, meta, bootstrap=0); rows=res['per_k']
def bd(rows):
 out=[]
 for row in rows:
  med={n: float('nan') for n in sa.BD_METRIC_NAMES}
  for k,v in row.items():
   if k in med and v is not None: med[k]=float(v)
  out.append(sa.BdKResult(k=float(row['k']), n_segments_total=int(row['total']), n_segments_included=int(row['included']), medians=med))
 return out
full=bd(rows); sa._bd_compute_normalised(full); full_norm={r.k:dict(r.normalised) for r in full}
for lo,hi in [(0.05,0.075),(0.045,0.075),(0.055,0.085)]:
 sub=[r for r in rows if lo-1e-9 <= r['k'] <= hi+1e-9]
 b=bd(sub); sa._bd_compute_normalised(b); bc=sa._bd_compute_cost(b,sa.BD_DEFAULT_WEIGHTS); ks=np.array([x.k for x in b]); ok=np.isfinite(bc)
 c=bd(sub)
 for rr in c: rr.normalised=full_norm[rr.k]
 cc=sa._bd_compute_cost(c,sa.BD_DEFAULT_WEIGHTS); okc=np.isfinite(cc)
 print('subset',lo,hi,'B disc',float(ks[ok][np.argmin(bc[ok])]),'B opt',sa._argmin_with_parabolic(ks[ok],bc[ok]),'C disc',float(ks[okc][np.argmin(cc[okc])]),'C opt',sa._argmin_with_parabolic(ks[okc],cc[okc]))
 print(' Bcost', ['%.4f:%.3f'%(k,v) for k,v in zip(ks,bc)])
 print(' Ccost', ['%.4f:%.3f'%(k,v) for k,v in zip(ks,cc)])
