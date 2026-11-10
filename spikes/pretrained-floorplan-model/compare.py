"""Score vectorize.py output (IMAGE frame) against the source image and optional references.

Walls: rasterize the vector walls and compare with the image's dark pixels. That's a reference,
       not ground truth: dark threshold + small-component removal (see gt_walls).
Doors: optional. Match model openings against reference doors, either the <path>s in an
       index.html #doors group (path starts at the hinge, arc ends at the far jamb) or a JSON
       list of {name, a, b}. References are in the APP frame; pass --transform if that differs
       from the image frame.
Scale: optional. A plan config JSON lists labeled rooms (a point on open floor + labeled
       size in feet) and the expected px/ft. See configs/.

Usage:
  python compare.py --json walls_doors.image.json --image plan.png \
      [--ref-doors ../../index.html] [--plan-config configs/x.json] [--transform transform.json] \
      --out-json metrics.json --out-png wall_diff.png
"""
import argparse
import json
import re

import cv2
import numpy as np
from PIL import Image

W, H = 0, 0   # set from the image in main()


def raster_walls(walls):
    m = np.zeros((H, W), np.uint8)
    for w in walls:
        p, q, t = np.array(w["a"], float), np.array(w["b"], float), w["thickness"]
        d = q - p
        n = np.array([-d[1], d[0]]) / (np.hypot(*d) or 1) * t / 2
        # pixel (i, j) covers [j, j+1) x [i, i+1); shift by -0.5 so fillPoly samples centers
        pts = np.array([p + n, q + n, q - n, p - n]) - 0.5
        cv2.fillPoly(m, [np.round(pts * 16).astype(np.int32)], 1, shift=4)
    return m.astype(bool)


def gt_walls(gray, dark_thresh, min_area):
    """Dark pixels, minus small components (room-label text, the entry triangle)."""
    dark = (gray < dark_thresh).astype(np.uint8)
    n, lab, st, _ = cv2.connectedComponentsWithStats(dark, connectivity=8)
    keep = np.zeros(n, bool)
    keep[1:] = st[1:, cv2.CC_STAT_AREA] >= min_area
    return keep[lab]


def overlap(pred, gt, tol):
    k = np.ones((2 * tol + 1, 2 * tol + 1), np.uint8)
    gt_d = cv2.dilate(gt.astype(np.uint8), k).astype(bool)
    pr_d = cv2.dilate(pred.astype(np.uint8), k).astype(bool)
    prec = (pred & gt_d).sum() / max(pred.sum(), 1)
    rec = (gt & pr_d).sum() / max(gt.sum(), 1)
    return float(prec), float(rec)


def ref_doors(path, M_inv=None):
    """Reference doors from index.html (#doors paths) or a JSON list of {name, a, b}."""
    if path.endswith(".json"):
        out = [dict(d) for d in json.load(open(path))]
    else:
        out = hand_doors(path)
    if M_inv is not None:
        for d in out:
            d["a"], d["b"] = [list(M_inv @ np.array([*d[k], 1.0])) for k in ("a", "b")]
    return out


def hand_doors(index_html):
    g = re.search(r'<g id="doors".*?</g>', open(index_html).read(), re.S).group(0)
    out = []
    for name, d in re.findall(r"<!--\s*(.*?)\s*-->\s*<path d=\"([^\"]+)\"", g):
        nums = list(map(float, re.findall(r"-?\d+\.?\d*", d)))
        hinge, far = nums[0:2], nums[-2:]
        out.append({"name": name, "a": hinge, "b": far})
    return out


def seg_match(p, q, tol):
    """Openings match if both endpoints agree (in either order) within tol px."""
    p, q = {k: np.array(v, float) for k, v in p.items() if k in "ab"}, {k: np.array(v, float) for k, v in q.items() if k in "ab"}
    e1 = max(np.hypot(*(p["a"] - q["a"])), np.hypot(*(p["b"] - q["b"])))
    e2 = max(np.hypot(*(p["a"] - q["b"])), np.hypot(*(p["b"] - q["a"])))
    return min(e1, e2) <= tol, float(min(e1, e2))


def ray(mask, x, y, dx, dy):
    n = 0
    while 0 <= x < W and 0 <= y < H and not mask[y, x]:
        x += dx
        y += dy
        n += 1
    return n


def room_size(mask, pt, spread):
    x, y = pt
    ws, hs = [], []
    for o in np.linspace(-spread, spread, 9).round().astype(int):  # several parallel rays, take the median (rays may exit via a door gap)
        ws.append(ray(mask, x, y + o, -1, 0) + ray(mask, x + 1, y + o, 1, 0))
        hs.append(ray(mask, x + o, y, 0, -1) + ray(mask, x + o, y + 1, 0, 1))
    return float(np.median(ws)), float(np.median(hs))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", required=True)
    ap.add_argument("--image", required=True)
    ap.add_argument("--ref-doors", help="index.html with #doors, or JSON list of {name,a,b} (app frame)")
    ap.add_argument("--plan-config", help="JSON with px_per_ft and labeled rooms (image frame)")
    ap.add_argument("--transform", help="align.py output, to map reference doors app -> image")
    ap.add_argument("--dark", type=float, default=100, help="gray level below which a pixel is wall ink")
    ap.add_argument("--out-json", required=True)
    ap.add_argument("--out-png", required=True)
    a = ap.parse_args()

    global W, H
    data = json.load(open(a.json))
    assert data["frame"]["name"] == "image", "compare.py expects vectorize.py's image-frame JSON"
    gray = np.asarray(Image.open(a.image).convert("L")).astype(float)
    H, W = gray.shape
    T = data["source"].get("wall_thickness_px", 6.0)   # all tolerances scale with it
    pred, gt = raster_walls(data["walls"]), gt_walls(gray, a.dark, min_area=4 * T * T)

    # Windows are wall in the model output but drawn light in the image; score both ways.
    win = raster_walls([{**w, "thickness": 1.7 * T} for w in data["windows"]])
    res = {"wall_thickness_px": T, "walls": {}}
    for key, care in (("all", np.ones_like(gt)), ("excluding_window_spans", ~win)):
        p_, g_ = pred & care, gt & care
        inter, union = (p_ & g_).sum(), (p_ | g_).sum()
        r = {"pixel_iou": round(float(inter / union), 3),
             "pixel_precision": round(float(inter / p_.sum()), 3),
             "pixel_recall": round(float(inter / g_.sum()), 3)}
        for tol in (1, 2):
            pr, rc = overlap(p_, g_, tol)
            r[f"within_{tol}px"] = {"precision": round(pr, 3), "recall": round(rc, 3)}
        res["walls"][key] = r

    # Doors
    M_inv = None
    if a.transform:
        M = np.vstack([np.array(json.load(open(a.transform))["matrix"]), [0, 0, 1]])
        M_inv = np.linalg.inv(M)[:2]
    truth = ref_doors(a.ref_doors, M_inv) if a.ref_doors else []
    used, rows = set(), []
    for t in truth:
        best = None
        for i, d in enumerate(data["doors"] + data["windows"]):
            ok, err = seg_match(t, d, tol=1.5 * T)
            if ok and i not in used and (best is None or err < best[1]):
                best = (i, err)
        if best:
            used.add(best[0])
            d = (data["doors"] + data["windows"])[best[0]]
            rows.append({"door": t["name"], "found": True, "endpoint_err_px": round(best[1], 1),
                         "model_class": d["model_class"],
                         "heuristic_class": "door" if best[0] < len(data["doors"]) else "window"})
        else:
            rows.append({"door": t["name"], "found": False})
    extra = [d for i, d in enumerate(data["doors"]) if i not in used]
    res["doors"] = {
        "reference_doors": len(truth),
        "found_as_opening": sum(r["found"] for r in rows),
        "raw_model_called_door": sum(r.get("model_class") == "door" for r in rows),
        "heuristic_called_door": sum(r.get("heuristic_class") == "door" for r in rows),
        "extra_doors_not_in_reference": [{"a": d["a"], "b": d["b"]} for d in extra],
        "model_openings_total": len(data["doors"]) + len(data["windows"]),
        "per_door": rows,
    }

    # Scale check: interior size between wall faces vs. the labeled size.
    # With an expected px_per_ft this checks alignment; without one it estimates px/ft.
    res["scale_check"] = []
    if a.plan_config:
        cfg = json.load(open(a.plan_config))
        ppf = cfg.get("px_per_ft_image")
        for room in cfg["rooms"]:
            w, h = room_size(pred, room["point"], spread=3 * T)
            wf, hf = room["ft"]
            row = {"room": room["name"], "measured_px": [w, h],
                   "px_per_ft_from_room": [round(w / wf, 2), round(h / hf, 2)]}
            if ppf:
                row["ratio_to_expected"] = [round(w / (wf * ppf), 3), round(h / (hf * ppf), 3)]
            res["scale_check"].append(row)
        est = [v for r in res["scale_check"] for v in r["px_per_ft_from_room"]]
        res["px_per_ft_estimate_image"] = round(float(np.median(est)), 2) if est else None

    json.dump(res, open(a.out_json, "w"), indent=1)
    # diff image: black = agree, red = model only, blue = image only
    out = np.full((H, W, 3), 255, np.uint8)
    out[gt & pred] = (30, 30, 30)
    out[pred & ~gt] = (220, 40, 40)
    out[gt & ~pred] = (40, 90, 230)
    Image.fromarray(out).save(a.out_png)
    print(json.dumps({k: v for k, v in res.items() if k != "doors"}, indent=1))
    print({k: v for k, v in res["doors"].items() if k != "per_door"})
    for r in rows:
        print("  ", r)


if __name__ == "__main__":
    main()
