"""ZALO-AGENT-01 PR-4a-1 (sửa theo review): OCR ở tiến trình con, engine hỏng không làm mất ảnh, luồng nền không giữ agent.

Tiến trình con thật cần easyocr nên không chạy ở đây: dùng "con giả" là các script Python nhỏ nói đúng giao thức của `ocr_child.py`
(mỗi dòng stdin một yêu cầu JSON, mỗi dòng stdout một câu trả lời JSON). Không cần easyocr/torch/Pillow.
"""

import json
import sys
import tempfile
import threading
import unittest
import unittest.mock
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from test_zalo_agent_money_images import (  # noqa: E402
    JPEG_LOCAL,
    JXL_AS_JPEG,
    SHA_JXL,
    SHA_LOCAL,
    TRANSFER,
    FakeEngine,
    MoneyBase,
)
from zalo_agent import ocr  # noqa: E402
from zalo_agent.processors import money_images  # noqa: E402

REPLY = {"boxes": [{"b": [1, 2, 30, 40], "t": "1.500.000 VND", "c": 0.9}]}
OK = "import sys, json\nfor line in sys.stdin.buffer:\n    sys.stdout.write(json.dumps(@REPLY@) + '\\n'); sys.stdout.flush()\n"


class Picture:
    """Ảnh giả: `read` của EasyOcr chỉ cần `save(đường dẫn, "PNG")`."""
    def save(self, path, fmt):
        Path(path).write_bytes(b"png-gia")


class ChildTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)

    def engine(self, code, timeout=20):
        script = self.dir / "child.py"
        script.write_text(code, encoding="utf-8")
        engine = ocr.EasyOcr(command=[sys.executable, str(script), str(self.dir / "marker")], timeout=timeout, work=self.tmp.name)
        self.addCleanup(engine.close)
        return engine

    def test_one_long_lived_child_answers_many_requests_and_temp_images_are_removed(self):
        engine = self.engine(OK.replace("@REPLY@", json.dumps(REPLY)))
        for _ in range(3):
            self.assertEqual(engine.read(Picture()), REPLY["boxes"])
        self.assertIsNotNone(engine.child)
        pid = engine.child.pid
        engine.read(Picture())
        self.assertEqual(engine.child.pid, pid)   # sống lâu: không tạo lại mỗi ảnh
        self.assertEqual([path.name for path in self.dir.glob("*.png")], [])

    def test_dead_child_is_a_failure_of_that_read_and_the_next_read_respawns_it(self):
        code = ("import sys, json, os\nmarker = sys.argv[1]\nline = sys.stdin.buffer.readline()\n"
                "if not os.path.exists(marker):\n    open(marker, 'w').close()\n    os._exit(3)\n"
                "sys.stdout.write(json.dumps(@REPLY@) + '\\n'); sys.stdout.flush()\n").replace("@REPLY@", json.dumps(REPLY))
        engine = self.engine(code)
        with self.assertRaises(ocr.OcrFailure):
            engine.read(Picture())
        self.assertIsNone(engine.child)   # đã dọn
        self.assertEqual(engine.read(Picture()), REPLY["boxes"])   # con mới

    def test_child_that_hangs_is_killed_after_the_timeout(self):
        engine = self.engine("import sys, time\nsys.stdin.buffer.readline()\ntime.sleep(120)\n", timeout=1)
        with self.assertRaises(ocr.OcrFailure):
            engine.read(Picture())
        self.assertIsNone(engine.child)

    def test_missing_library_or_model_is_unavailable_not_a_failure_of_the_image(self):
        for code in ("unavailable", "model_missing"):
            engine = self.engine(OK.replace("@REPLY@", json.dumps({"error": code})))
            with self.assertRaises(ocr.OcrUnavailable):
                engine.read(Picture())

    def test_garbage_replies_and_bad_boxes_are_failures(self):
        for text in ("khong phai json", json.dumps({"boxes": "x"}), json.dumps({"boxes": [{"b": [1], "t": "x", "c": 0.5}]}),
                     json.dumps({"boxes": [{"b": [1, 2, 3, 4], "t": "x", "c": 7}]}), json.dumps({"error": "failed"})):
            engine = self.engine("import sys\nfor line in sys.stdin.buffer:\n    sys.stdout.write(@TEXT@ + '\\n'); sys.stdout.flush()\n".replace("@TEXT@", repr(text)))
            with self.assertRaises(ocr.OcrFailure, msg=text):
                engine.read(Picture())

    def test_no_interpreter_is_unavailable(self):
        engine = ocr.EasyOcr(command=[str(self.dir / "khong-co-python")])
        with self.assertRaises(ocr.OcrUnavailable):
            engine.read(Picture())

    def test_pythonw_is_replaced_by_python_for_the_child(self):
        with unittest.mock.patch.object(ocr.sys, "executable", str(self.dir / "Pythonw.exe")):
            self.assertEqual(Path(ocr.EasyOcr.interpreter()).name, "python.exe")

    def test_the_agent_process_never_imports_torch_or_easyocr(self):
        import subprocess
        code = (f"import sys; sys.path.insert(0, {str(ROOT / 'tools')!r}); import zalo_agent.__main__, zalo_agent.processors.money_images; "
                "print('torch' in sys.modules or 'easyocr' in sys.modules)")
        done = subprocess.run([sys.executable, "-I", "-c", code], capture_output=True, check=True)
        self.assertEqual(done.stdout.decode().strip(), "False")


class Crashy(FakeEngine):
    """Engine mà `read` ném lỗi theo kịch bản: OcrFailure (con chết), OcrUnavailable (thiếu thư viện/model)."""
    def __init__(self, error):
        super().__init__(script={JPEG_LOCAL: TRANSFER, JXL_AS_JPEG: TRANSFER})
        self.error = error

    def read(self, image):
        if self.error:
            raise self.error
        return super().read(image)


class RobustnessTest(MoneyBase):
    def test_engine_unavailable_keeps_the_images_waiting_and_never_marks_them_failed(self):
        engine = Crashy(ocr.OcrUnavailable("model_missing"))
        processor = self.make(engine=engine)
        for _ in range(8):
            result = processor.step()
        self.assertEqual((result["error"], result["counts"]["pending"], result["counts"]["failed"]), ("ocr_unavailable", 2, 0))
        self.assertTrue(all(item["tries"] == 0 for item in processor.state()["todo"]))   # không tính lần thử
        self.assertFalse(processor.wants_work())   # không đòi gom 3 giây mỗi vòng
        engine.error = None
        self.now += money_images.BROKEN + 1
        self.assertEqual(self.drain(processor)["counts"]["read"], 2)

    def test_unavailable_engine_is_not_asked_again_every_second(self):
        class Counting(Crashy):
            asked = 0

            @property
            def version(self):
                Counting.asked += 1
                return "1.0+t"

            @version.setter
            def version(self, value):
                pass
        engine = Counting(None)
        processor = self.make(engine=engine)
        processor.step()
        engine.error = ocr.OcrUnavailable("x")
        processor.step()   # đọc ảnh đầu: unavailable
        processor.step()   # thu kết quả, đặt `broken_until`
        asked = Counting.asked
        for _ in range(5):
            processor.step()
        self.assertEqual(Counting.asked, asked)

    def test_child_deaths_cool_the_engine_down_and_only_three_tries_per_image_then_failed_but_reread_can_retry(self):
        engine = Crashy(ocr.OcrFailure("child_died"))
        processor = self.make(engine=engine)
        processor.step()
        processor.step()   # lần đọc thứ nhất chết
        self.assertGreater(processor.cool_until, self.now)
        calls = engine.calls
        for _ in range(4):
            processor.step()
        self.assertEqual(engine.calls, calls)   # đang nghỉ: không đọc thêm
        for _ in range(12):
            self.now = max(self.now, processor.cool_until) + 1
            processor.step()
        self.assertEqual(processor.counts()["failed"], 2)   # cả hai ảnh thử đủ 3 lần
        self.assertEqual(processor.counts()["pending"], 0)
        # Engine lành lại: `reread` đọc được cả ảnh đã vào `failed`.
        engine.error = None
        counts = processor.reread(engine, 0)
        self.assertEqual((counts["wanted"], counts["read"], counts["failed"]), (2, 2, 0))
        self.assertTrue((self.root / "reads" / SHA_LOCAL).is_dir() and (self.root / "reads" / SHA_JXL).is_dir())

    def test_failed_images_are_tried_again_after_the_ban_and_find_the_result_already_in_the_store(self):
        engine = Crashy(ocr.OcrFailure("child_died"))
        processor = self.make(engine=engine)
        for _ in range(16):
            self.now = max(self.now, processor.cool_until) + 1
            processor.step()
        self.assertEqual(processor.counts()["failed"], 2)
        engine.error = None
        processor.reread(engine, 0)   # đọc ngoài agent: kho có kết quả
        self.now += money_images.FAILED_BAN + 1
        (self.src / "baseline-manifest.json").write_text(json.dumps({"messages_sha256": "b" * 64}), encoding="utf-8")   # buộc dựng lại
        self.assertEqual(self.drain(processor)["counts"]["read"], 2)   # sau hạn cấm: nhận lại từ kho, không đọc lại
        self.assertEqual(processor.counts()["pending"], 0)

    def test_background_runs_each_job_in_a_daemon_thread_so_exit_never_waits_for_ocr(self):
        future = money_images.Background().submit(lambda: threading.current_thread().daemon)
        self.assertTrue(future.result(timeout=10))
        failing = money_images.Background().submit(lambda: 1 / 0)
        with self.assertRaises(ZeroDivisionError):
            failing.result(timeout=10)


if __name__ == "__main__":
    unittest.main()
