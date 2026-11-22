# Project Agent Team Bootstrap

A **stack-neutral, opt-in** installer for project-local subagents in **Codex CLI, Claude Code, GitHub Copilot CLI, and Google Antigravity**. Besides software roles it has electronics roles for **KiCad 10** and mechanical/FDM roles for **FreeCAD 1.1**, each with optional helper scripts. No third-party Python dependencies. Tested with Python 3.11+.

## Quick start

Clone and run from this repository:

```bash
git clone https://github.com/dsscheib/agent-team.git && cd agent-team
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

To generate initial project instructions, use `--with-agents-md` and edit the resulting `AGENTS.md`. When KiCad or FreeCAD roles are selected it includes an Electronics or Mechanical section with project facts to fill in. If `AGENTS.md` already exists (for example from another guidance package), only the domain sections it lacks are appended, matched by their heading; nothing else in it is changed, and reruns add nothing. It also gets a model escalation section for each domain selected (see [Model escalation](#model-escalation)). With `--platforms claude`, a `CLAUDE.md` containing `@AGENTS.md` is created, or that line appended to an existing one, because Claude Code reads `CLAUDE.md` rather than `AGENTS.md`.

## KiCad and FreeCAD kits

`--with-tools` also installs the helper files of each hardware domain you selected. The agent instructions refer to these paths, so install them unless the project already has its own.

| Domain | Installed files |
|---|---|
| KiCad | `tools/kicad/doctor.py` (environment check), `tools/kicad/verify.py` (ERC on each root schematic named by a `.kicad_pro`, DRC with schematic parity; reports in `reports/kicad/`), `tools/kicad/fabrication_export.py` (Gerbers and drills to `reports/fab-staging/`, never orders), `tools/kicad/layout_metrics.py` (reads a saved `.kicad_pcb` without KiCad running: outline and courtyard extent, track length and vias, and for named nets length, layers, reference-plane coverage, pair skew, decoupling distances and loop areas; report in `reports/kicad/`), `tools/kicad/check_availability.py` (stock and lifecycle by MPN or BOM CSV through the Digi-Key and Mouser APIs, or with `--search KEYWORDS` a keyword search for candidate parts at both, filtered by `--in-stock`, `--active` and `--require TEXT`, report `search-*.csv`; and optionally stock on hand in a [Feeder](https://github.com/dsscheib/feeder) inventory through its read-only parts API (`FEEDER_URL`, `FEEDER_API_KEY`), report in `reports/kicad/`; credentials and optional Digi-Key locale/currency overrides (`DIGIKEY_LOCALE_SITE`, `DIGIKEY_LOCALE_LANGUAGE`, `DIGIKEY_LOCALE_CURRENCY`, defaulting to `US`/`en`/`USD`) come from the environment or `*.env` files in `$DISTRIBUTOR_API_DIR`, default `~/.config/distributor-api`), `docs/electronics/design-requirements.md`, `docs/electronics/release-checklist.md` |
| FreeCAD | `tools/freecad/doctor.py` (finds FreeCAD/OrcaSlicer on PATH or as Flatpaks), `tools/freecad/inspect_model.py` (run with `FreeCADCmd`; shape validity, solids, volume, envelope to `reports/`), `tools/freecad/check_build_volume.py` (requires `--volume X Y Z` in mm), `scripts/create_parametric_plate.py` (example sketch + pad with STEP/STL export), `docs/mechanical/design-requirements.md`, `docs/mechanical/slicing.md` |

Kit files follow the same rules as agent files: created only when absent, identical files left alone, conflicts stop the install unless `--skip-existing`. The tools write generated reports under `reports/`, so `--with-tools` also adds `reports/`, plus KiCad's per-user and cache files (`*.kicad_prl`, `*.lck`, `fp-info-cache`, `*-backups/`), to `.gitignore` (creating it, or appending if the entry is missing) to keep check runs from dirtying the tree.

- KiCad schematics have no IPC editing API, so agents edit `.kicad_sch` files natively and validate with `kicad-cli`. Live PCB edits use the KiCad 10 IPC API with a running PCB Editor (enable the API server in Preferences > Plugins) through `kicad-python` (`import kipy`). Agents expect it in a venv at `~/.local/share/kicad-python`, or at the interpreter named by `$KICAD_PYTHON`; `tools/kicad/doctor.py` reports which one it found and whether the editor answers. ERC/DRC passing is not proof of electrical correctness or fab readiness.
- With the FreeCAD Flatpak, run scripts as `flatpak run --command=FreeCADCmd org.freecad.FreeCAD SCRIPT.py ARGS`, from inside the project: the sandbox has its own `/tmp`.
- No kit sends G-code, controls a printer, flashes firmware or places fabrication orders.

Tested 2026-11-13 with KiCad 10.0.8 (the `complex_hierarchy` demo) and the FreeCAD 1.1.4 Flatpak (example plate, inspection and build-volume check). See [docs/pcb-layout-model-test.md](docs/pcb-layout-model-test.md) for an optional evaluation protocol for benchmarking PCB layout models with `layout_metrics.py`.

## Installation semantics

- Project-local files only; **never writes to your home directory**.
- Agent files are created only when absent. Identical existing files are left alone.
- A conflicting existing agent file stops the whole install; `--skip-existing` leaves that file untouched.
- Apart from appending missing sections to `AGENTS.md`, `CLAUDE.md` and `.gitignore`, the installer only creates new files. It never edits `.codex/config.toml` or any other existing file, so there is nothing to back up.
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

- Codex defaults use GPT-6.2 Sol for most engineering (including component engineering, where footprint and pin errors force a board respin), GPT-6.1 Terra for UI, documentation and slicer work, and GPT-6.2 Astra for security, auditors, power electronics and signal integrity. Reasoning effort ranges from Medium to Extra High.
- Claude defaults: Sonnet for implementation, Opus for the circuit designer (native schematic edits and design calculations), component engineering and electrical verification (where a pin, footprint or rating error forces a board respin), security, auditors, power electronics and signal integrity. These use documented family aliases, **not** pinned versions; modify per project if desired.
- Most Copilot roles inherit the CLI-selected model. Frontend, frontend testing and UX review prefer `mai-code-2`, and documentation prefers `mai-code-2-flash`, the same light tier that runs on GPT-6.1 Terra in Codex. These roles set `model-policy: preferred`, so an escalation can override the model. Security, auditors, power electronics and signal integrity pin `gpt-6.2-astra` with `model-policy: required`, so Copilot ignores a model override for them. Under either policy, if the account lacks the model, Copilot warns and runs the agent on the session model. Tools use the documented aliases `read`, `search`, `edit` and `execute`. Copilot silently ignores names it does not recognize. [Copilot CLI agent settings](https://docs.github.com/en/copilot/reference/copilot-cli-reference/cli-command-reference#custom-agent-frontmatter-fields)
- Antigravity defaults: `model: inherit` for every role. Subagent files accept only the tiers `inherit`, `flash_lite`, `flash` and `pro`, not model IDs, and in agy 1.5.8 both `pro` and `flash` ran on `gemini-3.8-flash-tiered` while `inherit` ran on the parent's model (tested 2026-11-13 against a `gemini-4-carbon-high` parent). Every role therefore runs on the session's model. Edit roles receive `write_to_file` and `replace_file_content` (mapped to `write_file` and `edit_file` in Antigravity CLI, verified live 2026-11-19), inspectors receive `run_command` with `commandExecutionPolicy: sandbox`, and read-only reviewers set `commandExecutionPolicy: off` without `run_command`. `find_by_name` is excluded because unknown tool names can hang older Antigravity builds and Antigravity CLI does not expose separate search tools (`grep_search` / `find_by_name`) to subagents—pass explicit file paths or diffs when delegating to a CLI reviewer so it can inspect them with `read_file`. See [Antigravity primary agent and Swarm escalation](#antigravity-primary-agent-and-swarm-escalation) below.
- For every platform, real tool permissions and model availability can vary by version, plan, or environment.

### Codex primary agent

These are task-based starting points, not benchmark results for your project. The installer leaves the primary model and effort unchanged. Select them in your Codex session with `/model` or configure them separately in the target project's `.codex/config.toml`, for example:

```toml
model = "gpt-6.2-sol"
model_reasoning_effort = "high"
```

In the tables below, Sol means `gpt-6.2-sol`, Terra means `gpt-6.1-terra`, and Astra means `gpt-6.2-astra`.

| Project / preset | Recommended primary | Adjust for the task |
|---|---|---|
| General software / `core` | Sol High | Medium for small, well-defined changes; Astra High for difficult architecture or elusive failures. |
| Web application / `web` | Sol High | Terra Medium for sessions dominated by styling, visual iteration and content. |
| Backend, API, database / `service` | Sol High | Astra High for distributed consistency, major migrations or complex security architecture. |
| Broad software / `full` | Sol High | Astra High for major redesigns across subsystems. |
| Ordinary PCB / `kicad-core` | Sol High | Astra High when novel circuit design and unresolved engineering decisions dominate. |
| Complex electronics / `kicad-full` | Astra High | Sol High for implementation after architecture and constraints are settled. |
| Ordinary CAD and FDM / `freecad-core` | Sol High | Medium for simple dimensional edits and familiar parametric parts. |
| Complex assemblies / `freecad-full` | Astra High | Sol High for straightforward modeling and enclosure implementation. |
| Combined PCB, firmware and enclosure | Astra High | Extra High (`xhigh`) for major cross-domain design reviews or especially difficult tradeoffs. |

Installing a `full` preset alone does not require Astra: choose based on the actual work. Astra High is also a reasonable quality-first primary when usage and latency matter less. Reserve Max for exceptional reasoning problems and Ultra for work that benefits from its subagent delegation.

### Codex specialist effort and escalation

The catalog sets integration testing and PCB manufacturing to High because their full responsibilities include failure-mode design and fabrication readiness. CAD verification defaults to Medium for its established inspection scripts. Other defaults retain the existing model split. The three auditors retain Astra Extra High for deep, comprehensive audits; use High for routine reviews or consultations.

Generated agent files have one fixed model and effort. The upward overrides below are also written to `AGENTS.md` as [escalation rules](#model-escalation) for the primary to apply when delegating; the downward ones (cheaper settings for routine work) stay manual, by editing the agent file or overriding the model when delegating.

| Specialist | Task-specific override |
|---|---|
| `frontend` | Sol High for complex state management, asynchronous behavior and application logic; retain Terra Medium for visual/component work. |
| `devops` | Sol Medium for small, familiar CI edits. |
| `integration-tester` | Sol Medium when running established suites; retain High for test design involving concurrency, recovery, authorization or migrations. |
| `ux-designer` | Terra Medium for straightforward visual feedback. |
| `auditor-advisor`, `hardware-auditor`, `mechanical-auditor` | Astra High for incremental reviews and routine consultations; retain Extra High for comprehensive audits. |
| `circuit-designer` | Astra High for novel analog, mixed-signal or protection design. |
| `pcb-layout` | Astra High for difficult electrical/layout tradeoffs. |
| `pcb-manufacturing` | Sol Medium for export staging and established checklists; retain High for final fabrication/assembly readiness. |
| `hardware-bringup` | Astra High for ambiguous fault diagnosis spanning several subsystems. |
| `power-electronics` | Astra Extra High for difficult stability, transient and interacting protection problems. |
| `signal-integrity` | Astra Extra High for difficult return-path, stackup and coupling tradeoffs. |
| `mechanical-engineer` | Astra High for coupled load, material, thermal and tolerance analysis. |
| `electronics-enclosure` | Astra High when thermal, electrical and mechanical requirements conflict. |
| `printability-engineer` | Sol High for load-bearing parts, anisotropy and tight fits. |
| `slicer-specialist` | Sol Medium for substantial scripting or export automation; retain Terra Medium for visual slicer workflows. |
| `cad-verifier` | Sol High for unexplained geometry or export failures. |

Keep component engineering and electrical verification on Sol High: their responsibilities include pinouts, footprints, ratings and engineering validation beyond automated rule checks. Backend, database, performance, firmware, CAD and assembly implementation also retain Sol High. Frontend testing and documentation retain Terra Medium.

Higher effort takes more time and tokens; validate these choices on representative tasks and adjust based on observed results. See the [official model and reasoning-effort guidance](https://learn.chatgpt.com/docs/models). Model availability is client- and account-dependent (explicit Terra selection requires Codex CLI 0.159.0+ and account access). Confirm available models in your target session with `codex debug models` before relying on Terra roles.

### Claude Code primary agent

As with Codex, these are task-based starting points, and the installer leaves the primary model and effort unchanged. Select them when starting a session, for example `claude --model opus --effort high`, or with `/model` inside a session. `--effort` accepts `low`, `medium`, `high`, `xhigh` and `max`.

In the tables below, Opus, Sonnet and Fable are the Claude Code aliases `opus`, `sonnet` and `fable`, which resolve to the latest model in each family (Claude Opus 5.5, Sonnet 5.5 and Fable 5.2 as of 2026-11-16). Fable is the most capable and costs more than Opus. Its gains above High are uneven, so move it to Extra High only where you see a measured improvement.

| Project / preset | Recommended primary | Adjust for the task |
|---|---|---|
| General software / `core` | Opus High | Medium for small, well-defined changes; Fable High for difficult architecture or elusive failures. |
| Web application / `web` | Opus High | Sonnet Medium for sessions dominated by styling, visual iteration and content. |
| Backend, API, database / `service` | Opus High | Fable High for distributed consistency, major migrations or complex security architecture. |
| Broad software / `full` | Opus High | Fable High for major redesigns across subsystems. |
| Ordinary PCB / `kicad-core` | Opus High | Fable High when novel circuit design and unresolved engineering decisions dominate. |
| Complex electronics / `kicad-full` | Fable High | Opus High for implementation after architecture and constraints are settled. |
| Ordinary CAD and FDM / `freecad-core` | Opus High | Medium for simple dimensional edits and familiar parametric parts. |
| Complex assemblies / `freecad-full` | Fable High | Opus High for straightforward modeling and enclosure implementation. |
| Combined PCB, firmware and enclosure | Fable High | Extra High (`xhigh`) for major cross-domain design reviews or especially difficult tradeoffs. |

Installing a `full` preset alone does not require Fable: choose based on the actual work. Reserve Max for exceptional reasoning problems.

### Claude Code specialist overrides

Generated Claude agent files set `model` (Sonnet or Opus, from `claude_model` in `catalog/roles.json`) but no `effort`. To fix a specialist's effort permanently, add an `effort:` line (`low` to `max`) to the frontmatter of its `.claude/agents/<role>.md` file. Every override below is an escalation, written to `AGENTS.md` as an [escalation rule](#model-escalation).

| Specialist | Default | Task-specific override |
|---|---|---|
| `frontend` | Sonnet | Opus High for complex state management, asynchronous behavior and application logic; retain Sonnet for visual/component work. |
| `devops` | Sonnet | Medium effort for small, familiar CI edits. |
| `integration-tester` | Sonnet | Opus High for test design involving concurrency, recovery, authorization or migrations; retain Sonnet for running established suites. |
| `security` | Opus | Fable High for complex security architecture or threat models spanning several services. |
| `auditor-advisor`, `hardware-auditor`, `mechanical-auditor` | Opus | Opus Extra High for comprehensive audits; the default for incremental reviews and routine consultations. |
| `circuit-designer` | Opus | Fable High for novel analog, mixed-signal or protection design. |
| `pcb-layout` | Sonnet | Opus High for difficult electrical/layout tradeoffs. |
| `pcb-manufacturing` | Sonnet | Opus High for final fabrication/assembly readiness; retain Sonnet for export staging and established checklists. |
| `hardware-bringup` | Sonnet | Opus High for ambiguous fault diagnosis spanning several subsystems. |
| `power-electronics` | Opus | Opus Extra High for difficult stability, transient and interacting protection problems. |
| `signal-integrity` | Opus | Opus Extra High for difficult return-path, stackup and coupling tradeoffs. |
| `mechanical-engineer` | Sonnet | Opus High for coupled load, material, thermal and tolerance analysis. |
| `electronics-enclosure` | Sonnet | Opus High when thermal, electrical and mechanical requirements conflict. |
| `printability-engineer` | Sonnet | Opus High for load-bearing parts, anisotropy and tight fits. |
| `cad-verifier` | Sonnet | Opus High for unexplained geometry or export failures. |

Component engineering and electrical verification run on Opus by default, like their Codex counterparts on Sol High. Backend, database, performance, firmware, CAD, assembly and slicer work, frontend testing, UX review and documentation retain Sonnet. Validate these choices on representative tasks and adjust based on observed results. See the [Claude Code subagent documentation](https://code.claude.com/docs/en/sub-agents) for supported frontmatter fields.

### Copilot CLI specialist overrides

The Copilot column in the generated escalation tables gives the model and reasoning effort for each task. These recommendations are based on the roles' responsibilities and the models' published strengths. [GitHub Copilot model comparison](https://docs.github.com/en/copilot/reference/ai-models/model-comparison) · [OpenAI model guide](https://learn.chatgpt.com/docs/models)

- **GPT-6.2 Sol** at High for complex frontend logic and unexplained CAD failures, and Medium for slicer scripting and export automation.
- **GPT-6.2 Astra** at High for PCB layout tradeoffs, board bring-up and conflicting enclosure requirements. These tasks can require several rounds of diagnosis and verification.
- **Claude Opus 5.5** at High for failure-mode test design, novel circuit design, final fabrication review, coupled mechanical analysis and difficult printability decisions.
- **Agent model** at Extra High (`xhigh`) for complex security reviews, comprehensive audits and difficult power or signal-integrity work. The profile selects its required Astra model, and the dispatch sets the effort.

MAI Code 2 and MAI Code 2 Flash are defaults only, never escalation targets. Microsoft positions MAI Code 2 for everyday coding at near-GPT-6.1 Sol quality and much lower cost, with strong UI results, but not for very long-horizon work. Flash is aimed at high-volume work: explanations, targeted edits and routine fixes. On SWE Atlas codebase Q&A, which documentation depends on, Flash scores about the same as MAI Code 2. Security and auditor roles keep Astra: the model card rates MAI alignment below GPT-6, and it is served behind cybersecurity classifiers that may refuse exploit-related review. Hardware roles keep the session model because the card says less common languages and frameworks have not been extensively evaluated. [MAI Code 2 model card](https://microsoft.ai/pdf/MAI-Code-2-And-MAI-Code-2-Flash-Model-Card.pdf)

The Gemini 4 models in Copilot (`gemini-4-neon`, `gemini-4-carbon`, `gemini-4-hydrogen`) are not assigned to any role yet; Gemini 4 Argon is removed on 2026-12-14. Hydrogen costs several times as much as MAI Code 2 for the same light work. Neon is the strongest candidate for escalation, but its model card and safety report are not yet published, Copilot Pro does not include it, and an unavailable override silently runs on the session model. Carbon is close to Neon in quality but slower, and its price doubles on 2026-12-01. [GitHub Copilot changelog](https://github.blog/changelog/)

For one task, set `model` and `reasoning_effort` on the Copilot `task` call. For a standing per-agent override, use `/subagents`. Select an explicit session model before delegating: under Auto, every subagent runs on the session model and ignores both per-call overrides and the agent's `model`, even with `model-policy: required`. An override the account cannot use does not fail; Copilot silently runs the task on the session model. Confirm that your account offers the recommended GPT-6.2 and MAI models, and for roles without a required model use Claude Opus 5.5 at the listed effort if a GPT-6.2 model is missing. [Copilot CLI dispatch rules](https://docs.github.com/en/copilot/reference/copilot-cli-reference/cli-command-reference#custom-agent-frontmatter-fields)

### Antigravity primary agent and Swarm escalation

Because `.agents/agents/*.md` subagents use `model: inherit` and cannot pin exact model IDs, model selection on Antigravity happens at the session level or through Swarm:

- **Everyday primary (Orchestrator):** Use **`Orchestrator (Neon)`** as your default session model, or **`Orchestrator (Carbon)`** when a session needs deeper planning for complex, long-horizon architecture. Neon replaces Argon as the everyday planner (faster and stronger on coding tasks), while Carbon is reserved for the hardest planning work. Orchestrator pairs the planner with **Gemini 4 Hydrogen** for edits and build/test loops automatically, avoiding older Flash tiers without burning frontier quota on every edit.
- **Deep reviews and audits:** Start the session on a frontier model directly — **Gemini 4 Neon (High or XHigh)** for fast deep reviews or **Gemini 4 Carbon (High)** for exhaustive long-horizon audits (via `/model` or `--model`) — before invoking `auditor-advisor`, `security`, `hardware-auditor`, or `mechanical-auditor`.
- **Exact per-role model pinning (Swarm):** When a task splits into parallel workstreams or needs independent cross-model verification, use Swarm (`/teamwork`), which accepts exact model IDs per worker (for example, `gemini-4-hydrogen-high` or `gemini-pro-orchestrator-neon` for implementation workers and `gemini-4-neon-high`, `gemini-4-neon-xhigh`, `gemini-4-carbon-high`, or `claude-opus-5-5-high` for auditors/verifiers). Avoid Swarm for small single-track changes because each worker runs its own conversation and increases quota usage.
- **CLI reviewer scope:** In Antigravity CLI, read-only reviewers (`commandExecutionPolicy: off`, no `run_command`) receive only `read_file` for repository inspection (no separate grep/glob tool). Have the parent agent supply the exact file paths or diff to inspect in the delegation prompt.
- **Reloading agent files:** Antigravity reloads `.agents/agents/*.md` on the next user turn (as well as on restart).

### Model escalation

The specialist tables above only help if the primary agent knows them, so escalation is installed in three layers:

1. **Defaults.** Each specialist starts with its configured or inherited model and reasoning effort.
2. **Rules for the primary.** `--with-agents-md` writes a `## Model escalation: <domain> roles` section to `AGENTS.md` for each selected domain. Each row gives a task trigger and the settings to use in Codex, Claude Code and Copilot CLI. The primary applies the settings on the delegation call. On Antigravity, run an Orchestrator primary for everyday work and either switch to a stronger frontier session model or pin exact models per role in Swarm (`/teamwork`) for escalated tasks. Each section covers the whole domain so it also applies when you install more roles later.
3. **Specialists ask.** Every role's shared practices tell it to stop and report that a task needs escalation, and why, rather than finish at reduced confidence. The escalation section tells the primary to delegate such a task again at the listed setting.

The primary still decides whether a task matches a rule, so review delegations on important work.

## Verification

1. Preview the installation; compare any existing files and role names.
2. Run with `--apply`, then restart the target tool.
3. Confirm the agent is discoverable and that requested models are supported.
4. Delegate a **read-only inspection task** first and check agent output and tool permissions.
5. Review the first implementation's diff and tests before permitting unattended work.

### Codex-specific caution

Codex loads project agents from `.codex/agents/` only after you trust the project. In an untrusted project it sees none of them, so trust the project before testing. No `[agents."<name>"]` entry in `config.toml` is needed. Older Codex releases used one with `config_file`, but Codex CLI 0.167.2 ignores its description and reads the agent file instead. Subagents are on by default; `agents.enabled = false` in your configuration turns them off.

Check the models available to your Codex client with `codex debug models`. To use the parent session's model for a role, set its `codex_model` to an empty string in the catalog before generating the agent.

## Customization

Edit `catalog/roles.json` to change descriptions, `domain` (`software`, `kicad` or `freecad`), recommended model defaults or `escalation` rules, and `catalog/role_details.json` to change responsibilities. Each escalation rule defines `when` and can set `codex_model`/`codex_effort`, `claude_model`/`claude_effort` or `copilot_model`/`copilot_effort`. `copilot_model` is required by default; add `"copilot_model_policy": "preferred"` so the role falls back to the session model and its escalation rule can set `copilot_model`. For a required Copilot model, set only `copilot_effort` in the escalation rule. These are the canonical definitions used to generate all platforms. Shared principles come from `catalog/practices.md` for software roles and `domains/<domain>/practices.md` for the hardware domains. Each domain's `AGENTS.md` section and its `files/` tree (laid out at install paths) make up its kit. Printer, OS, sourcing, and tool facts live in the kit's `AGENTS.md` section and `docs/` templates, not in the agents, so fill those in for your environment. Rerunning won't overwrite previously installed agents: remove or manually update individual files intentionally.

### Updating existing installations

To refresh `AGENTS.md` escalation sections in an existing project after updating this repository, run the same presets with `--with-agents-md --apply` in a temporary directory, then merge the updated escalation sections from its `AGENTS.md` into your project's copy.

Documentation references (agent file fields and tool names for Codex, Copilot CLI and Antigravity checked 2026-11-13):
- https://learn.chatgpt.com/docs/agent-configuration/subagents
- https://code.claude.com/docs/en/sub-agents
- https://docs.github.com/en/copilot/how-tos/copilot-cli/customize-copilot/create-custom-agents-for-cli
- https://antigravity.google/docs/subagents

## Running tests

```bash
python3 -m unittest discover -s tests -v
```

Requires Python 3.11+ (stdlib only, no third-party dependencies).

## License

MIT — see [LICENSE](LICENSE).
