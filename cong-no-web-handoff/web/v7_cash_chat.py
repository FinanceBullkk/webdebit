"""ZALO-THU-CHI-01 PR-2 (B1–B2): thu chi đọc từ tin chữ của các nhóm Zalo đã chọn, đối chiếu chỉ đọc với sổ. Không lưu gì, không ghi tiền.

B1. Đọc mẫu `thu|chi|ứng <số> <đối tượng>` bằng biểu thức chính quy cố định. Chữ của tin không đi vào model hay lệnh nào: nó chỉ
được khớp mẫu rồi hiện lại cho người xem. Ảnh cùng người gửi trong 2 phút sau tin thì gộp làm ảnh chứng. Số không đọc được là None
(không phải 0), không vào tổng. Đối tượng chỉ gắn khi khớp đúng một sổ, xe hoặc người.
B2. Đối chiếu với phiếu thu (`get_receipt_book`: phiếu web chưa hủy và dòng thu sổ gốc), ứng và dòng chi của Đội xe (`doixe.get_so`),
và các dấu "Khách báo đã chuyển" (`get_marks`, tự chấm sẵn bằng SQL). Khoảng ngày và luật "quá 3 ngày" lấy đúng của `sokhach._mark_json`
(`MATCH_BEFORE`, `MATCH_AFTER`, `MISSING_AFTER`; test đối chiếu với file SQL để hai nơi không chấm khác nhau). Một phiếu hoặc dòng sổ
chỉ ứng với một khoản báo; hai khoản cùng ứng với một dòng thì để người xem chọn (`shared`).
B4 trên hao (PR-4b): số đọc từ ảnh chuyển khoản lấy ở `money-reads.json` mà máy Zalo đẩy lên (ZALO-AGENT-01 Phần 3). Ảnh không kèm mẫu
thành khoản thu "từ ảnh"; ảnh chứng của khoản gõ theo mẫu thì đem so số. Luật không đếm hai lần ở spec Thu chi, mục "B4 trên `hao`".
"""

from __future__ import annotations

import json
import os
import re
import sys
import threading
import time
from concurrent.futures import Future
from concurrent.futures import TimeoutError as FlightTimeout
from datetime import date, datetime, timedelta
from fractions import Fraction
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs

import v7_api_sheet
import v7_machine
import v7_zalo_chat
from v7_api_tables import ERRORS
from v7_api_validate import ApiError, bad, positive_int, valid_date, vnd

VN = v7_machine.VN
STATUSES = ("RECORDED", "WAITING", "MISSING", "AMOUNT_DIFF", "SUGGEST", "UNKNOWN_TARGET", "NO_LEDGER", "NO_AMOUNT", "NOT_CASH")
REVIEW_FIELDS = frozenset({"message_id", "action", "value", "reason", "request_id"})
REVIEW_ACTIONS = ("confirm", "target", "amount", "not_cash")
TARGET_KINDS = ("so", "xe", "tai_xe")
MATCH_BEFORE, MATCH_AFTER, MISSING_AFTER = 3, 7, 3   # như sokhach._mark_json: phiếu từ báo−3 tới báo+7; quá báo+3 mà chưa thấy là "chưa vào sổ"
IMAGE_GAP_MS = 120_000
MAX_SPAN_DAYS = 93
MAX_AMOUNT = 10**12
MAX_CONVERSATIONS = 20
CACHE_SECONDS = 8   # trang hỏi vài giây một lần; phần đọc DB giữ ngắn như vậy để nhiều người xem không nhân số lần đọc
MARK_STATUS = {"received": "RECORDED", "not_seen": "MISSING", "waiting": "WAITING"}
UNITS = {"trieu": 10**6, "tr": 10**6, "k": 10**3, "nghin": 10**3, "ngan": 10**3, "ty": 10**9}
REPORT = re.compile(r"\s*(?P<verb>thu|chi|ung)(?![a-z])(?P<sep>[\s:.\-−–—]*)(?P<yen>[¥￥]\s*)?(?P<num>\d[\d.,]*)"
                    r"(?:\s*(?P<unit>trieu|tr|k|nghin|ngan|ty|vnd|d|nhan dan te|ndt|rmb|cny|te|元|块)(?![a-z])(?P<tail>\d*))?(?P<rest>.*)", re.S)
# Đơn vị tệ (WECHAT-01, đã chữ đã bỏ dấu): khoản tính bằng tệ có tổng riêng, không đổi ra VND, không đối chiếu với sổ VND.
CNY_UNITS = frozenset({"nhan dan te", "ndt", "rmb", "cny", "te", "元", "块"})
OFFICE = re.compile(r"(?<![a-z0-9])(luong|van phong|vpp|mat bang|thue nha|tien nha|internet)(?![a-z0-9])")
# Biển số chỉ nhận khi có chữ cái của dãy biển (51C-123.45) hoặc đứng ngay sau "xe", "bks", "bs", "biển số": "15.11", "2026" không phải biển.
PLATE = re.compile(r"(?<![a-z0-9])(?:\d{2}(?!tr|ty)[a-z]{1,2}[\s.\-]*|(?:xe|bks|bs|bien so)[\s:.\-]*(?:so\s*)?)(\d[\d.\-]*\d)(?![a-z])")
# Số bị tách: sau đơn vị rồi cách rồi 1–3 chữ số đứng một mình ("1 triệu 2", "2 tr 5", "1 triệu 2 cho Hùng"): không đoán là số lẻ hay chữ khác.
# Không phải số tách khi chữ số dính chữ cái (biển 51C-...), là ngày/tháng ("20/11") hoặc đứng trước danh từ đếm được ("5tr 30 cont", "800k 2 xe").
COUNTED = r"cont|container|xe|bao|thung|kien|chuyen|lan|cai|chiec|con|cuon|bo|kg|tan|ngay|thang|bill|pallet"
SPLIT_AMOUNT = re.compile(r"\s+\d{1,3}(?!\d)(?![a-z])(?![/\-]\d)(?!\s+(?:" + COUNTED + r")(?![a-z]))")
FLIGHT_WAIT = 60.0   # người chờ lượt dựng của người khác tối đa chừng này giây rồi tự dựng, không treo luồng
# Lỗi do dữ liệu lạ (cột thiếu, kiểu sai, ngày tràn): trang trả "chưa đọc được", không bao giờ 500.
DATA_ERRORS = (KeyError, ValueError, TypeError, AttributeError, IndexError, ArithmeticError, OSError)
MIN_NAME = 3   # tên (đã bỏ dấu) ngắn hơn thế không tự khớp: dễ trùng với từ thường
READS_DIR = "/srv/v7/zalo-reads"   # máy Zalo đẩy kết quả đọc ảnh tới đây (`--reads-target`); đổi bằng WEBDEBIT_ZALO_READS_DIR
READS_FILE = "money-reads.json"
READS_MAX_BYTES = 8 * 1024 * 1024
SHA256 = re.compile(r"[0-9a-f]{64}")   # khóa ảnh, trùng `media[].id` của gói chat
READ_BY = re.compile(r"[a-z0-9-]{1,20}")   # kết luận của máy đọc ảnh; "human" là cần người xem, không có số
ENGINE = re.compile(r"[A-Za-z0-9_.+-]{1,40}")   # tên và phiên bản engine đọc ảnh: mã cố định, không chữ tự do
# Giờ giao dịch: ISO như spec; nhận thêm cách ghi của đường đọc ngoài (cách thay T, "Z", "+0700") rồi chuẩn hóa về `±HH:MM`.
TXN_TIME = re.compile(r"(\d{4}-\d{2}-\d{2})(?:[T ](\d{2}:\d{2}(?::\d{2})?)(Z|[+-]\d{2}:?\d{2})?)?")
SAME_PAYMENT_MS = 24 * 3600 * 1000   # khoản thu gõ theo mẫu cùng hội thoại, cùng số trong chừng này: ảnh là ảnh của lần trả đó
MARK_IMAGE_DAYS = 1   # dấu "Khách báo đã chuyển" cùng hội thoại, cùng số, ngày báo cách ngày giao dịch của ảnh không quá chừng này
_FLIGHTS: dict[tuple, Future] = {}
_CACHE: dict[tuple, tuple[float, dict]] = {}
_LOCK = threading.Lock()
_READS: dict = {"stamp": None, "value": {}, "ok": True}
_READS_LOCK = threading.Lock()


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
    cny = bool(match["yen"]) or match["unit"] in CNY_UNITS
    num = match["num"].rstrip(".,")
    if cny:   # số nguyên tệ ("500 tệ", "1.200元", "¥300"); số lẻ hay dạng lạ thì để trống, không đoán
        whole = num.isdigit() or re.fullmatch(r"\d{1,3}([.,]\d{3})+", num)
        amount = int(re.sub(r"\D", "", num)) if whole and not match["tail"] else None
        amount = amount if amount is not None and 0 < amount <= MAX_AMOUNT else None
    else:
        amount = amount_vnd(match["num"], match["unit"], match["tail"] or "")
    # "chi -500k" (dấu trừ dính vào số) và "chi 1 triệu 2" (số rời sau đơn vị) không đoán: số để trống.
    if match["sep"].endswith(("-", "−", "–", "—")) or SPLIT_AMOUNT.match(match["rest"]):
        amount = None
    return {"direction": {"thu": "thu", "chi": "chi", "ung": "ung"}[match["verb"]], "amount_vnd": None if cny else amount,
            "amount_cny": amount if cny else None, "currency": "CNY" if cny else "VND", "rest": match["rest"]}


def _has(text: str, needle: str) -> bool:
    words = [re.escape(word) for word in needle.split()]
    return bool(words) and re.search(r"(?<![a-z0-9])" + r"\s+".join(words) + r"(?![a-z0-9])", text) is not None


def _longest(hits: list[tuple]) -> list[tuple]:
    """Tên ngắn nằm trong tên dài ("AN" trong "AN LONG", "Bình" trong "Bình An") mà cả hai cùng khớp thì giữ tên dài."""
    return [hit for hit in hits if not any(hit[2] != other[2] and hit[2] in other[2] for other in hits)]


def _unique(found: dict[Any, str]) -> dict | None:
    return {"id": next(iter(found)), "label": next(iter(found.values()))} if len(found) == 1 else None


def _texts(value: Any) -> list:
    """Danh sách tên khác từ JSON: chỉ nhận mảng (chuỗi, số hay null thì bỏ, không tách thành từng ký tự)."""
    return value if isinstance(value, list) else []


class Directory:
    """Sổ khách, xe và người của Đội xe, tên đã bỏ dấu để khớp. Chỉ gắn đối tượng khi khớp đúng một."""

    def __init__(self, customers: list[dict], xe: list[dict], nguoi: list[dict]):
        self.books = [(row["id"], row["name"], [fold for name in (row.get("name"), row.get("display_name"), *_texts(row.get("aliases")))
                                                 if isinstance(name, str) and len(fold := v7_zalo_chat.fold(name).strip()) >= MIN_NAME])
                      for row in customers if isinstance(row.get("id"), int) and isinstance(row.get("name"), str)]
        self.xe = {row["id"]: row for row in xe if isinstance(row.get("id"), int) and isinstance(row.get("bien_so"), str)}
        self.people = [(row["id"], row["ten"], v7_zalo_chat.fold(row["ten"]).strip()) for row in nguoi
                       if isinstance(row.get("id"), int) and isinstance(row.get("ten"), str) and row.get("dang_dung", True)
                       and len(v7_zalo_chat.fold(row["ten"]).strip()) >= MIN_NAME]
        # Tên hiện cho đối tượng người dùng gắn tay (PR-3): đủ mọi sổ, xe, người, kể cả người đã nghỉ hay tên ngắn không tự khớp.
        self.labels = {**{("so", row["id"]): row["name"] for row in customers if isinstance(row.get("id"), int) and isinstance(row.get("name"), str)},
                       **{("xe", xid): row["bien_so"] for xid, row in self.xe.items()},
                       **{("tai_xe", row["id"]): row["ten"] for row in nguoi if isinstance(row.get("id"), int) and isinstance(row.get("ten"), str)}}
        # Xe và người còn dùng: ô "Gắn sổ/xe" chỉ cho chọn những đối tượng này (sổ khách thì mọi sổ).
        self.active = {("xe", xid) for xid, row in self.xe.items() if row.get("dang_dung", True) is not False} | {
            ("tai_xe", row["id"]) for row in nguoi
            if isinstance(row.get("id"), int) and isinstance(row.get("ten"), str) and row.get("dang_dung", True) is not False}

    def label(self, kind: str, entity: int) -> str | None:
        return self.labels.get((kind, entity))

    def book(self, rest: str) -> tuple[dict | None, int]:
        hits = [(book_id, name, cand) for book_id, name, cands in self.books for cand in cands if _has(rest, cand)]
        hits = _longest(hits)
        return _unique({book_id: name for book_id, name, _ in hits}), len({hit[0] for hit in hits})

    def vehicle(self, rest: str) -> tuple[dict | None, None]:
        tokens = {digits for run in PLATE.findall(rest) if 4 <= len(digits := re.sub(r"\D", "", run)) <= 5}
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


def collect(store, directory_of, start_ms: int, end_ms: int, conversations: list[dict], reads: dict | None = None) -> tuple[list[dict], list[dict]]:
    """Khoản báo trong [start_ms, end_ms) của các hội thoại đã chọn, kèm ảnh chứng. `directory_of()` chỉ được gọi khi có ít nhất một khoản.

    Trả thêm các ảnh có kết quả đọc (`reads`) không làm ảnh chứng: mỗi ảnh một khoản thu "từ ảnh", chưa có đối tượng. Ảnh chứng thắng bất
    kể thứ tự đọc: ảnh đã làm ảnh chứng ở bất kỳ hội thoại nào thì không thành khoản riêng; cùng ảnh gửi nhiều lần chỉ giữ lần sớm nhất.
    Mỗi lần gửi lại bị bỏ được đếm vào `resent` của khoản giữ ảnh đó (Luồng 4: chỉ tính một khoản, kèm cảnh báo trùng).
    Ảnh do tài khoản Zalo của mình gửi không thành khoản (thường là mình trả hoặc chuyển tiếp)."""
    reads = reads or {}
    names = {row["conversation_id"]: row["display_name"] for row in conversations}
    items: list[dict] = []
    candidates: list[dict] = []
    proof: dict[str, dict] = {}   # mã ảnh → khoản gõ giữ ảnh đó làm ảnh chứng (khoản sớm nhất)
    last: dict | None = None
    current = None
    directory = None
    for cid, row in store.messages_between(start_ms, end_ms + IMAGE_GAP_MS):
        if cid not in names:
            continue
        if cid != current:
            current, last = cid, None
        stamp = row["timestamp_ms"] or 0
        report = read_report(row["body_text"]) if row["body_kind"] == "text" and row["body_text"] and not row["deleted"] else None
        if report and stamp < end_ms:
            directory = directory or directory_of()
            last = {"message_id": row["message_id"], "conversation_id": cid, "conversation_name": names.get(cid), "sent_at": stamp,
                    "sender_name": row["sender_name"], "sender": row["sender_id"], "direction": report["direction"],
                    "amount_vnd": report["amount_vnd"], "currency": report["currency"], "amount_cny": report["amount_cny"],
                    "text": row["body_text"][:300], "media": [],
                    "target": directory.target(report["direction"], report["rest"]), "rest": report["rest"]}
            items.append(last)
        elif row["media"] and last and row["sender_id"] == last["sender"] and 0 <= stamp - last["sent_at"] <= IMAGE_GAP_MS:
            have = {media["id"] for media in last["media"]}
            last["media"] += [media for media in row["media"] if media["id"] not in have]
            for media in row["media"]:
                proof.setdefault(media["id"], last)
        elif row["media"] and stamp < end_ms and not row["deleted"] and not row["is_own"]:
            candidates += [image_item(cid, names.get(cid), row, stamp, media, reads[media["id"]]) for media in row["media"] if media["id"] in reads]
    images: list[dict] = []
    seen: dict[str, dict] = {}
    for image in sorted(candidates, key=lambda one: one["sent_at"]):
        key = image["media"][0]["id"]
        holder = proof.get(key) or seen.get(key)
        if holder is not None:   # cùng ảnh gửi lại: không thành khoản mới, khoản đang giữ ảnh ghi thêm một lần gửi lại
            holder["resent"] = holder.get("resent", 0) + 1
            continue
        seen[key] = image
        images.append(image)
    return items, images


# ---- B4 trên hao: số đọc từ ảnh ----
def _amount(value: Any) -> int | None:
    """Số tiền trong file đọc ảnh: số nguyên dương của JSON. Chuỗi, bool, số lẻ, 0 hay số âm đều là None, không ép."""
    return value if isinstance(value, int) and not isinstance(value, bool) and 0 < value <= MAX_AMOUNT else None


def _txn_time(value: Any) -> str | None:
    """Giờ giao dịch máy đọc → `YYYY-MM-DD` hoặc `YYYY-MM-DDTHH:MM[:SS][±HH:MM]`. Ngày giờ không có thật hay cách ghi lạ thì None."""
    found = TXN_TIME.fullmatch(value) if isinstance(value, str) else None
    if found is None:
        return None
    day, clock, zone = found.groups()
    if clock is None:
        text = day
    else:
        zone = "" if zone is None else "+00:00" if zone == "Z" else zone if ":" in zone else f"{zone[:3]}:{zone[3:]}"
        text = f"{day}T{clock}{zone}"
    try:
        datetime.fromisoformat(text)
    except ValueError:
        return None
    return text


def txn_day(value: str | None) -> date | None:
    """Ngày giao dịch theo giờ VN (giờ không ghi múi là giờ VN)."""
    if not value:
        return None
    when = datetime.fromisoformat(value)
    return when.astimezone(VN).date() if when.tzinfo else when.date()


def txn_key(value: str | None) -> str | None:
    """Khóa "cùng một giao dịch": ngày giờ tới phút theo giờ VN; chỉ có ngày thì không đủ để nhận ra."""
    if not value or "T" not in value:
        return None
    when = datetime.fromisoformat(value)
    return (when.astimezone(VN) if when.tzinfo else when).strftime("%Y-%m-%dT%H:%M")


def image_item(cid: str, name: str | None, row: dict, stamp: int, media: dict, read: dict) -> dict:
    """Một ảnh chuyển khoản thành một khoản thu "từ ảnh". Ngày của khoản là ngày giao dịch khi ảnh cũ được gửi lại (giao dịch trước ngày tin,
    trong 93 ngày), để đối chiếu đúng phiếu và cộng vào đúng ngày tiền vào; còn lại là ngày tin."""
    sent = datetime.fromtimestamp(stamp / 1000, VN).date()
    paid = txn_day(read["txn_time"])
    return {"message_id": row["message_id"], "conversation_id": cid, "conversation_name": name, "sent_at": stamp,
            "day": paid if paid is not None and paid < sent and (sent - paid).days < MAX_SPAN_DAYS else sent,
            "sender_name": row["sender_name"], "sender": row["sender_id"], "direction": "thu", "amount_vnd": read["amount_vnd"],
            "text": "", "media": [media], "rest": "", "source": "anh", "image_vnd": read["amount_vnd"], "image_diff": False,
            "amount_from": "anh" if read["amount_vnd"] is not None else None, "image": {key: read[key] for key in ("by", "bank", "txn_time", "candidates")},
            "_engines": read.get("engines") or []}   # số từng engine đọc (vòng phản hồi, ZALO-AGENT-01 Phần 5); không ra API


def parse_reads(data: Any) -> dict[str, dict]:
    """`money-reads.json` → {sha256 ảnh: {by, amount_vnd, bank, txn_time, candidates}}. Sai khuôn cả file thì ValueError; một mục lạ thì bỏ mục đó.

    Kết luận có số mà số hỏng thì bỏ cả mục, không đoán. "human" (cần người xem) không có số; `candidates` là các số máy đọc ra để người xem."""
    if not isinstance(data, dict) or data.get("schema") != 1 or not isinstance(data.get("reads"), dict):
        raise ValueError("money-reads")
    out: dict[str, dict] = {}
    for key, entry in data["reads"].items():
        if not (isinstance(key, str) and SHA256.fullmatch(key) and isinstance(entry, dict) and isinstance(entry.get("by"), str)
                and READ_BY.fullmatch(entry["by"])):
            continue
        human = entry["by"] == "human"
        amount = None if human else _amount(entry.get("amount_vnd"))
        if amount is None and not human:
            continue
        bank = entry.get("bank").strip() if isinstance(entry.get("bank"), str) else ""
        candidates = sorted({value for one in _dicts(entry.get("reads")) if (value := _amount(one.get("amount_vnd"))) is not None})
        engines = [{"engine": f"{one['engine']}@{one['version']}", "amount_vnd": _amount(one.get("amount_vnd"))} for one in _dicts(entry.get("reads"))[:8]
                   if all(isinstance(one.get(name), str) and ENGINE.fullmatch(one[name]) for name in ("engine", "version"))]
        out[key] = {"by": entry["by"], "amount_vnd": amount, "bank": bank if 0 < len(bank) <= 40 and bank.isprintable() else None,
                    "txn_time": _txn_time(entry.get("txn_time")), "candidates": candidates[:4], "engines": engines[:4]}
    return out


def load_reads() -> tuple[dict[str, dict], bool]:
    """Kết quả đọc ảnh, đọc lại khi file đổi (giờ sửa, cỡ). Thiếu file là máy Zalo chưa bật đọc ảnh: ({}, True).
    File hỏng, quá lớn hay sai khuôn: ({}, False) để trang cảnh báo, không báo lỗi trang."""
    path = Path(os.getenv("WEBDEBIT_ZALO_READS_DIR") or READS_DIR) / READS_FILE
    try:
        info = path.stat()
    except FileNotFoundError:
        return {}, True
    except OSError:
        return {}, False
    stamp = (str(path), info.st_mtime_ns, info.st_size)
    with _READS_LOCK:
        if _READS["stamp"] == stamp:
            return _READS["value"], _READS["ok"]
    try:
        if info.st_size > READS_MAX_BYTES or path.is_symlink() or not path.is_file():
            raise ValueError("money-reads")
        with path.open("rb") as stream:   # đọc có giới hạn: file bị thay giữa stat và đọc cũng không nạp quá cỡ
            raw = stream.read(READS_MAX_BYTES + 1)
        if len(raw) > READS_MAX_BYTES:
            raise ValueError("money-reads")
        value, ok = parse_reads(json.loads(raw)), True
    except (OSError, ValueError, TypeError, RecursionError):
        value, ok = {}, False
    with _READS_LOCK:
        _READS.update(stamp=stamp, value=value, ok=ok)
    return value, ok


def image_amount(media: list[dict], reads: dict) -> int | None:
    """Số đọc từ các ảnh chứng của một khoản: chỉ khi các ảnh đọc ra đúng một số."""
    found = {reads[one["id"]]["amount_vnd"] for one in media if one["id"] in reads and reads[one["id"]]["amount_vnd"] is not None}
    return found.pop() if len(found) == 1 else None


def _fits(host: dict, key: str | None) -> bool:
    """Chỗ (khoản gõ hay dấu) còn nhận được một ảnh theo số và ngày: chưa nhận ảnh nào theo luật này, giờ giao dịch không vênh."""
    return host["_took"] == 0 and (key is None or not host["_keys"] or key in host["_keys"])


def attach_images(items: list[dict], marks: list[dict], images: list[dict], reads: dict) -> list[dict]:
    """Không đếm hai lần (spec Thu chi, "B4 trên `hao`"). Mỗi khoản thu gõ theo mẫu và mỗi dấu "Khách báo đã chuyển" là một lần trả.
    Ảnh (theo thứ tự gửi) được gắn vào:
    1. chỗ đang giữ một ảnh cùng hội thoại, cùng số, cùng giờ giao dịch (tới phút), không giới hạn ngày: cùng một giao dịch;
    2. dấu đặt trên chính tin ảnh;
    3. khoản thu gõ cùng hội thoại cùng số (số gõ hoặc số ảnh chứng) trong 24 giờ, rồi dấu cùng hội thoại cùng số cách ngày giao dịch của ảnh
       không quá 1 ngày; chỉ khi giờ giao dịch không vênh với ảnh chỗ đó đã có, và chỗ đó chưa nhận ảnh nào theo luật này.
    Ảnh gắn theo luật 1 là gửi lại: chỗ giữ cộng thêm một vào `resent` (cộng cả số lần gửi lại mà ảnh đó đã mang). Trả các ảnh còn lại,
    mỗi ảnh một khoản."""
    index: dict[tuple, dict] = {}
    hosts = [item for item in items if item["direction"] == "thu"]
    for host in (*hosts, *marks):
        host["_keys"], host["_took"] = set(), 0
    for host in hosts:   # ảnh chứng đã gắn sẵn cho biết giao dịch của khoản gõ
        for media in host["media"]:
            read = reads.get(media["id"])
            key = txn_key(read["txn_time"]) if read and read["amount_vnd"] is not None else None
            if key:
                host["_keys"].add(key)
                index.setdefault((host["conversation_id"], read["amount_vnd"], key), host)
    kept: list[dict] = []
    for image in images:
        conv, amount, key = image["conversation_id"], image["amount_vnd"], txn_key(image["image"]["txn_time"])
        same = (conv, amount, key) if amount is not None and key else None
        owner, took = index.get(same) if same else None, False
        again = owner is not None   # luật 1: giao dịch này đã có chỗ giữ, ảnh này là một lần gửi lại
        if owner is None:
            owner = next((mark for mark in marks if mark["conversation_id"] == conv and mark["message_id"] is not None and mark["message_id"] == image["message_id"]), None)
        if owner is None and amount is not None:
            owner = next((host for host in hosts if host["conversation_id"] == conv and _fits(host, key) and amount in (host["amount_vnd"], host["image_vnd"])
                          and abs(host["sent_at"] - image["sent_at"]) <= SAME_PAYMENT_MS), None) \
                or next((mark for mark in marks if mark["conversation_id"] == conv and _fits(mark, key) and mark["amount"] == amount
                         and abs((mark["day"] - image["day"]).days) <= MARK_IMAGE_DAYS), None)
            took = owner is not None
        if owner is None:
            kept.append(image)
            if same:
                index[same] = image
            continue
        have = {media["id"] for media in owner["media"]}
        owner["media"] += [media for media in image["media"] if media["id"] not in have]
        # Gộp theo luật 1 (cùng số, cùng phút giao dịch) là cùng một giao dịch gửi lại; luật 2–3 là ảnh chứng của lần trả, không phải trùng.
        owner["resent"] = owner.get("resent", 0) + image.get("resent", 0) + int(again)
        if "_took" in owner:
            owner["_took"] += took
            if key:
                owner["_keys"].add(key)
        if same:
            index.setdefault(same, owner)
    for host in (*hosts, *marks):
        del host["_keys"], host["_took"]
    return kept


def link_targets(images: list[dict], sources: Sources, directory: Directory) -> None:
    """Đối tượng của khoản từ ảnh: hội thoại gắn đúng một sổ (ZALO-GROUP-01) thì là sổ đó; chưa gắn hoặc gắn nhiều sổ thì chưa rõ.
    `link` ghi lý do cho trang: one, many, none, hoặc failed (không đọc được danh sách nhóm gắn sổ)."""
    linked: dict[str, dict[int, Any]] = {}
    for link in _dicts(sources.read("links", "get_zalo_links", {}).get("links")):
        if isinstance(link.get("conversation_id"), str) and isinstance(link.get("customer_id"), int) and not isinstance(link["customer_id"], bool):
            linked.setdefault(link["conversation_id"], {})[link["customer_id"]] = link.get("customer_name")
    failed = "links" in sources.failed
    names = {book_id: name for book_id, name, _ in directory.books}
    for image in images:
        if image.get("target_reviewed"):   # người dùng đã gắn đối tượng (PR-3): không đè
            continue
        found = linked.get(image["conversation_id"], {})
        if len(found) == 1:
            customer, name = next(iter(found.items()))
            image["target"], image["link"] = {"kind": "so", "id": customer, "label": names.get(customer) or (name if isinstance(name, str) else None)}, "one"
        else:
            image["target"] = {"kind": None, "id": None, "label": None, "ambiguous": len(found) > 1}
            image["link"] = "failed" if failed else "many" if len(found) > 1 else "none"


# ---- B2: đối chiếu ----
def month_of(day: date) -> date:
    return day.replace(day=1)


def months(first: date, last: date) -> list[date]:
    out, current = [], month_of(first)
    while current <= last:
        out.append(current)
        current = (current + timedelta(days=32)).replace(day=1)
    return out


def _int(value: Any) -> int | None:
    """Số nguyên từ JSON (số hoặc chuỗi số); null, bool và chữ khác là None để bỏ dòng, không ép thành 0."""
    if isinstance(value, bool) or not isinstance(value, (int, str)) or not re.fullmatch(r"-?[0-9]{1,18}", str(value)):
        return None
    return int(value)


def _day(value: Any) -> date | None:
    try:
        return date.fromisoformat(value) if isinstance(value, str) else None
    except (ValueError, OverflowError):
        return None


def _dicts(value: Any) -> list[dict]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


class Sources:
    """Mỗi lần dựng đọc từng hàm DB một lần (theo tháng, theo người hoặc xe); chỉ đọc, qua các hàm đọc đã có của Bảng thu và Đội xe.

    Dòng có giá trị null hay sai khuôn bị bỏ (NULL không phải 0). Một nguồn đọc lỗi thì ghi mã vào `failed` (`receipt`, `fleet`, `directory`,
    `marks`) và trang hiện các khoản liên quan là "chưa đối chiếu được" thay vì báo lỗi cả trang hay kết luận "chưa vào sổ"."""

    def __init__(self, runner, actor: str, today: date, failed: set[str]):
        self.runner, self.actor, self.today, self.failed = runner, actor, today, failed
        self.books: dict[date, list[dict]] = {}
        self.fleet: dict[tuple, dict] = {}

    def read(self, code: str, function: str, payload: dict) -> dict:
        try:
            body = self.runner.run(function, payload, self.actor)
        except (ApiError, OSError, ValueError, TypeError, KeyError):
            body = None
        if not isinstance(body, dict):
            self.failed.add(code)
            return {}
        return body

    def receipts(self, day: date) -> list[dict]:
        out = []
        for month in months(day - timedelta(MATCH_BEFORE), min(day + timedelta(MATCH_AFTER), self.today)):
            if month not in self.books:
                rows = []
                for group in _dicts(self.read("receipt", "get_receipt_book", {"month": month.isoformat()}).get("days")):
                    for row in _dicts(group.get("rows")):
                        when, amount = _day(row.get("date")), _int(row.get("amount_vnd"))
                        if when is None or amount is None or not isinstance(row.get("customer_id"), int):
                            continue
                        rows.append({"key": ("receipt", row.get("source"), row.get("id")), "date": when, "customer": row["customer_id"], "amount": amount,
                                     "ref": {"kind": "receipt", "source": row.get("source"), "id": row.get("id"), "pid": row.get("pid"),
                                             "customer_id": row["customer_id"], "name": row.get("name"), "date": when.isoformat()}})
                self.books[month] = rows
            out += self.books[month]
        return out

    def fleet_rows(self, kind: str, entity: int, direction: str, day: date) -> list[dict]:
        out = []
        for month in months(day - timedelta(MATCH_BEFORE), min(day + timedelta(MATCH_AFTER), self.today)):
            key = (kind, entity, month)
            if key not in self.fleet:
                self.fleet[key] = self.read("fleet", "doixe_get_so", {"loai": "xe" if kind == "xe" else "nguoi", "id": entity, "thang": month.isoformat()})
            data = self.fleet[key]
            if direction == "ung":
                for row in _dicts(data.get("ung")):
                    when, amount = _day(row.get("ngay")), _int(row.get("so_tien_vnd"))
                    if when is not None and amount is not None and isinstance(row.get("id"), int) and not row.get("huy"):
                        out.append({"key": ("ung", row["id"]), "date": when, "amount": amount, "ref": {"kind": "ung", "id": row["id"], "date": when.isoformat()}})
                continue
            for trip in _dicts(data.get("chang")):
                when = _day(trip.get("ngay"))
                if when is None or trip.get("da_bo") or (kind == "tai_xe" and trip.get("nguoi_tra_id") != entity):
                    continue
                for line in _dicts(trip.get("dong")):
                    for code, money in (line.get("phi") or {}).items() if isinstance(line.get("phi"), dict) else []:
                        amount = _int(money)
                        if amount is not None and isinstance(line.get("id"), int):
                            out.append({"key": ("phi", line["id"], code), "date": when, "amount": amount,
                                        "ref": {"kind": "dong_phi", "id": line["id"], "loai_phi": code, "chang_id": trip.get("id"), "date": when.isoformat()}})
        return out


def _near(rows: list[dict], day: date) -> list[dict]:
    return [row for row in rows if day - timedelta(MATCH_BEFORE) <= row["date"] <= day + timedelta(MATCH_AFTER)]


def _settle(item: dict, status: str, row: dict | None = None, shared: bool = False) -> None:
    item.update(status=status, shared=shared, ledger_ref=row["ref"] if row else None, ledger_vnd=row["amount"] if row else None)


def _components(items: list[dict], cands: dict) -> list[list[dict]]:
    """Nhóm các khoản báo có chung ít nhất một dòng ứng viên (trực tiếp hay qua khoản khác)."""
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
    return list(groups.values())


def _saturate(members: list[dict], cands: dict) -> dict | None:
    """Ghép mỗi khoản báo với một dòng riêng (ghép cực đại, đường tăng của Kuhn, khoản sớm trước, dòng sớm trước).
    Trả {khóa dòng: khoản} khi mọi khoản đều có dòng; None khi không có cách nào đủ."""
    owner: dict = {}

    def augment(item: dict, seen: set) -> bool:
        for row in sorted(cands[id(item)], key=lambda one: (one["date"], str(one["key"]))):
            if row["key"] in seen:
                continue
            seen.add(row["key"])
            if row["key"] not in owner or augment(owner[row["key"]], seen):
                owner[row["key"]] = item
                return True
        return False

    return owner if all(augment(item, set()) for item in sorted(members, key=lambda one: one["sent_at"])) else None


def pair_exact(items: list[dict], rows_of, claimed: set) -> None:
    """Khoản báo đúng số với dòng sổ trong khoảng ngày thì ứng đúng một dòng. Trong mỗi nhóm khoản tranh chung dòng, nếu có cách ghép đủ
    cho mọi khoản thì ghép (chọn theo thứ tự thời gian); không đủ dòng thì cả nhóm để người xem chọn (`shared`), không tự chọn."""
    cands = {id(item): [row for row in rows_of(item) if row["amount"] == item["amount_vnd"] and row["key"] not in claimed] for item in items}
    for members in _components(items, cands):
        owner = _saturate(members, cands)
        if owner is None:
            for item in members:
                _settle(item, "AMOUNT_DIFF", cands[id(item)][0], shared=True)
                claimed.update(row["key"] for row in cands[id(item)])   # dòng đang chờ người chọn thì không gán cho khoản khác nữa
            continue
        rows = {row["key"]: row for item in members for row in cands[id(item)]}
        for key, item in owner.items():
            claimed.add(key)
            _settle(item, "RECORDED", rows[key])


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


def reconcile(items: list[dict], directory: Directory, sources: Sources, today: date, reserved: frozenset = frozenset()) -> None:
    """Gán `status`, `ledger_ref`, `ledger_vnd`, `shared`, `unchecked` cho từng khoản báo theo bảng trạng thái của spec (Luồng 2).

    Chủ ý: chi khớp từng dòng phí chứ không khớp tổng của chặng; ứng cho xe không có tài xế là chưa rõ đối tượng; "chi lương tài xế Hùng"
    có người nên đi ghép sổ Đội xe (chỉ chi không có xe hay người mà nói lương, văn phòng… mới là `NO_LEDGER`).

    Khoản từ ảnh (B4) không ghép đoán (lệch số, gợi ý) vào phiếu mà một dấu "Khách báo đã chuyển" đang giữ (`reserved`, mã phiếu): ảnh
    khác số với phiếu đó thường là lần trả khác. Khoản gõ tay vẫn ghép như cũ vì gõ nhầm số là chuyện thường. Ngày của khoản từ ảnh đã
    đặt sẵn (ngày giao dịch khi ảnh cũ được gửi lại); khoản khác lấy ngày tin."""
    for item in items:
        if "day" not in item:
            item["day"] = datetime.fromtimestamp(item["sent_at"] / 1000, VN).date()
        item["status"], item["shared"], item["ledger_ref"], item["ledger_vnd"], item["unchecked"] = None, False, None, None, False
    claimed: set = set()
    for item in items:
        kind, entity, direction = item["target"]["kind"], item["target"]["id"], item["direction"]
        if item.get("currency") == "CNY":   # tiền tệ: sổ khách và Đội xe tính VND, không có dòng nào để ghép
            item["status"] = "NO_LEDGER"
        elif item["amount_vnd"] is None:
            item["status"] = "NO_AMOUNT"
        elif direction == "thu" and kind == "so":
            item["track"] = "receipt"
            item["rows"] = lambda one=item: [row for row in _near(sources.receipts(one["day"]), one["day"]) if row["customer"] == one["target"]["id"]]
        elif direction == "ung" and kind == "xe" and directory.xe.get(entity, {}).get("tai_xe_id"):   # xe gắn tay mà danh mục đọc lỗi: không sập trang
            item["track"] = "fleet"
            item["rows"] = lambda one=item: _near(sources.fleet_rows("tai_xe", directory.xe[one["target"]["id"]]["tai_xe_id"], "ung", one["day"]), one["day"])
        elif (direction == "ung" and kind == "tai_xe") or (direction == "chi" and kind in ("xe", "tai_xe")):
            item["track"] = "fleet"
            item["rows"] = lambda one=item: _near(sources.fleet_rows(one["target"]["kind"], one["target"]["id"], one["direction"], one["day"]), one["day"])
        elif direction == "chi" and OFFICE.search(item["rest"]):
            item["status"] = "NO_LEDGER"
    known = [item for item in items if "rows" in item]
    pair_exact(known, lambda one: one["rows"](), claimed)

    def guess(one: dict, rows: list[dict]) -> list[dict]:
        return [row for row in rows if one.get("source") != "anh" or row["ref"].get("pid") not in reserved]

    pair_single([item for item in known if item["status"] is None], lambda one: guess(one, one["rows"]()), claimed, "AMOUNT_DIFF")
    unknown_thu = [item for item in items if item["status"] is None and item["direction"] == "thu" and "rows" not in item]
    anywhere = lambda one: guess(one, [row for row in _near(sources.receipts(one["day"]), one["day"]) if row["amount"] == one["amount_vnd"]])   # noqa: E731
    pair_single(unknown_thu, anywhere, claimed, "SUGGEST")
    for item in items:
        if item["status"] is None:
            if "rows" not in item:
                item["status"] = "UNKNOWN_TARGET"
            elif item["track"] in sources.failed:
                item["status"], item["unchecked"] = "WAITING", True   # không đọc được sổ thì không kết luận "chưa vào sổ"
            else:
                item["status"] = "MISSING" if today > item["day"] + timedelta(MISSING_AFTER) else "WAITING"
        item["unchecked"] = item["unchecked"] or (item["status"] in ("UNKNOWN_TARGET", "NO_LEDGER") and "directory" in sources.failed) \
            or (item["status"] == "UNKNOWN_TARGET" and item["direction"] == "thu" and "receipt" in sources.failed)   # chưa kiểm được SUGGEST


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


def read_marks(conversations: list[dict], sources: Sources, start: date, end: date) -> list[dict]:
    """Dấu "Khách báo đã chuyển" hợp lệ của các nhóm đã chọn, ngày báo trong khoảng xem (mỗi nhóm đọc một lần). Đọc trước khi đối chiếu
    để ảnh chuyển khoản của cùng lần trả gộp vào dấu (`attach_images`)."""
    out = []
    for conversation in conversations:
        for mark in _dicts(sources.read("marks", "get_marks", {"conversation_id": conversation["conversation_id"]}).get("marks")):
            day, amount = _day(mark.get("on_date")), _int(mark.get("amount_vnd"))
            if mark.get("kind") != "paid_claim" or mark.get("status") not in MARK_STATUS or day is None or amount is None or amount <= 0 \
                    or not isinstance(mark.get("customer_id"), int) or not start <= day <= end:
                continue
            out.append({"raw": mark, "conversation_id": conversation["conversation_id"], "conversation_name": conversation["display_name"],
                        "message_id": mark.get("message_id") if isinstance(mark.get("message_id"), str) else None, "day": day, "amount": amount, "media": []})
    return out


def mark_items(marks: list[dict], directory: Directory, taken_messages: set, taken_receipts: set) -> tuple[list[dict], int]:
    """Dấu hiện như khoản thu, trạng thái do SQL chấm (cùng luật), không chép sang đâu.

    Cửa sổ ngày của dấu tính từ `on_date` (ngày khách báo đã chuyển), của khoản chat từ ngày tin. Dấu cùng tin với một khoản chat, hoặc có
    phiếu (`receipt_pid`) mà một khoản chat đã ứng, thì ẩn: giữ khoản chat, tổng thu không cộng hai lần (trả thêm số dấu đã ẩn)."""
    names = {book_id: name for book_id, name, _ in directory.books}
    items, hidden, seen = [], 0, set()
    for entry in marks:
        mark = entry["raw"]
        pid = mark.get("receipt_pid") if isinstance(mark.get("receipt_pid"), str) else None
        if mark.get("message_id") in taken_messages or (pid and (pid in taken_receipts or pid in seen)):
            hidden += 1
            continue
        seen.add(pid)
        try:
            sent = int(datetime.fromisoformat(mark["message_at"]).timestamp() * 1000) if isinstance(mark.get("message_at"), str) else None
        except (ValueError, OverflowError, OSError):
            sent = None
        if sent is not None and not 946_684_800_000 <= sent <= 4_102_444_800_000:   # ngoài 2000–2100 là giờ vô lý: bỏ giờ, giữ dấu
            sent = None
        items.append({"message_id": mark.get("message_id"), "conversation_id": entry["conversation_id"], "conversation_name": entry["conversation_name"],
                      "sent_at": sent, "sender_name": mark.get("message_sender"), "direction": "thu", "amount_vnd": entry["amount"],
                      "text": str(mark.get("message_excerpt") or mark.get("note") or "")[:300], "media": entry["media"], "day": entry["day"], "source": "mark",
                      "target": {"kind": "so", "id": mark["customer_id"], "label": names.get(mark["customer_id"])},
                      "status": MARK_STATUS[mark["status"]], "shared": False, "unchecked": False, "ledger_vnd": None,
                      "ledger_ref": {"kind": "receipt", "pid": pid} if pid else None, "resent": entry.get("resent", 0)})
    return items, hidden


def _week(monday: date) -> dict:
    iso = monday.isocalendar()
    return {"week": f"{iso.year}-W{iso.week:02d}", "from": monday.isoformat(), "to": (monday + timedelta(6)).isoformat(),
            "decided": {}, "reviewed": 0, "human_handled": 0, "engines": {}}


def feedback(read_images: list[dict], items: list[dict]) -> dict:
    """Vòng phản hồi (ZALO-AGENT-01 Phần 5), chỉ số đếm và mã, theo tuần thứ Hai–Chủ nhật (giờ VN) của ngày khoản:

    - `decided`: ảnh chuyển khoản đã đọc (đứng riêng hay gộp vào khoản gõ sau đó) theo kết luận `by` (mã của máy đọc, hoặc human: cần người xem);
    - `reviewed`: ảnh người đã chốt số (xác nhận, sửa số) hay loại; `human_handled`: trong đó, ảnh "cần xem". Chỉ gắn đối tượng thì chưa là chốt;
    - `engines`: với mỗi ảnh đã chốt, mỗi `engine@phiên bản` đọc ra số trùng số cuối cùng là đúng, khác là sai; ảnh bị loại thì mọi số đọc
      ra đều sai; xác nhận mà vẫn không có số thì không chấm.
    Không có chữ của tin, lý do hay tên: `summary()` của tab Máy chạy dùng thẳng bản này."""
    weeks: dict[date, dict] = {}

    def week_of(day: date) -> dict:
        monday = day - timedelta(days=day.weekday())
        return weeks.setdefault(monday, _week(monday))

    for image in read_images:
        decided = week_of(image["day"])["decided"]
        decided[image["image"]["by"]] = decided.get(image["image"]["by"], 0) + 1
    for item in items:
        review = item.get("review") if item.get("source") == "anh" else None
        decision = (review or {}).get("decision")
        if not review or (decision not in ("confirm", "not_cash") and item.get("amount_from") != "sua"):
            continue
        week = week_of(item["day"])
        week["reviewed"] += 1
        week["human_handled"] += item["image"]["by"] == "human"
        final = None if decision == "not_cash" else item["amount_vnd"]
        if final is None and decision != "not_cash":
            continue
        for read in item.get("_engines") or []:
            if read["amount_vnd"] is not None:
                score = week["engines"].setdefault(read["engine"], {"right": 0, "wrong": 0})
                score["right" if read["amount_vnd"] == final else "wrong"] += 1
    return {"weeks": [weeks[monday] for monday in sorted(weeks, reverse=True)]}


def read_reviews(items: list[dict], sources: Sources) -> dict[str, dict]:
    """Trạng thái xác nhận (PR-3) của các khoản đang xem, theo mã tin; đọc lỗi thì `sources_failed` ghi `reviews`."""
    ids = sorted({item["message_id"] for item in items if isinstance(item.get("message_id"), str)})[:5000]
    reviews = sources.read("reviews", "get_cash_reviews", {"message_ids": ids}).get("reviews") if ids else None
    return {key: value for key, value in reviews.items() if isinstance(key, str) and isinstance(value, dict)} if isinstance(reviews, dict) else {}


def apply_reviews(items: list[dict], reviews: dict[str, dict], directory: Directory) -> list[dict]:
    """Số và đối tượng người dùng sửa thay cho số đọc từ tin; trả các khoản đã loại (không đối chiếu, không cộng tổng). Giá trị lạ thì bỏ.

    Tin sinh nhiều khoản (một tin nhiều ảnh chuyển khoản) thì không áp: xác nhận theo tin không biết là ảnh nào (route cũng từ chối)."""
    dropped = []
    per_message: dict[str, int] = {}
    for item in items:
        per_message[item["message_id"]] = per_message.get(item["message_id"], 0) + 1
    for item in items:
        state = reviews.get(item["message_id"])
        if not state or per_message[item["message_id"]] > 1:
            continue
        item["review"] = {key: state.get(key) for key in ("decision", "reason", "reviews", "last_action", "last_by", "last_at")}
        amount = _int(state.get("amount_vnd"))
        if amount is not None and 0 < amount <= MAX_AMOUNT:
            item["amount_vnd"], item["amount_from"] = amount, "sua"
            item["image_diff"] = item.get("image_vnd") is not None and amount != item["image_vnd"]
        target = state.get("target")
        if isinstance(target, dict) and target.get("kind") in TARGET_KINDS and positive_int(target.get("id")):
            item["target"] = {"kind": target["kind"], "id": target["id"], "label": directory.label(target["kind"], target["id"]), "ambiguous": False}
            item["target_reviewed"] = True
            item.pop("link", None)
        if state.get("decision") == "not_cash":   # như một khoản đã đối chiếu xong: không phiếu, không dòng sổ
            item.update(status="NOT_CASH", shared=False, ledger_ref=None, ledger_vnd=None, unchecked=False)
            item.setdefault("target", {"kind": None, "id": None, "label": None, "ambiguous": False})   # ảnh bị loại bỏ qua bước gắn đối tượng
            if "day" not in item:   # ngày của khoản gõ do bước đối chiếu gán; khoản loại bỏ qua bước đó
                item["day"] = datetime.fromtimestamp(item["sent_at"] / 1000, VN).date()
            dropped.append(item)
    return dropped


def handle_review(raw: bytes, runner, actor: str) -> tuple[int, dict]:
    """POST /api/v7/cash-chat/review (ZALO-THU-CHI-01 PR-3): xác nhận, gắn đối tượng, sửa số hay loại một khoản báo. Không ghi tiền.

    Thân lệnh `{message_id, action, value, reason, request_id}`: `value` là chuỗi VND khi sửa số (`amount`), `{kind, id}` khi gắn đối tượng
    (`target`), không có khi xác nhận (`confirm`) hay loại (`not_cash`, bắt buộc lý do). Tin phải còn trong gói chat và chưa xóa; mã hội
    thoại lấy từ gói, không lấy từ trang. Hàm SQL ghi người làm và trạng thái trước → sau; bấm lặp cùng `request_id` chỉ ghi một lần."""
    invalid = ERRORS["INVALID_CASH_REVIEW"][1]
    try:
        body = json.loads(raw)
    except ValueError:
        body = None
    if not isinstance(body, dict) or not set(body) <= REVIEW_FIELDS or body.get("action") not in REVIEW_ACTIONS:
        bad("INVALID_CASH_REVIEW", invalid)
    action, value, reason, key, message = (body.get(name) for name in ("action", "value", "reason", "request_id", "message_id"))
    if (not isinstance(message, str) or not v7_zalo_chat.MESSAGE_ID.fullmatch(message) or not isinstance(key, str) or not key.strip()
            or len(key) > 200 or (reason is not None and (not isinstance(reason, str) or len(reason) > 500))):
        bad("INVALID_CASH_REVIEW", invalid)
    reason = reason.strip() if isinstance(reason, str) and reason.strip() else None
    if action == "not_cash" and reason is None:
        bad("REASON_REQUIRED", ERRORS["REASON_REQUIRED"][1])
    payload = {"message_id": message, "action": action, "request_id": key, "reason": reason}
    if action == "amount":
        if not vnd(value) or value == "0" or int(value) > MAX_AMOUNT:
            bad("INVALID_CASH_REVIEW", invalid)
        payload["amount_vnd"] = value
    elif action == "target":
        if not isinstance(value, dict) or not set(value) <= {"kind", "id", "label"} or value.get("kind") not in TARGET_KINDS or not positive_int(value.get("id")):
            bad("INVALID_CASH_REVIEW", invalid)
        payload["target"] = {"kind": value["kind"], "id": value["id"]}
    elif value is not None:
        bad("INVALID_CASH_REVIEW", invalid)
    conversation, shaped = message_conversation(message)
    reads, _ = load_reads()
    if sum(1 for media in shaped["media"] if media.get("id") in reads) > 1:
        bad("MULTIPLE_IMAGES", ERRORS["MULTIPLE_IMAGES"][1])
    payload["conversation_id"] = conversation
    result = runner.run("record_cash_review", payload, actor)
    with _LOCK:
        _CACHE.clear()   # lần hỏi kế tiếp của trang thấy ngay kết quả bấm, không đợi hết thời gian giữ kết quả
    return 200, result


def message_conversation(message: str) -> tuple[str, dict]:
    """(mã hội thoại, tin) của một tin còn trong gói chat; tin không có (gói chưa tới, nhóm bỏ chọn) hay đã xóa thì MESSAGE_NOT_FOUND."""
    try:
        store = v7_zalo_chat.get_store()
        found = store.latest.get(message)
        page = store.messages(found[0], 0, 1, "", message) if found else None
    except v7_zalo_chat.ChatError as exc:
        if exc.status == 503:
            raise ApiError(503, exc.code, exc.message) from None
        page = None
    if not page or not page["messages"] or page["messages"][0]["deleted"]:
        bad("MESSAGE_NOT_FOUND", ERRORS["MESSAGE_NOT_FOUND"][1])
    return found[0], page["messages"][0]


def _public(item: dict) -> dict:
    out = {key: item.get(key) for key in ("message_id", "conversation_id", "conversation_name", "sent_at", "sender_name", "direction", "amount_vnd", "text",
                                          "media", "status", "shared", "unchecked", "ledger_ref", "ledger_vnd", "image_vnd", "amount_from", "image",
                                          "link", "review", "amount_cny")}
    out["currency"] = item.get("currency", "VND")
    out["image_diff"] = bool(item.get("image_diff"))
    out["target_from"] = "sua" if item.get("target_reviewed") else None   # Luồng 3: đối tượng người dùng gắn tay, không phải máy tự khớp
    out["resent"] = item.get("resent", 0)   # Luồng 4: số lần cùng giao dịch được gửi lại (chỉ tính một khoản); 0 là không trùng
    out["day"] = item["day"].isoformat()
    out["source"] = item.get("source", "chat")
    out["target"] = {key: item["target"].get(key) for key in ("kind", "id", "label")}
    out["ambiguous"] = bool(item["target"].get("ambiguous"))
    return out


def totals(items: list[dict]) -> dict:
    items = [item for item in items if item["status"] != "NOT_CASH"]   # người dùng đã loại (PR-3): không phải thu chi, không đếm, không cộng
    out = {"thu_vnd": 0, "chi_vnd": 0, "ung_vnd": 0, "thu_count": 0, "chi_count": 0, "ung_count": 0, "no_amount": 0,
           "missing": sum(item["status"] == "MISSING" for item in items),
           "amount_diff": sum(item["status"] == "AMOUNT_DIFF" or bool(item.get("image_diff")) for item in items),
           "from_image": sum(item.get("source") == "anh" and item["amount_vnd"] is not None for item in items)}
    out["cny"] = {"thu": 0, "chi": 0, "ung": 0, "count": 0, "no_amount": 0}   # khoản tính bằng tệ: tổng riêng, không vào tổng VND
    for item in items:
        if item.get("currency") == "CNY":
            if item.get("amount_cny") is None:
                out["cny"]["no_amount"] += 1
            else:
                out["cny"][item["direction"]] += item["amount_cny"]
                out["cny"]["count"] += 1
            continue
        if item["amount_vnd"] is None:
            out["no_amount"] += 1
        else:
            out[item["direction"] + "_vnd"] += item["amount_vnd"]
            out[item["direction"] + "_count"] += 1
    return out


def zalo_view(now: float) -> dict:
    """Tuổi dữ liệu Zalo theo `status.json` của máy Zalo (ZALO-AGENT-01 Phần 6) thay cho `zalo_age_seconds` của spec cũ: có đủ tín hiệu
    "máy im", "Zalo chưa mở" và số phút, không phải đoán từ giờ tin cuối."""
    return v7_machine.zalo_brief(now)


def _single_flight(key: tuple, now: float, compute) -> dict:
    """Kết quả giữ `CACHE_SECONDS` giây; nhiều người cùng hỏi lúc hết hạn thì chỉ một lượt dựng, những người kia chờ kết quả đó."""
    with _LOCK:
        hit = _CACHE.get(key)
        if hit is not None and now - hit[0] <= CACHE_SECONDS:
            return hit[1]
        flight = _FLIGHTS.get(key)
        leader = flight is None
        if leader:
            flight = _FLIGHTS[key] = Future()
    if not leader:
        try:
            return flight.result(timeout=FLIGHT_WAIT)
        except FlightTimeout:
            return compute()   # lượt kia quá lâu: tự dựng, không giữ kết quả
    try:
        value = compute()
    except BaseException as exc:
        with _LOCK:
            _FLIGHTS.pop(key, None)
        flight.set_exception(exc)
        raise
    with _LOCK:
        if len(_CACHE) > 16:
            _CACHE.clear()
        _CACHE[key] = (now, value)
        _FLIGHTS.pop(key, None)
    flight.set_result(value)
    return value


def build(start: date, end: date, runner, actor: str, now: float | None = None) -> dict:
    now = time.time() if now is None else now
    today = datetime.fromtimestamp(now, VN).date()
    zalo = zalo_view(now)
    try:
        store = v7_zalo_chat.get_store()
    except v7_zalo_chat.ChatError:
        return {"unavailable": True, "zalo": zalo}
    try:
        core = _single_flight((start, end, store.token()), now, lambda: _core(store, start, end, runner, actor, today))
        last_ms = max((row["last_message_at"] or 0 for row in store.conversations()), default=0) or None
    except DATA_ERRORS as exc:
        print(f"V7 thu chi: dữ liệu lạ ({type(exc).__name__}), trả chưa đọc được", file=sys.stderr, flush=True)   # chỉ tên lỗi, không chữ của tin
        return {"unavailable": True, "reason": "UNREADABLE", "zalo": zalo}
    return {"unavailable": False, "from": start.isoformat(), "to": end.isoformat(), "today": today.isoformat(), "zalo": zalo,
            "bundle_at": store.report.get("built_at") if isinstance(store.report.get("built_at"), str) else None, "last_message_at": last_ms, **core}


def load_directory(sources: Sources) -> Directory:
    """Sổ khách, xe và người của Đội xe qua hai hàm đọc có sẵn; đọc lỗi thì `sources.failed` có `directory` và danh sách thiếu phần đó."""
    try:
        body = sources.read("directory", "list_customers", {})
        rows = [row for row in _dicts(body.get("customers")) if isinstance(row.get("id"), int) and isinstance(row.get("name"), str)]   # một dòng lạ không làm mất cả danh sách
        customers = v7_api_sheet.with_display_names({**body, "customers": rows}).get("customers", [])
    except DATA_ERRORS:
        customers = []
        sources.failed.add("directory")
    fleet = sources.read("directory", "doixe_get_tong", {"thang": None}).get("danh_muc")
    fleet = fleet if isinstance(fleet, dict) else {}
    return Directory(_dicts(customers), _dicts(fleet.get("xe")), _dicts(fleet.get("nguoi")))


def handle_targets(query: str, runner, actor: str, now: float | None = None) -> dict:
    """GET /api/v7/cash-chat/targets (Luồng 3): sổ, xe, tài xế cho ô "Gắn sổ/xe" của trang Thu chi; chỉ quản lý (cùng tiền tố).

    Trang chỉ hỏi khi người dùng mở ô gắn. Xe và người đã thôi dùng không vào danh sách chọn (vẫn hiện đúng tên nếu đã gắn từ trước).
    Đọc lỗi thì `failed: true` kèm phần đọc được, không 500."""
    if query:
        bad()
    now = time.time() if now is None else now
    failed: set[str] = set()
    directory = load_directory(Sources(runner, actor, datetime.fromtimestamp(now, VN).date(), failed))
    rows = {kind: [] for kind in TARGET_KINDS}
    for (kind, entity), label in directory.labels.items():
        if kind == "so" or (kind, entity) in directory.active:
            rows[kind].append({"id": entity, "label": label})
    for kind in rows:
        rows[kind].sort(key=lambda row: (v7_zalo_chat.fold(row["label"]), row["id"]))
    return {**rows, "failed": bool(failed)}


def _core(store, start: date, end: date, runner, actor: str, today: date) -> dict:
    start_ms = int(datetime.combine(start, datetime.min.time(), VN).timestamp() * 1000)
    end_ms = int(datetime.combine(end + timedelta(1), datetime.min.time(), VN).timestamp() * 1000)
    failed: set[str] = set()
    sources = Sources(runner, actor, today, failed)
    holder: dict = {}

    def directory_of() -> Directory:
        if "directory" not in holder:
            holder["directory"] = load_directory(sources)
        return holder["directory"]

    # Một giới hạn số nhóm cho cả tin chat, ảnh và dấu: nhóm có tin mới nhất trước.
    everything = store.conversations()
    conversations = everything[:MAX_CONVERSATIONS]
    reads, reads_ok = load_reads()
    if not reads_ok:
        failed.add("reads")
    items, images = collect(store, directory_of, start_ms, end_ms, conversations, reads)
    # Số ảnh chứng của khoản gõ (chỉ ảnh chứng) có trước khi gộp, để ảnh gộp sau không xóa mất cảnh báo "mẫu X, ảnh Y".
    for item in items:
        item["image_vnd"], item["amount_from"] = image_amount(item["media"], reads), None
        if item["amount_vnd"] is None and item["image_vnd"] is not None and item.get("currency") != "CNY":   # mẫu không đọc được số mà ảnh chứng đọc được
            item["amount_vnd"], item["amount_from"] = item["image_vnd"], "anh"
        item["image_diff"] = item["image_vnd"] is not None and item["amount_from"] is None and item["amount_vnd"] not in (None, item["image_vnd"])
    before = sum(image["day"] < start for image in images)   # ảnh cũ gửi lại: giao dịch trước khoảng xem, không cộng vào khoảng này
    images = [image for image in images if image["day"] >= start]
    marks = read_marks(conversations, sources, start, end) if conversations else []
    # PR-3: số và đối tượng người dùng sửa có hiệu lực trước khi gộp ảnh chứng (số sửa có thể khớp đúng ảnh của khoản đó) và trước khi
    # đối chiếu; khoản đã loại không giữ ảnh, không đối chiếu, không cộng tổng.
    read_images = list(images)   # mọi ảnh đã đọc trong khoảng, trước khi loại hay gộp: mẫu số "máy kết luận" của vòng phản hồi
    reviews = read_reviews(items + images, sources) if items or images else {}
    dropped = apply_reviews(items + images, reviews, directory_of()) if reviews else []
    if dropped:
        items = [item for item in items if item.get("status") != "NOT_CASH"]
        images = [image for image in images if image.get("status") != "NOT_CASH"]
    images = attach_images(items, marks, images, reads)
    if images:
        link_targets(images, sources, directory_of())
        items += images
    if items:
        held = frozenset(pid for mark in marks if isinstance(pid := mark["raw"].get("receipt_pid"), str))
        reconcile(items, directory_of(), sources, today, held)
    items += dropped
    for item in items:
        if item.get("link") == "failed":
            item["unchecked"] = True
    marked, hidden = mark_items(marks, directory_of(), {item["message_id"] for item in items},
                                {item["ledger_ref"]["pid"] for item in items if item.get("ledger_ref") and item["ledger_ref"].get("pid")}) if conversations else ([], 0)
    for item in marked:   # dấu giữ số người nhập; số ảnh chỉ để người xem so
        item["image_vnd"] = image_amount(item["media"], reads)
    items += marked
    items.sort(key=lambda item: (item["day"], item["sent_at"] or 0), reverse=True)
    looped = feedback(read_images, items)
    if start <= today <= end:   # tuần hiện tại cho summary() của tab Máy chạy (máy không có kết nối DB): chỉ số đếm và mã
        monday = today - timedelta(days=today.weekday())
        current = next((week for week in looped["weeks"] if week["from"] == monday.isoformat()), None) or _week(monday)
        v7_machine.FEEDBACK.clear()
        v7_machine.FEEDBACK.update(at=datetime.now(VN).isoformat(timespec="seconds"), **current)
    return {"items": [_public(item) for item in items], "totals": totals(items), "sources_failed": sorted(failed), "marks_hidden": hidden,
            "feedback": looped,
            "conversations_skipped": len(everything) - len(conversations), "images_before": before,
            "counts": {code: sum(item["status"] == code for item in items) for code in STATUSES}}


def handle_get(query: str, runner, actor: str, now: float | None = None) -> dict:
    """GET /api/v7/cash-chat?from=YYYY-MM-DD&to=YYYY-MM-DD&status=CODE[,CODE]: mặc định 7 ngày tới hôm nay (giờ VN), mọi trạng thái trừ
    NOT_CASH (khoản người dùng đã loại, PR-3: chỉ hiện khi hỏi `status=NOT_CASH`). Tổng và `counts` tính trên cả khoảng, không theo `status`;
    `status` chỉ lọc `items`."""
    now = time.time() if now is None else now
    start, end, wanted = parse_query(query, datetime.fromtimestamp(now, VN).date())
    body = build(start, end, runner, actor, now)
    if not body.get("unavailable"):
        keep = wanted or set(STATUSES) - {"NOT_CASH"}
        body = {**body, "items": [item for item in body["items"] if item["status"] in keep]}
    return body
