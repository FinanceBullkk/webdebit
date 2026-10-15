# Sổ opening/posting và đường ghi P0

**Trạng thái:** web hiện có đường đọc; schema/đường ghi còn các gate P0. Xem [quyết định](../decisions.md) và [spec P0](../../specs/p0-write-path/README.md) trước khi đề xuất sửa tiền.

- Luồng đọc: HTTP request → `web/ledger_app.py:LedgerHandler` → `web/ledger_db.py` → opening, posting, pending và chi tiết.
- SQL hiện có: `cong-no-web-handoff/tools/pg_ledger_schema.sql`; đây không phải migration production đã duyệt.
- Kiểm: `tests/test_ledger_web.py` dùng fake DB; `tools/test_pg_ledger_schema.py` characterization trên PostgreSQL giả tách khỏi service thật. Xem [bằng chứng có revision](../verification.md).
- Bất biến: khách + kỳ; receipt khác allocation; pending ngoài số dư; maker khác checker; posting không sửa đè; lịch sử trong opening không cộng lại.
- Giới hạn: CI/fixture không chứng minh danh tính người thật, quyền duyệt, dữ liệu live hoặc ghi tiền production.
