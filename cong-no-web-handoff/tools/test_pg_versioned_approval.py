#!/usr/bin/env python3
"""PostgreSQL 18 acceptance fixture: charge-only versioned approval (schema v3).

Fake data only, isolated container, no network. Not evidence about hao, the Sheet or real data.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from test_pg_ledger_schema import (
    IMAGE,
    LABEL_RUN,
    LABEL_TEST,
    LABEL_VALUE,
    HarnessError,
    PsqlSession,
    cleanup_owned_container,
    run,
)


ROOT = Path(__file__).resolve().parents[2]
SCHEMA = ROOT / "cong-no-web-handoff" / "tools" / "pg_versioned_approval_fixture.sql"
DATABASE = "webdebit_ledger"
API_LOGIN = "webdebit_app"
NO_GRANT_LOGIN = "webdebit_no_grant"
NOT_MEMBER_LOGIN = "webdebit_not_member"
MAKER = uuid.UUID("11111111-1111-4111-8111-111111111111")       # maker + checker
CHECKER = uuid.UUID("22222222-2222-4222-8222-222222222222")     # checker only
DISABLED = uuid.UUID("33333333-3333-4333-8333-333333333333")    # inactive maker
MAKER_ONLY = uuid.UUID("44444444-4444-4444-8444-444444444444")  # maker only
DUAL2 = uuid.UUID("55555555-5555-4555-8555-555555555555")       # maker + checker
UNKNOWN = uuid.UUID("99999999-9999-4999-8999-999999999999")
ABSENT = "ABSENT_FROM_OPENING_APPROVED"

M_STALE = "stale, unavailable, or self-approved revision"
M_POST = "current approved revision required for posting"
M_RES_APPROVAL = "opening resolution is not ABSENT_FROM_OPENING_APPROVED at approval"
M_RES_POST = "opening resolution is not ABSENT_FROM_OPENING_APPROVED at posting"
M_PRICE_BLOCK = "price confirmation requires complete positive matching price"


def sql_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def dumps(payload: object) -> str:
    return json.dumps(payload, ensure_ascii=True, separators=(",", ":"))


AUTO = object()


def trip_key(booking: str | None, container: str | None) -> str:
    """Mirror of p0_fixture.compute_trip_key; '' stands for NULL (booking or container blank)."""
    b = re.sub(r"\s", "", booking or "").upper()
    c = re.sub(r"\s", "", container or "").upper()
    return b + c if b and c else ""


def charge_payload(booking: str | None, container: str | None, *, customer: str, amount: int = 100,
                   period: str = "2026-10", warehouse: str = "2026-10-14",
                   drop: tuple[str, ...] = (), **overrides: object) -> dict[str, object]:
    first = amount // 2
    payload: dict[str, object] = {
        "schema_version": 3,
        "customer_id": customer,
        "debt_period": period,
        "total_vnd": amount,
        "warehouse_in_date": warehouse,
        "posting_date": "2026-10-15",
        "source_ref": "fixture-source-reference-only",
        "evidence_ref": "fixture-evidence-reference-only",
        "evidence_sha256": "a" * 64,
        "reason": "fixture reason only",
        "lines": [{"line_no": 1, "customer_id": customer, "debt_period": period,
                   "amount_vnd": amount}],
        "booking_no": booking,
        "container_no": container,
        "price_components": [{"label": "A", "amount_vnd": first},
                             {"label": "B", "amount_vnd": amount - first}],
        "period_override_reason": None,
        "period_override_evidence_ref": None,
        "period_override_evidence_sha256": None,
    }
    payload.update(overrides)
    for key in drop:
        payload.pop(key, None)
    return payload


OVERRIDE = {
    "period_override_reason": "fixture cross-month reason",
    "period_override_evidence_ref": "fixture cross-month evidence",
    "period_override_evidence_sha256": "b" * 64,
}


def submit_sql(proposal_id: int | None, payload_text: str, actor: uuid.UUID = MAKER,
               session: uuid.UUID | None = None) -> str:
    return ("SELECT row_to_json(x)::text FROM p0_fixture.submit_revision("
            f"{'NULL' if proposal_id is None else proposal_id}::bigint,"
            f"{sql_literal(payload_text)}::text,'{actor}'::uuid,'{session or uuid.uuid4()}'::uuid) x")


def decision_sql(function: str, proposal_id: int, revision_id: int, content_hash: str,
                 actor: uuid.UUID, session: uuid.UUID | None = None) -> str:
    return (f"SELECT p0_fixture.{function}({proposal_id}, {revision_id}, "
            f"{sql_literal(content_hash)}, '{actor}'::uuid, '{session or uuid.uuid4()}'::uuid)")


class Fixture:
    def __init__(self, docker: list[str], container: str):
        self.docker = docker
        self.container = container

    def psql(self, sql: str, *, user: str = "postgres", check: bool = True,
             database: str = DATABASE, appname: str | None = None,
             pg_options: str | None = None, timeout: float = 30) -> subprocess.CompletedProcess[str]:
        command = self.docker + ["exec"]
        if appname is not None:
            command += ["--env", f"PGAPPNAME={appname}"]
        if pg_options is not None:
            command += ["--env", f"PGOPTIONS={pg_options}"]
        return run(command + [self.container, "psql", "-X", "-qAt",
            "-v", "ON_ERROR_STOP=1", "-v", "VERBOSITY=verbose", "-U", user,
            "-d", database, "-c", sql], check=check, timeout=timeout)


@dataclass
class Charge:
    proposal_id: int
    revision_id: int
    content_hash: str
    key: str
    customer: str
    amount: int
    period: str
    maker: uuid.UUID
    payload: dict[str, object] = field(default_factory=dict)


class Suite:
    def __init__(self, docker: list[str], container: str, run_id: str, report: dict[str, object]):
        self.docker = docker
        self.container = container
        self.run_id = run_id
        self.report = report
        self.f = Fixture(docker, container)
        self.trip_counter = 0
        self.group_name = "setup"

    # ---- recording -------------------------------------------------------------------------
    def case(self, name: str, expected: object, actual: object) -> bool:
        passed = expected == actual
        self.report["cases"].append({  # type: ignore[union-attr]
            "group": self.group_name, "name": name, "expected": expected, "actual": actual,
            "result": "pass" if passed else "fail"})
        if not passed:
            self.report["failed_cases"].append(f"{self.group_name}/{name}")  # type: ignore[union-attr]
        return passed

    def rejected(self, name: str, result: subprocess.CompletedProcess[str], expected_text: str) -> bool:
        combined = result.stdout + result.stderr
        ok = result.returncode != 0 and expected_text in combined
        return self.case(name, True, ok if ok else {"returncode": result.returncode,
                                                      "output": combined[-400:]})

    def run_group(self, name: str, function) -> None:
        self.group_name = name
        started = len(self.report["cases"])  # type: ignore[arg-type]
        try:
            function()
        except BaseException as exc:  # keep running the other groups; report decides exit code
            self.report["group_errors"].append(f"{name}: {type(exc).__name__}: {exc}"[:1500])  # type: ignore[union-attr]
        finished = self.report["cases"][started:]  # type: ignore[index]
        self.report["groups"][name] = {  # type: ignore[index]
            "cases": len(finished),
            "failed": sum(1 for item in finished if item["result"] == "fail")}

    # ---- queries ---------------------------------------------------------------------------
    def query(self, sql: str, *, appname: str | None = None, pg_options: str | None = None,
              timeout: float = 30) -> str:
        return self.f.psql(sql, appname=appname, pg_options=pg_options, timeout=timeout).stdout.strip()

    def balance(self, customer: str, period: str | None = None) -> int:
        where = f"customer_id={sql_literal(customer)}"
        if period is not None:
            where += f" AND debt_period={sql_literal(period)}"
        return int(self.query("SELECT coalesce(sum(posted_balance_vnd), 0)::bigint::text "
                              f"FROM p0_fixture.posted_balance WHERE {where}"))

    def balance_rows(self, customer: str, period: str) -> list[object]:
        return json.loads(self.query(
            "SELECT coalesce(jsonb_agg(jsonb_build_object('customer_id', customer_id, "
            "'debt_period', debt_period, 'posted_balance_vnd', posted_balance_vnd) "
            "ORDER BY customer_id, debt_period), '[]'::jsonb)::text FROM p0_fixture.posted_balance "
            f"WHERE customer_id={sql_literal(customer)} AND debt_period={sql_literal(period)}"))

    def snapshot(self, proposal_id: int) -> dict[str, object]:
        return json.loads(self.query(
            "SELECT jsonb_build_object('state', p.state, 'revision_no', p.revision_no, "
            "'current_revision_id', p.current_revision_id, 'content_sha256', r.content_sha256, "
            "'revision_count', (SELECT count(*) FROM p0_fixture.business_revision x "
            "WHERE x.proposal_id=p.proposal_id), "
            "'approval_history', (SELECT coalesce(jsonb_agg(jsonb_build_array(a.approval_id, "
            "a.revision_id, a.content_sha256) ORDER BY a.approval_id), '[]'::jsonb) "
            "FROM p0_fixture.approval a WHERE a.proposal_id=p.proposal_id), "
            "'posting_count', (SELECT count(*) FROM p0_fixture.posting x WHERE x.proposal_id=p.proposal_id), "
            "'period_confirmation_history', (SELECT coalesce(jsonb_agg(jsonb_build_array("
            "x.confirmation_id, x.revision_id, x.content_sha256) ORDER BY x.revision_id), '[]'::jsonb) "
            "FROM p0_fixture.period_confirmation x WHERE x.proposal_id=p.proposal_id), "
            "'price_confirmation_history', (SELECT coalesce(jsonb_agg(jsonb_build_array("
            "x.confirmation_id, x.revision_id, x.content_sha256) ORDER BY x.revision_id), '[]'::jsonb) "
            "FROM p0_fixture.price_confirmation x WHERE x.proposal_id=p.proposal_id), "
            "'audit_count', (SELECT count(*) FROM p0_fixture.audit x WHERE x.proposal_id=p.proposal_id))::text "
            "FROM p0_fixture.proposal p JOIN p0_fixture.business_revision r "
            f"ON r.revision_id=p.current_revision_id WHERE p.proposal_id={proposal_id}"))

    def projection(self, proposal_id: int) -> dict[str, object]:
        return json.loads(self.query(
            f"SELECT p0_fixture.fixture_review_projection({proposal_id})::text"))

    def current_view(self, charge_or_id: Charge | int) -> dict[str, object]:
        proposal_id = charge_or_id.proposal_id if isinstance(charge_or_id, Charge) else charge_or_id
        return self.projection(proposal_id)["revisions"][-1]  # type: ignore[index]

    def count(self, table: str, where: str = "true") -> int:
        return int(self.query(f"SELECT count(*) FROM p0_fixture.{table} WHERE {where}"))

    def audit_actions(self, proposal_id: int) -> list[str]:
        raw = self.query("SELECT coalesce(string_agg(action, ',' ORDER BY audit_id), '') "
                         f"FROM p0_fixture.audit WHERE proposal_id={proposal_id}")
        return raw.split(",") if raw else []

    # ---- scenario building blocks ----------------------------------------------------------
    def seed(self, key: str, status: str = ABSENT) -> None:
        self.f.psql("INSERT INTO p0_fixture.trip_opening_resolution"
                    "(trip_key, status, evidence_ref, approved_by) VALUES "
                    f"({sql_literal(key)}, {sql_literal(status)}, 'fixture-evidence-only', 'fixture-owner') "
                    "ON CONFLICT (trip_key) DO UPDATE SET status = EXCLUDED.status")

    def set_resolution(self, key: str, status: str) -> None:
        self.f.psql(f"UPDATE p0_fixture.trip_opening_resolution SET status={sql_literal(status)} "
                    f"WHERE trip_key={sql_literal(key)}")

    def set_period(self, period: str, state: str) -> None:
        self.f.psql(f"UPDATE p0_fixture.debt_period_state SET state={sql_literal(state)} "
                    f"WHERE debt_period={sql_literal(period)}")

    def next_trip(self) -> tuple[str, str]:
        self.trip_counter += 1
        return f"BK{self.trip_counter:04d}", f"CT{self.trip_counter:04d}"

    def submit_raw(self, payload_text: str, *, proposal_id: int | None = None,
                   actor: uuid.UUID = MAKER, check: bool = True,
                   session: uuid.UUID | None = None) -> subprocess.CompletedProcess[str]:
        return self.f.psql(submit_sql(proposal_id, payload_text, actor, session),
                           user=API_LOGIN, check=check)

    def call(self, function: str, ids: tuple[int, int, str], actor: uuid.UUID, *,
             check: bool = False, user: str = API_LOGIN) -> subprocess.CompletedProcess[str]:
        return self.f.psql(decision_sql(function, ids[0], ids[1], ids[2], actor),
                           user=user, check=check)

    def charge(self, *, customer: str, amount: int = 100, period: str = "2026-10",
               warehouse: str = "2026-10-14", seed: str | None = ABSENT,
               maker: uuid.UUID = MAKER, booking: object = AUTO, container: object = AUTO,
               drop: tuple[str, ...] = (), **overrides: object) -> Charge:
        if booking is AUTO and container is AUTO:
            booking, container = self.next_trip()
        payload = charge_payload(booking, container, customer=customer, amount=amount,  # type: ignore[arg-type]
                                 period=period, warehouse=warehouse, drop=drop, **overrides)
        created = json.loads(self.submit_raw(dumps(payload), actor=maker).stdout.strip())
        key = trip_key(booking, container)  # type: ignore[arg-type]
        if seed is not None and key:
            self.seed(key, seed)
        return Charge(int(created["proposal_id"]), int(created["revision_id"]),
                      str(created["content_sha256"]), key, customer, amount, period, maker, payload)

    def ids(self, c: Charge) -> tuple[int, int, str]:
        return c.proposal_id, c.revision_id, c.content_hash

    def confirm_both(self, c: Charge, *, price_actor: uuid.UUID = MAKER) -> None:
        self.call("confirm_period_revision", self.ids(c), c.maker, check=True)
        self.call("confirm_price_revision", self.ids(c), price_actor, check=True)

    def approve(self, c: Charge, actor: uuid.UUID = CHECKER, *, check: bool = False):
        return self.call("approve_revision", self.ids(c), actor, check=check)

    def post(self, c: Charge, actor: uuid.UUID = CHECKER, *, check: bool = False):
        return self.call("post_revision", self.ids(c), actor, check=check)

    def ready(self, c: Charge) -> Charge:
        self.confirm_both(c)
        return c

    def run_to_posted(self, c: Charge) -> None:
        self.confirm_both(c)
        self.approve(c, check=True)
        self.post(c, check=True)

    # ---- contention ------------------------------------------------------------------------
    def run_contention(self, name: str, proposal_id: int, customer: str, debt_period: str,
                       holder_user: str, holder_sql: str, waiter_user: str, waiter_sql: str,
                       waiter_error: str | None = None) -> dict[str, object]:
        short_name = name.replace("-", "")
        holder_app = f"m2:{self.run_id}:{short_name}:h"
        waiter_app = f"m2:{self.run_id}:{short_name}:w"
        observer_app = f"m2:{self.run_id}:{short_name}:o"
        if any(len(value.encode("utf-8")) > 63 for value in (holder_app, waiter_app, observer_app)):
            raise HarnessError("contention PGAPPNAME exceeds PostgreSQL limit")

        before = self.snapshot(proposal_id)
        balance_before = self.balance_rows(customer, debt_period)
        evidence: dict[str, object] = {
            "scenario": name, "holder_appname": holder_app, "waiter_appname": waiter_app,
            "observer_appname": observer_app, "holder_user": holder_user, "waiter_user": waiter_user,
            "proposal_id": proposal_id, "before": before, "balance_before": balance_before,
            "waiter_expected_error": waiter_error,
        }
        self.report["concurrency_evidence"].append(evidence)  # type: ignore[union-attr]

        pg_options = "-c statement_timeout=20000 -c lock_timeout=12000"
        holder = PsqlSession(self.docker, {"PGAPPNAME": holder_app, "PGOPTIONS": pg_options},
                             container=self.container, user=holder_user, database=DATABASE)
        waiter: subprocess.Popen[str] | None = None
        failure: BaseException | None = None
        try:
            holder.send("BEGIN")
            holder_action_lines = holder.execute(holder_sql, f"__HOLDER_ACTION_{uuid.uuid4().hex}__", timeout=10)
            holder_info_lines = holder.execute(
                "SELECT pg_backend_pid()::text || '|' || session_user || '|' "
                "|| current_setting('application_name')",
                f"__HOLDER_INFO_{uuid.uuid4().hex}__", timeout=10)
            holder_info = next((line for line in reversed(holder_info_lines) if line), "")
            holder_parts = holder_info.split("|")
            if len(holder_parts) != 3:
                raise HarnessError(f"cannot identify contention holder session: {holder_info!r}")
            holder_pid = int(holder_parts[0])
            evidence["holder_pid"] = holder_pid
            evidence["holder_session_user"] = holder_parts[1]
            evidence["holder_action_output"] = holder_action_lines
            self.case(f"{name}_holder_identity", (holder_user, holder_app),
                      (holder_parts[1], holder_parts[2]))

            waiter = subprocess.Popen(
                self.docker + ["exec", "--env", f"PGAPPNAME={waiter_app}",
                    "--env", f"PGOPTIONS={pg_options}", self.container,
                    "psql", "-X", "-qAt", "-v", "ON_ERROR_STOP=1",
                    "-v", "VERBOSITY=verbose", "-U", waiter_user,
                    "-d", DATABASE, "-c", waiter_sql],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8")

            deadline = time.monotonic() + 8
            observation: dict[str, object] | None = None
            last_activity = ""
            while time.monotonic() < deadline:
                if waiter.poll() is not None:
                    stdout, stderr = waiter.communicate()
                    raise HarnessError(f"{name} waiter exited before observed lock: "
                                       f"{waiter.returncode}; {stdout}{stderr}")
                activity = self.query(
                    "SELECT pid::text || '|' || usename || '|' || coalesce(state, '') || '|' "
                    "|| coalesce(wait_event_type, '') || '|' || coalesce(wait_event, '') || '|' "
                    "|| array_to_string(pg_blocking_pids(pid), ',') "
                    "FROM pg_stat_activity "
                    f"WHERE application_name={sql_literal(waiter_app)} AND datname=current_database()",
                    appname=observer_app, pg_options="-c statement_timeout=5000", timeout=8)
                if activity:
                    last_activity = activity
                    fields = activity.split("|")
                    if len(fields) == 6:
                        blockers = [int(value) for value in fields[5].split(",") if value]
                        current = {
                            "waiter_pid": int(fields[0]), "waiter_session_user": fields[1],
                            "waiter_state": fields[2], "wait_event_type": fields[3],
                            "wait_event": fields[4], "pg_blocking_pids": blockers,
                        }
                        if (current["waiter_state"] == "active"
                                and current["wait_event_type"] == "Lock"
                                and holder_pid in blockers):
                            observation = current
                            break
                time.sleep(0.05)
            if observation is None:
                raise HarnessError(f"{name} waiter never showed holder in pg_blocking_pids; "
                                   f"last activity={last_activity!r}")

            evidence.update(observation)
            self.case(f"{name}_waiter_blocked_by_holder",
                      (waiter_user, "Lock", True),
                      (observation["waiter_session_user"], observation["wait_event_type"],
                       holder_pid in observation["pg_blocking_pids"]))  # type: ignore[operator]

            holder.close("COMMIT")
            try:
                waiter_stdout, waiter_stderr = waiter.communicate(timeout=25)
            except subprocess.TimeoutExpired:
                waiter.kill()
                waiter_stdout, waiter_stderr = waiter.communicate(timeout=5)
                raise HarnessError(f"{name} waiter exceeded bounded process timeout")
            waiter_output = waiter_stdout + waiter_stderr
            waiter_ok = ((waiter.returncode != 0 and waiter_error in waiter_output)
                         if waiter_error is not None else waiter.returncode == 0)
            evidence["waiter_returncode"] = waiter.returncode
            evidence["waiter_output"] = waiter_output[-3000:]
            self.case(f"{name}_waiter_outcome", True, waiter_ok)

            after = self.snapshot(proposal_id)
            balance_after = self.balance_rows(customer, debt_period)
            evidence["after"] = after
            evidence["balance_after"] = balance_after
            evidence["balance_unchanged"] = balance_before == balance_after
            self.case(f"{name}_leaves_posted_balance_unchanged", balance_before, balance_after)
            return evidence
        except BaseException as exc:
            failure = exc
            raise
        finally:
            cleanup_errors: list[str] = []
            try:
                if holder.proc.poll() is None:
                    holder.close()
            except BaseException as exc:
                cleanup_errors.append(f"holder: {type(exc).__name__}: {exc}")
            try:
                if waiter is not None and waiter.poll() is None:
                    waiter.terminate()
                if waiter is not None:
                    try:
                        waiter.communicate(timeout=5)
                    except subprocess.TimeoutExpired:
                        waiter.kill()
                        waiter.communicate(timeout=5)
            except BaseException as exc:
                cleanup_errors.append(f"waiter: {type(exc).__name__}: {exc}")
            evidence["holder_process_exited"] = holder.proc.poll() is not None
            evidence["waiter_process_exited"] = waiter is None or waiter.poll() is not None
            if cleanup_errors:
                evidence["cleanup_errors"] = cleanup_errors
                if failure is None:
                    raise HarnessError(f"{name} subprocess cleanup failed: {cleanup_errors}")

    # ======================================================================================
    # Groups
    # ======================================================================================
    def g_schema(self) -> None:
        q = self.query
        self.case("single_api_role_and_no_identity_test_role", "p0_fixture_api,p0_fixture_owner",
                  q("SELECT string_agg(rolname, ',' ORDER BY rolname) FROM pg_roles "
                    "WHERE rolname LIKE 'p0_fixture%'"))
        self.case("hmac_machinery_is_gone", "0|0",
                  q("SELECT (SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
                    "WHERE n.nspname='p0_fixture' AND c.relname IN ('actor_signing_key','used_assertion_nonce')) "
                    "|| '|' || (SELECT count(*) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace "
                    "WHERE n.nspname='p0_fixture' AND p.proname IN "
                    "('verify_actor_assertion','assert_fixture_kind_access'))"))
        self.case("audit_has_no_assertion_columns_but_keeps_actor_session_and_login", "0|3",
                  q("SELECT (SELECT count(*) FROM information_schema.columns WHERE table_schema='p0_fixture' "
                    "AND table_name='audit' AND column_name IN ('assertion_nonce','key_id','request_scope')) "
                    "|| '|' || (SELECT count(*) FROM information_schema.columns WHERE table_schema='p0_fixture' "
                    "AND table_name='audit' AND column_name IN ('app_actor_id','app_session_id','database_session_user'))"))
        self.case("opening_resolution_table_is_empty_by_default", 0, self.count("trip_opening_resolution"))
        self.case("period_seed_states", "closed|open|open|open", q(
            "SELECT string_agg(state, '|' ORDER BY debt_period) FROM p0_fixture.debt_period_state"))
        denied = {}
        for table in ("proposal", "business_revision", "posting", "audit", "trip_opening_resolution",
                      "app_actor", "posted_balance"):
            result = self.f.psql(f"SELECT count(*) FROM p0_fixture.{table}", user=API_LOGIN, check=False)
            denied[table] = result.returncode != 0 and "permission denied" in result.stderr
        self.case("api_login_cannot_read_any_fixture_table", {k: True for k in denied}, denied)
        direct = self.f.psql(
            f"INSERT INTO p0_fixture.proposal(maker_actor_id) VALUES ('{MAKER}'::uuid)",
            user=API_LOGIN, check=False)
        self.rejected("api_login_cannot_insert_proposal_directly", direct, "permission denied")
        resolution_write = self.f.psql(
            "INSERT INTO p0_fixture.trip_opening_resolution(trip_key, status, evidence_ref, approved_by) "
            "VALUES ('API1', 'ABSENT_FROM_OPENING_APPROVED', 'x', 'x')", user=API_LOGIN, check=False)
        self.rejected("api_login_cannot_write_opening_resolution", resolution_write, "permission denied")
        helper = self.f.psql(f"SELECT p0_fixture.require_actor('{MAKER}'::uuid, '{uuid.uuid4()}'::uuid, 'maker')",
                             user=API_LOGIN, check=False)
        self.rejected("api_login_cannot_call_require_actor_directly", helper, "permission denied")
        projection = self.f.psql("SELECT p0_fixture.fixture_review_projection(1)", user=API_LOGIN, check=False)
        self.rejected("api_login_cannot_call_review_projection", projection, "permission denied")
        no_grant = self.f.psql(submit_sql(None, "{}", MAKER), user=NO_GRANT_LOGIN, check=False)
        self.rejected("login_without_execute_grant_is_denied", no_grant, "permission denied")
        self.f.psql("GRANT USAGE ON SCHEMA p0_fixture TO webdebit_not_member; "
                    "GRANT EXECUTE ON FUNCTION p0_fixture.submit_revision(bigint,text,uuid,uuid) "
                    "TO webdebit_not_member")
        not_member = self.f.psql(submit_sql(None, "{}", MAKER), user=NOT_MEMBER_LOGIN, check=False)
        self.rejected("login_outside_api_role_is_untrusted_even_with_execute", not_member,
                      "untrusted database principal")
        bad_status = self.f.psql("INSERT INTO p0_fixture.trip_opening_resolution"
                                 "(trip_key, status, evidence_ref, approved_by) "
                                 "VALUES ('BADSTATUS1', 'MAYBE', 'x', 'x')", check=False)
        blank_evidence = self.f.psql("INSERT INTO p0_fixture.trip_opening_resolution"
                                     "(trip_key, status, evidence_ref, approved_by) "
                                     "VALUES ('BLANKEVID1', 'IN_OPENING', '  ', 'x')", check=False)
        lower_key = self.f.psql("INSERT INTO p0_fixture.trip_opening_resolution"
                                "(trip_key, status, evidence_ref, approved_by) "
                                "VALUES ('lower1', 'IN_OPENING', 'x', 'x')", check=False)
        self.case("resolution_table_rejects_bad_status_blank_evidence_and_unnormalized_key",
                  [True, True, True],
                  ["violates check constraint" in r.stderr and r.returncode != 0
                   for r in (bad_status, blank_evidence, lower_key)])

    def g_success(self) -> None:
        customer, period, amount = "FAKE-CUSTOMER-OK", "2026-10", 2500
        before = self.balance(customer)
        c = self.charge(customer=customer, amount=amount, booking=" bk 9001 ", container="ct\t9001")
        self.case("success_trip_key_is_stored_normalized", ("BK9001CT9001", "review_needed", 1),
                  (c.key, self.snapshot(c.proposal_id)["state"], self.snapshot(c.proposal_id)["revision_count"]))
        view = self.current_view(c)
        self.case("success_submit_time_reasons_and_blockers_before_confirmation",
                  ([], ["PERIOD_CONFIRMATION_MISSING", "PRICE_CONFIRMATION_MISSING"]),
                  (view["submit_time_reasons"], view["current_blockers"]))
        self.case("success_submit_does_not_change_balance", before, self.balance(customer))
        self.call("confirm_period_revision", self.ids(c), MAKER, check=True)
        self.call("confirm_price_revision", self.ids(c), MAKER, check=True)  # PRICE-MAKER: maker self-confirms
        self.case("success_no_blockers_after_both_confirmations", [], self.current_view(c)["current_blockers"])
        self.approve(c, check=True)
        self.case("success_approved_but_pending_stays_outside_balance", ("approved", before),
                  (self.snapshot(c.proposal_id)["state"], self.balance(customer)))
        self.post(c, check=True)
        after = self.balance(customer)
        self.case("success_path_posted_balance_increases_by_exact_amount", before + amount, after)
        self.case("success_balance_row_is_per_customer_and_period", [{
            "customer_id": customer, "debt_period": period, "posted_balance_vnd": amount}],
            [{**row, "posted_balance_vnd": int(row["posted_balance_vnd"])}  # type: ignore[call-overload]
             for row in self.balance_rows(customer, period)])
        posting = self.query(
            "SELECT state || '|' || (SELECT count(*) FROM p0_fixture.posting x WHERE x.proposal_id=p.proposal_id) "
            "|| '|' || (SELECT x.trip_key || '|' || x.database_session_user || '|' || x.maker_actor_id "
            f"|| '|' || x.checker_actor_id FROM p0_fixture.posting x WHERE x.proposal_id=p.proposal_id) "
            f"FROM p0_fixture.proposal p WHERE p.proposal_id={c.proposal_id}")
        self.case("success_posting_records_key_login_maker_and_checker",
                  f"posted|1|BK9001CT9001|{API_LOGIN}|{MAKER}|{CHECKER}", posting)
        self.case("success_audit_sequence",
                  ["submit", "confirm_period", "confirm_price", "approve", "post"],
                  self.audit_actions(c.proposal_id))
        self.rejected("success_second_post_is_refused", self.post(c), M_POST)
        edit = self.submit_raw(dumps({**c.payload, "reason": "after posted"}), proposal_id=c.proposal_id,
                               check=False)
        self.rejected("success_posted_proposal_cannot_be_edited", edit, "proposal unavailable to this maker")
        self.case("success_refusals_keep_balance", before + amount, self.balance(customer))

        second = self.charge(customer=customer, amount=700)
        self.run_to_posted(second)
        self.case("success_second_charge_adds_to_same_customer_period", before + amount + 700,
                  self.balance(customer, period))
        zero_component = self.charge(customer=customer, amount=300,
                                     price_components=[{"label": "A", "amount_vnd": 300},
                                                       {"label": "B", "amount_vnd": 0}])
        self.case("success_zero_component_is_warning_only",
                  (["COMPONENT_AMOUNT_ZERO_WARNING"], ["COMPONENT_AMOUNT_ZERO_WARNING"], []),
                  (self.current_view(zero_component)["submit_time_reasons"],
                   self.current_view(zero_component)["warnings"],
                   [b for b in self.current_view(zero_component)["current_blockers"]
                    if b.endswith("_WARNING")]))
        self.confirm_both(zero_component, price_actor=MAKER_ONLY)
        self.approve(zero_component, DUAL2, check=True)
        self.post(zero_component, DUAL2, check=True)
        self.case("success_zero_component_charge_posts_with_other_maker_and_checker",
                  before + amount + 700 + 300, self.balance(customer))
        self.report["success_path"] = {
            "customer": customer, "debt_period": period, "amount_vnd": amount,
            "balance_before": before, "balance_after": after,
            "balance_after_all_three_charges": self.balance(customer),
            "proposal_id": c.proposal_id, "trip_key": c.key,
            "resolution_status": ABSENT, "price_confirmed_by_maker": True,
        }

    def g_resolution(self) -> None:
        customer = "FAKE-CUSTOMER-RES"
        for label, status in (("no_row", None), ("in_opening", "IN_OPENING"), ("unresolved", "UNRESOLVED")):
            c = self.charge(customer=customer, seed=status)
            self.confirm_both(c)
            before = self.snapshot(c.proposal_id)
            approval = self.approve(c)
            post = self.post(c)
            self.case(f"{label}_projection_reports_missing_resolution", True,
                      "OPENING_RESOLUTION_MISSING" in self.current_view(c)["current_blockers"])
            self.rejected(f"{label}_approval_refused", approval, M_RES_APPROVAL)
            self.rejected(f"{label}_post_refused", post, M_POST)
            self.case(f"{label}_nothing_recorded_and_balance_unchanged", (before, 0),
                      (self.snapshot(c.proposal_id), self.balance(customer)))
            last = c
        self.set_resolution(last.key, ABSENT)
        self.case("unresolved_then_absent_clears_projection_blocker", [],
                  self.current_view(last)["current_blockers"])
        self.approve(last, check=True)
        self.post(last, check=True)
        self.case("unresolved_then_absent_charge_posts", last.amount, self.balance(customer))

        other = self.charge(customer=customer, seed=None)
        self.seed("NOSUCHKEYXYZ")
        self.confirm_both(other)
        self.rejected("resolution_for_a_different_key_does_not_help", self.approve(other), M_RES_APPROVAL)

        flip = self.charge(customer=customer, amount=410)
        self.confirm_both(flip)
        self.approve(flip, check=True)
        balance_before = self.balance(customer)
        self.set_resolution(flip.key, "IN_OPENING")
        self.rejected("resolution_flipped_after_approval_blocks_post", self.post(flip), M_RES_POST)
        self.case("blocked_post_keeps_approved_state_and_balance", ("approved", 0, balance_before),
                  (self.snapshot(flip.proposal_id)["state"], self.count("posting", f"proposal_id={flip.proposal_id}"),
                   self.balance(customer)))
        self.set_resolution(flip.key, ABSENT)
        self.post(flip, check=True)
        self.case("restoring_absent_resolution_allows_post", balance_before + 410, self.balance(customer))

    def g_trip_key(self) -> None:
        customer = "FAKE-CUSTOMER-TRIP"
        self.case("compute_trip_key_removes_all_whitespace_and_uppercases", ["ABC123CONT9"] * 2, [
            self.query("SELECT p0_fixture.compute_trip_key(' abc 123 ', E'cont\\t9')"),
            self.query("SELECT p0_fixture.compute_trip_key('ABC123', 'CONT9')")])
        spaced = self.charge(customer=customer, booking=" abc 123 ", container="cont 9", seed=None)
        self.case("spaced_payload_stores_normalized_key", ("ABC123CONT9", [], " abc 123 "),
                  (self.current_view(spaced)["payload"]["trip_key"], self.current_view(spaced)["submit_time_reasons"],
                   self.current_view(spaced)["payload"]["booking_no"]))
        same = self.charge(customer=customer, booking="ABC123", container="CONT9", seed=None)
        self.case("same_key_second_proposal_gets_duplicate_reason_and_original_shows_blocker",
                  (True, True), ("DUPLICATE_TRIP_KEY" in self.current_view(same)["submit_time_reasons"],
                                 "DUPLICATE_TRIP_KEY" in self.current_view(spaced)["current_blockers"]))
        lower = self.charge(customer=customer, booking="abc123", container="cont9", seed=None)
        self.case("duplicate_detection_ignores_case", True,
                  "DUPLICATE_TRIP_KEY" in self.current_view(lower)["submit_time_reasons"])
        distinct = self.charge(customer=customer, seed=None)
        self.case("distinct_key_has_no_duplicate_reason", ([], False), (
            self.current_view(distinct)["submit_time_reasons"],
            "DUPLICATE_TRIP_KEY" in self.current_view(distinct)["current_blockers"]))
        self.submit_raw(dumps({**distinct.payload, "reason": "edited"}), proposal_id=distinct.proposal_id)
        self.case("editing_own_proposal_is_not_a_duplicate", [], json.loads(
            self.query(f"SELECT to_jsonb(review_reason_codes)::text FROM p0_fixture.business_revision "
                       f"WHERE proposal_id={distinct.proposal_id} AND revision_no=2")))

        missing_variants = {
            "null_booking": (None, "C1"), "empty_booking": ("", "C1"), "blank_booking": ("   ", "C1"),
            "null_container": ("B1", None), "tab_container": ("B1", " \t "),
        }
        for label, (booking, container) in missing_variants.items():
            c = self.charge(customer=customer, booking=booking, container=container, seed=None)
            self.confirm_both(c)
            view = self.current_view(c)
            self.case(f"{label}_is_trip_key_missing_and_stored_null",
                      (True, None), ("TRIP_KEY_MISSING" in view["submit_time_reasons"], view["payload"]["trip_key"]))
            self.rejected(f"{label}_approval_refused", self.approve(c), "trip key missing or placeholder")
        omitted = self.charge(customer=customer, booking=None, container=None, seed=None,
                              drop=("booking_no", "container_no"))
        self.case("omitted_booking_and_container_are_trip_key_missing", True,
                  "TRIP_KEY_MISSING" in self.current_view(omitted)["submit_time_reasons"])
        number_booking = self.submit_raw(dumps(charge_payload(123, "C1", customer=customer)), check=False)
        self.rejected("non_string_booking_is_rejected", number_booking, "invalid fixture optional field")

        for label, booking, container in (("slash", "/", "PH1"), ("spaced_slash", " / ", "PH2")):
            c = self.charge(customer=customer, booking=booking, container=container, seed=ABSENT)
            self.confirm_both(c)
            codes = self.current_view(c)["submit_time_reasons"]
            self.case(f"{label}_booking_is_placeholder_not_missing", (True, False),
                      ("BOOKING_PLACEHOLDER" in codes, "TRIP_KEY_MISSING" in codes))
            self.rejected(f"{label}_booking_blocks_approval_even_with_resolution", self.approve(c),
                          "trip key missing or placeholder")
        both = self.charge(customer=customer, booking="/", container="", seed=None)
        self.case("slash_with_blank_container_has_both_codes", ["BOOKING_PLACEHOLDER", "TRIP_KEY_MISSING"],
                  self.current_view(both)["submit_time_reasons"])

        first = self.charge(customer=customer, amount=120)
        second = self.charge(customer=customer, amount=130, booking=first.payload["booking_no"],  # type: ignore[arg-type]
                             container=first.payload["container_no"], seed=None)  # type: ignore[arg-type]
        self.confirm_both(first)
        self.confirm_both(second)
        self.case("duplicate_pair_second_has_reason", True,
                  "DUPLICATE_TRIP_KEY" in self.current_view(second)["submit_time_reasons"])
        before = self.balance(customer)
        self.approve(first, check=True)
        self.approve(second, check=True)  # nothing posted yet: both can reach approved
        self.post(first, check=True)
        self.rejected("duplicate_second_post_refused_after_first_posted", self.post(second),
                      "trip key already posted by another proposal")
        self.case("duplicate_pair_only_first_amount_in_balance", (before + 120, "approved", 1),
                  (self.balance(customer), self.snapshot(second.proposal_id)["state"],
                   self.count("posting", f"trip_key={sql_literal(first.key)}")))
        third = self.charge(customer=customer, amount=140, booking=first.payload["booking_no"],  # type: ignore[arg-type]
                            container=first.payload["container_no"], seed=None)  # type: ignore[arg-type]
        self.confirm_both(third)
        self.rejected("duplicate_of_posted_key_cannot_be_approved", self.approve(third),
                      "trip key already posted by another proposal")
        self.case("duplicate_of_posted_key_stays_review_needed_and_out_of_balance", ("review_needed", before + 120),
                  (self.snapshot(third.proposal_id)["state"], self.balance(customer)))

    def g_date(self) -> None:
        customer = "FAKE-CUSTOMER-DATE"
        proposals_before = self.count("proposal")
        rejected_old = []
        for value in ("2026-10-13", "2026-10-01", "2026-09-30"):
            booking, container = self.next_trip()
            payload = charge_payload(booking, container, customer=customer, warehouse=value)
            result = self.submit_raw(dumps(payload), check=False)
            rejected_old.append(result.returncode != 0 and "opening 13/10" in result.stderr)
        self.case("warehouse_date_before_14_10_is_rejected_as_old_trip", [True] * 3, rejected_old)
        invalid = []
        for value in ("14/10/2026", "2026-10-14T00:00", "2026-02-30", "2026-13-01", ""):
            booking, container = self.next_trip()
            payload = charge_payload(booking, container, customer=customer, warehouse=value)
            result = self.submit_raw(dumps(payload), check=False)
            invalid.append(result.returncode != 0 and "invalid fixture date" in result.stderr)
        self.case("malformed_or_impossible_warehouse_dates_are_rejected", [True] * 5, invalid)
        self.case("rejected_dates_created_no_proposal", proposals_before, self.count("proposal"))
        accepted = []
        for value in ("2026-10-14", "2026-10-15"):
            c = self.charge(customer=customer, warehouse=value)
            accepted.append(self.current_view(c)["payload"]["warehouse_in_date"])
        self.case("warehouse_date_14_10_and_later_is_accepted", ["2026-10-14", "2026-10-15"], accepted)
        legacy_name = charge_payload("BKX", "CTX", customer=customer)
        legacy_name["event_date"] = legacy_name.pop("warehouse_in_date")
        self.rejected("event_date_name_is_no_longer_accepted",
                      self.submit_raw(dumps(legacy_name), check=False), "missing or unknown business fields")

    def g_canonical(self) -> None:
        customer = "FAKE-CUSTOMER-CANON"
        base = charge_payload("BKCAN", "CTCAN", customer=customer)
        text = dumps(base)
        replacements = {
            "total_100.0": ('"total_vnd":100', '"total_vnd":100.0'),
            "total_1e2": ('"total_vnd":100', '"total_vnd":1e2'),
            "total_1E+2": ('"total_vnd":100', '"total_vnd":1E+2'),
            "total_string": ('"total_vnd":100', '"total_vnd":"100"'),
            "total_negative": ('"total_vnd":100', '"total_vnd":-5'),
            "total_fraction": ('"total_vnd":100', '"total_vnd":100.5'),
            "total_boolean": ('"total_vnd":100', '"total_vnd":true'),
            "total_16_digits": ('"total_vnd":100', '"total_vnd":1000000000000000'),
            "line_amount_100.0": ('"amount_vnd":100}', '"amount_vnd":100.0}'),
            "component_50.0": ('"amount_vnd":50}', '"amount_vnd":50.0}'),
            "line_no_1.0": ('"line_no":1,', '"line_no":1.0,'),
            "schema_version_3.0": ('"schema_version":3', '"schema_version":3.0'),
        }
        results = {}
        for label, (old, new) in replacements.items():
            mutated = text.replace(old, new, 1)
            result = self.submit_raw(mutated, check=False)
            results[label] = result.returncode != 0 and "canonical" in result.stderr
        self.case("non_canonical_numbers_are_rejected_not_normalized", {k: True for k in results}, results)
        string_ok = self.submit_raw(dumps({**base, "reason": 'ghi chu 1.5 va 1e2 va \\"2.5\\"'}), check=False)
        self.case("number_like_text_inside_strings_is_accepted", 0, string_ok.returncode)

        first = json.loads(self.submit_raw(text).stdout.strip())
        pid = int(first["proposal_id"])
        pretty = json.dumps(dict(reversed(list(base.items()))), indent=3, ensure_ascii=True)
        again = json.loads(self.submit_raw(pretty, proposal_id=pid).stdout.strip())
        self.case("key_order_and_whitespace_do_not_change_hash_or_create_revision",
                  (first["content_sha256"], first["revision_id"], False, 1),
                  (again["content_sha256"], again["revision_id"], again["revision_created"],
                   self.snapshot(pid)["revision_count"]))
        self.case("noop_submit_is_audited", ["submit", "submit_noop"], self.audit_actions(pid))
        changed = json.loads(self.submit_raw(dumps({**base, "source_ref": "other"}), proposal_id=pid).stdout.strip())
        self.case("changed_business_field_creates_new_revision_and_hash", (2, True, True),
                  (changed["revision_no"], changed["content_sha256"] != first["content_sha256"],
                   changed["revision_created"]))

        def hash_of(**kw) -> tuple[str, list[str]]:
            created = json.loads(self.submit_raw(dumps(charge_payload(
                *self.next_trip(), customer=customer, **kw))).stdout.strip())
            codes = json.loads(self.query(
                "SELECT to_jsonb(review_reason_codes)::text FROM p0_fixture.business_revision "
                f"WHERE revision_id={created['revision_id']}"))
            return created["content_sha256"], codes
        null_total = hash_of(total_vnd=None, lines=[{"line_no": 1, "customer_id": customer,
                                                      "debt_period": "2026-10", "amount_vnd": None}])
        zero_total = hash_of(total_vnd=0, lines=[{"line_no": 1, "customer_id": customer,
                                                   "debt_period": "2026-10", "amount_vnd": 0}])
        self.case("null_total_and_zero_total_have_different_reasons",
                  (True, True, True),
                  ("TOTAL_MISSING" in null_total[1] and "LINE_AMOUNT_MISSING" in null_total[1],
                   "TOTAL_ZERO" in zero_total[1] and "LINE_AMOUNT_MISSING" not in zero_total[1],
                   "TOTAL_ZERO" not in null_total[1]))
        omitted = json.loads(self.submit_raw(dumps(charge_payload(
            "BKOMIT", "CTOMIT", customer=customer, drop=("total_vnd", "source_ref")))).stdout.strip())
        explicit = json.loads(self.submit_raw(dumps(charge_payload(
            "BKOMIT", "CTOMIT", customer=customer, total_vnd=None, source_ref=None))).stdout.strip())
        self.case("omitted_and_null_optional_fields_have_the_same_hash", True,
                  omitted["content_sha256"] == explicit["content_sha256"])

        bad = {
            "schema_version_2": ({**base, "schema_version": 2}, "expected version 3"),
            "schema_version_4": ({**base, "schema_version": 4}, "expected version 3"),
            "schema_version_missing": ({k: v for k, v in base.items() if k != "schema_version"},
                                       "missing or unknown business fields"),
            "legacy_trip_code": ({**base, "trip_code": "X"}, "missing or unknown business fields"),
            "legacy_kind": ({**base, "kind": "charge_fixture"}, "missing or unknown business fields"),
            "legacy_opening_ref": ({**base, "opening_snapshot_ref": "x"}, "missing or unknown business fields"),
            "customer_missing": ({k: v for k, v in base.items() if k != "customer_id"},
                                 "missing or unknown business fields"),
            "no_lines": ({**base, "lines": []}, "exactly one debt line"),
            "two_lines": ({**base, "lines": base["lines"] * 2}, "exactly one debt line"),  # type: ignore[operator]
            "line_customer_mismatch": ({**base, "lines": [{**base["lines"][0], "customer_id": "OTHER"}]},  # type: ignore[index]
                                       "invalid fixture line"),
            "line_period_mismatch": ({**base, "lines": [{**base["lines"][0], "debt_period": "2026-11"}]},  # type: ignore[index]
                                     "invalid fixture line"),
            "line_unknown_key": ({**base, "lines": [{**base["lines"][0], "memo": "x"}]},  # type: ignore[index]
                                 "invalid fixture line"),
            "bad_period_format": ({**base, "debt_period": "2026-13"}, "invalid fixture payload fields"),
            "blank_reason": ({**base, "reason": "  "}, "invalid fixture payload fields"),
            "malformed_evidence_hash": ({**base, "evidence_sha256": "zz"}, "invalid evidence hash"),
            "malformed_override_hash": ({**base, "period_override_evidence_sha256": "zz"},
                                        "invalid period override evidence hash"),
            "component_unknown_key": ({**base, "price_components": [{"label": "A", "amount_vnd": 1, "x": 1}]},
                                      "invalid per-trip price component"),
            "component_blank_label": ({**base, "price_components": [{"label": " ", "amount_vnd": 1}]},
                                      "invalid per-trip price component"),
            "payload_too_long": ({**base, "reason": "x" * 70000}, "invalid fixture payload length"),
        }
        outcomes = {}
        proposals_before_bad = self.count("proposal")
        for label, (payload, expected) in bad.items():
            result = self.submit_raw(dumps(payload), check=False)
            outcomes[label] = result.returncode != 0 and expected in result.stderr
        top_level = self.submit_raw("[]", check=False)
        outcomes["top_level_array"] = top_level.returncode != 0
        self.case("structural_violations_are_rejected_with_specific_reason", {k: True for k in outcomes}, outcomes)
        self.case("rejected_payloads_created_no_proposal", proposals_before_bad, self.count("proposal"))

    def g_price(self) -> None:
        customer = "FAKE-CUSTOMER-PRICE"
        zero_amount = {"total_vnd": 0, "lines": [{"line_no": 1, "customer_id": customer,
                                                   "debt_period": "2026-10", "amount_vnd": 0}],
                       "price_components": [{"label": "A", "amount_vnd": 0}]}
        line = lambda amount: [{"line_no": 1, "customer_id": customer, "debt_period": "2026-10",  # noqa: E731
                                "amount_vnd": amount}]
        variants = {
            "total_zero": ("TOTAL_ZERO", zero_amount),
            "total_null": ("TOTAL_MISSING", {"total_vnd": None}),
            "components_null": ("PRICE_COMPONENTS_MISSING", {"price_components": None}),
            "components_empty": ("PRICE_COMPONENTS_MISSING", {"price_components": []}),
            "component_amount_null": ("COMPONENT_AMOUNT_MISSING", {"price_components": [
                {"label": "A", "amount_vnd": None}, {"label": "B", "amount_vnd": 50}]}),
            "components_do_not_sum_to_total": ("COMPONENT_TOTAL_MISMATCH", {"price_components": [
                {"label": "A", "amount_vnd": 40}, {"label": "B", "amount_vnd": 50}]}),
            "line_amount_null": ("LINE_AMOUNT_MISSING", {"lines": line(None)}),
            "line_differs_from_total": ("LINE_TOTAL_MISMATCH", {"lines": line(90)}),
            "source_ref_null": ("SOURCE_EVIDENCE_MISSING", {"source_ref": None}),
            "evidence_ref_blank": ("SOURCE_EVIDENCE_MISSING", {"evidence_ref": "   "}),
        }
        for label, (expected_code, override) in variants.items():
            c = self.charge(customer=customer, **override)
            before = self.snapshot(c.proposal_id)
            result = self.call("confirm_price_revision", self.ids(c), MAKER)
            codes = self.current_view(c)["submit_time_reasons"]
            self.case(f"{label}_blocks_price_confirmation_and_leaves_no_record",
                      (True, True, before),
                      (expected_code in codes, M_PRICE_BLOCK in result.stderr and result.returncode != 0,
                       self.snapshot(c.proposal_id)))

        zero =self.charge(customer=customer, amount=200,
                           price_components=[{"label": "A", "amount_vnd": 200}, {"label": "B", "amount_vnd": 0}])
        confirmed = self.call("confirm_price_revision", self.ids(zero), MAKER)
        self.case("zero_component_warns_and_price_confirmation_succeeds", (0, ["COMPONENT_AMOUNT_ZERO_WARNING"]),
                  (confirmed.returncode, self.current_view(zero)["warnings"]))

        self_confirm = self.charge(customer=customer)
        other_confirm = self.charge(customer=customer)
        a = self.call("confirm_price_revision", self.ids(self_confirm), MAKER)
        b = self.call("confirm_price_revision", self.ids(other_confirm), MAKER_ONLY)
        self.case("maker_may_confirm_own_price_and_another_maker_may_too", (0, 0), (a.returncode, b.returncode))
        self.rejected("checker_only_actor_cannot_confirm_price",
                      self.call("confirm_price_revision", self.ids(self_confirm), CHECKER), "actor role required")
        self.rejected("same_revision_price_cannot_be_confirmed_twice",
                      self.call("confirm_price_revision", self.ids(self_confirm), MAKER_ONLY), "duplicate key")

        c = self.charge(customer=customer, maker=MAKER_ONLY)
        self.call("confirm_period_revision", self.ids(c), MAKER_ONLY, check=True)
        self.call("confirm_price_revision", self.ids(c), MAKER, check=True)
        self.rejected("price_confirmer_cannot_checker_approve_same_revision", self.approve(c, MAKER),
                      "price confirmer cannot checker-approve the same revision")
        self.case("refused_approval_left_charge_pending", ("review_needed", 0),
                  (self.snapshot(c.proposal_id)["state"], self.count("approval", f"proposal_id={c.proposal_id}")))
        approved = self.approve(c, CHECKER)
        self.case("a_different_checker_may_approve", 0, approved.returncode)
        self.post(c, CHECKER, check=True)
        self.case("charge_with_separate_maker_price_confirmer_and_checker_posts", c.amount,
                  self.balance(customer))

    def g_actors(self) -> None:
        customer = "FAKE-CUSTOMER-ACT"
        payload = dumps(charge_payload("BKACT", "CTACT", customer=customer))
        audits_before = self.count("audit")
        proposals_before = self.count("proposal")
        self.rejected("inactive_actor_cannot_submit", self.submit_raw(payload, actor=DISABLED, check=False),
                      "inactive actor")
        self.rejected("unknown_actor_cannot_submit", self.submit_raw(payload, actor=UNKNOWN, check=False),
                      "inactive actor")
        self.rejected("checker_only_actor_cannot_submit", self.submit_raw(payload, actor=CHECKER, check=False),
                      "actor role required")
        null_session = self.f.psql(
            f"SELECT row_to_json(x)::text FROM p0_fixture.submit_revision(NULL::bigint, {sql_literal(payload)}::text, "
            f"'{MAKER}'::uuid, NULL::uuid) x", user=API_LOGIN, check=False)
        self.rejected("missing_session_is_rejected", null_session, "actor and session are required")
        self.case("rejected_calls_wrote_no_proposal_or_audit", (proposals_before, audits_before),
                  (self.count("proposal"), self.count("audit")))

        session = uuid.uuid4()
        created = json.loads(self.submit_raw(payload, session=session).stdout.strip())
        c = Charge(int(created["proposal_id"]), int(created["revision_id"]), str(created["content_sha256"]),
                   "BKACTCTACT", customer, 100, "2026-10", MAKER, {})
        self.seed(c.key)
        self.case("audit_stores_app_actor_session_and_api_login", (str(MAKER), str(session), API_LOGIN), tuple(
            self.query("SELECT app_actor_id || '|' || app_session_id || '|' || database_session_user "
                       f"FROM p0_fixture.audit WHERE proposal_id={c.proposal_id}").split("|")))
        self.rejected("other_maker_cannot_edit_proposal",
                      self.submit_raw(payload, proposal_id=c.proposal_id, actor=MAKER_ONLY, check=False),
                      "proposal unavailable to this maker")
        self.rejected("other_maker_cannot_set_presentation_title", self.f.psql(
            f"SELECT p0_fixture.set_presentation_title({c.proposal_id}, 'x', '{MAKER_ONLY}'::uuid, '{uuid.uuid4()}'::uuid)",
            user=API_LOGIN, check=False), "proposal unavailable to this maker")
        self.rejected("only_the_proposal_maker_confirms_period",
                      self.call("confirm_period_revision", self.ids(c), MAKER_ONLY),
                      "period confirmation requires current charge revision from its maker")
        self.confirm_both(c)
        self.rejected("maker_only_actor_cannot_approve", self.approve(c, MAKER_ONLY), "actor role required")
        self.rejected("maker_with_checker_role_cannot_approve_own_charge", self.approve(c, MAKER), M_STALE)
        self.approve(c, CHECKER, check=True)
        self.rejected("maker_cannot_post_own_charge", self.post(c, MAKER), M_POST)
        self.rejected("a_checker_who_did_not_approve_cannot_post", self.post(c, DUAL2), M_POST)
        self.case("refused_decisions_left_charge_approved_not_posted", ("approved", 0),
                  (self.snapshot(c.proposal_id)["state"], self.count("posting", f"proposal_id={c.proposal_id}")))
        self.post(c, CHECKER, check=True)
        self.case("posting_and_audit_use_one_api_login", [API_LOGIN], json.loads(self.query(
            "SELECT to_jsonb(array_agg(DISTINCT database_session_user::text))::text FROM p0_fixture.audit "
            f"WHERE proposal_id={c.proposal_id}")))

    def g_revision(self) -> None:
        customer = "FAKE-CUSTOMER-REV"
        c = self.charge(customer=customer, amount=600)
        self.confirm_both(c)
        self.approve(c, check=True)
        edit = json.loads(self.submit_raw(dumps({**c.payload, "reason": "revised"}), proposal_id=c.proposal_id)
                          .stdout.strip())
        rev2 = Charge(c.proposal_id, int(edit["revision_id"]), str(edit["content_sha256"]),
                      c.key, customer, 600, "2026-10", MAKER, {**c.payload, "reason": "revised"})
        snap = self.snapshot(c.proposal_id)
        self.case("edit_after_approval_creates_revision_2_keeps_old_approval_and_returns_to_review",
                  ("review_needed", 2, 1, True),
                  (snap["state"], snap["revision_no"], len(snap["approval_history"]),  # type: ignore[arg-type]
                   rev2.content_hash != c.content_hash))
        self.rejected("stale_revision_cannot_be_posted", self.post(c), M_POST)
        self.rejected("stale_revision_cannot_be_approved", self.approve(c), M_STALE)
        self.rejected("stale_revision_cannot_take_price_confirmation",
                      self.call("confirm_price_revision", self.ids(c), MAKER), "requires the current charge revision")
        self.rejected("stale_revision_cannot_take_period_confirmation",
                      self.call("confirm_period_revision", self.ids(c), MAKER),
                      "period confirmation requires current charge revision")
        projection = self.projection(c.proposal_id)["revisions"]
        self.case("old_confirmations_do_not_carry_to_new_revision",
                  (False, True, ["PERIOD_CONFIRMATION_MISSING", "PRICE_CONFIRMATION_MISSING"], []),
                  (projection[0]["is_current_revision"], projection[1]["is_current_revision"],  # type: ignore[index]
                   projection[1]["current_blockers"], projection[0]["current_blockers"]))  # type: ignore[index]
        self.rejected("new_revision_cannot_be_approved_without_its_own_confirmations",
                      self.approve(rev2), "maker confirmation required")
        self.confirm_both(rev2)
        wrong_hash = Charge(**{**rev2.__dict__, "content_hash": "0" * 64})
        self.rejected("approval_with_wrong_hash_is_refused", self.approve(wrong_hash), M_STALE)
        self.approve(rev2, check=True)
        self.rejected("post_with_wrong_hash_is_refused", self.post(wrong_hash), M_POST)
        self.post(rev2, check=True)
        same_payload = self.query(
            "SELECT (p.canonical_payload = r.canonical_payload AND p.content_sha256 = r.content_sha256 "
            "AND p.revision_id = r.revision_id)::text FROM p0_fixture.posting p "
            f"JOIN p0_fixture.business_revision r ON r.revision_id=p.revision_id WHERE p.proposal_id={c.proposal_id}")
        self.case("posting_stores_exact_revision_2_payload_hash_and_id", ("true", rev2.revision_id, 600),
                  (same_payload, int(self.query(f"SELECT revision_id FROM p0_fixture.posting WHERE proposal_id={c.proposal_id}")),
                   self.balance(customer)))

        p = self.charge(customer=customer)
        self.confirm_both(p)
        self.approve(p, check=True)
        before = self.snapshot(p.proposal_id)
        title = self.f.psql(f"SELECT p0_fixture.set_presentation_title({p.proposal_id}, 'Display only', "
                            f"'{MAKER}'::uuid, '{uuid.uuid4()}'::uuid)", user=API_LOGIN, check=False)
        after = self.snapshot(p.proposal_id)
        self.case("presentation_change_keeps_revision_hash_and_approval", (0, before["content_sha256"], "approved",
                                                                         before["approval_history"]),
                  (title.returncode, after["content_sha256"], after["state"], after["approval_history"]))
        self.case("presentation_is_audited", "presentation", self.audit_actions(p.proposal_id)[-1])

        for table, column in (("business_revision", "content_sha256"), ("approval", "content_sha256"),
                              ("price_confirmation", "content_sha256"), ("period_confirmation", "content_sha256"),
                              ("posting", "content_sha256"), ("audit", "content_sha256")):
            update = self.f.psql(f"UPDATE p0_fixture.{table} SET {column}={column}", check=False)
            delete = self.f.psql(f"DELETE FROM p0_fixture.{table}", check=False)
            self.case(f"{table}_is_append_only", [True, True],
                      ["append-only fixture row" in update.stderr and update.returncode != 0,
                       "append-only fixture row" in delete.stderr and delete.returncode != 0])

    def g_period(self) -> None:
        customer = "FAKE-CUSTOMER-PER"
        closed = self.charge(customer=customer, period="2026-08", **OVERRIDE)
        self.case("closed_period_blocks_period_confirmation_and_shows_in_projection", (True, 0),
                  ("DEBT_PERIOD_NOT_OPEN" in self.current_view(closed)["current_blockers"],
                   self.count("period_confirmation", f"proposal_id={closed.proposal_id}")))
        self.rejected("closed_period_period_confirmation_refused",
                      self.call("confirm_period_revision", self.ids(closed), MAKER),
                      "debt period is not open for maker confirmation")
        unknown = self.charge(customer=customer, period="2026-12", **OVERRIDE)
        self.rejected("period_without_state_row_is_treated_as_not_open",
                      self.call("confirm_period_revision", self.ids(unknown), MAKER),
                      "debt period is not open for maker confirmation")

        cross = {}
        for label, drop in (("reason", "period_override_reason"), ("evidence_ref", "period_override_evidence_ref"),
                            ("evidence_hash", "period_override_evidence_sha256")):
            c = self.charge(customer=customer, period="2026-09", **{**OVERRIDE, drop: None})
            result = self.call("confirm_period_revision", self.ids(c), MAKER)
            cross[label] = ("PERIOD_OVERRIDE_EVIDENCE_MISSING" in self.current_view(c)["submit_time_reasons"]
                            and result.returncode != 0 and "period override evidence is required" in result.stderr)
        self.case("cross_month_charge_needs_all_three_override_fields", {k: True for k in cross}, cross)
        full = self.charge(customer=customer, period="2026-09", **OVERRIDE)
        self.case("full_override_has_no_missing_reason", [], self.current_view(full)["submit_time_reasons"])
        self.run_to_posted(full)
        self.case("cross_month_charge_posts_to_its_debt_period_not_the_trip_month", (full.amount, 0),
                  (self.balance(customer, "2026-09"), self.balance(customer, "2026-10")))

        self.set_period("2026-11", "open")
        close_after_confirm = self.charge(customer=customer, period="2026-11", warehouse="2026-11-02")
        self.confirm_both(close_after_confirm)
        self.set_period("2026-11", "closed")
        self.rejected("period_closed_after_confirmation_blocks_approval", self.approve(close_after_confirm),
                      "debt period is not open at approval")
        self.set_period("2026-11", "open")
        self.approve(close_after_confirm, check=True)
        self.set_period("2026-11", "closed")
        before = self.balance(customer, "2026-11")
        self.rejected("period_closed_after_approval_blocks_post", self.post(close_after_confirm),
                      "debt period is not open at posting")
        self.case("blocked_post_keeps_approved_state_and_balance", ("approved", before),
                  (self.snapshot(close_after_confirm.proposal_id)["state"], self.balance(customer, "2026-11")))
        self.set_period("2026-11", "open")
        self.post(close_after_confirm, check=True)
        self.case("reopened_period_allows_post", close_after_confirm.amount, self.balance(customer, "2026-11"))

    def g_rollback(self) -> None:
        customer = "FAKE-CUSTOMER-RB"
        c = self.charge(customer=customer, amount=330)
        self.confirm_both(c)
        self.approve(c, check=True)
        before = self.snapshot(c.proposal_id)
        balance_before = self.balance(customer)
        query = ("BEGIN; SET LOCAL p0_fixture.fail_post = 'on'; "
                 + decision_sql("post_revision", *self.ids(c), CHECKER) + "; COMMIT")
        failed = self.f.psql(query, user=API_LOGIN, check=False)
        self.rejected("injected_deferred_failure_aborts_the_post", failed, "injected deferred fixture failure")
        self.case("failed_post_rolls_back_state_posting_audit_and_balance", (before, balance_before, False),
                  (self.snapshot(c.proposal_id), self.balance(customer),
                   "post" in self.audit_actions(c.proposal_id)))
        self.post(c, check=True)
        self.case("retry_after_rollback_posts_once", (balance_before + 330, 1),
                  (self.balance(customer), self.count("posting", f"proposal_id={c.proposal_id}")))

    def g_contention(self) -> None:
        customer = "FAKE-CUSTOMER-LOCK"
        self.set_period("2026-11", "open")

        # 1. edit commits first; the waiting approval of the old revision must become stale.
        c = self.charge(customer=customer, amount=701)
        self.confirm_both(c)
        edit_sql = submit_sql(c.proposal_id, dumps({**c.payload, "reason": "edit first"}), MAKER)
        ev = self.run_contention("edit-before-approve", c.proposal_id, customer, "2026-10", API_LOGIN, edit_sql,
                                 API_LOGIN, decision_sql("approve_revision", *self.ids(c), CHECKER), M_STALE)
        after = ev["after"]
        self.case("edit_before_approve_creates_revision_2_and_leaves_old_unapproved", (2, True, 0, 0),
                  (after["revision_no"], after["content_sha256"] != c.content_hash,  # type: ignore[index]
                   self.count("approval", f"proposal_id={c.proposal_id}"),
                   self.count("posting", f"proposal_id={c.proposal_id}")))

        # 2. approval commits first; the waiting edit becomes revision 2 and the old approval cannot post.
        c = self.charge(customer=customer, amount=711)
        self.confirm_both(c)
        edit_sql = submit_sql(c.proposal_id, dumps({**c.payload, "reason": "edit second"}), MAKER)
        ev = self.run_contention("approve-before-edit", c.proposal_id, customer, "2026-10", API_LOGIN,
                                 decision_sql("approve_revision", *self.ids(c), CHECKER), API_LOGIN, edit_sql)
        after = ev["after"]
        self.case("approve_before_edit_keeps_old_approval_and_adds_revision_2", (2, True, True),
                  (after["revision_no"], after["current_revision_id"] != c.revision_id,  # type: ignore[index]
                   any(row[1] == c.revision_id for row in after["approval_history"])))  # type: ignore[index]
        self.rejected("approve_before_edit_old_approval_cannot_post", self.post(c), M_POST)

        # 3. period close commits first; the waiting period confirmation must be refused.
        self.set_period("2026-11", "open")
        c = self.charge(customer=customer, amount=803, period="2026-11", warehouse="2026-11-02")
        self.call("confirm_price_revision", self.ids(c), MAKER, check=True)
        close_sql = ("UPDATE p0_fixture.debt_period_state SET state='closed' "
                     "WHERE debt_period='2026-11' RETURNING debt_period || '|' || state")
        ev = self.run_contention("close-before-confirm-period", c.proposal_id, customer, "2026-11", "postgres",
                                 close_sql, API_LOGIN, decision_sql("confirm_period_revision", *self.ids(c), MAKER),
                                 "debt period is not open for maker confirmation")
        self.case("close_before_confirm_records_no_confirmation_or_audit", (["2026-11|closed"], [], True),
                  (ev["holder_action_output"], ev["after"]["period_confirmation_history"],  # type: ignore[index]
                   ev["after"]["audit_count"] == ev["before"]["audit_count"]))  # type: ignore[index]
        self.case("close_before_confirm_projection_reports_closed_period", True,
                  "DEBT_PERIOD_NOT_OPEN" in self.current_view(c)["current_blockers"])

        # 4. period confirmation commits first; the waiting period close then wins, blocking approval.
        self.set_period("2026-11", "open")
        c = self.charge(customer=customer, amount=809, period="2026-11", warehouse="2026-11-02")
        self.call("confirm_price_revision", self.ids(c), MAKER, check=True)
        ev = self.run_contention("confirm-period-before-close", c.proposal_id, customer, "2026-11", API_LOGIN,
                                 decision_sql("confirm_period_revision", *self.ids(c), MAKER), "postgres", close_sql)
        self.case("confirm_before_close_keeps_confirmation_and_period_ends_closed", (1, "2026-11|closed", "closed"),
                  (len(ev["after"]["period_confirmation_history"]),  # type: ignore[index]
                   ev["waiter_output"].strip(),  # type: ignore[union-attr]
                   self.query("SELECT state FROM p0_fixture.debt_period_state WHERE debt_period='2026-11'")))
        self.rejected("closed_period_after_confirmation_cannot_be_approved", self.approve(c),
                      "debt period is not open at approval")
        self.set_period("2026-11", "open")

    def g_final(self) -> None:
        self.case("every_posting_has_an_absent_resolution_and_distinct_key", (0, 0), (
            int(self.query("SELECT count(*) FROM p0_fixture.posting p WHERE NOT EXISTS (SELECT 1 FROM "
                           "p0_fixture.trip_opening_resolution t WHERE t.trip_key=p.trip_key "
                           "AND t.status='ABSENT_FROM_OPENING_APPROVED')")),
            int(self.query("SELECT count(*) FROM (SELECT trip_key FROM p0_fixture.posting GROUP BY 1 "
                           "HAVING count(*) > 1) d"))))
        self.case("every_posting_is_from_an_approved_current_revision_with_maker_different_from_checker", 0,
                  int(self.query(
                      "SELECT count(*) FROM p0_fixture.posting p JOIN p0_fixture.approval a ON a.approval_id=p.approval_id "
                      "JOIN p0_fixture.proposal pr ON pr.proposal_id=p.proposal_id "
                      "WHERE a.revision_id<>p.revision_id OR a.content_sha256<>p.content_sha256 "
                      "OR pr.current_revision_id<>p.revision_id OR p.maker_actor_id=p.checker_actor_id "
                      "OR pr.state<>'posted'")))
        self.case("posted_balance_equals_sum_of_posted_line_amounts", True, self.query(
            "SELECT ((SELECT coalesce(sum(posted_balance_vnd), 0) FROM p0_fixture.posted_balance) = "
            "(SELECT coalesce(sum((x.line->>'amount_vnd')::numeric), 0) FROM p0_fixture.posting p "
            "CROSS JOIN LATERAL jsonb_array_elements(p.canonical_payload->'lines') x(line)))::text") == "true")
        self.case("no_pending_or_unposted_revision_contributes_to_balance", 0, int(self.query(
            "SELECT count(*) FROM p0_fixture.proposal pr WHERE pr.state<>'posted' AND EXISTS "
            "(SELECT 1 FROM p0_fixture.posting p WHERE p.proposal_id=pr.proposal_id)")))
        rows = self.report["concurrency_evidence"]
        self.case("contention_sessions_and_processes_are_closed", True, all(
            row.get("holder_process_exited") is True and row.get("waiter_process_exited") is True
            and not row.get("cleanup_errors") for row in rows))  # type: ignore[union-attr]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", type=Path, default=Path("pg-versioned-approval.json"))
    ap.add_argument("--timeout", type=int, default=90)
    args = ap.parse_args()
    if shutil.which("docker") is None:
        raise HarnessError("docker CLI not found")

    run_id = uuid.uuid4().hex
    container = f"webdebit-pg-versioned-{run_id}"
    marker = f"codex_versioned_run={run_id}"
    sql_bytes = SCHEMA.read_bytes().replace(b"\r\n", b"\n")
    report: dict[str, object] = {
        "run_id": run_id,
        "database": DATABASE,
        "image": IMAGE,
        "payload_schema_version": 3,
        "fixture_sha256": hashlib.sha256(sql_bytes).hexdigest(),
        "fixture_path": str(SCHEMA),
        "runner_sha256": hashlib.sha256(Path(__file__).read_bytes().replace(b"\r\n", b"\n")).hexdigest(),
        "container_helper_sha256": hashlib.sha256(
            (SCHEMA.parent / "test_pg_ledger_schema.py").read_bytes().replace(b"\r\n", b"\n")
        ).hexdigest(),
        "revision": run(["git", "-C", str(ROOT), "rev-parse", "HEAD"]).stdout.strip(),
        "network": "none",
        "published_ports": [],
        "volume_mounts": [],
        "cases": [],
        "groups": {},
        "failed_cases": [],
        "group_errors": [],
        "success_path": {},
        "concurrency_evidence": [],
        "session_cleanup": "not_started",
        "runtime_checks": {
            "app_login_session": "not_implemented",
            "tailscale_boundary": "not_run",
            "receipt_verification_q09": "open_and_not_in_fixture",
            "production_resolution_table": "not_designed_fixture_table_is_empty_by_default",
        },
        "cleanup": "not_started",
        "exit_code": 1,
    }
    report["tree"] = run(["git", "-C", str(ROOT), "rev-parse", "HEAD^{tree}"]).stdout.strip()
    docker = ["docker"]
    container_id: str | None = None
    error: BaseException | None = None

    try:
        run(docker + ["run", "--detach", "--name", container,
            "--label", f"{LABEL_TEST}={LABEL_VALUE}",
            "--label", f"{LABEL_RUN}={run_id}",
            "--network", "none", "--tmpfs", "/var/lib/postgresql:rw,exec,nosuid,size=512m",
            "--env", "POSTGRES_HOST_AUTH_METHOD=trust", IMAGE], timeout=240)
        inspect = json.loads(run(docker + ["inspect", container]).stdout)[0]
        container_id = inspect.get("Id")
        if (not container_id or inspect.get("Name", "").lstrip("/") != container
                or inspect["Config"]["Labels"].get(LABEL_TEST) != LABEL_VALUE
                or inspect["Config"]["Labels"].get(LABEL_RUN) != run_id
                or inspect.get("Mounts")
                or inspect.get("HostConfig", {}).get("Tmpfs") != {
                    "/var/lib/postgresql": "rw,exec,nosuid,size=512m"}
                or inspect.get("HostConfig", {}).get("NetworkMode") != "none"
                or inspect.get("HostConfig", {}).get("PortBindings")):
            raise HarnessError("container identity/isolation check failed")
        report["container_id"] = container_id

        deadline = time.monotonic() + args.timeout
        while time.monotonic() < deadline:
            ready = run(docker + ["exec", container, "pg_isready", "-U", "postgres", "-d", "postgres"], check=False)
            logs = run(docker + ["logs", container], check=False, timeout=10)
            if ready.returncode == 0 and "PostgreSQL init process complete; ready for start up." in logs.stdout + logs.stderr:
                break
            time.sleep(0.25)
        else:
            raise HarnessError("PostgreSQL startup/readiness marker timed out")

        pg = ["exec", "--env", f"PGAPPNAME={marker}", "--env", "PGOPTIONS=-c statement_timeout=25000", container]
        server = run(docker + pg + ["psql", "-X", "-qAt", "-U", "postgres", "-d", "postgres",
            "-c", "SELECT version() || '|' || current_setting('application_name')"])
        report["postgres_version_and_marker"] = server.stdout.strip()
        if marker not in server.stdout or "PostgreSQL 18.6" not in server.stdout:
            raise HarnessError("unexpected PostgreSQL version or run marker")
        run(docker + pg + ["psql", "-X", "-v", "ON_ERROR_STOP=1", "-U", "postgres", "-d", "postgres",
            "-c", "CREATE DATABASE webdebit_ledger"])
        run(docker + pg + ["psql", "-X", "-v", "ON_ERROR_STOP=1", "-U", "postgres", "-d", "postgres",
            "-c", f"COMMENT ON DATABASE webdebit_ledger IS '{marker}'"])
        target = run(docker + pg + ["psql", "-X", "-qAt", "-U", "postgres", "-d", DATABASE,
            "-c", "SELECT current_database() || '|' || shobj_description((SELECT oid FROM pg_database WHERE datname=current_database()), 'pg_database') || '|' || current_setting('application_name')"]).stdout.strip()
        if target != f"{DATABASE}|{marker}|{marker}":
            raise HarnessError("pre-DDL database/run marker check failed")
        run(docker + ["exec", "-i", "--env", f"PGAPPNAME={marker}", container,
            "psql", "-X", "-v", "ON_ERROR_STOP=1", "-U", "postgres", "-d", DATABASE],
            input_text=SCHEMA.read_text(encoding="utf-8"))
        run(docker + pg + ["psql", "-X", "-v", "ON_ERROR_STOP=1", "-U", "postgres", "-d", DATABASE,
            "-c", f"CREATE ROLE {API_LOGIN} LOGIN; GRANT p0_fixture_api TO {API_LOGIN}; "
                  f"CREATE ROLE {NO_GRANT_LOGIN} LOGIN; CREATE ROLE {NOT_MEMBER_LOGIN} LOGIN; "
                  f"GRANT CONNECT ON DATABASE {DATABASE} TO {NO_GRANT_LOGIN}, {NOT_MEMBER_LOGIN}"])

        suite = Suite(docker, container, run_id, report)
        suite.group_name = "setup"
        suite.case("fixture_schema_loads_on_postgresql_18_6", True, True)
        for name, function in (
            ("schema_and_grants", suite.g_schema),
            ("success_path", suite.g_success),
            ("opening_resolution", suite.g_resolution),
            ("trip_key", suite.g_trip_key),
            ("warehouse_date", suite.g_date),
            ("canonical_v3", suite.g_canonical),
            ("price", suite.g_price),
            ("actors_and_roles", suite.g_actors),
            ("revisions_and_append_only", suite.g_revision),
            ("debt_period", suite.g_period),
            ("rollback", suite.g_rollback),
            ("contention", suite.g_contention),
            ("final_invariants", suite.g_final),
        ):
            suite.run_group(name, function)

        cases = report["cases"]
        report["case_total"] = len(cases)  # type: ignore[arg-type]
        report["case_pass"] = sum(1 for item in cases if item["result"] == "pass")  # type: ignore[union-attr]
        report["case_fail"] = len(cases) - report["case_pass"]  # type: ignore[operator]
        if report["case_fail"] == 0 and not report["group_errors"]:
            report["exit_code"] = 0
    except BaseException as exc:
        error = exc
        report["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        contention_rows = report["concurrency_evidence"]
        report["session_cleanup"] = {
            "holders_exited": all(row.get("holder_process_exited") is True for row in contention_rows),
            "waiters_exited": all(row.get("waiter_process_exited") is True for row in contention_rows),
            "verified": all(row.get("holder_process_exited") is True
                            and row.get("waiter_process_exited") is True
                            and not row.get("cleanup_errors") for row in contention_rows),
        }  # type: ignore[union-attr]
        if not report["session_cleanup"]["verified"]:  # type: ignore[index]
            report["exit_code"] = 1
            report["session_cleanup_error"] = "one or more contention processes did not exit cleanly"
            if error is None:
                error = HarnessError(str(report["session_cleanup_error"]))
        try:
            removed = cleanup_owned_container(docker, container, run_id, container_id)
            report["cleanup"] = "verified_and_removed" if removed else "nothing_created"
        except BaseException as cleanup_error:
            report["cleanup"] = f"failed: {type(cleanup_error).__name__}: {cleanup_error}"
            report["exit_code"] = 1
            error = cleanup_error
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    summary = {key: report.get(key) for key in (
        "run_id", "revision", "tree", "case_total", "case_pass", "case_fail", "groups",
        "failed_cases", "group_errors", "success_path", "session_cleanup", "cleanup", "exit_code", "error")}
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if error:
        return 1
    return int(report["exit_code"])


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except HarnessError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
