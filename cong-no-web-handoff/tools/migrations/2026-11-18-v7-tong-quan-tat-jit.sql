-- HIEU-NANG-02 (18/11/2026): get_dashboard_debt chạy với JIT tắt (specs/hieu-nang-02.md). Câu chính của hàm (Tổng quan,
-- Việc cần làm, huy hiệu menu, lưới an toàn) có chi phí ước tính ~180.000, vượt ngưỡng JIT mặc định (jit_above_cost 100.000),
-- nên mỗi lần gọi PostgreSQL biên dịch LLVM ~620 hàm: ~0,5 giây trên hao cho ~0,25 giây chạy thật.
-- Chỉ đổi cấu hình của một hàm đọc: không đổi thân hàm, bảng, view, dữ liệu, chủ hay quyền. Kết quả get_dashboard_debt giữ
-- nguyên từng byte. Chạy lại được. Chạy lại 2026-11-09-v7-thu-thang-theo-so.sql (hay migration cũ hơn có CREATE OR REPLACE
-- get_dashboard_debt: 2026-11-06-v7-ngay-tra-that.sql, 2026-10-29-v7-tong-quan-quan-ly-no.sql) thì phải chạy lại file này,
-- vì CREATE OR REPLACE xóa cấu hình hàm.
BEGIN;
SET LOCAL ROLE sokhach_owner;
ALTER FUNCTION sokhach.get_dashboard_debt() SET jit = off;
COMMIT;
