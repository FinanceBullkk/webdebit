#!/usr/bin/env python3
"""PostgreSQL 18 acceptance fixture for app actor assertions and business revisions."""

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
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "cong-no-web-handoff" / "web"))

from actor_assertion import (
    AuthenticatedSession,
    revision_scope,
    sign_actor_assertion,
    submit_scope,
)
from test_pg_ledger_schema import (
    IMAGE,
    LABEL_RUN,
    LABEL_TEST,
    LABEL_VALUE,
    HarnessError,
    cleanup_owned_container,
    owned_container_id,
    run,
)


SCHEMA = ROOT / "cong-no-web-handoff" / "tools" / "pg_versioned_approval_fixture.sql"
ACTOR_ASSERTION = ROOT / "cong-no-web-handoff" / "web" / "actor_assertion.py"
DATABASE = "webdebit_ledger"
DB_LOGIN = "webdebit_app"
KEY_ID = "fixture-key-v1"
KEY = bytes.fromhex("11" * 32)
MAKER = uuid.UUID("11111111-1111-4111-8111-111111111111")
CHECKER = uuid.UUID("22222222-2222-4222-8222-222222222222")
DISABLED = uuid.UUID("33333333-3333-4333-8333-333333333333")
MAKER_ONLY = uuid.UUID("44444444-4444-4444-8444-444444444444")


def sql_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def make_payload(amount: int, *, source: str = "fixture-source-01", evidence: str = "fixture-evidence-01") -> str:
    first = amount // 2
    second = amount - first
    payload = {
        "schema_version": 1,
        "kind": "charge_fixture",
        "customer_id": "FAKE-CUSTOMER-1",
        "debt_period": "2026-01",
        "total_vnd": amount,
        "event_date": "2026-01-31",
        "posting_date": "2026-02-01",
        "source_ref": source,
        "evidence_ref": evidence,
        "evidence_sha256": "a" * 64,
        "reason": "fixture reason only",
        "lines": [
            {"line_no": 2, "customer_id": "FAKE-CUSTOMER-1",
             "debt_period": "2026-01", "amount_vnd": second},
            {"line_no": 1, "customer_id": "FAKE-CUSTOMER-1",
             "debt_period": "2026-01", "amount_vnd": first},
        ],
    }
    return json.dumps(payload, ensure_ascii=True, separators=(",", ":"))


class Fixture:
    def __init__(self, docker: list[str], container: str, run_id: str):
        self.docker = docker
        self.container = container
        self.run_id = run_id

    def psql(self, sql: str, *, user: str = "postgres", check: bool = True,
             database: str = DATABASE) -> subprocess.CompletedProcess[str]:
        return run(self.docker + ["exec", self.container, "psql", "-X", "-qAt",
            "-v", "ON_ERROR_STOP=1", "-v", "VERBOSITY=verbose", "-U", user,
            "-d", database, "-c", sql], check=check, timeout=30)

    def assertion(self, actor: uuid.UUID, action: str, scope: str,
                   *, session_id: uuid.UUID | None = None,
                   nonce: uuid.UUID | None = None,
                   issued_epoch: int | None = None):
        session = AuthenticatedSession(actor, session_id or uuid.uuid4())
        return session, sign_actor_assertion(session, action, scope,
            key_id=KEY_ID, key=KEY, nonce=nonce, issued_epoch=issued_epoch)

    @staticmethod
    def assertion_sql(session: AuthenticatedSession, assertion,
                      claimed_actor: uuid.UUID | None = None) -> str:
        return ", ".join((
            f"'{claimed_actor or session.actor_id}'::uuid", f"'{session.session_id}'::uuid",
            f"'{assertion.nonce}'::uuid", str(assertion.issued_epoch),
            sql_literal(assertion.key_id), sql_literal(assertion.signature),
        ))

    def submit(self, proposal_id: int | None, payload: str, actor: uuid.UUID = MAKER,
               *, session_id: uuid.UUID | None = None, nonce: uuid.UUID | None = None,
               signed_actor: uuid.UUID | None = None, scope_payload: str | None = None,
               issued_epoch: int | None = None, check: bool = True):
        signed_for = signed_actor or actor
        scope = submit_scope(proposal_id, scope_payload if scope_payload is not None else payload)
        session, assertion = self.assertion(signed_for, "submit", scope,
            session_id=session_id, nonce=nonce, issued_epoch=issued_epoch)
        args = self.assertion_sql(session, assertion, actor)
        query = (
            "SELECT row_to_json(x)::text FROM p0_fixture.submit_revision("
            f"{proposal_id if proposal_id is not None else 'NULL'}::bigint,"
            f"{sql_literal(payload)}::text,{args}) x"
        )
        return self.psql(query, user=DB_LOGIN, check=check), assertion, session

    def present(self, proposal_id: int, title: str, actor: uuid.UUID = MAKER):
        scope = f"presentation:{proposal_id}:{hashlib.sha256(title.encode()).hexdigest()}"
        session, assertion = self.assertion(actor, "presentation", scope)
        args = self.assertion_sql(session, assertion)
        return self.psql(
            "SELECT p0_fixture.set_presentation_title("
            f"{proposal_id}, {sql_literal(title)}, {args})",
            user=DB_LOGIN,
        )

    def decide(self, action: str, proposal_id: int, revision_id: int,
               content_hash: str, actor: uuid.UUID = CHECKER, *, check: bool = True,
               fail_post: bool = False):
        scope = revision_scope(action, proposal_id, revision_id, content_hash)
        session, assertion = self.assertion(actor, action, scope)
        args = self.assertion_sql(session, assertion)
        function = "approve_revision" if action == "approve" else "post_revision"
        query = (
            f"SELECT p0_fixture.{function}({proposal_id}, {revision_id}, "
            f"{sql_literal(content_hash)}, {args})"
        )
        if fail_post:
            query = ("BEGIN; SET LOCAL p0_fixture.fail_post = 'on'; "
                     + query + "; COMMIT")
        return self.psql(query, user=DB_LOGIN, check=check), session, assertion


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
        "fixture_sha256": hashlib.sha256(sql_bytes).hexdigest(),
        "fixture_path": str(SCHEMA),
        "runner_sha256": hashlib.sha256(Path(__file__).read_bytes().replace(b"\r\n", b"\n")).hexdigest(),
        "container_helper_sha256": hashlib.sha256(
            (SCHEMA.parent / "test_pg_ledger_schema.py").read_bytes().replace(b"\r\n", b"\n")
        ).hexdigest(),
        "actor_assertion_sha256": hashlib.sha256(ACTOR_ASSERTION.read_bytes().replace(b"\r\n", b"\n")).hexdigest(),
        "revision": run(["git", "-C", str(ROOT), "rev-parse", "HEAD"]).stdout.strip(),
        "network": "none",
        "published_ports": [],
        "volume_mounts": [],
        "cases": [],
        "runtime_checks": {
            "app_login_session": "not_implemented",
            "tailscale_boundary": "not_run",
            "receipt_verification_q09": "open_and_not_in_fixture",
        },
        "cleanup": "not_started",
        "exit_code": 1,
    }
    docker = ["docker"]
    container_id: str | None = None
    error: BaseException | None = None

    def case(name: str, expected, actual) -> None:
        passed = expected == actual
        record = {"name": name, "expected": expected, "actual": actual,
                  "result": "pass" if passed else "fail"}
        report["cases"].append(record)  # type: ignore[union-attr]
        if not passed:
            raise HarnessError(f"{name}: expected {expected!r}, got {actual!r}")

    def query(sql: str) -> str:
        return Fixture(docker, container, run_id).psql(sql).stdout.strip()

    def rejected(name: str, result: subprocess.CompletedProcess[str], expected_text: str) -> None:
        combined = result.stdout + result.stderr
        case(name, True, result.returncode != 0 and expected_text in combined)

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
            "-c", "CREATE ROLE webdebit_app LOGIN; GRANT p0_fixture_api TO webdebit_app"])
        case("fixture_schema_loads_on_postgresql_18_6", True, True)

        f = Fixture(docker, container, run_id)
        payload100 = make_payload(100, source="fixture-é-source", evidence="fixture-é-evidence")
        created, first_assertion, maker_session = f.submit(None, payload100)
        first = json.loads(created.stdout.strip())
        proposal_id = int(first["proposal_id"])
        revision1 = int(first["revision_id"])
        hash1 = first["content_sha256"]
        case("new_submit_creates_revision_1", (1, True),
             (int(first["revision_no"]), first["revision_created"]))
        case("revision_hash_has_sha256_shape", True, bool(re.fullmatch(r"[0-9a-f]{64}", hash1)))

        forged_payload_call, _, _ = f.submit(None, make_payload(333, source="forged-source-01"),
            actor=MAKER_ONLY, signed_actor=MAKER, check=False)
        rejected("client_cannot_replace_session_actor", forged_payload_call, "signature or scope mismatch")
        original_payload = make_payload(335, source="scope-source-01")
        altered_payload = make_payload(336, source="scope-source-01")
        changed_scope, _, _ = f.submit(None, altered_payload, scope_payload=original_payload, check=False)
        rejected("actor_assertion_is_bound_to_exact_request_payload", changed_scope, "signature or scope mismatch")
        old_epoch = int(time.time()) - 121
        expired_assertion, _, _ = f.submit(None, make_payload(337, source="expired-source-01"),
            issued_epoch=old_epoch, check=False)
        rejected("expired_actor_assertion_is_rejected", expired_assertion, "invalid actor assertion")

        inactive, _, _ = f.submit(None, make_payload(334, source="inactive-source-01"), actor=DISABLED, check=False)
        rejected("disabled_actor_is_rejected", inactive, "inactive actor")

        wrong_role_session, wrong_role_assertion = f.assertion(MAKER_ONLY, "approve",
            revision_scope("approve", proposal_id, revision1, hash1))
        wrong_role_args = f.assertion_sql(wrong_role_session, wrong_role_assertion)
        wrong_role = f.psql(
            f"SELECT p0_fixture.approve_revision({proposal_id},{revision1},"
            f"{sql_literal(hash1)},{wrong_role_args})", user=DB_LOGIN, check=False)
        rejected("actor_without_checker_role_is_rejected", wrong_role, "actor role required")

        # Canonical JSONB ignores object key order/whitespace; lines sort by line number, text stays exact.
        payload_obj = json.loads(payload100)
        payload_obj["lines"] = list(reversed(payload_obj["lines"]))
        reordered = json.dumps(dict(reversed(list(payload_obj.items()))), ensure_ascii=True, indent=2)
        noop, replayable_nonce_assertion, _ = f.submit(proposal_id, reordered, session_id=maker_session.session_id)
        noop_record = json.loads(noop.stdout.strip())
        case("equivalent_business_payload_is_noop", (revision1, hash1, False),
             (int(noop_record["revision_id"]), noop_record["content_sha256"], noop_record["revision_created"]))
        same_nonce_result, _, _ = f.submit(proposal_id, reordered,
            session_id=maker_session.session_id, nonce=replayable_nonce_assertion.nonce, check=False)
        rejected("successful_actor_assertion_nonce_cannot_be_replayed", same_nonce_result, "actor assertion replay")

        self_approval, _, _ = f.decide("approve", proposal_id, revision1, hash1, actor=MAKER, check=False)
        rejected("maker_cannot_approve_own_revision", self_approval, "self-approved revision")
        f.decide("approve", proposal_id, revision1, hash1)
        f.present(proposal_id, "Fixture presentation title")
        presentation_state = query(
            "SELECT p.state || '|' || p.current_revision_id || '|' || r.content_sha256 || '|' || "
            "(SELECT count(*) FROM p0_fixture.approval a WHERE a.revision_id=r.revision_id) "
            "FROM p0_fixture.proposal p JOIN p0_fixture.business_revision r "
            "ON r.revision_id=p.current_revision_id WHERE p.proposal_id=" + str(proposal_id))
        case("presentation_change_keeps_revision_and_approval", f"approved|{revision1}|{hash1}|1", presentation_state)

        changed_result, _, _ = f.submit(proposal_id, make_payload(101,
            source="fixture-é-source", evidence="fixture-é-evidence"), session_id=maker_session.session_id)
        changed = json.loads(changed_result.stdout.strip())
        revision2 = int(changed["revision_id"])
        hash2 = changed["content_sha256"]
        revision_current = revision2
        hash_current = hash2
        previous_hash = hash2
        case("business_change_creates_new_pending_revision", (2, True, "pending", 1),
             (int(changed["revision_no"]), changed["revision_created"],
              query(f"SELECT state FROM p0_fixture.proposal WHERE proposal_id={proposal_id}"),
              int(query(f"SELECT count(*) FROM p0_fixture.approval WHERE proposal_id={proposal_id}"))))
        stale, _, _ = f.decide("post", proposal_id, revision1, hash1, check=False)
        rejected("stale_approval_cannot_post_after_business_edit", stale, "current approved revision required")

        current_payload = json.loads(make_payload(101,
            source="fixture-é-source", evidence="fixture-é-evidence"))
        business_mutations = [
            ("source_ref", lambda p: p.__setitem__("source_ref", "fixture-e\u0301-source")),
            ("evidence_ref", lambda p: p.__setitem__("evidence_ref", "fixture-evidence-02")),
            ("evidence_hash", lambda p: p.__setitem__("evidence_sha256", "b" * 64)),
            ("customer_id", lambda p: (p.__setitem__("customer_id", "FAKE-CUSTOMER-2"),
                [line.__setitem__("customer_id", "FAKE-CUSTOMER-2") for line in p["lines"]])),
            ("debt_period", lambda p: (p.__setitem__("debt_period", "2026-02"),
                [line.__setitem__("debt_period", "2026-02") for line in p["lines"]])),
            ("event_date", lambda p: p.__setitem__("event_date", "2026-02-01")),
            ("posting_date", lambda p: p.__setitem__("posting_date", "2026-02-02")),
            ("reason", lambda p: p.__setitem__("reason", "fixture reason revised")),
            ("line_amounts", lambda p: (p["lines"][0].__setitem__("amount_vnd", p["lines"][0]["amount_vnd"] + 1),
                p["lines"][1].__setitem__("amount_vnd", p["lines"][1]["amount_vnd"] - 1))),
            ("line_number", lambda p: next(line for line in p["lines"] if line["line_no"] == 1).__setitem__("line_no", 3)),
            ("total_vnd", lambda p: (p.__setitem__("total_vnd", p["total_vnd"] + 1),
                p["lines"][0].__setitem__("amount_vnd", p["lines"][0]["amount_vnd"] + 1))),
        ]
        for expected_no, (field_name, mutate) in enumerate(business_mutations, start=3):
            mutate(current_payload)
            current_text = json.dumps(current_payload, ensure_ascii=True, separators=(",", ":"))
            updated_result, _, _ = f.submit(proposal_id, current_text,
                session_id=maker_session.session_id)
            updated = json.loads(updated_result.stdout.strip())
            revision_current = int(updated["revision_id"])
            hash_current = updated["content_sha256"]
            case(f"business_field_{field_name}_creates_revision", (expected_no, True),
                 (int(updated["revision_no"]), updated["revision_created"]))
            case(f"business_field_{field_name}_changes_hash", True, hash_current != previous_hash)
            previous_hash = hash_current

        # Unknown and fractional business values are rejected instead of omitted or rounded.
        unknown_obj = json.loads(make_payload(102, source="unknown-source-01"))
        unknown_obj["unhashed_extra"] = "must not disappear"
        unknown_payload = json.dumps(unknown_obj, separators=(",", ":"))
        unknown, _, _ = f.submit(None, unknown_payload, check=False)
        rejected("unknown_business_field_fails_closed", unknown, "missing or unknown business fields")
        fractional_obj = json.loads(make_payload(103, source="fractional-source-01"))
        fractional_obj["total_vnd"] = 103.5
        fractional_obj["lines"][0]["amount_vnd"] = 103.5
        fractional, _, _ = f.submit(None, json.dumps(fractional_obj, separators=(",", ":")), check=False)
        rejected("fractional_vnd_is_rejected", fractional, "positive integer")

        sum_obj = json.loads(make_payload(104, source="sum-source-01"))
        sum_obj["lines"][0]["amount_vnd"] = 105
        bad_sum, _, _ = f.submit(None, json.dumps(sum_obj, separators=(",", ":")), check=False)
        rejected("line_total_must_match_document_total", bad_sum, "line sum differs from total")

        missing_evidence_obj = json.loads(make_payload(104, source="missing-evidence-01"))
        del missing_evidence_obj["evidence_ref"]
        missing_evidence, _, _ = f.submit(None,
            json.dumps(missing_evidence_obj, separators=(",", ":")), check=False)
        rejected("missing_evidence_reference_fails_closed", missing_evidence,
            "missing or unknown business fields")
        malformed_evidence_obj = json.loads(make_payload(104, source="malformed-evidence-01"))
        malformed_evidence_obj["evidence_sha256"] = "not-a-sha256"
        malformed_evidence, _, _ = f.submit(None,
            json.dumps(malformed_evidence_obj, separators=(",", ":")), check=False)
        rejected("malformed_evidence_hash_fails_closed", malformed_evidence,
            "invalid fixture payload fields")

        receipt_obj = json.loads(make_payload(105, source="receipt-not-enabled-01"))
        receipt_obj["kind"] = "receipt"
        receipt, _, _ = f.submit(None, json.dumps(receipt_obj, separators=(",", ":")), check=False)
        rejected("receipt_path_is_not_enabled_while_q09_is_open", receipt, "invalid fixture payload fields")

        wrong_scope_session, wrong_scope_assertion = f.assertion(CHECKER, "approve",
            revision_scope("approve", proposal_id, revision1, hash1))
        wrong_scope_args = f.assertion_sql(wrong_scope_session, wrong_scope_assertion)
        wrong_scope_result = f.psql(
            f"SELECT p0_fixture.approve_revision({proposal_id},{revision_current},"
            f"{sql_literal(hash_current)},{wrong_scope_args})", user=DB_LOGIN, check=False)
        rejected("actor_assertion_cannot_be_reused_for_another_revision_scope",
            wrong_scope_result, "signature or scope mismatch")

        f.decide("approve", proposal_id, revision_current, hash_current)
        f.present(proposal_id, "Presentation edit after approval")
        failed_post, _, _ = f.decide("post", proposal_id, revision_current, hash_current, fail_post=True, check=False)
        rejected("late_post_failure_rolls_back_statement", failed_post, "injected deferred fixture failure")
        after_failed_post = query(
            "SELECT p.state || '|' || (SELECT count(*) FROM p0_fixture.posting x "
            f"WHERE x.proposal_id=p.proposal_id) || '|' || (SELECT count(*) FROM p0_fixture.audit a "
            f"WHERE a.proposal_id=p.proposal_id AND a.action='post') FROM p0_fixture.proposal p WHERE p.proposal_id={proposal_id}")
        case("failed_post_leaves_approved_revision_unchanged", "approved|0|0", after_failed_post)
        f.decide("post", proposal_id, revision_current, hash_current)
        posted = json.loads(query(
            "SELECT row_to_json(x)::text FROM p0_fixture.posting x "
            f"WHERE x.proposal_id={proposal_id}"))
        case("posting_uses_approved_revision_payload_and_hash", True,
             posted["revision_id"] == revision_current and posted["content_sha256"] == hash_current
             and posted["canonical_payload"]["total_vnd"] == current_payload["total_vnd"]
             and posted["maker_actor_id"] == str(MAKER)
             and posted["checker_actor_id"] == str(CHECKER)
             and posted["database_session_user"] == DB_LOGIN)
        approval_link = query(
            "SELECT count(*) FROM p0_fixture.approval a "
            f"WHERE a.approval_id={posted['approval_id']} AND a.revision_id={revision_current} "
            f"AND a.content_sha256='{hash_current}' AND a.checker_actor_id='{CHECKER}'::uuid")
        case("posting_references_its_exact_approval_event", 1, int(approval_link))
        duplicate_post, _, _ = f.decide("post", proposal_id, revision_current, hash_current, check=False)
        rejected("already_posted_revision_cannot_post_twice", duplicate_post, "current approved revision required")

        audit_mapping = query(
            "SELECT count(*) FROM p0_fixture.audit a WHERE a.proposal_id=" + str(proposal_id)
            + f" AND a.app_actor_id='{MAKER}'::uuid AND a.database_session_user='{DB_LOGIN}'"
            + " AND a.key_id='fixture-key-v1' AND EXISTS (SELECT 1 FROM p0_fixture.used_assertion_nonce n"
            + " WHERE n.nonce=a.assertion_nonce AND n.actor_id=a.app_actor_id AND n.session_id=a.app_session_id)")
        case("audit_separates_app_actor_from_database_service_login", True, int(audit_mapping) > 0)
        direct_read = f.psql("SELECT * FROM p0_fixture.business_revision", user=DB_LOGIN, check=False)
        rejected("api_role_cannot_read_revision_table_directly", direct_read, "permission denied")
        direct_update = f.psql(
            "UPDATE p0_fixture.proposal SET state='pending'", user=DB_LOGIN, check=False)
        rejected("api_role_cannot_update_proposal_table_directly", direct_update, "permission denied")
        direct_key_read = f.psql("SELECT secret FROM p0_fixture.actor_signing_key",
            user=DB_LOGIN, check=False)
        rejected("api_role_cannot_read_actor_signing_key", direct_key_read, "permission denied")

        final_state = query(
            f"SELECT state || '|' || (SELECT count(*) FROM p0_fixture.posting WHERE proposal_id={proposal_id}) "
            f"|| '|' || (SELECT count(*) FROM p0_fixture.business_revision WHERE proposal_id={proposal_id}) "
            f"|| '|' || (SELECT count(*) FROM p0_fixture.approval WHERE proposal_id={proposal_id}) "
            f"FROM p0_fixture.proposal WHERE proposal_id={proposal_id}")
        case("revision_approval_posting_history_is_append_only", "posted|1|13|2", final_state)

        # The PostgreSQL test admin verifies append-only triggers after the app-role checks.
        immutability = f.psql(
            f"UPDATE p0_fixture.business_revision SET content_sha256='{hash1}' WHERE revision_id={revision1}",
            check=False)
        rejected("revision_update_trigger_rejects_mutation", immutability, "append-only fixture row")
        deletion = f.psql(
            f"DELETE FROM p0_fixture.business_revision WHERE revision_id={revision1}", check=False)
        rejected("revision_delete_trigger_rejects_mutation", deletion, "append-only fixture row")
        approval_id = int(query(f"SELECT approval_id FROM p0_fixture.approval WHERE revision_id={revision_current}"))
        approval_mutation = f.psql(
            f"UPDATE p0_fixture.approval SET content_sha256='{hash1}' WHERE approval_id={approval_id}", check=False)
        rejected("approval_update_trigger_rejects_mutation", approval_mutation, "append-only fixture row")
        posting_id = int(query(f"SELECT posting_id FROM p0_fixture.posting WHERE proposal_id={proposal_id}"))
        posting_mutation = f.psql(
            f"UPDATE p0_fixture.posting SET content_sha256='{hash1}' WHERE posting_id={posting_id}", check=False)
        rejected("posting_update_trigger_rejects_mutation", posting_mutation, "append-only fixture row")
        audit_id = int(query(f"SELECT audit_id FROM p0_fixture.audit WHERE proposal_id={proposal_id} ORDER BY audit_id DESC LIMIT 1"))
        audit_deletion = f.psql(f"DELETE FROM p0_fixture.audit WHERE audit_id={audit_id}", check=False)
        rejected("audit_delete_trigger_rejects_mutation", audit_deletion, "append-only fixture row")
        report["exit_code"] = 0
    except BaseException as exc:
        error = exc
        report["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        try:
            removed = cleanup_owned_container(docker, container, run_id, container_id)
            report["cleanup"] = "verified_and_removed" if removed else "nothing_created"
        except BaseException as cleanup_error:
            report["cleanup"] = f"failed: {type(cleanup_error).__name__}: {cleanup_error}"
            report["exit_code"] = 1
            error = cleanup_error
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(json.dumps(report, ensure_ascii=False, indent=2))
    if error:
        return 1
    return int(report["exit_code"])


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except HarnessError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
