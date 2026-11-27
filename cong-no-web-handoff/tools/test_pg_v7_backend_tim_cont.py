"""Tìm chuyến theo số cont (TIM-CONT-01) và khách theo tháng (KHACH-THANG-01), specs/v7-tim-cont-khach-thang.md.

Chỉ chạy qua harness V7 dùng một lần (test_pg_v7_backend.py), dữ liệu giả. Hai hàm chỉ đọc: không đổi version sổ."""
import json

from pg_v7_harness import (
    call,
    fixture_open_month,
    lit,
    new_book,
    reject_call,
    require,
    trip_json,
    version,
)

CURRENT = "SELECT date_trunc('month',(now() AT TIME ZONE 'Asia/Ho_Chi_Minh'))::date::text"


def _legacy_trip(pg, customer: int, month: str, container: str, row: int) -> int:
    """Dòng chuyến sổ gốc giả, chèn như ca chặn trùng (tắt trigger chặn chèn trong một giao dịch)."""
    cutover = pg.value(f"SELECT cutover_id FROM sokhach.cutover_customer WHERE customer_id={customer}")
    event = pg.value(f"SELECT id FROM sokhach.event WHERE customer_id={customer} AND kind='import'")
    display = json.dumps({"container": container, "date": f"05/{month[5:7]}/{month[:4]}", "from": "FAKE-A", "to": "FAKE-B"})
    return int(pg.value("BEGIN; SET LOCAL ROLE sokhach_owner; "
        "ALTER TABLE sokhach.legacy_row DISABLE TRIGGER legacy_row_insert_guard; "
        "INSERT INTO sokhach.legacy_row(customer_id,cutover_id,debt_month,kind,display,source_total_vnd,source_tab,source_row,created_by_event) "
        f"VALUES({customer},{cutover},{lit(month)},'trip',{lit(display)},50,'FAKE',{row},{event}) RETURNING id; "
        "ALTER TABLE sokhach.legacy_row ENABLE TRIGGER legacy_row_insert_guard; COMMIT").splitlines()[0])


def _paste(pg, customer: int, key: str, container: str, month: str) -> int:
    return call(pg, "paste_trips", customer, version(pg, customer), key, month, trip_json(container=container, month=month))["trip_ids"][0]


def check_tim_cont(pg) -> None:
    a = new_book(pg, ("2026-01-01", 1000))
    b = new_book(pg, ("2026-01-01", 500))
    for book in (a, b):
        fixture_open_month(pg, book, "2026-02-01")
    web = _paste(pg, a, "tc-web", "FAKE-TCX-1001", "2026-02-01")
    gone = _paste(pg, a, "tc-gone", "FAKE-TCX-1009", "2026-02-01")
    call(pg, "delete_trip", a, version(pg, a), "tc-del", gone)
    _paste(pg, b, "tc-other", "FAKE-TCX-1002", "2026-02-01")
    c = new_book(pg, ("2026-01-01", 0))   # sổ riêng cho dòng sổ gốc: không đụng số tháng 1 của a, b
    _legacy_trip(pg, c, "2026-01-01", "fake-tcx 2002", 901)

    body = call(pg, "find_container", "tcx-100")
    require(body["query"] == "TCX-100" and body["more"] is False, f"query normalised, no overflow: {body}")
    found = {(item["customer_id"], item["container"], item["source"]) for item in body["items"]}
    require(found == {(a, "FAKE-TCX-1001", "web"), (b, "FAKE-TCX-1002", "web")}, f"web trips of every book, deleted trip left out: {found}")
    item = next(item for item in body["items"] if item["container"] == "FAKE-TCX-1001")
    require(item["debt_month"] == "2026-02-01" and item["date"] == "2026-02-01" and item["origin"] == "FAKE-A" and item["destination"] == "FAKE-B",
            f"trip fields: {item}")

    # Dòng chuyến sổ gốc: so sau khi bỏ khoảng trắng và không phân biệt hoa thường; nguyên số đứng trước.
    legacy = call(pg, "find_container", " Fake-TCX 2002 ")["items"]
    require([(row["customer_id"], row["source"], row["debt_month"], row["date"]) for row in legacy] == [(c, "legacy", "2026-01-01", "2026-01-05")],
            f"legacy trip: {legacy}")
    mixed = call(pg, "find_container", "FAKE-TCX")["items"]
    require(len(mixed) == 3, f"three live trips contain TCX: {mixed}")
    exact = call(pg, "find_container", "FAKE-TCX-1002")["items"]
    require(exact[0]["container"] == "FAKE-TCX-1002", f"exact match first: {exact}")

    # Sửa số cont: tìm theo số mới thấy chuyến, số cũ không còn.
    call(pg, "edit_trip_info", a, version(pg, a), "tc-edit", web, "container", "FAKE-TCX-7007")
    require([row["container"] for row in call(pg, "find_container", "TCX-7007")["items"]] == ["FAKE-TCX-7007"], "edited container found")
    require(not call(pg, "find_container", "TCX-1001")["items"], "old container no longer matches")

    for bad in ("TCX", "   ", "A" * 21):
        reject_call(pg, "find_container", bad, error="INVALID_QUERY")
    reject_call(pg, "get_month_customers", "2026-02-15", error="INVALID_MONTH")
    before = (version(pg, a), version(pg, b), version(pg, c))
    call(pg, "find_container", "FAKE-TCX")
    call(pg, "get_month_customers", "2026-01-01")
    require((version(pg, a), version(pg, b), version(pg, c)) == before, "reads must not change book versions")
    check_khach_thang(pg, a, b)


def check_khach_thang(pg, a: int, b: int) -> None:
    current = pg.value(CURRENT)
    fixture_open_month(pg, a, current)
    trip = _paste(pg, a, "kt-trip", "FAKE-KT-1", current)
    call(pg, "edit_trip_price", a, version(pg, a), "kt-price", trip, 250, None)
    today = pg.value("SELECT (now() AT TIME ZONE 'Asia/Ho_Chi_Minh')::date::text")
    call(pg, "record_receipt", b, version(pg, b), "kt-thu", today, "THU TIỀN", 300, None)

    # Tháng hiện tại (tham số trống) cộng đúng như thẻ Thu tháng của Tổng quan.
    body = call(pg, "get_month_customers", None)
    require(body["month"] == current, f"default month: {body['month']}")
    rows = {row["customer_id"]: row for row in body["customers"]}
    require(rows[a]["charges_vnd"] == "250" and rows[a]["received_vnd"] == "0" and rows[a]["outstanding_vnd"] == "250", f"book a: {rows[a]}")
    require(rows[b]["charges_vnd"] == "0" and rows[b]["received_vnd"] == "300" and rows[b]["outstanding_vnd"] == "0", f"book b: {rows[b]}")
    flow = {row["customer_id"]: (row["charges_vnd"], row["received_vnd"]) for row in call(pg, "get_dashboard_debt")["this_month"]["customers"]}
    mine = {cid: (row["charges_vnd"], row["received_vnd"]) for cid, row in rows.items() if row["charges_vnd"] != "0" or row["received_vnd"] != "0"}
    require(mine == flow, f"same numbers as get_dashboard_debt.this_month: {mine} vs {flow}")
    require(body["charges_vnd"] == str(sum(int(row["charges_vnd"]) for row in body["customers"])), "charges total")

    # Tháng cũ: số dư đầu là phát sinh; còn nợ của tháng sau khi thu (nợ cũ trước), như ma trận Công nợ theo tháng.
    jan = {row["customer_id"]: row for row in call(pg, "get_month_customers", "2026-01-01")["customers"]}
    require((jan[a]["charges_vnd"], jan[a]["outstanding_vnd"]) == ("1000", "1000"), f"book a January: {jan[a]}")
    require((jan[b]["charges_vnd"], jan[b]["received_vnd"], jan[b]["outstanding_vnd"]) == ("500", "0", "200"), f"book b January: {jan[b]}")
    # Cùng nguồn với ô ma trận (get_receivables_matrix cộng v_outstanding_month). Không gọi chính ma trận: DB harness dùng chung có
    # ca số rất lớn ở sổ khác làm tổng của ma trận tràn bigint.
    view = pg.value("SELECT string_agg(customer_id||'='||outstanding_vnd,',' ORDER BY customer_id) FROM sokhach.v_outstanding_month "
                    f"WHERE customer_id IN ({a},{b}) AND debt_month='2026-01-01'")
    require(view == f"{a}=1000,{b}=200", f"January outstanding equals v_outstanding_month: {view}")
    empty = call(pg, "get_month_customers", "2001-01-01")
    require(empty["customers"] == [] and empty["charges_vnd"] == "0", f"empty month: {empty}")
