-- Đội xe đợt 2 (DOI-XE-THU-01, 18/11/2026; spec specs/doi-xe-thu-01.md): thu cước, bảng kê tháng gửi HTH, công nợ cước.
-- Nối vào schema `doixe` của đợt 1 (2026-11-18-v7-doi-xe.sql), áp sau file đó. Chỉ thêm bảng/hàm/cột; đổi hai ràng buộc của
-- Lịch sử (thêm loại việc thu) và thân get_lich_su (Lịch sử đội xe đợt 1 không lẫn việc thu). Không ghi `sokhach`. Chạy lại được.
--
-- Cách tính (ĐÃ CHỐT theo bản bấm thử, docs/decisions/doi-xe-thu-01.md):
-- * Bảng kê một tháng của một bên nhận (hiện chỉ HTH, chặng của xe công ty). Chưa gửi ("đang gom") thì web tính sống: cước theo
--   bảng giá tuyến có ngày áp dụng (rút/thả mooc 70% giá tuyến, làm tròn tới nghìn đồng) hoặc giá nhập tay của chặng; đóng ghép
--   và phát sinh đọc từ ghi chú của chặng dạng "_ Tên khoản số k". Chặng chưa có giá: ô cước trống (NULL), không tính.
-- * "Gửi bảng kê" chép từng dòng vào bang_ke_dong (đổi giá, sửa ghi chú sau đó không đổi bảng kê đã gửi). Đã gửi thì chỉ sửa
--   bằng điều chỉnh gắn từng dòng (lý do bắt buộc); "Đối chiếu xong" thì thôi nhận điều chỉnh, rồi mới ghi tiền HTH trả.
-- * Tiền về gắn bảng kê của tháng: trả thiếu ghi được, trả thừa bị chặn; hủy bắt buộc lý do.
-- * Công nợ cước = tổng bảng kê đã gửi + điều chỉnh − tiền về chưa hủy; tính khi đọc, không có ô sửa tay.
-- * Chặng ghi thêm vào tháng đã gửi (ghi muộn) vào bảng kê đang gom kế tiếp của bên đó.
-- Mọi lệnh ghi: khóa tư vấn chung với đợt 1, mã yêu cầu chống ghi trùng, người làm từ sokhach.actor, Lịch sử trước → sau.
BEGIN;
SET LOCAL ROLE sokhach_owner;

-- ---------------------------------------------------------------------------------------------------------------------------
-- Chữ chuẩn hóa để so tên: bỏ dấu tiếng Việt, chữ hoa, gộp khoảng trắng. NULL hoặc chỉ khoảng trắng là NULL.
CREATE OR REPLACE FUNCTION doixe._fold(p text) RETURNS text
LANGUAGE sql IMMUTABLE PARALLEL SAFE SET search_path = pg_catalog, doixe, pg_temp AS $$
    SELECT nullif(btrim(regexp_replace(upper(translate(regexp_replace(normalize(p, NFD), '[̀-ͯ]', '', 'g'), 'đĐ', 'dD')),
                                       '\s+', ' ', 'g')), '')
$$;

-- Khóa nhận ra tuyến của một chặng: tên hàng | tỉnh, đã chuẩn hóa (ví dụ 'SAU RIENG|KRONG PAC').
CREATE OR REPLACE FUNCTION doixe._khoa_tuyen(p_hang text, p_tinh text) RETURNS text
LANGUAGE sql IMMUTABLE PARALLEL SAFE SET search_path = pg_catalog, doixe, pg_temp AS $$
    SELECT coalesce(doixe._fold(p_hang), '') || '|' || coalesce(doixe._fold(p_tinh), '')
$$;

-- Cờ chi hộ trên danh mục phí chặng (phía chi), để lãi lỗ đợt 3 loại được chi hộ ở cả hai phía. Mặc định theo số đo 18/11/2026:
-- xí cont, cont mới thu lại đúng số đã chi; 'hasom' (hạ sớm/kiểm hoá, migration phiếu chi nếu đã áp). Chỉ đặt lúc thêm cột.
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_attribute WHERE attrelid = 'doixe.loai_phi'::regclass AND attname = 'chi_ho' AND NOT attisdropped) THEN
        ALTER TABLE doixe.loai_phi ADD COLUMN chi_ho boolean NOT NULL DEFAULT false;
        UPDATE doixe.loai_phi SET chi_ho = true WHERE ma IN ('xi', 'moi', 'hasom');
    END IF;
END $$;
COMMENT ON COLUMN doixe.loai_phi.chi_ho IS 'DOI-XE-THU-01: khoản chi hộ (trả giùm rồi đòi lại đúng số), không tính vào chi phí đội xe ở lãi lỗ.';

-- ---------------------------------------------------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS doixe.ben (
    ma text PRIMARY KEY CHECK (ma ~ '^[a-z_]{2,20}$'),
    ten text NOT NULL CHECK (btrim(ten) <> '' AND char_length(ten) <= 40),
    kinh_gui text NOT NULL CHECK (btrim(kinh_gui) <> '' AND char_length(kinh_gui) <= 200),
    tieu_de text NOT NULL CHECK (btrim(tieu_de) <> '' AND char_length(tieu_de) <= 100),
    xe_thue_ngoai boolean NOT NULL UNIQUE
);
COMMENT ON TABLE doixe.ben IS 'Bên nhận bảng kê. Chặng của xe nhóm nào (xe công ty hay thuê ngoài) vào bảng kê của bên đó. Hiện một bên: HTH.';
INSERT INTO doixe.ben(ma, ten, kinh_gui, tieu_de, xe_thue_ngoai) VALUES ('hth', 'HTH', 'HTH', 'DEBIT TÍN PHÁT', false)
ON CONFLICT (ma) DO NOTHING;

CREATE TABLE IF NOT EXISTS doixe.tuyen (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    loai text NOT NULL CHECK (loai IN ('hang', 'chuyen_cang', 'tra_rong')),
    hang text CHECK (hang IS NULL OR (btrim(hang) <> '' AND char_length(hang) <= 60)),
    di text NOT NULL CHECK (btrim(di) <> '' AND char_length(di) <= 100),
    den text CHECK (den IS NULL OR (btrim(den) <> '' AND char_length(den) <= 100)),
    dang_dung boolean NOT NULL DEFAULT true,
    actor text NOT NULL CHECK (btrim(actor) <> ''),
    luc timestamptz NOT NULL DEFAULT clock_timestamp(),
    CHECK ((loai = 'hang') = (hang IS NOT NULL))
);
CREATE UNIQUE INDEX IF NOT EXISTS tuyen_mot ON doixe.tuyen (loai, coalesce(doixe._fold(hang), ''), doixe._fold(di), coalesce(doixe._fold(den), ''))
    WHERE dang_dung;
COMMENT ON TABLE doixe.tuyen IS 'Tuyến chuẩn để tính cước: hàng + vùng đi (tỉnh, kho) + nơi đến; chặng phụ (chuyển cảng, trả rỗng) có tuyến riêng giá cố định.';

CREATE TABLE IF NOT EXISTS doixe.tuyen_ten_goc (
    khoa text PRIMARY KEY CHECK (khoa ~ '^[A-Z0-9 ]*\|[A-Z0-9 ]*$' AND khoa <> '|' AND char_length(khoa) <= 260),
    tuyen_id bigint NOT NULL REFERENCES doixe.tuyen(id),
    actor text NOT NULL CHECK (btrim(actor) <> ''),
    luc timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE INDEX IF NOT EXISTS tuyen_ten_goc_tuyen ON doixe.tuyen_ten_goc (tuyen_id);
COMMENT ON TABLE doixe.tuyen_ten_goc IS 'Tên gốc hay gặp của tuyến (TÊN HÀNG|TỈNH đã chuẩn hóa) để nhận ra chặng khi dán; mỗi tên gốc trỏ một tuyến.';

CREATE TABLE IF NOT EXISTS doixe.gia_tuyen (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    ben text NOT NULL REFERENCES doixe.ben(ma),
    tuyen_id bigint NOT NULL REFERENCES doixe.tuyen(id),
    tu_ngay date NOT NULL CHECK (tu_ngay >= DATE '2020-01-01'),
    gia_vnd bigint NOT NULL CHECK (gia_vnd > 0 AND gia_vnd < 10000000000000000),
    actor text NOT NULL CHECK (btrim(actor) <> ''),
    luc timestamptz NOT NULL DEFAULT clock_timestamp(),
    UNIQUE (ben, tuyen_id, tu_ngay)
);
COMMENT ON TABLE doixe.gia_tuyen IS 'Giá cước tuyến theo bên nhận, áp dụng từ ngày (giá của chặng = bản có tu_ngay lớn nhất không sau ngày chặng). Tháng đã gửi giữ số đã chép.';

CREATE TABLE IF NOT EXISTS doixe.phat_sinh (
    ma text PRIMARY KEY CHECK (ma ~ '^[a-z_]{2,16}$'),
    ten text NOT NULL CHECK (btrim(ten) <> '' AND char_length(ten) <= 40),
    cach text NOT NULL CHECK (cach IN ('co_dinh', 'theo_ngay', 'theo_don_vi', 'nhap_tay')),
    muc_vnd bigint CHECK (muc_vnd IS NULL OR (muc_vnd > 0 AND muc_vnd < 10000000000000000)),
    muc_them_vnd bigint CHECK (muc_them_vnd IS NULL OR (muc_them_vnd >= 0 AND muc_them_vnd < 10000000000000000)),
    chi_ho boolean NOT NULL DEFAULT false,
    cot text NOT NULL DEFAULT 'ps' CHECK (cot IN ('ps', 'ghep')),
    loai_phi text REFERENCES doixe.loai_phi(ma),
    thu_tu integer NOT NULL UNIQUE CHECK (thu_tu > 0),
    actor text NOT NULL CHECK (btrim(actor) <> ''),
    luc timestamptz NOT NULL DEFAULT clock_timestamp(),
    CHECK (cach = 'theo_ngay' OR muc_them_vnd IS NULL),
    CHECK (cach <> 'nhap_tay' OR muc_vnd IS NULL)
);
COMMENT ON TABLE doixe.phat_sinh IS 'Danh mục phát sinh tính HTH: cách tính, mức (NULL: chưa có mức), chi hộ (đòi lại đúng số đã trả, không vào lãi), cột trên bảng kê (phát sinh hay đóng ghép).';

CREATE TABLE IF NOT EXISTS doixe.phat_sinh_ten (
    ten text PRIMARY KEY CHECK (ten ~ '^[A-Z0-9]+( [A-Z0-9]+)*$' AND char_length(ten) <= 40),
    ma text NOT NULL REFERENCES doixe.phat_sinh(ma)
);
CREATE INDEX IF NOT EXISTS phat_sinh_ten_ma ON doixe.phat_sinh_ten (ma);
COMMENT ON TABLE doixe.phat_sinh_ten IS 'Tên đọc được trong ghi chú (đã chuẩn hóa, không dấu, chữ hoa) của từng khoản phát sinh; mỗi tên thuộc một khoản.';

-- Danh mục mặc định theo bản bấm thử (DOI-XE-THU-01 mục 5). Mức để trống: xác nhận khi nạp dữ liệu thật hoặc người dùng tự ghi.
INSERT INTO doixe.phat_sinh(ma, ten, cach, chi_ho, cot, loai_phi, thu_tu, actor) VALUES
    ('kiem_hoa', 'Kiểm hoá', 'co_dinh', true, 'ps', NULL, 1, 'migration'),
    ('ha_som', 'Hạ sớm', 'co_dinh', true, 'ps', NULL, 2, 'migration'),
    ('can', 'Cân', 'nhap_tay', true, 'ps', NULL, 3, 'migration'),
    ('xi_cont', 'Xí cont', 'co_dinh', true, 'ps', 'xi', 4, 'migration'),
    ('cont_moi', 'Cont mới', 'co_dinh', true, 'ps', 'moi', 5, 'migration'),
    ('neo', 'Neo', 'theo_ngay', false, 'ps', 'neo', 6, 'migration'),
    ('no_may', 'Nổ máy phát', 'theo_don_vi', false, 'ps', 'may', 7, 'migration'),
    ('dong_an', 'Phí bãi Đồng An', 'co_dinh', false, 'ps', NULL, 8, 'migration'),
    ('lay_xa', 'Lấy rỗng xa', 'co_dinh', false, 'ps', NULL, 9, 'migration'),
    ('mua_seal', 'Mua seal', 'nhap_tay', false, 'ps', 'seal', 10, 'migration'),
    ('bai_cho', 'Bãi chờ', 'nhap_tay', false, 'ps', 'bai', 11, 'migration'),
    ('dieu_do', 'Điều độ', 'nhap_tay', false, 'ps', 'dieu', 12, 'migration'),
    ('nang_ha', 'Nâng hạ', 'nhap_tay', false, 'ps', 'nangha', 13, 'migration'),
    ('dong_ghep', 'Đóng ghép', 'nhap_tay', false, 'ghep', NULL, 14, 'migration')
ON CONFLICT (ma) DO NOTHING;
INSERT INTO doixe.phat_sinh_ten(ten, ma) VALUES
    ('KIEM HOA', 'kiem_hoa'), ('HA KIEM HOA', 'kiem_hoa'), ('HA SOM', 'ha_som'), ('CAN', 'can'), ('CAN XE', 'can'), ('CAN CONT', 'can'),
    ('XI CONT', 'xi_cont'), ('CONT MOI', 'cont_moi'), ('NEO', 'neo'), ('NO MAY PHAT', 'no_may'), ('NO MAY', 'no_may'),
    ('MAY PHAT', 'no_may'), ('DONG AN', 'dong_an'), ('LAY DONG AN', 'dong_an'), ('BAI DONG AN', 'dong_an'),
    ('PHI BAI DONG AN', 'dong_an'), ('LAY RONG XA', 'lay_xa'), ('LAY XA', 'lay_xa'), ('MUA SEAL', 'mua_seal'), ('SEAL', 'mua_seal'),
    ('BAI CHO', 'bai_cho'), ('BAI XE', 'bai_cho'), ('DIEU DO', 'dieu_do'), ('NANG HA', 'nang_ha'), ('DONG GHEP', 'dong_ghep'),
    ('GHEP', 'dong_ghep')
ON CONFLICT (ten) DO NOTHING;

CREATE TABLE IF NOT EXISTS doixe.thu_chang (
    chang_id bigint PRIMARY KEY REFERENCES doixe.chang(id),
    tuyen_id bigint REFERENCES doixe.tuyen(id),
    cuoc_tay_vnd bigint CHECK (cuoc_tay_vnd IS NULL OR (cuoc_tay_vnd >= 0 AND cuoc_tay_vnd < 10000000000000000)),
    actor text NOT NULL CHECK (btrim(actor) <> ''),
    luc timestamptz NOT NULL DEFAULT clock_timestamp()
);
COMMENT ON TABLE doixe.thu_chang IS 'Phần thu riêng của một chặng chưa gửi: tuyến gắn tay (NULL: nhận theo tên gốc), giá cước nhập tay (NULL: theo bảng giá).';

CREATE TABLE IF NOT EXISTS doixe.bang_ke (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    ben text NOT NULL REFERENCES doixe.ben(ma),
    thang date NOT NULL CHECK (extract(day FROM thang) = 1),
    so text NOT NULL UNIQUE CHECK (btrim(so) <> ''),
    trang_thai text NOT NULL CHECK (trang_thai IN ('da_gui', 'da_doi_chieu')),
    gui_ngay date NOT NULL,
    gui_actor text NOT NULL CHECK (btrim(gui_actor) <> ''),
    gui_luc timestamptz NOT NULL DEFAULT clock_timestamp(),
    doi_chieu_actor text,
    doi_chieu_luc timestamptz,
    UNIQUE (ben, thang),
    CHECK ((trang_thai = 'da_doi_chieu') = (doi_chieu_luc IS NOT NULL)),
    CHECK ((doi_chieu_luc IS NULL) = (doi_chieu_actor IS NULL))
);
COMMENT ON TABLE doixe.bang_ke IS 'Bảng kê tháng đã gửi một bên. Chưa có dòng ở đây là đang gom (web tính sống). Thu đủ: đã đối chiếu và tiền về bằng số đòi.';

CREATE TABLE IF NOT EXISTS doixe.bang_ke_dong (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    bang_ke_id bigint NOT NULL REFERENCES doixe.bang_ke(id),
    stt integer NOT NULL CHECK (stt > 0),
    chang_id bigint NOT NULL UNIQUE REFERENCES doixe.chang(id),
    ngay date NOT NULL,
    container text NOT NULL,
    loai text NOT NULL,
    tinh text, kho text, tai_xe text, so_xe text, noi_lay text, noi_ha text, ten_hang text, ghi_chu text,
    tuyen text,
    gia_bang_vnd bigint,
    cuoc_vnd bigint CHECK (cuoc_vnd IS NULL OR cuoc_vnd >= 0),
    cuoc_tay boolean NOT NULL,
    ghep_vnd bigint,
    ps_vnd bigint,
    chi_ho_vnd bigint,
    ps jsonb NOT NULL CHECK (jsonb_typeof(ps) = 'array'),
    UNIQUE (bang_ke_id, stt)
);
COMMENT ON TABLE doixe.bang_ke_dong IS 'Dòng bảng kê chép lúc gửi (chữ và số như lúc gửi). Một chặng vào tối đa một bảng kê. Không sửa, không xóa: chỉ điều chỉnh.';

CREATE TABLE IF NOT EXISTS doixe.dieu_chinh_bk (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    bang_ke_id bigint NOT NULL REFERENCES doixe.bang_ke(id),
    dong_id bigint NOT NULL REFERENCES doixe.bang_ke_dong(id),
    so_tien_vnd bigint NOT NULL CHECK (so_tien_vnd <> 0),
    ly_do text NOT NULL CHECK (btrim(ly_do) <> '' AND char_length(ly_do) <= 500),
    actor text NOT NULL CHECK (btrim(actor) <> ''),
    luc timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE INDEX IF NOT EXISTS dieu_chinh_bk_bang_ke ON doixe.dieu_chinh_bk (bang_ke_id);
COMMENT ON TABLE doixe.dieu_chinh_bk IS 'Điều chỉnh khi đối chiếu, gắn một dòng bảng kê; số có dấu (bớt âm, thêm dương), lý do bắt buộc. Chỉ thêm.';

CREATE TABLE IF NOT EXISTS doixe.tien_ve (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    bang_ke_id bigint NOT NULL REFERENCES doixe.bang_ke(id),
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
CREATE INDEX IF NOT EXISTS tien_ve_bang_ke ON doixe.tien_ve (bang_ke_id);
COMMENT ON TABLE doixe.tien_ve IS 'Tiền HTH trả, gắn bảng kê của tháng. Không xóa; hủy bắt buộc lý do, vẫn hiện.';

CREATE OR REPLACE TRIGGER bang_ke_khong_xoa BEFORE DELETE ON doixe.bang_ke FOR EACH ROW EXECUTE FUNCTION doixe._chan_sua();
CREATE OR REPLACE TRIGGER bang_ke_dong_chi_them BEFORE UPDATE OR DELETE ON doixe.bang_ke_dong FOR EACH ROW EXECUTE FUNCTION doixe._chan_sua();
CREATE OR REPLACE TRIGGER dieu_chinh_bk_chi_them BEFORE UPDATE OR DELETE ON doixe.dieu_chinh_bk FOR EACH ROW EXECUTE FUNCTION doixe._chan_sua();
CREATE OR REPLACE TRIGGER tien_ve_khong_xoa BEFORE DELETE ON doixe.tien_ve FOR EACH ROW EXECUTE FUNCTION doixe._chan_sua();
CREATE OR REPLACE TRIGGER gia_tuyen_khong_xoa BEFORE DELETE ON doixe.gia_tuyen FOR EACH ROW EXECUTE FUNCTION doixe._chan_sua();

-- Lịch sử: thêm các việc thu; hủy tiền về và điều chỉnh bảng kê bắt buộc lý do.
DO $$
DECLARE r record;
BEGIN
    FOR r IN SELECT conname FROM pg_constraint WHERE conrelid = 'doixe.su_kien'::regclass AND contype = 'c'
                AND pg_get_constraintdef(oid) LIKE '%huy_ung%' LOOP
        EXECUTE format('ALTER TABLE doixe.su_kien DROP CONSTRAINT %I', r.conname);
    END LOOP;
END $$;
ALTER TABLE doixe.su_kien ADD CONSTRAINT su_kien_viec CHECK (viec IN (
    'nap', 'them_chang', 'sua_chang', 'dieu_chinh', 'doi_nguoi_tra', 'xoa_chang', 'bo_chang', 'ghi_ung', 'huy_ung', 'ghi_hoan', 'huy_hoan',
    'khoa_thang', 'gui_bang_ke', 'doi_chieu_xong', 'dieu_chinh_bk', 'ghi_tien_ve', 'huy_tien_ve', 'sua_cuoc', 'gan_tuyen', 'sua_gia',
    'luu_tuyen', 'luu_phat_sinh'));
ALTER TABLE doixe.su_kien ADD CONSTRAINT su_kien_ly_do CHECK (
    (viec IN ('huy_ung', 'huy_hoan', 'huy_tien_ve', 'dieu_chinh_bk')) = (ly_do IS NOT NULL));
CREATE INDEX IF NOT EXISTS su_kien_thu ON doixe.su_kien (id DESC)
    WHERE viec IN ('gui_bang_ke', 'doi_chieu_xong', 'dieu_chinh_bk', 'ghi_tien_ve', 'huy_tien_ve', 'sua_cuoc', 'gan_tuyen', 'sua_gia',
                   'luu_tuyen', 'luu_phat_sinh');

-- ---------------------------------------------------------------------------------------------------------------------------
-- Hàm phụ (không cấp cho ai).
CREATE OR REPLACE FUNCTION doixe._viec_thu() RETURNS text[]
LANGUAGE sql IMMUTABLE SET search_path = pg_catalog, doixe, pg_temp AS $$
    SELECT ARRAY['gui_bang_ke', 'doi_chieu_xong', 'dieu_chinh_bk', 'ghi_tien_ve', 'huy_tien_ve', 'sua_cuoc', 'gan_tuyen', 'sua_gia',
                 'luu_tuyen', 'luu_phat_sinh']
$$;

CREATE OR REPLACE FUNCTION doixe._ben_nhan(p_ben text) RETURNS doixe.ben
LANGUAGE plpgsql STABLE SET search_path = pg_catalog, doixe, pg_temp AS $$
DECLARE b doixe.ben;
BEGIN
    SELECT * INTO b FROM doixe.ben WHERE ma = coalesce(p_ben, 'hth');
    IF NOT FOUND THEN RAISE EXCEPTION 'INVALID_COMMAND'; END IF;
    RETURN b;
END $$;

CREATE OR REPLACE FUNCTION doixe._thang(v jsonb) RETURNS date
LANGUAGE plpgsql STABLE SET search_path = pg_catalog, doixe, pg_temp AS $$
DECLARE m date;
BEGIN
    m := doixe._ngay(v);
    IF m IS NULL OR extract(day FROM m) <> 1 OR m > doixe._hom_nay() THEN RAISE EXCEPTION 'INVALID_MONTH'; END IF;
    RETURN m;
END $$;

CREATE OR REPLACE FUNCTION doixe._ten_tuyen(t doixe.tuyen) RETURNS text
LANGUAGE sql IMMUTABLE SET search_path = pg_catalog, doixe, pg_temp AS $$
    SELECT CASE t.loai WHEN 'hang' THEN t.hang || ' · ' WHEN 'chuyen_cang' THEN 'Chuyển cảng · ' ELSE 'Trả rỗng · ' END
           || t.di || coalesce(' → ' || t.den, '')
$$;

-- Giá bảng của một tuyến cho bên nhận ở một ngày: bản có tu_ngay lớn nhất không sau ngày đó; NULL khi chưa có.
CREATE OR REPLACE FUNCTION doixe._gia(p_ben text, p_tuyen bigint, p_ngay date) RETURNS bigint
LANGUAGE sql STABLE SET search_path = pg_catalog, doixe, pg_temp AS $$
    SELECT g.gia_vnd FROM doixe.gia_tuyen g WHERE g.ben = p_ben AND g.tuyen_id = p_tuyen AND g.tu_ngay <= p_ngay
     ORDER BY g.tu_ngay DESC LIMIT 1
$$;

-- Tuyến tính giá của chặng: gắn tay (thu_chang) → tên gốc (TÊN HÀNG|TỈNH) → chặng phụ có đúng một tuyến cùng loại đang dùng.
CREATE OR REPLACE FUNCTION doixe._tuyen_chang(c doixe.chang) RETURNS bigint
LANGUAGE sql STABLE SET search_path = pg_catalog, doixe, pg_temp AS $$
    SELECT coalesce(
        (SELECT t.id FROM doixe.thu_chang tc JOIN doixe.tuyen t ON t.id = tc.tuyen_id AND t.dang_dung WHERE tc.chang_id = c.id),
        (SELECT t.id FROM doixe.tuyen_ten_goc g JOIN doixe.tuyen t ON t.id = g.tuyen_id AND t.dang_dung
          WHERE g.khoa = doixe._khoa_tuyen(c.ten_hang, c.tinh)),
        CASE WHEN c.loai IN ('chuyen_cang', 'tra_rong') THEN
            (SELECT min(t.id) FROM doixe.tuyen t WHERE t.dang_dung AND t.loai = c.loai HAVING count(*) = 1) END)
$$;

-- Giá bảng của chặng theo tuyến: hàng theo giá tuyến; rút/thả mooc 70% giá tuyến hàng, làm tròn tới nghìn đồng (nửa nghìn lên);
-- chuyển cảng, trả rỗng theo tuyến cùng loại. Tuyến không hợp loại chặng thì không có giá.
CREATE OR REPLACE FUNCTION doixe._gia_bang(p_ben text, p_loai text, p_tuyen doixe.tuyen, p_ngay date) RETURNS bigint
LANGUAGE plpgsql STABLE SET search_path = pg_catalog, doixe, pg_temp AS $$
DECLARE v bigint;
BEGIN
    IF p_tuyen.id IS NULL THEN RETURN NULL; END IF;
    IF p_loai IN ('hang', 'rut_mooc', 'tha_mooc') AND p_tuyen.loai = 'hang' OR p_loai IN ('chuyen_cang', 'tra_rong') AND p_tuyen.loai = p_loai THEN
        v := doixe._gia(p_ben, p_tuyen.id, p_ngay);
        IF v IS NOT NULL AND p_loai IN ('rut_mooc', 'tha_mooc') THEN v := (v * 7 + 5000) / 10000 * 1000; END IF;
        RETURN v;
    END IF;
    RETURN NULL;
END $$;

-- Đọc ghi chú phát sinh. Mỗi khoản bắt đầu bằng "_" (đầu ghi chú hoặc sau khoảng trắng), tới "_" kế tiếp; chữ trước "_" đầu
-- tiên là ghi chú thường, không đọc. Một khoản: tên rồi số tiền ở cuối: 1250k · 1tr5 · 1,5tr · 1.250.000 · 1250000đ. Không có
-- số tiền thì: khoản theo ngày/đơn vị lấy số lượng ở cuối ("Neo 2 ngày" = mức + 1 × mức thêm; "Nổ máy phát 3" = 3 × mức), khoản
-- cố định lấy mức. Tên khớp tên dài nhất của danh mục ở đầu khoản (phần còn lại là mô tả); không khớp mà có số tiền: khoản lạ,
-- vẫn tính (không chi hộ) và gắn cờ. Không đọc được (thiếu số tiền, chưa có mức, số lạ): gắn lỗi, không tính.
-- Trả mảng: {goc, ten, ma, so_tien_vnd, chi_ho, cot, la?} hoặc {goc, loi}.
CREATE OR REPLACE FUNCTION doixe._doc_ghi_chu(p_ghi_chu text) RETURNS jsonb
LANGUAGE plpgsql STABLE SET search_path = pg_catalog, doixe, pg_temp AS $$
DECLARE v_out jsonb := '[]'::jsonb; v_goc text; v_ten text; v_tien numeric; v_sl integer; m text[]; ps doixe.phat_sinh;
        v_khop text; v_n integer := 0;
BEGIN
    IF p_ghi_chu IS NULL OR p_ghi_chu !~ '(^|\s)_' THEN RETURN v_out; END IF;
    FOR v_goc IN SELECT btrim(x) FROM regexp_split_to_table(regexp_replace(p_ghi_chu, '\s+', ' ', 'g'), '(^|\s)_') WITH ORDINALITY AS s(x, n)
                  WHERE n > 1 ORDER BY n LOOP
        IF v_goc = '' THEN CONTINUE; END IF;
        v_n := v_n + 1;
        IF v_n > 20 THEN
            v_out := v_out || jsonb_build_object('goc', v_goc, 'loi', 'Quá 20 khoản trong một ghi chú');
            CONTINUE;
        END IF;
        v_tien := NULL; v_sl := NULL; v_ten := NULL; ps := NULL;
        m := regexp_match(v_goc, '^(.*?)\s*([0-9]{1,9})[.,]([0-9]{1,3})\s*(tr|triệu|trieu)$', 'i');
        IF m IS NOT NULL THEN
            v_ten := m[1]; v_tien := m[2]::numeric * 1000000 + rpad(m[3], 3, '0')::numeric * 1000;
        ELSE
            m := regexp_match(v_goc, '^(.*?)\s*([0-9]{1,9})\s*(tr|triệu|trieu)\s*([0-9]{1,3})?$', 'i');
            IF m IS NOT NULL THEN
                v_ten := m[1]; v_tien := m[2]::numeric * 1000000 + coalesce(rpad(m[4], 3, '0')::numeric * 1000, 0);
            ELSE
                m := regexp_match(v_goc, '^(.*?)\s*([0-9]{1,12})\s*k$', 'i');
                IF m IS NOT NULL THEN
                    v_ten := m[1]; v_tien := m[2]::numeric * 1000;
                ELSE
                    m := regexp_match(v_goc, '^(.*?)\s*([0-9]{1,3}(?:[.,][0-9]{3})+)\s*(đ|đồng|d|dong|vnd)?$', 'i');
                    IF m IS NOT NULL THEN
                        v_ten := m[1]; v_tien := regexp_replace(m[2], '[.,]', '', 'g')::numeric;
                    ELSE
                        m := regexp_match(v_goc, '^(.*?)\s*([0-9]{1,15})\s*(đ|đồng|d|dong|vnd)$', 'i');
                        IF m IS NOT NULL THEN
                            v_ten := m[1]; v_tien := m[2]::numeric;
                        ELSE
                            m := regexp_match(v_goc, '^(.*?)\s*([0-9]{1,2})\s*(ngày|ngay|đơn vị|don vi|lần|lan|tiếng|tieng|giờ|gio|h)?$', 'i');
                            IF m IS NOT NULL THEN
                                v_ten := m[1]; v_sl := m[2]::integer;
                            ELSE
                                v_ten := v_goc;
                            END IF;
                        END IF;
                    END IF;
                END IF;
            END IF;
        END IF;
        IF v_tien IS NULL AND v_sl IS NULL AND v_goc ~ '[0-9]\s*$' THEN
            v_out := v_out || jsonb_build_object('goc', v_goc, 'loi', 'Số ở cuối thiếu đơn vị tiền (k, tr)');
            CONTINUE;
        END IF;
        -- Hai số tiền trong một khoản ("Xí cont 150k ĐIỀU ĐỘ 450K" khi quên dấu _): không đoán khoản nào.
        IF v_ten ~* '[0-9]\s*(k|tr|triệu|trieu|đ|đồng)(\s|$)' THEN
            v_out := v_out || jsonb_build_object('goc', v_goc, 'loi', 'Một khoản có hai số tiền: tách mỗi khoản bằng dấu _');
            CONTINUE;
        END IF;
        -- "1.250k", "1,5k", "1 200k", "Kiểm hoá 1250": số dính sau tên dễ đọc sai, không đoán.
        IF v_ten ~ '[0-9][.,]?$' THEN
            v_out := v_out || jsonb_build_object('goc', v_goc, 'loi', 'Số tiền lạ: ghi kiểu 1250k, 1tr5 hoặc 1.250.000');
            CONTINUE;
        END IF;
        v_ten := btrim(v_ten, ' :-–=_.,');
        v_khop := doixe._fold(v_ten);
        IF v_khop IS NOT NULL THEN
            SELECT p.* INTO ps FROM doixe.phat_sinh_ten t JOIN doixe.phat_sinh p ON p.ma = t.ma
             WHERE v_khop = t.ten OR v_khop LIKE t.ten || ' %' ORDER BY char_length(t.ten) DESC LIMIT 1;
        END IF;
        IF v_tien IS NULL AND ps.ma IS NOT NULL THEN
            IF v_sl IS NOT NULL AND ps.cach = 'theo_ngay' AND v_sl >= 1 AND ps.muc_vnd IS NOT NULL AND ps.muc_them_vnd IS NOT NULL THEN
                v_tien := ps.muc_vnd + (v_sl - 1) * ps.muc_them_vnd;
            ELSIF v_sl IS NOT NULL AND ps.cach = 'theo_don_vi' AND v_sl >= 1 AND ps.muc_vnd IS NOT NULL THEN
                v_tien := v_sl * ps.muc_vnd;
            ELSIF v_sl IS NULL AND ps.cach = 'co_dinh' AND ps.muc_vnd IS NOT NULL THEN
                v_tien := ps.muc_vnd;
            END IF;
        END IF;
        IF v_tien IS NULL THEN
            v_out := v_out || jsonb_build_object('goc', v_goc, 'loi',
                CASE WHEN ps.ma IS NULL AND v_sl IS NULL THEN 'Thiếu số tiền (ví dụ 200k)'
                     WHEN ps.ma IS NULL THEN 'Chưa rõ khoản và số tiền'
                     WHEN ps.cach IN ('theo_ngay', 'theo_don_vi', 'co_dinh') AND ps.muc_vnd IS NULL THEN 'Khoản này chưa có mức: ghi số tiền'
                     WHEN v_sl IS NOT NULL AND ps.cach NOT IN ('theo_ngay', 'theo_don_vi') THEN 'Số ở cuối thiếu đơn vị tiền (k, tr)'
                     ELSE 'Thiếu số tiền (ví dụ 200k)' END);
        ELSIF v_tien <= 0 OR v_tien >= 10000000000000000 THEN
            v_out := v_out || jsonb_build_object('goc', v_goc, 'loi', 'Số tiền không hợp lệ');
        ELSIF ps.ma IS NULL THEN
            v_out := v_out || jsonb_build_object('goc', v_goc, 'ten', coalesce(nullif(v_ten, ''), 'Khoản không tên'), 'ma', NULL,
                'so_tien_vnd', v_tien::bigint::text, 'chi_ho', false, 'cot', 'ps', 'la', true);
        ELSE
            v_out := v_out || jsonb_build_object('goc', v_goc, 'ten', coalesce(nullif(v_ten, ''), ps.ten), 'ma', ps.ma, 'ten_dm', ps.ten,
                'so_tien_vnd', v_tien::bigint::text, 'chi_ho', ps.chi_ho, 'cot', ps.cot);
        END IF;
    END LOOP;
    RETURN v_out;
END $$;

-- Chặng đang gom của bảng kê (bên, tháng): chặng xe đúng nhóm, chưa xóa/bỏ, chưa vào bảng kê nào, và tháng gom của nó là tháng
-- này. Tháng gom = tháng của chặng, hoặc (khi bảng kê tháng đó đã gửi) tháng kế tiếp đầu tiên chưa gửi.
CREATE OR REPLACE FUNCTION doixe._thang_gom(p_ben text, p_ngay date) RETURNS date
LANGUAGE plpgsql STABLE SET search_path = pg_catalog, doixe, pg_temp AS $$
DECLARE m date := date_trunc('month', p_ngay)::date;
BEGIN
    WHILE EXISTS (SELECT 1 FROM doixe.bang_ke k WHERE k.ben = p_ben AND k.thang = m) LOOP
        m := (m + interval '1 month')::date;
    END LOOP;
    RETURN m;
END $$;

CREATE OR REPLACE FUNCTION doixe._chang_gom(p_ben doixe.ben, p_thang date) RETURNS bigint[]
LANGUAGE sql STABLE SET search_path = pg_catalog, doixe, pg_temp AS $$
    SELECT coalesce(array_agg(c.id ORDER BY c.ngay, c.id), '{}')
      FROM doixe.chang c JOIN doixe.xe x ON x.id = c.xe_id
     WHERE NOT c.da_xoa AND NOT c.da_bo AND x.thue_ngoai = p_ben.xe_thue_ngoai AND c.ngay < (p_thang + interval '1 month')::date
       AND NOT EXISTS (SELECT 1 FROM doixe.bang_ke_dong d WHERE d.chang_id = c.id)
       AND doixe._thang_gom(p_ben.ma, c.ngay) = p_thang
$$;

-- Phần thu của một chặng chưa gửi, đúng hình dạng một dòng bảng kê (dùng cho màn đang gom và lúc chép khi gửi).
CREATE OR REPLACE FUNCTION doixe._tinh_chang(p_chang bigint, p_ben text) RETURNS jsonb
LANGUAGE plpgsql STABLE SET search_path = pg_catalog, doixe, pg_temp AS $$
DECLARE c doixe.chang; tc doixe.thu_chang; t doixe.tuyen; v_bang bigint; v_cuoc bigint; v_ps jsonb;
        v_ghep bigint; v_psv bigint; v_chiho bigint; v_doc integer; v_la integer;
BEGIN
    SELECT * INTO c FROM doixe.chang WHERE id = p_chang;
    SELECT * INTO tc FROM doixe.thu_chang WHERE chang_id = p_chang;
    SELECT * INTO t FROM doixe.tuyen WHERE id = doixe._tuyen_chang(c);
    v_bang := doixe._gia_bang(p_ben, c.loai, t, c.ngay);
    v_cuoc := coalesce(tc.cuoc_tay_vnd, v_bang);
    v_ps := doixe._doc_ghi_chu(c.ghi_chu);
    SELECT sum((e ->> 'so_tien_vnd')::bigint) FILTER (WHERE e ->> 'cot' = 'ghep'),
           sum((e ->> 'so_tien_vnd')::bigint) FILTER (WHERE e ->> 'cot' = 'ps'),
           sum((e ->> 'so_tien_vnd')::bigint) FILTER (WHERE e ->> 'cot' = 'ps' AND (e ->> 'chi_ho')::boolean),
           count(*) FILTER (WHERE e ? 'loi'), count(*) FILTER (WHERE (e ->> 'la')::boolean)
      INTO v_ghep, v_psv, v_chiho, v_doc, v_la FROM jsonb_array_elements(v_ps) e;
    RETURN jsonb_build_object(
        'chang_id', c.id, 'ngay', c.ngay, 'container', c.container, 'loai', c.loai, 'tinh', c.tinh, 'kho', c.kho,
        'tai_xe', (SELECT n.ten FROM doixe.nguoi n WHERE n.id = c.tai_xe_id), 'so_xe', (SELECT x.bien_so FROM doixe.xe x WHERE x.id = c.xe_id),
        'noi_lay', c.noi_lay, 'noi_ha', c.noi_ha, 'ten_hang', c.ten_hang, 'ghi_chu', c.ghi_chu,
        'tuyen_id', t.id, 'tuyen', doixe._ten_tuyen(t), 'tuyen_gan', coalesce(tc.tuyen_id = t.id, false),
        'khoa_tuyen', doixe._khoa_tuyen(c.ten_hang, c.tinh),
        'gia_bang_vnd', v_bang::text, 'cuoc_vnd', v_cuoc::text, 'cuoc_tay', tc.cuoc_tay_vnd IS NOT NULL,
        'ghep_vnd', v_ghep::text, 'ps_vnd', v_psv::text, 'chi_ho_vnd', v_chiho::text, 'ps', v_ps,
        'chua_doc', v_doc, 'khoan_la', v_la, 'chang_con', true);
END $$;

-- Tiền còn phải thu của một bảng kê đã gửi: dòng + điều chỉnh − tiền về chưa hủy.
CREATE OR REPLACE FUNCTION doixe._doi_bk(p_bang_ke bigint) RETURNS bigint
LANGUAGE sql STABLE SET search_path = pg_catalog, doixe, pg_temp AS $$
    SELECT coalesce((SELECT sum(coalesce(d.cuoc_vnd, 0) + coalesce(d.ghep_vnd, 0) + coalesce(d.ps_vnd, 0)) FROM doixe.bang_ke_dong d
                      WHERE d.bang_ke_id = p_bang_ke), 0)::bigint
         + coalesce((SELECT sum(a.so_tien_vnd) FROM doixe.dieu_chinh_bk a WHERE a.bang_ke_id = p_bang_ke), 0)::bigint
$$;

CREATE OR REPLACE FUNCTION doixe._tra_bk(p_bang_ke bigint) RETURNS bigint
LANGUAGE sql STABLE SET search_path = pg_catalog, doixe, pg_temp AS $$
    SELECT coalesce(sum(v.so_tien_vnd), 0)::bigint FROM doixe.tien_ve v WHERE v.bang_ke_id = p_bang_ke AND v.huy_luc IS NULL
$$;

-- Dòng của bảng kê đã gửi (chép lúc gửi) kèm điều chỉnh từng dòng và cờ chặng đã xóa/bỏ sau khi gửi.
CREATE OR REPLACE FUNCTION doixe._dong_bk(p_bang_ke bigint) RETURNS jsonb
LANGUAGE sql STABLE SET search_path = pg_catalog, doixe, pg_temp AS $$
    SELECT coalesce(jsonb_agg(jsonb_build_object(
        'id', d.id, 'stt', d.stt, 'chang_id', d.chang_id, 'ngay', d.ngay, 'container', d.container, 'loai', d.loai, 'tinh', d.tinh,
        'kho', d.kho, 'tai_xe', d.tai_xe, 'so_xe', d.so_xe, 'noi_lay', d.noi_lay, 'noi_ha', d.noi_ha, 'ten_hang', d.ten_hang,
        'ghi_chu', d.ghi_chu, 'tuyen', d.tuyen, 'gia_bang_vnd', d.gia_bang_vnd::text, 'cuoc_vnd', d.cuoc_vnd::text, 'cuoc_tay', d.cuoc_tay,
        'ghep_vnd', d.ghep_vnd::text, 'ps_vnd', d.ps_vnd::text, 'chi_ho_vnd', d.chi_ho_vnd::text, 'ps', d.ps,
        'chua_doc', (SELECT count(*) FROM jsonb_array_elements(d.ps) e WHERE e ? 'loi'),
        'khoan_la', (SELECT count(*) FROM jsonb_array_elements(d.ps) e WHERE (e ->> 'la')::boolean),
        'chang_con', EXISTS (SELECT 1 FROM doixe.chang c WHERE c.id = d.chang_id AND NOT c.da_xoa AND NOT c.da_bo),
        'dc_vnd', (SELECT sum(a.so_tien_vnd)::text FROM doixe.dieu_chinh_bk a WHERE a.dong_id = d.id),
        'dieu_chinh', (SELECT coalesce(jsonb_agg(jsonb_build_object('id', a.id, 'so_tien_vnd', a.so_tien_vnd::text, 'ly_do', a.ly_do,
                          'actor', a.actor, 'luc', doixe._luc(a.luc)) ORDER BY a.id), '[]'::jsonb)
                       FROM doixe.dieu_chinh_bk a WHERE a.dong_id = d.id)) ORDER BY d.stt), '[]'::jsonb)
      FROM doixe.bang_ke_dong d WHERE d.bang_ke_id = p_bang_ke
$$;

-- Tổng của các dòng (dạng jsonb của _tinh_chang hoặc _dong_bk): cước, đóng ghép, phát sinh doanh thu, chi hộ, điều chỉnh, số đòi.
CREATE OR REPLACE FUNCTION doixe._tong_dong(p_dong jsonb) RETURNS jsonb
LANGUAGE sql IMMUTABLE SET search_path = pg_catalog, doixe, pg_temp AS $$
    SELECT jsonb_build_object(
        'cuoc_vnd', coalesce(sum((e ->> 'cuoc_vnd')::bigint), 0)::text,
        'ghep_vnd', coalesce(sum((e ->> 'ghep_vnd')::bigint), 0)::text,
        'ps_vnd', coalesce(sum((e ->> 'ps_vnd')::bigint), 0)::text,
        'chi_ho_vnd', coalesce(sum((e ->> 'chi_ho_vnd')::bigint), 0)::text,
        'dc_vnd', coalesce(sum((e ->> 'dc_vnd')::bigint), 0)::text,
        'doi_vnd', (coalesce(sum((e ->> 'cuoc_vnd')::bigint), 0) + coalesce(sum((e ->> 'ghep_vnd')::bigint), 0)
                    + coalesce(sum((e ->> 'ps_vnd')::bigint), 0) + coalesce(sum((e ->> 'dc_vnd')::bigint), 0))::text,
        'so_chang', count(*),
        'chua_gia', count(*) FILTER (WHERE e ->> 'cuoc_vnd' IS NULL),
        'khac_gia', count(*) FILTER (WHERE (e ->> 'cuoc_tay')::boolean AND e ->> 'gia_bang_vnd' IS NOT NULL
                                       AND e ->> 'gia_bang_vnd' IS DISTINCT FROM e ->> 'cuoc_vnd'),
        'chua_doc', count(*) FILTER (WHERE (e ->> 'chua_doc')::integer > 0),
        'khoan_la', count(*) FILTER (WHERE (e ->> 'khoan_la')::integer > 0),
        'co_dc', count(*) FILTER (WHERE e ->> 'dc_vnd' IS NOT NULL),
        'phu', count(*) FILTER (WHERE e ->> 'loai' <> 'hang'))
      FROM jsonb_array_elements(coalesce(p_dong, '[]'::jsonb)) e
$$;

-- Các tháng trên thanh tháng: tháng có bảng kê, tháng có chặng đang gom, tháng này và tháng trước; kèm trạng thái.
CREATE OR REPLACE FUNCTION doixe._thang_bk(p_ben doixe.ben) RETURNS jsonb
LANGUAGE sql STABLE SET search_path = pg_catalog, doixe, pg_temp AS $$
    WITH d AS (SELECT date_trunc('month', doixe._hom_nay())::date AS nay),
    m AS (SELECT DISTINCT x FROM (
        SELECT k.thang AS x FROM doixe.bang_ke k WHERE k.ben = p_ben.ma
        UNION ALL SELECT doixe._thang_gom(p_ben.ma, c.ngay) FROM doixe.chang c JOIN doixe.xe xe ON xe.id = c.xe_id
         WHERE NOT c.da_xoa AND NOT c.da_bo AND xe.thue_ngoai = p_ben.xe_thue_ngoai
           AND NOT EXISTS (SELECT 1 FROM doixe.bang_ke_dong bd WHERE bd.chang_id = c.id)
        UNION ALL SELECT nay FROM d
        UNION ALL SELECT (nay - interval '1 month')::date FROM d) s, d WHERE x <= d.nay)
    SELECT coalesce(jsonb_agg(jsonb_build_object('thang', m.x, 'trang_thai',
        CASE WHEN k.id IS NULL THEN 'nhap' WHEN k.trang_thai = 'da_gui' THEN 'gui'
             WHEN doixe._doi_bk(k.id) - doixe._tra_bk(k.id) = 0 THEN 'du' ELSE 'doi' END,
        'con_vnd', CASE WHEN k.id IS NOT NULL THEN (doixe._doi_bk(k.id) - doixe._tra_bk(k.id))::text END) ORDER BY m.x), '[]'::jsonb)
      FROM m LEFT JOIN doixe.bang_ke k ON k.ben = p_ben.ma AND k.thang = m.x
$$;

-- Công nợ cước của một bên: bảng kê đã gửi + điều chỉnh − tiền về chưa hủy.
CREATE OR REPLACE FUNCTION doixe._cong_no(p_ben text) RETURNS bigint
LANGUAGE sql STABLE SET search_path = pg_catalog, doixe, pg_temp AS $$
    SELECT coalesce(sum(doixe._doi_bk(k.id) - doixe._tra_bk(k.id)), 0)::bigint FROM doixe.bang_ke k WHERE k.ben = p_ben
$$;

-- Bảng kê (bên, tháng) dạng đọc: đã gửi thì dòng chép, chưa gửi thì tính sống.
CREATE OR REPLACE FUNCTION doixe._doc_bang_ke(b doixe.ben, p_thang date) RETURNS jsonb
LANGUAGE plpgsql STABLE SET search_path = pg_catalog, doixe, pg_temp AS $$
DECLARE k doixe.bang_ke; v_dong jsonb; v_tong jsonb; v_tra bigint := 0;
BEGIN
    SELECT * INTO k FROM doixe.bang_ke WHERE ben = b.ma AND thang = p_thang;
    IF FOUND THEN
        v_dong := doixe._dong_bk(k.id);
        v_tra := doixe._tra_bk(k.id);
    ELSE
        SELECT coalesce(jsonb_agg(doixe._tinh_chang(x.id, b.ma) ORDER BY x.n), '[]'::jsonb) INTO v_dong
          FROM unnest(doixe._chang_gom(b, p_thang)) WITH ORDINALITY AS x(id, n);
    END IF;
    v_tong := doixe._tong_dong(v_dong);
    RETURN jsonb_build_object(
        'bang_ke', CASE WHEN k.id IS NULL THEN NULL ELSE jsonb_build_object('id', k.id, 'so', k.so, 'trang_thai', k.trang_thai,
            'gui_ngay', k.gui_ngay, 'gui_actor', k.gui_actor, 'gui_luc', doixe._luc(k.gui_luc),
            'doi_chieu_actor', k.doi_chieu_actor, 'doi_chieu_luc', doixe._luc(k.doi_chieu_luc),
            'thu_du', k.trang_thai = 'da_doi_chieu' AND (v_tong ->> 'doi_vnd')::bigint - v_tra = 0) END,
        'dong', v_dong,
        'tong', v_tong || jsonb_build_object('tra_vnd', v_tra::text, 'con_vnd', ((v_tong ->> 'doi_vnd')::bigint - v_tra)::text),
        'tien_ve', CASE WHEN k.id IS NULL THEN '[]'::jsonb ELSE (SELECT coalesce(jsonb_agg(jsonb_build_object('id', v.id, 'ngay', v.ngay,
            'so_tien_vnd', v.so_tien_vnd::text, 'ghi_chu', v.ghi_chu, 'actor', v.actor, 'luc', doixe._luc(v.luc),
            'huy', CASE WHEN v.huy_luc IS NULL THEN NULL
                        ELSE jsonb_build_object('actor', v.huy_actor, 'luc', doixe._luc(v.huy_luc), 'ly_do', v.huy_ly_do) END)
            ORDER BY v.ngay, v.id), '[]'::jsonb) FROM doixe.tien_ve v WHERE v.bang_ke_id = k.id) END);
END $$;

-- ---------------------------------------------------------------------------------------------------------------------------
-- Hàm đọc (cấp cho sokhach_app).
CREATE OR REPLACE FUNCTION doixe.get_bang_ke(p_ben text, p_thang date) RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = pg_catalog, doixe, pg_temp AS $$
-- Màn Bảng kê: thanh tháng (trạng thái), công nợ cước, bảng kê tháng chọn (dòng, tổng, tiền về).
DECLARE d date := doixe._hom_nay(); m date; b doixe.ben;
BEGIN
    PERFORM doixe._actor();
    b := doixe._ben_nhan(p_ben);
    m := coalesce(p_thang, date_trunc('month', d)::date);
    IF date_trunc('month', m)::date <> m OR m > d THEN RAISE EXCEPTION 'INVALID_MONTH'; END IF;
    RETURN jsonb_build_object('hom_nay', d, 'thang', m,
        'ben', jsonb_build_object('ma', b.ma, 'ten', b.ten, 'kinh_gui', b.kinh_gui, 'tieu_de', b.tieu_de),
        'thang_ds', doixe._thang_bk(b), 'cong_no_vnd', doixe._cong_no(b.ma)::text) || doixe._doc_bang_ke(b, m);
END $$;

CREATE OR REPLACE FUNCTION doixe.get_bang_gia(p_ben text) RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = pg_catalog, doixe, pg_temp AS $$
-- Màn Bảng giá: tuyến (giá từng ngày áp dụng, tên gốc, ngày các chặng đang gom theo bảng giá để báo "n chặng đổi theo") và danh
-- mục phát sinh (cách tính, mức, chi hộ, tên đọc được).
DECLARE d date := doixe._hom_nay(); b doixe.ben; v_cho jsonb;
BEGIN
    PERFORM doixe._actor();
    b := doixe._ben_nhan(p_ben);
    -- Ngày các chặng đang gom theo bảng giá (không giá tay), theo tuyến: tính tuyến mỗi chặng một lần.
    SELECT coalesce(jsonb_object_agg(x.tid::text, x.ngays), '{}'::jsonb) INTO v_cho FROM (
        SELECT cg.tid, jsonb_agg(cg.ngay ORDER BY cg.ngay) AS ngays FROM (
            SELECT c.ngay, doixe._tuyen_chang(c) AS tid FROM doixe.chang c JOIN doixe.xe x ON x.id = c.xe_id
             WHERE NOT c.da_xoa AND NOT c.da_bo AND x.thue_ngoai = b.xe_thue_ngoai
               AND NOT EXISTS (SELECT 1 FROM doixe.bang_ke_dong bd WHERE bd.chang_id = c.id)
               AND NOT EXISTS (SELECT 1 FROM doixe.thu_chang tc WHERE tc.chang_id = c.id AND tc.cuoc_tay_vnd IS NOT NULL)) cg
         WHERE cg.tid IS NOT NULL GROUP BY cg.tid) x;
    RETURN jsonb_build_object('hom_nay', d,
        'ben', jsonb_build_object('ma', b.ma, 'ten', b.ten),
        'tuyen', (SELECT coalesce(jsonb_agg(jsonb_build_object('id', t.id, 'loai', t.loai, 'hang', t.hang, 'di', t.di, 'den', t.den,
                    'ten', doixe._ten_tuyen(t), 'dang_dung', t.dang_dung,
                    'gia', (SELECT coalesce(jsonb_agg(jsonb_build_object('tu_ngay', g.tu_ngay, 'gia_vnd', g.gia_vnd::text, 'actor', g.actor,
                                'luc', doixe._luc(g.luc)) ORDER BY g.tu_ngay), '[]'::jsonb)
                            FROM doixe.gia_tuyen g WHERE g.ben = b.ma AND g.tuyen_id = t.id),
                    'ten_goc', (SELECT coalesce(jsonb_agg(g.khoa ORDER BY g.khoa), '[]'::jsonb) FROM doixe.tuyen_ten_goc g WHERE g.tuyen_id = t.id),
                    'cho_doi', coalesce(v_cho -> t.id::text, '[]'::jsonb))
                  ORDER BY NOT t.dang_dung, t.loai <> 'hang', doixe._fold(t.hang), doixe._fold(t.di), t.id), '[]'::jsonb) FROM doixe.tuyen t),
        'phat_sinh', (SELECT coalesce(jsonb_agg(jsonb_build_object('ma', p.ma, 'ten', p.ten, 'cach', p.cach, 'muc_vnd', p.muc_vnd::text,
                    'muc_them_vnd', p.muc_them_vnd::text, 'chi_ho', p.chi_ho, 'cot', p.cot, 'loai_phi', p.loai_phi,
                    'ten_goc', (SELECT coalesce(jsonb_agg(n.ten ORDER BY n.ten), '[]'::jsonb) FROM doixe.phat_sinh_ten n WHERE n.ma = p.ma))
                  ORDER BY p.thu_tu), '[]'::jsonb) FROM doixe.phat_sinh p));
END $$;

CREATE OR REPLACE FUNCTION doixe.get_lich_su_thu() RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = pg_catalog, doixe, pg_temp AS $$
-- Lịch sử phần thu (gửi, đối chiếu, điều chỉnh, tiền về, giá, tuyến, danh mục), 300 việc mới nhất.
BEGIN
    PERFORM doixe._actor();
    RETURN jsonb_build_object('events', (SELECT coalesce(jsonb_agg(jsonb_build_object('id', e.id, 'viec', e.viec, 'actor', e.actor,
            'luc', doixe._luc(e.luc), 'truoc', e.truoc, 'sau', e.sau, 'ly_do', e.ly_do) ORDER BY e.id DESC), '[]'::jsonb)
        FROM (SELECT * FROM doixe.su_kien s WHERE s.viec = ANY (doixe._viec_thu()) ORDER BY s.id DESC LIMIT 300) e));
END $$;

-- Lịch sử đội xe đợt 1 không lẫn việc thu (thân như bản đợt 1, thêm điều kiện cuối).
CREATE OR REPLACE FUNCTION doixe.get_lich_su(p_nguoi bigint, p_xe bigint) RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = pg_catalog, doixe, pg_temp AS $$
BEGIN
    PERFORM doixe._actor();
    IF p_nguoi IS NOT NULL AND p_xe IS NOT NULL THEN RAISE EXCEPTION 'INVALID_COMMAND'; END IF;
    RETURN jsonb_build_object('events', (SELECT coalesce(jsonb_agg(jsonb_build_object('id', e.id, 'viec', e.viec, 'actor', e.actor,
            'luc', doixe._luc(e.luc), 'nguoi_id', e.nguoi_id, 'tai_xe_id', e.tai_xe_id, 'xe_id', e.xe_id, 'truoc', e.truoc, 'sau', e.sau,
            'ly_do', e.ly_do) ORDER BY e.id DESC), '[]'::jsonb)
        FROM (SELECT * FROM doixe.su_kien s
               WHERE ((p_nguoi IS NULL AND p_xe IS NULL) OR s.viec = 'khoa_thang'
                      OR (p_nguoi IS NOT NULL AND (s.nguoi_id = p_nguoi OR s.tai_xe_id = p_nguoi OR (s.sau ->> 'nguoi_tra_id') = p_nguoi::text))
                      OR (p_xe IS NOT NULL AND s.xe_id = p_xe))
                 AND s.viec <> ALL (doixe._viec_thu())
               ORDER BY s.id DESC LIMIT 500) e));
END $$;

-- Danh mục phí trong mọi hàm đọc đợt 1 có thêm cờ chi hộ (thân như bản đợt 1, thêm 'chi_ho').
CREATE OR REPLACE FUNCTION doixe._chung() RETURNS jsonb
LANGUAGE sql STABLE SET search_path = pg_catalog, doixe, pg_temp AS $$
    WITH t AS (SELECT DISTINCT m FROM (
        SELECT date_trunc('month', ngay)::date AS m FROM doixe.chang WHERE NOT da_xoa
        UNION ALL SELECT date_trunc('month', ngay)::date FROM doixe.ung
        UNION ALL SELECT date_trunc('month', ngay)::date FROM doixe.dot_hoan
        UNION ALL SELECT date_trunc('month', doixe._hom_nay())::date) s)
    SELECT jsonb_build_object(
        'loai_phi', (SELECT jsonb_agg(jsonb_build_object('ma', l.ma, 'ten', l.ten, 'ten_day_du', l.ten_day_du, 'thu_tu', l.thu_tu,
                       'cot_sheet', l.cot_sheet, 'cong_ty_tra', l.cong_ty_tra, 'chi_ho', l.chi_ho) ORDER BY l.thu_tu) FROM doixe.loai_phi l),
        'danh_muc', jsonb_build_object(
            'nguoi', (SELECT coalesce(jsonb_agg(jsonb_build_object('id', n.id, 'ten', n.ten, 'vai', n.vai, 'dang_dung', n.dang_dung)
                        ORDER BY n.id), '[]'::jsonb) FROM doixe.nguoi n),
            'xe', (SELECT coalesce(jsonb_agg(jsonb_build_object('id', x.id, 'bien_so', x.bien_so, 'nhom', x.nhom, 'thue_ngoai', x.thue_ngoai,
                        'tai_xe_id', x.tai_xe_id, 'dang_dung', x.dang_dung) ORDER BY x.thue_ngoai, x.bien_so), '[]'::jsonb) FROM doixe.xe x)),
        'thang_co', (SELECT jsonb_agg(m ORDER BY m) FROM t),
        'khoa', (SELECT jsonb_object_agg(m::text, doixe._khoa(m)) FROM t))
$$;

-- ---------------------------------------------------------------------------------------------------------------------------
-- Lệnh ghi (cấp cho sokhach_app).
CREATE OR REPLACE FUNCTION doixe.gui_bang_ke(p jsonb) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, doixe, pg_temp AS $$
-- Gửi bảng kê tháng: chép các dòng đang gom (số như màn đang thấy) rồi chuyển "đã gửi". `doi_vnd`, `so_chang` là số máy người
-- gửi đang thấy: khác số hiện tại thì BANG_KE_DOI (tải lại, xem lại rồi gửi). Chặng chưa có giá vẫn gửi, ô cước trống.
DECLARE v_retry jsonb; b doixe.ben; m date; v_dong jsonb; v_tong jsonb; v_id bigint; v_so text; v_n integer;
BEGIN
    v_retry := doixe._bat_dau(p, 'gui_bang_ke');
    IF v_retry IS NOT NULL THEN RETURN v_retry; END IF;
    PERFORM doixe._chi_khoa(p, ARRAY['idempotency_key', 'thang', 'doi_vnd', 'so_chang']);
    b := doixe._ben_nhan(NULL);
    m := doixe._thang(p -> 'thang');
    IF jsonb_typeof(p -> 'so_chang') IS DISTINCT FROM 'number' OR (p -> 'so_chang')::text !~ '^(0|[1-9][0-9]{0,5})$' THEN
        RAISE EXCEPTION 'INVALID_COMMAND';
    END IF;
    IF EXISTS (SELECT 1 FROM doixe.bang_ke WHERE ben = b.ma AND thang = m) THEN RAISE EXCEPTION 'BANG_KE_DA_GUI'; END IF;
    SELECT coalesce(jsonb_agg(doixe._tinh_chang(x.id, b.ma) ORDER BY x.n), '[]'::jsonb) INTO v_dong
      FROM unnest(doixe._chang_gom(b, m)) WITH ORDINALITY AS x(id, n);
    v_n := jsonb_array_length(v_dong);
    IF v_n = 0 THEN RAISE EXCEPTION 'BANG_KE_TRONG'; END IF;
    v_tong := doixe._tong_dong(v_dong);
    IF doixe._vnd(p -> 'doi_vnd') IS DISTINCT FROM (v_tong ->> 'doi_vnd')::bigint OR (p ->> 'so_chang')::integer <> v_n THEN
        RAISE EXCEPTION 'BANG_KE_DOI';
    END IF;
    v_so := upper(b.ma) || '-' || to_char(m, 'YYYY-MM');
    INSERT INTO doixe.bang_ke(ben, thang, so, trang_thai, gui_ngay, gui_actor) VALUES (b.ma, m, v_so, 'da_gui', doixe._hom_nay(), doixe._actor())
    RETURNING id INTO v_id;
    INSERT INTO doixe.bang_ke_dong(bang_ke_id, stt, chang_id, ngay, container, loai, tinh, kho, tai_xe, so_xe, noi_lay, noi_ha, ten_hang,
                                   ghi_chu, tuyen, gia_bang_vnd, cuoc_vnd, cuoc_tay, ghep_vnd, ps_vnd, chi_ho_vnd, ps)
    SELECT v_id, x.n, (e ->> 'chang_id')::bigint, (e ->> 'ngay')::date, e ->> 'container', e ->> 'loai', e ->> 'tinh', e ->> 'kho',
           e ->> 'tai_xe', e ->> 'so_xe', e ->> 'noi_lay', e ->> 'noi_ha', e ->> 'ten_hang', e ->> 'ghi_chu', e ->> 'tuyen',
           (e ->> 'gia_bang_vnd')::bigint, (e ->> 'cuoc_vnd')::bigint, (e ->> 'cuoc_tay')::boolean, (e ->> 'ghep_vnd')::bigint,
           (e ->> 'ps_vnd')::bigint, (e ->> 'chi_ho_vnd')::bigint, e -> 'ps'
      FROM jsonb_array_elements(v_dong) WITH ORDINALITY AS x(e, n);
    PERFORM doixe._ghi('gui_bang_ke', NULL, NULL, NULL, jsonb_build_object('thang', m),
        jsonb_build_object('thang', m, 'so', v_so, 'so_chang', v_n, 'chua_gia', (v_tong ->> 'chua_gia')::integer,
                           'doi_vnd', v_tong ->> 'doi_vnd'),
        NULL, p ->> 'idempotency_key');
    RETURN doixe._xong(p, 'gui_bang_ke', jsonb_build_object('ok', true, 'bang_ke_id', v_id, 'so', v_so, 'doi_vnd', v_tong ->> 'doi_vnd',
                                                               'so_chang', v_n));
END $$;

CREATE OR REPLACE FUNCTION doixe.doi_chieu_xong(p jsonb) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, doixe, pg_temp AS $$
-- HTH đồng ý số đòi: bảng kê đã gửi chuyển "đã đối chiếu", thôi nhận điều chỉnh. `doi_vnd` là số đòi máy người bấm đang thấy.
DECLARE v_retry jsonb; b doixe.ben; m date; k doixe.bang_ke; v_doi bigint;
BEGIN
    v_retry := doixe._bat_dau(p, 'doi_chieu_xong');
    IF v_retry IS NOT NULL THEN RETURN v_retry; END IF;
    PERFORM doixe._chi_khoa(p, ARRAY['idempotency_key', 'thang', 'doi_vnd']);
    b := doixe._ben_nhan(NULL);
    m := doixe._thang(p -> 'thang');
    SELECT * INTO k FROM doixe.bang_ke WHERE ben = b.ma AND thang = m FOR UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION 'BANG_KE_CHUA_GUI'; END IF;
    IF k.trang_thai <> 'da_gui' THEN RAISE EXCEPTION 'BANG_KE_DA_DOI_CHIEU'; END IF;
    v_doi := doixe._doi_bk(k.id);
    IF doixe._vnd(p -> 'doi_vnd') IS DISTINCT FROM v_doi THEN RAISE EXCEPTION 'BANG_KE_DOI'; END IF;
    UPDATE doixe.bang_ke SET trang_thai = 'da_doi_chieu', doi_chieu_actor = doixe._actor(), doi_chieu_luc = clock_timestamp() WHERE id = k.id;
    PERFORM doixe._ghi('doi_chieu_xong', NULL, NULL, NULL, jsonb_build_object('thang', m, 'trang_thai', 'da_gui'),
        jsonb_build_object('thang', m, 'so', k.so, 'trang_thai', 'da_doi_chieu', 'doi_vnd', v_doi::text,
                           'so_dieu_chinh', (SELECT count(*) FROM doixe.dieu_chinh_bk a WHERE a.bang_ke_id = k.id)),
        NULL, p ->> 'idempotency_key');
    RETURN doixe._xong(p, 'doi_chieu_xong', jsonb_build_object('ok', true, 'doi_vnd', v_doi::text));
END $$;

CREATE OR REPLACE FUNCTION doixe.ghi_dieu_chinh_bk(p jsonb) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, doixe, pg_temp AS $$
-- Điều chỉnh một dòng của bảng kê đã gửi, chưa đối chiếu xong: số có dấu (bớt âm, thêm dương), khác 0, lý do bắt buộc; tổng dòng
-- sau điều chỉnh không âm. Lịch sử có Đòi HTH và tổng dòng trước → sau.
DECLARE v_retry jsonb; dd doixe.bang_ke_dong; k doixe.bang_ke; v_tien bigint; v_ly text; v_doi0 bigint; v_dong0 bigint; v_id bigint;
BEGIN
    v_retry := doixe._bat_dau(p, 'ghi_dieu_chinh_bk');
    IF v_retry IS NOT NULL THEN RETURN v_retry; END IF;
    PERFORM doixe._chi_khoa(p, ARRAY['idempotency_key', 'dong_id', 'so_tien_vnd', 'ly_do']);
    v_ly := doixe._chu(p -> 'ly_do', 500);
    IF v_ly IS NULL THEN RAISE EXCEPTION 'LY_DO_DIEU_CHINH'; END IF;
    v_tien := doixe._vnd_co_dau(p -> 'so_tien_vnd');
    IF v_tien IS NULL OR v_tien = 0 THEN RAISE EXCEPTION 'INVALID_VND'; END IF;
    SELECT * INTO dd FROM doixe.bang_ke_dong WHERE id = doixe._id(p, 'dong_id');
    IF NOT FOUND THEN RAISE EXCEPTION 'DONG_BK_NOT_FOUND'; END IF;
    SELECT * INTO k FROM doixe.bang_ke WHERE id = dd.bang_ke_id FOR UPDATE;
    IF k.trang_thai <> 'da_gui' THEN RAISE EXCEPTION 'BANG_KE_DA_DOI_CHIEU'; END IF;
    v_doi0 := doixe._doi_bk(k.id);
    v_dong0 := coalesce(dd.cuoc_vnd, 0) + coalesce(dd.ghep_vnd, 0) + coalesce(dd.ps_vnd, 0)
               + coalesce((SELECT sum(a.so_tien_vnd) FROM doixe.dieu_chinh_bk a WHERE a.dong_id = dd.id), 0);
    IF v_dong0 + v_tien < 0 THEN RAISE EXCEPTION 'DIEU_CHINH_AM'; END IF;
    INSERT INTO doixe.dieu_chinh_bk(bang_ke_id, dong_id, so_tien_vnd, ly_do, actor) VALUES (k.id, dd.id, v_tien, v_ly, doixe._actor())
    RETURNING id INTO v_id;
    PERFORM doixe._ghi('dieu_chinh_bk', NULL, NULL, NULL,
        jsonb_build_object('thang', k.thang, 'dong_id', dd.id, 'ngay', dd.ngay, 'container', dd.container, 'doi_vnd', v_doi0::text,
                           'dong_vnd', v_dong0::text),
        jsonb_build_object('so_tien_vnd', v_tien::text, 'doi_vnd', (v_doi0 + v_tien)::text, 'dong_vnd', (v_dong0 + v_tien)::text,
                           'dieu_chinh_id', v_id),
        v_ly, p ->> 'idempotency_key');
    RETURN doixe._xong(p, 'ghi_dieu_chinh_bk', jsonb_build_object('ok', true, 'dieu_chinh_id', v_id, 'doi_truoc_vnd', v_doi0::text,
                                                                     'doi_sau_vnd', (v_doi0 + v_tien)::text));
END $$;

CREATE OR REPLACE FUNCTION doixe.ghi_tien_ve(p jsonb) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, doixe, pg_temp AS $$
-- Tiền HTH trả cho bảng kê tháng đã đối chiếu: ngày không sau hôm nay (giờ VN), không trước ngày gửi; số dương, không lớn hơn số
-- còn phải thu (trả thừa bị chặn; trả thiếu ghi được). Trả đủ thì bảng kê thành thu đủ.
DECLARE v_retry jsonb; b doixe.ben; m date; k doixe.bang_ke; v_ngay date; v_tien bigint; v_con bigint; v_id bigint; v_ghi text;
BEGIN
    v_retry := doixe._bat_dau(p, 'ghi_tien_ve');
    IF v_retry IS NOT NULL THEN RETURN v_retry; END IF;
    PERFORM doixe._chi_khoa(p, ARRAY['idempotency_key', 'thang', 'ngay', 'so_tien_vnd', 'ghi_chu']);
    b := doixe._ben_nhan(NULL);
    m := doixe._thang(p -> 'thang');
    SELECT * INTO k FROM doixe.bang_ke WHERE ben = b.ma AND thang = m FOR UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION 'BANG_KE_CHUA_GUI'; END IF;
    IF k.trang_thai <> 'da_doi_chieu' THEN RAISE EXCEPTION 'BANG_KE_CHUA_DOI_CHIEU'; END IF;
    v_ngay := doixe._ngay(p -> 'ngay');
    IF v_ngay IS NULL THEN RAISE EXCEPTION 'INVALID_DATE'; END IF;
    IF v_ngay > doixe._hom_nay() THEN RAISE EXCEPTION 'NGAY_TUONG_LAI'; END IF;
    IF v_ngay < k.gui_ngay THEN RAISE EXCEPTION 'TIEN_VE_TRUOC_GUI'; END IF;
    v_tien := doixe._vnd(p -> 'so_tien_vnd');
    IF v_tien IS NULL OR v_tien = 0 THEN RAISE EXCEPTION 'INVALID_VND'; END IF;
    v_ghi := doixe._chu(p -> 'ghi_chu', 500);
    v_con := doixe._doi_bk(k.id) - doixe._tra_bk(k.id);
    IF v_tien > v_con THEN RAISE EXCEPTION 'TIEN_VE_THUA'; END IF;
    INSERT INTO doixe.tien_ve(bang_ke_id, ngay, so_tien_vnd, ghi_chu, actor) VALUES (k.id, v_ngay, v_tien, v_ghi, doixe._actor())
    RETURNING id INTO v_id;
    PERFORM doixe._ghi('ghi_tien_ve', NULL, NULL, NULL, jsonb_build_object('thang', m, 'con_vnd', v_con::text),
        jsonb_build_object('thang', m, 'tien_ve_id', v_id, 'ngay', v_ngay, 'so_tien_vnd', v_tien::text, 'con_vnd', (v_con - v_tien)::text,
                           'ghi_chu', v_ghi),
        NULL, p ->> 'idempotency_key');
    RETURN doixe._xong(p, 'ghi_tien_ve', jsonb_build_object('ok', true, 'tien_ve_id', v_id, 'con_truoc_vnd', v_con::text,
                                                               'con_sau_vnd', (v_con - v_tien)::text));
END $$;

CREATE OR REPLACE FUNCTION doixe.huy_tien_ve(p jsonb) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, doixe, pg_temp AS $$
-- Hủy một lần tiền về: bắt buộc lý do; vẫn hiện, gạch ngang. Bảng kê thu đủ trở lại chờ HTH trả.
DECLARE v_retry jsonb; v doixe.tien_ve; k doixe.bang_ke; v_ly text; v_con bigint;
BEGIN
    v_retry := doixe._bat_dau(p, 'huy_tien_ve');
    IF v_retry IS NOT NULL THEN RETURN v_retry; END IF;
    PERFORM doixe._chi_khoa(p, ARRAY['idempotency_key', 'tien_ve_id', 'ly_do']);
    v_ly := doixe._chu(p -> 'ly_do', 500);
    IF v_ly IS NULL THEN RAISE EXCEPTION 'LY_DO_THIEU'; END IF;
    SELECT * INTO v FROM doixe.tien_ve WHERE id = doixe._id(p, 'tien_ve_id') FOR UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION 'TIEN_VE_NOT_FOUND'; END IF;
    IF v.huy_luc IS NOT NULL THEN RAISE EXCEPTION 'DA_HUY'; END IF;
    SELECT * INTO k FROM doixe.bang_ke WHERE id = v.bang_ke_id;
    v_con := doixe._doi_bk(k.id) - doixe._tra_bk(k.id);
    UPDATE doixe.tien_ve SET huy_actor = doixe._actor(), huy_luc = clock_timestamp(), huy_ly_do = v_ly WHERE id = v.id;
    PERFORM doixe._ghi('huy_tien_ve', NULL, NULL, NULL,
        jsonb_build_object('thang', k.thang, 'tien_ve_id', v.id, 'ngay', v.ngay, 'so_tien_vnd', v.so_tien_vnd::text, 'con_vnd', v_con::text),
        jsonb_build_object('con_vnd', (v_con + v.so_tien_vnd)::text), v_ly, p ->> 'idempotency_key');
    RETURN doixe._xong(p, 'huy_tien_ve', jsonb_build_object('ok', true, 'con_truoc_vnd', v_con::text,
                                                               'con_sau_vnd', (v_con + v.so_tien_vnd)::text));
END $$;

-- Chặng sửa được phần thu: còn, chưa bỏ, chưa vào bảng kê đã gửi.
CREATE OR REPLACE FUNCTION doixe._chang_thu(p_id bigint) RETURNS doixe.chang
LANGUAGE plpgsql SET search_path = pg_catalog, doixe, pg_temp AS $$
DECLARE c doixe.chang;
BEGIN
    SELECT * INTO c FROM doixe.chang WHERE id = p_id FOR UPDATE;
    IF NOT FOUND OR c.da_xoa THEN RAISE EXCEPTION 'CHANG_NOT_FOUND'; END IF;
    IF c.da_bo THEN RAISE EXCEPTION 'CHANG_DA_BO'; END IF;
    IF EXISTS (SELECT 1 FROM doixe.bang_ke_dong d WHERE d.chang_id = c.id) THEN RAISE EXCEPTION 'CHANG_DA_GUI'; END IF;
    RETURN c;
END $$;

CREATE OR REPLACE FUNCTION doixe.sua_cuoc(p jsonb) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, doixe, pg_temp AS $$
-- Giá cước nhập tay của một chặng chưa gửi. `truoc`: giá tay máy người sửa đang thấy (null: đang theo bảng giá), khác thì CHANGED.
-- `gia_tri` null hoặc bằng giá bảng: theo bảng giá (đổi giá bảng thì đổi theo).
DECLARE v_retry jsonb; b doixe.ben; c doixe.chang; tc doixe.thu_chang; t doixe.tuyen; v_bang bigint; v_moi bigint; v_desc jsonb;
BEGIN
    v_retry := doixe._bat_dau(p, 'sua_cuoc');
    IF v_retry IS NOT NULL THEN RETURN v_retry; END IF;
    PERFORM doixe._chi_khoa(p, ARRAY['idempotency_key', 'chang_id', 'truoc', 'gia_tri']);
    IF NOT (p ? 'truoc' AND p ? 'gia_tri') THEN RAISE EXCEPTION 'INVALID_COMMAND'; END IF;
    b := doixe._ben_nhan(NULL);
    c := doixe._chang_thu(doixe._id(p, 'chang_id'));
    SELECT * INTO tc FROM doixe.thu_chang WHERE chang_id = c.id FOR UPDATE;
    IF doixe._vnd(p -> 'truoc') IS DISTINCT FROM tc.cuoc_tay_vnd THEN RAISE EXCEPTION 'CHANGED'; END IF;
    SELECT * INTO t FROM doixe.tuyen WHERE id = doixe._tuyen_chang(c);
    v_bang := doixe._gia_bang(b.ma, c.loai, t, c.ngay);
    v_moi := doixe._vnd(p -> 'gia_tri');
    IF v_moi IS NOT DISTINCT FROM v_bang THEN v_moi := NULL; END IF;
    IF v_moi IS NOT DISTINCT FROM tc.cuoc_tay_vnd THEN
        RETURN doixe._xong(p, 'sua_cuoc', jsonb_build_object('ok', true, 'khong_doi', true));
    END IF;
    INSERT INTO doixe.thu_chang(chang_id, cuoc_tay_vnd, actor) VALUES (c.id, v_moi, doixe._actor())
    ON CONFLICT (chang_id) DO UPDATE SET cuoc_tay_vnd = EXCLUDED.cuoc_tay_vnd, actor = EXCLUDED.actor, luc = clock_timestamp();
    v_desc := jsonb_build_object('chang_id', c.id, 'ngay', c.ngay, 'container', c.container, 'thang', doixe._thang_gom(b.ma, c.ngay));
    PERFORM doixe._ghi('sua_cuoc', NULL, c.tai_xe_id, c.xe_id,
        v_desc || jsonb_build_object('cuoc_vnd', coalesce(tc.cuoc_tay_vnd, v_bang)::text, 'cuoc_tay', tc.cuoc_tay_vnd IS NOT NULL),
        jsonb_build_object('cuoc_vnd', coalesce(v_moi, v_bang)::text, 'cuoc_tay', v_moi IS NOT NULL, 'gia_bang_vnd', v_bang::text),
        NULL, p ->> 'idempotency_key');
    RETURN doixe._xong(p, 'sua_cuoc', jsonb_build_object('ok', true, 'cuoc_vnd', coalesce(v_moi, v_bang)::text, 'cuoc_tay', v_moi IS NOT NULL));
END $$;

CREATE OR REPLACE FUNCTION doixe.gan_tuyen(p jsonb) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, doixe, pg_temp AS $$
-- Gắn tuyến cho chặng chưa gửi. `nho` = true: nhớ tên gốc (TÊN HÀNG|TỈNH của chặng) cho tuyến này, mọi chặng ghi giống thế nhận
-- theo; tuyen_id null + nhớ: bỏ tên gốc đó. `nho` = false: chỉ chặng này (tuyen_id null: bỏ gắn tay).
DECLARE v_retry jsonb; b doixe.ben; c doixe.chang; v_tuyen bigint; v_nho boolean; v_khoa text; v_truoc bigint; v_cu bigint; v_n integer;
BEGIN
    v_retry := doixe._bat_dau(p, 'gan_tuyen');
    IF v_retry IS NOT NULL THEN RETURN v_retry; END IF;
    PERFORM doixe._chi_khoa(p, ARRAY['idempotency_key', 'chang_id', 'tuyen_id', 'nho']);
    IF NOT p ? 'tuyen_id' OR jsonb_typeof(p -> 'nho') IS DISTINCT FROM 'boolean' THEN RAISE EXCEPTION 'INVALID_COMMAND'; END IF;
    b := doixe._ben_nhan(NULL);
    c := doixe._chang_thu(doixe._id(p, 'chang_id'));
    v_tuyen := doixe._id(p, 'tuyen_id', true);
    IF v_tuyen IS NOT NULL AND NOT EXISTS (SELECT 1 FROM doixe.tuyen WHERE id = v_tuyen AND dang_dung) THEN RAISE EXCEPTION 'TUYEN_NOT_FOUND'; END IF;
    v_nho := (p ->> 'nho')::boolean;
    v_truoc := doixe._tuyen_chang(c);
    IF v_nho THEN
        v_khoa := doixe._khoa_tuyen(c.ten_hang, c.tinh);
        IF v_khoa = '|' OR v_khoa !~ '^[A-Z0-9 ]*\|[A-Z0-9 ]*$' OR char_length(v_khoa) > 260 THEN RAISE EXCEPTION 'KHONG_CO_TEN_GOC'; END IF;
        SELECT tuyen_id INTO v_cu FROM doixe.tuyen_ten_goc WHERE khoa = v_khoa FOR UPDATE;
        IF v_tuyen IS NULL THEN
            DELETE FROM doixe.tuyen_ten_goc WHERE khoa = v_khoa;
        ELSE
            INSERT INTO doixe.tuyen_ten_goc(khoa, tuyen_id, actor) VALUES (v_khoa, v_tuyen, doixe._actor())
            ON CONFLICT (khoa) DO UPDATE SET tuyen_id = EXCLUDED.tuyen_id, actor = EXCLUDED.actor, luc = clock_timestamp();
        END IF;
        UPDATE doixe.thu_chang SET tuyen_id = NULL WHERE chang_id = c.id AND tuyen_id IS NOT NULL;
        SELECT count(*) INTO v_n FROM doixe.chang o JOIN doixe.xe x ON x.id = o.xe_id
         WHERE NOT o.da_xoa AND NOT o.da_bo AND x.thue_ngoai = b.xe_thue_ngoai AND doixe._khoa_tuyen(o.ten_hang, o.tinh) = v_khoa
           AND NOT EXISTS (SELECT 1 FROM doixe.bang_ke_dong d WHERE d.chang_id = o.id);
    ELSE
        INSERT INTO doixe.thu_chang(chang_id, tuyen_id, actor) VALUES (c.id, v_tuyen, doixe._actor())
        ON CONFLICT (chang_id) DO UPDATE SET tuyen_id = EXCLUDED.tuyen_id, actor = EXCLUDED.actor, luc = clock_timestamp();
        v_n := 1;
    END IF;
    PERFORM doixe._ghi('gan_tuyen', NULL, c.tai_xe_id, c.xe_id,
        jsonb_build_object('chang_id', c.id, 'ngay', c.ngay, 'container', c.container, 'tuyen_id', v_truoc, 'khoa', v_khoa,
                           'khoa_tuyen_id', v_cu),
        jsonb_build_object('tuyen_id', v_tuyen, 'nho', v_nho, 'so_chang', v_n), NULL, p ->> 'idempotency_key');
    RETURN doixe._xong(p, 'gan_tuyen', jsonb_build_object('ok', true, 'so_chang', v_n));
END $$;

CREATE OR REPLACE FUNCTION doixe.luu_gia(p jsonb) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, doixe, pg_temp AS $$
-- Giá tuyến áp dụng từ ngày (cùng ngày thì thay giá). Tháng đã gửi giữ số đã chép; chặng đang gom theo bảng giá từ ngày đó đổi
-- theo (Lịch sử ghi số chặng đổi). Ngày áp dụng được sau hôm nay (giá đã báo trước), tới một năm.
DECLARE v_retry jsonb; b doixe.ben; t doixe.tuyen; v_tu date; v_gia bigint; v_cu bigint; v_hien bigint; v_n integer;
BEGIN
    v_retry := doixe._bat_dau(p, 'luu_gia');
    IF v_retry IS NOT NULL THEN RETURN v_retry; END IF;
    PERFORM doixe._chi_khoa(p, ARRAY['idempotency_key', 'tuyen_id', 'tu_ngay', 'gia_vnd']);
    b := doixe._ben_nhan(NULL);
    SELECT * INTO t FROM doixe.tuyen WHERE id = doixe._id(p, 'tuyen_id') AND dang_dung;
    IF NOT FOUND THEN RAISE EXCEPTION 'TUYEN_NOT_FOUND'; END IF;
    v_tu := doixe._ngay(p -> 'tu_ngay');
    IF v_tu IS NULL THEN RAISE EXCEPTION 'INVALID_DATE'; END IF;
    IF v_tu > doixe._hom_nay() + 366 THEN RAISE EXCEPTION 'NGAY_GIA_XA'; END IF;
    v_gia := doixe._vnd(p -> 'gia_vnd');
    IF v_gia IS NULL OR v_gia = 0 THEN RAISE EXCEPTION 'INVALID_VND'; END IF;
    SELECT gia_vnd INTO v_cu FROM doixe.gia_tuyen WHERE ben = b.ma AND tuyen_id = t.id AND tu_ngay = v_tu FOR UPDATE;
    v_hien := doixe._gia(b.ma, t.id, v_tu);
    IF v_cu IS NOT DISTINCT FROM v_gia THEN
        RETURN doixe._xong(p, 'luu_gia', jsonb_build_object('ok', true, 'khong_doi', true, 'so_chang', 0));
    END IF;
    -- Chặng đang gom theo bảng giá của tuyến này, ngày từ ngày áp dụng và trước bản giá kế tiếp (bản sau vẫn quyết định ngày của nó).
    SELECT count(*) INTO v_n FROM doixe.chang c JOIN doixe.xe x ON x.id = c.xe_id
     WHERE NOT c.da_xoa AND NOT c.da_bo AND x.thue_ngoai = b.xe_thue_ngoai AND c.ngay >= v_tu
       AND NOT EXISTS (SELECT 1 FROM doixe.gia_tuyen g WHERE g.ben = b.ma AND g.tuyen_id = t.id AND g.tu_ngay > v_tu AND g.tu_ngay <= c.ngay)
       AND NOT EXISTS (SELECT 1 FROM doixe.bang_ke_dong d WHERE d.chang_id = c.id)
       AND NOT EXISTS (SELECT 1 FROM doixe.thu_chang tc WHERE tc.chang_id = c.id AND tc.cuoc_tay_vnd IS NOT NULL)
       AND (c.loai IN ('hang', 'rut_mooc', 'tha_mooc') AND t.loai = 'hang' OR c.loai = t.loai)
       AND doixe._tuyen_chang(c) = t.id;
    INSERT INTO doixe.gia_tuyen(ben, tuyen_id, tu_ngay, gia_vnd, actor) VALUES (b.ma, t.id, v_tu, v_gia, doixe._actor())
    ON CONFLICT (ben, tuyen_id, tu_ngay) DO UPDATE SET gia_vnd = EXCLUDED.gia_vnd, actor = EXCLUDED.actor, luc = clock_timestamp();
    PERFORM doixe._ghi('sua_gia', NULL, NULL, NULL,
        jsonb_build_object('tuyen_id', t.id, 'tuyen', doixe._ten_tuyen(t), 'tu_ngay', v_tu, 'gia_vnd', v_cu::text, 'gia_truoc_vnd', v_hien::text),
        jsonb_build_object('tuyen_id', t.id, 'tu_ngay', v_tu, 'gia_vnd', v_gia::text, 'so_chang', v_n),
        NULL, p ->> 'idempotency_key');
    RETURN doixe._xong(p, 'luu_gia', jsonb_build_object('ok', true, 'so_chang', v_n));
END $$;

CREATE OR REPLACE FUNCTION doixe.luu_tuyen(p jsonb) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, doixe, pg_temp AS $$
-- Thêm tuyến (tuyen_id null, kèm giá đầu và ngày áp dụng) hoặc sửa tên, ngưng dùng, tên gốc của tuyến. `ten_goc`: danh sách
-- {hang, tinh} thay cả bộ tên gốc của tuyến; tên gốc đang thuộc tuyến khác thì TEN_GOC_TRUNG.
DECLARE v_retry jsonb; b doixe.ben; t doixe.tuyen; v_id bigint; v_loai text; v_hang text; v_di text; v_den text; v_dung boolean;
        v_khoa text[]; r jsonb; v_k text; v_truoc jsonb; v_gia bigint; v_tu date;
BEGIN
    v_retry := doixe._bat_dau(p, 'luu_tuyen');
    IF v_retry IS NOT NULL THEN RETURN v_retry; END IF;
    PERFORM doixe._chi_khoa(p, ARRAY['idempotency_key', 'tuyen_id', 'loai', 'hang', 'di', 'den', 'dang_dung', 'ten_goc', 'gia_vnd', 'tu_ngay']);
    b := doixe._ben_nhan(NULL);
    v_id := doixe._id(p, 'tuyen_id', true);
    v_loai := p ->> 'loai';
    IF v_loai IS NULL OR v_loai NOT IN ('hang', 'chuyen_cang', 'tra_rong') THEN RAISE EXCEPTION 'INVALID_COMMAND'; END IF;
    v_hang := doixe._chu(p -> 'hang', 60);
    v_di := doixe._chu(p -> 'di', 100);
    v_den := doixe._chu(p -> 'den', 100);
    IF v_di IS NULL OR (v_loai = 'hang') <> (v_hang IS NOT NULL) THEN RAISE EXCEPTION 'TUYEN_THIEU'; END IF;
    v_dung := coalesce((p ->> 'dang_dung')::boolean, true);
    IF jsonb_typeof(coalesce(p -> 'ten_goc', '[]'::jsonb)) <> 'array' OR jsonb_array_length(coalesce(p -> 'ten_goc', '[]'::jsonb)) > 50 THEN
        RAISE EXCEPTION 'INVALID_COMMAND';
    END IF;
    v_khoa := '{}';
    FOR r IN SELECT * FROM jsonb_array_elements(coalesce(p -> 'ten_goc', '[]'::jsonb)) LOOP
        PERFORM doixe._chi_khoa(r, ARRAY['hang', 'tinh']);
        v_k := doixe._khoa_tuyen(doixe._chu(r -> 'hang', 120), doixe._chu(r -> 'tinh', 120));
        IF v_k = '|' OR v_k !~ '^[A-Z0-9 ]*\|[A-Z0-9 ]*$' OR char_length(v_k) > 260 THEN RAISE EXCEPTION 'TEN_GOC_LA'; END IF;
        IF NOT v_k = ANY (v_khoa) THEN v_khoa := v_khoa || v_k; END IF;
    END LOOP;
    IF v_id IS NULL THEN
        v_gia := doixe._vnd(p -> 'gia_vnd');
        v_tu := doixe._ngay(p -> 'tu_ngay');
        IF v_gia IS NULL OR v_gia = 0 THEN RAISE EXCEPTION 'INVALID_VND'; END IF;
        IF v_tu IS NULL THEN RAISE EXCEPTION 'INVALID_DATE'; END IF;
        IF v_tu > doixe._hom_nay() + 366 THEN RAISE EXCEPTION 'NGAY_GIA_XA'; END IF;
        IF NOT v_dung THEN RAISE EXCEPTION 'INVALID_COMMAND'; END IF;
    ELSE
        IF p ? 'gia_vnd' OR p ? 'tu_ngay' THEN RAISE EXCEPTION 'INVALID_COMMAND'; END IF;
        SELECT * INTO t FROM doixe.tuyen WHERE id = v_id FOR UPDATE;
        IF NOT FOUND THEN RAISE EXCEPTION 'TUYEN_NOT_FOUND'; END IF;
        IF t.loai <> v_loai THEN RAISE EXCEPTION 'INVALID_COMMAND'; END IF;
        v_truoc := jsonb_build_object('tuyen_id', t.id, 'ten', doixe._ten_tuyen(t), 'dang_dung', t.dang_dung,
            'ten_goc', (SELECT coalesce(jsonb_agg(g.khoa ORDER BY g.khoa), '[]'::jsonb) FROM doixe.tuyen_ten_goc g WHERE g.tuyen_id = t.id));
    END IF;
    IF v_dung AND EXISTS (SELECT 1 FROM doixe.tuyen o WHERE o.dang_dung AND o.id IS DISTINCT FROM v_id AND o.loai = v_loai
                          AND coalesce(doixe._fold(o.hang), '') = coalesce(doixe._fold(v_hang), '') AND doixe._fold(o.di) = doixe._fold(v_di)
                          AND coalesce(doixe._fold(o.den), '') = coalesce(doixe._fold(v_den), '')) THEN
        RAISE EXCEPTION 'TUYEN_TRUNG';
    END IF;
    IF EXISTS (SELECT 1 FROM doixe.tuyen_ten_goc g WHERE g.khoa = ANY (v_khoa) AND g.tuyen_id IS DISTINCT FROM v_id) THEN
        RAISE EXCEPTION 'TEN_GOC_TRUNG';
    END IF;
    IF v_id IS NULL THEN
        INSERT INTO doixe.tuyen(loai, hang, di, den, actor) VALUES (v_loai, v_hang, v_di, v_den, doixe._actor()) RETURNING * INTO t;
        INSERT INTO doixe.gia_tuyen(ben, tuyen_id, tu_ngay, gia_vnd, actor) VALUES (b.ma, t.id, v_tu, v_gia, doixe._actor());
        v_truoc := '{}'::jsonb;
    ELSE
        UPDATE doixe.tuyen SET hang = v_hang, di = v_di, den = v_den, dang_dung = v_dung WHERE id = v_id RETURNING * INTO t;
        DELETE FROM doixe.tuyen_ten_goc WHERE tuyen_id = t.id AND NOT khoa = ANY (v_khoa);
    END IF;
    INSERT INTO doixe.tuyen_ten_goc(khoa, tuyen_id, actor) SELECT k, t.id, doixe._actor() FROM unnest(v_khoa) k
    ON CONFLICT (khoa) DO NOTHING;
    PERFORM doixe._ghi('luu_tuyen', NULL, NULL, NULL, v_truoc,
        jsonb_build_object('tuyen_id', t.id, 'ten', doixe._ten_tuyen(t), 'dang_dung', t.dang_dung, 'ten_goc', to_jsonb(v_khoa),
                           'gia_vnd', v_gia::text, 'tu_ngay', v_tu),
        NULL, p ->> 'idempotency_key');
    RETURN doixe._xong(p, 'luu_tuyen', jsonb_build_object('ok', true, 'tuyen_id', t.id));
END $$;

CREATE OR REPLACE FUNCTION doixe.luu_phat_sinh(p jsonb) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, doixe, pg_temp AS $$
-- Thêm hoặc sửa một khoản phát sinh: tên, cách tính, mức, chi hộ, cột trên bảng kê, tên đọc được trong ghi chú (thay cả bộ; tên đang
-- thuộc khoản khác thì TEN_GOC_TRUNG). Chỉ đổi cách đọc ghi chú của tháng đang gom; tháng đã gửi giữ số đã chép.
DECLARE v_retry jsonb; ps doixe.phat_sinh; v_ma text; v_ten text; v_cach text; v_muc bigint; v_them bigint; v_chiho boolean; v_cot text;
        v_tens text[]; v_t text; r jsonb; v_truoc jsonb;
BEGIN
    v_retry := doixe._bat_dau(p, 'luu_phat_sinh');
    IF v_retry IS NOT NULL THEN RETURN v_retry; END IF;
    PERFORM doixe._chi_khoa(p, ARRAY['idempotency_key', 'ma', 'ten', 'cach', 'muc_vnd', 'muc_them_vnd', 'chi_ho', 'cot', 'ten_goc']);
    v_ma := p ->> 'ma';
    IF v_ma IS NULL OR v_ma !~ '^[a-z_]{2,16}$' THEN RAISE EXCEPTION 'INVALID_COMMAND'; END IF;
    v_ten := doixe._chu(p -> 'ten', 40);
    v_cach := p ->> 'cach';
    v_cot := coalesce(p ->> 'cot', 'ps');
    IF v_ten IS NULL OR v_cach IS NULL OR v_cach NOT IN ('co_dinh', 'theo_ngay', 'theo_don_vi', 'nhap_tay') OR v_cot NOT IN ('ps', 'ghep')
       OR jsonb_typeof(p -> 'chi_ho') IS DISTINCT FROM 'boolean' THEN
        RAISE EXCEPTION 'INVALID_COMMAND';
    END IF;
    v_chiho := (p ->> 'chi_ho')::boolean;
    v_muc := doixe._vnd(p -> 'muc_vnd');
    v_them := doixe._vnd(p -> 'muc_them_vnd');
    IF v_muc = 0 OR (v_cach = 'nhap_tay' AND v_muc IS NOT NULL) OR (v_cach <> 'theo_ngay' AND v_them IS NOT NULL) THEN
        RAISE EXCEPTION 'MUC_PHAT_SINH';
    END IF;
    IF jsonb_typeof(p -> 'ten_goc') IS DISTINCT FROM 'array' OR jsonb_array_length(p -> 'ten_goc') NOT BETWEEN 1 AND 20 THEN
        RAISE EXCEPTION 'TEN_GOC_LA';
    END IF;
    v_tens := '{}';
    FOR r IN SELECT * FROM jsonb_array_elements(p -> 'ten_goc') LOOP
        v_t := doixe._fold(doixe._chu(r, 40));
        IF v_t IS NULL OR v_t !~ '^[A-Z0-9]+( [A-Z0-9]+)*$' THEN RAISE EXCEPTION 'TEN_GOC_LA'; END IF;
        IF NOT v_t = ANY (v_tens) THEN v_tens := v_tens || v_t; END IF;
    END LOOP;
    IF EXISTS (SELECT 1 FROM doixe.phat_sinh_ten n WHERE n.ten = ANY (v_tens) AND n.ma <> v_ma) THEN RAISE EXCEPTION 'TEN_GOC_TRUNG'; END IF;
    SELECT * INTO ps FROM doixe.phat_sinh WHERE ma = v_ma FOR UPDATE;
    IF FOUND THEN
        v_truoc := jsonb_build_object('ma', ps.ma, 'ten', ps.ten, 'cach', ps.cach, 'muc_vnd', ps.muc_vnd::text, 'muc_them_vnd', ps.muc_them_vnd::text,
            'chi_ho', ps.chi_ho, 'cot', ps.cot,
            'ten_goc', (SELECT coalesce(jsonb_agg(n.ten ORDER BY n.ten), '[]'::jsonb) FROM doixe.phat_sinh_ten n WHERE n.ma = ps.ma));
        UPDATE doixe.phat_sinh SET ten = v_ten, cach = v_cach, muc_vnd = v_muc, muc_them_vnd = v_them, chi_ho = v_chiho, cot = v_cot,
            actor = doixe._actor(), luc = clock_timestamp() WHERE ma = v_ma;
    ELSE
        v_truoc := '{}'::jsonb;
        INSERT INTO doixe.phat_sinh(ma, ten, cach, muc_vnd, muc_them_vnd, chi_ho, cot, thu_tu, actor)
        VALUES (v_ma, v_ten, v_cach, v_muc, v_them, v_chiho, v_cot, (SELECT coalesce(max(thu_tu), 0) + 1 FROM doixe.phat_sinh), doixe._actor());
    END IF;
    DELETE FROM doixe.phat_sinh_ten WHERE ma = v_ma AND NOT ten = ANY (v_tens);
    INSERT INTO doixe.phat_sinh_ten(ten, ma) SELECT x, v_ma FROM unnest(v_tens) x ON CONFLICT (ten) DO NOTHING;
    PERFORM doixe._ghi('luu_phat_sinh', NULL, NULL, NULL, v_truoc,
        jsonb_build_object('ma', v_ma, 'ten', v_ten, 'cach', v_cach, 'muc_vnd', v_muc::text, 'muc_them_vnd', v_them::text, 'chi_ho', v_chiho,
                           'cot', v_cot, 'ten_goc', to_jsonb(v_tens)),
        NULL, p ->> 'idempotency_key');
    RETURN doixe._xong(p, 'luu_phat_sinh', jsonb_build_object('ok', true));
END $$;

-- Quyền: hàm đọc và lệnh ghi mới cho app; hàm phụ không cấp ai. Không quyền trên bảng.
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA doixe FROM PUBLIC;
REVOKE ALL ON ALL TABLES IN SCHEMA doixe FROM PUBLIC;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA doixe FROM PUBLIC;
GRANT EXECUTE ON FUNCTION doixe.get_bang_ke(text, date), doixe.get_bang_gia(text), doixe.get_lich_su_thu(),
    doixe.gui_bang_ke(jsonb), doixe.doi_chieu_xong(jsonb), doixe.ghi_dieu_chinh_bk(jsonb), doixe.ghi_tien_ve(jsonb), doixe.huy_tien_ve(jsonb),
    doixe.sua_cuoc(jsonb), doixe.gan_tuyen(jsonb), doixe.luu_gia(jsonb), doixe.luu_tuyen(jsonb), doixe.luu_phat_sinh(jsonb) TO sokhach_app;
COMMIT;
