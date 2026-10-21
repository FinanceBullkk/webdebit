# Nguồn và phiên bản bản tóm tắt

Bản v1, trích ngày 15/10/2026. Các nguồn là hồ sơ nội bộ giữ ngoài repository, không được upload cùng tài liệu này. Tên file và SHA-256 cho phép người có quyền đối chiếu; hash không thay quyền truy cập hoặc chứng cứ duyệt chính sách. Bản tóm tắt được kiểm chéo với nguồn, không tạo quyết định mới.

| ID | Hồ sơ gốc | SHA-256 bytes gốc |
| --- | --- | --- |
| S17 | `17-independent-ledger-2026-10-13.md` | `39658d2bc8b895a1f5f1b7798a08b716537b0dce0c1a746b774ff950d6e9e55c` |
| S22 | `22-so-cong-no-handoff-review-2026-10-14.md` | `d535d4fc463ead1a83a010def14c577d983546ce0f08062788f35c3eea067aba` |
| S23 | `23-monthly-ledger-preview-2026-10-14.md` | `0b147d183801571455e4a4748e7b4dd99ba679239f0e096b52a4911e6054b119` |
| S15 | `README.md` | `144ab5267adcbdf4d985a7f69bc40a7d1082538b52c6d2881e3bca7edc93f906` |
| S15R | `response.md` | `9e36f8a507f3969b6c6823fef5216d25d905b9b5c2af3ffd98b51b6bcc592393` |

Các nguồn có báo cáo triển khai/probe lịch sử; không xác minh DB/service hôm nay. Quyết định trực tiếp trong chat 15/10/2026 chọn GitHub làm nơi phát triển chung là nguồn W01. Các thay đổi tài liệu sau này cập nhật tại repo; không sửa ngược nguồn cũ để làm bằng chứng mới.

## Release v2 (20/10/2026)

Đối chiếu chỉ đọc ngày 21/10/2026 với baseline `ae8f8f7b9cab6679bd00fa8730e6357671921709`: [bảng từng file, hash web và giới hạn kiểm](release-v2-source-audit.md). Gói `ledger-web-release-2026-10-20-v2` giữ ngoài Git; mã web trong Git khớp từng byte gói v2 sau khi cập nhật hai hằng opening (người dùng chốt 21/10/2026). Hash sau là bytes của chính file metadata, không phải bằng chứng service đã cài hoặc đang chạy.

| File trong gói | SHA-256 bytes gốc |
| --- | --- |
| `release.sha256` | `3dff80b81a734590ae5d2ef0949e62e034a6972000e0e7943ca06377b78249d4` |
| `installed.sha256` | `c2a389ebee03ce6e61dd680276ca8c7b6619189490f6a9457d1d4c6921fcc989` |
| `previous.sha256` | `8c509115d59bc40ff22c098d1fe8c9398f8a0dfac2ce727862f5eebf9878d0c1` |
| `install.sh` | `25c066af3a530a81c0c28f3b16557f51db982cf46f222d04ff3e7f925dda8c41` |
