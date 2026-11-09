"""Score the model's walls/doors against the source image and the app's hand-placed doors.

Walls: rasterize the vector walls and compare with the image's dark wall pixels (ground truth).
Doors: match model door openings against the 10 <path>s in index.html's #doors group
       (each path starts at the hinge; the arc ends at the far jamb).
Scale: measure a few labeled rooms between wall faces at 16 px/ft.

Usage:
  python compare.py --json walls_doors.json --image original.png --index ../../index.html \
      --out-json metrics.json --out-png wall_diff.png
"""
import argparse
import json
import re

import cv2
import numpy as np
from PIL import Image

W, H, PX_PER_FT = 1194, 703, 16

ROOMS = {  # label point (in a room's open floor) -> dimension label from the image (w x h)
    "Bedroom 22'9\" x 11'2\"": ((290, 260), (22 + 9 / 12, 11 + 2 / 12)),
    "Bedroom 11'9\" x 10'2\"": ((201, 480), (11 + 9 / 12, 10 + 2 / 12)),
    "Kitchen 12'3\" x 13'5\"": ((465, 470), (12 + 3 / 12, 13 + 5 / 12)),
    "Living Room 13'1\" x 15'4\"": ((673, 360), (13 + 1 / 12, 15 + 4 / 12)),
    "Bathroom 8'4\" x 6'4\"": ((660, 510), (8 + 4 / 12, 6 + 4 / 12)),
    "Office 9'4\" x 6'5\"": ((958, 510), (9 + 4 / 12, 6 + 5 / 12)),
}


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


def gt_walls(gray):
    """Dark pixels, minus small components (room-label text, the entry triangle)."""
    dark = (gray < 100).astype(np.uint8)
    n, lab, st, _ = cv2.connectedComponentsWithStats(dark, connectivity=8)
    keep = np.zeros(n, bool)
    keep[1:] = st[1:, cv2.CC_STAT_AREA] >= 150
    return keep[lab]


def overlap(pred, gt, tol):
    k = np.ones((2 * tol + 1, 2 * tol + 1), np.uint8)
    gt_d = cv2.dilate(gt.astype(np.uint8), k).astype(bool)
    pr_d = cv2.dilate(pred.astype(np.uint8), k).astype(bool)
    prec = (pred & gt_d).sum() / max(pred.sum(), 1)
    rec = (gt & pr_d).sum() / max(gt.sum(), 1)
    return float(prec), float(rec)


def hand_doors(index_html):
    g = re.search(r'<g id="doors".*?</g>', open(index_html).read(), re.S).group(0)
    out = []
    for name, d in re.findall(r"<!--\s*(.*?)\s*-->\s*<path d=\"([^\"]+)\"", g):
        nums = list(map(float, re.findall(r"-?\d+\.?\d*", d)))
        hinge, far = nums[0:2], nums[-2:]
        out.append({"name": name, "a": hinge, "b": far})
    return out


def seg_match(p, q, tol=8):
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


def room_size(mask, pt):
    x, y = pt
    ws, hs = [], []
    for o in range(-20, 21, 5):  # several parallel rays, take the median (rays may exit via a door gap)
        ws.append(ray(mask, x, y + o, -1, 0) + ray(mask, x + 1, y + o, 1, 0))
        hs.append(ray(mask, x + o, y, 0, -1) + ray(mask, x + o, y + 1, 0, 1))
    return float(np.median(ws)), float(np.median(hs))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", required=True)
    ap.add_argument("--image", required=True)
    ap.add_argument("--index", required=True)
    ap.add_argument("--out-json", required=True)
    ap.add_argument("--out-png", required=True)
    a = ap.parse_args()

    data = json.load(open(a.json))
    gray = np.asarray(Image.open(a.image).convert("L")).astype(float)
    pred, gt = raster_walls(data["walls"]), gt_walls(gray)

    # Windows are wall in the model output but drawn light in the image; score both ways.
    win = raster_walls([{**w, "thickness": 10} for w in data["windows"]])
    res = {"walls": {}}
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
    truth = hand_doors(a.index)
    used, rows = set(), []
    for t in truth:
        best = None
        for i, d in enumerate(data["doors"] + data["windows"]):
            ok, err = seg_match(t, d)
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
        "hand_placed": len(truth),
        "found_as_opening": sum(r["found"] for r in rows),
        "raw_model_called_door": sum(r.get("model_class") == "door" for r in rows),
        "heuristic_called_door": sum(r.get("heuristic_class") == "door" for r in rows),
        "extra_doors_not_in_app": [{"a": d["a"], "b": d["b"]} for d in extra],
        "per_door": rows,
    }

    # Scale check
    res["scale_check"] = []
    for name, (pt, (wf, hf)) in ROOMS.items():
        w, h = room_size(pred, pt)
        res["scale_check"].append({"room": name, "measured_px": [w, h],
                                   "expected_px": [round(wf * PX_PER_FT, 1), round(hf * PX_PER_FT, 1)],
                                   "ratio": [round(w / (wf * PX_PER_FT), 3), round(h / (hf * PX_PER_FT), 3)]})

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
