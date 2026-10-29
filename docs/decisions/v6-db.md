# V6-DB

[← Sổ quyết định](../decisions.md)

## Quyết định

Người dùng chốt bỏ người duyệt thứ hai ở **cả đường ghi tiền PostgreSQL**, không chỉ ở sổ web: một người nhập và ghi sổ, không cần người thứ hai duyệt. Mở rộng `V6-2` sang tầng database.

## Ngày / nguồn

19/10/2026, xác nhận trong chat sau khi được nêu rõ hệ quả

## Hiệu lực và giới hạn

ĐÃ CHỐT **chính sách**. CHƯA TRIỂN KHAI, và hiện mã đang làm ngược: `cong-no-web-handoff/tools/pg_ledger_schema.sql` còn hai role `ledger_maker`/`ledger_checker`, ràng buộc `CHECK (checker <> maker)` ở dòng 93, và luồng `submit_entry` → `approve_entry`. 8 trong 13 case của bộ kiểm PostgreSQL 18.6 đứng trên cơ chế đó. Sửa schema cần spec riêng trước khi viết DDL; chưa có service live nên đây là sửa thiết kế, không phải migration dữ liệu. Người dùng đã được nêu rõ: bỏ `CHECK (checker <> maker)` là bỏ lớp chặn tự duyệt ở tầng cuối, sau này dựng lại phải migration. CÒN MỞ: ai được xem lưu vết (V6 mục 6.5); `Q01` phần maker/checker khác nhau hết hiệu lực theo dòng này, phần tài khoản riêng theo người và session server-side vẫn giữ. **Bổ sung 20/10/2026:** thiết kế backend V7 nháp dùng lược đồ mới `sokhach` không có maker/checker ([`V7-MIG`](v7-mig.md)); danh tính người thao tác theo [`V7-ID`](v7-id.md).
