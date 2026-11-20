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


STUBS = {
    "numpy.py": "def asarray(value):\n    return value\n",
    "torch.py": "def set_num_threads(count):\n    pass\n",
    "PIL/__init__.py": ("class _Picture:\n    def __enter__(self):\n        return self\n    def __exit__(self, *args):\n        return False\n"
               "    def convert(self, mode):\n        return self\nclass Image:\n    @staticmethod\n    def open(path):\n        return _Picture()\n"),
    "easyocr.py": ("import os\nclass Reader:\n    def __init__(self, languages, gpu=False, verbose=False, download_enabled=True):\n"
                   "        assert download_enabled is False\n        os.write(1, b'RAC native\\n')\n        print('rac python')\n"
                   "    def readtext(self, image):\n        os.write(1, b'RAC native 2\\n')\n        print('rac python 2')\n"
                   "        return [([[1.4, 2.6], [30.2, 2.0], [30.0, 20.0], [1.0, 20.6]], 'Giao dich', 0.7295)]\n"),
    "easyocr_missing_model.py": "class Reader:\n    def __init__(self, *args, **kwargs):\n        raise FileNotFoundError('Missing model and downloads disabled')\n",
}


class RealChildTest(unittest.TestCase):
    """`ocr_child.py` thật chạy với thư viện **giả** (không cần easyocr/torch/Pillow): kiểm giao thức, ép số nguyên, đường trả lời riêng."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)
        self.stubs = self.dir / "stubs"
        self.stubs.mkdir()
        for name, text in STUBS.items():
            (self.stubs / name).parent.mkdir(parents=True, exist_ok=True)
            (self.stubs / name).write_text(text, encoding="utf-8")

    def engine(self, easyocr="easyocr.py"):
        if easyocr != "easyocr.py":
            (self.stubs / "easyocr.py").write_text((self.stubs / easyocr).read_text(encoding="utf-8"), encoding="utf-8")
        env = unittest.mock.patch.dict("os.environ", {"PYTHONPATH": str(self.stubs)})
        env.start()
        self.addCleanup(env.stop)
        engine = ocr.EasyOcr(command=[sys.executable, "-X", "utf8", str(ocr.CHILD), "2"], timeout=30, work=str(self.dir / "tmp"))
        self.addCleanup(engine.close)
        return engine

    def test_numpy_style_floats_become_plain_ints_and_stdout_noise_never_breaks_the_protocol(self):
        engine = self.engine()
        for _ in range(2):   # hai lượt: tiếng ồn ở stdout (kể cả ghi thẳng fd 1) xảy ra ở cả hai lượt
            boxes = engine.read(Picture())
            self.assertEqual(boxes, [{"b": [1, 2, 30, 21], "t": "Giao dich", "c": 0.73, "p": [[1, 3], [30, 2], [30, 20], [1, 21]]}])
        self.assertTrue(all(type(value) is int for box in boxes for value in box["b"]))

    def test_missing_model_is_reported_not_downloaded(self):
        engine = self.engine("easyocr_missing_model.py")
        with self.assertRaises(ocr.OcrUnavailable):
            engine.read(Picture())

    def test_malformed_request_line_gets_bad_request_and_the_child_keeps_serving(self):
        engine = self.engine()
        child = engine.spawn()
        child.stdin.write(b"khong phai json\n")
        child.stdin.flush()
        self.assertEqual(json.loads(child.stdout.readline()), {"error": "bad_request"})
        self.assertEqual(engine.read(Picture())[0]["t"], "Giao dich")


class WorkDirTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)

    def test_temp_pngs_live_in_the_agent_work_dir_and_leftovers_are_swept_at_startup(self):
        work = self.dir / "tmp"
        work.mkdir()
        (work / "ocr-old.png").write_bytes(b"sot")
        (work / "giu-lai.txt").write_text("khong phai png cua OCR", encoding="utf-8")
        seen = self.dir / "seen.txt"
        script = self.dir / "child.py"
        script.write_text("import sys, json\nfor line in sys.stdin.buffer:\n    open(@SEEN@, 'w').write(json.loads(line)['path'])\n"
                          "    sys.stdout.write(json.dumps({'boxes': []}) + '\\n'); sys.stdout.flush()\n".replace("@SEEN@", repr(str(seen))), encoding="utf-8")
        engine = ocr.EasyOcr(command=[sys.executable, str(script)], work=str(work))
        self.addCleanup(engine.close)
        self.assertEqual(sorted(path.name for path in work.iterdir()), ["giu-lai.txt"])
        engine.read(Picture())
        self.assertEqual(Path(seen.read_text(encoding="utf-8")).parent, work)   # không phải %TEMP%
        self.assertEqual(sorted(path.name for path in work.iterdir()), ["giu-lai.txt"])   # ảnh tạm được xóa sau khi đọc

    def test_the_processors_default_engine_uses_a_tmp_dir_next_to_state(self):
        from zalo_agent.processors.money_images import MoneyImagesProcessor
        from zalo_agent.source import LiveSync
        processor = MoneyImagesProcessor(LiveSync(self.dir), self.dir / "state", self.dir / "reads")
        self.assertEqual(Path(processor.engine.work), self.dir / "tmp")
        self.assertTrue((self.dir / "tmp").is_dir())

    def test_atexit_is_registered_once_however_often_the_child_is_respawned(self):
        script = self.dir / "child.py"
        script.write_text("import sys\nsys.stdin.buffer.readline()\nsys.exit(1)\n", encoding="utf-8")
        engine = ocr.EasyOcr(command=[sys.executable, str(script)], work=str(self.dir))
        self.addCleanup(engine.close)
        with unittest.mock.patch.object(ocr.atexit, "register") as register:
            for _ in range(3):
                with self.assertRaises(ocr.OcrFailure):
                    engine.read(Picture())
        self.assertEqual(register.call_count, 1)

    def test_polygon_corners_are_kept_and_malformed_ones_are_rejected(self):
        good = {"boxes": [{"b": [1, 2, 30, 40], "t": "x", "c": 0.9, "p": [[1, 2], [30, 2], [30, 40], [1, 40]]}]}
        script = self.dir / "child.py"
        for reply, ok in ((good, True), ({"boxes": [{**good["boxes"][0], "p": [[1, 2]]}]}, False), ({"boxes": [{**good["boxes"][0], "p": [[1, 2], [3, "x"], [1, 1], [2, 2]]}]}, False)):
            script.write_text("import sys, json\nfor line in sys.stdin.buffer:\n    sys.stdout.write(json.dumps(@R@) + '\\n'); sys.stdout.flush()\n".replace("@R@", repr(reply)), encoding="utf-8")
            engine = ocr.EasyOcr(command=[sys.executable, str(script)], work=str(self.dir))
            self.addCleanup(engine.close)
            if ok:
                self.assertEqual(engine.read(Picture()), good["boxes"])
            else:
                with self.assertRaises(ocr.OcrFailure):
                    engine.read(Picture())


class BackoffTest(MoneyBase):
    def test_wait_doubles_each_time_up_to_one_hour(self):
        self.assertEqual([money_images.wait_for(60, n) for n in range(1, 9)], [60, 120, 240, 480, 960, 1920, 3600, 3600])

    def test_a_dying_engine_is_retried_less_and_less_often(self):
        engine = Crashy(ocr.OcrFailure("child_died"))
        processor = self.make(engine=engine)
        waits = []
        for _ in range(5):
            processor.step()
            processor.step()
            waits.append(processor.cool_until - self.now)
            self.now = processor.cool_until + 1
        self.assertEqual(waits[:3], [60, 120, 240])

    def test_a_missing_engine_is_asked_less_and_less_often_and_reset_by_a_good_read(self):
        engine = Crashy(ocr.OcrUnavailable("x"))
        processor = self.make(engine=engine)
        waits = []
        for _ in range(4):
            processor.step()
            processor.step()
            waits.append(processor.broken_until - self.now)
            self.now = processor.broken_until + 1
        self.assertEqual(waits, [60, 120, 240, 480])
        engine.error = None
        self.drain(processor)
        self.assertEqual(processor.broken_failures, 0)

    def test_failed_count_drops_when_the_ban_expires(self):
        engine = Crashy(ocr.OcrFailure("child_died"))
        processor = self.make(engine=engine)
        for _ in range(16):
            self.now = max(self.now, processor.cool_until) + 1
            processor.step()
        self.assertEqual(processor.counts()["failed"], 2)
        self.now += money_images.FAILED_BAN + 1
        self.assertEqual(processor.counts()["failed"], 0)


if __name__ == "__main__":
    unittest.main()
