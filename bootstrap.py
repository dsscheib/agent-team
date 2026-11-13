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
COMMON = _read(ROOT / 'catalog/practices.md').strip()
PLATFORMS = ('codex', 'claude', 'copilot', 'antigravity')
PRESETS = {
    'core': ['backend', 'frontend', 'integration-tester', 'auditor-advisor'],
    'service': ['backend', 'database', 'integration-tester', 'security', 'devops'],
    'web': ['backend', 'frontend', 'frontend-tester', 'integration-tester', 'ux-designer'],
    'full': list(ROLES),
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
            f'{scope}\n\n{COMMON}\n')


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
    requested = set(PRESETS[args.preset]) if args.preset else set()
    requested.update(args.roles or [])
    unknown = sorted(requested - ROLES.keys())
    if unknown:
        raise ValueError(f'Unknown roles: {", ".join(unknown)}')
    if not requested:
        raise ValueError('Select --preset core|service|web|full and/or --roles role1 role2')
    return [r for r in ROLES if r in requested]


def planned_files(platforms, roles, context):
    files = {}
    for platform in platforms:
        path_for, render = GENERATORS[platform]
        for role in roles:
            files[path_for(role)] = render(role)
    if context:
        files[Path('AGENTS.md')] = STARTER_AGENTS_MD
    return files


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    p.add_argument('--project', type=Path, help='Existing project root (directory); required unless --list')
    p.add_argument('--platforms', nargs='+', choices=PLATFORMS, default=['codex'])
    p.add_argument('--preset', choices=PRESETS)
    p.add_argument('--roles', nargs='+', metavar='ROLE', help='Additional role identifiers')
    p.add_argument('--with-agents-md', action='store_true', help='Create a starter AGENTS.md only if absent')
    p.add_argument('--apply', action='store_true', help='Actually install (default: preview/dry-run)')
    p.add_argument('--list', action='store_true', help='List roles and presets')
    p.add_argument('--skip-existing', action='store_true', help='Do not error on existing identical/different agent files; leave them unchanged')
    args = p.parse_args(argv)
    if args.list:
        print('Presets:')
        for name, members in PRESETS.items():
            print(f'  {name:8} {", ".join(members)}')
        print('Roles:')
        for name, info in ROLES.items():
            print(f'  {name:20} {info["kind"]:12} {info["title"]}')
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
    files = planned_files(platforms, roles, args.with_agents_md)
    changes = {}
    conflicts = []
    for rel, content in files.items():
        target = project / rel
        if target.exists():
            if target.is_file() and _read(target) == content:
                print(f'UNCHANGED {rel}')
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
    for rel in changes:
        print(f'{"WRITE" if args.apply else "WOULD WRITE"} {rel}')
    if not args.apply:
        print('\nDry-run only. Add --apply to install.')
        return 0
    for rel, content in changes.items():
        dest = project / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        # Exclusive create: never overwrite a file that appeared after planning.
        with dest.open('x', encoding='utf-8') as f:
            f.write(content)
    print('\nInstalled. Restart your coding tool and verify agent discovery and model availability.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
