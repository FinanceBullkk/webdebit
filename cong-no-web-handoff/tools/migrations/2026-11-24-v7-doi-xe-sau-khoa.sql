-- Đội xe DX-05 (DOI-XE-SAU-KHOA-01, 24/11/2026): ứng, đợt hoàn và hủy của chúng vào tháng đã khóa vẫn ghi, gắn cờ "sau khóa" như
-- chặng (`doixe.chang.sau_khoa`). Không chặn, không đòi lý do (đồng bộ V7-SO); hủy vẫn bắt buộc lý do như cũ. Áp sau
-- 2026-11-23-v7-doi-xe-sua-audit.sql.
--
-- * Bảng `ung`, `dot_hoan` thêm `sau_khoa` (ghi khi tháng của ngày khoản đã khóa) và `huy_sau_khoa` (hủy khi tháng đó đã khóa),
--   mặc định false. Khoản cũ giữ false: không biết lúc ghi tháng đã khóa hay chưa, không đoán.
-- * `ghi_ung`, `ghi_hoan`, `huy_ung`, `huy_hoan` (thân như bản trước, thêm cờ): ghi cờ vào khoản, vào `sau` của Lịch sử và vào kết
--   quả trả về (`sau_khoa`). `get_so` trả `sau_khoa` của từng lần ứng / đợt hoàn và `sau_khoa` trong `huy`.
--
-- Không đổi dữ liệu tiền, số dư, quyền, `sokhach`. Chạy lại được.
BEGIN;
SET LOCAL ROLE sokhach_owner;

ALTER TABLE doixe.ung ADD COLUMN IF NOT EXISTS sau_khoa boolean NOT NULL DEFAULT false;
ALTER TABLE doixe.ung ADD COLUMN IF NOT EXISTS huy_sau_khoa boolean NOT NULL DEFAULT false;
ALTER TABLE doixe.dot_hoan ADD COLUMN IF NOT EXISTS sau_khoa boolean NOT NULL DEFAULT false;
ALTER TABLE doixe.dot_hoan ADD COLUMN IF NOT EXISTS huy_sau_khoa boolean NOT NULL DEFAULT false;
COMMENT ON COLUMN doixe.ung.sau_khoa IS 'Ghi khi tháng của ngày ứng đã khóa (DOI-XE-SAU-KHOA-01). Khoản ghi trước 24/11/2026 luôn false.';
COMMENT ON COLUMN doixe.ung.huy_sau_khoa IS 'Hủy khi tháng của ngày ứng đã khóa.';
COMMENT ON COLUMN doixe.dot_hoan.sau_khoa IS 'Ghi khi tháng của ngày đợt hoàn đã khóa (DOI-XE-SAU-KHOA-01). Đợt ghi trước 24/11/2026 luôn false.';
COMMENT ON COLUMN doixe.dot_hoan.huy_sau_khoa IS 'Hủy khi tháng của ngày đợt hoàn đã khóa.';

CREATE OR REPLACE FUNCTION doixe.ghi_ung(p jsonb) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, doixe, pg_temp AS $$
-- DX-03: `so_du_vnd` (không bắt buộc) là số dư máy người ghi đang thấy; khác số dư hiện tại thì SO_DU_DOI.
-- DX-05: ngày ứng ở tháng đã khóa vẫn ghi, gắn sau_khoa.
DECLARE v_retry jsonb; v_nguoi bigint; v_ngay date; v_tien bigint; v_ghi text; v_sd0 bigint; v_sd1 bigint; v_id bigint; v_sk boolean;
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
    v_sk := doixe._khoa(v_ngay);
    INSERT INTO doixe.ung(nguoi_id, ngay, so_tien_vnd, ghi_chu, sau_khoa, actor) VALUES (v_nguoi, v_ngay, v_tien, v_ghi, v_sk, doixe._actor())
    RETURNING id INTO v_id;
    v_sd1 := doixe._so_du(v_nguoi);
    PERFORM doixe._ghi('ghi_ung', v_nguoi, NULL, NULL, jsonb_build_object('so_du_vnd', v_sd0::text),
        jsonb_build_object('ung_id', v_id, 'ngay', v_ngay, 'so_tien_vnd', v_tien::text, 'ghi_chu', v_ghi, 'so_du_vnd', v_sd1::text,
                           'sau_khoa', v_sk),
        NULL, p ->> 'idempotency_key');
    RETURN doixe._xong(p, 'ghi_ung', jsonb_build_object('ok', true, 'ung_id', v_id, 'so_du_truoc_vnd', v_sd0::text, 'so_du_sau_vnd', v_sd1::text,
        'sau_khoa', v_sk));
END $$;

CREATE OR REPLACE FUNCTION doixe.huy_ung(p jsonb) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, doixe, pg_temp AS $$
-- DX-05: lần ứng ở tháng đã khóa vẫn hủy được (lý do bắt buộc như mọi lần hủy), gắn huy_sau_khoa.
DECLARE v_retry jsonb; u doixe.ung; v_ly text; v_sd0 bigint; v_sd1 bigint; v_sk boolean;
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
    v_sk := doixe._khoa(u.ngay);
    UPDATE doixe.ung SET huy_actor = doixe._actor(), huy_luc = clock_timestamp(), huy_ly_do = v_ly, huy_sau_khoa = v_sk WHERE id = u.id;
    v_sd1 := doixe._so_du(u.nguoi_id);
    PERFORM doixe._ghi('huy_ung', u.nguoi_id, NULL, NULL,
        jsonb_build_object('ung_id', u.id, 'ngay', u.ngay, 'so_tien_vnd', u.so_tien_vnd::text, 'so_du_vnd', v_sd0::text),
        jsonb_build_object('so_du_vnd', v_sd1::text, 'sau_khoa', v_sk), v_ly, p ->> 'idempotency_key');
    RETURN doixe._xong(p, 'huy_ung', jsonb_build_object('ok', true, 'so_du_truoc_vnd', v_sd0::text, 'so_du_sau_vnd', v_sd1::text,
        'sau_khoa', v_sk));
END $$;

CREATE OR REPLACE FUNCTION doixe.ghi_hoan(p jsonb) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, doixe, pg_temp AS $$
-- Đợt hoàn: các dòng của đúng người trả, chưa xóa, chưa hoàn, có tiền khác 0; dòng nào vừa đổi thì DONG_DA_DOI (tải lại, chọn lại).
-- Số tiền thực chuyển là số nguyên >= 0, có thể khác tổng các dòng; số dư vẫn theo công thức đã chốt.
-- DX-03: `tong_dong_vnd`, `so_du_vnd` (không bắt buộc) là tổng các dòng đã chọn và số dư máy người ghi đang thấy; khác thì
-- DONG_DA_DOI (tổng dòng) hoặc SO_DU_DOI (số dư).
-- DX-05: ngày đợt hoàn ở tháng đã khóa vẫn ghi, gắn sau_khoa.
DECLARE v_retry jsonb; v_nguoi bigint; v_ngay date; v_tien bigint; v_ids bigint[]; v_tong bigint; v_sd0 bigint; v_sd1 bigint; v_id bigint;
        v_sk boolean;
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
    v_sk := doixe._khoa(v_ngay);
    INSERT INTO doixe.dot_hoan(nguoi_id, ngay, so_tien_vnd, tong_dong_vnd, dong_ids, sau_khoa, actor)
    VALUES (v_nguoi, v_ngay, v_tien, v_tong, v_ids, v_sk, doixe._actor()) RETURNING id INTO v_id;
    UPDATE doixe.dong SET dot_hoan_id = v_id WHERE id = ANY (v_ids);
    v_sd1 := doixe._so_du(v_nguoi);
    PERFORM doixe._ghi('ghi_hoan', v_nguoi, NULL, NULL, jsonb_build_object('so_du_vnd', v_sd0::text),
        jsonb_build_object('dot_id', v_id, 'ngay', v_ngay, 'so_tien_vnd', v_tien::text, 'tong_dong_vnd', v_tong::text,
                           'so_dong', cardinality(v_ids), 'so_du_vnd', v_sd1::text, 'sau_khoa', v_sk),
        NULL, p ->> 'idempotency_key');
    RETURN doixe._xong(p, 'ghi_hoan', jsonb_build_object('ok', true, 'dot_id', v_id, 'tong_dong_vnd', v_tong::text,
        'so_du_truoc_vnd', v_sd0::text, 'so_du_sau_vnd', v_sd1::text, 'sau_khoa', v_sk));
END $$;

CREATE OR REPLACE FUNCTION doixe.huy_hoan(p jsonb) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, doixe, pg_temp AS $$
-- Hủy đợt hoàn bắt buộc lý do; các dòng của đợt trở lại chưa hoàn.
-- DX-05: đợt hoàn ở tháng đã khóa vẫn hủy được, gắn huy_sau_khoa.
DECLARE v_retry jsonb; h doixe.dot_hoan; v_ly text; v_sd0 bigint; v_sd1 bigint; v_n integer; v_sk boolean;
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
    v_sk := doixe._khoa(h.ngay);
    UPDATE doixe.dot_hoan SET huy_actor = doixe._actor(), huy_luc = clock_timestamp(), huy_ly_do = v_ly, huy_sau_khoa = v_sk WHERE id = h.id;
    UPDATE doixe.dong SET dot_hoan_id = NULL WHERE dot_hoan_id = h.id;
    GET DIAGNOSTICS v_n = ROW_COUNT;
    v_sd1 := doixe._so_du(h.nguoi_id);
    PERFORM doixe._ghi('huy_hoan', h.nguoi_id, NULL, NULL,
        jsonb_build_object('dot_id', h.id, 'ngay', h.ngay, 'so_tien_vnd', h.so_tien_vnd::text, 'tong_dong_vnd', h.tong_dong_vnd::text,
                           'so_dong', cardinality(h.dong_ids), 'so_du_vnd', v_sd0::text),
        jsonb_build_object('dong_tro_lai', v_n, 'so_du_vnd', v_sd1::text, 'sau_khoa', v_sk), v_ly, p ->> 'idempotency_key');
    RETURN doixe._xong(p, 'huy_hoan', jsonb_build_object('ok', true, 'dong_tro_lai', v_n, 'so_du_truoc_vnd', v_sd0::text,
        'so_du_sau_vnd', v_sd1::text, 'sau_khoa', v_sk));
END $$;

CREATE OR REPLACE FUNCTION doixe.get_so(p_loai text, p_id bigint, p_thang date) RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = pg_catalog, doixe, pg_temp AS $$
-- Sổ người (thẻ tiền tháng, ứng, đợt hoàn, chặng người đó lái hoặc trả, dòng chưa hoàn mọi tháng) hoặc sổ xe (mọi chặng của xe).
-- DX-05: lần ứng và đợt hoàn có `sau_khoa`; `huy` có `sau_khoa` (hủy khi tháng đã khóa).
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
                        'ghi_chu', u.ghi_chu, 'sau_khoa', u.sau_khoa, 'actor', u.actor, 'luc', doixe._luc(u.luc),
                        'huy', CASE WHEN u.huy_luc IS NULL THEN NULL
                                    ELSE jsonb_build_object('actor', u.huy_actor, 'luc', doixe._luc(u.huy_luc), 'ly_do', u.huy_ly_do,
                                                            'sau_khoa', u.huy_sau_khoa) END)
                      ORDER BY u.ngay, u.id), '[]'::jsonb) FROM doixe.ung u WHERE u.nguoi_id = n.id AND u.ngay >= m AND u.ngay < m2),
            'dot', (SELECT coalesce(jsonb_agg(jsonb_build_object('id', h.id, 'ngay', h.ngay, 'so_tien_vnd', h.so_tien_vnd::text,
                        'tong_dong_vnd', h.tong_dong_vnd::text, 'so_dong', cardinality(h.dong_ids), 'sau_khoa', h.sau_khoa,
                        'actor', h.actor, 'luc', doixe._luc(h.luc),
                        'huy', CASE WHEN h.huy_luc IS NULL THEN NULL
                                    ELSE jsonb_build_object('actor', h.huy_actor, 'luc', doixe._luc(h.huy_luc), 'ly_do', h.huy_ly_do,
                                                            'sau_khoa', h.huy_sau_khoa) END)
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

REVOKE ALL ON ALL FUNCTIONS IN SCHEMA doixe FROM PUBLIC;
COMMIT;
