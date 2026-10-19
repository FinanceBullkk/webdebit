#!/usr/bin/env python3
"""Run isolated PostgreSQL characterization against the repository SQL verbatim."""

from __future__ import annotations

import argparse
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
SCHEMA = ROOT / "cong-no-web-handoff" / "tools" / "pg_ledger_schema.sql"
DATABASE = "webdebit_ledger"
IMAGE = "postgres:18.6@sha256:74935e72241653ca55e0414067e6d8763aceb8a810eb51b452253ec3dcfc4336"
LABEL_TEST = "codex.test"
LABEL_RUN = "codex.run"
LABEL_VALUE = "webdebit-pg-ledger"


class HarnessError(RuntimeError):
    pass


def run(args: list[str], *, input_text: str | None = None, env: dict[str, str] | None = None,
        check: bool = True, timeout: float = 30) -> subprocess.CompletedProcess[str]:
    p = subprocess.run(args, input=input_text, text=True, encoding="utf-8", capture_output=True,
                       env=env, timeout=timeout, check=False)
    if check and p.returncode:
        raise HarnessError(f"command failed ({p.returncode}): {args[0]} {args[1:3]}\n{p.stderr[-3000:]}")
    return p


class PsqlSession:
    def __init__(self, docker: list[str], env: dict[str, str]):
        self.proc = subprocess.Popen(docker + ["exec", "-i", *env_args(env),
            CONTAINER, "psql", "-X", "-qAt", "-v", "ON_ERROR_STOP=1", "-v", "VERBOSITY=verbose", "-U", "postgres",
            "-d", DATABASE], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True, bufsize=1)
        self.lines: queue.Queue[str | None] = queue.Queue()
        self.thread = threading.Thread(target=self._pump, daemon=True)
        self.thread.start()

    def _pump(self) -> None:
        assert self.proc.stdout
        for line in self.proc.stdout:
            self.lines.put(line.rstrip("\r\n"))
        self.lines.put(None)

    def send(self, sql: str) -> None:
        assert self.proc.stdin
        self.proc.stdin.write(sql.rstrip(";") + ";\n")
        self.proc.stdin.flush()

    def read_until(self, marker: str, timeout: float = 10) -> list[str]:
        found: list[str] = []
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                line = self.lines.get(timeout=max(0.01, deadline - time.monotonic()))
            except queue.Empty:
                break
            if line is None:
                raise HarnessError("psql session ended before synchronization marker")
            if line == marker:
                return found
            found.append(line)
        raise HarnessError(f"psql session did not reach synchronization marker {marker!r}")

    def close(self, sql: str = "ROLLBACK") -> None:
        try:
            self.send(sql)
            self.proc.stdin.close()  # type: ignore[union-attr]
            self.proc.wait(timeout=10)
        except Exception:
            self.proc.kill()
            self.proc.wait(timeout=5)
            raise
        if self.proc.returncode:
            err = self.proc.stderr.read() if self.proc.stderr else ""
            raise HarnessError(f"psql session exit {self.proc.returncode}: {err[-2000:]}")


CONTAINER = ""


def env_args(env: dict[str, str]) -> list[str]:
    return [part for k, v in env.items() for part in ("--env", f"{k}={v}")]


def owned_container_id(docker: list[str], name: str, run_id: str,
                       expected_id: str | None = None) -> str | None:
    """Find a container by this run's exact name and labels, then verify its identity."""
    candidates = run(docker + ["ps", "--all", "--quiet", "--no-trunc", "--filter", f"name=^/{name}$",
                              "--filter", f"label={LABEL_TEST}={LABEL_VALUE}",
                              "--filter", f"label={LABEL_RUN}={run_id}"], check=False)
    if candidates.returncode:
        raise HarnessError("could not discover run container for verified cleanup: " + candidates.stderr[-2000:])
    ids = [line.strip() for line in candidates.stdout.splitlines() if line.strip()]
    if not ids:
        return None
    if len(ids) != 1:
        raise HarnessError("refusing container cleanup: exact name and run labels matched multiple IDs")
    container_id = ids[0]
    inspect_result = run(docker + ["inspect", container_id], check=False)
    if inspect_result.returncode:
        raise HarnessError("refusing container cleanup: discovered container could not be inspected")
    inspected = json.loads(inspect_result.stdout)
    if len(inspected) != 1:
        raise HarnessError("refusing container cleanup: inspect did not return exactly one container")
    current = inspected[0]
    labels = current.get("Config", {}).get("Labels") or {}
    if (current.get("Id") != container_id
            or (expected_id is not None and current.get("Id") != expected_id)
            or current.get("Name", "").lstrip("/") != name
            or labels.get(LABEL_TEST) != LABEL_VALUE
            or labels.get(LABEL_RUN) != run_id):
        raise HarnessError("refusing container cleanup: identity/name/labels/run-id did not match")
    return container_id


def cleanup_owned_container(docker: list[str], name: str, run_id: str,
                            expected_id: str | None = None) -> bool:
    container_id = owned_container_id(docker, name, run_id, expected_id)
    if container_id is None:
        return False
    run(docker + ["rm", "--force", container_id])
    return True


def main() -> int:
    global CONTAINER
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", type=Path, default=Path("pg-ledger-characterization.json"))
    ap.add_argument("--timeout", type=int, default=90)
    args = ap.parse_args()
    if shutil.which("docker") is None:
        raise HarnessError("docker CLI not found")
    run_id = uuid.uuid4().hex
    CONTAINER = f"webdebit-pg-ledger-{run_id}"
    volume = f"webdebit-pg-ledger-{run_id}"
    marker = f"codex_run_id={run_id}"
    # Match the tracked SQL content regardless of Git's Windows checkout line endings.
    schema_bytes = SCHEMA.read_bytes().replace(b"\r\n", b"\n")
    schema_sha = hashlib.sha256(schema_bytes).hexdigest()
    report: dict[str, object] = {
        "run_id": run_id, "database": DATABASE, "image": IMAGE,
        "schema_sha256": schema_sha, "schema_path": str(SCHEMA),
        "revision": run(["git", "-C", str(ROOT), "rev-parse", "HEAD"]).stdout.strip(),
        "command": f"python cong-no-web-handoff/tools/test_pg_ledger_schema.py --report {args.report}",
        "cases": [], "cleanup": "not_started",
    }
    docker = ["docker"]
    volume_created = False
    container_created = False
    error: BaseException | None = None
    try:
        run(docker + ["volume", "create", "--label", f"{LABEL_TEST}={LABEL_VALUE}",
                      "--label", f"{LABEL_RUN}={run_id}", volume])
        volume_created = True
        run(docker + ["run", "--detach", "--name", CONTAINER, "--label", f"{LABEL_TEST}={LABEL_VALUE}",
                      "--label", f"{LABEL_RUN}={run_id}", "--network", "none", "--volume", f"{volume}:/var/lib/postgresql",
                      "--env", "POSTGRES_HOST_AUTH_METHOD=trust", IMAGE], timeout=240)
        container_created = True
        inspect = json.loads(run(docker + ["inspect", CONTAINER]).stdout)[0]
        report["container_id"] = inspect.get("Id")
        if inspect.get("Id") is None or inspect.get("Name", "").lstrip("/") != CONTAINER:
            raise HarnessError("container identity did not match this run")
        container_id = inspect["Id"]
        labels = inspect["Config"]["Labels"]
        if labels.get(LABEL_TEST) != LABEL_VALUE or labels.get(LABEL_RUN) != run_id:
            raise HarnessError("container labels did not match this run")
        report["container_id"] = container_id
        inspect_volume = json.loads(run(docker + ["volume", "inspect", volume]).stdout)[0]
        if inspect_volume["Name"] != volume or inspect_volume["Labels"].get(LABEL_TEST) != LABEL_VALUE or inspect_volume["Labels"].get(LABEL_RUN) != run_id:
            raise HarnessError("volume identity/labels did not match this run")
        mounts = [m for m in inspect.get("Mounts", []) if m.get("Name") == volume and m.get("Destination") == "/var/lib/postgresql"]
        if len(mounts) != 1:
            raise HarnessError("container is not attached to exactly this run's PostgreSQL volume")
        deadline = time.monotonic() + args.timeout
        while True:
            ready = run(docker + ["exec", CONTAINER, "pg_isready", "-U", "postgres", "-d", DATABASE], check=False, timeout=10)
            if ready.returncode == 0:
                break
            if time.monotonic() >= deadline:
                raise HarnessError("PostgreSQL readiness timed out")
            time.sleep(0.25)
        # pg_isready also succeeds during the image entrypoint's temporary server.
        # Wait for the official entrypoint's initialization-complete log before using SQL.
        pg_env = {"PGAPPNAME": marker, "PGOPTIONS": "-c statement_timeout=25000"}
        while time.monotonic() < deadline:
            logs = run(docker + ["logs", CONTAINER], check=False, timeout=10)
            if "PostgreSQL init process complete; ready for start up." in logs.stdout + logs.stderr:
                break
            time.sleep(0.25)
        else:
            raise HarnessError("PostgreSQL initialization completion marker timed out")
        initialized = run(docker + ["exec", *env_args(pg_env), CONTAINER, "psql", "-X", "-qAt", "-U", "postgres", "-d", "postgres",
            "-c", "SELECT current_database() || '|' || current_setting('application_name') || '|' || EXISTS (SELECT 1 FROM pg_database WHERE datname='webdebit_ledger')"], check=False)
        if initialized.returncode != 0 or initialized.stdout.strip() != f"postgres|{marker}|false":
            raise HarnessError("default DB/run marker check failed: " + (initialized.stderr[-1000:] or initialized.stdout[-1000:]))
        # The first DDL is the one approved task database, after checking the system DB and run marker.
        pre_ddl_container = json.loads(run(docker + ["inspect", CONTAINER]).stdout)[0]
        pre_ddl_volume = json.loads(run(docker + ["volume", "inspect", volume]).stdout)[0]
        pre_ddl_mounts = [m for m in pre_ddl_container.get("Mounts", []) if m.get("Name") == volume and m.get("Destination") == "/var/lib/postgresql"]
        if (pre_ddl_container.get("Id") != report.get("container_id")
                or pre_ddl_container.get("Name", "").lstrip("/") != CONTAINER
                or pre_ddl_container["Config"]["Labels"].get(LABEL_TEST) != LABEL_VALUE
                or pre_ddl_container["Config"]["Labels"].get(LABEL_RUN) != run_id
                or pre_ddl_volume.get("Name") != volume
                or pre_ddl_volume["Labels"].get(LABEL_TEST) != LABEL_VALUE
                or pre_ddl_volume["Labels"].get(LABEL_RUN) != run_id
                or len(pre_ddl_mounts) != 1):
            raise HarnessError("pre-DDL container/volume identity check failed")
        run(docker + ["exec", *env_args(pg_env), CONTAINER, "psql", "-X", "-v", "ON_ERROR_STOP=1", "-U", "postgres", "-d", "postgres",
                      "-c", "CREATE DATABASE webdebit_ledger"])
        # Mark the task database, then require the durable marker before any schema DDL.
        pre = run(docker + ["exec", *env_args(pg_env), CONTAINER, "psql", "-X", "-qAt", "-U", "postgres", "-d", DATABASE,
                      "-c", "SELECT current_database() || '|' || current_setting('application_name')"]).stdout.strip()
        if pre != f"{DATABASE}|{marker}":
            raise HarnessError("pre-marker database/run check failed")
        run(docker + ["exec", *env_args(pg_env), CONTAINER, "psql", "-X", "-v", "ON_ERROR_STOP=1", "-U", "postgres", "-d", DATABASE,
                      "-c", f"COMMENT ON DATABASE {DATABASE} IS '{marker}'"])
        check_marker = run(docker + ["exec", *env_args(pg_env), CONTAINER, "psql", "-X", "-qAt", "-U", "postgres", "-d", DATABASE,
                      "-c", "SELECT current_database() || '|' || shobj_description((SELECT oid FROM pg_database WHERE datname=current_database()), 'pg_database') || '|' || current_setting('application_name')"]).stdout.strip()
        if check_marker != f"{DATABASE}|{marker}|{marker}":
            raise HarnessError("database marker did not match before schema DDL")

        def assert_target() -> None:
            current = json.loads(run(docker + ["inspect", CONTAINER]).stdout)[0]
            current_labels = current["Config"]["Labels"]
            current_mounts = [m for m in current.get("Mounts", []) if m.get("Name") == volume and m.get("Destination") == "/var/lib/postgresql"]
            if (current.get("Id") != container_id or current.get("Name", "").lstrip("/") != CONTAINER
                    or current_labels.get(LABEL_TEST) != LABEL_VALUE or current_labels.get(LABEL_RUN) != run_id
                    or len(current_mounts) != 1):
                raise HarnessError("container identity/labels/volume changed before DDL")
            marker_value = run(docker + ["exec", *env_args(pg_env), CONTAINER, "psql", "-X", "-qAt", "-U", "postgres", "-d", DATABASE,
                "-c", "SELECT current_database() || '|' || shobj_description((SELECT oid FROM pg_database WHERE datname=current_database()), 'pg_database') || '|' || current_setting('application_name')"]).stdout.strip()
            if marker_value != f"{DATABASE}|{marker}|{marker}":
                raise HarnessError("database/run marker changed before DDL")

        def ddl(sql: str) -> None:
            assert_target()
            run(docker + ["exec", *env_args(pg_env), CONTAINER, "psql", "-X", "-v", "ON_ERROR_STOP=1", "-U", "postgres", "-d", DATABASE, "-c", sql])

        version = run(docker + ["exec", CONTAINER, "psql", "-X", "-qAt", "-U", "postgres", "-d", DATABASE, "-c", "SELECT version()"]).stdout.strip()
        report["postgres_version"] = version
        report["image_digest"] = IMAGE.split("@", 1)[1]
        # Pass the repository file verbatim; psql aborts on the first error.
        assert_target()
        run(docker + ["exec", "-i", *env_args(pg_env), CONTAINER, "psql", "-X", "-v", "ON_ERROR_STOP=1", "-U", "postgres", "-d", DATABASE], input_text=SCHEMA.read_text(encoding="utf-8"))

        # Everything below uses fake fixture values and explicit isolated logins.
        ddl("CREATE ROLE maker_a LOGIN; CREATE ROLE checker_b LOGIN; CREATE ROLE maker_checker LOGIN; GRANT ledger_maker TO maker_a, maker_checker; GRANT ledger_checker TO checker_b, maker_checker")
        setup_sql = """
        INSERT INTO ledger.cutover(singleton,capture_id,as_of,captured_at_utc,source_spreadsheet_id,
          source_workbook_sha256,engine_sha256,period_report_sha256,opening_decision,first_posting_date)
        VALUES(true,'FAKE-CUTOVER','2026-01-31','2026-02-01 00:00:00+00','FAKE-SHEET',repeat('a',64),repeat('b',64),repeat('c',64),'fixture only','2026-02-01');
        INSERT INTO ledger.customer(customer) VALUES ('FAKE CUSTOMER A'),('FAKE CUSTOMER B');
        INSERT INTO ledger.opening(customer,debt_period,balance_vnd,replay_event_count,comparison_status)
        VALUES ('FAKE CUSTOMER A','2026-01',0,1,'NO_BASELINE'),('FAKE CUSTOMER B','2026-01',0,1,'NO_BASELINE');
        """
        run(docker + ["exec", *env_args(pg_env), CONTAINER, "psql", "-X", "-v", "ON_ERROR_STOP=1", "-U", "postgres", "-d", DATABASE, "-c", setup_sql])

        def psql(sql: str, user: str = "postgres", pw: str | None = None, *, check: bool = True) -> subprocess.CompletedProcess[str]:
            env = {"PGAPPNAME": marker, "PGOPTIONS": "-c statement_timeout=25000"}
            if pw is not None:
                env["PGPASSWORD"] = pw
            return run(docker + ["exec", *env_args(env), CONTAINER, "psql", "-X", "-qAt", "-v", "ON_ERROR_STOP=1", "-v", "VERBOSITY=verbose", "-U", user, "-d", DATABASE, "-c", sql], check=check)

        def query(sql: str) -> str:
            return psql(sql).stdout.strip()

        cases: list[dict[str, object]] = report["cases"]  # type: ignore[assignment]
        def record(group: str, name: str, expected: object, actual: object, *, sqlstate: str | None = None, counts: dict[str, object] | None = None) -> None:
            passed = expected == actual
            result = "repro_success" if group == "defect_repro" and passed else ("pass" if passed else "fail")
            cases.append({"group": group, "case": name, "expected": expected, "actual": actual,
                          "sqlstate": sqlstate, "counts": counts if counts is not None else global_counts(),
                          "result": result})
            if not passed:
                raise HarnessError(f"assertion failed: {group}/{name}")

        def counts(pid: int) -> dict[str, object]:
            return json.loads(query("SELECT json_build_object('status',(SELECT status FROM ledger.proposal WHERE proposal_id=" + str(pid) + "),'postings',(SELECT count(*) FROM ledger.posting WHERE proposal_id=" + str(pid) + "),'approve_audits',(SELECT count(*) FROM ledger.audit WHERE proposal_id=" + str(pid) + " AND action='approve'))"))

        def global_counts() -> dict[str, object]:
            return json.loads(query("SELECT json_build_object('postings',(SELECT count(*) FROM ledger.posting),'proposal_statuses',(SELECT json_object_agg(status,n) FROM (SELECT status,count(*) n FROM ledger.proposal GROUP BY status) s),'audits',(SELECT count(*) FROM ledger.audit))"))

        def submit(key: str, kind: str = "charge", lines: str = '[{"customer":"FAKE CUSTOMER A","debt_period":"2026-01","amount_vnd":100}]', total: int = 100, source: str | None = None, user: str = "maker_a", pw: str = "") -> int:
            source = source or f"FAKE-SOURCE-{key[-8:]}"
            sql = ("SELECT ledger.submit_entry('" + key + "','" + kind + "'," + str(total) + ",DATE '2026-02-01',DATE '2026-02-02','" + source + "','FAKE-EVIDENCE','fake test reason','" + lines.replace("'", "''") + "'::jsonb)")
            return int(psql(sql, user, pw).stdout.strip())

        # Characterization: multi-line receipt, bad role, self-approval, duplicate approve, duplicate key.
        multi = submit("fixture-request-multi-0001", "receipt", '[{"customer":"FAKE CUSTOMER A","debt_period":"2026-01","amount_vnd":60},{"customer":"FAKE CUSTOMER B","debt_period":"2026-01","amount_vnd":40}]', 100, "FAKE-SOURCE-MULTI", user="maker_a")
        approved = psql(f"SELECT ledger.approve_entry({multi})", "checker_b")
        record("characterization", "submit_and_approve_multiline", 2, int(approved.stdout.strip()), counts=counts(multi))
        bad_role = psql(f"SELECT ledger.approve_entry({multi})", "maker_a", check=False)
        sqlstate = re.search(r"ERROR:\s+([0-9A-Z]{5}):", bad_role.stderr)
        record("characterization", "wrong_role_rejected", "42501", sqlstate.group(1) if sqlstate else None, sqlstate=sqlstate.group(1) if sqlstate else None, counts=counts(multi))
        self_id = submit("fixture-request-self-0001", user="maker_checker")
        self_fail = psql(f"SELECT ledger.approve_entry({self_id})", "maker_checker", check=False)
        state = re.search(r"ERROR:\s+([0-9A-Z]{5}):", self_fail.stderr)
        record("characterization", "self_approval_rejected", "P0001", state.group(1) if state else None, sqlstate=state.group(1) if state else None, counts=counts(self_id))
        repeat = psql(f"SELECT ledger.approve_entry({multi})", "checker_b", check=False)
        state = re.search(r"ERROR:\s+([0-9A-Z]{5}):", repeat.stderr)
        record("characterization", "repeat_approval_no_second_posting", {"sqlstate":"P0001","postings":2}, {"sqlstate":state.group(1) if state else None,"postings":counts(multi)["postings"]}, sqlstate=state.group(1) if state else None, counts=counts(multi))
        duplicate = psql("SELECT ledger.submit_entry('fixture-request-multi-0001','charge',100,DATE '2026-02-01',DATE '2026-02-02','FAKE-DUPLICATE-SOURCE','FAKE-EVIDENCE','fake test reason','[{\"customer\":\"FAKE CUSTOMER A\",\"debt_period\":\"2026-01\",\"amount_vnd\":100}]'::jsonb)", "maker_a", check=False)
        state = re.search(r"ERROR:\s+([0-9A-Z]{5}):", duplicate.stderr)
        record("characterization", "duplicate_key_unique_violation", "23505", state.group(1) if state else None, sqlstate=state.group(1) if state else None)

        # Defect repro: post-submit owner mutation changes the content that checker approves.
        stale = submit("fixture-request-stale-0001", total=100, user="maker_a")
        submitted_amount = int(query(f"SELECT amount_vnd FROM ledger.proposal_line WHERE proposal_id={stale}"))
        run(docker + ["exec", *env_args(pg_env), CONTAINER, "psql", "-X", "-v", "ON_ERROR_STOP=1", "-U", "postgres", "-d", DATABASE,
                      "-c", f"UPDATE ledger.proposal_line SET amount_vnd=101 WHERE proposal_id={stale}"])
        psql(f"SELECT ledger.approve_entry({stale})", "checker_b")
        posted_amount = int(query(f"SELECT signed_amount_vnd FROM ledger.posting WHERE proposal_id={stale}"))
        record("defect_repro", "owner_mutation_after_submit_posts_unreviewed_content", "repro_success: submitted 100; posted 101", f"repro_success: submitted {submitted_amount}; posted {posted_amount}", counts=counts(stale))

        # Atomicity: fail the approval audit insert after posting/status work; the function statement must roll back.
        atomic = submit("fixture-request-atomic-0001", user="maker_a")
        ddl("CREATE FUNCTION ledger.fixture_fail_approve_audit() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN IF NEW.action='approve' THEN RAISE EXCEPTION 'fixture audit failure'; END IF; RETURN NEW; END $$; CREATE TRIGGER fixture_fail_approve_audit BEFORE INSERT ON ledger.audit FOR EACH ROW EXECUTE FUNCTION ledger.fixture_fail_approve_audit()")
        failed = psql(f"SELECT ledger.approve_entry({atomic})", "checker_b", check=False)
        state = re.search(r"ERROR:\s+([0-9A-Z]{5}):", failed.stderr)
        atomic_counts = counts(atomic)
        record("atomicity", "audit_error_rolls_back_posting_and_status", {"sqlstate":"P0001","status":"pending","postings":0,"approve_audits":0}, {"sqlstate":state.group(1) if state else None,**atomic_counts}, sqlstate=state.group(1) if state else None, counts=atomic_counts)
        ddl("DROP TRIGGER fixture_fail_approve_audit ON ledger.audit; DROP FUNCTION ledger.fixture_fail_approve_audit()")

        # Contention: hold the proposal row, start checker 1, observe checker 1 blocked by this session,
        # then release the holder. checker 1 posts; checker 2 then sees decided state and cannot post again.
        contested = submit("fixture-request-lock-0001", user="maker_a")
        holder = PsqlSession(docker, pg_env)
        holder.send("BEGIN")
        holder.send(f"SELECT proposal_id FROM ledger.proposal WHERE proposal_id={contested} FOR UPDATE")
        holder.send("SELECT 'LOCK_HELD'")
        holder.read_until("LOCK_HELD")
        holder_pid = int(query("SELECT pid FROM pg_stat_activity WHERE application_name='" + marker + "' AND state='idle in transaction' ORDER BY pid DESC LIMIT 1"))
        checker1 = subprocess.Popen(docker + ["exec", *env_args({"PGAPPNAME":f"{marker}-checker1","PGOPTIONS":"-c statement_timeout=25000"}), CONTAINER, "psql", "-X", "-qAt", "-v", "ON_ERROR_STOP=1", "-v", "VERBOSITY=verbose", "-U", "checker_b", "-d", DATABASE, "-c", f"SELECT ledger.approve_entry({contested})"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        checker2 = subprocess.Popen(docker + ["exec", *env_args({"PGAPPNAME":f"{marker}-checker2","PGOPTIONS":"-c statement_timeout=25000"}), CONTAINER, "psql", "-X", "-qAt", "-v", "ON_ERROR_STOP=1", "-v", "VERBOSITY=verbose", "-U", "checker_b", "-d", DATABASE, "-c", f"SELECT ledger.approve_entry({contested})"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        observed: list[str] = []
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            blocked = query("SELECT count(*) || '|' || coalesce(string_agg(pid::text || ':' || pg_blocking_pids(pid)::text, ',' ORDER BY pid), '') FROM pg_stat_activity WHERE usename='checker_b' AND pid <> pg_backend_pid() AND cardinality(pg_blocking_pids(pid)) > 0")
            if blocked.split("|", 1)[0] == "2":
                observed = [blocked]
                break
            time.sleep(0.05)
        holder.close("COMMIT")
        out, err = checker1.communicate(timeout=15)
        checker1_rc = checker1.returncode
        out2, err2 = checker2.communicate(timeout=15)
        checker2_rc = checker2.returncode
        blocker_snapshot = observed[0] if observed else ""
        blocked_checker_count = int(blocker_snapshot.split("|", 1)[0]) if blocker_snapshot else 0
        observed_actual = {"checker_sessions_with_blockers":blocked_checker_count,
                           "holder_pid_in_blocker_chain":str(holder_pid) in blocker_snapshot,
                           "pg_blocking_pids":blocker_snapshot.split("|", 1)[1] if "|" in blocker_snapshot else ""}
        record("contention", "both_checkers_wait_observed_with_pg_blocking_pids", {"checker_sessions_with_blockers":2,"holder_pid_in_blocker_chain":True},
               {"checker_sessions_with_blockers":blocked_checker_count,"holder_pid_in_blocker_chain":observed_actual["holder_pid_in_blocker_chain"]}, counts=counts(contested))
        state1 = re.search(r"ERROR:\s+([0-9A-Z]{5}):", err)
        state2 = re.search(r"ERROR:\s+([0-9A-Z]{5}):", err2)
        final_counts = counts(contested)
        successful = [x for x in (checker1_rc, checker2_rc) if x == 0]
        rejected_states = [s for rc, s in ((checker1_rc, state1.group(1) if state1 else None), (checker2_rc, state2.group(1) if state2 else None)) if rc != 0]
        record("contention", "two_checker_calls_post_once", {"successful_calls":1,"rejected_sqlstates":["P0001"],"postings":1}, {"successful_calls":len(successful),"rejected_sqlstates":rejected_states,"postings":final_counts["postings"]}, sqlstate=rejected_states[0] if rejected_states else None, counts=final_counts)
        report["concurrency_evidence"] = {"holder_pid":holder_pid,"blocking_pids":observed_actual["pg_blocking_pids"],"checker1_stdout":out.strip(),"checker2_stdout":out2.strip(),"checker1_exit":checker1_rc,"checker2_exit":checker2_rc,"checker1_error_sqlstate":state1.group(1) if state1 else None,"checker2_error_sqlstate":state2.group(1) if state2 else None}

        # Posting-date policy (16/10/2026): today in Asia/Ho_Chi_Minh is allowed, any later date is
        # rejected on the submit, approve and reversal paths. Today is computed independently of the
        # schema helper and passed as a literal, so the guard cannot be proved by its own clock.
        def failure(result: subprocess.CompletedProcess[str]) -> dict[str, object]:
            found = re.search(r"ERROR:\s+([0-9A-Z]{5}):\s*(.+)", result.stderr)
            return {"exit": result.returncode, "sqlstate": found.group(1) if found else None,
                    "message": found.group(2).strip() if found else None}

        def submit_dated(key: str, posting_date: str) -> subprocess.CompletedProcess[str]:
            return psql("SELECT ledger.submit_entry('" + key + "','charge',100,DATE '2026-02-01'," + posting_date
                        + ",'FAKE-SOURCE-" + key[-8:] + "','FAKE-EVIDENCE','fake test reason',"
                        + "'[{\"customer\":\"FAKE CUSTOMER A\",\"debt_period\":\"2026-01\",\"amount_vnd\":100}]'::jsonb)",
                        "maker_a", check=False)

        def proposal_count() -> int:
            return int(query("SELECT count(*) FROM ledger.proposal"))

        original_posting = int(query(f"SELECT min(posting_id) FROM ledger.posting WHERE proposal_id={multi}"))
        vn_today = "(now() AT TIME ZONE 'Asia/Ho_Chi_Minh')::date"
        today = "DATE '" + query(f"SELECT {vn_today}") + "'"
        tomorrow = "DATE '" + query(f"SELECT {vn_today} + 1") + "'"

        # Today must still be accepted: a guard that rejects the ordinary case is not a passing guard.
        today_result = submit_dated("fixture-request-today-0001", today)
        today_id = int(today_result.stdout.strip()) if today_result.returncode == 0 else None
        record("posting_date", "today_posting_date_accepted", {"exit":0,"status":"pending"},
               {"exit":today_result.returncode,"status":counts(today_id)["status"] if today_id else None})
        before = proposal_count()
        record("posting_date", "future_posting_date_rejected_on_submit",
               {"exit":1,"sqlstate":"P0001","message":"missing or invalid posting evidence/date/lines","new_proposals":0},
               {**failure(submit_dated("fixture-request-future-0001", tomorrow)),"new_proposals":proposal_count() - before})
        # Owner-inserted pending row simulates a proposal whose date passed submit under an older function.
        future_id = int(query("INSERT INTO ledger.proposal(request_key,kind,total_vnd,event_date,posting_date,source_ref,evidence_ref,reason,maker) "
                              "VALUES ('fixture-request-future-approve-0001','charge',100,DATE '2026-02-01'," + tomorrow + ","
                              "'FAKE-SOURCE-FUTURE','FAKE-EVIDENCE','fake test reason','maker_a') RETURNING proposal_id"))
        psql(f"INSERT INTO ledger.proposal_line(proposal_id,line_no,customer,debt_period,amount_vnd) VALUES ({future_id},1,'FAKE CUSTOMER A','2026-01',100)")
        record("posting_date", "future_posting_date_rejected_on_approve",
               {"exit":1,"sqlstate":"P0001","message":"posting date is in the future","status":"pending","postings":0},
               {**failure(psql(f"SELECT ledger.approve_entry({future_id})", "checker_b", check=False)),
                "status":counts(future_id)["status"],"postings":counts(future_id)["postings"]}, counts=counts(future_id))
        before = proposal_count()
        record("posting_date", "future_posting_date_rejected_on_reversal",
               {"exit":1,"sqlstate":"P0001","message":"invalid reversal request","new_proposals":0},
               {**failure(psql(f"SELECT ledger.request_reversal('fixture-request-future-rev-0001',{original_posting},{tomorrow},'FAKE-EVIDENCE','fake test reason')", "maker_a", check=False)),
                "new_proposals":proposal_count() - before})

        report["exit_code"] = 0
    except BaseException as exc:
        error = exc
        report["error"] = f"{type(exc).__name__}: {exc}"
        if container_created:
            diagnostic = run(docker + ["logs", "--tail", "40", CONTAINER], check=False, timeout=10)
            # PostgreSQL's startup log excludes the container environment and test credentials.
            report["postgres_startup_log"] = (diagnostic.stdout + diagnostic.stderr)[-6000:]
        report["exit_code"] = 1
    finally:
        # Never remove a resource unless its unique name, exact label and run-id all verify.
        try:
            cleanup_container_removed = cleanup_owned_container(
                docker, CONTAINER, run_id,
                str(report["container_id"]) if report.get("container_id") else None)
            if volume_created:
                current_volume = json.loads(run(docker + ["volume", "inspect", volume]).stdout)[0]
                if current_volume["Name"] != volume or current_volume["Labels"].get(LABEL_TEST) != LABEL_VALUE or current_volume["Labels"].get(LABEL_RUN) != run_id:
                    raise HarnessError("refusing volume cleanup: identity/labels/run-id changed")
                run(docker + ["volume", "rm", volume])
            report["cleanup"] = "verified_and_removed" if cleanup_container_removed or volume_created else "nothing_created"
        except BaseException as cleanup_error:
            report["cleanup"] = f"failed: {type(cleanup_error).__name__}: {cleanup_error}"
            error = cleanup_error
            report["exit_code"] = 1
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return int(report.get("exit_code", 1))


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except HarnessError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
