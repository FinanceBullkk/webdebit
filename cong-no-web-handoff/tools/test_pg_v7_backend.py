#!/usr/bin/env python3
"""V7 contract checks in one disposable PostgreSQL container with fake rows."""

from __future__ import annotations

import argparse
import errno
import hashlib
import json
import queue
import re
import shutil
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path

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


# IDs retain section 7 numbering; suffixes split schema checks from missing commands.
CASES = [
    case("DASH.01", "BEHAVIOR", "Dashboard returns stable empty contract", check="dashboard", functions=("get_dashboard",)),
    case("CSM.01", "BEHAVIOR", "Optional reference, edit, duplicate warning and idempotency", check="csm_reference", functions=("record_receipt", "edit_receipt_meta")),
    case("CSM.02", "BEHAVIOR", "Every month lock command has one atomic audit event", check="csm_locks", functions=("set_month_lock", "get_ledger")),
    case("CSM.03", "BEHAVIOR", "Atomic CSM migration preserves old rows and retries", check="csm_migration", functions=("record_receipt", "set_month_lock")),
    case("7.24", "BEHAVIOR", "M2-11 duplicate quarantine and money guards", check="dedup", functions=("paste_trips",)),
    case("7.25", "BEHAVIOR", "NEWTRIP-01 review: confirm/reject pending trip with reason", check="trip_review",
         functions=("review_trip", "get_ledger", "paste_trips")),
    case("7.01", "BEHAVIOR", "Import 11 opening months and historical PH-101", check="opening_import", functions=("get_ledger", "import_cutover")),
    case("7.02", "BEHAVIOR", "JS model operation parity and monthly tuples", check="model", functions=("paste_trips", "record_receipt", "reallocate")),
    case("7.02b", "BEHAVIOR", "Advance, price edit, paste after receipt, missing price, adjustment after void", check="model_edges", functions=("paste_trips", "edit_trip_price", "adjust_month", "void_receipt")),
    case("7.sheet", "BEHAVIOR", "Sheet cross-customer duplicate and NULL price", check="sheet_cross_customer", functions=("paste_trips", "list_sheet_trip_refs")),
    case("7.03", "BEHAVIOR", "Atomic failure after allocation write", check="atomic", functions=("record_receipt",)),
    case("7.03b", "BEHAVIOR", "Reject allocation, advance and event invariant corruption", check="invariant_rejections", functions=("record_receipt", "_check_allocations")),
    case("7.04", "BEHAVIOR", "Idempotency before stale version", check="idempotency", functions=("record_receipt",)),
    case("7.05", "BEHAVIOR", "Concurrent receipts and stale version", check="concurrent", functions=("record_receipt",)),
    case("7.05b", "BEHAVIOR", "Same-date mixed-case pid uses JS/C order", check="pid_order", functions=("reallocate",)),
    case("7.06", "SCHEMA", "Immutable money rows and role DML denial", check="immutable"),
    case("7.07", "BEHAVIOR", "Void every original line, snapshots, rollback", check="void", functions=("void_receipt",)),
    case("7.08", "BEHAVIOR", "VN month lock after customer lock", check="locks", functions=("set_month_lock", "edit_trip_price", "paste_trips")),
    case("7.09a", "SCHEMA", "App and reader DB role boundaries", check="roles"),
    case("7.09b", "BEHAVIOR", "Actor, hostile search_path, allowed EXECUTE", check="actor", functions=("get_ledger", "record_receipt")),
    case("7.09c", "BEHAVIOR", "Trial actor comes from session; no per-person ACL", check="actor", functions=("get_ledger",)),
    case("7.10a", "SCHEMA", "Bigint, NULL and integer constraints", check="numbers"),
    case("7.10b", "BEHAVIOR", "Reject -0 and oversized user input", check="input", functions=("paste_trips",)),
    case("7.11a", "SCHEMA", "Draft/one-sided active view gate, monthly buckets", check="gate_view"),
    case("7.11b", "BEHAVIOR", "FIFO monthly gate and nonzero opening anchor", check="cutover_gate", functions=("import_cutover", "verify_cutover_customer", "verify_cutover", "activate_cutover", "activate_cutover_customer")),
    case("7.11c", "SKIPPED_OPEN", "Complete source population evidence", open_reason="frozen source row and customer completeness cannot be proven by submitted aggregates and hashes"),
    case("7.12", "BEHAVIOR", "FIFO through opening and adjustment", check="opening_fifo", functions=("record_receipt", "adjust_month", "reallocate")),
    case("7.13", "SCHEMA", "Legacy rows excluded and immutable", check="legacy"),
    case("7.14a", "SCHEMA", "Import-once indexes and customer uniqueness", check="import_guard"),
    case("7.14b", "BEHAVIOR", "Retry import, totals, NO_BASELINE, concurrent import/verify", check="import_behavior", functions=("import_cutover", "verify_cutover_customer")),
    case("7.15a", "SCHEMA", "Negative opening remains signed in active view", check="negative"),
    case("7.15b", "BEHAVIOR", "Receipt skips negative bucket; void preserves other receipts", check="negative_receipt", functions=("record_receipt", "void_receipt")),
    case("7.15c", "SKIPPED_OPEN", "Cross-ledger negative transfer and refund", open_reason="cross-ledger transfer and refund policy remain open"),
    case("7.16a", "SCHEMA", "Event snapshot and same-customer FK checks", check="events"),
    case("7.16b", "BEHAVIOR", "Reallocation snapshots and rollback of seven commands", check="snapshots", functions=("record_receipt", "edit_receipt_meta", "void_receipt", "adjust_trip", "adjust_month", "edit_trip_price", "paste_trips")),
    case("7.17", "SCHEMA", "Evidence freeze by trigger and concurrent direct DML", check="evidence"),
    case("7.18a", "SCHEMA", "NULL fee storage and three SQL view amount cases", check="fee"),
    case("7.18b", "BEHAVIOR", "get_ledger missing-price flag and JS tripAmount parity", check="ledger_fee", functions=("get_ledger",)),
    case("7.xx", "BEHAVIOR", "Golden anonymous V7 fixture", check="golden", functions=("get_ledger",)),
    case("7.19", "BEHAVIOR", "Monthly identity includes active signed opening and adjustments", check="monthly_identity", functions=("get_ledger",)),
    case("7.20", "BEHAVIOR", "Locked field edits use current price; NULL fee; legacy amount; retry", check="field_adjustment", functions=("adjust_trip",)),
    case("7.21", "BEHAVIOR", "VN receipt today accepted; tomorrow rejected without version change", check="future_receipt", functions=("record_receipt", "edit_receipt_meta")),
    case("7.22", "BEHAVIOR", "Void GET identifies only allocations current at void time", check="void_get", functions=("get_ledger", "void_receipt", "reallocate")),
    case("7.23", "BEHAVIOR", "Typed adjustment values survive audit tampering and latest price revision", check="adjustment_source", functions=("adjust_trip",)),
    case("7.26", "BEHAVIOR", "Shipper survives paste, review and edits in the ledger reader", check="shipper_write_sync", functions=("paste_trips", "edit_trip_info", "review_trip")),
    case("7.27", "BEHAVIOR", "Typed fee intent lands on the effective fee after a price revision", check="fee_intent_after_price", functions=("adjust_trip", "edit_trip_price")),
]


# CT-2SO acceptance map. Detailed Docker scenarios stay isolated from legacy fixture cases.
for _n, _title in [
    (1, "pair write preserves total and audit"), (2, "source credit overflow"),
    (3, "pair write rollback"), (4, "same source contention"),
    (5, "cross pair lock ordering"), (6, "pair idempotency"),
    (7, "void from either side"), (8, "date edit both sides"),
    (9, "paired method immutable"), (10, "outside ledger remains single receipt"),
    (11, "source list filters and A-Z order"), (12, "Vietnam future date"),
    (13, "legacy CẤN TRỪ remains unlinked"), (14, "per-book PH sequence"),
    (15, "target overpayment becomes advance"),
]:
    CASES.append(case(f"CT-2SO.{_n:02d}", "BEHAVIOR", _title, check=f"ct_{_n:02d}",
                      functions=("record_offset", "void_offset", "edit_offset_date",
                                 "list_offset_sources")))


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


def check_opening_import(pg: Pg) -> None:
    amounts = [100, 0, -20, 30, 40, 50, 60, 70, 80, 90, 100]
    customer, cutover = cutover_book(pg, sum(amounts))
    openings, _, checks = import_data(amounts)
    legacy = json.dumps([{"debt_month": "2026-06-01", "kind": "receipt",
                          "display": {"pid": "PH-101"}, "source_total_vnd": 600694000,
                          "source_tab": "FAKE", "source_row": 101}])
    result = call(pg, "import_cutover", customer, 0, "eleven-month-import", cutover,
                  openings, legacy, checks, sum(amounts), "a" * 64)
    require(result["status"] == "draft" and result["version"] == 1, "import did not make draft")
    require(pg.value(f"SELECT count(*) FROM sokhach.opening_balance WHERE customer_id={customer}") == "11",
            "11 opening rows missing")
    require(pg.value(f"SELECT count(*) FROM sokhach.event WHERE customer_id={customer} AND kind='import'") == "1",
            "import event missing")
    require(pg.value(f"SELECT display->>'pid' FROM sokhach.legacy_row WHERE customer_id={customer}") == "PH-101",
            "historical PH-101 missing")
    require(call(pg, "get_ledger", customer)["status"] == "NO_BASELINE", "draft ledger leaked")
    require(pg.value(f"SELECT count(*) FROM sokhach.v_outstanding_month WHERE customer_id={customer}") == "0",
            "draft opening entered balance")


def check_cutover_gate(pg: Pg) -> None:
    wrong, wrong_cutover = cutover_book(pg, 300)
    wrong_openings, wrong_legacy, wrong_checks = import_data(
        [90, 210], buckets=[90, 210], standards=[100, 200])
    call(pg, "import_cutover", wrong, 0, "wrong-month-import", wrong_cutover,
         wrong_openings, wrong_legacy, wrong_checks, 300, "a" * 64)
    reject_call(pg, "verify_cutover_customer", wrong, wrong_cutover, version(pg, wrong),
                "wrong-month-verify", "FAKE-SIGNOFF", error="CUTOVER_MONTH_MISMATCH")
    require(pg.value(f"SELECT status FROM sokhach.cutover_customer WHERE customer_id={wrong}") == "draft",
            "[90,210] passed independent [100,200] monthly gate")
    customer, cutover = cutover_book(pg, 300)
    openings, legacy, checks = import_data([100, 200], buckets=[90, 210],
                                          charges=[100, 200])
    call(pg, "import_cutover", customer, 0, "gate-import", cutover,
         openings, legacy, checks, 300, "a" * 64)
    reject_call(pg, "verify_cutover_customer", customer, cutover, version(pg, customer),
                "gate-bad-bucket", "FAKE-SIGNOFF", error="CUTOVER_MONTH_MISMATCH")
    require(pg.value(f"SELECT status FROM sokhach.cutover_customer WHERE customer_id={customer}") == "draft",
            "bad monthly bucket verified")
    # Source charges stay [100,200]; repair only imported monthly buckets.
    pg.sql(f"UPDATE sokhach.cutover_month_check SET standard_bucket_vnd=100, bucket_vnd=100 "
           f"WHERE customer_id={customer} "
           "AND debt_month='2026-01-01'")
    pg.sql(f"UPDATE sokhach.cutover_month_check SET standard_bucket_vnd=200, bucket_vnd=200 "
           f"WHERE customer_id={customer} "
           "AND debt_month='2026-02-01'")
    pg.sql(f"UPDATE sokhach.cutover_month_check SET replay_cumulative_vnd=-1 WHERE customer_id={customer}")
    # Client replay is diagnostic only; anchored bucket and source checks decide gate.
    no_anchor, no_anchor_cutover = cutover_book(pg, 0)
    anchor_openings, anchor_legacy, anchor_checks = import_data([0])
    broken_checks = json.loads(anchor_checks)
    broken_checks[0]["standard_source_ref"] = None
    call(pg, "import_cutover", no_anchor, 0, "missing-anchor-import", no_anchor_cutover,
         anchor_openings, anchor_legacy, json.dumps(broken_checks), 0, "a" * 64)
    reject_call(pg, "verify_cutover_customer", no_anchor, no_anchor_cutover,
                version(pg, no_anchor), "missing-anchor-verify", "FAKE-SIGNOFF",
                error="CUTOVER_MONTH_MISMATCH")
    missing_flow, missing_flow_cutover = cutover_book(pg, 100)
    import_book(pg, missing_flow, missing_flow_cutover, [100], "missing-flow-import")
    pg.sql(f"UPDATE sokhach.cutover_month_check SET source_receipt_vnd=NULL "
           f"WHERE customer_id={missing_flow}")
    reject_call(pg, "verify_cutover_customer", missing_flow, missing_flow_cutover,
                version(pg, missing_flow), "missing-flow-verify", None,
                error="CUTOVER_MONTH_MISMATCH")
    # Real automatic policy; no fake signoff function in harness.
    contradictory, contradictory_cutover = cutover_book(pg, 300)
    import_book(pg, contradictory, contradictory_cutover, [100, 200], "anchor-import")
    pg.sql(f"UPDATE sokhach.cutover_month_check SET opening_anchor_vnd=0, "
           f"source_cumulative_vnd=CASE WHEN debt_month='2026-01-01' THEN 110 ELSE 310 END, "
           f"replay_cumulative_vnd=CASE WHEN debt_month='2026-01-01' THEN 110 ELSE 310 END "
           f"WHERE customer_id={contradictory}")
    reject_call(pg, "verify_cutover_customer", contradictory, contradictory_cutover,
                version(pg, contradictory), "anchor-contradiction", "FAKE-SIGNOFF",
                error="CUTOVER_ANCHOR_MISMATCH")
    require(pg.value(f"SELECT status FROM sokhach.cutover_customer WHERE customer_id={contradictory}") == "draft",
            "self-contradictory first source anchor verified")
    absent, absent_cutover = cutover_book(pg, 100)
    import_book(pg, absent, absent_cutover, [100], "no-first-anchor")
    pg.sql(f"UPDATE sokhach.cutover_month_check SET opening_anchor_vnd=NULL "
           f"WHERE customer_id={absent}")
    reject_call(pg, "verify_cutover_customer", absent, absent_cutover,
                version(pg, absent), "no-first-anchor-verify", "FAKE-SIGNOFF",
                error="CUTOVER_MONTH_MISMATCH")
    # Initial 50 belongs in oldest monthly bucket; final anchor is 350.
    nonzero, nonzero_cutover = cutover_book(pg, 350)
    opening, legacy, checks = import_data([150, 200], charges=[100, 200], opening_anchor=50)
    call(pg, "import_cutover", nonzero, 0, "nonzero-anchor-import", nonzero_cutover,
         opening, legacy, checks, 350, "a" * 64)
    require(call(pg, "verify_cutover_customer", nonzero, nonzero_cutover,
                 version(pg, nonzero), "nonzero-anchor-verify", None)["status"] ==
             "verified", "initial 50 was not included in oldest FIFO bucket")
    lost, lost_cutover = cutover_book(pg, 300)
    opening, legacy, checks = import_data([100, 200], charges=[100, 200], opening_anchor=50)
    call(pg, "import_cutover", lost, 0, "lost-anchor-import", lost_cutover,
         opening, legacy, checks, 300, "a" * 64)
    reject_call(pg, "verify_cutover_customer", lost, lost_cutover, version(pg, lost),
                "lost-anchor-verify", None, error="CUTOVER_FIFO_MISMATCH")
    fifo, fifo_cutover = cutover_book(pg, 150)
    opening, legacy, checks = import_data([0, 150], charges=[100, 200], receipts=[0, 150])
    call(pg, "import_cutover", fifo, 0, "fifo-import", fifo_cutover,
         opening, legacy, checks, 150, "a" * 64)
    require(call(pg, "verify_cutover_customer", fifo, fifo_cutover, version(pg, fifo),
                 "fifo-verify", None)["status"] == "verified", "FIFO [0,150] rejected")
    wrong_fifo, wrong_fifo_cutover = cutover_book(pg, 150)
    opening, legacy, checks = import_data([100, 50], charges=[100, 200],
                                         receipts=[0, 150])
    call(pg, "import_cutover", wrong_fifo, 0, "wrong-fifo-import", wrong_fifo_cutover,
         opening, legacy, checks, 150, "a" * 64)
    reject_call(pg, "verify_cutover_customer", wrong_fifo, wrong_fifo_cutover,
                version(pg, wrong_fifo), "wrong-fifo-verify", None,
                error="CUTOVER_FIFO_MISMATCH")
    reject_call(pg, "activate_cutover_customer", customer, cutover, version(pg, customer),
                "early-customer", "FAKE-SIGNOFF", error="CUTOVER_TRANSITION_ORDER")
    reject_call(pg, "verify_cutover", cutover, "early-cutover", "FAKE-SIGNOFF",
                error="CUTOVER_CUSTOMERS_NOT_VERIFIED")
    verified = call(pg, "verify_cutover_customer", customer, cutover, version(pg, customer),
                    "gate-verify-customer", "FAKE-SIGNOFF")
    require(verified["status"] == "verified", "customer verification missing")
    require(pg.value(f"SELECT count(*) FROM sokhach.cutover_customer "
                     f"WHERE customer_id={customer} AND cutover_id={cutover} AND status='verified'") == "1"
            and pg.value(f"SELECT count(*) FROM sokhach.idempotency "
                         f"WHERE customer_id={customer} AND key='gate-verify-customer'") == "1"
            and call(pg, "verify_cutover_customer", customer, cutover, 0,
                     "gate-verify-customer", "FAKE-SIGNOFF") == verified,
            "automatic verification yielded more than one result")
    require(call(pg, "get_ledger", customer)["status"] == "NO_BASELINE", "verified leaked")
    reject_call(pg, "activate_cutover_customer", customer, cutover, version(pg, customer),
                "early-activate", "FAKE-SIGNOFF", error="CUTOVER_TRANSITION_ORDER")
    # Other cutover has a draft customer; whole-cutover gate must ignore it.
    other_customer, other_cutover = cutover_book(pg, 1)
    import_book(pg, other_customer, other_cutover, [1], "other-cutover-import")
    all_verified = call(pg, "verify_cutover", cutover, "gate-verify-all", "FAKE-SIGNOFF")
    require(all_verified["status"] == "verified", "cutover verification missing")
    require(pg.value(f"SELECT status FROM sokhach.cutover_customer WHERE customer_id={other_customer}")
            == "draft", "whole-cutover gate changed other cutover")
    reject_call(pg, "verify_cutover", other_cutover, "other-verify-all", "FAKE-SIGNOFF",
                error="CUTOVER_CUSTOMERS_NOT_VERIFIED")
    require(call(pg, "get_ledger", customer)["status"] == "NO_BASELINE", "verified cutover leaked")
    active = call(pg, "activate_cutover", cutover, "gate-activate-all", "FAKE-SIGNOFF")
    require(active["status"] == "active", "cutover activation missing")
    require(call(pg, "get_ledger", customer)["status"] == "NO_BASELINE", "one-sided active leaked")
    customer_active = call(pg, "activate_cutover_customer", customer, cutover,
                           version(pg, customer), "gate-activate-customer", "FAKE-SIGNOFF")
    require(customer_active["status"] == "active", "customer activation missing")
    ledger = call(pg, "get_ledger", customer)
    require(ledger["total_outstanding_vnd"] == "300" and len(ledger["months"]) == 2,
            "active opening wrong or legacy doubled")
    require(call(pg, "verify_cutover", cutover, "gate-verify-all", "FAKE-SIGNOFF") == all_verified,
            "whole-cutover retry changed result")
    reject_call(pg, "verify_cutover", cutover, "gate-verify-all", "changed-ref",
                error="IDEMPOTENCY_CONFLICT")
    zero, zero_cutover = cutover_book(pg, 0)
    import_book(pg, zero, zero_cutover, [0], "zero-import")
    call(pg, "verify_cutover_customer", zero, zero_cutover, version(pg, zero),
         "zero-verify", "FAKE-SIGNOFF")
    call(pg, "verify_cutover", zero_cutover, "zero-verify-all", "FAKE-SIGNOFF")
    call(pg, "activate_cutover", zero_cutover, "zero-activate-all", "FAKE-SIGNOFF")
    call(pg, "activate_cutover_customer", zero, zero_cutover, version(pg, zero),
         "zero-activate-customer", "FAKE-SIGNOFF")
    require(call(pg, "get_ledger", zero)["total_outstanding_vnd"] == "0",
            "explicit zero baseline failed")
    mismatch, mismatch_cutover = cutover_book(pg, 301)
    import_book(pg, mismatch, mismatch_cutover, [100, 200], "total-import")
    call(pg, "verify_cutover_customer", mismatch, mismatch_cutover, version(pg, mismatch),
         "total-verify-customer", "FAKE-SIGNOFF")
    reject_call(pg, "verify_cutover", mismatch_cutover, "total-verify-all", "FAKE-SIGNOFF",
                error="CUTOVER_TOTAL_MISMATCH")
    require(pg.value(f"SELECT status FROM sokhach.cutover WHERE id={mismatch_cutover}") == "draft",
            "wrong whole-cutover total verified")


def check_import_behavior(pg: Pg) -> str:
    customer, cutover = cutover_book(pg, 100)
    args = (customer, 0, "import-retry", cutover, *import_data([100]), 100, "a" * 64)
    first = call(pg, "import_cutover", *args)
    require(call(pg, "import_cutover", *args) == first, "same-key import retry changed result")
    reject_call(pg, "import_cutover", customer, 0, "import-retry", cutover,
                *import_data([101]), 100, "a" * 64, error="IDEMPOTENCY_CONFLICT")
    reject_call(pg, "import_cutover", customer, 0, "import-stale", cutover,
                *import_data([100]), 100, "a" * 64, error="STALE_LEDGER")
    reject_call(pg, "import_cutover", customer, version(pg, customer), "import-duplicate", cutover,
                *import_data([100]), 100, "a" * 64, error="CUTOVER_IMPORT_CONFLICT")
    empty_customer, empty_cutover = cutover_book(pg, 0)
    empty_args = (empty_customer, 0, "empty-import", empty_cutover,
                  *import_data([]), 0, "a" * 64)
    empty_result = call(pg, "import_cutover", *empty_args)
    require(call(pg, "import_cutover", *empty_args) == empty_result,
            "empty opening retry changed result")
    reject_call(pg, "import_cutover", empty_customer, version(pg, empty_customer),
                "empty-duplicate", empty_cutover, *import_data([]), 0, "a" * 64,
                error="CUTOVER_IMPORT_CONFLICT")
    bad_customer, bad_cutover = cutover_book(pg, 100)
    reject_call(pg, "import_cutover", bad_customer, 0, "one-dong", bad_cutover,
                *import_data([100]), 101, "a" * 64, error="CUTOVER_CUSTOMER_TOTAL_MISMATCH")
    pg.true(f"NOT EXISTS(SELECT 1 FROM sokhach.cutover_customer WHERE customer_id={bad_customer}) "
            f"AND NOT EXISTS(SELECT 1 FROM sokhach.event WHERE customer_id={bad_customer}) "
            f"AND NOT EXISTS(SELECT 1 FROM sokhach.opening_balance WHERE customer_id={bad_customer}) "
            f"AND NOT EXISTS(SELECT 1 FROM sokhach.idempotency WHERE customer_id={bad_customer})",
            "one-dong rejection left partial rows")
    late_customer, late_cutover = cutover_book(pg, 200)
    late_openings, _, late_checks = import_data([100, 100])
    duplicate_legacy = json.dumps([{"debt_month": "2026-01-01", "kind": "trip",
        "display": {}, "source_tab": "FAKE", "source_row": 77},
        {"debt_month": "2026-02-01", "kind": "trip", "display": {},
         "source_tab": "FAKE", "source_row": 77}])
    reject_call(pg, "import_cutover", late_customer, 0, "late-fail", late_cutover,
                late_openings, duplicate_legacy, late_checks, 200, "a" * 64,
                error="duplicate key")
    pg.true(f"NOT EXISTS(SELECT 1 FROM sokhach.cutover_customer WHERE customer_id={late_customer}) "
            f"AND NOT EXISTS(SELECT 1 FROM sokhach.event WHERE customer_id={late_customer}) "
            f"AND NOT EXISTS(SELECT 1 FROM sokhach.opening_balance WHERE customer_id={late_customer}) "
            f"AND NOT EXISTS(SELECT 1 FROM sokhach.legacy_row WHERE customer_id={late_customer})",
            "late failure left partial rows")
    flagged, flagged_cutover = cutover_book(pg, 600)
    import_book(pg, flagged, flagged_cutover, [600], "flagged-import",
                flags=[["NO_BASELINE", "MISSING_PRICE", "MISSING_CACHE",
                        "HISTORICAL_DELTA_600"]])
    pg.true(f"EXISTS(SELECT 1 FROM sokhach.cutover_month_check WHERE customer_id={flagged} "
            "AND exception_codes @> ARRAY['NO_BASELINE','MISSING_PRICE','MISSING_CACHE',"
            "'HISTORICAL_DELTA_600']::text[])",
            "source exception flags lost")
    draft_ledger = call(pg, "get_ledger", flagged)
    require(draft_ledger["status"] == "NO_BASELINE"
            and len(draft_ledger["source_exceptions"][0]["exception_codes"]) == 4,
            "draft flags hidden or draft amount leaked")
    require(call(pg, "verify_cutover_customer", flagged, flagged_cutover, version(pg, flagged),
                 "flagged-verify", None)["status"] == "verified", "flags blocked mechanical gate")
    call(pg, "verify_cutover", flagged_cutover, "flagged-all", None)
    call(pg, "activate_cutover", flagged_cutover, "flagged-active", None)
    call(pg, "activate_cutover_customer", flagged, flagged_cutover, version(pg, flagged),
         "flagged-customer-active", None)
    require(set(call(pg, "get_ledger", flagged)["source_exceptions"][0]["exception_codes"])
            == {"NO_BASELINE", "MISSING_PRICE", "MISSING_CACHE", "HISTORICAL_DELTA_600"},
            "source flags missing from active ledger")
    live, live_cutover = cutover_book(pg, 0)
    reject_call(pg, "record_receipt", live, version(pg, live), "unbased-receipt",
                "2026-01-01", "THU TIỀN", 1, error="NO_BASELINE")
    pg.sql(f"INSERT INTO sokhach.event(customer_id,kind,actor,\"before\",\"after\") "
           f"VALUES({live},'paste','harness','{{}}','{{\"trips\":[]}}')")
    reject_call(pg, "import_cutover", live, 0, "late-import", live_cutover,
                *import_data([]), 0, "a" * 64, error="CUTOVER_IMPORT_CONFLICT")
    observed = check_import_verify_locks(pg)
    single = check_single_verification_result(pg)
    return ("retry, one-dong rollback, source flags, NO_BASELINE, live-event guard; "
            + observed + "; " + single)


def check_single_verification_result(pg: Pg) -> str:
    customer, cutover = cutover_book(pg, 100)
    import_book(pg, customer, cutover, [100], "race-import")
    a, b = PsqlSession(pg, f"v7_verify_a_{customer}"), PsqlSession(pg, f"v7_verify_b_{customer}")
    try:
        a.send("BEGIN; SET LOCAL sokhach.actor='race-a'; SELECT pg_backend_pid()")
        pid_a = int(a.line())
        a.send(f"SELECT sokhach.verify_cutover_customer({customer},{cutover},1,'race-a','FAKE-SIGNOFF')")
        result = json.loads(a.line())
        b.send("BEGIN; SET LOCAL sokhach.actor='race-b'; SELECT pg_backend_pid()")
        pid_b = int(b.line())
        b.send(f"SELECT sokhach.verify_cutover_customer({customer},{cutover},1,'race-b','FAKE-SIGNOFF')")
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline and pg.value(
                f"SELECT {pid_a}=ANY(pg_blocking_pids({pid_b}))") != "t":
            time.sleep(0.05)
        require(pg.value(f"SELECT {pid_a}=ANY(pg_blocking_pids({pid_b}))") == "t",
                "second verify did not wait for first")
        a.send("COMMIT; SELECT 'committed'")
        require(a.line() == "committed", "first verification did not commit")
        b.proc.wait(timeout=10)
        stderr = b.proc.stderr.read() if b.proc.stderr else ""
        require("STALE_LEDGER" in stderr and result["status"] == "verified",
                f"second verification did not reject stale version: {stderr[-500:]}")
        require(version(pg, customer) == 2 and pg.value(
            f"SELECT count(*) FROM sokhach.idempotency WHERE customer_id={customer} "
            "AND key IN ('race-a','race-b')") == "1",
            "automatic-policy race produced more than one result")
    finally:
        a.close()
        b.close()
    return "one verified result and one stale rejection under fake policy"


def check_import_verify_locks(pg: Pg) -> str:
    """Cutover lock must block command before its customer lock, in both orders."""

    def worker(name: str, command: str) -> subprocess.Popen[str]:
        return subprocess.Popen(
            ["docker", "exec", "--env", f"PGAPPNAME={name}", "--env",
             "PGOPTIONS=-c statement_timeout=20000 -c lock_timeout=18000",
             pg.name, "psql", "-X", "-qAt", "-v", "ON_ERROR_STOP=1",
             "-U", "postgres", "-d", DATABASE, "-c", actor_sql(command)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            encoding="utf-8", errors="replace")

    def blockers(name: str) -> tuple[int | None, set[int]]:
        rows = pg.value("SELECT pid::text || '|' || array_to_string(pg_blocking_pids(pid), ',') "
            "FROM pg_stat_activity WHERE datname=current_database() "
            "AND state='active' AND wait_event_type='Lock' "
            f"AND application_name={lit(name)}").splitlines()
        require(len(rows) <= 1, f"multiple PostgreSQL sessions for {name}: {rows}")
        if not rows:
            return None, set()
        return parse_blocker_row(rows[0])

    def wait_blocked(name: str, expected: set[int], process: subprocess.Popen[str]) -> int:
        deadline = time.monotonic() + 8
        observed: tuple[int | None, set[int]] = (None, set())
        while time.monotonic() < deadline:
            observed = blockers(name)
            if observed[1] & expected:
                return observed[0]
            if process.poll() is not None:
                break
            time.sleep(0.05)  # polling only; pg_blocking_pids is lock evidence
        raise HarnessError(f"{name} did not block on cutover queue: "
                           f"pid/blockers={observed}, exit={process.poll()}")

    def finish(process: subprocess.Popen[str], error: str | None,
               status: str | None = None) -> None:
        try:
            out, err = process.communicate(timeout=22)
        except subprocess.TimeoutExpired as exc:
            process.kill()
            process.communicate()
            raise HarnessError("import/verify worker timed out") from exc
        require("40P01" not in err and "deadlock detected" not in err,
                f"import/verify deadlock: {err[-600:]}")
        if error is None:
            require(process.returncode == 0, f"import worker failed: {out} {err[-600:]}")
            require(json.loads(out.strip())["status"] == status,
                    f"worker returned wrong status: {out} {err[-600:]}")
        else:
            require(process.returncode != 0 and error in err,
                    f"verify worker had unexpected outcome: {out} {err[-600:]}")

    def import_sql(c: int, key: str) -> str:
        args = (c, 0, key, cutover, *import_data([100]), 100, "a" * 64)
        return "SELECT sokhach.import_cutover(" + ",".join(lit(x) for x in args) + ")"

    def verify_sql(c: int, key: str) -> str:
        args = (c, cutover, version(pg, c), key, "FAKE-SIGNOFF")
        return "SELECT sokhach.verify_cutover_customer(" + ",".join(lit(x) for x in args) + ")"

    for direction in ("import-first", "verify-first"):
        customer, cutover = cutover_book(pg, 100)
        holder_name = f"v7_cutover_holder_{pg.run_id}"
        holder = PsqlSession(pg, holder_name)
        first = second = None
        try:
            holder.send("BEGIN")
            holder.send(f"SELECT pg_backend_pid() FROM sokhach.cutover WHERE id={cutover} FOR UPDATE")
            holder_pid = int(holder.line())
            require(pg.value(f"SELECT application_name FROM pg_stat_activity WHERE pid={holder_pid}")
                    == holder_name, "cutover holder PID/application_name mismatch")
            if direction == "import-first":
                first_name = f"v7_import_{pg.run_id}"
                first = worker(first_name, import_sql(customer, "lock-import"))
                first_error = None
                second_name = f"v7_verify_{pg.run_id}"
                second_command = verify_sql(customer, "lock-verify")
            else:
                first_name = f"v7_verify2_{pg.run_id}"
                first = worker(first_name, verify_sql(customer, "lock-verify2"))
                first_error = "CUTOVER_TRANSITION_ORDER"
                second_name = f"v7_import2_{pg.run_id}"
                second_command = import_sql(customer, "lock-import2")
            first_pid = wait_blocked(first_name, {holder_pid}, first)
            pg.value(f"BEGIN; SELECT id FROM sokhach.customer WHERE id={customer} FOR UPDATE NOWAIT; COMMIT")
            second = worker(second_name, second_command)
            # pg_blocking_pids may name first waiter as soft blocker of second.
            wait_blocked(second_name, {holder_pid, first_pid}, second)
            require(holder_pid in blockers(first_name)[1],
                    "first worker no longer blocked by cutover holder")
        finally:
            holder.close()
        if first is not None:
            finish(first, first_error, "draft" if direction == "import-first" else None)
        if second is not None:
            finish(second, "STALE_LEDGER" if direction == "import-first" else None,
                   "draft" if direction == "verify-first" else None)
        require(pg.value(f"SELECT status FROM sokhach.cutover_customer WHERE customer_id={customer}")
                == "draft" and version(pg, customer) == 1,
                f"{direction} did not leave exactly one draft import")
    return ("pg_blocking_pids: import then stale verify; "
            "transition-order verify then successful draft import")


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


def check_idempotency(pg: Pg) -> None:
    c = new_book(pg, ("2026-01-01", 100))
    first = call(pg, "record_receipt", c, 0, "idem-1", "2026-02-01", "THU TIỀN", 60)
    require(first["version"] == 1 and first["pid"] == "PH-001", "first receipt result wrong")
    require(call(pg, "record_receipt", c, 0, "idem-1", "2026-02-01", "THU TIỀN", 60) == first,
            "same-key retry changed result")
    require(version(pg, c) == 1 and pg.value(f"SELECT count(*) FROM sokhach.receipt WHERE customer_id={c}") == "1",
            "same-key retry wrote again")
    reject_call(pg, "record_receipt", c, 0, "idem-1", "2026-02-01", "THU TIỀN", 61,
                error="IDEMPOTENCY_CONFLICT")
    reject_call(pg, "record_receipt", c, 0, "idem-2", "2026-02-01", "THU TIỀN", 1,
                error="STALE_LEDGER")
    require(months(pg, c)[0][1] == "40", "idempotency changed balance")


def check_atomic(pg: Pg) -> None:
    c = new_book(pg, ("2026-01-01", 60), ("2026-02-01", 60))
    pg.sql("""CREATE FUNCTION public.fail_second_allocation() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN IF NEW.debt_month='2026-02-01' THEN RAISE EXCEPTION 'HARNESS_FAIL_SECOND_LINE'; END IF;
RETURN NEW; END $$;
CREATE TRIGGER harness_fail_second_allocation BEFORE INSERT ON sokhach.receipt_line
FOR EACH ROW EXECUTE FUNCTION public.fail_second_allocation()""")
    try:
        reject_call(pg, "record_receipt", c, 0, "atomic-1", "2026-03-01", "THU TIỀN", 100,
                    error="HARNESS_FAIL_SECOND_LINE")
        for table in ("receipt", "receipt_line", "idempotency"):
            require(pg.value(f"SELECT count(*) FROM sokhach.{table} WHERE customer_id={c}") == "0",
                    f"atomic failure left {table}")
        require(pg.value(f"SELECT count(*) FROM sokhach.event WHERE customer_id={c} AND kind='receipt'") == "0"
                and version(pg, c) == 0 and [r[1] for r in months(pg, c)] == ["60", "60"],
                "atomic failure left event/version/balance")
    finally:
        pg.sql("DROP TRIGGER harness_fail_second_allocation ON sokhach.receipt_line; "
               "DROP FUNCTION public.fail_second_allocation()")
    call(pg, "record_receipt", c, 0, "atomic-base", "2026-03-01", "THU TIỀN", 100)
    fixture_open_month(pg, c, "2026-01-01")
    before = (version(pg, c), months(pg, c), allocations(pg, c, "PH-001"),
              pg.value(f"SELECT count(*) FROM sokhach.event WHERE customer_id={c}"))
    pg.sql("CREATE FUNCTION public.fail_reallocation() RETURNS trigger LANGUAGE plpgsql AS $$ "
           "BEGIN RAISE EXCEPTION 'HARNESS_REALLOCATE_ABORT'; END $$; "
           "CREATE TRIGGER harness_fail_reallocation BEFORE INSERT ON sokhach.receipt_line "
           "FOR EACH ROW EXECUTE FUNCTION public.fail_reallocation()")
    try:
        reject_call(pg, "adjust_month", c, 1, "atomic-reallocate", "2026-01-01", 20,
                    "sửa", error="HARNESS_REALLOCATE_ABORT")
        require((version(pg, c), months(pg, c), allocations(pg, c, "PH-001"),
                 pg.value(f"SELECT count(*) FROM sokhach.event WHERE customer_id={c}")) == before,
                "reallocate insert failure left partial state")
    finally:
        pg.sql("DROP TRIGGER harness_fail_reallocation ON sokhach.receipt_line; "
               "DROP FUNCTION public.fail_reallocation()")
    pg.sql("CREATE FUNCTION public.fail_finish() RETURNS trigger LANGUAGE plpgsql AS $$ "
           "BEGIN RAISE EXCEPTION 'HARNESS_FINISH_ABORT'; END $$; "
           "CREATE TRIGGER harness_fail_finish BEFORE INSERT ON sokhach.idempotency "
           "FOR EACH ROW EXECUTE FUNCTION public.fail_finish()")
    try:
        reject_call(pg, "adjust_month", c, 1, "atomic-finish", "2026-01-01", 20,
                    "sửa", error="HARNESS_FINISH_ABORT")
        require((version(pg, c), months(pg, c), allocations(pg, c, "PH-001"),
                 pg.value(f"SELECT count(*) FROM sokhach.event WHERE customer_id={c}")) == before,
                "finish failure left partial state")
    finally:
        pg.sql("DROP TRIGGER harness_fail_finish ON sokhach.idempotency; "
               "DROP FUNCTION public.fail_finish()")


def check_invariant_rejections(pg: Pg) -> None:
    c = new_book(pg, ("2026-01-01", 100), ("2026-02-01", 0))
    call(pg, "record_receipt", c, 0, "invariant-receipt", "2026-03-01", "THU TIỀN", 120)
    line = pg.value(f"SELECT id FROM sokhach.receipt_line WHERE customer_id={c} AND kind='debt'")
    advance = pg.value(f"SELECT id FROM sokhach.receipt_line WHERE customer_id={c} AND kind='advance'")
    def reject_corruption(change: str, error: str) -> None:
        pg.rejects("BEGIN; ALTER TABLE sokhach.receipt_line DISABLE TRIGGER receipt_line_guard; "
                   + change + f"; SELECT sokhach._check_allocations({c})", message=error)
        assert_allocations(pg, c)
    reject_corruption(f"UPDATE sokhach.receipt_line SET amount_vnd=99 WHERE id={line}",
                      "ALLOCATION_INVARIANT")
    reject_corruption(f"UPDATE sokhach.receipt_line SET debt_month='2026-01-01' WHERE id={advance}",
                      "ADVANCE_MONTH_INVARIANT")
    bad_event = pg.value(f"INSERT INTO sokhach.event(customer_id,kind,actor,\"before\",\"after\") "
                         f"VALUES ({c},'paste','harness','{{}}','{{\"trips\":[]}}') RETURNING id")
    reject_corruption(f"UPDATE sokhach.receipt_line SET created_by_event={bad_event} WHERE id={line}",
                      "ALLOCATION_EVENT_INVARIANT")


def check_void(pg: Pg) -> None:
    c = new_book(pg, ("2026-01-01", 60), ("2026-02-01", 60))
    first = call(pg, "record_receipt", c, 0, "void-r1", "2026-03-01", "THU TIỀN", 100)
    call(pg, "record_receipt", c, 1, "void-r2", "2026-03-02", "THU TIỀN", 10)
    before = allocations(pg, c, first["pid"])
    other = allocations(pg, c, "PH-002")
    require(before == [("2026-01-01", "debt", "60"), ("2026-02-01", "debt", "40")],
            "void setup lacks two months")
    reject_call(pg, "void_receipt", c, 2, "void-blank", first["pid"], " ", error="VOID_REASON_REQUIRED")
    pg.sql("""CREATE FUNCTION public.fail_second_void() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN IF OLD.debt_month='2026-02-01' THEN RAISE EXCEPTION 'HARNESS_FAIL_SECOND_VOID'; END IF;
RETURN NEW; END $$;
CREATE TRIGGER harness_fail_second_void BEFORE UPDATE ON sokhach.receipt_line
FOR EACH ROW EXECUTE FUNCTION public.fail_second_void()""")
    try:
        reject_call(pg, "void_receipt", c, 2, "void-fault", first["pid"], "sai",
                    error="HARNESS_FAIL_SECOND_VOID")
        require(allocations(pg, c, first["pid"]) == before and version(pg, c) == 2
                and pg.value(f"SELECT count(*) FROM sokhach.event WHERE customer_id={c} AND kind='void'") == "0",
                "void failure left first closed line or event")
    finally:
        pg.sql("DROP TRIGGER harness_fail_second_void ON sokhach.receipt_line; "
               "DROP FUNCTION public.fail_second_void()")
    result = call(pg, "void_receipt", c, 2, "void-ok", first["pid"], "sai phiếu")
    require(result["voided_lines"] == 2 and allocations(pg, c, first["pid"]) == []
            and allocations(pg, c, "PH-002") == other, "void touched wrong lines")
    pg.true("(SELECT count(*)=2 AND count(DISTINCT l.superseded_by_event)=1 "
        "AND bool_and(e.kind='void' AND e.\"before\"->'allocations' @> "
        "jsonb_build_array(jsonb_build_object('id',l.id,'month',l.debt_month,'kind',l.kind,"
        "'amount_vnd',l.amount_vnd::text))) FROM sokhach.receipt_line l "
        "JOIN sokhach.receipt r ON r.id=l.receipt_id "
        "JOIN sokhach.event e ON e.id=l.superseded_by_event "
        f"WHERE r.customer_id={c} AND r.pid='PH-001')", "void event/snapshot misses original ID")
    pg.true("(SELECT e.\"after\"->'allocations'='[]'::jsonb "
        "AND e.\"after\"->>'void_reason'='sai phiếu' "
        "AND r.voided_on IS NOT NULL AND r.voided_by_event=e.id "
        "FROM sokhach.receipt r JOIN sokhach.event e ON e.id=r.voided_by_event "
        f"WHERE r.customer_id={c} AND r.pid='PH-001')", "void after snapshot or receipt state wrong")
    require([r[1] for r in months(pg, c)] == ["60", "50"], "void balance wrong")
    reject_call(pg, "void_receipt", c, 3, "void-again", first["pid"], "lại", error="RECEIPT_ALREADY_VOID")


def check_opening_fifo(pg: Pg) -> None:
    c = new_book(pg, ("2026-01-01", 100), ("2026-02-01", 200))
    call(pg, "set_month_lock", c, 0, "fifo-open", "2026-01-01", "false")
    opening = pg.value(f"SELECT string_agg(amount_vnd::text,',' ORDER BY debt_month) FROM sokhach.opening_balance WHERE customer_id={c}")
    call(pg, "record_receipt", c, 1, "fifo-r", "2026-03-01", "THU TIỀN", 150)
    require(allocations(pg, c, "PH-001") == [("2026-01-01", "debt", "100"),
             ("2026-02-01", "debt", "50")], "receipt did not use old opening first")
    call(pg, "adjust_month", c, 2, "fifo-a", "2026-01-01", 60, "giá mới")
    require(allocations(pg, c, "PH-001") == [("2026-01-01", "debt", "150")]
            and [r[1] for r in months(pg, c)] == ["10", "200"], "adjustment did not reallocate FIFO")
    require(pg.value(f"SELECT string_agg(amount_vnd::text,',' ORDER BY debt_month) FROM sokhach.opening_balance WHERE customer_id={c}") == opening,
            "opening changed after reallocation")
    assert_allocations(pg, c)


def check_negative_receipt(pg: Pg) -> None:
    c = new_book(pg, ("2026-01-01", -50), ("2026-02-01", 100), ("2026-03-01", 20))
    call(pg, "record_receipt", c, 0, "negative-r1", "2026-04-01", "THU TIỀN", 130)
    require(allocations(pg, c, "PH-001") == [("2026-02-01", "debt", "100"),
             ("2026-03-01", "debt", "20"), ("2026-03-01", "advance", "10")],
            "negative opening consumed receipt or advance wrong")
    before = allocations(pg, c, "PH-001")
    reject_call(pg, "adjust_month", c, 1, "unknown-month", "2099-01-01", 5, "sai kỳ",
                error="MONTH_NOT_FOUND")
    require(version(pg, c) == 1 and allocations(pg, c, "PH-001") == before
            and pg.value(f"SELECT count(*) FROM sokhach.adjustment WHERE customer_id={c}") == "0"
            and pg.value(f"SELECT count(*) FROM sokhach.v_outstanding_month "
                         f"WHERE customer_id={c} AND debt_month='2099-01-01'") == "0",
            "unknown month changed advance or created a new last month")
    call(pg, "record_receipt", c, 1, "negative-r2", "2026-04-02", "THU TIỀN", 5)
    other = allocations(pg, c, "PH-002")
    call(pg, "void_receipt", c, 2, "negative-void", "PH-001", "sai")
    require([r[1] for r in months(pg, c)] == ["-50", "100", "15"]
            and allocations(pg, c, "PH-002") == other, "void altered negative opening or other receipt")


def check_input(pg: Pg) -> None:
    c = new_book(pg, ("2026-01-01", 1))
    month = pg.value("SELECT date_trunc('month',clock_timestamp() AT TIME ZONE 'Asia/Ho_Chi_Minh')::date")
    for key, amount, error in (("neg-zero", "-0", "INVALID_VND"),
                               ("overflow", "9223372036854775808", "INVALID_VND"),
                               ("decimal", "1.5", "INVALID_TRIP_INPUT")):
        reject_call(pg, "paste_trips", c, 0, key, month,
                    trip_json(amount), error=error)
    both = json.loads(trip_json("9223372036854775807"))
    both[0]["otherFeeVnd"] = "1"
    reject_call(pg, "paste_trips", c, 0, "sum-overflow", month, json.dumps(both),
                error="INVALID_VND")
    reject_call(pg, "paste_trips", c, 0, "null-trip", month, "null", error="INVALID_TRIPS")
    require(version(pg, c) == 0 and pg.value(f"SELECT count(*) FROM sokhach.trip WHERE customer_id={c}") == "0",
            "invalid amount inserted a trip")
    trip = call(pg, "paste_trips", c, 0, "missing-price", month, trip_json(None, month=month))["trip_ids"][0]
    reject_call(pg, "edit_trip_price", c, 1, "price-sum-overflow", trip,
                9223372036854775807, 1, error="INVALID_VND")
    row = next(t for t in call(pg, "get_ledger", c)["trips"] if t["id"] == trip)
    require(row["unit_price_vnd"] is None and row["amount_vnd"] is None
            and row["is_missing_price"] is True and call(pg, "get_ledger", c)["pending_count"] == 1,
            "NULL price became zero or entered balance")
    event = int(pg.value(f"INSERT INTO sokhach.event(customer_id,kind,actor,\"before\",\"after\") "
        f"VALUES ({c},'price_edit','harness','{{\"price\":{{}}}}','{{\"price\":{{}}}}') RETURNING id"))
    # Corrupt fixture and rejection share a transaction: no invalid price leaks
    # into later cross-customer reads such as list_offset_sources.
    pg.rejects(actor_sql("INSERT INTO sokhach.trip_price_rev(trip_id,customer_id,unit_price_vnd,other_fee_vnd,created_by_event) "
           f"VALUES ({trip},{c},9223372036854775807,1,{event}); "
           f"SELECT sokhach.adjust_trip({c},1,'adjust-overflow',{trip},1,'sửa')"),
           message="INVALID_VND")
    pg.true(f"NOT EXISTS (SELECT 1 FROM sokhach.trip_price_rev WHERE trip_id={trip} "
            "AND unit_price_vnd=9223372036854775807)", "overflow price fixture leaked")
    overflow = new_book(pg, ("2026-01-01", 9223372036854775807))
    fixture_open_month(pg, overflow, "2026-01-01")
    reject_call(pg, "adjust_month", overflow, 0, "month-overflow", "2026-01-01", 1,
                "sửa", error="INVALID_VND")
    require(version(pg, overflow) == 0 and pg.value(
        f"SELECT count(*) FROM sokhach.adjustment WHERE customer_id={overflow}") == "0",
        "overflow adjustment left partial money rows")
    event = int(pg.value("INSERT INTO sokhach.event(customer_id,kind,actor,\"before\",\"after\") "
        f"VALUES ({overflow},'adjust_month','harness','{{\"month\":\"2026-01-01\"}}',"
        "'{\"adjustment\":1}') RETURNING id"))
    pg.rejects(actor_sql("INSERT INTO sokhach.adjustment(customer_id,debt_month,amount_vnd,actor,created_by_event) "
           f"VALUES ({overflow},'2026-01-01',1,'harness',{event}); "
           f"SELECT sokhach.reallocate({overflow},'direct-overflow')"),
               message="INVALID_VND")
    pg.true(f"NOT EXISTS (SELECT 1 FROM sokhach.adjustment WHERE customer_id={overflow})",
            "overflow adjustment fixture leaked")


def check_dashboard(pg: Pg) -> None:
    before = call(pg, "get_dashboard")
    current = pg.value("SELECT date_trunc('month',now() AT TIME ZONE 'Asia/Ho_Chi_Minh')::date")
    recent = pg.value("SELECT (date_trunc('month',now() AT TIME ZONE 'Asia/Ho_Chi_Minh')-interval '2 months')::date")
    old = pg.value("SELECT (date_trunc('month',now() AT TIME ZONE 'Asia/Ho_Chi_Minh')-interval '7 months')::date")
    today = pg.value("SELECT (now() AT TIME ZONE 'Asia/Ho_Chi_Minh')::date")
    positive = new_book(pg, (old, 100), (recent, 200))
    credit = new_book(pg, ("2026-01-01", -50))
    zero = new_book(pg, ("2026-01-01", 0))
    classified = new_book(pg, (current, 25))
    commodity = int(pg.value("INSERT INTO sokhach.commodity(name) VALUES ('FAKE COMMODITY') RETURNING id"))
    pg.sql(f"UPDATE sokhach.customer SET commodity_id={commodity},transport_mode='CANG' WHERE id={classified}")
    no_base = int(pg.value("INSERT INTO sokhach.customer(name) VALUES ('FAKE NO BASELINE') RETURNING id"))
    batch = json.dumps([json.loads(trip_json(month=current))[0],
                        json.loads(trip_json(container="FAKE-D", month=current))[0]])
    call(pg, "paste_trips", positive, version(pg, positive), "dash-paste", current, batch)
    call(pg, "paste_trips", positive, version(pg, positive), "dash-missing", current,
         trip_json(None, container="FAKE-M", month=current))
    call(pg, "paste_trips", positive, version(pg, positive), "dash-pending", current,
         trip_json(container="FAKE-C", month=current))
    call(pg, "record_receipt", positive, version(pg, positive), "dash-receipt", today, "THU TIỀN", 25)
    call(pg, "void_receipt", positive, version(pg, positive), "dash-void", "PH-001", "dash void")
    result = call(pg, "get_dashboard")
    customers = call(pg, "list_customers")["customers"]
    active = [(c, call(pg, "get_ledger", c["id"])) for c in customers if c["status"] == "active"]
    positive_ledgers = [(c, ledger, int(ledger["total_outstanding_vnd"]))
                        for c, ledger in active if int(ledger["total_outstanding_vnd"]) > 0]
    negative_ledgers = [(c, ledger, int(ledger["total_outstanding_vnd"]))
                        for c, ledger in active if int(ledger["total_outstanding_vnd"]) < 0]
    require(int(result["receivable"]["total_vnd"]) - int(before["receivable"]["total_vnd"]) == 525
            and result["receivable"]["customers"] - before["receivable"]["customers"] == 2,
            f"dashboard receivable delta: {before['receivable']} -> {result['receivable']}")
    require(int(result["credit"]["total_vnd"]) - int(before["credit"]["total_vnd"]) == -50
            and result["credit"]["customers"] - before["credit"]["customers"] == 1,
            f"dashboard credit delta: {before['credit']} -> {result['credit']}")
    require(result["receivable"] == {"total_vnd": str(sum(x[2] for x in positive_ledgers)),
                                     "customers": len(positive_ledgers)},
            "dashboard positive get_ledger reconciliation")
    require(result["credit"] == {"total_vnd": str(sum(x[2] for x in negative_ledgers)),
                                 "customers": len(negative_ledgers)},
            "dashboard credit get_ledger reconciliation")
    receivable = int(result["receivable"]["total_vnd"])
    require(sum(int(x["receivable_vnd"]) for x in result["aging"]) == receivable,
            "dashboard aging total")
    require(sum(int(x["receivable_vnd"]) for x in result["by_commodity"]) == receivable,
            "dashboard commodity total")
    require([x["bucket"] for x in result["aging"]] == ["current", "1-2", "3-6", "over-6"],
            "dashboard aging buckets")
    require(any(x["commodity"] == "FAKE COMMODITY" and x["transport_mode"] == "CANG"
                and x["customers"] == 1 for x in result["by_commodity"]),
            "dashboard commodity grouping")
    expected_top = [x[0]["id"] for x in sorted(positive_ledgers,
                    key=lambda x: (-x[2], x[0]["name"], x[0]["id"]))[:10]]
    require([x["customer_id"] for x in result["top_debtors"]] == expected_top,
            "dashboard top debtor order")
    positive_top = next((x for x in result["top_debtors"] if x["customer_id"] == positive), None)
    require(positive_top is not None and positive_top["oldest_open_month"] == old,
            "dashboard oldest open month")
    aging = {x["bucket"]: int(x["receivable_vnd"]) for x in result["aging"]}
    before_aging = {x["bucket"]: int(x["receivable_vnd"]) for x in before["aging"]}
    require({key: aging[key] - before_aging[key] for key in aging}
            == {"current": 225, "1-2": 200, "3-6": 0, "over-6": 100},
            "dashboard aging month boundaries")
    require(result["today"]["trips"] - before["today"]["trips"] == 4
            and result["today"]["receipts"] - before["today"]["receipts"] == 1
            and int(result["today"]["received_vnd"]) - int(before["today"]["received_vnd"]) == 25
            and result["today"]["voids"] - before["today"]["voids"] == 1,
            "dashboard today event counts")
    actor = next(x for x in result["today"]["by_actor"] if x["actor"] == "harness")
    before_actor = next((x for x in before["today"]["by_actor"] if x["actor"] == "harness"),
                        {"trips": 0, "receipts": 0, "received_vnd": "0", "voids": 0})
    require(actor["trips"] - before_actor["trips"] == 4
            and actor["receipts"] - before_actor["receipts"] == 1
            and int(actor["received_vnd"]) - int(before_actor["received_vnd"]) == 25
            and actor["voids"] - before_actor["voids"] == 1, "dashboard actor counts")
    require(any(x["customer_id"] == no_base for x in result["todo"]["no_baseline"])
            and any(x["customer_id"] == positive for x in result["todo"]["missing_price"])
            and any(x["customer_id"] == positive for x in result["todo"]["pending_review"])
            and any(x["customer_id"] == credit for x in result["todo"]["credit"])
            and zero not in [x["customer_id"] for x in result["todo"]["credit"]], "dashboard todo boundaries")
    pg.sql("INSERT INTO sokhach.event(customer_id,kind,actor,at,\"before\",\"after\") "
           f"VALUES ({positive},'paste','late',(((now() AT TIME ZONE 'Asia/Ho_Chi_Minh')::date "
           "+ time '23:30') AT TIME ZONE 'Asia/Ho_Chi_Minh'),'{}','{\"trips\":[{}]}')")
    pg.sql("INSERT INTO sokhach.event(customer_id,kind,actor,at,\"before\",\"after\") "
           f"VALUES ({positive},'paste','tomorrow',((((now() AT TIME ZONE 'Asia/Ho_Chi_Minh')::date + 1) "
           "+ time '00:30') AT TIME ZONE 'Asia/Ho_Chi_Minh'),'{}','{\"trips\":[{}]}')")
    boundary = call(pg, "get_dashboard")
    require(boundary["today"]["trips"] == result["today"]["trips"] + 1
            and any(x["actor"] == "late" and x["trips"] == 1 for x in boundary["today"]["by_actor"])
            and not any(x["actor"] == "tomorrow" for x in boundary["today"]["by_actor"]),
            "dashboard Asia/Ho_Chi_Minh event boundary")


def check_actor(pg: Pg) -> None:
    c = new_book(pg, ("2026-01-01", 10))
    pg.rejects(f"SELECT sokhach.get_ledger({c})", message="ACTOR_REQUIRED")
    pg.rejects(f"SELECT sokhach.record_receipt({c},0,'actor-empty','2026-02-01','THU TIỀN',1)",
               message="ACTOR_REQUIRED")
    pg.rejects(actor_sql(f"SELECT sokhach.get_ledger({c})", " "), message="ACTOR_REQUIRED")
    require(json.loads(pg.value(actor_sql(f"SELECT sokhach.get_ledger({c})", "harness"),
                                user="v7_app"))["total_outstanding_vnd"] == "10",
            "app cannot read through allowed function")
    pg.rejects(f"SELECT sokhach.record_receipt({c},0,'actor-role','2026-02-01','THU TIỀN',1)",
               user="v7_app", message="ACTOR_REQUIRED")
    result = pg.value(actor_sql(f"SELECT sokhach.get_ledger({c})", "actor-a",
        search_path="CREATE TEMP TABLE customer(version bigint); INSERT INTO customer VALUES (999); "
                    "SET LOCAL search_path = pg_temp, public; "))
    require(json.loads(result)["total_outstanding_vnd"] == "10", "hostile search_path changed ledger")
    require(call(pg, "get_ledger", c, actor="actor-a")["status"] == "active"
            and call(pg, "get_ledger", c, actor="actor-b")["status"] == "active",
            "trial reader applied unexpected per-person ACL")
    pg.true("NOT EXISTS (SELECT 1 FROM pg_proc p WHERE p.pronamespace='sokhach'::regnamespace "
            "AND p.proname IN ('record_receipt','get_ledger') AND "
            "pg_get_function_arguments(p.oid) ~ '(^|, )actor ')",
            "public command accepts actor parameter")
    call(pg, "record_receipt", c, 0, "actor-ok", "2026-02-01", "THU TIỀN", 1,
         actor="actor-b")
    require(pg.value(f"SELECT actor FROM sokhach.event WHERE customer_id={c} AND kind='receipt'") == "actor-b",
            "event actor differs from SET LOCAL")


def check_csm_migration(pg: Pg) -> None:
    old_ref = "b49a752156bbc57e418fbf1a48838711b0ec4ee5"
    old_schema = run(["git", "show", old_ref + ":specs/v7-backend/schema-draft.sql"], cwd=ROOT).stdout
    old_functions = run(["git", "show", old_ref + ":cong-no-web-handoff/tools/v7_backend_functions.sql"], cwd=ROOT).stdout
    db = "webdebit_v7_csm_migration_test"
    pg.sql(f"CREATE DATABASE {db}", database="postgres")
    class CopyPg(Pg):
        def sql(self, sql, **kwargs):
            return super().sql(sql, **{**kwargs, "database": db})
    copy = CopyPg(pg.name, pg.run_id)
    copy.sql(re.sub(r"^CREATE ROLE .*;\n", "", old_schema, flags=re.M))
    copy.sql(old_functions)
    c = new_book(copy, ("2026-01-01", 100))
    old_result = call(copy, "record_receipt", c, 0, "old-retry", "2026-01-02", "THU TIỀN", 10)
    snapshot = copy.value(f"SELECT row_to_json(x) FROM sokhach.receipt x WHERE customer_id={c}")
    migration = (ROOT / "cong-no-web-handoff/tools/migrations/2026-10-21-v7-csm.sql").read_text(encoding="utf-8")
    copy.rejects(migration.replace("COMMIT;", "DO $$ BEGIN RAISE EXCEPTION 'CSM_MIGRATION_FAULT'; END $$; COMMIT;"),
                 message="CSM_MIGRATION_FAULT")
    copy.true("NOT EXISTS (SELECT FROM information_schema.columns WHERE table_schema='sokhach' "
              "AND table_name='receipt' AND column_name='reference')", "migration rollback left column")
    copy.sql(migration)
    copy.sql(migration)  # repeat is safe; no new events or financial writes
    copy.sql(REVIEW_MIGRATION.read_text(encoding="utf-8"))
    copy.sql(REVIEW_MIGRATION.read_text(encoding="utf-8"))
    copy.sql(NHAP_MIGRATION.read_text(encoding="utf-8"))
    copy.sql(NHAP_MIGRATION.read_text(encoding="utf-8"))
    copy.sql(MH_MIGRATION.read_text(encoding="utf-8"))
    copy.sql(MH_MIGRATION.read_text(encoding="utf-8"))
    copy.sql(DASHBOARD_MIGRATION.read_text(encoding="utf-8"))
    copy.sql(DASHBOARD_MIGRATION.read_text(encoding="utf-8"))
    copy.sql(LOCKED_TRIP_MIGRATION.read_text(encoding="utf-8"))
    copy.sql(SHEET_MIGRATION.read_text(encoding="utf-8"))
    copy.sql(SHEET_MIGRATION.read_text(encoding="utf-8"))
    copy.sql(MATRIX_MIGRATION.read_text(encoding="utf-8"))
    copy.sql(MATRIX_MIGRATION.read_text(encoding="utf-8"))
    copy.sql(DETAIL_MIGRATION.read_text(encoding="utf-8"))
    copy.sql(DETAIL_MIGRATION.read_text(encoding="utf-8"))
    copy.sql(SYNC_MIGRATION.read_text(encoding="utf-8"))
    copy.sql(SYNC_MIGRATION.read_text(encoding="utf-8"))
    copy.sql(LEGACY_RECEIPT_MIGRATION.read_text(encoding="utf-8"))
    copy.sql(LEGACY_RECEIPT_MIGRATION.read_text(encoding="utf-8"))
    require(json.loads(copy.value(f"SELECT (to_jsonb(x)-'reference')::text FROM sokhach.receipt x WHERE customer_id={c}"))
            == json.loads(snapshot),
            "migration changed receipt row")
    require(call(copy, "record_receipt", c, 0, "old-retry", "2026-01-02", "THU TIỀN", 10) == old_result,
            "old idempotency key broken by migration")
    catalog = "SELECT jsonb_object_agg(proname,pg_get_functiondef(oid)) FROM pg_proc WHERE pronamespace='sokhach'::regnamespace"
    require(json.loads(copy.value(catalog)) == json.loads(pg.value(catalog)), "migrated functions differ")
    check_csm_reference(copy)
    check_csm_locks(copy)
    from test_pg_v7_grants import check_catalog
    check_catalog(copy)
    # Sheet conflict commands exist only as migrations (hao order); standard files do not carry them yet.
    for migration in (SHEET_CONFLICT_MIGRATION, SHEET_CONFLICT_DATE_MIGRATION):
        copy.sql(migration.read_text(encoding="utf-8"))
        copy.sql(migration.read_text(encoding="utf-8"))
    check_sheet_conflict_resolution(copy)


def check_csm_reference(pg: Pg) -> None:
    c = new_book(pg, ("2026-01-01", 100))
    other = new_book(pg, ("2026-01-01", 100))
    def write(key, reference=None):
        return call(pg, "record_receipt", c, version(pg, c), key,
                    "2026-01-02", "THU TIỀN", 10, reference)
    require(not write("no-ref")["duplicate_reference"], "optional reference warned")
    require(not write("blank-ref", "  ")["duplicate_reference"], "blank reference warned")
    require(not write("first-ref", " FAKE-TXN USD/rate text ")["duplicate_reference"], "first reference warned")
    duplicate = write("duplicate-ref", "FAKE-TXN USD/rate text")
    require(duplicate["duplicate_reference"] and version(pg, c) == 4, "duplicate blocked or not warned")
    require(call(pg, "record_receipt", c, 3, "duplicate-ref", "2026-01-02", "THU TIỀN", 10,
                 "FAKE-TXN USD/rate text") == duplicate and version(pg, c) == 4, "retry wrote twice")
    reject_call(pg, "record_receipt", c, 4, "duplicate-ref", "2026-01-02", "THU TIỀN", 10,
                "different", error="IDEMPOTENCY_CONFLICT")
    require(not call(pg, "record_receipt", other, 0, "other-ref", "2026-01-02", "THU TIỀN", 1,
                     "FAKE-TXN USD/rate text")["duplicate_reference"], "cross-ledger warning")
    old_lines = allocations(pg, c, "PH-001")
    edited = call(pg, "edit_receipt_meta", c, 4, "edit-ref", "PH-001", None, None, "FAKE-TXN USD/rate text")
    require(edited["duplicate_reference"] and allocations(pg, c, "PH-001") == old_lines,
            "reference edit blocked or changed allocations")
    ledger = call(pg, "get_ledger", c)
    receipt = next(r for r in ledger["receipts"] if r["pid"] == "PH-001")
    require(receipt["reference"] == "FAKE-TXN USD/rate text", "GET lost reference")
    event = next(e for e in ledger["events"] if e["kind"] == "receipt_edit")
    require(event["before"]["reference"] is None and event["after"]["reference"] == receipt["reference"],
            "reference edit audit missing")
    call(pg, "edit_receipt_meta", c, 5, "clear-ref", "PH-001", None, None, " ")
    pg.true(f"(SELECT reference IS NULL FROM sokhach.receipt WHERE customer_id={c} AND pid='PH-001')",
            "clear reference did not store NULL")
    pg.rejects(f"UPDATE sokhach.receipt SET reference='unaudited' WHERE customer_id={c} AND pid='PH-001'",
               message="receipt change forbidden")
    require(call(pg, "get_ledger", c)["total_outstanding_vnd"] == "60", "text changed VND")
    call(pg, "void_receipt", c, 6, "void-ref", "PH-004", "fake reason")
    require(write("voided-ref", "FAKE-TXN USD/rate text")["duplicate_reference"], "voided reference ignored")
    unique = call(pg, "edit_receipt_meta", c, version(pg, c), "unique-ref", "PH-005", None, None, "FAKE-UNIQUE")
    require(not unique["duplicate_reference"], "receipt warned against itself")
    call(pg, "edit_receipt_meta", c, version(pg, c), "preserve-ref", "PH-005", None, "KHÁC")
    pg.true(f"(SELECT reference='FAKE-UNIQUE' FROM sokhach.receipt WHERE customer_id={c} AND pid='PH-005')",
            "omitted reference erased existing text")


def check_csm_locks(pg: Pg) -> None:
    c = new_book(pg, ("2026-01-01", 100))
    before = pg.value("SELECT clock_timestamp()")
    opened = call(pg, "set_month_lock", c, 0, "csm-open", "2026-01-01", "false", actor="fake-opener")
    call(pg, "paste_trips", c, 1, "csm-late-paste", "2026-01-01", trip_json(container="FAKE-LATE"))
    call(pg, "set_month_lock", c, 2, "csm-close", "2026-01-01", "true", actor="fake-closer")
    require(call(pg, "set_month_lock", c, 0, "csm-open", "2026-01-01", "false") == opened,
            "lock retry not stable")
    call(pg, "set_month_lock", c, 3, "csm-close-again", "2026-01-01", "true")
    reject_call(pg, "set_month_lock", c, 3, "csm-stale", "2026-01-01", "false", error="STALE_LEDGER")
    reject_call(pg, "set_month_lock", c, 4, "csm-invalid", "2026-01-02", "false", error="INVALID_MONTH_LOCK")
    events = [e for e in call(pg, "get_ledger", c)["events"] if e["kind"] == "month_lock"]
    require(len(events) == 3 and events[-1]["actor"] == "fake-opener"
            and events[-2]["actor"] == "fake-closer", "lock event count/actor")
    require(events[-1]["before"]["locked"] is True and events[-2]["before"]["locked"] is False,
            "default/explicit lock before snapshot wrong")
    require([e["after"] for e in events] == [
        {"month": "2026-01-01", "locked": True}, {"month": "2026-01-01", "locked": True},
        {"month": "2026-01-01", "locked": False}], "open/close events merged")
    pg.true(f"(SELECT bool_and(at>={lit(before)}::timestamptz AND at<=clock_timestamp()) "
            f"FROM sokhach.event WHERE customer_id={c} AND kind='month_lock')", "event timestamp")
    for snapshot in ({}, {"month": "2026-01-01"}, {"month": "2026-01-01", "locked": "false"},
                     {"month": "2026-02-01", "locked": False}):
        pg.rejects('INSERT INTO sokhach.event(customer_id,kind,actor,"before","after") '
                   f"VALUES ({c},'month_lock','fake',"
                   f"'{json.dumps({'month': '2026-01-01', 'locked': True})}',{lit(json.dumps(snapshot))})",
                   message="check constraint")
    pg.sql("CREATE FUNCTION public.csm_abort_lock() RETURNS trigger LANGUAGE plpgsql AS $$ "
           "BEGIN RAISE EXCEPTION 'CSM_ABORT'; END $$; "
           "CREATE TRIGGER csm_abort_lock BEFORE UPDATE ON sokhach.month_state "
           "FOR EACH ROW EXECUTE FUNCTION public.csm_abort_lock()")
    try:
        reject_call(pg, "set_month_lock", c, 4, "csm-rollback", "2026-01-01", "false", error="CSM_ABORT")
        pg.true(f"(SELECT count(*)=3 FROM sokhach.event WHERE customer_id={c} AND kind='month_lock')",
                "rollback left event")
        require(version(pg, c) == 4, "rollback changed version")
    finally:
        pg.sql("DROP TRIGGER csm_abort_lock ON sokhach.month_state; DROP FUNCTION public.csm_abort_lock()")


def check_locks(pg: Pg) -> str:
    c = new_book(pg, ("2026-01-01", 1))
    definition = pg.value("SELECT pg_get_functiondef(oid) FROM pg_proc WHERE pronamespace='sokhach'::regnamespace AND proname='edit_trip_price'")
    require(definition.index("_begin_command") < definition.index("clock_timestamp()") < definition.index("_month_open"),
            "price edit must read wall clock after customer lock")
    paste = pg.value("SELECT pg_get_functiondef(oid) FROM pg_proc WHERE pronamespace='sokhach'::regnamespace AND proname='paste_trips'")
    require("_month_open" not in paste, "paste still blocks locked months")
    pg.value(f"SELECT sokhach._month_open({c},'2026-10-01','2026-10-31 16:59:59+00')")
    pg.rejects(f"SELECT sokhach._month_open({c},'2026-10-01','2026-10-31 17:00:00+00')", message="MONTH_LOCKED")
    pg.value(f"SELECT sokhach._month_open({c},'2026-11-01','2026-10-31 17:00:00+00')")
    current = pg.value("SELECT date_trunc('month',clock_timestamp() AT TIME ZONE 'Asia/Ho_Chi_Minh')::date")
    old = pg.value(f"SELECT ({lit(current)}::date-interval '1 month')::date")
    trip = call(pg, "paste_trips", c, 0, "lock-old", old, trip_json(month=old))["trip_ids"][0]
    reject_call(pg, "edit_trip_price", c, 1, "lock-price", trip, 101, None, error="MONTH_LOCKED")
    current_trip = call(pg, "paste_trips", c, 1, "lock-current", current,
                        trip_json(container="LOCK-CURRENT", month=current))["trip_ids"][0]
    a, b = PsqlSession(pg, f"v7_lock_a_{c}"), PsqlSession(pg, f"v7_lock_b_{c}")
    try:
        a.send("BEGIN; SET LOCAL sokhach.actor='locker'; SELECT pg_backend_pid()")
        pid_a = int(a.line())
        a.send(f"SELECT sokhach.set_month_lock({c},2,'close-current','{current}',true)")
        require(json.loads(a.line())["version"] == 3, "lock did not stage")
        b.send("BEGIN; SET LOCAL sokhach.actor='writer'; SELECT pg_backend_pid()")
        pid_b = int(b.line())
        b.send(f"SELECT sokhach.paste_trips({c},3,'paste-after-lock','{current}',{lit(trip_json(container='LOCK-LATE',month=current))}::jsonb)")
        deadline = time.monotonic()+8
        while time.monotonic()<deadline and pg.value(f"SELECT {pid_a}=ANY(pg_blocking_pids({pid_b}))")!='t':
            time.sleep(0.05)
        require(pg.value(f"SELECT {pid_a}=ANY(pg_blocking_pids({pid_b}))")=='t', "paste did not wait for customer lock")
        a.send("COMMIT; SELECT 'done'")
        require(a.line()=="done", "lock commit")
        require(json.loads(b.line())["version"]==4, "locked-month paste did not proceed after customer lock")
        b.send("COMMIT; SELECT 'done'")
        require(b.line()=="done", "paste commit")
    finally:
        a.close()
        b.close()
    reject_call(pg, "edit_trip_price", c, 4, "price-locked-current", current_trip, 101, None, error="MONTH_LOCKED")
    before = (version(pg, c), pg.value(f"SELECT count(*) FROM sokhach.event WHERE customer_id={c}"))
    for name, args in (
            ("edit_trip_info", (current_trip, "carrier", "FAKE NEW")),
            ("delete_trip", (current_trip,)),
            ("adjust_trip", (current_trip, 120, "fake")),
            ("adjust_month", (current, 5, "fake"))):
        reject_call(pg, name, c, 4, "locked-" + name, *args, error="MONTH_LOCKED")
    require((version(pg, c), pg.value(f"SELECT count(*) FROM sokhach.event WHERE customer_id={c}")) == before,
            "locked trip edit wrote audit or version")
    call(pg, "set_month_lock", c, 4, "reopen-current", current, "false")
    a, b = PsqlSession(pg, f"v7_edit_a_{c}"), PsqlSession(pg, f"v7_edit_b_{c}")
    try:
        a.send("BEGIN; SET LOCAL sokhach.actor='locker'; SELECT pg_backend_pid()")
        pid_a = int(a.line())
        a.send(f"SELECT sokhach.set_month_lock({c},5,'close-current-again','{current}',true)")
        require(json.loads(a.line())["version"] == 6, "current-month close did not stage")
        b.send("BEGIN; SET LOCAL sokhach.actor='editor'; SELECT pg_backend_pid()")
        pid_b = int(b.line())
        b.send(f"SELECT sokhach.edit_trip_price({c},6,'edit-after-close',{current_trip},101,NULL)")
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline and pg.value(f"SELECT {pid_a}=ANY(pg_blocking_pids({pid_b}))") != "t":
            time.sleep(0.05)
        require(pg.value(f"SELECT {pid_a}=ANY(pg_blocking_pids({pid_b}))") == "t", "price edit did not wait for customer lock")
        a.send("COMMIT; SELECT 'done'")
        require(a.line() == "done", "close commit")
        b.proc.wait(timeout=10)
        stderr = b.proc.stderr.read() if b.proc.stderr else ""
        require("MONTH_LOCKED" in stderr and version(pg, c) == 6, "price edit crossed concurrent lock")
    finally:
        a.close()
        b.close()
    empty = pg.value(f"SELECT ({lit(current)}::date-interval '3 month')::date")
    call(pg, "set_month_lock", c, 6, "open-empty", empty, "false")
    ledger = call(pg, "get_ledger", c)
    locks = {r["month"]: r["locked"] for r in ledger["month_locks"]}
    require(ledger["today_month"]==current and locks[current] and not locks[empty]
            and not any(m["month"]==empty for m in ledger["months"]), "GET month lock flags")
    call(pg, "record_receipt", c, version(pg, c), "receipt-while-locked", current, "THU TIỀN", 1)
    return "VN clock boundary; price uses current month; paste serializes without month gate"


def check_concurrent(pg: Pg) -> str:
    c = new_book(pg, ("2026-01-01", 100))
    a, b = PsqlSession(pg, f"v7_a_{c}"), PsqlSession(pg, f"v7_b_{c}")
    try:
        a.send("BEGIN; SET LOCAL sokhach.actor='actor-a'; SELECT pg_backend_pid()")
        pid_a = int(a.line())
        a.send(f"SELECT sokhach.record_receipt({c},0,'concurrent-a','2026-02-01','THU TIỀN',70)")
        first = json.loads(a.line())
        b.send("BEGIN; SET LOCAL sokhach.actor='actor-b'; SELECT pg_backend_pid()")
        pid_b = int(b.line())
        b.send(f"SELECT sokhach.record_receipt({c},0,'concurrent-b','2026-02-02','THU TIỀN',70)")
        deadline = time.monotonic() + 8
        blocked = False
        while time.monotonic() < deadline:
            blocked = pg.value(f"SELECT {pid_a}=ANY(pg_blocking_pids({pid_b}))") == "t"
            if blocked:
                break
        require(blocked, "second receipt never blocked behind customer lock")
        a.send("COMMIT; SELECT 'committed'")
        require(a.line() == "committed", "first receipt did not commit")
        # ON_ERROR_STOP ends B on expected STALE_LEDGER; stderr is checked after exit.
        b.proc.wait(timeout=10)
        stderr = b.proc.stderr.read() if b.proc.stderr else ""
        require("STALE_LEDGER" in stderr, f"blocked stale command did not reject: {stderr[-500:]}")
        require(first["version"] == 1 and version(pg, c) == 1 and months(pg, c)[0][1] == "30"
                and pg.value(f"SELECT count(*) FROM sokhach.receipt WHERE customer_id={c}") == "1",
                "concurrent receipts overapplied debt")
        evidence = f"pg_blocking_pids observed: {pid_b} blocked by {pid_a}; stale rejected"
    finally:
        a.close()
        b.close()
    same = new_book(pg, ("2026-01-01", 100))
    a, b = PsqlSession(pg, f"v7_same_a_{same}"), PsqlSession(pg, f"v7_same_b_{same}")
    try:
        a.send("BEGIN; SET LOCAL sokhach.actor='same-a'; SELECT pg_backend_pid()")
        pid_a = int(a.line())
        sql = (f"SELECT sokhach.record_receipt({same},0,'same-key-concurrent',"
               "'2026-02-01','THU TIỀN',70)")
        a.send(sql)
        first = json.loads(a.line())
        b.send("BEGIN; SET LOCAL sokhach.actor='same-b'; SELECT pg_backend_pid()")
        pid_b = int(b.line())
        b.send(sql)
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline and pg.value(
                f"SELECT {pid_a}=ANY(pg_blocking_pids({pid_b}))") != "t":
            time.sleep(0.05)
        require(pg.value(f"SELECT {pid_a}=ANY(pg_blocking_pids({pid_b}))") == "t",
                "same-key command did not wait for first transaction")
        a.send("COMMIT; SELECT 'committed'")
        require(a.line() == "committed", "first same-key command did not commit")
        require(json.loads(b.line()) == first, "concurrent same-key retry changed result")
        b.send("COMMIT; SELECT 'committed'")
        require(b.line() == "committed", "second same-key command did not commit")
        require(version(pg, same) == 1 and pg.value(
            f"SELECT count(*) FROM sokhach.receipt WHERE customer_id={same}") == "1",
            "same-key concurrent command wrote twice")
    finally:
        a.close()
        b.close()
    return evidence + "; same-key returned stored result"


def check_pid_order(pg: Pg) -> None:
    c = new_book(pg, ("2026-01-01", 100))
    call(pg, "record_receipt", c, 0, "pid-first", "2026-02-01", "THU TIỀN", 60)
    call(pg, "record_receipt", c, 1, "pid-second", "2026-02-01", "THU TIỀN", 60)
    pg.true("'PH-B' COLLATE \"C\" < 'PH-a' COLLATE \"C\" AND "
            "'PH-a' COLLATE \"en-US-x-icu\" < 'PH-B' COLLATE \"en-US-x-icu\"",
            "test pid pair does not distinguish C from en-US ICU")
    expected = run_node("const m=require('./cong-no-web-handoff/preview/so-khach-v7-model.js');"
        "const d='01/02/2026',method='THU TIỀN';"
        "const r=(pid,amountVnd,kind)=>({pid,date:d,method,amountVnd,kind,voided:null});"
        "const book={months:[{key:'2026-01',trips:[{container:'C',unitPriceVnd:'100',"
        "otherFeeVnd:null}],adjustments:[],receipts:[r('PH-a','60','debt'),"
        "r('PH-B','40','debt'),r('PH-B','20','advance')]}]};"
        "console.log(JSON.stringify(m.planReallocation(book).lines.map(x=>"
        "[x.receipt.pid,x.receipt.kind,x.receipt.amountVnd]).sort((a,b)=>"
        "a[0]<b[0]?-1:a[0]>b[0]?1:a[1]<b[1]?-1:a[1]>b[1]?1:0)))")
    require(expected == [["PH-B", "debt", "60"], ["PH-a", "advance", "20"],
                         ["PH-a", "debt", "40"]], "JS mixed-case fixture changed")
    sql = ("BEGIN; ALTER TABLE sokhach.receipt DISABLE TRIGGER receipt_guard; "
           f"UPDATE sokhach.receipt SET pid=CASE pid WHEN 'PH-001' THEN 'PH-a' "
           f"ELSE 'PH-B' END WHERE customer_id={c}; "
           "SET CONSTRAINTS ALL IMMEDIATE; "  # deferred pair checks block ALTER TABLE
           "ALTER TABLE sokhach.receipt ENABLE TRIGGER receipt_guard; "
           "SET LOCAL sokhach.actor='harness'; "
           f"SELECT sokhach.reallocate({c},'pid-order'); "
           f"SELECT coalesce(jsonb_agg(jsonb_build_array(r.pid,l.kind,l.amount_vnd::text) "
           "ORDER BY r.pid COLLATE \"C\",l.kind),'[]'::jsonb) "
           "FROM sokhach.receipt_line l JOIN sokhach.receipt r ON r.id=l.receipt_id "
           f"WHERE r.customer_id={c} AND l.superseded_by_event IS NULL; ROLLBACK")
    result = json.loads(pg.value(sql).splitlines()[-1])
    require(result == expected,
            f"same-day pid order differs from JS: {result}")


def check_ledger_fee(pg: Pg) -> None:
    # check_fee seeded these three shapes on active fake customer 1.
    rows = {r["id"]: r for r in call(pg, "get_ledger", 1)["trips"]}
    require({101, 102, 103} <= rows.keys(),
            "7.18a fee fixture missing; cannot check get_ledger parity")
    expected = run_node("const m=require('./cong-no-web-handoff/preview/so-khach-v7-model.js'); "
        "const x=[{container:'X',unitPriceVnd:'120',otherFeeVnd:null},"
        "{container:'X',unitPriceVnd:null,otherFeeVnd:'7'},"
        "{container:null,unitPriceVnd:null,otherFeeVnd:'7'}]; "
        "console.log(JSON.stringify(x.map(t=>{const r=m.tripAmount(t);return {amount:r.amountVnd?.toString()??null,missing:r.isMissingPrice,fee:r.isFeeOnly}})))")
    for trip_id, model in zip((101, 102, 103), expected, strict=True):
        row = rows[trip_id]
        require((row["amount_vnd"], row["is_missing_price"], row["is_fee_only"]) ==
                (model["amount"], model["missing"], model["fee"]),
                f"tripAmount parity failed for {trip_id}")
    require(rows[101]["other_fee_vnd"] is None and rows[102]["amount_vnd"] is None
            and rows[103]["event_date"] is None
            and call(pg, "get_ledger", 1)["pending_count"] == 1,
            "NULL storage or pending count wrong")
    c = new_book(pg, ("2026-01-01", 0))
    current = pg.value("SELECT date_trunc('month',clock_timestamp() AT TIME ZONE 'Asia/Ho_Chi_Minh')::date")
    ids = call(pg, "paste_trips", c, 0, "space-container", current,
               trip_json(None, container="   ", month=current))["trip_ids"]
    call(pg, "edit_trip_price", c, 1, "space-fee", ids[0], None, 7)
    row = next(t for t in call(pg, "get_ledger", c)["trips"] if t["id"] == ids[0])
    require(row["is_fee_only"] is False and row["is_missing_price"] is True,
            "whitespace container differs from JS truthiness")
    require(any(m["month"] == current and m["outstanding_vnd"] == "0"
                for m in call(pg, "get_ledger", c)["months"]),
            "month with only missing-price trip absent")
    fee_only = json.dumps([{"container": None, "carrier": None, "date": None,
        "from": None, "to": None, "unitPriceVnd": None, "otherFeeVnd": "7",
        "note": "fee only", "src": "FAKE"}])
    fee_id = call(pg, "paste_trips", c, version(pg, c), "fee-no-date", current,
                  fee_only)["trip_ids"][0]
    fee_row = next(t for t in call(pg, "get_ledger", c)["trips"] if t["id"] == fee_id)
    require(fee_row["event_date"] is None and fee_row["amount_vnd"] == "7"
            and fee_row["is_fee_only"] is True, "undated fee was not entered and counted")
    require(any(m["month"] == current and m["outstanding_vnd"] == "7"
                for m in call(pg, "get_ledger", c)["months"]),
            "undated fee missing from month balance")
    normal = json.loads(trip_json())[0]
    normal["date"] = None
    reject_call(pg, "paste_trips", c, version(pg, c), "trip-no-date", current,
                json.dumps([normal]), error="INVALID_TRIP_INPUT")


def check_model(pg: Pg) -> None:
    # Identical two-month fixture and operation order in Node and PostgreSQL.
    js = r"""
const m=require('./cong-no-web-handoff/preview/so-khach-v7-model.js');
const book={months:['2026-01','2026-02'].map((key,i)=>({key,
  trips:[{container:'FAKE-C',unitPriceVnd:'100',otherFeeVnd:null}],receipts:[],adjustments:[]}))};
const month=k=>book.months.find(x=>x.key===k);
const apply=()=>{const p=m.planReallocation(book);for(const x of book.months)x.receipts=x.receipts.filter(r=>r.voided!==null);
  for(const x of p.lines)month(x.monthKey).receipts.push(x.receipt)};
const add=(pid,date,amount)=>{const p=m.planReceipt(book,{pid,date,method:'THU TIỀN',amountVnd:amount});
  for(const x of p.lines)month(x.monthKey).receipts.push({pid,date,method:'THU TIỀN',amountVnd:x.amountVnd,kind:x.kind,voided:null})};
const snap=()=>({months:m.outstandingByMonth(book).map(x=>[x.monthKey,x.outstandingVnd.toString()]),
  total:m.monthChain(book).totalOutstandingVnd.toString(),
  receipts:Object.fromEntries(['PH-001','PH-002','PH-003'].map(pid=>[pid,book.months.flatMap(x=>
    x.receipts.filter(r=>r.pid===pid&&r.voided===null).map(r=>[x.key,r.kind,r.amountVnd]))]))});
const out=[];add('PH-001','03/01/2026','120');out.push(snap());
const t=month('2026-01').trips[0];
for(const [target,note] of [['80','lần một'],['110','lần hai']]){
  month('2026-01').adjustments.push(m.planAdjustment(book,{'2026-01':true},
    {monthKey:'2026-01',lineId:'2026-01#0',newAmountVnd:target,reason:note}));apply();out.push(snap())}
for(const amount of ['+20','-10']){month('2026-01').adjustments.push(
  m.planMonthAdjustment(book,{monthKey:'2026-01',amount,reason:'tháng'}));apply();out.push(snap())}
add('PH-002','02/01/2026','20');out.push(snap());
for(const date of ['04/01/2026','02/01/2026']){
  const edit=m.planReceiptEdit(book,'PH-001',{date});
  for(const x of edit.lines)month(x.monthKey).receipts[x.index]=x.receipt;
  apply();out.push(snap());
}
const voided=m.planVoid(book,'PH-001','sai','20/10/2026');
for(const x of voided.lines)month(x.monthKey).receipts[x.index]=x.receipt;out.push(snap());
add('PH-003','04/01/2026','30');out.push(snap());
console.log(JSON.stringify(out));
"""
    expected = run_node(js)
    c = new_book(pg)
    for month in ("2026-01-01", "2026-02-01"):
        call(pg, "set_month_lock", c, version(pg, c), "open-" + month, month, "false")
        call(pg, "paste_trips", c, version(pg, c), "paste-" + month, month, trip_json(container="FAKE-" + month, month=month))
    trip = int(pg.value(f"SELECT id FROM sokhach.trip WHERE customer_id={c} AND debt_month='2026-01-01'"))
    actions = [
        ("record_receipt", ("2026-01-03", "THU TIỀN", 120)),
        ("adjust_trip", (trip, 80, "lần một")),
        ("adjust_trip", (trip, 110, "lần hai")),
        ("adjust_month", ("2026-01-01", 20, "tháng")),
        ("adjust_month", ("2026-01-01", -10, "tháng")),
        ("record_receipt", ("2026-01-02", "THU TIỀN", 20)),
        ("edit_receipt_meta", ("PH-001", "2026-01-04", None)),
        ("edit_receipt_meta", ("PH-001", "2026-01-02", None)),
        ("void_receipt", ("PH-001", "sai")),
        ("record_receipt", ("2026-01-04", "THU TIỀN", 30)),
    ]
    for index, ((name, args), want) in enumerate(zip(actions, expected, strict=True), 1):
        result = call(pg, name, c, version(pg, c), f"model-{index}", *args)
        got_rows = months(pg, c)
        got = {"months": [[m, amount] for m, amount, _ in got_rows],
               "total": call(pg, "get_ledger", c)["total_outstanding_vnd"],
               "receipts": {pid: [[m[:7], kind, amount] for m, kind, amount in allocations(pg, c, pid)]
                            for pid in ("PH-001", "PH-002", "PH-003")}}
        require(got == want, f"JS/SQL operation {index} {name} differs: {got} != {want}")
        if name in ("adjust_trip", "adjust_month", "edit_receipt_meta"):
            prior = expected[index - 2]["receipts"]
            changed = sorted(pid for pid in want["receipts"]
                             if {r[0] for r in prior[pid]} !=
                                {r[0] for r in want["receipts"][pid]})
            returned = sorted(item["pid"] for item in result["reallocated"]
                              if {line["month"][:7] for line in item["before"]} !=
                                 {line["month"][:7] for line in item["after"]})
            require(returned == changed,
                    f"operation {index} changed receipt-month list differs: {returned} != {changed}")
        assert_allocations(pg, c)


def check_model_edges(pg: Pg) -> None:
    c = new_book(pg, ("2025-12-01", 100))
    current = pg.value("SELECT date_trunc('month',clock_timestamp() AT TIME ZONE 'Asia/Ho_Chi_Minh')::date")
    first = call(pg, "record_receipt", c, 0, "edge-advance", "2026-02-01", "THU TIỀN", 150)
    require(first["overpayment_vnd"] == "50" and allocations(pg, c, "PH-001") ==
            [("2025-12-01", "debt", "100"), ("2025-12-01", "advance", "50")],
            "receipt over debt did not create advance")
    missing = call(pg, "paste_trips", c, 1, "edge-missing", current,
                   trip_json(None, month=current))["trip_ids"][0]
    require(call(pg, "get_ledger", c)["pending_count"] == 1,
            "missing price did not remain pending after receipt")
    call(pg, "edit_trip_price", c, 2, "edge-price", missing, 20, None)
    require(call(pg, "get_ledger", c)["pending_count"] == 0 and
            allocations(pg, c, "PH-001")[-1] == (current, "advance", "30"),
            "pricing pending trip did not move advance to last month")
    priced = call(pg, "paste_trips", c, 3, "edge-paste-after-receipt", current,
                  trip_json("40", container="FAKE-NEW", month=current))["trip_ids"][0]
    require(priced != missing and allocations(pg, c, "PH-001") ==
            [("2025-12-01", "debt", "100"), (current, "debt", "50")],
            "paste after receipt did not reallocate FIFO")
    call(pg, "void_receipt", c, 4, "edge-void", "PH-001", "sai")
    before = months(pg, c)
    call(pg, "adjust_month", c, 5, "edge-adjust-after-void", current, 10, "sửa")
    require(allocations(pg, c, "PH-001") == [] and
            [int(row[1]) for row in months(pg, c)] == [int(row[1]) for row in before[:-1]] +
            [int(before[-1][1]) + 10], "adjustment after void moved canceled receipt")
    assert_allocations(pg, c)


def check_golden(pg: Pg) -> None:
    fixture = run_node("console.log(JSON.stringify(require('./cong-no-web-handoff/preview/so-khach-v7-fixture.js')))")
    c = new_book(pg)
    trips = [{"month": m["key"] + "-01", "trip": t} for m in fixture["months"] for t in m["trips"]]
    receipts: dict[str, dict] = {}
    for month in fixture["months"]:
        for line in month["receipts"]:
            require(line["voided"] is None, "golden fixture contains unsupported voided line")
            item = receipts.setdefault(line["pid"], {"pid": line["pid"], "date": line["date"],
                "method": line["method"], "amount": 0, "lines": []})
            item["amount"] += int(line["amountVnd"])
            item["lines"].append({"month": month["key"] + "-01", "kind": line.get("kind", "debt"),
                                  "amount": line["amountVnd"]})
    # One psql transaction; large fixture travels on stdin, never command line.
    script = """BEGIN;
DO $fixture$ DECLARE t jsonb; r jsonb; l jsonb; v_event bigint; v_trip bigint;
 v_receipt bigint; v_lines jsonb; v_line jsonb;
BEGIN
INSERT INTO sokhach.event(customer_id,kind,actor,"before","after")
VALUES (CUSTOMER,'paste','harness','{}','{"trips":[]}') RETURNING id INTO v_event;
FOR t IN SELECT value FROM jsonb_array_elements(TRIPS::jsonb) LOOP
 INSERT INTO sokhach.trip(customer_id,debt_month,event_date,container,carrier,origin,destination,
 note,source_ref,created_by_event) VALUES (CUSTOMER,(t->>'month')::date,
  CASE WHEN t->'trip'->>'date' IS NULL THEN NULL
      ELSE to_date(t->'trip'->>'date','DD/MM/YYYY') END,
 t->'trip'->>'container',t->'trip'->>'carrier',
 t->'trip'->>'from',t->'trip'->>'to',t->'trip'->>'note',t->'trip'->>'src',v_event)
 RETURNING id INTO v_trip;
 INSERT INTO sokhach.trip_price_rev(trip_id,customer_id,unit_price_vnd,other_fee_vnd,created_by_event)
 VALUES(v_trip,CUSTOMER,(t->'trip'->>'unitPriceVnd')::bigint,
 (t->'trip'->>'otherFeeVnd')::bigint,v_event);
END LOOP;
FOR r IN SELECT value FROM jsonb_array_elements(RECEIPTS::jsonb) LOOP
 v_receipt:=nextval(pg_get_serial_sequence('sokhach.receipt','id'));
 v_lines:='[]'::jsonb;
 FOR l IN SELECT value FROM jsonb_array_elements(r->'lines') LOOP
  v_line:=jsonb_build_object('id',nextval(pg_get_serial_sequence('sokhach.receipt_line','id')),
   'month',l->>'month','kind',l->>'kind','amount_vnd',l->>'amount');
  v_lines:=v_lines||jsonb_build_array(v_line);
 END LOOP;
 INSERT INTO sokhach.event(customer_id,kind,actor,"before","after") VALUES
 (CUSTOMER,'receipt','harness','{}',jsonb_build_object('receipt',v_receipt,'pid',r->>'pid',
  'allocations',v_lines)) RETURNING id INTO v_event;
 INSERT INTO sokhach.receipt(id,customer_id,pid,date,method,amount_vnd,created_by_event)
 OVERRIDING SYSTEM VALUE VALUES(v_receipt,CUSTOMER,r->>'pid',to_date(r->>'date','DD/MM/YYYY'),
 r->>'method',(r->>'amount')::bigint,v_event);
 FOR l IN SELECT value FROM jsonb_array_elements(v_lines) LOOP
  INSERT INTO sokhach.receipt_line(id,receipt_id,customer_id,debt_month,kind,amount_vnd,created_by_event)
  OVERRIDING SYSTEM VALUE VALUES((l->>'id')::bigint,v_receipt,CUSTOMER,(l->>'month')::date,
  l->>'kind',(l->>'amount_vnd')::bigint,v_event);
 END LOOP;
END LOOP;
END $fixture$;
COMMIT;
"""
    script = script.replace("CUSTOMER", str(c)).replace("TRIPS", lit(json.dumps(trips, ensure_ascii=False)))
    script = script.replace("RECEIPTS", lit(json.dumps(list(receipts.values()), ensure_ascii=False)))
    p = run(["docker", "exec", "-i", *pg.env, pg.name, "psql", "-X", "-v", "ON_ERROR_STOP=1",
             "-U", "postgres", "-d", DATABASE], input_text=script, timeout=120)
    require(p.returncode == 0, "golden fixture load failed")
    ledger = call(pg, "get_ledger", c)
    expected = run_node("const m=require('./cong-no-web-handoff/preview/so-khach-v7-model.js');"
        "const f=require('./cong-no-web-handoff/preview/so-khach-v7-fixture.js');"
        "const x=m.monthChain(f);console.log(JSON.stringify({months:x.months.map(r=>"
        "[r.key,r.chargesVnd.toString(),r.receivedVnd.toString(),r.endOfMonthVnd.toString(),"
        "r.lineCount,r.tripCount]),total:x.totalOutstandingVnd.toString(),"
        "ph101:m.planReallocation(f).lines.filter(x=>x.receipt.pid==='PH-101').map(x=>"
        "[x.monthKey+'-01',x.receipt.kind,x.receipt.amountVnd]),"
        "plan:m.planReallocation(f).lines.map(x=>"
        "[x.receipt.pid,x.monthKey,x.receipt.kind,x.receipt.amountVnd]),"
        "changed:m.planReallocation(f).changedPids}))")
    got = []
    counts = {month: sum(t["month"][:7] == month for t in ledger["trips"])
              for month in (row["month"][:7] for row in ledger["months"])}
    for row in ledger["months"]:
        m = row["month"][:7]
        charges = sum(int(t["amount_vnd"] or 0) for t in ledger["trips"] if t["month"][:7] == m)
        received = sum(int(a["amount_vnd"]) for r in ledger["receipts"] for a in r["allocations"]
                       if r["voided_on"] is None and a["superseded_by_event"] is None
                       and a["month"][:7] == m)
        trip_count = sum(t["month"][:7] == m and not t["is_fee_only"] for t in ledger["trips"])
        got.append([m, str(charges), str(received), row["end_of_month_vnd"], counts[m], trip_count])
    require(got == expected["months"] and ledger["total_outstanding_vnd"] == expected["total"]
            and len(ledger["months"]) == 11, f"golden monthly totals differ: {got}")
    ph101 = [[line["month"], line["kind"], line["amount_vnd"]]
             for receipt in ledger["receipts"] if receipt["pid"] == "PH-101"
             for line in receipt["allocations"] if line["superseded_by_event"] is None]
    require(ph101 == expected["ph101"] and len(ph101) == 2,
            "PH-101 two-month allocation differs from JS plan")
    require(ledger["pending_count"] == run_node(
        "const m=require('./cong-no-web-handoff/preview/so-khach-v7-model.js');"
        "const f=require('./cong-no-web-handoff/preview/so-khach-v7-fixture.js');"
        "console.log(JSON.stringify(m.pendingCounts(f).missingPrice))"), "golden pending_count differs")
    fee = next(t for t in ledger["trips"] if t["id"] == int(pg.value(
        f"SELECT id FROM sokhach.trip WHERE customer_id={c} AND source_ref='CH:900'")))
    require(fee["is_fee_only"] is True and fee["event_date"] is None
            and fee["amount_vnd"] == "1310000"
            and fee["is_missing_price"] is False, "CH:900 fee-only classification differs")
    replay = pg.value("BEGIN; SET LOCAL sokhach.actor='golden'; "
        f"SELECT sokhach.reallocate({c},'golden-rollback'); "
        "SELECT coalesce(jsonb_agg(jsonb_build_array(r.pid,to_char(l.debt_month,'YYYY-MM'),"
        "l.kind,l.amount_vnd::text) ORDER BY r.pid COLLATE \"C\",l.debt_month,l.kind), '[]'::jsonb) "
        f"FROM sokhach.receipt_line l JOIN sokhach.receipt r ON r.id=l.receipt_id "
        f"WHERE r.customer_id={c} AND l.superseded_by_event IS NULL; ROLLBACK")
    changes, got_plan = map(json.loads, replay.splitlines()[-2:])
    require(expected["changed"] and set(expected["changed"]).issubset(
        {change["pid"] for change in changes}), "golden reallocate made no expected changes")
    require(sorted(got_plan) == sorted(expected["plan"]),
            "golden reallocate differs from independent JS plan")
    require(pg.value(f"SELECT count(*) FROM sokhach.event WHERE customer_id={c} AND "
                     "idempotency_key='golden-rollback'") == "0", "golden replay did not rollback")


def check_snapshots(pg: Pg) -> None:
    c = new_book(pg, ("2026-01-01", 60), ("2026-02-01", 60))
    call(pg, "record_receipt", c, 0, "snap-receipt", "2026-03-01", "THU TIỀN", 100)
    call(pg, "set_month_lock", c, 1, "snap-open", "2026-01-01", "false")
    old = pg.value("SELECT jsonb_agg(jsonb_build_object('id',l.id,'month',l.debt_month,"
        "'kind',l.kind,'amount_vnd',l.amount_vnd::text) ORDER BY l.id)::text "
        f"FROM sokhach.receipt_line l WHERE l.customer_id={c}")
    result = call(pg, "adjust_month", c, 2, "snap-adjust", "2026-01-01", 10, "sửa")
    require(len(result["reallocated"]) == 1, "changed allocation lacks reallocation result")
    event_id = result["reallocated"][0]["event_id"]
    event = json.loads(pg.value(f"SELECT jsonb_build_object('before',\"before\",'after',\"after\") "
                                   f"FROM sokhach.event WHERE id={event_id}"))
    require(event["before"]["allocations"] == json.loads(old)
            and event["after"]["allocations"] == result["reallocated"][0]["after"],
            "reallocation snapshot mismatches row IDs and amounts")
    pg.true(f"(SELECT count(*)=2 AND bool_and(superseded_by_event={event_id}) "
        f"FROM sokhach.receipt_line WHERE customer_id={c} AND id IN "
        f"(SELECT (x->>'id')::bigint FROM jsonb_array_elements({lit(old)}::jsonb) x))",
        "original allocations not superseded by snapshot event")
    require(allocations(pg, c, "PH-001") == [("2026-01-01", "debt", "70"),
            ("2026-02-01", "debt", "30")], "same-month-set reallocation tuple wrong")
    assert_allocations(pg, c)
    receipt_id = int(pg.value(f"SELECT id FROM sokhach.receipt WHERE customer_id={c} AND pid='PH-001'"))
    pg.rejects("INSERT INTO sokhach.receipt_line(receipt_id,customer_id,debt_month,kind,amount_vnd,created_by_event) "
               f"VALUES ({receipt_id},{c},'2026-01-01','debt',1,999999999)", message="foreign key")
    pg.rejects("INSERT INTO sokhach.event(customer_id,kind,actor,\"before\",\"after\") "
               f"VALUES ({c},'reallocation','harness','{{}}','{{\"allocations\":[]}}')",
               message="check constraint")
    pg.rejects("INSERT INTO sokhach.event(customer_id,kind,actor,\"before\",\"after\") "
               f"VALUES ({c},'reallocation','harness','{{\"allocations\":[]}}','{{}}')",
               message="check constraint")

    fault = new_book(pg, ("2026-01-01", 100), ("2026-02-01", 100))
    call(pg, "set_month_lock", fault, 0, "fault-open", "2026-01-01", "false")
    current = pg.value("SELECT date_trunc('month',clock_timestamp() AT TIME ZONE 'Asia/Ho_Chi_Minh')::date")
    trip = call(pg, "paste_trips", fault, 1, "fault-base-trip", current, trip_json(month=current))["trip_ids"][0]
    call(pg, "record_receipt", fault, 2, "fault-base-receipt", "2026-03-01", "THU TIỀN", 150)
    pg.sql("CREATE FUNCTION public.harness_abort() RETURNS trigger LANGUAGE plpgsql AS $$ "
           "BEGIN RAISE EXCEPTION 'HARNESS_ABORT'; END $$")
    try:
        operations = [
            ("record_receipt", ("2026-03-02", "THU TIỀN", 10), "receipt_line", "INSERT"),
            ("edit_receipt_meta", ("PH-001", "2026-03-03", None), "receipt", "UPDATE"),
            ("void_receipt", ("PH-001", "sai"), "receipt_line", "UPDATE"),
            ("adjust_trip", (trip, 101, "sửa"), "adjustment", "INSERT"),
            ("adjust_month", ("2026-01-01", 5, "sửa"), "adjustment", "INSERT"),
            ("edit_trip_price", (trip, 110, None), "trip_price_rev", "INSERT"),
            ("paste_trips", (current, trip_json(month=current)), "trip", "INSERT"),
        ]
        tables = ("event", "trip", "trip_price_rev", "adjustment", "receipt",
                  "receipt_line", "idempotency")
        def state() -> tuple:
            return (version(pg, fault), tuple(pg.value("SELECT coalesce(jsonb_agg(to_jsonb(x) "
                    "ORDER BY to_jsonb(x)::text),'[]'::jsonb) FROM "
                    f"(SELECT * FROM sokhach.{t} WHERE customer_id={fault}) x") for t in tables),
                    tuple(months(pg, fault)),
                    tuple(allocations(pg, fault, "PH-001")))
        for i, (name, args, table, timing) in enumerate(operations, 1):
            before = state()
            pg.sql(f"CREATE TRIGGER harness_abort_{i} BEFORE {timing} ON sokhach.{table} "
                   "FOR EACH ROW EXECUTE FUNCTION public.harness_abort()")
            try:
                reject_call(pg, name, fault, version(pg, fault), f"fault-{i}", *args,
                            error="HARNESS_ABORT")
                require(state() == before, f"{name} left partial rows/version/balance after abort")
            finally:
                pg.sql(f"DROP TRIGGER harness_abort_{i} ON sokhach.{table}")
    finally:
        pg.sql("DROP FUNCTION public.harness_abort()")
    success = [
        ("paste_trips", (current, trip_json("20", month=current)), "paste"),
        ("edit_trip_price", (trip, 110, None), "price_edit"),
        ("adjust_trip", (trip, 115, "sửa"), "adjust_trip"),
        ("adjust_month", ("2026-01-01", 5, "sửa"), "adjust_month"),
        ("record_receipt", ("2026-03-02", "THU TIỀN", 10), "receipt"),
        ("edit_receipt_meta", ("PH-002", "2026-03-04", None), "receipt_edit"),
        ("void_receipt", ("PH-002", "sai"), "void"),
    ]
    for i, (name, args, kind) in enumerate(success, 1):
        key = f"snap-success-{i}"
        call(pg, name, fault, version(pg, fault), key, *args)
        assert_allocations(pg, fault)
        events = json.loads(pg.value("SELECT coalesce(json_agg(json_build_object('kind',kind,"
            "'before',\"before\",'after',\"after\")),'[]'::json)::text FROM sokhach.event "
            f"WHERE customer_id={fault} AND idempotency_key={lit(key)} AND kind={lit(kind)}"))
        require(len(events) == 1 and isinstance(events[0]["before"], dict)
                and isinstance(events[0]["after"], dict) and bool(events[0]["after"]),
                f"{name} missing main event snapshot")
        if kind not in ("paste", "receipt"):
            require(bool(events[0]["before"]), f"{name} missing before snapshot")


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


def check_immutable(pg: Pg) -> None:
    for table, column in [("event", "actor"), ("trip", "container"), ("trip_price_rev", "unit_price_vnd"),
                          ("adjustment", "amount_vnd"), ("idempotency", "request_hash"),
                          ("opening_balance", "amount_vnd"), ("legacy_row", "source_total_vnd")]:
        pg.true(f"EXISTS (SELECT 1 FROM pg_trigger WHERE tgrelid='sokhach.{table}'::regclass AND NOT tgisinternal AND tgname LIKE '%immutable%')",
                f"missing immutable trigger on {table}")
        pg.rejects(f"UPDATE sokhach.{table} SET {column}={column} WHERE false", user="v7_app")
        pg.rejects(f"DELETE FROM sokhach.{table} WHERE false", user="v7_app")
    pg.rejects("UPDATE sokhach.opening_balance SET amount_vnd=101 WHERE id=1", message="immutable row")
    pg.rejects("DELETE FROM sokhach.legacy_row WHERE id=1", message="immutable row")


def check_roles(pg: Pg) -> None:
    pg.true("NOT EXISTS (SELECT 1 FROM pg_namespace n CROSS JOIN LATERAL "
            "aclexplode(coalesce(n.nspacl, acldefault('n',n.nspowner))) a "
            "WHERE n.nspname='sokhach' AND a.grantee=0 AND a.privilege_type='USAGE')",
            "PUBLIC has schema usage")
    for role in ("v7_app", "v7_reader"):
        pg.true(f"has_schema_privilege('{role}','sokhach','USAGE')", f"{role} lacks schema usage")
        for relation in ("customer", "cutover", "opening_balance", "trip", "receipt", "event",
                         "v_outstanding_month", "v_month_chain"):
            pg.true(f"NOT has_table_privilege('{role}','sokhach.{relation}','SELECT') AND "
                    f"NOT has_table_privilege('{role}','sokhach.{relation}','INSERT') AND "
                    f"NOT has_table_privilege('{role}','sokhach.{relation}','UPDATE') AND "
                    f"NOT has_table_privilege('{role}','sokhach.{relation}','DELETE')",
                    f"{role} can read/write {relation}")
        pg.rejects("SELECT * FROM sokhach.v_outstanding_month", user=role)
    public_commands = ("paste_trips", "edit_trip_price", "adjust_trip", "adjust_month",
                       "record_receipt", "edit_receipt_meta", "void_receipt", "set_month_lock", "review_trip", "edit_trip_info", "delete_trip", "edit_legacy_trip", "delete_legacy_trip",
                       "get_ledger", "list_customers", "get_dashboard", "list_sheet_trip_refs", "record_offset", "void_offset",
                       "get_receivables_matrix", "get_receivables_detail",
                       "edit_offset_date", "list_offset_sources", "import_cutover", "verify_cutover_customer",
                       "verify_cutover", "activate_cutover", "activate_cutover_customer")
    allowed = ",".join(lit(name) for name in public_commands)
    pg.true("(SELECT count(*) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace "
            f"WHERE n.nspname='sokhach' AND p.proname IN ({allowed})) = {len(public_commands)}",
            "public command missing or overloaded")
    for role in ("v7_app", "v7_reader"):
        forbidden = pg.value("SELECT coalesce(string_agg(p.oid::regprocedure::text,','), '') "
            "FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace "
            f"WHERE n.nspname='sokhach' AND p.proname NOT IN ({allowed}) "
            f"AND has_function_privilege({lit(role)},p.oid,'EXECUTE')")
        require(not forbidden, f"{role} may execute private helper: {forbidden}")
    pg.true("(SELECT count(*) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace "
            f"WHERE n.nspname='sokhach' AND p.proname NOT IN ({allowed})) >= 18",
            "private helper inventory unexpectedly incomplete")


def check_numbers(pg: Pg) -> None:
    pg.true("(SELECT data_type='bigint' FROM information_schema.columns WHERE table_schema='sokhach' AND table_name='opening_balance' AND column_name='amount_vnd')",
            "opening money not bigint")
    pg.true("(SELECT is_nullable='YES' AND data_type='bigint' FROM information_schema.columns WHERE table_schema='sokhach' AND table_name='trip_price_rev' AND column_name='other_fee_vnd')",
            "source fee NULL/bigint lost")
    pg.rejects("INSERT INTO sokhach.opening_balance(customer_id,cutover_id,debt_month,amount_vnd,source_tab,source_row,created_by_event) VALUES (1,1,'2026-03-01',NULL,'FAKE',4,1)")
    pg.rejects("SELECT 9223372036854775808::bigint", message="out of range")
    pg.true("(SELECT standard_bucket_vnd IS NOT NULL FROM sokhach.cutover_month_check WHERE debt_month='2026-01-01')",
            "seed standard bucket missing")
    pg.true("(SELECT data_type='bigint' AND is_nullable='YES' FROM information_schema.columns "
            "WHERE table_schema='sokhach' AND table_name='cutover_month_check' "
            "AND column_name='opening_anchor_vnd')", "first source anchor column missing")


def check_gate_view(pg: Pg) -> None:
    require(pg.value("SELECT count(*) FROM sokhach.v_outstanding_month") == "0", "draft leaked into balance")
    # Direct status moves characterize trigger/view only; they do not prove command reconciliation.
    pg.sql("UPDATE sokhach.cutover_customer SET status='verified' WHERE customer_id=1")
    require(pg.value("SELECT count(*) FROM sokhach.v_outstanding_month") == "0", "verified customer leaked")
    pg.sql("UPDATE sokhach.cutover SET status='verified' WHERE id=1")
    require(pg.value("SELECT count(*) FROM sokhach.v_outstanding_month") == "0", "verified cutover leaked")
    pg.sql("UPDATE sokhach.cutover SET status='active' WHERE id=1")
    require(pg.value("SELECT count(*) FROM sokhach.v_outstanding_month") == "0", "one-sided active leaked")
    pg.sql("UPDATE sokhach.cutover_customer SET status='active' WHERE customer_id=1")
    require(pg.value("SELECT string_agg(debt_month::text || ':' || outstanding_vnd::text, ',' ORDER BY debt_month) FROM sokhach.v_outstanding_month") ==
            "2026-01-01:100,2026-02-01:200", "active monthly amounts wrong")
    require(pg.value("SELECT string_agg(end_of_month_vnd::text, ',' ORDER BY debt_month) FROM sokhach.v_month_chain") == "100,300",
            "monthly cumulative view wrong")


def check_legacy(pg: Pg) -> None:
    require(pg.value("SELECT coalesce(sum(outstanding_vnd),0) FROM sokhach.v_outstanding_month") == "300",
            "legacy total added to balance")
    pg.rejects("UPDATE sokhach.legacy_row SET source_total_vnd=123 WHERE id=1", message="immutable row")
    pg.rejects("DELETE FROM sokhach.legacy_row WHERE id=1", message="immutable row")


def check_import_guard(pg: Pg) -> None:
    for index in ("event_import_once", "event_one_cutover_per_customer"):
        pg.true(f"EXISTS (SELECT 1 FROM pg_indexes WHERE schemaname='sokhach' AND indexname='{index}' AND indexdef LIKE '%UNIQUE%')",
                f"missing unique {index}")
    pg.rejects("INSERT INTO sokhach.event(customer_id,kind,actor,\"before\",\"after\",cutover_id) VALUES (1,'import','test','{}','{\"cutover\":1}',1)")
    pg.rejects("INSERT INTO sokhach.cutover_customer(customer_id,cutover_id,expected_control_total_vnd,report_sha256,source_rows,imported_rows,quarantined_rows,skipped_with_reason_rows,unresolved_exceptions) SELECT customer_id,cutover_id,300,report_sha256,0,0,0,0,0 FROM sokhach.cutover_customer WHERE customer_id=1")


def check_negative(pg: Pg) -> None:
    customer = new_book(pg, ("2026-01-01", -50))
    require(pg.value(f"SELECT outstanding_vnd FROM sokhach.v_outstanding_month WHERE customer_id={customer}") == "-50",
            "negative opening clamped or omitted")


def check_events(pg: Pg) -> None:
    pg.rejects("INSERT INTO sokhach.event(customer_id,kind,actor,\"before\",\"after\") VALUES (1,'receipt','test',NULL,'{\"receipt\":1}')")
    pg.rejects("INSERT INTO sokhach.event(customer_id,kind,actor,\"before\",\"after\") VALUES (1,'receipt','test','{}','{}')")
    pg.true("EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid='sokhach.receipt_line'::regclass AND conname='receipt_line_created_by_event_customer_id_fkey') OR EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid='sokhach.receipt_line'::regclass AND contype='f' AND pg_get_constraintdef(oid) LIKE '%created_by_event, customer_id%')",
            "receipt line event/customer FK missing")


def check_evidence(pg: Pg) -> str:
    for table in ("cutover_month_check", "opening_balance", "legacy_row"):
        pg.true(f"EXISTS (SELECT 1 FROM pg_trigger WHERE tgrelid='sokhach.{table}'::regclass AND NOT tgisinternal AND tgfoid='sokhach.guard_cutover_evidence()'::regprocedure)",
                f"evidence guard absent on {table}")
    # check_gate_view moved customer and cutover through draft -> verified -> active.
    pg.true("EXISTS (SELECT 1 FROM sokhach.cutover AS c JOIN sokhach.cutover_customer AS cc "
            "ON cc.cutover_id=c.id WHERE c.id=1 AND cc.customer_id=1 "
            "AND c.status='active' AND cc.status='active')", "evidence fixture not active")
    pg.rejects("UPDATE sokhach.cutover_month_check SET bucket_vnd=91 WHERE customer_id=1 AND debt_month='2026-01-01'", message="cutover evidence frozen")
    pg.rejects("INSERT INTO sokhach.cutover_month_check(customer_id,cutover_id,debt_month) VALUES (1,1,'2026-03-01')", message="cutover evidence frozen")
    pg.rejects("DELETE FROM sokhach.cutover_month_check WHERE customer_id=1 AND debt_month='2026-01-01'", message="cutover evidence frozen")
    pg.rejects("INSERT INTO sokhach.opening_balance(customer_id,cutover_id,debt_month,amount_vnd,source_tab,source_row,created_by_event) VALUES (1,1,'2026-03-01',1,'FAKE',4,1)", message="cutover evidence frozen")
    pg.rejects("INSERT INTO sokhach.legacy_row(customer_id,cutover_id,debt_month,kind,display,source_tab,source_row,created_by_event) VALUES (1,1,'2026-03-01','trip','{}','FAKE',4,1)", message="cutover evidence frozen")
    pg.rejects("UPDATE sokhach.cutover SET control_total_vnd=301 WHERE id=1", message="cutover status transition forbidden")
    pg.rejects("UPDATE sokhach.cutover_customer SET report_sha256=repeat('c',64) WHERE customer_id=1", message="cutover customer transition order forbidden")
    holder = PsqlSession(pg, f"v7_holder_{pg.run_id}")
    worker = None
    observed = None
    try:
        holder.send("BEGIN")
        holder.send("SELECT pg_backend_pid() FROM sokhach.cutover WHERE id=1 FOR UPDATE")
        holder_pid = int(holder.line())
        worker_name = f"v7_worker_{pg.run_id}"
        worker = subprocess.Popen(
            ["docker", "exec", "--env", f"PGAPPNAME={worker_name}", "--env",
             "PGOPTIONS=-c statement_timeout=10000", pg.name, "psql", "-X", "-qAt",
             "-v", "ON_ERROR_STOP=1", "-U", "postgres", "-d", DATABASE, "-c",
             "INSERT INTO sokhach.cutover_month_check(customer_id,cutover_id,debt_month) VALUES (1,1,'2026-03-01')"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            encoding="utf-8", errors="replace")
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            snapshot = pg.value(
                "SELECT coalesce(string_agg(pid::text || ':' || pg_blocking_pids(pid)::text,','), '') "
                f"FROM pg_stat_activity WHERE application_name='{worker_name}'")
            if re.search(rf"\b{holder_pid}\b", snapshot):
                observed = snapshot
                break
            if worker.poll() is not None:
                break
            time.sleep(0.05)  # polling; only pg_blocking_pids counts as evidence
        require(observed is not None, "direct evidence DML did not block on cutover holder via pg_blocking_pids")
    finally:
        holder.close()
        if worker is not None:
            try:
                out, err = worker.communicate(timeout=12)
            except subprocess.TimeoutExpired:
                worker.kill()
                out, err = worker.communicate()
                raise HarnessError("direct evidence worker timed out") from None
            require(worker.returncode != 0 and "cutover evidence frozen" in err,
                    f"worker must reject evidence after lock release: {out} {err[-500:]}")
    return f"trigger freeze and pg_blocking_pids observed: {observed}"


def check_fee(pg: Pg) -> None:
    # Two event-linked fake trips plus fee-only row under active fake customer.
    event = int(pg.value("INSERT INTO sokhach.event(customer_id,kind,actor,\"before\",\"after\") "
        "VALUES (1,'paste','test','{}','{\"trips\":[]}') RETURNING id"))
    pg.sql(f"""BEGIN;
INSERT INTO sokhach.trip(id,customer_id,debt_month,event_date,container,created_by_event)
OVERRIDING SYSTEM VALUE VALUES (101,1,'2026-03-01','2026-03-04','FAKE-1',{event}),
       (102,1,'2026-04-01','2026-04-04','FAKE-2',{event}),
       (103,1,'2026-05-01',NULL,NULL,{event});
INSERT INTO sokhach.trip_price_rev(trip_id,customer_id,unit_price_vnd,other_fee_vnd,created_by_event)
VALUES (101,1,120,NULL,{event}),(102,1,NULL,7,{event}),(103,1,NULL,7,{event});
COMMIT;""")
    pg.rejects(f"""BEGIN;
INSERT INTO sokhach.trip(id,customer_id,debt_month,event_date,container,created_by_event)
OVERRIDING SYSTEM VALUE VALUES (104,1,'2026-06-01',NULL,NULL,{event});
INSERT INTO sokhach.trip_price_rev(trip_id,customer_id,unit_price_vnd,other_fee_vnd,created_by_event)
VALUES (104,1,120,NULL,{event});
COMMIT;""", message="INVALID_FEE_ONLY_DATE")
    pg.rejects(f"INSERT INTO sokhach.trip(id,customer_id,debt_month,event_date,container,created_by_event) "
               f"OVERRIDING SYSTEM VALUE VALUES (104,1,'2026-06-01',NULL,'FAKE-4',{event})",
               message="trip_missing_date_fee_only")
    pg.sql("SELECT setval(pg_get_serial_sequence('sokhach.trip','id'),103,true)")
    require(pg.value("SELECT other_fee_vnd IS NULL FROM sokhach.trip_price_rev WHERE trip_id=101") == "t",
            "stored NULL fee changed")
    require(pg.value("SELECT string_agg(debt_month::text || ':' || outstanding_vnd::text, ',' ORDER BY debt_month) FROM sokhach.v_outstanding_month WHERE customer_id=1") ==
            "2026-01-01:100,2026-02-01:200,2026-03-01:120,2026-05-01:7",
            "NULL fee/missing price/fee-only SQL view differs")


def check_monthly_identity(pg: Pg) -> None:
    c = new_book(pg, ("2026-01-01", 500), ("2026-02-01", -50), ("2026-03-01", 0))
    call(pg, "set_month_lock", c, 0, "identity-open", "2026-02-01", "false")
    call(pg, "record_receipt", c, 1, "identity-r", "2026-04-01", "THU TIỀN", 100)
    rows = call(pg, "get_ledger", c)["months"]
    require(rows[0]["charges_vnd"] == "500" and rows[0]["end_of_month_vnd"] == "400",
            "opening absent from charges or counted twice")
    call(pg, "adjust_month", c, 2, "identity-a", "2026-02-01", -25, "giảm")
    rows = call(pg, "get_ledger", c)["months"]
    require(rows[1]["charges_vnd"] == "-75" and rows[1]["outstanding_vnd"] == "-75",
            "signed opening/adjustment missing from charges")


def check_field_adjustment(pg: Pg) -> None:
    c = new_book(pg, ("2026-01-01", 0))
    call(pg, "set_month_lock", c, 0, "field-open", "2026-01-01", "false")
    trip = call(pg, "paste_trips", c, 1, "field-paste", "2026-01-01", trip_json(container="FIELD-PRICED"))["trip_ids"][0]
    missing = call(pg, "paste_trips", c, 2, "field-missing", "2026-01-01", trip_json(None, container="FIELD-MISSING"))["trip_ids"][0]
    call(pg, "set_month_lock", c, 3, "field-open-again", "2026-01-01", "false")
    for expected_version, key, field, value, delta in (
            (4, "field-unit-1", "unit_price_vnd", 120, "20"),
            (5, "field-unit-2", "unit_price_vnd", 130, "10"),
            (6, "field-fee-1", "other_fee_vnd", 7, "7"),
            (7, "field-fee-2", "other_fee_vnd", 9, "2"),
            (8, "field-unit-3", "unit_price_vnd", 140, "10")):
        result = call(pg, "adjust_trip", c, expected_version, key, trip, None, "ghi chú", field, value)
        require(result["delta_vnd"] == delta, f"field current value double-counted: {key}")
        require(call(pg, "adjust_trip", c, expected_version, key, trip, None, "ghi chú", field, value) == result,
                "field retry not idempotent")
    reject_call(pg, "adjust_trip", c, 4, "field-unit-1", trip, None, "ghi chú", "unit_price_vnd", 121,
                error="IDEMPOTENCY_CONFLICT")
    rows = call(pg, "get_ledger", c)
    require([a["amount_vnd"] for a in rows["adjustments"]] == ["20", "10", "7", "2", "10"]
            and rows["total_outstanding_vnd"] == "149", "field deltas or final balance wrong")
    original = next(t for t in rows["trips"] if t["id"] == trip)
    require(original["unit_price_vnd"] == "100" and original["other_fee_vnd"] is None,
            "locked edit changed original price or NULL storage")
    require(all(a["note"] == "ghi chú" for a in rows["adjustments"]), "field note lost")
    edits = [e for e in reversed(rows["events"]) if e["kind"] == "adjust_trip"]
    require(edits[1]["before"]["new_value_vnd"] == "120" and edits[1]["after"]["new_value_vnd"] == "130"
            and edits[2]["before"]["new_value_vnd"] == "0", "field snapshots lost current value/NULL-fee semantics")
    reject_call(pg, "adjust_trip", c, 9, "field-no-price", missing, None, "", "other_fee_vnd", 5,
                error="TRIP_HAS_NO_PRICE")
    reject_call(pg, "adjust_trip", c, 9, "field-invalid", trip, None, "", "invalid", 5,
                error="INVALID_ADJUSTMENT")
    reject_call(pg, "adjust_trip", c, 9, "field-negative", trip, None, "", "unit_price_vnd", -1,
                error="INVALID_ADJUSTMENT")
    reject_call(pg, "adjust_trip", c, 9, "field-overflow", trip, None, "", "unit_price_vnd", 9223372036854775807,
                error="INVALID_VND")
    require(version(pg, c) == 9, "rejected field adjustment changed version")
    require(call(pg, "adjust_trip", c, 9, "field-legacy", trip, 159, "legacy")["delta_vnd"] == "10",
            "legacy total amount route broke")
    require(call(pg, "adjust_trip", c, 10, "field-after-legacy", trip, None, "", "unit_price_vnd", 155)["delta_vnd"] == "5",
            "field edit ignored current total after legacy adjustment")
    # GET audit money must be strings before JavaScript parses JSON, including old numeric price snapshots.
    call(pg, "set_month_lock", c, 11, "field-reopen", "2026-01-01", "false")
    call(pg, "edit_trip_price", c, 12, "field-big-price", missing, 9007199254740993, None)
    event = next(e for e in call(pg, "get_ledger", c)["events"] if e["kind"] == "price_edit")
    require(event["after"]["price"]["unit_price_vnd"] == "9007199254740993"
            and event["before"]["price"]["unit_price_vnd"] is None,
            "GET price history loses integer precision or turns NULL into zero")


def check_adjustment_source(pg: Pg) -> None:
    c = new_book(pg, ("2026-01-01", 0))
    call(pg, "set_month_lock", c, 0, "source-open", "2026-01-01", "false")
    trip = call(pg, "paste_trips", c, 1, "source-paste", "2026-01-01", trip_json())["trip_ids"][0]
    call(pg, "set_month_lock", c, 2, "source-open-again", "2026-01-01", "false")
    first = call(pg, "adjust_trip", c, 3, "source-unit", trip, None, "", "unit_price_vnd", 120)
    fee = call(pg, "adjust_trip", c, 4, "source-fee", trip, None, "", "other_fee_vnd", 7)
    require(first["delta_vnd"] == "20" and fee["delta_vnd"] == "7", "unit/fee deltas wrong")
    pg.true(f"(SELECT field='other_fee_vnd' AND new_value_vnd=7 FROM sokhach.adjustment "
            f"WHERE id={fee['adjustment_id']})", "fee intent not stored in adjustment")
    event = pg.value(f"SELECT created_by_event FROM sokhach.adjustment WHERE id={fee['adjustment_id']}")
    # Disposable fake DB only: owner deliberately corrupts one audit value, restores trigger in same transaction.
    pg.sql("BEGIN; SET LOCAL ROLE sokhach_owner; "
           "ALTER TABLE sokhach.event DISABLE TRIGGER event_immutable; "
           f"UPDATE sokhach.event SET \"after\"=jsonb_set(\"after\",'{{new_value_vnd}}','\"999\"'::jsonb) WHERE id={event}; "
           "ALTER TABLE sokhach.event ENABLE TRIGGER event_immutable; COMMIT")
    pg.true(f"(SELECT \"after\"->>'new_value_vnd'='999' FROM sokhach.event WHERE id={event})",
            "audit tampering experiment did not change audit")
    last = call(pg, "adjust_trip", c, 5, "source-unit-after-audit", trip, None, "", "unit_price_vnd", 130)
    require(last["delta_vnd"] == "10", "money still depends on corrupted audit fee")
    pg.true(f"(SELECT string_agg(field || ':' || new_value_vnd::text,',' ORDER BY created_by_event) "
            f"FROM sokhach.adjustment WHERE customer_id={c})='unit_price_vnd:120,other_fee_vnd:7,unit_price_vnd:130'",
            "typed unit/fee values not stored in event order")
    rows = call(pg, "get_ledger", c)
    require(rows["total_outstanding_vnd"] == "137"
            and [a["amount_vnd"] for a in rows["adjustments"]] == ["20", "7", "10"],
            "locked unit/fee/unit sequence double-counted")
    require(rows["trips"][0]["unit_price_vnd"] == "100" and rows["trips"][0]["other_fee_vnd"] is None,
            "typed adjustments changed original price/NULL fee")
    call(pg, "adjust_trip", c, 6, "source-total", trip, 147, "direct total")
    call(pg, "adjust_month", c, 7, "source-month", "2026-01-01", 3, "month")
    pg.true(f"(SELECT count(*) FROM sokhach.adjustment WHERE customer_id={c} "
            "AND field IS NULL AND new_value_vnd IS NULL)=2", "direct total/month intent must stay NULL")
    for field, value in (("'unit_price_vnd'", "NULL"), ("NULL", "1"), ("'invalid'", "1"), ("'other_fee_vnd'", "-1")):
        pg.rejects("INSERT INTO sokhach.adjustment(customer_id,debt_month,trip_id,amount_vnd,actor,created_by_event,field,new_value_vnd) "
                   f"SELECT customer_id,debt_month,trip_id,amount_vnd,actor,created_by_event,{field},{value} "
                   f"FROM sokhach.adjustment WHERE id={first['adjustment_id']}", message="check constraint")
    zero = call(pg, "adjust_trip", c, 8, "source-zero", trip, None, "", "other_fee_vnd", 0)
    pg.true(f"(SELECT field='other_fee_vnd' AND new_value_vnd=0 FROM sokhach.adjustment "
            f"WHERE id={zero['adjustment_id']})", "zero fee rejected or stored as NULL")
    require(zero["delta_vnd"] == "-7", "zero fee ignored stored fee")
    call(pg, "set_month_lock", c, 9, "source-reopen", "2026-01-01", "false")
    call(pg, "edit_trip_price", c, 10, "source-price-revision", trip, 200, 30)
    call(pg, "set_month_lock", c, 11, "source-relock", "2026-01-01", "false")
    revised = call(pg, "adjust_trip", c, 12, "source-after-revision", trip, None, "", "unit_price_vnd", 220)
    require(revised["delta_vnd"] == "-20" and call(pg, "get_ledger", c)["total_outstanding_vnd"] == "253",
            "fee adjustment before latest price revision leaked into current fee")


def check_shipper_write_sync(pg: Pg) -> None:
    c = new_book(pg, ("2026-01-01", 0))
    cut = pg.value(f"SELECT cutover_id FROM sokhach.cutover_customer WHERE customer_id={c}")
    pg.sql(f"INSERT INTO sokhach.baseline_trip_ref VALUES ({cut},'BK1','SHIP-BASE','2026-01-10')")
    call(pg, "set_month_lock", c, 0, "ship-open", "2026-01-01", "false")
    row = json.loads(trip_json(container="SHIP-C", shipper="SAIGON A"))[0] | {"date": "10/01/2026"}
    first = call(pg, "paste_trips", c, version(pg, c), "ship-first", "2026-01-01", json.dumps([row]))["trip_ids"][0]
    second = call(pg, "paste_trips", c, version(pg, c), "ship-second", "2026-01-01",
                  json.dumps([row]))["trip_ids"][0]

    def trip(trip_id):
        return next(t for t in call(pg, "get_ledger", c)["trips"] if t["id"] == trip_id)

    require(trip(first)["shipper"] == "SAIGON A", "paste lost shipper")
    require(trip(second)["status"] == "pending_review" and trip(second)["shipper"] == "SAIGON A",
            "pending paste lost shipper")
    call(pg, "review_trip", c, version(pg, c), "ship-confirm", second, "confirm", "đối chiếu xong")
    require(trip(second)["shipper"] == "SAIGON A", "review lost shipper")
    call(pg, "edit_trip_info", c, version(pg, c), "ship-origin", first, "origin", "DIEN BIEN")
    require(trip(first)["shipper"] == "SAIGON A", "info edit lost shipper")
    call(pg, "edit_trip_info", c, version(pg, c), "ship-edit", first, "shipper", "HA NOI B")
    require(trip(first)["shipper"] == "HA NOI B", "shipper field rejected")
    require(call(pg, "get_ledger", c)["total_outstanding_vnd"] == "200", "shipper edits changed money")


def check_fee_intent_after_price(pg: Pg) -> None:
    c = new_book(pg, ("2026-01-01", 0))
    cut = pg.value(f"SELECT cutover_id FROM sokhach.cutover_customer WHERE customer_id={c}")
    pg.sql(f"INSERT INTO sokhach.baseline_trip_ref VALUES ({cut},'BK1','FEE-BASE','2026-01-10')")
    call(pg, "set_month_lock", c, 0, "fee-open", "2026-01-01", "false")
    row = json.loads(trip_json(container="FEE-C"))[0] | {"date": "10/01/2026"}
    trip = call(pg, "paste_trips", c, version(pg, c), "fee-paste", "2026-01-01", json.dumps([row]))["trip_ids"][0]
    plus = call(pg, "adjust_trip", c, version(pg, c), "fee-plus", trip, None, "", "other_fee_vnd", 7)
    require(plus["delta_vnd"] == "7", "fee +7 delta wrong")
    call(pg, "edit_trip_price", c, version(pg, c), "fee-price", trip, 100, 30)
    # 100 unit + (30 fee + 7 stale delta) = 137: a price edit never absorbs older deltas.
    require(call(pg, "get_ledger", c)["total_outstanding_vnd"] == "137", "stale fee delta lost")
    ten = call(pg, "adjust_trip", c, version(pg, c), "fee-ten", trip, None, "", "other_fee_vnd", 10)
    require(ten["delta_vnd"] == "-27" and call(pg, "get_ledger", c)["total_outstanding_vnd"] == "110",
            "fee intent must land on the effective fee after a price revision")


def check_future_receipt(pg: Pg) -> None:
    c = new_book(pg, ("2026-01-01", 500))
    today = pg.value("SELECT (clock_timestamp() AT TIME ZONE 'Asia/Ho_Chi_Minh')::date")
    tomorrow = pg.value(f"SELECT ({lit(today)}::date+1)::text")
    first = call(pg, "record_receipt", c, 0, "date-today", today, "THU TIỀN", 100)
    require(version(pg, c) == 1, "today receipt rejected")
    before = call(pg, "get_ledger", c)
    reject_call(pg, "record_receipt", c, 1, "date-tomorrow", tomorrow, "THU TIỀN", 10,
                error="FUTURE_RECEIPT_DATE")
    reject_call(pg, "edit_receipt_meta", c, 1, "date-edit-tomorrow", first["pid"], tomorrow, None,
                error="FUTURE_RECEIPT_DATE")
    require(call(pg, "get_ledger", c) == before and version(pg, c) == 1,
            "future receipt changed version, events, allocations or receipt")
    call(pg, "edit_receipt_meta", c, 1, "date-edit-today", first["pid"], today, "KHÁC")
    require(version(pg, c) == 2, "today metadata edit rejected")
    for name in ("record_receipt", "edit_receipt_meta"):
        definition = pg.value("SELECT pg_get_functiondef(oid) FROM pg_proc "
            f"WHERE pronamespace='sokhach'::regnamespace AND proname='{name}'")
        require(definition.index("_begin_command") < definition.index("clock_timestamp()"),
                f"{name} reads receipt clock before customer lock")


def check_void_get(pg: Pg) -> None:
    c = new_book(pg, ("2026-01-01", 60), ("2026-02-01", 60))
    first = call(pg, "record_receipt", c, 0, "void-get-r", "2026-03-01", "THU TIỀN", 100)
    fixture_open_month(pg, c, "2026-01-01")
    call(pg, "adjust_month", c, 1, "void-get-a", "2026-01-01", -30, "đổi phân bổ")
    at_void = allocations(pg, c, first["pid"])
    call(pg, "void_receipt", c, 2, "void-get-v", first["pid"], "nhập trùng")
    receipt = call(pg, "get_ledger", c)["receipts"][0]
    require(receipt["voided_by_event"] is not None, "GET lacks void event")
    shown = [(line["month"], line["kind"], line["amount_vnd"]) for line in receipt["allocations"]
             if line["superseded_by_event"] == receipt["voided_by_event"]]
    require(shown == at_void and len(receipt["allocations"]) > len(shown),
            "void shows reallocation history or loses current allocation")


# CT-2SO uses disposable fake opening only. Snapshot covers both books and every
# pair-command artifact, not identity sequences (PostgreSQL sequences do not roll back).
def ct_total(pg: Pg, customer: int) -> int:
    return int(call(pg, "get_ledger", customer)["total_outstanding_vnd"])


def ct_record(pg: Pg, source: int, target: int, key: str, amount: int = 50,
              date: str = "2026-03-01") -> dict:
    return call(pg, "record_offset", target, version(pg, target), source,
                version(pg, source), key, date, amount)


def ct_snapshot(pg: Pg, source: int, target: int) -> str:
    ids = f"({source},{target})"
    queries = []
    for table, where in (
        ("customer", f"id IN {ids}"), ("event", f"customer_id IN {ids}"),
        ("receipt", f"customer_id IN {ids}"), ("receipt_line", f"customer_id IN {ids}"),
        ("idempotency", f"customer_id IN {ids}"),
        ("offset_pair", f"source_customer_id IN {ids} OR target_customer_id IN {ids}"),
        ("offset_command", f"low_customer_id IN {ids} OR high_customer_id IN {ids}"),
    ):
        queries.append(f"'{table}',(SELECT coalesce(jsonb_agg(to_jsonb(t) ORDER BY to_jsonb(t)::text),'[]') "
                       f"FROM sokhach.{table} t WHERE {where})")
    return pg.value("SELECT jsonb_build_object(" + ",".join(queries) + ")")


def check_ct_01(pg: Pg) -> None:
    a = new_book(pg, ("2026-01-01", -100_000_000))
    b = new_book(pg, ("2026-01-01", 50_000_000))
    pair = ct_record(pg, a, b, "ct01", 50_000_000)
    require((ct_total(pg, a), ct_total(pg, b)) == (-50_000_000, 0), "CT01 balances")
    require(pair["source_version"] == pair["target_version"] == 1, "CT01 versions")
    for book, other in ((a, b), (b, a)):
        events = [e for e in call(pg, "get_ledger", book)["events"] if e["kind"] != "import"]
        require(len(events) == 1 and events[0]["actor"] == "harness", "CT01 audit cardinality/actor")
        require(events[0]["counterparty_customer_id"] == other, "CT01 audit link")
    require(call(pg, "get_ledger", a)["outgoing_offsets"][0]["amount_vnd"] == "-50000000",
            "CT01 outgoing displayed as negative payment")
    require(call(pg, "get_ledger", a)["months"][-1]["charges_vnd"] == "0",
            "CT01 outgoing became trip charge")


def check_ct_02(pg: Pg) -> None:
    a = new_book(pg, ("2026-01-01", -100_000_000))
    b = new_book(pg, ("2026-01-01", 50_000_000))
    before = ct_snapshot(pg, a, b)
    reject_call(pg, "record_offset", b, 0, a, 0, "ct02", "2026-03-01", 120_000_000,
                error="OFFSET_EXCEEDS_CREDIT")
    require(ct_snapshot(pg, a, b) == before, "CT02 overflow changed state")
    result = pg.sql(actor_sql(f"SELECT sokhach.record_offset({b},0,{a},0,'ct02-detail',"
                             "'2026-03-01',120000000)"), check=False)
    require('"available_credit_vnd": "100000000"' in result.stderr, "CT02 missing credit detail")
    reject_call(pg, "record_offset", a, 0, a, 0, "ct02-same", "2026-03-01", 1,
                error="OFFSET_SAME_BOOK")
    for amount in (None, 0, -1):
        reject_call(pg, "record_offset", b, 0, a, 0, "ct02-invalid", "2026-03-01", amount,
                    error="INVALID_VND")
    unbased = int(pg.value("INSERT INTO sokhach.customer(name) VALUES ('CT UNBASED') RETURNING id"))
    reject_call(pg, "record_offset", b, 0, unbased, 0, "ct02-unbased-source", "2026-03-01", 1,
                error="NO_BASELINE")
    reject_call(pg, "record_offset", unbased, 0, a, 0, "ct02-unbased-target", "2026-03-01", 1,
                error="NO_BASELINE")
    for av, bv in ((1, 0), (0, 1)):
        reject_call(pg, "record_offset", b, bv, a, av, "ct02-stale", "2026-03-01", 1,
                    error="STALE_LEDGER")


def check_ct_03(pg: Pg) -> None:
    a = new_book(pg, ("2026-01-01", -100))
    b = new_book(pg, ("2026-01-01", 50))
    before = ct_snapshot(pg, a, b)
    pg.sql("CREATE FUNCTION sokhach.ct_fault() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN "
           "RAISE EXCEPTION 'CT_FAULT_AFTER_TARGET'; END $$; "
           "CREATE TRIGGER ct_fault BEFORE INSERT ON sokhach.offset_pair "
           "FOR EACH ROW EXECUTE FUNCTION sokhach.ct_fault()")
    try:
        reject_call(pg, "record_offset", b, 0, a, 0, "ct03", "2026-03-01", 50,
                    error="CT_FAULT_AFTER_TARGET")
        require(ct_snapshot(pg, a, b) == before, "CT03 target/source/event/key escaped rollback")
    finally:
        pg.sql("DROP TRIGGER ct_fault ON sokhach.offset_pair; DROP FUNCTION sokhach.ct_fault()")
    pair = ct_record(pg, a, b, "ct03")
    for command, value in (("void_offset", "wrong"), ("edit_offset_date", "2026-02-01")):
        before = ct_snapshot(pg, a, b)
        pg.sql("CREATE FUNCTION sokhach.ct_fault() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN "
               "RAISE EXCEPTION 'CT_FAULT_AFTER_TARGET'; END $$; "
               "CREATE TRIGGER ct_fault BEFORE UPDATE ON sokhach.offset_pair "
               "FOR EACH ROW EXECUTE FUNCTION sokhach.ct_fault()")
        try:
            reject_call(pg, command, a, 1, 1, "ct03-" + command, pair["offset_pair_id"], value,
                        error="CT_FAULT_AFTER_TARGET")
            require(ct_snapshot(pg, a, b) == before, "CT03 change escaped rollback")
        finally:
            pg.sql("DROP TRIGGER ct_fault ON sokhach.offset_pair; DROP FUNCTION sokhach.ct_fault()")


def ct_contend(pg: Pg, cross: bool) -> str:
    source = new_book(pg, ("2026-01-01", -100))
    target = new_book(pg, ("2026-01-01", -100 if cross else 50))
    other = source if cross else new_book(pg, ("2026-01-01", 50))
    a, b = PsqlSession(pg, f"ct_a_{source}"), PsqlSession(pg, f"ct_b_{source}")
    try:
        a.send("BEGIN; SET LOCAL sokhach.actor='ct-a'; SELECT pg_backend_pid()")
        pid_a = int(a.line())
        first_sql = f"SELECT sokhach.record_offset({target},0,{source},0,'ct-first','2026-03-01',60)"
        if cross:
            # A owns only the lowest ID. Inverse B must wait here without owning
            # the higher ID, otherwise A's command below will expose a deadlock.
            a.send(f"SELECT id FROM sokhach.customer WHERE id={source} FOR UPDATE")
            require(int(a.line()) == source, "CT05 did not lock lowest ID")
        else:
            a.send(first_sql)
            first = json.loads(a.line())
        b.send("BEGIN; SET LOCAL sokhach.actor='ct-b'; SELECT pg_backend_pid()")
        pid_b = int(b.line())
        second_source = target if cross else source
        b.send(f"SELECT sokhach.record_offset({other},0,{second_source},0,'ct-second','2026-03-01',60)")
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            if pg.value(f"SELECT {pid_a}=ANY(pg_blocking_pids({pid_b}))") == "t":
                break
        else:
            raise HarnessError("CT contention did not observe pg_blocking_pids")
        if cross:
            a.send(first_sql)
            first = json.loads(a.line())
        a.send("COMMIT; SELECT 'committed'")
        require(a.line() == "committed", "CT first commit")
        b.proc.wait(timeout=10)
        stderr = b.proc.stderr.read() if b.proc.stderr else ""
        require("STALE_LEDGER" in stderr and "deadlock" not in stderr.lower(),
                f"CT blocked writer wrong result: {stderr[-700:]}")
        require(first["source_version"] == 1 and ct_total(pg, source) == -40,
                "CT same credit spent twice")
    finally:
        a.close()
        b.close()
    if cross:
        ct_record(pg, target, source, "ct-reverse", 60)
        require(ct_total(pg, source) == ct_total(pg, target) == -100, "CT reverse after refresh")
    else:
        reject_call(pg, "record_offset", other, 0, source, 1, "ct-after-refresh", "2026-03-01", 60,
                    error="OFFSET_EXCEEDS_CREDIT")
    return f"pg_blocking_pids: {pid_b} blocked by {pid_a}; stale rejected without deadlock"


def check_ct_04(pg: Pg) -> str:
    return ct_contend(pg, False)


def check_ct_05(pg: Pg) -> str:
    return ct_contend(pg, True)


def check_ct_06(pg: Pg) -> None:
    a = new_book(pg, ("2026-01-01", -100))
    b = new_book(pg, ("2026-01-01", 50))
    first = ct_record(pg, a, b, "ct06")
    before = ct_snapshot(pg, a, b)
    require(call(pg, "record_offset", b, 0, a, 0, "ct06", "2026-03-01", 50) == first,
            "CT06 retry stale versions")
    reject_call(pg, "record_offset", b, 0, a, 0, "ct06", "2026-03-01", 51,
                error="IDEMPOTENCY_CONFLICT")
    require(ct_snapshot(pg, a, b) == before, "CT06 retry wrote again")
    # Retries of a pair mutation can originate on the other side.
    edited = call(pg, "edit_offset_date", a, 1, 1, "ct06-edit", first["offset_pair_id"], "2026-02-01")
    require(call(pg, "edit_offset_date", b, 1, 1, "ct06-edit", first["offset_pair_id"],
                 "2026-02-01") == edited, "CT06 cross-side date retry")
    voided = call(pg, "void_offset", b, 2, 2, "ct06-void", first["offset_pair_id"], "wrong")
    require(call(pg, "void_offset", a, 2, 2, "ct06-void", first["offset_pair_id"], "wrong") == voided,
            "CT06 cross-side void retry")


def check_ct_07(pg: Pg) -> None:
    a = new_book(pg, ("2026-01-01", -100))
    b = new_book(pg, ("2026-01-01", 50), ("2026-02-01", 50))
    receipt = call(pg, "record_receipt", b, 0, "ct07-other", "2026-03-01", "THU TIỀN", 20)
    original = (ct_total(pg, a), ct_total(pg, b))
    other_lines = allocations(pg, b, receipt["pid"])
    for side in (a, b):
        pair = ct_record(pg, a, b, "ct07-record-" + str(side))
        reject_call(pg, "void_offset", side, version(pg, side), version(pg, b if side == a else a),
                    "ct07-empty", pair["offset_pair_id"], " ", error="VOID_REASON_REQUIRED")
        call(pg, "void_offset", side, version(pg, side), version(pg, b if side == a else a),
             "ct07-void-" + str(side), pair["offset_pair_id"], "wrong")
        require((ct_total(pg, a), ct_total(pg, b)) == original, "CT07 both books not restored")
        require(allocations(pg, b, receipt["pid"]) == other_lines, "CT07 changed other target receipt")
        assert_allocations(pg, b)
        reject_call(pg, "void_offset", side, version(pg, side), version(pg, b if side == a else a),
                    "ct07-again", pair["offset_pair_id"], "wrong", error="OFFSET_ALREADY_VOID")


def check_ct_08(pg: Pg) -> None:
    a = new_book(pg, ("2026-01-01", -100), ("2026-02-01", 50))
    b = new_book(pg, ("2026-01-01", 40), ("2026-02-01", 40))
    call(pg, "record_receipt", a, 0, "ct08-source", "2026-03-02", "THU TIỀN", 60)
    call(pg, "record_receipt", b, 0, "ct08-target", "2026-03-02", "THU TIỀN", 30)
    pair = ct_record(pg, a, b, "ct08", 40, "2026-03-03")
    before = ct_total(pg, a) + ct_total(pg, b)
    changed = call(pg, "edit_offset_date", a, 2, 2, "ct08-edit", pair["offset_pair_id"], "2026-01-03")
    require(changed["source_reallocated"] and changed["target_receipt"]["reallocated"],
            "CT08 lacks both reallocation snapshots")
    pg.true(f"EXISTS (SELECT 1 FROM sokhach.offset_pair p JOIN sokhach.receipt r "
            f"ON r.id=p.target_receipt_id WHERE p.id={pair['offset_pair_id']} "
            "AND p.date='2026-01-03' AND r.date=p.date)", "CT08 dates differ")
    require(ct_total(pg, a) + ct_total(pg, b) == before, "CT08 changed total")
    for book in (a, b):
        ledger = call(pg, "get_ledger", book)
        require(any(e["kind"] == "receipt_edit" and e["counterparty_customer_id"] is not None
                    for e in ledger["events"]), "CT08 missing paired edit history")
        assert_allocations(pg, book)


def check_ct_09(pg: Pg) -> None:
    a = new_book(pg, ("2026-01-01", -100))
    b = new_book(pg, ("2026-01-01", 50))
    pair = ct_record(pg, a, b, "ct09")
    before = ct_snapshot(pg, a, b)
    for method in ("KHÁC", "CẤN TRỪ"):
        reject_call(pg, "edit_receipt_meta", b, 1, "ct09-method", pair["target_pid"],
                    "2026-02-01", method, error="OFFSET_PAIR_REQUIRED")
    reject_call(pg, "void_receipt", b, 1, "ct09-single-void", pair["target_pid"], "wrong",
                error="OFFSET_PAIR_REQUIRED")
    require(ct_snapshot(pg, a, b) == before, "CT09 single side command modified pair")


def check_ct_10(pg: Pg) -> None:
    a = new_book(pg, ("2026-01-01", -100))
    b = new_book(pg, ("2026-01-01", 50))
    receipt = call(pg, "record_receipt", b, 0, "ct10", "2026-03-01", "CẤN TRỪ", 50)
    require(ct_total(pg, a) == -100 and ct_total(pg, b) == 0 and version(pg, a) == 0,
            "CT10 outside receipt changed source")
    require(call(pg, "get_ledger", b)["receipts"][0]["offset_pair_id"] is None,
            "CT10 outside receipt linked")
    call(pg, "void_receipt", b, 1, "ct10-void", receipt["pid"], "wrong")
    require(ct_total(pg, b) == 50, "CT10 outside void no longer works")


def check_ct_11(pg: Pg) -> None:
    target = new_book(pg, ("2026-01-01", -10))
    yes_a = new_book(pg, ("2026-01-01", -20))
    yes_z = new_book(pg, ("2026-01-01", -30))
    debt = new_book(pg, ("2026-01-01", 20))
    zero = new_book(pg, ("2026-01-01", 0))
    archived = new_book(pg, ("2026-01-01", -20))
    draft = int(pg.value("INSERT INTO sokhach.customer(name) VALUES ('CT11 DRAFT') RETURNING id"))
    pg.sql(f"UPDATE sokhach.customer SET name='CT11 A' WHERE id={yes_a}; "
           f"UPDATE sokhach.customer SET name='CT11 Z' WHERE id={yes_z}; "
           f"UPDATE sokhach.customer SET archived=true WHERE id={archived}")
    rows = call(pg, "list_offset_sources", target)
    ids = [row["customer_id"] for row in rows]
    require(yes_a in ids and yes_z in ids and ids.index(yes_a) < ids.index(yes_z), "CT11 A-Z order")
    require(not {target, debt, zero, archived, draft} & set(ids), "CT11 invalid source listed")
    row = next(r for r in rows if r["customer_id"] == yes_a)
    require(row["version"] == 0 and row["available_credit_vnd"] == "20"
            and row["outstanding_vnd"] == "-20", "CT11 source contract")
    reject_call(pg, "record_offset", target, 0, archived, 0, "ct11-archive", "2026-03-01", 1,
                error="OFFSET_SOURCE_ARCHIVED")


def check_ct_12(pg: Pg) -> None:
    a = new_book(pg, ("2026-01-01", -100))
    b = new_book(pg, ("2026-01-01", 50))
    # Clock independent of sokhach helper; session timezone deliberately differs.
    today = pg.value("SET TIME ZONE 'Pacific/Honolulu'; "
                     "SELECT (clock_timestamp() AT TIME ZONE 'Asia/Ho_Chi_Minh')::date")
    tomorrow = pg.value(f"SELECT ({lit(today)}::date+1)::text")
    before = ct_snapshot(pg, a, b)
    reject_call(pg, "record_offset", b, 0, a, 0, "ct12-future", tomorrow, 1, error="FUTURE_DATE")
    require(ct_snapshot(pg, a, b) == before, "CT12 future record changed state")
    pair = ct_record(pg, a, b, "ct12-today", 50, today)
    before = ct_snapshot(pg, a, b)
    for side in (a, b):
        reject_call(pg, "edit_offset_date", side, 1, 1, "ct12-edit", pair["offset_pair_id"], tomorrow,
                    error="FUTURE_DATE")
    require(ct_snapshot(pg, a, b) == before, "CT12 future edit changed state")


def check_ct_13(pg: Pg) -> None:
    a = new_book(pg, ("2026-01-01", -100))
    b = new_book(pg, ("2026-01-01", 50))
    old = call(pg, "record_receipt", b, 0, "ct13-old", "2026-02-01", "CẤN TRỪ", 10)
    ct_record(pg, a, b, "ct13-new", 10, "2026-02-01")
    ledger = call(pg, "get_ledger", b)
    row = next(r for r in ledger["receipts"] if r["pid"] == old["pid"])
    require(row["offset_pair_id"] is None and row["counterparty_customer_id"] is None,
            "CT13 guessed link from identical date/method/amount")
    require(pg.value(f"SELECT count(*) FROM sokhach.offset_pair WHERE target_customer_id={b}") == "1",
            "CT13 backfilled old receipt")


def check_ct_14(pg: Pg) -> None:
    a = new_book(pg, ("2026-01-01", -100))
    b = new_book(pg, ("2026-01-01", 50))
    for n in range(12):
        call(pg, "record_receipt", a, n, f"ct14-a{n}", "2026-02-01", "THU TIỀN", 1)
    call(pg, "record_receipt", b, 0, "ct14-b", "2026-02-01", "THU TIỀN", 1)
    pair = ct_record(pg, a, b, "ct14", 10)
    require(pair["source_pid"] == "PH-013" and pair["target_pid"] == "PH-002", "CT14 per-book code")
    receipt = call(pg, "record_receipt", a, 13, "ct14-next", "2026-04-01", "THU TIỀN", 1)
    require(receipt["pid"] == "PH-014", "CT14 ordinary receipt reused outgoing code")
    pg.true("NOT EXISTS (SELECT customer_id,pid FROM (SELECT customer_id,pid FROM sokhach.receipt "
            "UNION ALL SELECT source_customer_id,source_pid FROM sokhach.offset_pair) codes "
            f"WHERE customer_id IN ({a},{b}) GROUP BY customer_id,pid HAVING count(*)>1)", "CT14 duplicate codes")


def check_ct_15(pg: Pg) -> None:
    a = new_book(pg, ("2026-01-01", -100_000_000))
    b = new_book(pg, ("2026-01-01", 50_000_000))
    pair = ct_record(pg, a, b, "ct15", 70_000_000)
    require((ct_total(pg, a), ct_total(pg, b)) == (-30_000_000, -20_000_000), "CT15 balances")
    require(allocations(pg, b, pair["target_pid"]) == [("2026-01-01", "debt", "50000000"),
                                                    ("2026-01-01", "advance", "20000000")],
            "CT15 missing advance")
    require(pair["target_receipt"]["overpayment_vnd"] == "20000000", "CT15 overpayment contract")


def check_dedup(pg: Pg) -> None:
    c = new_book(pg, ("2026-01-01", 0))
    current = pg.value("SELECT date_trunc('month',clock_timestamp() AT TIME ZONE 'Asia/Ho_Chi_Minh')::date")
    cut = pg.value(f"SELECT cutover_id FROM sokhach.cutover_customer WHERE customer_id={c}")
    pg.sql(f"INSERT INTO sokhach.baseline_trip_ref VALUES ({cut},'BK1','BASE','2026-01-10')")

    def paste(key, container, day="10/01/2026", booking=None, month=current):
        row = json.loads(trip_json(container=container))[0]
        row.update(date=day, booking=booking)
        return call(pg, "paste_trips", c, version(pg, c), key, month, json.dumps([row]))

    code = paste("code", " b a s e\u00a0", booking=" b\u202fk 1")
    require(code["pending_review"][0]["reason"] == "BASELINE_CODE_MATCH", "Unicode code match")
    # Test outside days before nearby pending rows are saved into this same book.
    for day, pending in (("06/01/2026", False), ("14/01/2026", False),
                         ("07/01/2026", True), ("13/01/2026", True)):
        result = paste(day, "BASE", day, "BK-" + day)
        require(bool(result["pending_review"]) == pending, "date boundary")
    first = paste("first", "NEW")
    again = paste("again", " n e w", booking="/")
    require(not first["pending_review"] and again["pending_review"][0]["reason"] == "WEB_DUPLICATE", "ALT duplicate")
    row = json.loads(trip_json(container="BATCH"))[0]
    result = call(pg, "paste_trips", c, version(pg, c), "batch", current, json.dumps([row, row]))
    require(result["pending_review"][0]["reason"] == "BATCH_DUPLICATE", "batch duplicate")
    pending_id = code["trip_ids"][0]
    money_rows = pg.value(f"SELECT (SELECT count(*) FROM sokhach.trip_price_rev WHERE customer_id={c})||':'||"
                                     f"(SELECT count(*) FROM sokhach.adjustment WHERE customer_id={c})")
    before = pg.value(f"SELECT count(*) FROM sokhach.event WHERE customer_id={c}")
    reject_call(pg, "edit_trip_price", c, version(pg, c), "edit-pending", pending_id, 20, None,
                error="TRIP_PENDING_REVIEW")
    reject_call(pg, "adjust_trip", c, version(pg, c), "adjust-pending", pending_id, 20, "fake",
                error="TRIP_PENDING_REVIEW")
    require(pg.value(f"SELECT count(*) FROM sokhach.event WHERE customer_id={c}") == before, "pending mutation event")
    require(pg.value(f"SELECT (SELECT count(*) FROM sokhach.trip_price_rev WHERE customer_id={c})||':'||"
                     f"(SELECT count(*) FROM sokhach.adjustment WHERE customer_id={c})") == money_rows,
            "pending edit wrote price or adjustment")
    require(call(pg, "get_ledger", c)["total_outstanding_vnd"] == "400", "pending leaked into money")
    # Only pending trip in a later month must not move overpayment there.
    future_month = "2099-01-01"
    call(pg, "set_month_lock", c, version(pg, c), "open-future", future_month, "false")
    paste("future-pending", "BASE", day="01/01/2099", booking="BK1", month=future_month)
    call(pg, "record_receipt", c, version(pg, c), "advance", "2026-01-01", "THU TIỀN", 500)
    require(allocations(pg, c, "PH-001")[-1] == ("2026-01-01", "advance", "100"), "pending advance month")
    reject_call(pg, "adjust_month", c, version(pg, c), "pending-month", future_month, 1, "fake",
                error="MONTH_NOT_FOUND")
    assert_allocations(pg, c)
    probe = new_book(pg, ("2026-01-01", 0))
    call(pg, "paste_trips", probe, 0, "probe-first", current, trip_json(month=current))
    second = call(pg, "paste_trips", probe, 1, "probe-again", current, trip_json(month=current))
    require(second["pending_review"][0]["reason"] == "WEB_DUPLICATE"
            and call(pg, "get_ledger", probe)["total_outstanding_vnd"] == "100", "C1 reproduced: must be 100, not 200")
    fee = json.loads(trip_json(None, container=""))[0]
    fee.update(date=None, otherFeeVnd="7")
    for n in range(2):
        require(not call(pg, "paste_trips", probe, version(pg, probe), f"fee-{n}", current,
                         json.dumps([fee]))["pending_review"], "fee-only deduped")
    require(call(pg, "get_ledger", probe)["total_outstanding_vnd"] == "114", "fee-only no longer counts")
    # NEWTRIP-01: web and within-batch matches include the inclusive +/-3 day window.
    for delta, pending in ((-4, False), (-3, True), (3, True), (4, False)):
        for scope in ("web", "batch"):
            target = new_book(pg, ("2026-01-01", 0))
            first_row = json.loads(trip_json(container="WINDOW"))[0]
            first_row.update(date="10/01/2026", booking="BK-FIRST")
            next_row = first_row | {"date": f"{10 + delta:02d}/01/2026", "booking": "BK-NEXT"}
            safe = first_row | {"container": "SAFE"}
            if scope == "web":
                call(pg, "paste_trips", target, 0, "window-first", current, json.dumps([first_row]))
            rows = [next_row, safe] if scope == "web" else [first_row, next_row, safe]
            result = call(pg, "paste_trips", target, version(pg, target), "window-mixed", current, json.dumps(rows))
            require(bool(result["pending_review"]) == pending, f"{scope} window {delta}")
            ledger = call(pg, "get_ledger", target)
            require(ledger["total_outstanding_vnd"] == ("200" if pending else "300"), "mixed batch balance")
            held = [t for t in ledger["trips"] if t["status"] == "pending_review"]
            require(len(held) == int(pending) and all(t["amount_vnd"] is None for t in held),
                    "pending row contract")
            if pending:
                require(result["pending_review"][0]["trip_id"] == result["trip_ids"][0 if scope == "web" else 1],
                        "wrong row quarantined")
    empty = new_book(pg)
    # Use separate empty cutover rather than bypass immutable reference rows.
    pg.sql("ALTER TABLE sokhach.baseline_trip_ref DISABLE TRIGGER baseline_trip_ref_immutable")
    empty_cut = pg.value(f"SELECT cutover_id FROM sokhach.cutover_customer WHERE customer_id={empty}")
    pg.sql(f"DELETE FROM sokhach.baseline_trip_ref WHERE cutover_id={empty_cut}")
    pg.sql("ALTER TABLE sokhach.baseline_trip_ref ENABLE TRIGGER baseline_trip_ref_immutable")
    reject_call(pg, "paste_trips", empty, 0, "missing-ref", current, trip_json(), error="BASELINE_REF_MISSING")
    require(version(pg, empty) == 0, "missing reference changed version")

NHAP_MIGRATION = ROOT / "cong-no-web-handoff/tools/migrations/2026-10-22-v7-nhap-sheet.sql"

REVIEW_MIGRATION = ROOT / "cong-no-web-handoff/tools/migrations/2026-10-22-v7-trip-review.sql"
MH_MIGRATION = ROOT / "cong-no-web-handoff/tools/migrations/2026-10-23-v7-mat-hang.sql"
SHEET_MIGRATION = ROOT / "cong-no-web-handoff/tools/migrations/2026-10-24-v7-sheet-cross-customer.sql"


def check_sheet_cross_customer(pg: Pg) -> None:
    first = new_book(pg, ("2026-01-01", 100))
    second = new_book(pg, ("2026-01-01", 200))
    untagged = new_book(pg, ("2026-01-01", 300))
    today = pg.value("SELECT (clock_timestamp() AT TIME ZONE 'Asia/Ho_Chi_Minh')::date")
    month = today[:7] + "-01"
    row = json.loads(trip_json(None, container="FAKE-CROSS-CUSTOMER"))[0]
    row.update(date=today[8:10] + "/" + today[5:7] + "/" + today[:4],
               src="sheet:" + "a" * 64 + ":2", unitPriceVnd=None, otherFeeVnd=None)
    before = call(pg, "get_ledger", first)["total_outstanding_vnd"]
    trip_id = call(pg, "paste_trips", first, version(pg, first), "sheet-first", month,
                   json.dumps([row]))["trip_ids"][0]
    ledger = call(pg, "get_ledger", first)
    saved = next(trip for trip in ledger["trips"] if trip["id"] == trip_id)
    require(ledger["total_outstanding_vnd"] == before and saved["unit_price_vnd"] is None
            and saved["amount_vnd"] is None, "NULL price changed balance")
    refs = json.loads(pg.value(actor_sql("SELECT sokhach.list_sheet_trip_refs()")))["items"]
    require(any(ref["customer_id"] == first and ref["container"] == "FAKE-CROSS-CUSTOMER"
                for ref in refs), "cross-customer reference missing")
    # Non-Sheet fixture rows may share a container; guard owns only Sheet imports.
    call(pg, "paste_trips", untagged, version(pg, untagged), "fixture-untagged", month,
         json.dumps([row | {"src": None}]))
    before_second = call(pg, "get_ledger", second)["total_outstanding_vnd"]
    reject_call(pg, "paste_trips", second, version(pg, second), "sheet-second", month,
                json.dumps([row | {"src": "sheet:" + "a" * 64 + ":3"}]), error="SHEET_CROSS_CUSTOMER_MATCH")
    require(call(pg, "get_ledger", second)["total_outstanding_vnd"] == before_second,
            "rejected cross-customer row changed balance")

DASHBOARD_MIGRATION = ROOT / "cong-no-web-handoff/tools/migrations/2026-10-24-v7-dashboard.sql"
LOCKED_TRIP_MIGRATION = ROOT / "cong-no-web-handoff/tools/migrations/2026-10-24-v7-locked-trip-edit.sql"
MATRIX_MIGRATION = ROOT / "cong-no-web-handoff/tools/migrations/2026-10-25-v7-receivables-matrix.sql"
DETAIL_MIGRATION = ROOT / "cong-no-web-handoff/tools/migrations/2026-10-26-v7-receivables-detail.sql"
SYNC_MIGRATION = ROOT / "cong-no-web-handoff/tools/migrations/2026-10-27-v7-shipper-write-sync.sql"
LEGACY_RECEIPT_MIGRATION = ROOT / "cong-no-web-handoff/tools/migrations/2026-10-28-v7-legacy-receipt-delete.sql"
SHEET_CONFLICT_MIGRATION = ROOT / "cong-no-web-handoff/tools/migrations/2026-10-25-v7-sheet-conflict.sql"
SHEET_CONFLICT_DATE_MIGRATION = ROOT / "cong-no-web-handoff/tools/migrations/2026-10-27-v7-sheet-conflict-date-booking.sql"


def check_sheet_conflict_resolution(pg: Pg) -> None:
    c = new_book(pg, ("2026-09-01", 0))
    fixture_open_month(pg, c, "2026-09-01")
    row = json.loads(trip_json(container="FAKE-SHEET-DATE"))[0] | {"date": "15/09/2026", "booking": "BK-OLD"}
    trip_id = call(pg, "paste_trips", c, version(pg, c), "sheet-date-paste", "2026-09-01",
                   json.dumps([row]))["trip_ids"][0]
    before = call(pg, "get_ledger", c)
    sha = "a" * 64

    def resolve(key, field, target, sheet, decision, kind="trip", target_id=trip_id):
        return (c, version(pg, c), key, sha, 9, kind, target_id, field, target, sheet, decision)

    # Date and booking differences close as "keep web" only, without touching the trip or money.
    call(pg, "resolve_sheet_conflict", *resolve("keep-date", "event_date", "2026-09-15", "2026-09-20", "keep_web"))
    call(pg, "resolve_sheet_conflict", *resolve("keep-booking", "booking", "BK-OLD", "", "keep_web"))
    after = call(pg, "get_ledger", c)
    trip = next(t for t in after["trips"] if t["id"] == trip_id)
    require(trip["event_date"] == "2026-09-15" and trip["booking"] == "BK-OLD", "keep_web changed the trip")
    require(after["total_outstanding_vnd"] == before["total_outstanding_vnd"], "keep_web changed balance")
    events = [e for e in after["events"] if e["kind"] == "sheet_conflict_resolved"]
    require(sorted(e["after"]["field"] for e in events) == ["booking", "event_date"]
            and all(e["after"]["decision"] == "keep_web" for e in events), "resolution events missing")
    for key, args in [("date-sheet", resolve("x", "event_date", "2026-09-15", "2026-09-20", "use_sheet")),
                      ("booking-sheet", resolve("x", "booking", "BK-OLD", "BK-NEW", "use_sheet")),
                      ("booking-legacy", resolve("x", "booking", None, "BK-NEW", "keep_web", "legacy", 1))]:
        reject_call(pg, "resolve_sheet_conflict", *args[:2], key, *args[3:], error="INVALID_SHEET_RESOLUTION")
    # Taking the Sheet value now honours the month lock; keeping web stays allowed.
    pg.sql(f"UPDATE sokhach.month_state SET locked=true WHERE customer_id={c} AND month='2026-09-01'")
    reject_call(pg, "resolve_sheet_conflict", *resolve("locked-carrier", "carrier", "FAKE", "FAKE NEW", "use_sheet"),
                error="MONTH_LOCKED")
    call(pg, "resolve_sheet_conflict", *resolve("locked-keep", "carrier", "FAKE", "FAKE NEW", "keep_web"))
    require(call(pg, "get_ledger", c)["total_outstanding_vnd"] == before["total_outstanding_vnd"],
            "locked resolution changed balance")


def check_trip_review(pg: Pg) -> None:
    c = new_book(pg, ("2026-01-01", 0))
    current = pg.value("SELECT date_trunc('month',clock_timestamp() AT TIME ZONE 'Asia/Ho_Chi_Minh')::date")
    cut = pg.value(f"SELECT cutover_id FROM sokhach.cutover_customer WHERE customer_id={c}")
    pg.sql(f"INSERT INTO sokhach.baseline_trip_ref VALUES ({cut},'BK1','BASE','2026-01-10')")

    def paste(key, container, booking):
        row = json.loads(trip_json(container=container))[0] | {"date": "10/01/2026", "booking": booking}
        return call(pg, "paste_trips", c, version(pg, c), key, current, json.dumps([row]))

    def trip(trip_id):
        return next(t for t in call(pg, "get_ledger", c)["trips"] if t["id"] == trip_id)

    held = paste("held", "BASE", "BK1")["trip_ids"][0]
    other = paste("other", "BASE", "BK2")["trip_ids"][0]
    require(trip(held)["review_reason"] == "BASELINE_CODE_MATCH"
            and trip(other)["review_reason"] == "BASELINE_DATE_WINDOW", "GET lost pending reason")
    call(pg, "record_receipt", c, version(pg, c), "pay", "2026-01-02", "THU TIỀN", 30)
    require(allocations(pg, c, "PH-001") == [("2026-01-01", "advance", "30")], "receipt not advance before review")
    before = version(pg, c)
    for args, error in (((held, "confirm", " "), "REVIEW_REASON_REQUIRED"),
                        ((held, "approve", "fake"), "INVALID_REVIEW"),
                        ((999999, "confirm", "fake"), "TRIP_NOT_FOUND")):
        reject_call(pg, "review_trip", c, before, "bad-" + error, *args, error=error)
    require(version(pg, c) == before, "rejected review changed version")
    call(pg, "set_month_lock", c, version(pg, c), "review-open-jan", "2026-01-01", "false")
    before = version(pg, c)
    confirmed = call(pg, "review_trip", c, before, "confirm", held, "confirm", " đã đối chiếu sổ gốc ", actor="fake-a")
    require(confirmed["status"] == "confirmed" and confirmed["reallocated"], "confirm did not reallocate")
    require(call(pg, "review_trip", c, before, "confirm", held, "confirm", " đã đối chiếu sổ gốc ") == confirmed,
            "review retry wrote twice")
    reject_call(pg, "review_trip", c, before, "confirm", held, "reject", "khác", error="IDEMPOTENCY_CONFLICT")
    ledger = call(pg, "get_ledger", c)
    require(ledger["total_outstanding_vnd"] == "70" and trip(held)["amount_vnd"] == "100"
            and trip(held)["editable"], "confirmed trip not in balance")
    require(allocations(pg, c, "PH-001") == [("2026-01-01", "debt", "30")], "receipt not moved onto confirmed trip")
    event = next(e for e in ledger["events"] if e["kind"] == "trip_review")
    require(event["actor"] == "fake-a" and event["before"]["status"] == "pending_review"
            and event["after"] == {"trip": held, "container": "BASE", "status": "confirmed",
                                   "review_reason": "đã đối chiếu sổ gốc"}, "review audit wrong")
    reject_call(pg, "review_trip", c, version(pg, c), "again", held, "reject", "fake", error="TRIP_NOT_PENDING")
    call(pg, "edit_trip_price", c, version(pg, c), "price-after", held, 120, None)
    # Locked month blocks conclusions since the 24/10 update (decisions.md);
    # reject leaves money untouched.
    call(pg, "set_month_lock", c, version(pg, c), "lock", "2026-01-01", "true")
    total = call(pg, "get_ledger", c)["total_outstanding_vnd"]
    reject_call(pg, "review_trip", c, version(pg, c), "locked-reject", other, "reject", "trùng dòng sổ gốc", error="MONTH_LOCKED")
    call(pg, "set_month_lock", c, version(pg, c), "unlock-review", "2026-01-01", "false")
    rejected = call(pg, "review_trip", c, version(pg, c), "reject", other, "reject", "trùng dòng sổ gốc")
    require(rejected == rejected | {"status": "rejected", "reallocated": []}, "reject result wrong")
    require(call(pg, "get_ledger", c)["total_outstanding_vnd"] == total and trip(other)["status"] == "rejected"
            and trip(other)["amount_vnd"] is None, "rejected trip leaked into money")
    call(pg, "set_month_lock", c, version(pg, c), "unlock", "2026-01-01", "false")
    reject_call(pg, "edit_trip_price", c, version(pg, c), "price-rejected", other, 5, None, error="TRIP_PENDING_REVIEW")
    require(paste("again", "BASE", "BK2")["pending_review"][0]["reason"] == "BASELINE_DATE_WINDOW",
            "rejected trip no longer blocks duplicate")
    assert_allocations(pg, c)
    pg.rejects(f"UPDATE sokhach.trip SET note='x' WHERE id={held}", message="immutable row")
    pg.rejects(f"DELETE FROM sokhach.trip WHERE id={other}", message="immutable row")
    pending = paste("direct", "BASE", "BK3")["trip_ids"][0]
    late = paste("late", "BASE", "BK4")["trip_ids"][0]
    call(pg, "set_month_lock", c, version(pg, c), "lock-late", "2026-01-01", "true")
    total = int(call(pg, "get_ledger", c)["total_outstanding_vnd"])
    reject_call(pg, "review_trip", c, version(pg, c), "locked-confirm", late, "confirm", "đối chiếu xong", error="MONTH_LOCKED")
    call(pg, "set_month_lock", c, version(pg, c), "unlock-late-review", "2026-01-01", "false")
    call(pg, "review_trip", c, version(pg, c), "confirmed-late", late, "confirm", "đối chiếu xong")
    require(int(call(pg, "get_ledger", c)["total_outstanding_vnd"]) == total + 100, "locked-month confirm not counted")
    assert_allocations(pg, c)
    call(pg, "set_month_lock", c, version(pg, c), "unlock-late", current, "false")
    pg.rejects(f"UPDATE sokhach.trip SET status='confirmed' WHERE id={pending}", message="immutable row")
    pg.rejects(f"UPDATE sokhach.trip SET status='confirmed',reviewed_by_event=1,note='x' WHERE id={pending}",
               message="immutable row")


def check_nhap_sheet(pg: Pg) -> None:
    c = new_book(pg, ("2026-09-01", 60000000), ("2026-10-01", 93000000))
    for month in ("2026-08-01", "2026-09-01", "2026-10-01"):
        fixture_open_month(pg, c, month)
    opening = pg.value(f"SELECT jsonb_agg(to_jsonb(o) ORDER BY id) FROM sokhach.opening_balance o WHERE customer_id={c}")
    cut = pg.value(f"SELECT cutover_id FROM sokhach.cutover_customer WHERE customer_id={c}")
    event = pg.value(f"SELECT id FROM sokhach.event WHERE customer_id={c} AND kind='import'")
    # Harness-only source rows; bypass import freeze, never monetary immutability.
    pg.sql("ALTER TABLE sokhach.legacy_row DISABLE TRIGGER legacy_row_insert_guard")
    ids = []
    try:
        for n, (month, amount, unit, kind) in enumerate([
            ("2026-09-01", 60000000, "60000000", "trip"),
            ("2026-10-01", 0, None, "trip"),
            ("2026-10-01", 93000000, "93000000", "trip"),
            ("2026-10-01", 4000000, None, "receipt"),
        ], 100):
            display = json.dumps({"container": f"FAKE-{n}", "carrier": "FAKE", "from": "A", "to": "B",
                                  "date": month, "unit_price": unit, "fee_vnd": None})
            ids.append(int(pg.value("INSERT INTO sokhach.legacy_row(customer_id,cutover_id,debt_month,kind,display,"
                "source_total_vnd,source_tab,source_row,created_by_event) "
                f"VALUES({c},{cut},{lit(month)},{lit(kind)},{lit(display)}, {amount},'FAKE',{n},{event}) RETURNING id")))
    finally:
        pg.sql("ALTER TABLE sokhach.legacy_row ENABLE TRIGGER legacy_row_insert_guard")
    legacy = pg.value(f"SELECT jsonb_agg(to_jsonb(l) ORDER BY id) FROM sokhach.legacy_row l WHERE customer_id={c}")
    pg.sql(f"UPDATE sokhach.month_state SET locked=true WHERE customer_id={c} AND month='2026-09-01'")
    reject_call(pg, "edit_legacy_trip", c, 0, "locked-legacy-edit", ids[0], "carrier", "FAKE NEW", error="MONTH_LOCKED")
    reject_call(pg, "delete_legacy_trip", c, 0, "locked-legacy-delete", ids[0], error="MONTH_LOCKED")
    require(version(pg, c) == 0, "locked legacy mutation changed version")
    fixture_open_month(pg, c, "2026-09-01")

    def write(name, *args, key=None, actor="fake-editor"):
        before = version(pg, c)
        key = key or f"nhap-{before}-{name}"
        result = call(pg, name, c, before, key, *args, actor=actor)
        require(version(pg, c) == before + 1, f"{name}: version")
        require(call(pg, name, c, before, key, *args, actor=actor) == result, f"{name}: retry")
        reject_call(pg, name, c, before, key+"-stale", *args, error="STALE_LEDGER")
        if name in ("edit_trip_info", "delete_trip", "edit_legacy_trip", "delete_legacy_trip"):
            reject_call(pg, name, c, before, key, args[0]+100000, *args[1:], error="IDEMPOTENCY_CONFLICT")
        return result

    def total():
        return int(call(pg, "get_ledger", c)["total_outstanding_vnd"])

    def deltas(row):
        return int(pg.value(f"SELECT coalesce(sum(amount_vnd),0) FROM sokhach.adjustment WHERE legacy_row_id={row}"))

    start = total()
    write("edit_legacy_trip", ids[0], "unit_price_vnd", "65000000", key="legacy-60-to-65")
    require(total() == start+5000000 and deltas(ids[0]) == 5000000, "60M to 65M")
    audit = json.loads(pg.value(f"SELECT jsonb_build_array(\"before\"->'legacy'->>'counted_vnd',\"after\"->'legacy'->>'counted_vnd') FROM sokhach.event WHERE customer_id={c} AND idempotency_key='legacy-60-to-65' AND kind='legacy_edit'"))
    require(audit == ["60000000", "65000000"], "legacy source/current amount audit")
    write("delete_legacy_trip", ids[0])
    require(total() == start-60000000 and deltas(ids[0]) == -60000000, "delete revised 65M")
    write("edit_legacy_trip", ids[1], "unit_price_vnd", "70000000")
    require(total() == start+10000000 and deltas(ids[1]) == 70000000, "missing price to 70M")
    write("edit_legacy_trip", ids[2], "event_date", "2026-09-28")
    require(total() == start+10000000 and deltas(ids[2]) == 0, "93M move preserves total")
    got = json.loads(pg.value(f"SELECT jsonb_object_agg(debt_month,amount_vnd::text) FROM sokhach.adjustment WHERE legacy_row_id={ids[2]}"))
    require(got == {"2026-10-01": "-93000000", "2026-09-01": "93000000"}, "93M wrong month deltas")
    write("edit_legacy_trip", ids[1], "unit_price_vnd", "69000000")
    require(deltas(ids[1]) == 69000000, "legacy negative price delta")
    for field, value in [("container", " fake changed "), ("carrier", "FAKE TWO"),
                         ("origin", "C"), ("destination", "D")]:
        count = pg.value(f"SELECT count(*) FROM sokhach.adjustment WHERE legacy_row_id={ids[1]}")
        write("edit_legacy_trip", ids[1], field, value)
        require(pg.value(f"SELECT count(*) FROM sokhach.adjustment WHERE legacy_row_id={ids[1]}") == count, "text edit wrote money")
    ledger = call(pg, "get_ledger", c)
    require(not any(row["id"] == ids[0] for row in ledger["legacy_rows"]), "deleted legacy visible")
    moved = next(row for row in ledger["legacy_rows"] if row["id"] == ids[2])
    require(moved["month"] == "2026-09-01" and moved["current"]["counted_vnd"] == "93000000"
            and moved["display"]["date"] == "2026-10-01" and moved["editable"], "legacy current/source separation")
    require(any(a["legacy_row_id"] == ids[2] for a in ledger["adjustments"]), "GET lost legacy target")
    for name, args, error in [
        ("edit_legacy_trip", (ids[3], "carrier", "X"), "LEGACY_NOT_TRIP"),
        ("delete_legacy_trip", (ids[0],), "LEGACY_NOT_FOUND"),
        ("edit_legacy_trip", (ids[1], "unknown", "X"), "INVALID_FIELD"),
        ("edit_legacy_trip", (ids[1], "unit_price_vnd", "-0"), "INVALID_VND"),
        ("edit_legacy_trip", (ids[1], "unit_price_vnd", "9223372036854775808"), "INVALID_VND"),
        ("edit_legacy_trip", (ids[1], "event_date", "2026-02-30"), "INVALID_DATE"),
    ]:
        reject_call(pg, name, c, version(pg, c), "bad-"+error, *args, error=error)
    # XOA-THU-GOC-01: xóa khoản thu sổ gốc cộng lại đúng số đã trừ, ở tháng của dòng.
    before_receipt = total()
    write("delete_legacy_trip", ids[3], key="legacy-receipt-delete")
    require(total() == before_receipt+4000000 and deltas(ids[3]) == 4000000, "receipt delete adds debt back")
    got = json.loads(pg.value(f"SELECT jsonb_object_agg(debt_month,amount_vnd::text) FROM sokhach.adjustment WHERE legacy_row_id={ids[3]}"))
    require(got == {"2026-10-01": "4000000"}, "receipt delete month")
    audit = json.loads(pg.value(f"SELECT \"before\"->'legacy' FROM sokhach.event WHERE customer_id={c} AND idempotency_key='legacy-receipt-delete'"))
    require(audit["kind"] == "receipt" and audit["counted_vnd"] == "4000000", "receipt delete audit")
    require(not any(row["id"] == ids[3] for row in call(pg, "get_ledger", c)["legacy_rows"]), "deleted receipt visible")
    reject_call(pg, "delete_legacy_trip", c, version(pg, c), "receipt-again", ids[3], error="LEGACY_NOT_FOUND")
    assert_allocations(pg, c)
    other = new_book(pg, ("2026-09-01", 0))
    reject_call(pg, "edit_legacy_trip", other, 0, "wrong-cut", ids[1], "carrier", "X", error="LEGACY_NOT_FOUND")
    write("edit_legacy_trip", ids[1], "unit_price_vnd", "")
    require(deltas(ids[1]) == 0, "blank price did not restore zero contribution")
    write("edit_legacy_trip", ids[1], "other_fee_vnd", "7")
    require(deltas(ids[1]) == 0, "fee without unit price entered balance")
    write("edit_legacy_trip", ids[1], "unit_price_vnd", "1")
    require(deltas(ids[1]) == 8, "legacy unit plus fee")
    write("edit_legacy_trip", ids[1], "other_fee_vnd", "")
    require(deltas(ids[1]) == 1, "NULL fee with known price is not zero in calculation")
    write("edit_legacy_trip", ids[1], "unit_price_vnd", "")
    current = pg.value("SELECT date_trunc('month',clock_timestamp() AT TIME ZONE 'Asia/Ho_Chi_Minh')::date")
    row = json.loads(trip_json("100", container="FAKE-WEB", month=current))[0]
    mixed = [row, row | {"container": "FAKE-LOCKED", "date": "10/09/2026"}]
    pasted = write("paste_trips", current, json.dumps(mixed))
    t, locked_trip = pasted["trip_ids"]
    require(pg.value(f"SELECT debt_month FROM sokhach.trip WHERE id={locked_trip}") == "2026-09-01", "paste into locked month")
    require(pg.value(f"SELECT count(*) FROM sokhach.event WHERE customer_id={c} AND kind='paste'") == "1", "mixed batch multiple events")
    write("adjust_trip", t, 125, "fake")
    write("record_receipt", "2026-09-01", "THU TIỀN", 100)
    before_move = total()
    pg.sql(f"UPDATE sokhach.month_state SET locked=true WHERE customer_id={c} AND month='2026-08-01'")
    reject_call(pg, "edit_trip_info", c, version(pg, c), "locked-destination", t,
                "event_date", "2026-08-10", error="MONTH_LOCKED")
    fixture_open_month(pg, c, "2026-08-01")
    write("edit_trip_info", t, "event_date", "2026-08-10")
    require(total() == before_move, "web move changed customer total")
    require(pg.value(f"SELECT debt_month FROM sokhach.adjustment WHERE trip_id={t}") == current, "rewrote adjustment FK month")
    require(pg.value(f"SELECT debt_month FROM sokhach.v_adjustment_current WHERE trip_id={t}") == "2026-08-01", "adjustment did not follow trip")
    require(allocations(pg, c, "PH-001") == [("2026-08-01", "debt", "100")], "move did not reallocate FIFO")
    require(any(m["month"] == "2026-08-01" for m in call(pg, "get_ledger", c)["months"]), "moved month missing")
    pg.sql(f"UPDATE sokhach.month_state SET locked=true WHERE customer_id={c} AND month='2026-08-01'")
    reject_call(pg, "edit_trip_price", c, version(pg, c), "current-lock", t, 101, None, error="MONTH_LOCKED")
    write("set_month_lock", "2026-08-01", "false")
    write("edit_trip_info", t, "event_date", "2026-08-11")
    write("edit_trip_price", t, 110, None)
    for locked in (False,):
        write("set_month_lock", "2026-08-01", str(locked).lower())
        for field, value in [("container", f" FAKE {locked} "), ("carrier", f"FAKE {locked}"),
                             ("origin", f"A {locked}"), ("destination", f"B {locked}")]:
            before = version(pg, c)
            old = pg.value(f"SELECT {field} FROM sokhach.v_trip_current WHERE id={t}")
            key = f"cell-{before}"
            write("edit_trip_info", t, field, value, key=key)
            audit = json.loads(pg.value(f"SELECT jsonb_build_object('before',\"before\",'after',\"after\",'actor',actor) FROM sokhach.event WHERE customer_id={c} AND idempotency_key={lit(key)} AND kind='trip_edit'"))
            require(audit["before"]["trip"]["value"] == old and audit["actor"] == "fake-editor", "edit audit before/actor")
            require(audit["after"]["trip"]["value"] == (value.replace(" ", "").upper() if field == "container" else value.strip()), "edit audit after")
            reject_call(pg, "edit_trip_info", c, before, key, t, field, "different", error="IDEMPOTENCY_CONFLICT")
    write("edit_trip_info", t, "event_date", "2026-08-10")
    for args, error in [((t, "carrier", "FAKE False"), "NO_CHANGE"), ((t, "price", "1"), "INVALID_FIELD"),
                        ((t, "event_date", "9999-01-01"), "FUTURE_DATE"), ((t, "carrier", " "), "INVALID_TRIP_INPUT")]:
        reject_call(pg, "edit_trip_info", c, version(pg, c), "info-"+error, *args, error=error)
    pg.sql(f"INSERT INTO sokhach.baseline_trip_ref VALUES({cut},'BASE','BASE','2026-08-10')")
    held = write("edit_trip_info", t, "container", "BASE")
    require(held["pending_review"] and pg.value(f"SELECT status FROM sokhach.v_trip_current WHERE id={t}") == "pending_review", "duplicate edit not quarantined")
    write("edit_trip_info", t, "container", "FAKE-CLEAN")
    require(pg.value(f"SELECT status FROM sokhach.v_trip_current WHERE id={t}") == "pending_review", "edit auto-confirmed")
    balance = total()
    write("delete_trip", t)
    require(total() == balance, "pending deletion changed total")
    write("delete_trip", locked_trip)
    require(total() == balance-100, "locked deletion amount")
    again = write("paste_trips", current, json.dumps([mixed[1]]))["trip_ids"][0]
    require(pg.value(f"SELECT status FROM sokhach.v_trip_current WHERE id={again}") == "confirmed", "deleted web duplicate blocked paste")
    write("adjust_trip", again, 150, "fake")
    balance = total()
    write("delete_trip", again, key="delete-adjusted")
    require(total() == balance-150, "delete did not remove adjusted amount")
    audit = json.loads(pg.value(f"SELECT \"before\"->'trip' FROM sokhach.event WHERE customer_id={c} AND idempotency_key='delete-adjusted' AND kind='trip_delete'"))
    require(audit["amount_vnd"] == "150" and audit["unit_price_vnd"] == "150"
            and audit["other_fee_vnd"] is None and audit["debt_month"] == "2026-09-01", "delete current amount snapshot")
    open_id = write("paste_trips", current, trip_json("20", container="FAKE-OPEN", month=current))["trip_ids"][0]
    balance = total()
    write("delete_trip", open_id)
    require(total() == balance-20, "open deletion")
    reject_call(pg, "delete_trip", c, version(pg, c), "deleted-again", t, error="TRIP_NOT_FOUND")
    atomic_trip = write("paste_trips", current, trip_json("20", container="FAKE-ATOMIC", month=current))["trip_ids"][0]
    pg.sql("CREATE FUNCTION public.nhap_abort() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'NHAP_ABORT'; END $$")
    try:
        for name, args, table in [
            ("edit_trip_info", (atomic_trip, "carrier", "FAKE CHANGE"), "trip_info_rev"),
            ("delete_trip", (atomic_trip,), "trip_info_rev"),
            ("edit_legacy_trip", (ids[2], "unit_price_vnd", "94000000"), "legacy_trip_rev"),
            ("delete_legacy_trip", (ids[2],), "legacy_trip_rev"),
        ]:
            def state():
                return (version(pg, c), total(), pg.value(f"SELECT jsonb_build_array("
                    f"(SELECT count(*) FROM sokhach.event WHERE customer_id={c}),"
                    f"(SELECT count(*) FROM sokhach.trip_info_rev WHERE customer_id={c}),"
                    f"(SELECT count(*) FROM sokhach.legacy_trip_rev WHERE customer_id={c}),"
                    f"(SELECT count(*) FROM sokhach.adjustment WHERE customer_id={c}))"))
            before = state()
            pg.sql(f"CREATE TRIGGER nhap_abort BEFORE INSERT ON sokhach.{table} FOR EACH ROW EXECUTE FUNCTION public.nhap_abort()")
            try:
                reject_call(pg, name, c, version(pg, c), "fault-"+name, *args, error="NHAP_ABORT")
                require(state() == before, f"{name} left partial changes")
            finally:
                pg.sql(f"DROP TRIGGER nhap_abort ON sokhach.{table}")
    finally:
        pg.sql("DROP FUNCTION public.nhap_abort()")
    fee = write("paste_trips", current, json.dumps([{"container": None, "date": None,
        "unitPriceVnd": None, "otherFeeVnd": "5"}]))["trip_ids"][0]
    for field, value in [("carrier", "FAKE"), ("origin", "A"), ("destination", "B"),
                         ("event_date", current), ("container", "FAKE-FEE-CONVERTED")]:
        write("edit_trip_info", fee, field, value)
    write("edit_trip_price", fee, 7, None)
    require(pg.value(f"SELECT jsonb_agg(to_jsonb(o) ORDER BY id) FROM sokhach.opening_balance o WHERE customer_id={c}") == opening, "opening changed")
    require(pg.value(f"SELECT jsonb_agg(to_jsonb(l) ORDER BY id) FROM sokhach.legacy_row l WHERE customer_id={c}") == legacy, "legacy source changed")
    for table in ("trip", "adjustment", "legacy_row", "opening_balance", "trip_info_rev", "legacy_trip_rev"):
        pg.rejects(f"UPDATE sokhach.{table} SET customer_id=customer_id WHERE customer_id={c}", message="immutable row")
        pg.rejects(f"DELETE FROM sokhach.{table} WHERE customer_id={c}", message="immutable row")
    assert_allocations(pg, c)


CASES.append(case("NHAP-SHEET.01", "BEHAVIOR", "Append-only edits, deletion, exact legacy examples, moved debt and FIFO",
                  check="nhap_sheet", functions=("edit_trip_info", "delete_trip", "edit_legacy_trip", "delete_legacy_trip")))

CHECKS = {"dashboard": check_dashboard, "nhap_sheet": check_nhap_sheet, "csm_reference": check_csm_reference, "csm_locks": check_csm_locks, "csm_migration": check_csm_migration,
          "dedup": check_dedup, "trip_review": check_trip_review, "monthly_identity": check_monthly_identity, "field_adjustment": check_field_adjustment,
          "adjustment_source": check_adjustment_source, "shipper_write_sync": check_shipper_write_sync,
          "fee_intent_after_price": check_fee_intent_after_price,
          "future_receipt": check_future_receipt, "void_get": check_void_get,
          "immutable": check_immutable, "roles": check_roles, "numbers": check_numbers,
          "gate_view": check_gate_view, "legacy": check_legacy, "import_guard": check_import_guard,
          "negative": check_negative, "events": check_events, "evidence": check_evidence,
           "fee": check_fee, "model": check_model, "model_edges": check_model_edges,
           "sheet_cross_customer": check_sheet_cross_customer,
           "atomic": check_atomic,
           "invariant_rejections": check_invariant_rejections,
           "idempotency": check_idempotency, "concurrent": check_concurrent,
           "pid_order": check_pid_order,
          "void": check_void, "locks": check_locks, "actor": check_actor,
          "input": check_input, "opening_fifo": check_opening_fifo,
          "negative_receipt": check_negative_receipt, "snapshots": check_snapshots,
          "ledger_fee": check_ledger_fee, "golden": check_golden,
          "opening_import": check_opening_import, "cutover_gate": check_cutover_gate,
          "import_behavior": check_import_behavior}


CHECKS.update({f"ct_{n:02d}": globals()[f"check_ct_{n:02d}"] for n in range(1, 16)})

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


def check_migration(pg: Pg) -> None:
    from v7_load_baseline_refs import apply
    from v7_load_real_copy import LoadError
    old_ref = "460882d9d5d60c3fc8eeac5161a0058219dc09d4"
    # Dedicated database; shared roles already exist in this disposable cluster.
    old_schema = run(["git", "show", old_ref + ":specs/v7-backend/schema-draft.sql"], cwd=ROOT).stdout
    old_functions = run(["git", "show", old_ref + ":cong-no-web-handoff/tools/v7_backend_functions.sql"], cwd=ROOT).stdout
    old_schema = re.sub(r"^CREATE ROLE .*;\n", "", old_schema, flags=re.M)
    db = "webdebit_v7_migration_test"
    pg.sql(f"CREATE DATABASE {db}", database="postgres")
    class CopyPg(Pg):
        def sql(self, sql, **kwargs):
            return super().sql(sql, **{**kwargs, "database": db})
    copy = CopyPg(pg.name, pg.run_id)
    copy.sql(old_schema)
    copy.sql(old_functions)
    # Real old fixture, with 236 fake customer identities; no financial source data.
    seed(copy, references=False)
    copy.sql("INSERT INTO sokhach.customer(name) SELECT 'FAKE '||g FROM generate_series(2,236) g")
    copy.sql("UPDATE sokhach.cutover_customer SET status='verified' WHERE customer_id=1; "
             "UPDATE sokhach.cutover SET status='verified' WHERE id=1; "
             "UPDATE sokhach.cutover SET status='active' WHERE id=1; "
             "UPDATE sokhach.cutover_customer SET status='active' WHERE customer_id=1")
    snapshot = copy.value("SELECT jsonb_agg(row_to_json(s)) FROM (SELECT c.id,v.debt_month,v.outstanding_vnd "
                          "FROM sokhach.customer c LEFT JOIN sokhach.v_outstanding_month v ON v.customer_id=c.id ORDER BY c.id,v.debt_month) s")
    migration = (ROOT / "specs/v7-backend/migrations/001-m2-11-dedup.sql").read_text(encoding="utf-8")
    copy.rejects(migration.replace("COMMIT;", "DO $$ BEGIN RAISE EXCEPTION 'FAKE_MIGRATION_FAULT'; END $$; COMMIT;"),
                 message="FAKE_MIGRATION_FAULT")
    copy.true("NOT EXISTS (SELECT FROM information_schema.columns WHERE table_schema='sokhach' AND table_name='trip' AND column_name='status')",
              "failed migration did not roll back")
    copy.sql(migration)
    copy.sql(migration)  # idempotent
    copy.sql((ROOT / "cong-no-web-handoff/tools/migrations/2026-10-21-v7-csm.sql").read_text(encoding="utf-8"))
    review = REVIEW_MIGRATION.read_text(encoding="utf-8")
    copy.rejects(review.replace("COMMIT;", "DO $$ BEGIN RAISE EXCEPTION 'REVIEW_MIGRATION_FAULT'; END $$; COMMIT;"),
                 message="REVIEW_MIGRATION_FAULT")
    copy.true("NOT EXISTS (SELECT FROM information_schema.columns WHERE table_schema='sokhach' "
              "AND table_name='trip' AND column_name='reviewed_by_event')", "failed review migration did not roll back")
    copy.sql(review)
    nhap = NHAP_MIGRATION.read_text(encoding="utf-8")
    copy.rejects(nhap.replace("COMMIT;", "DO $$ BEGIN RAISE EXCEPTION 'NHAP_FAULT'; END $$; COMMIT;"), message="NHAP_FAULT")
    copy.true("to_regclass('sokhach.trip_info_rev') IS NULL", "failed NHAP migration left revision table")
    drift = """WITH e AS (INSERT INTO sokhach.event(customer_id,kind,actor,"before","after")
        VALUES(1,'adjust_month','fake','{"month":"2026-01-01"}','{"adjustment":1}') RETURNING id)
        INSERT INTO sokhach.adjustment(customer_id,debt_month,amount_vnd,actor,created_by_event)
        SELECT 1,'2026-01-01',1,'fake',id FROM e;
"""
    balance_check = "DO $$ BEGIN\n IF EXISTS(SELECT 1 FROM nhap_sheet_before"
    require(balance_check in nhap, "migration balance checker marker missing")
    copy.rejects(nhap.replace(balance_check, drift+balance_check), message="NHAP_SHEET_BALANCE_CHANGED")
    copy.true("to_regclass('sokhach.trip_info_rev') IS NULL", "balance mismatch did not rollback schema")
    copy.sql(nhap)
    copy.sql(nhap)
    mh = MH_MIGRATION.read_text(encoding="utf-8")
    copy.rejects(mh.replace("COMMIT;", "DO $$ BEGIN RAISE EXCEPTION 'MH_FAULT'; END $$; COMMIT;"), message="MH_FAULT")
    copy.true("position('commodity' in pg_get_functiondef('sokhach.list_customers()'::regprocedure))=0",
              "failed MH migration left new list_customers")
    copy.sql(mh)
    copy.sql(mh)
    dashboard = (ROOT / "cong-no-web-handoff/tools/migrations/2026-10-24-v7-dashboard.sql").read_text(encoding="utf-8")
    copy.rejects(dashboard.replace("COMMIT;", "DO $$ BEGIN RAISE EXCEPTION 'DASHBOARD_FAULT'; END $$; COMMIT;"),
                 message="DASHBOARD_FAULT")
    copy.sql(dashboard)
    copy.sql(dashboard)
    copy.sql(LOCKED_TRIP_MIGRATION.read_text(encoding="utf-8"))
    copy.sql(LOCKED_TRIP_MIGRATION.read_text(encoding="utf-8"))
    sheet = SHEET_MIGRATION.read_text(encoding="utf-8")
    copy.sql(sheet)
    copy.sql(sheet)
    matrix = MATRIX_MIGRATION.read_text(encoding="utf-8")
    copy.sql(matrix)
    copy.sql(matrix)
    require(copy.value("SELECT jsonb_agg(row_to_json(s)) FROM (SELECT c.id,v.debt_month,v.outstanding_vnd "
                       "FROM sokhach.customer c LEFT JOIN sokhach.v_outstanding_month v ON v.customer_id=c.id ORDER BY c.id,v.debt_month) s") == snapshot,
            "migration changed fake 236-customer balances")
    catalog = "SELECT jsonb_object_agg(proname,pg_get_functiondef(oid)) FROM pg_proc WHERE pronamespace='sokhach'::regnamespace"
    require(copy.value(catalog) == pg.value(catalog), "migration function definitions differ from fresh schema")
    cols = "SELECT jsonb_agg(row_to_json(s)) FROM (SELECT table_name,column_name,data_type,is_nullable,column_default "
    cols += "FROM information_schema.columns WHERE table_schema='sokhach' ORDER BY table_name,column_name) s"
    require(copy.value(cols) == pg.value(cols), "migration columns differ")
    views = "SELECT jsonb_object_agg(viewname,definition) FROM pg_views WHERE schemaname='sokhach'"
    require(copy.value(views) == pg.value(views), "migration views differ")
    copy.sql("CREATE ROLE v7_loader LOGIN IN ROLE sokhach_owner; "
             f"REVOKE CONNECT ON DATABASE {db} FROM PUBLIC; GRANT CONNECT ON DATABASE {db} TO v7_loader,v7_app")
    checker = (ROOT / "cong-no-web-handoff/tools/v7_post_deploy_check.sql").read_text(encoding="utf-8")
    copy.sql(f"\\set db_v7 {db}\n\\set loader_role v7_loader\n\\set expect_customers 236\n" + checker)
    # Loader conflict/retry and balance checks use isolated reference-only cutover.
    copy.sql("ALTER TABLE sokhach.baseline_trip_ref DISABLE TRIGGER baseline_trip_ref_immutable; "
             "DELETE FROM sokhach.baseline_trip_ref; "
             "ALTER TABLE sokhach.baseline_trip_ref ENABLE TRIGGER baseline_trip_ref_immutable; "
             "SELECT 1")
    from v7_load_direct import DirectPg
    refs = [("ALT:FAKE:20260101", "FAKE", "2026-01-01")]
    direct = DirectPg("/var/run/postgresql", db, "v7_loader", psql_command=pg.psql_command())
    try:
        require(apply(direct, refs, "a" * 64, 1) == "LOADED", "loader failed")
        # Temp table is per-call; drop before exercising idempotent retry in same transaction.
        direct.sql("DROP TABLE incoming_refs")
        require(apply(direct, refs, "a" * 64, 1) == "UNCHANGED", "loader retry duplicated")
        direct.close(commit=True)
    except Exception:
        direct.close()
        raise
    rejected = DirectPg("/var/run/postgresql", db, "v7_loader", psql_command=pg.psql_command())
    try:
        try:
            apply(rejected, refs, "b" * 64, 1)
        except LoadError:
            pass
        else:
            raise HarnessError("wrong manifest accepted")
    finally:
        rejected.close()
    require(copy.value("SELECT count(*) FROM sokhach.baseline_trip_ref") == "1", "loader failure changed references")
    # A legacy trip without container gets no reference: counted via skipped, never silently dropped.
    copy.sql("ALTER TABLE sokhach.legacy_row DISABLE TRIGGER legacy_row_insert_guard; "
             "INSERT INTO sokhach.legacy_row(customer_id,cutover_id,debt_month,kind,display,source_tab,source_row,created_by_event) "
             "VALUES (1,1,'2026-01-01','trip','{\"fake\":true,\"container\":\"\",\"date\":null}','FAKE',9,1); "
             "ALTER TABLE sokhach.legacy_row ENABLE TRIGGER legacy_row_insert_guard")
    for skipped, expect in ((0, None), (1, "UNCHANGED")):
        nocontainer = DirectPg("/var/run/postgresql", db, "v7_loader", psql_command=pg.psql_command())
        try:
            try:
                got = apply(nocontainer, refs, "a" * 64, 1, skipped)
            except LoadError:
                got = None
        finally:
            nocontainer.close()
        require(got == expect, f"no-container legacy trip handling wrong for skipped={skipped}")
    require(copy.value("SELECT count(*) FROM sokhach.baseline_trip_ref") == "1", "no-container trip got a reference")
    check_dedup(copy)
    # Reproduce deployment order: the locked-trip migration replaced the earlier shipper reader.
    shipper = (ROOT / "cong-no-web-handoff/tools/migrations/2026-10-24-v7-shipper.sql").read_text(encoding="utf-8")
    ledger_shipper = (ROOT / "cong-no-web-handoff/tools/migrations/2026-10-26-v7-ledger-shipper-read.sql").read_text(encoding="utf-8")
    reader = "pg_get_functiondef('sokhach.get_ledger(bigint)'::regprocedure)"
    balances = "SELECT jsonb_agg(row_to_json(s)) FROM (SELECT c.id,v.debt_month,v.outstanding_vnd "
    balances += "FROM sokhach.customer c LEFT JOIN sokhach.v_outstanding_month v ON v.customer_id=c.id ORDER BY c.id,v.debt_month) s"
    before_repair = copy.value(balances)
    copy.sql(shipper)
    copy.sql(LOCKED_TRIP_MIGRATION.read_text(encoding="utf-8"))
    copy.true(f"position('shipper' in {reader})=0", "locked-trip migration did not reproduce missing shipper")
    copy.sql(ledger_shipper)
    copy.sql(ledger_shipper)  # read-only function repair is idempotent
    copy.true(f"position('shipper' in {reader})>0", "ledger reader still omits shipper")
    copy.sql(SYNC_MIGRATION.read_text(encoding="utf-8"))
    copy.true(f"position('shipper' in {reader})>0", "write sync migration lost shipper reader")
    require(copy.value(balances) == before_repair,
            "shipper reader repair changed fake balances")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--list", action="store_true", help="list cases without Docker")
    ap.add_argument("--report", type=Path, help="write JSON report")
    ap.add_argument("--migration-test", action="store_true")
    ap.add_argument("--m2-11-only", action="store_true", help="focused development checks")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--expect-red", action="store_true", default=True,
                      help="default: missing command functions may fail")
    mode.add_argument("--strict", action="store_true", help="require every case to pass")
    args = ap.parse_args()
    selected = [c for c in CASES if not args.m2_11_only or c["id"] == "7.24"]
    if args.list:
        for c in CASES:
            print(f"{c['id']}\t{c['label']}\t{c['title']}")
        return 0
    run_id = uuid.uuid4().hex
    name = f"webdebit-v7-test-{run_id}"
    volume = name
    report = {"run_id": run_id, "image": IMAGE, "schema": str(SCHEMA),
              "schema_sha256": hashlib.sha256(SCHEMA.read_bytes().replace(b"\r\n", b"\n")).hexdigest(),
              "functions": str(FUNCTIONS),
              "functions_sha256": hashlib.sha256(FUNCTIONS.read_bytes().replace(b"\r\n", b"\n")).hexdigest(),
              "sql_hash_normalization": "CRLF to LF",
              "cases": [], "cleanup": "not_started"}
    volume_created = False
    container_id = None
    fatal = None
    try:
        require(shutil.which("docker") is not None, "Docker CLI unavailable")
        run(["docker", "volume", "create", "--label", f"{LABEL_TEST}={LABEL_VALUE}",
             "--label", f"{LABEL_RUN}={run_id}", volume])
        volume_created = True
        inspect_volume(volume, run_id)
        run(["docker", "run", "--detach", "--name", name, "--label", f"{LABEL_TEST}={LABEL_VALUE}",
             "--label", f"{LABEL_RUN}={run_id}", "--network", "none", "--volume",
             f"{volume}:/var/lib/postgresql", "--env", "POSTGRES_HOST_AUTH_METHOD=trust", IMAGE], timeout=240)
        container_id = inspect_owned(name, volume, run_id)
        require(container_id is not None, "container absent after Docker run")
        report["container_id"] = container_id
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            logs = run(["docker", "logs", name], check=False, timeout=10)
            if "PostgreSQL init process complete; ready for start up." in logs.stdout + logs.stderr:
                break
            time.sleep(0.25)  # readiness polling only; never contention evidence
        else:
            raise HarnessError("PostgreSQL init marker timed out")
        # The init marker precedes the final restart; wait until the server accepts connections.
        while time.monotonic() < deadline:
            if run(["docker", "exec", name, "pg_isready", "-U", "postgres"], check=False, timeout=10).returncode == 0:
                break
            time.sleep(0.25)  # readiness polling only; never contention evidence
        else:
            raise HarnessError("PostgreSQL readiness timed out")
        pg = Pg(name, run_id)
        require(pg.sql("SELECT current_database()", database="postgres").stdout.strip() == "postgres",
                "unexpected initial database")
        inspect_owned(name, volume, run_id, container_id)
        inspect_volume(volume, run_id)
        pg.sql(f"CREATE DATABASE {DATABASE}", database="postgres")
        marker = f"codex_v7_run_id={run_id}"
        pg.sql(f"COMMENT ON DATABASE {DATABASE} IS '{marker}'")
        require(pg.value("SELECT shobj_description(oid,'pg_database') FROM pg_database WHERE datname=current_database()") == marker,
                "database marker mismatch")
        inspect_owned(name, volume, run_id, container_id)
        inspect_volume(volume, run_id)
        run(["docker", "exec", "-i", *pg.env, name, "psql", "-X", "-v", "ON_ERROR_STOP=1",
             "-U", "postgres", "-d", DATABASE], input_text=SCHEMA.read_text(encoding="utf-8"))
        run(["docker", "exec", "-i", *pg.env, name, "psql", "-X", "-v", "ON_ERROR_STOP=1",
             "-U", "postgres", "-d", DATABASE], input_text=FUNCTIONS.read_text(encoding="utf-8"))
        pg.sql(SHEET_MIGRATION.read_text(encoding="utf-8"))
        report["postgres_version"] = pg.value("SHOW server_version")
        pg.sql("CREATE ROLE v7_app LOGIN IN ROLE sokhach_app; CREATE ROLE v7_reader LOGIN IN ROLE sokhach_reader")
        if args.migration_test:
            check_migration(pg)
            report["migration"] = "pass"
        seed(pg)
        # Existing schema checks share customer 1; run before isolated behavioral books.
        ordered = sorted(selected, key=lambda c: 0 if c["label"] == "SCHEMA" else 1)
        for c in ordered:
            row = {"id": c["id"], "label": c["label"], "result": "fail", "reason": ""}
            try:
                if c["label"] == "SKIPPED_OPEN":
                    row.update(result="skipped", reason=c["open_reason"])
                elif c["label"] in ("NEEDS_FUNCTION", "BEHAVIOR"):
                    missing = [f for f in c["functions"] if pg.value(
                        f"SELECT count(*) FROM pg_proc WHERE pronamespace='sokhach'::regnamespace AND proname='{f}'") == "0"]
                    if missing:
                        row["reason"] = "function does not exist: " + ", ".join(missing)
                    else:
                        require(c["check"] in CHECKS, "function present but no behavioral assertion")
                        row["executed"] = True
                        evidence = CHECKS[c["check"]](pg)
                        row.update(result="pass", reason=evidence or "PostgreSQL behavioral assertion passed")
                else:
                    evidence = CHECKS[c["check"]](pg)
                    row.update(result="pass", reason=evidence or "PostgreSQL schema assertion passed")
            except (HarnessError, OSError, ValueError, KeyError, TypeError, AssertionError,
                    subprocess.TimeoutExpired) as exc:
                row["reason"] = str(exc)
            report["cases"].append(row)
        position = {c["id"]: i for i, c in enumerate(CASES)}
        report["cases"].sort(key=lambda row: position[row["id"]])
    except (HarnessError, OSError, ValueError) as exc:
        fatal = str(exc)
        report["error"] = fatal
    finally:
        try:
            owned = inspect_owned(name, volume, run_id, container_id) if volume_created else None
            if owned:
                run(["docker", "rm", "--force", owned])
            if volume_created:
                inspect_volume(volume, run_id)
                run(["docker", "volume", "rm", volume])
            report["cleanup"] = "verified_and_removed" if volume_created else "nothing_created"
        except (HarnessError, OSError, ValueError) as exc:
            report["cleanup"] = "failed: " + str(exc)
            fatal = str(exc)
        if len(report["cases"]) < len(selected):
            done = {c["id"] for c in report["cases"]}
            for c in selected:
                if c["id"] not in done:
                    report["cases"].append({
                        "id": c["id"], "label": c["label"],
                        "result": "skipped" if c["label"] == "SKIPPED_OPEN" else "fail",
                        "reason": c["open_reason"] if c["label"] == "SKIPPED_OPEN"
                        else "harness did not reach case: " + (fatal or "unknown setup failure")})
        counts = {label: {result: sum(c["label"] == label and c["result"] == result for c in report["cases"])
                          for result in ("pass", "fail", "skipped")}
                  for label in ("SCHEMA", "BEHAVIOR", "NEEDS_FUNCTION", "SKIPPED_OPEN")}
        report["summary"] = counts
        report["exit_code"] = int(bool(fatal) or len(report["cases"]) != len(selected)
                                  or any(c["result"] != "pass" for c in report["cases"]
                                         if args.strict or c["label"] in ("SCHEMA", "BEHAVIOR")
                                         or c.get("executed")))
        if args.report:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return report["exit_code"]


if __name__ == "__main__":
    sys.exit(main())
