"""Turn the CubiCasa5K prediction into simple wall / opening geometry in the app frame.

Walls:    from the model's "Wall" room-class mask. 45-degree runs (the bay window) are
          split off first with a diagonal-line opening and fitted with a min-area rectangle;
          the remaining horizontal and vertical runs become {a, b, thickness} segments.
          The Wall class runs through openings, so door spans are cut out afterwards.
Openings: from the official CubiCasa post-processing (floortrans.post_prosessing.get_polygons),
          which finds openings from junction heatmaps + icon segmentation. On this plan the
          model labels every opening "window" (doors here are drawn as plain gaps, not swing
          arcs). We keep that raw label and add a tiny, non-ML reclassification:
          a window glyph has glazing lines inside the wall band, a door is a plain white gap.

Usage:
  python vectorize.py --repo CUBICASA_SRC --pred pred_s2.npz --image original.png \
      --out walls_doors.json --render walls_doors.png
"""
import argparse
import json
import sys
import types

import cv2
import numpy as np
import scipy.stats
import torch
from PIL import Image

APP_W, APP_H, PX_PER_FT = 1194, 703, 16
MIN_RUN = 9          # px; a horizontal/vertical run must be at least this long to count
MIN_WALL_LEN = 6     # px; drop wall fragments shorter than this
MIN_THICK = 3        # px; thinner axis-aligned runs are slivers of diagonal walls
GLAZING_DARK = 170   # cross-wall profile darker than this => window glazing lines present


def official_openings(repo, pred):
    sys.path.insert(0, repo)
    import floortrans.post_prosessing as pp
    # The repo targets an old SciPy where stats.mode(...).mode was an array; shim it.
    pp.stats = types.SimpleNamespace(mode=lambda a: types.SimpleNamespace(
        mode=np.atleast_1d(scipy.stats.mode(a, keepdims=False).mode)))
    t = torch.from_numpy(pred.astype(np.float32))[None]
    h, w = t.shape[2:]
    heat, rooms, icons = pp.split_prediction(t, (h, w), [21, 12, 11])
    polys, kinds, _, _ = pp.get_polygons((heat, rooms, icons), 0.2, [1, 2])
    out = []
    for p, k in zip(polys, kinds):
        if k["type"] == "icon":   # openings come back as icon polygons, class 1=window 2=door
            out.append((np.asarray(p, float), {1: "window", 2: "door"}.get(k["class"], str(k["class"]))))
    return out


def opening_segment(poly, gray):
    x0, y0 = poly.min(0)
    x1, y1 = poly.max(0)
    horiz = (x1 - x0) >= (y1 - y0)
    if horiz:
        c = (y0 + y1) / 2
        a, b = [x0, c], [x1, c]
        lo, hi = int(x0 + (x1 - x0) / 5), int(x1 - (x1 - x0) / 5)
        ci = int(round(c))
        prof = gray[ci - 7:ci + 8, lo:hi].mean(1)
    else:
        c = (x0 + x1) / 2
        a, b = [c, y0], [c, y1]
        lo, hi = int(y0 + (y1 - y0) / 5), int(y1 - (y1 - y0) / 5)
        ci = int(round(c))
        prof = gray[lo:hi, ci - 7:ci + 8].mean(0)
    return a, b, float(prof.min())


def split_diagonals(mask, k=15):
    """45-degree walls: pixels covered by a k-long diagonal line that fits inside the mask.
    Axis-aligned walls (~6 px thick) and their corners can't hold one."""
    m = mask.astype(np.uint8)
    diag = np.zeros_like(m)
    for ker in (np.eye(k, dtype=np.uint8), np.fliplr(np.eye(k, dtype=np.uint8)).copy()):
        diag |= cv2.morphologyEx(m, cv2.MORPH_OPEN, ker)
    rest = m & (1 - cv2.dilate(diag, np.ones((3, 3), np.uint8)))
    return rest, diag


def hv_walls(mask):
    m = mask.astype(np.uint8)
    hm = cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((1, MIN_RUN), np.uint8))
    vm = cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((MIN_RUN, 1), np.uint8))
    walls = []
    for arr, horiz in ((hm, True), (vm, False)):
        n, lab, stats, _ = cv2.connectedComponentsWithStats(arr, connectivity=4)
        for i in range(1, n):
            x, y, w, h, area = stats[i]
            comp = lab[y:y + h, x:x + w] == i
            # thickness = median run across the wall; length = bbox extent along it
            if horiz:
                cols = comp.sum(0)
                t = float(np.median(cols[cols > 0]))
                rows = np.nonzero(comp.any(1))[0]
                cy = y + (rows.min() + rows.max() + 1) / 2
                seg = {"a": [x, cy], "b": [x + w, cy], "thickness": t}
                length = w
            else:
                rows = comp.sum(1)
                t = float(np.median(rows[rows > 0]))
                cols = np.nonzero(comp.any(0))[0]
                cx = x + (cols.min() + cols.max() + 1) / 2
                seg = {"a": [cx, y], "b": [cx, y + h], "thickness": t}
                length = h
            # Drop thin slivers left at the ends of diagonal runs.
            if length >= MIN_WALL_LEN and t >= MIN_THICK:
                walls.append(seg)
    return walls


def diagonal_walls(residual, min_area=30):
    walls = []
    n, lab, stats, _ = cv2.connectedComponentsWithStats(residual.astype(np.uint8), connectivity=8)
    for i in range(1, n):
        if stats[i, cv2.CC_STAT_AREA] < min_area:
            continue
        ys, xs = np.nonzero(lab == i)
        (cx, cy), (w, h), ang = cv2.minAreaRect(np.stack([xs, ys], 1).astype(np.float32))
        length, thick = max(w, h), min(w, h)
        if length < 2 * thick or length < MIN_WALL_LEN:
            continue   # a blob, not a wall
        theta = np.deg2rad(ang if w >= h else ang + 90)
        dx, dy = np.cos(theta) * length / 2, np.sin(theta) * length / 2
        walls.append({"a": [cx - dx + 0.5, cy - dy + 0.5], "b": [cx + dx + 0.5, cy + dy + 0.5],
                      "thickness": float(thick), "diagonal": True})
    return walls


def merge_collinear(walls, tol=2.0, gap=2.0):
    """Merge axis-aligned segments that sit on the same line and touch or overlap."""
    out, rest = [], [w for w in walls if w.get("diagonal")]
    for horiz in (True, False):
        k, j = (1, 0) if horiz else (0, 1)   # k = fixed coord index, j = running coord index
        segs = sorted((w for w in walls if not w.get("diagonal") and (w["a"][k] == w["b"][k])
                       and ((w["a"][j] != w["b"][j]))
                       and (abs(w["b"][0] - w["a"][0]) >= abs(w["b"][1] - w["a"][1])) == horiz),
                      key=lambda w: (round(w["a"][k]), w["a"][j]))
        cur = None
        for s in segs:
            if cur and abs(s["a"][k] - cur["a"][k]) <= tol and s["a"][j] <= cur["b"][j] + gap:
                cur["b"][j] = max(cur["b"][j], s["b"][j])
                cur["thickness"] = max(cur["thickness"], s["thickness"])
            else:
                if cur:
                    out.append(cur)
                cur = {"a": list(s["a"]), "b": list(s["b"]), "thickness": s["thickness"]}
        if cur:
            out.append(cur)
    return out + rest


def cut_doors(walls, doors, slack=2.0):
    """CubiCasa's Wall class runs through openings; cut each door span out of the
    axis-aligned wall it sits on so the gap is walkable. Windows stay as wall."""
    for d in doors:
        (ax, ay), (bx, by) = d["a"], d["b"]
        horiz = abs(bx - ax) >= abs(by - ay)
        j, k = (0, 1) if horiz else (1, 0)          # j = along the wall, k = across
        lo, hi = sorted((d["a"][j], d["b"][j]))
        c = (d["a"][k] + d["b"][k]) / 2
        out = []
        for w in walls:
            on_line = (not w.get("diagonal") and w["a"][k] == w["b"][k]
                       and abs(w["a"][k] - c) <= w["thickness"] / 2 + slack)
            w0, w1 = sorted((w["a"][j], w["b"][j]))
            if not on_line or w1 <= lo or w0 >= hi:
                out.append(w)
                continue
            for s0, s1 in ((w0, lo), (hi, w1)):
                if s1 - s0 >= MIN_WALL_LEN / 2:
                    a, b = list(w["a"]), list(w["b"])
                    a[j], b[j] = s0, s1
                    out.append({**w, "a": a, "b": b})
        walls = out
    return walls


def rnd(v, n=1):
    return [round(float(x), n) for x in v]


def render(data, path, scale=2):
    img = Image.new("RGB", (APP_W * scale, APP_H * scale), "white")
    a = np.asarray(img).copy()
    S = scale
    for w in data["walls"]:
        p, q, t = np.array(w["a"]) * S, np.array(w["b"]) * S, w["thickness"] * S
        d = q - p
        n = np.array([-d[1], d[0]]) / (np.hypot(*d) or 1) * t / 2
        pts = np.array([p + n, q + n, q - n, p - n]).astype(np.int32)
        cv2.fillPoly(a, [pts], (40, 40, 40))
    for w in data["windows"]:
        cv2.line(a, tuple(int(v * S) for v in w["a"]), tuple(int(v * S) for v in w["b"]), (60, 130, 230), 3 * S)
    for d in data["doors"]:
        cv2.line(a, tuple(int(v * S) for v in d["a"]), tuple(int(v * S) for v in d["b"]), (225, 120, 20), 4 * S)
        for e in (d["a"], d["b"]):
            cv2.circle(a, tuple(int(v * S) for v in e), 3 * S, (225, 120, 20), -1)
    Image.fromarray(a).save(path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    ap.add_argument("--pred", required=True)
    ap.add_argument("--image", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--render", required=True)
    a = ap.parse_args()

    d = np.load(a.pred)
    gray = np.asarray(Image.open(a.image).convert("L")).astype(float)
    assert gray.shape == (APP_H, APP_W), "expects the original 1194x703 image (identity transform)"

    wall_mask = d["room_argmax"] == 2
    axis_mask, diag_mask = split_diagonals(wall_mask)
    walls = merge_collinear(hv_walls(axis_mask) + diagonal_walls(diag_mask))

    doors, windows = [], []
    for poly, model_cls in official_openings(a.repo, d["pred"]):
        p, q, darkest = opening_segment(poly, gray)
        item = {"a": rnd(p), "b": rnd(q), "model_class": model_cls,
                "glazing_min": round(darkest)}
        (windows if darkest < GLAZING_DARK else doors).append(item)
    walls = cut_doors(walls, doors)

    data = {
        "frame": {"viewBox": [0, 0, APP_W, APP_H], "px_per_ft": PX_PER_FT},
        "source": {"model": "CubiCasa5K hg_furukawa_original (model_best_val_loss_var.pkl)",
                   "scale": float(d["scale"]), "tta": "4 rotations",
                   "transform_to_app": {"scale": 1, "offset": [0, 0]}},
        "door_rule": f"model opening; glazing_min >= {GLAZING_DARK} => door, else window",
        "walls": [{"a": rnd(w["a"]), "b": rnd(w["b"]), "thickness": round(w["thickness"], 1)} for w in walls],
        "doors": doors,
        "windows": windows,
    }
    json.dump(data, open(a.out, "w"), indent=1)
    render(data, a.render)
    print(f"{len(data['walls'])} walls, {len(doors)} doors, {len(windows)} windows -> {a.out}, {a.render}")


if __name__ == "__main__":
    main()
