# OPENING-SO-GOC

[← Sổ quyết định](../decisions.md)

## Quyết định

Người dùng/chủ nghiệp vụ chốt **sổ gốc** — Google Sheet đang dùng hằng ngày, gồm tab tổng hợp `TONG` và tab từng khách — là chuẩn cho số dư đầu, và mở lại sổ PostgreSQL trên `hao` từ sổ gốc, thay replay 13/10 (`OPENING`). Quy tắc lấy số chung: đọc từng chuyến/khoản thu ở tab khách, không lấy sổ chép lại hay replay 13/10 làm chuẩn; khi `TONG` lệch tab khách thì lấy số tab khách (20/10/2026); chia số dư của khách thành nợ từng kỳ theo thu trừ chuyến cũ nhất trước (FIFO, cùng hướng [`V7-MIG`](v7-mig.md)); mọi kỳ mang cờ `NO_BASELINE`. Quy tắc riêng theo từng khách (gộp tên trùng, ô bảo hiểm, tab trùng tên, khối chuyển kỳ gõ tay) giữ ở hồ sơ ngoài Git.

## Ngày / nguồn

19/10/2026, xác nhận trong chat; bổ sung 20/10/2026 sau khi đối soát lại sổ gốc

## Hiệu lực và giới hạn

ĐÃ CHỐT nguồn và cách lấy số. ĐÃ TRIỂN KHAI trên `hao` theo hồ sơ phiên 19–20/10/2026: nạp lần đầu ngày 19/10, nạp lại bản v2 ngày 20/10 (người dùng tự chạy lệnh nạp, đọc lại DB cùng ngày; mốc cutover `2026-10-20-so-goc-v2`; lúc nạp chưa có proposal/posting; trigger khóa opening bật); web xem sổ cài gói `ledger-web-release-2026-10-20-v2`. Số kỳ, tổng tiền, backup trước nạp và bảng đối soát ở `captures/2026-10-19-so-goc/`, `captures/2026-10-20-so-goc/`, `design/2026-10-20/`, ngoài Git. Chưa kiểm lại live sau thời điểm đó. CÒN MỞ: (1) mã web của bản v2 chưa có trong Git — `main` (PR #30) gắn mốc bản trung gian `2026-10-20-so-goc`, còn bản chạy trên `hao` lấy từ gói release; (2) bản hotfix tắt lịch sử replay M1 (`HISTORY_ENABLED=False`) vì sổ mới không có provenance replay; (3) mốc chuyến mới — đã chốt ngày 20/10/2026 bằng [`MOC-CHUYEN-MOI`](moc-chuyen-moi.md); (4) bản xuất sổ gốc chưa đóng băng bằng hash ghi trong repo.
