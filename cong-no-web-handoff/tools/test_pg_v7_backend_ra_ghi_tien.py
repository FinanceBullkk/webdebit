"""Rà đường ghi tiền 29/10/2026 (FUTURE-01 áp V7, V7-SO phiếu mới phân bổ lại, BANG-GIA-01 gõ tay thắng bảng).

Run only through disposable test_pg_v7_backend.py harness."""
import json

from pg_v7_harness import (
    CAN_DU_MIGRATION,
    RA_GHI_TIEN_MIGRATION,
    actor_sql,
    allocations,
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


def _vn(pg, sql: str) -> str:
    return pg.value(sql.replace("TODAY", "(clock_timestamp() AT TIME ZONE 'Asia/Ho_Chi_Minh')::date"))


def check_ra_ghi_tien(pg) -> str:
    # Migration chỉ thay thân hàm: chạy hai lượt trên lược đồ chuẩn không đổi catalog.
    fresh = pg.value(CATALOG)
    migration = RA_GHI_TIEN_MIGRATION.read_text(encoding="utf-8")
    pg.sql(migration)
    pg.sql(migration)
    pg.sql(CAN_DU_MIGRATION.read_text(encoding="utf-8"))  # CAN-DU-01 thay record_receipt sau bản 29/10
    require(pg.value(CATALOG) == fresh, "ra-ghi-tien migration rerun changed function catalog")
    pg.true("EXISTS (SELECT 1 FROM pg_trigger WHERE tgrelid='sokhach.trip'::regclass AND tgname='trip_sheet_cross_customer')",
            "sheet cross-customer trigger missing from canonical schema")
    for name, allowed in (("list_sheet_trip_refs", True), ("resolve_sheet_conflict", True), ("guard_sheet_cross_customer", False)):
        require(pg.value(f"SELECT bool_and(has_function_privilege('v7_app',oid,'EXECUTE')) FROM pg_proc "
                         f"WHERE pronamespace='sokhach'::regnamespace AND proname={lit(name)}") == ("t" if allowed else "f"),
                f"{name} EXECUTE grant for app wrong")

    # 1. FUTURE-01 áp vào V7: dán chuyến có ngày xe nhập kho sau hôm nay (giờ VN) bị từ chối, sổ không đổi.
    c = new_book(pg, ("2026-01-01", 100))
    current = _vn(pg, "SELECT date_trunc('month',TODAY)::date")
    today = _vn(pg, "SELECT to_char(TODAY,'DD/MM/YYYY')")
    tomorrow = _vn(pg, "SELECT to_char(TODAY+1,'DD/MM/YYYY')")
    row = json.loads(trip_json(container="FUTURE-C"))[0]
    row["date"] = tomorrow
    before = call(pg, "get_ledger", c)
    reject_call(pg, "paste_trips", c, 0, "future-paste", current, json.dumps([row]), error="FUTURE_DATE")
    require(call(pg, "get_ledger", c) == before and version(pg, c) == 0, "future paste changed ledger or version")
    row["date"] = today
    pasted = call(pg, "paste_trips", c, 0, "today-paste", current, json.dumps([row]))
    require(len(pasted["trip_ids"]) == 1 and not pasted["pending_review"], "today paste rejected")
    definition = pg.value("SELECT pg_get_functiondef(oid) FROM pg_proc WHERE pronamespace='sokhach'::regnamespace AND proname='paste_trips'")
    require(definition.index("_begin_command") < definition.index("clock_timestamp()"), "paste_trips reads clock before customer lock")

    # 2. V7-SO: phiếu ghi sau nhưng ngày sớm hơn được xếp trước; dòng phân bổ đã lưu là kết quả chuẩn.
    c2 = new_book(pg, ("2026-01-01", 100), ("2026-02-01", 100))
    late = call(pg, "record_receipt", c2, 0, "ra-late", "2026-01-10", "THU TIỀN", 100)
    require(allocations(pg, c2, late["pid"]) == [("2026-01-01", "debt", "100")], "first receipt allocation")
    early = call(pg, "record_receipt", c2, 1, "ra-early", "2026-01-05", "THU TIỀN", 100)
    require(allocations(pg, c2, early["pid"]) == [("2026-01-01", "debt", "100")]
            and allocations(pg, c2, late["pid"]) == [("2026-02-01", "debt", "100")],
            "earlier-dated receipt did not take the older month")
    require([(x["month"], x["kind"], x["amount_vnd"]) for x in early["allocations"]] == [("2026-01-01", "debt", "100")],
            "record_receipt result allocations not final")
    # Phiếu mới xếp tạm theo nợ còn lại rồi phân bổ lại cùng mọi phiếu: cả hai phiếu đổi dòng.
    require(sorted(x["pid"] for x in early["reallocated"]) == sorted([early["pid"], late["pid"]]),
            "record_receipt did not report the moved receipts")
    require([m[1] for m in months(pg, c2)] == ["0", "0"], "month totals changed by receipt order")
    require(json.loads(pg.value(actor_sql(f"SELECT sokhach.reallocate({c2},'ra-check')"))) == [],
            "a later reallocation still moved lines: stored allocation was not canonical")
    require(call(pg, "record_receipt", c2, 1, "ra-early", "2026-01-05", "THU TIỀN", 100) == early, "receipt retry changed")

    # 3. BANG-GIA-01: đơn giá gõ tay không bị bảng giá ghi đè; chuyến chưa có giá và giá do bảng ghi vẫn áp được.
    c3 = new_book(pg, ("2026-01-01", 0))
    fixture_open_month(pg, c3, "2026-01-01")
    rows = []
    for container, price in (("TYPED", "100"), ("EMPTY", None)):
        item = json.loads(trip_json(price, container=container))[0]
        item.update(date="10/01/2026", **{"from": "DAK LAK"})
        rows.append(item)
    typed, empty = call(pg, "paste_trips", c3, version(pg, c3), "price-paste", "2026-01-01", json.dumps(rows))["trip_ids"]

    def table(price):
        return json.dumps({"tt_shippers": [], "locations": [{"name": "DAK LAK"}],
                           "periods": [{"valid_from": "2026-01-01", "valid_to": None,
                                        "rates": [{"location": "DAK LAK", "tier": "khach", "unit_price_vnd": price}]}]})
    call(pg, "save_price_table", c3, version(pg, c3), "price-table-1", table("75"))
    v = version(pg, c3)
    before = call(pg, "get_ledger", c3)
    reject_call(pg, "apply_price_table", c3, v, "apply-typed", json.dumps([typed]), error="PRICE_TYPED_PRICE")
    reject_call(pg, "apply_price_table", c3, v, "apply-mixed", json.dumps([empty, typed]), error="PRICE_TYPED_PRICE")
    require(call(pg, "get_ledger", c3) == before and version(pg, c3) == v, "typed-price rejection changed ledger")
    pg.true(f"NOT EXISTS (SELECT 1 FROM sokhach.trip_price_source WHERE customer_id={c3})", "rejected apply wrote a source")
    call(pg, "apply_price_table", c3, v, "apply-empty", json.dumps([empty]))

    def price_of(trip_id):
        return next(t for t in call(pg, "get_ledger", c3)["trips"] if t["id"] == trip_id)["unit_price_vnd"]
    require(price_of(empty) == "75" and price_of(typed) == "100", "apply changed the typed trip or skipped the empty one")
    call(pg, "save_price_table", c3, version(pg, c3), "price-table-2", table("80"))
    call(pg, "apply_price_table", c3, version(pg, c3), "apply-reapply", json.dumps([empty]))
    require(price_of(empty) == "80", "table-priced trip could not be re-applied")
    call(pg, "edit_trip_price", c3, version(pg, c3), "manual-empty", empty, 90, None)
    reject_call(pg, "apply_price_table", c3, version(pg, c3), "apply-after-manual", json.dumps([empty]), error="PRICE_TYPED_PRICE")
    require(price_of(empty) == "90", "manual price overwritten by table")
    return "future paste rejected; receipts FIFO by (date,pid) at write; typed prices kept; Sheet functions canonical"
