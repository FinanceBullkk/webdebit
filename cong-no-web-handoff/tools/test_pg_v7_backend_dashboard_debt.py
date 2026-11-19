"""DASH-03: get_dashboard_debt — nhóm hạn trả, mức rủi ro, lần trả/đi hàng gần nhất, thu/phát sinh tháng này; cờ khách mới (KHACH-MOI-01)."""

from __future__ import annotations

import json
from datetime import date, timedelta

from pg_v7_harness import (
    Pg,
    actor_sql,
    call,
    fixture_open_month,
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


def _flow_by_book(pg: Pg, month: str) -> dict[int, tuple[int, int]]:
    """Như _flow nhưng từng sổ, chỉ sổ có số khác 0 — chuẩn để so this_month.customers (DASH-08)."""
    value = pg.value(actor_sql(
        "SELECT coalesce(json_agg(json_build_array(a.id,(m->>'charges_vnd')::bigint,(m->>'received_vnd')::bigint)),'[]')::text "
        f"FROM ({ACTIVE}) a CROSS JOIN LATERAL jsonb_array_elements(sokhach.get_ledger(a.id)->'months') m "
        f"WHERE m->>'month'={lit(month)} AND ((m->>'charges_vnd')::bigint<>0 OR (m->>'received_vnd')::bigint<>0)"))
    return {int(book): (int(charges), int(received)) for book, charges, received in json.loads(value)}


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
                               "no_trip_days": 90, "active_trip_days": 30,
                               "new_days": 90, "new_no_pay_days": 30, "new_unpaid_days": 45}, "rule constants")

    month = result["this_month"]
    require(month["month"] == m0, "this_month is not the current VN month")
    charges, received = _flow(pg, m0)
    require((int(month["charges_vnd"]), int(month["received_vnd"])) == (charges, received),
            f"this_month differs from get_ledger: {month} vs {(charges, received)}")
    # Phát sinh: A mở 50 + B chuyến 100 + G số Sheet 120; đã thu: A 10 + B cấn trừ 10 + G Sheet 50 − E xóa khoản thu 5.
    delta = (int(month["charges_vnd"]) - int(before["this_month"]["charges_vnd"]),
             int(month["received_vnd"]) - int(before["this_month"]["received_vnd"]))
    require(delta == (270, 65), f"this_month delta: {delta}")
    # DASH-08: từng sổ khớp dòng tháng của get_ledger, cộng lại đúng tổng; sổ số 0 không có; mặt hàng lấy theo sổ.
    books = {x["customer_id"]: x for x in month["customers"]}
    require({book: (int(x["charges_vnd"]), int(x["received_vnd"])) for book, x in books.items()} == _flow_by_book(pg, m0),
            f"this_month.customers differs from get_ledger: {month['customers']}")
    require((sum(int(x["charges_vnd"]) for x in books.values()), sum(int(x["received_vnd"]) for x in books.values()))
            == (int(month["charges_vnd"]), int(month["received_vnd"])), "this_month.customers does not add up to the total")
    require([x["customer_id"] for x in month["customers"]] == sorted(books), "this_month.customers is not ordered by id")
    for book, x in books.items():
        if book in rows:
            require((x["commodity"], x["transport_mode"]) == (rows[book]["commodity"], rows[book]["transport_mode"]),
                    f"commodity of book {book}: {x} vs {rows[book]}")

    check_pay_date_rule(pg, m0, m1, m2, _month(pg, 3), m8, today)
    check_new_customer(pg, today)


def check_new_customer(pg: Pg, today: str) -> None:
    """KHACH-MOI-01: sổ mới trong 90 ngày đầu; no_pay sau 30 ngày chưa trả; slow khi chuyến cũ nhất chưa trả đủ quá 45 ngày."""
    now = date.fromisoformat(today)

    def ago(days: int) -> str:
        return (now - timedelta(days=days)).isoformat()

    def trip(book: int, key: str, days: int, price: str | None = "100", booking: str | None = None) -> int:
        day = now - timedelta(days=days)
        month = day.replace(day=1).isoformat()
        fixture_open_month(pg, book, month)
        row = json.loads(trip_json(price, container=f"FAKE-NEW-{key}", month=month))
        row[0]["date"] = day.strftime("%d/%m/%Y")
        if booking is not None:
            row[0]["booking"] = booking
        return call(pg, "paste_trips", book, version(pg, book), f"new-{key}", month, json.dumps(row))["trip_ids"][0]

    def book(key: str, *days: int, price: str | None = "100", opening: tuple[str, int] | None = None) -> int:
        created = new_book(pg, opening or (now.replace(day=1).isoformat(), 0))
        for n, day in enumerate(days):
            trip(created, f"{key}{n}", day, price)
        return created

    def pay(book_id: int, key: str, amount: int) -> dict:
        return call(pg, "record_receipt", book_id, version(pg, book_id), f"new-{key}", today, "THU TIỀN", amount)

    def legacy_pay(book_id: int, days: int, row: int) -> None:
        day = now - timedelta(days=days)
        _legacy(pg, book_id, day.replace(day=1).isoformat(), "receipt", day.strftime("%d/%m/%Y"), row, amount=1000)

    edge90 = book("e90", 90)                 # đúng 90 ngày: còn là sổ mới, đủ 30 ngày chưa trả
    edge91 = book("e91", 91)                 # 91 ngày: hết là sổ mới
    nopay29 = book("n29", 29)
    nopay30 = book("n30", 30)
    voided = book("vd", 35)                  # phiếu đã hủy không tính là đã trả
    pid = pay(voided, "vd-r", 10)["pid"]
    call(pg, "void_receipt", voided, version(pg, voided), "new-vd-void", pid, "nhập nhầm")
    slow46 = book("s46", 60, 46)             # trả đủ chuyến cũ: chuyến 46 ngày còn nợ
    pay(slow46, "s46-r", 100)
    ok45 = book("o45", 60, 45)
    pay(ok45, "o45-r", 100)
    partial = book("pt", 60, 46)             # trả một phần: chuyến 60 ngày còn nợ một nửa
    pay(partial, "pt-r", 50)
    no_price = book("np", 60)                # chuyến chưa giá không tính; dòng thu sổ gốc là đã trả
    trip(no_price, "np1", 50, None)
    legacy_pay(no_price, 58, 31)
    prepay = book("pp", 20)                  # trả trước chuyến đầu quá 7 ngày: có lịch sử, không phải sổ mới
    legacy_pay(prepay, 28, 32)
    near = book("nr", 20)                    # trả trước 7 ngày vẫn là sổ mới
    legacy_pay(near, 27, 33)
    # Chuyến chờ duyệt nằm ngoài số dư nên không dùng để xếp: chuyến 60 ngày vẫn là chuyến chưa trả.
    pending = book("pd", 60)
    legacy_pay(pending, 58, 35)
    cutover = pg.value(f"SELECT cutover_id FROM sokhach.cutover_customer WHERE customer_id={pending}")
    held_day = now - timedelta(days=5)
    pg.sql(f"INSERT INTO sokhach.baseline_trip_ref VALUES ({cutover},'FAKE-BKP','FAKE-NEW-PD1',{lit(held_day.isoformat())})")
    trip(pending, "pd1", 5, booking="FAKE-BKP")
    require(pg.value(f"SELECT count(*) FROM sokhach.v_trip_current WHERE customer_id={pending} AND status='pending_review'") == "1",
            "pending fixture: trip was not held for review")
    # Dòng điều chỉnh của chuyến tính vào chuyến đó: trả 100 đủ chuyến 60 ngày, chuyến 20 ngày tăng lên 150 còn nợ cả.
    adjusted = book("aj", 60)
    late = trip(adjusted, "aj1", 20)
    pay(adjusted, "aj-r", 100)
    call(pg, "adjust_trip", adjusted, version(pg, adjusted), "new-aj-adj", late, 150, "tăng giá")
    require(pg.value(f"SELECT count(*) FROM sokhach.adjustment WHERE trip_id={late}") == "1", "adjustment fixture: no trip adjustment")
    # Nợ mốc từ tháng trước tháng của chuyến đầu: sổ có lịch sử (tách từ khách cũ), không phải sổ mới.
    old_debt = book("od", 20, opening=((now.replace(day=1) - timedelta(days=100)).replace(day=1).isoformat(), 500))
    legacy_only = new_book(pg, (now.replace(day=1).isoformat(), 500))   # dòng sổ gốc nằm trong mốc: nợ là số mốc
    _legacy(pg, legacy_only, now.replace(day=1).isoformat(), "trip", None, 34, amount=500)

    rows = {x["customer_id"]: x for x in call(pg, "get_dashboard_debt")["customers"]}

    def expect(book_id: int, name: str, first: str, is_new: bool, flag: str | None, unpaid: str | None,
               exact: bool = True) -> None:
        row = rows.get(book_id)
        require(row is not None, f"{name}: missing")
        got = (row["first_trip_day"], row["first_trip_exact"], row["is_new"], row["new_flag"], row["oldest_unpaid_trip_day"])
        require(got == (first, exact, is_new, flag, unpaid), f"{name}: {got}")

    expect(edge90, "90 days is new", ago(90), True, "no_pay", ago(90))
    expect(edge91, "91 days is not new", ago(91), False, None, None)
    expect(nopay29, "29 days unpaid", ago(29), True, None, ago(29))
    expect(nopay30, "30 days unpaid", ago(30), True, "no_pay", ago(30))
    expect(voided, "voided receipt", ago(35), True, "no_pay", ago(35))
    expect(slow46, "trip 46 days unpaid", ago(60), True, "slow", ago(46))
    expect(ok45, "trip 45 days unpaid", ago(60), True, None, ago(45))
    expect(partial, "partial payment", ago(60), True, "slow", ago(60))
    expect(no_price, "missing price not counted", ago(60), True, "slow", ago(60))
    expect(prepay, "paid before first trip", ago(20), False, None, None)
    expect(near, "paid within 7 days before", ago(20), True, None, ago(20))
    expect(legacy_only, "undated legacy trip", today, True, None, today, exact=False)
    expect(pending, "pending trip outside the balance", ago(60), True, "slow", ago(60))
    expect(adjusted, "trip adjustment counts on its trip", ago(60), True, None, ago(20))
    expect(old_debt, "opening debt before the first trip", ago(20), False, None, None)
