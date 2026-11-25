"""Audit SQL lõi tiền 23/11/2026 (sql-findings.md ngoài repo): F1 bảng băm định nghĩa + mức lược đồ, F2 phí lẻ không ngày theo
khóa tháng, F8 một hàm lý do CHỜ KIỂM cho dán/sửa chuyến/sửa sổ gốc, F9 khóa sổ NO KEY UPDATE và khóa container theo thứ tự,
F10 cờ lưu trữ qua đường lệnh.

Run only through disposable test_pg_v7_backend.py harness."""
import json

from pg_v7_harness import (
    AUDIT_SQL_MIGRATION,
    DIEU_CHINH_THEO_GIA_MIGRATION,
    ROOT,
    SO_GON_MIGRATION,
    THANG_HIEN_TAI_MIGRATION,
    Pg,
    PsqlSession,
    call,
    fixture_open_month,
    lit,
    new_book,
    reject_call,
    require,
    trip_json,
    version,
)
from test_pg_v7_backend_chan_trung import CATALOG, _legacy

MIGRATION = AUDIT_SQL_MIGRATION
MANIFEST = ROOT / "cong-no-web-handoff" / "tools" / "v7_catalog_manifest.json"
FEE_ONLY = {"container": None, "carrier": None, "date": None, "from": None, "to": None, "unitPriceVnd": None,
            "otherFeeVnd": "-500", "note": "FAKE phí lẻ"}


def _months(pg: Pg) -> tuple[str, str, str]:
    """(tháng trước, tháng này, tháng sau) theo giờ VN, dạng YYYY-MM-01."""
    row = pg.value("SELECT to_char(m - interval '1 month','YYYY-MM-DD')||'|'||to_char(m,'YYYY-MM-DD')||'|'||"
                   "to_char(m + interval '1 month','YYYY-MM-DD') FROM (SELECT date_trunc('month',"
                   "clock_timestamp() AT TIME ZONE 'Asia/Ho_Chi_Minh')::date AS m) s")
    prev, cur, nxt = row.split("|")
    return prev, cur, nxt


def _trip(pg: Pg, customer: int, trip_id: int) -> dict:
    return next(item for item in call(pg, "get_ledger", customer)["trips"] if item["id"] == trip_id)


def _paste_one(pg: Pg, customer: int, key: str, container: str, day: str, month: str = "2026-01-01") -> dict:
    row = json.loads(trip_json("100", container=container, month=month))[0]
    row["date"] = f"{day}/{month[5:7]}/{month[:4]}"
    return call(pg, "paste_trips", customer, version(pg, customer), key, month, json.dumps([row]))


def _check_catalog(pg: Pg) -> None:
    fresh = pg.value(CATALOG)
    migration = MIGRATION.read_text(encoding="utf-8")
    pg.sql(migration)
    pg.sql(migration)
    pg.sql(DIEU_CHINH_THEO_GIA_MIGRATION.read_text(encoding="utf-8"))  # DIEU-CHINH-THEO-GIA-01: v_adjustment_current, schema_level hiện hành
    pg.sql(SO_GON_MIGRATION.read_text(encoding="utf-8"))  # audit SQL F4: get_ledger, ba lệnh ghi Sheet, schema_level hiện hành
    pg.sql(THANG_HIEN_TAI_MIGRATION.read_text(encoding="utf-8"))  # SK-C1: get_ledger hiện hành
    require(pg.value(CATALOG) == fresh, "audit SQL migration rerun changed function catalog")
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    live = json.loads(pg.value("SELECT sokhach._catalog_manifest()"))
    require(live == manifest, "repo manifest differs from fresh schema: regenerate with v7_schema_snapshot.py")
    require(int(pg.value("SELECT sokhach.schema_level()")) == manifest["level"], "schema_level differs from manifest")
    # Trigger tắt tay thì dấu đổi (cờ tgenabled), bật lại thì về như cũ.
    key = "trip.trip_sheet_cross_customer"
    pg.sql("ALTER TABLE sokhach.trip DISABLE TRIGGER trip_sheet_cross_customer")
    disabled = json.loads(pg.value("SELECT sokhach._catalog_manifest()"))["triggers"][key]
    pg.sql("ALTER TABLE sokhach.trip ENABLE TRIGGER trip_sheet_cross_customer")
    require(disabled.endswith(":D") and disabled != manifest["triggers"][key], f"disabled trigger not visible: {disabled}")
    require(json.loads(pg.value("SELECT sokhach._catalog_manifest()")) == manifest, "re-enabled trigger left a difference")


def _check_fee_month(pg: Pg) -> None:
    prev, cur, nxt = _months(pg)
    customer = new_book(pg, ("2026-01-01", 50))
    fee = json.dumps([FEE_ONLY])
    # Tháng trước chưa mở: phí lẻ không ngày không được vào (trước đây vào thẳng tháng khóa).
    reject_call(pg, "paste_trips", customer, version(pg, customer), "as-fee-locked", prev, fee, error="MONTH_LOCKED")
    # Tháng sau: kể cả khi có dòng mở khóa, không tạo tháng tương lai (trước đây dựng được tháng năm 2031).
    fixture_open_month(pg, customer, nxt)
    reject_call(pg, "paste_trips", customer, version(pg, customer), "as-fee-future", nxt, fee, error="FUTURE_DATE")
    reject_call(pg, "paste_trips", customer, version(pg, customer), "as-fee-2031", "2031-01-01", fee, error="FUTURE_DATE")
    require(pg.value(f"SELECT count(*) FROM sokhach.trip WHERE customer_id={customer}") == "0", "rejected fee row written")
    # Tháng hiện tại và tháng đã mở: vào được, tính tiền ngay.
    call(pg, "paste_trips", customer, version(pg, customer), "as-fee-cur", cur, fee)
    fixture_open_month(pg, customer, prev)
    call(pg, "paste_trips", customer, version(pg, customer), "as-fee-prev", prev, fee)
    require(call(pg, "get_ledger", customer)["total_outstanding_vnd"] == "-950", "fee rows in open months must count")
    # Chuyến có ngày vẫn nhập bù vào tháng khóa (NHAP-SHEET-01 (7)).
    pg.sql(f"UPDATE sokhach.month_state SET locked=true WHERE customer_id={customer} AND month={lit(prev)}")
    dated = _paste_one(pg, customer, "as-dated-locked", "FAKE-AS-DATED", "01", prev)
    require(not dated["pending_review"], f"dated back-fill into locked month must pass: {dated}")


def _check_dup_reason(pg: Pg) -> None:
    customer = new_book(pg, ("2026-01-01", 50))
    fixture_open_month(pg, customer, "2026-01-01")
    # Sổ gốc không ngày đổi container thành đúng chuyến web đang tính, cùng tháng: chuyến vào CHỜ KIỂM.
    trip_a = _paste_one(pg, customer, "as-a", "FAKE-AS-1", "05")["trip_ids"][0]
    undated = _legacy(pg, customer, "2026-01-01", {"container": "FAKE-AS-OTHER", "date": None}, 31)
    require(call(pg, "get_ledger", customer)["total_outstanding_vnd"] == "150", "fixture: opening 50 + trip 100")
    edited = call(pg, "edit_legacy_trip", customer, version(pg, customer), "as-legacy-1", undated, "container", "FAKE-AS-1")
    require(edited["review_trips"] == [trip_a], f"legacy edit must hold the matching web trip: {edited}")
    held = _trip(pg, customer, trip_a)
    require(held["status"] == "pending_review" and held["review_reason"] == "BASELINE_UNDATED_MONTH", f"held trip: {held}")
    require(call(pg, "get_ledger", customer)["total_outstanding_vnd"] == "50", "held trip still counted")
    # Người duyệt giữ chuyến: sửa dòng sổ gốc khác thành cùng container không đẩy lại (đã có lý do trùng từ trước).
    call(pg, "review_trip", customer, version(pg, customer), "as-review", trip_a, "confirm", "FAKE khác chuyến")
    other = _legacy(pg, customer, "2026-01-01", {"container": "FAKE-AS-OTHER2", "date": None}, 32)
    again = call(pg, "edit_legacy_trip", customer, version(pg, customer), "as-legacy-2", other, "container", "FAKE-AS-1")
    require(again["review_trips"] == [] and _trip(pg, customer, trip_a)["status"] == "confirmed", f"reviewed trip re-held: {again}")
    # Dòng sổ gốc có ngày, cách chuyến 2 ngày: chuyến vào CHỜ KIỂM theo cửa sổ ngày.
    trip_b = _paste_one(pg, customer, "as-b", "FAKE-AS-2", "08")["trip_ids"][0]
    dated = _legacy(pg, customer, "2026-01-01", {"container": "FAKE-AS-2X", "date": "2026-01-10"}, 33)
    window = call(pg, "edit_legacy_trip", customer, version(pg, customer), "as-legacy-3", dated, "container", "FAKE-AS-2")
    require(window["review_trips"] == [trip_b] and _trip(pg, customer, trip_b)["review_reason"] == "BASELINE_DATE_WINDOW",
            f"dated legacy edit must hold the trip: {window}")
    # Đối chứng: dòng có ngày cách xa hơn 3 ngày không giữ chuyến (container dùng lại).
    trip_c = _paste_one(pg, customer, "as-c", "FAKE-AS-3", "02")["trip_ids"][0]
    far = _legacy(pg, customer, "2026-01-01", {"container": "FAKE-AS-3X", "date": "2026-01-20"}, 34)
    kept = call(pg, "edit_legacy_trip", customer, version(pg, customer), "as-legacy-4", far, "container", "FAKE-AS-3")
    require(kept["review_trips"] == [] and _trip(pg, customer, trip_c)["status"] == "confirmed", f"far legacy row held: {kept}")
    # Chiều dán: dòng sổ gốc đã sửa (baseline_trip_ref không thấy) vẫn giữ chuyến mới dán trong cửa sổ ngày.
    moved = _legacy(pg, customer, "2026-01-01", {"container": "FAKE-AS-4X", "date": "2026-01-12"}, 35)
    call(pg, "edit_legacy_trip", customer, version(pg, customer), "as-legacy-5", moved, "container", "FAKE-AS-4")
    pasted = _paste_one(pg, customer, "as-d", "FAKE-AS-4", "13")
    require([row["reason"] for row in pasted["pending_review"]] == ["BASELINE_DATE_WINDOW"], f"paste after legacy edit: {pasted}")
    # Chiều sửa chuyến dùng cùng hàm: chuyến khác đổi container sang FAKE-AS-4 cùng ngày cũng vào CHỜ KIỂM.
    trip_e = _paste_one(pg, customer, "as-e", "FAKE-AS-5", "11")["trip_ids"][0]
    edit = call(pg, "edit_trip_info", customer, version(pg, customer), "as-edit-e", trip_e, "container", "FAKE-AS-4")
    require(edit["pending_review"] is True and edit["reason"] == "BASELINE_DATE_WINDOW", f"trip edit after legacy edit: {edit}")


def _check_locks(pg: Pg) -> None:
    for function in ("_begin_command(bigint,bigint,text,jsonb)", "reallocate(bigint,text)",
                     "_begin_offset(bigint,bigint,bigint,bigint,text,jsonb)"):
        body = pg.value(f"SELECT pg_get_functiondef('sokhach.{function}'::regprocedure)")
        require("FOR NO KEY UPDATE" in body and "FOR UPDATE" not in body.replace("FOR NO KEY UPDATE", ""),
                f"{function} must lock the book FOR NO KEY UPDATE")
    customer = new_book(pg, ("2026-01-01", 50))
    holder = PsqlSession(pg, "v7_audit_sql_lock")
    try:
        holder.send(f"BEGIN; SET LOCAL sokhach.actor='harness'; "
                    f"SELECT sokhach._begin_command({customer},{version(pg, customer)},'as-lock','{{}}'::jsonb) IS NULL")
        require(holder.line() == "t", "lock holder did not start the command")
        # Dòng con (khóa ngoại lấy KEY SHARE) không chờ lệnh tiền; lệnh tiền khác vẫn phải chờ.
        pg.sql(f"SET lock_timeout='1s'; SELECT 1 FROM sokhach.customer WHERE id={customer} FOR KEY SHARE")
        pg.rejects(f"SET lock_timeout='1s'; SELECT 1 FROM sokhach.customer WHERE id={customer} FOR NO KEY UPDATE",
                   message="lock timeout")
    finally:
        holder.close()
    # Hai lô Sheet cùng hai container, thứ tự ngược nhau, ở hai sổ: lô sau chờ lô trước rồi xong, không kẹt chéo.
    first, second = new_book(pg, ("2026-01-01", 50)), new_book(pg, ("2026-01-01", 50))
    for book in (first, second):
        fixture_open_month(pg, book, "2026-01-01")

    def sheet_rows(order, day):
        rows = []
        for n, container in enumerate(order, 1):
            row = json.loads(trip_json("100", container=container))[0]
            row.update(date=f"{day}/01/2026", src=f"sheet:{'b' * 64}:{n}")
            rows.append(row)
        return json.dumps(rows)
    a, b = PsqlSession(pg, "v7_audit_sql_a"), PsqlSession(pg, "v7_audit_sql_b")
    try:
        a.send(f"BEGIN; SET LOCAL sokhach.actor='harness'; SELECT (sokhach.paste_trips({first},{version(pg, first)},'as-sheet-a',"
               f"'2026-01-01',{lit(sheet_rows(['FAKE-AS-K2', 'FAKE-AS-K1'], '02'))})->>'version') IS NOT NULL")
        require(a.line() == "t", "first sheet batch failed")
        b.send(f"BEGIN; SET LOCAL sokhach.actor='harness'; SELECT (sokhach.paste_trips({second},{version(pg, second)},'as-sheet-b',"
               f"'2026-01-01',{lit(sheet_rows(['FAKE-AS-K1', 'FAKE-AS-K2'], '20'))})->>'version') IS NOT NULL")
        try:
            b.line(timeout=1.5)
        except Exception:  # noqa: BLE001  phải chờ khóa container của lô trước
            pass
        else:
            raise AssertionError("second batch did not wait for the first batch's container locks")
        a.send("COMMIT")
        require(b.line(timeout=15) == "t", "second sheet batch failed after the first committed")
        b.send("COMMIT")
    finally:
        a.close()
        b.close()


def _check_archive(pg: Pg) -> None:
    customer = new_book(pg, ("2026-01-01", 50))
    reject_call(pg, "set_customer_archived", customer, version(pg, customer), "as-arch-debt", "true", error="ARCHIVE_BALANCE_NOT_ZERO")
    call(pg, "record_receipt", customer, version(pg, customer), "as-arch-pay", "2026-01-15", "THU TIỀN", "50", None)
    before = version(pg, customer)
    done = call(pg, "set_customer_archived", customer, before, "as-arch", "true")
    require(done["archived"] is True and done["version"] == before + 1, f"archive result: {done}")
    replay = call(pg, "set_customer_archived", customer, before, "as-arch", "true")
    require(replay == done, "same key must replay the stored result")
    event = json.loads(pg.value(f"SELECT jsonb_build_array(\"before\"->'customer'->'archived',\"after\"->'customer'->'archived') "
                                f"FROM sokhach.event WHERE customer_id={customer} AND kind='customer_attr' ORDER BY id DESC LIMIT 1"))
    require(event == [False, True], f"archive must leave a History row before -> after: {event}")
    reject_call(pg, "set_customer_archived", customer, version(pg, customer), "as-arch-again", "true", error="NO_CHANGE")
    call(pg, "set_customer_archived", customer, version(pg, customer), "as-unarch", "false")
    require(pg.value(f"SELECT archived FROM sokhach.customer WHERE id={customer}") == "f", "unarchive failed")


def _check_adjustment_needs_price(pg: Pg) -> None:
    """DIEU-CHINH-THEO-GIA-01 (F6, cách A): xóa đơn giá thì điều chỉnh của chuyến cũng ra khỏi số dư; nhập lại giá thì tính lại."""
    customer = new_book(pg, ("2026-01-01", 50))
    fixture_open_month(pg, customer, "2026-01-01")
    trip = _paste_one(pg, customer, "f6-paste", "FAKE-F6-1", "05")["trip_ids"][0]
    call(pg, "adjust_trip", customer, version(pg, customer), "f6-adjust", trip, 90, "giảm giá")
    total = lambda: call(pg, "get_ledger", customer)["total_outstanding_vnd"]  # noqa: E731
    require(total() == "140", "fixture: opening 50 + trip 100 - 10")
    call(pg, "edit_trip_price", customer, version(pg, customer), "f6-clear", trip, None, None)
    require(total() == "50", "cleared price must drop the trip and its adjustment")
    ledger = call(pg, "get_ledger", customer)
    require(ledger["adjustments"] == [] and pg.value(f"SELECT count(*) FROM sokhach.adjustment WHERE trip_id={trip}") == "1",
            "adjustment row stays stored but is not listed while the trip has no price")
    call(pg, "edit_trip_price", customer, version(pg, customer), "f6-reprice", trip, 100, None)
    require(total() == "140", "re-priced trip counts its adjustment again")
    # Xóa giá rồi nhập giá KHÁC: điều chỉnh (−10) vẫn cộng lên giá mới.
    call(pg, "edit_trip_price", customer, version(pg, customer), "f6-clear-2", trip, None, None)
    call(pg, "edit_trip_price", customer, version(pg, customer), "f6-reprice-2", trip, 200, None)
    require(total() == "240", "new price counts with the existing adjustment: 50 + 200 - 10")
    # Dòng chỉ phụ phí (không container): còn phụ phí thì điều chỉnh tính; xóa hết phụ phí thì cả dòng lẫn điều chỉnh ra ngoài.
    fee_book = new_book(pg, ("2026-01-01", 50))
    fixture_open_month(pg, fee_book, "2026-01-01")
    fee_row = {"container": None, "carrier": None, "date": "06/01/2026", "from": None, "to": None, "unitPriceVnd": None,
               "otherFeeVnd": "300", "note": "FAKE phí lẻ"}
    fee_trip = call(pg, "paste_trips", fee_book, version(pg, fee_book), "f6-fee", "2026-01-01", json.dumps([fee_row]))["trip_ids"][0]
    call(pg, "adjust_trip", fee_book, version(pg, fee_book), "f6-fee-adjust", fee_trip, 250, "giảm phí")
    fee_total = lambda: call(pg, "get_ledger", fee_book)["total_outstanding_vnd"]  # noqa: E731
    require(fee_total() == "300", "fixture: opening 50 + fee 300 - 50")
    call(pg, "edit_trip_price", fee_book, version(pg, fee_book), "f6-fee-clear", fee_trip, None, None)
    require(fee_total() == "50", "fee-only row without fee drops with its adjustment")


def _check_slim_ledger(pg: Pg) -> None:
    """F4: get_ledger chỉ trả dòng phân bổ còn hiệu lực và dòng bị chính lệnh hủy phiếu thay; lý do CHỜ KIỂM lúc dán vẫn đọc được."""
    customer = new_book(pg, ("2026-01-01", 50))
    for month in ("2026-01-01", "2026-02-01"):
        fixture_open_month(pg, customer, month)
    _paste_one(pg, customer, "f4-feb", "FAKE-F4-1", "03", "2026-02-01")
    kept = call(pg, "record_receipt", customer, version(pg, customer), "f4-pay-1", "2026-02-10", "THU TIỀN", "120", None)["pid"]
    voided = call(pg, "record_receipt", customer, version(pg, customer), "f4-pay-2", "2026-02-11", "THU TIỀN", "20", None)["pid"]
    # Chuyến tháng 1 dán sau: phân bổ lại hai phiếu theo nợ cũ trước, các dòng cũ bị thay (superseded).
    _paste_one(pg, customer, "f4-jan", "FAKE-F4-2", "04", "2026-01-01")
    call(pg, "void_receipt", customer, version(pg, customer), "f4-void", voided, "nhập nhầm")
    stored = int(pg.value(f"SELECT count(*) FROM sokhach.receipt_line WHERE customer_id={customer}"))
    expected = json.loads(pg.value(
        "SELECT jsonb_object_agg(r.pid, (SELECT jsonb_agg(l.id ORDER BY l.id) FROM sokhach.receipt_line l WHERE l.receipt_id=r.id "
        "AND (l.superseded_by_event IS NULL OR l.superseded_by_event=r.voided_by_event))) "
        f"FROM sokhach.receipt r WHERE r.customer_id={customer}"))
    ledger = call(pg, "get_ledger", customer)
    got = {r["pid"]: [line["id"] for line in r["allocations"]] for r in ledger["receipts"]}
    require(got == expected and sum(map(len, got.values())) < stored, f"allocations: {got} vs {expected}, stored {stored}")
    require(all(line["superseded_by_event"] is None for r in ledger["receipts"] if r["pid"] == kept for line in r["allocations"]),
            "kept receipt lists only live lines")
    held = _paste_one(pg, customer, "f4-dup", "FAKE-F4-1", "04", "2026-02-01")
    reason = next(t["review_reason"] for t in call(pg, "get_ledger", customer)["trips"] if t["id"] == held["trip_ids"][0])
    require(reason == "WEB_DUPLICATE", f"paste review reason must still show: {reason}")


def check_audit_sql(pg: Pg) -> str:
    _check_catalog(pg)
    _check_fee_month(pg)
    _check_dup_reason(pg)
    _check_locks(pg)
    _check_archive(pg)
    _check_adjustment_needs_price(pg)
    _check_slim_ledger(pg)
    return ("manifest = fresh schema, trigger disabled is visible; undated fee rows need an open, non-future month; "
            "legacy container/date edits hold matching web trips, paste/trip edit see edited legacy rows; book lock is "
            "NO KEY UPDATE and sheet container locks are ordered; archive flag goes through a command with History; "
            "trip adjustment counts only while the trip has a price")
