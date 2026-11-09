"""PS fee lines waiting to be split on one customer ledger (read-only projection).

specs/v7-phu-phi-tu-ps.md. One CONT_MASTER row of the bill workbook points at one web trip or
original-book row of the same customer by the price queue's rule (container, exact date, then
within 3 days; a different booking never matches). A split only reclassifies: READY requires the
PS total to equal the web fee total and at least one unclassified line (Khác, Giảm trừ, Phụ phí
ban đầu). Money never comes from PS; every other case is listed for review or left out.

MAY-PS-01: the Health+KĐ cell is one more fee of the combined type. A `fill` is the one case where lines may grow:
an original-book row whose TOTAL minus unit price already equals the PS total keeps that TOTAL (no money moves).
A PS smaller than the web fee splits its named cells and leaves the rest in Khác (`plan_part`).
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from v7_price_queue import DATE_WINDOW_DAYS, container_key, iso, targets
from v7_sheet_queue import _name, read_snapshot
from v7_sheet_task_keep import kept, ps_identity, ps_web_value

UNCLASSIFIED = ("other", "discount", "initial")
# The fee migration (2026-10-28) stamped these on every "Phụ phí ban đầu" line; nobody typed them, and the event keeps them.
# PHU-PHI-BU-01: công cụ bù ghi GAP_NOTE trên phần thiếu so với TOTAL; máy PS vẫn được tách các khoản này.
GAP_NOTE = "Theo TOTAL Sheet: cột không tiêu đề"
GENERATED_NOTES = {"migration: legacy fee", "migration: initial fee", GAP_NOTE}
FEE_NAMES = {"neo": "Neo", "dien": "Điện", "ghep": "Ghép", "bao_hiem": "Bảo hiểm", "combined": "Health + KĐ"}
FLAG_NAMES = {"health": "Health cert", "kd": "Kiểm định"}
LABELS = {"neo": "Neo", "dien": "Điện", "ghep": "Ghép", "khac": "Khác", "bao_hiem": "Bảo hiểm", "combined": "Health + KĐ"}
REVIEW = ("MONTH_LOCKED", "TOTAL_DIFF", "WEB_NO_FEE", "AMBIGUOUS", "PS_SOURCE_ERROR", "PS_TYPO", "PS_BAD_AMOUNT",
          "TYPED_CONFLICT", "FEE_TYPE_MISSING", "NEED_HEALTH", "NEED_KD")
# Dòng người trả lời được "Không thu, hết báo" (PS-HOI-01): có chuyến đích và là câu hỏi về tiền, không phải việc máy
# tự làm (tháng khóa) hay cấu hình (thiếu loại phí).
KEEPABLE = ("TOTAL_DIFF", "WEB_NO_FEE", "PS_TYPO", "PS_BAD_AMOUNT", "PS_SOURCE_ERROR", "TYPED_CONFLICT", "NEED_HEALTH", "NEED_KD")


def load_ps_snapshot(path: str | Path) -> dict[str, Any]:
    snapshot = read_snapshot(path, "PS snapshot")
    if not isinstance(snapshot.get("customer_aliases"), dict):
        raise ValueError("PS snapshot row count mismatch")
    return snapshot


def vnd_text(value: int) -> str:
    return f"{value:,}".replace(",", ".") + " đ"


def fee_type_ids(fee_types: list[dict]) -> dict[str, int | None]:
    active = [t for t in fee_types if isinstance(t, dict) and t.get("active") and type(t.get("id")) is int]
    by_name = {_name(t.get("name")): t["id"] for t in active if not t.get("system_key")}
    ids: dict[str, int | None] = {field: by_name.get(_name(name)) for field, name in {**FEE_NAMES, **FLAG_NAMES}.items()}
    ids["khac"] = next((t["id"] for t in active if t.get("system_key") == "other"), None)
    ids["unclassified"] = {t["id"] for t in fee_types if isinstance(t, dict) and t.get("system_key") in UNCLASSIFIED}
    return ids


def customer_names(customers: list[dict]) -> dict[str, set]:
    """Ledger names, display names and aliases -> customer ids (several ids: no match)."""
    names: dict[str, set] = {}
    for customer in customers:
        for name in [customer.get("name"), customer.get("display_name"), *(customer.get("aliases") or [])]:
            if isinstance(name, str) and name.strip():
                names.setdefault(_name(name), set()).add(customer["id"])
    return names


def customer_of(owner: str, aliases: dict[str, str], names: dict[str, set]) -> Any:
    """Booking owner -> one customer id, through the review mapping first like the trip sync queue."""
    found = names.get(_name(aliases.get(_name(owner), owner)), set())
    return next(iter(found)) if len(found) == 1 else None


def pool(ledger: dict) -> list[dict]:
    extra = {("trip", t.get("id")): (t.get("fee_lines") or [], container_key(t.get("booking")), t.get("month"))
             for t in ledger.get("trips", [])}
    for row in ledger.get("legacy_rows", []):
        current = row.get("current") or {}
        extra[("legacy", row.get("id"))] = (row.get("fee_lines") or [], container_key(current.get("booking")),
                                            current.get("month") or row.get("month"))
    out = []
    for target in targets(ledger):
        lines, booking, month = extra[(target["kind"], target["id"])]
        counted = None
        if target["kind"] == "legacy" and target["total"] is not None and target["price"] is not None:
            counted = target["total"] - target["price"]
        out.append({**target, "lines": lines, "booking": booking, "month": str(month or "")[:7], "counted_fee": counted})
    return out


def match(row: dict, candidates: list[dict]) -> tuple[list[dict], str]:
    same = [t for t in candidates if t["container"] == row["container"]
            and not (row.get("booking") and t["booking"] and t["booking"] != row["booking"])]
    day = iso(row.get("date"))
    if not day:
        return same, "container_only"
    found = [t for t in same if t["date"] == day]
    if found:
        return found, "exact_date"
    return [t for t in same if t["date"] and abs((t["date"] - day).days) <= DATE_WINDOW_DAYS], "near_date"


def row_fees(row: dict) -> dict[str, Any]:
    return {**row["fees"], "combined": row.get("combined_vnd")}


def plan_part(fees: dict, lines: list[dict], target: dict, ids: dict, info: dict) -> tuple[str, dict]:
    """PS names only part of a larger web fee (MAY-PS-01, 5/11/2026): named cells get their type, the rest stays Khác.

    PS smaller than the web means no money question, because the Sheet total stands. Left for review: a discount line,
    an original-book row whose TOTAL is not its fee lines, a PS with only Khác, typed lines that leave too little to split.
    """
    named = Counter((ids.get(field), value) for field, value in fees.items() if field != "khac")
    web_total, consistent = info["web_total"], target["kind"] != "legacy" or target.get("counted_fee") == info["web_total"]
    if (info["ps_total"] > web_total or not named or not consistent or ids["khac"] is None
            or any(int(line["amount_vnd"]) < 0 for line in lines)):
        return "TOTAL_DIFF", info
    missing = [field for field in fees if field != "khac" and ids.get(field) is None]
    if missing:
        return "FEE_TYPE_MISSING", {**info, "missing": missing}
    kept, free = [], 0
    for line in lines:
        if line["fee_type_id"] in ids["unclassified"]:
            free += int(line["amount_vnd"])
            continue
        kept.append({k: line[k] for k in ("fee_type_id", "amount_vnd", "note")})
        named[(line["fee_type_id"], int(line["amount_vnd"]))] -= 1
    wanted = +named
    if not wanted:
        return "DONE", info
    rest = free - sum(value * count for (_, value), count in wanted.items())
    if rest < 0:
        return "TOTAL_DIFF", info
    after = kept + [{"fee_type_id": type_id, "amount_vnd": str(value), "note": None}
                    for (type_id, value), count in sorted(wanted.items()) for _ in range(count)]
    if rest:
        after.append({"fee_type_id": ids["khac"], "amount_vnd": str(rest), "note": None})
    return ("MONTH_LOCKED" if target["locked"] else "READY"), {**info, "after": after}


def plan(row: dict, target: dict, ids: dict) -> tuple[str, dict]:
    """Status and the line set a split would write; money stays exactly as on the web."""
    fees = {field: int(value) for field, value in row_fees(row).items() if value is not None}
    ps_total = sum(fees.values())
    lines = [{"id": x["id"], "fee_type_id": x["fee_type_id"], "amount_vnd": str(x["amount_vnd"]), "note": x.get("note")}
             for x in target["lines"]]
    web_total = sum(int(x["amount_vnd"]) for x in lines) if lines else None
    fill = web_total != ps_total and target.get("counted_fee") == ps_total
    info = {"ps_total": ps_total, "web_total": web_total, "before": lines, "after": [], "fill": fill}
    if target["pending"]:
        return "PENDING_REVIEW", info
    if not fill and web_total is None:
        return "WEB_NO_FEE", info
    if not fill and web_total != ps_total:
        return plan_part(fees, lines, target, ids, info)
    missing = [field for field in fees if ids.get(field) is None]
    if missing:
        return "FEE_TYPE_MISSING", {**info, "missing": missing}
    wanted = Counter((ids[field], value) for field, value in fees.items())
    kept = []
    for line in lines:
        if line["fee_type_id"] in ids["unclassified"]:
            continue
        key = (line["fee_type_id"], int(line["amount_vnd"]))
        if not wanted[key]:
            return "TYPED_CONFLICT", info
        wanted[key] -= 1
        kept.append({k: line[k] for k in ("fee_type_id", "amount_vnd", "note")})
    after = kept + [{"fee_type_id": type_id, "amount_vnd": str(value), "note": None}
                    for (type_id, value), count in sorted(wanted.items()) for _ in range(count)]
    info["after"] = after
    if not fill and (len(kept) == len(lines) or Counter((x["fee_type_id"], x["amount_vnd"]) for x in after) == Counter(
            (x["fee_type_id"], x["amount_vnd"]) for x in lines)):
        return "DONE", info
    return ("MONTH_LOCKED" if target["locked"] else "READY"), info


def message(status: str, row: dict, info: dict) -> str:
    problem = (row.get("problems") or [{}])[0]
    month = info.get("month") or ""
    return {
        "MONTH_LOCKED": f"Tháng {month[5:7]}/{month[:4]} đang khóa",
        "TOTAL_DIFF": f"Sổ khách tính {vnd_text(info.get('web_total') or 0)} phụ phí, PS ghi {vnd_text(info.get('ps_total') or 0)}",
        "WEB_NO_FEE": f"PS ghi {vnd_text(info.get('ps_total') or 0)} phụ phí, sổ khách chưa thu",
        "AMBIGUOUS": "Cont khớp nhiều chuyến hoặc nhiều dòng PS cùng một chuyến",
        "PS_SOURCE_ERROR": f"Bộ lập bill báo lỗi: {row.get('source_error')}",
        "PS_TYPO": f"{LABELS.get(problem.get('field'), '')} = {problem.get('value')} trên PS, có thể gõ sai",
        "PS_BAD_AMOUNT": f"PS ghi {LABELS.get(problem.get('field'), '')} = {problem.get('value')}, không phải số đồng nguyên nên máy không đọc",
        "TYPED_CONFLICT": "Web đã phân loại khác PS",
        "FEE_TYPE_MISSING": "Danh mục chưa có loại " + ", ".join(LABELS[f] for f in info.get("missing", [])),
        "NEED_HEALTH": "PS đánh dấu Health cert — nhập giá tay",
        "NEED_KD": "PS đánh dấu Kiểm định — nhập giá tay",
    }.get(status, "")


def project_ps(snapshot: dict, ledger: dict, customers: list[dict], fee_types: list[dict], *, include_kept=False) -> dict:
    """Rows of this ledger's customer: READY for the split button, review for "PS cần xem"."""
    customer = ledger.get("customer_id")
    aliases = {_name(k): v for k, v in snapshot.get("customer_aliases", {}).items()}
    names = customer_names([c for c in customers if type(c.get("id")) is int])
    ids = fee_type_ids(fee_types)
    candidates = pool(ledger)
    results = []
    for row in snapshot["rows"]:
        if customer_of(row.get("owner"), aliases, names) != customer:
            continue
        found, basis = match(row, candidates)
        target = found[0] if len(found) == 1 else None
        info: dict = {"ps_total": None, "web_total": None, "before": [], "after": []}
        if row.get("source_error"):
            status = "PS_SOURCE_ERROR"
        elif (row.get("ps_match_count") or 0) > 1 or len(found) > 1:
            status = "AMBIGUOUS"
        elif row.get("problems"):
            status = row["problems"][0]["code"]
            # PHU-PHI-01 (11): a typo cell is no money. When the readable cells already equal the web fee, it blocks nothing.
            if target and all(p.get("code") == "PS_TYPO" for p in row["problems"]):
                exact, exact_info = plan(row, target, ids)
                if exact in ("READY", "MONTH_LOCKED", "DONE") and exact_info["web_total"] == exact_info["ps_total"]:
                    status, info = exact, exact_info
        elif target is None:
            status = "NOT_FOUND"
        elif not any(v is not None for v in row_fees(row).values()):
            status = "PS_EMPTY"
        else:
            status, info = plan(row, target, ids)
        results.append({"row": row, "target": target, "status": status, "basis": basis,
                        "info": {**info, "month": target["month"] if target else ""}})
    used = Counter((r["target"]["kind"], r["target"]["id"]) for r in results if r["target"])
    for result in results:
        if result["target"] and used[(result["target"]["kind"], result["target"]["id"])] > 1:
            result["status"] = "AMBIGUOUS"

    def public(result: dict, status: str) -> dict:
        row, target, info = result["row"], result["target"], result["info"]
        return {"key": row.get("key"), "source_row": row.get("source_row"), "container": row.get("container"),
                "date": row.get("date"), "bill_month": row.get("bill_month"), "ps_source": row.get("ps_source"),
                "target_kind": target["kind"] if target else "", "target_id": target["id"] if target else "",
                "month": info["month"], "status": status, "message": message(status, row, info),
                "ps_total": None if info["ps_total"] is None else str(info["ps_total"]),
                "web_total": None if info["web_total"] is None else str(info["web_total"]),
                "before": info["before"], "after": info["after"], "fill": bool(info.get("fill")),
                "source_fingerprint": ps_identity(row), "keepable": bool(target) and status in KEEPABLE}
    ready = [public(r, r["status"]) for r in results if r["status"] == "READY"]
    review = [public(r, r["status"]) for r in results if r["status"] in REVIEW]
    for result in results:   # Health/KĐ marks only remind; they never create money.
        target = result["target"]
        if target is None or result["status"] in ("AMBIGUOUS", "PS_SOURCE_ERROR"):
            continue
        for field, status in (("health", "NEED_HEALTH"), ("kd", "NEED_KD")):
            covered = {ids.get(field), ids.get("combined")} - {None}
            if result["row"].get(field) and not any(x.get("fee_type_id") in covered for x in target["lines"]):
                review.append(public(result, status))
    # PS-HOI-01: dòng người đã trả lời "Không thu, hết báo" không hiện nữa tới khi ô PS hoặc tiền chuyến trên web đổi.
    if not include_kept:
        review = [r for r in review if not (r["keepable"] and kept(ledger, "ps", r["target_kind"], r["target_id"],
                  r["source_fingerprint"], ps_web_value(ledger, r["target_kind"], r["target_id"])))]
    return {"snapshot_sha256": snapshot["sha256"], "snapshot_created_at": (snapshot.get("runner") or {}).get("created_at"),
            "ready": ready, "review": review, "ready_count": len(ready), "review_count": len(review)}


def auto_ps(ps: dict[str, Any]) -> list[dict[str, Any]]:
    """Rows the machine may split (MAY-PS-01): READY and month-locked ones, unless replacing lines would lose a note."""
    def keeps_notes(row: dict) -> bool:
        notes = Counter(x.get("note") for x in row.get("before") or [] if x.get("note") and x["note"] not in GENERATED_NOTES)
        return not notes - Counter(x.get("note") for x in row.get("after") or [] if x.get("note"))
    rows = list(ps.get("ready") or []) + [row for row in ps.get("review") or [] if row.get("status") == "MONTH_LOCKED"]
    return [row for row in rows if keeps_notes(row)]


def best_columns(ledger: dict, fee_types: list[dict], limit: int = 3) -> list[int] | None:
    """Own columns after a machine split (MAY-PS-01): the book's largest typed fees, moving as few columns as possible.

    Only columns outside that group are replaced, last first. None when nothing changes.
    """
    typed = {t["id"] for t in fee_types if t.get("active") and not t.get("system_key")}
    money: Counter = Counter()
    rows = [t for t in ledger.get("trips") or [] if not t.get("deleted") and t.get("status") != "rejected"]
    rows += [r for r in ledger.get("legacy_rows") or [] if r.get("kind") == "trip" and not (r.get("current") or {}).get("deleted")]
    for row in rows:
        for fee in row.get("fee_lines") or []:
            if fee.get("fee_type_id") in typed:
                money[fee["fee_type_id"]] += abs(int(fee["amount_vnd"]))
    top = sorted(money, key=lambda type_id: (-money[type_id], type_id))[:limit]
    current = [c["fee_type_id"] for c in sorted(ledger.get("fee_columns") or [], key=lambda c: c.get("position") or 0)]
    columns = list(current)
    for type_id in top:
        if type_id in columns:
            continue
        if len(columns) < limit:
            columns.append(type_id)
        else:
            columns[max(i for i, column in enumerate(columns) if column not in top)] = type_id
    return None if columns == current else columns
