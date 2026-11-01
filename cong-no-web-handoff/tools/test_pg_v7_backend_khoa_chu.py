"""KHOA-CHU-01 (1/11/2026): tháng khóa vẫn sửa được bốn ô chữ mô tả, có Lịch sử; tiền, ngày, container, xóa vẫn khóa.

Run only through disposable test_pg_v7_backend.py harness."""
import json

from pg_v7_harness import (
    KHOA_CHU_MIGRATION,
    actor_sql,
    call,
    fixture_open_month,
    lit,
    months,
    new_book,
    reject_call,
    require,
    trip_json,
    version,
)

CATALOG = ("SELECT jsonb_object_agg(p.oid::regprocedure::text,pg_get_functiondef(p.oid)) FROM pg_proc p "
           "WHERE p.pronamespace='sokhach'::regnamespace")


def _lock(pg, customer: int, month: str) -> None:
    pg.sql("INSERT INTO sokhach.month_state(customer_id,month,locked,changed_by) "
           f"VALUES ({customer},{lit(month)},true,'harness') "
           "ON CONFLICT (customer_id,month) DO UPDATE SET locked=true,changed_by='harness'")


def _legacy(pg, customer: int, display: dict, row: int) -> int:
    cutover = pg.value(f"SELECT cutover_id FROM sokhach.cutover_customer WHERE customer_id={customer}")
    event = pg.value(f"SELECT id FROM sokhach.event WHERE customer_id={customer} AND kind='import'")
    return int(pg.value("BEGIN; SET LOCAL ROLE sokhach_owner; "
        "ALTER TABLE sokhach.legacy_row DISABLE TRIGGER legacy_row_insert_guard; "
        "INSERT INTO sokhach.legacy_row(customer_id,cutover_id,debt_month,kind,display,source_total_vnd,source_tab,source_row,created_by_event) "
        f"VALUES({customer},{cutover},'2026-01-01','trip',{lit(json.dumps(display))},100,'FAKE',{row},{event}) RETURNING id; "
        "ALTER TABLE sokhach.legacy_row ENABLE TRIGGER legacy_row_insert_guard; COMMIT").splitlines()[0])


def check_khoa_chu(pg) -> str:
    # Migration chỉ thay thân ba hàm: chạy hai lượt trên lược đồ chuẩn không đổi catalog.
    fresh = pg.value(CATALOG)
    migration = KHOA_CHU_MIGRATION.read_text(encoding="utf-8")
    pg.sql(migration)
    pg.sql(migration)
    require(pg.value(CATALOG) == fresh, "khoa-chu migration rerun changed function catalog")

    c = new_book(pg, ("2026-01-01", 100))
    fixture_open_month(pg, c, "2026-01-01")
    row = json.loads(trip_json(container="KC-1"))[0]
    trip = call(pg, "paste_trips", c, version(pg, c), "kc-paste", "2026-01-01", json.dumps([row]))["trip_ids"][0]
    legacy = _legacy(pg, c, {"container": "KC-L", "date": "2026-01-05", "from": "KHO A", "to": "CANG B",
                             "carrier": "HT", "unit_price": "100"}, 31)
    _lock(pg, c, "2026-01-01")
    before = months(pg, c)

    # 1. Chuyến web, tháng khóa: bốn ô chữ sửa được, có Lịch sử trước → sau.
    for n, (field, value) in enumerate((("carrier", "HT2"), ("shipper", "SHIP"), ("origin", "KHO C"), ("destination", "CANG D"))):
        call(pg, "edit_trip_info", c, version(pg, c), f"kc-trip-{n}", trip, field, value)
    event = json.loads(pg.value(f"SELECT jsonb_build_object('before',\"before\",'after',\"after\") FROM sokhach.event "
                                f"WHERE customer_id={c} AND kind='trip_edit' ORDER BY id DESC LIMIT 1"))
    require(event["after"]["trip"]["field"] == "destination" and event["after"]["trip"]["value"] == "CANG D"
            and event["before"]["trip"]["value"] == "FAKE-B", f"trip text edit audit wrong: {event}")
    current = next(t for t in call(pg, "get_ledger", c)["trips"] if t["id"] == trip)
    require((current["carrier"], current["shipper"], current["origin"], current["destination"]) == ("HT2", "SHIP", "KHO C", "CANG D"),
            "locked-month text edits not visible")
    # Container và ngày vẫn theo khóa tháng.
    reject_call(pg, "edit_trip_info", c, version(pg, c), "kc-trip-container", trip, "container", "KC-2", error="MONTH_LOCKED")
    reject_call(pg, "edit_trip_info", c, version(pg, c), "kc-trip-date", trip, "event_date", "2026-01-09", error="MONTH_LOCKED")

    # 2. Dòng sổ gốc, tháng khóa: ô chữ sửa được; tiền, ngày, container, xóa vẫn khóa.
    call(pg, "edit_legacy_trip", c, version(pg, c), "kc-legacy-origin", legacy, "origin", "KHO E")
    for field, value in (("unit_price_vnd", "120"), ("other_fee_vnd", "5"), ("event_date", "2026-01-06"), ("container", "KC-L2")):
        reject_call(pg, "edit_legacy_trip", c, version(pg, c), f"kc-legacy-{field}", legacy, field, value, error="MONTH_LOCKED")
    reject_call(pg, "delete_legacy_trip", c, version(pg, c), "kc-legacy-delete", legacy, error="MONTH_LOCKED")

    # 3. Lấy theo Sheet (giải quyết lệch) cho ô chữ ở tháng khóa: được, ghi event với quyết định.
    sha = "d" * 64
    call(pg, "resolve_sheet_conflict", c, version(pg, c), "kc-resolve", sha, 7, "legacy", legacy, "destination",
         "CANG B", "CANG F", "use_sheet")
    resolved = json.loads(pg.value(f"SELECT \"after\" FROM sokhach.event WHERE customer_id={c} AND kind='sheet_conflict_resolved' "
                                   "ORDER BY id DESC LIMIT 1"))
    require(resolved["decision"] == "use_sheet" and resolved["target_value"] == "CANG F", f"resolve audit wrong: {resolved}")
    cur = json.loads(pg.value(actor_sql(f"SELECT sokhach._legacy_current({legacy})")))
    require((cur["origin"], cur["destination"]) == ("KHO E", "CANG F"), f"legacy text not updated: {cur}")

    # 4. Không đổi số dư; tháng vẫn khóa.
    require(months(pg, c) == before, "text edits changed month totals")
    pg.true(f"(SELECT locked FROM sokhach.month_state WHERE customer_id={c} AND month='2026-01-01')", "month unlocked")
    return "locked month: four text fields editable (trip, legacy, use_sheet) with audit; money, date, container, delete still locked"
