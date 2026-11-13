"""Read-only price match: Sheet tab rows to one web trip or original-book row, fake data only."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tests"))
import v7_price_match as pm  # noqa: E402
from test_v7_load_real_copy import FAKE_AMOUNT, FAKE_NAME, fixture  # noqa: E402


def sheet(row=5, container="FAKEU0000001", date="2026-10-03", price=50000000, fee=None, tab="Khach gia A"):
    return {"customer_tab": tab, "source_row": row, "debt_month": "2026-10", "container": container,
            "date": date, "sheet_unit_price_vnd": price, "sheet_other_fee_vnd": fee}


def trip(trip_id=11, container="FAKEU 0000001", date="2026-10-03", price=None, fee=None, status="confirmed"):
    return {"id": trip_id, "container": container, "event_date": date, "unit_price_vnd": price,
            "other_fee_vnd": fee, "status": status, "month": date[:7] + "-01", "deleted": False}


def book(trips=(), legacy=(), locked=False):
    return {"today_month": "2026-10-01", "month_locks": [{"month": "2026-10-01", "locked": locked}],
            "trips": list(trips), "legacy_rows": list(legacy)}


def status(rows, ledgers):
    return [r["status"] for r in pm.match(rows, ledgers)]


class PriceMatchTest(unittest.TestCase):
    def test_statuses_for_one_unique_target(self):
        self.assertEqual(status([sheet()], {"Khach gia A": book([trip()])}), ["READY"])
        self.assertEqual(status([sheet()], {"Khach gia A": book([trip()], locked=True)}), ["MONTH_LOCKED"])
        self.assertEqual(status([sheet()], {"Khach gia A": book([trip(price="50000000")])}), ["PRICE_UNCHANGED"])
        self.assertEqual(status([sheet(fee=0)], {"Khach gia A": book([trip(price="50000000")])}), ["PRICE_UNCHANGED"])
        self.assertEqual(status([sheet(fee=300)], {"Khach gia A": book([trip(price="50000000")])}), ["CONFLICT"])
        self.assertEqual(status([sheet()], {"Khach gia A": book([trip(price="49000000")])}), ["CONFLICT"])
        self.assertEqual(status([sheet()], {"Khach gia A": book([trip(status="pending_review")])}), ["PENDING_REVIEW"])
        self.assertEqual(status([sheet(price=None)], {"Khach gia A": book([trip()])}), ["SHEET_NO_PRICE"])
        self.assertEqual(status([sheet(fee=-500000)], {"Khach gia A": book([trip()])}), ["READY"])
        self.assertEqual(status([sheet(fee=-500000)], {"Khach gia A": book([trip() | {"has_typed_fee": True}])}), ["MANUAL"])

    def test_unmatched_and_ambiguous_rows_are_never_ready(self):
        self.assertEqual(status([sheet(container="")], {"Khach gia A": book([trip()])}), ["NO_CONTAINER"])
        self.assertEqual(status([sheet(tab="Khach khac")], {"Khach gia A": book([trip()])}), ["NO_CUSTOMER"])
        self.assertEqual(status([sheet(date="2026-09-01")], {"Khach gia A": book([trip()])}), ["NOT_FOUND"])
        self.assertEqual(status([sheet()], {"Khach gia A": book([trip(), trip(12)])}), ["AMBIGUOUS"])
        self.assertEqual(status([sheet(), sheet(6)], {"Khach gia A": book([trip()])}), ["AMBIGUOUS", "AMBIGUOUS"])
        self.assertEqual(status([sheet()], {"Khach gia A": book([trip(status="rejected")])}), ["NOT_FOUND"])

    def test_exact_date_wins_and_near_date_is_labelled(self):
        rows = pm.match([sheet()], {"Khach gia A": book([trip(), trip(12, date="2026-10-05")])})
        self.assertEqual((rows[0]["status"], rows[0]["match_basis"], rows[0]["target_id"]), ("READY", "exact_date", 11))
        rows = pm.match([sheet(date="2026-10-01")], {"Khach gia A": book([trip()])})
        self.assertEqual((rows[0]["status"], rows[0]["match_basis"]), ("READY", "near_date"))

    def test_original_book_rows_are_targets(self):
        legacy = {"id": 21, "kind": "trip", "month": "2026-10-01", "current": {
            "container": "FAKEU0000001", "event_date": "2026-10-03", "unit_price_vnd": None,
            "other_fee_vnd": None, "month": "2026-10-01", "deleted": False}}
        rows = pm.match([sheet()], {"Khach gia A": book(legacy=[legacy])})
        self.assertEqual((rows[0]["status"], rows[0]["target_kind"], rows[0]["target_id"]), ("READY", "legacy", 21))

    def test_alias_names_find_the_book_unless_shared(self):
        named = book([trip()]) | {"_display_name": "Khach gia A tren Sheet", "_aliases": ["KHACH A CU"]}
        rows = pm.match([sheet(tab="KHACH A CU")], {"Khach V7": named})
        self.assertEqual((rows[0]["status"], rows[0]["customer_basis"]), ("READY", "alias"))
        other = book([trip(21)]) | {"_aliases": ["KHACH A CU"]}
        self.assertEqual(status([sheet(tab="KHACH A CU")], {"Khach V7": named, "Khach khac": other}), ["NO_CUSTOMER"])
        self.assertEqual(status([sheet(tab="Khach V7")], {"Khach V7": named, "Khach khac": other}), ["READY"])

    def test_undated_sheet_row_uses_container_only_when_unique(self):
        rows = pm.match([sheet(date=None)], {"Khach gia A": book([trip(date="2026-10-03")])})
        self.assertEqual((rows[0]["status"], rows[0]["match_basis"]), ("READY", "container_only"))
        self.assertEqual(status([sheet(date=None)], {"Khach gia A": book([trip(), trip(12, date="2026-07-01")])}),
                         ["AMBIGUOUS"])
        priced = [trip(price="1"), trip(12, date="2026-07-01", price="2")]
        self.assertEqual(status([sheet(date=None)], {"Khach gia A": book(priced)}), ["AMBIGUOUS_PRICED"])
        # A dated Sheet row never falls back to container alone.
        self.assertEqual(status([sheet(date="2026-01-01")], {"Khach gia A": book([trip()])}), ["NOT_FOUND"])

    def test_undated_sheet_row_with_an_identical_undated_web_copy_asks_nothing(self):
        # GHEP-KHONG-NGAY-01. Đo trên `hao` 13/11/2026: container dùng lại nhiều chuyến, dòng Sheet không ngày đã có đúng bản sao
        # không ngày trong sổ gốc, nhưng một chuyến có ngày chưa giá làm cả dòng thành "khớp nhiều chuyến".
        def copy(row_id=21, price="50000000", counted="50000000"):
            return {"id": row_id, "kind": "trip", "month": "2026-06-01", "current": {
                "container": "FAKEU0000001", "event_date": None, "unit_price_vnd": price, "other_fee_vnd": None,
                "counted_vnd": counted, "month": "2026-06-01", "deleted": False}}

        def found(rows, ledger):
            return [(r["status"], r["target_id"]) for r in pm.match(rows, {"Khach gia A": ledger})]
        undated = sheet(date=None) | {"sheet_total_vnd": 50000000}
        second = undated | {"source_row": 6}
        later = [trip(), trip(12, date="2026-07-01", price="60000000")]   # cùng container, có ngày; một chuyến chưa giá
        rows = pm.match([undated], {"Khach gia A": book(later, [copy()])})
        self.assertEqual((rows[0]["status"], rows[0]["match_basis"], rows[0]["target_kind"], rows[0]["target_id"]),
                         ("PRICE_UNCHANGED", "undated_copy", "legacy", 21))
        # Chỉ bản sao giống hệt là ứng viên: dòng không ngày khác số hoặc chưa giá của cùng container không chen vào.
        self.assertEqual(found([undated], book(later, [copy(), copy(22, "49000000", "49000000")])), [("PRICE_UNCHANGED", 21)])
        self.assertEqual(found([undated], book(later, [copy(), copy(22, None, None)])), [("PRICE_UNCHANGED", 21)])
        # Hình đo được trên `hao`: hai dòng Sheet, hai bản sao, mỗi dòng đúng một bản (một có phụ phí, một không).
        with_fee = sheet(6, date=None, price=10500000, fee=840000) | {"sheet_total_vnd": 11340000}
        plain = sheet(7, date=None, price=10500000) | {"sheet_total_vnd": 10500000}
        pair = [copy(21, "10500000", "11340000"), copy(22, "10500000", "10500000")]
        self.assertEqual(found([with_fee, plain], book(later, pair)), [("PRICE_UNCHANGED", 21), ("PRICE_UNCHANGED", 22)])
        # Hai bản sao giống hệt nhau: không biết dòng nào của dòng nào, nhưng đều đã có giá nên không có gì để ghi.
        self.assertEqual(found([undated], book(later, [copy(), copy(22)])), [("AMBIGUOUS_PRICED", "")])
        # Không có bản sao giống hệt thì vẫn hỏi như cũ: khác đơn giá, khác tổng tính tiền, dòng web chưa giá,
        # Sheet thiếu TỔNG (trống không phải 0), Sheet trống giá.
        self.assertEqual(found([undated], book(later, [copy(price="49000000", counted="49000000")])), [("AMBIGUOUS", "")])
        self.assertEqual(found([undated], book(later, [copy(counted="50840000")])), [("AMBIGUOUS", "")])
        self.assertEqual(found([undated], book(later, [copy(price=None, counted=None)])), [("AMBIGUOUS", "")])
        self.assertEqual(found([sheet(date=None)], book(later, [copy()])), [("AMBIGUOUS", "")])
        self.assertEqual(found([sheet(date=None, price=None) | {"sheet_total_vnd": 50000000}], book(later, [copy()])),
                         [("AMBIGUOUS", "")])
        self.assertEqual(found([sheet(date=None, price=None) | {"sheet_total_vnd": 0}], book(later, [copy(price=None, counted="0")])),
                         [("AMBIGUOUS", "")])
        # Hai dòng Sheet cùng nhận một bản sao: một dòng thừa hoặc dòng web kia còn thiếu, vẫn hỏi cả hai.
        self.assertEqual(found([undated, second], book(later, [copy()])), [("AMBIGUOUS", 21), ("AMBIGUOUS", 21)])
        self.assertEqual(found([undated, second], book(later, [copy(), copy(22, "49000000", "49000000")])),
                         [("AMBIGUOUS", 21), ("AMBIGUOUS", 21)])
        # Luật cũ không hỏi (mọi ứng viên đã có giá) thì luật mới không chen vào: không câu hỏi nào mới hiện.
        priced = [trip(price="60000000"), trip(12, date="2026-07-01", price="60000000")]
        self.assertEqual(found([undated, second], book(priced, [copy()])), [("AMBIGUOUS_PRICED", ""), ("AMBIGUOUS_PRICED", "")])
        self.assertEqual(pm.match([undated], {"Khach gia A": book(priced, [copy()])})[0]["match_basis"], "container_only")
        # Dòng Sheet có ngày không dùng luật này.
        self.assertEqual(found([sheet() | {"sheet_total_vnd": 50000000}], book(later, [copy()])), [("READY", 11)])

    def test_fee_is_total_minus_unit_price_when_the_sheet_has_both(self):
        # Kiểm Sheet 3/11/2026: cột BAO HIEM, cột không tiêu đề, tiêu đề tiếng Trung không qua bộ quét "OTHER FEE";
        # TỔNG vẫn cộng chúng. GIA-NGUON-01: tổng phụ phí theo sổ gốc, nên phụ phí = TỔNG − đơn giá.
        self.assertEqual(pm.sheet_fee(85000000, 88365691, None), 3365691)
        self.assertEqual(pm.sheet_fee(45000000, 48600000, 3600000), 3600000)
        self.assertEqual(pm.sheet_fee(55000000, 22092549, None), -32907451)    # giảm trừ âm
        self.assertIsNone(pm.sheet_fee(45000000, 45000000, None))
        self.assertIsNone(pm.sheet_fee(45000000, 45000000, 1500000))           # phí ngoài công thức TỔNG: Sheet không tính
        self.assertEqual(pm.sheet_fee(None, 45000000, 1500000), 1500000)        # thiếu đơn giá: giữ số bộ quét đọc
        self.assertEqual(pm.sheet_fee(45000000, None, 1500000), 1500000)        # thiếu TỔNG: như trên
        scan = {"KHACH A": {"records": [
            {"kind": "trip", "row": 7, "month": "2026-10", "container": "FAKEU0000001", "date": "2026-10-03",
             "amount": 88365691, "details": {"unit_price": 85000000, "fee": None}},
            {"kind": "receipt", "row": 8, "month": "2026-10", "amount": 1000}]}}
        rows = pm.rows_from_scan(scan)
        self.assertEqual([(r["source_row"], r["sheet_unit_price_vnd"], r["sheet_other_fee_vnd"], r["sheet_total_vnd"])
                          for r in rows], [(7, 85000000, 3365691, 88365691)])

    def test_original_book_row_compares_charged_total_not_fee(self):
        legacy = {"id": 21, "kind": "trip", "month": "2026-10-01", "current": {
            "container": "FAKEU0000001", "event_date": "2026-10-03", "unit_price_vnd": "50000000",
            "other_fee_vnd": None, "counted_vnd": "49500000", "month": "2026-10-01", "deleted": False}}
        discounted = sheet(fee=-500000) | {"sheet_total_vnd": 49500000}
        self.assertEqual(status([discounted], {"Khach gia A": book(legacy=[legacy])}), ["PRICE_UNCHANGED"])
        self.assertEqual(status([discounted | {"sheet_total_vnd": 49000000}], {"Khach gia A": book(legacy=[legacy])}),
                         ["CONFLICT"])
        # Web trips still compare the fee itself.
        self.assertEqual(status([discounted], {"Khach gia A": book([trip(price="50000000")])}), ["CONFLICT"])

    def test_cli_reads_xlsx_and_writes_outside_repo_only(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source"
            source.mkdir()
            fixture(source)
            web = root / "web"
            web.mkdir()
            (web / f"{FAKE_NAME}.json").write_text(json.dumps(book([trip(container="FAKE-CONT-XY")])), encoding="utf-8")
            out = root / "out"
            code = pm.main(["--xlsx", str(source / "source-google-export.xlsx"), "--ledger-json", str(web), "--out", str(out)])
            self.assertEqual(code, 0)
            summary = json.loads((out / "summary.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["counts"]["READY"], 1)
            self.assertIn(str(FAKE_AMOUNT), (out / "price_match_rows.csv").read_text(encoding="utf-8-sig"))
            self.assertIn("Ghi được", (out / "price_match_report.html").read_text(encoding="utf-8"))
            self.assertEqual(pm.main(["--xlsx", str(source / "source-google-export.xlsx"),
                                      "--ledger-json", str(web), "--out", str(out)]), 2)
            self.assertEqual(pm.main(["--xlsx", str(source / "source-google-export.xlsx"),
                                      "--ledger-json", str(web), "--out", str(ROOT / "price-out")]), 2)


if __name__ == "__main__":
    unittest.main()
