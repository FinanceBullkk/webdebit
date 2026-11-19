"""CHI-PHI-XE-01: API đội xe đợt 1 (`/api/v7/doixe/*`), gọi các hàm schema `doixe` qua đúng runner psql của sổ khách.

Đọc: màn Đội xe (`GET /api/v7/doixe`), sổ người hoặc sổ xe (`/so`), Lịch sử (`/lich-su`). Ghi: lưu chặng, sửa ô, xóa chặng,
ghi/hủy ứng, ghi/hủy đợt hoàn, khóa tháng. Mỗi lệnh kiểm thân JSON đủ chặt ở đây để DB không nhận chuỗi lạ (ép kiểu lỗi ở psql
thành 503); hàm SQL kiểm lại lần nữa và giữ mọi luật tiền (ngày không sau hôm nay giờ VN, khóa tháng, mã yêu cầu chống ghi
trùng). Đăng nhập và quyền như mọi route V7 (ACCESS-01): `handle` của `v7_ledger_api` giải danh tính trước khi gọi vào đây.

DOI-XE-THU-01 (đợt 2): đọc bảng kê tháng (`/bang-ke`, file Excel `/bang-ke.xlsx`), bảng giá (`/bang-gia`), Lịch sử phần thu
(`/bang-ke/lich-su`); ghi: gửi bảng kê, đối chiếu xong, điều chỉnh dòng, tiền về và hủy, giá cước tay, gắn tuyến, giá tuyến,
tuyến, danh mục phát sinh.

DOI-XE-CHANG-01 (mục Chặng): đọc danh sách việc và chặng của cả đội (`GET /chang`, việc lấy từ bản chụp booking, chặng và
trạng thái từ `doixe.get_dieu_do`), ghi phân xe, đổi, bỏ phân công và nhận thay đổi của booking (bốn `POST /chang/...`).
Hợp đồng đầy đủ: specs/doi-xe-chang-01.md.
"""

from __future__ import annotations

import json
import re
import unicodedata
from datetime import date, datetime, timedelta
from urllib.parse import parse_qs
from zoneinfo import ZoneInfo

import v7_api_sheet
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


def _write(function: str, required: set[str], check, optional: set[str] = frozenset(), pre=None):
    """`pre(body, runner, actor)`: kiểm cần đọc dữ liệu ngoài thân lệnh (ví dụ bản chụp booking), chạy sau `check`, trước khi ghi."""
    def handler(raw: bytes, runner, actor: str) -> tuple[int, dict]:
        body = _body(raw)
        _fields(body, required, optional)
        check(body)
        if pre is not None:
            pre(body, runner, actor)
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


# ---- DOI-XE-CHANG-01: phân công trên mục Chặng (nối với migration 2026-11-19-v7-doi-xe-dieu-do) ----
NHAN_TEXT = ("kho", "noi_lay", "noi_ha", "ten_hang", "tinh")


def _cont_required(value: object) -> None:
    if value is None or (isinstance(value, str) and not value.strip()):
        bad("CONT_THIEU", ERRORS["CONT_THIEU"][1])
    _text(value, 20, required=True)   # giới hạn của chang.container; hàm SQL chặn dài hơn


def _check_phan_xe(body: dict) -> None:
    _cont_required(body["container"])
    _date(body["ngay_dong"])
    _id(body["xe_id"], nullable=True)   # trống thì SQL trả XE_KHONG_RO bằng câu thường
    _id(body.get("tai_xe_id"), nullable=True)
    _date(body.get("ngay"), nullable=True)
    if "loai" in body and body["loai"] not in LOAI:
        bad()
    for name in ("noi_lay", "noi_ha", "kho", "tinh", "ten_hang", "ghi_chu"):
        _text(body.get(name), 200)
    others = body.get("ngay_dong_khac")
    if others is not None:
        if not isinstance(others, list) or len(others) > 20:
            bad()
        for item in others:
            _date(item)


def _check_doi_phan_cong(body: dict) -> None:
    _id(body["chang_id"])
    before = body["truoc"]
    if not isinstance(before, dict) or set(before) != {"xe_id", "tai_xe_id", "ngay"}:
        bad()
    _id(before["xe_id"])
    _id(before["tai_xe_id"], nullable=True)
    _date(before["ngay"])
    _id(body["xe_id"], nullable=True)
    _id(body["tai_xe_id"], nullable=True)
    _date(body["ngay"])


def _check_nhan_booking(body: dict) -> None:
    _id(body["chang_id"])
    kind, rest = body["kieu"], set(body) - {"idempotency_key", "chang_id", "kieu"}
    if kind == "giu_ngoai":
        if rest:
            bad()
    elif kind == "cap_nhat":
        if "ngay_dong" not in rest:
            bad()
        _date(body["ngay_dong"])
        if "container" in rest:
            _cont_required(body["container"])
        for name in NHAN_TEXT:
            if name in rest:
                _text(body[name], 200)
    else:
        bad()


POST_HANDLERS = {
    CHANG_PATH: _write("luu_chang", {"rows"}, _check_rows),
    PREFIX + "/chang/sua": _write("sua_chang", {"chang_id", "cot", "truoc", "gia_tri"}, lambda b: (_id(b["chang_id"]), _cell(b))),
    PREFIX + "/chang/xoa": _write("xoa_chang", {"chang_id"}, lambda b: _id(b["chang_id"])),
    # DOI-XE-CHANG-01
    PREFIX + "/chang/phan-xe": _write("phan_xe", {"container", "ngay_dong", "xe_id"}, _check_phan_xe,
                                      {"ngay", "loai", "tai_xe_id", "noi_lay", "noi_ha", "kho", "tinh", "ten_hang", "ghi_chu", "ngay_dong_khac"},
                                      pre=lambda body, runner, actor: _check_on_booking(body, runner, actor)),  # noqa: PLW0108 (hàm định nghĩa ở dưới)
    PREFIX + "/chang/doi-phan-cong": _write("doi_phan_cong", {"chang_id", "truoc", "xe_id", "tai_xe_id", "ngay"}, _check_doi_phan_cong),
    PREFIX + "/chang/bo-phan-cong": _write("bo_phan_cong", {"chang_id"}, lambda b: _id(b["chang_id"])),
    PREFIX + "/chang/nhan-booking": _write("nhan_booking", {"chang_id", "kieu"}, _check_nhan_booking, {"ngay_dong", "container", *NHAN_TEXT}),
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


# ---- DOI-XE-CHANG-01: đọc danh sách việc và chặng (mục Chặng) ----
PHIEU_PATH = PREFIX + "/chang/phieu"
VN = ZoneInfo("Asia/Ho_Chi_Minh")
MAX_VIEC = 1500        # 1500 việc ≈ 84 KB trong tham số psql, dưới trần 128 KB của một đối số dòng lệnh Linux
MAX_SPAN_DAYS = 93
MAX_CU = 92
CONTAINER = re.compile(r"[A-Z]{4}[0-9]{7}")
MARGIN_DAYS = 10       # luật nối chặng ↔ việc (doixe._cach_viec): ngày đóng lệch ≤ 3 ngày (NGUON-CHUYEN-01); chặng chưa có ngày đóng nối theo
                       # ngày chạy, lệch ≤ 10 ngày. Gửi kèm việc trong 10 ngày quanh khoảng xem để cả hai kiểu nối đều thấy việc của mình
MIN_DAY = "2020-01-01"  # doixe._ngay từ chối ngày trước mốc này (INVALID_DATE cho cả lượt gọi), nên dòng booking cũ hơn bị bỏ ở đây
STALE_AFTER = timedelta(hours=1)
STATES = ("sap_toi", "cho_phan_xe", "da_phan_xe", "da_co_phi", "da_len_bang_ke")
BOOKING_FIELDS = (("kho", "origin"), ("hang", "commodity"), ("cang", "destination"), ("hang_tau", "carrier"), ("so_booking", "booking"),
                  ("khach", "customer_name"), ("seal", "seal"), ("nhiet_do", "nhiet_do"), ("ten_tau", "ten_tau"))
NO_COLUMN = ("NGUON_THIEU_NHA_XE", "Bản chụp booking chưa có cột Nhà xe. Chờ lượt đồng bộ kế tiếp (15 phút) rồi tải lại.")
NOT_ON_BOOKING = ("VIEC_KHONG_CON", "Việc này không còn trên booking của đội xe (số container hoặc ngày đóng đã đổi). Tải lại danh sách.")


def load_booking() -> dict:
    """Bản chụp booking (CONT_NGUON) mà timer webdebit-sheet-sync ghi; test vá hàm này."""
    try:
        return v7_api_sheet.cached_load(v7_api_sheet.load_snapshot, v7_api_sheet.SHEET_SNAPSHOT_PATH)
    except (ValueError, OSError) as exc:
        raise ApiError(503, "SHEET_SNAPSHOT_UNAVAILABLE", "Không đọc được bản chụp booking.") from exc


def _ma(value: object) -> str:
    """Mã nhà xe để so NGUYÊN mã: cắt khoảng trắng hai đầu, không so chuỗi con, không bỏ khoảng trắng giữa."""
    return unicodedata.normalize("NFC", str(value or "")).strip()


def _plain(value: object) -> str:
    return " ".join(unicodedata.normalize("NFC", str(value or "")).split()).casefold()


def _cont(value: object) -> str | None:
    """Số container của một dòng booking, chỉ khi đúng dạng chuẩn sau khi viết hoa và bỏ khoảng trắng: bốn chữ cái rồi bảy chữ số
    (người dùng ĐÃ CHỐT ở DOI-XE-DIEU-DO-01: chưa có số container thì chưa phân xe được). Ô trống hoặc chữ giữ chỗ ("chờ cont", "CHUA CO")
    trả None: việc "sắp tới". Luật này chỉ cho đường đọc việc từ booking; chặng ngoài booking (`POST /chang`) giữ luật container của luu_chang."""
    text = re.sub(r"\s+", "", str(value or "")).upper()
    return text if CONTAINER.fullmatch(text) else None


def _month_end(first: date) -> date:
    return (first.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)


def parse_chang_query(query: str, now: datetime | None = None) -> dict:
    """`thang=YYYY-MM-01` hoặc `tu`+`den` (YYYY-MM-DD, tối đa 93 ngày), cộng `cu` (số ngày lùi để giữ việc cũ còn chờ, 0..92).
    Không có tham số nào thì lấy tháng hiện tại (giờ VN)."""
    q = _query(query, {"thang", "tu", "den", "cu"})
    if ("thang" in q and ("tu" in q or "den" in q)) or (("tu" in q) != ("den" in q)):
        bad()
    if "thang" in q:
        first = date.fromisoformat(_month(q["thang"]))
        last = _month_end(first)
    elif "tu" in q:
        if not valid_date(q["tu"]) or not valid_date(q["den"]):
            bad("INVALID_DATE", "Ngày không hợp lệ.")
        first, last = date.fromisoformat(q["tu"]), date.fromisoformat(q["den"])
        if last < first or (last - first).days >= MAX_SPAN_DAYS:
            bad("INVALID_DATE", "Khoảng ngày không hợp lệ (tối đa 93 ngày).")
    else:
        first = (now or datetime.now(VN)).astimezone(VN).date().replace(day=1)
        last = _month_end(first)
    cu = q.get("cu", "0")
    if not re.fullmatch(r"0|[1-9][0-9]?", cu) or int(cu) > MAX_CU:
        bad()
    return {"tu": first.isoformat(), "den": last.isoformat(), "cu": int(cu), "lui": (first - timedelta(days=int(cu))).isoformat()}


def _booking_viec(snapshot: dict, codes: set[str], window: dict) -> tuple[list[dict], dict]:
    """Việc của đội xe trong bản chụp: dòng có mã nhà xe nằm NGUYÊN trong `codes`, có ngày đóng hợp lệ, bỏ dòng lặp (cùng container và ngày).
    Giữ việc trong [lùi − 3 ngày, đến + 3 ngày] cộng việc ngoài đó nhưng cùng container với một việc giữ lại: hàm nối chặng chọn việc
    gần nhất và chỉ nối chặng với việc trong ±3 ngày, nên nó phải thấy các việc sát mép khoảng xem (nếu không, một chặng có booking dời
    qua mép bị coi là mồ côi). Dòng chưa có số cont là việc "sắp tới", chưa phân xe được."""
    skipped = {"khong_nha_xe": 0, "khong_ngay": 0, "trung": 0}
    mine = []
    for row in snapshot["rows"]:
        if _ma(row.get("nha_xe")) not in codes:
            skipped["khong_nha_xe"] += 1
            continue
        day = str(row.get("event_date") or "")
        if not valid_date(day) or day < MIN_DAY:
            skipped["khong_ngay"] += 1
            continue
        mine.append({"cont": _cont(row.get("container")), "day": day, "row": row,
                     "raw": " ".join(str(row.get("container") or "").split()) or None})
    lo = (date.fromisoformat(window["lui"]) - timedelta(days=MARGIN_DAYS)).isoformat()
    hi = (date.fromisoformat(window["den"]) + timedelta(days=MARGIN_DAYS)).isoformat()
    near = {m["cont"] for m in mine if m["cont"] and lo <= m["day"] <= hi}
    seen, out = set(), []
    for m in mine:
        if not (lo <= m["day"] <= hi or m["cont"] in near):
            continue
        key = (m["cont"], m["day"]) if m["cont"] else (None, m["day"], m["row"].get("source_row"))
        if key in seen:
            skipped["trung"] += 1
            continue
        seen.add(key)
        out.append(m)
    out.sort(key=lambda m: (m["day"], m["cont"] or "", m["row"].get("source_row") or 0))
    return out, skipped


def _chang_out(chang: dict) -> dict:
    """Một chặng của `get_dieu_do` kèm `khoa` (vì sao điều độ không đổi được, theo thứ tự đã gửi → đã hoàn → đã có phí) và `cho_phep`."""
    khoa = "CHANG_DA_GUI" if chang["da_gui"] else "CHANG_DA_HOAN" if chang["da_hoan"] else "CHANG_CO_PHI" if chang["co_phi"] else None
    return {**chang, "khoa": khoa, "cho_phep": {"doi_phan_cong": khoa is None, "bo_phan_cong": khoa is None}}


def _booking_doi(chang: dict, day: str, kho: str | None) -> list[dict]:
    """Chặng đã nhận ngày đóng mà booking nay ghi khác (ngày đóng, kho): trước → sau. Chặng chưa có ngày đóng không so được."""
    out = []
    if chang["ngay_dong"] is None:
        return out
    if chang["ngay_dong"] != day:
        out.append({"chang_id": chang["id"], "truong": "ngay_dong", "truoc": chang["ngay_dong"], "sau": day})
    if kho and chang.get("kho") and _plain(chang["kho"]) != _plain(kho):
        out.append({"chang_id": chang["id"], "truong": "kho", "truoc": chang["kho"], "sau": kho})
    return out


def _state(cont: str | None, hang: dict | None) -> str:
    if cont is None:
        return "sap_toi"
    if hang is None:
        return "cho_phan_xe"
    return "da_len_bang_ke" if hang["da_gui"] else "da_co_phi" if hang["co_phi"] or hang["da_hoan"] else "da_phan_xe"


def _tai_chinh_gon(item: dict | None) -> dict:
    """Bản gọn của phần tài chính một chặng cho danh sách: bỏ từng khoản chi và từng dòng thu (có ở phiếu chặng)."""
    if item is None:
        return {}
    chi = {k: v for k, v in item["chi"].items() if k != "dong"}
    thu = None if item["thu"] is None else {k: v for k, v in item["thu"].items() if k not in ("dong", "loi")}
    return {"thang_khoa": item["thang_khoa"], "bang_ke_thang": item["bang_ke_thang"], "chi": chi, "thu": thu, "lai_gop": item["lai_gop"]}


def read_phieu(query: str, runner, actor: str) -> dict:
    """`GET /api/v7/doixe/chang/phieu?id=N`: một chặng đầy đủ (từng khoản chi kèm người trả, từng dòng thu) cho phiếu chặng."""
    q = _query(query, {"id"})
    if "id" not in q:
        bad()
    got = runner.run("doixe_get_chang_tai_chinh", {"tu": None, "den": None, "ids": [_positive(q["id"])]}, actor,
                     read_only=True)
    if not got["chang"]:
        raise ApiError(409, "CHANG_NOT_FOUND", ERRORS["CHANG_NOT_FOUND"][1])
    return {"hom_nay": got["hom_nay"], "chang": _chang_out(got["chang"][0])}


def read_route(path: str, query: str, runner, actor: str) -> dict | None:
    """Đường đọc mục Chặng không đi một hàm SQL duy nhất (cần bản chụp booking hoặc gộp kết quả); None nếu path không thuộc mục này."""
    if path == CHANG_PATH:
        return read_chang(query, runner, actor)
    if path == PHIEU_PATH:
        return read_phieu(query, runner, actor)
    return None


def _nearest(days: list[str], day: str) -> list[str]:
    """Tối đa 20 ngày đóng khác của cùng container, gần `day` nhất (bằng nhau thì ngày sớm hơn), xếp tăng dần."""
    here = date.fromisoformat(day)
    near = sorted((d for d in days if d != day), key=lambda d: (abs((date.fromisoformat(d) - here).days), d))[:20]
    return sorted(near)


def _booking_snapshot() -> dict:
    snapshot = load_booking()
    if "nha_xe" not in (snapshot.get("columns") or []):
        raise ApiError(503, *NO_COLUMN)
    return snapshot


def _check_on_booking(body: dict, runner, actor: str) -> None:
    """`phan-xe` chỉ cho một việc có thật trên booking của đội xe (cặp container + ngày đóng trong bản chụp hiện tại, mã nhà xe đang dùng);
    gõ sai thì không tạo chặng mồ côi. Chặng ngoài booking (container nhà xe khác kéo, chuyển cảng...) đi đường `POST /chang` (luu_chang)."""
    snapshot = _booking_snapshot()
    codes = {_ma(item["ma"]) for item in runner.run("doixe_get_dieu_do", [], actor, read_only=True)["nha_xe"] if item["dang_dung"]}
    cont = _cont(body["container"])
    if cont is None or not any(_ma(row.get("nha_xe")) in codes and row.get("event_date") == body["ngay_dong"] and _cont(row.get("container")) == cont
                               for row in snapshot["rows"]):
        raise ApiError(409, *NOT_ON_BOOKING)


def read_chang(query: str, runner, actor: str, *, now: datetime | None = None) -> dict:
    """`GET /api/v7/doixe/chang`: việc của đội xe trong khoảng (từ bản chụp booking) cùng chặng đã nối và trạng thái.
    Hai lượt DB chỉ đọc: lượt đầu (mảng việc rỗng) lấy danh mục mã nhà xe để lọc bản chụp; lượt hai lấy chặng của đúng các việc đó."""
    window = parse_chang_query(query, now)
    snapshot = _booking_snapshot()
    base = runner.run("doixe_get_dieu_do", [], actor, read_only=True)
    codes = {_ma(item["ma"]) for item in base["nha_xe"] if item["dang_dung"]}
    mine, skipped = _booking_viec(snapshot, codes, window)
    asked = [{"container": m["cont"], "ngay_dong": m["day"]} for m in mine if m["cont"]]
    if len(asked) > MAX_VIEC:
        bad("QUA_NHIEU_VIEC", "Khoảng ngày có quá nhiều việc. Chọn khoảng ngắn hơn.")
    dd = runner.run("doixe_get_dieu_do", asked, actor, read_only=True) if asked else base
    found = {(v["container"], v["ngay_dong"]): v for v in dd["viec"]}
    days: dict[str, list[str]] = {}
    for item in asked:
        days.setdefault(item["container"], []).append(item["ngay_dong"])
    viec = []
    for m in mine:
        cont, day, row = m["cont"], m["day"], m["row"]
        got = found.get((cont, day)) or {"chang": [], "hang_id": None}
        chang = [_chang_out(c) for c in got["chang"]]
        # Việc ngoài khoảng chỉ hiện khi giữ một chặng có ngày đóng trong khoảng: booking dời ngày đóng qua mép thì chặng phải còn thấy,
        # kèm nhãn "booking đã đổi", không biến thành chặng mồ côi.
        held = any(c["ngay_dong"] is not None and window["tu"] <= c["ngay_dong"] <= window["den"] for c in chang)
        if not (window["lui"] <= day <= window["den"] or held):
            continue
        state = _state(cont, next((c for c in chang if c["id"] == got["hang_id"]), None))
        if day < window["tu"] and state != "cho_phan_xe" and not held:
            continue   # việc cũ chỉ giữ khi còn chờ phân xe
        cu = day < window["tu"] and state == "cho_phan_xe"   # việc cũ còn chờ phân xe
        off_window = held and not window["tu"] <= day <= window["den"]   # hiện vì giữ chặng, không phải vì ngày đóng trong khoảng
        odd = cont is None and m["raw"] is not None
        kho = str(row.get("origin") or "").strip() or None
        viec.append({
            "id": f"{cont}|{day}" if cont else f"#{row.get('source_row')}|{day}",
            "ngay_dong": day, "container": cont, "so_cont_la": odd, "so_cont_goc": m["raw"] if odd else None,
            "trang_thai": state, "cu": cu, "ngoai_khoang": off_window,
            "booking": {name: (str(row.get(src) or "").strip() or None) for name, src in BOOKING_FIELDS},
            "hang_id": got["hang_id"], "chang": chang,
            "booking_doi": [x for c in chang for x in _booking_doi(c, day, kho)] or None,
            "ngay_dong_khac": _nearest(days.get(cont, []), day),
        })
    orphans = []
    for c in dd["mo_coi"]:
        if c["ngay_dong"] is not None and window["lui"] <= c["ngay_dong"] <= window["den"]:
            out = _chang_out(c)
            out["cho_phep"] = {**out["cho_phep"], "chuyen_container": out["khoa"] is None, "giu_ngoai": True}
            orphans.append({**out, "trang_thai": "khong_con_tren_booking"})
    # [PR 2] Thu, chi, lãi gộp: một lượt cho mọi chặng đang hiện, cộng chặng ngày chạy trong khoảng mà không thuộc việc nào.
    shown = [c for v in viec for c in v["chang"]] + orphans
    fin = {c["id"]: c for c in runner.run("doixe_get_chang_tai_chinh", {"tu": window["tu"], "den": window["den"],
                                                                         "ids": [c["id"] for c in shown]}, actor,
                                                                         read_only=True)["chang"]}
    for chang in shown:
        chang.update(_tai_chinh_gon(fin.get(chang["id"])))
    # Chặng mà hàm nối đã nối với MỘT việc nào đó (kể cả việc ẩn vì ngoài khoảng) hoặc đã xếp mồ côi không phải chặng ngoài booking.
    linked = {c["id"] for v in dd["viec"] for c in v["chang"]} | {c["id"] for c in dd["mo_coi"]}
    seen = {c["id"] for c in shown} | linked
    outside = []
    for item in fin.values():
        if item["id"] not in seen and item["ngay_dong"] is None:
            outside.append({**_chang_out(item), "trang_thai": "ngoai_booking"})
            outside[-1].update(_tai_chinh_gon(item))
    counted = [v for v in viec if not v["ngoai_khoang"]]
    created = str((snapshot.get("runner") or {}).get("created_at") or "")
    try:
        stamp = datetime.fromisoformat(created)
        stale = stamp.tzinfo is None or (now or datetime.now(VN)) - stamp > STALE_AFTER
        shown_at = stamp.astimezone(VN).isoformat(timespec="seconds") if stamp.tzinfo is not None else None
    except ValueError:
        stale, shown_at = True, None
    return {
        "hom_nay": dd["hom_nay"], "tu": window["tu"], "den": window["den"], "cu": window["cu"],
        "nguon": {"tao_luc": shown_at, "qua_han": stale, "so_dong": len(snapshot["rows"]), "bo_qua": skipped},
        "viec": viec, "khong_con_tren_booking": orphans, "ngoai_booking": outside,
        # Bộ đếm hàng chờ chỉ đếm việc trong khoảng đang xem (kể cả việc cũ còn chờ, `cu`); việc `ngoai_khoang` hiện trong `viec` nhưng
        # không cộng vào, vì bấm bộ đếm là lọc trong khoảng đang xem.
        "dem": {"viec": len(counted), **{state: sum(1 for v in counted if v["trang_thai"] == state) for state in STATES},
                "booking_doi": sum(1 for v in counted if v["booking_doi"]),
                "chua_co_phi": sum(1 for v in counted for c in v["chang"] if not c["co_phi"]),
                "chua_co_gia": sum(1 for v in counted for c in v["chang"] if "gia" in (c.get("lai_gop") or {}).get("thieu", ())),
                "ngoai_khoang": len(viec) - len(counted),
                "khong_con_tren_booking": len(orphans), "ngoai_booking": len(outside)},
        "xe": dd["xe"], "tai_xe": dd["tai_xe"],
    }


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
