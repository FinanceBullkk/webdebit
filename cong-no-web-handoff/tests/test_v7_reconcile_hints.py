"""Máy đoán chỗ gây lệch (CHAN-DOAN-LECH-01): bốn kiểu gặp ngày 9/11/2026, dữ liệu giả, không cần DB."""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "web"))
import v7_reconcile_hints as hints  # noqa: E402

TAB = "KHACH GIA"


def receipt(pid, date, amount, **extra):
    return {"pid": pid, "date": date, "amount_vnd": str(amount), "voided_on": None, "offset_pair_id": None, **extra}


def ledger(receipts=(), legacy=()):
    return {"customer_id": 7, "receipts": list(receipts), "trips": [], "month_locks": [], "legacy_rows": list(legacy)}


def legacy_row(row_id, container, date, price, fee, counted):
    return {"id": row_id, "kind": "trip", "month": date[:7] + "-01",
            "current": {"container": container, "event_date": date, "debt_month": date[:7] + "-01", "deleted": False,
                        "unit_price_vnd": str(price), "other_fee_vnd": str(fee), "counted_vnd": str(counted)},
            "display": {"container": container, "date": date}, "fee_lines": [{"id": 1, "amount_vnd": str(fee), "fee_type_id": 1}],
            "has_typed_fee": True}


def sheet_row(row, container, date, price, fee, total):
    return {"customer_tab": TAB, "source_row": row, "debt_month": "2026-10", "container": container, "date": date,
            "sheet_unit_price_vnd": price, "sheet_other_fee_vnd": fee, "sheet_total_vnd": total}


class ReceiptTwiceTest(unittest.TestCase):
    def test_same_day_same_amount_is_named_once_with_both_slips(self):
        found = hints.receipt_twice(ledger([receipt("PH-001", "2026-10-31", 8300000), receipt("PH-002", "2026-10-31", 8300000)]))
        self.assertEqual(found, [{"kind": "receipt_twice", "date": "2026-10-31", "amount_vnd": 8300000,
                                  "pids": ["PH-001", "PH-002"], "delta_vnd": 8300000}])

    def test_two_payments_the_sheet_also_has_twice_are_not_twins(self):
        web = ledger([receipt("PH-001", "2026-10-15", 10500000), receipt("PH-002", "2026-10-15", 10500000)])
        sheet = [{"customer_tab": TAB, "source_row": n, "amount_vnd": 10500000} for n in (40, 41)]
        self.assertEqual(hints.receipt_twice(web, sheet), [])
        self.assertEqual(len(hints.receipt_twice(web, sheet[:1])), 1)   # Sheet chỉ còn một dòng: vẫn báo

    def test_voided_offset_or_different_day_is_not_a_twin(self):
        rows = [receipt("PH-001", "2026-10-31", 500), receipt("PH-002", "2026-10-31", 500, voided_on="2026-11-09"),
                receipt("PH-003", "2026-10-30", 500), receipt("PH-004", "2026-10-31", 500, offset_pair_id=3)]
        self.assertEqual(hints.receipt_twice(ledger(rows)), [])


class PriceRowsTest(unittest.TestCase):
    def test_row_needing_a_person_is_named_with_both_totals(self):
        web = ledger(legacy=[legacy_row(6805, "MAUU0000231", "2026-10-03", 95000000, 3000000, 98000000)])
        rows = [sheet_row(231, "MAUU0000231", "2026-10-03", 95000000, 6500000, 101500000)]
        self.assertEqual(hints.price_rows(rows, web), [{"kind": "price_review", "status": "MANUAL", "row": 231, "container": "MAUU0000231",
                                                        "date": "2026-10-03", "sheet_vnd": 101500000, "web_vnd": 98000000, "delta_vnd": 3500000}])

    def test_sheet_row_with_money_and_no_web_row_is_named(self):
        rows = [sheet_row(284, "MAUU0000284 取消", None, 7700000, None, 7700000)]
        found = hints.price_rows(rows, ledger())
        self.assertEqual([(h["kind"], h["row"], h["delta_vnd"]) for h in found], [("sheet_row_missing", 284, 7700000)])

    def test_rows_without_money_or_already_equal_say_nothing(self):
        web = ledger(legacy=[legacy_row(1, "AAAU1234567", "2026-10-03", 90, 0, 90)])
        rows = [sheet_row(10, "AAAU1234567", "2026-10-03", 90, None, 90), sheet_row(11, "BBBU1234567", None, None, None, None),
                sheet_row(12, "", None, 5, None, 5)]
        self.assertEqual(hints.price_rows(rows, web), [])


class ForBookTest(unittest.TestCase):
    def test_two_hints_that_add_up_to_the_gap_explain_it(self):
        web = ledger([receipt("PH-001", "2026-10-31", 8300000), receipt("PH-002", "2026-10-31", 8300000)])
        rows = [sheet_row(284, "MAUU0000284 取消", None, 7700000, None, 7700000)]
        found, explained = hints.for_book(web, rows, 16000000)
        self.assertEqual(([h["kind"] for h in found], explained), (["receipt_twice", "sheet_row_missing"], True))
        self.assertEqual(hints.for_book(web, rows, 16033040)[1], False)   # lệch 1 đồng là không giải thích được

    def test_nothing_found_is_empty(self):
        self.assertEqual(hints.for_book(ledger(), [], 5), ([], False))


class ChainBreakTest(unittest.TestCase):
    def test_first_month_whose_sheet_end_differs_is_named(self):
        checks = [{"debt_month": "2026-09-01", "source_cumulative_vnd": 500, "replay_cumulative_vnd": 500},
                  {"debt_month": "2026-10-01", "source_cumulative_vnd": 95000000, "replay_cumulative_vnd": 95000500},
                  {"debt_month": "2026-11-01", "source_cumulative_vnd": 1, "replay_cumulative_vnd": 2}]
        self.assertEqual(hints.chain_break(checks), {"kind": "chain_break", "month": "2026-10", "sheet_end_vnd": 95000000,
                                                     "expected_end_vnd": 95000500, "delta_vnd": -500})

    def test_unknown_or_matching_months_are_no_break(self):
        self.assertIsNone(hints.chain_break([{"debt_month": "2026-10-01", "source_cumulative_vnd": None, "replay_cumulative_vnd": 4},
                                             {"debt_month": "2026-11-01", "source_cumulative_vnd": 4, "replay_cumulative_vnd": 4}]))

    def test_money_leaves_as_exact_strings(self):
        self.assertEqual(hints.money_fields({"kind": "x", "delta_vnd": -500, "month": "2026-10"}),
                         {"kind": "x", "delta_vnd": "-500", "month": "2026-10"})


if __name__ == "__main__":
    unittest.main()
