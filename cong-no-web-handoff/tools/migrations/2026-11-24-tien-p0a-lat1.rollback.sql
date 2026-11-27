-- Hoàn tác 2026-11-24-tien-p0a-lat1.sql: xóa schema `tien` cùng mọi bảng, hàm, trigger trong đó và ba role tien_owner, tien_app,
-- tien_reader (spec specs/so-tien-p0a.md, mục Hoàn tác).
-- CHỈ DÙNG KHI CHƯA CÓ DỮ LIỆU THẬT. Sao lưu trước theo runbook. File tự dừng (TIEN_HAS_DATA) khi đã có bất kỳ tài khoản nào (số dư
-- mở, lô sao kê, giao dịch, phân bổ đều cần tài khoản); chỉ còn pháp nhân và cấp vai khởi tạo thì được xóa. Có dữ liệu thật thì không
-- xóa, tắt cờ. Login của API/máy canh (thành viên tien_app/tien_reader) do runbook tạo thì runbook gỡ; xóa role ở đây chỉ bỏ tư cách
-- thành viên của login đó. Không đụng schema hay role nào khác.
BEGIN;
DO $$
BEGIN
    IF to_regclass('tien.financial_account') IS NOT NULL THEN
        IF EXISTS (SELECT 1 FROM tien.financial_account) THEN
            RAISE EXCEPTION 'TIEN_HAS_DATA';
        END IF;
    END IF;
END $$;
DROP SCHEMA IF EXISTS tien CASCADE;
DO $$
DECLARE r text;
BEGIN
    FOREACH r IN ARRAY ARRAY['tien_app', 'tien_reader', 'tien_owner'] LOOP
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = r) THEN
            -- Bỏ quyền mặc định (ALTER DEFAULT PRIVILEGES) và quyền còn sót của role trong DB này trước khi xóa role.
            EXECUTE format('DROP OWNED BY %I', r);
            EXECUTE format('DROP ROLE %I', r);
        END IF;
    END LOOP;
END $$;
COMMIT;
