-- Tách phụ phí theo bảng PS (specs/v7-phu-phi-tu-ps.md): lệnh rewrite_trip_fees giữ nguyên tổng phụ phí.
-- Chỉ thêm hàm và loại event; không đổi tiền, phân bổ, khóa tháng hay hàm cũ. Áp sau 2026-10-29-v7-chung-tu.sql
-- (ràng buộc event gồm mọi loại tới CHUNG-TU-01). Chạy lại được. Không chạy trên hao khi chưa có lệnh người dùng.
BEGIN;
SET LOCAL ROLE sokhach_owner;
ALTER TABLE sokhach.event DROP CONSTRAINT event_kind_check;
ALTER TABLE sokhach.event ADD CONSTRAINT event_kind_check CHECK (kind IN ('paste', 'price_edit', 'adjust_trip',
        'adjust_month', 'receipt', 'receipt_edit', 'void', 'reallocation', 'month_lock', 'import',
        'customer_attr', 'trip_review', 'trip_edit', 'trip_delete', 'legacy_edit', 'legacy_delete',
        'sheet_conflict_resolved', 'fee_migration', 'add_trip_fees', 'set_trip_fee_type', 'replace_trip_fee', 'void_trip_fee', 'set_book_fee_columns',
        'price_table_edit', 'price_table_apply', 'receipt_image', 'receipt_image_remove', 'adjust_month_delete',
        'rewrite_trip_fees'));
ALTER TABLE sokhach.event DROP CONSTRAINT event_snapshot_check;
ALTER TABLE sokhach.event ADD CONSTRAINT event_snapshot_check CHECK (CASE kind
        WHEN 'paste' THEN "before" = '{}'::jsonb AND "after" ? 'trips'
        WHEN 'receipt' THEN "before" = '{}'::jsonb AND "after" ? 'receipt'
        WHEN 'import' THEN "before" = '{}'::jsonb AND "after" ? 'cutover'
        WHEN 'price_edit' THEN "before" ? 'price' AND "after" ? 'price'
        WHEN 'adjust_trip' THEN "before" ? 'trip' AND "after" ? 'adjustment'
        WHEN 'adjust_month' THEN "before" ? 'month' AND "after" ? 'adjustment'
        WHEN 'receipt_edit' THEN "before" ? 'receipt' AND "after" ? 'receipt'
        WHEN 'month_lock' THEN coalesce("before"->>'month' = "after"->>'month'
            AND jsonb_typeof("before"->'locked')='boolean'
            AND jsonb_typeof("after"->'locked')='boolean',false)
        WHEN 'void' THEN "before" ? 'receipt' AND "after" ? 'receipt'
        WHEN 'reallocation' THEN "before" ? 'allocations' AND "after" ? 'allocations'
        WHEN 'customer_attr' THEN "before" ? 'customer' AND "after" ? 'customer'
        WHEN 'trip_edit' THEN "before" ? 'trip' AND "after" ? 'trip'
        WHEN 'legacy_edit' THEN "before" ? 'legacy' AND "after" ? 'legacy'
        WHEN 'trip_delete' THEN "before" ? 'trip' AND coalesce("after"->'trip'->'deleted'='true'::jsonb,false)
        WHEN 'legacy_delete' THEN "before" ? 'legacy' AND coalesce("after"->'legacy'->'deleted'='true'::jsonb,false)
        WHEN 'trip_review' THEN "before"->>'status' = 'pending_review' AND "after" ? 'trip'
            AND "after"->>'status' IN ('confirmed','rejected') AND btrim(coalesce("after"->>'review_reason','')) <> ''
        WHEN 'sheet_conflict_resolved' THEN "before" ? 'target' AND "before" ? 'field'
            AND "after" ? 'target' AND "after" ? 'field' AND "after" ? 'source_row'
            AND "after" ? 'sheet_value' AND "after" ? 'decision'
        WHEN 'fee_migration' THEN "before" = '{}'::jsonb AND "after" ? 'trip_count' AND "after" ? 'legacy_count'
        WHEN 'add_trip_fees' THEN "before" ? 'targets' AND "after" ? 'targets'
        WHEN 'set_trip_fee_type' THEN "before" ? 'targets' AND "after" ? 'targets'
        WHEN 'replace_trip_fee' THEN "before" ? 'targets' AND "after" ? 'targets'
        WHEN 'void_trip_fee' THEN "before" ? 'targets' AND "after" ? 'targets'
        WHEN 'set_book_fee_columns' THEN "before" ? 'fee_columns' AND "after" ? 'fee_columns'
        WHEN 'price_table_edit' THEN "before" ? 'price_table' AND "after" ? 'price_table'
        WHEN 'price_table_apply' THEN "before" ? 'trips' AND "after" ? 'trips'
        WHEN 'receipt_image' THEN "before" = '{}'::jsonb AND "after" ? 'image'
        WHEN 'receipt_image_remove' THEN "before" ? 'image' AND "after" ? 'image'
        WHEN 'adjust_month_delete' THEN "before" ? 'adjustment' AND coalesce("after"->'adjustment'->'deleted'='true'::jsonb,false)
        WHEN 'rewrite_trip_fees' THEN "before" ? 'targets' AND "after" ? 'targets' AND "after" ? 'source'
        ELSE false END);
CREATE OR REPLACE FUNCTION sokhach._rewrite_trip_fees(p_customer bigint,p_version bigint,p_key text,
 p_target jsonb,p_expected jsonb,p_lines jsonb,p_source jsonb) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,sokhach,pg_temp AS $$
DECLARE v_payload jsonb:=jsonb_build_object('command','rewrite_trip_fees','target',p_target,
 'expected_line_ids',p_expected,'lines',p_lines,'source',p_source);
 v_retry jsonb; v_before jsonb; v_after jsonb; v_line jsonb; v_new jsonb:='[]'; v_type sokhach.fee_type%ROWTYPE;
 v_amount bigint; v_old_total bigint; v_new_total bigint:=0; v_event bigint; v_trip bigint; v_legacy bigint;
BEGIN
 BEGIN v_retry:=sokhach._begin_command(p_customer,p_version,p_key,v_payload);
 EXCEPTION WHEN raise_exception THEN
   IF SQLERRM='STALE_LEDGER' THEN RAISE EXCEPTION 'VERSION_CONFLICT'; ELSE RAISE; END IF;
 END;
 IF v_retry IS NOT NULL THEN RETURN v_retry; END IF;
 PERFORM sokhach._baseline(p_customer);
 IF jsonb_typeof(p_expected) IS DISTINCT FROM 'array' OR jsonb_typeof(p_lines) IS DISTINCT FROM 'array'
   OR jsonb_array_length(p_lines) NOT BETWEEN 1 AND 10 OR jsonb_typeof(p_source) IS DISTINCT FROM 'object'
   OR length(p_source::text)>2000 THEN RAISE EXCEPTION 'INVALID_COMMAND'; END IF;
 v_before:=sokhach._fee_target(p_customer,p_target);
 v_trip:=(p_target->>'trip_id')::bigint; v_legacy:=(p_target->>'legacy_row_id')::bigint;
 PERFORM 1 FROM sokhach.trip_fee_line WHERE customer_id=p_customer AND voided_by_event IS NULL
   AND (trip_id=v_trip OR legacy_row_id=v_legacy) FOR UPDATE;
 IF (SELECT coalesce(jsonb_agg((x->>'id')::bigint ORDER BY (x->>'id')::bigint),'[]') FROM jsonb_array_elements(v_before->'fee_lines') x)
   IS DISTINCT FROM (SELECT coalesce(jsonb_agg(x::bigint ORDER BY x::bigint),'[]') FROM jsonb_array_elements_text(p_expected) x)
 THEN RAISE EXCEPTION 'FEE_LINES_CHANGED'; END IF;
 SELECT sum((x->>'amount_vnd')::bigint)::bigint INTO v_old_total FROM jsonb_array_elements(v_before->'fee_lines') x;
 FOR v_line IN SELECT x FROM jsonb_array_elements(p_lines) x LOOP
   IF jsonb_typeof(v_line) IS DISTINCT FROM 'object' OR NOT (v_line ? 'fee_type_id' AND v_line ? 'amount_vnd')
     OR EXISTS(SELECT 1 FROM jsonb_object_keys(v_line) k WHERE k NOT IN ('fee_type_id','amount_vnd','note'))
     OR jsonb_typeof(v_line->'note') NOT IN ('string','null') OR length(v_line->>'note')>2000
   THEN RAISE EXCEPTION 'INVALID_COMMAND'; END IF;
   SELECT * INTO v_type FROM sokhach.fee_type WHERE id=(v_line->>'fee_type_id')::bigint FOR SHARE;
   IF NOT FOUND OR NOT v_type.active THEN RAISE EXCEPTION 'FEE_TYPE_INACTIVE'; END IF;
   IF v_type.system_key='initial' THEN RAISE EXCEPTION 'FEE_TYPE_SYSTEM'; END IF;
   v_amount:=(v_line->>'amount_vnd')::bigint;
   IF v_amount IS NULL OR v_amount=0 THEN RAISE EXCEPTION 'FEE_AMOUNT_INVALID'; END IF;
   IF (v_type.sign='positive' AND v_amount<0) OR (v_type.sign='negative' AND v_amount>0)
   THEN RAISE EXCEPTION 'FEE_SIGN_INVALID'; END IF;
   v_new_total:=v_new_total+v_amount;
   v_new:=v_new||jsonb_build_array(jsonb_build_object('fee_type_id',v_type.id,'amount_vnd',v_amount::text,
     'note',nullif(btrim(coalesce(v_line->>'note','')),'')));
 END LOOP;
 IF v_new_total IS DISTINCT FROM v_old_total THEN RAISE EXCEPTION 'FEE_TOTAL_CHANGED'; END IF;
 IF (SELECT jsonb_agg(x-'id' ORDER BY x->>'fee_type_id',x->>'amount_vnd',x->>'note') FROM jsonb_array_elements(v_before->'fee_lines') x)
   = (SELECT jsonb_agg(x ORDER BY x->>'fee_type_id',x->>'amount_vnd',x->>'note') FROM jsonb_array_elements(v_new) x)
 THEN RAISE EXCEPTION 'NO_CHANGE'; END IF;
 v_after:=v_before||jsonb_build_object('fee_lines',v_new);
 INSERT INTO sokhach.event(customer_id,kind,actor,"before","after",idempotency_key)
 VALUES(p_customer,'rewrite_trip_fees',sokhach._actor(),
   jsonb_build_object('targets',jsonb_build_array(v_before),'batch_count',1,'source',p_source),
   jsonb_build_object('targets',jsonb_build_array(v_after),'batch_count',1,'source',p_source),p_key) RETURNING id INTO v_event;
 UPDATE sokhach.trip_fee_line SET voided_by_event=v_event WHERE customer_id=p_customer AND voided_by_event IS NULL
   AND (trip_id=v_trip OR legacy_row_id=v_legacy);
 INSERT INTO sokhach.trip_fee_line(customer_id,trip_id,legacy_row_id,fee_type_id,amount_vnd,note,created_by_event)
 SELECT p_customer,v_trip,v_legacy,(x->>'fee_type_id')::bigint,(x->>'amount_vnd')::bigint,x->>'note',v_event
 FROM jsonb_array_elements(v_new) x;
 IF v_trip IS NOT NULL THEN PERFORM sokhach._sync_trip_fee(v_trip,v_event); END IF;
 RETURN sokhach._finish_command(p_customer,p_key,v_payload,jsonb_build_object('event_id',v_event,
   'targets',jsonb_build_array(sokhach._fee_target(p_customer,p_target))));
EXCEPTION WHEN numeric_value_out_of_range THEN RAISE EXCEPTION 'FEE_AMOUNT_INVALID';
 WHEN invalid_text_representation THEN RAISE EXCEPTION 'INVALID_COMMAND';
END $$;

CREATE OR REPLACE FUNCTION sokhach.rewrite_trip_fees(customer_id bigint,expected_version bigint,idempotency_key text,
 target jsonb,expected_line_ids jsonb,lines jsonb,source jsonb) RETURNS jsonb
LANGUAGE sql SECURITY DEFINER SET search_path=pg_catalog,sokhach,pg_temp AS $$
 SELECT sokhach._rewrite_trip_fees(customer_id,expected_version,idempotency_key,target,expected_line_ids,lines,source)
$$;

REVOKE ALL ON ALL FUNCTIONS IN SCHEMA sokhach FROM PUBLIC;
REVOKE ALL ON FUNCTION sokhach._rewrite_trip_fees(bigint,bigint,text,jsonb,jsonb,jsonb,jsonb) FROM PUBLIC,sokhach_app,sokhach_reader;
GRANT EXECUTE ON FUNCTION sokhach.rewrite_trip_fees(bigint,bigint,text,jsonb,jsonb,jsonb,jsonb) TO sokhach_app;
COMMIT;
