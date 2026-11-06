"""DASH-03: get_dashboard_debt — nhóm hạn trả, mức rủi ro, lần trả/đi hàng gần nhất, thu/phát sinh tháng này."""

from __future__ import annotations

import json
from datetime import date, timedelta

from pg_v7_harness import (
    Pg,
    actor_sql,
    call,
    lit,
    new_book,
    require,
    trip_json,
    version,
)

TIERS = ["not_due", "due_this_month", "late_1_2", "late_3_6", "late_over_6"]
ACTIVE = ("SELECT c.id FROM sokhach.customer c JOIN sokhach.cutover_customer cc ON cc.customer_id=c.id AND cc.status='active' "
          "JOIN sokhach.cutover x ON x.id=cc.cutover_id AND x.status='active' WHERE NOT c.archived")


def _month(pg: Pg, back: int) -> str:
    return pg.value(f"SELECT (date_trunc('month',now() AT TIME ZONE 'Asia/Ho_Chi_Minh')-interval '{back} months')::date")


def _legacy(pg: Pg, customer: int, month: str, kind: str, date: str | None, row: int,
            *, raw: str | None = None, amount: int | None = None) -> int:
    cutover = pg.value(f"SELECT cutover_id FROM sokhach.cutover_customer WHERE customer_id={customer}")
    event = pg.value(f"SELECT id FROM sokhach.event WHERE customer_id={customer} AND kind='import'")
    display = json.dumps({"fake": True, "date": date, "raw_date": raw, "pid": f"PH-9{row:02d}" if kind == "receipt" else None})
    total = "NULL" if amount is None else amount
    return int(pg.value(
        "ALTER TABLE sokhach.legacy_row DISABLE TRIGGER legacy_row_insert_guard; "
        "INSERT INTO sokhach.legacy_row(customer_id,cutover_id,debt_month,kind,display,source_total_vnd,source_tab,source_row,created_by_event) "
        f"VALUES ({customer},{cutover},{lit(month)},{lit(kind)},{lit(display)}::jsonb,{total},'FAKE-DASH',{row},{event}) RETURNING id; "
        "ALTER TABLE sokhach.legacy_row ENABLE TRIGGER legacy_row_insert_guard"))


def _month_end(pg: Pg, month: str) -> str:
    return pg.value(f"SELECT ({lit(month)}::date+interval '1 month')::date-1")


def check_pay_date_rule(pg: Pg, m0: str, m1: str, m2: str, m3: str, m8: str, today: str) -> None:
    """Ngày trả là ngày tiền về thật, cùng luật ngày với get_receipt_book; ngưỡng 60 ngày đọc theo ngày đó."""
    now = date.fromisoformat(today)

    def ago(days: int) -> str:
        return (now - timedelta(days=days)).isoformat()

    def vn(day: str) -> str:
        return f"{day[8:10]}/{day[5:7]}/{day[:4]}"

    def overdue_active(key: str) -> int:
        """Quá hạn 1–2 tháng, vẫn đi hàng: nhãn chỉ còn phụ thuộc số ngày chưa trả."""
        book = new_book(pg, (m2, 100))
        call(pg, "paste_trips", book, version(pg, book), f"dash3-{key}-trip", m0, trip_json(month=m0, container=f"FAKE-DASH-{key}"))
        return book

    serial = str((now - timedelta(days=10) - date(1899, 12, 30)).days)
    # Khối tháng cũ, tiền về 10 ngày trước (số serial Excel): cuối tháng khối thì quá 60 ngày, ngày thật thì không.
    recent_cash = overdue_active("h")
    _legacy(pg, recent_cash, m8, "receipt", None, 11, raw=serial, amount=1000)
    # Khối tháng trước, tiền về 70 ngày trước: cuối tháng khối thì chưa quá 60 ngày, ngày thật thì quá.
    old_cash = overdue_active("i")
    _legacy(pg, old_cash, m1, "receipt", None, 12, raw=f"CK {vn(ago(70))} VCB", amount=1000)
    # Ngày ngoài khoảng nhận: trước tháng nợ hơn 12 tháng; sau lúc nạp sổ dù chưa qua hôm nay (Sheet đảo ngày tháng).
    too_old = overdue_active("j")
    _legacy(pg, too_old, m1, "receipt", None, 13, raw="01/01/2020 tt", amount=1000)
    after_load = overdue_active("k")
    _legacy(pg, after_load, m2, "receipt", None, 14, raw=vn(ago(2)), amount=1000)
    pg.sql("ALTER TABLE sokhach.cutover DISABLE TRIGGER cutover_status_guard; "
           "UPDATE sokhach.cutover SET frozen_at=now()-interval '5 days' WHERE id="
           f"(SELECT cutover_id FROM sokhach.cutover_customer WHERE customer_id={after_load}); "
           "ALTER TABLE sokhach.cutover ENABLE TRIGGER cutover_status_guard")
    # display.date đọc trước raw_date.
    both = overdue_active("l")
    _legacy(pg, both, m2, "receipt", vn(ago(20)), 15, raw=vn(ago(5)), amount=1000)
    # Dòng số tiền 0 hay trống không phải khoản thu, dù ghi ngày mới hơn.
    zero = overdue_active("m")
    _legacy(pg, zero, m2, "receipt", None, 16, raw=vn(ago(20)), amount=1000)
    _legacy(pg, zero, m0, "receipt", None, 17, raw=today, amount=0)
    _legacy(pg, zero, m1, "receipt", None, 18, raw=vn(ago(1)))
    # Ngày thật muộn hơn ngày tạm của khối cũ thì lấy ngày thật.
    real_wins = overdue_active("n")
    _legacy(pg, real_wins, m3, "receipt", None, 19, raw="da tt", amount=1000)
    _legacy(pg, real_wins, m3, "receipt", None, 20, raw=vn(ago(5)), amount=1000)
    # Phiếu web đuôi ngày tạm: giữ ngày phiếu, không rõ ngày; vượt ngày thật cũ hơn; bằng ngày thì dòng rõ ngày thắng.
    symbolic = []
    for key, tail in (("p", " (ngày tượng trưng)"), ("q", " · ngày theo cuối tháng khối Sheet")):
        book = overdue_active(key)
        call(pg, "record_receipt", book, version(pg, book), f"dash3-{key}-r", today, "THU TIỀN", 10, f"Sheet: da tt{tail}")
        _legacy(pg, book, m2, "receipt", None, 21, raw=vn(ago(5)), amount=1000)
        symbolic.append(book)
    tie = overdue_active("r")
    call(pg, "record_receipt", tie, version(pg, tie), "dash3-r-1", today, "THU TIỀN", 10, "CK (ngày tượng trưng)")
    call(pg, "record_receipt", tie, version(pg, tie), "dash3-r-2", today, "THU TIỀN", 10, "CK ngân hàng")

    rows = {x["customer_id"]: x for x in call(pg, "get_dashboard_debt")["customers"]}

    def expect(book: int, name: str, day: str, exact: bool, risk: str) -> None:
        row = rows[book]
        days = max((now - date.fromisoformat(day)).days, 0)
        require((row["last_receipt_date"], row["last_receipt_exact"], row["pay_days"], row["risk"]) == (day, exact, days, risk),
                f"{name}: {row}")

    expect(recent_cash, "real date beats old block", ago(10), True, "watch")
    expect(old_cash, "real date older than block month", ago(70), True, "high")
    expect(too_old, "date over 12 months before block", _month_end(pg, m1), False, "watch")
    m2_end_age = (now - date.fromisoformat(_month_end(pg, m2))).days
    expect(after_load, "date after load", _month_end(pg, m2), False, "high" if m2_end_age > 60 else "watch")
    expect(both, "display date first", ago(20), True, "watch")
    expect(zero, "zero or blank amount is not a payment", ago(20), True, "watch")
    expect(real_wins, "real date later than placeholder", ago(5), True, "watch")
    for book in symbolic:
        expect(book, "placeholder web date", today, False, "watch")
    expect(tie, "same day prefers the exact receipt", today, True, "watch")


def _flow(pg: Pg, month: str) -> tuple[int, int]:
    """Dòng Tổng tháng của get_ledger cộng qua mọi sổ đang hoạt động — chuẩn để so."""
    value = pg.value(actor_sql(
        "SELECT json_build_array(coalesce(sum((m->>'charges_vnd')::bigint),0),coalesce(sum((m->>'received_vnd')::bigint),0))::text "
        f"FROM ({ACTIVE}) a CROSS JOIN LATERAL jsonb_array_elements(sokhach.get_ledger(a.id)->'months') m "
        f"WHERE m->>'month'={lit(month)}"))
    charges, received = json.loads(value)
    return int(charges), int(received)


def check_dashboard_debt(pg: Pg) -> None:
    m0, m1, m2, m4, m8 = (_month(pg, n) for n in (0, 1, 2, 4, 8))
    today = pg.value("SELECT (now() AT TIME ZONE 'Asia/Ho_Chi_Minh')::date")
    before = call(pg, "get_dashboard_debt")
    # A: trả hôm nay nhưng còn nợ quá hạn từ 3 tháng → rủi ro cao. Phiếu trừ nợ cũ trước: m8 còn 90.
    a = new_book(pg, (m8, 100), (m2, 200), (m0, 50))
    call(pg, "record_receipt", a, version(pg, a), "dash3-a", today, "THU TIỀN", 10)
    # B: quá hạn 1–2 tháng, vừa trả, vẫn đi hàng → theo dõi.
    b = new_book(pg, (m2, 300), (m1, 100))
    call(pg, "record_receipt", b, version(pg, b), "dash3-b", today, "CẤN TRỪ", 10)
    call(pg, "paste_trips", b, version(pg, b), "dash3-b-trip", m0, trip_json(month=m0, container="FAKE-DASH-B"))
    # C: quá hạn 1–2 và 3–6 tháng, chưa trả lần nào, chưa có chuyến → rủi ro cao.
    c = new_book(pg, (m4, 40), (m2, 100))
    # D: chỉ nợ tháng trước (đến hạn cuối tháng này) → trong hạn.
    d = new_book(pg, (m1, 100))
    # E: dòng sổ gốc — ngày hợp lệ, ô ngày sai (lấy cuối tháng), dòng đã xóa không tính.
    e = new_book(pg, (m2, 100))
    _legacy(pg, e, m2, "receipt", f"15/{m2[5:7]}/{m2[:4]}", 1, amount=1000)
    _legacy(pg, e, m1, "receipt", "không rõ", 2, amount=1000)
    deleted = _legacy(pg, e, m0, "receipt", m0, 3, amount=5)
    _legacy(pg, e, m2, "trip", f"{m2[:8]}20", 4)
    call(pg, "delete_legacy_trip", e, version(pg, e), "dash3-e-del", deleted)
    # G: tháng này có số Sheet trong mốc → phát sinh/đã thu lấy số Sheet như get_ledger (DA-THU-01).
    g = new_book(pg, (m0, 70))
    cutover = pg.value(f"SELECT cutover_id FROM sokhach.cutover_customer WHERE customer_id={g}")
    pg.sql("ALTER TABLE sokhach.cutover_month_check DISABLE TRIGGER cutover_month_check_guard; "
           "INSERT INTO sokhach.cutover_month_check(customer_id,cutover_id,debt_month,source_charge_vnd,source_receipt_vnd) "
           f"VALUES ({g},{cutover},{lit(m0)},120,50); "
           "ALTER TABLE sokhach.cutover_month_check ENABLE TRIGGER cutover_month_check_guard")

    result = call(pg, "get_dashboard_debt")
    dash = call(pg, "get_dashboard")
    receivable = int(result["receivable_vnd"])
    require(receivable == int(dash["receivable"]["total_vnd"]), "debt receivable differs from get_dashboard")
    require([x["tier"] for x in result["due_tiers"]] == TIERS, "due tier order")
    require(sum(int(x["receivable_vnd"]) for x in result["due_tiers"]) == receivable, "due tiers do not add up")
    rows = {x["customer_id"]: x for x in result["customers"]}
    require(len(rows) == dash["receivable"]["customers"], "debt customers differ from get_dashboard")
    require(sum(int(x["outstanding_vnd"]) for x in rows.values()) == receivable, "customer totals do not add up")
    for x in rows.values():
        tiers = [int(v) for v in x["tiers_vnd"]]
        require(sum(tiers) == int(x["outstanding_vnd"]) and int(x["overdue_vnd"]) == sum(tiers[2:])
                and int(x["long_overdue_vnd"]) == sum(tiers[3:]), f"customer {x['customer_id']} tier split")
    order = [(-int(x["overdue_vnd"]), -int(x["outstanding_vnd"])) for x in result["customers"]]
    require(order == sorted(order), "customers not ordered by overdue then total")

    def row(customer: int) -> dict:
        require(customer in rows, f"customer {customer} missing from debt overview")
        return rows[customer]

    require(row(a)["tiers_vnd"] == ["50", "0", "200", "0", "90"] and row(a)["risk"] == "high"
            and row(a)["last_receipt_date"] == today and row(a)["last_receipt_exact"] is True and row(a)["pay_days"] == 0
            and row(a)["oldest_open_month"] == m8, f"A: {row(a)}")
    require(row(b)["tiers_vnd"] == ["100", "100", "290", "0", "0"] and row(b)["risk"] == "watch"
            and row(b)["last_receipt_date"] == today and row(b)["last_trip_date"] == m0
            and row(b)["last_trip_exact"] is True, f"B: {row(b)}")
    require(row(c)["tiers_vnd"] == ["0", "0", "100", "40", "0"] and row(c)["long_overdue_vnd"] == "40"
            and row(c)["risk"] == "high" and row(c)["last_receipt_date"] is None and row(c)["pay_days"] is None
            and row(c)["last_trip_date"] is None and row(c)["trip_days"] is None, f"C: {row(c)}")
    require(row(d)["tiers_vnd"] == ["0", "100", "0", "0", "0"] and row(d)["risk"] == "ok", f"D: {row(d)}")
    m1_end = pg.value(f"SELECT ({lit(m1)}::date+interval '1 month')::date-1")
    require(row(e)["last_receipt_date"] == m1_end and row(e)["last_receipt_exact"] is False
            and row(e)["last_trip_date"] == f"{m2[:8]}20" and row(e)["last_trip_exact"] is True
            and row(e)["risk"] == "watch", f"E: {row(e)}")
    require(row(g)["months"] == [{"month": m0, "outstanding_vnd": "70"}], f"G months: {row(g)}")

    summary = result["summary"]
    require(int(summary["overdue_vnd"]) == sum(int(x["overdue_vnd"]) for x in rows.values())
            and int(summary["long_overdue_vnd"]) == sum(int(x["long_overdue_vnd"]) for x in rows.values())
            and summary["overdue_customers"] == sum(int(x["overdue_vnd"]) > 0 for x in rows.values())
            and summary["high_customers"] == sum(x["risk"] == "high" for x in rows.values())
            and int(summary["high_overdue_vnd"]) == sum(int(x["overdue_vnd"]) for x in rows.values() if x["risk"] == "high"),
            "summary does not match customers")
    require(result["rule"] == {"due_after_months": 1, "long_overdue_months": 3, "no_pay_days": 60,
                               "no_trip_days": 90, "active_trip_days": 30}, "rule constants")

    month = result["this_month"]
    require(month["month"] == m0, "this_month is not the current VN month")
    charges, received = _flow(pg, m0)
    require((int(month["charges_vnd"]), int(month["received_vnd"])) == (charges, received),
            f"this_month differs from get_ledger: {month} vs {(charges, received)}")
    # Phát sinh: A mở 50 + B chuyến 100 + G số Sheet 120; đã thu: A 10 + B cấn trừ 10 + G Sheet 50 − E xóa khoản thu 5.
    delta = (int(month["charges_vnd"]) - int(before["this_month"]["charges_vnd"]),
             int(month["received_vnd"]) - int(before["this_month"]["received_vnd"]))
    require(delta == (270, 65), f"this_month delta: {delta}")

    check_pay_date_rule(pg, m0, m1, m2, _month(pg, 3), m8, today)
