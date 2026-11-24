-- Sổ tiền P0-a, lát 2 (SO-TIEN-01, 25/11/2026; spec specs/so-tien-p0a-lat2.md; thiết kế specs/van-hanh-tai-chinh/F1-kien-truc-ky-thuat.md
-- mục 3, 4, 6 (I-3), 7, 9): file sao kê gốc (QD-08), bằng chứng số dư ngân hàng nhập tay (BR-DC4), review ngày hai chữ ký có mở lại
-- (BR-DC2, BR-DC3, BR-DC5), chặn thêm hay hủy giao dịch của ngày đã ký số dư (BR-IM13), hàm đọc cho API và hai màn hình, dữ liệu xuất
-- cho kế toán. Cần lát 1 (2026-11-24-tien-p0a-lat1.sql) đã chạy; thay hàm preview_import của lát 1 (thêm file gốc, ngày đã ký).
-- Độ phủ ngày suy thẳng từ lô đã commit, không lưu bảng riêng. Không đọc, không ghi, không cấp quyền gì ở schema khác; không quyền
-- bảng cho role nào ngoài chủ schema. Chạy lại được khi chạy theo thứ tự lát 1 rồi lát 2. Hoàn tác: 2026-11-25-tien-p0a-lat2.rollback.sql
-- rồi chạy lại file lát 1. Chưa chạy trên hao (spec, Trạng thái).
BEGIN;
DO $$
BEGIN
    IF to_regprocedure('tien._classify(bigint,text,date,date,bigint,bigint,date,jsonb)') IS NULL THEN
        RAISE EXCEPTION 'TIEN_LAT1_REQUIRED';
    END IF;
END $$;
SET LOCAL ROLE tien_owner;
COMMENT ON SCHEMA tien IS 'SO-TIEN-01 sổ tiền P0-a lát 1–2: nhập sao kê có xem trước và file gốc, giao dịch ngân hàng, phân bổ, ký ngày; chỉ thêm, có vết.';

-- Vết: thêm bốn loại của lát 2 (F1 mục 9); nội dung tối thiểu theo loại như lát 1.
ALTER TABLE tien.event DROP CONSTRAINT IF EXISTS tien_event_kind, DROP CONSTRAINT IF EXISTS tien_event_shape,
    ADD CONSTRAINT tien_event_kind CHECK (kind IN ('entity_create', 'account_create', 'opening_set', 'grant', 'revoke',
        'import_preview', 'import_commit', 'import_reject', 'import_void', 'allocation_set',
        'balance_evidence', 'day_sign_coverage', 'day_sign_business', 'day_reopen')),
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
        WHEN 'balance_evidence' THEN before = '{}' AND after ? 'evidence'
        WHEN 'day_sign_coverage' THEN before ? 'day' AND after ? 'day' AND after ? 'snapshot'
        WHEN 'day_sign_business' THEN before ? 'day' AND after ? 'day' AND after ? 'snapshot'
        WHEN 'day_reopen' THEN before ? 'day' AND after ? 'day' AND after ? 'reason'
        ELSE false END);

-- ---------------------------------------------------------------------------------------------------------------------------
-- File sao kê gốc (QD-08): nguyên byte, một file một lần cho mỗi tài khoản; chỉ vai nhập/review đọc được (get_statement_file).
CREATE TABLE IF NOT EXISTS tien.statement_file (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    account_id bigint NOT NULL REFERENCES tien.financial_account(id),
    file_sha256 text NOT NULL CHECK (file_sha256 ~ '^[0-9a-f]{64}$'),
    byte_size integer NOT NULL CHECK (byte_size BETWEEN 1 AND 4194304),
    file_name text NOT NULL CHECK (btrim(file_name) <> '' AND char_length(file_name) <= 200 AND file_name !~ '[[:cntrl:]]'
                                   AND strpos(file_name, '/') = 0),
    media_type text NOT NULL CHECK (media_type IN ('application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', 'text/csv')),
    content bytea NOT NULL,
    created_event bigint NOT NULL REFERENCES tien.event(id),
    CONSTRAINT statement_file_content CHECK (octet_length(content) = byte_size AND encode(sha256(content), 'hex') = file_sha256),
    CONSTRAINT statement_file_once UNIQUE (account_id, file_sha256),
    CONSTRAINT statement_file_account_key UNIQUE (id, account_id)
);
COMMENT ON TABLE tien.statement_file IS 'File sao kê gốc (QD-08): nguyên byte, một file một lần cho mỗi tài khoản; chỉ vai nhập/review đọc, API ghi log mỗi lần tải.';

ALTER TABLE tien.statement_import ADD COLUMN IF NOT EXISTS file_id bigint;
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid = 'tien.statement_import'::regclass AND conname = 'statement_import_file_fk') THEN
        ALTER TABLE tien.statement_import ADD CONSTRAINT statement_import_file_fk FOREIGN KEY (file_id, account_id)
            REFERENCES tien.statement_file(id, account_id);
    END IF;
END $$;
COMMENT ON COLUMN tien.statement_import.file_id IS 'File gốc của lô (lát 2); NULL với lô gửi không kèm file. Không đổi sau khi ghi.';

-- Số dư cuối ngày theo ngân hàng do người xem tận mắt (BR-DC4); bản mới nhất của ngày là bản dùng khi kiểm và ký.
CREATE TABLE IF NOT EXISTS tien.balance_evidence (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    account_id bigint NOT NULL REFERENCES tien.financial_account(id),
    as_of_date date NOT NULL,
    amount_minor bigint NOT NULL,
    source text NOT NULL CHECK (source IN ('bank_pdf', 'bank_app', 'bank_paper', 'other')),
    note text NOT NULL CHECK (btrim(note) <> '' AND char_length(note) <= 500),
    role_overlap boolean NOT NULL,
    created_event bigint NOT NULL REFERENCES tien.event(id)
);
COMMENT ON TABLE tien.balance_evidence IS 'Số dư cuối ngày theo ngân hàng nhập tay, có nguồn và ghi chú; role_overlap khi người nhập cũng là người nhập lô phủ ngày đó.';

-- Nhật ký ký/mở lại của từng ngày, hai mạch riêng (BR-DC2): trạng thái hiện tại là dòng mới nhất của (tài khoản, ngày, mạch).
CREATE TABLE IF NOT EXISTS tien.day_review (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    account_id bigint NOT NULL REFERENCES tien.financial_account(id),
    business_date date NOT NULL,
    track text NOT NULL CHECK (track IN ('coverage', 'business')),
    action text NOT NULL CHECK (action IN ('sign', 'reopen')),
    role_overlap boolean NOT NULL,
    snapshot jsonb NOT NULL CHECK (jsonb_typeof(snapshot) = 'object'),
    note text CHECK (btrim(note) <> '' AND char_length(note) <= 500),
    created_event bigint NOT NULL REFERENCES tien.event(id),
    CONSTRAINT day_review_reopen_reason CHECK (action <> 'reopen' OR note IS NOT NULL)
);
COMMENT ON TABLE tien.day_review IS 'Ký số dư (coverage) và ký đối soát (business) của từng ngày, mở lại có lý do; chỉ thêm, dòng mới nhất là trạng thái.';

CREATE INDEX IF NOT EXISTS balance_evidence_day ON tien.balance_evidence (account_id, as_of_date, id);
CREATE INDEX IF NOT EXISTS day_review_day ON tien.day_review (account_id, business_date, track, id);
CREATE INDEX IF NOT EXISTS statement_import_period ON tien.statement_import (account_id, period_from, period_to)
    WHERE status IN ('validated', 'committed');

CREATE OR REPLACE TRIGGER statement_file_immutable BEFORE UPDATE OR DELETE ON tien.statement_file FOR EACH ROW
    EXECUTE FUNCTION tien._reject_change();
CREATE OR REPLACE TRIGGER balance_evidence_immutable BEFORE UPDATE OR DELETE ON tien.balance_evidence FOR EACH ROW
    EXECUTE FUNCTION tien._reject_change();
CREATE OR REPLACE TRIGGER day_review_immutable BEFORE UPDATE OR DELETE ON tien.day_review FOR EACH ROW
    EXECUTE FUNCTION tien._reject_change();
DO $$
DECLARE t text;
BEGIN
    FOREACH t IN ARRAY ARRAY['statement_file', 'balance_evidence', 'day_review'] LOOP
        EXECUTE format('CREATE OR REPLACE TRIGGER %I BEFORE TRUNCATE ON tien.%I FOR EACH STATEMENT EXECUTE FUNCTION tien._reject_change()',
                       t || '_no_truncate', t);
    END LOOP;
END $$;

-- ---------------------------------------------------------------------------------------------------------------------------
-- Hàm phụ lát 2: không cấp cho ai.

-- Trạng thái hiện tại của một mạch ký của một ngày: dòng day_review mới nhất; chưa có dòng thì coverage 'unconfirmed', business 'open'.
CREATE OR REPLACE FUNCTION tien._day_status(p_account bigint, p_date date, p_track text) RETURNS text
LANGUAGE sql STABLE SECURITY DEFINER SET search_path TO 'pg_catalog', 'tien', 'pg_temp' AS $$
    SELECT coalesce((SELECT CASE r.action WHEN 'sign' THEN 'signed' ELSE 'reopened' END FROM tien.day_review r
                      WHERE r.account_id = p_account AND r.business_date = p_date AND r.track = p_track
                      ORDER BY r.id DESC LIMIT 1),
                    CASE p_track WHEN 'coverage' THEN 'unconfirmed' ELSE 'open' END)
$$;

-- Đã ký số dư ngày D thì không thêm, không hủy giao dịch có ngày ghi sổ D (BR-IM13): mở lại ngày trước. Phân bổ (chỉ tăng version)
-- không bị chặn; commit lô chỉ xác nhận trùng không tạo giao dịch nên vẫn được.
CREATE OR REPLACE FUNCTION tien._guard_signed_day() RETURNS trigger
LANGUAGE plpgsql SET search_path TO 'pg_catalog', 'tien', 'pg_temp' AS $$
DECLARE v_date date;
BEGIN
    IF TG_OP = 'INSERT' THEN
        v_date := NEW.booking_date;
    ELSIF OLD.voided_event IS NULL AND NEW.voided_event IS NOT NULL THEN
        v_date := OLD.booking_date;
    ELSE
        RETURN NEW;
    END IF;
    IF tien._day_status(NEW.account_id, v_date, 'coverage') = 'signed' THEN
        RAISE EXCEPTION 'DAY_SIGNED' USING DETAIL = to_char(v_date, 'YYYY-MM-DD');
    END IF;
    RETURN NEW;
END $$;
CREATE OR REPLACE TRIGGER bank_transaction_signed_day BEFORE INSERT OR UPDATE OF voided_event ON tien.bank_transaction
    FOR EACH ROW EXECUTE FUNCTION tien._guard_signed_day();

-- Độ phủ từng ngày của [p_from, p_to] (BR-IM11, BR-IM12), từ lô đã commit (lô hủy, bỏ, chờ không tính): 'full' khi có lô phủ ngày
-- đó mà ngày trước ngày cuối của lô hoặc lô ghi ngày cuối đã trọn; 'partial' khi chỉ có lô mà ngày là ngày cuối chưa trọn;
-- 'missing' khi không lô nào phủ. Ngày tính bằng số nguyên (không qua timestamp nên không phụ thuộc múi giờ của phiên).
CREATE OR REPLACE FUNCTION tien._coverage(p_account bigint, p_from date, p_to date) RETURNS TABLE (day date, state text)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path TO 'pg_catalog', 'tien', 'pg_temp' AS $$
    SELECT p_from + g.k, CASE WHEN bool_or(i.period_to > p_from + g.k OR i.last_day_complete) THEN 'full'
                              WHEN count(i.id) > 0 THEN 'partial' ELSE 'missing' END
      FROM generate_series(0, p_to - p_from) g(k)
      LEFT JOIN tien.statement_import i ON i.account_id = p_account AND i.status = 'committed'
                                        AND p_from + g.k BETWEEN i.period_from AND i.period_to
     GROUP BY g.k
     ORDER BY g.k
$$;

-- Số dư sổ cuối ngày: số dư mở + giao dịch chưa hủy có ngày ghi sổ ≤ ngày đó (vào cộng, ra trừ); chưa có số dư mở → NULL.
CREATE OR REPLACE FUNCTION tien._ledger_closing(p_account bigint, p_date date) RETURNS bigint
LANGUAGE sql STABLE SECURITY DEFINER SET search_path TO 'pg_catalog', 'tien', 'pg_temp' AS $$
    SELECT (o.amount_minor + coalesce((SELECT sum(CASE t.direction WHEN 'in' THEN t.amount_minor ELSE -t.amount_minor END)
                                         FROM tien.bank_transaction t
                                        WHERE t.account_id = p_account AND t.voided_event IS NULL AND t.booking_date <= p_date), 0))::bigint
      FROM tien.account_opening o WHERE o.account_id = p_account
$$;

-- Người nhập của ngày (BR-DC5): người xem trước hoặc commit một lô đã commit phủ ngày đó.
CREATE OR REPLACE FUNCTION tien._day_importers(p_account bigint, p_date date) RETURNS text[]
LANGUAGE sql STABLE SECURITY DEFINER SET search_path TO 'pg_catalog', 'tien', 'pg_temp' AS $$
    SELECT coalesce(array_agg(DISTINCT e.actor ORDER BY e.actor), '{}')
      FROM tien.statement_import i JOIN tien.event e ON e.id IN (i.created_event, i.committed_event)
     WHERE i.account_id = p_account AND i.status = 'committed' AND p_date BETWEEN i.period_from AND i.period_to
$$;

-- Bằng chứng số dư cuối ngày theo ngân hàng (BR-DC4): mỗi lô đã commit phủ TRỌN ngày và có số dư đầu hoặc cuối của file cho một
-- giá trị (số dư đầu + dòng của file tới hết ngày; không có số dư đầu thì số dư cuối − dòng sau ngày); thêm bản nhập tay mới nhất.
-- `current`: lô mới nhất (mã lô lớn nhất) trong số đó và bản nhập tay là bằng chứng dùng để ký; lô cũ hơn chỉ để xem, vì ngân hàng
-- có thể ghi lùi ngày một giao dịch sau khi file cũ đã tải (file cũ thành ảnh chụp lỗi thời, không phải lỗi của sổ).
-- Dòng của lô đã commit đều hợp lệ (commit chặn lô có dòng lỗi) nên chiều và số tiền đọc thẳng từ StatementLine đã lưu; phép đổi
-- kiểu vẫn có pg_input_is_valid vì planner có thể tính biểu thức trên mọi dòng gốc (cả dòng lỗi của lô bị bỏ) trước khi lọc theo lô.
CREATE OR REPLACE FUNCTION tien._day_evidence(p_account bigint, p_date date) RETURNS jsonb
LANGUAGE sql STABLE SECURITY DEFINER SET search_path TO 'pg_catalog', 'tien', 'pg_temp' AS $$
    SELECT coalesce(jsonb_agg(x.e ORDER BY x.ord, x.id), '[]'::jsonb) FROM (
        SELECT 1 AS ord, i.id, jsonb_build_object('source', 'file', 'import_id', i.id, 'amount_minor', (CASE
                   WHEN i.opening_minor IS NOT NULL THEN i.opening_minor + coalesce(sum(s.signed) FILTER (WHERE s.bdate <= p_date), 0)
                   ELSE i.closing_minor - coalesce(sum(s.signed) FILTER (WHERE s.bdate > p_date), 0) END)::bigint::text,
                   'current', i.id = max(i.id) OVER ()) AS e
          FROM tien.statement_import i
          LEFT JOIN LATERAL (SELECT (r.line ->> 'booking_date')::date AS bdate,
                                    CASE WHEN pg_input_is_valid(r.line ->> 'amount_minor', 'bigint') THEN
                                        CASE r.line ->> 'direction' WHEN 'in' THEN (r.line ->> 'amount_minor')::bigint
                                                                    WHEN 'out' THEN -(r.line ->> 'amount_minor')::bigint END END AS signed
                               FROM tien.raw_statement_line r WHERE r.import_id = i.id) s ON true
         WHERE i.account_id = p_account AND i.status = 'committed' AND p_date BETWEEN i.period_from AND i.period_to
           AND (p_date < i.period_to OR i.last_day_complete) AND (i.opening_minor IS NOT NULL OR i.closing_minor IS NOT NULL)
         GROUP BY i.id
        UNION ALL
        SELECT 2, b.id, jsonb_build_object('source', b.source, 'evidence_id', b.id, 'amount_minor', b.amount_minor::text,
                                           'note', b.note, 'role_overlap', b.role_overlap, 'actor', ev.actor, 'at', ev.at,
                                           'current', true)
          FROM tien.balance_evidence b JOIN tien.event ev ON ev.id = b.created_event
         WHERE b.id = (SELECT max(b2.id) FROM tien.balance_evidence b2 WHERE b2.account_id = p_account AND b2.as_of_date = p_date)
    ) x
$$;

-- Kiểm ngày (I-3, BR-DC3): MỘT hàm cho màn hình (get_day) và lệnh ký (sign_day_coverage). ready khi không có lý do nào.
CREATE OR REPLACE FUNCTION tien._day_check(p_account bigint, p_date date) RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path TO 'pg_catalog', 'tien', 'pg_temp' AS $$
DECLARE v_open tien.account_opening; v_cov text := 'missing'; v_gaps date[]; v_gap_count bigint := 0; v_pending bigint[];
        v_ledger bigint; v_evidence jsonb := '[]'::jsonb; v_reasons text[] := '{}';
BEGIN
    SELECT * INTO v_open FROM tien.account_opening WHERE account_id = p_account;
    IF NOT FOUND THEN
        v_reasons := ARRAY['NO_OPENING'];
    ELSIF p_date > tien._today() THEN
        v_cov := 'future';
        v_reasons := ARRAY['DAY_FUTURE'];
    ELSIF p_date < v_open.as_of THEN
        v_cov := 'before_opening';
        v_reasons := ARRAY['BEFORE_OPENING'];
    ELSE
        SELECT c.state INTO v_cov FROM tien._coverage(p_account, p_date, p_date) c;
        IF v_cov = 'partial' THEN
            v_reasons := v_reasons || 'DAY_INCOMPLETE'::text;
        ELSIF v_cov = 'missing' THEN
            v_reasons := v_reasons || 'DAY_MISSING'::text;
        END IF;
        SELECT array_agg(c.day ORDER BY c.day), count(*) INTO v_gaps, v_gap_count
          FROM tien._coverage(p_account, v_open.as_of, p_date - 1) c WHERE c.state <> 'full';
        IF v_gap_count > 0 THEN v_reasons := v_reasons || 'MISSING_DAYS_BEFORE'::text; END IF;
        SELECT array_agg(i.id ORDER BY i.id) INTO v_pending FROM tien.statement_import i
         WHERE i.account_id = p_account AND i.status = 'validated' AND i.period_from <= p_date;
        IF v_pending IS NOT NULL THEN v_reasons := v_reasons || 'PENDING_IMPORT'::text; END IF;
        v_ledger := tien._ledger_closing(p_account, p_date);
        SELECT coalesce(jsonb_agg(x.e || jsonb_build_object('difference_minor', (v_ledger - (x.e ->> 'amount_minor')::bigint)::text)
                                  ORDER BY x.o), '[]'::jsonb)
          INTO v_evidence FROM jsonb_array_elements(tien._day_evidence(p_account, p_date)) WITH ORDINALITY x(e, o);
        IF NOT EXISTS (SELECT 1 FROM jsonb_array_elements(v_evidence) e WHERE (e ->> 'current')::boolean) THEN
            v_reasons := v_reasons || 'NO_EVIDENCE'::text;
        ELSIF EXISTS (SELECT 1 FROM jsonb_array_elements(v_evidence) e
                       WHERE (e ->> 'current')::boolean AND e ->> 'difference_minor' <> '0') THEN
            v_reasons := v_reasons || 'BALANCE_DIFFERENCE'::text;
        END IF;
    END IF;
    RETURN jsonb_build_object('date', p_date, 'coverage', v_cov, 'missing_before', coalesce(to_jsonb(v_gaps[1:31]), '[]'::jsonb),
        'missing_before_count', v_gap_count, 'pending_imports', coalesce(to_jsonb(v_pending), '[]'::jsonb),
        'ledger_closing_minor', v_ledger::text, 'evidence', v_evidence, 'reasons', to_jsonb(v_reasons),
        'ready', cardinality(v_reasons) = 0);
END $$;

-- Số giao dịch chưa hủy của một ngày theo trạng thái phân loại (ký đối soát lưu lại lúc ký, BR-DC2).
CREATE OR REPLACE FUNCTION tien._day_business(p_account bigint, p_date date) RETURNS jsonb
LANGUAGE sql STABLE SECURITY DEFINER SET search_path TO 'pg_catalog', 'tien', 'pg_temp' AS $$
    SELECT jsonb_build_object('transactions', count(*),
        'not_fully_allocated', count(*) FILTER (WHERE t.status NOT IN ('applied', 'matched')),
        'in', jsonb_build_object('count', count(*) FILTER (WHERE t.direction = 'in'),
                                 'amount_minor', coalesce(sum(t.amount_minor) FILTER (WHERE t.direction = 'in'), 0)::bigint::text,
                                 'unidentified', count(*) FILTER (WHERE t.status = 'unidentified'),
                                 'unapplied', count(*) FILTER (WHERE t.status = 'unapplied'),
                                 'partial', count(*) FILTER (WHERE t.direction = 'in' AND t.status = 'partial'),
                                 'applied', count(*) FILTER (WHERE t.status = 'applied')),
        'out', jsonb_build_object('count', count(*) FILTER (WHERE t.direction = 'out'),
                                  'amount_minor', coalesce(sum(t.amount_minor) FILTER (WHERE t.direction = 'out'), 0)::bigint::text,
                                  'unmatched', count(*) FILTER (WHERE t.status = 'unmatched'),
                                  'partial', count(*) FILTER (WHERE t.direction = 'out' AND t.status = 'partial'),
                                  'matched', count(*) FILTER (WHERE t.status = 'matched')))
      FROM tien.v_transaction t WHERE t.account_id = p_account AND t.booking_date = p_date AND t.voided_event IS NULL
$$;

-- Ai làm, lúc nào (từ vết); NULL khi không có vết.
CREATE OR REPLACE FUNCTION tien._who(p_event bigint) RETURNS jsonb
LANGUAGE sql STABLE SECURITY DEFINER SET search_path TO 'pg_catalog', 'tien', 'pg_temp' AS $$
    SELECT jsonb_build_object('actor', e.actor, 'actor_kind', e.actor_kind, 'at', e.at) FROM tien.event e WHERE e.id = p_event
$$;

-- Vai của người đang đọc ở phạm vi một tài khoản (màn hình chỉ vẽ nút người đó dùng được; quyền thật vẫn kiểm trong từng lệnh).
CREATE OR REPLACE FUNCTION tien._my_roles(p_entity bigint, p_account bigint) RETURNS jsonb
LANGUAGE sql STABLE SECURITY DEFINER SET search_path TO 'pg_catalog', 'tien', 'pg_temp' AS $$
    SELECT coalesce(jsonb_agg(DISTINCT g.role ORDER BY g.role), '[]'::jsonb) FROM tien.access_grant g
     WHERE g.login = tien._actor() AND g.revoked_event IS NULL
       AND (g.account_id = p_account OR (g.account_id IS NULL AND g.legal_entity_id = p_entity))
$$;

-- Cần một trong các vai ở phạm vi: không có thì ENTITY_SCOPE (có vai đó ở chỗ khác) hoặc TIEN_FORBIDDEN, như _require của lát 1.
CREATE OR REPLACE FUNCTION tien._require_any(p_roles text[], p_entity bigint, p_account bigint) RETURNS void
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path TO 'pg_catalog', 'tien', 'pg_temp' AS $$
BEGIN
    IF tien._has_role(p_roles, p_entity, p_account) THEN RETURN; END IF;
    IF EXISTS (SELECT 1 FROM tien.access_grant g WHERE g.login = tien._actor() AND g.revoked_event IS NULL AND g.role = ANY (p_roles)) THEN
        RAISE EXCEPTION 'ENTITY_SCOPE';
    END IF;
    RAISE EXCEPTION 'TIEN_FORBIDDEN';
END $$;

-- Mở đầu hàm đọc: người làm, tài khoản có thật, vai (p_role NULL: vai bất kỳ) ở phạm vi tài khoản.
CREATE OR REPLACE FUNCTION tien._read_account(p_account bigint, p_role text) RETURNS tien.financial_account
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path TO 'pg_catalog', 'tien', 'pg_temp' AS $$
DECLARE v_acc tien.financial_account;
BEGIN
    PERFORM tien._actor();
    PERFORM tien._actor_kind();
    SELECT * INTO v_acc FROM tien.financial_account WHERE id = p_account;
    IF NOT FOUND THEN RAISE EXCEPTION 'INVALID_COMMAND'; END IF;
    PERFORM tien._require(p_role, v_acc.legal_entity_id, v_acc.id);
    RETURN v_acc;
END $$;

-- Ngày đã ký số dư có dòng mới hoặc nghi trùng trong một lô (commit sẽ bị DAY_SIGNED nếu tạo giao dịch ở ngày đó).
CREATE OR REPLACE FUNCTION tien._signed_days(p_account bigint, p_classes jsonb, p_lines jsonb) RETURNS jsonb
LANGUAGE sql STABLE SECURITY DEFINER SET search_path TO 'pg_catalog', 'tien', 'pg_temp' AS $$
    SELECT coalesce(jsonb_agg(x.d ORDER BY x.d), '[]'::jsonb) FROM (
        SELECT DISTINCT (l.e ->> 'booking_date')::date AS d
          FROM jsonb_array_elements(p_classes) c
          JOIN jsonb_array_elements(p_lines) WITH ORDINALITY l(e, ord) ON l.ord = (c ->> 'seq')::bigint
         WHERE c ->> 'class' IN ('new', 'suspect')) x
     WHERE tien._day_status(p_account, x.d, 'coverage') = 'signed'
$$;

-- ---------------------------------------------------------------------------------------------------------------------------
-- Hàm lệnh (cấp cho tien_app). Thứ tự chung như lát 1: người làm, khóa lặp, hình dạng payload → khóa dòng tài khoản → vai → khóa
-- lặp đã có → kiểm trạng thái, nội dung → vết → ghi → lưu khóa lặp.

-- Xem trước (thay bản lát 1): như lát 1, thêm file gốc tùy chọn `file: {name, media_type, content_base64}` (băm nội dung phải bằng
-- file_sha256; cùng file đã lưu ở tài khoản thì dùng lại) và `signed_days` trong kết quả.
CREATE OR REPLACE FUNCTION tien.preview_import(p jsonb) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path TO 'pg_catalog', 'tien', 'pg_temp' AS $$
DECLARE v_key text := tien._begin(p); v_acc tien.financial_account; v_scope text; v_retry jsonb; v_sha text; v_tpl text;
        v_from date; v_to date; v_opening bigint; v_closing bigint; v_last boolean; v_old tien.statement_import; v_rows bigint;
        v_cls jsonb; v_id bigint; v_event bigint; v_result jsonb;
        v_file jsonb; v_b64 text; v_bytes bytea; v_name text; v_media text; v_file_id bigint; v_reused boolean := false;
BEGIN
    PERFORM tien._keys(p, ARRAY['idempotency_key', 'account_id', 'file_sha256', 'template', 'period_from', 'period_to', 'lines'],
                       ARRAY['opening_minor', 'closing_minor', 'last_day_complete', 'file']);
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
    v_file := p -> 'file';
    IF v_file IS NOT NULL AND jsonb_typeof(v_file) <> 'null' THEN
        PERFORM tien._keys(v_file, ARRAY['name', 'media_type', 'content_base64'], ARRAY[]::text[]);
        v_name := tien._text(v_file -> 'name', 200);
        v_media := tien._text(v_file -> 'media_type', 100);
        IF jsonb_typeof(v_file -> 'content_base64') IS DISTINCT FROM 'string' THEN RAISE EXCEPTION 'INVALID_COMMAND'; END IF;
        v_b64 := v_file ->> 'content_base64';
        IF v_name IS NULL OR strpos(v_name, '/') > 0
           OR v_media IS NULL OR v_media NOT IN ('application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', 'text/csv')
           OR char_length(v_b64) NOT BETWEEN 4 AND 5592408 OR char_length(v_b64) % 4 <> 0 OR v_b64 !~ '^[A-Za-z0-9+/]+={0,2}$' THEN
            RAISE EXCEPTION 'INVALID_COMMAND';
        END IF;
        v_bytes := decode(v_b64, 'base64');
        IF octet_length(v_bytes) NOT BETWEEN 1 AND 4194304 OR encode(sha256(v_bytes), 'hex') <> v_sha THEN
            RAISE EXCEPTION 'INVALID_COMMAND';
        END IF;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM tien.account_opening WHERE account_id = v_acc.id) THEN RAISE EXCEPTION 'NO_OPENING'; END IF;
    SELECT * INTO v_old FROM tien.statement_import WHERE account_id = v_acc.id AND file_sha256 = v_sha AND status = 'committed';
    IF FOUND THEN
        SELECT count(*) INTO v_rows FROM tien.raw_statement_line WHERE import_id = v_old.id;
        RETURN tien._finish(v_scope, 'preview_import', p, jsonb_build_object('import_id', v_old.id, 'status', 'committed',
            'same_file', true, 'counts', jsonb_build_object('rows', v_rows, 'new', 0, 'duplicate', v_rows, 'suspect', 0, 'error', 0)));
    END IF;
    v_cls := tien._classify(v_acc.id, v_tpl, v_from, v_to, v_opening, v_closing, tien._today(), p -> 'lines');
    v_id := nextval(pg_get_serial_sequence('tien.statement_import', 'id'));
    IF v_bytes IS NOT NULL THEN
        SELECT id INTO v_file_id FROM tien.statement_file WHERE account_id = v_acc.id AND file_sha256 = v_sha;
        v_reused := FOUND;
        IF NOT v_reused THEN v_file_id := nextval(pg_get_serial_sequence('tien.statement_file', 'id')); END IF;
    END IF;
    v_event := tien._event('import_preview', v_acc.legal_entity_id, v_acc.id, '{}', jsonb_build_object(
        'import', jsonb_build_object('id', v_id, 'status', 'validated', 'file_sha256', v_sha, 'template', v_tpl, 'period_from', v_from,
                                     'period_to', v_to, 'opening_minor', v_opening::text, 'closing_minor', v_closing::text,
                                     'last_day_complete', v_last, 'preview_hash', v_cls ->> 'hash', 'counts', v_cls -> 'counts',
                                     'file_id', v_file_id),
        'file', CASE WHEN v_bytes IS NULL THEN NULL ELSE jsonb_build_object('id', v_file_id, 'name', v_name, 'media_type', v_media,
                                                                             'byte_size', octet_length(v_bytes), 'reused', v_reused) END,
        'account_version', v_acc.version, 'breaks', v_cls -> 'breaks'), v_key);
    IF v_bytes IS NOT NULL AND NOT v_reused THEN
        INSERT INTO tien.statement_file(id, account_id, file_sha256, byte_size, file_name, media_type, content, created_event)
        OVERRIDING SYSTEM VALUE VALUES (v_file_id, v_acc.id, v_sha, octet_length(v_bytes), v_name, v_media, v_bytes, v_event);
    END IF;
    INSERT INTO tien.statement_import(id, account_id, file_sha256, template, period_from, period_to, opening_minor, closing_minor,
                                      last_day_complete, preview_account_version, preview_hash, counts, created_event, file_id)
    OVERRIDING SYSTEM VALUE VALUES (v_id, v_acc.id, v_sha, v_tpl, v_from, v_to, v_opening, v_closing, v_last, v_acc.version,
                                    v_cls ->> 'hash', v_cls -> 'counts', v_event, v_file_id);
    INSERT INTO tien.raw_statement_line(import_id, seq, line_no, line, cells, line_hash)
    SELECT v_id, x.ord, (x.e ->> 'line_no')::integer, x.e - 'cells', x.e -> 'cells', encode(sha256(convert_to(x.e::text, 'UTF8')), 'hex')
      FROM jsonb_array_elements(p -> 'lines') WITH ORDINALITY x(e, ord);
    v_result := jsonb_build_object('import_id', v_id, 'status', 'validated', 'template', v_tpl, 'preview_account_version', v_acc.version,
        'preview_hash', v_cls ->> 'hash', 'counts', v_cls -> 'counts', 'balance', v_cls -> 'balance', 'breaks', v_cls -> 'breaks',
        'lines', (SELECT coalesce(jsonb_agg(x - 'fp' ORDER BY (x ->> 'seq')::integer), '[]'::jsonb) FROM jsonb_array_elements(v_cls -> 'lines') x),
        'file_id', v_file_id, 'signed_days', tien._signed_days(v_acc.id, v_cls -> 'lines', p -> 'lines'));
    RETURN tien._finish(v_scope, 'preview_import', p, v_result);
END $$;

-- Bằng chứng số dư cuối ngày theo ngân hàng nhập tay (BR-DC4): ngày từ số dư mở tới hôm nay, nguồn, ghi chú bắt buộc.
CREATE OR REPLACE FUNCTION tien.record_balance_evidence(p jsonb) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path TO 'pg_catalog', 'tien', 'pg_temp' AS $$
DECLARE v_key text := tien._begin(p); v_acc tien.financial_account; v_scope text; v_retry jsonb; v_open tien.account_opening;
        v_date date; v_amount bigint; v_source text; v_note text; v_overlap boolean; v_event bigint; v_id bigint;
BEGIN
    PERFORM tien._keys(p, ARRAY['idempotency_key', 'account_id', 'as_of_date', 'amount_minor', 'source'], ARRAY['note']);
    v_acc := tien._lock_account(tien._id(p -> 'account_id'));
    PERFORM tien._require('tien_review', v_acc.legal_entity_id, v_acc.id);
    v_scope := 'account:' || v_acc.id;
    v_retry := tien._replay(v_scope, 'record_balance_evidence', p);
    IF v_retry IS NOT NULL THEN RETURN v_retry; END IF;
    v_date := tien._date(p -> 'as_of_date');
    v_amount := tien._minor(p -> 'amount_minor', true);
    v_source := tien._text(p -> 'source', 20);
    v_note := tien._text(p -> 'note', 500);
    IF v_date IS NULL OR v_amount IS NULL OR v_source IS NULL OR v_source NOT IN ('bank_pdf', 'bank_app', 'bank_paper', 'other')
       OR v_date > tien._today() THEN
        RAISE EXCEPTION 'INVALID_COMMAND';
    END IF;
    SELECT * INTO v_open FROM tien.account_opening WHERE account_id = v_acc.id;
    IF NOT FOUND THEN RAISE EXCEPTION 'NO_OPENING'; END IF;
    IF v_date < v_open.as_of THEN RAISE EXCEPTION 'INVALID_COMMAND'; END IF;
    IF v_note IS NULL THEN RAISE EXCEPTION 'REASON_REQUIRED'; END IF;
    v_overlap := tien._actor() = ANY (tien._day_importers(v_acc.id, v_date));
    v_id := nextval(pg_get_serial_sequence('tien.balance_evidence', 'id'));
    v_event := tien._event('balance_evidence', v_acc.legal_entity_id, v_acc.id, '{}', jsonb_build_object('evidence', jsonb_build_object(
        'id', v_id, 'as_of_date', v_date, 'amount_minor', v_amount::text, 'source', v_source, 'note', v_note, 'role_overlap', v_overlap)), v_key);
    INSERT INTO tien.balance_evidence(id, account_id, as_of_date, amount_minor, source, note, role_overlap, created_event)
    OVERRIDING SYSTEM VALUE VALUES (v_id, v_acc.id, v_date, v_amount, v_source, v_note, v_overlap, v_event);
    RETURN tien._finish(v_scope, 'record_balance_evidence', p, jsonb_build_object('evidence_id', v_id, 'account_id', v_acc.id,
        'as_of_date', v_date, 'role_overlap', v_overlap));
END $$;

-- Ký số dư (I-3, BR-DC3): kiểm ngày phải sẵn sàng; expected_version = version tài khoản người ký đã xem. Đã ký → trả lại, không ghi.
CREATE OR REPLACE FUNCTION tien.sign_day_coverage(p jsonb) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path TO 'pg_catalog', 'tien', 'pg_temp' AS $$
DECLARE v_key text := tien._begin(p); v_acc tien.financial_account; v_scope text; v_retry jsonb; v_date date; v_note text;
        v_status text; v_check jsonb; v_importers text[]; v_overlap boolean; v_snapshot jsonb; v_event bigint;
BEGIN
    PERFORM tien._keys(p, ARRAY['idempotency_key', 'account_id', 'business_date', 'expected_version'], ARRAY['note']);
    v_acc := tien._lock_account(tien._id(p -> 'account_id'));
    PERFORM tien._require('tien_review', v_acc.legal_entity_id, v_acc.id);
    v_scope := 'account:' || v_acc.id;
    v_retry := tien._replay(v_scope, 'sign_day_coverage', p);
    IF v_retry IS NOT NULL THEN RETURN v_retry; END IF;
    v_date := tien._date(p -> 'business_date');
    v_note := tien._text(p -> 'note', 500);
    IF v_date IS NULL OR jsonb_typeof(p -> 'expected_version') IS DISTINCT FROM 'number'
       OR (p ->> 'expected_version') !~ '^(0|[1-9][0-9]{0,17})$' THEN
        RAISE EXCEPTION 'INVALID_COMMAND';
    END IF;
    IF v_acc.version <> (p ->> 'expected_version')::bigint THEN RAISE EXCEPTION 'STALE_VERSION'; END IF;
    v_status := tien._day_status(v_acc.id, v_date, 'coverage');
    IF v_status = 'signed' THEN
        RETURN tien._finish(v_scope, 'sign_day_coverage', p, jsonb_build_object('account_id', v_acc.id, 'business_date', v_date,
            'coverage_status', 'signed', 'changed', false));
    END IF;
    v_check := tien._day_check(v_acc.id, v_date);
    IF NOT (v_check ->> 'ready')::boolean THEN
        RAISE EXCEPTION 'DAY_NOT_READY' USING DETAIL = (SELECT string_agg(r, ',') FROM jsonb_array_elements_text(v_check -> 'reasons') r);
    END IF;
    v_importers := tien._day_importers(v_acc.id, v_date);
    v_overlap := tien._actor() = ANY (v_importers)
                 OR EXISTS (SELECT 1 FROM jsonb_array_elements(v_check -> 'evidence') e WHERE e ->> 'actor' = tien._actor());
    v_snapshot := jsonb_build_object('ledger_closing_minor', v_check -> 'ledger_closing_minor', 'evidence', v_check -> 'evidence',
                                     'importers', to_jsonb(v_importers), 'account_version', v_acc.version);
    v_event := tien._event('day_sign_coverage', v_acc.legal_entity_id, v_acc.id,
        jsonb_build_object('day', jsonb_build_object('date', v_date, 'coverage_status', v_status)),
        jsonb_build_object('day', jsonb_build_object('date', v_date, 'coverage_status', 'signed'), 'snapshot', v_snapshot,
                           'role_overlap', v_overlap, 'note', v_note), v_key);
    INSERT INTO tien.day_review(account_id, business_date, track, action, role_overlap, snapshot, note, created_event)
    VALUES (v_acc.id, v_date, 'coverage', 'sign', v_overlap, v_snapshot, v_note, v_event);
    RETURN tien._finish(v_scope, 'sign_day_coverage', p, jsonb_build_object('account_id', v_acc.id, 'business_date', v_date,
        'coverage_status', 'signed', 'changed', true, 'role_overlap', v_overlap,
        'ledger_closing_minor', v_check -> 'ledger_closing_minor'));
END $$;

-- Ký đối soát (BR-DC2): số dư của ngày đã ký; được ký khi còn khoản chưa phân bổ, số đếm lúc ký vào snapshot. Đã ký → trả lại.
CREATE OR REPLACE FUNCTION tien.sign_day_business(p jsonb) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path TO 'pg_catalog', 'tien', 'pg_temp' AS $$
DECLARE v_key text := tien._begin(p); v_acc tien.financial_account; v_scope text; v_retry jsonb; v_date date; v_note text;
        v_status text; v_importers text[]; v_overlap boolean; v_snapshot jsonb; v_event bigint;
BEGIN
    PERFORM tien._keys(p, ARRAY['idempotency_key', 'account_id', 'business_date'], ARRAY['note']);
    v_acc := tien._lock_account(tien._id(p -> 'account_id'));
    PERFORM tien._require('tien_review', v_acc.legal_entity_id, v_acc.id);
    v_scope := 'account:' || v_acc.id;
    v_retry := tien._replay(v_scope, 'sign_day_business', p);
    IF v_retry IS NOT NULL THEN RETURN v_retry; END IF;
    v_date := tien._date(p -> 'business_date');
    v_note := tien._text(p -> 'note', 500);
    IF v_date IS NULL THEN RAISE EXCEPTION 'INVALID_COMMAND'; END IF;
    IF tien._day_status(v_acc.id, v_date, 'coverage') <> 'signed' THEN
        RAISE EXCEPTION 'DAY_NOT_READY' USING DETAIL = 'COVERAGE_NOT_SIGNED';
    END IF;
    v_status := tien._day_status(v_acc.id, v_date, 'business');
    IF v_status = 'signed' THEN
        RETURN tien._finish(v_scope, 'sign_day_business', p, jsonb_build_object('account_id', v_acc.id, 'business_date', v_date,
            'business_status', 'signed', 'changed', false));
    END IF;
    v_importers := tien._day_importers(v_acc.id, v_date);
    v_overlap := tien._actor() = ANY (v_importers)
                 OR EXISTS (SELECT 1 FROM tien.event e JOIN tien.bank_transaction t ON t.id = (e."after" ->> 'transaction')::bigint
                             WHERE e.account_id = v_acc.id AND e.kind = 'allocation_set' AND e.actor = tien._actor()
                               AND t.account_id = v_acc.id AND t.booking_date = v_date);
    v_snapshot := tien._day_business(v_acc.id, v_date) || jsonb_build_object('importers', to_jsonb(v_importers));
    v_event := tien._event('day_sign_business', v_acc.legal_entity_id, v_acc.id,
        jsonb_build_object('day', jsonb_build_object('date', v_date, 'business_status', v_status)),
        jsonb_build_object('day', jsonb_build_object('date', v_date, 'business_status', 'signed'), 'snapshot', v_snapshot,
                           'role_overlap', v_overlap, 'note', v_note), v_key);
    INSERT INTO tien.day_review(account_id, business_date, track, action, role_overlap, snapshot, note, created_event)
    VALUES (v_acc.id, v_date, 'business', 'sign', v_overlap, v_snapshot, v_note, v_event);
    RETURN tien._finish(v_scope, 'sign_day_business', p, jsonb_build_object('account_id', v_acc.id, 'business_date', v_date,
        'business_status', 'signed', 'changed', true, 'role_overlap', v_overlap,
        'not_fully_allocated', v_snapshot -> 'not_fully_allocated'));
END $$;

-- Mở lại ngày (lý do bắt buộc): mạch coverage kéo theo đối soát nếu đã ký; mạch business chỉ mở đối soát.
CREATE OR REPLACE FUNCTION tien.reopen_day(p jsonb) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path TO 'pg_catalog', 'tien', 'pg_temp' AS $$
DECLARE v_key text := tien._begin(p); v_acc tien.financial_account; v_scope text; v_retry jsonb; v_date date; v_track text;
        v_reason text; v_cov text; v_bus text; v_new_cov text; v_new_bus text; v_event bigint;
BEGIN
    PERFORM tien._keys(p, ARRAY['idempotency_key', 'account_id', 'business_date', 'track'], ARRAY['reason']);
    v_acc := tien._lock_account(tien._id(p -> 'account_id'));
    PERFORM tien._require('tien_review', v_acc.legal_entity_id, v_acc.id);
    v_scope := 'account:' || v_acc.id;
    v_retry := tien._replay(v_scope, 'reopen_day', p);
    IF v_retry IS NOT NULL THEN RETURN v_retry; END IF;
    v_date := tien._date(p -> 'business_date');
    v_track := tien._text(p -> 'track', 20);
    v_reason := tien._text(p -> 'reason', 500);
    IF v_date IS NULL OR v_track IS NULL OR v_track NOT IN ('coverage', 'business') THEN RAISE EXCEPTION 'INVALID_COMMAND'; END IF;
    IF v_reason IS NULL THEN RAISE EXCEPTION 'REASON_REQUIRED'; END IF;
    v_cov := tien._day_status(v_acc.id, v_date, 'coverage');
    v_bus := tien._day_status(v_acc.id, v_date, 'business');
    IF (v_track = 'coverage' AND v_cov <> 'signed') OR (v_track = 'business' AND v_bus <> 'signed') THEN
        RAISE EXCEPTION 'INVALID_COMMAND';
    END IF;
    v_new_cov := CASE WHEN v_track = 'coverage' THEN 'reopened' ELSE v_cov END;
    v_new_bus := CASE WHEN v_bus = 'signed' THEN 'reopened' ELSE v_bus END;
    v_event := tien._event('day_reopen', v_acc.legal_entity_id, v_acc.id,
        jsonb_build_object('day', jsonb_build_object('date', v_date, 'coverage_status', v_cov, 'business_status', v_bus)),
        jsonb_build_object('day', jsonb_build_object('date', v_date, 'coverage_status', v_new_cov, 'business_status', v_new_bus),
                           'track', v_track, 'reason', v_reason), v_key);
    IF v_track = 'coverage' THEN
        INSERT INTO tien.day_review(account_id, business_date, track, action, role_overlap, snapshot, note, created_event)
        VALUES (v_acc.id, v_date, 'coverage', 'reopen', false, '{}', v_reason, v_event);
    END IF;
    IF v_bus = 'signed' THEN
        INSERT INTO tien.day_review(account_id, business_date, track, action, role_overlap, snapshot, note, created_event)
        VALUES (v_acc.id, v_date, 'business', 'reopen', false, '{}', v_reason, v_event);
    END IF;
    RETURN tien._finish(v_scope, 'reopen_day', p, jsonb_build_object('account_id', v_acc.id, 'business_date', v_date,
        'coverage_status', v_new_cov, 'business_status', v_new_bus));
END $$;

-- ---------------------------------------------------------------------------------------------------------------------------
-- Hàm đọc lát 2: cần một vai bất kỳ ở phạm vi tài khoản (trừ khi ghi khác). Tiền là chuỗi; NULL là chưa biết, không phải 0. Mô tả
-- chuyển khoản, ô gốc, tên file chỉ trả cho tien_nhap/tien_review (QD-08).

-- Vai của chính người đang đăng nhập (mọi người gọi được, kể cả chưa có vai nào): API dùng cho cờ shadow và để màn hình báo đúng.
CREATE OR REPLACE FUNCTION tien.my_access() RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path TO 'pg_catalog', 'tien', 'pg_temp' AS $$
BEGIN
    PERFORM tien._actor();
    PERFORM tien._actor_kind();
    RETURN jsonb_build_object('actor', tien._actor(), 'grants', (SELECT coalesce(jsonb_agg(jsonb_build_object(
            'role', g.role, 'legal_entity_id', g.legal_entity_id, 'legal_entity_code', e.code, 'account_id', g.account_id)
            ORDER BY g.legal_entity_id, g.account_id NULLS FIRST, g.role), '[]'::jsonb)
        FROM tien.access_grant g JOIN tien.legal_entity e ON e.id = g.legal_entity_id
       WHERE g.login = tien._actor() AND g.revoked_event IS NULL));
END $$;

CREATE OR REPLACE FUNCTION tien.list_accounts() RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path TO 'pg_catalog', 'tien', 'pg_temp' AS $$
DECLARE v_result jsonb;
BEGIN
    PERFORM tien._actor();
    PERFORM tien._actor_kind();
    SELECT jsonb_build_object('accounts', coalesce(jsonb_agg(jsonb_build_object(
            'id', a.id, 'legal_entity', jsonb_build_object('id', e.id, 'code', e.code, 'name', e.name), 'kind', a.kind,
            'bank_code', a.bank_code, 'account_last4', a.account_last4, 'currency', a.currency, 'holder', a.holder,
            'statement_template', a.statement_template, 'status', a.status, 'roles', tien._my_roles(a.legal_entity_id, a.id))
            ORDER BY a.id), '[]'::jsonb))
      INTO v_result FROM tien.financial_account a JOIN tien.legal_entity e ON e.id = a.legal_entity_id
     WHERE tien._has_role(NULL, a.legal_entity_id, a.id);
    RETURN v_result;
END $$;

-- Thẻ tài khoản (FR-06): tóm tắt lát 1 + dữ liệu tới, ngày đủ liền từ số dư mở, ngày thiếu, lô chờ, ngày ký gần nhất.
CREATE OR REPLACE FUNCTION tien.get_account_card(p_account bigint) RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path TO 'pg_catalog', 'tien', 'pg_temp' AS $$
DECLARE v_acc tien.financial_account; v_open tien.account_opening; v_until date; v_until_state text; v_end date; v_gap date;
        v_complete date; v_missing date[]; v_missing_count bigint := 0; v_signed date; v_unsigned bigint := 0; v_last tien.statement_import;
BEGIN
    v_acc := tien._read_account(p_account, NULL);
    SELECT * INTO v_open FROM tien.account_opening WHERE account_id = v_acc.id;
    SELECT max(i.period_to) INTO v_until FROM tien.statement_import i WHERE i.account_id = v_acc.id AND i.status = 'committed';
    IF v_open.account_id IS NOT NULL AND v_until IS NOT NULL THEN
        SELECT c.state INTO v_until_state FROM tien._coverage(v_acc.id, v_until, v_until) c;
        v_end := least(v_until, tien._today());
        SELECT min(c.day) INTO v_gap FROM tien._coverage(v_acc.id, v_open.as_of, v_end) c WHERE c.state <> 'full';
        v_complete := CASE WHEN v_gap IS NULL THEN v_end WHEN v_gap > v_open.as_of THEN v_gap - 1 END;
        SELECT array_agg(c.day ORDER BY c.day), count(*) INTO v_missing, v_missing_count
          FROM tien._coverage(v_acc.id, v_open.as_of, v_end) c WHERE c.state = 'missing';
        SELECT count(*) INTO v_unsigned FROM tien._coverage(v_acc.id, v_open.as_of, v_end) c
         WHERE c.state = 'full' AND tien._day_status(v_acc.id, c.day, 'coverage') <> 'signed';
    END IF;
    SELECT max(s.business_date) INTO v_signed FROM (
        SELECT DISTINCT ON (r.business_date) r.business_date, r.action FROM tien.day_review r
         WHERE r.account_id = v_acc.id AND r.track = 'coverage' ORDER BY r.business_date, r.id DESC) s
     WHERE s.action = 'sign';
    SELECT * INTO v_last FROM tien.statement_import WHERE account_id = v_acc.id AND status = 'committed' ORDER BY id DESC LIMIT 1;
    RETURN tien.get_account_summary(v_acc.id) || jsonb_build_object(
        'today', tien._today(), 'roles', tien._my_roles(v_acc.legal_entity_id, v_acc.id),
        'coverage', jsonb_build_object('data_until', v_until, 'data_until_state', v_until_state, 'complete_until', v_complete,
                                       'missing_days', coalesce(to_jsonb(v_missing[1:31]), '[]'::jsonb), 'missing_count', v_missing_count,
                                       'unsigned_full_days', v_unsigned, 'last_signed_day', v_signed),
        'pending_imports', (SELECT count(*) FROM tien.statement_import WHERE account_id = v_acc.id AND status = 'validated'),
        'last_import', CASE WHEN v_last.id IS NULL THEN NULL ELSE jsonb_build_object('id', v_last.id, 'period_from', v_last.period_from,
                                     'period_to', v_last.period_to, 'last_day_complete', v_last.last_day_complete,
                                     'committed', tien._who(v_last.committed_event)) END);
END $$;

-- Độ phủ và hai trạng thái ký từng ngày (≤ 93 ngày), ngày mới nhất trước: cột ngày của màn Đối soát ngày.
CREATE OR REPLACE FUNCTION tien.get_coverage(p_account bigint, p_from date, p_to date) RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path TO 'pg_catalog', 'tien', 'pg_temp' AS $$
DECLARE v_acc tien.financial_account; v_open tien.account_opening; v_today date := tien._today();
BEGIN
    v_acc := tien._read_account(p_account, NULL);
    IF p_from IS NULL OR p_to IS NULL OR p_from > p_to OR p_to - p_from > 92 THEN RAISE EXCEPTION 'INVALID_COMMAND'; END IF;
    SELECT * INTO v_open FROM tien.account_opening WHERE account_id = v_acc.id;
    RETURN jsonb_build_object('account_id', v_acc.id, 'from', p_from, 'to', p_to, 'today', v_today, 'opening_as_of', v_open.as_of,
        'days', (SELECT coalesce(jsonb_agg(jsonb_build_object('date', c.day,
                    'coverage', CASE WHEN v_open.account_id IS NULL OR c.day < v_open.as_of THEN 'before_opening'
                                     WHEN c.day > v_today THEN 'future' ELSE c.state END,
                    'coverage_status', tien._day_status(v_acc.id, c.day, 'coverage'),
                    'business_status', tien._day_status(v_acc.id, c.day, 'business'),
                    'transactions', (SELECT count(*) FROM tien.bank_transaction t WHERE t.account_id = v_acc.id AND t.booking_date = c.day
                                       AND t.voided_event IS NULL)) ORDER BY c.day DESC), '[]'::jsonb)
                   FROM tien._coverage(v_acc.id, p_from, p_to) c));
END $$;

-- Một ngày của màn Đối soát ngày: kiểm ngày (cùng hàm với lệnh ký), hai trạng thái, số giao dịch theo trạng thái, lịch sử ký.
CREATE OR REPLACE FUNCTION tien.get_day(p_account bigint, p_date date) RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path TO 'pg_catalog', 'tien', 'pg_temp' AS $$
DECLARE v_acc tien.financial_account;
BEGIN
    v_acc := tien._read_account(p_account, NULL);
    IF p_date IS NULL THEN RAISE EXCEPTION 'INVALID_COMMAND'; END IF;
    RETURN tien._day_check(v_acc.id, p_date) || jsonb_build_object('account_id', v_acc.id, 'account_version', v_acc.version,
        'currency', v_acc.currency, 'roles', tien._my_roles(v_acc.legal_entity_id, v_acc.id),
        'coverage_status', tien._day_status(v_acc.id, p_date, 'coverage'),
        'business_status', tien._day_status(v_acc.id, p_date, 'business'),
        'importers', to_jsonb(tien._day_importers(v_acc.id, p_date)),
        'business', tien._day_business(v_acc.id, p_date),
        'history', (SELECT coalesce(jsonb_agg(jsonb_build_object('id', r.id, 'track', r.track, 'action', r.action,
                                                                 'role_overlap', r.role_overlap, 'note', r.note, 'snapshot', r.snapshot,
                                                                 'by', tien._who(r.created_event)) ORDER BY r.id DESC), '[]'::jsonb)
                      FROM tien.day_review r WHERE r.account_id = v_acc.id AND r.business_date = p_date));
END $$;

-- 100 lô gần nhất của tài khoản, mới nhất trước; stale khi lô chờ mà sổ đã đổi từ lúc xem trước (commit sẽ IMPORT_PREVIEW_STALE).
CREATE OR REPLACE FUNCTION tien.list_imports(p_account bigint) RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path TO 'pg_catalog', 'tien', 'pg_temp' AS $$
DECLARE v_acc tien.financial_account; v_raw boolean; v_result jsonb;
BEGIN
    v_acc := tien._read_account(p_account, NULL);
    v_raw := tien._has_role(ARRAY['tien_nhap', 'tien_review'], v_acc.legal_entity_id, v_acc.id);
    SELECT jsonb_build_object('account_id', v_acc.id, 'account_version', v_acc.version, 'roles', tien._my_roles(v_acc.legal_entity_id, v_acc.id),
            'imports', coalesce(jsonb_agg(jsonb_build_object(
                'id', i.id, 'status', i.status, 'template', i.template, 'period_from', i.period_from, 'period_to', i.period_to,
                'last_day_complete', i.last_day_complete, 'counts', i.counts, 'reason', i.reason,
                'stale', i.status = 'validated' AND i.preview_account_version <> v_acc.version,
                'file', CASE WHEN f.id IS NULL THEN NULL
                             ELSE jsonb_build_object('id', f.id, 'byte_size', f.byte_size, 'media_type', f.media_type)
                                  || CASE WHEN v_raw THEN jsonb_build_object('name', f.file_name) ELSE '{}'::jsonb END END,
                'created', tien._who(i.created_event), 'committed', tien._who(i.committed_event), 'closed', tien._who(i.closed_event))
                ORDER BY i.id DESC), '[]'::jsonb))
      INTO v_result
      FROM (SELECT * FROM tien.statement_import WHERE account_id = v_acc.id ORDER BY id DESC LIMIT 100) i
      LEFT JOIN tien.statement_file f ON f.id = i.file_id;
    RETURN v_result;
END $$;

-- Một lô với từng dòng. Lô chờ (validated): phân loại lại bằng đúng hàm của commit (người đối chiếu mở sau vẫn thấy phân loại hiện
-- tại, preview_hash để commit); lô đã commit/hủy: dòng → giao dịch và vai nguồn. Ô gốc, mô tả chỉ cho tien_nhap/tien_review.
CREATE OR REPLACE FUNCTION tien.get_import(p_import bigint) RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path TO 'pg_catalog', 'tien', 'pg_temp' AS $$
DECLARE v_imp tien.statement_import; v_acc tien.financial_account; v_raw boolean; v_lines jsonb; v_cls jsonb; v_cls_lines jsonb;
        v_out jsonb; v_file tien.statement_file;
BEGIN
    PERFORM tien._actor();
    PERFORM tien._actor_kind();
    SELECT * INTO v_imp FROM tien.statement_import WHERE id = p_import;
    IF NOT FOUND THEN RAISE EXCEPTION 'INVALID_COMMAND'; END IF;
    v_acc := tien._read_account(v_imp.account_id, NULL);
    v_raw := tien._has_role(ARRAY['tien_nhap', 'tien_review'], v_acc.legal_entity_id, v_acc.id);
    IF v_imp.status = 'validated' THEN
        SELECT coalesce(jsonb_agg(r.line ORDER BY r.seq), '[]'::jsonb) INTO v_lines FROM tien.raw_statement_line r WHERE r.import_id = v_imp.id;
        v_cls := tien._classify(v_acc.id, v_imp.template, v_imp.period_from, v_imp.period_to, v_imp.opening_minor, v_imp.closing_minor,
                                tien._today(), v_lines);
        v_cls_lines := v_cls -> 'lines';
    END IF;
    SELECT coalesce(jsonb_agg(jsonb_build_object('seq', r.seq, 'line_no', r.line_no, 'booking_date', r.line -> 'booking_date',
                                                 'value_date', r.line -> 'value_date', 'direction', r.line -> 'direction',
                                                 'amount_minor', r.line -> 'amount_minor', 'currency', r.line -> 'currency',
                                                 'bank_ref', r.line -> 'bank_ref', 'balance_after_minor', r.line -> 'balance_after_minor')
                              || CASE WHEN v_raw THEN jsonb_build_object('description', r.line -> 'description', 'cells', r.cells)
                                      ELSE '{}'::jsonb END
                              || CASE WHEN (v_cls_lines -> (r.seq - 1) ->> 'seq')::integer = r.seq
                                      THEN (v_cls_lines -> (r.seq - 1)) - 'seq' - 'line_no' - 'fp' ELSE '{}'::jsonb END
                              || coalesce((SELECT jsonb_build_object('transaction_id', s.bank_transaction_id, 'source_role', s.role)
                                             FROM tien.bank_transaction_source s WHERE s.raw_line_id = r.id), '{}'::jsonb)
                              ORDER BY r.seq), '[]'::jsonb)
      INTO v_out FROM tien.raw_statement_line r WHERE r.import_id = v_imp.id;
    SELECT * INTO v_file FROM tien.statement_file WHERE id = v_imp.file_id;
    RETURN jsonb_build_object(
        'import', jsonb_build_object('id', v_imp.id, 'account_id', v_imp.account_id, 'status', v_imp.status, 'template', v_imp.template,
            'period_from', v_imp.period_from, 'period_to', v_imp.period_to, 'opening_minor', v_imp.opening_minor::text,
            'closing_minor', v_imp.closing_minor::text, 'last_day_complete', v_imp.last_day_complete, 'counts_at_preview', v_imp.counts,
            'preview_account_version', v_imp.preview_account_version, 'reason', v_imp.reason,
            'file', CASE WHEN v_file.id IS NULL THEN NULL
                         ELSE jsonb_build_object('id', v_file.id, 'byte_size', v_file.byte_size, 'media_type', v_file.media_type)
                              || CASE WHEN v_raw THEN jsonb_build_object('name', v_file.file_name) ELSE '{}'::jsonb END END,
            'created', tien._who(v_imp.created_event), 'committed', tien._who(v_imp.committed_event), 'closed', tien._who(v_imp.closed_event)),
        'account_version', v_acc.version, 'currency', v_acc.currency, 'raw_visible', v_raw,
        'roles', tien._my_roles(v_acc.legal_entity_id, v_acc.id),
        'stale', v_imp.status = 'validated' AND v_imp.preview_account_version <> v_acc.version, 'lines', v_out)
      || CASE WHEN v_cls IS NULL THEN '{}'::jsonb
              ELSE jsonb_build_object('preview_hash', v_cls ->> 'hash', 'counts', v_cls -> 'counts', 'balance', v_cls -> 'balance',
                                      'breaks', v_cls -> 'breaks', 'signed_days', tien._signed_days(v_acc.id, v_cls_lines, v_lines)) END;
END $$;

-- Một giao dịch: nguồn (lô, dòng), phân bổ hiện tại và lịch sử thay bộ phân bổ (người, lúc, trước → sau, lý do).
CREATE OR REPLACE FUNCTION tien.get_transaction(p_tx bigint) RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path TO 'pg_catalog', 'tien', 'pg_temp' AS $$
DECLARE v_tx tien.bank_transaction; v_view tien.v_transaction; v_acc tien.financial_account; v_desc boolean;
BEGIN
    PERFORM tien._actor();
    PERFORM tien._actor_kind();
    SELECT * INTO v_tx FROM tien.bank_transaction WHERE id = p_tx;
    IF NOT FOUND THEN RAISE EXCEPTION 'INVALID_COMMAND'; END IF;
    v_acc := tien._read_account(v_tx.account_id, NULL);
    SELECT * INTO v_view FROM tien.v_transaction WHERE id = p_tx;
    v_desc := tien._has_role(ARRAY['tien_nhap', 'tien_review'], v_acc.legal_entity_id, v_acc.id);
    RETURN jsonb_build_object(
        'transaction', jsonb_build_object('id', v_tx.id, 'account_id', v_tx.account_id, 'direction', v_tx.direction,
            'amount_minor', v_tx.amount_minor::text, 'currency', v_tx.currency, 'booking_date', v_tx.booking_date,
            'value_date', v_tx.value_date, 'bank_ref', v_tx.bank_ref, 'balance_after_minor', v_tx.balance_after_minor::text,
            'allocated_minor', v_view.allocated_minor::text, 'unallocated_minor', (v_tx.amount_minor - v_view.allocated_minor)::text,
            'status', v_view.status, 'voided', v_tx.voided_event IS NOT NULL, 'version', v_tx.version,
            'created', tien._who(v_tx.created_event), 'voided_by', tien._who(v_tx.voided_event))
            || CASE WHEN v_desc THEN jsonb_build_object('description', v_tx.description) ELSE '{}'::jsonb END,
        'description_visible', v_desc, 'roles', tien._my_roles(v_acc.legal_entity_id, v_acc.id),
        'coverage_status', tien._day_status(v_acc.id, v_tx.booking_date, 'coverage'),
        'sources', (SELECT coalesce(jsonb_agg(jsonb_build_object('import_id', s.import_id, 'role', s.role, 'line_no', r.line_no,
                                                                 'import_status', i.status, 'period_from', i.period_from,
                                                                 'period_to', i.period_to) ORDER BY s.id), '[]'::jsonb)
                      FROM tien.bank_transaction_source s JOIN tien.raw_statement_line r ON r.id = s.raw_line_id
                      JOIN tien.statement_import i ON i.id = s.import_id WHERE s.bank_transaction_id = v_tx.id),
        'allocations', tien._allocations(v_tx.id),
        'history', (SELECT coalesce(jsonb_agg(jsonb_build_object('event_id', e.id, 'before', e."before" -> 'allocations',
                                                                 'after', e."after" -> 'allocations', 'reason', e."after" -> 'reason',
                                                                 'by', tien._who(e.id)) ORDER BY e.id DESC), '[]'::jsonb)
                      FROM tien.event e WHERE e.account_id = v_acc.id AND e.kind = 'allocation_set'
                       AND (e."after" ->> 'transaction')::bigint = v_tx.id));
END $$;

-- File gốc của một lô (QD-08): chỉ tien_nhap/tien_review; API ghi log mỗi lần tải. base64 một dòng.
CREATE OR REPLACE FUNCTION tien.get_statement_file(p_file bigint) RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path TO 'pg_catalog', 'tien', 'pg_temp' AS $$
DECLARE v_file tien.statement_file; v_acc tien.financial_account;
BEGIN
    PERFORM tien._actor();
    PERFORM tien._actor_kind();
    SELECT * INTO v_file FROM tien.statement_file WHERE id = p_file;
    IF NOT FOUND THEN RAISE EXCEPTION 'INVALID_COMMAND'; END IF;
    v_acc := tien._read_account(v_file.account_id, NULL);
    PERFORM tien._require_any(ARRAY['tien_nhap', 'tien_review'], v_acc.legal_entity_id, v_acc.id);
    RETURN jsonb_build_object('id', v_file.id, 'account_id', v_file.account_id, 'file_name', v_file.file_name,
        'media_type', v_file.media_type, 'byte_size', v_file.byte_size, 'file_sha256', v_file.file_sha256,
        'content_base64', replace(encode(v_file.content, 'base64'), chr(10), ''));
END $$;

-- Dữ liệu xuất cho kế toán (QD-09): tien_review, ≤ 366 ngày; giao dịch chưa hủy, phân bổ hiệu lực, độ phủ và trạng thái ký từng ngày,
-- số dư sổ đầu và cuối kỳ.
CREATE OR REPLACE FUNCTION tien.export_rows(p_account bigint, p_from date, p_to date) RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path TO 'pg_catalog', 'tien', 'pg_temp' AS $$
DECLARE v_acc tien.financial_account; v_open tien.account_opening; v_entity tien.legal_entity; v_today date := tien._today();
BEGIN
    v_acc := tien._read_account(p_account, 'tien_review');
    IF p_from IS NULL OR p_to IS NULL OR p_from > p_to OR p_to - p_from > 365 THEN RAISE EXCEPTION 'INVALID_COMMAND'; END IF;
    SELECT * INTO v_open FROM tien.account_opening WHERE account_id = v_acc.id;
    SELECT * INTO v_entity FROM tien.legal_entity WHERE id = v_acc.legal_entity_id;
    RETURN jsonb_build_object(
        'account', jsonb_build_object('id', v_acc.id, 'bank_code', v_acc.bank_code, 'account_last4', v_acc.account_last4,
                                      'currency', v_acc.currency, 'legal_entity_code', v_entity.code, 'legal_entity_name', v_entity.name),
        'from', p_from, 'to', p_to, 'actor', tien._actor(), 'generated_at', clock_timestamp(), 'opening_as_of', v_open.as_of,
        'opening_minor', tien._ledger_closing(v_acc.id, p_from - 1)::text, 'closing_minor', tien._ledger_closing(v_acc.id, p_to)::text,
        'transactions', (SELECT coalesce(jsonb_agg(jsonb_build_object('id', t.id, 'booking_date', t.booking_date,
                'value_date', t.value_date, 'bank_ref', t.bank_ref, 'description', t.description, 'direction', t.direction,
                'amount_minor', t.amount_minor::text, 'status', t.status, 'allocated_minor', t.allocated_minor::text,
                'unallocated_minor', (t.amount_minor - t.allocated_minor)::text,
                'imports', (SELECT coalesce(jsonb_agg(DISTINCT s.import_id ORDER BY s.import_id), '[]'::jsonb)
                              FROM tien.bank_transaction_source s JOIN tien.statement_import i ON i.id = s.import_id
                             WHERE s.bank_transaction_id = t.id AND i.status = 'committed'))
                ORDER BY t.booking_date, t.id), '[]'::jsonb)
              FROM tien.v_transaction t WHERE t.account_id = v_acc.id AND t.voided_event IS NULL AND t.booking_date BETWEEN p_from AND p_to),
        'allocations', (SELECT coalesce(jsonb_agg(jsonb_build_object('transaction_id', l.bank_transaction_id, 'booking_date', t.booking_date,
                'direction', t.direction, 'target_kind', l.target_kind, 'target_ref', l.target_ref, 'amount_minor', l.amount_minor::text,
                'note', l.note) ORDER BY t.booking_date, t.id, l.id), '[]'::jsonb)
              FROM tien.allocation l JOIN tien.bank_transaction t ON t.id = l.bank_transaction_id
             WHERE l.account_id = v_acc.id AND l.superseded_event IS NULL AND t.voided_event IS NULL
               AND t.booking_date BETWEEN p_from AND p_to),
        'days', CASE WHEN v_open.account_id IS NULL THEN '[]'::jsonb ELSE (SELECT coalesce(jsonb_agg(jsonb_build_object('date', c.day,
                'coverage', c.state, 'coverage_status', tien._day_status(v_acc.id, c.day, 'coverage'),
                'business_status', tien._day_status(v_acc.id, c.day, 'business')) ORDER BY c.day), '[]'::jsonb)
              FROM tien._coverage(v_acc.id, greatest(p_from, v_open.as_of), least(p_to, v_today)) c) END);
END $$;

-- Quyền: tien_app thêm bốn lệnh mới, mười hàm đọc mới (file gốc và dữ liệu xuất chỉ tien_app); tien_reader tám hàm đọc không chứa
-- file gốc hay dữ liệu xuất. Hàm phụ không cấp cho ai; không quyền bảng.
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA tien FROM PUBLIC;
REVOKE ALL ON ALL TABLES IN SCHEMA tien FROM PUBLIC;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA tien FROM PUBLIC;
GRANT EXECUTE ON FUNCTION tien.preview_import(jsonb), tien.record_balance_evidence(jsonb), tien.sign_day_coverage(jsonb),
    tien.sign_day_business(jsonb), tien.reopen_day(jsonb), tien.get_statement_file(bigint), tien.export_rows(bigint, date, date) TO tien_app;
GRANT EXECUTE ON FUNCTION tien.my_access(), tien.list_accounts(), tien.get_account_card(bigint), tien.get_coverage(bigint, date, date),
    tien.get_day(bigint, date), tien.list_imports(bigint), tien.get_import(bigint), tien.get_transaction(bigint) TO tien_app, tien_reader;
COMMIT;
