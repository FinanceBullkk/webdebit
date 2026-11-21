"""ZALO-THU-CHI-01 PR-3: xác nhận, sửa số, gắn đối tượng, loại khoản thu chi báo trong nhóm Zalo — ngoài đường tiền."""

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

CONV = "c3" * 32


def review(action: str, message: str, key: str, **fields) -> str:
    return json.dumps({"conversation_id": CONV, "message_id": message, "action": action, "request_id": key, **fields}, ensure_ascii=False)


def check_cash_review(pg: Pg) -> None:
    book = new_book(pg, ("2026-08-01", 1000))
    other = new_book(pg, ("2026-08-01", 50))
    money = ("SELECT jsonb_agg(to_jsonb(v) ORDER BY customer_id,debt_month) FROM sokhach.v_outstanding_month v "
             f"WHERE customer_id IN ({book},{other})")
    before = pg.value(money)
    versions = (version(pg, book), version(pg, other))

    # Xác nhận: `before` rỗng (giá trị đọc từ tin); bấm lặp cùng request_id trả dòng cũ, chỉ ghi một lần.
    first = call(pg, "record_cash_review", review("confirm", "m1", "cr-1"))
    require((first["before"], first["state"]["decision"], first["created_by"]) == ({}, "confirm", "harness"), f"confirm: {first}")
    again = call(pg, "record_cash_review", review("confirm", "m1", "cr-1"))
    require(again.get("replayed") is True and again["id"] == first["id"], f"repeated click: {again}")
    rows = pg.value("SELECT count(*) FROM sokhach.cash_report_review WHERE message_id='m1'")
    require(rows == "1", f"repeated click must write once, got {rows}")
    reject_call(pg, "record_cash_review", review("not_cash", "m1", "cr-1", reason="x"), error="IDEMPOTENCY_CONFLICT")

    # Sửa số: bỏ xác nhận cũ (đã xác nhận số cũ); `before` ghi trạng thái ngay trước.
    amount = call(pg, "record_cash_review", review("amount", "m1", "cr-2", amount_vnd="1500000"))
    require((amount["before"]["decision"], amount["state"]["amount_vnd"], amount["state"]["decision"]) == ("confirm", "1500000", None),
            f"amount: {amount}")
    for bad in ("0", "1,5", "-5", "99999999999999999999"):
        reject_call(pg, "record_cash_review", review("amount", "m1", "cr-3", amount_vnd=bad), error="INVALID_CASH_REVIEW")
    reject_call(pg, "record_cash_review", review("confirm", "m1", "cr-3", amount_vnd="5"), error="INVALID_CASH_REVIEW")

    # Gắn đối tượng: sổ có thật thì ghi; sổ, xe, người không có thì TARGET_NOT_FOUND; loại lạ thì INVALID_CASH_REVIEW.
    target = call(pg, "record_cash_review", review("target", "m1", "cr-4", target={"kind": "so", "id": book}))
    require((target["state"]["target"], target["state"]["amount_vnd"], target["before"]["amount_vnd"]) == ({"kind": "so", "id": book}, "1500000", "1500000"),
            f"target: {target}")
    for kind in ("so", "xe", "tai_xe"):
        reject_call(pg, "record_cash_review", review("target", "m1", f"cr-x-{kind}", target={"kind": kind, "id": 999999999}), error="TARGET_NOT_FOUND")
    reject_call(pg, "record_cash_review", review("target", "m1", "cr-5", target={"kind": "khac", "id": book}), error="INVALID_CASH_REVIEW")
    reject_call(pg, "record_cash_review", review("target", "m1", "cr-5"), error="INVALID_CASH_REVIEW")

    # Loại: bắt buộc lý do; thiếu hay chỉ khoảng trắng đều bị từ chối và không ghi dòng nào.
    reject_call(pg, "record_cash_review", review("not_cash", "m2", "cr-6"), error="REASON_REQUIRED")
    reject_call(pg, "record_cash_review", review("not_cash", "m2", "cr-6", reason="   "), error="REASON_REQUIRED")
    require(pg.value("SELECT count(*) FROM sokhach.cash_report_review WHERE message_id='m2'") == "0", "rejected not_cash wrote a row")
    dropped = call(pg, "record_cash_review", review("not_cash", "m2", "cr-7", reason="tin hỏi giá"))
    require((dropped["state"]["decision"], dropped["reason"]) == ("not_cash", "tin hỏi giá"), f"not_cash: {dropped}")
    restored = call(pg, "record_cash_review", review("confirm", "m2", "cr-8"))
    require((restored["before"]["decision"], restored["state"]["decision"]) == ("not_cash", "confirm"), f"confirm after not_cash: {restored}")
    for bad in ({"conversation_id": "x"}, {"message_id": "../m1"}, {"action": "delete"}, {"request_id": " "}):
        reject_call(pg, "record_cash_review", json.dumps({**json.loads(review("confirm", "m3", "cr-9")), **bad}), error="INVALID_CASH_REVIEW")

    # Đọc: trạng thái hiệu lực theo tin; tin chưa có dòng thì không có khóa; dòng cũ giữ nguyên (chỉ thêm dòng).
    states = call(pg, "get_cash_reviews", json.dumps({"message_ids": ["m1", "m2", "m3"]}))["reviews"]
    require(sorted(states) == ["m1", "m2"] and (states["m1"]["reviews"], states["m1"]["target"], states["m2"]["decision"]) == (3, {"kind": "so", "id": book}, "confirm"),
            f"get_cash_reviews: {states}")
    require(pg.value("SELECT string_agg(action, ',' ORDER BY id) FROM sokhach.cash_report_review") == "confirm,amount,target,not_cash,confirm",
            "reviews must only be appended")
    # Gửi lại cùng request_id: đúng nội dung thì trả dòng cũ; khác số, đối tượng hay lý do thì từ chối (không âm thầm giữ số cũ).
    call(pg, "record_cash_review", review("amount", "m4", "cr-a", amount_vnd="5000000"))
    require(call(pg, "record_cash_review", review("amount", "m4", "cr-a", amount_vnd="5000000")).get("replayed") is True, "exact replay")
    reject_call(pg, "record_cash_review", review("amount", "m4", "cr-a", amount_vnd="4500000"), error="IDEMPOTENCY_CONFLICT")
    call(pg, "record_cash_review", review("target", "m4", "cr-b", target={"kind": "so", "id": book}))
    reject_call(pg, "record_cash_review", review("target", "m4", "cr-b", target={"kind": "so", "id": other}), error="IDEMPOTENCY_CONFLICT")
    call(pg, "record_cash_review", review("not_cash", "m4", "cr-c", reason="trùng tin"))
    require(call(pg, "record_cash_review", review("not_cash", "m4", "cr-c", reason="  trùng tin ")).get("replayed") is True, "replay trims reason")
    reject_call(pg, "record_cash_review", review("not_cash", "m4", "cr-c", reason="lý do khác"), error="IDEMPOTENCY_CONFLICT")
    reject_call(pg, "record_cash_review", json.dumps({**json.loads(review("not_cash", "m4", "cr-c", reason="trùng tin")), "conversation_id": "d4" * 32}),
                error="IDEMPOTENCY_CONFLICT")
    require(pg.value("SELECT count(*) FROM sokhach.cash_report_review WHERE message_id='m4'") == "3", "conflicting replays must not write")
    reject_call(pg, "get_cash_reviews", json.dumps({"message_ids": ["../x"]}), error="INVALID_CASH_REVIEW")
    reject_call(pg, "get_cash_reviews", json.dumps({"message_ids": "m1"}), error="INVALID_CASH_REVIEW")

    # Ngoài đường tiền: số dư từng tháng và version của sổ không đổi.
    require(pg.value(money) == before, "reviews changed outstanding balances")
    require((version(pg, book), version(pg, other)) == versions, "reviews must not bump customer.version")

    # Quyền: app ghi và đọc qua hàm; reader chỉ đọc; không role nào chạm bảng hay hàm phụ trực tiếp.
    pg.true("has_function_privilege('sokhach_app','sokhach.record_cash_review(jsonb)','EXECUTE')", "app cannot record a review")
    pg.true("NOT has_function_privilege('sokhach_reader','sokhach.record_cash_review(jsonb)','EXECUTE')", "reader can record a review")
    pg.true("NOT has_function_privilege('public','sokhach.record_cash_review(jsonb)','EXECUTE')", "PUBLIC can record a review")
    for role in ("sokhach_app", "sokhach_reader"):
        pg.true(f"has_function_privilege('{role}','sokhach.get_cash_reviews(jsonb)','EXECUTE')", f"{role} cannot read reviews")
        pg.true(f"NOT has_table_privilege('{role}','sokhach.cash_report_review','SELECT,INSERT,UPDATE,DELETE')", f"{role} touches the table")
        pg.true(f"NOT has_function_privilege('{role}','sokhach._cash_review_state(text,bigint)','EXECUTE')", f"{role} runs a helper")
