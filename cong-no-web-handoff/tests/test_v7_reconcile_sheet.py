"""Synthetic-only reconciliation checks. No captures, Docker, or real DB."""

import csv
import hashlib
import io
import json
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
import uuid
from contextlib import redirect_stderr, redirect_stdout
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import v7_reconcile_sheet as tool


class ReconcileSheetTest(unittest.TestCase):
    def setUp(self):
        # ponytail: synthetic fixtures only, inherit temp ACL for this Windows
        # sandbox; use TemporaryDirectory when its mode=0700 ACL works here.
        self.root = Path(tempfile.gettempdir()) / ("v7-reconcile-test-" + uuid.uuid4().hex)
        self.root.mkdir()
        self.addCleanup(shutil.rmtree, self.root)
        self.sheet = self.root / "sheet"
        self.web = self.root / "web"
        self.out = self.root / "result"
        self.sheet.mkdir()
        self.web.mkdir()
        self.sheet_books = {"Khach gia A": [100, 200]}
        self.web_books = {"Khach gia A": [100, 200]}

    def csv(self, path, fields, rows):
        with path.open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)

    def inputs(self):
        customers, months = [], []
        for key, amounts in self.sheet_books.items():
            total = None if any(x is None for x in amounts) else sum(amounts)
            customers.append({"customer": key, "anchor_vnd": total, "months": len(amounts), "rows": 0, "cleaning": ""})
            for i, amount in enumerate(amounts, 1):
                months.append({"customer": key, "debt_month": f"2026-{i:02}",
                               "opening_anchor_vnd": 0, "charge_vnd": amount, "receipt_vnd": 0,
                               "month_end_vnd": 999999, "sheet_month_end_vnd": 999999, "bucket_vnd": amount})
        # Reverse export column order to prove matching uses header names.
        self.csv(self.sheet / "clean_customers.csv", ["cleaning", "rows", "months", "anchor_vnd", "customer"], customers)
        self.csv(self.sheet / "clean_months.csv", ["bucket_vnd", "sheet_month_end_vnd", "month_end_vnd",
                 "receipt_vnd", "charge_vnd", "opening_anchor_vnd", "debt_month", "customer"], months)
        for i, (key, amounts) in enumerate(self.web_books.items(), 1):
            total = None if any(x is None for x in amounts) else str(sum(amounts))
            self.write_ledger(key, {"status": "active", "customer_id": i, "version": 0,
                              "total_outstanding_vnd": total,
                              "months": [{"month": f"2026-{j:02}-01", "outstanding_vnd": None if x is None else str(x)}
                                         for j, x in enumerate(amounts, 1)]})

    def write_ledger(self, key, raw):
        (self.web / f"{key}.json").write_text(json.dumps(raw), encoding="utf-8")

    def run_tool(self, *extra):
        args = ["--sheet-dir", str(self.sheet), "--out", str(self.out)]
        args += list(extra) if extra else ["--ledger-json", str(self.web)]
        with redirect_stderr(io.StringIO()):
            return tool.main(args)

    def run_tool_stdout(self, *extra):
        output = io.StringIO()
        with redirect_stdout(output):
            code = self.run_tool("--ledger-json", str(self.web), *extra)
        return code, output.getvalue()

    def report(self, filename):
        with (self.out / filename).open(encoding="utf-8-sig", newline="") as stream:
            return list(csv.DictReader(stream))

    def summary(self):
        return json.loads((self.out / "summary.json").read_text(encoding="utf-8"))

    def test_exact_match_and_input_hashes(self):
        self.inputs()
        self.assertEqual(self.run_tool(), 0)
        self.assertEqual(self.report("reconcile_customer.csv")[0]["status"], "KHOP")
        self.assertEqual(self.report("reconcile_month.csv"), [])
        self.assertEqual(self.summary()["total_absolute_difference_vnd"], 0)
        for group, folder in (("sheet", self.sheet), ("web", self.web)):
            for filename, digest in self.summary()["input_sha256"][group].items():
                self.assertEqual(digest, hashlib.sha256((folder / filename).read_bytes()).hexdigest())
        self.assertEqual(set(self.summary()["counts"]), set(tool.STATUSES))

    def test_brief_index_and_status_ranges(self):
        self.sheet_books = {
            "Alice": [100], "Bob": [200], "Carol": [300], "Dave": [400],
            "Eve": [None], "Frank": [None], "Grace": [None],
        }
        self.web_books = {
            "Alice": [100], "Bob": [201], "Carol": [300], "Dora": [987654321],
            "Eve": [500], "Frank": [600], "Grace": [701],
        }
        self.inputs()
        code, output = self.run_tool_stdout("--brief")
        self.assertEqual(code, 1)
        self.assertIn("DOI SOAT: KHONG DAT", output)
        self.assertIn("LECH_TONG: #2", output)
        self.assertIn("CHI_CO_WEB: #5", output)
        self.assertIn("CHI_CO_SHEET: #4", output)
        self.assertIn("THIEU_SO: #6-#8", output)
        self.assertIn("KHOP: 2 | LECH_TONG: 1 | CHI_LECH_THANG: 0 | CHI_CO_SHEET: 1 | CHI_CO_WEB: 1 | THIEU_SO: 3 | TONG: 8", output)
        for secret in (*self.sheet_books, *self.web_books, "987654321", "201", "http", "127.0.0.1"):
            self.assertNotIn(secret, output)
        self.assertNotIn(str(self.out), output)
        index = self.report("reconcile_index.csv")
        self.assertEqual(index[0], {"no": "1", "customer": "Alice", "status": "KHOP"})
        customers = self.report("reconcile_customer.csv")
        self.assertEqual(index, [{"no": str(no), "customer": row["customer"], "status": row["status"]}
                                 for no, row in enumerate(customers, 1)])
        self.assertEqual(list(self.report("reconcile_customer.csv")[0]),
                         ["customer", "sheet_total_vnd", "web_total_vnd", "difference_vnd", "status"])
        self.assertEqual(list(self.report("reconcile_month.csv")[0]),
                         ["customer", "debt_month", "sheet_vnd", "web_vnd", "difference_vnd",
                          "sheet_month_present", "web_month_present", "status"])

    def test_number_ranges(self):
        self.assertEqual(tool.number_ranges([3, 17, 40, 41, 42]), "#3,#17,#40-#42")
        self.assertEqual(tool.number_ranges([]), "")

    def test_default_stdout_empty_and_month_difference_passes_brief(self):
        self.web_books["Khach gia A"] = [0, 300]
        self.inputs()
        self.assertEqual(self.run_tool_stdout(), (0, ""))
        self.out = self.root / "brief-result"
        code, output = self.run_tool_stdout("--brief")
        self.assertEqual(code, 0)
        self.assertIn("DOI SOAT: DAT", output)
        self.assertIn("CHI_LECH_THANG: #1", output)

    def test_brief_success_and_input_error_stdout_empty(self):
        self.inputs()
        code, output = self.run_tool_stdout("--brief")
        self.assertEqual(code, 0)
        self.assertIn("DOI SOAT: DAT", output)
        self.out = self.root / "bad-result"
        self.csv(self.sheet / "clean_customers.csv", ["customer"], [])
        code, output = self.run_tool_stdout("--brief")
        self.assertEqual((code, output), (2, ""))

    def test_one_vnd_total_difference(self):
        self.web_books["Khach gia A"] = [100, 201]
        self.inputs()
        self.assertEqual(self.run_tool(), 1)
        row = self.report("reconcile_customer.csv")[0]
        self.assertEqual((row["status"], row["difference_vnd"]), ("LECH_TONG", "1"))
        self.assertEqual(self.summary()["total_absolute_difference_vnd"], 1)
        self.assertEqual(len(self.report("reconcile_month.csv")), 2)

    def test_only_months_differ_is_success(self):
        self.web_books["Khach gia A"] = [0, 300]
        self.inputs()
        self.assertEqual(self.run_tool(), 0)
        self.assertEqual(self.report("reconcile_customer.csv")[0]["status"], "CHI_LECH_THANG")
        self.assertEqual([r["difference_vnd"] for r in self.report("reconcile_month.csv")], ["-100", "100"])

    def test_names_only_normalize_whitespace(self):
        self.sheet_books = {"  Khach   gia A  ": [100], "Khach gia B": [10]}
        self.web_books = {"Khach gia A": [100], "Khach gia Bx": [10]}
        self.inputs()
        self.assertEqual(self.run_tool(), 1)
        statuses = {r["customer"]: r["status"] for r in self.report("reconcile_customer.csv")}
        self.assertEqual(statuses, {"Khach gia A": "KHOP", "Khach gia B": "CHI_CO_SHEET", "Khach gia Bx": "CHI_CO_WEB"})
        self.assertIsNone(self.summary()["total_absolute_difference_vnd"])
        self.assertEqual(self.summary()["customers_without_total_difference"], 2)

    def test_blank_sheet_and_null_web_are_unknown(self):
        self.sheet_books["Khach gia A"] = [None, 200]
        self.web_books["Khach gia A"] = [None, 200]
        self.inputs()
        self.assertEqual(self.run_tool(), 1)  # Unknown cells are not a match.
        row = self.report("reconcile_customer.csv")[0]
        self.assertEqual((row["status"], row["sheet_total_vnd"], row["web_total_vnd"], row["difference_vnd"]),
                         ("THIEU_SO", "", "", ""))
        self.assertIsNone(self.summary()["total_absolute_difference_vnd"])
        self.assertEqual(self.report("reconcile_month.csv")[0]["sheet_vnd"], "")

    def test_month_blank_with_known_totals_is_unknown(self):
        self.inputs()
        raw = json.loads((self.web / "Khach gia A.json").read_text())
        raw["months"][0]["outstanding_vnd"] = ""
        self.write_ledger("Khach gia A", raw)
        self.assertEqual(self.run_tool(), 1)
        self.assertEqual(self.report("reconcile_customer.csv")[0]["status"], "THIEU_SO")

    def test_known_total_difference_wins_over_blank_month(self):
        self.inputs()
        raw = json.loads((self.web / "Khach gia A.json").read_text())
        raw["months"][0]["outstanding_vnd"] = ""
        raw["total_outstanding_vnd"] = "301"
        self.write_ledger("Khach gia A", raw)
        self.assertEqual(self.run_tool(), 1)
        row = self.report("reconcile_customer.csv")[0]
        self.assertEqual((row["status"], row["difference_vnd"]), ("LECH_TONG", "1"))

    def test_no_baseline_is_unknown_not_zero(self):
        self.inputs()
        self.write_ledger("Khach gia A", {"customer_id": 1, "status": "NO_BASELINE", "months": [], "total_outstanding_vnd": None})
        self.assertEqual(self.run_tool(), 1)
        self.assertEqual(self.report("reconcile_customer.csv")[0]["status"], "THIEU_SO")

    def test_missing_csv_column_exits_two_without_output(self):
        self.inputs()
        self.csv(self.sheet / "clean_customers.csv", ["customer"], [{"customer": "Khach gia A"}])
        self.assertEqual(self.run_tool(), 2)
        self.assertFalse(self.out.exists())

    def test_missing_month_column_exits_two(self):
        self.inputs()
        self.csv(self.sheet / "clean_months.csv", ["customer", "debt_month"], [])
        self.assertEqual(self.run_tool(), 2)
        self.assertFalse(self.out.exists())

    def test_only_sheet_or_only_web(self):
        for side in ("sheet", "web"):
            with self.subTest(side=side):
                self.out = self.root / ("only-" + side)
                self.sheet_books = {"Khach gia A": [100]} if side == "sheet" else {}
                self.web_books = {"Khach gia A": [100]} if side == "web" else {}
                self.inputs()
                self.assertEqual(self.run_tool(), 1)
                self.assertEqual(self.report("reconcile_customer.csv")[0]["status"],
                                 "CHI_CO_SHEET" if side == "sheet" else "CHI_CO_WEB")

    def test_absent_month_keeps_blank_and_presence_flag(self):
        self.sheet_books["Khach gia A"] = [300]
        self.web_books["Khach gia A"] = [300, 0]
        self.inputs()
        self.assertEqual(self.run_tool(), 0)
        row = self.report("reconcile_month.csv")[1]
        self.assertEqual((row["status"], row["sheet_vnd"], row["web_vnd"], row["difference_vnd"]),
                         ("CHI_LECH_THANG", "", "0", ""))
        self.assertEqual(row["sheet_month_present"], "False")

    def test_blank_anchor_and_literal_null_are_unknown(self):
        self.inputs()
        self.csv(self.sheet / "clean_customers.csv", ["customer", "anchor_vnd"],
                 [{"customer": "Khach gia A", "anchor_vnd": " NULL "}])
        self.assertEqual(self.run_tool(), 1)
        row = self.report("reconcile_customer.csv")[0]
        self.assertEqual((row["status"], row["sheet_total_vnd"], row["web_total_vnd"]), ("THIEU_SO", "", "300"))

    def test_invalid_money_rejected_not_rounded(self):
        self.inputs()
        for bad in (1.0, True, "1.5", "1e3", "NaN"):
            with self.subTest(value=bad):
                raw = {"customer_id": 1, "status": "active", "total_outstanding_vnd": bad, "months": []}
                self.write_ledger("Khach gia A", raw)
                self.assertEqual(self.run_tool(), 2)
        self.assertFalse(self.out.exists())

    def test_big_integer_and_negative_credit_exact(self):
        self.sheet_books = self.web_books = {"Khach gia A": [9007199254740993, -11]}
        self.inputs()
        self.assertEqual(self.run_tool(), 0)
        self.assertEqual(self.report("reconcile_customer.csv")[0]["web_total_vnd"], "9007199254740982")

    def test_duplicate_normalized_names_rejected(self):
        self.sheet_books[" Khach  gia A "] = [100, 200]
        self.inputs()
        self.assertEqual(self.run_tool(), 2)

    def test_malformed_ledger_and_duplicate_month_rejected(self):
        self.inputs()
        for raw in ([], {"customer_id": 1}, {"customer_id": 1, "status": "active", "total_outstanding_vnd": "2",
                    "months": [{"month": "2026-01-01", "outstanding_vnd": "1"}] * 2}):
            with self.subTest(raw=raw):
                self.write_ledger("Khach gia A", raw)
                self.assertEqual(self.run_tool(), 2)
        self.assertFalse(self.out.exists())

    def test_invalid_calendar_month_rejected(self):
        self.inputs()
        self.write_ledger("Khach gia A", {"customer_id": 1, "status": "active", "total_outstanding_vnd": "300",
                          "months": [{"month": "2026-13-01", "outstanding_vnd": "300"}]})
        self.assertEqual(self.run_tool(), 2)

    def test_remote_api_rejected_before_network(self):
        self.inputs()
        for address in ("http://example.com:8780", "http://192.0.2.1:8780", "http://127.0.0.1.example.com:8780",
                        "http://[2001:db8::1]:8780", "http://127.0.0.1:8780@192.0.2.1:8780", "https://127.0.0.1:8780"):
            with self.subTest(address=address), patch.object(tool, "build_opener") as network:
                self.assertEqual(self.run_tool("--api", address), 2)
                network.assert_not_called()
        self.assertFalse(self.out.exists())

    def test_output_must_be_new_and_outside_repo(self):
        self.inputs()
        with self.subTest(case="existing"):
            self.out.mkdir()
            marker = self.out / "keep.txt"
            marker.write_text("keep")
            self.assertEqual(self.run_tool(), 2)
            self.assertEqual(marker.read_text(), "keep")
        with self.subTest(case="repository"):
            self.out = tool.REPO / "must-not-be-created"
            self.assertEqual(self.run_tool(), 2)
            self.assertFalse(self.out.exists())

    def test_loopback_api_fake_http_and_redirect_block(self):
        self.inputs()
        raw = json.loads((self.web / "Khach gia A.json").read_text())
        requests, responses = [], {"/api/v7/customers": {"customers": [{"id": 1, "name": "Khach gia A"}]},
                                  "/api/v7/ledger?customer=1": raw}

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                requests.append(self.path)
                if self.server.redirect:
                    self.send_response(302)
                    self.send_header("Location", "http://192.0.2.1:8780/")
                    self.end_headers()
                    return
                payload = json.dumps(responses[self.path]).encode()
                self.send_response(200)
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, *args):
                pass

        with ThreadingHTTPServer(("127.0.0.1", 0), Handler) as server:
            server.redirect = False
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                address = f"http://127.0.0.1:{server.server_port}"
                self.assertEqual(self.run_tool("--api", address), 0)
                self.assertEqual(requests, list(responses))
                self.assertEqual(self.report("reconcile_customer.csv")[0]["status"], "KHOP")
                self.assertEqual(len(self.summary()["input_sha256"]["web"]), 2)
                server.redirect = True
                self.out = self.root / "redirect-output"
                self.assertEqual(self.run_tool("--api", address), 2)
                self.assertFalse(self.out.exists())
            finally:
                server.shutdown()
                thread.join()

    def test_cli_exit_code_for_broken_input(self):
        self.inputs()
        self.csv(self.sheet / "clean_customers.csv", ["customer"], [])
        result = subprocess.run(check=False, args=[sys.executable, "-B", str(Path(tool.__file__)), "--sheet-dir", str(self.sheet),
                                 "--ledger-json", str(self.web), "--out", str(self.out)], capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 2)
        self.assertNotIn(b"Traceback", result.stderr)


if __name__ == "__main__":
    unittest.main()
