#!/usr/bin/env python3
"""Stage KiCad Gerbers and drill files for review; never approves or submits a fabrication release."""
import argparse
import shutil
import subprocess
import sys
from pathlib import Path


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    ap.add_argument('board', type=Path, help='Path to the .kicad_pcb file')
    ap.add_argument('--staging', type=Path, default=Path('reports/fab-staging'),
                    help='Directory where Gerbers and drill files are staged')
    args = ap.parse_args(argv)
    cli = shutil.which('kicad-cli')
    if not cli:
        print('ERROR: kicad-cli not found. Install KiCad 10.', file=sys.stderr)
        return 2
    board = args.board.expanduser().resolve()
    if not board.is_file():
        print(f'ERROR: board not found: {board}', file=sys.stderr)
        return 2
    stage = args.staging.expanduser().resolve()
    stage.mkdir(parents=True, exist_ok=True)
    commands = [
        [cli, 'pcb', 'export', 'gerbers', '--output', str(stage), str(board)],
        [cli, 'pcb', 'export', 'drill', '--output', str(stage), str(board)],
    ]
    for command in commands:
        print('RUN:', ' '.join(command), flush=True)
        subprocess.run(command, check=True)
    print('STAGED ONLY: do not submit for manufacturing without human review')
    return 0


if __name__ == '__main__':
    sys.exit(main())
