#!/usr/bin/env python3
"""Run KiCad 10 ERC and DRC (with schematic parity) without modifying the source design.

Each root-level *.kicad_pro names one project: ERC runs on its root schematic and DRC on its board.
Hierarchical subsheets are checked through the root schematic, never on their own, because a
subsheet checked alone reports every hierarchical connection as a false violation.
"""
import argparse
import shutil
import subprocess
import sys
from pathlib import Path


def checks(root):
    found = []
    for pro in sorted(root.glob('*.kicad_pro')):
        for typ, cmd, suffix in (('sch', 'erc', '.kicad_sch'), ('pcb', 'drc', '.kicad_pcb')):
            source = pro.with_suffix(suffix)
            if source.is_file():
                found.append((typ, cmd, source))
    return found


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--project', type=Path, default=Path('.'), help='Directory holding the .kicad_pro file(s)')
    ap.add_argument('--output', type=Path, default=None, help='Report directory (default: PROJECT/reports/kicad)')
    args = ap.parse_args(argv)
    root = args.project.expanduser().resolve()
    if not root.is_dir():
        ap.error('project directory does not exist')
    cli = shutil.which('kicad-cli')
    if not cli:
        print('ERROR: kicad-cli not found. Install KiCad 10.', file=sys.stderr)
        return 2
    result = subprocess.run([cli, 'version'], capture_output=True, text=True)
    print('KiCad:', result.stdout.strip() or result.stderr.strip())
    designs = checks(root)
    if not designs:
        print('No root-level .kicad_pro with a matching .kicad_sch or .kicad_pcb found', file=sys.stderr)
        return 2
    output = args.output.expanduser().resolve() if args.output else root / 'reports' / 'kicad'
    output.mkdir(parents=True, exist_ok=True)
    exitcode = 0
    for typ, cmd, source in designs:
        report = output / f'{source.stem}-{cmd}.rpt'
        command = [cli, typ, cmd, '--exit-code-violations', '--output', str(report)]
        if typ == 'pcb':
            command.append('--schematic-parity')
        command.append(str(source))
        print('RUN:', ' '.join(command), flush=True)
        rc = subprocess.run(command, cwd=root).returncode
        print(f'{source.name}: {cmd.upper()} exit={rc}, report={report}')
        if rc:
            exitcode = 1
    return exitcode


if __name__ == '__main__':
    sys.exit(main())
