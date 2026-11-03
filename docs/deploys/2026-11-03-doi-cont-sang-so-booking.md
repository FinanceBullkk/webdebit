# Dời 4 chuyến tháng 3/2026 từ sổ gốc một khách sang sổ khách theo Sheet booking (3/11/2026)

**ĐÃ GHI trên `hao` ngày 3/11/2026 (khoảng 15:46 giờ VN).** Người dùng duyệt trong chat cùng ngày: Sheet booking ghi đúng khách,
sổ gốc nhập nhầm sang khách khác; dời chuyến về đúng sổ, tiền đã trả đi theo chuyến để số nợ hai khách không đổi.
Nối tiếp [nhật ký sổ anh em](2026-11-03-trung-so-anh-em.md) (4 dòng CÒN MỞ ở đó).

| Mục | Nội dung |
| --- | --- |
| Sổ | sổ nguồn (sổ gốc có 4 chuyến) và sổ đích (Sheet booking ghi tên khách này); hai khách khác nhau |
| Chuyến | 4 container, 18–23/3/2026, 181.000.000 đ; tháng 3 của sổ nguồn đã trả hết bằng khoản thu tháng 4 |
| Ghi tiền | Có, bằng các lệnh app có sẵn, người làm `claude` trong Lịch sử; không migration, không loader, không đụng Sheet |
| Bằng chứng | thư mục `backup-20261103-doi-cont` trong `/srv/v7` trên `hao` (dump trước khi ghi kèm sha256, script đã chạy) |

## Các bước (một script, cùng khóa chống ghi trùng cố định)

1. Mở khóa tháng 3 ở hai sổ (`set_month_lock`, có Lịch sử).
2. Sổ nguồn: xóa 4 dòng sổ gốc (`delete_legacy_trip`), rồi dòng điều chỉnh tháng 3 **+181.000.000** ghi rõ tiền đã trả cho 4 chuyến tính cho sổ đích.
3. Sổ đích: dán 4 chuyến kèm đơn giá như sổ gốc, nối đúng dòng Sheet (`paste_trips`). Lớp chặn trùng đưa cả 4 vào chờ kiểm
   (`BASELINE_DATE_WINDOW`, container có trong bản đối chiếu lúc nạp dưới tên sổ nguồn); kết luận "Đúng" từng chuyến kèm lý do.
4. Sổ đích: dòng điều chỉnh tháng 3 **−181.000.000** ghi rõ đã trả trong khoản thu tháng 4 ở sổ nguồn.
5. Khóa lại tháng 3 ở hai sổ.

Không dùng cấn trừ hai sổ: lệnh đó chặn khi vượt phần dư của sổ lấy tiền; sau bước 2 sổ nguồn chỉ dư 43,5 tr vì còn nợ tháng 9.

## Thử trước và kết quả

- Bản sao: dump, restore vào DB thử, chạy script (vào bằng `postgres` rồi `SET ROLE v7_app`, vì pg_hba không mở cho bản sao). Ba lượt
  (hai lượt đầu lộ tháng khóa và chờ kiểm, đã thêm bước 1, 3, 5). Lượt cuối: số nợ hai sổ, tổng mọi sổ không đổi; tháng 3 khóa lại;
  15 event đúng loại. Đã xóa DB thử.
- Trước khi ghi thật: không phiên nào nối DB; số event bằng lúc dump (8.295).
- Sau: sổ nguồn còn nợ 137.500.000, sổ đích 256.500.000 (bằng trước); tổng nợ mọi sổ 64.729.039.261 (bằng trước); event 8.310.
  Không còn chuyến chờ kiểm; 4 dòng đã hết khỏi hàng chờ của sổ đích. `v7_post_deploy_check.sql` OK.

## Rollback

Restore `truoc.dump` vào DB mới; hoặc trên web: hủy hai dòng điều chỉnh, xóa 4 chuyến ở sổ đích, khôi phục 4 dòng sổ gốc ở sổ nguồn
(cần mở khóa tháng 3).
