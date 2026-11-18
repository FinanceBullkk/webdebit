"""Một sổ khách giả trên PostgreSQL dùng một lần, chạy song song với mô hình tham chiếu `v7_fifo_model.py`.

Mỗi lệnh: hỏi mô hình kết quả dự đoán, gọi đúng hàm `sokhach.*` theo cách API gọi (một transaction có
`sokhach.actor`), so kết quả hoặc mã lỗi, áp vào mô hình; `verify` so cả sổ trong DB với mô hình. Lệch nào cũng
ném `HarnessError`. Chỉ dùng trong `test_pg_v7_fifo_ngau_nhien.py` (specs/v7-fifo-ngau-nhien.md).
"""

from __future__ import annotations

import json

from pg_v7_harness import Pg, actor_sql, lit, new_book, require
from v7_fifo_model import ADVANCE, Book, Trip, canonical, month_of

MONTHS = [f"2026-{n:02d}-01" for n in range(1, 7)]
OPEN_MONTHS = [*MONTHS, "2026-07-01"]  # tháng 7 chỉ có ngày phiếu, không có phát sinh
METHODS = ("THU TIỀN", "CẤN TRỪ", "ỨNG TRƯỚC", "KHÁC")

# Phiếu và dòng phân bổ đọc thẳng từ bảng; phần còn lại là đúng `get_ledger` mà trang sổ khách đọc.
STATE = """SELECT jsonb_build_object('receipts',(SELECT coalesce(jsonb_agg(jsonb_build_object(
 'pid',r.pid,'day',r.date,'amount',r.amount_vnd,'method',r.method,'voided',r.voided_on IS NOT NULL,
 'lines',(SELECT coalesce(jsonb_agg(jsonb_build_array(l.debt_month,l.kind,l.amount_vnd)
   ORDER BY l.debt_month,CASE l.kind WHEN 'debt' THEN 0 ELSE 1 END,l.id),'[]'::jsonb)
   FROM sokhach.receipt_line l WHERE l.receipt_id=r.id AND l.superseded_by_event IS NULL))
 ORDER BY r.pid),'[]'::jsonb) FROM sokhach.receipt r WHERE r.customer_id={c}),
 'ledger',sokhach.get_ledger({c}))"""


def dmy(day: str | None) -> str | None:
    return None if day is None else f"{day[8:10]}/{day[5:7]}/{day[:4]}"


def opt(value) -> int | None:
    return None if value is None else int(value)


def opt_text(value: int | None) -> str | None:
    return None if value is None else str(value)


class Session:
    def __init__(self, pg: Pg, openings: dict[str, int], today_month: str):
        self.pg = pg
        self.customer = new_book(pg, *sorted(openings.items()))
        pg.sql("INSERT INTO sokhach.month_state(customer_id,month,locked,changed_by) VALUES "
               + ",".join(f"({self.customer},{lit(month)},false,'harness')" for month in OPEN_MONTHS))
        self.book = Book(openings, OPEN_MONTHS, today_month)
        self.history: list[tuple[str, str, dict]] = []  # (khóa, câu lệnh, kết quả) của lệnh được nhận
        self.serial = 0  # khóa lệnh, container và ghi chú đều duy nhất trong một sổ
        self.rejected = 0

    def _next(self) -> int:
        self.serial += 1
        return self.serial

    def command(self, fn: str, args: list, expected: str | None, *, key: str | None = None,
                version: int | None = None) -> dict | None:
        key = key or f"fifo-{self._next()}"
        values = [str(self.customer), str(self.book.version if version is None else version), lit(key)]
        values += ["NULL" if value is None else lit(value) for value in args]
        sql = actor_sql(f"SELECT sokhach.{fn}({','.join(values)})")
        if expected is None:
            result = json.loads(self.pg.value(sql))  # lỗi SQL ngoài dự đoán: HarnessError kèm mã lỗi
            self.history.append((key, sql, result))
            return result
        self.rejected += 1
        p = self.pg.sql(sql, check=False)
        require(p.returncode != 0, f"{fn}: chờ bị từ chối {expected} nhưng được nhận: {p.stdout.strip()[:300]}")
        require(expected in p.stderr, f"{fn}: chờ {expected}, nhận lỗi khác: {p.stderr.strip()[-400:]}")
        return None

    @staticmethod
    def _reallocated(fn: str, result: dict, changed: list[str]) -> None:
        got = [item["pid"] for item in result["reallocated"]]
        require(got == changed, f"{fn}: 'reallocated' {got}, mô hình {changed}")

    @staticmethod
    def _outcome(expected: str | None) -> str:
        return f"bị từ chối {expected}" if expected else "được nhận"

    # ---- lệnh ----
    def paste(self, month: str, rows: list[dict]) -> str:
        payload = []
        for row in rows:
            if "unit" in row:  # chuyến có container; container luôn mới nên không vào CHỜ KIỂM
                payload.append({"container": f"FAKE-T{self._next():04d}", "carrier": "FAKE", "date": dmy(row["day"]),
                                "from": "FAKE-A", "to": "FAKE-B", "note": "", "src": "FAKE",
                                "unitPriceVnd": opt_text(row["unit"]), "otherFeeVnd": opt_text(row["fee"])})
            else:  # dòng chỉ phụ phí: không container, không đơn giá, ngày có thể trống
                payload.append({"container": "", "date": dmy(row["day"]), "note": "", "src": "FAKE",
                                "unitPriceVnd": None, "otherFeeVnd": str(row["fee"])})
        result = self.command("paste_trips", [month, json.dumps(payload, ensure_ascii=False)], None)
        require(result["pending_review"] == [], f"paste_trips: chuyến vào CHỜ KIỂM {result['pending_review']}")
        trips = [Trip(trip_id, month_of(row["day"]) if row["day"] else month, row["day"], "unit" in row,
                      row.get("unit"), row["fee"]) for trip_id, row in zip(result["trip_ids"], rows, strict=True)]
        self._reallocated("paste_trips", result, self.book.paste(trips))
        return f"dán {len(rows)} chuyến (tháng {month}): {rows} → id {result['trip_ids']}"

    def price(self, trip_id: int, unit: int | None, fee: int | None) -> str:
        expected = self.book.expect_price(trip_id, unit, fee)
        result = self.command("edit_trip_price", [trip_id, unit, fee], expected)
        if result:
            self._reallocated("edit_trip_price", result, self.book.edit_price(trip_id, unit, fee))
        return f"sửa giá chuyến {trip_id} = {unit} + phụ phí {fee}: {self._outcome(expected)}"

    def move(self, trip_id: int, day: str) -> str:
        expected = self.book.expect_move(trip_id, day)
        result = self.command("edit_trip_info", [trip_id, "event_date", day], expected)
        if result:
            self._reallocated("edit_trip_info", result, self.book.move(trip_id, day))
        return f"đổi ngày chuyến {trip_id} sang {day}: {self._outcome(expected)}"

    def delete_trip(self, trip_id: int) -> str:
        expected = self.book.expect_trip(trip_id)
        result = self.command("delete_trip", [trip_id], expected)
        if result:
            self._reallocated("delete_trip", result, self.book.delete_trip(trip_id))
        return f"xóa chuyến {trip_id}: {self._outcome(expected)}"

    def adjust(self, month: str, amount: int) -> str:
        expected = self.book.expect_adjust(month)
        result = self.command("adjust_month", [month, amount, "harness"], expected)
        if result:
            self._reallocated("adjust_month", result, self.book.adjust(result["adjustment_id"], month, amount))
        return f"điều chỉnh {month} {amount:+d}: {self._outcome(expected)}"

    def delete_adjustment(self, adjustment_id: int) -> str:
        expected = self.book.expect_delete_adjustment(adjustment_id)
        result = self.command("delete_month_adjustment", [adjustment_id], expected)
        if result:
            self._reallocated("delete_month_adjustment", result, self.book.delete_adjustment(adjustment_id))
        return f"xóa điều chỉnh {adjustment_id}: {self._outcome(expected)}"

    def receipt(self, day: str, amount: int, method: str) -> str:
        expected = self.book.expect_receipt()
        plan = [] if expected else self.book.plan_receipt(amount)
        result = self.command("record_receipt", [day, method, amount], expected)
        if result:
            pid = self.book.next_pid()
            require(result["pid"] == pid, f"record_receipt: mã phiếu {result['pid']}, mô hình {pid}")
            over = sum(value for _, kind, value in plan if kind == ADVANCE)
            require(int(result["overpayment_vnd"]) == over, f"record_receipt: dư {result['overpayment_vnd']}, mô hình {over}")
            self._reallocated("record_receipt", result, self.book.record_receipt(pid, day, amount, method))
            lines = canonical((x["month"], x["kind"], int(x["amount_vnd"])) for x in result["allocations"])
            require(lines == canonical(self.book.receipts[pid].lines), f"record_receipt: dòng trả về {lines}")
        return f"ghi thu {amount} ngày {day} ({method}): {self._outcome(expected)}"

    def edit_receipt(self, pid: str, day: str | None, method: str | None) -> str:
        expected = self.book.expect_receipt_edit(pid, day, method)
        result = self.command("edit_receipt_meta", [pid, day, method], expected)
        if result:
            self._reallocated("edit_receipt_meta", result, self.book.edit_receipt(pid, day, method))
        return f"sửa phiếu {pid} ngày={day} hình thức={method}: {self._outcome(expected)}"

    def void(self, pid: str) -> str:
        expected = self.book.expect_void(pid)
        result = self.command("void_receipt", [pid, "harness"], expected)
        if result:
            count = self.book.void(pid)
            require(result["voided_lines"] == count, f"void_receipt: hủy {result['voided_lines']} dòng, mô hình {count}")
        return f"hủy phiếu {pid}: {self._outcome(expected)}"

    def lock(self, month: str, locked: bool) -> str:
        result = self.command("set_month_lock", [month, "true" if locked else "false"], None)
        require(result["locked"] is locked, f"set_month_lock: trả {result}")
        self.book.set_lock(month, locked)
        return f"{'khóa' if locked else 'mở'} tháng {month}"

    def replay(self, index: int) -> str:
        key, sql, first = self.history[index]
        again = json.loads(self.pg.value(sql))
        require(again == first, f"gửi lặp {key}: kết quả khác lần đầu\n  lần đầu: {first}\n  gửi lặp: {again}")
        return f"gửi lặp lệnh {key}: trả đúng kết quả đã lưu"

    def conflict(self, index: int) -> str:
        key = self.history[index][0]
        self.command("adjust_month", [MONTHS[0], 1, f"xung đột {self._next()}"], "IDEMPOTENCY_CONFLICT", key=key)
        return f"dùng lại khóa {key} cho lệnh khác: bị từ chối IDEMPOTENCY_CONFLICT"

    def stale(self) -> str:
        self.command("record_receipt", ["2026-01-15", METHODS[0], 10], "STALE_LEDGER", version=self.book.version + 1)
        return "ghi thu với phiên bản sai: bị từ chối STALE_LEDGER"

    # ---- so cả sổ ----
    def verify(self, label: str) -> None:
        state = json.loads(self.pg.value(actor_sql(STATE.format(c=self.customer))))
        book, ledger = self.book, state["ledger"]

        def same(what: str, got, want) -> None:
            require(got == want, f"sau bước '{label}': {what} lệch\n  DB:      {got}\n  mô hình: {want}")

        same("version", ledger["version"], book.version)
        same("phiếu và dòng phân bổ",
             {r["pid"]: (r["day"], r["amount"], r["method"], r["voided"], [tuple(x) for x in r["lines"]])
              for r in state["receipts"]},
             {r.pid: (r.day, r.amount, r.method, r.voided, canonical(r.lines)) for r in book.receipts.values()})
        same("các tháng của get_ledger (tháng, nợ còn lại, phát sinh, đã thu, cuối tháng)",
             [(m["month"], int(m["outstanding_vnd"]), int(m["charges_vnd"]), int(m["received_vnd"]),
               int(m["end_of_month_vnd"])) for m in ledger["months"]], book.ledger_months())
        same("tổng còn phải thu", int(ledger["total_outstanding_vnd"]), book.total())
        same("chuyến (tháng, đơn giá, phụ phí, tiền, thiếu giá, sửa được)",
             {t["id"]: (t["month"], opt(t["unit_price_vnd"]), opt(t["other_fee_vnd"]), opt(t["amount_vnd"]),
                        t["is_missing_price"], t["editable"]) for t in ledger["trips"]},
             {t.id: (t.month, t.unit, t.fee, t.amount, t.amount is None, not book.locked(t.month))
              for t in book.live_trips()})
        same("chuyến thiếu giá", ledger["pending_count"], sum(t.amount is None for t in book.live_trips()))
        same("điều chỉnh tháng", {a["id"]: (a["month"], int(a["amount_vnd"])) for a in ledger["adjustments"]},
             {a.id: (a.month, a.amount) for a in book.adjustments.values() if not a.deleted})
        same("khóa tháng", {x["month"]: x["locked"] for x in ledger["month_locks"]}, book.locks)
