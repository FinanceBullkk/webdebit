# FUTURE-01

[← Sổ quyết định](../decisions.md)

## Quyết định

Người dùng chốt cấm phiếu có ngày ghi sổ (`posting_date`) sau ngày hiện tại theo giờ Việt Nam (Asia/Ho_Chi_Minh), chặn ở cả bước nhập, đề nghị đảo và bước duyệt. Ngày ghi sổ bằng hôm nay vẫn hợp lệ.

## Ngày / nguồn

16/10/2026, xác nhận trong chat khi review audit ledger 16/10 (F2)

## Hiệu lực và giới hạn

ĐÃ CHỐT chính sách. Nhánh `fix/ledger-audit-f1-f3` sửa `tools/pg_ledger_schema.sql` và kiểm bằng harness PostgreSQL 18.6 trên dữ liệu giả; chưa migration, chưa triển khai trên DB thật. Không đổi quy tắc ngày nghiệp vụ (`event_date`) hay chính sách nhập muộn/khóa kỳ D07. **Sửa 20/10/2026:** theo `V6-DB` không còn bước duyệt, nên chặn ở mọi hàm ghi sổ có `posting_date` (hàm ghi thẳng), không còn "bước duyệt" để chặn. Câu báo lỗi của luật `FUTURE-01` trong `scripts/business-rules.js` đã sửa theo (20/10/2026): mọi hàm ghi sổ tự chặn, không nhắc bước duyệt. Lược đồ V7 nháp (`sokhach`) không có cột `posting_date`; áp luật này vào V7 thế nào CÒN MỞ. **Sửa 29/10/2026 (rà đường ghi tiền; Claude chốt theo quyền 21/10, người dùng duyệt sửa trong chat):** áp vào V7 — ngày phiếu thu, ngày cấn trừ và **ngày xe nhập kho** của chuyến đều không được sau hôm nay giờ VN, hàm ghi tự chặn (`FUTURE_RECEIPT_DATE`, `FUTURE_DATE`). Trước đó `paste_trips` (dán lô, gồm chuyến đồng bộ từ Sheet) không chặn trong khi sửa ngày tại ô đã chặn; migration `2026-10-29-v7-ra-ghi-tien.sql` đóng khoảng trống này. Vế CÒN MỞ cho V7 đóng.
