"""Quản lý tạo sổ khách mới và gán tên chủ hàng booking trên web (KHACH-WEB-01). Chạy qua harness V7 dùng một lần, dữ liệu giả."""
import json

from pg_v7_harness import (
    ROOT,
    call,
    fixture_open_month,
    new_book,
    reject_call,
    require,
    trip_json,
    version,
)

CREATE = "sokhach.create_customer(text,text,text,jsonb,text)"
SET_NAME = "sokhach.set_booking_name(bigint,bigint,text,text,boolean)"


def _rows(pg):
    return pg.value("SELECT (SELECT count(*) FROM sokhach.customer)||'/'||(SELECT count(*) FROM sokhach.cutover)"
                    "||'/'||(SELECT count(*) FROM sokhach.event)||'/'||(SELECT count(*) FROM sokhach.booking_name)"
                    "||'/'||(SELECT count(*) FROM sokhach.idempotency)")


def _listed(pg, customer):
    return next(row for row in call(pg, "list_customers")["customers"] if row["id"] == customer)


def check_khach_web(pg):
    month = pg.value("SELECT to_char(date_trunc('month', now() AT TIME ZONE 'Asia/Ho_Chi_Minh'), 'YYYY-MM-DD')")
    names = json.dumps(["KHACH GIA 413", "KHACH GIA 413 B"], ensure_ascii=False)
    created = call(pg, "create_customer", "KHACH MOI WEB", "Dừa", "CANG", names, "web-tao-1", actor="quan-ly-thu")
    customer = created["customer_id"]
    require(created["booking_names"] == ["KHACH GIA 413", "KHACH GIA 413 B"], f"booking names {created}")
    require(created["version"] == version(pg, customer) == 5, f"version after create and two names: {created}")

    # Sổ mới hoạt động ngay, nợ 0, một số dư đầu 0 ở tháng tạo, mốc riêng của web, cột phụ phí mặc định như mọi sổ.
    ledger = call(pg, "get_ledger", customer)
    require(ledger["status"] == "active" and ledger["total_outstanding_vnd"] == "0", "new book not active with zero debt")
    require(pg.value(f"SELECT string_agg(debt_month||':'||amount_vnd,',') FROM sokhach.opening_balance WHERE customer_id={customer}")
            == f"{month}:0", "zero opening of the creation month")
    cutover = pg.value(f"SELECT status||'|'||source||'|'||created_by FROM sokhach.cutover WHERE id={created['cutover_id']}")
    require(cutover == "active|Web, quản lý tạo sổ (KHACH-WEB-01)|quan-ly-thu", f"cutover: {cutover}")
    defaults = pg.value("SELECT string_agg(id::text,',' ORDER BY default_position) FROM sokhach.fee_type WHERE default_position IS NOT NULL")
    require(",".join(str(c["fee_type_id"]) for c in ledger["fee_columns"]) == defaults, "default fee columns on web book")
    listed = _listed(pg, customer)
    require((listed["status"], listed["commodity"], listed["transport_mode"], listed["booking_names"])
            == ("active", "Dừa", "CANG", ["KHACH GIA 413", "KHACH GIA 413 B"]), f"list_customers {listed}")
    events = call(pg, "get_ledger_events", customer)["events"]
    added = [row["after"].get("booking_name_added") for row in events if row["kind"] == "customer_attr"]
    require(sorted(added) == ["KHACH GIA 413", "KHACH GIA 413 B"], f"one history line per name: {added}")
    require(all(row["actor"] == "quan-ly-thu" for row in events), "history not under the manager")

    # Bấm lại cùng khóa: kết quả lần đầu, không tạo gì thêm. Cùng khóa khác nội dung: từ chối.
    before = _rows(pg)
    again = call(pg, "create_customer", "KHACH MOI WEB", "Dừa", "CANG", names, "web-tao-1", actor="quan-ly-thu")
    require(again == created and _rows(pg) == before, "retry created again")
    reject_call(pg, "create_customer", "KHACH MOI WEB 2", "Dừa", "CANG", names, "web-tao-1", error="IDEMPOTENCY_CONFLICT")
    # Tên sổ đã có (kể cả khác hoa thường), tên booking đã ở sổ khác, dữ liệu sai: không để lại gì.
    reject_call(pg, "create_customer", "khach moi web", None, "CANG", "[]", "web-tao-2", error="BOOK_EXISTS")
    reject_call(pg, "create_customer", "KHACH KHAC", None, "BO", json.dumps(["KHACH GIA 413"]), "web-tao-3", error="BOOKING_NAME_TAKEN")
    for args, error in ((("", None, "CANG", "[]"), "INVALID_BOOK_NAME"), ((" KHACH X", None, "CANG", "[]"), "INVALID_BOOK_NAME"),
                        (("KHACH X", None, None, "[]"), "INVALID_COMMAND"), (("KHACH X", None, "SAI", "[]"), "INVALID_COMMAND"),
                        (("KHACH X", " ", "CANG", "[]"), "INVALID_COMMAND"), (("KHACH X", None, "CANG", '"KHACH"'), "INVALID_COMMAND"),
                        (("KHACH X", None, "CANG", '["A", "A"]'), "INVALID_COMMAND"), (("KHACH X", None, "CANG", "[1]"), "INVALID_COMMAND"),
                        (("KHACH X", None, "CANG", json.dumps([f"T {n}" for n in range(21)])), "INVALID_COMMAND"),
                        (("KHACH X", None, "CANG", '["khach thuong"]'), "INVALID_BOOKING_NAME"),
                        (("KHACH X", None, "CANG", '["KHACH  HAI CACH"]'), "INVALID_BOOKING_NAME")):
        reject_call(pg, "create_customer", *args, "web-sai-" + error + str(len(args[3])), error=error)
    reject_call(pg, "create_customer", "KHACH X", None, "CANG", "[]", " ", error="INVALID_COMMAND")
    require(_rows(pg) == before, "failed create left rows behind")

    # Sổ mới nhận chuyến như mọi sổ (paste_trips cần mốc có tham chiếu: dòng đánh dấu SO-MOI).
    fixture_open_month(pg, customer, month)
    pasted = call(pg, "paste_trips", customer, version(pg, customer), "web-dan", month, trip_json(month=month))
    require(pasted["trip_ids"], "paste into web book")

    # Gán, bỏ tên booking ở một sổ đã có: Lịch sử trước → sau, phiên bản tăng, tiền không đổi.
    old = new_book(pg, ("2026-01-01", 700))
    balance = call(pg, "get_ledger", old)["total_outstanding_vnd"]
    v = version(pg, old)
    result = call(pg, "set_booking_name", old, v, "ten-1", "CHU HANG CU 126", False, actor="quan-ly-thu")
    require(result == {"booking_names": ["CHU HANG CU 126"], "version": v + 1}, f"add result {result}")
    require(call(pg, "set_booking_name", old, v, "ten-1", "CHU HANG CU 126", False) == result, "replay not idempotent")
    event = next(row for row in call(pg, "get_ledger_events", old)["events"] if row["kind"] == "customer_attr")
    require((event["before"]["booking_names"], event["after"]["booking_names"], event["after"]["booking_name_added"])
            == ([], ["CHU HANG CU 126"], "CHU HANG CU 126") and "customer" in event["before"], f"history {event}")
    reject_call(pg, "set_booking_name", old, v + 1, "ten-2", "CHU HANG CU 126", False, error="NO_CHANGE")
    reject_call(pg, "set_booking_name", old, v + 1, "ten-3", "KHACH GIA 413", False, error="BOOKING_NAME_TAKEN")
    reject_call(pg, "set_booking_name", old, v + 1, "ten-4", "KHACH GIA 413", True, error="NO_CHANGE")
    reject_call(pg, "set_booking_name", old, v, "ten-5", "CHU HANG KHAC", False, error="STALE_LEDGER")
    for bad in ("chu hang thuong", "CHU  HANG", " CHU HANG", "CHU\tHANG", "", "X" * 201):
        reject_call(pg, "set_booking_name", old, v + 1, "ten-sai", bad, False, error="INVALID_BOOKING_NAME")
    reject_call(pg, "set_booking_name", old, v + 1, "ten-null", "CHU HANG", None, error="INVALID_BOOKING_NAME")
    removed = call(pg, "set_booking_name", old, v + 1, "ten-6", "CHU HANG CU 126", True)
    require(removed == {"booking_names": [], "version": v + 2}, f"remove result {removed}")
    gone = [row for row in call(pg, "get_ledger_events", old)["events"] if row["after"].get("booking_name_removed")]
    require(len(gone) == 1, "remove not in history")
    require(call(pg, "get_ledger", old)["total_outstanding_vnd"] == balance, "booking names changed money")
    # Tên vừa bỏ thì sổ khác gán được.
    call(pg, "set_booking_name", customer, version(pg, customer), "ten-7", "CHU HANG CU 126", False)
    require(_listed(pg, customer)["booking_names"] == ["CHU HANG CU 126", "KHACH GIA 413", "KHACH GIA 413 B"], "moved name")

    for role in ("sokhach_app",):
        for signature in (CREATE, SET_NAME):
            pg.true(f"has_function_privilege('{role}','{signature}','EXECUTE')", f"{role} cannot run {signature}")
    for role in ("sokhach_reader", "public"):
        for signature in (CREATE, SET_NAME):
            pg.true(f"NOT has_function_privilege('{role}','{signature}','EXECUTE')", f"{role} can run {signature}")
    for role in ("sokhach_app", "sokhach_reader"):
        pg.true(f"NOT has_function_privilege('{role}','sokhach._booking_names(bigint)','EXECUTE')", f"{role} runs helper")
        pg.true(f"NOT has_table_privilege('{role}','sokhach.booking_name','SELECT') AND "
                f"NOT has_table_privilege('{role}','sokhach.booking_name','INSERT')", f"{role} touches booking_name directly")

    # Chạy lại migration: bảng, dữ liệu, định nghĩa hàm giữ nguyên.
    migration = (ROOT / "cong-no-web-handoff/tools/migrations/2026-11-24-v7-khach-web.sql").read_text(encoding="utf-8")
    catalog = ("SELECT string_agg(md5(pg_get_functiondef(p.oid)),',' ORDER BY p.oid::regprocedure::text) FROM pg_proc p "
               "WHERE p.pronamespace='sokhach'::regnamespace AND p.proname IN ('create_customer','set_booking_name','_booking_names','list_customers')")
    original, names_before = pg.value(catalog), _rows(pg)
    pg.sql(migration)
    pg.sql(migration)
    require(pg.value(catalog) == original and _rows(pg) == names_before, "migration rerun changed definitions or data")
