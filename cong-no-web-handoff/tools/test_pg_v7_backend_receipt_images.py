"""CHUNG-TU-01 harness: ảnh chứng từ gắn phiếu thu, chỉ ảnh giả do test tạo."""

from __future__ import annotations

import base64
import hashlib
import json

from pg_v7_harness import (
    ROOT,
    Pg,
    actor_sql,
    call,
    new_book,
    reject_call,
    require,
    version,
)

MIGRATION = ROOT / "cong-no-web-handoff/tools/migrations/2026-10-29-v7-chung-tu.sql"
ROLLBACK = ROOT / "cong-no-web-handoff/tools/migrations/2026-10-29-v7-chung-tu.rollback.sql"
PNG = b"\x89PNG\r\n\x1a\n" + b"FAKE-PNG"
PNG2 = b"\x89PNG\r\n\x1a\n" + b"FAKE-PNG-2"
JPEG = b"\xff\xd8\xff" + b"FAKE-JPEG"
WEBP = b"RIFF\x10\x00\x00\x00WEBP" + b"FAKE"


def hexa(data: bytes) -> str:
    return "\\x" + data.hex()


def money(pg: Pg) -> str:
    return pg.value("SELECT jsonb_build_object('months',(SELECT jsonb_agg(to_jsonb(v) ORDER BY customer_id,debt_month) "
                    "FROM sokhach.v_outstanding_month v),'lines',(SELECT jsonb_agg(to_jsonb(l) ORDER BY id) "
                    "FROM sokhach.receipt_line l))")


def check_receipt_images(pg: Pg) -> None:
    c = new_book(pg, ("2026-01-01", 100))
    other = new_book(pg, ("2026-01-01", 100))
    call(pg, "record_receipt", c, version(pg, c), "img-r1", "2026-01-02", "THU TIỀN", 10)
    call(pg, "record_receipt", c, version(pg, c), "img-r2", "2026-01-03", "THU TIỀN", 5)
    call(pg, "record_receipt", other, version(pg, other), "img-o1", "2026-01-02", "THU TIỀN", 7)
    before = money(pg)

    def attach(customer, key, pid, data=PNG, kind="image/png", ver=None):
        return call(pg, "attach_receipt_image", customer, version(pg, customer) if ver is None else ver,
                    key, pid, kind, hexa(data))

    first = attach(c, "img-a1", "PH-001")
    sha = hashlib.sha256(PNG).hexdigest()
    require(first["image"]["sha256"] == sha and first["duplicates"] == [], "first attach result")
    v = version(pg, c)
    require(attach(c, "img-a1", "PH-001", ver=v - 1) == first and version(pg, c) == v, "retry wrote twice")
    reject_call(pg, "attach_receipt_image", c, v, "img-a1", "PH-001", "image/png", hexa(PNG2), error="IDEMPOTENCY_CONFLICT")
    reject_call(pg, "attach_receipt_image", c, v - 1, "img-stale", "PH-001", "image/png", hexa(PNG2), error="STALE_LEDGER")
    reject_call(pg, "attach_receipt_image", c, v, "img-dup", "PH-001", "image/png", hexa(PNG), error="IMAGE_DUPLICATE")
    reject_call(pg, "attach_receipt_image", c, v, "img-bad", "PH-001", "image/png", hexa(b"%PDF fake"), error="IMAGE_INVALID")
    reject_call(pg, "attach_receipt_image", c, v, "img-mime", "PH-001", "image/jpeg", hexa(PNG2), error="IMAGE_INVALID")
    reject_call(pg, "attach_receipt_image", c, v, "img-none", "PH-404", "image/png", hexa(PNG2), error="RECEIPT_NOT_FOUND")
    reject_call(pg, "attach_receipt_image", other, version(pg, other), "img-cross", "PH-001", "image/png", "\\x" + "00",
                error="IMAGE_INVALID")
    require(version(pg, c) == v, "rejected attach changed version")
    # Cùng ảnh ở phiếu khác (kể cả sổ khác) chỉ cảnh báo.
    second = attach(c, "img-a2", "PH-002")
    require([d["pid"] for d in second["duplicates"]] == ["PH-001"], "same-book duplicate warning")
    cross = attach(other, "img-o-a1", "PH-001")
    require({d["customer_id"] for d in cross["duplicates"]} == {c}, "cross-book duplicate warning")
    found = call(pg, "find_receipt_image", sha)["matches"]
    require(len(found) == 3, "find by sha256")
    reject_call(pg, "find_receipt_image", "XYZ", error="IMAGE_INVALID")
    attach(c, "img-a3", "PH-001", JPEG, "image/jpeg")
    attach(c, "img-a4", "PH-001", WEBP, "image/webp")
    attach(c, "img-a5", "PH-001", PNG2)
    attach(c, "img-a6", "PH-001", PNG + b"6")
    reject_call(pg, "attach_receipt_image", c, version(pg, c), "img-a7", "PH-001", "image/png", hexa(PNG + b"7"),
                error="IMAGE_LIMIT")
    # Đọc lại: danh sách, ảnh, quyền xem từ reader.
    listed = call(pg, "list_receipt_images", c)["images"]
    require([i["pid"] for i in listed] == ["PH-001"] * 5 + ["PH-002"] and listed[0]["actor"] == "harness", "list images")
    image = call(pg, "get_receipt_image", c, first["image"]["id"])
    require(base64.b64decode(image["data_base64"]) == PNG and image["content_type"] == "image/png", "image bytes round trip")
    reject_call(pg, "get_receipt_image", other, first["image"]["id"], error="IMAGE_NOT_FOUND")
    reader = json.loads(pg.value(f"SELECT sokhach.list_receipt_images({c})", user="v7_reader"))
    require(len(reader["images"]) == 6, "reader list")
    # Gỡ: bắt buộc lý do, ghi Lịch sử, không xóa hẳn; tháng khóa không chặn.
    reject_call(pg, "remove_receipt_image", c, version(pg, c), "img-rm-blank", first["image"]["id"], " ",
                error="IMAGE_REMOVE_REASON_REQUIRED")
    reject_call(pg, "remove_receipt_image", other, version(pg, other), "img-rm-cross", first["image"]["id"], "x",
                error="IMAGE_NOT_FOUND")
    removed = call(pg, "remove_receipt_image", c, version(pg, c), "img-rm", first["image"]["id"], " Đính nhầm ")
    require(removed["removed"] is True, "remove result")
    reject_call(pg, "remove_receipt_image", c, version(pg, c), "img-rm-again", first["image"]["id"], "x",
                error="IMAGE_ALREADY_REMOVED")
    require(len(call(pg, "list_receipt_images", c)["images"]) == 5, "removed image still listed")
    require(call(pg, "get_receipt_image", c, first["image"]["id"])["removed"] is True, "removed image not kept")
    attach(c, "img-reattach", "PH-001", PNG + b"8")
    events = [e for e in call(pg, "get_ledger", c)["events"] if e["kind"] in ("receipt_image", "receipt_image_remove")]
    gone = next(e for e in events if e["kind"] == "receipt_image_remove")
    require(gone["after"]["image"]["reason"] == "Đính nhầm" and gone["actor"] == "harness", "remove audit")
    require(len(events) == 8, f"image events {len(events)}")
    require(money(pg) == before, "image commands changed money or allocations")
    # Phiếu hủy: giữ ảnh, chỉ xem.
    call(pg, "void_receipt", c, version(pg, c), "img-void", "PH-002", "Thử hủy")
    reject_call(pg, "attach_receipt_image", c, version(pg, c), "img-on-void", "PH-002", "image/png", hexa(PNG2),
                error="RECEIPT_ALREADY_VOID")
    kept = next(i for i in listed if i["pid"] == "PH-002")
    reject_call(pg, "remove_receipt_image", c, version(pg, c), "img-rm-void", kept["id"], "x", error="RECEIPT_ALREADY_VOID")
    require(call(pg, "get_receipt_image", c, kept["id"])["removed"] is False, "void dropped image")
    # Bất biến: không sửa/xóa trực tiếp; app không đọc bảng; ảnh không đổi tiền.
    pg.rejects(actor_sql(f"DELETE FROM sokhach.receipt_image WHERE id={kept['id']}"), message="RECEIPT_IMAGE_IMMUTABLE")
    pg.rejects(f"UPDATE sokhach.receipt_image SET sha256=repeat('b',64) WHERE id={kept['id']}", message="RECEIPT_IMAGE_IMMUTABLE")
    pg.rejects("SELECT data FROM sokhach.receipt_image", user="v7_app", message="permission denied")
    # Migration chạy lại được và không đổi dữ liệu.
    snapshot = pg.value("SELECT jsonb_agg(to_jsonb(i)-'data' ORDER BY id) FROM sokhach.receipt_image")
    pg.sql(MIGRATION.read_text(encoding="utf-8"))
    pg.sql(MIGRATION.read_text(encoding="utf-8"))
    require(pg.value("SELECT jsonb_agg(to_jsonb(i)-'data' ORDER BY id) FROM sokhach.receipt_image") == snapshot,
            "migration rerun changed images")
    # Hoàn tác từ chối khi đã có ảnh.
    pg.rejects(ROLLBACK.read_text(encoding="utf-8"), message="RECEIPT_IMAGES_PRESENT")
