-- DASH-03 (29/10/2026): Tổng quan quản lý công nợ. Chỉ thêm hai hàm đọc; không đổi bảng, view,
-- hàm cũ, tiền hay phân bổ. Chạy lại được. Áp sau mọi migration ngày 29/10/2026 đã có trên hao.
BEGIN;
SET LOCAL ROLE sokhach_owner;

-- Ngày ghi trong ô của dòng sổ gốc (YYYY-MM-DD hoặc DD/MM/YYYY); ô trống hay sai thì NULL, như _legacy_current.
CREATE OR REPLACE FUNCTION sokhach._legacy_date(p_text text) RETURNS date
LANGUAGE plpgsql STABLE SET search_path=pg_catalog,sokhach,pg_temp AS $$
DECLARE v_date date;
BEGIN
    IF p_text ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$' THEN v_date:=p_text::date;
    ELSIF p_text ~ '^[0-9]{2}/[0-9]{2}/[0-9]{4}$' THEN
        v_date:=to_date(p_text,'DD/MM/YYYY');
        IF to_char(v_date,'DD/MM/YYYY')<>p_text THEN v_date:=NULL; END IF;
    END IF;
    RETURN v_date;
EXCEPTION WHEN invalid_datetime_format OR datetime_field_overflow THEN RETURN NULL;
END $$;

CREATE OR REPLACE FUNCTION sokhach.get_dashboard_debt() RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, sokhach, pg_temp AS $$
-- DASH-03 (29/10/2026). Nhóm hạn trả theo tháng nợ (giờ VN): nợ tháng M đến hạn cuối tháng M+1,
-- số tháng quá hạn = (tháng hiện tại - M) - 1: dưới 0 chưa đến hạn, 0 đến hạn cuối tháng này, 1-2, 3-6, từ 7.
-- Rủi ro cao = có nợ quá hạn và (quá hạn từ 3 tháng, hoặc hơn 60 ngày chưa trả hay chưa trả lần nào, hoặc
-- hơn 90 ngày không đi hàng hay chưa có chuyến); còn nợ quá hạn khác là theo dõi. Lần trả: phiếu chưa hủy
-- (cả cấn trừ) và dòng thu sổ gốc chưa xóa; lần đi hàng: chuyến chưa xóa, không tính đã loại, và dòng chuyến
-- sổ gốc chưa xóa. Ngày của dòng không có ngày lấy cuối tháng của dòng (exact=false).
-- Thu/phát sinh tháng này cộng đúng dòng Tổng tháng của get_ledger (DA-THU-01) qua mọi sổ đang hoạt động.
-- Tổng cộng bằng numeric (không ép bigint) để không tràn số khi cộng nhiều sổ.
DECLARE d date := (now() AT TIME ZONE 'Asia/Ho_Chi_Minh')::date; m date := date_trunc('month', d)::date;
BEGIN
  PERFORM sokhach._actor();
  RETURN (WITH act AS (
      SELECT c.id,c.name,c.commodity_id,c.transport_mode,cc.cutover_id FROM sokhach.customer c
        JOIN sokhach.cutover_customer cc ON cc.customer_id=c.id AND cc.status='active'
        JOIN sokhach.cutover x ON x.id=cc.cutover_id AND x.status='active'
       WHERE NOT c.archived),
    om AS (SELECT v.customer_id,v.debt_month,v.outstanding_vnd,
        ((extract(year FROM m)-extract(year FROM v.debt_month))*12
          +extract(month FROM m)-extract(month FROM v.debt_month))::int-1 AS late
        FROM sokhach.v_outstanding_month v JOIN act ON act.id=v.customer_id),
    debtor AS (SELECT act.*,s.total FROM act
        JOIN (SELECT customer_id,sum(outstanding_vnd) AS total FROM om GROUP BY customer_id) s ON s.customer_id=act.id
       WHERE s.total>0),
    tier AS (SELECT om.customer_id,
        coalesce(sum(om.outstanding_vnd) FILTER (WHERE om.late<0),0) AS t0,
        coalesce(sum(om.outstanding_vnd) FILTER (WHERE om.late=0),0) AS t1,
        coalesce(sum(om.outstanding_vnd) FILTER (WHERE om.late BETWEEN 1 AND 2),0) AS t2,
        coalesce(sum(om.outstanding_vnd) FILTER (WHERE om.late BETWEEN 3 AND 6),0) AS t3,
        coalesce(sum(om.outstanding_vnd) FILTER (WHERE om.late>=7),0) AS t4,
        min(om.debt_month) FILTER (WHERE om.outstanding_vnd>0) AS oldest,
        coalesce(jsonb_agg(jsonb_build_object('month',om.debt_month,'outstanding_vnd',om.outstanding_vnd::text)
          ORDER BY om.debt_month) FILTER (WHERE om.outstanding_vnd<>0),'[]'::jsonb) AS months
        FROM om JOIN debtor b ON b.id=om.customer_id GROUP BY om.customer_id),
    leg AS (SELECT l.customer_id,l.kind,coalesce(r.debt_month,l.debt_month) AS mon,
        CASE WHEN r.id IS NULL THEN sokhach._legacy_date(l.display->>'date') ELSE r.event_date END AS dt
        FROM sokhach.legacy_row l JOIN debtor b ON (b.id,b.cutover_id)=(l.customer_id,l.cutover_id)
        LEFT JOIN LATERAL (SELECT x.id,x.debt_month,x.event_date,x.deleted FROM sokhach.legacy_trip_rev x
            WHERE x.legacy_row_id=l.id ORDER BY x.id DESC LIMIT 1) r ON true
       WHERE NOT coalesce(r.deleted,false)),
    pay_last AS (SELECT DISTINCT ON (customer_id) customer_id,dt,exact FROM (
        SELECT r.customer_id,r.date AS dt,true AS exact FROM sokhach.receipt r
          JOIN debtor b ON b.id=r.customer_id WHERE r.voided_on IS NULL
        UNION ALL
        SELECT customer_id,coalesce(dt,least((mon+interval '1 month')::date-1,d)),dt IS NOT NULL
          FROM leg WHERE kind='receipt') p ORDER BY customer_id,dt DESC,exact DESC),
    trip_last AS (SELECT DISTINCT ON (customer_id) customer_id,dt,exact FROM (
        SELECT t.customer_id,coalesce(t.event_date,least((t.debt_month+interval '1 month')::date-1,d)) AS dt,
               t.event_date IS NOT NULL AS exact
          FROM sokhach.v_trip_current t JOIN debtor b ON b.id=t.customer_id
         WHERE NOT t.deleted AND t.status<>'rejected'
        UNION ALL
        SELECT customer_id,coalesce(dt,least((mon+interval '1 month')::date-1,d)),dt IS NOT NULL
          FROM leg WHERE kind='trip') p ORDER BY customer_id,dt DESC,exact DESC),
    base AS (SELECT b.id,b.name,cm.name AS commodity,b.transport_mode,b.total,t.t0,t.t1,t.t2,t.t3,t.t4,
        t.t2+t.t3+t.t4 AS overdue,t.t3+t.t4 AS long_overdue,t.oldest,t.months,
        p.dt AS pay_day,p.exact AS pay_exact,CASE WHEN p.dt IS NOT NULL THEN greatest(d-p.dt,0) END AS pay_days,
        tr.dt AS trip_day,tr.exact AS trip_exact,CASE WHEN tr.dt IS NOT NULL THEN greatest(d-tr.dt,0) END AS trip_days
        FROM debtor b JOIN tier t ON t.customer_id=b.id
        LEFT JOIN pay_last p ON p.customer_id=b.id LEFT JOIN trip_last tr ON tr.customer_id=b.id
        LEFT JOIN sokhach.commodity cm ON cm.id=b.commodity_id),
    ranked AS (SELECT r.*,CASE WHEN r.overdue<=0 THEN 'ok'
        WHEN r.long_overdue>0 OR r.pay_days IS NULL OR r.pay_days>60 OR r.trip_days IS NULL OR r.trip_days>90 THEN 'high'
        ELSE 'watch' END AS risk FROM base r),
    -- Như month_keys của get_ledger: sổ không có dòng tháng này thì tháng này không có số.
    keyed AS (SELECT a.id,a.cutover_id FROM act a WHERE
        EXISTS (SELECT 1 FROM sokhach.v_outstanding_month v WHERE v.customer_id=a.id AND v.debt_month=m)
        OR EXISTS (SELECT 1 FROM sokhach.v_trip_current t WHERE NOT t.deleted AND t.customer_id=a.id AND t.debt_month=m)
        OR EXISTS (SELECT 1 FROM sokhach.receipt r WHERE r.customer_id=a.id AND r.voided_on IS NULL
          AND date_trunc('month',r.date)::date=m)),
    flow AS (SELECT
        coalesce(sum(coalesce(s.source_charge_vnd,(SELECT sum(o.amount_vnd) FROM sokhach.opening_balance o
            WHERE o.customer_id=k.id AND o.cutover_id=k.cutover_id AND o.debt_month=m),0)
          +coalesce((SELECT sum(CASE WHEN p.unit_price_vnd IS NOT NULL THEN p.unit_price_vnd+coalesce(p.other_fee_vnd,0)
              WHEN t.container IS NULL OR t.container='' THEN p.other_fee_vnd END)
              FROM sokhach.v_trip_current t LEFT JOIN LATERAL
                (SELECT unit_price_vnd,other_fee_vnd FROM sokhach.trip_price_rev
                 WHERE trip_id=t.id ORDER BY id DESC LIMIT 1) p ON true
              WHERE t.customer_id=k.id AND t.debt_month=m AND NOT t.deleted AND t.status='confirmed'),0)
          +coalesce((SELECT sum(a.amount_vnd) FROM sokhach.v_adjustment_current a
              LEFT JOIN sokhach.legacy_row lr ON lr.id=a.legacy_row_id
              WHERE a.customer_id=k.id AND a.debt_month=m AND lr.kind IS DISTINCT FROM 'receipt'),0)),0) AS charges,
        coalesce(sum(coalesce(s.source_receipt_vnd,0)
          +coalesce((SELECT sum(r.amount_vnd) FROM sokhach.receipt r
              WHERE r.customer_id=k.id AND r.voided_on IS NULL AND date_trunc('month',r.date)::date=m),0)
          -coalesce((SELECT sum(o.amount_vnd) FROM sokhach.v_offset_outgoing o
              WHERE o.customer_id=k.id AND o.debt_month=m),0)
          -coalesce((SELECT sum(a.amount_vnd) FROM sokhach.v_adjustment_current a
              JOIN sokhach.legacy_row lr ON lr.id=a.legacy_row_id AND lr.kind='receipt'
              WHERE a.customer_id=k.id AND a.debt_month=m),0)),0) AS received
        FROM keyed k LEFT JOIN LATERAL (SELECT mc.source_charge_vnd,mc.source_receipt_vnd
            FROM sokhach.cutover_month_check mc
           WHERE mc.customer_id=k.id AND mc.cutover_id=k.cutover_id AND mc.debt_month=m
             AND mc.source_charge_vnd IS NOT NULL AND mc.source_receipt_vnd IS NOT NULL) s ON true)
  SELECT jsonb_build_object('as_of',d::text,'month',m::text,
    'rule',jsonb_build_object('due_after_months',1,'long_overdue_months',3,'no_pay_days',60,'no_trip_days',90,'active_trip_days',30),
    'receivable_vnd',(SELECT coalesce(sum(total),0)::text FROM ranked),
    'due_tiers',(SELECT jsonb_build_array(
        jsonb_build_object('tier','not_due','receivable_vnd',coalesce(sum(t0),0)::text),
        jsonb_build_object('tier','due_this_month','receivable_vnd',coalesce(sum(t1),0)::text),
        jsonb_build_object('tier','late_1_2','receivable_vnd',coalesce(sum(t2),0)::text),
        jsonb_build_object('tier','late_3_6','receivable_vnd',coalesce(sum(t3),0)::text),
        jsonb_build_object('tier','late_over_6','receivable_vnd',coalesce(sum(t4),0)::text)) FROM ranked),
    'summary',(SELECT jsonb_build_object('overdue_vnd',coalesce(sum(overdue),0)::text,
        'long_overdue_vnd',coalesce(sum(long_overdue),0)::text,
        'overdue_customers',count(*) FILTER (WHERE overdue>0),'high_customers',count(*) FILTER (WHERE risk='high'),
        'high_overdue_vnd',coalesce(sum(overdue) FILTER (WHERE risk='high'),0)::text) FROM ranked),
    'this_month',(SELECT jsonb_build_object('month',m::text,'charges_vnd',charges::text,'received_vnd',received::text) FROM flow),
    'customers',coalesce((SELECT jsonb_agg(jsonb_build_object('customer_id',id,'name',name,'commodity',commodity,
        'transport_mode',transport_mode,'outstanding_vnd',total::text,
        'tiers_vnd',jsonb_build_array(t0::text,t1::text,t2::text,t3::text,t4::text),
        'overdue_vnd',overdue::text,'long_overdue_vnd',long_overdue::text,'oldest_open_month',oldest::text,
        'last_receipt_date',pay_day::text,'last_receipt_exact',pay_exact,'pay_days',pay_days,
        'last_trip_date',trip_day::text,'last_trip_exact',trip_exact,'trip_days',trip_days,
        'risk',risk,'months',months) ORDER BY overdue DESC,total DESC,name COLLATE "C",id) FROM ranked),'[]'::jsonb)));
END $$;

REVOKE ALL ON FUNCTION sokhach._legacy_date(text) FROM PUBLIC, sokhach_app, sokhach_reader;
REVOKE ALL ON FUNCTION sokhach.get_dashboard_debt() FROM PUBLIC, sokhach_app, sokhach_reader;
GRANT EXECUTE ON FUNCTION sokhach.get_dashboard_debt() TO sokhach_app, sokhach_reader;
COMMIT;
