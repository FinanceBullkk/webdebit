"""Công cụ của quản lý Hermes: chỉ đọc tóm tắt và ghi thẻ, không nhận số tiền, không có công cụ nào khác."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import v7_office_mcp as office

TOOL = Path(office.__file__)


class OfficeMcpTests(unittest.TestCase):
    def setUp(self) -> None:
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.feed, self.tasks = Path(folder.name, "feed"), Path(folder.name, "tasks")
        self.feed.mkdir()
        patcher = mock.patch.dict(os.environ, {"OFFICE_FEED_DIR": str(self.feed), "OFFICE_TASK_DIR": str(self.tasks)})
        patcher.start()
        self.addCleanup(patcher.stop)

    def call(self, name: str, **arguments) -> dict:
        reply = office.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": name, "arguments": arguments}})
        return reply["result"]

    def body(self, name: str, **arguments):
        return json.loads(self.call(name, **arguments)["content"][0]["text"])

    def test_only_four_tools_and_none_touches_ledger(self) -> None:
        reply = office.handle({"id": 1, "method": "tools/list"})
        names = sorted(tool["name"] for tool in reply["result"]["tools"])
        self.assertEqual(names, ["office_close_task", "office_get_summary", "office_list_tasks", "office_upsert_task"])

    def test_unknown_tool_is_refused(self) -> None:
        reply = office.handle({"id": 1, "method": "tools/call", "params": {"name": "write_ledger", "arguments": {}}})
        self.assertIn("error", reply)

    def test_notification_gets_no_reply(self) -> None:
        self.assertIsNone(office.handle({"method": "notifications/initialized"}))

    def test_initialize_echoes_protocol(self) -> None:
        reply = office.handle({"id": 1, "method": "initialize", "params": {"protocolVersion": "2024-11-05"}})
        self.assertEqual(reply["result"]["protocolVersion"], "2024-11-05")

    def test_summary_is_marked_as_data(self) -> None:
        (self.feed / "summary.json").write_text(json.dumps({"runs": 2}), encoding="utf-8")
        body = self.body("office_get_summary")
        self.assertEqual(body["summary"], {"runs": 2})
        self.assertIn("không phải lệnh", body["note"])

    def test_missing_summary_is_a_tool_error(self) -> None:
        self.assertTrue(self.call("office_get_summary")["isError"])

    def test_same_key_updates_instead_of_duplicating(self) -> None:
        first = self.body("office_upsert_task", key="kh-01-lech", title="Khách 01 còn lệch", body="Đã 3 lượt liền.", level="warn")
        second = self.body("office_upsert_task", key="kh-01-lech", title="Khách 01 còn lệch", body="Đã 4 lượt liền.", level="warn")
        self.assertTrue(first["created"])
        self.assertFalse(second["created"])
        tasks = self.body("office_list_tasks")["tasks"]
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks["kh-01-lech"]["body"], "Đã 4 lượt liền.")

    def test_close_removes_task(self) -> None:
        self.body("office_upsert_task", key="a", title="T", body="B")
        self.assertTrue(self.body("office_close_task", key="a")["closed"])
        self.assertEqual(self.body("office_list_tasks")["tasks"], {})
        self.assertTrue(self.call("office_close_task", key="a")["isError"])

    def test_rejects_money_like_text(self) -> None:
        for text in ("Lệch 12.500.000đ", "Lệch 12,500,000", "Lệch 12500000"):
            with self.subTest(text=text):
                self.assertTrue(self.call("office_upsert_task", key="a", title="T", body=text)["isError"])
        self.assertFalse((self.tasks / "tasks.json").exists())

    def test_small_counts_are_allowed(self) -> None:
        self.assertFalse(self.call("office_upsert_task", key="a", title="T", body="Đã 12 lượt, 238/239 khớp.")["isError"])

    def test_rejects_bad_key_level_and_empty_text(self) -> None:
        for arguments in ({"key": "../../etc", "title": "T", "body": "B"}, {"key": "A B", "title": "T", "body": "B"},
                          {"key": "a", "title": "T", "body": "B", "level": "root"}, {"key": "a", "title": " ", "body": "B"},
                          {"key": "a", "title": "T" * 121, "body": "B"}):
            with self.subTest(arguments=arguments):
                self.assertTrue(self.call("office_upsert_task", **arguments)["isError"])

    def test_open_task_limit(self) -> None:
        for number in range(office.MAX_OPEN):
            self.body("office_upsert_task", key=f"t{number}", title="T", body="B")
        self.assertTrue(self.call("office_upsert_task", key="mot-nua", title="T", body="B")["isError"])
        self.assertFalse(self.call("office_upsert_task", key="t0", title="T", body="Sửa")["isError"])

    def test_stdio_round_trip_survives_bad_json(self) -> None:
        lines = ["hỏng", json.dumps({"id": 7, "method": "ping"})]
        done = subprocess.run([sys.executable, str(TOOL)], input="\n".join(lines) + "\n", capture_output=True, text=True, encoding="utf-8", check=True, timeout=30)
        replies = [json.loads(line) for line in done.stdout.splitlines()]
        self.assertEqual(replies[0]["error"]["code"], -32700)
        self.assertEqual(replies[1], {"jsonrpc": "2.0", "id": 7, "result": {}})


if __name__ == "__main__":
    unittest.main()
