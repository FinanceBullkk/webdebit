"""Shared disposable PostgreSQL setup and fixtures for the V7 backend harness."""

from __future__ import annotations

import errno
import json
import queue
import shutil
import subprocess
import threading
from pathlib import Path

from docker_exec_channel import run_docker_exec

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = ROOT / "specs" / "v7-backend" / "schema-draft.sql"
FUNCTIONS = ROOT / "cong-no-web-handoff" / "tools" / "v7_backend_functions.sql"
IMAGE = "postgres:18.6@sha256:74935e72241653ca55e0414067e6d8763aceb8a810eb51b452253ec3dcfc4336"
DATABASE = "webdebit_v7_test"
LABEL_TEST = "codex.test"
LABEL_RUN = "codex.run"
LABEL_VALUE = "webdebit-v7-backend"


class HarnessError(RuntimeError):
    pass


def run(args: list[str], *, input_text: str | None = None, check: bool = True,
        timeout: float = 30, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    try:
        p = run_docker_exec(args, input_text=input_text, timeout=timeout)
        if p is None:
            p = subprocess.run(args, input=input_text, text=True, encoding="utf-8",
                               errors="replace", capture_output=True, timeout=timeout, cwd=cwd, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise HarnessError(f"command unavailable/timed out: {args[:3]}: {exc}") from exc
    if check and p.returncode:
        raise HarnessError(f"command failed ({p.returncode}): {args[:3]}: {p.stderr[-1500:]}")
    return p


def require(condition: bool, reason: str) -> None:
    if not condition:
        raise HarnessError(reason)


def parse_blocker_row(row: str) -> tuple[int, set[int]]:
    """Parse one pg_stat_activity row, including PostgreSQL soft blockers.

    >>> parse_blocker_row('2402|2401,2399')
    (2402, {2401, 2399})
    >>> parse_blocker_row('2402|')
    (2402, set())
    """
    pid, blocked_by = row.split("|", 1)
    return int(pid), {int(value) for value in blocked_by.split(",") if value}


def case(case_id: str, label: str, title: str, check=None, *, functions=(), open_reason="") -> dict:
    return {"id": case_id, "label": label, "title": title, "check": check,
            "functions": functions, "open_reason": open_reason}


class Pg:
    def psql_command(self) -> list[str]:
        """Constructor-only direct adapter prefix for this disposable container."""
        return ["docker", "exec", "-i", self.name, "psql"]

    def __init__(self, name: str, run_id: str):
        self.name = name
        self.run_id = run_id
        self.env = ["--env", f"PGAPPNAME=codex_v7_{run_id}", "--env", "PGOPTIONS=-c statement_timeout=15000 -c lock_timeout=12000"]

    def sql(self, sql: str, *, user: str = "postgres", check: bool = True,
            database: str = DATABASE) -> subprocess.CompletedProcess[str]:
        return run(["docker", "exec", "-i", *self.env, self.name, "psql", "-X", "-qAt",
                    "-v", "ON_ERROR_STOP=1", "-v", "VERBOSITY=verbose", "-U", user,
                    "-d", database], input_text=sql.rstrip().rstrip(";") + ";\n", check=check)

    def value(self, sql: str, *, user: str = "postgres") -> str:
        return self.sql(sql, user=user).stdout.strip()

    def true(self, sql: str, reason: str) -> None:
        require(self.value("SELECT CASE WHEN (" + sql + ") THEN 'ok' ELSE 'bad' END") == "ok", reason)

    def rejects(self, sql: str, *, user: str = "postgres", message: str = "") -> None:
        p = self.sql(sql, user=user, check=False)
        require(p.returncode != 0 and (not message or message in p.stderr),
                f"statement unexpectedly accepted or wrong error: {p.stdout} {p.stderr[-700:]}")


def lit(value) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def actor_sql(sql: str, actor: str = "harness", *, search_path: str = "") -> str:
    return "BEGIN; SET LOCAL sokhach.actor = " + lit(actor) + "; " + search_path + sql + "; COMMIT"


def call(pg: Pg, name: str, *args, actor: str = "harness") -> dict:
    values = ",".join("NULL" if x is None else lit(x) for x in args)
    result = json.loads(pg.value(actor_sql(f"SELECT sokhach.{name}({values})", actor)))
    if name == "get_ledger":
        for month in result.get("months", []):
            require(int(month["prior_months_vnd"]) + int(month["charges_vnd"]) - int(month["received_vnd"])
                    == int(month["end_of_month_vnd"]), f"monthly identity failed: {month}")
    return result


def reject_call(pg: Pg, name: str, *args, error: str, actor: str = "harness") -> None:
    values = ",".join("NULL" if x is None else lit(x) for x in args)
    pg.rejects(actor_sql(f"SELECT sokhach.{name}({values})", actor), message=error)


def version(pg: Pg, customer: int) -> int:
    return int(pg.value(f"SELECT version FROM sokhach.customer WHERE id={customer}"))


def fixture_open_month(pg: Pg, customer: int, month: str) -> None:
    # Disposable contract fixture; lock-command audit is tested separately.
    pg.sql("INSERT INTO sokhach.month_state(customer_id,month,locked,changed_by) "
           f"VALUES ({customer},{lit(month)},false,'harness') "
           "ON CONFLICT (customer_id,month) DO UPDATE SET locked=false,changed_by='harness'")


def new_book(pg: Pg, *amounts: tuple[str, int]) -> int:
    """Harness-only opening: no import/verification acceptance claim."""
    customer = int(pg.value("INSERT INTO sokhach.customer(name) VALUES ('FAKE CONTRACT') RETURNING id"))
    total = sum(amount for _, amount in amounts)
    cutover = int(pg.value("INSERT INTO sokhach.cutover(name,source,source_sha256,frozen_at,control_total_vnd,created_by) "
        f"VALUES ('FAKE CONTRACT','anonymous',repeat('a',64),now(),{total},'harness') RETURNING id"))
    pg.sql("INSERT INTO sokhach.cutover_customer(customer_id,cutover_id,expected_control_total_vnd,report_sha256,"
        "source_rows,imported_rows,quarantined_rows,skipped_with_reason_rows,unresolved_exceptions) "
        f"VALUES ({customer},{cutover},{total},repeat('a',64),{len(amounts)},{len(amounts)},0,0,0)")
    event = int(pg.value("INSERT INTO sokhach.event(customer_id,kind,actor,\"before\",\"after\",cutover_id) "
        f"VALUES ({customer},'import','harness','{{}}',jsonb_build_object('cutover',{cutover}),{cutover}) RETURNING id"))
    for n, (month, amount) in enumerate(amounts, 1):
        pg.sql("INSERT INTO sokhach.opening_balance(customer_id,cutover_id,debt_month,amount_vnd,"
            f"source_tab,source_row,created_by_event) VALUES ({customer},{cutover},{lit(month)},{amount},'FAKE',{n},{event})")
    pg.sql(f"UPDATE sokhach.cutover_customer SET status='verified' WHERE customer_id={customer}")
    pg.sql(f"UPDATE sokhach.cutover SET status='verified' WHERE id={cutover}")
    pg.sql(f"UPDATE sokhach.cutover SET status='active' WHERE id={cutover}")
    pg.sql(f"UPDATE sokhach.cutover_customer SET status='active' WHERE customer_id={customer}")
    pg.sql(f"INSERT INTO sokhach.baseline_trip_ref VALUES ({cutover},'FAKE-REF','FAKE-REF',NULL)")
    return customer


def cutover_book(pg: Pg, total: int, *, cutover: int | None = None) -> tuple[int, int]:
    customer = int(pg.value("INSERT INTO sokhach.customer(name) VALUES ('FAKE IMPORT') RETURNING id"))
    if cutover is None:
        cutover = int(pg.value("INSERT INTO sokhach.cutover(name,source,source_sha256,frozen_at,control_total_vnd,created_by) "
            f"VALUES ('FAKE IMPORT','anonymous',repeat('a',64),now(),{total},'harness') RETURNING id"))
    return customer, cutover


def import_data(amounts: list[int], *, buckets: list[int] | None = None,
                standards: list[int] | None = None, charges: list[int] | None = None,
                receipts: list[int] | None = None, opening_anchor: int = 0,
                flags: list[list[str]] | None = None) -> tuple[str, str, str]:
    buckets = amounts if buckets is None else buckets
    standards = buckets if standards is None else standards
    flags = [[] for _ in amounts] if flags is None else flags
    dates = [f"2026-{n:02d}-01" for n in range(1, len(amounts) + 1)]
    openings = [{"debt_month": month, "amount_vnd": amount, "source_tab": "FAKE",
                 "source_row": n} for n, (month, amount) in enumerate(zip(dates, amounts, strict=True), 1)]
    checks = []
    charges = standards if charges is None else charges
    receipts = [0] * len(amounts) if receipts is None else receipts
    cumulative = opening_anchor
    replay = 0
    for month, bucket, standard, charge, receipt, codes in zip(
            dates, buckets, standards, charges, receipts, flags, strict=True):
        cumulative += charge - receipt
        replay += bucket
        checks.append({"debt_month": month, "source_cumulative_vnd": cumulative,
                       "opening_anchor_vnd": opening_anchor,
                       "source_charge_vnd": charge, "source_receipt_vnd": receipt,
                       "replay_cumulative_vnd": replay, "bucket_vnd": bucket,
                       "standard_bucket_vnd": standard,
                       "standard_source_ref": f"FAKE anchors before/after {month}",
                       "standard_source_sha256": "a" * 64,
                       "source_evidence_sha256": "b" * 64,
                       "exception_codes": codes})
    return tuple(json.dumps(value) for value in (openings, [], checks))


def import_book(pg: Pg, customer: int, cutover: int, amounts: list[int], key: str,
                *, buckets: list[int] | None = None,
                flags: list[list[str]] | None = None, total: int | None = None) -> dict:
    openings, legacy, checks = import_data(amounts, buckets=buckets, flags=flags)
    return call(pg, "import_cutover", customer, version(pg, customer), key, cutover,
                openings, legacy, checks, sum(amounts) if total is None else total, "a" * 64)


def months(pg: Pg, customer: int) -> list[tuple[str, str, str]]:
    ledger = call(pg, "get_ledger", customer)
    require(ledger["status"] == "active", "active fixture returned no baseline")
    return [(row["month"][:7], row["outstanding_vnd"], row["end_of_month_vnd"])
            for row in ledger["months"]]


def allocations(pg: Pg, customer: int, pid: str) -> list[tuple[str, str, str]]:
    rows = pg.value("SELECT coalesce(json_agg(json_build_array(l.debt_month::text,l.kind,l.amount_vnd::text) "
        "ORDER BY l.debt_month,CASE l.kind WHEN 'debt' THEN 0 ELSE 1 END,l.id),'[]'::json)::text FROM sokhach.receipt_line l "
        "JOIN sokhach.receipt r ON r.id=l.receipt_id WHERE "
        f"r.customer_id={customer} AND r.pid={lit(pid)} AND l.superseded_by_event IS NULL")
    return [tuple(row) for row in json.loads(rows)]


def assert_allocations(pg: Pg, customer: int) -> None:
    pg.true("NOT EXISTS (SELECT 1 FROM sokhach.receipt r LEFT JOIN sokhach.receipt_line l "
        "ON l.receipt_id=r.id AND l.superseded_by_event IS NULL "
        f"WHERE r.customer_id={customer} GROUP BY r.id,r.amount_vnd,r.voided_on "
        "HAVING (r.voided_on IS NULL AND (count(l.id)=0 OR sum(l.amount_vnd)<>r.amount_vnd)) "
        "OR (r.voided_on IS NOT NULL AND count(l.id)<>0))", "receipt allocation sum/current rows wrong")


def trip_json(amount: str | None = "100", *, container: str = "FAKE-C", month: str = "2026-01-01",
              shipper: str | None = None) -> str:
    row = {"container": container, "carrier": "FAKE", "date": f"01/{month[5:7]}/{month[:4]}",
           "from": "FAKE-A", "to": "FAKE-B", "unitPriceVnd": amount,
           "otherFeeVnd": None, "note": "", "src": "FAKE"}
    if shipper is not None:
        row["shipper"] = shipper
    return json.dumps([row], ensure_ascii=False)


def run_node(code: str) -> dict:
    require(shutil.which("node") is not None, "Node unavailable for model parity")
    return json.loads(run(["node", "-e", code], timeout=30, cwd=ROOT).stdout)


class PsqlSession:
    """One persistent docker exec / psql connection for lock observations."""

    def __init__(self, pg: Pg, app_name: str):
        self.proc = subprocess.Popen(
            ["docker", "exec", "-i", "--env", f"PGAPPNAME={app_name}", pg.name,
             "psql", "-X", "-qAt", "-v", "ON_ERROR_STOP=1", "-U", "postgres", "-d", DATABASE],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8", errors="replace", bufsize=1)
        self.lines: queue.Queue[str | None] = queue.Queue()
        threading.Thread(target=self._pump, daemon=True).start()

    def _pump(self) -> None:
        assert self.proc.stdout is not None
        for line in self.proc.stdout:
            self.lines.put(line.strip())
        self.lines.put(None)

    def send(self, sql: str) -> None:
        assert self.proc.stdin is not None
        try:
            self.proc.stdin.write(sql.rstrip(";") + ";\n")
            self.proc.stdin.flush()
        except OSError as exc:
            raise HarnessError(f"psql session input failed: {exc}") from exc

    def line(self, timeout: float = 10) -> str:
        try:
            value = self.lines.get(timeout=timeout)
        except queue.Empty as exc:
            raise HarnessError("psql session response timeout") from exc
        require(value is not None, "psql session ended while lock held")
        return value

    def close(self) -> None:
        """EOF rolls back open transactions, even when ON_ERROR_STOP races exit.

        >>> from unittest.mock import Mock
        >>> session = object.__new__(PsqlSession)
        >>> session.proc = Mock()
        >>> session.proc.stdin.close.side_effect = OSError(errno.EINVAL, 'closed pipe')
        >>> session.close()
        >>> session.proc.wait.assert_called_once_with(timeout=10)
        >>> session.proc.stdin.write.assert_not_called()
        """
        # No ROLLBACK write: psql may already have exited after an expected error.
        # Windows reports that race as EINVAL rather than BrokenPipeError.
        if self.proc.stdin is not None:
            try:
                self.proc.stdin.close()
            except OSError as exc:
                if exc.errno not in (errno.EPIPE, errno.EINVAL, errno.EBADF):
                    raise
        try:
            self.proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            self.proc.wait(timeout=5)


def seed(pg: Pg, *, references=True) -> None:
    sha = "a" * 64
    pg.sql(f"""INSERT INTO sokhach.customer(name) VALUES ('FAKE V7') ;
INSERT INTO sokhach.cutover(name,source,source_sha256,frozen_at,control_total_vnd,created_by)
VALUES ('FAKE CUTOVER','anonymous fixture','{sha}',now(),300,'test');
INSERT INTO sokhach.cutover_customer(customer_id,cutover_id,expected_control_total_vnd,report_sha256,
 source_rows,imported_rows,quarantined_rows,skipped_with_reason_rows,unresolved_exceptions)
VALUES (1,1,300,'{sha}',2,2,0,0,0);
INSERT INTO sokhach.event(customer_id,kind,actor,"before","after",idempotency_key,cutover_id)
VALUES (1,'import','test','{{}}','{{"cutover":1}}','fake-import',1);
INSERT INTO sokhach.cutover_month_check(customer_id,cutover_id,debt_month,opening_anchor_vnd,source_cumulative_vnd,
 replay_cumulative_vnd,bucket_vnd,standard_bucket_vnd,source_charge_vnd,source_receipt_vnd,
 standard_source_ref,standard_source_sha256,source_evidence_sha256)
VALUES (1,1,'2026-01-01',0,100,100,100,100,100,0,'fake-anchor-0-and-1','{sha}','{sha}'),
       (1,1,'2026-02-01',0,300,300,200,200,200,0,'fake-anchor-1-and-2','{sha}','{sha}');
INSERT INTO sokhach.opening_balance(customer_id,cutover_id,debt_month,amount_vnd,source_tab,source_row,created_by_event)
VALUES (1,1,'2026-01-01',100,'FAKE',1,1),(1,1,'2026-02-01',200,'FAKE',2,1);
INSERT INTO sokhach.legacy_row(customer_id,cutover_id,debt_month,kind,display,source_total_vnd,source_tab,source_row,created_by_event)
VALUES (1,1,'2026-01-01','trip','{{"fake":true,"container":"FAKE","date":"2026-01-01"}}',999,'FAKE',3,1);
""")
    if references:
        pg.sql("INSERT INTO sokhach.baseline_trip_ref VALUES (1,'FAKE-REF','FAKE-REF',NULL)")

NHAP_MIGRATION = ROOT / "cong-no-web-handoff/tools/migrations/2026-10-22-v7-nhap-sheet.sql"

REVIEW_MIGRATION = ROOT / "cong-no-web-handoff/tools/migrations/2026-10-22-v7-trip-review.sql"
MH_MIGRATION = ROOT / "cong-no-web-handoff/tools/migrations/2026-10-23-v7-mat-hang.sql"
SHEET_MIGRATION = ROOT / "cong-no-web-handoff/tools/migrations/2026-10-24-v7-sheet-cross-customer.sql"

DASHBOARD_MIGRATION = ROOT / "cong-no-web-handoff/tools/migrations/2026-10-24-v7-dashboard.sql"
LOCKED_TRIP_MIGRATION = ROOT / "cong-no-web-handoff/tools/migrations/2026-10-24-v7-locked-trip-edit.sql"
MATRIX_MIGRATION = ROOT / "cong-no-web-handoff/tools/migrations/2026-10-25-v7-receivables-matrix.sql"
DETAIL_MIGRATION = ROOT / "cong-no-web-handoff/tools/migrations/2026-10-26-v7-receivables-detail.sql"
SYNC_MIGRATION = ROOT / "cong-no-web-handoff/tools/migrations/2026-10-27-v7-shipper-write-sync.sql"
LEGACY_RECEIPT_MIGRATION = ROOT / "cong-no-web-handoff/tools/migrations/2026-10-28-v7-legacy-receipt-delete.sql"
DA_THU_MIGRATION = ROOT / "cong-no-web-handoff/tools/migrations/2026-10-28-v7-da-thu-theo-ngay-thu.sql"
SHEET_CONFLICT_MIGRATION = ROOT / "cong-no-web-handoff/tools/migrations/2026-10-25-v7-sheet-conflict.sql"
SHEET_CONFLICT_DATE_MIGRATION = ROOT / "cong-no-web-handoff/tools/migrations/2026-10-27-v7-sheet-conflict-date-booking.sql"

def inspect_owned(name: str, volume: str, run_id: str, expected_id: str | None = None) -> str | None:
    p = run(["docker", "ps", "--all", "--quiet", "--no-trunc", "--filter", f"name=^/{name}$"], check=False)
    require(p.returncode == 0, "cannot inspect run container")
    ids = p.stdout.split()
    if not ids:
        return None
    require(len(ids) == 1, "multiple containers with exact run name")
    info = json.loads(run(["docker", "inspect", ids[0]]).stdout)[0]
    labels = info.get("Config", {}).get("Labels") or {}
    mounts = [m for m in info.get("Mounts", []) if m.get("Name") == volume and m.get("Destination") == "/var/lib/postgresql"]
    require(info.get("Id") == ids[0] and (expected_id is None or ids[0] == expected_id)
            and info.get("Name") == "/" + name and labels.get(LABEL_TEST) == LABEL_VALUE
            and labels.get(LABEL_RUN) == run_id and len(mounts) == 1
            and info.get("HostConfig", {}).get("NetworkMode") == "none"
            and not info.get("HostConfig", {}).get("PortBindings"),
            "run container ID/name/labels/volume mismatch")
    return ids[0]


def inspect_volume(volume: str, run_id: str) -> None:
    info = json.loads(run(["docker", "volume", "inspect", volume]).stdout)[0]
    labels = info.get("Labels") or {}
    require(info.get("Name") == volume and labels.get(LABEL_TEST) == LABEL_VALUE
            and labels.get(LABEL_RUN) == run_id, "run volume identity/labels mismatch")
