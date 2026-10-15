#!/usr/bin/env python3
"""PostgreSQL 18 acceptance fixture for app actor assertions and business revisions."""

from __future__ import annotations

import argparse
import hashlib
import hmac
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
IDENTITY_LOGIN = "webdebit_identity_test_app"
CHARGE_LOGIN = "webdebit_app"
KEY_ID = "fixture-key-v1"
KEY = bytes.fromhex("11" * 32)
MAKER = uuid.UUID("11111111-1111-4111-8111-111111111111")
CHECKER = uuid.UUID("22222222-2222-4222-8222-222222222222")
DISABLED = uuid.UUID("33333333-3333-4333-8333-333333333333")
MAKER_ONLY = uuid.UUID("44444444-4444-4444-8444-444444444444")
PRICE_OWNER = uuid.UUID("55555555-5555-4555-8555-555555555555")


def sql_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def legacy_signature(session: AuthenticatedSession, action: str | None, nonce: uuid.UUID,
                     issued_epoch: int | None, scope: str) -> str:
    fields = (
        "webdebit-actor-assertion-v1", str(session.actor_id), str(session.session_id),
        action, str(nonce), None if issued_epoch is None else str(issued_epoch), scope,
    )
    message = "\n".join(field for field in fields if field is not None).encode("utf-8")
    return hmac.new(KEY, message, hashlib.sha256).hexdigest()


def make_payload(amount: int, *, source: str = "fixture-source-01",
                 evidence: str = "fixture-evidence-01",
                 kind: str = "revision_fixture") -> str:
    first = amount // 2
    second = amount - first
    payload = {
        "schema_version": 2,
        "kind": kind,
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


def make_charge_payload(*, trip_code: str | None = None, period: str = "2026-09",
                        event_date: str = "2026-10-14",
                        opening_refs: bool = False, amount: int = 100) -> str:
    payload = {
        "schema_version": 2,
        "kind": "charge_fixture",
        "customer_id": "FAKE-CUSTOMER-1",
        "debt_period": period,
        "total_vnd": amount,
        "event_date": event_date,
        "posting_date": "2026-10-15",
        "source_ref": "fixture-source-reference-only",
        "evidence_ref": "fixture-evidence-reference-only",
        "evidence_sha256": "a" * 64,
        "reason": "fixture reason only",
        "lines": [
            {"line_no": 1, "customer_id": "FAKE-CUSTOMER-1",
             "debt_period": period, "amount_vnd": amount},
        ],
        "trip_code": trip_code,
        "opening_snapshot_ref": "fixture-opening-snapshot" if opening_refs else None,
        "opening_absence_evidence_ref": "fixture-absence-check" if opening_refs else None,
        "price_components": [
            {"label": "per-trip component A", "amount_vnd": amount // 2},
            {"label": "per-trip component B", "amount_vnd": amount - amount // 2},
        ],
    }
    return json.dumps(payload, ensure_ascii=True, separators=(",", ":"))


class Fixture:
    def __init__(self, docker: list[str], container: str, run_id: str,
                 db_user: str = IDENTITY_LOGIN):
        self.docker = docker
        self.container = container
        self.run_id = run_id
        self.db_user = db_user

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
               issued_epoch: int | None = None, user: str | None = None,
               check: bool = True, date_style: str | None = None):
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
        if date_style is not None:
            if date_style not in {"SQL, DMY", "SQL, MDY"}:
                raise ValueError("unsupported fixture DateStyle")
            query = f"SET DateStyle TO '{date_style}'; " + query
        return self.psql(query, user=user or self.db_user, check=check), assertion, session

    def present(self, proposal_id: int, title: str, actor: uuid.UUID = MAKER,
                *, user: str | None = None, check: bool = True):
        scope = f"presentation:{proposal_id}:{hashlib.sha256(title.encode()).hexdigest()}"
        session, assertion = self.assertion(actor, "presentation", scope)
        args = self.assertion_sql(session, assertion)
        return self.psql(
            "SELECT p0_fixture.set_presentation_title("
            f"{proposal_id}, {sql_literal(title)}, {args})",
            user=user or self.db_user,
            check=check,
        )

    def confirm(self, action: str, function: str, proposal_id: int,
                revision_id: int, content_hash: str, actor: uuid.UUID,
                *, user: str | None = None, check: bool = True):
        scope = f"{action}:{proposal_id}:{revision_id}:{content_hash}"
        session, assertion = self.assertion(actor, action, scope)
        args = self.assertion_sql(session, assertion)
        return self.psql(
            f"SELECT p0_fixture.{function}({proposal_id}, {revision_id}, "
            f"{sql_literal(content_hash)}, {args})",
            user=user or self.db_user,
            check=check,
        )

    def confirm_price(self, proposal_id: int, revision_id: int, content_hash: str,
                      actor: uuid.UUID = PRICE_OWNER, *, user: str | None = None,
                      check: bool = True):
        return self.confirm("confirm_price", "confirm_price_revision",
            proposal_id, revision_id, content_hash, actor, user=user, check=check)

    def confirm_period(self, proposal_id: int, revision_id: int, content_hash: str,
                       actor: uuid.UUID = MAKER, *, user: str | None = None,
                       check: bool = True):
        return self.confirm("confirm_period", "confirm_period_revision",
            proposal_id, revision_id, content_hash, actor, user=user, check=check)

    def decide(self, action: str, proposal_id: int, revision_id: int,
               content_hash: str, actor: uuid.UUID = CHECKER, *, check: bool = True,
               fail_post: bool = False, user: str | None = None):
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
        return self.psql(query, user=user or self.db_user, check=check), session, assertion


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
        "draft_matrix": [],
        "runtime_checks": {
            "app_login_session": "not_implemented",
            "tailscale_boundary": "not_run",
            "receipt_verification_q09": "open_and_not_in_fixture",
        },
        "cleanup": "not_started",
        "exit_code": 1,
    }
    report["tree"] = run(["git", "-C", str(ROOT), "rev-parse", "HEAD^{tree}"]).stdout.strip()
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

    def proposal_snapshot(proposal_id: int) -> str:
        return query(
            "SELECT jsonb_build_object("
            "'kind', p.kind, 'state', p.state, 'revision_no', p.revision_no, "
            "'current_revision_id', p.current_revision_id, 'content_sha256', r.content_sha256, "
            "'revision_count', (SELECT count(*) FROM p0_fixture.business_revision x "
            "WHERE x.proposal_id=p.proposal_id), "
            "'revision_history', (SELECT coalesce(jsonb_agg(jsonb_build_array("
            "x.revision_id, x.revision_no, x.canonical_payload, x.content_sha256, "
            "x.review_reason_codes) ORDER BY x.revision_no), '[]'::jsonb) "
            "FROM p0_fixture.business_revision x WHERE x.proposal_id=p.proposal_id), "
            "'approval_history', (SELECT coalesce(jsonb_agg(jsonb_build_array("
            "a.approval_id, a.revision_id, a.content_sha256, a.checker_actor_id, a.approved_at) "
            "ORDER BY a.approval_id), '[]'::jsonb) FROM p0_fixture.approval a "
            "WHERE a.proposal_id=p.proposal_id), "
            "'posting_count', (SELECT count(*) FROM p0_fixture.posting x "
            "WHERE x.proposal_id=p.proposal_id), "
            "'period_confirmation_history', (SELECT coalesce(jsonb_agg(jsonb_build_array("
            "x.confirmation_id, x.revision_id, x.content_sha256, x.maker_actor_id) "
            "ORDER BY x.revision_id), '[]'::jsonb) FROM p0_fixture.period_confirmation x "
            "WHERE x.proposal_id=p.proposal_id), "
            "'price_confirmation_history', (SELECT coalesce(jsonb_agg(jsonb_build_array("
            "x.confirmation_id, x.revision_id, x.content_sha256, x.owner_actor_id) "
            "ORDER BY x.revision_id), '[]'::jsonb) FROM p0_fixture.price_confirmation x "
            "WHERE x.proposal_id=p.proposal_id), "
            "'audit_count', (SELECT count(*) FROM p0_fixture.audit x "
            "WHERE x.proposal_id=p.proposal_id))::text "
            "FROM p0_fixture.proposal p JOIN p0_fixture.business_revision r "
            "ON r.revision_id=p.current_revision_id "
            f"WHERE p.proposal_id={proposal_id}"
        )

    def review_projection(proposal_id: int) -> dict[str, object]:
        return json.loads(query(
            "SELECT p0_fixture.fixture_review_projection(" + str(proposal_id) + ")::text"
        ))

    def legacy_signature_matches(session: AuthenticatedSession, action: str | None,
                                 nonce: uuid.UUID, issued_epoch: int | None,
                                 scope: str, signature: str) -> bool:
        fields = (
            sql_literal("webdebit-actor-assertion-v1"),
            f"{sql_literal(str(session.actor_id))}::text",
            f"{sql_literal(str(session.session_id))}::text",
            "NULL::text" if action is None else sql_literal(action),
            f"{sql_literal(str(nonce))}::text",
            "NULL::text" if issued_epoch is None else sql_literal(str(issued_epoch)),
            sql_literal(scope),
        )
        sql = (
            "SELECT (encode(public.hmac(convert_to(concat_ws(E'\\n', "
            + ", ".join(fields)
            + "), 'UTF8'), k.secret, 'sha256'), 'hex') = "
            + sql_literal(signature)
            + ")::text FROM p0_fixture.actor_signing_key k WHERE k.key_id='fixture-key-v1'"
        )
        return query(sql) in {"true", "t"}

    def rejected(name: str, result: subprocess.CompletedProcess[str], expected_text: str) -> None:
        if isinstance(result, tuple):
            result = result[0]
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
            "-c", "CREATE ROLE webdebit_identity_test_app LOGIN; "
                  "GRANT p0_fixture_identity_test_api TO webdebit_identity_test_app; "
                  "CREATE ROLE webdebit_app LOGIN; GRANT p0_fixture_api TO webdebit_app"])
        case("fixture_schema_loads_on_postgresql_18_6", True, True)

        f = Fixture(docker, container, run_id)
        charge = Fixture(docker, container, run_id, db_user=CHARGE_LOGIN)

        def pending_charge(name: str, payload: dict[str, object], expected_codes: list[str],
                           approval_gate: str) -> tuple[int, int, str]:
            result, _, _ = charge.submit(None,
                json.dumps(payload, ensure_ascii=True, separators=(",", ":")))
            created = json.loads(result.stdout.strip())
            proposal_id = int(created["proposal_id"])
            revision_id = int(created["revision_id"])
            content_hash = str(created["content_sha256"])
            saved = review_projection(proposal_id)
            revision = saved["revisions"][-1]
            case(f"{name}_visible_after_commit", (revision_id, content_hash, 1),
                 (int(revision["revision_id"]), revision["content_sha256"],
                  len(saved["revisions"])))
            case(f"{name}_committed_review_needed", "review_needed", saved["state"])
            case(f"{name}_reason_codes", sorted(expected_codes), revision["reason_codes"])

            charge.confirm_period(proposal_id, revision_id, content_hash)
            charge.confirm_price(proposal_id, revision_id, content_hash)
            before_refusal = proposal_snapshot(proposal_id)
            approval, _, _ = charge.decide("approve", proposal_id, revision_id,
                content_hash, check=False)
            rejected(f"{name}_approval_refused", approval, approval_gate)
            posting, _, _ = charge.decide("post", proposal_id, revision_id,
                content_hash, check=False)
            rejected(f"{name}_posting_refused", posting,
                "current approved revision required for posting")
            case(f"{name}_refusal_preserves_revision_history", before_refusal,
                 proposal_snapshot(proposal_id))
            report["draft_matrix"].append({
                "case": name,
                "revision_id": revision_id,
                "content_sha256": content_hash,
                "reason_codes": revision["reason_codes"],
                "state": saved["state"],
                "approval_refused": approval.returncode != 0,
                "posting_refused": posting.returncode != 0,
            })  # type: ignore[union-attr]
            return proposal_id, revision_id, content_hash

        case("fixture_logins_have_disjoint_kind_roles", "yes|yes", query(
            "SELECT CASE WHEN pg_has_role('webdebit_app', 'p0_fixture_api', 'member') "
            "AND NOT pg_has_role('webdebit_app', 'p0_fixture_identity_test_api', 'member') "
            "THEN 'yes' ELSE 'no' END || '|' || "
            "CASE WHEN pg_has_role('webdebit_identity_test_app', 'p0_fixture_identity_test_api', 'member') "
            "AND NOT pg_has_role('webdebit_identity_test_app', 'p0_fixture_api', 'member') "
            "THEN 'yes' ELSE 'no' END"))
        case("fixture_api_roles_are_nologin", "p0_fixture_api:nologin|p0_fixture_identity_test_api:nologin",
            query("SELECT string_agg(rolname || ':' || CASE WHEN rolcanlogin THEN 'login' ELSE 'nologin' END, '|' ORDER BY rolname) "
                  "FROM pg_roles WHERE rolname IN ('p0_fixture_api', 'p0_fixture_identity_test_api')"))
        case("fixture_logins_have_only_api_function_grants", "6|6", query(
            "SELECT count(*) FILTER (WHERE has_function_privilege('webdebit_identity_test_app', p.oid, 'EXECUTE'))::text "
            "|| '|' || count(*) FILTER (WHERE has_function_privilege('webdebit_app', p.oid, 'EXECUTE'))::text "
            "FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='p0_fixture'"))
        case("fixture_logins_have_no_direct_table_privileges", "yes", query(
            "SELECT CASE WHEN bool_and("
            "NOT has_table_privilege('webdebit_identity_test_app', c.oid, 'SELECT') "
            "AND NOT has_table_privilege('webdebit_identity_test_app', c.oid, 'INSERT') "
            "AND NOT has_table_privilege('webdebit_identity_test_app', c.oid, 'UPDATE') "
            "AND NOT has_table_privilege('webdebit_identity_test_app', c.oid, 'DELETE') "
            "AND NOT has_table_privilege('webdebit_app', c.oid, 'SELECT') "
            "AND NOT has_table_privilege('webdebit_app', c.oid, 'INSERT') "
            "AND NOT has_table_privilege('webdebit_app', c.oid, 'UPDATE') "
            "AND NOT has_table_privilege('webdebit_app', c.oid, 'DELETE')) "
            "THEN 'yes' ELSE 'no' END FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
            "WHERE n.nspname='p0_fixture' AND c.relkind IN ('r','p','v','m','f')"))
        case("fixture_logins_have_no_direct_sequence_privileges", "yes", query(
            "SELECT CASE WHEN bool_and("
            "NOT has_sequence_privilege('webdebit_identity_test_app', c.oid, 'USAGE') "
            "AND NOT has_sequence_privilege('webdebit_identity_test_app', c.oid, 'SELECT') "
            "AND NOT has_sequence_privilege('webdebit_identity_test_app', c.oid, 'UPDATE') "
            "AND NOT has_sequence_privilege('webdebit_app', c.oid, 'USAGE') "
            "AND NOT has_sequence_privilege('webdebit_app', c.oid, 'SELECT') "
            "AND NOT has_sequence_privilege('webdebit_app', c.oid, 'UPDATE')) "
            "THEN 'yes' ELSE 'no' END FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
            "WHERE n.nspname='p0_fixture' AND c.relkind='S'"))

        # V2 canonicalization is independent of DateStyle and JSON numeric scale.
        date_payload = make_payload(100, source="fixture-date-style-source")
        dmy_result, _, _ = f.submit(None, date_payload, date_style="SQL, DMY")
        mdy_result, _, _ = f.submit(None, date_payload, date_style="SQL, MDY")
        dmy_revision = json.loads(dmy_result.stdout.strip())
        mdy_revision = json.loads(mdy_result.stdout.strip())
        case("date_style_dmy_and_mdy_have_same_v2_hash",
            dmy_revision["content_sha256"], mdy_revision["content_sha256"])
        case("date_style_dmy_and_mdy_have_same_canonical_payload",
            query("SELECT canonical_payload::text FROM p0_fixture.business_revision "
                f"WHERE revision_id={dmy_revision['revision_id']}"),
            query("SELECT canonical_payload::text FROM p0_fixture.business_revision "
                f"WHERE revision_id={mdy_revision['revision_id']}"))
        case("canonical_payload_uses_schema_version_2", "2",
            query("SELECT canonical_payload->>'schema_version' FROM p0_fixture.business_revision "
                f"WHERE revision_id={dmy_revision['revision_id']}"))
        case("stored_hash_uses_v2_domain_and_canonical_bytes",
            dmy_revision["content_sha256"], query(
                "SELECT encode(public.digest(convert_to('webdebit.business-payload.v2' || E'\\n' "
                "|| canonical_payload::text, 'UTF8'), 'sha256'), 'hex') "
                "FROM p0_fixture.business_revision "
                f"WHERE revision_id={dmy_revision['revision_id']}"))
        case("pure_canonical_functions_are_immutable",
            "canonical_vnd:i|canonicalize_payload:i|parse_iso_date:i", query(
                "SELECT string_agg(p.proname || ':' || p.provolatile::text, '|' ORDER BY p.proname) "
                "FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace "
                "WHERE n.nspname='p0_fixture' "
                "AND p.proname IN ('canonical_vnd','canonicalize_payload','parse_iso_date')"))

        integer_payload = make_payload(100, source="fixture-numeric-scale-source")
        decimal_one_payload = (integer_payload.replace('"total_vnd":100', '"total_vnd":100.0')
            .replace('"amount_vnd":50', '"amount_vnd":50.00'))
        decimal_payload = (integer_payload.replace('"total_vnd":100', '"total_vnd":100.00')
            .replace('"amount_vnd":50', '"amount_vnd":50.0'))
        integer_result, _, _ = f.submit(None, integer_payload)
        decimal_one_result, _, _ = f.submit(None, decimal_one_payload)
        decimal_result, _, _ = f.submit(None, decimal_payload)
        integer_revision = json.loads(integer_result.stdout.strip())
        decimal_one_revision = json.loads(decimal_one_result.stdout.strip())
        decimal_revision = json.loads(decimal_result.stdout.strip())
        integer_canonical = query("SELECT canonical_payload::text FROM p0_fixture.business_revision "
            f"WHERE revision_id={integer_revision['revision_id']}")
        decimal_one_canonical = query("SELECT canonical_payload::text FROM p0_fixture.business_revision "
            f"WHERE revision_id={decimal_one_revision['revision_id']}")
        decimal_canonical = query("SELECT canonical_payload::text FROM p0_fixture.business_revision "
            f"WHERE revision_id={decimal_revision['revision_id']}")
        case("vnd_100_100_0_100_00_have_same_canonical_payload",
            f"{integer_canonical}|{integer_canonical}",
            f"{decimal_one_canonical}|{decimal_canonical}")
        case("vnd_100_100_0_100_00_have_same_business_hash",
            f"{integer_revision['content_sha256']}|{integer_revision['content_sha256']}",
            f"{decimal_one_revision['content_sha256']}|{decimal_revision['content_sha256']}")

        integer_charge = make_charge_payload(amount=100)
        decimal_one_charge = (integer_charge.replace('"total_vnd":100', '"total_vnd":100.0')
            .replace('"amount_vnd":100', '"amount_vnd":100.00')
            .replace('"amount_vnd":50', '"amount_vnd":50.0'))
        decimal_charge = (integer_charge.replace('"total_vnd":100', '"total_vnd":100.00')
            .replace('"amount_vnd":100', '"amount_vnd":100.0')
            .replace('"amount_vnd":50', '"amount_vnd":50.00'))
        integer_charge_result, _, _ = charge.submit(None, integer_charge)
        decimal_one_charge_result, _, _ = charge.submit(None, decimal_one_charge)
        decimal_charge_result, _, _ = charge.submit(None, decimal_charge)
        integer_charge_revision = json.loads(integer_charge_result.stdout.strip())
        decimal_one_charge_revision = json.loads(decimal_one_charge_result.stdout.strip())
        decimal_charge_revision = json.loads(decimal_charge_result.stdout.strip())
        integer_charge_canonical = query("SELECT canonical_payload::text FROM p0_fixture.business_revision "
            f"WHERE revision_id={integer_charge_revision['revision_id']}")
        decimal_one_charge_canonical = query("SELECT canonical_payload::text FROM p0_fixture.business_revision "
            f"WHERE revision_id={decimal_one_charge_revision['revision_id']}")
        decimal_charge_canonical = query("SELECT canonical_payload::text FROM p0_fixture.business_revision "
            f"WHERE revision_id={decimal_charge_revision['revision_id']}")
        case("charge_vnd_spellings_100_100_0_100_00_have_same_canonical_payload",
            f"{integer_charge_canonical}|{integer_charge_canonical}",
            f"{decimal_one_charge_canonical}|{decimal_charge_canonical}")
        case("charge_vnd_spellings_100_100_0_100_00_have_same_business_hash",
            f"{integer_charge_revision['content_sha256']}|{integer_charge_revision['content_sha256']}",
            f"{decimal_one_charge_revision['content_sha256']}|{decimal_charge_revision['content_sha256']}")
        case("canonical_price_component_has_v2_exact_integer",
            "50", query("SELECT canonical_payload->'price_components'->0->>'amount_vnd' "
                "FROM p0_fixture.business_revision "
                f"WHERE revision_id={decimal_charge_revision['revision_id']}"))
        large_amount = 18446744073709551617
        large_result, _, _ = f.submit(None, make_payload(large_amount,
            source="fixture-large-exact-vnd-source"))
        large_revision = json.loads(large_result.stdout.strip())
        large_values = query(
            "SELECT canonical_payload->>'total_vnd' || '|' || "
            "(SELECT string_agg(line->>'amount_vnd', '|' ORDER BY (line->>'line_no')::integer) "
            "FROM jsonb_array_elements(canonical_payload->'lines') AS x(line)) "
            "FROM p0_fixture.business_revision "
            f"WHERE revision_id={large_revision['revision_id']}")
        case("vnd_above_bigint_remains_exact_in_total_and_lines",
            "18446744073709551617|9223372036854775808|9223372036854775809", large_values)
        large_charge_amount = 36893488147419103234
        large_charge_result, _, _ = charge.submit(None,
            make_charge_payload(amount=large_charge_amount))
        large_charge_revision = json.loads(large_charge_result.stdout.strip())
        large_charge_values = query(
            "SELECT canonical_payload->>'total_vnd' || '|' || "
            "(canonical_payload->'lines'->0->>'amount_vnd') || '|' || "
            "(SELECT string_agg(component->>'amount_vnd', '|' ORDER BY ordinality) "
            "FROM jsonb_array_elements(canonical_payload->'price_components') "
            "WITH ORDINALITY AS x(component, ordinality)) "
            "FROM p0_fixture.business_revision "
            f"WHERE revision_id={large_charge_revision['revision_id']}")
        case("vnd_above_bigint_remains_exact_in_charge_total_line_and_components",
            "36893488147419103234|36893488147419103234|18446744073709551617|18446744073709551617",
            large_charge_values)

        old_version_payload = integer_payload.replace('"schema_version":2', '"schema_version":1')
        old_version, _, _ = f.submit(None, old_version_payload, check=False)
        rejected("schema_version_1_is_explicitly_rejected", old_version,
            "schema version 1 is unsupported; expected version 2")

        null_money = integer_payload.replace('"total_vnd":100', '"total_vnd":null')
        null_money_result, _, _ = f.submit(None, null_money, check=False)
        rejected("null_money_is_rejected_as_non_numeric", null_money_result,
            "fixture VND value must be a JSON number")
        zero_money = integer_payload.replace('"total_vnd":100', '"total_vnd":0')
        zero_money_result, _, _ = f.submit(None, zero_money, check=False)
        rejected("zero_money_remains_rejected_by_strict_fixture", zero_money_result,
            "fixture amount must be a positive integer")
        case("null_money_is_not_coerced_to_zero", True,
            "fixture VND value must be a JSON number" in null_money_result.stdout + null_money_result.stderr
            and "fixture amount must be a positive integer" in zero_money_result.stdout + zero_money_result.stderr)
        negative_money = integer_payload.replace('"total_vnd":100', '"total_vnd":-100')
        negative_money_result, _, _ = f.submit(None, negative_money, check=False)
        rejected("negative_money_is_rejected", negative_money_result,
            "fixture amount must be a positive integer")
        for field, bad_value, marker in (
            ("line_zero", '"amount_vnd":0', '"amount_vnd":50'),
            ("line_negative", '"amount_vnd":-50', '"amount_vnd":50'),
            ("line_fractional", '"amount_vnd":50.5', '"amount_vnd":50'),
            ("line_null", '"amount_vnd":null', '"amount_vnd":50'),
        ):
            bad_line_payload = integer_payload.replace(marker, bad_value, 1)
            bad_line_result, _, _ = f.submit(None, bad_line_payload, check=False)
            rejected(f"{field}_money_is_rejected", bad_line_result,
                "fixture VND value must be a JSON number" if field == "line_null"
                else "fixture amount must be a positive integer")
        for field, bad_value in (
            ("component_negative", '"amount_vnd":-50'),
            ("component_fractional", '"amount_vnd":50.5'),
        ):
            bad_component_payload = make_charge_payload().replace(
                '"amount_vnd":50', bad_value, 1)
            bad_component_result, _, _ = charge.submit(None, bad_component_payload, check=False)
            rejected(f"{field}_money_is_rejected", bad_component_result,
                "fixture amount must be a nonnegative integer")
        zero_component = json.loads(make_charge_payload())
        zero_component["price_components"][0]["amount_vnd"] = 0
        zero_component["price_components"][1]["amount_vnd"] = 100
        pending_charge("zero_component_persists_as_review_needed", zero_component,
            ["COMPONENT_AMOUNT_ZERO", "OPENING_EVIDENCE_MISSING",
             "SOURCE_RESOLVER_UNAVAILABLE", "TRIP_CODE_MISSING"],
            "stable trip code missing")
        null_component = json.loads(make_charge_payload())
        null_component["price_components"][0]["amount_vnd"] = None
        null_component["price_components"][1]["amount_vnd"] = 100
        pending_charge("null_component_amount_persists_as_review_needed", null_component,
            ["COMPONENT_AMOUNT_MISSING", "OPENING_EVIDENCE_MISSING",
             "SOURCE_RESOLVER_UNAVAILABLE", "TRIP_CODE_MISSING"],
            "stable trip code missing")
        for nonfinite_token in ("NaN", "Infinity", "-Infinity"):
            nonfinite_money = integer_payload.replace('"total_vnd":100',
                f'"total_vnd":{nonfinite_token}')
            nonfinite_money_result, _, _ = f.submit(None, nonfinite_money, check=False)
            case(f"nonfinite_json_money_{nonfinite_token}_is_rejected", True,
                nonfinite_money_result.returncode != 0)

        valid_dates = ("0001-01-01", "2024-02-29", "9999-12-31")
        for valid_date in valid_dates:
            date_case_payload = (integer_payload.replace('"event_date":"2026-01-31"',
                f'"event_date":"{valid_date}"').replace('"posting_date":"2026-02-01"',
                f'"posting_date":"{valid_date}"'))
            valid_date_result, _, _ = f.submit(None, date_case_payload)
            valid_date_revision = json.loads(valid_date_result.stdout.strip())
            case(f"strict_iso_date_accepts_{valid_date}",
                valid_date, query("SELECT canonical_payload->>'event_date' "
                    "FROM p0_fixture.business_revision "
                    f"WHERE revision_id={valid_date_revision['revision_id']}"))

        invalid_dates = (
            ("year_zero", "0000-01-01"),
            ("year_ten_thousand", "10000-01-01"),
            ("invalid_leap_day", "2025-02-29"),
            ("invalid_month", "2026-13-01"),
            ("invalid_day", "2026-01-32"),
            ("slash_date", "01/02/2026"),
            ("slash_iso_date", "2026/01/31"),
            ("date_timestamp", "2026-01-01T00:00:00Z"),
            ("date_timestamp_space", "2026-01-01 00:00:00"),
            ("date_leading_whitespace", " 2026-01-01"),
            ("date_trailing_whitespace", "2026-01-01 "),
            ("date_unicode_digits", "２０２６-01-01"),
            ("positive_infinity_date", "infinity"),
            ("negative_infinity_date", "-infinity"),
        )
        for date_case, invalid_date in invalid_dates:
            for date_field, default_value in (("event_date", "2026-01-31"),
                                              ("posting_date", "2026-02-01")):
                invalid_date_payload = integer_payload.replace(
                    f'"{date_field}":"{default_value}"',
                    f'"{date_field}":{json.dumps(invalid_date, ensure_ascii=True)}')
                invalid_date_result, _, _ = f.submit(None, invalid_date_payload, check=False)
                rejected(f"strict_iso_date_rejects_{date_field}_{date_case}",
                    invalid_date_result, "invalid fixture date")

        payload100 = make_payload(100, source="fixture-é-source", evidence="fixture-é-evidence")
        created, first_assertion, maker_session = f.submit(None, payload100)
        first = json.loads(created.stdout.strip())
        proposal_id = int(first["proposal_id"])
        revision1 = int(first["revision_id"])
        hash1 = first["content_sha256"]
        case("revision_kind_is_stored_at_proposal_creation", "revision_fixture",
            query(f"SELECT kind FROM p0_fixture.proposal WHERE proposal_id={proposal_id}"))
        generic_to_charge = f.submit(None, make_charge_payload(
            trip_code="fixture-only-trip-code", opening_refs=True), check=False)
        rejected("identity_login_cannot_submit_new_charge", generic_to_charge[0],
            "database principal cannot use charge_fixture")
        charge_to_generic = charge.submit(None, make_payload(107, source="charge-login-generic-01"),
            check=False)
        rejected("charge_login_cannot_submit_new_revision_fixture", charge_to_generic[0],
            "database principal cannot use revision_fixture")
        charge_to_existing_generic = charge.submit(proposal_id,
            make_payload(100, source="fixture-é-source", evidence="fixture-é-evidence"), check=False)
        rejected("charge_login_cannot_revise_generic_proposal", charge_to_existing_generic[0],
            "database principal cannot use revision_fixture")
        rejected("charge_login_cannot_present_generic_proposal",
            charge.present(proposal_id, "Forbidden charge service presentation", check=False),
            "database principal cannot use revision_fixture")
        rejected("charge_login_cannot_confirm_price_for_generic_proposal",
            charge.confirm_price(proposal_id, revision1, hash1, check=False),
            "database principal cannot use revision_fixture")
        rejected("charge_login_cannot_confirm_period_for_generic_proposal",
            charge.confirm_period(proposal_id, revision1, hash1, check=False),
            "database principal cannot use revision_fixture")
        rejected("charge_login_cannot_approve_generic_proposal",
            charge.decide("approve", proposal_id, revision1, hash1, check=False)[0],
            "database principal cannot use revision_fixture")
        rejected("charge_login_cannot_post_generic_proposal",
            charge.decide("post", proposal_id, revision1, hash1, check=False)[0],
            "database principal cannot use revision_fixture")
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
        future_epoch = int(time.time()) + 31
        future_assertion, _, _ = f.submit(None, make_payload(338, source="future-source-01"),
            issued_epoch=future_epoch, check=False)
        rejected("future_actor_assertion_is_rejected", future_assertion, "invalid actor assertion")

        null_epoch_payload = make_payload(339, source="null-epoch-source-01")
        null_epoch_scope = submit_scope(None, null_epoch_payload)
        null_epoch_session = AuthenticatedSession(MAKER, uuid.uuid4())
        null_epoch_nonce = uuid.uuid4()
        null_epoch_signature = legacy_signature(
            null_epoch_session, "submit", null_epoch_nonce, None, null_epoch_scope)
        case("null_epoch_legacy_hmac_matches_old_concat_protocol", True,
            legacy_signature_matches(null_epoch_session, "submit", null_epoch_nonce,
                None, null_epoch_scope, null_epoch_signature))
        null_epoch_result = f.psql(
            "SELECT row_to_json(x)::text FROM p0_fixture.submit_revision("
            f"NULL::bigint, {sql_literal(null_epoch_payload)}::text, '{MAKER}'::uuid, "
            f"'{null_epoch_session.session_id}'::uuid, '{null_epoch_nonce}'::uuid, "
            f"NULL::bigint, 'fixture-key-v1', {sql_literal(null_epoch_signature)}) x",
            user=IDENTITY_LOGIN, check=False)
        rejected("null_issued_epoch_is_rejected_before_hmac", null_epoch_result,
            "invalid actor assertion")

        null_action_session = AuthenticatedSession(CHECKER, uuid.uuid4())
        null_action_nonce = uuid.uuid4()
        null_action_epoch = int(time.time())
        null_action_scope = "fixture-null-action-scope"
        null_action_signature = legacy_signature(
            null_action_session, None, null_action_nonce, null_action_epoch, null_action_scope)
        case("null_action_legacy_hmac_matches_old_concat_protocol", True,
            legacy_signature_matches(null_action_session, None, null_action_nonce,
                null_action_epoch, null_action_scope, null_action_signature))
        null_action_result = f.psql(
            "SELECT p0_fixture.verify_actor_assertion("
            f"'{CHECKER}'::uuid, '{null_action_session.session_id}'::uuid, NULL::text, "
            f"'{null_action_nonce}'::uuid, {null_action_epoch}, 'fixture-key-v1', "
            f"{sql_literal(null_action_scope)}, {sql_literal(null_action_signature)})",
            user="postgres", check=False)
        rejected("null_actor_action_is_rejected_before_hmac", null_action_result,
            "invalid actor assertion")

        inactive, _, _ = f.submit(None, make_payload(334, source="inactive-source-01"), actor=DISABLED, check=False)
        rejected("disabled_actor_is_rejected", inactive, "inactive actor")

        wrong_role_session, wrong_role_assertion = f.assertion(MAKER_ONLY, "approve",
            revision_scope("approve", proposal_id, revision1, hash1))
        wrong_role_args = f.assertion_sql(wrong_role_session, wrong_role_assertion)
        wrong_role = f.psql(
            f"SELECT p0_fixture.approve_revision({proposal_id},{revision1},"
            f"{sql_literal(hash1)},{wrong_role_args})", user=IDENTITY_LOGIN, check=False)
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

        generic_kind_before = proposal_snapshot(proposal_id)
        valid_charge_revision = make_charge_payload(
            trip_code="fixture-only-trip-code", opening_refs=True)
        kind_change_to_charge = f.submit(proposal_id, valid_charge_revision, check=False)
        rejected("revision_kind_cannot_change_to_charge", kind_change_to_charge[0],
            "proposal kind is immutable")
        case("rejected_kind_change_to_charge_preserves_proposal_history",
            generic_kind_before, proposal_snapshot(proposal_id))
        proposal_kind_trigger = f.psql(
            f"UPDATE p0_fixture.proposal SET kind='charge_fixture' WHERE proposal_id={proposal_id}",
            check=False)
        rejected("proposal_kind_column_is_immutable", proposal_kind_trigger,
            "proposal kind is immutable")

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
        fractional_payload = (make_payload(103, source="fractional-source-01")
            .replace('"total_vnd":103', '"total_vnd":103.5')
            .replace('"amount_vnd":51', '"amount_vnd":51.5', 1))
        fractional, _, _ = f.submit(None, fractional_payload, check=False)
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
        rejected("receipt_path_is_not_enabled_while_q09_is_open", receipt,
            "missing or unknown business fields")

        # Malformed charge requests reject; only well-formed incomplete business evidence persists.
        old_date, _, _ = charge.submit(None, make_charge_payload(event_date="2026-10-13"), check=False)
        rejected("charge_before_2026_10_14_is_rejected", old_date, "before 2026-10-14")
        multi_line_payload = json.loads(make_charge_payload())
        multi_line_payload["lines"].append(
            {"line_no": 2, "customer_id": "FAKE-CUSTOMER-1",
             "debt_period": "2026-09", "amount_vnd": 1})
        multi_line_payload["total_vnd"] = 101
        multi_line_payload["price_components"][1]["amount_vnd"] += 1
        multi_line, _, _ = charge.submit(None,
            json.dumps(multi_line_payload, separators=(",", ":")), check=False)
        rejected("charge_requires_exactly_one_debt_line", multi_line, "exactly one debt line")

        missing_total_obj = json.loads(make_charge_payload(
            trip_code="opaque-fixture-trip", opening_refs=True))
        missing_total_obj["total_vnd"] = None
        missing_total, missing_total_revision, missing_total_hash = pending_charge(
            "total_missing", missing_total_obj,
            ["TOTAL_MISSING", "SOURCE_RESOLVER_UNAVAILABLE"],
            "source key and opening reconciliation are unresolved")
        zero_total_obj = json.loads(make_charge_payload(
            trip_code="opaque-fixture-trip", opening_refs=True))
        zero_total_obj["total_vnd"] = 0
        zero_total_obj["lines"][0]["amount_vnd"] = 0
        zero_total_obj["price_components"] = [
            {"label": "zero fixture component", "amount_vnd": 0}]
        zero_total, zero_total_revision, zero_total_hash = pending_charge(
            "total_zero", zero_total_obj,
            ["COMPONENT_AMOUNT_ZERO", "TOTAL_ZERO", "SOURCE_RESOLVER_UNAVAILABLE"],
            "source key and opening reconciliation are unresolved")
        missing_total_view = review_projection(missing_total)
        zero_total_view = review_projection(zero_total)
        case("charge_json_null_is_preserved", None,
             missing_total_view["revisions"][0]["payload"]["total_vnd"])
        case("charge_zero_is_preserved", 0,
             zero_total_view["revisions"][0]["payload"]["total_vnd"])
        case("charge_null_and_zero_hashes_are_distinct", True,
             missing_total_hash != zero_total_hash
             and missing_total_revision != zero_total_revision)

        missing_components_obj = json.loads(make_charge_payload(
            trip_code="opaque-fixture-trip", opening_refs=True))
        missing_components_obj["price_components"] = None
        pending_charge("price_components_null", missing_components_obj,
            ["PRICE_COMPONENTS_MISSING", "SOURCE_RESOLVER_UNAVAILABLE"],
            "source key and opening reconciliation are unresolved")
        empty_components_obj = json.loads(make_charge_payload(
            trip_code="opaque-fixture-trip", opening_refs=True))
        empty_components_obj["price_components"] = []
        pending_charge("price_components_empty", empty_components_obj,
            ["PRICE_COMPONENTS_MISSING", "SOURCE_RESOLVER_UNAVAILABLE"],
            "source key and opening reconciliation are unresolved")

        partial_component_obj = json.loads(make_charge_payload(
            trip_code="opaque-fixture-trip", opening_refs=True))
        partial_component_obj["price_components"] = [
            {"label": "known component", "amount_vnd": 100},
            {"label": "missing component amount", "amount_vnd": None},
        ]
        pending_charge("component_amount_missing", partial_component_obj,
            ["COMPONENT_AMOUNT_MISSING", "SOURCE_RESOLVER_UNAVAILABLE"],
            "source key and opening reconciliation are unresolved")

        mismatched_components_obj = json.loads(make_charge_payload(
            trip_code="opaque-fixture-trip", opening_refs=True))
        mismatched_components_obj["price_components"] = [
            {"label": "component A", "amount_vnd": 40},
            {"label": "component B", "amount_vnd": 50},
        ]
        pending_charge("component_total_mismatch", mismatched_components_obj,
            ["COMPONENT_TOTAL_MISMATCH", "SOURCE_RESOLVER_UNAVAILABLE"],
            "source key and opening reconciliation are unresolved")

        missing_line_obj = json.loads(make_charge_payload(
            trip_code="opaque-fixture-trip", opening_refs=True))
        missing_line_obj["lines"][0]["amount_vnd"] = None
        pending_charge("line_amount_missing", missing_line_obj,
            ["LINE_AMOUNT_MISSING", "SOURCE_RESOLVER_UNAVAILABLE"],
            "source key and opening reconciliation are unresolved")
        mismatch_line_obj = json.loads(make_charge_payload(
            trip_code="opaque-fixture-trip", opening_refs=True))
        mismatch_line_obj["lines"][0]["amount_vnd"] = 99
        pending_charge("line_total_mismatch", mismatch_line_obj,
            ["LINE_TOTAL_MISMATCH", "SOURCE_RESOLVER_UNAVAILABLE"],
            "source key and opening reconciliation are unresolved")

        missing_source_obj = json.loads(make_charge_payload(
            trip_code="opaque-fixture-trip", opening_refs=True))
        missing_source_obj["source_ref"] = ""
        missing_source_obj["evidence_ref"] = None
        missing_source_obj["evidence_sha256"] = None
        missing_source, _, _ = pending_charge("source_evidence_missing",
            missing_source_obj,
            ["SOURCE_EVIDENCE_MISSING", "SOURCE_RESOLVER_UNAVAILABLE"],
            "source key and opening reconciliation are unresolved")
        case("blank_source_reference_is_preserved_for_review", "",
             review_projection(missing_source)["revisions"][0]["payload"]["source_ref"])

        missing_trip_obj = json.loads(make_charge_payload(opening_refs=True))
        missing_trip_obj["trip_code"] = "  "
        pending_charge("trip_code_missing", missing_trip_obj,
            ["SOURCE_RESOLVER_UNAVAILABLE", "TRIP_CODE_MISSING"],
            "stable trip code missing")
        missing_opening_obj = json.loads(make_charge_payload(trip_code="opaque-fixture-trip"))
        pending_charge("opening_evidence_missing", missing_opening_obj,
            ["OPENING_EVIDENCE_MISSING", "SOURCE_RESOLVER_UNAVAILABLE"],
            "opening comparison evidence missing")
        resolver_obj = json.loads(make_charge_payload(
            trip_code="opaque-fixture-trip", opening_refs=True))
        resolver_proposal, _, _ = pending_charge("source_resolver_unavailable", resolver_obj,
            ["SOURCE_RESOLVER_UNAVAILABLE"],
            "source key and opening reconciliation are unresolved")
        case("review_projection_is_not_granted_to_api_logins", "false|false", query(
            "SELECT has_function_privilege('webdebit_app', "
            "'p0_fixture.fixture_review_projection(bigint)', 'EXECUTE')::text || '|' || "
            "has_function_privilege('webdebit_identity_test_app', "
            "'p0_fixture.fixture_review_projection(bigint)', 'EXECUTE')::text"))
        projection_api_attempt = charge.psql(
            f"SELECT p0_fixture.fixture_review_projection({resolver_proposal})",
            user=CHARGE_LOGIN, check=False)
        rejected("charge_api_cannot_read_fixture_projection", projection_api_attempt,
            "permission denied for function fixture_review_projection")

        combined_missing_obj = json.loads(make_charge_payload())
        combined_missing_obj["total_vnd"] = None
        combined_missing_obj["source_ref"] = None
        combined_missing_obj["evidence_ref"] = "  "
        combined_missing_obj["evidence_sha256"] = None
        combined_missing_obj["lines"][0]["amount_vnd"] = None
        combined_missing_obj["price_components"] = [
            {"label": "pending component", "amount_vnd": None}]
        combined_missing, _, _ = pending_charge("combined_missing_evidence",
            combined_missing_obj,
            ["COMPONENT_AMOUNT_MISSING", "LINE_AMOUNT_MISSING", "OPENING_EVIDENCE_MISSING",
             "SOURCE_EVIDENCE_MISSING", "SOURCE_RESOLVER_UNAVAILABLE", "TOTAL_MISSING",
             "TRIP_CODE_MISSING"], "stable trip code missing")

        omitted_payload = json.loads(make_charge_payload())
        omitted_fields = ["total_vnd", "source_ref", "evidence_ref", "evidence_sha256",
                          "trip_code", "opening_snapshot_ref", "opening_absence_evidence_ref",
                          "price_components"]
        for field_name in omitted_fields:
            omitted_payload.pop(field_name)
        omitted_payload["lines"][0].pop("amount_vnd")
        omitted_text = json.dumps(omitted_payload, ensure_ascii=True, separators=(",", ":"))
        omitted_result, _, _ = charge.submit(None, omitted_text)
        omitted_revision = json.loads(omitted_result.stdout.strip())
        explicit_null_payload = json.loads(make_charge_payload())
        explicit_null_payload["total_vnd"] = None
        for field_name in omitted_fields[1:]:
            explicit_null_payload[field_name] = None
        explicit_null_payload["lines"][0]["amount_vnd"] = None
        explicit_null_text = json.dumps(explicit_null_payload, ensure_ascii=True,
                                        separators=(",", ":"))
        explicit_null_result, _, _ = charge.submit(int(omitted_revision["proposal_id"]),
            explicit_null_text)
        explicit_null_revision = json.loads(explicit_null_result.stdout.strip())
        case("omitted_and_null_charge_fields_have_same_hash",
            omitted_revision["content_sha256"], explicit_null_revision["content_sha256"])
        case("omitted_null_equivalence_is_business_noop",
            (1, int(omitted_revision["revision_id"]), False),
            (int(explicit_null_revision["revision_no"]),
             int(explicit_null_revision["revision_id"]),
             explicit_null_revision["revision_created"]))
        omitted_projection = review_projection(int(omitted_revision["proposal_id"]))
        case("omitted_fields_are_saved_as_json_null", True,
             all(omitted_projection["revisions"][0]["payload"][field_name] is None
                 for field_name in omitted_fields)
             and omitted_projection["revisions"][0]["payload"]["lines"][0]["amount_vnd"] is None)

        component_omitted = json.loads(make_charge_payload())
        component_omitted["price_components"] = [{"label": "optional amount"}]
        component_explicit_null = json.loads(make_charge_payload())
        component_explicit_null["price_components"] = [
            {"label": "optional amount", "amount_vnd": None}]
        component_omitted_result, _, _ = charge.submit(None,
            json.dumps(component_omitted, separators=(",", ":")))
        component_null_result, _, _ = charge.submit(None,
            json.dumps(component_explicit_null, separators=(",", ":")))
        component_omitted_revision = json.loads(component_omitted_result.stdout.strip())
        component_null_revision = json.loads(component_null_result.stdout.strip())
        case("omitted_and_null_component_amounts_have_same_hash",
             component_omitted_revision["content_sha256"],
             component_null_revision["content_sha256"])
        component_omitted_view = review_projection(
            int(component_omitted_revision["proposal_id"]))
        case("omitted_component_amount_is_saved_as_json_null", None,
             component_omitted_view["revisions"][0]["payload"]
             ["price_components"][0]["amount_vnd"])

        combined_before_edit = review_projection(combined_missing)
        old_revision = combined_before_edit["revisions"][0]
        correction = json.loads(make_charge_payload(
            trip_code="opaque-fixture-trip", opening_refs=True))
        correction_result, _, _ = charge.submit(combined_missing,
            json.dumps(correction, ensure_ascii=True, separators=(",", ":")))
        corrected_revision = json.loads(correction_result.stdout.strip())
        corrected_view = review_projection(combined_missing)
        case("correcting_charge_content_creates_revision_two", (2, True),
             (int(corrected_revision["revision_no"]), corrected_revision["revision_created"]))
        case("corrected_charge_reasons_are_resolver_only",
             ["SOURCE_RESOLVER_UNAVAILABLE"],
             corrected_view["revisions"][1]["reason_codes"])
        case("old_charge_revision_payload_hash_and_reasons_remain_immutable", True,
             corrected_view["revisions"][0] == old_revision
             and old_revision["reason_codes"] == sorted([
                 "COMPONENT_AMOUNT_MISSING", "LINE_AMOUNT_MISSING", "OPENING_EVIDENCE_MISSING",
                 "SOURCE_EVIDENCE_MISSING", "SOURCE_RESOLVER_UNAVAILABLE", "TOTAL_MISSING",
                 "TRIP_CODE_MISSING"]))
        stale_old_approval, _, _ = charge.decide("approve", combined_missing,
            int(old_revision["revision_id"]), old_revision["content_sha256"], check=False)
        rejected("old_incomplete_revision_cannot_be_approved_after_correction",
            stale_old_approval, "stale, unavailable, or self-approved revision")
        charge.confirm_period(combined_missing, int(corrected_revision["revision_id"]),
                              corrected_revision["content_sha256"])
        charge.confirm_price(combined_missing, int(corrected_revision["revision_id"]),
                             corrected_revision["content_sha256"])
        rejected("corrected_opaque_trip_still_fails_source_resolver",
            charge.decide("approve", combined_missing, int(corrected_revision["revision_id"]),
                corrected_revision["content_sha256"], check=False)[0],
            "source key and opening reconciliation are unresolved")
        case("corrected_opaque_trip_has_no_approval_or_posting", "review_needed|0|0", query(
            "SELECT p.state || '|' || (SELECT count(*) FROM p0_fixture.approval a "
            "WHERE a.proposal_id=p.proposal_id) || '|' || "
            "(SELECT count(*) FROM p0_fixture.posting x WHERE x.proposal_id=p.proposal_id) "
            f"FROM p0_fixture.proposal p WHERE p.proposal_id={combined_missing}"))

        malformed_target = resolver_proposal
        malformed_cases: list[tuple[str, str]] = [("invalid_json", "{")]
        malformed_obj = json.loads(make_charge_payload(
            trip_code="opaque-fixture-trip", opening_refs=True))
        malformed_obj["clientreasoncodes"] = ["TRIP_CODE_MISSING"]
        malformed_cases.append(("client_reason_codes", json.dumps(malformed_obj)))
        wrong_type_cases = [
            ("customer_object", "customer_id", {"id": "FAKE-CUSTOMER-1"}),
            ("period_boolean", "debt_period", True),
            ("event_date_object", "event_date", {"date": "2026-10-14"}),
            ("posting_date_boolean", "posting_date", False),
            ("source_object", "source_ref", {"ref": "fixture"}),
            ("evidence_boolean", "evidence_ref", True),
            ("hash_boolean", "evidence_sha256", True),
            ("reason_object", "reason", {"text": "fixture"}),
            ("trip_boolean", "trip_code", True),
            ("opening_object", "opening_snapshot_ref", {"ref": "fixture"}),
        ]
        for case_name, field_name, bad_value in wrong_type_cases:
            bad_obj = json.loads(make_charge_payload(
                trip_code="opaque-fixture-trip", opening_refs=True))
            bad_obj[field_name] = bad_value
            malformed_cases.append((case_name, json.dumps(bad_obj)))
        for case_name, bad_value in (
            ("money_string", "100"), ("money_boolean", True),
            ("money_object", {"amount": 100}), ("money_negative", -100),
            ("money_fractional", 100.5),
        ):
            bad_obj = json.loads(make_charge_payload(
                trip_code="opaque-fixture-trip", opening_refs=True))
            bad_obj["total_vnd"] = bad_value
            malformed_cases.append((case_name, json.dumps(bad_obj)))
        for case_name, bad_value in (
            ("line_amount_string", "100"), ("line_amount_boolean", True),
            ("line_amount_object", {"amount": 100}),
            ("line_amount_negative", -100), ("line_amount_fractional", 100.5),
        ):
            bad_obj = json.loads(make_charge_payload(
                trip_code="opaque-fixture-trip", opening_refs=True))
            bad_obj["lines"][0]["amount_vnd"] = bad_value
            malformed_cases.append((case_name, json.dumps(bad_obj)))
        multi_line_invalid = json.loads(make_charge_payload(
            trip_code="opaque-fixture-trip", opening_refs=True))
        multi_line_invalid["lines"].append({
            "line_no": 2, "customer_id": "FAKE-CUSTOMER-1",
            "debt_period": "2026-09", "amount_vnd": 1,
        })
        malformed_cases.append(("multiple_debt_lines", json.dumps(multi_line_invalid)))
        bad_line_number = json.loads(make_charge_payload(
            trip_code="opaque-fixture-trip", opening_refs=True))
        bad_line_number["lines"][0]["line_no"] = 1.5
        malformed_cases.append(("fractional_line_number", json.dumps(bad_line_number)))
        bad_period_customer = json.loads(make_charge_payload(
            trip_code="opaque-fixture-trip", opening_refs=True))
        bad_period_customer["lines"][0]["customer_id"] = "FAKE-CUSTOMER-2"
        malformed_cases.append(("line_customer_mismatch", json.dumps(bad_period_customer)))
        bad_period_line = json.loads(make_charge_payload(
            trip_code="opaque-fixture-trip", opening_refs=True))
        bad_period_line["lines"][0]["debt_period"] = "2026-08"
        malformed_cases.append(("line_period_mismatch", json.dumps(bad_period_line)))
        bad_period_year = json.loads(make_charge_payload(
            trip_code="opaque-fixture-trip", opening_refs=True))
        bad_period_year["debt_period"] = "0000-01"
        bad_period_year["lines"][0]["debt_period"] = "0000-01"
        malformed_cases.append(("zero_year_period_header_and_line", json.dumps(bad_period_year)))
        bad_period_header_year = json.loads(make_charge_payload(
            trip_code="opaque-fixture-trip", opening_refs=True))
        bad_period_header_year["debt_period"] = "0000-01"
        malformed_cases.append(("zero_year_period_header", json.dumps(bad_period_header_year)))
        bad_period_line_year = json.loads(make_charge_payload(
            trip_code="opaque-fixture-trip", opening_refs=True))
        bad_period_line_year["lines"][0]["debt_period"] = "0000-01"
        malformed_cases.append(("zero_year_period_line", json.dumps(bad_period_line_year)))
        bad_line_type = json.loads(make_charge_payload(
            trip_code="opaque-fixture-trip", opening_refs=True))
        bad_line_type["lines"][0]["customer_id"] = {"id": "FAKE-CUSTOMER-1"}
        malformed_cases.append(("line_customer_object", json.dumps(bad_line_type)))
        bad_line_period_type = json.loads(make_charge_payload(
            trip_code="opaque-fixture-trip", opening_refs=True))
        bad_line_period_type["lines"][0]["debt_period"] = {"period": "2026-09"}
        malformed_cases.append(("line_period_object", json.dumps(bad_line_period_type)))
        bad_opening_evidence_type = json.loads(make_charge_payload(
            trip_code="opaque-fixture-trip", opening_refs=True))
        bad_opening_evidence_type["opening_absence_evidence_ref"] = False
        malformed_cases.append(("opening_evidence_boolean", json.dumps(bad_opening_evidence_type)))
        bad_component_label = json.loads(make_charge_payload(
            trip_code="opaque-fixture-trip", opening_refs=True))
        bad_component_label["price_components"][0]["label"] = {"label": "fixture"}
        malformed_cases.append(("component_label_object", json.dumps(bad_component_label)))
        bad_component_money = json.loads(make_charge_payload(
            trip_code="opaque-fixture-trip", opening_refs=True))
        bad_component_money["price_components"][0]["amount_vnd"] = "50"
        malformed_cases.append(("component_amount_string", json.dumps(bad_component_money)))
        for date_index, date_value in enumerate(("2026-02-30", "2026/10/14",
                "2026-10-14T00:00:00", "2026-10-13"), start=1):
            bad_date_obj = json.loads(make_charge_payload(
                trip_code="opaque-fixture-trip", opening_refs=True))
            bad_date_obj["event_date"] = date_value
            malformed_cases.append((f"bad_event_date_{date_index}", json.dumps(bad_date_obj)))
        bad_hash_obj = json.loads(make_charge_payload(
            trip_code="opaque-fixture-trip", opening_refs=True))
        bad_hash_obj["evidence_sha256"] = "not-a-hash"
        malformed_cases.append(("malformed_supplied_hash", json.dumps(bad_hash_obj)))
        bad_nonfinite_payload = make_charge_payload(
            trip_code="opaque-fixture-trip", opening_refs=True)
        for nonfinite_token in ("NaN", "Infinity", "-Infinity"):
            malformed_cases.append((f"nonfinite_{nonfinite_token}",
                bad_nonfinite_payload.replace('"total_vnd":100',
                    f'"total_vnd":{nonfinite_token}')))
        unknown_component_obj = json.loads(make_charge_payload(
            trip_code="opaque-fixture-trip", opening_refs=True))
        unknown_component_obj["price_components"][0]["client_reason"] = "invented"
        malformed_cases.append(("unknown_component_key", json.dumps(unknown_component_obj)))

        before_malformed = proposal_snapshot(malformed_target)
        for case_name, raw_payload in malformed_cases:
            malformed_result, _, _ = charge.submit(malformed_target, raw_payload, check=False)
            case(f"malformed_{case_name}_is_rejected", True,
                 malformed_result.returncode != 0)
            case(f"malformed_{case_name}_leaves_state_unchanged", before_malformed,
                 proposal_snapshot(malformed_target))

        missing_trip_result, _, _ = charge.submit(None, make_charge_payload())
        missing_trip = json.loads(missing_trip_result.stdout.strip())
        missing_trip_proposal = int(missing_trip["proposal_id"])
        missing_trip_revision = int(missing_trip["revision_id"])
        missing_trip_hash = missing_trip["content_sha256"]
        case("charge_starts_in_review_needed_state", "review_needed",
            query(f"SELECT state FROM p0_fixture.proposal WHERE proposal_id={missing_trip_proposal}"))
        case("charge_date_period_and_one_line_are_canonical",
            ("2026-10-14", "2026-09", "1", "2"),
            tuple(query(
                "SELECT (r.canonical_payload->>'event_date') || '|' || "
                "(r.canonical_payload->>'debt_period') || '|' || "
                "jsonb_array_length(r.canonical_payload->'lines')::text || '|' || "
                "jsonb_array_length(r.canonical_payload->'price_components')::text "
                "FROM p0_fixture.business_revision r "
                f"WHERE r.revision_id={missing_trip_revision}").split("|")))
        closed_period, _, _ = charge.submit(None,
            make_charge_payload(period="2026-08"), check=False)
        closed_period_proposal = None
        if closed_period.returncode == 0:
            closed_record = json.loads(closed_period.stdout.strip())
            closed_period_proposal = (int(closed_record["proposal_id"]),
                                      int(closed_record["revision_id"]),
                                      closed_record["content_sha256"])
            rejected("closed_period_cannot_be_confirmed_by_maker",
                charge.confirm_period(*closed_period_proposal, check=False),
                "not open for maker confirmation")
            closed_approval, _, _ = charge.decide("approve", closed_period_proposal[0],
                closed_period_proposal[1], closed_period_proposal[2], check=False)
            rejected("closed_period_cannot_be_approved", closed_approval, "debt period is not open")
        else:
            raise HarnessError("closed-period proposal should remain a draft for fail-closed approval test")

        unknown_period, _, _ = charge.submit(None,
            make_charge_payload(period="2026-07"), check=False)
        if unknown_period.returncode == 0:
            unknown_record = json.loads(unknown_period.stdout.strip())
            unknown_proposal = (int(unknown_record["proposal_id"]),
                                int(unknown_record["revision_id"]),
                                unknown_record["content_sha256"])
            rejected("period_without_open_state_cannot_be_confirmed",
                charge.confirm_period(*unknown_proposal, check=False),
                "not open for maker confirmation")
            unknown_approval, _, _ = charge.decide("approve", unknown_proposal[0],
                unknown_proposal[1], unknown_proposal[2], check=False)
            rejected("period_without_open_state_cannot_be_approved",
                unknown_approval, "debt period is not open")
        else:
            raise HarnessError("unknown-period proposal should remain a draft for fail-closed check")

        charge.confirm_period(missing_trip_proposal, missing_trip_revision, missing_trip_hash)
        charge.confirm_price(missing_trip_proposal, missing_trip_revision, missing_trip_hash)
        rejected("charge_missing_stable_trip_code_stays_pending",
            charge.decide("approve", missing_trip_proposal, missing_trip_revision,
                missing_trip_hash, check=False),
            "stable trip code missing")
        missing_trip_state = query(
            "SELECT p.state || '|' || "
            f"(SELECT count(*) FROM p0_fixture.approval a WHERE a.proposal_id=p.proposal_id) || '|' || "
            f"(SELECT count(*) FROM p0_fixture.posting x WHERE x.proposal_id=p.proposal_id) "
            f"FROM p0_fixture.proposal p WHERE p.proposal_id={missing_trip_proposal}")
        case("missing_trip_code_charge_remains_outside_balance", "review_needed|0|0", missing_trip_state)

        missing_opening_result, _, _ = charge.submit(None,
            make_charge_payload(trip_code="fixture-only-trip-code"))
        missing_opening = json.loads(missing_opening_result.stdout.strip())
        missing_opening_proposal = int(missing_opening["proposal_id"])
        missing_opening_revision = int(missing_opening["revision_id"])
        missing_opening_hash = missing_opening["content_sha256"]
        charge.confirm_period(missing_opening_proposal, missing_opening_revision,
            missing_opening_hash)
        charge.confirm_price(missing_opening_proposal, missing_opening_revision,
            missing_opening_hash)
        rejected("missing_opening_comparison_keeps_charge_pending",
            charge.decide("approve", missing_opening_proposal, missing_opening_revision,
                missing_opening_hash, check=False),
            "opening comparison evidence missing")

        candidate_result, _, _ = charge.submit(None, make_charge_payload(
            trip_code="fixture-only-trip-code", opening_refs=True))
        candidate = json.loads(candidate_result.stdout.strip())
        charge_proposal = int(candidate["proposal_id"])
        charge_revision = int(candidate["revision_id"])
        charge_hash = candidate["content_sha256"]
        case("charge_kind_is_stored_at_proposal_creation", "charge_fixture",
            query(f"SELECT kind FROM p0_fixture.proposal WHERE proposal_id={charge_proposal}"))
        generic_to_charge_revision = f.submit(charge_proposal,
            make_charge_payload(trip_code="fixture-only-trip-code", opening_refs=True), check=False)
        rejected("identity_login_cannot_revise_charge_proposal",
            generic_to_charge_revision[0], "database principal cannot use charge_fixture")
        rejected("identity_login_cannot_present_charge_proposal",
            f.present(charge_proposal, "Forbidden identity presentation", check=False),
            "database principal cannot use charge_fixture")
        rejected("identity_login_cannot_confirm_price_for_charge_proposal",
            f.confirm_price(charge_proposal, charge_revision, charge_hash, check=False),
            "database principal cannot use charge_fixture")
        rejected("identity_login_cannot_confirm_period_for_charge_proposal",
            f.confirm_period(charge_proposal, charge_revision, charge_hash, check=False),
            "database principal cannot use charge_fixture")
        rejected("identity_login_cannot_approve_charge_proposal",
            f.decide("approve", charge_proposal, charge_revision, charge_hash, check=False)[0],
            "database principal cannot use charge_fixture")
        rejected("identity_login_cannot_post_charge_proposal",
            f.decide("post", charge_proposal, charge_revision, charge_hash, check=False)[0],
            "database principal cannot use charge_fixture")
        charge_kind_before = proposal_snapshot(charge_proposal)
        valid_generic_revision = make_payload(108, source="charge-to-generic-01")
        kind_change_to_generic = charge.submit(charge_proposal, valid_generic_revision, check=False)
        rejected("charge_kind_cannot_change_to_revision_fixture", kind_change_to_generic[0],
            "proposal kind is immutable")
        case("rejected_kind_change_to_generic_preserves_proposal_history",
            charge_kind_before, proposal_snapshot(charge_proposal))
        rejected("charge_without_owner_price_confirmation_stays_pending",
            charge.decide("approve", charge_proposal, charge_revision, charge_hash, check=False),
            "maker confirmation required")
        charge.confirm_period(charge_proposal, charge_revision, charge_hash)
        rejected("charge_without_owner_price_confirmation_is_rejected",
            charge.decide("approve", charge_proposal, charge_revision, charge_hash, check=False),
            "per-trip price owner confirmation required")
        charge.confirm_price(charge_proposal, charge_revision, charge_hash)
        owner_confirmation = query(
            "SELECT c.owner_actor_id::text || '|' || c.revision_id::text || '|' || c.content_sha256 "
            "FROM p0_fixture.price_confirmation c "
            f"WHERE c.proposal_id={charge_proposal}")
        case("owner_price_confirmation_binds_actor_revision_and_hash",
            f"{PRICE_OWNER}|{charge_revision}|{charge_hash}", owner_confirmation)
        period_confirmation = query(
            "SELECT c.maker_actor_id::text || '|' || c.revision_id::text || '|' || c.content_sha256 "
            "FROM p0_fixture.period_confirmation c "
            f"WHERE c.proposal_id={charge_proposal}")
        case("maker_period_confirmation_binds_actor_revision_and_hash",
            f"{MAKER}|{charge_revision}|{charge_hash}", period_confirmation)
        charge_audit_login = query(
            "SELECT count(*) FROM p0_fixture.audit "
            f"WHERE proposal_id={charge_proposal} AND database_session_user='{CHARGE_LOGIN}' "
            "AND action IN ('submit', 'confirm_period', 'confirm_price')")
        case("charge_fixture_audit_uses_charge_login", 3, int(charge_audit_login))
        rejected("checker_cannot_attest_per_trip_price",
            charge.confirm_price(charge_proposal, charge_revision, charge_hash,
                actor=CHECKER, check=False),
            "actor role required")
        rejected("price_owner_cannot_checker_approve_same_revision",
            charge.decide("approve", charge_proposal, charge_revision, charge_hash,
                actor=PRICE_OWNER, check=False),
            "price owner cannot checker-approve")
        rejected("opaque_trip_code_and_opening_refs_do_not_prove_source_resolution",
            charge.decide("approve", charge_proposal, charge_revision, charge_hash, check=False),
            "source key and opening reconciliation are unresolved")

        changed_charge_payload = json.loads(make_charge_payload(
            trip_code="fixture-only-trip-code", opening_refs=True, amount=101))
        changed_charge_result, _, _ = charge.submit(charge_proposal,
            json.dumps(changed_charge_payload, separators=(",", ":")))
        changed_charge = json.loads(changed_charge_result.stdout.strip())
        changed_charge_revision = int(changed_charge["revision_id"])
        changed_charge_hash = changed_charge["content_sha256"]
        rejected("old_period_confirmation_is_invalid_after_charge_edit",
            charge.decide("approve", charge_proposal, changed_charge_revision,
                changed_charge_hash, check=False),
            "maker confirmation required")
        charge.confirm_period(charge_proposal, changed_charge_revision, changed_charge_hash)
        rejected("old_price_confirmation_is_invalid_after_charge_edit",
            charge.decide("approve", charge_proposal, changed_charge_revision,
                changed_charge_hash, check=False),
            "per-trip price owner confirmation required")
        charge.confirm_price(charge_proposal, changed_charge_revision, changed_charge_hash)
        rejected("reconfirmed_charge_still_fails_closed_on_opening",
            charge.decide("approve", charge_proposal, changed_charge_revision,
                changed_charge_hash, check=False),
            "source key and opening reconciliation are unresolved")
        blocked_charge_state = query(
            "SELECT p.state || '|' || "
            f"(SELECT count(*) FROM p0_fixture.approval a WHERE a.proposal_id=p.proposal_id) || '|' || "
            f"(SELECT count(*) FROM p0_fixture.posting x WHERE x.proposal_id=p.proposal_id) "
            f"FROM p0_fixture.proposal p WHERE p.proposal_id={charge_proposal}")
        case("unresolved_opening_charge_remains_outside_balance", "review_needed|0|0", blocked_charge_state)

        wrong_scope_session, wrong_scope_assertion = f.assertion(CHECKER, "approve",
            revision_scope("approve", proposal_id, revision1, hash1))
        wrong_scope_args = f.assertion_sql(wrong_scope_session, wrong_scope_assertion)
        wrong_scope_result = f.psql(
            f"SELECT p0_fixture.approve_revision({proposal_id},{revision_current},"
            f"{sql_literal(hash_current)},{wrong_scope_args})", user=IDENTITY_LOGIN, check=False)
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
             and posted["database_session_user"] == IDENTITY_LOGIN)
        approval_link = query(
            "SELECT count(*) FROM p0_fixture.approval a "
            f"WHERE a.approval_id={posted['approval_id']} AND a.revision_id={revision_current} "
            f"AND a.content_sha256='{hash_current}' AND a.checker_actor_id='{CHECKER}'::uuid")
        case("posting_references_its_exact_approval_event", 1, int(approval_link))
        duplicate_post, _, _ = f.decide("post", proposal_id, revision_current, hash_current, check=False)
        rejected("already_posted_revision_cannot_post_twice", duplicate_post, "current approved revision required")

        audit_mapping = query(
            "SELECT count(*) FROM p0_fixture.audit a WHERE a.proposal_id=" + str(proposal_id)
            + f" AND a.app_actor_id='{MAKER}'::uuid AND a.database_session_user='{IDENTITY_LOGIN}'"
            + " AND a.key_id='fixture-key-v1' AND EXISTS (SELECT 1 FROM p0_fixture.used_assertion_nonce n"
            + " WHERE n.nonce=a.assertion_nonce AND n.actor_id=a.app_actor_id AND n.session_id=a.app_session_id)")
        case("audit_separates_app_actor_from_database_service_login", True, int(audit_mapping) > 0)
        direct_read = f.psql("SELECT * FROM p0_fixture.business_revision", user=IDENTITY_LOGIN, check=False)
        rejected("api_role_cannot_read_revision_table_directly", direct_read, "permission denied")
        direct_update = f.psql(
            "UPDATE p0_fixture.proposal SET state='pending'", user=IDENTITY_LOGIN, check=False)
        rejected("api_role_cannot_update_proposal_table_directly", direct_update, "permission denied")
        direct_key_read = f.psql("SELECT secret FROM p0_fixture.actor_signing_key",
            user=IDENTITY_LOGIN, check=False)
        rejected("api_role_cannot_read_actor_signing_key", direct_key_read, "permission denied")
        direct_insert = f.psql(
            f"INSERT INTO p0_fixture.proposal(maker_actor_id, kind) "
            f"VALUES ('{MAKER}'::uuid, 'revision_fixture')",
            user=IDENTITY_LOGIN, check=False)
        rejected("identity_api_role_cannot_insert_proposals_directly",
            direct_insert, "permission denied")
        charge_direct_read = f.psql("SELECT * FROM p0_fixture.business_revision",
            user=CHARGE_LOGIN, check=False)
        rejected("charge_api_role_cannot_read_revision_table_directly",
            charge_direct_read, "permission denied")
        charge_direct_dml = f.psql("DELETE FROM p0_fixture.proposal",
            user=CHARGE_LOGIN, check=False)
        rejected("charge_api_role_cannot_delete_proposals_directly",
            charge_direct_dml, "permission denied")
        charge_direct_key_read = f.psql("SELECT secret FROM p0_fixture.actor_signing_key",
            user=CHARGE_LOGIN, check=False)
        rejected("charge_api_role_cannot_read_actor_signing_key",
            charge_direct_key_read, "permission denied")
        charge_direct_insert = f.psql(
            f"INSERT INTO p0_fixture.proposal(maker_actor_id, kind) "
            f"VALUES ('{MAKER}'::uuid, 'charge_fixture')",
            user=CHARGE_LOGIN, check=False)
        rejected("charge_api_role_cannot_insert_proposals_directly",
            charge_direct_insert, "permission denied")

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
        price_confirmation_id = int(query(
            "SELECT confirmation_id FROM p0_fixture.price_confirmation "
            f"WHERE proposal_id={charge_proposal} ORDER BY revision_id DESC LIMIT 1"))
        price_confirmation_mutation = f.psql(
            "UPDATE p0_fixture.price_confirmation "
            f"SET content_sha256='{hash1}' WHERE confirmation_id={price_confirmation_id}",
            check=False)
        rejected("price_confirmation_is_append_only", price_confirmation_mutation,
            "append-only fixture row")
        period_confirmation_id = int(query(
            "SELECT confirmation_id FROM p0_fixture.period_confirmation "
            f"WHERE proposal_id={charge_proposal} ORDER BY revision_id DESC LIMIT 1"))
        period_confirmation_mutation = f.psql(
            "UPDATE p0_fixture.period_confirmation "
            f"SET content_sha256='{hash1}' WHERE confirmation_id={period_confirmation_id}",
            check=False)
        rejected("period_confirmation_is_append_only", period_confirmation_mutation,
            "append-only fixture row")
        charge_approval_or_post = query(
            "SELECT count(*) FROM p0_fixture.proposal p WHERE p.kind='charge_fixture' "
            "AND (p.state IN ('approved', 'posted') "
            "OR EXISTS (SELECT 1 FROM p0_fixture.approval a WHERE a.proposal_id=p.proposal_id) "
            "OR EXISTS (SELECT 1 FROM p0_fixture.posting x WHERE x.proposal_id=p.proposal_id))")
        case("no_charge_fixture_approved_or_posted", 0, int(charge_approval_or_post))
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
