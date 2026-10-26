BEGIN;
SET LOCAL ROLE sokhach_owner;
CREATE OR REPLACE FUNCTION sokhach.get_receivables_detail(p_customer bigint, p_month date) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, sokhach, pg_temp AS $$
DECLARE v_active boolean; v_outstanding bigint; v_charges bigint; v_received bigint;
        v_opening boolean; v_trips jsonb;
BEGIN
    PERFORM sokhach._actor();
    IF p_month IS NULL OR date_trunc('month', p_month)::date <> p_month THEN
        RAISE EXCEPTION 'INVALID_MONTH';
    END IF;
    SELECT EXISTS (SELECT 1 FROM sokhach.cutover_customer cc JOIN sokhach.cutover c ON c.id=cc.cutover_id
        WHERE cc.customer_id=p_customer AND cc.status='active' AND c.status='active') INTO v_active;
    IF NOT v_active THEN RAISE EXCEPTION 'CUSTOMER_NOT_FOUND'; END IF;
    SELECT coalesce(sum(v.outstanding_vnd),0)::bigint INTO v_outstanding
      FROM sokhach.v_outstanding_month v WHERE v.customer_id=p_customer AND v.debt_month=p_month;
    SELECT coalesce(sum(CASE WHEN p.unit_price_vnd IS NOT NULL THEN p.unit_price_vnd+coalesce(p.other_fee_vnd,0)
        WHEN t.container IS NULL OR t.container='' THEN p.other_fee_vnd END),0)::bigint
      + coalesce((SELECT sum(a.amount_vnd) FROM sokhach.v_adjustment_current a
          WHERE a.customer_id=p_customer AND a.debt_month=p_month),0)
      + coalesce((SELECT sum(o.amount_vnd) FROM sokhach.opening_balance o
          JOIN sokhach.cutover_customer cc ON (cc.customer_id,cc.cutover_id)=(o.customer_id,o.cutover_id)
          JOIN sokhach.cutover c ON c.id=cc.cutover_id
          WHERE o.customer_id=p_customer AND o.debt_month=p_month AND cc.status='active' AND c.status='active'),0)
      INTO v_charges
      FROM sokhach.v_trip_current t LEFT JOIN LATERAL
        (SELECT unit_price_vnd,other_fee_vnd FROM sokhach.trip_price_rev WHERE trip_id=t.id ORDER BY id DESC LIMIT 1) p ON true
      WHERE t.customer_id=p_customer AND t.debt_month=p_month AND NOT t.deleted AND t.status='confirmed';
    SELECT coalesce(sum(l.amount_vnd),0) - coalesce((SELECT sum(o.amount_vnd) FROM sokhach.v_offset_outgoing o
        WHERE o.customer_id=p_customer AND o.debt_month=p_month),0) INTO v_received
      FROM sokhach.v_receipt_line_active l WHERE l.customer_id=p_customer AND l.debt_month=p_month;
    SELECT EXISTS (SELECT 1 FROM sokhach.opening_balance o JOIN sokhach.cutover_customer cc
        ON (cc.customer_id,cc.cutover_id)=(o.customer_id,o.cutover_id) JOIN sokhach.cutover c ON c.id=cc.cutover_id
        WHERE o.customer_id=p_customer AND o.debt_month=p_month AND cc.status='active' AND c.status='active') INTO v_opening;
    SELECT coalesce(jsonb_agg(jsonb_build_object('id',t.id,'month',t.debt_month,'event_date',t.event_date,
        'container',t.container,'carrier',t.carrier,'status',t.status,'unit_price_vnd',p.unit_price_vnd::text,
         'other_fee_vnd',p.other_fee_vnd::text,'amount_vnd',CASE WHEN t.status<>'confirmed' THEN NULL
          WHEN p.unit_price_vnd IS NOT NULL THEN (p.unit_price_vnd+coalesce(p.other_fee_vnd,0))::text
          WHEN t.container IS NULL OR t.container='' THEN p.other_fee_vnd::text END) ORDER BY t.id),'[]'::jsonb) INTO v_trips
      FROM sokhach.v_trip_current t LEFT JOIN LATERAL
        (SELECT unit_price_vnd,other_fee_vnd FROM sokhach.trip_price_rev WHERE trip_id=t.id ORDER BY id DESC LIMIT 1) p ON true
      WHERE t.customer_id=p_customer AND t.debt_month=p_month AND NOT t.deleted;
    RETURN jsonb_build_object('status','active','customer_id',p_customer,'month',p_month::text,
        'outstanding_vnd',v_outstanding::text,'charges_vnd',v_charges::text,'received_vnd',v_received::text,
        'opening',v_opening,'trips',v_trips);
END $$;
GRANT EXECUTE ON FUNCTION sokhach.get_receivables_detail(bigint,date) TO sokhach_app, sokhach_reader;
COMMIT;
