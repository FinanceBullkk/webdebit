"""CHI-PHI-XE-01: API đội xe đợt 1 (`/api/v7/doixe/*`), gọi các hàm schema `doixe` qua đúng runner psql của sổ khách.

Đọc: màn Đội xe (`GET /api/v7/doixe`), sổ người hoặc sổ xe (`/so`), Lịch sử (`/lich-su`). Ghi: lưu chặng, sửa ô, xóa chặng,
ghi/hủy ứng, ghi/hủy đợt hoàn, khóa tháng. Mỗi lệnh kiểm thân JSON đủ chặt ở đây để DB không nhận chuỗi lạ (ép kiểu lỗi ở psql
thành 503); hàm SQL kiểm lại lần nữa và giữ mọi luật tiền (ngày không sau hôm nay giờ VN, khóa tháng, mã yêu cầu chống ghi
trùng). Đăng nhập và quyền như mọi route V7 (ACCESS-01): `handle` của `v7_ledger_api` giải danh tính trước khi gọi vào đây.

DOI-XE-THU-01 (đợt 2): đọc bảng kê tháng (`/bang-ke`, file Excel `/bang-ke.xlsx`), bảng giá (`/bang-gia`), Lịch sử phần thu
(`/bang-ke/lich-su`); ghi: gửi bảng kê, đối chiếu xong, điều chỉnh dòng, tiền về và hủy, giá cước tay, gắn tuyến, giá tuyến,
tuyến, danh mục phát sinh.
"""

from __future__ import annotations

import json
import re
from urllib.parse import parse_qs

from v7_api_tables import ERRORS, MAX_BIGINT
from v7_api_validate import ApiError, bad, no_duplicates, positive_int, valid_date

PREFIX = "/api/v7/doixe"
CHANG_PATH = PREFIX + "/chang"
# Một lần dán tối đa 200 dòng; mỗi dòng có thể tới ~1 KB chữ (nơi lấy, nơi hạ, ghi chú) nên lệnh lưu chặng được lớn hơn MAX_BODY.
MAX_CHANG_BODY = 256 * 1024
MAX_ROWS = 200
LOAI = ("hang", "chuyen_cang", "tra_rong", "rut_mooc", "tha_mooc", "khac")
PHI = ("nang", "nangha", "cau", "neo", "xi", "dao", "moi", "doi", "seal", "bai", "dieu", "dau", "ps", "may", "vetc", "hasom")
# Phiếu chi mới (11/2026): số lượng của chặng, chuỗi số nguyên 1..trần; null là trống. Không phải tiền.
SO_LUONG = {"neo_ngay": 365, "may_gio": 999, "km": 9999}
TEXT_COLS = ("noi_lay", "noi_ha", "kho", "ghi_chu")
ROW_FIELDS = {"ngay", "container", "loai", "xe_id", "tai_xe_id", "tra", "nguoi_tra_id", "noi_lay", "noi_ha", "kho", "tinh",
              "ten_hang", "ghi_chu", "phi", *SO_LUONG}
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
        bad(code, ERRORS[code][1] if code in ERRORS else "Dữ liệu gửi không hợp lệ.")


def _money(value: object, *, nullable: bool = True) -> None:
    if value is None and nullable:
        return
    if not isinstance(value, str) or not MONEY.fullmatch(value):
        bad("INVALID_VND", "Số tiền phải là số nguyên VND, không âm.")


def _count(value: object, limit: int) -> None:
    if value is None:
        return
    if not isinstance(value, str) or not re.fullmatch(r"[1-9][0-9]{0,4}", value) or int(value) > limit:
        bad("INVALID_SO_LUONG", f"Số lượng phải là số nguyên từ 1 tới {limit}.")


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
    for name, limit in SO_LUONG.items():
        _count(row.get(name), limit)


def _cell(body: dict) -> None:
    column, before, value = body["cot"], body["truoc"], body["gia_tri"]
    if not isinstance(column, str):
        bad()
    if column.startswith("phi:"):
        if column[4:] not in PHI:
            bad()
        _money(before)
        _money(value)
    elif column in SO_LUONG:
        _count(before, 99999)
        _count(value, SO_LUONG[column])
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


# ---- DOI-XE-THU-01: đợt 2 (bảng kê HTH, bảng giá, tiền về). Bên nhận cố định ở SQL (một bên), không nhận từ client. ----
SIGNED = re.compile(r"-?[1-9][0-9]{0,15}")
PS_CODE = re.compile(r"[a-z_]{2,16}")
DAU = re.compile(r"[0-9a-f]{32}")
TUYEN_LOAI = ("hang", "chuyen_cang", "tra_rong")
PS_CACH = ("co_dinh", "theo_ngay", "theo_don_vi", "nhap_tay")


def _month_body(value: object) -> None:
    if not isinstance(value, str) or not MONTH.fullmatch(value) or not valid_date(value):
        bad("INVALID_MONTH", "Tháng không hợp lệ.")


def _so_chang(value: object) -> None:
    if type(value) is not int or not 0 <= value <= 999999:
        bad()


def _flag(value: object) -> None:
    if type(value) is not bool:
        bad()


def _check_gui(body: dict) -> None:
    _month_body(body["thang"])
    _money(body["doi_vnd"], nullable=False)
    _so_chang(body["so_chang"])
    # Dấu các dòng đang gom (md5 từ get_bang_ke): máy chủ so lại, khác thì BANG_KE_DOI.
    if not isinstance(body["dau"], str) or not DAU.fullmatch(body["dau"]):
        bad()


def _check_doi_chieu(body: dict) -> None:
    _month_body(body["thang"])
    _money(body["doi_vnd"], nullable=False)


def _check_dieu_chinh(body: dict) -> None:
    _id(body["dong_id"])
    if not isinstance(body["so_tien_vnd"], str) or not SIGNED.fullmatch(body["so_tien_vnd"]):
        bad("INVALID_VND", "Số tiền điều chỉnh phải là số nguyên VND khác 0.")
    _text(body["ly_do"], 500)
    if not isinstance(body["ly_do"], str) or not body["ly_do"].strip():
        bad("LY_DO_DIEU_CHINH", "Cần ghi lý do điều chỉnh.")


def _check_tien_ve(body: dict) -> None:
    _month_body(body["thang"])
    _date(body["ngay"])
    _money(body["so_tien_vnd"], nullable=False)
    if body["so_tien_vnd"] == "0":
        bad("INVALID_VND", "Số tiền phải lớn hơn 0.")
    _text(body.get("ghi_chu"), 500)


def _check_cuoc(body: dict) -> None:
    _id(body["chang_id"])
    _money(body["truoc"])
    _money(body["gia_tri"])


def _check_gan_tuyen(body: dict) -> None:
    _id(body["chang_id"])
    _id(body["tuyen_id"], nullable=True)
    _flag(body["nho"])


def _check_gia(body: dict) -> None:
    _id(body["tuyen_id"])
    _date(body["tu_ngay"])
    _money(body["gia_vnd"], nullable=False)
    if body["gia_vnd"] == "0":
        bad("INVALID_VND", "Giá phải lớn hơn 0.")


def _check_tuyen(body: dict) -> None:
    _id(body["tuyen_id"], nullable=True)
    if body["loai"] not in TUYEN_LOAI:
        bad()
    _text(body["hang"], 60)
    _text(body["di"], 100, required=True, code="TUYEN_THIEU")
    _text(body["den"], 100)
    names = body["ten_goc"]
    if not isinstance(names, list) or len(names) > 50:
        bad()
    for item in names:
        if not isinstance(item, dict) or set(item) != {"hang", "tinh"}:
            bad()
        _text(item["hang"], 120)
        _text(item["tinh"], 120)
    if "dang_dung" in body:
        _flag(body["dang_dung"])
    if body["tuyen_id"] is None:
        if "gia_vnd" not in body or "tu_ngay" not in body:
            bad()
        _check_gia({"tuyen_id": 1, "tu_ngay": body["tu_ngay"], "gia_vnd": body["gia_vnd"]})
    elif "gia_vnd" in body or "tu_ngay" in body:
        bad()


def _check_phat_sinh(body: dict) -> None:
    if not isinstance(body["ma"], str) or not PS_CODE.fullmatch(body["ma"]) or body["cach"] not in PS_CACH or body["cot"] not in ("ps", "ghep"):
        bad()
    _text(body["ten"], 40, required=True)
    _money(body["muc_vnd"])
    _money(body["muc_them_vnd"])
    _flag(body["chi_ho"])
    names = body["ten_goc"]
    if not isinstance(names, list) or not 1 <= len(names) <= 20:
        bad("TEN_GOC_LA", "Cần ít nhất một tên đọc được trong ghi chú.")
    for item in names:
        _text(item, 40, required=True, code="TEN_GOC_LA")


POST_HANDLERS = {
    CHANG_PATH: _write("luu_chang", {"rows"}, _check_rows),
    PREFIX + "/chang/sua": _write("sua_chang", {"chang_id", "cot", "truoc", "gia_tri"}, lambda b: (_id(b["chang_id"]), _cell(b))),
    PREFIX + "/chang/xoa": _write("xoa_chang", {"chang_id"}, lambda b: _id(b["chang_id"])),
    PREFIX + "/ung": _write("ghi_ung", {"nguoi_id", "ngay", "so_tien_vnd"}, _check_ung, {"ghi_chu"}),
    PREFIX + "/ung/huy": _write("huy_ung", {"ung_id", "ly_do"}, _check_huy("ung_id")),
    PREFIX + "/hoan": _write("ghi_hoan", {"nguoi_id", "ngay", "so_tien_vnd", "dong_ids"}, _check_hoan),
    PREFIX + "/hoan/huy": _write("huy_hoan", {"dot_id", "ly_do"}, _check_huy("dot_id")),
    PREFIX + "/thang/khoa": _write("khoa_thang", {"thang", "khoa"}, _check_khoa),
    # DOI-XE-THU-01
    PREFIX + "/bang-ke/gui": _write("gui_bang_ke", {"thang", "doi_vnd", "so_chang", "dau"}, _check_gui),
    PREFIX + "/bang-ke/doi-chieu": _write("doi_chieu_xong", {"thang", "doi_vnd"}, _check_doi_chieu),
    PREFIX + "/bang-ke/dieu-chinh": _write("ghi_dieu_chinh_bk", {"dong_id", "so_tien_vnd", "ly_do"}, _check_dieu_chinh),
    PREFIX + "/bang-ke/tien-ve": _write("ghi_tien_ve", {"thang", "ngay", "so_tien_vnd"}, _check_tien_ve, {"ghi_chu"}),
    PREFIX + "/bang-ke/tien-ve/huy": _write("huy_tien_ve", {"tien_ve_id", "ly_do"}, _check_huy("tien_ve_id")),
    PREFIX + "/thu/cuoc": _write("sua_cuoc", {"chang_id", "truoc", "gia_tri"}, _check_cuoc),
    PREFIX + "/thu/tuyen": _write("gan_tuyen", {"chang_id", "tuyen_id", "nho"}, _check_gan_tuyen),
    PREFIX + "/gia": _write("luu_gia", {"tuyen_id", "tu_ngay", "gia_vnd"}, _check_gia),
    PREFIX + "/tuyen": _write("luu_tuyen", {"tuyen_id", "loai", "hang", "di", "den", "ten_goc"}, _check_tuyen,
                              {"dang_dung", "gia_vnd", "tu_ngay"}),
    PREFIX + "/phat-sinh": _write("luu_phat_sinh", {"ma", "ten", "cach", "muc_vnd", "muc_them_vnd", "chi_ho", "cot", "ten_goc"},
                                  _check_phat_sinh),
}
# Tải Excel bảng kê (DOI-XE-THU-01): GET nhị phân, v7_ledger_api gửi file sau xác thực danh tính.
XLSX_PATH = PREFIX + "/bang-ke.xlsx"


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
    if path in (PREFIX + "/bang-ke", XLSX_PATH):
        query = _query(parts_query, {"thang"})
        return "doixe_get_bang_ke", {"thang": _month(query.get("thang"))}
    if path == PREFIX + "/bang-gia":
        _query(parts_query, set())
        return "doixe_get_bang_gia", {}
    if path == PREFIX + "/bang-ke/lich-su":
        _query(parts_query, set())
        return "doixe_get_lich_su_thu", {}
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
