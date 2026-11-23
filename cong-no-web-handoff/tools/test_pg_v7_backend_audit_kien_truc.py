"""Audit kiến trúc 19/11/2026 (commit 0a2eaad): A12 sửa chuyến chạy đủ kiểm trùng như dán, A08 khóa ghi dấu không nhận nội dung khác.

Run only through disposable test_pg_v7_backend.py harness. Probe gốc: _logs/architecture-deep-20261119/pg-dedup-probe.py và
pg-probes.py (mark_changed_payload) — ở đó chuyến sửa giữ confirmed (nợ 150) và dấu đổi tiền trả replayed; ở đây kiểm hành vi đúng."""
import json

from pg_v7_harness import (
    AUDIT_SQL_MIGRATION,
    AUDIT_KIEN_TRUC_MIGRATION,
    call,
    fixture_open_month,
    new_book,
    reject_call,
    require,
    trip_json,
    version,
)
from test_pg_v7_backend_chan_trung import CATALOG, _legacy


def _trip(pg, customer: int, trip_id: int) -> dict:
    return next(item for item in call(pg, "get_ledger", customer)["trips"] if item["id"] == trip_id)


def _undated_edit(pg, field: str) -> str:
    """Chuyến confirmed sửa container (hoặc ngày) thành đúng dòng sổ gốc không ngày cùng tháng: vào chờ kiểm như khi dán."""
    customer = new_book(pg, ("2026-01-01", 50))
    for month in ("2026-01-01", "2026-02-01"):
        fixture_open_month(pg, customer, month)
    duplicate = "FAKE-AK-" + field.upper().replace("_", "")
    _legacy(pg, customer, "2026-01-01", {"container": duplicate, "date": None}, 11)
    old_container = "FAKE-AK-UNIQUE" if field == "container" else duplicate
    old_month = "2026-01-01" if field == "container" else "2026-02-01"
    pasted = call(pg, "paste_trips", customer, version(pg, customer), f"ak-{field}-paste", old_month,
                  trip_json("100", container=old_container, month=old_month))
    require(not pasted["pending_review"], f"fixture trip unexpectedly held: {pasted}")
    trip_id = pasted["trip_ids"][0]
    require(call(pg, "get_ledger", customer)["total_outstanding_vnd"] == "150", "fixture balance must be opening 50 + trip 100")
    edited = call(pg, "edit_trip_info", customer, version(pg, customer), f"ak-{field}-edit", trip_id,
                  field, duplicate if field == "container" else "2026-01-01")
    require(edited["pending_review"] is True and edited["reason"] == "BASELINE_UNDATED_MONTH",
            f"edit into undated duplicate must be held like paste: {edited}")
    require(_trip(pg, customer, trip_id)["status"] == "pending_review", "edited trip not pending_review")
    require(call(pg, "get_ledger", customer)["total_outstanding_vnd"] == "50", "held trip still counted in balance")
    # Đối chứng: dán mới đúng container/ngày cuối cùng cũng bị giữ cùng lý do.
    direct = call(pg, "paste_trips", customer, version(pg, customer), f"ak-{field}-control", "2026-01-01",
                  trip_json("100", container=duplicate, month="2026-01-01"))
    require([row["reason"] for row in direct["pending_review"]] == ["BASELINE_UNDATED_MONTH"], f"control paste: {direct}")
    return customer


def check_audit_kien_truc(pg) -> str:
    # Migration chỉ thay thân hai hàm: chạy hai lượt trên lược đồ chuẩn không đổi catalog.
    fresh = pg.value(CATALOG)
    migration = AUDIT_KIEN_TRUC_MIGRATION.read_text(encoding="utf-8")
    pg.sql(migration)
    pg.sql(migration)
    pg.sql(AUDIT_SQL_MIGRATION.read_text(encoding="utf-8"))  # audit SQL 23/11: bản paste_trips/edit_trip_info/_change_legacy hiện hành
    require(pg.value(CATALOG) == fresh, "audit migration rerun changed function catalog")

    # A12 — hai đường vào cùng một trạng thái cuối: sửa container, sửa ngày sang tháng có dòng sổ gốc không ngày.
    _undated_edit(pg, "container")
    _undated_edit(pg, "event_date")

    # A12 đối chứng: dòng sổ gốc không ngày ở tháng khác, hoặc container khác, không giữ chuyến sửa (container dùng lại).
    customer = new_book(pg, ("2026-01-01", 50))
    for month in ("2026-01-01", "2026-02-01"):
        fixture_open_month(pg, customer, month)
    _legacy(pg, customer, "2026-01-01", {"container": "FAKE-AK-JAN", "date": None}, 12)
    pasted = call(pg, "paste_trips", customer, version(pg, customer), "ak-ctl-paste", "2026-02-01",
                  trip_json("100", container="FAKE-AK-OTHER", month="2026-02-01"))
    trip_id = pasted["trip_ids"][0]
    moved = call(pg, "edit_trip_info", customer, version(pg, customer), "ak-ctl-edit", trip_id, "container", "FAKE-AK-JAN")
    require(moved["pending_review"] is False and moved["reason"] is None, f"other-month undated row must not hold: {moved}")
    require(call(pg, "get_ledger", customer)["total_outstanding_vnd"] == "150", "control trip must stay counted")
    # Ô chữ mô tả không chạy kiểm trùng (chỉ container/ngày).
    carrier = call(pg, "edit_trip_info", customer, version(pg, customer), "ak-ctl-carrier", trip_id, "carrier", "FAKE-2")
    require(carrier["pending_review"] is False, f"carrier edit must not run duplicate rules: {carrier}")

    # A08 — cùng khóa, cùng nội dung: trả dấu cũ; cùng khóa, nội dung khác: IDEMPOTENCY_CONFLICT, không thêm dòng, dấu cũ giữ nguyên.
    book = new_book(pg, ("2026-08-01", 1000))
    today = pg.value("SELECT (clock_timestamp() AT TIME ZONE 'Asia/Ho_Chi_Minh')::date")
    later = pg.value(f"SELECT ('{today}'::date + 5)::text")
    base = {"customer_id": book, "kind": "promise", "idempotency_key": "ak-mark", "amount_vnd": "10", "on_date": later,
            "note": "hẹn", "conversation_id": "c1" * 32, "message_id": "m1"}
    first = call(pg, "record_mark", json.dumps(base, ensure_ascii=False))
    same = call(pg, "record_mark", json.dumps({**base, "amount_vnd": 10, "note": "  hẹn "}, ensure_ascii=False))
    require(same["id"] == first["id"] and same["replayed"] is True, f"identical retry must replay: {same}")
    for change in ({"amount_vnd": "20"}, {"on_date": today}, {"note": "khác"}, {"note": None},
                   {"message_id": "m2"}, {"conversation_id": "d2" * 32}):
        reject_call(pg, "record_mark", json.dumps({**base, **change}, ensure_ascii=False), error="IDEMPOTENCY_CONFLICT")
    rows = pg.value(f"SELECT jsonb_agg(jsonb_build_array(amount_vnd,on_date,note)) FROM sokhach.contact_mark WHERE customer_id={book}")
    require(json.loads(rows) == [[10, later, "hẹn"]], f"changed retries must not add or alter marks: {rows}")
    return ("edit into undated original-row duplicate is held (container and date) like paste; other month/text edits pass; "
            "mark key replays only identical content")
