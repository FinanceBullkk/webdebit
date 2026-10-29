-- PR-B only; apply after PR-A. No data conversion, no production execution here.
BEGIN;
SET LOCAL ROLE sokhach_owner;
ALTER TABLE sokhach.event DROP CONSTRAINT event_kind_check;
ALTER TABLE sokhach.event ADD CONSTRAINT event_kind_check CHECK (kind IN ('paste', 'price_edit', 'adjust_trip',
        'adjust_month', 'receipt', 'receipt_edit', 'void', 'reallocation', 'month_lock', 'import',
        'customer_attr', 'trip_review', 'trip_edit', 'trip_delete', 'legacy_edit', 'legacy_delete',
        'sheet_conflict_resolved', 'fee_migration', 'add_trip_fees', 'set_trip_fee_type', 'replace_trip_fee', 'void_trip_fee', 'set_book_fee_columns'));

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
        ELSE false END);

CREATE OR REPLACE FUNCTION sokhach._fee_lines(p_trip bigint,p_legacy bigint) RETURNS jsonb
LANGUAGE sql STABLE SET search_path=pg_catalog,sokhach,pg_temp AS $$
 SELECT coalesce(jsonb_agg(jsonb_build_object('id',id,'fee_type_id',fee_type_id,
   'amount_vnd',amount_vnd::text,'note',note) ORDER BY id),'[]'::jsonb)
 FROM sokhach.trip_fee_line WHERE voided_by_event IS NULL
   AND (trip_id=p_trip OR legacy_row_id=p_legacy)
$$;

CREATE OR REPLACE FUNCTION sokhach._fee_target(p_customer bigint,p_target jsonb) RETURNS jsonb
LANGUAGE plpgsql SET search_path=pg_catalog,sokhach,pg_temp AS $$
DECLARE t sokhach.v_trip_current%ROWTYPE; l jsonb; v_id bigint; v_month date;
BEGIN
 IF jsonb_typeof(p_target) IS DISTINCT FROM 'object' THEN
   RAISE EXCEPTION 'INVALID_TRIP'; END IF;
 IF (SELECT count(*) FROM jsonb_object_keys(p_target))<>1 OR NOT (p_target ? 'trip_id' OR p_target ? 'legacy_row_id') THEN RAISE EXCEPTION 'INVALID_TRIP'; END IF;
 IF p_target ? 'trip_id' THEN
   SELECT * INTO t FROM sokhach.v_trip_current WHERE id=(p_target->>'trip_id')::bigint
     AND customer_id=p_customer AND NOT deleted;
   IF NOT FOUND THEN RAISE EXCEPTION 'TRIP_NOT_FOUND'; END IF;
   IF t.status<>'confirmed' THEN RAISE EXCEPTION 'TRIP_PENDING_REVIEW'; END IF;
   v_id:=t.id; v_month:=t.debt_month;
 ELSE
   SELECT sokhach._legacy_current(lr.id) INTO l FROM sokhach.legacy_row lr
     JOIN sokhach.cutover_customer cc USING(customer_id,cutover_id)
     JOIN sokhach.cutover c ON c.id=cc.cutover_id
     WHERE lr.id=(p_target->>'legacy_row_id')::bigint AND lr.customer_id=p_customer
       AND lr.kind='trip' AND cc.status='active' AND c.status='active';
   IF l IS NULL OR (l->>'deleted')::boolean THEN RAISE EXCEPTION 'LEGACY_NOT_FOUND'; END IF;
   v_id:=(p_target->>'legacy_row_id')::bigint; v_month:=(l->>'month')::date;
 END IF;
 PERFORM sokhach._month_open(p_customer,v_month,clock_timestamp());
 RETURN p_target||jsonb_build_object('fee_lines',sokhach._fee_lines(t.id,CASE WHEN l IS NOT NULL THEN v_id END),
   'counted_vnd',l->>'counted_vnd');
EXCEPTION WHEN invalid_text_representation OR numeric_value_out_of_range THEN RAISE EXCEPTION 'INVALID_TRIP';
END $$;

-- One customer lock, event, allocation pass and idempotency result per public command.
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
   IF NOT FOUND THEN RAISE EXCEPTION 'TRIP_NOT_FOUND'; END IF;
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

CREATE OR REPLACE FUNCTION sokhach.add_trip_fees(customer_id bigint,expected_version bigint,idempotency_key text,
 targets jsonb,fee_type_id bigint,amount_vnd bigint,note text) RETURNS jsonb
LANGUAGE sql SECURITY DEFINER SET search_path=pg_catalog,sokhach,pg_temp AS $$
 SELECT sokhach._change_trip_fees(customer_id,expected_version,idempotency_key,'add_trip_fees',targets,fee_type_id,amount_vnd,note,NULL)
$$;
CREATE OR REPLACE FUNCTION sokhach.set_trip_fee_type(customer_id bigint,expected_version bigint,idempotency_key text,
 target jsonb,fee_type_id bigint,amount_vnd bigint) RETURNS jsonb
LANGUAGE sql SECURITY DEFINER SET search_path=pg_catalog,sokhach,pg_temp AS $$
 SELECT sokhach._change_trip_fees(customer_id,expected_version,idempotency_key,'set_trip_fee_type',jsonb_build_array(target),fee_type_id,amount_vnd,NULL,NULL)
$$;
CREATE OR REPLACE FUNCTION sokhach.replace_trip_fee(customer_id bigint,expected_version bigint,idempotency_key text,
 fee_line_id bigint,fee_type_id bigint,amount_vnd bigint,note text) RETURNS jsonb
LANGUAGE sql SECURITY DEFINER SET search_path=pg_catalog,sokhach,pg_temp AS $$
 SELECT sokhach._change_trip_fees(customer_id,expected_version,idempotency_key,'replace_trip_fee',NULL,fee_type_id,amount_vnd,note,fee_line_id)
$$;
CREATE OR REPLACE FUNCTION sokhach.void_trip_fee(customer_id bigint,expected_version bigint,idempotency_key text,
 fee_line_id bigint) RETURNS jsonb
LANGUAGE sql SECURITY DEFINER SET search_path=pg_catalog,sokhach,pg_temp AS $$
 SELECT sokhach._change_trip_fees(customer_id,expected_version,idempotency_key,'void_trip_fee',NULL,NULL,NULL,NULL,fee_line_id)
$$;

CREATE OR REPLACE FUNCTION sokhach._change_fee_type(p_key text,p_command text,p_id bigint,p_value text,p_kind text) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,sokhach,pg_temp AS $$
DECLARE v_payload jsonb:=jsonb_build_object('command',p_command,'id',p_id,'value',p_value,'kind',p_kind);
 v_saved sokhach.fee_type_audit%ROWTYPE; v_old sokhach.fee_type%ROWTYPE; v_new sokhach.fee_type%ROWTYPE;
BEGIN
 PERFORM sokhach._actor();
 IF p_key IS NULL OR btrim(p_key)='' OR length(p_key)>128 THEN RAISE EXCEPTION 'INVALID_COMMAND'; END IF;
 -- Serializes both key claims and name uniqueness across add/rename/update.
 PERFORM pg_advisory_xact_lock(771029);
 SELECT * INTO v_saved FROM sokhach.fee_type_audit WHERE idempotency_key=p_key;
 IF FOUND THEN
   IF v_saved.payload IS DISTINCT FROM v_payload THEN RAISE EXCEPTION 'IDEMPOTENCY_CONFLICT'; END IF;
   RETURN v_saved.after_value;
 END IF;
 IF p_command<>'add_fee_type' THEN
   SELECT * INTO v_old FROM sokhach.fee_type WHERE id=p_id FOR UPDATE;
   IF NOT FOUND THEN RAISE EXCEPTION 'FEE_TYPE_INACTIVE'; END IF;
   IF v_old.system_key IS NOT NULL THEN RAISE EXCEPTION 'FEE_TYPE_SYSTEM'; END IF;
 END IF;
 IF p_command IN ('add_fee_type','rename_fee_type') AND
   (p_value IS NULL OR btrim(p_value)='' OR length(p_value)>200) THEN RAISE EXCEPTION 'INVALID_COMMAND'; END IF;
 IF p_command IN ('add_fee_type','set_fee_type_kind') AND
   (p_kind IS NULL OR p_kind NOT IN ('service','pass_through')) THEN RAISE EXCEPTION 'INVALID_COMMAND'; END IF;
 CASE p_command
 WHEN 'add_fee_type' THEN
   INSERT INTO sokhach.fee_type(name,kind,sign,sort) SELECT btrim(p_value),p_kind,'positive',coalesce(max(sort),0)+1
     FROM sokhach.fee_type RETURNING * INTO v_new;
 WHEN 'rename_fee_type' THEN UPDATE sokhach.fee_type SET name=btrim(p_value) WHERE id=p_id RETURNING * INTO v_new;
 WHEN 'set_fee_type_kind' THEN UPDATE sokhach.fee_type SET kind=p_kind WHERE id=p_id RETURNING * INTO v_new;
 WHEN 'set_fee_type_active' THEN
   IF p_value IS NULL OR p_value NOT IN ('true','false') THEN RAISE EXCEPTION 'INVALID_COMMAND'; END IF;
   UPDATE sokhach.fee_type SET active=p_value::boolean WHERE id=p_id RETURNING * INTO v_new;
 ELSE RAISE EXCEPTION 'INVALID_COMMAND'; END CASE;
 INSERT INTO sokhach.fee_type_audit(fee_type_id,actor,payload,before_value,after_value,idempotency_key)
 VALUES(v_new.id,sokhach._actor(),v_payload,coalesce(to_jsonb(v_old),'{}'),to_jsonb(v_new),p_key);
 RETURN to_jsonb(v_new);
EXCEPTION WHEN unique_violation THEN RAISE EXCEPTION 'FEE_TYPE_DUPLICATE';
END $$;
CREATE OR REPLACE FUNCTION sokhach.add_fee_type(idempotency_key text,name text,kind text) RETURNS jsonb
LANGUAGE sql SECURITY DEFINER SET search_path=pg_catalog,sokhach,pg_temp AS $$
 SELECT sokhach._change_fee_type(idempotency_key,'add_fee_type',NULL,name,kind)
$$;
CREATE OR REPLACE FUNCTION sokhach.rename_fee_type(idempotency_key text,fee_type_id bigint,name text) RETURNS jsonb
LANGUAGE sql SECURITY DEFINER SET search_path=pg_catalog,sokhach,pg_temp AS $$
 SELECT sokhach._change_fee_type(idempotency_key,'rename_fee_type',fee_type_id,name,NULL)
$$;
CREATE OR REPLACE FUNCTION sokhach.set_fee_type_kind(idempotency_key text,fee_type_id bigint,kind text) RETURNS jsonb
LANGUAGE sql SECURITY DEFINER SET search_path=pg_catalog,sokhach,pg_temp AS $$
 SELECT sokhach._change_fee_type(idempotency_key,'set_fee_type_kind',fee_type_id,NULL,kind)
$$;
CREATE OR REPLACE FUNCTION sokhach.set_fee_type_active(idempotency_key text,fee_type_id bigint,active boolean) RETURNS jsonb
LANGUAGE sql SECURITY DEFINER SET search_path=pg_catalog,sokhach,pg_temp AS $$
 SELECT sokhach._change_fee_type(idempotency_key,'set_fee_type_active',fee_type_id,active::text,NULL)
$$;
CREATE OR REPLACE FUNCTION sokhach.get_fee_types() RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,sokhach,pg_temp AS $$
BEGIN
 PERFORM sokhach._actor();
 RETURN jsonb_build_object('fee_types',(SELECT coalesce(jsonb_agg(to_jsonb(f)-'name_key' ORDER BY sort,id),'[]') FROM sokhach.fee_type f));
END $$;

CREATE OR REPLACE FUNCTION sokhach.set_book_fee_columns(customer_id bigint,expected_version bigint,idempotency_key text,
 fee_type_ids jsonb) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,sokhach,pg_temp AS $$
DECLARE v_payload jsonb:=jsonb_build_object('command','set_book_fee_columns','fee_type_ids',fee_type_ids);
 v_retry jsonb; v_before jsonb; v_type jsonb; v_seen bigint[]:='{}';
BEGIN
 BEGIN v_retry:=sokhach._begin_command(customer_id,expected_version,idempotency_key,v_payload);
 EXCEPTION WHEN raise_exception THEN
   IF SQLERRM='STALE_LEDGER' THEN RAISE EXCEPTION 'VERSION_CONFLICT'; ELSE RAISE; END IF;
 END;
 IF v_retry IS NOT NULL THEN RETURN v_retry; END IF;
 IF jsonb_typeof(fee_type_ids) IS DISTINCT FROM 'array' THEN RAISE EXCEPTION 'INVALID_COMMAND'; END IF;
 IF jsonb_array_length(fee_type_ids)>3 THEN RAISE EXCEPTION 'FEE_COLUMNS_MAX'; END IF;
 FOR v_type IN SELECT x FROM jsonb_array_elements(fee_type_ids) x LOOP
   IF jsonb_typeof(v_type)<>'number' OR v_type::text !~ '^[1-9][0-9]*$' OR v_type::text::bigint=ANY(v_seen)
   THEN RAISE EXCEPTION 'INVALID_COMMAND'; END IF;
   PERFORM 1 FROM sokhach.fee_type WHERE id=v_type::text::bigint AND active AND system_key IS DISTINCT FROM 'initial' FOR SHARE;
   IF NOT FOUND THEN RAISE EXCEPTION 'FEE_TYPE_INACTIVE'; END IF;
   v_seen:=array_append(v_seen,v_type::text::bigint);
 END LOOP;
 SELECT coalesce(jsonb_agg(fee_type_id ORDER BY position),'[]') INTO v_before FROM sokhach.book_fee_column b
   WHERE b.customer_id=set_book_fee_columns.customer_id;
 INSERT INTO sokhach.event(customer_id,kind,actor,"before","after",idempotency_key)
 VALUES(customer_id,'set_book_fee_columns',sokhach._actor(),jsonb_build_object('fee_columns',v_before),
   jsonb_build_object('fee_columns',fee_type_ids),idempotency_key);
 DELETE FROM sokhach.book_fee_column b WHERE b.customer_id=set_book_fee_columns.customer_id;
 INSERT INTO sokhach.book_fee_column(customer_id,fee_type_id,position)
 SELECT customer_id,x::text::bigint,n FROM jsonb_array_elements(fee_type_ids) WITH ORDINALITY a(x,n);
 RETURN sokhach._finish_command(customer_id,idempotency_key,v_payload,jsonb_build_object('fee_columns',fee_type_ids));
EXCEPTION WHEN numeric_value_out_of_range THEN RAISE EXCEPTION 'INVALID_COMMAND';
END $$;

CREATE OR REPLACE FUNCTION sokhach._change_legacy(customer_id bigint,expected_version bigint,idempotency_key text,
    legacy_row_id bigint,field text,value text,p_delete boolean,p_fee_event bigint) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,sokhach,pg_temp AS $$
DECLARE v_payload jsonb:=jsonb_build_object('command',CASE WHEN p_delete THEN 'delete_legacy_trip' ELSE 'edit_legacy_trip' END,
      'legacy_row_id',legacy_row_id,'field',field,'value',value);
    v_retry jsonb; l sokhach.legacy_row%ROWTYPE; v_old jsonb; v_new jsonb; v_value text;
    v_month date; v_old_month date; v_count bigint; v_old_count bigint; v_event bigint; v_changes jsonb;
    v_fee bigint;
BEGIN
    IF p_fee_event IS NULL THEN
    v_retry:=sokhach._begin_command(customer_id,expected_version,idempotency_key,v_payload);
    IF v_retry IS NOT NULL THEN RETURN v_retry; END IF;
    END IF;
    PERFORM sokhach._baseline(customer_id);
    SELECT l0.* INTO l FROM sokhach.legacy_row l0 JOIN sokhach.cutover_customer cc USING(customer_id,cutover_id)
      JOIN sokhach.cutover c ON c.id=cc.cutover_id WHERE l0.id=legacy_row_id AND l0.customer_id=_change_legacy.customer_id AND cc.status='active' AND c.status='active';
    IF NOT FOUND THEN RAISE EXCEPTION 'LEGACY_NOT_FOUND'; END IF;
    -- Khoản thu sổ gốc chỉ xóa được, không sửa ô (XOA-THU-GOC-01).
    IF l.kind<>'trip' AND NOT p_delete THEN RAISE EXCEPTION 'LEGACY_NOT_TRIP'; END IF;
    v_old:=sokhach._legacy_current(l.id)||jsonb_build_object('kind',l.kind); v_new:=v_old;
    IF l.kind='trip' THEN
      SELECT sum(amount_vnd)::bigint INTO v_fee FROM sokhach.trip_fee_line
        WHERE trip_fee_line.legacy_row_id=l.id AND voided_by_event IS NULL;
      v_old:=v_old||jsonb_build_object('other_fee_vnd',v_fee::text); v_new:=v_old;
    END IF;
    IF (v_old->>'deleted')::boolean THEN RAISE EXCEPTION 'LEGACY_NOT_FOUND'; END IF;
    v_old_month:=(v_old->>'month')::date; v_month:=v_old_month; v_old_count:=(v_old->>'counted_vnd')::bigint;
    PERFORM sokhach._month_open(customer_id,v_old_month,clock_timestamp());
    IF p_delete THEN v_count:=0; v_new:=v_new||jsonb_build_object('deleted',true);
    ELSE
      IF field IS NULL OR field NOT IN ('container','carrier','shipper','origin','destination','event_date','unit_price_vnd','other_fee_vnd') THEN RAISE EXCEPTION 'INVALID_FIELD'; END IF;
      v_value:=nullif(btrim(value),'');
      IF field IN ('unit_price_vnd','other_fee_vnd') THEN
        IF v_value IS NOT NULL AND v_value !~ (CASE WHEN field='other_fee_vnd' THEN '^-?[0-9]+$' ELSE '^[0-9]+$' END) THEN RAISE EXCEPTION 'INVALID_VND'; END IF;
        v_value:=((v_value)::bigint)::text;
        IF field='other_fee_vnd' AND v_value='0' THEN v_value:=NULL; END IF;
      ELSIF field='event_date' THEN v_value:=sokhach._trip_date(value)::text; v_month:=date_trunc('month',v_value::date)::date;
      ELSIF field='container' THEN v_value:=nullif(sokhach._normalize_key(value),''); END IF;
      IF p_fee_event IS NULL AND field='other_fee_vnd' AND EXISTS (SELECT 1 FROM sokhach.trip_fee_line fl JOIN sokhach.fee_type ft ON ft.id=fl.fee_type_id
          WHERE fl.legacy_row_id=l.id AND fl.voided_by_event IS NULL
            AND coalesce(ft.system_key,'') NOT IN ('other','discount','initial'))
      THEN RAISE EXCEPTION 'FEE_LINES_TYPED'; END IF;
      IF p_fee_event IS NULL AND v_old->>field IS NOT DISTINCT FROM v_value THEN RAISE EXCEPTION 'NO_CHANGE'; END IF;
      v_new:=v_new||jsonb_build_object(field,v_value);
      -- Text edits preserve the Sheet counted amount, including flagged source differences.
      v_count:=v_old_count;
      IF field IN ('unit_price_vnd','other_fee_vnd') THEN
        v_count:=CASE WHEN v_new->>'unit_price_vnd' IS NULL THEN 0 ELSE
          (v_new->>'unit_price_vnd')::bigint+coalesce((v_new->>'other_fee_vnd')::bigint,0) END;
      END IF;
    END IF;
    IF v_month<>v_old_month THEN PERFORM sokhach._month_open(customer_id,v_month,clock_timestamp()); END IF;
    v_new:=v_new||jsonb_build_object('month',v_month,'debt_month',v_month,'counted_vnd',v_count::text,'field',field,'value',v_new->field);
    IF p_fee_event IS NULL THEN
    INSERT INTO sokhach.event(customer_id,kind,actor,"before","after",idempotency_key)
      VALUES(customer_id,CASE WHEN p_delete THEN 'legacy_delete' ELSE 'legacy_edit' END,sokhach._actor(),
        jsonb_build_object('legacy',v_old||jsonb_build_object('field',field,'value',v_old->field)),jsonb_build_object('legacy',v_new),idempotency_key) RETURNING id INTO v_event;
    ELSE v_event:=p_fee_event; END IF;
    IF p_fee_event IS NULL AND field='other_fee_vnd' AND NOT p_delete THEN
      UPDATE sokhach.trip_fee_line SET voided_by_event=v_event
        WHERE trip_fee_line.legacy_row_id=l.id AND voided_by_event IS NULL;
      IF v_value IS NOT NULL THEN
        INSERT INTO sokhach.trip_fee_line(customer_id,legacy_row_id,fee_type_id,amount_vnd,created_by_event)
        SELECT customer_id,l.id,id,v_value::bigint,v_event FROM sokhach.fee_type
        WHERE system_key=CASE WHEN v_value::bigint<0 THEN 'discount' ELSE 'other' END;
      END IF;
    END IF;
    INSERT INTO sokhach.legacy_trip_rev(legacy_row_id,customer_id,debt_month,event_date,container,carrier,shipper,origin,destination,unit_price_vnd,other_fee_vnd,deleted,counted_vnd,created_by_event)
      VALUES(l.id,customer_id,v_month,(v_new->>'event_date')::date,v_new->>'container',v_new->>'carrier',v_new->>'shipper',v_new->>'origin',v_new->>'destination',
        (v_new->>'unit_price_vnd')::bigint,(v_new->>'other_fee_vnd')::bigint,p_delete,v_count,v_event);
    -- Khoản thu đã trừ nợ: xóa thì cộng lại đúng số đó vào tháng của dòng.
    INSERT INTO sokhach.adjustment(customer_id,debt_month,legacy_row_id,amount_vnd,actor,created_by_event)
      SELECT customer_id,m,l.id,CASE WHEN l.kind='receipt' THEN -delta ELSE delta END,sokhach._actor(),v_event FROM (
        SELECT v_old_month AS m,CASE WHEN v_month=v_old_month THEN v_count-v_old_count ELSE -v_old_count END AS delta
        UNION ALL SELECT v_month,v_count WHERE v_month<>v_old_month) d WHERE delta<>0;
    IF p_fee_event IS NOT NULL THEN RETURN v_new; END IF;
    v_changes:=sokhach.reallocate(customer_id,idempotency_key);
    RETURN sokhach._finish_command(customer_id,idempotency_key,v_payload,jsonb_build_object('legacy_row_id',l.id,'deleted',p_delete,'reallocated',v_changes));
EXCEPTION WHEN numeric_value_out_of_range THEN RAISE EXCEPTION 'INVALID_VND';
END $$;
CREATE OR REPLACE FUNCTION sokhach._change_legacy(customer_id bigint,expected_version bigint,idempotency_key text,
    legacy_row_id bigint,field text,value text,p_delete boolean) RETURNS jsonb
LANGUAGE sql SECURITY DEFINER SET search_path=pg_catalog,sokhach,pg_temp AS $$
 SELECT sokhach._change_legacy(customer_id,expected_version,idempotency_key,legacy_row_id,field,value,p_delete,NULL)
$$;
CREATE OR REPLACE FUNCTION sokhach._guard_fee_line() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog,sokhach,pg_temp AS $$
DECLARE t sokhach.fee_type%ROWTYPE;
BEGIN
 IF TG_OP='DELETE' THEN RAISE EXCEPTION 'FEE_LINE_IMMUTABLE'; END IF;
 IF TG_OP='UPDATE' THEN
   IF OLD.voided_by_event IS NOT NULL OR NEW.voided_by_event IS NULL
      OR (to_jsonb(NEW)-'voided_by_event') IS DISTINCT FROM (to_jsonb(OLD)-'voided_by_event')
   THEN RAISE EXCEPTION 'FEE_LINE_IMMUTABLE'; END IF;
   RETURN NEW;
 END IF;
 SELECT * INTO t FROM sokhach.fee_type WHERE id=NEW.fee_type_id;
 IF NOT FOUND OR NOT t.active THEN RAISE EXCEPTION 'FEE_TYPE_INACTIVE'; END IF;
 IF NEW.amount_vnd IS NULL OR NEW.amount_vnd=0 THEN RAISE EXCEPTION 'FEE_AMOUNT_INVALID'; END IF;
 IF t.system_key='initial' AND NOT EXISTS (
   SELECT 1 FROM sokhach.event e JOIN sokhach.trip_fee_line old_line ON old_line.voided_by_event=e.id
   WHERE e.id=NEW.created_by_event AND e.kind='replace_trip_fee' AND e.customer_id=NEW.customer_id
     AND old_line.fee_type_id=NEW.fee_type_id AND old_line.trip_id IS NOT DISTINCT FROM NEW.trip_id
     AND old_line.legacy_row_id IS NOT DISTINCT FROM NEW.legacy_row_id
     AND e."before"->'targets'->0->'fee_lines' @> jsonb_build_array(jsonb_build_object('id',old_line.id))
     AND NOT EXISTS(SELECT 1 FROM sokhach.trip_fee_line n WHERE n.created_by_event=e.id))
 THEN RAISE EXCEPTION 'FEE_TYPE_SYSTEM'; END IF;
 IF (t.sign='positive' AND NEW.amount_vnd<0) OR (t.sign='negative' AND NEW.amount_vnd>0)
 THEN RAISE EXCEPTION 'FEE_SIGN_INVALID'; END IF;
 RETURN NEW;
END $$;
CREATE OR REPLACE FUNCTION sokhach._fee_columns(p_customer bigint) RETURNS jsonb
LANGUAGE sql STABLE SET search_path=pg_catalog,sokhach,pg_temp AS $$
 SELECT coalesce(jsonb_agg(jsonb_build_object('fee_type_id',fee_type_id,'position',position) ORDER BY position),'[]')
 FROM sokhach.book_fee_column WHERE customer_id=p_customer
$$;
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

REVOKE ALL ON ALL FUNCTIONS IN SCHEMA sokhach FROM PUBLIC;
GRANT EXECUTE ON FUNCTION sokhach.add_trip_fees(bigint,bigint,text,jsonb,bigint,bigint,text) TO sokhach_app;
GRANT EXECUTE ON FUNCTION sokhach.set_trip_fee_type(bigint,bigint,text,jsonb,bigint,bigint) TO sokhach_app;
GRANT EXECUTE ON FUNCTION sokhach.replace_trip_fee(bigint,bigint,text,bigint,bigint,bigint,text) TO sokhach_app;
GRANT EXECUTE ON FUNCTION sokhach.void_trip_fee(bigint,bigint,text,bigint) TO sokhach_app;
GRANT EXECUTE ON FUNCTION sokhach.add_fee_type(text,text,text) TO sokhach_app;
GRANT EXECUTE ON FUNCTION sokhach.rename_fee_type(text,bigint,text) TO sokhach_app;
GRANT EXECUTE ON FUNCTION sokhach.set_fee_type_kind(text,bigint,text) TO sokhach_app;
GRANT EXECUTE ON FUNCTION sokhach.set_fee_type_active(text,bigint,boolean) TO sokhach_app;
GRANT EXECUTE ON FUNCTION sokhach.set_book_fee_columns(bigint,bigint,text,jsonb) TO sokhach_app;
GRANT EXECUTE ON FUNCTION sokhach.get_fee_types() TO sokhach_app,sokhach_reader;
REVOKE ALL ON FUNCTION sokhach._fee_lines(bigint,bigint) FROM PUBLIC,sokhach_app,sokhach_reader;
REVOKE ALL ON FUNCTION sokhach._fee_columns(bigint) FROM PUBLIC,sokhach_app,sokhach_reader;
REVOKE ALL ON FUNCTION sokhach._fee_target(bigint,jsonb) FROM PUBLIC,sokhach_app,sokhach_reader;
REVOKE ALL ON FUNCTION sokhach._change_trip_fees(bigint,bigint,text,text,jsonb,bigint,bigint,text,bigint) FROM PUBLIC,sokhach_app,sokhach_reader;
REVOKE ALL ON FUNCTION sokhach._change_fee_type(text,text,bigint,text,text) FROM PUBLIC,sokhach_app,sokhach_reader;
REVOKE ALL ON FUNCTION sokhach._change_legacy(bigint,bigint,text,bigint,text,text,boolean,bigint) FROM PUBLIC,sokhach_app,sokhach_reader;
COMMIT;
