import json
import sys

r = json.load(open(sys.argv[1], encoding="utf-8"))
print("t_acc_ms", r["t_acc"] * 1000.0, "duration_ms", r["duration"] * 1000.0)
print("Kopt", r["k_opt"], "disc", r["discrete_k"])
print("direction", r["direction"])
print("costs")
for x in r["per_k"]:
    print(
        "{:.4f} cost={} incl={}/{} over={} under={} high={} noise={}".format(
            x["k"],
            x["cost"],
            x["included"],
            x["total"],
            x["overshoot"],
            x["undershoot"],
            x["high_level"],
            x["baseline_noise_std"],
        )
    )

print("coverage sample")
for k in ["0.0250", "0.0475", "0.0525", "0.0600", "0.0850"]:
    print("K", k, r["coverage"]["wet"][k])
print("dry", r["coverage"]["dry"])
