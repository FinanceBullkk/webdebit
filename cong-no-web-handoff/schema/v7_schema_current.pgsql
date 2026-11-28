-- ============================================================================================================
-- SINH TỰ ĐỘNG, không sửa tay, không chạy trên hao.
-- Trạng thái hiện hành của lược đồ V7 `sokhach` sau khi nạp đủ như harness PostgreSQL: specs/v7-backend/schema-draft.sql
-- → cong-no-web-handoff/tools/v7_backend_functions.sql → migrations/2026-10-24-v7-sheet-cross-customer.sql.
-- Mỗi hàm/view/bảng xuất hiện đúng một lần, bản đang có hiệu lực; tìm theo tên, ví dụ "FUNCTION sokhach.get_ledger(".
-- Sửa SQL ở file nguồn + migration, rồi sinh lại:  python cong-no-web-handoff/tools/v7_schema_snapshot.py
-- CI (job postgres-v7-backend) sinh lại và so với file này; lệch thì đỏ.
-- File chỉ để đọc: thiếu vai trò, thứ tự phụ thuộc và dữ liệu, không phải đường triển khai.
-- Ảnh PostgreSQL: postgres:18.6
-- ============================================================================================================

-- ------------------------------------------------------------------------------------------------------------
-- SCHEMA sokhach
-- ------------------------------------------------------------------------------------------------------------

CREATE SCHEMA sokhach AUTHORIZATION sokhach_owner;
GRANT USAGE ON SCHEMA sokhach TO sokhach_app;
GRANT USAGE ON SCHEMA sokhach TO sokhach_reader;
-- ALTER DEFAULT PRIVILEGES FOR ROLE sokhach_owner ON FUNCTIONS: ACL còn lại {sokhach_owner=X/sokhach_owner} (không có '=' đầu = PUBLIC bị thu)

-- ------------------------------------------------------------------------------------------------------------
-- BẢNG (36)
-- ------------------------------------------------------------------------------------------------------------

CREATE TABLE sokhach.adjustment (
    id bigint GENERATED ALWAYS AS IDENTITY NOT NULL,
    customer_id bigint NOT NULL,
    debt_month date NOT NULL,
    trip_id bigint,
    amount_vnd bigint NOT NULL,
    field text,
    fee_absorbed boolean DEFAULT false NOT NULL,
    new_value_vnd bigint,
    note text,
    actor text NOT NULL,
    at timestamp with time zone DEFAULT now() NOT NULL,
    created_by_event bigint NOT NULL,
    legacy_row_id bigint,
    reverses_adjustment_id bigint,
    CONSTRAINT adjustment_actor_check CHECK ((btrim(actor) <> ''::text)),
    CONSTRAINT adjustment_amount_vnd_check CHECK ((amount_vnd <> 0)),
    CONSTRAINT adjustment_check CHECK (((field IS NULL) = (new_value_vnd IS NULL))),
    CONSTRAINT adjustment_customer_id_fkey FOREIGN KEY (customer_id) REFERENCES sokhach.customer(id),
    CONSTRAINT adjustment_debt_month_check CHECK ((EXTRACT(day FROM debt_month) = (1)::numeric)),
    CONSTRAINT adjustment_event_fk FOREIGN KEY (created_by_event, customer_id) REFERENCES sokhach.event(id, customer_id),
    CONSTRAINT adjustment_field_check CHECK ((field = ANY (ARRAY['unit_price_vnd'::text, 'other_fee_vnd'::text]))),
    CONSTRAINT adjustment_legacy_row_id_fkey FOREIGN KEY (legacy_row_id) REFERENCES sokhach.legacy_row(id),
    CONSTRAINT adjustment_new_value_vnd_check CHECK ((new_value_vnd >= 0)),
    CONSTRAINT adjustment_one_target CHECK (((trip_id IS NULL) OR (legacy_row_id IS NULL))),
    CONSTRAINT adjustment_pkey PRIMARY KEY (id),
    CONSTRAINT adjustment_reversal_month_only CHECK (((reverses_adjustment_id IS NULL) OR ((trip_id IS NULL) AND (legacy_row_id IS NULL) AND (field IS NULL)))),
    CONSTRAINT adjustment_reverses_adjustment_id_fkey FOREIGN KEY (reverses_adjustment_id) REFERENCES sokhach.adjustment(id),
    CONSTRAINT adjustment_reverses_adjustment_id_key UNIQUE (reverses_adjustment_id),
    CONSTRAINT adjustment_trip_id_customer_id_debt_month_fkey FOREIGN KEY (trip_id, customer_id, debt_month) REFERENCES sokhach.trip(id, customer_id, debt_month)
);
ALTER TABLE sokhach.adjustment OWNER TO sokhach_owner;
CREATE INDEX adjustment_customer_month ON sokhach.adjustment USING btree (customer_id, debt_month, id);
CREATE INDEX adjustment_trip ON sokhach.adjustment USING btree (trip_id) WHERE (trip_id IS NOT NULL);
CREATE TRIGGER adjustment_immutable BEFORE DELETE OR UPDATE ON sokhach.adjustment FOR EACH ROW EXECUTE FUNCTION sokhach.reject_immutable_change();
COMMENT ON TABLE sokhach.adjustment IS 'Hiệu số có dấu, tính ngay; trip_id NULL là điều chỉnh cả tháng.';
COMMENT ON COLUMN sokhach.adjustment.amount_vnd IS 'Khác 0; số đúng theo chuyến do hàm lệnh đổi thành hiệu số.';
COMMENT ON COLUMN sokhach.adjustment.note IS 'Ghi chú tùy chọn, không phải điều kiện ghi tiền V7.';

CREATE TABLE sokhach.baseline_trip_ref (
    cutover_id bigint NOT NULL,
    booking_norm text NOT NULL,
    container_norm text NOT NULL,
    event_date date,
    CONSTRAINT baseline_trip_ref_cutover_id_fkey FOREIGN KEY (cutover_id) REFERENCES sokhach.cutover(id)
);
ALTER TABLE sokhach.baseline_trip_ref OWNER TO sokhach_owner;
CREATE INDEX baseline_trip_ref_code ON sokhach.baseline_trip_ref USING btree (cutover_id, booking_norm, container_norm);
CREATE INDEX baseline_trip_ref_date ON sokhach.baseline_trip_ref USING btree (cutover_id, container_norm, event_date);
CREATE TRIGGER baseline_trip_ref_immutable BEFORE DELETE OR UPDATE ON sokhach.baseline_trip_ref FOR EACH ROW EXECUTE FUNCTION sokhach.reject_immutable_change();

CREATE TABLE sokhach.book_fee_column (
    customer_id bigint NOT NULL,
    fee_type_id bigint NOT NULL,
    position integer NOT NULL,
    CONSTRAINT book_fee_column_customer_id_fkey FOREIGN KEY (customer_id) REFERENCES sokhach.customer(id),
    CONSTRAINT book_fee_column_customer_id_position_key UNIQUE (customer_id, "position"),
    CONSTRAINT book_fee_column_fee_type_id_fkey FOREIGN KEY (fee_type_id) REFERENCES sokhach.fee_type(id),
    CONSTRAINT book_fee_column_pkey PRIMARY KEY (customer_id, fee_type_id),
    CONSTRAINT book_fee_column_position_check CHECK (("position" > 0))
);
ALTER TABLE sokhach.book_fee_column OWNER TO sokhach_owner;

CREATE TABLE sokhach.booking_name (
    name text NOT NULL,
    customer_id bigint NOT NULL,
    created_by text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT booking_name_created_by_check CHECK ((btrim(created_by) <> ''::text)),
    CONSTRAINT booking_name_customer_id_fkey FOREIGN KEY (customer_id) REFERENCES sokhach.customer(id),
    CONSTRAINT booking_name_name_check CHECK (((name = btrim(name)) AND (name <> ''::text) AND (char_length(name) <= 200) AND (POSITION(('  '::text) IN (name)) = 0) AND (name !~ '[[:cntrl:]]'::text) AND (name !~ '[- ­ ᠎ -‏ -  -⁯　﻿]'::text) AND (name = NORMALIZE(name, NFC)) AND (name = upper(name)))),
    CONSTRAINT booking_name_pkey PRIMARY KEY (name)
);
ALTER TABLE sokhach.booking_name OWNER TO sokhach_owner;
CREATE INDEX booking_name_customer ON sokhach.booking_name USING btree (customer_id);
COMMENT ON TABLE sokhach.booking_name IS 'KHACH-WEB-01: tên chủ hàng trên booking (cột "Chủ hàng (chuẩn)" của CONT_NGUON, "CHỦ HÀNG" của CONT_BO) ứng với một sổ; một tên chỉ một sổ. Web viết hoa, bỏ khoảng trắng thừa trước khi ghi; không nhận ký tự điều khiển hay khoảng trắng lạ (NBSP, ký tự vô hình). Không tham gia tính tiền.';

CREATE TABLE sokhach.cash_report_review (
    id bigint GENERATED ALWAYS AS IDENTITY NOT NULL,
    conversation_id text NOT NULL,
    message_id text NOT NULL,
    action text NOT NULL,
    target_kind text,
    target_id bigint,
    amount_vnd bigint,
    before jsonb NOT NULL,
    reason text,
    request_id text NOT NULL,
    created_by text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT cash_report_review_action_check CHECK ((action = ANY (ARRAY['confirm'::text, 'target'::text, 'amount'::text, 'not_cash'::text]))),
    CONSTRAINT cash_report_review_amount_vnd_check CHECK (((amount_vnd IS NULL) OR (amount_vnd > 0))),
    CONSTRAINT cash_report_review_before_check CHECK (((jsonb_typeof(before) = 'object'::text) AND (octet_length((before)::text) <= 10000))),
    CONSTRAINT cash_report_review_check CHECK ((((action = 'target'::text) = (target_kind IS NOT NULL)) AND ((target_kind IS NULL) = (target_id IS NULL)))),
    CONSTRAINT cash_report_review_check1 CHECK (((action = 'amount'::text) = (amount_vnd IS NOT NULL))),
    CONSTRAINT cash_report_review_check2 CHECK (((action <> 'not_cash'::text) OR (reason IS NOT NULL))),
    CONSTRAINT cash_report_review_conversation_id_check CHECK ((conversation_id ~ '^[0-9a-f]{64}$'::text)),
    CONSTRAINT cash_report_review_created_by_check CHECK ((btrim(created_by) <> ''::text)),
    CONSTRAINT cash_report_review_message_id_check CHECK ((message_id ~ '^[0-9A-Za-z_-]{1,128}$'::text)),
    CONSTRAINT cash_report_review_pkey PRIMARY KEY (id),
    CONSTRAINT cash_report_review_reason_check CHECK (((reason IS NULL) OR ((btrim(reason) <> ''::text) AND (char_length(reason) <= 500)))),
    CONSTRAINT cash_report_review_request_id_check CHECK (((btrim(request_id) <> ''::text) AND (char_length(request_id) <= 200))),
    CONSTRAINT cash_report_review_request_id_key UNIQUE (request_id),
    CONSTRAINT cash_report_review_target_id_check CHECK (((target_id IS NULL) OR (target_id > 0))),
    CONSTRAINT cash_report_review_target_kind_check CHECK (((target_kind IS NULL) OR (target_kind = ANY (ARRAY['so'::text, 'xe'::text, 'tai_xe'::text]))))
);
ALTER TABLE sokhach.cash_report_review OWNER TO sokhach_owner;
CREATE INDEX cash_report_review_message ON sokhach.cash_report_review USING btree (message_id, id);
COMMENT ON TABLE sokhach.cash_report_review IS 'ZALO-THU-CHI-01 PR-3: xác nhận/sửa số/gắn đối tượng/loại một khoản thu chi báo trong nhóm Zalo; chỉ thêm dòng, gộp theo thứ tự; không tham gia tính tiền.';

CREATE TABLE sokhach.commodity (
    id bigint GENERATED ALWAYS AS IDENTITY NOT NULL,
    name text NOT NULL,
    CONSTRAINT commodity_name_check CHECK ((btrim(name) <> ''::text)),
    CONSTRAINT commodity_name_key UNIQUE (name),
    CONSTRAINT commodity_pkey PRIMARY KEY (id)
);
ALTER TABLE sokhach.commodity OWNER TO sokhach_owner;
COMMENT ON TABLE sokhach.commodity IS 'Danh mục mặt hàng (cột LOAI HANG của tab TONG); chỉ để phân loại, không tham gia tính nợ.';

CREATE TABLE sokhach.contact_mark (
    id bigint GENERATED ALWAYS AS IDENTITY NOT NULL,
    customer_id bigint NOT NULL,
    kind text NOT NULL,
    amount_vnd bigint,
    on_date date,
    note text,
    conversation_id text,
    message_id text,
    message_at timestamp with time zone,
    message_sender text,
    message_excerpt text,
    idempotency_key text NOT NULL,
    created_by text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    created_on date NOT NULL,
    cancelled_by text,
    cancelled_at timestamp with time zone,
    cancel_reason text,
    CONSTRAINT contact_mark_amount_vnd_check CHECK (((amount_vnd IS NULL) OR (amount_vnd > 0))),
    CONSTRAINT contact_mark_cancel_reason_check CHECK (((cancel_reason IS NULL) OR (btrim(cancel_reason) <> ''::text))),
    CONSTRAINT contact_mark_cancelled_by_check CHECK (((cancelled_by IS NULL) OR (btrim(cancelled_by) <> ''::text))),
    CONSTRAINT contact_mark_check CHECK ((((kind = 'note'::text) AND (amount_vnd IS NULL) AND (on_date IS NULL) AND (note IS NOT NULL)) OR ((kind <> 'note'::text) AND (amount_vnd IS NOT NULL) AND (on_date IS NOT NULL)))),
    CONSTRAINT contact_mark_check1 CHECK (((message_id IS NULL) OR (conversation_id IS NOT NULL))),
    CONSTRAINT contact_mark_check2 CHECK ((((cancelled_at IS NULL) = (cancelled_by IS NULL)) AND ((cancelled_at IS NULL) = (cancel_reason IS NULL)))),
    CONSTRAINT contact_mark_conversation_id_check CHECK (((conversation_id IS NULL) OR (conversation_id ~ '^[0-9a-f]{64}$'::text))),
    CONSTRAINT contact_mark_created_by_check CHECK ((btrim(created_by) <> ''::text)),
    CONSTRAINT contact_mark_customer_id_fkey FOREIGN KEY (customer_id) REFERENCES sokhach.customer(id),
    CONSTRAINT contact_mark_idempotency_key_check CHECK (((btrim(idempotency_key) <> ''::text) AND (char_length(idempotency_key) <= 200))),
    CONSTRAINT contact_mark_idempotency_key_key UNIQUE (idempotency_key),
    CONSTRAINT contact_mark_kind_check CHECK ((kind = ANY (ARRAY['promise'::text, 'paid_claim'::text, 'note'::text]))),
    CONSTRAINT contact_mark_message_excerpt_check CHECK (((message_excerpt IS NULL) OR (char_length(message_excerpt) <= 300))),
    CONSTRAINT contact_mark_message_id_check CHECK (((message_id IS NULL) OR (message_id ~ '^[0-9A-Za-z_-]{1,128}$'::text))),
    CONSTRAINT contact_mark_message_sender_check CHECK (((message_sender IS NULL) OR (char_length(message_sender) <= 200))),
    CONSTRAINT contact_mark_note_check CHECK (((note IS NULL) OR ((btrim(note) <> ''::text) AND (char_length(note) <= 500)))),
    CONSTRAINT contact_mark_pkey PRIMARY KEY (id)
);
ALTER TABLE sokhach.contact_mark OWNER TO sokhach_owner;
CREATE INDEX contact_mark_conversation ON sokhach.contact_mark USING btree (conversation_id) WHERE (conversation_id IS NOT NULL);
CREATE INDEX contact_mark_customer ON sokhach.contact_mark USING btree (customer_id, created_at DESC);
COMMENT ON TABLE sokhach.contact_mark IS 'ZALO-GROUP-01/TRANG-KHACH-01 B2: dấu hứa trả, khách báo đã chuyển, ghi chú (có thể gắn một tin Zalo); trạng thái tính khi đọc; không tham gia tính tiền.';

CREATE TABLE sokhach.customer (
    id bigint GENERATED ALWAYS AS IDENTITY NOT NULL,
    name text NOT NULL,
    commodity_id bigint,
    transport_mode text,
    archived boolean DEFAULT false NOT NULL,
    version bigint DEFAULT 0 NOT NULL,
    CONSTRAINT customer_commodity_id_fkey FOREIGN KEY (commodity_id) REFERENCES sokhach.commodity(id),
    CONSTRAINT customer_name_check CHECK ((btrim(name) <> ''::text)),
    CONSTRAINT customer_pkey PRIMARY KEY (id),
    CONSTRAINT customer_transport_mode_check CHECK ((transport_mode = ANY (ARRAY['CANG'::text, 'BO'::text]))),
    CONSTRAINT customer_version_check CHECK ((version >= 0))
);
ALTER TABLE sokhach.customer OWNER TO sokhach_owner;
COMMENT ON TABLE sokhach.customer IS 'Một khách là đơn vị khóa và kiểm phiên bản cho lệnh ghi.';
COMMENT ON COLUMN sokhach.customer.commodity_id IS 'Mặt hàng của sổ này (một dòng TONG = một sổ = một mặt hàng); NULL = chưa gán, chỉ tô màu, không chặn.';
COMMENT ON COLUMN sokhach.customer.transport_mode IS 'Phương thức vận chuyển của sổ: CANG (cảng) hoặc BO (đường bộ); NULL = không phân biệt/chưa gán. Trên TONG, sầu riêng tách CANG/BO; xoài và thanh long có thêm nhóm "BỘ"; các mặt hàng còn lại không ghi.';
COMMENT ON COLUMN sokhach.customer.archived IS 'Sổ lưu trữ: xem được, không tính vào thống kê. Chỉ áp dụng cho tab không có dòng TONG và không có số dư mở; khách có nợ không được archive.';
COMMENT ON COLUMN sokhach.customer.version IS 'Tăng sau mỗi lệnh ghi; expected_version cũ bị từ chối.';

CREATE TABLE sokhach.cutover (
    id bigint GENERATED ALWAYS AS IDENTITY NOT NULL,
    name text NOT NULL,
    source text NOT NULL,
    source_sha256 text NOT NULL,
    frozen_at timestamp with time zone NOT NULL,
    control_total_vnd bigint NOT NULL,
    status text DEFAULT 'draft'::text NOT NULL,
    created_by text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT cutover_created_by_check CHECK ((btrim(created_by) <> ''::text)),
    CONSTRAINT cutover_name_check CHECK ((btrim(name) <> ''::text)),
    CONSTRAINT cutover_pkey PRIMARY KEY (id),
    CONSTRAINT cutover_source_check CHECK ((btrim(source) <> ''::text)),
    CONSTRAINT cutover_source_sha256_check CHECK ((source_sha256 ~ '^[0-9a-fA-F]{64}$'::text)),
    CONSTRAINT cutover_status_check CHECK ((status = ANY (ARRAY['draft'::text, 'verified'::text, 'active'::text])))
);
ALTER TABLE sokhach.cutover OWNER TO sokhach_owner;
CREATE TRIGGER cutover_status_guard BEFORE INSERT OR DELETE OR UPDATE ON sokhach.cutover FOR EACH ROW EXECUTE FUNCTION sokhach.guard_cutover_status();
COMMENT ON TABLE sokhach.cutover IS 'ĐỀ XUẤT: mốc nguồn draft, verified, active; chuyển trạng thái chỉ qua gate đối soát và kích hoạt riêng.';
COMMENT ON COLUMN sokhach.cutover.control_total_vnd IS 'Tổng kiểm toàn mốc có dấu; đối chiếu sau khi nhập đủ khách, không thay tổng kiểm từng khách của import_cutover.';
COMMENT ON COLUMN sokhach.cutover.status IS 'Draft không hiệu lực; verified đã đối soát nhưng chưa hiệu lực; active chỉ sau gate kích hoạt riêng.';

CREATE TABLE sokhach.cutover_customer (
    customer_id bigint NOT NULL,
    cutover_id bigint NOT NULL,
    expected_control_total_vnd bigint NOT NULL,
    status text DEFAULT 'draft'::text NOT NULL,
    report_sha256 text NOT NULL,
    source_rows bigint NOT NULL,
    imported_rows bigint NOT NULL,
    quarantined_rows bigint NOT NULL,
    skipped_with_reason_rows bigint NOT NULL,
    unresolved_exceptions bigint NOT NULL,
    CONSTRAINT cutover_customer_check CHECK ((source_rows = ((imported_rows + quarantined_rows) + skipped_with_reason_rows))),
    CONSTRAINT cutover_customer_customer_id_cutover_id_key UNIQUE (customer_id, cutover_id),
    CONSTRAINT cutover_customer_customer_id_fkey FOREIGN KEY (customer_id) REFERENCES sokhach.customer(id),
    CONSTRAINT cutover_customer_cutover_id_fkey FOREIGN KEY (cutover_id) REFERENCES sokhach.cutover(id),
    CONSTRAINT cutover_customer_imported_rows_check CHECK ((imported_rows >= 0)),
    CONSTRAINT cutover_customer_pkey PRIMARY KEY (customer_id),
    CONSTRAINT cutover_customer_quarantined_rows_check CHECK ((quarantined_rows >= 0)),
    CONSTRAINT cutover_customer_report_sha256_check CHECK ((report_sha256 ~ '^[0-9a-fA-F]{64}$'::text)),
    CONSTRAINT cutover_customer_skipped_with_reason_rows_check CHECK ((skipped_with_reason_rows >= 0)),
    CONSTRAINT cutover_customer_source_rows_check CHECK ((source_rows >= 0)),
    CONSTRAINT cutover_customer_status_check CHECK ((status = ANY (ARRAY['draft'::text, 'verified'::text, 'active'::text]))),
    CONSTRAINT cutover_customer_unresolved_exceptions_check CHECK ((unresolved_exceptions >= 0))
);
ALTER TABLE sokhach.cutover_customer OWNER TO sokhach_owner;
CREATE TRIGGER cutover_customer_status_guard BEFORE INSERT OR DELETE OR UPDATE ON sokhach.cutover_customer FOR EACH ROW EXECUTE FUNCTION sokhach.guard_cutover_customer_status();
COMMENT ON TABLE sokhach.cutover_customer IS 'ĐỀ XUẤT: gate riêng từng khách kể cả số dư 0; customer_id duy nhất tạm chặn nhập mốc thứ hai. Báo cáo nguồn ngoài repo.';

CREATE TABLE sokhach.cutover_month_check (
    customer_id bigint NOT NULL,
    cutover_id bigint NOT NULL,
    debt_month date NOT NULL,
    opening_anchor_vnd bigint,
    source_cumulative_vnd bigint,
    replay_cumulative_vnd bigint,
    bucket_vnd bigint,
    standard_bucket_vnd bigint,
    source_charge_vnd bigint,
    source_receipt_vnd bigint,
    standard_source_ref text,
    standard_source_sha256 text,
    source_evidence_sha256 text,
    exception_codes text[] DEFAULT '{}'::text[] NOT NULL,
    CONSTRAINT cutover_month_check_customer_id_cutover_id_fkey FOREIGN KEY (customer_id, cutover_id) REFERENCES sokhach.cutover_customer(customer_id, cutover_id),
    CONSTRAINT cutover_month_check_debt_month_check CHECK ((EXTRACT(day FROM debt_month) = (1)::numeric)),
    CONSTRAINT cutover_month_check_exception_codes_check CHECK ((exception_codes <@ ARRAY['NO_BASELINE'::text, 'MISSING_PRICE'::text, 'MISSING_CACHE'::text, 'HISTORICAL_DELTA_600'::text, 'OTHER'::text])),
    CONSTRAINT cutover_month_check_pkey PRIMARY KEY (customer_id, cutover_id, debt_month),
    CONSTRAINT cutover_month_check_source_evidence_sha256_check CHECK ((source_evidence_sha256 ~ '^[0-9a-fA-F]{64}$'::text)),
    CONSTRAINT cutover_month_check_source_receipt_vnd_check CHECK ((source_receipt_vnd >= 0)),
    CONSTRAINT cutover_month_check_standard_source_ref_check CHECK ((btrim(standard_source_ref) <> ''::text)),
    CONSTRAINT cutover_month_check_standard_source_sha256_check CHECK ((standard_source_sha256 ~ '^[0-9a-fA-F]{64}$'::text))
);
ALTER TABLE sokhach.cutover_month_check OWNER TO sokhach_owner;
CREATE TRIGGER cutover_month_check_guard BEFORE INSERT OR DELETE OR UPDATE ON sokhach.cutover_month_check FOR EACH ROW EXECUTE FUNCTION sokhach.guard_cutover_evidence();
COMMENT ON TABLE sokhach.cutover_month_check IS 'ĐỀ XUẤT: mỏ neo và dòng tiền nguồn từng tháng để tính FIFO độc lập với bucket nhập; NULL tiền/chứng cứ chặn, exception_codes giữ nguyên và không chặn khi số khớp.';
COMMENT ON COLUMN sokhach.cutover_month_check.opening_anchor_vnd IS 'ĐỀ XUẤT: mỏ neo nguồn trước tháng đầu, lặp cùng giá trị ở chuỗi tháng; NULL chặn verify, không thay bằng 0.';
COMMENT ON COLUMN sokhach.cutover_month_check.replay_cumulative_vnd IS 'Client gửi chỉ để đối chiếu; DB không dùng làm chứng cứ verify.';
COMMENT ON COLUMN sokhach.cutover_month_check.standard_bucket_vnd IS 'ĐỀ XUẤT: bucket nợ còn lại theo kỳ sau FIFO, tính lại từ mỏ neo đầu kỳ, phát sinh và thu nguồn; không lấy hiệu mỏ neo hay bucket nhập.';
COMMENT ON COLUMN sokhach.cutover_month_check.source_charge_vnd IS 'ĐỀ XUẤT: tổng phát sinh có dấu của kỳ từ dòng nguồn; NULL chặn verify.';
COMMENT ON COLUMN sokhach.cutover_month_check.source_receipt_vnd IS 'ĐỀ XUẤT: tổng thu của kỳ từ dòng nguồn; NULL chặn verify.';
COMMENT ON COLUMN sokhach.cutover_month_check.standard_source_ref IS 'Tham chiếu mỏ neo đầu, phát sinh, thu và mỏ neo cuối trong nguồn; dữ liệu nguồn giữ ngoài repo.';

CREATE TABLE sokhach.event (
    id bigint GENERATED ALWAYS AS IDENTITY NOT NULL,
    customer_id bigint NOT NULL,
    kind text NOT NULL,
    actor text NOT NULL,
    at timestamp with time zone DEFAULT now() NOT NULL,
    before jsonb NOT NULL,
    after jsonb NOT NULL,
    idempotency_key text,
    cutover_id bigint,
    CONSTRAINT event_actor_check CHECK ((btrim(actor) <> ''::text)),
    CONSTRAINT event_after_check CHECK ((jsonb_typeof(after) = 'object'::text)),
    CONSTRAINT event_before_check CHECK ((jsonb_typeof(before) = 'object'::text)),
    CONSTRAINT event_check CHECK (((kind = 'import'::text) = (cutover_id IS NOT NULL))),
    CONSTRAINT event_customer_id_fkey FOREIGN KEY (customer_id) REFERENCES sokhach.customer(id),
    CONSTRAINT event_cutover_id_fkey FOREIGN KEY (cutover_id) REFERENCES sokhach.cutover(id),
    CONSTRAINT event_id_customer_id_key UNIQUE (id, customer_id),
    CONSTRAINT event_kind_check CHECK ((kind = ANY (ARRAY['paste'::text, 'price_edit'::text, 'adjust_trip'::text, 'adjust_month'::text, 'receipt'::text, 'receipt_edit'::text, 'void'::text, 'reallocation'::text, 'month_lock'::text, 'import'::text, 'customer_attr'::text, 'trip_review'::text, 'trip_edit'::text, 'trip_delete'::text, 'legacy_edit'::text, 'legacy_delete'::text, 'sheet_conflict_resolved'::text, 'fee_migration'::text, 'add_trip_fees'::text, 'set_trip_fee_type'::text, 'replace_trip_fee'::text, 'void_trip_fee'::text, 'set_book_fee_columns'::text, 'price_table_edit'::text, 'price_table_apply'::text, 'receipt_image'::text, 'receipt_image_remove'::text, 'adjust_month_delete'::text, 'rewrite_trip_fees'::text]))),
    CONSTRAINT event_pkey PRIMARY KEY (id),
    CONSTRAINT event_snapshot_check CHECK (
CASE kind
    WHEN 'paste'::text THEN ((before = '{}'::jsonb) AND (after ? 'trips'::text))
    WHEN 'receipt'::text THEN ((before = '{}'::jsonb) AND (after ? 'receipt'::text))
    WHEN 'import'::text THEN ((before = '{}'::jsonb) AND (after ? 'cutover'::text))
    WHEN 'price_edit'::text THEN ((before ? 'price'::text) AND (after ? 'price'::text))
    WHEN 'adjust_trip'::text THEN ((before ? 'trip'::text) AND (after ? 'adjustment'::text))
    WHEN 'adjust_month'::text THEN ((before ? 'month'::text) AND (after ? 'adjustment'::text))
    WHEN 'receipt_edit'::text THEN ((before ? 'receipt'::text) AND (after ? 'receipt'::text))
    WHEN 'month_lock'::text THEN COALESCE((((before ->> 'month'::text) = (after ->> 'month'::text)) AND (jsonb_typeof((before -> 'locked'::text)) = 'boolean'::text) AND (jsonb_typeof((after -> 'locked'::text)) = 'boolean'::text)), false)
    WHEN 'void'::text THEN ((before ? 'receipt'::text) AND (after ? 'receipt'::text))
    WHEN 'reallocation'::text THEN ((before ? 'allocations'::text) AND (after ? 'allocations'::text))
    WHEN 'customer_attr'::text THEN ((before ? 'customer'::text) AND (after ? 'customer'::text))
    WHEN 'trip_edit'::text THEN ((before ? 'trip'::text) AND (after ? 'trip'::text))
    WHEN 'legacy_edit'::text THEN ((before ? 'legacy'::text) AND (after ? 'legacy'::text))
    WHEN 'trip_delete'::text THEN ((before ? 'trip'::text) AND COALESCE((((after -> 'trip'::text) -> 'deleted'::text) = 'true'::jsonb), false))
    WHEN 'legacy_delete'::text THEN ((before ? 'legacy'::text) AND COALESCE((((after -> 'legacy'::text) -> 'deleted'::text) = 'true'::jsonb), false))
    WHEN 'trip_review'::text THEN (((before ->> 'status'::text) = 'pending_review'::text) AND (after ? 'trip'::text) AND ((after ->> 'status'::text) = ANY (ARRAY['confirmed'::text, 'rejected'::text])) AND (btrim(COALESCE((after ->> 'review_reason'::text), ''::text)) <> ''::text))
    WHEN 'sheet_conflict_resolved'::text THEN ((before ? 'target'::text) AND (before ? 'field'::text) AND (after ? 'target'::text) AND (after ? 'field'::text) AND (after ? 'source_row'::text) AND (after ? 'sheet_value'::text) AND (after ? 'decision'::text))
    WHEN 'fee_migration'::text THEN ((before = '{}'::jsonb) AND (after ? 'trip_count'::text) AND (after ? 'legacy_count'::text))
    WHEN 'add_trip_fees'::text THEN ((before ? 'targets'::text) AND (after ? 'targets'::text))
    WHEN 'set_trip_fee_type'::text THEN ((before ? 'targets'::text) AND (after ? 'targets'::text))
    WHEN 'replace_trip_fee'::text THEN ((before ? 'targets'::text) AND (after ? 'targets'::text))
    WHEN 'void_trip_fee'::text THEN ((before ? 'targets'::text) AND (after ? 'targets'::text))
    WHEN 'set_book_fee_columns'::text THEN ((before ? 'fee_columns'::text) AND (after ? 'fee_columns'::text))
    WHEN 'price_table_edit'::text THEN ((before ? 'price_table'::text) AND (after ? 'price_table'::text))
    WHEN 'price_table_apply'::text THEN ((before ? 'trips'::text) AND (after ? 'trips'::text))
    WHEN 'receipt_image'::text THEN ((before = '{}'::jsonb) AND (after ? 'image'::text))
    WHEN 'receipt_image_remove'::text THEN ((before ? 'image'::text) AND (after ? 'image'::text))
    WHEN 'adjust_month_delete'::text THEN ((before ? 'adjustment'::text) AND COALESCE((((after -> 'adjustment'::text) -> 'deleted'::text) = 'true'::jsonb), false))
    WHEN 'rewrite_trip_fees'::text THEN ((before ? 'targets'::text) AND (after ? 'targets'::text) AND (after ? 'source'::text))
    ELSE false
END)
);
ALTER TABLE sokhach.event OWNER TO sokhach_owner;
CREATE INDEX event_at ON sokhach.event USING btree (at);
CREATE INDEX event_customer_key ON sokhach.event USING btree (customer_id, idempotency_key);
CREATE INDEX event_customer_recent ON sokhach.event USING btree (customer_id, at DESC, id DESC);
CREATE UNIQUE INDEX event_import_once ON sokhach.event USING btree (customer_id, cutover_id) WHERE (kind = 'import'::text);
CREATE UNIQUE INDEX event_one_cutover_per_customer ON sokhach.event USING btree (customer_id) WHERE (kind = 'import'::text);
CREATE TRIGGER event_immutable BEFORE DELETE OR UPDATE ON sokhach.event FOR EACH ROW EXECUTE FUNCTION sokhach.reject_immutable_change();
COMMENT ON TABLE sokhach.event IS 'Vết chỉ thêm trước/sau; gồm mở/khóa tháng.';
COMMENT ON COLUMN sokhach.event.actor IS 'Đọc từ current_setting(''sokhach.actor'', false), từ chối rỗng trong hàm lệnh.';
COMMENT ON COLUMN sokhach.event.before IS 'Bắt buộc: tạo mới dùng {}; sửa/hủy/phân bổ lại có snapshot ID và giá trị trước.';
COMMENT ON COLUMN sokhach.event.after IS 'Bắt buộc theo kind: ID, giá trị sau và bộ phân bổ; CHECK chỉ xác nhận key tối thiểu, hàm phải kiểm nội dung/quan hệ trước commit.';
COMMENT ON COLUMN sokhach.event.idempotency_key IS 'Khóa lệnh nguồn, có thể lặp giữa các event của cùng lệnh.';
COMMENT ON COLUMN sokhach.event.cutover_id IS 'Chỉ event import có mốc chuyển; chỉ mục duy nhất chặn nhập lại kể cả khi không có dòng opening.';

CREATE TABLE sokhach.fee_type (
    id bigint GENERATED ALWAYS AS IDENTITY NOT NULL,
    name text NOT NULL,
    kind text NOT NULL,
    sign text NOT NULL,
    system_key text,
    active boolean DEFAULT true NOT NULL,
    sort integer NOT NULL,
    name_key text GENERATED ALWAYS AS (lower(btrim(name))) STORED,
    default_position integer,
    CONSTRAINT fee_type_default_position_check CHECK ((default_position > 0)),
    CONSTRAINT fee_type_default_position_key UNIQUE (default_position),
    CONSTRAINT fee_type_kind_check CHECK ((kind = ANY (ARRAY['service'::text, 'pass_through'::text]))),
    CONSTRAINT fee_type_name_key_key UNIQUE (name_key),
    CONSTRAINT fee_type_pkey PRIMARY KEY (id),
    CONSTRAINT fee_type_sign_check CHECK ((sign = ANY (ARRAY['positive'::text, 'negative'::text, 'any'::text]))),
    CONSTRAINT fee_type_sort_check CHECK ((sort > 0)),
    CONSTRAINT fee_type_system_key_key UNIQUE (system_key)
);
ALTER TABLE sokhach.fee_type OWNER TO sokhach_owner;

CREATE TABLE sokhach.fee_type_audit (
    id bigint GENERATED ALWAYS AS IDENTITY NOT NULL,
    fee_type_id bigint,
    actor text NOT NULL,
    payload jsonb NOT NULL,
    before_value jsonb NOT NULL,
    after_value jsonb NOT NULL,
    idempotency_key text NOT NULL,
    at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT fee_type_audit_fee_type_id_fkey FOREIGN KEY (fee_type_id) REFERENCES sokhach.fee_type(id),
    CONSTRAINT fee_type_audit_idempotency_key_key UNIQUE (idempotency_key),
    CONSTRAINT fee_type_audit_pkey PRIMARY KEY (id)
);
ALTER TABLE sokhach.fee_type_audit OWNER TO sokhach_owner;

CREATE TABLE sokhach.idempotency (
    customer_id bigint NOT NULL,
    key text NOT NULL,
    request_hash text NOT NULL,
    result jsonb NOT NULL,
    CONSTRAINT idempotency_customer_id_fkey FOREIGN KEY (customer_id) REFERENCES sokhach.customer(id),
    CONSTRAINT idempotency_key_check CHECK ((btrim(key) <> ''::text)),
    CONSTRAINT idempotency_pkey PRIMARY KEY (customer_id, key),
    CONSTRAINT idempotency_request_hash_check CHECK ((request_hash ~ '^[0-9a-f]{64}$'::text))
);
ALTER TABLE sokhach.idempotency OWNER TO sokhach_owner;
CREATE TRIGGER idempotency_immutable BEFORE DELETE OR UPDATE ON sokhach.idempotency FOR EACH ROW EXECUTE FUNCTION sokhach.reject_immutable_change();
COMMENT ON TABLE sokhach.idempotency IS 'Cùng khách và khóa: cùng băm trả kết quả cũ, khác băm bị từ chối.';
COMMENT ON COLUMN sokhach.idempotency.request_hash IS 'SHA-256 của yêu cầu chuẩn hóa do hàm lệnh xác định.';
COMMENT ON COLUMN sokhach.idempotency.result IS 'Kết quả tính sẵn để trả lại khi lặp lệnh.';

CREATE TABLE sokhach.legacy_row (
    id bigint GENERATED ALWAYS AS IDENTITY NOT NULL,
    customer_id bigint NOT NULL,
    cutover_id bigint NOT NULL,
    debt_month date NOT NULL,
    kind text NOT NULL,
    display jsonb NOT NULL,
    source_total_vnd bigint,
    source_tab text NOT NULL,
    source_row bigint NOT NULL,
    created_by_event bigint NOT NULL,
    CONSTRAINT legacy_event_fk FOREIGN KEY (created_by_event, customer_id) REFERENCES sokhach.event(id, customer_id),
    CONSTRAINT legacy_row_customer_id_cutover_id_fkey FOREIGN KEY (customer_id, cutover_id) REFERENCES sokhach.cutover_customer(customer_id, cutover_id),
    CONSTRAINT legacy_row_customer_unique UNIQUE (id, customer_id),
    CONSTRAINT legacy_row_cutover_id_source_tab_source_row_key UNIQUE (cutover_id, source_tab, source_row),
    CONSTRAINT legacy_row_debt_month_check CHECK ((EXTRACT(day FROM debt_month) = (1)::numeric)),
    CONSTRAINT legacy_row_display_check CHECK ((jsonb_typeof(display) = 'object'::text)),
    CONSTRAINT legacy_row_kind_check CHECK ((kind = ANY (ARRAY['trip'::text, 'receipt'::text]))),
    CONSTRAINT legacy_row_pkey PRIMARY KEY (id),
    CONSTRAINT legacy_row_source_row_check CHECK ((source_row > 0)),
    CONSTRAINT legacy_row_source_tab_check CHECK ((btrim(source_tab) <> ''::text))
);
ALTER TABLE sokhach.legacy_row OWNER TO sokhach_owner;
CREATE INDEX legacy_row_container_key ON sokhach.legacy_row USING btree (sokhach._normalize_key((display ->> 'container'::text)));
CREATE INDEX legacy_row_customer_month ON sokhach.legacy_row USING btree (customer_id, debt_month, id);
CREATE TRIGGER legacy_row_immutable BEFORE DELETE OR UPDATE ON sokhach.legacy_row FOR EACH ROW EXECUTE FUNCTION sokhach.reject_immutable_change();
CREATE TRIGGER legacy_row_insert_guard BEFORE INSERT ON sokhach.legacy_row FOR EACH ROW EXECUTE FUNCTION sokhach.guard_cutover_evidence();
COMMENT ON TABLE sokhach.legacy_row IS 'Dòng chuyến/thu đã nằm trong số dư đầu: chỉ hiển thị, không sửa, không phân bổ lại; không cột nào của bảng này tham gia công thức tiền.';
COMMENT ON COLUMN sokhach.legacy_row.display IS 'Các ô hiển thị từ nguồn; cấu trúc từng loại và dữ liệu thiếu cần review khi viết import.';
COMMENT ON COLUMN sokhach.legacy_row.source_total_vnd IS 'Thành tiền lịch sử theo ô tổng của sổ gốc; chỉ hiển thị, không cộng vào nợ.';

CREATE TABLE sokhach.legacy_trip_rev (
    id bigint GENERATED ALWAYS AS IDENTITY NOT NULL,
    legacy_row_id bigint NOT NULL,
    customer_id bigint NOT NULL,
    debt_month date NOT NULL,
    event_date date,
    container text,
    carrier text,
    shipper text,
    origin text,
    destination text,
    unit_price_vnd bigint,
    other_fee_vnd bigint,
    deleted boolean DEFAULT false NOT NULL,
    counted_vnd bigint NOT NULL,
    created_by_event bigint NOT NULL,
    CONSTRAINT legacy_trip_rev_created_by_event_customer_id_fkey FOREIGN KEY (created_by_event, customer_id) REFERENCES sokhach.event(id, customer_id),
    CONSTRAINT legacy_trip_rev_debt_month_check CHECK ((EXTRACT(day FROM debt_month) = (1)::numeric)),
    CONSTRAINT legacy_trip_rev_legacy_row_id_fkey FOREIGN KEY (legacy_row_id) REFERENCES sokhach.legacy_row(id),
    CONSTRAINT legacy_trip_rev_pkey PRIMARY KEY (id),
    CONSTRAINT legacy_trip_rev_unit_price_vnd_check CHECK ((unit_price_vnd >= 0))
);
ALTER TABLE sokhach.legacy_trip_rev OWNER TO sokhach_owner;
CREATE INDEX legacy_trip_rev_container_key ON sokhach.legacy_trip_rev USING btree (sokhach._normalize_key(container));
CREATE INDEX legacy_trip_rev_latest ON sokhach.legacy_trip_rev USING btree (legacy_row_id, id DESC);
CREATE TRIGGER legacy_trip_rev_immutable BEFORE DELETE OR UPDATE ON sokhach.legacy_trip_rev FOR EACH ROW EXECUTE FUNCTION sokhach.reject_immutable_change();

CREATE TABLE sokhach.month_state (
    customer_id bigint NOT NULL,
    month date NOT NULL,
    locked boolean NOT NULL,
    changed_by text NOT NULL,
    changed_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT month_state_changed_by_check CHECK ((btrim(changed_by) <> ''::text)),
    CONSTRAINT month_state_customer_id_fkey FOREIGN KEY (customer_id) REFERENCES sokhach.customer(id),
    CONSTRAINT month_state_month_check CHECK ((EXTRACT(day FROM month) = (1)::numeric)),
    CONSTRAINT month_state_pkey PRIMARY KEY (customer_id, month)
);
ALTER TABLE sokhach.month_state OWNER TO sokhach_owner;
COMMENT ON TABLE sokhach.month_state IS 'Cờ ghi đè; thiếu hàng thì chỉ tháng hiện tại theo Asia/Ho_Chi_Minh mở. Mở/khóa ghi event theo V7-CSM.';
COMMENT ON COLUMN sokhach.month_state.locked IS 'Không DEFAULT: thiếu hàng dùng mặc định động theo giờ VN; hàng có sẵn ghi đè mặc định.';
COMMENT ON COLUMN sokhach.month_state.changed_by IS 'Danh tính phiên máy chủ đã xác minh, không lấy từ body.';

CREATE TABLE sokhach.offset_command (
    low_customer_id bigint NOT NULL,
    high_customer_id bigint NOT NULL,
    key text NOT NULL,
    payload jsonb NOT NULL,
    result jsonb NOT NULL,
    CONSTRAINT offset_command_check CHECK ((low_customer_id < high_customer_id)),
    CONSTRAINT offset_command_high_customer_id_fkey FOREIGN KEY (high_customer_id) REFERENCES sokhach.customer(id),
    CONSTRAINT offset_command_key_check CHECK ((btrim(key) <> ''::text)),
    CONSTRAINT offset_command_low_customer_id_fkey FOREIGN KEY (low_customer_id) REFERENCES sokhach.customer(id),
    CONSTRAINT offset_command_pkey PRIMARY KEY (low_customer_id, high_customer_id, key)
);
ALTER TABLE sokhach.offset_command OWNER TO sokhach_owner;
CREATE TRIGGER offset_command_immutable BEFORE DELETE OR UPDATE ON sokhach.offset_command FOR EACH ROW EXECUTE FUNCTION sokhach.reject_immutable_change();

CREATE TABLE sokhach.offset_pair (
    id bigint GENERATED ALWAYS AS IDENTITY NOT NULL,
    source_customer_id bigint NOT NULL,
    target_customer_id bigint NOT NULL,
    target_receipt_id bigint NOT NULL,
    source_pid text NOT NULL,
    date date NOT NULL,
    amount_vnd bigint NOT NULL,
    created_by_event bigint NOT NULL,
    changed_by_event bigint,
    voided_by_event bigint,
    void_reason text,
    CONSTRAINT offset_pair_amount_vnd_check CHECK ((amount_vnd > 0)),
    CONSTRAINT offset_pair_changed_by_event_source_customer_id_fkey FOREIGN KEY (changed_by_event, source_customer_id) REFERENCES sokhach.event(id, customer_id),
    CONSTRAINT offset_pair_check CHECK ((source_customer_id <> target_customer_id)),
    CONSTRAINT offset_pair_check1 CHECK (((void_reason IS NULL) = (voided_by_event IS NULL))),
    CONSTRAINT offset_pair_consistency_trigger TRIGGER DEFERRABLE INITIALLY DEFERRED,
    CONSTRAINT offset_pair_created_by_event_source_customer_id_fkey FOREIGN KEY (created_by_event, source_customer_id) REFERENCES sokhach.event(id, customer_id),
    CONSTRAINT offset_pair_pkey PRIMARY KEY (id),
    CONSTRAINT offset_pair_source_customer_id_fkey FOREIGN KEY (source_customer_id) REFERENCES sokhach.customer(id),
    CONSTRAINT offset_pair_source_customer_id_source_pid_key UNIQUE (source_customer_id, source_pid),
    CONSTRAINT offset_pair_target_customer_id_fkey FOREIGN KEY (target_customer_id) REFERENCES sokhach.customer(id),
    CONSTRAINT offset_pair_target_receipt_id_key UNIQUE (target_receipt_id),
    CONSTRAINT offset_pair_target_receipt_id_target_customer_id_fkey FOREIGN KEY (target_receipt_id, target_customer_id) REFERENCES sokhach.receipt(id, customer_id),
    CONSTRAINT offset_pair_void_reason_check CHECK ((btrim(void_reason) <> ''::text)),
    CONSTRAINT offset_pair_voided_by_event_source_customer_id_fkey FOREIGN KEY (voided_by_event, source_customer_id) REFERENCES sokhach.event(id, customer_id)
);
ALTER TABLE sokhach.offset_pair OWNER TO sokhach_owner;
CREATE CONSTRAINT TRIGGER offset_pair_consistency_trigger AFTER INSERT OR UPDATE ON sokhach.offset_pair DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION sokhach.check_offset_pair();
CREATE TRIGGER offset_pair_guard BEFORE DELETE OR UPDATE ON sokhach.offset_pair FOR EACH ROW EXECUTE FUNCTION sokhach.guard_offset_pair();
CREATE TRIGGER offset_pair_pid BEFORE INSERT ON sokhach.offset_pair FOR EACH ROW EXECUTE FUNCTION sokhach.check_offset_pid();

CREATE TABLE sokhach.opening_balance (
    id bigint GENERATED ALWAYS AS IDENTITY NOT NULL,
    customer_id bigint NOT NULL,
    cutover_id bigint NOT NULL,
    debt_month date NOT NULL,
    amount_vnd bigint NOT NULL,
    source_tab text NOT NULL,
    source_row bigint NOT NULL,
    created_by_event bigint NOT NULL,
    CONSTRAINT opening_balance_customer_id_cutover_id_fkey FOREIGN KEY (customer_id, cutover_id) REFERENCES sokhach.cutover_customer(customer_id, cutover_id),
    CONSTRAINT opening_balance_customer_id_debt_month_cutover_id_key UNIQUE (customer_id, debt_month, cutover_id),
    CONSTRAINT opening_balance_debt_month_check CHECK ((EXTRACT(day FROM debt_month) = (1)::numeric)),
    CONSTRAINT opening_balance_pkey PRIMARY KEY (id),
    CONSTRAINT opening_balance_source_row_check CHECK ((source_row > 0)),
    CONSTRAINT opening_balance_source_tab_check CHECK ((btrim(source_tab) <> ''::text)),
    CONSTRAINT opening_event_fk FOREIGN KEY (created_by_event, customer_id) REFERENCES sokhach.event(id, customer_id)
);
ALTER TABLE sokhach.opening_balance OWNER TO sokhach_owner;
CREATE INDEX opening_balance_customer_month ON sokhach.opening_balance USING btree (customer_id, debt_month);
CREATE TRIGGER opening_balance_immutable BEFORE DELETE OR UPDATE ON sokhach.opening_balance FOR EACH ROW EXECUTE FUNCTION sokhach.reject_immutable_change();
CREATE TRIGGER opening_balance_insert_guard BEFORE INSERT ON sokhach.opening_balance FOR EACH ROW EXECUTE FUNCTION sokhach.guard_cutover_evidence();
COMMENT ON TABLE sokhach.opening_balance IS 'Số dư đầu theo khách và tháng tại mốc chuyển, chỉ thêm; lịch sử nguồn không cộng lại.';
COMMENT ON COLUMN sokhach.opening_balance.amount_vnd IS 'Có dấu: âm là khách ứng trước; 0 chỉ ghi khi nguồn chứng minh đúng 0, NULL không được phép.';
COMMENT ON COLUMN sokhach.opening_balance.source_row IS 'Dòng mỏ neo trong tab nguồn, không chứa dữ liệu nguồn trong bản nháp.';

CREATE TABLE sokhach.price_location (
    id bigint GENERATED ALWAYS AS IDENTITY NOT NULL,
    customer_id bigint NOT NULL,
    name text NOT NULL,
    name_key text NOT NULL,
    CONSTRAINT price_location_customer_id_fkey FOREIGN KEY (customer_id) REFERENCES sokhach.customer(id),
    CONSTRAINT price_location_customer_id_name_key_key UNIQUE (customer_id, name_key),
    CONSTRAINT price_location_id_customer_id_key UNIQUE (id, customer_id),
    CONSTRAINT price_location_name_check CHECK (((btrim(name) <> ''::text) AND (length(name) <= 200))),
    CONSTRAINT price_location_pkey PRIMARY KEY (id)
);
ALTER TABLE sokhach.price_location OWNER TO sokhach_owner;

CREATE TABLE sokhach.price_location_alias (
    customer_id bigint NOT NULL,
    location_id bigint NOT NULL,
    alias text NOT NULL,
    alias_key text NOT NULL,
    CONSTRAINT price_location_alias_alias_check CHECK (((btrim(alias) <> ''::text) AND (length(alias) <= 200))),
    CONSTRAINT price_location_alias_location_id_customer_id_fkey FOREIGN KEY (location_id, customer_id) REFERENCES sokhach.price_location(id, customer_id) ON DELETE CASCADE,
    CONSTRAINT price_location_alias_pkey PRIMARY KEY (customer_id, alias_key)
);
ALTER TABLE sokhach.price_location_alias OWNER TO sokhach_owner;

CREATE TABLE sokhach.price_period (
    id bigint GENERATED ALWAYS AS IDENTITY NOT NULL,
    customer_id bigint NOT NULL,
    valid_from date NOT NULL,
    valid_to date,
    CONSTRAINT price_period_check CHECK (((valid_to IS NULL) OR (valid_to >= valid_from))),
    CONSTRAINT price_period_customer_id_fkey FOREIGN KEY (customer_id) REFERENCES sokhach.customer(id),
    CONSTRAINT price_period_id_customer_id_key UNIQUE (id, customer_id),
    CONSTRAINT price_period_pkey PRIMARY KEY (id)
);
ALTER TABLE sokhach.price_period OWNER TO sokhach_owner;

CREATE TABLE sokhach.price_rate (
    period_id bigint NOT NULL,
    location_id bigint NOT NULL,
    customer_id bigint NOT NULL,
    destination text DEFAULT ''::text NOT NULL,
    destination_key text DEFAULT ''::text NOT NULL,
    tier text NOT NULL,
    unit_price_vnd bigint NOT NULL,
    CONSTRAINT price_rate_location_id_customer_id_fkey FOREIGN KEY (location_id, customer_id) REFERENCES sokhach.price_location(id, customer_id) ON DELETE CASCADE,
    CONSTRAINT price_rate_period_id_customer_id_fkey FOREIGN KEY (period_id, customer_id) REFERENCES sokhach.price_period(id, customer_id) ON DELETE CASCADE,
    CONSTRAINT price_rate_pkey PRIMARY KEY (period_id, location_id, destination_key, tier),
    CONSTRAINT price_rate_tier_check CHECK ((tier = ANY (ARRAY['khach'::text, 'tt'::text]))),
    CONSTRAINT price_rate_unit_price_vnd_check CHECK ((unit_price_vnd >= 0))
);
ALTER TABLE sokhach.price_rate OWNER TO sokhach_owner;

CREATE TABLE sokhach.price_tt_shipper (
    customer_id bigint NOT NULL,
    name text NOT NULL,
    shipper_key text NOT NULL,
    CONSTRAINT price_tt_shipper_customer_id_fkey FOREIGN KEY (customer_id) REFERENCES sokhach.customer(id),
    CONSTRAINT price_tt_shipper_name_check CHECK (((btrim(name) <> ''::text) AND (length(name) <= 200))),
    CONSTRAINT price_tt_shipper_pkey PRIMARY KEY (customer_id, shipper_key)
);
ALTER TABLE sokhach.price_tt_shipper OWNER TO sokhach_owner;

CREATE TABLE sokhach.receipt (
    id bigint GENERATED ALWAYS AS IDENTITY NOT NULL,
    customer_id bigint NOT NULL,
    pid text NOT NULL,
    date date NOT NULL,
    method text NOT NULL,
    reference text,
    amount_vnd bigint NOT NULL,
    void_reason text,
    voided_on date,
    voided_by text,
    meta_changed_by_event bigint,
    voided_by_event bigint,
    created_by_event bigint NOT NULL,
    CONSTRAINT receipt_amount_vnd_check CHECK ((amount_vnd > 0)),
    CONSTRAINT receipt_check CHECK ((((void_reason IS NULL) AND (voided_on IS NULL) AND (voided_by IS NULL) AND (voided_by_event IS NULL)) OR ((void_reason IS NOT NULL) AND (voided_on IS NOT NULL) AND (voided_by IS NOT NULL) AND (voided_by_event IS NOT NULL)))),
    CONSTRAINT receipt_customer_id_fkey FOREIGN KEY (customer_id) REFERENCES sokhach.customer(id),
    CONSTRAINT receipt_customer_id_pid_key UNIQUE (customer_id, pid),
    CONSTRAINT receipt_event_fk FOREIGN KEY (created_by_event, customer_id) REFERENCES sokhach.event(id, customer_id),
    CONSTRAINT receipt_id_customer_id_key UNIQUE (id, customer_id),
    CONSTRAINT receipt_meta_event_fk FOREIGN KEY (meta_changed_by_event, customer_id) REFERENCES sokhach.event(id, customer_id),
    CONSTRAINT receipt_method_check CHECK ((method = ANY (ARRAY['THU TIỀN'::text, 'CẤN TRỪ'::text, 'ỨNG TRƯỚC'::text, 'KHÁC'::text]))),
    CONSTRAINT receipt_offset_pair_check TRIGGER DEFERRABLE INITIALLY DEFERRED,
    CONSTRAINT receipt_pid_check CHECK ((btrim(pid) <> ''::text)),
    CONSTRAINT receipt_pkey PRIMARY KEY (id),
    CONSTRAINT receipt_reference_check CHECK (((reference IS NULL) OR (btrim(reference) <> ''::text))),
    CONSTRAINT receipt_void_event_fk FOREIGN KEY (voided_by_event, customer_id) REFERENCES sokhach.event(id, customer_id),
    CONSTRAINT receipt_void_reason_check CHECK (((void_reason IS NULL) OR (btrim(void_reason) <> ''::text))),
    CONSTRAINT receipt_voided_by_check CHECK (((voided_by IS NULL) OR (btrim(voided_by) <> ''::text)))
);
ALTER TABLE sokhach.receipt OWNER TO sokhach_owner;
CREATE INDEX receipt_customer_fifo ON sokhach.receipt USING btree (customer_id, date, pid) WHERE (voided_on IS NULL);
CREATE INDEX receipt_voided_by_event ON sokhach.receipt USING btree (voided_by_event) WHERE (voided_by_event IS NOT NULL);
CREATE TRIGGER receipt_guard BEFORE DELETE OR UPDATE ON sokhach.receipt FOR EACH ROW EXECUTE FUNCTION sokhach.guard_receipt_change();
CREATE CONSTRAINT TRIGGER receipt_offset_pair_check AFTER INSERT OR UPDATE ON sokhach.receipt DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION sokhach.check_offset_pair();
CREATE TRIGGER receipt_offset_pid BEFORE INSERT ON sokhach.receipt FOR EACH ROW EXECUTE FUNCTION sokhach.check_offset_pid();
COMMENT ON TABLE sokhach.receipt IS 'Một phiếu của một khách; hủy không phân bổ lại phiếu khác.';
COMMENT ON COLUMN sokhach.receipt.pid IS 'Mã phiếu do server cấp, duy nhất trong khách kể cả đã hủy.';
COMMENT ON COLUMN sokhach.receipt.date IS 'Ngày phiếu; FIFO xếp theo ngày rồi pid.';
COMMENT ON COLUMN sokhach.receipt.reference IS 'V7-CSM: optional text; duplicate warns only; blank stored as NULL.';
COMMENT ON COLUMN sokhach.receipt.amount_vnd IS 'Tổng phiếu bất biến; phải bằng tổng dòng hiệu lực khi phiếu còn sống.';
COMMENT ON COLUMN sokhach.receipt.void_reason IS 'Hủy bắt buộc lý do không rỗng.';
COMMENT ON COLUMN sokhach.receipt.created_by_event IS 'Event tạo phiếu; đổi ngày/hình thức/hủy phải có event tương ứng trước khi commit.';

CREATE TABLE sokhach.receipt_image (
    id bigint GENERATED ALWAYS AS IDENTITY NOT NULL,
    customer_id bigint NOT NULL,
    receipt_id bigint NOT NULL,
    sha256 text NOT NULL,
    content_type text NOT NULL,
    data bytea NOT NULL,
    created_by_event bigint NOT NULL,
    removed_reason text,
    removed_by_event bigint,
    CONSTRAINT receipt_image_check CHECK (((removed_reason IS NULL) = (removed_by_event IS NULL))),
    CONSTRAINT receipt_image_content_type_check CHECK ((content_type = ANY (ARRAY['image/png'::text, 'image/jpeg'::text, 'image/webp'::text]))),
    CONSTRAINT receipt_image_created_by_event_customer_id_fkey FOREIGN KEY (created_by_event, customer_id) REFERENCES sokhach.event(id, customer_id),
    CONSTRAINT receipt_image_customer_id_fkey FOREIGN KEY (customer_id) REFERENCES sokhach.customer(id),
    CONSTRAINT receipt_image_data_check CHECK (((octet_length(data) >= 1) AND (octet_length(data) <= 2097152))),
    CONSTRAINT receipt_image_pkey PRIMARY KEY (id),
    CONSTRAINT receipt_image_receipt_id_customer_id_fkey FOREIGN KEY (receipt_id, customer_id) REFERENCES sokhach.receipt(id, customer_id),
    CONSTRAINT receipt_image_removed_by_event_customer_id_fkey FOREIGN KEY (removed_by_event, customer_id) REFERENCES sokhach.event(id, customer_id),
    CONSTRAINT receipt_image_removed_reason_check CHECK (((removed_reason IS NULL) OR (btrim(removed_reason) <> ''::text))),
    CONSTRAINT receipt_image_sha256_check CHECK ((sha256 ~ '^[0-9a-f]{64}$'::text))
);
ALTER TABLE sokhach.receipt_image OWNER TO sokhach_owner;
CREATE UNIQUE INDEX receipt_image_active_unique ON sokhach.receipt_image USING btree (receipt_id, sha256) WHERE (removed_by_event IS NULL);
CREATE INDEX receipt_image_customer ON sokhach.receipt_image USING btree (customer_id, receipt_id);
CREATE INDEX receipt_image_sha256 ON sokhach.receipt_image USING btree (sha256) WHERE (removed_by_event IS NULL);
CREATE TRIGGER receipt_image_guard BEFORE DELETE OR UPDATE ON sokhach.receipt_image FOR EACH ROW EXECUTE FUNCTION sokhach._guard_receipt_image();

CREATE TABLE sokhach.receipt_line (
    id bigint GENERATED ALWAYS AS IDENTITY NOT NULL,
    receipt_id bigint NOT NULL,
    customer_id bigint NOT NULL,
    debt_month date NOT NULL,
    kind text NOT NULL,
    amount_vnd bigint NOT NULL,
    created_by_event bigint NOT NULL,
    superseded_by_event bigint,
    CONSTRAINT receipt_line_amount_vnd_check CHECK ((amount_vnd > 0)),
    CONSTRAINT receipt_line_created_by_event_customer_id_fkey FOREIGN KEY (created_by_event, customer_id) REFERENCES sokhach.event(id, customer_id),
    CONSTRAINT receipt_line_debt_month_check CHECK ((EXTRACT(day FROM debt_month) = (1)::numeric)),
    CONSTRAINT receipt_line_kind_check CHECK ((kind = ANY (ARRAY['debt'::text, 'advance'::text]))),
    CONSTRAINT receipt_line_pkey PRIMARY KEY (id),
    CONSTRAINT receipt_line_receipt_id_customer_id_fkey FOREIGN KEY (receipt_id, customer_id) REFERENCES sokhach.receipt(id, customer_id),
    CONSTRAINT receipt_line_superseded_by_event_customer_id_fkey FOREIGN KEY (superseded_by_event, customer_id) REFERENCES sokhach.event(id, customer_id)
);
ALTER TABLE sokhach.receipt_line OWNER TO sokhach_owner;
CREATE INDEX receipt_line_active_month ON sokhach.receipt_line USING btree (customer_id, debt_month, receipt_id) WHERE (superseded_by_event IS NULL);
CREATE INDEX receipt_line_active_receipt ON sokhach.receipt_line USING btree (receipt_id) WHERE (superseded_by_event IS NULL);
CREATE TRIGGER receipt_line_guard BEFORE DELETE OR UPDATE ON sokhach.receipt_line FOR EACH ROW EXECUTE FUNCTION sokhach.guard_receipt_line_change();
COMMENT ON TABLE sokhach.receipt_line IS 'Phân bổ có phiên bản; hủy phiếu giữ dòng để xem lịch sử.';
COMMENT ON COLUMN sokhach.receipt_line.debt_month IS 'Tháng được phân bổ; không suy từ ngày phiếu.';
COMMENT ON COLUMN sokhach.receipt_line.kind IS 'advance là phần dư ở tháng cuối, vẫn nằm trong sổ khách.';
COMMENT ON COLUMN sokhach.receipt_line.created_by_event IS 'Sự kiện tạo phiên bản phân bổ này.';
COMMENT ON COLUMN sokhach.receipt_line.superseded_by_event IS 'NULL là phiên bản phân bổ hiện hành; reallocation hoặc void đóng dòng cũ.';

CREATE TABLE sokhach.reminder_log (
    id bigint GENERATED ALWAYS AS IDENTITY NOT NULL,
    customer_id bigint NOT NULL,
    source text NOT NULL,
    reminded_at date NOT NULL,
    actor text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT reminder_log_actor_check CHECK ((btrim(actor) <> ''::text)),
    CONSTRAINT reminder_log_customer_id_fkey FOREIGN KEY (customer_id) REFERENCES sokhach.customer(id),
    CONSTRAINT reminder_log_customer_id_source_reminded_at_key UNIQUE (customer_id, source, reminded_at),
    CONSTRAINT reminder_log_pkey PRIMARY KEY (id),
    CONSTRAINT reminder_log_source_check CHECK ((source = ANY (ARRAY['zalo'::text, 'copy-button'::text, 'manual'::text])))
);
ALTER TABLE sokhach.reminder_log OWNER TO sokhach_owner;
CREATE INDEX reminder_log_customer ON sokhach.reminder_log USING btree (customer_id, reminded_at DESC);
COMMENT ON TABLE sokhach.reminder_log IS 'Mốc đã nhắc đòi nợ từng khách (nguồn copy-button/zalo/manual); một dòng mỗi khách/nguồn/ngày; không tham gia tính tiền.';

CREATE TABLE sokhach.trip (
    id bigint GENERATED ALWAYS AS IDENTITY NOT NULL,
    customer_id bigint NOT NULL,
    debt_month date NOT NULL,
    event_date date,
    container text,
    booking text,
    status text DEFAULT 'confirmed'::text NOT NULL,
    carrier text,
    shipper text,
    origin text,
    destination text,
    note text,
    source_ref text,
    created_by_event bigint NOT NULL,
    reviewed_by_event bigint,
    CONSTRAINT trip_created_event_fk FOREIGN KEY (created_by_event, customer_id) REFERENCES sokhach.event(id, customer_id),
    CONSTRAINT trip_customer_id_fkey FOREIGN KEY (customer_id) REFERENCES sokhach.customer(id),
    CONSTRAINT trip_debt_month_check CHECK ((EXTRACT(day FROM debt_month) = (1)::numeric)),
    CONSTRAINT trip_event_customer_unique UNIQUE (id, customer_id),
    CONSTRAINT trip_id_customer_id_debt_month_key UNIQUE (id, customer_id, debt_month),
    CONSTRAINT trip_missing_date_check TRIGGER DEFERRABLE INITIALLY DEFERRED,
    CONSTRAINT trip_missing_date_fee_only CHECK (((event_date IS NOT NULL) OR (container IS NULL) OR (container = ''::text))),
    CONSTRAINT trip_pkey PRIMARY KEY (id),
    CONSTRAINT trip_review_event_fk FOREIGN KEY (reviewed_by_event, customer_id) REFERENCES sokhach.event(id, customer_id),
    CONSTRAINT trip_review_state CHECK ((((status <> 'pending_review'::text) OR (reviewed_by_event IS NULL)) AND ((status <> 'rejected'::text) OR (reviewed_by_event IS NOT NULL)))),
    CONSTRAINT trip_status_check CHECK ((status = ANY (ARRAY['confirmed'::text, 'pending_review'::text, 'rejected'::text])))
);
ALTER TABLE sokhach.trip OWNER TO sokhach_owner;
CREATE INDEX trip_customer_month ON sokhach.trip USING btree (customer_id, debt_month, id);
CREATE TRIGGER trip_immutable BEFORE DELETE OR UPDATE ON sokhach.trip FOR EACH ROW EXECUTE FUNCTION sokhach.reject_immutable_change();
CREATE CONSTRAINT TRIGGER trip_missing_date_check AFTER INSERT ON sokhach.trip DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION sokhach.check_trip_missing_date();
CREATE TRIGGER trip_sheet_cross_customer BEFORE INSERT ON sokhach.trip FOR EACH ROW EXECUTE FUNCTION sokhach.guard_sheet_cross_customer();
COMMENT ON TABLE sokhach.trip IS 'Danh tính chuyến chỉ thêm; container không phải khóa duy nhất.';
COMMENT ON COLUMN sokhach.trip.debt_month IS 'Tháng gốc giữ FK; kỳ nợ hiện tại ở v_trip_current theo NHAP-SHEET-01.';
COMMENT ON COLUMN sokhach.trip.event_date IS 'Ngày xe nhập kho gốc; sửa ngày qua trip_info_rev, kỳ nợ hiện tại theo tháng ngày chuyến.';
COMMENT ON COLUMN sokhach.trip.container IS 'Phân loại phí lẻ theo JS truthiness: chỉ NULL hoặc chuỗi rỗng là không có container; chuỗi toàn khoảng trắng vẫn là giá trị có mặt.';
COMMENT ON COLUMN sokhach.trip.source_ref IS 'Tham chiếu nguồn nếu có; không chứa chứng từ thật trong bản nháp.';
COMMENT ON COLUMN sokhach.trip.reviewed_by_event IS 'Event kết luận CHỜ KIỂM (NEWTRIP-01); chỉ đổi một lần từ pending_review sang confirmed/rejected.';

CREATE TABLE sokhach.trip_fee_line (
    id bigint GENERATED ALWAYS AS IDENTITY NOT NULL,
    customer_id bigint NOT NULL,
    trip_id bigint,
    legacy_row_id bigint,
    fee_type_id bigint NOT NULL,
    amount_vnd bigint NOT NULL,
    note text,
    created_by_event bigint NOT NULL,
    voided_by_event bigint,
    CONSTRAINT fee_line_created_event_fk FOREIGN KEY (created_by_event, customer_id) REFERENCES sokhach.event(id, customer_id),
    CONSTRAINT fee_line_legacy_customer_fk FOREIGN KEY (legacy_row_id, customer_id) REFERENCES sokhach.legacy_row(id, customer_id),
    CONSTRAINT fee_line_trip_customer_fk FOREIGN KEY (trip_id, customer_id) REFERENCES sokhach.trip(id, customer_id),
    CONSTRAINT fee_line_voided_event_fk FOREIGN KEY (voided_by_event, customer_id) REFERENCES sokhach.event(id, customer_id),
    CONSTRAINT trip_fee_cache_check TRIGGER DEFERRABLE INITIALLY DEFERRED,
    CONSTRAINT trip_fee_line_amount_vnd_check CHECK ((amount_vnd <> 0)),
    CONSTRAINT trip_fee_line_check CHECK (((trip_id IS NOT NULL) <> (legacy_row_id IS NOT NULL))),
    CONSTRAINT trip_fee_line_customer_id_fkey FOREIGN KEY (customer_id) REFERENCES sokhach.customer(id),
    CONSTRAINT trip_fee_line_fee_type_id_fkey FOREIGN KEY (fee_type_id) REFERENCES sokhach.fee_type(id),
    CONSTRAINT trip_fee_line_pkey PRIMARY KEY (id)
);
ALTER TABLE sokhach.trip_fee_line OWNER TO sokhach_owner;
CREATE INDEX trip_fee_line_customer ON sokhach.trip_fee_line USING btree (customer_id, id);
CREATE INDEX trip_fee_line_legacy_active ON sokhach.trip_fee_line USING btree (legacy_row_id) WHERE (voided_by_event IS NULL);
CREATE INDEX trip_fee_line_trip_active ON sokhach.trip_fee_line USING btree (trip_id) WHERE (voided_by_event IS NULL);
CREATE TRIGGER fee_line_guard BEFORE INSERT OR DELETE OR UPDATE ON sokhach.trip_fee_line FOR EACH ROW EXECUTE FUNCTION sokhach._guard_fee_line();
CREATE CONSTRAINT TRIGGER trip_fee_cache_check AFTER INSERT OR DELETE OR UPDATE ON sokhach.trip_fee_line DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION sokhach._fee_cache_check();

CREATE TABLE sokhach.trip_info_rev (
    id bigint GENERATED ALWAYS AS IDENTITY NOT NULL,
    trip_id bigint NOT NULL,
    customer_id bigint NOT NULL,
    debt_month date NOT NULL,
    event_date date,
    container text,
    carrier text,
    shipper text,
    origin text,
    destination text,
    status text NOT NULL,
    deleted boolean DEFAULT false NOT NULL,
    created_by_event bigint NOT NULL,
    CONSTRAINT trip_info_rev_created_by_event_customer_id_fkey FOREIGN KEY (created_by_event, customer_id) REFERENCES sokhach.event(id, customer_id),
    CONSTRAINT trip_info_rev_debt_month_check CHECK ((EXTRACT(day FROM debt_month) = (1)::numeric)),
    CONSTRAINT trip_info_rev_pkey PRIMARY KEY (id),
    CONSTRAINT trip_info_rev_status_check CHECK ((status = ANY (ARRAY['confirmed'::text, 'pending_review'::text, 'rejected'::text]))),
    CONSTRAINT trip_info_rev_trip_id_customer_id_fkey FOREIGN KEY (trip_id, customer_id) REFERENCES sokhach.trip(id, customer_id)
);
ALTER TABLE sokhach.trip_info_rev OWNER TO sokhach_owner;
CREATE INDEX trip_info_rev_latest ON sokhach.trip_info_rev USING btree (trip_id, id DESC);
CREATE TRIGGER trip_info_rev_immutable BEFORE DELETE OR UPDATE ON sokhach.trip_info_rev FOR EACH ROW EXECUTE FUNCTION sokhach.reject_immutable_change();

CREATE TABLE sokhach.trip_price_rev (
    id bigint GENERATED ALWAYS AS IDENTITY NOT NULL,
    trip_id bigint NOT NULL,
    unit_price_vnd bigint,
    other_fee_vnd bigint,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    customer_id bigint NOT NULL,
    created_by_event bigint NOT NULL,
    CONSTRAINT price_event_fk FOREIGN KEY (created_by_event, customer_id) REFERENCES sokhach.event(id, customer_id),
    CONSTRAINT price_trip_customer_fk FOREIGN KEY (trip_id, customer_id) REFERENCES sokhach.trip(id, customer_id),
    CONSTRAINT trip_price_cache_check TRIGGER DEFERRABLE INITIALLY DEFERRED,
    CONSTRAINT trip_price_missing_date_check TRIGGER DEFERRABLE INITIALLY DEFERRED,
    CONSTRAINT trip_price_rev_pkey PRIMARY KEY (id),
    CONSTRAINT trip_price_rev_trip_id_fkey FOREIGN KEY (trip_id) REFERENCES sokhach.trip(id),
    CONSTRAINT trip_price_rev_unit_price_vnd_check CHECK ((unit_price_vnd >= 0))
);
ALTER TABLE sokhach.trip_price_rev OWNER TO sokhach_owner;
CREATE INDEX trip_price_rev_latest ON sokhach.trip_price_rev USING btree (trip_id, id DESC);
CREATE CONSTRAINT TRIGGER trip_price_cache_check AFTER INSERT OR UPDATE ON sokhach.trip_price_rev DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION sokhach._fee_cache_check();
CREATE CONSTRAINT TRIGGER trip_price_missing_date_check AFTER INSERT ON sokhach.trip_price_rev DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION sokhach.check_trip_missing_date();
CREATE TRIGGER trip_price_rev_immutable BEFORE DELETE OR UPDATE ON sokhach.trip_price_rev FOR EACH ROW EXECUTE FUNCTION sokhach.reject_immutable_change();
COMMENT ON TABLE sokhach.trip_price_rev IS 'Giá hiện tại là revision id lớn nhất của chuyến; sửa giá thêm dòng.';
COMMENT ON COLUMN sokhach.trip_price_rev.unit_price_vnd IS 'NULL là chưa biết, không phải 0.';
COMMENT ON COLUMN sokhach.trip_price_rev.other_fee_vnd IS 'NULL giữ nguyên từ nguồn; ĐÃ CHỐT 20/10/2026: khi có đơn giá thì phụ phí NULL tính 0, không đổi NULL lưu trữ.';

CREATE TABLE sokhach.trip_price_source (
    price_rev_id bigint NOT NULL,
    customer_id bigint NOT NULL,
    rate jsonb NOT NULL,
    created_by_event bigint NOT NULL,
    CONSTRAINT trip_price_source_created_by_event_fkey FOREIGN KEY (created_by_event) REFERENCES sokhach.event(id),
    CONSTRAINT trip_price_source_customer_id_fkey FOREIGN KEY (customer_id) REFERENCES sokhach.customer(id),
    CONSTRAINT trip_price_source_pkey PRIMARY KEY (price_rev_id),
    CONSTRAINT trip_price_source_price_rev_id_fkey FOREIGN KEY (price_rev_id) REFERENCES sokhach.trip_price_rev(id),
    CONSTRAINT trip_price_source_rate_check CHECK ((jsonb_typeof(rate) = 'object'::text))
);
ALTER TABLE sokhach.trip_price_source OWNER TO sokhach_owner;
CREATE TRIGGER trip_price_source_immutable BEFORE DELETE OR UPDATE ON sokhach.trip_price_source FOR EACH ROW EXECUTE FUNCTION sokhach.reject_immutable_change();

CREATE TABLE sokhach.zalo_link (
    id bigint GENERATED ALWAYS AS IDENTITY NOT NULL,
    conversation_id text NOT NULL,
    customer_id bigint NOT NULL,
    linked_by text NOT NULL,
    linked_at timestamp with time zone DEFAULT now() NOT NULL,
    unlinked_by text,
    unlinked_at timestamp with time zone,
    unlink_reason text,
    CONSTRAINT zalo_link_check CHECK ((((unlinked_at IS NULL) = (unlinked_by IS NULL)) AND ((unlinked_at IS NULL) = (unlink_reason IS NULL)))),
    CONSTRAINT zalo_link_conversation_id_check CHECK ((conversation_id ~ '^[0-9a-f]{64}$'::text)),
    CONSTRAINT zalo_link_customer_id_fkey FOREIGN KEY (customer_id) REFERENCES sokhach.customer(id),
    CONSTRAINT zalo_link_linked_by_check CHECK ((btrim(linked_by) <> ''::text)),
    CONSTRAINT zalo_link_pkey PRIMARY KEY (id),
    CONSTRAINT zalo_link_unlink_reason_check CHECK (((unlink_reason IS NULL) OR (btrim(unlink_reason) <> ''::text))),
    CONSTRAINT zalo_link_unlinked_by_check CHECK (((unlinked_by IS NULL) OR (btrim(unlinked_by) <> ''::text)))
);
ALTER TABLE sokhach.zalo_link OWNER TO sokhach_owner;
CREATE UNIQUE INDEX zalo_link_active ON sokhach.zalo_link USING btree (conversation_id, customer_id) WHERE (unlinked_at IS NULL);
CREATE INDEX zalo_link_customer ON sokhach.zalo_link USING btree (customer_id) WHERE (unlinked_at IS NULL);
COMMENT ON TABLE sokhach.zalo_link IS 'ZALO-GROUP-01: group Zalo (id băm của gói web) gắn với sổ; nhiều–nhiều, bỏ gắn giữ vết; không tham gia tính tiền.';


-- ------------------------------------------------------------------------------------------------------------
-- VIEW (7)
-- ------------------------------------------------------------------------------------------------------------

CREATE VIEW sokhach.v_adjustment_current AS
 SELECT a.id,
    a.customer_id,
    COALESCE(t.debt_month, a.debt_month) AS debt_month,
    a.trip_id,
    a.legacy_row_id,
    a.amount_vnd,
    a.field,
    a.new_value_vnd,
    a.note,
    a.actor,
    a.at,
    a.created_by_event
   FROM ((sokhach.adjustment a
     LEFT JOIN sokhach.v_trip_current t ON ((t.id = a.trip_id)))
     LEFT JOIN LATERAL ( SELECT trip_price_rev.unit_price_vnd,
            trip_price_rev.other_fee_vnd
           FROM sokhach.trip_price_rev
          WHERE (trip_price_rev.trip_id = a.trip_id)
          ORDER BY trip_price_rev.id DESC
         LIMIT 1) p ON ((a.trip_id IS NOT NULL)))
  WHERE ((NOT a.fee_absorbed) AND ((a.trip_id IS NULL) OR ((NOT t.deleted) AND (t.status = 'confirmed'::text) AND ((p.unit_price_vnd IS NOT NULL) OR (((t.container IS NULL) OR (t.container = ''::text)) AND (p.other_fee_vnd IS NOT NULL))))) AND (a.reverses_adjustment_id IS NULL) AND (NOT (EXISTS ( SELECT 1
           FROM sokhach.adjustment r
          WHERE (r.reverses_adjustment_id = a.id)))));
ALTER VIEW sokhach.v_adjustment_current OWNER TO sokhach_owner;

CREATE VIEW sokhach.v_month_chain AS
 SELECT customer_id,
    debt_month,
    outstanding_vnd,
    (sum(outstanding_vnd) OVER (PARTITION BY customer_id ORDER BY debt_month ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW))::bigint AS end_of_month_vnd
   FROM sokhach.v_outstanding_month;
ALTER VIEW sokhach.v_month_chain OWNER TO sokhach_owner;
COMMENT ON VIEW sokhach.v_month_chain IS 'Chuỗi cộng dồn tháng cho get_ledger; chỉ cộng v_outstanding_month, không cộng legacy_row lần hai.';

CREATE VIEW sokhach.v_offset_outgoing AS
 SELECT id,
    source_customer_id AS customer_id,
    (date_trunc('month'::text, (date)::timestamp with time zone))::date AS debt_month,
    amount_vnd
   FROM sokhach.offset_pair
  WHERE (voided_by_event IS NULL);
ALTER VIEW sokhach.v_offset_outgoing OWNER TO sokhach_owner;

CREATE VIEW sokhach.v_outstanding_month AS
 WITH s AS (
         SELECT v_outstanding_month_raw.customer_id,
            v_outstanding_month_raw.debt_month,
            v_outstanding_month_raw.outstanding_vnd AS raw_vnd,
            sum(GREATEST((- v_outstanding_month_raw.outstanding_vnd), (0)::bigint)) OVER whole AS credit_vnd,
            sum(GREATEST(v_outstanding_month_raw.outstanding_vnd, (0)::bigint)) OVER whole AS debt_vnd,
            sum(GREATEST(v_outstanding_month_raw.outstanding_vnd, (0)::bigint)) OVER (PARTITION BY v_outstanding_month_raw.customer_id ORDER BY v_outstanding_month_raw.debt_month ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS debt_through_vnd,
            (v_outstanding_month_raw.debt_month = max(v_outstanding_month_raw.debt_month) OVER whole) AS last_month
           FROM sokhach.v_outstanding_month_raw
          WINDOW whole AS (PARTITION BY v_outstanding_month_raw.customer_id)
        )
 SELECT customer_id,
    debt_month,
    ((LEAST((GREATEST(raw_vnd, (0)::bigint))::numeric, GREATEST((debt_through_vnd - credit_vnd), (0)::numeric)) +
        CASE
            WHEN last_month THEN LEAST((debt_vnd - credit_vnd), (0)::numeric)
            ELSE (0)::numeric
        END))::bigint AS outstanding_vnd
   FROM s;
ALTER VIEW sokhach.v_outstanding_month OWNER TO sokhach_owner;
COMMENT ON VIEW sokhach.v_outstanding_month IS 'Chỉ khách và cutover active tham gia mọi vế tiền; draft/verified không hiệu lực. Lệnh ghi còn phải chặn NO_BASELINE dưới khóa khách. legacy_row không tham gia.';

CREATE VIEW sokhach.v_outstanding_month_raw AS
 WITH active_customer AS (
         SELECT cc.customer_id,
            cc.cutover_id
           FROM (sokhach.cutover_customer cc
             JOIN sokhach.cutover c ON ((c.id = cc.cutover_id)))
          WHERE ((cc.status = 'active'::text) AND (c.status = 'active'::text))
        ), latest_price AS (
         SELECT t.customer_id,
            t.debt_month,
                CASE
                    WHEN (p.unit_price_vnd IS NOT NULL) THEN (p.unit_price_vnd + COALESCE(p.other_fee_vnd, (0)::bigint))
                    WHEN ((t.container IS NULL) OR (t.container = ''::text)) THEN p.other_fee_vnd
                    ELSE NULL::bigint
                END AS amount_vnd
           FROM ((sokhach.v_trip_current t
             JOIN active_customer ac ON ((ac.customer_id = t.customer_id)))
             LEFT JOIN LATERAL ( SELECT trip_price_rev.unit_price_vnd,
                    trip_price_rev.other_fee_vnd
                   FROM sokhach.trip_price_rev
                  WHERE (trip_price_rev.trip_id = t.id)
                  ORDER BY trip_price_rev.id DESC
                 LIMIT 1) p ON (true))
          WHERE ((NOT t.deleted) AND (t.status = 'confirmed'::text))
        ), movements AS (
         SELECT o.customer_id,
            o.debt_month,
            o.amount_vnd
           FROM (sokhach.opening_balance o
             JOIN active_customer ac ON (((ac.customer_id = o.customer_id) AND (ac.cutover_id = o.cutover_id))))
        UNION ALL
         SELECT latest_price.customer_id,
            latest_price.debt_month,
            latest_price.amount_vnd
           FROM latest_price
          WHERE (latest_price.amount_vnd IS NOT NULL)
        UNION ALL
         SELECT a.customer_id,
            a.debt_month,
            a.amount_vnd
           FROM (sokhach.v_adjustment_current a
             JOIN active_customer ac ON ((ac.customer_id = a.customer_id)))
        UNION ALL
         SELECT o.customer_id,
            o.debt_month,
            o.amount_vnd
           FROM (sokhach.v_offset_outgoing o
             JOIN active_customer ac ON ((ac.customer_id = o.customer_id)))
        UNION ALL
         SELECT l.customer_id,
            l.debt_month,
            (- l.amount_vnd)
           FROM (sokhach.v_receipt_line_active l
             JOIN active_customer ac ON ((ac.customer_id = l.customer_id)))
        )
 SELECT customer_id,
    debt_month,
    (sum(amount_vnd))::bigint AS outstanding_vnd
   FROM movements
  GROUP BY customer_id, debt_month;
ALTER VIEW sokhach.v_outstanding_month_raw OWNER TO sokhach_owner;

CREATE VIEW sokhach.v_receipt_line_active AS
 SELECT l.id,
    l.receipt_id,
    l.customer_id,
    l.debt_month,
    l.kind,
    l.amount_vnd,
    l.created_by_event,
    r.pid,
    r.date,
    r.method
   FROM (sokhach.receipt_line l
     JOIN sokhach.receipt r ON (((r.id = l.receipt_id) AND (r.customer_id = l.customer_id))))
  WHERE ((l.superseded_by_event IS NULL) AND (r.voided_on IS NULL));
ALTER VIEW sokhach.v_receipt_line_active OWNER TO sokhach_owner;
COMMENT ON VIEW sokhach.v_receipt_line_active IS 'Dòng hiệu lực của phiếu chưa hủy; không cộng dòng cũ hoặc phiếu hủy.';

CREATE VIEW sokhach.v_trip_current AS
 SELECT t.id,
    t.customer_id,
    t.debt_month AS origin_month,
    COALESCE(r.debt_month, t.debt_month) AS debt_month,
        CASE
            WHEN (r.id IS NULL) THEN t.event_date
            ELSE r.event_date
        END AS event_date,
        CASE
            WHEN (r.id IS NULL) THEN t.container
            ELSE r.container
        END AS container,
        CASE
            WHEN (r.id IS NULL) THEN t.carrier
            ELSE r.carrier
        END AS carrier,
        CASE
            WHEN (r.id IS NULL) THEN t.origin
            ELSE r.origin
        END AS origin,
        CASE
            WHEN (r.id IS NULL) THEN t.destination
            ELSE r.destination
        END AS destination,
    t.booking,
    t.note,
    t.source_ref,
    COALESCE(r.status, t.status) AS status,
    COALESCE(r.deleted, false) AS deleted,
        CASE
            WHEN (r.id IS NULL) THEN t.shipper
            ELSE r.shipper
        END AS shipper
   FROM (sokhach.trip t
     LEFT JOIN LATERAL ( SELECT x.id,
            x.trip_id,
            x.customer_id,
            x.debt_month,
            x.event_date,
            x.container,
            x.carrier,
            x.shipper,
            x.origin,
            x.destination,
            x.status,
            x.deleted,
            x.created_by_event
           FROM sokhach.trip_info_rev x
          WHERE ((x.trip_id = t.id) AND (x.customer_id = t.customer_id))
          ORDER BY x.id DESC
         LIMIT 1) r ON (true));
ALTER VIEW sokhach.v_trip_current OWNER TO sokhach_owner;


-- ------------------------------------------------------------------------------------------------------------
-- HÀM (153), sắp theo tên + chữ ký
-- ------------------------------------------------------------------------------------------------------------

-- FUNCTION sokhach._actor()
CREATE OR REPLACE FUNCTION sokhach._actor()
 RETURNS text
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'pg_catalog', 'sokhach', 'pg_temp'
AS $function$
DECLARE v text := nullif(btrim(current_setting('sokhach.actor', true)), '');
BEGIN
    IF v IS NULL THEN RAISE EXCEPTION 'ACTOR_REQUIRED'; END IF;
    RETURN v;
END $function$;
ALTER FUNCTION sokhach._actor() OWNER TO sokhach_owner;
REVOKE ALL ON FUNCTION sokhach._actor() FROM PUBLIC;

-- FUNCTION sokhach._baseline(bigint)
CREATE OR REPLACE FUNCTION sokhach._baseline(p_customer bigint)
 RETURNS void
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'pg_catalog', 'sokhach', 'pg_temp'
AS $function$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM sokhach.cutover_customer cc
        JOIN sokhach.cutover c ON c.id = cc.cutover_id
        WHERE cc.customer_id = p_customer AND cc.status = 'active' AND c.status = 'active'
    ) THEN RAISE EXCEPTION 'NO_BASELINE'; END IF;
END $function$;
ALTER FUNCTION sokhach._baseline(bigint) OWNER TO sokhach_owner;
REVOKE ALL ON FUNCTION sokhach._baseline(bigint) FROM PUBLIC;

-- FUNCTION sokhach._begin_command(bigint,bigint,text,jsonb)
CREATE OR REPLACE FUNCTION sokhach._begin_command(p_customer bigint, p_version bigint, p_key text, p_payload jsonb)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'pg_catalog', 'sokhach', 'pg_temp'
AS $function$
DECLARE v_version bigint; v_saved sokhach.idempotency%ROWTYPE;
        v_hash text := encode(sha256(convert_to(p_payload::text, 'UTF8')), 'hex');
BEGIN
    PERFORM sokhach._actor();
    IF p_key IS NULL OR btrim(p_key) = '' OR left(p_key, 9) = chr(31) || 'cutover:'
       OR p_payload IS NULL THEN
        RAISE EXCEPTION 'INVALID_COMMAND';
    END IF;
    -- Audit SQL 23/11/2026 (F9): NO KEY UPDATE đủ chặn lệnh tiền khác trên sổ, không chặn dòng con (zalo_link, contact_mark…).
    SELECT version INTO v_version FROM sokhach.customer WHERE id = p_customer FOR NO KEY UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION 'CUSTOMER_NOT_FOUND'; END IF;
    SELECT * INTO v_saved FROM sokhach.idempotency WHERE customer_id = p_customer AND key = p_key;
    IF FOUND THEN
        IF v_saved.request_hash <> v_hash THEN RAISE EXCEPTION 'IDEMPOTENCY_CONFLICT'; END IF;
        RETURN v_saved.result;
    END IF;
    IF p_version IS DISTINCT FROM v_version THEN RAISE EXCEPTION 'STALE_LEDGER'; END IF;
    RETURN NULL;
END $function$;
ALTER FUNCTION sokhach._begin_command(bigint,bigint,text,jsonb) OWNER TO sokhach_owner;
REVOKE ALL ON FUNCTION sokhach._begin_command(bigint,bigint,text,jsonb) FROM PUBLIC;

-- FUNCTION sokhach._begin_cutover(bigint,text,jsonb)
CREATE OR REPLACE FUNCTION sokhach._begin_cutover(p_cutover bigint, p_key text, p_payload jsonb)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'pg_catalog', 'sokhach', 'pg_temp'
AS $function$
DECLARE v_customer bigint; v_saved sokhach.idempotency%ROWTYPE;
        v_storage_key text; v_hash text;
BEGIN
    PERFORM sokhach._actor();
    IF p_key IS NULL OR btrim(p_key)='' OR p_payload IS NULL THEN
        RAISE EXCEPTION 'INVALID_COMMAND'; END IF;
    PERFORM 1 FROM sokhach.cutover WHERE id=p_cutover FOR UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION 'CUTOVER_NOT_FOUND'; END IF;
    FOR v_customer IN SELECT customer_id FROM sokhach.cutover_customer
        WHERE cutover_id=p_cutover ORDER BY customer_id LOOP
        PERFORM 1 FROM sokhach.customer WHERE id=v_customer FOR UPDATE;
    END LOOP;
    SELECT min(customer_id) INTO v_customer FROM sokhach.cutover_customer
        WHERE cutover_id=p_cutover;
    IF v_customer IS NULL THEN RAISE EXCEPTION 'CUTOVER_SOURCE_INCOMPLETE'; END IF;
    v_storage_key := chr(31)||'cutover:'||p_cutover||':'||p_key;
    v_hash := encode(sha256(convert_to(p_payload::text,'UTF8')),'hex');
    SELECT * INTO v_saved FROM sokhach.idempotency
        WHERE customer_id=v_customer AND key=v_storage_key;
    IF FOUND THEN
        IF v_saved.request_hash<>v_hash THEN RAISE EXCEPTION 'IDEMPOTENCY_CONFLICT'; END IF;
        RETURN v_saved.result;
    END IF;
    RETURN NULL;
END $function$;
ALTER FUNCTION sokhach._begin_cutover(bigint,text,jsonb) OWNER TO sokhach_owner;
REVOKE ALL ON FUNCTION sokhach._begin_cutover(bigint,text,jsonb) FROM PUBLIC;

-- FUNCTION sokhach._begin_offset(bigint,bigint,bigint,bigint,text,jsonb)
CREATE OR REPLACE FUNCTION sokhach._begin_offset(p_target bigint, p_target_version bigint, p_source bigint, p_source_version bigint, p_key text, p_payload jsonb)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'pg_catalog', 'sokhach', 'pg_temp'
AS $function$
DECLARE v_saved sokhach.offset_command%ROWTYPE; v_count integer;
BEGIN
    PERFORM sokhach._actor();
    IF p_target=p_source THEN RAISE EXCEPTION 'OFFSET_SAME_BOOK'; END IF;
    IF p_key IS NULL OR btrim(p_key)='' OR p_source IS NULL OR p_target IS NULL
    THEN RAISE EXCEPTION 'INVALID_COMMAND'; END IF;
    PERFORM id FROM sokhach.customer WHERE id IN (p_source,p_target) ORDER BY id FOR NO KEY UPDATE;
    GET DIAGNOSTICS v_count=ROW_COUNT;
    IF v_count<>2 THEN RAISE EXCEPTION 'CUSTOMER_NOT_FOUND'; END IF;
    SELECT * INTO v_saved FROM sokhach.offset_command
      WHERE low_customer_id=least(p_source,p_target) AND high_customer_id=greatest(p_source,p_target)
        AND key=p_key;
    IF FOUND THEN
        IF v_saved.payload IS DISTINCT FROM p_payload THEN RAISE EXCEPTION 'IDEMPOTENCY_CONFLICT'; END IF;
        RETURN v_saved.result;
    END IF;
    IF p_source_version IS DISTINCT FROM (SELECT version FROM sokhach.customer WHERE id=p_source)
       OR p_target_version IS DISTINCT FROM (SELECT version FROM sokhach.customer WHERE id=p_target)
    THEN RAISE EXCEPTION 'STALE_LEDGER'; END IF;
    PERFORM sokhach._baseline(p_source);
    PERFORM sokhach._baseline(p_target);
    RETURN NULL;
END $function$;
ALTER FUNCTION sokhach._begin_offset(bigint,bigint,bigint,bigint,text,jsonb) OWNER TO sokhach_owner;
REVOKE ALL ON FUNCTION sokhach._begin_offset(bigint,bigint,bigint,bigint,text,jsonb) FROM PUBLIC;

-- FUNCTION sokhach._booking_key(text,text,date)
CREATE OR REPLACE FUNCTION sokhach._booking_key(p_booking text, p_container text, p_date date)
 RETURNS text
 LANGUAGE sql
 IMMUTABLE
 SET search_path TO 'pg_catalog', 'sokhach', 'pg_temp'
AS $function$
    SELECT CASE WHEN sokhach._normalize_key(p_booking) ~ '[[:alnum:]]'
        THEN sokhach._normalize_key(p_booking)
        ELSE 'ALT:' || sokhach._normalize_key(p_container) || ':' || coalesce(to_char(p_date,'YYYYMMDD'),'UNKNOWN') END
$function$;
ALTER FUNCTION sokhach._booking_key(text,text,date) OWNER TO sokhach_owner;
REVOKE ALL ON FUNCTION sokhach._booking_key(text,text,date) FROM PUBLIC;

-- FUNCTION sokhach._booking_names(bigint)
CREATE OR REPLACE FUNCTION sokhach._booking_names(p_customer bigint)
 RETURNS jsonb
 LANGUAGE sql
 STABLE SECURITY DEFINER
 SET search_path TO 'pg_catalog', 'sokhach', 'pg_temp'
AS $function$
    SELECT coalesce(jsonb_agg(b.name ORDER BY b.name COLLATE "C"), '[]'::jsonb) FROM sokhach.booking_name b WHERE b.customer_id = p_customer
$function$;
ALTER FUNCTION sokhach._booking_names(bigint) OWNER TO sokhach_owner;
REVOKE ALL ON FUNCTION sokhach._booking_names(bigint) FROM PUBLIC;

-- FUNCTION sokhach._cash_review_json(sokhach.cash_report_review)
CREATE OR REPLACE FUNCTION sokhach._cash_review_json(r sokhach.cash_report_review)
 RETURNS jsonb
 LANGUAGE sql
 STABLE SECURITY DEFINER
 SET search_path TO 'pg_catalog', 'sokhach', 'pg_temp'
AS $function$
 SELECT jsonb_build_object('id',r.id,'conversation_id',r.conversation_id,'message_id',r.message_id,'action',r.action,
   'target',CASE WHEN r.target_kind IS NULL THEN NULL ELSE jsonb_build_object('kind',r.target_kind,'id',r.target_id) END,
   'amount_vnd',r.amount_vnd::text,'before',r.before,'reason',r.reason,'request_id',r.request_id,'created_by',r.created_by,
   'created_at',r.created_at,'state',sokhach._cash_review_state(r.message_id,r.id+1))
$function$;
ALTER FUNCTION sokhach._cash_review_json(sokhach.cash_report_review) OWNER TO sokhach_owner;
REVOKE ALL ON FUNCTION sokhach._cash_review_json(sokhach.cash_report_review) FROM PUBLIC;

-- FUNCTION sokhach._cash_review_state(text,bigint)
CREATE OR REPLACE FUNCTION sokhach._cash_review_state(p_message text, p_before bigint)
 RETURNS jsonb
 LANGUAGE plpgsql
 STABLE SECURITY DEFINER
 SET search_path TO 'pg_catalog', 'sokhach', 'pg_temp'
AS $function$
DECLARE r sokhach.cash_report_review; v_last sokhach.cash_report_review; v_amount bigint; v_kind text; v_id bigint;
 v_decision text; v_reason text; v_count int := 0;
BEGIN
 FOR r IN SELECT * FROM sokhach.cash_report_review c WHERE c.message_id=p_message AND (p_before IS NULL OR c.id<p_before) ORDER BY c.id LOOP
   v_count:=v_count+1; v_last:=r;
   IF r.action='amount' THEN v_amount:=r.amount_vnd; v_decision:=NULL; v_reason:=NULL;
   ELSIF r.action='target' THEN v_kind:=r.target_kind; v_id:=r.target_id; v_decision:=NULL; v_reason:=NULL;
   ELSE v_decision:=r.action; v_reason:=r.reason; END IF;
 END LOOP;
 IF v_count=0 THEN RETURN '{}'::jsonb; END IF;
 RETURN jsonb_build_object('amount_vnd',v_amount::text,
   'target',CASE WHEN v_kind IS NULL THEN NULL ELSE jsonb_build_object('kind',v_kind,'id',v_id) END,
   'decision',v_decision,'reason',v_reason,'reviews',v_count,'last_action',v_last.action,'last_by',v_last.created_by,'last_at',v_last.created_at);
END $function$;
ALTER FUNCTION sokhach._cash_review_state(text,bigint) OWNER TO sokhach_owner;
REVOKE ALL ON FUNCTION sokhach._cash_review_state(text,bigint) FROM PUBLIC;

-- FUNCTION sokhach._catalog_manifest()
CREATE OR REPLACE FUNCTION sokhach._catalog_manifest()
 RETURNS jsonb
 LANGUAGE sql
 STABLE
 SET search_path TO 'pg_catalog', 'sokhach', 'pg_temp'
AS $function$
SELECT jsonb_build_object(
    'level', sokhach.schema_level(),
    'functions', (SELECT coalesce(jsonb_object_agg(p.oid::regprocedure::text,
                    md5(CASE WHEN p.prokind = 'a' THEN p.proname::text ELSE pg_get_functiondef(p.oid) END)), '{}'::jsonb)
                  FROM pg_proc p WHERE p.pronamespace = 'sokhach'::regnamespace),
    'views', (SELECT coalesce(jsonb_object_agg(c.relname, md5(sokhach._catalog_view_text(pg_get_viewdef(c.oid)))), '{}'::jsonb)
              FROM pg_class c WHERE c.relnamespace = 'sokhach'::regnamespace AND c.relkind IN ('v', 'm')),
    'triggers', (SELECT coalesce(jsonb_object_agg(c.relname || '.' || t.tgname,
                   md5(pg_get_triggerdef(t.oid)) || ':' || t.tgenabled::text), '{}'::jsonb)
                 FROM pg_trigger t JOIN pg_class c ON c.oid = t.tgrelid
                 WHERE c.relnamespace = 'sokhach'::regnamespace AND NOT t.tgisinternal),
    'indexes', (SELECT coalesce(jsonb_object_agg(ic.relname, md5(pg_get_indexdef(i.indexrelid))), '{}'::jsonb)
                FROM pg_index i JOIN pg_class c ON c.oid = i.indrelid JOIN pg_class ic ON ic.oid = i.indexrelid
                WHERE c.relnamespace = 'sokhach'::regnamespace),
    'constraints', (SELECT coalesce(jsonb_object_agg(c.relname || '.' || k.conname, md5(pg_get_constraintdef(k.oid))), '{}'::jsonb)
                    FROM pg_constraint k JOIN pg_class c ON c.oid = k.conrelid
                    WHERE k.connamespace = 'sokhach'::regnamespace AND k.contype <> 'n'))
$function$;
ALTER FUNCTION sokhach._catalog_manifest() OWNER TO sokhach_owner;
REVOKE ALL ON FUNCTION sokhach._catalog_manifest() FROM PUBLIC;

-- FUNCTION sokhach._catalog_view_text(text)
CREATE OR REPLACE FUNCTION sokhach._catalog_view_text(p_def text)
 RETURNS text
 LANGUAGE plpgsql
 IMMUTABLE
 SET search_path TO 'pg_catalog', 'sokhach', 'pg_temp'
AS $function$
DECLARE v_list text; v_out text := p_def;
BEGIN
    FOR v_list IN SELECT m[1] FROM regexp_matches(p_def, '(SELECT (?:x\.\w+,\s+)+x\.\w+)', 'g') m LOOP
        v_out := replace(v_out, v_list, 'SELECT ' || (SELECT string_agg(c[1], ',' ORDER BY c[1] COLLATE "C")
                                                      FROM regexp_matches(substr(v_list, 8), '(x\.\w+)', 'g') c));
    END LOOP;
    RETURN v_out;
END $function$;
ALTER FUNCTION sokhach._catalog_view_text(text) OWNER TO sokhach_owner;
REVOKE ALL ON FUNCTION sokhach._catalog_view_text(text) FROM PUBLIC;

-- FUNCTION sokhach._change_fee_type(text,text,bigint,text,text)
CREATE OR REPLACE FUNCTION sokhach._change_fee_type(p_key text, p_command text, p_id bigint, p_value text, p_kind text)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'pg_catalog', 'sokhach', 'pg_temp'
AS $function$
DECLARE v_payload jsonb:=jsonb_build_object('command',p_command,'id',p_id,'value',p_value,'kind',p_kind);
 v_saved sokhach.fee_type_audit%ROWTYPE; v_old sokhach.fee_type%ROWTYPE; v_new sokhach.fee_type%ROWTYPE;
BEGIN
 PERFORM sokhach._actor();
 IF p_key IS NULL OR btrim(p_key)='' OR length(p_key)>128 THEN RAISE EXCEPTION 'INVALID_COMMAND'; END IF;
 -- Serializes both key claims and name uniqueness across add/rename/update.
 PERFORM pg_advisory_xact_lock(771029);
 SELECT * INTO v_saved FROM sokhach.fee_type_audit WHERE idempotency_key=p_key;
 IF FOUND THEN
   IF v_saved.payload IS DISTINCT FROM v_payload THEN RAISE EXCEPTION 'IDEMPOTENCY_CONFLICT'; END IF;
   RETURN v_saved.after_value;
 END IF;
 IF p_command<>'add_fee_type' THEN
   SELECT * INTO v_old FROM sokhach.fee_type WHERE id=p_id FOR UPDATE;
   IF NOT FOUND THEN RAISE EXCEPTION 'FEE_TYPE_INACTIVE'; END IF;
   IF v_old.system_key IS NOT NULL THEN RAISE EXCEPTION 'FEE_TYPE_SYSTEM'; END IF;
 END IF;
 IF p_command IN ('add_fee_type','rename_fee_type') AND
   (p_value IS NULL OR btrim(p_value)='' OR length(p_value)>200) THEN RAISE EXCEPTION 'INVALID_COMMAND'; END IF;
 IF p_command IN ('add_fee_type','set_fee_type_kind') AND
   (p_kind IS NULL OR p_kind NOT IN ('service','pass_through')) THEN RAISE EXCEPTION 'INVALID_COMMAND'; END IF;
 CASE p_command
 WHEN 'add_fee_type' THEN
   INSERT INTO sokhach.fee_type(name,kind,sign,sort) SELECT btrim(p_value),p_kind,'positive',coalesce(max(sort),0)+1
     FROM sokhach.fee_type RETURNING * INTO v_new;
 WHEN 'rename_fee_type' THEN UPDATE sokhach.fee_type SET name=btrim(p_value) WHERE id=p_id RETURNING * INTO v_new;
 WHEN 'set_fee_type_kind' THEN UPDATE sokhach.fee_type SET kind=p_kind WHERE id=p_id RETURNING * INTO v_new;
 WHEN 'set_fee_type_active' THEN
   IF p_value IS NULL OR p_value NOT IN ('true','false') THEN RAISE EXCEPTION 'INVALID_COMMAND'; END IF;
   UPDATE sokhach.fee_type SET active=p_value::boolean WHERE id=p_id RETURNING * INTO v_new;
 ELSE RAISE EXCEPTION 'INVALID_COMMAND'; END CASE;
 INSERT INTO sokhach.fee_type_audit(fee_type_id,actor,payload,before_value,after_value,idempotency_key)
 VALUES(v_new.id,sokhach._actor(),v_payload,coalesce(to_jsonb(v_old),'{}'),to_jsonb(v_new),p_key);
 RETURN to_jsonb(v_new);
EXCEPTION WHEN unique_violation THEN RAISE EXCEPTION 'FEE_TYPE_DUPLICATE';
END $function$;
ALTER FUNCTION sokhach._change_fee_type(text,text,bigint,text,text) OWNER TO sokhach_owner;
REVOKE ALL ON FUNCTION sokhach._change_fee_type(text,text,bigint,text,text) FROM PUBLIC;

-- FUNCTION sokhach._change_legacy(bigint,bigint,text,bigint,text,text,boolean)
CREATE OR REPLACE FUNCTION sokhach._change_legacy(customer_id bigint, expected_version bigint, idempotency_key text, legacy_row_id bigint, field text, value text, p_delete boolean)
 RETURNS jsonb
 LANGUAGE sql
 SECURITY DEFINER
 SET search_path TO 'pg_catalog', 'sokhach', 'pg_temp'
AS $function$
 SELECT sokhach._change_legacy(customer_id,expected_version,idempotency_key,legacy_row_id,field,value,p_delete,NULL)
$function$;
ALTER FUNCTION sokhach._change_legacy(bigint,bigint,text,bigint,text,text,boolean) OWNER TO sokhach_owner;
REVOKE ALL ON FUNCTION sokhach._change_legacy(bigint,bigint,text,bigint,text,text,boolean) FROM PUBLIC;

-- FUNCTION sokhach._change_legacy(bigint,bigint,text,bigint,text,text,boolean,bigint)
CREATE OR REPLACE FUNCTION sokhach._change_legacy(customer_id bigint, expected_version bigint, idempotency_key text, legacy_row_id bigint, field text, value text, p_delete boolean, p_fee_event bigint)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'pg_catalog', 'sokhach', 'pg_temp'
AS $function$
DECLARE v_payload jsonb:=jsonb_build_object('command',CASE WHEN p_delete THEN 'delete_legacy_trip' ELSE 'edit_legacy_trip' END,
      'legacy_row_id',legacy_row_id,'field',field,'value',value);
    v_retry jsonb; l sokhach.legacy_row%ROWTYPE; v_old jsonb; v_new jsonb; v_value text;
    v_month date; v_old_month date; v_count bigint; v_old_count bigint; v_event bigint; v_changes jsonb;
    v_fee bigint; v_cutover bigint; v_trip sokhach.v_trip_current%ROWTYPE; v_review jsonb := '[]'; v_review_reason text;
BEGIN
    IF p_fee_event IS NULL THEN
    v_retry:=sokhach._begin_command(customer_id,expected_version,idempotency_key,v_payload);
    IF v_retry IS NOT NULL THEN RETURN v_retry; END IF;
    END IF;
    PERFORM sokhach._baseline(customer_id);
    SELECT l0.* INTO l FROM sokhach.legacy_row l0 JOIN sokhach.cutover_customer cc USING(customer_id,cutover_id)
      JOIN sokhach.cutover c ON c.id=cc.cutover_id WHERE l0.id=legacy_row_id AND l0.customer_id=_change_legacy.customer_id AND cc.status='active' AND c.status='active';
    IF NOT FOUND THEN RAISE EXCEPTION 'LEGACY_NOT_FOUND'; END IF;
    -- Khoản thu sổ gốc chỉ xóa được, không sửa ô (XOA-THU-GOC-01).
    IF l.kind<>'trip' AND NOT p_delete THEN RAISE EXCEPTION 'LEGACY_NOT_TRIP'; END IF;
    v_old:=sokhach._legacy_current(l.id)||jsonb_build_object('kind',l.kind); v_new:=v_old;
    IF l.kind='trip' THEN
      SELECT sum(amount_vnd)::bigint INTO v_fee FROM sokhach.trip_fee_line
        WHERE trip_fee_line.legacy_row_id=l.id AND voided_by_event IS NULL;
      v_old:=v_old||jsonb_build_object('other_fee_vnd',v_fee::text,'fee_lines',sokhach._fee_lines(NULL,l.id)); v_new:=v_old;
    END IF;
    IF (v_old->>'deleted')::boolean THEN RAISE EXCEPTION 'LEGACY_NOT_FOUND'; END IF;
    v_old_month:=(v_old->>'month')::date; v_month:=v_old_month; v_old_count:=(v_old->>'counted_vnd')::bigint;
    -- KHOA-CHU-01 (1/11/2026): sửa một trong bốn ô chữ mô tả không cần tháng mở; xóa, tiền, ngày, container vẫn theo khóa.
    IF p_delete OR p_fee_event IS NOT NULL OR field IS NULL OR field NOT IN ('carrier','shipper','origin','destination') THEN
      PERFORM sokhach._month_open(customer_id,v_old_month,clock_timestamp());
    END IF;
    IF NOT p_delete AND field='other_fee_vnd' AND v_old->>'unit_price_vnd' IS NULL
    THEN RAISE EXCEPTION 'LEGACY_NO_UNIT_PRICE'; END IF;
    IF p_delete THEN v_count:=0; v_new:=v_new||jsonb_build_object('deleted',true);
    ELSE
      IF field IS NULL OR field NOT IN ('container','carrier','shipper','origin','destination','event_date','unit_price_vnd','other_fee_vnd') THEN RAISE EXCEPTION 'INVALID_FIELD'; END IF;
      v_value:=nullif(btrim(value),'');
      IF field IN ('unit_price_vnd','other_fee_vnd') THEN
        IF v_value IS NOT NULL AND v_value !~ (CASE WHEN field='other_fee_vnd' THEN '^-?[0-9]+$' ELSE '^[0-9]+$' END) THEN RAISE EXCEPTION 'INVALID_VND'; END IF;
        v_value:=((v_value)::bigint)::text;
        IF p_fee_event IS NULL AND field='other_fee_vnd' AND v_value='0' THEN v_value:=NULL; END IF;
      ELSIF field='event_date' THEN v_value:=sokhach._trip_date(value)::text; v_month:=date_trunc('month',v_value::date)::date;
      ELSIF field='container' THEN v_value:=nullif(sokhach._normalize_key(value),''); END IF;
      IF p_fee_event IS NULL AND field='other_fee_vnd' AND EXISTS (SELECT 1 FROM sokhach.trip_fee_line fl JOIN sokhach.fee_type ft ON ft.id=fl.fee_type_id
          WHERE fl.legacy_row_id=l.id AND fl.voided_by_event IS NULL
            AND coalesce(ft.system_key,'') NOT IN ('other','discount','initial'))
      THEN RAISE EXCEPTION 'FEE_LINES_TYPED'; END IF;
      IF p_fee_event IS NULL AND v_old->>field IS NOT DISTINCT FROM v_value THEN RAISE EXCEPTION 'NO_CHANGE'; END IF;
      v_new:=v_new||jsonb_build_object(field,v_value);
      -- Text edits preserve the Sheet counted amount, including flagged source differences.
      v_count:=v_old_count;
      IF field IN ('unit_price_vnd','other_fee_vnd') THEN
        v_count:=CASE WHEN v_new->>'unit_price_vnd' IS NULL THEN 0 ELSE
          (v_new->>'unit_price_vnd')::bigint+coalesce((v_new->>'other_fee_vnd')::bigint,0) END;
      END IF;
    END IF;
    IF v_month<>v_old_month THEN PERFORM sokhach._month_open(customer_id,v_month,clock_timestamp()); END IF;
    v_new:=v_new||jsonb_build_object('month',v_month,'debt_month',v_month,'counted_vnd',v_count::text,'field',field,'value',v_new->field);
    -- Audit SQL 23/11/2026 (F8): sửa container/ngày của dòng sổ gốc thành trùng một chuyến web đang tính (cùng sổ, cùng container;
    -- dòng không ngày cùng tháng nợ, hoặc có ngày cách tối đa 3 ngày) thì chuyến đó vào CHỜ KIỂM, như chiều ngược lại ở edit_trip_info.
    -- Chỉ xét chuyến chưa có lý do trùng nào trước lần sửa này (cùng hàm _trip_dup_reason): chuyến người đã duyệt giữ không bị đẩy lại.
    IF NOT p_delete AND p_fee_event IS NULL AND l.kind='trip' AND field IN ('container','event_date')
       AND nullif(v_new->>'container','') IS NOT NULL THEN
      SELECT cc.cutover_id INTO v_cutover FROM sokhach.cutover_customer cc JOIN sokhach.cutover c ON c.id=cc.cutover_id
        WHERE cc.customer_id=_change_legacy.customer_id AND cc.status='active' AND c.status='active';
      v_review_reason:=CASE WHEN v_new->>'event_date' IS NULL THEN 'BASELINE_UNDATED_MONTH' ELSE 'BASELINE_DATE_WINDOW' END;
      FOR v_trip IN SELECT t.* FROM sokhach.v_trip_current t
          WHERE t.customer_id=_change_legacy.customer_id AND NOT t.deleted AND t.status='confirmed'
            AND sokhach._normalize_key(t.container)=sokhach._normalize_key(v_new->>'container')
            AND CASE WHEN v_new->>'event_date' IS NULL THEN t.debt_month=v_month
                     ELSE abs(t.event_date-(v_new->>'event_date')::date)<=3 END
          ORDER BY t.id LOOP
        IF sokhach._trip_dup_reason(v_trip.customer_id,v_cutover,sokhach._normalize_key(v_trip.container),
             sokhach._booking_key(v_trip.booking,v_trip.container,v_trip.event_date),v_trip.event_date,v_trip.id,NULL) IS NULL THEN
          PERFORM sokhach._month_open(v_trip.customer_id,v_trip.debt_month,clock_timestamp());
          v_review:=v_review||jsonb_build_array(v_trip.id);
        END IF;
      END LOOP;
    END IF;
    IF p_fee_event IS NULL THEN
    INSERT INTO sokhach.event(customer_id,kind,actor,"before","after",idempotency_key)
      VALUES(customer_id,CASE WHEN p_delete THEN 'legacy_delete' ELSE 'legacy_edit' END,sokhach._actor(),
        jsonb_build_object('legacy',v_old||jsonb_build_object('field',field,'value',v_old->field)),jsonb_build_object('legacy',v_new)
          ||CASE WHEN jsonb_array_length(v_review)>0 THEN jsonb_build_object('review_trips',v_review,'review_reason',v_review_reason)
                 ELSE '{}'::jsonb END,idempotency_key) RETURNING id INTO v_event;
    ELSE v_event:=p_fee_event; END IF;
    IF jsonb_array_length(v_review)>0 THEN
      INSERT INTO sokhach.trip_info_rev(trip_id,customer_id,debt_month,event_date,container,carrier,shipper,origin,destination,status,created_by_event)
      SELECT t.id,t.customer_id,t.debt_month,t.event_date,t.container,t.carrier,t.shipper,t.origin,t.destination,'pending_review',v_event
        FROM sokhach.v_trip_current t WHERE t.id IN (SELECT (x#>>'{}')::bigint FROM jsonb_array_elements(v_review) x);
    END IF;
    IF p_fee_event IS NULL AND field='other_fee_vnd' AND NOT p_delete THEN
      UPDATE sokhach.trip_fee_line SET voided_by_event=v_event
        WHERE trip_fee_line.legacy_row_id=l.id AND voided_by_event IS NULL;
      IF v_value IS NOT NULL THEN
        INSERT INTO sokhach.trip_fee_line(customer_id,legacy_row_id,fee_type_id,amount_vnd,created_by_event)
        SELECT customer_id,l.id,id,v_value::bigint,v_event FROM sokhach.fee_type
        WHERE system_key=CASE WHEN v_value::bigint<0 THEN 'discount' ELSE 'other' END;
      END IF;
    END IF;
    INSERT INTO sokhach.legacy_trip_rev(legacy_row_id,customer_id,debt_month,event_date,container,carrier,shipper,origin,destination,unit_price_vnd,other_fee_vnd,deleted,counted_vnd,created_by_event)
      VALUES(l.id,customer_id,v_month,(v_new->>'event_date')::date,v_new->>'container',v_new->>'carrier',v_new->>'shipper',v_new->>'origin',v_new->>'destination',
        (v_new->>'unit_price_vnd')::bigint,(v_new->>'other_fee_vnd')::bigint,p_delete,v_count,v_event);
    -- Khoản thu đã trừ nợ: xóa thì cộng lại đúng số đó vào tháng của dòng.
    INSERT INTO sokhach.adjustment(customer_id,debt_month,legacy_row_id,amount_vnd,actor,created_by_event)
      SELECT customer_id,m,l.id,CASE WHEN l.kind='receipt' THEN -delta ELSE delta END,sokhach._actor(),v_event FROM (
        SELECT v_old_month AS m,CASE WHEN v_month=v_old_month THEN v_count-v_old_count ELSE -v_old_count END AS delta
        UNION ALL SELECT v_month,v_count WHERE v_month<>v_old_month) d WHERE delta<>0;
    IF p_fee_event IS NOT NULL THEN RETURN v_new; END IF;
    v_changes:=sokhach.reallocate(customer_id,idempotency_key);
    RETURN sokhach._finish_command(customer_id,idempotency_key,v_payload,jsonb_build_object('legacy_row_id',l.id,'deleted',p_delete,
      'review_trips',v_review,'reallocated',v_changes));
EXCEPTION WHEN numeric_value_out_of_range THEN
    IF p_fee_event IS NOT NULL THEN RAISE EXCEPTION 'FEE_AMOUNT_INVALID'; END IF;
    RAISE EXCEPTION 'INVALID_VND';
END $function$;
ALTER FUNCTION sokhach._change_legacy(bigint,bigint,text,bigint,text,text,boolean,bigint) OWNER TO sokhach_owner;
REVOKE ALL ON FUNCTION sokhach._change_legacy(bigint,bigint,text,bigint,text,text,boolean,bigint) FROM PUBLIC;

-- FUNCTION sokhach._change_offset(bigint,bigint,bigint,text,bigint,date,text,boolean)
CREATE OR REPLACE FUNCTION sokhach._change_offset(customer_id bigint, expected_version bigint, other_version bigint, idempotency_key text, offset_pair_id bigint, new_date date, reason text, is_void boolean)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'pg_catalog', 'sokhach', 'pg_temp'
AS $function$
DECLARE v_pair sokhach.offset_pair%ROWTYPE; v_payload jsonb; v_retry jsonb;
    v_target_version bigint; v_source_version bigint; v_target jsonb; v_changes jsonb;
    v_event bigint; v_pid text; v_before jsonb; v_after jsonb; v_internal_key text;
BEGIN
    SELECT * INTO v_pair FROM sokhach.offset_pair WHERE id=offset_pair_id;
    IF NOT FOUND OR customer_id NOT IN (v_pair.source_customer_id,v_pair.target_customer_id)
    THEN RAISE EXCEPTION 'OFFSET_NOT_FOUND'; END IF;
    v_source_version:=CASE WHEN customer_id=v_pair.source_customer_id THEN expected_version ELSE other_version END;
    v_target_version:=CASE WHEN customer_id=v_pair.target_customer_id THEN expected_version ELSE other_version END;
    v_payload:=jsonb_build_object('command',CASE WHEN is_void THEN 'void_offset' ELSE 'edit_offset_date' END,
        'offset_pair_id',offset_pair_id,'date',new_date,'reason',reason);
    v_retry:=sokhach._begin_offset(v_pair.target_customer_id,v_target_version,
        v_pair.source_customer_id,v_source_version,idempotency_key,v_payload);
    IF v_retry IS NOT NULL THEN RETURN v_retry; END IF;
    -- Refresh after waiting for customer locks, never lock pair before customers.
    SELECT * INTO v_pair FROM sokhach.offset_pair WHERE id=offset_pair_id;
    IF v_pair.voided_by_event IS NOT NULL THEN RAISE EXCEPTION 'OFFSET_ALREADY_VOID'; END IF;
    IF is_void THEN
        IF reason IS NULL OR btrim(reason)='' THEN RAISE EXCEPTION 'VOID_REASON_REQUIRED'; END IF;
    ELSE
        IF new_date IS NULL THEN RAISE EXCEPTION 'INVALID_DATE'; END IF;
        IF new_date>(clock_timestamp() AT TIME ZONE 'Asia/Ho_Chi_Minh')::date
        THEN RAISE EXCEPTION 'FUTURE_DATE'; END IF;
        IF new_date=v_pair.date THEN RAISE EXCEPTION 'NO_CHANGE'; END IF;
    END IF;
    SELECT pid INTO v_pid FROM sokhach.receipt WHERE id=v_pair.target_receipt_id;
    v_internal_key:=chr(31)||'offset:'||v_pair.id||':'||idempotency_key;
    IF is_void THEN
        v_target:=sokhach._void_receipt(v_pair.target_customer_id,v_target_version,v_internal_key,v_pid,reason);
    ELSE
        v_target:=sokhach._edit_receipt_meta(v_pair.target_customer_id,v_target_version,
            v_internal_key,v_pid,new_date,'CẤN TRỪ');
    END IF;
    v_before:=jsonb_build_object('receipt',v_pair.source_pid,'offset_pair_id',v_pair.id,
        'date',v_pair.date,'amount_vnd',(-v_pair.amount_vnd)::text,
        'counterparty_customer_id',v_pair.target_customer_id,
        'counterparty_name',(SELECT name FROM sokhach.customer WHERE id=v_pair.target_customer_id));
    v_after:=v_before || CASE WHEN is_void THEN jsonb_build_object('void_reason',btrim(reason))
        ELSE jsonb_build_object('date',new_date) END;
    INSERT INTO sokhach.event(customer_id,kind,actor,"before","after",idempotency_key)
    VALUES(v_pair.source_customer_id,CASE WHEN is_void THEN 'void' ELSE 'receipt_edit' END,
        sokhach._actor(),v_before,v_after,idempotency_key) RETURNING id INTO v_event;
    IF is_void THEN
        UPDATE sokhach.offset_pair SET void_reason=btrim(reason),voided_by_event=v_event WHERE id=v_pair.id;
    ELSE
        UPDATE sokhach.offset_pair SET date=new_date,changed_by_event=v_event WHERE id=v_pair.id;
    END IF;
    v_changes:=sokhach.reallocate(v_pair.source_customer_id,idempotency_key);
    RETURN sokhach._finish_offset(v_pair,idempotency_key,v_payload,jsonb_build_object(
        'target_receipt',v_target,'source_reallocated',v_changes));
EXCEPTION WHEN numeric_value_out_of_range THEN RAISE EXCEPTION 'INVALID_VND';
END $function$;
ALTER FUNCTION sokhach._change_offset(bigint,bigint,bigint,text,bigint,date,text,boolean) OWNER TO sokhach_owner;
REVOKE ALL ON FUNCTION sokhach._change_offset(bigint,bigint,bigint,text,bigint,date,text,boolean) FROM PUBLIC;

-- FUNCTION sokhach._change_trip_fees(bigint,bigint,text,text,jsonb,bigint,bigint,text,bigint)
CREATE OR REPLACE FUNCTION sokhach._change_trip_fees(p_customer bigint, p_version bigint, p_key text, p_command text, p_targets jsonb, p_type bigint, p_amount bigint, p_note text, p_line bigint)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'pg_catalog', 'sokhach', 'pg_temp'
AS $function$
DECLARE v_payload jsonb:=jsonb_build_object('command',p_command,'targets',p_targets,'fee_type_id',p_type,
 'amount_vnd',p_amount::text,'note',p_note,'fee_line_id',p_line);
 v_retry jsonb; v_before jsonb:='[]'; v_after jsonb:='[]'; v_target jsonb; v_state jsonb;
 v_old sokhach.trip_fee_line%ROWTYPE; v_type sokhach.fee_type%ROWTYPE;
 v_event bigint; v_total bigint; v_changes jsonb;
BEGIN
 BEGIN v_retry:=sokhach._begin_command(p_customer,p_version,p_key,v_payload);
 EXCEPTION WHEN raise_exception THEN
   IF SQLERRM='STALE_LEDGER' THEN RAISE EXCEPTION 'VERSION_CONFLICT'; ELSE RAISE; END IF;
 END;
 IF v_retry IS NOT NULL THEN RETURN v_retry; END IF;
 PERFORM sokhach._baseline(p_customer);
 IF p_command NOT IN ('add_trip_fees','set_trip_fee_type','replace_trip_fee','void_trip_fee')
   OR p_command IS NULL THEN RAISE EXCEPTION 'INVALID_COMMAND'; END IF;
 IF p_command IN ('replace_trip_fee','void_trip_fee') THEN
   SELECT * INTO v_old FROM sokhach.trip_fee_line WHERE id=p_line AND customer_id=p_customer
     AND voided_by_event IS NULL FOR UPDATE;
   IF NOT FOUND THEN RAISE EXCEPTION 'FEE_LINE_NOT_FOUND'; END IF;
   p_targets:=jsonb_build_array(CASE WHEN v_old.trip_id IS NOT NULL
     THEN jsonb_build_object('trip_id',v_old.trip_id) ELSE jsonb_build_object('legacy_row_id',v_old.legacy_row_id) END);
 END IF;
 IF jsonb_typeof(p_targets) IS DISTINCT FROM 'array' THEN RAISE EXCEPTION 'INVALID_TRIPS'; END IF;
 IF jsonb_array_length(p_targets)<1 OR
   (p_command<>'add_trip_fees' AND jsonb_array_length(p_targets)<>1) OR
   (SELECT count(*)<>count(DISTINCT x) FROM jsonb_array_elements(p_targets) x)
 THEN RAISE EXCEPTION 'INVALID_TRIPS'; END IF;
 IF p_command<>'void_trip_fee' THEN
   SELECT * INTO v_type FROM sokhach.fee_type WHERE id=p_type FOR SHARE;
   IF NOT FOUND OR NOT v_type.active THEN RAISE EXCEPTION 'FEE_TYPE_INACTIVE'; END IF;
   IF v_type.system_key='initial' AND NOT (p_command='replace_trip_fee' AND v_old.fee_type_id IS NOT DISTINCT FROM p_type)
   THEN RAISE EXCEPTION 'FEE_TYPE_SYSTEM'; END IF;
   IF p_amount=0 OR (p_amount IS NULL AND p_command<>'set_trip_fee_type') THEN RAISE EXCEPTION 'FEE_AMOUNT_INVALID'; END IF;
   IF (v_type.sign='positive' AND p_amount<0) OR (v_type.sign='negative' AND p_amount>0)
   THEN RAISE EXCEPTION 'FEE_SIGN_INVALID'; END IF;
 END IF;
 IF length(p_note)>2000 THEN RAISE EXCEPTION 'INVALID_COMMAND'; END IF;
 FOR v_target IN SELECT x FROM jsonb_array_elements(p_targets) x LOOP
   v_state:=sokhach._fee_target(p_customer,v_target);
   v_before:=v_before||jsonb_build_array(v_state);
   SELECT coalesce(jsonb_agg(x),'[]') INTO v_retry FROM jsonb_array_elements(v_state->'fee_lines') x
     WHERE NOT (p_command='set_trip_fee_type' AND (x->>'fee_type_id')::bigint=p_type)
       AND NOT (p_command IN ('replace_trip_fee','void_trip_fee') AND (x->>'id')::bigint=p_line);
   IF p_command<>'void_trip_fee' AND p_amount IS NOT NULL THEN
     v_retry:=v_retry||jsonb_build_array(jsonb_build_object('fee_type_id',p_type,'amount_vnd',p_amount::text,'note',p_note));
   END IF;
   v_state:=v_state||jsonb_build_object('fee_lines',v_retry);
   IF v_target ? 'legacy_row_id' THEN
     SELECT sum((x->>'amount_vnd')::bigint)::bigint INTO v_total FROM jsonb_array_elements(v_retry) x;
     v_state:=v_state||jsonb_build_object('counted_vnd',CASE WHEN sokhach._legacy_current((v_target->>'legacy_row_id')::bigint)->>'unit_price_vnd' IS NULL THEN '0'
       ELSE (((sokhach._legacy_current((v_target->>'legacy_row_id')::bigint)->>'unit_price_vnd')::bigint)+coalesce(v_total,0))::text END);
   END IF;
   v_after:=v_after||jsonb_build_array(v_state);
 END LOOP;
 INSERT INTO sokhach.event(customer_id,kind,actor,"before","after",idempotency_key)
 VALUES(p_customer,p_command,sokhach._actor(),jsonb_build_object('targets',v_before,'batch_count',jsonb_array_length(p_targets)),
   jsonb_build_object('targets',v_after,'batch_count',jsonb_array_length(p_targets)),p_key) RETURNING id INTO v_event;
 v_after:='[]';
 FOR v_target IN SELECT x FROM jsonb_array_elements(p_targets) x LOOP
   IF p_command IN ('replace_trip_fee','void_trip_fee') THEN
     UPDATE sokhach.trip_fee_line SET voided_by_event=v_event WHERE id=p_line;
   ELSIF p_command='set_trip_fee_type' THEN
     UPDATE sokhach.trip_fee_line SET voided_by_event=v_event WHERE customer_id=p_customer AND fee_type_id=p_type
       AND (trip_id=(v_target->>'trip_id')::bigint OR legacy_row_id=(v_target->>'legacy_row_id')::bigint)
       AND voided_by_event IS NULL;
   END IF;
   IF p_command<>'void_trip_fee' AND p_amount IS NOT NULL THEN
     INSERT INTO sokhach.trip_fee_line(customer_id,trip_id,legacy_row_id,fee_type_id,amount_vnd,note,created_by_event)
     VALUES(p_customer,(v_target->>'trip_id')::bigint,(v_target->>'legacy_row_id')::bigint,p_type,p_amount,p_note,v_event);
   END IF;
   IF v_target ? 'trip_id' THEN
     PERFORM sokhach._sync_trip_fee((v_target->>'trip_id')::bigint,v_event);
   ELSE
     SELECT sum(amount_vnd)::bigint INTO v_total FROM sokhach.trip_fee_line
       WHERE legacy_row_id=(v_target->>'legacy_row_id')::bigint AND voided_by_event IS NULL;
     PERFORM sokhach._change_legacy(p_customer,p_version,p_key,(v_target->>'legacy_row_id')::bigint,
       'other_fee_vnd',v_total::text,false,v_event);
   END IF;
   v_state:=sokhach._fee_target(p_customer,v_target);
   v_after:=v_after||jsonb_build_array(v_state);
 END LOOP;
 v_changes:=sokhach.reallocate(p_customer,p_key);
 RETURN sokhach._finish_command(p_customer,p_key,v_payload,jsonb_build_object('event_id',v_event,'targets',v_after,'reallocated',v_changes));
EXCEPTION WHEN numeric_value_out_of_range THEN RAISE EXCEPTION 'FEE_AMOUNT_INVALID';
END $function$;
ALTER FUNCTION sokhach._change_trip_fees(bigint,bigint,text,text,jsonb,bigint,bigint,text,bigint) OWNER TO sokhach_owner;
REVOKE ALL ON FUNCTION sokhach._change_trip_fees(bigint,bigint,text,text,jsonb,bigint,bigint,text,bigint) FROM PUBLIC;

-- FUNCTION sokhach._check_allocations(bigint)
CREATE OR REPLACE FUNCTION sokhach._check_allocations(p_customer bigint)
 RETURNS void
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'pg_catalog', 'sokhach', 'pg_temp'
AS $function$
BEGIN
    IF EXISTS (
        SELECT 1 FROM sokhach.receipt r LEFT JOIN sokhach.receipt_line l
          ON l.receipt_id = r.id AND l.customer_id = r.customer_id
             AND l.superseded_by_event IS NULL
        WHERE r.customer_id = p_customer
        GROUP BY r.id, r.amount_vnd, r.voided_on
        HAVING (r.voided_on IS NULL AND (count(l.id) = 0 OR sum(l.amount_vnd) <> r.amount_vnd))
            OR (r.voided_on IS NOT NULL AND count(l.id) <> 0)
    ) THEN RAISE EXCEPTION 'ALLOCATION_INVARIANT'; END IF;
    IF EXISTS (
        SELECT 1 FROM sokhach.receipt_line l JOIN sokhach.receipt r ON r.id = l.receipt_id
        WHERE l.customer_id = p_customer AND l.kind = 'advance'
          AND l.superseded_by_event IS NULL AND r.voided_on IS NULL
          AND l.debt_month <> coalesce((SELECT max(debt_month) FROM (
              SELECT debt_month FROM sokhach.opening_balance WHERE customer_id = p_customer
              UNION ALL SELECT debt_month FROM sokhach.v_trip_current WHERE NOT deleted AND customer_id = p_customer AND status='confirmed'
              UNION ALL SELECT debt_month FROM sokhach.v_adjustment_current WHERE customer_id = p_customer
              UNION ALL SELECT debt_month FROM sokhach.v_offset_outgoing WHERE customer_id = p_customer
          ) m),(SELECT max(x.debt_month) FROM sokhach.receipt_line x JOIN sokhach.receipt r0 ON r0.id=x.receipt_id
            WHERE r0.customer_id=p_customer AND r0.voided_on IS NULL AND x.superseded_by_event IS NULL))
    ) THEN RAISE EXCEPTION 'ADVANCE_MONTH_INVARIANT'; END IF;
    IF EXISTS (
        SELECT 1 FROM sokhach.receipt_line l
        JOIN sokhach.receipt r ON (r.id, r.customer_id) = (l.receipt_id, l.customer_id)
        JOIN sokhach.event e ON (e.id, e.customer_id) = (l.created_by_event, l.customer_id)
        WHERE l.customer_id = p_customer AND (
            e.kind NOT IN ('receipt', 'reallocation') OR
            e."after"->>'receipt' IS DISTINCT FROM r.id::text OR
            (e."after"->'allocations' @> jsonb_build_array(jsonb_build_object(
                'id',l.id,'month',l.debt_month,'kind',l.kind,'amount_vnd',l.amount_vnd::text))) IS NOT TRUE OR
            (l.superseded_by_event IS NOT NULL AND NOT EXISTS (
                SELECT 1 FROM sokhach.event s WHERE (s.id, s.customer_id) =
                  (l.superseded_by_event, l.customer_id) AND s.kind IN ('reallocation', 'void')
                  AND s."before"->>'receipt' = r.id::text
                  AND s."before"->'allocations' @> jsonb_build_array(jsonb_build_object(
                    'id',l.id,'month',l.debt_month,'kind',l.kind,'amount_vnd',l.amount_vnd::text))
            ))
        )
    ) THEN RAISE EXCEPTION 'ALLOCATION_EVENT_INVARIANT'; END IF;
END $function$;
ALTER FUNCTION sokhach._check_allocations(bigint) OWNER TO sokhach_owner;
REVOKE ALL ON FUNCTION sokhach._check_allocations(bigint) FROM PUBLIC;

-- FUNCTION sokhach._check_cutover(bigint)
CREATE OR REPLACE FUNCTION sokhach._check_cutover(p_cutover bigint)
 RETURNS void
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'pg_catalog', 'sokhach', 'pg_temp'
AS $function$
DECLARE v_customer bigint; v_total numeric;
BEGIN
    FOR v_customer IN SELECT customer_id FROM sokhach.cutover_customer
        WHERE cutover_id=p_cutover ORDER BY customer_id LOOP
        IF (SELECT status FROM sokhach.cutover_customer
            WHERE customer_id=v_customer AND cutover_id=p_cutover)<>'verified'
        THEN RAISE EXCEPTION 'CUTOVER_CUSTOMERS_NOT_VERIFIED'; END IF;
        PERFORM sokhach._check_cutover_customer(v_customer,p_cutover);
    END LOOP;
    SELECT sum(expected_control_total_vnd)::numeric INTO v_total
      FROM sokhach.cutover_customer WHERE cutover_id=p_cutover;
    IF v_total IS NULL OR v_total IS DISTINCT FROM
       (SELECT control_total_vnd FROM sokhach.cutover WHERE id=p_cutover) THEN
        RAISE EXCEPTION 'CUTOVER_TOTAL_MISMATCH';
    END IF;
END $function$;
ALTER FUNCTION sokhach._check_cutover(bigint) OWNER TO sokhach_owner;
REVOKE ALL ON FUNCTION sokhach._check_cutover(bigint) FROM PUBLIC;

-- FUNCTION sokhach._check_cutover_customer(bigint,bigint)
CREATE OR REPLACE FUNCTION sokhach._check_cutover_customer(p_customer bigint, p_cutover bigint)
 RETURNS void
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'pg_catalog', 'sokhach', 'pg_temp'
AS $function$
DECLARE v_cc sokhach.cutover_customer%ROWTYPE; v_bad boolean;
        v_open_count bigint; v_check_count bigint; v_total numeric;
        v_anchor numeric; v_initial numeric; v_balances numeric[] := ARRAY[]::numeric[];
        v_months date[] := ARRAY[]::date[]; v_row record; v_due numeric;
        v_left numeric; v_take numeric; v_i integer; v_n integer;
BEGIN
    SELECT * INTO v_cc FROM sokhach.cutover_customer
        WHERE customer_id=p_customer AND cutover_id=p_cutover;
    IF NOT FOUND THEN RAISE EXCEPTION 'CUTOVER_CUSTOMER_NOT_FOUND'; END IF;
    SELECT count(*),sum(amount_vnd)::numeric INTO v_open_count,v_total
        FROM sokhach.opening_balance
        WHERE customer_id=p_customer AND cutover_id=p_cutover;
    IF coalesce(v_total,0) <> v_cc.expected_control_total_vnd THEN
        RAISE EXCEPTION 'CUTOVER_CUSTOMER_TOTAL_MISMATCH';
    END IF;
    SELECT count(*) INTO v_check_count FROM sokhach.cutover_month_check
        WHERE customer_id=p_customer AND cutover_id=p_cutover;
    IF v_check_count=0 OR v_check_count<>v_open_count
       OR v_cc.source_rows<>v_cc.imported_rows+v_cc.quarantined_rows+v_cc.skipped_with_reason_rows THEN
        RAISE EXCEPTION 'CUTOVER_SOURCE_INCOMPLETE';
    END IF;
    SELECT EXISTS (
      SELECT 1 FROM sokhach.cutover_month_check m
      FULL JOIN sokhach.opening_balance o USING(customer_id,cutover_id,debt_month)
      WHERE coalesce(m.customer_id,o.customer_id)=p_customer
        AND coalesce(m.cutover_id,o.cutover_id)=p_cutover
        AND (m.customer_id IS NULL OR o.id IS NULL
         OR m.opening_anchor_vnd IS NULL
         OR m.bucket_vnd IS NULL OR m.standard_bucket_vnd IS NULL
         OR m.source_charge_vnd IS NULL OR m.source_receipt_vnd IS NULL
         OR m.source_cumulative_vnd IS NULL
         OR nullif(btrim(m.standard_source_ref),'') IS NULL
         OR m.standard_source_sha256 IS NULL OR m.source_evidence_sha256 IS NULL
         OR m.bucket_vnd IS DISTINCT FROM m.standard_bucket_vnd
         OR m.bucket_vnd IS DISTINCT FROM o.amount_vnd)
    ) INTO v_bad;
    IF v_bad THEN RAISE EXCEPTION 'CUTOVER_MONTH_MISMATCH'; END IF;
    -- Source charges/receipts determine FIFO independently of imported buckets.
    FOR v_row IN SELECT * FROM sokhach.cutover_month_check
        WHERE customer_id=p_customer AND cutover_id=p_cutover ORDER BY debt_month LOOP
        IF v_initial IS NULL THEN
            v_initial := v_row.opening_anchor_vnd;
            v_anchor := v_initial;
        END IF;
        IF v_row.opening_anchor_vnd::numeric <> v_initial
        THEN RAISE EXCEPTION 'CUTOVER_ANCHOR_MISMATCH'; END IF;
        v_due := v_row.source_charge_vnd::numeric;
        IF cardinality(v_months)=0 THEN v_due := v_due+v_anchor; END IF;
        v_months := array_append(v_months,v_row.debt_month);
        v_balances := array_append(v_balances,v_due);
        v_n := cardinality(v_balances);
        v_left := v_row.source_receipt_vnd;
        FOR v_i IN 1..v_n LOOP
            v_take := least(greatest(v_balances[v_i],0),v_left);
            v_balances[v_i] := v_balances[v_i]-v_take;
            v_left := v_left-v_take;
        END LOOP;
        IF v_left>0 THEN v_balances[v_n] := v_balances[v_n]-v_left; END IF;
        v_anchor := v_anchor+v_row.source_charge_vnd-v_row.source_receipt_vnd;
        IF v_anchor<>v_row.source_cumulative_vnd::numeric
        THEN RAISE EXCEPTION 'CUTOVER_ANCHOR_MISMATCH'; END IF;
    END LOOP;
    FOR v_i IN 1..cardinality(v_months) LOOP
        IF v_balances[v_i] IS DISTINCT FROM (SELECT standard_bucket_vnd::numeric
            FROM sokhach.cutover_month_check WHERE customer_id=p_customer
              AND cutover_id=p_cutover AND debt_month=v_months[v_i])
        THEN RAISE EXCEPTION 'CUTOVER_FIFO_MISMATCH'; END IF;
    END LOOP;
    IF v_anchor IS DISTINCT FROM v_cc.expected_control_total_vnd::numeric
       OR (SELECT sum(x)::numeric FROM unnest(v_balances) x) IS DISTINCT FROM v_anchor
    THEN RAISE EXCEPTION 'CUTOVER_ANCHOR_MISMATCH'; END IF;
END $function$;
ALTER FUNCTION sokhach._check_cutover_customer(bigint,bigint) OWNER TO sokhach_owner;
REVOKE ALL ON FUNCTION sokhach._check_cutover_customer(bigint,bigint) FROM PUBLIC;

-- FUNCTION sokhach._compat_trip_fee(bigint,bigint,bigint,bigint)
CREATE OR REPLACE FUNCTION sokhach._compat_trip_fee(p_customer bigint, p_trip bigint, p_fee bigint, p_event bigint)
 RETURNS void
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'pg_catalog', 'sokhach', 'pg_temp'
AS $function$
DECLARE v_type bigint; v_old bigint; v_count bigint; v_existing_type bigint;
BEGIN
    SELECT sum(amount_vnd)::bigint,count(*),min(fee_type_id) INTO v_old,v_count,v_existing_type FROM sokhach.trip_fee_line
      WHERE trip_id=p_trip AND voided_by_event IS NULL;
    IF v_old IS NOT DISTINCT FROM nullif(p_fee,0) THEN
        PERFORM sokhach._sync_trip_fee(p_trip,p_event);
        RETURN;
    END IF;
    IF EXISTS (SELECT 1 FROM sokhach.trip_fee_line l JOIN sokhach.fee_type f ON f.id=l.fee_type_id
        WHERE l.trip_id=p_trip AND l.voided_by_event IS NULL
          AND coalesce(f.system_key,'') NOT IN ('other','discount','initial'))
    THEN RAISE EXCEPTION 'FEE_LINES_TYPED'; END IF;
    IF p_fee IS NOT NULL AND p_fee<>0 THEN
      SELECT id INTO v_type FROM sokhach.fee_type
        WHERE system_key=CASE WHEN p_fee<0 THEN 'discount' ELSE 'other' END;
    END IF;
    IF v_old IS DISTINCT FROM nullif(p_fee,0)
       OR v_count<>(CASE WHEN p_fee IS NULL OR p_fee=0 THEN 0 ELSE 1 END)
       OR (v_count=1 AND v_existing_type IS DISTINCT FROM v_type) THEN
      UPDATE sokhach.trip_fee_line SET voided_by_event=p_event
        WHERE trip_id=p_trip AND voided_by_event IS NULL;
      IF p_fee IS NOT NULL AND p_fee<>0 THEN
        INSERT INTO sokhach.trip_fee_line(customer_id,trip_id,fee_type_id,amount_vnd,created_by_event)
          VALUES(p_customer,p_trip,v_type,p_fee,p_event);
      END IF;
    END IF;
    PERFORM sokhach._sync_trip_fee(p_trip,p_event);
END $function$;
ALTER FUNCTION sokhach._compat_trip_fee(bigint,bigint,bigint,bigint) OWNER TO sokhach_owner;
REVOKE ALL ON FUNCTION sokhach._compat_trip_fee(bigint,bigint,bigint,bigint) FROM PUBLIC;

-- FUNCTION sokhach._edit_receipt_meta(bigint,bigint,text,text,date,text)
CREATE OR REPLACE FUNCTION sokhach._edit_receipt_meta(customer_id bigint, expected_version bigint, idempotency_key text, pid text, date date, method text)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'pg_catalog', 'sokhach', 'pg_temp'
AS $function$
DECLARE v_payload jsonb := jsonb_build_object('command','_edit_receipt_meta','pid',pid,
        'date',date,'method',method);
        v_retry jsonb; v_receipt sokhach.receipt%ROWTYPE; v_date date; v_method text;
        v_event bigint; v_changes jsonb := '[]'::jsonb; v_before jsonb;
BEGIN
    v_retry := sokhach._begin_command(customer_id,expected_version,idempotency_key,v_payload);
    IF v_retry IS NOT NULL THEN RETURN v_retry; END IF;
    PERFORM sokhach._baseline(customer_id);
    SELECT * INTO v_receipt FROM sokhach.receipt
     WHERE receipt.customer_id=_edit_receipt_meta.customer_id AND receipt.pid=_edit_receipt_meta.pid;
    IF NOT FOUND OR v_receipt.voided_on IS NOT NULL THEN RAISE EXCEPTION 'RECEIPT_NOT_FOUND'; END IF;
    v_date := coalesce(date,v_receipt.date);
    IF v_date > (clock_timestamp() AT TIME ZONE 'Asia/Ho_Chi_Minh')::date
       THEN RAISE EXCEPTION 'FUTURE_RECEIPT_DATE'; END IF;
    v_method := coalesce(method,v_receipt.method);
    IF v_method NOT IN ('THU TIỀN','CẤN TRỪ','ỨNG TRƯỚC','KHÁC')
       THEN RAISE EXCEPTION 'INVALID_METHOD'; END IF;
    IF (v_date,v_method) IS NOT DISTINCT FROM (v_receipt.date,v_receipt.method)
       THEN RAISE EXCEPTION 'NO_CHANGE'; END IF;
    v_before := sokhach._lines(v_receipt.id);
    INSERT INTO sokhach.event(customer_id,kind,actor,"before","after",idempotency_key)
    VALUES (customer_id,'receipt_edit',sokhach._actor(),
        jsonb_build_object('receipt',v_receipt.id,'pid',pid,'date',v_receipt.date,
            'method',v_receipt.method,'allocations',v_before),
        jsonb_build_object('receipt',v_receipt.id,'pid',pid,'date',v_date,
            'method',v_method,'allocations',v_before),idempotency_key)
    RETURNING id INTO v_event;
    UPDATE sokhach.receipt SET date=v_date,method=v_method,meta_changed_by_event=v_event
    WHERE id=v_receipt.id;
    IF v_date IS DISTINCT FROM v_receipt.date THEN
        v_changes := sokhach.reallocate(customer_id,idempotency_key);
    ELSE
        PERFORM sokhach._check_allocations(customer_id);
    END IF;
    RETURN sokhach._finish_command(customer_id,idempotency_key,v_payload,
        jsonb_build_object('receipt_id',v_receipt.id,'pid',pid,'reallocated',v_changes));
END $function$;
ALTER FUNCTION sokhach._edit_receipt_meta(bigint,bigint,text,text,date,text) OWNER TO sokhach_owner;
REVOKE ALL ON FUNCTION sokhach._edit_receipt_meta(bigint,bigint,text,text,date,text) FROM PUBLIC;

-- FUNCTION sokhach._fee_cache_check()
CREATE OR REPLACE FUNCTION sokhach._fee_cache_check()
 RETURNS trigger
 LANGUAGE plpgsql
 SET search_path TO 'pg_catalog', 'sokhach', 'pg_temp'
AS $function$
DECLARE v_trip bigint; v_cache bigint; v_total bigint; v_count bigint;
BEGIN IF TG_OP='DELETE' THEN v_trip:=OLD.trip_id; ELSE v_trip:=NEW.trip_id; END IF; IF v_trip IS NULL THEN IF TG_OP='DELETE' THEN RETURN OLD; ELSE RETURN NEW; END IF; END IF;
 SELECT p.other_fee_vnd INTO v_cache FROM sokhach.trip_price_rev p WHERE p.trip_id=v_trip ORDER BY p.id DESC LIMIT 1;
 SELECT count(*),sum(amount_vnd) INTO v_count,v_total FROM sokhach.trip_fee_line WHERE trip_id=v_trip AND voided_by_event IS NULL;
 IF (v_count=0 AND v_cache IS NOT NULL) OR (v_count>0 AND v_cache IS DISTINCT FROM v_total) THEN RAISE EXCEPTION 'FEE_CACHE_MISMATCH'; END IF;
 IF TG_OP='DELETE' THEN RETURN OLD; ELSE RETURN NEW; END IF; END $function$;
ALTER FUNCTION sokhach._fee_cache_check() OWNER TO sokhach_owner;
REVOKE ALL ON FUNCTION sokhach._fee_cache_check() FROM PUBLIC;

-- FUNCTION sokhach._fee_columns(bigint)
CREATE OR REPLACE FUNCTION sokhach._fee_columns(p_customer bigint)
 RETURNS jsonb
 LANGUAGE sql
 STABLE
 SET search_path TO 'pg_catalog', 'sokhach', 'pg_temp'
AS $function$
 SELECT coalesce(jsonb_agg(jsonb_build_object('fee_type_id',fee_type_id,'position',position) ORDER BY position),'[]')
 FROM sokhach.book_fee_column WHERE customer_id=p_customer
$function$;
ALTER FUNCTION sokhach._fee_columns(bigint) OWNER TO sokhach_owner;
REVOKE ALL ON FUNCTION sokhach._fee_columns(bigint) FROM PUBLIC;

-- FUNCTION sokhach._fee_lines(bigint,bigint)
CREATE OR REPLACE FUNCTION sokhach._fee_lines(p_trip bigint, p_legacy bigint)
 RETURNS jsonb
 LANGUAGE sql
 STABLE
 SET search_path TO 'pg_catalog', 'sokhach', 'pg_temp'
AS $function$
 SELECT coalesce(jsonb_agg(jsonb_build_object('id',id,'fee_type_id',fee_type_id,
   'amount_vnd',amount_vnd::text,'note',note) ORDER BY id),'[]'::jsonb)
 FROM sokhach.trip_fee_line WHERE voided_by_event IS NULL
   AND (trip_id=p_trip OR legacy_row_id=p_legacy)
$function$;
ALTER FUNCTION sokhach._fee_lines(bigint,bigint) OWNER TO sokhach_owner;
REVOKE ALL ON FUNCTION sokhach._fee_lines(bigint,bigint) FROM PUBLIC;

-- FUNCTION sokhach._fee_target(bigint,jsonb)
CREATE OR REPLACE FUNCTION sokhach._fee_target(p_customer bigint, p_target jsonb)
 RETURNS jsonb
 LANGUAGE plpgsql
 SET search_path TO 'pg_catalog', 'sokhach', 'pg_temp'
AS $function$
DECLARE t sokhach.v_trip_current%ROWTYPE; l jsonb; v_id bigint; v_month date;
BEGIN
 IF jsonb_typeof(p_target) IS DISTINCT FROM 'object' THEN
   RAISE EXCEPTION 'INVALID_TRIP'; END IF;
 IF (SELECT count(*) FROM jsonb_object_keys(p_target))<>1 OR NOT (p_target ? 'trip_id' OR p_target ? 'legacy_row_id') THEN RAISE EXCEPTION 'INVALID_TRIP'; END IF;
 IF p_target ? 'trip_id' THEN
   SELECT * INTO t FROM sokhach.v_trip_current WHERE id=(p_target->>'trip_id')::bigint
     AND customer_id=p_customer AND NOT deleted;
   IF NOT FOUND THEN RAISE EXCEPTION 'TRIP_NOT_FOUND'; END IF;
   IF t.status<>'confirmed' THEN RAISE EXCEPTION 'TRIP_PENDING_REVIEW'; END IF;
   v_id:=t.id; v_month:=t.debt_month;
 ELSE
   SELECT sokhach._legacy_current(lr.id) INTO l FROM sokhach.legacy_row lr
     JOIN sokhach.cutover_customer cc USING(customer_id,cutover_id)
     JOIN sokhach.cutover c ON c.id=cc.cutover_id
     WHERE lr.id=(p_target->>'legacy_row_id')::bigint AND lr.customer_id=p_customer
       AND lr.kind='trip' AND cc.status='active' AND c.status='active';
   IF l IS NULL OR (l->>'deleted')::boolean THEN RAISE EXCEPTION 'LEGACY_NOT_FOUND'; END IF;
   v_id:=(p_target->>'legacy_row_id')::bigint; v_month:=(l->>'month')::date;
 END IF;
 PERFORM sokhach._month_open(p_customer,v_month,clock_timestamp());
 IF l IS NOT NULL AND l->>'unit_price_vnd' IS NULL THEN RAISE EXCEPTION 'LEGACY_NO_UNIT_PRICE'; END IF;
 RETURN p_target||jsonb_build_object('fee_lines',sokhach._fee_lines(t.id,CASE WHEN l IS NOT NULL THEN v_id END),
   'counted_vnd',l->>'counted_vnd');
EXCEPTION WHEN invalid_text_representation OR numeric_value_out_of_range THEN RAISE EXCEPTION 'INVALID_TRIP';
END $function$;
ALTER FUNCTION sokhach._fee_target(bigint,jsonb) OWNER TO sokhach_owner;
REVOKE ALL ON FUNCTION sokhach._fee_target(bigint,jsonb) FROM PUBLIC;

-- FUNCTION sokhach._finish_command(bigint,text,jsonb,jsonb)
CREATE OR REPLACE FUNCTION sokhach._finish_command(p_customer bigint, p_key text, p_payload jsonb, p_result jsonb)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'pg_catalog', 'sokhach', 'pg_temp'
AS $function$
DECLARE v_version bigint; v_result jsonb;
BEGIN
    UPDATE sokhach.customer SET version = version + 1 WHERE id = p_customer
        RETURNING version INTO v_version;
    v_result := p_result || jsonb_build_object('version', v_version);
    INSERT INTO sokhach.idempotency(customer_id, key, request_hash, result)
    VALUES (p_customer, p_key, encode(sha256(convert_to(p_payload::text, 'UTF8')), 'hex'), v_result);
    RETURN v_result;
END $function$;
ALTER FUNCTION sokhach._finish_command(bigint,text,jsonb,jsonb) OWNER TO sokhach_owner;
REVOKE ALL ON FUNCTION sokhach._finish_command(bigint,text,jsonb,jsonb) FROM PUBLIC;

-- FUNCTION sokhach._finish_cutover(bigint,text,jsonb,jsonb)
CREATE OR REPLACE FUNCTION sokhach._finish_cutover(p_cutover bigint, p_key text, p_payload jsonb, p_result jsonb)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'pg_catalog', 'sokhach', 'pg_temp'
AS $function$
DECLARE v_customer bigint;
BEGIN
    SELECT min(customer_id) INTO v_customer FROM sokhach.cutover_customer
        WHERE cutover_id=p_cutover;
    INSERT INTO sokhach.idempotency(customer_id,key,request_hash,result)
    VALUES(v_customer,chr(31)||'cutover:'||p_cutover||':'||p_key,
        encode(sha256(convert_to(p_payload::text,'UTF8')),'hex'),p_result);
    RETURN p_result;
END $function$;
ALTER FUNCTION sokhach._finish_cutover(bigint,text,jsonb,jsonb) OWNER TO sokhach_owner;
REVOKE ALL ON FUNCTION sokhach._finish_cutover(bigint,text,jsonb,jsonb) FROM PUBLIC;

-- FUNCTION sokhach._finish_offset(sokhach.offset_pair,text,jsonb,jsonb)
CREATE OR REPLACE FUNCTION sokhach._finish_offset(p_pair sokhach.offset_pair, p_key text, p_payload jsonb, p_result jsonb)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'pg_catalog', 'sokhach', 'pg_temp'
AS $function$
DECLARE v_source_version bigint; v_result jsonb;
BEGIN
    UPDATE sokhach.customer SET version=version+1 WHERE id=p_pair.source_customer_id
        RETURNING version INTO v_source_version;
    v_result:=p_result || jsonb_build_object('offset_pair_id',p_pair.id,
        'source_customer_id',p_pair.source_customer_id,'target_customer_id',p_pair.target_customer_id,
        'source_version',v_source_version,
        'target_version',(SELECT version FROM sokhach.customer WHERE id=p_pair.target_customer_id),
        'source_pid',p_pair.source_pid,
        'target_pid',(SELECT pid FROM sokhach.receipt WHERE id=p_pair.target_receipt_id));
    INSERT INTO sokhach.offset_command(low_customer_id,high_customer_id,key,payload,result)
    VALUES (least(p_pair.source_customer_id,p_pair.target_customer_id),
        greatest(p_pair.source_customer_id,p_pair.target_customer_id),p_key,p_payload,v_result);
    RETURN v_result;
END $function$;
ALTER FUNCTION sokhach._finish_offset(sokhach.offset_pair,text,jsonb,jsonb) OWNER TO sokhach_owner;
REVOKE ALL ON FUNCTION sokhach._finish_offset(sokhach.offset_pair,text,jsonb,jsonb) FROM PUBLIC;

-- FUNCTION sokhach._guard_fee_line()
CREATE OR REPLACE FUNCTION sokhach._guard_fee_line()
 RETURNS trigger
 LANGUAGE plpgsql
 SET search_path TO 'pg_catalog', 'sokhach', 'pg_temp'
AS $function$
DECLARE t sokhach.fee_type%ROWTYPE;
BEGIN
 IF TG_OP='DELETE' THEN RAISE EXCEPTION 'FEE_LINE_IMMUTABLE'; END IF;
 IF TG_OP='UPDATE' THEN
   IF OLD.voided_by_event IS NOT NULL OR NEW.voided_by_event IS NULL
      OR (to_jsonb(NEW)-'voided_by_event') IS DISTINCT FROM (to_jsonb(OLD)-'voided_by_event')
   THEN RAISE EXCEPTION 'FEE_LINE_IMMUTABLE'; END IF;
   RETURN NEW;
 END IF;
 SELECT * INTO t FROM sokhach.fee_type WHERE id=NEW.fee_type_id;
 IF NOT FOUND OR NOT t.active THEN RAISE EXCEPTION 'FEE_TYPE_INACTIVE'; END IF;
 IF NEW.amount_vnd IS NULL OR NEW.amount_vnd=0 THEN RAISE EXCEPTION 'FEE_AMOUNT_INVALID'; END IF;
 IF t.system_key='initial' AND NOT EXISTS (
   SELECT 1 FROM sokhach.event e JOIN sokhach.trip_fee_line old_line ON old_line.voided_by_event=e.id
   WHERE e.id=NEW.created_by_event AND e.kind='replace_trip_fee' AND e.customer_id=NEW.customer_id
     AND old_line.fee_type_id=NEW.fee_type_id AND old_line.trip_id IS NOT DISTINCT FROM NEW.trip_id
     AND old_line.legacy_row_id IS NOT DISTINCT FROM NEW.legacy_row_id
     AND e."before"->'targets'->0->'fee_lines' @> jsonb_build_array(jsonb_build_object('id',old_line.id))
     AND NOT EXISTS(SELECT 1 FROM sokhach.trip_fee_line n WHERE n.created_by_event=e.id))
 THEN RAISE EXCEPTION 'FEE_TYPE_SYSTEM'; END IF;
 IF (t.sign='positive' AND NEW.amount_vnd<0) OR (t.sign='negative' AND NEW.amount_vnd>0)
 THEN RAISE EXCEPTION 'FEE_SIGN_INVALID'; END IF;
 RETURN NEW;
END $function$;
ALTER FUNCTION sokhach._guard_fee_line() OWNER TO sokhach_owner;
REVOKE ALL ON FUNCTION sokhach._guard_fee_line() FROM PUBLIC;

-- FUNCTION sokhach._guard_receipt_image()
CREATE OR REPLACE FUNCTION sokhach._guard_receipt_image()
 RETURNS trigger
 LANGUAGE plpgsql
 SET search_path TO 'pg_catalog', 'sokhach', 'pg_temp'
AS $function$
BEGIN
 IF TG_OP='DELETE' THEN RAISE EXCEPTION 'RECEIPT_IMAGE_IMMUTABLE'; END IF;
 IF OLD.removed_by_event IS NOT NULL OR NEW.removed_by_event IS NULL
    OR (to_jsonb(NEW)-'removed_by_event'-'removed_reason') IS DISTINCT FROM (to_jsonb(OLD)-'removed_by_event'-'removed_reason')
 THEN RAISE EXCEPTION 'RECEIPT_IMAGE_IMMUTABLE'; END IF;
 RETURN NEW;
END $function$;
ALTER FUNCTION sokhach._guard_receipt_image() OWNER TO sokhach_owner;
REVOKE ALL ON FUNCTION sokhach._guard_receipt_image() FROM PUBLIC;

-- FUNCTION sokhach._ledger_events(bigint)
CREATE OR REPLACE FUNCTION sokhach._ledger_events(p_customer bigint)
 RETURNS jsonb
 LANGUAGE sql
 STABLE
 SET search_path TO 'pg_catalog', 'sokhach', 'pg_temp'
AS $function$
    SELECT coalesce(jsonb_agg(jsonb_build_object('id',id,'kind',kind,'actor',actor,
        'label',CASE kind WHEN 'fee_migration' THEN 'Tách phụ phí' WHEN 'trip_edit' THEN 'Sửa chuyến' WHEN 'trip_delete' THEN 'Xóa chuyến'
            WHEN 'legacy_edit' THEN 'Sửa dòng sổ gốc' WHEN 'legacy_delete' THEN 'Xóa dòng sổ gốc' ELSE kind END,
        -- Audit SQL 23/11/2026 (F4): chỉ event có khóa `receipt` mới có thể là cấn trừ; event khác bỏ qua hai câu con.
        'counterparty_customer_id',CASE WHEN event."after" ? 'receipt' THEN (SELECT CASE WHEN p.source_customer_id=event.customer_id
            THEN p.target_customer_id ELSE p.source_customer_id END FROM sokhach.offset_pair p
            WHERE (p.source_customer_id=event.customer_id AND p.source_pid=event."after"->>'receipt')
               OR (p.target_customer_id=event.customer_id AND p.target_receipt_id::text=event."after"->>'receipt')) END,
        'counterparty_name',CASE WHEN event."after" ? 'receipt' THEN (SELECT c.name FROM sokhach.offset_pair p JOIN sokhach.customer c
            ON c.id=CASE WHEN p.source_customer_id=event.customer_id THEN p.target_customer_id
                ELSE p.source_customer_id END
            WHERE (p.source_customer_id=event.customer_id AND p.source_pid=event."after"->>'receipt')
               OR (p.target_customer_id=event.customer_id AND p.target_receipt_id::text=event."after"->>'receipt')) END,
        'at',at,'before',CASE WHEN kind='price_edit' THEN "before" || jsonb_build_object(
            'price',"before"->'price' || jsonb_build_object(
                'unit_price_vnd',"before"->'price'->>'unit_price_vnd',
                'other_fee_vnd',"before"->'price'->>'other_fee_vnd')) ELSE "before" END,
        'after',CASE WHEN kind='price_edit' THEN "after" || jsonb_build_object(
            'price',"after"->'price' || jsonb_build_object(
                'unit_price_vnd',"after"->'price'->>'unit_price_vnd',
                'other_fee_vnd',"after"->'price'->>'other_fee_vnd')) ELSE "after" END)
        ORDER BY at DESC,id DESC),'[]'::jsonb)
 FROM sokhach.event WHERE event.customer_id=p_customer
$function$;
ALTER FUNCTION sokhach._ledger_events(bigint) OWNER TO sokhach_owner;
REVOKE ALL ON FUNCTION sokhach._ledger_events(bigint) FROM PUBLIC;

-- FUNCTION sokhach._legacy_current(bigint)
CREATE OR REPLACE FUNCTION sokhach._legacy_current(p_id bigint)
 RETURNS jsonb
 LANGUAGE plpgsql
 STABLE
 SET search_path TO 'pg_catalog', 'sokhach', 'pg_temp'
AS $function$
DECLARE l sokhach.legacy_row%ROWTYPE; r sokhach.legacy_trip_rev%ROWTYPE;
    v_date date; v_unit bigint; v_fee bigint;
BEGIN
    SELECT * INTO l FROM sokhach.legacy_row WHERE id=p_id;
    SELECT * INTO r FROM sokhach.legacy_trip_rev WHERE legacy_row_id=p_id ORDER BY id DESC LIMIT 1;
    IF FOUND THEN RETURN to_jsonb(r)||jsonb_build_object('month',r.debt_month,'unit_price_vnd',r.unit_price_vnd::text,'other_fee_vnd',r.other_fee_vnd::text,'counted_vnd',r.counted_vnd::text); END IF;
    BEGIN
      IF l.display->>'date' ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$' THEN v_date:=(l.display->>'date')::date;
      ELSIF l.display->>'date' ~ '^[0-9]{2}/[0-9]{2}/[0-9]{4}$' THEN
        v_date:=to_date(l.display->>'date','DD/MM/YYYY');
        IF to_char(v_date,'DD/MM/YYYY')<>l.display->>'date' THEN v_date:=NULL; END IF;
      END IF;
    EXCEPTION WHEN invalid_datetime_format OR datetime_field_overflow THEN v_date:=NULL; END;
    BEGIN IF l.display->>'unit_price' ~ '^[0-9]+$' THEN v_unit:=(l.display->>'unit_price')::bigint; END IF;
    EXCEPTION WHEN numeric_value_out_of_range THEN v_unit:=NULL; END;
    BEGIN IF l.display->>'fee_vnd' ~ '^[0-9]+$' THEN v_fee:=(l.display->>'fee_vnd')::bigint; END IF;
    EXCEPTION WHEN numeric_value_out_of_range THEN v_fee:=NULL; END;
    RETURN jsonb_build_object('legacy_row_id',l.id,'customer_id',l.customer_id,'month',l.debt_month,'debt_month',l.debt_month,
      'event_date',v_date,'container',l.display->>'container','carrier',l.display->>'carrier','shipper',l.display->>'shipper','origin',l.display->>'from','destination',l.display->>'to',
      'unit_price_vnd',v_unit::text,'other_fee_vnd',v_fee::text,'counted_vnd',coalesce(l.source_total_vnd,0)::text,'deleted',false);
END $function$;
ALTER FUNCTION sokhach._legacy_current(bigint) OWNER TO sokhach_owner;
REVOKE ALL ON FUNCTION sokhach._legacy_current(bigint) FROM PUBLIC;

-- FUNCTION sokhach._legacy_date(text)
CREATE OR REPLACE FUNCTION sokhach._legacy_date(p_text text)
 RETURNS date
 LANGUAGE plpgsql
 STABLE
 SET search_path TO 'pg_catalog', 'sokhach', 'pg_temp'
AS $function$
DECLARE v_date date;
BEGIN
    IF p_text ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$' THEN v_date:=p_text::date;
    ELSIF p_text ~ '^[0-9]{2}/[0-9]{2}/[0-9]{4}$' THEN
        v_date:=to_date(p_text,'DD/MM/YYYY');
        IF to_char(v_date,'DD/MM/YYYY')<>p_text THEN v_date:=NULL; END IF;
    END IF;
    RETURN v_date;
EXCEPTION WHEN invalid_datetime_format OR datetime_field_overflow THEN RETURN NULL;
END $function$;
ALTER FUNCTION sokhach._legacy_date(text) OWNER TO sokhach_owner;
REVOKE ALL ON FUNCTION sokhach._legacy_date(text) FROM PUBLIC;

-- FUNCTION sokhach._legacy_edited_date_match(text,date)
CREATE OR REPLACE FUNCTION sokhach._legacy_edited_date_match(p_container text, p_date date)
 RETURNS boolean
 LANGUAGE plpgsql
 STABLE
 SET search_path TO 'pg_catalog', 'sokhach', 'pg_temp'
AS $function$
BEGIN
    IF coalesce(p_container,'')='' OR p_date IS NULL THEN RETURN false; END IF;
    RETURN EXISTS (SELECT 1 FROM (SELECT DISTINCT y.legacy_row_id FROM sokhach.legacy_trip_rev y
            WHERE sokhach._normalize_key(y.container)=p_container) c
        JOIN sokhach.legacy_row l ON l.id=c.legacy_row_id AND l.kind='trip'
        JOIN sokhach.cutover_customer cc ON (cc.customer_id,cc.cutover_id)=(l.customer_id,l.cutover_id) AND cc.status='active'
        CROSS JOIN LATERAL (SELECT x.event_date,x.container,x.deleted FROM sokhach.legacy_trip_rev x
            WHERE x.legacy_row_id=l.id ORDER BY x.id DESC LIMIT 1) r
        WHERE NOT r.deleted AND sokhach._normalize_key(r.container)=p_container
          AND r.event_date IS NOT NULL AND abs(r.event_date-p_date)<=3);
END $function$;
ALTER FUNCTION sokhach._legacy_edited_date_match(text,date) OWNER TO sokhach_owner;
REVOKE ALL ON FUNCTION sokhach._legacy_edited_date_match(text,date) FROM PUBLIC;

-- FUNCTION sokhach._legacy_pay_date(text)
CREATE OR REPLACE FUNCTION sokhach._legacy_pay_date(p_text text)
 RETURNS date
 LANGUAGE plpgsql
 STABLE
 SET search_path TO 'pg_catalog', 'sokhach', 'pg_temp'
AS $function$
-- Ngày trong ô ngày của khoản thu Sheet, cùng luật với pay_date (web/v7_receipt_queue.py): số serial, ISO đầu chuỗi,
-- dd/mm/yyyy ở đầu hoặc giữa ghi chú. Không đọc được thì NULL, không đoán.
DECLARE v_text text := btrim(coalesce(p_text,''),E' \t\r\n'); v_part text[];
BEGIN
    IF v_text ~ '^[0-9]{5}(\.0+)?$' THEN RETURN DATE '1899-12-30'+split_part(v_text,'.',1)::int; END IF;
    v_part := regexp_match(v_text,'^([0-9]{4})-([0-9]{1,2})-([0-9]{1,2})(?![0-9])');
    IF v_part IS NOT NULL THEN RETURN make_date(v_part[1]::int,v_part[2]::int,v_part[3]::int); END IF;
    v_part := regexp_match(v_text,'(?<![0-9])([0-9]{1,2})[/.-]([0-9]{1,2})[/.-]([0-9]{4})(?![0-9])');
    IF v_part IS NOT NULL THEN RETURN make_date(v_part[3]::int,v_part[2]::int,v_part[1]::int); END IF;
    RETURN NULL;
EXCEPTION WHEN datetime_field_overflow THEN RETURN NULL;
END $function$;
ALTER FUNCTION sokhach._legacy_pay_date(text) OWNER TO sokhach_owner;
REVOKE ALL ON FUNCTION sokhach._legacy_pay_date(text) FROM PUBLIC;

-- FUNCTION sokhach._legacy_undated_match(text,date)
CREATE OR REPLACE FUNCTION sokhach._legacy_undated_match(p_container text, p_date date)
 RETURNS boolean
 LANGUAGE plpgsql
 STABLE
 SET search_path TO 'pg_catalog', 'sokhach', 'pg_temp'
AS $function$
DECLARE v_month date := date_trunc('month',p_date)::date;
BEGIN
    IF coalesce(p_container,'')='' OR p_date IS NULL THEN RETURN false; END IF;
    -- Lọc theo tháng và container trước (rẻ), rồi mới đọc bản sửa mới nhất của từng dòng ứng viên.
    RETURN EXISTS (SELECT 1 FROM (
            SELECT l.id FROM sokhach.legacy_row l WHERE l.kind='trip' AND l.debt_month=v_month
               AND sokhach._normalize_key(l.display->>'container')=p_container
            UNION
            SELECT y.legacy_row_id FROM sokhach.legacy_trip_rev y WHERE y.debt_month=v_month
               AND sokhach._normalize_key(y.container)=p_container) c
        JOIN sokhach.legacy_row l ON l.id=c.id
        JOIN sokhach.cutover_customer cc ON (cc.customer_id,cc.cutover_id)=(l.customer_id,l.cutover_id) AND cc.status='active'
        LEFT JOIN LATERAL (SELECT x.id,x.debt_month,x.event_date,x.container,x.deleted FROM sokhach.legacy_trip_rev x
            WHERE x.legacy_row_id=l.id ORDER BY x.id DESC LIMIT 1) r ON true
        WHERE NOT coalesce(r.deleted,false)
          AND coalesce(r.debt_month,l.debt_month)=v_month
          AND sokhach._normalize_key(CASE WHEN r.id IS NULL THEN l.display->>'container' ELSE r.container END)=p_container
          AND (CASE WHEN r.id IS NULL THEN sokhach._legacy_date(l.display->>'date') ELSE r.event_date END) IS NULL);
END $function$;
ALTER FUNCTION sokhach._legacy_undated_match(text,date) OWNER TO sokhach_owner;
REVOKE ALL ON FUNCTION sokhach._legacy_undated_match(text,date) FROM PUBLIC;

-- FUNCTION sokhach._lines(bigint)
CREATE OR REPLACE FUNCTION sokhach._lines(p_receipt bigint)
 RETURNS jsonb
 LANGUAGE sql
 SECURITY DEFINER
 SET search_path TO 'pg_catalog', 'sokhach', 'pg_temp'
AS $function$
    SELECT coalesce(jsonb_agg(jsonb_build_object('id', id, 'month', debt_month,
        'kind', kind, 'amount_vnd', amount_vnd::text)
        ORDER BY debt_month, CASE kind WHEN 'debt' THEN 0 ELSE 1 END, id), '[]'::jsonb)
    FROM sokhach.receipt_line
    WHERE receipt_id = p_receipt AND superseded_by_event IS NULL
$function$;
ALTER FUNCTION sokhach._lines(bigint) OWNER TO sokhach_owner;
REVOKE ALL ON FUNCTION sokhach._lines(bigint) FROM PUBLIC;

-- FUNCTION sokhach._lookup_price(bigint,date,text,text,text)
CREATE OR REPLACE FUNCTION sokhach._lookup_price(p_customer bigint, p_date date, p_origin text, p_destination text, p_shipper text)
 RETURNS jsonb
 LANGUAGE plpgsql
 STABLE
 SET search_path TO 'pg_catalog', 'sokhach', 'pg_temp'
AS $function$
DECLARE v_key text:=sokhach._price_key(p_origin); v_dest text:=coalesce(sokhach._price_key(p_destination),'');
 v_use text:=''; v_loc sokhach.price_location%ROWTYPE; v_tier text; v_rate record;
BEGIN
 IF NOT EXISTS (SELECT 1 FROM sokhach.price_period WHERE customer_id=p_customer) THEN
   RETURN jsonb_build_object('reason','NO_TABLE'); END IF;
 IF p_date IS NULL THEN RETURN jsonb_build_object('reason','NO_DATE'); END IF;
 IF v_key IS NULL THEN RETURN jsonb_build_object('reason','NO_ORIGIN'); END IF;
 SELECT l.* INTO v_loc FROM sokhach.price_location l WHERE l.customer_id=p_customer AND (l.name_key=v_key
   OR EXISTS (SELECT 1 FROM sokhach.price_location_alias a WHERE a.location_id=l.id AND a.alias_key=v_key));
 IF NOT FOUND THEN RETURN jsonb_build_object('reason','UNKNOWN_LOCATION'); END IF;
 -- Q3: shipper trong danh sách TT lấy giá TT; mọi shipper khác, kể cả trống, lấy giá khách.
 v_tier:=CASE WHEN EXISTS (SELECT 1 FROM sokhach.price_tt_shipper s WHERE s.customer_id=p_customer
   AND s.shipper_key=sokhach._price_key(p_shipper)) THEN 'tt' ELSE 'khach' END;
 -- BANG-GIA-04: dòng Nơi đến trống là giá chung của nơi đi. Đợt có đúng nơi đến phủ ngày chuyến thì dùng
 -- đợt đó (thiếu nhóm giá cũng không lấy giá chung thay); không có thì dùng giá chung.
 IF v_dest<>'' AND EXISTS (SELECT 1 FROM sokhach.price_rate r JOIN sokhach.price_period p ON p.id=r.period_id
     WHERE r.location_id=v_loc.id AND r.destination_key=v_dest
       AND p.valid_from<=p_date AND (p.valid_to IS NULL OR p_date<=p.valid_to)) THEN v_use:=v_dest; END IF;
 SELECT p.valid_from,p.valid_to,r.unit_price_vnd INTO v_rate FROM sokhach.price_rate r
   JOIN sokhach.price_period p ON p.id=r.period_id
   WHERE r.location_id=v_loc.id AND r.destination_key=v_use AND r.tier=v_tier AND p.valid_from<=p_date AND (p.valid_to IS NULL OR p_date<=p.valid_to);
 IF FOUND THEN
   RETURN jsonb_build_object('unit_price_vnd',v_rate.unit_price_vnd::text,'tier',v_tier,'location',v_loc.name,'destination',p_destination,
     'any_destination',v_use='','valid_from',v_rate.valid_from,'valid_to',v_rate.valid_to);
 END IF;
 -- Có đợt phủ ngày cho kho này nhưng thiếu ô của nhóm cần dùng: không lấy giá nhóm kia thay.
 RETURN jsonb_build_object('reason',CASE WHEN NOT EXISTS (SELECT 1 FROM sokhach.price_rate r
     WHERE r.location_id=v_loc.id AND r.destination_key IN (v_dest,''))
     THEN CASE WHEN v_dest='' THEN 'NO_DESTINATION' ELSE 'UNKNOWN_DESTINATION' END
   WHEN EXISTS (SELECT 1 FROM sokhach.price_rate r
     JOIN sokhach.price_period p ON p.id=r.period_id WHERE r.location_id=v_loc.id
       AND r.destination_key=v_use
       AND p.valid_from<=p_date AND (p.valid_to IS NULL OR p_date<=p.valid_to)) THEN 'NO_RATE' ELSE 'NO_PERIOD' END,
   'tier',v_tier,'location',v_loc.name,'destination',p_destination);
END $function$;
ALTER FUNCTION sokhach._lookup_price(bigint,date,text,text,text) OWNER TO sokhach_owner;
REVOKE ALL ON FUNCTION sokhach._lookup_price(bigint,date,text,text,text) FROM PUBLIC;

-- FUNCTION sokhach._mark_json(sokhach.contact_mark,date)
CREATE OR REPLACE FUNCTION sokhach._mark_json(m sokhach.contact_mark, p_today date)
 RETURNS jsonb
 LANGUAGE plpgsql
 STABLE SECURITY DEFINER
 SET search_path TO 'pg_catalog', 'sokhach', 'pg_temp'
AS $function$
DECLARE v_status text; v_paid bigint; v_pid text;
BEGIN
 IF m.cancelled_at IS NOT NULL THEN v_status:='cancelled';
 ELSIF m.kind='promise' THEN
   SELECT coalesce(sum(r.amount_vnd),0) INTO v_paid FROM sokhach.receipt r
     WHERE r.customer_id=m.customer_id AND r.voided_on IS NULL AND r.date BETWEEN m.created_on AND m.on_date;
   v_status:=CASE WHEN v_paid>=m.amount_vnd THEN 'kept' WHEN p_today>m.on_date THEN 'missed' ELSE 'pending' END;
 ELSIF m.kind='paid_claim' THEN
   SELECT r.pid INTO v_pid FROM sokhach.receipt r
     WHERE r.customer_id=m.customer_id AND r.voided_on IS NULL AND r.amount_vnd=m.amount_vnd
       AND r.date BETWEEN m.on_date-3 AND m.on_date+7 ORDER BY r.date,r.pid LIMIT 1;
   v_status:=CASE WHEN v_pid IS NOT NULL THEN 'received' WHEN p_today>m.on_date+3 THEN 'not_seen' ELSE 'waiting' END;
 END IF;
 RETURN jsonb_build_object('id',m.id,'customer_id',m.customer_id,'kind',m.kind,'amount_vnd',m.amount_vnd::text,'on_date',m.on_date,
   'note',m.note,'conversation_id',m.conversation_id,'message_id',m.message_id,'message_at',m.message_at,
   'message_sender',m.message_sender,'message_excerpt',m.message_excerpt,'created_by',m.created_by,'created_at',m.created_at,
   'created_on',m.created_on,'cancelled_by',m.cancelled_by,'cancelled_at',m.cancelled_at,'cancel_reason',m.cancel_reason,
   'status',v_status,'paid_vnd',v_paid::text,'receipt_pid',v_pid);
END $function$;
ALTER FUNCTION sokhach._mark_json(sokhach.contact_mark,date) OWNER TO sokhach_owner;
REVOKE ALL ON FUNCTION sokhach._mark_json(sokhach.contact_mark,date) FROM PUBLIC;

-- FUNCTION sokhach._month_open(bigint,date,timestamp with time zone)
CREATE OR REPLACE FUNCTION sokhach._month_open(p_customer bigint, p_month date, p_now timestamp with time zone)
 RETURNS void
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'pg_catalog', 'sokhach', 'pg_temp'
AS $function$
DECLARE v_locked boolean;
BEGIN
    IF p_month IS NULL OR extract(day FROM p_month) <> 1 THEN RAISE EXCEPTION 'INVALID_MONTH'; END IF;
    SELECT locked INTO v_locked FROM sokhach.month_state
    WHERE customer_id = p_customer AND month = p_month;
    IF coalesce(v_locked, p_month <> date_trunc('month', p_now AT TIME ZONE 'Asia/Ho_Chi_Minh')::date)
    THEN RAISE EXCEPTION 'MONTH_LOCKED'; END IF;
END $function$;
ALTER FUNCTION sokhach._month_open(bigint,date,timestamp with time zone) OWNER TO sokhach_owner;
REVOKE ALL ON FUNCTION sokhach._month_open(bigint,date,timestamp with time zone) FROM PUBLIC;

-- FUNCTION sokhach._next_pid(bigint)
CREATE OR REPLACE FUNCTION sokhach._next_pid(p_customer bigint)
 RETURNS text
 LANGUAGE sql
 SECURITY DEFINER
 SET search_path TO 'pg_catalog', 'sokhach', 'pg_temp'
AS $function$
    SELECT 'PH-' || lpad(n::text,greatest(3,length(n::text)),'0') FROM (
        SELECT coalesce(max(substring(pid FROM 4)::bigint),0)+1 AS n FROM (
            SELECT pid FROM sokhach.receipt WHERE customer_id=p_customer
            UNION ALL SELECT source_pid FROM sokhach.offset_pair WHERE source_customer_id=p_customer
            UNION ALL SELECT display->>'pid' FROM sokhach.legacy_row
                WHERE customer_id=p_customer AND kind='receipt'
        ) codes WHERE pid ~ '^PH-[0-9]+$'
    ) seq
$function$;
ALTER FUNCTION sokhach._next_pid(bigint) OWNER TO sokhach_owner;
REVOKE ALL ON FUNCTION sokhach._next_pid(bigint) FROM PUBLIC;

-- FUNCTION sokhach._normalize_key(text)
CREATE OR REPLACE FUNCTION sokhach._normalize_key(p_value text)
 RETURNS text
 LANGUAGE sql
 IMMUTABLE
 SET search_path TO 'pg_catalog', 'sokhach', 'pg_temp'
AS $function$
    SELECT upper(regexp_replace(coalesce(p_value,''),
        U&'[\0009-\000D\0020\0085\00A0\1680\2000-\200A\2028\2029\202F\205F\3000]', '', 'g'))
$function$;
ALTER FUNCTION sokhach._normalize_key(text) OWNER TO sokhach_owner;
REVOKE ALL ON FUNCTION sokhach._normalize_key(text) FROM PUBLIC;

-- FUNCTION sokhach._price_date(jsonb)
CREATE OR REPLACE FUNCTION sokhach._price_date(p_value jsonb)
 RETURNS date
 LANGUAGE plpgsql
 IMMUTABLE
 SET search_path TO 'pg_catalog', 'sokhach', 'pg_temp'
AS $function$
DECLARE v date;
BEGIN
 IF jsonb_typeof(p_value) IS DISTINCT FROM 'string' OR p_value#>>'{}' !~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$'
 THEN RAISE EXCEPTION 'PRICE_INVALID_PERIOD'; END IF;
 BEGIN v:=(p_value#>>'{}')::date;
 EXCEPTION WHEN invalid_datetime_format OR datetime_field_overflow THEN RAISE EXCEPTION 'PRICE_INVALID_PERIOD'; END;
 IF to_char(v,'YYYY-MM-DD')<>p_value#>>'{}' THEN RAISE EXCEPTION 'PRICE_INVALID_PERIOD'; END IF;
 RETURN v;
END $function$;
ALTER FUNCTION sokhach._price_date(jsonb) OWNER TO sokhach_owner;
REVOKE ALL ON FUNCTION sokhach._price_date(jsonb) FROM PUBLIC;

-- FUNCTION sokhach._price_key(text)
CREATE OR REPLACE FUNCTION sokhach._price_key(p_value text)
 RETURNS text
 LANGUAGE sql
 IMMUTABLE
 SET search_path TO 'pg_catalog', 'sokhach', 'pg_temp'
AS $function$
 SELECT nullif(btrim(regexp_replace(upper(coalesce(p_value,'')),
   U&'[\0009-\000D\0020\0085\00A0\1680\2000-\200A\2028\2029\202F\205F\3000]+',' ','g')),'')
$function$;
ALTER FUNCTION sokhach._price_key(text) OWNER TO sokhach_owner;
REVOKE ALL ON FUNCTION sokhach._price_key(text) FROM PUBLIC;

-- FUNCTION sokhach._price_table(bigint)
CREATE OR REPLACE FUNCTION sokhach._price_table(p_customer bigint)
 RETURNS jsonb
 LANGUAGE sql
 STABLE
 SET search_path TO 'pg_catalog', 'sokhach', 'pg_temp'
AS $function$
 SELECT jsonb_build_object(
  'tt_shippers',(SELECT coalesce(jsonb_agg(s.name ORDER BY s.shipper_key),'[]') FROM sokhach.price_tt_shipper s
     WHERE s.customer_id=p_customer),
  'locations',(SELECT coalesce(jsonb_agg(jsonb_build_object('name',l.name,'aliases',
       (SELECT coalesce(jsonb_agg(a.alias ORDER BY a.alias_key),'[]') FROM sokhach.price_location_alias a
        WHERE a.location_id=l.id)) ORDER BY l.name_key),'[]') FROM sokhach.price_location l WHERE l.customer_id=p_customer),
  'periods',(SELECT coalesce(jsonb_agg(jsonb_build_object('valid_from',p.valid_from,'valid_to',p.valid_to,'rates',
       (SELECT coalesce(jsonb_agg(jsonb_build_object('location',l.name,'destination',r.destination,'tier',r.tier,'unit_price_vnd',r.unit_price_vnd::text)
          ORDER BY l.name_key,r.destination_key,r.tier),'[]') FROM sokhach.price_rate r JOIN sokhach.price_location l ON l.id=r.location_id
        WHERE r.period_id=p.id)) ORDER BY p.valid_from,p.valid_to NULLS LAST,p.id),'[]')
     FROM sokhach.price_period p WHERE p.customer_id=p_customer))
$function$;
ALTER FUNCTION sokhach._price_table(bigint) OWNER TO sokhach_owner;
REVOKE ALL ON FUNCTION sokhach._price_table(bigint) FROM PUBLIC;

-- FUNCTION sokhach._price_text(jsonb)
CREATE OR REPLACE FUNCTION sokhach._price_text(p_value jsonb)
 RETURNS text
 LANGUAGE plpgsql
 IMMUTABLE
 SET search_path TO 'pg_catalog', 'sokhach', 'pg_temp'
AS $function$
BEGIN
 IF jsonb_typeof(p_value) IS DISTINCT FROM 'string' OR btrim(p_value#>>'{}')='' OR length(p_value#>>'{}')>200
 THEN RAISE EXCEPTION 'INVALID_PRICE_TABLE'; END IF;
 RETURN btrim(p_value#>>'{}');
END $function$;
ALTER FUNCTION sokhach._price_text(jsonb) OWNER TO sokhach_owner;
REVOKE ALL ON FUNCTION sokhach._price_text(jsonb) FROM PUBLIC;

-- FUNCTION sokhach._price_trip_rows(bigint)
CREATE OR REPLACE FUNCTION sokhach._price_trip_rows(p_customer bigint)
 RETURNS TABLE(trip_id bigint, debt_month date, status text, unit_price_vnd bigint, other_fee_vnd bigint, from_table boolean, lookup jsonb, month_open boolean)
 LANGUAGE sql
 STABLE
 SET search_path TO 'pg_catalog', 'sokhach', 'pg_temp'
AS $function$
 SELECT t.id,t.debt_month,t.status,p.unit_price_vnd,p.other_fee_vnd,
  EXISTS (SELECT 1 FROM sokhach.trip_price_source s JOIN sokhach.trip_price_rev sr ON sr.id=s.price_rev_id
    WHERE sr.trip_id=t.id AND sr.unit_price_vnd IS NOT DISTINCT FROM p.unit_price_vnd
      AND NOT EXISTS (SELECT 1 FROM sokhach.trip_price_rev x WHERE x.trip_id=t.id AND x.id>sr.id
        AND x.unit_price_vnd IS DISTINCT FROM sr.unit_price_vnd)),
  sokhach._lookup_price(p_customer,t.event_date,t.origin,t.destination,t.shipper),
  NOT coalesce(ms.locked,t.debt_month<>date_trunc('month',clock_timestamp() AT TIME ZONE 'Asia/Ho_Chi_Minh')::date)
 FROM sokhach.v_trip_current t
 LEFT JOIN LATERAL (SELECT r.unit_price_vnd,r.other_fee_vnd FROM sokhach.trip_price_rev r
   WHERE r.trip_id=t.id ORDER BY r.id DESC LIMIT 1) p ON true
 LEFT JOIN sokhach.month_state ms ON (ms.customer_id,ms.month)=(t.customer_id,t.debt_month)
 WHERE t.customer_id=p_customer AND NOT t.deleted AND coalesce(t.container,'')<>''
$function$;
ALTER FUNCTION sokhach._price_trip_rows(bigint) OWNER TO sokhach_owner;
REVOKE ALL ON FUNCTION sokhach._price_trip_rows(bigint) FROM PUBLIC;

-- FUNCTION sokhach._receipt_image_matches(text,bigint)
CREATE OR REPLACE FUNCTION sokhach._receipt_image_matches(p_sha256 text, p_exclude bigint)
 RETURNS jsonb
 LANGUAGE sql
 STABLE SECURITY DEFINER
 SET search_path TO 'pg_catalog', 'sokhach', 'pg_temp'
AS $function$
 SELECT coalesce(jsonb_agg(jsonb_build_object('image_id',i.id,'customer_id',r.customer_id,'customer_name',c.name,
   'pid',r.pid,'date',r.date,'voided',r.voided_by_event IS NOT NULL) ORDER BY r.date,c.name COLLATE "C",r.pid COLLATE "C"),'[]'::jsonb)
 FROM sokhach.receipt_image i JOIN sokhach.receipt r ON r.id=i.receipt_id JOIN sokhach.customer c ON c.id=r.customer_id
 WHERE i.sha256=p_sha256 AND i.removed_by_event IS NULL AND i.id IS DISTINCT FROM p_exclude;
$function$;
ALTER FUNCTION sokhach._receipt_image_matches(text,bigint) OWNER TO sokhach_owner;
REVOKE ALL ON FUNCTION sokhach._receipt_image_matches(text,bigint) FROM PUBLIC;

-- FUNCTION sokhach._reprice_from_table(bigint,text)
CREATE OR REPLACE FUNCTION sokhach._reprice_from_table(p_customer bigint, p_key text)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'pg_catalog', 'sokhach', 'pg_temp'
AS $function$
DECLARE v_before jsonb; v_after jsonb; v_trips jsonb; v_delta bigint; v_item jsonb; v_event bigint; v_rev bigint; v_changes jsonb;
BEGIN
 SELECT jsonb_agg(jsonb_build_object('trip_id',x.trip_id,'container',t.container,
     'unit_price_vnd',x.unit_price_vnd::text,'other_fee_vnd',x.other_fee_vnd::text) ORDER BY x.trip_id),
   jsonb_agg(jsonb_build_object('trip_id',x.trip_id,'container',t.container,
     'unit_price_vnd',x.lookup->>'unit_price_vnd','other_fee_vnd',x.other_fee_vnd::text,'rate',x.lookup) ORDER BY x.trip_id),
   jsonb_agg(jsonb_build_object('trip_id',x.trip_id,'container',t.container,
     'before_vnd',x.unit_price_vnd::text,'after_vnd',x.lookup->>'unit_price_vnd') ORDER BY x.trip_id),
   sum((x.lookup->>'unit_price_vnd')::bigint-x.unit_price_vnd)
  INTO v_before,v_after,v_trips,v_delta
  FROM sokhach._price_trip_rows(p_customer) x JOIN sokhach.v_trip_current t ON t.id=x.trip_id
  WHERE x.from_table AND x.status='confirmed' AND x.month_open AND x.lookup ? 'unit_price_vnd'
    AND x.unit_price_vnd::text<>x.lookup->>'unit_price_vnd';
 IF v_after IS NULL THEN RETURN jsonb_build_object('trips','[]'::jsonb,'delta_vnd','0','reallocated','[]'::jsonb); END IF;
 INSERT INTO sokhach.event(customer_id,kind,actor,"before","after",idempotency_key)
 VALUES(p_customer,'price_table_apply',sokhach._actor(),jsonb_build_object('trips',v_before),
   jsonb_build_object('trips',v_after),p_key) RETURNING id INTO v_event;
 FOR v_item IN SELECT x FROM jsonb_array_elements(v_after) x LOOP
   INSERT INTO sokhach.trip_price_rev(trip_id,customer_id,unit_price_vnd,created_by_event)
   VALUES((v_item->>'trip_id')::bigint,p_customer,(v_item->>'unit_price_vnd')::bigint,v_event)
   RETURNING id INTO v_rev;
   INSERT INTO sokhach.trip_price_source(price_rev_id,customer_id,rate,created_by_event)
   VALUES(v_rev,p_customer,v_item->'rate',v_event);
   -- Phụ phí chỉ do _sync_trip_fee ghi lại từ dòng phụ phí (PHU-PHI-01), như apply_price_table.
   PERFORM sokhach._sync_trip_fee((v_item->>'trip_id')::bigint,v_event);
 END LOOP;
 v_changes:=sokhach.reallocate(p_customer,p_key);
 RETURN jsonb_build_object('trips',v_trips,'delta_vnd',v_delta::text,'reallocated',v_changes);
END $function$;
ALTER FUNCTION sokhach._reprice_from_table(bigint,text) OWNER TO sokhach_owner;
REVOKE ALL ON FUNCTION sokhach._reprice_from_table(bigint,text) FROM PUBLIC;

-- FUNCTION sokhach._rewrite_trip_fees(bigint,bigint,text,jsonb,jsonb,jsonb,jsonb)
CREATE OR REPLACE FUNCTION sokhach._rewrite_trip_fees(p_customer bigint, p_version bigint, p_key text, p_target jsonb, p_expected jsonb, p_lines jsonb, p_source jsonb)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'pg_catalog', 'sokhach', 'pg_temp'
AS $function$
DECLARE v_payload jsonb:=jsonb_build_object('command','rewrite_trip_fees','target',p_target,
 'expected_line_ids',p_expected,'lines',p_lines,'source',p_source);
 v_retry jsonb; v_before jsonb; v_after jsonb; v_line jsonb; v_new jsonb:='[]'; v_type sokhach.fee_type%ROWTYPE;
 v_amount bigint; v_old_total bigint; v_new_total bigint:=0; v_event bigint; v_trip bigint; v_legacy bigint;
 v_cur jsonb; v_fill boolean:=false;
BEGIN
 BEGIN v_retry:=sokhach._begin_command(p_customer,p_version,p_key,v_payload);
 EXCEPTION WHEN raise_exception THEN
   IF SQLERRM='STALE_LEDGER' THEN RAISE EXCEPTION 'VERSION_CONFLICT'; ELSE RAISE; END IF;
 END;
 IF v_retry IS NOT NULL THEN RETURN v_retry; END IF;
 PERFORM sokhach._baseline(p_customer);
 IF jsonb_typeof(p_expected) IS DISTINCT FROM 'array' OR jsonb_typeof(p_lines) IS DISTINCT FROM 'array'
   OR jsonb_array_length(p_lines) NOT BETWEEN 1 AND 10 OR jsonb_typeof(p_source) IS DISTINCT FROM 'object'
   OR length(p_source::text)>2000 THEN RAISE EXCEPTION 'INVALID_COMMAND'; END IF;
 v_before:=sokhach._fee_target(p_customer,p_target);
 v_trip:=(p_target->>'trip_id')::bigint; v_legacy:=(p_target->>'legacy_row_id')::bigint;
 PERFORM 1 FROM sokhach.trip_fee_line WHERE customer_id=p_customer AND voided_by_event IS NULL
   AND (trip_id=v_trip OR legacy_row_id=v_legacy) FOR UPDATE;
 IF (SELECT coalesce(jsonb_agg((x->>'id')::bigint ORDER BY (x->>'id')::bigint),'[]') FROM jsonb_array_elements(v_before->'fee_lines') x)
   IS DISTINCT FROM (SELECT coalesce(jsonb_agg(x::bigint ORDER BY x::bigint),'[]') FROM jsonb_array_elements_text(p_expected) x)
 THEN RAISE EXCEPTION 'FEE_LINES_CHANGED'; END IF;
 SELECT sum((x->>'amount_vnd')::bigint)::bigint INTO v_old_total FROM jsonb_array_elements(v_before->'fee_lines') x;
 FOR v_line IN SELECT x FROM jsonb_array_elements(p_lines) x LOOP
   IF jsonb_typeof(v_line) IS DISTINCT FROM 'object' OR NOT (v_line ? 'fee_type_id' AND v_line ? 'amount_vnd')
     OR EXISTS(SELECT 1 FROM jsonb_object_keys(v_line) k WHERE k NOT IN ('fee_type_id','amount_vnd','note'))
     OR jsonb_typeof(v_line->'note') NOT IN ('string','null') OR length(v_line->>'note')>2000
   THEN RAISE EXCEPTION 'INVALID_COMMAND'; END IF;
   SELECT * INTO v_type FROM sokhach.fee_type WHERE id=(v_line->>'fee_type_id')::bigint FOR SHARE;
   IF NOT FOUND OR NOT v_type.active THEN RAISE EXCEPTION 'FEE_TYPE_INACTIVE'; END IF;
   IF v_type.system_key='initial' THEN RAISE EXCEPTION 'FEE_TYPE_SYSTEM'; END IF;
   v_amount:=(v_line->>'amount_vnd')::bigint;
   IF v_amount IS NULL OR v_amount=0 THEN RAISE EXCEPTION 'FEE_AMOUNT_INVALID'; END IF;
   IF (v_type.sign='positive' AND v_amount<0) OR (v_type.sign='negative' AND v_amount>0)
   THEN RAISE EXCEPTION 'FEE_SIGN_INVALID'; END IF;
   v_new_total:=v_new_total+v_amount;
   v_new:=v_new||jsonb_build_array(jsonb_build_object('fee_type_id',v_type.id,'amount_vnd',v_amount::text,
     'note',nullif(btrim(coalesce(v_line->>'note','')),'')));
 END LOOP;
 IF v_new_total IS DISTINCT FROM v_old_total THEN
   -- MAY-PS-01: ô TOTAL của dòng sổ gốc đã gồm phí mà các khoản chưa đủ: được bổ sung tới đúng TOTAL - đơn giá, TOTAL không đổi.
   IF v_legacy IS NOT NULL THEN
     v_cur:=sokhach._legacy_current(v_legacy);
     v_fill:=v_new_total=(v_cur->>'counted_vnd')::bigint-(v_cur->>'unit_price_vnd')::bigint;
   END IF;
   IF NOT v_fill THEN RAISE EXCEPTION 'FEE_TOTAL_CHANGED'; END IF;
 END IF;
 IF (SELECT jsonb_agg(x-'id' ORDER BY x->>'fee_type_id',x->>'amount_vnd',x->>'note') FROM jsonb_array_elements(v_before->'fee_lines') x)
   = (SELECT jsonb_agg(x ORDER BY x->>'fee_type_id',x->>'amount_vnd',x->>'note') FROM jsonb_array_elements(v_new) x)
 THEN RAISE EXCEPTION 'NO_CHANGE'; END IF;
 v_after:=v_before||jsonb_build_object('fee_lines',v_new);
 INSERT INTO sokhach.event(customer_id,kind,actor,"before","after",idempotency_key)
 VALUES(p_customer,'rewrite_trip_fees',sokhach._actor(),
   jsonb_build_object('targets',jsonb_build_array(v_before),'batch_count',1,'source',p_source),
   jsonb_build_object('targets',jsonb_build_array(v_after),'batch_count',1,'source',p_source),p_key) RETURNING id INTO v_event;
 UPDATE sokhach.trip_fee_line SET voided_by_event=v_event WHERE customer_id=p_customer AND voided_by_event IS NULL
   AND (trip_id=v_trip OR legacy_row_id=v_legacy);
 INSERT INTO sokhach.trip_fee_line(customer_id,trip_id,legacy_row_id,fee_type_id,amount_vnd,note,created_by_event)
 SELECT p_customer,v_trip,v_legacy,(x->>'fee_type_id')::bigint,(x->>'amount_vnd')::bigint,x->>'note',v_event
 FROM jsonb_array_elements(v_new) x;
 IF v_trip IS NOT NULL THEN PERFORM sokhach._sync_trip_fee(v_trip,v_event); END IF;
 -- _change_legacy tính lại TOTAL = đơn giá + tổng mới, đúng bằng TOTAL cũ nên không sinh điều chỉnh.
 IF v_fill THEN PERFORM sokhach._change_legacy(p_customer,p_version,p_key,v_legacy,'other_fee_vnd',v_new_total::text,false,v_event); END IF;
 RETURN sokhach._finish_command(p_customer,p_key,v_payload,jsonb_build_object('event_id',v_event,
   'targets',jsonb_build_array(sokhach._fee_target(p_customer,p_target))));
EXCEPTION WHEN numeric_value_out_of_range THEN RAISE EXCEPTION 'FEE_AMOUNT_INVALID';
 WHEN invalid_text_representation THEN RAISE EXCEPTION 'INVALID_COMMAND';
END $function$;
ALTER FUNCTION sokhach._rewrite_trip_fees(bigint,bigint,text,jsonb,jsonb,jsonb,jsonb) OWNER TO sokhach_owner;
REVOKE ALL ON FUNCTION sokhach._rewrite_trip_fees(bigint,bigint,text,jsonb,jsonb,jsonb,jsonb) FROM PUBLIC;

-- FUNCTION sokhach._safety_events(bigint,interval)
CREATE OR REPLACE FUNCTION sokhach._safety_events(p_upto bigint, p_settle interval)
 RETURNS jsonb
 LANGUAGE plpgsql
 STABLE SECURITY DEFINER
 SET search_path TO 'pg_catalog', 'sokhach', 'pg_temp'
 SET "TimeZone" TO 'UTC'
 SET "DateStyle" TO 'ISO, YMD'
AS $function$
-- LUOI-AN-TOAN-01 kiểm 4. Khối 1000 id của sokhach.event: [số dòng, md5 nối md5 từng dòng theo id]. `store`: mọi dòng id <= settled,
-- với settled là id lớn nhất trong các dòng cũ hơn p_settle (id cấp lúc chèn, dòng hiện lúc commit: giao dịch còn chạy có thể giữ id
-- nhỏ hơn dòng đã thấy). `check`: tính lại trên dòng id <= p_upto (mốc lượt trước) để so với khối đã giữ.
DECLARE v_settled bigint;
BEGIN
    SELECT max(id) INTO v_settled FROM sokhach.event WHERE at < statement_timestamp() - p_settle;
    RETURN (WITH e AS MATERIALIZED (
        SELECT id, id / 1000 AS b, md5(jsonb_strip_nulls(to_jsonb(x))::text) AS h FROM sokhach.event x
         WHERE id <= greatest(coalesce(v_settled, 0), coalesce(p_upto, 0)))
    SELECT jsonb_build_object('settled', v_settled,
        'store', (SELECT coalesce(jsonb_object_agg(b::text, jsonb_build_array(n, h)), '{}'::jsonb) FROM (
            SELECT b, count(*) AS n, md5(string_agg(h, '' ORDER BY id)) AS h FROM e WHERE id <= v_settled GROUP BY b) s),
        'check', CASE WHEN p_upto IS NOT NULL THEN (SELECT coalesce(jsonb_object_agg(b::text, jsonb_build_array(n, h)), '{}'::jsonb) FROM (
            SELECT b, count(*) AS n, md5(string_agg(h, '' ORDER BY id)) AS h FROM e WHERE id <= p_upto GROUP BY b) s) END));
END $function$;
ALTER FUNCTION sokhach._safety_events(bigint,interval) OWNER TO sokhach_owner;
REVOKE ALL ON FUNCTION sokhach._safety_events(bigint,interval) FROM PUBLIC;

-- FUNCTION sokhach._safety_fingerprints()
CREATE OR REPLACE FUNCTION sokhach._safety_fingerprints()
 RETURNS jsonb
 LANGUAGE sql
 STABLE SECURITY DEFINER
 SET search_path TO 'pg_catalog', 'sokhach', 'pg_temp'
 SET "TimeZone" TO 'UTC'
 SET "DateStyle" TO 'ISO, YMD'
AS $function$
-- LUOI-AN-TOAN-01 kiểm 3. Mỗi sổ: version và md5 từng phần dữ liệu tiền. md5 một phần nối md5 từng dòng theo khóa dòng (thứ tự byte);
-- bỏ khóa NULL nên thêm cột cho phép NULL không đổi dấu vân. Giờ UTC, ngày ISO cố định để dấu vân không theo cài đặt của phiên.
WITH r AS (
    SELECT customer_id, 'opening_balance'::text AS part, id::text AS k, md5(jsonb_strip_nulls(to_jsonb(x))::text) AS h FROM sokhach.opening_balance x
    UNION ALL SELECT customer_id, 'legacy_row', id::text, md5(jsonb_strip_nulls(to_jsonb(x))::text) FROM sokhach.legacy_row x
    UNION ALL SELECT customer_id, 'legacy_trip_rev', id::text, md5(jsonb_strip_nulls(to_jsonb(x))::text) FROM sokhach.legacy_trip_rev x
    UNION ALL SELECT customer_id, 'trip', id::text, md5(jsonb_strip_nulls(to_jsonb(x))::text) FROM sokhach.trip x
    UNION ALL SELECT customer_id, 'trip_info_rev', id::text, md5(jsonb_strip_nulls(to_jsonb(x))::text) FROM sokhach.trip_info_rev x
    UNION ALL SELECT customer_id, 'trip_price_rev', id::text, md5(jsonb_strip_nulls(to_jsonb(x))::text) FROM sokhach.trip_price_rev x
    UNION ALL SELECT customer_id, 'trip_fee_line', id::text, md5(jsonb_strip_nulls(to_jsonb(x))::text) FROM sokhach.trip_fee_line x
    UNION ALL SELECT customer_id, 'adjustment', id::text, md5(jsonb_strip_nulls(to_jsonb(x))::text) FROM sokhach.adjustment x
    UNION ALL SELECT customer_id, 'receipt', id::text, md5(jsonb_strip_nulls(to_jsonb(x))::text) FROM sokhach.receipt x
    UNION ALL SELECT customer_id, 'receipt_line', id::text, md5(jsonb_strip_nulls(to_jsonb(x))::text) FROM sokhach.receipt_line x
    UNION ALL SELECT source_customer_id, 'offset_pair', id::text, md5(jsonb_strip_nulls(to_jsonb(x))::text) FROM sokhach.offset_pair x
    UNION ALL SELECT customer_id, 'month_state', month::text, md5(jsonb_strip_nulls(to_jsonb(x))::text) FROM sokhach.month_state x
    UNION ALL SELECT customer_id, 'cutover_customer', cutover_id::text, md5(jsonb_strip_nulls(to_jsonb(x))::text) FROM sokhach.cutover_customer x
), p AS (
    SELECT customer_id, jsonb_object_agg(part, h) AS parts FROM (
        SELECT customer_id, part, md5(string_agg(h, '' ORDER BY k COLLATE "C")) AS h FROM r GROUP BY customer_id, part) s
    GROUP BY customer_id
)
SELECT coalesce(jsonb_object_agg(c.id::text, jsonb_build_object('version', c.version, 'parts', coalesce(p.parts, '{}'::jsonb))), '{}'::jsonb)
FROM sokhach.customer c LEFT JOIN p ON p.customer_id = c.id
$function$;
ALTER FUNCTION sokhach._safety_fingerprints() OWNER TO sokhach_owner;
REVOKE ALL ON FUNCTION sokhach._safety_fingerprints() FROM PUBLIC;

-- FUNCTION sokhach._sync_trip_fee(bigint,bigint)
CREATE OR REPLACE FUNCTION sokhach._sync_trip_fee(p_trip_id bigint, p_event_id bigint)
 RETURNS void
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'pg_catalog', 'sokhach', 'pg_temp'
AS $function$
DECLARE v_unit bigint; v_old bigint; v_total bigint; v_count bigint;
BEGIN SELECT unit_price_vnd,other_fee_vnd INTO v_unit,v_old FROM sokhach.trip_price_rev WHERE trip_id=p_trip_id ORDER BY id DESC LIMIT 1;
 SELECT count(*),sum(amount_vnd) INTO v_count,v_total FROM sokhach.trip_fee_line WHERE trip_id=p_trip_id AND voided_by_event IS NULL;
 IF v_count=0 THEN v_total:=NULL; END IF; IF v_old IS NOT DISTINCT FROM v_total THEN RETURN; END IF;
 INSERT INTO sokhach.trip_price_rev(trip_id,customer_id,unit_price_vnd,other_fee_vnd,created_by_event) SELECT p_trip_id,t.customer_id,v_unit,v_total,p_event_id FROM sokhach.trip t WHERE t.id=p_trip_id;
END $function$;
ALTER FUNCTION sokhach._sync_trip_fee(bigint,bigint) OWNER TO sokhach_owner;
REVOKE ALL ON FUNCTION sokhach._sync_trip_fee(bigint,bigint) FROM PUBLIC;

-- FUNCTION sokhach._trip_current_row(bigint,bigint)
CREATE OR REPLACE FUNCTION sokhach._trip_current_row(p_customer bigint, p_trip bigint)
 RETURNS jsonb
 LANGUAGE sql
 STABLE
 SET search_path TO 'pg_catalog', 'sokhach', 'pg_temp'
AS $function$
    SELECT jsonb_build_object('id',t.id,'event_date',t.event_date,'container',t.container,'status',t.status,'booking',t.booking,
        'unit_price_vnd',p.unit_price_vnd::text,'other_fee_vnd',p.other_fee_vnd::text)
    FROM sokhach.v_trip_current t
    LEFT JOIN LATERAL (SELECT unit_price_vnd,other_fee_vnd FROM sokhach.trip_price_rev
        WHERE trip_id=t.id ORDER BY id DESC LIMIT 1) p ON true
    WHERE t.id=p_trip AND t.customer_id=p_customer AND NOT t.deleted
$function$;
ALTER FUNCTION sokhach._trip_current_row(bigint,bigint) OWNER TO sokhach_owner;
REVOKE ALL ON FUNCTION sokhach._trip_current_row(bigint,bigint) FROM PUBLIC;

-- FUNCTION sokhach._trip_date(text)
CREATE OR REPLACE FUNCTION sokhach._trip_date(p_value text)
 RETURNS date
 LANGUAGE plpgsql
 SET search_path TO 'pg_catalog', 'sokhach', 'pg_temp'
AS $function$
DECLARE v date;
BEGIN
    IF p_value IS NULL OR p_value !~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$' THEN RAISE EXCEPTION 'INVALID_DATE'; END IF;
    BEGIN v := p_value::date;
    EXCEPTION WHEN invalid_datetime_format OR datetime_field_overflow THEN RAISE EXCEPTION 'INVALID_DATE'; END;
    IF NOT isfinite(v) OR to_char(v,'YYYY-MM-DD')<>p_value THEN RAISE EXCEPTION 'INVALID_DATE'; END IF;
    IF v>(clock_timestamp() AT TIME ZONE 'Asia/Ho_Chi_Minh')::date THEN RAISE EXCEPTION 'FUTURE_DATE'; END IF;
    RETURN v;
END $function$;
ALTER FUNCTION sokhach._trip_date(text) OWNER TO sokhach_owner;
REVOKE ALL ON FUNCTION sokhach._trip_date(text) FROM PUBLIC;

-- FUNCTION sokhach._trip_dup_reason(bigint,bigint,text,text,date,bigint,jsonb)
CREATE OR REPLACE FUNCTION sokhach._trip_dup_reason(p_customer bigint, p_cutover bigint, p_container text, p_booking text, p_date date, p_exclude_trip bigint, p_batch jsonb)
 RETURNS text
 LANGUAGE plpgsql
 STABLE
 SET search_path TO 'pg_catalog', 'sokhach', 'pg_temp'
AS $function$
BEGIN
    IF EXISTS (SELECT 1 FROM sokhach.baseline_trip_ref r WHERE r.cutover_id=p_cutover
        AND r.booking_norm=p_booking AND r.container_norm=p_container)
    THEN RETURN 'BASELINE_CODE_MATCH'; END IF;
    IF EXISTS (SELECT 1 FROM sokhach.baseline_trip_ref r WHERE r.cutover_id=p_cutover
        AND r.container_norm=p_container AND abs(r.event_date-p_date)<=3)
       OR sokhach._legacy_edited_date_match(p_container,p_date)
    THEN RETURN 'BASELINE_DATE_WINDOW'; END IF;
    IF sokhach._legacy_undated_match(p_container,p_date) THEN RETURN 'BASELINE_UNDATED_MONTH'; END IF;
    IF EXISTS (SELECT 1 FROM sokhach.v_trip_current t WHERE NOT t.deleted AND t.customer_id=p_customer
        AND t.id IS DISTINCT FROM p_exclude_trip
        AND sokhach._normalize_key(t.container)=p_container
        AND (sokhach._booking_key(t.booking,t.container,t.event_date)=p_booking OR abs(t.event_date-p_date)<=3))
    THEN RETURN 'WEB_DUPLICATE'; END IF;
    IF EXISTS (SELECT 1 FROM jsonb_array_elements(coalesce(p_batch,'[]'::jsonb)) r
        WHERE sokhach._normalize_key(r->>'container')=p_container
        AND (sokhach._booking_key(r->>'booking',r->>'container',(r->>'event_date')::date)=p_booking
            OR abs((r->>'event_date')::date-p_date)<=3))
    THEN RETURN 'BATCH_DUPLICATE'; END IF;
    RETURN NULL;
END $function$;
ALTER FUNCTION sokhach._trip_dup_reason(bigint,bigint,text,text,date,bigint,jsonb) OWNER TO sokhach_owner;
REVOKE ALL ON FUNCTION sokhach._trip_dup_reason(bigint,bigint,text,text,date,bigint,jsonb) FROM PUBLIC;

-- FUNCTION sokhach._void_receipt(bigint,bigint,text,text,text)
CREATE OR REPLACE FUNCTION sokhach._void_receipt(customer_id bigint, expected_version bigint, idempotency_key text, pid text, reason text)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'pg_catalog', 'sokhach', 'pg_temp'
AS $function$
DECLARE v_payload jsonb := jsonb_build_object('command','_void_receipt','pid',pid,'reason',reason);
        v_retry jsonb; v_receipt sokhach.receipt%ROWTYPE; v_before jsonb;
        v_event bigint; v_count bigint;
BEGIN
    v_retry := sokhach._begin_command(customer_id,expected_version,idempotency_key,v_payload);
    IF v_retry IS NOT NULL THEN RETURN v_retry; END IF;
    PERFORM sokhach._baseline(customer_id);
    IF reason IS NULL OR btrim(reason)='' THEN RAISE EXCEPTION 'VOID_REASON_REQUIRED'; END IF;
    SELECT * INTO v_receipt FROM sokhach.receipt
     WHERE receipt.customer_id=_void_receipt.customer_id AND receipt.pid=_void_receipt.pid;
    IF NOT FOUND THEN RAISE EXCEPTION 'RECEIPT_NOT_FOUND'; END IF;
    IF v_receipt.voided_on IS NOT NULL THEN RAISE EXCEPTION 'RECEIPT_ALREADY_VOID'; END IF;
    v_before := sokhach._lines(v_receipt.id);
    INSERT INTO sokhach.event(customer_id,kind,actor,"before","after",idempotency_key)
    VALUES (customer_id,'void',sokhach._actor(),
        jsonb_build_object('receipt',v_receipt.id,'pid',pid,'amount_vnd',v_receipt.amount_vnd::text,
            'allocations',v_before),
        jsonb_build_object('receipt',v_receipt.id,'pid',pid,'void_reason',btrim(reason),
            'allocations','[]'::jsonb),idempotency_key)
    RETURNING id INTO v_event;
    UPDATE sokhach.receipt_line SET superseded_by_event=v_event
    WHERE receipt_id=v_receipt.id AND superseded_by_event IS NULL;
    GET DIAGNOSTICS v_count = ROW_COUNT;
    IF v_count <> jsonb_array_length(v_before) THEN RAISE EXCEPTION 'VOID_LINE_MISMATCH'; END IF;
    UPDATE sokhach.receipt SET void_reason=btrim(reason),
        voided_on=(clock_timestamp() AT TIME ZONE 'Asia/Ho_Chi_Minh')::date,
        voided_by=sokhach._actor(),voided_by_event=v_event WHERE id=v_receipt.id;
    PERFORM sokhach._check_allocations(customer_id);
    RETURN sokhach._finish_command(customer_id,idempotency_key,v_payload,
        jsonb_build_object('receipt_id',v_receipt.id,'pid',pid,'voided_lines',v_count));
END $function$;
ALTER FUNCTION sokhach._void_receipt(bigint,bigint,text,text,text) OWNER TO sokhach_owner;
REVOKE ALL ON FUNCTION sokhach._void_receipt(bigint,bigint,text,text,text) FROM PUBLIC;

-- FUNCTION sokhach.activate_cutover(bigint,text,text)
CREATE OR REPLACE FUNCTION sokhach.activate_cutover(cutover_id bigint, idempotency_key text, signoff_ref text)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'pg_catalog', 'sokhach', 'pg_temp'
AS $function$
DECLARE v_payload jsonb:=jsonb_build_object('command','activate_cutover','signoff_ref',signoff_ref);
        v_retry jsonb; v_result jsonb;
BEGIN
    v_retry:=sokhach._begin_cutover(cutover_id,idempotency_key,v_payload);
    IF v_retry IS NOT NULL THEN RETURN v_retry; END IF;
    IF (SELECT status FROM sokhach.cutover WHERE id=activate_cutover.cutover_id)<>'verified'
    THEN RAISE EXCEPTION 'CUTOVER_TRANSITION_ORDER'; END IF;
    PERFORM sokhach._check_cutover(cutover_id);
    UPDATE sokhach.cutover SET status='active' WHERE id=activate_cutover.cutover_id;
    v_result:=jsonb_build_object('cutover_id',cutover_id,'status','active');
    RETURN sokhach._finish_cutover(cutover_id,idempotency_key,v_payload,v_result);
END $function$;
ALTER FUNCTION sokhach.activate_cutover(bigint,text,text) OWNER TO sokhach_owner;
REVOKE ALL ON FUNCTION sokhach.activate_cutover(bigint,text,text) FROM PUBLIC;

-- FUNCTION sokhach.activate_cutover_customer(bigint,bigint,bigint,text,text)
CREATE OR REPLACE FUNCTION sokhach.activate_cutover_customer(customer_id bigint, cutover_id bigint, expected_version bigint, idempotency_key text, signoff_ref text)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'pg_catalog', 'sokhach', 'pg_temp'
AS $function$
DECLARE v_payload jsonb:=jsonb_build_object('command','activate_cutover_customer',
        'cutover_id',cutover_id,'signoff_ref',signoff_ref);
        v_retry jsonb; v_result jsonb;
BEGIN
    PERFORM 1 FROM sokhach.cutover WHERE id=activate_cutover_customer.cutover_id FOR UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION 'CUTOVER_NOT_FOUND'; END IF;
    v_retry:=sokhach._begin_command(customer_id,expected_version,idempotency_key,v_payload);
    IF v_retry IS NOT NULL THEN RETURN v_retry; END IF;
    IF NOT EXISTS(SELECT 1 FROM sokhach.cutover_customer cc
      JOIN sokhach.cutover c ON c.id=cc.cutover_id
      WHERE cc.customer_id=activate_cutover_customer.customer_id
        AND cc.cutover_id=activate_cutover_customer.cutover_id
        AND cc.status='verified' AND c.status='active')
    THEN RAISE EXCEPTION 'CUTOVER_TRANSITION_ORDER'; END IF;
    PERFORM sokhach._check_cutover_customer(customer_id,cutover_id);
    UPDATE sokhach.cutover_customer SET status='active'
      WHERE cutover_customer.customer_id=activate_cutover_customer.customer_id
        AND cutover_customer.cutover_id=activate_cutover_customer.cutover_id;
    v_result:=jsonb_build_object('cutover_id',cutover_id,'customer_id',customer_id,
        'status','active');
    RETURN sokhach._finish_command(customer_id,idempotency_key,v_payload,v_result);
END $function$;
ALTER FUNCTION sokhach.activate_cutover_customer(bigint,bigint,bigint,text,text) OWNER TO sokhach_owner;
REVOKE ALL ON FUNCTION sokhach.activate_cutover_customer(bigint,bigint,bigint,text,text) FROM PUBLIC;

-- FUNCTION sokhach.add_fee_type(text,text,text)
CREATE OR REPLACE FUNCTION sokhach.add_fee_type(idempotency_key text, name text, kind text)
 RETURNS jsonb
 LANGUAGE sql
 SECURITY DEFINER
 SET search_path TO 'pg_catalog', 'sokhach', 'pg_temp'
AS $function$
 SELECT sokhach._change_fee_type(idempotency_key,'add_fee_type',NULL,name,kind)
$function$;
ALTER FUNCTION sokhach.add_fee_type(text,text,text) OWNER TO sokhach_owner;
REVOKE ALL ON FUNCTION sokhach.add_fee_type(text,text,text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION sokhach.add_fee_type(text,text,text) TO sokhach_app;

-- FUNCTION sokhach.add_trip_fees(bigint,bigint,text,jsonb,bigint,bigint,text)
CREATE OR REPLACE FUNCTION sokhach.add_trip_fees(customer_id bigint, expected_version bigint, idempotency_key text, targets jsonb, fee_type_id bigint, amount_vnd bigint, note text)
 RETURNS jsonb
 LANGUAGE sql
 SECURITY DEFINER
 SET search_path TO 'pg_catalog', 'sokhach', 'pg_temp'
AS $function$
 SELECT sokhach._change_trip_fees(customer_id,expected_version,idempotency_key,'add_trip_fees',targets,fee_type_id,amount_vnd,note,NULL)
$function$;
ALTER FUNCTION sokhach.add_trip_fees(bigint,bigint,text,jsonb,bigint,bigint,text) OWNER TO sokhach_owner;
REVOKE ALL ON FUNCTION sokhach.add_trip_fees(bigint,bigint,text,jsonb,bigint,bigint,text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION sokhach.add_trip_fees(bigint,bigint,text,jsonb,bigint,bigint,text) TO sokhach_app;

-- FUNCTION sokhach.adjust_month(bigint,bigint,text,date,bigint,text)
CREATE OR REPLACE FUNCTION sokhach.adjust_month(customer_id bigint, expected_version bigint, idempotency_key text, debt_month date, amount_vnd bigint, note text)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'pg_catalog', 'sokhach', 'pg_temp'
AS $function$
DECLARE v_payload jsonb := jsonb_build_object('command','adjust_month','month',debt_month,
        'amount_vnd',amount_vnd,'note',note);
        v_retry jsonb; v_id bigint; v_event bigint; v_changes jsonb;
BEGIN
    v_retry := sokhach._begin_command(customer_id,expected_version,idempotency_key,v_payload);
    IF v_retry IS NOT NULL THEN RETURN v_retry; END IF;
    PERFORM sokhach._baseline(customer_id);
    IF debt_month IS NULL OR extract(day FROM debt_month) <> 1 OR amount_vnd IS NULL OR amount_vnd=0
    THEN RAISE EXCEPTION 'INVALID_ADJUSTMENT'; END IF;
    IF NOT EXISTS (SELECT 1 FROM sokhach.opening_balance o
        JOIN sokhach.cutover_customer cc USING (customer_id,cutover_id)
        JOIN sokhach.cutover c ON c.id=cc.cutover_id
        WHERE o.customer_id=adjust_month.customer_id AND o.debt_month=adjust_month.debt_month
          AND cc.status='active' AND c.status='active')
       AND NOT EXISTS (SELECT 1 FROM sokhach.v_trip_current t
           WHERE t.customer_id=adjust_month.customer_id AND t.debt_month=adjust_month.debt_month AND NOT t.deleted AND t.status='confirmed')
       AND NOT EXISTS (SELECT 1 FROM sokhach.v_adjustment_current a
           WHERE a.customer_id=adjust_month.customer_id AND a.debt_month=adjust_month.debt_month)
    THEN RAISE EXCEPTION 'MONTH_NOT_FOUND'; END IF;
    PERFORM sokhach._month_open(customer_id,debt_month,clock_timestamp());
    v_id := nextval(pg_get_serial_sequence('sokhach.adjustment','id'));
    INSERT INTO sokhach.event(customer_id,kind,actor,"before","after",idempotency_key)
    VALUES (customer_id,'adjust_month',sokhach._actor(),
        jsonb_build_object('month',debt_month,'amount_vnd','0'),
        jsonb_build_object('adjustment',v_id,'month',debt_month,'amount_vnd',amount_vnd::text,'note',note),idempotency_key)
    RETURNING id INTO v_event;
    INSERT INTO sokhach.adjustment(id,customer_id,debt_month,trip_id,amount_vnd,note,actor,created_by_event)
    OVERRIDING SYSTEM VALUE VALUES (v_id,customer_id,debt_month,NULL,amount_vnd,note,sokhach._actor(),v_event);
    v_changes := sokhach.reallocate(customer_id,idempotency_key);
    RETURN sokhach._finish_command(customer_id,idempotency_key,v_payload,
        jsonb_build_object('adjustment_id',v_id,'reallocated',v_changes));
EXCEPTION WHEN numeric_value_out_of_range THEN RAISE EXCEPTION 'INVALID_VND';
END $function$;
ALTER FUNCTION sokhach.adjust_month(bigint,bigint,text,date,bigint,text) OWNER TO sokhach_owner;
REVOKE ALL ON FUNCTION sokhach.adjust_month(bigint,bigint,text,date,bigint,text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION sokhach.adjust_month(bigint,bigint,text,date,bigint,text) TO sokhach_app;

-- FUNCTION sokhach.adjust_trip(bigint,bigint,text,bigint,bigint,text,text,bigint)
CREATE OR REPLACE FUNCTION sokhach.adjust_trip(customer_id bigint, expected_version bigint, idempotency_key text, trip_id bigint, new_amount_vnd bigint, note text, field text DEFAULT NULL::text, new_value_vnd bigint DEFAULT NULL::bigint)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'pg_catalog', 'sokhach', 'pg_temp'
AS $function$
DECLARE v_payload jsonb := jsonb_build_object('command','adjust_trip','trip_id',trip_id,
        'new_amount_vnd',new_amount_vnd,'note',note) ||
        CASE WHEN field IS NULL AND new_value_vnd IS NULL THEN '{}'::jsonb
        ELSE jsonb_build_object('field',field,'new_value_vnd',new_value_vnd) END;
        v_retry jsonb; v_trip sokhach.v_trip_current%ROWTYPE; v_base bigint; v_old bigint;
        v_delta bigint; v_id bigint; v_event bigint; v_changes jsonb;
        v_price sokhach.trip_price_rev%ROWTYPE; v_fee bigint; v_field_old bigint;
BEGIN
    v_retry := sokhach._begin_command(customer_id,expected_version,idempotency_key,v_payload);
    IF v_retry IS NOT NULL THEN RETURN v_retry; END IF;
    PERFORM sokhach._baseline(customer_id);
    SELECT * INTO v_trip FROM sokhach.v_trip_current v WHERE v.id=trip_id AND v.customer_id=adjust_trip.customer_id AND NOT v.deleted;
    IF v_trip.status<>'confirmed' THEN RAISE EXCEPTION 'TRIP_PENDING_REVIEW'; END IF;
    IF NOT FOUND THEN RAISE EXCEPTION 'TRIP_NOT_FOUND'; END IF;
    PERFORM sokhach._month_open(customer_id,v_trip.debt_month,clock_timestamp());
    SELECT * INTO v_price FROM sokhach.trip_price_rev p
    WHERE p.trip_id=adjust_trip.trip_id ORDER BY p.id DESC LIMIT 1;
    v_base := CASE WHEN v_price.unit_price_vnd IS NOT NULL
        THEN v_price.unit_price_vnd+coalesce(v_price.other_fee_vnd,0)
        WHEN v_trip.container IS NULL OR v_trip.container='' THEN v_price.other_fee_vnd END;
    IF v_base IS NULL THEN RAISE EXCEPTION 'TRIP_HAS_NO_PRICE'; END IF;
    SELECT v_base+coalesce(sum(amount_vnd),0)::bigint INTO v_old
    FROM sokhach.v_adjustment_current a WHERE a.customer_id=adjust_trip.customer_id
      AND a.trip_id=adjust_trip.trip_id;
    IF field IS NOT NULL OR new_value_vnd IS NOT NULL THEN
        IF field='other_fee_vnd' AND EXISTS (SELECT 1 FROM sokhach.trip_fee_line l JOIN sokhach.fee_type f ON f.id=l.fee_type_id
            WHERE l.trip_id=adjust_trip.trip_id AND l.voided_by_event IS NULL
              AND coalesce(f.system_key,'') NOT IN ('other','discount','initial'))
        THEN RAISE EXCEPTION 'FEE_LINES_TYPED'; END IF;
        IF field IS NULL OR field NOT IN ('unit_price_vnd','other_fee_vnd')
           OR new_value_vnd IS NULL OR (field='unit_price_vnd' AND new_value_vnd<0) OR new_amount_vnd IS NOT NULL
        THEN RAISE EXCEPTION 'INVALID_ADJUSTMENT'; END IF;
        -- Effective fee = latest price revision fee plus every fee delta. A price edit
        -- never absorbs older deltas, so a typed intent lands on the displayed value.
        SELECT coalesce(v_price.other_fee_vnd,0)
            +coalesce(sum(a.amount_vnd) FILTER (WHERE a.field='other_fee_vnd'),0)
        INTO v_fee
        FROM sokhach.v_adjustment_current a WHERE a.customer_id=adjust_trip.customer_id
          AND a.trip_id=adjust_trip.trip_id;
        v_field_old := CASE field WHEN 'unit_price_vnd' THEN v_old-v_fee ELSE v_fee END;
        new_amount_vnd := CASE field WHEN 'unit_price_vnd' THEN new_value_vnd+v_fee
            ELSE v_old-v_fee+new_value_vnd END;
    END IF;
    IF new_amount_vnd IS NULL OR (field IS DISTINCT FROM 'other_fee_vnd' AND new_amount_vnd < 0)
    THEN RAISE EXCEPTION 'INVALID_VND'; END IF;
    v_delta := new_amount_vnd-v_old;
    IF v_delta=0 THEN RAISE EXCEPTION 'NO_CHANGE'; END IF;
    v_id := CASE WHEN field='other_fee_vnd' THEN NULL
        ELSE nextval(pg_get_serial_sequence('sokhach.adjustment','id')) END;
    INSERT INTO sokhach.event(customer_id,kind,actor,"before","after",idempotency_key)
    VALUES (customer_id,'adjust_trip',sokhach._actor(),
        jsonb_build_object('trip',trip_id,'amount_vnd',v_old::text,'field',field,'new_value_vnd',v_field_old::text),
        jsonb_build_object('adjustment',CASE WHEN field='other_fee_vnd' THEN NULL ELSE v_id END,'trip_id',trip_id,'old_amount_vnd',v_old::text,
            'new_amount_vnd',new_amount_vnd::text,'delta_vnd',v_delta::text,'note',note,
            'field',field,'new_value_vnd',new_value_vnd::text),idempotency_key)
    RETURNING id INTO v_event;
    IF field='other_fee_vnd' THEN
        PERFORM sokhach._compat_trip_fee(customer_id,trip_id,new_value_vnd,v_event);
        v_changes := sokhach.reallocate(customer_id,idempotency_key);
        RETURN sokhach._finish_command(customer_id,idempotency_key,v_payload,
            jsonb_build_object('trip_id',trip_id,'fee_vnd',new_value_vnd::text,'delta_vnd',v_delta::text,'reallocated',v_changes));
    END IF;
    INSERT INTO sokhach.adjustment(id,customer_id,debt_month,trip_id,amount_vnd,note,actor,created_by_event,field,new_value_vnd)
    OVERRIDING SYSTEM VALUE VALUES (v_id,customer_id,v_trip.origin_month,trip_id,v_delta,note,
        sokhach._actor(),v_event,field,new_value_vnd);
    v_changes := sokhach.reallocate(customer_id,idempotency_key);
    RETURN sokhach._finish_command(customer_id,idempotency_key,v_payload,
        jsonb_build_object('adjustment_id',v_id,'delta_vnd',v_delta::text,'reallocated',v_changes));
EXCEPTION WHEN numeric_value_out_of_range THEN RAISE EXCEPTION 'INVALID_VND';
    END $function$;
ALTER FUNCTION sokhach.adjust_trip(bigint,bigint,text,bigint,bigint,text,text,bigint) OWNER TO sokhach_owner;
REVOKE ALL ON FUNCTION sokhach.adjust_trip(bigint,bigint,text,bigint,bigint,text,text,bigint) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION sokhach.adjust_trip(bigint,bigint,text,bigint,bigint,text,text,bigint) TO sokhach_app;

-- FUNCTION sokhach.apply_price_table(bigint,bigint,text,jsonb)
CREATE OR REPLACE FUNCTION sokhach.apply_price_table(customer_id bigint, expected_version bigint, idempotency_key text, trip_ids jsonb)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'pg_catalog', 'sokhach', 'pg_temp'
AS $function$
DECLARE v_payload jsonb:=jsonb_build_object('command','apply_price_table','trip_ids',trip_ids);
 v_retry jsonb; v_id bigint; t sokhach.v_trip_current%ROWTYPE; v_old sokhach.trip_price_rev%ROWTYPE;
 v_lookup jsonb; v_before jsonb:='[]'; v_after jsonb:='[]'; v_item jsonb; v_event bigint; v_rev bigint; v_changes jsonb;
 v_from jsonb;
BEGIN
 v_retry:=sokhach._begin_command(customer_id,expected_version,idempotency_key,v_payload);
 IF v_retry IS NOT NULL THEN RETURN v_retry; END IF;
 PERFORM sokhach._baseline(customer_id);
 IF jsonb_typeof(trip_ids) IS DISTINCT FROM 'array' OR jsonb_array_length(trip_ids) NOT BETWEEN 1 AND 500
   OR EXISTS (SELECT 1 FROM jsonb_array_elements(trip_ids) x WHERE jsonb_typeof(x)<>'number' OR x::text !~ '^[1-9][0-9]{0,18}$')
   OR (SELECT count(*)<>count(DISTINCT x::text) FROM jsonb_array_elements(trip_ids) x)
 THEN RAISE EXCEPTION 'INVALID_TRIPS'; END IF;
 -- BANG-GIA-01 (29/10/2026): gõ tay thắng bảng giá. Chỉ ghi chuyến chưa có đơn giá hoặc đang mang đơn giá do
 -- bảng ghi (áp lại); đơn giá gõ tay không bị bảng ghi đè, kể cả khi client gửi nhầm.
 SELECT coalesce(jsonb_object_agg(x.trip_id::text,x.from_table),'{}') INTO v_from
   FROM sokhach._price_trip_rows(apply_price_table.customer_id) x;
 FOR v_id IN SELECT x::text::bigint FROM jsonb_array_elements(trip_ids) x ORDER BY 1 LOOP
   SELECT * INTO t FROM sokhach.v_trip_current v WHERE v.id=v_id AND v.customer_id=apply_price_table.customer_id AND NOT v.deleted;
   IF NOT FOUND OR coalesce(t.container,'')='' THEN RAISE EXCEPTION 'TRIP_NOT_FOUND'; END IF;
   IF t.status<>'confirmed' THEN RAISE EXCEPTION 'TRIP_PENDING_REVIEW'; END IF;
   PERFORM sokhach._month_open(customer_id,t.debt_month,clock_timestamp());
   v_lookup:=sokhach._lookup_price(customer_id,t.event_date,t.origin,t.destination,t.shipper);
   IF NOT v_lookup ? 'unit_price_vnd' THEN RAISE EXCEPTION 'PRICE_NOT_FOUND'; END IF;
   SELECT * INTO v_old FROM sokhach.trip_price_rev r WHERE r.trip_id=v_id ORDER BY r.id DESC LIMIT 1;
   IF v_old.unit_price_vnd::text IS NOT DISTINCT FROM v_lookup->>'unit_price_vnd' THEN RAISE EXCEPTION 'NO_CHANGE'; END IF;
   IF v_old.unit_price_vnd IS NOT NULL AND NOT coalesce((v_from->>v_id::text)::boolean,false)
   THEN RAISE EXCEPTION 'PRICE_TYPED_PRICE'; END IF;
   v_before:=v_before||jsonb_build_array(jsonb_build_object('trip_id',v_id,'container',t.container,
     'unit_price_vnd',v_old.unit_price_vnd::text,'other_fee_vnd',v_old.other_fee_vnd::text));
   v_after:=v_after||jsonb_build_array(jsonb_build_object('trip_id',v_id,'container',t.container,
     'unit_price_vnd',v_lookup->>'unit_price_vnd','other_fee_vnd',v_old.other_fee_vnd::text,'rate',v_lookup));
 END LOOP;
 INSERT INTO sokhach.event(customer_id,kind,actor,"before","after",idempotency_key)
 VALUES(customer_id,'price_table_apply',sokhach._actor(),jsonb_build_object('trips',v_before),
   jsonb_build_object('trips',v_after),idempotency_key) RETURNING id INTO v_event;
 FOR v_item IN SELECT x FROM jsonb_array_elements(v_after) x LOOP
   INSERT INTO sokhach.trip_price_rev(trip_id,customer_id,unit_price_vnd,created_by_event)
   VALUES((v_item->>'trip_id')::bigint,customer_id,(v_item->>'unit_price_vnd')::bigint,v_event)
   RETURNING id INTO v_rev;
   INSERT INTO sokhach.trip_price_source(price_rev_id,customer_id,rate,created_by_event)
   VALUES(v_rev,customer_id,v_item->'rate',v_event);
   -- Phụ phí chỉ do _sync_trip_fee ghi lại từ dòng phụ phí (PHU-PHI-01), như edit_trip_price.
   PERFORM sokhach._sync_trip_fee((v_item->>'trip_id')::bigint,v_event);
 END LOOP;
 v_changes:=sokhach.reallocate(customer_id,idempotency_key);
 RETURN sokhach._finish_command(customer_id,idempotency_key,v_payload,
   jsonb_build_object('event_id',v_event,'trips',v_after,'reallocated',v_changes));
END $function$;
ALTER FUNCTION sokhach.apply_price_table(bigint,bigint,text,jsonb) OWNER TO sokhach_owner;
REVOKE ALL ON FUNCTION sokhach.apply_price_table(bigint,bigint,text,jsonb) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION sokhach.apply_price_table(bigint,bigint,text,jsonb) TO sokhach_app;

-- FUNCTION sokhach.apply_sheet_price(bigint,bigint,text,text,bigint,text,jsonb,jsonb)
CREATE OR REPLACE FUNCTION sokhach.apply_sheet_price(customer_id bigint, expected_version bigint, idempotency_key text, target_kind text, target_id bigint, source_fingerprint text, web_value jsonb, sheet_price jsonb)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'pg_catalog', 'sokhach', 'pg_temp'
AS $function$
DECLARE v_payload jsonb:=jsonb_build_object('command','apply_sheet_price','target_kind',target_kind,
 'target_id',target_id,'source_fingerprint',source_fingerprint,'web_value',web_value,'sheet_price',sheet_price);
 v_retry jsonb; v_current jsonb; v_result jsonb; v_version bigint; v_key text;
BEGIN
 v_retry:=sokhach._begin_command(customer_id,expected_version,idempotency_key,v_payload);
 IF v_retry IS NOT NULL THEN RETURN v_retry; END IF;
 PERFORM sokhach._baseline(customer_id);
 IF target_kind IS NULL OR target_kind NOT IN ('trip','legacy') OR target_id IS NULL OR target_id<=0
  OR source_fingerprint IS NULL OR source_fingerprint !~ '^[0-9a-f]{64}$'
  OR jsonb_typeof(sheet_price) IS DISTINCT FROM 'object' OR web_value IS NULL
  OR sheet_price->>'unit_price_vnd' IS NULL OR sheet_price->>'unit_price_vnd' !~ '^[0-9]+$'
  OR (sheet_price->>'other_fee_vnd' IS NOT NULL AND sheet_price->>'other_fee_vnd' !~ '^-?[0-9]+$')
 THEN RAISE EXCEPTION 'INVALID_SHEET_RESOLUTION'; END IF;
 IF target_kind='trip' THEN
  -- audit SQL F4: một chuyến/một dòng sổ gốc, không dựng cả sổ bằng get_ledger.
  SELECT jsonb_build_object('unit_price_vnd',r->>'unit_price_vnd','other_fee_vnd',r->>'other_fee_vnd')
   INTO v_current FROM sokhach._trip_current_row(customer_id,target_id) r WHERE r IS NOT NULL;
 ELSE
  SELECT jsonb_build_object('unit_price_vnd',cur->>'unit_price_vnd','other_fee_vnd',cur->>'other_fee_vnd')
   INTO v_current FROM sokhach.legacy_row l
   JOIN sokhach.cutover_customer cc USING(customer_id,cutover_id) JOIN sokhach.cutover c ON c.id=cc.cutover_id
   CROSS JOIN LATERAL sokhach._legacy_current(l.id) cur
   WHERE l.customer_id=apply_sheet_price.customer_id AND l.id=target_id AND l.kind='trip'
     AND cc.status='active' AND c.status='active' AND NOT coalesce((cur->>'deleted')::boolean,false);
 END IF;
 IF v_current IS NULL THEN RAISE EXCEPTION 'TRIP_NOT_FOUND'; END IF;
 IF v_current IS DISTINCT FROM web_value THEN RAISE EXCEPTION 'STALE_LEDGER'; END IF;
 v_key:=encode(sha256(convert_to(idempotency_key||':sheet-price','UTF8')),'hex');
 IF target_kind='trip' THEN
  v_result:=sokhach.edit_trip_price(customer_id,expected_version,v_key,target_id,
   (sheet_price->>'unit_price_vnd')::bigint,(sheet_price->>'other_fee_vnd')::bigint);
 ELSE
  v_version:=expected_version;
  IF v_current->>'unit_price_vnd' IS DISTINCT FROM sheet_price->>'unit_price_vnd' THEN
   v_result:=sokhach.edit_legacy_trip(customer_id,v_version,v_key,target_id,'unit_price_vnd',sheet_price->>'unit_price_vnd');
   v_version:=(v_result->>'version')::bigint;
  END IF;
  IF nullif(v_current->>'other_fee_vnd','0') IS DISTINCT FROM nullif(sheet_price->>'other_fee_vnd','0') THEN
   v_result:=sokhach.edit_legacy_trip(customer_id,v_version,v_key||':fee',target_id,'other_fee_vnd',sheet_price->>'other_fee_vnd');
  END IF;
  IF v_result IS NULL THEN RAISE EXCEPTION 'NO_CHANGE'; END IF;
 END IF;
 INSERT INTO sokhach.event(customer_id,kind,actor,"before","after",idempotency_key)
 VALUES(customer_id,'sheet_conflict_resolved',sokhach._actor(),
  jsonb_build_object('target',jsonb_build_object('kind',target_kind,'id',target_id),'field','task_price','value',v_current),
  jsonb_build_object('target',jsonb_build_object('kind',target_kind,'id',target_id),'field','task_price','source_row',0,
   'sheet_value',source_fingerprint,'target_value',sheet_price,'decision','use_sheet','requested_price',sheet_price,
   'web_value',web_value,'request_key',idempotency_key),idempotency_key);
 RETURN sokhach._finish_command(customer_id,idempotency_key,v_payload,jsonb_build_object('written',1,'complete',true));
END $function$;
ALTER FUNCTION sokhach.apply_sheet_price(bigint,bigint,text,text,bigint,text,jsonb,jsonb) OWNER TO sokhach_owner;
REVOKE ALL ON FUNCTION sokhach.apply_sheet_price(bigint,bigint,text,text,bigint,text,jsonb,jsonb) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION sokhach.apply_sheet_price(bigint,bigint,text,text,bigint,text,jsonb,jsonb) TO sokhach_app;

-- FUNCTION sokhach.assign_sheet_trip(bigint,bigint,text,bigint,bigint,text,jsonb)
CREATE OR REPLACE FUNCTION sokhach.assign_sheet_trip(customer_id bigint, expected_version bigint, idempotency_key text, target_customer_id bigint, target_version bigint, source_fingerprint text, source_row jsonb)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'pg_catalog', 'sokhach', 'pg_temp'
AS $function$
DECLARE v_payload jsonb:=jsonb_build_object('command','assign_sheet_trip','target_customer_id',target_customer_id,
 'source_fingerprint',source_fingerprint,'source_row',source_row);
 v_retry jsonb; v_result jsonb; v_trip bigint; v_after jsonb; v_date date; v_key text;
BEGIN
 PERFORM id FROM sokhach.customer c WHERE c.id IN (customer_id,target_customer_id) ORDER BY id FOR UPDATE;
 v_retry:=sokhach._begin_command(customer_id,expected_version,idempotency_key,v_payload);
 IF v_retry IS NOT NULL THEN RETURN v_retry; END IF;
 IF target_customer_id IS NULL OR target_customer_id<=0 OR source_fingerprint IS NULL
  OR source_fingerprint !~ '^[0-9a-f]{64}$' OR jsonb_typeof(source_row) IS DISTINCT FROM 'object'
 THEN RAISE EXCEPTION 'INVALID_COMMAND'; END IF;
 v_date:=(source_row->>'event_date')::date;
 IF v_date IS NULL THEN RAISE EXCEPTION 'INVALID_DATE'; END IF;
 v_key:=encode(sha256(convert_to(idempotency_key||':assign','UTF8')),'hex');
 v_result:=sokhach.paste_trips(target_customer_id,target_version,v_key,date_trunc('month',v_date)::date,
  jsonb_build_array(jsonb_build_object('date',to_char(v_date,'DD/MM/YYYY'),'container',source_row->>'container',
   'carrier',source_row->>'carrier','shipper',source_row->>'shipper','from',source_row->>'origin','to',source_row->>'destination',
   'booking',coalesce(source_row->>'booking',''),'unitPriceVnd',NULL,'otherFeeVnd',NULL,
   'note','Chuyến đồng bộ','src','sheet-choice:'||source_fingerprint)));
 v_trip:=(v_result->'trip_ids'->>0)::bigint;
 v_after:=jsonb_build_object('target',jsonb_build_object('kind','trip','id',v_trip),'field','task_assignment',
  'source_row',source_row->'source_row','sheet_value',source_fingerprint,'target_value',target_customer_id,
  'decision','use_sheet','target_customer_id',target_customer_id,'request_key',idempotency_key,
  'arguments',jsonb_build_object('customer_id',customer_id,'expected_version',expected_version,'idempotency_key',idempotency_key,
   'target_customer_id',target_customer_id,'target_version',target_version,'source_fingerprint',source_fingerprint,'source_row',source_row));
 INSERT INTO sokhach.event(customer_id,kind,actor,"before","after",idempotency_key)
 VALUES(customer_id,'sheet_conflict_resolved',sokhach._actor(),jsonb_build_object('target',v_after->'target','field','task_assignment'),v_after,idempotency_key);
 IF target_customer_id<>customer_id THEN
  INSERT INTO sokhach.event(customer_id,kind,actor,"before","after",idempotency_key)
  VALUES(target_customer_id,'sheet_conflict_resolved',sokhach._actor(),jsonb_build_object('target',v_after->'target','field','task_assignment'),v_after,v_key);
 END IF;
 RETURN sokhach._finish_command(customer_id,idempotency_key,v_payload,jsonb_build_object('approved',1,'trip_id',v_trip,
  'target_customer_id',target_customer_id,'pending_review',v_result->'pending_review','complete',true));
END $function$;
ALTER FUNCTION sokhach.assign_sheet_trip(bigint,bigint,text,bigint,bigint,text,jsonb) OWNER TO sokhach_owner;
REVOKE ALL ON FUNCTION sokhach.assign_sheet_trip(bigint,bigint,text,bigint,bigint,text,jsonb) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION sokhach.assign_sheet_trip(bigint,bigint,text,bigint,bigint,text,jsonb) TO sokhach_app;

-- FUNCTION sokhach.attach_receipt_image(bigint,bigint,text,text,text,bytea)
CREATE OR REPLACE FUNCTION sokhach.attach_receipt_image(customer_id bigint, expected_version bigint, idempotency_key text, pid text, content_type text, data bytea)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'pg_catalog', 'sokhach', 'pg_temp'
AS $function$
DECLARE v_sha text:=CASE WHEN data IS NULL THEN NULL ELSE encode(sha256(data),'hex') END;
 v_payload jsonb:=jsonb_build_object('command','attach_receipt_image','pid',pid,'content_type',content_type,'sha256',v_sha);
 v_retry jsonb; r sokhach.receipt%ROWTYPE; v_id bigint; v_event bigint; v_image jsonb; v_ok boolean;
BEGIN
 v_retry:=sokhach._begin_command(customer_id,expected_version,idempotency_key,v_payload);
 IF v_retry IS NOT NULL THEN RETURN v_retry; END IF;
 -- plpgsql đọc điều kiện IF tới chữ THEN đầu tiên, nên CASE kiểm đầu file tính riêng.
 v_ok:=data IS NOT NULL AND CASE content_type
     WHEN 'image/png' THEN substring(data FROM 1 FOR 8)='\x89504e470d0a1a0a'::bytea
     WHEN 'image/jpeg' THEN substring(data FROM 1 FOR 3)='\xffd8ff'::bytea
     WHEN 'image/webp' THEN substring(data FROM 1 FOR 4)='\x52494646'::bytea AND substring(data FROM 9 FOR 4)='\x57454250'::bytea
     ELSE false END;
 IF NOT coalesce(v_ok,false) THEN RAISE EXCEPTION 'IMAGE_INVALID'; END IF;
 IF octet_length(data)>2097152 THEN RAISE EXCEPTION 'IMAGE_TOO_LARGE'; END IF;
 SELECT * INTO r FROM sokhach.receipt WHERE receipt.customer_id=attach_receipt_image.customer_id
   AND receipt.pid=attach_receipt_image.pid FOR UPDATE;
 IF NOT FOUND THEN RAISE EXCEPTION 'RECEIPT_NOT_FOUND'; END IF;
 IF r.voided_by_event IS NOT NULL OR r.void_reason IS NOT NULL THEN RAISE EXCEPTION 'RECEIPT_ALREADY_VOID'; END IF;
 IF EXISTS(SELECT 1 FROM sokhach.receipt_image i WHERE i.receipt_id=r.id AND i.sha256=v_sha AND i.removed_by_event IS NULL)
 THEN RAISE EXCEPTION 'IMAGE_DUPLICATE'; END IF;
 IF (SELECT count(*) FROM sokhach.receipt_image i WHERE i.receipt_id=r.id AND i.removed_by_event IS NULL)>=5
 THEN RAISE EXCEPTION 'IMAGE_LIMIT'; END IF;
 v_id:=nextval(pg_get_serial_sequence('sokhach.receipt_image','id'));
 v_image:=jsonb_build_object('id',v_id,'receipt_id',r.id,'pid',r.pid,'sha256',v_sha,'content_type',content_type,
   'byte_size',octet_length(data));
 INSERT INTO sokhach.event(customer_id,kind,actor,"before","after",idempotency_key)
   VALUES(customer_id,'receipt_image',sokhach._actor(),'{}',jsonb_build_object('image',v_image),idempotency_key)
   RETURNING id INTO v_event;
 INSERT INTO sokhach.receipt_image(id,customer_id,receipt_id,sha256,content_type,data,created_by_event)
   OVERRIDING SYSTEM VALUE VALUES(v_id,customer_id,r.id,v_sha,content_type,data,v_event);
 RETURN sokhach._finish_command(customer_id,idempotency_key,v_payload,
   jsonb_build_object('image',v_image,'duplicates',sokhach._receipt_image_matches(v_sha,v_id)));
END $function$;
ALTER FUNCTION sokhach.attach_receipt_image(bigint,bigint,text,text,text,bytea) OWNER TO sokhach_owner;
REVOKE ALL ON FUNCTION sokhach.attach_receipt_image(bigint,bigint,text,text,text,bytea) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION sokhach.attach_receipt_image(bigint,bigint,text,text,text,bytea) TO sokhach_app;

-- FUNCTION sokhach.cancel_mark(bigint,text)
CREATE OR REPLACE FUNCTION sokhach.cancel_mark(p_id bigint, p_reason text)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'pg_catalog', 'sokhach', 'pg_temp'
AS $function$
DECLARE v_row sokhach.contact_mark;
BEGIN
 IF p_reason IS NULL OR btrim(p_reason)='' THEN RAISE EXCEPTION 'REASON_REQUIRED'; END IF;
 SELECT * INTO v_row FROM sokhach.contact_mark m WHERE m.id=p_id FOR UPDATE;
 IF NOT FOUND THEN RAISE EXCEPTION 'MARK_NOT_FOUND'; END IF;
 IF v_row.cancelled_at IS NOT NULL THEN RAISE EXCEPTION 'MARK_ALREADY_CANCELLED'; END IF;
 UPDATE sokhach.contact_mark m SET cancelled_by=sokhach._actor(),cancelled_at=now(),cancel_reason=btrim(p_reason)
   WHERE m.id=p_id RETURNING * INTO v_row;
 RETURN sokhach._mark_json(v_row,(clock_timestamp() AT TIME ZONE 'Asia/Ho_Chi_Minh')::date);
END $function$;
ALTER FUNCTION sokhach.cancel_mark(bigint,text) OWNER TO sokhach_owner;
REVOKE ALL ON FUNCTION sokhach.cancel_mark(bigint,text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION sokhach.cancel_mark(bigint,text) TO sokhach_app;

-- FUNCTION sokhach.check_offset_pair()
CREATE OR REPLACE FUNCTION sokhach.check_offset_pair()
 RETURNS trigger
 LANGUAGE plpgsql
 SET search_path TO 'pg_catalog', 'sokhach', 'pg_temp'
AS $function$
DECLARE v_pair sokhach.offset_pair%ROWTYPE; v_id bigint;
BEGIN
    IF TG_TABLE_NAME='receipt' THEN
        SELECT id INTO v_id FROM sokhach.offset_pair WHERE target_receipt_id=NEW.id;
    ELSE v_id:=NEW.id; END IF;
    IF v_id IS NULL THEN RETURN NEW; END IF;
    SELECT * INTO v_pair FROM sokhach.offset_pair WHERE id=v_id;
    IF NOT EXISTS (SELECT 1 FROM sokhach.receipt r WHERE r.id=v_pair.target_receipt_id
        AND r.customer_id=v_pair.target_customer_id AND r.date=v_pair.date
        AND r.amount_vnd=v_pair.amount_vnd AND r.method='CẤN TRỪ'
        AND (r.voided_by_event IS NULL)=(v_pair.voided_by_event IS NULL)
        AND r.void_reason IS NOT DISTINCT FROM v_pair.void_reason)
       OR NOT EXISTS (SELECT 1 FROM sokhach.event e WHERE e.id=v_pair.created_by_event
        AND e.kind='receipt' AND e."after"->>'offset_pair_id'=v_pair.id::text
        AND e."after"->>'receipt'=v_pair.source_pid
        AND e."after"->>'amount_vnd'=(-v_pair.amount_vnd)::text)
       OR (v_pair.changed_by_event IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM sokhach.event e WHERE e.id=v_pair.changed_by_event AND e.kind='receipt_edit'
        AND e."after"->>'offset_pair_id'=v_pair.id::text AND (e."after"->>'date')::date=v_pair.date))
       OR (v_pair.voided_by_event IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM sokhach.event e WHERE e.id=v_pair.voided_by_event AND e.kind='void'
        AND e."after"->>'offset_pair_id'=v_pair.id::text
        AND e."after"->>'void_reason'=v_pair.void_reason))
    THEN RAISE EXCEPTION 'OFFSET_PAIR_INVARIANT'; END IF;
    RETURN NEW;
END $function$;
ALTER FUNCTION sokhach.check_offset_pair() OWNER TO sokhach_owner;
REVOKE ALL ON FUNCTION sokhach.check_offset_pair() FROM PUBLIC;

-- FUNCTION sokhach.check_offset_pid()
CREATE OR REPLACE FUNCTION sokhach.check_offset_pid()
 RETURNS trigger
 LANGUAGE plpgsql
 SET search_path TO 'pg_catalog', 'sokhach', 'pg_temp'
AS $function$
BEGIN
    IF TG_TABLE_NAME='receipt' THEN
        IF EXISTS (SELECT 1 FROM sokhach.offset_pair
            WHERE source_customer_id=NEW.customer_id AND source_pid=NEW.pid)
        THEN RAISE EXCEPTION 'OFFSET_PID_CONFLICT'; END IF;
    ELSE
        IF EXISTS (SELECT 1 FROM sokhach.receipt
            WHERE customer_id=NEW.source_customer_id AND pid=NEW.source_pid)
        THEN RAISE EXCEPTION 'OFFSET_PID_CONFLICT'; END IF;
    END IF;
    RETURN NEW;
END $function$;
ALTER FUNCTION sokhach.check_offset_pid() OWNER TO sokhach_owner;
REVOKE ALL ON FUNCTION sokhach.check_offset_pid() FROM PUBLIC;

-- FUNCTION sokhach.check_trip_missing_date()
CREATE OR REPLACE FUNCTION sokhach.check_trip_missing_date()
 RETURNS trigger
 LANGUAGE plpgsql
 SET search_path TO 'pg_catalog', 'sokhach', 'pg_temp'
AS $function$
DECLARE v_trip bigint;
BEGIN
    IF TG_TABLE_NAME = 'trip' THEN v_trip := NEW.id;
    ELSE v_trip := NEW.trip_id; END IF;
    IF EXISTS (SELECT 1 FROM sokhach.v_trip_current t WHERE t.id=v_trip AND t.event_date IS NULL
        AND NOT (t.container IS NULL OR t.container=''))
       OR EXISTS (SELECT 1 FROM sokhach.v_trip_current t WHERE t.id=v_trip AND t.event_date IS NULL
         AND NOT EXISTS (SELECT 1 FROM sokhach.trip_price_rev p WHERE p.trip_id=t.id))
       OR EXISTS (SELECT 1 FROM sokhach.v_trip_current t JOIN LATERAL
           (SELECT unit_price_vnd,other_fee_vnd FROM sokhach.trip_price_rev
            WHERE trip_id=t.id ORDER BY id DESC LIMIT 1) p ON true
           WHERE t.id=v_trip AND t.event_date IS NULL
             AND (p.unit_price_vnd IS NOT NULL OR p.other_fee_vnd IS NULL))
    THEN RAISE EXCEPTION 'INVALID_FEE_ONLY_DATE'; END IF;
    RETURN NEW;
END $function$;
ALTER FUNCTION sokhach.check_trip_missing_date() OWNER TO sokhach_owner;
REVOKE ALL ON FUNCTION sokhach.check_trip_missing_date() FROM PUBLIC;

-- FUNCTION sokhach.create_book_from_sheet(text,text,text,jsonb,jsonb,jsonb,bigint,text)
CREATE OR REPLACE FUNCTION sokhach.create_book_from_sheet(book_name text, commodity_name text, book_mode text, openings jsonb, legacy jsonb, month_checks jsonb, control_total bigint, report_sha256 text)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'pg_catalog', 'sokhach', 'pg_temp'
AS $function$
DECLARE v_actor text:=sokhach._actor(); v_commodity bigint; v_customer bigint; v_cutover bigint;
BEGIN
 IF book_name IS NULL OR btrim(book_name)='' OR book_name<>btrim(book_name) OR length(book_name)>200
 THEN RAISE EXCEPTION 'INVALID_BOOK_NAME'; END IF;
 IF report_sha256 IS NULL OR report_sha256 !~ '^[0-9a-fA-F]{64}$' OR control_total IS NULL
 THEN RAISE EXCEPTION 'INVALID_CUTOVER_INPUT'; END IF;
 -- Bảng khách không có ràng buộc tên duy nhất: khóa để hai lượt cùng lúc không tạo trùng.
 PERFORM pg_advisory_xact_lock(hashtext('sokhach.create_book_from_sheet'));
 IF EXISTS(SELECT 1 FROM sokhach.customer c WHERE lower(c.name)=lower(book_name))
 THEN RAISE EXCEPTION 'BOOK_EXISTS'; END IF;
 IF commodity_name IS NOT NULL THEN
  INSERT INTO sokhach.commodity(name) VALUES(commodity_name) ON CONFLICT (name) DO NOTHING;
  SELECT m.id INTO v_commodity FROM sokhach.commodity m WHERE m.name=commodity_name;
 END IF;
 INSERT INTO sokhach.customer(name,commodity_id,transport_mode) VALUES(book_name,v_commodity,book_mode)
 RETURNING id INTO v_customer;
 INSERT INTO sokhach.book_fee_column(customer_id,fee_type_id,position)
 SELECT v_customer,f.id,row_number() OVER (ORDER BY f.default_position)
   FROM sokhach.fee_type f WHERE f.default_position IS NOT NULL AND f.active;
 INSERT INTO sokhach.cutover(name,source,source_sha256,frozen_at,control_total_vnd,created_by)
 VALUES('Sổ mới theo Sheet','Sheet, máy tạo sổ (MAY-TAO-SO-01)',report_sha256,now(),control_total,v_actor)
 RETURNING id INTO v_cutover;
 PERFORM sokhach.import_cutover(v_customer,0,'tao-so-import',v_cutover,openings,legacy,month_checks,control_total,report_sha256);
 PERFORM sokhach.verify_cutover_customer(v_customer,v_cutover,1,'tao-so-verify',NULL);
 PERFORM sokhach.verify_cutover(v_cutover,'tao-so-verify-moc',NULL);
 PERFORM sokhach.activate_cutover(v_cutover,'tao-so-activate-moc',NULL);
 PERFORM sokhach.activate_cutover_customer(v_customer,v_cutover,2,'tao-so-activate',NULL);
 INSERT INTO sokhach.baseline_trip_ref(cutover_id,booking_norm,container_norm,event_date)
 SELECT v_cutover,sokhach._booking_key(NULL,l.display->>'container',nullif(l.display->>'date','')::date),
  sokhach._normalize_key(l.display->>'container'),nullif(l.display->>'date','')::date
 FROM sokhach.legacy_row l
 WHERE l.cutover_id=v_cutover AND l.kind='trip' AND sokhach._normalize_key(l.display->>'container')<>'';
 -- paste_trips đòi mốc có tham chiếu; tab không có container thì một dòng đánh dấu, không trùng container thật nào.
 IF NOT FOUND THEN
  INSERT INTO sokhach.baseline_trip_ref(cutover_id,booking_norm,container_norm,event_date)
  VALUES(v_cutover,'SO-MOI','SO-MOI',NULL);
 END IF;
 RETURN jsonb_build_object('customer_id',v_customer,'cutover_id',v_cutover,
  'version',(SELECT c.version FROM sokhach.customer c WHERE c.id=v_customer));
END $function$;
ALTER FUNCTION sokhach.create_book_from_sheet(text,text,text,jsonb,jsonb,jsonb,bigint,text) OWNER TO sokhach_owner;
REVOKE ALL ON FUNCTION sokhach.create_book_from_sheet(text,text,text,jsonb,jsonb,jsonb,bigint,text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION sokhach.create_book_from_sheet(text,text,text,jsonb,jsonb,jsonb,bigint,text) TO sokhach_app;

-- FUNCTION sokhach.create_customer(text,text,text,jsonb,text)
CREATE OR REPLACE FUNCTION sokhach.create_customer(book_name text, commodity_name text, book_mode text, booking_names jsonb, idempotency_key text)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'pg_catalog', 'sokhach', 'pg_temp'
AS $function$
DECLARE v_actor text := sokhach._actor(); v_commodity bigint; v_customer bigint; v_cutover bigint;
 v_month date := date_trunc('month', clock_timestamp() AT TIME ZONE 'Asia/Ho_Chi_Minh')::date;
 v_key text; v_hash text; v_sha text; v_saved sokhach.idempotency%ROWTYPE; v_name text; v_n int := 0; v_result jsonb; v_book_key text;
BEGIN
 IF idempotency_key IS NULL OR btrim(idempotency_key) = '' OR char_length(idempotency_key) > 200 THEN RAISE EXCEPTION 'INVALID_COMMAND'; END IF;
 v_key := 'create_customer:' || idempotency_key;
 v_hash := encode(sha256(convert_to(jsonb_build_object('command','create_customer','book_name',book_name,'commodity_name',commodity_name,
   'book_mode',book_mode,'booking_names',booking_names)::text, 'UTF8')), 'hex');
 PERFORM pg_advisory_xact_lock(hashtext('sokhach.create_book_from_sheet'));
 SELECT * INTO v_saved FROM sokhach.idempotency i WHERE i.key = v_key ORDER BY i.customer_id LIMIT 1;
 IF FOUND THEN
  IF v_saved.request_hash <> v_hash THEN RAISE EXCEPTION 'IDEMPOTENCY_CONFLICT'; END IF;
  RETURN v_saved.result;
 END IF;
 IF book_name IS NULL OR btrim(book_name) = '' OR book_name <> btrim(book_name) OR char_length(book_name) > 200
    OR position('  ' IN book_name) > 0 OR book_name ~ '[[:cntrl:]]' OR book_name ~ U&'[\0080-\009F\00A0\00AD\1680\180E\2000-\200F\2028-\202F\205F-\206F\3000\FEFF]'
    OR book_name <> normalize(book_name, NFC) OR translate(book_name, '/\?*[]:''', '') <> book_name
 THEN RAISE EXCEPTION 'INVALID_BOOK_NAME'; END IF;
 IF book_mode IS NULL OR book_mode NOT IN ('CANG','BO')
    OR (commodity_name IS NOT NULL AND (btrim(commodity_name) = '' OR commodity_name <> btrim(commodity_name) OR length(commodity_name) > 80))
    OR jsonb_typeof(booking_names) IS DISTINCT FROM 'array'
 THEN RAISE EXCEPTION 'INVALID_COMMAND'; END IF;
 -- Tách khỏi điều kiện trên: OR không hứa thứ tự, hàm mảng gặp giá trị không phải mảng thì lỗi.
 IF jsonb_array_length(booking_names) > 20
    OR EXISTS (SELECT 1 FROM jsonb_array_elements(booking_names) x(v) WHERE jsonb_typeof(x.v) <> 'string')
 THEN RAISE EXCEPTION 'INVALID_COMMAND'; END IF;
 IF (SELECT count(DISTINCT x.v) <> count(*) FROM jsonb_array_elements_text(booking_names) x(v))
 THEN RAISE EXCEPTION 'INVALID_COMMAND'; END IF;
 v_book_key := lower(btrim(regexp_replace(translate(normalize(book_name, NFC), '/\?*[]:''', ''), U&'[\0009-\000D\0020\0085\00A0\1680\2000-\200A\2028\2029\202F\205F\3000]+', ' ', 'g')) COLLATE "pg_c_utf8");
 IF EXISTS (SELECT 1 FROM sokhach.customer c WHERE lower(btrim(regexp_replace(translate(normalize(c.name, NFC), '/\?*[]:''', ''), U&'[\0009-\000D\0020\0085\00A0\1680\2000-\200A\2028\2029\202F\205F\3000]+', ' ', 'g')) COLLATE "pg_c_utf8") = v_book_key)
 THEN RAISE EXCEPTION 'BOOK_EXISTS'; END IF;
 IF EXISTS (SELECT 1 FROM sokhach.booking_name b WHERE b.name IN (SELECT jsonb_array_elements_text(booking_names)))
 THEN RAISE EXCEPTION 'BOOKING_NAME_TAKEN'; END IF;
 -- Chỉ mặt hàng có sẵn trong danh mục: gõ tự do thì danh mục thêm nhóm lạ và sổ không bao giờ trùng mặt hàng booking để tự dán.
 IF commodity_name IS NOT NULL THEN
  SELECT m.id INTO v_commodity FROM sokhach.commodity m WHERE m.name = commodity_name;
  IF NOT FOUND THEN RAISE EXCEPTION 'INVALID_COMMODITY'; END IF;
 END IF;
 INSERT INTO sokhach.customer(name, commodity_id, transport_mode) VALUES (book_name, v_commodity, book_mode) RETURNING id INTO v_customer;
 INSERT INTO sokhach.book_fee_column(customer_id, fee_type_id, position)
 SELECT v_customer, f.id, row_number() OVER (ORDER BY f.default_position)
   FROM sokhach.fee_type f WHERE f.default_position IS NOT NULL AND f.active;
 v_sha := encode(sha256(convert_to(v_key, 'UTF8')), 'hex');
 INSERT INTO sokhach.cutover(name, source, source_sha256, frozen_at, control_total_vnd, created_by)
 VALUES ('Sổ mới tạo trên web', 'Web, quản lý tạo sổ (KHACH-WEB-01)', v_sha, now(), 0, v_actor)
 RETURNING id INTO v_cutover;
 PERFORM sokhach.import_cutover(v_customer, 0, 'khach-web-import', v_cutover,
  jsonb_build_array(jsonb_build_object('debt_month', v_month, 'amount_vnd', 0, 'source_tab', 'WEB', 'source_row', 1)), '[]'::jsonb,
  jsonb_build_array(jsonb_build_object('debt_month', v_month, 'opening_anchor_vnd', 0, 'source_cumulative_vnd', 0,
   'replay_cumulative_vnd', 0, 'bucket_vnd', 0, 'standard_bucket_vnd', 0, 'standard_source_ref', 'Khách mới tạo trên web, chưa có nợ',
   'standard_source_sha256', v_sha, 'source_evidence_sha256', v_sha, 'exception_codes', '[]'::jsonb,
   'source_charge_vnd', 0, 'source_receipt_vnd', 0)),
  0, v_sha);
 PERFORM sokhach.verify_cutover_customer(v_customer, v_cutover, 1, 'khach-web-verify', NULL);
 PERFORM sokhach.verify_cutover(v_cutover, 'khach-web-verify-moc', NULL);
 PERFORM sokhach.activate_cutover(v_cutover, 'khach-web-activate-moc', NULL);
 PERFORM sokhach.activate_cutover_customer(v_customer, v_cutover, 2, 'khach-web-activate', NULL);
 -- paste_trips đòi mốc có tham chiếu chuyến; sổ mới không có chuyến cũ nên một dòng đánh dấu, như sổ máy tạo không có container.
 INSERT INTO sokhach.baseline_trip_ref(cutover_id, booking_norm, container_norm, event_date) VALUES (v_cutover, 'SO-MOI', 'SO-MOI', NULL);
 FOR v_name IN SELECT x.v FROM jsonb_array_elements_text(booking_names) WITH ORDINALITY x(v, n) ORDER BY x.n LOOP
  v_n := v_n + 1;
  PERFORM sokhach.set_booking_name(v_customer, (SELECT c.version FROM sokhach.customer c WHERE c.id = v_customer),
   'khach-web-ten-' || v_n, v_name, false);
 END LOOP;
 v_result := jsonb_build_object('customer_id', v_customer, 'cutover_id', v_cutover, 'booking_names', sokhach._booking_names(v_customer),
  'version', (SELECT c.version FROM sokhach.customer c WHERE c.id = v_customer));
 INSERT INTO sokhach.idempotency(customer_id, key, request_hash, result) VALUES (v_customer, v_key, v_hash, v_result);
 RETURN v_result;
END $function$;
ALTER FUNCTION sokhach.create_customer(text,text,text,jsonb,text) OWNER TO sokhach_owner;
REVOKE ALL ON FUNCTION sokhach.create_customer(text,text,text,jsonb,text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION sokhach.create_customer(text,text,text,jsonb,text) TO sokhach_app;

-- FUNCTION sokhach.delete_legacy_trip(bigint,bigint,text,bigint)
CREATE OR REPLACE FUNCTION sokhach.delete_legacy_trip(customer_id bigint, expected_version bigint, idempotency_key text, legacy_row_id bigint)
 RETURNS jsonb
 LANGUAGE sql
 SECURITY DEFINER
 SET search_path TO 'pg_catalog', 'sokhach', 'pg_temp'
AS $function$
    SELECT sokhach._change_legacy(customer_id,expected_version,idempotency_key,legacy_row_id,NULL,NULL,true)
$function$;
ALTER FUNCTION sokhach.delete_legacy_trip(bigint,bigint,text,bigint) OWNER TO sokhach_owner;
REVOKE ALL ON FUNCTION sokhach.delete_legacy_trip(bigint,bigint,text,bigint) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION sokhach.delete_legacy_trip(bigint,bigint,text,bigint) TO sokhach_app;

-- FUNCTION sokhach.delete_month_adjustment(bigint,bigint,text,bigint)
CREATE OR REPLACE FUNCTION sokhach.delete_month_adjustment(customer_id bigint, expected_version bigint, idempotency_key text, adjustment_id bigint)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'pg_catalog', 'sokhach', 'pg_temp'
AS $function$
DECLARE v_payload jsonb := jsonb_build_object('command','delete_month_adjustment','adjustment_id',adjustment_id);
        v_retry jsonb; a sokhach.adjustment%ROWTYPE; v_id bigint; v_event bigint; v_changes jsonb;
BEGIN
    v_retry := sokhach._begin_command(customer_id,expected_version,idempotency_key,v_payload);
    IF v_retry IS NOT NULL THEN RETURN v_retry; END IF;
    PERFORM sokhach._baseline(customer_id);
    SELECT a0.* INTO a FROM sokhach.adjustment a0
    WHERE a0.id=delete_month_adjustment.adjustment_id AND a0.customer_id=delete_month_adjustment.customer_id
      AND a0.trip_id IS NULL AND a0.legacy_row_id IS NULL AND a0.field IS NULL AND NOT a0.fee_absorbed
      AND a0.reverses_adjustment_id IS NULL
      AND NOT EXISTS (SELECT 1 FROM sokhach.adjustment r WHERE r.reverses_adjustment_id=a0.id);
    IF NOT FOUND THEN RAISE EXCEPTION 'ADJUSTMENT_NOT_FOUND'; END IF;
    PERFORM sokhach._month_open(customer_id,a.debt_month,clock_timestamp());
    v_id := nextval(pg_get_serial_sequence('sokhach.adjustment','id'));
    INSERT INTO sokhach.event(customer_id,kind,actor,"before","after",idempotency_key)
    VALUES (customer_id,'adjust_month_delete',sokhach._actor(),
        jsonb_build_object('adjustment',jsonb_build_object('id',a.id,'month',a.debt_month,
            'amount_vnd',a.amount_vnd::text,'note',a.note,'actor',a.actor,'at',a.at)),
        jsonb_build_object('adjustment',jsonb_build_object('id',a.id,'month',a.debt_month,
            'amount_vnd','0','deleted',true,'reversal',v_id)),idempotency_key)
    RETURNING id INTO v_event;
    INSERT INTO sokhach.adjustment(id,customer_id,debt_month,trip_id,amount_vnd,note,actor,created_by_event,reverses_adjustment_id)
    OVERRIDING SYSTEM VALUE VALUES (v_id,customer_id,a.debt_month,NULL,-a.amount_vnd,a.note,sokhach._actor(),v_event,a.id);
    v_changes := sokhach.reallocate(customer_id,idempotency_key);
    RETURN sokhach._finish_command(customer_id,idempotency_key,v_payload,
        jsonb_build_object('adjustment_id',a.id,'reversal_id',v_id,'reallocated',v_changes));
END $function$;
ALTER FUNCTION sokhach.delete_month_adjustment(bigint,bigint,text,bigint) OWNER TO sokhach_owner;
REVOKE ALL ON FUNCTION sokhach.delete_month_adjustment(bigint,bigint,text,bigint) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION sokhach.delete_month_adjustment(bigint,bigint,text,bigint) TO sokhach_app;

-- FUNCTION sokhach.delete_trip(bigint,bigint,text,bigint)
CREATE OR REPLACE FUNCTION sokhach.delete_trip(customer_id bigint, expected_version bigint, idempotency_key text, trip_id bigint)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'pg_catalog', 'sokhach', 'pg_temp'
AS $function$
DECLARE v_payload jsonb:=jsonb_build_object('command','delete_trip','trip_id',trip_id);
    v_retry jsonb; t sokhach.v_trip_current%ROWTYPE; v_price jsonb; v_event bigint; v_changes jsonb;
BEGIN
    v_retry:=sokhach._begin_command(customer_id,expected_version,idempotency_key,v_payload);
    IF v_retry IS NOT NULL THEN RETURN v_retry; END IF;
    PERFORM sokhach._baseline(customer_id);
    SELECT * INTO t FROM sokhach.v_trip_current v WHERE v.id=trip_id AND v.customer_id=delete_trip.customer_id AND NOT v.deleted;
    IF NOT FOUND THEN RAISE EXCEPTION 'TRIP_NOT_FOUND'; END IF;
    PERFORM sokhach._month_open(customer_id,t.debt_month,clock_timestamp());
    -- Snapshot shows the effective fee: latest price revision plus every fee delta,
    -- including deltas older than the revision (a price edit never absorbs them).
    SELECT jsonb_build_object('unit_price_vnd',CASE WHEN p.unit_price_vnd IS NOT NULL
          THEN (a.amount_vnd-f.fee)::text END,
      'other_fee_vnd',f.fee_display::text,
      'amount_vnd',CASE WHEN t.status='confirmed' THEN a.amount_vnd::text END)
    INTO v_price FROM (SELECT * FROM sokhach.trip_price_rev WHERE trip_price_rev.trip_id=t.id ORDER BY id DESC LIMIT 1) p
    LEFT JOIN LATERAL (SELECT coalesce(p.other_fee_vnd,0)
        +coalesce((SELECT sum(x.amount_vnd) FROM sokhach.adjustment x WHERE x.trip_id=t.id AND x.field='other_fee_vnd' AND NOT x.fee_absorbed),0) AS fee,
        CASE WHEN p.other_fee_vnd IS NULL
          AND NOT EXISTS (SELECT 1 FROM sokhach.adjustment x WHERE x.trip_id=t.id AND x.field='other_fee_vnd' AND NOT x.fee_absorbed)
        THEN NULL ELSE coalesce(p.other_fee_vnd,0)
          +coalesce((SELECT sum(x.amount_vnd) FROM sokhach.adjustment x WHERE x.trip_id=t.id AND x.field='other_fee_vnd' AND NOT x.fee_absorbed),0) END AS fee_display) f ON true
    CROSS JOIN LATERAL (SELECT (CASE WHEN p.unit_price_vnd IS NOT NULL THEN p.unit_price_vnd+coalesce(p.other_fee_vnd,0)
        WHEN coalesce(t.container,'')='' THEN p.other_fee_vnd END)
        +coalesce((SELECT sum(x.amount_vnd) FROM sokhach.adjustment x WHERE x.trip_id=t.id AND NOT x.fee_absorbed),0) AS amount_vnd) a;
    INSERT INTO sokhach.event(customer_id,kind,actor,"before","after",idempotency_key)
      VALUES(customer_id,'trip_delete',sokhach._actor(),jsonb_build_object('trip',to_jsonb(t)||coalesce(v_price,'{}')||jsonb_build_object('fee_lines',sokhach._fee_lines(t.id,NULL))),
        jsonb_build_object('trip',jsonb_build_object('id',t.id,'deleted',true)),idempotency_key) RETURNING id INTO v_event;
    INSERT INTO sokhach.trip_info_rev(trip_id,customer_id,debt_month,event_date,container,carrier,shipper,origin,destination,status,deleted,created_by_event)
      VALUES(t.id,customer_id,t.debt_month,t.event_date,t.container,t.carrier,t.shipper,t.origin,t.destination,t.status,true,v_event);
    v_changes:=sokhach.reallocate(customer_id,idempotency_key);
    RETURN sokhach._finish_command(customer_id,idempotency_key,v_payload,jsonb_build_object('trip_id',t.id,'deleted',true,'reallocated',v_changes));
END $function$;
ALTER FUNCTION sokhach.delete_trip(bigint,bigint,text,bigint) OWNER TO sokhach_owner;
REVOKE ALL ON FUNCTION sokhach.delete_trip(bigint,bigint,text,bigint) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION sokhach.delete_trip(bigint,bigint,text,bigint) TO sokhach_app;

-- FUNCTION sokhach.edit_legacy_trip(bigint,bigint,text,bigint,text,text)
CREATE OR REPLACE FUNCTION sokhach.edit_legacy_trip(customer_id bigint, expected_version bigint, idempotency_key text, legacy_row_id bigint, field text, value text)
 RETURNS jsonb
 LANGUAGE sql
 SECURITY DEFINER
 SET search_path TO 'pg_catalog', 'sokhach', 'pg_temp'
AS $function$
    SELECT sokhach._change_legacy(customer_id,expected_version,idempotency_key,legacy_row_id,field,value,false)
$function$;
ALTER FUNCTION sokhach.edit_legacy_trip(bigint,bigint,text,bigint,text,text) OWNER TO sokhach_owner;
REVOKE ALL ON FUNCTION sokhach.edit_legacy_trip(bigint,bigint,text,bigint,text,text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION sokhach.edit_legacy_trip(bigint,bigint,text,bigint,text,text) TO sokhach_app;

-- FUNCTION sokhach.edit_offset_date(bigint,bigint,bigint,text,bigint,date)
CREATE OR REPLACE FUNCTION sokhach.edit_offset_date(customer_id bigint, expected_version bigint, other_version bigint, idempotency_key text, offset_pair_id bigint, date date)
 RETURNS jsonb
 LANGUAGE sql
 SECURITY DEFINER
 SET search_path TO 'pg_catalog', 'sokhach', 'pg_temp'
AS $function$
    SELECT sokhach._change_offset(customer_id,expected_version,other_version,idempotency_key,
        offset_pair_id,date,NULL,false)
$function$;
ALTER FUNCTION sokhach.edit_offset_date(bigint,bigint,bigint,text,bigint,date) OWNER TO sokhach_owner;
REVOKE ALL ON FUNCTION sokhach.edit_offset_date(bigint,bigint,bigint,text,bigint,date) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION sokhach.edit_offset_date(bigint,bigint,bigint,text,bigint,date) TO sokhach_app;

-- FUNCTION sokhach.edit_receipt_meta(bigint,bigint,text,text,date,text,text)
CREATE OR REPLACE FUNCTION sokhach.edit_receipt_meta(customer_id bigint, expected_version bigint, idempotency_key text, pid text, date date, method text, reference text DEFAULT NULL::text)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'pg_catalog', 'sokhach', 'pg_temp'
AS $function$
DECLARE v_payload jsonb := jsonb_build_object('command','edit_receipt_meta','pid',pid,
        'date',date,'method',method)
        || CASE WHEN reference IS NULL THEN '{}'::jsonb ELSE jsonb_build_object('reference',reference) END;
        v_retry jsonb; v_receipt sokhach.receipt%ROWTYPE; v_date date; v_method text; v_reference text;
        v_event bigint; v_changes jsonb := '[]'::jsonb; v_before jsonb;
BEGIN
    IF (date IS NOT NULL OR method IS NOT NULL OR reference IS NULL) AND EXISTS (
        SELECT 1 FROM sokhach.offset_pair p JOIN sokhach.receipt r ON r.id=p.target_receipt_id
        WHERE r.customer_id=edit_receipt_meta.customer_id AND r.pid=edit_receipt_meta.pid)
    THEN RAISE EXCEPTION 'OFFSET_PAIR_REQUIRED'; END IF;
    v_retry := sokhach._begin_command(customer_id,expected_version,idempotency_key,v_payload);
    IF v_retry IS NOT NULL THEN RETURN v_retry; END IF;
    PERFORM sokhach._baseline(customer_id);
    SELECT * INTO v_receipt FROM sokhach.receipt
     WHERE receipt.customer_id=edit_receipt_meta.customer_id AND receipt.pid=edit_receipt_meta.pid;
    IF NOT FOUND OR v_receipt.voided_on IS NOT NULL THEN RAISE EXCEPTION 'RECEIPT_NOT_FOUND'; END IF;
    v_date := coalesce(date,v_receipt.date);
    IF v_date > (clock_timestamp() AT TIME ZONE 'Asia/Ho_Chi_Minh')::date
       THEN RAISE EXCEPTION 'FUTURE_RECEIPT_DATE'; END IF;
    v_method := coalesce(method,v_receipt.method);
    IF v_method NOT IN ('THU TIỀN','CẤN TRỪ','ỨNG TRƯỚC','KHÁC')
       THEN RAISE EXCEPTION 'INVALID_METHOD'; END IF;
    v_reference := CASE WHEN reference IS NULL THEN v_receipt.reference ELSE nullif(btrim(reference),'') END;
    IF (v_date,v_method,v_reference) IS NOT DISTINCT FROM (v_receipt.date,v_receipt.method,v_receipt.reference)
       THEN RAISE EXCEPTION 'NO_CHANGE'; END IF;
    v_before := sokhach._lines(v_receipt.id);
    INSERT INTO sokhach.event(customer_id,kind,actor,"before","after",idempotency_key)
    VALUES (customer_id,'receipt_edit',sokhach._actor(),
        jsonb_build_object('receipt',v_receipt.id,'pid',pid,'date',v_receipt.date,
            'method',v_receipt.method,'reference',v_receipt.reference,'allocations',v_before),
        jsonb_build_object('receipt',v_receipt.id,'pid',pid,'date',v_date,
            'method',v_method,'reference',v_reference,'allocations',v_before),idempotency_key)
    RETURNING id INTO v_event;
    UPDATE sokhach.receipt SET date=v_date,method=v_method,reference=v_reference,meta_changed_by_event=v_event
    WHERE id=v_receipt.id;
    IF v_date IS DISTINCT FROM v_receipt.date THEN
        v_changes := sokhach.reallocate(customer_id,idempotency_key);
    ELSE
        PERFORM sokhach._check_allocations(customer_id);
    END IF;
    RETURN sokhach._finish_command(customer_id,idempotency_key,v_payload,
        jsonb_build_object('receipt_id',v_receipt.id,'pid',pid,'reallocated',v_changes,
            'duplicate_reference',EXISTS (SELECT 1 FROM sokhach.receipt r
                WHERE r.customer_id=edit_receipt_meta.customer_id AND r.id<>v_receipt.id
                  AND r.reference=v_reference)));
END $function$;
ALTER FUNCTION sokhach.edit_receipt_meta(bigint,bigint,text,text,date,text,text) OWNER TO sokhach_owner;
REVOKE ALL ON FUNCTION sokhach.edit_receipt_meta(bigint,bigint,text,text,date,text,text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION sokhach.edit_receipt_meta(bigint,bigint,text,text,date,text,text) TO sokhach_app;

-- FUNCTION sokhach.edit_trip_info(bigint,bigint,text,bigint,text,text)
CREATE OR REPLACE FUNCTION sokhach.edit_trip_info(customer_id bigint, expected_version bigint, idempotency_key text, trip_id bigint, field text, value text)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'pg_catalog', 'sokhach', 'pg_temp'
AS $function$
DECLARE v_payload jsonb := jsonb_build_object('command','edit_trip_info','trip_id',trip_id,'field',field,'value',value);
    v_retry jsonb; t sokhach.v_trip_current%ROWTYPE; v_before jsonb; v_after jsonb;
    v_value text; v_date date; v_event bigint; v_changes jsonb; v_cutover bigint; v_reason text;
    v_booking text; v_container text;
BEGIN
    v_retry := sokhach._begin_command(customer_id,expected_version,idempotency_key,v_payload);
    IF v_retry IS NOT NULL THEN RETURN v_retry; END IF;
    PERFORM sokhach._baseline(customer_id);
    IF field IS NULL OR field NOT IN ('container','carrier','shipper','origin','destination','event_date') THEN RAISE EXCEPTION 'INVALID_FIELD'; END IF;
    SELECT * INTO t FROM sokhach.v_trip_current v WHERE v.id=trip_id AND v.customer_id=edit_trip_info.customer_id AND NOT v.deleted;
    IF NOT FOUND THEN RAISE EXCEPTION 'TRIP_NOT_FOUND'; END IF;
    -- KHOA-CHU-01 (1/11/2026): bốn ô chữ mô tả sửa được cả ở tháng khóa; container và ngày vẫn theo khóa tháng.
    IF field NOT IN ('carrier','shipper','origin','destination') THEN
      PERFORM sokhach._month_open(customer_id,t.debt_month,clock_timestamp());
    END IF;
    v_value := nullif(btrim(value),'');
    IF field='container' THEN v_value := nullif(sokhach._normalize_key(value),''); END IF;
    IF field='event_date' THEN v_date := sokhach._trip_date(value); v_value := v_date::text;
    ELSIF v_value IS NULL AND field<>'shipper' AND (coalesce(t.container,'')<>'' OR field='container' AND t.container IS NOT NULL)
    THEN RAISE EXCEPTION 'INVALID_TRIP_INPUT'; END IF;
    -- KIEM-TAB-01 (K4): chuỗi rỗng và NULL là cùng một giá trị "chưa có" ở ô chữ, nên không phải thay đổi.
    IF nullif(btrim(to_jsonb(t)->>field),'') IS NOT DISTINCT FROM v_value THEN RAISE EXCEPTION 'NO_CHANGE'; END IF;
    v_before := jsonb_build_object('id',t.id,'field',field,'value',to_jsonb(t)->field,'debt_month',t.debt_month,'status',t.status);
    CASE field WHEN 'container' THEN t.container:=v_value; WHEN 'carrier' THEN t.carrier:=v_value; WHEN 'shipper' THEN t.shipper:=v_value;
      WHEN 'origin' THEN t.origin:=v_value; WHEN 'destination' THEN t.destination:=v_value;
      WHEN 'event_date' THEN t.event_date:=v_date; t.debt_month:=date_trunc('month',v_date)::date; END CASE;
    IF t.debt_month<>(v_before->>'debt_month')::date THEN
      PERFORM sokhach._month_open(customer_id,t.debt_month,clock_timestamp()); END IF;
    -- Converting a fee-only row to a container trip must satisfy normal trip inputs.
    IF coalesce(t.container,'')<>'' AND (t.event_date IS NULL OR nullif(btrim(t.carrier),'') IS NULL
       OR nullif(btrim(t.origin),'') IS NULL OR nullif(btrim(t.destination),'') IS NULL)
    THEN RAISE EXCEPTION 'INVALID_TRIP_INPUT'; END IF;
    IF t.status='confirmed' AND field IN ('container','event_date') AND coalesce(t.container,'')<>'' THEN
      SELECT cc.cutover_id INTO v_cutover FROM sokhach.cutover_customer cc JOIN sokhach.cutover c ON c.id=cc.cutover_id
        WHERE cc.customer_id=edit_trip_info.customer_id AND cc.status='active' AND c.status='active';
      IF NOT EXISTS(SELECT FROM sokhach.baseline_trip_ref WHERE cutover_id=v_cutover) THEN RAISE EXCEPTION 'BASELINE_REF_MISSING'; END IF;
      v_container:=sokhach._normalize_key(t.container); v_booking:=sokhach._booking_key(t.booking,t.container,t.event_date);
      -- Audit 19/11/2026 (A12), 23/11/2026 (F8): cùng một hàm tính lý do như paste_trips, trừ chính chuyến đang sửa.
      v_reason:=sokhach._trip_dup_reason(edit_trip_info.customer_id,v_cutover,v_container,v_booking,t.event_date,t.id,NULL);
      IF v_reason IS NOT NULL THEN t.status:='pending_review'; END IF;
    END IF;
    v_after:=jsonb_build_object('trip',jsonb_build_object('id',t.id,'field',field,'value',v_value,'debt_month',t.debt_month,'status',t.status));
    IF t.debt_month<>(v_before->>'debt_month')::date THEN
      v_after:=v_after||jsonb_build_object('moved_from_month',v_before->'debt_month','moved_to_month',t.debt_month); END IF;
    IF v_reason IS NOT NULL THEN v_after:=v_after||jsonb_build_object('review_reason',v_reason); END IF;
    INSERT INTO sokhach.event(customer_id,kind,actor,"before","after",idempotency_key)
      VALUES(customer_id,'trip_edit',sokhach._actor(),jsonb_build_object('trip',v_before),v_after,idempotency_key) RETURNING id INTO v_event;
    INSERT INTO sokhach.trip_info_rev(trip_id,customer_id,debt_month,event_date,container,carrier,shipper,origin,destination,status,created_by_event)
      VALUES(t.id,customer_id,t.debt_month,t.event_date,t.container,t.carrier,t.shipper,t.origin,t.destination,t.status,v_event);
    v_changes:=sokhach.reallocate(customer_id,idempotency_key);
    RETURN sokhach._finish_command(customer_id,idempotency_key,v_payload,jsonb_build_object('trip_id',t.id,'pending_review',t.status='pending_review','reason',v_reason,'reallocated',v_changes));
END $function$;
ALTER FUNCTION sokhach.edit_trip_info(bigint,bigint,text,bigint,text,text) OWNER TO sokhach_owner;
REVOKE ALL ON FUNCTION sokhach.edit_trip_info(bigint,bigint,text,bigint,text,text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION sokhach.edit_trip_info(bigint,bigint,text,bigint,text,text) TO sokhach_app;

-- FUNCTION sokhach.edit_trip_price(bigint,bigint,text,bigint,bigint,bigint)
CREATE OR REPLACE FUNCTION sokhach.edit_trip_price(customer_id bigint, expected_version bigint, idempotency_key text, trip_id bigint, unit_price_vnd bigint, other_fee_vnd bigint)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'pg_catalog', 'sokhach', 'pg_temp'
AS $function$
DECLARE v_payload jsonb := jsonb_build_object('command','edit_trip_price','trip_id',trip_id,
        'unit_price_vnd',unit_price_vnd,'other_fee_vnd',other_fee_vnd);
        v_retry jsonb; v_trip sokhach.v_trip_current%ROWTYPE; v_old sokhach.trip_price_rev%ROWTYPE;
        v_now timestamptz; v_event bigint; v_rev bigint; v_changes jsonb;
BEGIN
    v_retry := sokhach._begin_command(customer_id,expected_version,idempotency_key,v_payload);
    IF v_retry IS NOT NULL THEN RETURN v_retry; END IF;
    PERFORM sokhach._baseline(customer_id);
    v_now := clock_timestamp();
    SELECT * INTO v_trip FROM sokhach.v_trip_current v WHERE v.id=trip_id AND v.customer_id=edit_trip_price.customer_id AND NOT v.deleted;
    IF NOT FOUND THEN RAISE EXCEPTION 'TRIP_NOT_FOUND'; END IF;
    IF v_trip.status<>'confirmed' THEN RAISE EXCEPTION 'TRIP_PENDING_REVIEW'; END IF;
    PERFORM sokhach._month_open(customer_id,v_trip.debt_month,v_now);
    IF unit_price_vnd < 0 OR
       coalesce(unit_price_vnd,0)::numeric+coalesce(other_fee_vnd,0)::numeric NOT BETWEEN -9223372036854775808 AND 9223372036854775807
    THEN RAISE EXCEPTION 'INVALID_VND'; END IF;
    SELECT * INTO v_old FROM sokhach.trip_price_rev WHERE trip_price_rev.trip_id=edit_trip_price.trip_id
        ORDER BY id DESC LIMIT 1;
    IF (v_old.unit_price_vnd,v_old.other_fee_vnd) IS NOT DISTINCT FROM
       (unit_price_vnd,other_fee_vnd) THEN RAISE EXCEPTION 'NO_CHANGE'; END IF;
    v_rev := nextval(pg_get_serial_sequence('sokhach.trip_price_rev','id'));
    INSERT INTO sokhach.event(customer_id,kind,actor,"before","after",idempotency_key)
    VALUES (customer_id,'price_edit',sokhach._actor(),
        jsonb_build_object('price',jsonb_build_object('trip_id',trip_id,'revision_id',v_old.id,
            'unit_price_vnd',v_old.unit_price_vnd,'other_fee_vnd',v_old.other_fee_vnd)),
        jsonb_build_object('price',jsonb_build_object('trip_id',trip_id,
            'unit_price_vnd',unit_price_vnd,'other_fee_vnd',other_fee_vnd)),idempotency_key)
    RETURNING id INTO v_event;
    INSERT INTO sokhach.trip_price_rev(id,trip_id,customer_id,unit_price_vnd,created_by_event)
    OVERRIDING SYSTEM VALUE VALUES (v_rev,trip_id,customer_id,unit_price_vnd,v_event);
    PERFORM sokhach._compat_trip_fee(customer_id,trip_id,other_fee_vnd,v_event);
    SELECT p.id INTO v_rev FROM sokhach.trip_price_rev p WHERE p.trip_id=edit_trip_price.trip_id ORDER BY p.id DESC LIMIT 1;
    v_changes := sokhach.reallocate(customer_id,idempotency_key);
    RETURN sokhach._finish_command(customer_id,idempotency_key,v_payload,
        jsonb_build_object('trip_id',trip_id,'revision_id',v_rev,'reallocated',v_changes));
END $function$;
ALTER FUNCTION sokhach.edit_trip_price(bigint,bigint,text,bigint,bigint,bigint) OWNER TO sokhach_owner;
REVOKE ALL ON FUNCTION sokhach.edit_trip_price(bigint,bigint,text,bigint,bigint,bigint) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION sokhach.edit_trip_price(bigint,bigint,text,bigint,bigint,bigint) TO sokhach_app;

-- FUNCTION sokhach.find_container(text)
CREATE OR REPLACE FUNCTION sokhach.find_container(p_query text)
 RETURNS jsonb
 LANGUAGE plpgsql
 STABLE SECURITY DEFINER
 SET search_path TO 'pg_catalog', 'sokhach', 'pg_temp'
AS $function$
-- TIM-CONT-01. Chuyến có số cont chứa chuỗi tìm (bỏ khoảng trắng, không phân biệt hoa thường), ở mọi sổ đang hoạt động: chuyến web
-- chưa xóa, không bị loại (cả chuyến chờ kiểm); dòng chuyến sổ gốc theo bản sửa mới nhất, chưa xóa. Lọc ứng viên theo cont của bản
-- gốc hoặc của bất kỳ bản sửa nào, rồi mới đọc bản hiện hành và lọc lại. Trùng khớp nguyên số trước, rồi ngày chuyến mới trước;
-- trả tối đa 30 dòng và cờ more khi còn nữa. Chỉ đọc.
DECLARE v_key text := sokhach._normalize_key(p_query); v_limit int := 30;
BEGIN
  PERFORM sokhach._actor();
  IF length(v_key) < 4 OR length(v_key) > 20 THEN RAISE EXCEPTION 'INVALID_QUERY'; END IF;
  RETURN (WITH act AS (
      SELECT c.id,cc.cutover_id FROM sokhach.customer c
        JOIN sokhach.cutover_customer cc ON cc.customer_id=c.id AND cc.status='active'
        JOIN sokhach.cutover x ON x.id=cc.cutover_id AND x.status='active'
       WHERE NOT c.archived),
    web_cand AS (SELECT t.id FROM sokhach.trip t WHERE strpos(sokhach._normalize_key(t.container),v_key)>0
        UNION SELECT r.trip_id FROM sokhach.trip_info_rev r WHERE strpos(sokhach._normalize_key(r.container),v_key)>0),
    web AS (SELECT t.customer_id,t.debt_month,t.event_date AS dt,t.container AS cont,t.origin,t.destination,
            CASE WHEN t.status='confirmed' THEN 'web' ELSE 'pending' END AS src
        FROM web_cand w JOIN sokhach.v_trip_current t ON t.id=w.id JOIN act ON act.id=t.customer_id
       WHERE NOT t.deleted AND t.status<>'rejected'),
    leg_cand AS (SELECT l.id FROM sokhach.legacy_row l
        WHERE l.kind='trip' AND strpos(sokhach._normalize_key(l.display->>'container'),v_key)>0
        UNION SELECT y.legacy_row_id FROM sokhach.legacy_trip_rev y WHERE strpos(sokhach._normalize_key(y.container),v_key)>0),
    leg AS (SELECT l.customer_id,coalesce(r.debt_month,l.debt_month) AS debt_month,
            CASE WHEN r.id IS NULL THEN sokhach._legacy_date(l.display->>'date') ELSE r.event_date END AS dt,
            CASE WHEN r.id IS NULL THEN l.display->>'container' ELSE r.container END AS cont,
            CASE WHEN r.id IS NULL THEN l.display->>'from' ELSE r.origin END AS origin,
            CASE WHEN r.id IS NULL THEN l.display->>'to' ELSE r.destination END AS destination,'legacy'::text AS src
        FROM leg_cand c JOIN sokhach.legacy_row l ON l.id=c.id AND l.kind='trip'
        JOIN act ON (act.id,act.cutover_id)=(l.customer_id,l.cutover_id)
        LEFT JOIN LATERAL (SELECT x.id,x.debt_month,x.event_date,x.container,x.origin,x.destination,x.deleted
            FROM sokhach.legacy_trip_rev x WHERE x.legacy_row_id=l.id ORDER BY x.id DESC LIMIT 1) r ON true
       WHERE NOT coalesce(r.deleted,false)),
    hit AS (SELECT *,sokhach._normalize_key(cont)=v_key AS exact FROM (SELECT * FROM web UNION ALL SELECT * FROM leg) a
       WHERE strpos(sokhach._normalize_key(cont),v_key)>0),
    top AS (SELECT * FROM hit ORDER BY exact DESC,dt DESC NULLS LAST,debt_month DESC,customer_id,cont LIMIT v_limit)
  SELECT jsonb_build_object('query',v_key,'more',(SELECT count(*) FROM hit)>v_limit,
    'items',(SELECT coalesce(jsonb_agg(jsonb_build_object('customer_id',t.customer_id,'debt_month',t.debt_month,'date',t.dt,
        'container',t.cont,'origin',t.origin,'destination',t.destination,'source',t.src)
        ORDER BY t.exact DESC,t.dt DESC NULLS LAST,t.debt_month DESC,t.customer_id,t.cont),'[]'::jsonb) FROM top t)));
END $function$;
ALTER FUNCTION sokhach.find_container(text) OWNER TO sokhach_owner;
REVOKE ALL ON FUNCTION sokhach.find_container(text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION sokhach.find_container(text) TO sokhach_app;
GRANT EXECUTE ON FUNCTION sokhach.find_container(text) TO sokhach_reader;

-- FUNCTION sokhach.find_receipt_image(text)
CREATE OR REPLACE FUNCTION sokhach.find_receipt_image(sha256 text)
 RETURNS jsonb
 LANGUAGE plpgsql
 STABLE SECURITY DEFINER
 SET search_path TO 'pg_catalog', 'sokhach', 'pg_temp'
AS $function$
BEGIN
 IF find_receipt_image.sha256 IS NULL OR find_receipt_image.sha256 !~ '^[0-9a-f]{64}$' THEN RAISE EXCEPTION 'IMAGE_INVALID'; END IF;
 RETURN jsonb_build_object('matches',sokhach._receipt_image_matches(find_receipt_image.sha256,NULL));
END $function$;
ALTER FUNCTION sokhach.find_receipt_image(text) OWNER TO sokhach_owner;
REVOKE ALL ON FUNCTION sokhach.find_receipt_image(text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION sokhach.find_receipt_image(text) TO sokhach_app;
GRANT EXECUTE ON FUNCTION sokhach.find_receipt_image(text) TO sokhach_reader;

-- FUNCTION sokhach.get_activity(date)
CREATE OR REPLACE FUNCTION sokhach.get_activity(p_day date)
 RETURNS jsonb
 LANGUAGE plpgsql
 STABLE SECURITY DEFINER
 SET search_path TO 'pg_catalog', 'sokhach', 'pg_temp'
AS $function$
-- Ngày theo giờ VN. Mỗi event cùng hình dạng với Lịch sử của sổ (_ledger_events) để giao diện dùng chung câu chữ, thêm tên sổ.
-- Lô dán chỉ giữ các ô giao diện đọc. Kèm container của chuyến/dòng sổ gốc và số phiếu mà event nhắc tới bằng id (mọi số nguyên
-- trong trước/sau, lọc theo sổ của event), để câu "Sửa giá chuyến X" không phải mở từng sổ. prev_day/next_day: ngày gần nhất có việc.
DECLARE d date := (now() AT TIME ZONE 'Asia/Ho_Chi_Minh')::date; v_day date := coalesce(p_day, d);
        v_from timestamptz; v_to timestamptz;
BEGIN
  PERFORM sokhach._actor();
  IF v_day > d THEN RAISE EXCEPTION 'INVALID_DAY'; END IF;
  v_from := v_day::timestamp AT TIME ZONE 'Asia/Ho_Chi_Minh';
  v_to := (v_day + 1)::timestamp AT TIME ZONE 'Asia/Ho_Chi_Minh';
  RETURN (WITH ev AS (
      SELECT e.id,e.customer_id,e.kind,e.actor,e.at,e."before",
        CASE WHEN e.kind='paste' THEN jsonb_build_object('trips',(SELECT coalesce(jsonb_agg(jsonb_strip_nulls(jsonb_build_object(
            'trip_id',t->'trip_id','container',t->'container','event_date',t->'event_date','date',t->'date',
            'unitPriceVnd',t->'unitPriceVnd','status',t->'status','note',t->'note')) ORDER BY n),'[]'::jsonb)
            FROM jsonb_array_elements(e."after"->'trips') WITH ORDINALITY x(t,n))) ELSE e."after" END AS "after"
        FROM sokhach.event e WHERE e.at>=v_from AND e.at<v_to),
    ids AS (
      SELECT DISTINCT ev.customer_id,(v #>> '{}')::bigint AS id
        FROM ev CROSS JOIN LATERAL jsonb_path_query(jsonb_build_array(ev."before",ev."after"),'strict $.** ? (@.type() == "number")') v
       WHERE (v #>> '{}') ~ '^[0-9]{1,18}$'),
    total AS (SELECT count(*) AS n FROM ev),
    shown AS (SELECT * FROM ev ORDER BY at DESC,id DESC LIMIT 2000)
    SELECT jsonb_build_object('day',v_day,'today',d,
      'prev_day',(SELECT (max(e.at) AT TIME ZONE 'Asia/Ho_Chi_Minh')::date FROM sokhach.event e WHERE e.at<v_from),
      'next_day',(SELECT (min(e.at) AT TIME ZONE 'Asia/Ho_Chi_Minh')::date FROM sokhach.event e WHERE e.at>=v_to),
      'total',(SELECT n FROM total),
      'events',(SELECT coalesce(jsonb_agg(jsonb_build_object('id',s.id,'customer_id',s.customer_id,'customer',c.name,
          'kind',s.kind,'actor',s.actor,'at',s.at,
          'counterparty_name',(SELECT o.name FROM sokhach.offset_pair p JOIN sokhach.customer o
              ON o.id=CASE WHEN p.source_customer_id=s.customer_id THEN p.target_customer_id ELSE p.source_customer_id END
              WHERE (p.source_customer_id=s.customer_id AND p.source_pid=s."after"->>'receipt')
                 OR (p.target_customer_id=s.customer_id AND p.target_receipt_id::text=s."after"->>'receipt')),
          'before',CASE WHEN s.kind='price_edit' THEN s."before" || jsonb_build_object('price',s."before"->'price' || jsonb_build_object(
              'unit_price_vnd',s."before"->'price'->>'unit_price_vnd','other_fee_vnd',s."before"->'price'->>'other_fee_vnd')) ELSE s."before" END,
          'after',CASE WHEN s.kind='price_edit' THEN s."after" || jsonb_build_object('price',s."after"->'price' || jsonb_build_object(
              'unit_price_vnd',s."after"->'price'->>'unit_price_vnd','other_fee_vnd',s."after"->'price'->>'other_fee_vnd')) ELSE s."after" END)
          ORDER BY s.at DESC,s.id DESC),'[]'::jsonb) FROM shown s JOIN sokhach.customer c ON c.id=s.customer_id),
      'trips',(SELECT coalesce(jsonb_agg(jsonb_build_object('id',t.id,'container',t.container) ORDER BY t.id),'[]'::jsonb)
        FROM sokhach.trip t JOIN ids ON (ids.customer_id,ids.id)=(t.customer_id,t.id)),
      'legacy_rows',(SELECT coalesce(jsonb_agg(jsonb_build_object('id',l.id,'current',jsonb_build_object('container',
          coalesce(sokhach._legacy_current(l.id)->>'container',l.display->>'container'))) ORDER BY l.id),'[]'::jsonb)
        FROM sokhach.legacy_row l JOIN ids ON (ids.customer_id,ids.id)=(l.customer_id,l.id)),
      'receipts',(SELECT coalesce(jsonb_agg(jsonb_build_object('id',r.id,'pid',r.pid,'date',r.date) ORDER BY r.id),'[]'::jsonb)
        FROM sokhach.receipt r JOIN ids ON (ids.customer_id,ids.id)=(r.customer_id,r.id)),
      'fee_types',(SELECT coalesce(jsonb_agg(jsonb_build_object('id',f.id,'name',f.name) ORDER BY f.sort,f.id),'[]'::jsonb)
        FROM sokhach.fee_type f)));
END $function$;
ALTER FUNCTION sokhach.get_activity(date) OWNER TO sokhach_owner;
REVOKE ALL ON FUNCTION sokhach.get_activity(date) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION sokhach.get_activity(date) TO sokhach_app;

-- FUNCTION sokhach.get_cash_reviews(jsonb)
CREATE OR REPLACE FUNCTION sokhach.get_cash_reviews(p jsonb)
 RETURNS jsonb
 LANGUAGE plpgsql
 STABLE SECURITY DEFINER
 SET search_path TO 'pg_catalog', 'sokhach', 'pg_temp'
AS $function$
DECLARE v_ids text[];
BEGIN
 IF jsonb_typeof(p)<>'object' OR jsonb_typeof(p->'message_ids')<>'array' OR jsonb_array_length(p->'message_ids')>5000
    OR EXISTS(SELECT 1 FROM jsonb_array_elements(p->'message_ids') e WHERE jsonb_typeof(e)<>'string' OR e#>>'{}' !~ '^[0-9A-Za-z_-]{1,128}$') THEN
   RAISE EXCEPTION 'INVALID_CASH_REVIEW'; END IF;
 v_ids:=ARRAY(SELECT jsonb_array_elements_text(p->'message_ids'));
 RETURN jsonb_build_object('reviews',(SELECT coalesce(jsonb_object_agg(m.message_id,sokhach._cash_review_state(m.message_id,NULL)),'{}'::jsonb)
   FROM (SELECT DISTINCT c.message_id FROM sokhach.cash_report_review c WHERE c.message_id=ANY(v_ids)) m));
END $function$;
ALTER FUNCTION sokhach.get_cash_reviews(jsonb) OWNER TO sokhach_owner;
REVOKE ALL ON FUNCTION sokhach.get_cash_reviews(jsonb) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION sokhach.get_cash_reviews(jsonb) TO sokhach_app;
GRANT EXECUTE ON FUNCTION sokhach.get_cash_reviews(jsonb) TO sokhach_reader;

-- FUNCTION sokhach.get_dashboard()
CREATE OR REPLACE FUNCTION sokhach.get_dashboard()
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'pg_catalog', 'sokhach', 'pg_temp'
AS $function$
DECLARE d date := (now() AT TIME ZONE 'Asia/Ho_Chi_Minh')::date; m date := date_trunc('month', d)::date;
BEGIN
  PERFORM sokhach._actor();
  RETURN (WITH a AS (SELECT c.id,c.name,c.commodity_id,c.transport_mode,coalesce(sum(v.outstanding_vnd),0)::bigint total
    FROM sokhach.customer c JOIN sokhach.cutover_customer cc ON cc.customer_id=c.id AND cc.status='active'
    JOIN sokhach.cutover x ON x.id=cc.cutover_id AND x.status='active' LEFT JOIN sokhach.v_outstanding_month v ON v.customer_id=c.id
    WHERE NOT c.archived GROUP BY c.id,c.name,c.commodity_id,c.transport_mode),
  p AS (SELECT t.customer_id,count(*)::int n FROM sokhach.v_trip_current t JOIN a ON a.id=t.customer_id
    LEFT JOIN LATERAL (SELECT unit_price_vnd,other_fee_vnd FROM sokhach.trip_price_rev z WHERE z.trip_id=t.id ORDER BY z.id DESC LIMIT 1) z ON true
    WHERE NOT t.deleted AND t.status='confirmed' AND z.unit_price_vnd IS NULL AND NOT ((t.container IS NULL OR t.container='') AND z.other_fee_vnd IS NOT NULL) GROUP BY t.customer_id),
  r AS (SELECT customer_id,count(*)::int n FROM sokhach.v_trip_current t JOIN a ON a.id=t.customer_id WHERE NOT t.deleted AND t.status='pending_review' GROUP BY customer_id),
  e AS (SELECT actor,coalesce(sum(jsonb_array_length(e."after"->'trips')) FILTER (WHERE kind='paste'),0)::int trips,count(*) FILTER (WHERE kind='receipt')::int receipts,
    coalesce(sum((e."after"->>'amount_vnd')::bigint) FILTER (WHERE kind='receipt'),0)::bigint received,
    count(*) FILTER (WHERE kind='void' AND EXISTS (SELECT 1 FROM sokhach.receipt z WHERE z.voided_by_event=e.id))::int voids
    FROM sokhach.event e WHERE e.at>=(d::timestamp AT TIME ZONE 'Asia/Ho_Chi_Minh') AND e.at<((d+1)::timestamp AT TIME ZONE 'Asia/Ho_Chi_Minh')
      AND (kind IN ('paste','receipt') OR (kind='void' AND EXISTS (SELECT 1 FROM sokhach.receipt z WHERE z.voided_by_event=e.id))) GROUP BY actor),
  t AS (SELECT coalesce(sum(total) FILTER (WHERE total>0),0)::bigint recv,count(*) FILTER (WHERE total>0)::int recv_n,
    coalesce(sum(total) FILTER (WHERE total<0),0)::bigint cred,count(*) FILTER (WHERE total<0)::int cred_n FROM a),
  aging AS (SELECT b.bucket,b.ord,coalesce(sum(v.outstanding_vnd),0)::bigint amount FROM (VALUES ('current',0),('1-2',1),('3-6',2),('over-6',3)) b(bucket,ord)
    LEFT JOIN sokhach.v_outstanding_month v ON v.customer_id IN (SELECT id FROM a WHERE total>0)
    AND CASE WHEN ((extract(year FROM m)-extract(year FROM v.debt_month))*12+extract(month FROM m)-extract(month FROM v.debt_month))<=0 THEN 0 WHEN ((extract(year FROM m)-extract(year FROM v.debt_month))*12+extract(month FROM m)-extract(month FROM v.debt_month))<=2 THEN 1 WHEN ((extract(year FROM m)-extract(year FROM v.debt_month))*12+extract(month FROM m)-extract(month FROM v.debt_month))<=6 THEN 2 ELSE 3 END=b.ord GROUP BY b.bucket,b.ord)
  SELECT jsonb_build_object('as_of',d::text,'receivable',jsonb_build_object('total_vnd',t.recv::text,'customers',t.recv_n),'credit',jsonb_build_object('total_vnd',t.cred::text,'customers',t.cred_n),
    'by_commodity',coalesce((SELECT jsonb_agg(jsonb_build_object('commodity',q.commodity,'transport_mode',q.transport_mode,'customers',q.n,'receivable_vnd',q.amount::text) ORDER BY q.commodity IS NULL,q.commodity COLLATE "C",q.transport_mode NULLS LAST) FROM (SELECT c.commodity_id,m.name commodity,c.transport_mode,count(*)::int n,sum(c.total)::bigint amount FROM a c LEFT JOIN sokhach.commodity m ON m.id=c.commodity_id WHERE c.total>0 GROUP BY c.commodity_id,m.name,c.transport_mode) q),'[]'::jsonb),
    'aging',(SELECT jsonb_agg(jsonb_build_object('bucket',bucket,'receivable_vnd',amount::text) ORDER BY ord) FROM aging),
    'top_debtors',coalesce((SELECT jsonb_agg(jsonb_build_object('customer_id',q.id,'name',q.name,'commodity',q.commodity,'transport_mode',q.transport_mode,'outstanding_vnd',q.total::text,'oldest_open_month',q.oldest::text) ORDER BY q.total DESC,q.name COLLATE "C",q.id) FROM (SELECT a.*,m.name commodity,min(v.debt_month) FILTER (WHERE v.outstanding_vnd>0) oldest FROM a LEFT JOIN sokhach.commodity m ON m.id=a.commodity_id LEFT JOIN sokhach.v_outstanding_month v ON v.customer_id=a.id WHERE a.total>0 GROUP BY a.id,a.name,a.commodity_id,a.transport_mode,a.total,m.name ORDER BY a.total DESC,a.name COLLATE "C",a.id LIMIT 10) q),'[]'::jsonb),
    'todo',jsonb_build_object('missing_price',coalesce((SELECT jsonb_agg(jsonb_build_object('customer_id',a.id,'name',a.name,'count',p.n) ORDER BY a.name COLLATE "C",a.id) FROM p JOIN a ON a.id=p.customer_id),'[]'::jsonb),'pending_review',coalesce((SELECT jsonb_agg(jsonb_build_object('customer_id',a.id,'name',a.name,'count',r.n) ORDER BY a.name COLLATE "C",a.id) FROM r JOIN a ON a.id=r.customer_id),'[]'::jsonb),'no_baseline',coalesce((SELECT jsonb_agg(jsonb_build_object('customer_id',c.id,'name',c.name) ORDER BY c.name COLLATE "C",c.id) FROM sokhach.customer c WHERE NOT c.archived AND NOT EXISTS (SELECT 1 FROM a WHERE a.id=c.id)),'[]'::jsonb),'credit',coalesce((SELECT jsonb_agg(jsonb_build_object('customer_id',id,'name',name,'credit_vnd',total::text) ORDER BY name COLLATE "C",id) FROM a WHERE total<0),'[]'::jsonb)),
    'today',jsonb_build_object('trips',coalesce((SELECT sum(trips) FROM e),0),'receipts',coalesce((SELECT sum(receipts) FROM e),0),'received_vnd',coalesce((SELECT sum(received) FROM e),0)::text,'voids',coalesce((SELECT sum(voids) FROM e),0),'by_actor',coalesce((SELECT jsonb_agg(jsonb_build_object('actor',actor,'trips',trips,'receipts',receipts,'received_vnd',received::text,'voids',voids) ORDER BY actor COLLATE "C") FROM e),'[]'::jsonb))) FROM t);
END $function$;
ALTER FUNCTION sokhach.get_dashboard() OWNER TO sokhach_owner;
REVOKE ALL ON FUNCTION sokhach.get_dashboard() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION sokhach.get_dashboard() TO sokhach_app;
GRANT EXECUTE ON FUNCTION sokhach.get_dashboard() TO sokhach_reader;

-- FUNCTION sokhach.get_dashboard_debt()
CREATE OR REPLACE FUNCTION sokhach.get_dashboard_debt()
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'pg_catalog', 'sokhach', 'pg_temp'
 SET jit TO 'off'
AS $function$
-- DASH-03 (29/10/2026). Nhóm hạn trả theo tháng nợ (giờ VN): nợ tháng M đến hạn cuối tháng M+1,
-- số tháng quá hạn = (tháng hiện tại - M) - 1: dưới 0 chưa đến hạn, 0 đến hạn cuối tháng này, 1-2, 3-6, từ 7.
-- Rủi ro cao = có nợ quá hạn và (quá hạn từ 3 tháng, hoặc hơn 60 ngày chưa trả hay chưa trả lần nào, hoặc
-- hơn 90 ngày không đi hàng hay chưa có chuyến); còn nợ quá hạn khác là theo dõi. Lần trả: phiếu chưa hủy
-- (cả cấn trừ) và dòng thu sổ gốc chưa xóa; lần đi hàng: chuyến chưa xóa, không tính đã loại, và dòng chuyến
-- sổ gốc chưa xóa. Ngày của dòng không có ngày lấy cuối tháng của dòng (exact=false).
-- Ngày trả là ngày tiền về, đọc cùng luật với get_receipt_book (BANG-THU-01): dòng thu sổ gốc lấy display.date rồi raw_date, chỉ nhận
-- ngày từ 12 tháng trước tháng nợ tới lúc nạp sổ và hôm nay, bỏ dòng số tiền 0 hoặc trống; phiếu web có đuôi ngày tạm giữ ngày phiếu
-- nhưng exact=false. Lấy ngày muộn nhất, cả ngày tạm; bằng ngày thì ưu tiên dòng rõ ngày.
-- Thu/phát sinh tháng này cộng đúng dòng Tổng tháng của get_ledger (DA-THU-01) qua mọi sổ đang hoạt động.
-- Tổng cộng bằng numeric (không ép bigint) để không tràn số khi cộng nhiều sổ.
-- DASH-08 (9/11/2026): this_month.customers là thu/phát sinh tháng này từng sổ có số khác 0 (cả sổ đã hết nợ), để Tổng quan
-- lọc thẻ Thu tháng theo mặt hàng / nhóm khách; cộng các sổ đúng bằng charges_vnd / received_vnd của this_month.
-- KHACH-MOI-01 (19/11/2026): sổ mới = chuyến đầu (sớm nhất, cùng luật ngày với lần đi hàng) cách hôm nay ≤ 60 ngày (người dùng
-- rút từ 90 xuống 60 ngày cùng ngày) và không có
-- lần trả nào sớm hơn chuyến đầu quá 7 ngày. no_pay: đủ 30 ngày từ chuyến đầu mà chưa trả lần nào; slow: chuyến cũ nhất còn chưa
-- trả đủ quá 45 ngày. Sổ có nợ mốc từ tháng trước tháng của chuyến đầu cũng không phải sổ mới (sổ tách từ khách cũ).
-- Chuyến chưa trả đủ = các chuyến mới nhất cộng lại vừa phủ số còn nợ của sổ (nợ cũ trả trước). Tiền chuyến tính như số dư:
-- chuyến đã xác nhận (giá mới nhất) và dòng chuyến sổ gốc (thành tiền sổ gốc), cộng dòng điều chỉnh gắn với chuyến đó;
-- chỉ để xếp, không cộng vào số nào; chuyến chưa có giá không tính. Chỉ là cờ đọc: không đổi nhóm hạn trả, mức rủi ro hay tiền.
DECLARE d date := (now() AT TIME ZONE 'Asia/Ho_Chi_Minh')::date; m date := date_trunc('month', d)::date;
BEGIN
  PERFORM sokhach._actor();
  RETURN (WITH act AS (
      SELECT c.id,c.name,c.commodity_id,c.transport_mode,cc.cutover_id,(x.frozen_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::date AS frozen
        FROM sokhach.customer c
        JOIN sokhach.cutover_customer cc ON cc.customer_id=c.id AND cc.status='active'
        JOIN sokhach.cutover x ON x.id=cc.cutover_id AND x.status='active'
       WHERE NOT c.archived),
    om AS (SELECT v.customer_id,v.debt_month,v.outstanding_vnd,
        ((extract(year FROM m)-extract(year FROM v.debt_month))*12
          +extract(month FROM m)-extract(month FROM v.debt_month))::int-1 AS late
        FROM sokhach.v_outstanding_month v JOIN act ON act.id=v.customer_id),
    debtor AS (SELECT act.*,s.total FROM act
        JOIN (SELECT customer_id,sum(outstanding_vnd) AS total FROM om GROUP BY customer_id) s ON s.customer_id=act.id
       WHERE s.total>0),
    tier AS (SELECT om.customer_id,
        coalesce(sum(om.outstanding_vnd) FILTER (WHERE om.late<0),0) AS t0,
        coalesce(sum(om.outstanding_vnd) FILTER (WHERE om.late=0),0) AS t1,
        coalesce(sum(om.outstanding_vnd) FILTER (WHERE om.late BETWEEN 1 AND 2),0) AS t2,
        coalesce(sum(om.outstanding_vnd) FILTER (WHERE om.late BETWEEN 3 AND 6),0) AS t3,
        coalesce(sum(om.outstanding_vnd) FILTER (WHERE om.late>=7),0) AS t4,
        min(om.debt_month) FILTER (WHERE om.outstanding_vnd>0) AS oldest,
        coalesce(jsonb_agg(jsonb_build_object('month',om.debt_month,'outstanding_vnd',om.outstanding_vnd::text)
          ORDER BY om.debt_month) FILTER (WHERE om.outstanding_vnd<>0),'[]'::jsonb) AS months
        FROM om JOIN debtor b ON b.id=om.customer_id GROUP BY om.customer_id),
    leg_trip AS (SELECT l.id,l.customer_id,coalesce(r.debt_month,l.debt_month) AS mon,
        CASE WHEN r.id IS NULL THEN sokhach._legacy_date(l.display->>'date') ELSE r.event_date END AS dt,
        l.source_total_vnd AS amt
        FROM sokhach.legacy_row l JOIN debtor b ON (b.id,b.cutover_id)=(l.customer_id,l.cutover_id)
        LEFT JOIN LATERAL (SELECT x.id,x.debt_month,x.event_date,x.deleted FROM sokhach.legacy_trip_rev x
            WHERE x.legacy_row_id=l.id ORDER BY x.id DESC LIMIT 1) r ON true
       WHERE l.kind='trip' AND NOT coalesce(r.deleted,false)),
    leg_pay AS (SELECT l.customer_id,l.debt_month AS mon,
        CASE WHEN p.dt BETWEEN (l.debt_month-interval '12 months')::date AND least(b.frozen,d) THEN p.dt END AS dt
        FROM sokhach.legacy_row l JOIN debtor b ON (b.id,b.cutover_id)=(l.customer_id,l.cutover_id)
        CROSS JOIN LATERAL (SELECT coalesce(sokhach._legacy_date(l.display->>'date'),sokhach._legacy_pay_date(l.display->>'raw_date')) AS dt) p
        LEFT JOIN LATERAL (SELECT x.deleted FROM sokhach.legacy_trip_rev x WHERE x.legacy_row_id=l.id ORDER BY x.id DESC LIMIT 1) r ON true
       WHERE l.kind='receipt' AND l.source_total_vnd IS NOT NULL AND l.source_total_vnd<>0 AND NOT coalesce(r.deleted,false)),
    pay_day AS (SELECT r.customer_id,r.date AS dt,
               coalesce(r.reference !~ '( \(ngày tượng trưng\)| · ngày theo cuối tháng khối Sheet)$',true) AS exact
          FROM sokhach.receipt r JOIN debtor b ON b.id=r.customer_id WHERE r.voided_on IS NULL
        UNION ALL
        SELECT customer_id,coalesce(dt,least((mon+interval '1 month')::date-1,d)),dt IS NOT NULL FROM leg_pay),
    pay_last AS (SELECT DISTINCT ON (customer_id) customer_id,dt,exact FROM pay_day ORDER BY customer_id,dt DESC,exact DESC),
    trip_day AS (SELECT t.customer_id,coalesce(t.event_date,least((t.debt_month+interval '1 month')::date-1,d)) AS dt,
               t.event_date IS NOT NULL AS exact
          FROM sokhach.v_trip_current t JOIN debtor b ON b.id=t.customer_id
         WHERE NOT t.deleted AND t.status<>'rejected'
        UNION ALL
        SELECT customer_id,coalesce(dt,least((mon+interval '1 month')::date-1,d)),dt IS NOT NULL
          FROM leg_trip),
    trip_last AS (SELECT DISTINCT ON (customer_id) customer_id,dt,exact FROM trip_day ORDER BY customer_id,dt DESC,exact DESC),
    trip_first AS (SELECT DISTINCT ON (customer_id) customer_id,dt,exact FROM trip_day ORDER BY customer_id,dt,exact DESC),
    newb AS (SELECT f.customer_id,f.dt FROM trip_first f JOIN debtor b ON b.id=f.customer_id WHERE f.dt>=d-60
        AND NOT EXISTS (SELECT 1 FROM pay_day p WHERE p.customer_id=f.customer_id AND p.dt<f.dt-7)
        AND NOT EXISTS (SELECT 1 FROM sokhach.opening_balance o WHERE o.customer_id=b.id AND o.cutover_id=b.cutover_id
            AND o.amount_vnd<>0 AND o.debt_month<date_trunc('month',f.dt)::date)),
    new_adj AS (SELECT a.trip_id,a.legacy_row_id,sum(a.amount_vnd) AS amt
          FROM sokhach.v_adjustment_current a JOIN newb n ON n.customer_id=a.customer_id
         WHERE a.trip_id IS NOT NULL OR a.legacy_row_id IS NOT NULL GROUP BY a.trip_id,a.legacy_row_id),
    new_trip AS (SELECT t.customer_id,coalesce(t.event_date,least((t.debt_month+interval '1 month')::date-1,d)) AS dt,t.id AS k,
               CASE WHEN p.unit_price_vnd IS NOT NULL THEN p.unit_price_vnd+coalesce(p.other_fee_vnd,0)
                    WHEN t.container IS NULL OR t.container='' THEN p.other_fee_vnd END+coalesce(j.amt,0) AS amt
          FROM sokhach.v_trip_current t JOIN newb n ON n.customer_id=t.customer_id
          LEFT JOIN LATERAL (SELECT unit_price_vnd,other_fee_vnd FROM sokhach.trip_price_rev
              WHERE trip_id=t.id ORDER BY id DESC LIMIT 1) p ON true
          LEFT JOIN new_adj j ON j.trip_id=t.id
         WHERE NOT t.deleted AND t.status='confirmed'
        UNION ALL
        SELECT l.customer_id,coalesce(l.dt,least((l.mon+interval '1 month')::date-1,d)),-l.id,l.amt+coalesce(j.amt,0)
          FROM leg_trip l JOIN newb n ON n.customer_id=l.customer_id LEFT JOIN new_adj j ON j.legacy_row_id=l.id),
    -- Đi từ chuyến mới nhất về cũ: chuyến đầu tiên làm tổng vừa phủ số còn nợ là chuyến cũ nhất chưa trả đủ;
    -- không phủ nổi (còn nợ từ mốc hay điều chỉnh) thì là chuyến cũ nhất.
    new_unpaid AS (SELECT DISTINCT ON (customer_id) customer_id,dt FROM (
        SELECT n.customer_id,n.dt,b.total,
               sum(n.amt) OVER (PARTITION BY n.customer_id ORDER BY n.dt DESC,n.k DESC ROWS UNBOUNDED PRECEDING) AS cum
          FROM new_trip n JOIN debtor b ON b.id=n.customer_id WHERE n.amt>0) x
        ORDER BY customer_id,(cum>=total) DESC,CASE WHEN cum>=total THEN cum ELSE -cum END),
    base AS (SELECT b.id,b.name,cm.name AS commodity,b.transport_mode,b.total,t.t0,t.t1,t.t2,t.t3,t.t4,
        t.t2+t.t3+t.t4 AS overdue,t.t3+t.t4 AS long_overdue,t.oldest,t.months,
        p.dt AS pay_day,p.exact AS pay_exact,CASE WHEN p.dt IS NOT NULL THEN greatest(d-p.dt,0) END AS pay_days,
        tr.dt AS trip_day,tr.exact AS trip_exact,CASE WHEN tr.dt IS NOT NULL THEN greatest(d-tr.dt,0) END AS trip_days,
        tf.dt AS first_trip_day,tf.exact AS first_trip_exact,n.customer_id IS NOT NULL AS is_new,
        CASE WHEN n.customer_id IS NOT NULL THEN u.dt END AS unpaid_day,
        CASE WHEN n.customer_id IS NULL THEN NULL
             WHEN p.dt IS NULL AND d-n.dt>=30 THEN 'no_pay'
             WHEN u.dt IS NOT NULL AND d-u.dt>45 THEN 'slow' END AS new_flag
        FROM debtor b JOIN tier t ON t.customer_id=b.id
        LEFT JOIN pay_last p ON p.customer_id=b.id LEFT JOIN trip_last tr ON tr.customer_id=b.id
        LEFT JOIN trip_first tf ON tf.customer_id=b.id LEFT JOIN newb n ON n.customer_id=b.id
        LEFT JOIN new_unpaid u ON u.customer_id=b.id
        LEFT JOIN sokhach.commodity cm ON cm.id=b.commodity_id),
    ranked AS (SELECT r.*,CASE WHEN r.overdue<=0 THEN 'ok'
        WHEN r.long_overdue>0 OR r.pay_days IS NULL OR r.pay_days>60 OR r.trip_days IS NULL OR r.trip_days>90 THEN 'high'
        ELSE 'watch' END AS risk FROM base r),
    -- Như month_keys của get_ledger: sổ không có dòng tháng này thì tháng này không có số.
    keyed AS (SELECT a.id,a.cutover_id FROM act a WHERE
        EXISTS (SELECT 1 FROM sokhach.v_outstanding_month v WHERE v.customer_id=a.id AND v.debt_month=m)
        OR EXISTS (SELECT 1 FROM sokhach.v_trip_current t WHERE NOT t.deleted AND t.customer_id=a.id AND t.debt_month=m)
        OR EXISTS (SELECT 1 FROM sokhach.receipt r WHERE r.customer_id=a.id AND r.voided_on IS NULL
          AND date_trunc('month',r.date)::date=m)),
    flow_c AS (SELECT k.id,
        coalesce(s.source_charge_vnd,(SELECT sum(o.amount_vnd) FROM sokhach.opening_balance o
            WHERE o.customer_id=k.id AND o.cutover_id=k.cutover_id AND o.debt_month=m),0)
          +coalesce((SELECT sum(CASE WHEN p.unit_price_vnd IS NOT NULL THEN p.unit_price_vnd+coalesce(p.other_fee_vnd,0)
              WHEN t.container IS NULL OR t.container='' THEN p.other_fee_vnd END)
              FROM sokhach.v_trip_current t LEFT JOIN LATERAL
                (SELECT unit_price_vnd,other_fee_vnd FROM sokhach.trip_price_rev
                 WHERE trip_id=t.id ORDER BY id DESC LIMIT 1) p ON true
              WHERE t.customer_id=k.id AND t.debt_month=m AND NOT t.deleted AND t.status='confirmed'),0)
          +coalesce((SELECT sum(a.amount_vnd) FROM sokhach.v_adjustment_current a
              LEFT JOIN sokhach.legacy_row lr ON lr.id=a.legacy_row_id
              WHERE a.customer_id=k.id AND a.debt_month=m AND lr.kind IS DISTINCT FROM 'receipt'),0) AS charges,
        coalesce(s.source_receipt_vnd,0)
          +coalesce((SELECT sum(r.amount_vnd) FROM sokhach.receipt r
              WHERE r.customer_id=k.id AND r.voided_on IS NULL AND date_trunc('month',r.date)::date=m),0)
          -coalesce((SELECT sum(o.amount_vnd) FROM sokhach.v_offset_outgoing o
              WHERE o.customer_id=k.id AND o.debt_month=m),0)
          -coalesce((SELECT sum(a.amount_vnd) FROM sokhach.v_adjustment_current a
              JOIN sokhach.legacy_row lr ON lr.id=a.legacy_row_id AND lr.kind='receipt'
              WHERE a.customer_id=k.id AND a.debt_month=m),0) AS received
        FROM keyed k LEFT JOIN LATERAL (SELECT mc.source_charge_vnd,mc.source_receipt_vnd
            FROM sokhach.cutover_month_check mc
           WHERE mc.customer_id=k.id AND mc.cutover_id=k.cutover_id AND mc.debt_month=m
             AND mc.source_charge_vnd IS NOT NULL AND mc.source_receipt_vnd IS NOT NULL) s ON true),
    flow AS (SELECT coalesce(sum(charges),0) AS charges,coalesce(sum(received),0) AS received FROM flow_c)
  SELECT jsonb_build_object('as_of',d::text,'month',m::text,
    'rule',jsonb_build_object('due_after_months',1,'long_overdue_months',3,'no_pay_days',60,'no_trip_days',90,'active_trip_days',30,
      'new_days',60,'new_no_pay_days',30,'new_unpaid_days',45),
    'receivable_vnd',(SELECT coalesce(sum(total),0)::text FROM ranked),
    'due_tiers',(SELECT jsonb_build_array(
        jsonb_build_object('tier','not_due','receivable_vnd',coalesce(sum(t0),0)::text),
        jsonb_build_object('tier','due_this_month','receivable_vnd',coalesce(sum(t1),0)::text),
        jsonb_build_object('tier','late_1_2','receivable_vnd',coalesce(sum(t2),0)::text),
        jsonb_build_object('tier','late_3_6','receivable_vnd',coalesce(sum(t3),0)::text),
        jsonb_build_object('tier','late_over_6','receivable_vnd',coalesce(sum(t4),0)::text)) FROM ranked),
    'summary',(SELECT jsonb_build_object('overdue_vnd',coalesce(sum(overdue),0)::text,
        'long_overdue_vnd',coalesce(sum(long_overdue),0)::text,
        'overdue_customers',count(*) FILTER (WHERE overdue>0),'high_customers',count(*) FILTER (WHERE risk='high'),
        'high_overdue_vnd',coalesce(sum(overdue) FILTER (WHERE risk='high'),0)::text) FROM ranked),
    'this_month',(SELECT jsonb_build_object('month',m::text,'charges_vnd',charges::text,'received_vnd',received::text,
        'customers',(SELECT coalesce(jsonb_agg(jsonb_build_object('customer_id',f.id,'commodity',cm.name,
            'transport_mode',a.transport_mode,'charges_vnd',f.charges::text,'received_vnd',f.received::text) ORDER BY f.id),'[]'::jsonb)
          FROM flow_c f JOIN act a ON a.id=f.id LEFT JOIN sokhach.commodity cm ON cm.id=a.commodity_id
         WHERE f.charges<>0 OR f.received<>0)) FROM flow),
    'customers',coalesce((SELECT jsonb_agg(jsonb_build_object('customer_id',id,'name',name,'commodity',commodity,
        'transport_mode',transport_mode,'outstanding_vnd',total::text,
        'tiers_vnd',jsonb_build_array(t0::text,t1::text,t2::text,t3::text,t4::text),
        'overdue_vnd',overdue::text,'long_overdue_vnd',long_overdue::text,'oldest_open_month',oldest::text,
        'last_receipt_date',pay_day::text,'last_receipt_exact',pay_exact,'pay_days',pay_days,
        'last_trip_date',trip_day::text,'last_trip_exact',trip_exact,'trip_days',trip_days,
        'risk',risk,'months',months,'first_trip_day',first_trip_day::text,'first_trip_exact',first_trip_exact,
        'is_new',is_new,'new_flag',new_flag,'oldest_unpaid_trip_day',unpaid_day::text) ORDER BY overdue DESC,total DESC,name COLLATE "C",id) FROM ranked),'[]'::jsonb)));
END $function$;
ALTER FUNCTION sokhach.get_dashboard_debt() OWNER TO sokhach_owner;
REVOKE ALL ON FUNCTION sokhach.get_dashboard_debt() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION sokhach.get_dashboard_debt() TO sokhach_app;
GRANT EXECUTE ON FUNCTION sokhach.get_dashboard_debt() TO sokhach_reader;

-- FUNCTION sokhach.get_fee_types()
CREATE OR REPLACE FUNCTION sokhach.get_fee_types()
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'pg_catalog', 'sokhach', 'pg_temp'
AS $function$
BEGIN
 PERFORM sokhach._actor();
 RETURN jsonb_build_object('fee_types',(SELECT coalesce(jsonb_agg(to_jsonb(f)-'name_key' ORDER BY sort,id),'[]') FROM sokhach.fee_type f));
END $function$;
ALTER FUNCTION sokhach.get_fee_types() OWNER TO sokhach_owner;
REVOKE ALL ON FUNCTION sokhach.get_fee_types() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION sokhach.get_fee_types() TO sokhach_app;
GRANT EXECUTE ON FUNCTION sokhach.get_fee_types() TO sokhach_reader;

-- FUNCTION sokhach.get_ledger(bigint)
CREATE OR REPLACE FUNCTION sokhach.get_ledger(customer_id bigint)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'pg_catalog', 'sokhach', 'pg_temp'
 SET jit TO 'off'
AS $function$
DECLARE v_version bigint; v_active boolean; v_months jsonb; v_trips jsonb;
        v_adjustments jsonb; v_receipts jsonb; v_opening jsonb; v_legacy jsonb;
        v_events jsonb; v_flags jsonb; v_total numeric; v_pending bigint; v_locks jsonb;
BEGIN
    PERFORM sokhach._actor();
    SELECT c.version INTO v_version FROM sokhach.customer c WHERE c.id=get_ledger.customer_id;
    IF NOT FOUND THEN RAISE EXCEPTION 'CUSTOMER_NOT_FOUND'; END IF;
    SELECT EXISTS (SELECT 1 FROM sokhach.cutover_customer cc
        JOIN sokhach.cutover c ON c.id=cc.cutover_id
        WHERE cc.customer_id=get_ledger.customer_id AND cc.status='active' AND c.status='active')
    INTO v_active;
    -- Source (Sheet) figures per month, for side-by-side reading only: never part of
    -- the balance, which comes from opening buckets (user choice 20/10/2026, option b).
    SELECT coalesce(jsonb_agg(jsonb_build_object('month',m.debt_month,
        'exception_codes',m.exception_codes,
        'source_charge_vnd',m.source_charge_vnd::text,
        'source_receipt_vnd',m.source_receipt_vnd::text,
        'source_cumulative_vnd',m.source_cumulative_vnd::text) ORDER BY m.debt_month),'[]'::jsonb)
    INTO v_flags FROM sokhach.cutover_month_check m
    WHERE m.customer_id=get_ledger.customer_id;
    IF NOT v_active THEN
        RETURN jsonb_build_object('status','NO_BASELINE','customer_id',customer_id,'fee_columns',sokhach._fee_columns(customer_id),
            'version',v_version,'months','[]'::jsonb,'source_exceptions',v_flags,
            'total_outstanding_vnd',NULL);
    END IF;
    -- DA-THU-01 (28/10/2026): dòng Tổng tháng cộng như Sheet. Đã thu = phiếu chưa hủy có ngày thu trong
    -- tháng (đủ số tiền) trừ cấn trừ đi và khoản thu sổ gốc đã xóa; tháng có số Sheet lấy phát sinh/đã thu
    -- của Sheet thay số dư đầu.
    -- Còn nợ cộng dồn tính lùi từ tổng còn nợ nên tháng cuối luôn bằng tổng; outstanding_vnd vẫn là
    -- nợ còn lại của kỳ sau phân bổ nợ cũ trước (tuổi nợ, đối soát), không đổi.
    WITH active_cutover AS (
      SELECT cc.cutover_id FROM sokhach.cutover_customer cc JOIN sokhach.cutover c ON c.id=cc.cutover_id
      WHERE cc.customer_id=get_ledger.customer_id AND cc.status='active' AND c.status='active'
    ), month_keys AS (
      SELECT v.debt_month FROM sokhach.v_outstanding_month v WHERE v.customer_id=get_ledger.customer_id
      UNION SELECT t.debt_month FROM sokhach.v_trip_current t
        WHERE NOT t.deleted AND t.customer_id=get_ledger.customer_id
      UNION SELECT date_trunc('month',r.date)::date FROM sokhach.receipt r
        WHERE r.customer_id=get_ledger.customer_id AND r.voided_on IS NULL
      -- SK-C1 (25/11/2026): tháng hiện tại (giờ VN) luôn có dòng để thẻ tháng có Nợ đầu tháng và Còn nợ cuối tháng;
      -- tháng chưa có gì thì phát sinh, đã thu, còn nợ của kỳ đều 0 nên tổng và các tháng khác không đổi.
      UNION SELECT date_trunc('month',clock_timestamp() AT TIME ZONE 'Asia/Ho_Chi_Minh')::date
    ), figures AS (
      SELECT k.debt_month,
        coalesce((SELECT v.outstanding_vnd FROM sokhach.v_outstanding_month v
            WHERE v.customer_id=get_ledger.customer_id AND v.debt_month=k.debt_month),0)::bigint AS outstanding_vnd,
        coalesce(s.source_charge_vnd,(SELECT sum(o.amount_vnd) FROM sokhach.opening_balance o
            JOIN active_cutover a ON a.cutover_id=o.cutover_id
            WHERE o.customer_id=get_ledger.customer_id AND o.debt_month=k.debt_month),0)
        +coalesce((SELECT sum(CASE WHEN p.unit_price_vnd IS NOT NULL
            THEN p.unit_price_vnd+coalesce(p.other_fee_vnd,0)
            WHEN t.container IS NULL OR t.container='' THEN p.other_fee_vnd END)
            FROM sokhach.v_trip_current t LEFT JOIN LATERAL
              (SELECT unit_price_vnd,other_fee_vnd FROM sokhach.trip_price_rev
               WHERE trip_id=t.id ORDER BY id DESC LIMIT 1) p ON true
            WHERE t.customer_id=get_ledger.customer_id AND t.debt_month=k.debt_month AND NOT t.deleted AND t.status='confirmed'),0)
        +coalesce((SELECT sum(a.amount_vnd) FROM sokhach.v_adjustment_current a
            LEFT JOIN sokhach.legacy_row lr ON lr.id=a.legacy_row_id
            WHERE a.customer_id=get_ledger.customer_id AND a.debt_month=k.debt_month
              AND lr.kind IS DISTINCT FROM 'receipt'),0) AS charges_vnd,
        coalesce(s.source_receipt_vnd,0)
        +coalesce((SELECT sum(r.amount_vnd) FROM sokhach.receipt r
            WHERE r.customer_id=get_ledger.customer_id AND r.voided_on IS NULL
              AND date_trunc('month',r.date)::date=k.debt_month),0)
        -coalesce((SELECT sum(o.amount_vnd) FROM sokhach.v_offset_outgoing o
            WHERE o.customer_id=get_ledger.customer_id AND o.debt_month=k.debt_month),0)
        -- Sửa/xóa khoản thu sổ gốc (XOA-THU-GOC-01) đổi tiền thu của tháng đó, không phải phát sinh.
        -coalesce((SELECT sum(a.amount_vnd) FROM sokhach.v_adjustment_current a
            JOIN sokhach.legacy_row lr ON lr.id=a.legacy_row_id AND lr.kind='receipt'
            WHERE a.customer_id=get_ledger.customer_id AND a.debt_month=k.debt_month),0) AS received_vnd
      FROM month_keys k LEFT JOIN LATERAL (SELECT m.source_charge_vnd,m.source_receipt_vnd
          FROM sokhach.cutover_month_check m JOIN active_cutover a ON a.cutover_id=m.cutover_id
          WHERE m.customer_id=get_ledger.customer_id AND m.debt_month=k.debt_month
            AND m.source_charge_vnd IS NOT NULL AND m.source_receipt_vnd IS NOT NULL) s ON true
    ), chain AS (
      SELECT f.*,(sum(f.outstanding_vnd) OVER () - coalesce(sum(f.charges_vnd-f.received_vnd) OVER
          (ORDER BY f.debt_month ROWS BETWEEN 1 FOLLOWING AND UNBOUNDED FOLLOWING),0))::bigint AS end_of_month_vnd
      FROM figures f
    )
    SELECT coalesce(jsonb_agg(jsonb_build_object('month',debt_month,
        'outstanding_vnd',outstanding_vnd::text,'end_of_month_vnd',end_of_month_vnd::text,
        'prior_months_vnd',(end_of_month_vnd-charges_vnd+received_vnd)::text,
        'charges_vnd',charges_vnd::text,'received_vnd',received_vnd::text)
        ORDER BY debt_month),'[]'::jsonb),coalesce(sum(outstanding_vnd),0)
    INTO v_months,v_total FROM chain;
    SELECT coalesce(jsonb_agg(jsonb_build_object('id',t.id,'month',t.debt_month,
        'event_date',t.event_date,'container',t.container,'carrier',t.carrier,'shipper',t.shipper,'status',t.status,'booking',t.booking,
        'review_reason',coalesce((SELECT e."after"->>'review_reason' FROM sokhach.trip_info_rev r
            JOIN sokhach.event e ON e.id=r.created_by_event WHERE r.trip_id=t.id ORDER BY r.id DESC LIMIT 1),
            pr.reason),
        'origin',t.origin,'destination',t.destination,'note',t.note,
        'unit_price_vnd',p.unit_price_vnd::text,'other_fee_vnd',p.other_fee_vnd::text,
        'fee_lines',sokhach._fee_lines(t.id,NULL),
        'has_typed_fee',EXISTS (SELECT 1 FROM sokhach.trip_fee_line fl JOIN sokhach.fee_type ft ON ft.id=fl.fee_type_id
            WHERE fl.trip_id=t.id AND fl.voided_by_event IS NULL
              AND coalesce(ft.system_key,'') NOT IN ('other','discount','initial')),
        'amount_vnd',CASE WHEN t.status<>'confirmed' THEN NULL WHEN p.unit_price_vnd IS NOT NULL
            THEN (p.unit_price_vnd+coalesce(p.other_fee_vnd,0))::text
            WHEN t.container IS NULL OR t.container='' THEN p.other_fee_vnd::text END,
        'is_fee_only',p.unit_price_vnd IS NULL AND p.other_fee_vnd IS NOT NULL
            AND (t.container IS NULL OR t.container=''),
        'is_missing_price',p.unit_price_vnd IS NULL AND NOT
            (p.other_fee_vnd IS NOT NULL AND (t.container IS NULL OR t.container='')),
        'editable',t.status='confirmed' AND NOT coalesce(ms.locked,t.debt_month <>
            date_trunc('month',clock_timestamp() AT TIME ZONE 'Asia/Ho_Chi_Minh')::date),
        'info_editable',NOT coalesce(ms.locked,t.debt_month <>
            date_trunc('month',clock_timestamp() AT TIME ZONE 'Asia/Ho_Chi_Minh')::date))
        ORDER BY t.debt_month,t.id),'[]'::jsonb),
        count(*) FILTER (WHERE t.status='pending_review' OR p.unit_price_vnd IS NULL AND NOT
            (p.other_fee_vnd IS NOT NULL AND (t.container IS NULL OR t.container='')))
    INTO v_trips,v_pending FROM sokhach.v_trip_current t
    LEFT JOIN LATERAL (SELECT unit_price_vnd,other_fee_vnd FROM sokhach.trip_price_rev
        WHERE trip_id=t.id ORDER BY id DESC LIMIT 1) p ON true
    LEFT JOIN sokhach.month_state ms ON (ms.customer_id,ms.month)=(t.customer_id,t.debt_month)
    -- Audit SQL 23/11/2026 (F4): lý do lúc dán đọc một lượt: mỗi event tạo chuyến của sổ bung mảng `trips` đúng một lần
    -- (trước: mỗi chuyến bung lại cả mảng của lô nó, bậc hai theo cỡ lô).
    LEFT JOIN (SELECT (x->>'trip_id')::bigint AS trip_id, x->>'review_reason' AS reason
        FROM (SELECT DISTINCT tr.created_by_event FROM sokhach.trip tr WHERE tr.customer_id=get_ledger.customer_id) ev
        JOIN sokhach.event e ON e.id=ev.created_by_event
        CROSS JOIN LATERAL jsonb_array_elements(CASE WHEN jsonb_typeof(e."after"->'trips')='array' THEN e."after"->'trips' ELSE '[]'::jsonb END) x
        WHERE x ? 'review_reason') pr ON pr.trip_id=t.id
    WHERE NOT t.deleted AND t.customer_id=get_ledger.customer_id;
    SELECT coalesce(jsonb_agg(jsonb_build_object('id',id,'month',debt_month,
        'trip_id',trip_id,'legacy_row_id',legacy_row_id,'amount_vnd',amount_vnd::text,'note',note,'at',at)
        ORDER BY debt_month,id),'[]'::jsonb) INTO v_adjustments
    FROM sokhach.v_adjustment_current WHERE v_adjustment_current.customer_id=get_ledger.customer_id;
    SELECT coalesce(jsonb_agg(jsonb_build_object('id',r.id,'pid',r.pid,'date',r.date,
        'method',r.method,'reference',r.reference,'amount_vnd',r.amount_vnd::text,'void_reason',r.void_reason,
        'offset_pair_id',(SELECT id FROM sokhach.offset_pair WHERE target_receipt_id=r.id),
        'counterparty_customer_id',(SELECT source_customer_id FROM sokhach.offset_pair WHERE target_receipt_id=r.id),
        'counterparty_name',(SELECT c.name FROM sokhach.offset_pair p JOIN sokhach.customer c
            ON c.id=p.source_customer_id WHERE p.target_receipt_id=r.id),
        'voided_on',r.voided_on,'voided_by_event',r.voided_by_event,'allocations',
        (SELECT coalesce(jsonb_agg(jsonb_build_object('id',l.id,'month',l.debt_month,
            'kind',l.kind,'amount_vnd',l.amount_vnd::text,'superseded_by_event',
            l.superseded_by_event) ORDER BY l.id),'[]'::jsonb)
            -- Audit SQL 23/11/2026 (F4): bỏ các bản phân bổ cũ đã bị phân bổ lại thay; giữ dòng còn hiệu lực và dòng bị chính
            -- lệnh hủy phiếu thay (tháng của phiếu đã hủy). Số dòng không còn tăng theo số lần phân bổ lại.
            FROM sokhach.receipt_line l WHERE l.receipt_id=r.id
              AND (l.superseded_by_event IS NULL OR l.superseded_by_event=r.voided_by_event))) ORDER BY r.date,r.pid COLLATE "C"),'[]'::jsonb)
    INTO v_receipts FROM sokhach.receipt r WHERE r.customer_id=get_ledger.customer_id;
    SELECT coalesce(jsonb_agg(jsonb_build_object('id',o.id,'month',o.debt_month,
        'amount_vnd',o.amount_vnd::text,'editable',false) ORDER BY o.debt_month),'[]'::jsonb)
    INTO v_opening FROM sokhach.opening_balance o
    JOIN sokhach.cutover_customer cc ON (cc.customer_id,cc.cutover_id)=(o.customer_id,o.cutover_id)
    JOIN sokhach.cutover c ON c.id=cc.cutover_id
    WHERE o.customer_id=get_ledger.customer_id AND cc.status='active' AND c.status='active';
    SELECT coalesce(jsonb_agg(jsonb_build_object('id',l.id,'month',CASE WHEN l.kind='trip' THEN (cur.data->>'month')::date ELSE l.debt_month END,
        'kind',l.kind,'display',l.display,'source_total_vnd',l.source_total_vnd::text,
        'fee_lines',sokhach._fee_lines(NULL,l.id),
        'has_typed_fee',EXISTS (SELECT 1 FROM sokhach.trip_fee_line fl JOIN sokhach.fee_type ft ON ft.id=fl.fee_type_id
            WHERE fl.legacy_row_id=l.id AND fl.voided_by_event IS NULL
              AND coalesce(ft.system_key,'') NOT IN ('other','discount','initial')),
        -- Lần sửa phí đầu tiên đổi TOTAL sổ gốc sang đơn giá + tổng khoản; cờ báo trước số sẽ đổi.
        'counted_differs',l.kind='trip' AND cur.data->>'unit_price_vnd' IS NOT NULL
            AND (cur.data->>'counted_vnd')::bigint<>(cur.data->>'unit_price_vnd')::bigint
              +coalesce((SELECT sum(fl.amount_vnd) FROM sokhach.trip_fee_line fl
                WHERE fl.legacy_row_id=l.id AND fl.voided_by_event IS NULL),0),
        'historical',true,'editable',l.kind='trip','current',CASE WHEN l.kind='trip' THEN cur.data END) ORDER BY l.debt_month,l.id),'[]'::jsonb)
    INTO v_legacy FROM sokhach.legacy_row l
    CROSS JOIN LATERAL (SELECT sokhach._legacy_current(l.id) AS data) cur
    JOIN sokhach.cutover_customer cc ON (cc.customer_id,cc.cutover_id)=(l.customer_id,l.cutover_id)
    JOIN sokhach.cutover c ON c.id=cc.cutover_id
    WHERE l.customer_id=get_ledger.customer_id AND cc.status='active' AND c.status='active' AND NOT (cur.data->>'deleted')::boolean;
    v_events:=sokhach._ledger_events(get_ledger.customer_id);
    -- Cờ khóa đã ghi của mọi tháng (kể cả tháng không chuyến); thiếu hàng thì
    -- chỉ today_month mở. Giao diện dùng hai trường này, không đoán theo đồng hồ máy.
    SELECT coalesce(jsonb_agg(jsonb_build_object('month',ms.month,'locked',ms.locked)
        ORDER BY ms.month),'[]'::jsonb) INTO v_locks
    FROM sokhach.month_state ms WHERE ms.customer_id=get_ledger.customer_id;
    RETURN jsonb_build_object('status','active','customer_id',customer_id,'fee_columns',sokhach._fee_columns(customer_id),
        'today_month',date_trunc('month',clock_timestamp() AT TIME ZONE 'Asia/Ho_Chi_Minh')::date,
        'month_locks',v_locks,
        'version',v_version,'months',v_months,'total_outstanding_vnd',v_total::bigint::text,
        'pending_count',v_pending,'trips',v_trips,'adjustments',v_adjustments,
        'receipts',v_receipts,'opening',v_opening,'source_exceptions',v_flags,
        'legacy_rows',v_legacy,'events',v_events,
        'outgoing_offsets',coalesce((SELECT jsonb_agg(jsonb_build_object(
            'offset_pair_id',p.id,'pid',p.source_pid,'date',p.date,'method','CẤN TRỪ',
            'amount_vnd',(-p.amount_vnd)::text,'void_reason',p.void_reason,
            'voided_by_event',p.voided_by_event,'counterparty_customer_id',p.target_customer_id,
            'counterparty_name',c.name) ORDER BY p.date,p.source_pid COLLATE "C")
            FROM sokhach.offset_pair p JOIN sokhach.customer c ON c.id=p.target_customer_id
            WHERE p.source_customer_id=get_ledger.customer_id),'[]'::jsonb));
END $function$;
ALTER FUNCTION sokhach.get_ledger(bigint) OWNER TO sokhach_owner;
REVOKE ALL ON FUNCTION sokhach.get_ledger(bigint) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION sokhach.get_ledger(bigint) TO sokhach_app;
GRANT EXECUTE ON FUNCTION sokhach.get_ledger(bigint) TO sokhach_reader;

-- FUNCTION sokhach.get_ledger_events(bigint)
CREATE OR REPLACE FUNCTION sokhach.get_ledger_events(customer_id bigint)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'pg_catalog', 'sokhach', 'pg_temp'
AS $function$
-- MO-SO-NHANH-02: khung Lịch sử đọc riêng, không dựng cả sổ. Một câu lệnh nên version và events cùng một ảnh dữ liệu.
-- Sổ chưa có mốc active không có Lịch sử, như get_ledger trả NO_BASELINE không kèm events.
DECLARE v_result jsonb;
BEGIN
    PERFORM sokhach._actor();
    SELECT jsonb_build_object('customer_id',c.id,'version',c.version,'events',
        CASE WHEN EXISTS (SELECT 1 FROM sokhach.cutover_customer cc JOIN sokhach.cutover x ON x.id=cc.cutover_id
            WHERE cc.customer_id=c.id AND cc.status='active' AND x.status='active')
        THEN sokhach._ledger_events(c.id) ELSE '[]'::jsonb END)
    INTO v_result FROM sokhach.customer c WHERE c.id=get_ledger_events.customer_id;
    IF NOT FOUND THEN RAISE EXCEPTION 'CUSTOMER_NOT_FOUND'; END IF;
    RETURN v_result;
END $function$;
ALTER FUNCTION sokhach.get_ledger_events(bigint) OWNER TO sokhach_owner;
REVOKE ALL ON FUNCTION sokhach.get_ledger_events(bigint) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION sokhach.get_ledger_events(bigint) TO sokhach_app;

-- FUNCTION sokhach.get_marks(bigint,text)
CREATE OR REPLACE FUNCTION sokhach.get_marks(p_customer bigint, p_conversation text)
 RETURNS jsonb
 LANGUAGE plpgsql
 STABLE SECURITY DEFINER
 SET search_path TO 'pg_catalog', 'sokhach', 'pg_temp'
AS $function$
DECLARE v_today date := (clock_timestamp() AT TIME ZONE 'Asia/Ho_Chi_Minh')::date;
BEGIN
 IF (p_customer IS NULL) = (p_conversation IS NULL) THEN RAISE EXCEPTION 'INVALID_MARK'; END IF;
 RETURN jsonb_build_object('marks',(SELECT coalesce(jsonb_agg(sokhach._mark_json(m,v_today) ORDER BY m.created_at DESC,m.id DESC),'[]'::jsonb)
   FROM sokhach.contact_mark m
   WHERE (p_customer IS NOT NULL AND m.customer_id=p_customer) OR (p_conversation IS NOT NULL AND m.conversation_id=p_conversation)));
END $function$;
ALTER FUNCTION sokhach.get_marks(bigint,text) OWNER TO sokhach_owner;
REVOKE ALL ON FUNCTION sokhach.get_marks(bigint,text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION sokhach.get_marks(bigint,text) TO sokhach_app;
GRANT EXECUTE ON FUNCTION sokhach.get_marks(bigint,text) TO sokhach_reader;

-- FUNCTION sokhach.get_month_customers(date)
CREATE OR REPLACE FUNCTION sokhach.get_month_customers(p_month date)
 RETURNS jsonb
 LANGUAGE plpgsql
 STABLE SECURITY DEFINER
 SET search_path TO 'pg_catalog', 'sokhach', 'pg_temp'
 SET jit TO 'off'
AS $function$
-- KHACH-THANG-01. Mỗi sổ đang hoạt động có phát sinh, đã thu hoặc còn nợ khác 0 ở một tháng (trống là tháng hiện tại, giờ VN):
-- phát sinh và đã thu cộng đúng dòng Tổng tháng của get_ledger (DA-THU-01), cùng phép tính this_month của get_dashboard_debt (harness
-- KHACH-THANG.01 so hai hàm ở tháng hiện tại); còn nợ của tháng là v_outstanding_month của tháng nợ đó (như Công nợ theo tháng).
-- KHACH-THANG-02: thêm nợ đầu tháng và còn nợ cuối tháng như thanh tháng của Sổ khách (SO-GON-05), cùng phép với get_ledger: cuối
-- tháng = tổng còn nợ trừ (phát sinh − đã thu) của các tháng sau trong cùng tập month_keys, đầu tháng = cuối − phát sinh + đã thu;
-- harness so từng sổ với get_ledger. Tổng cộng bằng numeric để không tràn số. Chỉ đọc.
DECLARE m date := coalesce(p_month,date_trunc('month',(now() AT TIME ZONE 'Asia/Ho_Chi_Minh'))::date);
BEGIN
  PERFORM sokhach._actor();
  IF date_trunc('month',m)::date <> m THEN RAISE EXCEPTION 'INVALID_MONTH'; END IF;
  RETURN (WITH act AS (
      SELECT c.id,cc.cutover_id FROM sokhach.customer c
        JOIN sokhach.cutover_customer cc ON cc.customer_id=c.id AND cc.status='active'
        JOIN sokhach.cutover x ON x.id=cc.cutover_id AND x.status='active'
       WHERE NOT c.archived),
    -- Như month_keys của get_ledger: sổ không có dòng tháng này thì tháng này không có số.
    keyed AS (SELECT a.id,a.cutover_id FROM act a WHERE
        EXISTS (SELECT 1 FROM sokhach.v_outstanding_month v WHERE v.customer_id=a.id AND v.debt_month=m)
        OR EXISTS (SELECT 1 FROM sokhach.v_trip_current t WHERE NOT t.deleted AND t.customer_id=a.id AND t.debt_month=m)
        OR EXISTS (SELECT 1 FROM sokhach.receipt r WHERE r.customer_id=a.id AND r.voided_on IS NULL
          AND date_trunc('month',r.date)::date=m)),
    -- Tháng m và các tháng sau của các sổ đó, đúng tập month_keys của get_ledger (dòng tháng hiện tại get_ledger luôn thêm có
    -- phát sinh, đã thu bằng 0 nên không đổi số cuối tháng).
    months AS (SELECT k.id,k.cutover_id,x.dm FROM keyed k CROSS JOIN LATERAL (
        SELECT v.debt_month AS dm FROM sokhach.v_outstanding_month v WHERE v.customer_id=k.id AND v.debt_month>=m
        UNION SELECT t.debt_month FROM sokhach.v_trip_current t WHERE NOT t.deleted AND t.customer_id=k.id AND t.debt_month>=m
        UNION SELECT date_trunc('month',r.date)::date FROM sokhach.receipt r
          WHERE r.customer_id=k.id AND r.voided_on IS NULL AND r.date>=m) x),
    flow_c AS (SELECT k.id,k.dm,
        coalesce(s.source_charge_vnd,(SELECT sum(o.amount_vnd) FROM sokhach.opening_balance o
            WHERE o.customer_id=k.id AND o.cutover_id=k.cutover_id AND o.debt_month=k.dm),0)
          +coalesce((SELECT sum(CASE WHEN p.unit_price_vnd IS NOT NULL THEN p.unit_price_vnd+coalesce(p.other_fee_vnd,0)
              WHEN t.container IS NULL OR t.container='' THEN p.other_fee_vnd END)
              FROM sokhach.v_trip_current t LEFT JOIN LATERAL
                (SELECT unit_price_vnd,other_fee_vnd FROM sokhach.trip_price_rev
                 WHERE trip_id=t.id ORDER BY id DESC LIMIT 1) p ON true
              WHERE t.customer_id=k.id AND t.debt_month=k.dm AND NOT t.deleted AND t.status='confirmed'),0)
          +coalesce((SELECT sum(a.amount_vnd) FROM sokhach.v_adjustment_current a
              LEFT JOIN sokhach.legacy_row lr ON lr.id=a.legacy_row_id
              WHERE a.customer_id=k.id AND a.debt_month=k.dm AND lr.kind IS DISTINCT FROM 'receipt'),0) AS charges,
        coalesce(s.source_receipt_vnd,0)
          +coalesce((SELECT sum(r.amount_vnd) FROM sokhach.receipt r
              WHERE r.customer_id=k.id AND r.voided_on IS NULL AND date_trunc('month',r.date)::date=k.dm),0)
          -coalesce((SELECT sum(o.amount_vnd) FROM sokhach.v_offset_outgoing o
              WHERE o.customer_id=k.id AND o.debt_month=k.dm),0)
          -coalesce((SELECT sum(a.amount_vnd) FROM sokhach.v_adjustment_current a
              JOIN sokhach.legacy_row lr ON lr.id=a.legacy_row_id AND lr.kind='receipt'
              WHERE a.customer_id=k.id AND a.debt_month=k.dm),0) AS received
        FROM months k LEFT JOIN LATERAL (SELECT mc.source_charge_vnd,mc.source_receipt_vnd
            FROM sokhach.cutover_month_check mc
           WHERE mc.customer_id=k.id AND mc.cutover_id=k.cutover_id AND mc.debt_month=k.dm
             AND mc.source_charge_vnd IS NOT NULL AND mc.source_receipt_vnd IS NOT NULL) s ON true),
    later AS (SELECT id,sum(charges-received) AS net FROM flow_c WHERE dm>m GROUP BY id),
    figures AS (SELECT f.id,f.charges,f.received,
        coalesce((SELECT sum(v.outstanding_vnd) FROM sokhach.v_outstanding_month v
            WHERE v.customer_id=f.id AND v.debt_month=m),0) AS outstanding,
        coalesce((SELECT sum(v.outstanding_vnd) FROM sokhach.v_outstanding_month v WHERE v.customer_id=f.id),0)
          -coalesce(l.net,0) AS end_of_month
        FROM flow_c f LEFT JOIN later l ON l.id=f.id WHERE f.dm=m),
    rows AS (SELECT * FROM figures WHERE charges<>0 OR received<>0 OR outstanding<>0)
  SELECT jsonb_build_object('month',m::text,
    'charges_vnd',(SELECT coalesce(sum(charges),0)::text FROM rows),
    'received_vnd',(SELECT coalesce(sum(received),0)::text FROM rows),
    'outstanding_vnd',(SELECT coalesce(sum(outstanding),0)::text FROM rows),
    'customers',(SELECT coalesce(jsonb_agg(jsonb_build_object('customer_id',r.id,'charges_vnd',r.charges::text,
        'received_vnd',r.received::text,'outstanding_vnd',r.outstanding::text,
        'prior_months_vnd',(r.end_of_month-r.charges+r.received)::text,'end_of_month_vnd',r.end_of_month::text)
        ORDER BY r.charges DESC,r.id),'[]'::jsonb) FROM rows r)));
END $function$;
ALTER FUNCTION sokhach.get_month_customers(date) OWNER TO sokhach_owner;
REVOKE ALL ON FUNCTION sokhach.get_month_customers(date) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION sokhach.get_month_customers(date) TO sokhach_app;
GRANT EXECUTE ON FUNCTION sokhach.get_month_customers(date) TO sokhach_reader;

-- FUNCTION sokhach.get_price_status(bigint)
CREATE OR REPLACE FUNCTION sokhach.get_price_status(customer_id bigint)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'pg_catalog', 'sokhach', 'pg_temp'
AS $function$
DECLARE v_version bigint;
BEGIN
 PERFORM sokhach._actor();
 SELECT c.version INTO v_version FROM sokhach.customer c WHERE c.id=get_price_status.customer_id;
 IF NOT FOUND THEN RAISE EXCEPTION 'CUSTOMER_NOT_FOUND'; END IF;
 RETURN (WITH r AS (
   SELECT x.*,x.lookup->>'unit_price_vnd' AS table_price,
     x.status='confirmed' AND x.month_open AND x.unit_price_vnd IS NULL AND x.lookup ? 'unit_price_vnd' AS ready,
     x.unit_price_vnd IS NOT NULL AND x.lookup ? 'unit_price_vnd'
       AND x.unit_price_vnd::text<>x.lookup->>'unit_price_vnd' AS differs
   FROM sokhach._price_trip_rows(get_price_status.customer_id) x)
  SELECT jsonb_build_object('customer_id',get_price_status.customer_id,'version',v_version,
   'has_table',EXISTS (SELECT 1 FROM sokhach.price_period p WHERE p.customer_id=get_price_status.customer_id),
   'trips',coalesce(jsonb_agg(jsonb_build_object('trip_id',r.trip_id,'unit_price_vnd',r.unit_price_vnd::text,
       'from_table',r.from_table,'lookup',r.lookup,'ready',r.ready,'differs',r.differs) ORDER BY r.trip_id),'[]'),
   'ready_count',count(*) FILTER (WHERE r.ready),
   -- Chuyến chưa có giá chưa tính tiền; ghi đơn giá thì cộng thêm đơn giá + phụ phí (trống = 0 theo V7-BE).
   'ready_total_vnd',coalesce(sum(r.table_price::bigint+coalesce(r.other_fee_vnd,0)) FILTER (WHERE r.ready),0)::text,
   'ready_months',coalesce(jsonb_agg(DISTINCT r.debt_month) FILTER (WHERE r.ready),'[]'),
   'reapply_count',count(*) FILTER (WHERE r.differs AND r.from_table AND r.status='confirmed' AND r.month_open))
  FROM r);
END $function$;
ALTER FUNCTION sokhach.get_price_status(bigint) OWNER TO sokhach_owner;
REVOKE ALL ON FUNCTION sokhach.get_price_status(bigint) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION sokhach.get_price_status(bigint) TO sokhach_app;
GRANT EXECUTE ON FUNCTION sokhach.get_price_status(bigint) TO sokhach_reader;

-- FUNCTION sokhach.get_price_table(bigint)
CREATE OR REPLACE FUNCTION sokhach.get_price_table(customer_id bigint)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'pg_catalog', 'sokhach', 'pg_temp'
AS $function$
DECLARE v_version bigint;
BEGIN
 PERFORM sokhach._actor();
 SELECT c.version INTO v_version FROM sokhach.customer c WHERE c.id=get_price_table.customer_id;
 IF NOT FOUND THEN RAISE EXCEPTION 'CUSTOMER_NOT_FOUND'; END IF;
 -- Shipper đang có trong sổ và nhóm giá đang áp: để soát tên viết lệch so với danh sách TT.
 RETURN jsonb_build_object('customer_id',customer_id,'version',v_version,
  'price_table',sokhach._price_table(customer_id),
  'book_shippers',(SELECT coalesce(jsonb_agg(jsonb_build_object('name',x.name,'tier',x.tier,'trip_count',x.n)
      ORDER BY x.tier,x.name),'[]') FROM (
    SELECT min(btrim(t.shipper)) AS name,count(*) AS n,
      CASE WHEN EXISTS (SELECT 1 FROM sokhach.price_tt_shipper s WHERE s.customer_id=get_price_table.customer_id
        AND s.shipper_key=sokhach._price_key(t.shipper)) THEN 'tt' ELSE 'khach' END AS tier
    FROM sokhach.v_trip_current t WHERE t.customer_id=get_price_table.customer_id AND NOT t.deleted
      AND sokhach._price_key(t.shipper) IS NOT NULL GROUP BY sokhach._price_key(t.shipper),3) x));
END $function$;
ALTER FUNCTION sokhach.get_price_table(bigint) OWNER TO sokhach_owner;
REVOKE ALL ON FUNCTION sokhach.get_price_table(bigint) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION sokhach.get_price_table(bigint) TO sokhach_app;
GRANT EXECUTE ON FUNCTION sokhach.get_price_table(bigint) TO sokhach_reader;

-- FUNCTION sokhach.get_read_stamp()
CREATE OR REPLACE FUNCTION sokhach.get_read_stamp()
 RETURNS jsonb
 LANGUAGE plpgsql
 STABLE SECURITY DEFINER
 SET search_path TO 'pg_catalog', 'sokhach', 'pg_temp'
AS $function$
DECLARE v_sql text; v_stamp text;
BEGIN
  PERFORM sokhach._actor();
  SELECT 'SELECT md5(string_agg(t||'':''||n||'':''||s,'','' ORDER BY t)) FROM ('
         ||string_agg(format('SELECT %L AS t,count(*) AS n,coalesce(sum(xmin::text::bigint),0) AS s FROM sokhach.%I',
                             c.relname,c.relname),' UNION ALL ' ORDER BY c.relname)||') z'
    INTO v_sql FROM pg_class c WHERE c.relnamespace='sokhach'::regnamespace AND c.relkind='r';
  EXECUTE v_sql INTO v_stamp;
  SELECT md5(v_stamp
    ||'|'||(SELECT count(*)||':'||coalesce(sum(p.xmin::text::bigint),0) FROM pg_proc p WHERE p.pronamespace='sokhach'::regnamespace)
    ||'|'||(SELECT count(*)||':'||coalesce(sum(r.xmin::text::bigint),0) FROM pg_rewrite r JOIN pg_class c ON c.oid=r.ev_class
            WHERE c.relnamespace='sokhach'::regnamespace)
    ||'|'||(SELECT count(*)||':'||coalesce(sum(c.xmin::text::bigint),0) FROM pg_class c WHERE c.relnamespace='sokhach'::regnamespace))
    INTO v_stamp;
  RETURN jsonb_build_object('as_of',(now() AT TIME ZONE 'Asia/Ho_Chi_Minh')::date::text,'stamp',v_stamp);
END $function$;
ALTER FUNCTION sokhach.get_read_stamp() OWNER TO sokhach_owner;
REVOKE ALL ON FUNCTION sokhach.get_read_stamp() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION sokhach.get_read_stamp() TO sokhach_app;
GRANT EXECUTE ON FUNCTION sokhach.get_read_stamp() TO sokhach_reader;

-- FUNCTION sokhach.get_receipt_book(date)
CREATE OR REPLACE FUNCTION sokhach.get_receipt_book(p_month date)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'pg_catalog', 'sokhach', 'pg_temp'
AS $function$
-- BANG-THU-01. Tháng tính theo ngày tiền về, khác "Đã thu" của sổ ở tháng có dòng Sheet (DA-THU-01 giữ nguyên): Sheet ghi khoản thu
-- ở khối tháng nợ. Gồm phiếu web chưa hủy và dòng thu sổ gốc chưa xóa; cấn trừ không phải tiền mới vào nên liệt kê riêng.
-- Dòng Sheet số tiền 0 là ô công thức trống, không liệt kê. Không rõ ngày (date NULL, nằm ở tháng của khối, không cộng vào tổng tháng): Sheet không đọc được ngày; ngày sau lúc nạp sổ hoặc sau
-- hôm nay; ngày trước tháng của khối hơn 12 tháng; phiếu đặt ngày cuối tháng khối vì Sheet không ghi ngày (MAY-DOI-SOAT-01).
-- Mọi tháng cộng lại, mọi sổ cộng lại bằng đúng tổng received_vnd của get_ledger: dòng chỉ đổi tháng, không thêm bớt tiền.
DECLARE d date := (now() AT TIME ZONE 'Asia/Ho_Chi_Minh')::date; v_this date := date_trunc('month', d)::date;
        v_month date := coalesce(p_month, v_this);
BEGIN
  PERFORM sokhach._actor();
  IF date_trunc('month', v_month)::date <> v_month THEN RAISE EXCEPTION 'INVALID_MONTH'; END IF;
  RETURN (WITH act AS (
      SELECT c.id,c.name,cc.cutover_id,(x.frozen_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::date AS frozen FROM sokhach.customer c
        JOIN sokhach.cutover_customer cc ON cc.customer_id=c.id AND cc.status='active'
        JOIN sokhach.cutover x ON x.id=cc.cutover_id AND x.status='active'
       WHERE NOT c.archived),
    sheet AS (
      SELECT l.id,l.customer_id,a.name,l.debt_month,l.source_total_vnd AS amount,q.dt,
        -- Ghi chú: chữ người gõ; ô chỉ có ngày mà ngày đã nhận thì không lặp lại, ngày không nhận thì giữ để người đọc thấy đã gõ gì.
        nullif(concat_ws(' · ',
          CASE WHEN t.raw ~ '^[0-9]{5}(\.0+)?$' THEN CASE WHEN q.dt IS NULL THEN to_char(p.dt,'DD/MM/YYYY') END
               WHEN q.dt IS NOT NULL AND t.raw ~ '^([0-9]{1,2}[/.-][0-9]{1,2}[/.-][0-9]{4}|[0-9]{4}-[0-9]{1,2}-[0-9]{1,2})$' THEN NULL
               ELSE nullif(t.raw,'') END,
          CASE WHEN t.note=t.raw OR t.note ~ '^([0-9]{1,2}[/.-][0-9]{1,2}[/.-][0-9]{4}|[0-9]{4}-[0-9]{1,2}-[0-9]{1,2}( [0-9:]+)?)$' THEN NULL
               ELSE nullif(t.note,'') END),'') AS note
        FROM sokhach.legacy_row l JOIN act a ON (a.id,a.cutover_id)=(l.customer_id,l.cutover_id)
        CROSS JOIN LATERAL (SELECT btrim(coalesce(l.display->>'raw_date','')) AS raw,btrim(coalesce(l.display->>'note','')) AS note) t
        CROSS JOIN LATERAL (SELECT coalesce(sokhach._legacy_date(l.display->>'date'),sokhach._legacy_pay_date(t.raw)) AS dt) p
        CROSS JOIN LATERAL (SELECT CASE WHEN p.dt BETWEEN (l.debt_month-interval '12 months')::date AND least(a.frozen,d) THEN p.dt END AS dt) q
        LEFT JOIN LATERAL (SELECT r.deleted FROM sokhach.legacy_trip_rev r WHERE r.legacy_row_id=l.id ORDER BY r.id DESC LIMIT 1) rev ON true
       WHERE l.kind='receipt' AND l.source_total_vnd IS NOT NULL AND l.source_total_vnd<>0 AND NOT coalesce(rev.deleted,false)),
    web AS (
      SELECT r.id,r.pid,r.customer_id,a.name,date_trunc('month',r.date)::date AS book_month,r.amount_vnd AS amount,r.method,
        CASE WHEN r.reference ~ '( \(ngày tượng trưng\)| · ngày theo cuối tháng khối Sheet)$' THEN NULL ELSE r.date END AS dt,
        -- Tiền tố và đuôi kỹ thuật (reference, review_reference, NO_DATE_NOTE, ghi tay "ngày tượng trưng") không lên màn.
        regexp_replace(regexp_replace(coalesce(r.reference,''),'^Sheet( #[^:]*)?(: ?|$)',''),'( \(ngày tượng trưng\)| · ngày theo cuối tháng khối Sheet)$','') AS note
        FROM sokhach.receipt r JOIN act a ON a.id=r.customer_id
       WHERE r.voided_on IS NULL AND NOT EXISTS (SELECT 1 FROM sokhach.offset_pair o WHERE o.target_receipt_id=r.id)),
    items AS (
      SELECT 'sheet'::text AS source,s.id,NULL::text AS pid,s.customer_id,s.name,s.debt_month AS book_month,s.amount,s.dt,NULL::text AS method,s.note FROM sheet s
      UNION ALL
      SELECT 'web',w.id,w.pid,w.customer_id,w.name,w.book_month,w.amount,w.dt,w.method,
        CASE WHEN w.note ~ '^([0-9]{1,2}[/.-][0-9]{1,2}[/.-][0-9]{4}|[0-9]{5}(\.0+)?)$' AND sokhach._legacy_pay_date(w.note)=w.dt THEN NULL
             WHEN w.note ~ '^[0-9]{5}(\.0+)?$' THEN to_char(sokhach._legacy_pay_date(w.note),'DD/MM/YYYY') ELSE nullif(w.note,'') END
        FROM web w),
    placed AS (SELECT i.*,date_trunc('month',coalesce(i.dt,i.book_month))::date AS month FROM items i),
    idx AS (
      SELECT p.month,coalesce(sum(p.amount) FILTER (WHERE p.dt IS NOT NULL),0) AS total,count(*) FILTER (WHERE p.dt IS NOT NULL) AS n,
             coalesce(sum(p.amount) FILTER (WHERE p.dt IS NULL),0) AS undated,count(*) FILTER (WHERE p.dt IS NULL) AS undated_n
        FROM placed p GROUP BY p.month
      UNION ALL SELECT v_this,0,0,0,0 WHERE NOT EXISTS (SELECT 1 FROM placed p WHERE p.month=v_this)),
    cur AS (
      SELECT p.*,jsonb_build_object('source',p.source,'id',p.id,'pid',p.pid,'customer_id',p.customer_id,'name',p.name,'date',p.dt,
          'book_month',p.book_month,'amount_vnd',p.amount::text,'method',p.method,'note',p.note,
          'allocations',CASE WHEN p.source='web' THEN (SELECT coalesce(jsonb_agg(jsonb_build_object('month',x.debt_month,'kind',x.kind,'amount_vnd',x.amount::text)
              ORDER BY x.debt_month,x.kind),'[]'::jsonb) FROM (SELECT l.debt_month,l.kind,sum(l.amount_vnd) AS amount
              FROM sokhach.v_receipt_line_active l WHERE l.receipt_id=p.id GROUP BY 1,2) x) ELSE '[]'::jsonb END) AS js
        FROM placed p WHERE p.month=v_month)
    SELECT jsonb_build_object('month',v_month,'as_of',d,'today_month',v_this,
      'months',(SELECT jsonb_agg(jsonb_build_object('month',m.month,'total_vnd',m.total::text,'count',m.n,
          'undated_vnd',m.undated::text,'undated_count',m.undated_n) ORDER BY m.month DESC) FROM idx m),
      'summary',(SELECT jsonb_build_object('total_vnd',coalesce(sum(c.amount) FILTER (WHERE c.dt IS NOT NULL),0)::text,
          'count',count(*) FILTER (WHERE c.dt IS NOT NULL),'customers',count(DISTINCT c.customer_id) FILTER (WHERE c.dt IS NOT NULL),
          'undated_vnd',coalesce(sum(c.amount) FILTER (WHERE c.dt IS NULL),0)::text,'undated_count',count(*) FILTER (WHERE c.dt IS NULL),
          'today_vnd',coalesce(sum(c.amount) FILTER (WHERE c.dt=d),0)::text,'today_count',count(*) FILTER (WHERE c.dt=d),
          'has_sheet',coalesce(bool_or(c.source='sheet'),false)) FROM cur c),
      'days',(SELECT coalesce(jsonb_agg(jsonb_build_object('date',g.dt,'total_vnd',g.total::text,'count',g.n,'rows',g.rows) ORDER BY g.dt DESC),'[]'::jsonb)
        FROM (SELECT c.dt,sum(c.amount) AS total,count(*) AS n,jsonb_agg(c.js ORDER BY c.amount DESC,c.name COLLATE "C",c.source,c.id) AS rows
                FROM cur c WHERE c.dt IS NOT NULL GROUP BY c.dt) g),
      'undated',(SELECT coalesce(jsonb_agg(c.js ORDER BY c.amount DESC,c.name COLLATE "C",c.source,c.id),'[]'::jsonb) FROM cur c WHERE c.dt IS NULL),
      'customers',(SELECT coalesce(jsonb_agg(jsonb_build_object('customer_id',g.customer_id,'name',g.name,'total_vnd',g.total::text,'count',g.n,
          'undated_vnd',g.undated::text,'undated_count',g.undated_n,'last_date',g.last_date,'book_month',g.book_month)
          ORDER BY g.total DESC,g.undated DESC,g.name COLLATE "C",g.customer_id),'[]'::jsonb)
        FROM (SELECT c.customer_id,c.name,coalesce(sum(c.amount) FILTER (WHERE c.dt IS NOT NULL),0) AS total,count(*) FILTER (WHERE c.dt IS NOT NULL) AS n,
                     coalesce(sum(c.amount) FILTER (WHERE c.dt IS NULL),0) AS undated,count(*) FILTER (WHERE c.dt IS NULL) AS undated_n,
                     max(c.dt) AS last_date,max(c.book_month) AS book_month
                FROM cur c GROUP BY c.customer_id,c.name) g),
      'offsets',(SELECT coalesce(jsonb_agg(jsonb_build_object('id',o.id,'date',o.date,'amount_vnd',o.amount_vnd::text,
          'source_customer_id',o.source_customer_id,'source_name',s.name,'target_customer_id',o.target_customer_id,'target_name',t.name)
          ORDER BY o.date DESC,o.id DESC),'[]'::jsonb)
        FROM sokhach.offset_pair o JOIN sokhach.customer s ON s.id=o.source_customer_id JOIN sokhach.customer t ON t.id=o.target_customer_id
       WHERE o.voided_by_event IS NULL AND date_trunc('month',o.date)::date=v_month),
      'voided',(SELECT coalesce(jsonb_agg(jsonb_build_object('pid',r.pid,'customer_id',r.customer_id,'name',a.name,'date',r.date,
          'amount_vnd',r.amount_vnd::text,'voided_on',r.voided_on,'void_reason',r.void_reason) ORDER BY r.date DESC,r.id DESC),'[]'::jsonb)
        FROM sokhach.receipt r JOIN act a ON a.id=r.customer_id
       WHERE r.voided_on IS NOT NULL AND date_trunc('month',r.date)::date=v_month
         AND NOT EXISTS (SELECT 1 FROM sokhach.offset_pair o WHERE o.target_receipt_id=r.id))));
END $function$;
ALTER FUNCTION sokhach.get_receipt_book(date) OWNER TO sokhach_owner;
REVOKE ALL ON FUNCTION sokhach.get_receipt_book(date) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION sokhach.get_receipt_book(date) TO sokhach_app;
GRANT EXECUTE ON FUNCTION sokhach.get_receipt_book(date) TO sokhach_reader;

-- FUNCTION sokhach.get_receipt_image(bigint,bigint)
CREATE OR REPLACE FUNCTION sokhach.get_receipt_image(customer_id bigint, image_id bigint)
 RETURNS jsonb
 LANGUAGE plpgsql
 STABLE SECURITY DEFINER
 SET search_path TO 'pg_catalog', 'sokhach', 'pg_temp'
AS $function$
DECLARE v jsonb;
BEGIN
 SELECT jsonb_build_object('id',i.id,'content_type',i.content_type,'sha256',i.sha256,'removed',i.removed_by_event IS NOT NULL,
   'data_base64',translate(encode(i.data,'base64'),E'\n',''))
 INTO v FROM sokhach.receipt_image i WHERE i.id=get_receipt_image.image_id AND i.customer_id=get_receipt_image.customer_id;
 IF v IS NULL THEN RAISE EXCEPTION 'IMAGE_NOT_FOUND'; END IF;
 RETURN v;
END $function$;
ALTER FUNCTION sokhach.get_receipt_image(bigint,bigint) OWNER TO sokhach_owner;
REVOKE ALL ON FUNCTION sokhach.get_receipt_image(bigint,bigint) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION sokhach.get_receipt_image(bigint,bigint) TO sokhach_app;
GRANT EXECUTE ON FUNCTION sokhach.get_receipt_image(bigint,bigint) TO sokhach_reader;

-- FUNCTION sokhach.get_receivables_detail(bigint,date)
CREATE OR REPLACE FUNCTION sokhach.get_receivables_detail(p_customer bigint, p_month date)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'pg_catalog', 'sokhach', 'pg_temp'
AS $function$
-- Ngăn kéo ma trận (29/10/2026): số tháng lấy đúng dòng Tổng tháng của get_ledger (DA-THU-01: tháng
-- sổ gốc dùng phát sinh/đã thu Sheet, đã thu theo ngày thu), danh sách gồm chuyến web và dòng chuyến
-- sổ gốc. outstanding_vnd là ô ma trận (nợ còn lại sau phân bổ nợ cũ trước); allocated_vnd là thu đã
-- phân bổ vào kỳ, để giải thích vì sao phát sinh − đã thu có thể khác còn lại. receipts (29/10/2026): phiếu
-- thu chưa hủy có ngày thu trong tháng, kèm các kỳ đang được trừ (dòng phân bổ hiệu lực).
-- credit_applied_vnd (CAN-DU-01, 30/10/2026): số thô − ô ma trận; dương là khoản dư tháng khác cấn vào tháng
-- này, âm là khoản dư của tháng này đã cấn sang tháng còn nợ.
DECLARE v_active boolean; v_ledger jsonb; v_row jsonb; v_allocated bigint; v_opening boolean;
        v_raw bigint; v_month text := p_month::text;
BEGIN
    PERFORM sokhach._actor();
    IF p_month IS NULL OR date_trunc('month', p_month)::date <> p_month THEN
        RAISE EXCEPTION 'INVALID_MONTH';
    END IF;
    SELECT EXISTS (SELECT 1 FROM sokhach.cutover_customer cc JOIN sokhach.cutover c ON c.id=cc.cutover_id
        WHERE cc.customer_id=p_customer AND cc.status='active' AND c.status='active') INTO v_active;
    IF NOT v_active THEN RAISE EXCEPTION 'CUSTOMER_NOT_FOUND'; END IF;
    v_ledger := sokhach.get_ledger(p_customer);
    SELECT m INTO v_row FROM jsonb_array_elements(v_ledger->'months') m WHERE m->>'month'=v_month;
    SELECT coalesce(sum(l.amount_vnd),0) - coalesce((SELECT sum(o.amount_vnd) FROM sokhach.v_offset_outgoing o
        WHERE o.customer_id=p_customer AND o.debt_month=p_month),0) INTO v_allocated
      FROM sokhach.v_receipt_line_active l WHERE l.customer_id=p_customer AND l.debt_month=p_month;
    SELECT EXISTS (SELECT 1 FROM jsonb_array_elements(v_ledger->'opening') o WHERE o->>'month'=v_month) INTO v_opening;
    SELECT coalesce(sum(outstanding_vnd),0) INTO v_raw FROM sokhach.v_outstanding_month_raw
      WHERE customer_id=p_customer AND debt_month=p_month;
    RETURN jsonb_build_object('status','active','customer_id',p_customer,'month',v_month,
        'outstanding_vnd',coalesce(v_row->>'outstanding_vnd','0'),
        'charges_vnd',coalesce(v_row->>'charges_vnd','0'),'received_vnd',coalesce(v_row->>'received_vnd','0'),
        'allocated_vnd',v_allocated::text,'opening',v_opening,
        'credit_applied_vnd',(v_raw-coalesce((v_row->>'outstanding_vnd')::bigint,0))::text,
        'receipts',(SELECT coalesce(jsonb_agg(jsonb_build_object('id',r->'id','pid',r->'pid','date',r->'date',
            'method',r->'method','reference',r->'reference','amount_vnd',r->'amount_vnd',
            'counterparty_name',r->'counterparty_name',
            'allocations',(SELECT coalesce(jsonb_agg(jsonb_build_object('month',a.month,'kind',a.kind,'amount_vnd',a.amount::text)
                ORDER BY a.month,a.kind),'[]'::jsonb) FROM (SELECT x->>'month' AS month,x->>'kind' AS kind,
                sum((x->>'amount_vnd')::bigint) AS amount FROM jsonb_array_elements(r->'allocations') x
                WHERE x->>'superseded_by_event' IS NULL GROUP BY 1,2) a))
            ORDER BY r->>'date',r->>'pid' COLLATE "C"),'[]'::jsonb)
          FROM jsonb_array_elements(v_ledger->'receipts') r
          WHERE r->>'voided_on' IS NULL AND date_trunc('month',(r->>'date')::date)::date=p_month),
        'trips',(SELECT coalesce(jsonb_agg(jsonb_build_object('id',t->'id','month',t->'month',
            'event_date',t->'event_date','container',t->'container','carrier',t->'carrier','status',t->'status',
            'unit_price_vnd',t->'unit_price_vnd','other_fee_vnd',t->'other_fee_vnd','amount_vnd',t->'amount_vnd',
            'historical',false) ORDER BY (t->>'id')::bigint),'[]'::jsonb)
          FROM jsonb_array_elements(v_ledger->'trips') t WHERE t->>'month'=v_month)
        || (SELECT coalesce(jsonb_agg(jsonb_build_object('id',l->'id','month',l->'month',
            'event_date',l->'current'->'event_date','container',l->'current'->'container',
            'carrier',l->'current'->'carrier','status','confirmed',
            'unit_price_vnd',l->'current'->'unit_price_vnd','other_fee_vnd',l->'current'->'other_fee_vnd',
            'amount_vnd',l->'current'->'counted_vnd','historical',true) ORDER BY (l->>'id')::bigint),'[]'::jsonb)
          FROM jsonb_array_elements(v_ledger->'legacy_rows') l WHERE l->>'kind'='trip' AND l->>'month'=v_month));
END $function$;
ALTER FUNCTION sokhach.get_receivables_detail(bigint,date) OWNER TO sokhach_owner;
REVOKE ALL ON FUNCTION sokhach.get_receivables_detail(bigint,date) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION sokhach.get_receivables_detail(bigint,date) TO sokhach_app;
GRANT EXECUTE ON FUNCTION sokhach.get_receivables_detail(bigint,date) TO sokhach_reader;

-- FUNCTION sokhach.get_receivables_matrix(integer)
CREATE OR REPLACE FUNCTION sokhach.get_receivables_matrix(p_year integer)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'pg_catalog', 'sokhach', 'pg_temp'
AS $function$
DECLARE d date := (now() AT TIME ZONE 'Asia/Ho_Chi_Minh')::date;
BEGIN
  IF p_year IS NULL OR p_year < 2000 OR p_year > extract(year FROM d)::int + 1 THEN
    RAISE EXCEPTION 'INVALID_YEAR'; END IF;
  PERFORM sokhach._actor();
  RETURN (WITH base AS (
    SELECT c.id, c.name, c.commodity_id, c.transport_mode,
           coalesce(sum(v.outstanding_vnd),0)::bigint AS total_all,
           coalesce(sum(v.outstanding_vnd) FILTER (WHERE extract(year FROM v.debt_month)=p_year),0)::bigint AS total_year,
           min(v.debt_month) FILTER (WHERE v.outstanding_vnd>0) AS oldest
      FROM sokhach.customer c
      JOIN sokhach.cutover_customer cc ON cc.customer_id=c.id AND cc.status='active'
      JOIN sokhach.cutover x ON x.id=cc.cutover_id AND x.status='active'
      LEFT JOIN sokhach.v_outstanding_month v ON v.customer_id=c.id
     WHERE NOT c.archived
     GROUP BY c.id, c.name, c.commodity_id, c.transport_mode
    HAVING coalesce(bool_or(v.outstanding_vnd <> 0), false)),
  cells AS (
    SELECT b.id, g.mm, coalesce(sum(v.outstanding_vnd),0)::bigint AS val
      FROM base b CROSS JOIN generate_series(1,12) AS g(mm)
      LEFT JOIN sokhach.v_outstanding_month v
        ON v.customer_id=b.id AND extract(year FROM v.debt_month)=p_year AND extract(month FROM v.debt_month)=g.mm
     GROUP BY b.id, g.mm),
  cust AS (
    SELECT jsonb_build_object('customer_id',b.id,'name',b.name,'commodity',m.name,
      'transport_mode',b.transport_mode,
      'months',(SELECT jsonb_object_agg(mm::text, val::text) FROM cells WHERE cells.id=b.id),
      'total_year_vnd',b.total_year::text,'total_all_vnd',b.total_all::text,
      'oldest_open_month',b.oldest::text) o
      FROM base b LEFT JOIN sokhach.commodity m ON m.id=b.commodity_id
     ORDER BY b.total_all DESC, b.name COLLATE "C", b.id)
  SELECT jsonb_build_object('as_of',d::text,'year',p_year,
    'years_available',(SELECT coalesce(jsonb_agg(DISTINCT y ORDER BY y),'[]'::jsonb) FROM
      (SELECT extract(year FROM debt_month)::int y FROM sokhach.v_outstanding_month
       UNION SELECT extract(year FROM d)::int) yy),
    'customers',(SELECT coalesce(jsonb_agg(o),'[]'::jsonb) FROM cust),
    'grand_total_year_vnd',(SELECT coalesce(sum(total_year),0)::bigint::text FROM base),
    'grand_total_all_vnd',(SELECT coalesce(sum(total_all),0)::bigint::text FROM base)));
END $function$;
ALTER FUNCTION sokhach.get_receivables_matrix(integer) OWNER TO sokhach_owner;
REVOKE ALL ON FUNCTION sokhach.get_receivables_matrix(integer) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION sokhach.get_receivables_matrix(integer) TO sokhach_app;
GRANT EXECUTE ON FUNCTION sokhach.get_receivables_matrix(integer) TO sokhach_reader;

-- FUNCTION sokhach.get_reminders()
CREATE OR REPLACE FUNCTION sokhach.get_reminders()
 RETURNS jsonb
 LANGUAGE plpgsql
 STABLE SECURITY DEFINER
 SET search_path TO 'pg_catalog', 'sokhach', 'pg_temp'
AS $function$
BEGIN
 RETURN jsonb_build_object('reminders',(SELECT coalesce(jsonb_agg(jsonb_build_object(
    'customer_id',t.customer_id,'last_reminded',t.last_reminded,'reminder_count',t.reminder_count,'last_source',t.last_source)
    ORDER BY t.last_reminded DESC),'[]'::jsonb)
  FROM (SELECT customer_id,max(reminded_at) AS last_reminded,count(*) AS reminder_count,
          (array_agg(source ORDER BY reminded_at DESC,id DESC))[1] AS last_source
        FROM sokhach.reminder_log GROUP BY customer_id) t));
END $function$;
ALTER FUNCTION sokhach.get_reminders() OWNER TO sokhach_owner;
REVOKE ALL ON FUNCTION sokhach.get_reminders() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION sokhach.get_reminders() TO sokhach_app;
GRANT EXECUTE ON FUNCTION sokhach.get_reminders() TO sokhach_reader;

-- FUNCTION sokhach.get_safety_net(jsonb)
CREATE OR REPLACE FUNCTION sokhach.get_safety_net(p_options jsonb)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'pg_catalog', 'sokhach', 'pg_temp'
AS $function$
-- LUOI-AN-TOAN-01. Chỉ chạy trong giao dịch REPEATABLE READ READ ONLY (adapter read_only=True): mọi phần thấy cùng một lúc của sổ và
-- không ghi được gì. Trả mã sổ, mã lỗi, số đếm, phiên bản, dấu vân md5; không tên khách, không số tiền.
-- p_options: event_upto (mốc kiểm 4 lượt trước), ledger_slice/ledger_slices (phần sổ so get_ledger lượt này; 0 phần là bỏ qua),
-- settle_seconds (mặc định 600).
DECLARE v_id bigint; v_total numeric; v_alloc jsonb := '[]'::jsonb; v_dash jsonb; v_debt jsonb; v_codes text[]; v_bad bigint[];
    v_archived bigint[];
    v_slice int; v_slices int; v_settle int; v_upto bigint; v_ledger jsonb; v_checked int := 0; v_wrong bigint[] := '{}';
BEGIN
    PERFORM sokhach._actor();
    IF current_setting('transaction_read_only') <> 'on'
       OR current_setting('transaction_isolation') NOT IN ('repeatable read', 'serializable') THEN
        RAISE EXCEPTION 'SNAPSHOT_REQUIRED';
    END IF;
    IF jsonb_typeof(p_options) IS DISTINCT FROM 'object' THEN RAISE EXCEPTION 'INVALID_OPTIONS'; END IF;
    v_slices := coalesce((p_options->>'ledger_slices')::int, 0);
    v_slice := coalesce((p_options->>'ledger_slice')::int, 0);
    v_settle := coalesce((p_options->>'settle_seconds')::int, 600);
    v_upto := (p_options->>'event_upto')::bigint;
    IF v_slices < 0 OR v_slice < 0 OR (v_slices > 0 AND v_slice >= v_slices) OR v_settle NOT BETWEEN 0 AND 86400 OR v_upto < 0 THEN
        RAISE EXCEPTION 'INVALID_OPTIONS';
    END IF;
    -- Kiểm 1: ba luật của _check_allocations cho mọi sổ có phiếu (dòng chia chỉ có ở sổ có phiếu).
    FOR v_id IN SELECT DISTINCT customer_id FROM sokhach.receipt ORDER BY 1 LOOP
        BEGIN
            PERFORM sokhach._check_allocations(v_id);
        EXCEPTION WHEN raise_exception THEN
            v_alloc := v_alloc || jsonb_build_array(jsonb_build_object('customer_id', v_id, 'code', SQLERRM));
        END;
    END LOOP;
    -- Kiểm 2: con số Tổng quan hiển thị so với tổng các sổ có mốc nạp đang hiệu lực (v_outstanding_month).
    v_dash := sokhach.get_dashboard();
    v_debt := sokhach.get_dashboard_debt();
    WITH books AS (
        SELECT c.id, c.archived, coalesce(sum(v.outstanding_vnd), 0)::numeric AS total
          FROM sokhach.customer c
          JOIN sokhach.cutover_customer cc ON cc.customer_id = c.id AND cc.status = 'active'
          JOIN sokhach.cutover x ON x.id = cc.cutover_id AND x.status = 'active'
          LEFT JOIN sokhach.v_outstanding_month v ON v.customer_id = c.id
         GROUP BY c.id, c.archived),
      live AS (SELECT id, total FROM books WHERE NOT archived),
      pos AS (SELECT id, total FROM live WHERE total > 0),
      listed AS (SELECT (e->>'customer_id')::bigint AS id, (e->>'outstanding_vnd')::numeric AS total
          FROM jsonb_array_elements(v_debt->'customers') e),
      list_wrong AS (SELECT coalesce(pos.id, listed.id) AS id FROM pos FULL JOIN listed ON listed.id = pos.id
          WHERE pos.total IS DISTINCT FROM listed.total),
      sums AS (SELECT (SELECT coalesce(sum(total), 0) FROM pos) AS pos_sum, (SELECT count(*) FROM pos) AS pos_n,
          (SELECT coalesce(sum(total), 0) FROM live WHERE total < 0) AS neg_sum, (SELECT count(*) FROM live WHERE total < 0) AS neg_n)
    SELECT array_remove(ARRAY[
            CASE WHEN (v_dash->'receivable'->>'total_vnd')::numeric IS DISTINCT FROM s.pos_sum THEN 'RECEIVABLE_TOTAL' END,
            CASE WHEN (v_dash->'receivable'->>'customers')::bigint IS DISTINCT FROM s.pos_n THEN 'RECEIVABLE_COUNT' END,
            CASE WHEN (v_dash->'credit'->>'total_vnd')::numeric IS DISTINCT FROM s.neg_sum THEN 'CREDIT_TOTAL' END,
            CASE WHEN (v_dash->'credit'->>'customers')::bigint IS DISTINCT FROM s.neg_n THEN 'CREDIT_COUNT' END,
            CASE WHEN (SELECT coalesce(sum((e->>'receivable_vnd')::numeric), 0) FROM jsonb_array_elements(v_dash->'by_commodity') e)
                IS DISTINCT FROM s.pos_sum THEN 'COMMODITY_TOTAL' END,
            CASE WHEN (v_debt->>'receivable_vnd')::numeric IS DISTINCT FROM s.pos_sum THEN 'DEBT_TOTAL' END,
            CASE WHEN (SELECT coalesce(sum((e->>'receivable_vnd')::numeric), 0) FROM jsonb_array_elements(v_debt->'due_tiers') e)
                IS DISTINCT FROM s.pos_sum THEN 'DEBT_TIERS' END,
            CASE WHEN EXISTS (SELECT 1 FROM list_wrong) THEN 'DEBT_LIST' END,
            CASE WHEN EXISTS (SELECT 1 FROM books WHERE archived AND total <> 0) THEN 'ARCHIVED_BALANCE' END], NULL),
        ARRAY(SELECT id FROM list_wrong ORDER BY 1), ARRAY(SELECT id FROM books WHERE archived AND total <> 0 ORDER BY 1)
      INTO v_codes, v_bad, v_archived FROM sums s;
    -- Kiểm 2, phần get_ledger: mở cả sổ tốn ~0,1 giây mỗi sổ nên mỗi lượt chỉ so một phần (mã sổ mod ledger_slices).
    IF v_slices > 0 THEN
        FOR v_id, v_total IN
            SELECT c.id, coalesce(sum(v.outstanding_vnd), 0)::numeric
              FROM sokhach.customer c
              JOIN sokhach.cutover_customer cc ON cc.customer_id = c.id AND cc.status = 'active'
              JOIN sokhach.cutover x ON x.id = cc.cutover_id AND x.status = 'active'
              LEFT JOIN sokhach.v_outstanding_month v ON v.customer_id = c.id
             WHERE c.id % v_slices = v_slice
             GROUP BY c.id ORDER BY c.id
        LOOP
            v_checked := v_checked + 1;
            IF (sokhach.get_ledger(v_id)->>'total_outstanding_vnd')::numeric IS DISTINCT FROM v_total THEN
                v_wrong := v_wrong || v_id;
            END IF;
        END LOOP;
        v_ledger := jsonb_build_object('slice', v_slice, 'slices', v_slices, 'checked', v_checked, 'customers', to_jsonb(v_wrong));
    END IF;
    RETURN jsonb_build_object('books', (SELECT count(*) FROM sokhach.customer), 'allocations', v_alloc,
        'totals', jsonb_build_object('codes', to_jsonb(v_codes), 'customers', to_jsonb(v_bad), 'archived', to_jsonb(v_archived)),
        'ledger', v_ledger,
        'fingerprints', sokhach._safety_fingerprints(), 'events', sokhach._safety_events(v_upto, make_interval(secs => v_settle)),
        -- Audit SQL 23/11/2026 (F1): bảng băm định nghĩa để v7_safety_net.py so với tools/v7_catalog_manifest.json của release.
        'catalog', sokhach._catalog_manifest());
END $function$;
ALTER FUNCTION sokhach.get_safety_net(jsonb) OWNER TO sokhach_owner;
REVOKE ALL ON FUNCTION sokhach.get_safety_net(jsonb) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION sokhach.get_safety_net(jsonb) TO sokhach_app;

-- FUNCTION sokhach.get_trip_month(date)
CREATE OR REPLACE FUNCTION sokhach.get_trip_month(p_month date)
 RETURNS jsonb
 LANGUAGE plpgsql
 STABLE SECURITY DEFINER
 SET search_path TO 'pg_catalog', 'sokhach', 'pg_temp'
AS $function$
-- BAO-CAO-THANG-01. Chuyến có container của mọi sổ đang hoạt động, ngày chuyến từ 3 ngày trước tháng tới 3 ngày sau tháng (để API ghép
-- với Sheet theo luật lệch tối đa 3 ngày của NGUON-CHUYEN-01; API tự lọc đúng tháng khi đếm). Chuyến web: chưa xóa, không bị loại.
-- Dòng chuyến sổ gốc: bản sửa mới nhất nếu có, chưa xóa. Chuyến không có ngày hoặc không có container không ghép được nên không trả.
-- Kèm danh sách sổ (tên, mặt hàng, biển/bộ) để trang ghép tên tab Sheet với sổ web.
DECLARE v_lo date; v_hi date;
BEGIN
  PERFORM sokhach._actor();
  IF p_month IS NULL OR date_trunc('month', p_month)::date <> p_month THEN RAISE EXCEPTION 'INVALID_MONTH'; END IF;
  v_lo := p_month - 3;
  v_hi := (p_month + interval '1 month')::date + 2;
  RETURN (WITH act AS (
      SELECT c.id,c.name,c.commodity_id,c.transport_mode,cc.cutover_id FROM sokhach.customer c
        JOIN sokhach.cutover_customer cc ON cc.customer_id=c.id AND cc.status='active'
        JOIN sokhach.cutover x ON x.id=cc.cutover_id AND x.status='active'
       WHERE NOT c.archived),
    web AS (SELECT t.customer_id,t.event_date AS dt,t.container AS cont,'web'::text AS src
        FROM sokhach.v_trip_current t JOIN act ON act.id=t.customer_id
       WHERE NOT t.deleted AND t.status<>'rejected' AND t.event_date BETWEEN v_lo AND v_hi),
    leg AS (SELECT l.customer_id,
        CASE WHEN r.id IS NULL THEN sokhach._legacy_date(l.display->>'date') ELSE r.event_date END AS dt,
        CASE WHEN r.id IS NULL THEN l.display->>'container' ELSE r.container END AS cont,'legacy'::text AS src
        FROM sokhach.legacy_row l JOIN act ON (act.id,act.cutover_id)=(l.customer_id,l.cutover_id)
        LEFT JOIN LATERAL (SELECT x.id,x.event_date,x.container,x.deleted FROM sokhach.legacy_trip_rev x
            WHERE x.legacy_row_id=l.id ORDER BY x.id DESC LIMIT 1) r ON true
       WHERE l.kind='trip' AND NOT coalesce(r.deleted,false)),
    trips AS (SELECT * FROM web UNION ALL SELECT * FROM leg WHERE dt BETWEEN v_lo AND v_hi)
  SELECT jsonb_build_object('month',p_month,
    'books',(SELECT coalesce(jsonb_agg(jsonb_build_object('id',a.id,'name',a.name,'commodity',cm.name,'transport_mode',a.transport_mode)
        ORDER BY a.id),'[]'::jsonb) FROM act a LEFT JOIN sokhach.commodity cm ON cm.id=a.commodity_id),
    'trips',(SELECT coalesce(jsonb_agg(jsonb_build_object('customer_id',t.customer_id,'date',t.dt,'container',t.cont,'source',t.src)
        ORDER BY t.customer_id,t.dt,t.cont),'[]'::jsonb) FROM trips t WHERE nullif(sokhach._normalize_key(t.cont),'') IS NOT NULL)));
END $function$;
ALTER FUNCTION sokhach.get_trip_month(date) OWNER TO sokhach_owner;
REVOKE ALL ON FUNCTION sokhach.get_trip_month(date) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION sokhach.get_trip_month(date) TO sokhach_app;
GRANT EXECUTE ON FUNCTION sokhach.get_trip_month(date) TO sokhach_reader;

-- FUNCTION sokhach.get_zalo_links()
CREATE OR REPLACE FUNCTION sokhach.get_zalo_links()
 RETURNS jsonb
 LANGUAGE plpgsql
 STABLE SECURITY DEFINER
 SET search_path TO 'pg_catalog', 'sokhach', 'pg_temp'
AS $function$
BEGIN
 RETURN jsonb_build_object('links',(SELECT coalesce(jsonb_agg(jsonb_build_object(
    'conversation_id',l.conversation_id,'customer_id',l.customer_id,'customer_name',c.name,
    'linked_by',l.linked_by,'linked_at',l.linked_at) ORDER BY l.conversation_id,c.name,l.customer_id),'[]'::jsonb)
  FROM sokhach.zalo_link l JOIN sokhach.customer c ON c.id=l.customer_id WHERE l.unlinked_at IS NULL));
END $function$;
ALTER FUNCTION sokhach.get_zalo_links() OWNER TO sokhach_owner;
REVOKE ALL ON FUNCTION sokhach.get_zalo_links() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION sokhach.get_zalo_links() TO sokhach_app;
GRANT EXECUTE ON FUNCTION sokhach.get_zalo_links() TO sokhach_reader;

-- FUNCTION sokhach.guard_cutover_customer_status()
CREATE OR REPLACE FUNCTION sokhach.guard_cutover_customer_status()
 RETURNS trigger
 LANGUAGE plpgsql
 SET search_path TO 'pg_catalog', 'sokhach', 'pg_temp'
AS $function$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'cutover customer deletion forbidden';
    END IF;
    -- Cấm thêm khách sau khi mốc verified; lệnh chuyển cũng khóa mốc trước khách.
    PERFORM 1 FROM sokhach.cutover WHERE id = NEW.cutover_id FOR UPDATE;
    IF TG_OP = 'INSERT' THEN
        IF NEW.status <> 'draft'
           OR NOT EXISTS (SELECT 1 FROM sokhach.cutover
                       WHERE id = NEW.cutover_id AND status = 'draft') THEN
            RAISE EXCEPTION 'cutover customer insert forbidden';
        END IF;
        RETURN NEW;
    END IF;
    -- Khách verified trước mốc; khách active chỉ sau mốc active.
    IF NOT ((OLD.status = 'draft' AND NEW.status = 'verified'
             AND EXISTS (SELECT 1 FROM sokhach.cutover WHERE id = OLD.cutover_id AND status = 'draft'))
         OR (OLD.status = 'verified' AND NEW.status = 'active'
             AND EXISTS (SELECT 1 FROM sokhach.cutover WHERE id = OLD.cutover_id AND status = 'active'))) THEN
        RAISE EXCEPTION 'cutover customer transition order forbidden';
    END IF;
    IF ROW(OLD.customer_id, OLD.cutover_id, OLD.expected_control_total_vnd,
           OLD.report_sha256, OLD.source_rows, OLD.imported_rows,
           OLD.quarantined_rows, OLD.skipped_with_reason_rows, OLD.unresolved_exceptions)
       IS DISTINCT FROM
       ROW(NEW.customer_id, NEW.cutover_id, NEW.expected_control_total_vnd,
           NEW.report_sha256, NEW.source_rows, NEW.imported_rows,
           NEW.quarantined_rows, NEW.skipped_with_reason_rows, NEW.unresolved_exceptions)
       OR NOT ((OLD.status = 'draft' AND NEW.status = 'verified')
            OR (OLD.status = 'verified' AND NEW.status = 'active')) THEN
        RAISE EXCEPTION 'cutover customer transition forbidden';
    END IF;
    RETURN NEW;
END $function$;
ALTER FUNCTION sokhach.guard_cutover_customer_status() OWNER TO sokhach_owner;
REVOKE ALL ON FUNCTION sokhach.guard_cutover_customer_status() FROM PUBLIC;

-- FUNCTION sokhach.guard_cutover_evidence()
CREATE OR REPLACE FUNCTION sokhach.guard_cutover_evidence()
 RETURNS trigger
 LANGUAGE plpgsql
 SET search_path TO 'pg_catalog', 'sokhach', 'pg_temp'
AS $function$
DECLARE
    v_customer_id bigint;
    v_cutover_id bigint;
    v_cutover_status text;
    v_customer_status text;
BEGIN
    v_customer_id := CASE WHEN TG_OP = 'DELETE' THEN OLD.customer_id ELSE NEW.customer_id END;
    v_cutover_id := CASE WHEN TG_OP = 'DELETE' THEN OLD.cutover_id ELSE NEW.cutover_id END;
    IF TG_OP = 'UPDATE' THEN
        IF (OLD.customer_id, OLD.cutover_id)
            IS DISTINCT FROM (NEW.customer_id, NEW.cutover_id) THEN
            RAISE EXCEPTION 'cutover evidence owner change forbidden';
        END IF;
    END IF;
    -- Cùng thứ tự khóa với import/verify/activate; đợi chuyển trạng thái xong rồi đọc.
    -- Lệnh phải lấy khóa mốc rồi khách TRƯỚC DML; UPDATE/DELETE có thể khóa
    -- hàng chứng cứ trước BEFORE ROW trigger. Test DML trực tiếp trước khi cấp quyền.
    SELECT status INTO v_cutover_status FROM sokhach.cutover
        WHERE id = v_cutover_id FOR UPDATE;
    SELECT status INTO v_customer_status FROM sokhach.cutover_customer
        WHERE customer_id = v_customer_id AND cutover_id = v_cutover_id FOR UPDATE;
    IF v_cutover_status IS NULL OR v_customer_status IS NULL
        OR v_cutover_status <> 'draft' OR v_customer_status <> 'draft' THEN
        RAISE EXCEPTION 'cutover evidence frozen';
    END IF;
    IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
    RETURN NEW;
END $function$;
ALTER FUNCTION sokhach.guard_cutover_evidence() OWNER TO sokhach_owner;
REVOKE ALL ON FUNCTION sokhach.guard_cutover_evidence() FROM PUBLIC;

-- FUNCTION sokhach.guard_cutover_status()
CREATE OR REPLACE FUNCTION sokhach.guard_cutover_status()
 RETURNS trigger
 LANGUAGE plpgsql
 SET search_path TO 'pg_catalog', 'sokhach', 'pg_temp'
AS $function$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'cutover deletion forbidden';
    END IF;
    IF TG_OP = 'INSERT' THEN
        IF NEW.status <> 'draft' THEN RAISE EXCEPTION 'cutover must start draft'; END IF;
        RETURN NEW;
    END IF;
    IF ROW(OLD.id, OLD.name, OLD.source, OLD.source_sha256, OLD.frozen_at,
           OLD.control_total_vnd, OLD.created_by, OLD.created_at)
       IS DISTINCT FROM
       ROW(NEW.id, NEW.name, NEW.source, NEW.source_sha256, NEW.frozen_at,
           NEW.control_total_vnd, NEW.created_by, NEW.created_at)
       OR NOT ((OLD.status = 'draft' AND NEW.status = 'verified')
            OR (OLD.status = 'verified' AND NEW.status = 'active')) THEN
        RAISE EXCEPTION 'cutover status transition forbidden';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM sokhach.cutover_customer
                   WHERE cutover_id = OLD.id)
       OR EXISTS (SELECT 1 FROM sokhach.cutover_customer
                  WHERE cutover_id = OLD.id AND status <> 'verified') THEN
        RAISE EXCEPTION 'cutover customers not all verified';
    END IF;
    RETURN NEW;
END $function$;
ALTER FUNCTION sokhach.guard_cutover_status() OWNER TO sokhach_owner;
REVOKE ALL ON FUNCTION sokhach.guard_cutover_status() FROM PUBLIC;

-- FUNCTION sokhach.guard_offset_pair()
CREATE OR REPLACE FUNCTION sokhach.guard_offset_pair()
 RETURNS trigger
 LANGUAGE plpgsql
 SET search_path TO 'pg_catalog', 'sokhach', 'pg_temp'
AS $function$
BEGIN
    IF TG_OP='DELETE' THEN RAISE EXCEPTION 'OFFSET_PAIR_IMMUTABLE'; END IF;
    IF ROW(NEW.id,NEW.source_customer_id,NEW.target_customer_id,NEW.target_receipt_id,
        NEW.source_pid,NEW.amount_vnd,NEW.created_by_event)
       IS DISTINCT FROM ROW(OLD.id,OLD.source_customer_id,OLD.target_customer_id,OLD.target_receipt_id,
        OLD.source_pid,OLD.amount_vnd,OLD.created_by_event)
       OR OLD.voided_by_event IS NOT NULL
    THEN RAISE EXCEPTION 'OFFSET_PAIR_IMMUTABLE'; END IF;
    RETURN NEW;
END $function$;
ALTER FUNCTION sokhach.guard_offset_pair() OWNER TO sokhach_owner;
REVOKE ALL ON FUNCTION sokhach.guard_offset_pair() FROM PUBLIC;

-- FUNCTION sokhach.guard_receipt_change()
CREATE OR REPLACE FUNCTION sokhach.guard_receipt_change()
 RETURNS trigger
 LANGUAGE plpgsql
 SET search_path TO 'pg_catalog', 'sokhach', 'pg_temp'
AS $function$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'receipt deletion forbidden';
    END IF;
    IF ROW(OLD.id, OLD.customer_id, OLD.pid, OLD.amount_vnd, OLD.created_by_event)
        IS DISTINCT FROM ROW(NEW.id, NEW.customer_id, NEW.pid, NEW.amount_vnd, NEW.created_by_event)
        OR OLD.voided_on IS NOT NULL
        OR (OLD.voided_on IS NULL AND NEW.voided_on IS NOT NULL
            AND (OLD.date IS DISTINCT FROM NEW.date OR OLD.method IS DISTINCT FROM NEW.method OR OLD.reference IS DISTINCT FROM NEW.reference
                 OR OLD.meta_changed_by_event IS DISTINCT FROM NEW.meta_changed_by_event))
        OR (OLD.voided_on IS NULL AND NEW.voided_on IS NULL
            AND ROW(OLD.void_reason, OLD.voided_by, OLD.voided_by_event)
                IS DISTINCT FROM ROW(NEW.void_reason, NEW.voided_by, NEW.voided_by_event))
        OR (OLD.voided_on IS NULL AND NEW.voided_on IS NULL
            AND ROW(OLD.date, OLD.method, OLD.reference) IS DISTINCT FROM ROW(NEW.date, NEW.method, NEW.reference)
            AND NEW.meta_changed_by_event IS NOT DISTINCT FROM OLD.meta_changed_by_event)
        OR (OLD.voided_on IS NULL AND NEW.voided_on IS NULL
            AND ROW(OLD.date, OLD.method, OLD.reference) IS NOT DISTINCT FROM ROW(NEW.date, NEW.method, NEW.reference)
            AND NEW.meta_changed_by_event IS DISTINCT FROM OLD.meta_changed_by_event)
        OR (OLD.voided_on IS NULL AND NEW.voided_on IS NOT NULL
            AND NEW.voided_by_event IS NULL) THEN
        RAISE EXCEPTION 'receipt change forbidden';
    END IF;
    RETURN NEW;
END $function$;
ALTER FUNCTION sokhach.guard_receipt_change() OWNER TO sokhach_owner;
REVOKE ALL ON FUNCTION sokhach.guard_receipt_change() FROM PUBLIC;

-- FUNCTION sokhach.guard_receipt_line_change()
CREATE OR REPLACE FUNCTION sokhach.guard_receipt_line_change()
 RETURNS trigger
 LANGUAGE plpgsql
 SET search_path TO 'pg_catalog', 'sokhach', 'pg_temp'
AS $function$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'receipt line deletion forbidden';
    END IF;
    IF ROW(OLD.id, OLD.receipt_id, OLD.customer_id, OLD.debt_month,
           OLD.kind, OLD.amount_vnd, OLD.created_by_event)
        IS DISTINCT FROM ROW(NEW.id, NEW.receipt_id, NEW.customer_id, NEW.debt_month,
                             NEW.kind, NEW.amount_vnd, NEW.created_by_event)
        OR OLD.superseded_by_event IS NOT NULL
        OR NEW.superseded_by_event IS NULL THEN
        RAISE EXCEPTION 'receipt line change forbidden';
    END IF;
    RETURN NEW;
END $function$;
ALTER FUNCTION sokhach.guard_receipt_line_change() OWNER TO sokhach_owner;
REVOKE ALL ON FUNCTION sokhach.guard_receipt_line_change() FROM PUBLIC;

-- FUNCTION sokhach.guard_sheet_cross_customer()
CREATE OR REPLACE FUNCTION sokhach.guard_sheet_cross_customer()
 RETURNS trigger
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'pg_catalog', 'sokhach', 'pg_temp'
AS $function$
DECLARE v_container text;
BEGIN
    IF NEW.source_ref IS NULL OR NEW.source_ref !~ '^sheet:[0-9a-f]{64}:[0-9]+$' THEN RETURN NEW; END IF;
    v_container := sokhach._normalize_key(NEW.container);
    PERFORM pg_advisory_xact_lock(746193,hashtext(v_container));
    IF EXISTS (SELECT 1 FROM sokhach.v_trip_current t WHERE NOT t.deleted
        AND t.customer_id<>NEW.customer_id
        AND sokhach._normalize_key(t.container)=v_container
        AND (sokhach._booking_key(t.booking,t.container,t.event_date)=
             sokhach._booking_key(NEW.booking,NEW.container,NEW.event_date)
             OR abs(t.event_date-NEW.event_date)<=3))
    THEN RAISE EXCEPTION 'SHEET_CROSS_CUSTOMER_MATCH'; END IF;
    RETURN NEW;
END $function$;
ALTER FUNCTION sokhach.guard_sheet_cross_customer() OWNER TO sokhach_owner;
REVOKE ALL ON FUNCTION sokhach.guard_sheet_cross_customer() FROM PUBLIC;

-- FUNCTION sokhach.guard_trip_change()
CREATE OR REPLACE FUNCTION sokhach.guard_trip_change()
 RETURNS trigger
 LANGUAGE plpgsql
 SET search_path TO 'pg_catalog', 'sokhach', 'pg_temp'
AS $function$
BEGIN
    IF TG_OP = 'UPDATE' AND OLD.status = 'pending_review' AND OLD.reviewed_by_event IS NULL
       AND NEW.status IN ('confirmed', 'rejected') AND NEW.reviewed_by_event IS NOT NULL
       AND to_jsonb(OLD) - 'status' - 'reviewed_by_event' = to_jsonb(NEW) - 'status' - 'reviewed_by_event' THEN
        RETURN NEW;
    END IF;
    RAISE EXCEPTION 'immutable row: %.%', TG_TABLE_SCHEMA, TG_TABLE_NAME;
END $function$;
ALTER FUNCTION sokhach.guard_trip_change() OWNER TO sokhach_owner;
REVOKE ALL ON FUNCTION sokhach.guard_trip_change() FROM PUBLIC;

-- FUNCTION sokhach.import_cutover(bigint,bigint,text,bigint,jsonb,jsonb,jsonb,bigint,text)
CREATE OR REPLACE FUNCTION sokhach.import_cutover(customer_id bigint, expected_version bigint, idempotency_key text, cutover_id bigint, openings jsonb, legacy jsonb, month_checks jsonb, expected_control_total bigint, report_sha256 text)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'pg_catalog', 'sokhach', 'pg_temp'
AS $function$
DECLARE v_payload jsonb := jsonb_build_object('command','import_cutover',
        'cutover_id',cutover_id,'openings',openings,'legacy',legacy,
        'month_checks',month_checks,'expected_control_total',expected_control_total,
        'report_sha256',report_sha256);
        v_retry jsonb; v_item jsonb; v_event bigint; v_total numeric;
        v_status text; v_result jsonb;
BEGIN
    PERFORM 1 FROM sokhach.cutover WHERE id=import_cutover.cutover_id FOR UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION 'CUTOVER_NOT_FOUND'; END IF;
    v_retry := sokhach._begin_command(customer_id,expected_version,idempotency_key,v_payload);
    IF v_retry IS NOT NULL THEN RETURN v_retry; END IF;
    SELECT status INTO v_status FROM sokhach.cutover WHERE id=import_cutover.cutover_id;
    IF v_status<>'draft' THEN RAISE EXCEPTION 'CUTOVER_NOT_DRAFT'; END IF;
    IF EXISTS(SELECT 1 FROM sokhach.cutover_customer WHERE cutover_customer.customer_id=import_cutover.customer_id)
       OR EXISTS(SELECT 1 FROM sokhach.trip WHERE trip.customer_id=import_cutover.customer_id)
       OR EXISTS(SELECT 1 FROM sokhach.adjustment WHERE adjustment.customer_id=import_cutover.customer_id)
       OR EXISTS(SELECT 1 FROM sokhach.receipt WHERE receipt.customer_id=import_cutover.customer_id)
       OR EXISTS(SELECT 1 FROM sokhach.event WHERE event.customer_id=import_cutover.customer_id
                 AND event.kind<>'import')
    THEN RAISE EXCEPTION 'CUTOVER_IMPORT_CONFLICT'; END IF;
    IF jsonb_typeof(openings) IS DISTINCT FROM 'array'
       OR jsonb_typeof(legacy) IS DISTINCT FROM 'array'
       OR jsonb_typeof(month_checks) IS DISTINCT FROM 'array'
       OR report_sha256 !~ '^[0-9a-fA-F]{64}$'
       OR expected_control_total IS NULL THEN RAISE EXCEPTION 'INVALID_CUTOVER_INPUT'; END IF;
    IF EXISTS(SELECT 1 FROM jsonb_array_elements(openings) AS x(value)
              WHERE jsonb_typeof(x.value) <> 'object' OR x.value->>'amount_vnd' IS NULL
                 OR x.value->>'debt_month' IS NULL OR x.value->>'source_tab' IS NULL
                 OR x.value->>'source_row' IS NULL)
       OR EXISTS(SELECT 1 FROM jsonb_array_elements(legacy) AS x(value)
              WHERE jsonb_typeof(x.value) <> 'object' OR x.value->>'debt_month' IS NULL
                 OR x.value->>'kind' IS NULL OR x.value->>'source_tab' IS NULL
                 OR x.value->>'source_row' IS NULL OR jsonb_typeof(x.value->'display') <> 'object')
       OR EXISTS(SELECT 1 FROM jsonb_array_elements(month_checks) AS x(value)
              WHERE jsonb_typeof(x.value) <> 'object' OR x.value->>'debt_month' IS NULL
                 OR jsonb_typeof(x.value->'exception_codes') IS DISTINCT FROM 'array')
    THEN RAISE EXCEPTION 'INVALID_CUTOVER_INPUT'; END IF;
    SELECT coalesce(sum((x.value->>'amount_vnd')::numeric),0) INTO v_total
      FROM jsonb_array_elements(openings) AS x(value);
    IF v_total<>expected_control_total THEN RAISE EXCEPTION 'CUTOVER_CUSTOMER_TOTAL_MISMATCH'; END IF;
    INSERT INTO sokhach.cutover_customer(customer_id,cutover_id,expected_control_total_vnd,
        report_sha256,source_rows,imported_rows,quarantined_rows,
        skipped_with_reason_rows,unresolved_exceptions)
    VALUES(customer_id,cutover_id,expected_control_total,report_sha256,
        jsonb_array_length(openings)+jsonb_array_length(legacy),
        jsonb_array_length(openings)+jsonb_array_length(legacy),0,0,
        (SELECT count(*) FROM jsonb_array_elements(month_checks) AS x(value)
         WHERE jsonb_array_length(x.value->'exception_codes')>0));
    INSERT INTO sokhach.event(customer_id,kind,actor,"before","after",idempotency_key,cutover_id)
    VALUES(customer_id,'import',sokhach._actor(),'{}',
        jsonb_build_object('cutover',cutover_id,'openings',jsonb_array_length(openings),
            'legacy',jsonb_array_length(legacy),'report_sha256',report_sha256),
        idempotency_key,cutover_id) RETURNING id INTO v_event;
    FOR v_item IN SELECT value FROM jsonb_array_elements(openings) LOOP
        INSERT INTO sokhach.opening_balance(customer_id,cutover_id,debt_month,
            amount_vnd,source_tab,source_row,created_by_event)
        VALUES(customer_id,cutover_id,(v_item->>'debt_month')::date,
            (v_item->>'amount_vnd')::bigint,v_item->>'source_tab',
            (v_item->>'source_row')::bigint,v_event);
    END LOOP;
    FOR v_item IN SELECT value FROM jsonb_array_elements(legacy) LOOP
        INSERT INTO sokhach.legacy_row(customer_id,cutover_id,debt_month,kind,
            display,source_total_vnd,source_tab,source_row,created_by_event)
        VALUES(customer_id,cutover_id,(v_item->>'debt_month')::date,
            v_item->>'kind',v_item->'display',(v_item->>'source_total_vnd')::bigint,
            v_item->>'source_tab',(v_item->>'source_row')::bigint,v_event);
    END LOOP;
    FOR v_item IN SELECT value FROM jsonb_array_elements(month_checks) LOOP
        INSERT INTO sokhach.cutover_month_check(customer_id,cutover_id,debt_month,
            opening_anchor_vnd,source_cumulative_vnd,replay_cumulative_vnd,bucket_vnd,
            standard_bucket_vnd,standard_source_ref,standard_source_sha256,
            source_evidence_sha256,exception_codes,source_charge_vnd,source_receipt_vnd)
        VALUES(customer_id,cutover_id,(v_item->>'debt_month')::date,
            (v_item->>'opening_anchor_vnd')::bigint,(v_item->>'source_cumulative_vnd')::bigint,
            (v_item->>'replay_cumulative_vnd')::bigint,(v_item->>'bucket_vnd')::bigint,
            (v_item->>'standard_bucket_vnd')::bigint,v_item->>'standard_source_ref',
            v_item->>'standard_source_sha256',v_item->>'source_evidence_sha256',
            ARRAY(SELECT jsonb_array_elements_text(v_item->'exception_codes')),
            (v_item->>'source_charge_vnd')::bigint,(v_item->>'source_receipt_vnd')::bigint);
    END LOOP;
    v_result := jsonb_build_object('cutover_id',cutover_id,'customer_id',customer_id,
        'status','draft','event_id',v_event);
    RETURN sokhach._finish_command(customer_id,idempotency_key,v_payload,v_result);
END $function$;
ALTER FUNCTION sokhach.import_cutover(bigint,bigint,text,bigint,jsonb,jsonb,jsonb,bigint,text) OWNER TO sokhach_owner;
REVOKE ALL ON FUNCTION sokhach.import_cutover(bigint,bigint,text,bigint,jsonb,jsonb,jsonb,bigint,text) FROM PUBLIC;

-- FUNCTION sokhach.keep_sheet_task(bigint,bigint,text,text,text,bigint,text,jsonb)
CREATE OR REPLACE FUNCTION sokhach.keep_sheet_task(customer_id bigint, expected_version bigint, idempotency_key text, task_kind text, target_kind text, target_id bigint, source_fingerprint text, web_value jsonb)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'pg_catalog', 'sokhach', 'pg_temp'
AS $function$
DECLARE v_payload jsonb:=jsonb_build_object('command','keep_sheet_task','task_kind',task_kind,
 'target_kind',target_kind,'target_id',target_id,'source_fingerprint',source_fingerprint,'web_value',web_value);
 v_retry jsonb; v_current jsonb; v_row jsonb;
BEGIN
 v_retry:=sokhach._begin_command(customer_id,expected_version,idempotency_key,v_payload);
 IF v_retry IS NOT NULL THEN RETURN v_retry; END IF;
 PERFORM sokhach._baseline(customer_id);
 IF task_kind IS NULL OR task_kind NOT IN ('price','removed','ps','source')
  OR source_fingerprint IS NULL OR source_fingerprint !~ '^[0-9a-f]{64}$' OR web_value IS NULL
 THEN RAISE EXCEPTION 'INVALID_SHEET_RESOLUTION'; END IF;
 IF task_kind='source' THEN
  -- K3: đóng một dòng Sheet theo dấu vân nội dung của nó, không gắn chuyến. web_value chỉ là {"scope": ...}.
  IF target_kind IS NOT NULL OR target_id IS NOT NULL OR jsonb_typeof(web_value)<>'object'
   OR web_value-'scope'<>'{}'::jsonb OR web_value->>'scope' IS NULL OR web_value->>'scope' NOT IN ('price','ps','trip')
  THEN RAISE EXCEPTION 'INVALID_SHEET_RESOLUTION'; END IF;
  INSERT INTO sokhach.event(customer_id,kind,actor,"before","after",idempotency_key)
  VALUES(customer_id,'sheet_conflict_resolved',sokhach._actor(),
   jsonb_build_object('target',jsonb_build_object('kind','source','scope',web_value->>'scope'),'field','task_source','value',web_value),
   jsonb_build_object('target',jsonb_build_object('kind','source','scope',web_value->>'scope'),'field','task_source',
    'source_row',0,'sheet_value',source_fingerprint,'target_value',web_value,'decision','keep_web','request_key',idempotency_key),idempotency_key);
  RETURN sokhach._finish_command(customer_id,idempotency_key,v_payload,jsonb_build_object('kept',true));
 END IF;
 IF target_kind IS NULL OR target_kind NOT IN ('trip','legacy') OR target_id IS NULL OR target_id<=0
  OR (task_kind='removed' AND target_kind<>'trip')
 THEN RAISE EXCEPTION 'INVALID_SHEET_RESOLUTION'; END IF;
 IF target_kind='trip' THEN
  v_row:=sokhach._trip_current_row(customer_id,target_id);  -- audit SQL F4: một chuyến, không dựng cả sổ
 ELSE
  SELECT sokhach._legacy_current(l.id) INTO v_row FROM sokhach.legacy_row l
   JOIN sokhach.cutover_customer cc USING(customer_id,cutover_id)
   JOIN sokhach.cutover c ON c.id=cc.cutover_id
   WHERE l.customer_id=keep_sheet_task.customer_id AND l.id=target_id AND l.kind='trip'
     AND cc.status='active' AND c.status='active';
 END IF;
 IF v_row IS NULL OR coalesce((v_row->>'deleted')::boolean,false) THEN RAISE EXCEPTION 'TRIP_NOT_FOUND'; END IF;
 v_current:=CASE WHEN task_kind IN ('price','ps') THEN jsonb_build_object(
  'unit_price_vnd',v_row->>'unit_price_vnd','other_fee_vnd',v_row->>'other_fee_vnd')
 ELSE jsonb_build_object('container',v_row->>'container','event_date',v_row->>'event_date',
  'status',v_row->>'status','booking',v_row->>'booking') END;
 IF v_current IS DISTINCT FROM web_value THEN RAISE EXCEPTION 'STALE_LEDGER'; END IF;
 INSERT INTO sokhach.event(customer_id,kind,actor,"before","after",idempotency_key)
 VALUES(customer_id,'sheet_conflict_resolved',sokhach._actor(),
  jsonb_build_object('target',jsonb_build_object('kind',target_kind,'id',target_id),'field','task_'||task_kind,'value',v_current),
  jsonb_build_object('target',jsonb_build_object('kind',target_kind,'id',target_id),'field','task_'||task_kind,
   'source_row',0,'sheet_value',source_fingerprint,'target_value',v_current,'decision','keep_web','request_key',idempotency_key),idempotency_key);
 RETURN sokhach._finish_command(customer_id,idempotency_key,v_payload,jsonb_build_object('kept',true));
END $function$;
ALTER FUNCTION sokhach.keep_sheet_task(bigint,bigint,text,text,text,bigint,text,jsonb) OWNER TO sokhach_owner;
REVOKE ALL ON FUNCTION sokhach.keep_sheet_task(bigint,bigint,text,text,text,bigint,text,jsonb) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION sokhach.keep_sheet_task(bigint,bigint,text,text,text,bigint,text,jsonb) TO sokhach_app;

-- FUNCTION sokhach.link_zalo(text,bigint)
CREATE OR REPLACE FUNCTION sokhach.link_zalo(p_conversation text, p_customer bigint)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'pg_catalog', 'sokhach', 'pg_temp'
AS $function$
DECLARE v sokhach.zalo_link;
BEGIN
 IF p_conversation IS NULL OR p_conversation !~ '^[0-9a-f]{64}$' THEN RAISE EXCEPTION 'INVALID_LINK'; END IF;
 IF NOT EXISTS(SELECT 1 FROM sokhach.customer c WHERE c.id=p_customer) THEN RAISE EXCEPTION 'CUSTOMER_NOT_FOUND'; END IF;
 INSERT INTO sokhach.zalo_link(conversation_id,customer_id,linked_by)
   VALUES(p_conversation,p_customer,sokhach._actor())
   ON CONFLICT (conversation_id,customer_id) WHERE unlinked_at IS NULL DO NOTHING;
 SELECT * INTO v FROM sokhach.zalo_link l WHERE l.conversation_id=p_conversation AND l.customer_id=p_customer AND l.unlinked_at IS NULL;
 RETURN jsonb_build_object('conversation_id',v.conversation_id,'customer_id',v.customer_id,
   'customer_name',(SELECT c.name FROM sokhach.customer c WHERE c.id=v.customer_id),'linked_by',v.linked_by,'linked_at',v.linked_at);
END $function$;
ALTER FUNCTION sokhach.link_zalo(text,bigint) OWNER TO sokhach_owner;
REVOKE ALL ON FUNCTION sokhach.link_zalo(text,bigint) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION sokhach.link_zalo(text,bigint) TO sokhach_app;

-- FUNCTION sokhach.list_customers()
CREATE OR REPLACE FUNCTION sokhach.list_customers()
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'pg_catalog', 'sokhach', 'pg_temp'
AS $function$
BEGIN
    PERFORM sokhach._actor();
    RETURN (SELECT jsonb_build_object('customers',coalesce(jsonb_agg(
        jsonb_build_object('id',id,'name',name,'status',status,
                           'commodity',commodity,'transport_mode',transport_mode,'booking_names',booking_names,'archived',archived)
        ORDER BY name COLLATE "C",id),'[]'::jsonb))
      FROM (SELECT c.id,c.name,
                   CASE WHEN cc.status='active' AND co.status='active'
                        THEN 'active' ELSE 'NO_BASELINE' END AS status,
                   m.name AS commodity,c.transport_mode,coalesce(bn.names,'[]'::jsonb) AS booking_names,c.archived
              FROM sokhach.customer c
              LEFT JOIN sokhach.commodity m ON m.id=c.commodity_id
              LEFT JOIN sokhach.cutover_customer cc ON cc.customer_id=c.id
              LEFT JOIN sokhach.cutover co ON co.id=cc.cutover_id
              -- Một lượt gom cho mọi sổ: gọi _booking_names từng sổ (SECURITY DEFINER, không inline) làm hàm chậm gấp đôi.
              LEFT JOIN (SELECT b.customer_id,jsonb_agg(b.name ORDER BY b.name COLLATE "C") AS names
                           FROM sokhach.booking_name b GROUP BY b.customer_id) bn ON bn.customer_id=c.id) q);
END $function$;
ALTER FUNCTION sokhach.list_customers() OWNER TO sokhach_owner;
REVOKE ALL ON FUNCTION sokhach.list_customers() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION sokhach.list_customers() TO sokhach_app;
GRANT EXECUTE ON FUNCTION sokhach.list_customers() TO sokhach_reader;

-- FUNCTION sokhach.list_legacy_trip_refs(jsonb)
CREATE OR REPLACE FUNCTION sokhach.list_legacy_trip_refs(containers jsonb)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'pg_catalog', 'sokhach', 'pg_temp'
AS $function$
DECLARE v_keys text[];
BEGIN
    PERFORM sokhach._actor();
    IF jsonb_typeof(containers) IS DISTINCT FROM 'array' OR jsonb_array_length(containers)>2000
       OR EXISTS (SELECT 1 FROM jsonb_array_elements(containers) c WHERE jsonb_typeof(c)<>'string')
    THEN RAISE EXCEPTION 'INVALID_COMMAND'; END IF;
    SELECT coalesce(array_agg(DISTINCT sokhach._normalize_key(c#>>'{}')),'{}') INTO v_keys FROM jsonb_array_elements(containers) c;
    -- Lọc theo container trước (dòng gốc hoặc bản sửa), rồi mới đọc bản sửa mới nhất của dòng ứng viên.
    -- Giữ = ANY(mảng), đừng đổi về IN (SELECT ...): với hash semi join planner gần như không tính chi phí _normalize_key
    -- nên quét tuần tự cả hai bảng và bỏ qua index container_key (đo trên bản sao thật 4/11/2026: 169 ms so với 9 ms).
    RETURN (WITH cand AS (SELECT l.id FROM sokhach.legacy_row l WHERE l.kind='trip'
                   AND sokhach._normalize_key(l.display->>'container') = ANY(v_keys)
                 UNION
                 SELECT y.legacy_row_id FROM sokhach.legacy_trip_rev y
                  WHERE sokhach._normalize_key(y.container) = ANY(v_keys)),
        x AS (SELECT l.id,l.customer_id,
                CASE WHEN r.id IS NULL THEN l.display->>'container' ELSE r.container END AS container,
                CASE WHEN r.id IS NULL THEN sokhach._legacy_date(l.display->>'date') ELSE r.event_date END AS event_date,
                coalesce(r.debt_month,l.debt_month) AS debt_month
            FROM cand JOIN sokhach.legacy_row l ON l.id=cand.id
            JOIN sokhach.cutover_customer cc ON (cc.customer_id,cc.cutover_id)=(l.customer_id,l.cutover_id) AND cc.status='active'
            LEFT JOIN LATERAL (SELECT y.id,y.debt_month,y.event_date,y.container,y.deleted FROM sokhach.legacy_trip_rev y
                WHERE y.legacy_row_id=l.id ORDER BY y.id DESC LIMIT 1) r ON true
            WHERE NOT coalesce(r.deleted,false))
        SELECT jsonb_build_object('items',coalesce(jsonb_agg(jsonb_build_object(
            'customer_id',x.customer_id,'container',x.container,'event_date',x.event_date,'debt_month',x.debt_month)
            ORDER BY x.customer_id,x.id),'[]'::jsonb))
        FROM x WHERE sokhach._normalize_key(x.container) = ANY(v_keys) AND sokhach._normalize_key(x.container)<>'');
END;
$function$;
ALTER FUNCTION sokhach.list_legacy_trip_refs(jsonb) OWNER TO sokhach_owner;
REVOKE ALL ON FUNCTION sokhach.list_legacy_trip_refs(jsonb) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION sokhach.list_legacy_trip_refs(jsonb) TO sokhach_app;

-- FUNCTION sokhach.list_offset_sources(bigint)
CREATE OR REPLACE FUNCTION sokhach.list_offset_sources(target_customer_id bigint)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'pg_catalog', 'sokhach', 'pg_temp'
AS $function$
BEGIN
    PERFORM sokhach._actor();
    IF NOT EXISTS (SELECT 1 FROM sokhach.customer WHERE id=target_customer_id)
    THEN RAISE EXCEPTION 'CUSTOMER_NOT_FOUND'; END IF;
    -- ponytail: no customer-group key; sort every eligible book by name until group key is approved.
    RETURN coalesce((SELECT jsonb_agg(jsonb_build_object('customer_id',c.id,'name',c.name,
        'commodity',m.name,'version',c.version,'outstanding_vnd',b.total::text,
        'available_credit_vnd',(-b.total)::text) ORDER BY c.name COLLATE "C",c.id)
      FROM sokhach.customer c LEFT JOIN sokhach.commodity m ON m.id=c.commodity_id
      JOIN (SELECT customer_id,sum(outstanding_vnd) AS total FROM sokhach.v_outstanding_month
            GROUP BY customer_id HAVING sum(outstanding_vnd)<0) b ON b.customer_id=c.id
      WHERE c.id<>target_customer_id AND NOT c.archived),'[]'::jsonb);
END $function$;
ALTER FUNCTION sokhach.list_offset_sources(bigint) OWNER TO sokhach_owner;
REVOKE ALL ON FUNCTION sokhach.list_offset_sources(bigint) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION sokhach.list_offset_sources(bigint) TO sokhach_app;
GRANT EXECUTE ON FUNCTION sokhach.list_offset_sources(bigint) TO sokhach_reader;

-- FUNCTION sokhach.list_receipt_images(bigint)
CREATE OR REPLACE FUNCTION sokhach.list_receipt_images(customer_id bigint)
 RETURNS jsonb
 LANGUAGE plpgsql
 STABLE SECURITY DEFINER
 SET search_path TO 'pg_catalog', 'sokhach', 'pg_temp'
AS $function$
BEGIN
 IF NOT EXISTS(SELECT 1 FROM sokhach.customer c WHERE c.id=list_receipt_images.customer_id) THEN RAISE EXCEPTION 'CUSTOMER_NOT_FOUND'; END IF;
 RETURN jsonb_build_object('images',(SELECT coalesce(jsonb_agg(jsonb_build_object('id',i.id,'receipt_id',i.receipt_id,'pid',r.pid,
   'sha256',i.sha256,'content_type',i.content_type,'byte_size',octet_length(i.data),'at',e.at,'actor',e.actor) ORDER BY i.receipt_id,i.id),'[]'::jsonb)
  FROM sokhach.receipt_image i JOIN sokhach.receipt r ON r.id=i.receipt_id JOIN sokhach.event e ON e.id=i.created_by_event
  WHERE i.customer_id=list_receipt_images.customer_id AND i.removed_by_event IS NULL));
END $function$;
ALTER FUNCTION sokhach.list_receipt_images(bigint) OWNER TO sokhach_owner;
REVOKE ALL ON FUNCTION sokhach.list_receipt_images(bigint) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION sokhach.list_receipt_images(bigint) TO sokhach_app;
GRANT EXECUTE ON FUNCTION sokhach.list_receipt_images(bigint) TO sokhach_reader;

-- FUNCTION sokhach.list_sheet_trip_refs()
CREATE OR REPLACE FUNCTION sokhach.list_sheet_trip_refs()
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'pg_catalog', 'sokhach', 'pg_temp'
AS $function$
BEGIN
    PERFORM sokhach._actor();
    RETURN (SELECT jsonb_build_object('items',coalesce(jsonb_agg(
        jsonb_build_object('customer_id',customer_id,'container',container)
        ORDER BY customer_id,id),'[]'::jsonb))
    FROM sokhach.v_trip_current WHERE NOT deleted AND container IS NOT NULL);
END;
$function$;
ALTER FUNCTION sokhach.list_sheet_trip_refs() OWNER TO sokhach_owner;
REVOKE ALL ON FUNCTION sokhach.list_sheet_trip_refs() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION sokhach.list_sheet_trip_refs() TO sokhach_app;

-- FUNCTION sokhach.paste_trips(bigint,bigint,text,date,jsonb)
CREATE OR REPLACE FUNCTION sokhach.paste_trips(customer_id bigint, expected_version bigint, idempotency_key text, debt_month date, trips jsonb)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'pg_catalog', 'sokhach', 'pg_temp'
AS $function$
DECLARE v_payload jsonb := jsonb_build_object('command','paste_trips','month',debt_month,'trips',trips);
        v_retry jsonb; v_actor text; v_ids jsonb := '[]'::jsonb;
        v_item jsonb; v_fee_item jsonb; v_id bigint; v_event bigint; v_rows jsonb := '[]'::jsonb;
        v_changes jsonb; v_date date; v_unit bigint; v_fee bigint; v_fee_total numeric; v_date_text text;
        v_fee_only boolean; v_cutover bigint; v_booking text; v_container text;
        v_reason text; v_pending jsonb := '[]'; v_lock integer;
BEGIN
    v_retry := sokhach._begin_command(customer_id,expected_version,idempotency_key,v_payload);
    IF v_retry IS NOT NULL THEN RETURN v_retry; END IF;
    PERFORM sokhach._baseline(customer_id);
    SELECT cc.cutover_id INTO v_cutover FROM sokhach.cutover_customer cc
        JOIN sokhach.cutover c ON c.id=cc.cutover_id
        WHERE cc.customer_id=paste_trips.customer_id AND cc.status='active' AND c.status='active';
    IF NOT EXISTS (SELECT 1 FROM sokhach.baseline_trip_ref WHERE cutover_id=v_cutover)
    THEN RAISE EXCEPTION 'BASELINE_REF_MISSING'; END IF;
    IF debt_month IS NULL OR extract(day FROM debt_month)<>1 THEN RAISE EXCEPTION 'INVALID_COMMAND'; END IF;
    IF jsonb_typeof(trips) IS DISTINCT FROM 'array' OR jsonb_array_length(trips)=0
    THEN RAISE EXCEPTION 'INVALID_TRIPS'; END IF;
    -- Audit SQL 23/11/2026 (F9): khóa container của dòng Sheet lấy trước, theo thứ tự khóa, thay vì từng dòng theo thứ tự lô trong
    -- trigger guard_sheet_cross_customer (trigger lấy lại cùng khóa, không chờ). Hai lô cùng container khác thứ tự hết kẹt chéo.
    FOR v_lock IN SELECT DISTINCT hashtext(sokhach._normalize_key(x->>'container')) FROM jsonb_array_elements(trips) x
        WHERE jsonb_typeof(x)='object' AND x->>'src' ~ '^sheet:[0-9a-f]{64}:[0-9]+$' AND nullif(x->>'container','') IS NOT NULL
        ORDER BY 1 LOOP
        PERFORM pg_advisory_xact_lock(746193,v_lock);
    END LOOP;
    FOR v_item IN SELECT value FROM jsonb_array_elements(trips) LOOP
        IF v_item ? 'fees' AND (jsonb_typeof(v_item->'fees')<>'array' OR v_item->>'otherFeeVnd' IS NOT NULL)
        THEN RAISE EXCEPTION 'INVALID_TRIP_INPUT'; END IF;
        v_fee_only := nullif(v_item->>'container','') IS NULL
            AND v_item->>'unitPriceVnd' IS NULL
            AND (v_item->>'otherFeeVnd' IS NOT NULL
              OR (v_item ? 'fees' AND jsonb_array_length(v_item->'fees')>0));
        IF jsonb_typeof(v_item) <> 'object'
           OR (NOT v_fee_only AND (v_item->>'container' IS NULL
             OR nullif(btrim(v_item->>'carrier'),'') IS NULL
             OR nullif(btrim(v_item->>'from'),'') IS NULL
             OR nullif(btrim(v_item->>'to'),'') IS NULL))
        THEN RAISE EXCEPTION 'INVALID_TRIP'; END IF;
        v_date_text := v_item->>'date';
        IF v_item->>'unitPriceVnd'='-0' OR v_item->>'otherFeeVnd'='-0'
        THEN RAISE EXCEPTION 'INVALID_VND'; END IF;
        IF (v_date_text IS NULL AND NOT v_fee_only)
           OR (v_date_text IS NOT NULL AND v_date_text !~ '^[0-9]{2}/[0-9]{2}/[0-9]{4}$')
           OR (v_item->>'unitPriceVnd' IS NOT NULL AND (v_item->>'unitPriceVnd') !~ '^[0-9]+$')
           OR (v_item->>'otherFeeVnd' IS NOT NULL AND (v_item->>'otherFeeVnd') !~ '^-?[0-9]+$')
        THEN RAISE EXCEPTION 'INVALID_TRIP_INPUT'; END IF;
        v_date := CASE WHEN v_date_text IS NULL THEN NULL ELSE to_date(v_date_text,'DD/MM/YYYY') END;
        IF v_date_text IS NOT NULL AND to_char(v_date,'DD/MM/YYYY') <> v_date_text
        THEN RAISE EXCEPTION 'INVALID_TRIP_DATE'; END IF;
        -- FUTURE-01 áp vào V7 (29/10/2026): ngày xe nhập kho khi dán không được sau hôm nay giờ VN,
        -- cùng luật với sửa ngày tại ô (_trip_date); chuyến đồng bộ từ Sheet cũng đi qua đây.
        IF v_date > (clock_timestamp() AT TIME ZONE 'Asia/Ho_Chi_Minh')::date
        THEN RAISE EXCEPTION 'FUTURE_DATE'; END IF;
        -- Audit SQL 23/11/2026 (F2): dòng phí lẻ không ngày vào tháng nợ của lệnh, nên theo luật của adjust_month: không sau tháng
        -- hiện tại giờ VN và tháng phải mở (khóa tháng 24/10/2026). Dòng có ngày giữ ngoại lệ nhập bù NHAP-SHEET-01 (7).
        IF v_date IS NULL THEN
            IF debt_month > date_trunc('month',clock_timestamp() AT TIME ZONE 'Asia/Ho_Chi_Minh')::date
            THEN RAISE EXCEPTION 'FUTURE_DATE'; END IF;
            PERFORM sokhach._month_open(customer_id,debt_month,clock_timestamp());
        END IF;
        BEGIN
            v_unit := (v_item->>'unitPriceVnd')::bigint;
            v_fee := (v_item->>'otherFeeVnd')::bigint;
        EXCEPTION WHEN numeric_value_out_of_range THEN RAISE EXCEPTION 'INVALID_VND'; END;
        v_fee_total:=coalesce(v_fee,0);
        IF v_item ? 'fees' THEN
          FOR v_fee_item IN SELECT value FROM jsonb_array_elements(v_item->'fees') LOOP
            IF jsonb_typeof(v_fee_item) NOT IN ('string','number')
              OR v_fee_item#>>'{}' !~ '^-?[0-9]+$'
            THEN RAISE EXCEPTION 'INVALID_TRIP_INPUT'; END IF;
            BEGIN v_fee:=(v_fee_item#>>'{}')::bigint;
            EXCEPTION WHEN numeric_value_out_of_range THEN RAISE EXCEPTION 'INVALID_VND'; END;
            IF v_fee=0 THEN RAISE EXCEPTION 'FEE_AMOUNT_INVALID'; END IF;
            v_fee_total:=v_fee_total+v_fee;
          END LOOP;
        END IF;
        -- ponytail: cap is signed bigint until business VND limit is decided.
        IF v_unit < 0 OR v_fee_total NOT BETWEEN -9223372036854775808 AND 9223372036854775807 OR
           coalesce(v_unit,0)::numeric+v_fee_total NOT BETWEEN -9223372036854775808 AND 9223372036854775807
        THEN RAISE EXCEPTION 'INVALID_VND'; END IF;
        v_reason := NULL;
        IF NOT v_fee_only THEN
            v_container := sokhach._normalize_key(v_item->>'container');
            v_booking := sokhach._booking_key(v_item->>'booking',v_container,v_date);
            v_reason := sokhach._trip_dup_reason(paste_trips.customer_id,v_cutover,v_container,v_booking,v_date,NULL,v_rows);
        END IF;
        v_id := nextval(pg_get_serial_sequence('sokhach.trip','id'));
        IF v_reason IS NOT NULL THEN
            v_pending := v_pending || jsonb_build_array(jsonb_build_object('trip_id',v_id,'reason',v_reason));
        END IF;
        v_ids := v_ids || jsonb_build_array(v_id);
        v_rows := v_rows || jsonb_build_array(v_item || jsonb_build_object(
            'trip_id',v_id,'debt_month',coalesce(date_trunc('month',v_date)::date,debt_month),'event_date',v_date,
            'status',CASE WHEN v_reason IS NULL THEN 'confirmed' ELSE 'pending_review' END)
            || CASE WHEN v_reason IS NULL THEN '{}'::jsonb ELSE jsonb_build_object('review_reason',v_reason) END);
    END LOOP;
    v_actor := sokhach._actor();
    INSERT INTO sokhach.event(customer_id,kind,actor,"before","after",idempotency_key)
    VALUES (customer_id,'paste',v_actor,'{}',jsonb_build_object('trips',v_rows),idempotency_key)
    RETURNING id INTO v_event;
    FOR v_item IN SELECT value FROM jsonb_array_elements(v_rows) LOOP
        INSERT INTO sokhach.trip(id,customer_id,debt_month,event_date,container,carrier,shipper,
            origin,destination,note,source_ref,created_by_event,booking,status) OVERRIDING SYSTEM VALUE
        VALUES ((v_item->>'trip_id')::bigint,customer_id,(v_item->>'debt_month')::date,(v_item->>'event_date')::date,
            v_item->>'container',v_item->>'carrier',v_item->>'shipper',v_item->>'from',v_item->>'to',
            v_item->>'note',v_item->>'src',v_event,v_item->>'booking',v_item->>'status');
        INSERT INTO sokhach.trip_price_rev(trip_id,customer_id,unit_price_vnd,created_by_event)
        VALUES ((v_item->>'trip_id')::bigint,customer_id,(v_item->>'unitPriceVnd')::bigint,v_event);
        IF v_item ? 'fees' THEN
          FOR v_fee_item IN SELECT value FROM jsonb_array_elements(v_item->'fees') LOOP
            v_fee:=(v_fee_item#>>'{}')::bigint;
            INSERT INTO sokhach.trip_fee_line(customer_id,trip_id,fee_type_id,amount_vnd,created_by_event)
            SELECT customer_id,(v_item->>'trip_id')::bigint,id,v_fee,v_event FROM sokhach.fee_type
            WHERE system_key=CASE WHEN v_fee<0 THEN 'discount' ELSE 'other' END;
          END LOOP;
        ELSE
          v_fee := (v_item->>'otherFeeVnd')::bigint;
          IF v_fee IS NOT NULL AND v_fee<>0 THEN
              INSERT INTO sokhach.trip_fee_line(customer_id,trip_id,fee_type_id,amount_vnd,created_by_event)
              SELECT customer_id,(v_item->>'trip_id')::bigint,id,v_fee,v_event FROM sokhach.fee_type
              WHERE system_key=CASE WHEN v_fee<0 THEN 'discount' ELSE 'other' END;
          END IF;
        END IF;
        PERFORM sokhach._sync_trip_fee((v_item->>'trip_id')::bigint,v_event);
    END LOOP;
    v_changes := sokhach.reallocate(customer_id,idempotency_key);
    RETURN sokhach._finish_command(customer_id,idempotency_key,v_payload,
        jsonb_build_object('trip_ids',v_ids,'reallocated',v_changes,'pending_review',v_pending));
END $function$;
ALTER FUNCTION sokhach.paste_trips(bigint,bigint,text,date,jsonb) OWNER TO sokhach_owner;
REVOKE ALL ON FUNCTION sokhach.paste_trips(bigint,bigint,text,date,jsonb) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION sokhach.paste_trips(bigint,bigint,text,date,jsonb) TO sokhach_app;

-- FUNCTION sokhach.preview_price_table(bigint,bigint,text,jsonb)
CREATE OR REPLACE FUNCTION sokhach.preview_price_table(customer_id bigint, expected_version bigint, idempotency_key text, price_table jsonb)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'pg_catalog', 'sokhach', 'pg_temp'
AS $function$
DECLARE v_saved jsonb; v_status jsonb; v_message text; v_detail text;
BEGIN
 BEGIN
   v_saved:=sokhach.save_price_table(customer_id,expected_version,idempotency_key,price_table);
   v_status:=sokhach.get_price_status(customer_id);
   RAISE EXCEPTION 'PRICE_PREVIEW_ROLLBACK' USING DETAIL=jsonb_build_object(
     'price_table',v_saved->'price_table','version',expected_version,
     'repriced_trips',(SELECT coalesce(jsonb_agg(r.x||jsonb_build_object('tier',s.x->'lookup'->>'tier')
         ORDER BY (r.x->>'trip_id')::bigint),'[]'::jsonb)
       FROM jsonb_array_elements(v_saved->'repriced_trips') r(x)
       LEFT JOIN jsonb_array_elements(v_status->'trips') s(x) ON s.x->>'trip_id'=r.x->>'trip_id'),
     'repriced_delta_vnd',v_saved->'repriced_delta_vnd','locked_trips',v_saved->'locked_trips',
     'no_price_trips',v_saved->'no_price_trips',
     -- Giá gõ tay hoặc lấy từ Sheet khác bảng mới: không đổi (gõ tay thắng bảng), chỉ đếm để người dùng biết.
     'typed_trips',(SELECT count(*) FROM jsonb_array_elements(v_status->'trips') s(x)
       WHERE (s.x->>'differs')::boolean AND NOT (s.x->>'from_table')::boolean),
     -- Chuyến chưa có giá mà bảng mới điền được: vẫn phải bấm "Điền giá theo bảng" (BANG-GIA-02), không đổi khi lưu.
     'ready_count',v_status->'ready_count','ready_total_vnd',v_status->'ready_total_vnd')::text;
 EXCEPTION WHEN raise_exception THEN
   GET STACKED DIAGNOSTICS v_message=MESSAGE_TEXT,v_detail=PG_EXCEPTION_DETAIL;
   IF v_message IS DISTINCT FROM 'PRICE_PREVIEW_ROLLBACK' THEN RAISE; END IF;
 END;
 RETURN v_detail::jsonb;
END $function$;
ALTER FUNCTION sokhach.preview_price_table(bigint,bigint,text,jsonb) OWNER TO sokhach_owner;
REVOKE ALL ON FUNCTION sokhach.preview_price_table(bigint,bigint,text,jsonb) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION sokhach.preview_price_table(bigint,bigint,text,jsonb) TO sokhach_app;

-- FUNCTION sokhach.reallocate(bigint,text)
CREATE OR REPLACE FUNCTION sokhach.reallocate(p_customer bigint, p_key text)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'pg_catalog', 'sokhach', 'pg_temp'
AS $function$
DECLARE v_months date[] := ARRAY[]::date[]; v_left bigint[] := ARRAY[]::bigint[];
        v_month date; v_amount bigint; v_last date; v_receipt sokhach.receipt%ROWTYPE;
        v_due bigint; v_remaining bigint; v_take bigint; v_new jsonb; v_old jsonb;
        v_old_snapshot jsonb; v_new_snapshot jsonb;
        v_event bigint; v_actor text; v_changes jsonb := '[]'::jsonb; i integer;
        v_row jsonb;
BEGIN
    SELECT version INTO v_amount FROM sokhach.customer WHERE id = p_customer FOR NO KEY UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION 'CUSTOMER_NOT_FOUND'; END IF;
    v_actor := sokhach._actor();
    PERFORM sokhach._baseline(p_customer);
    FOR v_month, v_due IN
        WITH charges AS (
            SELECT o.debt_month, o.amount_vnd FROM sokhach.opening_balance o
            JOIN sokhach.cutover_customer cc ON (cc.customer_id,cc.cutover_id)=(o.customer_id,o.cutover_id)
            JOIN sokhach.cutover c ON c.id=cc.cutover_id
            WHERE o.customer_id=p_customer AND cc.status='active' AND c.status='active'
            UNION ALL
            SELECT t.debt_month,
                CASE WHEN p.unit_price_vnd IS NOT NULL
                     THEN p.unit_price_vnd + coalesce(p.other_fee_vnd,0)
                     WHEN t.container IS NULL OR t.container='' THEN p.other_fee_vnd END
            FROM sokhach.v_trip_current t LEFT JOIN LATERAL (
                SELECT unit_price_vnd,other_fee_vnd FROM sokhach.trip_price_rev
                WHERE trip_id=t.id ORDER BY id DESC LIMIT 1) p ON true
            WHERE t.customer_id=p_customer AND NOT t.deleted AND t.status='confirmed'
            UNION ALL
            SELECT debt_month,amount_vnd FROM sokhach.v_adjustment_current WHERE customer_id=p_customer
            UNION ALL SELECT debt_month,amount_vnd FROM sokhach.v_offset_outgoing WHERE customer_id=p_customer
        ) SELECT debt_month, sum(amount_vnd)::bigint FROM charges
          GROUP BY debt_month ORDER BY debt_month
    LOOP
        v_months := array_append(v_months,v_month);
        v_left := array_append(v_left,v_due);
        v_last := v_month;
    END LOOP;
    IF v_last IS NULL THEN
        SELECT max(l.debt_month) INTO v_last FROM sokhach.receipt_line l JOIN sokhach.receipt r ON r.id=l.receipt_id
          WHERE r.customer_id=p_customer AND r.voided_on IS NULL AND l.superseded_by_event IS NULL;
    END IF;
    IF v_last IS NULL AND EXISTS (SELECT 1 FROM sokhach.receipt WHERE customer_id=p_customer AND voided_on IS NULL)
    THEN RAISE EXCEPTION 'NO_MONTH_FOR_RECEIPT'; END IF;
    FOR v_receipt IN SELECT * FROM sokhach.receipt
        WHERE customer_id=p_customer AND voided_on IS NULL ORDER BY date,pid COLLATE "C"
    LOOP
        v_remaining := v_receipt.amount_vnd;
        v_new := '[]'::jsonb;
        FOR i IN 1..coalesce(array_length(v_months,1),0) LOOP
            EXIT WHEN v_remaining=0;
            IF v_left[i] > 0 THEN
                v_take := least(v_remaining,v_left[i]);
                v_new := v_new || jsonb_build_array(jsonb_build_object(
                    'month',v_months[i],'kind','debt','amount_vnd',v_take::text));
                v_left[i] := v_left[i]-v_take;
                v_remaining := v_remaining-v_take;
            END IF;
        END LOOP;
        IF v_remaining > 0 THEN
            v_new := v_new || jsonb_build_array(jsonb_build_object(
                'month',v_last,'kind','advance','amount_vnd',v_remaining::text));
        END IF;
        SELECT coalesce(jsonb_agg(jsonb_build_object('month',debt_month,
                   'kind',kind,'amount_vnd',amount_vnd::text)
                   ORDER BY debt_month,CASE kind WHEN 'debt' THEN 0 ELSE 1 END,id),'[]'::jsonb) INTO v_old
        FROM sokhach.receipt_line WHERE receipt_id=v_receipt.id AND superseded_by_event IS NULL;
        IF v_old IS DISTINCT FROM v_new THEN
            v_old_snapshot := sokhach._lines(v_receipt.id);
            v_new_snapshot := '[]'::jsonb;
            FOR v_row IN SELECT value FROM jsonb_array_elements(v_new) LOOP
                v_new_snapshot := v_new_snapshot || jsonb_build_array(v_row ||
                    jsonb_build_object('id',nextval(pg_get_serial_sequence('sokhach.receipt_line','id'))));
            END LOOP;
            INSERT INTO sokhach.event(customer_id,kind,actor,"before","after",idempotency_key)
            VALUES (p_customer,'reallocation',v_actor,
                jsonb_build_object('receipt',v_receipt.id,'allocations',v_old_snapshot),
                jsonb_build_object('receipt',v_receipt.id,'allocations',v_new_snapshot),p_key)
            RETURNING id INTO v_event;
            UPDATE sokhach.receipt_line SET superseded_by_event=v_event
            WHERE receipt_id=v_receipt.id AND superseded_by_event IS NULL;
            FOR v_row IN SELECT value FROM jsonb_array_elements(v_new_snapshot) LOOP
                INSERT INTO sokhach.receipt_line(id,receipt_id,customer_id,debt_month,kind,amount_vnd,created_by_event)
                OVERRIDING SYSTEM VALUE VALUES ((v_row->>'id')::bigint,v_receipt.id,p_customer,
                        (v_row->>'month')::date,v_row->>'kind',(v_row->>'amount_vnd')::bigint,v_event);
            END LOOP;
            v_changes := v_changes || jsonb_build_array(jsonb_build_object(
                'pid',v_receipt.pid,'before',v_old_snapshot,'after',v_new_snapshot,'event_id',v_event));
        END IF;
    END LOOP;
    PERFORM sokhach._check_allocations(p_customer);
    RETURN v_changes;
EXCEPTION WHEN numeric_value_out_of_range THEN RAISE EXCEPTION 'INVALID_VND';
END $function$;
ALTER FUNCTION sokhach.reallocate(bigint,text) OWNER TO sokhach_owner;
REVOKE ALL ON FUNCTION sokhach.reallocate(bigint,text) FROM PUBLIC;

-- FUNCTION sokhach.record_cash_review(jsonb)
CREATE OR REPLACE FUNCTION sokhach.record_cash_review(p jsonb)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'pg_catalog', 'sokhach', 'pg_temp'
AS $function$
DECLARE
 v_action text := p->>'action'; v_message text := p->>'message_id'; v_key text := p->>'request_id';
 v_conversation text := p->>'conversation_id'; v_reason text := nullif(btrim(p->>'reason'),''); v_amount bigint; v_kind text; v_id bigint;
 v_old sokhach.cash_report_review; v_row sokhach.cash_report_review; v_found boolean;
BEGIN
 IF jsonb_typeof(p)<>'object' OR v_action IS NULL OR v_action NOT IN ('confirm','target','amount','not_cash')
    OR coalesce(v_conversation,'') !~ '^[0-9a-f]{64}$' OR coalesce(v_message,'') !~ '^[0-9A-Za-z_-]{1,128}$'
    OR v_key IS NULL OR btrim(v_key)='' OR char_length(v_key)>200 OR char_length(coalesce(v_reason,''))>500 THEN
   RAISE EXCEPTION 'INVALID_CASH_REVIEW'; END IF;
 IF v_action='amount' THEN
   IF coalesce(p->>'amount_vnd','') !~ '^[1-9][0-9]{0,17}$' THEN RAISE EXCEPTION 'INVALID_CASH_REVIEW'; END IF;
   v_amount:=(p->>'amount_vnd')::bigint;
 ELSIF p ? 'amount_vnd' AND p->'amount_vnd'<>'null'::jsonb THEN RAISE EXCEPTION 'INVALID_CASH_REVIEW';
 END IF;
 IF v_action='target' THEN
   v_kind:=p->'target'->>'kind';
   IF jsonb_typeof(p->'target')<>'object' OR v_kind IS NULL OR v_kind NOT IN ('so','xe','tai_xe')
      OR coalesce(p->'target'->>'id','') !~ '^[1-9][0-9]{0,17}$' THEN RAISE EXCEPTION 'INVALID_CASH_REVIEW'; END IF;
   v_id:=(p->'target'->>'id')::bigint;
 ELSIF p ? 'target' AND p->'target'<>'null'::jsonb THEN RAISE EXCEPTION 'INVALID_CASH_REVIEW';
 END IF;
 IF v_action='not_cash' AND v_reason IS NULL THEN RAISE EXCEPTION 'REASON_REQUIRED'; END IF;
 -- Bấm lặp (mất mạng rồi gửi lại cùng mã): đúng nội dung cũ thì trả dòng đã ghi; khác bất kỳ trường nào thì từ chối, như record_mark.
 SELECT * INTO v_old FROM sokhach.cash_report_review c WHERE c.request_id=v_key;
 IF FOUND THEN
   IF (v_old.conversation_id,v_old.message_id,v_old.action,v_old.amount_vnd,v_old.target_kind,v_old.target_id,v_old.reason)
      IS DISTINCT FROM (v_conversation,v_message,v_action,v_amount,v_kind,v_id,v_reason) THEN RAISE EXCEPTION 'IDEMPOTENCY_CONFLICT'; END IF;
   RETURN sokhach._cash_review_json(v_old)||jsonb_build_object('replayed',true);
 END IF;
 IF v_action='target' THEN
   -- Mỗi bảng một câu: PL/pgSQL chỉ lập kế hoạch câu khi chạy tới, nên DB chưa có Đội xe vẫn gắn được sổ.
   IF v_kind='so' THEN v_found:=EXISTS(SELECT 1 FROM sokhach.customer c WHERE c.id=v_id);
   ELSIF v_kind='xe' AND to_regclass('doixe.xe') IS NOT NULL THEN v_found:=EXISTS(SELECT 1 FROM doixe.xe x WHERE x.id=v_id);
   ELSIF v_kind='tai_xe' AND to_regclass('doixe.nguoi') IS NOT NULL THEN v_found:=EXISTS(SELECT 1 FROM doixe.nguoi n WHERE n.id=v_id);
   END IF;
   IF NOT coalesce(v_found,false) THEN RAISE EXCEPTION 'TARGET_NOT_FOUND'; END IF;
 END IF;
 -- Hai người bấm cùng lúc trên một tin: xếp hàng theo tin, để `before` của người sau là trạng thái sau lượt của người trước.
 PERFORM pg_advisory_xact_lock(hashtextextended('cash_report_review:'||v_message,0));
 INSERT INTO sokhach.cash_report_review(conversation_id,message_id,action,target_kind,target_id,amount_vnd,before,reason,request_id,created_by)
   VALUES(v_conversation,v_message,v_action,v_kind,v_id,v_amount,
          sokhach._cash_review_state(v_message,NULL)-'last_by'-'last_at'-'last_action'-'reviews',v_reason,v_key,sokhach._actor())
   ON CONFLICT (request_id) DO NOTHING
   RETURNING * INTO v_row;
 IF v_row.id IS NULL THEN   -- cùng request_id vừa được người khác ghi giữa lúc kiểm và lúc ghi
   SELECT * INTO v_old FROM sokhach.cash_report_review c WHERE c.request_id=v_key;
   IF (v_old.conversation_id,v_old.message_id,v_old.action,v_old.amount_vnd,v_old.target_kind,v_old.target_id,v_old.reason)
      IS DISTINCT FROM (v_conversation,v_message,v_action,v_amount,v_kind,v_id,v_reason) THEN RAISE EXCEPTION 'IDEMPOTENCY_CONFLICT'; END IF;
   RETURN sokhach._cash_review_json(v_old)||jsonb_build_object('replayed',true);
 END IF;
 RETURN sokhach._cash_review_json(v_row);
END $function$;
ALTER FUNCTION sokhach.record_cash_review(jsonb) OWNER TO sokhach_owner;
REVOKE ALL ON FUNCTION sokhach.record_cash_review(jsonb) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION sokhach.record_cash_review(jsonb) TO sokhach_app;

-- FUNCTION sokhach.record_mark(jsonb)
CREATE OR REPLACE FUNCTION sokhach.record_mark(p jsonb)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'pg_catalog', 'sokhach', 'pg_temp'
AS $function$
DECLARE
 v_today date := (clock_timestamp() AT TIME ZONE 'Asia/Ho_Chi_Minh')::date;
 v_kind text := p->>'kind'; v_customer bigint; v_amount bigint; v_on date; v_key text := p->>'idempotency_key';
 v_old sokhach.contact_mark; v_row sokhach.contact_mark;
BEGIN
 IF jsonb_typeof(p)<>'object' OR v_kind IS NULL OR v_kind NOT IN ('promise','paid_claim','note')
    OR jsonb_typeof(p->'customer_id')<>'number' OR v_key IS NULL OR btrim(v_key)='' THEN RAISE EXCEPTION 'INVALID_MARK'; END IF;
 v_customer:=(p->>'customer_id')::bigint;
 -- VND là chuỗi số nguyên dương như mọi lệnh tiền (số JSON cũng nhận); chữ lạ là INVALID_MARK, không lỗi ép kiểu.
 IF p->>'amount_vnd' IS NOT NULL THEN
   IF p->>'amount_vnd' !~ '^[1-9][0-9]{0,17}$' THEN RAISE EXCEPTION 'INVALID_MARK'; END IF;
   v_amount:=(p->>'amount_vnd')::bigint;
 END IF;
 IF p->>'on_date' IS NOT NULL AND p->>'on_date' !~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$' THEN RAISE EXCEPTION 'INVALID_MARK'; END IF;
 IF p->>'on_date' IS NOT NULL THEN v_on:=(p->>'on_date')::date; END IF;
 SELECT * INTO v_old FROM sokhach.contact_mark m WHERE m.idempotency_key=v_key;
 IF FOUND THEN
   -- Bấm Lưu lặp (mất mạng rồi gửi lại): trả dấu đã ghi, không thêm dòng. Khóa dùng cho nội dung khác (khách, loại, tiền,
   -- ngày, ghi chú, tin gắn) thì từ chối, kể cả khi người dùng sửa ô sau lần gửi chưa rõ kết quả (audit 19/11/2026, A08).
   IF v_old.customer_id<>v_customer OR v_old.kind<>v_kind
      OR v_old.amount_vnd IS DISTINCT FROM v_amount OR v_old.on_date IS DISTINCT FROM v_on
      OR v_old.note IS DISTINCT FROM nullif(btrim(p->>'note'),'')
      OR v_old.conversation_id IS DISTINCT FROM p->>'conversation_id' OR v_old.message_id IS DISTINCT FROM p->>'message_id'
   THEN RAISE EXCEPTION 'IDEMPOTENCY_CONFLICT'; END IF;
   RETURN sokhach._mark_json(v_old,v_today)||jsonb_build_object('replayed',true);
 END IF;
 IF NOT EXISTS(SELECT 1 FROM sokhach.customer c WHERE c.id=v_customer) THEN RAISE EXCEPTION 'CUSTOMER_NOT_FOUND'; END IF;
 IF v_kind='note' AND (v_amount IS NOT NULL OR v_on IS NOT NULL OR p->>'note' IS NULL OR btrim(p->>'note')='') THEN
   RAISE EXCEPTION 'INVALID_MARK'; END IF;
 IF v_kind<>'note' AND (v_amount IS NULL OR v_amount<=0 OR v_on IS NULL) THEN RAISE EXCEPTION 'INVALID_MARK'; END IF;
 -- Hứa trả hẹn từ hôm nay tới một năm; khách báo đã chuyển là chuyện đã xảy ra, không sau hôm nay (giờ VN).
 IF v_kind='promise' AND (v_on<v_today OR v_on>v_today+366) THEN RAISE EXCEPTION 'INVALID_MARK_DATE'; END IF;
 IF v_kind='paid_claim' AND (v_on>v_today OR v_on<v_today-366) THEN RAISE EXCEPTION 'INVALID_MARK_DATE'; END IF;
 IF p->>'message_id' IS NOT NULL AND p->>'conversation_id' IS NULL THEN RAISE EXCEPTION 'INVALID_MARK'; END IF;
 INSERT INTO sokhach.contact_mark(customer_id,kind,amount_vnd,on_date,note,conversation_id,message_id,message_at,
     message_sender,message_excerpt,idempotency_key,created_by,created_on)
   VALUES(v_customer,v_kind,v_amount,v_on,nullif(btrim(p->>'note'),''),p->>'conversation_id',p->>'message_id',
     (p->>'message_at')::timestamptz,p->>'message_sender',p->>'message_excerpt',v_key,sokhach._actor(),v_today)
   RETURNING * INTO v_row;
 RETURN sokhach._mark_json(v_row,v_today);
END $function$;
ALTER FUNCTION sokhach.record_mark(jsonb) OWNER TO sokhach_owner;
REVOKE ALL ON FUNCTION sokhach.record_mark(jsonb) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION sokhach.record_mark(jsonb) TO sokhach_app;

-- FUNCTION sokhach.record_offset(bigint,bigint,bigint,bigint,text,date,bigint,text)
CREATE OR REPLACE FUNCTION sokhach.record_offset(target_customer_id bigint, target_version bigint, source_customer_id bigint, source_version bigint, idempotency_key text, date date, amount_vnd bigint, reference text DEFAULT NULL::text)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'pg_catalog', 'sokhach', 'pg_temp'
AS $function$
DECLARE v_payload jsonb:=jsonb_build_object('command','record_offset','target',target_customer_id,
        'source',source_customer_id,'date',date,'amount_vnd',amount_vnd)
        || CASE WHEN reference IS NULL THEN '{}'::jsonb ELSE jsonb_build_object('reference',reference) END;
    v_retry jsonb; v_credit numeric; v_receipt jsonb; v_pair sokhach.offset_pair%ROWTYPE;
    v_event bigint; v_id bigint; v_pid text; v_changes jsonb;
BEGIN
    v_retry:=sokhach._begin_offset(target_customer_id,target_version,source_customer_id,
        source_version,idempotency_key,v_payload);
    IF v_retry IS NOT NULL THEN RETURN v_retry; END IF;
    IF amount_vnd IS NULL OR amount_vnd<=0 THEN RAISE EXCEPTION 'INVALID_VND'; END IF;
    IF date IS NULL THEN RAISE EXCEPTION 'INVALID_DATE'; END IF;
    IF date>(clock_timestamp() AT TIME ZONE 'Asia/Ho_Chi_Minh')::date
    THEN RAISE EXCEPTION 'FUTURE_DATE'; END IF;
    IF EXISTS (SELECT 1 FROM sokhach.customer WHERE id=source_customer_id AND archived)
    THEN RAISE EXCEPTION 'OFFSET_SOURCE_ARCHIVED'; END IF;
    SELECT greatest(-sum(outstanding_vnd),0) INTO v_credit FROM sokhach.v_outstanding_month
        WHERE customer_id=source_customer_id;
    IF v_credit IS NULL OR amount_vnd>v_credit THEN
        RAISE EXCEPTION 'OFFSET_EXCEEDS_CREDIT'
            USING DETAIL=jsonb_build_object('available_credit_vnd',v_credit::text)::text;
    END IF;
    v_id:=nextval(pg_get_serial_sequence('sokhach.offset_pair','id'));
    v_pid:=sokhach._next_pid(source_customer_id);
    v_receipt:=sokhach.record_receipt(target_customer_id,target_version,
        chr(31)||'offset:'||v_id||':record',date,'CẤN TRỪ',amount_vnd,reference);
    INSERT INTO sokhach.event(customer_id,kind,actor,"before","after",idempotency_key)
    VALUES (source_customer_id,'receipt',sokhach._actor(),'{}',jsonb_build_object(
        'receipt',v_pid,'offset_pair_id',v_id,'pid',v_pid,'date',date,
        'amount_vnd',(-amount_vnd)::text,'counterparty_customer_id',target_customer_id,
        'counterparty_name',(SELECT name FROM sokhach.customer WHERE id=target_customer_id)),idempotency_key)
    RETURNING id INTO v_event;
    INSERT INTO sokhach.offset_pair(id,source_customer_id,target_customer_id,target_receipt_id,
        source_pid,date,amount_vnd,created_by_event) OVERRIDING SYSTEM VALUE
    VALUES(v_id,source_customer_id,target_customer_id,(v_receipt->>'receipt_id')::bigint,
        v_pid,date,amount_vnd,v_event) RETURNING * INTO v_pair;
    v_changes:=sokhach.reallocate(source_customer_id,idempotency_key);
    RETURN sokhach._finish_offset(v_pair,idempotency_key,v_payload,jsonb_build_object(
        'target_receipt',v_receipt,'source_reallocated',v_changes));
EXCEPTION WHEN numeric_value_out_of_range THEN RAISE EXCEPTION 'INVALID_VND';
END $function$;
ALTER FUNCTION sokhach.record_offset(bigint,bigint,bigint,bigint,text,date,bigint,text) OWNER TO sokhach_owner;
REVOKE ALL ON FUNCTION sokhach.record_offset(bigint,bigint,bigint,bigint,text,date,bigint,text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION sokhach.record_offset(bigint,bigint,bigint,bigint,text,date,bigint,text) TO sokhach_app;

-- FUNCTION sokhach.record_receipt(bigint,bigint,text,date,text,bigint,text)
CREATE OR REPLACE FUNCTION sokhach.record_receipt(customer_id bigint, expected_version bigint, idempotency_key text, date date, method text, amount_vnd bigint, reference text DEFAULT NULL::text)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'pg_catalog', 'sokhach', 'pg_temp'
AS $function$
DECLARE v_payload jsonb := jsonb_build_object('command','record_receipt','date',date,
        'method',method,'amount_vnd',amount_vnd)
        || CASE WHEN reference IS NULL THEN '{}'::jsonb ELSE jsonb_build_object('reference',reference) END;
        v_retry jsonb; v_id bigint; v_pid text; v_event bigint; v_left bigint;
        v_last date; v_month date; v_due bigint; v_take bigint; v_plan jsonb := '[]'::jsonb;
        v_line jsonb; v_result jsonb; v_plan_ids jsonb := '[]'::jsonb; v_changes jsonb;
BEGIN
    v_retry := sokhach._begin_command(customer_id,expected_version,idempotency_key,v_payload);
    IF v_retry IS NOT NULL THEN RETURN v_retry; END IF;
    PERFORM sokhach._baseline(customer_id);
    IF date IS NULL OR method NOT IN ('THU TIỀN','CẤN TRỪ','ỨNG TRƯỚC','KHÁC')
       OR amount_vnd IS NULL OR amount_vnd <= 0 THEN RAISE EXCEPTION 'INVALID_RECEIPT'; END IF;
    IF date > (clock_timestamp() AT TIME ZONE 'Asia/Ho_Chi_Minh')::date
       THEN RAISE EXCEPTION 'FUTURE_RECEIPT_DATE'; END IF;
    SELECT max(debt_month) INTO v_last FROM (
        SELECT debt_month FROM sokhach.opening_balance WHERE opening_balance.customer_id=record_receipt.customer_id
        UNION ALL SELECT debt_month FROM sokhach.v_trip_current v WHERE v.customer_id=record_receipt.customer_id AND NOT deleted AND status='confirmed'
        UNION ALL SELECT debt_month FROM sokhach.v_adjustment_current a WHERE a.customer_id=record_receipt.customer_id
        UNION ALL SELECT o.debt_month FROM sokhach.v_offset_outgoing o
            WHERE o.customer_id=record_receipt.customer_id
    ) m;
    IF v_last IS NULL THEN RAISE EXCEPTION 'NO_MONTH_FOR_RECEIPT'; END IF;
    v_pid := sokhach._next_pid(customer_id);
    v_id := nextval(pg_get_serial_sequence('sokhach.receipt','id'));
    v_left := amount_vnd;
    -- Xếp tạm theo số thô, cùng cách reallocate (CAN-DU-01 chỉ đổi số nợ hiển thị, không đổi dòng phân bổ).
    FOR v_month,v_due IN SELECT debt_month,outstanding_vnd FROM sokhach.v_outstanding_month_raw
        WHERE v_outstanding_month_raw.customer_id=record_receipt.customer_id ORDER BY debt_month
    LOOP
        EXIT WHEN v_left=0;
        IF v_due > 0 THEN
            v_take := least(v_left,v_due);
            v_plan := v_plan || jsonb_build_array(jsonb_build_object(
                'month',v_month,'kind','debt','amount_vnd',v_take::text));
            v_left := v_left-v_take;
        END IF;
    END LOOP;
    IF v_left>0 THEN
        v_plan := v_plan || jsonb_build_array(jsonb_build_object(
            'month',v_last,'kind','advance','amount_vnd',v_left::text));
    END IF;
    FOR v_line IN SELECT value FROM jsonb_array_elements(v_plan) LOOP
        v_plan_ids := v_plan_ids || jsonb_build_array(v_line ||
            jsonb_build_object('id',nextval(pg_get_serial_sequence('sokhach.receipt_line','id'))));
    END LOOP;
    INSERT INTO sokhach.event(customer_id,kind,actor,"before","after",idempotency_key)
    VALUES (customer_id,'receipt',sokhach._actor(),'{}',
        jsonb_build_object('receipt',v_id,'pid',v_pid,'date',date,'method',method,
                           'amount_vnd',amount_vnd::text,'reference',nullif(btrim(reference),''),'allocations',v_plan_ids),idempotency_key)
    RETURNING id INTO v_event;
    INSERT INTO sokhach.receipt(id,customer_id,pid,date,method,amount_vnd,reference,created_by_event)
    OVERRIDING SYSTEM VALUE VALUES (v_id,customer_id,v_pid,date,method,amount_vnd,nullif(btrim(reference),''),v_event);
    FOR v_line IN SELECT value FROM jsonb_array_elements(v_plan_ids) LOOP
        INSERT INTO sokhach.receipt_line(id,receipt_id,customer_id,debt_month,kind,amount_vnd,created_by_event)
        OVERRIDING SYSTEM VALUE VALUES ((v_line->>'id')::bigint,v_id,customer_id,(v_line->>'month')::date,v_line->>'kind',
                (v_line->>'amount_vnd')::bigint,v_event);
    END LOOP;
    -- V7-SO (sửa 29/10/2026): phiếu mới cũng phân bổ lại mọi phiếu chưa hủy theo (ngày, mã phiếu), nên dòng
    -- phân bổ đã lưu luôn là kết quả chuẩn và không đổi ở lệnh kế tiếp. Tổng nợ từng tháng không đổi.
    v_changes := sokhach.reallocate(customer_id,idempotency_key);
    v_result := jsonb_build_object('receipt_id',v_id,'pid',v_pid,'allocations',sokhach._lines(v_id),
                                  'reallocated',v_changes,'overpayment_vnd',v_left::text,
        'duplicate_reference',EXISTS (SELECT 1 FROM sokhach.receipt r
            WHERE r.customer_id=record_receipt.customer_id AND r.id<>v_id
              AND r.reference=nullif(btrim(record_receipt.reference),'')));
    RETURN sokhach._finish_command(customer_id,idempotency_key,v_payload,v_result);
END $function$;
ALTER FUNCTION sokhach.record_receipt(bigint,bigint,text,date,text,bigint,text) OWNER TO sokhach_owner;
REVOKE ALL ON FUNCTION sokhach.record_receipt(bigint,bigint,text,date,text,bigint,text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION sokhach.record_receipt(bigint,bigint,text,date,text,bigint,text) TO sokhach_app;

-- FUNCTION sokhach.record_reminder(bigint,text)
CREATE OR REPLACE FUNCTION sokhach.record_reminder(p_customer bigint, p_source text)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'pg_catalog', 'sokhach', 'pg_temp'
AS $function$
DECLARE v_at date := (clock_timestamp() AT TIME ZONE 'Asia/Ho_Chi_Minh')::date;
BEGIN
 IF p_source IS NULL OR p_source NOT IN ('zalo','copy-button','manual') THEN RAISE EXCEPTION 'INVALID_REMINDER'; END IF;
 IF NOT EXISTS(SELECT 1 FROM sokhach.customer c WHERE c.id=p_customer) THEN RAISE EXCEPTION 'CUSTOMER_NOT_FOUND'; END IF;
 INSERT INTO sokhach.reminder_log(customer_id,source,reminded_at,actor)
   VALUES(p_customer,p_source,v_at,sokhach._actor())
   ON CONFLICT(customer_id,source,reminded_at) DO NOTHING;
 RETURN jsonb_build_object('customer_id',p_customer,'source',p_source,'reminded_at',v_at);
END $function$;
ALTER FUNCTION sokhach.record_reminder(bigint,text) OWNER TO sokhach_owner;
REVOKE ALL ON FUNCTION sokhach.record_reminder(bigint,text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION sokhach.record_reminder(bigint,text) TO sokhach_app;

-- FUNCTION sokhach.reject_immutable_change()
CREATE OR REPLACE FUNCTION sokhach.reject_immutable_change()
 RETURNS trigger
 LANGUAGE plpgsql
 SET search_path TO 'pg_catalog', 'sokhach', 'pg_temp'
AS $function$
BEGIN
    RAISE EXCEPTION 'immutable row: %.%', TG_TABLE_SCHEMA, TG_TABLE_NAME;
END $function$;
ALTER FUNCTION sokhach.reject_immutable_change() OWNER TO sokhach_owner;
REVOKE ALL ON FUNCTION sokhach.reject_immutable_change() FROM PUBLIC;

-- FUNCTION sokhach.remove_receipt_image(bigint,bigint,text,bigint,text)
CREATE OR REPLACE FUNCTION sokhach.remove_receipt_image(customer_id bigint, expected_version bigint, idempotency_key text, image_id bigint, reason text)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'pg_catalog', 'sokhach', 'pg_temp'
AS $function$
DECLARE v_payload jsonb:=jsonb_build_object('command','remove_receipt_image','image_id',image_id,'reason',reason);
 v_retry jsonb; i sokhach.receipt_image%ROWTYPE; r sokhach.receipt%ROWTYPE; v_event bigint; v_image jsonb;
BEGIN
 v_retry:=sokhach._begin_command(customer_id,expected_version,idempotency_key,v_payload);
 IF v_retry IS NOT NULL THEN RETURN v_retry; END IF;
 IF reason IS NULL OR btrim(reason)='' THEN RAISE EXCEPTION 'IMAGE_REMOVE_REASON_REQUIRED'; END IF;
 SELECT * INTO i FROM sokhach.receipt_image WHERE receipt_image.id=remove_receipt_image.image_id
   AND receipt_image.customer_id=remove_receipt_image.customer_id FOR UPDATE;
 IF NOT FOUND THEN RAISE EXCEPTION 'IMAGE_NOT_FOUND'; END IF;
 IF i.removed_by_event IS NOT NULL THEN RAISE EXCEPTION 'IMAGE_ALREADY_REMOVED'; END IF;
 SELECT * INTO r FROM sokhach.receipt WHERE receipt.id=i.receipt_id;
 IF r.voided_by_event IS NOT NULL OR r.void_reason IS NOT NULL THEN RAISE EXCEPTION 'RECEIPT_ALREADY_VOID'; END IF;
 v_image:=jsonb_build_object('id',i.id,'receipt_id',r.id,'pid',r.pid,'sha256',i.sha256,'content_type',i.content_type,
   'byte_size',octet_length(i.data));
 INSERT INTO sokhach.event(customer_id,kind,actor,"before","after",idempotency_key)
   VALUES(customer_id,'receipt_image_remove',sokhach._actor(),jsonb_build_object('image',v_image),
     jsonb_build_object('image',v_image||jsonb_build_object('removed',true,'reason',btrim(reason))),idempotency_key)
   RETURNING id INTO v_event;
 UPDATE sokhach.receipt_image SET removed_reason=btrim(reason),removed_by_event=v_event WHERE receipt_image.id=i.id;
 RETURN sokhach._finish_command(customer_id,idempotency_key,v_payload,jsonb_build_object('image_id',i.id,'removed',true));
END $function$;
ALTER FUNCTION sokhach.remove_receipt_image(bigint,bigint,text,bigint,text) OWNER TO sokhach_owner;
REVOKE ALL ON FUNCTION sokhach.remove_receipt_image(bigint,bigint,text,bigint,text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION sokhach.remove_receipt_image(bigint,bigint,text,bigint,text) TO sokhach_app;

-- FUNCTION sokhach.rename_fee_type(text,bigint,text)
CREATE OR REPLACE FUNCTION sokhach.rename_fee_type(idempotency_key text, fee_type_id bigint, name text)
 RETURNS jsonb
 LANGUAGE sql
 SECURITY DEFINER
 SET search_path TO 'pg_catalog', 'sokhach', 'pg_temp'
AS $function$
 SELECT sokhach._change_fee_type(idempotency_key,'rename_fee_type',fee_type_id,name,NULL)
$function$;
ALTER FUNCTION sokhach.rename_fee_type(text,bigint,text) OWNER TO sokhach_owner;
REVOKE ALL ON FUNCTION sokhach.rename_fee_type(text,bigint,text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION sokhach.rename_fee_type(text,bigint,text) TO sokhach_app;

-- FUNCTION sokhach.replace_trip_fee(bigint,bigint,text,bigint,bigint,bigint,text)
CREATE OR REPLACE FUNCTION sokhach.replace_trip_fee(customer_id bigint, expected_version bigint, idempotency_key text, fee_line_id bigint, fee_type_id bigint, amount_vnd bigint, note text)
 RETURNS jsonb
 LANGUAGE sql
 SECURITY DEFINER
 SET search_path TO 'pg_catalog', 'sokhach', 'pg_temp'
AS $function$
 SELECT sokhach._change_trip_fees(customer_id,expected_version,idempotency_key,'replace_trip_fee',NULL,fee_type_id,amount_vnd,note,fee_line_id)
$function$;
ALTER FUNCTION sokhach.replace_trip_fee(bigint,bigint,text,bigint,bigint,bigint,text) OWNER TO sokhach_owner;
REVOKE ALL ON FUNCTION sokhach.replace_trip_fee(bigint,bigint,text,bigint,bigint,bigint,text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION sokhach.replace_trip_fee(bigint,bigint,text,bigint,bigint,bigint,text) TO sokhach_app;

-- FUNCTION sokhach.resolve_sheet_conflict(bigint,bigint,text,text,bigint,text,bigint,text,text,text,text)
CREATE OR REPLACE FUNCTION sokhach.resolve_sheet_conflict(customer_id bigint, expected_version bigint, idempotency_key text, snapshot_sha256 text, source_row bigint, target_kind text, target_id bigint, field text, target_value text, sheet_value text, decision text)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'pg_catalog', 'sokhach', 'pg_temp'
AS $function$
DECLARE v_payload jsonb := jsonb_build_object('command','resolve_sheet_conflict',
        'snapshot_sha256',snapshot_sha256,'source_row',source_row,'target_kind',target_kind,
        'target_id',target_id,'field',field,'target_value',target_value,
        'sheet_value',sheet_value,'decision',decision);
    v_retry jsonb; v_trip sokhach.v_trip_current%ROWTYPE; v_legacy jsonb;
    v_event bigint; v_before text; v_after text;
BEGIN
    v_retry := sokhach._begin_command(customer_id,expected_version,idempotency_key,v_payload);
    IF v_retry IS NOT NULL THEN RETURN v_retry; END IF;
    PERFORM sokhach._baseline(customer_id);
    IF snapshot_sha256 !~ '^[0-9a-f]{64}$' OR source_row <= 0 OR target_id <= 0
       OR target_kind NOT IN ('trip','legacy')
       OR field NOT IN ('carrier','shipper','origin','destination','event_date','booking')
       OR decision NOT IN ('keep_web','use_sheet') OR sheet_value IS NULL
       -- Date edits must use the normal edit path; posted booking never changes.
       OR (field IN ('event_date','booking') AND decision<>'keep_web')
       OR (field='booking' AND target_kind<>'trip') THEN
        RAISE EXCEPTION 'INVALID_SHEET_RESOLUTION';
    END IF;
    IF target_kind='trip' THEN
        SELECT * INTO v_trip FROM sokhach.v_trip_current t
          WHERE t.id=target_id AND t.customer_id=resolve_sheet_conflict.customer_id AND NOT t.deleted;
        IF NOT FOUND THEN RAISE EXCEPTION 'TRIP_NOT_FOUND'; END IF;
        v_before:=to_jsonb(v_trip)->>field;
    ELSE
        SELECT sokhach._legacy_current(l.id) INTO v_legacy FROM sokhach.legacy_row l
          JOIN sokhach.cutover_customer cc USING(customer_id,cutover_id)
          JOIN sokhach.cutover c ON c.id=cc.cutover_id
          WHERE l.id=target_id AND l.customer_id=resolve_sheet_conflict.customer_id
            AND l.kind='trip' AND cc.status='active' AND c.status='active';
        IF NOT FOUND OR (v_legacy->>'deleted')::boolean THEN RAISE EXCEPTION 'LEGACY_NOT_FOUND'; END IF;
        v_before:=CASE WHEN field='shipper' THEN coalesce(nullif(btrim(v_legacy->>'shipper'),''),v_legacy->>'carrier')
          ELSE v_legacy->>field END;
    END IF;
    -- KIEM-TAB-01 (K4): chuỗi rỗng và NULL là cùng một giá trị "chưa có"; phần đọc của web gửi NULL cho chủ hàng ''.
    IF nullif(btrim(v_before),'') IS DISTINCT FROM nullif(btrim(target_value),'') THEN RAISE EXCEPTION 'STALE_LEDGER'; END IF;
    IF decision='use_sheet' AND nullif(btrim(sheet_value),'') IS NULL THEN
        RAISE EXCEPTION 'INVALID_SHEET_RESOLUTION';
    END IF;
    -- KHOA-CHU-01 (1/11/2026): lấy theo Sheet cho bốn ô chữ mô tả không cần tháng mở.
    IF decision='use_sheet' AND field NOT IN ('carrier','shipper','origin','destination') THEN
        PERFORM sokhach._month_open(customer_id,CASE WHEN target_kind='trip' THEN v_trip.debt_month
          ELSE (v_legacy->>'debt_month')::date END,clock_timestamp());
    END IF;
    v_after:=CASE WHEN decision='use_sheet' THEN btrim(sheet_value) ELSE v_before END;
    INSERT INTO sokhach.event(customer_id,kind,actor,"before","after",idempotency_key)
      VALUES(customer_id,'sheet_conflict_resolved',sokhach._actor(),
        jsonb_build_object('target',jsonb_build_object('kind',target_kind,'id',target_id),
          'field',field,'value',v_before),
        jsonb_build_object('snapshot_sha256',snapshot_sha256,'source_row',source_row,
          'target',jsonb_build_object('kind',target_kind,'id',target_id),
          'field',field,'sheet_value',sheet_value,'target_value',v_after,'decision',decision),
        idempotency_key) RETURNING id INTO v_event;
    IF decision='use_sheet' THEN
      IF target_kind='trip' THEN
        INSERT INTO sokhach.trip_info_rev(trip_id,customer_id,debt_month,event_date,container,
          carrier,shipper,origin,destination,status,created_by_event)
        VALUES(v_trip.id,customer_id,v_trip.debt_month,v_trip.event_date,v_trip.container,
          CASE WHEN field='carrier' THEN v_after ELSE v_trip.carrier END,
          CASE WHEN field='shipper' THEN v_after ELSE v_trip.shipper END,
          CASE WHEN field='origin' THEN v_after ELSE v_trip.origin END,
          CASE WHEN field='destination' THEN v_after ELSE v_trip.destination END,
          v_trip.status,v_event);
      ELSE
        v_legacy:=v_legacy||jsonb_build_object(field,v_after);
        INSERT INTO sokhach.legacy_trip_rev(legacy_row_id,customer_id,debt_month,event_date,
          container,carrier,shipper,origin,destination,unit_price_vnd,other_fee_vnd,
          deleted,counted_vnd,created_by_event)
        VALUES(target_id,customer_id,(v_legacy->>'debt_month')::date,
          (v_legacy->>'event_date')::date,v_legacy->>'container',v_legacy->>'carrier',
          v_legacy->>'shipper',v_legacy->>'origin',v_legacy->>'destination',
          (v_legacy->>'unit_price_vnd')::bigint,(v_legacy->>'other_fee_vnd')::bigint,
          false,(v_legacy->>'counted_vnd')::bigint,v_event);
      END IF;
    END IF;
    RETURN sokhach._finish_command(customer_id,idempotency_key,v_payload,
      jsonb_build_object('resolved',true,'field',field,'decision',decision));
END $function$;
ALTER FUNCTION sokhach.resolve_sheet_conflict(bigint,bigint,text,text,bigint,text,bigint,text,text,text,text) OWNER TO sokhach_owner;
REVOKE ALL ON FUNCTION sokhach.resolve_sheet_conflict(bigint,bigint,text,text,bigint,text,bigint,text,text,text,text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION sokhach.resolve_sheet_conflict(bigint,bigint,text,text,bigint,text,bigint,text,text,text,text) TO sokhach_app;

-- FUNCTION sokhach.review_trip(bigint,bigint,text,bigint,text,text)
CREATE OR REPLACE FUNCTION sokhach.review_trip(customer_id bigint, expected_version bigint, idempotency_key text, trip_id bigint, decision text, reason text)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'pg_catalog', 'sokhach', 'pg_temp'
AS $function$
DECLARE v_payload jsonb := jsonb_build_object('command','review_trip','trip_id',trip_id,
        'decision',decision,'reason',reason);
        v_retry jsonb; v_trip sokhach.v_trip_current%ROWTYPE; v_status text; v_event bigint;
        v_changes jsonb := '[]'::jsonb;
BEGIN
    v_retry := sokhach._begin_command(customer_id,expected_version,idempotency_key,v_payload);
    IF v_retry IS NOT NULL THEN RETURN v_retry; END IF;
    PERFORM sokhach._baseline(customer_id);
    v_status := CASE decision WHEN 'confirm' THEN 'confirmed' WHEN 'reject' THEN 'rejected' END;
    IF v_status IS NULL THEN RAISE EXCEPTION 'INVALID_REVIEW'; END IF;
    IF reason IS NULL OR btrim(reason)='' THEN RAISE EXCEPTION 'REVIEW_REASON_REQUIRED'; END IF;
    SELECT * INTO v_trip FROM sokhach.v_trip_current v WHERE v.id=trip_id AND v.customer_id=review_trip.customer_id AND NOT v.deleted;
    IF NOT FOUND THEN RAISE EXCEPTION 'TRIP_NOT_FOUND'; END IF;
    IF v_trip.status<>'pending_review' THEN RAISE EXCEPTION 'TRIP_NOT_PENDING'; END IF;
    PERFORM sokhach._month_open(customer_id,v_trip.debt_month,clock_timestamp());
    INSERT INTO sokhach.event(customer_id,kind,actor,"before","after",idempotency_key)
    VALUES (customer_id,'trip_review',sokhach._actor(),
        jsonb_build_object('trip',trip_id,'container',v_trip.container,'status','pending_review'),
        jsonb_build_object('trip',trip_id,'container',v_trip.container,'status',v_status,
            'review_reason',btrim(reason)),idempotency_key)
    RETURNING id INTO v_event;
    INSERT INTO sokhach.trip_info_rev(trip_id,customer_id,debt_month,event_date,container,carrier,shipper,origin,destination,status,created_by_event)
    VALUES (v_trip.id,customer_id,v_trip.debt_month,v_trip.event_date,v_trip.container,v_trip.carrier,v_trip.shipper,v_trip.origin,v_trip.destination,v_status,v_event);
    IF v_status='confirmed' THEN v_changes := sokhach.reallocate(customer_id,idempotency_key); END IF;
    RETURN sokhach._finish_command(customer_id,idempotency_key,v_payload,
        jsonb_build_object('trip_id',trip_id,'status',v_status,'reallocated',v_changes));
END $function$;
ALTER FUNCTION sokhach.review_trip(bigint,bigint,text,bigint,text,text) OWNER TO sokhach_owner;
REVOKE ALL ON FUNCTION sokhach.review_trip(bigint,bigint,text,bigint,text,text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION sokhach.review_trip(bigint,bigint,text,bigint,text,text) TO sokhach_app;

-- FUNCTION sokhach.rewrite_trip_fees(bigint,bigint,text,jsonb,jsonb,jsonb,jsonb)
CREATE OR REPLACE FUNCTION sokhach.rewrite_trip_fees(customer_id bigint, expected_version bigint, idempotency_key text, target jsonb, expected_line_ids jsonb, lines jsonb, source jsonb)
 RETURNS jsonb
 LANGUAGE sql
 SECURITY DEFINER
 SET search_path TO 'pg_catalog', 'sokhach', 'pg_temp'
AS $function$
 SELECT sokhach._rewrite_trip_fees(customer_id,expected_version,idempotency_key,target,expected_line_ids,lines,source)
$function$;
ALTER FUNCTION sokhach.rewrite_trip_fees(bigint,bigint,text,jsonb,jsonb,jsonb,jsonb) OWNER TO sokhach_owner;
REVOKE ALL ON FUNCTION sokhach.rewrite_trip_fees(bigint,bigint,text,jsonb,jsonb,jsonb,jsonb) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION sokhach.rewrite_trip_fees(bigint,bigint,text,jsonb,jsonb,jsonb,jsonb) TO sokhach_app;

-- FUNCTION sokhach.save_price_table(bigint,bigint,text,jsonb)
CREATE OR REPLACE FUNCTION sokhach.save_price_table(customer_id bigint, expected_version bigint, idempotency_key text, price_table jsonb)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'pg_catalog', 'sokhach', 'pg_temp'
AS $function$
DECLARE v_payload jsonb:=jsonb_build_object('command','save_price_table','price_table',price_table);
 v_retry jsonb; v_before jsonb; v_after jsonb; v_item jsonb; v_alias jsonb; v_rate jsonb;
 v_name text; v_key text; v_dest text; v_dest_key text; v_loc bigint; v_period bigint; v_from date; v_to date; v_amount bigint; v_repriced jsonb;
 v_locked bigint; v_no_price bigint;
BEGIN
 v_retry:=sokhach._begin_command(customer_id,expected_version,idempotency_key,v_payload);
 IF v_retry IS NOT NULL THEN RETURN v_retry; END IF;
 IF jsonb_typeof(price_table) IS DISTINCT FROM 'object'
   OR EXISTS (SELECT 1 FROM jsonb_object_keys(price_table) k WHERE k NOT IN ('tt_shippers','locations','periods'))
   OR jsonb_typeof(price_table->'tt_shippers') IS DISTINCT FROM 'array'
   OR jsonb_typeof(price_table->'locations') IS DISTINCT FROM 'array'
   OR jsonb_typeof(price_table->'periods') IS DISTINCT FROM 'array'
 THEN RAISE EXCEPTION 'INVALID_PRICE_TABLE'; END IF;
 v_before:=sokhach._price_table(customer_id);
 DELETE FROM sokhach.price_rate r WHERE r.customer_id=save_price_table.customer_id;
 DELETE FROM sokhach.price_period p WHERE p.customer_id=save_price_table.customer_id;
 DELETE FROM sokhach.price_location_alias a WHERE a.customer_id=save_price_table.customer_id;
 DELETE FROM sokhach.price_location l WHERE l.customer_id=save_price_table.customer_id;
 DELETE FROM sokhach.price_tt_shipper s WHERE s.customer_id=save_price_table.customer_id;
 FOR v_item IN SELECT x FROM jsonb_array_elements(price_table->'tt_shippers') x LOOP
   v_name:=sokhach._price_text(v_item); v_key:=sokhach._price_key(v_name);
   IF EXISTS (SELECT 1 FROM sokhach.price_tt_shipper s WHERE s.customer_id=save_price_table.customer_id AND s.shipper_key=v_key)
   THEN RAISE EXCEPTION 'PRICE_DUPLICATE_SHIPPER'; END IF;
   INSERT INTO sokhach.price_tt_shipper(customer_id,name,shipper_key) VALUES(customer_id,v_name,v_key);
 END LOOP;
 -- Tên kho và tên khác dùng chung một không gian khóa trong sổ: một cách viết chỉ trỏ một kho.
 FOR v_item IN SELECT x FROM jsonb_array_elements(price_table->'locations') x LOOP
   IF jsonb_typeof(v_item) IS DISTINCT FROM 'object'
     OR EXISTS (SELECT 1 FROM jsonb_object_keys(v_item) k WHERE k NOT IN ('name','aliases'))
     OR jsonb_typeof(coalesce(v_item->'aliases','[]')) IS DISTINCT FROM 'array'
   THEN RAISE EXCEPTION 'INVALID_PRICE_TABLE'; END IF;
   v_name:=sokhach._price_text(v_item->'name'); v_key:=sokhach._price_key(v_name);
   IF EXISTS (SELECT 1 FROM sokhach.price_location l WHERE l.customer_id=save_price_table.customer_id AND l.name_key=v_key)
     OR EXISTS (SELECT 1 FROM sokhach.price_location_alias a WHERE a.customer_id=save_price_table.customer_id AND a.alias_key=v_key)
   THEN RAISE EXCEPTION 'PRICE_DUPLICATE_ALIAS'; END IF;
   INSERT INTO sokhach.price_location(customer_id,name,name_key) VALUES(customer_id,v_name,v_key) RETURNING id INTO v_loc;
   FOR v_alias IN SELECT x FROM jsonb_array_elements(coalesce(v_item->'aliases','[]')) x LOOP
     v_name:=sokhach._price_text(v_alias); v_key:=sokhach._price_key(v_name);
     IF EXISTS (SELECT 1 FROM sokhach.price_location l WHERE l.customer_id=save_price_table.customer_id AND l.name_key=v_key)
       OR EXISTS (SELECT 1 FROM sokhach.price_location_alias a WHERE a.customer_id=save_price_table.customer_id AND a.alias_key=v_key)
     THEN RAISE EXCEPTION 'PRICE_DUPLICATE_ALIAS'; END IF;
     INSERT INTO sokhach.price_location_alias(customer_id,location_id,alias,alias_key) VALUES(customer_id,v_loc,v_name,v_key);
   END LOOP;
 END LOOP;
 FOR v_item IN SELECT x FROM jsonb_array_elements(price_table->'periods') x LOOP
   IF jsonb_typeof(v_item) IS DISTINCT FROM 'object'
     OR EXISTS (SELECT 1 FROM jsonb_object_keys(v_item) k WHERE k NOT IN ('valid_from','valid_to','rates'))
     OR jsonb_typeof(v_item->'rates') IS DISTINCT FROM 'array'
   THEN RAISE EXCEPTION 'INVALID_PRICE_TABLE'; END IF;
   v_from:=sokhach._price_date(v_item->'valid_from');
   v_to:=CASE WHEN jsonb_typeof(coalesce(v_item->'valid_to','null'))='null' THEN NULL ELSE sokhach._price_date(v_item->'valid_to') END;
   IF v_to<v_from THEN RAISE EXCEPTION 'PRICE_INVALID_PERIOD'; END IF;
   INSERT INTO sokhach.price_period(customer_id,valid_from,valid_to) VALUES(customer_id,v_from,v_to) RETURNING id INTO v_period;
   FOR v_rate IN SELECT x FROM jsonb_array_elements(v_item->'rates') x LOOP
     IF jsonb_typeof(v_rate) IS DISTINCT FROM 'object'
       OR (SELECT count(*) FROM jsonb_object_keys(v_rate) k WHERE k IN ('location','destination','tier','unit_price_vnd'))<>4
       OR (SELECT count(*) FROM jsonb_object_keys(v_rate))<>4
       OR v_rate->>'tier' IS NULL OR v_rate->>'tier' NOT IN ('khach','tt')
     THEN RAISE EXCEPTION 'INVALID_PRICE_TABLE'; END IF;
     IF jsonb_typeof(v_rate->'unit_price_vnd') IS DISTINCT FROM 'string' OR v_rate->>'unit_price_vnd' !~ '^(0|[1-9][0-9]{0,18})$'
     THEN RAISE EXCEPTION 'PRICE_INVALID_AMOUNT'; END IF;
     v_amount:=(v_rate->>'unit_price_vnd')::bigint;
     SELECT l.id INTO v_loc FROM sokhach.price_location l WHERE l.customer_id=save_price_table.customer_id
       AND l.name_key=sokhach._price_key(sokhach._price_text(v_rate->'location'));
     IF NOT FOUND THEN RAISE EXCEPTION 'PRICE_UNKNOWN_LOCATION'; END IF;
     -- BANG-GIA-04: Nơi đến trống (chuỗi rỗng) là giá chung của nơi đi.
     v_dest:=CASE WHEN jsonb_typeof(v_rate->'destination')='string' AND sokhach._price_key(v_rate->>'destination') IS NULL
       THEN '' ELSE sokhach._price_text(v_rate->'destination') END;
     v_dest_key:=coalesce(sokhach._price_key(v_dest),'');
     IF EXISTS (SELECT 1 FROM sokhach.price_rate r WHERE r.period_id=v_period AND r.location_id=v_loc AND r.destination_key=v_dest_key AND r.tier=v_rate->>'tier')
     THEN RAISE EXCEPTION 'PRICE_DUPLICATE_RATE'; END IF;
     INSERT INTO sokhach.price_rate(period_id,location_id,customer_id,destination,destination_key,tier,unit_price_vnd)
     VALUES(v_period,v_loc,customer_id,v_dest,v_dest_key,v_rate->>'tier',v_amount);
   END LOOP;
 END LOOP;
 -- Hai đợt có cùng kho và cùng nhóm giá không được chồng ngày (hai đầu đều tính).
 IF EXISTS (SELECT 1 FROM sokhach.price_rate r1 JOIN sokhach.price_period p1 ON p1.id=r1.period_id
     JOIN sokhach.price_rate r2 ON r2.location_id=r1.location_id AND r2.destination_key=r1.destination_key AND r2.tier=r1.tier AND r2.period_id>r1.period_id
     JOIN sokhach.price_period p2 ON p2.id=r2.period_id
     WHERE r1.customer_id=save_price_table.customer_id
       AND daterange(p1.valid_from,p1.valid_to,'[]') && daterange(p2.valid_from,p2.valid_to,'[]'))
 THEN RAISE EXCEPTION 'PRICE_PERIOD_OVERLAP'; END IF;
 v_after:=sokhach._price_table(customer_id);
 IF v_after=v_before THEN RAISE EXCEPTION 'NO_CHANGE'; END IF;
 INSERT INTO sokhach.event(customer_id,kind,actor,"before","after",idempotency_key)
 VALUES(customer_id,'price_table_edit',sokhach._actor(),jsonb_build_object('price_table',v_before),
   jsonb_build_object('price_table',v_after),idempotency_key);
 v_repriced:=sokhach._reprice_from_table(customer_id,idempotency_key);
 SELECT count(*) FILTER (WHERE x.lookup ? 'unit_price_vnd'),count(*) FILTER (WHERE NOT x.lookup ? 'unit_price_vnd')
   INTO v_locked,v_no_price FROM sokhach._price_trip_rows(save_price_table.customer_id) x
   WHERE x.from_table AND x.unit_price_vnd::text IS DISTINCT FROM x.lookup->>'unit_price_vnd';
 RETURN sokhach._finish_command(customer_id,idempotency_key,v_payload,
   jsonb_build_object('price_table',v_after,'affected_trips',v_locked+v_no_price,'repriced_trips',v_repriced->'trips',
     'repriced_delta_vnd',v_repriced->'delta_vnd','locked_trips',v_locked,'no_price_trips',v_no_price,
     'reallocated',v_repriced->'reallocated'));
EXCEPTION WHEN numeric_value_out_of_range THEN RAISE EXCEPTION 'PRICE_INVALID_AMOUNT';
END $function$;
ALTER FUNCTION sokhach.save_price_table(bigint,bigint,text,jsonb) OWNER TO sokhach_owner;
REVOKE ALL ON FUNCTION sokhach.save_price_table(bigint,bigint,text,jsonb) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION sokhach.save_price_table(bigint,bigint,text,jsonb) TO sokhach_app;

-- FUNCTION sokhach.schema_level()
CREATE OR REPLACE FUNCTION sokhach.schema_level()
 RETURNS integer
 LANGUAGE sql
 IMMUTABLE
 SET search_path TO 'pg_catalog', 'sokhach', 'pg_temp'
AS $function$ SELECT 2026112303 $function$;
ALTER FUNCTION sokhach.schema_level() OWNER TO sokhach_owner;
REVOKE ALL ON FUNCTION sokhach.schema_level() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION sokhach.schema_level() TO sokhach_app;

-- FUNCTION sokhach.set_book_fee_columns(bigint,bigint,text,jsonb)
CREATE OR REPLACE FUNCTION sokhach.set_book_fee_columns(customer_id bigint, expected_version bigint, idempotency_key text, fee_type_ids jsonb)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'pg_catalog', 'sokhach', 'pg_temp'
AS $function$
DECLARE v_payload jsonb:=jsonb_build_object('command','set_book_fee_columns','fee_type_ids',fee_type_ids);
 v_retry jsonb; v_before jsonb; v_type jsonb; v_seen bigint[]:='{}';
BEGIN
 BEGIN v_retry:=sokhach._begin_command(customer_id,expected_version,idempotency_key,v_payload);
 EXCEPTION WHEN raise_exception THEN
   IF SQLERRM='STALE_LEDGER' THEN RAISE EXCEPTION 'VERSION_CONFLICT'; ELSE RAISE; END IF;
 END;
 IF v_retry IS NOT NULL THEN RETURN v_retry; END IF;
 IF jsonb_typeof(fee_type_ids) IS DISTINCT FROM 'array' THEN RAISE EXCEPTION 'INVALID_COMMAND'; END IF;
 -- COT-PHU-PHI-01: không giới hạn số cột riêng.
 FOR v_type IN SELECT x FROM jsonb_array_elements(fee_type_ids) x LOOP
   IF jsonb_typeof(v_type)<>'number' OR v_type::text !~ '^[1-9][0-9]*$' OR v_type::text::bigint=ANY(v_seen)
   THEN RAISE EXCEPTION 'INVALID_COMMAND'; END IF;
   PERFORM 1 FROM sokhach.fee_type WHERE id=v_type::text::bigint AND active AND system_key IS DISTINCT FROM 'initial' FOR SHARE;
   IF NOT FOUND THEN RAISE EXCEPTION 'FEE_TYPE_INACTIVE'; END IF;
   v_seen:=array_append(v_seen,v_type::text::bigint);
 END LOOP;
 SELECT coalesce(jsonb_agg(fee_type_id ORDER BY position),'[]') INTO v_before FROM sokhach.book_fee_column b
   WHERE b.customer_id=set_book_fee_columns.customer_id;
 INSERT INTO sokhach.event(customer_id,kind,actor,"before","after",idempotency_key)
 VALUES(customer_id,'set_book_fee_columns',sokhach._actor(),jsonb_build_object('fee_columns',v_before),
   jsonb_build_object('fee_columns',fee_type_ids),idempotency_key);
 DELETE FROM sokhach.book_fee_column b WHERE b.customer_id=set_book_fee_columns.customer_id;
 INSERT INTO sokhach.book_fee_column(customer_id,fee_type_id,position)
 SELECT customer_id,x::text::bigint,n FROM jsonb_array_elements(fee_type_ids) WITH ORDINALITY a(x,n);
 RETURN sokhach._finish_command(customer_id,idempotency_key,v_payload,jsonb_build_object('fee_columns',fee_type_ids));
EXCEPTION WHEN numeric_value_out_of_range THEN RAISE EXCEPTION 'INVALID_COMMAND';
END $function$;
ALTER FUNCTION sokhach.set_book_fee_columns(bigint,bigint,text,jsonb) OWNER TO sokhach_owner;
REVOKE ALL ON FUNCTION sokhach.set_book_fee_columns(bigint,bigint,text,jsonb) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION sokhach.set_book_fee_columns(bigint,bigint,text,jsonb) TO sokhach_app;

-- FUNCTION sokhach.set_booking_name(bigint,bigint,text,text,boolean)
CREATE OR REPLACE FUNCTION sokhach.set_booking_name(customer_id bigint, expected_version bigint, idempotency_key text, name text, remove boolean)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'pg_catalog', 'sokhach', 'pg_temp'
AS $function$
DECLARE v_payload jsonb := jsonb_build_object('command','set_booking_name','name',name,'remove',remove);
 v_retry jsonb; v_owner bigint; v_customer jsonb; v_before jsonb; v_after jsonb;
BEGIN
 v_retry := sokhach._begin_command(customer_id, expected_version, idempotency_key, v_payload);
 IF v_retry IS NOT NULL THEN RETURN v_retry; END IF;
 IF remove IS NULL OR name IS NULL OR name <> btrim(name) OR name = '' OR char_length(name) > 200 OR position('  ' IN name) > 0
    OR name ~ '[[:cntrl:]]' OR name ~ U&'[\0080-\009F\00A0\00AD\1680\180E\2000-\200F\2028-\202F\205F-\206F\3000\FEFF]' OR name <> normalize(name, NFC) OR name <> upper(name)
 THEN RAISE EXCEPTION 'INVALID_BOOKING_NAME'; END IF;
 -- Khóa sổ của _begin_command chỉ chặn trong một sổ: hai sổ cùng gán một tên cùng lúc thì khóa theo tên.
 PERFORM pg_advisory_xact_lock(hashtextextended('booking_name:' || set_booking_name.name, 0));
 SELECT b.customer_id INTO v_owner FROM sokhach.booking_name b WHERE b.name = set_booking_name.name;
 SELECT to_jsonb(c) INTO v_customer FROM sokhach.customer c WHERE c.id = set_booking_name.customer_id;
 -- Sổ đã lưu trữ không nhận chuyến mới nên không gán thêm tên; bỏ tên vẫn được để dọn.
 IF NOT remove AND (v_customer->>'archived')::boolean THEN RAISE EXCEPTION 'CUSTOMER_ARCHIVED'; END IF;
 v_before := sokhach._booking_names(set_booking_name.customer_id);
 IF remove THEN
  IF v_owner IS DISTINCT FROM set_booking_name.customer_id THEN RAISE EXCEPTION 'NO_CHANGE'; END IF;
  DELETE FROM sokhach.booking_name b WHERE b.name = set_booking_name.name;
 ELSE
  IF v_owner = set_booking_name.customer_id THEN RAISE EXCEPTION 'NO_CHANGE'; END IF;
  IF v_owner IS NOT NULL THEN RAISE EXCEPTION 'BOOKING_NAME_TAKEN'; END IF;
  INSERT INTO sokhach.booking_name(name, customer_id, created_by)
  VALUES (set_booking_name.name, set_booking_name.customer_id, sokhach._actor());
 END IF;
 v_after := sokhach._booking_names(set_booking_name.customer_id);
 INSERT INTO sokhach.event(customer_id, kind, actor, "before", "after", idempotency_key)
 VALUES (set_booking_name.customer_id, 'customer_attr', sokhach._actor(),
  jsonb_build_object('customer', v_customer, 'booking_names', v_before),
  jsonb_build_object('customer', v_customer, 'booking_names', v_after,
   CASE WHEN remove THEN 'booking_name_removed' ELSE 'booking_name_added' END, set_booking_name.name),
  idempotency_key);
 RETURN sokhach._finish_command(set_booking_name.customer_id, idempotency_key, v_payload, jsonb_build_object('booking_names', v_after));
END $function$;
ALTER FUNCTION sokhach.set_booking_name(bigint,bigint,text,text,boolean) OWNER TO sokhach_owner;
REVOKE ALL ON FUNCTION sokhach.set_booking_name(bigint,bigint,text,text,boolean) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION sokhach.set_booking_name(bigint,bigint,text,text,boolean) TO sokhach_app;

-- FUNCTION sokhach.set_customer_archived(bigint,bigint,text,boolean)
CREATE OR REPLACE FUNCTION sokhach.set_customer_archived(customer_id bigint, expected_version bigint, idempotency_key text, archived boolean)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'pg_catalog', 'sokhach', 'pg_temp'
AS $function$
DECLARE v_payload jsonb := jsonb_build_object('command','set_customer_archived','archived',archived);
    v_retry jsonb; v_before jsonb; v_after jsonb; v_balance numeric;
BEGIN
    v_retry := sokhach._begin_command(customer_id,expected_version,idempotency_key,v_payload);
    IF v_retry IS NOT NULL THEN RETURN v_retry; END IF;
    IF archived IS NULL THEN RAISE EXCEPTION 'INVALID_COMMAND'; END IF;
    SELECT to_jsonb(c) INTO v_before FROM sokhach.customer c WHERE c.id=set_customer_archived.customer_id;
    IF (v_before->>'archived')::boolean = archived THEN RAISE EXCEPTION 'NO_CHANGE'; END IF;
    IF archived THEN
        SELECT coalesce(sum(v.outstanding_vnd),0) INTO v_balance FROM sokhach.v_outstanding_month v
         WHERE v.customer_id=set_customer_archived.customer_id;
        IF v_balance <> 0 THEN RAISE EXCEPTION 'ARCHIVE_BALANCE_NOT_ZERO'; END IF;
    END IF;
    UPDATE sokhach.customer c SET archived=set_customer_archived.archived WHERE c.id=set_customer_archived.customer_id
        RETURNING to_jsonb(c) INTO v_after;
    INSERT INTO sokhach.event(customer_id,kind,actor,"before","after",idempotency_key)
    VALUES (customer_id,'customer_attr',sokhach._actor(),jsonb_build_object('customer',v_before),
        jsonb_build_object('customer',v_after,'archived',archived),idempotency_key);
    RETURN sokhach._finish_command(customer_id,idempotency_key,v_payload,jsonb_build_object('archived',archived));
END $function$;
ALTER FUNCTION sokhach.set_customer_archived(bigint,bigint,text,boolean) OWNER TO sokhach_owner;
REVOKE ALL ON FUNCTION sokhach.set_customer_archived(bigint,bigint,text,boolean) FROM PUBLIC;

-- FUNCTION sokhach.set_customer_commodity(bigint,bigint,text,text)
CREATE OR REPLACE FUNCTION sokhach.set_customer_commodity(customer_id bigint, expected_version bigint, idempotency_key text, commodity_name text)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'pg_catalog', 'sokhach', 'pg_temp'
AS $function$
DECLARE v_payload jsonb:=jsonb_build_object('command','set_customer_commodity','commodity_name',commodity_name);
 v_retry jsonb; v_before jsonb; v_after jsonb; v_commodity bigint;
BEGIN
 v_retry:=sokhach._begin_command(customer_id,expected_version,idempotency_key,v_payload);
 IF v_retry IS NOT NULL THEN RETURN v_retry; END IF;
 IF commodity_name IS NULL OR commodity_name NOT IN ('Sầu riêng','Thanh long','Chuối','Mít','Dừa')
 THEN RAISE EXCEPTION 'INVALID_COMMAND'; END IF;
 SELECT to_jsonb(c) INTO v_before FROM sokhach.customer c WHERE c.id=customer_id;
 IF v_before->>'commodity_id' IS NOT NULL THEN RAISE EXCEPTION 'STALE_LEDGER'; END IF;
 INSERT INTO sokhach.commodity(name) VALUES(commodity_name) ON CONFLICT(name) DO NOTHING;
 SELECT id INTO v_commodity FROM sokhach.commodity WHERE name=commodity_name;
 UPDATE sokhach.customer c SET commodity_id=v_commodity WHERE c.id=customer_id RETURNING to_jsonb(c) INTO v_after;
 INSERT INTO sokhach.event(customer_id,kind,actor,"before","after",idempotency_key)
 VALUES(customer_id,'customer_attr',sokhach._actor(),jsonb_build_object('customer',v_before),
  jsonb_build_object('customer',v_after,'commodity_name',commodity_name),idempotency_key);
 RETURN sokhach._finish_command(customer_id,idempotency_key,v_payload,jsonb_build_object('commodity',commodity_name));
END $function$;
ALTER FUNCTION sokhach.set_customer_commodity(bigint,bigint,text,text) OWNER TO sokhach_owner;
REVOKE ALL ON FUNCTION sokhach.set_customer_commodity(bigint,bigint,text,text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION sokhach.set_customer_commodity(bigint,bigint,text,text) TO sokhach_app;

-- FUNCTION sokhach.set_customer_transport(bigint,bigint,text,text)
CREATE OR REPLACE FUNCTION sokhach.set_customer_transport(customer_id bigint, expected_version bigint, idempotency_key text, transport_mode text)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'pg_catalog', 'sokhach', 'pg_temp'
AS $function$
DECLARE v_payload jsonb:=jsonb_build_object('command','set_customer_transport','transport_mode',transport_mode);
 v_retry jsonb; v_before jsonb; v_after jsonb;
BEGIN
 v_retry:=sokhach._begin_command(customer_id,expected_version,idempotency_key,v_payload);
 IF v_retry IS NOT NULL THEN RETURN v_retry; END IF;
 IF transport_mode IS NULL OR transport_mode NOT IN ('CANG','BO') THEN RAISE EXCEPTION 'INVALID_COMMAND'; END IF;
 SELECT to_jsonb(c) INTO v_before FROM sokhach.customer c WHERE c.id=customer_id;
 IF v_before->>'commodity_id' IS NULL OR v_before->>'transport_mode' IS NOT NULL THEN RAISE EXCEPTION 'STALE_LEDGER'; END IF;
 UPDATE sokhach.customer c SET transport_mode=set_customer_transport.transport_mode WHERE c.id=customer_id RETURNING to_jsonb(c) INTO v_after;
 INSERT INTO sokhach.event(customer_id,kind,actor,"before","after",idempotency_key)
 VALUES(customer_id,'customer_attr',sokhach._actor(),jsonb_build_object('customer',v_before),
  jsonb_build_object('customer',v_after,'transport_mode',set_customer_transport.transport_mode),idempotency_key);
 RETURN sokhach._finish_command(customer_id,idempotency_key,v_payload,jsonb_build_object('transport_mode',set_customer_transport.transport_mode));
END $function$;
ALTER FUNCTION sokhach.set_customer_transport(bigint,bigint,text,text) OWNER TO sokhach_owner;
REVOKE ALL ON FUNCTION sokhach.set_customer_transport(bigint,bigint,text,text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION sokhach.set_customer_transport(bigint,bigint,text,text) TO sokhach_app;

-- FUNCTION sokhach.set_fee_type_active(text,bigint,boolean)
CREATE OR REPLACE FUNCTION sokhach.set_fee_type_active(idempotency_key text, fee_type_id bigint, active boolean)
 RETURNS jsonb
 LANGUAGE sql
 SECURITY DEFINER
 SET search_path TO 'pg_catalog', 'sokhach', 'pg_temp'
AS $function$
 SELECT sokhach._change_fee_type(idempotency_key,'set_fee_type_active',fee_type_id,active::text,NULL)
$function$;
ALTER FUNCTION sokhach.set_fee_type_active(text,bigint,boolean) OWNER TO sokhach_owner;
REVOKE ALL ON FUNCTION sokhach.set_fee_type_active(text,bigint,boolean) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION sokhach.set_fee_type_active(text,bigint,boolean) TO sokhach_app;

-- FUNCTION sokhach.set_fee_type_kind(text,bigint,text)
CREATE OR REPLACE FUNCTION sokhach.set_fee_type_kind(idempotency_key text, fee_type_id bigint, kind text)
 RETURNS jsonb
 LANGUAGE sql
 SECURITY DEFINER
 SET search_path TO 'pg_catalog', 'sokhach', 'pg_temp'
AS $function$
 SELECT sokhach._change_fee_type(idempotency_key,'set_fee_type_kind',fee_type_id,NULL,kind)
$function$;
ALTER FUNCTION sokhach.set_fee_type_kind(text,bigint,text) OWNER TO sokhach_owner;
REVOKE ALL ON FUNCTION sokhach.set_fee_type_kind(text,bigint,text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION sokhach.set_fee_type_kind(text,bigint,text) TO sokhach_app;

-- FUNCTION sokhach.set_month_lock(bigint,bigint,text,date,boolean)
CREATE OR REPLACE FUNCTION sokhach.set_month_lock(customer_id bigint, expected_version bigint, idempotency_key text, month date, locked boolean)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'pg_catalog', 'sokhach', 'pg_temp'
AS $function$
DECLARE v_payload jsonb := jsonb_build_object('command','set_month_lock','month',month,'locked',locked);
        v_retry jsonb; v_before boolean;
BEGIN
    v_retry := sokhach._begin_command(customer_id,expected_version,idempotency_key,v_payload);
    IF v_retry IS NOT NULL THEN RETURN v_retry; END IF;
    IF month IS NULL OR extract(day FROM month) <> 1 OR locked IS NULL
       THEN RAISE EXCEPTION 'INVALID_MONTH_LOCK'; END IF;
    SELECT coalesce((SELECT ms.locked FROM sokhach.month_state ms
        WHERE ms.customer_id=set_month_lock.customer_id AND ms.month=set_month_lock.month),
        month<>date_trunc('month',clock_timestamp() AT TIME ZONE 'Asia/Ho_Chi_Minh')::date)
    INTO v_before;
    INSERT INTO sokhach.event(customer_id,kind,actor,at,"before","after",idempotency_key)
    VALUES (customer_id,'month_lock',sokhach._actor(),clock_timestamp(),
        jsonb_build_object('month',month,'locked',v_before),
        jsonb_build_object('month',month,'locked',locked),idempotency_key);
    INSERT INTO sokhach.month_state(customer_id,month,locked,changed_by,changed_at)
    VALUES (customer_id,month,locked,sokhach._actor(),clock_timestamp())
    ON CONFLICT ON CONSTRAINT month_state_pkey DO UPDATE SET locked=excluded.locked,
        changed_by=excluded.changed_by,changed_at=excluded.changed_at;
    RETURN sokhach._finish_command(customer_id,idempotency_key,v_payload,
        jsonb_build_object('month',month,'locked',locked));
END $function$;
ALTER FUNCTION sokhach.set_month_lock(bigint,bigint,text,date,boolean) OWNER TO sokhach_owner;
REVOKE ALL ON FUNCTION sokhach.set_month_lock(bigint,bigint,text,date,boolean) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION sokhach.set_month_lock(bigint,bigint,text,date,boolean) TO sokhach_app;

-- FUNCTION sokhach.set_trip_fee_type(bigint,bigint,text,jsonb,bigint,bigint)
CREATE OR REPLACE FUNCTION sokhach.set_trip_fee_type(customer_id bigint, expected_version bigint, idempotency_key text, target jsonb, fee_type_id bigint, amount_vnd bigint)
 RETURNS jsonb
 LANGUAGE sql
 SECURITY DEFINER
 SET search_path TO 'pg_catalog', 'sokhach', 'pg_temp'
AS $function$
 SELECT sokhach._change_trip_fees(customer_id,expected_version,idempotency_key,'set_trip_fee_type',jsonb_build_array(target),fee_type_id,amount_vnd,NULL,NULL)
$function$;
ALTER FUNCTION sokhach.set_trip_fee_type(bigint,bigint,text,jsonb,bigint,bigint) OWNER TO sokhach_owner;
REVOKE ALL ON FUNCTION sokhach.set_trip_fee_type(bigint,bigint,text,jsonb,bigint,bigint) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION sokhach.set_trip_fee_type(bigint,bigint,text,jsonb,bigint,bigint) TO sokhach_app;

-- FUNCTION sokhach.undo_sheet_batch(bigint,bigint,text,jsonb)
CREATE OR REPLACE FUNCTION sokhach.undo_sheet_batch(customer_id bigint, expected_version bigint, idempotency_key text, command_keys jsonb)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'pg_catalog', 'sokhach', 'pg_temp'
AS $function$
DECLARE v_payload jsonb:=jsonb_build_object('command','undo_sheet_batch','command_keys',command_keys);
 v_retry jsonb; v_key text; v_undo_key text; e sokhach.event%ROWTYPE; v_version bigint;
 v_result jsonb; v_before jsonb; v_after jsonb; v_current jsonb; v_id bigint; v_event bigint; v_count bigint;
BEGIN
 v_retry:=sokhach._begin_command(customer_id,expected_version,idempotency_key,v_payload);
 IF v_retry IS NOT NULL THEN RETURN v_retry; END IF;
 PERFORM sokhach._baseline(customer_id);
 IF jsonb_typeof(command_keys) IS DISTINCT FROM 'array' OR jsonb_array_length(command_keys) NOT BETWEEN 1 AND 1000
  OR EXISTS(SELECT 1 FROM jsonb_array_elements(command_keys) k WHERE jsonb_typeof(k)<>'string' OR k#>>'{}' !~ '^[0-9a-f]{64}$')
  OR (SELECT count(DISTINCT k) FROM jsonb_array_elements_text(command_keys) k)<>jsonb_array_length(command_keys)
 THEN RAISE EXCEPTION 'INVALID_COMMAND'; END IF;
 v_version:=expected_version;
 FOR v_key IN SELECT k FROM jsonb_array_elements_text(command_keys) WITH ORDINALITY x(k,n) ORDER BY n DESC LOOP
  SELECT * INTO e FROM sokhach.event ev WHERE ev.customer_id=undo_sheet_batch.customer_id AND ev.idempotency_key=v_key
   AND ev.kind IN ('price_edit','receipt','legacy_edit') ORDER BY ev.id DESC LIMIT 1;
  IF NOT FOUND THEN RAISE EXCEPTION 'INVALID_COMMAND'; END IF;
  v_undo_key:=encode(sha256(convert_to(idempotency_key||':'||v_key,'UTF8')),'hex');
  IF e.kind='receipt' THEN
   v_result:=sokhach.void_receipt(customer_id,v_version,v_undo_key,e."after"->>'pid','Hoàn tác lần ghi từ Việc cần làm');
  ELSIF e.kind='price_edit' THEN
   v_before:=e."before"->'price'; v_after:=e."after"->'price'; v_id:=(v_after->>'trip_id')::bigint;
   v_current:=sokhach._trip_current_row(customer_id,v_id);  -- audit SQL F4: một chuyến, không dựng cả sổ mỗi khóa
   IF v_current IS NULL OR v_current->>'unit_price_vnd' IS DISTINCT FROM v_after->>'unit_price_vnd'
    OR v_current->>'other_fee_vnd' IS DISTINCT FROM v_after->>'other_fee_vnd' THEN RAISE EXCEPTION 'STALE_LEDGER'; END IF;
   v_result:=sokhach.edit_trip_price(customer_id,v_version,v_undo_key,v_id,
     (v_before->>'unit_price_vnd')::bigint,(v_before->>'other_fee_vnd')::bigint);
  ELSE
   v_before:=e."before"->'legacy'; v_after:=e."after"->'legacy'; v_id:=(v_before->>'legacy_row_id')::bigint;
   IF v_before->>'kind'<>'trip' OR v_before->>'field' NOT IN ('unit_price_vnd','other_fee_vnd') THEN RAISE EXCEPTION 'INVALID_COMMAND'; END IF;
   v_current:=sokhach._legacy_current(v_id);
   IF v_current->>'unit_price_vnd' IS DISTINCT FROM v_after->>'unit_price_vnd'
    OR v_current->>'counted_vnd' IS DISTINCT FROM v_after->>'counted_vnd' THEN RAISE EXCEPTION 'STALE_LEDGER'; END IF;
   v_result:=sokhach.edit_legacy_trip(customer_id,v_version,v_undo_key,v_id,v_before->>'field',v_before->>'value');
   v_current:=sokhach._legacy_current(v_id);
   v_count:=(v_before->>'counted_vnd')::bigint;
   IF (v_current->>'counted_vnd')::bigint<>v_count THEN
    -- Restoring an original-book price must also restore its original TOTAL, which may differ from price + fees.
    v_after:=v_current||jsonb_build_object('counted_vnd',v_count::text,'field','unit_price_vnd','value',v_current->'unit_price_vnd');
    INSERT INTO sokhach.event(customer_id,kind,actor,"before","after",idempotency_key)
    VALUES(customer_id,'legacy_edit',sokhach._actor(),jsonb_build_object('legacy',v_current),jsonb_build_object('legacy',v_after),v_undo_key) RETURNING id INTO v_event;
    INSERT INTO sokhach.legacy_trip_rev(legacy_row_id,customer_id,debt_month,event_date,container,carrier,shipper,origin,destination,unit_price_vnd,other_fee_vnd,deleted,counted_vnd,created_by_event)
    VALUES(v_id,customer_id,(v_current->>'month')::date,(v_current->>'event_date')::date,v_current->>'container',v_current->>'carrier',v_current->>'shipper',v_current->>'origin',v_current->>'destination',
     (v_current->>'unit_price_vnd')::bigint,(v_current->>'other_fee_vnd')::bigint,false,v_count,v_event);
    INSERT INTO sokhach.adjustment(customer_id,debt_month,legacy_row_id,amount_vnd,actor,created_by_event)
    VALUES(customer_id,(v_current->>'month')::date,v_id,v_count-(v_current->>'counted_vnd')::bigint,sokhach._actor(),v_event);
   END IF;
  END IF;
  v_version:=(v_result->>'version')::bigint;
 END LOOP;
 PERFORM sokhach.reallocate(customer_id,idempotency_key);
 RETURN sokhach._finish_command(customer_id,idempotency_key,v_payload,jsonb_build_object('undone',jsonb_array_length(command_keys),'complete',true));
END $function$;
ALTER FUNCTION sokhach.undo_sheet_batch(bigint,bigint,text,jsonb) OWNER TO sokhach_owner;
REVOKE ALL ON FUNCTION sokhach.undo_sheet_batch(bigint,bigint,text,jsonb) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION sokhach.undo_sheet_batch(bigint,bigint,text,jsonb) TO sokhach_app;

-- FUNCTION sokhach.unlink_zalo(text,bigint,text)
CREATE OR REPLACE FUNCTION sokhach.unlink_zalo(p_conversation text, p_customer bigint, p_reason text)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'pg_catalog', 'sokhach', 'pg_temp'
AS $function$
BEGIN
 IF p_reason IS NULL OR btrim(p_reason)='' THEN RAISE EXCEPTION 'REASON_REQUIRED'; END IF;
 UPDATE sokhach.zalo_link l SET unlinked_by=sokhach._actor(),unlinked_at=now(),unlink_reason=btrim(p_reason)
   WHERE l.conversation_id=p_conversation AND l.customer_id=p_customer AND l.unlinked_at IS NULL;
 IF NOT FOUND THEN RAISE EXCEPTION 'LINK_NOT_FOUND'; END IF;
 RETURN jsonb_build_object('conversation_id',p_conversation,'customer_id',p_customer,'unlinked',true);
END $function$;
ALTER FUNCTION sokhach.unlink_zalo(text,bigint,text) OWNER TO sokhach_owner;
REVOKE ALL ON FUNCTION sokhach.unlink_zalo(text,bigint,text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION sokhach.unlink_zalo(text,bigint,text) TO sokhach_app;

-- FUNCTION sokhach.v7_fee_migration_dry_run()
CREATE OR REPLACE FUNCTION sokhach.v7_fee_migration_dry_run()
 RETURNS TABLE(orphan_zero_fee bigint, null_price_with_adjustment bigint)
 LANGUAGE sql
 SECURITY DEFINER
 SET search_path TO 'pg_catalog', 'sokhach', 'pg_temp'
AS $function$
 SELECT (SELECT count(*) FROM sokhach.trip t JOIN LATERAL
   (SELECT unit_price_vnd,other_fee_vnd FROM sokhach.trip_price_rev p WHERE p.trip_id=t.id ORDER BY p.id DESC LIMIT 1)p ON true
   WHERE coalesce(t.container,'')='' AND p.unit_price_vnd IS NULL
     AND (p.other_fee_vnd IS NOT NULL OR EXISTS(SELECT 1 FROM sokhach.adjustment a
       WHERE a.trip_id=t.id AND a.field='other_fee_vnd' AND NOT a.fee_absorbed))
     AND coalesce(p.other_fee_vnd,0)+coalesce((SELECT sum(a.amount_vnd) FROM sokhach.adjustment a
       WHERE a.trip_id=t.id AND a.field='other_fee_vnd' AND NOT a.fee_absorbed),0)=0
     AND NOT EXISTS(SELECT 1 FROM sokhach.trip_fee_line l WHERE l.trip_id=t.id)),
   (SELECT count(DISTINCT t.id) FROM sokhach.adjustment a JOIN sokhach.trip t ON t.id=a.trip_id
     JOIN LATERAL(SELECT unit_price_vnd FROM sokhach.trip_price_rev p WHERE p.trip_id=t.id ORDER BY p.id DESC LIMIT 1)p ON true
     WHERE a.field='other_fee_vnd' AND NOT a.fee_absorbed AND p.unit_price_vnd IS NULL
       AND coalesce(t.container,'')<>'' AND NOT EXISTS(SELECT 1 FROM sokhach.trip_fee_line l WHERE l.trip_id=t.id));
$function$;
ALTER FUNCTION sokhach.v7_fee_migration_dry_run() OWNER TO sokhach_owner;
REVOKE ALL ON FUNCTION sokhach.v7_fee_migration_dry_run() FROM PUBLIC;

-- FUNCTION sokhach.verify_cutover(bigint,text,text)
CREATE OR REPLACE FUNCTION sokhach.verify_cutover(cutover_id bigint, idempotency_key text, signoff_ref text)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'pg_catalog', 'sokhach', 'pg_temp'
AS $function$
DECLARE v_payload jsonb:=jsonb_build_object('command','verify_cutover','signoff_ref',signoff_ref);
        v_retry jsonb; v_result jsonb;
BEGIN
    v_retry:=sokhach._begin_cutover(cutover_id,idempotency_key,v_payload);
    IF v_retry IS NOT NULL THEN RETURN v_retry; END IF;
    IF (SELECT status FROM sokhach.cutover WHERE id=verify_cutover.cutover_id)<>'draft'
    THEN RAISE EXCEPTION 'CUTOVER_TRANSITION_ORDER'; END IF;
    PERFORM sokhach._check_cutover(cutover_id);
    UPDATE sokhach.cutover SET status='verified' WHERE id=verify_cutover.cutover_id;
    v_result:=jsonb_build_object('cutover_id',cutover_id,'status','verified');
    RETURN sokhach._finish_cutover(cutover_id,idempotency_key,v_payload,v_result);
END $function$;
ALTER FUNCTION sokhach.verify_cutover(bigint,text,text) OWNER TO sokhach_owner;
REVOKE ALL ON FUNCTION sokhach.verify_cutover(bigint,text,text) FROM PUBLIC;

-- FUNCTION sokhach.verify_cutover_customer(bigint,bigint,bigint,text,text)
CREATE OR REPLACE FUNCTION sokhach.verify_cutover_customer(customer_id bigint, cutover_id bigint, expected_version bigint, idempotency_key text, signoff_ref text)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'pg_catalog', 'sokhach', 'pg_temp'
AS $function$
DECLARE v_payload jsonb := jsonb_build_object('command','verify_cutover_customer',
        'cutover_id',cutover_id,'signoff_ref',signoff_ref);
        v_retry jsonb; v_result jsonb;
BEGIN
    PERFORM 1 FROM sokhach.cutover WHERE id=verify_cutover_customer.cutover_id FOR UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION 'CUTOVER_NOT_FOUND'; END IF;
    v_retry := sokhach._begin_command(customer_id,expected_version,idempotency_key,v_payload);
    IF v_retry IS NOT NULL THEN RETURN v_retry; END IF;
    IF NOT EXISTS(SELECT 1 FROM sokhach.cutover_customer cc
      JOIN sokhach.cutover c ON c.id=cc.cutover_id
      WHERE cc.customer_id=verify_cutover_customer.customer_id
        AND cc.cutover_id=verify_cutover_customer.cutover_id
        AND cc.status='draft' AND c.status='draft')
    THEN RAISE EXCEPTION 'CUTOVER_TRANSITION_ORDER'; END IF;
    PERFORM sokhach._check_cutover_customer(customer_id,cutover_id);
    UPDATE sokhach.cutover_customer SET status='verified'
      WHERE cutover_customer.customer_id=verify_cutover_customer.customer_id
        AND cutover_customer.cutover_id=verify_cutover_customer.cutover_id;
    v_result:=jsonb_build_object('cutover_id',cutover_id,'customer_id',customer_id,
        'status','verified');
    RETURN sokhach._finish_command(customer_id,idempotency_key,v_payload,v_result);
END $function$;
ALTER FUNCTION sokhach.verify_cutover_customer(bigint,bigint,bigint,text,text) OWNER TO sokhach_owner;
REVOKE ALL ON FUNCTION sokhach.verify_cutover_customer(bigint,bigint,bigint,text,text) FROM PUBLIC;

-- FUNCTION sokhach.void_offset(bigint,bigint,bigint,text,bigint,text)
CREATE OR REPLACE FUNCTION sokhach.void_offset(customer_id bigint, expected_version bigint, other_version bigint, idempotency_key text, offset_pair_id bigint, reason text)
 RETURNS jsonb
 LANGUAGE sql
 SECURITY DEFINER
 SET search_path TO 'pg_catalog', 'sokhach', 'pg_temp'
AS $function$
    SELECT sokhach._change_offset(customer_id,expected_version,other_version,idempotency_key,
        offset_pair_id,NULL,reason,true)
$function$;
ALTER FUNCTION sokhach.void_offset(bigint,bigint,bigint,text,bigint,text) OWNER TO sokhach_owner;
REVOKE ALL ON FUNCTION sokhach.void_offset(bigint,bigint,bigint,text,bigint,text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION sokhach.void_offset(bigint,bigint,bigint,text,bigint,text) TO sokhach_app;

-- FUNCTION sokhach.void_receipt(bigint,bigint,text,text,text)
CREATE OR REPLACE FUNCTION sokhach.void_receipt(customer_id bigint, expected_version bigint, idempotency_key text, pid text, reason text)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'pg_catalog', 'sokhach', 'pg_temp'
AS $function$
DECLARE v_payload jsonb := jsonb_build_object('command','void_receipt','pid',pid,'reason',reason);
        v_retry jsonb; v_receipt sokhach.receipt%ROWTYPE; v_before jsonb;
        v_event bigint; v_count bigint;
BEGIN
    IF EXISTS (SELECT 1 FROM sokhach.offset_pair p JOIN sokhach.receipt r ON r.id=p.target_receipt_id
        WHERE r.customer_id=void_receipt.customer_id AND r.pid=void_receipt.pid)
    THEN RAISE EXCEPTION 'OFFSET_PAIR_REQUIRED'; END IF;
    v_retry := sokhach._begin_command(customer_id,expected_version,idempotency_key,v_payload);
    IF v_retry IS NOT NULL THEN RETURN v_retry; END IF;
    PERFORM sokhach._baseline(customer_id);
    IF reason IS NULL OR btrim(reason)='' THEN RAISE EXCEPTION 'VOID_REASON_REQUIRED'; END IF;
    SELECT * INTO v_receipt FROM sokhach.receipt
     WHERE receipt.customer_id=void_receipt.customer_id AND receipt.pid=void_receipt.pid;
    IF NOT FOUND THEN RAISE EXCEPTION 'RECEIPT_NOT_FOUND'; END IF;
    IF v_receipt.voided_on IS NOT NULL THEN RAISE EXCEPTION 'RECEIPT_ALREADY_VOID'; END IF;
    v_before := sokhach._lines(v_receipt.id);
    INSERT INTO sokhach.event(customer_id,kind,actor,"before","after",idempotency_key)
    VALUES (customer_id,'void',sokhach._actor(),
        jsonb_build_object('receipt',v_receipt.id,'pid',pid,'amount_vnd',v_receipt.amount_vnd::text,
            'allocations',v_before),
        jsonb_build_object('receipt',v_receipt.id,'pid',pid,'void_reason',btrim(reason),
            'allocations','[]'::jsonb),idempotency_key)
    RETURNING id INTO v_event;
    UPDATE sokhach.receipt_line SET superseded_by_event=v_event
    WHERE receipt_id=v_receipt.id AND superseded_by_event IS NULL;
    GET DIAGNOSTICS v_count = ROW_COUNT;
    IF v_count <> jsonb_array_length(v_before) THEN RAISE EXCEPTION 'VOID_LINE_MISMATCH'; END IF;
    UPDATE sokhach.receipt SET void_reason=btrim(reason),
        voided_on=(clock_timestamp() AT TIME ZONE 'Asia/Ho_Chi_Minh')::date,
        voided_by=sokhach._actor(),voided_by_event=v_event WHERE id=v_receipt.id;
    PERFORM sokhach._check_allocations(customer_id);
    RETURN sokhach._finish_command(customer_id,idempotency_key,v_payload,
        jsonb_build_object('receipt_id',v_receipt.id,'pid',pid,'voided_lines',v_count));
END $function$;
ALTER FUNCTION sokhach.void_receipt(bigint,bigint,text,text,text) OWNER TO sokhach_owner;
REVOKE ALL ON FUNCTION sokhach.void_receipt(bigint,bigint,text,text,text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION sokhach.void_receipt(bigint,bigint,text,text,text) TO sokhach_app;

-- FUNCTION sokhach.void_trip_fee(bigint,bigint,text,bigint)
CREATE OR REPLACE FUNCTION sokhach.void_trip_fee(customer_id bigint, expected_version bigint, idempotency_key text, fee_line_id bigint)
 RETURNS jsonb
 LANGUAGE sql
 SECURITY DEFINER
 SET search_path TO 'pg_catalog', 'sokhach', 'pg_temp'
AS $function$
 SELECT sokhach._change_trip_fees(customer_id,expected_version,idempotency_key,'void_trip_fee',NULL,NULL,NULL,NULL,fee_line_id)
$function$;
ALTER FUNCTION sokhach.void_trip_fee(bigint,bigint,text,bigint) OWNER TO sokhach_owner;
REVOKE ALL ON FUNCTION sokhach.void_trip_fee(bigint,bigint,text,bigint) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION sokhach.void_trip_fee(bigint,bigint,text,bigint) TO sokhach_app;
