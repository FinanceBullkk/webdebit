"""Bounded, read-only PostgreSQL queries for the M1 viewer.

Values go through psql's :'variable' SQL-literal quoting. The database role
has SELECT on a short list of views and defaults to read-only transactions.
"""

from __future__ import annotations

import json
import re
import subprocess
from datetime import date


class DatabaseUnavailable(RuntimeError):
    pass


class Database:
    def __init__(self, dbname: str, capture_id: str, as_of: str, psql: str = "psql"):
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", capture_id):
            raise ValueError("invalid capture ID")
        date.fromisoformat(as_of)
        self.dbname = dbname
        self.capture_id = capture_id
        self.as_of = as_of
        self.psql = psql

    def rows(self, sql: str, **params) -> list[dict]:
        values = {"capture": self.capture_id, "as_of": self.as_of, **params}
        command = [self.psql, "-X", "-w", "-q", "-A", "-t", "-v", "ON_ERROR_STOP=1"]
        for key, value in values.items():
            if not re.fullmatch(r"[a-z_]+", key):
                raise ValueError("invalid query variable")
            command += ["-v", f"{key}={value}"]
        command += ["-d", self.dbname, "-f", "-"]
        # SQL is fixed in this module; user values appear only as :'variable'.
        statement = f"SELECT coalesce(json_agg(item), '[]'::json) FROM ({sql}) item;\n"
        try:
            result = subprocess.run(command, input=statement, text=True,
                                    capture_output=True, encoding="utf-8", timeout=8,
                                    check=False)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise DatabaseUnavailable("PostgreSQL query unavailable") from exc
        if result.returncode:
            raise DatabaseUnavailable("PostgreSQL query failed")
        try:
            parsed = json.loads(result.stdout.strip())
        except json.JSONDecodeError as exc:
            raise DatabaseUnavailable("PostgreSQL returned invalid JSON") from exc
        if not isinstance(parsed, list):
            raise DatabaseUnavailable("PostgreSQL returned invalid row set")
        return parsed

    def provenance(self):
        return self.rows("""
            SELECT capture_id, as_of, source_spreadsheet_id, source_title,
                   source_workbook_sha256, engine_sha256, baseline_date
            FROM pilot.m1_provenance
            WHERE capture_id = :'capture' AND as_of = :'as_of'::date
            LIMIT 1
        """)

    def coverage(self):
        return self.rows("""
            SELECT tab_title, source_rows, decided_rows, missing_rows,
                   accepted_rows, replayed_rows, quarantined_rows
            FROM pilot.m1_coverage
            WHERE capture_id = :'capture' AND as_of = :'as_of'::date
            ORDER BY tab_title
        """)

    def customers(self, search: str = ""):
        return self.rows("""
            SELECT customer, sheet_balance_vnd, db_balance_vnd,
                   old_book_delta_vnd, result
            FROM pilot.m1_customer_diff
            WHERE capture_id = :'capture' AND as_of = :'as_of'::date
              AND position(lower(:'search') in lower(customer)) > 0
            ORDER BY customer LIMIT 250
        """, search=search)

    def period_status_counts(self):
        return self.rows("""
            SELECT result, count(*) AS n
            FROM pilot.m1_period_diff
            WHERE capture_id = :'capture' AND as_of = :'as_of'::date
            GROUP BY result ORDER BY result
        """)

    def exception_counts(self):
        return self.rows("""
            SELECT code, count(*) AS n
            FROM pilot.m1_exception_detail
            WHERE capture_id = :'capture' AND as_of = :'as_of'::date
            GROUP BY code ORDER BY code
        """)

    def periods(self, customer: str):
        return self.rows("""
            SELECT d.customer, d.debt_period, d.sheet_balance_vnd,
                   d.db_balance_vnd, d.delta_vnd, d.result,
                   p.event_count, p.opening_vnd, p.charge_vnd,
                   p.receipt_vnd, p.offset_vnd,
                   p.adjustment_plus_vnd, p.adjustment_minus_vnd
            FROM pilot.m1_period_diff d
            LEFT JOIN pilot.m1_period_balance p
              ON p.capture_id = d.capture_id AND p.as_of = d.as_of
             AND p.customer = d.customer AND p.debt_period = d.debt_period
            WHERE d.capture_id = :'capture' AND d.as_of = :'as_of'::date
              AND d.customer = :'customer'
            ORDER BY d.debt_period DESC LIMIT 250
        """, customer=customer)

    def period(self, customer: str, debt_period: str):
        return self.rows("""
            SELECT d.customer, d.debt_period, d.sheet_balance_vnd,
                   d.db_balance_vnd, d.delta_vnd, d.result,
                   d.baseline_gid, d.baseline_row,
                   p.event_count, p.opening_vnd, p.charge_vnd,
                   p.receipt_vnd, p.offset_vnd,
                   p.adjustment_plus_vnd, p.adjustment_minus_vnd
            FROM pilot.m1_period_diff d
            LEFT JOIN pilot.m1_period_balance p
              ON p.capture_id = d.capture_id AND p.as_of = d.as_of
             AND p.customer = d.customer AND p.debt_period = d.debt_period
            WHERE d.capture_id = :'capture' AND d.as_of = :'as_of'::date
              AND d.customer = :'customer' AND d.debt_period = :'period'
            LIMIT 1
        """, customer=customer, period=debt_period)

    def events(self, customer: str, debt_period: str, limit: int, offset: int):
        return self.rows("""
            SELECT event_no, posting_date, kind, amount_vnd, signed_amount_vnd,
                   tab_title, sheet_gid, source_row, row_sha256, source_url
            FROM pilot.web_period_event
            WHERE capture_id = :'capture' AND as_of = :'as_of'::date
              AND customer = :'customer' AND debt_period = :'period'
            ORDER BY posting_date, event_no
            LIMIT :'limit'::integer OFFSET :'offset'::integer
        """, customer=customer, period=debt_period,
             limit=limit, offset=offset)

    def exception_total(self, code: str, customer: str):
        return self.rows("""
            SELECT count(*) AS n FROM pilot.m1_exception_detail
            WHERE capture_id = :'capture' AND as_of = :'as_of'::date
              AND (:'code' = '' OR code = :'code')
              AND (:'customer' = '' OR customer = :'customer')
        """, code=code, customer=customer)[0]["n"]

    def exceptions(self, code: str, customer: str, limit: int, offset: int):
        return self.rows("""
            SELECT exception_no, code, status, resolution_status,
                   customer, debt_period, detail, tab_title, sheet_gid,
                   source_row, row_sha256, source_url
            FROM pilot.m1_exception_detail
            WHERE capture_id = :'capture' AND as_of = :'as_of'::date
              AND (:'code' = '' OR code = :'code')
              AND (:'customer' = '' OR customer = :'customer')
            ORDER BY exception_no
            LIMIT :'limit'::integer OFFSET :'offset'::integer
        """, code=code, customer=customer, limit=limit, offset=offset)

    def source_row(self, sheet_gid: int, source_row: int):
        return self.rows("""
            SELECT sheet_gid, source_row, tab_title, row_sha256,
                   source_values, source_url
            FROM pilot.web_source_row
            WHERE capture_id = :'capture'
              AND sheet_gid = :'gid'::bigint
              AND source_row = :'row'::integer
            LIMIT 1
        """, gid=sheet_gid, row=source_row)
