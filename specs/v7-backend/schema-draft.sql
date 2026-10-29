-- DRAFT — NOT A MIGRATION — KHÔNG CHẠY
-- Ngày 19/10/2026. Thiết kế: specs/v7-backend/thiet-ke.md.
-- PostgreSQL 18; schema nháp cho container test. Thân hàm ở tools/v7_backend_functions.sql.
-- Đã chạy harness trên dữ liệu giả; chưa kiểm dữ liệu thật hay duyệt ghi tiền.

CREATE ROLE sokhach_owner NOLOGIN;
CREATE ROLE sokhach_app NOLOGIN;
CREATE ROLE sokhach_reader NOLOGIN;
-- ĐỀ XUẤT: role migration phải có quyền SET ROLE sokhach_owner.
-- Script này chỉ là bản nháp, không chạy trên DB thật.
CREATE SCHEMA sokhach AUTHORIZATION sokhach_owner;
REVOKE ALL ON SCHEMA sokhach FROM PUBLIC;
SET ROLE sokhach_owner;

CREATE TABLE sokhach.commodity (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name text NOT NULL CHECK (btrim(name) <> ''),
    UNIQUE (name)
);
COMMENT ON TABLE sokhach.commodity IS 'Danh mục mặt hàng (cột LOAI HANG của tab TONG); chỉ để phân loại, không tham gia tính nợ.';

CREATE TABLE sokhach.customer (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name text NOT NULL CHECK (btrim(name) <> ''),
    commodity_id bigint REFERENCES sokhach.commodity(id),
    transport_mode text CHECK (transport_mode IN ('CANG', 'BO')),
    archived boolean NOT NULL DEFAULT false,
    version bigint NOT NULL DEFAULT 0 CHECK (version >= 0)
);
COMMENT ON TABLE sokhach.customer IS 'Một khách là đơn vị khóa và kiểm phiên bản cho lệnh ghi.';
COMMENT ON COLUMN sokhach.customer.commodity_id IS 'Mặt hàng của sổ này (một dòng TONG = một sổ = một mặt hàng); NULL = chưa gán, chỉ tô màu, không chặn.';
COMMENT ON COLUMN sokhach.customer.transport_mode IS 'Phương thức vận chuyển của sổ: CANG (cảng) hoặc BO (đường bộ); NULL = không phân biệt/chưa gán. Trên TONG, sầu riêng tách CANG/BO; xoài và thanh long có thêm nhóm "BỘ"; các mặt hàng còn lại không ghi.';
COMMENT ON COLUMN sokhach.customer.archived IS 'Sổ lưu trữ: xem được, không tính vào thống kê. Chỉ áp dụng cho tab không có dòng TONG và không có số dư mở; khách có nợ không được archive.';
COMMENT ON COLUMN sokhach.customer.version IS 'Tăng sau mỗi lệnh ghi; expected_version cũ bị từ chối.';

CREATE TABLE sokhach.cutover (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name text NOT NULL CHECK (btrim(name) <> ''),
    source text NOT NULL CHECK (btrim(source) <> ''),
    source_sha256 text NOT NULL CHECK (source_sha256 ~ '^[0-9a-fA-F]{64}$'),
    frozen_at timestamptz NOT NULL,
    control_total_vnd bigint NOT NULL,
    status text NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'verified', 'active')),
    created_by text NOT NULL CHECK (btrim(created_by) <> ''),
    created_at timestamptz NOT NULL DEFAULT now()
);
COMMENT ON TABLE sokhach.cutover IS 'ĐỀ XUẤT: mốc nguồn draft, verified, active; chuyển trạng thái chỉ qua gate đối soát và kích hoạt riêng.';
COMMENT ON COLUMN sokhach.cutover.status IS 'Draft không hiệu lực; verified đã đối soát nhưng chưa hiệu lực; active chỉ sau gate kích hoạt riêng.';
COMMENT ON COLUMN sokhach.cutover.control_total_vnd IS 'Tổng kiểm toàn mốc có dấu; đối chiếu sau khi nhập đủ khách, không thay tổng kiểm từng khách của import_cutover.';

CREATE TABLE sokhach.cutover_customer (
    customer_id bigint PRIMARY KEY REFERENCES sokhach.customer(id),
    cutover_id bigint NOT NULL REFERENCES sokhach.cutover(id),
    expected_control_total_vnd bigint NOT NULL,
    status text NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'verified', 'active')),
    report_sha256 text NOT NULL CHECK (report_sha256 ~ '^[0-9a-fA-F]{64}$'),
    source_rows bigint NOT NULL CHECK (source_rows >= 0),
    imported_rows bigint NOT NULL CHECK (imported_rows >= 0),
    quarantined_rows bigint NOT NULL CHECK (quarantined_rows >= 0),
    skipped_with_reason_rows bigint NOT NULL CHECK (skipped_with_reason_rows >= 0),
    unresolved_exceptions bigint NOT NULL CHECK (unresolved_exceptions >= 0),
    UNIQUE (customer_id, cutover_id),
    CHECK (source_rows = imported_rows + quarantined_rows + skipped_with_reason_rows)
);
COMMENT ON TABLE sokhach.cutover_customer IS 'ĐỀ XUẤT: gate riêng từng khách kể cả số dư 0; customer_id duy nhất tạm chặn nhập mốc thứ hai. Báo cáo nguồn ngoài repo.';

CREATE TABLE sokhach.cutover_month_check (
    customer_id bigint NOT NULL,
    cutover_id bigint NOT NULL,
    debt_month date NOT NULL CHECK (EXTRACT(DAY FROM debt_month) = 1),
    opening_anchor_vnd bigint,
    source_cumulative_vnd bigint,
    replay_cumulative_vnd bigint, -- client gửi chỉ để đối chiếu, không phải chứng cứ gate
    bucket_vnd bigint,
    standard_bucket_vnd bigint,
    source_charge_vnd bigint,
    source_receipt_vnd bigint CHECK (source_receipt_vnd >= 0),
    standard_source_ref text CHECK (btrim(standard_source_ref) <> ''),
    standard_source_sha256 text CHECK (standard_source_sha256 ~ '^[0-9a-fA-F]{64}$'),
    source_evidence_sha256 text CHECK (source_evidence_sha256 ~ '^[0-9a-fA-F]{64}$'),
    exception_codes text[] NOT NULL DEFAULT '{}'::text[]
        CHECK (exception_codes <@ ARRAY['NO_BASELINE', 'MISSING_PRICE',
            'MISSING_CACHE', 'HISTORICAL_DELTA_600', 'OTHER']::text[]),
    PRIMARY KEY (customer_id, cutover_id, debt_month),
    FOREIGN KEY (customer_id, cutover_id) REFERENCES sokhach.cutover_customer(customer_id, cutover_id)
);
COMMENT ON TABLE sokhach.cutover_month_check IS 'ĐỀ XUẤT: mỏ neo và dòng tiền nguồn từng tháng để tính FIFO độc lập với bucket nhập; NULL tiền/chứng cứ chặn, exception_codes giữ nguyên và không chặn khi số khớp.';
COMMENT ON COLUMN sokhach.cutover_month_check.opening_anchor_vnd IS 'ĐỀ XUẤT: mỏ neo nguồn trước tháng đầu, lặp cùng giá trị ở chuỗi tháng; NULL chặn verify, không thay bằng 0.';
COMMENT ON COLUMN sokhach.cutover_month_check.replay_cumulative_vnd IS 'Client gửi chỉ để đối chiếu; DB không dùng làm chứng cứ verify.';
COMMENT ON COLUMN sokhach.cutover_month_check.standard_bucket_vnd IS 'ĐỀ XUẤT: bucket nợ còn lại theo kỳ sau FIFO, tính lại từ mỏ neo đầu kỳ, phát sinh và thu nguồn; không lấy hiệu mỏ neo hay bucket nhập.';
COMMENT ON COLUMN sokhach.cutover_month_check.source_charge_vnd IS 'ĐỀ XUẤT: tổng phát sinh có dấu của kỳ từ dòng nguồn; NULL chặn verify.';
COMMENT ON COLUMN sokhach.cutover_month_check.source_receipt_vnd IS 'ĐỀ XUẤT: tổng thu của kỳ từ dòng nguồn; NULL chặn verify.';
COMMENT ON COLUMN sokhach.cutover_month_check.standard_source_ref IS 'Tham chiếu mỏ neo đầu, phát sinh, thu và mỏ neo cuối trong nguồn; dữ liệu nguồn giữ ngoài repo.';
-- Gate chuyển trạng thái có thân hàm trong tools/v7_backend_functions.sql: MỌI lệnh cùng mốc khóa cutover
-- trước, rồi customer theo ID tăng dần; kể cả import_cutover và trigger chứng cứ.
-- So bucket_vnd = standard_bucket_vnd = opening_balance.amount_vnd TỪNG tháng;
-- replay_cumulative_vnd chỉ để đối chiếu, không là chứng cứ độc lập.
-- ĐỀ XUẤT: DB tính chuỗi mỏ neo = opening_anchor_vnd + SUM(phát sinh - thu);
-- bucket FIFO từ mỏ neo đầu + phát sinh tháng đầu, phát sinh tháng sau, trừ
-- tổng thu vào nợ dương cũ trước; tổng bucket phải bằng mỏ neo cuối.
-- mọi số và standard_source_ref/standard_source_sha256/source_evidence_sha256 NOT NULL,
-- Giữ exception_codes dù gate cơ học đạt; cờ không tự biến NULL thành 0.
-- Đồng thời so tổng khách, tổng mốc và số dòng đã nhập. Chứng cứ 100% dòng
-- nguồn thật còn thiếu; đề xuất source_movement + manifest trong thiet-ke.md.
-- Thứ tự: verify_cutover_customer (mọi khách) -> verify_cutover ->
-- activate_cutover -> activate_cutover_customer (từng khách). View đòi cả hai active.

CREATE TABLE sokhach.opening_balance (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id bigint NOT NULL,
    cutover_id bigint NOT NULL,
    debt_month date NOT NULL CHECK (EXTRACT(DAY FROM debt_month) = 1),
    amount_vnd bigint NOT NULL,
    source_tab text NOT NULL CHECK (btrim(source_tab) <> ''),
    source_row bigint NOT NULL CHECK (source_row > 0),
    UNIQUE (customer_id, debt_month, cutover_id),
    FOREIGN KEY (customer_id, cutover_id) REFERENCES sokhach.cutover_customer(customer_id, cutover_id)
);
COMMENT ON TABLE sokhach.opening_balance IS 'Số dư đầu theo khách và tháng tại mốc chuyển, chỉ thêm; lịch sử nguồn không cộng lại.';
COMMENT ON COLUMN sokhach.opening_balance.amount_vnd IS 'Có dấu: âm là khách ứng trước; 0 chỉ ghi khi nguồn chứng minh đúng 0, NULL không được phép.';
COMMENT ON COLUMN sokhach.opening_balance.source_row IS 'Dòng mỏ neo trong tab nguồn, không chứa dữ liệu nguồn trong bản nháp.';

CREATE TABLE sokhach.legacy_row (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id bigint NOT NULL,
    cutover_id bigint NOT NULL,
    debt_month date NOT NULL CHECK (EXTRACT(DAY FROM debt_month) = 1),
    kind text NOT NULL CHECK (kind IN ('trip', 'receipt')),
    display jsonb NOT NULL CHECK (jsonb_typeof(display) = 'object'),
    source_total_vnd bigint,
    source_tab text NOT NULL CHECK (btrim(source_tab) <> ''),
    source_row bigint NOT NULL CHECK (source_row > 0),
    UNIQUE (cutover_id, source_tab, source_row),
    FOREIGN KEY (customer_id, cutover_id) REFERENCES sokhach.cutover_customer(customer_id, cutover_id)
);
COMMENT ON TABLE sokhach.legacy_row IS 'Dòng chuyến/thu đã nằm trong số dư đầu: chỉ hiển thị, không sửa, không phân bổ lại; không cột nào của bảng này tham gia công thức tiền.';
COMMENT ON COLUMN sokhach.legacy_row.display IS 'Các ô hiển thị từ nguồn; cấu trúc từng loại và dữ liệu thiếu cần review khi viết import.';
COMMENT ON COLUMN sokhach.legacy_row.source_total_vnd IS 'Thành tiền lịch sử theo ô tổng của sổ gốc; chỉ hiển thị, không cộng vào nợ.';

CREATE TABLE sokhach.month_state (
    customer_id bigint NOT NULL REFERENCES sokhach.customer(id),
    month date NOT NULL CHECK (EXTRACT(DAY FROM month) = 1),
    locked boolean NOT NULL,
    changed_by text NOT NULL CHECK (btrim(changed_by) <> ''),
    changed_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (customer_id, month)
);
COMMENT ON TABLE sokhach.month_state IS 'Cờ ghi đè; thiếu hàng thì chỉ tháng hiện tại theo Asia/Ho_Chi_Minh mở. Mở/khóa ghi event theo V7-CSM.';
COMMENT ON COLUMN sokhach.month_state.locked IS 'Không DEFAULT: thiếu hàng dùng mặc định động theo giờ VN; hàng có sẵn ghi đè mặc định.';
COMMENT ON COLUMN sokhach.month_state.changed_by IS 'Danh tính phiên máy chủ đã xác minh, không lấy từ body.';

CREATE TABLE sokhach.trip (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id bigint NOT NULL REFERENCES sokhach.customer(id),
    debt_month date NOT NULL CHECK (EXTRACT(DAY FROM debt_month) = 1),
    event_date date,
    container text,
    booking text,
    status text NOT NULL DEFAULT 'confirmed' CHECK (status IN ('confirmed','pending_review','rejected')),
    CONSTRAINT trip_missing_date_fee_only CHECK (event_date IS NOT NULL OR container IS NULL OR container = ''),
    carrier text,
    shipper text,
    origin text,
    destination text,
    note text,
    source_ref text,
    UNIQUE (id, customer_id, debt_month)
);
COMMENT ON TABLE sokhach.trip IS 'Danh tính chuyến chỉ thêm; container không phải khóa duy nhất.';
COMMENT ON COLUMN sokhach.trip.container IS 'Phân loại phí lẻ theo JS truthiness: chỉ NULL hoặc chuỗi rỗng là không có container; chuỗi toàn khoảng trắng vẫn là giá trị có mặt.';
COMMENT ON COLUMN sokhach.trip.debt_month IS 'Tháng gốc giữ FK; kỳ nợ hiện tại ở v_trip_current theo NHAP-SHEET-01.';
COMMENT ON COLUMN sokhach.trip.event_date IS 'Ngày xe nhập kho gốc; sửa ngày qua trip_info_rev, kỳ nợ hiện tại theo tháng ngày chuyến.';
COMMENT ON COLUMN sokhach.trip.source_ref IS 'Tham chiếu nguồn nếu có; không chứa chứng từ thật trong bản nháp.';

-- Read-only reference; no monetary amounts. Cutover identity freezes provenance.
CREATE TABLE sokhach.baseline_trip_ref (
    cutover_id bigint NOT NULL REFERENCES sokhach.cutover(id),
    booking_norm text NOT NULL,
    container_norm text NOT NULL,
    event_date date
);
CREATE INDEX baseline_trip_ref_code ON sokhach.baseline_trip_ref(cutover_id,booking_norm,container_norm);
CREATE INDEX baseline_trip_ref_date ON sokhach.baseline_trip_ref(cutover_id,container_norm,event_date);

CREATE TABLE sokhach.trip_price_rev (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    trip_id bigint NOT NULL REFERENCES sokhach.trip(id),
    unit_price_vnd bigint CHECK (unit_price_vnd >= 0),
    other_fee_vnd bigint,
    created_at timestamptz NOT NULL DEFAULT now()
);
-- ĐỀ XUẤT: CHECK liên bảng cho ngày NULL; deferred để paste chèn trip rồi giá.
CREATE FUNCTION sokhach.check_trip_missing_date() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog, sokhach, pg_temp AS $$
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
END $$;
CREATE CONSTRAINT TRIGGER trip_missing_date_check AFTER INSERT ON sokhach.trip
    DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION sokhach.check_trip_missing_date();
CREATE CONSTRAINT TRIGGER trip_price_missing_date_check AFTER INSERT ON sokhach.trip_price_rev
    DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION sokhach.check_trip_missing_date();
COMMENT ON TABLE sokhach.trip_price_rev IS 'Giá hiện tại là revision id lớn nhất của chuyến; sửa giá thêm dòng.';
COMMENT ON COLUMN sokhach.trip_price_rev.unit_price_vnd IS 'NULL là chưa biết, không phải 0.';
COMMENT ON COLUMN sokhach.trip_price_rev.other_fee_vnd IS 'NULL giữ nguyên từ nguồn; ĐÃ CHỐT 20/10/2026: khi có đơn giá thì phụ phí NULL tính 0, không đổi NULL lưu trữ.';

CREATE TABLE sokhach.adjustment (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id bigint NOT NULL REFERENCES sokhach.customer(id),
    debt_month date NOT NULL CHECK (EXTRACT(DAY FROM debt_month) = 1),
    trip_id bigint,
    amount_vnd bigint NOT NULL CHECK (amount_vnd <> 0),
    field text CHECK (field IN ('unit_price_vnd','other_fee_vnd')),
    fee_absorbed boolean NOT NULL DEFAULT false,
    new_value_vnd bigint CHECK (new_value_vnd >= 0),
    CHECK ((field IS NULL) = (new_value_vnd IS NULL)),
    note text,
    actor text NOT NULL CHECK (btrim(actor) <> ''),
    at timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (trip_id, customer_id, debt_month)
        REFERENCES sokhach.trip(id, customer_id, debt_month)
);
COMMENT ON TABLE sokhach.adjustment IS 'Hiệu số có dấu, tính ngay; trip_id NULL là điều chỉnh cả tháng.';
COMMENT ON COLUMN sokhach.adjustment.amount_vnd IS 'Khác 0; số đúng theo chuyến do hàm lệnh đổi thành hiệu số.';
COMMENT ON COLUMN sokhach.adjustment.note IS 'Ghi chú tùy chọn, không phải điều kiện ghi tiền V7.';

CREATE TABLE IF NOT EXISTS sokhach.fee_type(
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,name text NOT NULL,
 kind text NOT NULL CHECK(kind IN('service','pass_through')),sign text NOT NULL CHECK(sign IN('positive','negative','any')),
 system_key text UNIQUE,active boolean NOT NULL DEFAULT true,sort integer NOT NULL CHECK(sort>0),
 name_key text GENERATED ALWAYS AS(lower(btrim(name))) STORED,UNIQUE(name_key));
CREATE TABLE IF NOT EXISTS sokhach.book_fee_column(
 customer_id bigint NOT NULL REFERENCES sokhach.customer(id),fee_type_id bigint NOT NULL REFERENCES sokhach.fee_type(id),
 position integer NOT NULL CHECK(position BETWEEN 1 AND 3),PRIMARY KEY(customer_id,fee_type_id),UNIQUE(customer_id,position));
CREATE TABLE IF NOT EXISTS sokhach.trip_fee_line(
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,customer_id bigint NOT NULL REFERENCES sokhach.customer(id),trip_id bigint,legacy_row_id bigint,
 fee_type_id bigint NOT NULL REFERENCES sokhach.fee_type(id),amount_vnd bigint NOT NULL CHECK(amount_vnd<>0),note text,created_by_event bigint NOT NULL,voided_by_event bigint,
 CHECK((trip_id IS NOT NULL)<>(legacy_row_id IS NOT NULL)));
CREATE TABLE IF NOT EXISTS sokhach.fee_type_audit(
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,fee_type_id bigint REFERENCES sokhach.fee_type(id),actor text NOT NULL,payload jsonb NOT NULL,before_value jsonb NOT NULL,after_value jsonb NOT NULL,idempotency_key text NOT NULL UNIQUE,at timestamptz NOT NULL DEFAULT now());
CREATE INDEX IF NOT EXISTS trip_fee_line_trip_active ON sokhach.trip_fee_line(trip_id) WHERE voided_by_event IS NULL;
CREATE INDEX IF NOT EXISTS trip_fee_line_legacy_active ON sokhach.trip_fee_line(legacy_row_id) WHERE voided_by_event IS NULL;
CREATE INDEX IF NOT EXISTS trip_fee_line_customer ON sokhach.trip_fee_line(customer_id,id);
INSERT INTO sokhach.fee_type(name,kind,sign,system_key,sort) VALUES
 ('Neo','service','positive',NULL,1),('Điện','service','positive',NULL,2),('Ghép','service','positive',NULL,3),('Bảo hiểm','service','positive',NULL,4),('Kiểm định','service','positive',NULL,5),('Health cert','service','positive',NULL,6),('Khác','service','positive','other',100),('Giảm trừ','service','negative','discount',101),('Phụ phí ban đầu','service','any','initial',102) ON CONFLICT(name_key) DO NOTHING;

CREATE TABLE sokhach.receipt (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id bigint NOT NULL REFERENCES sokhach.customer(id),
    pid text NOT NULL CHECK (btrim(pid) <> ''),
    date date NOT NULL,
    method text NOT NULL CHECK (method IN ('THU TIỀN', 'CẤN TRỪ', 'ỨNG TRƯỚC', 'KHÁC')),
    reference text CHECK (reference IS NULL OR btrim(reference) <> ''),
    amount_vnd bigint NOT NULL CHECK (amount_vnd > 0),
    void_reason text CHECK (void_reason IS NULL OR btrim(void_reason) <> ''),
    voided_on date,
    voided_by text CHECK (voided_by IS NULL OR btrim(voided_by) <> ''),
    meta_changed_by_event bigint,
    voided_by_event bigint,
    UNIQUE (customer_id, pid),
    UNIQUE (id, customer_id),
    CHECK ((void_reason IS NULL AND voided_on IS NULL AND voided_by IS NULL
            AND voided_by_event IS NULL)
        OR (void_reason IS NOT NULL AND voided_on IS NOT NULL AND voided_by IS NOT NULL
            AND voided_by_event IS NOT NULL))
);
COMMENT ON TABLE sokhach.receipt IS 'Một phiếu của một khách; hủy không phân bổ lại phiếu khác.';
COMMENT ON COLUMN sokhach.receipt.pid IS 'Mã phiếu do server cấp, duy nhất trong khách kể cả đã hủy.';
COMMENT ON COLUMN sokhach.receipt.reference IS 'V7-CSM: optional text; duplicate warns only; blank stored as NULL.';
COMMENT ON COLUMN sokhach.receipt.date IS 'Ngày phiếu; FIFO xếp theo ngày rồi pid.';
COMMENT ON COLUMN sokhach.receipt.amount_vnd IS 'Tổng phiếu bất biến; phải bằng tổng dòng hiệu lực khi phiếu còn sống.';
COMMENT ON COLUMN sokhach.receipt.void_reason IS 'Hủy bắt buộc lý do không rỗng.';

CREATE TABLE sokhach.event (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id bigint NOT NULL REFERENCES sokhach.customer(id),
    kind text NOT NULL CONSTRAINT event_kind_check CHECK (kind IN ('paste', 'price_edit', 'adjust_trip',
        'adjust_month', 'receipt', 'receipt_edit', 'void', 'reallocation', 'month_lock', 'import',
        'customer_attr', 'trip_review', 'trip_edit', 'trip_delete', 'legacy_edit', 'legacy_delete',
        'sheet_conflict_resolved', 'fee_migration', 'add_trip_fees', 'set_trip_fee_type', 'replace_trip_fee', 'void_trip_fee', 'set_book_fee_columns')),
    actor text NOT NULL CHECK (btrim(actor) <> ''),
    at timestamptz NOT NULL DEFAULT now(),
    "before" jsonb NOT NULL CHECK (jsonb_typeof("before") = 'object'),
    "after" jsonb NOT NULL CHECK (jsonb_typeof("after") = 'object'),
    idempotency_key text,
    cutover_id bigint REFERENCES sokhach.cutover(id),
    CHECK ((kind = 'import') = (cutover_id IS NOT NULL)),
    CONSTRAINT event_snapshot_check CHECK (CASE kind
        WHEN 'paste' THEN "before" = '{}'::jsonb AND "after" ? 'trips'
        WHEN 'receipt' THEN "before" = '{}'::jsonb AND "after" ? 'receipt'
        WHEN 'import' THEN "before" = '{}'::jsonb AND "after" ? 'cutover'
        WHEN 'price_edit' THEN "before" ? 'price' AND "after" ? 'price'
        WHEN 'adjust_trip' THEN "before" ? 'trip' AND "after" ? 'adjustment'
        WHEN 'adjust_month' THEN "before" ? 'month' AND "after" ? 'adjustment'
        WHEN 'receipt_edit' THEN "before" ? 'receipt' AND "after" ? 'receipt'
        WHEN 'month_lock' THEN coalesce("before"->>'month' = "after"->>'month'
            AND jsonb_typeof("before"->'locked')='boolean'
            AND jsonb_typeof("after"->'locked')='boolean',false)
        WHEN 'void' THEN "before" ? 'receipt' AND "after" ? 'receipt'
        WHEN 'reallocation' THEN "before" ? 'allocations' AND "after" ? 'allocations'
        WHEN 'customer_attr' THEN "before" ? 'customer' AND "after" ? 'customer'
        WHEN 'trip_edit' THEN "before" ? 'trip' AND "after" ? 'trip'
        WHEN 'legacy_edit' THEN "before" ? 'legacy' AND "after" ? 'legacy'
        WHEN 'trip_delete' THEN "before" ? 'trip' AND coalesce("after"->'trip'->'deleted'='true'::jsonb,false)
        WHEN 'legacy_delete' THEN "before" ? 'legacy' AND coalesce("after"->'legacy'->'deleted'='true'::jsonb,false)
        WHEN 'trip_review' THEN "before"->>'status' = 'pending_review' AND "after" ? 'trip'
            AND "after"->>'status' IN ('confirmed','rejected') AND btrim(coalesce("after"->>'review_reason','')) <> ''
        WHEN 'sheet_conflict_resolved' THEN "before" ? 'target' AND "before" ? 'field'
            AND "after" ? 'target' AND "after" ? 'field' AND "after" ? 'source_row'
            AND "after" ? 'sheet_value' AND "after" ? 'decision'
        WHEN 'fee_migration' THEN "before" = '{}'::jsonb AND "after" ? 'trip_count' AND "after" ? 'legacy_count'
        WHEN 'add_trip_fees' THEN "before" ? 'targets' AND "after" ? 'targets'
        WHEN 'set_trip_fee_type' THEN "before" ? 'targets' AND "after" ? 'targets'
        WHEN 'replace_trip_fee' THEN "before" ? 'targets' AND "after" ? 'targets'
        WHEN 'void_trip_fee' THEN "before" ? 'targets' AND "after" ? 'targets'
        WHEN 'set_book_fee_columns' THEN "before" ? 'fee_columns' AND "after" ? 'fee_columns'
        ELSE false END),
    UNIQUE (id, customer_id)
);
DO $$ BEGIN ALTER TABLE sokhach.trip_fee_line ADD CONSTRAINT fee_line_created_event_fk FOREIGN KEY(created_by_event,customer_id) REFERENCES sokhach.event(id,customer_id); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN ALTER TABLE sokhach.trip_fee_line ADD CONSTRAINT fee_line_voided_event_fk FOREIGN KEY(voided_by_event,customer_id) REFERENCES sokhach.event(id,customer_id); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
COMMENT ON TABLE sokhach.event IS 'Vết chỉ thêm trước/sau; gồm mở/khóa tháng.';
COMMENT ON COLUMN sokhach.event.actor IS 'Đọc từ current_setting(''sokhach.actor'', false), từ chối rỗng trong hàm lệnh.';
COMMENT ON COLUMN sokhach.event.idempotency_key IS 'Khóa lệnh nguồn, có thể lặp giữa các event của cùng lệnh.';
COMMENT ON COLUMN sokhach.event.cutover_id IS 'Chỉ event import có mốc chuyển; chỉ mục duy nhất chặn nhập lại kể cả khi không có dòng opening.';
COMMENT ON COLUMN sokhach.event."before" IS 'Bắt buộc: tạo mới dùng {}; sửa/hủy/phân bổ lại có snapshot ID và giá trị trước.';
COMMENT ON COLUMN sokhach.event."after" IS 'Bắt buộc theo kind: ID, giá trị sau và bộ phân bổ; CHECK chỉ xác nhận key tối thiểu, hàm phải kiểm nội dung/quan hệ trước commit.';

ALTER TABLE sokhach.trip ADD COLUMN created_by_event bigint NOT NULL;
ALTER TABLE sokhach.trip ADD CONSTRAINT trip_created_event_fk
    FOREIGN KEY (created_by_event, customer_id) REFERENCES sokhach.event(id, customer_id);
ALTER TABLE sokhach.trip ADD CONSTRAINT trip_event_customer_unique UNIQUE (id, customer_id);
DO $$ BEGIN ALTER TABLE sokhach.trip_fee_line ADD CONSTRAINT fee_line_trip_customer_fk FOREIGN KEY(trip_id,customer_id) REFERENCES sokhach.trip(id,customer_id); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
ALTER TABLE sokhach.trip ADD COLUMN reviewed_by_event bigint;
ALTER TABLE sokhach.trip ADD CONSTRAINT trip_review_event_fk
    FOREIGN KEY (reviewed_by_event, customer_id) REFERENCES sokhach.event(id, customer_id);
ALTER TABLE sokhach.trip ADD CONSTRAINT trip_review_state
    CHECK ((status <> 'pending_review' OR reviewed_by_event IS NULL)
       AND (status <> 'rejected' OR reviewed_by_event IS NOT NULL));
COMMENT ON COLUMN sokhach.trip.reviewed_by_event IS 'Event kết luận CHỜ KIỂM (NEWTRIP-01); chỉ đổi một lần từ pending_review sang confirmed/rejected.';
ALTER TABLE sokhach.trip_price_rev ADD COLUMN customer_id bigint NOT NULL;
ALTER TABLE sokhach.trip_price_rev ADD COLUMN created_by_event bigint NOT NULL;
ALTER TABLE sokhach.trip_price_rev ADD CONSTRAINT price_trip_customer_fk
    FOREIGN KEY (trip_id, customer_id) REFERENCES sokhach.trip(id, customer_id);
ALTER TABLE sokhach.trip_price_rev ADD CONSTRAINT price_event_fk
    FOREIGN KEY (created_by_event, customer_id) REFERENCES sokhach.event(id, customer_id);
ALTER TABLE sokhach.adjustment ADD COLUMN created_by_event bigint NOT NULL;
ALTER TABLE sokhach.adjustment ADD CONSTRAINT adjustment_event_fk
    FOREIGN KEY (created_by_event, customer_id) REFERENCES sokhach.event(id, customer_id);
ALTER TABLE sokhach.receipt ADD COLUMN created_by_event bigint NOT NULL;
ALTER TABLE sokhach.receipt ADD CONSTRAINT receipt_event_fk
    FOREIGN KEY (created_by_event, customer_id) REFERENCES sokhach.event(id, customer_id);
ALTER TABLE sokhach.receipt ADD CONSTRAINT receipt_meta_event_fk
    FOREIGN KEY (meta_changed_by_event, customer_id) REFERENCES sokhach.event(id, customer_id);
ALTER TABLE sokhach.receipt ADD CONSTRAINT receipt_void_event_fk
    FOREIGN KEY (voided_by_event, customer_id) REFERENCES sokhach.event(id, customer_id);
COMMENT ON COLUMN sokhach.receipt.created_by_event IS 'Event tạo phiếu; đổi ngày/hình thức/hủy phải có event tương ứng trước khi commit.';

-- V7 NHAP-SHEET-01: immutable identity with append-only information revisions.
CREATE TABLE sokhach.trip_info_rev (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    trip_id bigint NOT NULL,
    customer_id bigint NOT NULL,
    debt_month date NOT NULL CHECK (EXTRACT(DAY FROM debt_month)=1),
    event_date date, container text, carrier text, shipper text, origin text, destination text,
    status text NOT NULL CHECK (status IN ('confirmed','pending_review','rejected')),
    deleted boolean NOT NULL DEFAULT false,
    created_by_event bigint NOT NULL,
    FOREIGN KEY (trip_id,customer_id) REFERENCES sokhach.trip(id,customer_id),
    FOREIGN KEY (created_by_event,customer_id) REFERENCES sokhach.event(id,customer_id)
);
CREATE INDEX trip_info_rev_latest ON sokhach.trip_info_rev(trip_id,id DESC);
CREATE TABLE sokhach.legacy_trip_rev (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    legacy_row_id bigint NOT NULL REFERENCES sokhach.legacy_row(id),
    customer_id bigint NOT NULL,
    debt_month date NOT NULL CHECK (EXTRACT(DAY FROM debt_month)=1),
    event_date date, container text, carrier text, shipper text, origin text, destination text,
    unit_price_vnd bigint CHECK (unit_price_vnd>=0), other_fee_vnd bigint,
    deleted boolean NOT NULL DEFAULT false, counted_vnd bigint NOT NULL,
    created_by_event bigint NOT NULL,
    FOREIGN KEY (created_by_event,customer_id) REFERENCES sokhach.event(id,customer_id)
);
CREATE INDEX legacy_trip_rev_latest ON sokhach.legacy_trip_rev(legacy_row_id,id DESC);
ALTER TABLE sokhach.adjustment ADD COLUMN legacy_row_id bigint REFERENCES sokhach.legacy_row(id);
ALTER TABLE sokhach.adjustment ADD CONSTRAINT adjustment_one_target CHECK (trip_id IS NULL OR legacy_row_id IS NULL);
CREATE OR REPLACE VIEW sokhach.v_trip_current AS
SELECT t.id,t.customer_id,t.debt_month AS origin_month,
       coalesce(r.debt_month,t.debt_month) AS debt_month,
       CASE WHEN r.id IS NULL THEN t.event_date ELSE r.event_date END AS event_date,
       CASE WHEN r.id IS NULL THEN t.container ELSE r.container END AS container, CASE WHEN r.id IS NULL THEN t.carrier ELSE r.carrier END AS carrier,
       CASE WHEN r.id IS NULL THEN t.origin ELSE r.origin END AS origin, CASE WHEN r.id IS NULL THEN t.destination ELSE r.destination END AS destination,
       t.booking AS booking, t.note AS note,
       t.source_ref AS source_ref, coalesce(r.status,t.status) AS status,
       coalesce(r.deleted,false) AS deleted,
       CASE WHEN r.id IS NULL THEN t.shipper ELSE r.shipper END AS shipper
FROM sokhach.trip t LEFT JOIN LATERAL (SELECT * FROM sokhach.trip_info_rev x
  WHERE x.trip_id=t.id AND x.customer_id=t.customer_id ORDER BY x.id DESC LIMIT 1) r ON true;

ALTER TABLE sokhach.opening_balance ADD COLUMN created_by_event bigint NOT NULL;
ALTER TABLE sokhach.opening_balance ADD CONSTRAINT opening_event_fk
    FOREIGN KEY (created_by_event, customer_id) REFERENCES sokhach.event(id, customer_id);
ALTER TABLE sokhach.legacy_row ADD COLUMN created_by_event bigint NOT NULL;
ALTER TABLE sokhach.legacy_row ADD CONSTRAINT legacy_row_customer_unique UNIQUE(id,customer_id);
DO $$ BEGIN ALTER TABLE sokhach.trip_fee_line ADD CONSTRAINT fee_line_legacy_customer_fk FOREIGN KEY(legacy_row_id,customer_id) REFERENCES sokhach.legacy_row(id,customer_id); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
ALTER TABLE sokhach.legacy_row ADD CONSTRAINT legacy_event_fk
    FOREIGN KEY (created_by_event, customer_id) REFERENCES sokhach.event(id, customer_id);
-- Hàm import kiểm event.kind = import và event.cutover_id trùng cutover của dòng.

CREATE TABLE sokhach.receipt_line (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    receipt_id bigint NOT NULL,
    customer_id bigint NOT NULL,
    debt_month date NOT NULL CHECK (EXTRACT(DAY FROM debt_month) = 1),
    kind text NOT NULL CHECK (kind IN ('debt', 'advance')),
    amount_vnd bigint NOT NULL CHECK (amount_vnd > 0),
    created_by_event bigint NOT NULL,
    superseded_by_event bigint,
    FOREIGN KEY (receipt_id, customer_id) REFERENCES sokhach.receipt(id, customer_id),
    FOREIGN KEY (created_by_event, customer_id) REFERENCES sokhach.event(id, customer_id),
    FOREIGN KEY (superseded_by_event, customer_id) REFERENCES sokhach.event(id, customer_id)
);
COMMENT ON TABLE sokhach.receipt_line IS 'Phân bổ có phiên bản; hủy phiếu giữ dòng để xem lịch sử.';
COMMENT ON COLUMN sokhach.receipt_line.debt_month IS 'Tháng được phân bổ; không suy từ ngày phiếu.';
COMMENT ON COLUMN sokhach.receipt_line.kind IS 'advance là phần dư ở tháng cuối, vẫn nằm trong sổ khách.';
COMMENT ON COLUMN sokhach.receipt_line.created_by_event IS 'Sự kiện tạo phiên bản phân bổ này.';
COMMENT ON COLUMN sokhach.receipt_line.superseded_by_event IS 'NULL là phiên bản phân bổ hiện hành; reallocation hoặc void đóng dòng cũ.';
-- HỢP ĐỒNG BẮT BUỘC sau MỌI lệnh đổi phân bổ, trước commit cùng giao dịch:
-- khóa customer; mỗi receipt sống có đúng một bộ dòng hiện hành, SUM(amount_vnd)
-- = receipt.amount_vnd; advance chỉ ở tháng cuối; receipt hủy không có dòng hiện hành.
-- void_receipt phải đặt superseded_by_event = event void cho TỪNG dòng gốc
-- đang hiệu lực (mọi tháng) trước commit; view loại phiếu hủy không thay kiểm này.
-- created_by_event/superseded_by_event phải cùng khách, đúng phiếu trong snapshot,
-- đúng kind (receipt/reallocation/void), và mọi dòng của bộ cũ phải đóng bằng
-- CÙNG event. So snapshot (debt_month, kind, amount_vnd) từng phiếu, không chỉ tháng.
-- Hàm kiểm đa hàng có trong tools/v7_backend_functions.sql; FK/CHECK từng hàng không đủ.

CREATE TABLE sokhach.idempotency (
    customer_id bigint NOT NULL REFERENCES sokhach.customer(id),
    key text NOT NULL CHECK (btrim(key) <> ''),
    request_hash text NOT NULL CHECK (request_hash ~ '^[0-9a-f]{64}$'),
    result jsonb NOT NULL,
    PRIMARY KEY (customer_id, key)
);
COMMENT ON TABLE sokhach.idempotency IS 'Cùng khách và khóa: cùng băm trả kết quả cũ, khác băm bị từ chối.';
COMMENT ON COLUMN sokhach.idempotency.request_hash IS 'SHA-256 của yêu cầu chuẩn hóa do hàm lệnh xác định.';
COMMENT ON COLUMN sokhach.idempotency.result IS 'Kết quả tính sẵn để trả lại khi lặp lệnh.';

-- CT-2SO: source entry is separate from positive receipts and trip charges.
CREATE TABLE sokhach.offset_pair (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source_customer_id bigint NOT NULL REFERENCES sokhach.customer(id),
    target_customer_id bigint NOT NULL REFERENCES sokhach.customer(id),
    target_receipt_id bigint NOT NULL UNIQUE,
    source_pid text NOT NULL,
    date date NOT NULL,
    amount_vnd bigint NOT NULL CHECK (amount_vnd > 0),
    created_by_event bigint NOT NULL,
    changed_by_event bigint,
    voided_by_event bigint,
    void_reason text CHECK (btrim(void_reason) <> ''),
    CHECK (source_customer_id <> target_customer_id),
    CHECK ((void_reason IS NULL) = (voided_by_event IS NULL)),
    UNIQUE (source_customer_id, source_pid),
    FOREIGN KEY (target_receipt_id, target_customer_id) REFERENCES sokhach.receipt(id, customer_id),
    FOREIGN KEY (created_by_event, source_customer_id) REFERENCES sokhach.event(id, customer_id),
    FOREIGN KEY (changed_by_event, source_customer_id) REFERENCES sokhach.event(id, customer_id),
    FOREIGN KEY (voided_by_event, source_customer_id) REFERENCES sokhach.event(id, customer_id)
);
CREATE TABLE sokhach.offset_command (
    low_customer_id bigint NOT NULL REFERENCES sokhach.customer(id),
    high_customer_id bigint NOT NULL REFERENCES sokhach.customer(id),
    key text NOT NULL CHECK (btrim(key) <> ''),
    payload jsonb NOT NULL,
    result jsonb NOT NULL,
    CHECK (low_customer_id < high_customer_id),
    PRIMARY KEY (low_customer_id, high_customer_id, key)
);
CREATE VIEW sokhach.v_offset_outgoing AS
SELECT id, source_customer_id AS customer_id, date_trunc('month',date)::date AS debt_month,
       amount_vnd FROM sokhach.offset_pair WHERE voided_by_event IS NULL;

CREATE FUNCTION sokhach.reject_immutable_change() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog, sokhach, pg_temp AS $$
BEGIN
    RAISE EXCEPTION 'immutable row: %.%', TG_TABLE_SCHEMA, TG_TABLE_NAME;
END $$;
CREATE TRIGGER baseline_trip_ref_immutable BEFORE UPDATE OR DELETE ON sokhach.baseline_trip_ref
    FOR EACH ROW EXECUTE FUNCTION sokhach.reject_immutable_change();
CREATE TRIGGER event_immutable BEFORE UPDATE OR DELETE ON sokhach.event
    FOR EACH ROW EXECUTE FUNCTION sokhach.reject_immutable_change();
-- Chuyến chỉ thêm; ngoại lệ duy nhất là kết luận CHỜ KIỂM một lần (NEWTRIP-01).
CREATE FUNCTION sokhach.guard_trip_change() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog, sokhach, pg_temp AS $$
BEGIN
    IF TG_OP = 'UPDATE' AND OLD.status = 'pending_review' AND OLD.reviewed_by_event IS NULL
       AND NEW.status IN ('confirmed', 'rejected') AND NEW.reviewed_by_event IS NOT NULL
       AND to_jsonb(OLD) - 'status' - 'reviewed_by_event' = to_jsonb(NEW) - 'status' - 'reviewed_by_event' THEN
        RETURN NEW;
    END IF;
    RAISE EXCEPTION 'immutable row: %.%', TG_TABLE_SCHEMA, TG_TABLE_NAME;
END $$;
DROP TRIGGER IF EXISTS trip_info_rev_immutable ON sokhach.trip_info_rev;
CREATE TRIGGER trip_info_rev_immutable BEFORE UPDATE OR DELETE ON sokhach.trip_info_rev FOR EACH ROW EXECUTE FUNCTION sokhach.reject_immutable_change();
DROP TRIGGER IF EXISTS legacy_trip_rev_immutable ON sokhach.legacy_trip_rev;
CREATE TRIGGER legacy_trip_rev_immutable BEFORE UPDATE OR DELETE ON sokhach.legacy_trip_rev FOR EACH ROW EXECUTE FUNCTION sokhach.reject_immutable_change();
CREATE TRIGGER trip_immutable BEFORE UPDATE OR DELETE ON sokhach.trip
    FOR EACH ROW EXECUTE FUNCTION sokhach.reject_immutable_change();
CREATE TRIGGER trip_price_rev_immutable BEFORE UPDATE OR DELETE ON sokhach.trip_price_rev
    FOR EACH ROW EXECUTE FUNCTION sokhach.reject_immutable_change();
CREATE TRIGGER adjustment_immutable BEFORE UPDATE OR DELETE ON sokhach.adjustment
    FOR EACH ROW EXECUTE FUNCTION sokhach.reject_immutable_change();
CREATE TRIGGER idempotency_immutable BEFORE UPDATE OR DELETE ON sokhach.idempotency
    FOR EACH ROW EXECUTE FUNCTION sokhach.reject_immutable_change();
CREATE TRIGGER offset_command_immutable BEFORE UPDATE OR DELETE ON sokhach.offset_command
    FOR EACH ROW EXECUTE FUNCTION sokhach.reject_immutable_change();
CREATE FUNCTION sokhach.guard_offset_pair() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog, sokhach, pg_temp AS $$
BEGIN
    IF TG_OP='DELETE' THEN RAISE EXCEPTION 'OFFSET_PAIR_IMMUTABLE'; END IF;
    IF ROW(NEW.id,NEW.source_customer_id,NEW.target_customer_id,NEW.target_receipt_id,
        NEW.source_pid,NEW.amount_vnd,NEW.created_by_event)
       IS DISTINCT FROM ROW(OLD.id,OLD.source_customer_id,OLD.target_customer_id,OLD.target_receipt_id,
        OLD.source_pid,OLD.amount_vnd,OLD.created_by_event)
       OR OLD.voided_by_event IS NOT NULL
    THEN RAISE EXCEPTION 'OFFSET_PAIR_IMMUTABLE'; END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER offset_pair_guard BEFORE UPDATE OR DELETE ON sokhach.offset_pair
    FOR EACH ROW EXECUTE FUNCTION sokhach.guard_offset_pair();
-- Enforce shared PH namespace even for privileged fixture inserts; normal commands
-- already hold the same customer lock before choosing the next code.
CREATE FUNCTION sokhach.check_offset_pid() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog, sokhach, pg_temp AS $$
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
END $$;
CREATE TRIGGER receipt_offset_pid BEFORE INSERT ON sokhach.receipt
    FOR EACH ROW EXECUTE FUNCTION sokhach.check_offset_pid();
CREATE TRIGGER offset_pair_pid BEFORE INSERT ON sokhach.offset_pair
    FOR EACH ROW EXECUTE FUNCTION sokhach.check_offset_pid();

CREATE FUNCTION sokhach.check_offset_pair() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog, sokhach, pg_temp AS $$
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
END $$;
CREATE CONSTRAINT TRIGGER offset_pair_consistency_trigger AFTER INSERT OR UPDATE ON sokhach.offset_pair
    DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION sokhach.check_offset_pair();
CREATE CONSTRAINT TRIGGER receipt_offset_pair_check AFTER INSERT OR UPDATE ON sokhach.receipt
    DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION sokhach.check_offset_pair();

CREATE FUNCTION sokhach.guard_cutover_status() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog, sokhach, pg_temp AS $$
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
END $$;
CREATE TRIGGER cutover_status_guard BEFORE INSERT OR UPDATE OR DELETE ON sokhach.cutover
    FOR EACH ROW EXECUTE FUNCTION sokhach.guard_cutover_status();
CREATE FUNCTION sokhach.guard_cutover_customer_status() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog, sokhach, pg_temp AS $$
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
END $$;
CREATE TRIGGER cutover_customer_status_guard BEFORE INSERT OR UPDATE OR DELETE ON sokhach.cutover_customer
    FOR EACH ROW EXECUTE FUNCTION sokhach.guard_cutover_customer_status();
CREATE FUNCTION sokhach.guard_cutover_evidence() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog, sokhach, pg_temp AS $$
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
END $$;
CREATE TRIGGER cutover_month_check_guard BEFORE INSERT OR UPDATE OR DELETE ON sokhach.cutover_month_check
    FOR EACH ROW EXECUTE FUNCTION sokhach.guard_cutover_evidence();
CREATE TRIGGER opening_balance_insert_guard BEFORE INSERT ON sokhach.opening_balance
    FOR EACH ROW EXECUTE FUNCTION sokhach.guard_cutover_evidence();
CREATE TRIGGER legacy_row_insert_guard BEFORE INSERT ON sokhach.legacy_row
    FOR EACH ROW EXECUTE FUNCTION sokhach.guard_cutover_evidence();
CREATE TRIGGER opening_balance_immutable BEFORE UPDATE OR DELETE ON sokhach.opening_balance
    FOR EACH ROW EXECUTE FUNCTION sokhach.reject_immutable_change();
CREATE TRIGGER legacy_row_immutable BEFORE UPDATE OR DELETE ON sokhach.legacy_row
    FOR EACH ROW EXECUTE FUNCTION sokhach.reject_immutable_change();

CREATE FUNCTION sokhach.guard_receipt_change() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog, sokhach, pg_temp AS $$
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
END $$;
CREATE TRIGGER receipt_guard BEFORE UPDATE OR DELETE ON sokhach.receipt
    FOR EACH ROW EXECUTE FUNCTION sokhach.guard_receipt_change();

CREATE FUNCTION sokhach.guard_receipt_line_change() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog, sokhach, pg_temp AS $$
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
END $$;
CREATE TRIGGER receipt_line_guard BEFORE UPDATE OR DELETE ON sokhach.receipt_line
    FOR EACH ROW EXECUTE FUNCTION sokhach.guard_receipt_line_change();

CREATE INDEX trip_customer_month ON sokhach.trip (customer_id, debt_month, id);
CREATE INDEX adjustment_customer_month ON sokhach.adjustment (customer_id, debt_month, id);
CREATE INDEX receipt_customer_fifo ON sokhach.receipt (customer_id, date, pid)
    WHERE voided_on IS NULL;
CREATE INDEX receipt_line_active_month ON sokhach.receipt_line (customer_id, debt_month, receipt_id)
    WHERE superseded_by_event IS NULL;
CREATE INDEX receipt_line_active_receipt ON sokhach.receipt_line (receipt_id)
    WHERE superseded_by_event IS NULL;
CREATE INDEX event_customer_recent ON sokhach.event (customer_id, at DESC, id DESC);
CREATE INDEX trip_price_rev_latest ON sokhach.trip_price_rev (trip_id, id DESC);
CREATE UNIQUE INDEX event_import_once ON sokhach.event (customer_id, cutover_id)
    WHERE kind = 'import';
CREATE UNIQUE INDEX event_one_cutover_per_customer ON sokhach.event (customer_id)
    WHERE kind = 'import';
CREATE INDEX opening_balance_customer_month ON sokhach.opening_balance (customer_id, debt_month);
CREATE INDEX legacy_row_customer_month ON sokhach.legacy_row (customer_id, debt_month, id);

-- Hàm lệnh khóa customer trước, SAU ĐÓ đọc clock_timestamp() một lần để kiểm;
-- dùng COALESCE(month_state.locked,
--   month <> date_trunc('month', clock_timestamp()
--       AT TIME ZONE 'Asia/Ho_Chi_Minh')::date); không dùng transaction_timestamp().
-- tháng không có hàng tự đổi mặc định khi sang tháng mới.

CREATE VIEW sokhach.v_receipt_line_active AS
SELECT l.id, l.receipt_id, l.customer_id, l.debt_month, l.kind,
       l.amount_vnd, l.created_by_event, r.pid, r.date, r.method
FROM sokhach.receipt_line AS l
JOIN sokhach.receipt AS r ON (r.id, r.customer_id) = (l.receipt_id, l.customer_id)
WHERE l.superseded_by_event IS NULL AND r.voided_on IS NULL;
COMMENT ON VIEW sokhach.v_receipt_line_active IS 'Dòng hiệu lực của phiếu chưa hủy; không cộng dòng cũ hoặc phiếu hủy.';

CREATE VIEW sokhach.v_outstanding_month AS
WITH active_customer AS (
    SELECT cc.customer_id, cc.cutover_id
    FROM sokhach.cutover_customer AS cc
    JOIN sokhach.cutover AS c ON c.id = cc.cutover_id
    WHERE cc.status = 'active' AND c.status = 'active'
), latest_price AS (
    SELECT t.customer_id, t.debt_month,
           CASE WHEN p.unit_price_vnd IS NOT NULL
                 THEN p.unit_price_vnd + COALESCE(p.other_fee_vnd, 0) -- ĐÃ CHỐT 20/10/2026; khớp tripAmount
                 WHEN (t.container IS NULL OR t.container = '')
                     AND p.other_fee_vnd IS NOT NULL THEN p.other_fee_vnd
                ELSE NULL END AS amount_vnd
    FROM sokhach.trip AS t
    JOIN active_customer AS ac ON ac.customer_id = t.customer_id
    LEFT JOIN LATERAL (
        SELECT unit_price_vnd, other_fee_vnd
        FROM sokhach.trip_price_rev
        WHERE trip_id = t.id
        ORDER BY id DESC LIMIT 1
    ) AS p ON true
), movements AS (
    SELECT o.customer_id, o.debt_month, o.amount_vnd
    FROM sokhach.opening_balance AS o
    JOIN active_customer AS ac
      ON (ac.customer_id, ac.cutover_id) = (o.customer_id, o.cutover_id)
    UNION ALL
    SELECT customer_id, debt_month, amount_vnd FROM latest_price WHERE amount_vnd IS NOT NULL
    UNION ALL
    SELECT a.customer_id, a.debt_month, a.amount_vnd
    FROM sokhach.adjustment AS a
    JOIN active_customer AS ac ON ac.customer_id = a.customer_id
    UNION ALL
    SELECT l.customer_id, l.debt_month, -l.amount_vnd
    FROM sokhach.v_receipt_line_active AS l
    JOIN active_customer AS ac ON ac.customer_id = l.customer_id
)
SELECT customer_id, debt_month, SUM(amount_vnd)::bigint AS outstanding_vnd
FROM movements
GROUP BY customer_id, debt_month;
COMMENT ON VIEW sokhach.v_outstanding_month IS 'Chỉ khách và cutover active tham gia mọi vế tiền; draft/verified không hiệu lực. Lệnh ghi còn phải chặn NO_BASELINE dưới khóa khách. legacy_row không tham gia.';

CREATE VIEW sokhach.v_month_chain AS
SELECT customer_id, debt_month, outstanding_vnd,
       (SUM(outstanding_vnd) OVER (
           PARTITION BY customer_id ORDER BY debt_month
           ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
       ))::bigint AS end_of_month_vnd
FROM sokhach.v_outstanding_month;
COMMENT ON VIEW sokhach.v_month_chain IS 'Chuỗi cộng dồn tháng cho get_ledger; chỉ cộng v_outstanding_month, không cộng legacy_row lần hai.';

REVOKE ALL ON ALL TABLES IN SCHEMA sokhach FROM PUBLIC, sokhach_app, sokhach_reader;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA sokhach FROM PUBLIC, sokhach_app, sokhach_reader;
CREATE OR REPLACE FUNCTION sokhach.delete_trip(customer_id bigint,expected_version bigint,idempotency_key text,trip_id bigint) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,sokhach,pg_temp AS $$
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
END $$;

REVOKE ALL ON ALL FUNCTIONS IN SCHEMA sokhach FROM PUBLIC, sokhach_app, sokhach_reader;
-- Migration tương lai: tất cả object thuộc sokhach_owner; SET ROLE sokhach_owner
-- trước CREATE để default privilege áp dụng đúng role tạo hàm. Không GRANT SELECT
-- bảng/view toàn khách cho app hoặc reader. Chỉ GRANT EXECUTE từng hàm sau review.
ALTER DEFAULT PRIVILEGES FOR ROLE sokhach_owner REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC;
ALTER DEFAULT PRIVILEGES FOR ROLE sokhach_owner IN SCHEMA sokhach REVOKE ALL ON TABLES FROM PUBLIC;
ALTER DEFAULT PRIVILEGES FOR ROLE sokhach_owner IN SCHEMA sokhach REVOKE ALL ON SEQUENCES FROM PUBLIC;
GRANT USAGE ON SCHEMA sokhach TO sokhach_app, sokhach_reader;
RESET ROLE;
-- Bản thử ai vào app cũng thao tác; allowlist EXECUTE ở cuối tools/v7_backend_functions.sql.
-- Từng hàm lệnh tương lai: SECURITY DEFINER SET search_path = pg_catalog, sokhach, pg_temp;
-- object đủ schema, actor chỉ do app server đặt qua SET LOCAL trên kết nối riêng.
-- PostgreSQL không xác minh custom setting; client không được kết nối DB/SQL tùy ý.
-- Lệnh theo mốc khóa cutover trước customer; lệnh khác khóa customer.
-- Sau khóa khách tra idempotency trước expected_version; cùng key/hash
-- trả kết quả lưu kể cả version cũ, khác hash báo IDEMPOTENCY_CONFLICT;
-- chỉ lệnh mới được kiểm STALE_LEDGER.
-- Mỗi lệnh ghi trả jsonb gồm version mới và kết quả server tính.
-- FUNCTION sokhach.paste_trips(customer_id bigint, expected_version bigint, idempotency_key text, debt_month date, trips jsonb) RETURNS jsonb
-- FUNCTION sokhach.edit_trip_price(customer_id bigint, expected_version bigint, idempotency_key text, trip_id bigint, unit_price_vnd bigint, other_fee_vnd bigint) RETURNS jsonb
-- FUNCTION sokhach.adjust_trip(customer_id bigint, expected_version bigint, idempotency_key text, trip_id bigint, new_amount_vnd bigint, note text) RETURNS jsonb
-- FUNCTION sokhach.adjust_month(customer_id bigint, expected_version bigint, idempotency_key text, debt_month date, amount_vnd bigint, note text) RETURNS jsonb
-- FUNCTION sokhach.record_receipt(customer_id bigint, expected_version bigint, idempotency_key text, date date, method text, amount_vnd bigint, reference text DEFAULT NULL) RETURNS jsonb
-- FUNCTION sokhach.edit_receipt_meta(customer_id bigint, expected_version bigint, idempotency_key text, pid text, date date, method text, reference text DEFAULT NULL) RETURNS jsonb
-- FUNCTION sokhach.void_receipt(customer_id bigint, expected_version bigint, idempotency_key text, pid text, reason text) RETURNS jsonb
-- FUNCTION sokhach.set_month_lock(customer_id bigint, expected_version bigint, idempotency_key text, month date, locked boolean) RETURNS jsonb
-- FUNCTION sokhach.set_customer_attributes(customer_id bigint, expected_version bigint, idempotency_key text, commodity_id bigint, transport_mode text, archived boolean) RETURNS jsonb
--   ĐỀ XUẤT 20/10: gán/đổi mặt hàng, phương thức vận chuyển, cờ archive; tăng version. archived=true bị từ chối nếu khách có số dư mở khác 0. Ghi event customer_attr (before/after: commodity_id, transport_mode, archived) để giữ vết người làm. paste_trips/record_receipt vào khách archived: từ chối (ĐỀ XUẤT, CÒN MỞ).
-- FUNCTION sokhach.get_ledger(customer_id bigint) RETURNS jsonb
--   Chỉ đọc; trả version. Không có expected_version/idempotency_key. Khi chưa active
--   trả NO_BASELINE, không hiển thị draft như số dư hiệu lực.
-- FUNCTION sokhach.import_cutover(customer_id bigint, expected_version bigint, idempotency_key text, cutover_id bigint, openings jsonb, legacy jsonb, month_checks jsonb, expected_control_total bigint, report_sha256 text) RETURNS jsonb
--   Một giao dịch: khóa cutover trước, rồi customer; tra idempotency trước version,
--   kiểm actor, nguồn/JSON; không giữ khóa customer rồi mới chờ cutover.
--   import nháp bị chặn nếu có trip/adjustment/receipt/event tiền sống. Một khách
--   chỉ một mốc. Lần nhập mới cùng khách/mốc bị từ chối; retry đúng
--   cùng key/payload trả kết quả lưu. SUM(openings.amount_vnd) phải khớp tổng
--   khách đến từng đồng; verify sau đó so từng bucket chuẩn theo tháng,
--   có tham chiếu/hash mỏ neo đầu, phát sinh, thu và mỏ neo cuối; không chỉ tổng khách.
--   Tạo event import với cutover_id; UNIQUE event_import_once từ chối lần nhập thứ hai
--   của cùng (khách, mốc), kể cả lô rỗng. Opening draft không vào view tiền;
--   legacy_row chỉ để đọc. Cờ ngoại lệ giữ nguyên; kiểm tổng toàn mốc riêng.
--   ĐỀ XUẤT: sau đối soát cơ học từng tháng/khách/toàn mốc, gọi
--   verify_cutover_customer cho mọi khách, verify_cutover, activate_cutover,
--   activate_cutover_customer cho từng khách. Mọi lệnh/trigger liên quan mốc
--   khóa cutover trước customer (nhiều khách: ID tăng dần);
--   không cần ký nhận; signoff_ref là tham số cũ, không dùng cho gate.
-- FUNCTION sokhach.verify_cutover_customer(customer_id bigint, cutover_id bigint, expected_version bigint, idempotency_key text, signoff_ref text) RETURNS jsonb
-- FUNCTION sokhach.verify_cutover(cutover_id bigint, idempotency_key text, signoff_ref text) RETURNS jsonb
-- FUNCTION sokhach.activate_cutover(cutover_id bigint, idempotency_key text, signoff_ref text) RETURNS jsonb
-- FUNCTION sokhach.activate_cutover_customer(customer_id bigint, cutover_id bigint, expected_version bigint, idempotency_key text, signoff_ref text) RETURNS jsonb
-- Thân hàm nháp đã có; idempotency toàn mốc dùng namespace tạm theo khách nhỏ nhất.
-- App/reader chỉ có EXECUTE theo allowlist cuối tools/v7_backend_functions.sql.

-- Thân hàm lệnh (kể cả import_cutover), reallocate, get_ledger và harness fixture
-- có trong tools/v7_backend_functions.sql, tools/test_pg_v7_backend.py; chỉ dữ liệu giả.
-- Chưa kiểm nguồn thật hay vận hành.
-- Điều cần review:
-- 1. Tên cột/kiểu trả jsonb/chữ ký nghiệp vụ chưa được thiết kế chốt chi tiết.
-- 2. Trạng thái khóa khi thiếu hàng đã cài theo giờ VN trong hàm nháp; chưa kiểm live.
-- 3. Dòng phí lẻ không container/đơn giá có phụ phí được event_date NULL;
--    chuyến thường thiếu ngày bị từ chối.
-- 4. Dạng băm yêu cầu chuẩn hóa, cách cấp pid/ID, giới hạn kích thước tiền/tổng,
--    và kiểm nội dung event/snapshot cần review trước khi triển khai.
-- 5. SET LOCAL sokhach.actor là giá trị app chuyển xuống; DB không tự xác minh Tailscale;
--    bản thử không ACL theo người; ranh giới phiên HTTP chưa nghiệm thu.
-- 6. Phân rã mỏ neo cuối tháng thành bucket theo từng tháng, tránh nhập tổng cộng dồn
--    nhiều lần; bản thử 20/10 bỏ qua bucket âm khi phân bổ thu mới.
-- 7. Một khách nhiều tab, thu trong khối cũ, hình thức thu, giờ đóng băng,
--    trạng thái mốc, cột display từng loại và cách hiển thị lịch sử vẫn CÒN MỞ.
-- 8. UNIQUE nguồn (mốc, tab, dòng) giả định một dòng nguồn thuộc tối đa một legacy_row;
--    cần review với bộ phân tích nguồn. Import cần kiểm mốc/customer/source và
--    tổng theo khách; unique event chặn lặp; thân hàm nháp có trong tools,
--    chưa đối soát nguồn thật hay duyệt logic tài chính.
-- 9. Tạm chặn khách nhập ở mốc thứ hai để view không cộng hai opening; quy trình
--    chuyển lại/sửa sai và chọn mốc hiệu lực phải được quyết trước khi bỏ chỉ mục này.

SET ROLE sokhach_owner;
CREATE OR REPLACE FUNCTION sokhach._fee_lines(p_trip bigint,p_legacy bigint) RETURNS jsonb
LANGUAGE sql STABLE SET search_path=pg_catalog,sokhach,pg_temp AS $$
 SELECT coalesce(jsonb_agg(jsonb_build_object('id',id,'fee_type_id',fee_type_id,
   'amount_vnd',amount_vnd::text,'note',note) ORDER BY id),'[]'::jsonb)
 FROM sokhach.trip_fee_line WHERE voided_by_event IS NULL
   AND (trip_id=p_trip OR legacy_row_id=p_legacy)
$$;

CREATE OR REPLACE FUNCTION sokhach._fee_target(p_customer bigint,p_target jsonb) RETURNS jsonb
LANGUAGE plpgsql SET search_path=pg_catalog,sokhach,pg_temp AS $$
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
END $$;

CREATE OR REPLACE FUNCTION sokhach._change_trip_fees(p_customer bigint,p_version bigint,p_key text,
 p_command text,p_targets jsonb,p_type bigint,p_amount bigint,p_note text,p_line bigint) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,sokhach,pg_temp AS $$
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
END $$;

CREATE OR REPLACE FUNCTION sokhach.add_trip_fees(customer_id bigint,expected_version bigint,idempotency_key text,
 targets jsonb,fee_type_id bigint,amount_vnd bigint,note text) RETURNS jsonb
LANGUAGE sql SECURITY DEFINER SET search_path=pg_catalog,sokhach,pg_temp AS $$
 SELECT sokhach._change_trip_fees(customer_id,expected_version,idempotency_key,'add_trip_fees',targets,fee_type_id,amount_vnd,note,NULL)
$$;

CREATE OR REPLACE FUNCTION sokhach.set_trip_fee_type(customer_id bigint,expected_version bigint,idempotency_key text,
 target jsonb,fee_type_id bigint,amount_vnd bigint) RETURNS jsonb
LANGUAGE sql SECURITY DEFINER SET search_path=pg_catalog,sokhach,pg_temp AS $$
 SELECT sokhach._change_trip_fees(customer_id,expected_version,idempotency_key,'set_trip_fee_type',jsonb_build_array(target),fee_type_id,amount_vnd,NULL,NULL)
$$;

CREATE OR REPLACE FUNCTION sokhach.replace_trip_fee(customer_id bigint,expected_version bigint,idempotency_key text,
 fee_line_id bigint,fee_type_id bigint,amount_vnd bigint,note text) RETURNS jsonb
LANGUAGE sql SECURITY DEFINER SET search_path=pg_catalog,sokhach,pg_temp AS $$
 SELECT sokhach._change_trip_fees(customer_id,expected_version,idempotency_key,'replace_trip_fee',NULL,fee_type_id,amount_vnd,note,fee_line_id)
$$;

CREATE OR REPLACE FUNCTION sokhach.void_trip_fee(customer_id bigint,expected_version bigint,idempotency_key text,
 fee_line_id bigint) RETURNS jsonb
LANGUAGE sql SECURITY DEFINER SET search_path=pg_catalog,sokhach,pg_temp AS $$
 SELECT sokhach._change_trip_fees(customer_id,expected_version,idempotency_key,'void_trip_fee',NULL,NULL,NULL,NULL,fee_line_id)
$$;

CREATE OR REPLACE FUNCTION sokhach._change_fee_type(p_key text,p_command text,p_id bigint,p_value text,p_kind text) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,sokhach,pg_temp AS $$
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
END $$;

CREATE OR REPLACE FUNCTION sokhach.add_fee_type(idempotency_key text,name text,kind text) RETURNS jsonb
LANGUAGE sql SECURITY DEFINER SET search_path=pg_catalog,sokhach,pg_temp AS $$
 SELECT sokhach._change_fee_type(idempotency_key,'add_fee_type',NULL,name,kind)
$$;

CREATE OR REPLACE FUNCTION sokhach.rename_fee_type(idempotency_key text,fee_type_id bigint,name text) RETURNS jsonb
LANGUAGE sql SECURITY DEFINER SET search_path=pg_catalog,sokhach,pg_temp AS $$
 SELECT sokhach._change_fee_type(idempotency_key,'rename_fee_type',fee_type_id,name,NULL)
$$;

CREATE OR REPLACE FUNCTION sokhach.set_fee_type_kind(idempotency_key text,fee_type_id bigint,kind text) RETURNS jsonb
LANGUAGE sql SECURITY DEFINER SET search_path=pg_catalog,sokhach,pg_temp AS $$
 SELECT sokhach._change_fee_type(idempotency_key,'set_fee_type_kind',fee_type_id,NULL,kind)
$$;

CREATE OR REPLACE FUNCTION sokhach.set_fee_type_active(idempotency_key text,fee_type_id bigint,active boolean) RETURNS jsonb
LANGUAGE sql SECURITY DEFINER SET search_path=pg_catalog,sokhach,pg_temp AS $$
 SELECT sokhach._change_fee_type(idempotency_key,'set_fee_type_active',fee_type_id,active::text,NULL)
$$;

CREATE OR REPLACE FUNCTION sokhach.get_fee_types() RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,sokhach,pg_temp AS $$
BEGIN
 PERFORM sokhach._actor();
 RETURN jsonb_build_object('fee_types',(SELECT coalesce(jsonb_agg(to_jsonb(f)-'name_key' ORDER BY sort,id),'[]') FROM sokhach.fee_type f));
END $$;

CREATE OR REPLACE FUNCTION sokhach.set_book_fee_columns(customer_id bigint,expected_version bigint,idempotency_key text,
 fee_type_ids jsonb) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,sokhach,pg_temp AS $$
DECLARE v_payload jsonb:=jsonb_build_object('command','set_book_fee_columns','fee_type_ids',fee_type_ids);
 v_retry jsonb; v_before jsonb; v_type jsonb; v_seen bigint[]:='{}';
BEGIN
 BEGIN v_retry:=sokhach._begin_command(customer_id,expected_version,idempotency_key,v_payload);
 EXCEPTION WHEN raise_exception THEN
   IF SQLERRM='STALE_LEDGER' THEN RAISE EXCEPTION 'VERSION_CONFLICT'; ELSE RAISE; END IF;
 END;
 IF v_retry IS NOT NULL THEN RETURN v_retry; END IF;
 IF jsonb_typeof(fee_type_ids) IS DISTINCT FROM 'array' THEN RAISE EXCEPTION 'INVALID_COMMAND'; END IF;
 IF jsonb_array_length(fee_type_ids)>3 THEN RAISE EXCEPTION 'FEE_COLUMNS_MAX'; END IF;
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
END $$;

CREATE OR REPLACE FUNCTION sokhach._change_legacy(customer_id bigint,expected_version bigint,idempotency_key text,
    legacy_row_id bigint,field text,value text,p_delete boolean,p_fee_event bigint) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,sokhach,pg_temp AS $$
DECLARE v_payload jsonb:=jsonb_build_object('command',CASE WHEN p_delete THEN 'delete_legacy_trip' ELSE 'edit_legacy_trip' END,
      'legacy_row_id',legacy_row_id,'field',field,'value',value);
    v_retry jsonb; l sokhach.legacy_row%ROWTYPE; v_old jsonb; v_new jsonb; v_value text;
    v_month date; v_old_month date; v_count bigint; v_old_count bigint; v_event bigint; v_changes jsonb;
    v_fee bigint;
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
    PERFORM sokhach._month_open(customer_id,v_old_month,clock_timestamp());
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
    IF p_fee_event IS NULL THEN
    INSERT INTO sokhach.event(customer_id,kind,actor,"before","after",idempotency_key)
      VALUES(customer_id,CASE WHEN p_delete THEN 'legacy_delete' ELSE 'legacy_edit' END,sokhach._actor(),
        jsonb_build_object('legacy',v_old||jsonb_build_object('field',field,'value',v_old->field)),jsonb_build_object('legacy',v_new),idempotency_key) RETURNING id INTO v_event;
    ELSE v_event:=p_fee_event; END IF;
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
    RETURN sokhach._finish_command(customer_id,idempotency_key,v_payload,jsonb_build_object('legacy_row_id',l.id,'deleted',p_delete,'reallocated',v_changes));
EXCEPTION WHEN numeric_value_out_of_range THEN
    IF p_fee_event IS NOT NULL THEN RAISE EXCEPTION 'FEE_AMOUNT_INVALID'; END IF;
    RAISE EXCEPTION 'INVALID_VND';
END $$;

CREATE OR REPLACE FUNCTION sokhach._change_legacy(customer_id bigint,expected_version bigint,idempotency_key text,
    legacy_row_id bigint,field text,value text,p_delete boolean) RETURNS jsonb
LANGUAGE sql SECURITY DEFINER SET search_path=pg_catalog,sokhach,pg_temp AS $$
 SELECT sokhach._change_legacy(customer_id,expected_version,idempotency_key,legacy_row_id,field,value,p_delete,NULL)
$$;

CREATE OR REPLACE FUNCTION sokhach._guard_fee_line() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog,sokhach,pg_temp AS $$
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
END $$;

CREATE OR REPLACE FUNCTION sokhach._fee_columns(p_customer bigint) RETURNS jsonb
LANGUAGE sql STABLE SET search_path=pg_catalog,sokhach,pg_temp AS $$
 SELECT coalesce(jsonb_agg(jsonb_build_object('fee_type_id',fee_type_id,'position',position) ORDER BY position),'[]')
 FROM sokhach.book_fee_column WHERE customer_id=p_customer
$$;

CREATE OR REPLACE FUNCTION sokhach.get_ledger(customer_id bigint) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, sokhach, pg_temp AS $$
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
            (SELECT x->>'review_reason' FROM sokhach.trip tr JOIN sokhach.event e ON e.id=tr.created_by_event
            CROSS JOIN LATERAL jsonb_array_elements(e."after"->'trips') x
            WHERE tr.id=t.id AND x->>'trip_id'=t.id::text)),
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
            FROM sokhach.receipt_line l WHERE l.receipt_id=r.id)) ORDER BY r.date,r.pid COLLATE "C"),'[]'::jsonb)
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
    SELECT coalesce(jsonb_agg(jsonb_build_object('id',id,'kind',kind,'actor',actor,
        'label',CASE kind WHEN 'fee_migration' THEN 'Tách phụ phí' WHEN 'trip_edit' THEN 'Sửa chuyến' WHEN 'trip_delete' THEN 'Xóa chuyến'
            WHEN 'legacy_edit' THEN 'Sửa dòng sổ gốc' WHEN 'legacy_delete' THEN 'Xóa dòng sổ gốc' ELSE kind END,
        'counterparty_customer_id',(SELECT CASE WHEN p.source_customer_id=event.customer_id
            THEN p.target_customer_id ELSE p.source_customer_id END FROM sokhach.offset_pair p
            WHERE (p.source_customer_id=event.customer_id AND p.source_pid=event."after"->>'receipt')
               OR (p.target_customer_id=event.customer_id AND p.target_receipt_id::text=event."after"->>'receipt')),
        'counterparty_name',(SELECT c.name FROM sokhach.offset_pair p JOIN sokhach.customer c
            ON c.id=CASE WHEN p.source_customer_id=event.customer_id THEN p.target_customer_id
                ELSE p.source_customer_id END
            WHERE (p.source_customer_id=event.customer_id AND p.source_pid=event."after"->>'receipt')
               OR (p.target_customer_id=event.customer_id AND p.target_receipt_id::text=event."after"->>'receipt')),
        'at',at,'before',CASE WHEN kind='price_edit' THEN "before" || jsonb_build_object(
            'price',"before"->'price' || jsonb_build_object(
                'unit_price_vnd',"before"->'price'->>'unit_price_vnd',
                'other_fee_vnd',"before"->'price'->>'other_fee_vnd')) ELSE "before" END,
        'after',CASE WHEN kind='price_edit' THEN "after" || jsonb_build_object(
            'price',"after"->'price' || jsonb_build_object(
                'unit_price_vnd',"after"->'price'->>'unit_price_vnd',
                'other_fee_vnd',"after"->'price'->>'other_fee_vnd')) ELSE "after" END)
        ORDER BY at DESC,id DESC),'[]'::jsonb)
    INTO v_events FROM sokhach.event WHERE event.customer_id=get_ledger.customer_id;
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
END $$;
CREATE OR REPLACE FUNCTION sokhach.delete_trip(customer_id bigint,expected_version bigint,idempotency_key text,trip_id bigint) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,sokhach,pg_temp AS $$
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
END $$;

REVOKE ALL ON ALL FUNCTIONS IN SCHEMA sokhach FROM PUBLIC,sokhach_app,sokhach_reader;
RESET ROLE;
