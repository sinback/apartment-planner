# Retro: the pretrained floorplan model spike

A review of how the spike in [`spikes/pretrained-floorplan-model/`](../../spikes/pretrained-floorplan-model/README.md)
was run, written for someone learning to do this kind of vision work. It follows the transcript,
including its tool calls and outputs, and covers both what was found and how it was found, mistakes
included. 🔍

## 1. Timeline

| Phase | What happened | Why at that point |
|---|---|---|
| **Candidate vetting** | Read Hugging Face API metadata, model cards and `config.json` `id2label` for each candidate. Searched HF for more door-capable checkpoints. | The brief said "verify each claim". Labels and cards cost a few KB to fetch; weights cost hundreds of MB. |
| **Network/permission blocks** | `add_repo` for CubiCasa was denied. The PyTorch install then failed on a redirect host. Stopped twice and asked. | The user's standing instruction was to stop on network issues rather than work around them. |
| **Setup** | Cloned the repo, downloaded the 209 MB weights, read `hg_furukawa_original.py` and the notebook before running anything. | Third-party code plus a pickle checkpoint: read first, then load with `weights_only=True`. |
| **Inference** | Ran 1× and 2× scales with the official 4-rotation test-time augmentation. | Unsure whether this plan's ~6 px walls were too thin for a model trained on larger scans, so both were run up front. |
| **First look at masks** | Overlaid the argmax masks (wall red, door green, window blue) on the image. | It's the cheapest way to tell "the model works" from "the model is confused" before writing any vectorization. |
| **Post-processing** | Ran the repo's own `get_polygons` after shimming SciPy. Got 26 openings, all labeled "window". | The model's own vectorizer was the fair baseline to try before writing one. |
| **Door/window discovery** | Cropped openings at 5× and printed cross-wall intensity profiles. | All-"window" output combined with geometry that matched the doors suggested a labeling problem, not a detection problem. |
| **Vectorization** | Morphology turned walls into H/V segments, then diagonals and door cuts were added. Iterated on the bay window. | The brief asked for simple `{a,b,thickness}` geometry. |
| **Metrics** | `compare.py`: wall pixel overlap, door matching against `#doors`, room-size scale check. | Ran after the geometry looked plausible, so the numbers measured something stable. |
| **App integration** | Inline JSON, a three-mode Plan select, theme tokens, Playwright screenshots. | This came last because it consumes the final JSON. |
| **Report** | README plus Checkpoint B, then a revision that folded in the planning session's late feedback. | |

## 2. What went wrong, and what each teaches

### Candidate vetting

**The brief's Mask2Former assumption.**
- *What happened:* the brief hoped `phungpx/mask2former-swin-base-cubicassa` might supply doors.
  One `curl` of its `config.json` returned `{'0': 'wall'}`, and its card agreed ("Predicts 1
  class(es): wall"). The `Hyunwoo1605` model's labels looked ideal (`door`, `window`, `wall`), but
  its config's `_name_or_path` and the author's dataset list showed it was trained on `FP_STR`, not
  CubiCasa5K.
- *Lesson:* `id2label`, the base model and the dataset are the cheapest facts about a model. Check
  them before you download weights, and before you trust a search-result summary.

### Network and environment

**Blocked hosts.**
- *What happened:* `download.pytorch.org` returned 200 in the initial reachability test. The pip
  install still failed, because the wheels are served from `download-r2.pytorch.org`. A reachability
  test on the index host told you nothing about the file host. HF has the same pattern (its CDN
  hosts), which the brief had warned about.
- *What went right:* the run stopped and reported the exact host instead of trying a workaround.
  That kept the user in control of the permission change.
- *Lesson:* when you test reachability, follow one real download, redirects included.

**The `importlib` detour.**
- *What happened:* to avoid installing `lmdb`/`svgpathtools`, `infer.py` loaded `augmentations.py`
  by file path. It failed anyway, because `augmentations.py` line 5 imports
  `floortrans.loaders.svg_utils`, which runs the package `__init__`. Installing two small packages
  was the right call from the start.
- *Lesson:* before you engineer around a dependency, grep the imports of the file you actually need,
  not just its siblings.

**SciPy API rot.**
- *What happened:* `stats.mode(widths).mode[0]` raised an `IndexError` on modern SciPy.
- *Fix:* a runtime shim on `pp.stats` instead of editing the cloned repo. Third-party code stays
  pristine, so it can be re-cloned and the fix is visible in our own code.
- *Lesson:* expect bit-rot in 2019 research code, and patch at your boundary.

### Inference and reading the masks

**Scale 1 vs. scale 2.**
- *What happened:* at 1×, the mask painted over several door gaps. The post-processing also put one
  opening on the solid wall at x 780 instead of the closet gap at x 822. That was confirmed by a crop
  showing the x 780 wall solid and the gap on the far wall, with green Door pixels near x 822 in the
  mask.
- *Lesson:* input resolution relative to the training distribution is a hyperparameter. Here the
  proxy is wall thickness in pixels.

**Misreading the first overlay.** ⚠️ This is the most instructive slip.
- *What happened:* after the first mask image, the run concluded that scale 2 "keeps them open"
  (door gaps). That was wrong. The overlay painted door and window pixels *on top of* wall pixels,
  so wherever the icon classes fired, the wall underneath was hidden. Later, `wall_diff.png` showed
  red ("model only") at every door and window, and the Wall class ran straight through the openings.
  The run acknowledged this ("I misread").
- *Lesson:* a multi-class overlay answers "what's the top label here", not "is class X present here".
  - Use per-class masks shown separately, or a two-way diff map against a reference.
  - Watch the draw order: whatever you paint last hides what's under it.

**The Door class barely fired.**
- *What happened:* 339 px at 1× and 35 px at 2×, in a plan with 10 doors. This is domain shift:
  CubiCasa5K teaches "door" as a swing arc, and this Matterport-style export draws a door as a plain
  gap between two thin lines.
- *What still worked:* the opening-corner heatmaps fired correctly. So the *geometry* of the
  openings was right (all 10 doors within about 1 px along the wall), and only the class decision,
  which leans on icon segmentation, failed.
- *Lesson:* multi-head models can fail in one head and not another. Score the heads separately
  before you judge the model.

### Vectorization

**The bay window took three tries.**
1. *First try:* the vectorizer used horizontal and vertical morphological openings (a 9 px run
   minimum). On a 45° wall about 6 px thick, horizontal runs are about 8–12 px long, so many passed.
   They connected into staircase components, and their bounding boxes put a fake vertical wall at
   x 1064 and scattered 1 px-thick fragments.
2. *Second try:* dropping thin runs removed the slivers, but the diagonals were still missing, and
   the fake wall was still there.
3. *What cracked it:* an ASCII dump of the raw mask. It showed clean diagonals and the true vertical
   at x 1071–1078, so the mask was fine and the vectorizer was the problem.
4. *Real fix:* separate diagonals *first*, with an opening by a 15 px diagonal line. A diagonal line
   that long fits inside a 45° wall but not inside a 6 px-thick axis-aligned wall or its corners.
   Fit the diagonals with `minAreaRect`, then run H/V on the rest.

- *Lesson:* when the output geometry is wrong, check the input mask before tuning the algorithm.
  Here the lowest-tech view (ASCII) was the fastest.

### Metrics

**Wall precision 0.65 on the first pass.**
- *What happened:* the tempting reading was "walls too thick". The diff map showed the red sat almost
  entirely at windows and doors, which is the "Wall runs through openings" fact above.
- *Fix:* cut door spans out of the walls (real vectorization semantics), and report scores with and
  without window spans. Excluding windows, precision rose to 0.80 exact and 0.958 within 1 px
  (0.79 and 0.949 after the merge-bug fix found on plan 2).
- *Lesson:* diagnose a bad metric spatially before you tune parameters.

**The glazing heuristic.**
- *What happened:* the threshold was picked after printing profiles for these very 26 openings
  (windows ≤ 160, doors ≥ 197, threshold 170). Its 10/10 is therefore a training-set score.
- *What the planning session added:* it said so, and asked that the app render the heuristic class
  while the JSON keeps `model_class`. It also reframed the ~1 px door agreement: the hand-placed
  doors were read by an LLM from the same pixels, so agreement means two readings agree, not that
  either is true to the apartment.
- *Lesson:* label every number by where its reference came from.

**Weaknesses a careful reviewer would also flag in `compare.py`:**
- **The reference is "dark pixels < 100 with components ≥ 150 px removed".**
  - The threshold is arbitrary. Antialiased wall edges sit around 100–200, so the reference walls
    are slightly thinner than the drawn walls. That inflates the model's "too thick" bias.
  - The area filter would drop short wall stubs and keep large dark text, though neither seemed to
    occur here.
- **Within-1 px precision of 0.958 is partly a tolerance artifact.** The model is consistently
  about 1 px thick, and a 1 px dilation absorbs exactly that bias. Report the bias directly (mean
  model thickness vs. measured drawn thickness) instead of hiding it inside a tolerance.
- **The room-size raycast** takes a median over 9 parallel rays from a hand-chosen point, measured
  against the *model's* walls. It confirms scale, not wall accuracy. The label points (`ROOMS`) are
  hardcoded to this plan.
- **Door matching tolerance is 8 px,** and the error is dominated by the face-vs-centerline
  convention (3.2 px). A matcher that measures along-wall and across-wall error separately would
  show the real alignment: about 1 px along the wall.
- **Window recall (14/16) was counted by eye,** not by `compare.py`. There's no window reference
  file, so it isn't reproducible.

### Process

- **Missed planning reply.** The planning session's Checkpoint A reply ("no objections" plus five
  report requests) arrived about 12 minutes before it was read. Checkpoint B went out without it.
  The run never called `ReadNotifications` before sending the checkpoint.
  - *Lesson:* before you send a checkpoint, drain the inbox.
  - The fix (a README revision and a follow-up message) was cheap only because the requests were
    about wording.
- **Misaddressed `send_message`.** One message went to the run's own session ID, an ID that differs
  from the planning session's only after `session_01SyzSt`. The user was fine with it.
  - *Lesson:* copy IDs from the source text, don't retype them.
- **Estimate before measuring.** The first README draft guessed "~52M parameters, about 209 MB", and
  the background export then measured **17.4M parameters and a 69.5 MB fp32 ONNX**. The 209 MB
  checkpoint holds `optimizer_state` too, which the run had printed as a key. The README was
  corrected before commit, and Checkpoint B used the measured numbers.
  - *Lesson:* checkpoint file size ≠ model size. Count parameters.
- **Small stuff:**
  - A `__pycache__/*.pyc` file got committed and was removed in a follow-up commit. Write
    `.gitignore` before the first `git add -A`.
  - Two `Monitor`s were started for the same pip install.
  - The ONNX export ran in the foreground with a 300 s limit and got moved to the background.
    Anything likely to take minutes should start in the background.
  - The vectorizer's leftover `keep` variable needed a `sed` cleanup after a scripted edit. Mixing
    regex edits with structural changes is fragile.

## 3. A reusable method ✅

1. **Read the labels first.** Check `id2label`, the base model, the training dataset and the license
   before downloading any weights.
2. **Check hosts by doing a real download,** redirects included. Stop and ask on a block.
3. **Read third-party code before running it.** Prefer `weights_only=True` for checkpoints, and patch
   bit-rot at your own boundary.
4. **Establish the transform before anything else.** Use a pixel diff or shift search, plus a scale
   check against known dimensions. Every later number depends on it.
5. **Try at least two input scales.** Pick one based on the target feature's size in pixels, not on
   speed.
6. **Look at raw outputs in more than one view:**
   - per-class masks shown separately
   - an ASCII or zoomed crop of the trouble spot
   - a **diff map** against the reference

   Be suspicious of layered overlays.
7. **Score each head of the model separately** (geometry vs. class).
8. **Keep model output and your heuristics apart** in the data (`model_class` vs. the final class),
   and say which one the UI shows.
9. **Any rule you tune by eye needs held-out images.** Until then, call its score optimistic.
10. **Name the reference behind every metric.** Report biases directly, not hidden inside a
    tolerance.
11. **Measure costs.** Time each stage, count parameters, and export once to check size.
12. **Drain the inbox before each checkpoint,** and copy IDs, don't retype them.

## 4. Open risks for the next image ⚠️

- **Drawing style.** On a plan with swing arcs, the Door class may finally fire, and the glazing
  check could misfire: an arc next to a window, or a window drawn as a single line. Hand-drawn,
  CAD-export and real-estate styles each need checking.
- **Resolution.** The 2× choice was tuned to about 6 px walls. Normalize each upload to a target
  wall thickness (estimated from a first pass, or from the dark-run histogram) instead of using a
  fixed factor.
- **Scanned or photographed plans.** Skew, perspective, JPEG noise and uneven lighting would all
  break the identity-transform assumption and the 100-grey threshold in `compare.py`. They'd need
  deskewing, a homography and adaptive thresholding.
- **Non-axis walls.** Only 45° diagonals are handled. Other angles and curves need a general line
  fitter, such as Hough or contour simplification.
- **Scale.** This plan's 16 px/ft came from the app. A new plan needs a known dimension: the user
  types one in, or the dimension labels are read by OCR. OCR runs into label formats like `13'1"`
  and the question of which label belongs to which room.
- **Openings with no glyph** (plain gaps, cased openings, sliding or pocket doors) are invisible to
  the opening detector. Gaps in the wall mask could be a second source of opening candidates.
- **Room segmentation** was mostly "Undefined" here. Don't count on it for room names.

## 5. Addendum: the reusability pass 🔁

*Added after the review, while making the pipeline reusable for new images. The new self-test
caught three more bugs, all on a copy of the plan shrunk to 0.8× and shifted.*

**Two different "wall thicknesses".**
- *What happened:* thresholds were made relative to wall thickness, measured from the model's mask.
  On the shrunk copy, that measure said 6 px at 1×, while the drawn walls were 4 px.
- *Why:* the model's output is upsampled ×4, so its mask can't draw walls much thinner than about
  5 px. A 4 px wall and a 6 px wall both come out around 5 px. (The skeleton-distance measure also
  rounded up by 1 px.)
- *First fix, half right:* measure the *drawn ink* inside the mask instead (6 px and 4 px, both
  correct). That broke vectorization badly. Wall recall against the original fell to 0.64, because
  the morphology runs on the *mask*, whose walls were still 5–6 px:
  - a `min_run` of 6 let vertical walls through the horizontal filter, so whole wall networks
    collapsed into bounding-box "walls";
  - a 10 px diagonal kernel fit inside every L/T junction and carved them out.
- *Real fix:* keep two thicknesses. Mask thickness drives mask morphology; ink thickness drives image
  steps (the glazing profile) and scoring tolerances. Add hard guards: `min_run > mask thickness + 1`,
  and a diagonal kernel longer than `2 × mask thickness`.
- *Lesson:* a measurement belongs to the space it was taken in. A threshold applied to array X has to
  come from array X.

**More upscaling isn't better.**
- *What happened:* the retro's advice (normalize to a target wall thickness) became "aim for 12 px",
  which picked 3× for the 4 px copy. At 3×, the model lost whole walls (the guest bedroom's bottom
  wall) and missed the same door (Hall → Living) on both shrunk copies. 2× was fine both times.
- *Tried next:* let a reference-free score pick (wall F1 against the image's own ink). It preferred
  2× on one copy (0.969 vs 0.945) and 3× on the other (0.966 vs 0.955). The only difference between
  the copies was padding. The wall score can't see opening quality, and its margins were noise.
- *Current rule:* default to 2×, and switch only when another candidate beats it by more than 0.02 F1.
  This is calibrated on one plan; recheck it on new ones.
- *Lesson:* a model's useful input range has two edges. A proxy metric that ignores the quantity you
  care about (openings) can't select for it.

**Regression test before refactor.**
- The refactor was checked by rerunning the original and requiring **byte-identical** `index.html`
  and output JSON, then running the shrink-and-shift self-test (`selftest.py`).
- The shifted copy was the useful test: the original alone passed every buggy version above.
  - *Lesson:* a test image with exactly the parameters you tuned on can't catch tuning bugs. Perturb
    it: scale, pad, shift.

## 6. Addendum: what plan 2 (the first held-out image) taught 🧪

- **A bug that had been covering for the model.** On plan 2, the vectorizer dropped whole interior
  walls at 1× although the mask had them. The cause was `merge_collinear` merging in rounded order
  and never extending a run's start.
  - Fixing it changed one plan 1 wall. The closet "gap" that the plan 1 report credited to the
    model had been kept open by the bug.
  - *Lesson:* when a pipeline has several layers, a bug in one can make another layer look better
    than it is. Inspect each layer's raw output, not just the final picture.
- **The hand-tuned rule failed out of sample.** The glazing check scored 0/10 doors on plan 2,
  because the contrast cue is inverted in the CubiCasa-app drawing style. That's the "held-out
  data" warning from section 3, now borne out.
- **Write the reference before the run.** The plan 2 opening list was committed before any model
  output existed, so it couldn't drift toward the model's answers.
- **Different scales suit different parts of the output.** On plan 2, openings were best at 1×
  (fewest false positives) and walls at 2–3×. The single-scale auto rule would have picked 3×, the
  worst scale for openings.
