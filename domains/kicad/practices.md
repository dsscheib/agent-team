# KiCad 10 electronics operating principles

- Before acting, read `AGENTS.md`, `docs/electronics/design-requirements.md`, the design constraints and the existing KiCad project files. Do not assume a supply, interface, stackup or fabricator that is not written down.
- Keep every design file editable in KiCad 10. Schematics have no IPC editing API: change `.kicad_sch` as native S-expressions, preserving UUIDs, sheet paths and library references, and confirm KiCad still loads the file. Boards are best changed through the KiCad 10 IPC API against a running PCB Editor, using the kicad-python interpreter that `tools/kicad/doctor.py` reports (by default `~/.local/share/kicad-python/bin/python`).
- Work only within your delegated scope. One role owns a file at a time; coordinate overlapping edits through the parent agent. Before a significant edit, make sure there is a git commit or backup to return to.
- Use datasheets and measured facts, never invented values. Cite the datasheet or source for each value that matters.
- `tools/kicad/verify.py` runs ERC on each root schematic and DRC with schematic parity on each board, writing reports to `reports/kicad/`. A clean ERC/DRC is necessary, not proof of electrical correctness, safety or fab readiness.
- No fabrication release, ordering, purchasing, flashing, energized testing or destructive operation without explicit human approval. Stage manufacturing outputs only in `reports/fab-staging/`.
- If the task needs more depth than your model and effort are suited for, for example a case listed for your role under Model escalation in `AGENTS.md`, stop and tell the parent agent it needs escalation, and why, instead of finishing at reduced confidence.
- Report files changed, checks actually run with their results, unverified assumptions, and the handoff to the lead.
