"""Tách phụ phí theo tên cột trên tab khách (TACH-PHI-TIEU-DE-01). Dữ liệu giả."""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "web"))
import v7_split_fee_by_header as tool  # noqa: E402

TYPES = [{"id": 1, "name": "Khác", "system_key": "other", "active": True},
         {"id": 2, "name": "Giảm trừ", "system_key": "discount", "active": True},
         {"id": 3, "name": "Phụ phí ban đầu", "system_key": "initial", "active": True},
         {"id": 4, "name": "Neo", "system_key": None, "active": True},
         {"id": 5, "name": "Điện", "system_key": None, "active": True},
         {"id": 6, "name": "Ghép", "system_key": None, "active": True},
         {"id": 7, "name": "Bảo hiểm", "system_key": None, "active": True},
         {"id": 8, "name": "Health cert", "system_key": None, "active": True},
         {"id": 10, "name": "Health + KĐ", "system_key": None, "active": True},
         {"id": 11, "name": "Cân hàng", "system_key": None, "active": True},
         {"id": 12, "name": "Local charge", "system_key": None, "active": True},
         {"id": 13, "name": "Phí hủy", "system_key": None, "active": True}]
HEADER = {"A": "Marks & Nos", "B": "CONTAINER NO", "C": "DATE", "D": "FROM", "E": "TO", "F": "开发电器", "G": "卫生证",
          "H": "PHÍ NEO\n押车费", "I": "PHÍ GHÉP KHO\n拼柜", "J": "BAO HIEM", "K": "", "L": "UNIT PRICE", "M": "TOTAL(VND)",
          "N": "NGAY TT(STK)", "O": "SỐ ĐÃ ỨNG TRƯỚC/ĐÃ THU TRONG THÁNG", "P": "SỐ CÒN PHẢI THU CUỐI THÁNG"}


def trip_row(stt, container, day, total, **fees):
    cells = {"A": str(stt), "B": container, "C": day, "D": "DAK LAK", "E": "QINGDAO", "L": "85000000", "M": str(total)}
    return cells | {col: str(value) for col, value in fees.items()}


def tab(*trips):
    rows = [(1, {"A": "THÁNG 10/2026"}), (2, dict(HEADER))]
    rows += [(3 + i, cells) for i, cells in enumerate(trips)]
    return [("KHACH A", rows)]


def fee_line(line_id, type_id, amount, note=None):
    return {"id": line_id, "fee_type_id": type_id, "amount_vnd": str(amount), "note": note}


def trip(trip_id, container, day, lines, month="2026-10-01"):
    return {"id": trip_id, "container": container, "event_date": day, "unit_price_vnd": "85000000",
            "other_fee_vnd": str(sum(int(x["amount_vnd"]) for x in lines)) if lines else None, "status": "confirmed",
            "month": month, "deleted": False, "booking": "", "fee_lines": list(lines)}


class Runner:
    def __init__(self, trips, locked=(), columns=(10,)):
        self.version, self.calls = 3, []
        self.trips = trips
        self.locks = dict.fromkeys(locked, True)
        self.columns = list(columns)

    def run(self, command, payload, actor):
        self.calls.append((command, payload))
        if command == "get_fee_types":
            return {"fee_types": TYPES}
        if command == "list_customers":
            return {"customers": [{"id": 7, "name": "KHACH A"}]}
        if command == "get_ledger":
            locks = [{"month": "2026-10-01", "locked": self.locks.get("2026-10", False)}]
            return {"customer_id": 7, "version": self.version, "today_month": "2026-10-01", "month_locks": locks,
                    "trips": self.trips, "legacy_rows": [],
                    "fee_columns": [{"fee_type_id": t, "position": i + 1} for i, t in enumerate(self.columns)]}
        if command == "set_book_fee_columns":
            self.columns = list(payload["fee_type_ids"])
            self.version += 1
            return {"version": self.version}
        if command in ("rewrite_trip_fees", "set_month_lock"):
            self.version += 1
            return {"version": self.version}
        raise AssertionError(command)


ROW2 = trip_row(2, "FAKEU0000002", "03/10/2026", 97865691, G=3500000, H=2000000, I=4000000, J="3365691")


class FieldOf(unittest.TestCase):
    def test_named_headers(self):
        self.assertEqual(tool.field_of("PHÍ NEO\n押车费"), "neo")
        self.assertEqual(tool.field_of("PHÍ GHÉP KHO 拼柜"), "ghep")
        self.assertEqual(tool.field_of("卫生证"), "combined")
        self.assertEqual(tool.field_of("BAO HIEM"), "bao_hiem")
        self.assertEqual(tool.field_of("开发电器"), "dien")
        self.assertEqual(tool.field_of("OTHER FEE\n码头插电费"), "dien")

    def test_headers_added_19_11(self):
        self.assertEqual(tool.field_of("过磅"), "can_hang")
        self.assertEqual(tool.field_of("CÂN HÀNG"), "can_hang")
        self.assertEqual(tool.field_of("LOCAL CHARGE\n本地费用"), "local")
        self.assertEqual(tool.field_of("CANCEL FEE 取消还空箱费"), "huy")
        self.assertEqual(tool.field_of("STORAGE 早装产生费用"), "luu_bai")
        self.assertEqual(tool.field_of("AMD FEE 改单费"), "sua_bill")

    def test_blank_unknown_or_mixed_header_is_khac(self):
        for header in ("", "OTHER FEE", "Neo / Phi dien / Dong ghep", "OTHER FEE 拖车", "DET FEE 滞箱费", "HUY"):
            self.assertEqual(tool.field_of(header), "khac", header)


class Plan(unittest.TestCase):
    def run_tool(self, trips, sheet, apply=False, locked=()):
        runner = Runner(trips, locked)
        return tool.run(runner, sheet, apply), runner

    def test_khac_line_splits_by_header_and_total_stays(self):
        web = [trip(11, "FAKEU0000002", "2026-10-03", [fee_line(50, 1, 12865691)])]
        result, runner = self.run_tool(web, tab(ROW2), apply=True)
        self.assertEqual(result["status"], {"READY": 1})
        self.assertEqual(result["written"], 1)
        payload = next(p for c, p in runner.calls if c == "rewrite_trip_fees")
        self.assertEqual(payload["target"], {"trip_id": 11})
        self.assertEqual(payload["expected_line_ids"], [50])
        got = sorted((x["fee_type_id"], int(x["amount_vnd"])) for x in payload["lines"])
        self.assertEqual(got, [(4, 2000000), (6, 4000000), (7, 3365691), (10, 3500000)])
        self.assertEqual(sum(v for _, v in got), 12865691)

    def test_new_types_split_and_get_own_columns(self):
        header = {**HEADER, "F": "过磅", "G": "LOCAL CHARGE\n本地费用", "H": "卫生证"}
        row = trip_row(2, "FAKEU0000002", "09/10/2026", 103907280, F=5000000, G="8907280", H=5000000)
        sheet = [("KHACH A", [(1, {"A": "THÁNG 10/2026"}), (2, header), (3, row)])]
        web = [trip(11, "FAKEU0000002", "2026-10-09", [fee_line(50, 1, 13907280), fee_line(51, 10, 5000000)])]
        result, runner = self.run_tool(web, sheet, apply=True)
        self.assertEqual(result["status"], {"READY": 1})
        payload = next(p for c, p in runner.calls if c == "rewrite_trip_fees")
        got = sorted((x["fee_type_id"], int(x["amount_vnd"])) for x in payload["lines"])
        self.assertEqual(got, [(10, 5000000), (11, 5000000), (12, 8907280)])
        self.assertEqual(runner.columns, [10, 11, 12])   # cột đang có giữ nguyên thứ tự, loại mới thêm sau
        self.assertEqual(result["columns"], 1)

    def test_count_only_writes_nothing(self):
        web = [trip(11, "FAKEU0000002", "2026-10-03", [fee_line(50, 1, 12865691)])]
        result, runner = self.run_tool(web, tab(ROW2))
        self.assertEqual(result["status"], {"READY": 1})
        self.assertFalse([c for c, _ in runner.calls if c == "rewrite_trip_fees"])

    def test_sheet_cells_not_adding_up_to_total_are_left(self):
        row = trip_row(2, "FAKEU0000002", "03/10/2026", 97865692, G=3500000, H=2000000, I=4000000, J="3365691")
        result, _ = self.run_tool([trip(11, "FAKEU0000002", "2026-10-03", [fee_line(50, 1, 12865692)])], tab(row))
        self.assertEqual(result["status"], {"SHEET_DIFF": 1})

    def test_web_total_different_from_sheet_is_left(self):
        result, _ = self.run_tool([trip(11, "FAKEU0000002", "2026-10-03", [fee_line(50, 1, 9000000)])], tab(ROW2))
        self.assertEqual(result["status"], {"TOTAL_DIFF": 1})

    def test_only_unnamed_cells_is_not_a_split(self):
        row = trip_row(1, "FAKEU0000001", "03/10/2026", 89500000, K=4500000)
        result, _ = self.run_tool([trip(11, "FAKEU0000001", "2026-10-03", [fee_line(50, 1, 4500000)])], tab(row))
        self.assertEqual(result["status"], {"NO_NAMED": 1})

    def test_negative_cell_is_left(self):
        row = trip_row(2, "FAKEU0000002", "03/10/2026", 85500000, H=2000000, K=-1500000)
        result, _ = self.run_tool([trip(11, "FAKEU0000002", "2026-10-03", [fee_line(50, 1, 500000)])], tab(row), apply=True)
        self.assertEqual(result["status"], {"SHEET_NEGATIVE": 1})
        self.assertEqual(result["written"], 0)

    def test_already_split_is_done(self):
        lines = [fee_line(1, 10, 3500000), fee_line(2, 4, 2000000), fee_line(3, 6, 4000000), fee_line(4, 7, 3365691)]
        result, _ = self.run_tool([trip(11, "FAKEU0000002", "2026-10-03", lines)], tab(ROW2))
        self.assertEqual(result["status"], {"DONE": 1})

    def test_locked_month_opens_writes_and_locks_again(self):
        web = [trip(11, "FAKEU0000002", "2026-10-03", [fee_line(50, 1, 12865691)])]
        result, runner = self.run_tool(web, tab(ROW2), apply=True, locked=("2026-10",))
        self.assertEqual(result["status"], {"MONTH_LOCKED": 1})
        order = [c for c, _ in runner.calls if c in ("set_month_lock", "rewrite_trip_fees")]
        self.assertEqual(order, ["set_month_lock", "rewrite_trip_fees", "set_month_lock"])

    def test_typed_note_on_khac_line_is_not_lost(self):
        web = [trip(11, "FAKEU0000002", "2026-10-03", [fee_line(50, 1, 12865691, "khach dong y")])]
        result, _ = self.run_tool(web, tab(ROW2), apply=True)
        self.assertEqual(result["status"], {"NOTE_LOST": 1})
        self.assertEqual(result["written"], 0)

    def test_no_web_trip(self):
        result, _ = self.run_tool([], tab(ROW2))
        self.assertEqual(result["status"], {"NOT_FOUND": 1})


class Snapshot(unittest.TestCase):
    """Runner giá ghi `sheet_fees` vào prices.json; máy theo Sheet lập kế hoạch từ đó như công cụ."""

    def test_price_snapshot_carries_named_fees_and_machine_plans_from_it(self):
        import v7_header_fees
        import v7_load_real_copy as loader
        import v7_price_snapshot
        other = trip_row(1, "FAKEU0000001", "03/10/2026", 89500000, K=4500000)   # chỉ cột không tên: không có `sheet_fees`
        sheet = tab(ROW2, other)
        prices, _ = v7_price_snapshot.snapshots(loader.scan_tabs(sheet), {"kind": "xlsx"}, sheet)
        by_row = {row["source_row"]: row for row in prices["rows"]}
        self.assertEqual(by_row[3]["sheet_fees"], {"neo": 2000000, "ghep": 4000000, "bao_hiem": 3365691, "combined": 3500000})
        self.assertNotIn("sheet_fees", by_row[4])
        ledger = {"customer_id": 7, "trips": [trip(11, "FAKEU0000002", "2026-10-03", [fee_line(50, 1, 12865691)])],
                  "legacy_rows": [], "month_locks": [], "today_month": "2026-10-01"}
        plans = v7_header_fees.project(prices, ledger, [{"id": 7, "name": "KHACH A"}], TYPES)
        self.assertEqual([p["status"] for p in plans], ["READY"])
        got = sorted((x["fee_type_id"], int(x["amount_vnd"])) for x in v7_header_fees.write_lines(plans[0]))
        self.assertEqual(got, [(4, 2000000), (6, 4000000), (7, 3365691), (10, 3500000)])

    def test_snapshot_without_raw_tabs_has_no_named_fees(self):
        import v7_load_real_copy as loader
        import v7_price_snapshot
        prices, _ = v7_price_snapshot.snapshots(loader.scan_tabs(tab(ROW2)), {"kind": "xlsx"})
        self.assertNotIn("sheet_fees", prices["rows"][0])


if __name__ == "__main__":
    unittest.main()
