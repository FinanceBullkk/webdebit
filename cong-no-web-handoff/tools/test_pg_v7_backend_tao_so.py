"""Máy tạo sổ cho khách mới (MAY-TAO-SO-01): một giao dịch qua đủ cổng kiểm của mốc. Chạy qua harness V7 dùng một lần, dữ liệu giả."""
import json

from pg_v7_harness import (
    ROOT,
    call,
    fixture_open_month,
    import_data,
    reject_call,
    require,
    trip_json,
    version,
)

SIGNATURE = "sokhach.create_book_from_sheet(text,text,text,jsonb,jsonb,jsonb,bigint,text)"
SHA = "c" * 64


def _rows(pg):
    return pg.value("SELECT (SELECT count(*) FROM sokhach.customer)||'/'||(SELECT count(*) FROM sokhach.cutover)"
                    "||'/'||(SELECT count(*) FROM sokhach.event)||'/'||(SELECT count(*) FROM sokhach.baseline_trip_ref)")


def _trip(month, container, date, total):
    return {"debt_month": month, "kind": "trip", "source_total_vnd": total, "source_tab": "FAKE", "source_row": 9,
            "display": {"container": container, "date": date, "unit_price": str(total), "flags": []}}


def check_tao_so(pg):
    openings, _, checks = import_data([300])
    legacy = json.dumps([_trip("2026-01-01", "FAKE TAO 1", "2026-01-03", 300)])
    created = call(pg, "create_book_from_sheet", "KHACH MOI A", "Mặt hàng thử", "CANG", openings, legacy, checks, 300, SHA, actor="may-thu")
    customer = created["customer_id"]
    require(created["version"] == version(pg, customer) == 3, "version after create")

    ledger = call(pg, "get_ledger", customer)
    require(ledger["status"] == "active" and ledger["total_outstanding_vnd"] == "300", "new book not active with Sheet total")
    defaults = pg.value("SELECT string_agg(id::text,',' ORDER BY default_position) FROM sokhach.fee_type WHERE default_position IS NOT NULL")
    require(",".join(str(c["fee_type_id"]) for c in ledger["fee_columns"]) == defaults, "COT-PHU-PHI-01 default columns on new book")
    require([row["id"] for row in ledger["legacy_rows"] if row["kind"] == "trip"], "legacy trip missing")
    event = next(row for row in ledger["events"] if row["kind"] == "import")
    require(event["actor"] == "may-thu", "import not under machine name")
    listed = next(row for row in call(pg, "list_customers")["customers"] if row["id"] == customer)
    require((listed["status"], listed["commodity"], listed["transport_mode"]) == ("active", "Mặt hàng thử", "CANG"), "list_customers attributes")
    cutover = pg.value(f"SELECT status||'/'||source_sha256 FROM sokhach.cutover WHERE id={created['cutover_id']}")
    require(cutover == f"active/{SHA}", "own cutover not active")
    refs = pg.value(f"SELECT booking_norm||'|'||container_norm||'|'||event_date FROM sokhach.baseline_trip_ref WHERE cutover_id={created['cutover_id']}")
    require(refs == "ALT:FAKETAO1:20260103|FAKETAO1|2026-01-03", f"trip reference wrong: {refs}")

    # Từ đó sổ chạy như mọi khách: thêm được chuyến, và chuyến trùng dòng sổ gốc tự vào chờ kiểm.
    fixture_open_month(pg, customer, "2026-01-01")
    pasted = call(pg, "paste_trips", customer, version(pg, customer), "tao-so-paste", "2026-01-01", trip_json())
    require(pasted["trip_ids"], "paste into new book")
    pending = call(pg, "paste_trips", customer, version(pg, customer), "tao-so-trung", "2026-01-01", trip_json(container="FAKE TAO 1"))
    require(pending.get("pending_review"), "duplicate of legacy row not flagged")

    # Tên đã có, kể cả khác hoa thường, không tạo thêm và không để lại gì.
    before = _rows(pg)
    reject_call(pg, "create_book_from_sheet", "khach moi a", None, None, openings, "[]", checks, 300, SHA, error="BOOK_EXISTS")
    reject_call(pg, "create_book_from_sheet", " ", None, None, openings, "[]", checks, 300, SHA, error="INVALID_BOOK_NAME")
    reject_call(pg, "create_book_from_sheet", " KHACH B ", None, None, openings, "[]", checks, 300, SHA, error="INVALID_BOOK_NAME")
    reject_call(pg, "create_book_from_sheet", "KHACH B", None, None, openings, "[]", checks, 300, "khong-phai-sha", error="INVALID_CUTOVER_INPUT")
    # Cổng kiểm không đạt ở bước nào thì khách, mốc, event của lần đó đều không còn.
    reject_call(pg, "create_book_from_sheet", "KHACH B", None, None, openings, "[]", checks, 301, SHA, error="CUTOVER_CUSTOMER_TOTAL_MISMATCH")
    reject_call(pg, "create_book_from_sheet", "KHACH B", None, None, "[]", "[]", "[]", 0, SHA, error="CUTOVER_SOURCE_INCOMPLETE")
    wrong = import_data([300], standards=[299], charges=[300])
    reject_call(pg, "create_book_from_sheet", "KHACH B", None, None, wrong[0], "[]", wrong[2], 300, SHA, error="CUTOVER_")
    reject_call(pg, "create_book_from_sheet", "KHACH B", None, "SAI", openings, "[]", checks, 300, SHA, error="transport_mode")
    require(_rows(pg) == before, "failed create left rows behind")

    # Tab không có container: vẫn dán chuyến được nhờ dòng đánh dấu. Không mặt hàng thì để trống.
    empty = call(pg, "create_book_from_sheet", "KHACH MOI C", None, None, openings, "[]", checks, 300, SHA)
    require(pg.value(f"SELECT container_norm FROM sokhach.baseline_trip_ref WHERE cutover_id={empty['cutover_id']}") == "SO-MOI", "marker reference")
    fixture_open_month(pg, empty["customer_id"], "2026-01-01")
    require(call(pg, "paste_trips", empty["customer_id"], version(pg, empty["customer_id"]), "tao-so-paste-c", "2026-01-01", trip_json())["trip_ids"], "paste into book without containers")
    require(next(row for row in call(pg, "list_customers")["customers"] if row["id"] == empty["customer_id"])["commodity"] is None, "commodity guessed")

    pg.true(f"has_function_privilege('sokhach_app','{SIGNATURE}','EXECUTE')", "app cannot create book")
    pg.true(f"NOT has_function_privilege('sokhach_reader','{SIGNATURE}','EXECUTE')", "reader can create book")
    pg.true(f"NOT has_function_privilege('public','{SIGNATURE}','EXECUTE')", "public can create book")

    migration = (ROOT / "cong-no-web-handoff/tools/migrations/2026-11-04-v7-tao-so.sql").read_text(encoding="utf-8")
    catalog = f"SELECT pg_get_functiondef('{SIGNATURE}'::regprocedure)"
    original = pg.value(catalog)
    pg.sql(migration)
    pg.sql(migration)
    # COT-PHU-PHI-01 thay thân hàm sau MAY-TAO-SO-01: chạy lại theo đúng thứ tự triển khai thì về bản chuẩn.
    pg.sql((ROOT / "cong-no-web-handoff/tools/migrations/2026-11-13-v7-cot-phu-phi-mac-dinh.sql").read_text(encoding="utf-8"))
    require(pg.value(catalog) == original, "migration changed canonical definition")
