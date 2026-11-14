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
- Delegate bounded tasks to relevant specialists; the parent retains integration responsibility.
- Avoid concurrent changes to overlapping files.
- Review the result of each delegated task before accepting it.
'''


def caps(role):
    kind = ROLES[role]['kind']
    if kind not in KINDS:
        raise ValueError(f'Role {role!r} has unknown kind {kind!r}; expected one of {", ".join(KINDS)}')
    if ROLES[role]['domain'] not in DOMAIN_DIRS:
        raise ValueError(f'Role {role!r} has unknown domain {ROLES[role]["domain"]!r}')
    return KINDS[kind]


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
    if ROLES[role]['copilot_model']:
        lines += [f'model: {ROLES[role]["copilot_model"]}', 'model-policy: required']
    lines += [f'tools: {json.dumps(tools)}', 'strict-tools-list: true', 'include-custom-instructions: true']
    return frontmatter(role, lines)


def antigravity_agent(role):
    # Only tool names Antigravity documents; an unknown name can hang the subagent.
    c = caps(role)
    tools = ['view_file', 'grep_search'] + (['replace_file_content'] if c['edit'] else []) + (['run_command'] if c['run'] else [])
    lines = [f'model: {ROLES[role]["antigravity_model"]}', 'mainAgent: false', 'subagent: true',
             'commandExecutionPolicy: sandbox', 'tools:'] + [f'  - {t}' for t in tools]
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


def agents_md(roles):
    sections = [_read(DOMAIN_DIRS[d] / 'AGENTS.md').strip() for d in kits(roles)]
    if any(ROLES[r]['domain'] == 'software' for r in roles) or not sections:
        return '\n\n'.join([STARTER_AGENTS_MD.strip()] + sections) + '\n'
    return '# Project instructions\n\n' + '\n\n'.join(sections) + '\n'


# Generated output of the domain helper tools; kept out of git so check runs leave the tree clean.
GITIGNORE_BLOCK = ('# Generated reports from the KiCad/FreeCAD helper tools (regenerated on each run)\nreports/\n'
                   '# KiCad per-user and cache files, written by kicad-cli and the editors\n'
                   '*.kicad_prl\n*.lck\nfp-info-cache\n*-backups/\n')


def appendable_blocks(roles, context, tools=False):
    """Blocks that may be appended to an existing file: {path: [(marker line, block)]}.

    A block is appended only when its marker line is absent, so reruns change nothing.
    """
    blocks = {}
    if context:
        blocks[Path('AGENTS.md')] = [(s.splitlines()[0].strip(), s)
                                     for s in (_read(DOMAIN_DIRS[d] / 'AGENTS.md').strip() + '\n' for d in kits(roles))]
    if tools and kits(roles):
        blocks[Path('.gitignore')] = [('reports/', GITIGNORE_BLOCK)]
    return blocks


def missing_blocks(existing, blocks):
    present = {line.strip() for line in existing.splitlines()}
    if 'reports/' in [m for m, _ in blocks] and present & {'/reports/', 'reports', '/reports'}:
        present.add('reports/')
    return [block for marker, block in blocks if marker not in present]


def planned_files(platforms, roles, context, tools=False):
    files = {}
    for platform in platforms:
        path_for, render = GENERATORS[platform]
        for role in roles:
            files[path_for(role)] = render(role)
    if context:
        files[Path('AGENTS.md')] = agents_md(roles)
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
    appendable = appendable_blocks(roles, args.with_agents_md, args.with_tools)
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
