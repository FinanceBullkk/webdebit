"""ZALO-THU-CHI-01 PR-2 (B1–B2): thu chi đọc từ tin chữ của các nhóm Zalo đã chọn, đối chiếu chỉ đọc với sổ. Không lưu gì, không ghi tiền.

B1. Đọc mẫu `thu|chi|ứng <số> <đối tượng>` bằng biểu thức chính quy cố định. Chữ của tin không đi vào model hay lệnh nào: nó chỉ
được khớp mẫu rồi hiện lại cho người xem. Ảnh cùng người gửi trong 2 phút sau tin thì gộp làm ảnh chứng. Số không đọc được là None
(không phải 0), không vào tổng. Đối tượng chỉ gắn khi khớp đúng một sổ, xe hoặc người.
B2. Đối chiếu với phiếu thu (`get_receipt_book`: phiếu web chưa hủy và dòng thu sổ gốc), ứng và dòng chi của Đội xe (`doixe.get_so`),
và các dấu "Khách báo đã chuyển" (`get_marks`, tự chấm sẵn bằng SQL). Khoảng ngày và luật "quá 3 ngày" lấy đúng của `sokhach._mark_json`
(`MATCH_BEFORE`, `MATCH_AFTER`, `MISSING_AFTER`; test đối chiếu với file SQL để hai nơi không chấm khác nhau). Một phiếu hoặc dòng sổ
chỉ ứng với một khoản báo; hai khoản cùng ứng với một dòng thì để người xem chọn (`shared`).
"""

from __future__ import annotations

import re
import threading
import time
from datetime import date, datetime, timedelta
from fractions import Fraction
from typing import Any
from urllib.parse import parse_qs

import v7_api_sheet
import v7_machine
import v7_zalo_chat
from v7_api_validate import bad, valid_date

VN = v7_machine.VN
STATUSES = ("RECORDED", "WAITING", "MISSING", "AMOUNT_DIFF", "SUGGEST", "UNKNOWN_TARGET", "NO_LEDGER", "NO_AMOUNT")
MATCH_BEFORE, MATCH_AFTER, MISSING_AFTER = 3, 7, 3   # như sokhach._mark_json: phiếu từ báo−3 tới báo+7; quá báo+3 mà chưa thấy là "chưa vào sổ"
IMAGE_GAP_MS = 120_000
MAX_SPAN_DAYS = 93
MAX_AMOUNT = 10**12
MAX_CONVERSATIONS = 20
CACHE_SECONDS = 8   # trang hỏi vài giây một lần; phần đọc DB giữ ngắn như vậy để nhiều người xem không nhân số lần đọc
MARK_STATUS = {"received": "RECORDED", "not_seen": "MISSING", "waiting": "WAITING"}
UNITS = {"trieu": 10**6, "tr": 10**6, "k": 10**3, "nghin": 10**3, "ngan": 10**3, "ty": 10**9}
REPORT = re.compile(r"\s*(?P<verb>thu|chi|ung)(?![a-z])[\s:.\-]*(?P<num>\d[\d.,]*)"
                    r"(?:\s*(?P<unit>trieu|tr|k|nghin|ngan|ty|vnd|d)(?![a-z])(?P<tail>\d*))?(?P<rest>.*)", re.S)
OFFICE = re.compile(r"(?<![a-z0-9])(luong|van phong|vpp|mat bang|thue nha|tien nha|internet)(?![a-z0-9])")
PLATE_RUN = re.compile(r"\d(?:[\d.\-]*\d)?")
_CACHE: dict[tuple, tuple[float, dict]] = {}
_LOCK = threading.Lock()


# ---- B1: đọc mẫu ----
def amount_vnd(num: str, unit: str | None, tail: str) -> int | None:
    """`2tr5`, `2,5tr`, `800k`, `1.200.000`, `1200000` đổi ra VND nguyên; không đoán: số trần dưới 1.000, số lẻ đồng hay dạng lạ là None."""
    num = num.rstrip(".,")
    if unit in (None, "vnd", "d"):
        if tail or not (re.fullmatch(r"\d{1,3}([.,]\d{3})+", num) or num.isdigit()):
            return None
        value = int(re.sub(r"\D", "", num))
        return value if 1000 <= value <= MAX_AMOUNT else None
    if unit == "k" and re.fullmatch(r"\d{1,3}([.,]\d{3})+", num) and not tail:   # "1.200k" là 1.200 nghìn
        num = re.sub(r"\D", "", num)
    found = re.fullmatch(r"(\d+)(?:[.,](\d+))?", num)
    if not found or (tail and found.group(2)):
        return None
    digits = found.group(2) or tail
    total = (Fraction(int(found.group(1))) + (Fraction(int(digits), 10 ** len(digits)) if digits else 0)) * UNITS[unit]
    return int(total) if total.denominator == 1 and 0 < total <= MAX_AMOUNT else None


def read_report(text: str) -> dict | None:
    """Tin chữ bắt đầu bằng thu/chi/ứng rồi tới một số (không phân biệt hoa thường và dấu) là một khoản báo; `amount_vnd` None khi số lạ."""
    match = REPORT.match(v7_zalo_chat.fold(text))
    if match is None:
        return None
    return {"direction": {"thu": "thu", "chi": "chi", "ung": "ung"}[match["verb"]],
            "amount_vnd": amount_vnd(match["num"], match["unit"], match["tail"] or ""), "rest": match["rest"]}


def _has(text: str, needle: str) -> bool:
    words = [re.escape(word) for word in needle.split()]
    return bool(words) and re.search(r"(?<![a-z0-9])" + r"\s+".join(words) + r"(?![a-z0-9])", text) is not None


def _longest(hits: list[tuple]) -> list[tuple]:
    """Tên ngắn nằm trong tên dài ("AN" trong "AN LONG", "Bình" trong "Bình An") mà cả hai cùng khớp thì giữ tên dài."""
    return [hit for hit in hits if not any(hit[2] != other[2] and hit[2] in other[2] for other in hits)]


def _unique(found: dict[Any, str]) -> dict | None:
    return {"id": next(iter(found)), "label": next(iter(found.values()))} if len(found) == 1 else None


class Directory:
    """Sổ khách, xe và người của Đội xe, tên đã bỏ dấu để khớp. Chỉ gắn đối tượng khi khớp đúng một."""

    def __init__(self, customers: list[dict], xe: list[dict], nguoi: list[dict]):
        self.books = [(row["id"], row["name"], [v7_zalo_chat.fold(name) for name in
                       (row.get("name"), row.get("display_name"), *(row.get("aliases") or [])) if isinstance(name, str) and len(name.strip()) >= 2])
                      for row in customers if isinstance(row.get("id"), int) and isinstance(row.get("name"), str)]
        self.xe = {row["id"]: row for row in xe if isinstance(row.get("id"), int) and isinstance(row.get("bien_so"), str)}
        self.people = [(row["id"], row["ten"], v7_zalo_chat.fold(row["ten"])) for row in nguoi
                       if isinstance(row.get("id"), int) and isinstance(row.get("ten"), str) and row.get("dang_dung", True) and len(row["ten"].strip()) >= 2]

    def book(self, rest: str) -> tuple[dict | None, int]:
        hits = [(book_id, name, cand) for book_id, name, cands in self.books for cand in cands if _has(rest, cand)]
        hits = _longest(hits)
        return _unique({book_id: name for book_id, name, _ in hits}), len({hit[0] for hit in hits})

    def vehicle(self, rest: str) -> tuple[dict | None, None]:
        tokens = {digits for run in PLATE_RUN.findall(rest) if 4 <= len(digits := re.sub(r"\D", "", run)) <= 5}
        return _unique({xid: row["bien_so"] for xid, row in self.xe.items()
                        if any(re.sub(r"\D", "", row["bien_so"]).endswith(token) for token in tokens)}), None

    def person(self, rest: str) -> tuple[dict | None, None]:
        hits = _longest([(pid, name, cand) for pid, name, cand in self.people if _has(rest, cand)])
        return _unique({pid: name for pid, name, _ in hits}), None

    def target(self, direction: str, rest: str) -> dict:
        """`kind`: so (thu) | xe | tai_xe (chi, ứng) | None; `ambiguous` khi khớp nhiều hơn một."""
        order = [("so", self.book)] if direction == "thu" else [("xe", self.vehicle), ("tai_xe", self.person)]
        ambiguous = False
        for kind, finder in order:
            found, count = finder(rest)
            if found:
                return {"kind": kind, **found}
            ambiguous = ambiguous or bool(count and count > 1)
        return {"kind": None, "id": None, "label": None, "ambiguous": ambiguous}


def collect(store, directory_of, start_ms: int, end_ms: int) -> list[dict]:
    """Khoản báo trong [start_ms, end_ms) của mọi hội thoại trong gói, kèm ảnh chứng. `directory_of()` chỉ được gọi khi có ít nhất một khoản."""
    names = {row["conversation_id"]: row["display_name"] for row in store.conversations()}
    items: list[dict] = []
    last: dict | None = None
    current = None
    directory = None
    for cid, row in store.messages_between(start_ms, end_ms + IMAGE_GAP_MS):
        if cid != current:
            current, last = cid, None
        stamp = row["timestamp_ms"] or 0
        report = read_report(row["body_text"]) if row["body_kind"] == "text" and row["body_text"] and not row["deleted"] else None
        if report and stamp < end_ms:
            directory = directory or directory_of()
            last = {"message_id": row["message_id"], "conversation_id": cid, "conversation_name": names.get(cid), "sent_at": stamp,
                    "sender_name": row["sender_name"], "sender": row["sender_id"], "direction": report["direction"],
                    "amount_vnd": report["amount_vnd"], "text": row["body_text"][:300], "media": [],
                    "target": directory.target(report["direction"], report["rest"]), "rest": report["rest"]}
            items.append(last)
        elif row["media"] and last and row["sender_id"] == last["sender"] and 0 <= stamp - last["sent_at"] <= IMAGE_GAP_MS:
            last["media"] += row["media"]
    return items


# ---- B2: đối chiếu ----
def month_of(day: date) -> date:
    return day.replace(day=1)


def months(first: date, last: date) -> list[date]:
    out, current = [], month_of(first)
    while current <= last:
        out.append(current)
        current = (current + timedelta(days=32)).replace(day=1)
    return out


class Sources:
    """Mỗi lần dựng đọc từng hàm DB một lần (theo tháng, theo người hoặc xe); chỉ đọc, qua các hàm đọc đã có của Bảng thu và Đội xe."""

    def __init__(self, runner, actor: str, today: date):
        self.runner, self.actor, self.today = runner, actor, today
        self.books: dict[date, list[dict]] = {}
        self.fleet: dict[tuple, dict] = {}

    def receipts(self, day: date) -> list[dict]:
        out = []
        for month in months(day - timedelta(MATCH_BEFORE), min(day + timedelta(MATCH_AFTER), self.today)):
            if month not in self.books:
                body = self.runner.run("get_receipt_book", {"month": month.isoformat()}, self.actor)
                self.books[month] = [{"key": ("receipt", row.get("source"), row.get("id")), "date": date.fromisoformat(row["date"]), "customer": row["customer_id"],
                                      "amount": int(row["amount_vnd"]), "ref": {"kind": "receipt", "source": row.get("source"), "id": row.get("id"), "pid": row.get("pid"),
                                                                                "customer_id": row["customer_id"], "name": row.get("name"), "date": row["date"]}}
                                     for group in body.get("days") or [] for row in group.get("rows") or [] if row.get("date")]
            out += self.books[month]
        return out

    def fleet_rows(self, kind: str, entity: int, direction: str, day: date) -> list[dict]:
        out = []
        for month in months(day - timedelta(MATCH_BEFORE), min(day + timedelta(MATCH_AFTER), self.today)):
            key = (kind, entity, month)
            if key not in self.fleet:
                self.fleet[key] = self.runner.run("doixe_get_so", {"loai": "xe" if kind == "xe" else "nguoi", "id": entity, "thang": month.isoformat()}, self.actor)
            data = self.fleet[key]
            if direction == "ung":
                out += [{"key": ("ung", row["id"]), "date": date.fromisoformat(row["ngay"]), "amount": int(row["so_tien_vnd"]),
                         "ref": {"kind": "ung", "id": row["id"], "date": row["ngay"]}} for row in data.get("ung") or [] if not row.get("huy")]
                continue
            for trip in data.get("chang") or []:
                if trip.get("da_bo") or (kind == "tai_xe" and trip.get("nguoi_tra_id") != entity):
                    continue
                out += [{"key": ("phi", line["id"], code), "date": date.fromisoformat(trip["ngay"]), "amount": int(money),
                         "ref": {"kind": "dong_phi", "id": line["id"], "loai_phi": code, "chang_id": trip.get("id"), "date": trip["ngay"]}}
                        for line in trip.get("dong") or [] for code, money in (line.get("phi") or {}).items()]
        return out


def _near(rows: list[dict], day: date) -> list[dict]:
    return [row for row in rows if day - timedelta(MATCH_BEFORE) <= row["date"] <= day + timedelta(MATCH_AFTER)]


def _settle(item: dict, status: str, row: dict | None = None, shared: bool = False) -> None:
    item.update(status=status, shared=shared, ledger_ref=row["ref"] if row else None, ledger_vnd=row["amount"] if row else None)


def pair_exact(items: list[dict], rows_of, claimed: set) -> None:
    """Khoản báo đúng số với dòng sổ trong khoảng ngày thì ứng đúng một dòng. Hai khoản tranh cùng dòng (nhiều khoản hơn dòng) thì cả hai
    để người xem chọn (`shared`), không tự chọn."""
    cands = {id(item): [row for row in rows_of(item) if row["amount"] == item["amount_vnd"] and row["key"] not in claimed] for item in items}
    parent: dict = {}

    def find(node):
        while parent.setdefault(node, node) != node:
            parent[node] = parent[parent[node]]
            node = parent[node]
        return node

    for item in items:
        for row in cands[id(item)]:
            parent[find(("i", id(item)))] = find(("r", row["key"]))
    groups: dict = {}
    for item in items:
        if cands[id(item)]:
            groups.setdefault(find(("i", id(item))), []).append(item)
    for members in groups.values():
        keys = {row["key"] for item in members for row in cands[id(item)]}
        free = {row["key"]: row for item in members for row in cands[id(item)]}
        for item in sorted(members, key=lambda one: one["sent_at"]):
            pick = next((row for row in sorted(cands[id(item)], key=lambda one: (one["date"], str(one["key"]))) if row["key"] in free), None)
            if len(members) > len(keys) or pick is None:
                _settle(item, "AMOUNT_DIFF", cands[id(item)][0], shared=True)
                continue
            del free[pick["key"]]
            claimed.add(pick["key"])
            _settle(item, "RECORDED", pick)


def pair_single(items: list[dict], rows_of, claimed: set, status: str) -> None:
    """Chưa có dòng đúng số: đúng một dòng khác trong khoảng ngày (cùng đối tượng) là `AMOUNT_DIFF` (đã biết đối tượng) hoặc `SUGGEST`
    (thu chưa rõ sổ, dòng đúng số của sổ bất kỳ). Một dòng là ứng viên duy nhất của hai khoản thì cả hai `shared`."""
    lone = {id(item): [row for row in rows_of(item) if row["key"] not in claimed] for item in items}
    lone = {key: rows for key, rows in lone.items() if len(rows) == 1}
    use: dict = {}
    for rows in lone.values():
        use[rows[0]["key"]] = use.get(rows[0]["key"], 0) + 1
    for item in items:
        rows = lone.get(id(item))
        if rows:
            _settle(item, status, rows[0], shared=use[rows[0]["key"]] > 1)


def reconcile(items: list[dict], directory: Directory, sources: Sources, today: date) -> None:
    """Gán `status`, `ledger_ref`, `ledger_vnd`, `shared` cho từng khoản báo theo bảng trạng thái của spec (Luồng 2)."""
    for item in items:
        item["day"] = datetime.fromtimestamp(item["sent_at"] / 1000, VN).date()
        item["status"], item["shared"], item["ledger_ref"], item["ledger_vnd"] = None, False, None, None
    claimed: set = set()
    for item in items:
        kind, entity, direction = item["target"]["kind"], item["target"]["id"], item["direction"]
        if item["amount_vnd"] is None:
            item["status"] = "NO_AMOUNT"
        elif direction == "thu" and kind == "so":
            item["rows"] = lambda one=item: [row for row in _near(sources.receipts(one["day"]), one["day"]) if row["customer"] == one["target"]["id"]]
        elif direction == "ung" and kind == "xe" and directory.xe[entity].get("tai_xe_id"):
            item["rows"] = lambda one=item: _near(sources.fleet_rows("tai_xe", directory.xe[one["target"]["id"]]["tai_xe_id"], "ung", one["day"]), one["day"])
        elif (direction == "ung" and kind == "tai_xe") or (direction == "chi" and kind in ("xe", "tai_xe")):
            item["rows"] = lambda one=item: _near(sources.fleet_rows(one["target"]["kind"], one["target"]["id"], one["direction"], one["day"]), one["day"])
        elif direction == "chi" and OFFICE.search(item["rest"]):
            item["status"] = "NO_LEDGER"
    known = [item for item in items if "rows" in item]
    pair_exact(known, lambda one: one["rows"](), claimed)
    pair_single([item for item in known if item["status"] is None], lambda one: one["rows"](), claimed, "AMOUNT_DIFF")
    unknown_thu = [item for item in items if item["status"] is None and item["direction"] == "thu" and "rows" not in item]
    anywhere = lambda one: [row for row in _near(sources.receipts(one["day"]), one["day"]) if row["amount"] == one["amount_vnd"]]   # noqa: E731
    pair_single(unknown_thu, anywhere, claimed, "SUGGEST")
    for item in items:
        if item["status"] is None:
            item["status"] = ("UNKNOWN_TARGET" if "rows" not in item else "MISSING" if today > item["day"] + timedelta(MISSING_AFTER) else "WAITING")


# ---- dựng kết quả ----
def parse_query(query: str, today: date) -> tuple[date, date, set[str]]:
    values = parse_qs(query, keep_blank_values=True)
    if not set(values) <= {"from", "to", "status"} or any(len(items) != 1 for items in values.values()):
        bad()
    first, last = values.get("from", [""])[0], values.get("to", [""])[0]
    if (first and not valid_date(first)) or (last and not valid_date(last)):
        bad()
    end = date.fromisoformat(last) if last else today
    start = date.fromisoformat(first) if first else end - timedelta(6)
    if start > end or (end - start).days >= MAX_SPAN_DAYS:
        bad("INVALID_RANGE", "Khoảng ngày không hợp lệ: từ ngày không sau đến ngày và tối đa 93 ngày.")
    wanted = {code for code in values.get("status", [""])[0].split(",") if code}
    if not wanted <= set(STATUSES):
        bad()
    return start, end, wanted


def _marks(store, runner, actor: str, start: date, end: date, directory: Directory, taken: set) -> list[dict]:
    """Dấu "Khách báo đã chuyển" của các nhóm trong gói: hiện như khoản thu, trạng thái do SQL chấm (cùng luật), không chép sang đâu."""
    names = {book_id: name for book_id, name, _ in directory.books}
    items = []
    for conversation in store.conversations()[:MAX_CONVERSATIONS]:
        for mark in runner.run("get_marks", {"conversation_id": conversation["conversation_id"]}, actor).get("marks") or []:
            if mark.get("kind") != "paid_claim" or mark.get("status") not in MARK_STATUS or mark.get("message_id") in taken:
                continue
            day = date.fromisoformat(mark["on_date"])
            if start <= day <= end:
                items.append({"message_id": mark.get("message_id"), "conversation_id": mark["conversation_id"], "conversation_name": conversation["display_name"],
                              "sent_at": int(datetime.fromisoformat(mark["message_at"]).timestamp() * 1000) if mark.get("message_at") else None,
                              "sender_name": mark.get("message_sender"), "direction": "thu", "amount_vnd": int(mark["amount_vnd"]),
                              "text": (mark.get("message_excerpt") or mark.get("note") or "")[:300], "media": [], "day": day, "source": "mark",
                              "target": {"kind": "so", "id": mark["customer_id"], "label": names.get(mark["customer_id"])},
                              "status": MARK_STATUS[mark["status"]], "shared": False, "ledger_vnd": None,
                              "ledger_ref": {"kind": "receipt", "pid": mark["receipt_pid"]} if mark.get("receipt_pid") else None})
    return items


def _public(item: dict) -> dict:
    out = {key: item.get(key) for key in ("message_id", "conversation_id", "conversation_name", "sent_at", "sender_name", "direction", "amount_vnd", "text",
                                          "media", "status", "shared", "ledger_ref", "ledger_vnd")}
    out["day"] = item["day"].isoformat()
    out["source"] = item.get("source", "chat")
    out["target"] = {key: item["target"].get(key) for key in ("kind", "id", "label")}
    out["ambiguous"] = bool(item["target"].get("ambiguous"))
    return out


def totals(items: list[dict]) -> dict:
    out = {"thu_vnd": 0, "chi_vnd": 0, "ung_vnd": 0, "thu_count": 0, "chi_count": 0, "ung_count": 0, "no_amount": 0,
           "missing": sum(item["status"] == "MISSING" for item in items), "amount_diff": sum(item["status"] == "AMOUNT_DIFF" for item in items)}
    for item in items:
        if item["amount_vnd"] is None:
            out["no_amount"] += 1
        else:
            out[item["direction"] + "_vnd"] += item["amount_vnd"]
            out[item["direction"] + "_count"] += 1
    return out


def zalo_view(now: float) -> dict:
    """Tuổi dữ liệu Zalo theo `status.json` của máy Zalo (ZALO-AGENT-01 Phần 6) thay cho `zalo_age_seconds` của spec cũ: có đủ tín hiệu
    "máy im", "Zalo chưa mở" và số phút, không phải đoán từ giờ tin cuối."""
    view = v7_machine.zalo(now)
    return {key: view.get(key) for key in ("state", "at", "silent_minutes", "identity", "quiet_minutes")}


def build(start: date, end: date, runner, actor: str, now: float | None = None) -> dict:
    now = time.time() if now is None else now
    today = datetime.fromtimestamp(now, VN).date()
    zalo = zalo_view(now)
    try:
        store = v7_zalo_chat.get_store()
    except v7_zalo_chat.ChatError:
        return {"unavailable": True, "zalo": zalo}
    key = (start, end, store.token())
    with _LOCK:
        cached = _CACHE.get(key)
    if cached is None or now - cached[0] > CACHE_SECONDS:
        cached = (now, _core(store, start, end, runner, actor, today))
        with _LOCK:
            if len(_CACHE) > 16:
                _CACHE.clear()
            _CACHE[key] = cached
    core = cached[1]
    last_ms = max((row["last_message_at"] or 0 for row in store.conversations()), default=0) or None
    return {"unavailable": False, "from": start.isoformat(), "to": end.isoformat(), "today": today.isoformat(), "zalo": zalo,
            "bundle_at": store.report.get("built_at") if isinstance(store.report.get("built_at"), str) else None, "last_message_at": last_ms, **core}


def _core(store, start: date, end: date, runner, actor: str, today: date) -> dict:
    start_ms = int(datetime.combine(start, datetime.min.time(), VN).timestamp() * 1000)
    end_ms = int(datetime.combine(end + timedelta(1), datetime.min.time(), VN).timestamp() * 1000)
    holder: dict = {}

    def directory_of() -> Directory:
        if "directory" not in holder:
            customers = v7_api_sheet.with_display_names(runner.run("list_customers", {}, actor)).get("customers", [])
            fleet = runner.run("doixe_get_tong", {"thang": None}, actor).get("danh_muc") or {}
            holder["directory"] = Directory(customers, fleet.get("xe") or [], fleet.get("nguoi") or [])
        return holder["directory"]

    items = collect(store, directory_of, start_ms, end_ms)
    directory = directory_of() if store.conversations() else None
    if items:
        reconcile(items, directory, Sources(runner, actor, today), today)
    items += _marks(store, runner, actor, start, end, directory, {item["message_id"] for item in items}) if directory else []
    items.sort(key=lambda item: (item["day"], item["sent_at"] or 0), reverse=True)
    return {"items": [_public(item) for item in items], "totals": totals(items),
            "counts": {code: sum(item["status"] == code for item in items) for code in STATUSES}}


def handle_get(query: str, runner, actor: str, now: float | None = None) -> dict:
    """GET /api/v7/cash-chat?from=YYYY-MM-DD&to=YYYY-MM-DD&status=CODE[,CODE]: mặc định 7 ngày tới hôm nay (giờ VN), mọi trạng thái.
    Tổng và `counts` tính trên cả khoảng, không theo `status`; `status` chỉ lọc `items`."""
    now = time.time() if now is None else now
    start, end, wanted = parse_query(query, datetime.fromtimestamp(now, VN).date())
    body = build(start, end, runner, actor, now)
    if wanted and not body.get("unavailable"):
        body = {**body, "items": [item for item in body["items"] if item["status"] in wanted]}
    return body
