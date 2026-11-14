# FreeCAD mechanical and FDM operating principles

- Before acting, read `AGENTS.md` and `docs/mechanical/design-requirements.md`. Take the FreeCAD version, printer, nozzle, build volume and slicer from them rather than assuming; confirm the actual FreeCAD executable with `python3 tools/freecad/doctor.py`.
- Run FreeCAD scripts headless with `FreeCADCmd` (Flatpak: `flatpak run --command=FreeCADCmd org.freecad.FreeCAD`). The Flatpak sandbox has its own `/tmp`, so keep inputs and outputs inside the project.
- Keep native parametric `.FCStd` models in `models/`, reproducible Python sources in `scripts/`, STEP/STL/3MF exports in `exports/` and verification output in `reports/`. Never replace native CAD with mesh-only geometry unless explicitly asked.
- Work only within your delegated scope. One role owns a model at a time; route dimensional and interface changes through the parent agent. Never overwrite user files destructively, and do not download external files without approval.
- After model changes, run `tools/freecad/inspect_model.py` and `tools/freecad/check_build_volume.py`, and say which checks were not run. Shape validity and build-volume checks are not proof of strength, fit or printability.
- Never send printer commands, upload or start print jobs, or change firmware. Final G-code and printing need human review.
- Report design decisions, files touched, dimensional assumptions, checks performed and unresolved risks.
