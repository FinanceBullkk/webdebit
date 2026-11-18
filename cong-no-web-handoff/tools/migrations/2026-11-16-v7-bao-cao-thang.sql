-- Báo cáo tháng (BAO-CAO-THANG-01, 16/11/2026): hàm đọc get_trip_month cho cột "Web" của trang Báo cáo tháng. Chỉ thêm một hàm đọc và
-- quyền EXECUTE: không đổi bảng, view, hàm ghi, phân bổ hay dữ liệu. Chạy lại được.
BEGIN;
SET LOCAL ROLE sokhach_owner;
CREATE OR REPLACE FUNCTION sokhach.get_trip_month(p_month date) RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = pg_catalog, sokhach, pg_temp AS $$
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
END $$;
REVOKE ALL ON FUNCTION sokhach.get_trip_month(date) FROM PUBLIC, sokhach_app, sokhach_reader;
GRANT EXECUTE ON FUNCTION sokhach.get_trip_month(date) TO sokhach_app, sokhach_reader;
RESET ROLE;
COMMIT;
