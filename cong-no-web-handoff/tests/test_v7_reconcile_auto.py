"""Máy tự đối soát (MAY-DOI-SOAT-01): cả lượt từ bản tải giả tới reconcile.json, DB giả. Không cần captures, Docker hay DB thật."""

import io
import json
import shutil
import sys
import tempfile
import unittest
from collections import Counter
from contextlib import redirect_stdout
from pathlib import Path
from typing import ClassVar
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


class GoneReceiptDb(Db):
    """Sổ khớp tổng mà có một phiếu ghi từ Sheet (ngày 30/9) Sheet không còn; hủy phiếu thì tổng tăng lại."""

    def __init__(self, amount):
        super().__init__(total=FAKE_AMOUNT - PAID)
        self.receipts = [{"pid": "PH-001", "date": "2026-09-30", "method": "THU TIỀN", "amount_vnd": str(amount),
                          "reference": "Sheet: 30/09/2026 tt", "voided_by_event": None}]

    def run(self, function, payload, actor):
        if function == "void_receipt":
            self.writes.append((function, payload, actor))
            self.version += 1
            gone = next(r for r in self.receipts if r.get("pid") == payload["pid"])
            gone.update(voided_by_event=99, void_reason=payload["reason"])
            self.total += int(gone["amount_vnd"])
            return {"version": self.version}
        return super().run(function, payload, actor)


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
        booking = patch.dict("os.environ", {"WEBDEBIT_BOOKING_CHECK": "off"})   # có test riêng bên dưới; khỏi mở tiến trình con mỗi lượt
        booking.start()
        self.addCleanup(booking.stop)

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

    def test_booking_check_runs_alongside_and_its_error_never_fails_the_run(self):
        """KIEM-BOOKING-01: thiếu bản chụp booking thì phép kiểm báo mã lỗi ở file riêng; lượt đối soát vẫn đạt, số không đổi."""
        fixture(self.source)
        with patch.dict("os.environ", {"WEBDEBIT_BOOKING_CHECK": "on"}):
            code, printed = self.run_job(Db(), "--fix", "--snapshot", str(self.root / "none.json"), "--road", str(self.root / "none2.json"))
        self.assertEqual(code, 0)
        self.assertEqual((self.result()["counts"], self.result()["booking"]), ({"KHOP": 1}, {"error": "SEA_MISSING"}))
        self.assertEqual(json.loads(printed)["booking"], {"error": "SEA_MISSING"})
        saved = json.loads(self.output.with_name("booking-check.json").read_text(encoding="utf-8"))
        self.assertEqual(saved["last_error"]["reason"], "SEA_MISSING")
        log = json.loads(self.output.with_name("reconcile-log.jsonl").read_text(encoding="utf-8").splitlines()[-1])
        self.assertEqual(log["booking"], {"error": "SEA_MISSING"})
        # DU-CHUYEN-01: phần so sổ web chạy trong lượt, lỗi cũng chỉ thành mã ở file riêng.
        self.assertEqual((self.result()["booking_web"]["error"], log["booking_web"]["error"]), ("SEA_MISSING", "SEA_MISSING"))
        saved_web = json.loads(self.output.with_name("booking-web.json").read_text(encoding="utf-8"))
        self.assertEqual(saved_web["last_error"]["reason"], "SEA_MISSING")
        self.assertEqual(list((self.root / "work").iterdir()), [])
        self.run_job(Db(), "--fix")
        self.assertEqual((self.result()["booking"], self.result()["booking_web"]), ({"skipped": "OFF"}, {"skipped": "OFF"}))

    def test_booking_check_reads_the_download_before_the_work_folder_is_removed(self):
        """Bản tải nằm trong thư mục tạm của lượt; tiến trình con phải đọc xong trước khi thư mục bị xóa."""
        fixture(self.source)
        created = job.dt.datetime.now(job.dt.UTC).isoformat()
        sources = {}
        for name, row in (("snapshot.json", {"container": "FAKE-CONT-XY", "event_date": "2026-10-03", "customer_name": "X", "source_row": 2}),
                          ("road.json", {"container": "ROAD1234567", "event_date": "2026-10-04", "owner": "Y", "source_row": 2})):
            sources[name] = self.root / name
            sources[name].write_text(json.dumps({"rows": [row], "runner": {"created_at": created}}), encoding="utf-8")

        def download(_sheet, _credentials, output):
            shutil.copy(self.source / "source-google-export.xlsx", output)
            return output

        printed = io.StringIO()
        with patch.dict("os.environ", {"WEBDEBIT_BOOKING_CHECK": "on"}), patch.object(job, "download", download), \
                patch.object(job, "PsqlDirect", return_value=Db()), redirect_stdout(printed), patch("sys.stderr"):
            code = job.main(["--source-dir", str(self.source), "--spreadsheet-id", "x", "--credentials", "y", "--output", str(self.output),
                             "--work-dir", str(self.root / "work"), "--snapshot", str(sources["snapshot.json"]), "--road", str(sources["road.json"])])
        self.assertEqual(code, 0)
        booking = self.result()["booking"]
        self.assertNotIn("error", booking)
        self.assertEqual((booking["sheet_rows"], booking["paired"]), (1, 1))
        self.assertNotIn(FAKE_NAME, printed.getvalue())
        self.assertEqual(list((self.root / "work").iterdir()), [])

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
                         ("FIXED", "KHOP", str(FAKE_AMOUNT - PAID), "0", {"receipts": 1, "prices": 0, "legacy_deleted": 0, "fee_rows": 0, "fee_undone": 0, "receipts_voided": 0}))
        self.assertEqual(result["matched"], {"1": str(FAKE_AMOUNT - PAID)})

    def test_matched_book_whose_sheet_replaced_a_receipt_waits_for_a_person(self):
        """THAY-PHIEU-SHEET-01 rồi WEB-CHINH-01 (25/11/2026): tổng khớp vì Sheet thay một phiếu web đã ghi bằng phiếu khác cùng số. Trước
        đây máy hủy phiếu cũ, ghi phiếu mới; nay web là sổ chính nên máy không đụng, khách hiện cho người và việc chờ không bị ẩn."""
        self.undated_receipt_book()
        db = GoneReceiptDb(PAID)
        self.assertEqual(self.run_job(db, "--fix")[0], 0)
        self.assertEqual(db.writes, [])
        result = self.result()
        row = result["customers"][0]
        self.assertEqual((result["counts"], row["status"], row["reason"], row["difference_vnd"]), ({"KHOP": 1}, "KHOP", "WEB_KEPT", "0"))
        self.assertEqual(sorted(group["kind"] for group in row["kept"]), ["receipts_gone", "receipts_no_date"])
        self.assertEqual((result["details"], result["matched"]), ({"checked": 1, "web_kept": 1}, {}))

    def test_matched_book_with_waiting_work_that_does_not_cancel_out_is_listed(self):
        self.undated_receipt_book()
        db = GoneReceiptDb(PAID + 300)
        self.assertEqual(self.run_job(db, "--fix")[0], 0)
        self.assertEqual(db.writes, [])
        result = self.result()
        row = result["customers"][0]
        self.assertEqual((result["counts"], row["status"], row["reason"], row["difference_vnd"]), ({"KHOP": 1}, "KHOP", "DETAIL_DIFFERS", "0"))
        self.assertEqual([(g["kind"], g["delta_vnd"], g["chosen"]) for g in row["groups"]],
                         [("receipts_gone", str(PAID + 300), False), ("receipts_no_date", str(-PAID), False)])
        self.assertEqual(result["details"], {"checked": 1, "detail_differs": 1})
        self.assertEqual(result["matched"], {})   # việc chờ của sổ không bị ẩn ở Việc cần làm
        self.run_job(GoneReceiptDb(PAID + 300))   # chế độ chỉ kiểm cũng báo như vậy
        self.assertEqual(self.result()["customers"][0]["reason"], "DETAIL_DIFFERS")

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

    def test_receipt_a_person_voided_is_not_written_again(self):
        self.undated_receipt_book()
        db = Db()
        self.assertEqual(self.run_job(db, "--fix")[0], 0)
        self.assertEqual([w[0] for w in db.writes], ["record_receipt"])
        db.receipts[0]["voided_by_event"] = 77   # người hủy phiếu máy vừa ghi; Sheet vẫn còn dòng thu
        db.total += PAID
        self.assertEqual(self.run_job(db, "--fix")[0], 0)
        self.assertEqual(len(db.writes), 1)      # trước đây: lượt sau ghi lại đúng phiếu đó
        row = next(r for r in self.result()["customers"] if r["status"] == "LECH_TONG")
        self.assertEqual((row["reason"], row["difference_vnd"]), ("NOTHING_TO_WRITE", str(PAID)))

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

    def test_old_web_ahead_trip_is_named_for_a_person_and_the_sum_stays(self):
        fixture(self.source, months=[("2026-10", "03/10/2026", 0, 0)], missing_price=True)

        def run_on(month, day):
            db = Db(total=500, unit_price=500)
            with patch.object(job, "now_vn", return_value=job.now_vn().replace(year=2026, month=month, day=day, hour=9)):
                self.assertEqual(self.run_job(db, "--fix")[0], 0)
            self.assertEqual(db.writes, [])
            return self.result()["customers"][0]
        fresh = run_on(10, 10)   # chuyến ngày 03/10 mới 7 ngày: Sheet chưa kịp nhập
        self.assertEqual((fresh["reason"], fresh["web_ahead_vnd"], fresh.get("hints")), ("WEB_AHEAD", "500", None))
        old = run_on(11, 10)     # 38 ngày: phép tính giữ nguyên, thêm câu để người xem
        self.assertEqual((old["reason"], old["web_ahead_vnd"], old["difference_vnd"]), ("WEB_AHEAD", "500", "500"))
        self.assertEqual(old["hints"], [{"kind": "ahead_old", "container": "FAKE-CONT-XY", "date": "2026-10-03", "amount_vnd": "500", "days": 38}])

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

    def tong_rows(self, *names_and_ends):
        """Tab TONG thật: tiêu đề hai khối (tháng 9, tháng 10), các dòng (tên, số cuối tháng) ở khối tháng 10; số None là ô trống."""
        rows = {6: TONG_TITLES}
        for number, (name, end) in enumerate(names_and_ends, 7):
            rows[number] = {"M": name} | ({} if end is None else {"Q": str(end)})
        return rows

    def test_tong_rows_equal_to_the_books_are_counted_and_only_counts_leave_the_file(self):
        """KIEM-TONG-01: lượt mọi khách khớp vẫn kiểm TONG; tên trên TONG khác dấu, gạch, khoảng trắng vẫn ghép được."""
        fixture(self.source, tong=self.tong_rows(("fake private - customer  zxq", FAKE_AMOUNT)))
        db = Db()
        with patch.object(job.snapshots, "build_all", wraps=job.snapshots.build_all) as build:
            code, printed = self.run_job(db, "--fix")
        self.assertEqual((code, db.writes), (0, []))
        build.assert_called_once()   # không khách nào lệch: dựng bản chụp riêng cho TONG
        tong = self.result()["tong"]
        self.assertEqual((tong["month"], tong["matched"], tong["differs"], tong["unknown_names"], tong["blank_on_tong"]), ("2026-10", 1, [], [], []))
        self.assertEqual((tong["tong_sum_vnd"], tong["expected_sum_vnd"], tong["gap_vnd"]), (str(FAKE_AMOUNT), str(FAKE_AMOUNT), "0"))
        counts = {"month": "2026-10", "matched": 1, "blank": 0, "differs": 0, "unknown_names": 0}
        self.assertEqual(json.loads(printed)["tong"], counts)
        log = self.output.with_name("reconcile-log.jsonl").read_text(encoding="utf-8")
        self.assertEqual(json.loads(log)["tong"], counts)
        for secret in (FAKE_NAME, "zxq", str(FAKE_AMOUNT)):
            self.assertNotIn(secret, printed)
        self.assertNotIn("zxq", log)

    def test_tong_month_end_takes_later_months_of_the_tab_off_the_book(self):
        later = 5000
        fixture(self.source, months=[("2026-10", "03/10/2026", FAKE_AMOUNT, FAKE_AMOUNT), ("2026-11", "04/11/2026", later, FAKE_AMOUNT + later)],
                tong=self.tong_rows((FAKE_NAME, FAKE_AMOUNT)))
        self.assertEqual(self.run_job(Db(total=FAKE_AMOUNT + later), "--fix")[0], 0)
        result = self.result()
        self.assertEqual(result["counts"], {"KHOP": 1})
        self.assertEqual((result["tong"]["matched"], result["tong"]["differs"]), (1, []))   # sổ hôm nay A + B; cuối tháng 10 là A

    def test_blank_tong_cell_and_a_name_without_book_are_named(self):
        for label, rows in (("ô trống", ((FAKE_NAME, None), ("KHACH KHONG CO SO", 5))), ("không có dòng", (("KHACH KHONG CO SO", 5),))):
            with self.subTest(label):
                fixture(self.source, tong=self.tong_rows(*rows))
                code, printed = self.run_job(Db(), "--fix")
                self.assertEqual(code, 0)
                tong = self.result()["tong"]
                self.assertEqual(tong["blank_on_tong"], [{"book": 1, "name": FAKE_NAME, "expected_vnd": str(FAKE_AMOUNT)}])
                self.assertEqual(tong["unknown_names"], [{"name": "KHACH KHONG CO SO", "end_vnd": "5"}])
                self.assertEqual((tong["matched"], tong["differs"], tong["gap_vnd"]), (0, [], str(5 - FAKE_AMOUNT)))
                self.assertEqual(json.loads(printed)["tong"], {"month": "2026-10", "matched": 0, "blank": 1, "differs": 0, "unknown_names": 1})
                self.assertNotIn("KHACH KHONG CO SO", printed)

    def test_tong_cell_that_differs_from_the_book_is_named(self):
        fixture(self.source, tong=self.tong_rows((FAKE_NAME, FAKE_AMOUNT + 7)))
        self.assertEqual(self.run_job(Db(), "--fix")[0], 0)
        tong = self.result()["tong"]
        self.assertEqual(tong["differs"], [{"name": FAKE_NAME, "book": 1, "tong_vnd": str(FAKE_AMOUNT + 7), "expected_vnd": str(FAKE_AMOUNT)}])
        self.assertEqual((tong["matched"], tong["blank_on_tong"], tong["gap_vnd"]), (0, [], "7"))

    def test_tong_is_compared_with_the_total_after_the_fix_and_snapshots_are_built_once(self):
        fixture(self.source, months=[("2026-10", "03/10/2026", FAKE_AMOUNT, FAKE_AMOUNT - PAID)], receipt=str(PAID), receipt_date="da tt",
                tong=self.tong_rows((FAKE_NAME, FAKE_AMOUNT - PAID)))
        db = Db()
        with patch.object(job.snapshots, "build_all", wraps=job.snapshots.build_all) as build:
            self.assertEqual(self.run_job(db, "--fix")[0], 0)
        self.assertEqual([w[0] for w in db.writes], ["record_receipt"])
        build.assert_called_once()   # tìm cách sửa và kiểm TONG dùng chung một bản chụp
        tong = self.result()["tong"]
        self.assertEqual((tong["matched"], tong["differs"]), (1, []))

    def test_web_ahead_part_is_taken_off_before_comparing_with_tong(self):
        fixture(self.source, months=[("2026-10", "03/10/2026", 0, 0)], missing_price=True, tong=self.tong_rows((FAKE_NAME, 0)))
        self.assertEqual(self.run_job(Db(total=500, unit_price=500), "--fix")[0], 0)
        result = self.result()
        self.assertEqual(result["customers"][0]["reason"], "WEB_AHEAD")
        self.assertEqual((result["tong"]["matched"], result["tong"]["differs"]), (1, []))   # web 500 đều là phần Sheet chưa ghi: cuối tháng 0

    def test_book_created_in_the_run_is_compared_with_its_tong_row(self):
        self.new_tab()
        self.assertEqual(self.run_job(NewBookDb(), "--fix")[0], 0)
        tong = self.result()["tong"]
        self.assertEqual((tong["matched"], tong["unknown_names"], tong["blank_on_tong"]), (1, [], []))

    def test_unreadable_tong_is_skipped(self):
        layouts = {"không có tab TONG": None,
                   "không có cột cuối tháng": {6: {"D": "LOAI HANG", "E": "TÊN KHÁCH HÀNG", "F": "CÔNG NỢ PHÁT SINH TRONG THÁNG 10.2026"},
                                               7: {"E": FAKE_NAME, "F": "5"}}}
        for label, tong in layouts.items():
            with self.subTest(label):
                fixture(self.source, tong=tong)
                with patch.object(job.snapshots, "build_all", wraps=job.snapshots.build_all) as build:
                    code, printed = self.run_job(Db(), "--fix")
                self.assertEqual(code, 0)
                result = self.result()
                self.assertEqual((result["tong"], result["counts"]), ({"month": None, "skipped": "TONG_KHONG_DOC_DUOC"}, {"KHOP": 1}))
                self.assertEqual(json.loads(printed)["tong"], {"skipped": "TONG_KHONG_DOC_DUOC"})
                build.assert_called_once()   # chỉ cho phần xét chi tiết khách khớp (THAY-PHIEU-SHEET-01); TONG vẫn bỏ qua

    def test_tong_failure_is_only_a_code_and_the_run_keeps_its_work(self):
        self.undated_receipt_book()
        db = Db()
        with patch.object(job.audit, "read_tong", side_effect=RuntimeError("đọc hỏng")):
            code, printed = self.run_job(db, "--fix")
        self.assertEqual(code, 0)
        self.assertEqual([w[0] for w in db.writes], ["record_receipt"])
        result = self.result()
        self.assertEqual((result["customers"][0]["reason"], result["counts"]), ("FIXED", {"KHOP": 1}))
        self.assertEqual(result["tong"], {"month": None, "skipped": "ERROR", "error": "RuntimeError"})
        self.assertEqual(json.loads(printed)["tong"], {"skipped": "ERROR", "error": "RuntimeError"})
        fixture(self.source, tong=self.tong_rows((FAKE_NAME, FAKE_AMOUNT)))   # mọi khách khớp, dựng bản chụp riêng cho TONG thì hỏng
        with patch.object(job.snapshots, "build_all", side_effect=OSError("đĩa đầy")):
            self.assertEqual(self.run_job(Db())[0], 0)
        self.assertEqual((self.result()["tong"], self.result()["counts"]), ({"month": None, "skipped": "ERROR", "error": "OSError"}, {"KHOP": 1}))

    def test_too_many_differences_skip_the_tong_check(self):
        self.undated_receipt_book()
        with patch.object(job, "MAX_DIFFERENT", 0):
            self.assertEqual(self.run_job(Db(), "--fix")[0], 0)
        self.assertEqual(self.result()["tong"], {"month": None, "skipped": "TOO_MANY_DIFFERENT"})

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

    def test_web_created_book_without_a_tab_is_not_a_difference(self):
        """KHACH-WEB-01: sổ quản lý tạo trên web (có tên booking) không có tab là đúng thiết kế; sổ không tên booking mà mất tab vẫn báo."""
        fixture(self.source)

        class WebBooks(Db):
            def run(self, function, payload, actor):
                if function == "list_customers":
                    return {"customers": [{"id": 1, "name": FAKE_NAME, "status": "active"},
                                          {"id": 5, "name": "SO WEB MOI", "status": "active", "booking_names": ["SO WEB MOI"]},
                                          {"id": 6, "name": "SO MAT TAB", "status": "active", "booking_names": []}]}
                return super().run(function, payload, actor)
        db = WebBooks()
        self.assertEqual(self.run_job(db, "--fix")[0], 0)
        self.assertEqual(db.writes, [])
        rows = {row["customer"]: (row["status"], row["reason"]) for row in self.result()["customers"]}
        self.assertEqual(rows["SO WEB MOI"], ("CHI_CO_WEB", "WEB_BOOK"))
        self.assertEqual(rows["SO MAT TAB"], ("CHI_CO_WEB", "CHI_CO_WEB"))

    def test_held_customer_is_named_with_reason_and_never_touched(self):
        fixture(self.source, months=[("2026-10", "03/10/2026", FAKE_AMOUNT, FAKE_AMOUNT + 1)])   # chuỗi số dư trên Sheet không khớp
        db = Db()
        self.assertEqual(self.run_job(db, "--fix")[0], 0)
        self.assertEqual(db.writes, [])
        row = self.result()["customers"][0]
        self.assertEqual((row["status"], row["reason"]), ("CHI_CO_WEB", "HELD"))
        self.assertTrue(row["held_reasons"])
        self.assertEqual(row["hints"], [{"kind": "chain_break", "month": "2026-10", "sheet_end_vnd": str(FAKE_AMOUNT + 1),
                                         "expected_end_vnd": str(FAKE_AMOUNT), "delta_vnd": "1"}])   # CHAN-DOAN-LECH-01

    def test_held_customer_carries_the_number_of_places_the_sheet_fix_block_names(self):
        fixture(self.source, months=[("2026-10", "03/10/2026", FAKE_AMOUNT, FAKE_AMOUNT + 1)])
        seen = []
        real = job.fix.sheet_findings

        def counted(prices, ledger, customers, held):
            found = real(prices, ledger, customers, held)
            seen.append((held["customer_id"], held["hints"][0]["kind"], len(found["findings"])))
            return found
        with patch.object(job.fix, "sheet_findings", side_effect=counted):
            self.assertEqual(self.run_job(Db(), "--fix")[0], 0)
        row = self.result()["customers"][0]
        self.assertEqual(seen, [(1, "chain_break", row["sheet_fix_count"])])   # cùng hàm, cùng dòng HELD (có gợi ý) với khối khi mở
        self.assertIsInstance(row["sheet_fix_count"], int)

    def test_counting_sheet_fixes_fails_quietly_and_keeps_the_held_row(self):
        fixture(self.source, months=[("2026-10", "03/10/2026", FAKE_AMOUNT, FAKE_AMOUNT + 1)])
        with patch.object(job.fix, "sheet_findings", side_effect=RuntimeError("x")):
            self.assertEqual(self.run_job(Db(), "--fix")[0], 0)
        row = self.result()["customers"][0]
        self.assertEqual(row["reason"], "HELD")
        self.assertNotIn("sheet_fix_count", row)

    def test_no_held_customer_reads_no_ledger_for_sheet_fixes(self):
        fixture(self.source)
        with patch.object(job.fix, "sheet_findings") as found:
            self.assertEqual(self.run_job(Db())[0], 0)
        found.assert_not_called()

    def test_unexplained_gap_names_a_slip_written_twice_and_writes_nothing(self):
        fixture(self.source)
        db = Db(total=FAKE_AMOUNT - 5)
        db.receipts = [{"pid": f"PH-00{n}", "date": "2026-10-31", "amount_vnd": "5", "reference": "tay", "voided_on": None} for n in (1, 2)]
        self.assertEqual(self.run_job(db, "--fix")[0], 0)
        self.assertEqual(db.writes, [])
        row = self.result()["customers"][0]
        self.assertEqual((row["reason"], row["hints_explain"]), ("NOTHING_TO_WRITE", True))
        self.assertEqual(row["hints_basis"]["version"], db.version)
        prices, receipts = job.snapshots.build_all(self.source / "source-google-export.xlsx")
        self.assertEqual(row["hints_basis"], {"version": db.version, "prices_sha256": prices["sha256"], "receipts_sha256": receipts["sha256"],
                                              "web_total_vnd": str(row["web_total_vnd"]), "sheet_total_vnd": str(row["sheet_total_vnd"])})
        self.assertEqual(row["hints"], [{"kind": "receipt_twice", "date": "2026-10-31", "amount_vnd": "5", "pids": ["PH-001", "PH-002"],
                                         "delta_vnd": "5"}])

    def test_hint_failure_keeps_the_conclusion(self):
        fixture(self.source)
        with patch.object(job.hints, "for_book", side_effect=RuntimeError("x")):
            self.assertEqual(self.run_job(Db(total=FAKE_AMOUNT + 5), "--fix")[0], 0)
        row = self.result()["customers"][0]
        self.assertEqual(row["reason"], "NOTHING_TO_WRITE")
        self.assertNotIn("hints", row)

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
        self.assertEqual(trace["books"], 1)
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


class BookDb:
    """Sổ 7 ("KHACH A") dựng từ chuyến, phiếu và dòng điều chỉnh giả; lệnh ghi đổi tổng đúng như hàm SQL. Dùng cho `settle` trực tiếp."""

    def __init__(self, trips=(), receipts=(), adjustments=(), fail=None):
        self.trips, self.receipts, self.adjustments = [dict(t) for t in trips], [dict(r) for r in receipts], [dict(a) for a in adjustments]
        self.version, self.writes, self.fail = 9, [], fail

    def total(self):
        charged = sum(int(t["unit_price_vnd"]) + int(t.get("other_fee_vnd") or 0) for t in self.trips if t.get("unit_price_vnd") is not None)
        paid = sum(int(r["amount_vnd"]) for r in self.receipts if not r.get("voided_by_event"))
        return charged + sum(int(a["amount_vnd"]) for a in self.adjustments) - paid

    def run(self, function, payload, actor):
        if function == "get_ledger":
            return {"customer_id": 7, "version": self.version, "total_outstanding_vnd": str(self.total()), "today_month": "2026-11-01",
                    "month_locks": [], "legacy_rows": [], "events": [], "trips": self.trips, "receipts": self.receipts,
                    "adjustments": self.adjustments}
        self.writes.append((function, payload, actor))
        if function == self.fail:
            raise ApiError(409, "STALE_LEDGER", "x")
        self.version += 1
        if function == "record_receipt":
            self.receipts.append({"pid": f"PH-{self.version}", "date": payload["date"], "method": "THU TIỀN",
                                  "amount_vnd": payload["amount_vnd"], "reference": payload["reference"]})
        elif function == "edit_trip_price":
            trip = next(t for t in self.trips if t["id"] == payload["trip_id"])
            trip.update(unit_price_vnd=payload["unit_price_vnd"], other_fee_vnd=payload["other_fee_vnd"])
        elif function == "void_receipt":
            next(r for r in self.receipts if r["pid"] == payload["pid"])["voided_by_event"] = self.version
        elif function == "adjust_month":
            self.adjustments.append({"id": self.version, "month": payload["debt_month"], "amount_vnd": payload["amount_vnd"], "note": payload["note"]})
        elif function == "delete_month_adjustment":
            self.adjustments = [a for a in self.adjustments if a["id"] != payload["adjustment_id"]]
        return {"version": self.version}


def trip(trip_id, container, unit=None, month="2026-11", day="03"):
    return {"id": trip_id, "status": "confirmed", "container": container, "event_date": f"{month}-{day}", "month": f"{month}-01",
            "unit_price_vnd": unit, "other_fee_vnd": None}


def line(source_row, container, unit=None, month="2026-11", day="03", tab="KHACH A"):
    return {"customer_tab": tab, "source_row": source_row, "debt_month": month, "container": container, "date": f"{month}-{day}",
            "sheet_unit_price_vnd": unit, "sheet_other_fee_vnd": None, "sheet_total_vnd": unit}


def paid(source_row, amount, day=None, month="2026-11"):
    """Dòng thu Sheet; ngày đọc từ ghi chú như runner (`pay_date`), không ngày thì là phiếu không ngày."""
    note = f"{day[8:10]}/{day[5:7]}/{day[:4]} tt" if day else "tt"
    return {"customer_tab": "KHACH A", "source_row": source_row, "debt_month": month, "amount_vnd": amount, "note": note}


class WebKeptTests(unittest.TestCase):
    """WEB-CHINH-01 (3), 25/11/2026: web là sổ chính thức. Máy theo Sheet chỉ thêm cái web chưa có; Sheet đổi giá, sửa hay bỏ phiếu web
    đã ghi, dòng tiền kéo tổng về Sheet thì máy không ghi, khách thành việc của người (`WEB_KEPT`) và web giữ nguyên tới khi người bấm."""

    CUSTOMERS = ({"id": 7, "name": "KHACH A"}, {"id": 8, "name": "KHACH B"})
    TODAY = job.dt.date(2026, 11, 25)
    TABS: ClassVar[dict] = {"KHACH A": {"status": "ok", "findings": []}}

    def settle(self, db, sheet_total, price_rows=(), receipt_rows=(), *, matched=False, write=True):
        prices = {"rows": list(price_rows), "sha256": "a" * 64, "tabs": self.TABS}
        receipts = {"rows": list(receipt_rows), "sha256": "b" * 64, "tabs": self.TABS}
        row = {"customer": "KHACH A", "status": "KHOP" if matched else "LECH_TONG", "sheet_total_vnd": sheet_total}
        settle = job.settle_matched if matched else job.settle
        with patch("sys.stderr"):
            settle(db, row, 7, list(self.CUSTOMERS), prices, receipts, self.TODAY, write=write)
        return row

    def test_new_receipt_is_written_and_a_sheet_price_change_waits_for_a_person(self):
        db = BookDb(trips=[trip(1, "AAAA1", unit="100")])
        row = self.settle(db, 100 + 20 - 50, [line(1, "AAAA1", unit=120)], [paid(30, 50, day="2026-11-20")])
        self.assertEqual([w[0] for w in db.writes], ["record_receipt"])   # trước 25/11: cả edit_trip_price lấy giá Sheet
        self.assertEqual(db.trips[0]["unit_price_vnd"], "100")
        self.assertEqual((row["reason"], row["status"], row["web_total_vnd"], row["difference_vnd"]), ("WEB_KEPT", "LECH_TONG", 50, -20))
        self.assertEqual(row["kept"], [{"kind": "prices", "month": "2026-11", "count": 1, "delta_vnd": "20"}])
        self.assertEqual(row["written"]["receipts"], 1)
        self.settle(db, 100 + 20 - 50, [line(1, "AAAA1", unit=120)], [paid(30, 50, day="2026-11-20")])
        self.assertEqual(len(db.writes), 1)   # lượt sau: phần để người vẫn để người, không ghi lại phiếu

    def test_price_for_an_unpriced_trip_is_still_added(self):
        db = BookDb(trips=[trip(1, "AAAA1")])
        row = self.settle(db, 90, [line(1, "AAAA1", unit=90)])
        self.assertEqual(([w[0] for w in db.writes], row["reason"], row["status"]), (["edit_trip_price"], "FIXED", "KHOP"))
        self.assertNotIn("kept", row)

    def test_receipt_the_sheet_dropped_is_not_voided(self):
        old = {"pid": "PH-001", "date": "2026-11-10", "method": "THU TIỀN", "amount_vnd": "40", "reference": "Sheet: 10/11/2026 tt"}
        db = BookDb(trips=[trip(1, "AAAA1", unit="100")], receipts=[old])
        row = self.settle(db, 100, [line(1, "AAAA1", unit=100)])
        self.assertEqual((db.writes, row["reason"], row["kept"][0]["kind"]), ([], "WEB_KEPT", "receipts_gone"))
        self.assertIsNone(db.receipts[0].get("voided_by_event"))

    def test_receipt_the_sheet_changed_keeps_the_old_slip_and_does_not_add_the_new_one(self):
        """Sheet sửa số một phiếu web đã ghi từ Sheet: phiếu cũ thành "Sheet không còn", phiếu mới thành "sẵn sàng". Ghi riêng phiếu mới là
        thu hai lần, nên cả hai chờ người."""
        old = {"pid": "PH-001", "date": "2026-11-10", "method": "THU TIỀN", "amount_vnd": "40", "reference": "Sheet: 10/11/2026 tt"}
        db = BookDb(trips=[trip(1, "AAAA1", unit="100")], receipts=[old])
        row = self.settle(db, 100 - 45, [line(1, "AAAA1", unit=100)], [paid(31, 45, day="2026-11-10")])
        self.assertEqual((db.writes, row["reason"]), ([], "WEB_KEPT"))
        self.assertEqual(sorted(group["kind"] for group in row["kept"]), ["receipts", "receipts_gone"])

    def test_money_row_without_container_is_not_turned_into_an_adjustment(self):
        db = BookDb(trips=[trip(1, "AAAA1", unit="100")])
        row = self.settle(db, 143, [line(1, "AAAA1", unit=100), line(2, "", unit=43)])
        self.assertEqual((db.writes, db.adjustments, row["reason"]), ([], [], "WEB_KEPT"))
        self.assertEqual(row["kept"], [{"kind": "fee_rows", "month": "2026-11", "count": 1, "delta_vnd": "43"}])

    def test_machine_adjustment_whose_sheet_row_is_gone_is_not_deleted(self):
        mine = {"id": 77, "month": "2026-11-01", "amount_vnd": "43", "note": job.fix.FEE_NOTE + ", dòng 2"}
        db = BookDb(trips=[trip(1, "AAAA1", unit="100")], adjustments=[mine])
        row = self.settle(db, 100, [line(1, "AAAA1", unit=100)])
        self.assertEqual((db.writes, len(db.adjustments), row["reason"], row["kept"][0]["kind"]), ([], 1, "WEB_KEPT", "fee_undo"))

    def test_matched_book_whose_sheet_changes_cancel_out_writes_nothing(self):
        """Khách khớp tổng mà Sheet đổi giá hai chuyến bù nhau: trước 25/11 máy ghi cả hai theo Sheet, nay là việc của người."""
        db = BookDb(trips=[trip(1, "AAAA1", unit="100"), trip(2, "AAAA2", unit="80", month="2026-10")])
        row = self.settle(db, 180, [line(1, "AAAA1", unit=110), line(2, "AAAA2", unit=70, month="2026-10")], matched=True)
        self.assertEqual((db.writes, row["reason"], row["status"], row["detail_check"]), ([], "WEB_KEPT", "KHOP", True))

    def test_matched_book_whose_price_changes_cancel_out_in_one_month_waits_for_a_person(self):
        """Sổ 141 tháng 9/2026 (thật, 27/11): Sheet sửa giá hai chuyến cùng tháng, một +10, một −10. Nhóm giá của tháng cộng lại bằng 0
        nên trước đây máy coi như không có việc, sổ khớp tổng mà web sai giá từng chuyến. Nay là việc của người, không ghi gì."""
        db = BookDb(trips=[trip(1, "AAAA1", unit="90"), trip(2, "AAAA2", unit="80")])
        row = self.settle(db, 170, [line(1, "AAAA1", unit=100), line(2, "AAAA2", unit=70)], matched=True)
        self.assertEqual((db.writes, row["reason"], row["status"], row["detail_check"]), ([], "WEB_KEPT", "KHOP", True))
        self.assertEqual(row["kept"], [{"kind": "prices", "month": "2026-11", "count": 2, "delta_vnd": "0"}])

    def test_matched_book_whose_additions_cancel_out_is_written_and_a_half_write_is_no_longer_matched(self):
        """Khách khớp tổng mà Sheet thêm cả giá cho chuyến chưa giá lẫn một phiếu bằng đúng số đó: toàn việc thêm, máy ghi hết. Ghi dở
        (phiếu xong, giá bị từ chối) thì tổng đã đổi, khách không còn tính là khớp."""
        rows, slips = [line(1, "AAAA1", unit=100), line(2, "AAAA2", unit=50)], [paid(30, 50, day="2026-11-20")]
        db = BookDb(trips=[trip(1, "AAAA1", unit="100"), trip(2, "AAAA2")])
        row = self.settle(db, 100, rows, slips, matched=True)
        self.assertEqual(([w[0] for w in db.writes], row["reason"], row["status"]), (["record_receipt", "edit_trip_price"], "FIXED", "KHOP"))
        db = BookDb(trips=[trip(1, "AAAA1", unit="100"), trip(2, "AAAA2")], fail="edit_trip_price")
        row = self.settle(db, 100, rows, slips, matched=True)
        self.assertEqual((row["status"], row["reason"], row["difference_vnd"]), ("LECH_TONG", "WRITE_ERROR", -50))

    def test_report_mode_still_says_it_would_add_and_names_what_waits(self):
        db = BookDb(trips=[trip(1, "AAAA1", unit="100")])
        row = self.settle(db, 70, [line(1, "AAAA1", unit=120)], [paid(30, 50, day="2026-11-20")], write=False)
        self.assertEqual((db.writes, row["reason"], [group["kind"] for group in row["kept"]]), ([], "WOULD_FIX", ["prices"]))

    def test_book_104_october_prices_changing_places_stays_shuffled_and_untouched(self):
        """Sổ 104 tháng 10/2026 (thật, 25/11): Sheet đổi chỗ đơn giá giữa các chuyến, web đúng. Máy chỉ báo `SHEET_SHUFFLED`, không ghi."""
        trips = [trip(1, "AAAA1", unit="50", month="2026-10"), trip(2, "AAAA2", unit="75", month="2026-10"),
                 trip(3, "AAAA3", unit="65", month="2026-10"), trip(4, "AAAA4", unit="55", month="2026-10")]
        rows = [line(1, "AAAA1", unit=75, month="2026-10"), line(2, "AAAA2", unit=65, month="2026-10"),
                line(3, "AAAA3", unit=50, month="2026-10"), line(4, "AAAA4", unit=50, month="2026-10")]
        slip = {"pid": "PH-1", "date": "2026-10-20", "method": "THU TIỀN", "amount_vnd": "45", "reference": "Sheet: tt"}
        db = BookDb(trips=trips, receipts=[slip])
        row = self.settle(db, 245 - 5 - 45, rows, [paid(30, 45, day="2026-10-20", month="2026-10")])
        self.assertEqual((db.writes, row["reason"], row["shuffled_months"], row["status"]), ([], "SHEET_SHUFFLED", ["2026-10"], "LECH_TONG"))

    def test_book_134_trip_moved_to_another_book_is_only_reported(self):
        """Sổ 134 (thật, 25/11): chuyến đã chuyển sang sổ 85 trên web mà tab của sổ 134 còn ghi. Máy chỉ báo lệch tổng, không thêm lại
        chuyến hay dòng tiền nào vào sổ 134."""
        db = BookDb(trips=[trip(1, "AAAA1", unit="100")])
        row = self.settle(db, 100 + 70, [line(1, "AAAA1", unit=100), line(109, "MOVE0000001", unit=70)])
        self.assertEqual((db.writes, row["status"], row["reason"]), ([], "LECH_TONG", "NOTHING_TO_WRITE"))
        self.assertNotIn("kept", row)


class BookingOnlyTests(unittest.TestCase):
    """WEB-CHINH-01, tắt máy 1/12/2026: `--booking-only` chỉ so sổ web với booking. Không tải Sheet, không đọc hay ghi reconcile.json,
    không lệnh ghi DB nào."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.output = Path(self.temp.name) / "reconcile.json"

    def run_job(self, db, env=None, *extra):
        printed, seen = io.StringIO(), {}

        def compare(books, output, sea, road):
            seen.update(books=books, output=output)
            return {"counts": {"khop": 1}, "booking": 1, "web_rows": 1, "paired": 1, "seconds": 0}
        with patch.object(job, "PsqlDirect", return_value=db), patch.object(job.booking_check, "run_web_safely", compare), \
                patch.object(job, "download", side_effect=AssertionError("không được tải Sheet")), \
                patch.dict("os.environ", env or {"WEBDEBIT_BOOKING_CHECK": "on"}), redirect_stdout(printed), patch("sys.stderr"):
            code = job.main(["--booking-only", "--output", str(self.output), *extra])
        return code, json.loads(printed.getvalue()), seen

    def test_compares_web_books_with_booking_and_touches_nothing_else(self):
        db = Db()
        code, printed, seen = self.run_job(db)
        self.assertEqual((code, printed["mode"], printed["ok"], db.writes), (0, "booking-only", True, []))
        self.assertEqual(([book["id"] for book in seen["books"]], [t["container"] for t in seen["books"][0]["trips"]]), ([1], ["FAKE-CONT-XY"]))
        self.assertEqual(seen["output"], self.output.with_name("booking-web.json"))
        self.assertFalse(self.output.exists())

    def test_switched_off_and_wrong_combinations(self):
        code, printed, seen = self.run_job(Db(), {"WEBDEBIT_BOOKING_CHECK": "off"})
        self.assertEqual((code, printed["booking_web"], seen), (0, {"skipped": "OFF"}, {}))
        with patch("sys.stderr"), self.assertRaises(SystemExit):
            job.main(["--booking-only", "--fix", "--output", str(self.output)])
        with patch("sys.stderr"), self.assertRaises(SystemExit):
            job.main(["--output", str(self.output), "--xlsx", "x.xlsx"])   # chế độ đối soát vẫn cần --source-dir


if __name__ == "__main__":
    unittest.main()
