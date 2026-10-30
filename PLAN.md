# PLAN — hiện tại (22/10/2026)

| Bước | Trạng thái |
| --- | --- |
| Dựng Harness Claude (CLAUDE.md, MAP, contexte, agents, skill, quét secrets) | Đã commit (PR #41) |
| Đưa V7 vào `main` và triển khai lên `hao` | ĐÃ TRIỂN KHAI: nạp mốc `clean-v2` 21/10 (PR #48), nâng lên `ada72cc` 22/10 (PR #56: kiểm trùng dán lô, ô tham chiếu, Lịch sử mở/khóa tháng); đối soát `DOI SOAT: DAT` 236 khách |
| Ghi vết sửa Sheet nguồn (capture-only) | ĐÃ CÀI trên Sheet thật 21/10 (PR #59) |
| Đủ điều kiện bắt đầu chạy song song Sheet–web | CÒN MỞ, theo [checklist](docs/song-song-checklist.md): dán bù sau mốc, hai khách bị giữ (đã chốt 30/10, `SONG-SONG-03`; một khách còn mở tới trước chuyển hẳn), tài khoản Tailscale từng người, backup định kỳ, giao diện và triển khai kết luận CHỜ KIỂM (backend đã có, PR #63, #64) |
| Chạy song song tới một lần cuối tháng khớp, rồi chuyển hẳn | Chờ bước trước |

Cập nhật bảng khi trạng thái đổi; lộ trình ở `docs/roadmap.md`, điều kiện khởi động ở `docs/song-song-checklist.md`.
