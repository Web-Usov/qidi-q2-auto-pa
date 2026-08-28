import json
import os
import sys

import numpy as np

sys.path.insert(0, os.getcwd())

from autopa_local.adaptive_matrix import analyse_adaptive_capture


def main() -> None:
    p = sys.argv[1]
    d = np.load(p, allow_pickle=False)
    meta = json.loads(str(d["meta"]))
    arr = np.asarray(d["samples"], dtype=float)
    res = analyse_adaptive_capture(arr, meta, bootstrap=1000)
    summary = {
        "status": res.get("status"),
        "reason": res.get("reason"),
        "k_opt": res.get("k_opt"),
        "discrete_k": res.get("discrete_k"),
        "segments_included": res.get("segments_included"),
        "segments_total": res.get("segments_total"),
        "dry_ratio": res.get("dry_ratio"),
        "direction_divergence": res.get("direction_divergence"),
        "sps": res.get("sample_rate"),
        "errors": meta.get("errors"),
        "capture": p,
        "meta": {
            k: meta.get(k)
            for k in [
                "speed",
                "flow",
                "accel",
                "x0",
                "x1",
                "y",
                "z",
                "kstart",
                "kend",
                "kstep",
                "cycles",
                "dry_cycles",
                "temp",
                "maxfilament",
            ]
        },
        "bootstrap": res.get("bootstrap"),
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    print("PERK")
    for r in res["per_k"]:
        print(
            "K %.4f cost %.6f incl %d/%d over %.6g under %.6g rise_delay %.6g "
            "fall_delay %.6g settle %.6g noise %.6g high %.6g low %.6g"
            % (
                r["k"],
                r["cost"],
                r["included"],
                r["total"],
                r["overshoot"],
                r["undershoot"],
                r.get("rise_delay", float("nan")),
                r.get("fall_delay", float("nan")),
                r["settling_time"],
                r["baseline_noise_std"],
                r.get("high_level", float("nan")),
                r.get("low_level", float("nan")),
            )
        )
    print("DIR")
    for item in res.get("direction_summary", []):
        print(item)


if __name__ == "__main__":
    main()
