import json
import sys

r = json.load(open(sys.argv[1], encoding="utf-8"))
print("Kopt", r["k_opt"], "disc", r["discrete_k"])
print("bootstrap", r["bootstrap"])
print("direction", {k: {"disc": v["discrete"], "k_opt": v["k_opt"]} for k, v in r["direction"].items()})
print("cost")
for x in r["per_k"]:
    cost = x["cost"]
    print(
        "{:.4f} {} incl={}/{} over={} under={} high={} noise={}".format(
            x["k"],
            "None" if cost is None else "{:.6f}".format(cost),
            x["included"],
            x["total"],
            x["overshoot"],
            x["undershoot"],
            x["high_level"],
            x["baseline_noise_std"],
        )
    )
