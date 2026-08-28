import numpy as np,json
p='capture_20260828-014917.npz'
d=np.load(p,allow_pickle=False)
meta=json.loads(str(d['meta'])); stats=json.loads(str(d['stats']))
print('files',d.files)
print('stats status', stats.get('status'), stats.get('reason'), stats.get('segments_included'), stats.get('segments_total'))
print('speed flow accel', meta.get('speed'), meta.get('flow'), meta.get('accel'))
print('k_values', meta.get('k_values'))
print('dry legs', len(meta.get('dry_legs',[])), 'wet legs', len(meta.get('wet_legs',[])))
arr=d['samples']; print('samples', arr.shape, 't span', arr[0,0], arr[-1,0], 'rate', (len(arr)-1)/(arr[-1,0]-arr[0,0]))
print('errors', meta.get('errors'))
print('first/last rows', arr[0], arr[-1])
for row in stats.get('per_k',[])[:20]: print(row)
