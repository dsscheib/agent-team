"""Run through FreeCADCmd: FreeCADCmd tools/freecad/inspect_model.py path/to/file.FCStd

Checks geometry and makes a report in reports/ (no changes to source).
"""
import sys, json
from pathlib import Path
import FreeCAD as App

if len(sys.argv) < 2:
    raise SystemExit("Usage: FreeCADCmd tools/freecad/inspect_model.py model.FCStd")
source = Path(sys.argv[-1]).resolve()
if not source.is_file():
    raise SystemExit("File not found: " + str(source))
doc = App.openDocument(str(source))
doc.recompute()
items = []
for obj in doc.Objects:
    if not hasattr(obj, "Shape") or obj.Shape.isNull():
        continue
    s = obj.Shape
    bb = s.BoundBox
    items.append({"object": obj.Name, "type": obj.TypeId,
        "valid": bool(s.isValid()), "solid_count": len(s.Solids),
        "volume_mm3": round(s.Volume, 4),
        "envelope_mm": [round(bb.XLength, 3), round(bb.YLength, 3), round(bb.ZLength, 3)]})
if not items:
    raise SystemExit("No non-null shapes found")
valid = all(i["valid"] for i in items)
# A multi-solid document is often valid: human/agent must identify the printable final features.
report = {"source": str(source), "shapes": items, "all_shapes_valid": valid}
outdir = Path.cwd() / "reports"
outdir.mkdir(exist_ok=True)
out = outdir / (source.stem + "-geometry.json")
out.write_text(json.dumps(report, indent=2))
print(json.dumps(report, indent=2))
App.closeDocument(doc.Name)
if not valid:
    raise SystemExit(1)
