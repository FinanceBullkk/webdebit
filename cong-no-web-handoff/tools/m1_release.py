"""Build and check the private M1 viewer runtime package. Neither command deploys anything.

build      Copy the allowlisted runtime files from one git commit into a new directory outside
           the worktree and write MANIFEST.json (commit, tree, SHA-256 of every file).
preflight  Read-only. Verify a package against its manifest, optionally compare an installed
           directory, and optionally check (SELECT only) that the viewer role can read every view the
           viewer queries. Without the database check the result is never "ready_for_deploy".
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

# Runtime of the read-only viewer only. Fixtures, SQL, tests, previews, captures and docs stay out.
RUNTIME_FILES = (
    "cong-no-web-handoff/web/ledger_app.py",
    "cong-no-web-handoff/web/ledger_db.py",
    "cong-no-web-handoff/web/style.css",
)
PACKAGE_STRIP = "cong-no-web-handoff/"
MANIFEST = "MANIFEST.json"
FORMAT = 1
# Everything the viewer reads in the pilot database (HistoryDB). The three M1 summary views feed
# /health and /exceptions: without SELECT on them /health answers 503. The two web views feed the
# customer pages. See docs/m1-acl-proposal.md.
M1_VIEWS = ("pilot.m1_provenance", "pilot.m1_exception_detail", "pilot.m1_customer_diff")
WEB_VIEWS = ("pilot.web_period_event", "pilot.web_source_row")
VIEWER_VIEWS = M1_VIEWS + WEB_VIEWS
PILOT_SCHEMA = "pilot"
HEX40 = re.compile(r"[0-9a-f]{40}")
HEX64 = re.compile(r"[0-9a-f]{64}")


class ReleaseError(RuntimeError):
    pass


def package_path(source_path: str) -> str:
    return source_path.removeprefix(PACKAGE_STRIP)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def git(repo: Path, *args: str) -> bytes:
    result = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, check=False)
    if result.returncode:
        raise ReleaseError(f"git {args[0]} failed: {result.stderr.decode('utf-8', 'replace').strip()}")
    return result.stdout


def check_python(path: str, data: bytes) -> None:
    if path.endswith(".py"):
        try:
            ast.parse(data, filename=path)  # parse only; never import or execute
        except SyntaxError as exc:
            raise ReleaseError(f"{path}: syntax error line {exc.lineno}") from exc


def build(repo: Path, out_dir: Path, commit: str = "HEAD") -> dict:
    repo = repo.resolve()
    out_dir = out_dir.resolve()
    if out_dir == repo or repo in out_dir.parents:
        raise ReleaseError("Package must be written outside the source repository")
    if out_dir.exists() and (not out_dir.is_dir() or any(out_dir.iterdir())):
        raise ReleaseError("Package directory must be empty or new")
    commit_sha = git(repo, "rev-parse", "--verify", f"{commit}^{{commit}}").decode().strip()
    tree_sha = git(repo, "rev-parse", f"{commit_sha}^{{tree}}").decode().strip()
    # Only HEAD is compared with the working tree; another commit is read from git as it is.
    if (commit_sha == git(repo, "rev-parse", "HEAD").decode().strip()
            and git(repo, "status", "--porcelain", "--", *RUNTIME_FILES).decode().strip()):
        raise ReleaseError("Runtime files differ from the working tree; commit or revert them first")
    files, contents = [], {}
    for source in RUNTIME_FILES:
        try:
            data = git(repo, "show", f"{commit_sha}:{source}")
        except ReleaseError as exc:
            raise ReleaseError(f"Runtime file missing in commit: {source}") from exc
        check_python(source, data)
        contents[package_path(source)] = data
        files.append({"path": package_path(source), "sha256": sha256(data), "bytes": len(data)})
    manifest = {
        "format": FORMAT,
        "commit": commit_sha,
        "tree": tree_sha,
        "files": files,
        "notes": ["Read-only viewer runtime; not a database migration.",
                  "Grant SELECT on the three M1 views before deploying, or /health returns 503."],
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, data in contents.items():
        target = out_dir / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    (out_dir / MANIFEST).write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n",
                                    encoding="utf-8", newline="\n")
    return manifest


def read_manifest(package: Path) -> dict:
    try:
        manifest = json.loads((package / MANIFEST).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReleaseError("MANIFEST.json missing or invalid") from exc
    if (not isinstance(manifest, dict) or manifest.get("format") != FORMAT
            or not HEX40.fullmatch(str(manifest.get("commit", "")))
            or not HEX40.fullmatch(str(manifest.get("tree", "")))
            or not isinstance(manifest.get("files"), list)):
        raise ReleaseError("MANIFEST.json has an unexpected shape")
    return manifest


def verify_package(package: Path) -> tuple[dict, dict[str, bytes]]:
    manifest = read_manifest(package)
    entries = manifest["files"]
    paths = [entry.get("path") if isinstance(entry, dict) else None for entry in entries]
    if sorted(paths, key=str) != sorted(package_path(p) for p in RUNTIME_FILES):
        raise ReleaseError("Manifest files differ from the runtime allowlist")
    present = sorted(p.relative_to(package).as_posix() for p in package.rglob("*") if not p.is_dir())
    if present != sorted([*paths, MANIFEST]):
        extra = sorted(set(present) - set(paths) - {MANIFEST})
        missing = sorted(set(paths) - set(present))
        raise ReleaseError(f"Package contents differ from manifest; extra={extra} missing={missing}")
    contents = {}
    for entry in entries:
        path = package / entry["path"]
        if path.is_symlink():
            raise ReleaseError(f"{entry['path']}: symlinks are not allowed")
        data = path.read_bytes()
        if not HEX64.fullmatch(str(entry.get("sha256", ""))) or sha256(data) != entry["sha256"]:
            raise ReleaseError(f"{entry['path']}: SHA-256 differs from manifest")
        if entry.get("bytes") != len(data):
            raise ReleaseError(f"{entry['path']}: size differs from manifest")
        check_python(entry["path"], data)
        contents[entry["path"]] = data
    return manifest, contents


def compare_installed(installed: Path, manifest: dict) -> list[dict]:
    rows = []
    for entry in manifest["files"]:
        path = installed / entry["path"]
        if not path.is_file():
            rows.append({"path": entry["path"], "state": "missing", "installed_sha256": None})
            continue
        digest = sha256(path.read_bytes())
        rows.append({"path": entry["path"], "state": "identical" if digest == entry["sha256"] else "different",
                     "installed_sha256": digest})
    return rows


def psql_rows(psql: str, dbname: str, sql: str) -> list[dict]:
    result = subprocess.run([psql, "-X", "-w", "-q", "-A", "-t", "-v", "ON_ERROR_STOP=1", "-d", dbname, "-c", sql],
                            capture_output=True, text=True, encoding="utf-8", timeout=15, check=False)
    if result.returncode:
        raise ReleaseError("database check failed: " + result.stderr.strip().splitlines()[-1][:200]
                           if result.stderr.strip() else "database check failed")
    return json.loads(result.stdout.strip() or "[]")


def probe(rows, psql: str, dbname: str, sql: str) -> tuple[str, str, list]:
    try:
        found = rows(psql, dbname, sql)
    except (ReleaseError, OSError, subprocess.TimeoutExpired, json.JSONDecodeError) as exc:
        text = str(exc) or exc.__class__.__name__
        return ("denied" if "permission denied" in text.lower() else "error"), text, []
    return "ok", "", found


def check_viewer_access(dbname: str, psql: str = "psql", rows=psql_rows) -> dict:
    """Read-only, run as the viewer role: connect, schema USAGE, then a real SELECT ... LIMIT 0
    on every view the viewer reads (a catalog privilege flag alone is not enough)."""
    state, detail, found = probe(rows, psql, dbname,
                                 f"SELECT json_build_array(has_schema_privilege('{PILOT_SCHEMA}', 'USAGE'))")
    if state != "ok" or found not in ([True], [False]):
        return {"status": "error", "detail": detail or "unexpected schema check result",
                "connect": False, "schema_usage": None, "views": {}}
    views, details = {}, {}
    for view in VIEWER_VIEWS:
        views[view], detail, _ = probe(rows, psql, dbname, f"SELECT 1 FROM {view} LIMIT 0")
        if detail:
            details[view] = detail
    states = set(views.values())
    status = ("error" if "error" in states else
              "denied" if "denied" in states or found == [False] else "ok")
    result = {"status": status, "connect": True, "schema_usage": found == [True], "views": views}
    if details:
        result["detail"] = details
    return result


def preflight(package: Path, installed: Path | None = None, db: str | None = None,
              psql: str = "psql", rows=psql_rows) -> dict:
    manifest, _ = verify_package(package)
    result = {"package": "ok", "commit": manifest["commit"], "tree": manifest["tree"],
              "files": {entry["path"]: entry["sha256"] for entry in manifest["files"]},
              "installed": compare_installed(installed, manifest) if installed else "not_checked",
              "acl": check_viewer_access(db, psql, rows) if db else {"status": "not_checked", "views": {}}}
    result["ready_for_deploy"] = result["acl"]["status"] == "ok"
    if result["acl"]["status"] in ("denied", "error"):
        result["warning"] = "Do not deploy: the viewer cannot read every view it queries; with the M1 summary views missing /health would return 503."
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    b = sub.add_parser("build", help="write the runtime package for a commit")
    b.add_argument("out_dir", type=Path)
    b.add_argument("--commit", default="HEAD")
    b.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[2])
    p = sub.add_parser("preflight", help="read-only package, installed-copy and ACL check")
    p.add_argument("package", type=Path)
    p.add_argument("--installed", type=Path, help="directory of the currently installed viewer, compared read-only")
    p.add_argument("--check-db", metavar="DBNAME", help="read-only SELECT ... LIMIT 0 on every viewer view; run as the viewer role")
    p.add_argument("--psql", default="psql")
    args = parser.parse_args(argv)
    try:
        if args.command == "build":
            manifest = build(args.repo, args.out_dir, args.commit)
            print(json.dumps({"commit": manifest["commit"], "tree": manifest["tree"],
                              "files": len(manifest["files"])}))
            return 0
        if args.check_db is not None and not re.fullmatch(r"[A-Za-z0-9_]+", args.check_db):
            raise ReleaseError("invalid database name")
        result = preflight(args.package, args.installed, args.check_db, args.psql)
    except ReleaseError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["ready_for_deploy"] else 1


if __name__ == "__main__":
    sys.exit(main())
