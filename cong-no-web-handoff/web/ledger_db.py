"""Read-only projections of the independent HTH ledger."""

from __future__ import annotations

import json
import re
import subprocess
from datetime import date


class LedgerUnavailable(RuntimeError):
    pass


class LedgerDB:
    def __init__(self, dbname: str = "webdebit_ledger", psql: str = "psql"):
        if not re.fullmatch(r"[a-zA-Z0-9_]+", dbname):
            raise ValueError("invalid database name")
        self.dbname, self.psql = dbname, psql

    def rows(self, sql: str, **values) -> list[dict]:
        command = [self.psql, "-X", "-w", "-q", "-A", "-t", "-v", "ON_ERROR_STOP=1"]
        for key, value in values.items():
            if not re.fullmatch(r"[a-z_]+", key):
                raise ValueError("invalid SQL variable")
            command += ["-v", f"{key}={value}"]
        command += ["-d", self.dbname, "-f", "-"]
        try:
            result = subprocess.run(command, check=False,
                input=f"SELECT coalesce(json_agg(item), '[]'::json) FROM ({sql}) item;\n",
                text=True, capture_output=True, encoding="utf-8", timeout=8)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise LedgerUnavailable("PostgreSQL unavailable") from exc
        if result.returncode:
            raise LedgerUnavailable("PostgreSQL read failed")
        try:
            data = json.loads(result.stdout.strip())
        except json.JSONDecodeError as exc:
            raise LedgerUnavailable("Invalid PostgreSQL result") from exc
        if not isinstance(data, list):
            raise LedgerUnavailable("Invalid PostgreSQL rows")
        return data

    def cutover(self):
        return self.rows("SELECT capture_id, as_of, captured_at_utc, source_spreadsheet_id, "
                         "source_workbook_sha256, engine_sha256, period_report_sha256, "
                         "opening_decision, first_posting_date FROM ledger.cutover LIMIT 1")

    def totals(self, as_of: date):
        return self.rows("""SELECT (SELECT count(*) FROM ledger.customer) AS customers,
            (SELECT count(*) FROM ledger.opening) AS opening_periods,
            (SELECT count(*) FROM ledger.opening WHERE comparison_status='NO_BASELINE') AS no_baseline,
            (SELECT coalesce(sum(balance_vnd),0) FROM ledger.opening) AS opening_vnd,
            (SELECT coalesce(sum(movement_vnd),0) FROM ledger.balance_as_of(:'date'::date)) AS movement_vnd,
            (SELECT coalesce(sum(balance_vnd),0) FROM ledger.balance_as_of(:'date'::date)) AS balance_vnd,
            (SELECT count(*) FROM ledger.proposal WHERE status='pending') AS pending,
            (SELECT count(*) FROM ledger.posting WHERE posting_date <= :'date'::date) AS postings
        """, date=as_of.isoformat())[0]

    def customers(self, as_of: date, search: str = ""):
        return self.rows("""SELECT c.customer, coalesce(sum(b.opening_vnd),0) AS opening_vnd,
            coalesce(sum(b.movement_vnd),0) AS movement_vnd,
            coalesce(sum(b.balance_vnd),0) AS balance_vnd,
            count(b.debt_period) AS periods,
            count(o.debt_period) FILTER (WHERE o.comparison_status='NO_BASELINE') AS no_baseline
            FROM ledger.customer c
            LEFT JOIN ledger.balance_as_of(:'date'::date) b ON b.customer=c.customer
            LEFT JOIN ledger.opening o ON o.customer=b.customer AND o.debt_period=b.debt_period
            WHERE position(lower(:'search') in lower(c.customer)) > 0
            GROUP BY c.customer ORDER BY c.customer LIMIT 250
        """, date=as_of.isoformat(), search=search)

    def overview(self, as_of: date, period: str, search: str = ""):
        """Current ledger balances, split around the selected debt period.

        The opening amount of a period is already net of historical replay
        charges and receipts. It must never be labelled as a new charge.
        """
        return self.rows("""WITH balances AS (
            SELECT * FROM ledger.balance_as_of(:'date'::date)
        ), grouped AS (
            SELECT customer,
                coalesce(sum(balance_vnd) FILTER (WHERE debt_period < :'period'),0) AS carried_vnd,
                coalesce(sum(opening_vnd) FILTER (WHERE debt_period = :'period'),0) AS period_opening_vnd,
                coalesce(sum(movement_vnd) FILTER (WHERE debt_period = :'period'),0) AS period_movement_vnd,
                coalesce(sum(balance_vnd) FILTER (WHERE debt_period = :'period'),0) AS period_balance_vnd,
                coalesce(sum(balance_vnd),0) AS total_balance_vnd
            FROM balances GROUP BY customer
        ), by_kind AS (
            SELECT customer,
                coalesce(sum(signed_amount_vnd) FILTER (WHERE kind='charge'),0) AS charge_vnd,
                coalesce(sum(-signed_amount_vnd) FILTER (WHERE kind='receipt'),0) AS receipt_vnd,
                coalesce(sum(-signed_amount_vnd) FILTER (WHERE kind='offset'),0) AS offset_vnd,
                coalesce(sum(signed_amount_vnd) FILTER
                    (WHERE kind IN ('adjustment_plus','adjustment_minus','reversal')),0) AS other_vnd
            FROM ledger.posting
            WHERE debt_period=:'period' AND posting_date <= :'date'::date
            GROUP BY customer
        )
        SELECT c.customer, coalesce(g.carried_vnd,0) AS carried_vnd,
            coalesce(g.period_opening_vnd,0) AS period_opening_vnd,
            coalesce(g.period_movement_vnd,0) AS period_movement_vnd,
            coalesce(g.period_balance_vnd,0) AS period_balance_vnd,
            coalesce(g.total_balance_vnd,0) AS total_balance_vnd,
            coalesce(k.charge_vnd,0) AS charge_vnd,
            coalesce(k.receipt_vnd,0) AS receipt_vnd,
            coalesce(k.offset_vnd,0) AS offset_vnd,
            coalesce(k.other_vnd,0) AS other_vnd,
            o.comparison_status
        FROM ledger.customer c
        LEFT JOIN grouped g ON g.customer=c.customer
        LEFT JOIN by_kind k ON k.customer=c.customer
        LEFT JOIN ledger.opening o ON o.customer=c.customer AND o.debt_period=:'period'
        WHERE position(lower(:'search') in lower(c.customer)) > 0
        ORDER BY c.customer LIMIT 250
        """, date=as_of.isoformat(), period=period, search=search)

    def periods(self, as_of: date, customer: str):
        return self.rows("""SELECT b.customer,b.debt_period,b.opening_vnd,b.movement_vnd,b.balance_vnd,
            o.comparison_status,o.replay_event_count
            FROM ledger.balance_as_of(:'date'::date) b
            LEFT JOIN ledger.opening o ON o.customer=b.customer AND o.debt_period=b.debt_period
            WHERE b.customer=:'customer' ORDER BY b.debt_period DESC LIMIT 250
        """, date=as_of.isoformat(), customer=customer)

    def period(self, as_of: date, customer: str, period: str):
        return self.rows("""SELECT b.customer,b.debt_period,b.opening_vnd,b.movement_vnd,b.balance_vnd,
            o.comparison_status,o.replay_event_count
            FROM ledger.balance_as_of(:'date'::date) b
            LEFT JOIN ledger.opening o ON o.customer=b.customer AND o.debt_period=b.debt_period
            WHERE b.customer=:'customer' AND b.debt_period=:'period' LIMIT 1
        """, date=as_of.isoformat(), customer=customer, period=period)

    def postings(self, as_of: date, customer: str = "", period: str = "", limit: int = 100, offset: int = 0):
        return self.rows("""SELECT posting_id,proposal_id,customer,debt_period,kind,
            signed_amount_vnd,posting_date,event_date,source_ref,evidence_ref,reason,
            maker,checker,original_posting_id,posted_at
            FROM ledger.posting WHERE posting_date <= :'date'::date
              AND (:'customer'='' OR customer=:'customer')
              AND (:'period'='' OR debt_period=:'period')
            ORDER BY posting_date DESC,posting_id DESC
            LIMIT :'limit'::integer OFFSET :'offset'::integer
        """, date=as_of.isoformat(), customer=customer, period=period, limit=limit, offset=offset)

    def proposals(self, status: str = "pending", limit: int = 100):
        return self.rows("""SELECT proposal_id,kind,total_vnd,event_date,posting_date,
            source_ref,evidence_ref,reason,maker,checker,status,created_at,decided_at,
            original_posting_id
            FROM ledger.proposal WHERE (:'status'='' OR status=:'status')
            ORDER BY proposal_id DESC LIMIT :'limit'::integer
        """, status=status, limit=limit)

    def proposal(self, proposal_id: int):
        return self.rows("""SELECT proposal_id,kind,total_vnd,event_date,posting_date,
            source_ref,evidence_ref,reason,maker,checker,status,created_at,decided_at,
            original_posting_id FROM ledger.proposal WHERE proposal_id=:'id'::bigint
        """, id=proposal_id)

    def proposal_lines(self, proposal_id: int):
        return self.rows("""SELECT line_no,customer,debt_period,amount_vnd
            FROM ledger.proposal_line WHERE proposal_id=:'id'::bigint ORDER BY line_no
        """, id=proposal_id)

    def proposal_audit(self, proposal_id: int):
        return self.rows("""SELECT actor,action,at,detail FROM ledger.audit
            WHERE proposal_id=:'id'::bigint ORDER BY audit_id
        """, id=proposal_id)

    def pending_for_customer(self, customer: str):
        return self.rows("""SELECT count(DISTINCT p.proposal_id) AS proposals,
            coalesce(sum(l.amount_vnd),0) AS amount_vnd,
            count(DISTINCT p.proposal_id) FILTER (WHERE p.kind='receipt') AS pending_receipts,
            count(DISTINCT p.proposal_id) FILTER (WHERE p.kind='charge') AS pending_charges
            FROM ledger.proposal p JOIN ledger.proposal_line l USING (proposal_id)
            WHERE p.status='pending' AND l.customer=:'customer'
        """, customer=customer)[0]


class HistoryDB(LedgerDB):
    """Fixed replay snapshot, read separately from the current ledger."""

    def __init__(self, dbname: str = "webdebit_pilot_system", psql: str = "psql"):
        super().__init__(dbname, psql)

    def events_for_customer(self, capture: str, customer: str, first_period: str = "", limit: int = 2001):
        return self.rows("""SELECT e.debt_period,e.event_no,e.posting_date,e.kind,e.amount_vnd,
            e.signed_amount_vnd,e.sheet_gid,e.source_row,r.source_values
            FROM pilot.web_period_event e
            JOIN pilot.web_source_row r ON r.capture_id=e.capture_id
                AND r.sheet_gid=e.sheet_gid AND r.source_row=e.source_row
            WHERE e.capture_id=:'capture' AND e.as_of=DATE '2026-10-13'
                AND e.customer=:'customer'
                AND (:'first_period'='' OR e.debt_period >= :'first_period')
            ORDER BY e.debt_period,e.posting_date,e.event_no
            LIMIT :'limit'::integer
        """, capture=capture, customer=customer, first_period=first_period, limit=limit)
