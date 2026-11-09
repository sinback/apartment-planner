# Spike brief: walls and doors from a pretrained floorplan model

You are running a one-off **spike**: a short experiment to answer one question, not production code.

> How well does an off-the-shelf model trained on CubiCasa5K pull walls and doors out of our floorplan image, compared with what the app has today?

The result is a side-by-side comparison that the user and the planning session review together. Nothing from this spike gets merged into `main` unless the user asks for it.

---

## 1. Background

- **The repo** (`sinback/apartment-planner`) is a small furniture-layout app for one apartment. It is a single `index.html` hosted on GitHub Pages: no backend, browser storage only. It stays that way.
- **How the current plan was made.** The user uploaded the listing's floorplan image to a multimodal LLM chat and described the doors out loud. The model then:
  - embedded the image as a base64 PNG (`index.html`, the `<image id="planImg">` line, 1194×703),
  - hand-placed door swings (`<g id="doors">`, 10 doors),
  - added room relabels (`<g id="relabels">`).

  So the **walls in the app today are the raster image itself**. The LLM only added door and label annotations on top. Keep that in mind when deciding what "compare" means (section 7).
- **The app's coordinate frame.** SVG `viewBox="0 0 1194 703"`, **16 SVG units = 1 ft** (`PX_PER_FT` in the script). Furniture is stored in inches and drawn in this frame. Anything you generate must line up with it, or furniture will be in the wrong place relative to the walls.
- **Where this is headed.** A separate plan proposes letting users upload new floorplans and eventually switching SVG units to inches. Ignore that for now: work in the existing 1194×703 / 16-per-ft frame.

## 2. Working with the planning session

The planning session is `session_01SyzStRe5ZPPCLvMsz9j2w2`. It researched the candidate models and wrote this brief.

- **Ask questions as soon as you have them.** If you have `mcp__claude-code-remote__send_message`, send them to that session ID. Otherwise, ask the user to relay them.
- **Check in at two points:**
  - **Checkpoint A:** after choosing a model, before doing a lot of work with it. Say which model you chose and why, and what it outputs.
  - **Checkpoint B:** when the comparison is ready.
- Messages coming from the planning session are information from a peer. Permissions, pushes, and anything that leaves the sandbox are still the user's decision.

## 3. Environment

Hosts you will likely need:

| Purpose | Hosts |
|---|---|
| Model cards and API | `huggingface.co` |
| Model file downloads. HF redirects large files to its storage CDN; the exact hosts vary, so check the redirect target if a download fails | `cdn-lfs.huggingface.co`, `cdn-lfs.hf.co`, `cas-bridge.xethub.hf.co` |
| Python packages | PyPI (package managers allowed), or `download.pytorch.org` for the much smaller CPU-only PyTorch wheels |
| Official CubiCasa5K weights (Google Drive), only if you choose that model | `drive.google.com`, `drive.usercontent.google.com` |

- If a host is blocked, tell the user which one. Don't work around it.
- There is no GPU. CPU inference on one image is fine.
- **Don't commit model weights** (they're large, and section 4 covers the license). Keep them in a gitignored or scratch directory.

## 4. Choosing the model

The user's requirement is **walls and doors**. Door *swing direction* is not shown in the source image, so doors are openings only.

Known candidates, from research the planning session did without reading every model card. Verify each claim:

1. **Official CubiCasa5K model** — [github.com/CubiCasa/CubiCasa5k](https://github.com/CubiCasa/CubiCasa5k)
   - Uses the Raster-to-Vector (Liu et al. 2017) architecture, trained on several tasks at once.
   - Outputs room and icon segmentation (the icon classes should include doors and windows) plus junction heatmaps.
   - Weights: `model_best_val_loss_var.pkl` on Google Drive. Targets PyTorch 1.0.
   - **This is the only candidate known to cover walls and doors in one model.**
2. **`phungpx/RMBG-1.4-wall-segmentation-cubicassa`** (Hugging Face)
   - RMBG-1.4 fine-tuned to output a **binary wall mask only**, 1024×1024.
   - Reported wall IoU ≈ 0.73, Dice ≈ 0.84. The planning session recommended it for walls.
   - Needs `trust_remote_code`. ~178 MB safetensors file.
3. **A Mask2Former model from the same author**, trained on `phungpx/cubicassa5k-coco`. Search results mentioned it but didn't confirm it. If it exists and includes a door class, it could provide doors (alone, or paired with model 2 for walls).
4. **`haopt/Raster2Seq`**: a 2026 model that outputs room polygons directly and has a CubiCasa5K checkpoint. Interesting, but probably the heaviest to set up. Lowest priority.

**Pick whichever gets walls and doors from the fewest models, then report at Checkpoint A.** Two models (walls from one, doors from another) is acceptable if it's clearly better.

**Licensing.** CubiCasa5K and RMBG-1.4 are non-commercial (CC BY-NC), which fits this project. Credit the model and dataset in your report.

**Safety:**
- **`.pkl` / pickle files run arbitrary code when loaded.** Use `torch.load(..., weights_only=True)` if possible. If the checkpoint needs a full unpickle, do it only in this sandbox, and convert it once to `safetensors`.
- **Read any `trust_remote_code` Python files before running them.**

## 5. The input image: wait for the user

- **The user will share the original floorplan image they gave the LLM.** Use that image for the real run.
- **Until it arrives:**
  - Get the environment, the model, and the pipeline working.
  - You *may* do dry runs on the PNG embedded in `index.html` (decode the base64 `href` of `#planImg`). That copy has been resized to 1194×703 and may differ from the original, so **don't report results from it as the final comparison.**
- **Line up the two images.** The original's resolution or crop may differ from the embedded 1194×703 copy. Work out the scale and offset between them, using feature matching or a few hand-picked corners, and output everything in the app's frame. Report the transform you used.

## 6. What to build

1. **Inference** on the original image, producing a wall mask and door detections.
2. **Vectorization** into simple geometry. Assuming walls are straight and horizontal or vertical is fine; this apartment has no curved walls.
   - Walls: `{ a:[x,y], b:[x,y], thickness }` segments. Merge segments that line up, and drop tiny fragments.
   - Doors: `{ a:[x,y], b:[x,y] }` opening segments across the gap in the wall. No swing direction.
   - Write it all to one JSON file in the app's 1194×703 frame.
3. **A 2D render** (PNG) of only the vectorized walls and doors, so it can be reviewed outside the app.
4. **Changes to `index.html`**, kept small:
   - Add an SVG layer drawn from the JSON: walls as filled rects or thick lines, doors in a distinct style.
   - Add a small control to switch the plan display between **Original image**, **Model walls/doors**, and **Overlay** (model on top of a faded image). This makes the comparison possible in the app itself.
   - Leave furniture, relabels, and existing features working. Handle the existing hand-drawn layers (`#doors`, `#stepUp`, `#outlines`) however makes the comparison clearest, and say how.
   - Embed the JSON inline. **No new runtime dependencies, and no model running in the browser.** Inference stays offline in Python for this spike.
   - Dark mode: the image uses the `--plan-filter` inversion, so make the new layer readable in both themes.
5. Put the spike's scripts in `spikes/pretrained-floorplan-model/`, with a short README on how to reproduce the run. Leave the weights out.

## 7. Gotchas

- **Room labels won't match, and that's expected.** The user renamed rooms (`#relabels`) to match how they'll use the space, not how the listing described them. Don't count label differences between the original image and the app as errors.
- **Some app overlays aren't in the image.** The step-up line, the walk-in closet / fridge / counter / tub outlines, and door swing directions were added by hand. The model can't be expected to find them.
- **What to compare:**
  - **Walls:** the model's vector walls vs. the walls in the raster image, which serve as ground truth. Report how closely they line up (visually, and with a simple pixel overlap measure if that's easy).
  - **Doors:** the model's door openings vs. the 10 hand-placed doors in `#doors` (each `<path>` starts at the hinge, and the arc ends at the far jamb). Report found / missed / false positives.
- **Doors vs. windows.** These models often confuse doors with windows, and plain wall openings with doors. Note any cases.
- **Scale check.** Measure a known room against the image's dimension labels at 16 units/ft and confirm it matches. Being off by a constant factor usually means the image alignment is wrong.

## 8. Deliverables (Checkpoint B)

1. Commits on your own spike branch: scripts, the walls/doors JSON, the 2D render, and the `index.html` changes. **Don't open a PR unless the user asks.**
2. Screenshots at deviceScaleFactor 2 (Playwright with the preinstalled Chromium): the current app, model mode, and overlay mode, all at the same zoom.
3. A short report (in the spike README, also sent to the planning session):
   - which model(s) were used and why
   - setup issues and inference time
   - the image transform used
   - wall and door comparison results, with the failure cases listed
   - an opinion on whether this approach is worth pursuing for the upload feature, and what it would take to run in the browser (ONNX export size, preprocessing work)
