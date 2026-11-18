-- MO-SO-NHANH-03 (18/11/2026): get_ledger chạy với JIT tắt (specs/mo-so-nhanh-03.md). Câu dựng bảng tháng của get_ledger
-- có chi phí ước tính vượt ngưỡng JIT mặc định ở sổ lớn (sổ 104 ~800.000, jit_above_cost 100.000), nên mỗi lần mở sổ
-- PostgreSQL biên dịch LLVM vài trăm hàm: ~3 giây biên dịch cho vài chục ms chạy thật, lâu hơn nữa khi máy bận.
-- Chỉ đổi cấu hình của một hàm đọc: không đổi thân hàm, bảng, view, dữ liệu, chủ hay quyền. Kết quả get_ledger giữ nguyên
-- từng byte. Chạy lại được. Chạy lại 2026-11-04-v7-ledger-events.sql (hay migration cũ hơn có CREATE OR REPLACE get_ledger)
-- thì phải chạy lại file này, vì CREATE OR REPLACE xóa cấu hình hàm.
BEGIN;
SET LOCAL ROLE sokhach_owner;
ALTER FUNCTION sokhach.get_ledger(bigint) SET jit = off;
COMMIT;
