-- Đội xe: sửa các lỗi của audit 23/11/2026 (DX-01, DX-03, DX-04, DX-06). Áp sau 2026-11-19-v7-doi-xe-tai-chinh-chang.sql. Chỉ thay
-- định nghĩa hàm (CREATE OR REPLACE, thân như bản cũ, thêm phần ghi ở từng hàm); không đổi bảng, ràng buộc, quyền; không đổi dữ liệu,
-- không ghi `sokhach`. Chạy lại được. Các trường mới trong thân lệnh đều KHÔNG bắt buộc ở SQL (API bắt buộc), để áp migration
-- trước hay sau bản code đều không gãy lệnh nào.
--
-- * DX-01 `luu_gia`: ngày áp dụng trước tháng hiện tại (giờ VN) phải kèm `xac_nhan_ngay_cu: true`, nếu không thì NGAY_GIA_CU
--   (màn hỏi lại, in đủ ngày/tháng/năm và số chặng đổi giá). Chặn kiểu tháng 12 gõ "01/01" thành 01/01 năm nay.
-- * DX-03 số đang thấy: `ghi_ung` nhận `so_du_vnd`; `ghi_hoan` nhận `so_du_vnd`, `tong_dong_vnd`; `ghi_tien_ve` nhận `con_vnd`;
--   `ghi_dieu_chinh_bk` nhận `doi_vnd`. Khác số hiện tại thì SO_DU_DOI (ứng, hoàn), DONG_DA_DOI (tổng dòng hoàn) hoặc
--   BANG_KE_DOI (bảng kê): hai người cùng ghi một khoản từ màn cũ thì người sau phải tải lại, thấy khoản của người trước.
-- * DX-04 container lặp: `_cont_lap(chang)` = ngày các chặng hàng khác cùng container, cùng nhóm xe (công ty / thuê ngoài), lệch
--   tới 10 ngày. `_tinh_chang` thêm `cont_lap` (dòng bảng kê đang gom), `_tong_dong` đếm `cont_lap`; `luu_chang` trả `canh_cont`
--   (chỉ cảnh báo, không chặn).
-- * DX-06 `xoa_chang` nhận `tong_vnd` (tổng phí mọi dòng của chặng máy người bấm đang thấy), khác thì CHANGED; `luu_tuyen` nhận
--   `ten_goc_truoc` (bộ tên gốc đang thấy), khác thì TUYEN_DOI, để màn cũ không xóa tên gốc người khác vừa gắn.
BEGIN;
SET LOCAL ROLE sokhach_owner;

-- DX-04: ngày các chặng hàng khác cùng container, lệch tới 10 ngày, cùng nhóm xe với chặng này. NULL khi không có (hoặc không phải
-- chặng hàng).
CREATE OR REPLACE FUNCTION doixe._cont_lap(c doixe.chang) RETURNS jsonb
LANGUAGE sql STABLE SET search_path = pg_catalog, doixe, pg_temp AS $$
    SELECT jsonb_agg(o.ngay ORDER BY o.ngay, o.id)
      FROM doixe.chang o JOIN doixe.xe ox ON ox.id = o.xe_id
     WHERE c.loai = 'hang' AND o.id <> c.id AND NOT o.da_xoa AND NOT o.da_bo AND o.loai = 'hang' AND o.container = c.container
       AND o.ngay BETWEEN c.ngay - 10 AND c.ngay + 10
       AND ox.thue_ngoai = (SELECT x.thue_ngoai FROM doixe.xe x WHERE x.id = c.xe_id)
$$;

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
    v_ps := v_ps || doixe._ps_tu_o(c, v_ps);
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
        'chua_doc', v_doc, 'khoan_la', v_la, 'chang_con', true,
        -- Cùng ngày, container, loại với một dòng đã gửi bên này (chặng đã gửi bị xóa rồi nhập lại?): tháng của bảng kê đó, để báo
        -- trước khi gửi; không tự bỏ chặng.
        'trung_gui', (SELECT min(k.thang) FROM doixe.bang_ke_dong d JOIN doixe.bang_ke k ON k.id = d.bang_ke_id
                       WHERE k.ben = p_ben AND d.ngay = c.ngay AND d.container = c.container AND d.loai = c.loai),
        -- DX-04: ngày các chặng hàng khác cùng container lệch tới 10 ngày (Sheet sửa ngày rồi dán lại?), để báo trước khi gửi.
        'cont_lap', doixe._cont_lap(c));
END $$;

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
        'phu', count(*) FILTER (WHERE e ->> 'loai' <> 'hang'),
        'trung', count(*) FILTER (WHERE e ->> 'trung_gui' IS NOT NULL),
        'cont_lap', count(*) FILTER (WHERE jsonb_typeof(e -> 'cont_lap') = 'array'),
        'chang_bo', count(*) FILTER (WHERE NOT (e ->> 'chang_con')::boolean))
      FROM jsonb_array_elements(coalesce(p_dong, '[]'::jsonb)) e
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
        'sau_khoa', (SELECT count(*) FROM doixe.chang WHERE id = ANY (v_ids) AND sau_khoa),
        -- DX-04: chặng hàng vừa lưu mà container đã có chặng hàng khác lệch tới 10 ngày (kể cả trong cùng lệnh). Chỉ báo, không chặn.
        'canh_cont', (SELECT coalesce(jsonb_agg(jsonb_build_object('chang_id', x.id, 'ngay', x.ngay, 'container', x.container,
                                                                   'ngay_khac', x.lap) ORDER BY x.ngay, x.id), '[]'::jsonb)
                        FROM (SELECT c.id, c.ngay, c.container, doixe._cont_lap(c) AS lap FROM doixe.chang c WHERE c.id = ANY (v_ids)) x
                       WHERE x.lap IS NOT NULL)));
END $$;

CREATE OR REPLACE FUNCTION doixe.xoa_chang(p jsonb) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, doixe, pg_temp AS $$
-- Tháng mở và chưa dòng nào hoàn: ẩn chặng (da_xoa), Lịch sử giữ bản trước. Tháng khóa hoặc có dòng đã hoàn: gạch ngang (da_bo)
-- và thêm dòng trừ lại đúng tổng từng loại phí của chặng, để số dư không đổi ngầm.
-- DX-06: `tong_vnd` (không bắt buộc) là tổng phí mọi dòng của chặng máy người bấm đang thấy; khác (vừa có người nhập phí) thì CHANGED.
DECLARE v_retry jsonb; c doixe.chang; v_cach text;
BEGIN
    v_retry := doixe._bat_dau(p, 'xoa_chang');
    IF v_retry IS NOT NULL THEN RETURN v_retry; END IF;
    PERFORM doixe._chi_khoa(p, ARRAY['idempotency_key', 'chang_id', 'tong_vnd']);
    SELECT * INTO c FROM doixe.chang WHERE id = doixe._id(p, 'chang_id') FOR UPDATE;
    IF NOT FOUND OR c.da_xoa THEN RAISE EXCEPTION 'CHANG_NOT_FOUND'; END IF;
    IF c.da_bo THEN RAISE EXCEPTION 'CHANG_DA_BO'; END IF;
    IF p ? 'tong_vnd' AND doixe._vnd_co_dau(p -> 'tong_vnd') IS DISTINCT FROM
       (SELECT coalesce(sum(f.so_tien_vnd), 0)::bigint FROM doixe.dong d JOIN doixe.dong_phi f ON f.dong_id = d.id WHERE d.chang_id = c.id) THEN
        RAISE EXCEPTION 'CHANGED';
    END IF;
    v_cach := doixe._xoa_chang_thuc(c, p ->> 'idempotency_key', 'xoa_chang', 'bo_chang', NULL);
    RETURN doixe._xong(p, 'xoa_chang', jsonb_build_object('ok', true, 'cach', v_cach));
END $$;

CREATE OR REPLACE FUNCTION doixe.ghi_ung(p jsonb) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, doixe, pg_temp AS $$
-- DX-03: `so_du_vnd` (không bắt buộc) là số dư máy người ghi đang thấy; khác số dư hiện tại thì SO_DU_DOI.
DECLARE v_retry jsonb; v_nguoi bigint; v_ngay date; v_tien bigint; v_ghi text; v_sd0 bigint; v_sd1 bigint; v_id bigint;
BEGIN
    v_retry := doixe._bat_dau(p, 'ghi_ung');
    IF v_retry IS NOT NULL THEN RETURN v_retry; END IF;
    PERFORM doixe._chi_khoa(p, ARRAY['idempotency_key', 'nguoi_id', 'ngay', 'so_tien_vnd', 'ghi_chu', 'so_du_vnd']);
    v_nguoi := doixe._id(p, 'nguoi_id');
    IF NOT EXISTS (SELECT 1 FROM doixe.nguoi WHERE id = v_nguoi) THEN RAISE EXCEPTION 'NGUOI_NOT_FOUND'; END IF;
    v_ngay := doixe._ngay(p -> 'ngay');
    IF v_ngay IS NULL THEN RAISE EXCEPTION 'INVALID_DATE'; END IF;
    IF v_ngay > doixe._hom_nay() THEN RAISE EXCEPTION 'NGAY_TUONG_LAI'; END IF;
    v_tien := doixe._vnd(p -> 'so_tien_vnd');
    IF v_tien IS NULL OR v_tien = 0 THEN RAISE EXCEPTION 'INVALID_VND'; END IF;
    v_ghi := doixe._chu(p -> 'ghi_chu', 500);
    v_sd0 := doixe._so_du(v_nguoi);
    IF p ? 'so_du_vnd' AND doixe._vnd_co_dau(p -> 'so_du_vnd') IS DISTINCT FROM v_sd0 THEN RAISE EXCEPTION 'SO_DU_DOI'; END IF;
    INSERT INTO doixe.ung(nguoi_id, ngay, so_tien_vnd, ghi_chu, actor) VALUES (v_nguoi, v_ngay, v_tien, v_ghi, doixe._actor())
    RETURNING id INTO v_id;
    v_sd1 := doixe._so_du(v_nguoi);
    PERFORM doixe._ghi('ghi_ung', v_nguoi, NULL, NULL, jsonb_build_object('so_du_vnd', v_sd0::text),
        jsonb_build_object('ung_id', v_id, 'ngay', v_ngay, 'so_tien_vnd', v_tien::text, 'ghi_chu', v_ghi, 'so_du_vnd', v_sd1::text),
        NULL, p ->> 'idempotency_key');
    RETURN doixe._xong(p, 'ghi_ung', jsonb_build_object('ok', true, 'ung_id', v_id, 'so_du_truoc_vnd', v_sd0::text, 'so_du_sau_vnd', v_sd1::text));
END $$;

CREATE OR REPLACE FUNCTION doixe.ghi_hoan(p jsonb) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, doixe, pg_temp AS $$
-- Đợt hoàn: các dòng của đúng người trả, chưa xóa, chưa hoàn, có tiền khác 0; dòng nào vừa đổi thì DONG_DA_DOI (tải lại, chọn lại).
-- Số tiền thực chuyển là số nguyên >= 0, có thể khác tổng các dòng; số dư vẫn theo công thức đã chốt.
-- DX-03: `tong_dong_vnd`, `so_du_vnd` (không bắt buộc) là tổng các dòng đã chọn và số dư máy người ghi đang thấy; khác thì
-- DONG_DA_DOI (tổng dòng) hoặc SO_DU_DOI (số dư).
DECLARE v_retry jsonb; v_nguoi bigint; v_ngay date; v_tien bigint; v_ids bigint[]; v_tong bigint; v_sd0 bigint; v_sd1 bigint; v_id bigint;
BEGIN
    v_retry := doixe._bat_dau(p, 'ghi_hoan');
    IF v_retry IS NOT NULL THEN RETURN v_retry; END IF;
    PERFORM doixe._chi_khoa(p, ARRAY['idempotency_key', 'nguoi_id', 'ngay', 'so_tien_vnd', 'dong_ids', 'tong_dong_vnd', 'so_du_vnd']);
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
    IF p ? 'tong_dong_vnd' AND doixe._vnd_co_dau(p -> 'tong_dong_vnd') IS DISTINCT FROM v_tong THEN RAISE EXCEPTION 'DONG_DA_DOI'; END IF;
    v_sd0 := doixe._so_du(v_nguoi);
    IF p ? 'so_du_vnd' AND doixe._vnd_co_dau(p -> 'so_du_vnd') IS DISTINCT FROM v_sd0 THEN RAISE EXCEPTION 'SO_DU_DOI'; END IF;
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

CREATE OR REPLACE FUNCTION doixe.ghi_dieu_chinh_bk(p jsonb) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, doixe, pg_temp AS $$
-- Điều chỉnh một dòng của bảng kê đã gửi, chưa đối chiếu xong: số có dấu (bớt âm, thêm dương), khác 0, lý do bắt buộc; tổng dòng
-- sau điều chỉnh không âm. Lịch sử có Đòi HTH và tổng dòng trước → sau.
-- DX-03: `doi_vnd` (không bắt buộc) là số đòi của bảng kê máy người ghi đang thấy; khác (vừa có người điều chỉnh) thì BANG_KE_DOI.
DECLARE v_retry jsonb; dd doixe.bang_ke_dong; k doixe.bang_ke; v_tien bigint; v_ly text; v_doi0 bigint; v_dong0 bigint; v_id bigint;
BEGIN
    v_retry := doixe._bat_dau(p, 'ghi_dieu_chinh_bk');
    IF v_retry IS NOT NULL THEN RETURN v_retry; END IF;
    PERFORM doixe._chi_khoa(p, ARRAY['idempotency_key', 'dong_id', 'so_tien_vnd', 'ly_do', 'doi_vnd']);
    v_ly := doixe._chu(p -> 'ly_do', 500);
    IF v_ly IS NULL THEN RAISE EXCEPTION 'LY_DO_DIEU_CHINH'; END IF;
    v_tien := doixe._vnd_co_dau(p -> 'so_tien_vnd');
    IF v_tien IS NULL OR v_tien = 0 THEN RAISE EXCEPTION 'INVALID_VND'; END IF;
    SELECT * INTO dd FROM doixe.bang_ke_dong WHERE id = doixe._id(p, 'dong_id');
    IF NOT FOUND THEN RAISE EXCEPTION 'DONG_BK_NOT_FOUND'; END IF;
    SELECT * INTO k FROM doixe.bang_ke WHERE id = dd.bang_ke_id FOR UPDATE;
    IF k.trang_thai <> 'da_gui' THEN RAISE EXCEPTION 'BANG_KE_DA_DOI_CHIEU'; END IF;
    v_doi0 := doixe._doi_bk(k.id);
    IF p ? 'doi_vnd' AND doixe._vnd(p -> 'doi_vnd') IS DISTINCT FROM v_doi0 THEN RAISE EXCEPTION 'BANG_KE_DOI'; END IF;
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
-- DX-03: `con_vnd` (không bắt buộc) là số còn phải thu máy người ghi đang thấy; khác (vừa có người ghi tiền về) thì BANG_KE_DOI.
DECLARE v_retry jsonb; b doixe.ben; m date; k doixe.bang_ke; v_ngay date; v_tien bigint; v_con bigint; v_id bigint; v_ghi text;
BEGIN
    v_retry := doixe._bat_dau(p, 'ghi_tien_ve');
    IF v_retry IS NOT NULL THEN RETURN v_retry; END IF;
    PERFORM doixe._chi_khoa(p, ARRAY['idempotency_key', 'thang', 'ngay', 'so_tien_vnd', 'ghi_chu', 'con_vnd']);
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
    IF p ? 'con_vnd' AND doixe._vnd_co_dau(p -> 'con_vnd') IS DISTINCT FROM v_con THEN RAISE EXCEPTION 'BANG_KE_DOI'; END IF;
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

CREATE OR REPLACE FUNCTION doixe.luu_gia(p jsonb) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, doixe, pg_temp AS $$
-- Giá tuyến áp dụng từ ngày (cùng ngày thì thay giá). Tháng đã gửi giữ số đã chép; chặng đang gom theo bảng giá từ ngày đó đổi
-- theo (Lịch sử ghi số chặng đổi). Ngày áp dụng được sau hôm nay (giá đã báo trước), tới một năm.
-- DX-01: ngày áp dụng trước tháng hiện tại (giờ VN) là áp giá ngược, phải kèm `xac_nhan_ngay_cu: true`, nếu không thì NGAY_GIA_CU.
DECLARE v_retry jsonb; b doixe.ben; t doixe.tuyen; v_tu date; v_gia bigint; v_cu bigint; v_hien bigint; v_n integer;
BEGIN
    v_retry := doixe._bat_dau(p, 'luu_gia');
    IF v_retry IS NOT NULL THEN RETURN v_retry; END IF;
    PERFORM doixe._chi_khoa(p, ARRAY['idempotency_key', 'tuyen_id', 'tu_ngay', 'gia_vnd', 'xac_nhan_ngay_cu']);
    IF p ? 'xac_nhan_ngay_cu' AND jsonb_typeof(p -> 'xac_nhan_ngay_cu') <> 'boolean' THEN RAISE EXCEPTION 'INVALID_COMMAND'; END IF;
    b := doixe._ben_nhan(NULL);
    SELECT * INTO t FROM doixe.tuyen WHERE id = doixe._id(p, 'tuyen_id') AND dang_dung;
    IF NOT FOUND THEN RAISE EXCEPTION 'TUYEN_NOT_FOUND'; END IF;
    v_tu := doixe._ngay(p -> 'tu_ngay');
    IF v_tu IS NULL THEN RAISE EXCEPTION 'INVALID_DATE'; END IF;
    IF v_tu > doixe._hom_nay() + 366 THEN RAISE EXCEPTION 'NGAY_GIA_XA'; END IF;
    IF v_tu < date_trunc('month', doixe._hom_nay())::date AND NOT coalesce((p ->> 'xac_nhan_ngay_cu')::boolean, false) THEN
        RAISE EXCEPTION 'NGAY_GIA_CU';
    END IF;
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
       AND doixe._tuyen_hop(c.loai, t.loai) AND doixe._tuyen_chang(c) = t.id;
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
-- DX-06: sửa tuyến có sẵn kèm `ten_goc_truoc` (không bắt buộc): bộ tên gốc dạng 'HÀNG|TỈNH' máy người bấm đang thấy; khác bộ hiện
-- tại (vừa có người gắn hay bỏ tên gốc) thì TUYEN_DOI, để danh sách cũ không xóa tên gốc người khác vừa nhớ.
DECLARE v_retry jsonb; b doixe.ben; t doixe.tuyen; v_id bigint; v_loai text; v_hang text; v_di text; v_den text; v_dung boolean;
        v_khoa text[]; r jsonb; v_k text; v_truoc jsonb; v_gia bigint; v_tu date;
BEGIN
    v_retry := doixe._bat_dau(p, 'luu_tuyen');
    IF v_retry IS NOT NULL THEN RETURN v_retry; END IF;
    PERFORM doixe._chi_khoa(p, ARRAY['idempotency_key', 'tuyen_id', 'loai', 'hang', 'di', 'den', 'dang_dung', 'ten_goc', 'gia_vnd', 'tu_ngay',
                                     'ten_goc_truoc']);
    IF p ? 'ten_goc_truoc' AND (jsonb_typeof(p -> 'ten_goc_truoc') <> 'array' OR jsonb_array_length(p -> 'ten_goc_truoc') > 50
       OR EXISTS (SELECT 1 FROM jsonb_array_elements(p -> 'ten_goc_truoc') e WHERE jsonb_typeof(e) <> 'string' OR char_length(e #>> '{}') > 260)) THEN
        RAISE EXCEPTION 'INVALID_COMMAND';
    END IF;
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
    -- Tên gốc chỉ cho tuyến hàng: chặng chuyển cảng, trả rỗng nhận tuyến theo loại, không theo hàng + tỉnh.
    IF v_loai <> 'hang' AND cardinality(v_khoa) > 0 THEN RAISE EXCEPTION 'TEN_GOC_CHI_TUYEN_HANG'; END IF;
    IF v_id IS NULL THEN
        v_gia := doixe._vnd(p -> 'gia_vnd');
        v_tu := doixe._ngay(p -> 'tu_ngay');
        IF v_gia IS NULL OR v_gia = 0 THEN RAISE EXCEPTION 'INVALID_VND'; END IF;
        IF v_tu IS NULL THEN RAISE EXCEPTION 'INVALID_DATE'; END IF;
        IF v_tu > doixe._hom_nay() + 366 THEN RAISE EXCEPTION 'NGAY_GIA_XA'; END IF;
        IF NOT v_dung OR p ? 'ten_goc_truoc' THEN RAISE EXCEPTION 'INVALID_COMMAND'; END IF;
    ELSE
        IF p ? 'gia_vnd' OR p ? 'tu_ngay' THEN RAISE EXCEPTION 'INVALID_COMMAND'; END IF;
        SELECT * INTO t FROM doixe.tuyen WHERE id = v_id FOR UPDATE;
        IF NOT FOUND THEN RAISE EXCEPTION 'TUYEN_NOT_FOUND'; END IF;
        IF t.loai <> v_loai THEN RAISE EXCEPTION 'INVALID_COMMAND'; END IF;
        IF p ? 'ten_goc_truoc' AND ARRAY(SELECT DISTINCT e #>> '{}' FROM jsonb_array_elements(p -> 'ten_goc_truoc') e ORDER BY 1)
           IS DISTINCT FROM ARRAY(SELECT g.khoa FROM doixe.tuyen_ten_goc g WHERE g.tuyen_id = t.id ORDER BY g.khoa) THEN
            RAISE EXCEPTION 'TUYEN_DOI';
        END IF;
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

REVOKE ALL ON ALL FUNCTIONS IN SCHEMA doixe FROM PUBLIC;
COMMIT;
