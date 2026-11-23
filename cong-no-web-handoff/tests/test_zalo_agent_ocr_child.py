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
    PHOTO,
    SHA_JXL,
    SHA_LOCAL,
    TRANSFER,
    FakeEngine,
    MoneyBase,
    box,
)
from zalo_agent import __main__ as agent_main  # noqa: E402
from zalo_agent import ocr, reads  # noqa: E402
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


RAPID_STUBS = {
    "numpy.py": ("class _Array:\n    def __getitem__(self, key):\n        return self\ndef asarray(value):\n    return _Array()\n"
                 "def ascontiguousarray(value):\n    return value\n"),
    "PIL/__init__.py": STUBS["PIL/__init__.py"],
    "onnxruntime.py": "class SessionOptions:\n    intra_op_num_threads = 0\n    inter_op_num_threads = 0\n",
    "rapidocr_onnxruntime.py": ("import os\nfrom onnxruntime import SessionOptions\nclass RapidOCR:\n    def __init__(self):\n"
                                "        self.options = SessionOptions()\n        os.write(1, b'RAC native' + bytes([10]))\n        print('rac python')\n"
                                "    def __call__(self, image):\n        os.write(1, b'RAC native 2' + bytes([10]))\n"
                                "        return [[[[1.4, 2.6], [30.2, 2.0], [30.0, 20.0], [1.0, 20.6]], 'Giao dich', '0.7295'],\n"
                                "                [[[5, 5], [9, 5], [9, 9], [5, 9]], 'x', 1.7]], [0.1, 0.2, 0.3]\n"),
    "rapidocr_onnxruntime_missing_model.py": "class RapidOCR:\n    def __init__(self):\n        raise FileNotFoundError('ch_PP-OCRv3_det_infer.onnx')\n",
    "rapidocr_onnxruntime_empty.py": "class RapidOCR:\n    def __call__(self, image):\n        return None, None\n",
}


class RapidChildTest(unittest.TestCase):
    """`ocr_child_rapid.py` thật chạy với thư viện **giả** (không cần onnxruntime/rapidocr/Pillow): cùng giao thức với easyocr, số luồng, model thiếu."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)
        self.stubs = self.dir / "stubs"
        for name, text in RAPID_STUBS.items():
            (self.stubs / name).parent.mkdir(parents=True, exist_ok=True)
            (self.stubs / name).write_text(text, encoding="utf-8")

    def engine(self, library="rapidocr_onnxruntime.py"):
        if library != "rapidocr_onnxruntime.py":
            (self.stubs / "rapidocr_onnxruntime.py").write_text((self.stubs / library).read_text(encoding="utf-8"), encoding="utf-8")
        env = unittest.mock.patch.dict("os.environ", {"PYTHONPATH": str(self.stubs)})
        env.start()
        self.addCleanup(env.stop)
        engine = ocr.RapidOcr(command=[sys.executable, "-X", "utf8", str(ocr.CHILD_RAPID), "2"], timeout=30, work=str(self.dir / "tmp"))
        self.addCleanup(engine.close)
        return engine

    def test_it_is_a_second_registered_engine_with_its_own_child_and_package(self):
        self.assertIs(ocr.ENGINES["rapidocr"], ocr.RapidOcr)
        self.assertIs(ocr.ENGINES["easyocr"], ocr.EasyOcr)
        self.assertEqual((ocr.RapidOcr.name, ocr.RapidOcr.package, ocr.RapidOcr.child_script), ("rapidocr", "rapidocr-onnxruntime", ocr.CHILD_RAPID))
        self.assertEqual((ocr.EasyOcr.name, ocr.EasyOcr.package, ocr.EasyOcr.child_script), ("easyocr", "easyocr", ocr.CHILD))
        self.assertTrue(ocr.CHILD_RAPID.is_file())
        default = ocr.RapidOcr(work=str(self.dir / "tmp"))
        self.assertEqual(default.command[-2:], [str(ocr.CHILD_RAPID), str(ocr.THREADS)])

    def test_version_comes_from_the_rapidocr_package_and_a_missing_package_is_unavailable(self):
        engine = ocr.RapidOcr(work=str(self.dir / "tmp"))
        with unittest.mock.patch.object(ocr.metadata, "version", return_value="1.2.3") as version:
            self.assertEqual(engine.version, f"1.2.3+{ocr.PREPARE}")
        version.assert_called_once_with("rapidocr-onnxruntime")
        with (unittest.mock.patch.object(ocr.metadata, "version", side_effect=ocr.metadata.PackageNotFoundError),
              self.assertRaises(ocr.OcrUnavailable) as caught):
            ocr.RapidOcr(work=str(self.dir / "tmp")).version  # noqa: B018
        self.assertEqual(str(caught.exception), "rapidocr-onnxruntime")

    def test_a_separate_venv_python_runs_the_child_and_is_asked_for_the_version_once(self):
        python = str(self.dir / "venv" / "python.exe")
        with unittest.mock.patch.dict("os.environ", {"ZALO_AGENT_OCR2_PYTHON": python}):
            engine = ocr.RapidOcr(work=str(self.dir / "tmp"))
            self.assertEqual(engine.command, [python, "-X", "utf8", "-I", str(ocr.CHILD_RAPID), str(ocr.THREADS)])
            fake = unittest.mock.Mock(stdout="1.2.3\n")
            with unittest.mock.patch.object(ocr.subprocess, "run", return_value=fake) as run:
                self.assertEqual(engine.version, f"1.2.3+{ocr.PREPARE}")
                self.assertEqual(engine.version, f"1.2.3+{ocr.PREPARE}")   # nhớ: step() hỏi mỗi giây
            self.assertEqual(run.call_count, 1)
            self.assertEqual(run.call_args.args[0][0], python)
            with unittest.mock.patch.object(ocr.subprocess, "run", side_effect=FileNotFoundError), self.assertRaises(ocr.OcrUnavailable):
                ocr.RapidOcr(work=str(self.dir / "tmp")).version  # noqa: B018

    def test_boxes_have_plain_int_coordinates_and_scores_clamped_to_0_1_and_stdout_noise_never_breaks_the_protocol(self):
        engine = self.engine()
        for _ in range(2):   # tiếng ồn ở stdout (kể cả ghi thẳng fd 1) xảy ra ở cả hai lượt
            boxes = engine.read(Picture())
            self.assertEqual(boxes, [{"b": [1, 2, 30, 21], "t": "Giao dich", "c": 0.73, "p": [[1, 3], [30, 2], [30, 20], [1, 21]]},
                                     {"b": [5, 5, 9, 9], "t": "x", "c": 1.0, "p": [[5, 5], [9, 5], [9, 9], [5, 9]]}])
        self.assertTrue(all(type(value) is int for box in boxes for value in box["b"]))

    def test_the_thread_count_is_applied_to_onnxruntime_session_options(self):
        env = unittest.mock.patch.dict("os.environ", {"PYTHONPATH": str(self.stubs)})
        env.start()
        self.addCleanup(env.stop)
        (self.stubs / "rapidocr_onnxruntime.py").write_text(
            "from onnxruntime import SessionOptions\nclass RapidOCR:\n    def __init__(self):\n        self.o = SessionOptions()\n"
            "    def __call__(self, image):\n        return [[[[0, 0], [4, 0], [4, 4], [0, 4]], 'n=%d/%d' % (self.o.intra_op_num_threads, self.o.inter_op_num_threads), 0.9]], []\n",
            encoding="utf-8")
        engine = ocr.RapidOcr(command=[sys.executable, "-X", "utf8", str(ocr.CHILD_RAPID), "3"], timeout=30, work=str(self.dir / "tmp"))
        self.addCleanup(engine.close)
        self.assertEqual(engine.read(Picture())[0]["t"], "n=3/1")

    def test_no_result_is_an_empty_list_not_a_failure(self):
        self.assertEqual(self.engine("rapidocr_onnxruntime_empty.py").read(Picture()), [])

    def test_missing_model_is_reported_not_downloaded(self):
        with self.assertRaises(ocr.OcrUnavailable):
            self.engine("rapidocr_onnxruntime_missing_model.py").read(Picture())

    def test_missing_library_is_unavailable(self):
        engine = self.engine()
        (self.stubs / "rapidocr_onnxruntime.py").unlink()
        with self.assertRaises(ocr.OcrUnavailable):
            engine.read(Picture())

    def test_malformed_request_line_gets_bad_request_and_the_child_keeps_serving(self):
        engine = self.engine()
        child = engine.spawn()
        child.stdin.write(b"khong phai json\n")
        child.stdin.flush()
        self.assertEqual(json.loads(child.stdout.readline()), {"error": "bad_request"})
        self.assertEqual(engine.read(Picture())[0]["t"], "Giao dich")

    def test_the_agent_process_never_imports_onnxruntime_or_rapidocr(self):
        import subprocess
        code = (f"import sys; sys.path.insert(0, {str(ROOT / 'tools')!r}); import zalo_agent.__main__, zalo_agent.processors.money_images; "
                "print('onnxruntime' in sys.modules or 'rapidocr_onnxruntime' in sys.modules or 'cv2' in sys.modules)")
        done = subprocess.run([sys.executable, "-I", "-c", code], capture_output=True, check=True)
        self.assertEqual(done.stdout.decode().strip(), "False")


class SecondEngine(FakeEngine):
    """Engine đọc lần hai giả: ô chữ theo byte ảnh như `FakeEngine`, tên riêng."""
    name = "second"


class SecondReaderTest(MoneyBase):
    """Lần đọc hai (RapidOCR): ảnh có số mà lần đọc chính không chắc, hai engine cùng một số thì chắc; còn lại như cũ."""
    UNSURE = (*TRANSFER[:1], {"b": [0, 100, 600, 200], "t": "1.500.000 đ", "c": 0.4}, {"b": [0, 300, 300, 330], "t": "Vietcombank", "c": 0.95})

    def setUp(self):
        super().setUp()
        self.engine.script[JPEG_LOCAL] = list(self.UNSURE)
        self.second = SecondEngine(version="9.9+t", script={JPEG_LOCAL: TRANSFER})

    def member(self, processor):
        return processor.state()["members"][SHA_LOCAL]

    def test_corroborates_needs_the_same_number_one_leader_and_confidence(self):
        read = ocr.analyse(list(self.UNSURE))
        self.assertEqual(ocr.verdict(read), "unsure")
        same = {"amount_vnd": 1_500_000, "unique": True, "confidence": 0.8}
        self.assertEqual(ocr.verdict({**read, "second": same}), "ocr")
        for other in ({**same, "amount_vnd": 1_500_001}, {**same, "unique": False}, {**same, "confidence": 0.59}, {**same, "amount_vnd": None}):
            self.assertEqual(ocr.verdict({**read, "second": other}), "unsure", other)
        weak = ocr.analyse([box(0, 100, 600, 200, "1.500.000 đ", 0.4)])   # thiếu từ khóa và dấu hiệu đã xong: lần hai không thay được
        self.assertEqual(ocr.verdict({**weak, "second": same}), "none" if not weak["is_money"] else "unsure")

    def test_two_engines_agreeing_make_an_unsure_image_ocr_without_asking_anyone(self):
        processor = self.make(second=self.second)
        result = self.drain(processor)
        self.assertEqual((self.member(processor)["by"], self.member(processor)["verdict"]), ("ocr", "ocr"))
        self.assertEqual((result["counts"]["review"], result["counts"]["asking"]), (0, 0))
        self.assertEqual(len(self.second.calls), 1)
        self.assertIsNotNone(reads.load(self.root / "reads", SHA_LOCAL, "second", "9.9+t"))   # kho riêng của engine hai, chữ chỉ nằm ở máy
        self.assertNotIn("second", self.stored(SHA_LOCAL))                                    # lần đọc chính không bị ghi thêm gì

    def test_a_different_number_a_weak_read_or_no_number_stays_for_a_human(self):
        for script in ([*TRANSFER[:1], box(40, 300, 700, 380, "1.500.001 VND"), *TRANSFER[2:5]], [box(40, 300, 700, 380, "1.500.000 VND", 0.3), *TRANSFER[:1]], PHOTO):
            with self.subTest(script=script[:2]):
                self.second.script[JPEG_LOCAL] = script
                processor = self.make(second=self.second)
                self.drain(processor)
                self.assertEqual(self.member(processor)["by"], "human")
                self.assertEqual(processor.counts()["review"], 1)
                shutil_reset(self)

    def test_the_second_engine_is_only_asked_when_the_first_is_unsure_with_a_number(self):
        self.engine.script[JPEG_LOCAL] = TRANSFER   # lần đọc chính đã chắc
        processor = self.make(second=self.second)
        self.drain(processor)
        self.assertEqual((self.second.calls, self.member(processor)["by"]), ([], "ocr"))

    def test_an_unavailable_or_crashing_second_engine_changes_nothing(self):
        class Down(SecondEngine):
            def read(self, image):
                raise ocr.OcrUnavailable("rapidocr")

        processor = self.make(second=Down(script={JPEG_LOCAL: TRANSFER}))
        result = self.drain(processor)
        self.assertEqual(self.member(processor)["by"], "human")
        self.assertEqual((result["counts"]["failed"], result["error"]), (0, None))   # lỗi của engine hai không phải lỗi của ảnh hay của engine chính

    def test_reread_with_the_second_engine_then_a_restart_promotes_the_images_already_waiting_for_a_human(self):
        first = self.make()
        self.drain(first)
        self.assertEqual(self.member(first)["by"], "human")
        first.reread(self.second, 0)   # `zalo_agent reread --engine rapidocr`: chỉ ghi kho
        restarted = self.make(second=self.second)
        self.assertEqual((self.member(restarted)["by"], self.member(restarted)["verdict"]), ("ocr", "ocr"))

    def test_the_option_exists_defaults_off_and_offers_only_the_second_engine(self):
        import contextlib
        import io
        out = io.StringIO()
        with contextlib.redirect_stdout(out), self.assertRaises(SystemExit):
            agent_main.main(["run", "--help"])
        text = " ".join(out.getvalue().split())
        self.assertIn("--money-second {off,rapidocr}", text)
        self.assertIn("MẶC ĐỊNH off", text)


def shutil_reset(case):
    """Mỗi ca con dựng lại từ kho trống: xóa kho kết quả và con trỏ của ca trước."""
    import shutil
    shutil.rmtree(case.root / "reads", ignore_errors=True)
    shutil.rmtree(case.root / "state", ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
