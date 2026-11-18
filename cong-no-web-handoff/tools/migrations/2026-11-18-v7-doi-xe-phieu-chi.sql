-- Đội xe: phiếu chi xe mới của nhà xe (áp dụng từ 11/2026; CHI-PHI-XE-01, specs/chi-phi-xe-01.md mục "Phiếu chi mới").
-- Áp sau 2026-11-18-v7-doi-xe.sql. Chạy lại được. Không đổi tiền đã ghi, không đổi hàm đọc chung (_chung) hay quyền.
-- 1. Loại phí "Hạ sớm/KH" (hạ sớm, kiểm hoá) do tài xế chi: phiếu mới có dòng riêng; tab tài xế 29 cột chưa có cột này nên
--    cot_sheet NULL (nhập tại ô). Thứ tự 16: sau Nổ máy, trước VETC trên màn (VETC luôn đứng cuối vì công ty trả).
-- 2. Ba ô số lượng của chặng, NULL là trống (không phải 0): ngày neo kho, giờ nổ máy phát, km. Không phải tiền: không vào
--    phần hoàn, sửa ghi đè cả ở tháng khóa, mọi lần sửa vào Lịch sử.
-- 3. Viết lại _chang_ds (trả ba ô), luu_chang (nhận ba ô), sua_chang (sửa ba ô); phần còn lại y như đợt 1.
BEGIN;
SET LOCAL ROLE sokhach_owner;

INSERT INTO doixe.loai_phi(ma, ten, ten_day_du, thu_tu, cot_sheet, cong_ty_tra) VALUES
    ('hasom', 'Hạ sớm/KH', 'Hạ sớm · kiểm hoá', 16, NULL, false)
ON CONFLICT (ma) DO UPDATE SET ten = EXCLUDED.ten, ten_day_du = EXCLUDED.ten_day_du, thu_tu = EXCLUDED.thu_tu,
    cot_sheet = EXCLUDED.cot_sheet, cong_ty_tra = EXCLUDED.cong_ty_tra;

ALTER TABLE doixe.chang ADD COLUMN IF NOT EXISTS neo_ngay integer CHECK (neo_ngay BETWEEN 1 AND 365);
ALTER TABLE doixe.chang ADD COLUMN IF NOT EXISTS may_gio integer CHECK (may_gio BETWEEN 1 AND 999);
ALTER TABLE doixe.chang ADD COLUMN IF NOT EXISTS km integer CHECK (km BETWEEN 1 AND 9999);
COMMENT ON COLUMN doixe.chang.neo_ngay IS 'Số ngày neo kho theo phiếu chi; tiền neo vẫn ở dong_phi (neo). NULL là trống.';
COMMENT ON COLUMN doixe.chang.may_gio IS 'Số giờ nổ máy phát theo phiếu chi; tiền (nếu có) ở dong_phi (may). NULL là trống.';
COMMENT ON COLUMN doixe.chang.km IS 'Km của chặng ghi trên phiếu chi (ô Tỉnh: huyện, tỉnh, km). NULL là trống.';

-- Số lượng: null/thiếu là trống; chuỗi số nguyên 1..p_max, sai thì INVALID_COMMAND (API và màn đã kiểm trước).
CREATE OR REPLACE FUNCTION doixe._sl(v jsonb, p_max integer) RETURNS integer
LANGUAGE plpgsql IMMUTABLE SET search_path = pg_catalog, doixe, pg_temp AS $$
BEGIN
    IF v IS NULL OR jsonb_typeof(v) = 'null' THEN RETURN NULL; END IF;
    -- Hai bước: SQL không hứa tính OR từ trái sang, ép kiểu trước khi khớp mẫu sẽ ra lỗi khác INVALID_COMMAND.
    IF jsonb_typeof(v) <> 'string' OR (v #>> '{}') !~ '^[1-9][0-9]{0,4}$' THEN RAISE EXCEPTION 'INVALID_COMMAND'; END IF;
    IF (v #>> '{}')::integer > p_max THEN RAISE EXCEPTION 'INVALID_COMMAND'; END IF;
    RETURN (v #>> '{}')::integer;
END $$;

-- DOI-XE-THU-01 (đợt 2) thêm cột loai_phi.chi_ho và coi hạ sớm/kiểm hoá là chi hộ. Hai migration chạy thứ tự nào cũng ra cùng kết quả.
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_attribute WHERE attrelid = 'doixe.loai_phi'::regclass AND attname = 'chi_ho' AND NOT attisdropped) THEN
        EXECUTE 'UPDATE doixe.loai_phi SET chi_ho = true WHERE ma = ''hasom''';
    END IF;
END $$;

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
        'ten_hang', c.ten_hang, 'ghi_chu', c.ghi_chu, 'neo_ngay', c.neo_ngay, 'may_gio', c.may_gio, 'km', c.km,
        'sau_khoa', c.sau_khoa, 'da_bo', c.da_bo, 'actor', c.actor, 'luc', doixe._luc(c.luc),
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
                                              'kho', 'tinh', 'ten_hang', 'ghi_chu', 'phi', 'neo_ngay', 'may_gio', 'km']);
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
        PERFORM doixe._sl(v_row -> 'neo_ngay', 365), doixe._sl(v_row -> 'may_gio', 999), doixe._sl(v_row -> 'km', 9999);
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
                                neo_ngay, may_gio, km, sau_khoa, actor)
        VALUES (v_ngay, v_cont, v_loai, doixe._id(v_row, 'xe_id'), doixe._id(v_row, 'tai_xe_id', true), v_row ->> 'tra',
                doixe._id(v_row, 'nguoi_tra_id', true), v_lay, v_ha, doixe._chu(v_row -> 'kho', 200), doixe._chu(v_row -> 'tinh', 200),
                doixe._chu(v_row -> 'ten_hang', 200), doixe._chu(v_row -> 'ghi_chu', 200),
                doixe._sl(v_row -> 'neo_ngay', 365), doixe._sl(v_row -> 'may_gio', 999), doixe._sl(v_row -> 'km', 9999),
                doixe._khoa(v_ngay), doixe._actor())
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
-- không chuyển chặng vào/ra tháng khóa; không trùng chặng. Số lượng (ngày neo, giờ máy phát, km) ghi đè cả ở tháng khóa: không phải tiền. Người trả: không đổi khi tháng khóa hoặc có dòng đã hoàn.
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
    ELSIF v_cot IN ('neo_ngay', 'may_gio', 'km') THEN
        v_old := CASE v_cot WHEN 'neo_ngay' THEN c.neo_ngay::text WHEN 'may_gio' THEN c.may_gio::text ELSE c.km::text END;
        IF v_truoc IS NULL OR jsonb_typeof(v_truoc) NOT IN ('string', 'null') THEN RAISE EXCEPTION 'INVALID_COMMAND'; END IF;
        IF (v_truoc #>> '{}') IS DISTINCT FROM v_old THEN RAISE EXCEPTION 'CHANGED'; END IF;
        v_new := doixe._sl(v_gia, CASE v_cot WHEN 'neo_ngay' THEN 365 WHEN 'may_gio' THEN 999 ELSE 9999 END)::text;
        IF v_new IS NOT DISTINCT FROM v_old THEN
            RETURN doixe._xong(p, 'sua_chang', jsonb_build_object('ok', true, 'khong_doi', true));
        END IF;
        UPDATE doixe.chang SET
            neo_ngay = CASE WHEN v_cot = 'neo_ngay' THEN v_new::integer ELSE neo_ngay END,
            may_gio = CASE WHEN v_cot = 'may_gio' THEN v_new::integer ELSE may_gio END,
            km = CASE WHEN v_cot = 'km' THEN v_new::integer ELSE km END
        WHERE id = c.id;
        PERFORM doixe._ghi('sua_chang', c.nguoi_tra_id, c.tai_xe_id, c.xe_id,
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

REVOKE ALL ON FUNCTION doixe._sl(jsonb, integer) FROM PUBLIC;
COMMIT;
