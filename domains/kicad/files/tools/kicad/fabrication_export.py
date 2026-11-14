#!/usr/bin/env python3
"""Stage Gerbers/drills only; does not approve a fabrication release."""
import argparse, subprocess, shutil, sys
from pathlib import Path
p=argparse.ArgumentParser()
p.add_argument('board',type=Path)
p.add_argument('--staging',type=Path,default=Path('reports/fab-staging'))
a=p.parse_args()
cli=shutil.which('kicad-cli')
if not cli:sys.exit('kicad-cli not found')
board=a.board.resolve(); stage=a.staging.resolve()
if not board.is_file():sys.exit('Board not found')
stage.mkdir(parents=True,exist_ok=True)
commands=[[cli,'pcb','export','gerbers','--output',str(stage),str(board)], [cli,'pcb','export','drill','--output',str(stage),str(board)]]
for command in commands:
    print('RUN', ' '.join(command),flush=True)
    subprocess.run(command,check=True)
print('STAGED ONLY: do not submit for manufacturing without human review')
