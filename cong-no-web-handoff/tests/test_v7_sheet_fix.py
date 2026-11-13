"""Máy tự sửa sổ lệch Sheet (MAY-DOI-SOAT-01): chỉ ghi khi đúng một tổ hợp đưa tổng về đúng tổng Sheet. Dữ liệu giả."""

import datetime as dt
import sys
import unittest
from pathlib import Path
from typing import ClassVar

sys.path.insert(0, str(Path(__file__).parents[1] / "web"))
import v7_sheet_fix as fix
from v7_api_validate import ApiError
from v7_inbox import AUTO_ACTOR
from v7_receipt_queue import project_receipts

TODAY = dt.date(2026, 11, 4)


def receipt(status, amount, month="2026-08", source_row=30, **extra):
    return {"customer_tab": "KHACH A", "source_row": source_row, "debt_month": month, "amount_vnd": str(amount), "note": "da tt",
            "date": extra.pop("date", None), "status": status, **extra}


def price(status, month="2026-10", kind="trip", target=11, sheet=("100", None), web=(None, None), total=None):
    return {"status": status, "month": month, "target_kind": kind, "target_id": target, "container": f"C{target}",
            "sheet_unit_price_vnd": sheet[0], "sheet_other_fee_vnd": sheet[1],
            "web_unit_price_vnd": web[0], "web_other_fee_vnd": web[1], "web_total_vnd": total}


class HelperTests(unittest.TestCase):
    def test_month_end_never_after_today(self):
        self.assertEqual(fix.month_end("2026-08", TODAY), "2026-08-31")
        self.assertEqual(fix.month_end("2024-02-01", TODAY), "2024-02-29")
        self.assertEqual(fix.month_end("2026-11", TODAY), "2026-11-04")

    def test_receipt_groups_by_kind_and_month(self):
        orphans = [{"id": 5, "amount_vnd": "300"}, {"id": 6, "amount_vnd": "100"}]
        receipts = {"ready": [receipt("READY", 70, date="2026-10-02"), receipt("READY", 30, date="2026-10-03")],
                    "review": [receipt("NO_DATE", 500, source_fingerprint="a" * 64),
                               receipt("NO_DATE", 11, month="2026-07", source_fingerprint="b" * 64),
                               receipt("SHEET_EDITED", 450, month="2026-07", date="2026-08-02", web_legacy=orphans),
                               receipt("FUTURE_DATE", 9), receipt("WEB_DELETED", 8), receipt("WEB_VOIDED", 7, date="2026-10-04")]}
        groups = fix.receipt_groups(receipts, {"legacy_rows": []})
        self.assertEqual([(g["kind"], g["month"], g["delta_vnd"], len(g["rows"])) for g in groups],
                         [("receipts", None, -100, 2),
                          ("receipts_edited", "2026-07", 400 - 461, 2),   # phiếu không ngày cùng tháng đi chung nhóm thay phiếu
                          ("receipts_no_date", "2026-08", -500, 1)])     # phiếu ngày tương lai, web đã xóa, phiếu người đã hủy: không phải việc của máy

    def test_edited_month_is_left_when_booked_amount_differs_from_sheet(self):
        receipts = {"ready": [], "review": [receipt("SHEET_EDITED", 450, date="2026-08-02", web_legacy=[{"id": 5, "amount_vnd": "300"}])]}
        self.assertEqual(fix.receipt_groups(receipts, {"legacy_rows": [{"id": 5, "counted_differs": True}]}), [])

    def test_price_delta_matches_what_will_be_written(self):
        self.assertEqual(fix.price_delta(price("READY", sheet=("100", "7"))), 107)                       # chưa giá: chưa tính nợ
        self.assertEqual(fix.price_delta(price("CONFLICT", sheet=("100", None), web=("90", "5"))), 5)     # phụ phí trống là 0
        self.assertEqual(fix.price_delta(price("CONFLICT", sheet=("90", "3"), web=("90", None))), 3)
        legacy = {"kind": "legacy", "target": 22}
        self.assertEqual(fix.price_delta(price("MONTH_LOCKED", sheet=("100", None), total="40", **legacy)), 60)   # đã có tổng
        self.assertEqual(fix.price_delta(price("READY", sheet=("100", None), web=(None, "5"), total="0", **legacy)), 105)   # không ghi phụ phí
        self.assertEqual(fix.price_delta(price("CONFLICT", sheet=("100", None), web=("100", "5"), total="105", **legacy)), -5)
        self.assertIsNone(fix.price_delta(price("CONFLICT", sheet=("100", "5"), web=("100", "5"), total="90", **legacy)))    # không có lệnh nào
        self.assertIsNone(fix.price_delta(price("CONFLICT", sheet=("100", None), web=("90", None), total=None, **legacy)))

    def test_price_groups_only_rows_the_machine_may_write(self):
        prices = {"ready": [price("READY", month="2026-11")],
                  "review": [price("CONFLICT", sheet=("100", None), web=("90", None)), price("MONTH_LOCKED", month="2026-09"),
                             price("AMBIGUOUS"), price("MANUAL"), price("PENDING_REVIEW")]}
        total_only = [price("READY", month="2026-09", sheet=("45", None))]
        self.assertEqual([(g["month"], g["delta_vnd"], len(g["rows"])) for g in fix.price_groups(prices, total_only)],
                         [("2026-09", 145, 2), ("2026-10", 10, 1), ("2026-11", 100, 1)])


def sheet_row(source_row, container, unit=None, total=None, month="2026-11", tab="KHACH A"):
    return {"customer_tab": tab, "source_row": source_row, "debt_month": month, "container": container, "date": month + "-01",
            "sheet_unit_price_vnd": unit, "sheet_other_fee_vnd": None, "sheet_total_vnd": total}


def web_trip(trip_id, container, unit=None, fee=None, status="confirmed", month="2026-11"):
    return {"id": trip_id, "container": container, "unit_price_vnd": unit, "other_fee_vnd": fee, "status": status,
            "month": month + "-01", "event_date": month + "-01"}


class PlanTests(unittest.TestCase):
    CUSTOMERS = ({"id": 7, "name": "KHACH A"}, {"id": 8, "name": "KHACH B"})

    def plan(self, rows, trips=(), legacy=(), adjustments=(), locks=()):
        ledger = {"customer_id": 7, "today_month": "2026-11-01", "trips": list(trips), "legacy_rows": list(legacy),
                  "adjustments": list(adjustments), "month_locks": list(locks), "receipts": [], "events": []}
        prices = {"rows": list(rows), "sha256": "a" * 64}
        return fix.plan(prices, {"rows": [], "sha256": "b" * 64}, ledger, list(self.CUSTOMERS), TODAY)

    def check(self, rows, trips, adjustments=(), today=TODAY):
        ledger = {"customer_id": 7, "today_month": "2026-11-01", "trips": list(trips), "legacy_rows": [],
                  "adjustments": list(adjustments), "month_locks": [], "receipts": [], "events": []}
        return fix.ahead_to_check({"rows": list(rows), "sha256": "a" * 64}, ledger, list(self.CUSTOMERS), today)

    def test_web_ahead_trips_a_person_should_look_at(self):
        fresh = web_trip(1, "AAAA1", unit="100")                         # 3 ngày: Sheet chưa kịp nhập
        old = web_trip(2, "AAAA2", unit="70", fee="5", month="2026-10")  # ngày 01/10: 34 ngày
        moved = web_trip(3, "AAAA3", unit="20")                          # Sheet ghi đúng chuyến này ở tab khách B
        reused = web_trip(4, "AAAA4", unit="30")                         # tab B có container này từ tháng 8: container dùng lại, chuyến khác
        rows = [sheet_row(9, "AAAA3", unit=20, total=20, tab="KHACH B"), sheet_row(8, "AAAA4", unit=30, total=30, month="2026-08", tab="KHACH B")]
        self.assertEqual(self.check(rows, [fresh, old, moved, reused]), [
            {"kind": "ahead_other_book", "container": "AAAA3", "date": "2026-11-01", "amount_vnd": 20, "other": "KHACH B"},
            {"kind": "ahead_old", "container": "AAAA2", "date": "2026-10-01", "amount_vnd": 75, "days": 34}])
        # Đúng 14 ngày thì chưa hỏi, sang ngày 15 mới hỏi.
        self.assertEqual(self.check([], [fresh], today=dt.date(2026, 11, 15)), [])
        self.assertEqual([hint["days"] for hint in self.check([], [fresh], today=dt.date(2026, 11, 16))], [15])
        # Dòng Sheet có container mà trống giá cũng tính tuổi như chuyến không có trên tab.
        self.assertEqual([hint["kind"] for hint in self.check([sheet_row(1, "AAAA2", month="2026-10")], [old])], ["ahead_old"])
        # Tiền đã ra khỏi sổ bằng dòng điều chỉnh, hoặc là dòng Sheet mất container: không tính đi trước nên không hỏi.
        gone = {"id": 61, "month": "2026-10-01", "amount_vnd": "-75", "note": "dời sang sổ khác"}
        self.assertEqual(self.check([], [old], adjustments=[gone]), [])
        self.assertEqual(self.check([sheet_row(5, "", unit=75, total=75, month="2026-10")], [old]), [])

    def test_web_ahead_is_priced_web_trips_the_sheet_has_not_priced(self):
        rows = [sheet_row(1, "AAAA1"), sheet_row(2, "AAAA2"), sheet_row(3, "AAAA3", unit=5, total=5), sheet_row(4, "AAAA4", total=0),
                sheet_row(5, "AAAA5", tab="KHACH B")]
        trips = [web_trip(1, "AAAA1", unit="100", fee="7"),         # Sheet có dòng, chưa giá: đi trước
                 web_trip(2, "AAAA2"),                              # hai bên chưa giá
                 web_trip(3, "AAAA3", unit="900"),                  # hai bên có giá: việc của hàng chờ giá
                 web_trip(4, "AAAA4", unit="11"),                   # TỔNG 0 cũng là chưa ghi giá
                 web_trip(5, "AAAA6", unit="20"),                   # chưa có dòng nào trên tab của khách này
                 web_trip(6, "AAAA7", unit="30", status="pending_review")]   # chờ kiểm chưa tính nợ
        legacy = [{"id": 40, "kind": "trip", "month": "2026-11-01",
                   "current": {"container": "AAAA8", "event_date": "2026-11-01", "unit_price_vnd": "50", "counted_vnd": "50", "month": "2026-11-01"}}]
        _, ahead, shuffled = self.plan(rows, trips, legacy)
        self.assertEqual((ahead, shuffled), (107 + 11 + 20, []))   # dòng sổ gốc không tính

    def test_undated_copy_rule_gives_the_machine_nothing_new_to_write(self):
        # GHEP-KHONG-NGAY-01: dòng Sheet không ngày ghép với bản sao không ngày giống hệt chỉ rời "Cần xem"; nhóm việc của máy
        # và tiền web đi trước y như khi dòng đó còn là "khớp nhiều chuyến".
        copy = {"id": 40, "kind": "trip", "month": "2026-06-01", "current": {
            "container": "AAAA1", "event_date": None, "unit_price_vnd": "50", "counted_vnd": "50", "month": "2026-06-01"}}
        undated = sheet_row(1, "AAAA1", unit=50, total=50, month="2026-06") | {"date": None}
        unpriced, ahead = web_trip(1, "AAAA1"), web_trip(2, "AAAA2", unit="30")
        self.assertEqual(self.plan([undated], [unpriced, ahead], [copy]), ([], 30, []))
        # Dòng Sheet có ngày của chuyến chưa giá vẫn là việc ghi giá như thường.
        dated = sheet_row(2, "AAAA1", unit=70, total=70)
        groups, money_ahead, shuffled = self.plan([undated, dated], [unpriced, ahead], [copy])
        self.assertEqual([(g["kind"], g["month"], g["delta_vnd"]) for g in groups], [("prices", "2026-11", 70)])
        self.assertEqual((money_ahead, shuffled), (30, []))

    def test_web_ahead_leaves_out_trips_an_adjustment_already_took_off_the_book(self):
        rows = [sheet_row(1, "AAAA1", unit=5, total=5, month="2026-03")]
        trips = [web_trip(1, "BBBB1", unit="46", month="2026-03"), web_trip(2, "BBBB2", unit="43", fee="1", month="2026-03"),
                 web_trip(3, "BBBB3", unit="20", month="2026-04")]
        moved = {"id": 61, "month": "2026-03-01", "amount_vnd": "-90", "note": "4 chuyến dời sang sổ khác"}
        self.assertEqual(self.plan(rows, trips, adjustments=[moved])[1], 20)   # tháng 3 đã trừ hết, tháng 4 vẫn đi trước
        pair = [{"id": 62, "month": "2026-03-01", "amount_vnd": "7"}, {"id": 63, "month": "2026-03-01", "amount_vnd": "-7"}]
        self.assertEqual(self.plan(rows, trips, adjustments=[moved, *pair])[1], 20)   # cặp tự triệt tiêu không làm đổi kết luận
        partly = {"id": 64, "month": "2026-03-01", "amount_vnd": "-50"}
        self.assertEqual(self.plan(rows, trips, adjustments=[partly])[1], 110)  # trừ không đúng bằng: không suy ra được, tính như thường
        other_month = {"id": 65, "month": "2026-04-01", "amount_vnd": "-90"}
        self.assertEqual(self.plan(rows, trips, adjustments=[other_month])[1], 110)  # khác tháng không liên quan

    def test_plan_reports_shuffled_month_and_leaves_its_prices_out(self):
        rows = [sheet_row(1, "AAAA1", unit=75, total=75, month="2026-10"), sheet_row(2, "AAAA2", unit=50, total=50, month="2026-10"),
                sheet_row(3, "AAAA3", unit=90, total=90, month="2026-09")]
        trips = [web_trip(1, "AAAA1", unit="50", month="2026-10"), web_trip(2, "AAAA2", unit="75", month="2026-10"),
                 web_trip(3, "AAAA3", unit="80", month="2026-09")]
        groups, _, shuffled = self.plan(rows, trips)
        self.assertEqual(shuffled, ["2026-10"])
        self.assertEqual([(g["kind"], g["month"], g["delta_vnd"]) for g in groups], [("prices", "2026-09", 10)])

    def test_total_without_unit_price_becomes_the_price_of_an_unpriced_trip(self):
        rows = [sheet_row(1, "AAAA1", total=45), sheet_row(2, "AAAA2", total=46), sheet_row(3, "AAAA3", total=47), sheet_row(4, "AAAA4", total=0)]
        trips = [web_trip(1, "AAAA1"), web_trip(2, "AAAA2", unit="9"), web_trip(3, "AAAA3", status="pending_review"), web_trip(4, "AAAA4")]
        legacy = [{"id": 40, "kind": "trip", "month": "2026-11-01",   # sổ gốc đã tính 30: tiền đã ở trong sổ, không ghi thêm
                   "current": {"container": "AAAA5", "event_date": "2026-11-01", "unit_price_vnd": None, "counted_vnd": "30", "month": "2026-11-01"}}]
        rows.append(sheet_row(5, "AAAA5", total=48))
        groups, ahead, _ = self.plan(rows, trips, legacy)
        self.assertEqual(ahead, 0)   # dòng 2 có TỔNG trên Sheet, web không đi trước
        self.assertEqual([(g["kind"], g["month"], g["delta_vnd"]) for g in groups], [("prices", "2026-11", 45)])
        row = groups[0]["rows"][0]
        self.assertEqual((row["target_id"], row["sheet_unit_price_vnd"], row["status"]), (1, "45", "READY"))

    def test_money_row_without_container_unless_already_booked(self):
        rows = [sheet_row(10, "", unit=43, total=43, month="2026-10"), sheet_row(11, "", total=0, month="2026-10"),
                sheet_row(12, "", unit=5, total=5, month="2026-09"), sheet_row(13, "", unit=6, total=6, month="2026-09"),
                sheet_row(14, "", unit=-2, total=-2, month="2026-08")]
        legacy = [{"id": 50, "kind": "trip", "month": "2026-09-01", "current": {"container": None, "counted_vnd": "5", "month": "2026-09-01"}}]
        adjustments = [{"month": "2026-09-01", "amount_vnd": "6", "note": fix.FEE_NOTE + ", dòng 13"},
                       {"month": "2026-10-01", "amount_vnd": "43", "note": "dòng người ghi"}]
        groups, _, _ = self.plan(rows, legacy=legacy, adjustments=adjustments)
        self.assertEqual([(g["kind"], g["month"], g["delta_vnd"], [r["source_row"] for r in g["rows"]]) for g in groups],
                         [("fee_rows", "2026-08", -2, [14]), ("fee_rows", "2026-10", 43, [10])])

    def test_price_handed_on_through_a_blank_cell_gives_no_price_group(self):
        # Thật: AAAA1=100, AAAA2=70, AAAA3 chưa giá. Sheet xếp lại container mà cột giá đứng yên: AAAA1 trống, AAAA2=100, AAAA3=70.
        rows = [sheet_row(1, "AAAA1"), sheet_row(2, "AAAA2", unit=100, total=100), sheet_row(3, "AAAA3", unit=70, total=70)]
        priced = [web_trip(1, "AAAA1", unit="100"), web_trip(2, "AAAA2", unit="70")]
        for last in (web_trip(3, "AAAA3"), web_trip(3, "AAAA3", unit="70")):   # trước và sau khi máy giá 15 phút ghi dòng sẵn sàng
            groups, ahead, shuffled = self.plan(rows, [*priced, last])
            self.assertEqual((shuffled, groups, ahead), (["2026-11"], [], 100))
            self.assertNotEqual(fix.choose(groups, 30)[0], "FIX")
        # Sửa giá thường, cùng tháng có chuyến web đi trước ở giá khác: vẫn là việc của máy.
        rows[1] = sheet_row(2, "AAAA2", unit=90, total=90)
        groups, ahead, shuffled = self.plan(rows, [*priced, web_trip(3, "AAAA3", unit="70")])
        self.assertEqual((shuffled, [(g["kind"], g["delta_vnd"]) for g in groups], ahead), ([], [("prices", 20)], 100))

    def test_sheet_row_that_lost_its_container_is_the_web_trip_not_a_new_fee(self):
        rows = [sheet_row(1, "", unit=100, total=100)]
        trips = [web_trip(1, "AAAA1", unit="100")]
        self.assertEqual(self.plan(rows, trips)[:2], ([], 0))   # trước đây: một dòng phí +100 và web đi trước 100
        # Lượt trước đã lỡ ghi dòng điều chỉnh cho dòng này: thành nhóm hủy, tổng về đúng Sheet.
        wrong = {"id": 90, "month": "2026-11-01", "amount_vnd": "100", "note": fix.FEE_NOTE + ", dòng 1"}
        groups, ahead, _ = self.plan(rows, trips, adjustments=[wrong])
        self.assertEqual(([(g["kind"], g["delta_vnd"]) for g in groups], ahead), ([("fee_undo", -100)], 0))
        # Khác số tiền hoặc khác tháng thì vẫn là hai việc riêng: dòng phí mới và chuyến web đi trước.
        for other in (web_trip(1, "AAAA1", unit="99"), web_trip(1, "AAAA1", unit="100", month="2026-10")):
            groups, ahead, _ = self.plan(rows, [other])
            self.assertEqual(([(g["kind"], g["delta_vnd"]) for g in groups], ahead), ([("fee_rows", 100)], int(other["unit_price_vnd"])))
        # Hai dòng mất container mà web chỉ có một chuyến trùng: ghép một, dòng còn lại vẫn là dòng phí.
        groups, ahead, _ = self.plan([*rows, sheet_row(2, "", unit=100, total=100)], trips)
        self.assertEqual(([(g["kind"], g["delta_vnd"], len(g["rows"])) for g in groups], ahead), ([("fee_rows", 100, 1)], 0))


class ShuffledTests(unittest.TestCase):
    @staticmethod
    def conflict(web, sheet, month="2026-10", fee=None):
        return price("CONFLICT", month=month, sheet=(sheet, fee), web=(web, None))

    def months(self, *rows):
        return fix.shuffled_months({"ready": [], "review": list(rows)})

    def test_prices_changing_places_in_a_circle(self):
        # Đúng ca đo trên `hao`: 50→75, 75→65, 65→50 là vòng; 55→50 đứng ngoài vòng vẫn không che được.
        self.assertEqual(self.months(self.conflict("55", "50"), self.conflict("50", "75"), self.conflict("75", "65"), self.conflict("65", "50")), ["2026-10"])
        self.assertEqual(self.months(self.conflict("50", "75"), self.conflict("75", "50")), ["2026-10"])

    def test_ordinary_corrections_are_not_a_circle(self):
        self.assertEqual(self.months(self.conflict("55", "50")), [])
        self.assertEqual(self.months(self.conflict("55", "50"), self.conflict("56", "50"), self.conflict("50", "45")), [])
        self.assertEqual(self.months(self.conflict("50", "50", fee="7")), [])   # chỉ khác phụ phí
        self.assertEqual(self.months(price("READY", sheet=("50", None))), [])   # web chưa có giá: không có gì để so
        self.assertEqual(self.months(self.conflict("50", "75"), self.conflict("75", "50", month="2026-09")), [])   # khác tháng

    def test_month_with_shuffled_prices_gives_no_price_group(self):
        prices = {"ready": [price("READY", month="2026-11")],
                  "review": [self.conflict("50", "75"), self.conflict("75", "50"), price("MONTH_LOCKED", month="2026-10")]}
        shuffled = fix.shuffled_months(prices)
        self.assertEqual([g["month"] for g in fix.price_groups(prices, [price("READY", month="2026-10", sheet=("45", None))], shuffled)], ["2026-11"])


class FeeUndoTests(unittest.TestCase):
    def test_machine_adjustment_whose_sheet_row_is_gone_becomes_an_undo_group(self):
        rows = [sheet_row(10, "", unit=43, total=43, month="2026-10")]
        adjustments = [{"id": 1, "month": "2026-10-01", "amount_vnd": "43", "note": fix.FEE_NOTE + ", dòng 10"},   # dòng còn: đã ghi rồi
                       {"id": 2, "month": "2026-09-01", "amount_vnd": "6", "note": fix.FEE_NOTE + ", dòng 13"},    # Sheet không còn dòng này
                       {"id": 3, "month": "2026-09-01", "amount_vnd": "7", "note": "dòng người ghi"}]               # của người: không đụng
        groups = fix.fee_groups([{"status": "NO_CONTAINER", "debt_month": r["debt_month"], "sheet_total_vnd": r["sheet_total_vnd"], "source_row": 10} for r in rows],
                                {"legacy_rows": [], "adjustments": adjustments})
        self.assertEqual([(g["kind"], g["month"], g["delta_vnd"], [r["id"] for r in g["rows"]]) for g in groups],
                         [("fee_undo", "2026-09", -6, [2])])


class ChooseTests(unittest.TestCase):
    def group(self, delta, kind="prices"):
        return {"kind": kind, "month": "2026-10", "rows": [], "delta_vnd": delta}

    def test_nothing_to_write(self):
        self.assertEqual(fix.choose([], -5), ("NOTHING_TO_WRITE", []))
        self.assertEqual(fix.choose([self.group(0)], -5), ("NOTHING_TO_WRITE", []))

    def test_exact_combination_only(self):
        a, b, c = self.group(-700), self.group(+5), self.group(-3)
        self.assertEqual(fix.choose([a, b, c], -700), ("FIX", [a]))
        self.assertEqual(fix.choose([a, b, c], -698), ("FIX", [a, b, c]))
        self.assertEqual(fix.choose([a, b, c], -699), ("NO_EXACT_FIX", []))   # lệch 1 đồng cũng không ghi

    def test_two_combinations_are_left_for_the_owner(self):
        self.assertEqual(fix.choose([self.group(-5), self.group(-5)], -5), ("AMBIGUOUS_FIX", []))

    def test_group_without_money_is_never_written(self):
        zero, real = self.group(0), self.group(-9)
        self.assertEqual(fix.choose([zero, real], -9), ("FIX", [real]))

    def test_too_many_groups_are_not_searched(self):
        self.assertEqual(fix.choose([self.group(i + 1) for i in range(fix.MAX_GROUPS + 1)], 3), ("TOO_MANY_GROUPS", []))


class Db:
    def __init__(self, fail=None):
        self.calls, self.version, self.fail = [], 9, fail

    def run(self, function, payload, actor):
        self.calls.append((function, payload, actor))
        if function == "get_ledger":
            return {"version": self.version}
        if function == self.fail:
            raise ApiError(409, "STALE_LEDGER", "x")
        self.version += 1
        return {"version": self.version}

    def writes(self):
        return [c for c in self.calls if c[0] != "get_ledger"]


class ApplyTests(unittest.TestCase):
    LEDGER: ClassVar[dict] = {"version": 9, "today_month": "2026-11-01", "month_locks": []}   # không có cờ: chỉ tháng hiện tại mở

    def test_edited_month_opens_deletes_relocks_then_writes_receipts_and_prices(self):
        db = Db()
        groups = [{"kind": "prices", "month": "2026-11", "rows": [price("READY", month="2026-11")], "delta_vnd": 100},
                  {"kind": "receipts_no_date", "month": "2026-08", "delta_vnd": -500,
                   "rows": [receipt("NO_DATE", 500, source_fingerprint="a" * 64)]},
                  {"kind": "receipts_edited", "month": "2026-07", "delta_vnd": -50, "orphans": [{"id": 5, "amount_vnd": "400"}],
                   "rows": [receipt("SHEET_EDITED", 450, month="2026-07", date="2026-08-02", web_legacy=[])]},
                  {"kind": "fee_rows", "month": "2026-11", "delta_vnd": 43, "rows": [{"source_row": 457, "amount_vnd": "43"}]}]
        done = fix.apply_fix(db, 7, self.LEDGER, groups, "d" * 64, TODAY, actor=AUTO_ACTOR)
        self.assertEqual([(c[0], c[1]["expected_version"]) for c in db.writes()], [
            ("set_month_lock", 9), ("delete_legacy_trip", 10), ("set_month_lock", 11),   # tháng 7 khóa: mở, xóa, khóa lại
            ("record_receipt", 12), ("record_receipt", 13),                              # phiếu thay rồi phiếu không ngày
            ("edit_trip_price", 14),                                                     # tháng 11 đang mở: ghi thẳng
            ("adjust_month", 15)])
        self.assertTrue(all(c[2] == AUTO_ACTOR for c in db.calls))
        self.assertEqual(done, {"receipts": 2, "prices": 1, "legacy_deleted": 1, "fee_rows": 1, "fee_undone": 0})
        adjust = db.writes()[-1][1]
        self.assertEqual((adjust["debt_month"], adjust["amount_vnd"], adjust["note"]), ("2026-11-01", "43", fix.FEE_NOTE + ", dòng 457"))
        records = [c[1] for c in db.writes() if c[0] == "record_receipt"]
        self.assertEqual([(r["date"], r["amount_vnd"], r["method"]) for r in records],
                         [("2026-08-02", "450", "THU TIỀN"), ("2026-08-31", "500", "THU TIỀN")])
        self.assertEqual(records[0]["reference"], "Sheet: da tt")
        self.assertTrue(records[1]["reference"].startswith("Sheet #" + "a" * 64 + ": da tt"))
        keys = [c[1]["idempotency_key"] for c in db.writes()]
        self.assertEqual(len(keys), len(set(keys)))

    def test_undated_receipt_written_by_machine_leaves_the_queue(self):
        rows = [{"customer_tab": "KHACH A", "source_row": 30, "debt_month": "2026-08", "amount_vnd": 500, "note": "da tt"}]
        snapshot = {"rows": rows, "sha256": "e" * 64}
        customers = [{"id": 7, "name": "KHACH A"}]
        ledger = {"customer_id": 7, "version": 9, "legacy_rows": [], "receipts": []}
        queue = project_receipts(snapshot, ledger, customers, TODAY)
        self.assertEqual([r["status"] for r in queue["review"]], ["NO_DATE"])
        db = Db()
        fix.apply_fix(db, 7, ledger, fix.receipt_groups(queue, ledger), "d" * 64, TODAY, actor=AUTO_ACTOR)
        written = db.writes()[0][1]
        ledger["receipts"] = [{"date": written["date"], "amount_vnd": written["amount_vnd"], "reference": written["reference"]}]
        queue = project_receipts(snapshot, ledger, customers, TODAY)
        self.assertEqual((queue["ready"], queue["review"]), ([], []))

    def test_money_row_in_locked_month_opens_writes_relocks(self):
        db = Db()
        fix.apply_fix(db, 7, self.LEDGER, [{"kind": "fee_rows", "month": "2026-10", "delta_vnd": 43,
                                            "rows": [{"source_row": 457, "amount_vnd": "43"}]}], "d" * 64, TODAY, actor=AUTO_ACTOR)
        self.assertEqual([c[0] for c in db.writes()], ["set_month_lock", "adjust_month", "set_month_lock"])

    def test_undo_deletes_machine_adjustment_inside_locked_month(self):
        db = Db()
        done = fix.apply_fix(db, 7, self.LEDGER, [{"kind": "fee_undo", "month": "2026-10", "delta_vnd": -43, "rows": [{"id": 77, "amount_vnd": "43"}]}], "d" * 64, TODAY, actor=AUTO_ACTOR)
        self.assertEqual([c[0] for c in db.writes()], ["set_month_lock", "delete_month_adjustment", "set_month_lock"])
        self.assertEqual(db.writes()[1][1]["adjustment_id"], 77)
        self.assertEqual(done["fee_undone"], 1)

    def test_conflict_rows_go_through_conflict_write_inside_locked_month(self):
        db = Db()
        row = price("CONFLICT", month="2026-10", sheet=("100", "7"), web=("100", None))
        fix.apply_fix(db, 7, self.LEDGER, [{"kind": "prices", "month": "2026-10", "rows": [row], "delta_vnd": 7}], "d" * 64, TODAY, actor=AUTO_ACTOR)
        self.assertEqual([c[0] for c in db.writes()], ["set_month_lock", "edit_trip_price", "set_month_lock"])
        edit = db.writes()[1][1]
        self.assertEqual((edit["trip_id"], edit["unit_price_vnd"], edit["other_fee_vnd"]), (11, "100", "7"))

    def test_write_error_relocks_and_stops(self):
        db = Db(fail="delete_legacy_trip")
        groups = [{"kind": "receipts_edited", "month": "2026-07", "delta_vnd": -50, "orphans": [{"id": 5, "amount_vnd": "400"}],
                   "rows": [receipt("SHEET_EDITED", 450, month="2026-07", date="2026-08-02", web_legacy=[])]}]
        with self.assertRaises(ApiError):
            fix.apply_fix(db, 7, self.LEDGER, groups, "d" * 64, TODAY, actor=AUTO_ACTOR)
        self.assertEqual([(c[0], c[1].get("locked")) for c in db.calls if c[0] != "get_ledger"],
                         [("set_month_lock", False), ("delete_legacy_trip", None), ("set_month_lock", True)])
        self.assertFalse([c for c in db.calls if c[0] == "record_receipt"])

    # Đủ mọi loại lệnh ghi; tháng 7 và 10 đang khóa nên có cả mở/khóa tháng.
    ALL_KINDS: ClassVar[list] = [
        {"kind": "receipts_edited", "month": "2026-07", "delta_vnd": -50, "orphans": [{"id": 5, "amount_vnd": "400"}],
         "rows": [receipt("SHEET_EDITED", 450, month="2026-07", date="2026-08-02", web_legacy=[])]},
        {"kind": "prices", "month": "2026-10", "delta_vnd": 100, "rows": [price("READY", month="2026-10")]},
        {"kind": "fee_rows", "month": "2026-10", "delta_vnd": 43, "rows": [{"source_row": 457, "amount_vnd": "43"}]},
        {"kind": "fee_undo", "month": "2026-10", "delta_vnd": -43, "rows": [{"id": 77, "amount_vnd": "43"}]}]

    def test_manual_call_writes_under_the_person_and_keeps_month_locks_as_machine(self):
        db = Db()
        fix.apply_fix(db, 7, self.LEDGER, self.ALL_KINDS, "d" * 64, TODAY, actor="claude")
        money = [c for c in db.writes() if c[0] != "set_month_lock"]
        self.assertEqual({c[0] for c in money}, {"delete_legacy_trip", "record_receipt", "edit_trip_price", "adjust_month", "delete_month_adjustment"})
        self.assertEqual({c[2] for c in money}, {"claude"})
        self.assertEqual({c[2] for c in db.writes() if c[0] == "set_month_lock"}, {AUTO_ACTOR})   # lượt nền khóa lại được nếu nơi gọi chết

    def test_same_work_keeps_the_same_idempotency_keys_whoever_calls(self):
        machine, person = Db(), Db()
        fix.apply_fix(machine, 7, self.LEDGER, self.ALL_KINDS, "d" * 64, TODAY, actor=AUTO_ACTOR)
        fix.apply_fix(person, 7, self.LEDGER, self.ALL_KINDS, "d" * 64, TODAY, actor="claude")
        self.assertEqual([c[1]["idempotency_key"] for c in machine.writes()], [c[1]["idempotency_key"] for c in person.writes()])

    def test_caller_must_name_the_actor(self):
        with self.assertRaises(TypeError):
            fix.apply_fix(Db(), 7, self.LEDGER, [], "d" * 64, TODAY)


if __name__ == "__main__":
    unittest.main()
