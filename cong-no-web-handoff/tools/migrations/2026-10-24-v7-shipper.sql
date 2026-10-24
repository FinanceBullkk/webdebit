-- SHIPPER-01: apply only after restored-copy rehearsal and production gate.
BEGIN;
SET LOCAL ROLE sokhach_owner;
ALTER TABLE sokhach.trip ADD COLUMN IF NOT EXISTS shipper text;
ALTER TABLE sokhach.trip_info_rev ADD COLUMN IF NOT EXISTS shipper text;
ALTER TABLE sokhach.legacy_trip_rev ADD COLUMN IF NOT EXISTS shipper text;
CREATE OR REPLACE VIEW sokhach.v_trip_current AS
SELECT t.id,t.customer_id,t.debt_month AS origin_month,
       coalesce(r.debt_month,t.debt_month) AS debt_month,
       CASE WHEN r.id IS NULL THEN t.event_date ELSE r.event_date END AS event_date,
       CASE WHEN r.id IS NULL THEN t.container ELSE r.container END AS container,
       CASE WHEN r.id IS NULL THEN t.carrier ELSE r.carrier END AS carrier,
       CASE WHEN r.id IS NULL THEN t.origin ELSE r.origin END AS origin,
       CASE WHEN r.id IS NULL THEN t.destination ELSE r.destination END AS destination,
       t.booking,t.note,t.source_ref,coalesce(r.status,t.status) AS status,
       coalesce(r.deleted,false) AS deleted,
       CASE WHEN r.id IS NULL THEN t.shipper ELSE r.shipper END AS shipper
FROM sokhach.trip t LEFT JOIN LATERAL (SELECT * FROM sokhach.trip_info_rev x
  WHERE x.trip_id=t.id AND x.customer_id=t.customer_id ORDER BY x.id DESC LIMIT 1) r ON true;

CREATE OR REPLACE FUNCTION sokhach._legacy_current(p_id bigint) RETURNS jsonb
LANGUAGE plpgsql STABLE SET search_path=pg_catalog,sokhach,pg_temp AS $$
DECLARE l sokhach.legacy_row%ROWTYPE; r sokhach.legacy_trip_rev%ROWTYPE;
    v_date date; v_unit bigint; v_fee bigint;
BEGIN
    SELECT * INTO l FROM sokhach.legacy_row WHERE id=p_id;
    SELECT * INTO r FROM sokhach.legacy_trip_rev WHERE legacy_row_id=p_id ORDER BY id DESC LIMIT 1;
    IF FOUND THEN RETURN to_jsonb(r)||jsonb_build_object('month',r.debt_month,'unit_price_vnd',r.unit_price_vnd::text,'other_fee_vnd',r.other_fee_vnd::text,'counted_vnd',r.counted_vnd::text); END IF;
    BEGIN
      IF l.display->>'date' ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$' THEN v_date:=(l.display->>'date')::date;
      ELSIF l.display->>'date' ~ '^[0-9]{2}/[0-9]{2}/[0-9]{4}$' THEN
        v_date:=to_date(l.display->>'date','DD/MM/YYYY');
        IF to_char(v_date,'DD/MM/YYYY')<>l.display->>'date' THEN v_date:=NULL; END IF;
      END IF;
    EXCEPTION WHEN invalid_datetime_format OR datetime_field_overflow THEN v_date:=NULL; END;
    BEGIN IF l.display->>'unit_price' ~ '^[0-9]+$' THEN v_unit:=(l.display->>'unit_price')::bigint; END IF;
    EXCEPTION WHEN numeric_value_out_of_range THEN v_unit:=NULL; END;
    BEGIN IF l.display->>'fee_vnd' ~ '^[0-9]+$' THEN v_fee:=(l.display->>'fee_vnd')::bigint; END IF;
    EXCEPTION WHEN numeric_value_out_of_range THEN v_fee:=NULL; END;
    RETURN jsonb_build_object('legacy_row_id',l.id,'customer_id',l.customer_id,'month',l.debt_month,'debt_month',l.debt_month,
      'event_date',v_date,'container',l.display->>'container','carrier',l.display->>'carrier','shipper',l.display->>'shipper','origin',l.display->>'from','destination',l.display->>'to',
      'unit_price_vnd',v_unit::text,'other_fee_vnd',v_fee::text,'counted_vnd',coalesce(l.source_total_vnd,0)::text,'deleted',false);
END $$;

CREATE OR REPLACE FUNCTION sokhach.paste_trips(customer_id bigint, expected_version bigint,
    idempotency_key text, debt_month date, trips jsonb) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, sokhach, pg_temp AS $$
DECLARE v_payload jsonb := jsonb_build_object('command','paste_trips','month',debt_month,'trips',trips);
        v_retry jsonb; v_actor text; v_now timestamptz; v_ids jsonb := '[]'::jsonb;
        v_item jsonb; v_id bigint; v_event bigint; v_rows jsonb := '[]'::jsonb;
        v_changes jsonb; v_date date; v_unit bigint; v_fee bigint; v_date_text text;
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
    v_now := clock_timestamp();
    PERFORM sokhach._month_open(customer_id,debt_month,v_now);
    IF jsonb_typeof(trips) IS DISTINCT FROM 'array' OR jsonb_array_length(trips)=0
    THEN RAISE EXCEPTION 'INVALID_TRIPS'; END IF;
    FOR v_item IN SELECT value FROM jsonb_array_elements(trips) LOOP
        v_fee_only := nullif(v_item->>'container','') IS NULL
            AND v_item->>'unitPriceVnd' IS NULL AND v_item->>'otherFeeVnd' IS NOT NULL;
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
           OR (v_item->>'otherFeeVnd' IS NOT NULL AND (v_item->>'otherFeeVnd') !~ '^[0-9]+$')
        THEN RAISE EXCEPTION 'INVALID_TRIP_INPUT'; END IF;
        v_date := CASE WHEN v_date_text IS NULL THEN NULL ELSE to_date(v_date_text,'DD/MM/YYYY') END;
        IF v_date_text IS NOT NULL AND to_char(v_date,'DD/MM/YYYY') <> v_date_text
        THEN RAISE EXCEPTION 'INVALID_TRIP_DATE'; END IF;
        BEGIN
            v_unit := (v_item->>'unitPriceVnd')::bigint;
            v_fee := (v_item->>'otherFeeVnd')::bigint;
        EXCEPTION WHEN numeric_value_out_of_range THEN RAISE EXCEPTION 'INVALID_VND'; END;
        -- ponytail: cap is signed bigint until business VND limit is decided.
        IF v_unit < 0 OR v_fee < 0 OR
           coalesce(v_unit,0)::numeric+coalesce(v_fee,0)::numeric>9223372036854775807
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
            ELSIF EXISTS (SELECT 1 FROM sokhach.trip t WHERE t.customer_id=paste_trips.customer_id
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
            'trip_id',v_id,'debt_month',debt_month,'event_date',v_date,
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
        VALUES ((v_item->>'trip_id')::bigint,customer_id,debt_month,(v_item->>'event_date')::date,
            v_item->>'container',v_item->>'carrier',v_item->>'shipper',v_item->>'from',v_item->>'to',
            v_item->>'note',v_item->>'src',v_event,v_item->>'booking',v_item->>'status');
        INSERT INTO sokhach.trip_price_rev(trip_id,customer_id,unit_price_vnd,other_fee_vnd,created_by_event)
        VALUES ((v_item->>'trip_id')::bigint,customer_id,
            (v_item->>'unitPriceVnd')::bigint,(v_item->>'otherFeeVnd')::bigint,v_event);
    END LOOP;
    v_changes := sokhach.reallocate(customer_id,idempotency_key);
    RETURN sokhach._finish_command(customer_id,idempotency_key,v_payload,
        jsonb_build_object('trip_ids',v_ids,'reallocated',v_changes,'pending_review',v_pending));
END $$;

CREATE OR REPLACE FUNCTION sokhach.edit_trip_info(customer_id bigint,expected_version bigint,idempotency_key text,
    trip_id bigint,field text,value text) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,sokhach,pg_temp AS $$
DECLARE v_payload jsonb := jsonb_build_object('command','edit_trip_info','trip_id',trip_id,'field',field,'value',value);
    v_retry jsonb; t sokhach.v_trip_current%ROWTYPE; v_before jsonb; v_after jsonb;
    v_value text; v_date date; v_event bigint; v_changes jsonb; v_cutover bigint; v_reason text;
    v_booking text; v_container text;
BEGIN
    v_retry := sokhach._begin_command(customer_id,expected_version,idempotency_key,v_payload);
    IF v_retry IS NOT NULL THEN RETURN v_retry; END IF;
    PERFORM sokhach._baseline(customer_id);
    IF field IS NULL OR field NOT IN ('container','carrier','shipper','origin','destination','event_date') THEN RAISE EXCEPTION 'INVALID_FIELD'; END IF;
    SELECT * INTO t FROM sokhach.v_trip_current v WHERE v.id=trip_id AND v.customer_id=edit_trip_info.customer_id AND NOT v.deleted;
    IF NOT FOUND THEN RAISE EXCEPTION 'TRIP_NOT_FOUND'; END IF;
    PERFORM sokhach._month_open(customer_id,t.debt_month,clock_timestamp());
    v_value := nullif(btrim(value),'');
    IF field='container' THEN v_value := nullif(sokhach._normalize_key(value),''); END IF;
    IF field='event_date' THEN v_date := sokhach._trip_date(value); v_value := v_date::text;
    ELSIF v_value IS NULL AND field<>'shipper' AND (coalesce(t.container,'')<>'' OR field='container' AND t.container IS NOT NULL)
    THEN RAISE EXCEPTION 'INVALID_TRIP_INPUT'; END IF;
    IF to_jsonb(t)->>field IS NOT DISTINCT FROM v_value THEN RAISE EXCEPTION 'NO_CHANGE'; END IF;
    v_before := jsonb_build_object('id',t.id,'field',field,'value',to_jsonb(t)->field,'debt_month',t.debt_month,'status',t.status);
    CASE field WHEN 'container' THEN t.container:=v_value; WHEN 'carrier' THEN t.carrier:=v_value; WHEN 'shipper' THEN t.shipper:=v_value;
      WHEN 'origin' THEN t.origin:=v_value; WHEN 'destination' THEN t.destination:=v_value;
      WHEN 'event_date' THEN t.event_date:=v_date; t.debt_month:=date_trunc('month',v_date)::date; END CASE;
    IF t.debt_month<>(v_before->>'debt_month')::date THEN
      PERFORM sokhach._month_open(customer_id,t.debt_month,clock_timestamp()); END IF;
    -- Converting a fee-only row to a container trip must satisfy normal trip inputs.
    IF coalesce(t.container,'')<>'' AND (t.event_date IS NULL OR nullif(btrim(t.carrier),'') IS NULL
       OR nullif(btrim(t.origin),'') IS NULL OR nullif(btrim(t.destination),'') IS NULL)
    THEN RAISE EXCEPTION 'INVALID_TRIP_INPUT'; END IF;
    IF t.status='confirmed' AND field IN ('container','event_date') AND coalesce(t.container,'')<>'' THEN
      SELECT cc.cutover_id INTO v_cutover FROM sokhach.cutover_customer cc JOIN sokhach.cutover c ON c.id=cc.cutover_id
        WHERE cc.customer_id=edit_trip_info.customer_id AND cc.status='active' AND c.status='active';
      IF NOT EXISTS(SELECT FROM sokhach.baseline_trip_ref WHERE cutover_id=v_cutover) THEN RAISE EXCEPTION 'BASELINE_REF_MISSING'; END IF;
      v_container:=sokhach._normalize_key(t.container); v_booking:=sokhach._booking_key(t.booking,t.container,t.event_date);
      IF EXISTS(SELECT FROM sokhach.baseline_trip_ref r WHERE r.cutover_id=v_cutover AND r.container_norm=v_container AND r.booking_norm=v_booking)
      THEN v_reason:='BASELINE_CODE_MATCH';
      ELSIF EXISTS(SELECT FROM sokhach.baseline_trip_ref r WHERE r.cutover_id=v_cutover AND r.container_norm=v_container AND abs(r.event_date-t.event_date)<=3)
      THEN v_reason:='BASELINE_DATE_WINDOW';
      ELSIF EXISTS(SELECT FROM sokhach.v_trip_current v WHERE v.customer_id=edit_trip_info.customer_id AND v.id<>t.id AND NOT v.deleted
        AND sokhach._normalize_key(v.container)=v_container AND (sokhach._booking_key(v.booking,v.container,v.event_date)=v_booking OR abs(v.event_date-t.event_date)<=3))
      THEN v_reason:='WEB_DUPLICATE'; END IF;
      IF v_reason IS NOT NULL THEN t.status:='pending_review'; END IF;
    END IF;
    v_after:=jsonb_build_object('trip',jsonb_build_object('id',t.id,'field',field,'value',v_value,'debt_month',t.debt_month,'status',t.status));
    IF t.debt_month<>(v_before->>'debt_month')::date THEN
      v_after:=v_after||jsonb_build_object('moved_from_month',v_before->'debt_month','moved_to_month',t.debt_month); END IF;
    IF v_reason IS NOT NULL THEN v_after:=v_after||jsonb_build_object('review_reason',v_reason); END IF;
    INSERT INTO sokhach.event(customer_id,kind,actor,"before","after",idempotency_key)
      VALUES(customer_id,'trip_edit',sokhach._actor(),jsonb_build_object('trip',v_before),v_after,idempotency_key) RETURNING id INTO v_event;
    INSERT INTO sokhach.trip_info_rev(trip_id,customer_id,debt_month,event_date,container,carrier,shipper,origin,destination,status,created_by_event)
      VALUES(t.id,customer_id,t.debt_month,t.event_date,t.container,t.carrier,t.shipper,t.origin,t.destination,t.status,v_event);
    v_changes:=sokhach.reallocate(customer_id,idempotency_key);
    RETURN sokhach._finish_command(customer_id,idempotency_key,v_payload,jsonb_build_object('trip_id',t.id,'pending_review',t.status='pending_review','reason',v_reason,'reallocated',v_changes));
END $$;

CREATE OR REPLACE FUNCTION sokhach.delete_trip(customer_id bigint,expected_version bigint,idempotency_key text,trip_id bigint) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,sokhach,pg_temp AS $$
DECLARE v_payload jsonb:=jsonb_build_object('command','delete_trip','trip_id',trip_id);
    v_retry jsonb; t sokhach.v_trip_current%ROWTYPE; v_price jsonb; v_event bigint; v_changes jsonb;
BEGIN
    v_retry:=sokhach._begin_command(customer_id,expected_version,idempotency_key,v_payload);
    IF v_retry IS NOT NULL THEN RETURN v_retry; END IF;
    PERFORM sokhach._baseline(customer_id);
    SELECT * INTO t FROM sokhach.v_trip_current v WHERE v.id=trip_id AND v.customer_id=delete_trip.customer_id AND NOT v.deleted;
    IF NOT FOUND THEN RAISE EXCEPTION 'TRIP_NOT_FOUND'; END IF;
    PERFORM sokhach._month_open(customer_id,t.debt_month,clock_timestamp());
    SELECT jsonb_build_object('unit_price_vnd',CASE WHEN p.unit_price_vnd IS NOT NULL
          THEN (a.amount_vnd-coalesce(f.fee,p.other_fee_vnd,0))::text END,
      'other_fee_vnd',coalesce(f.fee,p.other_fee_vnd)::text,
      'amount_vnd',CASE WHEN t.status='confirmed' THEN a.amount_vnd::text END)
    INTO v_price FROM (SELECT * FROM sokhach.trip_price_rev WHERE trip_price_rev.trip_id=t.id ORDER BY id DESC LIMIT 1) p
    LEFT JOIN LATERAL (SELECT x.new_value_vnd AS fee FROM sokhach.adjustment x
        WHERE x.trip_id=t.id AND x.field='other_fee_vnd' AND x.created_by_event>p.created_by_event
        ORDER BY x.created_by_event DESC LIMIT 1) f ON true
    CROSS JOIN LATERAL (SELECT (CASE WHEN p.unit_price_vnd IS NOT NULL THEN p.unit_price_vnd+coalesce(p.other_fee_vnd,0)
        WHEN coalesce(t.container,'')='' THEN p.other_fee_vnd END)
        +coalesce((SELECT sum(x.amount_vnd) FROM sokhach.adjustment x WHERE x.trip_id=t.id),0) AS amount_vnd) a;
    INSERT INTO sokhach.event(customer_id,kind,actor,"before","after",idempotency_key)
      VALUES(customer_id,'trip_delete',sokhach._actor(),jsonb_build_object('trip',to_jsonb(t)||coalesce(v_price,'{}')),
        jsonb_build_object('trip',jsonb_build_object('id',t.id,'deleted',true)),idempotency_key) RETURNING id INTO v_event;
    INSERT INTO sokhach.trip_info_rev(trip_id,customer_id,debt_month,event_date,container,carrier,shipper,origin,destination,status,deleted,created_by_event)
      VALUES(t.id,customer_id,t.debt_month,t.event_date,t.container,t.carrier,t.shipper,t.origin,t.destination,t.status,true,v_event);
    v_changes:=sokhach.reallocate(customer_id,idempotency_key);
    RETURN sokhach._finish_command(customer_id,idempotency_key,v_payload,jsonb_build_object('trip_id',t.id,'deleted',true,'reallocated',v_changes));
END $$;

CREATE OR REPLACE FUNCTION sokhach._change_legacy(customer_id bigint,expected_version bigint,idempotency_key text,
    legacy_row_id bigint,field text,value text,p_delete boolean) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,sokhach,pg_temp AS $$
DECLARE v_payload jsonb:=jsonb_build_object('command',CASE WHEN p_delete THEN 'delete_legacy_trip' ELSE 'edit_legacy_trip' END,
      'legacy_row_id',legacy_row_id,'field',field,'value',value);
    v_retry jsonb; l sokhach.legacy_row%ROWTYPE; v_old jsonb; v_new jsonb; v_value text;
    v_month date; v_old_month date; v_count bigint; v_old_count bigint; v_event bigint; v_changes jsonb;
BEGIN
    v_retry:=sokhach._begin_command(customer_id,expected_version,idempotency_key,v_payload);
    IF v_retry IS NOT NULL THEN RETURN v_retry; END IF;
    PERFORM sokhach._baseline(customer_id);
    SELECT l0.* INTO l FROM sokhach.legacy_row l0 JOIN sokhach.cutover_customer cc USING(customer_id,cutover_id)
      JOIN sokhach.cutover c ON c.id=cc.cutover_id WHERE l0.id=legacy_row_id AND l0.customer_id=_change_legacy.customer_id AND cc.status='active' AND c.status='active';
    IF NOT FOUND THEN RAISE EXCEPTION 'LEGACY_NOT_FOUND'; END IF;
    IF l.kind<>'trip' THEN RAISE EXCEPTION 'LEGACY_NOT_TRIP'; END IF;
    v_old:=sokhach._legacy_current(l.id); v_new:=v_old;
    IF (v_old->>'deleted')::boolean THEN RAISE EXCEPTION 'LEGACY_NOT_FOUND'; END IF;
    v_old_month:=(v_old->>'month')::date; v_month:=v_old_month; v_old_count:=(v_old->>'counted_vnd')::bigint;
    PERFORM sokhach._month_open(customer_id,v_old_month,clock_timestamp());
    IF p_delete THEN v_count:=0; v_new:=v_new||jsonb_build_object('deleted',true);
    ELSE
      IF field IS NULL OR field NOT IN ('container','carrier','shipper','origin','destination','event_date','unit_price_vnd','other_fee_vnd') THEN RAISE EXCEPTION 'INVALID_FIELD'; END IF;
      v_value:=nullif(btrim(value),'');
      IF field IN ('unit_price_vnd','other_fee_vnd') THEN
        IF v_value IS NOT NULL AND v_value !~ '^[0-9]+$' THEN RAISE EXCEPTION 'INVALID_VND'; END IF;
        v_value:=((v_value)::bigint)::text;
      ELSIF field='event_date' THEN v_value:=sokhach._trip_date(value)::text; v_month:=date_trunc('month',v_value::date)::date;
      ELSIF field='container' THEN v_value:=nullif(sokhach._normalize_key(value),''); END IF;
      IF v_old->>field IS NOT DISTINCT FROM v_value THEN RAISE EXCEPTION 'NO_CHANGE'; END IF;
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
    INSERT INTO sokhach.event(customer_id,kind,actor,"before","after",idempotency_key)
      VALUES(customer_id,CASE WHEN p_delete THEN 'legacy_delete' ELSE 'legacy_edit' END,sokhach._actor(),
        jsonb_build_object('legacy',v_old||jsonb_build_object('field',field,'value',v_old->field)),jsonb_build_object('legacy',v_new),idempotency_key) RETURNING id INTO v_event;
    INSERT INTO sokhach.legacy_trip_rev(legacy_row_id,customer_id,debt_month,event_date,container,carrier,shipper,origin,destination,unit_price_vnd,other_fee_vnd,deleted,counted_vnd,created_by_event)
      VALUES(l.id,customer_id,v_month,(v_new->>'event_date')::date,v_new->>'container',v_new->>'carrier',v_new->>'shipper',v_new->>'origin',v_new->>'destination',
        (v_new->>'unit_price_vnd')::bigint,(v_new->>'other_fee_vnd')::bigint,p_delete,v_count,v_event);
    INSERT INTO sokhach.adjustment(customer_id,debt_month,legacy_row_id,amount_vnd,actor,created_by_event)
      SELECT customer_id,m,l.id,delta,sokhach._actor(),v_event FROM (
        SELECT v_old_month AS m,CASE WHEN v_month=v_old_month THEN v_count-v_old_count ELSE -v_old_count END AS delta
        UNION ALL SELECT v_month,v_count WHERE v_month<>v_old_month) d WHERE delta<>0;
    v_changes:=sokhach.reallocate(customer_id,idempotency_key);
    RETURN sokhach._finish_command(customer_id,idempotency_key,v_payload,jsonb_build_object('legacy_row_id',l.id,'deleted',p_delete,'reallocated',v_changes));
EXCEPTION WHEN numeric_value_out_of_range THEN RAISE EXCEPTION 'INVALID_VND';
END $$;

CREATE OR REPLACE FUNCTION sokhach.review_trip(customer_id bigint, expected_version bigint,
    idempotency_key text, trip_id bigint, decision text, reason text)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, sokhach, pg_temp AS $$
DECLARE v_payload jsonb := jsonb_build_object('command','review_trip','trip_id',trip_id,
        'decision',decision,'reason',reason);
        v_retry jsonb; v_trip sokhach.v_trip_current%ROWTYPE; v_status text; v_event bigint;
        v_changes jsonb := '[]'::jsonb;
BEGIN
    v_retry := sokhach._begin_command(customer_id,expected_version,idempotency_key,v_payload);
    IF v_retry IS NOT NULL THEN RETURN v_retry; END IF;
    PERFORM sokhach._baseline(customer_id);
    v_status := CASE decision WHEN 'confirm' THEN 'confirmed' WHEN 'reject' THEN 'rejected' END;
    IF v_status IS NULL THEN RAISE EXCEPTION 'INVALID_REVIEW'; END IF;
    IF reason IS NULL OR btrim(reason)='' THEN RAISE EXCEPTION 'REVIEW_REASON_REQUIRED'; END IF;
    SELECT * INTO v_trip FROM sokhach.v_trip_current v WHERE v.id=trip_id AND v.customer_id=review_trip.customer_id AND NOT v.deleted;
    IF NOT FOUND THEN RAISE EXCEPTION 'TRIP_NOT_FOUND'; END IF;
    IF v_trip.status<>'pending_review' THEN RAISE EXCEPTION 'TRIP_NOT_PENDING'; END IF;
    PERFORM sokhach._month_open(customer_id,v_trip.debt_month,clock_timestamp());
    INSERT INTO sokhach.event(customer_id,kind,actor,"before","after",idempotency_key)
    VALUES (customer_id,'trip_review',sokhach._actor(),
        jsonb_build_object('trip',trip_id,'container',v_trip.container,'status','pending_review'),
        jsonb_build_object('trip',trip_id,'container',v_trip.container,'status',v_status,
            'review_reason',btrim(reason)),idempotency_key)
    RETURNING id INTO v_event;
    INSERT INTO sokhach.trip_info_rev(trip_id,customer_id,debt_month,event_date,container,carrier,shipper,origin,destination,status,created_by_event)
    VALUES (v_trip.id,customer_id,v_trip.debt_month,v_trip.event_date,v_trip.container,v_trip.carrier,v_trip.shipper,v_trip.origin,v_trip.destination,v_status,v_event);
    IF v_status='confirmed' THEN v_changes := sokhach.reallocate(customer_id,idempotency_key); END IF;
    RETURN sokhach._finish_command(customer_id,idempotency_key,v_payload,
        jsonb_build_object('trip_id',trip_id,'status',v_status,'reallocated',v_changes));
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
        RETURN jsonb_build_object('status','NO_BASELINE','customer_id',customer_id,
            'version',v_version,'months','[]'::jsonb,'source_exceptions',v_flags,
            'total_outstanding_vnd',NULL);
    END IF;
    WITH visible_months AS (
      SELECT debt_month,outstanding_vnd,end_of_month_vnd FROM sokhach.v_month_chain
      WHERE v_month_chain.customer_id=get_ledger.customer_id
      UNION ALL
      SELECT DISTINCT t.debt_month,0::bigint,
          coalesce((SELECT sum(v.outstanding_vnd)::bigint FROM sokhach.v_outstanding_month v
              WHERE v.customer_id=t.customer_id AND v.debt_month<=t.debt_month),0)
      FROM sokhach.v_trip_current t WHERE NOT t.deleted AND t.customer_id=get_ledger.customer_id
        AND NOT EXISTS (SELECT 1 FROM sokhach.v_month_chain v
            WHERE v.customer_id=t.customer_id AND v.debt_month=t.debt_month)
    )
    SELECT coalesce(jsonb_agg(jsonb_build_object('month',debt_month,
        'outstanding_vnd',outstanding_vnd::text,'end_of_month_vnd',end_of_month_vnd::text,
        'prior_months_vnd',(end_of_month_vnd-outstanding_vnd)::text,
        'charges_vnd',(coalesce((SELECT sum(CASE WHEN p.unit_price_vnd IS NOT NULL
            THEN p.unit_price_vnd+coalesce(p.other_fee_vnd,0)
            WHEN t.container IS NULL OR t.container='' THEN p.other_fee_vnd END)
            FROM sokhach.v_trip_current t LEFT JOIN LATERAL
              (SELECT unit_price_vnd,other_fee_vnd FROM sokhach.trip_price_rev
               WHERE trip_id=t.id ORDER BY id DESC LIMIT 1) p ON true
            WHERE t.customer_id=get_ledger.customer_id AND t.debt_month=visible_months.debt_month AND NOT t.deleted AND t.status='confirmed'),0)
            +coalesce((SELECT sum(a.amount_vnd) FROM sokhach.v_adjustment_current a
                WHERE a.customer_id=get_ledger.customer_id AND a.debt_month=visible_months.debt_month),0)
            +coalesce((SELECT sum(o.amount_vnd) FROM sokhach.opening_balance o
                JOIN sokhach.cutover_customer cc ON (cc.customer_id,cc.cutover_id)=(o.customer_id,o.cutover_id)
                JOIN sokhach.cutover c ON c.id=cc.cutover_id
                WHERE o.customer_id=get_ledger.customer_id AND o.debt_month=visible_months.debt_month
                  AND cc.status='active' AND c.status='active'),0))::text,
        'received_vnd',(coalesce((SELECT sum(l.amount_vnd) FROM sokhach.v_receipt_line_active l
            WHERE l.customer_id=get_ledger.customer_id AND l.debt_month=visible_months.debt_month),0)
            -coalesce((SELECT sum(o.amount_vnd) FROM sokhach.v_offset_outgoing o
                WHERE o.customer_id=get_ledger.customer_id AND o.debt_month=visible_months.debt_month),0))::text)
        ORDER BY debt_month),'[]'::jsonb),coalesce(sum(outstanding_vnd),0)
    INTO v_months,v_total FROM visible_months;
    SELECT coalesce(jsonb_agg(jsonb_build_object('id',t.id,'month',t.debt_month,
        'event_date',t.event_date,'container',t.container,'carrier',t.carrier,'shipper',t.shipper,'status',t.status,'booking',t.booking,
        'review_reason',coalesce((SELECT e."after"->>'review_reason' FROM sokhach.trip_info_rev r
            JOIN sokhach.event e ON e.id=r.created_by_event WHERE r.trip_id=t.id ORDER BY r.id DESC LIMIT 1),
            (SELECT x->>'review_reason' FROM sokhach.trip tr JOIN sokhach.event e ON e.id=tr.created_by_event
            CROSS JOIN LATERAL jsonb_array_elements(e."after"->'trips') x
            WHERE tr.id=t.id AND x->>'trip_id'=t.id::text)),
        'origin',t.origin,'destination',t.destination,'note',t.note,
        'unit_price_vnd',p.unit_price_vnd::text,'other_fee_vnd',p.other_fee_vnd::text,
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
        'historical',true,'editable',l.kind='trip','current',CASE WHEN l.kind='trip' THEN cur.data END) ORDER BY l.debt_month,l.id),'[]'::jsonb)
    INTO v_legacy FROM sokhach.legacy_row l
    CROSS JOIN LATERAL (SELECT sokhach._legacy_current(l.id) AS data) cur
    JOIN sokhach.cutover_customer cc ON (cc.customer_id,cc.cutover_id)=(l.customer_id,l.cutover_id)
    JOIN sokhach.cutover c ON c.id=cc.cutover_id
    WHERE l.customer_id=get_ledger.customer_id AND cc.status='active' AND c.status='active' AND NOT (cur.data->>'deleted')::boolean;
    SELECT coalesce(jsonb_agg(jsonb_build_object('id',id,'kind',kind,'actor',actor,
        'label',CASE kind WHEN 'trip_edit' THEN 'Sửa chuyến' WHEN 'trip_delete' THEN 'Xóa chuyến'
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
    RETURN jsonb_build_object('status','active','customer_id',customer_id,
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

COMMIT;
