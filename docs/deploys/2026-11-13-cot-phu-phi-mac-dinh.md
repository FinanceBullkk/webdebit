# Triển khai bảy cột phụ phí mặc định (13/11/2026)

**ĐÃ CHẠY trên `hao` lúc 12:14 giờ VN.** Theo [`DEPLOY-CLAUDE-01`](../decisions/deploy-claude-01.md) và [`COT-PHU-PHI-01`](../decisions/cot-phu-phi-01.md); người dùng yêu cầu trong chat cùng ngày.

| Mục | Kết quả |
| --- | --- |
| PR / release | #415, merge `5a720f8`; release tay `5a720f8` từ `761fa1a` |
| CI | Mọi check của #415 xanh (15/15, gồm PostgreSQL `--migration-test`) |
| Migration | `2026-11-13-v7-cot-phu-phi-mac-dinh.sql`, SHA-256 `e2231b64ddf0d0b489eb01094c271726e6f7845be9dabe71dce187f15f213286` |
| Ghi tiền | Không; thêm 3 loại phí, cột `fee_type.default_position`, đặt lại cột riêng của mọi sổ, thay thân `set_book_fee_columns` và `create_book_from_sheet` |

## Gate và kết quả

- Trước cửa sổ: không phiên nào khác đang chạy, không kết nối DB khác, không lệnh ghi trong 10 phút; lượt `v7-reconcile-auto` kế tiếp còn 50 phút.
- Bản sao: backup toàn phần `webdebit_v7` kèm hash (`09fd687c…`), `pg_restore --list` đọc được 34 bảng, restore vào DB thử riêng. Migration hai lượt, mỗi lượt 1 `COMMIT` (~200 ms); catalog (hàm, quyền, cột, ràng buộc) và cột riêng ổn định giữa hai lượt; dấu vân tay (số dư từng khách, tháng, event, version sổ, dòng phụ phí, số dòng các bảng khác) không đổi; checker 9/9. Gọi `set_book_fee_columns` với 10 loại trên một sổ (trong giao dịch `ROLLBACK`): nhận đủ 10 cột. Rollback thử (hàm cũ, ràng buộc 1–3, cột riêng cũ) trả cột riêng và dấu vân tay về đúng bản trước.
- DB thật, cửa sổ dừng ghi 12:14:37–12:14:42: dừng timer và API, chụp dấu vân tay, lưu cột riêng cũ thành lệnh khôi phục, backup lần nữa (`cd650b47…`, đọc lại được 34 bảng), áp migration với `ON_ERROR_STOP` (1 `COMMIT`, 294 ms). Catalog và cột riêng trùng bản thử; dấu vân tay trước/sau khớp, 242 khách; checker 9/9. Bật lại API và timer, `/healthz` 200.
- Release tay `5a720f8` lúc 12:15:10; `.release-sha` là `5a720f8`, `/healthz` 200, file giao diện có nút Bật tất cả. Script release cảnh báo không dọn được vài release cũ có file của user khác (đã có từ trước, admin dọn tay).

## Ảnh hưởng đo được

| | Trước | Sau |
| --- | --- | --- |
| Loại phí đang dùng được | 10 | 13 (thêm Lưu bãi, Phí hủy, Sửa bill) |
| Sổ có cột riêng | 14 / 242 (21 cột) | 242 / 242 (1.694 cột) |
| Bộ cột | 228 sổ chỉ cột Khác; 9 sổ Neo; 5 sổ tổ hợp Neo/Điện/Ghép/Health + KĐ | cả 242 sổ: Lưu bãi, Ghép, Điện, Neo, Health + KĐ, Phí hủy, Sửa bill |

Mọi cột cũ đều nằm trong bảy cột nên không sổ nào mất cột; chỉ thứ tự đổi theo chứng từ. Không dòng phụ phí, số dư hay version sổ nào đổi.

Bằng chứng gốc ngoài Git: `/srv/v7/backup-20261113-cot-phu-phi-mac-dinh/` trên `hao` (quyền 700), gồm `restore-cols-live.sql`.

## Rollback

`rollback.sql` trong thư mục bằng chứng (đã thử trên bản sao): trả `set_book_fee_columns` bản giới hạn 3 cột và `create_book_from_sheet` bản trước, ràng buộc vị trí 1–3, rồi chạy `restore-cols-live.sql` và `COMMIT`. Ba loại phí mới và cột `default_position` để lại (release cũ không đọc). Release cũ `761fa1a` chạy được với DB mới nhưng sổ bảy cột ở màn 1280 sẽ bị cắt như trước PR.

## Còn mở

Người dùng chưa tự đi luồng trên bản thật có đăng nhập: mở Cài đặt loại phụ phí, Tắt tất cả / Bật tất cả / Về mặc định, xem sổ bảy cột ở màn 1280.
