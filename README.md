# Project Agent Team Bootstrap

A **stack-neutral, opt-in** installer for project-local subagents in **Codex CLI, Claude Code, GitHub Copilot CLI, and Google Antigravity**. No third-party Python dependencies. Tested with Python 3.11+.

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
- `full`: all 11 roles

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

To generate initial project instructions only if missing, use `--with-agents-md` and edit the resulting `AGENTS.md`. Existing project instructions are never overwritten.

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
| `implementer`, `tester` | Yes | Yes | backend, frontend, database, devops, documentation, integration-tester |
| `inspector` | No | Yes (tests, browsers, profilers) | frontend-tester, performance |
| `reviewer` | No | No | security, ux-designer, auditor-advisor |

Codex has no per-agent tool list, and `sandbox_mode` in an agent file does not override the parent session. Reviewers get `[features] shell_tool = false`, so they cannot run commands. Codex has no documented way to stop an agent editing files, so on Codex the no-edit limit for inspectors and reviewers rests on their instructions.

## Where files go

| Platform | Project-local files |
|---|---|
| Codex | `.codex/agents/<role>.toml` (standalone; Codex discovers it without a `config.toml` entry) |
| Claude Code | `.claude/agents/<role>.md` |
| Copilot CLI | `.github/agents/<role>.agent.md` |
| Antigravity | `.agents/agents/<role>.md` |

## Models and constraints

- Codex defaults: Sol for most engineering, Terra for UI/docs, Astra for security and auditor/advisor; reasoning medium/high/xhigh as appropriate.
- Claude defaults: Sonnet for implementation, Opus for security/audit. These use documented family aliases, **not** pinned versions; modify per project if desired.
- Copilot defaults: inherit the CLI-selected model for most roles, pin `gpt-6-astra` with required policy for security/audit. Confirm your Copilot subscription supports it. Tools use the documented aliases `read`, `search`, `edit` and `execute`; Copilot silently ignores names it does not recognize.
- Antigravity defaults: `model: inherit`. The subagent docs also accept `flash` and `pro`; set `antigravity_model` per role to pin a tier. `inherit` does not guarantee a distinct cheaper model. Tools are limited to the documented `view_file`, `grep_search`, `replace_file_content` and `run_command`, because an unknown tool name can hang an Antigravity subagent.
- For every platform, real tool permissions and model availability can vary by version, plan, or environment.

## Verification

1. Preview the installation; compare any existing files and role names.
2. Run with `--apply`, then restart the target tool.
3. Confirm the agent is discoverable and that requested models are supported.
4. Delegate a **read-only inspection task** first and check agent output and tool permissions.
5. Review the first implementation's diff and tests before permitting unattended work.

### Codex-specific caution

Subagents are on by default in current Codex releases; `agents.enabled = false` in your configuration turns them off. Test spawning a named agent before relying on it. The model names in `catalog/roles.json` are not checked against the Codex docs; clear `codex_model` to use the parent session's model.

## Customization

Edit `catalog/roles.json` to change descriptions or recommended model defaults, and `catalog/role_details.json` to change responsibilities. These are the canonical definitions used to generate all platforms. `catalog/practices.md` provides shared principles. Rerunning won't overwrite previously installed agents: remove or manually update individual files intentionally.

Documentation references (agent file fields and tool names for Codex, Copilot CLI and Antigravity checked 2026-11-13):
- https://learn.chatgpt.com/docs/agent-configuration/subagents
- https://code.claude.com/docs/en/sub-agents
- https://docs.github.com/en/copilot/how-tos/copilot-cli/customize-copilot/create-custom-agents-for-cli
- https://antigravity.google/docs/subagents
