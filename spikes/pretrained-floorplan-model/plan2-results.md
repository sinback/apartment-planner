# Plan 2: first held-out test

**Input.** A Zillow listing image (`.webp`, pasted into chat; 1024×768). It's the 1st floor of a
three-floor house, and the footer reads *"Floor plan created by CubiCasa App"*. So this is probably
the same drawing style as the model's training data. The image isn't committed (third-party listing
photo).

**Baseline setup.** The only change to the image was cropping off the footer text:
`crop = original[x 371:652, y 2:627]`, so the crop-frame offset is (371, 2). Inference was forced at
1×, 2× and 3×. Results are scored with the **model's own door/window class** (`--no-glazing`) first,
and the glazing check from plan 1 second.

**Reference.** [`references/plan2-openings.json`](references/plan2-openings.json): every door and
window, hand-marked from the image **before any model run** (committed first), in the crop frame.
- **Doors:** 11 hinged doors, matching the user's count. D7 and D8 are two separate doors back to back
  in one doorway (bath and hall).
- **Windows:** 12, matching the user's count. The pre-run list had 13 candidates. **After the run**,
  the user identified W3 (the "double-wide window with a seam" on the top-right bedroom's top wall)
  as a **sliding door**, which the user couldn't tell from the drawing at first either. Only its
  `kind` changed; no positions were edited.
- **Neutral (neither hit nor false positive):** the sliding door (S1), the bifold closet doors (B1),
  and two doorless openings (O1, the faint Living ↔ Eat-in doorway, and O2).

Scoring script: [`score_openings.py`](score_openings.py). It matches by position: same axis,
centerline within 6 px, at least 50% overlap. A window detected as several pieces counts as one hit,
flagged "fragmented".

## Openings

| Scale | Doors found (right class) | Windows found (right class) | Fragmented windows | False positives (door / window) |
|---|---|---|---|---|
| 1× | **10/11 (10)** | **12/12 (12)** | 3 | **2 / 4** |
| 2× | 10/11 (10) | 12/12 (12) | 3 | 2 / 9 |
| 3× | 10/11 (10) | 12/12 (12) | 3 | 2 / 10 |

**The scoring rules don't drive this.** The across-wall tolerance (6 px) was chosen after the run,
so I rescored at 3 px and 10 px: identical results at every scale.

- **The model's own door/window class is right on every opening it found, at every scale.** This
  reverses plan 1, where it called all 26 openings "window". The Door mask fires on ~1,000 px here,
  vs. 35 px on plan 1.
- **Missed door: D8**, the hall door back to back with the bath door. The model did see it, but as a
  vertical opening along the door's *leaf* (x 51, y 382–417) instead of across the doorway. That
  counts as one miss plus one door false positive.
- **The other door false positive** is a light, opening-like glyph on the bath's right wall beside the
  vanity (x 84, y 335–355). The drawing is ambiguous there.
- **Every window false positive is furniture or fixture line art:** kitchen counter and sink lines,
  the stove edge, the toilet, the laundry machines, and the closet shelf line between the bedrooms.
  They don't come from the Window mask (it fires only on real windows). They come from the opening
  post-processing pairing up corner-heatmap peaks on those lines. More upscaling gives more of them.
  That's the motivation for the user's next experiment: whiting out furniture before inference.
- **Fragmentation:** wide windows come out in 2 pieces: W11 and W13 (both drawn with seams), and W9
  (the bay front). The sliding door S1, the "double-wide window" the user expected the model to
  over-count, is labeled **window** by the model, and split in 2 at 2×.
- **Raw window counts, for comparison with the user's "15 or 16" guess.** The model's actual
  window output is **20 at 1× and 26 at 2× and 3×**. Of those, 15–16 are pieces on real windows or
  the sliding door; the user's fragmentation intuition was right. The remaining 4–10 are the
  furniture false positives, on top of that.
- **Neutral:** the sliding door is detected at every scale, labeled window. At 3×, the faint
  Living ↔ Eat-in doorway is detected as an opening. The bifolds are never detected.
- **The model's own icon probability separates the furniture false positives.** I averaged the
  model's Door + Window probability along each opening:

  | Scale | Hits (doors and windows) | Furniture false positives | Door false positives |
  |---|---|---|---|
  | 1× | 0.47–0.97 | **0.00** (all 4) | 0.65, 0.86 |
  | 2× | 0.92–0.99 | **0.00–0.16** (8 of 9; one at 0.54) | ≤0.54 |
  | 3× | 0.76–0.99 | **0.00–0.04** (9 of 10; one at 0.32) | ≤0.51 |

  - So the post-processing labels openings "window" with almost no support from the model's own
    icon output.
  - This cue comes from the model, so it shouldn't depend on drawing style the way the glazing
    check did.
  - **I haven't built a filter from it:** a threshold picked on this image would be tuned on the
    test data again. It's a candidate to test on the *next* plan, and a natural comparison for the
    furniture whiting-out experiment.

## Glazing check (plan 1's door/window rule): fails on held-out data

| Scale | Doors with right class | Windows with right class |
|---|---|---|
| 1× | 0/10 | 5/13 |
| 2× | 0/10 | 5/13 |
| 3× | 0/10 | 4/13 |

The cue is **inverted** in this drawing style:
- **Doors** are drawn with dark jamb and threshold lines inside the wall band (profile minimum
  118–177).
- **Windows** come out lighter after the image's blur and compression (161–223).

The plan 1 rule, "dark lines inside the wall = window", tags doors as windows. That's the
"tuned and tested on the same image" risk from the plan 1 retro, now confirmed. **The rule should
not be used** unless the model's own class is clearly broken (as on plan 1). Even then, it would
need per-style calibration.

## Walls

- **Wall mask (the model):** good at every scale. It catches both thick exterior walls (~5 px) and
  thin interior ones (~3 px). It also labels the **solid black blocks** (the chimney mass between
  the living room and the primary bedroom, and the black block in the kitchen at 2×) as wall.
- **Vectorizer bug, found and fixed.** At 1×, whole interior walls disappeared from the vector
  output although the mask had them.
  - The cause was `merge_collinear`. It merged nearly collinear segments in rounded-coordinate
    order and only ever extended a run's *end*, so a long segment merged into a shorter one lost
    its left part. Plan 2's walls sit on slightly different pixel rows (1 px apart); plan 1's mostly
    didn't.
  - The fix clusters segments into lines and does a proper interval merge.
  - **The fix changed one plan 1 wall.** The model's mask bridges plan 1's closet opening (x 823,
    y 341–376) with a thin, 1 px-offset wall piece, and the old bug happened to drop it. So the
    plan 1 report's claim that "the wall mask leaves the closet gap open" was wrong. Plan 1's
    within-1 px wall precision moves from 0.958 to 0.949, and the committed plan 1 outputs were
    regenerated.
- **Remaining vectorizer issues:** the black blocks. The diagonal pass fits a rotated rectangle to
  the chimney at 1×, and a scribble to the kitchen block at 2×.
- **Wall scores** (excluding window spans; **low confidence**, because the "dark ink" reference is
  weak on this blurry image):

  | Scale | IoU | Within 1 px precision / recall |
  |---|---|---|
  | 1× | 0.611 | 0.868 / 0.930 |
  | 2× | 0.657 | 0.848 / 0.981 |
  | 3× | 0.695 | 0.887 / 0.979 |

## Scale

- **For openings, 1× is best:** same hits as 2× and 3×, and the fewest false positives.
- **For walls, 2× and 3× are better** (fewer thin walls lost).
- **Auto-scale picks 3×** (confirmed by running `run.py --scale auto`: `scale_selection.json` has
  2× at 0.9097 and 3× at 0.9307, so 3× wins by a 0.021 margin over the 0.02 threshold). That's the
  scale with the most false-positive windows. The wall-only score can't see opening quality, as
  already noted after plan 1.
  - **Takeaway:** walls and openings want different scales. Running openings at 1× and walls at 2×
    is cheap here (6–19 s per pass) and is worth trying.

## Predictions (written before the run) vs. results

| Prediction | Result |
|---|---|
| The Door class fires on the swing-arc doors | ✅ 10/11 hinged doors, all with the right class |
| Bifolds: unsure | Not detected as openings (neutral) |
| The glazing check becomes unnecessary or harmful | ✅ **Harmful:** 0/10 doors right |
| Exterior walls fine; thin interior walls dropped or broken | ⚠️ The mask kept the thin walls. Losses at 1× were a **vectorizer bug** (now fixed), not the model. |
| Black blocks come out as thick wall blobs | ✅ Labeled wall by the model; the vectorizer makes odd shapes of them |
| Auto-scale tries 2×/3× and probably keeps 2× | ❌ It picks 3× (by a 0.021 margin, confirmed by running it), the worst scale for openings |
| No 45° walls, so diagonal handling shouldn't matter | ❌ The diagonal pass misfires on the black blocks |

## Open items

- ~~Which of the 13 window candidates isn't a window~~: resolved, W3 is a sliding door.
- Whether walls the model draws across gaps in the image should be cut. Today only *detected*
  doors are cut. The merge fix made plan 1's closet opening appear closed in Model mode: more
  faithful to the model, worse for furniture planning.
- The furniture whiting-out experiment, against this baseline.
- The vectorizer's handling of solid blocks: the diagonal pass should accept only elongated
  components, not filled blobs.
