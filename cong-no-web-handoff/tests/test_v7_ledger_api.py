"""V7 HTTP boundary checks; Docker case runs only on an isolated fake harness."""

import http.client
import io
import json
import os
import subprocess
import sys
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


class FakePsql:
    def __init__(self):
        self.calls = []

    def run(self, function, payload, actor):
        self.calls.append((function, payload, actor))
        return {"function": function, "version": payload.get("expected_version", 0)}


class LedgerApiTest(unittest.TestCase):
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
                conn.request(method, path, body=json.dumps(payload or {}).encode(), headers=headers)
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
        charges = sql.split("'charges_vnd',", 1)[1].split("'received_vnd'", 1)[0]
        self.assertIn("sokhach.opening_balance", charges)
        self.assertIn("cc.status='active' AND c.status='active'", charges)
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

    def test_get_and_host_origin(self):
        status, data = api.handle("GET", "/api/v7/customers", self.headers, b"", self.runner,
                                  port=8780, host="127.0.0.1", default_actor="ignored", source_ip="127.0.0.1", source_port=43210)
        self.assertEqual((status, data["function"]), (200, "list_customers"))
        self.assertEqual(self.runner.calls[-1], ("list_customers", {}, "configured"))
        self.assertEqual(api.SQL["list_customers"], "SELECT sokhach.list_customers();")
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
            for path in ("/so-khach-v7-live.html", "/so-khach-v7-ui.js",
                         "/so-khach-v7-model.js", "/so-khach-v7-api.js"):
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


if __name__ == "__main__":
    unittest.main()
