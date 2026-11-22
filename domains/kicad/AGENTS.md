## Electronics (KiCad)

### Environment
- CAD: KiCad 10 (update OS and version for your machine); check with `python3 tools/kicad/doctor.py`
- Checks: `python3 tools/kicad/verify.py --project .` (ERC + DRC with schematic parity, reports in `reports/kicad/`)
- Schematics: edit native `.kicad_sch` files carefully, preserving UUIDs and references; validate through KiCad
- PCB: prefer the KiCad 10 IPC API with an open PCB Editor (enable the API server in Preferences > Plugins)
- IPC scripts: run with the kicad-python venv, `~/.local/share/kicad-python/bin/python` (override with `$KICAD_PYTHON`); `doctor.py` shows which one it found and whether the editor answers
- Part availability: `python3 tools/kicad/check_availability.py --bom bom.csv --boards 1` (or MPNs as arguments) checks stock and lifecycle at Digi-Key and Mouser, and optionally what is already on hand (available quantity and storage location) in a [Feeder](https://github.com/dsscheib/feeder) parts inventory, read-only, report in `reports/kicad/`. To find candidates, `--search "keywords"` (with optional `--in-stock`, `--active`, `--require TEXT` and `--limit N`) searches Digi-Key and Mouser by keyword and writes `search-*.csv` with descriptions, categories, parameters, stock, lifecycle, price and datasheets; treat results as leads to verify against datasheets. Credentials: `DIGIKEY_CLIENT_ID`, `DIGIKEY_CLIENT_SECRET`, `MOUSER_API_KEY`, and optionally `FEEDER_URL` and `FEEDER_API_KEY` (a read-only key from `feeder api-key create`), plus optional Digi-Key locale overrides `DIGIKEY_LOCALE_SITE`, `DIGIKEY_LOCALE_LANGUAGE`, and `DIGIKEY_LOCALE_CURRENCY` (defaulting to `US`/`en`/`USD`), from the environment or `*.env` files in `$DISTRIBUTOR_API_DIR` (default `~/.config/distributor-api`); never commit them
- Layout metrics: `python3 tools/kicad/layout_metrics.py BOARD.kicad_pcb --net NET ... --pair P N --decoupling IC:CAP,CAP --loop REF.PAD,...` reads the saved board (no running KiCad needed) and reports outline and courtyard extent, track length, vias, critical-net length, layers and reference-plane coverage, pair skew, decoupling distances and loop areas, report in `reports/kicad/`. Refill zones and save before measuring coverage
- Requirements: `docs/electronics/design-requirements.md`; release gate: `docs/electronics/release-checklist.md`

### Project facts (fill in before design)
- Purpose:
- Supply voltage, source, protection and max current:
- Interfaces and speed:
- Board dimensions, layers and stackup:
- Components, approved distributors/region and acceptable substitutions:
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
