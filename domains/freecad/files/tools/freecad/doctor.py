#!/usr/bin/env python3
"""Report where FreeCAD and OrcaSlicer are installed. Read-only; needs no dependencies."""
import shutil
import subprocess

FLATPAKS = {'FreeCAD': 'org.freecad.FreeCAD', 'OrcaSlicer': 'com.orcaslicer.OrcaSlicer'}


def flatpak_version(app_id):
    p = subprocess.run(['flatpak', 'info', app_id], capture_output=True, text=True)
    if p.returncode:
        return None
    for line in p.stdout.splitlines():
        key, _, value = line.strip().partition(':')
        if key.strip() == 'Version':
            return value.strip()
    return 'installed'


def main():
    for app in ('FreeCADCmd', 'freecadcmd', 'FreeCAD', 'freecad', 'orca-slicer', 'flatpak'):
        print(f'{app:16} {shutil.which(app) or "not found on PATH"}')
    if shutil.which('flatpak'):
        for name, app_id in FLATPAKS.items():
            version = flatpak_version(app_id)
            print(f'{name + " Flatpak":16} {version or "not installed"}')
        if flatpak_version(FLATPAKS['FreeCAD']):
            print('Headless FreeCAD: flatpak run --command=FreeCADCmd org.freecad.FreeCAD SCRIPT.py [ARGS]')
            print('Note: the Flatpak sandbox has its own /tmp; keep scripts and files inside the project.')
    print('Tip: AppImage installs may not put FreeCADCmd on PATH; locate the bundled executable.')


if __name__ == '__main__':
    main()
