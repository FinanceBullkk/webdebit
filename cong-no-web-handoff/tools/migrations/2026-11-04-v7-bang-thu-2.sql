-- BANG-THU-01 (4/11/2026), lần 2 sau khi xem bản thật trên hao: bỏ dòng Sheet số tiền 0, Theo khách xếp theo cột Đã trả, ghi chú không hiện số
-- serial ngày. Chỉ thay hàm đọc get_receipt_book: không đổi bảng, view, hàm ghi, phân bổ hay dữ liệu; giữ quyền EXECUTE. Chạy lại được.
-- Chạy sau 2026-11-04-v7-bang-thu.sql.
BEGIN;
SET LOCAL ROLE sokhach_owner;
CREATE OR REPLACE FUNCTION sokhach.get_receipt_book(p_month date) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, sokhach, pg_temp AS $$
-- BANG-THU-01. Tháng tính theo ngày tiền về, khác "Đã thu" của sổ ở tháng có dòng Sheet (DA-THU-01 giữ nguyên): Sheet ghi khoản thu
-- ở khối tháng nợ. Gồm phiếu web chưa hủy và dòng thu sổ gốc chưa xóa; cấn trừ không phải tiền mới vào nên liệt kê riêng.
-- Dòng Sheet số tiền 0 là ô công thức trống, không liệt kê. Không rõ ngày (date NULL, nằm ở tháng của khối, không cộng vào tổng tháng): Sheet không đọc được ngày; ngày sau lúc nạp sổ hoặc sau
-- hôm nay; ngày trước tháng của khối hơn 12 tháng; phiếu đặt ngày cuối tháng khối vì Sheet không ghi ngày (MAY-DOI-SOAT-01).
-- Mọi tháng cộng lại, mọi sổ cộng lại bằng đúng tổng received_vnd của get_ledger: dòng chỉ đổi tháng, không thêm bớt tiền.
DECLARE d date := (now() AT TIME ZONE 'Asia/Ho_Chi_Minh')::date; v_this date := date_trunc('month', d)::date;
        v_month date := coalesce(p_month, v_this);
BEGIN
  PERFORM sokhach._actor();
  IF date_trunc('month', v_month)::date <> v_month THEN RAISE EXCEPTION 'INVALID_MONTH'; END IF;
  RETURN (WITH act AS (
      SELECT c.id,c.name,cc.cutover_id,(x.frozen_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::date AS frozen FROM sokhach.customer c
        JOIN sokhach.cutover_customer cc ON cc.customer_id=c.id AND cc.status='active'
        JOIN sokhach.cutover x ON x.id=cc.cutover_id AND x.status='active'
       WHERE NOT c.archived),
    sheet AS (
      SELECT l.id,l.customer_id,a.name,l.debt_month,l.source_total_vnd AS amount,q.dt,
        -- Ghi chú: chữ người gõ; ô chỉ có ngày mà ngày đã nhận thì không lặp lại, ngày không nhận thì giữ để người đọc thấy đã gõ gì.
        nullif(concat_ws(' · ',
          CASE WHEN t.raw ~ '^[0-9]{5}(\.0+)?$' THEN CASE WHEN q.dt IS NULL THEN to_char(p.dt,'DD/MM/YYYY') END
               WHEN q.dt IS NOT NULL AND t.raw ~ '^([0-9]{1,2}[/.-][0-9]{1,2}[/.-][0-9]{4}|[0-9]{4}-[0-9]{1,2}-[0-9]{1,2})$' THEN NULL
               ELSE nullif(t.raw,'') END,
          CASE WHEN t.note=t.raw OR t.note ~ '^([0-9]{1,2}[/.-][0-9]{1,2}[/.-][0-9]{4}|[0-9]{4}-[0-9]{1,2}-[0-9]{1,2}( [0-9:]+)?)$' THEN NULL
               ELSE nullif(t.note,'') END),'') AS note
        FROM sokhach.legacy_row l JOIN act a ON (a.id,a.cutover_id)=(l.customer_id,l.cutover_id)
        CROSS JOIN LATERAL (SELECT btrim(coalesce(l.display->>'raw_date','')) AS raw,btrim(coalesce(l.display->>'note','')) AS note) t
        CROSS JOIN LATERAL (SELECT coalesce(sokhach._legacy_date(l.display->>'date'),sokhach._legacy_pay_date(t.raw)) AS dt) p
        CROSS JOIN LATERAL (SELECT CASE WHEN p.dt BETWEEN (l.debt_month-interval '12 months')::date AND least(a.frozen,d) THEN p.dt END AS dt) q
        LEFT JOIN LATERAL (SELECT r.deleted FROM sokhach.legacy_trip_rev r WHERE r.legacy_row_id=l.id ORDER BY r.id DESC LIMIT 1) rev ON true
       WHERE l.kind='receipt' AND l.source_total_vnd IS NOT NULL AND l.source_total_vnd<>0 AND NOT coalesce(rev.deleted,false)),
    web AS (
      SELECT r.id,r.pid,r.customer_id,a.name,date_trunc('month',r.date)::date AS book_month,r.amount_vnd AS amount,r.method,
        CASE WHEN r.reference ~ '( \(ngày tượng trưng\)| · ngày theo cuối tháng khối Sheet)$' THEN NULL ELSE r.date END AS dt,
        -- Tiền tố và đuôi kỹ thuật (reference, review_reference, NO_DATE_NOTE, ghi tay "ngày tượng trưng") không lên màn.
        regexp_replace(regexp_replace(coalesce(r.reference,''),'^Sheet( #[^:]*)?(: ?|$)',''),'( \(ngày tượng trưng\)| · ngày theo cuối tháng khối Sheet)$','') AS note
        FROM sokhach.receipt r JOIN act a ON a.id=r.customer_id
       WHERE r.voided_on IS NULL AND NOT EXISTS (SELECT 1 FROM sokhach.offset_pair o WHERE o.target_receipt_id=r.id)),
    items AS (
      SELECT 'sheet'::text AS source,s.id,NULL::text AS pid,s.customer_id,s.name,s.debt_month AS book_month,s.amount,s.dt,NULL::text AS method,s.note FROM sheet s
      UNION ALL
      SELECT 'web',w.id,w.pid,w.customer_id,w.name,w.book_month,w.amount,w.dt,w.method,
        CASE WHEN w.note ~ '^([0-9]{1,2}[/.-][0-9]{1,2}[/.-][0-9]{4}|[0-9]{5}(\.0+)?)$' AND sokhach._legacy_pay_date(w.note)=w.dt THEN NULL
             WHEN w.note ~ '^[0-9]{5}(\.0+)?$' THEN to_char(sokhach._legacy_pay_date(w.note),'DD/MM/YYYY') ELSE nullif(w.note,'') END
        FROM web w),
    placed AS (SELECT i.*,date_trunc('month',coalesce(i.dt,i.book_month))::date AS month FROM items i),
    idx AS (
      SELECT p.month,coalesce(sum(p.amount) FILTER (WHERE p.dt IS NOT NULL),0) AS total,count(*) FILTER (WHERE p.dt IS NOT NULL) AS n,
             coalesce(sum(p.amount) FILTER (WHERE p.dt IS NULL),0) AS undated,count(*) FILTER (WHERE p.dt IS NULL) AS undated_n
        FROM placed p GROUP BY p.month
      UNION ALL SELECT v_this,0,0,0,0 WHERE NOT EXISTS (SELECT 1 FROM placed p WHERE p.month=v_this)),
    cur AS (
      SELECT p.*,jsonb_build_object('source',p.source,'id',p.id,'pid',p.pid,'customer_id',p.customer_id,'name',p.name,'date',p.dt,
          'book_month',p.book_month,'amount_vnd',p.amount::text,'method',p.method,'note',p.note,
          'allocations',CASE WHEN p.source='web' THEN (SELECT coalesce(jsonb_agg(jsonb_build_object('month',x.debt_month,'kind',x.kind,'amount_vnd',x.amount::text)
              ORDER BY x.debt_month,x.kind),'[]'::jsonb) FROM (SELECT l.debt_month,l.kind,sum(l.amount_vnd) AS amount
              FROM sokhach.v_receipt_line_active l WHERE l.receipt_id=p.id GROUP BY 1,2) x) ELSE '[]'::jsonb END) AS js
        FROM placed p WHERE p.month=v_month)
    SELECT jsonb_build_object('month',v_month,'as_of',d,'today_month',v_this,
      'months',(SELECT jsonb_agg(jsonb_build_object('month',m.month,'total_vnd',m.total::text,'count',m.n,
          'undated_vnd',m.undated::text,'undated_count',m.undated_n) ORDER BY m.month DESC) FROM idx m),
      'summary',(SELECT jsonb_build_object('total_vnd',coalesce(sum(c.amount) FILTER (WHERE c.dt IS NOT NULL),0)::text,
          'count',count(*) FILTER (WHERE c.dt IS NOT NULL),'customers',count(DISTINCT c.customer_id) FILTER (WHERE c.dt IS NOT NULL),
          'undated_vnd',coalesce(sum(c.amount) FILTER (WHERE c.dt IS NULL),0)::text,'undated_count',count(*) FILTER (WHERE c.dt IS NULL),
          'today_vnd',coalesce(sum(c.amount) FILTER (WHERE c.dt=d),0)::text,'today_count',count(*) FILTER (WHERE c.dt=d),
          'has_sheet',coalesce(bool_or(c.source='sheet'),false)) FROM cur c),
      'days',(SELECT coalesce(jsonb_agg(jsonb_build_object('date',g.dt,'total_vnd',g.total::text,'count',g.n,'rows',g.rows) ORDER BY g.dt DESC),'[]'::jsonb)
        FROM (SELECT c.dt,sum(c.amount) AS total,count(*) AS n,jsonb_agg(c.js ORDER BY c.amount DESC,c.name COLLATE "C",c.source,c.id) AS rows
                FROM cur c WHERE c.dt IS NOT NULL GROUP BY c.dt) g),
      'undated',(SELECT coalesce(jsonb_agg(c.js ORDER BY c.amount DESC,c.name COLLATE "C",c.source,c.id),'[]'::jsonb) FROM cur c WHERE c.dt IS NULL),
      'customers',(SELECT coalesce(jsonb_agg(jsonb_build_object('customer_id',g.customer_id,'name',g.name,'total_vnd',g.total::text,'count',g.n,
          'undated_vnd',g.undated::text,'undated_count',g.undated_n,'last_date',g.last_date,'book_month',g.book_month)
          ORDER BY g.total DESC,g.undated DESC,g.name COLLATE "C",g.customer_id),'[]'::jsonb)
        FROM (SELECT c.customer_id,c.name,coalesce(sum(c.amount) FILTER (WHERE c.dt IS NOT NULL),0) AS total,count(*) FILTER (WHERE c.dt IS NOT NULL) AS n,
                     coalesce(sum(c.amount) FILTER (WHERE c.dt IS NULL),0) AS undated,count(*) FILTER (WHERE c.dt IS NULL) AS undated_n,
                     max(c.dt) AS last_date,max(c.book_month) AS book_month
                FROM cur c GROUP BY c.customer_id,c.name) g),
      'offsets',(SELECT coalesce(jsonb_agg(jsonb_build_object('id',o.id,'date',o.date,'amount_vnd',o.amount_vnd::text,
          'source_customer_id',o.source_customer_id,'source_name',s.name,'target_customer_id',o.target_customer_id,'target_name',t.name)
          ORDER BY o.date DESC,o.id DESC),'[]'::jsonb)
        FROM sokhach.offset_pair o JOIN sokhach.customer s ON s.id=o.source_customer_id JOIN sokhach.customer t ON t.id=o.target_customer_id
       WHERE o.voided_by_event IS NULL AND date_trunc('month',o.date)::date=v_month),
      'voided',(SELECT coalesce(jsonb_agg(jsonb_build_object('pid',r.pid,'customer_id',r.customer_id,'name',a.name,'date',r.date,
          'amount_vnd',r.amount_vnd::text,'voided_on',r.voided_on,'void_reason',r.void_reason) ORDER BY r.date DESC,r.id DESC),'[]'::jsonb)
        FROM sokhach.receipt r JOIN act a ON a.id=r.customer_id
       WHERE r.voided_on IS NOT NULL AND date_trunc('month',r.date)::date=v_month
         AND NOT EXISTS (SELECT 1 FROM sokhach.offset_pair o WHERE o.target_receipt_id=r.id))));
END $$;
COMMIT;
