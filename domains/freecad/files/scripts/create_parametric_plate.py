"""Example FreeCAD script. Run with FreeCADCmd in a configured FreeCAD environment.
Creates editable sketch + pad in FCStd, plus STEP/STL. Dimensions in mm.
Not a load-bearing design; change parameters after review.
"""
from pathlib import Path
import FreeCAD as App
import Part
import Sketcher

OUT = Path(__file__).resolve().parents[1]  # installed at <project>/scripts/
(OUT / "models").mkdir(exist_ok=True)
(OUT / "exports").mkdir(exist_ok=True)
width, depth, thickness = 60.0, 40.0, 3.0

doc = App.newDocument("SampleMountingPlate")
body = doc.addObject("PartDesign::Body", "Body")
sketch = doc.addObject("Sketcher::SketchObject", "PlateOutline")
body.addObject(sketch)
V = App.Vector
corners = [(0, 0), (width, 0), (width, depth), (0, depth)]
for i in range(4):
    a, b = corners[i], corners[(i + 1) % 4]
    sketch.addGeometry(Part.LineSegment(V(a[0], a[1], 0), V(b[0], b[1], 0)), False)
for i in range(4):
    sketch.addConstraint(Sketcher.Constraint("Coincident", i, 2, (i + 1) % 4, 1))
for i in (0, 2):
    sketch.addConstraint(Sketcher.Constraint("Horizontal", i))
for i in (1, 3):
    sketch.addConstraint(Sketcher.Constraint("Vertical", i))
sketch.addConstraint(Sketcher.Constraint("Coincident", 0, 1, -1, 1))
sketch.addConstraint(Sketcher.Constraint("Distance", 0, width))
sketch.addConstraint(Sketcher.Constraint("Distance", 1, depth))
pad = body.newObject("PartDesign::Pad", "Pad")
pad.Profile = sketch
pad.Length = thickness
doc.recompute()
assert not pad.Shape.isNull(), "Pad shape is null"
assert pad.Shape.isValid(), "Pad shape invalid"
assert len(pad.Shape.Solids) == 1, "Expected one solid"
doc.saveAs(str(OUT / "models" / "sample-mounting-plate.FCStd"))
Part.export([pad], str(OUT / "exports" / "sample-mounting-plate.step"))
Part.export([pad], str(OUT / "exports" / "sample-mounting-plate.stl"))
print("Saved example model, STEP and STL")
App.closeDocument(doc.Name)
