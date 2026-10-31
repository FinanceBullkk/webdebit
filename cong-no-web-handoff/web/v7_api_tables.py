"""Bảng tra của API V7: trang và file tĩnh, route POST, mã lỗi, SQL cố định, kiểu ép tham số.

Chỉ hằng và bảng, không có logic xử lý yêu cầu. Tách nguyên từ `v7_ledger_api.py` 31/10/2026;
`v7_ledger_api.py` vẫn là điểm vào và re-export các tên này cho test và công cụ.
"""

from __future__ import annotations

import re
from pathlib import Path

MAX_BODY = 64 * 1024
# CHUNG-TU-01: ảnh chứng từ tối đa 2 MiB, gửi base64 trong JSON nên thân lệnh đính ảnh được lớn hơn.
IMAGE_PATH = "/api/v7/receipts/images"
MAX_IMAGE_BYTES = 2 * 1024 * 1024
MAX_IMAGE_BODY = 3 * 1024 * 1024
IMAGE_TYPES = {"image/png": (b"\x89PNG\r\n\x1a\n",), "image/jpeg": (b"\xff\xd8\xff",), "image/webp": (b"RIFF", b"WEBP")}
BASE64 = re.compile(r"[A-Za-z0-9+/]+={0,2}")
MAX_BIGINT = 9223372036854775807
PREVIEW = Path(__file__).resolve().parents[1] / "preview"
# Trang HTML được phục vụ; file .js/.css mỗi trang nạp lấy thẳng từ thẻ <script>/<link> của trang
# (29/10/2026), để thêm file preview chỉ sửa một chỗ là HTML. File không được trang nào nạp
# (ví dụ so-khach-v7-fixture.js) vẫn trả 404.
PAGES = {
    "/": "dashboard-v7.html",
    "/dashboard-v7.html": "dashboard-v7.html",
    "/viec-can-lam.html": "viec-can-lam.html",
    "/cong-no-theo-thang.html": "cong-no-theo-thang.html",
    "/so-khach-v7-live.html": "so-khach-v7-live.html",
    "/doi-no.html": "doi-no.html",
    "/zalo-chat.html": "zalo-chat.html",
    "/sheet-trip-queue.html": "sheet-trip-queue-live.html",
}
PAGE_FILE = re.compile(r'<script src="([a-z0-9-]+\.js)"></script>|<link rel="stylesheet" href="([a-z0-9-]+\.css)">')


def page_assets(pages: dict[str, str]) -> dict[str, tuple[str, str]]:
    assets = {route: (name, "text/html; charset=utf-8") for route, name in pages.items()}
    for name in sorted(set(pages.values())):
        for script, style in PAGE_FILE.findall((PREVIEW / name).read_text(encoding="utf-8")):
            assets[f"/{script or style}"] = (script or style, "text/javascript; charset=utf-8" if script else "text/css; charset=utf-8")
    return assets


ASSETS = page_assets(PAGES)
ROUTES = {
    "/api/v7/offsets": ("record_offset", {"target_customer_id", "target_version", "source_customer_id", "source_version", "idempotency_key", "date", "amount_vnd", "reference"}),
    "/api/v7/offsets/void": ("void_offset", {"customer_id", "expected_version", "other_version", "idempotency_key", "offset_pair_id", "reason"}),
    "/api/v7/offsets/date": ("edit_offset_date", {"customer_id", "expected_version", "other_version", "idempotency_key", "offset_pair_id", "date"}),
    "/api/v7/trips/paste": ("paste_trips", {"debt_month", "trips"}),
    "/api/v7/trips/price": ("edit_trip_price", {"trip_id", "unit_price_vnd", "other_fee_vnd"}),
    "/api/v7/trips/adjust": ("adjust_trip", {"trip_id", "new_amount_vnd", "field", "new_value_vnd", "note"}),
    "/api/v7/months/adjust": ("adjust_month", {"debt_month", "amount_vnd", "note"}),
    "/api/v7/months/adjust/delete": ("delete_month_adjustment", {"adjustment_id"}),
    "/api/v7/receipts": ("record_receipt", {"date", "method", "amount_vnd", "reference"}),
    "/api/v7/receipts/meta": ("edit_receipt_meta", {"pid", "date", "method", "reference"}),
    "/api/v7/receipts/void": ("void_receipt", {"pid", "reason"}),
    IMAGE_PATH: ("attach_receipt_image", {"pid", "content_type", "data_base64"}),
    "/api/v7/receipts/images/remove": ("remove_receipt_image", {"image_id", "reason"}),
    "/api/v7/months/lock": ("set_month_lock", {"month", "locked"}),
    "/api/v7/trips/review": ("review_trip", {"trip_id", "decision", "reason"}),
    "/api/v7/trips/info": ("edit_trip_info", {"trip_id", "field", "value"}),
    "/api/v7/trips/delete": ("delete_trip", {"trip_id"}),
    "/api/v7/legacy/edit": ("edit_legacy_trip", {"legacy_row_id", "field", "value"}),
    "/api/v7/legacy/delete": ("delete_legacy_trip", {"legacy_row_id"}),
    "/api/v7/trips/fees/add": ("add_trip_fees", {"targets", "fee_type_id", "amount_vnd", "note"}),
    "/api/v7/trips/fees/set": ("set_trip_fee_type", {"target", "fee_type_id", "amount_vnd"}),
    "/api/v7/trips/fees/replace": ("replace_trip_fee", {"fee_line_id", "fee_type_id", "amount_vnd", "note"}),
    "/api/v7/trips/fees/void": ("void_trip_fee", {"fee_line_id"}),
    "/api/v7/fee-types": ("add_fee_type", {"name", "kind"}),
    "/api/v7/fee-types/update": ("fee_type_update", {"command", "fee_type_id", "name", "kind", "active"}),
    "/api/v7/books/fee-columns": ("set_book_fee_columns", {"fee_type_ids"}),
    "/api/v7/price-table": ("save_price_table", {"price_table"}),
    "/api/v7/price-table/apply": ("apply_price_table", {"trip_ids"}),
}
COMMON = {"customer_id", "expected_version", "idempotency_key"}
TRIP_FIELDS = {"date", "booking", "container", "carrier", "shipper", "from", "to", "note", "src", "unitPriceVnd", "otherFeeVnd", "fees"}
ERRORS = {
    "INVALID_SHEET_RESOLUTION": (422, "Không thể xử lý ô này."),
    "INVALID_FIELD": (422, "Ô không được sửa."),
    "LEGACY_NO_UNIT_PRICE": (422, "Dòng sổ gốc chưa có đơn giá. Bổ sung đơn giá trước khi sửa phụ phí; số tiền hiện tại được giữ nguyên."),
    "LEGACY_NOT_FOUND": (422, "Không tìm thấy dòng sổ gốc."),
    "ADJUSTMENT_NOT_FOUND": (422, "Không tìm thấy dòng điều chỉnh cả tháng, có thể đã xóa. Tải lại sổ."),
    "LEGACY_NOT_TRIP": (422, "Dòng sổ gốc này là khoản thu, không sửa ở đây."),
    "STALE_LEDGER": (409, "Sổ đã thay đổi. Tải lại rồi thử tiếp."),
    "MONTH_LOCKED": (409, "Tháng đang khóa."),
    "IDEMPOTENCY_CONFLICT": (409, "Mã yêu cầu đã dùng cho nội dung khác."),
    "NO_BASELINE": (409, "Khách chưa có số dư đầu hiệu lực."),
    "RECEIPT_ALREADY_VOID": (409, "Phiếu đã hủy."),
    "NO_CHANGE": (409, "Nội dung không thay đổi."),
    "CUSTOMER_NOT_FOUND": (422, "Không tìm thấy khách."),
    "INVALID_REMINDER": (422, "Dữ liệu nhắc nợ không hợp lệ."),
    "TRIP_NOT_FOUND": (422, "Không tìm thấy chuyến."),
    "FEE_LINE_NOT_FOUND": (409, "Không tìm thấy khoản phụ phí. Tải lại sổ."),
    "TRIP_HAS_NO_PRICE": (422, "Chuyến chưa có giá."),
    "TRIP_PENDING_REVIEW": (409, "Chuyến chưa được tính vào sổ (CHỜ KIỂM hoặc đã loại)."),
    "VERSION_CONFLICT": (409, "Sổ đã thay đổi. Tải lại rồi thử tiếp."),
    "FEE_AMOUNT_INVALID": (422, "Số phụ phí phải là số nguyên VND khác 0 và không tràn."),
    "FEE_SIGN_INVALID": (422, "Dấu phụ phí không phù hợp với loại phí."),
    "FEE_TYPE_INACTIVE": (422, "Loại phụ phí không tồn tại hoặc đã ngừng dùng."),
    "FEE_TYPE_SYSTEM": (422, "Không được chọn loại phụ phí hệ thống."),
    "FEE_TYPE_DUPLICATE": (409, "Tên loại phụ phí đã tồn tại."),
    "FEE_COLUMNS_MAX": (422, "Sổ chỉ được chọn tối đa 3 cột phụ phí."),
    "FEE_LINES_TYPED": (409, "Chuyến có phụ phí đã phân loại. Sửa trong khung chi tiết."),
    "FEE_LINES_CHANGED": (409, "Phụ phí chuyến này vừa đổi. Tải lại rồi tách."),
    "FEE_TOTAL_CHANGED": (409, "Tách sẽ đổi tổng phụ phí nên không ghi. Tải lại rồi xem lại."),
    "TRIP_NOT_PENDING": (409, "Chuyến không còn CHỜ KIỂM."),
    "SHEET_CROSS_CUSTOMER_MATCH": (409, "Chuyến đã có ở khách khác. Tải lại để kiểm tra."),
    "REVIEW_REASON_REQUIRED": (422, "Cần ghi lý do kết luận chuyến CHỜ KIỂM."),
    "RECEIPT_NOT_FOUND": (422, "Không tìm thấy phiếu."),
    "MONTH_NOT_FOUND": (422, "Không tìm thấy tháng."),
    "NO_MONTH_FOR_RECEIPT": (422, "Chưa có tháng để ghi phiếu."),
    "VOID_REASON_REQUIRED": (422, "Cần ghi lý do hủy phiếu."),
    "FUTURE_RECEIPT_DATE": (422, "Ngày trả không được sau hôm nay."),
    "OFFSET_SAME_BOOK": (422, "Không thể cấn trừ cùng sổ."),
    "OFFSET_EXCEEDS_CREDIT": (422, "Số tiền vượt số dư được cấn trừ."),
    "OFFSET_SOURCE_ARCHIVED": (409, "Sổ nguồn đã lưu trữ."),
    "OFFSET_NOT_FOUND": (422, "Không tìm thấy cặp cấn trừ."),
    "OFFSET_PAIR_REQUIRED": (409, "Cần thao tác cả cặp cấn trừ."),
    "OFFSET_ALREADY_VOID": (409, "Cặp cấn trừ đã hủy."),
    "FUTURE_DATE": (422, "Ngày không được sau hôm nay."),
    "INVALID_DATE": (422, "Ngày không hợp lệ."),
    "INVALID_YEAR": (422, "Năm không hợp lệ."),
    "INVALID_MONTH": (422, "Tháng không hợp lệ."),
    "IMAGE_INVALID": (422, "File không phải ảnh PNG, JPG hoặc WebP."),
    "IMAGE_TOO_LARGE": (422, "Ảnh quá lớn (trên 2 MB). Cắt bớt rồi dán lại."),
    "IMAGE_LIMIT": (422, "Mỗi phiếu tối đa 5 ảnh."),
    "IMAGE_DUPLICATE": (409, "Ảnh này đã có trong phiếu."),
    "IMAGE_NOT_FOUND": (422, "Không tìm thấy ảnh."),
    "IMAGE_ALREADY_REMOVED": (409, "Ảnh đã được gỡ."),
    "IMAGE_REMOVE_REASON_REQUIRED": (422, "Cần ghi lý do gỡ ảnh."),
    "INVALID_PRICE_TABLE": (422, "Bảng giá không hợp lệ."),
    "PRICE_PERIOD_OVERLAP": (422, "Hai đợt giá trùng ngày ở cùng kho và cùng loại giá."),
    "PRICE_INVALID_PERIOD": (422, "Ngày hiệu lực không hợp lệ (ngày đến phải từ ngày bắt đầu trở đi)."),
    "PRICE_INVALID_AMOUNT": (422, "Giá phải là số nguyên VND không âm."),
    "PRICE_UNKNOWN_LOCATION": (422, "Kho chưa có trong danh sách kho của bảng giá."),
    "PRICE_DUPLICATE_ALIAS": (422, "Tên kho hoặc tên khác bị trùng."),
    "PRICE_DUPLICATE_SHIPPER": (422, "Shipper của TT bị nhập trùng."),
    "PRICE_DUPLICATE_RATE": (422, "Một kho có hai giá cùng loại trong cùng đợt."),
    "PRICE_NOT_FOUND": (409, "Có chuyến không tra được giá theo bảng. Tải lại để xem lý do."),
    "PRICE_TYPED_PRICE": (409, "Có chuyến đã gõ đơn giá tay; bảng giá không ghi đè. Tải lại rồi chọn lại."),
}
for _code in ("INVALID_VND", "INVALID_ADJUSTMENT", "INVALID_COMMAND", "INVALID_METHOD",
              "INVALID_MONTH", "INVALID_MONTH_LOCK", "INVALID_RECEIPT", "INVALID_TRIP",
              "INVALID_TRIP_DATE", "INVALID_TRIP_INPUT", "INVALID_TRIPS", "INVALID_REVIEW"):
    ERRORS[_code] = (422, "Dữ liệu nhập không hợp lệ.")


# Fixed SQL; psql :'payload' and :'actor' quote variable values as SQL literals.
SQL = {
    "list_offset_sources": "SELECT sokhach.list_offset_sources((:'payload'::jsonb->>'target_customer_id')::bigint);",
    "get_ledger": "SELECT sokhach.get_ledger((:'payload'::jsonb->>'customer_id')::bigint);",
    "list_customers": "SELECT sokhach.list_customers();",
    "get_fee_types": "SELECT sokhach.get_fee_types();",
    "get_price_table": "SELECT sokhach.get_price_table((:'payload'::jsonb->>'customer_id')::bigint);",
    "get_price_status": "SELECT sokhach.get_price_status((:'payload'::jsonb->>'customer_id')::bigint);",
    "get_dashboard": "SELECT sokhach.get_dashboard();",
    "get_dashboard_debt": "SELECT sokhach.get_dashboard_debt();",
    "get_receivables_matrix": "SELECT sokhach.get_receivables_matrix((:'payload'::jsonb->>'year')::int);",
    "get_receivables_detail": "SELECT sokhach.get_receivables_detail((:'payload'::jsonb->>'customer_id')::bigint,(:'payload'::jsonb->>'month')::date);",
    "list_sheet_trip_refs": "SELECT sokhach.list_sheet_trip_refs();",
    "resolve_sheet_conflict": "WITH j AS (SELECT :'payload'::jsonb AS p) SELECT sokhach.resolve_sheet_conflict((p->>'customer_id')::bigint,(p->>'expected_version')::bigint,p->>'idempotency_key',p->>'snapshot_sha256',(p->>'source_row')::bigint,p->>'target_kind',(p->>'target_id')::bigint,p->>'field',p->>'target_value',p->>'sheet_value',p->>'decision') FROM j;",
}
ARGUMENTS = {
    "record_offset": ("target_customer_id", "target_version", "source_customer_id", "source_version", "idempotency_key", "date", "amount_vnd", "reference"),
    "void_offset": ("customer_id", "expected_version", "other_version", "idempotency_key", "offset_pair_id", "reason"),
    "edit_offset_date": ("customer_id", "expected_version", "other_version", "idempotency_key", "offset_pair_id", "date"),
    "paste_trips": ("debt_month", "trips"),
    "edit_trip_price": ("trip_id", "unit_price_vnd", "other_fee_vnd"),
    "adjust_trip": ("trip_id", "new_amount_vnd", "note", "field", "new_value_vnd"),
    "adjust_month": ("debt_month", "amount_vnd", "note"),
    "delete_month_adjustment": ("adjustment_id",),
    "record_receipt": ("date", "method", "amount_vnd", "reference"),
    "edit_receipt_meta": ("pid", "date", "method", "reference"),
    "void_receipt": ("pid", "reason"),
    "remove_receipt_image": ("image_id", "reason"),
    "set_month_lock": ("month", "locked"),
    "review_trip": ("trip_id", "decision", "reason"),
    "edit_trip_info": ("trip_id", "field", "value"),
    "delete_trip": ("trip_id",),
    "edit_legacy_trip": ("legacy_row_id", "field", "value"),
    "delete_legacy_trip": ("legacy_row_id",),
    "add_trip_fees": ("targets", "fee_type_id", "amount_vnd", "note"),
    "set_trip_fee_type": ("target", "fee_type_id", "amount_vnd"),
    "replace_trip_fee": ("fee_line_id", "fee_type_id", "amount_vnd", "note"),
    "void_trip_fee": ("fee_line_id",),
    # Không có đường POST riêng: chỉ /api/v7/ps/fees gọi, với kế hoạch server tự tính từ bảng PS.
    "rewrite_trip_fees": ("target", "expected_line_ids", "lines", "source"),
    "set_book_fee_columns": ("fee_type_ids",),
    "add_fee_type": ("idempotency_key", "name", "kind"),
    "rename_fee_type": ("idempotency_key", "fee_type_id", "name"),
    "set_fee_type_kind": ("idempotency_key", "fee_type_id", "kind"),
    "set_fee_type_active": ("idempotency_key", "fee_type_id", "active"),
    "save_price_table": ("price_table",),
    "apply_price_table": ("trip_ids",),
}
CAST = {"debt_month": "date", "month": "date", "date": "date", "trip_id": "bigint",
        "legacy_row_id": "bigint", "adjustment_id": "bigint",
        "target_customer_id": "bigint", "target_version": "bigint", "source_customer_id": "bigint", "source_version": "bigint",
        "customer_id": "bigint", "expected_version": "bigint", "other_version": "bigint", "offset_pair_id": "bigint",
        "unit_price_vnd": "bigint", "other_fee_vnd": "bigint", "new_amount_vnd": "bigint",
        "amount_vnd": "bigint", "new_value_vnd": "bigint", "trips": "jsonb", "locked": "boolean",
        "targets": "jsonb", "target": "jsonb", "fee_type_id": "bigint", "fee_line_id": "bigint", "fee_type_ids": "jsonb", "active": "boolean",
        "image_id": "bigint", "price_table": "jsonb", "trip_ids": "jsonb",
        "expected_line_ids": "jsonb", "lines": "jsonb", "source": "jsonb"}
for _name, _fields in ARGUMENTS.items():
    _args = ["(j->>'customer_id')::bigint", "(j->>'expected_version')::bigint", "j->>'idempotency_key'"]
    if _name in ("record_offset", "void_offset", "edit_offset_date", "add_fee_type", "rename_fee_type", "set_fee_type_kind", "set_fee_type_active"):
        _args = []
    _args += [f"(j{'->' if CAST.get(field) == 'jsonb' else '->>'}'{field}')::{CAST[field]}" if field in CAST
              else f"j->>'{field}'" for field in _fields]
    SQL[_name] = f"WITH b AS (SELECT :'payload'::jsonb AS j) SELECT sokhach.{_name}({', '.join(_args)}) FROM b;"
# Ảnh vượt giới hạn một tham số dòng lệnh (-v payload) nên đi qua stdin: _run_psql thay chỗ đánh dấu
# bằng chữ base64 đã kiểm (chỉ A-Z a-z 0-9 + / =), không có dấu nháy để thoát chuỗi SQL.
IMAGE_MARK = "__IMAGE_BASE64__"
SQL["attach_receipt_image"] = ("WITH b AS (SELECT :'payload'::jsonb AS j) SELECT sokhach.attach_receipt_image("
                               "(j->>'customer_id')::bigint, (j->>'expected_version')::bigint, j->>'idempotency_key', "
                               f"j->>'pid', j->>'content_type', decode('{IMAGE_MARK}', 'base64')) FROM b;")
SQL["list_receipt_images"] = "SELECT sokhach.list_receipt_images((:'payload'::jsonb->>'customer_id')::bigint);"
SQL["get_receipt_image"] = ("SELECT sokhach.get_receipt_image((:'payload'::jsonb->>'customer_id')::bigint,"
                            "(:'payload'::jsonb->>'image_id')::bigint);")
SQL["find_receipt_image"] = "SELECT sokhach.find_receipt_image(:'payload'::jsonb->>'sha256');"
# NHAC-NO-01: nhắc nợ là ghi chú ngoài đường tiền, không dùng COMMON (version/idempotency); POST đặc biệt.
SQL["record_reminder"] = "WITH b AS (SELECT :'payload'::jsonb AS j) SELECT sokhach.record_reminder((j->>'customer_id')::bigint, j->>'source') FROM b;"
SQL["get_reminders"] = "SELECT sokhach.get_reminders();"
# /healthz: chỉ chứng minh đường psql của app tới DB còn chạy (audit DevOps 31/10, #6); không đọc sổ.
SQL["healthz"] = "SELECT 1;"
