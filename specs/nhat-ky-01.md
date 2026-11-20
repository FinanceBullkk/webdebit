# NHAT-KY-01: trang Nhật ký công việc

Quyết định: [`docs/decisions/nhat-ky-01.md`](../docs/decisions/nhat-ky-01.md).

## Mục tiêu

Người làm và quản lý mở web công nợ là thấy việc đã đưa lên hệ thống: hôm nay làm gì, có đều không, làm mảng nào, có nhanh lên không, làm lúc nào. Cập nhật trong vòng vài phút sau mỗi lần merge, 24/7, không phụ thuộc máy cá nhân.

## Luồng

1. `v7_ledger_api.main` khởi động `v7_nhat_ky.journal().start()`: luồng nền, mỗi 5 phút:
   - `GET /repos/FinanceBullkk/webdebit/pulls?state=closed&sort=updated&direction=desc&per_page=100` kèm `If-None-Match`; 304 là không có gì mới.
   - PR mới merge (tối đa 20 mỗi nhịp): bỏ nếu tên khớp mẫu không đếm; còn lại lấy `GET /pulls/{n}` để có dòng thêm, bỏ, số file; xếp mảng theo từ khóa; giờ merge đổi sang giờ Việt Nam.
   - Ngày có PR mới mà tóm tắt cũ đã quá 30 phút: gửi tên PR cho Claude (Haiku), nhận `{headline, items: [[mảng, câu]]}`; sai hình dạng thì bỏ.
   - Ghi `store.json` (ghi tạm rồi đổi tên, mode 600). GitHub báo hết lượt thì chờ tới giờ mở lại.
2. Chưa có `store.json` thì nạp `web/nhat-ky-seed.json`: 431 PR và tóm tắt viết tay 20/10–19/11/2026.
3. `GET /api/v7/nhat-ky` (sau xác thực danh tính, không tham số) trả `{available, checked_at, error, from, to, highlights, next, days: {ngày: {headline, items, changes: [[#số, tên, mảng, thêm, bỏ, file, HH:MM]]}}}`.
4. Trang `nhat-ky-cong-viec.html` đọc API lúc mở, mỗi 60 giây khi tab đang mở và khi tab quay lại; có thay đổi mới thì báo "+N thay đổi mới".

## Giao diện

Theo trang hồ sơ GitHub, mọi kiểu nằm dưới `.nk`: cột trái (avatar, số liệu, huy hiệu 18 ngày liền / % ngoài giờ / ngày cuối tuần, Đang làm tiếp); tab Tổng quan (Hôm nay, Việc lớn, lưới đóng góp + chọn tháng, Theo tuần, Giờ làm) và Cây công việc; ngăn kéo chi tiết ngày. Bộ lọc chung mảng/ngày/tuần/ô giờ; mỗi hộp không tự lọc theo chiều của nó.

## Kiểm

- `tests/test_v7_nhat_ky.py`: chia mảng, mẫu không đếm, nhịp đọc với GitHub và Claude giả, ETag, tóm tắt chỉ viết lại sau 30 phút, bỏ câu trả lời sai, không key thì không gọi Claude, nạp bản khởi đầu, hết lượt thì chờ, route và trang được phục vụ.
- `preview/test-nhat-ky-browser.js`: trang với API giả, bỏ PR nhật ký triển khai, lọc chéo, chi tiết ngày, tab cây, lỗi máy chủ rồi đọc lại, không cuộn ngang 1280/390, menu vẫn chín mục.
- Trên `hao` sau triển khai: `GET /api/v7/nhat-ky` có `checked_at` mới, `store.json` được tạo, ngày hôm nay có tóm tắt.
