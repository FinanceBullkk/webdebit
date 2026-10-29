-- Rà đường ghi tiền 29/10/2026 (docs/decisions: FUTURE-01, V7-SO, BANG-GIA-01): chỉ thay thân hàm, không đổi bảng,
-- ràng buộc, loại event, dữ liệu hay quyền. Chạy sau 2026-10-29-v7-matrix-drawer-receipts.sql. Chạy lại được.
-- 1. paste_trips: ngày xe nhập kho không được sau hôm nay (giờ VN) — FUTURE_DATE, cùng luật với sửa ngày tại ô.
-- 2. record_receipt: phân bổ lại mọi phiếu chưa hủy theo (ngày, mã phiếu) ngay khi ghi; tổng từng tháng không đổi.
-- 3. apply_price_table: không ghi đè đơn giá gõ tay — PRICE_TYPED_PRICE.
-- 4. Đồng bộ ba hàm Sheet (list_sheet_trip_refs, guard_sheet_cross_customer, resolve_sheet_conflict) với file chuẩn:
--    thân hàm giữ nguyên bản migration 24/10 và 27/10, nên DB đã có là không đổi; DB thiếu thì được bổ sung.
BEGIN;
SET LOCAL ROLE sokhach_owner;
CREATE OR REPLACE FUNCTION sokhach.paste_trips(customer_id bigint, expected_version bigint,
    idempotency_key text, debt_month date, trips jsonb) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, sokhach, pg_temp AS $$
DECLARE v_payload jsonb := jsonb_build_object('command','paste_trips','month',debt_month,'trips',trips);
        v_retry jsonb; v_actor text; v_ids jsonb := '[]'::jsonb;
        v_item jsonb; v_fee_item jsonb; v_id bigint; v_event bigint; v_rows jsonb := '[]'::jsonb;
        v_changes jsonb; v_date date; v_unit bigint; v_fee bigint; v_fee_total numeric; v_date_text text;
        v_fee_only boolean; v_cutover bigint; v_booking text; v_container text;
        v_reason text; v_pending jsonb := '[]';
BEGIN
    v_retry := sokhach._begin_command(customer_id,expected_version,idempotency_key,v_payload);
    IF v_retry IS NOT NULL THEN RETURN v_retry; END IF;
    PERFORM sokhach._baseline(customer_id);
    SELECT cc.cutover_id INTO v_cutover FROM sokhach.cutover_customer cc
        JOIN sokhach.cutover c ON c.id=cc.cutover_id
        WHERE cc.customer_id=paste_trips.customer_id AND cc.status='active' AND c.status='active';
    IF NOT EXISTS (SELECT 1 FROM sokhach.baseline_trip_ref WHERE cutover_id=v_cutover)
    THEN RAISE EXCEPTION 'BASELINE_REF_MISSING'; END IF;
    IF debt_month IS NULL OR extract(day FROM debt_month)<>1 THEN RAISE EXCEPTION 'INVALID_COMMAND'; END IF;
    IF jsonb_typeof(trips) IS DISTINCT FROM 'array' OR jsonb_array_length(trips)=0
    THEN RAISE EXCEPTION 'INVALID_TRIPS'; END IF;
    FOR v_item IN SELECT value FROM jsonb_array_elements(trips) LOOP
        IF v_item ? 'fees' AND (jsonb_typeof(v_item->'fees')<>'array' OR v_item->>'otherFeeVnd' IS NOT NULL)
        THEN RAISE EXCEPTION 'INVALID_TRIP_INPUT'; END IF;
        v_fee_only := nullif(v_item->>'container','') IS NULL
            AND v_item->>'unitPriceVnd' IS NULL
            AND (v_item->>'otherFeeVnd' IS NOT NULL
              OR (v_item ? 'fees' AND jsonb_array_length(v_item->'fees')>0));
        IF jsonb_typeof(v_item) <> 'object'
           OR (NOT v_fee_only AND (v_item->>'container' IS NULL
             OR nullif(btrim(v_item->>'carrier'),'') IS NULL
             OR nullif(btrim(v_item->>'from'),'') IS NULL
             OR nullif(btrim(v_item->>'to'),'') IS NULL))
        THEN RAISE EXCEPTION 'INVALID_TRIP'; END IF;
        v_date_text := v_item->>'date';
        IF v_item->>'unitPriceVnd'='-0' OR v_item->>'otherFeeVnd'='-0'
        THEN RAISE EXCEPTION 'INVALID_VND'; END IF;
        IF (v_date_text IS NULL AND NOT v_fee_only)
           OR (v_date_text IS NOT NULL AND v_date_text !~ '^[0-9]{2}/[0-9]{2}/[0-9]{4}$')
           OR (v_item->>'unitPriceVnd' IS NOT NULL AND (v_item->>'unitPriceVnd') !~ '^[0-9]+$')
           OR (v_item->>'otherFeeVnd' IS NOT NULL AND (v_item->>'otherFeeVnd') !~ '^-?[0-9]+$')
        THEN RAISE EXCEPTION 'INVALID_TRIP_INPUT'; END IF;
        v_date := CASE WHEN v_date_text IS NULL THEN NULL ELSE to_date(v_date_text,'DD/MM/YYYY') END;
        IF v_date_text IS NOT NULL AND to_char(v_date,'DD/MM/YYYY') <> v_date_text
        THEN RAISE EXCEPTION 'INVALID_TRIP_DATE'; END IF;
        -- FUTURE-01 áp vào V7 (29/10/2026): ngày xe nhập kho khi dán không được sau hôm nay giờ VN,
        -- cùng luật với sửa ngày tại ô (_trip_date); chuyến đồng bộ từ Sheet cũng đi qua đây.
        IF v_date > (clock_timestamp() AT TIME ZONE 'Asia/Ho_Chi_Minh')::date
        THEN RAISE EXCEPTION 'FUTURE_DATE'; END IF;
        BEGIN
            v_unit := (v_item->>'unitPriceVnd')::bigint;
            v_fee := (v_item->>'otherFeeVnd')::bigint;
        EXCEPTION WHEN numeric_value_out_of_range THEN RAISE EXCEPTION 'INVALID_VND'; END;
        v_fee_total:=coalesce(v_fee,0);
        IF v_item ? 'fees' THEN
          FOR v_fee_item IN SELECT value FROM jsonb_array_elements(v_item->'fees') LOOP
            IF jsonb_typeof(v_fee_item) NOT IN ('string','number')
              OR v_fee_item#>>'{}' !~ '^-?[0-9]+$'
            THEN RAISE EXCEPTION 'INVALID_TRIP_INPUT'; END IF;
            BEGIN v_fee:=(v_fee_item#>>'{}')::bigint;
            EXCEPTION WHEN numeric_value_out_of_range THEN RAISE EXCEPTION 'INVALID_VND'; END;
            IF v_fee=0 THEN RAISE EXCEPTION 'FEE_AMOUNT_INVALID'; END IF;
            v_fee_total:=v_fee_total+v_fee;
          END LOOP;
        END IF;
        -- ponytail: cap is signed bigint until business VND limit is decided.
        IF v_unit < 0 OR v_fee_total NOT BETWEEN -9223372036854775808 AND 9223372036854775807 OR
           coalesce(v_unit,0)::numeric+v_fee_total NOT BETWEEN -9223372036854775808 AND 9223372036854775807
        THEN RAISE EXCEPTION 'INVALID_VND'; END IF;
        v_reason := NULL;
        IF NOT v_fee_only THEN
            v_container := sokhach._normalize_key(v_item->>'container');
            v_booking := sokhach._booking_key(v_item->>'booking',v_container,v_date);
            IF EXISTS (SELECT 1 FROM sokhach.baseline_trip_ref r WHERE r.cutover_id=v_cutover
                AND r.booking_norm=v_booking AND r.container_norm=v_container)
            THEN v_reason := 'BASELINE_CODE_MATCH';
            ELSIF EXISTS (SELECT 1 FROM sokhach.baseline_trip_ref r WHERE r.cutover_id=v_cutover
                AND r.container_norm=v_container AND abs(r.event_date-v_date)<=3)
            THEN v_reason := 'BASELINE_DATE_WINDOW';
            ELSIF EXISTS (SELECT 1 FROM sokhach.v_trip_current t WHERE NOT t.deleted AND t.customer_id=paste_trips.customer_id
                AND sokhach._normalize_key(t.container)=v_container
                AND (sokhach._booking_key(t.booking,t.container,t.event_date)=v_booking
                    OR abs(t.event_date-v_date)<=3))
            THEN v_reason := 'WEB_DUPLICATE';
            ELSIF EXISTS (SELECT 1 FROM jsonb_array_elements(v_rows) r
                WHERE sokhach._normalize_key(r->>'container')=v_container
                AND (sokhach._booking_key(r->>'booking',r->>'container',(r->>'event_date')::date)=v_booking
                    OR abs((r->>'event_date')::date-v_date)<=3))
            THEN v_reason := 'BATCH_DUPLICATE'; END IF;
        END IF;
        v_id := nextval(pg_get_serial_sequence('sokhach.trip','id'));
        IF v_reason IS NOT NULL THEN
            v_pending := v_pending || jsonb_build_array(jsonb_build_object('trip_id',v_id,'reason',v_reason));
        END IF;
        v_ids := v_ids || jsonb_build_array(v_id);
        v_rows := v_rows || jsonb_build_array(v_item || jsonb_build_object(
            'trip_id',v_id,'debt_month',coalesce(date_trunc('month',v_date)::date,debt_month),'event_date',v_date,
            'status',CASE WHEN v_reason IS NULL THEN 'confirmed' ELSE 'pending_review' END)
            || CASE WHEN v_reason IS NULL THEN '{}'::jsonb ELSE jsonb_build_object('review_reason',v_reason) END);
    END LOOP;
    v_actor := sokhach._actor();
    INSERT INTO sokhach.event(customer_id,kind,actor,"before","after",idempotency_key)
    VALUES (customer_id,'paste',v_actor,'{}',jsonb_build_object('trips',v_rows),idempotency_key)
    RETURNING id INTO v_event;
    FOR v_item IN SELECT value FROM jsonb_array_elements(v_rows) LOOP
        INSERT INTO sokhach.trip(id,customer_id,debt_month,event_date,container,carrier,shipper,
            origin,destination,note,source_ref,created_by_event,booking,status) OVERRIDING SYSTEM VALUE
        VALUES ((v_item->>'trip_id')::bigint,customer_id,(v_item->>'debt_month')::date,(v_item->>'event_date')::date,
            v_item->>'container',v_item->>'carrier',v_item->>'shipper',v_item->>'from',v_item->>'to',
            v_item->>'note',v_item->>'src',v_event,v_item->>'booking',v_item->>'status');
        INSERT INTO sokhach.trip_price_rev(trip_id,customer_id,unit_price_vnd,created_by_event)
        VALUES ((v_item->>'trip_id')::bigint,customer_id,(v_item->>'unitPriceVnd')::bigint,v_event);
        IF v_item ? 'fees' THEN
          FOR v_fee_item IN SELECT value FROM jsonb_array_elements(v_item->'fees') LOOP
            v_fee:=(v_fee_item#>>'{}')::bigint;
            INSERT INTO sokhach.trip_fee_line(customer_id,trip_id,fee_type_id,amount_vnd,created_by_event)
            SELECT customer_id,(v_item->>'trip_id')::bigint,id,v_fee,v_event FROM sokhach.fee_type
            WHERE system_key=CASE WHEN v_fee<0 THEN 'discount' ELSE 'other' END;
          END LOOP;
        ELSE
          v_fee := (v_item->>'otherFeeVnd')::bigint;
          IF v_fee IS NOT NULL AND v_fee<>0 THEN
              INSERT INTO sokhach.trip_fee_line(customer_id,trip_id,fee_type_id,amount_vnd,created_by_event)
              SELECT customer_id,(v_item->>'trip_id')::bigint,id,v_fee,v_event FROM sokhach.fee_type
              WHERE system_key=CASE WHEN v_fee<0 THEN 'discount' ELSE 'other' END;
          END IF;
        END IF;
        PERFORM sokhach._sync_trip_fee((v_item->>'trip_id')::bigint,v_event);
    END LOOP;
    v_changes := sokhach.reallocate(customer_id,idempotency_key);
    RETURN sokhach._finish_command(customer_id,idempotency_key,v_payload,
        jsonb_build_object('trip_ids',v_ids,'reallocated',v_changes,'pending_review',v_pending));
END $$;

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
    FOR v_month,v_due IN SELECT debt_month,outstanding_vnd FROM sokhach.v_outstanding_month
        WHERE v_outstanding_month.customer_id=record_receipt.customer_id ORDER BY debt_month
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

CREATE OR REPLACE FUNCTION sokhach.apply_price_table(customer_id bigint,expected_version bigint,idempotency_key text,
 trip_ids jsonb) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,sokhach,pg_temp AS $$
DECLARE v_payload jsonb:=jsonb_build_object('command','apply_price_table','trip_ids',trip_ids);
 v_retry jsonb; v_id bigint; t sokhach.v_trip_current%ROWTYPE; v_old sokhach.trip_price_rev%ROWTYPE;
 v_lookup jsonb; v_before jsonb:='[]'; v_after jsonb:='[]'; v_item jsonb; v_event bigint; v_rev bigint; v_changes jsonb;
 v_from jsonb;
BEGIN
 v_retry:=sokhach._begin_command(customer_id,expected_version,idempotency_key,v_payload);
 IF v_retry IS NOT NULL THEN RETURN v_retry; END IF;
 PERFORM sokhach._baseline(customer_id);
 IF jsonb_typeof(trip_ids) IS DISTINCT FROM 'array' OR jsonb_array_length(trip_ids) NOT BETWEEN 1 AND 500
   OR EXISTS (SELECT 1 FROM jsonb_array_elements(trip_ids) x WHERE jsonb_typeof(x)<>'number' OR x::text !~ '^[1-9][0-9]{0,18}$')
   OR (SELECT count(*)<>count(DISTINCT x::text) FROM jsonb_array_elements(trip_ids) x)
 THEN RAISE EXCEPTION 'INVALID_TRIPS'; END IF;
 -- BANG-GIA-01 (29/10/2026): gõ tay thắng bảng giá. Chỉ ghi chuyến chưa có đơn giá hoặc đang mang đơn giá do
 -- bảng ghi (áp lại); đơn giá gõ tay không bị bảng ghi đè, kể cả khi client gửi nhầm.
 SELECT coalesce(jsonb_object_agg(x.trip_id::text,x.from_table),'{}') INTO v_from
   FROM sokhach._price_trip_rows(apply_price_table.customer_id) x;
 FOR v_id IN SELECT x::text::bigint FROM jsonb_array_elements(trip_ids) x ORDER BY 1 LOOP
   SELECT * INTO t FROM sokhach.v_trip_current v WHERE v.id=v_id AND v.customer_id=apply_price_table.customer_id AND NOT v.deleted;
   IF NOT FOUND OR coalesce(t.container,'')='' THEN RAISE EXCEPTION 'TRIP_NOT_FOUND'; END IF;
   IF t.status<>'confirmed' THEN RAISE EXCEPTION 'TRIP_PENDING_REVIEW'; END IF;
   PERFORM sokhach._month_open(customer_id,t.debt_month,clock_timestamp());
   v_lookup:=sokhach._lookup_price(customer_id,t.event_date,t.origin,t.shipper);
   IF NOT v_lookup ? 'unit_price_vnd' THEN RAISE EXCEPTION 'PRICE_NOT_FOUND'; END IF;
   SELECT * INTO v_old FROM sokhach.trip_price_rev r WHERE r.trip_id=v_id ORDER BY r.id DESC LIMIT 1;
   IF v_old.unit_price_vnd::text IS NOT DISTINCT FROM v_lookup->>'unit_price_vnd' THEN RAISE EXCEPTION 'NO_CHANGE'; END IF;
   IF v_old.unit_price_vnd IS NOT NULL AND NOT coalesce((v_from->>v_id::text)::boolean,false)
   THEN RAISE EXCEPTION 'PRICE_TYPED_PRICE'; END IF;
   v_before:=v_before||jsonb_build_array(jsonb_build_object('trip_id',v_id,'container',t.container,
     'unit_price_vnd',v_old.unit_price_vnd::text,'other_fee_vnd',v_old.other_fee_vnd::text));
   v_after:=v_after||jsonb_build_array(jsonb_build_object('trip_id',v_id,'container',t.container,
     'unit_price_vnd',v_lookup->>'unit_price_vnd','other_fee_vnd',v_old.other_fee_vnd::text,'rate',v_lookup));
 END LOOP;
 INSERT INTO sokhach.event(customer_id,kind,actor,"before","after",idempotency_key)
 VALUES(customer_id,'price_table_apply',sokhach._actor(),jsonb_build_object('trips',v_before),
   jsonb_build_object('trips',v_after),idempotency_key) RETURNING id INTO v_event;
 FOR v_item IN SELECT x FROM jsonb_array_elements(v_after) x LOOP
   INSERT INTO sokhach.trip_price_rev(trip_id,customer_id,unit_price_vnd,created_by_event)
   VALUES((v_item->>'trip_id')::bigint,customer_id,(v_item->>'unit_price_vnd')::bigint,v_event)
   RETURNING id INTO v_rev;
   INSERT INTO sokhach.trip_price_source(price_rev_id,customer_id,rate,created_by_event)
   VALUES(v_rev,customer_id,v_item->'rate',v_event);
   -- Phụ phí chỉ do _sync_trip_fee ghi lại từ dòng phụ phí (PHU-PHI-01), như edit_trip_price.
   PERFORM sokhach._sync_trip_fee((v_item->>'trip_id')::bigint,v_event);
 END LOOP;
 v_changes:=sokhach.reallocate(customer_id,idempotency_key);
 RETURN sokhach._finish_command(customer_id,idempotency_key,v_payload,
   jsonb_build_object('event_id',v_event,'trips',v_after,'reallocated',v_changes));
END $$;

CREATE OR REPLACE FUNCTION sokhach.list_sheet_trip_refs() RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, sokhach, pg_temp AS $$
BEGIN
    PERFORM sokhach._actor();
    RETURN (SELECT jsonb_build_object('items',coalesce(jsonb_agg(
        jsonb_build_object('customer_id',customer_id,'container',container)
        ORDER BY customer_id,id),'[]'::jsonb))
    FROM sokhach.v_trip_current WHERE NOT deleted AND container IS NOT NULL);
END;
$$;

CREATE OR REPLACE FUNCTION sokhach.guard_sheet_cross_customer() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, sokhach, pg_temp AS $$
DECLARE v_container text;
BEGIN
    IF NEW.source_ref IS NULL OR NEW.source_ref !~ '^sheet:[0-9a-f]{64}:[0-9]+$' THEN RETURN NEW; END IF;
    v_container := sokhach._normalize_key(NEW.container);
    PERFORM pg_advisory_xact_lock(746193,hashtext(v_container));
    IF EXISTS (SELECT 1 FROM sokhach.v_trip_current t WHERE NOT t.deleted
        AND t.customer_id<>NEW.customer_id
        AND sokhach._normalize_key(t.container)=v_container
        AND (sokhach._booking_key(t.booking,t.container,t.event_date)=
             sokhach._booking_key(NEW.booking,NEW.container,NEW.event_date)
             OR abs(t.event_date-NEW.event_date)<=3))
    THEN RAISE EXCEPTION 'SHEET_CROSS_CUSTOMER_MATCH'; END IF;
    RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS trip_sheet_cross_customer ON sokhach.trip;
CREATE TRIGGER trip_sheet_cross_customer BEFORE INSERT ON sokhach.trip
FOR EACH ROW EXECUTE FUNCTION sokhach.guard_sheet_cross_customer();
CREATE OR REPLACE FUNCTION sokhach.resolve_sheet_conflict(
    customer_id bigint, expected_version bigint, idempotency_key text,
    snapshot_sha256 text, source_row bigint, target_kind text, target_id bigint,
    field text, target_value text, sheet_value text, decision text
) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,sokhach,pg_temp AS $$
DECLARE v_payload jsonb := jsonb_build_object('command','resolve_sheet_conflict',
        'snapshot_sha256',snapshot_sha256,'source_row',source_row,'target_kind',target_kind,
        'target_id',target_id,'field',field,'target_value',target_value,
        'sheet_value',sheet_value,'decision',decision);
    v_retry jsonb; v_trip sokhach.v_trip_current%ROWTYPE; v_legacy jsonb;
    v_event bigint; v_before text; v_after text;
BEGIN
    v_retry := sokhach._begin_command(customer_id,expected_version,idempotency_key,v_payload);
    IF v_retry IS NOT NULL THEN RETURN v_retry; END IF;
    PERFORM sokhach._baseline(customer_id);
    IF snapshot_sha256 !~ '^[0-9a-f]{64}$' OR source_row <= 0 OR target_id <= 0
       OR target_kind NOT IN ('trip','legacy')
       OR field NOT IN ('carrier','shipper','origin','destination','event_date','booking')
       OR decision NOT IN ('keep_web','use_sheet') OR sheet_value IS NULL
       -- Date edits must use the normal edit path; posted booking never changes.
       OR (field IN ('event_date','booking') AND decision<>'keep_web')
       OR (field='booking' AND target_kind<>'trip') THEN
        RAISE EXCEPTION 'INVALID_SHEET_RESOLUTION';
    END IF;
    IF target_kind='trip' THEN
        SELECT * INTO v_trip FROM sokhach.v_trip_current t
          WHERE t.id=target_id AND t.customer_id=resolve_sheet_conflict.customer_id AND NOT t.deleted;
        IF NOT FOUND THEN RAISE EXCEPTION 'TRIP_NOT_FOUND'; END IF;
        v_before:=to_jsonb(v_trip)->>field;
    ELSE
        SELECT sokhach._legacy_current(l.id) INTO v_legacy FROM sokhach.legacy_row l
          JOIN sokhach.cutover_customer cc USING(customer_id,cutover_id)
          JOIN sokhach.cutover c ON c.id=cc.cutover_id
          WHERE l.id=target_id AND l.customer_id=resolve_sheet_conflict.customer_id
            AND l.kind='trip' AND cc.status='active' AND c.status='active';
        IF NOT FOUND OR (v_legacy->>'deleted')::boolean THEN RAISE EXCEPTION 'LEGACY_NOT_FOUND'; END IF;
        v_before:=CASE WHEN field='shipper' THEN coalesce(v_legacy->>'shipper',v_legacy->>'carrier')
          ELSE v_legacy->>field END;
    END IF;
    IF v_before IS DISTINCT FROM target_value THEN RAISE EXCEPTION 'STALE_LEDGER'; END IF;
    IF decision='use_sheet' AND nullif(btrim(sheet_value),'') IS NULL THEN
        RAISE EXCEPTION 'INVALID_SHEET_RESOLUTION';
    END IF;
    IF decision='use_sheet' THEN
        PERFORM sokhach._month_open(customer_id,CASE WHEN target_kind='trip' THEN v_trip.debt_month
          ELSE (v_legacy->>'debt_month')::date END,clock_timestamp());
    END IF;
    v_after:=CASE WHEN decision='use_sheet' THEN btrim(sheet_value) ELSE v_before END;
    INSERT INTO sokhach.event(customer_id,kind,actor,"before","after",idempotency_key)
      VALUES(customer_id,'sheet_conflict_resolved',sokhach._actor(),
        jsonb_build_object('target',jsonb_build_object('kind',target_kind,'id',target_id),
          'field',field,'value',v_before),
        jsonb_build_object('snapshot_sha256',snapshot_sha256,'source_row',source_row,
          'target',jsonb_build_object('kind',target_kind,'id',target_id),
          'field',field,'sheet_value',sheet_value,'target_value',v_after,'decision',decision),
        idempotency_key) RETURNING id INTO v_event;
    IF decision='use_sheet' THEN
      IF target_kind='trip' THEN
        INSERT INTO sokhach.trip_info_rev(trip_id,customer_id,debt_month,event_date,container,
          carrier,shipper,origin,destination,status,created_by_event)
        VALUES(v_trip.id,customer_id,v_trip.debt_month,v_trip.event_date,v_trip.container,
          CASE WHEN field='carrier' THEN v_after ELSE v_trip.carrier END,
          CASE WHEN field='shipper' THEN v_after ELSE v_trip.shipper END,
          CASE WHEN field='origin' THEN v_after ELSE v_trip.origin END,
          CASE WHEN field='destination' THEN v_after ELSE v_trip.destination END,
          v_trip.status,v_event);
      ELSE
        v_legacy:=v_legacy||jsonb_build_object(field,v_after);
        INSERT INTO sokhach.legacy_trip_rev(legacy_row_id,customer_id,debt_month,event_date,
          container,carrier,shipper,origin,destination,unit_price_vnd,other_fee_vnd,
          deleted,counted_vnd,created_by_event)
        VALUES(target_id,customer_id,(v_legacy->>'debt_month')::date,
          (v_legacy->>'event_date')::date,v_legacy->>'container',v_legacy->>'carrier',
          v_legacy->>'shipper',v_legacy->>'origin',v_legacy->>'destination',
          (v_legacy->>'unit_price_vnd')::bigint,(v_legacy->>'other_fee_vnd')::bigint,
          false,(v_legacy->>'counted_vnd')::bigint,v_event);
      END IF;
    END IF;
    RETURN sokhach._finish_command(customer_id,idempotency_key,v_payload,
      jsonb_build_object('resolved',true,'field',field,'decision',decision));
END $$;

REVOKE ALL ON FUNCTION sokhach.list_sheet_trip_refs() FROM PUBLIC,sokhach_reader;
GRANT EXECUTE ON FUNCTION sokhach.list_sheet_trip_refs() TO sokhach_app;
REVOKE ALL ON FUNCTION sokhach.guard_sheet_cross_customer() FROM PUBLIC,sokhach_app,sokhach_reader;
REVOKE ALL ON FUNCTION sokhach.resolve_sheet_conflict(bigint,bigint,text,text,bigint,text,bigint,text,text,text,text) FROM PUBLIC,sokhach_reader;
GRANT EXECUTE ON FUNCTION sokhach.resolve_sheet_conflict(bigint,bigint,text,text,bigint,text,bigint,text,text,text,text) TO sokhach_app;
COMMIT;
