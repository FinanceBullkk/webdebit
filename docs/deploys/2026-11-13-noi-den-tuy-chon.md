# Triển khai Nơi đến không bắt buộc (13/11/2026)

**ĐÃ CHẠY trên `hao` lúc 09:15 giờ VN.** Theo [`DEPLOY-CLAUDE-01`](../decisions/deploy-claude-01.md) và [`BANG-GIA-04`](../decisions/bang-gia-04.md); người dùng bảo “Merge và deploy” trong chat.

| Mục | Kết quả |
| --- | --- |
| PR / release | #403, merge `222fd77`; release tay từ `0fb8d4f` |
| CI | Mọi check của PR xanh trên head `43d30e4` (gồm PostgreSQL `--migration-test`) |
| Migration | `2026-11-13-v7-noi-den-tuy-chon.sql`, SHA-256 `30633d5473b2f507e83c2941c86be55872047fddbe77be7f99493fc5d2471bee` |
| Ghi tiền | Không; chỉ thay thân `_lookup_price` và `save_price_table` |

## Gate và kết quả

- Bản sao trước: backup toàn phần `webdebit_v7` kèm hash, `pg_restore --list` đọc được 34 bảng, restore vào DB thử riêng. Migration hai lượt, mỗi lượt 1 `COMMIT` (~100 ms); catalog ổn định giữa hai lượt; dấu vân tay (số dư từng khách, tháng, event, số dòng) không đổi; checker 9/9. Rollback bằng `2026-11-10-v7-bang-gia-noi-den.sql` trên bản sao trả catalog, số chuyến có giá bảng và dấu vân tay về đúng bản trước.
- Đợi lượt `v7-reconcile-auto` 09:05–09:12 xong. Cửa sổ dừng ghi 09:15:19–09:15:24: dừng timer và API, không còn kết nối DB khác, chụp dấu vân tay và backup lần nữa (đọc lại được 34 bảng), áp migration với `ON_ERROR_STOP` (1 `COMMIT`, 97 ms). Catalog trùng bản thử; dấu vân tay trước/sau khớp, 242 khách; checker 9/9. Bật lại API và timer, `/healthz` 200.
- Release tay `222fd77` lúc 09:15:31; tiến trình API chạy từ thư mục release mới, file giao diện có chữ “Mọi nơi đến”. `Deploy hao` của `222fd77` dừng ở gate SQL là chủ ý.

## Ảnh hưởng đo được (chỉ đọc, 3 sổ có bảng giá)

| | Trước | Sau |
| --- | --- | --- |
| Dòng giá, trong đó Nơi đến trống | 142 / 142 | 142 / 142 |
| Chuyến tra được giá bảng | 0 / 80 | 46 / 80 |
| Chuyến đang ghi theo bảng, giá trùng bảng | 0 | 24 |
| Chuyến chưa có giá, có gợi ý “bảng …” | 0 | 3 (ở 2 sổ) |
| Chuyến đang theo bảng mà khác bảng / gõ tay khác bảng | 0 / 0 | 0 / 0 |

Còn 31 chuyến có nơi đi ngoài bảng giá và 3 chuyến ngoài ngày có giá, như trước. Không chuyến nào đổi tiền; lần lưu bảng sau cũng không tự đổi giá chuyến nào vì không có chuyến theo bảng khác bảng.

Bằng chứng gốc ngoài Git: `/srv/v7/backup-20261113-noi-den-tuy-chon/` trên `hao` (quyền 700).

## Rollback

Chạy lại `2026-11-10-v7-bang-gia-noi-den.sql` (đã thử trên bản sao): dòng Nơi đến trống thôi là giá chung, không mất dữ liệu, giá đã ghi vào chuyến giữ nguyên. Release cũ chạy được với DB mới.

## Còn mở

Người dùng chưa lưu bảng giá có dòng Nơi đến trống trên giao diện có đăng nhập; 3 chuyến có gợi ý giá chờ người bấm “Điền giá theo bảng”.
