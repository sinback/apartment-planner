"""Run the official CubiCasa5K model on one floorplan image.

Saves the raw averaged prediction (44 channels: 21 junction heatmaps,
12 room classes, 11 icon classes) plus argmax masks to an .npz file.

Usage:
  python infer.py --repo CUBICASA_SRC --weights model_best_val_loss_var.pkl \
      --image original.png --scale 2 --out pred.npz
"""
import argparse
import sys
import time

import numpy as np
import torch
import torch.nn.functional as F
from PIL import Image

N_CLASSES = 44
SPLIT = [21, 12, 11]
ROOM_CLASSES = ["Background", "Outdoor", "Wall", "Kitchen", "Living Room", "Bed Room",
                "Bath", "Entry", "Railing", "Storage", "Garage", "Undefined"]
ICON_CLASSES = ["No Icon", "Window", "Door", "Closet", "Electrical Appliance", "Toilet",
                "Sink", "Sauna Bench", "Fire Place", "Bathtub", "Chimney"]


def load_model(repo, weights):
    sys.path.insert(0, repo)
    from floortrans.models.hg_furukawa_original import hg_furukawa_original

    # Build the net directly instead of get_model(): get_model() calls init_weights(),
    # which unpickles an extra pose-estimation checkpoint we don't need (it's overwritten).
    model = hg_furukawa_original(n_classes=51)
    model.conv4_ = torch.nn.Conv2d(256, N_CLASSES, bias=True, kernel_size=1)
    model.upsample = torch.nn.ConvTranspose2d(N_CLASSES, N_CLASSES, kernel_size=4, stride=4)
    ckpt = torch.load(weights, map_location="cpu", weights_only=True)
    model.load_state_dict(ckpt["model_state"])
    model.eval()
    return model


def predict(model, repo, img_rgb, scale):
    """4-rotation test-time augmentation, as in the official samples notebook."""
    sys.path.insert(0, repo)
    # Importing floortrans.loaders pulls in dataset-only deps (lmdb, svgpathtools); install them.
    from floortrans.loaders import RotateNTurns

    rot = RotateNTurns()
    h0, w0 = img_rgb.shape[:2]
    pil = Image.fromarray(img_rgb)
    if scale != 1:
        pil = pil.resize((round(w0 * scale), round(h0 * scale)), Image.BICUBIC)
    arr = np.asarray(pil).astype(np.float32)
    x = torch.from_numpy(2 * (arr / 255.0) - 1).permute(2, 0, 1)[None]
    h, w = x.shape[2:]

    rotations = [(0, 0), (1, -1), (2, 2), (-1, 1)]
    out = torch.zeros([len(rotations), N_CLASSES, h, w])
    with torch.no_grad():
        for i, (fwd, back) in enumerate(rotations):
            p = model(rot(x, "tensor", fwd))
            p = rot(p, "tensor", back)
            p = rot(p, "points", back)
            out[i] = F.interpolate(p, size=(h, w), mode="bilinear", align_corners=True)[0]
    pred = out.mean(0, keepdim=True)
    # Back to the source image's pixel grid (= the app frame, see README).
    pred = F.interpolate(pred, size=(h0, w0), mode="bilinear", align_corners=False)
    return pred


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True, help="path to a CubiCasa5k clone")
    ap.add_argument("--weights", required=True)
    ap.add_argument("--image", required=True)
    ap.add_argument("--scale", type=float, default=1.0, help="upscale before inference")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    torch.set_num_threads(max(1, torch.get_num_threads()))
    t0 = time.time()
    model = load_model(a.repo, a.weights)
    t1 = time.time()
    img = np.asarray(Image.open(a.image).convert("RGB"))
    pred = predict(model, a.repo, img, a.scale)
    t2 = time.time()

    rooms = F.softmax(pred[0, 21:33], 0).numpy()
    icons = F.softmax(pred[0, 33:], 0).numpy()
    np.savez_compressed(
        a.out,
        pred=pred[0].numpy().astype(np.float16),
        room_argmax=rooms.argmax(0).astype(np.uint8),
        icon_argmax=icons.argmax(0).astype(np.uint8),
        wall_prob=rooms[2].astype(np.float16),
        door_prob=icons[2].astype(np.float16),
        window_prob=icons[1].astype(np.float16),
        scale=a.scale,
    )
    print(f"load {t1 - t0:.1f}s, inference (4 rotations, scale {a.scale}) {t2 - t1:.1f}s -> {a.out}")


if __name__ == "__main__":
    main()
