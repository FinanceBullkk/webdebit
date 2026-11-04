"""Máy tự đối soát (MAY-DOI-SOAT-01): cả lượt từ bản tải giả tới reconcile.json, DB giả. Không cần captures, Docker hay DB thật."""

import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tests"))
import v7_reconcile_auto as job  # noqa: E402
from test_v7_load_real_copy import FAKE_AMOUNT, FAKE_NAME, fixture  # noqa: E402
from v7_api_validate import ApiError  # noqa: E402
from v7_inbox import AUTO_ACTOR  # noqa: E402

PAID = 1000


class Db:
    """Một sổ khớp bản tải giả: chuyến FAKE-CONT-XY đã có giá; phiếu thu ghi xong thì tổng giảm."""

    def __init__(self, total=FAKE_AMOUNT, unit_price=FAKE_AMOUNT, fail=None):
        self.total, self.unit_price, self.fail, self.version = total, unit_price, fail, 4
        self.receipts, self.writes = [], []

    def ledger(self):
        return {"customer_id": 1, "status": "active", "version": self.version, "total_outstanding_vnd": str(self.total),
                "months": [{"month": "2026-10-01", "outstanding_vnd": str(self.total)}], "today_month": "2026-11-01",
                "month_locks": [], "legacy_rows": [], "events": [], "receipts": self.receipts,
                "trips": [{"id": 3, "status": "confirmed", "container": "FAKE-CONT-XY", "event_date": "2026-10-03", "month": "2026-10-01",
                           "unit_price_vnd": None if self.unit_price is None else str(self.unit_price), "other_fee_vnd": None}]}

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

    def undated_receipt_book(self):
        fixture(self.source, months=[("2026-10", "03/10/2026", FAKE_AMOUNT, FAKE_AMOUNT - PAID)], receipt=str(PAID), receipt_date="da tt")

    def test_matching_book_reports_and_writes_nothing(self):
        fixture(self.source)
        db = Db()
        code, printed = self.run_job(db, "--fix")
        self.assertEqual(code, 0)
        result = self.result()
        self.assertEqual((result["counts"], result["customers"], result["months_differ"]), ({"KHOP": 1}, [], []))
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


if __name__ == "__main__":
    unittest.main()
