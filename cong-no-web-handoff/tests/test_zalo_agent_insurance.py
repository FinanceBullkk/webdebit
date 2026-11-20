"""ZALO-AGENT-01 PR-3: bộ xử lý `insurance` (giấy bảo hiểm lên `hao`), thay `insurance_push.py`.

Dữ liệu bịa trong thư mục tạm: snapshot giả, PDF giả, máy chủ giả của `test_zalo_agent.Remote` (đoạn shell thật hoặc bản Python).
Bản gọn so từng byte với `tests/golden/zalo-insurance-web.json`, file sinh bằng chính `insurance_web.build` gốc trên cùng snapshot giả
(`python tests/test_zalo_agent_insurance.py --regen <đường dẫn insurance_web.py>`). Có `ZALO_INSURANCE_WEB_ORIGINAL=<insurance_web.py>`
thì so thêm trực tiếp với code gốc. Không đọc kho thật, không ssh.
"""

import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "web"))
import v7_insurance_queue as queue  # noqa: E402  (phía đọc trên hao: bản gọn phải qua được cổng kiểm của nó)
import zalo_web_bundle as wb  # noqa: E402
from test_zalo_agent import BUNDLE_REMOTE, STATUS_REMOTE, Remote  # noqa: E402
from test_zalo_web_bundle import (  # noqa: E402
    BASH,
    GROUP,
    KHACH,
    NOW,
    FakeCdn,
    no_jxl,
    row,
    write_source,
)
from zalo_agent import __main__ as agent_main  # noqa: E402
from zalo_agent import push as pusher  # noqa: E402
from zalo_agent import source as source_module  # noqa: E402
from zalo_agent import status as status_file  # noqa: E402
from zalo_agent.processors import insurance as ins  # noqa: E402
from zalo_agent.processors.insurance import InsuranceProcessor  # noqa: E402
from zalo_agent.source import VN, LiveSync  # noqa: E402

INS_REMOTE = "/srv/v7/insurance"
GOLDEN = ROOT / "tests" / "golden" / "zalo-insurance-web.json"
PRIVATE = ["BL-SECRET-77", "TAU GIA SO 9", "CONG TY KHACH GIA", "0312345678", "NIEMPHONG-5", "gui luc 09:15", "tin nhan rieng"]
PDFS = {name: f"%PDF-1.4 giay bao hiem gia {name}".encode() for name in ("a", "b", "c", "d")}
SHA = {name: hashlib.sha256(data).hexdigest() for name, data in PDFS.items()}


def fake_row(cert: str, pdf: str, container: str, **extra) -> dict:
    return {"cert_no": cert, "sha256": SHA[pdf], "container": container, "chat_bookings": ["BK-2", "BK-1", "BK-1", 7],
            "amount_vnd": 1_500_000, "cert_premium_vnd": 1_363_636, "cert_vat_vnd": 136_364, "cert_total_vnd": 1_500_000,
            "containers_on_cert": 2, "depart_date": "2026-11-01", "issue_date": "2026-10-30", "status": "ok",
            "warnings": ["info: có 2 container", "B/L BL-SECRET-77 không khớp", "Tàu TAU GIA SO 9 khác chuyến", "seal NIEMPHONG-5 lạ"],
            # Trường riêng tư và trường lạ: không được lọt ra bản gọn.
            "bl_no": "BL-SECRET-77", "vessel": "TAU GIA SO 9", "insured": "CONG TY KHACH GIA", "insured_tax_code": "0312345678",
            "seals": ["NIEMPHONG-5"], "sent_at": "gui luc 09:15", "message_text": "tin nhan rieng", **extra}


def fake_snapshot(rows: list | None = None) -> dict:
    if rows is None:
        rows = [fake_row("GIA-002", "b", "TEST0000002", amount_vnd=None, status="needs_review", warnings=["Thiếu số tiền"]),
                fake_row("GIA-001", "a", "TEST0000001", amount_vnd="1500000", cert_premium_vnd=1363636.0, cert_vat_vnd=12.5,
                         cert_total_vnd=True, containers_on_cert="2"),
                fake_row("GIA-001", "a", "TEST0000000"),            # cùng giấy, container khác: xếp theo (sha256, cert_no, container)
                "không phải dòng", {"sha256": SHA["c"]}, fake_row("GIA-003", "c", "TEST0000003", chat_bookings=None, warnings=None)]
    return {"schema_version": 1, "generated_at": "2026-11-01T09:00:00+07:00", "amount_basis": "certificate total incl. VAT", "rows": rows}


def dump(value) -> bytes:
    return json.dumps(value, ensure_ascii=False).encode("utf-8")


class FixedDatetime(datetime):
    @classmethod
    def now(cls, tz=None):
        return datetime.fromtimestamp(NOW, VN)


def regen(original: Path) -> None:
    """Sinh lại file golden bằng `insurance_web.build` gốc (đọc code gốc, không sửa nó)."""
    spec = importlib.util.spec_from_file_location("insurance_web_original", original)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "s.json").write_bytes(dump(fake_snapshot()))
        with patch.object(module, "datetime", FixedDatetime):
            module.build(Path(tmp) / "s.json", Path(tmp) / "o.json")
        GOLDEN.parent.mkdir(exist_ok=True)
        GOLDEN.write_bytes((Path(tmp) / "o.json").read_bytes())


class InsuranceCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name)
        self.src, self.root = base / "live-sync", base / "agent"
        self.src.mkdir()
        (base / "remote").mkdir()
        self.store = self.src / "remote-media-store"
        self.store.mkdir()
        self.remote = Remote(base / "remote")
        self.remote.dirs[INS_REMOTE] = base / "remote" / "insurance"
        self.remote.dirs[INS_REMOTE].mkdir()
        self.now = NOW
        self.live = LiveSync(self.src)
        self.state = self.root / "state"
        self.processor = self.make()
        self.hao = self.remote.dirs[INS_REMOTE]

    def make(self, **kwargs):
        args = {"run": self.remote, "clock": lambda: self.now, **kwargs}
        return InsuranceProcessor(self.live, self.state, self.root / "insurance", "fake:" + INS_REMOTE, **args)

    def put_snapshot(self, snapshot=None):
        (self.src / "insurance-snapshot.json").write_bytes(dump(fake_snapshot() if snapshot is None else snapshot))

    def put_pdf(self, name, as_file=None):
        # Kho đặt tên file theo băm URL, không theo nội dung: tên khác hẳn sha256 của nội dung.
        (self.store / f"{hashlib.sha256(('url-' + (as_file or name)).encode()).hexdigest()}.pdf").write_bytes(PDFS[name])

    def hao_files(self) -> dict[str, bytes]:
        return {path.relative_to(self.hao).as_posix(): path.read_bytes() for path in self.hao.rglob("*") if path.is_file()}

    def hao_web(self) -> dict:
        return json.loads((self.hao / "insurance-web.json").read_text(encoding="utf-8"))

    def start(self):
        self.put_snapshot()
        for name in "abc":
            self.put_pdf(name)
        self.put_pdf("d")   # PDF của kho không thuộc giấy nào: không được gửi



class InsuranceTest(InsuranceCase):
    # --- bản gọn: hợp đồng giữ nguyên ---
    def test_web_file_is_byte_identical_to_the_original_build_and_to_the_golden_file(self):
        self.start()
        self.processor.step()
        pushed = (self.hao / "insurance-web.json").read_bytes()
        self.assertEqual(pushed, GOLDEN.read_bytes())
        original = os.environ.get("ZALO_INSURANCE_WEB_ORIGINAL")
        if original:   # so trực tiếp với code gốc nếu máy này có nó
            spec = importlib.util.spec_from_file_location("insurance_web_original", original)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            (Path(self.tmp.name) / "s.json").write_bytes(dump(fake_snapshot()))
            with patch.object(module, "datetime", FixedDatetime):
                module.build(Path(self.tmp.name) / "s.json", Path(self.tmp.name) / "o.json")
            self.assertEqual(pushed, (Path(self.tmp.name) / "o.json").read_bytes())

    def test_contract_whitelist_no_private_values_and_the_reader_accepts_it(self):
        self.start()
        self.processor.step()
        web = self.hao_web()
        self.assertEqual((web["schema_version"], web["row_count"], len(web["rows"])), (1, 5, 5))
        self.assertEqual(set(web), {"schema_version", "created_at", "amount_basis", "row_count", "sha256", "rows"})
        fields = {"cert_no", "sha256", "container", "bookings", "amount_vnd", "cert_premium_vnd", "cert_vat_vnd", "cert_total_vnd",
                  "containers_on_cert", "depart_date", "issue_date", "status", "warnings"}
        self.assertTrue(all(set(row) == fields for row in web["rows"]))
        text = (self.hao / "insurance-web.json").read_text(encoding="utf-8")
        for secret in PRIVATE:
            self.assertNotIn(secret, text)
        self.assertEqual([row["container"] for row in web["rows"] if row["sha256"] == SHA["a"]], ["TEST0000000", "TEST0000001"])   # xếp theo container
        self.assertEqual([row["sha256"] for row in web["rows"]], sorted(row["sha256"] for row in web["rows"]))
        by_container = {row["container"]: row for row in web["rows"]}
        self.assertIsNone(by_container["TEST0000002"]["amount_vnd"])                 # NULL không thành 0
        self.assertEqual(by_container["TEST0000001"]["amount_vnd"], 1_500_000)        # chuỗi số thành int
        self.assertIsNone(by_container["TEST0000001"]["cert_vat_vnd"])               # 12,5 không nguyên: NULL
        self.assertIsNone(by_container["TEST0000001"]["cert_total_vnd"])             # bool không là số
        self.assertEqual(by_container["TEST0000000"]["bookings"], ["BK-1", "BK-2"])  # sắp, bỏ trùng, bỏ không phải chuỗi
        self.assertEqual(by_container["TEST0000000"]["warnings"],
                         ["info: có 2 container", "B/L [redacted] không khớp", "Tàu [redacted] khác chuyến", "seal [redacted] lạ"])
        loaded = queue.load_insurance_snapshot(self.hao / "insurance-web.json")     # cổng kiểm của phía đọc: schema, sha256 dòng
        self.assertEqual(loaded["row_count"], 5)
        self.assertEqual(queue.cert_pdf(loaded, SHA["a"], self.hao / "pdf"), PDFS["a"])

    # --- đẩy ---
    def test_first_push_sends_needed_pdfs_by_content_hash_and_final_file_last(self):
        self.start()
        result = self.processor.step()
        self.assertEqual((result["action"], result["error"], result["revision"]), ("push", None, None))
        self.assertEqual(sorted(self.hao_files()), sorted(["insurance-web.json", *(f"pdf/{SHA[name]}.pdf" for name in "abc")]))
        for name in "abc":
            self.assertEqual((self.hao / "pdf" / f"{SHA[name]}.pdf").read_bytes(), PDFS[name])
        self.assertNotIn(f"pdf/{SHA['d']}.pdf", self.hao_files())          # PDF không thuộc giấy nào ở lại máy này
        self.assertEqual(self.remote.tars[-1][-1], "insurance-web.json")   # file chốt là thành viên cuối của tar
        self.assertIn("pdf_sent=3", result["reason"])
        self.assertEqual(list(self.hao.glob(".incoming-*")), [])

    def test_unchanged_snapshot_sends_no_tar_and_asks_the_server_only_when_resync_is_due(self):
        self.start()
        self.processor.step()
        calls, applies = len(self.remote.calls), self.remote.applies(INS_REMOTE)
        self.assertFalse(self.processor.wants_work())
        self.now += 60
        self.assertEqual(self.processor.step()["action"], "idle")
        self.assertEqual(len(self.remote.calls), calls)                      # chưa tới 15 phút: không hỏi gì cả
        self.now += ins.RESYNC
        result = self.processor.step()
        self.assertEqual((result["action"], result["bytes_sent"], result["error"]), ("idle", 0, None))
        self.assertEqual((len(self.remote.calls), self.remote.applies(INS_REMOTE)), (calls + 1, applies))   # một lượt hỏi, không gửi tar
        self.assertEqual(self.hao_web()["created_at"], status_file.now_iso(NOW))   # `created_at` giữ nguyên khi các dòng không đổi

    def test_resync_repairs_what_the_server_lost(self):
        self.start()
        self.processor.step()
        (self.hao / "pdf" / f"{SHA['b']}.pdf").unlink()
        (self.hao / "pdf" / f"{SHA['a']}.pdf").write_bytes(b"cut")          # sai cỡ
        self.now += ins.RESYNC
        result = self.processor.step()
        self.assertEqual(result["action"], "push")
        self.assertEqual((self.hao / "pdf" / f"{SHA['b']}.pdf").read_bytes(), PDFS["b"])
        self.assertEqual((self.hao / "pdf" / f"{SHA['a']}.pdf").read_bytes(), PDFS["a"])

    def test_new_pdf_in_the_store_is_sent_alone_and_without_rewriting_the_web_file(self):
        self.put_snapshot()
        self.put_pdf("a")
        self.put_pdf("b")
        first = self.processor.step()                                        # thiếu PDF c: vẫn đẩy bản gọn, c chưa có
        self.assertNotIn(f"pdf/{SHA['c']}.pdf", self.hao_files())
        self.assertIn("missing_local=1", first["reason"])
        web = (self.hao / "insurance-web.json").read_bytes()
        self.now += 30
        self.put_pdf("c")
        self.assertTrue(self.processor.wants_work())                         # kho đổi: gom 3 giây rồi xử lý
        before = len(self.remote.tars)
        result = self.processor.step()
        self.assertEqual(result["action"], "push")
        self.assertEqual([name for name in self.remote.tars[before] if name.startswith("pdf/")], [f"pdf/{SHA['c']}.pdf"])
        self.assertEqual((self.hao / "insurance-web.json").read_bytes(), web)   # các dòng không đổi: cùng byte, cùng created_at
        self.assertEqual((self.hao / "pdf" / f"{SHA['c']}.pdf").read_bytes(), PDFS["c"])

    def test_changed_snapshot_sends_the_new_pdf_prunes_the_old_and_rewrites_the_web_file(self):
        self.start()
        self.processor.step()
        self.now += 60
        self.put_snapshot(fake_snapshot([fake_row("GIA-001", "a", "TEST0000001"), fake_row("GIA-004", "d", "TEST0000004")]))
        self.assertTrue(self.processor.wants_work())
        result = self.processor.step()
        self.assertEqual((result["action"], result["error"]), ("push", None))
        self.assertEqual(sorted(name for name in self.hao_files() if name.startswith("pdf/")),
                         sorted(f"pdf/{SHA[name]}.pdf" for name in "ad"))     # b và c không còn giấy nào dùng: dọn
        web = self.hao_web()
        self.assertEqual((web["row_count"], web["created_at"]), (2, status_file.now_iso(NOW + 60)))
        self.assertFalse(self.processor.wants_work())

    def test_zero_rows_is_refused_and_the_server_keeps_everything(self):
        self.start()
        self.processor.step()
        before = self.hao_files()
        for snapshot in (fake_snapshot([]), fake_snapshot(["không phải dòng"])):
            self.now += 60
            self.put_snapshot(snapshot)
            calls = len(self.remote.calls)
            result = self.processor.step()
            self.assertEqual((result["action"], result["error"]), ("idle", "empty_snapshot"))
            self.assertEqual((self.hao_files(), len(self.remote.calls)), (before, calls))   # không hỏi, không gửi, không dọn

    def test_bad_snapshot_is_an_error_code_not_a_push(self):
        self.start()
        self.processor.step()
        before = self.hao_files()
        for raw in (b"{khong phai json", dump({"schema_version": 2, "rows": []}), dump([1, 2]), dump({"schema_version": 1})):
            self.now += 60
            (self.src / "insurance-snapshot.json").write_bytes(raw)
            self.assertEqual(self.processor.step()["error"], "snapshot_invalid")
            self.assertEqual(self.hao_files(), before)

    def test_missing_snapshot_is_quiet_until_it_has_existed_then_it_is_an_error(self):
        self.assertEqual((self.processor.step()["action"], self.processor.step()["error"]), ("idle", None))   # chưa cài insurance_sync
        self.assertFalse(self.processor.wants_work())
        self.start()
        self.processor.step()
        (self.src / "insurance-snapshot.json").unlink()
        self.now += 60
        self.assertEqual(self.processor.step()["error"], "no_snapshot")

    def test_pdf_with_no_local_copy_stays_on_the_server_while_a_row_still_uses_it(self):
        self.start()
        self.processor.step()
        for path in self.store.glob("*.pdf"):
            if path.read_bytes() == PDFS["b"]:
                path.unlink()                                                 # kho tạm mất PDF b, dòng của b vẫn trong snapshot
        stale = self.hao / "pdf" / ("e" * 64 + ".pdf")
        stale.write_bytes(b"khong ai dung")
        self.now += 60
        result = self.processor.step()
        self.assertEqual(result["action"], "push")
        self.assertIn("missing_local=1", result["reason"])
        self.assertTrue((self.hao / "pdf" / f"{SHA['b']}.pdf").is_file())     # giữ: còn dòng dùng nó
        self.assertFalse(stale.exists())                                      # không ai dùng: dọn
        self.assertTrue((self.hao / "pdf" / f"{SHA['a']}.pdf").is_file())

    def test_other_files_on_the_server_are_left_alone_and_unreferenced_pdf_prune_needs_no_new_file(self):
        self.start()
        self.processor.step()
        (self.hao / "ghi-chu.txt").write_text("giữ", encoding="utf-8")
        (self.hao / "pdf" / ("f" * 64 + ".pdf")).write_bytes(b"x")
        self.now += ins.RESYNC
        self.assertEqual(self.processor.step()["action"], "push")
        self.assertEqual((self.hao / "ghi-chu.txt").read_text(encoding="utf-8"), "giữ")
        self.assertFalse((self.hao / "pdf" / ("f" * 64 + ".pdf")).exists())

    # --- cache băm PDF ---
    def test_pdfs_are_hashed_once_and_again_only_when_size_or_mtime_changes(self):
        self.start()
        hashed = []
        real = ins.sha256_file

        def counting(path):
            hashed.append(Path(path).name)
            return real(path)
        with patch.object(ins, "sha256_file", counting):
            self.processor.step()
            self.assertEqual(len(hashed), 4)                                  # 4 PDF của kho, mỗi file một lần
            self.now += 60
            self.put_snapshot(fake_snapshot([fake_row("GIA-001", "a", "TEST0000001")]))   # snapshot đổi, kho không
            self.processor.step()
            self.now += ins.RESYNC
            self.processor.step()
            self.assertEqual(len(hashed), 4)                                  # không băm lại
            touched = next(path for path in self.store.glob("*.pdf") if path.read_bytes() == PDFS["d"])
            os.utime(touched, ns=(1_700_000_000_000_000_000, 1_700_000_000_000_000_000))
            self.processor.step()
            self.assertEqual(hashed[4:], [touched.name])                      # đúng file đổi mtime
            self.assertEqual(sorted(json.loads((self.state / "insurance.json").read_text(encoding="utf-8"))["pdf_cache"]),
                             sorted(path.name for path in self.store.glob("*.pdf")))

    def test_state_file_holds_only_hashes_counts_and_times(self):
        self.start()
        self.processor.step()
        text = (self.state / "insurance.json").read_text(encoding="utf-8")
        saved = json.loads(text)
        self.assertEqual(set(saved), {"snapshot_sha256", "store_sig", "checked_at", "pdf_cache", "pdf_missing", "updated_at"})
        for secret in PRIVATE:
            self.assertNotIn(secret, text)

    # --- lỗi đẩy, dry-run, status ---
    def test_failed_push_keeps_the_trigger_and_the_hash_cache_and_retries_to_the_same_bytes(self):
        self.start()

        def broken(host, command, stdin=None):
            raise pusher.PushError("mạng đứt tới 100.1.2.3")
        result = self.make(run=broken).step()
        self.assertEqual((result["action"], result["error"]), ("retry", "push_failed"))
        saved = json.loads((self.state / "insurance.json").read_text(encoding="utf-8"))
        self.assertNotIn("snapshot_sha256", saved)                            # chưa tiến: lượt sau vẫn phải đẩy
        self.assertEqual(len(saved["pdf_cache"]), 4)
        self.assertTrue(self.processor.wants_work())
        web = (self.root / "insurance" / "insurance-web.json").read_bytes()
        self.now += 600
        self.assertEqual(self.processor.step()["action"], "push")
        self.assertEqual((self.hao / "insurance-web.json").read_bytes(), web)  # bản gọn giữ nguyên byte qua lần thử lại, created_at cũ
        self.assertEqual(self.hao_web()["created_at"], status_file.now_iso(NOW))

    def test_error_since_is_set_on_failure_and_cleared_on_recovery_in_status_json(self):
        self.start()
        write_source(self.src)
        wb.Source(self.src).save_selection([GROUP])
        clock = {"t": NOW}
        mode = {"fail": True}

        def run(host, command, stdin=None):
            if mode["fail"]:
                raise pusher.PushError("hao không tới được")
            return self.remote(host, command, stdin)
        agent = agent_main.Agent(LiveSync(self.src), self.root, "fake:" + BUNDLE_REMOTE, "fake:" + STATUS_REMOTE, run=run,
                                 clock=lambda: clock["t"], fetch=FakeCdn(), transcode=no_jxl, max_age_days=None,
                                 insurance_target="fake:" + INS_REMOTE)
        self.addCleanup(agent.release)
        first = agent.cycle(force_status=True)["processors"]["insurance"]
        self.assertEqual((first["error"], first["error_since"], first["last_ok_at"], first["revision"], first["lag_revisions"]),
                         ("push_failed", status_file.now_iso(NOW), None, None, None))
        self.assertEqual(set(first), {"revision", "lag_revisions", "last_ok_at", "error", "error_since"})
        clock["t"] += 600
        again = agent.cycle(force_status=True)["processors"]["insurance"]
        self.assertEqual(again["error_since"], status_file.now_iso(NOW))      # vẫn lỗi: giữ mốc
        mode["fail"] = False
        clock["t"] += 600
        agent.retry_at = dict.fromkeys(agent.retry_at, 0.0)
        status = agent.cycle(force_status=True)
        ok = status["processors"]["insurance"]
        self.assertEqual((ok["error"], ok["error_since"], ok["last_ok_at"]), (None, None, status_file.now_iso(NOW + 1200)))
        self.assertTrue((self.hao / "insurance-web.json").is_file())
        remote_status = json.loads((self.remote.dirs[STATUS_REMOTE] / "status.json").read_text(encoding="utf-8"))
        self.assertIn("insurance", remote_status["processors"])

    def test_dry_run_builds_locally_pushes_nothing_saves_nothing_and_does_not_block_the_real_run(self):
        self.start()
        dry = self.make(dry_run=True)
        result = dry.step()
        self.assertEqual((result["action"], result["error"], self.remote.calls), ("idle", None, []))
        self.assertFalse(self.state.exists())                                 # không con trỏ, không cache
        self.assertTrue((self.root / "insurance" / "insurance-web.json").is_file())
        self.assertEqual(dry.step()["action"], "idle")
        self.assertEqual(self.remote.calls, [])
        real = self.processor.step()
        self.assertEqual((real["action"], real["error"]), ("push", None))
        self.assertTrue((self.hao / "insurance-web.json").is_file())

    def test_agent_registers_insurance_only_with_a_target_and_the_command_line_has_defaults(self):
        agent = agent_main.Agent(self.live, self.root, "fake:/a", "fake:/b", run=self.remote)
        self.addCleanup(agent.release)
        self.assertEqual([processor.name for processor in agent.processors], ["bundle"])
        write_source(self.src)
        wb.Source(self.src).save_selection([GROUP])
        base = [sys.executable, "-X", "utf8", "-I", str(ROOT / "tools" / "zalo_agent"), "run", "--once", "--dry-run", "--max-fetch", "0",
                "--live-sync", str(self.src), "--insurance-store", str(self.store)]
        off = subprocess.run([*base, "--root", str(self.root / "cli-off")], capture_output=True, check=False, timeout=120)
        self.assertEqual(off.returncode, 0, off.stderr.decode("utf-8", "replace"))
        self.assertNotIn("insurance", json.loads(off.stdout.decode("utf-8"))["processors"])   # mặc định TẮT: chưa bật thì không ghi /srv/v7/insurance
        on = subprocess.run([*base, "--root", str(self.root / "cli-on"), "--insurance-target", "hao:/srv/v7/insurance"],
                            capture_output=True, check=False, timeout=120)
        self.assertEqual(on.returncode, 0, on.stderr.decode("utf-8", "replace"))
        self.assertEqual(json.loads(on.stdout.decode("utf-8"))["processors"]["insurance"]["error"], None)

    @unittest.skipUnless(BASH, "cần bash và tar để chạy đoạn shell phía máy chủ")
    def test_real_shell_matches_the_python_fake_for_the_insurance_plan(self):
        self.start()
        root = Path(self.tmp.name) / "real"
        (root / "remote").mkdir(parents=True)
        real = Remote(root / "remote", fast=False)
        real.dirs[INS_REMOTE] = root / "remote" / "insurance"
        real.dirs[INS_REMOTE].mkdir()
        twin = InsuranceProcessor(self.live, root / "state", root / "insurance", "fake:" + INS_REMOTE, run=real, clock=lambda: self.now)
        steps = [lambda: None,
                 lambda: (self.put_snapshot(fake_snapshot([fake_row("GIA-001", "a", "TEST0000001"), fake_row("GIA-004", "d", "TEST0000004")])),
                          setattr(self, "now", self.now + 60)),
                 lambda: (shutil.rmtree(self.store), self.store.mkdir(), setattr(self, "now", self.now + 60))]   # kho mất hết: giữ PDF đang có
        for index, change in enumerate(steps):
            change()
            self.processor.step()
            twin.step()
            self.assertEqual(self.hao_files(),
                             {path.relative_to(real.dirs[INS_REMOTE]).as_posix(): path.read_bytes()
                              for path in real.dirs[INS_REMOTE].rglob("*") if path.is_file()}, f"bước {index}")
        self.assertEqual(sorted(name for name in self.hao_files() if name.startswith("pdf/")),
                         sorted(f"pdf/{SHA[name]}.pdf" for name in "ad"))


class InsuranceRobustnessTest(InsuranceCase):
    """Các ca từ review PR-3: PDF đổi giữa chừng, dòng sai sha256, PDF mất ở cả hai nơi, cache stat của snapshot."""

    def test_row_with_missing_or_bad_sha256_is_refused_so_the_server_keeps_its_good_file(self):
        self.start()
        self.processor.step()
        before = self.hao_files()
        for bad in (None, "", "khong-phai-hex", "A" * 64):
            self.now += 60
            self.put_snapshot(fake_snapshot([fake_row("GIA-001", "a", "TEST0000001"), {**fake_row("GIA-009", "b", "TEST0000009"), "sha256": bad}]))
            calls = len(self.remote.calls)
            result = self.processor.step()
            self.assertEqual((result["action"], result["error"]), ("idle", "snapshot_invalid"))
            self.assertEqual((self.hao_files(), len(self.remote.calls)), (before, calls))   # không đẩy, không dọn pdf/*

    def test_pdf_missing_on_both_sides_is_reported_and_stays_until_the_pdf_arrives(self):
        self.put_snapshot()
        self.put_pdf("a")
        self.put_pdf("b")                                                     # thiếu PDF c ở máy, hao cũng chưa có
        first = self.processor.step()
        self.assertEqual((first["action"], first["error"]), ("push", "pdf_missing"))   # đã đẩy phần có, nhưng không im lặng
        self.assertIn("missing_on_hao=1", first["reason"])
        self.now += 60
        self.assertEqual(self.processor.step()["error"], "pdf_missing")        # lượt không có gì mới vẫn báo, không nhấp nháy
        self.put_pdf("c")
        self.assertTrue(self.processor.wants_work())
        done = self.processor.step()
        self.assertEqual((done["action"], done["error"]), ("push", None))
        self.assertEqual(self.processor.step()["error"], None)
        local_only = self.make(dry_run=True)                                  # dry-run không hỏi hao nên không kết luận được: không báo
        self.assertIsNone(local_only.step()["error"])

    def test_pdf_missing_locally_but_present_on_hao_is_not_an_error(self):
        self.start()
        self.processor.step()
        for path in self.store.glob("*.pdf"):
            if path.read_bytes() == PDFS["b"]:
                path.unlink()
        self.now += 60
        self.assertEqual(self.processor.step()["error"], None)

    def test_pdf_whose_content_changed_after_hashing_is_not_sent_under_the_old_name(self):
        self.put_snapshot()
        self.put_pdf("b")
        self.put_pdf("c")
        wrong = self.store / ("9" * 64 + ".pdf")
        wrong.write_bytes(PDFS["d"])                                          # nội dung d, nhưng cache (cũ) tin là a
        stat = wrong.stat()
        self.state.mkdir(parents=True)
        (self.state / "insurance.json").write_text(json.dumps({"pdf_cache": {wrong.name: [stat.st_size, stat.st_mtime_ns, SHA["a"]]}}), encoding="utf-8")
        result = self.processor.step()
        self.assertEqual((result["action"], result["error"]), ("retry", "pdf_changed"))
        self.assertNotIn(f"pdf/{SHA['a']}.pdf", self.hao_files())              # không gửi nội dung sai dưới tên a
        saved = json.loads((self.state / "insurance.json").read_text(encoding="utf-8"))
        self.assertNotIn(wrong.name, saved["pdf_cache"])                      # cache bỏ file đó: lượt sau băm lại
        self.assertNotIn("snapshot_sha256", saved)                            # chưa tiến: lượt sau vẫn đẩy
        self.now += 10
        after = self.processor.step()
        self.assertEqual(after["error"], "pdf_missing")                        # băm lại ra d, không ai dùng; a thiếu ở cả hai nơi
        self.assertNotIn(f"pdf/{SHA['a']}.pdf", self.hao_files())

    def test_snapshot_is_hashed_only_when_stat_changes_or_resync_is_due_and_retries_a_locked_file(self):
        self.start()
        reads = []
        real = ins.retry_io
        with patch.object(ins, "retry_io", lambda action, *a, **k: (reads.append(1) if getattr(action, "__name__", "") == "read_bytes" else None, real(action, *a, **k))[1]):
            self.processor.step()
            for _ in range(5):
                self.now += 1
                self.processor.wants_work()
                self.processor.step()
            self.assertEqual(len(reads), 1)                                   # mỗi giây một lượt, vẫn một lần đọc
            self.now += ins.RESYNC
            self.processor.step()
            self.assertEqual(len(reads), 2)                                   # mốc an toàn: đọc lại sau 15 phút dù stat không đổi
            self.put_snapshot(fake_snapshot([fake_row("GIA-001", "a", "TEST0000001")]))
            self.processor.step()
            self.assertEqual(len(reads), 3)                                   # stat đổi
        self.assertEqual(self.hao_web()["row_count"], 1)

    def test_locked_snapshot_is_retried_then_reported_as_unreadable(self):
        self.start()
        real = self.src / "insurance-snapshot.json"

        class Locked:
            def __init__(self, fails):
                self.fails = fails

            def stat(self):
                return real.stat()

            def read_bytes(self):
                if self.fails:
                    self.fails -= 1
                    raise PermissionError(5, "Access is denied")
                return real.read_bytes()
        with patch.object(source_module, "PAUSE", 0):
            self.processor.snapshot = Locked(2)                               # insurance_sync đang giữ file tạm thời
            self.assertEqual(self.processor.step()["error"], None)
            self.assertEqual(self.hao_web()["row_count"], 5)
            self.processor.seen = None
            self.processor.snapshot = Locked(99)                              # giữ mãi
            self.assertFalse(self.processor.wants_work())
            self.assertEqual(self.processor.step()["error"], "snapshot_unreadable")


class AgentIsolationTest(unittest.TestCase):
    """Lùi dần riêng từng bộ xử lý và `--dry-run` của `bundle` giữ con trỏ trong bộ nhớ."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name)
        self.src, self.root = base / "live-sync", base / "agent"
        self.src.mkdir()
        (base / "remote").mkdir()
        write_source(self.src)
        wb.Source(self.src).save_selection([GROUP])
        (self.src / "remote-media-store").mkdir()
        (self.src / "poller-identity.json").write_text(json.dumps({"status": "attached"}), encoding="utf-8")
        self.remote = Remote(base / "remote")
        self.remote.dirs[INS_REMOTE] = base / "remote" / "insurance"
        self.remote.dirs[INS_REMOTE].mkdir()
        self.clock = {"t": NOW}
        self.live = LiveSync(self.src)

    def make_agent(self, run=None, **kwargs):
        def sleep(seconds):
            self.clock["t"] += seconds
        agent = agent_main.Agent(self.live, self.root, "fake:" + BUNDLE_REMOTE, "fake:" + STATUS_REMOTE, run=run or self.remote,
                                 clock=lambda: self.clock["t"], sleep=sleep, fetch=FakeCdn(), transcode=no_jxl, max_age_days=None,
                                 insurance_target=kwargs.pop("insurance_target", "fake:" + INS_REMOTE), **kwargs)
        self.addCleanup(agent.release)
        return agent

    def put_snapshot(self, snapshot):
        (self.src / "insurance-snapshot.json").write_bytes(dump(snapshot))

    def publish(self, body):
        revision = self.live.revision() + 1
        name = f"z{revision}"
        lines = (self.src / "messages.jsonl").read_text(encoding="utf-8").splitlines()
        lines.append(json.dumps(row(GROUP, name, KHACH, 1_700_000_200_000 + revision, body), ensure_ascii=False))
        (self.src / "messages.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
        (self.src / f"changes-{revision}.json").write_text(json.dumps({"revision": revision, "added": [name], "updated": [], "deleted": []}),
                                                         encoding="utf-8")
        (self.src / "revision.json").write_text(json.dumps({"revision": revision, "message_publish_epoch_ms": int(self.clock["t"] * 1000)}),
                                                encoding="utf-8")

    def hao_deltas(self) -> int:
        found = list(self.remote.dirs[BUNDLE_REMOTE].glob("data-*/messages-delta.jsonl"))
        return sum(len(path.read_text(encoding="utf-8").splitlines()) for path in found)

    def test_insurance_push_failures_never_slow_the_chat_bundle(self):
        self.put_snapshot(fake_snapshot())
        for name in "abc":
            (self.src / "remote-media-store" / (name * 8 + ".pdf")).write_bytes(PDFS[name])

        def run(host, command, stdin=None):
            if INS_REMOTE in command:                                         # /srv/v7/insurance mất setgid như 19/11
                raise pusher.PushError("hao từ chối")
            return self.remote(host, command, stdin)
        agent = self.make_agent(run)
        agent.tick()
        self.assertEqual((agent.last["bundle"]["error"], agent.last["insurance"]["error"]), (None, "push_failed"))
        self.assertEqual((agent.failures["bundle"], agent.retry_at["bundle"]), (0, 0.0))
        self.assertEqual(agent.failures["insurance"], 1)
        self.assertGreaterEqual(agent.retry_at["insurance"], self.clock["t"] + 59)
        steps = []
        original = agent.processors[1].step
        agent.processors[1].step = lambda: (steps.append(1), original())[1]
        for number in range(3):                                               # gói chat vẫn chạy mỗi nhịp và đẩy được
            self.publish(f"tin số {number}")
            agent.tick()
            self.assertEqual((agent.last["bundle"]["action"], agent.last["bundle"]["error"]), ("delta", None))
            self.assertEqual(agent.ran, ["bundle"])
        self.assertEqual(self.hao_deltas(), 3)
        self.assertEqual(steps, [])                                           # bảo hiểm đang lùi: không chạm hao
        status = agent.cycle(force_status=True)
        self.assertEqual((status["processors"]["bundle"]["error"], status["processors"]["insurance"]["error"]), (None, "push_failed"))
        self.assertIsNone(status["push"]["error"])                            # `push` chỉ là nhịp tim, không gom lỗi của bộ xử lý

    def test_local_insurance_errors_do_not_make_the_bundle_retry_every_ten_seconds(self):
        self.put_snapshot(fake_snapshot([]))                                  # snapshot rỗng: empty_snapshot
        agent = self.make_agent()
        agent.tick()
        self.assertEqual(agent.last["insurance"]["error"], "empty_snapshot")
        self.assertEqual((agent.retry_at["bundle"], agent.failures["bundle"]), (0.0, 0))
        self.assertAlmostEqual(agent.retry_at["insurance"], self.clock["t"] + 10, delta=1)
        sleeps = []
        agent.sleep = lambda seconds: (sleeps.append(seconds), self.clock.__setitem__("t", self.clock["t"] + seconds))[1]
        agent.tick()
        self.assertEqual((agent.ran, sleeps), (["bundle"], []))               # bảo hiểm còn đợi 10 giây: chỉ bundle chạy, không gom 3 giây
        self.publish("tin mới")
        agent.tick()
        self.assertEqual((agent.last["bundle"]["action"], sleeps), ("delta", [agent_main.SETTLE]))

    def test_a_broken_wants_work_does_not_stop_the_other_processor(self):
        agent = self.make_agent()
        self.publish("tin mới")
        agent.processors[1].wants_work = lambda: (_ for _ in ()).throw(RuntimeError("lỗi bất ngờ"))
        agent.cycle()
        self.publish("tin nữa")
        self.assertTrue(agent.wants_work())                                   # bundle vẫn báo có việc
        agent.processors[0].wants_work = lambda: False
        self.assertFalse(agent.wants_work())                                  # không ném lỗi ra vòng lặp

    def test_dry_run_loop_builds_the_bundle_once_not_every_few_seconds(self):
        built = []
        real = wb.build

        def counting(*args, **kwargs):
            built.append(1)
            return real(*args, **kwargs)
        agent = self.make_agent(dry_run=True, insurance_target="")
        with patch.object(wb, "build", counting):
            for _ in range(6):
                agent.tick()
        self.assertEqual(len(built), 1)
        self.assertEqual(self.remote.calls, [])
        self.assertFalse((self.root / "state" / "bundle.json").exists())      # vẫn không lưu con trỏ ra đĩa
        self.publish("tin mới")                                               # có tin mới thì dry-run vẫn xử lý phần thêm, không dựng lại
        with patch.object(wb, "build", counting):
            agent.tick()
        self.assertEqual((len(built), agent.last["bundle"]["action"]), (1, "delta"))


class PlanKeepTest(unittest.TestCase):
    """`Plan.keep`: tên giữ nếu máy chủ có, không gửi (thêm ở PR-3 cho PDF tạm mất ở máy)."""

    def test_keep_names_are_validated_and_must_not_duplicate_files_or_the_final(self):
        item = pusher.Item("pdf/" + "a" * 64 + ".pdf", b"x", True)
        final = pusher.Item("insurance-web.json", b"{}")
        for plan in (pusher.Plan("h:/srv/x", (item,), final, ("pdf/*",), keep=(item.rel,)),
                     pusher.Plan("h:/srv/x", (), final, ("pdf/*",), keep=("pdf/a b",)),
                     pusher.Plan("h:/srv/x", (), final, ("pdf/*",), keep=("insurance-web.json",)),
                     pusher.Plan("h:/srv/x", (), final, ("pdf/*",), keep=("../x",))):
            with self.assertRaises(pusher.PushError):
                pusher.validate(plan)
        pusher.validate(pusher.Plan("h:/srv/x", (item,), final, ("pdf/*",), keep=("pdf/" + "b" * 64 + ".pdf",)))


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--regen":
        regen(Path(sys.argv[2]))
    else:
        unittest.main()
