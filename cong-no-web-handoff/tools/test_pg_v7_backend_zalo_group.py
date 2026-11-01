"""ZALO-GROUP-01: gắn group Zalo ↔ sổ và dấu tin (hứa trả, khách báo đã chuyển, ghi chú) — ngoài đường tiền."""

from __future__ import annotations

import json

from pg_v7_harness import (
    Pg,
    call,
    new_book,
    reject_call,
    require,
    version,
)

CONV = "a1" * 32
OTHER_CONV = "b2" * 32


def mark(customer: int, kind: str, key: str, **fields) -> str:
    return json.dumps({"customer_id": customer, "kind": kind, "idempotency_key": key, **fields}, ensure_ascii=False)


def check_zalo_group(pg: Pg) -> None:
    book = new_book(pg, ("2026-08-01", 1000))
    other = new_book(pg, ("2026-08-01", 50))
    today = pg.value("SELECT (clock_timestamp() AT TIME ZONE 'Asia/Ho_Chi_Minh')::date")
    def shift(days: int) -> str:
        return pg.value(f"SELECT ('{today}'::date + {days})::text")
    money = ("SELECT jsonb_agg(to_jsonb(v) ORDER BY customer_id,debt_month) FROM sokhach.v_outstanding_month v "
             f"WHERE customer_id IN ({book},{other})")
    before = pg.value(money)

    # Gắn: một group nhiều sổ; gắn lặp không thêm dòng; bỏ gắn bắt buộc lý do, giữ vết; gắn lại được.
    linked = call(pg, "link_zalo", CONV, book)
    require(linked["customer_id"] == book and linked["linked_by"] == "harness" and linked["customer_name"] == "FAKE CONTRACT",
            f"link_zalo result: {linked}")
    call(pg, "link_zalo", CONV, book)
    call(pg, "link_zalo", CONV, other)
    rows = int(pg.value(f"SELECT count(*) FROM sokhach.zalo_link WHERE conversation_id='{CONV}'"))
    require(rows == 2, f"repeated link must not add a row, got {rows}")
    links = [row for row in call(pg, "get_zalo_links")["links"] if row["conversation_id"] == CONV]
    require(sorted(row["customer_id"] for row in links) == sorted([book, other]), f"get_zalo_links: {links}")
    reject_call(pg, "unlink_zalo", CONV, other, "  ", error="REASON_REQUIRED")
    call(pg, "unlink_zalo", CONV, other, "nhầm sổ")
    reject_call(pg, "unlink_zalo", CONV, other, "nhầm sổ", error="LINK_NOT_FOUND")
    links = [row for row in call(pg, "get_zalo_links")["links"] if row["conversation_id"] == CONV]
    require([row["customer_id"] for row in links] == [book], f"unlinked book still listed: {links}")
    trail = pg.value(f"SELECT unlink_reason||'|'||unlinked_by FROM sokhach.zalo_link WHERE customer_id={other}")
    require(trail == "nhầm sổ|harness", f"unlink trail lost: {trail}")
    call(pg, "link_zalo", CONV, other)
    reject_call(pg, "link_zalo", "khong-hop-le", book, error="INVALID_LINK")
    reject_call(pg, "link_zalo", CONV, 999999999, error="CUSTOMER_NOT_FOUND")

    # Hứa trả từ một tin: đang chờ; bấm Lưu lặp cùng khóa trả dấu cũ, không thêm dòng.
    promise = call(pg, "record_mark", mark(book, "promise", "zg-promise", amount_vnd=300, on_date=shift(5), note="mai chuyển",
                                           conversation_id=CONV, message_id="m42", message_at="2026-11-01T09:15:00+07:00",
                                           message_sender="Vũ", message_excerpt="Mai em chuyển 300"))
    # Tiền trả về dạng chuỗi như mọi API tiền (ARCH-03, trang định dạng bằng BigInt).
    require((promise["status"], promise["amount_vnd"], promise["paid_vnd"], promise["created_by"], promise["message_id"])
            == ("pending", "300", "0", "harness", "m42"),
            f"new promise: {promise}")
    replay = call(pg, "record_mark", mark(book, "promise", "zg-promise", amount_vnd=300, on_date=shift(5)))
    require(replay["id"] == promise["id"] and replay["replayed"] is True, f"replay must return the same mark: {replay}")
    reject_call(pg, "record_mark", mark(book, "note", "zg-promise", note="x"), error="IDEMPOTENCY_CONFLICT")
    count = int(pg.value(f"SELECT count(*) FROM sokhach.contact_mark WHERE customer_id={book}"))
    require(count == 1, f"replay added rows: {count}")

    # Dữ liệu sai bị từ chối ở DB (API cũng chặn trước).
    reject_call(pg, "record_mark", mark(book, "note", "zg-bad-1"), error="INVALID_MARK")
    reject_call(pg, "record_mark", mark(book, "note", "zg-bad-2", note="x", amount_vnd=5), error="INVALID_MARK")
    reject_call(pg, "record_mark", mark(book, "promise", "zg-bad-3", amount_vnd=0, on_date=today), error="INVALID_MARK")
    reject_call(pg, "record_mark", mark(book, "promise", "zg-bad-4", amount_vnd=5, on_date=shift(-1)), error="INVALID_MARK_DATE")
    reject_call(pg, "record_mark", mark(book, "paid_claim", "zg-bad-5", amount_vnd=5, on_date=shift(1)), error="INVALID_MARK_DATE")
    reject_call(pg, "record_mark", mark(book, "note", "zg-bad-6", note="x", message_id="m1"), error="INVALID_MARK")
    reject_call(pg, "record_mark", mark(999999999, "note", "zg-bad-7", note="x"), error="CUSTOMER_NOT_FOUND")
    reject_call(pg, "record_mark", mark(book, "khac", "zg-bad-8", note="x"), error="INVALID_MARK")
    reject_call(pg, "record_mark", mark(book, "promise", "zg-bad-9", amount_vnd="12a", on_date=today), error="INVALID_MARK")
    reject_call(pg, "record_mark", mark(book, "promise", "zg-bad-10", amount_vnd="300", on_date="mai"), error="INVALID_MARK")

    # Khách báo đã chuyển và ghi chú.
    # Tiền đi dạng chuỗi như mọi lệnh tiền của API.
    claim = call(pg, "record_mark", mark(book, "paid_claim", "zg-claim", amount_vnd="300", on_date=today, conversation_id=CONV, message_id="m43"))
    old_claim = call(pg, "record_mark", mark(book, "paid_claim", "zg-claim-old", amount_vnd=777, on_date=shift(-5)))
    waiting = call(pg, "record_mark", mark(book, "paid_claim", "zg-claim-wait", amount_vnd=999, on_date=today))
    note = call(pg, "record_mark", mark(book, "note", "zg-note", note="Xin giãn tới cuối tháng", conversation_id=OTHER_CONV))
    require((claim["status"], old_claim["status"], waiting["status"], note["status"]) == ("waiting", "not_seen", "waiting", None),
            f"claim statuses before receipt: {claim} {old_claim} {waiting} {note}")
    # Hứa trả đã quá hẹn (dựng thẳng như dữ liệu cũ: lệnh ghi không cho hẹn ngày đã qua).
    pg.sql("INSERT INTO sokhach.contact_mark(customer_id,kind,amount_vnd,on_date,idempotency_key,created_by,created_on) "
           f"VALUES ({book},'promise',500,'{shift(-2)}','zg-missed','harness','{shift(-10)}')")

    # Phiếu thu hôm nay 300: hứa trả giữ lời, báo đã chuyển 300 có phiếu; báo 999 vẫn chờ; hứa đã quá hẹn thì lỡ hẹn.
    receipt = call(pg, "record_receipt", book, version(pg, book), "zg-receipt", today, "THU TIỀN", 300)
    by_id = {row["id"]: row for row in call(pg, "get_marks", book, None)["marks"]}
    missed_id = int(pg.value("SELECT id FROM sokhach.contact_mark WHERE idempotency_key='zg-missed'"))
    require((by_id[promise["id"]]["status"], by_id[promise["id"]]["paid_vnd"]) == ("kept", "300"), f"promise after receipt: {by_id[promise['id']]}")
    require((by_id[claim["id"]]["status"], by_id[claim["id"]]["receipt_pid"]) == ("received", receipt["pid"]), f"claim: {by_id[claim['id']]}")
    require(by_id[waiting["id"]]["status"] == "waiting", f"unmatched claim: {by_id[waiting['id']]}")
    require((by_id[missed_id]["status"], by_id[missed_id]["paid_vnd"]) == ("missed", "0"), f"overdue promise: {by_id[missed_id]}")
    ordered = [row["id"] for row in call(pg, "get_marks", book, None)["marks"]]
    require(ordered[0] == missed_id and len(ordered) == 6, f"marks must be newest first: {ordered}")

    # Phiếu hủy không tính: hứa trả về đang chờ, báo đã chuyển về chờ.
    call(pg, "void_receipt", book, version(pg, book), "zg-void", receipt["pid"], "nhập nhầm")
    by_id = {row["id"]: row for row in call(pg, "get_marks", book, None)["marks"]}
    require((by_id[promise["id"]]["status"], by_id[claim["id"]]["status"]) == ("pending", "waiting"),
            f"void receipt must not count: {by_id[promise['id']]} {by_id[claim['id']]}")

    # Dấu theo group: chỉ dấu có conversation đó.
    in_group = [row["id"] for row in call(pg, "get_marks", None, CONV)["marks"]]
    require(sorted(in_group) == sorted([promise["id"], claim["id"]]), f"get_marks by conversation: {in_group}")
    reject_call(pg, "get_marks", None, None, error="INVALID_MARK")
    reject_call(pg, "get_marks", book, CONV, error="INVALID_MARK")

    # Bỏ dấu: bắt buộc lý do, giữ vết, không bỏ hai lần.
    reject_call(pg, "cancel_mark", note["id"], " ", error="REASON_REQUIRED")
    cancelled = call(pg, "cancel_mark", note["id"], "ghi nhầm khách")
    require((cancelled["status"], cancelled["cancel_reason"], cancelled["cancelled_by"]) == ("cancelled", "ghi nhầm khách", "harness"),
            f"cancel_mark: {cancelled}")
    reject_call(pg, "cancel_mark", note["id"], "lại", error="MARK_ALREADY_CANCELLED")
    reject_call(pg, "cancel_mark", 999999999, "x", error="MARK_NOT_FOUND")

    # Ngoài đường tiền: số dư chỉ đổi theo phiếu thu (đã hủy), sổ kia không đổi version.
    require(pg.value(money) == before, "marks/links changed outstanding balances")
    require(version(pg, other) == 0, "links must not bump customer.version")
