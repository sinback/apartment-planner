"""Estimate the transform from a source image to the app's plan frame.

The app frame is the image embedded in index.html (#planImg, 1194x703 for the first plan),
or any reference PNG. Uses ORB features + RANSAC similarity (scale, rotation, shift),
then reports how well the two images agree after warping.

Usage:
  python align.py --image plan.png --ref-index ../../index.html --out transform.json
  python align.py --image plan.png --ref ref.png --out transform.json
"""
import argparse
import base64
import io
import json
import re

import cv2
import numpy as np
from PIL import Image


def app_image(index_html):
    html = open(index_html).read()
    m = re.search(r'<image id="planImg"[^>]*href="data:image/png;base64,([^"]+)"', html)
    return Image.open(io.BytesIO(base64.b64decode(m.group(1)))).convert("L")


def estimate(src, ref):
    """Similarity transform mapping src pixel coords -> ref pixel coords."""
    if src.shape == ref.shape and np.abs(src.astype(float) - ref.astype(float)).mean() < 2:
        return np.array([[1, 0, 0], [0, 1, 0]], float), {"method": "identical size and pixels"}
    orb = cv2.ORB_create(5000)
    k1, d1 = orb.detectAndCompute(src, None)
    k2, d2 = orb.detectAndCompute(ref, None)
    matches = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True).match(d1, d2)
    p1 = np.float32([k1[m.queryIdx].pt for m in matches])
    p2 = np.float32([k2[m.trainIdx].pt for m in matches])
    M, inl = cv2.estimateAffinePartial2D(p1, p2, method=cv2.RANSAC, ransacReprojThreshold=2.0)
    return M, {"method": "ORB + RANSAC similarity", "matches": len(matches), "inliers": int(inl.sum())}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--image", required=True)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--ref-index", help="index.html whose #planImg defines the app frame")
    g.add_argument("--ref", help="reference image in the app frame")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    src = np.asarray(Image.open(a.image).convert("L"))
    ref = np.asarray(app_image(a.ref_index) if a.ref_index else Image.open(a.ref).convert("L"))
    M, info = estimate(src, ref)
    scale = float(np.hypot(M[0, 0], M[1, 0]))
    rot = float(np.degrees(np.arctan2(M[1, 0], M[0, 0])))

    warped = cv2.warpAffine(src, M, (ref.shape[1], ref.shape[0]), borderValue=255)
    d_src, d_ref = warped < 100, ref < 100
    iou = float((d_src & d_ref).sum() / max((d_src | d_ref).sum(), 1))

    out = {"matrix": M.tolist(), "scale": round(scale, 5), "rotation_deg": round(rot, 3),
           "offset": [round(float(M[0, 2]), 2), round(float(M[1, 2]), 2)],
           "app_size": [int(ref.shape[1]), int(ref.shape[0])],
           "dark_pixel_iou_after_warp": round(iou, 3), **info}
    json.dump(out, open(a.out, "w"), indent=1)
    print(json.dumps(out))
    if iou < 0.8:
        print("WARNING: low agreement after warp; check the transform by eye before using it")


if __name__ == "__main__":
    main()
