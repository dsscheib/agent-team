## Electronics (KiCad)

### Environment
- CAD: KiCad 10 on Linux; check with `python3 tools/kicad/doctor.py`
- Checks: `python3 tools/kicad/verify.py --project .` (ERC + DRC with schematic parity, reports in `reports/kicad/`)
- Schematics: edit native `.kicad_sch` files carefully, preserving UUIDs and references; validate through KiCad
- PCB: prefer the KiCad 10 IPC API with an open PCB Editor (enable the API server in Preferences > Plugins)
- IPC scripts: run with the kicad-python venv, `~/.local/share/kicad-python/bin/python` (override with `$KICAD_PYTHON`); `doctor.py` shows which one it found and whether the editor answers
- Part availability: `python3 tools/kicad/check_availability.py --bom bom.csv --boards 1` (or MPNs as arguments) checks stock and lifecycle at Digi-Key and Mouser, read-only, report in `reports/kicad/`. Credentials: `DIGIKEY_CLIENT_ID`, `DIGIKEY_CLIENT_SECRET`, `MOUSER_API_KEY` from the environment or `*.env` files in `$DISTRIBUTOR_API_DIR` (default `~/.config/distributor-api`); never commit them
- Requirements: `docs/electronics/design-requirements.md`; release gate: `docs/electronics/release-checklist.md`

### Project facts (fill in before design)
- Purpose:
- Supply voltage, source, protection and max current:
- Interfaces and speed:
- Board dimensions, layers and stackup:
- Components, acceptable substitutions and sourcing:
- Environmental limits and intended usage:
- Applicable safety / regulatory standards:
- Fabricator design rules and assembly requirements:

### Design workflow
1. Freeze written requirements for the design iteration.
2. Assign non-overlapping file owners and record assumptions.
3. Schematic and component work; ERC and netlist verification.
4. PCB work; DRC with schematic parity and human visual inspection.
5. Independent hardware audit and resolution log.
6. Stage manufacturing outputs only after explicit release authorization.

### Safety policy
Automated ERC and DRC are necessary checks, not a guarantee of electrical correctness. Do not manufacture or energize boards on AI assurance alone.
