#!/usr/bin/env python3
"""Compare bounding boxes from an inspect_model.py report with a printer's nominal build volume.

Checks axis-aligned dimensions only: not placement, brim, skirt, supports or printer offsets.
The default volume is a Creality Ender-3 S1 Pro (220 x 220 x 270 mm); pass --volume for another printer.
"""
import argparse
import itertools
import json
import sys
from pathlib import Path


def fits(dims, limits, margin):
    return all(v <= lim - 2 * margin for v, lim in zip(dims, limits))


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('report', type=Path, help='reports/PART-geometry.json from inspect_model.py')
    p.add_argument('--object', help='Feature name to check; recommended for multi-object documents')
    p.add_argument('--margin', type=float, default=5, help='Reserve per side, mm')
    p.add_argument('--volume', type=float, nargs=3, default=[220, 220, 270], metavar=('X', 'Y', 'Z'),
                   help='Nominal build volume, mm')
    a = p.parse_args(argv)
    d = json.loads(a.report.read_text())
    items = [x for x in d['shapes'] if x['object'] == a.object] if a.object else d['shapes']
    if not items:
        p.error('No matching geometry')
    worst = 0
    for x in items:
        dims = x['envelope_mm']
        as_is = fits(dims, a.volume, a.margin)
        rotated = any(fits(c, a.volume, a.margin) for c in itertools.permutations(dims))
        print(f"{x['object']}: {dims} mm | {'x'.join(f'{v:g}' for v in a.volume)} mm with {a.margin:g} mm margin: "
              f"{'possible' if rotated else 'too large'} | current orientation: {'fits' if as_is else 'does not fit'}")
        if not rotated:
            worst = 2
    return worst


if __name__ == '__main__':
    sys.exit(main())
