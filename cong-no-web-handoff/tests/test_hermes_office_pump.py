"""Script gọi Hermes: chỉ gọi model khi có việc mới; hết việc thì code tự dọn; lỗi thì vòng sau làm lại."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts" / "hermes-office"))
import pump


def summary(*open_rows, jobs=None, **extra):
    return {"day": "2000-01-15", "runs": [{"at": "09:10", "matched": 9, "different": 1, "fixed": 0}], "open": [{"customer": c, "reason": r, "note": "x", "runs_in_a_row": 1} for c, r in open_rows],
            "unlinked": {}, "too_many_different": False, "last_run_failed": False, "jobs": jobs or {"sheet": "ok"}, **extra}


class FakeApi:
    def __init__(self, data):
        self.data, self.reports = data, []

    def summary(self):
        return self.data

    def report(self, body):
        self.reports.append(body)


class PumpTests(unittest.TestCase):
    def setUp(self) -> None:
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.data = Path(folder.name)
        self.calls = 0

    def hermes(self, tasks=None, ok=True):
        def run():
            self.calls += 1
            if tasks is not None:
                path = self.data / "tasks" / "tasks.json"
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps(tasks), encoding="utf-8")
            return ok
        return run

    def test_new_work_calls_model_and_sends_tasks(self):
        api = FakeApi(summary(("kh-7", "NO_EXACT_FIX")))
        tasks = {"kh-7-lech": {"title": "T", "body": "B", "level": "warn"}}
        self.assertIn("goi model", pump.run_once(api, self.data, self.hermes(tasks)))
        self.assertEqual(self.calls, 1)
        self.assertEqual(api.reports[0], {"state": "working"})
        self.assertEqual(api.reports[-1], {"state": "idle", "tasks": tasks, "model_called": True})
        self.assertEqual(json.loads((self.data / "feed" / "summary.json").read_text(encoding="utf-8"))["open"][0]["customer"], "kh-7")

    def test_same_work_does_not_call_model_again(self):
        api = FakeApi(summary(("kh-7", "NO_EXACT_FIX")))
        pump.run_once(api, self.data, self.hermes({}))
        reports = len(api.reports)
        self.assertEqual(pump.run_once(api, self.data, self.hermes({})), "khong doi")
        self.assertEqual((self.calls, len(api.reports)), (1, reports))

    def test_only_counters_changing_is_not_new_work(self):
        first, later = summary(("kh-7", "NO_EXACT_FIX")), summary(("kh-7", "NO_EXACT_FIX"))
        later["runs"].append({"at": "10:10", "matched": 9, "different": 1, "fixed": 0})
        later["open"][0]["runs_in_a_row"] = 2
        self.assertEqual(pump.fingerprint(first), pump.fingerprint(later))

    def test_a_new_customer_or_reason_or_broken_job_is_new_work(self):
        base = pump.fingerprint(summary(("kh-7", "NO_EXACT_FIX")))
        self.assertNotEqual(base, pump.fingerprint(summary(("kh-7", "NO_EXACT_FIX"), ("kh-8", "HELD"))))
        self.assertNotEqual(base, pump.fingerprint(summary(("kh-7", "AMBIGUOUS_FIX"))))
        self.assertNotEqual(base, pump.fingerprint(summary(("kh-7", "NO_EXACT_FIX"), jobs={"sheet": "failed"})))
        self.assertEqual(base, pump.fingerprint(summary(("kh-7", "NO_EXACT_FIX"), jobs={"sheet": "running"})))

    def test_nothing_open_clears_cards_without_model(self):
        api = FakeApi(summary(("kh-7", "NO_EXACT_FIX")))
        pump.run_once(api, self.data, self.hermes({"kh-7-lech": {"title": "T", "body": "B"}}))
        api.data = summary()
        self.assertIn("khong goi model", pump.run_once(api, self.data, self.hermes({})))
        self.assertEqual(self.calls, 1)
        self.assertEqual(api.reports[-1], {"state": "idle", "tasks": {}})

    def test_failure_keeps_old_cards_and_tries_again(self):
        api = FakeApi(summary(("kh-7", "NO_EXACT_FIX")))
        self.assertEqual(pump.run_once(api, self.data, self.hermes(ok=False)), "hermes loi")
        self.assertEqual(api.reports[-1], {"state": "idle"})
        self.assertIn("goi model", pump.run_once(api, self.data, self.hermes({})))
        self.assertEqual(self.calls, 2)

    def test_timeout_and_broken_task_file_do_not_send_cards(self):
        api = FakeApi(summary(("kh-7", "NO_EXACT_FIX")))

        def slow():
            raise subprocess.TimeoutExpired("docker", 1)
        self.assertEqual(pump.run_once(api, self.data, slow), "hermes loi")
        path = self.data / "tasks" / "tasks.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("hỏng", encoding="utf-8")
        self.assertEqual(pump.run_once(api, self.data, self.hermes()), "the hong")
        self.assertTrue(all("tasks" not in body for body in api.reports))

    def test_missing_config_is_a_clean_error(self):
        with unittest.mock.patch.dict("os.environ", {}, clear=True), unittest.mock.patch("sys.stderr"):
            self.assertEqual(pump.main(), 2)


if __name__ == "__main__":
    unittest.main()
