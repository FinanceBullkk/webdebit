"""Bot Zalo (ZALO-BOT-01) PR-2: lớp gọi API chỉ GET, công cụ tính chỉ nhận số từ công cụ, trần chi phí theo ngày. Không cần mạng."""

import datetime as dt
import io
import json
import re
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from zalo_bot import budget, calc, webapi  # noqa: E402

VN = ZoneInfo("Asia/Ho_Chi_Minh")
NOW = dt.datetime(2026, 11, 22, 10, 0, tzinfo=VN).timestamp()
DEBT = webapi.Route("/api/v7/dashboard/debt", {"customer": re.compile(r"\d{1,9}")})
MACHINE = webapi.Route("/api/v7/machine/now", admin=True)


class Response(io.BytesIO):
    def __init__(self, body: bytes, status: int = 200):
        super().__init__(body)
        self.status = status


class Opener:
    def __init__(self, body=b'{"ok": true}', status=200, error=None):
        self.body, self.status, self.error, self.requests = body, status, error, []

    def open(self, request, timeout=None):
        self.requests.append(request)
        if self.error:
            raise self.error
        return Response(self.body, self.status)


class WebApiTests(unittest.TestCase):
    def test_get_sends_only_get_with_login_and_loopback_host(self):
        opener = Opener()
        api = webapi.WebApi(opener=opener)
        self.assertEqual(api.get(DEBT, {"customer": "12"}, login="chu@example.com", role="user"), {"ok": True})
        request = opener.requests[0]
        self.assertEqual((request.get_method(), request.full_url), ("GET", "http://127.0.0.1:8780/api/v7/dashboard/debt?customer=12"))
        self.assertEqual(request.get_header("Tailscale-user-login"), "chu@example.com")
        self.assertEqual(request.get_header("Host"), "127.0.0.1:8780")
        self.assertIsNone(request.data)

    def test_unknown_or_malformed_params_are_refused_before_any_call(self):
        opener = Opener()
        api = webapi.WebApi(opener=opener)
        for params in ({"customer": "12&x=1"}, {"customer": "abc"}, {"month": "2026-11"}, {"customer": 12}):
            with self.subTest(params=params), self.assertRaises(webapi.ApiError) as caught:
                api.get(DEBT, params, login="chu@example.com", role="admin")
            self.assertEqual(caught.exception.code, "bad_param")
        self.assertEqual(opener.requests, [])

    def test_admin_route_and_identity_checks(self):
        api = webapi.WebApi(opener=Opener())
        with self.assertRaises(webapi.ApiError) as caught:
            api.get(MACHINE, login="chu@example.com", role="user")
        self.assertEqual(caught.exception.code, "forbidden_role")
        for login, role in (("không phải login", "admin"), ("chu@example.com", "boss")):
            with self.subTest(login=login, role=role), self.assertRaises(webapi.ApiError):
                api.get(DEBT, login=login, role=role)

    def test_errors_become_short_codes(self):
        cases = {urllib.error.HTTPError("u", 403, "x", {}, None): "forbidden", urllib.error.HTTPError("u", 502, "x", {}, None): "server_error",
                 urllib.error.URLError("down"): "unreachable", TimeoutError(): "unreachable"}
        for error, code in cases.items():
            with self.subTest(code=code), self.assertRaises(webapi.ApiError) as caught:
                webapi.WebApi(opener=Opener(error=error)).get(DEBT, login="chu@example.com", role="user")
            self.assertEqual(caught.exception.code, code)
        for opener, code in ((Opener(body=b"<html>"), "bad_json"), (Opener(status=302), "http_error"),
                             (Opener(body=b"1" * (webapi.MAX_BYTES + 1)), "too_large")):
            with self.subTest(code=code), self.assertRaises(webapi.ApiError) as caught:
                webapi.WebApi(opener=opener).get(DEBT, login="chu@example.com", role="user")
            self.assertEqual(caught.exception.code, code)

    def test_base_must_be_local(self):
        for base in ("https://127.0.0.1:8780", "http://hao.example:8780", "http://127.0.0.1", "http://127.0.0.1:8780/api"):
            with self.subTest(base=base), self.assertRaises(ValueError):
                webapi.WebApi(base)


class CalcTests(unittest.TestCase):
    ALLOWED = frozenset({350_000_000, 120_500_000, 45_000})

    def test_sum_difference_and_percent_on_tool_values(self):
        self.assertEqual(calc.calculate("cong", ["350000000", 45000], self.ALLOWED), {"ket_qua_vnd": "350045000"})
        self.assertEqual(calc.calculate("tru", ["350000000", "120500000"], self.ALLOWED), {"ket_qua_vnd": "229500000"})
        self.assertEqual(calc.calculate("ti_le", ["120500000", "350000000"], self.ALLOWED), {"ti_le_phan_tram": "34,4"})

    def test_numbers_not_from_tools_cannot_be_laundered(self):
        with self.assertRaises(calc.CalcError) as caught:
            calc.calculate("cong", ["1", "349999999"], self.ALLOWED)
        self.assertEqual(str(caught.exception), "value_not_from_tools")
        for op, values in (("nhan", ["45000"]), ("cong", []), ("cong", [True]), ("ti_le", ["45000"]), ("cong", ["4,5"])):
            with self.subTest(op=op, values=values), self.assertRaises(calc.CalcError):
                calc.calculate(op, values, self.ALLOWED)


class BudgetTests(unittest.TestCase):
    def test_cost_per_model_in_nano_usd(self):
        usage = {"input_tokens": 1000, "output_tokens": 500, "cache_read_input_tokens": 20000, "cache_creation_input_tokens": 3000,
                 "cache_creation": {"ephemeral_1h_input_tokens": 1000}}
        # Opus 5.5: 1000×4000 + 500×20000 + 2000×5000 + 1000×8000 + 20000×200 = 36 000 000 nano-USD = 0,036 USD
        self.assertEqual(budget.cost("claude-opus-5-5", usage), 36_000_000)
        self.assertEqual(budget.cost("claude-haiku-5-5", {"input_tokens": 1000, "output_tokens": 1000}), 600_000)
        self.assertEqual(budget.cost("claude-haiku-5-5", {"input_tokens": 150_000}), 75_000_000)   # trên 100K: bảng giá dài
        with self.assertRaises(KeyError):
            budget.cost("gpt-x", usage)

    def test_daily_cap_resets_each_vietnam_day_and_survives_restart(self):
        path = Path(tempfile.mkdtemp()) / "budget.json"
        cap = budget.Budget(path, cap_usd=1)
        self.assertTrue(cap.allows(NOW))
        cap.add("claude-opus-5-5", {"output_tokens": 50_000}, NOW)          # 1 USD
        self.assertFalse(cap.allows(NOW + 60))
        self.assertFalse(budget.Budget(path, cap_usd=1).allows(NOW + 120))
        tomorrow = dt.datetime(2026, 11, 23, 0, 1, tzinfo=VN).timestamp()
        self.assertTrue(budget.Budget(path, cap_usd=1).allows(tomorrow))
        self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["spent_nano_usd"], 1_000_000_000)


if __name__ == "__main__":
    unittest.main()
