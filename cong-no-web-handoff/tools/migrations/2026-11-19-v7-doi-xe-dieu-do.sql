-- Đội xe: điều độ, chặng sinh từ booking (DOI-XE-DIEU-DO-01, 19/11/2026; specs/doi-xe-dieu-do-01.md, bước 3 phần 1: schema, lệnh
-- ghi). Nối vào schema `doixe`, áp sau 2026-11-18-v7-doi-xe.sql, ...-doi-xe-phieu-chi.sql, ...-doi-xe-thu.sql và
-- ...-doi-xe-thu-doc-ghi-chu.sql. Chỉ đọc `sokhach` (tuyến chuyến khách), không ghi bảng nào của `sokhach`. Chạy lại được.
-- Không đổi luật tiền, khóa tháng, hoàn, bảng kê; không seed dữ liệu nào (kể cả mã nhà xe).
--
-- * `chang` thêm `ngay_dong` (ngày đóng của việc mà chặng phục vụ) và `nguon` (điều độ / nhập chi phí / nạp). Chặng đã có trước
--   migration này giữ NULL cả hai: "có trước điều độ", không đoán là nhập hay nạp (Lịch sử `them_chang` không phân biệt được hai
--   đường). Chặng mới từ `luu_chang` tự mang nguon = 'nhap' nhờ giá trị mặc định của cột; chặng từ `phan_xe` mang 'dieu_do'.
-- * Danh mục `ma_nha_xe`: mã nhà xe trên booking mà đội xe nhận, lưu nguyên văn (sau khi cắt khoảng trắng hai đầu). Nạp bằng
--   `nap_nha_xe` như `nap_danh_muc`: công cụ nạp, không cấp cho app, mỗi lần nạp ghi Lịch sử trước → sau. Chọn cách này vì danh sách
--   chỉ vài mã và đổi hiếm; lệnh có mã yêu cầu trên web thuộc màn quản trị, chưa có trong phạm vi.
-- * Luật nối việc ↔ chặng nằm ở MỘT chỗ (`_cach_viec`, `_viec_cua`, `_chang_cua_viec`, `_chang_hang`); `get_dieu_do` (đọc) và
--   `phan_xe` (ghi) cùng gọi chúng. Việc = (container, ngày đóng) đọc từ bản chụp booking, không có bảng "việc".
-- * Lệnh ghi theo mẫu `luu_chang`: `_bat_dau` (khóa tư vấn chung + mã yêu cầu), `_actor`, `_ghi` Lịch sử trước → sau, `_xong`.
--   `bo_phan_cong` dùng chung thân xóa/bỏ với `xoa_chang` (`_xoa_chang_thuc`), không có đường xóa riêng.
-- Lưu ý thứ tự: chạy lại file đợt 2 (...-doi-xe-thu.sql) SAU file này sẽ thu hẹp ràng buộc `su_kien_viec`; chạy lại file này sau đó.
BEGIN;
SET LOCAL ROLE sokhach_owner;

-- ---------------------------------------------------------------------------------------------------------------------------
-- Chặng: ngày đóng của việc và nguồn tạo.
ALTER TABLE doixe.chang ADD COLUMN IF NOT EXISTS ngay_dong date;
ALTER TABLE doixe.chang ADD COLUMN IF NOT EXISTS nguon text CHECK (nguon IN ('dieu_do', 'nhap', 'nap'));
-- Giá trị mặc định chỉ áp cho dòng thêm sau này; chặng đã có giữ NULL.
ALTER TABLE doixe.chang ALTER COLUMN nguon SET DEFAULT 'nhap';
COMMENT ON COLUMN doixe.chang.ngay_dong IS 'DOI-XE-DIEU-DO-01: ngày đóng hàng của việc (dòng booking) mà chặng phục vụ; NULL với chặng ngoài booking, chặng giữ lại ngoài booking và chặng có trước điều độ.';
COMMENT ON COLUMN doixe.chang.nguon IS 'DOI-XE-DIEU-DO-01: dieu_do (phân xe trên màn Điều độ), nhap (nhập chi phí), nap (nạp dữ liệu cũ). NULL: chặng có trước điều độ, không rõ.';
-- Tìm chặng theo container khi nối với việc.
CREATE INDEX IF NOT EXISTS chang_container ON doixe.chang (container, ngay) WHERE NOT da_xoa;

CREATE TABLE IF NOT EXISTS doixe.ma_nha_xe (
    ma text PRIMARY KEY CHECK (ma <> '' AND ma = btrim(ma) AND char_length(ma) <= 60 AND ma !~ '[[:cntrl:]]'),
    dang_dung boolean NOT NULL DEFAULT true,
    actor text NOT NULL CHECK (btrim(actor) <> ''),
    luc timestamptz NOT NULL DEFAULT clock_timestamp()
);
COMMENT ON TABLE doixe.ma_nha_xe IS 'Mã nhà xe trên booking mà đội xe nhận (nguyên văn, so nguyên mã, không so chuỗi con). Nạp bằng nap_nha_xe; không xóa, ngừng nhận thì đặt dang_dung = false.';
CREATE OR REPLACE TRIGGER ma_nha_xe_khong_xoa BEFORE DELETE ON doixe.ma_nha_xe FOR EACH ROW EXECUTE FUNCTION doixe._chan_sua();

-- Lịch sử: thêm các việc điều độ (đổi ràng buộc theo mẫu đợt 2: bỏ ràng buộc loại việc cũ rồi thêm lại đủ danh sách).
DO $$
DECLARE r record;
BEGIN
    FOR r IN SELECT conname FROM pg_constraint WHERE conrelid = 'doixe.su_kien'::regclass AND contype = 'c'
                AND pg_get_constraintdef(oid) LIKE '%''khoa_thang''%' LOOP
        EXECUTE format('ALTER TABLE doixe.su_kien DROP CONSTRAINT %I', r.conname);
    END LOOP;
END $$;
ALTER TABLE doixe.su_kien ADD CONSTRAINT su_kien_viec CHECK (viec IN (
    'nap', 'them_chang', 'sua_chang', 'dieu_chinh', 'doi_nguoi_tra', 'xoa_chang', 'bo_chang', 'ghi_ung', 'huy_ung', 'ghi_hoan', 'huy_hoan',
    'khoa_thang', 'gui_bang_ke', 'doi_chieu_xong', 'dieu_chinh_bk', 'ghi_tien_ve', 'huy_tien_ve', 'sua_cuoc', 'gan_tuyen', 'sua_gia',
    'luu_tuyen', 'luu_phat_sinh', 'phan_xe', 'doi_phan_cong', 'bo_phan_cong', 'nhan_booking'));

-- ---------------------------------------------------------------------------------------------------------------------------
-- Luật nối việc ↔ chặng (hàm phụ, không cấp cho ai). Việc = (container, ngày đóng).
-- Khoảng cách (số ngày) giữa chặng và việc, NULL khi không nối được: cùng container (so nguyên chuỗi); chặng có ngày đóng thì lệch
-- không quá 3 ngày (NGUON-CHUYEN-01, chịu được Sheet sửa ngày); chặng chưa có ngày đóng (có trước điều độ, hoặc giữ ngoài booking)
-- thì theo ngày chạy, lệch không quá 10 ngày như đợt 1.
CREATE OR REPLACE FUNCTION doixe._cach_viec(p_cont_chang text, p_ngay date, p_ngay_dong date, p_cont text, p_dong date) RETURNS integer
LANGUAGE sql IMMUTABLE SET search_path = pg_catalog, doixe, pg_temp AS $$
    SELECT CASE WHEN p_cont_chang IS DISTINCT FROM p_cont OR p_dong IS NULL THEN NULL
                WHEN p_ngay_dong IS NOT NULL THEN CASE WHEN abs(p_ngay_dong - p_dong) <= 3 THEN abs(p_ngay_dong - p_dong) END
                ELSE CASE WHEN abs(p_ngay - p_dong) <= 10 THEN abs(p_ngay - p_dong) END
           END
$$;

-- Ngày đóng của việc mà chặng phục vụ trong tập việc cùng container `p_dongs`: việc gần nhất, bằng nhau thì việc sớm hơn.
-- Một chặng chỉ thuộc một việc, nên hai việc cùng container gần nhau không tranh nhau một chặng.
CREATE OR REPLACE FUNCTION doixe._viec_cua(c doixe.chang, p_cont text, p_dongs date[]) RETURNS date
LANGUAGE sql IMMUTABLE SET search_path = pg_catalog, doixe, pg_temp AS $$
    SELECT x FROM unnest(p_dongs) x WHERE doixe._cach_viec(c.container, c.ngay, c.ngay_dong, p_cont, x) IS NOT NULL
     ORDER BY doixe._cach_viec(c.container, c.ngay, c.ngay_dong, p_cont, x), x LIMIT 1
$$;

-- Chặng chưa xóa, chưa bỏ của một việc. `p_khac`: ngày đóng của các việc khác cùng container mà người gọi biết (từ booking).
CREATE OR REPLACE FUNCTION doixe._chang_cua_viec(p_cont text, p_dong date, p_khac date[] DEFAULT '{}')
RETURNS TABLE(chang_id bigint, loai_chang text, cach integer)
LANGUAGE sql STABLE SET search_path = pg_catalog, doixe, pg_temp AS $$
    SELECT c.id, c.loai, doixe._cach_viec(c.container, c.ngay, c.ngay_dong, p_cont, p_dong)
      FROM doixe.chang c
     WHERE c.container = p_cont AND NOT c.da_xoa AND NOT c.da_bo
       AND doixe._cach_viec(c.container, c.ngay, c.ngay_dong, p_cont, p_dong) IS NOT NULL
       AND doixe._viec_cua(c, p_cont, array_append(coalesce(p_khac, '{}'), p_dong)) = p_dong
$$;

-- Chặng hàng của việc (nhiều nhất một khi ghi qua phan_xe); chặng cũ có hai chặng hàng cùng việc thì lấy chặng gần nhất.
CREATE OR REPLACE FUNCTION doixe._chang_hang(p_cont text, p_dong date, p_khac date[] DEFAULT '{}') RETURNS bigint
LANGUAGE sql STABLE SET search_path = pg_catalog, doixe, pg_temp AS $$
    SELECT k.chang_id FROM doixe._chang_cua_viec(p_cont, p_dong, p_khac) k WHERE k.loai_chang = 'hang' ORDER BY k.cach, k.chang_id LIMIT 1
$$;

-- Lý do khóa chặng khỏi màn Điều độ, theo thứ tự: đã lên bảng kê đã gửi, đã hoàn, đã có phí. NULL: tự do.
-- Chặng thuộc những trường hợp này chỉ đổi ở sổ tài xế (điều chỉnh) hoặc Bảng kê.
CREATE OR REPLACE FUNCTION doixe._ly_khoa_chang(p_id bigint) RETURNS text
LANGUAGE sql STABLE SET search_path = pg_catalog, doixe, pg_temp AS $$
    SELECT CASE
        WHEN EXISTS (SELECT 1 FROM doixe.bang_ke_dong d WHERE d.chang_id = p_id) THEN 'CHANG_DA_GUI'
        WHEN EXISTS (SELECT 1 FROM doixe.dong dd WHERE dd.chang_id = p_id AND dd.dot_hoan_id IS NOT NULL) THEN 'CHANG_DA_HOAN'
        WHEN EXISTS (SELECT 1 FROM doixe.dong dd JOIN doixe.dong_phi f ON f.dong_id = dd.id WHERE dd.chang_id = p_id) THEN 'CHANG_CO_PHI'
    END
$$;

CREATE OR REPLACE FUNCTION doixe._nha_xe_json() RETURNS jsonb
LANGUAGE sql STABLE SET search_path = pg_catalog, doixe, pg_temp AS $$
    SELECT coalesce(jsonb_agg(jsonb_build_object('ma', m.ma, 'dang_dung', m.dang_dung) ORDER BY m.ma), '[]'::jsonb) FROM doixe.ma_nha_xe m
$$;

-- Một chặng cho màn Điều độ: chữ, người làm và ba cờ khóa (có phí, đã hoàn, đã lên bảng kê đã gửi).
CREATE OR REPLACE FUNCTION doixe._chang_dd(p_id bigint) RETURNS jsonb
LANGUAGE sql STABLE SET search_path = pg_catalog, doixe, pg_temp AS $$
    SELECT jsonb_build_object(
        'id', c.id, 'loai', c.loai, 'ngay', c.ngay, 'ngay_dong', c.ngay_dong, 'nguon', c.nguon, 'container', c.container,
        'xe_id', c.xe_id, 'tai_xe_id', c.tai_xe_id, 'tra', c.tra, 'nguoi_tra_id', c.nguoi_tra_id,
        'noi_lay', c.noi_lay, 'noi_ha', c.noi_ha, 'kho', c.kho, 'tinh', c.tinh, 'ten_hang', c.ten_hang, 'ghi_chu', c.ghi_chu,
        'sau_khoa', c.sau_khoa, 'actor', c.actor, 'luc', doixe._luc(c.luc),
        'co_phi', EXISTS (SELECT 1 FROM doixe.dong dd JOIN doixe.dong_phi f ON f.dong_id = dd.id WHERE dd.chang_id = c.id),
        'da_hoan', EXISTS (SELECT 1 FROM doixe.dong dd WHERE dd.chang_id = c.id AND dd.dot_hoan_id IS NOT NULL),
        'da_gui', EXISTS (SELECT 1 FROM doixe.bang_ke_dong d WHERE d.chang_id = c.id))
      FROM doixe.chang c WHERE c.id = p_id
$$;

-- Thân xóa/bỏ chặng dùng chung cho xoa_chang và bo_phan_cong (chuyển nguyên từ xoa_chang của đợt 1, không đổi hành vi):
-- tháng mở và chưa dòng nào hoàn thì ẩn chặng (da_xoa); tháng khóa hoặc có dòng đã hoàn thì gạch ngang (da_bo) và thêm dòng trừ lại
-- đúng tổng từng loại phí. `p_viec_xoa`/`p_viec_bo`: tên việc ghi vào Lịch sử cho từng nhánh; `p_them`: ô thêm vào phần "trước".
-- Trả 'xoa' hoặc 'bo'.
CREATE OR REPLACE FUNCTION doixe._xoa_chang_thuc(c doixe.chang, p_key text, p_viec_xoa text, p_viec_bo text, p_them jsonb) RETURNS text
LANGUAGE plpgsql SET search_path = pg_catalog, doixe, pg_temp AS $$
DECLARE v_tien bigint; v_sd0 bigint; v_dong bigint; v_desc jsonb; v_cach text;
BEGIN
    SELECT sum(f.so_tien_vnd)::bigint INTO v_tien FROM doixe.dong dd JOIN doixe.dong_phi f ON f.dong_id = dd.id
      JOIN doixe.loai_phi l ON l.ma = f.loai_phi WHERE dd.chang_id = c.id AND NOT l.cong_ty_tra;
    v_sd0 := CASE WHEN c.nguoi_tra_id IS NOT NULL THEN doixe._so_du(c.nguoi_tra_id) END;
    v_desc := jsonb_build_object('chang_id', c.id, 'ngay', c.ngay, 'container', c.container, 'loai', c.loai, 'tien_vnd', v_tien::text,
                                 'so_du_vnd', v_sd0::text) || coalesce(p_them, '{}'::jsonb);
    IF NOT doixe._khoa(c.ngay) AND NOT EXISTS (SELECT 1 FROM doixe.dong WHERE chang_id = c.id AND dot_hoan_id IS NOT NULL) THEN
        UPDATE doixe.chang SET da_xoa = true WHERE id = c.id;
        v_cach := 'xoa';
        PERFORM doixe._ghi(p_viec_xoa, c.nguoi_tra_id, c.tai_xe_id, c.xe_id, v_desc,
            jsonb_build_object('cach', v_cach, 'so_du_vnd', (CASE WHEN c.nguoi_tra_id IS NOT NULL THEN doixe._so_du(c.nguoi_tra_id) END)::text),
            NULL, p_key);
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
        PERFORM doixe._ghi(p_viec_bo, c.nguoi_tra_id, c.tai_xe_id, c.xe_id, v_desc,
            jsonb_build_object('cach', v_cach, 'dong_id', v_dong, 'ly_do_dc', CASE WHEN doixe._khoa(c.ngay) THEN 'thang_khoa' ELSE 'da_hoan' END,
                               'so_du_vnd', (CASE WHEN c.nguoi_tra_id IS NOT NULL THEN doixe._so_du(c.nguoi_tra_id) END)::text),
            NULL, p_key);
    END IF;
    RETURN v_cach;
END $$;

-- xoa_chang: thân như đợt 1, phần xóa/bỏ chuyển sang _xoa_chang_thuc (Lịch sử của xoa_chang không đổi tên việc; ô `cach` thêm
-- vào phần "sau" của sự kiện).
CREATE OR REPLACE FUNCTION doixe.xoa_chang(p jsonb) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, doixe, pg_temp AS $$
-- Tháng mở và chưa dòng nào hoàn: ẩn chặng (da_xoa), Lịch sử giữ bản trước. Tháng khóa hoặc có dòng đã hoàn: gạch ngang (da_bo)
-- và thêm dòng trừ lại đúng tổng từng loại phí của chặng, để số dư không đổi ngầm.
DECLARE v_retry jsonb; c doixe.chang; v_cach text;
BEGIN
    v_retry := doixe._bat_dau(p, 'xoa_chang');
    IF v_retry IS NOT NULL THEN RETURN v_retry; END IF;
    PERFORM doixe._chi_khoa(p, ARRAY['idempotency_key', 'chang_id']);
    SELECT * INTO c FROM doixe.chang WHERE id = doixe._id(p, 'chang_id') FOR UPDATE;
    IF NOT FOUND OR c.da_xoa THEN RAISE EXCEPTION 'CHANG_NOT_FOUND'; END IF;
    IF c.da_bo THEN RAISE EXCEPTION 'CHANG_DA_BO'; END IF;
    v_cach := doixe._xoa_chang_thuc(c, p ->> 'idempotency_key', 'xoa_chang', 'bo_chang', NULL);
    RETURN doixe._xong(p, 'xoa_chang', jsonb_build_object('ok', true, 'cach', v_cach));
END $$;

-- ---------------------------------------------------------------------------------------------------------------------------
-- Hàm đọc (cấp cho sokhach_app).
CREATE OR REPLACE FUNCTION doixe.get_dieu_do(p_viec jsonb) RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = pg_catalog, doixe, pg_temp AS $$
-- `p_viec`: mảng việc [{container, ngay_dong}] mà API đọc từ bản chụp booking (mọi việc của khoảng ngày cần xem, không lọc trước:
-- chặng mồ côi được tìm trong khoảng từ ngày đóng sớm nhất tới muộn nhất của danh sách). Trả, với mỗi việc, các chặng đã nối
-- (chặng hàng đứng đầu, `hang_id` là chặng hàng gần nhất) kèm cờ co_phi, da_hoan, da_gui; danh sách chặng mồ côi (nguồn điều độ,
-- có ngày đóng trong khoảng, không khớp việc nào); xe và tài xế đang dùng; danh mục mã nhà xe. Trạng thái của việc (sắp tới, chờ
-- phân xe, đã phân xe, đã có phí, đã lên bảng kê, booking đã đổi) do API tính từ dữ liệu này, không tính ở đây.
DECLARE d date := doixe._hom_nay(); i integer; e jsonb; v_cont text; v_dong date; v_conts text[] := '{}'; v_dongs date[] := '{}';
        v_lo date; v_hi date; r jsonb;
BEGIN
    PERFORM doixe._actor();
    IF jsonb_typeof(p_viec) IS DISTINCT FROM 'array' OR jsonb_array_length(p_viec) > 5000 THEN RAISE EXCEPTION 'INVALID_COMMAND'; END IF;
    FOR i IN 0 .. jsonb_array_length(p_viec) - 1 LOOP
        e := p_viec -> i;
        PERFORM doixe._chi_khoa(e, ARRAY['container', 'ngay_dong']);
        v_cont := nullif(sokhach._normalize_key(doixe._chu(e -> 'container', 40)), '');
        v_dong := doixe._ngay(e -> 'ngay_dong');
        IF v_cont IS NULL OR v_dong IS NULL OR char_length(v_cont) > 20 THEN RAISE EXCEPTION 'INVALID_COMMAND'; END IF;
        v_conts := v_conts || v_cont;
        v_dongs := v_dongs || v_dong;
    END LOOP;
    SELECT min(x), max(x) INTO v_lo, v_hi FROM unnest(v_dongs) x;
    WITH v AS (SELECT DISTINCT t.cont, t.dong FROM unnest(v_conts, v_dongs) AS t(cont, dong)),
         m AS (SELECT v.cont, v.dong, c.id, c.loai, c.ngay, doixe._cach_viec(c.container, c.ngay, c.ngay_dong, v.cont, v.dong) AS cach
                 FROM v JOIN doixe.chang c ON c.container = v.cont AND NOT c.da_xoa AND NOT c.da_bo
                WHERE doixe._cach_viec(c.container, c.ngay, c.ngay_dong, v.cont, v.dong) IS NOT NULL
                  AND doixe._viec_cua(c, v.cont, (SELECT array_agg(w.dong) FROM v w WHERE w.cont = v.cont)) = v.dong)
    SELECT jsonb_build_object(
        'hom_nay', d,
        'viec', (SELECT coalesce(jsonb_agg(jsonb_build_object(
                    'container', v.cont, 'ngay_dong', v.dong,
                    'hang_id', (SELECT m.id FROM m WHERE m.cont = v.cont AND m.dong = v.dong AND m.loai = 'hang' ORDER BY m.cach, m.id LIMIT 1),
                    'chang', (SELECT coalesce(jsonb_agg(doixe._chang_dd(m.id) ORDER BY (m.loai <> 'hang'), m.cach, m.ngay, m.id), '[]'::jsonb)
                                FROM m WHERE m.cont = v.cont AND m.dong = v.dong))
                  ORDER BY v.dong, v.cont), '[]'::jsonb) FROM v),
        'mo_coi', (SELECT coalesce(jsonb_agg(doixe._chang_dd(c.id) ORDER BY c.ngay_dong, c.id), '[]'::jsonb) FROM doixe.chang c
                    WHERE c.nguon = 'dieu_do' AND c.ngay_dong BETWEEN v_lo AND v_hi AND NOT c.da_xoa AND NOT c.da_bo
                      AND NOT EXISTS (SELECT 1 FROM m WHERE m.id = c.id)),
        'xe', (SELECT coalesce(jsonb_agg(jsonb_build_object('id', x.id, 'bien_so', x.bien_so, 'nhom', x.nhom, 'thue_ngoai', x.thue_ngoai,
                    'tai_xe_id', x.tai_xe_id) ORDER BY x.thue_ngoai, x.bien_so), '[]'::jsonb) FROM doixe.xe x WHERE x.dang_dung),
        'tai_xe', (SELECT coalesce(jsonb_agg(jsonb_build_object('id', n.id, 'ten', n.ten) ORDER BY n.id), '[]'::jsonb)
                     FROM doixe.nguoi n WHERE n.dang_dung AND n.vai = 'tai_xe'),
        'nha_xe', doixe._nha_xe_json())
    INTO r;
    RETURN r;
END $$;

-- ---------------------------------------------------------------------------------------------------------------------------
-- Lệnh ghi (cấp cho sokhach_app).
CREATE OR REPLACE FUNCTION doixe.phan_xe(p jsonb) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, doixe, pg_temp AS $$
-- Phân xe cho một việc: tạo một chặng (mặc định loại hàng) cho container + ngày đóng, nguon = 'dieu_do', một dòng gốc chưa phí.
-- Ngày chạy mặc định là ngày đóng. Người trả theo mặc định đợt 1: tài xế (tai_xe_id, bỏ trống thì tài xế của xe); xe không có
-- tài xế (xe thuê ngoài) thì công ty. `loai` khác 'hang' (chuyển cảng, trả rỗng, rút/thả mooc, khác) thêm chặng phụ của việc, không
-- giới hạn số chặng phụ. `ngay_dong_khac`: ngày đóng của các việc khác cùng container (từ booking), để luật nối chọn đúng việc.
-- Chặn theo thứ tự: thiếu container (CONT_THIEU); việc đã có chặng hàng chưa bỏ (CHANG_HANG_DA_CO); xe không rõ (XE_KHONG_RO),
-- xe ngừng dùng (XE_NGUNG); ngày chạy sau hôm nay trừ khi bằng ngày đóng (NGAY_TUONG_LAI); tháng khóa (THANG_KHOA); trùng chặng
-- (TRUNG_CHANG). Chặng hàng trống nơi lấy và nơi hạ thì lấy tuyến của chuyến khách đã nối, như luu_chang.
DECLARE v_retry jsonb; d date := doixe._hom_nay(); v_cont text; v_dong date; v_ngay date; v_loai text; v_xe bigint; v_tx bigint; x doixe.xe;
        v_khac date[] := '{}'; v_lay text; v_ha text; v_ch jsonb; v_id bigint; v_tra text; v_ntra bigint;
        v_kho text; v_tinh text; v_hang text; v_ghi text; v_sau jsonb;
BEGIN
    v_retry := doixe._bat_dau(p, 'phan_xe');
    IF v_retry IS NOT NULL THEN RETURN v_retry; END IF;
    PERFORM doixe._chi_khoa(p, ARRAY['idempotency_key', 'container', 'ngay_dong', 'ngay', 'loai', 'xe_id', 'tai_xe_id', 'noi_lay', 'noi_ha',
                                      'kho', 'tinh', 'ten_hang', 'ghi_chu', 'ngay_dong_khac']);
    v_cont := nullif(sokhach._normalize_key(doixe._chu(p -> 'container', 40)), '');
    IF v_cont IS NULL THEN RAISE EXCEPTION 'CONT_THIEU'; END IF;
    IF char_length(v_cont) > 20 THEN RAISE EXCEPTION 'INVALID_COMMAND'; END IF;
    v_dong := doixe._ngay(p -> 'ngay_dong');
    IF v_dong IS NULL THEN RAISE EXCEPTION 'INVALID_DATE'; END IF;
    v_ngay := coalesce(doixe._ngay(p -> 'ngay'), v_dong);
    IF p ? 'loai' AND jsonb_typeof(p -> 'loai') IS DISTINCT FROM 'string' THEN RAISE EXCEPTION 'INVALID_COMMAND'; END IF;
    v_loai := coalesce(p ->> 'loai', 'hang');
    IF v_loai NOT IN ('hang', 'chuyen_cang', 'tra_rong', 'rut_mooc', 'tha_mooc', 'khac') THEN RAISE EXCEPTION 'INVALID_COMMAND'; END IF;
    v_xe := doixe._id(p, 'xe_id', true);
    v_tx := doixe._id(p, 'tai_xe_id', true);
    v_lay := doixe._chu(p -> 'noi_lay', 200);
    v_ha := doixe._chu(p -> 'noi_ha', 200);
    v_kho := doixe._chu(p -> 'kho', 200);
    v_tinh := doixe._chu(p -> 'tinh', 200);
    v_hang := doixe._chu(p -> 'ten_hang', 200);
    v_ghi := doixe._chu(p -> 'ghi_chu', 200);
    IF jsonb_typeof(p -> 'ngay_dong_khac') = 'array' THEN
        IF jsonb_array_length(p -> 'ngay_dong_khac') > 20 THEN RAISE EXCEPTION 'INVALID_COMMAND'; END IF;
        SELECT coalesce(array_agg(t.k), '{}') INTO v_khac FROM (SELECT doixe._ngay(e) AS k FROM jsonb_array_elements(p -> 'ngay_dong_khac') e) t
         WHERE t.k IS NOT NULL;
    ELSIF p ? 'ngay_dong_khac' AND jsonb_typeof(p -> 'ngay_dong_khac') <> 'null' THEN
        RAISE EXCEPTION 'INVALID_COMMAND';
    END IF;
    IF v_loai = 'hang' AND doixe._chang_hang(v_cont, v_dong, v_khac) IS NOT NULL THEN RAISE EXCEPTION 'CHANG_HANG_DA_CO'; END IF;
    SELECT * INTO x FROM doixe.xe WHERE id = v_xe;
    IF NOT FOUND THEN RAISE EXCEPTION 'XE_KHONG_RO'; END IF;
    IF NOT x.dang_dung THEN RAISE EXCEPTION 'XE_NGUNG'; END IF;
    IF v_tx IS NOT NULL AND NOT EXISTS (SELECT 1 FROM doixe.nguoi WHERE id = v_tx) THEN RAISE EXCEPTION 'NGUOI_NOT_FOUND'; END IF;
    IF v_ngay > d AND v_ngay <> v_dong THEN RAISE EXCEPTION 'NGAY_TUONG_LAI'; END IF;
    IF v_ngay <= d AND doixe._khoa(v_ngay) THEN RAISE EXCEPTION 'THANG_KHOA'; END IF;
    IF EXISTS (SELECT 1 FROM doixe.chang o WHERE NOT o.da_xoa AND o.ngay = v_ngay AND o.container = v_cont AND o.loai = v_loai AND o.xe_id = v_xe) THEN
        RAISE EXCEPTION 'TRUNG_CHANG';
    END IF;
    v_tx := coalesce(v_tx, x.tai_xe_id);
    IF v_tx IS NOT NULL THEN v_tra := 'nguoi'; v_ntra := v_tx; ELSE v_tra := 'cong_ty'; v_ntra := NULL; END IF;
    IF v_loai = 'hang' AND v_lay IS NULL AND v_ha IS NULL THEN
        v_ch := doixe._chuyen(v_cont, v_ngay);
        v_lay := left(nullif(btrim(v_ch ->> 'tu'), ''), 200);
        v_ha := left(nullif(btrim(v_ch ->> 'den'), ''), 200);
    END IF;
    INSERT INTO doixe.chang(ngay, ngay_dong, nguon, container, loai, xe_id, tai_xe_id, tra, nguoi_tra_id, noi_lay, noi_ha, kho, tinh, ten_hang,
                            ghi_chu, sau_khoa, actor)
    VALUES (v_ngay, v_dong, 'dieu_do', v_cont, v_loai, v_xe, v_tx, v_tra, v_ntra, v_lay, v_ha, v_kho, v_tinh, v_hang, v_ghi, false, doixe._actor())
    RETURNING id INTO v_id;
    INSERT INTO doixe.dong(chang_id, loai, actor) VALUES (v_id, 'goc', doixe._actor());
    v_sau := jsonb_build_object('chang_id', v_id, 'container', v_cont, 'ngay_dong', v_dong, 'loai', v_loai, 'ngay', v_ngay, 'xe_id', v_xe,
                                'tai_xe_id', v_tx, 'tra', v_tra, 'nguoi_tra_id', v_ntra);
    PERFORM doixe._ghi('phan_xe', v_ntra, v_tx, v_xe, jsonb_build_object('container', v_cont, 'ngay_dong', v_dong, 'loai', v_loai, 'chang_id', NULL),
                       v_sau, NULL, p ->> 'idempotency_key');
    RETURN doixe._xong(p, 'phan_xe', jsonb_build_object('ok', true, 'chang_id', v_id, 'nguon', 'dieu_do', 'tra', v_tra, 'nguoi_tra_id', v_ntra));
END $$;

CREATE OR REPLACE FUNCTION doixe.doi_phan_cong(p jsonb) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, doixe, pg_temp AS $$
-- Đổi xe, tài xế, ngày chạy của một chặng. `truoc` {xe_id, tai_xe_id, ngay}: cái máy người sửa đang thấy, khác hiện tại thì CHANGED.
-- Chặn khi chặng đã lên bảng kê đã gửi (CHANG_DA_GUI), đã hoàn (CHANG_DA_HOAN) hoặc đã có phí (CHANG_CO_PHI): đổi ở sổ tài xế hoặc
-- Bảng kê. Người trả đang ở mặc định (tài xế của chặng, hoặc công ty khi chặng chưa có tài xế) thì theo tài xế mới; người trả khác
-- giữ nguyên. Chặng chưa có phí nên không có tiền nào chuyển giữa các người.
DECLARE v_retry jsonb; d date := doixe._hom_nay(); c doixe.chang; v_ly text; v_truoc jsonb; v_xe bigint; v_tx bigint; v_ngay date; x doixe.xe;
        v_t_xe bigint; v_t_tx bigint; v_t_ngay date; v_tra text; v_ntra bigint;
BEGIN
    v_retry := doixe._bat_dau(p, 'doi_phan_cong');
    IF v_retry IS NOT NULL THEN RETURN v_retry; END IF;
    PERFORM doixe._chi_khoa(p, ARRAY['idempotency_key', 'chang_id', 'truoc', 'xe_id', 'tai_xe_id', 'ngay']);
    IF NOT (p ? 'truoc' AND p ? 'xe_id' AND p ? 'tai_xe_id' AND p ? 'ngay') THEN RAISE EXCEPTION 'INVALID_COMMAND'; END IF;
    v_truoc := p -> 'truoc';
    PERFORM doixe._chi_khoa(v_truoc, ARRAY['xe_id', 'tai_xe_id', 'ngay']);
    IF NOT (v_truoc ? 'xe_id' AND v_truoc ? 'tai_xe_id' AND v_truoc ? 'ngay') THEN RAISE EXCEPTION 'INVALID_COMMAND'; END IF;
    v_t_xe := doixe._id(v_truoc, 'xe_id');
    v_t_tx := doixe._id(v_truoc, 'tai_xe_id', true);
    v_t_ngay := doixe._ngay(v_truoc -> 'ngay');
    v_xe := doixe._id(p, 'xe_id', true);
    IF v_xe IS NULL THEN RAISE EXCEPTION 'XE_KHONG_RO'; END IF;
    v_tx := doixe._id(p, 'tai_xe_id', true);
    v_ngay := doixe._ngay(p -> 'ngay');
    IF v_ngay IS NULL THEN RAISE EXCEPTION 'INVALID_DATE'; END IF;
    SELECT * INTO c FROM doixe.chang WHERE id = doixe._id(p, 'chang_id') FOR UPDATE;
    IF NOT FOUND OR c.da_xoa THEN RAISE EXCEPTION 'CHANG_NOT_FOUND'; END IF;
    IF c.da_bo THEN RAISE EXCEPTION 'CHANG_DA_BO'; END IF;
    IF (c.xe_id, c.tai_xe_id, c.ngay) IS DISTINCT FROM (v_t_xe, v_t_tx, v_t_ngay) THEN RAISE EXCEPTION 'CHANGED'; END IF;
    IF (v_xe, v_tx, v_ngay) IS NOT DISTINCT FROM (c.xe_id, c.tai_xe_id, c.ngay) THEN
        RETURN doixe._xong(p, 'doi_phan_cong', jsonb_build_object('ok', true, 'khong_doi', true));
    END IF;
    v_ly := doixe._ly_khoa_chang(c.id);
    IF v_ly IS NOT NULL THEN RAISE EXCEPTION '%', v_ly; END IF;
    IF v_xe IS DISTINCT FROM c.xe_id THEN
        SELECT * INTO x FROM doixe.xe WHERE id = v_xe;
        IF NOT FOUND THEN RAISE EXCEPTION 'XE_KHONG_RO'; END IF;
        IF NOT x.dang_dung THEN RAISE EXCEPTION 'XE_NGUNG'; END IF;
    END IF;
    IF v_tx IS NOT NULL AND v_tx IS DISTINCT FROM c.tai_xe_id AND NOT EXISTS (SELECT 1 FROM doixe.nguoi WHERE id = v_tx) THEN
        RAISE EXCEPTION 'NGUOI_NOT_FOUND';
    END IF;
    IF v_ngay IS DISTINCT FROM c.ngay THEN
        IF v_ngay > d AND v_ngay IS DISTINCT FROM c.ngay_dong THEN RAISE EXCEPTION 'NGAY_TUONG_LAI'; END IF;
        IF date_trunc('month', v_ngay) <> date_trunc('month', c.ngay) AND (doixe._khoa(c.ngay) OR (v_ngay <= d AND doixe._khoa(v_ngay))) THEN
            RAISE EXCEPTION 'THANG_KHOA_CHUYEN';
        END IF;
    END IF;
    IF EXISTS (SELECT 1 FROM doixe.chang o WHERE o.id <> c.id AND NOT o.da_xoa AND o.ngay = v_ngay AND o.container = c.container
                  AND o.loai = c.loai AND o.xe_id = v_xe) THEN
        RAISE EXCEPTION 'TRUNG_CHANG';
    END IF;
    v_tra := c.tra;
    v_ntra := c.nguoi_tra_id;
    IF v_tx IS DISTINCT FROM c.tai_xe_id AND ((c.tra = 'nguoi' AND c.nguoi_tra_id IS NOT DISTINCT FROM c.tai_xe_id)
                                              OR (c.tra = 'cong_ty' AND c.tai_xe_id IS NULL)) THEN
        IF v_tx IS NULL THEN v_tra := 'cong_ty'; v_ntra := NULL; ELSE v_tra := 'nguoi'; v_ntra := v_tx; END IF;
    END IF;
    UPDATE doixe.chang SET xe_id = v_xe, tai_xe_id = v_tx, ngay = v_ngay, tra = v_tra, nguoi_tra_id = v_ntra WHERE id = c.id;
    PERFORM doixe._ghi('doi_phan_cong', v_ntra, v_tx, v_xe,
        jsonb_build_object('chang_id', c.id, 'container', c.container, 'ngay_dong', c.ngay_dong, 'xe_id', c.xe_id, 'tai_xe_id', c.tai_xe_id,
                           'ngay', c.ngay, 'nguoi_tra_id', c.nguoi_tra_id),
        jsonb_build_object('xe_id', v_xe, 'tai_xe_id', v_tx, 'ngay', v_ngay, 'nguoi_tra_id', v_ntra), NULL, p ->> 'idempotency_key');
    RETURN doixe._xong(p, 'doi_phan_cong', jsonb_build_object('ok', true, 'tra', v_tra, 'nguoi_tra_id', v_ntra));
END $$;

CREATE OR REPLACE FUNCTION doixe.bo_phan_cong(p jsonb) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, doixe, pg_temp AS $$
-- Bỏ một chặng khỏi điều độ, đúng ngữ nghĩa xóa/bỏ của xoa_chang (_xoa_chang_thuc): tháng mở thì ẩn (cach = 'xoa'), tháng khóa thì
-- gạch ngang (cach = 'bo'). Chặn khi chặng đã lên bảng kê đã gửi (CHANG_DA_GUI), đã hoàn (CHANG_DA_HOAN) hoặc đã có phí (CHANG_CO_PHI).
DECLARE v_retry jsonb; c doixe.chang; v_ly text; v_cach text;
BEGIN
    v_retry := doixe._bat_dau(p, 'bo_phan_cong');
    IF v_retry IS NOT NULL THEN RETURN v_retry; END IF;
    PERFORM doixe._chi_khoa(p, ARRAY['idempotency_key', 'chang_id']);
    SELECT * INTO c FROM doixe.chang WHERE id = doixe._id(p, 'chang_id') FOR UPDATE;
    IF NOT FOUND OR c.da_xoa THEN RAISE EXCEPTION 'CHANG_NOT_FOUND'; END IF;
    IF c.da_bo THEN RAISE EXCEPTION 'CHANG_DA_BO'; END IF;
    v_ly := doixe._ly_khoa_chang(c.id);
    IF v_ly IS NOT NULL THEN RAISE EXCEPTION '%', v_ly; END IF;
    v_cach := doixe._xoa_chang_thuc(c, p ->> 'idempotency_key', 'bo_phan_cong', 'bo_phan_cong',
                                    jsonb_build_object('ngay_dong', c.ngay_dong, 'xe_id', c.xe_id, 'tai_xe_id', c.tai_xe_id));
    RETURN doixe._xong(p, 'bo_phan_cong', jsonb_build_object('ok', true, 'cach', v_cach));
END $$;

CREATE OR REPLACE FUNCTION doixe.nhan_booking(p jsonb) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, doixe, pg_temp AS $$
-- Người nhận thay đổi của booking cho một chặng (web không tự sửa chặng). `kieu`:
--   cap_nhat: đặt ngày đóng mới (bắt buộc `ngay_dong`) và, nếu gửi kèm, container mới (chặng mồ côi sang container mới), kho,
--             nơi lấy, nơi hạ, tên hàng, tỉnh (khóa có mặt là đặt giá trị đó, null là xóa; khóa vắng là giữ nguyên);
--   giu_ngoai: giữ chặng thành chặng ngoài booking (ngày đóng về NULL).
-- Không đổi tiền, ngày chạy, xe, tài xế. Chỉ đổi ngày đóng (nối lại việc), chữ và giu_ngoai thì cho phép mọi lúc: không đụng tiền
-- hay khóa chuyến khách. ĐỔI CONTAINER thì như đổi phân công: chặng đã lên bảng kê đã gửi (CHANG_DA_GUI), đã hoàn (CHANG_DA_HOAN)
-- hoặc đã có phí (CHANG_CO_PHI) bị chặn; chặng ở tháng khóa (ngày chạy không sau hôm nay) bị chặn THANG_KHOA; trùng chặng
-- (TRUNG_CHANG). Không đổi gì thì khong_doi.
DECLARE v_retry jsonb; d date := doixe._hom_nay(); c doixe.chang; n doixe.chang; v_kieu text; v_ly text;
BEGIN
    v_retry := doixe._bat_dau(p, 'nhan_booking');
    IF v_retry IS NOT NULL THEN RETURN v_retry; END IF;
    IF jsonb_typeof(p -> 'kieu') IS DISTINCT FROM 'string' THEN RAISE EXCEPTION 'INVALID_COMMAND'; END IF;
    v_kieu := p ->> 'kieu';
    IF v_kieu = 'giu_ngoai' THEN
        PERFORM doixe._chi_khoa(p, ARRAY['idempotency_key', 'chang_id', 'kieu']);
    ELSIF v_kieu = 'cap_nhat' THEN
        PERFORM doixe._chi_khoa(p, ARRAY['idempotency_key', 'chang_id', 'kieu', 'ngay_dong', 'container', 'kho', 'noi_lay', 'noi_ha', 'ten_hang', 'tinh']);
    ELSE
        RAISE EXCEPTION 'INVALID_COMMAND';
    END IF;
    SELECT * INTO c FROM doixe.chang WHERE id = doixe._id(p, 'chang_id') FOR UPDATE;
    IF NOT FOUND OR c.da_xoa THEN RAISE EXCEPTION 'CHANG_NOT_FOUND'; END IF;
    IF c.da_bo THEN RAISE EXCEPTION 'CHANG_DA_BO'; END IF;
    n := c;
    IF v_kieu = 'giu_ngoai' THEN
        n.ngay_dong := NULL;
    ELSE
        n.ngay_dong := doixe._ngay(p -> 'ngay_dong');
        IF n.ngay_dong IS NULL THEN RAISE EXCEPTION 'INVALID_DATE'; END IF;
        IF p ? 'container' THEN
            n.container := nullif(sokhach._normalize_key(doixe._chu(p -> 'container', 40)), '');
            IF n.container IS NULL THEN RAISE EXCEPTION 'CONT_THIEU'; END IF;
            IF char_length(n.container) > 20 THEN RAISE EXCEPTION 'INVALID_COMMAND'; END IF;
        END IF;
        IF p ? 'kho' THEN n.kho := doixe._chu(p -> 'kho', 200); END IF;
        IF p ? 'noi_lay' THEN n.noi_lay := doixe._chu(p -> 'noi_lay', 200); END IF;
        IF p ? 'noi_ha' THEN n.noi_ha := doixe._chu(p -> 'noi_ha', 200); END IF;
        IF p ? 'ten_hang' THEN n.ten_hang := doixe._chu(p -> 'ten_hang', 200); END IF;
        IF p ? 'tinh' THEN n.tinh := doixe._chu(p -> 'tinh', 200); END IF;
    END IF;
    IF (n.ngay_dong, n.container, n.kho, n.noi_lay, n.noi_ha, n.ten_hang, n.tinh)
       IS NOT DISTINCT FROM (c.ngay_dong, c.container, c.kho, c.noi_lay, c.noi_ha, c.ten_hang, c.tinh) THEN
        RETURN doixe._xong(p, 'nhan_booking', jsonb_build_object('ok', true, 'khong_doi', true));
    END IF;
    IF n.container <> c.container THEN
        v_ly := doixe._ly_khoa_chang(c.id);
        IF v_ly IS NOT NULL THEN RAISE EXCEPTION '%', v_ly; END IF;
        IF c.ngay <= d AND doixe._khoa(c.ngay) THEN RAISE EXCEPTION 'THANG_KHOA'; END IF;
        IF EXISTS (SELECT 1 FROM doixe.chang o WHERE o.id <> c.id AND NOT o.da_xoa AND o.ngay = c.ngay AND o.container = n.container
                      AND o.loai = c.loai AND o.xe_id = c.xe_id) THEN
            RAISE EXCEPTION 'TRUNG_CHANG';
        END IF;
    END IF;
    UPDATE doixe.chang SET ngay_dong = n.ngay_dong, container = n.container, kho = n.kho, noi_lay = n.noi_lay, noi_ha = n.noi_ha,
                           ten_hang = n.ten_hang, tinh = n.tinh WHERE id = c.id;
    PERFORM doixe._ghi('nhan_booking', c.nguoi_tra_id, c.tai_xe_id, c.xe_id,
        jsonb_build_object('chang_id', c.id, 'kieu', v_kieu, 'container', c.container, 'ngay_dong', c.ngay_dong, 'kho', c.kho,
                           'noi_lay', c.noi_lay, 'noi_ha', c.noi_ha, 'ten_hang', c.ten_hang, 'tinh', c.tinh),
        jsonb_build_object('container', n.container, 'ngay_dong', n.ngay_dong, 'kho', n.kho, 'noi_lay', n.noi_lay, 'noi_ha', n.noi_ha,
                           'ten_hang', n.ten_hang, 'tinh', n.tinh),
        NULL, p ->> 'idempotency_key');
    RETURN doixe._xong(p, 'nhan_booking', jsonb_build_object('ok', true));
END $$;

-- Nạp danh mục mã nhà xe (công cụ nạp, cần người dùng đồng ý trước mỗi lần chạy trên hao; mã thật chỉ nạp vào DB, không vào repo).
-- Thêm mã mới hoặc đổi cờ dang_dung của mã có sẵn; mã không nêu thì giữ nguyên. Ghi Lịch sử (viec 'nap') danh sách trước → sau.
-- Không cấp cho app.
CREATE OR REPLACE FUNCTION doixe.nap_nha_xe(p jsonb) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, doixe, pg_temp AS $$
DECLARE r jsonb; v_truoc jsonb; v_ma text; v_n integer := 0;
BEGIN
    PERFORM doixe._actor();
    PERFORM pg_advisory_xact_lock(hashtext('doixe.ghi'));
    PERFORM doixe._chi_khoa(p, ARRAY['nha_xe']);
    IF jsonb_typeof(p -> 'nha_xe') IS DISTINCT FROM 'array' OR jsonb_array_length(p -> 'nha_xe') NOT BETWEEN 1 AND 50 THEN
        RAISE EXCEPTION 'INVALID_COMMAND';
    END IF;
    v_truoc := doixe._nha_xe_json();
    FOR r IN SELECT * FROM jsonb_array_elements(p -> 'nha_xe') LOOP
        PERFORM doixe._chi_khoa(r, ARRAY['ma', 'dang_dung']);
        v_ma := doixe._chu(r -> 'ma', 60);
        IF v_ma IS NULL OR (r ? 'dang_dung' AND jsonb_typeof(r -> 'dang_dung') IS DISTINCT FROM 'boolean') THEN RAISE EXCEPTION 'INVALID_COMMAND'; END IF;
        INSERT INTO doixe.ma_nha_xe AS t(ma, dang_dung, actor) VALUES (v_ma, coalesce((r ->> 'dang_dung')::boolean, true), doixe._actor())
        ON CONFLICT (ma) DO UPDATE SET dang_dung = EXCLUDED.dang_dung, actor = EXCLUDED.actor, luc = clock_timestamp()
            WHERE t.dang_dung IS DISTINCT FROM EXCLUDED.dang_dung;
        v_n := v_n + 1;
    END LOOP;
    PERFORM doixe._ghi('nap', NULL, NULL, NULL, jsonb_build_object('nha_xe', v_truoc), jsonb_build_object('nha_xe', doixe._nha_xe_json()), NULL, NULL);
    RETURN jsonb_build_object('ok', true, 'so_ma', v_n);
END $$;

-- Quyền: hàm đọc và lệnh ghi mới cho app; hàm phụ và nap_nha_xe không cấp cho ai. Không quyền trên bảng.
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA doixe FROM PUBLIC;
REVOKE ALL ON ALL TABLES IN SCHEMA doixe FROM PUBLIC;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA doixe FROM PUBLIC;
GRANT EXECUTE ON FUNCTION doixe.get_dieu_do(jsonb), doixe.phan_xe(jsonb), doixe.doi_phan_cong(jsonb), doixe.bo_phan_cong(jsonb),
    doixe.nhan_booking(jsonb) TO sokhach_app;
COMMIT;
