"""DASH-03: get_dashboard_debt — nhóm hạn trả, mức rủi ro, lần trả/đi hàng gần nhất, thu/phát sinh tháng này."""

from __future__ import annotations

import json

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


def _legacy(pg: Pg, customer: int, month: str, kind: str, date: str | None, row: int) -> int:
    cutover = pg.value(f"SELECT cutover_id FROM sokhach.cutover_customer WHERE customer_id={customer}")
    event = pg.value(f"SELECT id FROM sokhach.event WHERE customer_id={customer} AND kind='import'")
    display = json.dumps({"fake": True, "date": date, "pid": f"PH-9{row:02d}" if kind == "receipt" else None})
    return int(pg.value(
        "ALTER TABLE sokhach.legacy_row DISABLE TRIGGER legacy_row_insert_guard; "
        "INSERT INTO sokhach.legacy_row(customer_id,cutover_id,debt_month,kind,display,source_tab,source_row,created_by_event) "
        f"VALUES ({customer},{cutover},{lit(month)},{lit(kind)},{lit(display)}::jsonb,'FAKE-DASH',{row},{event}) RETURNING id; "
        "ALTER TABLE sokhach.legacy_row ENABLE TRIGGER legacy_row_insert_guard"))


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
    _legacy(pg, e, m2, "receipt", f"15/{m2[5:7]}/{m2[:4]}", 1)
    _legacy(pg, e, m1, "receipt", "không rõ", 2)
    deleted = _legacy(pg, e, m0, "receipt", m0, 3)
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
    # Phát sinh: A mở 50 + B chuyến 100 + G số Sheet 120; đã thu: A 10 + B cấn trừ 10 + G Sheet 50.
    delta = (int(month["charges_vnd"]) - int(before["this_month"]["charges_vnd"]),
             int(month["received_vnd"]) - int(before["this_month"]["received_vnd"]))
    require(delta == (270, 70), f"this_month delta: {delta}")
