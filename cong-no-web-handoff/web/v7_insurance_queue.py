"""Giấy chứng nhận bảo hiểm trong group Zalo đối chiếu với phí Bảo hiểm của sổ (BAO-HIEM-ZALO-01, PR-1: chỉ đọc).

specs/v7-bao-hiem-zalo.md. Giấy là nguồn phụ như bảng PS: không cộng tiền, không ghi gì; web chỉ nhắc và mở PDF gốc.
`insurance-web.json` do máy có Zalo ghi (schema_version 1, `sha256` tính trên các dòng); đọc lỗi, sai phiên bản hay sai hash thì
cả mục là `unavailable` và sổ vẫn mở bình thường.

Ghép (sau P0, người dùng chốt 19/11/2026):
1. Giấy có `status` khác `ok`, số NULL hoặc cảnh báo không bắt đầu bằng `info:` → CERT_REVIEW; cảnh báo `info:` chỉ để hiện.
2. Booking + container chỉ ghép được với chuyến web: dòng sổ gốc không có booking.
3. Giấy không ghép được theo booking (NO_BOOKING, NOT_FOUND) mà trong mọi sổ có đúng một chuyến cùng container và tổng các khoản
   Bảo hiểm của chuyến đó bằng đúng số giấy → DONE `match: "container"`. Khớp container chỉ để hiện: không sinh trạng thái nào khác.
4. CLASSIFY / MONTH_LOCKED hiện trong "Bảo hiểm cần xem" (chưa có máy đổi loại: PR-3 hoãn).
"""

from __future__ import annotations

import hashlib
import json
import re
import threading
from collections import Counter
from pathlib import Path
from typing import Any

from v7_price_queue import container_key
from v7_ps_queue import fee_type_ids, pool, vnd_text
from v7_sheet_queue import read_snapshot

SCHEMA_VERSION = 1
CERT_PREFIX = "/api/v7/insurance/cert/"
MAX_PDF_BYTES = 25 * 1024 * 1024
HEX64 = re.compile(r"[0-9a-f]{64}")
# Hiện trong "Bảo hiểm cần xem" của sổ có chuyến; ba mã còn lại không có chuyến nên nằm ở Việc cần làm.
REVIEW = ("SHEET_MISSING", "AMOUNT_DIFF", "AMBIGUOUS", "CLASSIFY", "MONTH_LOCKED")
NO_TRIP = ("NO_BOOKING", "NOT_FOUND", "CERT_REVIEW")
CLASSIFY_HINT = "Khoản Khác bằng đúng số giấy: đổi loại thành Bảo hiểm bằng nút sửa loại phí, tổng không đổi."


def rows_hash(rows: list[dict]) -> str:
    """Hash của máy ghi file: các dòng, khóa xếp thứ tự, không khoảng trắng, UTF-8 không thoát."""
    text = json.dumps(rows, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_insurance_snapshot(path: str | Path) -> dict[str, Any]:
    snapshot = read_snapshot(path, "Insurance snapshot")
    if type(snapshot.get("schema_version")) is not int or snapshot["schema_version"] != SCHEMA_VERSION:
        raise ValueError("Insurance snapshot schema mismatch")
    if any(not isinstance(row, dict) or not isinstance(row.get("sha256"), str) or not HEX64.fullmatch(row["sha256"])
           for row in snapshot["rows"]):
        raise ValueError("Insurance snapshot row invalid")
    if rows_hash(snapshot["rows"]) != snapshot["sha256"]:
        raise ValueError("Insurance snapshot hash mismatch")
    return snapshot


class ContainerIndex:
    """Chuyến và dòng sổ gốc của mọi sổ đã đọc, tra theo container, để khớp container và biết "chưa có chuyến" qua nhiều sổ.

    Mỗi lượt chiếu một sổ ghi đè phần của sổ đó. `complete` chỉ bật khi lượt nền của hộp việc đã đọc đủ mọi sổ đang dùng:
    trước đó "đúng một chuyến ứng viên" chưa chắc đúng nên không khớp container và nhóm "chưa có chuyến" chưa tính.
    """

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.by_customer: dict[Any, list[dict]] = {}
        self.by_container: dict[str, dict[Any, list[dict]]] = {}
        self.complete = False

    def replace(self, customer: Any, entries: list[dict]) -> None:
        with self.lock:
            for entry in self.by_customer.get(customer, ()):
                self.by_container.get(entry["container"], {}).pop(customer, None)
            self.by_customer[customer] = entries
            for entry in entries:
                self.by_container.setdefault(entry["container"], {}).setdefault(customer, []).append(entry)

    def lookup(self, container: str) -> list[dict]:
        with self.lock:
            return [entry for found in self.by_container.get(container, {}).values() for entry in found]

    def mark_complete(self, customers: set) -> None:
        with self.lock:
            if customers <= set(self.by_customer):
                self.complete = True


def book_entries(ledger: dict, fee_types: list[dict]) -> list[dict]:
    """Một dòng cho mỗi chuyến web và dòng sổ gốc: khoản Bảo hiểm và các khoản chưa phân loại (Khác, Phụ phí ban đầu)."""
    insured = fee_type_ids(fee_types)["bao_hiem"]
    plain = {t["id"] for t in fee_types if isinstance(t, dict) and t.get("system_key") in ("other", "initial")}
    out = []
    for target in pool(ledger):
        lines = [(line.get("fee_type_id"), int(line["amount_vnd"])) for line in target["lines"]]
        paid = [amount for type_id, amount in lines if insured is not None and type_id == insured]
        out.append({"customer_id": ledger.get("customer_id"), "kind": target["kind"], "id": target["id"],
                    "container": target["container"], "month": target["month"], "locked": bool(target["locked"]),
                    # Sổ gốc không có booking (đo 19/11/2026): chỉ chuyến web ghép được theo booking.
                    "booking": target["booking"] if target["kind"] == "trip" else "",
                    "insured": sum(paid) if paid else None, "plain": [a for type_id, a in lines if type_id in plain],
                    "counted_vnd": target["total"]})
    return out


def _amount(value: Any) -> int | None:
    return value if type(value) is int else None


def _warnings(row: dict) -> tuple[list[str], list[str]]:
    """(cảnh báo chặn, cảnh báo `info:`); `warnings` sai hình dạng là cảnh báo chặn."""
    raw = row.get("warnings")
    items = [] if raw is None else [str(w) for w in raw] if isinstance(raw, list) else ["warnings malformed"]
    return [w for w in items if not w.startswith("info:")], [w for w in items if w.startswith("info:")]


def _plan(trip: dict, cert: int) -> tuple[str, bool]:
    """(trạng thái, hai khoản cùng số) khi giấy ghép đúng một chuyến theo booking + container."""
    if trip["insured"] is not None:
        return ("DONE" if trip["insured"] == cert else "AMOUNT_DIFF"), False
    same = [amount for amount in trip["plain"] if amount == cert]
    if len(same) == 1:
        return ("MONTH_LOCKED" if trip["locked"] else "CLASSIFY"), False
    return "SHEET_MISSING", len(same) > 1


def judge(row: dict, lookup, complete: bool) -> dict:
    """Trạng thái một giấy: `targets` là chuyến đã ghép (rỗng với NO_TRIP), `match` là "booking" hoặc "container"."""
    cert, container = _amount(row.get("amount_vnd")), container_key(row.get("container"))
    bookings = sorted({b for b in (container_key(x) for x in row.get("bookings") or [] if isinstance(x, str)) if b})
    blocking, info = _warnings(row)
    out = {"row": row, "container": container, "bookings": bookings, "cert": cert, "warnings": blocking,
           "warnings_info": info, "targets": [], "match": None, "same_amount": False}
    if row.get("status") != "ok" or cert is None or blocking:
        return {**out, "status": "CERT_REVIEW"}
    found: list[dict] = []
    status = "NO_BOOKING"
    if bookings and container:
        found = [t for t in lookup(container) if t["kind"] == "trip" and t["booking"] in bookings]
        status = "NOT_FOUND"
    if found:
        out["match"], out["targets"] = "booking", found
        if len(found) > 1:
            return {**out, "status": "AMBIGUOUS"}
        status, out["same_amount"] = _plan(found[0], cert)
        return {**out, "status": status}
    if complete and container:
        candidates = lookup(container)
        if len(candidates) == 1 and candidates[0]["insured"] == cert:
            return {**out, "status": "DONE", "match": "container", "targets": candidates}
    return {**out, "status": status}


def evaluate(rows: list[dict], lookup, complete: bool) -> list[dict]:
    results = [judge(row, lookup, complete) for row in rows]
    # Một chuyến không nhận hai giấy: hai giấy cùng ghép một chuyến theo booking thì cả hai là AMBIGUOUS.
    used = Counter((r["targets"][0]["customer_id"], r["targets"][0]["kind"], r["targets"][0]["id"])
                   for r in results if r["match"] == "booking" and len(r["targets"]) == 1)
    for r in results:
        if r["match"] == "booking" and len(r["targets"]) == 1 and used[
                (r["targets"][0]["customer_id"], r["targets"][0]["kind"], r["targets"][0]["id"])] > 1:
            r["status"] = "AMBIGUOUS"
    return results


def message(result: dict, target: dict | None) -> str:
    status, container, cert = result["status"], result["container"] or "(không có container)", result["cert"]
    head = f"{container} · "
    if status in ("CLASSIFY", "MONTH_LOCKED"):
        month = (target or {}).get("month") or ""
        locked = f" Tháng {month[5:7]}/{month[:4]} đang khóa." if status == "MONTH_LOCKED" else ""
        return head + CLASSIFY_HINT + locked
    if status == "SHEET_MISSING":
        if result["same_amount"]:
            return head + f"giấy bảo hiểm {vnd_text(cert)}; sổ có hai khoản cùng số này, chọn tay khoản nào là Bảo hiểm."
        return head + (f"giấy bảo hiểm {vnd_text(cert)}, Sheet chưa ghi Bảo hiểm. "
                       "Ghi tổng có VAT trên giấy vào cột BẢO HIỂM của tab khách.")
    if status == "AMOUNT_DIFF":
        return head + f"sổ khách ghi Bảo hiểm {vnd_text(target['insured'])}, giấy ghi {vnd_text(cert)}. Xem lại Sheet hoặc giấy."
    if status == "AMBIGUOUS":
        return head + "booking + container khớp nhiều chuyến hoặc nhiều giấy cùng một chuyến. Người xem chọn."
    if status == "NO_BOOKING":
        return head + "giấy không có booking trong tin Zalo, chưa gắn được chuyến. Ghi Bảo hiểm theo giấy vào Sheet nếu cần."
    if status == "NOT_FOUND":
        return head + "chưa có chuyến web nào khớp booking + container (thường chuyến chưa lên Sheet; lượt sau tự xét lại)."
    if status == "CERT_REVIEW":
        reasons = []
        if result["row"].get("status") != "ok":
            reasons.append(f"trạng thái đọc {result['row'].get('status')}")
        if cert is None:
            reasons.append("chưa có số (chưa qua kiểm phép cộng hoặc nhiều container)")
        if result["warnings"]:
            reasons.append("cảnh báo khi đọc: " + "; ".join(result["warnings"]))
        return head + "giấy chưa dùng được số: " + ", ".join(reasons) + ". Người xem giấy."
    return ""


def public(result: dict, target: dict | None) -> dict:
    """Một mục cho giao diện; `target` là chuyến thuộc sổ đang xem (None ở Việc cần làm). Số tiền là chuỗi như bảng PS."""
    row = result["row"]
    web = None if target is None or target["insured"] is None else str(target["insured"])
    return {"cert_no": row.get("cert_no"), "sha256": row["sha256"], "container": result["container"],
            "booking": (target or {}).get("booking") or ", ".join(result["bookings"]),
            "depart_date": row.get("depart_date"), "issue_date": row.get("issue_date"),
            "target_kind": target["kind"] if target else "", "target_id": target["id"] if target else "",
            "month": target["month"] if target else "",
            "cert_vnd": None if result["cert"] is None else str(result["cert"]), "web_vnd": web,
            "status": result["status"], "match": result["match"], "message": message(result, target),
            "warnings": result["warnings"], "warnings_info": result["warnings_info"]}


def project_insurance(snapshot: dict, ledger: dict, fee_types: list[dict], index: ContainerIndex) -> dict:
    """Giấy ghép được vào chuyến của sổ này: `review` cho "Bảo hiểm cần xem", `done` để gắn số giấy và nút Mở giấy."""
    customer = ledger.get("customer_id")
    index.replace(customer, book_entries(ledger, fee_types))
    review, done = [], []
    for result in evaluate(snapshot["rows"], index.lookup, index.complete):
        mine = [t for t in result["targets"] if t["customer_id"] == customer]
        if not mine:
            continue
        item = public(result, mine[0])
        if result["status"] == "DONE":
            done.append(item)
        elif result["status"] in REVIEW:
            review.append(item)
    return {"snapshot_sha256": snapshot["sha256"], "review": review, "done": done, "review_count": len(review)}


def orphan_items(snapshot: dict, index: ContainerIndex) -> dict:
    """Việc cần làm: giấy chưa có chuyến (NO_BOOKING, NOT_FOUND, CERT_REVIEW). Chưa đọc đủ mọi sổ thì chưa tính được."""
    if not index.complete:
        raise ValueError("Insurance container index incomplete")
    items = [public(r, None) for r in evaluate(snapshot["rows"], index.lookup, True) if r["status"] in NO_TRIP]
    return {"snapshot_sha256": snapshot["sha256"], "items": items, "count": len(items)}


def cert_pdf(snapshot: dict, sha256: str, directory: str | Path) -> bytes:
    """PDF của một giấy trong bản chụp hiện tại. FileNotFoundError khi `sha256` lạ, không phải hex hay file trên đĩa băm sai."""
    if not HEX64.fullmatch(sha256) or not any(row["sha256"] == sha256 for row in snapshot["rows"]):
        raise FileNotFoundError(sha256)
    path = Path(directory) / f"{sha256}.pdf"
    try:
        if path.stat().st_size > MAX_PDF_BYTES:
            raise FileNotFoundError(sha256)
        data = path.read_bytes()
    except OSError as exc:
        raise FileNotFoundError(sha256) from exc
    if hashlib.sha256(data).hexdigest() != sha256:
        raise FileNotFoundError(sha256)
    return data
