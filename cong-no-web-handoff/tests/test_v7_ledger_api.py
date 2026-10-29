"""V7 HTTP boundary checks; Docker case runs only on an isolated fake harness."""

import base64
import http.client
import io
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import uuid
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "web"))
import v7_ledger_api as api  # noqa: E402


class FeeApiTest(unittest.TestCase):
    def setUp(self):
        self.common = {"customer_id": 1, "expected_version": 0, "idempotency_key": "fee-request"}
        self.headers = {"Host": "127.0.0.1:8780", "Origin": "http://127.0.0.1:8780", "Content-Type": "application/json"}

    def request(self, path, body, method="POST"):
        runner = FakePsql()
        result = api.handle(method, path, self.headers, json.dumps(body).encode(), runner,
                            port=8780, host="127.0.0.1", actor="server-fee-actor")
        self.assertEqual(result[0], 200)
        self.assertEqual(runner.calls[-1][2], "server-fee-actor")
        return runner.calls[-1]

    def test_all_fee_routes_and_sql(self):
        samples = [
            ("/api/v7/trips/fees/add", "add_trip_fees", self.common | {"targets": [{"trip_id": 1}, {"legacy_row_id": 2}], "fee_type_id": 1, "amount_vnd": "5", "note": "fee"}),
            ("/api/v7/trips/fees/set", "set_trip_fee_type", self.common | {"target": {"trip_id": 1}, "fee_type_id": 1, "amount_vnd": None}),
            ("/api/v7/trips/fees/replace", "replace_trip_fee", self.common | {"fee_line_id": 1, "fee_type_id": 1, "amount_vnd": "-5"}),
            ("/api/v7/trips/fees/void", "void_trip_fee", self.common | {"fee_line_id": 1}),
            ("/api/v7/books/fee-columns", "set_book_fee_columns", self.common | {"fee_type_ids": [3, 1]}),
            ("/api/v7/fee-types", "add_fee_type", {"idempotency_key": "catalog", "name": "FAKE", "kind": "service"}),
            ("/api/v7/fee-types/update", "rename_fee_type", {"command": "rename_fee_type", "idempotency_key": "catalog", "fee_type_id": 1, "name": "FAKE RENAMED"}),
            ("/api/v7/fee-types/update", "set_fee_type_kind", {"command": "set_fee_type_kind", "idempotency_key": "catalog", "fee_type_id": 1, "kind": "pass_through"}),
            ("/api/v7/fee-types/update", "set_fee_type_active", {"command": "set_fee_type_active", "idempotency_key": "catalog", "fee_type_id": 1, "active": False}),
        ]
        for path, function, body in samples:
            with self.subTest(path=path, function=function):
                name, payload, _ = self.request(path, body)
                self.assertEqual(name, function)
                self.assertNotIn("command", payload)
                self.assertIn(f"SELECT sokhach.{function}(", api.SQL[name])
                self.assertNotIn("actor", api.SQL[name])
        self.assertEqual(self.request("/api/v7/fee-types", {}, "GET")[0], "get_fee_types")
        self.assertIn("(j->'targets')::jsonb", api.SQL["add_trip_fees"])
        self.assertIn("(j->'target')::jsonb", api.SQL["set_trip_fee_type"])
        self.assertIn("(j->'fee_type_ids')::jsonb", api.SQL["set_book_fee_columns"])

    def test_fee_boundaries(self):
        path = "/api/v7/trips/fees/add"
        base = self.common | {"targets": [{"trip_id": 1}], "fee_type_id": 1, "amount_vnd": "5"}
        for amount in ("0", "-0", "1.5", 1, True, None, "9223372036854775808", "-9223372036854775809"):
            with self.subTest(amount=amount), self.assertRaises(api.ApiError) as caught:
                api.validate(path, json.dumps(base | {"amount_vnd": amount}).encode())
            self.assertEqual(caught.exception.code, "FEE_AMOUNT_INVALID")
        for change in ({"actor": "client"}, {"expected_version": None}, {"idempotency_key": " "},
                       {"targets": []}, {"targets": [{"trip_id": 1, "legacy_row_id": 2}]},
                       {"targets": [{"trip_id": True}]}, {"targets": [{"trip_id": 1}] * 2}, {"fee_type_id": False}):
            with self.subTest(change=change), self.assertRaises(api.ApiError):
                api.validate(path, json.dumps(base | change).encode())
        for command in ([], None, "drop_table"):
            with self.assertRaises(api.ApiError):
                api.validate("/api/v7/fee-types/update", json.dumps({"command": command}).encode())
        with self.assertRaises(api.ApiError) as caught:
            api.validate("/api/v7/books/fee-columns", json.dumps(self.common | {"fee_type_ids": [1, 2, 3, 4]}).encode())
        self.assertEqual(caught.exception.code, "FEE_COLUMNS_MAX")

    def test_every_spec_error_maps_to_vietnamese(self):
        codes = ("MONTH_LOCKED", "FEE_AMOUNT_INVALID", "FEE_SIGN_INVALID", "FEE_TYPE_INACTIVE", "FEE_TYPE_SYSTEM",
                 "FEE_TYPE_DUPLICATE", "FEE_LINES_TYPED", "FEE_COLUMNS_MAX", "VERSION_CONFLICT", "IDEMPOTENCY_CONFLICT",
                 "TRIP_NOT_FOUND", "LEGACY_NOT_FOUND", "TRIP_PENDING_REVIEW", "LEGACY_NO_UNIT_PRICE",
                 "FEE_LINE_NOT_FOUND")
        for code in codes:
            with self.subTest(code=code):
                failure = subprocess.CompletedProcess([], 3, "", f"psql:<stdin>:3: ERROR:  P0001: {code}\n")
                with patch.object(api.subprocess, "run", return_value=failure), self.assertRaises(api.ApiError) as caught:
                    api._PsqlRunner()._run_psql(["fake-psql"], "add_trip_fees", {}, "server-actor")
                self.assertEqual(caught.exception.code, code)
                self.assertEqual(caught.exception.status, api.ERRORS[code][0])
                self.assertTrue(any(ord(char) > 127 for char in caught.exception.message))


class PriceApiTest(unittest.TestCase):
    setUp = FeeApiTest.setUp
    request = FeeApiTest.request

    def test_price_routes_and_sql(self):
        table = {"tt_shippers": ["FAKE"], "locations": [{"name": "DAK LAK"}], "periods": []}
        name, payload, _ = self.request("/api/v7/price-table", self.common | {"price_table": table})
        self.assertEqual((name, payload["price_table"]), ("save_price_table", table))
        name, payload, _ = self.request("/api/v7/price-table/apply", self.common | {"trip_ids": [3, 1]})
        self.assertEqual((name, payload["trip_ids"]), ("apply_price_table", [3, 1]))
        self.assertIn("(j->'price_table')::jsonb", api.SQL["save_price_table"])
        self.assertIn("(j->'trip_ids')::jsonb", api.SQL["apply_price_table"])
        for path, function in (("/api/v7/price-table?customer=7", "get_price_table"),
                               ("/api/v7/price-table/status?customer=7", "get_price_status")):
            with self.subTest(path=path):
                name, payload, _ = self.request(path, {}, "GET")
                self.assertEqual((name, payload), (function, {"customer_id": 7}))
                self.assertNotIn("actor", api.SQL[name])

    def test_price_boundaries(self):
        for change in ({"price_table": []}, {"price_table": None}, {"actor": "client"}, {}):
            with self.subTest(change=change), self.assertRaises(api.ApiError):
                body = self.common | {"price_table": {}} | change
                if not change:
                    body.pop("price_table")
                api.validate("/api/v7/price-table", json.dumps(body).encode())
        for ids in ([], [0], [1, 1], ["1"], [True], [1.5], list(range(1, 502)), None):
            with self.subTest(ids=ids), self.assertRaises(api.ApiError):
                api.validate("/api/v7/price-table/apply", json.dumps(self.common | {"trip_ids": ids}).encode())
        for query in ("", "?customer=0", "?customer=1&customer=2", "?id=1"):
            with self.subTest(query=query), self.assertRaises(api.ApiError):
                api.handle("GET", "/api/v7/price-table" + query, self.headers, b"", FakePsql(),
                           port=8780, host="127.0.0.1", actor="server-fee-actor")

    def test_price_errors_map_to_vietnamese(self):
        for code in ("INVALID_PRICE_TABLE", "PRICE_PERIOD_OVERLAP", "PRICE_INVALID_PERIOD", "PRICE_INVALID_AMOUNT",
                     "PRICE_UNKNOWN_LOCATION", "PRICE_DUPLICATE_ALIAS", "PRICE_DUPLICATE_SHIPPER",
                     "PRICE_DUPLICATE_RATE", "PRICE_NOT_FOUND", "NO_CHANGE", "MONTH_LOCKED"):
            with self.subTest(code=code):
                failure = subprocess.CompletedProcess([], 3, "", f"psql:<stdin>:3: ERROR:  P0001: {code}\n")
                with patch.object(api.subprocess, "run", return_value=failure), self.assertRaises(api.ApiError) as caught:
                    api._PsqlRunner()._run_psql(["fake-psql"], "save_price_table", {}, "server-actor")
                self.assertEqual(caught.exception.code, code)
                self.assertTrue(any(ord(char) > 127 for char in caught.exception.message))


class FakePsql:
    def __init__(self):
        self.calls = []

    def run(self, function, payload, actor):
        self.calls.append((function, payload, actor))
        return {"function": function, "version": payload.get("expected_version", 0)}


class LedgerApiTest(unittest.TestCase):
    def test_customer_name_mapping_enriches_picker_without_changing_id(self):
        mapping = {"version": 1, "customers": {"7": {
            "v7_name": "V7 NAME", "display_name": "SHEET NAME", "aliases": ["OLD NAME"],
            "commodity": "Chuối", "commodity_review": "OK", "label": "SHEET NAME · Chuối"}}}
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".json", delete=False) as handle:
            json.dump(mapping, handle)
            path = handle.name
        try:
            rows = {"customers": [{"id": 7, "name": "V7 NAME", "status": "active",
                                   "commodity": None, "transport_mode": None}]}
            with patch.object(api, "CUSTOMER_NAME_MAPPING_PATH", path), \
                    patch.object(self.runner, "run", return_value=rows):
                status, result = api.handle("GET", "/api/v7/customers", self.headers, b"", self.runner,
                                            port=8780, host="127.0.0.1", actor="server")
            self.assertEqual(status, 200)
            self.assertEqual(result["customers"][0]["id"], 7)
            self.assertEqual(result["customers"][0]["name"], "V7 NAME")
            self.assertEqual(result["customers"][0]["display_name"], "SHEET NAME")
            self.assertEqual(result["customers"][0]["aliases"], ["OLD NAME"])
            self.assertEqual(result["customers"][0]["commodity"], "Chuối")
        finally:
            os.unlink(path)

    def test_customer_name_mapping_rejects_stale_and_bad_config(self):
        stale = {"id": 7, "name": "RENAMED"}
        self.assertEqual(api.named_customer(stale, {"7": {
            "v7_name": "OLD", "display_name": "SHEET"}}), stale)
        with patch.object(api, "CUSTOMER_NAME_MAPPING_PATH", None):
            self.assertEqual(api.customer_name_mapping(), {})
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".json", delete=False) as handle:
            json.dump({"version": 1, "customers": {"7": {
                "v7_name": "V7", "display_name": " ", "aliases": []}}}, handle)
            path = handle.name
        try:
            with patch.object(api, "CUSTOMER_NAME_MAPPING_PATH", path):
                self.assertEqual(api.customer_name_mapping(), {})
        finally:
            os.unlink(path)

    def test_sheet_conflict_resolution_uses_server_values_and_rejects_stale(self):
        class Runner:
            def __init__(self):
                self.calls = []
            def run(self, function, payload, actor):
                self.calls.append((function, payload, actor))
                if function == "get_ledger":
                    return {"customer_id": 7, "version": 3, "status": "active"}
                return {"version": 4}
        runner = Runner()
        body = {"customer_id": 7, "expected_version": 3, "snapshot_sha256": "a" * 64,
                "source_row": 8, "target_kind": "trip", "target_id": 9, "field": "carrier",
                "decision": "keep_web", "idempotency_key": "fake-resolution"}
        projection = {"snapshot_sha256": "a" * 64, "items": [{"source_row": 8,
            "sync_state": "CONFLICT", "existing_kind": "trip", "existing_id": 9,
            "changed_fields": ["carrier"], "carrier": "COSCO", "existing_values": {"carrier": "WH"}}]}
        with patch.object(api, "sheet_projection", return_value=projection), \
                patch.object(api, "load_snapshot", return_value={"sha256": "a" * 64}):
            status, result = api.resolve_sheet_conflict(json.dumps(body).encode(), runner, "fake-actor")
        self.assertEqual((status, result["version"]), (200, 4))
        self.assertEqual(runner.calls[-1][0], "resolve_sheet_conflict")
        self.assertEqual(runner.calls[-1][1]["sheet_value"], "COSCO")
        self.assertEqual(runner.calls[-1][1]["target_value"], "WH")
        self.assertEqual(runner.calls[-1][2], "fake-actor")
        shipper = body | {"field": "shipper", "decision": "use_sheet"}
        projection["items"][0].update(changed_fields=["shipper"], shipper="KHOI PHONG",
                                      existing_values={"shipper": None})
        with patch.object(api, "sheet_projection", return_value=projection), \
                patch.object(api, "load_snapshot", return_value={"sha256": "a" * 64}):
            api.resolve_sheet_conflict(json.dumps(shipper).encode(), runner, "fake-actor")
        self.assertIsNone(runner.calls[-1][1]["target_value"])
        for change in ({"sheet_value": "FORGED"}, {"field": "unit_price_vnd"}, {"target_id": 10},
                       {"snapshot_sha256": "b" * 64}, {"expected_version": 2}):
            runner.calls.clear()
            with self.subTest(change=change), patch.object(api, "sheet_projection", return_value=projection), \
                    patch.object(api, "load_snapshot", return_value={"sha256": "a" * 64}), \
                    self.assertRaises(api.ApiError):
                api.resolve_sheet_conflict(json.dumps(body | change).encode(), runner, "fake-actor")
            self.assertFalse(any(call[0] == "resolve_sheet_conflict" for call in runner.calls))

    def test_sheet_date_and_booking_conflicts_only_keep_web(self):
        class Runner:
            def __init__(self):
                self.calls = []
            def run(self, function, payload, actor):
                self.calls.append((function, payload, actor))
                if function == "get_ledger":
                    return {"customer_id": 7, "version": 3, "status": "active"}
                return {"version": 4}
        runner = Runner()
        body = {"customer_id": 7, "expected_version": 3, "snapshot_sha256": "a" * 64,
                "source_row": 8, "target_kind": "trip", "target_id": 9, "field": "event_date",
                "decision": "keep_web", "idempotency_key": "fake-date"}
        projection = {"snapshot_sha256": "a" * 64, "items": [{"source_row": 8,
            "sync_state": "CONFLICT", "existing_kind": "trip", "existing_id": 9,
            "changed_fields": ["event_date", "booking"], "event_date": "2026-10-20", "booking": None,
            "existing_values": {"event_date": "2026-10-18", "booking": "BK-OLD"}}]}
        with patch.object(api, "sheet_projection", return_value=projection), \
                patch.object(api, "load_snapshot", return_value={"sha256": "a" * 64}):
            api.resolve_sheet_conflict(json.dumps(body).encode(), runner, "fake-actor")
            self.assertEqual((runner.calls[-1][1]["sheet_value"], runner.calls[-1][1]["target_value"]),
                             ("2026-10-20", "2026-10-18"))
            api.resolve_sheet_conflict(json.dumps(body | {"field": "booking"}).encode(), runner, "fake-actor")
            self.assertEqual((runner.calls[-1][1]["sheet_value"], runner.calls[-1][1]["target_value"]), ("", "BK-OLD"))
            for change in ({"decision": "use_sheet"}, {"field": "booking", "decision": "use_sheet"},
                           {"field": "booking", "target_kind": "legacy"}):
                runner.calls.clear()
                with self.subTest(change=change), self.assertRaises(api.ApiError):
                    api.resolve_sheet_conflict(json.dumps(body | change).encode(), runner, "fake-actor")
                self.assertFalse(any(call[0] == "resolve_sheet_conflict" for call in runner.calls))

    def test_nhap_sheet_routes_and_validation(self):
        routes = [
            ("/api/v7/trips/info", "edit_trip_info", {"trip_id": 7, "field": "container", "value": "FAKE"}),
            ("/api/v7/trips/delete", "delete_trip", {"trip_id": 7}),
            ("/api/v7/legacy/edit", "edit_legacy_trip", {"legacy_row_id": 8, "field": "unit_price_vnd", "value": "70000000"}),
            ("/api/v7/legacy/delete", "delete_legacy_trip", {"legacy_row_id": 8}),
        ]
        for route, function, fields in routes:
            body = self.common | fields
            self.assertEqual(self.call(route, body)[0], 200)
            self.assertEqual(self.runner.calls[-1], (function, body, "configured"))
            for extra in ({"actor": "forged"}, {"status": "confirmed"}, {"deleted": True}, {"amount_vnd": "0"}):
                with self.subTest(route=route, extra=extra), self.assertRaises(api.ApiError):
                    self.call(route, body | extra)
            id_field = "trip_id" if "trip_id" in fields else "legacy_row_id"
            for invalid in (None, 0, -1, True, "7", 9223372036854775808):
                with self.subTest(route=route, invalid=invalid), self.assertRaises(api.ApiError):
                    self.call(route, body | {id_field: invalid})
            self.assertIn(f"sokhach.{function}(", api.SQL[function])
        for route, id_field in [("/api/v7/trips/info", "trip_id"), ("/api/v7/legacy/edit", "legacy_row_id")]:
            for field in ("container", "carrier", "origin", "destination", "event_date"):
                self.call(route, self.common | {id_field: 1, "field": field,
                                               "value": "2026-01-01" if field == "event_date" else "FAKE"})
            for invalid in ("unknown", [], {}, None, "status"):
                with self.assertRaises(api.ApiError) as caught:
                    self.call(route, self.common | {id_field: 1, "field": invalid, "value": "X"})
                self.assertEqual(caught.exception.code, "INVALID_FIELD")
            for change in ({"value": 1}, {"value": None}, {"value": []}):
                with self.assertRaises(api.ApiError):
                    self.call(route, self.common | {id_field: 1, "field": "carrier"} | change)
            with self.assertRaises(api.ApiError):
                self.call(route, self.common | {id_field: 1, "field": "carrier"})
            with self.assertRaises(api.ApiError) as caught:
                self.call(route, self.common | {id_field: 1, "field": "event_date", "value": "2026-02-30"})
            self.assertEqual(caught.exception.code, "INVALID_DATE")
        for value in ("", "0", "65000000"):
            self.call("/api/v7/legacy/edit", self.common | {"legacy_row_id": 1, "field": "unit_price_vnd", "value": value})
        for value in ("-0", "1.5", "-1", "9223372036854775808"):
            with self.assertRaises(api.ApiError) as caught:
                self.call("/api/v7/legacy/edit", self.common | {"legacy_row_id": 1, "field": "unit_price_vnd", "value": value})
            self.assertEqual(caught.exception.code, "INVALID_VND")
        with self.assertRaises(api.ApiError) as caught:
            self.call("/api/v7/trips/info", self.common | {"trip_id": 1, "field": "unit_price_vnd", "value": "1"})
        self.assertEqual(caught.exception.code, "INVALID_FIELD")

    def test_nhap_sheet_error_mapping(self):
        for code in ("INVALID_FIELD", "LEGACY_NOT_FOUND", "LEGACY_NOT_TRIP"):
            with self.subTest(code=code), patch.object(api.subprocess, "run") as run:
                run.return_value = Mock(returncode=1, stdout="", stderr=f"psql:<stdin>:1: ERROR:  P0001: {code}\n")
                with self.assertRaises(api.ApiError) as caught:
                    api._PsqlRunner()._run_psql([], "delete_legacy_trip", self.common | {"legacy_row_id": 1}, "fake")
                self.assertEqual((caught.exception.status, caught.exception.code), (422, code))
        self.assertEqual(api.ERRORS["LEGACY_NOT_FOUND"][1], "Không tìm thấy dòng sổ gốc.")
        self.assertEqual(api.ERRORS["LEGACY_NOT_TRIP"][1], "Dòng sổ gốc này là khoản thu, không sửa ở đây.")

    def test_optional_receipt_reference_and_reference_only_edit(self):
        receipt = self.common | {"date": "2026-01-02", "method": "THU TIỀN", "amount_vnd": "10"}
        for reference in (None, "", "FAKE-TXN USD/rate text", "x" * 500):
            for route, fields in (("/api/v7/receipts", receipt),
                                  ("/api/v7/receipts/meta", self.common | {"pid": "PH-001"})):
                if route.endswith("/meta") and reference is None:
                    continue
                self.call(route, fields | {"reference": reference})
                self.assertEqual(self.runner.calls[-1][1]["reference"], reference)
        for invalid in (0, False, [], {}, "x" * 501):
            with self.assertRaises(api.ApiError):
                self.call("/api/v7/receipts", receipt | {"reference": invalid})
        self.assertIn("j->>'reference'", api.SQL["record_receipt"])
        self.assertIn("j->>'reference'", api.SQL["edit_receipt_meta"])

    def test_paste_booking_passes_boundary_but_client_status_does_not(self):
        row = {"booking": " b k 1 ", "container": "FAKE", "date": "10/01/2026",
               "carrier": "SHIP", "from": "A", "to": "B", "unitPriceVnd": "100", "otherFeeVnd": None}
        body = {"customer_id": 1, "expected_version": 0, "idempotency_key": "fake-paste-booking",
                "debt_month": "2026-01-01", "trips": [row]}
        function, payload = api.validate("/api/v7/trips/paste", json.dumps(body).encode())
        self.assertEqual(function, "paste_trips")
        self.assertEqual(payload["trips"][0], row)
        with self.assertRaises(api.ApiError):
            api.validate("/api/v7/trips/paste", json.dumps(body | {"trips": [row | {"status": "confirmed"}]}).encode())

    def test_paste_signed_fee_cells(self):
        row = {"container": "FAKE", "date": "10/01/2026", "carrier": "SHIP",
               "from": "A", "to": "B", "unitPriceVnd": "100", "fees": ["7", "-3"]}
        body = {"customer_id": 1, "expected_version": 0, "idempotency_key": "fake-fees",
                "debt_month": "2026-01-01", "trips": [row]}
        self.assertEqual(api.validate("/api/v7/trips/paste", json.dumps(body).encode())[1]["trips"], [row])
        for fees in (["0"], ["-0"], [0], ["1.5"], "7", ["7", None]):
            with self.subTest(fees=fees), self.assertRaises(api.ApiError):
                api.validate("/api/v7/trips/paste", json.dumps(body | {"trips": [row | {"fees": fees}]}).encode())

    def test_sheet_bulk_approval_freezes_snapshot_and_keeps_price_null(self):
        class SheetRunner:
            def __init__(self):
                self.version = 3
                self.calls = []

            def run(self, function, payload, actor):
                self.calls.append((function, payload, actor))
                if function == "get_ledger":
                    return {"status": "active", "version": self.version, "today_month": "2026-10-01",
                            "month_locks": [{"month": "2026-09-01", "locked": False}]}
                if function == "paste_trips":
                    self.version += 1
                    return {"pending_review": []}
                raise AssertionError(function)

        runner = SheetRunner()
        row = {"sync_state": "NEW", "source_row": 2, "event_date": "2026-10-24", "booking": "BK1",
               "container": "FAKE1", "carrier": "WH", "origin": "A", "destination": "B"}
        projection = {"snapshot_sha256": "a" * 64, "items": [row, row | {"sync_state": "CONFLICT", "source_row": 3},
            row | {"source_row": 4, "event_date": "2026-09-24", "container": "FAKE2"}]}
        body = {"customer_id": 7, "expected_version": 3, "snapshot_sha256": "a" * 64,
                "idempotency_key": "test-bulk"}
        with patch.object(api, "sheet_projection", return_value=projection):
            status, result = api.handle("POST", "/api/v7/sheet/approve", self.headers,
                json.dumps(body).encode(), runner, port=8780, host="127.0.0.1", actor="tester")
        self.assertEqual((status, result["approved"], result["complete"]), (200, 2, True))
        writes = [call for call in runner.calls if call[0] == "paste_trips"]
        self.assertEqual(len(writes), 2)
        self.assertEqual([call[1]["expected_version"] for call in writes], [3, 4])
        self.assertTrue(all(call[1]["trips"][0]["unitPriceVnd"] is None for call in writes))
        self.assertTrue(all(call[1]["trips"][0]["note"] == "Chuyến đồng bộ" for call in writes))
        self.assertTrue(all(call[2] == "tester" for call in writes))
        runner.calls.clear()
        runner.version = 3
        with patch.object(api, "sheet_projection", return_value=projection | {"snapshot_sha256": "b" * 64}), \
                self.assertRaises(api.ApiError) as caught:
            api.approve_sheet(json.dumps(body).encode(), runner, "tester")
        self.assertEqual(caught.exception.code, "STALE_SHEET")
        self.assertFalse(any(call[0] == "paste_trips" for call in runner.calls))
        runner.calls.clear()
        runner.version = 3
        original_run = runner.run
        def locked_run(function, payload, actor):
            value = original_run(function, payload, actor)
            if function == "get_ledger":
                value["month_locks"] = [{"month": "2026-09-01", "locked": True}]
            return value
        runner.run = locked_run
        with patch.object(api, "sheet_projection", return_value=projection):
            status, result = api.approve_sheet(json.dumps(body).encode(), runner, "tester")
        self.assertEqual((status, result["approved"], result["remaining"]), (200, 2, 0))
        self.assertEqual([call[1]["debt_month"] for call in runner.calls if call[0] == "paste_trips"],
                         ["2026-09-01", "2026-10-01"])
        runner.calls.clear()
        runner.version = 3
        with patch.object(api, "sheet_projection", return_value=projection | {"items": [projection["items"][2]]}):
            status, result = api.approve_sheet(json.dumps(body).encode(), runner, "tester")
        self.assertEqual((status, result["approved"]), (200, 1))
        self.assertEqual([call[1]["debt_month"] for call in runner.calls if call[0] == "paste_trips"],
                         ["2026-09-01"])

    def test_review_trip_boundary(self):
        body = self.common | {"trip_id": 7, "decision": "confirm", "reason": "đã đối chiếu sổ gốc"}
        for decision in ("confirm", "reject"):
            function, payload = api.validate("/api/v7/trips/review", json.dumps(body | {"decision": decision}).encode())
            self.assertEqual((function, payload["decision"]), ("review_trip", decision))
        for change in ({"decision": "approve"}, {"decision": None}, {"trip_id": 0}, {"reason": 1},
                       {"reason": "x" * 501}, {"status": "confirmed"}):
            with self.subTest(change=change), self.assertRaises(api.ApiError):
                api.validate("/api/v7/trips/review", json.dumps(body | change).encode())
        for reason in (None, "", "   "):
            with self.assertRaises(api.ApiError) as caught:
                api.validate("/api/v7/trips/review", json.dumps(body | {"reason": reason}).encode())
            self.assertEqual(caught.exception.code, "REVIEW_REASON_REQUIRED")
        self.assertIn("sokhach.review_trip(", api.SQL["review_trip"])
        self.assertIn("(j->>'trip_id')::bigint, j->>'decision', j->>'reason'", api.SQL["review_trip"])

    def test_serve_host_origin_assets_and_identity(self):
        authority = "demo.tail-example.ts.net:8443"
        class ServeHandler(api.Handler):
            behind_tailscale_serve = True
            serve_hosts = (authority, "second.tail-example.ts.net")
            default_actor = None
            dev_actor_mode = False
        ServeHandler.runner = self.runner
        ServeHandler.localapi = self.localapi
        self.localapi.whois.return_value = {}
        with api.ThreadingHTTPServer(("127.0.0.1", 0), ServeHandler) as server:
            ServeHandler.port = server.server_port
            worker = threading.Thread(target=server.serve_forever, daemon=True)
            worker.start()
            def request(path, host=authority, method="GET", origin=None, payload=None, identity=True):
                conn = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
                headers = {"Host": host, "Content-Type": "application/json"}
                if identity:
                    headers["Tailscale-User-Login"] = "serve-user@example.test"
                if origin is not None:
                    headers["Origin"] = origin
                # No GET body: server leaves it unread, and Windows resets the socket on close (WinError 10053).
                body = None if method == "GET" else json.dumps(payload or {}).encode()
                conn.request(method, path, body=body, headers=headers)
                response = conn.getresponse()
                data = response.read()
                conn.close()
                return response.status, data
            try:
                for route in ("/api/v7/customers", next(iter(api.ASSETS))):
                    for host in ServeHandler.serve_hosts:
                        self.assertEqual(request(route, host)[0], 200)
                    for host in ("evil.example.test:8443", authority + ".evil", authority.upper()):
                        self.assertEqual(request(route, host)[0], 400)
                    ServeHandler.serve_hosts = ()
                    self.assertEqual(request(route)[0], 400)
                    ServeHandler.serve_hosts = (authority,)
                    ServeHandler.behind_tailscale_serve = False
                    self.localapi.whois.return_value = {"UserProfile": {"LoginName": "verified@example.test"}}
                    self.assertEqual(request(route)[0], 400)
                    ServeHandler.behind_tailscale_serve = True
                    self.localapi.whois.return_value = {}
                    self.assertEqual(request(route, identity=False)[0], 403)
                payload = self.common | {"month": "2026-10-01", "locked": True}
                self.assertEqual(request("/api/v7/months/lock", method="POST",
                                         origin="https://" + authority, payload=payload)[0], 200)
                self.assertEqual(self.runner.calls[-1][2], "serve-user@example.test")
                for origin in (None, "http://" + authority, "https://evil.example.test", "https://" + authority + "/"):
                    self.assertEqual(request("/api/v7/months/lock", method="POST", origin=origin, payload=payload)[0], 403)
                self.assertEqual(request("/api/v7/months/lock", method="POST", origin="https://" + authority,
                                         payload=payload | {"actor": "client-forged"})[0], 422)
                self.assertEqual(request("/api/v7/customers?actor=client-forged")[0], 404)
            finally:
                server.shutdown()
                worker.join(timeout=3)

    def test_serve_cli_requires_flag_and_valid_exact_host(self):
        for value in ("*.example.test", "example.test/path", "user@example.test", "example.test:0",
                      "example.test:65536", "https://example.test", "example.test?x=1", "EXAMPLE.test"):
            with self.subTest(value=value), patch.object(sys, "argv", ["api", "--container", "fake",
                    "--behind-tailscale-serve", "--serve-host", value]), patch.object(api, "Psql") as runner:
                with self.assertRaises(SystemExit):
                    api.main()
                runner.assert_not_called()
        with patch.object(sys, "argv", ["api", "--container", "fake", "--serve-host", "demo.example.test"]), \
                patch.dict(os.environ, {"V7_API_BEHIND_TAILSCALE_SERVE": "0"}), self.assertRaises(SystemExit):
            api.main()

    def test_get_opening_and_void_contract_sql(self):
        # Static contract only; money identities run in the PostgreSQL harness.
        sql = (ROOT / "tools/v7_backend_functions.sql").read_text(encoding="utf-8")
        ledger = sql.split("FUNCTION sokhach.get_ledger(", 1)[1].split("END $$;", 1)[0]
        active = ledger.split("active_cutover AS (", 1)[1].split("), month_keys", 1)[0]
        charges = ledger.split("figures AS (", 1)[1].split("AS charges_vnd", 1)[0]
        received = ledger.split("AS charges_vnd", 1)[1].split("AS received_vnd", 1)[0]
        self.assertIn("cc.status='active' AND c.status='active'", active)
        self.assertIn("sokhach.opening_balance", charges)
        self.assertIn("JOIN active_cutover", charges)
        # DA-THU-01: đã thu theo ngày thu của phiếu chưa hủy, không theo kỳ được trừ nợ.
        self.assertIn("date_trunc('month',r.date)::date=k.debt_month", received)
        self.assertIn("r.voided_on IS NULL", received)
        self.assertNotIn("v_receipt_line_active", received)
        self.assertIn("'voided_by_event',r.voided_by_event", sql)

    def test_field_adjustment_boundary(self):
        for field in ("unit_price_vnd", "other_fee_vnd"):
            fields = {"trip_id": 1, "field": field, "new_value_vnd": "120", "note": "giá mới"}
            self.assertEqual(self.call("/api/v7/trips/adjust", self.common | fields)[0], 200)
            self.assertEqual(self.runner.calls[-1][1], self.common | fields)
        self.runner.calls.clear()
        for fields in ({"field": "amount_vnd", "new_value_vnd": "1"},
                       {"field": "unit_price_vnd"}, {"new_value_vnd": "1"},
                       {"field": "other_fee_vnd", "new_value_vnd": None},
                       {"field": "unit_price_vnd", "new_value_vnd": "1", "new_amount_vnd": "1"}):
            with self.subTest(fields=fields):
                with self.assertRaises(api.ApiError) as caught:
                    self.call("/api/v7/trips/adjust", self.common | {"trip_id": 1} | fields)
                self.assertEqual(caught.exception.status, 422)
        self.assertEqual(self.runner.calls, [])
        self.assertIn("j->>'field'", api.SQL["adjust_trip"])
        self.assertIn("(j->>'new_value_vnd')::bigint", api.SQL["adjust_trip"])

    def test_future_receipt_guards_and_error(self):
        self.assertEqual(api.ERRORS.get("FUTURE_RECEIPT_DATE"),
                         (422, "Ngày trả không được sau hôm nay."))
        sql = (ROOT / "tools/v7_backend_functions.sql").read_text(encoding="utf-8")
        for name in ("record_receipt", "edit_receipt_meta"):
            body = sql.split(f"CREATE FUNCTION sokhach.{name}(", 1)[1].split("END $$;", 1)[0]
            self.assertLess(body.index("_begin_command"), body.index("clock_timestamp()"))
            self.assertIn("AT TIME ZONE 'Asia/Ho_Chi_Minh'", body)
            self.assertIn("RAISE EXCEPTION 'FUTURE_RECEIPT_DATE'", body)

    def test_real_copy_cli_and_demo_exclusion(self):
        with patch.object(sys, "argv", ["v7_ledger_api.py", "--container", "fake", "--real-copy"]), \
             patch.object(api, "Psql"), patch.object(api, "ThreadingHTTPServer") as server, \
             patch.object(api.Handler, "real_copy", False), patch.object(api.Handler, "demo", False), \
             patch.object(api.Handler, "default_actor", None), patch.object(api.Handler, "dev_actor_mode", None), \
             patch.object(api.Handler, "behind_tailscale_serve", False):
            api.main()
            self.assertTrue(api.Handler.real_copy)
            server.return_value.serve_forever.assert_called_once()
        with patch.object(sys, "argv", ["v7_ledger_api.py", "--container", "fake", "--real-copy", "--demo"]), \
             patch.object(api, "Psql") as runner:
            with self.assertRaises(SystemExit) as caught:
                api.main()
            self.assertEqual(caught.exception.code, 2)
            runner.assert_not_called()

    def test_serve_cli_wires_repeatable_hosts(self):
        with patch.object(sys, "argv", ["api", "--container", "fake", "--behind-tailscale-serve",
                "--serve-host", "demo.example.test:8443", "--serve-host", "second.example.test"]), \
                patch.object(api, "Psql"), patch.object(api, "ThreadingHTTPServer") as server, \
                patch.object(api.Handler, "serve_hosts", ()), patch.object(api.Handler, "behind_tailscale_serve", False), \
                patch.object(api.Handler, "default_actor", None), patch.object(api.Handler, "dev_actor_mode", None), \
                patch.object(api.Handler, "demo", False), patch.object(api.Handler, "real_copy", False):
            api.main()
            self.assertEqual(api.Handler.serve_hosts, ("demo.example.test:8443", "second.example.test"))
            self.assertTrue(api.Handler.behind_tailscale_serve)
            server.return_value.serve_forever.assert_called_once()

    def setUp(self):
        self.localapi = Mock()
        self.localapi.whois.return_value = {"UserProfile": {"LoginName": "configured"}}
        patcher = patch.object(api.v7_identity, "TailscaleLocalAPI", return_value=self.localapi)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.runner = FakePsql()
        self.headers = {"Host": "127.0.0.1:8780", "Origin": "http://127.0.0.1:8780",
                        "Content-Type": "application/json"}
        self.common = {"customer_id": 1, "expected_version": 0, "idempotency_key": "same-request"}

    def call(self, path, body, headers=None):
        return api.handle("POST", path, headers or self.headers, json.dumps(body).encode(), self.runner,
                          port=8780, host="127.0.0.1", default_actor="ignored", source_ip="127.0.0.1", source_port=43210)

    def error(self, status, code, action):
        with self.assertRaises(api.ApiError) as caught:
            action()
        self.assertEqual((caught.exception.status, caught.exception.code), (status, code))
        self.assertEqual(self.runner.calls, [])

    def test_routes_and_actor_source(self):
        samples = {
            "/api/v7/trips/paste": ("paste_trips", {"debt_month": "2026-10-01", "trips": [
                {"container": "FAKE", "carrier": "FAKE", "from": "A", "to": "B", "date": "20/10/2026",
                 "unitPriceVnd": "100", "otherFeeVnd": None}]}),
            "/api/v7/trips/price": ("edit_trip_price", {"trip_id": 1, "unit_price_vnd": "100", "other_fee_vnd": None}),
            "/api/v7/trips/adjust": ("adjust_trip", {"trip_id": 1, "new_amount_vnd": "100"}),
            "/api/v7/months/adjust": ("adjust_month", {"debt_month": "2026-10-01", "amount_vnd": "-1"}),
            "/api/v7/receipts": ("record_receipt", {"date": "2026-10-20", "method": "THU TIỀN", "amount_vnd": "10"}),
            "/api/v7/receipts/meta": ("edit_receipt_meta", {"pid": "PH-001", "date": "2026-10-21"}),
            "/api/v7/receipts/void": ("void_receipt", {"pid": "PH-001", "reason": "nhập trùng"}),
            "/api/v7/months/lock": ("set_month_lock", {"month": "2026-10-01", "locked": True}),
            "/api/v7/trips/review": ("review_trip", {"trip_id": 1, "decision": "reject", "reason": "trùng sổ gốc"}),
        }
        for path, (function, fields) in samples.items():
            with self.subTest(path=path):
                self.runner.calls.clear()
                status, data = self.call(path, self.common | fields,
                                         self.headers | {"Tailscale-User-Login": "forged@example.test"})
                self.assertEqual((status, data["function"]), (200, function))
                self.assertEqual(self.runner.calls[0][2], "configured")
                status, _ = api.handle("POST", path,
                    self.headers | {"Tailscale-User-Login": "trusted@example.test"},
                    json.dumps(self.common | fields).encode(), self.runner, port=8780,
                    host="127.0.0.1", default_actor="ignored", source_ip="127.0.0.1", source_port=43210, behind_tailscale_serve=True)
                self.assertEqual(status, 200)
                self.assertEqual(self.runner.calls[-1][2], "trusted@example.test")

    def test_receivables_matrix_route_year_validation(self):
        current = api.datetime.now().year
        for year in (2000, current + 1):
            self.runner.calls.clear()
            status, data = api.handle("GET", f"/api/v7/receivables/matrix?year={year}", self.headers, b"", self.runner,
                                      port=8780, host="127.0.0.1", actor="server")
            self.assertEqual((status, data["function"]), (200, "get_receivables_matrix"))
            self.assertEqual(self.runner.calls[-1], ("get_receivables_matrix", {"year": year}, "server"))
        for query in ("", "year=", "year=1999", f"year={current + 2}", "year=20a6", "year=20260",
                      "year=2026&year=2027", "year=2026&x=1"):
            self.runner.calls.clear()
            with self.assertRaises(api.ApiError) as caught:
                api.handle("GET", "/api/v7/receivables/matrix?" + query, self.headers, b"", self.runner,
                           port=8780, host="127.0.0.1", actor="server")
            self.assertEqual((caught.exception.status, caught.exception.code), (422, "INVALID_YEAR"))
            self.assertEqual(self.runner.calls, [])
        self.assertEqual(api.SQL["get_receivables_matrix"],
                         "SELECT sokhach.get_receivables_matrix((:'payload'::jsonb->>'year')::int);")

    def test_receivables_detail_route_month_validation(self):
        path = "/api/v7/receivables/detail?customer=7&month=2026-10-01"
        status, data = api.handle("GET", path, self.headers, b"", self.runner,
                                  port=8780, host="127.0.0.1", actor="server")
        self.assertEqual((status, data["function"]), (200, "get_receivables_detail"))
        self.assertEqual(self.runner.calls[-1], ("get_receivables_detail", {"customer_id": 7, "month": "2026-10-01"}, "server"))
        for query, code in (("customer=7&month=2026-10-02", "INVALID_MONTH"),
                            ("customer=7&month=2026-13-01", "INVALID_MONTH"),
                            ("customer=7&month=2026-10-01&x=1", "INVALID_REQUEST"),
                            ("customer=0&month=2026-10-01", "INVALID_REQUEST")):
            with self.assertRaises(api.ApiError) as caught:
                api.handle("GET", "/api/v7/receivables/detail?" + query, self.headers, b"", self.runner,
                           port=8780, host="127.0.0.1", actor="server")
            self.assertEqual((caught.exception.status, caught.exception.code), (422, code))

    def test_get_and_host_origin(self):
        status, data = api.handle("GET", "/api/v7/customers", self.headers, b"", self.runner,
                                  port=8780, host="127.0.0.1", default_actor="ignored", source_ip="127.0.0.1", source_port=43210)
        self.assertEqual((status, data["function"]), (200, "list_customers"))
        self.assertEqual(self.runner.calls[-1], ("list_customers", {}, "configured"))
        self.assertEqual(api.SQL["list_customers"], "SELECT sokhach.list_customers();")
        status, data = api.handle("GET", "/api/v7/dashboard", self.headers, b"", self.runner,
                                  port=8780, host="127.0.0.1", default_actor="ignored", source_ip="127.0.0.1", source_port=43210)
        self.assertEqual((status, data["function"]), (200, "get_dashboard"))
        self.assertEqual(self.runner.calls[-1], ("get_dashboard", {}, "configured"))
        with patch.object(api, "load_snapshot", return_value={"rows": [], "row_count": 0, "sha256": "a" * 64}), \
             patch.object(api, "load_baseline", return_value={"cutover_id": 1, "count": 1, "refs": [{}]}), \
             patch.object(api, "build_queue", return_value={"items": [], "row_count": 0, "ready_count": 0, "review_count": 0}) as queue:
            status, data = api.handle("GET", "/api/v7/sheet-queue", self.headers, b"", self.runner,
                                      port=8780, host="127.0.0.1", default_actor="ignored", source_ip="127.0.0.1", source_port=43210)
            self.assertEqual((status, data["row_count"]), (200, 0))
            queue.assert_called_once()
        self.runner.calls.clear()
        self.error(404, "NOT_FOUND", lambda: api.handle("GET", "/api/v7/customers?all=1",
                   self.headers, b"", self.runner, port=8780, host="127.0.0.1", default_actor="ignored", source_ip="127.0.0.1", source_port=43210))
        status, data = api.handle("GET", "/api/v7/ledger?customer=1", self.headers, b"", self.runner,
                                  port=8780, host="127.0.0.1", default_actor="ignored", source_ip="127.0.0.1", source_port=43210)
        self.assertEqual((status, data["function"]), (200, "get_ledger"))
        status, data = api.handle("GET", "/api/v7/ledger?customer=1", self.headers, b"", self.runner,
                                  port=8780, host="127.0.0.1", default_actor="ignored", source_ip="127.0.0.1", source_port=43210, demo=True)
        self.assertEqual((status, data["demo"]), (200, True))
        status, data = api.handle("GET", "/api/v7/ledger?customer=1", self.headers, b"", self.runner,
                                  port=8780, host="127.0.0.1", default_actor="ignored", source_ip="127.0.0.1", source_port=43210, real_copy=True)
        self.assertEqual((status, data["real_copy"]), (200, True))
        self.assertEqual(self.runner.calls[-1], ("get_ledger", {"customer_id": 1}, "configured"))
        self.runner.calls.clear()
        body = self.common | {"date": "2026-10-20", "method": "THU TIỀN", "amount_vnd": "10"}
        self.error(400, "INVALID_HOST", lambda: self.call("/api/v7/receipts", body,
                   self.headers | {"Host": "attacker.test"}))
        self.error(403, "INVALID_ORIGIN", lambda: self.call("/api/v7/receipts", body,
                   self.headers | {"Origin": "http://attacker.test"}))
        self.error(403, "INVALID_ORIGIN", lambda: self.call("/api/v7/receipts", body,
                   {key: val for key, val in self.headers.items() if key != "Origin"}))
        self.error(422, "INVALID_REQUEST", lambda: api.handle("GET", "/api/v7/ledger?customer=1&customer=2",
                   self.headers, b"", self.runner, port=8780, host="127.0.0.1", default_actor="ignored", source_ip="127.0.0.1", source_port=43210))
        self.error(422, "INVALID_REQUEST", lambda: api.handle("GET", "/api/v7/ledger?customer=" + "9" * 5000,
                   self.headers, b"", self.runner, port=8780, host="127.0.0.1", default_actor="ignored", source_ip="127.0.0.1", source_port=43210))

    def test_rejects_client_calculation_actor_and_bad_money(self):
        self.assertTrue(api.vnd("-9223372036854775808", signed=True))
        self.assertFalse(api.vnd("-9223372036854775809", signed=True))
        path = "/api/v7/receipts"
        body = self.common | {"date": "2026-10-20", "method": "THU TIỀN", "amount_vnd": "10"}
        for field in ("actor", "allocation", "allocations", "total_vnd"):
            with self.subTest(field=field):
                self.error(422, "INVALID_REQUEST", lambda field=field: self.call(path, body | {field: "forged"}))
        for amount in (10, 1.5, "1.5", "-0", "01", "9" * 5000, "9223372036854775808"):
            with self.subTest(amount=str(amount)[:24]):
                code = "INVALID_REQUEST" if amount == 1.5 else "INVALID_VND"
                self.error(422, code, lambda amount=amount: self.call(path, body | {"amount_vnd": amount}))
        self.error(422, "INVALID_REQUEST", lambda: self.call(path, body | {"idempotency_key": "x\nq"}))
        self.error(422, "INVALID_REQUEST", lambda: self.call(path, body | {"customer_id": True}))
        self.error(422, "INVALID_REQUEST", lambda: self.call(path, body | {"expected_version": -1}))
        self.error(422, "INVALID_REQUEST", lambda: self.call(path, body | {"date": "2026-02-30"}))
        self.error(422, "INVALID_REQUEST", lambda: api.handle("POST", path, self.headers,
                   b'{"customer_id":1,"customer_id":2}', self.runner, port=8780,
                   host="127.0.0.1", default_actor="ignored", source_ip="127.0.0.1", source_port=43210))

    def test_content_type_and_body_size(self):
        path = "/api/v7/receipts"
        self.error(415, "INVALID_CONTENT_TYPE", lambda: api.handle("POST", path,
                   self.headers | {"Content-Type": "text/plain"}, b"{}", self.runner,
                   port=8780, host="127.0.0.1", default_actor="ignored", source_ip="127.0.0.1", source_port=43210))
        self.error(413, "BODY_TOO_LARGE", lambda: api.handle("POST", path, self.headers,
                   b"x" * (api.MAX_BODY + 1), self.runner, port=8780,
                   host="127.0.0.1", default_actor="ignored", source_ip="127.0.0.1", source_port=43210))

    def test_psql_error_mapping_and_fixed_sql(self):
        self.assertIn("(j->'trips')::jsonb", api.SQL["paste_trips"])
        self.assertIn("(j->>'amount_vnd')::bigint", api.SQL["record_receipt"])
        self.assertNotIn("->>>", "\n".join(api.SQL.values()))
        inspect = subprocess.CompletedProcess([], 0, json.dumps([{"Id": "a" * 64, "Config": {"Labels": {
            "codex.test": "webdebit-v7-backend", "codex.run": "fake-run"}},
            "HostConfig": {"NetworkMode": "none"}}]), "")
        business = subprocess.CompletedProcess([], 3, "", "psql:<stdin>:3: ERROR:  P0001: STALE_LEDGER\n")
        with patch.object(api.subprocess, "run", side_effect=[inspect, business]) as command:
            runner = api.Psql("webdebit-v7-test-fake", "webdebit_v7_test", "v7_app")
            with self.assertRaises(api.ApiError) as caught:
                runner.run("record_receipt", self.common | {"date": "2026-10-20",
                           "method": "THU TIỀN", "amount_vnd": "10"}, "server-actor")
            self.assertEqual((caught.exception.status, caught.exception.code), (409, "STALE_LEDGER"))
            args = command.call_args.args[0]
            sql = command.call_args.kwargs["input"]
            self.assertIn("BEGIN;\nSET LOCAL sokhach.actor = :'actor';", sql)
            self.assertIn("SELECT sokhach.record_receipt(", sql)
            self.assertIn("-v", args)
            self.assertIn("actor=server-actor", args)
            self.assertNotIn("server-actor", sql)
            self.assertEqual(args[args.index("docker") + 1], "exec")
            self.assertIn("a" * 64, args)
        with patch.object(api.subprocess, "run", return_value=inspect):
            self.assertEqual(api.Psql("webdebit-v7-test-fake", "webdebit_v7_test", "v7_app").user, "v7_app")
        unsafe = subprocess.CompletedProcess([], 0, json.dumps([{"Id": "b" * 64, "Config": {"Labels": {}},
            "HostConfig": {"NetworkMode": "bridge"}}]), "")
        with patch.object(api.subprocess, "run", return_value=unsafe), self.assertRaises(ValueError):
            api.Psql("not-a-harness", "webdebit_v7_test", "v7_app")
        for code, (status, _) in api.ERRORS.items():
            with self.subTest(error=code):
                error = subprocess.CompletedProcess([], 3, "", f"psql:<stdin>:3: ERROR:  P0001: {code}\n")
                with patch.object(api.subprocess, "run", side_effect=[inspect, error]):
                    runner = api.Psql("webdebit-v7-test-fake", "webdebit_v7_test", "v7_app")
                    with self.assertRaises(api.ApiError) as caught:
                        runner.run("get_ledger", {"customer_id": 1}, "configured")
                    self.assertEqual((caught.exception.status, caught.exception.code), (status, code))
        with patch.object(api.subprocess, "run", side_effect=[inspect, subprocess.TimeoutExpired([], 25)]):
            runner = api.Psql("webdebit-v7-test-fake", "webdebit_v7_test", "postgres")
            with self.assertRaises(api.ApiError) as caught:
                runner.run("record_receipt", self.common | {"date": "2026-10-20",
                           "method": "THU TIỀN", "amount_vnd": "10"}, "configured")
            self.assertEqual((caught.exception.status, caught.exception.code), (503, "RESULT_UNKNOWN"))
        internal = subprocess.CompletedProcess([], 3, "", "psql:<stdin>:3: ERROR:  23514: secret SQL detail\n")
        with patch.object(api.subprocess, "run", side_effect=[inspect, internal]):
            runner = api.Psql("webdebit-v7-test-fake", "webdebit_v7_test", "postgres")
            with self.assertRaises(api.ApiError) as caught:
                runner.run("get_ledger", {"customer_id": 1}, "configured")
            self.assertEqual((caught.exception.status, caught.exception.code), (503, "DB_UNAVAILABLE"))
            self.assertNotIn("secret", caught.exception.message)

    def offset_samples(self):
        return {
            "/api/v7/offsets": ("record_offset", {
                "target_customer_id": 1, "target_version": 0, "source_customer_id": 2,
                "source_version": 3, "idempotency_key": "offset", "date": "2026-10-20", "amount_vnd": "100"}),
            "/api/v7/offsets/void": ("void_offset", self.common | {
                "other_version": 3, "offset_pair_id": 4, "reason": "nhập trùng"}),
            "/api/v7/offsets/date": ("edit_offset_date", self.common | {
                "other_version": 3, "offset_pair_id": 4, "date": "2026-10-20"}),
        }

    def test_offset_routes_actor_and_sql_arguments(self):
        for path, (function, body) in self.offset_samples().items():
            with self.subTest(path=path):
                self.assertEqual(self.call(path, body)[0], 200)
                self.assertEqual(self.runner.calls[-1], (function, body, "configured"))
                args = {
                    "record_offset": ("target_customer_id", "target_version", "source_customer_id", "source_version", "idempotency_key", "date", "amount_vnd", "reference"),
                    "void_offset": ("customer_id", "expected_version", "other_version", "idempotency_key", "offset_pair_id", "reason"),
                    "edit_offset_date": ("customer_id", "expected_version", "other_version", "idempotency_key", "offset_pair_id", "date"),
                }[function]
                expected = ", ".join(f"(j->>'{key}')::{api.CAST[key]}" if key in api.CAST
                                     else f"j->>'{key}'" for key in args)
                self.assertEqual(api.SQL[function],
                    f"WITH b AS (SELECT :'payload'::jsonb AS j) SELECT sokhach.{function}({expected}) FROM b;")
                self.runner.calls.clear()
                self.error(422, "INVALID_REQUEST", lambda path=path, body=body: self.call(path, body | {"actor": "forged"}))
                for header, value, status, code in (("Origin", "http://bad.test", 403, "INVALID_ORIGIN"),
                                                   ("Content-Type", "text/plain", 415, "INVALID_CONTENT_TYPE")):
                    self.error(status, code, lambda path=path, body=body, header=header, value=value: self.call(path, body, self.headers | {header: value}))
                for key in body:
                    with self.subTest(missing=key), self.assertRaises(api.ApiError):
                        self.call(path, {k: v for k, v in body.items() if k != key})
                raw = json.dumps(body)[:-1] + ',"idempotency_key":"duplicate"}'
                self.error(422, "INVALID_REQUEST", lambda path=path, raw=raw: api.validate(path, raw.encode()))

    def test_offset_invalid_fields(self):
        for path, (_, body) in self.offset_samples().items():
            invalid = {"idempotency_key": [None, "", "x\n"], "actor": ["forged"]}
            for key in body:
                if key.endswith("version"):
                    invalid[key] = [-1, True, "0", api.MAX_BIGINT + 1]
                elif key.endswith("_id"):
                    invalid[key] = [-1, 0, "1", True, api.MAX_BIGINT + 1]
            if "amount_vnd" in body:
                invalid["amount_vnd"] = ["-1", "0", "-0", "1.5", 1, 1.5, None, "01", "9223372036854775808"]
            if "date" in body:
                invalid["date"] = [None, "", "2026-02-30", "20/10/2026", "2026-1-01", 123]
            if "reason" in body:
                invalid["reason"] = [None, 1, "", "   ", "x" * 501]
            for key, values in invalid.items():
                for value in values:
                    with self.subTest(path=path, key=key, value=value), self.assertRaises(api.ApiError) as caught:
                        self.call(path, body | {key: value})
                    self.assertEqual(caught.exception.status, 422)
            self.assertEqual(self.runner.calls, [])

    def test_offset_sources_query_flags_and_timeout(self):
        self.assertEqual(api.SQL["list_offset_sources"],
                         "SELECT sokhach.list_offset_sources((:'payload'::jsonb->>'target_customer_id')::bigint);")
        for flags in ({}, {"demo": True}, {"real_copy": True}):
            runner = Mock()
            runner.run.return_value = [{"customer_id": 2, "available_credit_vnd": "100"}]
            status, data = api.handle("GET", "/api/v7/offset-sources?customer=1", self.headers,
                b"", runner, port=8780, host="127.0.0.1", actor="server", **flags)
            self.assertEqual(status, 200)
            self.assertEqual(data, {"sources": runner.run.return_value, **flags})
            runner.run.assert_called_once_with("list_offset_sources", {"target_customer_id": 1}, "server")
        for query in ("", "customer=", "customer=0", "customer=-1", "customer=01", "customer=1&x=2",
                      "customer=1&customer=2", "customer=9223372036854775808", "customer=" + "9" * 5000):
            self.error(422, "INVALID_REQUEST", lambda query=query: api.handle("GET", "/api/v7/offset-sources?" + query,
                self.headers, b"", self.runner, port=8780, host="127.0.0.1", actor="server"))
        runner = object.__new__(api.Psql)
        runner.container, runner.database, runner.user = "fake", "fake", "fake"
        with patch.object(api.subprocess, "run", side_effect=subprocess.TimeoutExpired([], 25)):
            with self.assertRaises(api.ApiError) as caught:
                runner.run("list_offset_sources", {"target_customer_id": 1}, "server")
            self.assertEqual(caught.exception.code, "DB_UNAVAILABLE")

    def test_offset_psql_payload_and_credit_detail(self):
        for code, status in {"OFFSET_SAME_BOOK": 422, "OFFSET_EXCEEDS_CREDIT": 422,
                             "OFFSET_SOURCE_ARCHIVED": 409, "OFFSET_NOT_FOUND": 422,
                             "OFFSET_ALREADY_VOID": 409, "OFFSET_PAIR_REQUIRED": 409,
                             "FUTURE_DATE": 422, "INVALID_DATE": 422}.items():
            self.assertEqual(api.ERRORS[code][0], status)
        runner = object.__new__(api.Psql)
        runner.container, runner.database, runner.user = "fake", "fake", "fake"
        for _, (function, body) in self.offset_samples().items():
            with patch.object(api.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, '{}', '')) as command:
                runner.run(function, body, "server-actor")
                self.assertIn(api.SQL[function], command.call_args.kwargs["input"])
                args = command.call_args.args[0]
                payload = next(arg[len("payload="):] for arg in args if arg.startswith("payload="))
                self.assertEqual(json.loads(payload), body)
                self.assertIn("actor=server-actor", args)
                self.assertNotIn("server-actor", command.call_args.kwargs["input"])
        for detail, expected in ((None, {}), ('{"available_credit_vnd":"123"}', {"available_credit_vnd": "123"}),
                ('{"available_credit_vnd":"0"}', {"available_credit_vnd": "0"}),
                ('{"available_credit_vnd":123}', {}), ('{"available_credit_vnd":null}', {}),
                ('{"available_credit_vnd":"-1"}', {}), ('{"available_credit_vnd":"01"}', {}),
                ('{"available_credit_vnd":"9223372036854775808"}', {}), ('invalid secret', {}),
                ('{"available_credit_vnd":"1","available_credit_vnd":"2"}', {})):
            stderr = "psql:<stdin>:3: ERROR:  P0001: OFFSET_EXCEEDS_CREDIT\n"
            if detail is not None:
                stderr += "DETAIL:  " + detail + "\nCONTEXT: secret SQL\n"
            with patch.object(api.subprocess, "run", return_value=subprocess.CompletedProcess([], 3, '', stderr)):
                with self.assertRaises(api.ApiError) as caught:
                    runner.run("record_offset", {}, "server")
                self.assertEqual((caught.exception.status, caught.exception.code), (422, "OFFSET_EXCEEDS_CREDIT"))
                self.assertEqual(caught.exception.extra, expected)
                self.assertNotIn("secret", caught.exception.message)


class LedgerHttpTest(unittest.TestCase):
    def test_identity_http_contract(self):
        for method in ("GET", "POST"):
            for error in (None, TimeoutError(), OSError(), api.v7_identity.IdentityError("NOT_TAILNET")):
                with self.subTest(method=method, error=error):
                    class TrialHandler(api.Handler):
                        runner = FakePsql()
                        default_actor = "must-not-fallback"
                        dev_actor_mode = False
                        localapi = Mock()
                    TrialHandler.localapi.whois.return_value = {"UserProfile": {"LoginName": "Real@EXAMPLE.TEST"}}
                    TrialHandler.localapi.whois.side_effect = error
                    with api.ThreadingHTTPServer(("127.0.0.1", 0), TrialHandler) as server:
                        TrialHandler.port = server.server_port
                        worker = threading.Thread(target=server.serve_forever, daemon=True)
                        worker.start()
                        try:
                            conn = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=3)
                            conn.connect()
                            peer_port = conn.sock.getsockname()[1]
                            headers = {"Origin": f"http://127.0.0.1:{server.server_port}",
                                       "Content-Type": "application/json", "Tailscale-User-Login": "forged",
                                       "X-Forwarded-For": "100.100.100.100"}
                            body = json.dumps({"customer_id": 1, "expected_version": 0, "idempotency_key": "identity",
                                               "date": "2026-10-20", "method": "THU TI\u1ec0N", "amount_vnd": "10"})
                            conn.request(method, "/api/v7/ledger?customer=1" if method == "GET" else "/api/v7/receipts",
                                         body=body if method == "POST" else None, headers=headers)
                            response = conn.getresponse()
                            data = json.loads(response.read())
                            conn.close()
                            TrialHandler.localapi.whois.assert_called_once_with(f"127.0.0.1:{peer_port}")
                            if error is None:
                                self.assertEqual(response.status, 200)
                                self.assertEqual(TrialHandler.runner.calls[-1][2], "Real@example.test")
                            else:
                                code = "LOCALAPI_TIMEOUT" if isinstance(error, TimeoutError) else (
                                    "LOCALAPI_ERROR" if isinstance(error, OSError) else error.code)
                                self.assertEqual((response.status, data), (403, {"error": code}))
                                self.assertEqual(TrialHandler.runner.calls, [])
                        finally:
                            server.shutdown()
                            worker.join(timeout=3)

    def test_dev_and_serve_startup_contract(self):
        for mode in (True, None, False):
            class TrialHandler(api.Handler):
                default_actor = "demo"
            with patch("sys.stderr", new_callable=io.StringIO) as stderr:
                with api.ThreadingHTTPServer(("127.0.0.1", 0), TrialHandler, dev_actor_mode=mode) as server:
                    self.assertEqual(server.dev_actor, None if mode is False else "dev:demo")
                self.assertEqual(stderr.getvalue().count("WARNING:"), 0 if mode is False else 1)
        for host in ("0.0.0.0", "192.0.2.1"):
            for mode in (True, None):
                with self.assertRaises(ValueError):
                    api.ThreadingHTTPServer((host, 0), TrialHandler, dev_actor_mode=mode)
            class ServeHandler(api.Handler):
                behind_tailscale_serve = True
            with self.assertRaises(ValueError):
                api.ThreadingHTTPServer((host, 0), ServeHandler)

    def test_cli_identity_environment(self):
        with patch.dict(os.environ, {"V7_API_BEHIND_TAILSCALE_SERVE": "1",
                                    "V7_API_INSECURE_DEV_ACTOR": "env-demo"}), \
             patch.object(sys, "argv", ["api", "--container", "fake"]), patch.object(api, "Psql"), \
             patch.object(api, "ThreadingHTTPServer"), patch.object(api.Handler, "default_actor"), \
             patch.object(api.Handler, "dev_actor_mode"), patch.object(api.Handler, "behind_tailscale_serve"):
            api.main()
            self.assertTrue(api.Handler.behind_tailscale_serve)
            self.assertTrue(api.Handler.dev_actor_mode)
            self.assertEqual(api.Handler.default_actor, "env-demo")

    def test_cli_identity_modes(self):
        for flags, actor, serve in (([], None, False), (["--insecure-dev-actor", "demo"], "demo", False),
                                    (["--behind-tailscale-serve"], None, True)):
            with patch.dict(os.environ, {}, clear=True), patch.object(sys, "argv", ["api", "--container", "fake", *flags]), \
                 patch.object(api, "Psql"), patch.object(api, "ThreadingHTTPServer"), \
                 patch.object(api.Handler, "default_actor"), patch.object(api.Handler, "dev_actor_mode"), \
                 patch.object(api.Handler, "behind_tailscale_serve"):
                api.main()
                self.assertEqual(api.Handler.default_actor, actor)
                self.assertEqual(api.Handler.dev_actor_mode, actor is not None)
                self.assertEqual(api.Handler.behind_tailscale_serve, serve)
        for flag in (["--insecure-dev-actor", "demo"], ["--behind-tailscale-serve"]):
            with patch.object(sys, "argv", ["api", "--container", "fake", "--host", "0.0.0.0", *flag]), \
                 patch.object(api, "Psql") as runner, self.assertRaises(SystemExit):
                api.main()
            runner.assert_not_called()

    def test_offset_http_with_fake_psql(self):
        class TrialHandler(api.Handler):
            runner = FakePsql()
            default_actor = "offset-test"
            dev_actor_mode = True

        with api.ThreadingHTTPServer(("127.0.0.1", 0), TrialHandler) as server:
            TrialHandler.port = server.server_port
            worker = threading.Thread(target=server.serve_forever, daemon=True)
            worker.start()
            try:
                def request(method, path, body=None):
                    conn = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=3)
                    headers = {"Origin": f"http://127.0.0.1:{server.server_port}", "Content-Type": "application/json"}
                    conn.request(method, path, body=json.dumps(body) if body is not None else None, headers=headers)
                    response = conn.getresponse()
                    result = response.status, json.loads(response.read())
                    conn.close()
                    return result

                self.common = {"customer_id": 1, "expected_version": 0, "idempotency_key": "http-offset"}
                for path, (function, body) in LedgerApiTest.offset_samples(self).items():
                    self.assertEqual(request("POST", path, body), (200, {"function": function,
                                     "version": body.get("expected_version", 0)}))
                    self.assertEqual(TrialHandler.runner.calls[-1], (function, body, "dev:offset-test"))
                self.assertEqual(request("GET", "/api/v7/offset-sources?customer=1")[0], 200)
                error = api.ApiError(422, "OFFSET_EXCEEDS_CREDIT", api.ERRORS["OFFSET_EXCEEDS_CREDIT"][1],
                                     {"available_credit_vnd": "123"})
                with patch.object(TrialHandler.runner, "run", side_effect=error):
                    path, (_, body) = next(iter(LedgerApiTest.offset_samples(self).items()))
                    self.assertEqual(request("POST", path, body), (422, {"error": error.code,
                        "message": error.message, "available_credit_vnd": "123"}))
            finally:
                server.shutdown()
                worker.join(timeout=3)

    def test_bounded_http_with_fake_psql(self):
        class TrialHandler(api.Handler):
            runner = FakePsql()
            demo = True
            default_actor = "fake-demo"
            dev_actor_mode = True
            localapi = Mock()

        TrialHandler.localapi.whois.return_value = {"UserProfile": {"LoginName": "whois@example.test"}}

        server = api.ThreadingHTTPServer(("127.0.0.1", 0), TrialHandler)
        TrialHandler.port = server.server_port
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            conn = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=3)
            conn.request("GET", "/api/v7/ledger?customer=1")
            response = conn.getresponse()
            self.assertEqual((response.status, json.loads(response.read())["demo"]), (200, True))
            conn.close()
            conn = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=3)
            base = {"Host": f"127.0.0.1:{server.server_port}", "Origin": f"http://127.0.0.1:{server.server_port}",
                    "Content-Type": "application/json", "Tailscale-User-Login": "forged@example.test"}
            body = json.dumps({"customer_id": 1, "expected_version": 0, "idempotency_key": "http",
                               "date": "2026-10-20", "method": "THU TIỀN", "amount_vnd": "10"})
            conn.request("POST", "/api/v7/receipts", body=body, headers=base)
            response = conn.getresponse()
            self.assertEqual(response.status, 200)
            self.assertEqual(json.loads(response.read())["function"], "record_receipt")
            self.assertEqual(TrialHandler.runner.calls[-1][2], "dev:fake-demo")
            TrialHandler.localapi.whois.assert_not_called()
            conn.close()
            conn = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=3)
            conn.request("POST", "/api/v7/receipts", body=b"", headers=base | {"Content-Length": str(api.MAX_BODY + 1)})
            response = conn.getresponse()
            self.assertEqual((response.status, json.loads(response.read())["error"]), (413, "BODY_TOO_LARGE"))
            conn.close()
            # Tài sản lấy từ thẻ <script>/<link> của các trang; mất một file quen là regex đã hỏng.
            self.assertLessEqual({"/", "/dashboard-v7.css", "/so-khach-v7-ui.js", "/so-khach-v7-edit-ui.js",
                                  "/sheet-refresh.js", "/sheet-trip-queue-live.js"}, set(api.ASSETS))
            for path in api.ASSETS:
                conn = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=3)
                conn.request("GET", path)
                response = conn.getresponse()
                self.assertEqual(response.status, 200)
                self.assertIn("default-src 'none'", response.getheader("Content-Security-Policy"))
                self.assertTrue(response.read())
                conn.close()
            conn = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=3)
            conn.request("GET", "/so-khach-v7-fixture.js")
            response = conn.getresponse()
            self.assertEqual(response.status, 404)
            response.read()
            conn.close()
        finally:
            server.shutdown()
            server.server_close()
            worker.join(timeout=3)


@unittest.skipUnless(os.getenv("V7_API_DOCKER_TEST") == "1", "set V7_API_DOCKER_TEST=1 for fake Docker harness")
class LedgerDockerTest(unittest.TestCase):
    @contextmanager
    def fake_container(self):
        sys.path.insert(0, str(ROOT / "tools"))
        from test_pg_v7_backend import (
            DATABASE,
            FUNCTIONS,
            IMAGE,
            LABEL_RUN,
            LABEL_TEST,
            LABEL_VALUE,
            SCHEMA,
            Pg,
            inspect_owned,
            inspect_volume,
            run,
        )

        existing = os.getenv("V7_API_CONTAINER")
        if existing:
            runner = api.Psql(existing, DATABASE, "postgres")
            yield runner, Pg(runner.container, "api")
            return

        run_id = uuid.uuid4().hex
        name = f"webdebit-v7-test-{run_id}"
        volume = name
        volume_created = False
        container_id = None
        try:
            run(["docker", "volume", "create", "--label", f"{LABEL_TEST}={LABEL_VALUE}",
                 "--label", f"{LABEL_RUN}={run_id}", volume])
            volume_created = True
            inspect_volume(volume, run_id)
            run(["docker", "run", "--detach", "--name", name,
                 "--label", f"{LABEL_TEST}={LABEL_VALUE}", "--label", f"{LABEL_RUN}={run_id}",
                 "--network", "none", "--volume", f"{volume}:/var/lib/postgresql",
                 "--env", "POSTGRES_HOST_AUTH_METHOD=trust", IMAGE], timeout=240)
            container_id = inspect_owned(name, volume, run_id)
            self.assertIsNotNone(container_id)
            deadline = time.monotonic() + 90
            while time.monotonic() < deadline:
                logs = run(["docker", "logs", name], check=False, timeout=10)
                if "PostgreSQL init process complete; ready for start up." in logs.stdout + logs.stderr:
                    break
                time.sleep(0.25)
            else:
                self.fail("PostgreSQL init marker timed out")
            pg = Pg(name, run_id)
            self.assertEqual(pg.sql("SELECT current_database()", database="postgres").stdout.strip(), "postgres")
            inspect_owned(name, volume, run_id, container_id)
            pg.sql(f"CREATE DATABASE {DATABASE}", database="postgres")
            for source in (SCHEMA, FUNCTIONS):
                run(["docker", "exec", "-i", *pg.env, name, "psql", "-X", "-v",
                     "ON_ERROR_STOP=1", "-U", "postgres", "-d", DATABASE],
                    input_text=source.read_text(encoding="utf-8"))
            yield api.Psql(name, DATABASE, "postgres"), pg
        finally:
            if volume_created:
                owned = inspect_owned(name, volume, run_id, container_id)
                if owned:
                    run(["docker", "rm", "--force", owned])
                inspect_volume(volume, run_id)
                run(["docker", "volume", "rm", volume])

    def test_fake_container_http_commands(self):
        if str(ROOT / "tools") not in sys.path:
            sys.path.insert(0, str(ROOT / "tools"))
        from test_pg_v7_backend import new_book

        with self.fake_container() as (runner, pg):
            customer = new_book(pg, ("2026-01-01", 100), ("2026-02-01", 200))

            class TrialHandler(api.Handler):
                default_actor = "api-harness"

            TrialHandler.runner = runner

            server = api.ThreadingHTTPServer(("127.0.0.1", 0), TrialHandler)
            TrialHandler.port = server.server_port
            worker = threading.Thread(target=server.serve_forever, daemon=True)
            worker.start()
            try:
                def request(method, path, body=None):
                    conn = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=30)
                    headers = {"Tailscale-User-Login": "spoofed@example.test"}
                    if body is not None:
                        headers.update({"Origin": f"http://127.0.0.1:{server.server_port}",
                                        "Content-Type": "application/json"})
                    conn.request(method, path, body=json.dumps(body).encode() if body is not None else None,
                                 headers=headers)
                    response = conn.getresponse()
                    result = response.status, json.loads(response.read())
                    conn.close()
                    return result

                path = f"/api/v7/ledger?customer={customer}"
                status, ledger = request("GET", path)
                self.assertEqual((status, ledger["status"], ledger["version"]), (200, "active", 0))
                self.assertEqual(ledger["total_outstanding_vnd"], "300")
                self.assertTrue(all(isinstance(row["amount_vnd"], str) for row in ledger["opening"]))

                common = {"customer_id": customer, "expected_version": 0}
                current_date = pg.value("SELECT (clock_timestamp() AT TIME ZONE 'Asia/Ho_Chi_Minh')::date")
                current_month = current_date[:7] + "-01"
                trip = {"container": "FAKE-C", "carrier": "FAKE", "from": "A", "to": "B",
                        "date": current_date[8:10] + "/" + current_date[5:7] + "/" + current_date[:4],
                        "unitPriceVnd": "50", "otherFeeVnd": None}
                paste = common | {"idempotency_key": f"api-paste-{customer}",
                                  "debt_month": current_month, "trips": [trip]}
                self.assertEqual(request("POST", "/api/v7/trips/paste", paste | {"actor": "forged"})[0], 422)
                status, first = request("POST", "/api/v7/trips/paste", paste)
                self.assertEqual((status, first["version"], len(first["trip_ids"])), (200, 1, 1))
                self.assertEqual(request("POST", "/api/v7/trips/paste", paste), (200, first))
                status, error = request("POST", "/api/v7/trips/paste",
                                        paste | {"trips": [trip | {"unitPriceVnd": "51"}]})
                self.assertEqual((status, error["error"]), (409, "IDEMPOTENCY_CONFLICT"))
                self.assertEqual(request("POST", "/api/v7/trips/paste", paste | {"idempotency_key": "stale-paste"}),
                                 (409, {"error": "STALE_LEDGER", "message": api.ERRORS["STALE_LEDGER"][1]}))

                receipt = common | {"expected_version": 1, "idempotency_key": f"api-receipt-{customer}",
                                    "date": current_date, "method": "THU TIỀN", "amount_vnd": "120"}
                self.assertEqual(request("POST", "/api/v7/receipts", receipt | {"actor": "forged"})[0], 422)
                status, saved = request("POST", "/api/v7/receipts", receipt)
                self.assertEqual((status, saved["version"]), (200, 2))
                self.assertTrue(all(isinstance(line["amount_vnd"], str) for line in saved["allocations"]))
                self.assertEqual(request("POST", "/api/v7/receipts", receipt), (200, saved))
                status, error = request("POST", "/api/v7/receipts", receipt | {"amount_vnd": "121"})
                self.assertEqual((status, error["error"]), (409, "IDEMPOTENCY_CONFLICT"))
                status, error = request("POST", "/api/v7/receipts", receipt | {"idempotency_key": "stale-receipt"})
                self.assertEqual((status, error["error"]), (409, "STALE_LEDGER"))
                status, ledger = request("GET", path)
                self.assertEqual((status, ledger["version"], ledger["total_outstanding_vnd"]), (200, 2, "230"))
                self.assertEqual(ledger["receipts"][0]["amount_vnd"], "120")
                self.assertTrue(all(isinstance(line["amount_vnd"], str)
                                    for line in ledger["receipts"][0]["allocations"]))
                self.assertEqual(pg.value(f"SELECT count(*) FROM sokhach.trip WHERE customer_id={customer}"), "1")
                self.assertEqual(pg.value(f"SELECT count(*) FROM sokhach.receipt WHERE customer_id={customer}"), "1")
                self.assertEqual(pg.value(f"SELECT count(*) FROM sokhach.event WHERE customer_id={customer} "
                                          "AND kind IN ('paste','receipt')"), "2")
                self.assertEqual(pg.value(f"SELECT string_agg(DISTINCT actor, ',') FROM sokhach.event "
                                          f"WHERE customer_id={customer} AND kind IN ('paste','receipt')"), "dev:api-harness")
            finally:
                server.shutdown()
                server.server_close()
                worker.join(timeout=3)


class ReceiptImageApiTest(unittest.TestCase):
    """CHUNG-TU-01: đính/gỡ/xem ảnh chứng từ; ảnh giả do test tự tạo."""

    PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 24
    WEBP = b"RIFF\x10\x00\x00\x00WEBPVP8 " + b"\x00" * 8

    def setUp(self):
        self.common = {"customer_id": 1, "expected_version": 3, "idempotency_key": "image-request"}
        self.headers = {"Host": "127.0.0.1:8780", "Origin": "http://127.0.0.1:8780", "Content-Type": "application/json"}

    def body(self, data=None, content_type="image/png", **extra):
        encoded = base64.b64encode(self.PNG if data is None else data).decode()
        return self.common | {"pid": "P-0001", "content_type": content_type, "data_base64": encoded} | extra

    def call(self, method, path, body=None):
        runner = FakePsql()
        status, _ = api.handle(method, path, self.headers, json.dumps(body or {}).encode() if method == "POST" else b"",
                               runner, port=8780, host="127.0.0.1", actor="server-image-actor")
        self.assertEqual(status, 200)
        return runner.calls[-1]

    def rejected(self, code, method, path, body=None, raw=None):
        with self.assertRaises(api.ApiError) as caught:
            api.handle(method, path, self.headers, raw if raw is not None else json.dumps(body or {}).encode(),
                       FakePsql(), port=8780, host="127.0.0.1", actor="server-image-actor")
        self.assertEqual(caught.exception.code, code)

    def test_routes_reach_functions(self):
        self.assertEqual(self.call("POST", "/api/v7/receipts/images", self.body())[0], "attach_receipt_image")
        self.assertEqual(self.call("POST", "/api/v7/receipts/images", self.body(self.WEBP, "image/webp"))[0], "attach_receipt_image")
        name, payload, actor = self.call("POST", "/api/v7/receipts/images/remove", self.common | {"image_id": 9, "reason": "Đính nhầm"})
        self.assertEqual((name, payload["image_id"], actor), ("remove_receipt_image", 9, "server-image-actor"))
        self.assertEqual(self.call("GET", "/api/v7/receipt-images?customer=1")[:2], ("list_receipt_images", {"customer_id": 1}))
        self.assertEqual(self.call("GET", "/api/v7/receipt-image?customer=1&id=9")[:2],
                         ("get_receipt_image", {"customer_id": 1, "image_id": 9}))
        sha = "a" * 64
        self.assertEqual(self.call("GET", f"/api/v7/receipt-images/find?sha256={sha}")[:2], ("find_receipt_image", {"sha256": sha}))
        self.assertIn("(j->>'image_id')::bigint", api.SQL["remove_receipt_image"])

    def test_rejects_bad_images_and_requests(self):
        path = "/api/v7/receipts/images"
        self.rejected("IMAGE_INVALID", "POST", path, self.body(b"%PDF-1.7 fake"))
        self.rejected("IMAGE_INVALID", "POST", path, self.body(self.PNG, "image/webp"))
        self.rejected("IMAGE_INVALID", "POST", path, self.body(content_type="image/gif"))
        self.rejected("IMAGE_INVALID", "POST", path, self.body() | {"data_base64": "AAA'; DROP TABLE x;--"})
        self.rejected("IMAGE_INVALID", "POST", path, self.body() | {"data_base64": "AAA"})
        self.rejected("IMAGE_TOO_LARGE", "POST", path, self.body(self.PNG + b"\x00" * api.MAX_IMAGE_BYTES))
        self.rejected("INVALID_REQUEST", "POST", path, self.body(pid=" "))
        self.rejected("INVALID_REQUEST", "POST", path, self.body(extra_field=1))
        remove = "/api/v7/receipts/images/remove"
        self.rejected("IMAGE_REMOVE_REASON_REQUIRED", "POST", remove, self.common | {"image_id": 9, "reason": "  "})
        self.rejected("INVALID_REQUEST", "POST", remove, self.common | {"image_id": 0, "reason": "x"})
        for target in ("/api/v7/receipt-images", "/api/v7/receipt-images?customer=0", "/api/v7/receipt-image?customer=1",
                       "/api/v7/receipt-image?customer=1&id=1&id=2", "/api/v7/receipt-images/find?sha256=ABC"):
            with self.subTest(target=target):
                self.rejected("INVALID_REQUEST", "GET", target, raw=b"")

    def test_body_limit_is_larger_only_for_image_path(self):
        big = b"{" + b" " * (api.MAX_BODY + 10) + b"}"
        self.rejected("BODY_TOO_LARGE", "POST", "/api/v7/receipts", raw=big)
        self.rejected("BODY_TOO_LARGE", "POST", "/api/v7/receipts/images", raw=b" " * (api.MAX_IMAGE_BODY + 1))
        self.rejected("INVALID_REQUEST", "POST", "/api/v7/receipts/images", raw=big)

    def test_image_goes_through_stdin_not_command_line(self):
        ok = Mock(returncode=0, stdout='{"image":{"id":1},"version":4}', stderr="")
        body = self.body()
        with patch.object(api.subprocess, "run", return_value=ok) as run:
            api._PsqlRunner()._run_psql(["fake-psql"], "attach_receipt_image", body, "server-image-actor")
        argv, kwargs = run.call_args[0][0], run.call_args[1]
        self.assertFalse(any(body["data_base64"] in arg for arg in argv))
        self.assertIn(f"decode('{body['data_base64']}', 'base64')", kwargs["input"])
        self.assertNotIn(api.IMAGE_MARK, kwargs["input"])
        with patch.object(api.subprocess, "run", return_value=ok), self.assertRaises(api.ApiError) as caught:
            api._PsqlRunner()._run_psql(["fake-psql"], "attach_receipt_image", body | {"data_base64": "x'--"}, "a")
        self.assertEqual(caught.exception.code, "IMAGE_INVALID")

    def test_image_error_mapping(self):
        for code in ("IMAGE_INVALID", "IMAGE_TOO_LARGE", "IMAGE_LIMIT", "IMAGE_DUPLICATE", "IMAGE_NOT_FOUND",
                     "IMAGE_ALREADY_REMOVED", "IMAGE_REMOVE_REASON_REQUIRED", "RECEIPT_ALREADY_VOID"):
            with self.subTest(code=code), patch.object(api.subprocess, "run") as run:
                run.return_value = Mock(returncode=1, stdout="", stderr=f"psql:<stdin>:1: ERROR:  P0001: {code}\n")
                with self.assertRaises(api.ApiError) as caught:
                    api._PsqlRunner()._run_psql([], "remove_receipt_image", self.common | {"image_id": 1, "reason": "x"}, "a")
                self.assertEqual(caught.exception.code, code)


if __name__ == "__main__":
    unittest.main()

