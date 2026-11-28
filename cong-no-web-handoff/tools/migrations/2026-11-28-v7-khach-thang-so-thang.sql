-- Bảng khách lọc tháng là sổ tháng (KHACH-THANG-02, 28/11/2026): get_month_customers thêm nợ đầu tháng (prior_months_vnd) và còn nợ
-- cuối tháng (end_of_month_vnd) của từng sổ, cùng phép và cùng tên trường với thanh tháng của get_ledger. Chỉ thay một hàm đọc, giữ chữ ký
-- và quyền: không đổi bảng, view, hàm ghi, phân bổ hay dữ liệu. Chạy lại được.
BEGIN;
SET LOCAL ROLE sokhach_owner;

CREATE OR REPLACE FUNCTION sokhach.get_month_customers(p_month date) RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = pg_catalog, sokhach, pg_temp SET jit = off AS $$
-- KHACH-THANG-01. Mỗi sổ đang hoạt động có phát sinh, đã thu hoặc còn nợ khác 0 ở một tháng (trống là tháng hiện tại, giờ VN):
-- phát sinh và đã thu cộng đúng dòng Tổng tháng của get_ledger (DA-THU-01), cùng phép tính this_month của get_dashboard_debt (harness
-- KHACH-THANG.01 so hai hàm ở tháng hiện tại); còn nợ của tháng là v_outstanding_month của tháng nợ đó (như Công nợ theo tháng).
-- KHACH-THANG-02: thêm nợ đầu tháng và còn nợ cuối tháng như thanh tháng của Sổ khách (SO-GON-05), cùng phép với get_ledger: cuối
-- tháng = tổng còn nợ trừ (phát sinh − đã thu) của các tháng sau trong cùng tập month_keys, đầu tháng = cuối − phát sinh + đã thu;
-- harness so từng sổ với get_ledger. Tổng cộng bằng numeric để không tràn số. Chỉ đọc.
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
    -- Tháng m và các tháng sau của các sổ đó, đúng tập month_keys của get_ledger (dòng tháng hiện tại get_ledger luôn thêm có
    -- phát sinh, đã thu bằng 0 nên không đổi số cuối tháng).
    months AS (SELECT k.id,k.cutover_id,x.dm FROM keyed k CROSS JOIN LATERAL (
        SELECT v.debt_month AS dm FROM sokhach.v_outstanding_month v WHERE v.customer_id=k.id AND v.debt_month>=m
        UNION SELECT t.debt_month FROM sokhach.v_trip_current t WHERE NOT t.deleted AND t.customer_id=k.id AND t.debt_month>=m
        UNION SELECT date_trunc('month',r.date)::date FROM sokhach.receipt r
          WHERE r.customer_id=k.id AND r.voided_on IS NULL AND r.date>=m) x),
    flow_c AS (SELECT k.id,k.dm,
        coalesce(s.source_charge_vnd,(SELECT sum(o.amount_vnd) FROM sokhach.opening_balance o
            WHERE o.customer_id=k.id AND o.cutover_id=k.cutover_id AND o.debt_month=k.dm),0)
          +coalesce((SELECT sum(CASE WHEN p.unit_price_vnd IS NOT NULL THEN p.unit_price_vnd+coalesce(p.other_fee_vnd,0)
              WHEN t.container IS NULL OR t.container='' THEN p.other_fee_vnd END)
              FROM sokhach.v_trip_current t LEFT JOIN LATERAL
                (SELECT unit_price_vnd,other_fee_vnd FROM sokhach.trip_price_rev
                 WHERE trip_id=t.id ORDER BY id DESC LIMIT 1) p ON true
              WHERE t.customer_id=k.id AND t.debt_month=k.dm AND NOT t.deleted AND t.status='confirmed'),0)
          +coalesce((SELECT sum(a.amount_vnd) FROM sokhach.v_adjustment_current a
              LEFT JOIN sokhach.legacy_row lr ON lr.id=a.legacy_row_id
              WHERE a.customer_id=k.id AND a.debt_month=k.dm AND lr.kind IS DISTINCT FROM 'receipt'),0) AS charges,
        coalesce(s.source_receipt_vnd,0)
          +coalesce((SELECT sum(r.amount_vnd) FROM sokhach.receipt r
              WHERE r.customer_id=k.id AND r.voided_on IS NULL AND date_trunc('month',r.date)::date=k.dm),0)
          -coalesce((SELECT sum(o.amount_vnd) FROM sokhach.v_offset_outgoing o
              WHERE o.customer_id=k.id AND o.debt_month=k.dm),0)
          -coalesce((SELECT sum(a.amount_vnd) FROM sokhach.v_adjustment_current a
              JOIN sokhach.legacy_row lr ON lr.id=a.legacy_row_id AND lr.kind='receipt'
              WHERE a.customer_id=k.id AND a.debt_month=k.dm),0) AS received
        FROM months k LEFT JOIN LATERAL (SELECT mc.source_charge_vnd,mc.source_receipt_vnd
            FROM sokhach.cutover_month_check mc
           WHERE mc.customer_id=k.id AND mc.cutover_id=k.cutover_id AND mc.debt_month=k.dm
             AND mc.source_charge_vnd IS NOT NULL AND mc.source_receipt_vnd IS NOT NULL) s ON true),
    later AS (SELECT id,sum(charges-received) AS net FROM flow_c WHERE dm>m GROUP BY id),
    figures AS (SELECT f.id,f.charges,f.received,
        coalesce((SELECT sum(v.outstanding_vnd) FROM sokhach.v_outstanding_month v
            WHERE v.customer_id=f.id AND v.debt_month=m),0) AS outstanding,
        coalesce((SELECT sum(v.outstanding_vnd) FROM sokhach.v_outstanding_month v WHERE v.customer_id=f.id),0)
          -coalesce(l.net,0) AS end_of_month
        FROM flow_c f LEFT JOIN later l ON l.id=f.id WHERE f.dm=m),
    rows AS (SELECT * FROM figures WHERE charges<>0 OR received<>0 OR outstanding<>0)
  SELECT jsonb_build_object('month',m::text,
    'charges_vnd',(SELECT coalesce(sum(charges),0)::text FROM rows),
    'received_vnd',(SELECT coalesce(sum(received),0)::text FROM rows),
    'outstanding_vnd',(SELECT coalesce(sum(outstanding),0)::text FROM rows),
    'customers',(SELECT coalesce(jsonb_agg(jsonb_build_object('customer_id',r.id,'charges_vnd',r.charges::text,
        'received_vnd',r.received::text,'outstanding_vnd',r.outstanding::text,
        'prior_months_vnd',(r.end_of_month-r.charges+r.received)::text,'end_of_month_vnd',r.end_of_month::text)
        ORDER BY r.charges DESC,r.id),'[]'::jsonb) FROM rows r)));
END $$;
ALTER FUNCTION sokhach.get_month_customers(date) OWNER TO sokhach_owner;
REVOKE ALL ON FUNCTION sokhach.get_month_customers(date) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION sokhach.get_month_customers(date) TO sokhach_app;
GRANT EXECUTE ON FUNCTION sokhach.get_month_customers(date) TO sokhach_reader;
COMMIT;
