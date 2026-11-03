# Gán tên khách cho sổ anh em và bỏ dòng trùng sổ cùng khách (3/11/2026)

**ĐÃ CHẠY trên `hao` ngày 3/11/2026 (khoảng 08:18 giờ VN), phần bảng gán tên.** Phần code lên `hao` khi PR này merge (`Deploy hao`).
Người dùng hỏi phương án cho dòng "đã có ở sổ gốc của sổ khác" rồi bảo "ok xử lý giúp".

| Mục | Nội dung |
| --- | --- |
| Căn cứ | [P3b](../../specs/v7-hop-ngoai-le-p3b.md) (chọn sổ theo tên khách + mặt hàng); [UX bước 02](../ux-luong-du-lieu.md) mục 3.3 và 8 |
| Ghi tiền | Không. Không đổi DB, không chạy migration, không đụng Sheet. |
| Bằng chứng | thư mục `backup-20261103-gan-ten` trong `/srv/v7` trên `hao` (bản bảng gán tên trước khi sửa, quyền 700) |

## Đo trước (chỉ đọc, hàm chiếu của bản đang chạy, cả 236 sổ)

28 dòng `OTHER_BOOK_LEGACY`; dòng nào cũng cùng container, **cùng ngày** với dòng sổ gốc ở sổ kia.

| Sổ đang hiện | Sổ đã có chuyến | Dòng | Nguyên nhân |
| --- | --- | ---: | --- |
| sổ sầu riêng của một khách | sổ mít cùng khách | 14 | Tên Sheet nối thẳng tới tên sổ sầu riêng (bí danh của bản chụp), máy không thấy sổ mít |
| sổ bán cước | sổ dừa cùng khách | 5 | Sổ dừa có tên khách khác chữ ("… -HANDLE") |
| sổ thanh long | sổ dừa cùng khách | 1 | Sổ dừa có tên khách thiếu phần chữ Hoa |
| sổ sầu riêng cảng | sổ thanh long cùng khách | 4 | Chọn sổ đúng; Sheet cũ ghi chuyến sầu riêng vào sổ thanh long |
| sổ một khách | sổ một khách **khác** | 4 | Chưa rõ: Sheet booking ghi một khách, sổ gốc tính cho khách kia |

## Đã làm

1. Bảng gán tên `/srv/v7/customer-name-mapping.json`: đổi `display_name` (và `label`) của 3 sổ cho trùng tên khách của sổ anh em,
   lấy đúng chuỗi từ sổ anh em. So với bản sao lưu: 236/236 khách, chỉ 3 mục đổi, chỉ hai trường đó. API đọc file mỗi lần,
   không cần restart. Đo lại: còn 22 dòng.
2. Code (PR này):
   - `_pick_book`: tên Sheet nối thẳng tới một sổ thì nhóm thêm các sổ cùng tên khách của sổ đó, rồi chọn theo mặt hàng.
   - `project_customer`: dòng sổ gốc khớp chỉ nằm ở sổ **cùng khách** thì chuyến đã tính ở đó, không hiện.
     Còn ở sổ khách khác thì vẫn đỏ để người xem.
   - Chạy thử trên `hao` bằng bản code mới đặt ở `/tmp` (chỉ đọc, đã xóa): chỉ đúng 14 dòng mít đổi sổ, không dòng nào khác;
     `OTHER_BOOK_LEGACY` còn 4; 14 dòng mít thành "Sheet khác thông tin trong sổ" (đã khớp chuyến cũ, lệch chữ); "chuyến mới" giữ 67.

## Rollback

- Bảng gán tên: chép lại file trong `backup-20261103-gan-ten` (giữ chủ `v7app`, quyền 600).
- Code: revert PR; app tự deploy lại.

## CÒN MỞ

- 4 dòng giữa hai khách khác nhau (cùng container, cùng ngày, tháng 3/2026): người dùng xem Sheet booking ghi đúng khách chưa.
  Ghi nhầm thì sửa tên khách trên Sheet, dòng tự hết; sổ gốc tính nhầm khách thì là việc điều chỉnh tiền, cần người dùng quyết.
- Bảng gán tên chỉ nằm trên `hao` (có trong gói cấu hình backup), không có trong Git.
