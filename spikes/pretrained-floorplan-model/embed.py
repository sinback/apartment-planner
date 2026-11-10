"""Embed walls_doors.json into index.html's <script id="modelPlanData"> block (compact form).

Usage: python embed.py --json walls_doors.json --index ../../index.html
"""
import argparse
import json
import re

ap = argparse.ArgumentParser()
ap.add_argument("--json", required=True)
ap.add_argument("--index", required=True)
a = ap.parse_args()

d = json.load(open(a.json))
assert d["frame"]["name"] == "app", "embed the app-frame JSON (to_app.py output), not the image-frame one"
slim = {
    "source": "CubiCasa5K (Kalervo et al. 2019), official model; see spikes/pretrained-floorplan-model",
    "walls": [{"a": w["a"], "b": w["b"], "thickness": w["thickness"]} for w in d["walls"]],
    "doors": [{"a": o["a"], "b": o["b"]} for o in d["doors"]],
    "windows": [{"a": o["a"], "b": o["b"]} for o in d["windows"]],
}
blob = json.dumps(slim, separators=(",", ":"))
html = open(a.index).read()
pat = r'(<script type="application/json" id="modelPlanData">)(.*?)(</script>)'
assert len(re.findall(pat, html, re.S)) == 1
html = re.sub(pat, lambda m: m.group(1) + blob + m.group(3), html, flags=re.S)
open(a.index, "w").write(html)
print(f"embedded {len(blob)} bytes into {a.index}")
