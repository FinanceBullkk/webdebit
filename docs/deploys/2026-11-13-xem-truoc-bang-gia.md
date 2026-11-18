# Triển khai Xem lại trước khi lưu bảng giá (13/11/2026)

**ĐÃ CHẠY trên `hao` lúc 10:14 giờ VN.** Theo [`DEPLOY-CLAUDE-01`](../decisions/deploy-claude-01.md) và [`BANG-GIA-05`](../decisions/bang-gia-05.md).

| Mục | Kết quả |
| --- | --- |
| PR / release | #408, merge `b3c8f56`; release tay `b3c8f56` từ `559ab75` (gồm cả #406 `0672da2` merge ngay trước, chỉ giao diện) |
| CI | Mọi check của #408 xanh trên head `f8036ff` (gồm PostgreSQL `--migration-test`, grants) |
| Migration | `2026-11-13-v7-xem-truoc-bang-gia.sql`, SHA-256 `8e0aea7f1c30fa369c7e5f715b553e809fac53020e300d9fb42362e97d160db5` |
| Ghi tiền | Không; chỉ thêm hàm `preview_price_table` và quyền gọi của `sokhach_app` |

## Gate và kết quả

- Trước merge, kiểm phiên khác: một phiên đang chạy chỉ đọc (`BEGIN READ ONLY`, đọc file cấu hình); lượt `v7-reconcile-auto` kế tiếp còn 50 phút.
- Bản sao: backup toàn phần `webdebit_v7` kèm hash (`7a36e451…`), `pg_restore --list` đọc được 34 bảng, restore vào DB thử riêng. Migration hai lượt, mỗi lượt 1 `COMMIT` (~88 ms); catalog ổn định giữa hai lượt và khác bản trước đúng một hàm; dấu vân tay (số dư từng khách, tháng, event, số dòng) không đổi; checker 9/9; quyền: `sokhach_app` gọi được, `sokhach_reader` và `PUBLIC` không.
- Trên bản sao, gọi xem trước cho cả 3 sổ có bảng giá với bảng tăng mọi giá 1.000 đ: dấu vân tay sau khi gọi trùng trước khi gọi (không ghi gì); rồi lưu thật cùng bảng trên bản sao: số chuyến đổi giá, tổng đổi, tháng khóa, chuyến hết giá và bảng sau lưu **trùng xem trước ở cả 3 sổ** (15, 1 và 9 chuyến). Rollback thử bằng `DROP FUNCTION` trả catalog về đúng bản trước.
- DB thật, cửa sổ dừng ghi 10:14:12–10:14:16: dừng timer và API, không còn kết nối DB khác, chụp dấu vân tay và backup lần nữa (`3e4cb1ef…`, đọc lại được 34 bảng), áp migration với `ON_ERROR_STOP` (1 `COMMIT`, 122 ms). Catalog trùng bản thử; dấu vân tay trước/sau khớp, 242 khách; checker 9/9. Bật lại API và timer, `/healthz` 200.
- Release tay `b3c8f56` lúc 10:14:25; tiến trình API chạy từ thư mục release mới, file giao diện có bước "Xem lại và lưu". Sau đó gọi xem trước cho 3 sổ trên DB thật trong giao dịch `ROLLBACK`: chạy đúng, dấu vân tay trước/sau trùng.
- `Tests` của `b3c8f56` trên `main` bị lượt của #409 (`28880e4`, merge ngay sau) thay nên không có lượt `Deploy hao` riêng cho `b3c8f56`. Lượt của `0672da2` (#406) chạy sau release tay nên thấy diff ngược (từ `b3c8f56` về `0672da2`) có file SQL và dừng ở gate, không đổi release — mã của #406 đã nằm trong `b3c8f56`. Các lượt sau đi tiếp từ release `b3c8f56` bình thường: `28880e4` (#409) xanh lúc 10:27, `569fefe` (#410) xanh lúc 10:40 (sau khi chạy lại một job Tests chập chờn trên windows không liên quan Bảng giá). Script release cảnh báo không dọn được vài thư mục release cũ có file của user khác (đã có từ trước, admin dọn tay).

Bằng chứng gốc ngoài Git: `/srv/v7/backup-20261113-xem-truoc-bang-gia/` trên `hao` (quyền 700).

## Rollback

`DROP FUNCTION sokhach.preview_price_table(bigint,bigint,text,jsonb);` (đã thử trên bản sao; không dữ liệu nào phụ thuộc). Release mới khi đó tự lùi: bước xem lại báo "Chưa tính được trước chuyến nào đổi giá" và vẫn cho lưu như trước.

## Còn mở

Người dùng chưa tự đi luồng trên bản thật có đăng nhập: mở Bảng giá dạng ma trận, đổi giá từ ngày, xem lại, lưu.
