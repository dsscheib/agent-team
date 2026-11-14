#!/usr/bin/env python3
"""Check stock and lifecycle status of parts at Digi-Key and Mouser, and stock on hand in a Feeder
parts inventory. Read-only: never orders and never changes Feeder.

Parts are looked up by manufacturer part number (MPN), given on the command line or read from a
BOM CSV with an MPN column (and optionally a quantity column). A line passes when at least one
distributor has the part Active and in stock for the needed quantity (per-board qty x --boards), or
Feeder has that quantity available (on hand minus what its projects have reserved).

Credentials come from the environment, or from KEY=VALUE *.env files in $DISTRIBUTOR_API_DIR
(default ~/.config/distributor-api). Environment variables win over files.
  Digi-Key: DIGIKEY_CLIENT_ID, DIGIKEY_CLIENT_SECRET  (Product Information API v4, client credentials)
  Mouser:   MOUSER_API_KEY                            (Search API v1)
  Feeder:   FEEDER_URL, FEEDER_API_KEY                 (parts API v1; key from `feeder api-key create`)
A source without credentials is skipped. Secrets are never printed or written to reports.
FEEDER_URL must be https:// unless it names this computer (localhost, 127.0.0.1, [::1]).

Writes reports/kicad/availability-<UTC timestamp>.csv and prints a summary.
Exit status: 0 every line passes, 1 some line fails, 2 usage or configuration error.
"""
import argparse
import csv
import json
import os
import re
import stat
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_CONFIG_DIR = Path.home() / '.config/distributor-api'
SECRET_KEYS = ('DIGIKEY_CLIENT_ID', 'DIGIKEY_CLIENT_SECRET', 'MOUSER_API_KEY', 'FEEDER_URL', 'FEEDER_API_KEY')
MPN_COLUMNS = ('mpn', 'manufacturer part number', 'manufacturer_part_number', 'mfr part number',
               'mfr. #', 'mfr #', 'mfg part number', 'part number', 'manufacturer_pn', 'mfr_pn')
QTY_COLUMNS = ('qty', 'quantity', 'qty per board', 'count')
TIMEOUT = 30

DIGIKEY_TOKEN_URL = 'https://api.digikey.com/v1/oauth2/token'
DIGIKEY_SEARCH_URL = 'https://api.digikey.com/products/v4/search/keyword'
MOUSER_SEARCH_URL = 'https://api.mouser.com/api/v1/search/partnumber'

# Lifecycle values that count as orderable for a new design. Anything else (NRND, Last Time Buy,
# EOL, Obsolete, Discontinued, Preliminary...) is reported as not active.
DIGIKEY_ACTIVE = {'active'}
MOUSER_ACTIVE = {'', 'new product', 'new at mouser'}

REPORT_FIELDS = ('mpn', 'needed_qty', 'distributor', 'distributor_pn', 'manufacturer', 'stock',
                 'lifecycle', 'verdict', 'unit_price_usd', 'price_break_qty', 'moq', 'datasheet',
                 'product_url', 'note', 'checked_at_utc')


# ---------------------------------------------------------------- configuration

def load_credentials(config_dir, environ=os.environ):
    """Return the credentials found, environment first, then *.env files in config_dir."""
    creds = {k: environ[k] for k in SECRET_KEYS if environ.get(k)}
    warnings = []
    if config_dir.is_dir():
        for path in sorted(config_dir.glob('*.env')):
            if path.stat().st_mode & (stat.S_IRWXG | stat.S_IRWXO):
                warnings.append(f'{path} is readable by other users; chmod 600 it')
            for key, value in parse_env(path.read_text(encoding='utf-8')).items():
                if key in SECRET_KEYS and value:
                    creds.setdefault(key, value)
    return creds, warnings


def parse_env(text):
    values = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, value = line.split('=', 1)
        key = key.strip().removeprefix('export ').strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in '"\'':
            value = value[1:-1]
        values[key] = value
    return values


# ---------------------------------------------------------------- input

def read_bom(path):
    """Return [(mpn, qty_per_board)] from a CSV whose header names an MPN column."""
    with open(path, newline='', encoding='utf-8-sig') as f:
        sample = f.read(4096)
        f.seek(0)
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=',;\t')
        except csv.Error:
            dialect = csv.excel
        reader = csv.DictReader(f, dialect=dialect)
        headers = {h.strip().lower(): h for h in reader.fieldnames or []}
        mpn_col = next((headers[c] for c in MPN_COLUMNS if c in headers), None)
        if mpn_col is None:
            raise ValueError(f'{path}: no MPN column; expected one of: {", ".join(MPN_COLUMNS)}')
        qty_col = next((headers[c] for c in QTY_COLUMNS if c in headers), None)
        lines = []
        for row in reader:
            mpn = (row.get(mpn_col) or '').strip()
            if not mpn or mpn == '~':
                continue
            qty = 1
            if qty_col and (row.get(qty_col) or '').strip():
                try:
                    qty = max(1, int(float(row[qty_col])))
                except ValueError:
                    pass
            lines.append((mpn, qty))
    return merge_lines(lines)


def merge_lines(lines):
    """Sum quantities of repeated MPNs, keeping first-seen order."""
    merged = {}
    for mpn, qty in lines:
        key = mpn.upper()
        name, total = merged.get(key, (mpn, 0))
        merged[key] = (name, total + qty)
    return list(merged.values())


# ---------------------------------------------------------------- HTTP

class Throttle:
    def __init__(self, min_interval):
        self.min_interval, self.last = min_interval, 0.0

    def wait(self):
        delay = self.last + self.min_interval - time.monotonic()
        if delay > 0:
            time.sleep(delay)
        self.last = time.monotonic()


def http_json(url, data=None, headers=None, form=False):
    body = None
    headers = dict(headers or {})
    headers.setdefault('Accept', 'application/json')
    if data is not None:
        if form:
            body = urllib.parse.urlencode(data).encode()
            headers['Content-Type'] = 'application/x-www-form-urlencoded'
        else:
            body = json.dumps(data).encode()
            headers['Content-Type'] = 'application/json'
    req = urllib.request.Request(url, data=body, headers=headers, method='POST' if body else 'GET')
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return json.loads(resp.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        # Report status and the API's own message only; the URL may carry a key.
        detail = ''
        try:
            payload = json.loads(e.read().decode('utf-8', 'replace'))
            detail = payload.get('detail') or payload.get('ErrorMessage') or payload.get('message') or ''
        except Exception:
            pass
        raise LookupError(f'HTTP {e.code} {e.reason}{": " + str(detail)[:200] if detail else ""}') from None
    except (urllib.error.URLError, TimeoutError) as e:
        raise LookupError(f'network error: {getattr(e, "reason", e)}') from None


# ---------------------------------------------------------------- common result helpers

def to_int(value):
    if value is None:
        return None
    digits = re.sub(r'[^\d]', '', str(value))
    return int(digits) if digits else None


def to_price(value):
    if value is None:
        return None
    m = re.search(r'\d[\d,]*\.?\d*', str(value))
    return float(m.group().replace(',', '')) if m else None


def price_at(breaks, qty):
    """breaks: [(break_qty, unit_price)]. Return the break that applies to qty, or the smallest."""
    breaks = sorted(b for b in breaks if b[0] and b[1] is not None)
    if not breaks:
        return None, None
    chosen = breaks[0]
    for b in breaks:
        if b[0] <= qty:
            chosen = b
    return chosen


def verdict(found, active, stock, needed):
    if not found:
        return 'NOT_FOUND'
    if not active:
        return 'NOT_ACTIVE'
    if not stock:
        return 'OUT_OF_STOCK'
    if stock < needed:
        return 'LOW_STOCK'
    return 'OK'


def result(mpn, needed, distributor, **fields):
    row = dict.fromkeys(REPORT_FIELDS, '')
    row.update(mpn=mpn, needed_qty=needed, distributor=distributor)
    row.update({k: ('' if v is None else v) for k, v in fields.items()})
    return row


# ---------------------------------------------------------------- Digi-Key

class DigiKey:
    name = 'Digi-Key'

    def __init__(self, client_id, client_secret):
        self.client_id, self.client_secret = client_id, client_secret
        self.token, self.expires = None, 0.0
        self.throttle = Throttle(0.6)

    def headers(self):
        if not self.token or time.monotonic() > self.expires - 60:
            data = http_json(DIGIKEY_TOKEN_URL, {'client_id': self.client_id, 'client_secret': self.client_secret,
                                                 'grant_type': 'client_credentials'}, form=True)
            self.token = data['access_token']
            self.expires = time.monotonic() + float(data.get('expires_in', 600))
        return {'Authorization': f'Bearer {self.token}', 'X-DIGIKEY-Client-Id': self.client_id,
                'X-DIGIKEY-Locale-Site': 'US', 'X-DIGIKEY-Locale-Language': 'en',
                'X-DIGIKEY-Locale-Currency': 'USD'}

    def lookup(self, mpn, needed):
        self.throttle.wait()
        data = http_json(DIGIKEY_SEARCH_URL, {'Keywords': mpn, 'Limit': 10, 'Offset': 0}, self.headers())
        return parse_digikey(data, mpn, needed)


def parse_digikey(data, mpn, needed):
    # ExactMatches usually repeats entries from Products; key each product by MPN and manufacturer.
    unique = {}
    for p in (data.get('ExactMatches') or []) + (data.get('Products') or []):
        key = ((p.get('ManufacturerProductNumber') or '').upper(), (p.get('Manufacturer') or {}).get('Name'))
        unique.setdefault(key, p)
    products = list(unique.values())
    exact = [p for p in products if (p.get('ManufacturerProductNumber') or '').upper() == mpn.upper()]
    if not exact:
        near = sorted({p.get('ManufacturerProductNumber') for p in products if p.get('ManufacturerProductNumber')})
        return result(mpn, needed, 'Digi-Key', verdict='NOT_FOUND',
                      note=('near matches: ' + ', '.join(near[:5])) if near else 'no results')
    # Several manufacturers can share an MPN; report the one with the most stock.
    p = max(exact, key=lambda x: to_int(x.get('QuantityAvailable')) or 0)
    lifecycle = ((p.get('ProductStatus') or {}).get('Status') or '').strip()
    active = lifecycle.lower() in DIGIKEY_ACTIVE and not p.get('Discontinued') and not p.get('EndOfLife')
    stock = to_int(p.get('QuantityAvailable')) or 0
    variations = p.get('ProductVariations') or []
    # Prefer a package type you can buy at the needed quantity (lowest MOQ, then most stock).
    var = None
    if variations:
        var = sorted(variations, key=lambda v: ((to_int(v.get('MinimumOrderQuantity')) or 1) > needed,
                                                -(to_int(v.get('QuantityAvailableforPackageType')) or 0)))[0]
    breaks = [(to_int(b.get('BreakQuantity')), to_price(b.get('UnitPrice')))
              for b in (var or {}).get('StandardPricing') or []]
    break_qty, unit = price_at(breaks, needed)
    note = []
    if len(exact) > 1:
        note.append(f'{len(exact)} manufacturers share this MPN')
    if var and (var.get('PackageType') or {}).get('Name'):
        note.append(f'package: {var["PackageType"]["Name"]}')
    return result(mpn, needed, 'Digi-Key',
                  distributor_pn=(var or {}).get('DigiKeyProductNumber'),
                  manufacturer=(p.get('Manufacturer') or {}).get('Name'),
                  stock=stock, lifecycle=lifecycle or 'unknown',
                  verdict=verdict(True, active, stock, needed),
                  unit_price_usd=unit, price_break_qty=break_qty,
                  moq=to_int((var or {}).get('MinimumOrderQuantity')),
                  datasheet=p.get('DatasheetUrl'), product_url=p.get('ProductUrl'), note='; '.join(note))


# ---------------------------------------------------------------- Mouser

class Mouser:
    name = 'Mouser'

    def __init__(self, api_key):
        self.api_key = api_key
        self.throttle = Throttle(2.1)  # Mouser allows about 30 calls per minute

    def lookup(self, mpn, needed):
        self.throttle.wait()
        url = MOUSER_SEARCH_URL + '?' + urllib.parse.urlencode({'apiKey': self.api_key})
        data = http_json(url, {'SearchByPartRequest': {'mouserPartNumber': mpn, 'partSearchOptions': 'Exact'}})
        return parse_mouser(data, mpn, needed)


def parse_mouser(data, mpn, needed):
    errors = data.get('Errors') or []
    if errors:
        raise LookupError('; '.join(str(e.get('Message') or e) for e in errors)[:200])
    parts = ((data.get('SearchResults') or {}).get('Parts')) or []
    exact = [p for p in parts if (p.get('ManufacturerPartNumber') or '').upper() == mpn.upper()]
    if not exact:
        near = sorted({p.get('ManufacturerPartNumber') for p in parts if p.get('ManufacturerPartNumber')})
        return result(mpn, needed, 'Mouser', verdict='NOT_FOUND',
                      note=('near matches: ' + ', '.join(near[:5])) if near else 'no results')
    p = max(exact, key=lambda x: to_int(x.get('AvailabilityInStock')) or 0)
    lifecycle = (p.get('LifecycleStatus') or '').strip()
    discontinued = str(p.get('IsDiscontinued') or '').lower() == 'true'
    active = lifecycle.lower() in MOUSER_ACTIVE and not discontinued
    stock = to_int(p.get('AvailabilityInStock'))
    if stock is None:
        avail = p.get('Availability') or ''
        stock = to_int(avail) if 'in stock' in avail.lower() else 0
    breaks = [(to_int(b.get('Quantity')), to_price(b.get('Price'))) for b in p.get('PriceBreaks') or []]
    break_qty, unit = price_at(breaks, needed)
    note = []
    if len(exact) > 1:
        note.append(f'{len(exact)} listings share this MPN')
    if not stock and p.get('LeadTime'):
        note.append(f'lead time: {p["LeadTime"]}')
    return result(mpn, needed, 'Mouser',
                  distributor_pn=p.get('MouserPartNumber'), manufacturer=p.get('Manufacturer'),
                  stock=stock, lifecycle=lifecycle or ('Discontinued' if discontinued else 'Active'),
                  verdict=verdict(True, active, stock, needed),
                  unit_price_usd=unit, price_break_qty=break_qty, moq=to_int(p.get('Min')),
                  datasheet=p.get('DataSheetUrl'), product_url=p.get('ProductDetailUrl'),
                  note='; '.join(note))


# ---------------------------------------------------------------- Feeder

def feeder_base_url(url):
    """Return the Feeder base URL without a trailing slash; refuse plain http to another host,
    which would send the API key in the clear."""
    parsed = urllib.parse.urlsplit(url.strip())
    local = parsed.hostname in ('localhost', '127.0.0.1', '::1')
    if parsed.scheme != 'https' and not (parsed.scheme == 'http' and local):
        raise ValueError('FEEDER_URL must start with https:// (http:// only for localhost)')
    if not parsed.hostname:
        raise ValueError('FEEDER_URL has no host name')
    return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, parsed.path.rstrip('/'), '', ''))


class Feeder:
    """The owner's own parts inventory: what is on hand, reserved and where it is stored."""
    name = 'Feeder'

    def __init__(self, url, api_key):
        self.url, self.api_key = feeder_base_url(url), api_key

    def lookup(self, mpn, needed):
        data = http_json(self.url + '/api/v1/search/partnumber', {'PartNumbers': [mpn]},
                         {'Authorization': f'Bearer {self.api_key}'})
        return parse_feeder(data, mpn, needed)


def parse_feeder(data, mpn, needed):
    # Feeder matches MPNs ignoring case, punctuation and packaging suffixes, so every product it
    # returns is this part; more than one means it is stored in more than one place.
    results = data.get('Results') or []
    products = (results[0].get('Products') if results else None) or []
    if not products:
        return result(mpn, needed, 'Feeder', verdict='NOT_FOUND', note='not in the inventory')
    available = sum(max(to_int(p.get('QuantityAvailable')) or 0, 0) for p in products)
    reserved = sum(to_int(p.get('QuantityReserved')) or 0 for p in products)
    best = max(products, key=lambda p: to_int(p.get('QuantityAvailable')) or 0)
    places = []
    for p in products:
        where = (p.get('Location') or {}).get('Path') or 'not put away'
        section = (p.get('Location') or {}).get('Section')
        places.append(f'{where}{" (" + section + ")" if section else ""}: {to_int(p.get("QuantityAvailable")) or 0}')
    note = ['at ' + '; '.join(places)]
    if reserved:
        note.append(f'{reserved} more reserved for projects')
    # Feeder holds stock whatever the part's lifecycle; lifecycle comes from the distributor rows.
    return result(mpn, needed, 'Feeder',
                  distributor_pn=', '.join(f'part {p.get("PartId")}' for p in products),
                  manufacturer=best.get('Manufacturer'), stock=available, lifecycle='on hand',
                  verdict=verdict(True, True, available, needed), unit_price_usd=best.get('UnitPrice'),
                  price_break_qty='', moq='', datasheet=best.get('DatasheetUrl'),
                  product_url=best.get('ProductUrl'), note='; '.join(note))


# ---------------------------------------------------------------- main

def check(lines, distributors, boards, stamp):
    rows, failures = [], []
    for mpn, per_board in lines:
        needed = per_board * boards
        line_rows = []
        for d in distributors:
            try:
                row = d.lookup(mpn, needed)
            except (LookupError, KeyError, ValueError) as e:
                row = result(mpn, needed, d.name, verdict='ERROR', note=str(e))
            row['checked_at_utc'] = stamp
            line_rows.append(row)
        rows.extend(line_rows)
        if not any(r['verdict'] == 'OK' for r in line_rows):
            failures.append(mpn)
    return rows, failures


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('mpns', nargs='*', help='Manufacturer part numbers (quantity 1 each)')
    ap.add_argument('--bom', type=Path, help='BOM CSV with an MPN column and optional quantity column')
    ap.add_argument('--boards', type=int, default=1, help='Number of boards to build (multiplies quantities)')
    ap.add_argument('--project', type=Path, default=Path('.'), help='Project directory (for the report location)')
    ap.add_argument('--output', type=Path, default=None, help='Report directory (default: PROJECT/reports/kicad)')
    ap.add_argument('--config-dir', type=Path, default=None,
                    help=f'Credential directory (default: $DISTRIBUTOR_API_DIR or {DEFAULT_CONFIG_DIR})')
    args = ap.parse_args(argv)
    if args.boards < 1:
        ap.error('--boards must be at least 1')

    lines = [(m.strip(), 1) for m in args.mpns if m.strip()]
    if args.bom:
        try:
            lines += read_bom(args.bom)
        except (OSError, ValueError) as e:
            print(f'ERROR: {e}', file=sys.stderr)
            return 2
    lines = merge_lines(lines)
    if not lines:
        ap.error('give part numbers or --bom')

    config_dir = (args.config_dir or Path(os.environ.get('DISTRIBUTOR_API_DIR') or DEFAULT_CONFIG_DIR)).expanduser()
    creds, warnings = load_credentials(config_dir)
    for w in warnings:
        print('WARNING:', w, file=sys.stderr)
    distributors = []
    if creds.get('FEEDER_URL') and creds.get('FEEDER_API_KEY'):
        try:
            distributors.append(Feeder(creds['FEEDER_URL'], creds['FEEDER_API_KEY']))
        except ValueError as e:
            print(f'ERROR: {e}', file=sys.stderr)
            return 2
    else:
        print('Feeder: skipped (FEEDER_URL / FEEDER_API_KEY not set)', file=sys.stderr)
    if creds.get('DIGIKEY_CLIENT_ID') and creds.get('DIGIKEY_CLIENT_SECRET'):
        distributors.append(DigiKey(creds['DIGIKEY_CLIENT_ID'], creds['DIGIKEY_CLIENT_SECRET']))
    else:
        print('Digi-Key: skipped (DIGIKEY_CLIENT_ID / DIGIKEY_CLIENT_SECRET not set)', file=sys.stderr)
    if creds.get('MOUSER_API_KEY'):
        distributors.append(Mouser(creds['MOUSER_API_KEY']))
    else:
        print('Mouser: skipped (MOUSER_API_KEY not set)', file=sys.stderr)
    if not distributors:
        print(f'ERROR: no Feeder or distributor credentials in the environment or {config_dir}. '
              'Check stock manually on the distributor sites.', file=sys.stderr)
        return 2

    now = datetime.now(timezone.utc)
    stamp = now.strftime('%Y-%m-%dT%H:%M:%SZ')
    rows, failures = check(lines, distributors, args.boards, stamp)

    out_dir = (args.output or args.project.expanduser().resolve() / 'reports/kicad')
    out_dir.mkdir(parents=True, exist_ok=True)
    report = out_dir / f'availability-{now.strftime("%Y%m%dT%H%M%SZ")}.csv'
    with open(report, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=REPORT_FIELDS, lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)

    print(f'Checked {len(lines)} part(s) x {args.boards} board(s) at {stamp}')
    for row in rows:
        price = ''
        if row['unit_price_usd'] != '':
            price = f' ${row["unit_price_usd"]}' + (f'@{row["price_break_qty"]}' if row['price_break_qty'] != '' else '')
        print(f'  {row["verdict"]:12} {row["mpn"]:24} {row["distributor"]:9} stock={row["stock"]!s:>7} '
              f'need={row["needed_qty"]} {row["lifecycle"]}{price}{"  (" + row["note"] + ")" if row["note"] else ""}')
    print('Report:', report)
    if failures:
        print(f'FAIL: neither Feeder has these available nor a distributor Active and in stock: {", ".join(failures)}')
        return 1
    print('PASS: every part is available in Feeder or Active and in stock at one or more distributors')
    return 0


if __name__ == '__main__':
    sys.exit(main())
