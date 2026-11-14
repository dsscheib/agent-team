#!/usr/bin/env python3
"""Inspect KiCad 10 automation prerequisites. Read-only: changes no files or settings.

kicad-python (import kipy) is looked for in $KICAD_PYTHON, then in the venv
~/.local/share/kicad-python, then in the Python running this script.
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path

DEFAULT_VENV_PYTHON = Path.home() / '.local/share/kicad-python/bin/python'

# Runs inside the candidate interpreter: report the kipy version and whether a PCB Editor answers.
PROBE = '''
import importlib.metadata as m
try:
    import kipy
except ImportError:
    print("missing"); raise SystemExit
print(m.version("kicad-python"))
try:
    print(kipy.KiCad(timeout_ms=2000).get_version())
except Exception as e:
    print("unreachable: " + type(e).__name__)
'''


def kipy_interpreters():
    seen = []
    for candidate in (os.environ.get('KICAD_PYTHON'), str(DEFAULT_VENV_PYTHON), sys.executable):
        if candidate and Path(candidate).is_file() and candidate not in seen:
            seen.append(candidate)
    return seen


def probe(python):
    try:
        r = subprocess.run([python, '-I', '-c', PROBE], capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.TimeoutExpired) as e:
        return None, f'probe failed: {type(e).__name__}'
    lines = r.stdout.strip().splitlines()
    if r.returncode or not lines or lines[0] == 'missing':
        return None, None
    return lines[0], lines[1] if len(lines) > 1 else 'unknown'


def main():
    cli = shutil.which('kicad-cli')
    print('KiCad CLI:', cli or 'NOT FOUND')
    if cli:
        r = subprocess.run([cli, 'version'], capture_output=True, text=True)
        v = (r.stdout or r.stderr).strip()
        print('Version:', v)
        if not v.startswith('10.'):
            print('WARNING: these tools target KiCad 10')
    found = False
    for python in kipy_interpreters():
        version, status = probe(python)
        if version:
            found = True
            print(f'kicad-python {version}: {python}')
            print(f'  PCB Editor API: {status}')
            break
    if found:
        print('Run IPC scripts with that interpreter. "unreachable" means no PCB Editor is open '
              'or its API server is off (Preferences > Plugins).')
    else:
        print('kicad-python (kipy): not installed. Install it in a venv, e.g. '
              f'uv venv {DEFAULT_VENV_PYTHON.parent.parent} && '
              f'uv pip install --python {DEFAULT_VENV_PYTHON} kicad-python')
    print('Schematics: native .kicad_sch editing; KiCad 10 has no schematic IPC editing API.')
    print('Git:', shutil.which('git') or 'not found')


if __name__ == '__main__':
    main()
