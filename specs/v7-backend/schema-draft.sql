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
COMMENT ON TABLE sokhach.month_state IS 'Cờ ghi đè; thiếu hàng thì chỉ tháng hiện tại theo Asia/Ho_Chi_Minh mở. Mở/khóa không ghi event.';
COMMENT ON COLUMN sokhach.month_state.locked IS 'Không DEFAULT: thiếu hàng dùng mặc định động theo giờ VN; hàng có sẵn ghi đè mặc định.';
COMMENT ON COLUMN sokhach.month_state.changed_by IS 'Danh tính phiên máy chủ đã xác minh, không lấy từ body.';

CREATE TABLE sokhach.trip (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id bigint NOT NULL REFERENCES sokhach.customer(id),
    debt_month date NOT NULL CHECK (EXTRACT(DAY FROM debt_month) = 1),
    event_date date,
    container text,
    CONSTRAINT trip_missing_date_fee_only CHECK (event_date IS NOT NULL OR container IS NULL OR container = ''),
    carrier text,
    origin text,
    destination text,
    note text,
    source_ref text,
    UNIQUE (id, customer_id, debt_month)
);
COMMENT ON TABLE sokhach.trip IS 'Danh tính chuyến chỉ thêm; container không phải khóa duy nhất.';
COMMENT ON COLUMN sokhach.trip.container IS 'Phân loại phí lẻ theo JS truthiness: chỉ NULL hoặc chuỗi rỗng là không có container; chuỗi toàn khoảng trắng vẫn là giá trị có mặt.';
COMMENT ON COLUMN sokhach.trip.debt_month IS 'Kỳ nợ là ngày mùng 1, độc lập ngày nghiệp vụ.';
COMMENT ON COLUMN sokhach.trip.event_date IS 'Ngày xe nhập kho; không suy ra kỳ nợ từ cột này.';
COMMENT ON COLUMN sokhach.trip.source_ref IS 'Tham chiếu nguồn nếu có; không chứa chứng từ thật trong bản nháp.';

CREATE TABLE sokhach.trip_price_rev (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    trip_id bigint NOT NULL REFERENCES sokhach.trip(id),
    unit_price_vnd bigint CHECK (unit_price_vnd >= 0),
    other_fee_vnd bigint CHECK (other_fee_vnd >= 0),
    created_at timestamptz NOT NULL DEFAULT now()
);
-- ĐỀ XUẤT: CHECK liên bảng cho ngày NULL; deferred để paste chèn trip rồi giá.
CREATE FUNCTION sokhach.check_trip_missing_date() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog, sokhach, pg_temp AS $$
DECLARE v_trip bigint;
BEGIN
    IF TG_TABLE_NAME = 'trip' THEN v_trip := NEW.id;
    ELSE v_trip := NEW.trip_id; END IF;
    IF EXISTS (SELECT 1 FROM sokhach.trip t WHERE t.id=v_trip AND t.event_date IS NULL
        AND NOT (t.container IS NULL OR t.container=''))
       OR EXISTS (SELECT 1 FROM sokhach.trip t WHERE t.id=v_trip AND t.event_date IS NULL
         AND NOT EXISTS (SELECT 1 FROM sokhach.trip_price_rev p WHERE p.trip_id=t.id))
       OR EXISTS (SELECT 1 FROM sokhach.trip t JOIN LATERAL
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

CREATE TABLE sokhach.receipt (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id bigint NOT NULL REFERENCES sokhach.customer(id),
    pid text NOT NULL CHECK (btrim(pid) <> ''),
    date date NOT NULL,
    method text NOT NULL CHECK (method IN ('THU TIỀN', 'CẤN TRỪ', 'ỨNG TRƯỚC', 'KHÁC')),
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
COMMENT ON COLUMN sokhach.receipt.date IS 'Ngày phiếu; FIFO xếp theo ngày rồi pid.';
COMMENT ON COLUMN sokhach.receipt.amount_vnd IS 'Tổng phiếu bất biến; phải bằng tổng dòng hiệu lực khi phiếu còn sống.';
COMMENT ON COLUMN sokhach.receipt.void_reason IS 'Hủy bắt buộc lý do không rỗng.';

CREATE TABLE sokhach.event (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id bigint NOT NULL REFERENCES sokhach.customer(id),
    kind text NOT NULL CHECK (kind IN ('paste', 'price_edit', 'adjust_trip',
        'adjust_month', 'receipt', 'receipt_edit', 'void', 'reallocation', 'import',
        'customer_attr')),
    actor text NOT NULL CHECK (btrim(actor) <> ''),
    at timestamptz NOT NULL DEFAULT now(),
    "before" jsonb NOT NULL CHECK (jsonb_typeof("before") = 'object'),
    "after" jsonb NOT NULL CHECK (jsonb_typeof("after") = 'object'),
    idempotency_key text,
    cutover_id bigint REFERENCES sokhach.cutover(id),
    CHECK ((kind = 'import') = (cutover_id IS NOT NULL)),
    CHECK (CASE kind
        WHEN 'paste' THEN "before" = '{}'::jsonb AND "after" ? 'trips'
        WHEN 'receipt' THEN "before" = '{}'::jsonb AND "after" ? 'receipt'
        WHEN 'import' THEN "before" = '{}'::jsonb AND "after" ? 'cutover'
        WHEN 'price_edit' THEN "before" ? 'price' AND "after" ? 'price'
        WHEN 'adjust_trip' THEN "before" ? 'trip' AND "after" ? 'adjustment'
        WHEN 'adjust_month' THEN "before" ? 'month' AND "after" ? 'adjustment'
        WHEN 'receipt_edit' THEN "before" ? 'receipt' AND "after" ? 'receipt'
        WHEN 'void' THEN "before" ? 'receipt' AND "after" ? 'receipt'
        WHEN 'reallocation' THEN "before" ? 'allocations' AND "after" ? 'allocations'
        WHEN 'customer_attr' THEN "before" ? 'customer' AND "after" ? 'customer'
        ELSE false END),
    UNIQUE (id, customer_id)
);
COMMENT ON TABLE sokhach.event IS 'Vết chỉ thêm trước/sau; không ghi sự kiện mở/khóa tháng.';
COMMENT ON COLUMN sokhach.event.actor IS 'Đọc từ current_setting(''sokhach.actor'', false), từ chối rỗng trong hàm lệnh.';
COMMENT ON COLUMN sokhach.event.idempotency_key IS 'Khóa lệnh nguồn, có thể lặp giữa các event của cùng lệnh.';
COMMENT ON COLUMN sokhach.event.cutover_id IS 'Chỉ event import có mốc chuyển; chỉ mục duy nhất chặn nhập lại kể cả khi không có dòng opening.';
COMMENT ON COLUMN sokhach.event."before" IS 'Bắt buộc: tạo mới dùng {}; sửa/hủy/phân bổ lại có snapshot ID và giá trị trước.';
COMMENT ON COLUMN sokhach.event."after" IS 'Bắt buộc theo kind: ID, giá trị sau và bộ phân bổ; CHECK chỉ xác nhận key tối thiểu, hàm phải kiểm nội dung/quan hệ trước commit.';

ALTER TABLE sokhach.trip ADD COLUMN created_by_event bigint NOT NULL;
ALTER TABLE sokhach.trip ADD CONSTRAINT trip_created_event_fk
    FOREIGN KEY (created_by_event, customer_id) REFERENCES sokhach.event(id, customer_id);
ALTER TABLE sokhach.trip ADD CONSTRAINT trip_event_customer_unique UNIQUE (id, customer_id);
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
ALTER TABLE sokhach.opening_balance ADD COLUMN created_by_event bigint NOT NULL;
ALTER TABLE sokhach.opening_balance ADD CONSTRAINT opening_event_fk
    FOREIGN KEY (created_by_event, customer_id) REFERENCES sokhach.event(id, customer_id);
ALTER TABLE sokhach.legacy_row ADD COLUMN created_by_event bigint NOT NULL;
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

CREATE FUNCTION sokhach.reject_immutable_change() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog, sokhach, pg_temp AS $$
BEGIN
    RAISE EXCEPTION 'immutable row: %.%', TG_TABLE_SCHEMA, TG_TABLE_NAME;
END $$;
CREATE TRIGGER event_immutable BEFORE UPDATE OR DELETE ON sokhach.event
    FOR EACH ROW EXECUTE FUNCTION sokhach.reject_immutable_change();
CREATE TRIGGER trip_immutable BEFORE UPDATE OR DELETE ON sokhach.trip
    FOR EACH ROW EXECUTE FUNCTION sokhach.reject_immutable_change();
CREATE TRIGGER trip_price_rev_immutable BEFORE UPDATE OR DELETE ON sokhach.trip_price_rev
    FOR EACH ROW EXECUTE FUNCTION sokhach.reject_immutable_change();
CREATE TRIGGER adjustment_immutable BEFORE UPDATE OR DELETE ON sokhach.adjustment
    FOR EACH ROW EXECUTE FUNCTION sokhach.reject_immutable_change();
CREATE TRIGGER idempotency_immutable BEFORE UPDATE OR DELETE ON sokhach.idempotency
    FOR EACH ROW EXECUTE FUNCTION sokhach.reject_immutable_change();
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
            AND (OLD.date IS DISTINCT FROM NEW.date OR OLD.method IS DISTINCT FROM NEW.method
                 OR OLD.meta_changed_by_event IS DISTINCT FROM NEW.meta_changed_by_event))
        OR (OLD.voided_on IS NULL AND NEW.voided_on IS NULL
            AND ROW(OLD.void_reason, OLD.voided_by, OLD.voided_by_event)
                IS DISTINCT FROM ROW(NEW.void_reason, NEW.voided_by, NEW.voided_by_event))
        OR (OLD.voided_on IS NULL AND NEW.voided_on IS NULL
            AND ROW(OLD.date, OLD.method) IS DISTINCT FROM ROW(NEW.date, NEW.method)
            AND NEW.meta_changed_by_event IS NOT DISTINCT FROM OLD.meta_changed_by_event)
        OR (OLD.voided_on IS NULL AND NEW.voided_on IS NULL
            AND ROW(OLD.date, OLD.method) IS NOT DISTINCT FROM ROW(NEW.date, NEW.method)
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
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA sokhach FROM PUBLIC, sokhach_app, sokhach_reader;
-- Migration tương lai: tất cả object thuộc sokhach_owner; SET ROLE sokhach_owner
-- trước CREATE để default privilege áp dụng đúng role tạo hàm. Không GRANT SELECT
-- bảng/view toàn khách cho app hoặc reader. Chỉ GRANT EXECUTE từng hàm sau review.
ALTER DEFAULT PRIVILEGES FOR ROLE sokhach_owner REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC;
ALTER DEFAULT PRIVILEGES FOR ROLE sokhach_owner IN SCHEMA sokhach REVOKE ALL ON TABLES FROM PUBLIC;
ALTER DEFAULT PRIVILEGES FOR ROLE sokhach_owner IN SCHEMA sokhach REVOKE ALL ON SEQUENCES FROM PUBLIC;
GRANT USAGE ON SCHEMA sokhach TO sokhach_app, sokhach_reader;
RESET ROLE;
-- Bản thử ai vào app cũng thao tác; chưa GRANT EXECUTE vì chưa nối app server.
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
-- FUNCTION sokhach.record_receipt(customer_id bigint, expected_version bigint, idempotency_key text, date date, method text, amount_vnd bigint) RETURNS jsonb
-- FUNCTION sokhach.edit_receipt_meta(customer_id bigint, expected_version bigint, idempotency_key text, pid text, date date, method text) RETURNS jsonb
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
-- Chưa cấp EXECUTE cho app/reader; chưa có phiên HTTP kết nối lược đồ này.

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
