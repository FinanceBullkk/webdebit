#!/usr/bin/env python3
"""Kiểm phân bổ thu bằng chuỗi lệnh ngẫu nhiên trên PostgreSQL dùng một lần (specs/v7-fifo-ngau-nhien.md).

Hypothesis sinh chuỗi lệnh ghi tiền: dán chuyến, sửa giá, đổi ngày chuyến, xóa chuyến, điều chỉnh tháng, xóa điều
chỉnh, ghi thu, sửa phiếu, hủy phiếu, khóa/mở tháng, gửi lặp, trùng khóa lệnh, phiên bản cũ. Mỗi lệnh chạy qua đúng
hàm `sokhach.*` của API; sau mỗi lệnh cả sổ trong DB được so với mô hình `v7_fifo_model.py` (`v7_fifo_session.py`).
Lệch thì Hypothesis rút gọn về chuỗi ngắn nhất và in từng bước. Cần Docker và Hypothesis (requirements-dev.txt):

    uv run --python 3.13 --with-requirements requirements-dev.txt python cong-no-web-handoff/tools/test_pg_v7_fifo_ngau_nhien.py
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
import time
from datetime import date
from pathlib import Path

import hypothesis
from hypothesis import HealthCheck, Phase, given, note, seed, settings
from hypothesis import strategies as st
from hypothesis.errors import HypothesisException
from pg_v7_harness import (
    FUNCTIONS,
    IMAGE,
    SCHEMA,
    HarnessError,
    Pg,
    disposable_database,
    require,
)
from v7_fifo_session import METHODS, MONTHS, OPEN_MONTHS, Session

DEFAULT_SEED = 20261118  # CI cố định seed để PR không đỏ vì một chuỗi mới; tìm rộng hơn thì --seed random
# Lỗi cố ý, chỉ sửa trong container dùng một lần, để chứng minh harness bắt được lỗi: (hàm, đoạn gốc, đoạn thay).
MUTANTS = {
    "ngay-phieu": ("reallocate", 'ORDER BY date,pid COLLATE "C"', 'ORDER BY pid COLLATE "C"'),
    "thang-am": ("reallocate", "IF v_left[i] > 0 THEN", "IF v_left[i] IS NOT NULL THEN"),
    "huy-phan-bo-lai": ("void_receipt", "PERFORM sokhach._check_allocations(customer_id);",
                        "PERFORM sokhach.reallocate(customer_id,idempotency_key);"),
}
# Trọng số lệnh: tên lặp lại thì được chọn nhiều hơn.
OPS = ("paste",) * 3 + ("receipt",) * 3 + ("price", "adjust", "edit_receipt") * 2 + (
    "move", "delete_trip", "delete_adjustment", "void", "lock", "replay", "conflict", "stale")


def days(first: str, last: str):
    return st.dates(date.fromisoformat(first), date.fromisoformat(last)).map(date.isoformat)


TRIP_DAYS = days("2026-01-01", "2026-06-30")
RECEIPT_DAYS = days("2026-01-01", "2026-07-31")  # tháng 7 chỉ có tiền về, không có phát sinh
UNITS = st.none() | st.integers(0, 1000)
FEES = st.none() | st.integers(-300, 500).filter(bool)  # phụ phí 0 ngoài phạm vi (spec)
ROWS = st.lists(st.one_of(
    st.fixed_dictionaries({"day": TRIP_DAYS, "unit": UNITS, "fee": FEES}),  # chuyến có container
    st.fixed_dictionaries({"day": st.none() | TRIP_DAYS, "fee": st.integers(-300, 500).filter(bool)}),  # chỉ phụ phí
), min_size=1, max_size=3)


def run_op(session: Session, op: str, data) -> str:
    """Chạy một lệnh; lệnh cần thứ chưa có (chuyến, phiếu, điều chỉnh, lệnh cũ) thì đổi sang lệnh tạo ra thứ đó."""
    book = session.book
    if op in ("price", "move", "delete_trip") and not book.trips:
        op = "paste"
    elif op == "delete_adjustment" and not book.adjustments:
        op = "adjust"
    elif op in ("edit_receipt", "void") and not book.receipts:
        op = "receipt"
    elif op in ("replay", "conflict") and not session.history:
        op = "lock"

    def draw(strategy, label):
        return data.draw(strategy, label=label)

    def pick(items, label):
        return draw(st.sampled_from(sorted(items)), label)

    match op:
        case "paste":
            return session.paste(draw(st.sampled_from(MONTHS), "tháng dán"), draw(ROWS, "chuyến"))
        case "price":
            return session.price(pick(book.trips, "chuyến"), draw(UNITS, "đơn giá"), draw(FEES, "phụ phí"))
        case "move":
            return session.move(pick(book.trips, "chuyến"), draw(TRIP_DAYS, "ngày mới"))
        case "delete_trip":
            return session.delete_trip(pick(book.trips, "chuyến"))
        case "adjust":
            return session.adjust(draw(st.sampled_from(MONTHS), "tháng"), draw(st.integers(-800, 800).filter(bool), "số"))
        case "delete_adjustment":
            return session.delete_adjustment(pick(book.adjustments, "điều chỉnh"))
        case "receipt":
            return session.receipt(draw(RECEIPT_DAYS, "ngày phiếu"), draw(st.integers(1, 2500), "tiền"),
                                   draw(st.sampled_from(METHODS), "hình thức"))
        case "edit_receipt":
            pid = pick(book.receipts, "phiếu")
            if draw(st.booleans(), "đổi ngày"):
                return session.edit_receipt(pid, draw(RECEIPT_DAYS, "ngày mới"), None)
            return session.edit_receipt(pid, None, draw(st.sampled_from(METHODS), "hình thức mới"))
        case "void":
            return session.void(pick(book.receipts, "phiếu"))
        case "lock":
            return session.lock(draw(st.sampled_from(OPEN_MONTHS), "tháng"), draw(st.booleans(), "khóa"))
        case "replay":
            return session.replay(draw(st.integers(0, len(session.history) - 1), "lệnh cũ"))
        case "conflict":
            return session.conflict(draw(st.integers(0, len(session.history) - 1), "lệnh cũ"))
        case _:
            return session.stale()


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def apply_mutant(pg: Pg, name: str) -> None:
    function, old, new = MUTANTS[name]
    source = pg.value(f"SELECT pg_get_functiondef('sokhach.{function}'::regproc)")
    require(source.count(old) == 1, f"mutant {name}: không thấy đúng một chỗ {old!r} trong sokhach.{function}")
    pg.sql(source.replace(old, new))


def main() -> int:
    for stream in (sys.stdout, sys.stderr):  # Windows chuyển hướng ra file thì mặc định cp1252, không in được tiếng Việt
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure:
            reconfigure(encoding="utf-8", errors="backslashreplace")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--examples", type=int, default=100, help="số chuỗi lệnh sinh mới (mặc định 100)")
    ap.add_argument("--steps", type=int, default=40, help="số lệnh tối đa mỗi chuỗi (mặc định 40)")
    ap.add_argument("--seed", default=str(DEFAULT_SEED), help="số nguyên, hoặc 'random' để tìm chuỗi mới")
    ap.add_argument("--mutant", choices=sorted(MUTANTS),
                    help="cố ý làm sai một hàm SQL trong container; lệnh đạt (mã 0) khi harness bắt được lỗi")
    ap.add_argument("--report", type=Path, help="ghi báo cáo JSON")
    args = ap.parse_args()
    seed_value = random.randrange(2**32) if args.seed == "random" else int(args.seed)
    stats = {"sequences": 0, "commands": 0, "rejected": 0}
    report = {"spec": "specs/v7-fifo-ngau-nhien.md", "image": IMAGE, "schema_sha256": sha(SCHEMA),
              "functions_sha256": sha(FUNCTIONS), "sql_hash_normalization": "CRLF to LF",
              "hypothesis": {"version": hypothesis.__version__, "seed": seed_value,
                             "examples": args.examples, "max_steps": args.steps},
              "mutant": args.mutant, "stats": stats, "result": "fail", "cleanup": "not_started"}
    started = time.monotonic()
    try:
        with disposable_database(report) as pg:
            today = pg.value("SELECT date_trunc('month',clock_timestamp() AT TIME ZONE 'Asia/Ho_Chi_Minh')::date")
            if args.mutant:
                apply_mutant(pg, args.mutant)

            @seed(seed_value)
            @settings(max_examples=args.examples, deadline=None, database=None, print_blob=False,
                      report_multiple_bugs=False, phases=(Phase.explicit, Phase.generate, Phase.shrink),
                      suppress_health_check=list(HealthCheck))
            @given(st.data())
            def sequences(data) -> None:
                openings = data.draw(st.dictionaries(st.sampled_from(MONTHS), st.integers(-300, 1500), max_size=3),
                                     label="opening")
                session = Session(pg, openings, today)
                stats["sequences"] += 1
                session.verify("mở sổ")
                step = 0
                # Mỗi bước đi tiếp với khả năng 15/16 (trung bình ~16 lệnh); rút gọn đưa số này về 0 là cắt chuỗi.
                while step < args.steps and (step == 0 or data.draw(st.integers(0, 15), label="còn tiếp") != 0):
                    step += 1
                    text = run_op(session, data.draw(st.sampled_from(OPS), label=f"lệnh {step}"), data)
                    note(f"{step}. {text}")
                    stats["commands"] += 1
                    session.verify(text)
                stats["rejected"] += session.rejected

            sequences()
        report["result"] = "pass"
    except (HarnessError, HypothesisException, AssertionError, KeyError, TypeError, OSError, ValueError) as exc:
        report["error"] = f"{type(exc).__name__}: {str(exc)[-4000:]}"
        # Hypothesis gắn chuỗi đã rút gọn (giá trị rút ra và từng bước `note`) vào __notes__ của lỗi, không in riêng.
        report["falsifying"] = list(getattr(exc, "__notes__", []))
        print("\n".join(["Chuỗi lệnh ngắn nhất còn gây lệch:", *report["falsifying"]]))
    report["seconds"] = round(time.monotonic() - started, 1)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    # Với --mutant, đạt nghĩa là harness đã đỏ (bắt được lỗi cố ý); đọc "error" để chắc là lệch sổ, không phải lỗi hạ tầng.
    passed = (report["result"] == "fail" and "error" in report) if args.mutant else report["result"] == "pass"
    return int(not passed or report["cleanup"] != "verified_and_removed")


if __name__ == "__main__":
    sys.exit(main())
