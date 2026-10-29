"""PS fee split: CONT_MASTER reader, per-ledger queue and the split API. Fake data only."""
import hashlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "web"))
sys.path.insert(0, str(ROOT / "tools"))
import v7_ledger_api as api  # noqa: E402
import v7_ps_snapshot as reader  # noqa: E402
from v7_ps_queue import load_ps_snapshot, project_ps  # noqa: E402

HEADER = ["Khóa", "Số cont", "Ngày đóng", "Tháng bill", "Chủ hàng", "Mặt hàng", "Kho", "Cảng đến", "Hãng tàu",
          "Booking", "Tab nguồn", "Dòng nguồn", "Giá+phí ghi trên booking", "Giá WeChat", "PS: số dòng khớp",
          "PS Neo", "PS Điện", "PS Ghép", "PS Health+KĐ", "PS cờ Health", "PS cờ KĐ", "PS Khác", "PS nguồn",
          "Đơn giá", "Bảo hiểm", "Số dòng nhập", "Trạng thái", "Lỗi", "Bill đã chốt"]
COL = {name: i for i, name in enumerate(HEADER)}


def cells(**values):
    raw = [""] * len(HEADER)
    raw[COL["Số cont"]], raw[COL["Ngày đóng"]], raw[COL["Chủ hàng"]] = "FAKEU0000001", "03/10/2026", "CHU HANG A 101"
    raw[COL["Khóa"]], raw[COL["PS: số dòng khớp"]] = "FAKEU0000001|2026-10-03", 1
    for name, value in values.items():
        raw[COL[name]] = value
    return raw


def ps_row(container="FAKEU0000001", date="2026-10-03", owner="CHU HANG A 101", booking="", **fees):
    base = {"neo": None, "dien": None, "ghep": None, "khac": None, "bao_hiem": None}
    return {"key": f"{container}|{date}", "source_row": 3, "container": container, "date": date, "bill_month": "10/2026",
            "owner": owner, "booking": booking, "ps_match_count": 1, "fees": base | fees, "combined_vnd": None,
            "health": False, "kd": False, "ps_source": "CHI PHI PS THANG 10 · dòng 4", "source_error": None, "problems": []}


TYPES = [{"id": 1, "name": "Khác", "system_key": "other", "active": True},
         {"id": 2, "name": "Giảm trừ", "system_key": "discount", "active": True},
         {"id": 3, "name": "Phụ phí ban đầu", "system_key": "initial", "active": True},
         {"id": 4, "name": "Neo", "system_key": None, "active": True},
         {"id": 5, "name": "Điện", "system_key": None, "active": True},
         {"id": 6, "name": "Ghép", "system_key": None, "active": True},
         {"id": 7, "name": "Bảo hiểm", "system_key": None, "active": True},
         {"id": 8, "name": "Health cert", "system_key": None, "active": True},
         {"id": 9, "name": "Kiểm định", "system_key": None, "active": True}]
CUSTOMERS = [{"id": 7, "name": "KHACH A"}, {"id": 8, "name": "KHACH B"}]
ALIASES = {"CHU HANG A 101": "KHACH A", "CHU HANG B": "KHACH B"}


def line(line_id, type_id, amount, note=None):
    return {"id": line_id, "fee_type_id": type_id, "amount_vnd": str(amount), "note": note}


def trip(trip_id=11, container="FAKEU0000001", date="2026-10-03", lines=(), month="2026-10-01", **extra):
    return {"id": trip_id, "container": container, "event_date": date, "unit_price_vnd": "1000000",
            "other_fee_vnd": None, "status": "confirmed", "month": month, "deleted": False,
            "booking": "", "fee_lines": list(lines), **extra}


def ledger(trips=(), legacy=(), customer_id=7):
    return {"customer_id": customer_id, "version": 3, "status": "active", "today_month": "2026-10-01",
            "month_locks": [{"month": "2026-10-01", "locked": False}, {"month": "2026-09-01", "locked": True}],
            "trips": list(trips), "legacy_rows": list(legacy)}


def project(rows, book):
    snapshot = {"sha256": "a" * 64, "row_count": len(rows), "rows": rows, "customer_aliases": ALIASES}
    return project_ps(snapshot, book, CUSTOMERS, TYPES)


class ReaderTest(unittest.TestCase):
    def test_amounts_dates_flags_and_problems(self):
        values = [HEADER,
                  cells(**{"PS Neo": "1,500,000", "PS Điện": 500000}),
                  cells(**{"PS Ghép": "1", "Số cont": "FAKEU0000002"}),
                  cells(**{"PS Khác": 315789.5, "Ngày đóng": 46298}),
                  cells(**{"PS Neo": 0, "PS cờ Health": "CÓ", "Lỗi": "B4 PS trùng dòng"}),
                  cells(**{"PS Neo": "", "PS cờ Health": False}),
                  cells(**{"Bảo hiểm": 200000, "PS Health+KĐ": "3,000,000"})]
        rows = reader.parse_rows(values)
        self.assertEqual(len(rows), 5)   # the row without money or marks is left out
        self.assertEqual(rows[0]["fees"], {"neo": "1500000", "dien": "500000", "ghep": None, "khac": None, "bao_hiem": None})
        self.assertEqual((rows[0]["date"], rows[0]["source_row"]), ("2026-10-03", 3))
        self.assertEqual(rows[1]["problems"], [{"field": "ghep", "code": "PS_TYPO", "value": "1"}])
        self.assertEqual(rows[2]["problems"][0]["code"], "PS_BAD_AMOUNT")
        self.assertEqual(rows[2]["date"], "2026-10-03")
        self.assertEqual((rows[3]["health"], rows[3]["fees"]["neo"], rows[3]["source_error"]), (True, None, "B4 PS trùng dòng"))
        self.assertEqual((rows[4]["fees"]["bao_hiem"], rows[4]["combined_vnd"]), ("200000", "3000000"))

    def test_header_by_name_and_missing_column(self):
        moved = HEADER[::-1]
        raw = cells(**{"PS Neo": 1500000})[::-1]
        self.assertEqual(reader.parse_rows([moved, raw])[0]["fees"]["neo"], "1500000")
        with self.assertRaises(ValueError):
            reader.parse_rows([HEADER[:-2], cells()])

    def test_fetch_reads_one_batch_and_hash_is_stable(self):
        payload = {"valueRanges": [{"values": [HEADER, cells(**{"PS Neo": 1500000})]},
                                   {"values": [["Chủ hàng từ BOOKING_DATA", "", "", "", "", "Khách chuẩn trên hao (bạn điền)"],
                                               ["CHU HANG A 101", "", "", "", "", "KHACH A"]]}]}
        urls = []

        def opener(request, timeout):
            urls.append(request.full_url)
            return io.BytesIO(json.dumps(payload).encode())
        with patch.object(reader.runner, "load_credentials", return_value={}):
            first = reader.build("F" * 30, "unused", token_exchange=lambda _: "token", opener=opener)
            second = reader.build("F" * 30, "unused", token_exchange=lambda _: "token", opener=opener)
        self.assertEqual(len(urls), 2)
        self.assertIn("UNFORMATTED_VALUE", urls[0])
        self.assertEqual(first["sha256"], second["sha256"])
        self.assertEqual(first["customer_aliases"], {"CHU HANG A 101": "KHACH A"})
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "ps.json"
            reader.write(first, path)
            self.assertEqual(load_ps_snapshot(path)["sha256"], first["sha256"])
            for content in ('{"rows":[],"row_count":0}', "not json",
                            '{"rows":[],"row_count":0,"sha256":"' + "a" * 64 + '"}'):
                path.write_text(content, encoding="utf-8")
                with self.subTest(content=content), self.assertRaises(ValueError):
                    load_ps_snapshot(path)


class QueueTest(unittest.TestCase):
    def test_initial_fee_splits_into_types_keeping_total(self):
        result = project([ps_row(neo="1500000", dien="500000")], ledger([trip(lines=[line(91, 3, 2000000)])]))
        self.assertEqual(result["ready_count"], 1)
        item = result["ready"][0]
        self.assertEqual((item["target_kind"], item["target_id"], item["ps_total"], item["web_total"]),
                         ("trip", 11, "2000000", "2000000"))
        self.assertEqual([(x["fee_type_id"], x["amount_vnd"]) for x in item["after"]], [(4, "1500000"), (5, "500000")])
        self.assertEqual([x["id"] for x in item["before"]], [91])

    def test_kept_typed_line_and_done(self):
        book = ledger([trip(lines=[line(91, 4, 1500000, "giữ"), line(92, 1, 500000)])])
        item = project([ps_row(neo="1500000", dien="500000")], book)["ready"][0]
        self.assertEqual(item["after"], [{"fee_type_id": 4, "amount_vnd": "1500000", "note": "giữ"},
                                         {"fee_type_id": 5, "amount_vnd": "500000", "note": None}])
        done = ledger([trip(lines=[line(91, 4, 1500000), line(93, 5, 500000)])])
        result = project([ps_row(neo="1500000", dien="500000")], done)
        self.assertEqual((result["ready_count"], result["review_count"]), (0, 0))
        khac_only = ledger([trip(lines=[line(91, 1, 300000)])])
        self.assertEqual(project([ps_row(khac="300000")], khac_only)["ready_count"], 0)

    def test_review_statuses(self):
        cases = [
            (ps_row(neo="1500000"), ledger([trip(lines=[line(91, 1, 1000000)])]), "TOTAL_DIFF", "Web 1.000.000 đ · PS 1.500.000 đ"),
            (ps_row(neo="1500000"), ledger([trip()]), "WEB_NO_FEE", "PS 1.500.000 đ · web chưa có phụ phí"),
            (ps_row(neo="1500000"), ledger([trip(lines=[line(91, 6, 1500000)])]), "TYPED_CONFLICT", "Web đã phân loại khác PS"),
            (ps_row(neo="1500000", date="2026-09-20"),
             ledger([trip(date="2026-09-20", month="2026-09-01", lines=[line(91, 1, 1500000)])]), "MONTH_LOCKED", "Tháng 09/2026 đang khóa"),
            (ps_row(neo="1500000") | {"problems": [{"field": "ghep", "code": "PS_TYPO", "value": "1"}]},
             ledger([trip(lines=[line(91, 1, 1500000)])]), "PS_TYPO", "Ghép = 1 trên PS, có thể gõ sai"),
            (ps_row(neo="1500000") | {"combined_vnd": "3000000"}, ledger([trip()]), "PS_COMBINED",
             "PS gộp Health+KĐ 3.000.000 đ, cần tách tay"),
            (ps_row(neo="1500000") | {"source_error": "B4 PS trùng dòng", "ps_match_count": 2}, ledger([trip()]),
             "PS_SOURCE_ERROR", "Bộ lập bill báo lỗi: B4 PS trùng dòng"),
            (ps_row(neo="1500000"), ledger([trip(), trip(12)]), "AMBIGUOUS", "Cont khớp nhiều chuyến hoặc nhiều dòng PS cùng một chuyến"),
        ]
        for row, book, status, text in cases:
            with self.subTest(status=status):
                result = project([row], book)
                self.assertEqual(result["ready_count"], 0)
                self.assertEqual([(r["status"], r["message"]) for r in result["review"]], [(status, text)])

    def test_matching_rules(self):
        lines = [line(91, 1, 1500000)]
        near = ledger([trip(date="2026-10-05", lines=lines)])
        self.assertEqual(project([ps_row(neo="1500000")], near)["ready_count"], 1)
        far = ledger([trip(date="2026-10-08", lines=lines)])
        self.assertEqual(project([ps_row(neo="1500000")], far)["ready_count"] + project([ps_row(neo="1500000")], far)["review_count"], 0)
        other_booking = ledger([trip(lines=lines, booking="BKG-2")])
        self.assertEqual(project([ps_row(neo="1500000", booking="BKG-1")], other_booking)["ready_count"], 0)
        two_rows = [ps_row(neo="1500000"), ps_row(neo="1500000") | {"source_row": 9}]
        self.assertEqual([r["status"] for r in project(two_rows, ledger([trip(lines=lines)]))["review"]], ["AMBIGUOUS"] * 2)
        self.assertEqual(project([ps_row(neo="1500000", owner="CHU HANG B")], ledger([trip(lines=lines)]))["ready_count"], 0)
        self.assertEqual(project([ps_row(neo="1500000", owner="CHU HANG B")], ledger([trip(lines=lines)], customer_id=8))["ready_count"], 1)
        legacy = {"id": 21, "kind": "trip", "month": "2026-10-01", "fee_lines": lines, "current": {
            "container": "FAKEU0000001", "event_date": "2026-10-03", "unit_price_vnd": "100", "counted_vnd": "999",
            "month": "2026-10-01", "deleted": False}}
        item = project([ps_row(neo="1500000")], ledger(legacy=[legacy]))["ready"][0]
        self.assertEqual((item["target_kind"], item["target_id"]), ("legacy", 21))

    def test_health_mark_only_reminds(self):
        row = ps_row(neo="1500000") | {"health": True}
        result = project([row], ledger([trip(lines=[line(91, 1, 1500000)])]))
        self.assertEqual(result["ready_count"], 1)
        self.assertEqual([r["status"] for r in result["review"]], ["NEED_HEALTH"])
        done = project([row], ledger([trip(lines=[line(91, 4, 1500000), line(92, 8, 500000)])]))
        self.assertEqual([r["status"] for r in done["review"]], ["TOTAL_DIFF"])
        flag_only = ps_row() | {"kd": True}
        self.assertEqual([r["status"] for r in project([flag_only], ledger([trip()]))["review"]], ["NEED_KD"])

    def test_missing_fee_type(self):
        types = [t for t in TYPES if t["name"] != "Điện"]
        snapshot = {"sha256": "a" * 64, "row_count": 1, "rows": [ps_row(dien="500000")], "customer_aliases": ALIASES}
        result = project_ps(snapshot, ledger([trip(lines=[line(91, 1, 500000)])]), CUSTOMERS, types)
        self.assertEqual([(r["status"], r["message"]) for r in result["review"]],
                         [("FEE_TYPE_MISSING", "Danh mục chưa có loại Điện")])


class Runner:
    def __init__(self, fail_at=None):
        self.calls, self.version, self.fail_at, self.writes = [], 3, fail_at, 0

    def run(self, function, payload, actor):
        self.calls.append((function, payload, actor))
        if function == "get_ledger":
            return {"customer_id": 7, "version": self.version, "status": "active"}
        self.writes += 1
        if self.writes == self.fail_at:
            raise api.ApiError(409, "FEE_LINES_CHANGED", "Phụ phí chuyến này vừa đổi.")
        self.version += 1
        return {"version": self.version}


READY = {"snapshot_sha256": "a" * 64, "ready": [
    {"key": "FAKEU0000001|2026-10-03", "ps_source": "PS · dòng 4", "target_kind": "trip", "target_id": 11,
     "before": [line(91, 3, 2000000)], "after": [{"fee_type_id": 4, "amount_vnd": "1500000", "note": None},
                                                 {"fee_type_id": 5, "amount_vnd": "500000", "note": None}]},
    {"key": "FAKEU0000002|2026-10-04", "ps_source": "PS · dòng 5", "target_kind": "legacy", "target_id": 21,
     "before": [line(92, 1, 700000)], "after": [{"fee_type_id": 4, "amount_vnd": "700000", "note": None}]}]}
BODY = {"customer_id": 7, "expected_version": 3, "snapshot_sha256": "a" * 64, "idempotency_key": "fake-split"}


class ApproveTest(unittest.TestCase):
    def approve(self, runner, body=BODY, projection=READY):
        with patch.object(api, "ps_projection", return_value=projection):
            return api.approve_ps_fees(json.dumps(body).encode(), runner, "fake-actor")

    def test_each_target_is_one_rewrite(self):
        runner = Runner()
        status, result = self.approve(runner)
        self.assertEqual((status, result["written"], result["complete"], result["version"]), (200, 2, True, 5))
        writes = [p for f, p, _ in runner.calls if f == "rewrite_trip_fees"]
        self.assertEqual([(p["target"], p["expected_line_ids"], p["expected_version"]) for p in writes],
                         [({"trip_id": 11}, [91], 3), ({"legacy_row_id": 21}, [92], 4)])
        self.assertEqual(writes[0]["lines"][0], {"fee_type_id": 4, "amount_vnd": "1500000", "note": None})
        self.assertEqual(writes[0]["source"], {"kind": "ps", "key": "FAKEU0000001|2026-10-03",
                                               "ps_source": "PS · dòng 4", "snapshot_sha256": "a" * 64})
        self.assertEqual(writes[0]["idempotency_key"], hashlib.sha256(f"fake-split:{'a' * 64}:trip:11".encode()).hexdigest())
        self.assertEqual({f for f, _, _ in runner.calls}, {"get_ledger", "rewrite_trip_fees"})

    def test_stale_or_bad_request_writes_nothing(self):
        for body in (BODY | {"snapshot_sha256": "b" * 64}, BODY | {"expected_version": 2}, BODY | {"extra": 1}):
            runner = Runner()
            with self.subTest(body=body), self.assertRaises(api.ApiError):
                self.approve(runner, body)
            self.assertEqual([c for c in runner.calls if c[0] != "get_ledger"], [])

    def test_failure_after_a_write_reports_partial_batch(self):
        status, result = self.approve(Runner(fail_at=2))
        self.assertEqual((status, result["written"], result["complete"], result["error"]), (200, 1, False, "FEE_LINES_CHANGED"))
        with self.assertRaises(api.ApiError):
            self.approve(Runner(fail_at=1))

    def test_ledger_read_falls_back_when_ps_snapshot_is_missing(self):
        with patch.object(api, "PS_SNAPSHOT_PATH", str(ROOT / "missing-ps.json")), \
                patch.object(api, "sheet_projection", return_value={"items": []}), \
                patch.object(api, "price_projection", return_value={"ready": []}):
            status, result = api.handle("GET", "/api/v7/ledger?customer=7", {"host": "127.0.0.1:8780"}, b"",
                                        Runner(), port=8780, host="127.0.0.1", actor="fake-actor")
        self.assertEqual((status, result["ps_fees"]["unavailable"], result["ps_fees"]["ready"]), (200, True, []))

    def test_rewrite_sql_casts_json_arguments(self):
        sql = api.SQL["rewrite_trip_fees"]
        for field in ("target", "expected_line_ids", "lines", "source"):
            self.assertIn(f"(j->'{field}')::jsonb", sql)
        self.assertNotIn("/api/v7/trips/fees/rewrite", api.ROUTES)


if __name__ == "__main__":
    unittest.main()
