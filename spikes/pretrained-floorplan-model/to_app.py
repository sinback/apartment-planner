"""Map vectorize.py output from the image frame into the app frame.

Usage:
  python to_app.py --json walls_doors.image.json --transform transform.json \
      --px-per-ft 16 --out walls_doors.json
Without --transform the image frame is used as-is (identity).
"""
import argparse
import json

import numpy as np


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", required=True)
    ap.add_argument("--transform")
    ap.add_argument("--px-per-ft", type=float, default=16)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    d = json.load(open(a.json))
    if a.transform:
        t = json.load(open(a.transform))
        M, s, size = np.array(t["matrix"]), t["scale"], t["app_size"]
    else:
        t, M, s = None, np.array([[1, 0, 0], [0, 1, 0]], float), 1.0
        size = d["frame"]["viewBox"][2:]

    def pt(p):
        return [round(float(v), 1) for v in M @ np.array([p[0], p[1], 1.0])]

    for key in ("walls", "doors", "windows"):
        for item in d[key]:
            item["a"], item["b"] = pt(item["a"]), pt(item["b"])
            if "thickness" in item:
                item["thickness"] = round(item["thickness"] * s, 1)
    d["frame"] = {"name": "app", "viewBox": [0, 0, *size], "px_per_ft": a.px_per_ft}
    d["source"]["transform_to_app"] = (
        {"scale": t["scale"], "rotation_deg": t["rotation_deg"], "offset": t["offset"]}
        if t else {"scale": 1, "rotation_deg": 0, "offset": [0, 0]})
    json.dump(d, open(a.out, "w"), indent=1)
    print(f"-> {a.out} ({d['source']['transform_to_app']})")


if __name__ == "__main__":
    main()
