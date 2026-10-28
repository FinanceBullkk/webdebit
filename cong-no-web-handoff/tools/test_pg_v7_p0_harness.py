#!/usr/bin/env python3
"""P0 write-path gaps: fake data, one owned disposable PostgreSQL container.

Contract: only test code; no production access or SQL changes. Each race proves
blocking through pg_blocking_pids, exact version delta and committed invariants.
Open policy cases stay skipped (also under --strict); never count as acceptance.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import time
import uuid
from functools import partial
from pathlib import Path

from test_pg_v7_backend import (
    DATABASE,
    FUNCTIONS,
    IMAGE,
    LABEL_RUN,
    LABEL_TEST,
    LABEL_VALUE,
    SCHEMA,
    HarnessError,
    Pg,
    PsqlSession,
    allocations,
    assert_allocations,
    call,
    case,
    inspect_owned,
    inspect_volume,
    lit,
    months,
    new_book,
    reject_call,
    require,
    run,
    trip_json,
    version,
)

COMMANDS = ("record_receipt", "paste_trips", "edit_trip_price", "adjust_month", "adjust_trip",
            "edit_receipt_meta", "void_receipt", "set_month_lock")


def statement(name, args):
    return "SELECT sokhach." + name + "(" + ",".join(
        "NULL" if x is None else lit(x) for x in args) + ")"


def snapshot(pg, c):
    # Full customer rows catch silent writes, audit-only duplicates and old-line changes.
    tables = ("customer", "trip", "trip_price_rev", "adjustment", "receipt",
              "receipt_line", "event", "idempotency", "month_state", "opening_balance")
    return {table: pg.value(
        "SELECT coalesce(jsonb_agg(to_jsonb(t) ORDER BY to_jsonb(t)::text),'[]')::text "
        f"FROM sokhach.{table} t WHERE " + (f"id={c}" if table == "customer" else f"customer_id={c}"))
        for table in tables}


def verify(pg, c):
    pg.sql(f"SELECT sokhach._check_allocations({c})")
    assert_allocations(pg, c)
    months(pg, c)  # get_ledger independently checks monthly identity.
    pg.true(f"NOT EXISTS (SELECT 1 FROM sokhach.v_outstanding_month WHERE customer_id={c} "
            "AND outstanding_vnd<0)", "positive fake debt was overallocated")


def setup(pg):
    c = new_book(pg, ("2026-01-01", 100), ("2026-02-01", 200))
    call(pg, "set_month_lock", c, 0, "setup-open", "2026-01-01", "false")
    call(pg, "set_month_lock", c, 1, "setup-open-feb", "2026-02-01", "false")
    trip = call(pg, "paste_trips", c, 2, "setup-trip", "2026-01-01", trip_json())["trip_ids"][0]
    receipt = call(pg, "record_receipt", c, 3, "setup-receipt", "2026-03-01", "THU TIỀN", 40)
    return c, trip, receipt["pid"]


def payloads(name, trip, pid):
    return {
        "record_receipt": (("2026-03-02", "THU TI\u1ec0N", 20), ("2026-03-02", "THU TI\u1ec0N", 21)),
        "paste_trips": (("2026-01-01", trip_json("20", container="FAKE-NEW")),
                        ("2026-01-01", trip_json("21", container="FAKE-NEW"))),
        "edit_trip_price": ((trip, 110, None), (trip, 111, None)),
        "adjust_month": (("2026-02-01", 10, "FAKE"), ("2026-02-01", 11, "FAKE")),
        "adjust_trip": ((trip, 110, "FAKE"), (trip, 111, "FAKE")),
        "edit_receipt_meta": ((pid, "2026-03-02", "KHÁC"), (pid, "2026-03-03", "KHÁC")),
        "void_receipt": ((pid, "FAKE wrong"), (pid, "FAKE different")),
        "set_month_lock": (("2026-01-01", "true"), ("2026-01-01", "false")),
    }[name]


def race(pg, c, first, second, error):
    before_version = version(pg, c)
    a = PsqlSession(pg, f"p0_a_{c}")
    b = None
    try:
        b = PsqlSession(pg, f"p0_b_{c}")
        for session in (a, b):
            session.send("SET statement_timeout='15s'; SET lock_timeout='12s'; "
                         "BEGIN; SET LOCAL sokhach.actor='p0'; SELECT pg_backend_pid()")
        pa, pb = int(a.line()), int(b.line())
        a.send(statement(*first))
        result = json.loads(a.line())
        b.send(statement(*second))
        deadline = time.monotonic() + 8
        blocked = False
        while time.monotonic() < deadline:
            if pg.value(f"SELECT {pa}=ANY(pg_blocking_pids({pb}))") == "t":
                blocked = True
                break
            require(b.proc.poll() is None, "second connection exited before blocking")
        require(blocked, "no pg_blocking_pids evidence")
        a.send("COMMIT; SELECT 'committed'")
        require(a.line() == "committed", "first transaction failed commit")
        committed = snapshot(pg, c)
        b.proc.wait(timeout=18)
        stderr = b.proc.stderr.read()
        require(b.proc.returncode != 0 and error in stderr,
                f"expected {error}; got {stderr[-1200:]}")
        require(snapshot(pg, c) == committed, "rejected concurrent command changed data")
        require(version(pg, c) == before_version + 1 and result["version"] == before_version + 1,
                "race version did not increment exactly once")
        verify(pg, c)
        return f"pg_blocking_pids: {pb} blocked by {pa}; {error}; version +1"
    finally:
        a.close()
        if b is not None:
            b.close()


def check_idempotency(pg, name, concurrent=False):
    c, trip, pid = setup(pg)
    good, bad = payloads(name, trip, pid)
    v = version(pg, c)
    args = (c, v, "p0-idem", *good)
    changed = (c, v, "p0-idem", *bad)
    evidence = ""
    if concurrent:
        evidence = race(pg, c, (name, args), (name, changed), "IDEMPOTENCY_CONFLICT")
        first = call(pg, name, *args)
    else:
        first = call(pg, name, *args)
    saved = snapshot(pg, c)
    require(call(pg, name, *args) == first, "replay result differs")
    require(snapshot(pg, c) == saved, "replay wrote data")
    reject_call(pg, name, *changed, error="IDEMPOTENCY_CONFLICT")
    # Keys are customer-scoped; command is part of hashed payload in _begin_command.
    if name == "record_receipt":
        reject_call(pg, "adjust_month", c, v, "p0-idem", "2026-01-01", 1, "FAKE",
                    error="IDEMPOTENCY_CONFLICT")
    else:
        reject_call(pg, "record_receipt", c, v, "p0-idem", "2026-03-01", "THU TI\u1ec0N", 1,
                    error="IDEMPOTENCY_CONFLICT")
    require(snapshot(pg, c) == saved and version(pg, c) == v + 1,
            "conflict changed rows or version")
    verify(pg, c)
    return evidence or "exact replay; changed payload and command rejected; full rows unchanged"


def check_race(pg, kind, reverse=False):
    c, trip, pid = setup(pg)
    v = version(pg, c)
    receipt = ("record_receipt", (c, v, "race-receipt", "2026-03-02", "THU TIỀN", 30))
    void = ("void_receipt", (c, v, "race-void", pid, "FAKE wrong"))
    other = {
        "double_void": ("void_receipt", (c, v, "race-void-2", pid, "FAKE wrong")),
        "void_record": receipt,
        "record_paste": ("paste_trips", (c, v, "race-paste", "2026-01-01", trip_json("20"))),
        "record_price": ("edit_trip_price", (c, v, "race-price", trip, 110, None)),
    }[kind]
    first = void if kind in ("double_void", "void_record") else receipt
    if reverse:
        first, other = other, first
    evidence = race(pg, c, first, other, "STALE_LEDGER")
    saved = snapshot(pg, c)
    if kind == "double_void":
        reject_call(pg, "void_receipt", c, v+1, "void-after-race", pid, "FAKE wrong",
                    error="RECEIPT_ALREADY_VOID")
        require(snapshot(pg, c) == saved and allocations(pg, c, pid) == [], "double reversal")
        pg.true(f"(SELECT count(*)=1 FROM sokhach.event WHERE customer_id={c} AND kind='void')",
                "more than one void event")
    else:
        # Retry rejected operation against committed version: both commands must
        # compose safely, including reallocation after paste/price changes.
        name, args = other
        result = call(pg, name, args[0], v+1, *args[2:])
        require(result["version"] == v+2 and version(pg, c) == v+2,
                "fresh-version retry did not commit exactly once")
        verify(pg, c)
        evidence += "; fresh-version retry committed; version +2"
    return evidence


def current_lines(pg, c):
    return json.loads(pg.value("SELECT coalesce(jsonb_agg(to_jsonb(l) ORDER BY l.id),'[]')::text "
                              f"FROM sokhach.receipt_line l WHERE customer_id={c} "
                              "AND superseded_by_event IS NULL"))


def check_inverse(pg, later=False):
    c = new_book(pg, ("2026-01-01", 60), ("2026-02-01", 70), ("2026-03-01", 80))
    call(pg, "record_receipt", c, 0, "other-before", "2026-04-01", "THU TIỀN", 10)
    before = months(pg, c), current_lines(pg, c)
    target = call(pg, "record_receipt", c, 1, "target", "2026-04-02", "THU TIỀN", 150)
    require(len(allocations(pg, c, target["pid"])) == 3, "target must span three months")
    original = allocations(pg, c, target["pid"])
    if later:
        call(pg, "record_receipt", c, 2, "other-after", "2026-04-03", "THU TIỀN", 20)
    other_lines = [row for row in current_lines(pg, c) if row["receipt_id"] != target["receipt_id"]]
    pre_void = months(pg, c)
    v = version(pg, c)
    result = call(pg, "void_receipt", c, v, "target-void", target["pid"], "FAKE wrong")
    require(result["voided_lines"] == 3 and version(pg, c) == v+1, "inverse count/version wrong")
    require(current_lines(pg, c) == other_lines, "void touched other receipt rows")
    require(allocations(pg, c, target["pid"]) == [], "void left active target lines")
    if not later:
        require((months(pg, c), current_lines(pg, c)) == before, "not exact pre-receipt state")
    else:
        restored = {month[:7]: int(amount) for month, _, amount in original}
        # DA-THU-01: cộng dồn tính theo ngày thu (04/2026), nên chỉ tháng ngày thu trở đi tăng lại 150.
        require(months(pg, c) == [(m, str(int(out)+restored.get(m, 0)),
                str(int(end)+(sum(restored.values()) if m[:7] >= "2026-04" else 0)))
                for m, out, end in pre_void], "void not exact inverse per month")
    verify(pg, c)
    if not later:
        again = call(pg, "record_receipt", c, v+1, "replacement", "2026-04-02", "THU TIỀN", 150)
        require(again["pid"] != target["pid"] and allocations(pg, c, again["pid"]) == original,
                "replacement receipt lost FIFO or reused voided PID")
        require(version(pg, c) == v+2, "replacement version wrong")
        verify(pg, c)


CASES = []
CHECKS = {}
for command in COMMANDS:
    for concurrent in (False, True):
        key = f"idem.{command}" + (".concurrent" if concurrent else "")
        CASES.append(case(key, "BEHAVIOR", key, check=key, functions=(command,)))
        CHECKS[key] = partial(check_idempotency, name=command, concurrent=concurrent)
for kind in ("double_void", "void_record", "record_paste", "record_price"):
    for reverse in ((False,) if kind == "double_void" else (False, True)):
        key = f"race.{kind}" + (".reverse" if reverse else "")
        CASES.append(case(key, "BEHAVIOR", key, check=key))
        CHECKS[key] = partial(check_race, kind=kind, reverse=reverse)
for later in (False, True):
    key = "inverse.preserve_later" if later else "inverse.restore_and_replace"
    CASES.append(case(key, "BEHAVIOR", key, check=key))
    CHECKS[key] = partial(check_inverse, later=later)
CASES.append(case("policy.refund_transfer", "SKIPPED_OPEN", "Refund, excess and cross-ledger transfer",
                  open_reason="D04 refund/excess policy remains open; CT-2SO is a separate scoped contract"))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--list", action="store_true", help="list cases without Docker")
    ap.add_argument("--report", type=Path, help="write JSON report")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--expect-red", action="store_true", default=True,
                      help="default: missing command functions may fail")
    mode.add_argument("--strict", action="store_true", help="require every case to pass")
    args = ap.parse_args()
    if args.list:
        for c in CASES:
            print(f"{c['id']}\t{c['label']}\t{c['title']}")
        return 0
    run_id = uuid.uuid4().hex
    name = f"webdebit-v7-p0-{run_id}"
    volume = name
    report = {"revision": run(["git", "rev-parse", "HEAD"], cwd=SCHEMA.parents[2]).stdout.strip(),
              "harness_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              "run_id": run_id, "image": IMAGE, "schema": str(SCHEMA),
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
        pg.sql(SCHEMA.read_text(encoding="utf-8"))
        pg.sql(FUNCTIONS.read_text(encoding="utf-8"))
        report["postgres_version"] = pg.value("SHOW server_version")
        pg.sql("CREATE ROLE v7_app LOGIN IN ROLE sokhach_app; CREATE ROLE v7_reader LOGIN IN ROLE sokhach_reader")
        # Existing schema checks share customer 1; run before isolated behavioral books.
        ordered = sorted(CASES, key=lambda c: 0 if c["label"] == "SCHEMA" else 1)
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
            except (HarnessError, ValueError, KeyError, TypeError, AssertionError,
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
        if len(report["cases"]) < len(CASES):
            done = {c["id"] for c in report["cases"]}
            for c in CASES:
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
        report["exit_code"] = int(bool(fatal) or len(report["cases"]) != len(CASES)
                                  or any(c["result"] != "pass" for c in report["cases"]
                                         if (c["label"] != "SKIPPED_OPEN" and (args.strict or c["label"] in ("SCHEMA", "BEHAVIOR")))
                                         or c.get("executed")))
        if args.report:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return report["exit_code"]


if __name__ == "__main__":
    sys.exit(main())
