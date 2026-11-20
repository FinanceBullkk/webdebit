"""QUYEN-02: danh sách login sửa trên trang Người dùng, gộp với danh sách cố định; mọi đường chặn và file hỏng."""

import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "web"))

import v7_access  # noqa: E402
from v7_api_validate import ApiError  # noqa: E402

BOSS, STAFF, NEW = "boss@example.test", "staff@example.test", "new@example.test"


class AccessStoreTest(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.path = Path(folder.name) / "access.json"
        self.store = v7_access.AccessStore(self.path, frozenset({BOSS}), frozenset({BOSS}))
        denied = patch.object(v7_access, "DENIED", v7_access.DeniedLog(limit=3))
        denied.start()
        self.addCleanup(denied.stop)
        self.quiet = patch.object(sys, "stderr", io.StringIO())
        self.quiet.start()
        self.addCleanup(self.quiet.stop)

    def apply(self, actor=BOSS, **body):
        body.setdefault("version", self.store.view(actor)["version"])
        return self.store.apply(actor, body)

    def error(self, code, **body):
        with self.assertRaises(ApiError) as caught:
            self.apply(**body)
        self.assertEqual(caught.exception.code, code)
        return caught.exception

    def test_missing_file_means_fixed_lists_only(self):
        self.assertEqual(self.store.lists(), (frozenset({BOSS}), frozenset({BOSS})))
        view = self.store.view(BOSS)
        self.assertEqual((view["configured"], view["version"]), (True, 0))
        self.assertEqual(view["users"], [{"login": BOSS, "name": None, "role": "admin", "fixed": True,
                                          "added_by": None, "added_at": None, "me": True}])

    def test_add_role_name_remove_change_lists_at_once_and_keep_history(self):
        self.assertTrue(self.apply(action="add", login="Staff@EXAMPLE.TEST", name="  Lan   Anh ")["changed"])
        self.assertEqual(self.store.lists(), (frozenset({BOSS, "Staff@example.test"}), frozenset({BOSS})))
        self.apply(action="role", login="Staff@example.test", role="admin")
        self.assertEqual(self.store.lists()[1], frozenset({BOSS, "Staff@example.test"}))
        self.apply(action="name", login="Staff@example.test", name=None)
        self.assertFalse(self.apply(action="name", login="Staff@example.test", name="")["changed"])   # không đổi gì: không ghi lịch sử
        self.apply(action="remove", login="Staff@example.test")
        self.assertEqual(self.store.lists(), (frozenset({BOSS}), frozenset({BOSS})))
        history = self.store.view(BOSS)["history"]
        self.assertEqual([item["action"] for item in history], ["remove", "name", "role", "add"])   # mới trước
        self.assertEqual(history[3]["after"], {"role": "user", "name": "Lan Anh"})
        self.assertEqual((history[2]["before"]["role"], history[2]["after"]["role"]), ("user", "admin"))
        self.assertIsNone(history[0]["after"])
        self.assertEqual(json.loads(self.path.read_text(encoding="utf-8"))["version"], 4)
        if os.name != "nt":
            self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)
        self.assertEqual([name for name in os.listdir(self.path.parent) if name.endswith(".tmp")], [])

    def test_guards(self):
        self.apply(action="add", login=STAFF)
        self.error("EXISTS", action="add", login=STAFF)
        self.error("FIXED_LOGIN", actor=STAFF, action="remove", login=BOSS)
        self.error("SELF", actor=STAFF, action="role", login=STAFF, role="admin")
        self.error("NOT_FOUND", action="remove", login=NEW)
        self.error("STALE", action="add", login=NEW, version=0)
        for bad in ("không có a còng", "a b@c", "a@b,c@d", "", "x@" , None, 5):
            with self.subTest(login=bad):
                self.error("INVALID_LOGIN", action="add", login=bad)
        self.error("INVALID_ROLE", action="add", login=NEW, role="owner")
        self.error("INVALID_NAME", action="add", login=NEW, name="x" * 41)
        self.error("INVALID_REQUEST", action="add", login=NEW, extra=1)
        self.error("INVALID_REQUEST", action="drop", login=NEW)
        self.error("INVALID_REQUEST", action="add", login=NEW, version=True)

    def test_last_admin_cannot_be_removed(self):
        store = v7_access.AccessStore(self.path, frozenset({BOSS}), frozenset())   # quản lý cố định rỗng: chỉ quản lý trên file
        store.apply(BOSS, {"action": "add", "login": STAFF, "role": "admin", "version": 0})
        with self.assertRaises(ApiError) as caught:
            store.apply(BOSS, {"action": "role", "login": STAFF, "role": "user", "version": 1})
        self.assertEqual(caught.exception.code, "LAST_ADMIN")
        self.assertEqual(store.lists()[1], frozenset({STAFF}))   # lần ghi bị chặn không đổi gì trong bộ nhớ
        self.assertEqual(json.loads(self.path.read_text(encoding="utf-8"))["version"], 1)

    def test_unset_admin_list_keeps_quyen01_meaning(self):
        store = v7_access.AccessStore(self.path, frozenset({BOSS}), None)
        self.assertEqual(store.lists(), (frozenset({BOSS}), None))   # mọi login được vào là quản lý
        store.apply(BOSS + "x", {"action": "add", "login": STAFF, "version": 0})
        self.assertEqual(store.lists(), (frozenset({BOSS, STAFF}), None))

    def test_broken_file_fails_closed_and_refuses_writes(self):
        self.apply(action="add", login=STAFF)
        for content in ("{not json", json.dumps({"version": 1, "users": [{"login": STAFF, "role": "owner"}]}),
                        json.dumps({"version": 1, "users": [{"login": STAFF, "role": "user"}, {"login": STAFF, "role": "user"}]})):
            with self.subTest(content=content[:20]):
                self.path.write_text(content, encoding="utf-8")
                os.utime(self.path, ns=(1, len(content) + 10))   # đổi dấu thời gian để chắc chắn đọc lại
                self.assertEqual(self.store.lists(), (frozenset({BOSS}), frozenset({BOSS})))
                view = self.store.view(BOSS)
                self.assertTrue(view["broken"])
                self.assertFalse(view["configured"])
                with self.assertRaises(ApiError) as caught:
                    self.store.apply(BOSS, {"action": "add", "login": NEW, "version": 0})
                self.assertEqual(caught.exception.code, "ACCESS_FILE_BROKEN")

    def test_file_changed_outside_is_reread(self):
        self.apply(action="add", login=STAFF)
        doc = json.loads(self.path.read_text(encoding="utf-8"))
        doc["users"] = []
        doc["version"] = 9
        self.path.write_text(json.dumps(doc), encoding="utf-8")
        self.assertEqual(self.store.lists()[0], frozenset({BOSS}))
        self.assertEqual(self.store.view(BOSS)["version"], 9)

    def test_not_configured_is_read_only(self):
        store = v7_access.AccessStore(None, frozenset({BOSS, STAFF}), frozenset({BOSS}))
        view = store.view(BOSS)
        self.assertFalse(view["configured"])
        self.assertEqual([(row["login"], row["role"]) for row in view["users"]], [(BOSS, "admin"), (STAFF, "user")])
        with self.assertRaises(ApiError) as caught:
            store.apply(BOSS, {"action": "add", "login": NEW, "version": 0})
        self.assertEqual(caught.exception.code, "ACCESS_NOT_CONFIGURED")

    def test_write_failure_keeps_memory_unchanged(self):
        with patch.object(v7_access.AccessStore, "_write", side_effect=OSError("disk")):
            self.error("ACCESS_WRITE_FAILED", action="add", login=STAFF)
        self.assertEqual(self.store.lists()[0], frozenset({BOSS}))

    def test_denied_log_is_bounded_newest_first_and_hides_allowed(self):
        for login in ("a@x", "b@x", "a@x", "c@x", "d@x", "bad login"):
            v7_access.DENIED.record(login)
        rows = v7_access.DENIED.view(frozenset({"d@x"}))
        self.assertEqual([row["login"] for row in rows], ["c@x", "a@x"])   # giới hạn 3: b bị đẩy ra; d đã được vào
        self.assertEqual(rows[1]["count"], 2)
        self.apply(action="add", login="c@x")   # cho vào thì biến khỏi danh sách bị chặn
        self.assertEqual([row["login"] for row in v7_access.DENIED.view(None)], ["d@x", "a@x"])


if __name__ == "__main__":
    unittest.main()
