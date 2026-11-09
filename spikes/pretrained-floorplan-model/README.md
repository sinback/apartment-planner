# Spike: walls and doors from a pretrained CubiCasa5K model

**Question** ([brief](../../docs/spikes/pretrained-floorplan-model-brief.md)): how well does an
off-the-shelf model trained on CubiCasa5K pull walls and doors out of our floorplan image,
compared with what the app has today?

**Short answer.** Walls come out excellent, and the door *openings* are all found. But the model
labels every opening a window, because this plan draws doors as plain gaps and CubiCasa5K draws them
as swing arcs. A ~10-line pixel check (glazing lines or not) fixes that on this plan. It is not the
model, and it is tuned to this plan's drawing style.

## Model used, and why

**Official CubiCasa5K model**: `hg_furukawa_original` with `model_best_val_loss_var.pkl`, from
[CubiCasa/CubiCasa5k](https://github.com/CubiCasa/CubiCasa5k). Kalervo et al., *CubiCasa5K: A
Dataset and an Improved Multi-Task Model for Floorplan Image Analysis*, SCIA 2019. Based on
Raster-to-Vector (Liu et al. 2017). The dataset and model are **CC BY-NC 4.0**.

I checked the other candidates first:

| Candidate | Classes | Verdict |
|---|---|---|
| `phungpx/RMBG-1.4-wall-segmentation-cubicassa` | wall only | no doors |
| `phungpx/mask2former-swin-base-cubicassa` | **wall only** (the brief hoped it had doors) | no doors |
| `Hyunwoo1605/mask2former-floorplan-instance-segmentation` | wall, door, window | trained on `FP_STR`, **not** CubiCasa5K; empty card, no license |
| `JessiP23/cubicasa5k` | wall, room, door, window (Detectron2 Mask R-CNN) | no card; needs detectron2 |
| `JessiP23/cubicasa-segformer-v2` | 18 classes | door IoU 0.145 |
| `haopt/Raster2Seq` | room polygons | lowest priority, not tried |

The official model is the only well-documented CubiCasa5K model with walls and doors in one
network. It outputs 44 channels: 21 junction/opening-corner heatmaps, 12 room classes (including
**Wall**), and 11 icon classes (including **Door** and **Window**).

## Setup issues and timings

- **Network.** `download.pytorch.org` redirects wheels to `download-r2.pytorch.org` (that host was
  blocked at first). The CubiCasa GitHub repo was outside the session's scope. Both were fixed by
  switching the environment to full network access. The weights come from Google Drive
  (`drive.usercontent.google.com`, 209 MB, plain download with `confirm=t`).
- **Pickle safety.** The checkpoint loads with `torch.load(..., weights_only=True)`, so there was
  no full unpickle and no safetensors conversion was needed. The script builds the network directly
  instead of calling `get_model()`, whose `init_weights()` would unpickle a second (pose-estimation)
  checkpoint that the real weights overwrite anyway. I read the model and post-processing code
  before running them.
- **Bit-rot in the 2019 code** (patched at runtime, the repo itself is unchanged):
  - `post_prosessing.py` uses the old `scipy.stats.mode(...).mode[0]` API. `vectorize.py` shims it.
  - Importing `floortrans.loaders` needs `lmdb` and `svgpathtools`, even for inference.
- **Timings** on a 4-core CPU, PyTorch 2.15 CPU build:
  - Model load: 0.6 s.
  - Inference with the official 4-rotation test-time augmentation: **7 s** at native 1194×703,
    **41 s** upscaled 2×. I used 2×.
- **Resolution matters.** At 1× (walls about 6 px thick), the wall mask paints over several door
  gaps, and one opening is snapped onto the wrong wall (see Openings below). At 2× (about 12 px)
  both problems go away. For the upload feature, uploads will come in at different resolutions, so
  each image should be resized to a target wall thickness (or a target px/ft) before inference,
  rather than run at whatever size it arrives.
  - Official polygon post-processing: about 1 s.
  - Vectorize + compare: under 1 s.

## Image transform

**Identity** (scale 1, offset 0,0). The original image is 1194×703, the same as the PNG embedded in
`index.html`.
- Best integer shift: (0,0), with mean absolute grey difference 0.25/255. Every ±1 px shift is
  about 2.6.
- Dark-pixel IoU between the two images: 0.99. The remaining differences are PNG re-encoding noise.

**Scale check** at 16 px/ft. Interior sizes were measured between the model's wall faces:

| Room (image label) | Measured / expected (w × h) |
|---|---|
| Bedroom 22'9" × 11'2" | 0.997 × 1.002 |
| Bedroom 11'9" × 10'2" | 0.995 × 0.996 |
| Kitchen 12'3" × 13'5" | 0.995 × 0.997 |
| Living Room 13'1" × 15'4" | 0.998 × 0.999 |
| Bathroom 8'4" × 6'4" | 0.990 × 0.987 |
| Office 9'4" × 6'5" | 0.991 × 0.984 |

The scale is right everywhere. The small shortfall (1–2 px) comes from the model's walls running
about 1 px thicker than the drawn ones.

## Results

### Walls

The ground truth is the image's dark pixels, with small components (label text) removed.
From `output/metrics.json`:

| | Pixel IoU | Precision | Recall | Precision / recall within 1 px |
|---|---|---|---|---|
| All wall pixels | 0.714 | 0.716 | 0.996 | 0.860 / 0.998 |
| Excluding window spans | **0.799** | 0.802 | 0.996 | **0.958 / 0.998** |

- Every wall in the image is found.
- **Windows count as wall.** CubiCasa's Wall class runs straight through openings. The vectorizer
  cuts door spans back out and keeps window spans as wall, drawn in window style on top, since a
  window is still a wall for furniture purposes. The image draws windows light, so they score as
  "model only" in the "All" row.
- The other precision loss is the ~1 px extra thickness: IoU 0.80 exact vs 0.96 within 1 px.
- The **bay window**'s two 45° walls are vectorized as diagonal segments. The small horizontal
  stubs where the bay meets the main wall (about 8 px) are dropped.

`output/wall_diff.png`: black = agree, red = model only, blue = image only.

### Openings: all 26 at scale 2, broken down

The JSON is the model's actual output; nothing was hand-corrected.

| Bucket | Count | Notes |
|---|---|---|
| Matched a hand-placed door | 10 | all 10 of `#doors` |
| Real windows | 14 | of 16 windows in the image |
| Door-like opening not in `#doors` | 2 | both look like real, unglazed openings (see below); not counted as false positives until the user confirms |
| False positives | 0 | at scale 2 |

Misses, against the image:
- **The 2 diagonal bay windows.** The opening detector only proposes axis-aligned openings.
- **The closet's opening onto the master bedroom** (x 822, y 338–378) isn't reported as an opening.
  The wall mask does leave the gap open.
- **The laundry room's bottom gap** (x 490–530, y 322) isn't reported either, but it's also open in
  the wall mask.

**At scale 1** the same post-processing put one opening on the solid wall at x 780 instead of the
closet gap at x 822. That's 1 miss plus 1 false positive, and the 1× wall mask also closed several
door gaps.

### Doors

The reference is the 10 hand-placed doors in `#doors`.

| | Count |
|---|---|
| Hand-placed doors found as model **openings** | **10 / 10** |
| Of those, **classified "door" by the model** | **0 / 10** (all labeled "window") |
| Classified door by the glazing check (see below) | 10 / 10 |
| Door-like openings the model found that aren't in `#doors` | 2 |
| Openings misclassified as windows after the glazing check | 0 |

- **Position.** Endpoint error is 3.2 px for 9 doors and 4.1 px for one. Almost all of that is a
  convention difference: the hand-drawn swings sit on the wall *face*, while the model's openings
  sit on the wall *centerline*. Along the wall, the jambs agree within about 1 px.
  - **How to read this match.** The hand-placed doors were read off these same pixels by the LLM.
    A close match shows the two readings of the image agree. It doesn't show that either one is
    ground truth for the real apartment.
- **Why the model says "window".** CubiCasa5K annotates doors with swing arcs. This plan (a
  Matterport-style export) draws doors as a plain white gap between two thin grey lines, which
  looks more like CubiCasa's window glyph. The official post-processing decides each opening's
  type from the Door/Window icon segmentation. Door evidence was close to zero everywhere (35 Door
  pixels in the whole 2× mask), so every opening became "window".
- **The glazing check** (`vectorize.py`, not ML) is my addition, not the model's. It averages the
  image's intensity profile across the wall at each opening. Windows here always have dark glazing
  lines inside the band (minimum ≤ 160); doors never go below 197. The threshold is 170.
  - **Its 10/10 is optimistic.** I designed the rule and picked the threshold by looking at this
    same image, so this is a training-set score, not a held-out one.
  - **What the app shows vs. what the JSON keeps.** The app renders the classes *after* the check.
    The model's raw class is kept as `model_class` on every opening in the JSON; it's "window" for
    all 26.
- **The 2 extra door-like openings.** Both look like real, unglazed openings in the image. Please
  check them on site:
  - The office ("Bike/Shoe Room") left wall, x 880, y 441–478.
  - The top of the stair corridor, x 308–351, y 373.

### Windows, and other openings

- 16 windows in the image; 14 detected, all correct.
- **Missed:** the 2 diagonal bay windows. The opening detector only proposes axis-aligned openings.
- **Plain wall gaps with no glyph:** the wall mask leaves these open, but they aren't reported as
  openings. One is the laundry room's bottom wall (x 490–530, y 322), the other the closet's
  right-hand wall (x 822, y 338–378).
- **Misplaced opening (scale 1 only).** At native resolution the post-processing snapped one opening
  onto the solid wall at x 780 instead of the closet gap at x 822. That's another reason for 2×.

### Room segmentation (out of scope, one note)

The 12 room classes aren't useful on this plan. At scale 2, most of the floor area comes out as
"Undefined" or "Background", and only part of one room is "Living Room". The model doesn't
recognize this export's room styling, so that output isn't worth building on.

## What changed in the app (`index.html`)

- **New "Plan" select** in the zoom bar, with three modes. The choice is remembered per browser in
  `localStorage`, wrapped in try/catch.
  - **Original image**: the app as before.
  - **Model walls/doors**: hides the raster image *and* the hand-drawn door swings (`#doors`),
    so only the model's walls (filled), door openings (orange, with jamb dots) and windows (blue)
    remain.
  - **Overlay**: the image faded to 35%, model walls semi-transparent red on top, and the
    hand-drawn swings kept. Each model door opening then sits next to its hand-placed swing.
- **Unchanged in every mode:** room relabels, `#stepUp`, `#outlines` and furniture. They're user
  annotations, not plan geometry, and the model couldn't produce them.
- **Data and drawing.**
  - The model data is inline in `<script type="application/json" id="modelPlanData">` (3.7 KB),
    written by `embed.py`, and drawn into `<g id="modelPlan">`.
  - No new runtime dependencies, and nothing runs a model in the browser.
- **Dark mode.** The model layer is *not* under `--plan-filter`. Its colors are theme tokens
  (`--model-wall`, `--model-overlay`, `--model-door`, `--model-window`) with dark-mode values.
- **Screenshots** are in `output/screenshots/`, all at the same zoom, deviceScaleFactor 2:
  original, model and overlay in light mode, plus model and overlay in dark mode.

## Is it worth pursuing for the upload feature?

**Yes for walls, with caveats for doors.**

- **Walls** are close to production-ready on this style of plan: full recall, 1 px precision
  around 0.96 excluding windows, and correct scale with an identity transform.
- **Door openings** are found reliably, but the **door vs. window call** is where this model is
  weakest on non-CubiCasa drawing styles. The glazing check works here because this export's
  window glyph is distinctive. A plan with swing arcs would probably go the other way (the model's
  own Door class fires). A plan with yet another style would need its own rule. For an upload
  feature I'd expect to let the user confirm or flip each opening's type in the UI; that's one
  click per opening.
- **Swing direction** is not available from this image, and the model wouldn't help where arcs
  are missing. The user would still set hinge side and swing.
- **Scale** for an uploaded plan needs one known dimension (the user, or OCR of a room label). The
  model gives nothing in feet.

### What running it in the browser would take

- **Network size:**
  - 17.4M parameters.
  - The fp32 ONNX export (opset 17, dynamic H/W) is **69.5 MB**. It exported cleanly with
    `torch.onnx.export`; I haven't run it in onnxruntime.
  - The 209 MB checkpoint also contains optimizer state.
  - Quantization should get the download to roughly **35 MB fp16 or 18 MB int8** (estimated, not
    measured).
- **Runtime:** onnxruntime-web with WebGPU, falling back to WASM. On WASM, a 2× pass with 4-rotation
  test-time augmentation would probably take tens of seconds (it's 41 s on 4 native CPU cores
  here). On WebGPU it should be a few seconds.
- **Preprocessing:** trivial (resize, scale to [-1, 1]). The 4-rotation test-time augmentation
  quadruples the cost; it could be dropped or cut to 2 rotations at some accuracy cost.
- **Post-processing is the real porting work.** The official `get_polygons` is about 1,500 lines
  of NumPy/SciPy/Shapely (junction heatmap peaks, line/opening assembly). The vectorizer here is
  OpenCV morphology and connected components. Both would need a JS port. OpenCV.js covers the
  morphology but is itself a multi-MB download.
- **App changes:** an "upload plan" flow, a wall/opening layer like the one added here, and the
  inches-based coordinate change from the separate plan.
- **Alternative:** run inference server-side, or once offline per plan (as in this spike), and
  ship JSON to the static page. That keeps the app a single `index.html` with no ML in the browser.

## Reproducing

```bash
python3 -m venv venv && . venv/bin/activate
pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
pip install opencv-python-headless numpy scipy pillow scikit-image shapely lmdb svgpathtools
git clone --depth 1 https://github.com/CubiCasa/CubiCasa5k cubicasa_src
curl -L -o model_best_val_loss_var.pkl \
  "https://drive.usercontent.google.com/download?id=1gRB7ez1e4H7a9Y09lLqRuna0luZO5VRK&export=download&confirm=t"
```

Then, with `original.png` as the source floorplan (1194×703):

```bash
python infer.py --repo cubicasa_src --weights model_best_val_loss_var.pkl --image original.png --scale 2 --out pred_s2.npz
python vectorize.py --repo cubicasa_src --pred pred_s2.npz --image original.png --out output/walls_doors.json --render output/walls_doors.png
python compare.py --json output/walls_doors.json --image original.png --index ../../index.html --out-json output/metrics.json --out-png output/wall_diff.png
python embed.py --json output/walls_doors.json --index ../../index.html
node screenshots.js ../../index.html output/screenshots
```

Keep the weights, the clone and `pred_*.npz` out of git (see `.gitignore`).

## Files

| File | Contents |
|---|---|
| `infer.py` | model load (`weights_only=True`) and 4-rotation TTA inference |
| `vectorize.py` | walls/openings → JSON in the app frame, plus the 2D render |
| `compare.py` | wall pixel overlap, door matching against `#doors`, scale check |
| `embed.py` | writes the JSON into `index.html` |
| `screenshots.js` | Playwright screenshots of each plan mode |
| `output/walls_doors.json` | 48 walls, 12 doors, 14 windows (1194×703 frame, 16 px/ft) |
| `output/walls_doors.png` | 2D render of the vectorized walls, doors and windows only (2×) |
| `output/wall_diff.png` | wall agreement map |
| `output/metrics.json` | all numbers above |
