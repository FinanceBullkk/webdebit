-- Sổ tiền P0-a, lát 1 (SO-TIEN-01, 24/11/2026; spec specs/so-tien-p0a.md; thiết kế specs/van-hanh-tai-chinh/F1-kien-truc-ky-thuat.md
-- mục 3, 4, 5.1, 6, 7, 8 và F2-adr.md): schema riêng `tien` gồm tiền tệ, pháp nhân, tài khoản, số dư mở, cấp vai, lô sao kê và dòng
-- gốc, giao dịch ngân hàng và dòng nguồn, phân bổ, vết chỉ thêm, khóa lặp; mười hàm lệnh (một jsonb vào, jsonb ra) và hai hàm đọc.
-- Không đọc, không ghi, không cấp quyền gì ở schema sổ nợ hay đội xe. Không quyền bảng cho role nào ngoài chủ schema.
-- Tiền là bigint đơn vị nhỏ nhất (cột *_minor), vào/ra là chuỗi số nguyên; NULL là chưa biết, không phải 0.
-- Người làm lấy từ tien.actor và tien.actor_kind (API đặt bằng SET LOCAL), không nhận từ payload. Lệnh trên tài khoản khóa dòng
-- financial_account (FOR NO KEY UPDATE) trước mọi kiểm; vai và phạm vi pháp nhân kiểm ngay trong hàm; "hôm nay" theo giờ VN.
-- Chạy lại được: lần hai chỉ báo đã có. Hoàn tác: 2026-11-24-tien-p0a-lat1.rollback.sql. Chưa chạy trên hao (spec, Trạng thái).
BEGIN;
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'tien_owner') THEN CREATE ROLE tien_owner NOLOGIN; END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'tien_app') THEN CREATE ROLE tien_app NOLOGIN; END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'tien_reader') THEN CREATE ROLE tien_reader NOLOGIN; END IF;
END $$;
CREATE SCHEMA IF NOT EXISTS tien AUTHORIZATION tien_owner;
REVOKE ALL ON SCHEMA tien FROM PUBLIC;
GRANT USAGE ON SCHEMA tien TO tien_app, tien_reader;
SET LOCAL ROLE tien_owner;
ALTER DEFAULT PRIVILEGES FOR ROLE tien_owner REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC;
COMMENT ON SCHEMA tien IS 'SO-TIEN-01 sổ tiền P0-a lát 1: nhập sao kê có xem trước, giao dịch ngân hàng, phân bổ; chỉ thêm, có vết.';

-- ---------------------------------------------------------------------------------------------------------------------------
-- Bảng chỉ thêm (I-7): trigger chặn UPDATE/DELETE/TRUNCATE; bảng có cột trạng thái chỉ cho đổi đúng các cột đó, đúng một chiều.
CREATE OR REPLACE FUNCTION tien._reject_change() RETURNS trigger
LANGUAGE plpgsql SET search_path TO 'pg_catalog', 'tien', 'pg_temp' AS $$
BEGIN
    RAISE EXCEPTION 'IMMUTABLE: tien.%', TG_TABLE_NAME;
END $$;

-- Tham số trigger là các cột được đổi: version tăng đúng 1; status theo các bước lô nhập; cột còn lại (…_event, reason) chỉ ghi
-- một lần từ NULL. Mọi cột khác và DELETE bị chặn.
CREATE OR REPLACE FUNCTION tien._guard_update() RETURNS trigger
LANGUAGE plpgsql SET search_path TO 'pg_catalog', 'tien', 'pg_temp' AS $$
DECLARE o jsonb; n jsonb; c text;
BEGIN
    IF TG_OP <> 'UPDATE' THEN RAISE EXCEPTION 'IMMUTABLE: tien.%', TG_TABLE_NAME; END IF;
    o := to_jsonb(OLD);
    n := to_jsonb(NEW);
    FOREACH c IN ARRAY TG_ARGV LOOP
        IF o -> c IS DISTINCT FROM n -> c AND NOT (CASE
            WHEN c = 'version' THEN (n ->> c)::bigint = (o ->> c)::bigint + 1
            WHEN c = 'status' THEN (o ->> c, n ->> c) IN (('validated', 'committed'), ('validated', 'rejected'), ('committed', 'voided'))
            ELSE jsonb_typeof(o -> c) = 'null' AND jsonb_typeof(n -> c) <> 'null' END) THEN
            RAISE EXCEPTION 'IMMUTABLE: tien.%.%', TG_TABLE_NAME, c;
        END IF;
        o := o - c;
        n := n - c;
    END LOOP;
    IF o IS DISTINCT FROM n THEN RAISE EXCEPTION 'IMMUTABLE: tien.%', TG_TABLE_NAME; END IF;
    RETURN NEW;
END $$;

CREATE TABLE IF NOT EXISTS tien.currency (
    code text PRIMARY KEY CHECK (code ~ '^[A-Z]{3}$'),
    minor_unit smallint NOT NULL CHECK (minor_unit BETWEEN 0 AND 3)
);
COMMENT ON TABLE tien.currency IS 'Tiền tệ và số chữ số lẻ của đơn vị nhỏ nhất (VND 0, USD 2, CNY 2).';
INSERT INTO tien.currency(code, minor_unit) VALUES ('VND', 0), ('USD', 2), ('CNY', 2) ON CONFLICT (code) DO NOTHING;

CREATE TABLE IF NOT EXISTS tien.event (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    legal_entity_id bigint NOT NULL,
    account_id bigint,
    kind text NOT NULL,
    actor text NOT NULL CHECK (btrim(actor) <> '' AND char_length(actor) <= 200),
    actor_kind text NOT NULL CHECK (actor_kind IN ('human', 'machine')),
    at timestamptz NOT NULL DEFAULT clock_timestamp(),
    before jsonb NOT NULL CHECK (jsonb_typeof(before) = 'object'),
    after jsonb NOT NULL CHECK (jsonb_typeof(after) = 'object'),
    idempotency_key text NOT NULL CHECK (btrim(idempotency_key) <> '' AND char_length(idempotency_key) <= 128),
    CONSTRAINT tien_event_kind CHECK (kind IN ('entity_create', 'account_create', 'opening_set', 'grant', 'revoke',
        'import_preview', 'import_commit', 'import_reject', 'import_void', 'allocation_set')),
    CONSTRAINT tien_event_shape CHECK (CASE kind
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
        ELSE false END)
);
COMMENT ON TABLE tien.event IS 'Vết chỉ thêm của mọi lệnh sổ tiền: người làm, người hay máy, trước → sau, khóa lặp.';

CREATE TABLE IF NOT EXISTS tien.legal_entity (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    code text NOT NULL UNIQUE CHECK (code ~ '^[A-Z0-9][A-Z0-9_-]{1,31}$'),
    name text NOT NULL CHECK (btrim(name) <> '' AND char_length(name) <= 200),
    status text NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'closed')),
    created_event bigint NOT NULL REFERENCES tien.event(id)
);
COMMENT ON TABLE tien.legal_entity IS 'Pháp nhân. Pháp nhân đầu tiên và vai quản trị đầu tiên chèn theo runbook (không qua hàm lệnh).';

CREATE TABLE IF NOT EXISTS tien.financial_account (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    legal_entity_id bigint NOT NULL REFERENCES tien.legal_entity(id),
    kind text NOT NULL CHECK (kind IN ('bank', 'cash')),
    bank_code text CHECK (bank_code ~ '^[A-Z0-9]{2,16}$'),
    account_last4 text CHECK (account_last4 ~ '^[0-9]{4}$'),
    account_hmac text NOT NULL CHECK (account_hmac ~ '^[0-9a-f]{64}$'),
    currency text NOT NULL REFERENCES tien.currency(code),
    holder text NOT NULL CHECK (holder IN ('company', 'personal')),
    statement_template text CHECK (statement_template ~ '^[a-z0-9][a-z0-9_-]{0,39}@[1-9][0-9]{0,3}$'),
    bank_ref_stable boolean NOT NULL DEFAULT false,
    status text NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'closed')),
    version bigint NOT NULL DEFAULT 0 CHECK (version >= 0),
    created_event bigint NOT NULL REFERENCES tien.event(id),
    CONSTRAINT financial_account_bank_fields CHECK (kind <> 'bank' OR (bank_code IS NOT NULL AND account_last4 IS NOT NULL)),
    CONSTRAINT financial_account_stable_template CHECK (NOT bank_ref_stable OR statement_template IS NOT NULL),
    CONSTRAINT financial_account_once UNIQUE (legal_entity_id, account_hmac, currency),
    CONSTRAINT financial_account_entity_key UNIQUE (id, legal_entity_id),
    CONSTRAINT financial_account_currency_key UNIQUE (id, currency)
);
COMMENT ON TABLE tien.financial_account IS 'Tài khoản: một pháp nhân, một tiền tệ, không đổi sau khi tạo. Số tài khoản chỉ giữ HMAC + 4 số cuối.';
COMMENT ON COLUMN tien.financial_account.version IS 'Tăng 1 khi commit hoặc hủy lô; xem trước ghi lại để commit biết sổ đã đổi (IMPORT_PREVIEW_STALE).';

CREATE TABLE IF NOT EXISTS tien.account_opening (
    account_id bigint PRIMARY KEY REFERENCES tien.financial_account(id),
    as_of date NOT NULL,
    amount_minor bigint NOT NULL,
    evidence_note text NOT NULL CHECK (btrim(evidence_note) <> '' AND char_length(evidence_note) <= 500),
    created_event bigint NOT NULL REFERENCES tien.event(id)
);
COMMENT ON TABLE tien.account_opening IS 'Số dư mở một lần cho mỗi tài khoản: số dư đầu ngày as_of; dòng sao kê trước as_of là lỗi.';

CREATE TABLE IF NOT EXISTS tien.access_grant (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    login text NOT NULL CHECK (login ~ '^[^[:space:][:cntrl:]]{1,200}$'),
    role text NOT NULL CHECK (role IN ('tien_xem', 'tien_nhap', 'tien_phan_bo', 'tien_review', 'tien_quan_tri')),
    legal_entity_id bigint NOT NULL REFERENCES tien.legal_entity(id),
    account_id bigint,
    created_event bigint NOT NULL REFERENCES tien.event(id),
    revoked_event bigint REFERENCES tien.event(id),
    CONSTRAINT access_grant_account_fk FOREIGN KEY (account_id, legal_entity_id) REFERENCES tien.financial_account(id, legal_entity_id)
);
COMMENT ON TABLE tien.access_grant IS 'Vai sổ tiền theo login: hiệu lực khi chưa thu, cho đúng tài khoản hoặc cả pháp nhân (account_id NULL).';

CREATE TABLE IF NOT EXISTS tien.statement_import (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    account_id bigint NOT NULL REFERENCES tien.financial_account(id),
    file_sha256 text NOT NULL CHECK (file_sha256 ~ '^[0-9a-f]{64}$'),
    template text NOT NULL CHECK (template ~ '^[a-z0-9][a-z0-9_-]{0,39}@[1-9][0-9]{0,3}$'),
    period_from date NOT NULL,
    period_to date NOT NULL,
    opening_minor bigint,
    closing_minor bigint,
    last_day_complete boolean NOT NULL,
    preview_account_version bigint NOT NULL,
    preview_hash text NOT NULL CHECK (preview_hash ~ '^[0-9a-f]{64}$'),
    counts jsonb NOT NULL CHECK (jsonb_typeof(counts) = 'object'),
    status text NOT NULL DEFAULT 'validated' CHECK (status IN ('validated', 'committed', 'rejected', 'voided')),
    reason text CHECK (btrim(reason) <> '' AND char_length(reason) <= 500),
    created_event bigint NOT NULL REFERENCES tien.event(id),
    committed_event bigint REFERENCES tien.event(id),
    closed_event bigint REFERENCES tien.event(id),
    CONSTRAINT statement_import_period CHECK (period_from <= period_to),
    CONSTRAINT statement_import_state CHECK (CASE status
        WHEN 'validated' THEN committed_event IS NULL AND closed_event IS NULL AND reason IS NULL
        WHEN 'committed' THEN committed_event IS NOT NULL AND closed_event IS NULL AND reason IS NULL
        WHEN 'rejected' THEN committed_event IS NULL AND closed_event IS NOT NULL AND reason IS NOT NULL
        ELSE committed_event IS NOT NULL AND closed_event IS NOT NULL AND reason IS NOT NULL END),
    CONSTRAINT statement_import_account_key UNIQUE (id, account_id)
);
COMMENT ON TABLE tien.statement_import IS 'Lô nhập: validated → committed | rejected; committed → voided. Số đếm là lúc xem trước.';

CREATE TABLE IF NOT EXISTS tien.raw_statement_line (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    import_id bigint NOT NULL REFERENCES tien.statement_import(id),
    seq integer NOT NULL CHECK (seq > 0),
    line_no integer NOT NULL CHECK (line_no > 0),
    line jsonb NOT NULL CHECK (jsonb_typeof(line) = 'object' AND NOT line ? 'cells'),
    cells jsonb NOT NULL CHECK (jsonb_typeof(cells) = 'object'),
    line_hash text NOT NULL CHECK (line_hash ~ '^[0-9a-f]{64}$'),
    CONSTRAINT raw_statement_line_seq UNIQUE (import_id, seq),
    CONSTRAINT raw_statement_line_import_key UNIQUE (id, import_id)
);
COMMENT ON TABLE tien.raw_statement_line IS 'Dòng gốc StatementLine v1 như bộ đọc gửi (line) và ô chữ nguyên văn (cells); quyền hẹp, chỉ thêm.';

CREATE TABLE IF NOT EXISTS tien.bank_transaction (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    account_id bigint NOT NULL,
    currency text NOT NULL,
    source_family text NOT NULL CHECK (source_family ~ '^[a-z0-9][a-z0-9_-]{0,39}$'),
    direction text NOT NULL CHECK (direction IN ('in', 'out')),
    amount_minor bigint NOT NULL CHECK (amount_minor > 0),
    booking_date date NOT NULL,
    value_date date,
    bank_ref text CHECK (btrim(bank_ref) <> '' AND char_length(bank_ref) <= 100),
    description text CHECK (char_length(description) <= 1000),
    balance_after_minor bigint,
    fingerprint text NOT NULL CHECK (fingerprint ~ '^[0-9a-f]{64}$'),
    version bigint NOT NULL DEFAULT 0 CHECK (version >= 0),
    created_event bigint NOT NULL REFERENCES tien.event(id),
    voided_event bigint REFERENCES tien.event(id),
    CONSTRAINT bank_transaction_account_fk FOREIGN KEY (account_id, currency) REFERENCES tien.financial_account(id, currency),
    CONSTRAINT bank_transaction_account_key UNIQUE (id, account_id),
    CONSTRAINT bank_transaction_currency_key UNIQUE (id, account_id, currency)
);
COMMENT ON TABLE tien.bank_transaction IS 'Giao dịch ngân hàng: hiệu lực khi còn ít nhất một dòng nguồn ở lô chưa hủy (voided_event đánh dấu khi hết).';
COMMENT ON COLUMN tien.bank_transaction.fingerprint IS 'SHA-256 của tài khoản | ngày ghi sổ | chiều | số tiền | mô tả chuẩn hóa; không gồm số dư sau.';

CREATE TABLE IF NOT EXISTS tien.bank_transaction_source (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    bank_transaction_id bigint NOT NULL,
    account_id bigint NOT NULL,
    import_id bigint NOT NULL,
    raw_line_id bigint NOT NULL,
    role text NOT NULL CHECK (role IN ('origin', 'duplicate_confirmed')),
    created_event bigint NOT NULL REFERENCES tien.event(id),
    CONSTRAINT source_transaction_fk FOREIGN KEY (bank_transaction_id, account_id) REFERENCES tien.bank_transaction(id, account_id),
    CONSTRAINT source_import_fk FOREIGN KEY (import_id, account_id) REFERENCES tien.statement_import(id, account_id),
    CONSTRAINT source_line_fk FOREIGN KEY (raw_line_id, import_id) REFERENCES tien.raw_statement_line(id, import_id),
    CONSTRAINT source_line_once UNIQUE (raw_line_id),
    CONSTRAINT source_one_line_per_import UNIQUE (bank_transaction_id, import_id)
);
COMMENT ON TABLE tien.bank_transaction_source IS 'Dòng gốc nào là nguồn của giao dịch nào: một dòng gốc nhiều nhất một giao dịch, một lô không hai dòng cùng giao dịch.';

CREATE TABLE IF NOT EXISTS tien.allocation (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    bank_transaction_id bigint NOT NULL,
    account_id bigint NOT NULL,
    currency text NOT NULL,
    target_kind text NOT NULL CHECK (target_kind IN ('ar_book', 'customer_unapplied', 'internal_transfer',
        'internal_transfer_pending', 'cash_withdrawal', 'bank_fee', 'interest', 'customer_funds_pending', 'fleet',
        'expense_category', 'other')),
    target_ref jsonb NOT NULL CHECK (jsonb_typeof(target_ref) = 'object'),
    amount_minor bigint NOT NULL CHECK (amount_minor > 0),
    note text CHECK (btrim(note) <> '' AND char_length(note) <= 500),
    created_event bigint NOT NULL REFERENCES tien.event(id),
    superseded_event bigint REFERENCES tien.event(id),
    CONSTRAINT allocation_transaction_fk FOREIGN KEY (bank_transaction_id, account_id, currency)
        REFERENCES tien.bank_transaction(id, account_id, currency)
);
COMMENT ON TABLE tien.allocation IS 'Phân bổ một phần tiền của giao dịch vào một đích; thay cả bộ tạo phiên bản mới, dòng cũ giữ lại (superseded_event).';

CREATE TABLE IF NOT EXISTS tien.idempotency (
    scope text NOT NULL CHECK (scope ~ '^(global|entity:[1-9][0-9]*|account:[1-9][0-9]*)$'),
    key text NOT NULL CHECK (btrim(key) <> '' AND char_length(key) <= 128),
    command text NOT NULL,
    request_hash text NOT NULL CHECK (request_hash ~ '^[0-9a-f]{64}$'),
    result jsonb NOT NULL,
    actor text NOT NULL,
    at timestamptz NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (scope, key)
);
COMMENT ON TABLE tien.idempotency IS 'Khóa lặp theo phạm vi: cùng lệnh, cùng nội dung (không gồm người làm, expected_version) trả kết quả cũ.';

-- Vết có thể tạo trước pháp nhân/tài khoản trong cùng giao dịch (lệnh tạo), nên khóa ngoại của vết kiểm lúc commit.
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid = 'tien.event'::regclass AND conname = 'event_entity_fk') THEN
        ALTER TABLE tien.event ADD CONSTRAINT event_entity_fk FOREIGN KEY (legal_entity_id) REFERENCES tien.legal_entity(id)
            DEFERRABLE INITIALLY DEFERRED;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid = 'tien.event'::regclass AND conname = 'event_account_fk') THEN
        ALTER TABLE tien.event ADD CONSTRAINT event_account_fk FOREIGN KEY (account_id) REFERENCES tien.financial_account(id)
            DEFERRABLE INITIALLY DEFERRED;
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS event_account ON tien.event (account_id, id) WHERE account_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS event_entity ON tien.event (legal_entity_id, id);
CREATE UNIQUE INDEX IF NOT EXISTS access_grant_active ON tien.access_grant (login, role, legal_entity_id, coalesce(account_id, 0))
    WHERE revoked_event IS NULL;
CREATE UNIQUE INDEX IF NOT EXISTS statement_import_file_once ON tien.statement_import (account_id, file_sha256) WHERE status = 'committed';
CREATE INDEX IF NOT EXISTS statement_import_account ON tien.statement_import (account_id, id);
CREATE INDEX IF NOT EXISTS bank_transaction_fingerprint ON tien.bank_transaction (account_id, fingerprint) WHERE voided_event IS NULL;
CREATE INDEX IF NOT EXISTS bank_transaction_ref ON tien.bank_transaction (account_id, source_family, bank_ref)
    WHERE voided_event IS NULL AND bank_ref IS NOT NULL;
CREATE INDEX IF NOT EXISTS bank_transaction_date ON tien.bank_transaction (account_id, booking_date, id);
CREATE UNIQUE INDEX IF NOT EXISTS source_one_origin ON tien.bank_transaction_source (bank_transaction_id) WHERE role = 'origin';
CREATE INDEX IF NOT EXISTS source_import ON tien.bank_transaction_source (import_id);
CREATE INDEX IF NOT EXISTS allocation_active ON tien.allocation (bank_transaction_id) WHERE superseded_event IS NULL;

CREATE OR REPLACE TRIGGER currency_immutable BEFORE UPDATE OR DELETE ON tien.currency FOR EACH ROW EXECUTE FUNCTION tien._reject_change();
CREATE OR REPLACE TRIGGER event_immutable BEFORE UPDATE OR DELETE ON tien.event FOR EACH ROW EXECUTE FUNCTION tien._reject_change();
CREATE OR REPLACE TRIGGER legal_entity_immutable BEFORE UPDATE OR DELETE ON tien.legal_entity FOR EACH ROW EXECUTE FUNCTION tien._reject_change();
CREATE OR REPLACE TRIGGER account_opening_immutable BEFORE UPDATE OR DELETE ON tien.account_opening FOR EACH ROW
    EXECUTE FUNCTION tien._reject_change();
CREATE OR REPLACE TRIGGER raw_statement_line_immutable BEFORE UPDATE OR DELETE ON tien.raw_statement_line FOR EACH ROW
    EXECUTE FUNCTION tien._reject_change();
CREATE OR REPLACE TRIGGER bank_transaction_source_immutable BEFORE UPDATE OR DELETE ON tien.bank_transaction_source FOR EACH ROW
    EXECUTE FUNCTION tien._reject_change();
CREATE OR REPLACE TRIGGER idempotency_immutable BEFORE UPDATE OR DELETE ON tien.idempotency FOR EACH ROW EXECUTE FUNCTION tien._reject_change();
CREATE OR REPLACE TRIGGER financial_account_guard BEFORE UPDATE OR DELETE ON tien.financial_account FOR EACH ROW
    EXECUTE FUNCTION tien._guard_update('version');
CREATE OR REPLACE TRIGGER access_grant_guard BEFORE UPDATE OR DELETE ON tien.access_grant FOR EACH ROW
    EXECUTE FUNCTION tien._guard_update('revoked_event');
CREATE OR REPLACE TRIGGER statement_import_guard BEFORE UPDATE OR DELETE ON tien.statement_import FOR EACH ROW
    EXECUTE FUNCTION tien._guard_update('status', 'committed_event', 'closed_event', 'reason');
CREATE OR REPLACE TRIGGER bank_transaction_guard BEFORE UPDATE OR DELETE ON tien.bank_transaction FOR EACH ROW
    EXECUTE FUNCTION tien._guard_update('version', 'voided_event');
CREATE OR REPLACE TRIGGER allocation_guard BEFORE UPDATE OR DELETE ON tien.allocation FOR EACH ROW
    EXECUTE FUNCTION tien._guard_update('superseded_event');
DO $$
DECLARE t text;
BEGIN
    FOREACH t IN ARRAY ARRAY['currency', 'event', 'legal_entity', 'financial_account', 'account_opening', 'access_grant',
                             'statement_import', 'raw_statement_line', 'bank_transaction', 'bank_transaction_source',
                             'allocation', 'idempotency'] LOOP
        EXECUTE format('CREATE OR REPLACE TRIGGER %I BEFORE TRUNCATE ON tien.%I FOR EACH STATEMENT EXECUTE FUNCTION tien._reject_change()',
                       t || '_no_truncate', t);
    END LOOP;
END $$;

-- Trạng thái suy ra từ phân bổ hiệu lực (F1 mục 4), không lưu cột: vào unidentified → unapplied (chỉ customer_unapplied) →
-- partial → applied; ra unmatched → partial → matched.
CREATE OR REPLACE VIEW tien.v_transaction AS
SELECT t.id, t.account_id, t.currency, t.direction, t.amount_minor, t.booking_date, t.value_date, t.bank_ref, t.description,
       t.version, t.voided_event, coalesce(a.allocated, 0)::bigint AS allocated_minor,
       CASE WHEN t.voided_event IS NOT NULL THEN 'voided'
            WHEN t.direction = 'in' THEN CASE WHEN a.n = 0 THEN 'unidentified' WHEN a.n = a.unapplied THEN 'unapplied'
                                              WHEN a.allocated < t.amount_minor THEN 'partial' ELSE 'applied' END
            ELSE CASE WHEN a.n = 0 THEN 'unmatched' WHEN a.allocated < t.amount_minor THEN 'partial' ELSE 'matched' END
       END AS status
  FROM tien.bank_transaction t
  CROSS JOIN LATERAL (SELECT count(*) AS n, count(*) FILTER (WHERE l.target_kind = 'customer_unapplied') AS unapplied,
                             sum(l.amount_minor) AS allocated
                        FROM tien.allocation l WHERE l.bank_transaction_id = t.id AND l.superseded_event IS NULL) a;

-- ---------------------------------------------------------------------------------------------------------------------------
-- Hàm phụ: không cấp cho ai (chỉ chạy bên trong hàm lệnh/hàm đọc, quyền của tien_owner).
CREATE OR REPLACE FUNCTION tien._actor() RETURNS text
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path TO 'pg_catalog', 'tien', 'pg_temp' AS $$
DECLARE v text := nullif(btrim(current_setting('tien.actor', true)), '');
BEGIN
    IF v IS NULL OR char_length(v) > 200 OR v ~ '[[:cntrl:]]' THEN RAISE EXCEPTION 'ACTOR_REQUIRED'; END IF;
    RETURN v;
END $$;

CREATE OR REPLACE FUNCTION tien._actor_kind() RETURNS text
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path TO 'pg_catalog', 'tien', 'pg_temp' AS $$
DECLARE v text := current_setting('tien.actor_kind', true);
BEGIN
    IF v IS NULL OR v NOT IN ('human', 'machine') THEN RAISE EXCEPTION 'ACTOR_REQUIRED'; END IF;
    RETURN v;
END $$;

CREATE OR REPLACE FUNCTION tien._today() RETURNS date
LANGUAGE sql VOLATILE SECURITY DEFINER SET search_path TO 'pg_catalog', 'tien', 'pg_temp' AS $$
    SELECT (clock_timestamp() AT TIME ZONE 'Asia/Ho_Chi_Minh')::date
$$;

-- Payload phải là object, đủ khóa bắt buộc, không khóa lạ.
CREATE OR REPLACE FUNCTION tien._keys(p jsonb, p_required text[], p_optional text[]) RETURNS void
LANGUAGE plpgsql IMMUTABLE SECURITY DEFINER SET search_path TO 'pg_catalog', 'tien', 'pg_temp' AS $$
BEGIN
    IF jsonb_typeof(p) IS DISTINCT FROM 'object' THEN RAISE EXCEPTION 'INVALID_COMMAND'; END IF;
    IF NOT p ?& p_required OR EXISTS (SELECT 1 FROM jsonb_object_keys(p) k WHERE k <> ALL (p_required || p_optional)) THEN
        RAISE EXCEPTION 'INVALID_COMMAND';
    END IF;
END $$;

-- Mã đối tượng: số JSON nguyên dương.
CREATE OR REPLACE FUNCTION tien._id(v jsonb) RETURNS bigint
LANGUAGE plpgsql IMMUTABLE SECURITY DEFINER SET search_path TO 'pg_catalog', 'tien', 'pg_temp' AS $$
BEGIN
    IF jsonb_typeof(v) IS DISTINCT FROM 'number' OR v::text !~ '^[1-9][0-9]{0,17}$' THEN RAISE EXCEPTION 'INVALID_COMMAND'; END IF;
    RETURN v::text::bigint;
END $$;

-- Chữ: thiếu, null hay toàn khoảng trắng là NULL; không phải chuỗi, quá dài, có ký tự điều khiển thì từ chối.
CREATE OR REPLACE FUNCTION tien._text(v jsonb, p_max integer) RETURNS text
LANGUAGE plpgsql IMMUTABLE SECURITY DEFINER SET search_path TO 'pg_catalog', 'tien', 'pg_temp' AS $$
DECLARE t text;
BEGIN
    IF v IS NULL OR jsonb_typeof(v) = 'null' THEN RETURN NULL; END IF;
    IF jsonb_typeof(v) <> 'string' THEN RAISE EXCEPTION 'INVALID_COMMAND'; END IF;
    t := btrim(v #>> '{}');
    IF t = '' THEN RETURN NULL; END IF;
    IF char_length(t) > p_max OR t ~ '[[:cntrl:]]' THEN RAISE EXCEPTION 'INVALID_COMMAND'; END IF;
    RETURN t;
END $$;

-- Ngày 'YYYY-MM-DD'; thiếu hoặc null là NULL.
CREATE OR REPLACE FUNCTION tien._date(v jsonb) RETURNS date
LANGUAGE plpgsql IMMUTABLE SECURITY DEFINER SET search_path TO 'pg_catalog', 'tien', 'pg_temp' AS $$
BEGIN
    IF v IS NULL OR jsonb_typeof(v) = 'null' THEN RETURN NULL; END IF;
    IF jsonb_typeof(v) <> 'string' OR (v #>> '{}') !~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$'
       OR NOT pg_input_is_valid(v #>> '{}', 'date') THEN
        RAISE EXCEPTION 'INVALID_COMMAND';
    END IF;
    RETURN (v #>> '{}')::date;
END $$;

-- Tiền: chuỗi số nguyên (có dấu nếu p_signed), tối đa 18 chữ số; thiếu hoặc null là NULL (chưa biết, không phải 0).
CREATE OR REPLACE FUNCTION tien._minor(v jsonb, p_signed boolean) RETURNS bigint
LANGUAGE plpgsql IMMUTABLE SECURITY DEFINER SET search_path TO 'pg_catalog', 'tien', 'pg_temp' AS $$
BEGIN
    IF v IS NULL OR jsonb_typeof(v) = 'null' THEN RETURN NULL; END IF;
    IF jsonb_typeof(v) <> 'string'
       OR (v #>> '{}') !~ (CASE WHEN p_signed THEN '^(0|-?[1-9][0-9]{0,17})$' ELSE '^(0|[1-9][0-9]{0,17})$' END) THEN
        RAISE EXCEPTION 'INVALID_COMMAND';
    END IF;
    RETURN (v #>> '{}')::bigint;
END $$;

CREATE OR REPLACE FUNCTION tien._bool(v jsonb, p_default boolean) RETURNS boolean
LANGUAGE plpgsql IMMUTABLE SECURITY DEFINER SET search_path TO 'pg_catalog', 'tien', 'pg_temp' AS $$
BEGIN
    IF v IS NULL OR jsonb_typeof(v) = 'null' THEN RETURN p_default; END IF;
    IF jsonb_typeof(v) <> 'boolean' THEN RAISE EXCEPTION 'INVALID_COMMAND'; END IF;
    RETURN v::text::boolean;
END $$;

-- Mọi lệnh ghi: người làm và loại người làm trước tiên, rồi khóa lặp (chuỗi 1–128 ký tự, không ký tự điều khiển).
CREATE OR REPLACE FUNCTION tien._begin(p jsonb) RETURNS text
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path TO 'pg_catalog', 'tien', 'pg_temp' AS $$
DECLARE v text;
BEGIN
    PERFORM tien._actor();
    PERFORM tien._actor_kind();
    IF jsonb_typeof(p) IS DISTINCT FROM 'object' OR jsonb_typeof(p -> 'idempotency_key') IS DISTINCT FROM 'string' THEN
        RAISE EXCEPTION 'INVALID_COMMAND';
    END IF;
    v := p ->> 'idempotency_key';
    IF btrim(v) = '' OR char_length(v) > 128 OR v ~ '[[:cntrl:]]' THEN RAISE EXCEPTION 'INVALID_COMMAND'; END IF;
    RETURN v;
END $$;

-- Băm nội dung lệnh: bỏ khóa lặp và expected_version (F1 mục 8: gửi lại sau RESULT_UNKNOWN không thành lệnh mới); người làm
-- không nằm trong payload nên không vào băm.
CREATE OR REPLACE FUNCTION tien._hash(p jsonb) RETURNS text
LANGUAGE sql IMMUTABLE SECURITY DEFINER SET search_path TO 'pg_catalog', 'tien', 'pg_temp' AS $$
    SELECT encode(sha256(convert_to((p - 'idempotency_key' - 'expected_version')::text, 'UTF8')), 'hex')
$$;

-- Gọi sau khi đã khóa và kiểm vai: cùng khóa, cùng lệnh, cùng băm → kết quả cũ; khác → IDEMPOTENCY_CONFLICT; chưa có → NULL.
CREATE OR REPLACE FUNCTION tien._replay(p_scope text, p_command text, p jsonb) RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path TO 'pg_catalog', 'tien', 'pg_temp' AS $$
DECLARE r tien.idempotency;
BEGIN
    SELECT * INTO r FROM tien.idempotency WHERE scope = p_scope AND key = p ->> 'idempotency_key';
    IF NOT FOUND THEN RETURN NULL; END IF;
    IF r.command <> p_command OR r.request_hash <> tien._hash(p) THEN RAISE EXCEPTION 'IDEMPOTENCY_CONFLICT'; END IF;
    RETURN r.result;
END $$;

CREATE OR REPLACE FUNCTION tien._finish(p_scope text, p_command text, p jsonb, p_result jsonb) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path TO 'pg_catalog', 'tien', 'pg_temp' AS $$
BEGIN
    INSERT INTO tien.idempotency(scope, key, command, request_hash, result, actor)
    VALUES (p_scope, p ->> 'idempotency_key', p_command, tien._hash(p), p_result, tien._actor());
    RETURN p_result;
END $$;

CREATE OR REPLACE FUNCTION tien._event(p_kind text, p_entity bigint, p_account bigint, p_before jsonb, p_after jsonb, p_key text)
RETURNS bigint
LANGUAGE sql SECURITY DEFINER SET search_path TO 'pg_catalog', 'tien', 'pg_temp' AS $$
    INSERT INTO tien.event(legal_entity_id, account_id, kind, actor, actor_kind, "before", "after", idempotency_key)
    VALUES (p_entity, p_account, p_kind, tien._actor(), tien._actor_kind(), p_before, p_after, p_key)
    RETURNING id
$$;

-- Khóa dòng tài khoản trước mọi kiểm của lệnh; mọi lệnh ghi trên một tài khoản chạy lần lượt.
CREATE OR REPLACE FUNCTION tien._lock_account(p_account bigint) RETURNS tien.financial_account
LANGUAGE plpgsql SECURITY DEFINER SET search_path TO 'pg_catalog', 'tien', 'pg_temp' AS $$
DECLARE a tien.financial_account;
BEGIN
    SELECT * INTO a FROM tien.financial_account WHERE id = p_account FOR NO KEY UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION 'INVALID_COMMAND'; END IF;
    RETURN a;
END $$;

CREATE OR REPLACE FUNCTION tien._lock_entity(p_entity bigint) RETURNS tien.legal_entity
LANGUAGE plpgsql SECURITY DEFINER SET search_path TO 'pg_catalog', 'tien', 'pg_temp' AS $$
DECLARE e tien.legal_entity;
BEGIN
    SELECT * INTO e FROM tien.legal_entity WHERE id = p_entity FOR NO KEY UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION 'INVALID_COMMAND'; END IF;
    RETURN e;
END $$;

-- Có một trong các vai p_roles (NULL: vai bất kỳ) ở phạm vi: cấp đúng tài khoản, hoặc cấp cả pháp nhân (account_id NULL).
-- p_account NULL: chỉ cấp cả pháp nhân mới tính.
CREATE OR REPLACE FUNCTION tien._has_role(p_roles text[], p_entity bigint, p_account bigint) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path TO 'pg_catalog', 'tien', 'pg_temp' AS $$
    SELECT EXISTS (SELECT 1 FROM tien.access_grant g
                    WHERE g.login = tien._actor() AND g.revoked_event IS NULL AND (p_roles IS NULL OR g.role = ANY (p_roles))
                      AND (g.account_id = p_account OR (g.account_id IS NULL AND g.legal_entity_id = p_entity)))
$$;

-- Không có vai đúng ở phạm vi: có vai đó ở pháp nhân/tài khoản khác → ENTITY_SCOPE, không có ở đâu → TIEN_FORBIDDEN.
CREATE OR REPLACE FUNCTION tien._require(p_role text, p_entity bigint, p_account bigint) RETURNS void
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path TO 'pg_catalog', 'tien', 'pg_temp' AS $$
DECLARE v_roles text[] := CASE WHEN p_role IS NULL THEN NULL ELSE ARRAY[p_role] END;
BEGIN
    IF tien._has_role(v_roles, p_entity, p_account) THEN RETURN; END IF;
    IF EXISTS (SELECT 1 FROM tien.access_grant g WHERE g.login = tien._actor() AND g.revoked_event IS NULL
                AND (p_role IS NULL OR g.role = p_role)) THEN
        RAISE EXCEPTION 'ENTITY_SCOPE';
    END IF;
    RAISE EXCEPTION 'TIEN_FORBIDDEN';
END $$;

-- Phân bổ hiệu lực của một giao dịch, dạng ghi vào vết (khuôn I-5).
CREATE OR REPLACE FUNCTION tien._allocations(p_tx bigint) RETURNS jsonb
LANGUAGE sql STABLE SECURITY DEFINER SET search_path TO 'pg_catalog', 'tien', 'pg_temp' AS $$
    SELECT coalesce(jsonb_agg(jsonb_build_object('id', l.id, 'target_kind', l.target_kind, 'target_ref', l.target_ref,
                                                 'amount_minor', l.amount_minor::text, 'note', l.note) ORDER BY l.id), '[]'::jsonb)
      FROM tien.allocation l WHERE l.bank_transaction_id = p_tx AND l.superseded_event IS NULL
$$;

CREATE OR REPLACE FUNCTION tien._tx_state(p_tx bigint) RETURNS jsonb
LANGUAGE sql STABLE SECURITY DEFINER SET search_path TO 'pg_catalog', 'tien', 'pg_temp' AS $$
    SELECT jsonb_build_object('transaction_id', t.id, 'version', t.version, 'direction', t.direction,
                              'amount_minor', t.amount_minor::text, 'allocated_minor', t.allocated_minor::text,
                              'unallocated_minor', (t.amount_minor - t.allocated_minor)::text, 'status', t.status,
                              'allocations', tien._allocations(t.id))
      FROM tien.v_transaction t WHERE t.id = p_tx
$$;

-- Bất biến của một tài khoản, kiểm cuối mỗi lệnh đổi giao dịch/nguồn/phân bổ:
-- I-4 Σ phân bổ hiệu lực ≤ số tiền, giao dịch đã hủy không còn phân bổ hiệu lực; I-5 mỗi dòng phân bổ có trong vết tạo và vết thay;
-- I-6 giao dịch hiệu lực ⇔ còn nguồn ở lô đã commit, mỗi giao dịch đúng một nguồn origin, mỗi dòng gốc của lô đã commit/hủy đúng
-- một nguồn. I-8 (cùng tài khoản, tiền tệ) do khóa ngoại ghép giữ.
CREATE OR REPLACE FUNCTION tien._check_account(p_account bigint) RETURNS void
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path TO 'pg_catalog', 'tien', 'pg_temp' AS $$
BEGIN
    IF EXISTS (SELECT 1 FROM tien.bank_transaction t JOIN tien.allocation l ON l.bank_transaction_id = t.id AND l.superseded_event IS NULL
                WHERE t.account_id = p_account GROUP BY t.id, t.amount_minor, t.voided_event
               HAVING sum(l.amount_minor) > t.amount_minor OR t.voided_event IS NOT NULL) THEN
        RAISE EXCEPTION 'ALLOCATION_INVARIANT';
    END IF;
    IF EXISTS (SELECT 1 FROM tien.allocation l JOIN tien.event e ON e.id = l.created_event
                CROSS JOIN LATERAL (SELECT jsonb_build_array(jsonb_build_object('id', l.id, 'target_kind', l.target_kind,
                    'target_ref', l.target_ref, 'amount_minor', l.amount_minor::text, 'note', l.note)) AS me) x
                WHERE l.account_id = p_account
                  AND (e.kind <> 'allocation_set' OR e.account_id IS DISTINCT FROM l.account_id
                       OR (e."after" ->> 'transaction')::bigint IS DISTINCT FROM l.bank_transaction_id
                       OR NOT coalesce((e."after" -> 'allocations') @> x.me, false)
                       OR (l.superseded_event IS NOT NULL AND NOT EXISTS (
                           SELECT 1 FROM tien.event s WHERE s.id = l.superseded_event AND s.kind = 'allocation_set'
                              AND (s."before" ->> 'transaction')::bigint = l.bank_transaction_id
                              AND coalesce((s."before" -> 'allocations') @> x.me, false))))) THEN
        RAISE EXCEPTION 'ALLOCATION_EVENT_INVARIANT';
    END IF;
    IF EXISTS (SELECT 1 FROM tien.bank_transaction t WHERE t.account_id = p_account
                AND ((t.voided_event IS NULL) <> EXISTS (SELECT 1 FROM tien.bank_transaction_source s
                                                           JOIN tien.statement_import i ON i.id = s.import_id
                                                          WHERE s.bank_transaction_id = t.id AND i.status = 'committed')
                     OR NOT EXISTS (SELECT 1 FROM tien.bank_transaction_source s WHERE s.bank_transaction_id = t.id AND s.role = 'origin')))
       OR EXISTS (SELECT 1 FROM tien.statement_import i WHERE i.account_id = p_account AND i.status IN ('committed', 'voided')
                     AND (SELECT count(*) FROM tien.raw_statement_line r WHERE r.import_id = i.id)
                         <> (SELECT count(*) FROM tien.bank_transaction_source s WHERE s.import_id = i.id)) THEN
        RAISE EXCEPTION 'SOURCE_INVARIANT';
    END IF;
END $$;

-- ---------------------------------------------------------------------------------------------------------------------------
-- StatementLine v1 (F1 mục 5.1): kiểm cấu trúc, sai thì từ chối cả lệnh. Giá trị chiều, số tiền, tiền tệ, ngày sai là lỗi dòng
-- (phân loại bên dưới), không phải lỗi lệnh.
CREATE OR REPLACE FUNCTION tien._check_lines(p jsonb) RETURNS void
LANGUAGE plpgsql IMMUTABLE SECURITY DEFINER SET search_path TO 'pg_catalog', 'tien', 'pg_temp' AS $$
BEGIN
    IF jsonb_typeof(p) IS DISTINCT FROM 'array' THEN RAISE EXCEPTION 'INVALID_COMMAND'; END IF;
    IF jsonb_array_length(p) > 20000 THEN RAISE EXCEPTION 'INVALID_COMMAND'; END IF;
    IF EXISTS (SELECT 1 FROM jsonb_array_elements(p) x(e) WHERE CASE WHEN jsonb_typeof(e) <> 'object' THEN true ELSE
            NOT e ?& ARRAY['line_no', 'booking_date', 'direction', 'amount_minor', 'currency', 'cells']
            OR EXISTS (SELECT 1 FROM jsonb_object_keys(e) k WHERE k NOT IN ('line_no', 'booking_date', 'value_date', 'direction',
                       'amount_minor', 'currency', 'description', 'bank_ref', 'balance_after_minor', 'cells'))
            OR jsonb_typeof(e -> 'line_no') <> 'number' OR (e ->> 'line_no') !~ '^[1-9][0-9]{0,8}$'
            OR jsonb_typeof(e -> 'booking_date') <> 'string' OR (e ->> 'booking_date') !~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$'
            OR NOT pg_input_is_valid(e ->> 'booking_date', 'date')
            OR coalesce(jsonb_typeof(e -> 'value_date'), 'null') NOT IN ('string', 'null')
            OR (jsonb_typeof(e -> 'value_date') = 'string' AND ((e ->> 'value_date') !~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$'
                                                                OR NOT pg_input_is_valid(e ->> 'value_date', 'date')))
            OR jsonb_typeof(e -> 'direction') NOT IN ('string', 'null')
            OR jsonb_typeof(e -> 'amount_minor') NOT IN ('string', 'null')
            OR jsonb_typeof(e -> 'currency') NOT IN ('string', 'null')
            OR coalesce(jsonb_typeof(e -> 'description'), 'null') NOT IN ('string', 'null')
            OR coalesce(char_length(e ->> 'description'), 0) > 1000
            OR coalesce(jsonb_typeof(e -> 'bank_ref'), 'null') NOT IN ('string', 'null')
            OR coalesce(char_length(e ->> 'bank_ref'), 0) > 100
            OR coalesce(jsonb_typeof(e -> 'balance_after_minor'), 'null') NOT IN ('string', 'null')
            OR coalesce((e ->> 'balance_after_minor') !~ '^(0|-?[1-9][0-9]{0,17})$', false)
            OR CASE WHEN jsonb_typeof(e -> 'cells') <> 'object' THEN true
                    ELSE EXISTS (SELECT 1 FROM jsonb_each(e -> 'cells') c WHERE jsonb_typeof(c.value) NOT IN ('string', 'null')) END
        END) THEN
        RAISE EXCEPTION 'INVALID_COMMAND';
    END IF;
END $$;

-- Phân loại dòng (spec mục "Phân loại dòng"): MỘT hàm cho cả xem trước và commit. Trả mỗi dòng (theo thứ tự trong lô) lớp
-- new/duplicate/suspect/error, mã lỗi, ứng viên, ứng viên mềm của bước 4b (soft_candidates), dấu vân; các chỗ gãy chuỗi số dư và
-- giao dịch đã có trong kỳ mà file không nhận (UNMATCHED_EXISTING); toàn bộ U (pool) cho commit; số đếm; preview_hash.
CREATE OR REPLACE FUNCTION tien._classify(p_account bigint, p_template text, p_from date, p_to date, p_opening bigint,
                                          p_closing bigint, p_today date, p_lines jsonb) RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path TO 'pg_catalog', 'tien', 'pg_temp' AS $$
DECLARE v_acc tien.financial_account; v_open tien.account_opening; v_expected bigint; v_start bigint; v_sum bigint;
        v_closing bigint; v_lines jsonb; v_running jsonb; v_unmatched jsonb; v_pool jsonb; v_breaks jsonb := '[]'::jsonb; v_chain integer;
        v_counts jsonb; v_hash text;
BEGIN
    SELECT * INTO v_acc FROM tien.financial_account WHERE id = p_account;
    SELECT * INTO v_open FROM tien.account_opening WHERE account_id = p_account;
    IF NOT FOUND THEN RAISE EXCEPTION 'NO_OPENING'; END IF;
    -- Số dư đầu kỳ vọng: số dư mở + giao dịch hiệu lực có ngày ghi sổ trước period_from.
    SELECT (v_open.amount_minor + coalesce(sum(CASE t.direction WHEN 'in' THEN t.amount_minor ELSE -t.amount_minor END), 0))::bigint
      INTO v_expected FROM tien.bank_transaction t
     WHERE t.account_id = p_account AND t.voided_event IS NULL AND t.booking_date < p_from;
    v_start := coalesce(p_opening, v_expected);
    WITH raw AS (
        SELECT x.ord::integer AS seq, (x.e ->> 'line_no')::integer AS line_no, (x.e ->> 'booking_date')::date AS bdate,
               x.e ->> 'direction' AS dir, x.e ->> 'amount_minor' AS amt, x.e ->> 'currency' AS cur, x.e ->> 'description' AS descr,
               nullif(btrim(x.e ->> 'bank_ref'), '') AS ref, (x.e ->> 'balance_after_minor')::bigint AS bal
          FROM jsonb_array_elements(p_lines) WITH ORDINALITY x(e, ord)
    ), checked AS (
        -- 1. Kiểm dòng.
        SELECT r.*, CASE
                   WHEN count(*) OVER (PARTITION BY r.line_no) > 1 THEN 'LINE_DUPLICATE_NO'
                   WHEN r.bdate > p_today THEN 'LINE_FUTURE_DATE'
                   WHEN r.bdate < p_from OR r.bdate > p_to THEN 'LINE_OUT_OF_PERIOD'
                   WHEN r.bdate < v_open.as_of THEN 'LINE_BEFORE_OPENING'
                   WHEN r.dir IS NULL OR r.dir NOT IN ('in', 'out') THEN 'LINE_DIRECTION'
                   WHEN r.amt IS NULL OR r.amt !~ '^[1-9][0-9]{0,18}$'
                        OR (length(r.amt) = 19 AND r.amt COLLATE "C" > '9223372036854775807') THEN 'LINE_AMOUNT'
                   WHEN r.cur IS DISTINCT FROM v_acc.currency THEN 'LINE_CURRENCY'
               END AS code
          FROM raw r
    ), valid AS (
        -- 2. Dấu vân: tài khoản | ngày ghi sổ | chiều | số tiền | mô tả chuẩn hóa (NFC, bỏ khoảng trắng đầu cuối, gộp khoảng trắng,
        -- chữ thường theo bảng Unicode dựng sẵn của PostgreSQL, không theo locale máy). Không gồm số dư sau. Biểu thức chính quy
        -- dùng lớp POSIX, không dấu gạch chéo, để không đổi theo standard_conforming_strings của phiên gọi.
        SELECT c.seq, c.line_no, c.bdate, c.dir, c.amt, c.bal, c.ref,
               CASE c.dir WHEN 'in' THEN c.amt::bigint ELSE -(c.amt::bigint) END AS signed,
               encode(sha256(convert_to(concat_ws('|', p_account::text, to_char(c.bdate, 'YYYY-MM-DD'), c.dir, c.amt,
                   lower(regexp_replace(regexp_replace(normalize(coalesce(c.descr, ''), NFC) COLLATE pg_c_utf8,
                                                       '^[[:space:]]+|[[:space:]]+$', '', 'g'), '[[:space:]]+', ' ', 'g'))),
                                        'UTF8')), 'hex') AS fp,
               (v_acc.bank_ref_stable AND c.ref IS NOT NULL) AS by_ref
          FROM checked c WHERE c.code IS NULL
    ), ref_lines AS (
        -- 3. Mã ngân hàng ổn định: trùng nếu đã có giao dịch hiệu lực cùng (tài khoản, họ nguồn, mã) VÀ cùng ngày ghi sổ, chiều, số
        -- tiền; nhiều dòng cùng khóa ghép lần lượt. Cùng mã mà khác ngày/chiều/số tiền (ngân hàng dùng lại mã) không phải trùng: dòng
        -- là new rồi qua bước 4b, để không bỏ mất tiền khi ứng viên theo mã nằm ngoài kỳ (review độc lập 24/11/2026, mức TB).
        SELECT v.seq, v.ref, v.bdate, v.dir, v.amt::bigint AS amount,
               row_number() OVER (PARTITION BY v.ref, v.bdate, v.dir, v.amt ORDER BY v.line_no) AS k
          FROM valid v WHERE v.by_ref
    ), ref_tx AS (
        SELECT t.bank_ref, t.booking_date, t.direction, t.amount_minor, t.id,
               row_number() OVER (PARTITION BY t.bank_ref, t.booking_date, t.direction, t.amount_minor ORDER BY t.id) AS k
          FROM tien.bank_transaction t
         WHERE t.account_id = p_account AND t.voided_event IS NULL AND t.source_family = split_part(p_template, '@', 1)
           AND t.bank_ref IN (SELECT rl.ref FROM ref_lines rl)
    ), ref_match AS (
        SELECT rl.seq, rt.id AS cand
          FROM ref_lines rl LEFT JOIN ref_tx rt ON rt.bank_ref = rl.ref AND rt.booking_date = rl.bdate AND rt.direction = rl.dir
                                                AND rt.amount_minor = rl.amount AND rt.k = rl.k
    ), fp_lines AS (
        -- 4. Còn lại theo dấu vân: E giao dịch hiệu lực (theo id), F dòng (theo line_no); min(E, F) dòng đầu trùng giao dịch thứ k,
        -- F − E dòng còn lại nghi trùng; E = 0 thì mọi dòng mới. Giao dịch đã là ứng viên theo mã ở bước 3 không tính lại (BR-IM6).
        SELECT v.seq, v.fp, row_number() OVER (PARTITION BY v.fp ORDER BY v.line_no) AS k FROM valid v WHERE NOT v.by_ref
    ), fp_tx AS (
        SELECT t.fingerprint, t.id, row_number() OVER (PARTITION BY t.fingerprint ORDER BY t.id) AS k
          FROM tien.bank_transaction t
         WHERE t.account_id = p_account AND t.voided_event IS NULL AND t.fingerprint IN (SELECT fl.fp FROM fp_lines fl)
           AND t.id NOT IN (SELECT rm.cand FROM ref_match rm WHERE rm.cand IS NOT NULL)
    ), matched AS (
        SELECT rm.seq, CASE WHEN rm.cand IS NULL THEN 'new' ELSE 'duplicate' END AS klass, rm.cand FROM ref_match rm
        UNION ALL
        SELECT fl.seq, CASE WHEN ft.id IS NOT NULL THEN 'duplicate'
                            WHEN EXISTS (SELECT 1 FROM fp_tx f2 WHERE f2.fingerprint = fl.fp) THEN 'suspect' ELSE 'new' END,
               ft.id
          FROM fp_lines fl LEFT JOIN fp_tx ft ON ft.fingerprint = fl.fp AND ft.k = fl.k
    ), pool AS (
        -- 4b. U: giao dịch hiệu lực có ngày ghi sổ trong kỳ, chưa là ứng viên của dòng nào ở bước 3–4. Dòng đang new được ghép mềm với
        -- giao dịch U cùng ngày ghi sổ, chiều, số tiền (mô tả có thể đã đổi giữa hai lần tải), trừ khi cả dòng lẫn giao dịch đều có mã
        -- ngân hàng ổn định (mã khác là giao dịch khác). Nhóm dòng (ngày, chiều, số tiền, có mã) có F dòng, E giao dịch U ghép được:
        -- F ≤ E thì dòng thứ k nhận giao dịch thứ k; F > E thì mọi dòng của nhóm là suspect với cả E giao dịch làm ứng viên, không gán
        -- theo thứ tự. Giao dịch U không là ứng viên mềm của dòng nào → gãy UNMATCHED_EXISTING. Commit phải phủ cả U (mục commit).
        SELECT t.id, t.booking_date, t.direction, t.amount_minor, t.bank_ref IS NOT NULL AS has_ref
          FROM tien.bank_transaction t
         WHERE t.account_id = p_account AND t.voided_event IS NULL AND t.booking_date BETWEEN p_from AND p_to
           AND t.id NOT IN (SELECT m.cand FROM matched m WHERE m.cand IS NOT NULL)
    ), fresh AS (
        SELECT v.seq, v.bdate, v.dir, v.amt::bigint AS amount, v.by_ref,
               row_number() OVER (PARTITION BY v.bdate, v.dir, v.amt, v.by_ref ORDER BY v.line_no) AS k,
               count(*) OVER (PARTITION BY v.bdate, v.dir, v.amt, v.by_ref) AS f
          FROM valid v JOIN matched m ON m.seq = v.seq WHERE m.klass = 'new'
    ), elig AS (
        SELECT fr.seq, fr.k, fr.f, u.id, row_number() OVER (PARTITION BY fr.seq ORDER BY u.id) AS r, count(*) OVER (PARTITION BY fr.seq) AS e
          FROM fresh fr JOIN pool u ON u.booking_date = fr.bdate AND u.direction = fr.dir AND u.amount_minor = fr.amount
                                   AND NOT (fr.by_ref AND u.has_ref)
    ), soft AS (
        SELECT el.seq, max(el.id) FILTER (WHERE el.f <= el.e AND el.r = el.k) AS cand,
               CASE WHEN max(el.f) <= max(el.e) THEN array_agg(el.id ORDER BY el.id) FILTER (WHERE el.r = el.k)
                    ELSE array_agg(el.id ORDER BY el.id) END AS ids
          FROM elig el GROUP BY el.seq
    ), classified AS (
        SELECT c.seq, c.line_no, c.code,
               CASE WHEN c.code IS NOT NULL THEN 'error' WHEN s.seq IS NOT NULL THEN 'suspect' ELSE m.klass END AS klass,
               coalesce(s.cand, m.cand) AS cand, s.ids AS soft_ids, v.fp
          FROM checked c LEFT JOIN matched m ON m.seq = c.seq LEFT JOIN valid v ON v.seq = c.seq LEFT JOIN soft s ON s.seq = c.seq
    ), run AS (
        -- 5. Số dư sau: đi theo line_no từ số dư đầu (của file, không có thì kỳ vọng) qua mọi dòng hợp lệ.
        SELECT v.line_no, v.bal, (v_start + sum(v.signed) OVER (ORDER BY v.line_no))::bigint AS running FROM valid v
    )
    SELECT (SELECT coalesce(jsonb_agg(jsonb_build_object('seq', seq, 'line_no', line_no, 'class', klass, 'code', code,
                                                         'candidate', cand, 'soft_candidates', soft_ids, 'fp', fp) ORDER BY seq), '[]'::jsonb)
              FROM classified),
           (SELECT coalesce(jsonb_agg(jsonb_build_object('code', 'RUNNING_BALANCE', 'line_no', line_no,
                                                         'expected_minor', running::text, 'actual_minor', bal::text)
                                      ORDER BY line_no), '[]'::jsonb)
              FROM run WHERE bal IS NOT NULL AND bal <> running),
           (SELECT coalesce(sum(signed), 0)::bigint FROM valid),
           (SELECT coalesce(jsonb_agg(jsonb_build_object('code', 'UNMATCHED_EXISTING', 'transaction_id', u.id,
                                                         'booking_date', u.booking_date, 'direction', u.direction,
                                                         'amount_minor', u.amount_minor::text) ORDER BY u.id), '[]'::jsonb)
              FROM pool u WHERE NOT EXISTS (SELECT 1 FROM soft s WHERE u.id = ANY (s.ids))),
           (SELECT coalesce(jsonb_agg(u.id ORDER BY u.id), '[]'::jsonb) FROM pool u)
      INTO v_lines, v_running, v_sum, v_unmatched, v_pool;
    IF p_opening IS NOT NULL AND p_opening <> v_expected THEN
        v_breaks := v_breaks || jsonb_build_array(jsonb_build_object('code', 'OPENING_MISMATCH', 'expected_minor', v_expected::text,
                                                                     'actual_minor', p_opening::text));
    END IF;
    v_breaks := v_breaks || v_running;
    v_closing := v_start + v_sum;
    IF p_closing IS NOT NULL AND p_closing <> v_closing THEN
        v_breaks := v_breaks || jsonb_build_array(jsonb_build_object('code', 'CLOSING_MISMATCH', 'expected_minor', v_closing::text,
                                                                     'actual_minor', p_closing::text));
    END IF;
    v_chain := jsonb_array_length(v_breaks);
    v_breaks := v_breaks || v_unmatched;
    SELECT jsonb_build_object('rows', count(*), 'new', count(*) FILTER (WHERE x ->> 'class' = 'new'),
                              'duplicate', count(*) FILTER (WHERE x ->> 'class' = 'duplicate'),
                              'suspect', count(*) FILTER (WHERE x ->> 'class' = 'suspect'),
                              'error', count(*) FILTER (WHERE x ->> 'class' = 'error'))
      INTO v_counts FROM jsonb_array_elements(v_lines) x;
    -- 6. preview_hash: lớp + ứng viên + ứng viên mềm từng dòng, các chỗ gãy (kể cả U còn lại), toàn bộ U, version tài khoản.
    v_hash := encode(sha256(convert_to(jsonb_build_object(
        'lines', (SELECT coalesce(jsonb_agg(jsonb_build_array(x -> 'seq', x -> 'class', x -> 'candidate', x -> 'soft_candidates')
                                            ORDER BY (x ->> 'seq')::integer), '[]'::jsonb) FROM jsonb_array_elements(v_lines) x),
        'breaks', v_breaks, 'pool', v_pool, 'version', v_acc.version)::text, 'UTF8')), 'hex');
    RETURN jsonb_build_object('lines', v_lines, 'breaks', v_breaks, 'pool', v_pool, 'counts', v_counts, 'hash', v_hash,
        'version', v_acc.version,
        'balance', jsonb_build_object('opening_minor', p_opening::text, 'expected_opening_minor', v_expected::text,
                                      'closing_minor', p_closing::text, 'computed_closing_minor', v_closing::text,
                                      'chain_breaks', v_chain, 'unmatched_existing', jsonb_array_length(v_unmatched)));
EXCEPTION WHEN numeric_value_out_of_range THEN RAISE EXCEPTION 'INVALID_COMMAND';
END $$;

-- ---------------------------------------------------------------------------------------------------------------------------
-- Hàm lệnh (cấp cho tien_app). Thứ tự chung: người làm, khóa lặp, hình dạng payload → khóa dòng → vai → khóa lặp đã có → kiểm
-- trạng thái, nội dung → vết → ghi → bất biến → lưu khóa lặp.

CREATE OR REPLACE FUNCTION tien.create_legal_entity(p jsonb) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path TO 'pg_catalog', 'tien', 'pg_temp' AS $$
DECLARE v_key text := tien._begin(p); v_retry jsonb; v_code text; v_name text; v_id bigint; v_event bigint;
BEGIN
    PERFORM tien._keys(p, ARRAY['idempotency_key', 'code', 'name'], '{}');
    PERFORM pg_advisory_xact_lock(hashtext('tien'), hashtext('legal_entity'));
    IF NOT EXISTS (SELECT 1 FROM tien.access_grant g WHERE g.login = tien._actor() AND g.role = 'tien_quan_tri'
                    AND g.revoked_event IS NULL) THEN
        RAISE EXCEPTION 'TIEN_FORBIDDEN';
    END IF;
    v_retry := tien._replay('global', 'create_legal_entity', p);
    IF v_retry IS NOT NULL THEN RETURN v_retry; END IF;
    v_code := tien._text(p -> 'code', 32);
    v_name := tien._text(p -> 'name', 200);
    IF v_code IS NULL OR v_code !~ '^[A-Z0-9][A-Z0-9_-]{1,31}$' OR v_name IS NULL
       OR EXISTS (SELECT 1 FROM tien.legal_entity WHERE code = v_code) THEN
        RAISE EXCEPTION 'INVALID_COMMAND';
    END IF;
    v_id := nextval(pg_get_serial_sequence('tien.legal_entity', 'id'));
    v_event := tien._event('entity_create', v_id, NULL, '{}',
        jsonb_build_object('legal_entity', jsonb_build_object('id', v_id, 'code', v_code, 'name', v_name, 'status', 'active')), v_key);
    INSERT INTO tien.legal_entity(id, code, name, created_event) OVERRIDING SYSTEM VALUE VALUES (v_id, v_code, v_name, v_event);
    RETURN tien._finish('global', 'create_legal_entity', p, jsonb_build_object('legal_entity_id', v_id, 'code', v_code));
END $$;

CREATE OR REPLACE FUNCTION tien.create_account(p jsonb) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path TO 'pg_catalog', 'tien', 'pg_temp' AS $$
DECLARE v_key text := tien._begin(p); v_ent tien.legal_entity; v_scope text; v_retry jsonb; v_id bigint; v_event bigint;
        v_kind text; v_bank text; v_last4 text; v_hmac text; v_cur text; v_holder text; v_tpl text; v_stable boolean; v_row jsonb;
BEGIN
    PERFORM tien._keys(p, ARRAY['idempotency_key', 'legal_entity_id', 'kind', 'account_hmac', 'currency', 'holder'],
                       ARRAY['bank_code', 'account_last4', 'statement_template', 'bank_ref_stable']);
    v_ent := tien._lock_entity(tien._id(p -> 'legal_entity_id'));
    PERFORM tien._require('tien_quan_tri', v_ent.id, NULL);
    v_scope := 'entity:' || v_ent.id;
    v_retry := tien._replay(v_scope, 'create_account', p);
    IF v_retry IS NOT NULL THEN RETURN v_retry; END IF;
    v_kind := tien._text(p -> 'kind', 10);
    v_bank := tien._text(p -> 'bank_code', 16);
    v_last4 := tien._text(p -> 'account_last4', 4);
    v_hmac := tien._text(p -> 'account_hmac', 64);
    v_cur := tien._text(p -> 'currency', 3);
    v_holder := tien._text(p -> 'holder', 10);
    v_tpl := tien._text(p -> 'statement_template', 45);
    v_stable := tien._bool(p -> 'bank_ref_stable', false);
    IF v_kind IS NULL OR v_kind NOT IN ('bank', 'cash') OR v_holder IS NULL OR v_holder NOT IN ('company', 'personal')
       OR v_hmac IS NULL OR v_hmac !~ '^[0-9a-f]{64}$' OR coalesce(v_bank !~ '^[A-Z0-9]{2,16}$', false)
       OR coalesce(v_last4 !~ '^[0-9]{4}$', false) OR (v_kind = 'bank' AND (v_bank IS NULL OR v_last4 IS NULL))
       OR coalesce(v_tpl !~ '^[a-z0-9][a-z0-9_-]{0,39}@[1-9][0-9]{0,3}$', false)
       OR (v_stable AND v_tpl IS NULL)  -- mã ngân hàng chỉ là khóa khi gắn đúng một mẫu file (họ nguồn)
       OR NOT EXISTS (SELECT 1 FROM tien.currency WHERE code = v_cur) THEN
        RAISE EXCEPTION 'INVALID_COMMAND';
    END IF;
    IF EXISTS (SELECT 1 FROM tien.financial_account WHERE legal_entity_id = v_ent.id AND account_hmac = v_hmac AND currency = v_cur) THEN
        RAISE EXCEPTION 'DUPLICATE_ACCOUNT';
    END IF;
    v_id := nextval(pg_get_serial_sequence('tien.financial_account', 'id'));
    v_row := jsonb_build_object('id', v_id, 'legal_entity_id', v_ent.id, 'kind', v_kind, 'bank_code', v_bank, 'account_last4', v_last4,
        'account_hmac', v_hmac, 'currency', v_cur, 'holder', v_holder, 'statement_template', v_tpl, 'bank_ref_stable', v_stable,
        'version', 0);
    v_event := tien._event('account_create', v_ent.id, v_id, '{}', jsonb_build_object('account', v_row), v_key);
    INSERT INTO tien.financial_account(id, legal_entity_id, kind, bank_code, account_last4, account_hmac, currency, holder,
                                       statement_template, bank_ref_stable, created_event)
    OVERRIDING SYSTEM VALUE VALUES (v_id, v_ent.id, v_kind, v_bank, v_last4, v_hmac, v_cur, v_holder, v_tpl, v_stable, v_event);
    RETURN tien._finish(v_scope, 'create_account', p, jsonb_build_object('account_id', v_id, 'version', 0));
END $$;

CREATE OR REPLACE FUNCTION tien.set_opening(p jsonb) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path TO 'pg_catalog', 'tien', 'pg_temp' AS $$
DECLARE v_key text := tien._begin(p); v_acc tien.financial_account; v_scope text; v_retry jsonb; v_as_of date; v_amount bigint;
        v_note text; v_event bigint;
BEGIN
    PERFORM tien._keys(p, ARRAY['idempotency_key', 'account_id', 'as_of', 'amount_minor', 'evidence_note'], '{}');
    v_acc := tien._lock_account(tien._id(p -> 'account_id'));
    PERFORM tien._require('tien_quan_tri', v_acc.legal_entity_id, v_acc.id);
    v_scope := 'account:' || v_acc.id;
    v_retry := tien._replay(v_scope, 'set_opening', p);
    IF v_retry IS NOT NULL THEN RETURN v_retry; END IF;
    IF EXISTS (SELECT 1 FROM tien.account_opening WHERE account_id = v_acc.id) THEN RAISE EXCEPTION 'OPENING_EXISTS'; END IF;
    v_as_of := tien._date(p -> 'as_of');
    v_amount := tien._minor(p -> 'amount_minor', true);
    v_note := tien._text(p -> 'evidence_note', 500);
    IF v_as_of IS NULL OR v_as_of > tien._today() OR v_amount IS NULL OR v_note IS NULL THEN RAISE EXCEPTION 'INVALID_COMMAND'; END IF;
    v_event := tien._event('opening_set', v_acc.legal_entity_id, v_acc.id, '{}', jsonb_build_object('opening', jsonb_build_object(
        'account_id', v_acc.id, 'as_of', v_as_of, 'amount_minor', v_amount::text, 'evidence_note', v_note)), v_key);
    INSERT INTO tien.account_opening(account_id, as_of, amount_minor, evidence_note, created_event)
    VALUES (v_acc.id, v_as_of, v_amount, v_note, v_event);
    RETURN tien._finish(v_scope, 'set_opening', p, jsonb_build_object('account_id', v_acc.id, 'as_of', v_as_of,
                                                                      'amount_minor', v_amount::text));
END $$;

-- Cấp vai: cần tien_quan_tri của cả pháp nhân; không cấp cho chính mình. Cấp lại đúng vai đang hiệu lực thì không ghi gì.
CREATE OR REPLACE FUNCTION tien.grant_role(p jsonb) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path TO 'pg_catalog', 'tien', 'pg_temp' AS $$
DECLARE v_key text := tien._begin(p); v_ent tien.legal_entity; v_scope text; v_retry jsonb; v_login text; v_role text;
        v_account bigint; v_id bigint; v_event bigint; v_row jsonb;
BEGIN
    PERFORM tien._keys(p, ARRAY['idempotency_key', 'login', 'role', 'legal_entity_id'], ARRAY['account_id']);
    v_ent := tien._lock_entity(tien._id(p -> 'legal_entity_id'));
    PERFORM tien._require('tien_quan_tri', v_ent.id, NULL);
    v_scope := 'entity:' || v_ent.id;
    v_retry := tien._replay(v_scope, 'grant_role', p);
    IF v_retry IS NOT NULL THEN RETURN v_retry; END IF;
    v_login := tien._text(p -> 'login', 200);
    v_role := tien._text(p -> 'role', 20);
    v_account := CASE WHEN coalesce(jsonb_typeof(p -> 'account_id'), 'null') <> 'null' THEN tien._id(p -> 'account_id') END;
    IF v_login IS NULL OR v_login !~ '^[^[:space:][:cntrl:]]{1,200}$' OR v_role IS NULL
       OR v_role NOT IN ('tien_xem', 'tien_nhap', 'tien_phan_bo', 'tien_review', 'tien_quan_tri')
       OR (v_account IS NOT NULL AND NOT EXISTS (SELECT 1 FROM tien.financial_account WHERE id = v_account AND legal_entity_id = v_ent.id)) THEN
        RAISE EXCEPTION 'INVALID_COMMAND';
    END IF;
    IF v_login = tien._actor() THEN RAISE EXCEPTION 'SELF_GRANT'; END IF;
    SELECT id INTO v_id FROM tien.access_grant WHERE login = v_login AND role = v_role AND legal_entity_id = v_ent.id
       AND account_id IS NOT DISTINCT FROM v_account AND revoked_event IS NULL;
    IF FOUND THEN
        RETURN tien._finish(v_scope, 'grant_role', p, jsonb_build_object('grant_id', v_id, 'unchanged', true));
    END IF;
    v_id := nextval(pg_get_serial_sequence('tien.access_grant', 'id'));
    v_row := jsonb_build_object('id', v_id, 'login', v_login, 'role', v_role, 'legal_entity_id', v_ent.id, 'account_id', v_account,
                                'revoked', false);
    v_event := tien._event('grant', v_ent.id, v_account, '{}', jsonb_build_object('grant', v_row), v_key);
    INSERT INTO tien.access_grant(id, login, role, legal_entity_id, account_id, created_event)
    OVERRIDING SYSTEM VALUE VALUES (v_id, v_login, v_role, v_ent.id, v_account, v_event);
    RETURN tien._finish(v_scope, 'grant_role', p, jsonb_build_object('grant_id', v_id, 'unchanged', false));
END $$;

CREATE OR REPLACE FUNCTION tien.revoke_role(p jsonb) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path TO 'pg_catalog', 'tien', 'pg_temp' AS $$
DECLARE v_key text := tien._begin(p); v_grant tien.access_grant; v_ent tien.legal_entity; v_scope text; v_retry jsonb;
        v_reason text; v_event bigint; v_row jsonb;
BEGIN
    PERFORM tien._keys(p, ARRAY['idempotency_key', 'grant_id'], ARRAY['reason']);
    SELECT * INTO v_grant FROM tien.access_grant WHERE id = tien._id(p -> 'grant_id');
    IF NOT FOUND THEN RAISE EXCEPTION 'INVALID_COMMAND'; END IF;
    v_ent := tien._lock_entity(v_grant.legal_entity_id);
    PERFORM tien._require('tien_quan_tri', v_ent.id, NULL);
    v_scope := 'entity:' || v_ent.id;
    v_retry := tien._replay(v_scope, 'revoke_role', p);
    IF v_retry IS NOT NULL THEN RETURN v_retry; END IF;
    SELECT * INTO v_grant FROM tien.access_grant WHERE id = v_grant.id;
    v_reason := tien._text(p -> 'reason', 500);
    IF v_grant.revoked_event IS NOT NULL THEN RAISE EXCEPTION 'INVALID_COMMAND'; END IF;
    IF v_grant.login = tien._actor() THEN RAISE EXCEPTION 'SELF_GRANT'; END IF;
    v_row := jsonb_build_object('id', v_grant.id, 'login', v_grant.login, 'role', v_grant.role, 'legal_entity_id', v_grant.legal_entity_id,
                                'account_id', v_grant.account_id);
    v_event := tien._event('revoke', v_ent.id, v_grant.account_id, jsonb_build_object('grant', v_row || '{"revoked": false}'),
                           jsonb_build_object('grant', v_row || '{"revoked": true}', 'reason', v_reason), v_key);
    UPDATE tien.access_grant SET revoked_event = v_event WHERE id = v_grant.id;
    RETURN tien._finish(v_scope, 'revoke_role', p, jsonb_build_object('grant_id', v_grant.id, 'revoked', true));
END $$;

-- Xem trước: kiểm và phân loại, lưu lô validated + dòng gốc. Cùng tài khoản + cùng file_sha256 đã commit → trả lô cũ, 0 mới.
CREATE OR REPLACE FUNCTION tien.preview_import(p jsonb) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path TO 'pg_catalog', 'tien', 'pg_temp' AS $$
DECLARE v_key text := tien._begin(p); v_acc tien.financial_account; v_scope text; v_retry jsonb; v_sha text; v_tpl text;
        v_from date; v_to date; v_opening bigint; v_closing bigint; v_last boolean; v_old tien.statement_import; v_rows bigint;
        v_cls jsonb; v_id bigint; v_event bigint; v_result jsonb;
BEGIN
    PERFORM tien._keys(p, ARRAY['idempotency_key', 'account_id', 'file_sha256', 'template', 'period_from', 'period_to', 'lines'],
                       ARRAY['opening_minor', 'closing_minor', 'last_day_complete']);
    v_acc := tien._lock_account(tien._id(p -> 'account_id'));
    PERFORM tien._require('tien_nhap', v_acc.legal_entity_id, v_acc.id);
    v_scope := 'account:' || v_acc.id;
    v_retry := tien._replay(v_scope, 'preview_import', p);
    IF v_retry IS NOT NULL THEN RETURN v_retry; END IF;
    v_sha := tien._text(p -> 'file_sha256', 64);
    v_tpl := tien._text(p -> 'template', 45);
    v_from := tien._date(p -> 'period_from');
    v_to := tien._date(p -> 'period_to');
    v_opening := tien._minor(p -> 'opening_minor', true);
    v_closing := tien._minor(p -> 'closing_minor', true);
    v_last := tien._bool(p -> 'last_day_complete', false);
    IF v_sha IS NULL OR v_sha !~ '^[0-9a-f]{64}$' OR v_tpl IS NULL OR v_tpl !~ '^[a-z0-9][a-z0-9_-]{0,39}@[1-9][0-9]{0,3}$'
       OR v_from IS NULL OR v_to IS NULL OR v_from > v_to OR v_to > tien._today()
       OR (v_acc.statement_template IS NOT NULL AND v_tpl <> v_acc.statement_template) THEN
        RAISE EXCEPTION 'INVALID_COMMAND';
    END IF;
    PERFORM tien._check_lines(p -> 'lines');
    IF NOT EXISTS (SELECT 1 FROM tien.account_opening WHERE account_id = v_acc.id) THEN RAISE EXCEPTION 'NO_OPENING'; END IF;
    SELECT * INTO v_old FROM tien.statement_import WHERE account_id = v_acc.id AND file_sha256 = v_sha AND status = 'committed';
    IF FOUND THEN
        SELECT count(*) INTO v_rows FROM tien.raw_statement_line WHERE import_id = v_old.id;
        RETURN tien._finish(v_scope, 'preview_import', p, jsonb_build_object('import_id', v_old.id, 'status', 'committed',
            'same_file', true, 'counts', jsonb_build_object('rows', v_rows, 'new', 0, 'duplicate', v_rows, 'suspect', 0, 'error', 0)));
    END IF;
    v_cls := tien._classify(v_acc.id, v_tpl, v_from, v_to, v_opening, v_closing, tien._today(), p -> 'lines');
    v_id := nextval(pg_get_serial_sequence('tien.statement_import', 'id'));
    v_event := tien._event('import_preview', v_acc.legal_entity_id, v_acc.id, '{}', jsonb_build_object(
        'import', jsonb_build_object('id', v_id, 'status', 'validated', 'file_sha256', v_sha, 'template', v_tpl, 'period_from', v_from,
                                     'period_to', v_to, 'opening_minor', v_opening::text, 'closing_minor', v_closing::text,
                                     'last_day_complete', v_last, 'preview_hash', v_cls ->> 'hash', 'counts', v_cls -> 'counts'),
        'account_version', v_acc.version, 'breaks', v_cls -> 'breaks'), v_key);
    INSERT INTO tien.statement_import(id, account_id, file_sha256, template, period_from, period_to, opening_minor, closing_minor,
                                      last_day_complete, preview_account_version, preview_hash, counts, created_event)
    OVERRIDING SYSTEM VALUE VALUES (v_id, v_acc.id, v_sha, v_tpl, v_from, v_to, v_opening, v_closing, v_last, v_acc.version,
                                    v_cls ->> 'hash', v_cls -> 'counts', v_event);
    INSERT INTO tien.raw_statement_line(import_id, seq, line_no, line, cells, line_hash)
    SELECT v_id, x.ord, (x.e ->> 'line_no')::integer, x.e - 'cells', x.e -> 'cells', encode(sha256(convert_to(x.e::text, 'UTF8')), 'hex')
      FROM jsonb_array_elements(p -> 'lines') WITH ORDINALITY x(e, ord);
    v_result := jsonb_build_object('import_id', v_id, 'status', 'validated', 'template', v_tpl, 'preview_account_version', v_acc.version,
        'preview_hash', v_cls ->> 'hash', 'counts', v_cls -> 'counts', 'balance', v_cls -> 'balance', 'breaks', v_cls -> 'breaks',
        'lines', (SELECT coalesce(jsonb_agg(x - 'fp' ORDER BY (x ->> 'seq')::integer), '[]'::jsonb) FROM jsonb_array_elements(v_cls -> 'lines') x));
    RETURN tien._finish(v_scope, 'preview_import', p, v_result);
END $$;

-- Commit: phân loại lại dưới khóa trên dòng gốc đã lưu; version tài khoản hay preview_hash khác → IMPORT_PREVIEW_STALE.
-- Dòng mới tạo giao dịch + nguồn origin; dòng trùng tạo nguồn duplicate_confirmed trỏ ứng viên; version tài khoản + 1.
-- suspect_decisions (quyết dòng nghi trùng) và keep_existing (giữ giao dịch đã có trong kỳ mà file không nhận, có lý do) là quyết
-- định của người đối chiếu: lô có một trong hai thì cần tien_review (đủ để tự commit lô đó); lô không có quyết định cần tien_nhap.
CREATE OR REPLACE FUNCTION tien.commit_import(p jsonb) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path TO 'pg_catalog', 'tien', 'pg_temp' AS $$
DECLARE v_key text := tien._begin(p); v_account bigint; v_acc tien.financial_account; v_imp tien.statement_import; v_scope text;
        v_retry jsonb; v_dec jsonb; v_keep jsonb; v_kept jsonb; v_lines jsonb; v_cls jsonb; v_plan jsonb; v_event bigint;
        v_created jsonb; v_confirmed jsonb; v_broken text; v_pool bigint[]; v_targets bigint[]; v_ids bigint[];
        v_seq regclass := pg_get_serial_sequence('tien.bank_transaction', 'id')::regclass;
BEGIN
    PERFORM tien._keys(p, ARRAY['idempotency_key', 'import_id', 'expected_preview_hash'], ARRAY['suspect_decisions', 'keep_existing']);
    SELECT account_id INTO v_account FROM tien.statement_import WHERE id = tien._id(p -> 'import_id');
    IF NOT FOUND THEN RAISE EXCEPTION 'INVALID_COMMAND'; END IF;
    v_acc := tien._lock_account(v_account);
    v_dec := coalesce(p -> 'suspect_decisions', '[]'::jsonb);
    v_keep := coalesce(p -> 'keep_existing', '[]'::jsonb);
    IF jsonb_typeof(v_dec) <> 'array' OR jsonb_typeof(v_keep) <> 'array' THEN RAISE EXCEPTION 'INVALID_COMMAND'; END IF;
    IF jsonb_array_length(v_dec) + jsonb_array_length(v_keep) > 0 THEN
        PERFORM tien._require('tien_review', v_acc.legal_entity_id, v_acc.id);
    ELSE
        PERFORM tien._require('tien_nhap', v_acc.legal_entity_id, v_acc.id);
    END IF;
    v_scope := 'account:' || v_acc.id;
    v_retry := tien._replay(v_scope, 'commit_import', p);
    IF v_retry IS NOT NULL THEN RETURN v_retry; END IF;
    IF jsonb_typeof(p -> 'expected_preview_hash') <> 'string' THEN RAISE EXCEPTION 'INVALID_COMMAND'; END IF;
    IF EXISTS (SELECT 1 FROM jsonb_array_elements(v_dec) x(d) WHERE CASE WHEN jsonb_typeof(d) <> 'object' THEN true ELSE
            EXISTS (SELECT 1 FROM jsonb_object_keys(d) k WHERE k NOT IN ('line_no', 'decision', 'transaction_id'))
            OR jsonb_typeof(d -> 'line_no') IS DISTINCT FROM 'number' OR (d ->> 'line_no') !~ '^[1-9][0-9]{0,8}$'
            OR coalesce(d ->> 'decision', '') NOT IN ('new', 'duplicate_of')
            OR ((d ->> 'decision') = 'duplicate_of') <> (d ? 'transaction_id')
            OR (d ? 'transaction_id' AND (jsonb_typeof(d -> 'transaction_id') <> 'number'
                                          OR (d ->> 'transaction_id') !~ '^[1-9][0-9]{0,17}$')) END)
       OR EXISTS (SELECT 1 FROM jsonb_array_elements(v_keep) x(k) WHERE CASE WHEN jsonb_typeof(k) <> 'object' THEN true ELSE
            EXISTS (SELECT 1 FROM jsonb_object_keys(k) n WHERE n NOT IN ('transaction_id', 'reason'))
            OR jsonb_typeof(k -> 'transaction_id') IS DISTINCT FROM 'number' OR (k ->> 'transaction_id') !~ '^[1-9][0-9]{0,17}$'
            OR coalesce(jsonb_typeof(k -> 'reason'), 'null') NOT IN ('string', 'null') END) THEN
        RAISE EXCEPTION 'INVALID_COMMAND';
    END IF;
    SELECT * INTO v_imp FROM tien.statement_import WHERE id = tien._id(p -> 'import_id');
    IF v_imp.status <> 'validated' OR v_imp.preview_account_version <> v_acc.version THEN RAISE EXCEPTION 'IMPORT_PREVIEW_STALE'; END IF;
    IF v_imp.period_to > tien._today() THEN RAISE EXCEPTION 'INVALID_COMMAND'; END IF;
    SELECT coalesce(jsonb_agg(r.line ORDER BY r.seq), '[]'::jsonb) INTO v_lines FROM tien.raw_statement_line r WHERE r.import_id = v_imp.id;
    v_cls := tien._classify(v_acc.id, v_imp.template, v_imp.period_from, v_imp.period_to, v_imp.opening_minor, v_imp.closing_minor,
                            tien._today(), v_lines);
    IF v_cls ->> 'hash' <> v_imp.preview_hash OR v_cls ->> 'hash' <> p ->> 'expected_preview_hash' THEN
        RAISE EXCEPTION 'IMPORT_PREVIEW_STALE';
    END IF;
    IF (v_cls -> 'counts' ->> 'error')::integer > 0 THEN RAISE EXCEPTION 'IMPORT_HAS_ERRORS'; END IF;
    SELECT string_agg(DISTINCT b ->> 'code', ',') INTO v_broken FROM jsonb_array_elements(v_cls -> 'breaks') x(b)
     WHERE b ->> 'code' <> 'UNMATCHED_EXISTING';
    IF v_broken IS NOT NULL THEN RAISE EXCEPTION 'BALANCE_CHAIN_BROKEN' USING DETAIL = v_broken; END IF;
    -- Quyết định chỉ cho dòng nghi trùng, mỗi dòng một lần; dòng nghi trùng nào cũng phải có quyết định.
    IF EXISTS (SELECT 1 FROM jsonb_array_elements(v_dec) x(d) WHERE NOT EXISTS (
                   SELECT 1 FROM jsonb_array_elements(v_cls -> 'lines') y(l) WHERE l ->> 'class' = 'suspect' AND l -> 'line_no' = d -> 'line_no'))
       OR (SELECT count(*) <> count(DISTINCT d -> 'line_no') FROM jsonb_array_elements(v_dec) x(d)) THEN
        RAISE EXCEPTION 'INVALID_COMMAND';
    END IF;
    IF EXISTS (SELECT 1 FROM jsonb_array_elements(v_cls -> 'lines') y(l) WHERE l ->> 'class' = 'suspect'
                AND NOT EXISTS (SELECT 1 FROM jsonb_array_elements(v_dec) x(d) WHERE d -> 'line_no' = l -> 'line_no')) THEN
        RAISE EXCEPTION 'IMPORT_SUSPECT_UNRESOLVED';
    END IF;
    -- "Trùng của X": X hiệu lực, cùng tài khoản, cùng ngày ghi sổ, chiều, số tiền với dòng; không là ứng viên của dòng trùng chắc
    -- khác, không là đích của quyết định khác trong lô (BR-IM6). Mô tả không xét: nghi trùng sinh ra chính vì mô tả có thể đổi.
    IF EXISTS (SELECT 1 FROM jsonb_array_elements(v_dec) x(d)
                 JOIN tien.raw_statement_line s ON s.import_id = v_imp.id AND s.line_no = (d ->> 'line_no')::integer
                 LEFT JOIN tien.bank_transaction t ON t.id = (d ->> 'transaction_id')::bigint
                WHERE d ->> 'decision' = 'duplicate_of'
                  AND (t.id IS NULL OR t.account_id <> v_acc.id OR t.voided_event IS NOT NULL
                       OR t.booking_date <> (s.line ->> 'booking_date')::date OR t.direction <> s.line ->> 'direction'
                       OR t.amount_minor <> (s.line ->> 'amount_minor')::bigint
                       OR EXISTS (SELECT 1 FROM jsonb_array_elements(v_cls -> 'lines') z(o)
                                   WHERE o ->> 'class' = 'duplicate' AND (o ->> 'candidate')::bigint = t.id)
                       OR (SELECT count(*) FROM jsonb_array_elements(v_dec) w(d2) WHERE d2 -> 'transaction_id' = d -> 'transaction_id') > 1)) THEN
        RAISE EXCEPTION 'DUPLICATE_TARGET_INVALID';
    END IF;
    -- Mọi giao dịch của U (giao dịch đã có trong kỳ chưa là ứng viên ở bước 3–4, kể cả giao dịch đang là ứng viên mềm của dòng nghi
    -- trùng) phải là đích "trùng của" hoặc được giữ có lý do: quyết new cho dòng nghi trùng mềm buộc nói rõ vì sao giữ giao dịch cũ.
    -- id giữ phải thuộc U và không đồng thời là đích "trùng của".
    v_pool := ARRAY(SELECT (x #>> '{}')::bigint FROM jsonb_array_elements(v_cls -> 'pool') x);
    v_targets := ARRAY(SELECT (d ->> 'transaction_id')::bigint FROM jsonb_array_elements(v_dec) x(d) WHERE d ->> 'decision' = 'duplicate_of');
    IF EXISTS (SELECT 1 FROM jsonb_array_elements(v_keep) x(k) WHERE (k ->> 'transaction_id')::bigint <> ALL (v_pool)
                                                                  OR (k ->> 'transaction_id')::bigint = ANY (v_targets))
       OR (SELECT count(*) <> count(DISTINCT k -> 'transaction_id') FROM jsonb_array_elements(v_keep) x(k)) THEN
        RAISE EXCEPTION 'INVALID_COMMAND';
    END IF;
    SELECT coalesce(jsonb_agg(jsonb_build_object('transaction_id', (k ->> 'transaction_id')::bigint, 'reason', tien._text(k -> 'reason', 500))
                              ORDER BY (k ->> 'transaction_id')::bigint), '[]'::jsonb)
      INTO v_kept FROM jsonb_array_elements(v_keep) x(k);
    IF EXISTS (SELECT 1 FROM jsonb_array_elements(v_kept) x(k) WHERE k ->> 'reason' IS NULL) THEN RAISE EXCEPTION 'REASON_REQUIRED'; END IF;
    IF EXISTS (SELECT 1 FROM unnest(v_pool) u(id) WHERE u.id <> ALL (v_targets)
                AND NOT EXISTS (SELECT 1 FROM jsonb_array_elements(v_kept) x(k) WHERE (k ->> 'transaction_id')::bigint = u.id)) THEN
        RAISE EXCEPTION 'BALANCE_CHAIN_BROKEN' USING DETAIL = 'UNMATCHED_EXISTING';
    END IF;
    WITH lines AS (
        SELECT (l ->> 'seq')::integer AS seq, (l ->> 'line_no')::integer AS line_no, l ->> 'fp' AS fp, s.id AS raw_id,
               CASE WHEN l ->> 'class' = 'duplicate' THEN (l ->> 'candidate')::bigint
                    WHEN d ->> 'decision' = 'duplicate_of' THEN (d ->> 'transaction_id')::bigint END AS target
          FROM jsonb_array_elements(v_cls -> 'lines') y(l)
          JOIN tien.raw_statement_line s ON s.import_id = v_imp.id AND s.seq = (l ->> 'seq')::integer
          LEFT JOIN jsonb_array_elements(v_dec) x(d) ON l ->> 'class' = 'suspect' AND d -> 'line_no' = l -> 'line_no'
    )
    SELECT coalesce(jsonb_agg(jsonb_build_object('seq', seq, 'line_no', line_no, 'raw_id', raw_id, 'fp', fp, 'target', target)
                              ORDER BY seq), '[]'::jsonb)
      INTO v_plan FROM lines;
    -- Mã giao dịch mới cấp theo thứ tự dòng trong lô (giữ trật tự cho lần ghép theo thứ tự ở bước 3–4 của các lô sau).
    v_ids := ARRAY(SELECT n FROM (SELECT nextval(v_seq) AS n FROM generate_series(1, (SELECT count(*)::integer
                       FROM jsonb_array_elements(v_plan) x WHERE x ->> 'target' IS NULL))) s ORDER BY n);
    SELECT coalesce(jsonb_agg(CASE WHEN r.target IS NULL THEN r.x || jsonb_build_object('new_id', v_ids[r.k::integer]) ELSE r.x END
                              ORDER BY r.seq),
                    '[]'::jsonb)
      INTO v_plan
      FROM (SELECT x, (x ->> 'seq')::integer AS seq, x ->> 'target' AS target,
                   row_number() OVER (PARTITION BY x ->> 'target' IS NULL ORDER BY (x ->> 'seq')::integer) AS k
              FROM jsonb_array_elements(v_plan) x) r;
    SELECT coalesce(jsonb_agg(jsonb_build_object('line_no', x -> 'line_no', 'transaction_id', x -> 'new_id') ORDER BY (x ->> 'seq')::integer)
                    FILTER (WHERE x ->> 'new_id' IS NOT NULL), '[]'::jsonb),
           coalesce(jsonb_agg(jsonb_build_object('line_no', x -> 'line_no', 'transaction_id', x -> 'target') ORDER BY (x ->> 'seq')::integer)
                    FILTER (WHERE x ->> 'target' IS NOT NULL), '[]'::jsonb)
      INTO v_created, v_confirmed FROM jsonb_array_elements(v_plan) x;
    v_event := tien._event('import_commit', v_acc.legal_entity_id, v_acc.id,
        jsonb_build_object('import', jsonb_build_object('id', v_imp.id, 'status', 'validated', 'preview_hash', v_imp.preview_hash),
                           'account_version', v_acc.version),
        jsonb_build_object('import', jsonb_build_object('id', v_imp.id, 'status', 'committed'), 'account_version', v_acc.version + 1,
                           'created', v_created, 'confirmed', v_confirmed, 'suspect_decisions', v_dec, 'kept', v_kept), v_key);
    INSERT INTO tien.bank_transaction(id, account_id, currency, source_family, direction, amount_minor, booking_date, value_date,
                                      bank_ref, description, balance_after_minor, fingerprint, created_event)
    OVERRIDING SYSTEM VALUE
    SELECT (x ->> 'new_id')::bigint, v_acc.id, v_acc.currency, split_part(v_imp.template, '@', 1), s.line ->> 'direction',
           (s.line ->> 'amount_minor')::bigint, (s.line ->> 'booking_date')::date, (s.line ->> 'value_date')::date,
           nullif(btrim(s.line ->> 'bank_ref'), ''), s.line ->> 'description', (s.line ->> 'balance_after_minor')::bigint, x ->> 'fp', v_event
      FROM jsonb_array_elements(v_plan) x JOIN tien.raw_statement_line s ON s.id = (x ->> 'raw_id')::bigint
     WHERE x ->> 'new_id' IS NOT NULL;
    INSERT INTO tien.bank_transaction_source(bank_transaction_id, account_id, import_id, raw_line_id, role, created_event)
    SELECT coalesce((x ->> 'new_id')::bigint, (x ->> 'target')::bigint), v_acc.id, v_imp.id, (x ->> 'raw_id')::bigint,
           CASE WHEN x ->> 'new_id' IS NULL THEN 'duplicate_confirmed' ELSE 'origin' END, v_event
      FROM jsonb_array_elements(v_plan) x;
    UPDATE tien.statement_import SET status = 'committed', committed_event = v_event WHERE id = v_imp.id;
    UPDATE tien.financial_account SET version = version + 1 WHERE id = v_acc.id;
    PERFORM tien._check_account(v_acc.id);
    RETURN tien._finish(v_scope, 'commit_import', p, jsonb_build_object('import_id', v_imp.id, 'status', 'committed',
        'account_version', v_acc.version + 1, 'created', jsonb_array_length(v_created), 'confirmed', jsonb_array_length(v_confirmed),
        'kept', jsonb_array_length(v_kept),
        'transaction_ids', (SELECT coalesce(jsonb_agg(x -> 'transaction_id'), '[]'::jsonb) FROM jsonb_array_elements(v_created) x)));
END $$;

CREATE OR REPLACE FUNCTION tien.reject_import(p jsonb) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path TO 'pg_catalog', 'tien', 'pg_temp' AS $$
DECLARE v_key text := tien._begin(p); v_account bigint; v_acc tien.financial_account; v_imp tien.statement_import; v_scope text;
        v_retry jsonb; v_reason text; v_event bigint;
BEGIN
    PERFORM tien._keys(p, ARRAY['idempotency_key', 'import_id'], ARRAY['reason']);
    SELECT account_id INTO v_account FROM tien.statement_import WHERE id = tien._id(p -> 'import_id');
    IF NOT FOUND THEN RAISE EXCEPTION 'INVALID_COMMAND'; END IF;
    v_acc := tien._lock_account(v_account);
    PERFORM tien._require('tien_nhap', v_acc.legal_entity_id, v_acc.id);
    v_scope := 'account:' || v_acc.id;
    v_retry := tien._replay(v_scope, 'reject_import', p);
    IF v_retry IS NOT NULL THEN RETURN v_retry; END IF;
    v_reason := tien._text(p -> 'reason', 500);
    IF v_reason IS NULL THEN RAISE EXCEPTION 'REASON_REQUIRED'; END IF;
    SELECT * INTO v_imp FROM tien.statement_import WHERE id = tien._id(p -> 'import_id');
    IF v_imp.status <> 'validated' THEN RAISE EXCEPTION 'INVALID_COMMAND'; END IF;
    v_event := tien._event('import_reject', v_acc.legal_entity_id, v_acc.id,
        jsonb_build_object('import', jsonb_build_object('id', v_imp.id, 'status', 'validated')),
        jsonb_build_object('import', jsonb_build_object('id', v_imp.id, 'status', 'rejected', 'reason', v_reason)), v_key);
    UPDATE tien.statement_import SET status = 'rejected', closed_event = v_event, reason = v_reason WHERE id = v_imp.id;
    RETURN tien._finish(v_scope, 'reject_import', p, jsonb_build_object('import_id', v_imp.id, 'status', 'rejected'));
END $$;

-- Hủy lô: giao dịch chỉ bị hủy khi không còn nguồn ở lô khác đã commit; chặn nếu giao dịch sẽ hủy còn phân bổ hiệu lực.
CREATE OR REPLACE FUNCTION tien.void_import(p jsonb) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path TO 'pg_catalog', 'tien', 'pg_temp' AS $$
DECLARE v_key text := tien._begin(p); v_account bigint; v_acc tien.financial_account; v_imp tien.statement_import; v_scope text;
        v_retry jsonb; v_reason text; v_event bigint; v_void bigint[]; v_keep bigint[];
BEGIN
    PERFORM tien._keys(p, ARRAY['idempotency_key', 'import_id'], ARRAY['reason']);
    SELECT account_id INTO v_account FROM tien.statement_import WHERE id = tien._id(p -> 'import_id');
    IF NOT FOUND THEN RAISE EXCEPTION 'INVALID_COMMAND'; END IF;
    v_acc := tien._lock_account(v_account);
    PERFORM tien._require('tien_review', v_acc.legal_entity_id, v_acc.id);
    v_scope := 'account:' || v_acc.id;
    v_retry := tien._replay(v_scope, 'void_import', p);
    IF v_retry IS NOT NULL THEN RETURN v_retry; END IF;
    v_reason := tien._text(p -> 'reason', 500);
    IF v_reason IS NULL THEN RAISE EXCEPTION 'REASON_REQUIRED'; END IF;
    SELECT * INTO v_imp FROM tien.statement_import WHERE id = tien._id(p -> 'import_id');
    IF v_imp.status <> 'committed' THEN RAISE EXCEPTION 'INVALID_COMMAND'; END IF;
    SELECT coalesce(array_agg(t.id ORDER BY t.id) FILTER (WHERE NOT o.other), '{}'), coalesce(array_agg(t.id ORDER BY t.id) FILTER (WHERE o.other), '{}')
      INTO v_void, v_keep
      FROM tien.bank_transaction t
      CROSS JOIN LATERAL (SELECT EXISTS (SELECT 1 FROM tien.bank_transaction_source s2 JOIN tien.statement_import i2 ON i2.id = s2.import_id
                                          WHERE s2.bank_transaction_id = t.id AND s2.import_id <> v_imp.id AND i2.status = 'committed') AS other) o
     WHERE t.voided_event IS NULL AND EXISTS (SELECT 1 FROM tien.bank_transaction_source s WHERE s.import_id = v_imp.id AND s.bank_transaction_id = t.id);
    IF EXISTS (SELECT 1 FROM tien.allocation WHERE bank_transaction_id = ANY (v_void) AND superseded_event IS NULL) THEN
        RAISE EXCEPTION 'VOID_WOULD_LOSE_ALLOCATED';
    END IF;
    v_event := tien._event('import_void', v_acc.legal_entity_id, v_acc.id,
        jsonb_build_object('import', jsonb_build_object('id', v_imp.id, 'status', 'committed'), 'account_version', v_acc.version),
        jsonb_build_object('import', jsonb_build_object('id', v_imp.id, 'status', 'voided', 'reason', v_reason),
                           'voided', to_jsonb(v_void), 'kept', to_jsonb(v_keep), 'account_version', v_acc.version + 1), v_key);
    UPDATE tien.bank_transaction SET voided_event = v_event WHERE id = ANY (v_void);
    UPDATE tien.statement_import SET status = 'voided', closed_event = v_event, reason = v_reason WHERE id = v_imp.id;
    UPDATE tien.financial_account SET version = version + 1 WHERE id = v_acc.id;
    PERFORM tien._check_account(v_acc.id);
    RETURN tien._finish(v_scope, 'void_import', p, jsonb_build_object('import_id', v_imp.id, 'status', 'voided',
        'account_version', v_acc.version + 1, 'voided_transactions', to_jsonb(v_void), 'kept_transactions', to_jsonb(v_keep)));
END $$;

-- Thay cả bộ phân bổ của một giao dịch theo expected_version. Σ ≤ số tiền, mỗi dòng > 0; bỏ hay đổi dòng đang hiệu lực cần lý do;
-- bộ mới y hệt bộ cũ thì không ghi gì.
CREATE OR REPLACE FUNCTION tien.set_allocation(p jsonb) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path TO 'pg_catalog', 'tien', 'pg_temp' AS $$
DECLARE v_key text := tien._begin(p); v_account bigint; v_acc tien.financial_account; v_tx tien.bank_transaction; v_scope text;
        v_retry jsonb; v_lines jsonb := '[]'::jsonb; v_old jsonb; v_new jsonb; v_reason text; v_total bigint := 0; v_amount bigint;
        e jsonb; v_kind text; v_ref jsonb; v_other tien.bank_transaction; v_removed boolean; v_event bigint;
        v_seq regclass := pg_get_serial_sequence('tien.allocation', 'id')::regclass;
BEGIN
    PERFORM tien._keys(p, ARRAY['idempotency_key', 'transaction_id', 'expected_version', 'lines'], ARRAY['reason']);
    SELECT account_id INTO v_account FROM tien.bank_transaction WHERE id = tien._id(p -> 'transaction_id');
    IF NOT FOUND THEN RAISE EXCEPTION 'INVALID_COMMAND'; END IF;
    v_acc := tien._lock_account(v_account);
    PERFORM tien._require('tien_phan_bo', v_acc.legal_entity_id, v_acc.id);
    v_scope := 'account:' || v_acc.id;
    v_retry := tien._replay(v_scope, 'set_allocation', p);
    IF v_retry IS NOT NULL THEN RETURN v_retry; END IF;
    IF jsonb_typeof(p -> 'expected_version') <> 'number' OR (p ->> 'expected_version') !~ '^(0|[1-9][0-9]{0,17})$'
       OR jsonb_typeof(p -> 'lines') <> 'array' THEN
        RAISE EXCEPTION 'INVALID_COMMAND';
    END IF;
    IF jsonb_array_length(p -> 'lines') > 200 THEN RAISE EXCEPTION 'INVALID_COMMAND'; END IF;
    SELECT * INTO v_tx FROM tien.bank_transaction WHERE id = tien._id(p -> 'transaction_id');
    IF v_tx.voided_event IS NOT NULL THEN RAISE EXCEPTION 'TRANSACTION_VOID'; END IF;
    IF v_tx.version <> (p ->> 'expected_version')::bigint THEN RAISE EXCEPTION 'STALE_VERSION'; END IF;
    FOR e IN SELECT value FROM jsonb_array_elements(p -> 'lines') LOOP
        PERFORM tien._keys(e, ARRAY['target_kind', 'target_ref', 'amount_minor'], ARRAY['note']);
        IF jsonb_typeof(e -> 'target_kind') <> 'string' OR jsonb_typeof(e -> 'target_ref') <> 'object' THEN
            RAISE EXCEPTION 'INVALID_COMMAND';
        END IF;
        v_kind := e ->> 'target_kind';
        v_ref := e -> 'target_ref';
        v_amount := tien._minor(e -> 'amount_minor', false);
        IF v_amount IS NULL OR v_amount <= 0 THEN RAISE EXCEPTION 'INVALID_COMMAND'; END IF;
        IF v_kind IN ('ar_book', 'customer_unapplied') THEN
            PERFORM tien._keys(v_ref, ARRAY['customer_id'], '{}');
            IF jsonb_typeof(v_ref -> 'customer_id') <> 'string' OR (v_ref ->> 'customer_id') !~ '^[1-9][0-9]{0,17}$' THEN
                RAISE EXCEPTION 'INVALID_COMMAND';
            END IF;
        ELSIF v_kind = 'internal_transfer' THEN
            -- Chân kia: giao dịch hiệu lực, ngược chiều, ở tài khoản khác cùng pháp nhân (khác pháp nhân → ENTITY_SCOPE, ADR-TIEN-06).
            PERFORM tien._keys(v_ref, ARRAY['transaction_id'], '{}');
            IF jsonb_typeof(v_ref -> 'transaction_id') <> 'string' OR (v_ref ->> 'transaction_id') !~ '^[1-9][0-9]{0,17}$' THEN
                RAISE EXCEPTION 'INVALID_COMMAND';
            END IF;
            SELECT * INTO v_other FROM tien.bank_transaction WHERE id = (v_ref ->> 'transaction_id')::bigint;
            IF NOT FOUND OR v_other.voided_event IS NOT NULL OR v_other.account_id = v_tx.account_id OR v_other.direction = v_tx.direction THEN
                RAISE EXCEPTION 'INVALID_COMMAND';
            END IF;
            IF NOT EXISTS (SELECT 1 FROM tien.financial_account WHERE id = v_other.account_id AND legal_entity_id = v_acc.legal_entity_id) THEN
                RAISE EXCEPTION 'ENTITY_SCOPE';
            END IF;
        ELSIF v_kind = 'expense_category' THEN
            PERFORM tien._keys(v_ref, ARRAY['category'], '{}');
            IF tien._text(v_ref -> 'category', 100) IS NULL THEN RAISE EXCEPTION 'INVALID_COMMAND'; END IF;
            v_ref := jsonb_build_object('category', tien._text(v_ref -> 'category', 100));
        ELSIF v_kind IN ('internal_transfer_pending', 'cash_withdrawal', 'bank_fee', 'interest', 'customer_funds_pending', 'fleet', 'other') THEN
            IF v_ref <> '{}'::jsonb THEN RAISE EXCEPTION 'INVALID_COMMAND'; END IF;
        ELSE
            RAISE EXCEPTION 'INVALID_COMMAND';
        END IF;
        IF v_amount > v_tx.amount_minor - v_total THEN RAISE EXCEPTION 'OVER_ALLOCATION'; END IF;
        v_total := v_total + v_amount;
        v_lines := v_lines || jsonb_build_array(jsonb_build_object('target_kind', v_kind, 'target_ref', v_ref,
                                                                   'amount_minor', v_amount::text, 'note', tien._text(e -> 'note', 500)));
    END LOOP;
    v_old := tien._allocations(v_tx.id);
    IF (SELECT coalesce(jsonb_agg(x - 'id' ORDER BY (x - 'id')::text), '[]'::jsonb) FROM jsonb_array_elements(v_old) x)
       = (SELECT coalesce(jsonb_agg(x ORDER BY x::text), '[]'::jsonb) FROM jsonb_array_elements(v_lines) x) THEN
        RETURN tien._finish(v_scope, 'set_allocation', p, tien._tx_state(v_tx.id) || jsonb_build_object('unchanged', true));
    END IF;
    SELECT EXISTS (SELECT 1 FROM (SELECT x - 'id' AS k, count(*) AS c FROM jsonb_array_elements(v_old) x GROUP BY 1) o
                     LEFT JOIN (SELECT x AS k, count(*) AS c FROM jsonb_array_elements(v_lines) x GROUP BY 1) n ON n.k = o.k
                    WHERE coalesce(n.c, 0) < o.c)
      INTO v_removed;
    v_reason := tien._text(p -> 'reason', 500);
    IF v_removed AND v_reason IS NULL THEN RAISE EXCEPTION 'REASON_REQUIRED'; END IF;
    SELECT coalesce(jsonb_agg(x || jsonb_build_object('id', nextval(v_seq)) ORDER BY y.ord), '[]'::jsonb)
      INTO v_new FROM jsonb_array_elements(v_lines) WITH ORDINALITY y(x, ord);
    v_event := tien._event('allocation_set', v_acc.legal_entity_id, v_acc.id,
        jsonb_build_object('transaction', v_tx.id, 'version', v_tx.version, 'allocations', v_old),
        jsonb_build_object('transaction', v_tx.id, 'version', v_tx.version + 1, 'allocations', v_new, 'reason', v_reason), v_key);
    UPDATE tien.allocation SET superseded_event = v_event WHERE bank_transaction_id = v_tx.id AND superseded_event IS NULL;
    INSERT INTO tien.allocation(id, bank_transaction_id, account_id, currency, target_kind, target_ref, amount_minor, note, created_event)
    OVERRIDING SYSTEM VALUE
    SELECT (x ->> 'id')::bigint, v_tx.id, v_tx.account_id, v_tx.currency, x ->> 'target_kind', x -> 'target_ref',
           (x ->> 'amount_minor')::bigint, x ->> 'note', v_event
      FROM jsonb_array_elements(v_new) x;
    UPDATE tien.bank_transaction SET version = version + 1 WHERE id = v_tx.id;
    PERFORM tien._check_account(v_acc.id);
    RETURN tien._finish(v_scope, 'set_allocation', p, tien._tx_state(v_tx.id) || jsonb_build_object('unchanged', false));
END $$;

-- ---------------------------------------------------------------------------------------------------------------------------
-- Hàm đọc (cấp cho tien_app và tien_reader): cần một vai bất kỳ ở phạm vi tài khoản. Tiền là chuỗi; không có số dư mở thì số dư
-- là null (chưa biết), không phải 0. Mô tả chuyển khoản chỉ trả khi người đọc có tien_nhap hoặc tien_review.
CREATE OR REPLACE FUNCTION tien.get_account_summary(p_account bigint) RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path TO 'pg_catalog', 'tien', 'pg_temp' AS $$
DECLARE v_acc tien.financial_account; v_open tien.account_opening; v_result jsonb;
BEGIN
    PERFORM tien._actor();
    PERFORM tien._actor_kind();
    SELECT * INTO v_acc FROM tien.financial_account WHERE id = p_account;
    IF NOT FOUND THEN RAISE EXCEPTION 'INVALID_COMMAND'; END IF;
    PERFORM tien._require(NULL, v_acc.legal_entity_id, v_acc.id);
    SELECT * INTO v_open FROM tien.account_opening WHERE account_id = v_acc.id;
    SELECT jsonb_build_object(
        'account', jsonb_build_object('id', v_acc.id, 'legal_entity_id', v_acc.legal_entity_id, 'kind', v_acc.kind,
                                      'bank_code', v_acc.bank_code, 'account_last4', v_acc.account_last4, 'currency', v_acc.currency,
                                      'holder', v_acc.holder, 'statement_template', v_acc.statement_template,
                                      'bank_ref_stable', v_acc.bank_ref_stable, 'version', v_acc.version),
        'opening', CASE WHEN v_open.account_id IS NULL THEN NULL
                        ELSE jsonb_build_object('as_of', v_open.as_of, 'amount_minor', v_open.amount_minor::text) END,
        'in_minor', coalesce(sum(t.amount_minor) FILTER (WHERE t.direction = 'in' AND t.voided_event IS NULL), 0)::bigint::text,
        'out_minor', coalesce(sum(t.amount_minor) FILTER (WHERE t.direction = 'out' AND t.voided_event IS NULL), 0)::bigint::text,
        'balance_minor', CASE WHEN v_open.account_id IS NULL THEN NULL ELSE (v_open.amount_minor
            + coalesce(sum(CASE t.direction WHEN 'in' THEN t.amount_minor ELSE -t.amount_minor END) FILTER (WHERE t.voided_event IS NULL), 0))::bigint::text END,
        'latest_booking_date', max(t.booking_date) FILTER (WHERE t.voided_event IS NULL),
        'transactions', count(*) FILTER (WHERE t.voided_event IS NULL),
        'voided', count(*) FILTER (WHERE t.voided_event IS NOT NULL),
        'status_counts', jsonb_build_object(
            'in', jsonb_build_object('unidentified', count(*) FILTER (WHERE t.status = 'unidentified'),
                                     'unapplied', count(*) FILTER (WHERE t.status = 'unapplied'),
                                     'partial', count(*) FILTER (WHERE t.direction = 'in' AND t.status = 'partial'),
                                     'applied', count(*) FILTER (WHERE t.status = 'applied')),
            'out', jsonb_build_object('unmatched', count(*) FILTER (WHERE t.status = 'unmatched'),
                                      'partial', count(*) FILTER (WHERE t.direction = 'out' AND t.status = 'partial'),
                                      'matched', count(*) FILTER (WHERE t.status = 'matched'))))
      INTO v_result FROM tien.v_transaction t WHERE t.account_id = v_acc.id;
    RETURN v_result;
END $$;

CREATE OR REPLACE FUNCTION tien.list_transactions(p_account bigint, p_from date, p_to date) RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path TO 'pg_catalog', 'tien', 'pg_temp' AS $$
DECLARE v_acc tien.financial_account; v_desc boolean; v_result jsonb;
BEGIN
    PERFORM tien._actor();
    PERFORM tien._actor_kind();
    SELECT * INTO v_acc FROM tien.financial_account WHERE id = p_account;
    IF NOT FOUND THEN RAISE EXCEPTION 'INVALID_COMMAND'; END IF;
    PERFORM tien._require(NULL, v_acc.legal_entity_id, v_acc.id);
    IF p_from > p_to THEN RAISE EXCEPTION 'INVALID_COMMAND'; END IF;
    v_desc := tien._has_role(ARRAY['tien_nhap', 'tien_review'], v_acc.legal_entity_id, v_acc.id);
    SELECT jsonb_build_object('account_id', v_acc.id, 'from', p_from, 'to', p_to, 'description_visible', v_desc,
        'transactions', coalesce(jsonb_agg(jsonb_build_object(
            'id', t.id, 'direction', t.direction, 'amount_minor', t.amount_minor::text, 'currency', t.currency,
            'booking_date', t.booking_date, 'value_date', t.value_date, 'bank_ref', t.bank_ref,
            'allocated_minor', t.allocated_minor::text, 'unallocated_minor', (t.amount_minor - t.allocated_minor)::text,
            'status', t.status, 'voided', t.voided_event IS NOT NULL, 'version', t.version,
            'sources', (SELECT coalesce(jsonb_agg(jsonb_build_object('import_id', s.import_id, 'role', s.role, 'line_no', r.line_no,
                                                                     'import_status', i.status) ORDER BY s.id), '[]'::jsonb)
                          FROM tien.bank_transaction_source s JOIN tien.raw_statement_line r ON r.id = s.raw_line_id
                          JOIN tien.statement_import i ON i.id = s.import_id WHERE s.bank_transaction_id = t.id))
            || CASE WHEN v_desc THEN jsonb_build_object('description', t.description) ELSE '{}'::jsonb END
            ORDER BY t.booking_date, t.id), '[]'::jsonb))
      INTO v_result FROM tien.v_transaction t
     WHERE t.account_id = v_acc.id AND (p_from IS NULL OR t.booking_date >= p_from) AND (p_to IS NULL OR t.booking_date <= p_to);
    RETURN v_result;
END $$;

-- Quyền: tien_app gọi mười lệnh và hai hàm đọc, tien_reader chỉ hai hàm đọc; hàm phụ không cấp cho ai; không quyền bảng.
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA tien FROM PUBLIC;
REVOKE ALL ON ALL TABLES IN SCHEMA tien FROM PUBLIC;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA tien FROM PUBLIC;
GRANT EXECUTE ON FUNCTION tien.create_legal_entity(jsonb), tien.create_account(jsonb), tien.set_opening(jsonb), tien.grant_role(jsonb),
    tien.revoke_role(jsonb), tien.preview_import(jsonb), tien.commit_import(jsonb), tien.reject_import(jsonb), tien.void_import(jsonb),
    tien.set_allocation(jsonb) TO tien_app;
GRANT EXECUTE ON FUNCTION tien.get_account_summary(bigint), tien.list_transactions(bigint, date, date) TO tien_app, tien_reader;
COMMIT;
