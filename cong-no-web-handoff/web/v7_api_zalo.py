"""ZALO-GROUP-01: API gắn group Zalo ↔ sổ và dấu tin (hứa trả, khách báo đã chuyển, ghi chú).

Ghi chú ngoài đường tiền như nhắc nợ (NHAC-NO-01): không version sổ, không vào số dư. Mỗi lệnh kiểm thân JSON
đủ chặt ở đây để DB không phải nhận chuỗi lạ (ép kiểu lỗi ở psql thành lỗi 500); DB kiểm lại lần nữa.
"""

from __future__ import annotations

import json
import re
from datetime import date, datetime, timedelta
from urllib.parse import parse_qs
from zoneinfo import ZoneInfo

from v7_api_tables import ERRORS, MAX_BIGINT
from v7_api_validate import bad, positive_int, valid_date, vnd

CONVERSATION = re.compile(r"[0-9a-f]{64}")
MESSAGE = re.compile(r"[0-9A-Za-z_-]{1,128}")
KINDS = ("promise", "paid_claim", "note")
MARK_FIELDS = {"customer_id", "kind", "idempotency_key", "amount_vnd", "on_date", "note", "conversation_id",
               "message_id", "message_at", "message_sender", "message_excerpt"}
LIMITS = {"note": 500, "message_sender": 200, "message_excerpt": 300, "idempotency_key": 200, "reason": 200}


def _body(raw: bytes) -> dict:
    try:
        body = json.loads(raw)
    except ValueError:
        body = None
    if not isinstance(body, dict):
        bad("INVALID_MARK", ERRORS["INVALID_MARK"][1])
    return body


def _text(body: dict, field: str, *, required: bool = False) -> str | None:
    value = body.get(field)
    if value is None and not required:
        return None
    if not isinstance(value, str) or not value.strip() or len(value) > LIMITS[field]:
        code = "REASON_REQUIRED" if field == "reason" else "INVALID_MARK"
        bad(code, ERRORS[code][1])
    return value


def today_vn() -> date:
    return datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")).date()


def handle_link(raw: bytes, runner, actor: str, *, unlink: bool = False) -> tuple[int, dict]:
    body = _body(raw)
    if (set(body) != ({"conversation_id", "customer_id", "reason"} if unlink else {"conversation_id", "customer_id"})
            or not isinstance(body["conversation_id"], str) or not CONVERSATION.fullmatch(body["conversation_id"])
            or not positive_int(body["customer_id"])):
        bad("INVALID_LINK", ERRORS["INVALID_LINK"][1])
    payload = {"conversation_id": body["conversation_id"], "customer_id": body["customer_id"]}
    if unlink:
        payload["reason"] = _text(body, "reason", required=True).strip()
    return 200, runner.run("unlink_zalo" if unlink else "link_zalo", payload, actor)


def handle_mark(raw: bytes, runner, actor: str, *, today: date | None = None) -> tuple[int, dict]:
    """POST /api/v7/marks. VND là chuỗi số nguyên dương như mọi lệnh tiền; ghi chú không có số tiền."""
    body = _body(raw)
    today = today or today_vn()
    kind = body.get("kind")
    if not set(body) <= MARK_FIELDS or kind not in KINDS or not positive_int(body.get("customer_id")):
        bad("INVALID_MARK", ERRORS["INVALID_MARK"][1])
    _text(body, "idempotency_key", required=True)
    amount, on_date = body.get("amount_vnd"), body.get("on_date")
    if kind == "note":
        if amount is not None or on_date is not None:
            bad("INVALID_MARK", ERRORS["INVALID_MARK"][1])
        _text(body, "note", required=True)
    else:
        if not vnd(amount) or amount == "0" or not valid_date(on_date):
            bad("INVALID_MARK", ERRORS["INVALID_MARK"][1])
        day = date.fromisoformat(on_date)
        # Hứa trả hẹn từ hôm nay tới một năm; khách báo đã chuyển là chuyện đã xảy ra (giờ VN), như DB.
        if (kind == "promise" and not today <= day <= today + timedelta(days=366)) or \
                (kind == "paid_claim" and not today - timedelta(days=366) <= day <= today):
            bad("INVALID_MARK_DATE", ERRORS["INVALID_MARK_DATE"][1])
        _text(body, "note")
    for field in ("message_sender", "message_excerpt"):
        _text(body, field)
    conversation, message, at = body.get("conversation_id"), body.get("message_id"), body.get("message_at")
    if conversation is not None and (not isinstance(conversation, str) or not CONVERSATION.fullmatch(conversation)):
        bad("INVALID_MARK", ERRORS["INVALID_MARK"][1])
    if message is not None and (conversation is None or not isinstance(message, str) or not MESSAGE.fullmatch(message)):
        bad("INVALID_MARK", ERRORS["INVALID_MARK"][1])
    if at is not None:
        try:
            parsed = datetime.fromisoformat(at) if isinstance(at, str) and len(at) <= 40 else None
        except ValueError:
            parsed = None
        if parsed is None or parsed.tzinfo is None or message is None:
            bad("INVALID_MARK", ERRORS["INVALID_MARK"][1])
    payload = {key: value for key, value in body.items() if value is not None}
    if isinstance(payload.get("note"), str):
        payload["note"] = payload["note"].strip()
    return 200, runner.run("record_mark", payload, actor)


def handle_cancel(raw: bytes, runner, actor: str) -> tuple[int, dict]:
    body = _body(raw)
    if set(body) != {"id", "reason"} or not positive_int(body["id"]):
        bad("INVALID_MARK", ERRORS["INVALID_MARK"][1])
    return 200, runner.run("cancel_mark", {"id": body["id"], "reason": _text(body, "reason", required=True).strip()}, actor)


def parse_marks(parts_query: str) -> tuple[str, dict]:
    """GET /api/v7/marks?customer=<id> hoặc ?conversation=<64 hex>: đúng một trong hai."""
    query = parse_qs(parts_query, keep_blank_values=True)
    if len(query) != 1 or any(len(values) != 1 for values in query.values()):
        bad()
    if "customer" in query:
        value = query["customer"][0]
        if not re.fullmatch(r"[1-9][0-9]{0,18}", value) or int(value) > MAX_BIGINT:
            bad()
        return "get_marks", {"customer_id": int(value)}
    if "conversation" in query and CONVERSATION.fullmatch(query["conversation"][0]):
        return "get_marks", {"conversation_id": query["conversation"][0]}
    bad()
