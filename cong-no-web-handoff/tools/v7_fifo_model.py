"""Mô hình tham chiếu cho phân bổ thu theo nợ cũ trước của sổ khách V7 — chỉ dùng để kiểm.

Viết độc lập với SQL: không đọc DB, không import `web/`. Luật theo `specs/v7-fifo-ngau-nhien.md`
(V7-SO, V7-BE (6), CAN-DU-01, XOA-DC-THANG-01). Harness `test_pg_v7_fifo_ngau_nhien.py` chạy cùng một
chuỗi lệnh trên PostgreSQL và trên mô hình này rồi so từng bước.

Quy ước: tháng là chuỗi 'YYYY-MM-01', ngày 'YYYY-MM-DD' (so chuỗi đúng thứ tự thời gian), tiền là int
VND nguyên, None là chưa có số (khác 0). Hàm `expect_*` trả mã lỗi SQL dự đoán theo đúng thứ tự kiểm
của hàm SQL tương ứng, None nghĩa là lệnh được nhận; hàm còn lại đổi trạng thái khi lệnh được nhận.
"""

from __future__ import annotations

from dataclasses import dataclass, field

DEBT, ADVANCE = "debt", "advance"
Line = tuple[str, str, int]  # (tháng, DEBT | ADVANCE, tiền)


def month_of(day: str) -> str:
    return day[:8] + "01"


def canonical(lines) -> list[Line]:
    """Thứ tự dòng như SQL so: tháng, rồi nợ trước ứng trước (không theo chữ cái)."""
    return sorted(lines, key=lambda line: (line[0], 0 if line[1] == DEBT else 1))


@dataclass
class Trip:
    id: int
    month: str
    day: str | None  # ngày xe; None ở dòng chỉ phụ phí không ngày
    container: bool  # False: dòng chỉ phụ phí (không container, không đơn giá)
    unit: int | None
    fee: int | None  # phụ phí; 0 không sinh dòng phụ phí nên mô hình coi như None
    deleted: bool = False

    @property
    def amount(self) -> int | None:
        """Tiền chuyến tính vào nợ (V7-BE): có đơn giá thì cộng phụ phí, trống tính 0; chưa giá là None."""
        if self.unit is not None:
            return self.unit + (self.fee or 0)
        return None if self.container else self.fee


@dataclass
class Adjustment:
    id: int
    month: str
    amount: int
    deleted: bool = False  # xóa bằng dòng đảo dấu; cả hai cùng ẩn (XOA-DC-THANG-01)


@dataclass
class Receipt:
    pid: str
    day: str
    amount: int
    method: str
    voided: bool = False
    lines: list[Line] = field(default_factory=list)


class Book:
    def __init__(self, openings: dict[str, int], open_months=(), current_month: str = ""):
        self.openings = dict(openings)
        self.trips: dict[int, Trip] = {}
        self.adjustments: dict[int, Adjustment] = {}
        self.receipts: dict[str, Receipt] = {}
        self.locks = dict.fromkeys(open_months, False)
        self.current_month = current_month
        self.version = 0

    # ---- trạng thái ----
    def locked(self, month: str) -> bool:
        """Tháng chưa có dòng khóa thì chỉ tháng hiện tại (giờ VN) mở (V7-SO)."""
        return self.locks.get(month, month != self.current_month)

    def live_trips(self) -> list[Trip]:
        return [trip for trip in self.trips.values() if not trip.deleted]

    def live_receipts(self) -> list[Receipt]:
        """Phiếu chưa hủy theo (ngày, mã phiếu); mã so như chuỗi, giống `pid COLLATE "C"`."""
        return sorted((r for r in self.receipts.values() if not r.voided), key=lambda r: (r.day, r.pid))

    def _movements(self):
        """(tháng, tiền | None) của opening, chuyến còn hiệu lực và điều chỉnh tháng còn hiệu lực."""
        yield from self.openings.items()
        for trip in self.live_trips():
            yield trip.month, trip.amount
        for adjustment in self.adjustments.values():
            if not adjustment.deleted:
                yield adjustment.month, adjustment.amount

    def charge_months(self) -> list[str]:
        """Tháng có dòng phát sinh, kể cả chuyến chưa giá: tập tháng của `reallocate`/`record_receipt`."""
        return sorted({month for month, _ in self._movements()})

    def charges(self) -> dict[str, int]:
        """Phát sinh từng tháng phát sinh, bỏ tiền None (tháng chỉ có chuyến chưa giá là 0)."""
        total = dict.fromkeys(self.charge_months(), 0)
        for month, amount in self._movements():
            if amount is not None:
                total[month] += amount
        return total

    def raw(self) -> dict[str, int]:
        """`v_outstanding_month_raw`: phát sinh có số trừ dòng phân bổ còn hiệu lực; chỉ tháng có dòng."""
        raw: dict[str, int] = {}
        for month, amount in self._movements():
            if amount is not None:
                raw[month] = raw.get(month, 0) + amount
        for receipt in self.live_receipts():
            for month, _, amount in receipt.lines:
                raw[month] = raw.get(month, 0) - amount
        return dict(sorted(raw.items()))

    def outstanding(self) -> dict[str, int]:
        """`v_outstanding_month` (CAN-DU-01): khoản dư của tháng âm cấn vào tháng nợ cũ nhất; dư còn lại ở tháng cuối."""
        raw = self.raw()
        credit = sum(max(-value, 0) for value in raw.values())
        debt = sum(max(value, 0) for value in raw.values())
        result, through = {}, 0
        for month, value in raw.items():
            through += max(value, 0)
            result[month] = min(max(value, 0), max(through - credit, 0))
        if raw:
            result[next(reversed(raw))] += min(debt - credit, 0)
        return result

    def total(self) -> int:
        return sum(self.outstanding().values())

    def ledger_months(self) -> list[tuple[str, int, int, int, int]]:
        """Các tháng của `get_ledger`: (tháng, nợ còn lại, phát sinh, đã thu theo ngày phiếu, số cuối tháng)."""
        outstanding, charges = self.outstanding(), self.charges()
        received: dict[str, int] = {}
        for receipt in self.live_receipts():
            received[month_of(receipt.day)] = received.get(month_of(receipt.day), 0) + receipt.amount
        keys = set(outstanding) | {trip.month for trip in self.live_trips()} | set(received)
        total, later, rows = sum(outstanding.values()), 0, []
        for month in sorted(keys, reverse=True):
            rows.append((month, outstanding.get(month, 0), charges.get(month, 0), received.get(month, 0), total - later))
            later += charges.get(month, 0) - received.get(month, 0)
        return rows[::-1]

    # ---- phân bổ ----
    @staticmethod
    def _fifo(amount: int, debts: list[list], last: str) -> list[Line]:
        """Trừ tháng còn nợ dương từ cũ tới mới (sửa `debts` tại chỗ); phần dư là ứng trước ở `last`."""
        lines: list[Line] = []
        for debt in debts:
            if amount == 0:
                break
            if debt[1] > 0:
                take = min(amount, debt[1])
                lines.append((debt[0], DEBT, take))
                debt[1] -= take
                amount -= take
        if amount > 0:
            lines.append((last, ADVANCE, amount))
        return lines

    def reallocate(self) -> list[str]:
        """`sokhach.reallocate`: phân bổ lại mọi phiếu chưa hủy; trả mã phiếu có dòng đổi, theo (ngày, mã)."""
        live = self.live_receipts()
        months = self.charge_months()
        last = months[-1] if months else max((line[0] for r in live for line in r.lines), default=None)
        if last is None and live:
            raise AssertionError("mô hình: có phiếu mà không có tháng nào để phân bổ")
        debts = [[month, amount] for month, amount in self.charges().items()]
        changed = []
        for receipt in live:
            lines = self._fifo(receipt.amount, debts, last)
            if lines != receipt.lines:
                changed.append(receipt.pid)
                receipt.lines = lines
        return changed

    def plan_receipt(self, amount: int) -> list[Line]:
        """Kế hoạch `record_receipt` trước khi phân bổ lại: theo nợ thô còn lại sau các phiếu khác."""
        debts = [[month, value] for month, value in self.raw().items()]
        return self._fifo(amount, debts, self.charge_months()[-1])

    def next_pid(self) -> str:
        """`_next_pid`: số lớn nhất của mọi phiếu, kể cả phiếu hủy, cộng 1, đệm 3 chữ số."""
        numbers = [int(pid[3:]) for pid in self.receipts if pid[3:].isdigit()]
        return f"PH-{max(numbers, default=0) + 1:03d}"

    # ---- dự đoán kết quả lệnh ----
    def expect_trip(self, trip_id: int) -> str | None:
        trip = self.trips[trip_id]
        if trip.deleted:
            return "TRIP_NOT_FOUND"
        return "MONTH_LOCKED" if self.locked(trip.month) else None

    def expect_price(self, trip_id: int, unit: int | None, fee: int | None) -> str | None:
        trip = self.trips[trip_id]
        error = self.expect_trip(trip_id) or ("NO_CHANGE" if (trip.unit, trip.fee) == (unit, fee) else None)
        if error is None and trip.day is None and (unit is not None or fee is None):
            # Ràng buộc hoãn `check_trip_missing_date`, báo lúc COMMIT: dòng không ngày chỉ được là dòng phụ phí.
            return "INVALID_FEE_ONLY_DATE"
        return error

    def expect_move(self, trip_id: int, day: str) -> str | None:
        trip = self.trips[trip_id]
        error = self.expect_trip(trip_id)
        if error or trip.day == day:
            return error or "NO_CHANGE"
        return "MONTH_LOCKED" if month_of(day) != trip.month and self.locked(month_of(day)) else None

    def expect_adjust(self, month: str) -> str | None:
        if month not in self.charge_months():
            return "MONTH_NOT_FOUND"
        return "MONTH_LOCKED" if self.locked(month) else None

    def expect_delete_adjustment(self, adjustment_id: int) -> str | None:
        adjustment = self.adjustments[adjustment_id]
        if adjustment.deleted:
            return "ADJUSTMENT_NOT_FOUND"
        return "MONTH_LOCKED" if self.locked(adjustment.month) else None

    def expect_receipt(self) -> str | None:
        return None if self.charge_months() else "NO_MONTH_FOR_RECEIPT"

    def expect_receipt_edit(self, pid: str, day: str | None, method: str | None) -> str | None:
        receipt = self.receipts[pid]
        if receipt.voided:
            return "RECEIPT_NOT_FOUND"
        return "NO_CHANGE" if (day or receipt.day, method or receipt.method) == (receipt.day, receipt.method) else None

    def expect_void(self, pid: str) -> str | None:
        return "RECEIPT_ALREADY_VOID" if self.receipts[pid].voided else None

    # ---- áp lệnh đã được nhận; lệnh có phân bổ lại trả mã phiếu đổi dòng ----
    def _done(self, changed: list[str]) -> list[str]:
        self.version += 1
        return changed

    def paste(self, trips: list[Trip]) -> list[str]:
        for trip in trips:
            self.trips[trip.id] = trip
        return self._done(self.reallocate())

    def edit_price(self, trip_id: int, unit: int | None, fee: int | None) -> list[str]:
        trip = self.trips[trip_id]
        trip.unit, trip.fee = unit, fee
        return self._done(self.reallocate())

    def move(self, trip_id: int, day: str) -> list[str]:
        trip = self.trips[trip_id]
        trip.day, trip.month = day, month_of(day)
        return self._done(self.reallocate())

    def delete_trip(self, trip_id: int) -> list[str]:
        self.trips[trip_id].deleted = True
        return self._done(self.reallocate())

    def adjust(self, adjustment_id: int, month: str, amount: int) -> list[str]:
        self.adjustments[adjustment_id] = Adjustment(adjustment_id, month, amount)
        return self._done(self.reallocate())

    def delete_adjustment(self, adjustment_id: int) -> list[str]:
        self.adjustments[adjustment_id].deleted = True
        return self._done(self.reallocate())

    def record_receipt(self, pid: str, day: str, amount: int, method: str) -> list[str]:
        self.receipts[pid] = Receipt(pid, day, amount, method, lines=self.plan_receipt(amount))
        return self._done(self.reallocate())

    def edit_receipt(self, pid: str, day: str | None, method: str | None) -> list[str]:
        receipt = self.receipts[pid]
        moved = day is not None and day != receipt.day
        receipt.day, receipt.method = day or receipt.day, method or receipt.method
        return self._done(self.reallocate() if moved else [])

    def void(self, pid: str) -> int:
        """Hủy phiếu: bỏ dòng của chính phiếu đó, không phân bổ lại phiếu khác (V7-SO)."""
        receipt = self.receipts[pid]
        count, receipt.voided, receipt.lines = len(receipt.lines), True, []
        self._done([])
        return count

    def set_lock(self, month: str, locked: bool) -> None:
        self.locks[month] = locked
        self._done([])
