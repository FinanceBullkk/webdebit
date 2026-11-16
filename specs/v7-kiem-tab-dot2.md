# Kiểm tab trước khi ghi, đợt 2: chuẩn hóa chữ rỗng và mã container (K4)

Trạng thái: ĐÃ CODE (Claude, 16/11/2026), chờ merge và triển khai. Đợt 2 của [KIEM-TAB-01](v7-kiem-tab-truoc-khi-ghi.md), mục K4. Không đổi luật tiền, phân bổ, opening.

## Ca thật

- Chuyến 493 có `shipper = ''`: phần đọc coi '' là trống và gửi NULL xuống, `resolve_sheet_conflict` so `'' IS DISTINCT FROM NULL` nên nút "Theo Sheet" luôn báo `STALE_LEDGER`.
- Ô `YMLU5506443-mã chưa up` trên tab (đã tính 50,6 tr) không khớp container `YMLU5506443`: dòng CONT_NGUON cùng container hiện thành "chuyến mới", duyệt vào có nguy cơ tính trùng.

## Đầu ra

1. `web/v7_normalize.py`, chỗ duy nhất quyết:
   - `text_or_none`: cắt khoảng trắng, chuỗi rỗng thành NULL, **chỉ cho trường chữ**; không có hàm nào cho trường tiền (NULL khác 0, "0" vẫn là chữ "0").
   - `container_code`, `split_container`, `container_key`: ô có đúng một mã theo mẫu 4 chữ + 7 số kèm chữ đi cùng thì mã là phần ISO, phần còn lại là ghi chú. Ô có hai mã, hoặc không có mã ISO (kể cả "FAKEU0000001" năm chữ, "YMLU55064431" tám số), giữ nguyên, không đoán. Số khoa học ("4.2E7") đọc như trước.
2. Mọi nơi khớp container dùng chung: `v7_price_queue.container_key`, `v7_sheet_queue._container`, `v7_month_report.container_key`, `v7_trip_source_match.container_key`.
3. Phần đọc Sheet–web (`v7_sheet_queue.project_customer`): `existing_values` gửi NULL cho chữ rỗng hoặc toàn khoảng trắng; chủ hàng dòng sổ gốc không có thì lấy hãng tàu.
4. SQL (`tools/v7_backend_functions.sql` và migration `2026-11-16-v7-chuan-hoa-chu.sql`, cùng thân hàm): `resolve_sheet_conflict` so `nullif(btrim(v_before),'') IS DISTINCT FROM nullif(btrim(target_value),'')`; `edit_trip_info` coi rỗng và NULL cùng là "chưa có" khi kiểm `NO_CHANGE`. Chỉ hai hàm, không đổi bảng, ràng buộc, quyền.
5. Khác biệt có chủ ý với `sokhach._normalize_key`: hàm SQL đó có index lưu kết quả nên không đổi.

## Tiêu chí nghiệm thu

- [x] Trip `shipper = ''`: "Theo Sheet" (giữ web, lấy Sheet, khoảng trắng) ghi được; giá trị web thật sự khác vẫn `STALE_LEDGER`. Case `KIEM-TAB.01` trên harness PostgreSQL.
- [x] Dòng sổ gốc chủ hàng '' hoặc khoảng trắng: so với hãng tàu như phần đọc.
- [x] Sửa ô chữ rỗng thành rỗng: `NO_CHANGE`.
- [x] `YMLU5506443-mã chưa up` khớp `YMLU5506443`: dòng nguồn cùng container không còn là `NEW` (`tests/test_v7_normalize.py`); hai mã khác nhau vẫn là `NEW`.
- [x] Tiền không đổi sau mọi lệnh trên (tổng tháng trước/sau trong case).
- [x] Migration chạy hai lượt không đổi catalog; chạy lại bản KHOA-CHU-01 rồi bản này trả về đúng bản chuẩn.
- [x] `npm run check` xanh; harness `test_pg_v7_backend.py` và `--migration-test` xanh.

## Phạm vi và hoàn tác

- Được sửa: `web/v7_normalize.py` (mới), `web/v7_price_queue.py`, `web/v7_sheet_queue.py`, `web/v7_month_report.py`, `tools/v7_trip_source_match.py`, `tools/v7_backend_functions.sql`, migration mới, harness, test, runbook.
- Hoàn tác: revert PR (code), và chạy lại `2026-11-01-v7-khoa-chu.sql` trên DB (hai hàm về bản trước).
- Triển khai: có SQL nên theo runbook [`DEPLOY-CLAUDE-01`](../docs/decisions/deploy-claude-01.md) (backup, `ON_ERROR_STOP`, `v7_post_deploy_check.sql`, đối soát tổng, nhật ký `docs/deploys/`).
