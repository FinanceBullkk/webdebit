"""NHAC-NO-01: record_reminder / get_reminders — nhật ký "đã nhắc" ngoài đường tiền."""

from __future__ import annotations

from pg_v7_harness import (
    Pg,
    call,
    new_book,
    reject_call,
    require,
    version,
)


def check_doi_no(pg: Pg) -> None:
    customer = new_book(pg, ("2026-08-01", 100))

    # Ghi một mốc nhắc.
    result = call(pg, "record_reminder", customer, "copy-button")
    require(result["customer_id"] == customer and result["source"] == "copy-button"
            and result["reminded_at"], f"record_reminder result: {result}")

    # Ghi người làm, không bump version (ngoài đường tiền).
    actor = pg.value(f"SELECT actor FROM sokhach.reminder_log WHERE customer_id={customer} ORDER BY id DESC LIMIT 1")
    require(actor == "harness", f"reminder actor must be the session actor, got {actor!r}")
    require(version(pg, customer) == 0, "record_reminder must not bump customer.version")

    # Cùng ngày cùng nguồn: dedupe, chỉ một dòng (chạy lại được).
    call(pg, "record_reminder", customer, "copy-button")
    count = int(pg.value(f"SELECT count(*) FROM sokhach.reminder_log "
                         f"WHERE customer_id={customer} AND source='copy-button'"))
    require(count == 1, f"same-day same-source reminder must dedupe, got {count}")

    # Nguồn khác cùng ngày: dòng riêng.
    call(pg, "record_reminder", customer, "zalo")
    count_all = int(pg.value(f"SELECT count(*) FROM sokhach.reminder_log WHERE customer_id={customer}"))
    require(count_all == 2, f"different source should be a separate row, got {count_all}")

    # get_reminders gộp theo khách.
    reminders = call(pg, "get_reminders")["reminders"]
    rows = [r for r in reminders if r["customer_id"] == customer]
    require(len(rows) == 1 and rows[0]["reminder_count"] == 2,
            f"get_reminders should group by customer: {rows}")

    # Nguồn sai và khách lạ bị từ chối.
    reject_call(pg, "record_reminder", customer, "bogus", error="INVALID_REMINDER")
    reject_call(pg, "record_reminder", 999999999, "copy-button", error="CUSTOMER_NOT_FOUND")
