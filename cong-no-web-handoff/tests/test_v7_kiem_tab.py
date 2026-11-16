"""KIEM-TAB-01 đợt 1 (specs/v7-kiem-tab-truoc-khi-ghi.md, K1): kết luận sức khỏe tab và chặn ghi tiền khi tab không lành.

Ca thật 16/11/2026 (sổ 239): tiền nằm lệch một dòng dưới container, bảng đối chiếu đề xuất hai dòng điều chỉnh và người dùng bấm ghi.
Fixture giả: tên khách, container và số tiền bịa.
"""
import datetime as dt
import sys
import unittest
from pathlib import Path
from typing import ClassVar

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "web"))
sys.path.insert(0, str(ROOT / "tools"))
import v7_load_real_copy as loader  # noqa: E402
import v7_price_snapshot as snapshots  # noqa: E402
import v7_reconcile_auto as job  # noqa: E402
import v7_sheet_fix as fix  # noqa: E402
from v7_api_validate import ApiError  # noqa: E402

TODAY = dt.date(2026, 11, 16)
HEADERS = ["Marks & Nos", "CONTAINER NO", "DATE", "UNIT PRICE", "OTHER FEE", "TOTAL(VND)", "NGAY TT(STK)",
           "SỐ ĐÃ ỨNG TRƯỚC/ĐÃ THU TRONG THÁNG", "SỐ CÒN PHẢI THU CUỐI THÁNG"]
TAB = "KHACH GIA"


def header_rows():
    return [(1, {"A": "THÁNG 10/2026"}), (2, {loader.col_name(n): h for n, h in enumerate(HEADERS, 1)})]


def trip(row, container="", total="", price="", day="03/10/2026"):
    cells = {"A": str(row - 2), "B": container, "C": day if container else "", "D": price, "F": total}
    return (row, {col: value for col, value in cells.items() if value != ""})


def scan(*rows, tab=TAB):
    return loader.scan_tabs([(tab, header_rows() + list(rows))])[tab]


class RowShiftTests(unittest.TestCase):
    def test_money_one_row_below_its_container_is_broken_and_names_both_cells(self):
        health = scan(trip(3, "MAUU0000001"), trip(4, total="44710920", price="44710920"),
                      trip(5, "MAUU0000002"), trip(6, total="42546330", price="42546330"))["health"]
        self.assertEqual(health["status"], "broken")
        shifts = [f for f in health["findings"] if f["kind"] == "row_shift"]
        self.assertEqual([(f["rows"], f["cells"], f["month"]) for f in shifts],
                         [([3, 4], ["B3", "F4"], "2026-10"), ([5, 6], ["B5", "F6"], "2026-10")])
        self.assertIn("lệch một dòng", shifts[0]["message"])
        self.assertTrue(shifts[0]["fix"])

    def test_money_row_above_a_container_without_money_is_also_a_shift(self):
        health = scan(trip(3, total="5000000", price="5000000"), trip(4, "MAUU0000001"))["health"]
        shifts = [f for f in health["findings"] if f["kind"] == "row_shift"]
        self.assertEqual([(f["rows"], f["cells"]) for f in shifts], [([3, 4], ["B4", "F3"])])

    def test_one_row_is_never_in_two_pairs(self):
        health = scan(trip(3, "MAUU0000001"), trip(4, total="1000"), trip(5, "MAUU0000002"))["health"]
        self.assertEqual([f["rows"] for f in health["findings"] if f["kind"] == "row_shift"], [[3, 4]])

    def test_fee_row_alone_or_next_to_a_priced_container_is_not_a_shift(self):
        health = scan(trip(3, "MAUU0000001", total="30000000", price="30000000"), trip(4, total="150000"),
                      trip(5, "MAUU0000002", total="31000000", price="31000000"))["health"]
        self.assertEqual([f for f in health["findings"] if f["kind"] == "row_shift"], [])

    def test_rows_that_are_not_next_to_each_other_are_not_a_pair(self):
        health = scan(trip(3, "MAUU0000001"), trip(5, total="44710920"))["health"]
        self.assertEqual([f for f in health["findings"] if f["kind"] == "row_shift"], [])

    def test_scanner_issues_make_a_tab_broken_with_their_codes(self):
        data = loader.scan_tabs([(TAB, header_rows() + [(3, {"A": "1", "B": "MAUU0000001", "C": "03/10/2026", "D": "100", "F": ""})])])[TAB]
        self.assertEqual(data["issues"]["MISSING_TRIP_AMOUNT"], 1)
        self.assertEqual(data["health"]["status"], "broken")
        self.assertIn({"kind": "MISSING_TRIP_AMOUNT", "level": "error", "count": 1}, data["health"]["findings"])

    def test_clean_tab_is_ok(self):
        health = scan(trip(3, "MAUU0000001", total="30000000", price="30000000"))["health"]
        self.assertEqual(health["status"], "ok", health["findings"])
        self.assertEqual(health["findings"], [])


def pairs(first, count, container_first=True, price="40000000"):
    """`count` cặp hai dòng bắt đầu ở dòng `first`: container không tiền rồi tiền không container (hoặc ngược lại)."""
    rows = []
    for index in range(count):
        at = first + 2 * index
        holder, money = trip(at, f"MAUU{at:07d}"), trip(at + 1, total=price, price=price)
        rows += [holder, money] if container_first else [trip(at, total=price, price=price), trip(at + 1, f"MAUU{at:07d}")]
    return rows


class ApprovedLayoutTests(unittest.TestCase):
    """Tab "KK - DỪA" được duyệt bố cục hai dòng/cont; tab khác, hoặc khối không đều, vẫn bị chặn (quyết 16/11/2026)."""
    APPROVED = "KK - DỪA"

    def kinds(self, health):
        return sorted({f["kind"] for f in health["findings"]})

    def test_approved_tab_with_a_regular_block_is_ok_and_keeps_notes(self):
        health = scan(*pairs(3, 5), tab=self.APPROVED)["health"]
        self.assertEqual((health["status"], self.kinds(health)), ("ok", ["two_row_layout"]))
        self.assertEqual({f["level"] for f in health["findings"]}, {"note"})
        self.assertIn("đã duyệt", health["findings"][0]["message"])

    def test_the_name_is_matched_the_way_tab_names_always_are(self):
        self.assertEqual(scan(*pairs(3, 3), tab="kk - dua")["health"]["status"], "ok")

    def test_approved_tab_with_a_one_row_trip_between_pairs_stays_regular(self):
        rows = pairs(3, 2) + [trip(7, "MAUU9999999", total="1000", price="1000")] + pairs(8, 2)
        self.assertEqual(scan(*rows, tab=self.APPROVED)["health"]["status"], "ok")

    def test_approved_tab_with_a_block_shifted_the_other_way_is_broken(self):
        health = scan(*pairs(3, 2), *pairs(8, 1, container_first=False), tab=self.APPROVED)["health"]
        self.assertEqual(health["status"], "broken")
        self.assertEqual(self.kinds(health), ["row_shift"])   # cả ba cặp của khối, kể cả hai cặp thường
        self.assertEqual(len(health["findings"]), 3)

    def test_other_tab_with_three_or_more_shifted_pairs_is_broken(self):
        health = scan(*pairs(3, 4))["health"]
        self.assertEqual((health["status"], self.kinds(health), len(health["findings"])), ("broken", ["row_shift"], 4))

    def test_issues_still_block_an_approved_tab(self):
        rows = pairs(3, 2) + [(9, {"A": "7", "B": "MAUU0000099", "C": "03/10/2026", "D": "100"})]
        health = scan(*rows, tab=self.APPROVED)["health"]
        self.assertEqual(health["status"], "broken")
        self.assertIn("MISSING_TRIP_AMOUNT", self.kinds(health))

    def test_fee_row_under_a_priced_trip_does_not_pair_with_the_next_container(self):
        rows = [trip(3, "MAUU0000001", total="30000000", price="30000000"), trip(4, total="150000"), trip(5, "MAUU0000002")]
        self.assertEqual([f for f in scan(*rows)["health"]["findings"] if f["kind"] == "row_shift"], [])


class SnapshotTests(unittest.TestCase):
    def test_both_snapshots_carry_the_tabs_health_and_the_hash_stays_on_rows(self):
        data = loader.scan_tabs([(TAB, header_rows() + [trip(3, "MAUU0000001"), trip(4, total="44710920", price="44710920")])])
        prices, receipts = snapshots.snapshots(data, {"kind": "test"})
        for snap in (prices, receipts):
            self.assertEqual(snap["tabs"][TAB]["status"], "broken")
            self.assertEqual(snap["tabs"][TAB]["findings"][0]["kind"], "row_shift")
        plain = snapshots.snapshot(prices["rows"], {"kind": "test"})
        self.assertNotIn("tabs", plain)
        self.assertEqual(plain["sha256"], prices["sha256"])


CUSTOMERS = ({"id": 7, "name": TAB},)
SHIFT = {"kind": "row_shift", "level": "error", "month": "2026-10", "rows": [3, 4], "cells": ["B3", "F4"], "message": "m", "fix": "f"}


def fee_row(source_row, total, month="2026-10"):
    return {"customer_tab": TAB, "source_row": source_row, "debt_month": month, "container": "", "date": month + "-01",
            "sheet_unit_price_vnd": total, "sheet_other_fee_vnd": None, "sheet_total_vnd": total}


def ledger():
    return {"customer_id": 7, "version": 9, "today_month": "2026-11-01", "trips": [], "legacy_rows": [], "adjustments": [],
            "month_locks": [], "receipts": [], "events": []}


def snapshot(*rows, tabs=None):
    return {"rows": list(rows), "sha256": "a" * 64, **({"tabs": tabs} if tabs is not None else {})}


def broken_tabs():
    return {TAB: {"status": "broken", "findings": [SHIFT]}}


class PlanBlockTests(unittest.TestCase):
    ROWS = (fee_row(4, 44710920), fee_row(6, 42546330))
    RECEIPTS: ClassVar[dict] = {"rows": [], "sha256": "b" * 64}

    def test_the_fee_rows_the_old_plan_proposed_are_there_for_a_healthy_tab(self):
        groups, _, _ = fix.plan(snapshot(*self.ROWS, tabs={TAB: {"status": "ok", "findings": []}}), self.RECEIPTS, ledger(), list(CUSTOMERS), TODAY)
        self.assertEqual([(g["kind"], g["delta_vnd"]) for g in groups], [("fee_rows", 44710920 + 42546330)])

    def test_broken_tab_gives_no_group_at_all(self):
        groups, ahead, shuffled = fix.plan(snapshot(*self.ROWS, tabs=broken_tabs()), self.RECEIPTS, ledger(), list(CUSTOMERS), TODAY)
        self.assertEqual((groups, ahead, shuffled), ([], 0, []))

    def test_old_snapshot_without_tabs_means_no_verdict(self):
        groups, _, _ = fix.plan(snapshot(*self.ROWS), self.RECEIPTS, ledger(), list(CUSTOMERS), TODAY)
        self.assertEqual(len(groups), 1)

    def test_health_only_counts_tabs_of_this_book(self):
        other = {"Tab khac": {"status": "broken", "findings": [SHIFT]}}
        self.assertEqual(fix.customer_health(snapshot(tabs=other), ledger(), list(CUSTOMERS))["status"], "ok")
        health = fix.customer_health(snapshot(tabs=broken_tabs()), ledger(), list(CUSTOMERS))
        self.assertEqual((health["status"], health["findings"][0]["tab"], health["findings"][0]["cells"]), ("broken", TAB, ["B3", "F4"]))
        note = {"KHACH GIA": {"status": "broken", "findings": [SHIFT, {"kind": "two_row_layout", "level": "note"}]}}
        self.assertEqual(len(fix.customer_health(snapshot(tabs=note), ledger(), list(CUSTOMERS))["findings"]), 1)   # chú thích không vào lý do chặn


class Db:
    def __init__(self):
        self.calls = []

    def run(self, function, payload, actor):
        self.calls.append(function)
        if function == "get_ledger":
            return ledger() | {"total_outstanding_vnd": "100"}
        return {"version": 10}


class ApplyBlockTests(unittest.TestCase):
    def test_apply_fix_refuses_a_broken_tab_before_any_command(self):
        db = Db()
        group = {"kind": "fee_rows", "month": "2026-11", "delta_vnd": 43, "rows": [{"source_row": 4, "amount_vnd": "43"}]}
        health = fix.customer_health(snapshot(tabs=broken_tabs()), ledger(), list(CUSTOMERS))
        with self.assertRaises(ApiError) as caught:
            fix.apply_fix(db, 7, {"version": 9, "today_month": "2026-11-01", "month_locks": []}, [group], "d" * 64, TODAY, actor="x", health=health)
        self.assertEqual((caught.exception.status, caught.exception.code), (409, "TAB_BROKEN"))
        self.assertEqual(db.calls, [])


class MachineTests(unittest.TestCase):
    def test_machine_holds_a_book_whose_tab_has_a_shift_even_when_no_issue_was_counted(self):
        db, row = Db(), {"customer": TAB, "sheet_total_vnd": 50}
        job.settle(db, row, 7, list(CUSTOMERS), snapshot(*PlanBlockTests.ROWS, tabs=broken_tabs()), PlanBlockTests.RECEIPTS, TODAY, write=True)
        self.assertEqual((row["reason"], row["held_reasons"]), ("HELD", {"ROW_SHIFT": 1}))
        self.assertEqual(db.calls, ["get_ledger"])


if __name__ == "__main__":
    unittest.main()
