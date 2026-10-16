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
        data = self._json(f"SELECT coalesce(json_agg(item), '[]'::json) FROM ({sql}) item", values)
        if not isinstance(data, list):
            raise LedgerUnavailable("Invalid PostgreSQL rows")
        return data

    def snapshot(self, **queries: tuple[str, dict]) -> dict[str, list[dict]]:
        """Read several row sets in one SQL statement, so one screen sees one database snapshot.

        Each query is (sql, values); queries share psql variables, so a name must
        carry the same value in every query that uses it.
        """
        values: dict = {}
        parts = []
        for name, (sql, query_values) in queries.items():
            if not re.fullmatch(r"[a-z_]+", name):
                raise ValueError("invalid snapshot name")
            for key, value in query_values.items():
                if key in values and values[key] != value:
                    raise ValueError("conflicting SQL variable")
                values[key] = value
            parts.append(f"'{name}', (SELECT coalesce(json_agg(item), '[]'::json) FROM ({sql}) item)")
        data = self._json(f"SELECT json_build_object({', '.join(parts)})", values)
        if (not isinstance(data, dict) or set(data) != set(queries)
                or not all(isinstance(rows, list) for rows in data.values())):
            raise LedgerUnavailable("Invalid PostgreSQL rows")
        return data

    def _json(self, statement: str, values: dict):
        command = [self.psql, "-X", "-w", "-q", "-A", "-t", "-v", "ON_ERROR_STOP=1"]
        for key, value in values.items():
            if not re.fullmatch(r"[a-z_]+", key):
                raise ValueError("invalid SQL variable")
            command += ["-v", f"{key}={value}"]
        command += ["-d", self.dbname, "-f", "-"]
        try:
            result = subprocess.run(command, input=f"{statement};\n",
                text=True, capture_output=True, encoding="utf-8", timeout=8)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise LedgerUnavailable("PostgreSQL unavailable") from exc
        if result.returncode:
            stderr = result.stderr.lower()
            if "permission denied" in stderr:
                message = "PostgreSQL permission denied"
            elif ("could not connect" in stderr or "connection refused" in stderr
                  or "connection to server" in stderr or "server closed the connection" in stderr
                  or "could not translate host name" in stderr or "timeout expired" in stderr
                  or "no such file or directory" in stderr
                  or "database " in stderr and "does not exist" in stderr):
                message = "PostgreSQL unavailable"
            else:
                message = "PostgreSQL read failed"
            raise LedgerUnavailable(message)
        try:
            return json.loads(result.stdout.strip())
        except json.JSONDecodeError as exc:
            raise LedgerUnavailable("Invalid PostgreSQL result") from exc

    def cutover(self):
        return self.rows("SELECT capture_id, as_of, captured_at_utc, source_spreadsheet_id, "
                         "source_workbook_sha256, engine_sha256, period_report_sha256, "
                         "opening_decision, first_posting_date FROM ledger.cutover LIMIT 1")

    def totals(self, as_of: date):
        return self._rows(self.totals_query(as_of))[0]

    @staticmethod
    def totals_query(as_of: date) -> tuple[str, dict]:
        return ("""SELECT (SELECT count(*) FROM ledger.customer) AS customers,
            (SELECT count(*) FROM ledger.opening) AS opening_periods,
            (SELECT count(*) FROM ledger.opening WHERE comparison_status='NO_BASELINE') AS no_baseline,
            (SELECT coalesce(sum(balance_vnd),0) FROM ledger.opening) AS opening_vnd,
            (SELECT coalesce(sum(movement_vnd),0) FROM ledger.balance_as_of(:'date'::date)) AS movement_vnd,
            (SELECT coalesce(sum(balance_vnd),0) FROM ledger.balance_as_of(:'date'::date)) AS balance_vnd,
            (SELECT count(*) FROM ledger.proposal WHERE status='pending') AS pending,
            (SELECT count(*) FROM ledger.posting WHERE posting_date <= :'date'::date) AS postings
        """, {"date": as_of.isoformat()})

    def customers(self, as_of: date, search: str = ""):
        return self._rows(self.customers_query(as_of, search))

    @staticmethod
    def customers_query(as_of: date, search: str = "") -> tuple[str, dict]:
        return ("""SELECT c.customer,
            CASE WHEN count(b.debt_period)=0 OR count(b.opening_vnd) < count(b.debt_period)
                 THEN NULL ELSE sum(b.opening_vnd) END AS opening_vnd,
            coalesce(sum(b.movement_vnd),0) AS movement_vnd,
            coalesce(sum(b.balance_vnd),0) AS balance_vnd,
            count(b.debt_period) AS periods,
            count(o.debt_period) FILTER (WHERE o.comparison_status='NO_BASELINE') AS no_baseline
            FROM ledger.customer c
            LEFT JOIN ledger.balance_as_of(:'date'::date) b ON b.customer=c.customer
            LEFT JOIN ledger.opening o ON o.customer=b.customer AND o.debt_period=b.debt_period
            WHERE position(lower(:'search') in lower(c.customer)) > 0
            GROUP BY c.customer ORDER BY c.customer
        """, {"date": as_of.isoformat(), "search": search})

    def overview(self, as_of: date, period: str, search: str = ""):
        """Current ledger balances, split around the selected debt period.

        The opening amount of a period is already net of historical replay
        charges and receipts. It must never be labelled as a new charge.
        """
        return self._rows(self.overview_query(as_of, period, search))

    @staticmethod
    def overview_query(as_of: date, period: str, search: str = "") -> tuple[str, dict]:
        return ("""WITH balances AS (
            SELECT * FROM ledger.balance_as_of(:'date'::date)
        ), grouped AS (
            SELECT customer,
                coalesce(sum(balance_vnd) FILTER (WHERE debt_period < :'period'),0) AS carried_vnd,
                sum(opening_vnd) FILTER (WHERE debt_period = :'period') AS period_opening_vnd,
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
            g.period_opening_vnd,
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
        ORDER BY c.customer
        """, {"date": as_of.isoformat(), "period": period, "search": search})

    def periods(self, as_of: date, customer: str):
        return self._rows(self.periods_query(as_of, customer))

    @staticmethod
    def periods_query(as_of: date, customer: str) -> tuple[str, dict]:
        return ("""SELECT b.customer,b.debt_period,b.opening_vnd,b.movement_vnd,b.balance_vnd,
            o.comparison_status,o.replay_event_count
            FROM ledger.balance_as_of(:'date'::date) b
            LEFT JOIN ledger.opening o ON o.customer=b.customer AND o.debt_period=b.debt_period
            WHERE b.customer=:'customer' ORDER BY b.debt_period DESC
        """, {"date": as_of.isoformat(), "customer": customer})

    def period(self, as_of: date, customer: str, period: str):
        return self._rows(self.period_query(as_of, customer, period))

    @staticmethod
    def period_query(as_of: date, customer: str, period: str) -> tuple[str, dict]:
        return ("""SELECT b.customer,b.debt_period,b.opening_vnd,b.movement_vnd,b.balance_vnd,
            o.comparison_status,o.replay_event_count
            FROM ledger.balance_as_of(:'date'::date) b
            LEFT JOIN ledger.opening o ON o.customer=b.customer AND o.debt_period=b.debt_period
            WHERE b.customer=:'customer' AND b.debt_period=:'period' LIMIT 1
        """, {"date": as_of.isoformat(), "customer": customer, "period": period})

    def postings(self, as_of: date, customer: str = "", period: str = "", limit: int = 100, offset: int = 0):
        return self._rows(self.postings_query(as_of, customer, period, limit, offset))

    @staticmethod
    def postings_query(as_of: date, customer: str = "", period: str = "", limit: int = 100, offset: int = 0) -> tuple[str, dict]:
        return ("""SELECT posting_id,proposal_id,customer,debt_period,kind,
            signed_amount_vnd,posting_date,event_date,source_ref,evidence_ref,reason,
            maker,checker,original_posting_id,posted_at
            FROM ledger.posting WHERE posting_date <= :'date'::date
              AND (:'customer'='' OR customer=:'customer')
              AND (:'period'='' OR debt_period=:'period')
            ORDER BY posting_date DESC,posting_id DESC
            LIMIT :'limit'::integer OFFSET :'offset'::integer
        """, {"date": as_of.isoformat(), "customer": customer, "period": period, "limit": limit, "offset": offset})

    def proposals(self, status: str = "pending", limit: int = 100):
        return self.rows("""SELECT proposal_id,kind,total_vnd,event_date,posting_date,
            source_ref,evidence_ref,reason,maker,checker,status,created_at,decided_at,
            original_posting_id
            FROM ledger.proposal WHERE (:'status'='' OR status=:'status')
            ORDER BY proposal_id DESC LIMIT :'limit'::integer
        """, status=status, limit=limit)

    def proposal(self, proposal_id: int):
        return self._rows(self.proposal_query(proposal_id))

    @staticmethod
    def proposal_query(proposal_id: int) -> tuple[str, dict]:
        return ("""SELECT proposal_id,kind,total_vnd,event_date,posting_date,
            source_ref,evidence_ref,reason,maker,checker,status,created_at,decided_at,
            original_posting_id FROM ledger.proposal WHERE proposal_id=:'id'::bigint
        """, {"id": proposal_id})

    def proposal_lines(self, proposal_id: int):
        return self._rows(self.proposal_lines_query(proposal_id))

    @staticmethod
    def proposal_lines_query(proposal_id: int) -> tuple[str, dict]:
        return ("""SELECT line_no,customer,debt_period,amount_vnd
            FROM ledger.proposal_line WHERE proposal_id=:'id'::bigint ORDER BY line_no
        """, {"id": proposal_id})

    def proposal_audit(self, proposal_id: int):
        return self._rows(self.proposal_audit_query(proposal_id))

    @staticmethod
    def proposal_audit_query(proposal_id: int) -> tuple[str, dict]:
        return ("""SELECT actor,action,at,detail FROM ledger.audit
            WHERE proposal_id=:'id'::bigint ORDER BY audit_id
        """, {"id": proposal_id})

    def pending_for_customer(self, customer: str):
        return self._rows(self.pending_for_customer_query(customer))[0]

    @staticmethod
    def pending_for_customer_query(customer: str) -> tuple[str, dict]:
        return ("""SELECT count(DISTINCT p.proposal_id) AS proposals,
            coalesce(sum(l.amount_vnd),0) AS amount_vnd,
            count(DISTINCT p.proposal_id) FILTER (WHERE p.kind='receipt') AS pending_receipts,
            count(DISTINCT p.proposal_id) FILTER (WHERE p.kind='charge') AS pending_charges
            FROM ledger.proposal p JOIN ledger.proposal_line l USING (proposal_id)
            WHERE p.status='pending' AND l.customer=:'customer'
        """, {"customer": customer})

    def _rows(self, query: tuple[str, dict]) -> list[dict]:
        sql, values = query
        return self.rows(sql, **values)

    # Each screen reads every ledger row set it shows in one statement (one snapshot),
    # so a concurrent approval cannot make its totals and details disagree.
    def overview_screen(self, as_of: date, period: str, search: str = "") -> tuple[dict, list[dict]]:
        data = self.snapshot(totals=self.totals_query(as_of),
                             customers=self.overview_query(as_of, period, search))
        return data["totals"][0], data["customers"]

    def customer_screen(self, as_of: date, customer: str, postings_limit: int = 1001) -> dict:
        data = self.snapshot(customers=self.customers_query(as_of, customer),
                             periods=self.periods_query(as_of, customer),
                             pending=self.pending_for_customer_query(customer),
                             postings=self.postings_query(as_of, customer, limit=postings_limit))
        return {**data, "pending": data["pending"][0]}

    def period_screen(self, as_of: date, customer: str, period: str) -> tuple[list[dict], list[dict]]:
        data = self.snapshot(period=self.period_query(as_of, customer, period),
                             postings=self.postings_query(as_of, customer, period))
        return data["period"], data["postings"]

    def proposal_screen(self, proposal_id: int) -> tuple[list[dict], list[dict], list[dict]]:
        data = self.snapshot(proposal=self.proposal_query(proposal_id),
                             lines=self.proposal_lines_query(proposal_id),
                             audits=self.proposal_audit_query(proposal_id))
        return data["proposal"], data["lines"], data["audits"]


# Blank text is unclassified, never a value of its own: btrim set matches
# HistoryDB._M1_WHITESPACE (space, tab, LF, CR, FF, VT).
_M1_TRIM_SQL = "' ' || chr(9) || chr(10) || chr(13) || chr(12) || chr(11)"


def _m1_group(column: str, alias: str | None = None) -> str:
    return f"CASE WHEN NULLIF(btrim({column}, {_M1_TRIM_SQL}),'') IS NULL THEN NULL ELSE {column} END AS {alias or column + '_group'}"


def _m1_match(name: str, column: str, group: str) -> str:
    """Filter predicate for one dimension: all / unclassified / exact (see HistoryDB._m1_filter)."""
    return (f"(:'{name}_mode'='all'"
            f" OR (:'{name}_mode'='unclassified' AND {group} IS NULL)"
            f" OR (:'{name}_mode'='exact' AND {column}=:'{name}'))")


_M1_CLASSIFIED_CTE = f"""classified AS (
                SELECT d.*, {_m1_group("d.customer", "customer_group")},
                    {_m1_group("d.debt_period", "period_group")}, {_m1_group("d.code", "code_group")}
                FROM pilot.m1_exception_detail d
                WHERE d.capture_id=:'capture' AND d.as_of=:'as_of'::date
            ), filtered AS (
                SELECT * FROM classified
                WHERE {_m1_match("customer", "customer", "customer_group")}
                  AND {_m1_match("period", "debt_period", "period_group")}
                  AND {_m1_match("code", "code", "code_group")}
            )"""


def _m1_group_ctes() -> str:
    return ", ".join(f"""by_{alias} AS (
                SELECT {alias}_group AS {alias},
                    count(*) AS exception_count,
                    count(DISTINCT (capture_id,as_of,sheet_gid,source_row)) AS source_row_count,
                    count(DISTINCT (capture_id,as_of,sheet_gid,source_row))
                        FILTER (WHERE tab_title=:'trip_tab') AS trip_source_row_count
                FROM filtered GROUP BY {alias}_group
            )""" for alias in ("customer", "period", "code"))


def _m1_group_json(alias: str) -> str:
    return f"""coalesce((SELECT jsonb_agg(jsonb_build_object(
                    '{alias}', {alias}, 'group_status', CASE WHEN {alias} IS NULL THEN 'UNCLASSIFIED' ELSE 'CLASSIFIED' END,
                    'exception_count', exception_count, 'source_row_count', source_row_count,
                    'trip_source_row_count', trip_source_row_count) ORDER BY {alias} NULLS LAST) FROM by_{alias}), '[]'::jsonb) AS by_{alias}"""


class HistoryDB(LedgerDB):
    """Fixed replay snapshot, read separately from the current ledger."""

    _M1_WHITESPACE = " \t\n\r\f\v"

    def __init__(self, dbname: str = "webdebit_pilot_system", psql: str = "psql",
                 cutover: dict | None = None):
        super().__init__(dbname, psql)
        self.expected_cutover = cutover

    def _m1_provenance(self) -> dict:
        """Validate M1 identity and hashes against the independent ledger cutover row."""
        cutover = self.expected_cutover
        if not isinstance(cutover, dict):
            raise LedgerUnavailable("M1 cutover metadata unavailable")
        capture = cutover.get("capture_id")
        as_of_value = cutover.get("as_of")
        try:
            as_of = as_of_value.isoformat() if isinstance(as_of_value, date) else date.fromisoformat(as_of_value).isoformat()
        except (TypeError, ValueError):
            raise LedgerUnavailable("M1 cutover snapshot date invalid") from None
        hashes = (cutover.get("source_workbook_sha256"), cutover.get("engine_sha256"))
        if not isinstance(capture, str) or not capture or "\x00" in capture:
            raise LedgerUnavailable("M1 cutover capture missing")
        if any(not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value) for value in hashes):
            raise LedgerUnavailable("M1 cutover source hash missing or invalid")

        rows = self.rows("""SELECT capture_id, as_of, source_workbook_sha256,
                engine_sha256, baseline_date
            FROM pilot.m1_provenance
            WHERE capture_id=:'capture' AND as_of=:'as_of'::date
        """, capture=capture, as_of=as_of)
        if len(rows) != 1:
            state = "missing" if not rows else "duplicate"
            raise LedgerUnavailable(f"M1 provenance {state} for cutover")
        provenance = rows[0]
        if (provenance.get("capture_id") != capture
                or provenance.get("as_of") != as_of
                or any(not isinstance(provenance.get(key), str)
                       or not re.fullmatch(r"[0-9a-f]{64}", provenance[key])
                       for key in ("source_workbook_sha256", "engine_sha256"))):
            raise LedgerUnavailable("M1 provenance identity or source hash missing or invalid")
        if (provenance["source_workbook_sha256"], provenance["engine_sha256"]) != hashes:
            raise LedgerUnavailable("M1 provenance source hashes do not match cutover")
        baseline_date = provenance.get("baseline_date")
        return {
            "capture_id": capture,
            "as_of": as_of,
            "source_workbook_sha256": provenance["source_workbook_sha256"],
            "engine_sha256": provenance["engine_sha256"],
            "baseline_date": baseline_date,
            "baseline_status": "AVAILABLE" if baseline_date == as_of else "NO_BASELINE",
        }

    @staticmethod
    def _m1_filter(value: str | None, name: str) -> tuple[str, str]:
        if value is None:
            return "all", ""
        if not isinstance(value, str):
            raise ValueError(f"{name} filter must be text or None")
        if "\x00" in value:
            raise ValueError(f"{name} filter contains NUL")
        return ("unclassified", "") if not value.strip(HistoryDB._M1_WHITESPACE) else ("exact", value)

    def _m1_filter_args(self, customer, period, code) -> dict:
        args = {}
        for name, value in (("customer", customer), ("period", period), ("code", code)):
            args[f"{name}_mode"], args[name] = self._m1_filter(value, name)
        return args

    def exception_summary(self, customer: str | None = None, period: str | None = None,
                          code: str | None = None) -> dict:
        """Return filtered counts and customer/period/code groups for the cutover snapshot."""
        filters = self._m1_filter_args(customer, period, code)
        provenance = self._m1_provenance()
        result = self.rows(f"""WITH {_M1_CLASSIFIED_CTE}, {_m1_group_ctes()}
            SELECT count(*) AS exception_count,
                count(DISTINCT (capture_id,as_of,sheet_gid,source_row)) AS source_row_count,
                count(DISTINCT (capture_id,as_of,sheet_gid,source_row))
                    FILTER (WHERE tab_title=:'trip_tab') AS trip_source_row_count,
                {", ".join(_m1_group_json(alias) for alias in ("customer", "period", "code"))}
            FROM filtered
        """, capture=provenance["capture_id"], as_of=provenance["as_of"], **filters, trip_tab="Chuyến hàng")[0]
        return {**provenance, **result}

    def exception_page(self, customer: str | None = None, period: str | None = None,
                       code: str | None = None, page: int = 1, page_size: int = 50) -> dict:
        """Return one stable page; empty-string filters select unclassified rows."""
        if type(page) is not int or page < 1:
            raise ValueError("page must be a positive integer")
        if type(page_size) is not int or not 1 <= page_size <= 50:
            raise ValueError("page_size must be between 1 and 50")
        offset = (page - 1) * page_size
        if offset > 2**63 - 1:
            raise ValueError("page offset is too large")
        filters = self._m1_filter_args(customer, period, code)
        provenance = self._m1_provenance()
        result = self.rows(f"""WITH {_M1_CLASSIFIED_CTE}, selected AS (
                SELECT * FROM filtered
                ORDER BY sheet_gid, source_row, code NULLS FIRST, exception_no
                LIMIT :'limit'::integer OFFSET :'offset'::bigint
            )
            SELECT jsonb_build_object(
                'total_results', (SELECT count(*) FROM filtered),
                'items', coalesce((SELECT jsonb_agg(jsonb_build_object(
                    'exception_no', exception_no, 'code', code, 'status', status,
                    'resolution_status', resolution_status, 'customer', customer,
                    'customer_group', customer_group,
                    'customer_group_status', CASE WHEN customer_group IS NULL THEN 'UNCLASSIFIED' ELSE 'CLASSIFIED' END,
                    'period', debt_period, 'period_group', period_group,
                    'period_group_status', CASE WHEN period_group IS NULL THEN 'UNCLASSIFIED' ELSE 'CLASSIFIED' END,
                    'code_group', code_group,
                    'code_group_status', CASE WHEN code_group IS NULL THEN 'UNCLASSIFIED' ELSE 'CLASSIFIED' END,
                    'detail', detail, 'tab_title', tab_title,
                    'source_identity', jsonb_build_object('capture_id',capture_id,'as_of',as_of,
                        'sheet_gid',sheet_gid,'source_row',source_row),
                    'row_sha256', row_sha256, 'source_url', source_url)
                    ORDER BY sheet_gid, source_row, code NULLS FIRST, exception_no) FROM selected), '[]'::jsonb)
            ) AS response
        """, capture=provenance["capture_id"], as_of=provenance["as_of"], **filters,
            limit=page_size, offset=offset)[0]["response"]
        return {**provenance, "page": page, "page_size": page_size, **result}

    def customer_reconciliations(self, customer: str | None = None) -> dict:
        """Batch customer reconciliation; old-book delta is returned once per customer."""
        filters = self._m1_filter_args(customer, None, None)
        provenance = self._m1_provenance()
        result = self.rows(f"""WITH classified AS (
                SELECT d.*, {_m1_group("d.customer", "customer_group")}
                FROM pilot.m1_customer_diff d
                WHERE d.capture_id=:'capture' AND d.as_of=:'as_of'::date
            ), scoped AS (
                SELECT customer, result, old_book_delta_vnd FROM classified
                WHERE {_m1_match("customer", "customer", "customer_group")}
            )
            SELECT count(*) AS total_results,
                coalesce(jsonb_agg(jsonb_build_object(
                    'customer', customer, 'reconciliation_status', result,
                    'old_book_delta_vnd', old_book_delta_vnd,
                    'old_book_delta_status', CASE
                        WHEN result='NO_BASELINE' THEN 'NO_BASELINE'
                        WHEN old_book_delta_vnd IS NULL THEN 'MISSING'
                        ELSE 'AVAILABLE' END)
                    ORDER BY customer), '[]'::jsonb) AS items
            FROM scoped
        """, capture=provenance["capture_id"], as_of=provenance["as_of"], **filters)[0]
        return {
            **provenance,
            **result,
            "reconciliation_status": "AVAILABLE" if provenance["baseline_status"] == "AVAILABLE" else "NO_BASELINE",
        }

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
