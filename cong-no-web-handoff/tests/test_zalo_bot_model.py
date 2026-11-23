"""Vòng gọi model của bot Zalo (ZALO-BOT-01 PR-2b) với model giả và API giả: gọi công cụ, điền số, kiểm số, trả lại một lần,
dòng nguồn và cảnh báo lệch Sheet do bot thêm, trần chi phí, giới hạn lượt gọi; và bộ não gửi câu trả lời qua kênh."""

import asyncio
import datetime as dt
import io
import json
import sys
import tempfile
import unittest
import urllib.error
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
    """API giả. Đường dò vai trò trả như web thật: login quản lý thì 404 (không có đường), login khác thì 403 (ADMIN_ONLY)."""

    def __init__(self, admins=("chu@example.com",)):
        self.admins = set(admins)
        self.paths = []

    def open(self, request, timeout=None):
        parts = urllib.parse.urlsplit(request.full_url)
        self.paths.append(parts.path)
        if parts.path == "/api/v7/admin/zalo-bot-role":
            code = 404 if request.get_header("Tailscale-user-login") in self.admins else 403
            raise urllib.error.HTTPError(request.full_url, code, "", {}, None)
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

    def answer(self, client, question="khách A còn nợ bao nhiêu", user=ADMIN, opener=None):
        answerer = model.Answerer(client, model="claude-opus-5-5", effort="medium", budget=self.budget,
                                  api=webapi.WebApi(opener=opener or Opener()), link_base="https://web.example", clock=lambda: NOW)
        return answerer.answer(user, question)

    def test_tools_then_filled_answer_with_source_lines_added_by_the_bot(self):
        client = FakeClient(tool_use(("tim_khach", {"ten": "khach a"})), tool_use(("no_khach", {"khach_id": 7})),
                            final("Khách {t2.ten} còn nợ {t2.no_vnd}, quá hạn {t2.qua_han_vnd}."))
        out = self.answer(client)
        self.assertEqual(out.outcome, "answered")
        self.assertEqual(out.text, "Khách Khách A còn nợ 350.000.000 đ, quá hạn 120.500.000 đ.\n\n"
                                   "Lưu ý: lần đối soát với Sheet đã cũ (10:05 22/11).\n"
                                   "Sổ: Khách A (mã 7) · số hiện tại\n"
                                   "Nguồn: Sổ khách · dữ liệu lúc 15:00 22/11\nMở: https://web.example/so-khach-v7-live.html?customer=7")
        first = client.requests[0]
        self.assertTrue(first["messages"][0]["content"].startswith("Hôm nay: 2026-11-22 (Chủ nhật), giờ Việt Nam.\n\n"))
        self.assertEqual((first["max_tokens"], first["cache_control"]), (16000, {"type": "ephemeral"}))   # F10
        self.assertTrue(model.MIN_CALL_SECONDS <= first["timeout"] <= model.DEADLINE)                    # F9
        self.assertTrue({"temperature", "top_p", "top_k", "thinking", "tool_choice"}.isdisjoint(first))
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
        capped = self.answer(idle)
        self.assertEqual(capped.outcome, "over_budget")
        self.assertEqual(capped.text, "Hôm nay đã hết hạn mức hỏi, mai hỏi lại giúp mình.")   # Q4, 24/11/2026
        self.assertEqual(idle.requests, [])
        tomorrow = NOW + 24 * 3600                                               # sang ngày giờ VN thì hỏi lại được
        self.assertTrue(self.budget.allows(tomorrow))

    def test_price_table_covers_every_allowed_model(self):
        self.assertEqual(set(budget.PRICES), set(config.MODELS))

    def test_history_goes_in_as_text_and_old_numbers_still_need_a_fresh_lookup(self):
        client = FakeClient(final("Khách A vẫn nợ 350.000.000 đ."), final("Khách A vẫn nợ 350.000.000 đ."))
        answerer = model.Answerer(client, model="claude-opus-5-5", effort="medium", budget=self.budget,
                                  api=webapi.WebApi(opener=Opener()), clock=lambda: NOW)
        out = answerer.answer(ADMIN, "còn khách đó?", [("khách A nợ bao nhiêu", "Khách A còn nợ 350.000.000 đ.")])
        first = client.requests[0]["messages"][0]["content"]
        self.assertTrue(first.startswith(model.today_line(NOW) + "\n\n" + model.HISTORY_NOTE))
        self.assertIn("Hỏi: khách A nợ bao nhiêu\nĐáp: Khách A còn nợ 350.000.000 đ.", first)
        self.assertTrue(first.endswith("Câu hỏi mới: còn khách đó?"))
        self.assertEqual(out.outcome, "not_sure")      # số chỉ có trong lượt cũ: bộ kiểm số chặn vì lượt này chưa tra lại

    def test_today_line_names_the_vietnam_date_and_weekday(self):
        """F3: 23:30 UTC ngày 22/11 đã là thứ Hai 23/11 giờ Việt Nam."""
        late = dt.datetime(2026, 11, 22, 23, 30, tzinfo=dt.UTC).timestamp()
        self.assertEqual(model.today_line(late), "Hôm nay: 2026-11-23 (thứ Hai), giờ Việt Nam.")
        self.assertEqual(model.with_history("tháng trước thu bao nhiêu?", [], late),
                         "Hôm nay: 2026-11-23 (thứ Hai), giờ Việt Nam.\n\ntháng trước thu bao nhiêu?")
        self.assertNotIn("Hôm nay:", model.SYSTEM.split("\n")[0])          # ngày ở lượt người dùng, không làm vỡ nhớ đệm lời dặn

    def test_footer_prints_the_period_of_each_cited_figure(self):
        results = [{"trang": "Công nợ theo tháng", "khach_id": 7, "ten": "Khách A", "thang": "2026-10", "outstanding_vnd": "5"},
                   {"trang": "Bảng thu", "thang": "2026-11", "tong_thang": {"total_vnd": "9"}},
                   {"trang": "Sổ khách: Lịch sử", "khach_id": 9, "ten": "KHACH B", "tu_ngay": "2026-11-15", "den_ngay": "2026-11-22"}]
        tail = model.footer(results, "{t1.outstanding_vnd} {t2.tong_thang.total_vnd} {t3.ten}")
        self.assertIn("Sổ: Khách A (mã 7) · tháng 10/2026", tail)
        self.assertIn("Kỳ: tháng 11/2026 (Bảng thu)", tail)
        self.assertIn("Sổ: KHACH B (mã 9) · 15/11/2026–22/11/2026", tail)

    def test_ambiguous_name_blocks_customer_tools_until_the_asker_chooses(self):
        """F2: tim_khach ra hai sổ, câu hỏi không nêu sổ nào: no_khach bị từ chối, model phải hỏi lại."""
        client = FakeClient(tool_use(("tim_khach", {"ten": "khach"})), tool_use(("no_khach", {"khach_id": 7})),
                            final("Có hai sổ: {t1.khach.0.ten} (mã {t1.khach.0.khach_id}) và {t1.khach.1.ten} (mã {t1.khach.1.khach_id}). Bạn hỏi sổ nào?"))
        out = self.answer(client, "khách nợ bao nhiêu")
        refused = json.loads(client.requests[2]["messages"][-1]["content"][0]["content"])
        self.assertEqual(refused["loi"], "chua_chon_so")
        self.assertEqual(out.outcome, "answered")
        self.assertEqual(out.text.split("\n\n")[0], "Có hai sổ: Khách A (mã 7) và KHACH B (mã 9). Bạn hỏi sổ nào?")
        for question in ("khách B nợ bao nhiêu", "sổ mã 9 nợ bao nhiêu"):
            with self.subTest(question=question):
                tools.reset_cache()
                chosen = FakeClient(tool_use(("tim_khach", {"ten": "khach"})), tool_use(("no_khach", {"khach_id": 9})),
                                    final("{t2.ten} nợ {t2.no_vnd}."))
                self.assertTrue(self.answer(chosen, question).text.startswith("KHACH B nợ 45.000 đ."))
        gate = model.BookGate("a tank sr nợ bao nhiêu")
        gate.seen("tim_khach", {"khach": [{"khach_id": 1, "ten": "A TANK"}, {"khach_id": 2, "ten": "A TANK SR"}]})
        self.assertEqual((gate.blocks("no_khach", {"khach_id": 1}), gate.blocks("no_khach", {"khach_id": 2})), (True, False))

    def test_amounts_of_two_books_without_names_are_sent_back(self):
        client = FakeClient(tool_use(("no_khach", {"khach_id": 7}), ("no_khach", {"khach_id": 9})),
                            final("Khách A nợ {t2.no_vnd}, khách B nợ {t1.no_vnd}."),
                            final("{t1.ten} nợ {t1.no_vnd}. {t2.ten} nợ {t2.no_vnd}."))
        out = self.answer(client, "khách A và B nợ bao nhiêu")
        self.assertIn("nhieu_so_thieu_ten", client.requests[2]["messages"][-1]["content"])
        self.assertTrue(out.text.startswith("Khách A nợ 350.000.000 đ. KHACH B nợ 45.000 đ."))
        self.assertIn("Sổ: Khách A (mã 7) · số hiện tại\nSổ: KHACH B (mã 9) · số hiện tại", out.text)

    def test_money_words_without_a_cited_figure_get_no_source_line(self):
        """F4: "đã trả hết" sau khi tra nợ: trả lại model một lần; vẫn không trích thì gửi mà không có dòng nguồn."""
        client = FakeClient(tool_use(("no_khach", {"khach_id": 7})), final("Khách A đã trả hết nợ."), final("Khách A đã trả hết nợ."))
        out = self.answer(client)
        self.assertIn("chua_trich_so", client.requests[2]["messages"][-1]["content"])
        self.assertEqual((out.outcome, out.text), ("answered", "Khách A đã trả hết nợ."))
        plain = self.answer(FakeClient(tool_use(("no_khach", {"khach_id": 7})), final("Sổ Khách A khớp Sheet.")))
        self.assertEqual(plain.text, "Sổ Khách A khớp Sheet.")                 # không trích số: không có dòng "Nguồn"

    def test_links_written_by_the_model_are_dropped(self):
        out = self.answer(FakeClient(tool_use(("no_khach", {"khach_id": 7})), final("Xem tại https://evil.example nhé: {t1.no_vnd}.")))
        self.assertNotIn("evil.example", out.text)
        self.assertIn("Mở: https://web.example/so-khach-v7-live.html?customer=7", out.text)

    def test_role_comes_from_the_web(self):
        """F11: quản lý bị hạ quyền trên web thì bot không đưa công cụ admin; file ghi user thì luôn là user."""
        demoted = Opener(admins=())
        client = FakeClient(final("Chưa tra được."))
        self.answer(client, user=ADMIN, opener=demoted)
        offered = {tool["name"] for tool in client.requests[0]["tools"]}
        self.assertNotIn("doi_soat", offered)
        self.assertIn("/api/v7/admin/zalo-bot-role", demoted.paths)
        tools.reset_cache()
        admin = FakeClient(final("Chưa tra được."))
        self.answer(admin, user=ADMIN)
        self.assertIn("doi_soat", {tool["name"] for tool in admin.requests[0]["tools"]})
        tools.reset_cache()
        capped, opener = FakeClient(final("Chưa tra được.")), Opener()
        self.answer(capped, user=config.User("1111", "chu@example.com", "user"), opener=opener)
        self.assertNotIn("doi_soat", {tool["name"] for tool in capped.requests[0]["tools"]})
        self.assertEqual(opener.paths, [])                                  # file đã hạ quyền: không cần hỏi web

    def test_budget_is_safe_with_two_askers_at_once(self):
        """F9: hai luồng cộng chi phí cùng lúc: tổng đúng, file không hỏng."""
        import threading

        def spend():
            for _ in range(50):
                self.budget.add("claude-haiku-5-5", {"output_tokens": 10}, NOW)

        threads = [threading.Thread(target=spend) for _ in range(4)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(self.budget.spent, 200 * 10 * 500)
        self.assertEqual(json.loads((self.dir / "budget.json").read_text(encoding="utf-8"))["spent_nano_usd"], 200 * 10 * 500)


class SelfCheckOpener:
    """API giả cho lượt tự kiểm: tuyến có trong DATA thì trả, tuyến khác 404."""

    def open(self, request, timeout=None):
        parts = urllib.parse.urlsplit(request.full_url)
        key = parts.path + (f"?{parts.query}" if parts.query else "")
        if key not in DATA:
            raise urllib.error.HTTPError(request.full_url, 404, "not found", {}, None)
        return io.BytesIO(json.dumps(DATA[key]).encode("utf-8"))


class ConfigTests(unittest.TestCase):
    def test_model_settings_are_validated(self):
        cfg = config.from_env({"WEBDEBIT_ZALO_BOT_MODEL": "claude-haiku-5-5", "WEBDEBIT_ZALO_BOT_CAP_USD": "2",
                               "WEBDEBIT_ZALO_BOT_LINK_BASE": "https://web.example:8443"})
        self.assertEqual((cfg.model, cfg.effort, cfg.cap_usd, cfg.link_base), ("claude-haiku-5-5", "medium", 2, "https://web.example:8443"))
        self.assertIsNone(config.from_env({}).model)
        self.assertEqual(config.from_env({}).cap_usd, 3)                       # Q4: mặc định và tối đa 3 USD/ngày lúc thử
        self.assertEqual(config.from_env({"WEBDEBIT_ZALO_BOT_CAP_USD": "3"}).cap_usd, config.CAP_MAX)
        for env in ({"WEBDEBIT_ZALO_BOT_MODEL": "gpt-x"}, {"WEBDEBIT_ZALO_BOT_EFFORT": "turbo"}, {"WEBDEBIT_ZALO_BOT_CAP_USD": "0"},
                    {"WEBDEBIT_ZALO_BOT_CAP_USD": "4"}, {"WEBDEBIT_ZALO_BOT_CAP_USD": "100"},
                    {"WEBDEBIT_ZALO_BOT_LINK_BASE": "http://web.example"}, {"WEBDEBIT_ZALO_BOT_EFFORT": "xhigh"},
                    {"WEBDEBIT_ZALO_BOT_EFFORT": "max"}):
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
        answerer = NS(answer=lambda user, text, history: model.Answer(f"Đã tra: {text}", "answered", tools=["no_khach"], cost_nano_usd=5))
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

    def test_queue_is_bounded_and_a_question_that_waited_too_long_is_not_answered(self):
        """F9: tối đa 3 câu chờ mỗi người, câu thứ tư được nhờ đợi; câu chờ quá 10 phút thì nhờ hỏi lại, không gọi model."""
        base = Path(tempfile.mkdtemp())
        cfg = config.Config(enabled=True, users_file=base / "u.json", socket=base / "s.sock", state_dir=base / "state",
                            release_link=base / "cur", model="claude-haiku-5-5")
        clock = [NOW]
        asked = []

        def answer(user, text, history):
            asked.append(text)
            clock[0] += 400                                     # mỗi câu tra mất gần 7 phút
            return model.Answer(f"Đáp {text}", "answered")

        service = brain.Service(cfg, {"1111": ADMIN}, core.Memory(greeted={"1111"}), clock=lambda: clock[0], answerer=NS(answer=answer))

        def line(msg_id):
            return json.dumps({"v": 1, "type": "message", "msg_id": msg_id, "thread_id": "1111", "from_id": "1111",
                               "ts": int(NOW * 1000), "kind": "text", "text": f"câu {msg_id}"}).encode()

        async def scenario():
            service.writer = FakeWriter()
            replies = [[json.loads(item) for item in service.on_line(line(f"m{i}"))] for i in range(1, 5)]
            await asyncio.gather(*service._tasks)
            return replies, service.writer.lines

        replies, sent = asyncio.run(scenario())
        self.assertEqual([[item["type"] for item in reply] for reply in replies], [["typing"]] * 3 + [["send"]])
        self.assertEqual(replies[3][0]["text"], brain.BUSY_REPLY)
        self.assertEqual(asked, ["câu m1", "câu m2"])                    # m3 bắt đầu sau 800 giây chờ: quá 10 phút
        self.assertEqual([item["text"] for item in sent if item["type"] == "send"], ["Đáp câu m1", "Đáp câu m2", core.LATE])
        self.assertEqual(service._pending, {"1111": 0})
        counts = service.counters.snapshot(clock[0])
        self.assertEqual((counts["busy"], counts["late_queued"]), (1, 1))

    def test_context_keeps_answered_turns_for_two_hours_and_moi_clears_it(self):
        base = Path(tempfile.mkdtemp())
        cfg = config.Config(enabled=True, users_file=base / "u.json", socket=base / "s.sock", state_dir=base / "state",
                            release_link=base / "cur", model="claude-haiku-5-5")
        calls = []

        def answer(user, text, history):
            calls.append((text, list(history)))
            return model.Answer(f"Trả lời: {text}", "answered", body=f"Đáp {text}")

        clock = [NOW]
        service = brain.Service(cfg, {"1111": ADMIN}, core.Memory(), clock=lambda: clock[0], answerer=NS(answer=answer))

        async def ask(msg_id, text):
            service.writer = FakeWriter()
            raw = json.dumps({"v": 1, "type": "message", "msg_id": msg_id, "thread_id": "1111", "from_id": "1111",
                              "ts": int(clock[0] * 1000), "kind": "text", "text": text}).encode()
            service.on_line(raw)
            await asyncio.gather(*service._tasks)
            return [line["text"] for line in service.writer.lines if line["type"] == "send"]

        async def scenario():
            await ask("m1", "nợ khách A")
            await ask("m2", "còn tháng trước?")
            reset = await ask("m3", "Mới!")
            await ask("m4", "câu khác")
            clock[0] += 2 * 3600 + 1
            await ask("m5", "sau hai giờ")
            return reset

        reset = asyncio.run(scenario())
        self.assertEqual([history for _text, history in calls],
                         [[], [("nợ khách A", "Đáp nợ khách A")], [], []])
        self.assertEqual(reset, [brain.RESET_REPLY])
        self.assertEqual([text for text, _history in calls], ["nợ khách A", "còn tháng trước?", "câu khác", "sau hai giờ"])

    def test_daily_tool_check_lists_broken_tools_in_status(self):
        tools.reset_cache()
        base = Path(tempfile.mkdtemp())
        cfg = config.Config(enabled=True, users_file=base / "u.json", socket=base / "s.sock", state_dir=base / "state", release_link=base / "cur")
        service = brain.Service(cfg, {"1111": ADMIN}, core.Memory(), clock=lambda: NOW)
        service.api = webapi.WebApi(opener=SelfCheckOpener())
        asyncio.run(service.check_tools())
        check = json.loads(cfg.status_file.read_text(encoding="utf-8"))["tool_check"]
        names = {item.split(":")[0] for item in check["failed"]}
        self.assertIn("tong_quan:api_not_found", check["failed"])
        self.assertTrue(names.isdisjoint({"no_khach", "doi_soat", "tim_khach"}))          # tuyến có thật thì qua
        self.assertTrue({"so_khach_thang", "thu_chi", "may_chay"} <= names)
        self.assertEqual(check["at"], "2026-11-22T15:00:00+07:00")


if __name__ == "__main__":
    unittest.main()
