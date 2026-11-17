# LUOI-AN-TOAN-01

[← Sổ quyết định](../decisions.md)

## Quyết định

Người dùng chọn làm **lưới an toàn**: phép kiểm định kỳ, chỉ đọc, trên sổ thật ở `hao`, báo email qua máy canh khi sổ sai quy
tắc của chính nó. Đây là phép kiểm thay "khớp Sheet" khi bỏ Sheet (mục F5 của [checklist chuyển hẳn](../chuyen-han-checklist.md)).
Đối soát Sheet cho biết web có giống Sheet không; lưới an toàn cho biết sổ web có tự giữ đúng luật không, kể cả khi không còn
Sheet để so.

Bốn phép kiểm, mỗi lượt máy canh (15 phút) ([spec](../../specs/v7-luoi-an-toan.md)):

1. **Phiếu thu chia đủ:** mọi phiếu chưa hủy có dòng chia còn hiệu lực cộng đúng tiền phiếu; phiếu hủy không còn dòng; tiền ứng
   trước ở đúng tháng; dòng chia khớp Lịch sử. Đúng ba luật mà mỗi lệnh ghi đã tự kiểm cho một sổ (`_check_allocations`), nay
   quét mọi sổ.
2. **Số tổng khớp:** con số Tổng quan hiển thị (còn phải thu, khách trả thừa, theo mặt hàng, dải hạn trả, danh sách khách nợ)
   bằng tổng các sổ; không sổ lưu trữ nào còn số dư (Tổng quan bỏ sổ lưu trữ); tổng `get_ledger` của từng sổ bằng tổng sổ đó
   (mỗi lượt 1/8 số sổ, vì mở cả sổ chậm).
3. **Sổ không tự đổi khi không có lệnh:** mọi lệnh ghi tăng `version` của sổ; dữ liệu tiền một sổ khác lượt trước mà `version`
   đứng yên là có thay đổi ngoài đường lệnh (sửa tay DB, migration, loader, phục hồi bản sao).
4. **Lịch sử chỉ thêm:** dòng Lịch sử đã thấy ở lượt trước không bị sửa, xóa hay chen thêm.

Cách làm do Claude đặt (ĐỀ XUẤT trong phạm vi người dùng giao):

- **Chỉ đọc.** Một hàm SQL `sokhach.get_safety_net` chạy trong giao dịch chỉ đọc, một ảnh dữ liệu; hàm từ chối chạy ngoài giao
  dịch đó. Máy canh vào DB như API (role `v7_app`); không thêm role, không đổi pg_hba hay quyền bảng.
- **Mốc giữa hai lượt** (kiểm 3, 4) là một file trong thư mục riêng của máy canh (`/var/lib/v7-watchdog`, systemd
  `StateDirectory`), không phải bảng trong DB: máy canh không ghi DB nó kiểm, và phục hồi DB từ bản cũ không phục hồi luôn mốc.
- **Kiểm 3, 4 báo mãi tới khi có người chấp nhận** (`v7_safety_net.py --accept`), vì đó là dấu vết việc đã xảy ra, kể cả khi
  sau đó có lệnh ghi mới. Kiểm 1, 2 tự hết báo khi sổ đúng lại.
- **Sau migration hay loader đổi dữ liệu sổ không qua lệnh:** chạy `--dry-run` xem đúng phạm vi rồi `--accept` (runbook).
- **Nội dung báo:** mã sổ, tên phần dữ liệu, số đếm, giờ; không tên khách, không số tiền, như các mục khác của máy canh.

## Ngày / nguồn

18/11/2026, chat: người dùng chọn làm lưới an toàn ở phiên riêng, sau khi phiên gốc merge kiểm FIFO ngẫu nhiên (#459) và giải
thích bốn phép kiểm trên. Số đo trên `hao` cùng ngày (chỉ đọc): 242 sổ, mở cả 242 sổ mất 23 giây, Tổng quan 0,9 giây, Lịch sử
khoảng 10 nghìn dòng.

## Hiệu lực và giới hạn

ĐÃ CHỐT làm. Triển khai: hàm SQL theo đợt nâng DB tay ([`DEPLOY-CLAUDE-01`](deploy-claude-01.md)), mã máy canh lên theo release,
kiểm 3, 4 bật khi cài drop-in `StateDirectory` cho máy canh ([runbook](../v7-deploy-runbook.md#lưới-an-toàn-luoi-an-toan-01--nâng-db-và-drop-in-cho-máy-canh)).

Không bắt được:

- Lệnh ghi đúng đường mà ra số sai so với thực tế (giá gõ nhầm, lỗi logic còn giữ luật): cần đối chiếu booking
  ([`KIEM-BOOKING-01`](kiem-booking-01.md)), kiểm FIFO ngẫu nhiên trước deploy, xác nhận debit note của khách.
- Sửa tay một sổ trong cùng 15 phút với một lệnh ghi trên sổ đó; sửa dòng Lịch sử trong 10 phút đầu sau khi ghi.
- Bảng ngoài dữ liệu tiền (bảng giá, ảnh chứng từ, ghi chú đòi nợ, gắn Zalo).
- Người có quyền quản trị sửa cả DB lẫn file mốc. Lưới chống tai nạn, không chống người cố ý có quyền root.
