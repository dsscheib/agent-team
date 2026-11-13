#!/usr/bin/env python3
"""Non-destructive project-local multi-tool agent team bootstrapper (stdlib only)."""
import argparse
import json
import re
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ROLES = json.loads((ROOT / 'catalog/roles.json').read_text())
DETAILS = json.loads((ROOT / 'catalog/role_details.json').read_text())
COMMON = (ROOT / 'catalog/practices.md').read_text().strip()
PLATFORMS = ('codex', 'claude', 'copilot', 'antigravity')
PRESETS = {
    'core': ['backend', 'frontend', 'integration-tester', 'auditor-advisor'],
    'service': ['backend', 'database', 'integration-tester', 'security', 'devops'],
    'web': ['backend', 'frontend', 'frontend-tester', 'integration-tester', 'ux-designer'],
    'full': list(ROLES),
}


def toml_string(value):
    return json.dumps(value, ensure_ascii=False)


def body(role):
    record = ROLES[role]
    scope = 'You are a review-only specialist. Do not edit project files or run commands that change state.' if record['kind'] == 'reviewer' else 'Work only within your delegated scope and coordinate changes with the parent agent.'
    return (f'You are the {record["title"]} specialist.\n\n'
            f'Core responsibilities: {DETAILS[role]}\n\n'
            f'{scope}\n\n{COMMON}\n')


def codex_paths(project, role):
    rel = Path('.codex/agents') / f'{role}.toml'
    return rel, Path('.codex/config.toml')


def codex_agent(role):
    r = ROLES[role]
    pieces = [f'model = {toml_string(r["codex_model"])}',
              f'model_reasoning_effort = {toml_string(r["codex_effort"])}']
    if r['kind'] == 'reviewer':
        pieces.append('sandbox_mode = "read-only"')
    pieces.append(f'developer_instructions = {toml_string(body(role))}')
    return '\n'.join(pieces) + '\n'


def codex_registration(role):
    r = ROLES[role]
    return (f'\n[agents.{toml_string(role)}]\n'
            f'description = {toml_string(r["description"])}\n'
            f'config_file = {toml_string("./agents/" + role + ".toml")}\n')


def claude_agent(role):
    r = ROLES[role]
    # Restrict source edits for review-only roles. No Bash means static inspection only.
    tools = 'Read, Grep, Glob' if r['kind'] == 'reviewer' else 'Read, Grep, Glob, Edit, Write, Bash'
    return (f'---\nname: {role}\ndescription: {r["description"]}\n'
            f'model: {r["claude_model"]}\ntools: {tools}\n---\n\n{body(role)}')


def copilot_agent(role):
    r = ROLES[role]
    tools = '["read", "grep", "glob"]' if r['kind'] == 'reviewer' else '["read", "grep", "glob", "edit", "execute"]'
    metadata = f'model: {r["copilot_model"]}\nmodel-policy: required\n' if r['copilot_model'] else ''
    return (f'---\nname: {role}\ndescription: {r["description"]}\n'
            f'{metadata}tools: {tools}\nstrict-tools-list: true\n'
            f'include-custom-instructions: true\n---\n\n{body(role)}')


def antigravity_agent(role):
    r = ROLES[role]
    # Known-documented tool identifiers only; no shell tool for reviewer roles.
    tools = ['view_file', 'grep_search', 'find_by_name']
    if r['kind'] != 'reviewer':
        tools += ['replace_file_content', 'run_command']
    return (f'---\nname: {role}\ndescription: {r["description"]}\n'
            f'model: {r["antigravity_model"]}\nmainAgent: false\nsubagent: true\n'
            'commandExecutionPolicy: sandbox\ntools:\n' + ''.join(f'  - {t}\n' for t in tools)
            + f'---\n\n{body(role)}')


def selections(args):
    requested = set(PRESETS[args.preset]) if args.preset else set()
    requested.update(args.roles or [])
    unknown = sorted(requested - ROLES.keys())
    if unknown:
        raise ValueError(f'Unknown roles: {", ".join(unknown)}')
    if not requested:
        raise ValueError('Select --preset core|service|web|full and/or --roles role1 role2')
    return [r for r in ROLES if r in requested]


def planned_files(project, platforms, roles, context):
    files = {}
    for platform in platforms:
        for role in roles:
            if platform == 'codex':
                rel, _ = codex_paths(project, role)
                content = codex_agent(role)
            elif platform == 'claude':
                rel, content = Path('.claude/agents') / f'{role}.md', claude_agent(role)
            elif platform == 'copilot':
                rel, content = Path('.github/agents') / f'{role}.agent.md', copilot_agent(role)
            else:
                rel, content = Path('.agents/agents') / f'{role}.md', antigravity_agent(role)
            files[rel] = content
    if context:
        files[Path('AGENTS.md')] = '''# Project instructions\n\n## Overview\nDescribe the purpose, audience, and key workflows of this repository.\n\n## Tech stack\n- Language(s): TODO\n- Framework(s): TODO\n- Data store(s): TODO\n- Deployment target: TODO\n\n## Development standards\n- Follow existing conventions and read relevant documentation.\n- Explain major architecture changes before implementing.\n- Run appropriate project tests; report tests not run.\n- Never deploy or modify production data without explicit permission.\n\n## Test commands\n- TODO: Add build, lint, unit and integration commands.\n\n## Agent delegation\n- Delegate bounded tasks to relevant specialists; the parent retains integration responsibility.\n- Avoid concurrent changes to overlapping files.\n- Review the result of each delegated task before accepting it.\n'''
    return files


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    p.add_argument('--project', type=Path, required=True, help='Existing project root (directory)')
    p.add_argument('--platforms', nargs='+', choices=PLATFORMS, default=['codex'])
    p.add_argument('--preset', choices=PRESETS)
    p.add_argument('--roles', nargs='+', metavar='ROLE', help='Additional role identifiers')
    p.add_argument('--with-agents-md', action='store_true', help='Create a starter AGENTS.md only if absent')
    p.add_argument('--apply', action='store_true', help='Actually install (default: preview/dry-run)')
    p.add_argument('--list', action='store_true', help='List roles and presets')
    p.add_argument('--skip-existing', action='store_true', help='Do not error on existing identical/different agent files; leave them unchanged')
    args = p.parse_args(argv)
    if args.list:
        print('Presets:', ', '.join(PRESETS))
        for name, info in ROLES.items():
            print(f'  {name:20} {info["title"]}')
        return 0
    project = args.project.expanduser().resolve()
    if not project.is_dir():
        p.error(f'Project directory does not exist: {project}')
    try:
        roles = selections(args)
    except ValueError as ex:
        p.error(str(ex))
    platforms = list(dict.fromkeys(args.platforms))
    files = planned_files(project, platforms, roles, args.with_agents_md)
    changes = {}
    conflicts = []
    for rel, content in files.items():
        target = project / rel
        if target.exists():
            if target.is_file() and target.read_text() == content:
                print(f'UNCHANGED {rel}')
            elif args.skip_existing:
                print(f'SKIP     {rel} (exists)')
            else:
                conflicts.append(str(rel))
        else:
            changes[rel] = content
    # Append to existing Codex config; never overwrite it.
    if 'codex' in platforms:
        rel = Path('.codex/config.toml')
        target = project / rel
        existing = target.read_text() if target.exists() else ''
        try:
            parsed = tomllib.loads(existing)
        except tomllib.TOMLDecodeError as e:
            conflicts.append(f'{rel} (invalid existing TOML: {e})')
            parsed = {}
        existing_agents = parsed.get('agents', {})
        to_append = []
        for role in roles:
            if role in existing_agents:
                # Preserve existing registration without modification, even when it points elsewhere.
                print(f'KEEP     existing registration: agents.{role}')
            else:
                to_append.append(codex_registration(role))
        if to_append:
            merged = existing.rstrip() + '\n' + ''.join(to_append)
            try:
                tomllib.loads(merged)
            except tomllib.TOMLDecodeError as e:
                conflicts.append(f'{rel} (merged TOML invalid: {e})')
            changes[rel] = merged
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
    # Validate all data before writes. All agent files are non-overwriting.
    for rel, content in changes.items():
        if rel.suffix == '.toml':
            tomllib.loads(content)
    for rel, content in changes.items():
        dest = project / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists():
            if rel == Path('.codex/config.toml'):
                backup = dest.with_name('config.toml.pre-agent-bootstrap.bak')
                if backup.exists():
                    raise RuntimeError(f'Backup already exists, refusing to replace: {backup}')
                backup.write_bytes(dest.read_bytes())
                print(f'BACKUP   {backup.relative_to(project)}')
            else:
                raise RuntimeError(f'Unexpected existing file: {dest}')
        # Atomic replacement for config file; new files created exclusively.
        if rel == Path('.codex/config.toml'):
            temp = dest.with_name('config.toml.agent-bootstrap.tmp')
            if temp.exists():
                raise RuntimeError(f'Temp path already exists: {temp}')
            temp.write_text(content)
            temp.replace(dest)
        else:
            with dest.open('x', encoding='utf-8') as f:
                f.write(content)
    print('\nInstalled. Restart your coding tool and verify agent discovery and model availability.')
    return 0

if __name__ == '__main__':
    sys.exit(main())
