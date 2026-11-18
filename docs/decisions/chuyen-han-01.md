# CHUYEN-HAN-01

[← Sổ quyết định](../decisions.md)

## Quyết định

**Chưa chuyển hẳn khỏi Sheet. Xét lại sau đối soát cuối tháng 11/2026.**

1. Người nhập vẫn ghi trên Sheet. Sheet vẫn là sổ chính thức, chưa khóa chỉ xem. Web tự chạy theo Sheet như [`MAY-DOI-SOAT-01`](may-doi-soat-01.md).
2. Vế "sau đó khóa Sheet ở chế độ chỉ xem" trong điều kiện chuyển hẳn của [`SONG-SONG-01`](song-song-01.md) **chưa áp dụng**. Các điều kiện còn lại của vế đó giữ nguyên.
3. Sau đối soát cuối tháng 11, chủ nghiệp vụ quyết có chuyển không và chuyển thế nào, dựa trên số đo của cả tháng: số lượt khớp, số việc máy tự ghi, số khách phải có người xem.

## Ngày / nguồn

5/11/2026, chat. Claude hỏi "chuyển hẳn" nên hiểu thế nào, vì quyết định cũ là khóa Sheet và nhập trên web, còn từ 4/11/2026 hướng mới là người nhập vẫn ghi Sheet. Người dùng chọn "Giữ Sheet, xét sau T11", không chọn "Vẫn khóa Sheet như cũ".

## Hiệu lực và giới hạn

ĐÃ CHỐT tới lần xét sau đối soát cuối tháng 11/2026. Trả lời câu CÒN MỞ của `MAY-DOI-SOAT-01` và mục F4 của [checklist](../song-song-checklist.md) cho tới lần xét đó, chưa phải quyết định chuyển hẳn. Không đổi luật tiền, DB, quyền hay máy ghi. Mốc tháng tính ở [`SONG-SONG-02`](song-song-02.md).

**Cập nhật 11/11/2026 (phạm vi, người dùng nói trong chat):** "phạm vi thay sheet chính là chuyển từ quản lý debit trên sheet 2026 debit sang web này". Thứ được xét thay là **Sheet sổ nợ** (tab TONG và các tab khách). Claude hiểu là file nguồn chuyến CHAU_HAO (`CONT_NGUON`, `CONT_BO`) vẫn dùng như [`NGUON-CHUYEN-01`](nguon-chuyen-01.md); người dùng chưa nói thẳng điều này, CÒN MỞ nếu hiểu sai. Cùng ngày người dùng hỏi cần audit những gì để nói web thay được Sheet, rồi cho chạy phần chỉ đọc và đưa vào repo: danh mục và số đo ở [checklist chuyển hẳn](../chuyen-han-checklist.md), công cụ theo [spec](../../specs/v7-cutover-audit.md). Danh mục là ĐỀ XUẤT của Claude, chưa phải điều kiện đã chốt; điều kiện đã chốt vẫn là của [`SONG-SONG-01`](song-song-01.md). Lượt đo đó cho thấy ba đầu vào (chuyến bộ, giá, phiếu thu) cùng khách mới còn lấy từ Sheet sổ nợ: phương án thay CÒN MỞ.
