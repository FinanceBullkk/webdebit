"""Read-only V7/Sheet reconciliation; totals govern SONG-SONG-01.

Usage: --sheet-dir CLEAN --ledger-json JSON --out NEW
Add --brief for a count/status-only stdout summary and customer row numbers.
Add --totals-only for SONG-SONG-01/02 daily checks; month buckets are ignored.
reconcile_index.csv maps those numbers to names; existing CSV columns stay fixed.
Or replace --ledger-json JSON with --api http://127.0.0.1:8780.

JSON contains unwrapped get_ledger responses. get_ledger has no customer name:
each filename stem MUST be the customer name (e.g. Khach gia A.json).
API mode gets names from /api/v7/customers and fetches every listed customer.
Sheet totals use anchor_vnd; monthly balances use bucket_vnd. Cumulative
month_end_vnd/sheet_month_end_vnd are not comparison cells and are never summed.
Missing months remain absent; blank/NULL comparison cells yield THIEU_SO.
THIEU_SO exits 1 like other failures: an unknown cell is not a match. Known
totals that differ are LECH_TONG even when a month cell is blank.
Absolute difference is NULL if any customer total difference is unknown;
known_absolute_difference_vnd counts only comparable totals. API input hashes
cover exact HTTP response bytes instead of files. No input data goes to stdout.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import ipaddress
import json
import re
import sys
from collections import Counter
from datetime import date
from http.client import HTTPException
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, build_opener

REPO = Path(__file__).resolve().parents[2]
STATUSES = ('KHOP', 'LECH_TONG', 'CHI_LECH_THANG', 'CHI_CO_SHEET', 'CHI_CO_WEB', 'THIEU_SO')
FAILURES = {'LECH_TONG', 'CHI_CO_SHEET', 'CHI_CO_WEB', 'THIEU_SO'}

class InputError(ValueError):
    pass

def name(value):
    if not isinstance(value, str) or not value.strip():
        raise InputError('missing customer name')
    return ' '.join(value.split())

def vnd(value):
    if value is None:
        return None
    if isinstance(value, str):
        value = value.strip()
        if not value or value.upper() == 'NULL':
            return None
        if re.fullmatch('-?[0-9]+', value):
            return int(value)
    elif type(value) is int:
        return value
    raise InputError('VND must be exact integer or blank/NULL')

def period(value):
    if not isinstance(value, str) or not re.fullmatch('[0-9]{4}-[0-9]{2}(?:-01)?', value):
        raise InputError('invalid debt month')
    date.fromisoformat(value[:7] + '-01')
    return value[:7]

def read_csv(path, required, hashes):
    raw = path.read_bytes()
    hashes[path.name] = hashlib.sha256(raw).hexdigest()
    reader = csv.DictReader(io.StringIO(raw.decode('utf-8-sig'), newline=''), strict=True)
    fields = reader.fieldnames or []
    if len(fields) != len(set(fields)) or not required <= set(fields):
        raise InputError('missing CSV columns')
    rows = list(reader)
    if any(None in row or any(x is None for x in row.values()) for row in rows):
        raise InputError('CSV row width')
    return rows

def read_sheet(folder):
    hashes, customers = ({}, {})
    for row in read_csv(folder / 'clean_customers.csv', {'customer', 'anchor_vnd'}, hashes):
        key = name(row['customer'])
        if key in customers:
            raise InputError('duplicate Sheet customer')
        customers[key] = {'total': vnd(row['anchor_vnd']), 'months': {}}
    required = {'customer', 'debt_month', 'month_end_vnd', 'sheet_month_end_vnd', 'bucket_vnd'}
    for row in read_csv(folder / 'clean_months.csv', required, hashes):
        key, mon = (name(row['customer']), period(row['debt_month']))
        if key not in customers or mon in customers[key]['months']:
            raise InputError('unknown/duplicate Sheet month')
        customers[key]['months'][mon] = vnd(row['bucket_vnd'])
    for item in customers.values():
        item['missing'] = item['total'] is None or not item['months'] or None in item['months'].values()
    return (customers, hashes)

def unique_keys(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            raise InputError('duplicate JSON key')
        out[key] = value
    return out

def decode(raw):
    value = json.loads(raw.decode('utf-8-sig'), object_pairs_hook=unique_keys)
    if not isinstance(value, dict):
        raise InputError('JSON object required')
    return value

def ledger(raw):
    if not {'customer_id', 'status', 'months', 'total_outstanding_vnd'} <= raw.keys():
        raise InputError('missing get_ledger fields')
    if type(raw['customer_id']) is not int or not 0 < raw['customer_id'] <= 9223372036854775807:
        raise InputError('invalid customer ID')
    if raw['status'] not in ('active', 'NO_BASELINE') or not isinstance(raw['months'], list):
        raise InputError('invalid ledger status')
    months = {}
    for row in raw['months']:
        if not isinstance(row, dict) or not {'month', 'outstanding_vnd'} <= row.keys():
            raise InputError('missing ledger month fields')
        mon = period(row['month'])
        if mon in months:
            raise InputError('duplicate web month')
        months[mon] = vnd(row['outstanding_vnd'])
    total = None if raw['status'] == 'NO_BASELINE' else vnd(raw['total_outstanding_vnd'])
    return {'total': total, 'months': months, 'missing': raw['status'] != 'active' or total is None or None in months.values()}

def read_ledgers(folder):
    if not folder.is_dir():
        raise InputError('ledger-json must be directory')
    customers, hashes, ids = ({}, {}, set())
    for path in sorted(folder.glob('*.json')):
        content = path.read_bytes()
        key, raw = (name(path.stem), decode(content))
        item = ledger(raw)
        if key in customers or raw['customer_id'] in ids:
            raise InputError('duplicate web customer/ID')
        customers[key] = item
        ids.add(raw['customer_id'])
        hashes[path.name] = hashlib.sha256(content).hexdigest()
    return (customers, hashes)

def api_base(value, serve_hosts=()):
    parsed = urlsplit(value)
    for authority in serve_hosts:
        if not re.fullmatch(r"(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z][a-z0-9-]*(?::[1-9][0-9]{0,4})?", authority) or not 1 <= (urlsplit('//'+authority).port or 443) <= 65535:
            raise InputError('invalid Serve host')
    host = parsed.hostname
    try:
        loopback = host == 'localhost' or ipaddress.ip_address(host or '').is_loopback
    except ValueError:
        loopback = False
    local = parsed.scheme == 'http' and loopback and parsed.port
    serve = parsed.scheme == 'https' and parsed.netloc in serve_hosts
    if (not (local or serve) or parsed.username is not None
            or parsed.password is not None or parsed.path not in ('', '/')
            or parsed.query or parsed.fragment):
        raise InputError('API requires HTTP loopback with port or explicitly allowed HTTPS Serve host')
    return value.rstrip('/')

class NoRedirect(HTTPRedirectHandler):

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise InputError('API redirect forbidden')

def read_api(value, serve_hosts=()):
    base = api_base(value, serve_hosts)
    opener = build_opener(ProxyHandler({}), NoRedirect())
    hashes, customers, ids = ({}, {}, set())

    def get(route):
        with opener.open(base + route, timeout=10) as response:
            raw = response.read()
        hashes[route] = hashlib.sha256(raw).hexdigest()
        return decode(raw)
    rows = get('/api/v7/customers').get('customers')
    if not isinstance(rows, list):
        raise InputError('missing API customers')
    for row in rows:
        if not isinstance(row, dict) or not {'id', 'name'} <= row.keys():
            raise InputError('invalid API customer')
        key, customer_id = (name(row['name']), row['id'])
        if (type(customer_id) is not int or not 0 < customer_id <= 9223372036854775807
                or key in customers or customer_id in ids):
            raise InputError('duplicate/invalid API customer')
        raw = get(f'/api/v7/ledger?customer={customer_id}')
        if raw.get('customer_id') != customer_id:
            raise InputError('API customer mismatch')
        customers[key] = ledger(raw)
        ids.add(customer_id)
    return (customers, hashes)

def diff(sheet, web):
    return None if sheet is None or web is None else web - sheet

def reconcile(sheet, web, compare_months=True):
    customers, months = ([], [])
    for key in sorted(sheet.keys() | web.keys()):
        left, right = (sheet.get(key), web.get(key))
        sm, wm = ((left or {}).get('months', {}), (right or {}).get('months', {}))
        st, wt = ((left or {}).get('total'), (right or {}).get('total'))
        if left is None:
            status = 'CHI_CO_WEB'
        elif right is None:
            status = 'CHI_CO_SHEET'
        elif st is None or wt is None:
            status = 'THIEU_SO'
        elif st != wt:
            status = 'LECH_TONG'
        elif (left['missing'] or right['missing']) and compare_months:
            status = 'THIEU_SO'
        elif compare_months and sm != wm:
            status = 'CHI_LECH_THANG'
        else:
            status = 'KHOP'
        customers.append({'customer': key, 'sheet_total_vnd': st, 'web_total_vnd': wt, 'difference_vnd': diff(st, wt), 'status': status})
        if status != 'KHOP' and compare_months:
            for mon in sorted(sm.keys() | wm.keys()):
                sv, wv = (sm.get(mon), wm.get(mon))
                months.append({'customer': key, 'debt_month': mon, 'sheet_vnd': sv, 'web_vnd': wv, 'difference_vnd': diff(sv, wv), 'sheet_month_present': mon in sm, 'web_month_present': mon in wm, 'status': status})
    counts = Counter(row['status'] for row in customers)
    deltas = [row['difference_vnd'] for row in customers]
    known = sum(abs(x) for x in deltas if x is not None)
    return customers, months, {
        'counts': {s: counts[s] for s in STATUSES},
        'total_absolute_difference_vnd': None if None in deltas else known,
        'known_absolute_difference_vnd': known,
        'customers_without_total_difference': deltas.count(None),
        'difference_convention': 'web - Sheet',
    }

def output_path(path):
    path = path.resolve()
    if path == REPO or REPO in path.parents or any((p / '.git').exists() for p in (path, *path.parents)):
        raise InputError('output must be outside repository')
    if path.exists():
        raise InputError('output must be new')
    return path

def write_csv(path, fields, rows):
    with path.open('x', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

def number_ranges(numbers):
    ranges = []
    for number in numbers:
        if ranges and number == ranges[-1][1] + 1:
            ranges[-1][1] = number
        else:
            ranges.append([number, number])
    return ','.join(f'#{start}' if start == end else f'#{start}-#{end}' for start, end in ranges)

def print_brief(customers, summary, failed):
    print('DOI SOAT: ' + ('KHONG DAT' if failed else 'DAT'))
    print(' | '.join(f'{status}: {summary["counts"][status]}' for status in STATUSES)
          + f' | TONG: {len(customers)}')
    for status in STATUSES[1:]:
        numbers = [no for no, row in enumerate(customers, 1) if row['status'] == status]
        if numbers:
            print(f'{status}: {number_ranges(numbers)}')
    print('So thu tu -> ten: xem reconcile_customer.csv hoac reconcile_index.csv trong thu muc ket qua.')

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--sheet-dir', type=Path, required=True, help='directory containing both clean CSV files')
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--ledger-json', type=Path, help='JSON directory; filename stems are customer names')
    source.add_argument('--api', help='HTTP loopback with port or HTTPS Serve base URL')
    parser.add_argument('--serve-host', action='append', default=[], help='Exact allowed HTTPS Serve fqdn[:port]; repeatable')
    parser.add_argument('--out', type=Path, required=True, help='new directory outside repositories')
    parser.add_argument('--brief', action='store_true', help='print counts, statuses and customer row numbers only')
    parser.add_argument('--totals-only', action='store_true',
                        help='compare customer totals only; month differences do not affect status')
    args = parser.parse_args(argv)
    try:
        out = output_path(args.out)
        if args.api:
            api_base(args.api, args.serve_host)
        sheet, sh = read_sheet(args.sheet_dir)
        web, wh = read_ledgers(args.ledger_json) if args.ledger_json else read_api(args.api, args.serve_host)
        customers, months, summary = reconcile(sheet, web, compare_months=not args.totals_only)
        summary['comparison_scope'] = 'customer_totals' if args.totals_only else 'customer_totals_and_months'
        summary['input_sha256'] = {'sheet': sh, 'web': wh}
        out.mkdir(parents=True)
        write_csv(out / 'reconcile_customer.csv', ['customer', 'sheet_total_vnd', 'web_total_vnd', 'difference_vnd', 'status'], customers)
        write_csv(out / 'reconcile_month.csv', ['customer', 'debt_month', 'sheet_vnd', 'web_vnd', 'difference_vnd', 'sheet_month_present', 'web_month_present', 'status'], months)
        with (out / 'summary.json').open('x', encoding='utf-8') as stream:
            stream.write(json.dumps(summary, ensure_ascii=False, indent=2) + '\n')
        write_csv(out / 'reconcile_index.csv', ['no', 'customer', 'status'],
                  ({'no': no, 'customer': row['customer'], 'status': row['status']}
                   for no, row in enumerate(customers, 1)))
        failed = int(any(row['status'] in FAILURES for row in customers))
        if args.brief:
            print_brief(customers, summary, failed)
        return failed
    except (OSError, ValueError, csv.Error, HTTPException, RecursionError):
        print('reconciliation input/output error; no result accepted', file=sys.stderr)
        return 2
if __name__ == '__main__':
    raise SystemExit(main())
