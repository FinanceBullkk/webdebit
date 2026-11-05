#!/usr/bin/env python3
"""Đọc log sửa Sheet do Apps Script ghi (SHEET-LOG-01, specs/sheet-log-doi-soat.md). Chỉ đọc, không bao giờ ghi tiền theo log.

Log thiếu lần sửa qua API, thường không có giá trị cũ và không biết ai sửa, nên chỉ dùng để giải thích: tab nào vừa sửa, sửa gì, lúc nào.
Đọc phần đuôi, bỏ cột nội dung: dòng SNAPSHOT mỗi ô tới 20.000 ký tự, cả tab EVENTS rất lớn.

Tra tay trên hao, cùng biến môi trường với runner (có tên khách và số tiền, không chép ra ngoài):

    v7_sheet_log.py                      các tab sửa trong 24 giờ qua
    v7_sheet_log.py --tab "TEN TAB"      từng lần sửa của một tab
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys
import urllib.parse
import urllib.request
from collections import Counter
from collections.abc import Callable, Iterable
from typing import Any
from zoneinfo import ZoneInfo

import sheet_sync_runner
from webdebit_export_connector import _fetch_values

TAB = "EVENTS"
# Khớp CAPTURE_HEADERS của scripts/sheet-capture/Code.gs, bỏ cột cuối payload_json.
HEADERS = ("id", "captured_at_utc", "kind", "sheet_id", "sheet_name", "range", "actor_if_available", "group_id", "part", "parts")
# Ngày đông nhất tới nay khoảng 1.500 dòng (4/11/2026): đủ cho một ngày, và giờ gần đây là phần đối soát cần.
TAIL_ROWS = 3000
# Đo log 21/10–5/11/2026: 93,5% khoảng nghỉ giữa hai lần sửa một tab không quá 15 phút; tab yên quá 15 phút thì 7% có sửa tiếp trong giờ sau.
EDITING_MINUTES = 15
# Quét bù hằng ngày luôn ghi một dòng INVENTORY, nên quá chừng này không có dòng nào là bộ ghi đã dừng.
STALE_HOURS = 26
# Chỉ các kết luận "chưa rõ vì sao lệch": máy ghi lỗi hay ghi xong không khớp thì vẫn phải có người xem, dù tab có đang sửa.
EDITING_REASONS = frozenset({"NO_EXACT_FIX", "NOTHING_TO_WRITE", "AMBIGUOUS_FIX", "SHEET_SHUFFLED", "TOO_MANY_GROUPS", "HELD"})
VN = ZoneInfo("Asia/Ho_Chi_Minh")
_BATCH = 100
Opener = Callable[..., Any]


def tab_key(value: Any) -> str:
    """Cùng cách so tên với v7_reconcile_sheet.name: tên tab Sheet hay có khoảng trắng thừa."""
    return " ".join(str(value).split())


def _get_json(url: str, token: str, opener: Opener) -> dict[str, Any]:
    request = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    with opener(request, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def _checked_id(log_id: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_-]+", log_id):
        raise ValueError("invalid spreadsheet ID")
    return log_id


def _row_count(log_id: str, token: str, opener: Opener) -> int:
    fields = urllib.parse.quote("sheets.properties(title,gridProperties.rowCount)", safe="")
    meta = _get_json(f"https://sheets.googleapis.com/v4/spreadsheets/{_checked_id(log_id)}?fields={fields}", token, opener)
    for sheet in meta.get("sheets") or []:
        if sheet["properties"]["title"] == TAB:
            return int(sheet["properties"]["gridProperties"]["rowCount"])
    raise ValueError("EDIT_LOG_NO_TAB")


def _parsed_at(value: Any) -> dt.datetime | None:
    try:
        moment = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return moment if moment.tzinfo else None


def read_tail(log_id: str, token: str, opener: Opener = urllib.request.urlopen, rows: int = TAIL_ROWS) -> list[dict[str, Any]]:
    """Các sự kiện ở đuôi log, cũ trước mới sau, không có nội dung. Tiêu đề đổi thì báo lỗi, không đoán cột."""
    if tuple(_fetch_values(log_id, token, opener, f"{TAB}!A1:J1")[0]) != HEADERS:
        raise ValueError("EDIT_LOG_FORMAT")
    last = _row_count(log_id, token, opener)
    first = max(2, last - rows + 1)
    if last < first:
        return []
    time_col, kind_col, tab_col, range_col = (HEADERS.index(name) for name in ("captured_at_utc", "kind", "sheet_name", "range"))
    events = []
    for number, row in enumerate(_fetch_values(log_id, token, opener, f"{TAB}!A{first}:J{last}"), start=first):
        cells = [*row, *[""] * len(HEADERS)]
        moment = _parsed_at(cells[time_col])
        if moment is not None:
            events.append({"row": number, "at": moment, "kind": cells[kind_col], "tab": tab_key(cells[tab_col]), "range": cells[range_col]})
    return events


def summarize(events: Iterable[dict[str, Any]], now: dt.datetime) -> tuple[dict[str, Any], dict[str, dt.datetime]]:
    """(tình trạng log, lần sửa cuối từng tab). Log không còn dòng mới thì là STALE: không có dòng EDIT không có nghĩa là không ai sửa."""
    last_event, last_edits = None, {}
    for event in events:
        last_event = max(last_event, event["at"]) if last_event else event["at"]
        if event["kind"] == "EDIT":
            last_edits[event["tab"]] = max(last_edits.get(event["tab"], event["at"]), event["at"])
    if last_event is None:
        return {"status": "STALE", "last_event_at": None}, {}
    status = "STALE" if now - last_event > dt.timedelta(hours=STALE_HOURS) else "OK"
    return {"status": status, "last_event_at": last_event.astimezone(VN).isoformat(timespec="seconds")}, last_edits


def annotate(rows: Iterable[dict[str, Any]], last_edits: dict[str, dt.datetime], downloaded_at: dt.datetime) -> None:
    """Ghi lần sửa cuối vào khách chưa khớp; tab sửa từ `EDITING_MINUTES` trước lúc tải trở đi thì đánh dấu `sheet_editing`. Không đổi kết luận."""
    since = downloaded_at - dt.timedelta(minutes=EDITING_MINUTES)
    for row in rows:
        last = last_edits.get(tab_key(row["customer"])) if row["status"] != "KHOP" else None
        if last is None:
            continue
        row["sheet_last_edit_at"] = last.astimezone(VN).isoformat(timespec="seconds")
        if last >= since and row.get("reason") in EDITING_REASONS:
            row["sheet_editing"] = True


def read_payloads(log_id: str, token: str, numbers: list[int], opener: Opener = urllib.request.urlopen) -> dict[int, str]:
    """Ô nội dung của đúng các dòng cần xem, để khỏi tải cả SNAPSHOT nằm xen giữa."""
    found: dict[int, str] = {}
    for start in range(0, len(numbers), _BATCH):
        part = numbers[start:start + _BATCH]
        query = "&".join("ranges=" + urllib.parse.quote(f"{TAB}!K{number}", safe="!") for number in part)
        data = _get_json(f"https://sheets.googleapis.com/v4/spreadsheets/{_checked_id(log_id)}/values:batchGet?{query}", token, opener)
        for number, item in zip(part, data.get("valueRanges") or [], strict=False):
            values = item.get("values") or [[""]]
            found[number] = values[0][0] if values[0] else ""
    return found


def _short(value: Any) -> str:
    text = " ".join(str(value).split())
    return text if len(text) <= 60 else text[:57] + "..."


def describe(payload: str) -> str:
    """Một lần sửa thành một câu. Sửa nhiều ô thì chỉ nói số ô; không có giá trị cũ là sửa ô trống hoặc dán, không phải cũ bằng 0."""
    try:
        data = json.loads(payload)
    except ValueError:
        return "(nội dung dài hoặc không đọc được)"
    values = data.get("values")
    if isinstance(values, list) and sum(len(row) for row in values) > 1:
        return f"sửa {sum(len(row) for row in values)} ô"
    new = data["event_value"] if data.get("event_value_available") else (values[0][0] if values and values[0] else None)
    new_text = "(trống)" if new in ("", None) else _short(new)
    return f"{_short(data['old_value'])} → {new_text}" if data.get("old_value_available") else new_text


def _clock(moment: dt.datetime) -> str:
    return moment.astimezone(VN).strftime("%d/%m %H:%M:%S")


def report(events: list[dict[str, Any]], log_id: str, token: str, tab: str | None, hours: float, now: dt.datetime,
           opener: Opener = urllib.request.urlopen) -> list[str]:
    edits = [event for event in events if event["kind"] == "EDIT" and now - event["at"] <= dt.timedelta(hours=hours)]
    if tab is None:
        counts = Counter(event["tab"] for event in edits)
        last = {event["tab"]: event["at"] for event in edits}
        return [f"{_clock(last[name])}  {count:>4} lần  {name}" for name, count in sorted(counts.items(), key=lambda item: last[item[0]], reverse=True)]
    chosen = [event for event in edits if event["tab"] == tab_key(tab)]
    payloads = read_payloads(log_id, token, [event["row"] for event in chosen], opener)
    return [f"{_clock(event['at'])}  {event['range']:<12}  {describe(payloads.get(event['row'], ''))}" for event in chosen]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--tab", help="tên tab; không có thì liệt kê các tab đã sửa")
    parser.add_argument("--hours", type=float, default=24.0)
    parser.add_argument("--rows", type=int, default=TAIL_ROWS, help="số dòng cuối của log được đọc; tra lâu hơn một ngày thì tăng lên")
    parser.add_argument("--log-id", default=os.getenv("WEBDEBIT_EDIT_LOG_ID"))
    parser.add_argument("--credentials", default=os.getenv("WEBDEBIT_GOOGLE_CREDENTIALS"))
    args = parser.parse_args(argv)
    if not args.log_id or not args.credentials:
        parser.error("cần --log-id/WEBDEBIT_EDIT_LOG_ID và --credentials/WEBDEBIT_GOOGLE_CREDENTIALS")
    token = sheet_sync_runner.exchange_token(sheet_sync_runner.load_credentials(args.credentials))
    now = dt.datetime.now(dt.UTC)
    events = read_tail(args.log_id, token, rows=args.rows)
    state, _ = summarize(events, now)
    if hasattr(sys.stdout, "reconfigure"):   # systemd-run --pipe có thể chạy locale không UTF-8
        sys.stdout.reconfigure(encoding="utf-8")
    print(f"Log: {state['status']}, dòng mới nhất {state['last_event_at']}. Không thấy lần sửa không có nghĩa là không ai sửa: sửa qua API không vào log.")
    for line in report(events, args.log_id, token, args.tab, args.hours, now):
        print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
