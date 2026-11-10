# Image import sanitization ritual

A note for the future "upload a floorplan" feature. Before any model or vectorizer sees an uploaded
image, put it through a fixed set of checks. Each check either **normalizes** the image (fixes it
silently and logs it), **warns** the user, or **refuses** the image. Refuse only when there's
nothing sensible to do: a refusal costs the user more than a fix we can do ourselves.

The principle: **the model should see what the user saw.** Viewers (browsers, chat apps, Zillow)
quietly do things to images before display. Image libraries often don't. Every gap between the two
is a way for the model to get an image that looks fine to the user and is garbage to the code.

## Normalize (silently, and record it)

| Problem | Why it bites | Fix |
|---|---|---|
| **Transparency** | A fully transparent pixel still stores RGB values that nothing displays. Exporters often write black (0,0,0). libwebp by default *rewrites* them for compressibility; `cwebp -exact` is needed to keep them. Browsers composite onto the page background, so the user sees white. `PIL.Image.convert("RGB")` just drops alpha, so the model sees black. | If any alpha < 255, composite onto white first. |
| **EXIF orientation** | Phone photos and some exports store "rotate 90°" as a metadata flag. Viewers apply it; raw pixel reads don't. | `ImageOps.exif_transpose` first thing. |
| **Color modes** | Palette (P), CMYK, 16-bit, grayscale with alpha (LA), and so on. Thresholds and the model assume 8-bit RGB. | Convert to 8-bit RGB (after the alpha and orientation steps). |
| **Animated WebP/GIF** | Has more than one frame; libraries load the first frame by default. | Use frame 0 and log the frame count. |
| **Lossy-compression blur** | Listing images are recompressed JPEG/WebP. Thin walls smear into grey. Plan 2 (a Zillow `.webp`) had more mid-grey pixels than dark ones. | Don't "fix" the image. Make downstream thresholds robust instead (no hard `gray < 100` assumptions). |

## Warn (go ahead, but tell the user)

- **Very low resolution:** measured wall thickness under ~3 px at 1×, or a plan region under a few
  hundred px. Results will be rough.
- **Inverted or dark-mode plans** (light lines on a dark background): mean luminance is low. Offer
  to invert. Don't do it silently.
- **Photos of paper plans:** perspective, shadows or skew. The pipeline assumes flat, axis-aligned
  line art.
- **Several floors or plans in one image,** or large text blocks such as the "Total GLA" footer.
  Ask the user to crop, or crop to the largest plan region and show what was kept.

## Refuse (with a clear message)

- The file doesn't decode as an image, or it's empty.
- It's absurdly large (decompression-bomb guard: cap the pixel count).
- After all the fixes above, there's no plausible plan in it, for example no wall-like structure
  detected at all.

## Why this is a list and not an afterthought

Every item above makes vision code fail *quietly*: no exception, just confidently wrong walls.
Having a checklist that runs first, and logs what it changed, makes those failures visible and
consistent across uploads.
