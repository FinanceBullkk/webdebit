"""Bảng chi tiết của sổ từ các tab "CHI TIET ..." trên Sheet (SO-CHI-TIET-01, specs/v7-so-chi-tiet.md). Chỉ đọc, chỉ để xem.

Tab chi tiết là bản chép bảng kê gửi khách: phí, cước tàu, VAT, tổng của từng container. Số nợ vẫn theo tab sổ; số ở đây không
được ghi vào sổ, khác sổ thì chỉ báo lệch. Có hai mẫu: bảng kê hai dòng mỗi container (dòng trên cước tàu, dòng dưới phần còn lại)
và bảng ủy thác một dòng (khách tự trả cước tàu). Sổ có hiện bảng hay không tính theo số container trùng, không theo tên tab.
"""

from __future__ import annotations

import datetime as dt
import re
import unicodedata
from collections import defaultdict
from collections.abc import Iterable
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from v7_sheet_queue import read_snapshot

TAB_PREFIX = "CHI TIET "
CONTAINER = re.compile(r"[A-Z]{4}\d{7}")
# Sổ hiện bảng chi tiết khi ít nhất một nửa container của sổ có trong tab chi tiết: một container dùng lại ở sổ khách khác không đủ.
MIN_SHARE = 0.5
MONEY_FIELDS = ("fee", "service", "truck", "of", "vat", "total")
EMPTY: dict[str, Any] = {"rows": [], "months": {}}

Tabs = Iterable[tuple[str, list[tuple[int, dict[str, str]]]]]


def normalized(value: Any) -> str:
    text = unicodedata.normalize("NFD", str(value).upper().replace("Đ", "D"))
    return re.sub(r"[^A-Z0-9]+", " ", "".join(char for char in text if not unicodedata.combining(char))).strip()


def number(value: Any) -> Decimal | None:
    try:
        parsed = Decimal(str(value).strip())
    except InvalidOperation:
        return None
    return parsed if parsed.is_finite() else None


def vnd(value: Decimal | None) -> str | None:
    """Tiền nguyên đồng; VAT trên bảng kê có thể lẻ thì làm tròn để hiện, không dùng để tính nợ."""
    return None if value is None else str(int(value.quantize(Decimal(1), rounding=ROUND_HALF_UP)))


def container_in(value: Any) -> str | None:
    found = CONTAINER.search(re.sub(r"\s+", "", str(value or "")).upper())
    return found.group(0) if found else None


def _columns(cells: dict[str, str], wanted: dict[str, str]) -> dict[str, str]:
    """Cột trái nhất có tiêu đề bắt đầu bằng chữ cần tìm, kể cả tiêu đề hai dòng."""
    found: dict[str, str] = {}
    for col, value in sorted(cells.items(), key=lambda item: (len(item[0]), item[0])):
        label = normalized(value)
        for key, prefix in wanted.items():
            if key not in found and label.startswith(prefix):
                found[key] = col
    return found


BILL_HEADERS = {"container": "SO CONT", "bill": "BILL", "ship": "TEN TAU", "pack": "NGAY DONG HANG", "etd": "ETD", "eta": "ETA",
                "from": "NOI DONG HANG", "to": "CANG DEN", "fee": "PHI PHAT SINH", "service": "PHI DICH VU", "truck": "CUOC VAN CHUYEN",
                "of": "CUOC VAN TAI QUOC TE", "vat": "VAT", "total": "TONG"}
TRUST_HEADERS = {"container": "CONTAINER NO", "ship": "HT", "bill": "SO BILL", "pack": "NGAY", "from": "KHO", "to": "CANG DEN",
                 "of": "CUOC TAU OF", "truck": "CUOC XE", "service": "PHI DICH VU"}


def _next_col(col: str) -> str:
    return chr(ord(col) + 1)


def _text(rows: list[dict[str, str]], col: str | None) -> str:
    return next((str(row[col]).strip() for row in rows if col and str(row.get(col, "")).strip()), "")


def _sum(rows: list[dict[str, str]], col: str | None) -> Decimal | None:
    values = [value for value in (number(row.get(col, "")) for row in rows if col) if value is not None]
    return sum(values, Decimal(0)) if values else None


def _bill_rows(tab: str, data: list[tuple[int, dict[str, str]]], start: int, cols: dict[str, str]) -> list[dict[str, Any]]:
    """Bảng kê: mỗi container một hoặc hai dòng. Dòng chưa có phí mà dòng ngay dưới có phí là nửa trên của một cặp (không cần ô gộp)."""
    grid = dict(data)
    costs = [cols[key] for key in ("fee", "service", "truck") if key in cols]
    has_cost = lambda row: any(number(row.get(col, "")) for col in costs)  # noqa: E731
    label = cols.get("container")
    rows, position, numbers = [], 0, [row for row, _ in data if row > start]
    while position < len(numbers):
        row_no = numbers[position]
        cells = grid[row_no]
        if any(normalized(value).startswith("TONG") for col, value in cells.items() if col <= (label or "C")):
            break
        below = grid.get(row_no + 1)
        pair = bool(below) and not has_cost(cells) and has_cost(below) and not (container_in(cells.get(label)) and container_in(below.get(label)))
        block = [cells, below] if pair else [cells]
        position += 2 if pair else 1
        container = next((found for found in (container_in(item.get(label)) for item in block) if found), None)
        if not container:
            continue
        money = {key: _sum(block, cols.get(key)) for key in MONEY_FIELDS}
        base = sum((money[key] or Decimal(0) for key in ("fee", "service", "truck", "vat")), Decimal(0))
        total, of = money["total"], money["of"]
        # Cước tàu nằm trong Tổng thì mình thu; ngoài Tổng là khách tự trả.
        counted = bool(of) and total is not None and abs(total - base - of) < abs(total - base)
        rows.append(_row(tab, row_no, "bill", container, block, cols, money, counted))
    return rows


def _added(parts: list[Decimal | None]) -> Decimal | None:
    """Cộng các ô có số; không ô nào có số thì trống, không phải 0."""
    values = [part for part in parts if part is not None]
    return sum(values, Decimal(0)) if values else None


def _trust_money(cells: dict[str, str], cols: dict[str, str]) -> dict[str, Decimal | None]:
    """Cột VAT nằm ngay sau cột tiền của nó. Tổng là phần mình thu: cước xe + phí dịch vụ + VAT của hai khoản; OF hiện gồm cả VAT của OF."""
    def amount(key: str) -> Decimal | None:
        return number(cells.get(cols[key], "")) if key in cols else None

    def vat_of(key: str) -> Decimal | None:
        return number(cells.get(_next_col(cols[key]), "")) if key in cols else None

    truck, service = amount("truck"), amount("service")
    vat = _added([vat_of("truck"), vat_of("service")])
    return {"fee": None, "service": service, "truck": truck, "vat": vat, "total": _added([truck, service, vat]),
            "of": _added([amount("of"), vat_of("of")]) if amount("of") is not None else None}


def _trust_rows(tab: str, data: list[tuple[int, dict[str, str]]], start: int, cols: dict[str, str]) -> list[dict[str, Any]]:
    """Bảng ủy thác: một dòng mỗi container, khách tự trả cước tàu, không có cột tổng."""
    rows = []
    for row_no, cells in data:
        text = str(cells.get(cols["container"], "")).strip().upper()
        if row_no > start and re.fullmatch(r"[A-Z]{4}\d{7}", text):
            rows.append(_row(tab, row_no, "trust", text, [cells], cols, _trust_money(cells, cols), False))
    return rows


def _row(tab: str, row_no: int, layout: str, container: str, block: list[dict[str, str]], cols: dict[str, str],
         money: dict[str, Decimal | None], counted: bool) -> dict[str, Any]:
    return {"tab": tab, "row": row_no, "layout": layout, "container": container, "of_counted": counted,
            **{key: _text(block, cols.get(key)) for key in ("bill", "ship", "pack", "etd", "eta", "from", "to")},
            **{f"{key}_vnd": vnd(money[key]) for key in MONEY_FIELDS}}


def rows_from_tabs(tabs: Tabs) -> list[dict[str, Any]]:
    """Dòng chi tiết của mọi tab tên "CHI TIET ...". Tab không nhận ra mẫu thì bỏ qua: đây chỉ là phần để xem."""
    rows: list[dict[str, Any]] = []
    for title, data in tabs:
        if not normalized(title).startswith(TAB_PREFIX):
            continue
        for row_no, cells in data:
            labels = [normalized(value) for value in cells.values()]
            if any(label.startswith("CUOC VAN TAI QUOC TE") for label in labels):
                rows += _bill_rows(title, list(data), row_no, _columns(cells, BILL_HEADERS))
                break
            if any(label.startswith("CUOC TAU OF") for label in labels):
                rows += _trust_rows(title, list(data), row_no, _columns(cells, TRUST_HEADERS))
                break
    return rows


def load_detail_snapshot(path: str | Path) -> dict[str, Any]:
    return read_snapshot(path, "Detail snapshot")


def _serial_date(text: str) -> dt.date | None:
    value = number(text)
    if value is None or not 20000 <= value <= 80000:
        return None
    return dt.date(1899, 12, 30) + dt.timedelta(days=int(value))


def _port(value: Any) -> str:
    """Cảng đến gọn cho cột hẹp: bỏ phần chữ Hán sau tên ("SHEKOU- 蛇口" → "SHEKOU")."""
    return re.sub(r"[\s-]*[\u2e80-\u9fff\uf900-\ufaff□]+$", "", str(value or "").strip())


def short_day(value: Any, month: str) -> str:
    """Ngày trên bảng kê → dd/mm. Số ngày bị đảo ngày/tháng (ô hiểu theo tháng/ngày) thì đọc lại theo tháng của sổ và tháng sau đó."""
    text = str(value or "").strip()
    day = _serial_date(text)
    if day is not None:
        near = {int(month[5:7]), int(month[5:7]) % 12 + 1} if month else set()
        if day.month not in near and day.day in near:
            return f"{day.month:02d}/{day.day:02d}"
        return f"{day.day:02d}/{day.month:02d}"
    found = re.fullmatch(r"(\d{1,2})/(\d{1,2})/\d+(?:\s.*)?", text)
    return f"{int(found.group(1)):02d}/{int(found.group(2)):02d}" if found else text[:10]


def _legacy_items(ledger: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """(dòng có container, dòng tiền không container còn lại). Dòng không container là nửa kia của container ngay trên, nếu không thì ngay dưới."""
    rows = sorted((row for row in ledger.get("legacy_rows") or [] if row.get("kind") == "trip" and not (row.get("current") or {}).get("deleted")),
                  key=lambda row: (row.get("display") or {}).get("row") or 0)
    by_row = {(row.get("display") or {}).get("row"): row for row in rows}
    has_container = lambda row: bool(row and str((row.get("current") or {}).get("container") or "").strip())  # noqa: E731
    money = lambda row: int((row.get("current") or {}).get("counted_vnd") or 0)  # noqa: E731
    taken: dict[int, int] = {}
    loose = []
    for row in rows:
        if has_container(row) or not money(row):
            continue
        row_no = (row.get("display") or {}).get("row")
        above, below = by_row.get(row_no - 1) if row_no else None, by_row.get(row_no + 1) if row_no else None
        host = next((item for item in (above, below) if has_container(item) and item["id"] not in taken), None)
        if host:
            taken[host["id"]] = money(row)
        else:
            loose.append(row)
    return ([{"kind": "legacy", "id": row["id"], "month": str((row["current"] or {}).get("month") or row.get("month"))[:7],
              "container": str(row["current"]["container"]).strip().upper(), "date": row["current"].get("event_date"),
              "origin": row["current"].get("origin"), "destination": row["current"].get("destination"), "carrier": row["current"].get("carrier"),
              "ledger_vnd": money(row) + taken.get(row["id"], 0)} for row in rows if has_container(row)], loose)


def project_details(snapshot: dict[str, Any], ledger: dict[str, Any]) -> dict[str, Any]:
    """`sheet_details` của GET sổ: bảng theo tháng cho sổ có tab chi tiết; sổ khác rỗng. Mọi số là chuỗi VND nguyên."""
    by_container: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in snapshot.get("rows") or []:
        by_container[row.get("container")].append(row)
    legacy, loose = _legacy_items(ledger)
    trips = [{"kind": "trip", "id": trip["id"], "month": str(trip.get("month"))[:7], "container": str(trip.get("container") or "").strip().upper(),
              "date": trip.get("event_date"), "origin": trip.get("origin"), "destination": trip.get("destination"), "carrier": trip.get("carrier"),
              "ledger_vnd": int(trip.get("amount_vnd") or 0)}
             for trip in ledger.get("trips") or [] if not trip.get("deleted") and trip.get("status") != "rejected" and trip.get("container")]
    items = legacy + trips
    containers = {item["container"] for item in items}
    if not containers or sum(1 for container in containers if container in by_container) < len(containers) * MIN_SHARE:
        return dict(EMPTY)
    # Container dùng lại: lần cuối trong sổ ứng với lần cuối trên bảng kê (bảng kê có thể có từ trước khi sổ mở).
    matched: dict[int, dict[str, Any]] = {}
    occurrences: dict[str, list[int]] = defaultdict(list)
    for index, item in enumerate(items):
        occurrences[item["container"]].append(index)
    for container, indexes in occurrences.items():
        ordered = sorted(indexes, key=lambda index: (str(items[index]["date"] or ""), index))
        for index, detail in zip(reversed(ordered), reversed(by_container.get(container, [])), strict=False):
            matched[index] = detail
    months: dict[str, dict[str, Any]] = {}
    charges = {str(item.get("month"))[:7]: item.get("charges_vnd") for item in ledger.get("months") or []}
    rows = []
    for index, item in enumerate(items):
        detail = matched.get(index)
        month = item["month"]
        sheet_total = detail.get("total_vnd") if detail else None
        ledger_vnd = item["ledger_vnd"]
        # Cột Tổng luôn là số của sổ (SO-CHI-TIET-01); bảng kê cũ không được làm người đọc tưởng đó là nợ.
        shown = str(ledger_vnd) if ledger_vnd else None
        differs = sheet_total is not None and abs(int(sheet_total) - ledger_vnd) > 1
        rows.append({"kind": item["kind"], "id": item["id"], "month": month, "container": item["container"], "has_detail": detail is not None,
                     "day": short_day(item["date"], "") if item["date"] and len(str(item["date"])) != 10 else _iso_day(item["date"]),
                     "bill": detail.get("bill", "") if detail else "", "ship": (detail.get("ship") or item["carrier"] or "") if detail else (item["carrier"] or ""),
                     "etd": short_day(detail.get("etd"), month) if detail else "", "eta": short_day(detail.get("eta"), month) if detail else "",
                     "from": (detail.get("from") or item["origin"] or "") if detail else (item["origin"] or ""),
                     "to": _port((detail.get("to") or item["destination"]) if detail else item["destination"]),
                     "of_counted": bool(detail and detail.get("of_counted")), "total_vnd": shown, "sheet_total_vnd": sheet_total, "ledger_vnd": str(ledger_vnd), "differs": differs,
                     **{f"{key}_vnd": detail.get(f"{key}_vnd") if detail else None for key in ("fee", "service", "truck", "of", "vat")}})
        summary = months.setdefault(month, {"fee": 0, "service": 0, "truck": 0, "vat": 0, "of_counted": 0, "of_customer": 0, "total": 0,
                                            "sheet_diff": 0, "no_detail": 0, "differs": []})
        if detail:
            for key in ("fee", "service", "truck", "vat"):
                summary[key] += int(detail.get(f"{key}_vnd") or 0)
            summary["of_counted" if detail.get("of_counted") else "of_customer"] += int(detail.get("of_vnd") or 0)
        else:
            summary["no_detail"] += 1
        summary["total"] += int(shown or 0)
        if differs:
            summary["differs"].append(item["container"])
            summary["sheet_diff"] += int(sheet_total) - ledger_vnd
    for row in loose:
        current = row["current"]
        month = str(current.get("month") or row.get("month"))[:7]
        rows.append({"kind": "legacy", "id": row["id"], "month": month, "container": "", "has_detail": False, "day": _iso_day(current.get("event_date")),
                     "bill": "", "ship": "", "etd": "", "eta": "", "from": "", "to": "", "of_counted": False, "total_vnd": str(current["counted_vnd"]),
                     "sheet_total_vnd": None, "ledger_vnd": str(current["counted_vnd"]), "differs": False, **{f"{key}_vnd": None for key in ("fee", "service", "truck", "of", "vat")}})
        summary = months.setdefault(month, {"fee": 0, "service": 0, "truck": 0, "vat": 0, "of_counted": 0, "of_customer": 0, "total": 0,
                                            "sheet_diff": 0, "no_detail": 0, "differs": []})
        summary["total"] += int(current["counted_vnd"])
    return {"rows": rows, "months": {month: {**{f"{key}_vnd": str(value[key]) for key in ("fee", "service", "truck", "vat", "of_counted", "of_customer", "total", "sheet_diff")},
                                             "no_detail": value["no_detail"], "differs": value["differs"], "charges_vnd": charges.get(month),
                                             "diff_vnd": None if charges.get(month) is None else str(int(charges[month]) - value["total"])}
                                     for month, value in months.items()}}


def _iso_day(value: Any) -> str:
    text = str(value or "")
    return f"{text[8:10]}/{text[5:7]}" if re.fullmatch(r"\d{4}-\d\d-\d\d", text) else ""
