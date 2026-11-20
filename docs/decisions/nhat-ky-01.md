# NHAT-KY-01

[← Sổ quyết định](../decisions.md)

## Quyết định

Web có trang **Nhật ký công việc** (chỉ xem) cho người làm và quản lý thấy việc đã đưa lên hệ thống theo ngày, tuần, tháng, mảng và giờ làm. Spec: [`specs/nhat-ky-01.md`](../../specs/nhat-ky-01.md).

1. **Nguồn là các PR đã merge của repo** (repo public). Không ghi việc ngoài repo. Không đếm PR chỉ ghi nhật ký/trạng thái triển khai (trùng với PR làm tính năng) và PR bot nâng thư viện.
2. **Chạy trên `hao`, không cần máy cá nhân bật**: tiến trình API có một luồng nền hỏi GitHub mỗi 5 phút (không token, dùng ETag), lưu ở `/var/lib/webdebit-sheet-sync/nhat-ky/store.json` (ngoài repo, ngoài DB). Dịch vụ cần thêm quyền ghi đúng thư mục đó (drop-in `ReadWritePaths`).
3. **Tóm tắt lời thường do Claude trên máy chủ viết**, dùng key đã có (`WEBDEBIT_ANTHROPIC_KEY_FILE`), chỉ gửi tên PR; mỗi ngày tối đa một lần mỗi 30 phút. Không có key thì trang vẫn hiện số liệu và tên PR.
4. **Ai cũng thấy** (từ 20/11/2026 chỉ quản lý thấy, theo [`QUYEN-01`](quyen-01.md)) trong số người được vào web: mục nằm dưới khối chín mục của menu trái (từ 20/11/2026 là thẻ Nhật ký trong dải thẻ Quản trị, [`QUYEN-02`](quyen-02.md)) (khung thấp thì nằm trong ☰).
5. Giao diện dạng **bản tin theo ngày**, dùng token và thẻ chung của web công nợ (từ 20/11/2026 thay bố cục trang hồ sơ GitHub ban đầu): khối tuần (số thay đổi, so tuần trước, bảng nhiệt mảng × tuần có mô tả việc lớn và ngày làm gần nhất), Từng ngày (mới nhất trước, câu lời thường hiện sẵn, danh sách thay đổi kỹ thuật thu gọn), cột phải Đang làm tiếp và Giờ làm (% ngoài giờ, biểu đồ theo giờ và theo thứ thay lưới thứ × giờ); bấm mảng, tuần, ô hoặc cột giờ thì cả trang lọc theo. Có chế độ **Sáng / Tối / Theo máy** như GitHub (mặc định Theo máy, nhớ theo trình duyệt), chỉ trang này.

## Ngày / nguồn

20/11/2026, chat. Người dùng cần nơi để mình và sếp xem 24/7, theo thời gian thực, việc đã làm (bản thử trên Artifact ngày 19/11 phụ thuộc máy cá nhân). Chọn đưa lên `hao` ("B"); cùng ngày trả lời ba câu: cho thêm quyền ghi thư mục (drop-in), dùng key Claude trên `hao` để viết tóm tắt, hiện trong menu cho mọi người vào web. Cách đọc GitHub, nhịp 5 phút, cách chia mảng do Claude chọn theo [`CLAUDE-ALL-01`](claude-all-01.md). Chiều 20/11/2026 người dùng thấy bố cục kiểu GitHub chưa hiệu quả; chọn phương án A "bản tin theo ngày" (giữa A và B "bảng theo mảng") và yêu cầu vẽ lại Giờ làm cho dễ đọc hơn. Cùng chiều người dùng hỏi thêm chế độ tối "giống github".

## Hiệu lực và giới hạn

ĐÃ CHỐT. Code theo PR; triển khai tự động khi merge qua `Deploy hao`, riêng thư mục và drop-in quyền ghi làm tay một lần (nhật ký trong `docs/deploys/`). Chia mảng theo từ khóa trong tên PR nên có thể lệch vài PR. Danh sách "Việc lớn" và "Đang làm tiếp" lấy từ bản khởi đầu, chưa tự đổi. GitHub không token cho 60 lượt/giờ: ngày rất nhiều PR có thể chậm vài nhịp mới đủ.
