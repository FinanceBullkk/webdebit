-- Hoàn tác 2026-11-25-tien-p0a-lat2.sql: xóa bảng file gốc, bằng chứng số dư, review ngày, cột statement_import.file_id, trigger chặn
-- ngày đã ký, các hàm của lát 2, và đưa ràng buộc vết về bản lát 1 (spec specs/so-tien-p0a-lat2.md, mục Đầu ra).
-- CHỈ DÙNG KHI CHƯA CÓ DỮ LIỆU CỦA LÁT 2. Sao lưu trước theo runbook. File tự dừng (TIEN_HAS_DATA) khi đã có file gốc, bằng chứng
-- số dư hay dòng ký ngày nào. Sau file này chạy lại 2026-11-24-tien-p0a-lat1.sql (chạy lại được) để đưa preview_import về bản lát 1;
-- trước bước đó lệnh xem trước bị lỗi (không ghi được gì). Không đụng dữ liệu lát 1, schema hay role nào khác.
BEGIN;
DO $$
BEGIN
    IF to_regclass('tien.statement_file') IS NOT NULL THEN
        IF EXISTS (SELECT 1 FROM tien.statement_file) OR EXISTS (SELECT 1 FROM tien.balance_evidence)
           OR EXISTS (SELECT 1 FROM tien.day_review) THEN
            RAISE EXCEPTION 'TIEN_HAS_DATA';
        END IF;
    END IF;
END $$;
SET LOCAL ROLE tien_owner;
DROP TRIGGER IF EXISTS bank_transaction_signed_day ON tien.bank_transaction;
DROP FUNCTION IF EXISTS tien._guard_signed_day(), tien.record_balance_evidence(jsonb), tien.sign_day_coverage(jsonb),
    tien.sign_day_business(jsonb), tien.reopen_day(jsonb), tien.my_access(), tien.list_accounts(), tien.get_account_card(bigint),
    tien.get_coverage(bigint, date, date), tien.get_day(bigint, date), tien.list_imports(bigint), tien.get_import(bigint),
    tien.get_transaction(bigint), tien.get_statement_file(bigint), tien.export_rows(bigint, date, date), tien._signed_days(bigint, jsonb, jsonb),
    tien._read_account(bigint, text), tien._require_any(text[], bigint, bigint), tien._my_roles(bigint, bigint), tien._who(bigint),
    tien._day_business(bigint, date), tien._day_check(bigint, date), tien._day_evidence(bigint, date), tien._day_importers(bigint, date),
    tien._ledger_closing(bigint, date), tien._coverage(bigint, date, date), tien._day_status(bigint, date, text);
DROP INDEX IF EXISTS tien.statement_import_period;
ALTER TABLE tien.statement_import DROP CONSTRAINT IF EXISTS statement_import_file_fk;
ALTER TABLE tien.statement_import DROP COLUMN IF EXISTS file_id;
DROP TABLE IF EXISTS tien.day_review, tien.balance_evidence, tien.statement_file;
ALTER TABLE tien.event DROP CONSTRAINT IF EXISTS tien_event_kind, DROP CONSTRAINT IF EXISTS tien_event_shape,
    ADD CONSTRAINT tien_event_kind CHECK (kind IN ('entity_create', 'account_create', 'opening_set', 'grant', 'revoke',
        'import_preview', 'import_commit', 'import_reject', 'import_void', 'allocation_set')),
    ADD CONSTRAINT tien_event_shape CHECK (CASE kind
        WHEN 'entity_create' THEN before = '{}' AND after ? 'legal_entity'
        WHEN 'account_create' THEN before = '{}' AND after ? 'account'
        WHEN 'opening_set' THEN before = '{}' AND after ? 'opening'
        WHEN 'grant' THEN before = '{}' AND after ? 'grant'
        WHEN 'revoke' THEN before ? 'grant' AND after ? 'grant'
        WHEN 'import_preview' THEN before = '{}' AND after ? 'import'
        WHEN 'import_commit' THEN before ? 'import' AND after ? 'import' AND after ? 'created' AND after ? 'confirmed'
        WHEN 'import_reject' THEN before ? 'import' AND after ? 'import'
        WHEN 'import_void' THEN before ? 'import' AND after ? 'import' AND after ? 'voided'
        WHEN 'allocation_set' THEN before ? 'transaction' AND before ? 'allocations' AND after ? 'allocations'
        ELSE false END);
COMMENT ON SCHEMA tien IS 'SO-TIEN-01 sổ tiền P0-a lát 1: nhập sao kê có xem trước, giao dịch ngân hàng, phân bổ; chỉ thêm, có vết.';
COMMIT;
