import hashlib
import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from pilot.reconcile import build, money

SOURCE_ID = "synthetic-source"
CAPTURE_ID = "synthetic-capture"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def make_capture(root):
    workbook = root / "source-google-export.xlsx"
    workbook.write_bytes(b"synthetic capture bytes")
    specs = [
        ("Khách hàng", 1, 4, 6, {7: ["A", "group", None, "OK"]}),
        ("Số dư đầu", 2, 8, 6, {7: ["A", "2025-12", "2025-12-31", -10, "source", "ĐÃ GHI SỔ", "OK", None]}),
        ("Chuyến hàng", 3, 16, 6, {
            7: ["A", "2026-10", "2026-10-01", "CONT1", None, None, None, None, None, None, 90, 100, "2026-10-01", "source", "OK", None],
            8: ["A", "2026-10", "2026-10-02", "CONT2", None, None, None, None, None, None, 20, None, "2026-10-02", "source", "OK", None],
            9: ["A", "2026-10", "2026-10-03", "CONT3", None, None, None, None, None, None, 0, 0, "2026-10-03", "source", "OK", None],
        }),
        ("Thu & cấn trừ", 4, 10, 6, {
            7: ["A", "2026-10", "2026-10-04", "2026-10-04", "THỰC NHẬN", 50, "ĐÃ GHI SỔ", "note", "proof ref", "OK"],
            8: ["A", "2026-10", "2026-10-05", "2026-10-05", "THỰC NHẬN", 20, "CHỜ KIỂM TRA", "note", None, "OK"],
        }),
        ("07 Đối soát", 5, 17, 6, {
            7: ["A", "2025-12", 0, 0, 0, -10, -10, 0, 0, -10, 0, "KHỚP"],
            8: ["A", "2026-10", 0, 100, 50, 50, 0, 100, 50, 50, 0, "KHỚP"],
        }),
        ("17 Đối soát theo khách", 6, 12, 6, {
            4: [None, "2026-10-13"],
            5: ["TỔNG", None, None, None, None, 40, 39, 1],
            7: ["A", None, None, None, None, 40, 39, 1],
        }),
        ("Tổng quan", 7, 17, 8, {4: [None, "2026-10", None, None, "2026-10-13"], 7: [None] * 9 + [40]}),
        ("06 Phiếu công nợ", 8, 26, None, {
            4: [None, "A", None, None, "2026-10", None, None, "2026-10-13"],
            7: [None] * 11 + [40], 8: [None] * 11 + [40],
        }),
    ]
    tabs = []
    for title, gid, width, header_row, records in specs:
        path = root / f"gid-{gid}.jsonl"
        with path.open("w", encoding="utf-8") as stream:
            for row_number, values in records.items():
                padded = values + [None] * (width - len(values))
                stream.write(json.dumps({"capture_id": CAPTURE_ID, "source_file_id": SOURCE_ID, "sheet_gid": gid, "source_row": row_number, "values": padded}, ensure_ascii=False) + "\n")
        tabs.append({"title": title, "gid": gid, "header_row": header_row, "grid_column_count": width, "nonempty_export_rows": len(records), "jsonl_file": path.name, "jsonl_sha256": digest(path)})
    (root / "manifest.json").write_text(json.dumps({"capture_id": CAPTURE_ID, "source_spreadsheet_id": SOURCE_ID, "source_workbook": workbook.name, "source_workbook_sha256": digest(workbook), "tabs": tabs}), encoding="utf-8")


class ReconcileTest(unittest.TestCase):
    def test_money_rejects_unknown_and_fractional_vnd(self):
        self.assertEqual(money(-10), -10)
        for value in (None, "", "1.5", True):
            with self.assertRaises(ValueError):
                money(value)

    def test_coverage_as_of_and_pending_receipt(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_capture(root)
            result = build(root, date(2026, 10, 13))
            self.assertEqual(result["totals"]["balance_vnd"], 40)
            self.assertEqual(result["coverage"]["Chuyến hàng"], {"replayed": 1, "quarantined": 2})
            self.assertEqual(result["coverage"]["Thu & cấn trừ"], {"replayed": 1, "quarantined": 1})
            self.assertEqual(len(result["reconciliation"]["period_diffs"]), 0)
            self.assertEqual(len(result["reconciliation"]["customer_diffs"]), 0)
            self.assertEqual(result["reconciliation"]["derived_view_checks"]["statement_selected"]["replayed_rollforward_vnd"], 40)
            self.assertEqual({e["code"] for e in result["exceptions"] if e["sheet"] == "Chuyến hàng"}, {"MISSING_TOTAL", "ZERO_TOTAL", "COMPONENT_DIFF"})
            self.assertEqual(len(result["events"]), 3)

            earlier = build(root, date(2026, 9, 30))
            self.assertEqual(earlier["totals"]["balance_vnd"], -10)
            self.assertEqual(earlier["reconciliation"]["comparison_status"], "skipped_as_of_mismatch")
            self.assertIsNone(earlier["reconciliation"]["derived_view_checks"]["overview_all_periods"]["replayed_vnd"])

    def test_tampered_capture_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_capture(root)
            with (root / "gid-3.jsonl").open("a", encoding="utf-8") as stream:
                stream.write("{}\n")
            with self.assertRaisesRegex(ValueError, "hash mismatch"):
                build(root, date(2026, 10, 13))

    def test_payment_types_stay_separate_and_receipts_are_not_merged(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_capture(root)
            path = root / "gid-4.jsonl"
            extra = [
                (9, "2025-12", "THỰC NHẬN", 5, "bank-ref"),
                (10, "2026-10", "CẤN TRỪ", 10, "USD note, VND amount confirmed in source"),
                (11, "2026-10", "ĐIỀU CHỈNH +", 3, "reason"),
                (12, "2026-10", "ĐIỀU CHỈNH -", 2, "reason"),
            ]
            with path.open("a", encoding="utf-8") as stream:
                for row_number, debt_period, kind, amount, note in extra:
                    stream.write(json.dumps({"capture_id": CAPTURE_ID, "source_file_id": SOURCE_ID, "sheet_gid": 4, "source_row": row_number, "values": ["A", debt_period, "2026-10-06", "2026-10-06", kind, amount, "ĐÃ GHI SỔ", note, "proof ref", "OK"]}, ensure_ascii=False) + "\n")
            manifest_path = root / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            tab = next(tab for tab in manifest["tabs"] if tab["gid"] == 4)
            tab["nonempty_export_rows"] += len(extra)
            tab["jsonl_sha256"] = digest(path)
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

            result = build(root, date(2026, 10, 13))
            self.assertEqual(result["totals"]["balance_vnd"], 26)
            self.assertEqual([event["kind"] for event in result["events"]].count("receipt"), 2)
            self.assertEqual([event["kind"] for event in result["events"]].count("offset"), 1)
            self.assertEqual([event["kind"] for event in result["events"]].count("adjustment_plus"), 1)
            self.assertEqual([event["kind"] for event in result["events"]].count("adjustment_minus"), 1)
            self.assertEqual(len({(event["sheet_gid"], event["source_row"]) for event in result["events"]}), len(result["events"]))


if __name__ == "__main__":
    unittest.main()
