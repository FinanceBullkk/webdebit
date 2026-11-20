"""ZALO-AGENT-01 PR-1: agent đọc live-sync theo revision, gói chat theo phần thêm, kênh đẩy chung, nhịp tim.

Dữ liệu bịa trong thư mục tạm (kho live-sync giả, máy chủ giả chạy đoạn shell thật bằng bash + tar). Không ssh, không kho thật.
"""

import contextlib
import hashlib
import io
import itertools
import json
import os
import shlex
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import zalo_web_bundle as wb  # noqa: E402
from test_zalo_web_bundle import (  # noqa: E402
    BAN,
    BASH,
    GROUP,
    KHACH,
    NOW,
    OTHER,
    OWNER,
    PRIVATE,
    FakeCdn,
    cdn_bytes,
    no_jxl,
    row,
    write_source,
)
from zalo_agent import __main__ as agent_main  # noqa: E402
from zalo_agent import cursor as cursors  # noqa: E402
from zalo_agent import push as pusher  # noqa: E402
from zalo_agent import status as status_file  # noqa: E402
from zalo_agent.processors.bundle import BundleProcessor, clean_row  # noqa: E402
from zalo_agent.source import VN, LiveSync, Rebuild  # noqa: E402

BUNDLE_REMOTE, STATUS_REMOTE = "/srv/v7/zalo-bundle", "/srv/v7/zalo-agent"


class Remote:
    """`hao` giả: mỗi đường dẫn đích là một thư mục tạm. `fast=False` chạy đúng dòng lệnh mà push() gửi qua ssh (đoạn shell
    thật bằng bash + tar thật, ~1 giây mỗi lệnh trên Windows); `fast=True` mô phỏng cùng hai đoạn shell bằng Python để các
    ca về con trỏ và delta chạy nhanh. `test_python_fake_matches_real_shell` giữ hai bản không lệch nhau."""

    def __init__(self, root: Path, fast: bool = True):
        self.dirs = {BUNDLE_REMOTE: root / "bundle", STATUS_REMOTE: root / "agent"}
        for directory in self.dirs.values():
            directory.mkdir()
        self.fast = fast
        self.calls: list[tuple[str, bool]] = []
        self.drop_after_apply = False
        self.tars: list[list[str]] = []   # tên các thành viên của mỗi tar đã gửi, theo thứ tự trong tar

    def __call__(self, host, command, stdin=None):
        assert host == "fake"
        remote = next(path for path in self.dirs if path in command)
        data = stdin.read() if stdin is not None else None   # đọc một lần: tránh lệch vị trí đọc của handle khi chuyển cho bash
        if data is not None:
            with tarfile.open(fileobj=io.BytesIO(data), mode="r:") as tar:
                self.tars.append(tar.getnames())
        out = self.emulate(remote, command, data) if self.fast else self.shell(remote, command, data)
        self.calls.append((remote, stdin is not None))
        if stdin is not None and self.drop_after_apply:
            self.drop_after_apply = False
            raise pusher.PushError("ssh đứt sau khi máy chủ đã áp gói")
        return out

    def shell(self, remote, command, data):
        done = subprocess.run([BASH, "-c", command.replace(remote, self.dirs[remote].as_posix())], input=data,
                              capture_output=True, check=False)
        assert done.returncode == 0, done.stderr
        return done.stdout.decode("utf-8", "replace")

    def emulate(self, remote, command, data):
        _, _, script, _, _, *args = shlex.split(command)
        root = self.dirs[remote]
        if script == pusher.INVENTORY_SCRIPT:
            files = [path for path in root.rglob("*") if path.is_file() and not path.relative_to(root).parts[0].startswith(".incoming-")]
            listing = "".join(f"{path.relative_to(root).as_posix()}\t{path.stat().st_size}\n" for path in files)
            hashes = "".join(f"{hashlib.sha256((root / name).read_bytes()).hexdigest()}  {name}\n" for name in args if (root / name).is_file())
            return listing + "---\n" + hashes
        assert script == pusher.APPLY_SCRIPT
        final, patterns = args[0], args[1:]
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:") as tar:
            members = {member.name: tar.extractfile(member).read() for member in tar.getmembers()}
        for rel in members[".list"].decode().splitlines():
            (root / rel).parent.mkdir(parents=True, exist_ok=True)
            (root / rel).write_bytes(members[rel])
        (root / final).write_bytes(members[final])
        keep = set(members[".keep"].decode().splitlines())
        for pattern in patterns:
            for path in sorted(root.glob(pattern)):
                if path.relative_to(root).as_posix() not in keep:
                    shutil.rmtree(path) if path.is_dir() else path.unlink()
        return ""

    def applies(self, remote=BUNDLE_REMOTE):
        return sum(1 for path, applied in self.calls if path == remote and applied)

    def text(self) -> str:
        return "\n".join(path.read_bytes().decode("utf-8", "replace") for path in self.dirs[BUNDLE_REMOTE].rglob("*") if path.is_file())


def snapshot(directory: Path) -> dict[str, bytes]:
    return {str(path.relative_to(directory)): path.read_bytes() for path in directory.rglob("*") if path.is_file()}


class AgentTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name)
        self.src, self.root = base / "live-sync", base / "agent"
        self.src.mkdir()
        (base / "remote").mkdir()
        write_source(self.src)
        (self.src / "baseline-manifest.json").write_text(json.dumps({"messages_sha256": "a" * 64}), encoding="utf-8")
        wb.Source(self.src).save_selection([GROUP])
        self.remote = Remote(base / "remote")
        self.base = base
        self.now = NOW
        self.live = LiveSync(self.src)
        self.processor = self.make()
        self.out = self.root / "bundle"
        self.next_id = 100

    def make(self, **kwargs):
        args = {"run": self.remote, "fetch": FakeCdn(), "transcode": no_jxl, "max_age_days": None, "clock": lambda: self.now, **kwargs}
        return BundleProcessor(self.live, self.root / "state", self.root / "bundle", "fake:" + BUNDLE_REMOTE, **args)

    # --- bắt chước live_sync: ghi lại cả messages.jsonl, thêm changes-N, revision.json ghi sau cùng ---
    def publish(self, added=(), updated=(), deleted=()):
        lines = (self.src / "messages.jsonl").read_text(encoding="utf-8").splitlines()
        rows = {}
        for index, line in enumerate(lines):
            with contextlib.suppress(ValueError):
                rows[json.loads(line)["message_id"]] = index
        for item in updated:
            lines[rows[item["message_id"]]] = json.dumps(item, ensure_ascii=False)
        for mid in deleted:
            old = json.loads(lines[rows[mid]])
            lines[rows[mid]] = json.dumps({**old, "body": None, "deleted": True}, ensure_ascii=False)
        lines += [json.dumps(item, ensure_ascii=False) for item in added]
        (self.src / "messages.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
        revision = self.live.revision() + 1
        change = {"revision": revision, "added": [item["message_id"] for item in added],
                  "updated": [item["message_id"] for item in updated], "deleted": list(deleted)}
        (self.src / f"changes-{revision}.json").write_text(json.dumps(change), encoding="utf-8")
        (self.src / "revision.json").write_text(json.dumps({"revision": revision, "message_publish_epoch_ms": int(self.now * 1000)}), encoding="utf-8")
        return revision

    def message(self, cid=GROUP, body="tin bịa", sender=KHACH):
        self.next_id += 1
        return row(cid, f"n{self.next_id}", sender, 1_700_000_100_000 + self.next_id, body)

    def remote_delta(self) -> list[dict]:
        found = list(self.remote.dirs[BUNDLE_REMOTE].glob("data-*/messages-delta.jsonl"))
        return [json.loads(line) for path in found for line in path.read_text(encoding="utf-8").splitlines()]

    def remote_report(self) -> dict:
        return json.loads((self.remote.dirs[BUNDLE_REMOTE] / wb.REPORT).read_text(encoding="utf-8"))

    def test_first_step_builds_pushes_and_idle_sends_nothing(self):
        before = snapshot(self.src)
        result = self.processor.step()
        self.assertEqual((result["action"], result["revision"], result["error"], result["reason"]), ("rebuild", 87, None, "first_run"))
        report = self.remote_report()
        self.assertEqual((report["delta_bytes"], report["delta_lines"], report["revision"], report["message_count"]), (0, 0, 87, 8))
        self.assertEqual(self.remote_delta(), [])
        self.assertFalse(list(self.remote.dirs[BUNDLE_REMOTE].glob("data-*/messages-delta.jsonl")))   # chưa có delta thì chưa có file
        saved = cursors.load(self.root / "state", "bundle")
        self.assertEqual((saved["revision"], saved["data_dir"], "pending" in saved), (87, report["data_dir"], False))
        calls = len(self.remote.calls)
        self.assertEqual(self.processor.step()["action"], "idle")   # không đổi gì: không hỏi, không gửi
        self.assertEqual(len(self.remote.calls), calls)
        self.assertFalse(self.processor.wants_work())
        self.assertEqual(snapshot(self.src), before)                 # kho live-sync không đổi byte nào

    def test_add_update_delete_become_delta_and_unselected_groups_stay_out(self):
        self.processor.step()
        before = self.remote_report()
        added, other, private = self.message(body="tin mới của khách"), self.message(OTHER, "Bí mật nhóm vận tải"), self.message(PRIVATE, "Chuyện riêng tư")
        self.publish(added=[added, other, private])
        updated = row(GROUP, "m1", OWNER, 1_700_000_001_000, "Anh ơi đã sửa lại tin này")
        self.publish(updated=[updated])
        self.publish(deleted=["m3"])
        self.assertTrue(self.processor.wants_work())
        result = self.processor.step()
        self.assertEqual((result["action"], result["revision"], result["reason"]), ("delta", 90, "delta"))
        lines = self.remote_delta()
        self.assertEqual([line["message_id"] for line in lines], ["m1", "m3", added["message_id"]])   # theo thứ tự trong messages.jsonl
        self.assertEqual(lines[0], clean_row(updated))
        self.assertEqual((lines[1]["message_id"], lines[1]["conversation_id"], lines[1]["timestamp"], lines[1]["deleted"], lines[1]["body"]),
                         ("m3", GROUP, "1700000003000", True, None))
        self.assertEqual(lines[2]["body"], "tin mới của khách")
        report = self.remote_report()
        size = next(self.remote.dirs[BUNDLE_REMOTE].glob("data-*/messages-delta.jsonl")).stat().st_size
        self.assertEqual((report["delta_lines"], report["delta_bytes"], report["revision"]), (3, size, 90))
        self.assertEqual((report["data_dir"], report["bundle_sha256"]), (before["data_dir"], before["bundle_sha256"]))
        self.assertNotIn("Bí mật", self.remote.text())
        self.assertNotIn("riêng tư", self.remote.text())
        # Người gửi mới có trong users.json của thư mục hiện tại; ảnh mới thì trong media.json (xem test_delta_of_new_image).
        self.assertEqual(self.processor.step()["action"], "idle")

    def test_delta_row_has_exactly_the_shape_build_would_produce(self):
        self.processor.step()
        text = row(GROUP, "m1", OWNER, 1_700_000_001_000, [{"title": "Thẻ", "description": "https://x.example/y", "href": "https://x.example/y"}], 21)
        self.publish(updated=[text])
        self.publish(deleted=["m3"])
        self.processor.step()
        full = wb.build(wb.Source(self.src), Path(self.tmp.name) / "full", fetch=FakeCdn(), transcode=no_jxl, now=NOW + 5, max_age_days=None)
        built = {item["message_id"]: item for item in (json.loads(line) for line in
                 (Path(self.tmp.name) / "full" / full["data_dir"] / "messages.jsonl").read_text(encoding="utf-8").splitlines())}
        delta = self.remote_delta()
        self.assertEqual([line["message_id"] for line in delta], ["m1", "m3"])
        for line in delta:   # cả tin sửa lẫn tin xóa giống hệt dòng của bản dựng đầy đủ
            self.assertEqual(line, {key: value for key, value in built[line["message_id"]].items() if key != "media"})
        self.assertEqual(delta[0]["body"], [{"title": "Thẻ"}])   # URL không lọt vào gói
        self.assertTrue(built["m3"]["deleted"])

    def test_delta_of_new_image_adds_media_and_is_sent(self):
        self.processor.step()
        url = "https://f5.photo.zdn.vn/new.jpg"
        image = row(GROUP, "img1", KHACH, 1_700_000_100_000, {"title": "", "description": "", "oriUrl": url, "normalUrl": url,
                                                              "params": json.dumps({"width": 800, "height": 600})}, 2)
        self.publish(added=[image])
        self.processor.step()
        sha = hashlib.sha256(cdn_bytes(url)).hexdigest()
        self.assertEqual(self.remote_delta()[0]["media"], [sha])
        data = next(self.remote.dirs[BUNDLE_REMOTE].glob("data-*"))
        self.assertIn(sha, json.loads((data / "media.json").read_text(encoding="utf-8")))
        self.assertTrue((self.remote.dirs[BUNDLE_REMOTE] / "media" / (sha + ".jpg")).is_file())

    def test_push_order_delta_media_users_images_first_report_last(self):
        self.processor.step()
        url = "https://f6.photo.zdn.vn/order.jpg"
        image = row(GROUP, "img2", KHACH, 1_700_000_100_000, {"title": "", "description": "", "oriUrl": url, "normalUrl": url}, 2)
        self.publish(added=[image, self.message(body="chữ", sender=BAN)])   # người gửi mới: users.json đổi
        before = len(self.remote.tars)
        self.processor.step()
        names = self.remote.tars[before]
        sha = hashlib.sha256(cdn_bytes(url)).hexdigest()
        data = next(self.remote.dirs[BUNDLE_REMOTE].glob("data-*")).name
        listed = ["messages-delta.jsonl", "media.json", "users.json"]
        for name in [f"{data}/{item}" for item in listed] + [f"media/{sha}.jpg"]:
            self.assertIn(name, names)
            self.assertLess(names.index(name), names.index(wb.REPORT))
        self.assertEqual(names[-1], wb.REPORT)                          # file chốt là thành viên cuối của tar
        self.assertNotIn(wb.REPORT, self.processor.plan(data).files and [item.rel for item in self.processor.plan(data).files])
        self.assertEqual(self.processor.plan(data).final.rel, wb.REPORT)

    @unittest.skipUnless(BASH, "cần bash và tar để chạy đoạn shell phía máy chủ")
    def test_python_fake_matches_real_shell(self):
        """Cùng một chuỗi bước chạy qua bản mô phỏng Python và đoạn shell thật phải để lại cùng một cây thư mục trên máy chủ."""
        root = Path(self.tmp.name) / "real"
        (root / "remote").mkdir(parents=True)
        real = Remote(root / "remote", fast=False)
        twin = BundleProcessor(self.live, root / "state", root / "bundle", "fake:" + BUNDLE_REMOTE, run=real, fetch=FakeCdn(),
                               transcode=no_jxl, max_age_days=None, clock=lambda: self.now)
        steps = [lambda: None,
                 lambda: self.publish(added=[self.message(body="một")], deleted=["m3"]),
                 lambda: (wb.Source(self.src).save_selection([GROUP, OTHER]), setattr(self, "now", self.now + 60)),
                 lambda: (wb.Source(self.src).save_selection([GROUP]), setattr(self, "now", self.now + 60))]   # bỏ chọn: máy chủ phải dọn
        for index, change in enumerate(steps):
            change()
            self.processor.step()
            twin.step()
            self.assertEqual(snapshot(self.remote.dirs[BUNDLE_REMOTE]), snapshot(real.dirs[BUNDLE_REMOTE]), f"bước {index}")

    def test_revision_without_selected_messages_moves_cursor_and_sends_nothing(self):
        self.processor.step()
        calls = len(self.remote.calls)
        self.publish(added=[self.message(OTHER)])
        result = self.processor.step()
        self.assertEqual((result["action"], result["revision"]), ("idle", 88))
        self.assertEqual(len(self.remote.calls), calls)
        self.assertEqual(cursors.load(self.root / "state", "bundle")["revision"], 88)

    def test_dropped_connection_resends_without_duplicate_lines(self):
        self.processor.step()
        first = self.message(body="một")
        self.publish(added=[first])
        self.remote.drop_after_apply = True   # máy chủ đã áp gói nhưng ssh đứt: con trỏ không được tiến
        result = self.processor.step()
        self.assertEqual((result["action"], result["error"], result["revision"]), ("retry", "push_failed", 87))
        saved = cursors.load(self.root / "state", "bundle")
        self.assertEqual((saved["revision"], saved["pending"]["revision"]), (87, 88))
        pushed = next(self.remote.dirs[BUNDLE_REMOTE].glob("data-*/messages-delta.jsonl")).read_bytes()
        # Tin trong phần chờ đẩy lại bị sửa tiếp: lượt sau vẫn đẩy đúng phần chờ, không viết lại byte nào đã gửi.
        self.publish(updated=[row(GROUP, first["message_id"], KHACH, int(first["timestamp"]), "hai")])
        applies = self.remote.applies()
        result = self.processor.step()
        self.assertEqual((result["action"], result["error"], result["revision"]), ("delta", None, 88))
        self.assertEqual(self.remote.applies(), applies)   # phần chờ trùng byte với máy chủ: không gửi lại tar
        result = self.processor.step()
        self.assertEqual((result["action"], result["revision"]), ("delta", 89))
        data = next(self.remote.dirs[BUNDLE_REMOTE].glob("data-*/messages-delta.jsonl")).read_bytes()
        self.assertTrue(data.startswith(pushed))
        self.assertEqual([(line["message_id"], line["body"]) for line in self.remote_delta()],
                         [(first["message_id"], "một"), (first["message_id"], "hai")])   # bản mới nhất thắng ở hao
        self.assertEqual(self.remote_report()["delta_lines"], 2)

    def test_leftover_tail_from_crash_before_pending_is_dropped(self):
        self.processor.step()
        self.publish(added=[self.message(body="một")])
        self.processor.step()
        saved = cursors.load(self.root / "state", "bundle")
        path = self.out / saved["data_dir"] / "messages-delta.jsonl"
        path.write_bytes(path.read_bytes() + b'{"message_id": "rac"}\n')   # chết giữa lúc ghi delta, chưa lưu pending
        self.publish(added=[self.message(body="hai")])
        self.processor.step()
        self.assertEqual([line["body"] for line in self.remote_delta()], ["một", "hai"])

    def test_rebuild_from_scratch_when_cursor_cannot_be_trusted(self):
        cases = {
            "missing_changes": lambda: (self.publish(added=[self.message()]), self.publish(added=[self.message()]),
                                        (self.src / "changes-89.json").unlink()),
            "revision_back": lambda: (self.src / "revision.json").write_text(json.dumps({"revision": 12}), encoding="utf-8"),
            "baseline_changed": lambda: (self.src / "baseline-manifest.json").write_text(json.dumps({"messages_sha256": "b" * 64}), encoding="utf-8"),
            "selection_changed": lambda: wb.Source(self.src).save_selection([GROUP, OTHER]),
            "nightly": lambda: setattr(self, "now", (datetime.fromtimestamp(NOW, VN) + timedelta(days=1)).replace(hour=4).timestamp()),
            "data_dir_missing": lambda: shutil.rmtree(next(self.out.glob("data-*"))),
            "report_mismatch": lambda: (self.out / wb.REPORT).write_text(json.dumps({"data_dir": "data-khac"}), encoding="utf-8"),
            "delta_short": lambda: (next(self.out.glob("data-*")) / "messages-delta.jsonl").write_bytes(b""),
        }
        for reason, change in cases.items():
            with self.subTest(reason=reason):
                self.tearDown_state()
                self.processor.step()
                first = self.remote_report()["data_dir"]
                self.publish(added=[self.message(body="tin trước khi dựng lại")])
                self.processor.step()
                self.assertEqual(self.remote_report()["delta_lines"], 1)
                self.now += 60
                change()
                result = self.processor.step()
                self.assertEqual((result["action"], result["reason"]), ("rebuild", reason))
                report = self.remote_report()
                self.assertNotEqual(report["data_dir"], first)
                self.assertEqual((report["delta_bytes"], report["delta_lines"]), (0, 0))
                self.assertEqual(report["revision"], result["revision"])
                self.assertFalse((self.remote.dirs[BUNDLE_REMOTE] / report["data_dir"] / "messages-delta.jsonl").exists())
                if reason == "selection_changed":
                    self.assertIn(OTHER, json.loads((self.remote.dirs[BUNDLE_REMOTE] / report["data_dir"] / "conversations.json").read_text(encoding="utf-8"))[1]["conversation_id"])

    def tearDown_state(self):
        """Đưa kho giả, thư mục agent và máy chủ giả về trạng thái ban đầu giữa hai ca con."""
        for directory in (self.root, self.remote.dirs[BUNDLE_REMOTE]):
            shutil.rmtree(directory, ignore_errors=True)
        self.remote.dirs[BUNDLE_REMOTE].mkdir()
        shutil.rmtree(self.src)
        self.src.mkdir()
        write_source(self.src)
        wb.Source(self.src).save_selection([GROUP])
        (self.src / "baseline-manifest.json").write_text(json.dumps({"messages_sha256": "a" * 64}), encoding="utf-8")
        self.now = NOW

    def test_dry_run_builds_locally_and_pushes_nothing(self):
        dry = self.make(dry_run=True)
        self.assertEqual(dry.step()["action"], "rebuild")
        self.assertEqual(self.remote.calls, [])
        self.assertTrue((self.out / wb.REPORT).is_file())
        self.assertEqual(cursors.load(self.root / "state", "bundle")["revision"], 87)

    def test_failed_first_push_keeps_pending_and_retry_does_not_rebuild(self):
        def broken(host, command, stdin=None):
            raise pusher.PushError("mạng đứt: chữ tự do không được lọt vào status")
        result = self.make(run=broken).step()
        self.assertEqual((result["action"], result["error"], result["revision"]), ("retry", "push_failed", None))
        saved = cursors.load(self.root / "state", "bundle")
        self.assertEqual(("revision" in saved, saved["pending"]["revision"]), (False, 87))
        built = sorted(path.name for path in self.out.glob("data-*"))
        result = self.processor.step()   # ssh về lại: đẩy đúng gói đã dựng, không dựng thêm thư mục dữ liệu
        self.assertEqual((result["action"], result["revision"], result["error"]), ("rebuild", 87, None))
        self.assertEqual(sorted(path.name for path in self.out.glob("data-*")), built)
        self.assertEqual(self.remote_report()["data_dir"], built[0])


@unittest.skipUnless(BASH, "cần bash và tar để chạy đoạn shell phía máy chủ")
class PushTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name)
        (base / "remote").mkdir()
        self.remote = Remote(base / "remote", fast=False)
        self.target = "fake:" + BUNDLE_REMOTE
        self.dir = self.remote.dirs[BUNDLE_REMOTE]

    def plan(self, files, final=b"1", prune=("data-*", "media/*")):
        return pusher.Plan(self.target, tuple(pusher.Item(rel, data, immutable) for rel, data, immutable in files),
                           pusher.Item("export-report.json", final), prune)

    def test_script_has_umask_first_no_chmod_and_final_file_moved_last(self):
        script = pusher.APPLY_SCRIPT
        lines = [line.strip() for line in script.splitlines() if line.strip()]
        self.assertEqual(lines[:2], ["set -eu", "umask 027"])
        self.assertNotIn("chmod", script)
        self.assertNotIn("chmod", pusher.INVENTORY_SCRIPT)
        moves = [line for line in lines if line.startswith("mv ")]
        self.assertEqual(moves[-1], 'mv -f -- "$tmp/$final" "$final"')
        self.assertLess(script.index('mv -f -- "$tmp/$f" "$f"'), script.index('mv -f -- "$tmp/$final"'))
        self.assertIn("mktemp -d .incoming-XXXXXX", script)
        self.assertIn("trap 'rm -rf -- \"$tmp\"' EXIT", script)

    @unittest.skipIf(os.name == "nt", "quyền POSIX chỉ kiểm được trên Linux/macOS")
    def test_files_land_group_readable_not_world_readable(self):
        pusher.push(self.plan([("data-1/messages.jsonl", b"x", True), ("media/a.jpg", b"y", True)]), run=self.remote)
        modes = {path.name: path.stat().st_mode & 0o777 for path in self.dir.rglob("*")}
        self.assertEqual((modes["messages.jsonl"], modes["a.jpg"], modes["export-report.json"]), (0o640, 0o640, 0o640))
        self.assertEqual((modes["data-1"], modes["media"]), (0o750, 0o750))

    def test_nothing_changed_sends_no_tar_and_changes_send_only_difference(self):
        files = [("data-1/messages.jsonl", b"abc", True), ("data-1/messages-delta.jsonl", b"1\n", False), ("media/a.jpg", b"y", True)]
        sent = pusher.push(self.plan(files), run=self.remote)
        self.assertEqual(sorted(sent["sent"]), ["data-1/messages-delta.jsonl", "data-1/messages.jsonl", "export-report.json", "media/a.jpg"])
        applies = self.remote.applies()
        again = pusher.push(self.plan(files), run=self.remote)
        self.assertEqual((again["skipped"], again["bytes"], self.remote.applies()), (True, 0, applies))
        files[1] = ("data-1/messages-delta.jsonl", b"1\n2\n", False)
        sent = pusher.push(self.plan(files, final=b"2"), run=self.remote)
        self.assertEqual(sorted(sent["sent"]), ["data-1/messages-delta.jsonl", "export-report.json"])
        self.assertEqual((self.dir / "data-1" / "messages-delta.jsonl").read_bytes(), b"1\n2\n")
        self.assertEqual((self.dir / "export-report.json").read_bytes(), b"2")
        self.assertEqual(list(self.dir.glob(".incoming-*")), [])

    def test_stale_directories_and_files_are_pruned_even_when_nothing_new_to_send(self):
        pusher.push(self.plan([("data-1/a", b"1", True), ("data-2/a", b"2", True), ("media/x.jpg", b"i", True), ("media/y.jpg", b"j", True)]), run=self.remote)
        sent = pusher.push(self.plan([("data-2/a", b"2", True), ("media/x.jpg", b"i", True)]), run=self.remote)
        self.assertFalse(sent["skipped"])
        self.assertEqual(sorted(path.relative_to(self.dir).as_posix() for path in self.dir.rglob("*") if path.is_file()),
                         ["data-2/a", "export-report.json", "media/x.jpg"])

    def test_dotfiles_on_server_are_not_stale_because_shell_globs_skip_them(self):
        files = [("data-1/a", b"1", True), ("media/x.jpg", b"i", True)]
        pusher.push(self.plan(files), run=self.remote)
        (self.dir / "media" / ".partial").write_bytes(b"x")   # fnmatch khớp, glob của shell thì không: không được coi là thừa
        applies = self.remote.applies()
        self.assertTrue(pusher.push(self.plan(files), run=self.remote)["skipped"])
        self.assertEqual(self.remote.applies(), applies)

    def test_final_only_plan_always_sends_and_keeps_other_files(self):
        (self.remote.dirs[STATUS_REMOTE] / "other").write_text("giữ", encoding="utf-8")
        target = "fake:" + STATUS_REMOTE
        for body in (b"1", b"2"):
            pusher.push(pusher.Plan(target, (), pusher.Item("status.json", body)), run=self.remote)
        self.assertEqual((self.remote.dirs[STATUS_REMOTE] / "status.json").read_bytes(), b"2")
        self.assertTrue((self.remote.dirs[STATUS_REMOTE] / "other").is_file())
        self.assertEqual(self.remote.applies(STATUS_REMOTE), 2)
        self.assertEqual(len([call for call in self.remote.calls if call[1] is False]), 0)   # không hỏi máy chủ

    def test_bad_plans_are_refused_before_any_ssh(self):
        item = pusher.Item("a", b"1")
        bad = [pusher.Plan("hao", (), item), pusher.Plan("hao:/srv/../etc", (), item), pusher.Plan("-oProxyCommand=x:/srv", (), item),
               pusher.Plan(self.target, (), pusher.Item("sub/status.json", b"1")), pusher.Plan(self.target, (), pusher.Item("../x", b"1")),
               pusher.Plan(self.target, (pusher.Item("a", b"1"), pusher.Item("a", b"2")), item),
               pusher.Plan(self.target, (pusher.Item("a b", b"1"),), item), pusher.Plan(self.target, (), item, ("a b",)),
               pusher.Plan(self.target, (), item, ("$(id)",)), pusher.Plan(self.target, (), item, ("media/..",))]
        for plan in bad:
            with self.subTest(target=plan.target), self.assertRaises(pusher.PushError):
                pusher.push(plan, run=self.remote)
        self.assertEqual(self.remote.calls, [])


class SshRunTest(unittest.TestCase):
    def run_with(self, stdin=None, effect=None):
        with patch.object(pusher.subprocess, "run", side_effect=effect or (lambda *a, **k: subprocess.CompletedProcess(a, 0, b"ra", b""))) as run:
            out = pusher.ssh_run("hao", "echo", stdin)
        return out, run.call_args

    def test_errors_become_push_error_so_the_agent_loop_survives(self):
        for effect in (subprocess.TimeoutExpired("ssh", 120), FileNotFoundError("ssh.exe"), PermissionError("ssh.exe")):
            with self.subTest(effect=type(effect).__name__), self.assertRaises(pusher.PushError):
                self.run_with(effect=effect)
        with self.assertRaises(pusher.PushError):
            self.run_with(effect=lambda *a, **k: subprocess.CompletedProcess(a, 255, b"", "lỗi".encode()))

    def test_keepalive_options_short_timeout_for_questions_and_size_based_for_uploads(self):
        out, call = self.run_with()
        command = call.args[0]
        self.assertEqual(out, "ra")
        for option in ("ServerAliveInterval=15", "ServerAliveCountMax=4", "BatchMode=yes", "ConnectTimeout=20"):
            self.assertIn(option, command)
        self.assertEqual((call.kwargs["timeout"], call.kwargs["stdin"]), (120, subprocess.DEVNULL))   # lượt hỏi: không stdin
        with tempfile.TemporaryFile() as spool:
            spool.write(b"x" * 5_000_000)
            spool.flush()
            _, call = self.run_with(spool)
            self.assertEqual((call.kwargs["timeout"], call.kwargs["stdin"] is spool), (170, True))   # 120 + 50 giây cho 5 MB
            spool.write(b"x" * 400_000_000)
            spool.flush()
            self.assertEqual(self.run_with(spool)[1].kwargs["timeout"], 1800)                        # trần 30 phút


class SourceStatusTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.src = Path(self.tmp.name) / "live-sync"
        self.src.mkdir()
        write_source(self.src)
        self.live = LiveSync(self.src)

    def test_rows_for_filters_by_id_and_conversation_and_survives_bad_lines(self):
        wanted = {"m1", "o1", "p1", "khong-co"}
        self.assertEqual([item["message_id"] for item in self.live.rows_for(wanted, {GROUP})], ["m1"])
        self.assertEqual([item["message_id"] for item in self.live.rows_for(wanted, {GROUP, OTHER, PRIVATE})], ["m1", "o1", "p1"])
        self.assertEqual(self.live.rows_for(set(), {GROUP}), [])
        self.assertEqual(self.live.rows_for(wanted, set()), [])

    def test_rows_for_long_prefix_nested_keys_and_ids_past_the_head(self):
        def line(top, prefix="", nested=None):
            body = {"quote": {"message_id": nested}} if nested else {}
            return json.dumps({"source_candidate_id": prefix, **body, "message_id": top, "conversation_id": GROUP}) + "\n"
        with (self.src / "messages.jsonl").open("w", encoding="utf-8") as stream:
            stream.write(line("w-long", prefix="s" * 250))                    # tiền tố dài, id vẫn trong 400 byte đầu
            stream.write(line("w-far", prefix="s" * 900))                     # id nằm sau 400 byte: rơi về json.loads
            stream.write(line("other", nested="w-nested"))                    # khóa lồng của tin trích dẫn khớp trước: kiểm lại cấp trên
            stream.write(line("w-nested", prefix="s" * 10))                   # tin thật có cùng id đó vẫn được lấy
            stream.write("không phải json\n")
        found = [item["message_id"] for item in self.live.rows_for({"w-long", "w-far", "w-nested"}, {GROUP})]
        self.assertEqual(found, ["w-long", "w-far", "w-nested"])

    def test_changed_ids_gathers_all_kinds_and_demands_rebuild_on_gap(self):
        for number, change in ((88, {"added": ["a"]}), (89, {"updated": ["b"], "deleted": ["c"]}), (91, {"added": ["z"]})):
            (self.src / f"changes-{number}.json").write_text(json.dumps({"revision": number, **change}), encoding="utf-8")
        self.assertEqual(self.live.changed_ids(87, 89), {"a", "b", "c"})
        self.assertEqual(self.live.changed_ids(89, 89), set())
        with self.assertRaises(Rebuild) as gap:
            self.live.changed_ids(87, 91)   # thiếu changes-90
        self.assertEqual(gap.exception.reason, "missing_changes")

    def test_identity_and_revision_time_from_live_sync_files(self):
        (self.src / "revision.json").write_text(json.dumps({"revision": 5, "message_publish_epoch_ms": 1_795_141_959_219}), encoding="utf-8")
        self.assertEqual(self.live.revision_at(), "2026-11-20T09:32:39+07:00")
        self.assertEqual(self.live.identity(), "unknown")
        for value, expected in (("attached", "attached"), ("waiting_for_zalo", "waiting_for_zalo"), ("reprobing", "reprobing"), ("lạ", "unknown")):
            (self.src / "poller-identity.json").write_text(json.dumps({"status": value}), encoding="utf-8")
            self.assertEqual(self.live.identity(), expected)

    def test_status_matches_the_contract_and_never_carries_free_text(self):
        (self.src / "poller-identity.json").write_text(json.dumps({"status": "attached"}), encoding="utf-8")
        results = {"bundle": {"action": "idle", "revision": 80, "error": None}}
        first = status_file.compose(None, NOW, "abc1234", 1, self.live, results, None, None, ("attached", "2026-11-01T09:00:00+07:00"))
        self.assertEqual(set(first), {"schema", "at", "agent_version", "selected_groups", "live_sync", "processors", "push"})
        self.assertEqual(first["schema"], 1)
        self.assertEqual(first["at"], "2026-11-01T09:26:40+07:00")
        self.assertEqual(first["live_sync"], {"revision": 87, "revision_at": None, "identity": "attached",
                                              "identity_since": "2026-11-01T09:00:00+07:00"})
        self.assertEqual(set(first["processors"]["bundle"]), {"revision", "lag_revisions", "last_ok_at", "error"})
        self.assertEqual((first["processors"]["bundle"]["revision"], first["processors"]["bundle"]["lag_revisions"]), (80, 7))
        self.assertEqual(first["push"], {"last_ok_at": None, "error": None})
        failed = {"bundle": {"action": "retry", "revision": 80, "error": "Lỗi: mạng đứt tới 100.1.2.3"}}
        second = status_file.compose(first, NOW + 60, "abc1234", 1, self.live, failed, "2026-11-01T09:26:40+07:00", None, ("attached", "x"))
        self.assertEqual(second["processors"]["bundle"]["error"], "unexpected")                       # chữ tự do bị thay bằng mã
        self.assertEqual(second["processors"]["bundle"]["last_ok_at"], first["processors"]["bundle"]["last_ok_at"])   # lỗi thì giữ mốc cũ
        self.assertNotIn("100.1.2.3", json.dumps(second))
        self.assertEqual(status_file.compose(second, NOW, "v", 0, self.live, {"bundle": {"revision": 80, "error": "push_failed"}}, None, None,
                                                ("unknown", "x"))["push"]["error"], "push_failed")

    def test_identity_since_changes_only_when_identity_changes_and_survives_restart(self):
        state = Path(self.tmp.name) / "state"
        self.assertEqual(status_file.track_identity(state, "waiting_for_zalo", NOW), "2026-11-01T09:26:40+07:00")
        self.assertEqual(status_file.track_identity(state, "waiting_for_zalo", NOW + 600), "2026-11-01T09:26:40+07:00")   # giữ mốc cũ
        self.assertEqual(status_file.track_identity(state, "attached", NOW + 900), "2026-11-01T09:41:40+07:00")
        self.assertEqual(status_file.track_identity(state, "attached", NOW + 9000), "2026-11-01T09:41:40+07:00")
        self.assertEqual(status_file.track_identity(state, "waiting_for_zalo", NOW + 9600), "2026-11-01T12:06:40+07:00")   # đổi lại: mốc mới

    def test_cursor_rules(self):
        base = {"revision": 100, "baseline_sha256": "x", "selection_sha256": cursors.selection_sha256([GROUP]), "built_at": cursors.now_iso(NOW)}
        self.assertEqual(cursors.rebuild_reason(None, 1, "x", [GROUP], NOW), "first_run")
        self.assertIsNone(cursors.rebuild_reason(base, 100, "x", [GROUP], NOW))
        self.assertIsNone(cursors.rebuild_reason(base, 105, "x", [GROUP], NOW))
        self.assertEqual(cursors.rebuild_reason(base, 99, "x", [GROUP], NOW), "revision_back")
        self.assertEqual(cursors.rebuild_reason(base, 100, "y", [GROUP], NOW), "baseline_changed")
        self.assertEqual(cursors.rebuild_reason(base, 100, "x", [GROUP, OTHER], NOW), "selection_changed")
        self.assertEqual(cursors.rebuild_reason(base, 100 + cursors.MAX_GAP + 1, "x", [GROUP], NOW), "gap_too_large")
        early = datetime.fromtimestamp(NOW, VN).replace(hour=1, minute=0).timestamp()   # cùng ngày, trước 03:00: chưa tới giờ dựng đêm
        self.assertIsNone(cursors.rebuild_reason({**base, "built_at": cursors.now_iso(early - 86400)}, 100, "x", [GROUP], early))
        self.assertEqual(cursors.rebuild_reason({**base, "built_at": cursors.now_iso(early - 86400)}, 100, "x", [GROUP], early + 3 * 3600), "nightly")


class AgentCycleTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name)
        self.src, self.root = base / "live-sync", base / "agent"
        self.src.mkdir()
        (base / "remote").mkdir()
        write_source(self.src)
        wb.Source(self.src).save_selection([GROUP])
        self.remote = Remote(base / "remote")
        (self.src / "poller-identity.json").write_text(json.dumps({"status": "attached"}), encoding="utf-8")

    def agent(self, **kwargs):
        agent = agent_main.Agent(LiveSync(self.src), self.root, "fake:" + BUNDLE_REMOTE, "fake:" + STATUS_REMOTE, run=self.remote,
                                clock=lambda: NOW, fetch=FakeCdn(), transcode=no_jxl, max_age_days=None, **kwargs)
        self.addCleanup(agent.release)
        return agent

    def test_cycle_pushes_bundle_and_heartbeat_and_dry_run_pushes_nothing(self):
        status = self.agent().cycle(force_status=True)
        remote_status = json.loads((self.remote.dirs[STATUS_REMOTE] / "status.json").read_text(encoding="utf-8"))
        self.assertEqual(remote_status["processors"]["bundle"]["revision"], 87)
        self.assertEqual((remote_status["schema"], remote_status["selected_groups"], remote_status["live_sync"]["identity"]), (1, 1, "attached"))
        self.assertEqual(remote_status["at"], status["at"])
        self.assertEqual(remote_status["live_sync"]["identity_since"], status["at"])   # lần đầu thấy "attached"
        self.assertEqual(json.loads((self.root / "state" / "identity.json").read_text(encoding="utf-8"))["identity"], "attached")
        self.assertTrue((self.remote.dirs[BUNDLE_REMOTE] / wb.REPORT).is_file())
        calls = len(self.remote.calls)
        quiet = self.agent(dry_run=True)
        quiet.cycle(force_status=True)
        self.assertEqual(len(self.remote.calls), calls)

    def test_one_agent_at_a_time_and_stale_lock_file_never_blocks(self):
        agent, other = self.agent(), self.agent()
        self.assertIsNotNone(agent.cycle(force_status=True))
        self.assertIsNone(other.cycle(force_status=True))   # agent kia đang giữ khóa: bỏ qua, không lỗi
        agent.release()
        self.assertIsNotNone(other.cycle(force_status=True))
        other.release()
        # File khóa sót của tiến trình đã chết (cũ nhiều giờ) không được chặn: khóa là của hệ điều hành, không phải của file.
        lock = self.root / "state" / "agent.lock"
        lock.write_text("tiến trình đã chết", encoding="utf-8")
        os.utime(lock, (NOW - 86400, NOW - 86400))
        revived = self.agent()
        self.assertIsNotNone(revived.cycle(force_status=True))
        revived.release()

    def test_lock_is_released_when_the_holding_process_is_killed(self):
        code = ("import sys, time; sys.path.insert(0, sys.argv[1]);"
                "from zalo_agent.__main__ import Agent; from zalo_agent.source import LiveSync; from pathlib import Path;"
                "agent = Agent(LiveSync(Path(sys.argv[2])), Path(sys.argv[3]), 'fake:/a', 'fake:/b');"
                "print(agent.lock(), flush=True); time.sleep(120)")
        holder = subprocess.Popen([sys.executable, "-I", "-c", code, str(ROOT / "tools"), str(self.src), str(self.root)],
                                  stdout=subprocess.PIPE)
        self.addCleanup(holder.stdout.close)
        self.addCleanup(holder.wait)
        self.addCleanup(holder.kill)
        self.assertEqual(holder.stdout.readline().strip(), b"True")
        mine = self.agent()
        self.assertFalse(mine.lock())                       # tiến trình khác còn sống: không giành được
        holder.kill()
        holder.wait()
        for _ in range(40):                                  # hệ điều hành nhả khóa ngay khi đóng handle của tiến trình đã chết
            if mine.lock():
                break
            time.sleep(0.1)
        self.assertIsNotNone(mine.lock_handle)               # bị giết giữa lượt: file khóa sót không chặn
        mine.release()

    def test_backoff_after_errors_does_not_hammer_the_server(self):
        self.assertEqual([agent_main.backoff(n) for n in range(1, 8)], [60, 120, 240, 480, 900, 900, 900])

        class Stop(Exception):
            pass
        clock = {"t": NOW}

        def sleep(seconds):
            clock["t"] += seconds
            if clock["t"] > NOW + 1000:
                raise Stop

        def broken(host, command, stdin=None):
            raise pusher.PushError("ssh không tới được hao")
        agent = agent_main.Agent(LiveSync(self.src), self.root, "fake:" + BUNDLE_REMOTE, "fake:" + STATUS_REMOTE, run=broken,
                                 clock=lambda: clock["t"], sleep=sleep, fetch=FakeCdn(), transcode=no_jxl, max_age_days=None)
        self.addCleanup(agent.release)
        steps = []
        original = agent.processors[0].step
        agent.processors[0].step = lambda: (steps.append(clock["t"] - NOW), original())[1]
        with self.assertRaises(Stop):
            agent.forever()
        self.assertLessEqual(len(steps), 6)                     # 1000 giây lỗi liên tục: vài lần thử, không phải ~1000
        self.assertGreaterEqual(len(steps), 4)
        gaps = [later - earlier for earlier, later in itertools.pairwise(steps)]
        self.assertEqual(gaps[:3], [63, 123, 243])             # 3 giây gom + 60, 120, 240 giây lùi
        self.assertEqual(agent.last["bundle"]["error"], "push_failed")

    def test_command_line_runs_under_isolated_python(self):
        done = subprocess.run([sys.executable, "-X", "utf8", "-I", str(ROOT / "tools" / "zalo_agent"), "run", "--once", "--dry-run",
                               "--max-fetch", "0", "--live-sync", str(self.src), "--root", str(self.root)], capture_output=True, check=False, timeout=120)
        self.assertEqual(done.returncode, 0, done.stderr.decode("utf-8", "replace"))
        self.assertEqual(json.loads(done.stdout.decode("utf-8"))["processors"]["bundle"]["error"], None)
        self.assertTrue((self.root / "state" / "status.json").is_file())
        self.assertTrue((self.root / "logs" / "agent.log").is_file())


if __name__ == "__main__":
    unittest.main()
