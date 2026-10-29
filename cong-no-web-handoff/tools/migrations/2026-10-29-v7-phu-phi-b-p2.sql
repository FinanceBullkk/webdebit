-- PR-B P2 (review 29/10): FEE_LINE_NOT_FOUND + cờ counted_differs ở get_ledger. Chạy sau PR-B; không đổi dữ liệu.
BEGIN;
SET LOCAL ROLE sokhach_owner;
CREATE OR REPLACE FUNCTION sokhach._change_trip_fees(p_customer bigint,p_version bigint,p_key text,
 p_command text,p_targets jsonb,p_type bigint,p_amount bigint,p_note text,p_line bigint) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,sokhach,pg_temp AS $$
DECLARE v_payload jsonb:=jsonb_build_object('command',p_command,'targets',p_targets,'fee_type_id',p_type,
 'amount_vnd',p_amount::text,'note',p_note,'fee_line_id',p_line);
 v_retry jsonb; v_before jsonb:='[]'; v_after jsonb:='[]'; v_target jsonb; v_state jsonb;
 v_old sokhach.trip_fee_line%ROWTYPE; v_type sokhach.fee_type%ROWTYPE;
 v_event bigint; v_total bigint; v_changes jsonb;
BEGIN
 BEGIN v_retry:=sokhach._begin_command(p_customer,p_version,p_key,v_payload);
 EXCEPTION WHEN raise_exception THEN
   IF SQLERRM='STALE_LEDGER' THEN RAISE EXCEPTION 'VERSION_CONFLICT'; ELSE RAISE; END IF;
 END;
 IF v_retry IS NOT NULL THEN RETURN v_retry; END IF;
 PERFORM sokhach._baseline(p_customer);
 IF p_command NOT IN ('add_trip_fees','set_trip_fee_type','replace_trip_fee','void_trip_fee')
   OR p_command IS NULL THEN RAISE EXCEPTION 'INVALID_COMMAND'; END IF;
 IF p_command IN ('replace_trip_fee','void_trip_fee') THEN
   SELECT * INTO v_old FROM sokhach.trip_fee_line WHERE id=p_line AND customer_id=p_customer
     AND voided_by_event IS NULL FOR UPDATE;
   IF NOT FOUND THEN RAISE EXCEPTION 'FEE_LINE_NOT_FOUND'; END IF;
   p_targets:=jsonb_build_array(CASE WHEN v_old.trip_id IS NOT NULL
     THEN jsonb_build_object('trip_id',v_old.trip_id) ELSE jsonb_build_object('legacy_row_id',v_old.legacy_row_id) END);
 END IF;
 IF jsonb_typeof(p_targets) IS DISTINCT FROM 'array' THEN RAISE EXCEPTION 'INVALID_TRIPS'; END IF;
 IF jsonb_array_length(p_targets)<1 OR
   (p_command<>'add_trip_fees' AND jsonb_array_length(p_targets)<>1) OR
   (SELECT count(*)<>count(DISTINCT x) FROM jsonb_array_elements(p_targets) x)
 THEN RAISE EXCEPTION 'INVALID_TRIPS'; END IF;
 IF p_command<>'void_trip_fee' THEN
   SELECT * INTO v_type FROM sokhach.fee_type WHERE id=p_type FOR SHARE;
   IF NOT FOUND OR NOT v_type.active THEN RAISE EXCEPTION 'FEE_TYPE_INACTIVE'; END IF;
   IF v_type.system_key='initial' AND NOT (p_command='replace_trip_fee' AND v_old.fee_type_id IS NOT DISTINCT FROM p_type)
   THEN RAISE EXCEPTION 'FEE_TYPE_SYSTEM'; END IF;
   IF p_amount=0 OR (p_amount IS NULL AND p_command<>'set_trip_fee_type') THEN RAISE EXCEPTION 'FEE_AMOUNT_INVALID'; END IF;
   IF (v_type.sign='positive' AND p_amount<0) OR (v_type.sign='negative' AND p_amount>0)
   THEN RAISE EXCEPTION 'FEE_SIGN_INVALID'; END IF;
 END IF;
 IF length(p_note)>2000 THEN RAISE EXCEPTION 'INVALID_COMMAND'; END IF;
 FOR v_target IN SELECT x FROM jsonb_array_elements(p_targets) x LOOP
   v_state:=sokhach._fee_target(p_customer,v_target);
   v_before:=v_before||jsonb_build_array(v_state);
   SELECT coalesce(jsonb_agg(x),'[]') INTO v_retry FROM jsonb_array_elements(v_state->'fee_lines') x
     WHERE NOT (p_command='set_trip_fee_type' AND (x->>'fee_type_id')::bigint=p_type)
       AND NOT (p_command IN ('replace_trip_fee','void_trip_fee') AND (x->>'id')::bigint=p_line);
   IF p_command<>'void_trip_fee' AND p_amount IS NOT NULL THEN
     v_retry:=v_retry||jsonb_build_array(jsonb_build_object('fee_type_id',p_type,'amount_vnd',p_amount::text,'note',p_note));
   END IF;
   v_state:=v_state||jsonb_build_object('fee_lines',v_retry);
   IF v_target ? 'legacy_row_id' THEN
     SELECT sum((x->>'amount_vnd')::bigint)::bigint INTO v_total FROM jsonb_array_elements(v_retry) x;
     v_state:=v_state||jsonb_build_object('counted_vnd',CASE WHEN sokhach._legacy_current((v_target->>'legacy_row_id')::bigint)->>'unit_price_vnd' IS NULL THEN '0'
       ELSE (((sokhach._legacy_current((v_target->>'legacy_row_id')::bigint)->>'unit_price_vnd')::bigint)+coalesce(v_total,0))::text END);
   END IF;
   v_after:=v_after||jsonb_build_array(v_state);
 END LOOP;
 INSERT INTO sokhach.event(customer_id,kind,actor,"before","after",idempotency_key)
 VALUES(p_customer,p_command,sokhach._actor(),jsonb_build_object('targets',v_before,'batch_count',jsonb_array_length(p_targets)),
   jsonb_build_object('targets',v_after,'batch_count',jsonb_array_length(p_targets)),p_key) RETURNING id INTO v_event;
 v_after:='[]';
 FOR v_target IN SELECT x FROM jsonb_array_elements(p_targets) x LOOP
   IF p_command IN ('replace_trip_fee','void_trip_fee') THEN
     UPDATE sokhach.trip_fee_line SET voided_by_event=v_event WHERE id=p_line;
   ELSIF p_command='set_trip_fee_type' THEN
     UPDATE sokhach.trip_fee_line SET voided_by_event=v_event WHERE customer_id=p_customer AND fee_type_id=p_type
       AND (trip_id=(v_target->>'trip_id')::bigint OR legacy_row_id=(v_target->>'legacy_row_id')::bigint)
       AND voided_by_event IS NULL;
   END IF;
   IF p_command<>'void_trip_fee' AND p_amount IS NOT NULL THEN
     INSERT INTO sokhach.trip_fee_line(customer_id,trip_id,legacy_row_id,fee_type_id,amount_vnd,note,created_by_event)
     VALUES(p_customer,(v_target->>'trip_id')::bigint,(v_target->>'legacy_row_id')::bigint,p_type,p_amount,p_note,v_event);
   END IF;
   IF v_target ? 'trip_id' THEN
     PERFORM sokhach._sync_trip_fee((v_target->>'trip_id')::bigint,v_event);
   ELSE
     SELECT sum(amount_vnd)::bigint INTO v_total FROM sokhach.trip_fee_line
       WHERE legacy_row_id=(v_target->>'legacy_row_id')::bigint AND voided_by_event IS NULL;
     PERFORM sokhach._change_legacy(p_customer,p_version,p_key,(v_target->>'legacy_row_id')::bigint,
       'other_fee_vnd',v_total::text,false,v_event);
   END IF;
   v_state:=sokhach._fee_target(p_customer,v_target);
   v_after:=v_after||jsonb_build_array(v_state);
 END LOOP;
 v_changes:=sokhach.reallocate(p_customer,p_key);
 RETURN sokhach._finish_command(p_customer,p_key,v_payload,jsonb_build_object('event_id',v_event,'targets',v_after,'reallocated',v_changes));
EXCEPTION WHEN numeric_value_out_of_range THEN RAISE EXCEPTION 'FEE_AMOUNT_INVALID';
END $$;

CREATE OR REPLACE FUNCTION sokhach.get_ledger(customer_id bigint) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, sokhach, pg_temp AS $$
DECLARE v_version bigint; v_active boolean; v_months jsonb; v_trips jsonb;
        v_adjustments jsonb; v_receipts jsonb; v_opening jsonb; v_legacy jsonb;
        v_events jsonb; v_flags jsonb; v_total numeric; v_pending bigint; v_locks jsonb;
BEGIN
    PERFORM sokhach._actor();
    SELECT c.version INTO v_version FROM sokhach.customer c WHERE c.id=get_ledger.customer_id;
    IF NOT FOUND THEN RAISE EXCEPTION 'CUSTOMER_NOT_FOUND'; END IF;
    SELECT EXISTS (SELECT 1 FROM sokhach.cutover_customer cc
        JOIN sokhach.cutover c ON c.id=cc.cutover_id
        WHERE cc.customer_id=get_ledger.customer_id AND cc.status='active' AND c.status='active')
    INTO v_active;
    -- Source (Sheet) figures per month, for side-by-side reading only: never part of
    -- the balance, which comes from opening buckets (user choice 20/10/2026, option b).
    SELECT coalesce(jsonb_agg(jsonb_build_object('month',m.debt_month,
        'exception_codes',m.exception_codes,
        'source_charge_vnd',m.source_charge_vnd::text,
        'source_receipt_vnd',m.source_receipt_vnd::text,
        'source_cumulative_vnd',m.source_cumulative_vnd::text) ORDER BY m.debt_month),'[]'::jsonb)
    INTO v_flags FROM sokhach.cutover_month_check m
    WHERE m.customer_id=get_ledger.customer_id;
    IF NOT v_active THEN
        RETURN jsonb_build_object('status','NO_BASELINE','customer_id',customer_id,'fee_columns',sokhach._fee_columns(customer_id),
            'version',v_version,'months','[]'::jsonb,'source_exceptions',v_flags,
            'total_outstanding_vnd',NULL);
    END IF;
    -- DA-THU-01 (28/10/2026): dòng Tổng tháng cộng như Sheet. Đã thu = phiếu chưa hủy có ngày thu trong
    -- tháng (đủ số tiền) trừ cấn trừ đi và khoản thu sổ gốc đã xóa; tháng có số Sheet lấy phát sinh/đã thu
    -- của Sheet thay số dư đầu.
    -- Còn nợ cộng dồn tính lùi từ tổng còn nợ nên tháng cuối luôn bằng tổng; outstanding_vnd vẫn là
    -- nợ còn lại của kỳ sau phân bổ nợ cũ trước (tuổi nợ, đối soát), không đổi.
    WITH active_cutover AS (
      SELECT cc.cutover_id FROM sokhach.cutover_customer cc JOIN sokhach.cutover c ON c.id=cc.cutover_id
      WHERE cc.customer_id=get_ledger.customer_id AND cc.status='active' AND c.status='active'
    ), month_keys AS (
      SELECT v.debt_month FROM sokhach.v_outstanding_month v WHERE v.customer_id=get_ledger.customer_id
      UNION SELECT t.debt_month FROM sokhach.v_trip_current t
        WHERE NOT t.deleted AND t.customer_id=get_ledger.customer_id
      UNION SELECT date_trunc('month',r.date)::date FROM sokhach.receipt r
        WHERE r.customer_id=get_ledger.customer_id AND r.voided_on IS NULL
    ), figures AS (
      SELECT k.debt_month,
        coalesce((SELECT v.outstanding_vnd FROM sokhach.v_outstanding_month v
            WHERE v.customer_id=get_ledger.customer_id AND v.debt_month=k.debt_month),0)::bigint AS outstanding_vnd,
        coalesce(s.source_charge_vnd,(SELECT sum(o.amount_vnd) FROM sokhach.opening_balance o
            JOIN active_cutover a ON a.cutover_id=o.cutover_id
            WHERE o.customer_id=get_ledger.customer_id AND o.debt_month=k.debt_month),0)
        +coalesce((SELECT sum(CASE WHEN p.unit_price_vnd IS NOT NULL
            THEN p.unit_price_vnd+coalesce(p.other_fee_vnd,0)
            WHEN t.container IS NULL OR t.container='' THEN p.other_fee_vnd END)
            FROM sokhach.v_trip_current t LEFT JOIN LATERAL
              (SELECT unit_price_vnd,other_fee_vnd FROM sokhach.trip_price_rev
               WHERE trip_id=t.id ORDER BY id DESC LIMIT 1) p ON true
            WHERE t.customer_id=get_ledger.customer_id AND t.debt_month=k.debt_month AND NOT t.deleted AND t.status='confirmed'),0)
        +coalesce((SELECT sum(a.amount_vnd) FROM sokhach.v_adjustment_current a
            LEFT JOIN sokhach.legacy_row lr ON lr.id=a.legacy_row_id
            WHERE a.customer_id=get_ledger.customer_id AND a.debt_month=k.debt_month
              AND lr.kind IS DISTINCT FROM 'receipt'),0) AS charges_vnd,
        coalesce(s.source_receipt_vnd,0)
        +coalesce((SELECT sum(r.amount_vnd) FROM sokhach.receipt r
            WHERE r.customer_id=get_ledger.customer_id AND r.voided_on IS NULL
              AND date_trunc('month',r.date)::date=k.debt_month),0)
        -coalesce((SELECT sum(o.amount_vnd) FROM sokhach.v_offset_outgoing o
            WHERE o.customer_id=get_ledger.customer_id AND o.debt_month=k.debt_month),0)
        -- Sửa/xóa khoản thu sổ gốc (XOA-THU-GOC-01) đổi tiền thu của tháng đó, không phải phát sinh.
        -coalesce((SELECT sum(a.amount_vnd) FROM sokhach.v_adjustment_current a
            JOIN sokhach.legacy_row lr ON lr.id=a.legacy_row_id AND lr.kind='receipt'
            WHERE a.customer_id=get_ledger.customer_id AND a.debt_month=k.debt_month),0) AS received_vnd
      FROM month_keys k LEFT JOIN LATERAL (SELECT m.source_charge_vnd,m.source_receipt_vnd
          FROM sokhach.cutover_month_check m JOIN active_cutover a ON a.cutover_id=m.cutover_id
          WHERE m.customer_id=get_ledger.customer_id AND m.debt_month=k.debt_month
            AND m.source_charge_vnd IS NOT NULL AND m.source_receipt_vnd IS NOT NULL) s ON true
    ), chain AS (
      SELECT f.*,(sum(f.outstanding_vnd) OVER () - coalesce(sum(f.charges_vnd-f.received_vnd) OVER
          (ORDER BY f.debt_month ROWS BETWEEN 1 FOLLOWING AND UNBOUNDED FOLLOWING),0))::bigint AS end_of_month_vnd
      FROM figures f
    )
    SELECT coalesce(jsonb_agg(jsonb_build_object('month',debt_month,
        'outstanding_vnd',outstanding_vnd::text,'end_of_month_vnd',end_of_month_vnd::text,
        'prior_months_vnd',(end_of_month_vnd-charges_vnd+received_vnd)::text,
        'charges_vnd',charges_vnd::text,'received_vnd',received_vnd::text)
        ORDER BY debt_month),'[]'::jsonb),coalesce(sum(outstanding_vnd),0)
    INTO v_months,v_total FROM chain;
    SELECT coalesce(jsonb_agg(jsonb_build_object('id',t.id,'month',t.debt_month,
        'event_date',t.event_date,'container',t.container,'carrier',t.carrier,'shipper',t.shipper,'status',t.status,'booking',t.booking,
        'review_reason',coalesce((SELECT e."after"->>'review_reason' FROM sokhach.trip_info_rev r
            JOIN sokhach.event e ON e.id=r.created_by_event WHERE r.trip_id=t.id ORDER BY r.id DESC LIMIT 1),
            (SELECT x->>'review_reason' FROM sokhach.trip tr JOIN sokhach.event e ON e.id=tr.created_by_event
            CROSS JOIN LATERAL jsonb_array_elements(e."after"->'trips') x
            WHERE tr.id=t.id AND x->>'trip_id'=t.id::text)),
        'origin',t.origin,'destination',t.destination,'note',t.note,
        'unit_price_vnd',p.unit_price_vnd::text,'other_fee_vnd',p.other_fee_vnd::text,
        'fee_lines',sokhach._fee_lines(t.id,NULL),
        'has_typed_fee',EXISTS (SELECT 1 FROM sokhach.trip_fee_line fl JOIN sokhach.fee_type ft ON ft.id=fl.fee_type_id
            WHERE fl.trip_id=t.id AND fl.voided_by_event IS NULL
              AND coalesce(ft.system_key,'') NOT IN ('other','discount','initial')),
        'amount_vnd',CASE WHEN t.status<>'confirmed' THEN NULL WHEN p.unit_price_vnd IS NOT NULL
            THEN (p.unit_price_vnd+coalesce(p.other_fee_vnd,0))::text
            WHEN t.container IS NULL OR t.container='' THEN p.other_fee_vnd::text END,
        'is_fee_only',p.unit_price_vnd IS NULL AND p.other_fee_vnd IS NOT NULL
            AND (t.container IS NULL OR t.container=''),
        'is_missing_price',p.unit_price_vnd IS NULL AND NOT
            (p.other_fee_vnd IS NOT NULL AND (t.container IS NULL OR t.container='')),
        'editable',t.status='confirmed' AND NOT coalesce(ms.locked,t.debt_month <>
            date_trunc('month',clock_timestamp() AT TIME ZONE 'Asia/Ho_Chi_Minh')::date),
        'info_editable',NOT coalesce(ms.locked,t.debt_month <>
            date_trunc('month',clock_timestamp() AT TIME ZONE 'Asia/Ho_Chi_Minh')::date))
        ORDER BY t.debt_month,t.id),'[]'::jsonb),
        count(*) FILTER (WHERE t.status='pending_review' OR p.unit_price_vnd IS NULL AND NOT
            (p.other_fee_vnd IS NOT NULL AND (t.container IS NULL OR t.container='')))
    INTO v_trips,v_pending FROM sokhach.v_trip_current t
    LEFT JOIN LATERAL (SELECT unit_price_vnd,other_fee_vnd FROM sokhach.trip_price_rev
        WHERE trip_id=t.id ORDER BY id DESC LIMIT 1) p ON true
    LEFT JOIN sokhach.month_state ms ON (ms.customer_id,ms.month)=(t.customer_id,t.debt_month)
    WHERE NOT t.deleted AND t.customer_id=get_ledger.customer_id;
    SELECT coalesce(jsonb_agg(jsonb_build_object('id',id,'month',debt_month,
        'trip_id',trip_id,'legacy_row_id',legacy_row_id,'amount_vnd',amount_vnd::text,'note',note,'at',at)
        ORDER BY debt_month,id),'[]'::jsonb) INTO v_adjustments
    FROM sokhach.v_adjustment_current WHERE v_adjustment_current.customer_id=get_ledger.customer_id;
    SELECT coalesce(jsonb_agg(jsonb_build_object('id',r.id,'pid',r.pid,'date',r.date,
        'method',r.method,'reference',r.reference,'amount_vnd',r.amount_vnd::text,'void_reason',r.void_reason,
        'offset_pair_id',(SELECT id FROM sokhach.offset_pair WHERE target_receipt_id=r.id),
        'counterparty_customer_id',(SELECT source_customer_id FROM sokhach.offset_pair WHERE target_receipt_id=r.id),
        'counterparty_name',(SELECT c.name FROM sokhach.offset_pair p JOIN sokhach.customer c
            ON c.id=p.source_customer_id WHERE p.target_receipt_id=r.id),
        'voided_on',r.voided_on,'voided_by_event',r.voided_by_event,'allocations',
        (SELECT coalesce(jsonb_agg(jsonb_build_object('id',l.id,'month',l.debt_month,
            'kind',l.kind,'amount_vnd',l.amount_vnd::text,'superseded_by_event',
            l.superseded_by_event) ORDER BY l.id),'[]'::jsonb)
            FROM sokhach.receipt_line l WHERE l.receipt_id=r.id)) ORDER BY r.date,r.pid COLLATE "C"),'[]'::jsonb)
    INTO v_receipts FROM sokhach.receipt r WHERE r.customer_id=get_ledger.customer_id;
    SELECT coalesce(jsonb_agg(jsonb_build_object('id',o.id,'month',o.debt_month,
        'amount_vnd',o.amount_vnd::text,'editable',false) ORDER BY o.debt_month),'[]'::jsonb)
    INTO v_opening FROM sokhach.opening_balance o
    JOIN sokhach.cutover_customer cc ON (cc.customer_id,cc.cutover_id)=(o.customer_id,o.cutover_id)
    JOIN sokhach.cutover c ON c.id=cc.cutover_id
    WHERE o.customer_id=get_ledger.customer_id AND cc.status='active' AND c.status='active';
    SELECT coalesce(jsonb_agg(jsonb_build_object('id',l.id,'month',CASE WHEN l.kind='trip' THEN (cur.data->>'month')::date ELSE l.debt_month END,
        'kind',l.kind,'display',l.display,'source_total_vnd',l.source_total_vnd::text,
        'fee_lines',sokhach._fee_lines(NULL,l.id),
        'has_typed_fee',EXISTS (SELECT 1 FROM sokhach.trip_fee_line fl JOIN sokhach.fee_type ft ON ft.id=fl.fee_type_id
            WHERE fl.legacy_row_id=l.id AND fl.voided_by_event IS NULL
              AND coalesce(ft.system_key,'') NOT IN ('other','discount','initial')),
        -- Lần sửa phí đầu tiên đổi TOTAL sổ gốc sang đơn giá + tổng khoản; cờ báo trước số sẽ đổi.
        'counted_differs',l.kind='trip' AND cur.data->>'unit_price_vnd' IS NOT NULL
            AND (cur.data->>'counted_vnd')::bigint<>(cur.data->>'unit_price_vnd')::bigint
              +coalesce((SELECT sum(fl.amount_vnd) FROM sokhach.trip_fee_line fl
                WHERE fl.legacy_row_id=l.id AND fl.voided_by_event IS NULL),0),
        'historical',true,'editable',l.kind='trip','current',CASE WHEN l.kind='trip' THEN cur.data END) ORDER BY l.debt_month,l.id),'[]'::jsonb)
    INTO v_legacy FROM sokhach.legacy_row l
    CROSS JOIN LATERAL (SELECT sokhach._legacy_current(l.id) AS data) cur
    JOIN sokhach.cutover_customer cc ON (cc.customer_id,cc.cutover_id)=(l.customer_id,l.cutover_id)
    JOIN sokhach.cutover c ON c.id=cc.cutover_id
    WHERE l.customer_id=get_ledger.customer_id AND cc.status='active' AND c.status='active' AND NOT (cur.data->>'deleted')::boolean;
    SELECT coalesce(jsonb_agg(jsonb_build_object('id',id,'kind',kind,'actor',actor,
        'label',CASE kind WHEN 'fee_migration' THEN 'Tách phụ phí' WHEN 'trip_edit' THEN 'Sửa chuyến' WHEN 'trip_delete' THEN 'Xóa chuyến'
            WHEN 'legacy_edit' THEN 'Sửa dòng sổ gốc' WHEN 'legacy_delete' THEN 'Xóa dòng sổ gốc' ELSE kind END,
        'counterparty_customer_id',(SELECT CASE WHEN p.source_customer_id=event.customer_id
            THEN p.target_customer_id ELSE p.source_customer_id END FROM sokhach.offset_pair p
            WHERE (p.source_customer_id=event.customer_id AND p.source_pid=event."after"->>'receipt')
               OR (p.target_customer_id=event.customer_id AND p.target_receipt_id::text=event."after"->>'receipt')),
        'counterparty_name',(SELECT c.name FROM sokhach.offset_pair p JOIN sokhach.customer c
            ON c.id=CASE WHEN p.source_customer_id=event.customer_id THEN p.target_customer_id
                ELSE p.source_customer_id END
            WHERE (p.source_customer_id=event.customer_id AND p.source_pid=event."after"->>'receipt')
               OR (p.target_customer_id=event.customer_id AND p.target_receipt_id::text=event."after"->>'receipt')),
        'at',at,'before',CASE WHEN kind='price_edit' THEN "before" || jsonb_build_object(
            'price',"before"->'price' || jsonb_build_object(
                'unit_price_vnd',"before"->'price'->>'unit_price_vnd',
                'other_fee_vnd',"before"->'price'->>'other_fee_vnd')) ELSE "before" END,
        'after',CASE WHEN kind='price_edit' THEN "after" || jsonb_build_object(
            'price',"after"->'price' || jsonb_build_object(
                'unit_price_vnd',"after"->'price'->>'unit_price_vnd',
                'other_fee_vnd',"after"->'price'->>'other_fee_vnd')) ELSE "after" END)
        ORDER BY at DESC,id DESC),'[]'::jsonb)
    INTO v_events FROM sokhach.event WHERE event.customer_id=get_ledger.customer_id;
    -- Cờ khóa đã ghi của mọi tháng (kể cả tháng không chuyến); thiếu hàng thì
    -- chỉ today_month mở. Giao diện dùng hai trường này, không đoán theo đồng hồ máy.
    SELECT coalesce(jsonb_agg(jsonb_build_object('month',ms.month,'locked',ms.locked)
        ORDER BY ms.month),'[]'::jsonb) INTO v_locks
    FROM sokhach.month_state ms WHERE ms.customer_id=get_ledger.customer_id;
    RETURN jsonb_build_object('status','active','customer_id',customer_id,'fee_columns',sokhach._fee_columns(customer_id),
        'today_month',date_trunc('month',clock_timestamp() AT TIME ZONE 'Asia/Ho_Chi_Minh')::date,
        'month_locks',v_locks,
        'version',v_version,'months',v_months,'total_outstanding_vnd',v_total::bigint::text,
        'pending_count',v_pending,'trips',v_trips,'adjustments',v_adjustments,
        'receipts',v_receipts,'opening',v_opening,'source_exceptions',v_flags,
        'legacy_rows',v_legacy,'events',v_events,
        'outgoing_offsets',coalesce((SELECT jsonb_agg(jsonb_build_object(
            'offset_pair_id',p.id,'pid',p.source_pid,'date',p.date,'method','CẤN TRỪ',
            'amount_vnd',(-p.amount_vnd)::text,'void_reason',p.void_reason,
            'voided_by_event',p.voided_by_event,'counterparty_customer_id',p.target_customer_id,
            'counterparty_name',c.name) ORDER BY p.date,p.source_pid COLLATE "C")
            FROM sokhach.offset_pair p JOIN sokhach.customer c ON c.id=p.target_customer_id
            WHERE p.source_customer_id=get_ledger.customer_id),'[]'::jsonb));
END $$;

REVOKE ALL ON FUNCTION sokhach._change_trip_fees(bigint,bigint,text,text,jsonb,bigint,bigint,text,bigint) FROM PUBLIC,sokhach_app,sokhach_reader;
COMMIT;
