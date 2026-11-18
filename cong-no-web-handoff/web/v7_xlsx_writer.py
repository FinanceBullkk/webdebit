"""Bảng tính .xlsx tối giản, chỉ thư viện chuẩn (XUAT-SO-01, specs/v7-xuat-ca-so.md).

Ghi: mỗi tab là một bảng (hàng tiêu đề cố định, có bộ lọc) hoặc một trang chữ tự do. Ô là `int` (tiền hoặc số đếm), `str`,
`date` (ô ngày dd/mm/yyyy), `Month` (ô ngày mm/yyyy) hoặc `None` (ô trống: không bao giờ thành 0). `Styled` bọc một ô để tô
riêng (tiêu đề, chữ đậm, đạt, lệch). Đọc: chỉ đọc lại file do chính module này ghi, để bản xuất tự kiểm trên đúng byte đã gửi.
"""

from __future__ import annotations

import datetime as dt
import io
import re
import zipfile
from dataclasses import dataclass
from typing import NamedTuple
from xml.etree import ElementTree as ET
from xml.sax.saxutils import escape

MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG = "http://schemas.openxmlformats.org/package/2006/relationships"
SHEET_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"
EPOCH = dt.date(1899, 12, 30)        # hệ ngày 1900 của Excel, đúng cho mọi ngày sau 1/3/1900
MAX_EXACT = 2 ** 53                 # Excel giữ số bằng double: số nguyên lớn hơn thì mất đồng lẻ
MAX_TEXT = 32767                    # giới hạn chữ trong một ô của Excel
FIXED_TIME = (2026, 1, 1, 0, 0, 0)  # giờ của mục zip cố định: cùng dữ liệu ra cùng byte
BAD_XML = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f￾￿]")
# Chỉ số kiểu ô trong styles.xml bên dưới; kiểu cột "auto" chọn theo giá trị.
STYLES = {"text": 0, "head": 1, "money": 2, "count": 3, "date": 4, "month": 5, "bold": 6, "bad": 7, "good": 8, "title": 9}
DATE_STYLES = {STYLES["date"]: "date", STYLES["month"]: "month"}


class Month(dt.date):
    """Ô tháng: ngày đầu tháng, hiện mm/yyyy."""


class Styled(NamedTuple):
    value: object
    style: str


@dataclass
class Sheet:
    name: str
    columns: list[tuple[str, str, int]]   # (tiêu đề, kiểu cột, độ rộng)
    rows: list[list]
    table: bool = True                    # False: trang chữ, không hàng tiêu đề, không bộ lọc


def clean_text(value: str) -> str:
    """Chữ ghi được vào ô: bỏ ký tự XML 1.0 không cho, cắt ở giới hạn của Excel. Bảng dựng ô bằng hàm này nên đọc lại khớp."""
    return BAD_XML.sub("", value)[:MAX_TEXT]


def column_name(number: int) -> str:
    name = ""
    while number > 0:
        number, rest = divmod(number - 1, 26)
        name = chr(65 + rest) + name
    return name


def _style(value: object, kind: str) -> str:
    if kind != "auto":
        return kind
    if isinstance(value, Month):
        return "month"
    if isinstance(value, dt.date):
        return "date"
    return "money" if isinstance(value, int) else "text"


def _cell(ref: str, value: object, kind: str) -> str:
    style = value.style if isinstance(value, Styled) else _style(value, kind)
    value = value.value if isinstance(value, Styled) else value
    if value is None:
        return ""
    s = STYLES[style]
    if isinstance(value, bool) or not isinstance(value, (int, str, dt.date)):
        raise TypeError(f"ô {ref}: kiểu {type(value).__name__} không ghi được")
    if isinstance(value, dt.date):
        if style not in ("date", "month"):
            s = STYLES["month" if isinstance(value, Month) else "date"]
        return f'<c r="{ref}" s="{s}"><v>{(value - EPOCH).days}</v></c>'
    if isinstance(value, int) and abs(value) < MAX_EXACT:
        return f'<c r="{ref}" s="{s}"><v>{value}</v></c>'
    text = escape(str(value))
    return f'<c r="{ref}" t="inlineStr" s="{s}"><is><t xml:space="preserve">{text}</t></is></c>'


def _sheet_xml(sheet: Sheet, selected: bool) -> tuple[str, str | None]:
    """(XML của tab, vùng bộ lọc hoặc None)."""
    width = len(sheet.columns)
    lines = [[Styled(title, "head") for title, _, _ in sheet.columns]] if sheet.table else []
    lines += sheet.rows
    last = column_name(width)
    area = f"A1:{last}{max(len(lines), 1)}"
    body = []
    for number, row in enumerate(lines, start=1):
        cells = "".join(_cell(f"{column_name(index + 1)}{number}", value, sheet.columns[index][1])
                        for index, value in enumerate(row[:width]))
        body.append(f'<row r="{number}">{cells}</row>')
    pane = ('<pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/><selection pane="bottomLeft"/>'
            if sheet.table else "")
    view = '<sheetView workbookViewId="0" tabSelected="1">' if selected else '<sheetView workbookViewId="0">'
    cols = "".join(f'<col min="{i}" max="{i}" width="{w}" customWidth="1"/>' for i, (_, _, w) in enumerate(sheet.columns, 1))
    autofilter = f'<autoFilter ref="{area}"/>' if sheet.table else ""
    xml = (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<worksheet xmlns="{MAIN}" xmlns:r="{REL}">'
           f'<dimension ref="{area}"/><sheetViews>{view}{pane}</sheetView></sheetViews>'
           f'<sheetFormatPr defaultRowHeight="15"/><cols>{cols}</cols>'
           f'<sheetData>{"".join(body)}</sheetData>{autofilter}</worksheet>')
    return xml, area if sheet.table else None


STYLES_XML = (
    f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<styleSheet xmlns="{MAIN}">'
    '<numFmts count="2"><numFmt numFmtId="164" formatCode="dd/mm/yyyy"/><numFmt numFmtId="165" formatCode="mm/yyyy"/></numFmts>'
    '<fonts count="5"><font><sz val="11"/><name val="Calibri"/></font><font><b/><sz val="11"/><name val="Calibri"/></font>'
    '<font><b/><sz val="11"/><color rgb="FFC8322F"/><name val="Calibri"/></font>'
    '<font><b/><sz val="11"/><color rgb="FF0F766E"/><name val="Calibri"/></font><font><b/><sz val="14"/><name val="Calibri"/></font></fonts>'
    '<fills count="3"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill>'
    '<fill><patternFill patternType="solid"><fgColor rgb="FFF3F5F8"/><bgColor indexed="64"/></patternFill></fill></fills>'
    '<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>'
    '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs><cellXfs count="10">'
    '<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>'
    '<xf numFmtId="0" fontId="1" fillId="2" borderId="0" xfId="0" applyFont="1" applyFill="1"/>'
    '<xf numFmtId="3" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/>'
    '<xf numFmtId="1" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/>'
    '<xf numFmtId="164" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/>'
    '<xf numFmtId="165" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/>'
    '<xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0" applyFont="1"/>'
    '<xf numFmtId="0" fontId="2" fillId="0" borderId="0" xfId="0" applyFont="1"/>'
    '<xf numFmtId="0" fontId="3" fillId="0" borderId="0" xfId="0" applyFont="1"/>'
    '<xf numFmtId="0" fontId="4" fillId="0" borderId="0" xfId="0" applyFont="1"/>'
    '</cellXfs><cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles></styleSheet>')


def write_workbook(sheets: list[Sheet]) -> bytes:
    parts, filters = {}, []
    for index, sheet in enumerate(sheets, start=1):
        if not 0 < len(sheet.name) <= 31 or re.search(r"[\[\]:*?/\\']", sheet.name):
            raise ValueError("tên tab không hợp lệ")
        parts[f"xl/worksheets/sheet{index}.xml"], area = _sheet_xml(sheet, index == 1)
        if area:
            fixed = re.sub(r"([A-Z]+)([0-9]+)", r"$\1$\2", area)
            quoted = escape("'" + sheet.name + "'")
            filters.append(f'<definedName name="_xlnm._FilterDatabase" localSheetId="{index - 1}" hidden="1">'
                           f"{quoted}!{fixed}</definedName>")
    tabs = "".join(f'<sheet name="{escape(s.name)}" sheetId="{i}" r:id="rId{i}"/>' for i, s in enumerate(sheets, 1))
    names = "<definedNames>" + "".join(filters) + "</definedNames>" if filters else ""
    parts["xl/workbook.xml"] = (
        f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<workbook xmlns="{MAIN}" xmlns:r="{REL}"><workbookPr/>'
        f'<bookViews><workbookView activeTab="0"/></bookViews><sheets>{tabs}</sheets>{names}</workbook>')
    links = "".join(f'<Relationship Id="rId{i}" Type="{REL}/worksheet" Target="worksheets/sheet{i}.xml"/>'
                    for i in range(1, len(sheets) + 1))
    parts["xl/_rels/workbook.xml.rels"] = (
        f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<Relationships xmlns="{PKG}">{links}'
        f'<Relationship Id="rId{len(sheets) + 1}" Type="{REL}/styles" Target="styles.xml"/></Relationships>')
    parts["xl/styles.xml"] = STYLES_XML
    overrides = "".join(f'<Override PartName="/xl/worksheets/sheet{i}.xml" ContentType="{SHEET_TYPE}"/>'
                        for i in range(1, len(sheets) + 1))
    head = {
        "[Content_Types].xml": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
            f'{overrides}<Override PartName="/xl/styles.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/></Types>'),
        "_rels/.rels": (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<Relationships xmlns="{PKG}">'
                        f'<Relationship Id="rId1" Type="{REL}/officeDocument" Target="xl/workbook.xml"/></Relationships>'),
    }
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as book:
        for name, text in {**head, **parts}.items():
            book.writestr(zipfile.ZipInfo(name, FIXED_TIME), text.encode("utf-8"), zipfile.ZIP_DEFLATED)
    return out.getvalue()


def _value(cell: ET.Element) -> object:
    if cell.get("t") == "inlineStr":
        return "".join(t.text or "" for t in cell.iter(f"{{{MAIN}}}t"))
    raw = cell.findtext(f"{{{MAIN}}}v")
    if raw is None:
        return None
    kind = DATE_STYLES.get(int(cell.get("s", "0")))
    if kind:
        day = EPOCH + dt.timedelta(days=int(raw))
        return Month(day.year, day.month, day.day) if kind == "month" else day
    # Module chỉ ghi số nguyên: số khác là file hỏng, trả nguyên chữ để phép kiểm báo lệch (không đổi sang số thực).
    return int(raw) if re.fullmatch(r"-?[0-9]+", raw) else raw


def read_workbook(data: bytes) -> dict[str, list[list]]:
    """{tên tab: các hàng, kể cả hàng tiêu đề}; ô trống là None, bỏ ô trống cuối hàng."""
    found = {}
    with zipfile.ZipFile(io.BytesIO(data)) as book:
        links = {r.get("Id"): r.get("Target") for r in ET.fromstring(book.read("xl/_rels/workbook.xml.rels"))}
        for tab in ET.fromstring(book.read("xl/workbook.xml")).iter(f"{{{MAIN}}}sheet"):
            rows: list[list] = []
            for row in ET.fromstring(book.read("xl/" + links[tab.get(f"{{{REL}}}id")])).iter(f"{{{MAIN}}}row"):
                cells: dict[int, object] = {}
                for cell in row.iter(f"{{{MAIN}}}c"):
                    letters = re.match(r"[A-Z]+", cell.get("r")).group()
                    cells[sum((ord(ch) - 64) * 26 ** i for i, ch in enumerate(reversed(letters))) - 1] = _value(cell)
                number = int(row.get("r"))
                rows.extend([] for _ in range(number - 1 - len(rows)))
                rows.append([cells.get(i) for i in range(max(cells, default=-1) + 1)])
            found[tab.get("name")] = rows
    return found


def plain_rows(sheet: Sheet) -> list[list]:
    """Các hàng của tab đúng như `read_workbook` sẽ trả: bỏ lớp Styled, bỏ ô trống cuối hàng."""
    lines = [[title for title, _, _ in sheet.columns]] if sheet.table else []
    out = []
    for row in lines + sheet.rows:
        values = [cell.value if isinstance(cell, Styled) else cell for cell in row[:len(sheet.columns)]]
        while values and values[-1] is None:
            values.pop()
        out.append(values)
    return out
