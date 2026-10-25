BEGIN;
SET LOCAL ROLE sokhach_owner;
CREATE OR REPLACE FUNCTION sokhach.get_receivables_matrix(p_year int) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, sokhach, pg_temp AS $$
DECLARE d date := (now() AT TIME ZONE 'Asia/Ho_Chi_Minh')::date;
BEGIN
  IF p_year IS NULL OR p_year < 2000 OR p_year > extract(year FROM d)::int + 1 THEN
    RAISE EXCEPTION 'INVALID_YEAR'; END IF;
  PERFORM sokhach._actor();
  RETURN (WITH base AS (
    SELECT c.id, c.name, c.commodity_id, c.transport_mode,
           coalesce(sum(v.outstanding_vnd),0)::bigint AS total_all,
           coalesce(sum(v.outstanding_vnd) FILTER (WHERE extract(year FROM v.debt_month)=p_year),0)::bigint AS total_year,
           min(v.debt_month) FILTER (WHERE v.outstanding_vnd>0) AS oldest
      FROM sokhach.customer c
      JOIN sokhach.cutover_customer cc ON cc.customer_id=c.id AND cc.status='active'
      JOIN sokhach.cutover x ON x.id=cc.cutover_id AND x.status='active'
      LEFT JOIN sokhach.v_outstanding_month v ON v.customer_id=c.id
     WHERE NOT c.archived
     GROUP BY c.id, c.name, c.commodity_id, c.transport_mode
    HAVING coalesce(bool_or(v.outstanding_vnd <> 0), false)),
  cells AS (
    SELECT b.id, g.mm, coalesce(sum(v.outstanding_vnd),0)::bigint AS val
      FROM base b CROSS JOIN generate_series(1,12) AS g(mm)
      LEFT JOIN sokhach.v_outstanding_month v
        ON v.customer_id=b.id AND extract(year FROM v.debt_month)=p_year AND extract(month FROM v.debt_month)=g.mm
     GROUP BY b.id, g.mm),
  cust AS (
    SELECT jsonb_build_object('customer_id',b.id,'name',b.name,'commodity',m.name,
      'transport_mode',b.transport_mode,
      'months',(SELECT jsonb_object_agg(mm::text, val::text) FROM cells WHERE cells.id=b.id),
      'total_year_vnd',b.total_year::text,'total_all_vnd',b.total_all::text,
      'oldest_open_month',b.oldest::text) o
      FROM base b LEFT JOIN sokhach.commodity m ON m.id=b.commodity_id
     ORDER BY b.total_all DESC, b.name COLLATE "C", b.id)
  SELECT jsonb_build_object('as_of',d::text,'year',p_year,
    'years_available',(SELECT coalesce(jsonb_agg(DISTINCT y ORDER BY y),'[]'::jsonb) FROM
      (SELECT extract(year FROM debt_month)::int y FROM sokhach.v_outstanding_month
       UNION SELECT extract(year FROM d)::int) yy),
    'customers',(SELECT coalesce(jsonb_agg(o),'[]'::jsonb) FROM cust),
    'grand_total_year_vnd',(SELECT coalesce(sum(total_year),0)::bigint::text FROM base),
    'grand_total_all_vnd',(SELECT coalesce(sum(total_all),0)::bigint::text FROM base)));
END $$;
REVOKE ALL ON FUNCTION sokhach.get_receivables_matrix(int) FROM PUBLIC, sokhach_app, sokhach_reader;
GRANT EXECUTE ON FUNCTION sokhach.get_receivables_matrix(int) TO sokhach_app, sokhach_reader;
COMMIT;
