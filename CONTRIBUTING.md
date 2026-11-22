# Contributing

Thanks for checking out **Project Agent Team Bootstrap**.

## What belongs in a PR vs. your own fork

- **Pull requests are welcome for:**
  - Bug fixes in `bootstrap.py` or the KiCad/FreeCAD helper scripts
  - Platform frontmatter, tool-name, or CLI compatibility updates (backed by official docs or tested CLI versions)
  - Documentation fixes, clearer examples, and additional unit tests
- **Better kept in a local copy or fork:**
  - Personal model-tier defaults, role splits, or stack-specific rules—feel free to edit `catalog/roles.json`, `catalog/role_details.json`, and `catalog/practices.md` directly for your own workflows

## Expectations for pull requests

- **Stdlib only:** Keep `bootstrap.py`, the helper scripts, and tests free of third-party Python dependencies (Python 3.11+).
- **Safe, non-destructive installs:** Preserve dry-run-by-default behavior, write only inside `--project` (never touch `$HOME` or global tool configs), and never overwrite conflicting files without explicit intent.
- **Portable defaults:** Do not hardcode personal OS/distro names, specific printers, regional supplier restrictions, local paths, or credentials.
- **Verify platform changes:** When updating agent fields, tool names, or model behavior for Codex, Claude Code, Copilot CLI, or Antigravity, cite the CLI version or official documentation you verified against.
- **Run and add tests:** Run the full test suite and include tests for behavioral changes:

```bash
python3 -m unittest discover -s tests -v
```
