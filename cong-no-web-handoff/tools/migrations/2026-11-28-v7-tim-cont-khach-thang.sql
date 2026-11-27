-- Tìm số cont và khách theo tháng (TIM-CONT-01, KHACH-THANG-01, 28/11/2026): hai hàm đọc cho ô Tìm khách ở menu và khối "Khách theo
-- tháng" của Tổng quan. Chỉ thêm hai hàm đọc và quyền EXECUTE: không đổi bảng, view, hàm ghi, phân bổ hay dữ liệu. Chạy lại được.
BEGIN;
SET LOCAL ROLE sokhach_owner;

CREATE OR REPLACE FUNCTION sokhach.find_container(p_query text) RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = pg_catalog, sokhach, pg_temp AS $$
-- TIM-CONT-01. Chuyến có số cont chứa chuỗi tìm (bỏ khoảng trắng, không phân biệt hoa thường), ở mọi sổ đang hoạt động: chuyến web
-- chưa xóa, không bị loại (cả chuyến chờ kiểm); dòng chuyến sổ gốc theo bản sửa mới nhất, chưa xóa. Lọc ứng viên theo cont của bản
-- gốc hoặc của bất kỳ bản sửa nào, rồi mới đọc bản hiện hành và lọc lại. Trùng khớp nguyên số trước, rồi ngày chuyến mới trước;
-- trả tối đa 30 dòng và cờ more khi còn nữa. Chỉ đọc.
DECLARE v_key text := sokhach._normalize_key(p_query); v_limit int := 30;
BEGIN
  PERFORM sokhach._actor();
  IF length(v_key) < 4 OR length(v_key) > 20 THEN RAISE EXCEPTION 'INVALID_QUERY'; END IF;
  RETURN (WITH act AS (
      SELECT c.id,cc.cutover_id FROM sokhach.customer c
        JOIN sokhach.cutover_customer cc ON cc.customer_id=c.id AND cc.status='active'
        JOIN sokhach.cutover x ON x.id=cc.cutover_id AND x.status='active'
       WHERE NOT c.archived),
    web_cand AS (SELECT t.id FROM sokhach.trip t WHERE strpos(sokhach._normalize_key(t.container),v_key)>0
        UNION SELECT r.trip_id FROM sokhach.trip_info_rev r WHERE strpos(sokhach._normalize_key(r.container),v_key)>0),
    web AS (SELECT t.customer_id,t.debt_month,t.event_date AS dt,t.container AS cont,t.origin,t.destination,
            CASE WHEN t.status='confirmed' THEN 'web' ELSE 'pending' END AS src
        FROM web_cand w JOIN sokhach.v_trip_current t ON t.id=w.id JOIN act ON act.id=t.customer_id
       WHERE NOT t.deleted AND t.status<>'rejected'),
    leg_cand AS (SELECT l.id FROM sokhach.legacy_row l
        WHERE l.kind='trip' AND strpos(sokhach._normalize_key(l.display->>'container'),v_key)>0
        UNION SELECT y.legacy_row_id FROM sokhach.legacy_trip_rev y WHERE strpos(sokhach._normalize_key(y.container),v_key)>0),
    leg AS (SELECT l.customer_id,coalesce(r.debt_month,l.debt_month) AS debt_month,
            CASE WHEN r.id IS NULL THEN sokhach._legacy_date(l.display->>'date') ELSE r.event_date END AS dt,
            CASE WHEN r.id IS NULL THEN l.display->>'container' ELSE r.container END AS cont,
            CASE WHEN r.id IS NULL THEN l.display->>'from' ELSE r.origin END AS origin,
            CASE WHEN r.id IS NULL THEN l.display->>'to' ELSE r.destination END AS destination,'legacy'::text AS src
        FROM leg_cand c JOIN sokhach.legacy_row l ON l.id=c.id AND l.kind='trip'
        JOIN act ON (act.id,act.cutover_id)=(l.customer_id,l.cutover_id)
        LEFT JOIN LATERAL (SELECT x.id,x.debt_month,x.event_date,x.container,x.origin,x.destination,x.deleted
            FROM sokhach.legacy_trip_rev x WHERE x.legacy_row_id=l.id ORDER BY x.id DESC LIMIT 1) r ON true
       WHERE NOT coalesce(r.deleted,false)),
    hit AS (SELECT *,sokhach._normalize_key(cont)=v_key AS exact FROM (SELECT * FROM web UNION ALL SELECT * FROM leg) a
       WHERE strpos(sokhach._normalize_key(cont),v_key)>0),
    top AS (SELECT * FROM hit ORDER BY exact DESC,dt DESC NULLS LAST,debt_month DESC,customer_id,cont LIMIT v_limit)
  SELECT jsonb_build_object('query',v_key,'more',(SELECT count(*) FROM hit)>v_limit,
    'items',(SELECT coalesce(jsonb_agg(jsonb_build_object('customer_id',t.customer_id,'debt_month',t.debt_month,'date',t.dt,
        'container',t.cont,'origin',t.origin,'destination',t.destination,'source',t.src)
        ORDER BY t.exact DESC,t.dt DESC NULLS LAST,t.debt_month DESC,t.customer_id,t.cont),'[]'::jsonb) FROM top t)));
END $$;
ALTER FUNCTION sokhach.find_container(text) OWNER TO sokhach_owner;
REVOKE ALL ON FUNCTION sokhach.find_container(text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION sokhach.find_container(text) TO sokhach_app;
GRANT EXECUTE ON FUNCTION sokhach.find_container(text) TO sokhach_reader;

CREATE OR REPLACE FUNCTION sokhach.get_month_customers(p_month date) RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = pg_catalog, sokhach, pg_temp SET jit = off AS $$
-- KHACH-THANG-01. Mỗi sổ đang hoạt động có phát sinh, đã thu hoặc còn nợ khác 0 ở một tháng (trống là tháng hiện tại, giờ VN):
-- phát sinh và đã thu cộng đúng dòng Tổng tháng của get_ledger (DA-THU-01), cùng phép tính this_month của get_dashboard_debt (harness
-- KHACH-THANG.01 so hai hàm ở tháng hiện tại); còn nợ của tháng là v_outstanding_month của tháng nợ đó (như Công nợ theo tháng).
-- Tổng cộng bằng numeric để không tràn số. Chỉ đọc.
DECLARE m date := coalesce(p_month,date_trunc('month',(now() AT TIME ZONE 'Asia/Ho_Chi_Minh'))::date);
BEGIN
  PERFORM sokhach._actor();
  IF date_trunc('month',m)::date <> m THEN RAISE EXCEPTION 'INVALID_MONTH'; END IF;
  RETURN (WITH act AS (
      SELECT c.id,cc.cutover_id FROM sokhach.customer c
        JOIN sokhach.cutover_customer cc ON cc.customer_id=c.id AND cc.status='active'
        JOIN sokhach.cutover x ON x.id=cc.cutover_id AND x.status='active'
       WHERE NOT c.archived),
    -- Như month_keys của get_ledger: sổ không có dòng tháng này thì tháng này không có số.
    keyed AS (SELECT a.id,a.cutover_id FROM act a WHERE
        EXISTS (SELECT 1 FROM sokhach.v_outstanding_month v WHERE v.customer_id=a.id AND v.debt_month=m)
        OR EXISTS (SELECT 1 FROM sokhach.v_trip_current t WHERE NOT t.deleted AND t.customer_id=a.id AND t.debt_month=m)
        OR EXISTS (SELECT 1 FROM sokhach.receipt r WHERE r.customer_id=a.id AND r.voided_on IS NULL
          AND date_trunc('month',r.date)::date=m)),
    flow_c AS (SELECT k.id,
        coalesce(s.source_charge_vnd,(SELECT sum(o.amount_vnd) FROM sokhach.opening_balance o
            WHERE o.customer_id=k.id AND o.cutover_id=k.cutover_id AND o.debt_month=m),0)
          +coalesce((SELECT sum(CASE WHEN p.unit_price_vnd IS NOT NULL THEN p.unit_price_vnd+coalesce(p.other_fee_vnd,0)
              WHEN t.container IS NULL OR t.container='' THEN p.other_fee_vnd END)
              FROM sokhach.v_trip_current t LEFT JOIN LATERAL
                (SELECT unit_price_vnd,other_fee_vnd FROM sokhach.trip_price_rev
                 WHERE trip_id=t.id ORDER BY id DESC LIMIT 1) p ON true
              WHERE t.customer_id=k.id AND t.debt_month=m AND NOT t.deleted AND t.status='confirmed'),0)
          +coalesce((SELECT sum(a.amount_vnd) FROM sokhach.v_adjustment_current a
              LEFT JOIN sokhach.legacy_row lr ON lr.id=a.legacy_row_id
              WHERE a.customer_id=k.id AND a.debt_month=m AND lr.kind IS DISTINCT FROM 'receipt'),0) AS charges,
        coalesce(s.source_receipt_vnd,0)
          +coalesce((SELECT sum(r.amount_vnd) FROM sokhach.receipt r
              WHERE r.customer_id=k.id AND r.voided_on IS NULL AND date_trunc('month',r.date)::date=m),0)
          -coalesce((SELECT sum(o.amount_vnd) FROM sokhach.v_offset_outgoing o
              WHERE o.customer_id=k.id AND o.debt_month=m),0)
          -coalesce((SELECT sum(a.amount_vnd) FROM sokhach.v_adjustment_current a
              JOIN sokhach.legacy_row lr ON lr.id=a.legacy_row_id AND lr.kind='receipt'
              WHERE a.customer_id=k.id AND a.debt_month=m),0) AS received,
        coalesce((SELECT sum(v.outstanding_vnd) FROM sokhach.v_outstanding_month v
            WHERE v.customer_id=k.id AND v.debt_month=m),0) AS outstanding
        FROM keyed k LEFT JOIN LATERAL (SELECT mc.source_charge_vnd,mc.source_receipt_vnd
            FROM sokhach.cutover_month_check mc
           WHERE mc.customer_id=k.id AND mc.cutover_id=k.cutover_id AND mc.debt_month=m
             AND mc.source_charge_vnd IS NOT NULL AND mc.source_receipt_vnd IS NOT NULL) s ON true),
    rows AS (SELECT * FROM flow_c WHERE charges<>0 OR received<>0 OR outstanding<>0)
  SELECT jsonb_build_object('month',m::text,
    'charges_vnd',(SELECT coalesce(sum(charges),0)::text FROM rows),
    'received_vnd',(SELECT coalesce(sum(received),0)::text FROM rows),
    'outstanding_vnd',(SELECT coalesce(sum(outstanding),0)::text FROM rows),
    'customers',(SELECT coalesce(jsonb_agg(jsonb_build_object('customer_id',r.id,'charges_vnd',r.charges::text,
        'received_vnd',r.received::text,'outstanding_vnd',r.outstanding::text) ORDER BY r.charges DESC,r.id),'[]'::jsonb) FROM rows r)));
END $$;
ALTER FUNCTION sokhach.get_month_customers(date) OWNER TO sokhach_owner;
REVOKE ALL ON FUNCTION sokhach.get_month_customers(date) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION sokhach.get_month_customers(date) TO sokhach_app;
GRANT EXECUTE ON FUNCTION sokhach.get_month_customers(date) TO sokhach_reader;
COMMIT;
