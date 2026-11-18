"""Kết luận sức khỏe từng tab của Sheet sổ nợ (KIEM-TAB-01, specs/v7-kiem-tab-truoc-khi-ghi.md, K1).

Không sửa bộ quét: nhận kết quả `v7_load_real_copy.scan_tabs` / `scan_workbook` và, để nêu đúng ô, các dòng thô của chính tab đó
(`(tên tab, [(số dòng, {chữ cột: chữ trong ô})])`, cùng thứ do `workbook_rows` hay `fetch_tabs` trả). Trả `{tab: {status, findings}}`.
Mọi luật kiểm mới của K1 (`chain_break` nêu ô, `negative_receipt`, `duplicate_container`) thêm ở đây, không ở bộ quét: cổng của
`Deploy hao` chặn mọi diff có `tools/v7_load*`.

Tab `broken` khi có phát hiện mức `error`: lỗi bộ quét đã đếm (`issues`, đúng các lỗi làm máy giữ khách), `row_shift`,
`negative_receipt`. Mức `warning` (`duplicate_container`: đáng xem, không đổi tiền) và `note` (bố cục hai dòng đã duyệt) có trong
`findings` để màn và lượt đo thấy, nhưng không làm tab `broken`.
"""

from __future__ import annotations

import itertools
import re
from collections import Counter
from collections.abc import Iterable
from typing import Any

from v7_load_real_copy import BLOCK_TITLE, block_month, col_num, header_key, normalized
from v7_normalize import container_key  # lớp web; tools được phép gọi

# Bố cục "hai dòng mỗi container" (dòng container không tiền, dòng tiền không container ngay dưới) và "tiền lệch một dòng" nhìn như nhau
# trong dữ liệu; chỉ người biết tab mới phân được. Khai tay từng tab, không suy ra từ dữ liệu, không dùng ngưỡng số cặp.
# "KK - DỪA": audit 4/11/2026 (kết quả chỉ ở ghi chú phiên, không có file trong repo): hai dòng mỗi container, tổng khớp tới từng đồng,
# nạp thành "Phí lẻ". Đo trên hao 16/11/2026: các khối T8–T11/2026 của tab đều theo bố cục này.
# Claude chốt 16/11/2026 theo quyền người dùng trao 21/10/2026. Thêm tab mới vào đây chỉ sau khi có audit tương tự.
TWO_ROW_LAYOUT_TABS = frozenset({normalized("KK - DỪA")})
CONTAINER_FIRST, MONEY_FIRST = "container_first", "money_first"
COLUMN_LETTERS = re.compile(r"[A-Z]{1,3}")


def column_letter(index: int) -> str:
    """Số cột (1 = A) sang chữ cột Sheet: 1 → A, 26 → Z, 27 → AA, 702 → ZZ, 703 → AAA."""
    if type(index) is not int or index < 1:
        raise ValueError("column index starts at 1")
    letters = ""
    while index:
        index, rest = divmod(index - 1, 26)
        letters = chr(ord("A") + rest) + letters
    return letters


def cell_name(column: str | int | None, row: int) -> str | None:
    """Địa chỉ A1 của ô từ chữ cột (hoặc số cột) và số dòng; không biết cột thì None."""
    if column is None:
        return None
    if type(column) is int:
        return f"{column_letter(column)}{row}"
    if not COLUMN_LETTERS.fullmatch(column):
        return None
    return f"{column_letter(col_num(column))}{row}"


def columns_by_row(rows: Iterable[tuple[int, dict[str, str]]]) -> dict[int, dict[str, str]]:
    """{số dòng: {"container", "total", "receipt", "anchor": chữ cột}} theo dòng tiêu đề đang hiệu lực ở dòng đó, tính như bộ quét: cột trái nhất
    cho mỗi tiêu đề, tiêu đề của bảng phụ bên phải không thay bảng chính, tiêu đề khối mới xóa cột cũ."""
    found: dict[int, dict[str, str]] = {}
    columns: dict[str, str] = {}
    for row_no, cells in rows:
        titled = [(col, value) for col, value in cells.items() if col in ("A", "B", "C")]
        if any(block_month(value) or BLOCK_TITLE in normalized(value) for _, value in titled):
            columns = {}
        else:
            detected: dict[str, str] = {}
            for col, value in sorted(cells.items(), key=lambda item: col_num(item[0])):
                key = header_key(normalized(value))
                if key and key not in detected:
                    detected[key] = col
            side = bool(columns.get("container") and "container" in detected and detected["container"] != columns["container"])
            if "container" in detected and "total" in detected and not side:
                columns = {**columns, **detected}
        found[row_no] = {key: columns[key] for key in ("container", "total", "receipt", "anchor") if key in columns}
    return found


def _shift_pairs(trips: list[dict]) -> list[tuple[dict, dict, str]]:
    """(dòng container không tiền, dòng tiền không container, thứ tự) cho các cặp dòng chuyến sát nhau (số dòng hơn kém 1, không dòng
    chuyến nào xen giữa). Ưu tiên "container trên, tiền dưới"; còn dòng container chưa ghép mới xét "tiền trên, container dưới", và
    dòng tiền nằm ngay dưới một dòng container có tiền là phí của dòng đó, không ghép. Mỗi dòng nằm trong nhiều nhất một cặp."""
    def holder(record):
        return bool(record["container"]) and record["amount"] in (None, 0)

    def money(record):
        return not record["container"] and record["amount"] not in (None, 0)

    def adjacent(upper, lower):
        return lower["row"] == upper["row"] + 1
    used: set[int] = set()
    found: list[tuple[dict, dict, str]] = []
    for upper, lower in itertools.pairwise(trips):
        if holder(upper) and money(lower) and adjacent(upper, lower):
            used.update((upper["row"], lower["row"]))
            found.append((upper, lower, CONTAINER_FIRST))
    for index in range(1, len(trips)):
        upper, lower = trips[index - 1], trips[index]
        if holder(lower) and money(upper) and adjacent(upper, lower) and not {upper["row"], lower["row"]} & used:
            above = trips[index - 2] if index >= 2 else None
            if above is not None and adjacent(above, upper) and above["container"] and above["amount"] not in (None, 0):
                continue   # dòng tiền ngay dưới một chuyến đã có tiền: phí của chuyến đó
            used.update((upper["row"], lower["row"]))
            found.append((lower, upper, MONEY_FIRST))
    return sorted(found, key=lambda pair: min(pair[0]["row"], pair[1]["row"]))


def row_shift_findings(block: dict, columns: dict[int, dict[str, str]] | None = None, approved_layout: bool = False) -> list[dict]:
    """`row_shift`: tiền nằm lệch một dòng so với container, trong cùng khối tháng.

    Hai dòng chuyến sát nhau: một dòng có container mà TỔNG trống hoặc 0, dòng kia có TỔNG khác 0 mà không container. Dòng "có tiền,
    không container" đứng một mình vẫn là phí riêng; chỉ cặp sát nhau như vậy mới là dấu hiệu lệch, và khi đó không ai biết tiền thuộc
    dòng nào. `columns` (từ `columns_by_row`) để nêu ô; thiếu thì không nêu ô.

    `approved_layout`: tab trong TWO_ROW_LAYOUT_TABS. Khối đều đặn (mọi cặp đều "container trên, tiền ngay dưới") thì các cặp thành chú
    thích `two_row_layout`, không chặn; khối có một cặp ngược (tiền trên, container dưới) vẫn là `row_shift` ở mọi cặp của khối.
    """
    columns = columns or {}
    pairs = _shift_pairs([record for record in block["records"] if record["kind"] == "trip"])
    regular = approved_layout and all(order == CONTAINER_FIRST for _, _, order in pairs)
    found = []
    for holder, money, order in pairs:
        cells = [cell for cell in (cell_name(columns.get(holder["row"], {}).get("container"), holder["row"]),
                                   cell_name(columns.get(money["row"], {}).get("total"), money["row"])) if cell]
        rows = sorted((holder["row"], money["row"]))
        if regular:
            found.append({"kind": "two_row_layout", "level": "note", "month": block["month"], "rows": rows, "cells": cells,
                          "message": f"Dòng {rows[0]} và {rows[1]}: bố cục hai dòng đã duyệt của tab này."})
            continue
        found.append({"kind": "row_shift", "level": "error", "month": block["month"], "rows": rows, "order": order, "cells": cells,
                      "message": f"Dòng {holder['row']} có container mà không có tiền, dòng {money['row']} có tiền mà không có container: "
                                 "tiền có thể nằm lệch một dòng.",
                      "fix": f"Đưa tiền ở dòng {money['row']} về cùng dòng với container ở dòng {holder['row']} (hoặc ngược lại), "
                             "rồi chờ máy đọc lại Sheet."})
    return found


def negative_receipt_findings(data: dict, columns: dict[int, dict[str, str]] | None = None) -> list[dict]:
    """`negative_receipt`: số âm ở cột thu. Web chưa có loại "chi trả khách" (K5 chưa chốt), nên số âm làm tab không đọc được; nêu đúng ô."""
    columns = columns or {}
    found = []
    for record in data.get("records", []):
        if record["kind"] != "receipt" or record["amount"] is None or record["amount"] >= 0:
            continue
        cell = cell_name(columns.get(record["row"], {}).get("receipt"), record["row"])
        found.append({"kind": "negative_receipt", "level": "error", "month": record["month"], "rows": [record["row"]],
                      "cells": [cell] if cell else [],
                      "message": f"Ô thu ở dòng {record['row']} là số âm ({record['amount']:,} đ). Web chưa có loại chi trả lại khách, nên chưa đọc được.".replace(",", "."),
                      "fix": "Nếu là tiền trả lại khách thì ghi ở chỗ khác ngoài cột thu; nếu gõ nhầm dấu thì sửa thành số dương."})
    return found


def duplicate_container_findings(block: dict, columns: dict[int, dict[str, str]] | None = None) -> list[dict]:
    """`duplicate_container` (mức `warning`): cùng container ở hai dòng chuyến trong một khối tháng mà một dòng không có tiền. Không
    đổi tiền (dòng không tiền cộng 0), nhưng thường là dòng gõ lặp hoặc tiền ghi nhầm dòng, đáng xem. Dòng cùng container có tiền cả
    hai là chuyến dùng lại, không báo."""
    columns = columns or {}
    seen: dict[str, list[dict]] = {}
    for record in block["records"]:
        key = container_key(record["container"]) if record["kind"] == "trip" else ""
        if key:
            seen.setdefault(key, []).append(record)
    found = []
    for same in seen.values():
        empty = [r for r in same if r["amount"] in (None, 0)]
        paid = [r for r in same if r["amount"] not in (None, 0)]
        if len(same) < 2 or not empty or not paid:
            continue
        rows = sorted(r["row"] for r in same)
        found.append({"kind": "duplicate_container", "level": "warning", "month": block["month"], "rows": rows,
                      "cells": [cell for r in sorted(same, key=lambda x: x["row"])
                                if (cell := cell_name(columns.get(r["row"], {}).get("container"), r["row"]))],
                      "message": f"Cùng một container ở các dòng {', '.join(map(str, rows))}, trong đó dòng {', '.join(str(r['row']) for r in empty)} không có tiền.",
                      "fix": "Xem dòng không có tiền là dòng gõ lặp (xóa) hay tiền ghi nhầm dòng (đưa tiền về đúng dòng)."})
    return found


def block_anchors(data: dict, columns: dict[int, dict[str, str]] | None = None) -> dict[str, str]:
    """{tháng: ô số dư cuối tháng} của từng khối (dòng TỔNG, cột số còn phải thu cuối tháng) khi biết được cột và dòng."""
    columns = columns or {}
    found = {}
    for month, block in sorted(data.get("blocks", {}).items()):
        row = block.get("anchor_row")
        cell = cell_name(columns.get(row, {}).get("anchor"), row) if type(row) is int else None
        if cell and block.get("anchor") is not None:
            found[month] = cell
    return found


def tab_health(issues: Counter | dict[str, int], shifts: list[dict]) -> dict[str, Any]:
    """`ok`, hoặc `broken` khi bộ quét đã đếm lỗi (`issues`) hay có phát hiện mức `error`. Lỗi bộ quét đã có phát hiện riêng nêu ô (số
    âm ở cột thu) thì không kể hai lần."""
    covered = Counter({"INVALID_RECEIPT_AMOUNT": sum(f["kind"] == "negative_receipt" for f in shifts)})
    findings = [{"kind": code, "level": "error", "count": count} for code, count in sorted(issues.items())
                if count > covered.get(code, 0)] + list(shifts)
    return {"status": "broken" if any(f["level"] == "error" for f in findings) else "ok", "findings": findings}


def scan_health(scan: dict[str, dict], tabs: Iterable[tuple[str, Iterable[tuple[int, dict[str, str]]]]] | None = None) -> dict[str, dict]:
    """{tab: health} cho mọi tab trong kết quả của `scan_tabs`. `tabs`: các dòng thô cùng lượt đọc, để nêu đúng ô; thiếu thì
    phát hiện vẫn có, chỉ không có ô."""
    raw = {name: columns_by_row(rows) for name, rows in (tabs or ())}
    result = {}
    for tab, data in sorted(scan.items()):
        approved = normalized(tab) in TWO_ROW_LAYOUT_TABS
        columns = raw.get(tab)
        found = [finding for block in data.get("blocks", {}).values()
                 for finding in row_shift_findings(block, columns, approved) + duplicate_container_findings(block, columns)]
        found += negative_receipt_findings(data, columns)
        result[tab] = tab_health(data.get("issues") or {}, found)
        if anchors := block_anchors(data, columns):
            result[tab]["blocks"] = anchors   # ô số dư cuối tháng của từng khối: chỗ để nêu ô khi chuỗi số dư gãy (chain_break)
    return result
