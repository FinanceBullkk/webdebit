-- Đội xe đợt 1 (CHI-PHI-XE-01, 18/11/2026; spec specs/chi-phi-xe-01.md): schema riêng `doixe` cho chi phí chặng do tài xế,
-- người đi lệnh hoặc công ty trả, lần ứng, đợt hoàn, khóa tháng chung cả đội xe và Lịch sử. Chỉ ĐỌC `sokhach` (nối chặng hàng với
-- chuyến khách theo container), không ghi bảng nào của `sokhach`, không đổi hàm hay quyền cũ. Chạy lại được.
-- Lệnh ghi nhận một jsonb (API kiểm hình dạng trước, hàm kiểm lại), tiền là chuỗi số nguyên VND, NULL là ô trống (không phải 0).
-- Mọi lệnh ghi: một lệnh đội xe mỗi lúc (khóa tư vấn), mã yêu cầu chống ghi trùng (doixe.lenh), người làm từ sokhach.actor,
-- ngày không sau hôm nay giờ VN, Lịch sử chỉ thêm (doixe.su_kien) có trước → sau. Áp sau 2026-11-18-v7-tong-quan-tat-jit.sql.
BEGIN;
CREATE SCHEMA IF NOT EXISTS doixe AUTHORIZATION sokhach_owner;
REVOKE ALL ON SCHEMA doixe FROM PUBLIC;
GRANT USAGE ON SCHEMA doixe TO sokhach_app;
SET LOCAL ROLE sokhach_owner;
COMMENT ON SCHEMA doixe IS 'CHI-PHI-XE-01: đội xe đợt 1 (chặng, chi phí, ứng, hoàn, khóa tháng). Chỉ đọc sokhach.';

CREATE TABLE IF NOT EXISTS doixe.nguoi (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    ma_nguon text NOT NULL UNIQUE CHECK (ma_nguon ~ '^[A-Za-z0-9_-]{1,40}$'),
    ten text NOT NULL CHECK (btrim(ten) <> '' AND char_length(ten) <= 100),
    vai text NOT NULL CHECK (vai IN ('tai_xe', 'di_lenh')),
    so_du_dau_vnd bigint NOT NULL,
    dang_dung boolean NOT NULL DEFAULT true
);
COMMENT ON TABLE doixe.nguoi IS 'Người nhận ứng: tài xế hoặc người đi lệnh. Danh mục nạp sẵn (nap_danh_muc), chưa sửa trên web ở đợt 1.';
COMMENT ON COLUMN doixe.nguoi.so_du_dau_vnd IS 'Số dư trước mọi dòng trong doixe; dương là công ty còn nợ người này. Nạp rõ ràng, không mặc định.';

CREATE TABLE IF NOT EXISTS doixe.xe (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    bien_so text NOT NULL CHECK (btrim(bien_so) <> '' AND char_length(bien_so) <= 20),
    bien_key text GENERATED ALWAYS AS (upper(regexp_replace(bien_so, '[^0-9A-Za-z]', '', 'g'))) STORED UNIQUE,
    nhom text NOT NULL CHECK (btrim(nhom) <> '' AND char_length(nhom) <= 50),
    thue_ngoai boolean NOT NULL DEFAULT false,
    tai_xe_id bigint REFERENCES doixe.nguoi(id),
    dang_dung boolean NOT NULL DEFAULT true
);
COMMENT ON TABLE doixe.xe IS 'Phương tiện. Xe mình hay xe thuê theo cột thue_ngoai của danh sách xe, không theo chữ nhà xe.';

CREATE TABLE IF NOT EXISTS doixe.loai_phi (
    ma text PRIMARY KEY CHECK (ma ~ '^[a-z]{2,12}$'),
    ten text NOT NULL CHECK (btrim(ten) <> ''),
    ten_day_du text,
    thu_tu integer NOT NULL UNIQUE CHECK (thu_tu > 0),
    cot_sheet integer UNIQUE CHECK (cot_sheet BETWEEN 0 AND 28),
    cong_ty_tra boolean NOT NULL DEFAULT false
);
COMMENT ON TABLE doixe.loai_phi IS 'Danh mục phí chặng theo cột tab tài xế (cot_sheet: chỉ số cột từ 0 của khối 29 cột). cong_ty_tra: VETC, không vào phần hoàn.';
INSERT INTO doixe.loai_phi(ma, ten, ten_day_du, thu_tu, cot_sheet, cong_ty_tra) VALUES
    ('nang', 'Phí nâng', NULL, 1, 12, false), ('nangha', 'Nâng hạ', NULL, 2, 13, false),
    ('cau', 'Cầu đường', NULL, 3, 14, false), ('neo', 'Neo', NULL, 4, 15, false),
    ('xi', 'Xí cont', 'Xí cont · trái tuyến · xe nâng', 5, 16, false), ('dao', 'Đảo cont', NULL, 6, 17, false),
    ('moi', 'Cont mới', NULL, 7, 18, false), ('doi', 'Dời cont', NULL, 8, 19, false),
    ('seal', 'Mua seal', NULL, 9, 20, false), ('bai', 'Bãi chờ', NULL, 10, 21, false),
    ('dieu', 'Điều độ', NULL, 11, 22, false), ('dau', 'Đổ dầu', NULL, 12, 23, false),
    ('ps', 'Phát sinh', NULL, 13, 24, false), ('may', 'Nổ máy', 'Nổ máy phát', 14, 27, false),
    ('vetc', 'VETC', 'Cầu đường VETC, công ty trả', 15, 26, true)
ON CONFLICT (ma) DO UPDATE SET ten = EXCLUDED.ten, ten_day_du = EXCLUDED.ten_day_du, thu_tu = EXCLUDED.thu_tu,
    cot_sheet = EXCLUDED.cot_sheet, cong_ty_tra = EXCLUDED.cong_ty_tra;

CREATE TABLE IF NOT EXISTS doixe.ung (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    nguoi_id bigint NOT NULL REFERENCES doixe.nguoi(id),
    ngay date NOT NULL,
    so_tien_vnd bigint NOT NULL CHECK (so_tien_vnd > 0),
    ghi_chu text CHECK (ghi_chu IS NULL OR (btrim(ghi_chu) <> '' AND char_length(ghi_chu) <= 500)),
    actor text NOT NULL CHECK (btrim(actor) <> ''),
    luc timestamptz NOT NULL DEFAULT clock_timestamp(),
    huy_actor text,
    huy_luc timestamptz,
    huy_ly_do text CHECK (huy_ly_do IS NULL OR btrim(huy_ly_do) <> ''),
    CHECK ((huy_luc IS NULL) = (huy_actor IS NULL) AND (huy_luc IS NULL) = (huy_ly_do IS NULL))
);
CREATE INDEX IF NOT EXISTS ung_nguoi ON doixe.ung (nguoi_id, ngay);
COMMENT ON TABLE doixe.ung IS 'Lần ứng. Không xóa; hủy bắt buộc lý do, vẫn hiện.';

CREATE TABLE IF NOT EXISTS doixe.dot_hoan (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    nguoi_id bigint NOT NULL REFERENCES doixe.nguoi(id),
    ngay date NOT NULL,
    so_tien_vnd bigint NOT NULL CHECK (so_tien_vnd >= 0),
    tong_dong_vnd bigint NOT NULL,
    dong_ids bigint[] NOT NULL CHECK (cardinality(dong_ids) > 0),
    actor text NOT NULL CHECK (btrim(actor) <> ''),
    luc timestamptz NOT NULL DEFAULT clock_timestamp(),
    huy_actor text,
    huy_luc timestamptz,
    huy_ly_do text CHECK (huy_ly_do IS NULL OR btrim(huy_ly_do) <> ''),
    CHECK ((huy_luc IS NULL) = (huy_actor IS NULL) AND (huy_luc IS NULL) = (huy_ly_do IS NULL))
);
CREATE INDEX IF NOT EXISTS dot_hoan_nguoi ON doixe.dot_hoan (nguoi_id, ngay);
COMMENT ON TABLE doixe.dot_hoan IS 'Đợt hoàn: số tiền thực chuyển (có thể khác tổng các dòng, kể cả 0); dong_ids giữ các dòng lúc ghi. Hủy bắt buộc lý do.';

CREATE TABLE IF NOT EXISTS doixe.chang (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    ngay date NOT NULL,
    container text NOT NULL CHECK (container <> '' AND container = upper(container) AND container !~ '\s' AND char_length(container) <= 20),
    loai text NOT NULL CHECK (loai IN ('hang', 'chuyen_cang', 'tra_rong', 'rut_mooc', 'tha_mooc', 'khac')),
    xe_id bigint NOT NULL REFERENCES doixe.xe(id),
    tai_xe_id bigint REFERENCES doixe.nguoi(id),
    tra text NOT NULL CHECK (tra IN ('nguoi', 'cong_ty')),
    nguoi_tra_id bigint REFERENCES doixe.nguoi(id),
    noi_lay text CHECK (char_length(noi_lay) <= 200),
    noi_ha text CHECK (char_length(noi_ha) <= 200),
    kho text CHECK (char_length(kho) <= 200),
    tinh text CHECK (char_length(tinh) <= 200),
    ten_hang text CHECK (char_length(ten_hang) <= 200),
    ghi_chu text CHECK (char_length(ghi_chu) <= 200),
    sau_khoa boolean NOT NULL DEFAULT false,
    da_xoa boolean NOT NULL DEFAULT false,
    da_bo boolean NOT NULL DEFAULT false,
    actor text NOT NULL CHECK (btrim(actor) <> ''),
    luc timestamptz NOT NULL DEFAULT clock_timestamp(),
    CHECK ((tra = 'nguoi') = (nguoi_tra_id IS NOT NULL)),
    CHECK (NOT (da_xoa AND da_bo))
);
CREATE UNIQUE INDEX IF NOT EXISTS chang_mot_lan ON doixe.chang (ngay, container, loai, xe_id) WHERE NOT da_xoa;
CREATE INDEX IF NOT EXISTS chang_nguoi_tra ON doixe.chang (nguoi_tra_id, ngay) WHERE NOT da_xoa;
CREATE INDEX IF NOT EXISTS chang_tai_xe ON doixe.chang (tai_xe_id, ngay) WHERE NOT da_xoa;
CREATE INDEX IF NOT EXISTS chang_xe ON doixe.chang (xe_id, ngay) WHERE NOT da_xoa;
COMMENT ON TABLE doixe.chang IS 'Một chặng một xe chạy. Người trả theo chặng: người (tài xế, người đi lệnh) hoặc công ty. da_xoa: xóa ở tháng mở, chưa hoàn (ẩn); da_bo: bỏ ở tháng khóa hoặc đã hoàn (gạch ngang, có dòng trừ lại).';

CREATE TABLE IF NOT EXISTS doixe.dong (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    chang_id bigint NOT NULL REFERENCES doixe.chang(id),
    loai text NOT NULL CHECK (loai IN ('goc', 'dieu_chinh', 'tru_lai')),
    dot_hoan_id bigint REFERENCES doixe.dot_hoan(id),
    dc_phi text REFERENCES doixe.loai_phi(ma),
    dc_truoc_vnd bigint,
    dc_sau_vnd bigint,
    actor text NOT NULL CHECK (btrim(actor) <> ''),
    luc timestamptz NOT NULL DEFAULT clock_timestamp(),
    CHECK ((loai = 'dieu_chinh') = (dc_phi IS NOT NULL)),
    CHECK (loai = 'dieu_chinh' OR (dc_truoc_vnd IS NULL AND dc_sau_vnd IS NULL))
);
CREATE UNIQUE INDEX IF NOT EXISTS dong_mot_goc ON doixe.dong (chang_id) WHERE loai = 'goc';
CREATE INDEX IF NOT EXISTS dong_chang ON doixe.dong (chang_id);
CREATE INDEX IF NOT EXISTS dong_dot ON doixe.dong (dot_hoan_id) WHERE dot_hoan_id IS NOT NULL;
COMMENT ON TABLE doixe.dong IS 'Đơn vị chờ hoàn: dòng gốc của chặng, dòng điều chỉnh (tháng khóa, đã hoàn), dòng trừ lại khi bỏ chặng. Thuộc tối đa một đợt hoàn chưa hủy (dot_hoan_id).';

CREATE TABLE IF NOT EXISTS doixe.dong_phi (
    dong_id bigint NOT NULL REFERENCES doixe.dong(id),
    loai_phi text NOT NULL REFERENCES doixe.loai_phi(ma),
    so_tien_vnd bigint NOT NULL,
    PRIMARY KEY (dong_id, loai_phi)
);
COMMENT ON TABLE doixe.dong_phi IS 'Tiền từng loại phí của một dòng. Không có dòng là ô trống (NULL), không phải 0. Dòng gốc không âm; điều chỉnh, trừ lại là hiệu số có dấu.';

CREATE TABLE IF NOT EXISTS doixe.thang_khoa (
    thang date PRIMARY KEY CHECK (extract(day FROM thang) = 1),
    khoa boolean NOT NULL,
    actor text NOT NULL CHECK (btrim(actor) <> ''),
    luc timestamptz NOT NULL DEFAULT clock_timestamp()
);
COMMENT ON TABLE doixe.thang_khoa IS 'Khóa tháng chung cả đội xe. Không có dòng: chỉ tháng hiện tại (giờ VN) mở.';

CREATE TABLE IF NOT EXISTS doixe.lenh (
    key text PRIMARY KEY CHECK (btrim(key) <> '' AND char_length(key) <= 128),
    lenh text NOT NULL,
    request_hash text NOT NULL CHECK (request_hash ~ '^[0-9a-f]{64}$'),
    result jsonb NOT NULL,
    actor text NOT NULL CHECK (btrim(actor) <> ''),
    luc timestamptz NOT NULL DEFAULT clock_timestamp()
);
COMMENT ON TABLE doixe.lenh IS 'Mã yêu cầu đã chạy: cùng mã cùng nội dung trả kết quả cũ, khác nội dung bị từ chối.';

CREATE TABLE IF NOT EXISTS doixe.su_kien (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    viec text NOT NULL CHECK (viec IN ('nap', 'them_chang', 'sua_chang', 'dieu_chinh', 'doi_nguoi_tra', 'xoa_chang', 'bo_chang',
                                       'ghi_ung', 'huy_ung', 'ghi_hoan', 'huy_hoan', 'khoa_thang')),
    actor text NOT NULL CHECK (btrim(actor) <> ''),
    luc timestamptz NOT NULL DEFAULT clock_timestamp(),
    nguoi_id bigint REFERENCES doixe.nguoi(id),
    tai_xe_id bigint REFERENCES doixe.nguoi(id),
    xe_id bigint REFERENCES doixe.xe(id),
    truoc jsonb NOT NULL CHECK (jsonb_typeof(truoc) = 'object'),
    sau jsonb NOT NULL CHECK (jsonb_typeof(sau) = 'object'),
    ly_do text CHECK (ly_do IS NULL OR btrim(ly_do) <> ''),
    lenh text,
    CHECK ((viec IN ('huy_ung', 'huy_hoan')) = (ly_do IS NOT NULL))
);
CREATE INDEX IF NOT EXISTS su_kien_nguoi ON doixe.su_kien (nguoi_id, id DESC);
CREATE INDEX IF NOT EXISTS su_kien_xe ON doixe.su_kien (xe_id, id DESC);
COMMENT ON TABLE doixe.su_kien IS 'Lịch sử đội xe, chỉ thêm: người làm, lúc làm, trước → sau, lý do hủy.';

CREATE OR REPLACE FUNCTION doixe._chan_sua() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog, doixe, pg_temp AS $$
BEGIN
    RAISE EXCEPTION 'IMMUTABLE';
END $$;
CREATE OR REPLACE TRIGGER su_kien_chi_them BEFORE UPDATE OR DELETE ON doixe.su_kien FOR EACH ROW EXECUTE FUNCTION doixe._chan_sua();
CREATE OR REPLACE TRIGGER lenh_chi_them BEFORE UPDATE OR DELETE ON doixe.lenh FOR EACH ROW EXECUTE FUNCTION doixe._chan_sua();
CREATE OR REPLACE TRIGGER ung_khong_xoa BEFORE DELETE ON doixe.ung FOR EACH ROW EXECUTE FUNCTION doixe._chan_sua();
CREATE OR REPLACE TRIGGER dot_hoan_khong_xoa BEFORE DELETE ON doixe.dot_hoan FOR EACH ROW EXECUTE FUNCTION doixe._chan_sua();
CREATE OR REPLACE TRIGGER chang_khong_xoa BEFORE DELETE ON doixe.chang FOR EACH ROW EXECUTE FUNCTION doixe._chan_sua();
CREATE OR REPLACE TRIGGER dong_khong_xoa BEFORE DELETE ON doixe.dong FOR EACH ROW EXECUTE FUNCTION doixe._chan_sua();

-- ---------------------------------------------------------------------------------------------------------------------------
-- Hàm phụ: không SECURITY DEFINER, không cấp cho ai; chỉ chạy bên trong hàm lệnh/hàm đọc.
CREATE OR REPLACE FUNCTION doixe._actor() RETURNS text
LANGUAGE plpgsql STABLE SET search_path = pg_catalog, doixe, pg_temp AS $$
DECLARE v text := nullif(btrim(current_setting('sokhach.actor', true)), '');
BEGIN
    IF v IS NULL THEN RAISE EXCEPTION 'ACTOR_REQUIRED'; END IF;
    RETURN v;
END $$;

CREATE OR REPLACE FUNCTION doixe._hom_nay() RETURNS date
LANGUAGE sql STABLE SET search_path = pg_catalog, doixe, pg_temp AS $$
    SELECT (now() AT TIME ZONE 'Asia/Ho_Chi_Minh')::date
$$;

CREATE OR REPLACE FUNCTION doixe._khoa(p_ngay date) RETURNS boolean
LANGUAGE sql STABLE SET search_path = pg_catalog, doixe, pg_temp AS $$
    SELECT coalesce((SELECT k.khoa FROM doixe.thang_khoa k WHERE k.thang = date_trunc('month', p_ngay)::date),
                    date_trunc('month', p_ngay)::date <> date_trunc('month', doixe._hom_nay())::date)
$$;

CREATE OR REPLACE FUNCTION doixe._id(p jsonb, p_key text, p_null boolean DEFAULT false) RETURNS bigint
LANGUAGE plpgsql IMMUTABLE SET search_path = pg_catalog, doixe, pg_temp AS $$
DECLARE v jsonb := p -> p_key;
BEGIN
    IF v IS NULL OR jsonb_typeof(v) = 'null' THEN
        IF p_null THEN RETURN NULL; END IF;
        RAISE EXCEPTION 'INVALID_COMMAND';
    END IF;
    IF jsonb_typeof(v) <> 'number' OR v::text !~ '^[1-9][0-9]{0,17}$' THEN RAISE EXCEPTION 'INVALID_COMMAND'; END IF;
    RETURN v::text::bigint;
END $$;

-- Tiền không âm: chuỗi số nguyên tối đa 16 chữ số (giữ an toàn số nguyên ở JS); null là ô trống.
CREATE OR REPLACE FUNCTION doixe._vnd(v jsonb) RETURNS bigint
LANGUAGE plpgsql IMMUTABLE SET search_path = pg_catalog, doixe, pg_temp AS $$
BEGIN
    IF v IS NULL OR jsonb_typeof(v) = 'null' THEN RETURN NULL; END IF;
    IF jsonb_typeof(v) <> 'string' OR (v #>> '{}') !~ '^(0|[1-9][0-9]{0,15})$' THEN RAISE EXCEPTION 'INVALID_VND'; END IF;
    RETURN (v #>> '{}')::bigint;
END $$;

CREATE OR REPLACE FUNCTION doixe._vnd_co_dau(v jsonb) RETURNS bigint
LANGUAGE plpgsql IMMUTABLE SET search_path = pg_catalog, doixe, pg_temp AS $$
BEGIN
    IF v IS NULL OR jsonb_typeof(v) = 'null' THEN RETURN NULL; END IF;
    IF jsonb_typeof(v) <> 'string' OR (v #>> '{}') !~ '^(0|-?[1-9][0-9]{0,15})$' THEN RAISE EXCEPTION 'INVALID_VND'; END IF;
    RETURN (v #>> '{}')::bigint;
END $$;

CREATE OR REPLACE FUNCTION doixe._ngay(v jsonb) RETURNS date
LANGUAGE plpgsql IMMUTABLE SET search_path = pg_catalog, doixe, pg_temp AS $$
DECLARE d date;
BEGIN
    IF v IS NULL OR jsonb_typeof(v) = 'null' THEN RETURN NULL; END IF;
    IF jsonb_typeof(v) <> 'string' OR (v #>> '{}') !~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$' THEN RAISE EXCEPTION 'INVALID_DATE'; END IF;
    BEGIN
        d := (v #>> '{}')::date;
    EXCEPTION WHEN others THEN
        RAISE EXCEPTION 'INVALID_DATE';
    END;
    IF d < DATE '2020-01-01' THEN RAISE EXCEPTION 'INVALID_DATE'; END IF;
    RETURN d;
END $$;

CREATE OR REPLACE FUNCTION doixe._chu(v jsonb, p_max integer) RETURNS text
LANGUAGE plpgsql IMMUTABLE SET search_path = pg_catalog, doixe, pg_temp AS $$
DECLARE t text;
BEGIN
    IF v IS NULL OR jsonb_typeof(v) = 'null' THEN RETURN NULL; END IF;
    IF jsonb_typeof(v) <> 'string' THEN RAISE EXCEPTION 'INVALID_COMMAND'; END IF;
    t := btrim(v #>> '{}');
    IF t = '' THEN RETURN NULL; END IF;
    IF char_length(t) > p_max OR t ~ '[[:cntrl:]]' THEN RAISE EXCEPTION 'INVALID_COMMAND'; END IF;
    RETURN t;
END $$;

CREATE OR REPLACE FUNCTION doixe._chi_khoa(p jsonb, p_keys text[]) RETURNS void
LANGUAGE plpgsql IMMUTABLE SET search_path = pg_catalog, doixe, pg_temp AS $$
BEGIN
    IF jsonb_typeof(p) IS DISTINCT FROM 'object' OR EXISTS (SELECT 1 FROM jsonb_object_keys(p) k WHERE k <> ALL (p_keys)) THEN
        RAISE EXCEPTION 'INVALID_COMMAND';
    END IF;
END $$;

-- Bắt đầu một lệnh ghi: khóa tư vấn chung (một lệnh đội xe mỗi lúc), rồi tra mã yêu cầu.
CREATE OR REPLACE FUNCTION doixe._bat_dau(p jsonb, p_lenh text) RETURNS jsonb
LANGUAGE plpgsql SET search_path = pg_catalog, doixe, pg_temp AS $$
DECLARE v_key text; v doixe.lenh%ROWTYPE; v_hash text;
BEGIN
    PERFORM doixe._actor();
    IF jsonb_typeof(p) IS DISTINCT FROM 'object' OR jsonb_typeof(p -> 'idempotency_key') IS DISTINCT FROM 'string' THEN
        RAISE EXCEPTION 'INVALID_COMMAND';
    END IF;
    v_key := p ->> 'idempotency_key';
    IF btrim(v_key) = '' OR char_length(v_key) > 128 OR v_key ~ '[[:cntrl:]]' THEN RAISE EXCEPTION 'INVALID_COMMAND'; END IF;
    PERFORM pg_advisory_xact_lock(hashtext('doixe.ghi'));
    v_hash := encode(sha256(convert_to((p - 'idempotency_key')::text, 'UTF8')), 'hex');
    SELECT * INTO v FROM doixe.lenh WHERE key = v_key;
    IF FOUND THEN
        IF v.lenh <> p_lenh OR v.request_hash <> v_hash THEN RAISE EXCEPTION 'IDEMPOTENCY_CONFLICT'; END IF;
        RETURN v.result || jsonb_build_object('lap_lai', true);
    END IF;
    RETURN NULL;
END $$;

CREATE OR REPLACE FUNCTION doixe._xong(p jsonb, p_lenh text, p_result jsonb) RETURNS jsonb
LANGUAGE plpgsql SET search_path = pg_catalog, doixe, pg_temp AS $$
BEGIN
    INSERT INTO doixe.lenh(key, lenh, request_hash, result, actor)
    VALUES (p ->> 'idempotency_key', p_lenh, encode(sha256(convert_to((p - 'idempotency_key')::text, 'UTF8')), 'hex'),
            p_result, doixe._actor());
    RETURN p_result;
END $$;

CREATE OR REPLACE FUNCTION doixe._ghi(p_viec text, p_nguoi bigint, p_tai_xe bigint, p_xe bigint, p_truoc jsonb, p_sau jsonb,
                                      p_ly_do text, p_lenh text) RETURNS bigint
LANGUAGE sql SET search_path = pg_catalog, doixe, pg_temp AS $$
    INSERT INTO doixe.su_kien(viec, actor, nguoi_id, tai_xe_id, xe_id, truoc, sau, ly_do, lenh)
    VALUES (p_viec, doixe._actor(), p_nguoi, p_tai_xe, p_xe, p_truoc, p_sau, p_ly_do, p_lenh)
    RETURNING id
$$;

-- Tiền của một dòng tính vào phần hoàn (mọi loại phí trừ loại công ty trả); NULL khi dòng không có ô nào.
CREATE OR REPLACE FUNCTION doixe._tien_dong(p_dong bigint) RETURNS bigint
LANGUAGE sql STABLE SET search_path = pg_catalog, doixe, pg_temp AS $$
    SELECT sum(f.so_tien_vnd)::bigint FROM doixe.dong_phi f JOIN doixe.loai_phi l ON l.ma = f.loai_phi
    WHERE f.dong_id = p_dong AND NOT l.cong_ty_tra
$$;

-- Số dư người nhận ứng = số dư đầu + tiền các dòng người đó trả − đợt hoàn chưa hủy − lần ứng chưa hủy (CHI-PHI-XE-01 mục 8).
-- p_truoc: chỉ tính các khoản có ngày trước ngày đó (số dư đầu tháng).
CREATE OR REPLACE FUNCTION doixe._so_du(p_nguoi bigint, p_truoc date DEFAULT NULL) RETURNS bigint
LANGUAGE sql STABLE SET search_path = pg_catalog, doixe, pg_temp AS $$
    SELECT (n.so_du_dau_vnd
        + coalesce((SELECT sum(f.so_tien_vnd) FROM doixe.chang c JOIN doixe.dong d ON d.chang_id = c.id
                    JOIN doixe.dong_phi f ON f.dong_id = d.id JOIN doixe.loai_phi l ON l.ma = f.loai_phi
                    WHERE c.nguoi_tra_id = n.id AND NOT c.da_xoa AND NOT l.cong_ty_tra
                      AND (p_truoc IS NULL OR c.ngay < p_truoc)), 0)
        - coalesce((SELECT sum(h.so_tien_vnd) FROM doixe.dot_hoan h
                    WHERE h.nguoi_id = n.id AND h.huy_luc IS NULL AND (p_truoc IS NULL OR h.ngay < p_truoc)), 0)
        - coalesce((SELECT sum(u.so_tien_vnd) FROM doixe.ung u
                    WHERE u.nguoi_id = n.id AND u.huy_luc IS NULL AND (p_truoc IS NULL OR u.ngay < p_truoc)), 0))::bigint
    FROM doixe.nguoi n WHERE n.id = p_nguoi
$$;

CREATE OR REPLACE FUNCTION doixe._luc(p timestamptz) RETURNS text
LANGUAGE sql STABLE SET search_path = pg_catalog, doixe, pg_temp AS $$
    SELECT to_char(p AT TIME ZONE 'Asia/Ho_Chi_Minh', 'DD/MM HH24:MI')
$$;

-- Chuyến khách có container trong danh sách, ngày trong khoảng: chuyến web chưa xóa, không bị loại, và dòng chuyến sổ gốc
-- (bản sửa mới nhất, chưa xóa) của sổ đang hoạt động; cùng cách lấy với sokhach.get_trip_month. Chỉ đọc.
CREATE OR REPLACE FUNCTION doixe._chuyen_ds(p_conts text[], p_lo date, p_hi date)
RETURNS TABLE(cont text, khach text, ngay date, tu text, den text)
LANGUAGE sql STABLE SET search_path = pg_catalog, doixe, pg_temp AS $$
    WITH act AS (
        SELECT c.id, c.name, cc.cutover_id FROM sokhach.customer c
          JOIN sokhach.cutover_customer cc ON cc.customer_id = c.id AND cc.status = 'active'
          JOIN sokhach.cutover x ON x.id = cc.cutover_id AND x.status = 'active'
         WHERE NOT c.archived)
    SELECT sokhach._normalize_key(t.container), a.name, t.event_date, t.origin, t.destination
      FROM sokhach.v_trip_current t JOIN act a ON a.id = t.customer_id
     WHERE cardinality(p_conts) > 0 AND NOT t.deleted AND t.status <> 'rejected' AND t.event_date BETWEEN p_lo AND p_hi
       AND sokhach._normalize_key(t.container) = ANY (p_conts)
    UNION ALL
    SELECT y.cont, a.name, y.dt, y.tu, y.den
      FROM sokhach.legacy_row l JOIN act a ON (a.id, a.cutover_id) = (l.customer_id, l.cutover_id)
      LEFT JOIN LATERAL (SELECT r.id, r.event_date, r.container, r.origin, r.destination, r.deleted FROM sokhach.legacy_trip_rev r
                          WHERE r.legacy_row_id = l.id ORDER BY r.id DESC LIMIT 1) r ON true
      CROSS JOIN LATERAL (SELECT sokhach._normalize_key(CASE WHEN r.id IS NULL THEN l.display ->> 'container' ELSE r.container END) AS cont,
                                 CASE WHEN r.id IS NULL THEN sokhach._legacy_date(l.display ->> 'date') ELSE r.event_date END AS dt,
                                 CASE WHEN r.id IS NULL THEN l.display ->> 'from' ELSE r.origin END AS tu,
                                 CASE WHEN r.id IS NULL THEN l.display ->> 'to' ELSE r.destination END AS den) y
     WHERE cardinality(p_conts) > 0 AND l.kind = 'trip' AND NOT coalesce(r.deleted, false)
       AND y.cont = ANY (p_conts) AND y.dt BETWEEN p_lo AND p_hi
$$;

-- Chuyến khách gần ngày nhất của một chặng hàng, lệch không quá 10 ngày.
CREATE OR REPLACE FUNCTION doixe._chuyen(p_cont text, p_ngay date) RETURNS jsonb
LANGUAGE sql STABLE SET search_path = pg_catalog, doixe, pg_temp AS $$
    SELECT jsonb_build_object('khach', k.khach, 'ngay', k.ngay, 'tu', k.tu, 'den', k.den)
      FROM doixe._chuyen_ds(ARRAY[p_cont], p_ngay - 10, p_ngay + 10) k
     ORDER BY abs(k.ngay - p_ngay), k.ngay, k.khach LIMIT 1
$$;

-- Chặng kèm các dòng, tiền từng phí (chuỗi), chuyến khách đã nối; dùng cho mọi hàm đọc sổ.
CREATE OR REPLACE FUNCTION doixe._chang_ds(p_ids bigint[]) RETURNS jsonb
LANGUAGE sql STABLE SET search_path = pg_catalog, doixe, pg_temp AS $$
    WITH c AS (SELECT * FROM doixe.chang WHERE id = ANY (p_ids)),
    cand AS MATERIALIZED (
        SELECT * FROM doixe._chuyen_ds(coalesce((SELECT array_agg(DISTINCT container) FROM c WHERE loai = 'hang'), '{}'),
                                       coalesce((SELECT min(ngay) FROM c), DATE '2020-01-01') - 10,
                                       coalesce((SELECT max(ngay) FROM c), DATE '2020-01-01') + 10))
    SELECT coalesce(jsonb_agg(jsonb_build_object(
        'id', c.id, 'ngay', c.ngay, 'container', c.container, 'loai', c.loai, 'xe_id', c.xe_id, 'tai_xe_id', c.tai_xe_id,
        'tra', c.tra, 'nguoi_tra_id', c.nguoi_tra_id, 'noi_lay', c.noi_lay, 'noi_ha', c.noi_ha, 'kho', c.kho, 'tinh', c.tinh,
        'ten_hang', c.ten_hang, 'ghi_chu', c.ghi_chu, 'sau_khoa', c.sau_khoa, 'da_bo', c.da_bo, 'actor', c.actor, 'luc', doixe._luc(c.luc),
        'chuyen', (SELECT jsonb_build_object('khach', k.khach, 'ngay', k.ngay, 'tu', k.tu, 'den', k.den) FROM cand k
                    WHERE c.loai = 'hang' AND k.cont = c.container AND abs(k.ngay - c.ngay) <= 10
                    ORDER BY abs(k.ngay - c.ngay), k.ngay, k.khach LIMIT 1),
        'dong', (SELECT coalesce(jsonb_agg(jsonb_build_object(
                    'id', d.id, 'loai', d.loai, 'dot_hoan_id', d.dot_hoan_id, 'dot_ngay', h.ngay,
                    'dc_phi', d.dc_phi, 'dc_truoc_vnd', d.dc_truoc_vnd::text, 'dc_sau_vnd', d.dc_sau_vnd::text,
                    'actor', d.actor, 'luc', doixe._luc(d.luc),
                    'phi', (SELECT coalesce(jsonb_object_agg(f.loai_phi, f.so_tien_vnd::text), '{}'::jsonb) FROM doixe.dong_phi f WHERE f.dong_id = d.id))
                  ORDER BY d.id), '[]'::jsonb)
                 FROM doixe.dong d LEFT JOIN doixe.dot_hoan h ON h.id = d.dot_hoan_id WHERE d.chang_id = c.id)
      ) ORDER BY c.ngay, c.id), '[]'::jsonb) FROM c
$$;

-- Phần chung của mọi hàm đọc: danh mục phí, người, xe, các tháng có dữ liệu và trạng thái khóa.
CREATE OR REPLACE FUNCTION doixe._chung() RETURNS jsonb
LANGUAGE sql STABLE SET search_path = pg_catalog, doixe, pg_temp AS $$
    WITH t AS (SELECT DISTINCT m FROM (
        SELECT date_trunc('month', ngay)::date AS m FROM doixe.chang WHERE NOT da_xoa
        UNION ALL SELECT date_trunc('month', ngay)::date FROM doixe.ung
        UNION ALL SELECT date_trunc('month', ngay)::date FROM doixe.dot_hoan
        UNION ALL SELECT date_trunc('month', doixe._hom_nay())::date) s)
    SELECT jsonb_build_object(
        'loai_phi', (SELECT jsonb_agg(jsonb_build_object('ma', l.ma, 'ten', l.ten, 'ten_day_du', l.ten_day_du, 'thu_tu', l.thu_tu,
                       'cot_sheet', l.cot_sheet, 'cong_ty_tra', l.cong_ty_tra) ORDER BY l.thu_tu) FROM doixe.loai_phi l),
        'danh_muc', jsonb_build_object(
            'nguoi', (SELECT coalesce(jsonb_agg(jsonb_build_object('id', n.id, 'ten', n.ten, 'vai', n.vai, 'dang_dung', n.dang_dung)
                        ORDER BY n.id), '[]'::jsonb) FROM doixe.nguoi n),
            'xe', (SELECT coalesce(jsonb_agg(jsonb_build_object('id', x.id, 'bien_so', x.bien_so, 'nhom', x.nhom, 'thue_ngoai', x.thue_ngoai,
                        'tai_xe_id', x.tai_xe_id, 'dang_dung', x.dang_dung) ORDER BY x.thue_ngoai, x.bien_so), '[]'::jsonb) FROM doixe.xe x)),
        'thang_co', (SELECT jsonb_agg(m ORDER BY m) FROM t),
        'khoa', (SELECT jsonb_object_agg(m::text, doixe._khoa(m)) FROM t))
$$;

-- ---------------------------------------------------------------------------------------------------------------------------
-- Hàm đọc (cấp cho sokhach_app).
CREATE OR REPLACE FUNCTION doixe.get_tong(p_thang date) RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = pg_catalog, doixe, pg_temp AS $$
-- Màn Đội xe: người nhận ứng (số dư hôm nay, số dòng chưa hoàn) và xe (chặng, chặng chưa có phí của tháng chọn).
DECLARE d date := doixe._hom_nay(); m date;
BEGIN
    PERFORM doixe._actor();
    m := coalesce(p_thang, date_trunc('month', d)::date);
    IF date_trunc('month', m)::date <> m OR m > d THEN RAISE EXCEPTION 'INVALID_MONTH'; END IF;
    RETURN jsonb_build_object('hom_nay', d, 'thang', m) || doixe._chung() || jsonb_build_object(
        'nguoi', (SELECT coalesce(jsonb_agg(jsonb_build_object('id', n.id, 'ten', n.ten, 'vai', n.vai,
                    'xe_id', (SELECT x.id FROM doixe.xe x WHERE x.tai_xe_id = n.id ORDER BY x.thue_ngoai, x.bien_so LIMIT 1),
                    'so_du_vnd', doixe._so_du(n.id)::text,
                    'chua_hoan', (SELECT count(*) FROM doixe.dong dd JOIN doixe.chang c ON c.id = dd.chang_id
                                   WHERE c.nguoi_tra_id = n.id AND NOT c.da_xoa AND dd.dot_hoan_id IS NULL
                                     AND coalesce(doixe._tien_dong(dd.id), 0) <> 0)) ORDER BY n.id), '[]'::jsonb)
                  FROM doixe.nguoi n WHERE n.dang_dung),
        'xe', (SELECT coalesce(jsonb_agg(jsonb_build_object('id', x.id, 'bien_so', x.bien_so, 'nhom', x.nhom, 'thue_ngoai', x.thue_ngoai,
                    'tai_xe_id', x.tai_xe_id,
                    'chang', (SELECT count(*) FROM doixe.chang c WHERE c.xe_id = x.id AND NOT c.da_xoa AND NOT c.da_bo
                               AND date_trunc('month', c.ngay)::date = m),
                    'chua_phi', (SELECT count(*) FROM doixe.chang c WHERE c.xe_id = x.id AND NOT c.da_xoa AND NOT c.da_bo
                                  AND date_trunc('month', c.ngay)::date = m
                                  AND NOT EXISTS (SELECT 1 FROM doixe.dong dd JOIN doixe.dong_phi f ON f.dong_id = dd.id WHERE dd.chang_id = c.id)))
                  ORDER BY x.thue_ngoai, x.bien_so), '[]'::jsonb) FROM doixe.xe x WHERE x.dang_dung));
END $$;

CREATE OR REPLACE FUNCTION doixe.get_so(p_loai text, p_id bigint, p_thang date) RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = pg_catalog, doixe, pg_temp AS $$
-- Sổ người (thẻ tiền tháng, ứng, đợt hoàn, chặng người đó lái hoặc trả, dòng chưa hoàn mọi tháng) hoặc sổ xe (mọi chặng của xe).
DECLARE d date := doixe._hom_nay(); m date; m2 date; n doixe.nguoi; x doixe.xe; v_ids bigint[]; r jsonb;
        v_dau bigint; v_chi bigint; v_hoan bigint; v_ung bigint;
BEGIN
    PERFORM doixe._actor();
    m := coalesce(p_thang, date_trunc('month', d)::date);
    IF date_trunc('month', m)::date <> m OR m > d THEN RAISE EXCEPTION 'INVALID_MONTH'; END IF;
    m2 := (m + interval '1 month')::date;
    r := jsonb_build_object('hom_nay', d, 'thang', m, 'loai', p_loai) || doixe._chung();
    IF p_loai = 'nguoi' THEN
        SELECT * INTO n FROM doixe.nguoi WHERE id = p_id;
        IF NOT FOUND THEN RAISE EXCEPTION 'NGUOI_NOT_FOUND'; END IF;
        SELECT array_agg(c.id) INTO v_ids FROM doixe.chang c
         WHERE NOT c.da_xoa AND c.ngay >= m AND c.ngay < m2 AND (c.tai_xe_id = n.id OR c.nguoi_tra_id = n.id);
        v_dau := doixe._so_du(n.id, m);
        SELECT coalesce(sum(f.so_tien_vnd), 0)::bigint INTO v_chi FROM doixe.chang c JOIN doixe.dong dd ON dd.chang_id = c.id
          JOIN doixe.dong_phi f ON f.dong_id = dd.id JOIN doixe.loai_phi l ON l.ma = f.loai_phi
         WHERE c.nguoi_tra_id = n.id AND NOT c.da_xoa AND NOT l.cong_ty_tra AND c.ngay >= m AND c.ngay < m2;
        SELECT coalesce(sum(h.so_tien_vnd), 0)::bigint INTO v_hoan FROM doixe.dot_hoan h
         WHERE h.nguoi_id = n.id AND h.huy_luc IS NULL AND h.ngay >= m AND h.ngay < m2;
        SELECT coalesce(sum(u.so_tien_vnd), 0)::bigint INTO v_ung FROM doixe.ung u
         WHERE u.nguoi_id = n.id AND u.huy_luc IS NULL AND u.ngay >= m AND u.ngay < m2;
        r := r || jsonb_build_object(
            'nguoi', jsonb_build_object('id', n.id, 'ten', n.ten, 'vai', n.vai,
                'xe_id', (SELECT xx.id FROM doixe.xe xx WHERE xx.tai_xe_id = n.id ORDER BY xx.thue_ngoai, xx.bien_so LIMIT 1)),
            'so_du_vnd', doixe._so_du(n.id)::text,
            'the', jsonb_build_object('dau_vnd', v_dau::text, 'chi_vnd', v_chi::text, 'hoan_vnd', v_hoan::text, 'ung_vnd', v_ung::text,
                                      'cuoi_vnd', (v_dau + v_chi - v_hoan - v_ung)::text),
            'ung', (SELECT coalesce(jsonb_agg(jsonb_build_object('id', u.id, 'ngay', u.ngay, 'so_tien_vnd', u.so_tien_vnd::text,
                        'ghi_chu', u.ghi_chu, 'actor', u.actor, 'luc', doixe._luc(u.luc),
                        'huy', CASE WHEN u.huy_luc IS NULL THEN NULL
                                    ELSE jsonb_build_object('actor', u.huy_actor, 'luc', doixe._luc(u.huy_luc), 'ly_do', u.huy_ly_do) END)
                      ORDER BY u.ngay, u.id), '[]'::jsonb) FROM doixe.ung u WHERE u.nguoi_id = n.id AND u.ngay >= m AND u.ngay < m2),
            'dot', (SELECT coalesce(jsonb_agg(jsonb_build_object('id', h.id, 'ngay', h.ngay, 'so_tien_vnd', h.so_tien_vnd::text,
                        'tong_dong_vnd', h.tong_dong_vnd::text, 'so_dong', cardinality(h.dong_ids), 'actor', h.actor, 'luc', doixe._luc(h.luc),
                        'huy', CASE WHEN h.huy_luc IS NULL THEN NULL
                                    ELSE jsonb_build_object('actor', h.huy_actor, 'luc', doixe._luc(h.huy_luc), 'ly_do', h.huy_ly_do) END)
                      ORDER BY h.ngay, h.id), '[]'::jsonb) FROM doixe.dot_hoan h WHERE h.nguoi_id = n.id AND h.ngay >= m AND h.ngay < m2),
            'chang', doixe._chang_ds(coalesce(v_ids, '{}')),
            'chua_hoan', doixe._chang_ds(coalesce((SELECT array_agg(DISTINCT c.id) FROM doixe.chang c JOIN doixe.dong dd ON dd.chang_id = c.id
                WHERE c.nguoi_tra_id = n.id AND NOT c.da_xoa AND dd.dot_hoan_id IS NULL AND coalesce(doixe._tien_dong(dd.id), 0) <> 0), '{}')));
    ELSIF p_loai = 'xe' THEN
        SELECT * INTO x FROM doixe.xe WHERE id = p_id;
        IF NOT FOUND THEN RAISE EXCEPTION 'XE_NOT_FOUND'; END IF;
        SELECT array_agg(c.id) INTO v_ids FROM doixe.chang c WHERE NOT c.da_xoa AND c.xe_id = x.id AND c.ngay >= m AND c.ngay < m2;
        r := r || jsonb_build_object(
            'xe', jsonb_build_object('id', x.id, 'bien_so', x.bien_so, 'nhom', x.nhom, 'thue_ngoai', x.thue_ngoai, 'tai_xe_id', x.tai_xe_id),
            'chang', doixe._chang_ds(coalesce(v_ids, '{}')));
    ELSE
        RAISE EXCEPTION 'INVALID_COMMAND';
    END IF;
    RETURN r;
END $$;

CREATE OR REPLACE FUNCTION doixe.get_lich_su(p_nguoi bigint, p_xe bigint) RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = pg_catalog, doixe, pg_temp AS $$
-- Lịch sử: cả đội (không tham số), việc của một người (người trả, tài xế của chặng, người trả mới), hoặc của một xe.
-- Khóa/mở tháng hiện ở mọi nơi. 500 việc mới nhất.
BEGIN
    PERFORM doixe._actor();
    IF p_nguoi IS NOT NULL AND p_xe IS NOT NULL THEN RAISE EXCEPTION 'INVALID_COMMAND'; END IF;
    RETURN jsonb_build_object('events', (SELECT coalesce(jsonb_agg(jsonb_build_object('id', e.id, 'viec', e.viec, 'actor', e.actor,
            'luc', doixe._luc(e.luc), 'nguoi_id', e.nguoi_id, 'tai_xe_id', e.tai_xe_id, 'xe_id', e.xe_id, 'truoc', e.truoc, 'sau', e.sau,
            'ly_do', e.ly_do) ORDER BY e.id DESC), '[]'::jsonb)
        FROM (SELECT * FROM doixe.su_kien s
               WHERE (p_nguoi IS NULL AND p_xe IS NULL) OR s.viec = 'khoa_thang'
                  OR (p_nguoi IS NOT NULL AND (s.nguoi_id = p_nguoi OR s.tai_xe_id = p_nguoi OR (s.sau ->> 'nguoi_tra_id') = p_nguoi::text))
                  OR (p_xe IS NOT NULL AND s.xe_id = p_xe)
               ORDER BY s.id DESC LIMIT 500) e));
END $$;

-- ---------------------------------------------------------------------------------------------------------------------------
-- Lệnh ghi (cấp cho sokhach_app). Lỗi theo từng dòng của lưu chặng trả trong kết quả, không ghi gì; lỗi khác RAISE mã.
CREATE OR REPLACE FUNCTION doixe.luu_chang(p jsonb) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, doixe, pg_temp AS $$
-- Lưu các dòng nháp hết lỗi thành chặng (mỗi chặng một dòng gốc). Chặn: thiếu ngày/container, ngày sau hôm nay, xe không rõ, trùng
-- chặng (ngày + container + loại + xe, kể cả trong cùng lệnh). Có lỗi thì trả {ok:false, loi:[{i,cot,ma}]} và không ghi gì.
-- Chặng hàng trống nơi lấy và nơi hạ thì lấy tuyến của chuyến khách đã nối. Thêm vào tháng khóa thì gắn sau_khoa.
DECLARE v_retry jsonb; v_rows jsonb; v_row jsonb; i integer; d date := doixe._hom_nay();
        v_loi jsonb := '[]'::jsonb; v_keys text[] := '{}'; v_key text;
        v_ngay date; v_cont text; v_loai text; v_xe bigint; v_tx bigint; v_tra text; v_ntra bigint; v_phi jsonb; v_ma text;
        v_id bigint; v_dong bigint; v_ids bigint[] := '{}'; v_lay text; v_ha text; v_ch jsonb; v_amt bigint; g record;
BEGIN
    v_retry := doixe._bat_dau(p, 'luu_chang');
    IF v_retry IS NOT NULL THEN RETURN v_retry; END IF;
    PERFORM doixe._chi_khoa(p, ARRAY['idempotency_key', 'rows']);
    v_rows := p -> 'rows';
    IF jsonb_typeof(v_rows) IS DISTINCT FROM 'array' OR jsonb_array_length(v_rows) NOT BETWEEN 1 AND 200 THEN
        RAISE EXCEPTION 'INVALID_COMMAND';
    END IF;
    FOR i IN 0 .. jsonb_array_length(v_rows) - 1 LOOP
        v_row := v_rows -> i;
        PERFORM doixe._chi_khoa(v_row, ARRAY['ngay', 'container', 'loai', 'xe_id', 'tai_xe_id', 'tra', 'nguoi_tra_id', 'noi_lay', 'noi_ha',
                                              'kho', 'tinh', 'ten_hang', 'ghi_chu', 'phi']);
        v_ngay := doixe._ngay(v_row -> 'ngay');
        v_cont := nullif(sokhach._normalize_key(doixe._chu(v_row -> 'container', 40)), '');
        v_loai := v_row ->> 'loai';
        IF v_loai IS NULL OR v_loai NOT IN ('hang', 'chuyen_cang', 'tra_rong', 'rut_mooc', 'tha_mooc', 'khac') THEN
            RAISE EXCEPTION 'INVALID_COMMAND';
        END IF;
        v_xe := doixe._id(v_row, 'xe_id', true);
        v_tx := doixe._id(v_row, 'tai_xe_id', true);
        v_tra := v_row ->> 'tra';
        v_ntra := doixe._id(v_row, 'nguoi_tra_id', true);
        IF v_tra IS NULL OR v_tra NOT IN ('nguoi', 'cong_ty') OR (v_tra = 'nguoi') <> (v_ntra IS NOT NULL)
           OR (v_ntra IS NOT NULL AND NOT EXISTS (SELECT 1 FROM doixe.nguoi WHERE id = v_ntra))
           OR (v_tx IS NOT NULL AND NOT EXISTS (SELECT 1 FROM doixe.nguoi WHERE id = v_tx)) THEN
            RAISE EXCEPTION 'INVALID_COMMAND';
        END IF;
        v_phi := coalesce(v_row -> 'phi', '{}'::jsonb);
        IF jsonb_typeof(v_phi) <> 'object' OR EXISTS (SELECT 1 FROM jsonb_object_keys(v_phi) k
                                                      WHERE NOT EXISTS (SELECT 1 FROM doixe.loai_phi l WHERE l.ma = k)) THEN
            RAISE EXCEPTION 'INVALID_COMMAND';
        END IF;
        FOR v_ma IN SELECT jsonb_object_keys(v_phi) LOOP
            PERFORM doixe._vnd(v_phi -> v_ma);
        END LOOP;
        PERFORM doixe._chu(v_row -> k, 200) FROM unnest(ARRAY['noi_lay', 'noi_ha', 'kho', 'tinh', 'ten_hang', 'ghi_chu']) k;
        IF v_cont IS NOT NULL AND char_length(v_cont) > 20 THEN RAISE EXCEPTION 'INVALID_COMMAND'; END IF;
        IF v_ngay IS NULL THEN
            v_loi := v_loi || jsonb_build_object('i', i, 'cot', 'ngay', 'ma', 'NGAY_THIEU');
        ELSIF v_ngay > d THEN
            v_loi := v_loi || jsonb_build_object('i', i, 'cot', 'ngay', 'ma', 'NGAY_TUONG_LAI');
        END IF;
        IF v_cont IS NULL THEN v_loi := v_loi || jsonb_build_object('i', i, 'cot', 'container', 'ma', 'CONT_THIEU'); END IF;
        IF v_xe IS NULL OR NOT EXISTS (SELECT 1 FROM doixe.xe WHERE id = v_xe AND dang_dung) THEN
            v_loi := v_loi || jsonb_build_object('i', i, 'cot', 'xe_id', 'ma', 'XE_KHONG_RO');
        ELSIF v_ngay IS NOT NULL AND v_cont IS NOT NULL THEN
            v_key := v_ngay || '|' || v_cont || '|' || v_loai || '|' || v_xe;
            IF v_key = ANY (v_keys) OR EXISTS (SELECT 1 FROM doixe.chang c WHERE NOT c.da_xoa AND c.ngay = v_ngay
                                                 AND c.container = v_cont AND c.loai = v_loai AND c.xe_id = v_xe) THEN
                v_loi := v_loi || jsonb_build_object('i', i, 'cot', 'container', 'ma', 'TRUNG_CHANG');
            END IF;
            v_keys := v_keys || v_key;
        END IF;
    END LOOP;
    IF jsonb_array_length(v_loi) > 0 THEN
        RETURN jsonb_build_object('ok', false, 'loi', v_loi);
    END IF;
    FOR i IN 0 .. jsonb_array_length(v_rows) - 1 LOOP
        v_row := v_rows -> i;
        v_ngay := doixe._ngay(v_row -> 'ngay');
        v_cont := sokhach._normalize_key(doixe._chu(v_row -> 'container', 40));
        v_loai := v_row ->> 'loai';
        v_lay := doixe._chu(v_row -> 'noi_lay', 200);
        v_ha := doixe._chu(v_row -> 'noi_ha', 200);
        IF v_loai = 'hang' AND v_lay IS NULL AND v_ha IS NULL THEN
            v_ch := doixe._chuyen(v_cont, v_ngay);
            v_lay := left(nullif(btrim(v_ch ->> 'tu'), ''), 200);
            v_ha := left(nullif(btrim(v_ch ->> 'den'), ''), 200);
        END IF;
        INSERT INTO doixe.chang(ngay, container, loai, xe_id, tai_xe_id, tra, nguoi_tra_id, noi_lay, noi_ha, kho, tinh, ten_hang, ghi_chu,
                                sau_khoa, actor)
        VALUES (v_ngay, v_cont, v_loai, doixe._id(v_row, 'xe_id'), doixe._id(v_row, 'tai_xe_id', true), v_row ->> 'tra',
                doixe._id(v_row, 'nguoi_tra_id', true), v_lay, v_ha, doixe._chu(v_row -> 'kho', 200), doixe._chu(v_row -> 'tinh', 200),
                doixe._chu(v_row -> 'ten_hang', 200), doixe._chu(v_row -> 'ghi_chu', 200), doixe._khoa(v_ngay), doixe._actor())
        RETURNING id INTO v_id;
        INSERT INTO doixe.dong(chang_id, loai, actor) VALUES (v_id, 'goc', doixe._actor()) RETURNING id INTO v_dong;
        v_phi := coalesce(v_row -> 'phi', '{}'::jsonb);
        FOR v_ma IN SELECT jsonb_object_keys(v_phi) LOOP
            v_amt := doixe._vnd(v_phi -> v_ma);
            IF v_amt IS NOT NULL THEN
                INSERT INTO doixe.dong_phi(dong_id, loai_phi, so_tien_vnd) VALUES (v_dong, v_ma, v_amt);
            END IF;
        END LOOP;
        v_ids := v_ids || v_id;
    END LOOP;
    FOR g IN SELECT c.nguoi_tra_id, c.tai_xe_id, c.xe_id, count(*) AS n, min(c.ngay) AS tu, max(c.ngay) AS den,
                    array_agg(c.id ORDER BY c.id) AS ids, coalesce(sum(doixe._tien_dong(dd.id)), 0)::bigint AS tien,
                    count(*) FILTER (WHERE c.sau_khoa) AS sk
               FROM doixe.chang c JOIN doixe.dong dd ON dd.chang_id = c.id AND dd.loai = 'goc'
              WHERE c.id = ANY (v_ids) GROUP BY c.nguoi_tra_id, c.tai_xe_id, c.xe_id
              ORDER BY c.nguoi_tra_id NULLS FIRST, c.tai_xe_id NULLS FIRST, c.xe_id LOOP
        PERFORM doixe._ghi('them_chang', g.nguoi_tra_id, g.tai_xe_id, g.xe_id, '{}'::jsonb,
            jsonb_build_object('so_dong', g.n, 'tu', g.tu, 'den', g.den, 'tien_vnd', g.tien::text, 'chang_ids', to_jsonb(g.ids), 'sau_khoa', g.sk),
            NULL, p ->> 'idempotency_key');
    END LOOP;
    RETURN doixe._xong(p, 'luu_chang', jsonb_build_object('ok', true, 'so_dong', cardinality(v_ids), 'chang_ids', to_jsonb(v_ids),
        'sau_khoa', (SELECT count(*) FROM doixe.chang WHERE id = ANY (v_ids) AND sau_khoa)));
END $$;

CREATE OR REPLACE FUNCTION doixe.sua_chang(p jsonb) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, doixe, pg_temp AS $$
-- Sửa một ô của chặng. `truoc` là giá trị máy người sửa đang thấy: khác giá trị hiện tại thì CHANGED (tải lại rồi sửa).
-- Tiền (cot 'phi:<mã>'): tháng mở, dòng gốc chưa hoàn (hoặc phí công ty trả) và chưa có điều chỉnh cho phí đó thì ghi đè;
-- còn lại thêm dòng điều chỉnh bằng hiệu số (số cũ giữ nguyên). Chữ (ngày, container, loại, xe, nơi, kho, ghi chú) ghi đè;
-- không chuyển chặng vào/ra tháng khóa; không trùng chặng. Người trả: không đổi khi tháng khóa hoặc có dòng đã hoàn.
DECLARE v_retry jsonb; c doixe.chang; v_cot text; v_truoc jsonb; v_gia jsonb; d date := doixe._hom_nay();
        v_khoa boolean; v_hoan boolean; v_old text; v_new text; v_date date; v_desc jsonb;
        v_ma text; v_cong_ty boolean; v_hien bigint; v_moi bigint; v_chenh bigint; v_goc bigint; v_goc_hoan boolean; v_co_dc boolean;
        v_dong bigint; v_sd0 bigint; v_ly text; v_new_id bigint; v_nguoi bigint;
BEGIN
    v_retry := doixe._bat_dau(p, 'sua_chang');
    IF v_retry IS NOT NULL THEN RETURN v_retry; END IF;
    PERFORM doixe._chi_khoa(p, ARRAY['idempotency_key', 'chang_id', 'cot', 'truoc', 'gia_tri']);
    IF NOT (p ? 'truoc' AND p ? 'gia_tri') OR jsonb_typeof(p -> 'cot') IS DISTINCT FROM 'string' THEN RAISE EXCEPTION 'INVALID_COMMAND'; END IF;
    v_cot := p ->> 'cot'; v_truoc := p -> 'truoc'; v_gia := p -> 'gia_tri';
    SELECT * INTO c FROM doixe.chang WHERE id = doixe._id(p, 'chang_id') FOR UPDATE;
    IF NOT FOUND OR c.da_xoa THEN RAISE EXCEPTION 'CHANG_NOT_FOUND'; END IF;
    IF c.da_bo THEN RAISE EXCEPTION 'CHANG_DA_BO'; END IF;
    v_khoa := doixe._khoa(c.ngay);
    v_hoan := EXISTS (SELECT 1 FROM doixe.dong WHERE chang_id = c.id AND dot_hoan_id IS NOT NULL);
    v_desc := jsonb_build_object('chang_id', c.id, 'ngay', c.ngay, 'container', c.container);
    IF v_cot LIKE 'phi:%' THEN
        v_ma := substr(v_cot, 5);
        SELECT l.cong_ty_tra INTO v_cong_ty FROM doixe.loai_phi l WHERE l.ma = v_ma;
        IF NOT FOUND THEN RAISE EXCEPTION 'INVALID_COMMAND'; END IF;
        SELECT sum(f.so_tien_vnd)::bigint INTO v_hien FROM doixe.dong dd JOIN doixe.dong_phi f ON f.dong_id = dd.id AND f.loai_phi = v_ma
         WHERE dd.chang_id = c.id;
        IF doixe._vnd_co_dau(v_truoc) IS DISTINCT FROM v_hien THEN RAISE EXCEPTION 'CHANGED'; END IF;
        v_moi := doixe._vnd(v_gia);
        IF v_moi IS NOT DISTINCT FROM v_hien THEN
            RETURN doixe._xong(p, 'sua_chang', jsonb_build_object('ok', true, 'khong_doi', true));
        END IF;
        SELECT dd.id, dd.dot_hoan_id IS NOT NULL INTO v_goc, v_goc_hoan FROM doixe.dong dd WHERE dd.chang_id = c.id AND dd.loai = 'goc';
        v_co_dc := EXISTS (SELECT 1 FROM doixe.dong dd JOIN doixe.dong_phi f ON f.dong_id = dd.id AND f.loai_phi = v_ma
                            WHERE dd.chang_id = c.id AND dd.loai <> 'goc');
        v_nguoi := CASE WHEN NOT v_cong_ty THEN c.nguoi_tra_id END;
        v_sd0 := CASE WHEN v_nguoi IS NOT NULL THEN doixe._so_du(v_nguoi) END;
        IF v_khoa OR (v_goc_hoan AND NOT v_cong_ty) OR v_co_dc THEN
            v_chenh := coalesce(v_moi, 0) - coalesce(v_hien, 0);
            IF v_chenh = 0 THEN
                RETURN doixe._xong(p, 'sua_chang', jsonb_build_object('ok', true, 'khong_doi', true));
            END IF;
            v_ly := CASE WHEN v_khoa THEN 'thang_khoa' WHEN v_goc_hoan AND NOT v_cong_ty THEN 'da_hoan' ELSE 'co_dieu_chinh' END;
            INSERT INTO doixe.dong(chang_id, loai, dc_phi, dc_truoc_vnd, dc_sau_vnd, actor)
            VALUES (c.id, 'dieu_chinh', v_ma, v_hien, v_moi, doixe._actor()) RETURNING id INTO v_dong;
            INSERT INTO doixe.dong_phi(dong_id, loai_phi, so_tien_vnd) VALUES (v_dong, v_ma, v_chenh);
            PERFORM doixe._ghi('dieu_chinh', c.nguoi_tra_id, c.tai_xe_id, c.xe_id,
                v_desc || jsonb_build_object('cot', v_cot, 'gia_tri', v_hien::text, 'so_du_vnd', v_sd0::text),
                jsonb_build_object('gia_tri', v_moi::text, 'chenh_vnd', v_chenh::text, 'ly_do_dc', v_ly, 'dong_id', v_dong,
                                   'so_du_vnd', (CASE WHEN v_nguoi IS NOT NULL THEN doixe._so_du(v_nguoi) END)::text),
                NULL, p ->> 'idempotency_key');
            RETURN doixe._xong(p, 'sua_chang', jsonb_build_object('ok', true, 'cach', 'dieu_chinh', 'ly_do_dc', v_ly, 'dong_id', v_dong,
                                                                   'chenh_vnd', v_chenh::text));
        END IF;
        IF v_moi IS NULL THEN
            DELETE FROM doixe.dong_phi WHERE dong_id = v_goc AND loai_phi = v_ma;
        ELSE
            INSERT INTO doixe.dong_phi(dong_id, loai_phi, so_tien_vnd) VALUES (v_goc, v_ma, v_moi)
            ON CONFLICT (dong_id, loai_phi) DO UPDATE SET so_tien_vnd = EXCLUDED.so_tien_vnd;
        END IF;
        PERFORM doixe._ghi('sua_chang', c.nguoi_tra_id, c.tai_xe_id, c.xe_id,
            v_desc || jsonb_build_object('cot', v_cot, 'gia_tri', v_hien::text, 'so_du_vnd', v_sd0::text),
            jsonb_build_object('cot', v_cot, 'gia_tri', v_moi::text,
                               'so_du_vnd', (CASE WHEN v_nguoi IS NOT NULL THEN doixe._so_du(v_nguoi) END)::text),
            NULL, p ->> 'idempotency_key');
        RETURN doixe._xong(p, 'sua_chang', jsonb_build_object('ok', true, 'cach', 'ghi_de'));
    ELSIF v_cot IN ('ngay', 'container', 'loai', 'xe_id', 'noi_lay', 'noi_ha', 'kho', 'ghi_chu') THEN
        v_old := CASE v_cot WHEN 'ngay' THEN c.ngay::text WHEN 'container' THEN c.container WHEN 'loai' THEN c.loai
                            WHEN 'xe_id' THEN c.xe_id::text WHEN 'noi_lay' THEN c.noi_lay WHEN 'noi_ha' THEN c.noi_ha
                            WHEN 'kho' THEN c.kho ELSE c.ghi_chu END;
        IF v_truoc IS NULL OR jsonb_typeof(v_truoc) NOT IN ('string', 'null') THEN RAISE EXCEPTION 'INVALID_COMMAND'; END IF;
        IF (v_truoc #>> '{}') IS DISTINCT FROM v_old THEN RAISE EXCEPTION 'CHANGED'; END IF;
        IF v_cot = 'ngay' THEN
            v_date := doixe._ngay(v_gia);
            IF v_date IS NULL THEN RAISE EXCEPTION 'INVALID_DATE'; END IF;
            IF v_date > d THEN RAISE EXCEPTION 'NGAY_TUONG_LAI'; END IF;
            IF date_trunc('month', v_date) <> date_trunc('month', c.ngay) AND (v_khoa OR doixe._khoa(v_date)) THEN
                RAISE EXCEPTION 'THANG_KHOA_CHUYEN';
            END IF;
            v_new := v_date::text;
        ELSIF v_cot = 'container' THEN
            v_new := nullif(sokhach._normalize_key(doixe._chu(v_gia, 40)), '');
            IF v_new IS NULL THEN RAISE EXCEPTION 'CONT_THIEU'; END IF;
            IF char_length(v_new) > 20 THEN RAISE EXCEPTION 'INVALID_COMMAND'; END IF;
        ELSIF v_cot = 'loai' THEN
            v_new := v_gia #>> '{}';
            IF jsonb_typeof(v_gia) IS DISTINCT FROM 'string' OR v_new NOT IN ('hang', 'chuyen_cang', 'tra_rong', 'rut_mooc', 'tha_mooc', 'khac') THEN
                RAISE EXCEPTION 'INVALID_COMMAND';
            END IF;
        ELSIF v_cot = 'xe_id' THEN
            v_new := v_gia #>> '{}';
            IF jsonb_typeof(v_gia) IS DISTINCT FROM 'string' OR v_new !~ '^[1-9][0-9]{0,17}$'
               OR NOT EXISTS (SELECT 1 FROM doixe.xe WHERE id = v_new::bigint AND dang_dung) THEN
                RAISE EXCEPTION 'XE_KHONG_RO';
            END IF;
        ELSE
            v_new := doixe._chu(v_gia, 200);
        END IF;
        IF v_new IS NOT DISTINCT FROM v_old THEN
            RETURN doixe._xong(p, 'sua_chang', jsonb_build_object('ok', true, 'khong_doi', true));
        END IF;
        IF v_cot IN ('ngay', 'container', 'loai', 'xe_id') AND EXISTS (
            SELECT 1 FROM doixe.chang o WHERE o.id <> c.id AND NOT o.da_xoa
               AND o.ngay = CASE WHEN v_cot = 'ngay' THEN v_new::date ELSE c.ngay END
               AND o.container = CASE WHEN v_cot = 'container' THEN v_new ELSE c.container END
               AND o.loai = CASE WHEN v_cot = 'loai' THEN v_new ELSE c.loai END
               AND o.xe_id = CASE WHEN v_cot = 'xe_id' THEN v_new::bigint ELSE c.xe_id END) THEN
            RAISE EXCEPTION 'TRUNG_CHANG';
        END IF;
        UPDATE doixe.chang SET
            ngay = CASE WHEN v_cot = 'ngay' THEN v_new::date ELSE ngay END,
            container = CASE WHEN v_cot = 'container' THEN v_new ELSE container END,
            loai = CASE WHEN v_cot = 'loai' THEN v_new ELSE loai END,
            xe_id = CASE WHEN v_cot = 'xe_id' THEN v_new::bigint ELSE xe_id END,
            noi_lay = CASE WHEN v_cot = 'noi_lay' THEN v_new ELSE noi_lay END,
            noi_ha = CASE WHEN v_cot = 'noi_ha' THEN v_new ELSE noi_ha END,
            kho = CASE WHEN v_cot = 'kho' THEN v_new ELSE kho END,
            ghi_chu = CASE WHEN v_cot = 'ghi_chu' THEN v_new ELSE ghi_chu END
        WHERE id = c.id;
        PERFORM doixe._ghi('sua_chang', c.nguoi_tra_id, c.tai_xe_id,
            CASE WHEN v_cot = 'xe_id' THEN v_new::bigint ELSE c.xe_id END,
            v_desc || jsonb_build_object('cot', v_cot, 'gia_tri', v_old), jsonb_build_object('cot', v_cot, 'gia_tri', v_new),
            NULL, p ->> 'idempotency_key');
        RETURN doixe._xong(p, 'sua_chang', jsonb_build_object('ok', true, 'cach', 'ghi_de'));
    ELSIF v_cot = 'nguoi_tra' THEN
        v_old := CASE WHEN c.tra = 'cong_ty' THEN 'cong_ty' ELSE c.nguoi_tra_id::text END;
        IF jsonb_typeof(v_truoc) IS DISTINCT FROM 'string' OR (v_truoc #>> '{}') <> v_old THEN RAISE EXCEPTION 'CHANGED'; END IF;
        v_new := v_gia #>> '{}';
        IF jsonb_typeof(v_gia) IS DISTINCT FROM 'string' OR NOT (v_new = 'cong_ty' OR (v_new ~ '^[1-9][0-9]{0,17}$'
                AND EXISTS (SELECT 1 FROM doixe.nguoi WHERE id = v_new::bigint))) THEN
            RAISE EXCEPTION 'INVALID_COMMAND';
        END IF;
        IF v_new = v_old THEN
            RETURN doixe._xong(p, 'sua_chang', jsonb_build_object('ok', true, 'khong_doi', true));
        END IF;
        IF v_khoa OR v_hoan THEN RAISE EXCEPTION 'KHONG_DOI_NGUOI_TRA'; END IF;
        v_new_id := CASE WHEN v_new = 'cong_ty' THEN NULL ELSE v_new::bigint END;
        UPDATE doixe.chang SET tra = CASE WHEN v_new_id IS NULL THEN 'cong_ty' ELSE 'nguoi' END, nguoi_tra_id = v_new_id WHERE id = c.id;
        PERFORM doixe._ghi('doi_nguoi_tra', c.nguoi_tra_id, c.tai_xe_id, c.xe_id,
            v_desc || jsonb_build_object('nguoi_tra', v_old), jsonb_build_object('nguoi_tra', v_new, 'nguoi_tra_id', v_new_id),
            NULL, p ->> 'idempotency_key');
        RETURN doixe._xong(p, 'sua_chang', jsonb_build_object('ok', true, 'cach', 'ghi_de'));
    END IF;
    RAISE EXCEPTION 'INVALID_COMMAND';
END $$;

CREATE OR REPLACE FUNCTION doixe.xoa_chang(p jsonb) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, doixe, pg_temp AS $$
-- Tháng mở và chưa dòng nào hoàn: ẩn chặng (da_xoa), Lịch sử giữ bản trước. Tháng khóa hoặc có dòng đã hoàn: gạch ngang (da_bo)
-- và thêm dòng trừ lại đúng tổng từng loại phí của chặng, để số dư không đổi ngầm.
DECLARE v_retry jsonb; c doixe.chang; v_tien bigint; v_sd0 bigint; v_dong bigint; v_desc jsonb; v_cach text;
BEGIN
    v_retry := doixe._bat_dau(p, 'xoa_chang');
    IF v_retry IS NOT NULL THEN RETURN v_retry; END IF;
    PERFORM doixe._chi_khoa(p, ARRAY['idempotency_key', 'chang_id']);
    SELECT * INTO c FROM doixe.chang WHERE id = doixe._id(p, 'chang_id') FOR UPDATE;
    IF NOT FOUND OR c.da_xoa THEN RAISE EXCEPTION 'CHANG_NOT_FOUND'; END IF;
    IF c.da_bo THEN RAISE EXCEPTION 'CHANG_DA_BO'; END IF;
    SELECT sum(f.so_tien_vnd)::bigint INTO v_tien FROM doixe.dong dd JOIN doixe.dong_phi f ON f.dong_id = dd.id
      JOIN doixe.loai_phi l ON l.ma = f.loai_phi WHERE dd.chang_id = c.id AND NOT l.cong_ty_tra;
    v_sd0 := CASE WHEN c.nguoi_tra_id IS NOT NULL THEN doixe._so_du(c.nguoi_tra_id) END;
    v_desc := jsonb_build_object('chang_id', c.id, 'ngay', c.ngay, 'container', c.container, 'loai', c.loai, 'tien_vnd', v_tien::text,
                                 'so_du_vnd', v_sd0::text);
    IF NOT doixe._khoa(c.ngay) AND NOT EXISTS (SELECT 1 FROM doixe.dong WHERE chang_id = c.id AND dot_hoan_id IS NOT NULL) THEN
        UPDATE doixe.chang SET da_xoa = true WHERE id = c.id;
        v_cach := 'xoa';
        PERFORM doixe._ghi('xoa_chang', c.nguoi_tra_id, c.tai_xe_id, c.xe_id, v_desc,
            jsonb_build_object('so_du_vnd', (CASE WHEN c.nguoi_tra_id IS NOT NULL THEN doixe._so_du(c.nguoi_tra_id) END)::text),
            NULL, p ->> 'idempotency_key');
    ELSE
        IF EXISTS (SELECT 1 FROM doixe.dong dd JOIN doixe.dong_phi f ON f.dong_id = dd.id WHERE dd.chang_id = c.id
                    GROUP BY f.loai_phi HAVING sum(f.so_tien_vnd) <> 0) THEN
            INSERT INTO doixe.dong(chang_id, loai, actor) VALUES (c.id, 'tru_lai', doixe._actor()) RETURNING id INTO v_dong;
            INSERT INTO doixe.dong_phi(dong_id, loai_phi, so_tien_vnd)
            SELECT v_dong, f.loai_phi, -sum(f.so_tien_vnd) FROM doixe.dong dd JOIN doixe.dong_phi f ON f.dong_id = dd.id
             WHERE dd.chang_id = c.id AND dd.id <> v_dong GROUP BY f.loai_phi HAVING sum(f.so_tien_vnd) <> 0;
        END IF;
        UPDATE doixe.chang SET da_bo = true WHERE id = c.id;
        v_cach := 'bo';
        PERFORM doixe._ghi('bo_chang', c.nguoi_tra_id, c.tai_xe_id, c.xe_id, v_desc,
            jsonb_build_object('dong_id', v_dong, 'ly_do_dc', CASE WHEN doixe._khoa(c.ngay) THEN 'thang_khoa' ELSE 'da_hoan' END,
                               'so_du_vnd', (CASE WHEN c.nguoi_tra_id IS NOT NULL THEN doixe._so_du(c.nguoi_tra_id) END)::text),
            NULL, p ->> 'idempotency_key');
    END IF;
    RETURN doixe._xong(p, 'xoa_chang', jsonb_build_object('ok', true, 'cach', v_cach));
END $$;

CREATE OR REPLACE FUNCTION doixe.ghi_ung(p jsonb) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, doixe, pg_temp AS $$
DECLARE v_retry jsonb; v_nguoi bigint; v_ngay date; v_tien bigint; v_ghi text; v_sd0 bigint; v_sd1 bigint; v_id bigint;
BEGIN
    v_retry := doixe._bat_dau(p, 'ghi_ung');
    IF v_retry IS NOT NULL THEN RETURN v_retry; END IF;
    PERFORM doixe._chi_khoa(p, ARRAY['idempotency_key', 'nguoi_id', 'ngay', 'so_tien_vnd', 'ghi_chu']);
    v_nguoi := doixe._id(p, 'nguoi_id');
    IF NOT EXISTS (SELECT 1 FROM doixe.nguoi WHERE id = v_nguoi) THEN RAISE EXCEPTION 'NGUOI_NOT_FOUND'; END IF;
    v_ngay := doixe._ngay(p -> 'ngay');
    IF v_ngay IS NULL THEN RAISE EXCEPTION 'INVALID_DATE'; END IF;
    IF v_ngay > doixe._hom_nay() THEN RAISE EXCEPTION 'NGAY_TUONG_LAI'; END IF;
    v_tien := doixe._vnd(p -> 'so_tien_vnd');
    IF v_tien IS NULL OR v_tien = 0 THEN RAISE EXCEPTION 'INVALID_VND'; END IF;
    v_ghi := doixe._chu(p -> 'ghi_chu', 500);
    v_sd0 := doixe._so_du(v_nguoi);
    INSERT INTO doixe.ung(nguoi_id, ngay, so_tien_vnd, ghi_chu, actor) VALUES (v_nguoi, v_ngay, v_tien, v_ghi, doixe._actor())
    RETURNING id INTO v_id;
    v_sd1 := doixe._so_du(v_nguoi);
    PERFORM doixe._ghi('ghi_ung', v_nguoi, NULL, NULL, jsonb_build_object('so_du_vnd', v_sd0::text),
        jsonb_build_object('ung_id', v_id, 'ngay', v_ngay, 'so_tien_vnd', v_tien::text, 'ghi_chu', v_ghi, 'so_du_vnd', v_sd1::text),
        NULL, p ->> 'idempotency_key');
    RETURN doixe._xong(p, 'ghi_ung', jsonb_build_object('ok', true, 'ung_id', v_id, 'so_du_truoc_vnd', v_sd0::text, 'so_du_sau_vnd', v_sd1::text));
END $$;

CREATE OR REPLACE FUNCTION doixe.huy_ung(p jsonb) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, doixe, pg_temp AS $$
DECLARE v_retry jsonb; u doixe.ung; v_ly text; v_sd0 bigint; v_sd1 bigint;
BEGIN
    v_retry := doixe._bat_dau(p, 'huy_ung');
    IF v_retry IS NOT NULL THEN RETURN v_retry; END IF;
    PERFORM doixe._chi_khoa(p, ARRAY['idempotency_key', 'ung_id', 'ly_do']);
    v_ly := doixe._chu(p -> 'ly_do', 500);
    IF v_ly IS NULL THEN RAISE EXCEPTION 'LY_DO_THIEU'; END IF;
    SELECT * INTO u FROM doixe.ung WHERE id = doixe._id(p, 'ung_id') FOR UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION 'UNG_NOT_FOUND'; END IF;
    IF u.huy_luc IS NOT NULL THEN RAISE EXCEPTION 'DA_HUY'; END IF;
    v_sd0 := doixe._so_du(u.nguoi_id);
    UPDATE doixe.ung SET huy_actor = doixe._actor(), huy_luc = clock_timestamp(), huy_ly_do = v_ly WHERE id = u.id;
    v_sd1 := doixe._so_du(u.nguoi_id);
    PERFORM doixe._ghi('huy_ung', u.nguoi_id, NULL, NULL,
        jsonb_build_object('ung_id', u.id, 'ngay', u.ngay, 'so_tien_vnd', u.so_tien_vnd::text, 'so_du_vnd', v_sd0::text),
        jsonb_build_object('so_du_vnd', v_sd1::text), v_ly, p ->> 'idempotency_key');
    RETURN doixe._xong(p, 'huy_ung', jsonb_build_object('ok', true, 'so_du_truoc_vnd', v_sd0::text, 'so_du_sau_vnd', v_sd1::text));
END $$;

CREATE OR REPLACE FUNCTION doixe.ghi_hoan(p jsonb) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, doixe, pg_temp AS $$
-- Đợt hoàn: các dòng của đúng người trả, chưa xóa, chưa hoàn, có tiền khác 0; dòng nào vừa đổi thì DONG_DA_DOI (tải lại, chọn lại).
-- Số tiền thực chuyển là số nguyên >= 0, có thể khác tổng các dòng; số dư vẫn theo công thức đã chốt.
DECLARE v_retry jsonb; v_nguoi bigint; v_ngay date; v_tien bigint; v_ids bigint[]; v_tong bigint; v_sd0 bigint; v_sd1 bigint; v_id bigint;
BEGIN
    v_retry := doixe._bat_dau(p, 'ghi_hoan');
    IF v_retry IS NOT NULL THEN RETURN v_retry; END IF;
    PERFORM doixe._chi_khoa(p, ARRAY['idempotency_key', 'nguoi_id', 'ngay', 'so_tien_vnd', 'dong_ids']);
    v_nguoi := doixe._id(p, 'nguoi_id');
    IF NOT EXISTS (SELECT 1 FROM doixe.nguoi WHERE id = v_nguoi) THEN RAISE EXCEPTION 'NGUOI_NOT_FOUND'; END IF;
    v_ngay := doixe._ngay(p -> 'ngay');
    IF v_ngay IS NULL THEN RAISE EXCEPTION 'INVALID_DATE'; END IF;
    IF v_ngay > doixe._hom_nay() THEN RAISE EXCEPTION 'NGAY_TUONG_LAI'; END IF;
    v_tien := doixe._vnd(p -> 'so_tien_vnd');
    IF v_tien IS NULL THEN RAISE EXCEPTION 'INVALID_VND'; END IF;
    IF jsonb_typeof(p -> 'dong_ids') IS DISTINCT FROM 'array' OR jsonb_array_length(p -> 'dong_ids') NOT BETWEEN 1 AND 2000
       OR EXISTS (SELECT 1 FROM jsonb_array_elements(p -> 'dong_ids') e WHERE jsonb_typeof(e) <> 'number' OR e::text !~ '^[1-9][0-9]{0,17}$') THEN
        RAISE EXCEPTION 'DONG_THIEU';
    END IF;
    SELECT array_agg(DISTINCT e::text::bigint ORDER BY e::text::bigint) INTO v_ids FROM jsonb_array_elements(p -> 'dong_ids') e;
    IF cardinality(v_ids) <> jsonb_array_length(p -> 'dong_ids') THEN RAISE EXCEPTION 'INVALID_COMMAND'; END IF;
    PERFORM 1 FROM doixe.dong WHERE id = ANY (v_ids) FOR UPDATE;
    IF (SELECT count(*) FROM doixe.dong dd JOIN doixe.chang c ON c.id = dd.chang_id
         WHERE dd.id = ANY (v_ids) AND c.nguoi_tra_id = v_nguoi AND NOT c.da_xoa AND dd.dot_hoan_id IS NULL
           AND coalesce(doixe._tien_dong(dd.id), 0) <> 0) <> cardinality(v_ids) THEN
        RAISE EXCEPTION 'DONG_DA_DOI';
    END IF;
    SELECT sum(doixe._tien_dong(id))::bigint INTO v_tong FROM doixe.dong WHERE id = ANY (v_ids);
    v_sd0 := doixe._so_du(v_nguoi);
    INSERT INTO doixe.dot_hoan(nguoi_id, ngay, so_tien_vnd, tong_dong_vnd, dong_ids, actor)
    VALUES (v_nguoi, v_ngay, v_tien, v_tong, v_ids, doixe._actor()) RETURNING id INTO v_id;
    UPDATE doixe.dong SET dot_hoan_id = v_id WHERE id = ANY (v_ids);
    v_sd1 := doixe._so_du(v_nguoi);
    PERFORM doixe._ghi('ghi_hoan', v_nguoi, NULL, NULL, jsonb_build_object('so_du_vnd', v_sd0::text),
        jsonb_build_object('dot_id', v_id, 'ngay', v_ngay, 'so_tien_vnd', v_tien::text, 'tong_dong_vnd', v_tong::text,
                           'so_dong', cardinality(v_ids), 'so_du_vnd', v_sd1::text),
        NULL, p ->> 'idempotency_key');
    RETURN doixe._xong(p, 'ghi_hoan', jsonb_build_object('ok', true, 'dot_id', v_id, 'tong_dong_vnd', v_tong::text,
        'so_du_truoc_vnd', v_sd0::text, 'so_du_sau_vnd', v_sd1::text));
END $$;

CREATE OR REPLACE FUNCTION doixe.huy_hoan(p jsonb) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, doixe, pg_temp AS $$
-- Hủy đợt hoàn bắt buộc lý do; các dòng của đợt trở lại chưa hoàn.
DECLARE v_retry jsonb; h doixe.dot_hoan; v_ly text; v_sd0 bigint; v_sd1 bigint; v_n integer;
BEGIN
    v_retry := doixe._bat_dau(p, 'huy_hoan');
    IF v_retry IS NOT NULL THEN RETURN v_retry; END IF;
    PERFORM doixe._chi_khoa(p, ARRAY['idempotency_key', 'dot_id', 'ly_do']);
    v_ly := doixe._chu(p -> 'ly_do', 500);
    IF v_ly IS NULL THEN RAISE EXCEPTION 'LY_DO_THIEU'; END IF;
    SELECT * INTO h FROM doixe.dot_hoan WHERE id = doixe._id(p, 'dot_id') FOR UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION 'DOT_NOT_FOUND'; END IF;
    IF h.huy_luc IS NOT NULL THEN RAISE EXCEPTION 'DA_HUY'; END IF;
    v_sd0 := doixe._so_du(h.nguoi_id);
    UPDATE doixe.dot_hoan SET huy_actor = doixe._actor(), huy_luc = clock_timestamp(), huy_ly_do = v_ly WHERE id = h.id;
    UPDATE doixe.dong SET dot_hoan_id = NULL WHERE dot_hoan_id = h.id;
    GET DIAGNOSTICS v_n = ROW_COUNT;
    v_sd1 := doixe._so_du(h.nguoi_id);
    PERFORM doixe._ghi('huy_hoan', h.nguoi_id, NULL, NULL,
        jsonb_build_object('dot_id', h.id, 'ngay', h.ngay, 'so_tien_vnd', h.so_tien_vnd::text, 'tong_dong_vnd', h.tong_dong_vnd::text,
                           'so_dong', cardinality(h.dong_ids), 'so_du_vnd', v_sd0::text),
        jsonb_build_object('dong_tro_lai', v_n, 'so_du_vnd', v_sd1::text), v_ly, p ->> 'idempotency_key');
    RETURN doixe._xong(p, 'huy_hoan', jsonb_build_object('ok', true, 'dong_tro_lai', v_n, 'so_du_truoc_vnd', v_sd0::text,
        'so_du_sau_vnd', v_sd1::text));
END $$;

CREATE OR REPLACE FUNCTION doixe.khoa_thang(p jsonb) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, doixe, pg_temp AS $$
-- Khóa hoặc mở một tháng cho cả đội xe; mỗi lần ghi Lịch sử trước → sau.
DECLARE v_retry jsonb; v_thang date; v_khoa boolean; v_truoc boolean;
BEGIN
    v_retry := doixe._bat_dau(p, 'khoa_thang');
    IF v_retry IS NOT NULL THEN RETURN v_retry; END IF;
    PERFORM doixe._chi_khoa(p, ARRAY['idempotency_key', 'thang', 'khoa']);
    v_thang := doixe._ngay(p -> 'thang');
    IF v_thang IS NULL OR extract(day FROM v_thang) <> 1 OR v_thang > doixe._hom_nay() THEN RAISE EXCEPTION 'INVALID_MONTH'; END IF;
    IF jsonb_typeof(p -> 'khoa') IS DISTINCT FROM 'boolean' THEN RAISE EXCEPTION 'INVALID_COMMAND'; END IF;
    v_khoa := (p ->> 'khoa')::boolean;
    v_truoc := doixe._khoa(v_thang);
    IF v_truoc = v_khoa THEN
        RETURN doixe._xong(p, 'khoa_thang', jsonb_build_object('ok', true, 'khong_doi', true));
    END IF;
    INSERT INTO doixe.thang_khoa(thang, khoa, actor) VALUES (v_thang, v_khoa, doixe._actor())
    ON CONFLICT (thang) DO UPDATE SET khoa = EXCLUDED.khoa, actor = EXCLUDED.actor, luc = clock_timestamp();
    PERFORM doixe._ghi('khoa_thang', NULL, NULL, NULL, jsonb_build_object('thang', v_thang, 'khoa', v_truoc),
                       jsonb_build_object('thang', v_thang, 'khoa', v_khoa), NULL, p ->> 'idempotency_key');
    RETURN doixe._xong(p, 'khoa_thang', jsonb_build_object('ok', true, 'khoa', v_khoa));
END $$;

-- Nạp danh mục người nhận ứng và xe (công cụ nạp, cần người dùng đồng ý trước mỗi lần chạy trên hao). Không cấp cho app.
CREATE OR REPLACE FUNCTION doixe.nap_danh_muc(p jsonb) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, doixe, pg_temp AS $$
DECLARE r jsonb; v_n integer := 0; v_x integer := 0;
BEGIN
    PERFORM doixe._actor();
    PERFORM pg_advisory_xact_lock(hashtext('doixe.ghi'));
    PERFORM doixe._chi_khoa(p, ARRAY['nguoi', 'xe']);
    FOR r IN SELECT * FROM jsonb_array_elements(coalesce(p -> 'nguoi', '[]'::jsonb)) LOOP
        PERFORM doixe._chi_khoa(r, ARRAY['ma', 'ten', 'vai', 'so_du_dau_vnd', 'dang_dung']);
        IF doixe._vnd_co_dau(r -> 'so_du_dau_vnd') IS NULL THEN RAISE EXCEPTION 'INVALID_VND'; END IF;
        INSERT INTO doixe.nguoi(ma_nguon, ten, vai, so_du_dau_vnd, dang_dung)
        VALUES (r ->> 'ma', doixe._chu(r -> 'ten', 100), r ->> 'vai', doixe._vnd_co_dau(r -> 'so_du_dau_vnd'),
                coalesce((r ->> 'dang_dung')::boolean, true))
        ON CONFLICT (ma_nguon) DO UPDATE SET ten = EXCLUDED.ten, vai = EXCLUDED.vai, so_du_dau_vnd = EXCLUDED.so_du_dau_vnd,
            dang_dung = EXCLUDED.dang_dung;
        v_n := v_n + 1;
    END LOOP;
    FOR r IN SELECT * FROM jsonb_array_elements(coalesce(p -> 'xe', '[]'::jsonb)) LOOP
        PERFORM doixe._chi_khoa(r, ARRAY['bien_so', 'nhom', 'thue_ngoai', 'tai_xe_ma', 'dang_dung']);
        IF r ->> 'tai_xe_ma' IS NOT NULL AND NOT EXISTS (SELECT 1 FROM doixe.nguoi WHERE ma_nguon = r ->> 'tai_xe_ma') THEN
            RAISE EXCEPTION 'NGUOI_NOT_FOUND';
        END IF;
        INSERT INTO doixe.xe(bien_so, nhom, thue_ngoai, tai_xe_id, dang_dung)
        VALUES (doixe._chu(r -> 'bien_so', 20), doixe._chu(r -> 'nhom', 50), coalesce((r ->> 'thue_ngoai')::boolean, false),
                (SELECT id FROM doixe.nguoi WHERE ma_nguon = r ->> 'tai_xe_ma'), coalesce((r ->> 'dang_dung')::boolean, true))
        ON CONFLICT (bien_key) DO UPDATE SET bien_so = EXCLUDED.bien_so, nhom = EXCLUDED.nhom, thue_ngoai = EXCLUDED.thue_ngoai,
            tai_xe_id = EXCLUDED.tai_xe_id, dang_dung = EXCLUDED.dang_dung;
        v_x := v_x + 1;
    END LOOP;
    PERFORM doixe._ghi('nap', NULL, NULL, NULL, '{}'::jsonb, jsonb_build_object('so_nguoi', v_n, 'so_xe', v_x), NULL, NULL);
    RETURN jsonb_build_object('ok', true, 'so_nguoi', v_n, 'so_xe', v_x);
END $$;

-- Quyền: chỉ hàm đọc và lệnh ghi; hàm phụ và nap_danh_muc không cấp cho ai. Không quyền trên bảng.
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA doixe FROM PUBLIC;
REVOKE ALL ON ALL TABLES IN SCHEMA doixe FROM PUBLIC;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA doixe FROM PUBLIC;
GRANT EXECUTE ON FUNCTION doixe.get_tong(date), doixe.get_so(text, bigint, date), doixe.get_lich_su(bigint, bigint),
    doixe.luu_chang(jsonb), doixe.sua_chang(jsonb), doixe.xoa_chang(jsonb), doixe.ghi_ung(jsonb), doixe.huy_ung(jsonb),
    doixe.ghi_hoan(jsonb), doixe.huy_hoan(jsonb), doixe.khoa_thang(jsonb) TO sokhach_app;
COMMIT;
