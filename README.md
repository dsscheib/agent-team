# Project Agent Team Bootstrap

A **stack-neutral, opt-in** installer for project-local subagents in **Codex CLI, Claude Code, GitHub Copilot CLI, and Google Antigravity**. Besides software roles it has electronics roles for **KiCad 10** and mechanical/FDM roles for **FreeCAD 1.1**, each with optional helper scripts. No third-party Python dependencies. Tested with Python 3.11+.

## Quick start

From this extracted package:

```bash
python3 bootstrap.py --list
python3 bootstrap.py --project ~/Projects/my-project --platforms codex --preset core
python3 bootstrap.py --project ~/Projects/my-project --platforms codex --preset core --with-agents-md --apply
```

**Default is dry-run.** `--apply` makes changes. Target project directory must exist.

## Presets

- `core`: backend, frontend, integration-tester, auditor-advisor
- `web`: backend, frontend, frontend-tester, integration-tester, ux-designer
- `service`: backend, database, integration-tester, security, devops
- `full`: all 11 software roles
- `kicad-core`: circuit-designer, pcb-layout, component-engineer, electrical-verifier, hardware-auditor
- `kicad-full`: all 10 KiCad roles (adds pcb-manufacturing, firmware, hardware-bringup, power-electronics, signal-integrity)
- `freecad-core`: cad-engineer, mechanical-engineer, printability-engineer, cad-verifier, mechanical-auditor
- `freecad-full`: all 8 FreeCAD roles (adds assembly-engineer, electronics-enclosure, slicer-specialist)

`--preset` takes several presets, for example a board and its enclosure:

```bash
python3 bootstrap.py --project ~/Projects/my-board --platforms codex claude copilot antigravity \
  --preset kicad-core freecad-core --roles electronics-enclosure --with-tools --with-agents-md --apply
```

You can also pick roles without a preset:

```bash
python3 bootstrap.py --project ~/Projects/parts --platforms codex claude copilot antigravity \
  --roles backend database devops security auditor-advisor
```

Or combine them:

```bash
python3 bootstrap.py --project ~/Projects/parts --platforms codex \
  --preset core --roles database devops --apply
```

To generate initial project instructions, use `--with-agents-md` and edit the resulting `AGENTS.md`. When KiCad or FreeCAD roles are selected it includes an Electronics or Mechanical section with project facts to fill in. If `AGENTS.md` already exists (for example from another guidance package), only the domain sections it lacks are appended, matched by their heading; nothing else in it is changed, and reruns add nothing.

## KiCad and FreeCAD kits

`--with-tools` also installs the helper files of each hardware domain you selected. The agent instructions refer to these paths, so install them unless the project already has its own.

| Domain | Installed files |
|---|---|
| KiCad | `tools/kicad/doctor.py` (environment check), `tools/kicad/verify.py` (ERC on each root schematic named by a `.kicad_pro`, DRC with schematic parity; reports in `reports/kicad/`), `tools/kicad/fabrication_export.py` (Gerbers and drills to `reports/fab-staging/`, never orders), `tools/kicad/check_availability.py` (stock and lifecycle by MPN or BOM CSV through the Digi-Key and Mouser APIs, or with `--search KEYWORDS` a keyword search for candidate parts at both, filtered by `--in-stock`, `--active` and `--require TEXT`, report `search-*.csv`; and stock on hand in a Feeder inventory through its read-only parts API (`FEEDER_URL`, `FEEDER_API_KEY`), report in `reports/kicad/`; credentials from the environment or `*.env` files in `$DISTRIBUTOR_API_DIR`, default `~/.config/distributor-api`), `docs/electronics/design-requirements.md`, `docs/electronics/release-checklist.md` |
| FreeCAD | `tools/freecad/doctor.py` (finds FreeCAD/OrcaSlicer on PATH or as Flatpaks), `tools/freecad/inspect_model.py` (run with `FreeCADCmd`; shape validity, solids, volume, envelope to `reports/`), `tools/freecad/check_build_volume.py` (`--volume X Y Z`, default Ender-3 S1 Pro 220 x 220 x 270 mm), `scripts/create_parametric_plate.py` (example sketch + pad with STEP/STL export), `docs/mechanical/design-requirements.md`, `docs/mechanical/slicing.md` |

Kit files follow the same rules as agent files: created only when absent, identical files left alone, conflicts stop the install unless `--skip-existing`. The tools write generated reports under `reports/`, so `--with-tools` also adds `reports/`, plus KiCad's per-user and cache files (`*.kicad_prl`, `*.lck`, `fp-info-cache`, `*-backups/`), to `.gitignore` (creating it, or appending if the entry is missing) to keep check runs from dirtying the tree.

- KiCad schematics have no IPC editing API, so agents edit `.kicad_sch` files natively and validate with `kicad-cli`. Live PCB edits use the KiCad 10 IPC API with a running PCB Editor (enable the API server in Preferences > Plugins) through `kicad-python` (`import kipy`). Agents expect it in a venv at `~/.local/share/kicad-python`, or at the interpreter named by `$KICAD_PYTHON`; `tools/kicad/doctor.py` reports which one it found and whether the editor answers. ERC/DRC passing is not proof of electrical correctness or fab readiness.
- With the FreeCAD Flatpak, run scripts as `flatpak run --command=FreeCADCmd org.freecad.FreeCAD SCRIPT.py ARGS`, from inside the project: the sandbox has its own `/tmp`.
- No kit sends G-code, controls a printer, flashes firmware or places fabrication orders.

Tested 2026-11-13 with KiCad 10.0.8 (the `complex_hierarchy` demo) and the FreeCAD 1.1.4 Flatpak (example plate, inspection and build-volume check).

## Installation semantics

- Project-local files only; **never writes to your home directory**.
- Agent files are created only when absent. Identical existing files are left alone.
- A conflicting existing agent file stops the whole install; `--skip-existing` leaves that file untouched.
- Every file the installer writes is a new agent file. It never edits `.codex/config.toml` or any other existing file, so there is nothing to back up.
- The installer never changes approval settings, sandbox defaults, or primary orchestrator model.
- Agent definitions include recommended models, but **model availability and exact configuration support must be verified in your installed clients**.
- Read-only specialist tool restrictions are best-effort and do not secure credentials or environments accessible through other tools.

## Role kinds

Each role in `catalog/roles.json` has a `kind` that sets its tool access on every platform:

| Kind | Edits files | Runs commands | Roles |
|---|---|---|---|
| `implementer`, `tester` | Yes | Yes | backend, frontend, database, devops, documentation, integration-tester; circuit-designer, pcb-layout, component-engineer, firmware, hardware-bringup; cad-engineer, mechanical-engineer, assembly-engineer, electronics-enclosure, slicer-specialist |
| `inspector` | No | Yes (tests, browsers, profilers, ERC/DRC, FreeCADCmd, simulations) | frontend-tester, performance; electrical-verifier, pcb-manufacturing, power-electronics, signal-integrity; printability-engineer, cad-verifier |
| `reviewer` | No | No | security, ux-designer, auditor-advisor; hardware-auditor, mechanical-auditor |

Codex has no per-agent tool list, and `sandbox_mode` in an agent file does not override the parent session. Reviewers get `[features] shell_tool = false`, so they cannot run commands. Codex has no documented way to stop an agent editing files, so on Codex the no-edit limit for inspectors and reviewers rests on their instructions.

## Where files go

| Platform | Project-local files |
|---|---|
| Codex | `.codex/agents/<role>.toml` (standalone; Codex discovers it without a `config.toml` entry, in a trusted project) |
| Claude Code | `.claude/agents/<role>.md` |
| Copilot CLI | `.github/agents/<role>.agent.md` |
| Antigravity | `.agents/agents/<role>.md` |

## Models and constraints

- Codex defaults: Sol for most engineering (including component engineering, where footprint and pin errors force a board respin), Terra for UI/docs and slicer work, Astra for security, auditors, power electronics and signal integrity; reasoning medium/high/xhigh as appropriate.
- Claude defaults: Sonnet for implementation, Opus for the circuit designer (native schematic edits and design calculations), security, auditors, power electronics and signal integrity. These use documented family aliases, **not** pinned versions; modify per project if desired.
- Copilot defaults: inherit the CLI-selected model for most roles, pin `gpt-6-astra` with required policy for the roles that use Astra on Codex. Confirm your Copilot subscription supports it. Tools use the documented aliases `read`, `search`, `edit` and `execute`; Copilot silently ignores names it does not recognize.
- Antigravity defaults: `model: inherit` for every role. Subagent files accept only the tiers `inherit`, `flash_lite`, `flash` and `pro`, not model IDs, and in agy 1.5.8 both `pro` and `flash` ran on `gemini-3.8-flash-tiered` while `inherit` ran on the parent's model (tested 2026-11-13 against a `gemini-4-carbon-high` parent). Every role therefore runs on the session's model: start reviews and audits on the strongest Gemini 4 model you have, for example `agy --model gemini-4-carbon-high`, or pick it with `/model`. Tools are limited to the documented `view_file`, `grep_search`, `replace_file_content` and `run_command`, because an unknown tool name can hang an Antigravity subagent.
- For every platform, real tool permissions and model availability can vary by version, plan, or environment.

## Verification

1. Preview the installation; compare any existing files and role names.
2. Run with `--apply`, then restart the target tool.
3. Confirm the agent is discoverable and that requested models are supported.
4. Delegate a **read-only inspection task** first and check agent output and tool permissions.
5. Review the first implementation's diff and tests before permitting unattended work.

### Codex-specific caution

Codex loads project agents from `.codex/agents/` only after you trust the project. In an untrusted project it sees none of them, so trust the project before testing. No `[agents."<name>"]` entry in `config.toml` is needed. Older Codex releases used one with `config_file`, but Codex CLI 0.167.2 ignores its description and reads the agent file instead. Subagents are on by default; `agents.enabled = false` in your configuration turns them off.

The Codex model names in `catalog/roles.json` (`gpt-6.1-sol`, `gpt-6.1-terra`, `gpt-6-astra`) are in Codex CLI 0.167.2's built-in model list. Check yours with `codex debug models`, or clear `codex_model` to use the parent session's model.

## Customization

Edit `catalog/roles.json` to change descriptions, `domain` (`software`, `kicad` or `freecad`) or recommended model defaults, and `catalog/role_details.json` to change responsibilities. These are the canonical definitions used to generate all platforms. Shared principles come from `catalog/practices.md` for software roles and `domains/<domain>/practices.md` for the hardware domains. Each domain's `AGENTS.md` section and its `files/` tree (laid out at install paths) make up its kit. Printer and tool facts live in the kit's `AGENTS.md` section, not in the agents, so edit that section for a different printer. Rerunning won't overwrite previously installed agents: remove or manually update individual files intentionally.

Documentation references (agent file fields and tool names for Codex, Copilot CLI and Antigravity checked 2026-11-13):
- https://learn.chatgpt.com/docs/agent-configuration/subagents
- https://code.claude.com/docs/en/sub-agents
- https://docs.github.com/en/copilot/how-tos/copilot-cli/customize-copilot/create-custom-agents-for-cli
- https://antigravity.google/docs/subagents
