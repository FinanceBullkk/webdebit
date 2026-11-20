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

Bản tin theo ngày (chọn A, 20/11/2026), dùng `cong-no-theme.css` và `.card` như các trang Quản trị; luật riêng nằm dưới `.nk`. Thứ tự đọc trong khung 1280×560:

1. **Khối tuần** (luôn ở đầu): tuần mới nhất hoặc tuần đang chọn, số thay đổi và số ngày làm, tuần trước, mảng làm nhiều nhất; **bảng nhiệt mảng × tuần** (8 tuần gần nhất, màn hẹp 5 tuần): một sắc xanh theo số thay đổi, số in trong ô, chấm màu và mô tả việc lớn dưới tên mảng, cột "Gần nhất". Bấm tên mảng, tuần hoặc ô để lọc.
2. **Từng ngày**: mới nhất trước, 7 ngày một lượt ("Xem thêm"), mỗi ngày tiêu đề tóm tắt, số thay đổi và giờ đầu–cuối, câu lời thường gom theo mảng; danh sách thay đổi kỹ thuật thu gọn (mở sẵn khi lọc giờ hoặc khi ngày chưa có tóm tắt).
3. **Cột phải**: Đang làm tiếp; **Giờ làm**: % ngoài giờ hành chính, thanh chia bốn nhóm (trong giờ, sáng sớm trước 8h, buổi tối từ 17h30, thứ Bảy/Chủ nhật) có số, biểu đồ cột theo giờ trong ngày (chồng theo nhóm, nền nhạt 8h–17h30, bấm cột để lọc giờ) và theo thứ trong tuần.

Bộ lọc chung mảng/tuần/giờ, chip bỏ từng lọc, Esc xóa hết; mỗi khối không tự lọc theo chiều của nó. Màu sáu mảng là sáu ô đầu bảng màu phân loại đã kiểm bằng công cụ kiểm bảng màu (phân biệt được cho người mù màu), tên mảng luôn in cạnh chấm màu. Màn dưới 1012px một cột: tuần → đang làm tiếp → từng ngày → giờ làm.

**Sáng / Tối / Theo máy** (20/11/2026): ba nút ở đầu trang, mặc định Theo máy (`prefers-color-scheme`, đổi theo khi máy đổi), lựa chọn lưu `localStorage` `nk-theme`. `nhat-ky-theme.js` nạp trong `<head>` đặt `data-nk-theme` trên `<html>` trước khi vẽ để không nháy trắng (CSP không cho script inline). Màu tối theo GitHub dark (nền `#0d1117`, thẻ `#151b23`); đổi token của `cong-no-theme.css` và màu cứng của thanh đầu trang, dải thẻ Quản trị, menu trái chỉ trên trang này. Màu mảng dùng cột tối của cùng bảng màu (đã kiểm trên nền thẻ); bảng nhiệt và giờ làm đảo chiều (ít/trong giờ tối gần nền, nhiều/ngoài giờ sáng), chữ trong ô đạt từ 5:1, cột giờ đạt từ 3:1 với nền.

## Kiểm

- `tests/test_v7_nhat_ky.py`: chia mảng, mẫu không đếm, nhịp đọc với GitHub và Claude giả, ETag, tóm tắt chỉ viết lại sau 30 phút, bỏ câu trả lời sai, không key thì không gọi Claude, nạp bản khởi đầu, hết lượt thì chờ, route và trang được phục vụ.
- `preview/test-nhat-ky-browser.js`: trang với API giả, bỏ PR nhật ký triển khai, khối tuần và bảng mảng × tuần, từng ngày lời thường, lọc mảng và giờ, Esc xóa lọc, % ngoài giờ, lỗi máy chủ rồi đọc lại, không cuộn ngang 1280/390, thẻ Nhật ký trong dải Quản trị; Theo máy đổi theo máy, Tối nhớ sau khi tải lại, Sáng trả nền sáng.
- Trên `hao` sau triển khai: `GET /api/v7/nhat-ky` có `checked_at` mới, `store.json` được tạo, ngày hôm nay có tóm tắt.
