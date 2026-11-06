"""Máy tự đối soát (MAY-DOI-SOAT-01): cả lượt từ bản tải giả tới reconcile.json, DB giả. Không cần captures, Docker hay DB thật."""

import io
import json
import sys
import tempfile
import unittest
from collections import Counter
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tests"))
import v7_reconcile_auto as job  # noqa: E402
from test_v7_load_real_copy import FAKE_AMOUNT, FAKE_NAME, csv_file, fixture  # noqa: E402
from v7_api_validate import ApiError  # noqa: E402
from v7_inbox import AUTO_ACTOR  # noqa: E402

PAID = 1000
TONG_TITLES = {"C": "STT", "D": "LOAI HANG", "E": "TÊN KHÁCH HÀNG", "F": "SỐ CÒN PHẢI THU THÁNG CHUYỂN SANG",
               "G": "CÔNG NỢ PHÁT SINH TRONG THÁNG 9.2026", "I": "SỐ CÒN PHẢI THU CUỐI THÁNG", "K": "STT", "L": "LOAI HANG",
               "M": "TÊN KHÁCH HÀNG", "N": "SỐ CÒN PHẢI THU THÁNG CHUYỂN SANG", "O": "CÔNG NỢ PHÁT SINH TRONG THÁNG 10.2026",
               "Q": "SỐ CÒN PHẢI THU CUỐI THÁNG", "R": "TỔNG SL CONT"}


class Db:
    """Một sổ khớp bản tải giả: chuyến FAKE-CONT-XY đã có giá; phiếu thu ghi xong thì tổng giảm."""

    def __init__(self, total=FAKE_AMOUNT, unit_price=FAKE_AMOUNT, fail=None, moved_trips=(), adjustments=()):
        self.total, self.unit_price, self.fail, self.version = total, unit_price, fail, 4
        self.receipts, self.writes = [], []
        self.moved_trips, self.adjustments = list(moved_trips), list(adjustments)

    def ledger(self):
        return {"customer_id": 1, "status": "active", "version": self.version, "total_outstanding_vnd": str(self.total),
                "months": [{"month": "2026-10-01", "outstanding_vnd": str(self.total)}], "today_month": "2026-11-01",
                "month_locks": [], "legacy_rows": [], "events": [], "receipts": self.receipts, "adjustments": self.adjustments,
                "trips": [{"id": 3, "status": "confirmed", "container": "FAKE-CONT-XY", "event_date": "2026-10-03", "month": "2026-10-01",
                           "unit_price_vnd": None if self.unit_price is None else str(self.unit_price), "other_fee_vnd": None},
                          *self.moved_trips]}

    def run(self, function, payload, actor):
        if function == "list_customers":
            return {"customers": [{"id": 1, "name": FAKE_NAME, "status": "active"}]}
        if function == "get_ledger":
            return self.ledger()
        self.writes.append((function, payload, actor))
        if function == self.fail:
            raise ApiError(409, "STALE_LEDGER", "x")
        self.version += 1
        if function == "record_receipt":
            self.total -= int(payload["amount_vnd"])
            self.receipts.append({"date": payload["date"], "amount_vnd": payload["amount_vnd"], "reference": payload["reference"]})
        return {"version": self.version}


class NewBookDb(Db):
    """Web chưa có sổ của tab; lệnh tạo sổ thêm sổ đó với số dư đầu đúng như gửi. `other` là một sổ khác đã có sẵn chuyến FAKE-CONT-XY."""

    def __init__(self, other=False, fail=None):
        super().__init__(total=0, fail=fail)
        self.other = other
        self.created = None

    def run(self, function, payload, actor):
        if function == "list_customers":
            books = [{"id": 1, "name": "KHACH KHAC", "status": "active"}] if self.other else []
            return {"customers": books + ([{"id": 2, "name": self.created, "status": "active"}] if self.created else [])}
        if function == "create_book_from_sheet":
            self.writes.append((function, payload, actor))
            if function == self.fail:
                raise ApiError(409, "BOOK_EXISTS", "x")
            self.created, self.total = payload["book_name"], payload["control_total"]
            return {"customer_id": 2, "cutover_id": 9, "version": 3}
        return super().run(function, payload, actor)


class ReconcileAutoTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "source"
        self.source.mkdir()
        self.output = self.root / "var" / "reconcile.json"

    def run_job(self, db, *extra):
        printed = io.StringIO()
        with patch.object(job, "PsqlDirect", return_value=db), redirect_stdout(printed), patch("sys.stderr"):
            code = job.main(["--source-dir", str(self.source), "--xlsx", str(self.source / "source-google-export.xlsx"),
                             "--output", str(self.output), "--work-dir", str(self.root / "work"), *extra])
        return code, printed.getvalue()

    def result(self):
        return json.loads(self.output.read_text(encoding="utf-8"))

    def new_tab(self, on_tong=FAKE_AMOUNT, tong=True):
        """Tab mới: có trên Sheet, ngoài danh sách đóng băng từ mốc 20/10, TONG ghi `on_tong` ở khối mới nhất."""
        rows = {6: TONG_TITLES, 7: {"L": "SAU RIENG CANG", "M": FAKE_NAME, "O": str(FAKE_AMOUNT), "Q": str(on_tong)}}
        fixture(self.source, tong=rows if tong else None)
        csv_file(self.source, "opening_final_so_goc.csv", ["tab", "target_balance_vnd", "flags", "delta_vs_db"], [])
        csv_file(self.source, "opening_by_period_so_goc.csv", ["customer", "debt_period", "balance_vnd"], [])
        csv_file(self.source, "trips_so_goc.csv", ["tab", "block", "row", "container", "date_iso", "date_mode", "unit_price", "total_cell", "flags"], [])
        csv_file(self.source, "v7-reconcile-customer.csv", ["customer", "source_anchor_vnd"], [])
        csv_file(self.source, "v7-reconcile-period.csv", ["customer", "period", "source_vnd"], [])

    def undated_receipt_book(self):
        fixture(self.source, months=[("2026-10", "03/10/2026", FAKE_AMOUNT, FAKE_AMOUNT - PAID)], receipt=str(PAID), receipt_date="da tt")

    def test_matching_book_reports_and_writes_nothing(self):
        fixture(self.source)
        db = Db()
        code, printed = self.run_job(db, "--fix")
        self.assertEqual(code, 0)
        result = self.result()
        self.assertEqual((result["counts"], result["customers"], result["months_differ"], result["outside_tabs"]), ({"KHOP": 1}, [], [], []))
        self.assertEqual(result["matched"], {"1": str(FAKE_AMOUNT)})
        self.assertEqual((result["matched_web_vnd"], result["all_web_vnd"]), (str(FAKE_AMOUNT), str(FAKE_AMOUNT)))
        self.assertEqual(db.writes, [])
        for secret in (FAKE_NAME, str(FAKE_AMOUNT)):
            self.assertNotIn(secret, printed)
        self.assertEqual(list((self.root / "work").iterdir()), [])   # bản làm sạch đã xóa
        log = (self.output.with_name("reconcile-log.jsonl")).read_text(encoding="utf-8").splitlines()
        self.assertEqual(json.loads(log[0])["counts"], {"KHOP": 1})
        self.assertNotIn(FAKE_NAME, log[0])

    def test_report_mode_says_what_it_would_write_and_writes_nothing(self):
        self.undated_receipt_book()
        db = Db()
        self.assertEqual(self.run_job(db)[0], 0)
        result = self.result()
        self.assertEqual((result["mode"], db.writes), ("report", []))
        row = result["customers"][0]
        self.assertEqual((row["status"], row["reason"], row["difference_vnd"], row["customer_id"]), ("LECH_TONG", "WOULD_FIX", str(PAID), 1))
        self.assertEqual(row["groups"], [{"kind": "receipts_no_date", "month": "2026-10", "count": 1, "delta_vnd": str(-PAID), "chosen": True}])

    def test_fix_mode_writes_only_the_exact_fix_then_book_matches(self):
        self.undated_receipt_book()
        db = Db()
        self.assertEqual(self.run_job(db, "--fix")[0], 0)
        self.assertEqual([(w[0], w[1]["amount_vnd"], w[1]["date"], w[2]) for w in db.writes],
                         [("record_receipt", str(PAID), "2026-10-31", AUTO_ACTOR)])
        result = self.result()
        self.assertEqual(result["counts"], {"KHOP": 1})
        row = result["customers"][0]
        self.assertEqual((row["reason"], row["status"], row["web_total_vnd"], row["difference_vnd"], row["written"]),
                         ("FIXED", "KHOP", str(FAKE_AMOUNT - PAID), "0", {"receipts": 1, "prices": 0, "legacy_deleted": 0, "fee_rows": 0, "fee_undone": 0}))
        self.assertEqual(result["matched"], {"1": str(FAKE_AMOUNT - PAID)})

    def test_fix_stays_listed_for_the_rest_of_the_day(self):
        self.undated_receipt_book()
        db = Db()
        first_hour = job.now_vn().replace(hour=9, minute=5, second=0, microsecond=0)

        def run_at(moment):
            with patch.object(job, "now_vn", return_value=moment):
                self.assertEqual(self.run_job(db, "--fix")[0], 0)
            return self.result()
        first = run_at(first_hour)["customers"][0]
        self.assertEqual((first["reason"], first["fixed_at"]), ("FIXED", first_hour.isoformat(timespec="seconds")))
        result = run_at(first_hour + job.dt.timedelta(hours=1))   # lượt sau cùng ngày: không ghi thêm, vẫn còn trên danh sách
        self.assertEqual(len(db.writes), 1)
        self.assertEqual(result["counts"], {"KHOP": 1})
        self.assertEqual([(r["reason"], r["fixed_at"]) for r in result["customers"]], [("FIXED", first["fixed_at"])])
        log = self.output.with_name("reconcile-log.jsonl").read_text(encoding="utf-8").splitlines()
        self.assertEqual([json.loads(line)["fixed"] for line in log], [1, 0])
        self.assertEqual(run_at(first_hour + job.dt.timedelta(days=1))["customers"], [])   # sang ngày mới thì hết

    def test_no_exact_fix_writes_nothing(self):
        self.undated_receipt_book()
        db = Db(total=FAKE_AMOUNT + 1)   # lệch thêm 1 đồng: phiếu không đưa về đúng tổng Sheet
        self.assertEqual(self.run_job(db, "--fix")[0], 0)
        self.assertEqual(db.writes, [])
        row = self.result()["customers"][0]
        self.assertEqual((row["reason"], row["status"]), ("NO_EXACT_FIX", "LECH_TONG"))

    def test_write_error_is_reported_and_total_read_back(self):
        self.undated_receipt_book()
        db = Db(fail="record_receipt")
        self.assertEqual(self.run_job(db, "--fix")[0], 0)
        row = self.result()["customers"][0]
        self.assertEqual((row["reason"], row["error"], row["web_total_vnd"]), ("WRITE_ERROR", "STALE_LEDGER", str(FAKE_AMOUNT)))

    def test_shuffled_prices_are_named_and_nothing_is_written(self):
        self.undated_receipt_book()
        db = Db()
        group = {"kind": "receipts_no_date", "month": "2026-10", "rows": [{}], "delta_vnd": -5}
        with patch.object(job.fix, "plan", return_value=([group], 0, ["2026-10"])):
            self.assertEqual(self.run_job(db, "--fix")[0], 0)
        self.assertEqual(db.writes, [])
        row = self.result()["customers"][0]
        self.assertEqual((row["reason"], row["shuffled_months"]), ("SHEET_SHUFFLED", ["2026-10"]))

    def test_error_on_one_book_does_not_stop_the_run(self):
        self.undated_receipt_book()
        db = Db()
        with patch.object(job.fix, "plan", side_effect=KeyError("x")):
            self.assertEqual(self.run_job(db, "--fix")[0], 0)
        self.assertEqual(db.writes, [])
        row = self.result()["customers"][0]
        self.assertEqual((row["reason"], row["error"], row["status"]), ("CHECK_ERROR", "KeyError", "LECH_TONG"))

    def test_web_ahead_of_sheet_explains_the_whole_difference(self):
        fixture(self.source, months=[("2026-10", "03/10/2026", 0, 0)], missing_price=True)
        db = Db(total=500, unit_price=500)
        self.assertEqual(self.run_job(db, "--fix")[0], 0)
        self.assertEqual(db.writes, [])
        row = self.result()["customers"][0]
        self.assertEqual((row["reason"], row["web_ahead_vnd"], row["difference_vnd"]), ("WEB_AHEAD", "500", "500"))

    def test_trip_an_adjustment_took_off_the_book_does_not_block_a_right_receipt(self):
        self.undated_receipt_book()
        moved = {"id": 9, "status": "confirmed", "container": "MOVED-CONT-XY", "event_date": "2026-03-18", "month": "2026-03-01",
                 "unit_price_vnd": "181", "other_fee_vnd": None}
        db = Db(moved_trips=[moved], adjustments=[{"id": 61, "month": "2026-03-01", "amount_vnd": "-181", "note": "dời sang sổ khác"}])
        self.assertEqual(self.run_job(db, "--fix")[0], 0)
        self.assertEqual([w[0] for w in db.writes], ["record_receipt"])
        row = self.result()["customers"][0]
        self.assertEqual((row["reason"], row["status"], row["web_ahead_vnd"]), ("FIXED", "KHOP", "0"))

    def test_live_tong_reads_the_rightmost_block_of_the_real_tab(self):
        fixture(self.source, tong={6: TONG_TITLES, 7: {"E": "Chỉ khối cũ", "I": "9", "M": "KHÁCH  Mới-1", "Q": "500"},
                                   8: {"M": "Ô chữ", "Q": "chưa có"}, 9: {"M": "Trùng", "Q": "5"}, 10: {"M": "Trùng", "Q": "5"}, 11: {"M": "Số thập phân", "Q": "7.0"}})
        tong = job.live_tong(self.source / "source-google-export.xlsx")
        self.assertEqual(tong, {"month": "2026-10", "rows": {"KHACH MOI 1": 500, "O CHU": None, "TRUNG": None, "SO THAP PHAN": 7}})

    def test_live_tong_with_unknown_layout_admits_nothing(self):
        empty = {"month": None, "rows": {}}
        fixture(self.source)
        self.assertEqual(job.live_tong(self.source / "source-google-export.xlsx"), empty)   # không có tab TONG
        fixture(self.source, tong={6: {"D": "LOAI HANG", "E": "TÊN KHÁCH HÀNG", "F": "CÔNG NỢ PHÁT SINH TRONG THÁNG 10.2026"}, 7: {"E": "A", "F": "5"}})
        self.assertEqual(job.live_tong(self.source / "source-google-export.xlsx"), empty)   # không có cột cuối tháng
        fixture(self.source, tong={6: {"D": "LOAI HANG", "E": "TÊN KHÁCH HÀNG", "F": "SỐ CÒN PHẢI THU CUỐI THÁNG"}, 7: {"E": "A", "F": "5"}})
        self.assertEqual(job.live_tong(self.source / "source-google-export.xlsx"), empty)   # không biết tháng nào

    def test_new_tab_on_real_tong_gets_a_book_through_the_cutover_path_then_matches(self):
        self.new_tab()
        db = NewBookDb()
        self.assertEqual(self.run_job(db, "--fix")[0], 0)
        self.assertEqual([w[0] for w in db.writes], ["create_book_from_sheet"])
        _, payload, actor = db.writes[0]
        self.assertEqual((payload["book_name"], payload["commodity_name"], payload["book_mode"], payload["control_total"], actor),
                         (FAKE_NAME, "Sầu riêng", "CANG", FAKE_AMOUNT, AUTO_ACTOR))
        self.assertEqual(sum(row["amount_vnd"] for row in payload["openings"]), FAKE_AMOUNT)
        self.assertEqual([row["kind"] for row in payload["legacy"]], ["trip"])
        self.assertEqual(len(payload["report_sha256"]), 64)
        result = self.result()
        self.assertEqual((result["counts"], result["outside_tabs"], result["matched"]), ({"KHOP": 1}, [], {"2": str(FAKE_AMOUNT)}))
        row = result["customers"][0]
        self.assertEqual((row["reason"], row["status"], row["customer_id"], row["web_total_vnd"], row["difference_vnd"]),
                         ("BOOK_CREATED", "KHOP", 2, str(FAKE_AMOUNT), "0"))
        self.assertEqual(result["checked_at"], row["fixed_at"])
        self.assertEqual(json.loads(self.output.with_name("reconcile-log.jsonl").read_text(encoding="utf-8").splitlines()[0])["created"], 1)
        self.assertEqual(self.run_job(db, "--fix")[0], 0)   # lượt sau: sổ đã có, so như mọi khách, không ghi thêm, vẫn còn trên danh sách trong ngày
        self.assertEqual(len(db.writes), 1)
        self.assertEqual([(row["reason"], row["customer_id"]) for row in self.result()["customers"]], [("BOOK_CREATED", 2)])
        self.assertEqual(self.result()["counts"], {"KHOP": 1})

    def test_book_stays_in_the_comparison_when_its_tab_leaves_tong(self):
        self.new_tab(tong=False)
        db = NewBookDb()
        db.created, db.total = FAKE_NAME, FAKE_AMOUNT + 5
        self.assertEqual(self.run_job(db, "--fix")[0], 0)
        result = self.result()
        self.assertEqual((result["counts"], result["outside_tabs"], db.writes), ({"LECH_TONG": 1}, [], []))
        self.assertEqual(result["customers"][0]["difference_vnd"], "5")

    def test_report_mode_says_it_would_create_and_writes_nothing(self):
        self.new_tab()
        db = NewBookDb()
        self.assertEqual(self.run_job(db)[0], 0)
        self.assertEqual(db.writes, [])
        row = self.result()["customers"][0]
        self.assertEqual((row["reason"], row["status"], row["customer_id"]), ("WOULD_CREATE_BOOK", "CHI_CO_SHEET", None))

    def test_tab_whose_container_is_already_on_another_book_is_not_created(self):
        self.new_tab()
        db = NewBookDb(other=True)
        self.assertEqual(self.run_job(db, "--fix")[0], 0)
        self.assertEqual(db.writes, [])
        row = next(row for row in self.result()["customers"] if row["customer"] == FAKE_NAME)
        self.assertEqual((row["reason"], row["overlap_ids"]), ("BOOK_OVERLAP", [1]))

    def test_tab_is_not_created_when_tong_differs_or_lacks_it(self):
        for kwargs, reason in (({"on_tong": FAKE_AMOUNT + 1}, "TONG_DIFFERS"), ({"tong": False}, "NOT_ON_TONG")):
            with self.subTest(reason=reason):
                self.new_tab(**kwargs)
                db = NewBookDb()
                self.assertEqual(self.run_job(db, "--fix")[0], 0)
                result = self.result()
                self.assertEqual((db.writes, result["customers"], result["total"]), ([], [], 0))
                self.assertEqual(result["outside_tabs"], [{"customer": FAKE_NAME, "sheet_total_vnd": str(FAKE_AMOUNT), "last_month": "2026-10", "reason": reason}])

    def test_too_many_new_tabs_only_report(self):
        self.new_tab()
        db = NewBookDb()
        with patch.object(job, "NEW_BOOKS_MAX", 0):
            self.assertEqual(self.run_job(db, "--fix")[0], 0)
        self.assertEqual(db.writes, [])
        self.assertEqual(self.result()["customers"][0]["reason"], "TOO_MANY_NEW_BOOKS")

    def test_create_error_is_reported_and_the_run_goes_on(self):
        self.new_tab()
        db = NewBookDb(fail="create_book_from_sheet")
        self.assertEqual(self.run_job(db, "--fix")[0], 0)
        row = self.result()["customers"][0]
        self.assertEqual((row["reason"], row["error"], row["status"], row["customer_id"]), ("WRITE_ERROR", "BOOK_EXISTS", "CHI_CO_SHEET", None))

    def test_only_recent_tabs_with_debt_outside_the_comparison_are_named(self):
        def book(name, anchor, on_summary=False, reasons=("NOT_ON_TONG",), **months):
            checks = [{"debt_month": f"{month[1:5]}-{month[5:]}-01", "source_charge_vnd": charge, "source_receipt_vnd": 0} for month, charge in months.items()]
            return {"name": name, "anchor": anchor, "in_summary": on_summary, "reasons": Counter(reasons), "checks": checks}
        tong = {"month": "2026-10", "rows": {"LECH TONG": 400, "KHONG DOC DUOC": 200}}
        books = [book("Tab mới", 500, m202609=0, m202610=500),
                 book("Lệch TONG", 300, m202610=300),
                 book("Không đọc được", 200, reasons=("NOT_ON_TONG", "CLEAN_MONTH_TOTAL"), m202610=200),
                 book("Bản sao cũ", 400, m202508=400, m202610=0),      # tháng mới chỉ là khối trống: vẫn là tab cũ
                 book("Đã trả hết", 0, m202610=300),
                 book("Không đọc được số dư", None, m202610=300),
                 book("Đã nhận", 700, on_summary=True, reasons=(), m202610=700),
                 book("Tab trống", 900)]
        self.assertEqual([(row["customer"], row["sheet_total_vnd"], row["last_month"], row["reason"]) for row in job.outside_tabs(books, tong)],
                         [("Tab mới", "500", "2026-10", "NOT_ON_TONG"), ("Lệch TONG", "300", "2026-10", "TONG_DIFFERS"),
                          ("Không đọc được", "200", "2026-10", "TAB_UNREADABLE")])

    def test_held_customer_is_named_with_reason_and_never_touched(self):
        fixture(self.source, months=[("2026-10", "03/10/2026", FAKE_AMOUNT, FAKE_AMOUNT + 1)])   # chuỗi số dư trên Sheet không khớp
        db = Db()
        self.assertEqual(self.run_job(db, "--fix")[0], 0)
        self.assertEqual(db.writes, [])
        row = self.result()["customers"][0]
        self.assertEqual((row["status"], row["reason"]), ("CHI_CO_WEB", "HELD"))
        self.assertTrue(row["held_reasons"])

    def test_too_many_differences_only_reports(self):
        self.undated_receipt_book()
        db = Db()
        with patch.object(job, "MAX_DIFFERENT", 0):
            self.assertEqual(self.run_job(db, "--fix")[0], 0)
        self.assertEqual(db.writes, [])
        self.assertEqual(self.result()["customers"][0]["reason"], "TOO_MANY_DIFFERENT")

    def test_failed_run_keeps_last_result_and_records_the_error(self):
        fixture(self.source)
        self.assertEqual(self.run_job(Db())[0], 0)
        (self.source / "trips_so_goc.csv").unlink()
        code, printed = self.run_job(Db())
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(printed)["ok"], False)
        result = self.result()
        self.assertEqual(result["counts"], {"KHOP": 1})
        self.assertTrue(result["last_error"]["reason"])
        fixture(self.source)
        self.assertEqual(self.run_job(Db())[0], 0)
        self.assertNotIn("last_error", self.result())

    def trace(self):
        return json.loads(self.output.with_name("reconcile-run.json").read_text(encoding="utf-8"))

    def test_trace_of_a_quiet_run_has_stages_and_no_customer(self):
        fixture(self.source)
        self.assertEqual(self.run_job(Db(), "--fix")[0], 0)
        trace = self.trace()
        self.assertEqual((trace["state"], trace["stage"], trace["counts"], trace["books"], trace["fixed"], trace["customers"]), ("done", None, {"KHOP": 1}, 1, 0, {}))
        self.assertEqual([item["stage"] for item in trace["segments"]], ["tai", "sach", "doc", "so", "luu"])
        self.assertTrue(trace["finished_at"])
        history = self.output.with_name("reconcile-run-history.jsonl").read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(history), 1)

    def test_trace_of_a_write_has_before_and_after_and_no_name(self):
        self.undated_receipt_book()
        self.assertEqual(self.run_job(Db(), "--fix")[0], 0)
        trace = self.trace()
        stages = [item["stage"] for item in trace["segments"]]
        self.assertEqual(stages[:6], ["tai", "sach", "doc", "so", "chot", "tim"])
        self.assertIn("ghi", stages)
        self.assertEqual(stages[-1], "luu")
        row = trace["customers"]["1"]
        self.assertEqual((row["reason"], row["before_vnd"], row["after_vnd"], row["target_vnd"], trace["fixed"]),
                         ("FIXED", str(FAKE_AMOUNT), str(FAKE_AMOUNT - PAID), str(FAKE_AMOUNT - PAID), 1))
        self.assertTrue(row["decided_at"] and row["done_at"])
        self.assertNotIn(FAKE_NAME, self.output.with_name("reconcile-run.json").read_text(encoding="utf-8"))

    def test_trace_reports_each_step_while_the_run_is_still_going(self):
        """Xem trực tiếp cần biết sớm: khớp bao nhiêu, ai đang chờ, ai đang ghi, kết luận từng khách trước khi lượt xong."""
        self.undated_receipt_book()
        snapshots = []
        write = job.run_trace.RunTrace._write

        def keep(trace):
            snapshots.append(json.loads(json.dumps(trace.data)))
            write(trace)

        with patch.object(job.run_trace.RunTrace, "_write", keep):
            self.assertEqual(self.run_job(Db(), "--fix")[0], 0)
        at_stage = lambda stage: [item for item in snapshots if item["stage"] == stage]  # noqa: E731
        self.assertEqual(at_stage("chot")[0]["books"], 1)
        self.assertEqual(at_stage("chot")[0]["counts"], {"KHOP": 0})
        waiting = at_stage("tim")[0]["customers"]
        self.assertEqual(list(waiting), [])
        waiting = next(item for item in at_stage("tim") if item["customers"])["customers"]["1"]
        self.assertNotIn("reason", waiting)
        self.assertNotIn("decided_at", waiting)
        writing = next(item for item in at_stage("ghi") if item["customers"]["1"].get("writing"))["customers"]["1"]
        self.assertNotIn("done_at", writing)
        self.assertNotIn("reason", writing)
        self.assertEqual(at_stage("tim")[-1]["customers"]["1"]["reason"], "FIXED")
        self.assertEqual(at_stage("tim")[-1]["done"], 1)
        self.assertEqual(at_stage("tim")[-1]["total"], 1)
        self.assertEqual(self.trace()["customers"]["1"]["reason"], "FIXED")

    def test_trace_failure_changes_nothing_in_the_run(self):
        self.undated_receipt_book()
        db_ok = Db()
        self.assertEqual(self.run_job(db_ok, "--fix")[0], 0)
        expected = {key: value for key, value in self.result().items() if key != "checked_at"}
        expected["customers"] = [{key: value for key, value in row.items() if key != "fixed_at"} for row in expected["customers"]]
        self.output.unlink()
        self.undated_receipt_book()
        db_broken = Db()
        with patch.object(job.run_trace.RunTrace, "_write", side_effect=OSError("đĩa đầy")), patch.object(job.run_trace.RunTrace, "_append_history", side_effect=OSError("đĩa đầy")):
            self.assertEqual(self.run_job(db_broken, "--fix")[0], 0)
        self.assertEqual(db_broken.writes, db_ok.writes)
        result = {key: value for key, value in self.result().items() if key != "checked_at"}
        result["customers"] = [{key: value for key, value in row.items() if key != "fixed_at"} for row in result["customers"]]
        self.assertEqual(result, expected)

    def test_too_many_differences_are_in_the_trace_and_nothing_is_written(self):
        self.undated_receipt_book()
        db = Db()
        with patch.object(job, "MAX_DIFFERENT", 0):
            self.assertEqual(self.run_job(db, "--fix")[0], 0)
        trace = self.trace()
        self.assertTrue(trace["too_many"])
        self.assertNotIn("tim", [item["stage"] for item in trace["segments"]])
        self.assertEqual(db.writes, [])

    def test_failed_run_is_marked_in_the_trace(self):
        fixture(self.source)
        (self.source / "trips_so_goc.csv").unlink()
        self.assertEqual(self.run_job(Db())[0], 2)
        trace = self.trace()
        self.assertEqual(trace["state"], "failed")
        self.assertTrue(trace["reason"])

    def run_with_log(self, db, *extra, read=None):
        """Lượt có đọc log sửa Sheet (SHEET-LOG-01); `read` trả các sự kiện hoặc ném lỗi."""
        with (patch.object(job.sheet_sync_runner, "load_credentials", return_value={}),
              patch.object(job.sheet_sync_runner, "exchange_token", return_value="token"),
              patch.object(job.edit_log, "read_tail", side_effect=read)):
            return self.run_job(db, "--edit-log-id", "fake-log", "--credentials", "c.json", *extra)

    def edit_at(self, minutes_ago):
        at = job.now_vn() - job.dt.timedelta(minutes=minutes_ago)
        return lambda *_: [{"row": 2, "at": at, "kind": "EDIT", "tab": FAKE_NAME, "range": "M5"}]

    def test_edit_log_is_off_without_config_and_the_result_says_so(self):
        fixture(self.source)
        self.assertEqual(self.run_job(Db())[0], 0)
        self.assertEqual(self.result()["edit_log"], {"status": "OFF"})

    def test_unmatched_book_with_a_fresh_edit_is_marked_but_its_conclusion_stays(self):
        fixture(self.source)
        db = Db(total=FAKE_AMOUNT + 5)
        code, printed = self.run_with_log(db, "--fix", read=self.edit_at(5))
        self.assertEqual((code, db.writes), (0, []))
        result = self.result()
        row = result["customers"][0]
        self.assertEqual((row["status"], row["reason"], row["sheet_editing"]), ("LECH_TONG", "NOTHING_TO_WRITE", True))
        self.assertEqual(row["difference_vnd"], "5")
        self.assertEqual(result["edit_log"]["status"], "OK")
        self.assertEqual(json.loads(printed)["edit_log"], "OK")
        self.assertEqual(json.loads(self.output.with_name("reconcile-log.jsonl").read_text(encoding="utf-8"))["editing"], 1)

    def test_old_edit_is_only_a_note_and_the_book_still_needs_a_person(self):
        fixture(self.source)
        self.assertEqual(self.run_with_log(Db(total=FAKE_AMOUNT + 5), read=self.edit_at(120))[0], 0)
        row = self.result()["customers"][0]
        self.assertNotIn("sheet_editing", row)
        self.assertTrue(row["sheet_last_edit_at"])

    def test_a_fresh_edit_does_not_stop_the_exact_fix(self):
        self.undated_receipt_book()
        db = Db()
        self.assertEqual(self.run_with_log(db, "--fix", read=self.edit_at(1))[0], 0)
        self.assertEqual([w[0] for w in db.writes], ["record_receipt"])   # chốt khớp tổng vẫn là thứ quyết định ghi
        row = self.result()["customers"][0]
        self.assertEqual(row["reason"], "FIXED")
        self.assertNotIn("sheet_editing", row)

    def test_log_failure_keeps_the_run_and_only_reports_a_code(self):
        fixture(self.source)
        error = job.sheet_sync_runner.urllib.error.HTTPError("https://x", 403, "Forbidden", {}, None)
        self.addCleanup(error.close)
        code, printed = self.run_with_log(Db(total=FAKE_AMOUNT + 5), read=error)
        self.assertEqual(code, 0)
        result = self.result()
        self.assertEqual(result["edit_log"], {"status": "UNAVAILABLE", "reason": "403"})
        self.assertEqual(result["customers"][0]["reason"], "NOTHING_TO_WRITE")
        self.assertNotIn("sheet_editing", result["customers"][0])
        self.assertEqual(json.loads(printed)["edit_log"], "UNAVAILABLE")


if __name__ == "__main__":
    unittest.main()
