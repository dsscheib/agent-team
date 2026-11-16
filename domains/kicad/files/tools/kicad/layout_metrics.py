#!/usr/bin/env python3
"""Measure a KiCad board's layout from the saved .kicad_pcb file, without KiCad running.

Reports the board outline and courtyard extent, footprints left outside the outline, track
length per layer and via count, and for each net named with --net (and each net of a --pair):
track length, vias, copper layers and how much of the track runs over a filled zone on an
adjacent copper layer (its reference plane). With --decoupling it reports the distance from each
capacitor to the nearest IC pin it shares a supply net with, and with --loop the area enclosed by
a chain of pads, such as a switching converter's hot loop.

These are geometric proxies for comparing layouts, not signal-integrity analysis. Lengths are
total track copper on the net, including branches; distances are pad centre to pad centre; zone
coverage needs zones filled before the board was saved. The report is written to
reports/kicad/<board>-layout-metrics.json beside the board's project.

Example:
  python3 tools/kicad/layout_metrics.py board.kicad_pcb --net /XI /XO \\
      --pair /USB_DP /USB_DN --decoupling U1:C1,C2,C3 --loop U2.1,C8.1,C8.2,U2.4
"""
import argparse
import difflib
import json
import math
import re
import sys
from pathlib import Path

SAMPLE_STEP_MM = 0.2
ARC_PIECES = 16


class Q(str):
    """A quoted string from the file, as opposed to a bare atom such as a number."""


TOKEN = re.compile(r'\(|\)|"(?:\\.|[^"\\])*"|[^\s()"]+')


def parse(text):
    stack = [[]]
    for match in TOKEN.finditer(text):
        token = match.group()
        if token == '(':
            stack.append([])
        elif token == ')':
            if len(stack) == 1:
                raise ValueError('unbalanced parentheses')
            node = stack.pop()
            stack[-1].append(node)
        elif token[0] == '"':
            stack[-1].append(Q(re.sub(r'\\(.)', r'\1', token[1:-1])))
        else:
            stack[-1].append(token)
    if len(stack) != 1 or not stack[0] or not isinstance(stack[0][0], list):
        raise ValueError('not an S-expression file')
    return stack[0][0]


def children(node, name):
    return [c for c in node[1:] if isinstance(c, list) and c and c[0] == name]


def first(node, name):
    found = children(node, name)
    return found[0] if found else None


def point(node):
    return float(node[1]), float(node[2])


def pts(node):
    holder = first(node, 'pts')
    return [point(xy) for xy in children(holder, 'xy')] if holder else []


def dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def arc_points(s, m, e):
    """Points along the circular arc from s through m to e, and its length."""
    (x1, y1), (x2, y2), (x3, y3) = s, m, e
    d = 2 * (x1 * (y2 - y3) + x2 * (y3 - y1) + x3 * (y1 - y2))
    if abs(d) < 1e-12:
        return [s, m, e], dist(s, m) + dist(m, e)
    ux = ((x1**2 + y1**2) * (y2 - y3) + (x2**2 + y2**2) * (y3 - y1) + (x3**2 + y3**2) * (y1 - y2)) / d
    uy = ((x1**2 + y1**2) * (x3 - x2) + (x2**2 + y2**2) * (x1 - x3) + (x3**2 + y3**2) * (x2 - x1)) / d
    r = math.hypot(x1 - ux, y1 - uy)
    a1, a2, a3 = (math.atan2(y - uy, x - ux) for x, y in (s, m, e))
    to_end, to_mid = (a3 - a1) % (2 * math.pi), (a2 - a1) % (2 * math.pi)
    sweep = to_end if to_mid <= to_end else to_end - 2 * math.pi
    points = [(ux + r * math.cos(a1 + sweep * i / ARC_PIECES), uy + r * math.sin(a1 + sweep * i / ARC_PIECES))
              for i in range(ARC_PIECES + 1)]
    return points, r * abs(sweep)


def circle_points(center, edge):
    r = dist(center, edge)
    return [(center[0] + r * math.cos(2 * math.pi * i / ARC_PIECES), center[1] + r * math.sin(2 * math.pi * i / ARC_PIECES))
            for i in range(ARC_PIECES)]


def shape_points(node):
    """Outline points of a graphic shape (line, arc, rect, circle or polygon), in its own coordinates."""
    kind = node[0][3:]  # gr_line -> line, fp_line -> line
    if kind == 'line':
        return [point(first(node, 'start')), point(first(node, 'end'))]
    if kind == 'arc':
        return arc_points(point(first(node, 'start')), point(first(node, 'mid')), point(first(node, 'end')))[0]
    if kind == 'rect':
        (x1, y1), (x2, y2) = point(first(node, 'start')), point(first(node, 'end'))
        return [(x1, y1), (x2, y1), (x2, y2), (x1, y2)]
    if kind == 'circle':
        return circle_points(point(first(node, 'center')), point(first(node, 'end')))
    if kind == 'poly':
        return pts(node)
    return []


def layer_of(node):
    layer = first(node, 'layer')
    return layer[1] if layer else None


def copper_order(name):
    if name == 'F.Cu':
        return -1
    if name == 'B.Cu':
        return 10**6
    match = re.fullmatch(r'In(\d+)\.Cu', name)
    return int(match.group(1)) if match else 10**5


def bbox(points):
    xs, ys = [p[0] for p in points], [p[1] for p in points]
    return min(xs), min(ys), max(xs), max(ys)


def inside(p, polygon):
    """Even-odd point-in-polygon test; KiCad stores filled zones as single fractured outlines."""
    x, y = p
    result = False
    j = len(polygon) - 1
    for i in range(len(polygon)):
        (xi, yi), (xj, yj) = polygon[i], polygon[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            result = not result
        j = i
    return result


def polygon_area(points):
    return abs(sum(points[i][0] * points[i - 1][1] - points[i - 1][0] * points[i][1] for i in range(len(points)))) / 2


class Board:
    def __init__(self, text):
        root = parse(text)
        if root[0] != 'kicad_pcb':
            raise ValueError('not a .kicad_pcb file')
        version = first(root, 'version')
        self.version = version[1] if version else ''
        # Before KiCad 10 nets are numbered and declared at the top; KiCad 10 files name them directly.
        self.net_names = {n[1]: n[2] for n in children(root, 'net') if len(n) > 2}
        layers = first(root, 'layers')
        names = [entry[1] for entry in layers[1:] if isinstance(entry, list) and len(entry) > 1] if layers else []
        self.copper = sorted((n for n in names if n.endswith('.Cu')), key=copper_order)
        self.tracks = []  # (layer, net, points, length)
        for seg in children(root, 'segment'):
            a, b = point(first(seg, 'start')), point(first(seg, 'end'))
            self.tracks.append((layer_of(seg), self.net(seg), [a, b], dist(a, b)))
        for arc in children(root, 'arc'):
            points, length = arc_points(point(first(arc, 'start')), point(first(arc, 'mid')), point(first(arc, 'end')))
            self.tracks.append((layer_of(arc), self.net(arc), points, length))
        self.vias = [(point(first(v, 'at')), self.net(v)) for v in children(root, 'via')]
        self.outline = [p for shape in root[1:] if isinstance(shape, list) and shape[0].startswith('gr_')
                        and layer_of(shape) == 'Edge.Cuts' for p in shape_points(shape)]
        self.footprints = [self.footprint(fp) for fp in children(root, 'footprint')]
        for fp in self.footprints:
            self.outline += fp['edge']
        self.zones = {}  # copper layer -> [(net, polygon, bbox)]
        for zone in children(root, 'zone'):
            net = self.net(zone) or (first(zone, 'net_name') or [None, ''])[1]
            for filled in children(zone, 'filled_polygon'):
                polygon = pts(filled)
                if len(polygon) >= 3:
                    self.zones.setdefault(layer_of(filled), []).append((net, polygon, bbox(polygon)))
        self.unfilled_zones = sum(1 for z in children(root, 'zone')
                                  if not children(z, 'filled_polygon') and not first(z, 'keepout'))

    def net(self, node):
        found = first(node, 'net')
        if not found or len(found) < 2:
            return ''
        if isinstance(found[1], Q):
            return str(found[1])
        return str(found[2]) if len(found) > 2 else str(self.net_names.get(found[1], ''))

    def footprint(self, node):
        at = first(node, 'at')
        x, y = point(at)
        angle = math.radians(float(at[3])) if len(at) > 3 else 0.0
        cos, sin = math.cos(angle), math.sin(angle)

        def place(p):  # footprint coordinates to board coordinates; positive angles turn counterclockwise on screen
            return x + p[0] * cos + p[1] * sin, y - p[0] * sin + p[1] * cos

        ref = next((str(p[2]) for p in children(node, 'property') if len(p) > 2 and p[1] == 'Reference'), None)
        if ref is None:
            ref = next((str(t[2]) for t in children(node, 'fp_text') if len(t) > 2 and t[1] == 'reference'), '?')
        pads = [(str(pad[1]), self.net(pad), place(point(first(pad, 'at')))) for pad in children(node, 'pad')
                if first(pad, 'at')]
        courtyard, edge = [], []
        for shape in node[1:]:
            if isinstance(shape, list) and shape and str(shape[0]).startswith('fp_'):
                if layer_of(shape) in ('F.CrtYd', 'B.CrtYd'):
                    courtyard += [place(p) for p in shape_points(shape)]
                elif layer_of(shape) == 'Edge.Cuts':
                    edge += [place(p) for p in shape_points(shape)]
        return {'ref': ref, 'layer': layer_of(node), 'at': (x, y), 'pads': pads, 'courtyard': courtyard, 'edge': edge}

    def pad(self, spec):
        ref, _, number = spec.rpartition('.')
        for fp in self.footprints:
            if fp['ref'] == ref:
                for pad_number, net, position in fp['pads']:
                    if pad_number == number:
                        return pad_number, net, position
                raise ValueError(f'{ref} has no pad {number!r}')
        raise ValueError(f'no footprint {ref!r} (pads are written REF.PAD, for example U2.1)')

    def reference_coverage(self, net):
        """Fraction of the net's track length over a filled zone of another net on an adjacent copper layer."""
        total = covered = 0.0
        for layer, track_net, points, _ in self.tracks:
            if track_net != net or layer not in self.copper:
                continue
            index = self.copper.index(layer)
            refs = [z for adjacent in (index - 1, index + 1) if 0 <= adjacent < len(self.copper)
                    for z in self.zones.get(self.copper[adjacent], []) if z[0] and z[0] != net]
            for a, b in zip(points, points[1:]):
                length = dist(a, b)
                steps = max(1, math.ceil(length / SAMPLE_STEP_MM))
                for i in range(steps):
                    t = (i + 0.5) / steps
                    p = (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)
                    total += length / steps
                    if any(bb[0] <= p[0] <= bb[2] and bb[1] <= p[1] <= bb[3] and inside(p, poly) for _, poly, bb in refs):
                        covered += length / steps
        return covered / total if total else None

    def all_nets(self):
        return ({t[1] for t in self.tracks} | {v[1] for v in self.vias}
                | {pad[1] for fp in self.footprints for pad in fp['pads']}) - {''}


def extent(points):
    if not points:
        return None
    x1, y1, x2, y2 = bbox(points)
    return {'width_mm': round(x2 - x1, 3), 'height_mm': round(y2 - y1, 3), 'area_mm2': round((x2 - x1) * (y2 - y1), 2)}


def measure(board, nets=(), pairs=(), decoupling=(), loops=(), ground=None):
    known = board.all_nets()
    wanted = list(dict.fromkeys(list(nets) + [n for pair in pairs for n in pair]))
    for net in wanted:
        if net not in known:
            close = difflib.get_close_matches(net, sorted(known), n=3)
            raise ValueError(f'no net {net!r}' + (f'; did you mean {", ".join(close)}?' if close else ''))
    is_ground = (lambda n: n in ground) if ground else (lambda n: 'GND' in n.upper())
    report = {'file_version': board.version, 'copper_layers': board.copper,
              'outline': extent(board.outline),
              'courtyards': extent([p for fp in board.footprints for p in fp['courtyard']])}
    if board.outline:
        x1, y1, x2, y2 = bbox(board.outline)
        report['footprints_outside_outline'] = sorted(fp['ref'] for fp in board.footprints
                                                      if not (x1 <= fp['at'][0] <= x2 and y1 <= fp['at'][1] <= y2))
    by_layer = {}
    for layer, _, _, length in board.tracks:
        by_layer[layer] = by_layer.get(layer, 0.0) + length
    report['track_length_mm'] = {'total': round(sum(by_layer.values()), 2),
                                 'by_layer': {k: round(by_layer[k], 2) for k in sorted(by_layer, key=copper_order)}}
    report['vias'] = len(board.vias)
    report['unfilled_zones'] = board.unfilled_zones
    report['nets'] = {}
    for net in wanted:
        coverage = board.reference_coverage(net)
        report['nets'][net] = {
            'length_mm': round(sum(t[3] for t in board.tracks if t[1] == net), 3),
            'vias': sum(1 for v in board.vias if v[1] == net),
            'layers': sorted({t[0] for t in board.tracks if t[1] == net}, key=copper_order),
            'over_reference_plane': None if coverage is None else round(coverage, 3)}
    report['pairs'] = [{'nets': [p, n], 'skew_mm': round(abs(report['nets'][p]['length_mm'] - report['nets'][n]['length_mm']), 3)}
                       for p, n in pairs]
    report['decoupling'] = []
    for ic, caps in decoupling:
        ic_pads = next((fp['pads'] for fp in board.footprints if fp['ref'] == ic), None)
        if ic_pads is None:
            raise ValueError(f'no footprint {ic!r}')
        for cap in caps:
            cap_pads = next((fp['pads'] for fp in board.footprints if fp['ref'] == cap), None)
            if cap_pads is None:
                raise ValueError(f'no footprint {cap!r}')
            best = min(((dist(cp[2], ip[2]), cp[1], ip[0]) for cp in cap_pads for ip in ic_pads
                        if cp[1] and cp[1] == ip[1] and not is_ground(cp[1])), default=None)
            report['decoupling'].append({'ic': ic, 'capacitor': cap, 'net': best[1] if best else None,
                                         'ic_pin': best[2] if best else None,
                                         'distance_mm': round(best[0], 3) if best else None})
    report['loops'] = []
    for chain in loops:
        positions = [board.pad(spec)[2] for spec in chain]
        report['loops'].append({'pads': list(chain), 'area_mm2': round(polygon_area(positions), 3)})
    return report


def summary(name, r):
    def mm(v):
        return 'n/a' if v is None else f'{v:g}'
    lines = [f'Board: {name} (file version {r["file_version"]}), copper: {", ".join(r["copper_layers"])}']
    for key, label in (('outline', 'Outline'), ('courtyards', 'Courtyards')):
        e = r[key]
        lines.append(f'{label}: ' + (f'{mm(e["width_mm"])} x {mm(e["height_mm"])} mm, bounding box {mm(e["area_mm2"])} mm2'
                                     if e else 'none found'))
    if r.get('footprints_outside_outline'):
        lines.append('Footprints outside the outline: ' + ', '.join(r['footprints_outside_outline']))
    t = r['track_length_mm']
    lines.append(f'Tracks: {mm(t["total"])} mm (' + ', '.join(f'{k} {mm(v)}' for k, v in t['by_layer'].items())
                 + f'); vias: {r["vias"]}')
    if r['unfilled_zones']:
        lines.append(f'Warning: {r["unfilled_zones"]} zone(s) unfilled; refill zones and save for reference-plane coverage')
    for net, m in r['nets'].items():
        cover = 'no tracks' if m['over_reference_plane'] is None else f'{m["over_reference_plane"]:.0%} over a reference plane'
        lines.append(f'Net {net}: {mm(m["length_mm"])} mm, {m["vias"]} vias, layers {", ".join(m["layers"]) or "none"}, {cover}')
    for p in r['pairs']:
        lines.append(f'Pair {" / ".join(p["nets"])}: skew {mm(p["skew_mm"])} mm')
    for d in r['decoupling']:
        lines.append(f'Decoupling {d["capacitor"]} -> {d["ic"]}: ' + (f'{mm(d["distance_mm"])} mm to pin {d["ic_pin"]} ({d["net"]})'
                                                                       if d['net'] else 'shares no supply net with the IC'))
    for loop in r['loops']:
        lines.append(f'Loop {" ".join(loop["pads"])}: {mm(loop["area_mm2"])} mm2 (pad-centre polygon)')
    return '\n'.join(lines)


def decoupling_arg(text):
    ic, sep, caps = text.partition(':')
    if not sep or not ic or not caps:
        raise argparse.ArgumentTypeError('expected IC:CAP,CAP,... for example U1:C1,C2')
    return ic, [c for c in caps.split(',') if c]


def loop_arg(text):
    chain = [p for p in text.split(',') if p]
    if len(chain) < 3 or any('.' not in p for p in chain):
        raise argparse.ArgumentTypeError('expected at least three pads as REF.PAD,REF.PAD,..., for example U2.1,C8.1,C8.2')
    return chain


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('board', type=Path, help='The .kicad_pcb file to measure')
    ap.add_argument('--net', nargs='+', default=[], metavar='NET', help='Critical nets to report, by exact KiCad name')
    ap.add_argument('--pair', nargs=2, action='append', default=[], metavar=('P', 'N'), help='A matched pair; repeatable')
    ap.add_argument('--decoupling', type=decoupling_arg, action='append', default=[], metavar='IC:CAP,CAP',
                    help='Capacitors to measure against an IC; repeatable')
    ap.add_argument('--loop', type=loop_arg, action='append', default=[], metavar='REF.PAD,...',
                    help='Pads in loop order, for the enclosed area; repeatable')
    ap.add_argument('--ground', nargs='+', metavar='NET',
                    help='Ground nets to ignore for decoupling (default: nets whose name contains GND)')
    ap.add_argument('--output', type=Path, help='Report directory (default: reports/kicad beside the board)')
    args = ap.parse_args(argv)
    if not args.board.is_file():
        ap.error(f'board file not found: {args.board}')
    try:
        board = Board(args.board.read_text(encoding='utf-8'))
        report = measure(board, args.net, args.pair, args.decoupling, args.loop, set(args.ground) if args.ground else None)
    except (ValueError, IndexError, TypeError) as ex:
        print(f'ERROR: {args.board}: {ex}', file=sys.stderr)
        return 2
    print(summary(args.board.name, report))
    output = args.output or args.board.resolve().parent / 'reports' / 'kicad'
    output.mkdir(parents=True, exist_ok=True)
    path = output / f'{args.board.stem}-layout-metrics.json'
    path.write_text(json.dumps({'board': str(args.board), **report}, indent=2) + '\n', encoding='utf-8')
    print(f'Report: {path}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
