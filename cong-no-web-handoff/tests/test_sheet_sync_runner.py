import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).parents[1] / "tools"))
import sheet_sync_runner as runner


class SheetSyncRunnerTests(unittest.TestCase):
    def test_run_once_writes_atomic_read_only_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            credential_path = Path(directory) / "credential.json"
            output_path = Path(directory) / "out" / "snapshot.json"
            credential_path.write_text(json.dumps({
                "type": "service_account", "client_email": "reader@example.com", "private_key": "unused",
            }), encoding="utf-8")
            original = runner.read_source
            runner.read_source = lambda sheet, token, **kwargs: {
                "row_count": 2, "sha256": "a" * 64, "rows": [], "source": {"spreadsheet_id": sheet},
            }
            try:
                snapshot = runner.run_once(str(credential_path), "sheet-id", str(output_path), lambda _: "token")
            finally:
                runner.read_source = original
            self.assertEqual(snapshot["runner"]["mode"], "read-only")
            self.assertEqual(json.loads(output_path.read_text(encoding="utf-8"))["row_count"], 2)
            self.assertFalse((output_path.with_name("snapshot.json.tmp")).exists())

    def test_source_option_picks_the_central_tab_and_rejects_unknown(self):
        with tempfile.TemporaryDirectory() as directory:
            credential_path = Path(directory) / "credential.json"
            credential_path.write_text(json.dumps({
                "type": "service_account", "client_email": "reader@example.com", "private_key": "unused",
            }), encoding="utf-8")
            calls = []
            originals = (runner.read_export, runner.read_source)
            runner.read_export = lambda sheet, token, **kwargs: calls.append("export") or {
                "row_count": 0, "sha256": "a" * 64, "rows": [], "source": {}}
            runner.read_source = lambda sheet, token, **kwargs: calls.append("cont_nguon") or {
                "row_count": 0, "sha256": "b" * 64, "rows": [], "source": {}}
            try:
                default = runner.run_once(str(credential_path), "sheet-id", str(Path(directory) / "a.json"), lambda _: "t")
                central = runner.run_once(str(credential_path), "sheet-id", str(Path(directory) / "b.json"), lambda _: "t",
                                          source="export")
                with self.assertRaisesRegex(ValueError, "unknown sheet source"):
                    runner.run_once(str(credential_path), "sheet-id", str(Path(directory) / "c.json"), lambda _: "t",
                                    source="booking")
            finally:
                runner.read_export, runner.read_source = originals
            self.assertEqual(calls, ["cont_nguon", "export"])
            self.assertEqual((default["runner"]["source"], central["runner"]["source"]), ("cont_nguon", "export"))

    def test_timeout_retries_twice_with_backoff_then_writes(self):
        # Audit DevOps 31/10 (#14): TimeoutError khi đọc Google API được thử lại 2 lần, chờ 5 rồi 15 giây.
        with tempfile.TemporaryDirectory() as directory:
            credential_path = Path(directory) / "credential.json"
            output_path = Path(directory) / "snapshot.json"
            credential_path.write_text(json.dumps({
                "type": "service_account", "client_email": "reader@example.com", "private_key": "unused",
            }), encoding="utf-8")
            failures = [TimeoutError("The read operation timed out"),
                        runner.urllib.error.URLError(TimeoutError("timed out"))]
            tokens, waits = [], []

            def read_source(sheet, token, **kwargs):
                if failures:
                    raise failures.pop(0)
                return {"row_count": 1, "sha256": "c" * 64, "rows": [], "source": {}}
            original = runner.read_source
            runner.read_source = read_source
            try:
                with patch.object(sys, "stderr", io.StringIO()) as errors:
                    snapshot = runner.run_once(str(credential_path), "sheet-id", str(output_path),
                                               lambda _: tokens.append(1) or "t", sleep=waits.append)
            finally:
                runner.read_source = original
            self.assertEqual(snapshot["row_count"], 1)
            self.assertEqual(waits, [5.0, 15.0])
            self.assertEqual(len(tokens), 3)  # mỗi lượt lấy token mới
            self.assertEqual(len(errors.getvalue().splitlines()), 2)
            self.assertTrue(output_path.exists())

    def test_timeout_gives_up_after_three_attempts_and_other_errors_are_not_retried(self):
        waits, calls = [], []

        def always_timeout():
            calls.append(1)
            raise TimeoutError("timed out")
        with patch.object(sys, "stderr", io.StringIO()), self.assertRaises(TimeoutError):
            runner.with_timeout_retry(always_timeout, sleep=waits.append)
        self.assertEqual((len(calls), waits), (3, [5.0, 15.0]))

        for error in (ValueError("bad sheet"), runner.urllib.error.URLError("name resolution failed")):
            with self.subTest(error=error):
                waits.clear()
                with self.assertRaises(type(error)):
                    runner.with_timeout_retry(Mock(side_effect=error), sleep=waits.append)
                self.assertEqual(waits, [])

    def test_assertion_has_expected_claims(self):
        credentials = {"client_email": "reader@example.com", "private_key": "unused"}
        assertion = runner.make_assertion(credentials, now=100, signer=lambda data, key: b"sig")
        header, claims, signature = assertion.split(".")
        self.assertEqual(json.loads(runner.base64.urlsafe_b64decode(header + "=="))["alg"], "RS256")
        self.assertEqual(json.loads(runner.base64.urlsafe_b64decode(claims + "=="))["iat"], 100)
        self.assertEqual(signature, "c2ln")
        def claims_of(token):
            return json.loads(runner.base64.urlsafe_b64decode(token.split(".")[1] + "=="))
        self.assertEqual(claims_of(assertion)["scope"], runner.SCOPE)
        other = runner.make_assertion(credentials, now=100, signer=lambda data, key: b"sig", scope="drive.readonly")
        self.assertEqual(claims_of(other)["scope"], "drive.readonly")


if __name__ == "__main__":
    unittest.main()
