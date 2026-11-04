"""Bù phụ phí theo ô TOTAL của Sheet ở dòng sổ gốc (PHU-PHI-BU-01). Dữ liệu giả."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "tools"))
sys.path.insert(0, str(Path(__file__).parents[1] / "web"))
import v7_fill_fee_gap as tool
from v7_api_validate import ApiError
from v7_ps_queue import GENERATED_NOTES

TYPES = {"other": 7, "discount": 8, "initial": 9}
FEE_TYPES = [{"id": 1, "name": "Neo", "system_key": None}, {"id": 7, "name": "Khác", "system_key": "other"},
             {"id": 8, "name": "Giảm trừ", "system_key": "discount"}, {"id": 9, "name": "Phụ phí ban đầu", "system_key": "initial"}]


def line(line_id, type_id, amount, note=None):
    return {"id": line_id, "fee_type_id": type_id, "amount_vnd": str(amount), "note": note}


def row(row_id=1, unit=90000000, counted=98500000, lines=None, cells=None, month="2026-06-01", differs=True, kind="trip"):
    cells = {"A": "2.0", "E": "46332.0", "H": "4000000.0", "K": "1500000.0", "L": "3000000.0", "M": "9.0E7", "N": "98500000"} if cells is None else cells
    return {"id": row_id, "kind": kind, "month": month, "counted_differs": differs, "fee_lines": lines if lines is not None else [line(50, 9, 4500000, "migration: legacy fee")],
            "display": {"cells": cells}, "current": {"unit_price_vnd": str(unit), "counted_vnd": str(counted), "deleted": False}}


class PlanRow(unittest.TestCase):
    def test_unlabeled_column_becomes_khac_and_initial_line_becomes_khac(self):
        plan = tool.plan_row(row(), TYPES)
        self.assertEqual(plan["status"], "READY")
        self.assertEqual(plan["gap_vnd"], 4000000)
        self.assertEqual(plan["expected_line_ids"], [50])
        self.assertEqual(plan["lines"], [{"fee_type_id": 7, "amount_vnd": "4500000", "note": None},
                                         {"fee_type_id": 7, "amount_vnd": "4000000", "note": tool.GAP_NOTE}])

    def test_total_stays_counted_minus_unit(self):
        plan = tool.plan_row(row(), TYPES)
        self.assertEqual(sum(int(x["amount_vnd"]) for x in plan["lines"]), 98500000 - 90000000)

    def test_negative_gap_goes_to_giam_tru(self):
        cells = {"H": "-4.719116E7", "J": "4.75E7", "K": "308840"}
        plan = tool.plan_row(row(unit=47500000, counted=308840, lines=[], cells=cells), TYPES)
        self.assertEqual(plan["status"], "READY")
        self.assertEqual(plan["lines"], [{"fee_type_id": 8, "amount_vnd": "-47191160", "note": tool.GAP_NOTE}])

    def test_several_unlabeled_columns_stay_one_line(self):
        cells = {"G": "1.0E7", "H": "1.2E7", "I": "4000000.0", "K": "8.5E7", "L": "111000000"}
        plan = tool.plan_row(row(unit=85000000, counted=111000000, lines=[], cells=cells), TYPES)
        self.assertEqual(plan["lines"], [{"fee_type_id": 7, "amount_vnd": "26000000", "note": tool.GAP_NOTE}])

    def test_typed_lines_and_real_notes_are_kept(self):
        lines = [line(1, 1, 1500000, "neo cang"), line(2, 9, 3000000, "ghi tay")]
        plan = tool.plan_row(row(lines=lines), TYPES)
        self.assertEqual(plan["lines"][:2], [{"fee_type_id": 1, "amount_vnd": "1500000", "note": "neo cang"},
                                             {"fee_type_id": 7, "amount_vnd": "3000000", "note": "ghi tay"}])

    def test_gap_the_cells_do_not_explain_is_left_alone(self):
        # TOTAL bị gõ khác: đơn giá + mọi ô tiền bên trái cột giá không ra TOTAL.
        cells = {"H": "1000000.0", "M": "9.0E7", "N": "98500000"}
        self.assertEqual(tool.plan_row(row(lines=[], cells=cells), TYPES)["status"], "UNEXPLAINED")

    def test_unit_price_not_in_cells_is_left_alone(self):
        cells = {"H": "4000000.0", "M": "8.0E7", "N": "98500000"}
        self.assertEqual(tool.plan_row(row(cells=cells), TYPES)["status"], "UNEXPLAINED")

    def test_date_serial_and_row_number_are_not_money(self):
        cells = {"A": "2.0", "E": "46332.0", "H": "8500000.0", "M": "9.0E7", "N": "98500000"}
        self.assertEqual(tool.plan_row(row(lines=[], cells=cells), TYPES)["status"], "READY")

    def test_text_cell_left_of_price_is_ignored(self):
        cells = {"F": "DAK NONG", "G": "1.5E7 tien", "H": "8500000.0", "M": "9.0E7", "N": "98500000"}
        self.assertEqual(tool.plan_row(row(lines=[], cells=cells), TYPES)["status"], "READY")

    def test_rows_that_need_nothing_return_none(self):
        self.assertIsNone(tool.plan_row(row(differs=False), TYPES))
        self.assertIsNone(tool.plan_row(row(kind="receipt"), TYPES))
        self.assertIsNone(tool.plan_row({**row(), "current": None}, TYPES))

    def test_gap_note_is_generated_so_the_ps_machine_can_still_split(self):
        self.assertIn(tool.GAP_NOTE, GENERATED_NOTES)


class Runner:
    """Sổ giả: `ledgers` theo id khách; ghi lại mọi lệnh; `fail` là id dòng trả lỗi."""

    def __init__(self, ledgers, fail=()):
        self.ledgers, self.fail, self.calls = ledgers, set(fail), []

    def run(self, function, payload, actor):
        self.calls.append((function, payload, actor))
        if function == "get_fee_types":
            return {"fee_types": FEE_TYPES}
        if function == "list_customers":
            return {"customers": [{"id": key} for key in self.ledgers]}
        if function == "get_ledger":
            return self.ledgers[payload["customer_id"]]
        ledger = self.ledgers[payload["customer_id"]]
        if function == "rewrite_trip_fees" and payload["target"]["legacy_row_id"] in self.fail:
            raise ApiError(409, "FEE_LINES_CHANGED", "x")
        ledger["version"] += 1
        return {"version": ledger["version"]}

    def writes(self):
        return [call for call in self.calls if call[0] in ("rewrite_trip_fees", "set_month_lock")]


def ledger(rows, locks=(), version=5):
    return {"version": version, "today_month": "2026-11-01", "month_locks": list(locks), "legacy_rows": rows}


class Run(unittest.TestCase):
    def test_dry_run_writes_nothing_and_counts(self):
        runner = Runner({1: ledger([row(1), row(2, cells={"M": "9.0E7"})])})
        result = tool.run(runner, apply=False)
        self.assertEqual(runner.writes(), [])
        self.assertEqual((result["ready"], result["unexplained"], result["written"]), (1, 1, 0))
        self.assertEqual(result["gap_abs_vnd"], 4000000)

    def test_apply_opens_locked_month_writes_and_relocks(self):
        runner = Runner({1: ledger([row(1), row(2)])})
        result = tool.run(runner, apply=True)
        self.assertEqual([call[0] for call in runner.writes()],
                         ["set_month_lock", "rewrite_trip_fees", "rewrite_trip_fees", "set_month_lock"])
        locks = [call[1]["locked"] for call in runner.writes() if call[0] == "set_month_lock"]
        self.assertEqual(locks, [False, True])
        self.assertEqual(result["written"], 2)
        command = runner.writes()[1][1]
        self.assertEqual(command["target"], {"legacy_row_id": 1})
        self.assertEqual(command["expected_line_ids"], [50])
        self.assertEqual(command["source"]["kind"], "sheet_total")
        self.assertEqual(runner.writes()[1][2], tool.ACTOR)

    def test_open_month_stays_open(self):
        runner = Runner({1: ledger([row(1)], locks=[{"month": "2026-06-01", "locked": False}])})
        tool.run(runner, apply=True)
        self.assertEqual([call[0] for call in runner.writes()], ["rewrite_trip_fees"])

    def test_each_month_is_opened_on_its_own(self):
        runner = Runner({1: ledger([row(1), row(2, month="2026-07-01")])})
        tool.run(runner, apply=True)
        months = [call[1]["month"] for call in runner.writes() if call[0] == "set_month_lock"]
        self.assertEqual(months, ["2026-06-01", "2026-06-01", "2026-07-01", "2026-07-01"])

    def test_failure_relocks_and_moves_to_next_customer(self):
        runner = Runner({1: ledger([row(1)]), 2: ledger([row(2)])}, fail={1})
        result = tool.run(runner, apply=True)
        self.assertEqual(result["errors"], {"FEE_LINES_CHANGED": 1})
        self.assertEqual(result["written"], 1)
        locks = [(call[1]["customer_id"], call[1]["locked"]) for call in runner.writes() if call[0] == "set_month_lock"]
        self.assertEqual(locks, [(1, False), (1, True), (2, False), (2, True)])

    def test_same_row_same_plan_uses_same_key(self):
        first, second = Runner({1: ledger([row(1)])}), Runner({1: ledger([row(1)])})
        tool.run(first, apply=True)
        tool.run(second, apply=True)
        keys = [[call[1]["idempotency_key"] for call in r.writes() if call[0] == "rewrite_trip_fees"] for r in (first, second)]
        self.assertEqual(keys[0], keys[1])

    def test_customers_can_be_limited(self):
        runner = Runner({1: ledger([row(1)]), 2: ledger([row(2)])})
        result = tool.run(runner, apply=False, customers=[2])
        self.assertEqual(result["ready"], 1)
        self.assertEqual([call[1]["customer_id"] for call in runner.calls if call[0] == "get_ledger"], [2])


if __name__ == "__main__":
    unittest.main()
