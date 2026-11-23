"""AI chỉ nhận một gói chứng cứ đã xem trước; không ghi sổ hoặc gọi mạng khi chưa đồng ý."""
import io
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parents[1] / "web"))
import v7_ai_explain as ai
import v7_ledger_api as api
from v7_api_validate import ApiError


class Runner:
    def __init__(self):
        self.calls = []

    def run(self, function, payload, actor):
        self.calls.append(function)
        raise AssertionError("Unexpected DB access")


REPORT = {"version": 1, "checked_at": "2026-11-10T15:00:00+07:00", "customers": [{"customer_id": 7, "customer": "KHACH MAU", "status": "LECH_TONG", "reason": "NO_EXACT_FIX", "hints": []}]}
STATEMENT = {"customer_id": 7, "checked_at": REPORT["checked_at"], "version": 3, "prices_sha256": "a"*64, "receipts_sha256": "b"*64,
             "sheet_total_vnd": "100", "web_vnd": "120", "web_ahead_vnd": "0", "groups": [{"kind": "receipts", "month": None, "delta_vnd": "-20", "rows": [{"source_row": 9, "amount_vnd": "20", "note": "private"}]}]}


class AiTests(unittest.TestCase):
    def setUp(self):
        ai._calls.clear()
        self.runner = Runner()
        self.patches = [patch.object(ai, "reconcile_result", return_value=REPORT), patch.object(ai.v7_api_doi_chieu, "statement", return_value=STATEMENT), patch.object(ai, "_key", return_value="fake-key")]
        for item in self.patches:
            item.start()
        self.addCleanup(lambda: [item.stop() for item in reversed(self.patches)])

    def test_preview_bounded_and_no_notes(self):
        result = ai.preview(7, self.runner, "actor")
        self.assertTrue(result["enabled"])
        self.assertEqual(result["packet"]["groups"][0]["rows"][0]["source_row"], 9)
        self.assertNotIn("private", json.dumps(result))
        self.assertEqual(self.runner.calls, [])

    def test_consent_and_stale_before_network(self):
        with patch.object(ai, "urlopen") as network:
            for body in ({"customer_id": 7, "fingerprint": "0"*64, "consent": False}, {"customer_id": 7, "fingerprint": "0"*64, "consent": True}):
                with self.assertRaises(ApiError):
                    ai.explain(json.dumps(body).encode(), self.runner, "actor")
            with self.assertRaises(ApiError):
                ai.explain(b'{"customer_id":7,"customer_id":8,"fingerprint":"' + b"0"*64 + b'","consent":true}', self.runner, "actor")
            network.assert_not_called()
        self.assertEqual(self.runner.calls, [])

    def test_changed_snapshot_blocks_send(self):
        fingerprint = ai.preview(7, self.runner, "actor")["fingerprint"]
        changed = {**STATEMENT, "version": 4}
        with patch.object(ai.v7_api_doi_chieu, "statement", return_value=changed), patch.object(ai, "urlopen") as network:
            with self.assertRaises(ApiError) as caught:
                ai.explain(json.dumps({"customer_id": 7, "fingerprint": fingerprint, "consent": True}).encode(), self.runner, "actor")
            network.assert_not_called()
        self.assertEqual(caught.exception.status, 409)

    def test_report_and_statement_total_must_match(self):
        changed = {**REPORT, "customers": [{**REPORT["customers"][0], "web_total_vnd": "999"}]}
        with patch.object(ai, "reconcile_result", return_value=changed), self.assertRaises(ApiError) as caught:
            ai.preview(7, self.runner, "actor")
        self.assertEqual(caught.exception.status, 409)

    def test_missing_key_disables_preview_and_send(self):
        with patch.object(ai, "_key", return_value=None), patch.object(ai, "urlopen") as network:
            self.assertFalse(ai.preview(7, self.runner, "actor")["enabled"])
            with self.assertRaises(ApiError) as caught:
                ai.explain(json.dumps({"customer_id": 7, "fingerprint": "f"*64, "consent": True}).encode(), self.runner, "actor")
            network.assert_not_called()
        self.assertEqual(caught.exception.status, 503)

    def test_single_api_call_and_usage(self):
        fingerprint = ai.preview(7, self.runner, "actor")["fingerprint"]
        answer = io.BytesIO(json.dumps({"content": [{"type": "text", "text": "Cần kiểm dòng 9."}], "usage": {"input_tokens": 10, "output_tokens": 5}}).encode())
        with patch.object(ai, "urlopen", return_value=answer) as network:
            status, body = ai.explain(json.dumps({"customer_id": 7, "fingerprint": fingerprint, "consent": True}).encode(), self.runner, "actor")
        self.assertEqual(status, 200)
        self.assertEqual(body["usage"], {"input_tokens": 10, "output_tokens": 5})
        self.assertEqual(network.call_count, 1)
        self.assertEqual(network.call_args.args[0].full_url, "https://api.anthropic.com/v1/messages")
        self.assertEqual(self.runner.calls, [])
        sent = json.loads(network.call_args.args[0].data)
        self.assertEqual((sent["model"], sent["max_tokens"], sent["output_config"]), ("claude-haiku-5-5", 2000, {"effort": "low"}))
        self.assertTrue({"temperature", "top_p", "top_k", "thinking"}.isdisjoint(sent))

    def test_model_override_is_checked_against_the_list_before_network(self):
        fingerprint = ai.preview(7, self.runner, "actor")["fingerprint"]
        request = json.dumps({"customer_id": 7, "fingerprint": fingerprint, "consent": True}).encode()
        with patch.dict(ai.os.environ, {"ANTHROPIC_MODEL": "claude-haiku-4-5-20251001"}), patch.object(ai, "urlopen") as network:
            with self.assertRaises(ApiError) as caught:
                ai.explain(request, self.runner, "actor")
            network.assert_not_called()
        self.assertEqual((caught.exception.status, caught.exception.code), (503, "AI_MODEL_INVALID"))
        answer = io.BytesIO(json.dumps({"content": [{"type": "text", "text": "ok"}], "usage": {}}).encode())
        with patch.dict(ai.os.environ, {"ANTHROPIC_MODEL": "claude-sonnet-5-5"}), patch.object(ai, "urlopen", return_value=answer) as network:
            ai.explain(request, self.runner, "other-actor")
        self.assertEqual(json.loads(network.call_args.args[0].data)["model"], "claude-sonnet-5-5")

    def test_refusal_and_thinking_only_answers_are_errors(self):
        fingerprint = ai.preview(7, self.runner, "actor")["fingerprint"]
        request = json.dumps({"customer_id": 7, "fingerprint": fingerprint, "consent": True}).encode()
        for actor, reply, code in (("a1", {"stop_reason": "refusal", "content": [], "usage": {}}, "AI_REFUSED"),
                                   ("a2", {"stop_reason": "max_tokens", "content": [{"type": "thinking", "thinking": ""}], "usage": {}},
                                    "AI_EMPTY_RESPONSE")):
            with patch.object(ai, "urlopen", return_value=io.BytesIO(json.dumps(reply).encode())), self.assertRaises(ApiError) as caught:
                ai.explain(request, self.runner, actor)
            self.assertEqual(caught.exception.code, code)

    def test_rate_limit(self):
        ai._calls["actor"] = [ai.time.monotonic()]
        with self.assertRaises(ApiError) as caught:
            ai._reserve("actor")
        self.assertEqual(caught.exception.status, 429)

    def test_http_routes_keep_origin_guard(self):
        args = {"port": 8765, "host": "127.0.0.1", "actor": "actor"}
        with patch.object(api.v7_ai_explain, "preview", return_value={"enabled": False}) as preview:
            status, body = api.handle("GET", "/api/v7/ai/preview?customer=7", {"host": "127.0.0.1:8765"}, b"", self.runner, **args)
        self.assertEqual((status, body), (200, {"enabled": False}))
        preview.assert_called_once()
        with patch.object(api.v7_ai_explain, "explain", return_value=(200, {"text": "ok"})) as explain:
            with self.assertRaises(ApiError):
                api.handle("POST", "/api/v7/ai/explain", {"host": "127.0.0.1:8765", "origin": "http://evil.test", "content-type": "application/json"}, b"{}", self.runner, **args)
            explain.assert_not_called()
            status, _ = api.handle("POST", "/api/v7/ai/explain", {"host": "127.0.0.1:8765", "origin": "http://127.0.0.1:8765", "content-type": "application/json"}, b"{}", self.runner, **args)
            self.assertEqual(status, 200)
        self.assertEqual(self.runner.calls, [])


if __name__ == "__main__":
    unittest.main()
