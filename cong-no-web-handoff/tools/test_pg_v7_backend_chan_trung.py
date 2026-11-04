"""Chặn tính trùng ở hàng chờ chuyến mới (1/11/2026, docs/ux-luong-du-lieu.md mục 3.3 và 8).

Run only through disposable test_pg_v7_backend.py harness."""
import json

from pg_v7_harness import (
    CHAN_TRUNG_MIGRATION,
    CONTAINER_INDEX_MIGRATION,
    call,
    fixture_open_month,
    lit,
    new_book,
    reject_call,
    require,
    trip_json,
    version,
)

CATALOG = ("SELECT jsonb_object_agg(p.oid::regprocedure::text,pg_get_functiondef(p.oid)) FROM pg_proc p "
           "WHERE p.pronamespace='sokhach'::regnamespace")


def _legacy(pg, customer: int, month: str, display: dict, row: int, kind: str = "trip") -> int:
    cutover = pg.value(f"SELECT cutover_id FROM sokhach.cutover_customer WHERE customer_id={customer}")
    event = pg.value(f"SELECT id FROM sokhach.event WHERE customer_id={customer} AND kind='import'")
    return int(pg.value("BEGIN; SET LOCAL ROLE sokhach_owner; "
        "ALTER TABLE sokhach.legacy_row DISABLE TRIGGER legacy_row_insert_guard; "
        "INSERT INTO sokhach.legacy_row(customer_id,cutover_id,debt_month,kind,display,source_total_vnd,source_tab,source_row,created_by_event) "
        f"VALUES({customer},{cutover},{lit(month)},{lit(kind)},{lit(json.dumps(display))},50,'FAKE',{row},{event}) RETURNING id; "
        "ALTER TABLE sokhach.legacy_row ENABLE TRIGGER legacy_row_insert_guard; COMMIT").splitlines()[0])


def _paste(pg, customer: int, key: str, container: str, date: str) -> dict:
    row = json.loads(trip_json(container=container))[0]
    row["date"] = date
    month = f"{date[6:]}-{date[3:5]}-01"
    return call(pg, "paste_trips", customer, version(pg, customer), key, month, json.dumps([row]))


def check_chan_trung(pg) -> str:
    # Migration chỉ thêm hai hàm và thay thân paste_trips: chạy hai lượt trên lược đồ chuẩn không đổi catalog.
    fresh = pg.value(CATALOG)
    migration = CHAN_TRUNG_MIGRATION.read_text(encoding="utf-8")
    pg.sql(migration)
    pg.sql(migration)
    container_index = CONTAINER_INDEX_MIGRATION.read_text(encoding="utf-8")
    pg.sql(container_index)  # chan-trung trả list_legacy_trip_refs cũ
    pg.sql(container_index)
    require(pg.value(CATALOG) == fresh, "chan-trung migration rerun changed function catalog")
    for name, allowed in (("list_legacy_trip_refs", True), ("_legacy_undated_match", False)):
        require(pg.value(f"SELECT bool_and(has_function_privilege('v7_app',oid,'EXECUTE')) FROM pg_proc "
                         f"WHERE pronamespace='sokhach'::regnamespace AND proname={lit(name)}") == ("t" if allowed else "f"),
                f"{name} EXECUTE grant for app wrong")

    # Sổ A (mặt hàng khác của cùng khách) giữ ba dòng sổ gốc tháng 1: không ngày, có ngày, không ngày nhưng sẽ xóa.
    other = new_book(pg, ("2026-01-01", 150))
    fixture_open_month(pg, other, "2026-01-01")
    _legacy(pg, other, "2026-01-01", {"container": "UND 1", "date": None}, 11)
    _legacy(pg, other, "2026-01-01", {"container": "DATED-1", "date": "2026-01-05"}, 12)
    deleted = _legacy(pg, other, "2026-01-01", {"container": "DEL-1", "date": ""}, 13)
    call(pg, "delete_legacy_trip", other, version(pg, other), "ct-delete", deleted)

    book = new_book(pg, ("2026-01-01", 100))
    for month in ("2026-01-01", "2026-02-01"):
        fixture_open_month(pg, book, month)

    # 1. Cùng container với dòng sổ gốc không ngày, cùng tháng nợ: vào chờ kiểm, không cộng nợ.
    before = call(pg, "get_ledger", book)["months"]
    held = _paste(pg, book, "ct-held", "und1", "10/01/2026")
    require([p["reason"] for p in held["pending_review"]] == ["BASELINE_UNDATED_MONTH"], f"undated duplicate not held: {held}")
    require(call(pg, "get_ledger", book)["months"] == before, "held trip changed month totals")

    # 2. Cùng container nhưng tháng khác: container dùng lại, vào sổ bình thường.
    reused = _paste(pg, book, "ct-other-month", "UND1", "10/02/2026")
    require(not reused["pending_review"], "undated row in another month blocked a reused container")

    # 3. Dòng sổ gốc có ngày lệch hơn 3 ngày: luật cũ không chặn, luật mới cũng không (container dùng lại là chuyện thường).
    dated = _paste(pg, book, "ct-dated", "DATED-1", "20/01/2026")
    require(not dated["pending_review"], "dated original row more than 3 days away blocked the paste")

    # 4. Dòng sổ gốc đã xóa không chặn.
    gone = _paste(pg, book, "ct-deleted", "DEL-1", "10/01/2026")
    require(not gone["pending_review"], "deleted original row still blocked the paste")

    # 5. list_legacy_trip_refs: chỉ dòng còn hiệu lực có container trong danh sách, ngày trống giữ NULL.
    refs = call(pg, "list_legacy_trip_refs", json.dumps(["und1", "DEL-1", "NONE"]))["items"]
    require(refs == [{"customer_id": other, "container": "UND 1", "event_date": None, "debt_month": "2026-01-01"}],
            f"legacy refs wrong: {refs}")
    require(call(pg, "list_legacy_trip_refs", "[]") == {"items": []}, "empty container list")
    reject_call(pg, "list_legacy_trip_refs", '{"a":1}', error="INVALID_COMMAND")
    reject_call(pg, "list_legacy_trip_refs", "[1]", error="INVALID_COMMAND")

    # 6. Đầu vào chuẩn hóa như dòng sổ: hoa/thường, khoảng trắng kể cả NBSP, lặp; một dòng chỉ ra một lần; chuỗi rỗng không khớp gì.
    same = call(pg, "list_legacy_trip_refs", json.dumps(["und 1", "UND1", "\u00a0Und\u202f1 "]))["items"]
    require([r["container"] for r in same] == ["UND 1"], f"normalized input wrong: {same}")
    _legacy(pg, other, "2026-01-01", {"date": None}, 14)
    require(call(pg, "list_legacy_trip_refs", json.dumps(["", " "])) == {"items": []}, "blank input matched a row without container")

    # 7. Bản sửa mới nhất quyết định: đổi container thì tìm được theo số mới, không còn theo số cũ. Dòng thu không phải chuyến.
    moved = _legacy(pg, other, "2026-01-01", {"container": "OLD-1", "date": "2026-01-07"}, 15)
    call(pg, "edit_legacy_trip", other, version(pg, other), "ct-move", moved, "container", "NEW-1")
    require(call(pg, "list_legacy_trip_refs", json.dumps(["OLD-1"])) == {"items": []}, "old container still listed after edit")
    require([r["container"] for r in call(pg, "list_legacy_trip_refs", json.dumps([" new-1"]))["items"]] == ["NEW-1"],
            "edited container not found by its new number")
    _legacy(pg, other, "2026-01-01", {"container": "PAY-1", "date": None}, 16, kind="receipt")
    require(call(pg, "list_legacy_trip_refs", json.dumps(["PAY-1"])) == {"items": []}, "receipt row listed as a trip")

    # 8. Biểu thức của index phải trùng điều kiện lọc trong hàm, nếu không index nằm đó mà không bao giờ được dùng.
    for table, column, index in (("legacy_row", "display->>'container'", "legacy_row_container_key"),
                                 ("legacy_trip_rev", "container", "legacy_trip_rev_container_key")):
        plan = pg.value(f"BEGIN; SET LOCAL enable_seqscan=off; EXPLAIN (COSTS OFF) SELECT 1 FROM sokhach.{table} "
                        f"WHERE sokhach._normalize_key({column}) = ANY('{{A,B}}'::text[]); ROLLBACK")
        require(index in plan, f"{index} not usable: {plan}")
    return "undated original row holds same-month paste; reuse, dated and deleted rows pass; legacy refs by container"
