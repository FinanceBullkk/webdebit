-- CAN-DU-01 (30/10/2026, docs/decisions/can-du-01.md, thay V7-BE (6)): nợ còn lại từng kỳ theo chuẩn tuổi nợ.
-- Khoản dư của kỳ âm cấn vào kỳ còn nợ cũ nhất trước; cấn hết mà vẫn dư thì phần dư nằm ở kỳ cuối.
-- Chỉ đổi view đọc và hai hàm, không đổi bảng, ràng buộc, dữ liệu, dòng phân bổ, event hay quyền.
-- 1. v_outstanding_month_raw: nguyên thân v_outstanding_month cũ (số thô, kỳ âm giữ dấu).
-- 2. v_outstanding_month: cấn khoản dư; tổng mỗi khách không đổi (kiểm ở cuối, lệch thì hủy cả lượt).
-- 3. record_receipt: xếp tạm theo số thô như reallocate, nên dòng phân bổ và event giữ như trước.
-- 4. get_receivables_detail: thêm credit_applied_vnd (số thô − ô ma trận) cho ngăn kéo.
-- 5. ANALYZE các bảng sokhach để planner tính view cấn dư một lần cho hàm đọc nhiều khách.
-- Chạy sau 2026-10-29-v7-ra-ghi-tien.sql. Chạy lại được.
BEGIN;
SET LOCAL ROLE sokhach_owner;
CREATE TEMP TABLE can_du_before ON COMMIT DROP AS
SELECT customer_id,sum(outstanding_vnd)::numeric AS total_vnd FROM sokhach.v_outstanding_month GROUP BY customer_id;

CREATE OR REPLACE VIEW sokhach.v_outstanding_month_raw AS
WITH active_customer AS (
    SELECT cc.customer_id,cc.cutover_id FROM sokhach.cutover_customer cc
    JOIN sokhach.cutover c ON c.id=cc.cutover_id
    WHERE cc.status='active' AND c.status='active'
), latest_price AS (
    SELECT t.customer_id,t.debt_month,
        CASE WHEN p.unit_price_vnd IS NOT NULL
             THEN p.unit_price_vnd+coalesce(p.other_fee_vnd,0)
             WHEN (t.container IS NULL OR t.container='') THEN p.other_fee_vnd END AS amount_vnd
    FROM sokhach.v_trip_current t JOIN active_customer ac ON ac.customer_id=t.customer_id
    LEFT JOIN LATERAL (SELECT unit_price_vnd,other_fee_vnd FROM sokhach.trip_price_rev
        WHERE trip_id=t.id ORDER BY id DESC LIMIT 1) p ON true
    WHERE NOT t.deleted AND t.status='confirmed'
), movements AS (
    SELECT o.customer_id,o.debt_month,o.amount_vnd FROM sokhach.opening_balance o
    JOIN active_customer ac ON (ac.customer_id,ac.cutover_id)=(o.customer_id,o.cutover_id)
    UNION ALL SELECT customer_id,debt_month,amount_vnd FROM latest_price WHERE amount_vnd IS NOT NULL
    UNION ALL SELECT a.customer_id,a.debt_month,a.amount_vnd FROM sokhach.v_adjustment_current a
        JOIN active_customer ac ON ac.customer_id=a.customer_id
    UNION ALL SELECT o.customer_id,o.debt_month,o.amount_vnd FROM sokhach.v_offset_outgoing o
        JOIN active_customer ac ON ac.customer_id=o.customer_id
    UNION ALL SELECT l.customer_id,l.debt_month,-l.amount_vnd FROM sokhach.v_receipt_line_active l
        JOIN active_customer ac ON ac.customer_id=l.customer_id
)
SELECT customer_id,debt_month,sum(amount_vnd)::bigint AS outstanding_vnd
FROM movements GROUP BY customer_id,debt_month;

CREATE OR REPLACE VIEW sokhach.v_outstanding_month AS
WITH s AS (
    SELECT customer_id,debt_month,outstanding_vnd AS raw_vnd,
        sum(greatest(-outstanding_vnd,0)) OVER whole AS credit_vnd,
        sum(greatest(outstanding_vnd,0)) OVER whole AS debt_vnd,
        sum(greatest(outstanding_vnd,0)) OVER (PARTITION BY customer_id ORDER BY debt_month
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS debt_through_vnd,
        debt_month=max(debt_month) OVER whole AS last_month
    FROM sokhach.v_outstanding_month_raw WINDOW whole AS (PARTITION BY customer_id)
)
SELECT customer_id,debt_month,
    (least(greatest(raw_vnd,0),greatest(debt_through_vnd-credit_vnd,0))
     + CASE WHEN last_month THEN least(debt_vnd-credit_vnd,0) ELSE 0 END)::bigint AS outstanding_vnd
FROM s;

CREATE OR REPLACE FUNCTION sokhach.record_receipt(customer_id bigint, expected_version bigint,
    idempotency_key text, date date, method text, amount_vnd bigint, reference text DEFAULT NULL)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, sokhach, pg_temp AS $$
DECLARE v_payload jsonb := jsonb_build_object('command','record_receipt','date',date,
        'method',method,'amount_vnd',amount_vnd)
        || CASE WHEN reference IS NULL THEN '{}'::jsonb ELSE jsonb_build_object('reference',reference) END;
        v_retry jsonb; v_id bigint; v_pid text; v_event bigint; v_left bigint;
        v_last date; v_month date; v_due bigint; v_take bigint; v_plan jsonb := '[]'::jsonb;
        v_line jsonb; v_result jsonb; v_plan_ids jsonb := '[]'::jsonb; v_changes jsonb;
BEGIN
    v_retry := sokhach._begin_command(customer_id,expected_version,idempotency_key,v_payload);
    IF v_retry IS NOT NULL THEN RETURN v_retry; END IF;
    PERFORM sokhach._baseline(customer_id);
    IF date IS NULL OR method NOT IN ('THU TIỀN','CẤN TRỪ','ỨNG TRƯỚC','KHÁC')
       OR amount_vnd IS NULL OR amount_vnd <= 0 THEN RAISE EXCEPTION 'INVALID_RECEIPT'; END IF;
    IF date > (clock_timestamp() AT TIME ZONE 'Asia/Ho_Chi_Minh')::date
       THEN RAISE EXCEPTION 'FUTURE_RECEIPT_DATE'; END IF;
    SELECT max(debt_month) INTO v_last FROM (
        SELECT debt_month FROM sokhach.opening_balance WHERE opening_balance.customer_id=record_receipt.customer_id
        UNION ALL SELECT debt_month FROM sokhach.v_trip_current v WHERE v.customer_id=record_receipt.customer_id AND NOT deleted AND status='confirmed'
        UNION ALL SELECT debt_month FROM sokhach.v_adjustment_current a WHERE a.customer_id=record_receipt.customer_id
        UNION ALL SELECT o.debt_month FROM sokhach.v_offset_outgoing o
            WHERE o.customer_id=record_receipt.customer_id
    ) m;
    IF v_last IS NULL THEN RAISE EXCEPTION 'NO_MONTH_FOR_RECEIPT'; END IF;
    v_pid := sokhach._next_pid(customer_id);
    v_id := nextval(pg_get_serial_sequence('sokhach.receipt','id'));
    v_left := amount_vnd;
    -- Xếp tạm theo số thô, cùng cách reallocate (CAN-DU-01 chỉ đổi số nợ hiển thị, không đổi dòng phân bổ).
    FOR v_month,v_due IN SELECT debt_month,outstanding_vnd FROM sokhach.v_outstanding_month_raw
        WHERE v_outstanding_month_raw.customer_id=record_receipt.customer_id ORDER BY debt_month
    LOOP
        EXIT WHEN v_left=0;
        IF v_due > 0 THEN
            v_take := least(v_left,v_due);
            v_plan := v_plan || jsonb_build_array(jsonb_build_object(
                'month',v_month,'kind','debt','amount_vnd',v_take::text));
            v_left := v_left-v_take;
        END IF;
    END LOOP;
    IF v_left>0 THEN
        v_plan := v_plan || jsonb_build_array(jsonb_build_object(
            'month',v_last,'kind','advance','amount_vnd',v_left::text));
    END IF;
    FOR v_line IN SELECT value FROM jsonb_array_elements(v_plan) LOOP
        v_plan_ids := v_plan_ids || jsonb_build_array(v_line ||
            jsonb_build_object('id',nextval(pg_get_serial_sequence('sokhach.receipt_line','id'))));
    END LOOP;
    INSERT INTO sokhach.event(customer_id,kind,actor,"before","after",idempotency_key)
    VALUES (customer_id,'receipt',sokhach._actor(),'{}',
        jsonb_build_object('receipt',v_id,'pid',v_pid,'date',date,'method',method,
                           'amount_vnd',amount_vnd::text,'reference',nullif(btrim(reference),''),'allocations',v_plan_ids),idempotency_key)
    RETURNING id INTO v_event;
    INSERT INTO sokhach.receipt(id,customer_id,pid,date,method,amount_vnd,reference,created_by_event)
    OVERRIDING SYSTEM VALUE VALUES (v_id,customer_id,v_pid,date,method,amount_vnd,nullif(btrim(reference),''),v_event);
    FOR v_line IN SELECT value FROM jsonb_array_elements(v_plan_ids) LOOP
        INSERT INTO sokhach.receipt_line(id,receipt_id,customer_id,debt_month,kind,amount_vnd,created_by_event)
        OVERRIDING SYSTEM VALUE VALUES ((v_line->>'id')::bigint,v_id,customer_id,(v_line->>'month')::date,v_line->>'kind',
                (v_line->>'amount_vnd')::bigint,v_event);
    END LOOP;
    -- V7-SO (sửa 29/10/2026): phiếu mới cũng phân bổ lại mọi phiếu chưa hủy theo (ngày, mã phiếu), nên dòng
    -- phân bổ đã lưu luôn là kết quả chuẩn và không đổi ở lệnh kế tiếp. Tổng nợ từng tháng không đổi.
    v_changes := sokhach.reallocate(customer_id,idempotency_key);
    v_result := jsonb_build_object('receipt_id',v_id,'pid',v_pid,'allocations',sokhach._lines(v_id),
                                  'reallocated',v_changes,'overpayment_vnd',v_left::text,
        'duplicate_reference',EXISTS (SELECT 1 FROM sokhach.receipt r
            WHERE r.customer_id=record_receipt.customer_id AND r.id<>v_id
              AND r.reference=nullif(btrim(record_receipt.reference),'')));
    RETURN sokhach._finish_command(customer_id,idempotency_key,v_payload,v_result);
END $$;

CREATE OR REPLACE FUNCTION sokhach.get_receivables_detail(p_customer bigint, p_month date) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, sokhach, pg_temp AS $$
-- Ngăn kéo ma trận (29/10/2026): số tháng lấy đúng dòng Tổng tháng của get_ledger (DA-THU-01: tháng
-- sổ gốc dùng phát sinh/đã thu Sheet, đã thu theo ngày thu), danh sách gồm chuyến web và dòng chuyến
-- sổ gốc. outstanding_vnd là ô ma trận (nợ còn lại sau phân bổ nợ cũ trước); allocated_vnd là thu đã
-- phân bổ vào kỳ, để giải thích vì sao phát sinh − đã thu có thể khác còn lại. receipts (29/10/2026): phiếu
-- thu chưa hủy có ngày thu trong tháng, kèm các kỳ đang được trừ (dòng phân bổ hiệu lực).
-- credit_applied_vnd (CAN-DU-01, 30/10/2026): số thô − ô ma trận; dương là khoản dư tháng khác cấn vào tháng
-- này, âm là khoản dư của tháng này đã cấn sang tháng còn nợ.
DECLARE v_active boolean; v_ledger jsonb; v_row jsonb; v_allocated bigint; v_opening boolean;
        v_raw bigint; v_month text := p_month::text;
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
    SELECT coalesce(sum(outstanding_vnd),0) INTO v_raw FROM sokhach.v_outstanding_month_raw
      WHERE customer_id=p_customer AND debt_month=p_month;
    RETURN jsonb_build_object('status','active','customer_id',p_customer,'month',v_month,
        'outstanding_vnd',coalesce(v_row->>'outstanding_vnd','0'),
        'charges_vnd',coalesce(v_row->>'charges_vnd','0'),'received_vnd',coalesce(v_row->>'received_vnd','0'),
        'allocated_vnd',v_allocated::text,'opening',v_opening,
        'credit_applied_vnd',(v_raw-coalesce((v_row->>'outstanding_vnd')::bigint,0))::text,
        'receipts',(SELECT coalesce(jsonb_agg(jsonb_build_object('id',r->'id','pid',r->'pid','date',r->'date',
            'method',r->'method','reference',r->'reference','amount_vnd',r->'amount_vnd',
            'counterparty_name',r->'counterparty_name',
            'allocations',(SELECT coalesce(jsonb_agg(jsonb_build_object('month',a.month,'kind',a.kind,'amount_vnd',a.amount::text)
                ORDER BY a.month,a.kind),'[]'::jsonb) FROM (SELECT x->>'month' AS month,x->>'kind' AS kind,
                sum((x->>'amount_vnd')::bigint) AS amount FROM jsonb_array_elements(r->'allocations') x
                WHERE x->>'superseded_by_event' IS NULL GROUP BY 1,2) a))
            ORDER BY r->>'date',r->>'pid' COLLATE "C"),'[]'::jsonb)
          FROM jsonb_array_elements(v_ledger->'receipts') r
          WHERE r->>'voided_on' IS NULL AND date_trunc('month',(r->>'date')::date)::date=p_month),
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

-- Hàm đọc nhiều khách nối view cấn dư; thiếu thống kê thì planner tính lại view cho từng khách (đo 30/10/2026:
-- ma trận 250 khách 45ms có thống kê, 750ms không có). Làm mới thống kê các bảng sokhach ngay sau khi đổi view.
DO $$
DECLARE r regclass;
BEGIN
    FOR r IN SELECT c.oid::regclass FROM pg_class c WHERE c.relnamespace='sokhach'::regnamespace AND c.relkind IN ('r','p')
    LOOP EXECUTE format('ANALYZE %s', r); END LOOP;
END $$;

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM can_du_before b FULL JOIN (SELECT customer_id,sum(outstanding_vnd)::numeric AS total_vnd
            FROM sokhach.v_outstanding_month GROUP BY customer_id) a USING (customer_id)
        WHERE a.total_vnd IS DISTINCT FROM b.total_vnd)
    OR EXISTS (SELECT 1 FROM (SELECT customer_id,sum(outstanding_vnd)::numeric AS total_vnd
            FROM sokhach.v_outstanding_month_raw GROUP BY customer_id) r FULL JOIN (SELECT customer_id,
            sum(outstanding_vnd)::numeric AS total_vnd FROM sokhach.v_outstanding_month GROUP BY customer_id) a
            USING (customer_id) WHERE a.total_vnd IS DISTINCT FROM r.total_vnd)
    THEN RAISE EXCEPTION 'CAN_DU_TOTAL_MISMATCH'; END IF;
    IF EXISTS (SELECT 1 FROM sokhach.v_outstanding_month v GROUP BY v.customer_id
        HAVING bool_or(v.outstanding_vnd>0) AND bool_or(v.outstanding_vnd<0))
    THEN RAISE EXCEPTION 'CAN_DU_CREDIT_LEFT'; END IF;
END $$;
COMMIT;
