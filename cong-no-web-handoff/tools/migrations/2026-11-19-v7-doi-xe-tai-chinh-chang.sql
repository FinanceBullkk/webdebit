-- Đội xe: hàm đọc thu, chi, lãi gộp của chặng (DOI-XE-CHANG-01 PR 2, 19/11/2026; specs/doi-xe-chang-01.md, gói B2 của
-- specs/doi-xe-cau-truc-01.md). Áp sau 2026-11-19-v7-doi-xe-dieu-do.sql. CHỈ có hàm đọc: không đổi bảng, ràng buộc, hàm ghi, quyền
-- trên bảng; không ghi `sokhach`; không seed dữ liệu. Chạy lại được.
--
-- * `_tai_chinh_chang(id)` (hàm phụ, không cấp cho ai): một chặng với phần chi, phần thu và lãi gộp. Phần thu lấy đúng từ
--   `_tinh_chang` (chặng chưa gửi bảng kê) hoặc từ dòng bảng kê đã chép lúc gửi (chặng đã gửi), nên cộng lại bằng `get_bang_ke`;
--   không viết lại cách tính tiền. Phần chi cộng từng loại phí qua mọi dòng của chặng (gốc, điều chỉnh, trừ lại), nên cộng lại
--   bằng `get_so`. Hình dạng theo mô hình mới của DOI-XE-MO-HINH-01 (chi từng khoản có người trả, thu từng dòng); giá trị suy từ mô
--   hình hiện tại: người trả của một khoản = công ty nếu loại phí do công ty trả (`loai_phi.cong_ty_tra`) hoặc chặng do công ty
--   trả, ngược lại là `chang.nguoi_tra_id`.
-- * `get_chang_tai_chinh(jsonb)`: `{tu, den, ids}`. Trả các chặng chưa xóa, chưa bỏ có ngày chạy hoặc ngày đóng trong [tu, den], hoặc
--   có id trong `ids` (API truyền id các chặng đã nối với việc để chặng lệch ngày vẫn có số). Mỗi chặng là `_chang_dd` cộng các
--   trường tài chính.
-- * Lãi gộp = thu không chi hộ − chi không chi hộ; NULL (không phải 0) khi chặng chưa có giá, chưa có phí, còn khoản ghi chú chưa
--   đọc được, hoặc không vào bảng kê (chưa có xe, xe thuê ngoài). Mảng `thieu` nói lý do.
BEGIN;
SET LOCAL ROLE sokhach_owner;

CREATE OR REPLACE FUNCTION doixe._tai_chinh_chang(p_id bigint) RETURNS jsonb
LANGUAGE plpgsql STABLE SET search_path = pg_catalog, doixe, pg_temp AS $$
DECLARE c doixe.chang; x doixe.xe; b doixe.ben; k doixe.bang_ke; d doixe.bang_ke_dong;
        t jsonb; v_dc bigint; v_thang date; v_gui boolean := false;
        v_chi jsonb; v_chi_tong bigint; v_chi_ho bigint; v_co_phi boolean; v_hoan boolean;
        v_cuoc bigint; v_ghep bigint; v_ps bigint; v_chiho_thu bigint; v_doi bigint; v_doc integer;
        v_dong jsonb; v_loi jsonb; v_thu jsonb; v_thieu text[] := '{}';
        v_thu_kch bigint; v_chi_kch bigint; v_lai bigint;
BEGIN
    SELECT * INTO c FROM doixe.chang WHERE id = p_id;
    SELECT * INTO x FROM doixe.xe WHERE id = c.xe_id;
    -- Chi: từng loại phí, tổng mọi dòng của chặng (dòng gốc cộng điều chỉnh cộng trừ lại).
    SELECT coalesce(jsonb_agg(jsonb_build_object(
               'khoan', s.ma, 'ten', s.ten, 'so_tien_vnd', s.tien::text,
               'nguoi_tra', s.nt, 'nguoi_tra_id', CASE WHEN s.nt = 'nguoi' THEN c.nguoi_tra_id END,
               'chi_ho', s.chi_ho, 'da_hoan', s.hoan) ORDER BY s.thu_tu), '[]'::jsonb),
           sum(s.tien)::bigint, (sum(s.tien) FILTER (WHERE s.chi_ho))::bigint, count(*) > 0
      INTO v_chi, v_chi_tong, v_chi_ho, v_co_phi
      FROM (SELECT l.ma, l.ten, l.thu_tu, l.chi_ho, sum(f.so_tien_vnd) AS tien,
                   CASE WHEN l.cong_ty_tra OR c.tra = 'cong_ty' THEN 'cong_ty' ELSE 'nguoi' END AS nt,
                   -- Hoàn chỉ áp cho khoản người trả: NULL (không áp dụng) với khoản công ty trả.
                   CASE WHEN l.cong_ty_tra OR c.tra = 'cong_ty' THEN NULL ELSE bool_and(dd.dot_hoan_id IS NOT NULL) END AS hoan
              FROM doixe.dong dd JOIN doixe.dong_phi f ON f.dong_id = dd.id JOIN doixe.loai_phi l ON l.ma = f.loai_phi
             WHERE dd.chang_id = c.id
             GROUP BY l.ma, l.ten, l.thu_tu, l.chi_ho, l.cong_ty_tra) s;
    SELECT coalesce(bool_or(dd.dot_hoan_id IS NOT NULL), false) INTO v_hoan FROM doixe.dong dd WHERE dd.chang_id = c.id;

    -- Thu: dòng bảng kê đã chép (chặng đã gửi) hoặc tính sống (chặng xe công ty chưa gửi).
    SELECT * INTO d FROM doixe.bang_ke_dong WHERE chang_id = c.id;
    IF FOUND THEN
        v_gui := true;
        SELECT * INTO k FROM doixe.bang_ke WHERE id = d.bang_ke_id;
        v_thang := k.thang;
        SELECT sum(a.so_tien_vnd)::bigint INTO v_dc FROM doixe.dieu_chinh_bk a WHERE a.dong_id = d.id;
        t := jsonb_build_object('cuoc_vnd', d.cuoc_vnd::text, 'gia_bang_vnd', d.gia_bang_vnd::text, 'cuoc_tay', d.cuoc_tay,
                                'tuyen_id', NULL, 'tuyen', d.tuyen, 'ghep_vnd', d.ghep_vnd::text, 'ps_vnd', d.ps_vnd::text,
                                'chi_ho_vnd', d.chi_ho_vnd::text, 'ps', d.ps);
    ELSIF x.id IS NOT NULL THEN
        SELECT * INTO b FROM doixe.ben WHERE xe_thue_ngoai = x.thue_ngoai;
        IF FOUND THEN
            t := doixe._tinh_chang(c.id, b.ma);
            v_thang := doixe._thang_gom(b.ma, c.ngay);
        END IF;
    END IF;

    IF t IS NULL THEN
        v_thu := NULL;
        v_thieu := ARRAY['khong_vao_bang_ke'];
    ELSE
        v_cuoc := (t ->> 'cuoc_vnd')::bigint;
        v_ghep := coalesce((t ->> 'ghep_vnd')::bigint, 0);
        v_ps := coalesce((t ->> 'ps_vnd')::bigint, 0);
        v_chiho_thu := coalesce((t ->> 'chi_ho_vnd')::bigint, 0);
        v_doc := (SELECT count(*) FROM jsonb_array_elements(t -> 'ps') e WHERE e ? 'loi');
        -- Số đòi của chặng cộng đúng như get_bang_ke: ô trống góp 0 (cước trống: chưa có giá, xem `cuoc.vnd`).
        v_doi := coalesce(v_cuoc, 0) + v_ghep + v_ps + coalesce(v_dc, 0);
        SELECT coalesce(jsonb_agg(jsonb_build_object(
                   'khoan', e ->> 'ma', 'ten', e ->> 'ten',
                   -- Số lượng chỉ có khi lấy từ ô số lượng của chặng và chặng chưa gửi (chặng đã gửi đóng băng bản chép).
                   'so_luong', CASE WHEN NOT v_gui AND (e ->> 'o')::boolean IS TRUE THEN
                                         CASE e ->> 'ma' WHEN 'neo' THEN c.neo_ngay WHEN 'no_may' THEN c.may_gio END END,
                   'muc_vnd', NULL, 'so_tien_vnd', e ->> 'so_tien_vnd', 'chi_ho', coalesce((e ->> 'chi_ho')::boolean, false),
                   'cot', e ->> 'cot', 'la', coalesce((e ->> 'la')::boolean, false)) ORDER BY n), '[]'::jsonb)
          INTO v_dong FROM jsonb_array_elements(t -> 'ps') WITH ORDINALITY AS z(e, n) WHERE e ? 'so_tien_vnd';
        SELECT coalesce(jsonb_agg(jsonb_build_object('goc', e ->> 'goc', 'loi', e ->> 'loi') ORDER BY n), '[]'::jsonb)
          INTO v_loi FROM jsonb_array_elements(t -> 'ps') WITH ORDINALITY AS z(e, n) WHERE e ? 'loi';
        v_thu := jsonb_build_object(
            'cuoc', jsonb_build_object('vnd', t ->> 'cuoc_vnd', 'gia_bang_vnd', t ->> 'gia_bang_vnd', 'tay', coalesce((t ->> 'cuoc_tay')::boolean, false),
                                       'tuyen_id', (t ->> 'tuyen_id')::bigint, 'tuyen', t ->> 'tuyen'),
            'ghep_vnd', v_ghep::text, 'ps_vnd', v_ps::text, 'chi_ho_vnd', v_chiho_thu::text, 'dc_vnd', v_dc::text, 'doi_vnd', v_doi::text,
            'dong', v_dong, 'loi', v_loi, 'chua_doc', v_doc);
        IF v_cuoc IS NULL THEN v_thieu := array_append(v_thieu, 'gia'); END IF;
    END IF;
    IF NOT v_co_phi THEN v_thieu := array_append(v_thieu, 'phi'); END IF;
    IF v_doc > 0 THEN v_thieu := array_append(v_thieu, 'doc'); END IF;
    IF t IS NOT NULL AND v_cuoc IS NOT NULL THEN v_thu_kch := v_doi - v_chiho_thu; END IF;
    IF v_co_phi THEN v_chi_kch := v_chi_tong - coalesce(v_chi_ho, 0); END IF;
    IF cardinality(v_thieu) = 0 THEN v_lai := v_thu_kch - v_chi_kch; END IF;

    RETURN jsonb_build_object(
        'thang_khoa', doixe._khoa(c.ngay), 'bang_ke_thang', v_thang, 'da_gui', v_gui, 'da_hoan', v_hoan, 'co_phi', v_co_phi,
        'chi', jsonb_build_object('dong', v_chi, 'tong_vnd', v_chi_tong::text, 'chi_ho_vnd', coalesce(v_chi_ho, 0)::text,
                                  'ngoai_chi_ho_vnd', v_chi_kch::text),
        'thu', v_thu,
        'lai_gop', jsonb_build_object('thu_vnd', v_thu_kch::text, 'chi_vnd', v_chi_kch::text, 'lai_vnd', v_lai::text,
                                      'thieu', to_jsonb(v_thieu)));
END $$;

-- Hàm đọc (cấp cho sokhach_app). `p`: {tu, den, ids}; tu và den cùng có hoặc cùng vắng; phải có khoảng hoặc ids.
CREATE OR REPLACE FUNCTION doixe.get_chang_tai_chinh(p jsonb) RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = pg_catalog, doixe, pg_temp AS $$
DECLARE v_tu date; v_den date; v_ids bigint[] := '{}'; e jsonb;
BEGIN
    PERFORM doixe._actor();
    PERFORM doixe._chi_khoa(p, ARRAY['tu', 'den', 'ids']);
    v_tu := doixe._ngay(p -> 'tu');
    v_den := doixe._ngay(p -> 'den');
    IF (v_tu IS NULL) <> (v_den IS NULL) OR (v_tu IS NOT NULL AND (v_den < v_tu OR v_den - v_tu > 400)) THEN RAISE EXCEPTION 'INVALID_COMMAND'; END IF;
    IF p ? 'ids' AND jsonb_typeof(p -> 'ids') <> 'null' THEN
        IF jsonb_typeof(p -> 'ids') <> 'array' OR jsonb_array_length(p -> 'ids') > 3000 THEN RAISE EXCEPTION 'INVALID_COMMAND'; END IF;
        FOR e IN SELECT * FROM jsonb_array_elements(p -> 'ids') LOOP
            IF jsonb_typeof(e) <> 'number' OR (e #>> '{}') !~ '^[1-9][0-9]{0,17}$' THEN RAISE EXCEPTION 'INVALID_COMMAND'; END IF;
            v_ids := v_ids || (e #>> '{}')::bigint;
        END LOOP;
    END IF;
    IF v_tu IS NULL AND cardinality(v_ids) = 0 THEN RAISE EXCEPTION 'INVALID_COMMAND'; END IF;
    RETURN jsonb_build_object(
        'hom_nay', doixe._hom_nay(),
        'chang', (SELECT coalesce(jsonb_agg(doixe._chang_dd(c.id) || doixe._tai_chinh_chang(c.id) ORDER BY c.ngay, c.id), '[]'::jsonb)
                    FROM doixe.chang c
                   WHERE NOT c.da_xoa AND NOT c.da_bo
                     AND (c.id = ANY (v_ids) OR (v_tu IS NOT NULL AND (c.ngay BETWEEN v_tu AND v_den OR c.ngay_dong BETWEEN v_tu AND v_den)))));
END $$;

-- Quyền: chỉ hàm đọc mới cho app; hàm phụ không cấp cho ai. Không quyền trên bảng.
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA doixe FROM PUBLIC;
GRANT EXECUTE ON FUNCTION doixe.get_chang_tai_chinh(jsonb) TO sokhach_app;
COMMIT;
