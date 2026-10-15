#!/usr/bin/env python3
"""Run HistoryDB M1 query tests against isolated PostgreSQL with fake source rows."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

TOOLS = Path(__file__).resolve().parent
ROOT = TOOLS.parents[1]
sys.path.insert(0, str(TOOLS))
import test_pg_ledger_schema as lifecycle  # noqa: E402
sys.path.insert(0, str(ROOT / "cong-no-web-handoff" / "web"))
import ledger_db  # noqa: E402

DATABASE = "webdebit_pilot_system"
PILOT_SCHEMA = TOOLS / "pg_pilot_schema.sql"
M1_SCHEMA = TOOLS / "pg_m1_schema.sql"
WORKBOOK_SHA = "a" * 64
ENGINE_SHA = "b" * 64
CAPTURE = "fake-m1-cutover"
OTHER_CAPTURE = "fake-m1-other"
AS_OF = "2026-10-13"
OTHER_AS_OF = "2026-10-14"


class M1QueryRunnerError(RuntimeError):
    pass


class M1HistoryDBTests(unittest.TestCase):
    def setUp(self) -> None:
        self.db = ledger_db.HistoryDB(cutover={
            "capture_id": CAPTURE,
            "as_of": AS_OF,
            "source_workbook_sha256": WORKBOOK_SHA,
            "engine_sha256": ENGINE_SHA,
        })

    def test_01_summary_counts_exceptions_source_rows_and_trips_separately(self) -> None:
        summary = self.db.exception_summary()
        self.assertEqual(summary["exception_count"], 13)
        self.assertEqual(summary["source_row_count"], 8)
        self.assertEqual(summary["trip_source_row_count"], 5)
        self.assertEqual(summary["as_of"], AS_OF)
        self.assertEqual(summary["baseline_status"], "AVAILABLE")
        self.assertEqual(sum(row["trip_source_row_count"] for row in summary["by_code"]), 7)
        unclassified_customers = [row for row in summary["by_customer"]
                                  if row["group_status"] == "UNCLASSIFIED"]
        unclassified_periods = [row for row in summary["by_period"]
                                if row["group_status"] == "UNCLASSIFIED"]
        self.assertEqual(unclassified_customers[0]["exception_count"], 4)
        self.assertEqual(unclassified_periods[0]["exception_count"], 4)

    def test_02_customer_period_code_filter_and_page_total_are_stable(self) -> None:
        first = self.db.exception_page(customer="ACME", period="2026-10", code="A",
                                       page=1, page_size=1)
        second = self.db.exception_page(customer="ACME", period="2026-10", code="A",
                                        page=2, page_size=1)
        self.assertEqual(first["total_results"], 2)
        self.assertEqual(second["total_results"], 2)
        self.assertEqual(len(first["items"]), 1)
        self.assertEqual(len(second["items"]), 1)
        self.assertNotEqual(first["items"][0]["exception_no"], second["items"][0]["exception_no"])
        source = first["items"][0]["source_identity"]
        self.assertEqual(source, {"capture_id": CAPTURE, "as_of": AS_OF,
                                  "sheet_gid": 10, "source_row": 7})
        all_page = self.db.exception_page(page=1, page_size=50)
        self.assertEqual(all_page["total_results"], 13)
        self.assertTrue(all(item["source_identity"]["capture_id"] == CAPTURE
                            and item["source_identity"]["as_of"] == AS_OF
                            for item in all_page["items"]))
        repeat = self.db.exception_page(page=1, page_size=50)
        self.assertEqual([item["exception_no"] for item in all_page["items"]],
                         [item["exception_no"] for item in repeat["items"]])

    def test_03_unclassified_filters_keep_null_and_blank_rows(self) -> None:
        summary = self.db.exception_summary(customer="", period="")
        page = self.db.exception_page(customer="", period="")
        self.assertEqual(summary["exception_count"], 4)
        self.assertEqual(page["total_results"], 4)
        self.assertTrue(all(item["customer_group_status"] == "UNCLASSIFIED"
                            for item in page["items"]))
        self.assertTrue(all(item["period_group_status"] == "UNCLASSIFIED"
                            for item in page["items"]))

    def test_04_quote_input_is_a_value_not_sql(self) -> None:
        quoted = self.db.exception_page(customer="O'Brien")
        self.assertEqual(quoted["total_results"], 1)
        self.assertEqual(quoted["items"][0]["customer"], "O'Brien")
        page = self.db.exception_page(code="A' OR 1=1 --")
        self.assertEqual(page["total_results"], 0)
        self.assertEqual(page["items"], [])

    def test_04b_nonblank_whitespace_is_part_of_customer_identity(self) -> None:
        plain = self.db.exception_summary(customer="ACME")
        leading = self.db.exception_summary(customer=" ACME")
        trailing = self.db.exception_summary(customer="ACME ")
        self.assertEqual(plain["exception_count"], 6)
        self.assertEqual(leading["exception_count"], 1)
        self.assertEqual(trailing["exception_count"], 1)
        self.assertEqual(self.db.exception_summary(period=" 2026-10")["exception_count"], 1)
        self.assertEqual(self.db.exception_summary(period="2026-10 ")["exception_count"], 1)
        self.assertEqual(self.db.exception_summary(code=" \n")["exception_count"], 2)
        self.assertEqual(self.db.exception_summary(code=" X")["exception_count"], 1)
        self.assertEqual(self.db.exception_summary(code="X ")["exception_count"], 1)
        groups = self.db.exception_summary()
        acme_groups = [row["customer"] for row in groups["by_customer"]
                       if row["customer"] is not None and "ACME" in row["customer"]]
        self.assertEqual(set(acme_groups), {"ACME", " ACME", "ACME "})

    def test_05_customer_delta_is_read_once_from_customer_reconciliation(self) -> None:
        batch = self.db.customer_reconciliations()
        self.assertEqual(batch["total_results"], 3)
        self.assertEqual(batch["reconciliation_status"], "AVAILABLE")
        acme = [row for row in batch["items"] if row["customer"] == "ACME"]
        self.assertEqual(len(acme), 1)
        self.assertEqual(acme[0]["old_book_delta_vnd"], 731)
        self.assertEqual(acme[0]["old_book_delta_status"], "AVAILABLE")
        no_baseline = [row for row in batch["items"] if row["customer"] == "NO-BASELINE"][0]
        missing_delta = [row for row in batch["items"] if row["customer"] == "NO-DELTA"][0]
        self.assertIsNone(no_baseline["old_book_delta_vnd"])
        self.assertEqual(no_baseline["old_book_delta_status"], "NO_BASELINE")
        self.assertIsNone(missing_delta["old_book_delta_vnd"])
        self.assertEqual(missing_delta["old_book_delta_status"], "MISSING")

    def test_06_page_bounds_reject_unbounded_requests(self) -> None:
        for args in ({"page": 0}, {"page": True}, {"page_size": 51}, {"page_size": 0}):
            with self.subTest(args=args), self.assertRaises(ValueError):
                self.db.exception_page(**args)
        with self.assertRaisesRegex(ValueError, "contains NUL"):
            self.db.exception_page(customer="\x00")

    def test_07_cutover_hash_mismatch_fails_closed(self) -> None:
        for workbook_hash, engine_hash in (("c" * 64, ENGINE_SHA), (WORKBOOK_SHA, "c" * 64)):
            with self.subTest(workbook_hash=workbook_hash[:1], engine_hash=engine_hash[:1]):
                bad = ledger_db.HistoryDB(cutover={
                    "capture_id": CAPTURE, "as_of": AS_OF,
                    "source_workbook_sha256": workbook_hash, "engine_sha256": engine_hash,
                })
                with self.assertRaisesRegex(ledger_db.LedgerUnavailable, "source hashes do not match cutover"):
                    bad.exception_summary()

    def test_08_missing_cutover_or_provenance_fails_closed(self) -> None:
        with self.assertRaisesRegex(ledger_db.LedgerUnavailable, "cutover metadata unavailable"):
            ledger_db.HistoryDB().exception_summary()
        absent = ledger_db.HistoryDB(cutover={
            "capture_id": "missing-capture", "as_of": AS_OF,
            "source_workbook_sha256": WORKBOOK_SHA, "engine_sha256": ENGINE_SHA,
        })
        with self.assertRaisesRegex(ledger_db.LedgerUnavailable, "provenance missing"):
            absent.exception_summary()
        invalid_hash = ledger_db.HistoryDB(cutover={
            "capture_id": CAPTURE, "as_of": AS_OF,
            "source_workbook_sha256": None, "engine_sha256": ENGINE_SHA,
        })
        with self.assertRaisesRegex(ledger_db.LedgerUnavailable, "source hash missing or invalid"):
            invalid_hash.exception_summary()
        offline = ledger_db.HistoryDB(psql="missing-psql-binary-for-t08", cutover={
            "capture_id": CAPTURE, "as_of": AS_OF,
            "source_workbook_sha256": WORKBOOK_SHA, "engine_sha256": ENGINE_SHA,
        })
        with self.assertRaisesRegex(ledger_db.LedgerUnavailable, "PostgreSQL unavailable"):
            offline.exception_summary()
        disconnected = ledger_db.HistoryDB(dbname="webdebit_missing_db", cutover={
            "capture_id": CAPTURE, "as_of": AS_OF,
            "source_workbook_sha256": WORKBOOK_SHA, "engine_sha256": ENGINE_SHA,
        })
        with self.assertRaisesRegex(ledger_db.LedgerUnavailable, "PostgreSQL unavailable"):
            disconnected.exception_summary()

    def test_09_missing_permission_is_an_explicit_internal_error(self) -> None:
        global CURRENT_DB_USER
        CURRENT_DB_USER = "m1_reader"
        try:
            with self.assertRaisesRegex(ledger_db.LedgerUnavailable, "permission denied"):
                self.db.exception_summary()
        finally:
            CURRENT_DB_USER = "postgres"

    def test_10_missing_provenance_and_reconciliation_permissions_fail_closed(self) -> None:
        global CURRENT_DB_USER
        CURRENT_DB_USER = "m1_no_provenance"
        try:
            with self.assertRaisesRegex(ledger_db.LedgerUnavailable, "permission denied"):
                self.db.exception_summary()
        finally:
            CURRENT_DB_USER = "postgres"
        CURRENT_DB_USER = "m1_no_reconciliation"
        try:
            with self.assertRaisesRegex(ledger_db.LedgerUnavailable, "permission denied"):
                self.db.customer_reconciliations()
        finally:
            CURRENT_DB_USER = "postgres"

    def test_11_missing_database_hash_fails_closed(self) -> None:
        missing_hash = """CREATE OR REPLACE VIEW pilot.m1_provenance AS
            SELECT capture_id, as_of, source_spreadsheet_id, source_title,
                   NULL::text AS source_workbook_sha256, captured_at_utc, engine_sha256, baseline_date
            FROM (SELECT c.capture_id, r.as_of, c.source_spreadsheet_id, c.source_title,
                         c.source_workbook_sha256, c.captured_at_utc, r.engine_sha256,
                         (SELECT left(x.record -> 'values' ->> 1, 10)
                          FROM pilot.raw_row x WHERE x.capture_id=c.capture_id
                            AND x.tab_title='17 Đối soát theo khách' AND x.source_row=4) AS baseline_date
                  FROM pilot.capture c JOIN pilot.replay_run r USING (capture_id)) p"""
        docker_psql(missing_hash, timeout=15)
        with self.assertRaisesRegex(ledger_db.LedgerUnavailable, "source hash missing or invalid"):
            self.db.exception_summary()
        docker_psql(M1_SCHEMA.read_text(encoding="utf-8"), timeout=15)
        malformed_hash = missing_hash.replace("NULL::text AS source_workbook_sha256",
                                             "'bad-hash'::text AS source_workbook_sha256")
        docker_psql(malformed_hash, timeout=15)
        with self.assertRaisesRegex(ledger_db.LedgerUnavailable, "source hash missing or invalid"):
            self.db.exception_summary()
        docker_psql(M1_SCHEMA.read_text(encoding="utf-8"), timeout=15)
        missing_engine = missing_hash.replace("NULL::text AS source_workbook_sha256, captured_at_utc, engine_sha256",
                                              "source_workbook_sha256, captured_at_utc, NULL::text AS engine_sha256")
        docker_psql(missing_engine, timeout=15)
        with self.assertRaisesRegex(ledger_db.LedgerUnavailable, "source hash missing or invalid"):
            self.db.exception_summary()
        docker_psql(M1_SCHEMA.read_text(encoding="utf-8"), timeout=15)

    def test_99_duplicate_provenance_fails_closed(self) -> None:
        duplicate_view = f"""CREATE OR REPLACE VIEW pilot.m1_provenance AS
            SELECT c.capture_id, r.as_of, c.source_spreadsheet_id, c.source_title,
                   c.source_workbook_sha256, c.captured_at_utc, r.engine_sha256,
                   (SELECT left(x.record -> 'values' ->> 1, 10)
                    FROM pilot.raw_row x WHERE x.capture_id=c.capture_id
                      AND x.tab_title='17 Đối soát theo khách' AND x.source_row=4) AS baseline_date
            FROM pilot.capture c JOIN pilot.replay_run r USING (capture_id)
            CROSS JOIN (VALUES (1),(2)) AS duplicate(copy_no)
        """
        docker_psql(duplicate_view, timeout=15)
        with self.assertRaisesRegex(ledger_db.LedgerUnavailable, "provenance duplicate"):
            self.db.exception_summary()


CURRENT_DB_USER = "postgres"
DOCKER: list[str] = ["docker"]
CONTAINER_ID = ""
PG_ENV: dict[str, str] = {}
ORIGINAL_SUBPROCESS_RUN = subprocess.run


def docker_psql(sql: str, *, database: str = DATABASE, user: str = "postgres",
                check: bool = True, timeout: float = 30) -> subprocess.CompletedProcess[str]:
    command = DOCKER + ["exec", "-i", *lifecycle.env_args(PG_ENV), CONTAINER_ID,
                        "psql", "-X", "-w", "-q", "-A", "-t", "-v", "ON_ERROR_STOP=1",
                        "-U", user, "-d", database]
    return lifecycle.run(command, input_text=sql, check=check, timeout=timeout)


def docker_transport(command: list[str], **kwargs) -> subprocess.CompletedProcess[str]:
    if not command or Path(command[0]).name.lower() not in {"psql", "psql.exe"}:
        return ORIGINAL_SUBPROCESS_RUN(command, **kwargs)
    docker_command = DOCKER + ["exec", "-i", *lifecycle.env_args(PG_ENV), CONTAINER_ID,
                               "psql", "-U", CURRENT_DB_USER, *command[1:]]
    return ORIGINAL_SUBPROCESS_RUN(docker_command, **kwargs)


def source_hash(path: Path) -> str:
    normalized = path.read_bytes().replace(b"\r\n", b"\n")
    return hashlib.sha256(normalized).hexdigest()


def initialize_fixture() -> None:
    docker_psql("CREATE DATABASE webdebit_pilot_system;", database="postgres")
    docker_psql(PILOT_SCHEMA.read_text(encoding="utf-8") + "\n" +
                M1_SCHEMA.read_text(encoding="utf-8"))
    workbook_other = "c" * 64
    engine_other = "d" * 64
    statements = f"""
    INSERT INTO pilot.capture VALUES
      ('{CAPTURE}','fake-spreadsheet','Fake source',TIMESTAMPTZ '2026-10-13 00:00:00+00',
       '{WORKBOOK_SHA}', '{{}}'::jsonb),
      ('{OTHER_CAPTURE}','fake-other','Fake other',TIMESTAMPTZ '2026-10-14 00:00:00+00',
       '{workbook_other}', '{{}}'::jsonb);
    INSERT INTO pilot.replay_run VALUES
      ('{CAPTURE}', DATE '{AS_OF}', '{ENGINE_SHA}', '{{}}'::jsonb),
      ('{CAPTURE}', DATE '{OTHER_AS_OF}', '{ENGINE_SHA}', '{{}}'::jsonb),
      ('{OTHER_CAPTURE}', DATE '{AS_OF}', '{engine_other}', '{{}}'::jsonb);
    INSERT INTO pilot.raw_row (capture_id,sheet_gid,source_row,tab_title,record,row_sha256)
    SELECT v.capture_id,v.sheet_gid,v.source_row,v.tab_title,
        jsonb_build_object('capture_id',v.capture_id,'sheet_gid',v.sheet_gid,
            'source_row',v.source_row,'values',v.row_values), repeat('e',64)
    FROM (VALUES
      ('{CAPTURE}',10,7,'Chuyến hàng','[]'::jsonb),
      ('{CAPTURE}',10,8,'Chuyến hàng','[]'::jsonb),
      ('{CAPTURE}',20,7,'Thu & cấn trừ','[]'::jsonb),
      ('{CAPTURE}',20,8,'Khách hàng','[]'::jsonb),
      ('{CAPTURE}',20,9,'Thu & cấn trừ','[]'::jsonb),
      ('{CAPTURE}',33,7,'Chuyến hàng','[]'::jsonb),
      ('{CAPTURE}',34,7,'Chuyến hàng','[]'::jsonb),
      ('{CAPTURE}',35,7,'Chuyến hàng','[]'::jsonb),
      ('{CAPTURE}',30,4,'17 Đối soát theo khách',jsonb_build_array('cutover','{AS_OF}')),
      ('{CAPTURE}',30,7,'17 Đối soát theo khách',jsonb_build_array('ACME','','','','','1200','','731')),
      ('{CAPTURE}',30,8,'17 Đối soát theo khách',jsonb_build_array('NO-DELTA','','','','','900','',null)),
      ('{OTHER_CAPTURE}',40,4,'17 Đối soát theo khách',jsonb_build_array('cutover','{AS_OF}')),
      ('{OTHER_CAPTURE}',40,7,'Chuyến hàng','[]'::jsonb)
    ) AS v(capture_id,sheet_gid,source_row,tab_title,row_values);
    INSERT INTO pilot.replay_event VALUES
      ('{CAPTURE}',DATE '{AS_OF}',1,'ACME','2026-10',DATE '2026-10-01','charge',1200,1200,10,7),
      ('{CAPTURE}',DATE '{AS_OF}',2,'NO-BASELINE','2026-10',DATE '2026-10-02','charge',50,50,10,8);
    INSERT INTO pilot.source_exception (capture_id,as_of,exception_no,sheet_gid,source_row,payload)
    VALUES
      ('{CAPTURE}',DATE '{AS_OF}',1,10,7,jsonb_build_object('code','A','status','open','customer','ACME','period','2026-10','detail','fake A1','sheet_gid',10,'source_row',7)),
      ('{CAPTURE}',DATE '{AS_OF}',2,10,7,jsonb_build_object('code','B','status','open','customer','ACME','period','2026-10','detail','fake B','sheet_gid',10,'source_row',7)),
      ('{CAPTURE}',DATE '{AS_OF}',3,10,7,jsonb_build_object('code','C','status','open','customer','ACME','period','2026-10','detail','fake C','sheet_gid',10,'source_row',7)),
      ('{CAPTURE}',DATE '{AS_OF}',4,10,8,jsonb_build_object('code','D','status','open','customer',null,'period','','detail','fake D','sheet_gid',10,'source_row',8)),
      ('{CAPTURE}',DATE '{AS_OF}',5,20,7,jsonb_build_object('code','A','status','open','customer','ACME','period','2026-10','detail','fake A4','sheet_gid',20,'source_row',7)),
      ('{CAPTURE}',DATE '{AS_OF}',6,20,7,jsonb_build_object('code','E','status','open','customer','','period',null,'detail','fake E','sheet_gid',20,'source_row',7)),
      ('{CAPTURE}',DATE '{AS_OF}',7,20,8,jsonb_build_object('status','open','detail','fake unclassified','sheet_gid',20,'source_row',8)),
      ('{CAPTURE}',DATE '{AS_OF}',8,33,7,jsonb_build_object('code','Q','status','open','customer','O''Brien','period','2026-10','detail','fake quoted customer','sheet_gid',33,'source_row',7)),
      ('{CAPTURE}',DATE '{AS_OF}',9,34,7,jsonb_build_object('code','W','status','open','customer',' ACME','period','2026-10','detail','fake leading whitespace','sheet_gid',34,'source_row',7)),
      ('{CAPTURE}',DATE '{AS_OF}',10,35,7,jsonb_build_object('code','W','status','open','customer','ACME ','period','2026-10','detail','fake trailing whitespace','sheet_gid',35,'source_row',7)),
      ('{CAPTURE}',DATE '{AS_OF}',11,20,9,jsonb_build_object('code',chr(11),'status','open','customer',chr(9),'period',chr(10),'detail','fake ASCII whitespace','sheet_gid',20,'source_row',9)),
      ('{CAPTURE}',DATE '{AS_OF}',12,20,9,jsonb_build_object('code',' X','status','open','customer','ACME','period',' 2026-10','detail','fake leading values','sheet_gid',20,'source_row',9)),
      ('{CAPTURE}',DATE '{AS_OF}',13,20,9,jsonb_build_object('code','X ','status','open','customer','ACME','period','2026-10 ','detail','fake trailing values','sheet_gid',20,'source_row',9)),
      ('{CAPTURE}',DATE '{OTHER_AS_OF}',101,10,7,jsonb_build_object('code','NEXT','customer','ACME','period','2026-10','sheet_gid',10,'source_row',7)),
      ('{OTHER_CAPTURE}',DATE '{AS_OF}',201,40,7,jsonb_build_object('code','OTHER','customer','OTHER','period','2026-10','sheet_gid',40,'source_row',7));
    CREATE ROLE m1_reader LOGIN;
    CREATE ROLE m1_no_provenance LOGIN;
    CREATE ROLE m1_no_reconciliation LOGIN;
    GRANT USAGE ON SCHEMA pilot TO m1_reader;
    GRANT SELECT ON pilot.m1_provenance TO m1_reader;
    GRANT USAGE ON SCHEMA pilot TO m1_no_provenance,m1_no_reconciliation;
    GRANT SELECT ON pilot.m1_provenance TO m1_no_reconciliation;
    """
    docker_psql(statements)


def main() -> int:
    global CONTAINER_ID, PG_ENV
    if shutil.which("docker") is None:
        raise M1QueryRunnerError("docker CLI not found")
    run_id = uuid.uuid4().hex
    container = f"webdebit-pg-ledger-{run_id}"
    marker = f"codex_run_id={run_id}"
    report_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("pg-m1-history-queries.json")
    expected_head = os.environ.get("EXPECTED_HEAD_SHA")
    if not expected_head:
        expected_head = lifecycle.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"]).stdout.strip()
    revision = lifecycle.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"]).stdout.strip()
    tree = lifecycle.run(["git", "-C", str(ROOT), "rev-parse", "HEAD^{tree}"]).stdout.strip()
    head_tree = lifecycle.run(["git", "-C", str(ROOT), "rev-parse", f"{expected_head}^{{tree}}"]).stdout.strip()
    report: dict[str, object] = {
        "database": DATABASE,
        "image": lifecycle.IMAGE,
        "query_result_mocked": False,
        "transport": "HistoryDB subprocess psql over docker exec",
        "run_id": run_id,
        "head_sha": expected_head,
        "tested_revision": revision,
        "revision_matches_head": revision == expected_head,
        "head_tree": head_tree,
        "tested_tree": tree,
        "tree_matches_head": tree == head_tree,
        "source_hashes_sha256_lf": {
            str(path.resolve().relative_to(ROOT)).replace("\\", "/"): source_hash(path)
            for path in (Path(__file__).resolve(), Path(ledger_db.__file__).resolve(), PILOT_SCHEMA,
                         M1_SCHEMA, TOOLS / "test_pg_ledger_schema.py",
                         ROOT / ".github" / "workflows" / "test.yml")
        },
        "cases": [],
        "cleanup": "not_started",
    }
    container_attempted = False
    expected_container_id: str | None = None
    try:
        if revision != expected_head or tree != head_tree:
            raise M1QueryRunnerError("tested revision/tree differs from requested final head")
        container_attempted = True
        lifecycle.run(DOCKER + ["run", "--detach", "--name", container,
                                "--label", f"{lifecycle.LABEL_TEST}={lifecycle.LABEL_VALUE}",
                                "--label", f"{lifecycle.LABEL_RUN}={run_id}",
                                "--network", "none", "--tmpfs", "/var/lib/postgresql:rw,exec,nosuid,size=512m",
                                "--env", "POSTGRES_HOST_AUTH_METHOD=trust", lifecycle.IMAGE], timeout=240)
        inspect = json.loads(lifecycle.run(DOCKER + ["inspect", container]).stdout)[0]
        expected_container_id = inspect.get("Id")
        CONTAINER_ID = expected_container_id or ""
        report["container_id"] = CONTAINER_ID
        labels = inspect.get("Config", {}).get("Labels") or {}
        host_config = inspect.get("HostConfig", {})
        mounts = inspect.get("Mounts", [])
        network_mode = host_config.get("NetworkMode")
        port_bindings = host_config.get("PortBindings") or {}
        tmpfs = host_config.get("Tmpfs") or {}
        report["network_mode"] = network_mode
        report["port_bindings"] = port_bindings
        report["mounts"] = mounts
        report["tmpfs"] = tmpfs
        if (len(CONTAINER_ID) != 64 or inspect.get("Name", "").lstrip("/") != container
                or labels.get(lifecycle.LABEL_TEST) != lifecycle.LABEL_VALUE
                or labels.get(lifecycle.LABEL_RUN) != run_id
                or network_mode != "none" or port_bindings
                or mounts
                or tmpfs != {"/var/lib/postgresql": "rw,exec,nosuid,size=512m"}):
            raise M1QueryRunnerError("container identity, labels, network, ports, or tmpfs did not match this run")
        deadline = time.monotonic() + 90
        pg_probe = ["exec", "--env", f"PGAPPNAME={marker}", "--env",
                    "PGOPTIONS=-c statement_timeout=20000 -c lock_timeout=12000", container]
        while time.monotonic() < deadline:
            ready = lifecycle.run(DOCKER + pg_probe + ["pg_isready", "-U", "postgres", "-d", "postgres"],
                                  check=False, timeout=10)
            logs = lifecycle.run(DOCKER + ["logs", container], check=False, timeout=10)
            if ready.returncode == 0 and "PostgreSQL init process complete; ready for start up." in logs.stdout + logs.stderr:
                break
            time.sleep(0.25)
        else:
            raise M1QueryRunnerError("PostgreSQL initialization completion marker timed out")
        PG_ENV = {"PGAPPNAME": marker, "PGOPTIONS": "-c statement_timeout=20000 -c lock_timeout=12000"}
        initialize_fixture()
        with patch.object(ledger_db.subprocess, "run", side_effect=docker_transport):
            suite = unittest.defaultTestLoader.loadTestsFromTestCase(M1HistoryDBTests)
            test_ids = [test.id() for test in suite]
            result = unittest.TextTestRunner(stream=sys.stdout, verbosity=2).run(suite)
        failed_names = {test.id() for test, _ in [*result.failures, *result.errors]}
        report["cases"] = [
            {"name": test_id, "status": "failed" if test_id in failed_names else "passed"}
            for test_id in test_ids
        ]
        report["case_count"] = result.testsRun
        report["passed"] = result.testsRun - len(result.failures) - len(result.errors)
        report["failed"] = len(result.failures) + len(result.errors)
        if not result.wasSuccessful():
            raise M1QueryRunnerError("one or more PostgreSQL M1 HistoryDB tests failed")
        report["exit_code"] = 0
    except BaseException as exc:
        report["error"] = f"{type(exc).__name__}: {exc}"
        report["exit_code"] = 1
    finally:
        try:
            if container_attempted:
                owned_id = expected_container_id or lifecycle.owned_container_id(DOCKER, container, run_id)
                if owned_id:
                    removed = lifecycle.cleanup_owned_container(DOCKER, container, run_id, owned_id)
                    if not removed:
                        raise M1QueryRunnerError("owned container disappeared before verified cleanup")
                    report["cleanup"] = "verified_and_removed"
                else:
                    report["cleanup"] = "nothing_created"
            else:
                report["cleanup"] = "nothing_created"
        except BaseException as cleanup_error:
            report["cleanup"] = f"failed: {type(cleanup_error).__name__}: {cleanup_error}"
            report["exit_code"] = 1
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return int(report.get("exit_code", 1))


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except M1QueryRunnerError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
