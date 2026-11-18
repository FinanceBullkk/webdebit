"""Máy canh, bản sao ngoài máy (CANH-BAO-01, bổ sung 18/11/2026): báo khi không PC nào kéo quá ngưỡng; không báo nhầm khi
thiếu quyền đọc journal; không lộ IP hay khóa. Không cần journal hay systemd thật."""

import datetime as dt
import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import v7_offsite_watch as watch  # noqa: E402

VN = ZoneInfo("Asia/Ho_Chi_Minh")
NOW = dt.datetime(2026, 11, 20, 9, 0, tzinfo=VN).timestamp()
PULL_A, PULL_B, ADMIN = "SHA256:" + "a" * 43, "SHA256:" + "b" * 43, "SHA256:" + "c" * 43
WANTED = {PULL_A, PULL_B}


def at(hours_ago):
    return NOW - hours_ago * 3600


class KeysTest(unittest.TestCase):
    def test_labels_commas_spaces_and_junk(self):
        self.assertEqual(watch.keys(f"pc-cu={PULL_A}, desktop={PULL_B}  msi=khong-phai-dau-van rac"), {PULL_A, PULL_B})
        self.assertEqual(watch.keys(""), set())


class CheckTest(unittest.TestCase):
    def check(self, seen, **kwargs):
        return watch.check(NOW, wanted=kwargs.pop("wanted", WANTED), read=lambda hours: seen, can_read=lambda: True, **kwargs)

    def test_not_configured_is_quiet_without_reading(self):
        def boom(hours):
            raise AssertionError("không được đọc journal khi chưa khai khóa")
        with patch.dict("os.environ", {"WEBDEBIT_OFFSITE_PULL_KEYS": ""}):
            self.assertEqual(watch.check(NOW, read=boom, can_read=lambda: False), [])

    def test_one_recent_pull_from_any_pc_is_enough(self):
        self.assertEqual(self.check([(at(70), PULL_A), (at(30), PULL_B)]), [])
        self.assertEqual(self.check([(at(48), PULL_A)]), [])   # đúng 48 giờ chưa quá ngưỡng

    def test_admin_logins_from_the_same_pc_do_not_count(self):
        found = self.check([(at(1), ADMIN), (at(60), PULL_A)])
        self.assertEqual(found, ["Không PC nào kéo bản sao ngoài máy quá 48 giờ (lần cuối 21:00 ngày 17/11): "
                                 "xem lịch Webdebit V7 Backup Pull trên các PC."])

    def test_nothing_in_the_window(self):
        self.assertEqual(self.check([]), ["Không PC nào kéo bản sao ngoài máy quá 48 giờ (không thấy lần nào trong 72 giờ): "
                                          "xem lịch Webdebit V7 Backup Pull trên các PC."])

    def test_threshold_and_window_follow_hours(self):
        seen = []
        watch.check(NOW, wanted=WANTED, hours=24, read=lambda hours: seen.append(hours) or [], can_read=lambda: True)
        self.assertEqual(seen, [48])

    def test_missing_journal_group_says_so_instead_of_a_false_no_pull(self):
        self.assertEqual(watch.check(NOW, wanted=WANTED, read=lambda hours: [], can_read=lambda: False),
                         ["Không đọc được log SSH để kiểm bản sao ngoài máy: unit máy canh thiếu nhóm systemd-journal."])

    def test_message_has_no_ip_or_key(self):
        text = " ".join(self.check([(at(60), PULL_A)]) + self.check([]))
        self.assertNotIn("SHA256", text)
        self.assertNotIn("100.", text)


class AcceptsTest(unittest.TestCase):
    def test_parses_only_key_logins_and_skips_bad_lines(self):
        lines = [
            {"MESSAGE": f"Accepted publickey for aohanh from 100.64.0.9 port 51515 ssh2: ED25519 {PULL_A}",
             "__REALTIME_TIMESTAMP": "1795000000000000"},
            {"MESSAGE": "Connection closed by 100.64.0.9 port 51515", "__REALTIME_TIMESTAMP": "1795000001000000"},
            {"MESSAGE": "Accepted password for x from 100.64.0.9 port 1 ssh2", "__REALTIME_TIMESTAMP": "1795000002000000"},
            {"MESSAGE": f"Accepted publickey for aohanh from 100.64.0.9 port 1 ssh2: ED25519 {PULL_B}"},   # thiếu giờ
        ]
        calls = []

        def run(args, **kwargs):
            calls.append((args, kwargs))
            return SimpleNamespace(stdout="\n".join(json.dumps(line) for line in lines) + "\nkhông phải json\n")
        self.assertEqual(watch.accepts(72, run=run), [(1795000000.0, PULL_A)])
        args, kwargs = calls[0]
        self.assertEqual(args[:3], ["journalctl", "--since", "-72h"])
        self.assertIn("_COMM=sshd-session", args)
        self.assertTrue(kwargs["check"])


class ReadableTest(unittest.TestCase):
    def test_without_grp_or_group_it_is_not_readable(self):
        with patch.dict(sys.modules, {"grp": None}):
            self.assertFalse(watch.readable())


if __name__ == "__main__":
    unittest.main()
