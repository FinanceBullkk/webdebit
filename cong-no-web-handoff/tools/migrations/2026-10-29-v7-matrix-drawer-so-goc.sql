-- Ngăn kéo Công nợ theo tháng đọc số tháng, chuyến web và dòng chuyến sổ gốc từ get_ledger.
-- Chỉ thay get_receivables_detail; không đổi dữ liệu, chạy lại được. Chạy sau 2026-10-29-v7-phu-phi-b-p2.sql.
BEGIN;
SET LOCAL ROLE sokhach_owner;
CREATE OR REPLACE FUNCTION sokhach.get_receivables_detail(p_customer bigint, p_month date) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, sokhach, pg_temp AS $$
-- Ngăn kéo ma trận (29/10/2026): số tháng lấy đúng dòng Tổng tháng của get_ledger (DA-THU-01: tháng
-- sổ gốc dùng phát sinh/đã thu Sheet, đã thu theo ngày thu), danh sách gồm chuyến web và dòng chuyến
-- sổ gốc. outstanding_vnd là ô ma trận (nợ còn lại sau phân bổ nợ cũ trước); allocated_vnd là thu đã
-- phân bổ vào kỳ, để giải thích vì sao phát sinh − đã thu có thể khác còn lại.
DECLARE v_active boolean; v_ledger jsonb; v_row jsonb; v_allocated bigint; v_opening boolean;
        v_month text := p_month::text;
BEGIN
    PERFORM sokhach._actor();
    IF p_month IS NULL OR date_trunc('month', p_month)::date <> p_month THEN
        RAISE EXCEPTION 'INVALID_MONTH';
    END IF;
    SELECT EXISTS (SELECT 1 FROM sokhach.cutover_customer cc JOIN sokhach.cutover c ON c.id=cc.cutover_id
        WHERE cc.customer_id=p_customer AND cc.status='active' AND c.status='active') INTO v_active;
    IF NOT v_active THEN RAISE EXCEPTION 'CUSTOMER_NOT_FOUND'; END IF;
    v_ledger := sokhach.get_ledger(p_customer);
    SELECT m INTO v_row FROM jsonb_array_elements(v_ledger->'months') m WHERE m->>'month'=v_month;
    SELECT coalesce(sum(l.amount_vnd),0) - coalesce((SELECT sum(o.amount_vnd) FROM sokhach.v_offset_outgoing o
        WHERE o.customer_id=p_customer AND o.debt_month=p_month),0) INTO v_allocated
      FROM sokhach.v_receipt_line_active l WHERE l.customer_id=p_customer AND l.debt_month=p_month;
    SELECT EXISTS (SELECT 1 FROM jsonb_array_elements(v_ledger->'opening') o WHERE o->>'month'=v_month) INTO v_opening;
    RETURN jsonb_build_object('status','active','customer_id',p_customer,'month',v_month,
        'outstanding_vnd',coalesce(v_row->>'outstanding_vnd','0'),
        'charges_vnd',coalesce(v_row->>'charges_vnd','0'),'received_vnd',coalesce(v_row->>'received_vnd','0'),
        'allocated_vnd',v_allocated::text,'opening',v_opening,
        'trips',(SELECT coalesce(jsonb_agg(jsonb_build_object('id',t->'id','month',t->'month',
            'event_date',t->'event_date','container',t->'container','carrier',t->'carrier','status',t->'status',
            'unit_price_vnd',t->'unit_price_vnd','other_fee_vnd',t->'other_fee_vnd','amount_vnd',t->'amount_vnd',
            'historical',false) ORDER BY (t->>'id')::bigint),'[]'::jsonb)
          FROM jsonb_array_elements(v_ledger->'trips') t WHERE t->>'month'=v_month)
        || (SELECT coalesce(jsonb_agg(jsonb_build_object('id',l->'id','month',l->'month',
            'event_date',l->'current'->'event_date','container',l->'current'->'container',
            'carrier',l->'current'->'carrier','status','confirmed',
            'unit_price_vnd',l->'current'->'unit_price_vnd','other_fee_vnd',l->'current'->'other_fee_vnd',
            'amount_vnd',l->'current'->'counted_vnd','historical',true) ORDER BY (l->>'id')::bigint),'[]'::jsonb)
          FROM jsonb_array_elements(v_ledger->'legacy_rows') l WHERE l->>'kind'='trip' AND l->>'month'=v_month));
END $$;
COMMIT;
