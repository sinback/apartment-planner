"""Regression test for the pipeline. Run after changing any script.

Takes the plan embedded in index.html, runs the pipeline on it and on a copy that is shrunk to
0.8x and shifted, then checks that:
  - the copy's alignment recovers the true transform,
  - both runs find every reference door as an opening,
  - the copy's walls, mapped to the app frame, match the original's walls.
The shrunk copy is what caught the mask-vs-ink thickness bugs and the 3x scale regression.

  python selftest.py --index ../../index.html [--work /tmp/selftest]   (~4 min on 4 CPU cores)
"""
import argparse
import json
import os
import subprocess
import sys
import tempfile

import cv2
import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import compare  # noqa: E402
from align import app_image  # noqa: E402

SHRINK, PAD = 0.8, (50, 25)


def run(image, out, index):
    subprocess.run([sys.executable, os.path.join(HERE, "run.py"), "--image", image, "--out", out,
                    "--ref-index", index, "--ref-doors", index], check=True,
                   stdout=subprocess.DEVNULL)
    return (json.load(open(os.path.join(out, "walls_doors.json"))),
            json.load(open(os.path.join(out, "metrics.json"))),
            json.load(open(os.path.join(out, "transform.json"))))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--index", required=True)
    ap.add_argument("--work", default=tempfile.mkdtemp(prefix="selftest-"))
    a = ap.parse_args()
    os.makedirs(a.work, exist_ok=True)

    orig = os.path.join(a.work, "plan.png")
    app_image(a.index).convert("RGB").save(orig)
    im = Image.open(orig)
    small = im.resize((round(im.width * SHRINK), round(im.height * SHRINK)), Image.LANCZOS)
    shifted = Image.new("RGB", (small.width + 2 * PAD[0], small.height + 2 * PAD[1]), "white")
    shifted.paste(small, PAD)
    shifted_path = os.path.join(a.work, "shifted.png")
    shifted.save(shifted_path)

    d0, m0, _ = run(orig, os.path.join(a.work, "orig"), a.index)
    d1, m1, t1 = run(shifted_path, os.path.join(a.work, "shifted"), a.index)

    compare.W, compare.H = im.width, im.height
    A, B = compare.raster_walls(d1["walls"]), compare.raster_walls(d0["walls"])
    prec, rec = compare.overlap(A, B, 2)
    checks = {
        "align scale": (abs(t1["scale"] - 1 / SHRINK) < 0.01, t1["scale"]),
        "align offset": (np.allclose(t1["offset"], [-PAD[0] / SHRINK, -PAD[1] / SHRINK], atol=1.5), t1["offset"]),
        "orig: all reference doors found": (m0["doors"]["found_as_opening"] == m0["doors"]["reference_doors"],
                                            f'{m0["doors"]["found_as_opening"]}/{m0["doors"]["reference_doors"]}'),
        "shifted: all reference doors found": (m1["doors"]["found_as_opening"] == m1["doors"]["reference_doors"],
                                               f'{m1["doors"]["found_as_opening"]}/{m1["doors"]["reference_doors"]}'),
        "walls agree within 2px (precision)": (prec >= 0.95, round(prec, 3)),
        "walls agree within 2px (recall)": (rec >= 0.95, round(rec, 3)),
    }
    ok = all(v[0] for v in checks.values())
    for k, (passed, val) in checks.items():
        print(f"{'PASS' if passed else 'FAIL'}  {k}: {val}")
    out = np.full((im.height, im.width, 3), 255, np.uint8)
    out[A & B], out[A & ~B], out[B & ~A] = (30, 30, 30), (220, 40, 40), (40, 90, 230)
    cv2.imwrite(os.path.join(a.work, "shifted_vs_orig.png"), out[:, :, ::-1])
    print(("all checks passed" if ok else "FAILED") + f"; outputs in {a.work}")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
