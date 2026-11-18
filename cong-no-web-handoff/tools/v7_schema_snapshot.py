#!/usr/bin/env python3
"""Sinh trạng thái hiện hành của lược đồ V7 (`sokhach`) ra một file đọc được, thứ tự ổn định.

Dựng PostgreSQL 18.6 dùng một lần đúng như harness (`pg_v7_harness.disposable_database`: `schema-draft.sql`,
`v7_backend_functions.sql`, migration Sheet), rồi đọc catalog: kiểu, bảng (cột, ràng buộc, chỉ mục, trigger, chú
thích, quyền), view, hàm (`pg_get_functiondef`, sắp theo tên + chữ ký, kèm quyền). Chuỗi migration lên `hao` cho cùng
định nghĩa hàm/view/cột/ràng buộc: `test_pg_v7_backend.py --migration-test` đã so catalog hai đường.

File sinh ra (`OUTPUT`) chỉ để đọc; đuôi `.pgsql` và chỗ đặt ngoài gói release nên không rơi vào cổng SQL của Deploy hao
và luật nghiệp vụ, runbook không nạp nó. Cần Docker:

    python cong-no-web-handoff/tools/v7_schema_snapshot.py           # sinh lại file
    python cong-no-web-handoff/tools/v7_schema_snapshot.py --check   # so với file trong repo, lệch thì exit 1
"""

from __future__ import annotations

import argparse
import difflib
import json
import sys
from pathlib import Path

from pg_v7_harness import IMAGE, ROOT, HarnessError, Pg, disposable_database

OUTPUT = ROOT / "cong-no-web-handoff" / "schema" / "v7_schema_current.pgsql"
REGENERATE = "python cong-no-web-handoff/tools/v7_schema_snapshot.py"
SCHEMA_NAME = "sokhach"

HEADER = f"""\
-- ============================================================================================================
-- SINH TỰ ĐỘNG, không sửa tay, không chạy trên hao.
-- Trạng thái hiện hành của lược đồ V7 `{SCHEMA_NAME}` sau khi nạp đủ như harness PostgreSQL: specs/v7-backend/schema-draft.sql
-- → cong-no-web-handoff/tools/v7_backend_functions.sql → migrations/2026-10-24-v7-sheet-cross-customer.sql.
-- Mỗi hàm/view/bảng xuất hiện đúng một lần, bản đang có hiệu lực; tìm theo tên, ví dụ "FUNCTION sokhach.get_ledger(".
-- Sửa SQL ở file nguồn + migration, rồi sinh lại:  {REGENERATE}
-- CI (job postgres-v7-backend) sinh lại và so với file này; lệch thì đỏ.
-- File chỉ để đọc: thiếu vai trò, thứ tự phụ thuộc và dữ liệu, không phải đường triển khai.
-- Ảnh PostgreSQL: {IMAGE.split('@')[0]}
-- ============================================================================================================
"""

# Mỗi truy vấn trả một mảng JSON đã sắp; Python chỉ ghép chữ.
Q_SCHEMA = f"""
SELECT json_build_object(
  'owner', pg_get_userbyid(n.nspowner),
  'acl', (SELECT coalesce(json_agg(json_build_array(CASE a.grantee WHEN 0 THEN 'PUBLIC' ELSE pg_get_userbyid(a.grantee) END,
                                                     a.privilege_type) ORDER BY 1,2), '[]') FROM aclexplode(n.nspacl) a
          WHERE a.grantee <> n.nspowner),
  'comment', obj_description(n.oid, 'pg_namespace'),
  'default_acl', (SELECT coalesce(json_agg(json_build_array(pg_get_userbyid(d.defaclrole), d.defaclnamespace <> 0,
                                  d.defaclobjtype::text, d.defaclacl::text[])), '[]')
                  FROM pg_default_acl d WHERE d.defaclnamespace = n.oid OR d.defaclnamespace = 0))
FROM pg_namespace n WHERE n.nspname = '{SCHEMA_NAME}'
"""

Q_OTHER_SCHEMAS = """
SELECT coalesce(json_agg(nspname ORDER BY nspname), '[]') FROM pg_namespace
WHERE nspname NOT IN ('pg_catalog','information_schema','pg_toast','public') AND nspname NOT LIKE 'pg\\_%'
"""

Q_TYPES = f"""
SELECT coalesce(json_agg(x ORDER BY x->>'name'), '[]') FROM (
  SELECT json_build_object('name', t.oid::regtype::text, 'kind', t.typtype::text,
    'labels', (SELECT json_agg(e.enumlabel ORDER BY e.enumsortorder) FROM pg_enum e WHERE e.enumtypid = t.oid),
    'base', CASE WHEN t.typtype = 'd' THEN format_type(t.typbasetype, t.typtypmod) END,
    'notnull', t.typnotnull,
    'checks', (SELECT json_agg(pg_get_constraintdef(c.oid) ORDER BY c.conname) FROM pg_constraint c WHERE c.contypid = t.oid),
    'comment', obj_description(t.oid, 'pg_type')) AS x
  FROM pg_type t
  WHERE t.typnamespace = '{SCHEMA_NAME}'::regnamespace AND t.typtype IN ('e','d')
) s
"""

ACL_REL = """(SELECT coalesce(json_agg(json_build_array(CASE a.grantee WHEN 0 THEN 'PUBLIC' ELSE pg_get_userbyid(a.grantee) END,
                a.privilege_type) ORDER BY 1,2), '[]') FROM aclexplode(c.relacl) a WHERE a.grantee <> c.relowner)"""

Q_RELATIONS = f"""
SELECT coalesce(json_agg(x ORDER BY x->>'kind', x->>'name'), '[]') FROM (
  SELECT json_build_object(
    'name', c.oid::regclass::text,
    'kind', c.relkind::text,
    'owner', pg_get_userbyid(c.relowner),
    'acl', {ACL_REL},
    'rls', c.relrowsecurity,
    'comment', obj_description(c.oid, 'pg_class'),
    'view', CASE WHEN c.relkind IN ('v','m') THEN pg_get_viewdef(c.oid) END,
    'columns', (SELECT json_agg(json_build_object(
                  'name', a.attname, 'type', format_type(a.atttypid, a.atttypmod), 'notnull', a.attnotnull,
                  'default', pg_get_expr(d.adbin, d.adrelid), 'identity', a.attidentity::text,
                  'generated', a.attgenerated::text, 'comment', col_description(c.oid, a.attnum)) ORDER BY a.attnum)
                FROM pg_attribute a LEFT JOIN pg_attrdef d ON d.adrelid = a.attrelid AND d.adnum = a.attnum
                WHERE a.attrelid = c.oid AND a.attnum > 0 AND NOT a.attisdropped),
    'constraints', (SELECT json_agg(json_build_array(k.conname, pg_get_constraintdef(k.oid)) ORDER BY k.conname)
                    FROM pg_constraint k WHERE k.conrelid = c.oid AND k.contype <> 'n'),
    'indexes', (SELECT json_agg(pg_get_indexdef(i.indexrelid) ORDER BY i.indexrelid::regclass::text COLLATE "C")
                FROM pg_index i WHERE i.indrelid = c.oid
                  AND NOT EXISTS (SELECT 1 FROM pg_constraint k WHERE k.conindid = i.indexrelid AND k.conrelid = c.oid)),
    'triggers', (SELECT json_agg(pg_get_triggerdef(t.oid) ORDER BY t.tgname)
                 FROM pg_trigger t WHERE t.tgrelid = c.oid AND NOT t.tgisinternal),
    'policies', (SELECT json_agg(json_build_array(p.polname, p.polcmd::text, pg_get_expr(p.polqual, p.polrelid),
                                                  pg_get_expr(p.polwithcheck, p.polrelid)) ORDER BY p.polname)
                 FROM pg_policy p WHERE p.polrelid = c.oid)) AS x
  FROM pg_class c
  WHERE c.relnamespace = '{SCHEMA_NAME}'::regnamespace AND c.relkind IN ('r','p','v','m','S')
    -- sequence của cột IDENTITY đã nằm trong định nghĩa cột
    AND NOT EXISTS (SELECT 1 FROM pg_depend dep WHERE dep.classid = 'pg_class'::regclass AND dep.objid = c.oid
                    AND dep.deptype = 'i')
) s
"""

Q_FUNCTIONS = f"""
SELECT coalesce(json_agg(x ORDER BY x->>'signature'), '[]') FROM (
  SELECT json_build_object(
    'signature', p.oid::regprocedure::text,
    'kind', p.prokind::text,
    'owner', pg_get_userbyid(p.proowner),
    'default_acl', p.proacl IS NULL,
    'acl', (SELECT coalesce(json_agg(json_build_array(CASE a.grantee WHEN 0 THEN 'PUBLIC' ELSE pg_get_userbyid(a.grantee) END,
                     a.privilege_type) ORDER BY 1,2), '[]') FROM aclexplode(p.proacl) a WHERE a.grantee <> p.proowner),
    'comment', obj_description(p.oid, 'pg_proc'),
    'definition', CASE WHEN p.prokind = 'a' THEN NULL ELSE pg_get_functiondef(p.oid) END) AS x
  FROM pg_proc p
  WHERE p.pronamespace = '{SCHEMA_NAME}'::regnamespace
) s
"""


def lit(text: str) -> str:
    return "'" + text.replace("'", "''") + "'"


def grants(acl: list[list[str]], obj: str) -> list[str]:
    """Gộp quyền theo người nhận, thứ tự ổn định.

    >>> grants([["sokhach_app", "SELECT"], ["sokhach_app", "INSERT"], ["PUBLIC", "USAGE"]], "TABLE sokhach.x")
    ['GRANT USAGE ON TABLE sokhach.x TO PUBLIC;', 'GRANT INSERT, SELECT ON TABLE sokhach.x TO sokhach_app;']
    """
    by_role: dict[str, set[str]] = {}
    for role, privilege in acl:
        by_role.setdefault(role, set()).add(privilege)
    return [f"GRANT {', '.join(sorted(privs))} ON {obj} TO {role};" for role, privs in sorted(by_role.items())]


def comment_line(kind: str, name: str, comment: str | None) -> list[str]:
    return [] if comment is None else [f"COMMENT ON {kind} {name} IS {lit(comment)};"]


def column_sql(col: dict) -> str:
    parts = [f"    {col['name']} {col['type']}"]
    if col["generated"] == "s":
        parts.append(f"GENERATED ALWAYS AS ({col['default']}) STORED")
    elif col["generated"] == "v":
        parts.append(f"GENERATED ALWAYS AS ({col['default']}) VIRTUAL")
    elif col["identity"] in ("a", "d"):
        parts.append("GENERATED " + ("ALWAYS" if col["identity"] == "a" else "BY DEFAULT") + " AS IDENTITY")
    elif col["default"] is not None:
        parts.append(f"DEFAULT {col['default']}")
    if col["notnull"]:
        parts.append("NOT NULL")
    return " ".join(parts)


def render_relation(rel: dict) -> list[str]:
    name, kind = rel["name"], rel["kind"]
    out: list[str] = []
    if kind in ("r", "p"):
        body = [column_sql(c) for c in rel["columns"] or []]
        body += [f"    CONSTRAINT {n} {d}" for n, d in rel["constraints"] or []]
        out.append(f"CREATE TABLE {name} (")
        out.append(",\n".join(body))
        out.append(");" if kind == "r" else ") PARTITIONED;")
        obj = "TABLE"
    elif kind in ("v", "m"):
        out.append(f"CREATE {'MATERIALIZED ' if kind == 'm' else ''}VIEW {name} AS")
        out.append(rel["view"].rstrip().rstrip(";") + ";")
        obj = "MATERIALIZED VIEW" if kind == "m" else "VIEW"
    else:
        out.append(f"CREATE SEQUENCE {name};")
        obj = "SEQUENCE"
    out.append(f"ALTER {obj} {name} OWNER TO {rel['owner']};")
    if rel["rls"]:
        out.append(f"ALTER TABLE {name} ENABLE ROW LEVEL SECURITY;")
    out += [d + ";" for d in rel["indexes"] or []]
    out += [d + ";" for d in rel["triggers"] or []]
    for pol, cmd, qual, check in rel["policies"] or []:
        out.append(f"CREATE POLICY {pol} ON {name} FOR {cmd}"
                   + (f" USING ({qual})" if qual else "") + (f" WITH CHECK ({check})" if check else "") + ";")
    out += comment_line(obj, name, rel["comment"])
    for col in rel["columns"] or []:
        if kind != "S":
            out += comment_line("COLUMN", f"{name}.{col['name']}", col["comment"])
    obj_for_grant = "TABLE" if kind in ("r", "p", "v", "m") else "SEQUENCE"
    out += grants(rel["acl"], f"{obj_for_grant} {name}")
    return out


def render_function(fn: dict) -> list[str]:
    sig = fn["signature"]
    obj = {"p": "PROCEDURE", "a": "AGGREGATE"}.get(fn["kind"], "FUNCTION")
    out = [f"-- {obj} {sig}"]
    if fn["definition"] is None:
        out.append(f"-- (aggregate: xem catalog) {sig}")
    else:
        out.append(fn["definition"].rstrip() + ";")
    out.append(f"ALTER {obj} {sig} OWNER TO {fn['owner']};")
    if fn["default_acl"]:
        out.append(f"-- quyền: mặc định (PUBLIC EXECUTE) cho {sig}")
    else:
        roles = {role for role, _ in fn["acl"]}
        if "PUBLIC" not in roles:
            out.append(f"REVOKE ALL ON {obj} {sig} FROM PUBLIC;")
        out += grants(fn["acl"], f"{obj} {sig}")
    out += comment_line(obj, sig, fn["comment"])
    return out


def section(title: str) -> list[str]:
    return ["", "-- " + "-" * 108, f"-- {title}", "-- " + "-" * 108, ""]


def render(pg: Pg) -> str:
    def load(query: str):
        return json.loads(pg.value(query))

    others = [n for n in load(Q_OTHER_SCHEMAS) if n != SCHEMA_NAME]
    if others:
        raise HarnessError(f"DB có schema ngoài {SCHEMA_NAME}, cần thêm vào snapshot: {others}")
    schema = load(Q_SCHEMA)
    # Sắp ở Python (thứ tự mã ký tự), không phụ thuộc collation của cụm PostgreSQL.
    types = sorted(load(Q_TYPES), key=lambda t: t["name"])
    relations = sorted(load(Q_RELATIONS), key=lambda r: r["name"])
    functions = sorted(load(Q_FUNCTIONS), key=lambda f: f["signature"])
    lines = [HEADER.rstrip("\n")]
    lines += section(f"SCHEMA {SCHEMA_NAME}")
    lines.append(f"CREATE SCHEMA {SCHEMA_NAME} AUTHORIZATION {schema['owner']};")
    lines += comment_line("SCHEMA", SCHEMA_NAME, schema["comment"])
    lines += grants(schema["acl"], f"SCHEMA {SCHEMA_NAME}")
    objtypes = {"r": "TABLES", "S": "SEQUENCES", "f": "FUNCTIONS", "T": "TYPES", "n": "SCHEMAS", "L": "LARGE OBJECTS"}
    for role, in_schema, objtype, acl in sorted(schema["default_acl"], key=json.dumps):
        scope = f" IN SCHEMA {SCHEMA_NAME}" if in_schema else ""
        lines.append(f"-- ALTER DEFAULT PRIVILEGES FOR ROLE {role}{scope} ON {objtypes.get(objtype, objtype)}: "
                     f"ACL còn lại {{{','.join(sorted(acl))}}} (không có '=' đầu = PUBLIC bị thu)")
    if types:
        lines += section(f"KIỂU ({len(types)})")
        for t in types:
            if t["kind"] == "e":
                lines.append(f"CREATE TYPE {t['name']} AS ENUM ({', '.join(lit(v) for v in t['labels'])});")
            else:
                lines.append(f"CREATE DOMAIN {t['name']} AS {t['base']}" + (" NOT NULL" if t["notnull"] else "")
                             + "".join(f" {c}" for c in t["checks"] or []) + ";")
            lines += comment_line("TYPE" if t["kind"] == "e" else "DOMAIN", t["name"], t["comment"])
    groups = (("r", "BẢNG"), ("p", "BẢNG PHÂN VÙNG"), ("S", "SEQUENCE"), ("v", "VIEW"), ("m", "MATERIALIZED VIEW"))
    for kind, title in groups:
        items = [r for r in relations if r["kind"] == kind]
        if not items:
            continue
        lines += section(f"{title} ({len(items)})")
        for rel in items:
            lines += render_relation(rel)
            lines.append("")
    lines += section(f"HÀM ({len(functions)}), sắp theo tên + chữ ký")
    for fn in functions:
        lines += render_function(fn)
        lines.append("")
    return "\n".join(lines).rstrip("\n") + "\n"


def main() -> int:
    for stream in (sys.stdout, sys.stderr):  # Windows chuyển hướng ra file thì mặc định cp1252
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure:
            reconfigure(encoding="utf-8", errors="backslashreplace")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true", help="không ghi; so với file trong repo, lệch thì exit 1")
    ap.add_argument("--output", type=Path, default=OUTPUT, help="file đích (mặc định %(default)s)")
    args = ap.parse_args()
    report: dict = {}
    try:
        with disposable_database(report) as pg:
            text = render(pg)
    except (HarnessError, OSError, ValueError, KeyError) as exc:
        print(f"LỖI: {type(exc).__name__}: {str(exc)[-3000:]}", file=sys.stderr)
        print(json.dumps(report, ensure_ascii=False), file=sys.stderr)
        return 2
    if report.get("cleanup") != "verified_and_removed":
        print(f"LỖI dọn container: {report.get('cleanup')}", file=sys.stderr)
        return 2
    shown = args.output.resolve().relative_to(ROOT).as_posix() if args.output.resolve().is_relative_to(ROOT) else args.output
    if args.check:
        current = args.output.read_text(encoding="utf-8").replace("\r\n", "\n") if args.output.exists() else ""
        if current == text:
            print(f"KHỚP: {shown} đúng trạng thái hiện hành.")
            return 0
        diff = list(difflib.unified_diff(current.splitlines(), text.splitlines(), "trong repo", "sinh lại", lineterm="", n=2))
        print("\n".join(diff[:200]))
        if len(diff) > 200:
            print(f"... còn {len(diff) - 200} dòng diff")
        print(f"\nLỆCH: {args.output.relative_to(ROOT).as_posix()} không khớp SQL hiện hành. Sinh lại rồi commit:\n"
              f"    {REGENERATE}", file=sys.stderr)
        return 1
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    print(f"ĐÃ GHI {args.output} ({text.count(chr(10))} dòng, {text.count('-- FUNCTION ')} hàm)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
