#!/usr/bin/env python3
"""Non-destructive project-local multi-tool agent team bootstrapper (stdlib only)."""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def _read(path):
    return path.read_text(encoding='utf-8')


ROLES = json.loads(_read(ROOT / 'catalog/roles.json'))
DETAILS = json.loads(_read(ROOT / 'catalog/role_details.json'))
PLATFORMS = ('codex', 'claude', 'copilot', 'antigravity')
ESCALATION_PLATFORMS = ('codex', 'claude', 'copilot')

# Each role belongs to one domain. A domain has shared operating principles and, except for
# software, a kit: an AGENTS.md section plus helper files laid out under files/ at their install paths.
DOMAIN_DIRS = {'software': None, 'kicad': ROOT / 'domains/kicad', 'freecad': ROOT / 'domains/freecad'}
PRACTICES = {d: _read(ROOT / 'catalog/practices.md' if path is None else path / 'practices.md').strip()
             for d, path in DOMAIN_DIRS.items()}


def domain_roles(domain):
    return [r for r, info in ROLES.items() if info['domain'] == domain]


PRESETS = {
    'core': ['backend', 'frontend', 'integration-tester', 'auditor-advisor'],
    'service': ['backend', 'database', 'integration-tester', 'security', 'devops'],
    'web': ['backend', 'frontend', 'frontend-tester', 'integration-tester', 'ux-designer'],
    'full': domain_roles('software'),
    'kicad-core': ['circuit-designer', 'pcb-layout', 'component-engineer', 'electrical-verifier', 'hardware-auditor'],
    'kicad-full': domain_roles('kicad'),
    'freecad-core': ['cad-engineer', 'mechanical-engineer', 'printability-engineer', 'cad-verifier', 'mechanical-auditor'],
    'freecad-full': domain_roles('freecad'),
}

# What each kind of role may do.
#   implementer, tester: edit files and run commands
#   inspector: run commands (tests, browsers, profilers) but not edit files
#   reviewer: static read-only inspection, no commands
KINDS = {
    'implementer': {'edit': True, 'run': True},
    'tester': {'edit': True, 'run': True},
    'inspector': {'edit': False, 'run': True},
    'reviewer': {'edit': False, 'run': False},
}
SCOPE = {
    'reviewer': 'You are a review-only specialist. Do not edit project files or run commands that change state.',
    'inspector': ('You may run commands to inspect, test and measure, but do not edit project files. '
                  'Keep any temporary output outside the repository or in disposable locations.'),
}
DEFAULT_SCOPE = 'Work only within your delegated scope and coordinate changes with the parent agent.'

STARTER_AGENTS_MD = '''# Project instructions

## Overview
Describe the purpose, audience, and key workflows of this repository.

## Tech stack
- Language(s): TODO
- Framework(s): TODO
- Data store(s): TODO
- Deployment target: TODO

## Development standards
- Follow existing conventions and read relevant documentation.
- Explain major architecture changes before implementing.
- Run appropriate project tests; report tests not run.
- Never deploy or modify production data without explicit permission.

## Test commands
- TODO: Add build, lint, unit and integration commands.

## Agent delegation
- Delegate bounded code and test tasks to the matching specialist by default (specialists run cheaper models); work directly only on docs, trivial edits, or when none fits. The parent retains integration responsibility.
- Avoid concurrent changes to overlapping files.
- Pass explicit file paths or diffs when delegating to read-only reviewers (Antigravity CLI reviewers have `read_file` only, without search or shell tools).
- Review the result of each delegated task before accepting it.
'''


def caps(role):
    info = ROLES[role]
    kind = info['kind']
    if kind not in KINDS:
        raise ValueError(f'Role {role!r} has unknown kind {kind!r}; expected one of {", ".join(KINDS)}')
    if info['domain'] not in DOMAIN_DIRS:
        raise ValueError(f'Role {role!r} has unknown domain {info["domain"]!r}')
    rule = info.get('escalation')
    if rule is not None:
        has_model = any(rule.get(f'{platform}_model') for platform in ESCALATION_PLATFORMS)
        if not rule.get('when') or not (has_model or rule.get('copilot_effort')):
            raise ValueError(f'Role {role!r} escalation needs "when" and a platform setting')
        for platform in ESCALATION_PLATFORMS:
            model = rule.get(f'{platform}_model')
            effort = rule.get(f'{platform}_effort')
            if (model or (platform == 'copilot' and effort)) and effort not in EFFORTS:
                raise ValueError(f'Role {role!r} escalation {platform}_effort must be one of {", ".join(EFFORTS)}')
        if copilot_required(role) and rule.get('copilot_model'):
            raise ValueError(f'Role {role!r} has a required Copilot model and can escalate only its effort')
        # Optional mid-tier first step, tried before the final setting on the same platform.
        for platform, setting in (rule.get('mid') or {}).items():
            name, _, field = platform.partition('_')
            if name not in ESCALATION_PLATFORMS or field not in ('model', 'effort'):
                raise ValueError(f'Role {role!r} escalation mid has unknown setting {platform!r}')
        for platform in ESCALATION_PLATFORMS:
            model = (rule.get('mid') or {}).get(f'{platform}_model')
            effort = (rule.get('mid') or {}).get(f'{platform}_effort')
            if not (model or effort):
                continue
            if not model or effort not in EFFORTS:
                raise ValueError(f'Role {role!r} escalation mid needs {platform}_model and a {platform}_effort '
                                 f'from {", ".join(EFFORTS)}')
            if platform == 'copilot' and copilot_required(role):
                raise ValueError(f'Role {role!r} has a required Copilot model and can escalate only its effort')
            if not rule.get(f'{platform}_model'):
                raise ValueError(f'Role {role!r} escalation mid {platform}_model needs a final {platform}_model')
    return KINDS[kind]


COPILOT_POLICIES = ('required', 'preferred')


def copilot_required(role):
    """True when the role pins a Copilot model that the dispatch may not replace."""
    info = ROLES[role]
    policy = info.get('copilot_model_policy', 'required')
    if policy not in COPILOT_POLICIES:
        raise ValueError(f'Role {role!r} copilot_model_policy must be one of {", ".join(COPILOT_POLICIES)}')
    return bool(info['copilot_model']) and policy == 'required'


def toml_string(value):
    return json.dumps(value, ensure_ascii=False)


def yaml_string(value):
    # A JSON string is a valid YAML double-quoted scalar, so ': ', '#' and quotes stay safe.
    return json.dumps(value, ensure_ascii=False)


def body(role):
    record = ROLES[role]
    scope = SCOPE.get(record['kind'], DEFAULT_SCOPE)
    return (f'You are the {record["title"]} specialist.\n\n'
            f'Core responsibilities: {DETAILS[role]}\n\n'
            f'{scope}\n\n{PRACTICES[record["domain"]]}\n')


def frontmatter(role, lines):
    head = [f'name: {yaml_string(role)}', f'description: {yaml_string(ROLES[role]["description"])}']
    return '---\n' + '\n'.join(head + lines) + '\n---\n\n' + body(role)


def codex_agent(role):
    # Codex discovers standalone .codex/agents/*.toml files; name, description and developer_instructions
    # are required. sandbox_mode in an agent file does not override the parent session, and there is no
    # per-agent edit restriction, so reviewers only lose the shell; the no-edit limit is in their instructions.
    r = ROLES[role]
    pieces = [f'name = {toml_string(role)}', f'description = {toml_string(r["description"])}']
    if r['codex_model']:
        pieces.append(f'model = {toml_string(r["codex_model"])}')
    if r['codex_effort']:
        pieces.append(f'model_reasoning_effort = {toml_string(r["codex_effort"])}')
    pieces.append(f'developer_instructions = {toml_string(body(role))}')
    if not caps(role)['run']:
        pieces += ['', '[features]', 'shell_tool = false']
    return '\n'.join(pieces) + '\n'


def claude_agent(role):
    c = caps(role)
    tools = ['Read', 'Grep', 'Glob'] + (['Edit', 'Write'] if c['edit'] else []) + (['Bash'] if c['run'] else [])
    return frontmatter(role, [f'model: {ROLES[role]["claude_model"]}', f'tools: {", ".join(tools)}'])


def copilot_agent(role):
    # Documented primary aliases: read, search (Grep/Glob), edit, execute. Unknown names are ignored silently.
    c = caps(role)
    tools = ['read', 'search'] + (['edit'] if c['edit'] else []) + (['execute'] if c['run'] else [])
    lines = []
    model = ROLES[role]['copilot_model']
    if model:
        # Copilot CLI 1.0.114 reads model-policy (it ignores modelPolicy and a models list). required ignores a
        # per-call model override; preferred accepts one. Under either policy an unavailable model falls back
        # to the session model with a warning.
        policy = 'required' if copilot_required(role) else 'preferred'
        lines += [f'model: {model}', f'model-policy: {policy}']
    lines += [f'tools: {json.dumps(tools)}', 'strict-tools-list: true', 'include-custom-instructions: true']
    return frontmatter(role, lines)


def antigravity_agent(role):
    # Only tool names Antigravity maps cleanly; an unknown name can hang older builds.
    c = caps(role)
    tools = (['view_file', 'grep_search']
             + (['write_to_file', 'replace_file_content'] if c['edit'] else [])
             + (['run_command'] if c['run'] else []))
    exec_policy = 'sandbox' if c['run'] else 'off'
    lines = [f'model: {ROLES[role]["antigravity_model"]}', 'mainAgent: false', 'subagent: true',
             f'commandExecutionPolicy: {exec_policy}', 'tools:'] + [f'  - {t}' for t in tools]
    return frontmatter(role, lines)


GENERATORS = {
    'codex': (lambda role: Path('.codex/agents') / f'{role}.toml', codex_agent),
    'claude': (lambda role: Path('.claude/agents') / f'{role}.md', claude_agent),
    'copilot': (lambda role: Path('.github/agents') / f'{role}.agent.md', copilot_agent),
    'antigravity': (lambda role: Path('.agents/agents') / f'{role}.md', antigravity_agent),
}


def selections(args):
    requested = {r for preset in args.preset or [] for r in PRESETS[preset]}
    requested.update(args.roles or [])
    unknown = sorted(requested - ROLES.keys())
    if unknown:
        raise ValueError(f'Unknown roles: {", ".join(unknown)}')
    if not requested:
        raise ValueError(f'Select --preset {"|".join(PRESETS)} and/or --roles role1 role2')
    return [r for r in ROLES if r in requested]


def kits(roles):
    """Domains with a kit among the selected roles, in catalog order."""
    used = {ROLES[r]['domain'] for r in roles}
    return [d for d, path in DOMAIN_DIRS.items() if path is not None and d in used]


DOMAIN_NAMES = {'software': 'Software', 'kicad': 'KiCad', 'freecad': 'FreeCAD'}
EFFORTS = ('low', 'medium', 'high', 'xhigh', 'max')

# Tool-neutral escalation policy for AGENTS.md. Each tool's settings and mechanics live in its own
# routed file (ESCALATION_DOC), so an agent reads only its own tool's details, and only when escalating.
ESCALATION_DOC = 'docs/agent-team/escalation-{}.md'
ESCALATION_POLICY = '''Specialists start at their configured or inherited model and effort; never escalate up front. Escalate a role listed below only when its specialist reports that the task needs escalation, or its result still fails review after one round of specific feedback. Escalate one step at a time: re-delegate at step 1 (mid-tier where the tool has one), and use step 2 only if step 1 also reports that it needs escalation or fails review. If the last step still falls short, or the role has no row, report it to the user. The "Escalate when" column describes the work that usually justifies escalation; it is not by itself a reason to escalate.

Before escalating, read the settings and mechanics for the tool you are running in: `docs/agent-team/escalation-<tool>.md`, where `<tool>` is `claude`, `codex`, `copilot` or `antigravity`. If your tool has no such file, report the need to the user instead. When escalation is warranted, re-delegate at the next step rather than accepting a reduced-confidence result.'''

TOOL_TITLES = {'codex': 'Codex', 'claude': 'Claude Code', 'copilot': 'Copilot CLI', 'antigravity': 'Antigravity'}
TOOL_NOTES = {
    'claude': "Set the subagent's `model` and `effort` to the listed values; they override the agent file. This is an explicit instruction to run that subagent at the listed effort.",
    'codex': 'Pass the listed values as the model and reasoning effort overrides when spawning the agent.',
    'copilot': 'Copilot CLI uses `model` and `reasoning_effort` on the `task` call. For "Agent model," pass only `reasoning_effort` and let the profile resolve the model. Select an explicit session model first: under Auto, every subagent runs on the session model, ignoring both overrides and the agent\'s own model, including a required one. Copilot does not report an unavailable override; the task silently runs on the session model. The same applies to an agent\'s preferred model such as `mai-code-2`, and a model override on the call replaces it. Before relying on a GPT-6.2 row, confirm the account offers that model; if it does not, use `claude-sonnet-5.5` at the listed effort for roles without a required model.',
    'antigravity': 'Antigravity subagents inherit the session model (`model: inherit`). For everyday work, run `Orchestrator (Neon)` as the primary (or `Orchestrator (Carbon)` for complex long-horizon architecture). For escalated tasks, switch to a frontier session model directly (`Gemini 4 Neon` High/XHigh or `Gemini 4 Carbon` High), or use Swarm (`/teamwork`) when you need to pin individual roles to exact model IDs (e.g., `gemini-4-neon-high`, `gemini-4-neon-xhigh`, `gemini-4-carbon-high`, or `claude-opus-5-5-high` for auditors alongside `gemini-4-hydrogen-high` or `gemini-pro-orchestrator-neon` for implementers). When delegating to a read-only reviewer on Antigravity CLI, pass explicit file paths or diffs because reviewers only receive `read_file`.',
}


def used_domains(roles):
    used = {ROLES[r]['domain'] for r in roles}
    return [d for d in DOMAIN_DIRS if d in used]


def escalation_rules(domain):
    return [(role, rule) for role in domain_roles(domain) if (rule := ROLES[role].get('escalation'))]


def escalation_setting(rule, platform):
    """One tool's escalation cell: `step 1` → `step 2`, a single step, or Default."""
    model = rule.get(f'{platform}_model')
    effort = rule.get(f'{platform}_effort')
    mid = rule.get('mid') or {}
    if model and mid.get(f'{platform}_model'):
        return f'`{mid[f"{platform}_model"]}`, {mid[f"{platform}_effort"]} → `{model}`, {effort}'
    if model:
        return f'`{model}`, {effort}'
    if platform == 'copilot' and effort:
        return f'Agent model, {effort}'
    return 'Default'


def escalation_section(domain):
    """Tool-neutral escalation rules for every role of a domain, the same whichever roles are installed."""
    rows = [f'| `{role}` | {rule["when"]} |' for role, rule in escalation_rules(domain)]
    if not rows:
        return ''
    return '\n'.join([f'## Model escalation: {DOMAIN_NAMES[domain]} roles', '', ESCALATION_POLICY, '',
                      '| Role | Escalate when |', '|---|---|'] + rows)


def escalation_doc_header(platform):
    title = TOOL_TITLES[platform]
    steps = ('' if platform == 'antigravity' else
             ' In the tables below, `A → B` means step 1 `A`, then step 2 `B`; one setting means one step. '
             '"Default" means the role\'s default is already suited, so it does not escalate in this tool; '
             'a role not installed in this project does not apply.')
    return (f'# Model escalation: {title}\n\n'
            f'How to apply the "Model escalation" rules in `AGENTS.md` when you run in {title}. Those rules decide '
            f'when to escalate; this file gives the settings.{steps}\n\n{TOOL_NOTES[platform]}\n')


def escalation_doc_table(domain, platform):
    rows = [f'| `{role}` | {escalation_setting(rule, platform)} |' for role, rule in escalation_rules(domain)]
    if platform == 'antigravity' or not rows:
        return ''
    title = TOOL_TITLES[platform]
    return '\n'.join([f'## {DOMAIN_NAMES[domain]} roles', '', f'| Role | {title} |', '|---|---|'] + rows) + '\n'


def escalation_doc_blocks(roles, platform):
    """[(marker line, block)] for one tool's escalation file: its header, then a table per used domain."""
    if not any(escalation_rules(d) for d in used_domains(roles)):
        return []
    blocks = [(f'# Model escalation: {TOOL_TITLES[platform]}', escalation_doc_header(platform))]
    for domain in used_domains(roles):
        if table := escalation_doc_table(domain, platform):
            blocks.append((f'## {DOMAIN_NAMES[domain]} roles', table))
    return blocks


def context_sections(roles):
    """Sections of AGENTS.md beyond the starter: domain kits, then model escalation rules."""
    kit_sections = [_read(DOMAIN_DIRS[d] / 'AGENTS.md').strip() for d in kits(roles)]
    return kit_sections + [s for s in map(escalation_section, used_domains(roles)) if s]


def agents_md(roles):
    head = STARTER_AGENTS_MD.strip() if 'software' in used_domains(roles) else '# Project instructions'
    return '\n\n'.join([head] + context_sections(roles)) + '\n'


# Claude Code reads CLAUDE.md, not AGENTS.md; this import gives it the same project instructions.
CLAUDE_MD = '@AGENTS.md\n'


# Generated output of the domain helper tools; kept out of git so check runs leave the tree clean.
GITIGNORE_BLOCK = ('# Generated reports from the KiCad/FreeCAD helper tools (regenerated on each run)\nreports/\n'
                   '# KiCad per-user and cache files, written by kicad-cli and the editors\n'
                   '*.kicad_prl\n*.lck\nfp-info-cache\n*-backups/\n')


def appendable_blocks(roles, context, tools=False, platforms=()):
    """Blocks that may be appended to an existing file: {path: [(marker line, block)]}.

    A block is appended only when its marker line is absent, so reruns change nothing.
    """
    blocks = {}
    if context:
        blocks[Path('AGENTS.md')] = [(s.splitlines()[0].strip(), s + '\n') for s in context_sections(roles)]
        if 'claude' in platforms:
            blocks[Path('CLAUDE.md')] = [('@AGENTS.md', CLAUDE_MD)]
        for platform in platforms:
            if doc := escalation_doc_blocks(roles, platform):
                blocks[Path(ESCALATION_DOC.format(platform))] = doc
    if tools and kits(roles):
        blocks[Path('.gitignore')] = [('reports/', GITIGNORE_BLOCK)]
    return blocks


# Other spellings of a marker line that already do its job.
MARKER_ALIASES = {'reports/': {'/reports/', 'reports', '/reports'}, '@AGENTS.md': {'@./AGENTS.md'}}


def missing_blocks(existing, blocks):
    present = {line.strip() for line in existing.splitlines()}
    for marker, aliases in MARKER_ALIASES.items():
        if present & aliases:
            present.add(marker)
    return [block for marker, block in blocks if marker not in present]


def planned_files(platforms, roles, context, tools=False):
    files = {}
    for platform in platforms:
        path_for, render = GENERATORS[platform]
        for role in roles:
            files[path_for(role)] = render(role)
    if context:
        files[Path('AGENTS.md')] = agents_md(roles)
        if 'claude' in platforms:
            files[Path('CLAUDE.md')] = CLAUDE_MD
        for platform in platforms:
            if doc := escalation_doc_blocks(roles, platform):
                files[Path(ESCALATION_DOC.format(platform))] = '\n'.join(block for _, block in doc)
    if tools:
        for domain in kits(roles):
            base = DOMAIN_DIRS[domain] / 'files'
            for src in sorted(f for f in base.rglob('*') if f.is_file() and '__pycache__' not in f.parts):
                files[src.relative_to(base)] = _read(src)
        if kits(roles):
            files[Path('.gitignore')] = GITIGNORE_BLOCK
    return files


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    p.add_argument('--project', type=Path, help='Existing project root (directory); required unless --list')
    p.add_argument('--platforms', nargs='+', choices=PLATFORMS, default=['codex'])
    p.add_argument('--preset', nargs='+', choices=PRESETS, help='One or more presets; roles are combined')
    p.add_argument('--roles', nargs='+', metavar='ROLE', help='Additional role identifiers')
    p.add_argument('--with-agents-md', action='store_true',
                   help='Create a starter AGENTS.md with KiCad/FreeCAD sections for those roles; '
                        'if AGENTS.md exists, append only the domain sections it lacks')
    p.add_argument('--with-tools', action='store_true',
                   help='Also install the helper scripts and docs of each KiCad/FreeCAD domain selected')
    p.add_argument('--apply', action='store_true', help='Actually install (default: preview/dry-run)')
    p.add_argument('--list', action='store_true', help='List roles and presets')
    p.add_argument('--skip-existing', action='store_true', help='Do not error on existing identical/different agent files; leave them unchanged')
    args = p.parse_args(argv)
    if args.list:
        print('Presets:')
        for name, members in PRESETS.items():
            print(f'  {name:13} {", ".join(members)}')
        print('Roles:')
        for name, info in ROLES.items():
            print(f'  {name:22} {info["domain"]:9} {info["kind"]:12} {info["title"]}')
        return 0
    if args.project is None:
        p.error('--project is required unless --list is given')
    project = args.project.expanduser().resolve()
    if not project.is_dir():
        p.error(f'Project directory does not exist: {project}')
    try:
        roles = selections(args)
        for role in roles:
            caps(role)
    except ValueError as ex:
        p.error(str(ex))
    platforms = list(dict.fromkeys(args.platforms))
    files = planned_files(platforms, roles, args.with_agents_md, args.with_tools)
    appendable = appendable_blocks(roles, args.with_agents_md, args.with_tools, platforms)
    changes = {}
    appends = {}
    conflicts = []
    for rel, content in files.items():
        target = project / rel
        if target.exists():
            if target.is_file() and _read(target) == content:
                print(f'UNCHANGED {rel}')
            elif target.is_file() and rel in appendable:
                missing = missing_blocks(_read(target), appendable[rel])
                if missing:
                    appends[rel] = missing
                else:
                    print(f'UNCHANGED {rel} (already has the sections)')
            elif args.skip_existing:
                print(f'SKIP     {rel} (exists)')
            else:
                conflicts.append(str(rel))
        else:
            changes[rel] = content
    if conflicts:
        print('Conflicts detected; nothing changed:', file=sys.stderr)
        for c in conflicts:
            print(f'  {c}', file=sys.stderr)
        print('Use --skip-existing to leave conflicting agent files untouched.', file=sys.stderr)
        return 2
    print(f'Project: {project}\nPlatforms: {", ".join(platforms)}\nRoles: {", ".join(roles)}')
    if kits(roles) and not args.with_tools:
        print(f'Note: add --with-tools for the {"/".join(kits(roles))} helper scripts the agents refer to.')
    if not args.with_agents_md:
        print('Note: add --with-agents-md for the model escalation rules in AGENTS.md.')
    for rel in changes:
        print(f'{"WRITE" if args.apply else "WOULD WRITE"} {rel}')
    for rel, blocks in appends.items():
        print(f'{"APPEND" if args.apply else "WOULD APPEND"} {rel} ({len(blocks)} section(s))')
    if not args.apply:
        print('\nDry-run only. Add --apply to install.')
        return 0
    for rel, content in changes.items():
        dest = project / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        # Exclusive create: never overwrite a file that appeared after planning.
        with dest.open('x', encoding='utf-8') as f:
            f.write(content)
        if content.startswith('#!'):
            dest.chmod(dest.stat().st_mode | 0o111)
    for rel, blocks in appends.items():
        dest = project / rel
        current = _read(dest)
        separator = '' if not current else ('\n' if current.endswith('\n') else '\n\n')
        with dest.open('a', encoding='utf-8') as f:
            f.write(separator + '\n'.join(blocks))
    print('\nInstalled. Restart your coding tool and verify agent discovery and model availability.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
