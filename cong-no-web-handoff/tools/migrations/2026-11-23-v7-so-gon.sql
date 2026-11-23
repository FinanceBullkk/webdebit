-- Audit SQL lõi tiền 23/11/2026, F4: thu gọn get_ledger và bỏ dựng cả sổ trong ba lệnh ghi. Không đổi số tiền, bảng, quyền hay
-- hình dạng JSON của get_ledger (trừ `allocations` của phiếu chỉ còn dòng hiệu lực và dòng bị chính lệnh hủy phiếu thay, là hai loại
-- giao diện và bản xuất sổ đọc). Chạy sau 2026-11-23-v7-dieu-chinh-theo-gia.sql; chạy lại được.
-- - get_ledger: lý do CHỜ KIỂM lúc dán đọc một lượt cho cả sổ (mỗi event tạo chuyến bung mảng `trips` đúng một lần; trước: mỗi
--   chuyến bung lại cả mảng của lô nó, bậc hai theo cỡ lô). Giữ SET jit = off.
-- - _ledger_events: chỉ event có khóa `receipt` mới tìm cặp cấn trừ.
-- - apply_sheet_price, keep_sheet_task, undo_sheet_batch: đọc đúng một chuyến/dòng sổ gốc (_trip_current_row) thay vì get_ledger.
BEGIN;
SET LOCAL ROLE sokhach_owner;

CREATE OR REPLACE FUNCTION sokhach._trip_current_row(p_customer bigint, p_trip bigint) RETURNS jsonb
LANGUAGE sql STABLE SET search_path = pg_catalog, sokhach, pg_temp AS $$
    SELECT jsonb_build_object('id',t.id,'event_date',t.event_date,'container',t.container,'status',t.status,'booking',t.booking,
        'unit_price_vnd',p.unit_price_vnd::text,'other_fee_vnd',p.other_fee_vnd::text)
    FROM sokhach.v_trip_current t
    LEFT JOIN LATERAL (SELECT unit_price_vnd,other_fee_vnd FROM sokhach.trip_price_rev
        WHERE trip_id=t.id ORDER BY id DESC LIMIT 1) p ON true
    WHERE t.id=p_trip AND t.customer_id=p_customer AND NOT t.deleted
$$;

CREATE OR REPLACE FUNCTION sokhach._ledger_events(p_customer bigint) RETURNS jsonb
LANGUAGE sql STABLE SET search_path=pg_catalog,sokhach,pg_temp AS $$
    SELECT coalesce(jsonb_agg(jsonb_build_object('id',id,'kind',kind,'actor',actor,
        'label',CASE kind WHEN 'fee_migration' THEN 'Tách phụ phí' WHEN 'trip_edit' THEN 'Sửa chuyến' WHEN 'trip_delete' THEN 'Xóa chuyến'
            WHEN 'legacy_edit' THEN 'Sửa dòng sổ gốc' WHEN 'legacy_delete' THEN 'Xóa dòng sổ gốc' ELSE kind END,
        -- Audit SQL 23/11/2026 (F4): chỉ event có khóa `receipt` mới có thể là cấn trừ; event khác bỏ qua hai câu con.
        'counterparty_customer_id',CASE WHEN event."after" ? 'receipt' THEN (SELECT CASE WHEN p.source_customer_id=event.customer_id
            THEN p.target_customer_id ELSE p.source_customer_id END FROM sokhach.offset_pair p
            WHERE (p.source_customer_id=event.customer_id AND p.source_pid=event."after"->>'receipt')
               OR (p.target_customer_id=event.customer_id AND p.target_receipt_id::text=event."after"->>'receipt')) END,
        'counterparty_name',CASE WHEN event."after" ? 'receipt' THEN (SELECT c.name FROM sokhach.offset_pair p JOIN sokhach.customer c
            ON c.id=CASE WHEN p.source_customer_id=event.customer_id THEN p.target_customer_id
                ELSE p.source_customer_id END
            WHERE (p.source_customer_id=event.customer_id AND p.source_pid=event."after"->>'receipt')
               OR (p.target_customer_id=event.customer_id AND p.target_receipt_id::text=event."after"->>'receipt')) END,
        'at',at,'before',CASE WHEN kind='price_edit' THEN "before" || jsonb_build_object(
            'price',"before"->'price' || jsonb_build_object(
                'unit_price_vnd',"before"->'price'->>'unit_price_vnd',
                'other_fee_vnd',"before"->'price'->>'other_fee_vnd')) ELSE "before" END,
        'after',CASE WHEN kind='price_edit' THEN "after" || jsonb_build_object(
            'price',"after"->'price' || jsonb_build_object(
                'unit_price_vnd',"after"->'price'->>'unit_price_vnd',
                'other_fee_vnd',"after"->'price'->>'other_fee_vnd')) ELSE "after" END)
        ORDER BY at DESC,id DESC),'[]'::jsonb)
 FROM sokhach.event WHERE event.customer_id=p_customer
$$;

CREATE OR REPLACE FUNCTION sokhach.get_ledger(customer_id bigint) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, sokhach, pg_temp SET jit = off AS $$
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
            pr.reason),
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
    -- Audit SQL 23/11/2026 (F4): lý do lúc dán đọc một lượt: mỗi event tạo chuyến của sổ bung mảng `trips` đúng một lần
    -- (trước: mỗi chuyến bung lại cả mảng của lô nó, bậc hai theo cỡ lô).
    LEFT JOIN (SELECT (x->>'trip_id')::bigint AS trip_id, x->>'review_reason' AS reason
        FROM (SELECT DISTINCT tr.created_by_event FROM sokhach.trip tr WHERE tr.customer_id=get_ledger.customer_id) ev
        JOIN sokhach.event e ON e.id=ev.created_by_event
        CROSS JOIN LATERAL jsonb_array_elements(CASE WHEN jsonb_typeof(e."after"->'trips')='array' THEN e."after"->'trips' ELSE '[]'::jsonb END) x
        WHERE x ? 'review_reason') pr ON pr.trip_id=t.id
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
            -- Audit SQL 23/11/2026 (F4): bỏ các bản phân bổ cũ đã bị phân bổ lại thay; giữ dòng còn hiệu lực và dòng bị chính
            -- lệnh hủy phiếu thay (tháng của phiếu đã hủy). Số dòng không còn tăng theo số lần phân bổ lại.
            FROM sokhach.receipt_line l WHERE l.receipt_id=r.id
              AND (l.superseded_by_event IS NULL OR l.superseded_by_event=r.voided_by_event))) ORDER BY r.date,r.pid COLLATE "C"),'[]'::jsonb)
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
    v_events:=sokhach._ledger_events(get_ledger.customer_id);
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

CREATE OR REPLACE FUNCTION sokhach.keep_sheet_task(
 customer_id bigint, expected_version bigint, idempotency_key text,
 task_kind text, target_kind text, target_id bigint, source_fingerprint text, web_value jsonb
) RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,sokhach,pg_temp AS $$
DECLARE v_payload jsonb:=jsonb_build_object('command','keep_sheet_task','task_kind',task_kind,
 'target_kind',target_kind,'target_id',target_id,'source_fingerprint',source_fingerprint,'web_value',web_value);
 v_retry jsonb; v_current jsonb; v_row jsonb;
BEGIN
 v_retry:=sokhach._begin_command(customer_id,expected_version,idempotency_key,v_payload);
 IF v_retry IS NOT NULL THEN RETURN v_retry; END IF;
 PERFORM sokhach._baseline(customer_id);
 IF task_kind IS NULL OR task_kind NOT IN ('price','removed','ps','source')
  OR source_fingerprint IS NULL OR source_fingerprint !~ '^[0-9a-f]{64}$' OR web_value IS NULL
 THEN RAISE EXCEPTION 'INVALID_SHEET_RESOLUTION'; END IF;
 IF task_kind='source' THEN
  -- K3: đóng một dòng Sheet theo dấu vân nội dung của nó, không gắn chuyến. web_value chỉ là {"scope": ...}.
  IF target_kind IS NOT NULL OR target_id IS NOT NULL OR jsonb_typeof(web_value)<>'object'
   OR web_value-'scope'<>'{}'::jsonb OR web_value->>'scope' IS NULL OR web_value->>'scope' NOT IN ('price','ps','trip')
  THEN RAISE EXCEPTION 'INVALID_SHEET_RESOLUTION'; END IF;
  INSERT INTO sokhach.event(customer_id,kind,actor,"before","after",idempotency_key)
  VALUES(customer_id,'sheet_conflict_resolved',sokhach._actor(),
   jsonb_build_object('target',jsonb_build_object('kind','source','scope',web_value->>'scope'),'field','task_source','value',web_value),
   jsonb_build_object('target',jsonb_build_object('kind','source','scope',web_value->>'scope'),'field','task_source',
    'source_row',0,'sheet_value',source_fingerprint,'target_value',web_value,'decision','keep_web','request_key',idempotency_key),idempotency_key);
  RETURN sokhach._finish_command(customer_id,idempotency_key,v_payload,jsonb_build_object('kept',true));
 END IF;
 IF target_kind IS NULL OR target_kind NOT IN ('trip','legacy') OR target_id IS NULL OR target_id<=0
  OR (task_kind='removed' AND target_kind<>'trip')
 THEN RAISE EXCEPTION 'INVALID_SHEET_RESOLUTION'; END IF;
 IF target_kind='trip' THEN
  v_row:=sokhach._trip_current_row(customer_id,target_id);  -- audit SQL F4: một chuyến, không dựng cả sổ
 ELSE
  SELECT sokhach._legacy_current(l.id) INTO v_row FROM sokhach.legacy_row l
   JOIN sokhach.cutover_customer cc USING(customer_id,cutover_id)
   JOIN sokhach.cutover c ON c.id=cc.cutover_id
   WHERE l.customer_id=keep_sheet_task.customer_id AND l.id=target_id AND l.kind='trip'
     AND cc.status='active' AND c.status='active';
 END IF;
 IF v_row IS NULL OR coalesce((v_row->>'deleted')::boolean,false) THEN RAISE EXCEPTION 'TRIP_NOT_FOUND'; END IF;
 v_current:=CASE WHEN task_kind IN ('price','ps') THEN jsonb_build_object(
  'unit_price_vnd',v_row->>'unit_price_vnd','other_fee_vnd',v_row->>'other_fee_vnd')
 ELSE jsonb_build_object('container',v_row->>'container','event_date',v_row->>'event_date',
  'status',v_row->>'status','booking',v_row->>'booking') END;
 IF v_current IS DISTINCT FROM web_value THEN RAISE EXCEPTION 'STALE_LEDGER'; END IF;
 INSERT INTO sokhach.event(customer_id,kind,actor,"before","after",idempotency_key)
 VALUES(customer_id,'sheet_conflict_resolved',sokhach._actor(),
  jsonb_build_object('target',jsonb_build_object('kind',target_kind,'id',target_id),'field','task_'||task_kind,'value',v_current),
  jsonb_build_object('target',jsonb_build_object('kind',target_kind,'id',target_id),'field','task_'||task_kind,
   'source_row',0,'sheet_value',source_fingerprint,'target_value',v_current,'decision','keep_web','request_key',idempotency_key),idempotency_key);
 RETURN sokhach._finish_command(customer_id,idempotency_key,v_payload,jsonb_build_object('kept',true));
END $$;
REVOKE ALL ON FUNCTION sokhach.keep_sheet_task(bigint,bigint,text,text,text,bigint,text,jsonb) FROM PUBLIC,sokhach_reader;
GRANT EXECUTE ON FUNCTION sokhach.keep_sheet_task(bigint,bigint,text,text,text,bigint,text,jsonb) TO sokhach_app;

CREATE OR REPLACE FUNCTION sokhach.apply_sheet_price(
 customer_id bigint, expected_version bigint, idempotency_key text,
 target_kind text, target_id bigint, source_fingerprint text, web_value jsonb, sheet_price jsonb
) RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,sokhach,pg_temp AS $$
DECLARE v_payload jsonb:=jsonb_build_object('command','apply_sheet_price','target_kind',target_kind,
 'target_id',target_id,'source_fingerprint',source_fingerprint,'web_value',web_value,'sheet_price',sheet_price);
 v_retry jsonb; v_current jsonb; v_result jsonb; v_version bigint; v_key text;
BEGIN
 v_retry:=sokhach._begin_command(customer_id,expected_version,idempotency_key,v_payload);
 IF v_retry IS NOT NULL THEN RETURN v_retry; END IF;
 PERFORM sokhach._baseline(customer_id);
 IF target_kind IS NULL OR target_kind NOT IN ('trip','legacy') OR target_id IS NULL OR target_id<=0
  OR source_fingerprint IS NULL OR source_fingerprint !~ '^[0-9a-f]{64}$'
  OR jsonb_typeof(sheet_price) IS DISTINCT FROM 'object' OR web_value IS NULL
  OR sheet_price->>'unit_price_vnd' IS NULL OR sheet_price->>'unit_price_vnd' !~ '^[0-9]+$'
  OR (sheet_price->>'other_fee_vnd' IS NOT NULL AND sheet_price->>'other_fee_vnd' !~ '^-?[0-9]+$')
 THEN RAISE EXCEPTION 'INVALID_SHEET_RESOLUTION'; END IF;
 IF target_kind='trip' THEN
  -- audit SQL F4: một chuyến/một dòng sổ gốc, không dựng cả sổ bằng get_ledger.
  SELECT jsonb_build_object('unit_price_vnd',r->>'unit_price_vnd','other_fee_vnd',r->>'other_fee_vnd')
   INTO v_current FROM sokhach._trip_current_row(customer_id,target_id) r WHERE r IS NOT NULL;
 ELSE
  SELECT jsonb_build_object('unit_price_vnd',cur->>'unit_price_vnd','other_fee_vnd',cur->>'other_fee_vnd')
   INTO v_current FROM sokhach.legacy_row l
   JOIN sokhach.cutover_customer cc USING(customer_id,cutover_id) JOIN sokhach.cutover c ON c.id=cc.cutover_id
   CROSS JOIN LATERAL sokhach._legacy_current(l.id) cur
   WHERE l.customer_id=apply_sheet_price.customer_id AND l.id=target_id AND l.kind='trip'
     AND cc.status='active' AND c.status='active' AND NOT coalesce((cur->>'deleted')::boolean,false);
 END IF;
 IF v_current IS NULL THEN RAISE EXCEPTION 'TRIP_NOT_FOUND'; END IF;
 IF v_current IS DISTINCT FROM web_value THEN RAISE EXCEPTION 'STALE_LEDGER'; END IF;
 v_key:=encode(sha256(convert_to(idempotency_key||':sheet-price','UTF8')),'hex');
 IF target_kind='trip' THEN
  v_result:=sokhach.edit_trip_price(customer_id,expected_version,v_key,target_id,
   (sheet_price->>'unit_price_vnd')::bigint,(sheet_price->>'other_fee_vnd')::bigint);
 ELSE
  v_version:=expected_version;
  IF v_current->>'unit_price_vnd' IS DISTINCT FROM sheet_price->>'unit_price_vnd' THEN
   v_result:=sokhach.edit_legacy_trip(customer_id,v_version,v_key,target_id,'unit_price_vnd',sheet_price->>'unit_price_vnd');
   v_version:=(v_result->>'version')::bigint;
  END IF;
  IF nullif(v_current->>'other_fee_vnd','0') IS DISTINCT FROM nullif(sheet_price->>'other_fee_vnd','0') THEN
   v_result:=sokhach.edit_legacy_trip(customer_id,v_version,v_key||':fee',target_id,'other_fee_vnd',sheet_price->>'other_fee_vnd');
  END IF;
  IF v_result IS NULL THEN RAISE EXCEPTION 'NO_CHANGE'; END IF;
 END IF;
 INSERT INTO sokhach.event(customer_id,kind,actor,"before","after",idempotency_key)
 VALUES(customer_id,'sheet_conflict_resolved',sokhach._actor(),
  jsonb_build_object('target',jsonb_build_object('kind',target_kind,'id',target_id),'field','task_price','value',v_current),
  jsonb_build_object('target',jsonb_build_object('kind',target_kind,'id',target_id),'field','task_price','source_row',0,
   'sheet_value',source_fingerprint,'target_value',sheet_price,'decision','use_sheet','requested_price',sheet_price,
   'web_value',web_value,'request_key',idempotency_key),idempotency_key);
 RETURN sokhach._finish_command(customer_id,idempotency_key,v_payload,jsonb_build_object('written',1,'complete',true));
END $$;
REVOKE ALL ON FUNCTION sokhach.apply_sheet_price(bigint,bigint,text,text,bigint,text,jsonb,jsonb) FROM PUBLIC,sokhach_reader;
GRANT EXECUTE ON FUNCTION sokhach.apply_sheet_price(bigint,bigint,text,text,bigint,text,jsonb,jsonb) TO sokhach_app;

CREATE OR REPLACE FUNCTION sokhach.undo_sheet_batch(
 customer_id bigint, expected_version bigint, idempotency_key text, command_keys jsonb
) RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,sokhach,pg_temp AS $$
DECLARE v_payload jsonb:=jsonb_build_object('command','undo_sheet_batch','command_keys',command_keys);
 v_retry jsonb; v_key text; v_undo_key text; e sokhach.event%ROWTYPE; v_version bigint;
 v_result jsonb; v_before jsonb; v_after jsonb; v_current jsonb; v_id bigint; v_event bigint; v_count bigint;
BEGIN
 v_retry:=sokhach._begin_command(customer_id,expected_version,idempotency_key,v_payload);
 IF v_retry IS NOT NULL THEN RETURN v_retry; END IF;
 PERFORM sokhach._baseline(customer_id);
 IF jsonb_typeof(command_keys) IS DISTINCT FROM 'array' OR jsonb_array_length(command_keys) NOT BETWEEN 1 AND 1000
  OR EXISTS(SELECT 1 FROM jsonb_array_elements(command_keys) k WHERE jsonb_typeof(k)<>'string' OR k#>>'{}' !~ '^[0-9a-f]{64}$')
  OR (SELECT count(DISTINCT k) FROM jsonb_array_elements_text(command_keys) k)<>jsonb_array_length(command_keys)
 THEN RAISE EXCEPTION 'INVALID_COMMAND'; END IF;
 v_version:=expected_version;
 FOR v_key IN SELECT k FROM jsonb_array_elements_text(command_keys) WITH ORDINALITY x(k,n) ORDER BY n DESC LOOP
  SELECT * INTO e FROM sokhach.event ev WHERE ev.customer_id=undo_sheet_batch.customer_id AND ev.idempotency_key=v_key
   AND ev.kind IN ('price_edit','receipt','legacy_edit') ORDER BY ev.id DESC LIMIT 1;
  IF NOT FOUND THEN RAISE EXCEPTION 'INVALID_COMMAND'; END IF;
  v_undo_key:=encode(sha256(convert_to(idempotency_key||':'||v_key,'UTF8')),'hex');
  IF e.kind='receipt' THEN
   v_result:=sokhach.void_receipt(customer_id,v_version,v_undo_key,e."after"->>'pid','Hoàn tác lần ghi từ Việc cần làm');
  ELSIF e.kind='price_edit' THEN
   v_before:=e."before"->'price'; v_after:=e."after"->'price'; v_id:=(v_after->>'trip_id')::bigint;
   v_current:=sokhach._trip_current_row(customer_id,v_id);  -- audit SQL F4: một chuyến, không dựng cả sổ mỗi khóa
   IF v_current IS NULL OR v_current->>'unit_price_vnd' IS DISTINCT FROM v_after->>'unit_price_vnd'
    OR v_current->>'other_fee_vnd' IS DISTINCT FROM v_after->>'other_fee_vnd' THEN RAISE EXCEPTION 'STALE_LEDGER'; END IF;
   v_result:=sokhach.edit_trip_price(customer_id,v_version,v_undo_key,v_id,
     (v_before->>'unit_price_vnd')::bigint,(v_before->>'other_fee_vnd')::bigint);
  ELSE
   v_before:=e."before"->'legacy'; v_after:=e."after"->'legacy'; v_id:=(v_before->>'legacy_row_id')::bigint;
   IF v_before->>'kind'<>'trip' OR v_before->>'field' NOT IN ('unit_price_vnd','other_fee_vnd') THEN RAISE EXCEPTION 'INVALID_COMMAND'; END IF;
   v_current:=sokhach._legacy_current(v_id);
   IF v_current->>'unit_price_vnd' IS DISTINCT FROM v_after->>'unit_price_vnd'
    OR v_current->>'counted_vnd' IS DISTINCT FROM v_after->>'counted_vnd' THEN RAISE EXCEPTION 'STALE_LEDGER'; END IF;
   v_result:=sokhach.edit_legacy_trip(customer_id,v_version,v_undo_key,v_id,v_before->>'field',v_before->>'value');
   v_current:=sokhach._legacy_current(v_id);
   v_count:=(v_before->>'counted_vnd')::bigint;
   IF (v_current->>'counted_vnd')::bigint<>v_count THEN
    -- Restoring an original-book price must also restore its original TOTAL, which may differ from price + fees.
    v_after:=v_current||jsonb_build_object('counted_vnd',v_count::text,'field','unit_price_vnd','value',v_current->'unit_price_vnd');
    INSERT INTO sokhach.event(customer_id,kind,actor,"before","after",idempotency_key)
    VALUES(customer_id,'legacy_edit',sokhach._actor(),jsonb_build_object('legacy',v_current),jsonb_build_object('legacy',v_after),v_undo_key) RETURNING id INTO v_event;
    INSERT INTO sokhach.legacy_trip_rev(legacy_row_id,customer_id,debt_month,event_date,container,carrier,shipper,origin,destination,unit_price_vnd,other_fee_vnd,deleted,counted_vnd,created_by_event)
    VALUES(v_id,customer_id,(v_current->>'month')::date,(v_current->>'event_date')::date,v_current->>'container',v_current->>'carrier',v_current->>'shipper',v_current->>'origin',v_current->>'destination',
     (v_current->>'unit_price_vnd')::bigint,(v_current->>'other_fee_vnd')::bigint,false,v_count,v_event);
    INSERT INTO sokhach.adjustment(customer_id,debt_month,legacy_row_id,amount_vnd,actor,created_by_event)
    VALUES(customer_id,(v_current->>'month')::date,v_id,v_count-(v_current->>'counted_vnd')::bigint,sokhach._actor(),v_event);
   END IF;
  END IF;
  v_version:=(v_result->>'version')::bigint;
 END LOOP;
 PERFORM sokhach.reallocate(customer_id,idempotency_key);
 RETURN sokhach._finish_command(customer_id,idempotency_key,v_payload,jsonb_build_object('undone',jsonb_array_length(command_keys),'complete',true));
END $$;
REVOKE ALL ON FUNCTION sokhach.undo_sheet_batch(bigint,bigint,text,jsonb) FROM PUBLIC,sokhach_reader;
GRANT EXECUTE ON FUNCTION sokhach.undo_sheet_batch(bigint,bigint,text,jsonb) TO sokhach_app;

CREATE OR REPLACE FUNCTION sokhach.schema_level() RETURNS integer
LANGUAGE sql IMMUTABLE SET search_path = pg_catalog, sokhach, pg_temp AS $$ SELECT 2026112303 $$;
REVOKE ALL ON FUNCTION sokhach.schema_level() FROM PUBLIC, sokhach_app, sokhach_reader;
GRANT EXECUTE ON FUNCTION sokhach.schema_level() TO sokhach_app;

REVOKE ALL ON FUNCTION sokhach._trip_current_row(bigint,bigint) FROM PUBLIC, sokhach_app, sokhach_reader;
RESET ROLE;
COMMIT;
