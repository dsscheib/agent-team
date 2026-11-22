## Mechanical (FreeCAD)

### Environment
- CAD: FreeCAD 1.1+ (update OS and version for your machine); prefer parametric `.FCStd` plus reproducible Python sources
- Headless: `FreeCADCmd` (Flatpak: `flatpak run --command=FreeCADCmd org.freecad.FreeCAD`); check with `python3 tools/freecad/doctor.py`
- Printer: TBD (model, build volume X x Y x Z mm, nozzle diameter; confirm current nozzle and firmware before slicing)
- Slicer: OrcaSlicer; profile confirmed by hand before any production G-code (`docs/mechanical/slicing.md`)
- Requirements: `docs/mechanical/design-requirements.md`

### Layout
- `models/` native models, `exports/` STEP/STL/3MF, `reports/` verification, `scripts/` CAD generation

### Checks
- `FreeCADCmd tools/freecad/inspect_model.py models/PART.FCStd` writes `reports/PART-geometry.json`
- `python3 tools/freecad/check_build_volume.py reports/PART-geometry.json --volume X Y Z --object Pad` (replace `X Y Z` with your printer's build volume in mm)

### Safety policy
Validation is necessary but not sufficient for mechanically safe or printable designs. Never send prints or change firmware automatically. Get an independent review before the final print.
