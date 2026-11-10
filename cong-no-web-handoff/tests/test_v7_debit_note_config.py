"""DEBIT-NOTE-03: cấu hình mẫu debit note đọc từ bản mặc định + file riêng ngoài repo."""

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "web"))
import v7_debit_note_config as config  # noqa: E402
import v7_ledger_api as api  # noqa: E402


class DebitNoteConfigTest(unittest.TestCase):
    def private(self, data) -> str:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / "debit-note.json"
        path.write_text(json.dumps(data, ensure_ascii=False) if not isinstance(data, str) else data, encoding="utf-8")
        return str(path)

    def test_default_is_v3_with_public_company_and_no_bank(self):
        body = config.load("")
        self.assertEqual(body["template"], "v3")
        self.assertEqual(body["company"]["email"], "hth.logs@gmail.com")
        self.assertIsNone(body["company"]["tax_id"])
        self.assertEqual({key: body["payment"][key] for key in ("beneficiary", "bank", "account", "swift")},
                         {"beneficiary": None, "bank": None, "account": None, "swift": None})
        self.assertEqual(body["fees"]["LUMP_SUM"], {"en": "Unit price", "cn": "单价", "width": 78})
        self.assertEqual(body["fees"]["HC_FEE"]["width"], 62)

    def test_private_file_overrides_per_key_and_switches_template(self):
        path = self.private({"template": "v4", "payment": {"bank": "Bank A", "account": "123"},
                             "fees": {"OTHER": {"en": "Others", "cn": "其他", "width": 80}}})
        body = config.load(path)
        self.assertEqual(body["template"], "v4")
        self.assertEqual(body["payment"]["bank"], "Bank A")
        self.assertEqual(body["payment"]["account_label_en"], "USD Account")   # khóa không ghi đè vẫn giữ
        self.assertEqual(body["fees"]["OTHER"]["en"], "Others")
        self.assertEqual(body["fees"]["STORAGE"]["en"], "Storage")

    def test_bad_private_file_is_an_error_not_a_silent_default(self):
        for data, code in (("{oops", "DEBIT_NOTE_CONFIG_UNAVAILABLE"), ({"template": "v5"}, "DEBIT_NOTE_CONFIG_INVALID"),
                           ({"bank": "x"}, "DEBIT_NOTE_CONFIG_INVALID"), ({"fees": {"OTHER": {"en": "x", "cn": "y", "width": 999}}}, "DEBIT_NOTE_CONFIG_INVALID"),
                           ({"company": {"name": "A\nB"}}, "DEBIT_NOTE_CONFIG_INVALID")):
            with self.subTest(data=data), self.assertRaises(config.ConfigError) as caught:
                config.load(self.private(data))
            self.assertEqual(caught.exception.code, code)
        with self.assertRaises(config.ConfigError) as caught:
            config.load(str(Path(tempfile.gettempdir()) / "khong-co-file-nay.json"))
        self.assertEqual(caught.exception.status, 503)

    def test_route_returns_config_and_rejects_query(self):
        runner = Mock()
        args = {"port": 8780, "host": "127.0.0.1", "actor": "nguoi-thu"}
        status, body = api.handle("GET", "/api/v7/debit-note/config", {"Host": "127.0.0.1:8780"}, b"", runner, **args)
        self.assertEqual(status, 200)
        self.assertIn(body["config"]["template"], ("v3", "v4"))
        runner.run.assert_not_called()
        with self.assertRaises(api.ApiError) as caught:
            api.handle("GET", "/api/v7/debit-note/config?x=1", {"Host": "127.0.0.1:8780"}, b"", runner, **args)
        self.assertEqual(caught.exception.status, 400)


if __name__ == "__main__":
    unittest.main()
