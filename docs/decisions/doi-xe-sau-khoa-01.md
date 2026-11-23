# DOI-XE-SAU-KHOA-01

[← Sổ quyết định](../decisions.md)

## Quyết định

Ứng, đợt hoàn và việc hủy chúng **vẫn ghi khi tháng của khoản đã khóa, gắn cờ "sau khóa"**, giống chặng thêm vào tháng khóa ([`CHI-PHI-XE-01`](chi-phi-xe-01.md), [spec](../../specs/chi-phi-xe-01.md) mục Khóa tháng). Cụ thể:

1. `ghi_ung`, `ghi_hoan`: ngày của khoản rơi vào tháng đã khóa thì vẫn ghi, khoản mang `sau_khoa = true`. Số dư và thẻ tiền tháng tính như mọi khoản khác.
2. `huy_ung`, `huy_hoan`: khoản có ngày ở tháng đã khóa vẫn hủy được, phần hủy mang `huy_sau_khoa = true`. Hủy vẫn bắt buộc lý do như cũ.
3. **Không chặn, không đòi thêm lý do** vì tháng khóa, đồng bộ với [`V7-SO`](v7-so.md) (tháng khóa chỉ sửa bằng dòng điều chỉnh, không cần lý do).
4. Cờ theo ngày của khoản, không theo dòng phí đợt hoàn trả cho. Cờ lấy trạng thái khóa lúc ghi; khóa hoặc mở tháng về sau không đổi cờ đã ghi.
5. Màn hiện nhãn "sau khóa" trên dòng ứng/đợt hoàn, trong hộp xem/hủy và trong Lịch sử. Hộp ghi ứng, hộp hoàn và hộp hủy báo trước khi ngày ở tháng đã khóa. Câu báo sau khi lưu nói rõ "1 khoản vào tháng đã khóa".
6. Khoản ghi trước khi có quyết định này giữ cờ false: không biết lúc ghi tháng đã khóa hay chưa, không đoán.

## Ngày / nguồn

24/11/2026. Audit Đội xe 23/11/2026, mục DX-05: ứng, hoàn và hủy bỏ qua khóa tháng, không ai biết khoản vào tháng đã chốt. Claude hỏi người dùng: chặn (`THANG_KHOA`) hay cho ghi nhưng gắn cờ. Người dùng nhờ Claude chốt (qua phiên điều phối "Kiểm toàn bộ website"). Claude chọn gắn cờ, vì:

- Chặng đã làm đúng cách này từ 18/11/2026. Hai luật khác nhau trong cùng một sổ người dễ gây nhầm.
- Chặn thì người nhập phải mở khóa tháng, ghi, rồi khóa lại. Việc đó vẫn để lại khoản trong tháng cũ mà không có dấu nào, tệ hơn cờ.
- V7-SO đã chốt: tháng khóa không chặn ghi tiền, chỉ đổi cách ghi và để lại dấu vết.

## Hiệu lực và giới hạn

ĐÃ CHỐT 24/11/2026. Migration `2026-11-24-v7-doi-xe-sau-khoa.sql`: thêm bốn cột cờ ở `doixe.ung` và `doixe.dot_hoan`, thay bốn lệnh ghi và `get_so`. Harness: `test_pg_doixe_sau_khoa.py`. ĐÃ TRIỂN KHAI trên `hao` 24/11/2026 (#627): [nhật ký](../deploys/2026-11-24-doi-xe-sau-khoa.md).

Không đổi: công thức số dư, cách hủy, quyền. Cờ chỉ để nhận ra; không có báo cáo riêng cho khoản sau khóa.
