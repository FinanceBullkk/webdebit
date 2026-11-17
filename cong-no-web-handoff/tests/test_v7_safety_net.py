"""Lưới an toàn (LUOI-AN-TOAN-01): so với mốc lượt trước, câu báo, mục chờ và chấp nhận. Không cần DB: kết quả SQL giả cùng
hình dạng với `sokhach.get_safety_net` (harness PostgreSQL thật ở tools/test_pg_v7_luoi_an_toan.py)."""

import copy
import datetime as dt
import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import v7_safety_net as net  # noqa: E402
from v7_api_validate import ApiError  # noqa: E402  (v7_safety_net đã thêm web/ vào sys.path)

VN = ZoneInfo("Asia/Ho_Chi_Minh")
T0 = dt.datetime(2026, 11, 18, 10, 2, tzinfo=VN)
STEP = dt.timedelta(minutes=15)
BLOCKS = {"0": [999, "a0"], "1": [1000, "a1"], "2": [500, "a2"]}


def book(version, **parts):
    return {"version": version, "parts": {"receipt": "r1", "receipt_line": "l1", **parts}}


def result(*, books=None, store=None, settled=2500, check=None, allocations=(), codes=(), customers=(), archived=(),
           ledger=None):
    return {"books": len(books or {}), "allocations": list(allocations),
            "totals": {"codes": list(codes), "customers": list(customers), "archived": list(archived)},
            "ledger": ledger if ledger is not None else {"slice": 0, "slices": 8, "checked": 3, "customers": []},
            "fingerprints": books if books is not None else {"7": book(3), "9": book(1)},
            "events": {"settled": settled, "store": store if store is not None else BLOCKS, "check": check}}


class FakeDb:
    """Trả lần lượt các kết quả cho get_safety_net; ghi lại lệnh gọi."""

    def __init__(self, *results, missing=False):
        self.results, self.calls, self.missing = list(results), [], missing

    def run(self, function, payload, actor, *, read_only=False):
        self.calls.append((function, payload, actor, read_only))
        if function == "has_safety_net":
            return {"ok": not self.missing}
        if self.missing or not self.results:
            raise ApiError(503, "DB_UNAVAILABLE", "Sổ tạm thời không truy cập được.")
        return copy.deepcopy(self.results.pop(0))


class Base(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.folder = Path(temp.name)

    def run_net(self, *results, at=T0, **kwargs):
        db = FakeDb(*results)
        with redirect_stderr(io.StringIO()):
            report = net.run(at, db=db, state_dir=kwargs.pop("state_dir", self.folder), **kwargs)
        return report, db

    def state(self):
        return json.loads((self.folder / net.STATE_FILE).read_text(encoding="utf-8"))


class BaselineTests(Base):
    def test_first_run_takes_a_baseline_read_only_and_reports_nothing(self):
        report, db = self.run_net(result())
        self.assertEqual(report["problems"], [])
        self.assertEqual(report["summary"]["baseline"], "lần đầu, lấy mốc")
        function, options, actor, read_only = db.calls[0]
        self.assertEqual((function, actor, read_only), ("get_safety_net", "may-canh", True))
        self.assertEqual(options, {"event_upto": None, "ledger_slice": net.slot(T0), "ledger_slices": 8, "settle_seconds": 600})
        state = self.state()
        self.assertEqual((state["format"], state["events"], state["pending"]), (1, {"upto": 2500, "blocks": BLOCKS}, []))
        self.assertEqual(state["books"], result()["fingerprints"])
        if os.name != "nt":
            self.assertEqual((self.folder / net.STATE_FILE).stat().st_mode & 0o777, 0o600)

    def test_next_run_sends_the_kept_history_mark_and_commands_are_quiet(self):
        self.run_net(result())
        after_command = result(books={"7": book(4, receipt_line="l2"), "9": book(1)},
                               store={**BLOCKS, "2": [1000, "a2b"], "3": [10, "a3"]}, settled=3009, check=BLOCKS)
        report, db = self.run_net(after_command, at=T0 + STEP)
        self.assertEqual(report["problems"], [])
        self.assertEqual(db.calls[0][1]["event_upto"], 2500)
        self.assertEqual(self.state()["events"]["upto"], 3009)

    def test_new_book_and_version_bump_without_data_change_are_quiet(self):
        self.run_net(result())
        report, _ = self.run_net(result(books={"7": book(5), "9": book(1), "12": book(1)}, check=BLOCKS), at=T0 + STEP)
        self.assertEqual(report["problems"], [])


class BookChangeTests(Base):
    def test_change_without_command_stays_reported_until_accepted(self):
        self.run_net(result())
        changed = result(books={"7": book(3, receipt_line="l-sua-tay", month_state="m2"), "9": book(1)}, check=BLOCKS)
        line = ("Sổ 7: khóa tháng, dòng chia phiếu thu đổi mà không qua lệnh nào, thấy lúc 10:17 ngày 18/11. "
                "Cần xem rồi chấp nhận.")
        self.assertEqual(self.run_net(changed, at=T0 + STEP)[0]["problems"], [line])
        # Lệnh ghi sau đó tăng version: vẫn báo, vì việc sửa tay đã xảy ra.
        later = result(books={"7": book(4, receipt_line="l3", month_state="m2"), "9": book(1)}, check=BLOCKS)
        self.assertEqual(self.run_net(later, at=T0 + 2 * STEP)[0]["problems"], [line])
        accepted, _ = self.run_net(later, at=T0 + 3 * STEP, accept=True)
        self.assertEqual((accepted["problems"], accepted["accepted"]), ([], [line]))
        self.assertEqual(self.run_net(later, at=T0 + 4 * STEP)[0]["problems"], [])

    def test_second_change_on_the_same_book_keeps_the_first_time(self):
        self.run_net(result())
        self.run_net(result(books={"7": book(3, receipt="r2"), "9": book(1)}, check=BLOCKS), at=T0 + STEP)
        report, _ = self.run_net(result(books={"7": book(3, receipt="r2", trip="t9"), "9": book(1)}, check=BLOCKS),
                                 at=T0 + 2 * STEP)
        self.assertEqual(report["problems"], ["Sổ 7: phiếu thu, chuyến đổi mà không qua lệnh nào, thấy lúc 10:17 ngày 18/11. "
                                              "Cần xem rồi chấp nhận."])

    def test_version_going_back_and_lost_book(self):
        self.run_net(result())
        report, _ = self.run_net(result(books={"7": book(2)}, check=BLOCKS), at=T0 + STEP)
        self.assertEqual(report["problems"], [
            "Số lần ghi của 1 sổ bị lùi (sổ 7): DB có thể vừa phục hồi từ bản cũ, thấy lúc 10:17 ngày 18/11. Cần xem rồi chấp nhận.",
            "1 sổ biến mất (sổ 9), thấy lúc 10:17 ngày 18/11. Cần xem rồi chấp nhận."])

    def test_many_changed_books_are_one_line_with_five_codes(self):
        before = {str(n): book(1) for n in range(1, 9)}
        self.run_net(result(books=before))
        report, _ = self.run_net(result(books={key: book(1, trip="x") for key in before}, check=BLOCKS), at=T0 + STEP)
        self.assertEqual(report["problems"], ["Dữ liệu tiền đổi mà không qua lệnh nào ở 8 sổ (sổ 1, 2, 3, 4, 5…), thấy từ 10:17 ngày 18/11. "
                                              "Cần xem rồi chấp nhận."])


class HistoryTests(Base):
    def test_old_history_rows_changed_or_removed_are_reported(self):
        self.run_net(result())
        tampered = {**BLOCKS, "1": [999, "khac"]}
        report, _ = self.run_net(result(store=tampered, check=tampered), at=T0 + STEP)
        self.assertEqual(report["problems"], ["Lịch sử có dòng cũ bị sửa hoặc xóa (id 1000–1999), thấy lúc 10:17 ngày 18/11. "
                                              "Cần xem rồi chấp nhận."])

    def test_no_kept_mark_or_nothing_settled_yet_compares_nothing(self):
        self.run_net(result(settled=None, store={}))
        report, db = self.run_net(result(store=BLOCKS, check=None), at=T0 + STEP)
        self.assertEqual((report["problems"], db.calls[0][1]["event_upto"]), ([], None))


class StatelessTests(Base):
    def test_allocation_and_total_problems_name_books_by_code_only(self):
        found = result(allocations=[{"customer_id": 12, "code": "ALLOCATION_INVARIANT"},
                                    {"customer_id": 4, "code": "ALLOCATION_INVARIANT"},
                                    {"customer_id": 4, "code": "ADVANCE_MONTH_INVARIANT"}],
                       codes=["RECEIVABLE_TOTAL", "DEBT_LIST", "ARCHIVED_BALANCE"], customers=[12], archived=[30])
        report, _ = self.run_net(found)
        self.assertEqual(report["problems"], [
            "Tiền ứng trước nằm sai tháng ở 1 sổ (sổ 4).",
            "Phiếu thu chia không khớp tiền phiếu ở 2 sổ (sổ 4, 12).",
            "Tổng quan không khớp tổng các sổ: tổng Còn phải thu, danh sách khách nợ (sổ 12).",
            "1 sổ lưu trữ còn số dư nên Tổng quan không tính (sổ 30)."])
        # Đúng lại thì tự hết báo, không cần chấp nhận.
        self.assertEqual(self.run_net(result(check=BLOCKS), at=T0 + STEP)[0]["problems"], [])

    def test_ledger_result_stays_until_its_slice_is_checked_again(self):
        line = ["Tổng trong sổ khác tổng Tổng quan dùng ở 1 sổ (sổ 11)."]
        first = net.slot(T0)
        report, _ = self.run_net(result(ledger={"slice": first, "slices": 8, "checked": 30, "customers": [11]}))
        self.assertEqual(report["problems"], line)
        report, _ = self.run_net(result(ledger={"slice": (first + 1) % 8, "slices": 8, "checked": 30, "customers": []}, check=BLOCKS),
                                 at=T0 + STEP)
        self.assertEqual(report["problems"], line)
        report, _ = self.run_net(result(ledger={"slice": first, "slices": 8, "checked": 30, "customers": []}, check=BLOCKS),
                                 at=T0 + 8 * STEP)
        self.assertEqual(report["problems"], [])

    def test_full_run_checks_every_slice_in_its_own_statement(self):
        slices = [result(ledger={"slice": n, "slices": 8, "checked": 30, "customers": [n * 8 + 3] if n == 5 else []})
                  for n in range(8)]
        current = net.slot(T0)
        ordered = [slices[current]] + [slices[n] for n in range(8) if n != current]
        report, db = self.run_net(*ordered, full=True)
        self.assertEqual(sorted(call[1]["ledger_slice"] for call in db.calls), list(range(8)))
        self.assertEqual(report["problems"], ["Tổng trong sổ khác tổng Tổng quan dùng ở 1 sổ (sổ 43)."])

    def test_without_a_state_directory_checks_three_and_four_rest(self):
        self.run_net(result(), state_dir=None)
        report, _ = self.run_net(result(books={"7": book(3, receipt="sua")}, allocations=[{"customer_id": 7, "code": "X"}]),
                                 state_dir=None, at=T0 + STEP)
        self.assertEqual(report["problems"], ["Phiếu thu lỗi kiểm (X) ở 1 sổ (sổ 7)."])
        self.assertEqual((report["summary"]["baseline"], list(self.folder.iterdir())), ("không giữ mốc", []))


class OperationTests(Base):
    def test_database_not_upgraded_yet_is_quiet_but_other_errors_are_not(self):
        db = FakeDb(missing=True)
        with redirect_stderr(io.StringIO()):
            self.assertEqual(net.check(T0, db=db, state_dir=self.folder), [])
        self.assertEqual([call[0] for call in db.calls], ["get_safety_net", "has_safety_net"])
        with self.assertRaises(ApiError), redirect_stderr(io.StringIO()):
            net.check(T0, db=FakeDb(), state_dir=self.folder)

    def test_broken_mark_starts_over_and_says_so_once_until_accepted(self):
        (self.folder / net.STATE_FILE).write_text("{hỏng", encoding="utf-8")
        report, _ = self.run_net(result())
        self.assertEqual(report["problems"], ["Mốc lưới an toàn hỏng, đã lấy mốc mới lúc 10:02 ngày 18/11: thay đổi trước đó không "
                                              "so được. Cần xem rồi chấp nhận."])
        self.assertEqual(report["summary"]["baseline"], "mốc hỏng, lấy mốc mới")
        self.assertEqual(self.state()["format"], 1)

    def test_dry_run_writes_nothing(self):
        self.run_net(result(), save_state=False)
        self.assertFalse((self.folder / net.STATE_FILE).exists())

    def test_check_reads_the_systemd_state_directory_and_logs_counts_only(self):
        printed = io.StringIO()
        with patch.dict(os.environ, {"STATE_DIRECTORY": f"{self.folder}{os.pathsep}/khac"}), redirect_stderr(printed):
            self.assertEqual(net.check(T0, db=FakeDb(result())), [])
        self.assertTrue((self.folder / net.STATE_FILE).exists())
        self.assertTrue(printed.getvalue().startswith("lưới an toàn: {"))

    def test_main_prints_the_report_and_accept_needs_a_folder(self):
        printed = io.StringIO()
        with patch.object(net, "connect", return_value=FakeDb(result(allocations=[{"customer_id": 2, "code": "X"}]))), \
                redirect_stdout(printed), redirect_stderr(io.StringIO()):
            code = net.main(["--state-dir", str(self.folder), "--dry-run"])
        self.assertEqual((code, json.loads(printed.getvalue())["ok"]), (1, False))
        self.assertFalse((self.folder / net.STATE_FILE).exists())
        with patch.dict(os.environ, {"STATE_DIRECTORY": ""}), redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            net.main(["--accept"])
        # Chạy tay bằng root sẽ để lại file mốc của root mà máy canh (v7app) không ghi được: chặn trước khi đụng DB.
        with patch.object(net.os, "geteuid", create=True, return_value=0), patch.object(net, "connect") as connect, \
                redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            net.main(["--state-dir", str(self.folder), "--dry-run"])
        connect.assert_not_called()


if __name__ == "__main__":
    unittest.main()
