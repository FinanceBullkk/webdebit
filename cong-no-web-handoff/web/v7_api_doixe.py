"""CHI-PHI-XE-01: API đội xe đợt 1 (`/api/v7/doixe/*`), gọi các hàm schema `doixe` qua đúng runner psql của sổ khách.

Đọc: màn Đội xe (`GET /api/v7/doixe`), sổ người hoặc sổ xe (`/so`), Lịch sử (`/lich-su`). Ghi: lưu chặng, sửa ô, xóa chặng,
ghi/hủy ứng, ghi/hủy đợt hoàn, khóa tháng. Mỗi lệnh kiểm thân JSON đủ chặt ở đây để DB không nhận chuỗi lạ (ép kiểu lỗi ở psql
thành 503); hàm SQL kiểm lại lần nữa và giữ mọi luật tiền (ngày không sau hôm nay giờ VN, khóa tháng, mã yêu cầu chống ghi
trùng). Đăng nhập và quyền như mọi route V7 (ACCESS-01): `handle` của `v7_ledger_api` giải danh tính trước khi gọi vào đây.
"""

from __future__ import annotations

import json
import re
from urllib.parse import parse_qs

from v7_api_tables import MAX_BIGINT
from v7_api_validate import ApiError, bad, no_duplicates, positive_int, valid_date

PREFIX = "/api/v7/doixe"
CHANG_PATH = PREFIX + "/chang"
# Một lần dán tối đa 200 dòng; mỗi dòng có thể tới ~1 KB chữ (nơi lấy, nơi hạ, ghi chú) nên lệnh lưu chặng được lớn hơn MAX_BODY.
MAX_CHANG_BODY = 256 * 1024
MAX_ROWS = 200
LOAI = ("hang", "chuyen_cang", "tra_rong", "rut_mooc", "tha_mooc", "khac")
PHI = ("nang", "nangha", "cau", "neo", "xi", "dao", "moi", "doi", "seal", "bai", "dieu", "dau", "ps", "may", "vetc")
TEXT_COLS = ("noi_lay", "noi_ha", "kho", "ghi_chu")
ROW_FIELDS = {"ngay", "container", "loai", "xe_id", "tai_xe_id", "tra", "nguoi_tra_id", "noi_lay", "noi_ha", "kho", "tinh",
              "ten_hang", "ghi_chu", "phi"}
MONEY = re.compile(r"0|[1-9][0-9]{0,15}")
MONTH = re.compile(r"[0-9]{4}-[0-9]{2}-01")
KEY_LIMIT = 128


def _body(raw: bytes) -> dict:
    try:
        body = json.loads(raw.decode("utf-8"), object_pairs_hook=no_duplicates,
                          parse_float=lambda _: bad(), parse_constant=lambda _: bad())
    except (UnicodeError, ValueError, TypeError, RecursionError):
        bad()
    if not isinstance(body, dict):
        bad()
    return body


def _fields(body: dict, required: set[str], optional: set[str] = frozenset()) -> None:
    if not required <= set(body) <= required | optional | {"idempotency_key"} or "idempotency_key" not in body:
        bad()
    key = body["idempotency_key"]
    if not isinstance(key, str) or not 1 <= len(key) <= KEY_LIMIT or not key.strip() or any(ord(c) < 32 for c in key):
        bad()


def _text(value: object, limit: int, *, required: bool = False, code: str = "INVALID_REQUEST") -> None:
    if value is None and not required:
        return
    if not isinstance(value, str) or len(value) > limit or any(ord(c) < 32 for c in value) or (required and not value.strip()):
        bad(code, "Cần ghi lý do hủy." if code == "LY_DO_THIEU" else "Dữ liệu gửi không hợp lệ.")


def _money(value: object, *, nullable: bool = True) -> None:
    if value is None and nullable:
        return
    if not isinstance(value, str) or not MONEY.fullmatch(value):
        bad("INVALID_VND", "Số tiền phải là số nguyên VND, không âm.")


def _id(value: object, *, nullable: bool = False) -> None:
    if value is None and nullable:
        return
    if not positive_int(value):
        bad()


def _date(value: object, *, nullable: bool = False) -> None:
    if value is None and nullable:
        return
    if not valid_date(value):
        bad("INVALID_DATE", "Ngày không hợp lệ.")


def _row(row: object) -> None:
    if not isinstance(row, dict) or not {"ngay", "container", "loai", "xe_id", "tra"} <= set(row) <= ROW_FIELDS:
        bad()
    _date(row["ngay"], nullable=True)
    _text(row["container"], 40)
    if row["loai"] not in LOAI or row["tra"] not in ("nguoi", "cong_ty"):
        bad()
    _id(row["xe_id"], nullable=True)
    _id(row.get("tai_xe_id"), nullable=True)
    _id(row.get("nguoi_tra_id"), nullable=True)
    if (row["tra"] == "nguoi") != (row.get("nguoi_tra_id") is not None):
        bad()
    for name in ("noi_lay", "noi_ha", "kho", "tinh", "ten_hang", "ghi_chu"):
        _text(row.get(name), 200)
    fees = row.get("phi", {})
    if not isinstance(fees, dict) or not set(fees) <= set(PHI):
        bad()
    for value in fees.values():
        _money(value)


def _cell(body: dict) -> None:
    column, before, value = body["cot"], body["truoc"], body["gia_tri"]
    if not isinstance(column, str):
        bad()
    if column.startswith("phi:"):
        if column[4:] not in PHI:
            bad()
        _money(before)
        _money(value)
    elif column in ("ngay", "container", "loai", "xe_id", "nguoi_tra", *TEXT_COLS):
        for item in (before, value):
            _text(item, 200)
        if column in ("ngay", "container", "loai", "xe_id", "nguoi_tra") and value is None:
            bad()
        if column == "ngay":
            _date(value)
        if column == "loai" and value not in LOAI:
            bad()
        if column == "xe_id" and not re.fullmatch(r"[1-9][0-9]{0,17}", value):
            bad()
        if column == "nguoi_tra" and value != "cong_ty" and not re.fullmatch(r"[1-9][0-9]{0,17}", value):
            bad()
    else:
        bad("INVALID_FIELD", "Ô không được sửa.")


def _write(function: str, required: set[str], check, optional: set[str] = frozenset()):
    def handler(raw: bytes, runner, actor: str) -> tuple[int, dict]:
        body = _body(raw)
        _fields(body, required, optional)
        check(body)
        return 200, runner.run("doixe_" + function, body, actor)
    return handler


def _check_rows(body: dict) -> None:
    rows = body["rows"]
    if not isinstance(rows, list) or not 1 <= len(rows) <= MAX_ROWS:
        bad()
    for row in rows:
        _row(row)


def _check_ung(body: dict) -> None:
    _id(body["nguoi_id"])
    _date(body["ngay"])
    _money(body["so_tien_vnd"], nullable=False)
    if body["so_tien_vnd"] == "0":
        bad("INVALID_VND", "Số tiền phải lớn hơn 0.")
    _text(body.get("ghi_chu"), 500)


def _check_hoan(body: dict) -> None:
    _id(body["nguoi_id"])
    _date(body["ngay"])
    _money(body["so_tien_vnd"], nullable=False)
    ids = body["dong_ids"]
    if not isinstance(ids, list) or not ids:
        bad("DONG_THIEU", "Chọn ít nhất một dòng.")
    if len(ids) > 2000 or any(not positive_int(item) for item in ids) or len(set(ids)) != len(ids):
        bad()


def _check_huy(name: str):
    def check(body: dict) -> None:
        _id(body[name])
        _text(body["ly_do"], 500, required=True, code="LY_DO_THIEU")
    return check


def _check_khoa(body: dict) -> None:
    if not isinstance(body["thang"], str) or not MONTH.fullmatch(body["thang"]) or not valid_date(body["thang"]):
        bad("INVALID_MONTH", "Tháng không hợp lệ.")
    if type(body["khoa"]) is not bool:
        bad()


POST_HANDLERS = {
    CHANG_PATH: _write("luu_chang", {"rows"}, _check_rows),
    PREFIX + "/chang/sua": _write("sua_chang", {"chang_id", "cot", "truoc", "gia_tri"}, lambda b: (_id(b["chang_id"]), _cell(b))),
    PREFIX + "/chang/xoa": _write("xoa_chang", {"chang_id"}, lambda b: _id(b["chang_id"])),
    PREFIX + "/ung": _write("ghi_ung", {"nguoi_id", "ngay", "so_tien_vnd"}, _check_ung, {"ghi_chu"}),
    PREFIX + "/ung/huy": _write("huy_ung", {"ung_id", "ly_do"}, _check_huy("ung_id")),
    PREFIX + "/hoan": _write("ghi_hoan", {"nguoi_id", "ngay", "so_tien_vnd", "dong_ids"}, _check_hoan),
    PREFIX + "/hoan/huy": _write("huy_hoan", {"dot_id", "ly_do"}, _check_huy("dot_id")),
    PREFIX + "/thang/khoa": _write("khoa_thang", {"thang", "khoa"}, _check_khoa),
}


def _query(parts_query: str, allowed: set[str]) -> dict[str, str]:
    query = parse_qs(parts_query, keep_blank_values=True)
    if not set(query) <= allowed or any(len(values) != 1 for values in query.values()):
        bad()
    return {name: values[0] for name, values in query.items()}


def _month(value: str | None) -> str | None:
    if value is None:
        return None
    if not MONTH.fullmatch(value) or not valid_date(value):
        bad("INVALID_MONTH", "Tháng không hợp lệ.")
    return value


def _positive(value: str) -> int:
    if not re.fullmatch(r"[1-9][0-9]{0,18}", value) or int(value) > MAX_BIGINT:
        bad()
    return int(value)


def parse_get(path: str, parts_query: str) -> tuple[str, dict]:
    """Đường đọc đội xe → (hàm SQL, payload). Đường lạ là 404 như mọi GET V7."""
    if path == PREFIX:
        query = _query(parts_query, {"thang"})
        return "doixe_get_tong", {"thang": _month(query.get("thang"))}
    if path == PREFIX + "/so":
        query = _query(parts_query, {"loai", "id", "thang"})
        if query.get("loai") not in ("nguoi", "xe") or "id" not in query:
            bad()
        return "doixe_get_so", {"loai": query["loai"], "id": _positive(query["id"]), "thang": _month(query.get("thang"))}
    if path == PREFIX + "/lich-su":
        query = _query(parts_query, {"nguoi", "xe"})
        if len(query) > 1:
            bad()
        return "doixe_get_lich_su", {"nguoi": _positive(query["nguoi"]) if "nguoi" in query else None,
                                     "xe": _positive(query["xe"]) if "xe" in query else None}
    raise ApiError(404, "NOT_FOUND", "Không có đường dẫn này.")


def with_names(value, display):
    """Thêm `actor_name` (tên ngắn theo bảng tên PRESENCE-01) cạnh mọi `actor` trong kết quả đọc; không sửa dict vào."""
    if isinstance(value, list):
        return [with_names(item, display) for item in value]
    if isinstance(value, dict):
        out = {key: with_names(item, display) for key, item in value.items()}
        if isinstance(value.get("actor"), str):
            out["actor_name"] = display(value["actor"])
        return out
    return value
