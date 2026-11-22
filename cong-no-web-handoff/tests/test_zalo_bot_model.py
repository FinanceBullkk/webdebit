"""Vòng gọi model của bot Zalo (ZALO-BOT-01 PR-2b) với model giả và API giả: gọi công cụ, điền số, kiểm số, trả lại một lần,
dòng nguồn và cảnh báo lệch Sheet do bot thêm, trần chi phí, giới hạn lượt gọi; và bộ não gửi câu trả lời qua kênh."""

import asyncio
import datetime as dt
import io
import json
import sys
import tempfile
import unittest
import urllib.parse
from pathlib import Path
from types import SimpleNamespace as NS
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from zalo_bot import brain, budget, config, core, model, protocol, tools, webapi  # noqa: E402

VN = ZoneInfo("Asia/Ho_Chi_Minh")
NOW = dt.datetime(2026, 11, 22, 15, 0, tzinfo=VN).timestamp()
ADMIN = config.User("1111", "chu@example.com", "admin")
USAGE = NS(input_tokens=1000, output_tokens=200, cache_read_input_tokens=0, cache_creation_input_tokens=0, cache_creation=None)
DATA = {
    "/api/v7/customers": {"customers": [{"id": 7, "name": "KHACH A", "display_name": "Khách A"}, {"id": 9, "name": "KHACH B"}]},
    "/api/v7/dashboard/debt": {"customers": [{"customer_id": 7, "outstanding_vnd": "350000000", "overdue_vnd": "120500000"}]},
    "/api/v7/ledger?customer=9": {"total_outstanding_vnd": "45000"},
    "/api/v7/inbox": {"reconcile": {"checked_at": "2026-11-22T10:05:00+07:00", "matched_ids": [7],
                                    "customers": [{"customer_id": 9, "status": "LECH_TONG", "reason": "HELD", "difference_vnd": "45000"}]}},
}


class Opener:
    def open(self, request, timeout=None):
        parts = urllib.parse.urlsplit(request.full_url)
        return io.BytesIO(json.dumps(DATA[parts.path + (f"?{parts.query}" if parts.query else "")]).encode("utf-8"))


def tool_use(*calls):
    return NS(stop_reason="tool_use", usage=USAGE,
              content=[NS(type="thinking", thinking=""), *(NS(type="tool_use", id=f"u{i}", name=n, input=a) for i, (n, a) in enumerate(calls))])


def final(text, stop="end_turn"):
    return NS(stop_reason=stop, usage=USAGE, content=[NS(type="text", text=text)])


class FakeClient:
    def __init__(self, *script):
        self.script = list(script)
        self.requests = []
        self.messages = self

    def create(self, **kwargs):
        self.requests.append({**kwargs, "messages": list(kwargs["messages"])})
        return self.script.pop(0)


class AnswererTests(unittest.TestCase):
    def setUp(self):
        tools.reset_cache()
        self.dir = Path(tempfile.mkdtemp())
        self.budget = budget.Budget(self.dir / "budget.json", cap_usd=3)

    def answer(self, client, question="khách A còn nợ bao nhiêu"):
        answerer = model.Answerer(client, model="claude-opus-5-5", effort="medium", budget=self.budget,
                                  api=webapi.WebApi(opener=Opener()), link_base="https://web.example", clock=lambda: NOW)
        return answerer.answer(ADMIN, question)

    def test_tools_then_filled_answer_with_source_lines_added_by_the_bot(self):
        client = FakeClient(tool_use(("tim_khach", {"ten": "khach a"})), tool_use(("no_khach", {"khach_id": 7})),
                            final("Khách {t2.ten} còn nợ {t2.no_vnd}, quá hạn {t2.qua_han_vnd}."))
        out = self.answer(client)
        self.assertEqual(out.outcome, "answered")
        self.assertEqual(out.text, "Khách Khách A còn nợ 350.000.000 đ, quá hạn 120.500.000 đ.\n\n"
                                   "Lưu ý: lần đối soát với Sheet đã cũ (10:05 22/11).\n"
                                   "Nguồn: Sổ khách · dữ liệu lúc 15:00 22/11\nMở: https://web.example/so-khach-v7-live.html?customer=7")
        self.assertEqual((out.tools, out.steps, out.cost_nano_usd), (["tim_khach", "no_khach"], 3, 3 * 8_000_000))
        second = client.requests[1]
        self.assertEqual(json.loads(second["messages"][-1]["content"][0]["content"])["ma"], "t1")
        for before, after in zip(client.requests, client.requests[1:], strict=False):
            self.assertEqual(after["messages"][: len(before["messages"])], before["messages"])   # chỉ thêm vào cuối
        self.assertEqual(second["output_config"], {"effort": "medium"})
        self.assertEqual(second["system"][0]["cache_control"], {"type": "ephemeral"})
        self.assertIn("tinh", [tool["name"] for tool in second["tools"]])

    def test_typed_number_is_sent_back_once_then_fixed(self):
        client = FakeClient(tool_use(("no_khach", {"khach_id": 7})), final("Khách nợ 351.000.000 đ."), final("Khách nợ {t1.no_vnd}."))
        out = self.answer(client)
        self.assertEqual(out.outcome, "answered")
        self.assertTrue(out.text.startswith("Khách nợ 350.000.000 đ."))
        self.assertIn("Bộ kiểm số chặn bản nháp", client.requests[2]["messages"][-1]["content"])

    def test_wrong_twice_says_not_sure(self):
        client = FakeClient(tool_use(("no_khach", {"khach_id": 7})), final("Nợ 1 tỷ."), final("Nợ {t1.khong_co_vnd}."))
        out = self.answer(client)
        self.assertEqual((out.outcome, out.text), ("not_sure", model.NOT_SURE))
        self.assertTrue(out.problems[0].startswith("cho_trong_sai"))

    def test_calculator_on_tool_values(self):
        client = FakeClient(tool_use(("no_khach", {"khach_id": 7})), tool_use(("tinh", {"phep": "tru", "so": ["350000000", "120500000"]})),
                            final("Phần chưa quá hạn {t2.ket_qua_vnd}."))
        self.assertTrue(self.answer(client).text.startswith("Phần chưa quá hạn 229.500.000 đ."))

    def test_lech_sheet_warning_is_added_by_the_bot(self):
        out = self.answer(FakeClient(tool_use(("no_khach", {"khach_id": 9})), final("Sổ {t1.ten} nợ {t1.no_vnd}.")))
        self.assertIn("Lưu ý: KHACH B đang lệch Sheet 45.000 đ (đối soát 10:05 22/11; máy đoán: HELD). Số trên web chưa chắc.", out.text)

    def test_refusal_budget_and_tool_call_limit(self):
        self.assertEqual(self.answer(FakeClient(final("", stop="refusal"))).outcome, "refused")
        many = FakeClient(tool_use(*[("tim_khach", {"ten": "a"})] * 9), final("Chưa tra được."))
        out = self.answer(many)
        last_results = many.requests[1]["messages"][-1]["content"]
        self.assertEqual(json.loads(last_results[-1]["content"])["loi"], "qua_so_lan_tra")
        self.assertEqual(out.outcome, "answered")
        self.budget.add("claude-opus-5-5", {"output_tokens": 200_000}, NOW)    # 4 USD > trần 3 USD
        idle = FakeClient()
        self.assertEqual(self.answer(idle).outcome, "over_budget")
        self.assertEqual(idle.requests, [])

    def test_price_table_covers_every_allowed_model(self):
        self.assertEqual(set(budget.PRICES), set(config.MODELS))


class ConfigTests(unittest.TestCase):
    def test_model_settings_are_validated(self):
        cfg = config.from_env({"WEBDEBIT_ZALO_BOT_MODEL": "claude-haiku-5-5", "WEBDEBIT_ZALO_BOT_CAP_USD": "2",
                               "WEBDEBIT_ZALO_BOT_LINK_BASE": "https://web.example:8443"})
        self.assertEqual((cfg.model, cfg.effort, cfg.cap_usd, cfg.link_base), ("claude-haiku-5-5", "medium", 2, "https://web.example:8443"))
        self.assertIsNone(config.from_env({}).model)
        for env in ({"WEBDEBIT_ZALO_BOT_MODEL": "gpt-x"}, {"WEBDEBIT_ZALO_BOT_EFFORT": "turbo"}, {"WEBDEBIT_ZALO_BOT_CAP_USD": "0"},
                    {"WEBDEBIT_ZALO_BOT_LINK_BASE": "http://web.example"}):
            with self.subTest(env=env), self.assertRaises(config.ConfigError):
                config.from_env(env)


class FakeWriter:
    def __init__(self):
        self.lines = []

    def write(self, data):
        self.lines.append(json.loads(data))

    async def drain(self):
        return None


class ServiceAnswerTests(unittest.TestCase):
    def test_question_goes_to_the_answerer_and_reply_is_sent_and_logged(self):
        base = Path(tempfile.mkdtemp())
        cfg = config.Config(enabled=True, users_file=base / "u.json", socket=base / "s.sock", state_dir=base / "state",
                            release_link=base / "cur", model="claude-haiku-5-5")
        answerer = NS(answer=lambda user, text: model.Answer(f"Đã tra: {text}", "answered", tools=["no_khach"], cost_nano_usd=5))
        service = brain.Service(cfg, {"1111": ADMIN}, core.Memory(), clock=lambda: NOW, answerer=answerer)

        async def scenario():
            service.writer = FakeWriter()
            raw = json.dumps({"v": 1, "type": "message", "msg_id": "m1", "thread_id": "1111", "from_id": "1111",
                              "ts": int(NOW * 1000), "kind": "text", "text": "nợ khách A"}).encode()
            first = [json.loads(line) for line in service.on_line(raw)]
            await asyncio.gather(*service._tasks)
            return first, service.writer.lines

        first, sent = asyncio.run(scenario())
        self.assertEqual([line["type"] for line in first], ["send", "typing"])       # câu chào, rồi đang gõ
        self.assertEqual([(line["type"], line["text"], line["quote_msg_id"]) for line in sent], [("send", "Đã tra: nợ khách A", "m1")])
        log = json.loads((cfg.log_dir / "2026-11.jsonl").read_text(encoding="utf-8").splitlines()[-1])
        self.assertEqual((log["outcome"], log["tools"], log["cost_nano_usd"], log["model"]), ("answered", ["no_khach"], 5, "claude-haiku-5-5"))
        self.assertEqual(protocol.MAX_TEXT_OUT, 2000)


if __name__ == "__main__":
    unittest.main()
