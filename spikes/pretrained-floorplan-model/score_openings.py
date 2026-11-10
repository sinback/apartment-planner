"""Score model openings against a hand-marked reference, by position.

Reference JSON (see references/): {"openings": [{"name", "kind", "a", "b"}]}, where kind is
door | window | bifold | doorless. Only doors and windows are scored. A model opening that lands on
a bifold or doorless reference is "neutral": neither a hit nor a false positive.

Matching: a model opening matches a reference when both are on the same axis, their centerlines
are within `across` px, and they overlap along the wall by at least half of the shorter one.
- Several model openings on one reference = one hit, flagged "fragmented" (e.g. a wide window
  drawn with a seam).
- The geometry hit (an opening exists there) and the class (door vs. window) are scored separately.

Usage: python score_openings.py --model walls_doors.image.json --ref references/plan2-openings.json
       [--across 6] [--out score.json]
"""
import argparse
import json


def axis(o):
    (ax, ay), (bx, by) = o["a"], o["b"]
    return "h" if abs(bx - ax) >= abs(by - ay) else "v"


def span(o):
    (ax, ay), (bx, by) = o["a"], o["b"]
    if axis(o) == "h":
        return (ay + by) / 2, min(ax, bx), max(ax, bx)
    return (ax + bx) / 2, min(ay, by), max(ay, by)


def matches(m, r, across):
    if axis(m) != axis(r):
        return False
    cm, m0, m1 = span(m)
    cr, r0, r1 = span(r)
    ov = min(m1, r1) - max(m0, r0)
    return abs(cm - cr) <= across and ov >= 0.5 * min(m1 - m0, r1 - r0)


def score(model, ref, across):
    mods = [dict(o, cls="door") for o in model["doors"]] + [dict(o, cls="window") for o in model["windows"]]
    refs = ref["openings"]
    hits_of = {i: [] for i in range(len(refs))}
    claimed = set()
    for j, m in enumerate(mods):
        cands = [i for i, r in enumerate(refs) if matches(m, r, across)]
        if cands:
            # nearest centerline wins (D7/D8 are back to back, 4 px apart)
            i = min(cands, key=lambda i: abs(span(m)[0] - span(refs[i])[0]))
            hits_of[i].append(j)
            claimed.add(j)
    rows, out = [], {}
    for kind in ("door", "window"):
        items = [i for i, r in enumerate(refs) if r["kind"] == kind]
        found = [i for i in items if hits_of[i]]
        right = [i for i in found if any(mods[j]["cls"] == kind for j in hits_of[i])]
        frag = [i for i in found if len(hits_of[i]) > 1]
        out[kind] = {"reference": len(items), "found_as_opening": len(found),
                     "found_with_right_class": len(right), "fragmented": len(frag),
                     "missed": [refs[i]["name"] for i in items if not hits_of[i]],
                     "wrong_class": [refs[i]["name"] for i in found if i not in right]}
    neutral = [refs[i]["name"] for i in hits_of
               if refs[i]["kind"] in ("bifold", "doorless") and hits_of[i]]
    fps = [m for j, m in enumerate(mods) if j not in claimed]
    out["neutral_hits"] = neutral
    out["false_positives"] = [{"cls": m["cls"], "a": m["a"], "b": m["b"]} for m in fps]
    out["false_positive_count"] = {"as_door": sum(m["cls"] == "door" for m in fps),
                                   "as_window": sum(m["cls"] == "window" for m in fps)}
    for i, r in enumerate(refs):
        rows.append({"ref": r["name"], "kind": r["kind"],
                     "model": [mods[j]["cls"] for j in hits_of[i]]})
    out["per_reference"] = rows
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--ref", required=True)
    ap.add_argument("--across", type=float, default=6.0, help="max centerline distance, px")
    ap.add_argument("--out")
    a = ap.parse_args()
    res = score(json.load(open(a.model)), json.load(open(a.ref)), a.across)
    if a.out:
        json.dump(res, open(a.out, "w"), indent=1)
    for k in ("door", "window"):
        r = res[k]
        print(f"{k}s: {r['found_as_opening']}/{r['reference']} found, {r['found_with_right_class']} right class, "
              f"{r['fragmented']} fragmented; missed {r['missed']}; wrong class {r['wrong_class']}")
    print("neutral:", res["neutral_hits"])
    print("false positives:", res["false_positive_count"], res["false_positives"])


if __name__ == "__main__":
    main()
