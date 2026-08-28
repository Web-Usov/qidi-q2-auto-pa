import json
import sys

r = json.load(open(sys.argv[1], encoding="utf-8"))
for section in ["window", "accel"]:
    vals = []
    for k, dirs in r["coverage"]["wet"].items():
        for d, cov in dirs.items():
            c = cov[section]
            vals.append(c)
    print("wet", section)
    for key in ["samples", "unique_2ms", "unique_5ms", "phase_p05_ms", "phase_p50_ms", "phase_p95_ms"]:
        xs = [v[key] for v in vals if key in v]
        print(key, min(xs), max(xs))
for section in ["window", "accel"]:
    vals = []
    for d, cov in r["coverage"]["dry"].items():
        vals.append(cov[section])
    print("dry", section)
    for key in ["samples", "unique_2ms", "unique_5ms", "phase_p05_ms", "phase_p50_ms", "phase_p95_ms"]:
        xs = [v[key] for v in vals if key in v]
        print(key, min(xs), max(xs))
