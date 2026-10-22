"""Direct Unix socket API and loader checks in one disposable fake database."""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path
from unittest.mock import patch

import test_pg_v7_grants as grants
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
    inspect_owned,
    inspect_volume,
    require,
    run,
)
from v7_ledger_api import PsqlDirect
from v7_load_direct import DirectPg
from v7_load_direct import main as load_main


def direct(pg, database=DATABASE, role="v7_app"):
    return PsqlDirect("/var/run/postgresql", database, role,
        psql_command=pg.psql_command())


def check_startup(pg):
    direct(pg)
    for role in ("postgres", "v7_excess"):
        try:
            direct(pg, role=role)
        except ValueError:
            continue
        raise HarnessError("privileged role accepted")


def check_api(pg):
    with patch.multiple(grants, Psql=lambda name, database, role: direct(pg, database, role)):
        grants.check_api(pg)


def check_loader(pg):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))
    import v7_export_clean as exporter
    from test_v7_load_real_copy import fixture
    pg.sql("CREATE DATABASE v7_direct_load", database="postgres")
    pg.sql("\n".join(line for line in SCHEMA.read_text(encoding="utf-8").splitlines() if not line.startswith("CREATE ROLE ")), database="v7_direct_load")
    pg.sql(FUNCTIONS.read_text(encoding="utf-8"), database="v7_direct_load")
    pg.sql("CREATE ROLE v7_loader LOGIN IN ROLE sokhach_owner")
    def factory(socket, database, role, **kwargs):
        return DirectPg(socket, database, role, psql_command=pg.psql_command(), **kwargs)
    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp)
        fixture(folder)
        books, digests = exporter.build_books(folder, folder / "source-google-export.xlsx", ())
        # MH-01: TONG parsing is unit-tested; here the bundle carries a commodity into the DB.
        books[0]["commodity"], books[0]["transport_mode"] = "Sầu riêng", "CANG"
        out = folder / "clean"
        exporter.export(books, digests, out, Path("fake.xlsx"), ())
        args = ["--from-clean", str(out), "--database", "v7_direct_load", "--loader-role", "v7_loader"]
        def count():
            return pg.sql("SELECT count(*) FROM sokhach.customer", database="v7_direct_load").stdout.strip()
        require(load_main(args, pg_factory=factory) == 0 and count() == "0", "plan wrote data")
        require(load_main(args + ["--apply"], pg_factory=factory) == 0, "apply failed")
        before = count()
        require(before != "0", "apply loaded nothing")
        ledger = direct(pg, "v7_direct_load").run("get_ledger", {"customer_id": 1}, "fake")
        require(ledger["total_outstanding_vnd"] == str(books[0]["anchor"]), "loaded ledger differs")
        listed = direct(pg, "v7_direct_load").run("list_customers", {}, "fake")["customers"]
        require([(r["commodity"], r["transport_mode"]) for r in listed] == [("Sầu riêng", "CANG")],
                "loaded commodity differs")
        require(load_main(args + ["--apply"], pg_factory=factory) == 1, "nonempty accepted")
        require(load_main(args + ["--apply", "--allow-nonempty"], pg_factory=factory) == 0 and count() == before, "repeat duplicated data")
        pg.sql("CREATE DATABASE v7_direct_empty", database="postgres")
        empty = args.copy()
        empty[empty.index("v7_direct_load")] = "v7_direct_empty"
        require(load_main(empty + ["--apply"], pg_factory=factory) == 1, "missing schema accepted")
        require(pg.sql("SELECT count(*) FROM pg_namespace WHERE nspname='sokhach'", database="v7_direct_empty").stdout.strip() == "0", "loader created schema")


CHECKS = {"startup": check_startup, "api": check_api, "loader": check_loader}
CASES = [{"id": "direct." + name, "label": "BEHAVIOR", "title": title, "check": name,
          "functions": (), "open_reason": ""} for name, title in [
    ("startup", "Socket startup and privileged role rejection"),
    ("api", "All API operations through direct socket"),
    ("loader", "Fake bundle plan, atomic apply, repeat and missing schema")]]

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
    name = f"webdebit-v7-direct-{run_id}"
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
        pg.sql("CREATE ROLE v7_app LOGIN IN ROLE sokhach_app; CREATE ROLE v7_reader LOGIN IN ROLE sokhach_reader; CREATE ROLE v7_excess LOGIN CREATEDB")
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
