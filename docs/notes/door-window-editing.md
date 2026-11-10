# Door/window review and editing (design note)

*From the user, while testing plan 2. Recorded so it doesn't get lost.*

**What happened.** On plan 2, a "double-wide window with a weird seam" turned out to be a **sliding
door**. The user, who has been inside the building, couldn't tell from the drawing at first. The
model labeled it a window.

**Implications for the app:**

1. **An import review step.** After an upload, ask per opening: "Is this really a door? y/n", and
   more generally door / window / sliding / bifold / plain opening. Some drawings are ambiguous even
   to a person who knows the place.
2. **Openings and walls stay editable after furniture placement starts.** People will realize later
   that "that window is really a door". If fixing it means redoing their furniture layout, they'll
   give up. So:
   - Edit opening type, swing and walls from a menu at any time, not only during import.
   - Furniture positions must survive those edits. Store edits as overrides on top of the imported
     geometry, so furniture (already stored separately, in inches) is untouched.
   - If an edit makes furniture overlap a newly swinging door, flag it rather than moving anything.
3. **Every user correction is labeled data.** A confirmed or flipped opening type is exactly the
   held-out reference the spike lacks. Keep the model's original suggestion next to the user's
   answer.

Related: [image import sanitization](image-import-sanitization.md), and
[`plan2-results.md`](../../spikes/pretrained-floorplan-model/plan2-results.md).
