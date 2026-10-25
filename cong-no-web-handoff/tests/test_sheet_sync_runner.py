import json
import sys
import tempfile
import unittest
from pathlib import Path

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
            original = runner.read_export
            runner.read_export = lambda sheet, token, **kwargs: {
                "row_count": 2, "sha256": "a" * 64, "rows": [], "source": {"spreadsheet_id": sheet},
            }
            try:
                snapshot = runner.run_once(str(credential_path), "sheet-id", str(output_path), lambda _: "token")
            finally:
                runner.read_export = original
            self.assertEqual(snapshot["runner"]["mode"], "read-only")
            self.assertEqual(json.loads(output_path.read_text(encoding="utf-8"))["row_count"], 2)
            self.assertFalse((output_path.with_name("snapshot.json.tmp")).exists())

    def test_assertion_has_expected_claims(self):
        credentials = {"client_email": "reader@example.com", "private_key": "unused"}
        assertion = runner.make_assertion(credentials, now=100, signer=lambda data, key: b"sig")
        header, claims, signature = assertion.split(".")
        self.assertEqual(json.loads(runner.base64.urlsafe_b64decode(header + "=="))["alg"], "RS256")
        self.assertEqual(json.loads(runner.base64.urlsafe_b64decode(claims + "=="))["iat"], 100)
        self.assertEqual(signature, "c2ln")


if __name__ == "__main__":
    unittest.main()
