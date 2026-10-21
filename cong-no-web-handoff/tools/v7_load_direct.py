"""Plan or atomically load a manifest-bound clean bundle through a local Unix socket."""

from __future__ import annotations

import argparse
import json
import os
import queue
import subprocess
import tempfile
import threading
import uuid
from pathlib import Path

from test_pg_v7_backend import call, lit, version
from v7_load_real_copy import LoadError, api, clean_data, import_one, report


class DirectPg:
    def __init__(
        self,
        socket_dir: str,
        database: str,
        role: str,
        *,
        actor="v7-loader",
        psql_command=None,
    ):
        self.connection = api.PsqlDirect(
            socket_dir, database, role, psql_command=psql_command
        )
        self.actor = actor
        self.stderr = tempfile.TemporaryFile(mode="w+t", encoding="utf-8")  # noqa: SIM115 - session lifetime
        env = os.environ.copy()
        env["PGOPTIONS"] = "-c statement_timeout=15000 -c lock_timeout=12000"
        self.process = subprocess.Popen(
            self.connection.psql_command
            + [
                "-X",
                "-qAt",
                "-v",
                "ON_ERROR_STOP=1",
                "-h",
                socket_dir,
                "-U",
                role,
                "-d",
                database,
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=self.stderr,
            text=True,
            encoding="utf-8",
            env=env,
        )
        self.output = queue.Queue()
        def read_output():
            for line in self.process.stdout:
                self.output.put(line)
            self.output.put("")
        threading.Thread(target=read_output, daemon=True).start()
        try:
            self.sql("BEGIN; SET LOCAL sokhach.actor=" + lit(actor))
        except Exception:
            self.close()
            raise

    def sql(self, sql, *, user=None, check=True, database=None):
        if user is not None or database is not None:
            raise LoadError("TARGET_OVERRIDE_FORBIDDEN")
        marker = uuid.uuid4().hex
        # call() supplies transaction wrappers; keep all calls in this one transaction.
        if sql.startswith("BEGIN; SET LOCAL sokhach.actor = "):
            sql = sql[sql.index(";", sql.index("SET LOCAL")) + 1 :].rsplit(
                "; COMMIT", 1
            )[0]
        self.process.stdin.write(
            sql.rstrip().rstrip(";") + ";\n\\echo " + marker + "\n"
        )
        self.process.stdin.flush()
        rows = []
        while True:
            try:
                line = self.output.get(timeout=25)
            except queue.Empty:
                raise LoadError("DIRECT_RESULT_UNKNOWN") from None
            if not line:
                self.stderr.seek(0)
                error = self.stderr.read()
                import re
                match = re.search(r"\bCUTOVER_[A-Z_]+\b", error)
                raise LoadError(match.group() if match else "DIRECT_SQL_FAILED")
            if line.strip() == marker:
                break
            rows.append(line)
        return subprocess.CompletedProcess([], 0, "".join(rows), "")

    def value(self, sql, *, user=None):
        return self.sql(sql, user=user).stdout.strip()

    def true(self, sql, reason):
        if self.value("SELECT (" + sql + ")") != "t":
            raise LoadError(reason)

    def rejects(self, sql, *, user=None, message=""):
        if user is not None:
            raise LoadError("TARGET_OVERRIDE_FORBIDDEN")
        c = self.connection
        result = subprocess.run(c.psql_command + ["-X", "-qAt", "-v", "ON_ERROR_STOP=1",
            "-h", c.socket_dir, "-U", c.user, "-d", c.database],
            input="BEGIN; " + sql + "; ROLLBACK;\n", capture_output=True, text=True,
            timeout=25, check=False, env={**os.environ, "PGOPTIONS": "-c statement_timeout=15000 -c lock_timeout=12000"})
        if not result.returncode or (message and message not in result.stderr):
            raise LoadError("EXPECTED_REJECTION_MISSING")

    def close(self, *, commit=False):
        try:
            if self.process.poll() is None:
                self.process.stdin.write("COMMIT;\n" if commit else "ROLLBACK;\n")
                self.process.stdin.close()
                try:
                    self.process.wait(timeout=25)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait()
                    raise LoadError("DIRECT_RESULT_UNKNOWN") from None
                if commit and self.process.returncode:
                    raise LoadError("DIRECT_COMMIT_FAILED")
        finally:
            self.process.stdout.close()
            self.stderr.close()


def load(pg, books, digests, manifest):
    pg.sql("SELECT pg_advisory_xact_lock(728721)")
    counts = json.loads(
        pg.value(
            "SELECT json_build_object('customers',(SELECT count(*) FROM sokhach.customer),"
            "'cutovers',(SELECT count(*) FROM sokhach.cutover))"
        )
    )
    return counts


def execute(pg, books, digests, manifest):
    digest = digests["manifest.json"]
    existing = pg.value(
        "SELECT id FROM sokhach.cutover WHERE source_sha256=" + lit(digest)
    )
    if existing:
        pg.true(
            "EXISTS (SELECT 1 FROM sokhach.cutover WHERE id="
            + existing
            + " AND status='active')",
            "CUTOVER_NOT_ACTIVE",
        )
        for item in books:
            item["status"] = "active"
        return
    cutover = int(
        pg.value(
            "INSERT INTO sokhach.cutover(name,source,source_sha256,frozen_at,control_total_vnd,created_by) VALUES "
            "('clean direct load','clean manifest',"
            + lit(digest)
            + ","
            + lit(manifest["frozen_at"])
            + "::timestamptz,"
            + str(manifest["control_total_vnd"])
            + ","
            + lit(pg.actor)
            + ") RETURNING id"
        )
    )
    for index, item in enumerate(books, 1):
        item["status"] = import_one(pg, item, digest, index, cutover=cutover)
    call(pg, "verify_cutover", cutover, digest + "-verify", None, actor=pg.actor)
    call(pg, "activate_cutover", cutover, digest + "-activate", None, actor=pg.actor)
    for index, item in enumerate(books, 1):
        call(
            pg,
            "activate_cutover_customer",
            item["id"],
            cutover,
            version(pg, item["id"]),
            digest + f"-active-{index}",
            None,
            actor=pg.actor,
        )
        item["status"] = "active"


def main(argv=None, *, pg_factory=DirectPg):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--from-clean", type=Path, required=True)
    parser.add_argument("--socket-dir", default="/var/run/postgresql")
    parser.add_argument("--database", required=True)
    parser.add_argument("--loader-role", required=True)
    parser.add_argument("--actor", default="v7-loader")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--allow-nonempty", action="store_true")
    args = parser.parse_args(argv)
    if args.database == "webdebit_ledger":
        parser.error("legacy database forbidden")
    if (
        not args.actor.strip()
        or len(args.actor) > 252
        or any(ord(c) < 32 for c in args.actor)
    ):
        parser.error("invalid actor")
    pg = None
    try:
        books, digests, manifest = clean_data(args.from_clean)
        pg = pg_factory(
            args.socket_dir, args.database, args.loader_role, actor=args.actor
        )
        counts = load(pg, books, digests, manifest)
        plan = report(books, digests, uuid.uuid4().hex)
        plan.update(
            phase="PLAN",
            books=len(books),
            openings=sum(len(b["openings"]) for b in books),
            database=args.database,
            role=args.loader_role,
            socket_dir=args.socket_dir,
            target=counts,
        )
        print(json.dumps(plan, ensure_ascii=True), flush=True)
        if not args.apply:
            return 0
        if any(counts.values()) and not args.allow_nonempty:
            raise LoadError("TARGET_NONEMPTY")
        execute(pg, books, digests, manifest)
        pg.close(commit=True)
        pg = None
        result = report(books, digests, plan["run_id"], loaded=True)
        folder = Path(tempfile.gettempdir()) / "v7-direct-reports"
        folder.mkdir(exist_ok=True)
        (folder / (plan["run_id"] + ".json")).write_text(
            json.dumps(result), encoding="utf-8"
        )
        print(json.dumps(result), flush=True)
        return 0
    except (OSError, ValueError, LoadError) as exc:
        print(json.dumps({"reason": str(exc) if isinstance(exc, LoadError) else "DIRECT_LOAD_FAILED"}))
        return 1
    finally:
        if pg is not None:
            pg.close()


if __name__ == "__main__":
    raise SystemExit(main())
