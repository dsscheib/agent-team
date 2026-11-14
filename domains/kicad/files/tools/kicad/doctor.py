#!/usr/bin/env python3
"""Inspect KiCad 10 automation prerequisites, no modifications."""
import shutil, subprocess, importlib.util, sys
from pathlib import Path
print('KiCad CLI:', shutil.which('kicad-cli') or 'NOT FOUND')
if shutil.which('kicad-cli'):
    r=subprocess.run(['kicad-cli','version'],capture_output=True,text=True)
    v=(r.stdout or r.stderr).strip(); print('Version:',v)
    if not v.startswith('10.') : print('WARNING: scripts are targeted to KiCad 10')
print('Python IPC library kipy:', 'available' if importlib.util.find_spec('kipy') else 'not installed')
print('KiCad 10 IPC API: PCB Editor must be open with API server enabled (Preferences > Plugins).')
print('KiCad 10 schematic editing: native-file workflow; no schematic IPC editing API.')
print('Git:', shutil.which('git') or 'not found')
