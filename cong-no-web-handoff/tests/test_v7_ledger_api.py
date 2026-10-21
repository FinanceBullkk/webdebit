"""V7 HTTP boundary checks; Docker case runs only on an isolated fake harness."""

import http.client
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
from unittest.mock import patch

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
             patch.object(api.Handler, "real_copy", False), patch.object(api.Handler, "demo", False):
            api.main()
            self.assertTrue(api.Handler.real_copy)
            server.return_value.serve_forever.assert_called_once()
        with patch.object(sys, "argv", ["v7_ledger_api.py", "--container", "fake", "--real-copy", "--demo"]), \
             patch.object(api, "Psql") as runner:
            with self.assertRaises(SystemExit) as caught:
                api.main()
            self.assertEqual(caught.exception.code, 2)
            runner.assert_not_called()

    def setUp(self):
        self.runner = FakePsql()
        self.headers = {"Host": "127.0.0.1:8780", "Origin": "http://127.0.0.1:8780",
                        "Content-Type": "application/json"}
        self.common = {"customer_id": 1, "expected_version": 0, "idempotency_key": "same-request"}

    def call(self, path, body, headers=None):
        return api.handle("POST", path, headers or self.headers, json.dumps(body).encode(), self.runner,
                          port=8780, host="127.0.0.1", default_actor="configured")

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
                    host="127.0.0.1", default_actor="configured", trust_header=True)
                self.assertEqual(status, 200)
                self.assertEqual(self.runner.calls[-1][2], "trusted@example.test")

    def test_get_and_host_origin(self):
        status, data = api.handle("GET", "/api/v7/customers", self.headers, b"", self.runner,
                                  port=8780, host="127.0.0.1", default_actor="configured")
        self.assertEqual((status, data["function"]), (200, "list_customers"))
        self.assertEqual(self.runner.calls[-1], ("list_customers", {}, "configured"))
        self.runner.calls.clear()
        self.error(404, "NOT_FOUND", lambda: api.handle("GET", "/api/v7/customers?all=1",
                   self.headers, b"", self.runner, port=8780, host="127.0.0.1", default_actor="configured"))
        status, data = api.handle("GET", "/api/v7/ledger?customer=1", self.headers, b"", self.runner,
                                  port=8780, host="127.0.0.1", default_actor="configured")
        self.assertEqual((status, data["function"]), (200, "get_ledger"))
        status, data = api.handle("GET", "/api/v7/ledger?customer=1", self.headers, b"", self.runner,
                                  port=8780, host="127.0.0.1", default_actor="configured", demo=True)
        self.assertEqual((status, data["demo"]), (200, True))
        status, data = api.handle("GET", "/api/v7/ledger?customer=1", self.headers, b"", self.runner,
                                  port=8780, host="127.0.0.1", default_actor="configured", real_copy=True)
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
                   self.headers, b"", self.runner, port=8780, host="127.0.0.1", default_actor="configured"))
        self.error(422, "INVALID_REQUEST", lambda: api.handle("GET", "/api/v7/ledger?customer=" + "9" * 5000,
                   self.headers, b"", self.runner, port=8780, host="127.0.0.1", default_actor="configured"))

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
                   host="127.0.0.1", default_actor="configured"))

    def test_content_type_and_body_size(self):
        path = "/api/v7/receipts"
        self.error(415, "INVALID_CONTENT_TYPE", lambda: api.handle("POST", path,
                   self.headers | {"Content-Type": "text/plain"}, b"{}", self.runner,
                   port=8780, host="127.0.0.1", default_actor="configured"))
        self.error(413, "BODY_TOO_LARGE", lambda: api.handle("POST", path, self.headers,
                   b"x" * (api.MAX_BODY + 1), self.runner, port=8780,
                   host="127.0.0.1", default_actor="configured"))

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


class LedgerHttpTest(unittest.TestCase):
    def test_bounded_http_with_fake_psql(self):
        class TrialHandler(api.Handler):
            runner = FakePsql()
            demo = True

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
            self.assertEqual(TrialHandler.runner.calls[-1][2], "v7-test")
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
                                          f"WHERE customer_id={customer} AND kind IN ('paste','receipt')"), "api-harness")
            finally:
                server.shutdown()
                server.server_close()
                worker.join(timeout=3)


if __name__ == "__main__":
    unittest.main()
