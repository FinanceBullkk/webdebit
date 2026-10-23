BEGIN;
SET LOCAL ROLE sokhach_owner;
CREATE OR REPLACE FUNCTION sokhach.get_dashboard() RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, sokhach, pg_temp AS $$
DECLARE d date := (now() AT TIME ZONE 'Asia/Ho_Chi_Minh')::date; m date := date_trunc('month', d)::date;
BEGIN
  PERFORM sokhach._actor();
  RETURN (WITH a AS (SELECT c.id,c.name,c.commodity_id,c.transport_mode,coalesce(sum(v.outstanding_vnd),0)::bigint total
    FROM sokhach.customer c JOIN sokhach.cutover_customer cc ON cc.customer_id=c.id AND cc.status='active'
    JOIN sokhach.cutover x ON x.id=cc.cutover_id AND x.status='active' LEFT JOIN sokhach.v_outstanding_month v ON v.customer_id=c.id
    WHERE NOT c.archived GROUP BY c.id,c.name,c.commodity_id,c.transport_mode),
  p AS (SELECT t.customer_id,count(*)::int n FROM sokhach.v_trip_current t JOIN a ON a.id=t.customer_id
    LEFT JOIN LATERAL (SELECT unit_price_vnd,other_fee_vnd FROM sokhach.trip_price_rev z WHERE z.trip_id=t.id ORDER BY z.id DESC LIMIT 1) z ON true
    WHERE NOT t.deleted AND t.status='confirmed' AND z.unit_price_vnd IS NULL AND NOT ((t.container IS NULL OR t.container='') AND z.other_fee_vnd IS NOT NULL) GROUP BY t.customer_id),
  r AS (SELECT customer_id,count(*)::int n FROM sokhach.v_trip_current t JOIN a ON a.id=t.customer_id WHERE NOT t.deleted AND t.status='pending_review' GROUP BY customer_id),
  e AS (SELECT actor,coalesce(sum(jsonb_array_length(e."after"->'trips')) FILTER (WHERE kind='paste'),0)::int trips,count(*) FILTER (WHERE kind='receipt')::int receipts,
    coalesce(sum((e."after"->>'amount_vnd')::bigint) FILTER (WHERE kind='receipt'),0)::bigint received,
    count(*) FILTER (WHERE kind='void' AND EXISTS (SELECT 1 FROM sokhach.receipt z WHERE z.voided_by_event=e.id))::int voids
    FROM sokhach.event e WHERE (e.at AT TIME ZONE 'Asia/Ho_Chi_Minh')::date=d
      AND (kind IN ('paste','receipt') OR (kind='void' AND EXISTS (SELECT 1 FROM sokhach.receipt z WHERE z.voided_by_event=e.id))) GROUP BY actor),
  t AS (SELECT coalesce(sum(total) FILTER (WHERE total>0),0)::bigint recv,count(*) FILTER (WHERE total>0)::int recv_n,
    coalesce(sum(total) FILTER (WHERE total<0),0)::bigint cred,count(*) FILTER (WHERE total<0)::int cred_n FROM a),
  aging AS (SELECT b.bucket,b.ord,coalesce(sum(v.outstanding_vnd),0)::bigint amount FROM (VALUES ('current',0),('1-2',1),('3-6',2),('over-6',3)) b(bucket,ord)
    LEFT JOIN sokhach.v_outstanding_month v ON v.customer_id IN (SELECT id FROM a WHERE total>0)
    AND CASE WHEN ((extract(year FROM m)-extract(year FROM v.debt_month))*12+extract(month FROM m)-extract(month FROM v.debt_month))<=0 THEN 0 WHEN ((extract(year FROM m)-extract(year FROM v.debt_month))*12+extract(month FROM m)-extract(month FROM v.debt_month))<=2 THEN 1 WHEN ((extract(year FROM m)-extract(year FROM v.debt_month))*12+extract(month FROM m)-extract(month FROM v.debt_month))<=6 THEN 2 ELSE 3 END=b.ord GROUP BY b.bucket,b.ord)
  SELECT jsonb_build_object('as_of',d::text,'receivable',jsonb_build_object('total_vnd',t.recv::text,'customers',t.recv_n),'credit',jsonb_build_object('total_vnd',t.cred::text,'customers',t.cred_n),
    'by_commodity',coalesce((SELECT jsonb_agg(jsonb_build_object('commodity',q.commodity,'transport_mode',q.transport_mode,'customers',q.n,'receivable_vnd',q.amount::text) ORDER BY q.commodity IS NULL,q.commodity COLLATE "C",q.transport_mode NULLS LAST) FROM (SELECT c.commodity_id,m.name commodity,c.transport_mode,count(*)::int n,sum(c.total)::bigint amount FROM a c LEFT JOIN sokhach.commodity m ON m.id=c.commodity_id WHERE c.total>0 GROUP BY c.commodity_id,m.name,c.transport_mode) q),'[]'::jsonb),
    'aging',(SELECT jsonb_agg(jsonb_build_object('bucket',bucket,'receivable_vnd',amount::text) ORDER BY ord) FROM aging),
    'top_debtors',coalesce((SELECT jsonb_agg(jsonb_build_object('customer_id',q.id,'name',q.name,'commodity',q.commodity,'transport_mode',q.transport_mode,'outstanding_vnd',q.total::text,'oldest_open_month',q.oldest::text) ORDER BY q.total DESC,q.name COLLATE "C",q.id) FROM (SELECT a.*,m.name commodity,min(v.debt_month) FILTER (WHERE v.outstanding_vnd>0) oldest FROM a LEFT JOIN sokhach.commodity m ON m.id=a.commodity_id LEFT JOIN sokhach.v_outstanding_month v ON v.customer_id=a.id WHERE a.total>0 GROUP BY a.id,a.name,a.commodity_id,a.transport_mode,a.total,m.name ORDER BY a.total DESC,a.name COLLATE "C",a.id LIMIT 10) q),'[]'::jsonb),
    'todo',jsonb_build_object('missing_price',coalesce((SELECT jsonb_agg(jsonb_build_object('customer_id',a.id,'name',a.name,'count',p.n) ORDER BY a.name COLLATE "C",a.id) FROM p JOIN a ON a.id=p.customer_id),'[]'::jsonb),'pending_review',coalesce((SELECT jsonb_agg(jsonb_build_object('customer_id',a.id,'name',a.name,'count',r.n) ORDER BY a.name COLLATE "C",a.id) FROM r JOIN a ON a.id=r.customer_id),'[]'::jsonb),'no_baseline',coalesce((SELECT jsonb_agg(jsonb_build_object('customer_id',c.id,'name',c.name) ORDER BY c.name COLLATE "C",c.id) FROM sokhach.customer c WHERE NOT c.archived AND NOT EXISTS (SELECT 1 FROM a WHERE a.id=c.id)),'[]'::jsonb),'credit',coalesce((SELECT jsonb_agg(jsonb_build_object('customer_id',id,'name',name,'credit_vnd',total::text) ORDER BY name COLLATE "C",id) FROM a WHERE total<0),'[]'::jsonb)),
    'today',jsonb_build_object('trips',coalesce((SELECT sum(trips) FROM e),0),'receipts',coalesce((SELECT sum(receipts) FROM e),0),'received_vnd',coalesce((SELECT sum(received) FROM e),0)::text,'voids',coalesce((SELECT sum(voids) FROM e),0),'by_actor',coalesce((SELECT jsonb_agg(jsonb_build_object('actor',actor,'trips',trips,'receipts',receipts,'received_vnd',received::text,'voids',voids) ORDER BY actor COLLATE "C") FROM e),'[]'::jsonb))) FROM t);
END $$;

REVOKE ALL ON FUNCTION sokhach.get_dashboard() FROM PUBLIC, sokhach_app, sokhach_reader;
GRANT EXECUTE ON FUNCTION sokhach.get_dashboard() TO sokhach_app, sokhach_reader;
COMMIT;
