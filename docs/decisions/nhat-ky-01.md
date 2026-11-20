# NHAT-KY-01

[← Sổ quyết định](../decisions.md)

## Quyết định

Web có trang **Nhật ký công việc** (chỉ xem) cho người làm và quản lý thấy việc đã đưa lên hệ thống theo ngày, tuần, tháng, mảng và giờ làm. Spec: [`specs/nhat-ky-01.md`](../../specs/nhat-ky-01.md).

1. **Nguồn là các PR đã merge của repo** (repo public). Không ghi việc ngoài repo. Không đếm PR chỉ ghi nhật ký/trạng thái triển khai (trùng với PR làm tính năng) và PR bot nâng thư viện.
2. **Chạy trên `hao`, không cần máy cá nhân bật**: tiến trình API có một luồng nền hỏi GitHub mỗi 5 phút (không token, dùng ETag), lưu ở `/var/lib/webdebit-sheet-sync/nhat-ky/store.json` (ngoài repo, ngoài DB). Dịch vụ cần thêm quyền ghi đúng thư mục đó (drop-in `ReadWritePaths`).
3. **Tóm tắt lời thường do Claude trên máy chủ viết**, dùng key đã có (`WEBDEBIT_ANTHROPIC_KEY_FILE`), chỉ gửi tên PR; mỗi ngày tối đa một lần mỗi 30 phút. Không có key thì trang vẫn hiện số liệu và tên PR.
4. **Ai cũng thấy** trong số người được vào web: mục nằm dưới khối chín mục của menu trái (khung thấp thì nằm trong ☰).
5. Giao diện theo trang hồ sơ GitHub (Primer, giao diện sáng): Hôm nay, Việc lớn, lưới đóng góp + chọn tháng, Theo tuần, Giờ làm (kèm % ngoài giờ), tab Cây công việc; bấm mảng, ngày, tuần, ô giờ thì cả trang lọc theo.

## Ngày / nguồn

20/11/2026, chat. Người dùng cần nơi để mình và sếp xem 24/7, theo thời gian thực, việc đã làm (bản thử trên Artifact ngày 19/11 phụ thuộc máy cá nhân). Chọn đưa lên `hao` ("B"); cùng ngày trả lời ba câu: cho thêm quyền ghi thư mục (drop-in), dùng key Claude trên `hao` để viết tóm tắt, hiện trong menu cho mọi người vào web. Cách đọc GitHub, nhịp 5 phút, cách chia mảng do Claude chọn theo [`CLAUDE-ALL-01`](claude-all-01.md).

## Hiệu lực và giới hạn

ĐÃ CHỐT. Code theo PR; triển khai tự động khi merge qua `Deploy hao`, riêng thư mục và drop-in quyền ghi làm tay một lần (nhật ký trong `docs/deploys/`). Chia mảng theo từ khóa trong tên PR nên có thể lệch vài PR. Danh sách "Việc lớn" và "Đang làm tiếp" lấy từ bản khởi đầu, chưa tự đổi. GitHub không token cho 60 lượt/giờ: ngày rất nhiều PR có thể chậm vài nhịp mới đủ.
