"""Whole pipeline for one floorplan image: infer -> vectorize -> (compare) -> app frame -> (embed).

  python run.py --image plan.png --out runs/plan
  python run.py --image plan.png --out runs/plan --ref-index ../../index.html \
      --ref-doors ../../index.html --plan-config configs/apartment-1.json --embed ../../index.html

--scale auto (default):
  1. Run once at 1x and measure the drawn wall thickness inside the model's wall mask.
  2. Candidates: the scale that makes walls ~TARGET_WALL_PX thick, plus 2x. On the first plan
     (6 px walls) 1x closed door gaps and 2x didn't. On a 0.8x copy, 3x (the 12 px target) lost
     whole walls while 2x was fine, so more upscaling is NOT monotonically better.
  3. Score each candidate's walls against the image's own dark ink (no references needed).
     Keep 2x unless another candidate beats it by more than SWITCH_MARGIN F1. On two shrunk
     copies of the first plan, 3x missed the same door both times while the wall scores were
     within ~0.01 of 2x, and which one "won" flipped with the padding. So the wall score can't
     see opening quality and is only trusted for large differences. The decision is saved to
     scale_selection.json. This rule rests on ONE plan; recheck it on new ones.

Paths default to setup.sh's layout under $CUBICASA_HOME (~/.cache/cubicasa-spike).
"""
import argparse
import json
import os
import subprocess
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
HOME = os.environ.get("CUBICASA_HOME", os.path.expanduser("~/.cache/cubicasa-spike"))
TARGET_WALL_PX = 12.0
MAX_SCALE = 3.0
DEFAULT_SCALE = 2.0
SWITCH_MARGIN = 0.02


def step(*args):
    cmd = [sys.executable, "-W", "ignore", *map(str, args)]
    print("$", os.path.basename(cmd[3]), " ".join(cmd[4:]))
    subprocess.run(cmd, check=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--image", required=True)
    ap.add_argument("--out", required=True, help="output directory for this run")
    ap.add_argument("--scale", default="auto", help="'auto' or a number")
    ap.add_argument("--repo", default=os.path.join(HOME, "cubicasa_src"))
    ap.add_argument("--weights", default=os.path.join(HOME, "model_best_val_loss_var.pkl"))
    ap.add_argument("--ref-index", help="index.html whose #planImg defines the app frame (for align.py)")
    ap.add_argument("--transform", help="precomputed align.py output (skips alignment)")
    ap.add_argument("--px-per-ft", type=float, default=16, help="app-frame px per ft")
    ap.add_argument("--ref-doors", help="reference doors (index.html or JSON) for scoring")
    ap.add_argument("--plan-config", help="labeled rooms for the scale check (see configs/)")
    ap.add_argument("--no-glazing", action="store_true", help="use the model's raw door/window class")
    ap.add_argument("--glazing-dark", type=float, default=170)
    ap.add_argument("--embed", help="index.html to embed the app-frame JSON into")
    a = ap.parse_args()

    os.makedirs(a.out, exist_ok=True)
    o = lambda name: os.path.join(a.out, name)
    s = lambda name: os.path.join(HERE, name)

    glz = ["--glazing-dark", a.glazing_dark, *(["--no-glazing"] if a.no_glazing else [])]

    def infer(scale):
        pred = o(f"pred_s{scale:g}.npz")
        if not os.path.exists(pred):
            step(s("infer.py"), "--repo", a.repo, "--weights", a.weights, "--image", a.image,
                 "--scale", scale, "--out", pred)
        return pred

    # 1. inference (auto: pick the scale by a reference-free wall score)
    if a.scale == "auto":
        infer(1.0)
        sys.path.insert(0, HERE)
        from PIL import Image
        from vectorize import wall_thickness
        gray = np.asarray(Image.open(a.image).convert("L")).astype(float)
        t1 = wall_thickness(np.load(o("pred_s1.npz"))["room_argmax"] == 2, gray)
        target = min(MAX_SCALE, round(max(1.0, TARGET_WALL_PX / max(t1, 1e-6)) * 2) / 2)
        cands = sorted({target, DEFAULT_SCALE})
        print(f"wall thickness at 1x: {t1:.2f}px -> candidate scales {cands}")
        scores = {}
        for sc in cands:
            tag = f"s{sc:g}"
            step(s("vectorize.py"), "--repo", a.repo, "--pred", infer(sc), "--image", a.image,
                 "--out", o(f"cand_{tag}.json"), "--render", o(f"cand_{tag}.png"), *glz)
            step(s("compare.py"), "--json", o(f"cand_{tag}.json"), "--image", a.image,
                 "--out-json", o(f"cand_{tag}_metrics.json"), "--out-png", o(f"cand_{tag}_diff.png"))
            m = json.load(open(o(f"cand_{tag}_metrics.json")))["walls"]["excluding_window_spans"]["within_1px"]
            p_, r_ = m["precision"], m["recall"]
            scores[sc] = round(2 * p_ * r_ / max(p_ + r_, 1e-9), 4)
        best = max(scores, key=scores.get)
        scale = best if scores[best] > scores[DEFAULT_SCALE] + SWITCH_MARGIN else DEFAULT_SCALE
        json.dump({"wall_thickness_1x_px": t1, "candidates": {f"{k:g}": v for k, v in scores.items()},
                   "metric": "wall F1 within 1px vs image ink, excluding window spans",
                   "rule": f"keep {DEFAULT_SCALE:g}x unless another beats it by > {SWITCH_MARGIN}",
                   "chosen": scale}, open(o("scale_selection.json"), "w"), indent=1)
        print(f"scale scores {scores} -> {scale}")
    else:
        scale = float(a.scale)
    pred = infer(scale)

    # 2. vectorize (image frame)
    step(s("vectorize.py"), "--repo", a.repo, "--pred", pred, "--image", a.image,
         "--out", o("walls_doors.image.json"), "--render", o("walls_doors.png"), *glz)

    # 3. transform to the app frame
    transform = a.transform
    if not transform and a.ref_index:
        transform = o("transform.json")
        step(s("align.py"), "--image", a.image, "--ref-index", a.ref_index, "--out", transform)

    # 4. compare (image frame) if there's anything to compare against
    cmp = ["--json", o("walls_doors.image.json"), "--image", a.image,
           "--out-json", o("metrics.json"), "--out-png", o("wall_diff.png")]
    if a.ref_doors:
        cmp += ["--ref-doors", a.ref_doors]
    if a.plan_config:
        cmp += ["--plan-config", a.plan_config]
    if transform:
        cmp += ["--transform", transform]
    step(s("compare.py"), *cmp)

    # 5. app frame JSON, then optionally embed it
    app = ["--json", o("walls_doors.image.json"), "--px-per-ft", a.px_per_ft, "--out", o("walls_doors.json")]
    step(s("to_app.py"), *app, *(["--transform", transform] if transform else []))
    if a.embed:
        step(s("embed.py"), "--json", o("walls_doors.json"), "--index", a.embed)

    print(json.dumps({"out": a.out, "scale": scale, "transform": transform}, indent=1))


if __name__ == "__main__":
    main()
