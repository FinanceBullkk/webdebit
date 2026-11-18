"""Mô hình tham chiếu phân bổ thu (FIFO-NGAU-NHIEN): ví dụ tính tay, dữ liệu giả, không cần DB.

Harness `tools/test_pg_v7_fifo_ngau_nhien.py` dùng mô hình này làm chuẩn so với PostgreSQL, nên chính mô hình phải
được khóa bằng số tính tay trước (specs/v7-fifo-ngau-nhien.md).
"""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from v7_fifo_model import ADVANCE, DEBT, Book, Trip, canonical  # noqa: E402

JAN, FEB, MAR, NOW = "2026-01-01", "2026-02-01", "2026-03-01", "2026-11-01"


class FifoModelTest(unittest.TestCase):
    def test_orders_by_receipt_day_then_pid_and_reports_changed(self):
        book = Book({JAN: 100, FEB: 100})
        self.assertEqual(book.record_receipt("PH-001", "2026-01-10", 100, "THU TIỀN"), [])
        self.assertEqual(book.receipts["PH-001"].lines, [(JAN, DEBT, 100)])
        # Phiếu sau có ngày sớm hơn: lấy nợ tháng 1 trước, phiếu cũ dời sang tháng 2 và dư thành ứng trước.
        self.assertEqual(book.record_receipt("PH-002", "2026-01-05", 150, "THU TIỀN"), ["PH-002", "PH-001"])
        self.assertEqual(book.receipts["PH-002"].lines, [(JAN, DEBT, 100), (FEB, DEBT, 50)])
        self.assertEqual(book.receipts["PH-001"].lines, [(FEB, DEBT, 50), (FEB, ADVANCE, 50)])
        self.assertEqual((book.version, book.total()), (2, -50))

    def test_negative_months_are_skipped_and_advance_goes_to_last_month(self):
        book = Book({JAN: -50, FEB: 30, MAR: 0})
        book.record_receipt("PH-001", "2026-02-01", 100, "KHÁC")
        self.assertEqual(book.receipts["PH-001"].lines, [(FEB, DEBT, 30), (MAR, ADVANCE, 70)])
        self.assertEqual(book.outstanding(), {JAN: 0, FEB: 0, MAR: -120})

    def test_unpriced_trip_keeps_its_month_but_adds_no_money(self):
        book = Book({JAN: 10})
        book.paste([Trip(7, MAR, "2026-03-04", True, None, 25)])
        self.assertEqual((book.charge_months(), book.charges()), ([JAN, MAR], {JAN: 10, MAR: 0}))
        book.record_receipt("PH-001", "2026-03-02", 40, "THU TIỀN")
        self.assertEqual(book.receipts["PH-001"].lines, [(JAN, DEBT, 10), (MAR, ADVANCE, 30)])
        self.assertEqual(book.ledger_months(), [(JAN, 0, 10, 0, 10), (MAR, -30, 0, 40, -30)])
        self.assertEqual(book.edit_price(7, 100, 25), ["PH-001"])
        self.assertEqual(book.receipts["PH-001"].lines, [(JAN, DEBT, 10), (MAR, DEBT, 30)])
        self.assertEqual(book.total(), 95)

    def test_trip_amount_null_is_not_zero(self):
        self.assertEqual(Trip(1, FEB, None, False, None, -20).amount, -20)
        self.assertIsNone(Trip(2, FEB, None, False, None, None).amount)
        self.assertIsNone(Trip(3, FEB, "2026-02-02", True, None, 5).amount)
        self.assertEqual(Trip(4, FEB, "2026-02-02", True, 0, None).amount, 0)

    def test_void_keeps_other_receipts_until_next_reallocation(self):
        book = Book({JAN: 100})
        book.record_receipt("PH-001", "2026-01-02", 60, "THU TIỀN")
        book.record_receipt("PH-002", "2026-01-03", 60, "THU TIỀN")
        before = list(book.receipts["PH-002"].lines)
        self.assertEqual(before, [(JAN, DEBT, 40), (JAN, ADVANCE, 20)])
        self.assertEqual(book.void("PH-001"), 1)
        self.assertEqual((book.receipts["PH-001"].lines, book.receipts["PH-002"].lines), ([], before))
        self.assertEqual(book.total(), 40)
        self.assertEqual(book.adjust(5, JAN, 1), ["PH-002"])
        self.assertEqual(book.receipts["PH-002"].lines, [(JAN, DEBT, 60)])

    def test_next_pid_counts_voided_receipts(self):
        book = Book({JAN: 100})
        book.record_receipt("PH-001", "2026-01-02", 10, "THU TIỀN")
        book.record_receipt("PH-002", "2026-01-02", 10, "THU TIỀN")
        book.void("PH-002")
        self.assertEqual(book.next_pid(), "PH-003")

    def test_can_du_moves_credit_to_oldest_debt_then_last_month(self):
        self.assertEqual(Book({JAN: 100, FEB: -30, MAR: 50}).outstanding(), {JAN: 70, FEB: 0, MAR: 50})
        self.assertEqual(Book({JAN: 20, FEB: -50}).outstanding(), {JAN: 0, FEB: -30})

    def test_ledger_end_of_month_counts_receipts_by_receipt_day(self):
        book = Book({JAN: 100})
        book.record_receipt("PH-001", "2026-02-10", 30, "THU TIỀN")
        self.assertEqual(book.receipts["PH-001"].lines, [(JAN, DEBT, 30)])
        self.assertEqual(book.ledger_months(), [(JAN, 70, 100, 0, 100), (FEB, 0, 0, 30, 70)])

    def test_months_appear_and_disappear_with_their_rows(self):
        book = Book({}, open_months=[FEB], current_month=NOW)
        self.assertEqual(book.expect_receipt(), "NO_MONTH_FOR_RECEIPT")
        self.assertEqual(book.expect_adjust(FEB), "MONTH_NOT_FOUND")
        book.paste([Trip(1, FEB, "2026-02-03", True, 100, None)])
        book.adjust(2, FEB, -30)
        book.delete_trip(1)
        self.assertEqual(book.charge_months(), [FEB])
        book.delete_adjustment(2)
        self.assertEqual((book.charge_months(), book.expect_adjust(FEB)), ([], "MONTH_NOT_FOUND"))
        self.assertEqual(book.expect_delete_adjustment(2), "ADJUSTMENT_NOT_FOUND")

    def test_trip_rejections_follow_sql_check_order(self):
        book = Book({JAN: 0}, open_months=[JAN], current_month=NOW)
        book.paste([Trip(3, JAN, "2026-01-05", True, 100, None)])
        self.assertEqual((book.expect_price(3, 100, None), book.expect_price(3, 100, 5)), ("NO_CHANGE", None))
        book.set_lock(JAN, True)
        self.assertEqual((book.expect_price(3, 100, None), book.expect_move(3, "2026-01-05")), ("MONTH_LOCKED",) * 2)
        book.set_lock(JAN, False)
        self.assertEqual(book.expect_move(3, "2026-01-05"), "NO_CHANGE")
        self.assertEqual(book.expect_move(3, "2026-02-05"), "MONTH_LOCKED")  # tháng chưa có dòng khóa thì khóa
        self.assertFalse(book.locked(NOW))
        book.delete_trip(3)
        book.set_lock(JAN, True)
        self.assertEqual(book.expect_price(3, 1, None), "TRIP_NOT_FOUND")
        self.assertEqual(book.version, 5)

    def test_undated_fee_only_row_must_stay_fee_only(self):
        book = Book({JAN: 0}, open_months=[FEB], current_month=NOW)
        book.paste([Trip(4, FEB, None, False, None, -20), Trip(5, FEB, "2026-02-03", False, None, -20)])
        self.assertEqual(book.expect_price(4, 10, -20), "INVALID_FEE_ONLY_DATE")
        self.assertEqual(book.expect_price(4, None, None), "INVALID_FEE_ONLY_DATE")
        self.assertIsNone(book.expect_price(4, None, 30))
        self.assertIsNone(book.expect_price(5, 10, None))  # có ngày thì được thêm đơn giá
        self.assertEqual(book.expect_price(4, None, -20), "NO_CHANGE")

    def test_receipt_edit_reallocates_only_when_day_changes(self):
        book = Book({JAN: 100, FEB: 100})
        book.record_receipt("PH-001", "2026-01-10", 100, "THU TIỀN")
        book.record_receipt("PH-002", "2026-01-20", 50, "THU TIỀN")
        self.assertEqual(book.expect_receipt_edit("PH-002", "2026-01-20", None), "NO_CHANGE")
        self.assertEqual(book.edit_receipt("PH-002", None, "KHÁC"), [])
        self.assertEqual(book.edit_receipt("PH-002", "2026-01-05", None), ["PH-002", "PH-001"])
        self.assertEqual(book.receipts["PH-001"].lines, [(JAN, DEBT, 50), (FEB, DEBT, 50)])
        book.void("PH-002")
        self.assertEqual(book.expect_receipt_edit("PH-002", None, "KHÁC"), "RECEIPT_NOT_FOUND")
        self.assertEqual(book.expect_void("PH-002"), "RECEIPT_ALREADY_VOID")

    def test_canonical_puts_debt_before_advance_in_a_month(self):
        lines = [(FEB, ADVANCE, 5), (FEB, DEBT, 3), (JAN, ADVANCE, 1)]
        self.assertEqual(canonical(lines), [(JAN, ADVANCE, 1), (FEB, DEBT, 3), (FEB, ADVANCE, 5)])


if __name__ == "__main__":
    unittest.main()
