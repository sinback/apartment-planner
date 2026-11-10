"""Turn the CubiCasa5K prediction into simple wall / opening geometry, in the IMAGE's pixel frame.
(to_app.py maps it into the app's frame afterwards.)

Pixel thresholds scale with wall thickness, so the same code works at other resolutions. There
are TWO thicknesses, and mixing them up breaks things (see wall_thickness):
  - mask thickness: walls in the model's mask. Used for every morphology step ON the mask.
  - ink thickness:  walls as drawn in the image. Used for steps on the image (glazing profile)
                    and for scoring tolerances.
At 6 px (the first plan at 2x, where both agree) they reduce to the values tuned on that plan
(min run 9, diagonal kernel 15, ...).

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
  python vectorize.py --repo CUBICASA_SRC --pred pred.npz --image plan.png \
      --out walls_doors.image.json --render walls_doors.png [--glazing-dark 170 | --no-glazing]
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

# Thresholds as multiples of the wall thickness T (values in brackets are for T = 6 px).
RUN_K = 1.5          # an H/V run must be >= 1.5 T long to count            [9]
MIN_LEN_K = 1.0      # drop wall fragments shorter than T                    [6]
MIN_THICK_K = 0.5    # thinner H/V runs are slivers of diagonal walls        [3]
DIAG_K = 2.5         # diagonal-line kernel length for 45-degree walls       [15]
PROFILE_K = 1.2      # half-width of the cross-wall profile at openings      [7]
GLAZING_DARK = 170   # cross-wall profile darker than this => glazing lines => window


def _cross_runs(m, k):
    """Run lengths ACROSS walls: vertical runs inside horizontal walls and vice versa."""
    m = m.astype(np.uint8)
    hm = cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((1, k), np.uint8))
    vm = cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((k, 1), np.uint8))
    out = []
    for arr in (hm, vm.T):
        d = np.diff(np.pad(arr.astype(np.int8), ((1, 1), (0, 0))), axis=0)
        starts, ends = np.nonzero(d.T == 1), np.nonzero(d.T == -1)
        out.append(ends[1] - starts[1])   # nonzero() on the transpose is ordered column by column
    r = np.concatenate(out)
    return r[(r > 0) & (r < k)]   # runs >= k are along a wall, not across it


def wall_thickness(mask, gray=None, dark=100):
    """Median wall thickness in px.

    The model's mask only says WHERE walls are: its output is upsampled x4, so its walls never
    get much thinner than ~5 px (a 4 px drawn wall and a 6 px one both come out ~5 px at 1x).
    So when the image has dark wall ink, measure the ink inside the (slightly grown) mask;
    otherwise fall back to the mask itself.
    """
    from skimage.morphology import skeletonize
    m = mask.astype(np.uint8)
    if not m.any():
        return 0.0
    rough = 2 * float(np.median(cv2.distanceTransform(m, cv2.DIST_L2, 5)[skeletonize(m > 0)]))
    k = max(9, round(3 * rough))
    if gray is not None:
        ink = (gray < dark) & (cv2.dilate(m, np.ones((5, 5), np.uint8)) > 0)
        if ink.sum() > 0.3 * m.sum():
            r = _cross_runs(ink, k)
            if r.size:
                return float(np.median(r))
    r = _cross_runs(m, k)
    return float(np.median(r)) if r.size else rough


class P:
    """Pixel thresholds. t = mask wall thickness (mask morphology), ink = drawn thickness."""
    def __init__(self, t, ink):
        self.t, self.ink = t, ink
        # a run filter shorter than the wall is thick lets walls of the other orientation through
        self.min_run = max(round(RUN_K * t), int(np.ceil(t)) + 2)
        self.min_len = MIN_LEN_K * t
        self.min_thick = MIN_THICK_K * t
        # a diagonal kernel must not fit inside an L/T junction of two axis walls
        self.diag = max(round(DIAG_K * t), int(np.ceil(2 * t)) + 3)
        self.half = max(3, round(PROFILE_K * ink))


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


def opening_segment(poly, gray, half):
    x0, y0 = poly.min(0)
    x1, y1 = poly.max(0)
    horiz = (x1 - x0) >= (y1 - y0)
    if horiz:
        c = (y0 + y1) / 2
        a, b = [x0, c], [x1, c]
        lo, hi = int(x0 + (x1 - x0) / 5), int(x1 - (x1 - x0) / 5)
        ci = int(round(c))
        prof = gray[max(ci - half, 0):ci + half + 1, lo:hi].mean(1)
    else:
        c = (x0 + x1) / 2
        a, b = [c, y0], [c, y1]
        lo, hi = int(y0 + (y1 - y0) / 5), int(y1 - (y1 - y0) / 5)
        ci = int(round(c))
        prof = gray[lo:hi, max(ci - half, 0):ci + half + 1].mean(0)
    return a, b, float(prof.min())


def split_diagonals(mask, k):
    """45-degree walls: pixels covered by a k-long diagonal line that fits inside the mask.
    Axis-aligned walls (thickness T < k / 2) and their corners can't hold one."""
    m = mask.astype(np.uint8)
    diag = np.zeros_like(m)
    for ker in (np.eye(k, dtype=np.uint8), np.fliplr(np.eye(k, dtype=np.uint8)).copy()):
        diag |= cv2.morphologyEx(m, cv2.MORPH_OPEN, ker)
    rest = m & (1 - cv2.dilate(diag, np.ones((3, 3), np.uint8)))
    return rest, diag


def hv_walls(mask, p):
    m = mask.astype(np.uint8)
    hm = cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((1, p.min_run), np.uint8))
    vm = cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((p.min_run, 1), np.uint8))
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
            if length >= p.min_len and t >= p.min_thick:
                walls.append(seg)
    return walls


def diagonal_walls(residual, p):
    min_area = p.t * p.t
    walls = []
    n, lab, stats, _ = cv2.connectedComponentsWithStats(residual.astype(np.uint8), connectivity=8)
    for i in range(1, n):
        if stats[i, cv2.CC_STAT_AREA] < min_area:
            continue
        ys, xs = np.nonzero(lab == i)
        (cx, cy), (w, h), ang = cv2.minAreaRect(np.stack([xs, ys], 1).astype(np.float32))
        length, thick = max(w, h), min(w, h)
        if length < 2 * thick or length < p.min_len:
            continue   # a blob, not a wall
        theta = np.deg2rad(ang if w >= h else ang + 90)
        dx, dy = np.cos(theta) * length / 2, np.sin(theta) * length / 2
        walls.append({"a": [cx - dx + 0.5, cy - dy + 0.5], "b": [cx + dx + 0.5, cy + dy + 0.5],
                      "thickness": float(thick), "diagonal": True})
    return walls


def merge_collinear(walls, tol=2.0, gap=2.0):
    """Merge axis-aligned segments that sit on the same line and touch or overlap.

    1. Cluster segments into lines: sorted by their fixed coordinate, a new line starts when
       the next segment is more than `tol` px from the previous one.
    2. Within a line, a proper interval merge (min start, max end).
    The merged segment sits on the fixed coordinate of the line's longest piece.
    (An earlier version merged in rounded-coordinate order and only ever extended the END of
    a run, so a long segment merged into a shorter one lost its left part. Plan 2 hit that.)
    """
    out, rest = [], [w for w in walls if w.get("diagonal")]
    for horiz in (True, False):
        k, j = (1, 0) if horiz else (0, 1)   # k = fixed coord index, j = running coord index
        segs = []
        for w in walls:
            if w.get("diagonal") or w["a"][k] != w["b"][k] or w["a"][j] == w["b"][j]:
                continue
            if (abs(w["b"][0] - w["a"][0]) >= abs(w["b"][1] - w["a"][1])) != horiz:
                continue
            lo, hi = sorted((float(w["a"][j]), float(w["b"][j])))
            segs.append((float(w["a"][k]), lo, hi, w["thickness"]))
        segs.sort()
        lines, cur = [], []
        for sgm in segs:
            if cur and sgm[0] - cur[-1][0] > tol:
                lines.append(cur)
                cur = []
            cur.append(sgm)
        if cur:
            lines.append(cur)
        for line in lines:
            line.sort(key=lambda t: t[1])
            run = None
            for kc, lo, hi, t in line:
                if run and lo <= run["hi"] + gap:
                    run["hi"] = max(run["hi"], hi)
                    run["t"] = max(run["t"], t)
                    run["pieces"].append((hi - lo, kc))
                else:
                    if run:
                        out.append(run)
                    run = {"lo": lo, "hi": hi, "t": t, "pieces": [(hi - lo, kc)]}
            if run:
                out.append(run)
        for r in out:
            if "k" not in r:
                r["k"], r["horiz"] = max(r["pieces"])[1], horiz
    res = []
    for r in out:
        a, b = [0.0, 0.0], [0.0, 0.0]
        k, j = (1, 0) if r["horiz"] else (0, 1)
        a[k] = b[k] = r["k"]
        a[j], b[j] = r["lo"], r["hi"]
        res.append({"a": a, "b": b, "thickness": r["t"]})
    return res + rest


def cut_doors(walls, doors, min_len, slack=2.0):
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
                if s1 - s0 >= min_len / 2:
                    a, b = list(w["a"]), list(w["b"])
                    a[j], b[j] = s0, s1
                    out.append({**w, "a": a, "b": b})
        walls = out
    return walls


def rnd(v, n=1):
    return [round(float(x), n) for x in v]


def render(data, path, scale=2):
    _, _, fw, fh = data["frame"]["viewBox"]
    img = Image.new("RGB", (int(fw * scale), int(fh * scale)), "white")
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
    ap.add_argument("--glazing-dark", type=float, default=GLAZING_DARK,
                    help="opening profile darker than this => window (tuned on the first plan only)")
    ap.add_argument("--no-glazing", action="store_true",
                    help="skip the glazing check; use the model's own door/window class")
    a = ap.parse_args()

    d = np.load(a.pred)
    gray = np.asarray(Image.open(a.image).convert("L")).astype(float)
    assert gray.shape == d["room_argmax"].shape, "prediction and image sizes differ"
    H, W = gray.shape

    wall_mask = d["room_argmax"] == 2
    p = P(wall_thickness(wall_mask), wall_thickness(wall_mask, gray))
    axis_mask, diag_mask = split_diagonals(wall_mask, p.diag)
    walls = merge_collinear(hv_walls(axis_mask, p) + diagonal_walls(diag_mask, p))

    doors, windows = [], []
    for poly, model_cls in official_openings(a.repo, d["pred"]):
        s0, s1, darkest = opening_segment(poly, gray, p.half)
        item = {"a": rnd(s0), "b": rnd(s1), "model_class": model_cls,
                "glazing_min": round(darkest)}
        if a.no_glazing:
            is_window = model_cls != "door"
        else:
            is_window = darkest < a.glazing_dark
        (windows if is_window else doors).append(item)
    walls = cut_doors(walls, doors, p.min_len)

    data = {
        "frame": {"name": "image", "viewBox": [0, 0, W, H]},
        "source": {"model": "CubiCasa5K hg_furukawa_original (model_best_val_loss_var.pkl)",
                   "image": a.image, "inference_scale": float(d["scale"]), "tta": "4 rotations",
                   "wall_thickness_px": round(p.ink, 2), "mask_wall_thickness_px": round(p.t, 2)},
        "door_rule": ("model class" if a.no_glazing else
                      f"model opening; glazing_min >= {a.glazing_dark:g} => door, else window"),
        "walls": [{"a": rnd(w["a"]), "b": rnd(w["b"]), "thickness": round(w["thickness"], 1)} for w in walls],
        "doors": doors,
        "windows": windows,
    }
    json.dump(data, open(a.out, "w"), indent=1)
    render(data, a.render)
    print(f"wall thickness ink {p.ink:.2f}px / mask {p.t:.2f}px; {len(data['walls'])} walls, {len(doors)} doors, "
          f"{len(windows)} windows -> {a.out}, {a.render}")


if __name__ == "__main__":
    main()
