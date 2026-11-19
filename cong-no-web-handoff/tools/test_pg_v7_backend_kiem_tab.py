"""KIEM-TAB-01 (16/11/2026), K4: chuỗi rỗng và NULL là cùng một giá trị "chưa có" ở ô chữ mô tả; tiền không bị đụng.

Ca thật: chuyến có shipper '' làm nút "Theo Sheet" luôn báo STALE_LEDGER, vì phần đọc coi '' là trống (gửi NULL) còn SQL so '' với NULL.
Run only through disposable test_pg_v7_backend.py harness."""
import json

from pg_v7_harness import (
    AUDIT_KIEN_TRUC_MIGRATION,
    KHOA_CHU_MIGRATION,
    KIEM_TAB_MIGRATION,
    call,
    fixture_open_month,
    months,
    new_book,
    reject_call,
    require,
    trip_json,
    version,
)
from test_pg_v7_backend_khoa_chu import CATALOG, _legacy

SHA = "e" * 64


def check_kiem_tab(pg) -> str:
    # Migration chỉ thay thân hai hàm: chạy hai lượt trên lược đồ chuẩn không đổi catalog; bản trước (KHOA-CHU-01) rồi chạy lại bản này
    # trả về đúng bản chuẩn.
    fresh = pg.value(CATALOG)
    migration = KIEM_TAB_MIGRATION.read_text(encoding="utf-8")
    audit = AUDIT_KIEN_TRUC_MIGRATION.read_text(encoding="utf-8")  # audit 19/11 thay edit_trip_info sau bản này
    pg.sql(migration)
    pg.sql(migration)
    pg.sql(audit)
    require(pg.value(CATALOG) == fresh, "kiem-tab migration rerun changed function catalog")
    pg.sql(KHOA_CHU_MIGRATION.read_text(encoding="utf-8"))
    require(pg.value(CATALOG) != fresh, "khoa-chu bodies must differ from the canonical ones (otherwise this check proves nothing)")
    pg.sql(migration)
    pg.sql(audit)
    require(pg.value(CATALOG) == fresh, "kiem-tab migration did not restore the canonical bodies")

    c = new_book(pg, ("2026-01-01", 100))
    fixture_open_month(pg, c, "2026-01-01")
    rows = [json.loads(trip_json(container=f"KT-{n}", shipper=value))[0] for n, value in enumerate(("", "", None), 1)]
    trips = call(pg, "paste_trips", c, version(pg, c), "kt-paste", "2026-01-01", json.dumps(rows))["trip_ids"]
    require(pg.value(f"SELECT shipper IS NOT DISTINCT FROM '' FROM sokhach.v_trip_current WHERE id={trips[0]}") == "t",
            "fixture: the trip must carry the empty string, not NULL")
    legacy = _legacy(pg, c, {"container": "KT-L", "date": "2026-01-05", "from": "KHO A", "to": "CANG B", "carrier": "HT",
                             "shipper": "", "unit_price": "100"}, 41)
    before = months(pg, c)

    # 1. Phần đọc của web gửi NULL cho chủ hàng '': giữ web hoặc lấy Sheet đều chạy, không báo "Sổ đã thay đổi".
    call(pg, "resolve_sheet_conflict", c, version(pg, c), "kt-keep", SHA, 7, "trip", trips[0], "shipper", None, "CHU HANG M", "keep_web")
    call(pg, "resolve_sheet_conflict", c, version(pg, c), "kt-use", SHA, 8, "trip", trips[1], "shipper", None, "CHU HANG M", "use_sheet")
    require(pg.value(f"SELECT shipper FROM sokhach.v_trip_current WHERE id={trips[1]}") == "CHU HANG M", "use_sheet did not write the Sheet shipper")
    # Khoảng trắng cũng là "chưa có"; chuyến shipper NULL nhận cả hai cách ghi.
    call(pg, "resolve_sheet_conflict", c, version(pg, c), "kt-blank", SHA, 9, "trip", trips[2], "shipper", "  ", "CHU HANG M", "keep_web")
    # Giá trị web thật sự khác vẫn là STALE_LEDGER: chỉ gộp rỗng với NULL, không nới so sánh.
    reject_call(pg, "resolve_sheet_conflict", c, version(pg, c), "kt-stale", SHA, 7, "trip", trips[0], "shipper", "KHAC", "CHU HANG M",
                "keep_web", error="STALE_LEDGER")

    # 2. Dòng sổ gốc không có chủ hàng thì web lấy hãng tàu, kể cả khi chủ hàng là '' hay toàn khoảng trắng (khớp phần đọc của web).
    call(pg, "resolve_sheet_conflict", c, version(pg, c), "kt-legacy", SHA, 10, "legacy", legacy, "shipper", "HT", "CHU HANG M", "use_sheet")
    reject_call(pg, "resolve_sheet_conflict", c, version(pg, c), "kt-legacy-stale", SHA, 11, "legacy", legacy, "shipper", "HT", "KHAC",
                "keep_web", error="STALE_LEDGER")   # sau khi lấy Sheet, chủ hàng là CHU HANG M, không còn là hãng tàu

    # 3. Sửa ô chữ rỗng thành rỗng không phải thay đổi; sửa thành giá trị thật vẫn ghi.
    reject_call(pg, "edit_trip_info", c, version(pg, c), "kt-nochange", trips[0], "shipper", "   ", error="NO_CHANGE")
    reject_call(pg, "edit_trip_info", c, version(pg, c), "kt-nochange-null", trips[2], "shipper", "", error="NO_CHANGE")
    call(pg, "edit_trip_info", c, version(pg, c), "kt-edit", trips[0], "shipper", "NGUOI GUI")
    require(pg.value(f"SELECT shipper FROM sokhach.v_trip_current WHERE id={trips[0]}") == "NGUOI GUI", "real shipper edit not written")

    # 4. Chữ rỗng không lan sang trường tiền: tiền không đổi sau mọi lệnh ở trên.
    require(months(pg, c) == before, "text normalisation changed month totals")
    return "empty string and NULL are one value for text fields in resolve_sheet_conflict/edit_trip_info; real differences still STALE_LEDGER; money unchanged"
