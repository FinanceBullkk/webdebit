"""SO-TIEN P0-a lát 2 (specs/so-tien-p0a-lat2.md): API sổ tiền — cờ, cổng shadow, bot chỉ-đọc, kiểm thân lệnh trước DB, đường đọc,
SQL cố định khớp hàm migration cấp cho tien_app, mã lỗi có câu thông báo, DETAIL trả kèm, file gốc, file Excel. Dữ liệu bịa."""

import base64
import hashlib
import http.client
import io
import json
import os
import re
import sys
import threading
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path
from unittest import mock
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "web"))
import v7_api_tables as tables  # noqa: E402
import v7_api_tien as tien  # noqa: E402
import v7_identity as identity  # noqa: E402
import v7_ledger_api as api  # noqa: E402
import v7_xlsx_writer  # noqa: E402

MIGRATIONS = [ROOT / "tools" / "migrations" / "2026-11-24-tien-p0a-lat1.sql", ROOT / "tools" / "migrations" / "2026-11-25-tien-p0a-lat2.sql"]
ACTOR = "ketoan@gia.test"
HASH = "a" * 64


def grants(*roles):
    return {"actor": ACTOR, "grants": [{"role": r, "legal_entity_id": 1, "legal_entity_code": "PN-GIA", "account_id": None} for r in roles]}


def demo_csv(rows="2026-10-01,FT1,CK GIA MOT,,50000,1050000\n2026-10-02,,CHI GIA HAI,20000,,1030000\n") -> bytes:
    return ("#period,2026-10-01,2026-10-03,partial\n#opening,1000000\n#closing,1030000\n"
            "date,ref,description,debit,credit,balance\n" + rows).encode()


class FakePsql:
    def __init__(self, results=None):
        self.calls, self.results = [], dict(results or {})

    def run(self, function, payload, actor, **options):
        self.calls.append((function, payload, actor, options))
        value = self.results.get(function, {"function": function})
        return value(payload) if callable(value) else value


class TienApiTest(unittest.TestCase):
    def setUp(self):
        self.headers = {"Host": "127.0.0.1:8780", "Origin": "http://127.0.0.1:8780", "Content-Type": "application/json"}
        saved = tien.CONFIG
        tien.CONFIG = tien.Config("on", None)
        self.addCleanup(setattr, tien, "CONFIG", saved)
        env = mock.patch.dict(os.environ, {"WEBDEBIT_TIEN_DEMO": "1"})
        env.start()
        self.addCleanup(env.stop)

    def call(self, method, path, body=None, *, results=None, raw=None):
        runner = FakePsql({"tien_my_access": grants("tien_nhap", "tien_review"),
                           "tien_get_account_card": {"account": {"id": 7, "currency": "VND"}}, **(results or {})})
        data = raw if raw is not None else json.dumps(body, ensure_ascii=False).encode() if body is not None else b""
        status, value = api.handle(method, path, self.headers, data, runner, port=8780, host="127.0.0.1", actor=ACTOR)
        self.assertEqual(status, 200)
        self.assertTrue(all(call[2] == ACTOR for call in runner.calls), "người làm lấy từ phiên, không từ thân lệnh")
        return runner, value

    def rejects(self, method, path, body, code, **kw):
        with self.assertRaises(api.ApiError) as caught:
            self.call(method, path, body, **kw)
        self.assertEqual(caught.exception.code, code, body)
        return caught.exception

    def test_flag_off_hides_every_route(self):
        self.assertEqual([tien.mode_from_env(v) for v in (None, "", "on", "shadow", "off", "ON", "yes")],
                         ["off", "off", "on", "shadow", "off", "off", "off"])
        tien.CONFIG = tien.Config("off", None)
        for method, path in (("GET", "/api/v7/tien/me"), ("GET", "/api/v7/tien/accounts"), ("POST", "/api/v7/tien/days/reopen")):
            error = self.rejects(method, path, {} if method == "POST" else None, "TIEN_OFF")
            self.assertEqual(error.status, 404)
        with self.assertRaises(api.ApiError) as caught:
            tien.binary("/api/v7/tien/files/3", "", FakePsql(), ACTOR)
        self.assertEqual(caught.exception.code, "TIEN_OFF")

    def test_shadow_only_reviewer_or_admin(self):
        tien.CONFIG = tien.Config("shadow", None)
        _, me = self.call("GET", "/api/v7/tien/me", results={"tien_my_access": grants("tien_nhap")})
        self.assertEqual((me["visible"], me["grants"]), (False, []))
        self.rejects("GET", "/api/v7/tien/accounts", None, "TIEN_FORBIDDEN", results={"tien_my_access": grants("tien_nhap")})
        self.rejects("POST", "/api/v7/tien/days/reopen", {}, "TIEN_FORBIDDEN", results={"tien_my_access": grants("tien_xem")})
        for role in ("tien_review", "tien_quan_tri"):
            runner, _ = self.call("GET", "/api/v7/tien/accounts", results={"tien_my_access": grants(role)})
            self.assertEqual([c[0] for c in runner.calls], ["tien_my_access", "tien_list_accounts"])
        _, me = self.call("GET", "/api/v7/tien/me", results={"tien_my_access": grants("tien_review")})
        self.assertTrue(me["visible"])

    def test_me_lists_grants_and_templates(self):
        _, me = self.call("GET", "/api/v7/tien/me")
        self.assertEqual((me["mode"], me["visible"], [g["role"] for g in me["grants"]]), ("on", True, ["tien_nhap", "tien_review"]))
        self.assertEqual([t["id"] for t in me["templates"]], ["demo-csv@1"])
        _, me = self.call("GET", "/api/v7/tien/me", results={"tien_my_access": grants()})
        self.assertFalse(me["visible"])
        with mock.patch.dict(os.environ, {"WEBDEBIT_TIEN_DEMO": ""}):
            self.assertEqual(self.call("GET", "/api/v7/tien/me")[1]["templates"], [])
        self.rejects("GET", "/api/v7/tien/me?x=1", None, "INVALID_REQUEST")

    def test_reads_call_fixed_functions(self):
        today = datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")).date()
        cases = [
            ("/api/v7/tien/accounts", "tien_list_accounts", {}),
            ("/api/v7/tien/accounts/7", "tien_get_account_card", {"account_id": 7}),
            ("/api/v7/tien/accounts/7/coverage?from=2026-10-01&to=2026-10-31", "tien_get_coverage",
             {"account_id": 7, "from": "2026-10-01", "to": "2026-10-31"}),
            ("/api/v7/tien/accounts/7/coverage", "tien_get_coverage",
             {"account_id": 7, "from": (today - timedelta(days=44)).isoformat(), "to": today.isoformat()}),
            ("/api/v7/tien/accounts/7/days/2026-10-05", "tien_get_day", {"account_id": 7, "date": "2026-10-05"}),
            ("/api/v7/tien/accounts/7/imports", "tien_list_imports", {"account_id": 7}),
            ("/api/v7/tien/accounts/7/transactions?from=2026-10-01&to=2026-10-31", "tien_list_transactions",
             {"account_id": 7, "from": "2026-10-01", "to": "2026-10-31"}),
            ("/api/v7/tien/imports/9", "tien_get_import", {"import_id": 9}),
            ("/api/v7/tien/transactions/11", "tien_get_transaction", {"transaction_id": 11}),
        ]
        for path, function, payload in cases:
            runner, _ = self.call("GET", path)
            self.assertEqual(runner.calls[-1][:2], (function, payload), path)
            self.assertEqual(runner.calls[-1][3], {"consistent": True}, "đọc trong giao dịch chỉ-đọc cùng ảnh dữ liệu")
        for path in ("/api/v7/tien/accounts/0", "/api/v7/tien/accounts/abc", "/api/v7/tien/nope", "/api/v7/tien/files/3"):
            self.rejects("GET", path, None, "NOT_FOUND")
        for path in ("/api/v7/tien/accounts/7/days/2026-02-30", "/api/v7/tien/accounts/7?x=1",
                     "/api/v7/tien/accounts/7/coverage?from=2026-10-31&to=2026-10-01",
                     "/api/v7/tien/accounts/7/coverage?from=2026-01-01&to=2026-10-01",
                     "/api/v7/tien/accounts/7/coverage?from=2026-10-01&from=2026-10-02&to=2026-10-31",
                     "/api/v7/tien/accounts/7/transactions?thang=10"):
            self.rejects("GET", path, None, "INVALID_REQUEST")

    def test_import_read_with_raw_cells_is_logged(self):
        errors = io.StringIO()
        with mock.patch.object(sys, "stderr", errors):
            self.call("GET", "/api/v7/tien/imports/9", results={"tien_get_import": {"raw_visible": True, "lines": []}})
            self.call("GET", "/api/v7/tien/imports/10", results={"tien_get_import": {"raw_visible": False, "lines": []}})
        self.assertEqual(errors.getvalue(), f"SO-TIEN: {ACTOR} mở lô có ô gốc 9\n")

    def test_writes_pass_body_as_is(self):
        decision = {"line_no": 3, "decision": "duplicate_of", "transaction_id": 41}
        line = {"target_kind": "customer_unapplied", "target_ref": {"customer_id": "12"}, "amount_minor": "50000", "note": "gia"}
        cases = [
            ("/imports/commit", "tien_commit_import", {"import_id": 9, "expected_preview_hash": HASH}),
            ("/imports/commit", "tien_commit_import", {"import_id": 9, "expected_preview_hash": HASH, "suspect_decisions": [decision],
                                                       "keep_existing": [{"transaction_id": 5, "reason": "giu gia"}]}),
            ("/imports/reject", "tien_reject_import", {"import_id": 9, "reason": "file sai"}),
            ("/imports/void", "tien_void_import", {"import_id": 9, "reason": "nhap nham"}),
            ("/imports/void", "tien_void_import", {"import_id": 9}),
            ("/allocations", "tien_set_allocation", {"transaction_id": 41, "expected_version": 0, "lines": [line]}),
            ("/allocations", "tien_set_allocation", {"transaction_id": 41, "expected_version": 2, "lines": [], "reason": "go"}),
            ("/balance-evidence", "tien_record_balance_evidence", {"account_id": 7, "as_of_date": "2026-10-05",
                                                                    "amount_minor": "-25000", "source": "bank_pdf", "note": "pdf gia"}),
            ("/days/sign-coverage", "tien_sign_day_coverage", {"account_id": 7, "business_date": "2026-10-05", "expected_version": 4}),
            ("/days/sign-business", "tien_sign_day_business", {"account_id": 7, "business_date": "2026-10-05", "note": "con 2 khoan"}),
            ("/days/reopen", "tien_reopen_day", {"account_id": 7, "business_date": "2026-10-05", "track": "coverage", "reason": "muon"}),
        ]
        for path, function, fields in cases:
            body = {"idempotency_key": "k-1", **fields}
            runner, _ = self.call("POST", tien.PREFIX + path, body)
            self.assertEqual(runner.calls[-1][:2], (function, body), path)

    def test_bad_bodies_rejected_before_db(self):
        base = {"idempotency_key": "k-1", "account_id": 7, "business_date": "2026-10-05", "expected_version": 4}
        line = {"target_kind": "bank_fee", "target_ref": {}, "amount_minor": "5000"}
        cases = [
            ("/days/sign-coverage", {**base, "actor": "khac"}),
            ("/days/sign-coverage", {k: v for k, v in base.items() if k != "idempotency_key"}),
            ("/days/sign-coverage", {**base, "idempotency_key": "x" * 129}),
            ("/days/sign-coverage", {**base, "account_id": True}),
            ("/days/sign-coverage", {**base, "account_id": 0}),
            ("/days/sign-coverage", {**base, "business_date": "05/10/2026"}),
            ("/days/sign-coverage", {**base, "expected_version": -1}),
            ("/days/reopen", {**{k: v for k, v in base.items() if k != "expected_version"}, "track": "ngay"}),
            ("/days/sign-business", {k: v for k, v in base.items() if k != "expected_version"} | {"note": "a\x01b"}),
            ("/imports/commit", {"idempotency_key": "k", "import_id": 9, "expected_preview_hash": "ABC"}),
            ("/imports/commit", {"idempotency_key": "k", "import_id": 9, "expected_preview_hash": HASH,
                                 "suspect_decisions": [{"line_no": 1, "decision": "duplicate_of"}]}),
            ("/imports/commit", {"idempotency_key": "k", "import_id": 9, "expected_preview_hash": HASH,
                                 "suspect_decisions": [{"line_no": 1, "decision": "new", "transaction_id": 4}]}),
            ("/imports/commit", {"idempotency_key": "k", "import_id": 9, "expected_preview_hash": HASH, "keep_existing": [{"reason": "x"}]}),
            ("/allocations", {"idempotency_key": "k", "transaction_id": 4, "expected_version": 0, "lines": [{**line, "target_kind": "luong"}]}),
            ("/allocations", {"idempotency_key": "k", "transaction_id": 4, "expected_version": 0, "lines": [{**line, "amount_minor": "12.5"}]}),
            ("/allocations", {"idempotency_key": "k", "transaction_id": 4, "expected_version": 0, "lines": [{**line, "amount_minor": "0"}]}),
            ("/allocations", {"idempotency_key": "k", "transaction_id": 4, "expected_version": 0, "lines": [{**line, "extra": 1}]}),
            ("/allocations", {"idempotency_key": "k", "transaction_id": 4, "expected_version": 0, "lines": [line] * 51}),
            ("/balance-evidence", {"idempotency_key": "k", "account_id": 7, "as_of_date": "2026-10-05", "amount_minor": 25000,
                                   "source": "bank_pdf"}),
            ("/balance-evidence", {"idempotency_key": "k", "account_id": 7, "as_of_date": "2026-10-05", "amount_minor": "25000",
                                   "source": "zalo"}),
        ]
        for path, body in cases:
            runner = FakePsql({"tien_my_access": grants("tien_review")})
            with self.assertRaises(api.ApiError) as caught:
                api.handle("POST", tien.PREFIX + path, self.headers, json.dumps(body).encode(), runner, port=8780, host="127.0.0.1",
                           actor=ACTOR)
            self.assertEqual(caught.exception.code, "INVALID_REQUEST", body)
            self.assertEqual(runner.calls, [], f"thân lệnh sai không được tới DB: {body}")
        self.rejects("POST", tien.PREFIX + "/allocations", None, "INVALID_REQUEST", raw=b'{"idempotency_key": "k", "transaction_id": 1.5}')
        self.rejects("POST", tien.PREFIX + "/allocations", None, "INVALID_REQUEST", raw=b'{"idempotency_key": "k", "idempotency_key": "j"}')
        self.rejects("POST", tien.PREFIX + "/khong-co", {"idempotency_key": "k"}, "NOT_FOUND")

    def test_preview_reads_file_and_sends_original(self):
        data = demo_csv()
        body = {"idempotency_key": "k-p", "account_id": 7, "template": "demo-csv@1", "file_name": "C:\\fakepath\\sao-ke-gia.csv",
                "content_base64": base64.b64encode(data).decode()}
        runner, _ = self.call("POST", tien.PREVIEW_PATH, body)
        self.assertEqual([c[0] for c in runner.calls], ["tien_get_account_card", "tien_preview_import"])
        sent = runner.calls[-1][1]
        self.assertEqual({k: sent[k] for k in ("idempotency_key", "account_id", "file_sha256", "template", "period_from", "period_to",
                                               "last_day_complete", "opening_minor", "closing_minor")},
                         {"idempotency_key": "k-p", "account_id": 7, "file_sha256": hashlib.sha256(data).hexdigest(),
                          "template": "demo-csv@1", "period_from": "2026-10-01", "period_to": "2026-10-03", "last_day_complete": False,
                          "opening_minor": "1000000", "closing_minor": "1030000"})
        self.assertEqual(sent["file"], {"name": "sao-ke-gia.csv", "media_type": "text/csv",
                                        "content_base64": base64.b64encode(data).decode()})
        self.assertEqual([(ln["line_no"], ln["direction"], ln["amount_minor"], ln["currency"]) for ln in sent["lines"]],
                         [(1, "in", "50000", "VND"), (2, "out", "20000", "VND")])

    def test_preview_rejections(self):
        good = {"idempotency_key": "k-p", "account_id": 7, "template": "demo-csv@1", "file_name": "sao-ke.csv",
                "content_base64": base64.b64encode(demo_csv()).decode()}
        self.rejects("POST", tien.PREVIEW_PATH, {**good, "template": "vcb-xlsx@1"}, "TEMPLATE_UNKNOWN")
        with mock.patch.dict(os.environ, {"WEBDEBIT_TIEN_DEMO": "0"}):
            self.rejects("POST", tien.PREVIEW_PATH, good, "TEMPLATE_UNKNOWN")
        self.rejects("POST", tien.PREVIEW_PATH, {**good, "content_base64": "khong phai base64"}, "INVALID_REQUEST")
        self.rejects("POST", tien.PREVIEW_PATH, {**good, "content_base64": ""}, "INVALID_REQUEST")
        self.rejects("POST", tien.PREVIEW_PATH, {**good, "file_name": "a\x00b.csv"}, "INVALID_REQUEST")
        big = base64.b64encode(b"x" * (4 * 1024 * 1024 + 1)).decode()
        self.assertEqual(self.rejects("POST", tien.PREVIEW_PATH, {**good, "content_base64": big}, "FILE_TOO_LARGE").status, 413)
        broken = base64.b64encode(demo_csv().replace(b"#period,2026-10-01,2026-10-03,partial\n", b"")).decode()
        error = self.rejects("POST", tien.PREVIEW_PATH, {**good, "content_base64": broken}, "IMPORT_PARSE_ERROR")
        self.assertEqual(error.message, "Thiếu dòng #period (kỳ của sao kê).")
        bad_day = base64.b64encode(demo_csv("2026-13-01,,CK,,1,\n")).decode()
        self.assertEqual(self.rejects("POST", tien.PREVIEW_PATH, {**good, "content_base64": bad_day}, "IMPORT_PARSE_ERROR").extra,
                         {"line": 5})

    def test_body_limit(self):
        self.assertEqual(api.body_limit(tien.PREVIEW_PATH), tien.MAX_PREVIEW_BODY)
        self.assertEqual(api.body_limit(tien.PREFIX + "/imports/commit"), tables.MAX_BODY)
        encoded = base64.b64encode(b"x" * (4 * 1024 * 1024)).decode()
        raw = json.dumps({"idempotency_key": "k", "account_id": 7, "template": "demo-csv@1", "file_name": "a.csv",
                          "content_base64": encoded}).encode()
        self.assertLess(len(raw), tien.MAX_PREVIEW_BODY)

    def test_sql_matches_migration_functions(self):
        source = "".join(m.read_text(encoding="utf-8") for m in MIGRATIONS)
        granted = {name for block in re.findall(r"GRANT EXECUTE ON FUNCTION (.*?) TO tien_app", source, re.S)
                   for name in re.findall(r"tien\.(\w+)\(", block)}
        used = {re.search(r"SELECT tien\.(\w+)\(", tables.SQL[key]).group(1) for key in tables.SQL if key.startswith("tien_")}
        self.assertLessEqual(used, granted, "API chỉ gọi hàm migration cấp cho tien_app")
        self.assertEqual(granted - used, {"create_legal_entity", "create_account", "set_opening", "grant_role", "revoke_role",
                                          "get_account_summary"}, "lát 2 chưa có màn quản trị; tóm tắt đọc qua thẻ tài khoản")
        for key in (k for k in tables.SQL if k.startswith("tien_")):
            self.assertTrue(tables.SQL[key].startswith(tables.TIEN_ACTOR), f"{key} phải đặt tien.actor và tien.actor_kind")
        codes = set(re.findall(r"RAISE EXCEPTION '([A-Z_]+)'", source)) - {"TIEN_LAT1_REQUIRED"}
        for code in codes:
            self.assertIn(code, tables.ERRORS, f"mã lỗi {code} của tien phải có câu thông báo")
        for code in ("TIEN_OFF", "TEMPLATE_UNKNOWN", "IMPORT_PARSE_ERROR", "FILE_TOO_LARGE"):
            self.assertIn(code, tables.ERRORS)

    def test_statement_file_download(self):
        data = demo_csv()
        found = {"id": 3, "account_id": 7, "file_name": "sao kê gia.csv", "media_type": "text/csv",
                 "file_sha256": hashlib.sha256(data).hexdigest(), "content_base64": base64.b64encode(data).decode()}
        errors = io.StringIO()
        with mock.patch.object(sys, "stderr", errors):
            kind, name, body = tien.binary("/api/v7/tien/files/3", "", FakePsql({"tien_get_statement_file": found}), ACTOR)
        self.assertEqual((kind, name, body), ("text/csv", "sao kê gia.csv", data))
        self.assertIn("tải file gốc 3 (tài khoản 7)", errors.getvalue())
        self.assertNotIn("CK GIA", errors.getvalue())
        with self.assertRaises(api.ApiError) as caught:
            tien.binary("/api/v7/tien/files/3", "", FakePsql({"tien_get_statement_file": {**found, "file_sha256": HASH}}), ACTOR)
        self.assertEqual(caught.exception.status, 503)
        self.assertEqual(tien.disposition("sao kê gia.csv"),
                         "attachment; filename=\"sao_k__gia.csv\"; filename*=UTF-8''sao%20k%C3%AA%20gia.csv")
        self.assertTrue(tien.binary_route("/api/v7/tien/files/3") and tien.binary_route("/api/v7/tien/accounts/7/export.xlsx"))
        self.assertFalse(tien.binary_route("/api/v7/tien/files/x") or tien.binary_route("/api/v7/tien/accounts/7/export.csv"))

    def test_export_workbook(self):
        rows = export_sample()
        errors = io.StringIO()
        with mock.patch.object(sys, "stderr", errors):
            kind, name, body = tien.binary("/api/v7/tien/accounts/7/export.xlsx", "from=2026-10-01&to=2026-10-31",
                                           FakePsql({"tien_export_rows": rows}), ACTOR)
        self.assertEqual((kind, name), (tien.XLSX_TYPE, "so-tien-NHGIA-1234-2026-10-01-2026-10-31.xlsx"))
        book = v7_xlsx_writer.read_workbook(body)
        self.assertEqual(list(book), ["Giao dịch", "Phân bổ", "Ngày"])
        self.assertIn("xuất Excel tài khoản 7 2026-10-01..2026-10-31", errors.getvalue())
        with self.assertRaises(api.ApiError) as caught:
            tien.binary("/api/v7/tien/accounts/7/export.xlsx", "from=2026-01-01&to=2027-01-02", FakePsql(), ACTOR)
        self.assertEqual(caught.exception.code, "INVALID_REQUEST")
        usd = {**rows, "account": {**rows["account"], "currency": "USD"}}
        with mock.patch.object(sys, "stderr", io.StringIO()), self.assertRaises(api.ApiError) as caught:
            tien.binary("/api/v7/tien/accounts/7/export.xlsx", "from=2026-10-01&to=2026-10-31", FakePsql({"tien_export_rows": usd}), ACTOR)
        self.assertEqual(caught.exception.code, "EXPORT_FAILED")


def export_sample() -> dict:
    return {"account": {"id": 7, "bank_code": "NHGIA", "account_last4": "1234", "currency": "VND", "legal_entity_code": "PN-GIA",
                        "legal_entity_name": "Phap nhan gia"},
            "from": "2026-10-01", "to": "2026-10-31", "actor": ACTOR, "generated_at": "2026-11-25T10:00:00.5+00:00",
            "opening_as_of": "2026-10-01", "opening_minor": "1000000", "closing_minor": "1030000",
            "transactions": [{"id": 41, "booking_date": "2026-10-01", "value_date": None, "bank_ref": "FT1", "description": "=CK GIA MOT",
                              "direction": "in", "amount_minor": "50000", "status": "applied", "allocated_minor": "50000",
                              "unallocated_minor": "0", "imports": [9]},
                             {"id": 42, "booking_date": "2026-10-02", "value_date": "2026-10-02", "bank_ref": None,
                              "description": None, "direction": "out", "amount_minor": "20000", "status": "unmatched",
                              "allocated_minor": "0", "unallocated_minor": "20000", "imports": [9, 10]}],
            "allocations": [{"transaction_id": 41, "booking_date": "2026-10-01", "direction": "in", "target_kind": "customer_unapplied",
                             "target_ref": {"customer_id": "12"}, "amount_minor": "50000", "note": None}],
            "days": [{"date": "2026-10-01", "coverage": "full", "coverage_status": "signed", "business_status": "open"}]}


class ReadOnlyPeerTest(unittest.TestCase):
    """Qua socket thật: bot chỉ-đọc (uid trong WEBDEBIT_READ_ONLY_PEER_UIDS) đọc được sổ nợ nhưng không đọc được sổ tiền (F1 mục 2)."""

    AUTHORITY = "congno.example.test:8443"

    def test_read_only_peer_blocked_on_tien_get(self):
        runner = FakePsql({"tien_my_access": grants("tien_review"), "tien_list_accounts": {"accounts": []}})
        login = "bot@example.test"

        class PeerHandler(api.Handler):
            behind_tailscale_serve = True
            serve_hosts = (self.AUTHORITY,)
            allowed_logins = frozenset({login})
            admin_logins = frozenset({login})
            read_only_uids = frozenset({1001})
            default_actor = None
            dev_actor_mode = False
        PeerHandler.runner = runner
        server = api.ThreadingHTTPServer(("127.0.0.1", 0), PeerHandler)
        PeerHandler.port = server.server_port
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        saved = tien.CONFIG
        tien.CONFIG = tien.Config("on", None)
        self.addCleanup(setattr, tien, "CONFIG", saved)

        def get(path, uid):
            with mock.patch.object(api.v7_access, "STORE", None), mock.patch.object(identity, "loopback_peer_uid", return_value=uid), \
                    mock.patch.object(sys, "stderr", io.StringIO()):
                conn = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
                conn.request("GET", path, headers={"Host": self.AUTHORITY, "Tailscale-User-Login": login})
                response = conn.getresponse()
                data = json.loads(response.read())
                conn.close()
            return response.status, data

        self.assertEqual(get("/api/v7/tien/accounts", 1001), (403, {"error": "READ_ONLY_PEER"}))
        self.assertEqual(get("/api/v7/tien/files/3", 1001), (403, {"error": "READ_ONLY_PEER"}))
        self.assertEqual(runner.calls, [], "bot chỉ-đọc bị chặn trước mọi lần gọi DB")
        self.assertEqual(get("/api/v7/tien/accounts", 0)[0], 200)


class DateDefaultsTest(unittest.TestCase):
    def test_range_defaults_to_vn_today(self):
        today = datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")).date()
        self.assertEqual(tien._range({}, default_days=30, max_days=366), ((today - timedelta(days=30)).isoformat(), today.isoformat()))
        self.assertEqual(tien._range({"from": "2026-10-01", "to": "2026-10-31"}, default_days=30, max_days=366),
                         ("2026-10-01", "2026-10-31"))
        self.assertIsInstance(date.fromisoformat(tien._range({"to": "2026-10-31"}, default_days=5, max_days=10)[0]), date)


if __name__ == "__main__":
    unittest.main()
