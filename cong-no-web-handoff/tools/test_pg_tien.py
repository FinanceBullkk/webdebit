#!/usr/bin/env python3
"""Sổ tiền P0-a lát 1 (SO-TIEN-01, specs/so-tien-p0a.md): schema `tien` trên PostgreSQL 18.6 dùng một lần.

Dựng DB như harness V7 (`pg_v7_harness.disposable_database`), chạy migration sổ tiền (lượt lỗi giữa chừng quay lại hết, chạy hai
lượt, hoàn tác xóa sạch rồi chạy lại), rồi gọi thật từng hàm `tien.*` bằng login thành viên `tien_app` như API: pháp nhân, tài
khoản, số dư mở, cấp/thu vai, xem trước và commit lô (chống trùng theo file, mã ngân hàng, dấu vân, ghép mềm khi mô tả đổi, giao
dịch đã có mà file không nhận), quyết nghi trùng và giữ giao dịch bằng vai review, bỏ lô, hủy lô, phân bổ. Phủ mọi tiêu chí nghiệm
thu của spec (AT-02.x, 03.x, 05.x, 06.x/08.2, 12.x và các ca sau review độc lập), hai phiên commit cùng lô (khuôn pg_blocking_pids),
số event và khóa lặp mỗi lệnh, bất biến I-1, I-4, I-5, I-6, I-8, I-10 tính thẳng từ bảng, và catalog `sokhach` không đổi. Dữ liệu
bịa (số tròn, mã tài khoản giả). Cần Docker:

    uv run --python 3.14 python cong-no-web-handoff/tools/test_pg_tien.py [--report <file>.json]
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import sys
import time
import unicodedata
from pathlib import Path

from pg_v7_harness import (
    IMAGE,
    HarnessError,
    Pg,
    PsqlSession,
    disposable_database,
    lit,
    require,
)

TOOLS = Path(__file__).resolve().parent
MIGRATION = TOOLS / "migrations" / "2026-11-24-tien-p0a-lat1.sql"
ROLLBACK = TOOLS / "migrations" / "2026-11-24-tien-p0a-lat1.rollback.sql"
APP, READER = "tien_api_gia", "tien_watch_gia"
TEMPLATE = "mau-gia@1"
EVENT_OF = {"create_legal_entity": "entity_create", "create_account": "account_create", "set_opening": "opening_set",
            "grant_role": "grant", "revoke_role": "revoke", "preview_import": "import_preview", "commit_import": "import_commit",
            "reject_import": "import_reject", "void_import": "import_void", "set_allocation": "allocation_set"}
READS = ["get_account_summary(bigint)", "list_transactions(bigint,date,date)"]
TABLES = ["currency", "event", "legal_entity", "financial_account", "account_opening", "access_grant", "statement_import",
          "raw_statement_line", "bank_transaction", "bank_transaction_source", "allocation", "idempotency"]
# Login giả: quản trị pháp nhân A/B, kế toán (nhập + phân bổ ở A), người review ở A, người xem một tài khoản, người nhập ở B, người lạ,
# kế toán trưởng (nhập + review ở A, được quyết nghi trùng), người nhập ở A có vai review ở B.
QT_A, QT_B, KT, RV, XEM, NB, LA = "qt-gia-a", "qt-gia-b", "ketoan-gia", "review-gia", "xem-gia", "nhap-gia-b", "nguoi-la-gia"
KTT, NA2 = "ktt-gia", "nhap-gia-2"
SOKHACH_PRINT = """SELECT md5(concat_ws('#',
  (SELECT string_agg(x, ',' ORDER BY x) FROM (SELECT p.oid::regprocedure::text || md5(pg_get_functiondef(p.oid))
      || coalesce(p.proacl::text, '') AS x FROM pg_proc p WHERE p.pronamespace = 'sokhach'::regnamespace AND p.prokind = 'f') f),
  (SELECT string_agg(x, ',' ORDER BY x) FROM (SELECT c.relname::text || c.relkind::text || coalesce(c.relacl::text, '') AS x FROM pg_class c
      WHERE c.relnamespace = 'sokhach'::regnamespace) r),
  (SELECT string_agg(x, ',' ORDER BY x) FROM (SELECT r.rolname::text || r.rolcanlogin::text || r.rolinherit::text AS x FROM pg_roles r
      WHERE r.rolname LIKE 'sokhach%') o),
  (SELECT string_agg(x, ',' ORDER BY x) FROM (SELECT m.roleid::regrole::text || '>' || m.member::regrole::text AS x
      FROM pg_auth_members m WHERE m.roleid::regrole::text LIKE 'sokhach%') a),
  (SELECT nspacl::text FROM pg_namespace WHERE nspname = 'sokhach')))"""


class T:
    """Gọi tien.* bằng login thành viên tien_app như API. Mỗi lệnh kiểm số event và khóa lặp ghi thêm, và event cuối đúng loại,
    người làm, loại người làm, khóa lặp; lệnh bị từ chối phải đúng mã và không ghi gì."""

    def __init__(self, pg: Pg):
        self.pg, self.serial = pg, 0

    def key(self) -> str:
        self.serial += 1
        return f"k-{self.serial}"

    @staticmethod
    def wrap(sql: str, actor: str | None, kind: str | None = "human", pre: str = "") -> str:
        sets = "".join(f"SET LOCAL tien.{name} = {lit(value)}; "
                       for name, value in (("actor", actor), ("actor_kind", kind)) if value is not None)
        return f"BEGIN; {pre}{sets}{sql}; COMMIT"

    def sql(self, fn: str, payload: dict, actor: str | None, kind: str | None = "human", pre: str = "") -> str:
        return self.wrap(f"SELECT tien.{fn}({lit(json.dumps(payload, ensure_ascii=False))}::jsonb)", actor, kind, pre)

    def counts(self) -> tuple[int, int]:
        events, saved = self.pg.value("SELECT (SELECT count(*) FROM tien.event)||'|'||(SELECT count(*) FROM tien.idempotency)").split("|")
        return int(events), int(saved)

    def cmd(self, fn: str, payload: dict, actor: str, *, key: str | None = None, events: int = 1, saved: int = 1,
            pre: str = "") -> dict:
        k = key or self.key()
        before = self.counts()
        out = json.loads(self.pg.value(self.sql(fn, {"idempotency_key": k, **payload}, actor, pre=pre), user=APP))
        after = self.counts()
        require((after[0] - before[0], after[1] - before[1]) == (events, saved),
                f"{fn}: ghi thêm {after[0] - before[0]} event / {after[1] - before[1]} khóa lặp, cần {events}/{saved}: {out}")
        if events:
            last = self.pg.value("SELECT kind||'|'||actor||'|'||actor_kind||'|'||idempotency_key FROM tien.event ORDER BY id DESC LIMIT 1")
            require(last == f"{EVENT_OF[fn]}|{actor}|human|{k}", f"{fn}: event cuối sai: {last}")
        return out

    def reject(self, fn: str, payload: dict, actor: str | None, error: str, *, key: str | None = None,
               kind: str | None = "human", detail: str | None = None) -> None:
        before = self.counts()
        p = self.pg.sql(self.sql(fn, {"idempotency_key": key or self.key(), **payload}, actor, kind), user=APP, check=False)
        require(p.returncode != 0 and re.search(rf"ERROR:\s+P0001: {error}$", p.stderr, re.M) is not None
                and (detail is None or re.search(rf"^DETAIL:\s+{detail}$", p.stderr, re.M) is not None),
                f"{fn}: cần {error} {detail or ''}: {p.stdout[-300:]} {p.stderr[-600:]}")
        require(self.counts() == before, f"{fn}: bị từ chối {error} mà vẫn ghi")

    def read(self, fn: str, args: str, actor: str | None, *, user: str = APP) -> dict:
        return json.loads(self.pg.value(self.wrap(f"SELECT tien.{fn}({args})", actor), user=user))

    def read_reject(self, fn: str, args: str, actor: str | None, error: str) -> None:
        p = self.pg.sql(self.wrap(f"SELECT tien.{fn}({args})", actor), user=APP, check=False)
        require(p.returncode != 0 and re.search(rf"ERROR:\s+P0001: {error}$", p.stderr, re.M) is not None,
                f"{fn}({args}) cần {error}: {p.stderr[-500:]}")


def line(no: int, day, direction: str | None, amount, desc: str | None, *, bal: int | None = None, ref: str | None = None,
         currency: str | None = "VND") -> dict:
    out = {"line_no": no, "booking_date": str(day), "direction": direction, "amount_minor": None if amount is None else str(amount),
           "currency": currency, "description": desc, "balance_after_minor": None if bal is None else str(bal),
           "cells": {"ngay": str(day), "noi_dung": desc, "so_tien": None if amount is None else str(amount)}}
    if ref is not None:
        out["bank_ref"] = ref
    return out


def statement(account: int, seed: str, start, end, opening: int | None, rows: list[tuple], *, closing: bool = True) -> dict:
    """Một file sao kê bịa theo StatementLine v1: rows là (số dòng, ngày, chiều, số tiền, mô tả[, mã ngân hàng]); số dư sau mỗi
    dòng tính từ số dư đầu nên file liền mạch, số dư cuối là số dư sau dòng cuối."""
    bal, lines = opening, []
    for no, day, direction, amount, desc, *ref in rows:
        bal = None if bal is None else bal + (amount if direction == "in" else -amount)
        lines.append(line(no, day, direction, amount, desc, bal=bal, ref=ref[0] if ref else None))
    return {"account_id": account, "file_sha256": hashlib.sha256(seed.encode()).hexdigest(), "template": TEMPLATE,
            "period_from": str(start), "period_to": str(end), "opening_minor": None if opening is None else str(opening),
            "closing_minor": str(bal) if closing and bal is not None else None, "last_day_complete": False, "lines": lines}


def net(rows: list[tuple]) -> int:
    return sum(amount if direction == "in" else -amount for _, _, direction, amount, *_ in rows)


def runbook_entity(pg: Pg, code: str, name: str) -> int:
    """Pháp nhân đầu tiên chèn bằng role chủ schema như runbook, kèm vết entity_create (khóa ngoại của vết kiểm lúc commit)."""
    return int(pg.value(
        "BEGIN; SET LOCAL ROLE tien_owner; WITH n AS (SELECT nextval(pg_get_serial_sequence('tien.legal_entity', 'id')) AS id), "
        "e AS (INSERT INTO tien.event(legal_entity_id, kind, actor, actor_kind, \"before\", \"after\", idempotency_key) "
        f"SELECT n.id, 'entity_create', 'runbook-gia', 'human', '{{}}', jsonb_build_object('legal_entity', jsonb_build_object("
        f"'id', n.id, 'code', {lit(code)})), {lit('runbook:' + code)} FROM n RETURNING id, legal_entity_id) "
        f"INSERT INTO tien.legal_entity(id, code, name, created_event) OVERRIDING SYSTEM VALUE "
        f"SELECT e.legal_entity_id, {lit(code)}, {lit(name)}, e.id FROM e RETURNING id; COMMIT"))


def runbook_grant(pg: Pg, entity: int, login: str) -> int:
    """Vai tien_quan_tri đầu tiên của một pháp nhân, chèn bằng role chủ schema như runbook."""
    return int(pg.value(
        "BEGIN; SET LOCAL ROLE tien_owner; WITH n AS (SELECT nextval(pg_get_serial_sequence('tien.access_grant', 'id')) AS id), "
        "e AS (INSERT INTO tien.event(legal_entity_id, kind, actor, actor_kind, \"before\", \"after\", idempotency_key) "
        f"SELECT {entity}, 'grant', 'runbook-gia', 'human', '{{}}', jsonb_build_object('grant', jsonb_build_object('id', n.id, "
        f"'login', {lit(login)}, 'role', 'tien_quan_tri', 'legal_entity_id', {entity})), {lit('runbook:' + login)} FROM n RETURNING id) "
        f"INSERT INTO tien.access_grant(id, login, role, legal_entity_id, created_event) OVERRIDING SYSTEM VALUE "
        f"SELECT n.id, {lit(login)}, 'tien_quan_tri', {entity}, e.id FROM n, e RETURNING id; COMMIT"))


def wait_blocked(pg: Pg, holder: int, waiter: int) -> None:
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        if pg.value(f"SELECT {holder} = ANY (pg_blocking_pids({waiter}))") == "t":
            return
        time.sleep(0.05)  # chỉ là vòng hỏi; bằng chứng chặn là pg_blocking_pids
    raise HarnessError("phiên sau không chờ khóa tài khoản của phiên trước")


def race(pg: Pg, body_a: dict, body_b: dict, actor: str) -> tuple[dict, str]:
    """Phiên A commit lô và giữ khóa tài khoản; phiên B gọi commit khi A chưa xong, phải chờ đúng khóa đó (pg_blocking_pids).
    Trả kết quả của A và dòng kết quả của B (hoặc 'ERR:' + stderr khi B bị từ chối)."""
    a, b = PsqlSession(pg, "tien_race_a"), PsqlSession(pg, "tien_race_b")
    begin = f"BEGIN; SET LOCAL tien.actor = {lit(actor)}; SET LOCAL tien.actor_kind = 'human'; SELECT pg_backend_pid()"
    try:
        a.send(begin)
        pid_a = int(a.line())
        a.send(f"SELECT tien.commit_import({lit(json.dumps(body_a))}::jsonb)")
        first = json.loads(a.line())
        b.send(begin)
        pid_b = int(b.line())
        b.send(f"SELECT tien.commit_import({lit(json.dumps(body_b))}::jsonb)")
        wait_blocked(pg, pid_a, pid_b)
        a.send("COMMIT; SELECT 'xong'")
        require(a.line() == "xong", "phiên A không commit được")
        second = b.lines.get(timeout=20)
        if second is None:  # B bị từ chối: psql dừng vì ON_ERROR_STOP, lỗi nằm ở stderr
            b.proc.wait(timeout=10)
            return first, "ERR:" + (b.proc.stderr.read() if b.proc.stderr else "")
        b.send("COMMIT; SELECT 'xong'")
        require(b.line() == "xong", "phiên B không commit được")
        return first, second
    finally:
        a.close()
        b.close()


def check_migration(pg: Pg, cases: list[str]) -> None:
    source, rollback = MIGRATION.read_text(encoding="utf-8"), ROLLBACK.read_text(encoding="utf-8")
    require(source.count("COMMIT;") == 1 and source.rstrip().endswith("COMMIT;") and source.count("\nBEGIN;\n") == 1,
            "migration phải là một giao dịch, COMMIT ở cuối")
    require(re.search(r"\b(sokhach|doixe)[._]", source + rollback) is None, "migration nhắc tới schema hay role của sổ nợ/đội xe")
    pg.rejects(source.replace("COMMIT;", "DO $$ BEGIN RAISE EXCEPTION 'TIEN_FAULT'; END $$; COMMIT;"), message="TIEN_FAULT")
    gone = "SELECT to_regnamespace('tien') IS NULL AND NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname IN ('tien_owner', 'tien_app', 'tien_reader'))"
    require(pg.value(gone) == "t", "migration lỗi giữa chừng không quay lại hết (schema hoặc role còn)")
    shape = ("SELECT (SELECT count(*) FROM pg_class WHERE relnamespace = 'tien'::regnamespace AND relkind = 'r')||'|'||"
             "(SELECT count(*) FROM pg_class WHERE relnamespace = 'tien'::regnamespace AND relkind = 'v')||'|'||"
             "(SELECT count(*) FROM pg_proc WHERE pronamespace = 'tien'::regnamespace)||'|'||"
             "(SELECT count(*) FROM pg_trigger g JOIN pg_class c ON c.oid = g.tgrelid WHERE c.relnamespace = 'tien'::regnamespace "
             "AND NOT g.tgisinternal)||'|'||(SELECT count(*) FROM tien.currency)")
    pg.sql(source)
    first = pg.value(shape)
    second = pg.sql(source)
    require("already exists" in second.stderr and pg.value(shape) == first, f"lần hai phải báo đã có, không đổi gì: {second.stderr[-300:]}")
    tables, views, _, triggers, currencies = first.split("|")
    require((tables, views, triggers, currencies) == ("12", "1", "24", "3"), f"đối tượng schema tien: {first}")
    pg.sql(rollback)
    require(pg.value(gone) == "t" and pg.value("SELECT count(*) FROM pg_default_acl d WHERE NOT EXISTS "
                                               "(SELECT 1 FROM pg_roles r WHERE r.oid = d.defaclrole)") == "0",
            "hoàn tác phải xóa sạch schema, ba role và quyền mặc định")
    pg.sql(source)
    pg.sql(source)
    require(pg.value(shape) == first, "chạy lại sau hoàn tác khác lần đầu")
    cases.append("migration: lỗi giữa chừng quay lại hết (không schema, không role); chạy hai lần, lần hai báo đã có và không đổi gì; "
                 "hoàn tác xóa sạch schema, ba role, quyền mặc định; chạy lại hai lần; không nhắc tới schema/role sổ nợ, đội xe")


def check_grants(pg: Pg, cases: list[str]) -> None:
    pg.sql(f"CREATE ROLE {APP} LOGIN IN ROLE tien_app; CREATE ROLE {READER} LOGIN IN ROLE tien_reader")

    def callable_by(role: str) -> list[str]:
        return sorted(json.loads(pg.value(
            "SELECT coalesce(json_agg(p.proname||'('||replace(oidvectortypes(p.proargtypes), ', ', ',')||')'), '[]') FROM pg_proc p "
            f"WHERE p.pronamespace = 'tien'::regnamespace AND has_function_privilege({lit(role)}, p.oid, 'EXECUTE')")))

    commands = sorted(f"{name}(jsonb)" for name in EVENT_OF)
    require(callable_by(APP) == sorted(commands + READS), f"tien_app gọi được: {callable_by(APP)}")
    require(callable_by(READER) == sorted(READS), f"tien_reader gọi được: {callable_by(READER)}")
    require(pg.value("SELECT count(*) FROM pg_proc p CROSS JOIN LATERAL aclexplode(coalesce(p.proacl, acldefault('f', p.proowner))) a "
                     "WHERE p.pronamespace = 'tien'::regnamespace AND a.grantee = 0") == "0", "PUBLIC gọi được hàm tien")
    for role in (APP, READER):
        require(pg.value("SELECT count(*) FROM pg_class c WHERE c.relnamespace = 'tien'::regnamespace AND c.relkind IN ('r', 'v', 'S') "
                         f"AND has_table_privilege({lit(role)}, c.oid, 'SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER')") == "0",
                f"{role} có quyền trên bảng tien")
        require(pg.value(f"SELECT has_schema_privilege({lit(role)}, 'sokhach', 'USAGE')") == "f", f"{role} dùng được schema sokhach")
        # AT-02.1: thử thật từng câu ghi/đọc trực tiếp trên mọi bảng; câu nào lọt thì DO báo tên.
        pg.sql(f"""DO $$
DECLARE t text; s text; leaked text[] := '{{}}';
BEGIN
    FOREACH t IN ARRAY ARRAY{TABLES!r}::text[] LOOP
        FOREACH s IN ARRAY ARRAY['SELECT 1 FROM tien.%I LIMIT 1', 'INSERT INTO tien.%I DEFAULT VALUES', 'UPDATE tien.%I SET %I = NULL',
                                 'DELETE FROM tien.%I', 'TRUNCATE tien.%I'] LOOP
            BEGIN
                EXECUTE format(s, t, (SELECT attname FROM pg_attribute WHERE attrelid = ('tien.' || t)::regclass AND attnum > 0
                                       AND NOT attisdropped AND attidentity = '' ORDER BY attnum LIMIT 1));
                leaked := leaked || format(s, t, '?');
            EXCEPTION WHEN insufficient_privilege THEN NULL;
            END;
        END LOOP;
    END LOOP;
    IF cardinality(leaked) > 0 THEN RAISE EXCEPTION 'QUYEN_LOT %', leaked; END IF;
END $$""", user=role)
    pg.rejects(T.wrap("SELECT tien._actor()", KT), user=APP, message="permission denied")
    pg.rejects(T.wrap("SELECT tien.preview_import('{}')", KT), user=READER, message="permission denied")
    require(pg.value("SELECT count(*) FROM pg_proc p WHERE p.pronamespace = 'tien'::regnamespace AND p.prorettype <> 'trigger'::regtype "
                     "AND NOT (p.prosecdef AND array_to_string(p.proconfig, ';') LIKE '%search_path=pg_catalog, tien, pg_temp%')") == "0",
            "hàm tien phải SECURITY DEFINER với search_path cố định")
    require(pg.value("SELECT bool_and(r = 'tien_owner') FROM (SELECT nspowner::regrole::text AS r FROM pg_namespace WHERE nspname = 'tien' "
                     "UNION ALL SELECT relowner::regrole::text FROM pg_class WHERE relnamespace = 'tien'::regnamespace "
                     "UNION ALL SELECT proowner::regrole::text FROM pg_proc WHERE pronamespace = 'tien'::regnamespace) o") == "t",
            "schema tien và mọi đối tượng phải thuộc tien_owner")
    cases.append("quyền: tien_app gọi đúng 10 lệnh + 2 hàm đọc, tien_reader chỉ 2 hàm đọc, PUBLIC không gọi gì, hàm phụ không cấp; "
                 "AT-02.1 cả hai login không SELECT/INSERT/UPDATE/DELETE/TRUNCATE được bảng nào (thử thật); không dùng được sokhach; "
                 "hàm SECURITY DEFINER + search_path cố định; mọi đối tượng thuộc tien_owner")


def invariants(pg: Pg, t: T, readers: dict[int, str]) -> None:
    for acc, actor in readers.items():
        direct = pg.value("SELECT (o.amount_minor + coalesce(sum(CASE x.direction WHEN 'in' THEN x.amount_minor ELSE -x.amount_minor END) "
                          "FILTER (WHERE x.voided_event IS NULL), 0))::text FROM tien.account_opening o "
                          f"LEFT JOIN tien.bank_transaction x ON x.account_id = o.account_id WHERE o.account_id = {acc} GROUP BY o.amount_minor")
        require(t.read("get_account_summary", str(acc), actor)["balance_minor"] == direct, f"I-1 tài khoản {acc}: số dư khác {direct}")
    checks = {
        "I-4 Σ phân bổ hiệu lực ≤ số tiền, giao dịch đã hủy không còn phân bổ":
            "NOT EXISTS (SELECT 1 FROM tien.bank_transaction x JOIN tien.allocation l ON l.bank_transaction_id = x.id "
            "AND l.superseded_event IS NULL GROUP BY x.id, x.amount_minor, x.voided_event "
            "HAVING sum(l.amount_minor) > x.amount_minor OR x.voided_event IS NOT NULL)",
        "I-5 mỗi dòng phân bổ có trong vết tạo, dòng đã thay có trong vết thay":
            "NOT EXISTS (SELECT 1 FROM tien.allocation l JOIN tien.event e ON e.id = l.created_event "
            "CROSS JOIN LATERAL (SELECT jsonb_build_array(jsonb_build_object('id', l.id, 'target_kind', l.target_kind, "
            "'target_ref', l.target_ref, 'amount_minor', l.amount_minor::text, 'note', l.note)) AS me) m "
            "WHERE e.kind <> 'allocation_set' OR NOT coalesce(e.\"after\" -> 'allocations' @> m.me, false) "
            "OR (l.superseded_event IS NOT NULL AND NOT EXISTS (SELECT 1 FROM tien.event s WHERE s.id = l.superseded_event "
            "AND s.kind = 'allocation_set' AND coalesce(s.\"before\" -> 'allocations' @> m.me, false))))",
        "I-6 giao dịch hiệu lực ⇔ còn nguồn ở lô đã commit; đúng một origin; dòng gốc của lô đã commit/hủy đúng một nguồn":
            "NOT EXISTS (SELECT 1 FROM tien.bank_transaction x WHERE (x.voided_event IS NULL) <> EXISTS (SELECT 1 FROM "
            "tien.bank_transaction_source s JOIN tien.statement_import i ON i.id = s.import_id WHERE s.bank_transaction_id = x.id "
            "AND i.status = 'committed') OR (SELECT count(*) FROM tien.bank_transaction_source s WHERE s.bank_transaction_id = x.id "
            "AND s.role = 'origin') <> 1) AND NOT EXISTS (SELECT 1 FROM tien.raw_statement_line r JOIN tien.statement_import i "
            "ON i.id = r.import_id WHERE (SELECT count(*) FROM tien.bank_transaction_source s WHERE s.raw_line_id = r.id) "
            "<> CASE WHEN i.status IN ('committed', 'voided') THEN 1 ELSE 0 END)",
        "I-8 phân bổ, giao dịch, tài khoản cùng tài khoản và tiền tệ":
            "NOT EXISTS (SELECT 1 FROM tien.allocation l JOIN tien.bank_transaction x ON x.id = l.bank_transaction_id "
            "JOIN tien.financial_account a ON a.id = x.account_id WHERE l.account_id <> x.account_id OR l.currency <> x.currency "
            "OR x.currency <> a.currency)",
        "I-10 mỗi event của lệnh có khóa lặp đã lưu, mỗi khóa đúng một event":
            "NOT EXISTS (SELECT 1 FROM tien.event e WHERE e.idempotency_key NOT LIKE 'runbook:%' AND NOT EXISTS "
            "(SELECT 1 FROM tien.idempotency i WHERE i.key = e.idempotency_key)) "
            "AND NOT EXISTS (SELECT 1 FROM tien.event GROUP BY idempotency_key HAVING count(*) > 1)",
        "mọi event có before/after là object, người làm và loại người làm":
            "NOT EXISTS (SELECT 1 FROM tien.event WHERE jsonb_typeof(\"before\") <> 'object' OR jsonb_typeof(\"after\") <> 'object' "
            "OR btrim(actor) = '' OR actor_kind NOT IN ('human', 'machine'))",
    }
    for name, sql in checks.items():
        pg.true(sql, name)


def scenario(pg: Pg, cases: list[str]) -> None:
    t = T(pg)
    today = dt.date.fromisoformat(pg.value("SELECT (clock_timestamp() AT TIME ZONE 'Asia/Ho_Chi_Minh')::date"))
    last = today.replace(day=1) - dt.timedelta(days=1)   # ngày cuối tháng trước
    month = last.replace(day=1)                          # tháng trước: mọi ngày đều trước hôm nay (giờ VN)

    def d(n: int) -> dt.date:
        return month + dt.timedelta(days=n - 1)

    def summary(acc: int, actor: str = KT) -> dict:
        return t.read("get_account_summary", str(acc), actor)

    def listing(acc: int, actor: str = KT) -> list[dict]:
        return t.read("list_transactions", f"{acc}, NULL, NULL", actor)["transactions"]

    def tx(acc: int, desc: str) -> list[int]:
        return [int(x) for x in pg.value(f"SELECT id FROM tien.bank_transaction WHERE account_id = {acc} AND description = {lit(desc)} "
                                         "AND voided_event IS NULL ORDER BY id").split()]

    def preview(body: dict, actor: str = KT, **kw) -> dict:
        return t.cmd("preview_import", body, actor, **kw)

    def commit(prev: dict, actor: str = KT, decisions: list | None = None, keep: list | None = None, **kw) -> dict:
        body = {"import_id": prev["import_id"], "expected_preview_hash": prev["preview_hash"]}
        if decisions is not None:
            body["suspect_decisions"] = decisions
        if keep is not None:
            body["keep_existing"] = keep
        return t.cmd("commit_import", body, actor, **kw)

    # Danh tính: người làm chỉ từ tien.actor / tien.actor_kind.
    entity_b = {"code": "PN-GIA-B", "name": "Phap nhan gia B"}
    t.reject("create_legal_entity", entity_b, None, "ACTOR_REQUIRED")
    t.reject("create_legal_entity", entity_b, QT_A, "ACTOR_REQUIRED", kind=None)
    t.reject("create_legal_entity", entity_b, QT_A, "ACTOR_REQUIRED", kind="robot")
    ent_a = runbook_entity(pg, "PN-GIA-A", "Phap nhan gia A")
    grant_qt_a = runbook_grant(pg, ent_a, QT_A)
    t.reject("create_legal_entity", entity_b, LA, "TIEN_FORBIDDEN")
    ent_b = t.cmd("create_legal_entity", entity_b, QT_A)["legal_entity_id"]
    t.reject("create_legal_entity", {**entity_b, "name": "Trung ma"}, QT_A, "INVALID_COMMAND")
    t.reject("create_legal_entity", {"code": "pn gia", "name": "Ma sai"}, QT_A, "INVALID_COMMAND")
    t.reject("create_legal_entity", {**entity_b, "actor": KT}, QT_A, "INVALID_COMMAND")
    runbook_grant(pg, ent_b, QT_B)
    cases.append("danh tính: thiếu tien.actor, thiếu/sai tien.actor_kind → ACTOR_REQUIRED, payload không nhận người làm; pháp nhân và "
                 "vai quản trị đầu tiên chèn bằng role chủ schema; create_legal_entity: không vai → TIEN_FORBIDDEN, mã trùng/sai → INVALID_COMMAND")

    # Tài khoản: HMAC 64 hex + 4 số cuối, một pháp nhân một tiền tệ; trùng → DUPLICATE_ACCOUNT.
    def account_body(entity: int, last4: str, **extra) -> dict:
        return {"legal_entity_id": entity, "kind": "bank", "bank_code": "NHGIA", "account_last4": last4, "currency": "VND",
                "account_hmac": hashlib.sha256(f"tk-gia-{entity}-{last4}".encode()).hexdigest(), "holder": "company",
                "statement_template": TEMPLATE, **extra}

    a1 = t.cmd("create_account", account_body(ent_a, "0001"), QT_A)["account_id"]
    a2 = t.cmd("create_account", account_body(ent_a, "0002"), QT_A)["account_id"]
    a3 = t.cmd("create_account", account_body(ent_a, "0003", bank_ref_stable=True), QT_A)["account_id"]
    a4 = t.cmd("create_account", account_body(ent_a, "0004"), QT_A)["account_id"]
    a5 = t.cmd("create_account", account_body(ent_a, "0005"), QT_A)["account_id"]
    b1 = t.cmd("create_account", account_body(ent_b, "0009"), QT_B)["account_id"]
    t.reject("create_account", account_body(ent_a, "0001"), QT_A, "DUPLICATE_ACCOUNT")
    t.reject("create_account", {**account_body(ent_a, "0006"), "account_hmac": "khong-phai-hmac"}, QT_A, "INVALID_COMMAND")
    t.reject("create_account", {**account_body(ent_a, "0006"), "currency": "XYZ"}, QT_A, "INVALID_COMMAND")
    t.reject("create_account", account_body(ent_a, "0006", bank_ref_stable=True, statement_template=None), QT_A, "INVALID_COMMAND")
    t.reject("create_account", account_body(ent_b, "0006"), QT_A, "ENTITY_SCOPE")
    t.reject("create_account", account_body(ent_a, "0006"), LA, "TIEN_FORBIDDEN")
    require(pg.value(f"SELECT version FROM tien.financial_account WHERE id = {a1}") == "0", "tài khoản mới phải version 0")
    cases.append("tài khoản: tạo đủ trường, trùng (pháp nhân, HMAC, tiền tệ) → DUPLICATE_ACCOUNT, HMAC/tiền tệ sai → INVALID_COMMAND, "
                 "bank_ref_stable mà không gắn mẫu file → INVALID_COMMAND, pháp nhân khác → ENTITY_SCOPE, không vai → TIEN_FORBIDDEN")

    # Cấp/thu vai: không cho chính mình (SELF_GRANT), đúng phạm vi pháp nhân.
    def grant(login: str, role: str, *, entity: int = ent_a, actor: str = QT_A, account: int | None = None, **kw) -> dict:
        body = {"login": login, "role": role, "legal_entity_id": entity, **({"account_id": account} if account else {})}
        return t.cmd("grant_role", body, actor, **kw)

    t.reject("grant_role", {"login": QT_A, "role": "tien_nhap", "legal_entity_id": ent_a}, QT_A, "SELF_GRANT")
    for login, role in ((KT, "tien_nhap"), (KT, "tien_phan_bo"), (RV, "tien_review"), (KTT, "tien_nhap"), (KTT, "tien_review"),
                        (NA2, "tien_nhap")):
        grant(login, role)
    grant(NA2, "tien_review", entity=ent_b, actor=QT_B)
    require(grant(KT, "tien_nhap", events=0)["unchanged"], "cấp lại vai đang có phải không ghi gì")
    grant(XEM, "tien_xem", account=a1)
    t.reject("grant_role", {"login": XEM, "role": "tien_xem", "legal_entity_id": ent_a, "account_id": b1}, QT_A, "INVALID_COMMAND")
    t.reject("grant_role", {"login": KT, "role": "tien_nhap", "legal_entity_id": ent_b}, QT_A, "ENTITY_SCOPE")
    t.reject("grant_role", {"login": KT, "role": "tien_nhap", "legal_entity_id": ent_a}, LA, "TIEN_FORBIDDEN")
    t.reject("grant_role", {"login": KT, "role": "tien_sep", "legal_entity_id": ent_a}, QT_A, "INVALID_COMMAND")
    for role in ("tien_nhap", "tien_phan_bo", "tien_review"):
        grant(NB, role, entity=ent_b, actor=QT_B)
    temp = grant("tam-gia", "tien_xem")["grant_id"]
    require(summary(a1, "tam-gia")["account"]["id"] == a1, "vai tạm đọc được")
    t.cmd("revoke_role", {"grant_id": temp, "reason": "het viec gia"}, QT_A)
    t.reject("revoke_role", {"grant_id": temp}, QT_A, "INVALID_COMMAND")
    t.reject("revoke_role", {"grant_id": grant_qt_a}, QT_A, "SELF_GRANT")
    t.reject("revoke_role", {"grant_id": temp}, KT, "TIEN_FORBIDDEN")
    t.read_reject("get_account_summary", str(a1), "tam-gia", "TIEN_FORBIDDEN")
    cases.append("cấp vai: cho chính mình → SELF_GRANT, thu vai của chính mình → SELF_GRANT, pháp nhân khác → ENTITY_SCOPE, không vai → "
                 "TIEN_FORBIDDEN, vai/tài khoản sai → INVALID_COMMAND, cấp lại không ghi; thu vai rồi đọc → TIEN_FORBIDDEN")

    # Số dư mở: một lần; chưa có thì không xem trước được, số dư là null (chưa biết), không phải 0.
    early = statement(a2, "a2-som", d(1), d(5), None, [(1, d(2), "in", 1000, "SOM GIA")])
    t.reject("preview_import", early, KT, "NO_OPENING")
    s2 = summary(a2)
    require(s2["opening"] is None and s2["balance_minor"] is None and s2["in_minor"] == "0", f"chưa có số dư mở: {s2}")

    def opening(acc: int, amount: int) -> dict:
        return {"account_id": acc, "as_of": str(month), "amount_minor": str(amount), "evidence_note": "so du gia theo sao ke gia"}

    t.cmd("set_opening", opening(a1, 1000000), QT_A)
    t.reject("set_opening", opening(a1, 1000000), QT_A, "OPENING_EXISTS")
    t.reject("set_opening", {**opening(a2, 500000), "as_of": str(today + dt.timedelta(days=1))}, QT_A, "INVALID_COMMAND")
    t.reject("set_opening", {**opening(a2, 500000), "evidence_note": "   "}, QT_A, "INVALID_COMMAND")
    t.reject("set_opening", {**opening(a2, 500000), "amount_minor": "500000.5"}, QT_A, "INVALID_COMMAND")
    t.reject("set_opening", opening(a2, 500000), KT, "TIEN_FORBIDDEN")
    t.cmd("set_opening", opening(a2, 500000), QT_A)
    t.cmd("set_opening", opening(a3, 2000000), QT_A)
    t.cmd("set_opening", opening(a4, 1000000), QT_A)
    t.cmd("set_opening", opening(a5, 1000000), QT_A)
    t.cmd("set_opening", opening(b1, 300000), QT_B)
    cases.append("số dư mở: chưa có → NO_OPENING và số dư null; đặt một lần, lần hai → OPENING_EXISTS; ngày tương lai, ghi chú rỗng, "
                 "tiền lẻ → INVALID_COMMAND; không quản trị → TIEN_FORBIDDEN")

    # Hoàn tác khi mới chỉ có tài khoản + số dư mở (chưa lô, chưa giao dịch) đã phải dừng.
    require(pg.value("SELECT (SELECT count(*) FROM tien.statement_import) + (SELECT count(*) FROM tien.bank_transaction)") == "0",
            "ca này cần trạng thái chưa có lô/giao dịch")
    pg.rejects(ROLLBACK.read_text(encoding="utf-8"), message="TIEN_HAS_DATA")
    require(pg.value("SELECT count(*) FROM tien.financial_account") == "6", "hoàn tác dừng mà vẫn xóa tài khoản")
    cases.append("hoàn tác khi mới chỉ có tài khoản + số dư mở (chưa lô, chưa giao dịch) → TIEN_HAS_DATA, không xóa gì")

    # X1 (kỳ 1–15): AT-03.3 hai giao dịch giống hệt trong một file → hai giao dịch.
    x1_rows = [(1, d(2), "in", 500000, "CK TIEN CUOC GIA 01"), (2, d(5), "out", 200000, "CHUYEN NOI BO GIA"),
               (3, d(10), "in", 300000, "CK TIEN CUOC GIA 02"), (4, d(12), "in", 100000, "CK GIONG HET GIA"),
               (5, d(12), "in", 100000, "CK GIONG HET GIA"), (6, d(15), "out", 50000, "PHI DICH VU GIA")]
    x1 = statement(a1, "x1", d(1), d(15), 1000000, x1_rows)
    p1 = preview(x1)
    require(p1["counts"] == {"rows": 6, "new": 6, "duplicate": 0, "suspect": 0, "error": 0} and p1["breaks"] == []
            and p1["balance"]["expected_opening_minor"] == "1000000" and p1["preview_account_version"] == 0, f"xem trước X1: {p1}")
    c1 = commit(p1)
    require(c1["created"] == 6 and c1["confirmed"] == 0 and c1["account_version"] == 1 and len(tx(a1, "CK GIONG HET GIA")) == 2,
            f"commit X1: {c1}")
    s1 = summary(a1)
    require((s1["balance_minor"], s1["in_minor"], s1["out_minor"], s1["latest_booking_date"], s1["transactions"])
            == ("1750000", "1000000", "250000", str(d(15)), 6), f"số dư sau X1: {s1}")
    require(t.read("list_transactions", f"{a1}, NULL, NULL", KT)["transactions"][0]["status"] == "unidentified", "giao dịch vào chưa phân bổ")
    cases.append("AT-03.3: X1 kỳ 1–15 có hai giao dịch giống hệt → 6 dòng mới, 6 giao dịch (hai giao dịch giống hệt vẫn là hai); "
                 "số dư = mở + vào − ra; version tài khoản + 1")

    # AT-03.1: cùng file lần hai → trả lô cũ, 0 giao dịch mới, không lô mới, không event.
    imports = pg.value("SELECT count(*) FROM tien.statement_import")
    again = preview(x1, events=0)
    require(again["import_id"] == p1["import_id"] and again["same_file"] and again["counts"]["new"] == 0
            and pg.value("SELECT count(*) FROM tien.statement_import") == imports and summary(a1)["transactions"] == 6,
            f"cùng file: {again}")
    cases.append("AT-03.1: cùng tài khoản + cùng SHA-256 đã commit → trả lô cũ, new = 0, không thêm lô, không thêm giao dịch, không event")

    # X2 (kỳ 10–cuối tháng) chồng X1: AT-03.2 chỉ 16–31 mới; mô tả khác khoảng trắng/hoa thường vẫn cùng dấu vân.
    # AT-03.6 trên xem trước: cùng khóa cùng nội dung → kết quả cũ; khác nội dung → IDEMPOTENCY_CONFLICT.
    x2_rows = [(1, d(10), "in", 300000, "CK TIEN CUOC GIA 02"), (2, d(12), "in", 100000, "CK GIONG HET GIA"),
               (3, d(12), "in", 100000, "  ck  giong   HET gia "), (4, d(15), "out", 50000, "PHI DICH VU GIA"),
               (5, d(16), "in", 400000, "CK TIEN CUOC GIA 03"), (6, d(20), "out", 100000, "CHI PHI GIA"),
               (7, last, "in", 250000, "CK TIEN CUOC GIA 04")]
    x2 = statement(a1, "x2", d(10), last, 1300000, x2_rows)
    p2 = preview(x2, key="xem-truoc-x2")
    require(preview(x2, key="xem-truoc-x2", events=0, saved=0) == p2, "cùng khóa cùng nội dung phải trả kết quả cũ")
    t.reject("preview_import", {**x2, "period_to": str(d(25))}, KT, "IDEMPOTENCY_CONFLICT", key="xem-truoc-x2")
    ids = tx(a1, "CK TIEN CUOC GIA 02") + tx(a1, "CK GIONG HET GIA") + tx(a1, "PHI DICH VU GIA")
    require(p2["counts"] == {"rows": 7, "new": 3, "duplicate": 4, "suspect": 0, "error": 0} and p2["breaks"] == []
            and [ln["candidate"] for ln in p2["lines"][:4]] == ids, f"xem trước X2: {p2}")
    c2 = commit(p2)
    created = pg.value(f"SELECT string_agg(booking_date::text, ',' ORDER BY id) FROM tien.bank_transaction WHERE id IN "
                       f"({','.join(str(i) for i in c2['transaction_ids'])})")
    require(c2["created"] == 3 and c2["confirmed"] == 4 and created == f"{d(16)},{d(20)},{last}", f"commit X2: {c2} {created}")
    require(summary(a1)["balance_minor"] == x2["closing_minor"] == str(1000000 + net(x1_rows[:2]) + net(x2_rows)),
            "AT-03.2 số dư cuối phải bằng số dư cuối file")
    cases.append("AT-03.2: kỳ 1–15 rồi 10–31 → 4 dòng trùng chắc (ứng viên là giao dịch thứ k), chỉ 3 dòng ngày 16–31 mới; số dư cuối "
                 "= số dư cuối file; mô tả khác khoảng trắng/hoa thường cùng dấu vân. AT-03.6: cùng khóa cùng nội dung → kết quả cũ "
                 "(0 event), khác nội dung → IDEMPOTENCY_CONFLICT")

    # X3 (ngày 12): AT-03.4 vùng chồng kỳ có thêm một dòng cùng dấu vân → nghi trùng, phải quyết.
    x3 = statement(a1, "x3", d(12), d(12), 1600000, [(n, d(12), "in", 100000, "CK GIONG HET GIA") for n in (1, 2, 3)])
    p3 = preview(x3)
    twins = tx(a1, "CK GIONG HET GIA")
    require(p3["counts"] == {"rows": 3, "new": 0, "duplicate": 2, "suspect": 1, "error": 0}
            and [(ln["class"], ln["candidate"]) for ln in p3["lines"]] == [("duplicate", twins[0]), ("duplicate", twins[1]), ("suspect", None)],
            f"xem trước X3: {p3}")
    t.reject("commit_import", {"import_id": p3["import_id"], "expected_preview_hash": p3["preview_hash"]}, KT, "IMPORT_SUSPECT_UNRESOLVED")
    for decision, error in (({"line_no": 1, "decision": "new"}, "INVALID_COMMAND"),
                            ({"line_no": 3, "decision": "duplicate_of", "transaction_id": twins[0]}, "DUPLICATE_TARGET_INVALID"),
                            ({"line_no": 3, "decision": "duplicate_of", "transaction_id": tx(a1, "CK TIEN CUOC GIA 01")[0]},
                             "DUPLICATE_TARGET_INVALID"),
                            ({"line_no": 3, "decision": "duplicate_of"}, "INVALID_COMMAND")):
        t.reject("commit_import", {"import_id": p3["import_id"], "expected_preview_hash": p3["preview_hash"],
                                   "suspect_decisions": [decision]}, KTT, error)
    t.reject("commit_import", {"import_id": p3["import_id"], "expected_preview_hash": "0" * 64,
                               "suspect_decisions": [{"line_no": 3, "decision": "new"}]}, KTT, "IMPORT_PREVIEW_STALE")
    c3 = commit(p3, KTT, decisions=[{"line_no": 3, "decision": "new"}])
    require(c3["created"] == 1 and c3["confirmed"] == 2 and len(tx(a1, "CK GIONG HET GIA")) == 3
            and summary(a1)["balance_minor"] == "2400000", f"commit X3: {c3}")
    cases.append("AT-03.4: thêm một dòng cùng dấu vân trong vùng chồng kỳ → 2 trùng chắc + 1 suspect; commit thiếu quyết định → "
                 "IMPORT_SUSPECT_UNRESOLVED; quyết cho dòng không nghi trùng → INVALID_COMMAND; trùng của giao dịch đã bị dòng khác nhận "
                 "hoặc khác ngày/số tiền → DUPLICATE_TARGET_INVALID; băm sai → IMPORT_PREVIEW_STALE; người review quyết new → thêm một giao dịch")

    # AT-03.5 + đồng thời: P và Q (cùng nội dung, khác file) xem trước ở cùng version; hai phiên commit P cùng khóa → một lần ghi.
    start = 2400000 - 250000
    pq_rows = [(1, last, "in", 250000, "CK TIEN CUOC GIA 04"), (2, last, "in", 80000, "CK MUON GIA")]
    pp, pq = preview(statement(a1, "p", last, last, start, pq_rows)), preview(statement(a1, "q", last, last, start, pq_rows))
    require(pp["preview_account_version"] == pq["preview_account_version"] and pp["counts"]["new"] == pq["counts"]["new"] == 1,
            f"P, Q xem trước: {pp['counts']} {pq['counts']}")
    body = {"idempotency_key": "commit-dong-thoi", "import_id": pp["import_id"], "expected_preview_hash": pp["preview_hash"]}
    first, second = race(pg, body, body, KT)
    require(first["created"] == 1 and json.loads(second) == first, f"cùng khóa song song: {first} / {second}")
    require(pg.value(f"SELECT count(*) FROM tien.event WHERE kind = 'import_commit' AND (\"after\" -> 'import' ->> 'id')::bigint = {pp['import_id']}")
            == "1" and len(tx(a1, "CK MUON GIA")) == 1, "hai phiên cùng commit một lô phải ghi đúng một lần")
    t.reject("commit_import", {"import_id": pq["import_id"], "expected_preview_hash": pq["preview_hash"]}, KT, "IMPORT_PREVIEW_STALE")
    pq2 = preview(statement(a1, "q", last, last, start, pq_rows))
    require(pq2["counts"] == {"rows": 2, "new": 0, "duplicate": 2, "suspect": 0, "error": 0}, f"Q xem trước lại: {pq2}")
    require(commit(pq2)["created"] == 0 and len(tx(a1, "CK MUON GIA")) == 1 and summary(a1)["balance_minor"] == "2480000",
            "Q commit lại không được ghi trùng")
    pr = preview(statement(a1, "r", last, last, start, pq_rows))
    first, second = race(pg, {"idempotency_key": "commit-r-1", "import_id": pr["import_id"], "expected_preview_hash": pr["preview_hash"]},
                         {"idempotency_key": "commit-r-2", "import_id": pr["import_id"], "expected_preview_hash": pr["preview_hash"]}, KT)
    require(first["confirmed"] == 2 and second.startswith("ERR:") and "IMPORT_PREVIEW_STALE" in second, f"khác khóa song song: {second[-400:]}")
    require(pg.value(f"SELECT count(*) FROM tien.event WHERE kind = 'import_commit' AND (\"after\" -> 'import' ->> 'id')::bigint = {pr['import_id']}")
            == "1", "lô R commit hơn một lần")
    cases.append("AT-03.5: P và Q chồng kỳ xem trước ở cùng version, commit P rồi Q → IMPORT_PREVIEW_STALE, xem trước lại Q → 0 mới, không "
                 "ghi trùng. Đồng thời (pg_blocking_pids): hai phiên commit cùng lô cùng khóa → phiên sau chờ khóa tài khoản rồi trả đúng "
                 "kết quả cũ, một event; khác khóa → phiên sau IMPORT_PREVIEW_STALE")

    # AT-12.1/12.2: lỗi dòng (ngày tương lai theo giờ VN, ngoài kỳ, trước số dư mở, số dòng trùng, chiều, số tiền, tiền tệ).
    err_lines = [line(1, month - dt.timedelta(days=1), "in", 1000, "TRUOC SO DU MO"), line(2, d(10), "in", 1000, "NGOAI KY"),
                 line(3, today + dt.timedelta(days=1), "in", 1000, "NGAY MAI"), line(4, d(3), "in", 1000, "TRUNG SO DONG A"),
                 line(4, d(3), "in", 2000, "TRUNG SO DONG B"), line(5, d(3), "both", 1000, "HAI CHIEU"),
                 line(6, d(3), "in", "12.5", "TIEN LE"), line(7, d(3), "in", 0, "KHONG DONG"), line(8, d(3), "in", None, "O TRONG"),
                 line(9, d(3), "in", 1000, "SAI TIEN TE", currency="USD"), line(10, d(4), "in", 7000, "DONG HOP LE GIA")]
    err = {**statement(a1, "loi", month - dt.timedelta(days=2), d(5), None, []), "lines": err_lines}
    pe = preview(err)
    require([ln["code"] for ln in pe["lines"]] == ["LINE_BEFORE_OPENING", "LINE_OUT_OF_PERIOD", "LINE_FUTURE_DATE", "LINE_DUPLICATE_NO",
                                                  "LINE_DUPLICATE_NO", "LINE_DIRECTION", "LINE_AMOUNT", "LINE_AMOUNT", "LINE_AMOUNT",
                                                  "LINE_CURRENCY", None]
            and pe["counts"]["error"] == 10 and pe["counts"]["new"] == 1, f"lỗi dòng: {pe['lines']}")
    t.reject("commit_import", {"import_id": pe["import_id"], "expected_preview_hash": pe["preview_hash"]}, KT, "IMPORT_HAS_ERRORS")
    t.reject("reject_import", {"import_id": pe["import_id"], "reason": "  "}, KT, "REASON_REQUIRED")
    t.reject("reject_import", {"import_id": pe["import_id"]}, RV, "TIEN_FORBIDDEN")
    require(t.cmd("reject_import", {"import_id": pe["import_id"], "reason": "file loi gia"}, KT)["status"] == "rejected", "bỏ lô")
    t.reject("reject_import", {"import_id": pe["import_id"], "reason": "lan hai"}, KT, "INVALID_COMMAND")
    t.reject("commit_import", {"import_id": pe["import_id"], "expected_preview_hash": pe["preview_hash"]}, KT, "IMPORT_PREVIEW_STALE")
    for bad in ({"line_no": 1.5}, {"booking_date": "2026-02-30"}, {"amount_minor": 1000}, {"cells": {"a": 1}}, {"them": "x"}):
        t.reject("preview_import", {**err, "lines": [{**err_lines[-1], **bad}]}, KT, "INVALID_COMMAND")
    # Gãy chuỗi số dư: số dư đầu khác số dư sổ, số dư sau lệch, số dư cuối lệch → BALANCE_CHAIN_BROKEN.
    gap = statement(a1, "gay", d(1), d(5), 1000001, x1_rows[:2])
    gap["lines"][0]["balance_after_minor"], gap["closing_minor"] = "1500000", "1300000"
    pg_gap = preview(gap)
    require([b["code"] for b in pg_gap["breaks"]] == ["OPENING_MISMATCH", "RUNNING_BALANCE", "CLOSING_MISMATCH"]
            and pg_gap["breaks"][1]["line_no"] == 1 and pg_gap["counts"]["duplicate"] == 2, f"gãy chuỗi: {pg_gap['breaks']}")
    t.reject("commit_import", {"import_id": pg_gap["import_id"], "expected_preview_hash": pg_gap["preview_hash"]}, KT,
             "BALANCE_CHAIN_BROKEN", detail="CLOSING_MISMATCH,OPENING_MISMATCH,RUNNING_BALANCE")
    t.cmd("reject_import", {"import_id": pg_gap["import_id"], "reason": "gay chuoi gia"}, KT)
    require(summary(a1)["balance_minor"] == "2480000", "lô lỗi/gãy làm đổi số dư")
    t.reject("preview_import", statement(a1, "mai", d(1), today + dt.timedelta(days=1), None, []), KT, "INVALID_COMMAND")
    cases.append("AT-12.1/12.2: ngày sau hôm nay (giờ VN), ngoài kỳ, trước số dư mở, số dòng trùng, chiều, số tiền (lẻ/0/trống), tiền tệ → "
                 "lớp error đúng mã; commit → IMPORT_HAS_ERRORS; bỏ lô cần lý do (REASON_REQUIRED), bỏ rồi không commit/bỏ lại được; "
                 "dòng sai cấu trúc → INVALID_COMMAND; kỳ có period_to là ngày mai → INVALID_COMMAND. Gãy chuỗi (OPENING_MISMATCH, "
                 "RUNNING_BALANCE, CLOSING_MISMATCH) → commit BALANCE_CHAIN_BROKEN, DETAIL liệt kê mã gãy")

    # Phiên gọi đặt standard_conforming_strings = off: chuẩn hóa mô tả không đổi (biểu thức chính quy không dùng dấu gạch chéo), ba dòng
    # khác khoảng trắng/hoa thường của ba giao dịch ngày 12 vẫn là trùng chắc, không thành nghi trùng hay mới.
    off = "SET LOCAL standard_conforming_strings = off; "
    require(pg.value(T.wrap("SELECT current_setting('standard_conforming_strings')", KT, pre=off), user=APP) == "off",
            "phiên thử không tắt được standard_conforming_strings")
    scs = statement(a1, "scs", d(12), d(12), 1600000, [(1, d(12), "in", 100000, "  CK   GIONG HET GIA "),
                                                       (2, d(12), "in", 100000, "CK GIONG  HET GIA  "),
                                                       (3, d(12), "in", 100000, " ck giong het gia")])
    ps = t.cmd("preview_import", scs, KT, pre=off)
    require(ps["counts"] == {"rows": 3, "new": 0, "duplicate": 3, "suspect": 0, "error": 0} and ps["breaks"] == []
            and [ln["candidate"] for ln in ps["lines"]] == tx(a1, "CK GIONG HET GIA"), f"standard_conforming_strings = off: {ps}")
    cases.append("phiên standard_conforming_strings = off: dấu vân không đổi, ba dòng khác khoảng trắng/hoa thường vẫn trùng chắc đúng ba "
                 "giao dịch ngày 12")

    # A2: Y1 rồi Y2 phủ trọn Y1 (AT-02.3), chân kia của chuyển nội bộ.
    y1_rows = [(1, d(3), "in", 200000, "NHAN NOI BO GIA"), (2, d(4), "out", 30000, "PHI GIA A2")]
    py1 = preview(statement(a2, "y1", d(1), d(5), 500000, y1_rows))
    commit(py1)
    py2 = preview(statement(a2, "y2", d(1), d(8), 500000, [*y1_rows, (3, d(7), "in", 70000, "CK GIA A2")]))
    require(py2["counts"]["duplicate"] == 2 and py2["counts"]["new"] == 1, f"Y2: {py2['counts']}")
    commit(py2)
    a2_in, a2_out = tx(a2, "NHAN NOI BO GIA")[0], tx(a2, "PHI GIA A2")[0]

    # Phân bổ trên giao dịch vào 500000 của A1 (AT-05.x) và giao dịch ra 200000 (chuyển nội bộ).
    t_in, t_out = tx(a1, "CK TIEN CUOC GIA 01")[0], tx(a1, "CHUYEN NOI BO GIA")[0]

    def alloc(tx_id: int, version: int, lines: list[tuple], **extra) -> dict:
        return {"transaction_id": tx_id, "expected_version": version, **extra,
                "lines": [{"target_kind": kind, "target_ref": ref, "amount_minor": str(amount)} for kind, ref, amount in lines]}

    cust = {"customer_id": "101"}
    r1 = t.cmd("set_allocation", alloc(t_in, 0, [("customer_unapplied", cust, 500000)]), KT)
    require((r1["status"], r1["version"], r1["unallocated_minor"]) == ("unapplied", 1, "0"), f"chỉ customer_unapplied: {r1}")
    t.reject("set_allocation", alloc(t_in, 0, [("customer_unapplied", cust, 500000)]), KT, "STALE_VERSION")
    t.reject("set_allocation", alloc(t_in, 1, [("ar_book", cust, 350000), ("customer_funds_pending", {}, 200000)]), KT, "OVER_ALLOCATION")
    split = [("ar_book", cust, 350000), ("customer_funds_pending", {}, 100000)]
    t.reject("set_allocation", alloc(t_in, 1, split), KT, "REASON_REQUIRED")
    r2 = t.cmd("set_allocation", alloc(t_in, 1, split, reason="phan loai lai gia"), KT)
    require((r2["status"], r2["allocated_minor"], r2["unallocated_minor"], r2["version"]) == ("partial", "450000", "50000", 2),
            f"AT-05.5 350/100/50: {r2}")
    require(t.cmd("set_allocation", alloc(t_in, 2, list(reversed(split))), KT, events=0)["unchanged"], "bộ y hệt phải không ghi")
    grow = alloc(t_in, 2, [*split, ("other", {}, 50000)])
    r3 = t.cmd("set_allocation", grow, KT, key="phan-bo-them")
    require((r3["status"], r3["version"], r3["unallocated_minor"]) == ("applied", 3, "0"), f"thêm dòng không cần lý do: {r3}")
    require(t.cmd("set_allocation", grow, KT, key="phan-bo-them", events=0, saved=0) == r3
            and t.cmd("set_allocation", {**grow, "expected_version": 3}, KT, key="phan-bo-them", events=0, saved=0) == r3,
            "gửi lại cùng khóa (kể cả version mới) phải trả kết quả cũ")
    t.reject("set_allocation", alloc(t_in, 3, split), KT, "IDEMPOTENCY_CONFLICT", key="phan-bo-them")
    for bad in ([("ar_book", {"customer_id": 101}, 1000)], [("ar_book", {"customer_id": "0"}, 1000)],
                [("expense_category", {}, 1000)], [("bank_fee", {"x": "1"}, 1000)], [("ar_book", cust, 0)],
                [("khong_co", {}, 1000)], [("internal_transfer", {"transaction_id": str(a2_out)}, 200000)],
                [("internal_transfer", {"transaction_id": str(t_in)}, 200000)]):
        t.reject("set_allocation", alloc(t_out, 0, bad), KT, "INVALID_COMMAND")
    r4 = t.cmd("set_allocation", alloc(t_out, 0, [("expense_category", {"category": " Xang dau gia "}, 50000)]), KT)
    require(r4["status"] == "partial" and r4["allocations"][0]["target_ref"] == {"category": "Xang dau gia"}, f"ra một phần: {r4}")
    r5 = t.cmd("set_allocation", alloc(t_out, 1, [("internal_transfer", {"transaction_id": str(a2_in)}, 200000)], reason="la chuyen noi bo"), KT)
    require(r5["status"] == "matched", f"ra khớp đủ: {r5}")
    t.reject("set_allocation", alloc(t_in, 3, split), RV, "TIEN_FORBIDDEN")
    st = summary(a1)["status_counts"]
    require(st == {"in": {"unidentified": 7, "unapplied": 0, "partial": 0, "applied": 1}, "out": {"unmatched": 2, "partial": 0, "matched": 1}},
            f"đếm trạng thái: {st}")
    cases.append("AT-05: vượt số tiền → OVER_ALLOCATION; sai expected_version → STALE_VERSION; bỏ/đổi dòng không lý do → REASON_REQUIRED; "
                 "350/100 trên 500 → partial (AT-05.5); thêm dòng không cần lý do; bộ y hệt không ghi; gửi lại cùng khóa (kể cả version "
                 "mới) → kết quả cũ, khác nội dung → IDEMPOTENCY_CONFLICT; trạng thái unidentified → unapplied → partial → applied, "
                 "unmatched → partial → matched; đích sai, chuyển nội bộ cùng chiều/cùng tài khoản → INVALID_COMMAND")

    # AT-02.2: hủy lô không lý do; hủy lô có giao dịch đang phân bổ → bị từ chối.
    t.reject("void_import", {"import_id": p1["import_id"]}, RV, "REASON_REQUIRED")
    t.reject("void_import", {"import_id": p1["import_id"], "reason": "nhap nham gia"}, RV, "VOID_WOULD_LOSE_ALLOCATED")
    t.reject("void_import", {"import_id": p1["import_id"], "reason": "nhap nham gia"}, KT, "TIEN_FORBIDDEN")
    t.reject("void_import", {"import_id": pe["import_id"], "reason": "lo da bo"}, RV, "INVALID_COMMAND")
    # AT-02.3: lô Y1 commit, lô Y2 chồng kỳ xác nhận trùng; hủy Y1 → giao dịch còn, số dư không đổi. Giao dịch còn nguồn ở Y2 đang
    # có phân bổ thì vẫn hủy được Y1, giao dịch và phân bổ còn nguyên.
    held = t.cmd("set_allocation", alloc(a2_in, 0, [("internal_transfer", {"transaction_id": str(t_out)}, 200000)]), KT)
    require(held["status"] == "applied", f"phân bổ chân nhận: {held}")
    before = summary(a2)
    v1 = t.cmd("void_import", {"import_id": py1["import_id"], "reason": "file thu nghiem gia"}, RV)
    after = summary(a2)
    require(v1["voided_transactions"] == [] and sorted(v1["kept_transactions"]) == sorted([a2_in, a2_out])
            and after["balance_minor"] == before["balance_minor"] == "740000" and after["transactions"] == 3, f"AT-02.3: {v1} {after}")
    row = next(x for x in listing(a2) if x["id"] == a2_in)
    require(sorted((s["import_id"], s["role"], s["import_status"]) for s in row["sources"])
            == sorted([(py1["import_id"], "origin", "voided"), (py2["import_id"], "duplicate_confirmed", "committed")]), f"nguồn: {row}")
    require((row["status"], row["allocated_minor"], row["version"]) == ("applied", "200000", 1)
            and pg.value(f"SELECT count(*) FROM tien.allocation WHERE bank_transaction_id = {a2_in} AND superseded_event IS NULL") == "1",
            f"phân bổ phải còn nguyên sau khi hủy Y1: {row}")
    cases.append("AT-02.2: hủy lô không lý do → REASON_REQUIRED; giao dịch sẽ hủy còn phân bổ → VOID_WOULD_LOSE_ALLOCATED; không vai review → "
                 "TIEN_FORBIDDEN. AT-02.3: Y1 commit, Y2 chồng kỳ xác nhận trùng; hủy Y1 → 0 giao dịch bị hủy, số dư không đổi, nguồn còn Y2; "
                 "giao dịch còn nguồn khác đang có phân bổ thì hủy lô được, giao dịch và phân bổ còn nguyên")

    # A3 mã ngân hàng ổn định: trùng theo mã dù mô tả khác; dấu vân dùng NFC + chữ thường Unicode; hủy lô làm mất giao dịch chỉ có ở lô đó.
    desc_vi = "Ứng tiền cọc giả"
    z1_rows = [(1, d(1), "in", 100000, "CHUYEN KHOAN GIA", "REF-GIA-1"), (2, d(2), "out", 40000, "PHI GIA A3", "REF-GIA-2"),
               (3, d(3), "in", 60000, desc_vi)]
    commit(preview(statement(a3, "z1", d(1), d(3), 2000000, z1_rows)))
    z2_rows = [(1, d(1), "in", 100000, "noi dung khac han", "REF-GIA-1"), (2, d(2), "out", 40000, "PHI GIA A3", " REF-GIA-2 "),
               (3, d(3), "in", 60000, unicodedata.normalize("NFD", desc_vi.upper())), (4, d(5), "in", 90000, "CK GIA A3", "REF-GIA-3")]
    z2 = statement(a3, "z2", d(1), d(5), 2000000, z2_rows)
    pz2 = preview(z2)
    require(pz2["counts"] == {"rows": 4, "new": 1, "duplicate": 3, "suspect": 0, "error": 0}, f"mã ổn định + NFC: {pz2['lines']}")
    commit(pz2)
    gone = tx(a3, "CK GIA A3")[0]
    v2 = t.cmd("void_import", {"import_id": pz2["import_id"], "reason": "tai nham file gia"}, RV)
    require(v2["voided_transactions"] == [gone] and len(v2["kept_transactions"]) == 3 and summary(a3)["balance_minor"] == "2120000",
            f"hủy Z2: {v2}")
    t.reject("set_allocation", alloc(gone, 0, [("other", {}, 1000)]), KT, "TRANSACTION_VOID")
    require(next(x for x in listing(a3) if x["id"] == gone)["status"] == "voided", "giao dịch đã hủy vẫn hiện, trạng thái voided")
    pz3 = preview(z2)
    require(pz3["counts"]["new"] == 1 and commit(pz3)["created"] == 1 and summary(a3)["balance_minor"] == "2210000",
            "nhập lại file của lô đã hủy: dòng của giao dịch đã hủy thành mới")
    cases.append("mã ngân hàng ổn định: trùng theo (tài khoản, họ nguồn, mã) dù mô tả khác, mã có khoảng trắng đầu cuối; mô tả NFD/chữ hoa "
                 "cùng dấu vân với NFC/chữ thường; hủy lô chỉ hủy giao dịch không còn nguồn khác, số dư về đúng; phân bổ giao dịch đã hủy → "
                 "TRANSACTION_VOID; nhập lại file của lô đã hủy được")

    # Nhiều dòng cùng mã ngân hàng trong một lô (chuyển khoản và phí chung mã): lần đầu mỗi dòng một giao dịch; tải lại ghép lần lượt
    # dòng thứ k với giao dịch thứ k cùng mã, dòng thừa là mới.
    m_rows = [(1, d(6), "out", 500000, "CK DI GIA", "REF-GIA-4"), (2, d(6), "out", 5000, "PHI CK GIA", "REF-GIA-4")]
    commit(preview(statement(a3, "m1", d(6), d(6), 2210000, m_rows)))
    transfer, fee = tx(a3, "CK DI GIA")[0], tx(a3, "PHI CK GIA")[0]
    pm2 = preview(statement(a3, "m2", d(6), d(6), 2210000, [*m_rows, (3, d(6), "out", 5000, "PHI CK GIA", "REF-GIA-4")]))
    require(pm2["counts"] == {"rows": 3, "new": 1, "duplicate": 2, "suspect": 0, "error": 0}
            and [ln["candidate"] for ln in pm2["lines"]] == [transfer, fee, None], f"nhiều dòng cùng mã: {pm2['lines']}")
    require(commit(pm2)["created"] == 1 and len(tx(a3, "PHI CK GIA")) == 2 and summary(a3)["balance_minor"] == str(2210000 - 510000),
            "nhiều dòng cùng mã: số dư")
    cases.append("nhiều dòng cùng mã ngân hàng trong một lô: lần đầu hai giao dịch; tải lại dòng thứ k trùng giao dịch thứ k cùng mã (đúng "
                 "chuyển khoản, đúng phí), dòng thừa cùng mã là mới; số dư đúng")

    # Mô tả đổi giữa hai lần tải (review độc lập, mức CAO): cùng giao dịch "CK ABC" ngày 12 nay là "CK ABC FT123" → dấu vân khác; bước 4b
    # ghép mềm theo ngày ghi sổ, chiều, số tiền thành nghi trùng; thiếu quyết định bị từ chối; chỉ người có thêm vai review mới quyết được;
    # quyết "trùng của" đúng giao dịch thì không ghi hai lần, số dư bằng số dư cuối của ngân hàng.
    commit(preview(statement(a4, "d1", d(1), d(15), 1000000, [(1, d(12), "in", 300000, "CK ABC"), (2, d(14), "out", 20000, "PHI GIA A4")])))
    abc, phi4 = tx(a4, "CK ABC")[0], tx(a4, "PHI GIA A4")[0]
    d2 = statement(a4, "d2", d(10), d(20), 1000000, [(1, d(12), "in", 300000, "CK ABC FT123"), (2, d(14), "out", 20000, "PHI GIA A4"),
                                                     (3, d(18), "in", 40000, "CK GIA A4 MOI")])
    pd2 = preview(d2)
    require(pd2["counts"] == {"rows": 3, "new": 1, "duplicate": 1, "suspect": 1, "error": 0} and pd2["breaks"] == []
            and [(ln["class"], ln["candidate"]) for ln in pd2["lines"]] == [("suspect", abc), ("duplicate", phi4), ("new", None)],
            f"mô tả đổi: {pd2['lines']} {pd2['breaks']}")
    body_d2 = {"import_id": pd2["import_id"], "expected_preview_hash": pd2["preview_hash"]}
    same_abc = [{"line_no": 1, "decision": "duplicate_of", "transaction_id": abc}]
    t.reject("commit_import", body_d2, KT, "IMPORT_SUSPECT_UNRESOLVED")
    t.reject("commit_import", {**body_d2, "suspect_decisions": same_abc}, KT, "TIEN_FORBIDDEN")
    t.reject("commit_import", {**body_d2, "suspect_decisions": same_abc}, NA2, "ENTITY_SCOPE")
    cd2 = commit(pd2, KTT, decisions=same_abc)
    require(cd2["created"] == 1 and cd2["confirmed"] == 2 and tx(a4, "CK ABC FT123") == []
            and summary(a4)["balance_minor"] == d2["closing_minor"] == "1320000", f"mô tả đổi phải không ghi hai lần: {cd2}")
    require(json.loads(pg.value("SELECT \"after\" -> 'suspect_decisions' FROM tien.event WHERE kind = 'import_commit' ORDER BY id DESC LIMIT 1"))
            == same_abc, "quyết định nghi trùng phải vào vết")
    cases.append("mô tả đổi giữa hai lần tải (CK ABC → CK ABC FT123): dòng thành suspect với ứng viên mềm cùng ngày/chiều/số tiền; commit "
                 "không quyết định → IMPORT_SUSPECT_UNRESOLVED; người chỉ có tien_nhap gửi quyết định → TIEN_FORBIDDEN, có review ở "
                 "pháp nhân khác → ENTITY_SCOPE; người review quyết duplicate_of đúng giao dịch → không thêm giao dịch, số dư = số dư cuối "
                 "ngân hàng, quyết định vào vết")

    # duplicate_of chỉ nhận giao dịch hiệu lực cùng tài khoản, cùng ngày ghi sổ, chiều, số tiền, chưa bị dòng khác nhận. Giao dịch đã có
    # trong kỳ mà file không nhận → UNMATCHED_EXISTING; người review giữ có lý do (keep_existing) mới commit được.
    v0 = preview(statement(a5, "v0", d(12), d(12), 1000000, [(1, d(12), "in", 300000, "CK HUY GIA")]))
    commit(v0)
    voided_tx = tx(a5, "CK HUY GIA")[0]
    t.cmd("void_import", {"import_id": v0["import_id"], "reason": "lo thu gia"}, RV)
    v1_rows = [(1, d(5), "in", 300000, "CK NGAY KHAC"), (2, d(12), "in", 70000, "CK TIEN KHAC"),
               (3, d(12), "in", 300000, "CK GOC 1"), (4, d(12), "in", 300000, "CK GOC 2")]
    pv1 = preview(statement(a5, "v1", d(1), d(15), 1000000, v1_rows))
    require(pv1["counts"]["new"] == 4 and pv1["breaks"] == [], f"V1: {pv1['counts']} {pv1['breaks']}")
    commit(pv1)
    other_day, small, g1, g2 = (tx(a5, desc)[0] for desc in ("CK NGAY KHAC", "CK TIEN KHAC", "CK GOC 1", "CK GOC 2"))
    pv2 = preview(statement(a5, "v2", d(12), d(12), 1300000, [(1, d(12), "in", 300000, "CK GOC 1 FT9"),
                                                              (2, d(12), "in", 300000, "CK GOC 2 FT9")]))
    require(pv2["counts"] == {"rows": 2, "new": 0, "duplicate": 0, "suspect": 2, "error": 0}
            and [ln["candidate"] for ln in pv2["lines"]] == [g1, g2]
            and pv2["breaks"] == [{"code": "UNMATCHED_EXISTING", "transaction_id": small, "booking_date": str(d(12)), "direction": "in",
                                   "amount_minor": "70000"}]
            and (pv2["balance"]["chain_breaks"], pv2["balance"]["unmatched_existing"]) == (0, 1), f"V2: {pv2}")
    body_v2 = {"import_id": pv2["import_id"], "expected_preview_hash": pv2["preview_hash"]}
    good = [{"line_no": 1, "decision": "duplicate_of", "transaction_id": g1}, {"line_no": 2, "decision": "duplicate_of", "transaction_id": g2}]
    for target in (small, other_day, voided_tx, g2):  # khác số tiền, khác ngày, đã hủy, đã bị dòng 2 nhận
        t.reject("commit_import", {**body_v2, "suspect_decisions": [{**good[0], "transaction_id": target}, good[1]]}, KTT,
                 "DUPLICATE_TARGET_INVALID")
    t.reject("commit_import", {**body_v2, "suspect_decisions": good}, KTT, "BALANCE_CHAIN_BROKEN", detail="UNMATCHED_EXISTING")
    for no_reason in ([{"transaction_id": small, "reason": "   "}], [{"transaction_id": small}]):
        t.reject("commit_import", {**body_v2, "suspect_decisions": good, "keep_existing": no_reason}, KTT, "REASON_REQUIRED")
    for outside in (other_day, g1):  # ngoài U (khác ngày); trong U nhưng đã là đích duplicate_of
        t.reject("commit_import", {**body_v2, "suspect_decisions": good, "keep_existing": [{"transaction_id": outside, "reason": "x"}]},
                 KTT, "INVALID_COMMAND")
    keep = [{"transaction_id": small, "reason": "giao dich co that, file nay thieu gia"}]
    t.reject("commit_import", {**body_v2, "keep_existing": keep}, KT, "TIEN_FORBIDDEN")
    cv2 = commit(pv2, KTT, decisions=good, keep=keep)
    require((cv2["created"], cv2["confirmed"], cv2["kept"]) == (0, 2, 1) and summary(a5)["balance_minor"] == "1970000"
            and len(tx(a5, "CK TIEN KHAC")) == 1, f"duplicate_of + keep_existing: {cv2}")
    require(json.loads(pg.value("SELECT \"after\" -> 'kept' FROM tien.event WHERE kind = 'import_commit' ORDER BY id DESC LIMIT 1")) == keep,
            "giao dịch giữ và lý do phải vào vết")
    cases.append("duplicate_of đúng giao dịch (cùng ngày, chiều, số tiền, chưa ai nhận) commit được; đích khác số tiền, khác ngày, đã hủy, đã "
                 "bị dòng khác nhận → DUPLICATE_TARGET_INVALID. File thiếu một giao dịch đã có trong kỳ → UNMATCHED_EXISTING (vào băm xem "
                 "trước); commit không giữ → BALANCE_CHAIN_BROKEN (DETAIL UNMATCHED_EXISTING); keep_existing thiếu lý do → "
                 "REASON_REQUIRED, id ngoài U hoặc đã là đích duplicate_of → INVALID_COMMAND, không có vai review → TIEN_FORBIDDEN; người "
                 "review giữ có lý do → commit, lý do vào vết")

    # Lượt review 2 — D3: hai dòng cùng ngày/chiều/số tiền, U chỉ có một giao dịch → cả hai là suspect với cùng danh sách ứng viên mềm,
    # không gán theo thứ tự dòng; người chỉ có tien_review quyết (dòng 1 trùng X, dòng 2 mới) → commit được, sổ cuối ngày = ngân hàng.
    commit(preview(statement(a4, "d3x", d(16), d(16), 1280000, [(1, d(16), "in", 50000, "CK X GIA")])))
    x16 = tx(a4, "CK X GIA")[0]
    pd3 = preview(statement(a4, "d3", d(16), d(16), 1280000, [(1, d(16), "in", 50000, "CK X GIA FT1"), (2, d(16), "in", 50000, "CK Y GIA")]))
    require(pd3["counts"]["suspect"] == 2 and pd3["breaks"] == []
            and [(ln["class"], ln["candidate"], ln["soft_candidates"]) for ln in pd3["lines"]] == [("suspect", None, [x16])] * 2,
            f"D3: {pd3['lines']}")
    t.reject("commit_import", {"import_id": pd3["import_id"], "expected_preview_hash": pd3["preview_hash"]}, KT, "IMPORT_SUSPECT_UNRESOLVED")
    cd3 = commit(pd3, RV, decisions=[{"line_no": 1, "decision": "duplicate_of", "transaction_id": x16}, {"line_no": 2, "decision": "new"}])
    end16 = pg.value("SELECT (o.amount_minor + coalesce(sum(CASE x.direction WHEN 'in' THEN x.amount_minor ELSE -x.amount_minor END), 0))::text "
                     f"FROM tien.account_opening o LEFT JOIN tien.bank_transaction x ON x.account_id = o.account_id AND x.voided_event IS NULL "
                     f"AND x.booking_date <= {lit(d(16))} WHERE o.account_id = {a4} GROUP BY o.amount_minor")
    require((cd3["created"], cd3["confirmed"]) == (1, 1) and end16 == "1380000", f"D3: {cd3}, số dư cuối ngày 16 {end16}")
    cases.append("D3: hai dòng cùng ngày/chiều/số tiền mà U chỉ có một giao dịch → cả hai suspect, ứng viên mềm là cả danh sách, không gán "
                 "theo thứ tự; người chỉ có tien_review quyết và commit được; quyết đúng → số dư sổ cuối ngày bằng ngân hàng")

    # D2: dòng nghi trùng mềm quyết new mà không giữ giao dịch cũ → BALANCE_CHAIN_BROKEN (UNMATCHED_EXISTING); giữ có lý do → commit,
    # sổ có cả giao dịch cũ lẫn giao dịch mới.
    moi = tx(a4, "CK GIA A4 MOI")[0]
    pdk = preview(statement(a4, "d2k", d(18), d(18), 1380000, [(1, d(18), "in", 40000, "CK KHACH KHAC GIA")]))
    require([(ln["class"], ln["candidate"], ln["soft_candidates"]) for ln in pdk["lines"]] == [("suspect", moi, [moi])]
            and pdk["breaks"] == [], f"D2: {pdk['lines']} {pdk['breaks']}")
    as_new = [{"line_no": 1, "decision": "new"}]
    body_dk = {"import_id": pdk["import_id"], "expected_preview_hash": pdk["preview_hash"], "suspect_decisions": as_new}
    t.reject("commit_import", body_dk, RV, "BALANCE_CHAIN_BROKEN", detail="UNMATCHED_EXISTING")
    before_dk = int(summary(a4)["balance_minor"])
    keep_moi = [{"transaction_id": moi, "reason": "hai khach cung chuyen so nay trong ngay gia"}]
    cdk = commit(pdk, RV, decisions=as_new, keep=keep_moi)
    require((cdk["created"], cdk["confirmed"], cdk["kept"]) == (1, 0, 1) and int(summary(a4)["balance_minor"]) == before_dk + 40000
            and tx(a4, "CK GIA A4 MOI") == [moi] and len(tx(a4, "CK KHACH KHAC GIA")) == 1, f"D2: {cdk}")
    cases.append("D2: dòng nghi trùng mềm quyết new, không keep_existing → BALANCE_CHAIN_BROKEN (UNMATCHED_EXISTING); giữ giao dịch cũ có "
                 "lý do → commit, sổ có cả giao dịch cũ và mới, số dư tăng đúng số tiền dòng mới")

    # R2: tài khoản mã ổn định, REF-GIA-1 đã có; file chỉ có REF-GIA-9 cùng ngày, chiều, số tiền → dòng là new (mã khác là giao dịch
    # khác, không ghép mềm), REF-GIA-1 thành UNMATCHED_EXISTING; commit không giữ → bị chặn; người chỉ có review mà lô không có quyết
    # định → TIEN_FORBIDDEN (lô không có quyết định cần tien_nhap).
    ref1 = tx(a3, "CHUYEN KHOAN GIA")[0]
    pr2 = preview(statement(a3, "r2", d(1), d(1), 2000000, [(1, d(1), "in", 100000, "CK REF HAI GIA", "REF-GIA-9")]))
    require([(ln["class"], ln["candidate"], ln["soft_candidates"]) for ln in pr2["lines"]] == [("new", None, None)]
            and [(b["code"], b["transaction_id"]) for b in pr2["breaks"]] == [("UNMATCHED_EXISTING", ref1)], f"R2: {pr2}")
    body_r2 = {"import_id": pr2["import_id"], "expected_preview_hash": pr2["preview_hash"]}
    t.reject("commit_import", body_r2, KT, "BALANCE_CHAIN_BROKEN", detail="UNMATCHED_EXISTING")
    t.reject("commit_import", body_r2, RV, "TIEN_FORBIDDEN")
    cases.append("R2: tài khoản mã ổn định, file chỉ có mã khác cùng ngày/chiều/số tiền → dòng new, giao dịch mã cũ thành UNMATCHED_EXISTING, "
                 "commit không giữ → BALANCE_CHAIN_BROKEN; lô không có quyết định mà người gửi chỉ có tien_review → TIEN_FORBIDDEN")

    # R3 (review độc lập lượt 3, mức TB): ngân hàng dùng lại mã REF-GIA-1 (đã có ở ngày 1, 100000) cho giao dịch ngày 11, 300000. Trước
    # bản sửa, dòng thành duplicate của giao dịch ngày 1 nằm ngoài kỳ, không chỗ gãy nào bắt, sổ thiếu 300000 so với ngân hàng. Nay chỉ
    # ghép theo mã khi cùng ngày, chiều, số tiền: dòng là new, commit tạo giao dịch, số dư sổ = số dư cuối của file.
    start11 = summary(a3)["balance_minor"]
    r3 = statement(a3, "r3", d(11), d(11), int(start11), [(1, d(11), "in", 300000, "CK DUNG LAI MA GIA", "REF-GIA-1")])
    pr3 = preview(r3)
    require(pr3["counts"] == {"rows": 1, "new": 1, "duplicate": 0, "suspect": 0, "error": 0}
            and [(ln["class"], ln["candidate"], ln["soft_candidates"]) for ln in pr3["lines"]] == [("new", None, None)]
            and pr3["breaks"] == [], f"R3: {pr3}")
    cr3 = commit(pr3)
    require(cr3["created"] == 1 and summary(a3)["balance_minor"] == r3["closing_minor"] == str(int(start11) + 300000)
            and len(tx(a3, "CK DUNG LAI MA GIA")) == 1 and tx(a3, "CHUYEN KHOAN GIA") == [ref1], f"R3: {cr3}")
    cases.append("R3: tài khoản mã ổn định, ngân hàng dùng lại mã cũ cho giao dịch khác ngày và số tiền (giao dịch cũ ngoài kỳ) → dòng new, "
                 "không gãy, commit tạo giao dịch, số dư sổ = số dư cuối file; giao dịch cũ cùng mã giữ nguyên")

    # AT-06.x / AT-08.2: vai ở pháp nhân A gọi thẳng lệnh trên tài khoản pháp nhân B → ENTITY_SCOPE; không vai → TIEN_FORBIDDEN.
    w1 = statement(b1, "w1", d(1), d(3), 300000, [(1, d(2), "in", 120000, "CK GIA B")])
    pw1 = preview(w1, NB)
    commit(pw1, NB)
    b_tx = tx(b1, "CK GIA B")[0]
    t.reject("preview_import", statement(b1, "w2", d(1), d(3), 300000, []), KT, "ENTITY_SCOPE")
    t.reject("commit_import", {"import_id": pw1["import_id"], "expected_preview_hash": pw1["preview_hash"]}, KT, "ENTITY_SCOPE")
    t.reject("set_allocation", alloc(b_tx, 0, [("other", {}, 1000)]), KT, "ENTITY_SCOPE")
    t.reject("void_import", {"import_id": pw1["import_id"], "reason": "x"}, RV, "ENTITY_SCOPE")
    t.reject("set_opening", opening(b1, 1), QT_A, "ENTITY_SCOPE")
    t.reject("set_allocation", alloc(t_out, 2, [("internal_transfer", {"transaction_id": str(b_tx)}, 200000)], reason="x"), KT,
             "ENTITY_SCOPE")
    t.reject("preview_import", statement(a1, "w3", d(1), d(3), None, []), NB, "ENTITY_SCOPE")
    t.reject("preview_import", statement(b1, "w4", d(1), d(3), None, []), LA, "TIEN_FORBIDDEN")
    t.reject("preview_import", {**statement(b1, "w5", d(1), d(3), None, []), "account_id": 999999}, KT, "INVALID_COMMAND")
    t.read_reject("get_account_summary", str(b1), KT, "ENTITY_SCOPE")
    t.read_reject("get_account_summary", str(a2), XEM, "ENTITY_SCOPE")
    t.read_reject("list_transactions", f"{a1}, NULL, NULL", LA, "TIEN_FORBIDDEN")
    t.read_reject("get_account_summary", str(a1), None, "ACTOR_REQUIRED")
    cases.append("AT-06.x/AT-08.2: gọi thẳng bằng ID — vai ở pháp nhân A trên tài khoản/lô/giao dịch của B (xem trước, commit, phân bổ, "
                 "hủy lô, số dư mở, chuyển nội bộ sang B) → ENTITY_SCOPE; vai một tài khoản đọc tài khoản khác → ENTITY_SCOPE; không vai "
                 "→ TIEN_FORBIDDEN; thiếu người làm → ACTOR_REQUIRED")

    # Hàm đọc: mô tả chỉ cho tien_nhap/tien_review; login tien_reader đọc được; số liệu khớp tính thẳng.
    full, masked = t.read("list_transactions", f"{a1}, NULL, NULL", KT), t.read("list_transactions", f"{a1}, NULL, NULL", XEM)
    require(full["description_visible"] and all("description" in x for x in full["transactions"])
            and not masked["description_visible"] and all("description" not in x for x in masked["transactions"])
            and len(full["transactions"]) == len(masked["transactions"]) == 11, "mô tả chỉ trả cho tien_nhap/tien_review")
    require(all("description" in x for x in listing(a1, RV)), "tien_review thấy mô tả")
    window = t.read("list_transactions", f"{a1}, {lit(d(10))}::date, {lit(d(12))}::date", XEM)["transactions"]
    require([x["booking_date"] for x in window] == [str(d(10))] + [str(d(12))] * 3, f"lọc theo ngày: {window}")
    t.read_reject("list_transactions", f"{a1}, {lit(d(12))}::date, {lit(d(10))}::date", KT, "INVALID_COMMAND")
    watch = t.read("get_account_summary", str(a1), XEM, user=READER)
    require(watch["balance_minor"] == "2480000" and watch["opening"] == {"as_of": str(month), "amount_minor": "1000000"},
            f"login máy canh đọc: {watch}")
    cases.append("hàm đọc: tóm tắt (số dư mở, Σ vào/ra, số dư, ngày mới nhất, đếm trạng thái), danh sách theo khoảng ngày có nguồn, "
                 "version; mô tả chỉ cho tien_nhap/tien_review; login tien_reader đọc được; từ > đến → INVALID_COMMAND")

    # Bất biến tính thẳng từ bảng; AT-02.1 phía chủ schema: UPDATE/DELETE/TRUNCATE bảng chỉ thêm bị trigger chặn.
    invariants(pg, t, {a1: KT, a2: KT, a3: KT, a4: KT, a5: KT, b1: NB})
    for stmt in ("UPDATE tien.currency SET minor_unit = minor_unit", "DELETE FROM tien.event",
                 "UPDATE tien.event SET actor = actor || 'x'", "UPDATE tien.legal_entity SET name = name || 'x'",
                 "UPDATE tien.financial_account SET currency = 'USD'", "UPDATE tien.financial_account SET version = version + 5",
                 "DELETE FROM tien.financial_account", "UPDATE tien.account_opening SET amount_minor = amount_minor + 1",
                 "UPDATE tien.access_grant SET role = 'tien_quan_tri'",
                 "UPDATE tien.access_grant SET revoked_event = NULL WHERE revoked_event IS NOT NULL",
                 "UPDATE tien.statement_import SET period_to = period_to + 1",
                 "UPDATE tien.statement_import SET status = 'validated', committed_event = NULL WHERE status = 'committed'",
                 "UPDATE tien.raw_statement_line SET cells = '{}'", "UPDATE tien.bank_transaction SET amount_minor = amount_minor + 1",
                 "UPDATE tien.bank_transaction SET voided_event = NULL WHERE voided_event IS NOT NULL",
                 "DELETE FROM tien.bank_transaction_source", "UPDATE tien.allocation SET amount_minor = amount_minor + 1",
                 "UPDATE tien.allocation SET superseded_event = NULL WHERE superseded_event IS NOT NULL",
                 "DELETE FROM tien.idempotency", "TRUNCATE tien.idempotency", "TRUNCATE tien.allocation"):
        pg.rejects(f"BEGIN; SET LOCAL ROLE tien_owner; {stmt}; COMMIT", message="IMMUTABLE")
    cases.append("bất biến tính thẳng từ bảng: I-1 số dư = mở + vào − ra (so get_account_summary), I-4, I-5, I-6, I-8, I-10; mọi event có "
                 "before/after là object; mỗi lệnh ghi đúng số event và khóa lặp (kiểm từng lệnh). AT-02.1 chủ schema: UPDATE/DELETE/"
                 "TRUNCATE bảng chỉ thêm, đổi cột trạng thái sai chiều đều bị trigger chặn")

    pg.rejects(ROLLBACK.read_text(encoding="utf-8"), message="TIEN_HAS_DATA")
    require(pg.value("SELECT to_regnamespace('tien') IS NOT NULL") == "t", "hoàn tác khi đã có dữ liệu phải dừng")
    cases.append("hoàn tác tự dừng (TIEN_HAS_DATA) cả khi đã có lô sao kê/giao dịch, schema còn nguyên")


def main() -> int:
    for stream in (sys.stdout, sys.stderr):  # Windows chuyển hướng ra file thì mặc định cp1252
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure:
            reconfigure(encoding="utf-8", errors="backslashreplace")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--report", type=Path, help="ghi báo cáo JSON")
    args = ap.parse_args()
    cases: list[str] = []
    report = {"spec": "specs/so-tien-p0a.md", "image": IMAGE, "cases": cases, "result": "fail", "cleanup": "not_started"}
    started = time.monotonic()
    try:
        with disposable_database(report) as pg:
            before = pg.value(SOKHACH_PRINT)
            check_migration(pg, cases)
            check_grants(pg, cases)
            scenario(pg, cases)
            require(pg.value(SOKHACH_PRINT) == before, "catalog/quyền/role của sokhach đổi sau migration và lệnh sổ tiền")
            cases.append("catalog sokhach (hàm, bảng, quyền, role, thành viên) không đổi sau migration, hoàn tác và mọi lệnh sổ tiền")
        report["result"] = "pass"
    except (HarnessError, OSError, ValueError, KeyError, StopIteration, IndexError, TypeError) as exc:
        report["error"] = f"{type(exc).__name__}: {str(exc)[-3000:]}"
    report["seconds"] = round(time.monotonic() - started, 1)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return int(report["result"] != "pass" or report["cleanup"] != "verified_and_removed")


if __name__ == "__main__":
    sys.exit(main())
