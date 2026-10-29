-- DRAFT V7 functions. Load only after schema-draft.sql in a disposable test DB.
SET ROLE sokhach_owner;

CREATE OR REPLACE FUNCTION sokhach._fee_lines(p_trip bigint,p_legacy bigint) RETURNS jsonb
LANGUAGE sql STABLE SET search_path=pg_catalog,sokhach,pg_temp AS $$
 SELECT coalesce(jsonb_agg(jsonb_build_object('id',id,'fee_type_id',fee_type_id,
   'amount_vnd',amount_vnd::text,'note',note) ORDER BY id),'[]'::jsonb)
 FROM sokhach.trip_fee_line WHERE voided_by_event IS NULL
   AND (trip_id=p_trip OR legacy_row_id=p_legacy)
$$;
CREATE OR REPLACE FUNCTION sokhach._fee_columns(p_customer bigint) RETURNS jsonb
LANGUAGE sql STABLE SET search_path=pg_catalog,sokhach,pg_temp AS $$
 SELECT coalesce(jsonb_agg(jsonb_build_object('fee_type_id',fee_type_id,'position',position) ORDER BY position),'[]')
 FROM sokhach.book_fee_column WHERE customer_id=p_customer
$$;

-- Trip adjustments follow current information; pending/deleted trips contribute nothing.
-- A deleted month adjustment and its reversal sum to 0 in the same month, so both are hidden (XOA-DC-THANG-01).
CREATE OR REPLACE VIEW sokhach.v_adjustment_current AS
SELECT a.id,a.customer_id,coalesce(t.debt_month,a.debt_month) AS debt_month,
       a.trip_id,a.legacy_row_id,a.amount_vnd,a.field,a.new_value_vnd,a.note,a.actor,a.at,a.created_by_event
FROM sokhach.adjustment a LEFT JOIN sokhach.v_trip_current t ON t.id=a.trip_id
WHERE NOT a.fee_absorbed AND (a.trip_id IS NULL OR (NOT t.deleted AND t.status='confirmed'))
  AND a.reverses_adjustment_id IS NULL
  AND NOT EXISTS (SELECT 1 FROM sokhach.adjustment r WHERE r.reverses_adjustment_id=a.id);

-- Keep source schema draft scoped to P1-2; align runtime read view with JS truthiness.
CREATE OR REPLACE VIEW sokhach.v_outstanding_month AS
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

CREATE FUNCTION sokhach._actor() RETURNS text
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, sokhach, pg_temp AS $$
DECLARE v text := nullif(btrim(current_setting('sokhach.actor', true)), '');
BEGIN
    IF v IS NULL THEN RAISE EXCEPTION 'ACTOR_REQUIRED'; END IF;
    RETURN v;
END $$;

-- Unicode White_Space, including NBSP and narrow NBSP, independent of DB locale.
CREATE FUNCTION sokhach._normalize_key(p_value text) RETURNS text
LANGUAGE sql IMMUTABLE SET search_path = pg_catalog, sokhach, pg_temp AS $$
    SELECT upper(regexp_replace(coalesce(p_value,''),
        U&'[\0009-\000D\0020\0085\00A0\1680\2000-\200A\2028\2029\202F\205F\3000]', '', 'g'))
$$;
CREATE FUNCTION sokhach._booking_key(p_booking text,p_container text,p_date date) RETURNS text
LANGUAGE sql IMMUTABLE SET search_path = pg_catalog, sokhach, pg_temp AS $$
    SELECT CASE WHEN sokhach._normalize_key(p_booking) ~ '[[:alnum:]]'
        THEN sokhach._normalize_key(p_booking)
        ELSE 'ALT:' || sokhach._normalize_key(p_container) || ':' || coalesce(to_char(p_date,'YYYYMMDD'),'UNKNOWN') END
$$;

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

-- Strict ISO edit dates; legacy source cells use this only behind exception handling.
CREATE FUNCTION sokhach._trip_date(p_value text) RETURNS date
LANGUAGE plpgsql SET search_path=pg_catalog,sokhach,pg_temp AS $$
DECLARE v date;
BEGIN
    IF p_value IS NULL OR p_value !~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$' THEN RAISE EXCEPTION 'INVALID_DATE'; END IF;
    BEGIN v := p_value::date;
    EXCEPTION WHEN invalid_datetime_format OR datetime_field_overflow THEN RAISE EXCEPTION 'INVALID_DATE'; END;
    IF NOT isfinite(v) OR to_char(v,'YYYY-MM-DD')<>p_value THEN RAISE EXCEPTION 'INVALID_DATE'; END IF;
    IF v>(clock_timestamp() AT TIME ZONE 'Asia/Ho_Chi_Minh')::date THEN RAISE EXCEPTION 'FUTURE_DATE'; END IF;
    RETURN v;
END $$;

CREATE FUNCTION sokhach.edit_trip_info(customer_id bigint,expected_version bigint,idempotency_key text,
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
    -- Snapshot shows the effective fee: latest price revision plus every fee delta,
    -- including deltas older than the revision (a price edit never absorbs them).
    SELECT jsonb_build_object('unit_price_vnd',CASE WHEN p.unit_price_vnd IS NOT NULL
          THEN (a.amount_vnd-f.fee)::text END,
      'other_fee_vnd',f.fee_display::text,
      'amount_vnd',CASE WHEN t.status='confirmed' THEN a.amount_vnd::text END)
    INTO v_price FROM (SELECT * FROM sokhach.trip_price_rev WHERE trip_price_rev.trip_id=t.id ORDER BY id DESC LIMIT 1) p
    LEFT JOIN LATERAL (SELECT coalesce(p.other_fee_vnd,0)
        +coalesce((SELECT sum(x.amount_vnd) FROM sokhach.adjustment x WHERE x.trip_id=t.id AND x.field='other_fee_vnd' AND NOT x.fee_absorbed),0) AS fee,
        CASE WHEN p.other_fee_vnd IS NULL
          AND NOT EXISTS (SELECT 1 FROM sokhach.adjustment x WHERE x.trip_id=t.id AND x.field='other_fee_vnd' AND NOT x.fee_absorbed)
        THEN NULL ELSE coalesce(p.other_fee_vnd,0)
          +coalesce((SELECT sum(x.amount_vnd) FROM sokhach.adjustment x WHERE x.trip_id=t.id AND x.field='other_fee_vnd' AND NOT x.fee_absorbed),0) END AS fee_display) f ON true
    CROSS JOIN LATERAL (SELECT (CASE WHEN p.unit_price_vnd IS NOT NULL THEN p.unit_price_vnd+coalesce(p.other_fee_vnd,0)
        WHEN coalesce(t.container,'')='' THEN p.other_fee_vnd END)
        +coalesce((SELECT sum(x.amount_vnd) FROM sokhach.adjustment x WHERE x.trip_id=t.id AND NOT x.fee_absorbed),0) AS amount_vnd) a;
    INSERT INTO sokhach.event(customer_id,kind,actor,"before","after",idempotency_key)
      VALUES(customer_id,'trip_delete',sokhach._actor(),jsonb_build_object('trip',to_jsonb(t)||coalesce(v_price,'{}')||jsonb_build_object('fee_lines',sokhach._fee_lines(t.id,NULL))),
        jsonb_build_object('trip',jsonb_build_object('id',t.id,'deleted',true)),idempotency_key) RETURNING id INTO v_event;
    INSERT INTO sokhach.trip_info_rev(trip_id,customer_id,debt_month,event_date,container,carrier,shipper,origin,destination,status,deleted,created_by_event)
      VALUES(t.id,customer_id,t.debt_month,t.event_date,t.container,t.carrier,t.shipper,t.origin,t.destination,t.status,true,v_event);
    v_changes:=sokhach.reallocate(customer_id,idempotency_key);
    RETURN sokhach._finish_command(customer_id,idempotency_key,v_payload,jsonb_build_object('trip_id',t.id,'deleted',true,'reallocated',v_changes));
END $$;

-- Source display is evidence, never trusted input: unreadable cells stay NULL.
CREATE FUNCTION sokhach._legacy_current(p_id bigint) RETURNS jsonb
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
      v_old:=v_old||jsonb_build_object('other_fee_vnd',v_fee::text,'fee_lines',sokhach._fee_lines(NULL,l.id)); v_new:=v_old;
    END IF;
    IF (v_old->>'deleted')::boolean THEN RAISE EXCEPTION 'LEGACY_NOT_FOUND'; END IF;
    v_old_month:=(v_old->>'month')::date; v_month:=v_old_month; v_old_count:=(v_old->>'counted_vnd')::bigint;
    PERFORM sokhach._month_open(customer_id,v_old_month,clock_timestamp());
    IF NOT p_delete AND field='other_fee_vnd' AND v_old->>'unit_price_vnd' IS NULL
    THEN RAISE EXCEPTION 'LEGACY_NO_UNIT_PRICE'; END IF;
    IF p_delete THEN v_count:=0; v_new:=v_new||jsonb_build_object('deleted',true);
    ELSE
      IF field IS NULL OR field NOT IN ('container','carrier','shipper','origin','destination','event_date','unit_price_vnd','other_fee_vnd') THEN RAISE EXCEPTION 'INVALID_FIELD'; END IF;
      v_value:=nullif(btrim(value),'');
      IF field IN ('unit_price_vnd','other_fee_vnd') THEN
        IF v_value IS NOT NULL AND v_value !~ (CASE WHEN field='other_fee_vnd' THEN '^-?[0-9]+$' ELSE '^[0-9]+$' END) THEN RAISE EXCEPTION 'INVALID_VND'; END IF;
        v_value:=((v_value)::bigint)::text;
        IF p_fee_event IS NULL AND field='other_fee_vnd' AND v_value='0' THEN v_value:=NULL; END IF;
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
EXCEPTION WHEN numeric_value_out_of_range THEN
    IF p_fee_event IS NOT NULL THEN RAISE EXCEPTION 'FEE_AMOUNT_INVALID'; END IF;
    RAISE EXCEPTION 'INVALID_VND';
END $$;
CREATE OR REPLACE FUNCTION sokhach._change_legacy(customer_id bigint,expected_version bigint,idempotency_key text,
    legacy_row_id bigint,field text,value text,p_delete boolean) RETURNS jsonb
LANGUAGE sql SECURITY DEFINER SET search_path=pg_catalog,sokhach,pg_temp AS $$
 SELECT sokhach._change_legacy(customer_id,expected_version,idempotency_key,legacy_row_id,field,value,p_delete,NULL)
$$;
CREATE FUNCTION sokhach.edit_legacy_trip(customer_id bigint,expected_version bigint,idempotency_key text,legacy_row_id bigint,field text,value text)
RETURNS jsonb LANGUAGE sql SECURITY DEFINER SET search_path=pg_catalog,sokhach,pg_temp AS $$
    SELECT sokhach._change_legacy(customer_id,expected_version,idempotency_key,legacy_row_id,field,value,false)
$$;
CREATE FUNCTION sokhach.delete_legacy_trip(customer_id bigint,expected_version bigint,idempotency_key text,legacy_row_id bigint)
RETURNS jsonb LANGUAGE sql SECURITY DEFINER SET search_path=pg_catalog,sokhach,pg_temp AS $$
    SELECT sokhach._change_legacy(customer_id,expected_version,idempotency_key,legacy_row_id,NULL,NULL,true)
$$;

-- Legacy commands replace only the three compatibility types, then sync cache once.
CREATE OR REPLACE FUNCTION sokhach._compat_trip_fee(p_customer bigint,p_trip bigint,p_fee bigint,p_event bigint) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,sokhach,pg_temp AS $$
DECLARE v_type bigint; v_old bigint; v_count bigint; v_existing_type bigint;
BEGIN
    SELECT sum(amount_vnd)::bigint,count(*),min(fee_type_id) INTO v_old,v_count,v_existing_type FROM sokhach.trip_fee_line
      WHERE trip_id=p_trip AND voided_by_event IS NULL;
    IF v_old IS NOT DISTINCT FROM nullif(p_fee,0) THEN
        PERFORM sokhach._sync_trip_fee(p_trip,p_event);
        RETURN;
    END IF;
    IF EXISTS (SELECT 1 FROM sokhach.trip_fee_line l JOIN sokhach.fee_type f ON f.id=l.fee_type_id
        WHERE l.trip_id=p_trip AND l.voided_by_event IS NULL
          AND coalesce(f.system_key,'') NOT IN ('other','discount','initial'))
    THEN RAISE EXCEPTION 'FEE_LINES_TYPED'; END IF;
    IF p_fee IS NOT NULL AND p_fee<>0 THEN
      SELECT id INTO v_type FROM sokhach.fee_type
        WHERE system_key=CASE WHEN p_fee<0 THEN 'discount' ELSE 'other' END;
    END IF;
    IF v_old IS DISTINCT FROM nullif(p_fee,0)
       OR v_count<>(CASE WHEN p_fee IS NULL OR p_fee=0 THEN 0 ELSE 1 END)
       OR (v_count=1 AND v_existing_type IS DISTINCT FROM v_type) THEN
      UPDATE sokhach.trip_fee_line SET voided_by_event=p_event
        WHERE trip_id=p_trip AND voided_by_event IS NULL;
      IF p_fee IS NOT NULL AND p_fee<>0 THEN
        INSERT INTO sokhach.trip_fee_line(customer_id,trip_id,fee_type_id,amount_vnd,created_by_event)
          VALUES(p_customer,p_trip,v_type,p_fee,p_event);
      END IF;
    END IF;
    PERFORM sokhach._sync_trip_fee(p_trip,p_event);
END $$;

CREATE OR REPLACE FUNCTION sokhach.edit_trip_price(customer_id bigint, expected_version bigint,
    idempotency_key text, trip_id bigint, unit_price_vnd bigint, other_fee_vnd bigint)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, sokhach, pg_temp AS $$
DECLARE v_payload jsonb := jsonb_build_object('command','edit_trip_price','trip_id',trip_id,
        'unit_price_vnd',unit_price_vnd,'other_fee_vnd',other_fee_vnd);
        v_retry jsonb; v_trip sokhach.v_trip_current%ROWTYPE; v_old sokhach.trip_price_rev%ROWTYPE;
        v_now timestamptz; v_event bigint; v_rev bigint; v_changes jsonb;
BEGIN
    v_retry := sokhach._begin_command(customer_id,expected_version,idempotency_key,v_payload);
    IF v_retry IS NOT NULL THEN RETURN v_retry; END IF;
    PERFORM sokhach._baseline(customer_id);
    v_now := clock_timestamp();
    SELECT * INTO v_trip FROM sokhach.v_trip_current v WHERE v.id=trip_id AND v.customer_id=edit_trip_price.customer_id AND NOT v.deleted;
    IF NOT FOUND THEN RAISE EXCEPTION 'TRIP_NOT_FOUND'; END IF;
    IF v_trip.status<>'confirmed' THEN RAISE EXCEPTION 'TRIP_PENDING_REVIEW'; END IF;
    PERFORM sokhach._month_open(customer_id,v_trip.debt_month,v_now);
    IF unit_price_vnd < 0 OR
       coalesce(unit_price_vnd,0)::numeric+coalesce(other_fee_vnd,0)::numeric NOT BETWEEN -9223372036854775808 AND 9223372036854775807
    THEN RAISE EXCEPTION 'INVALID_VND'; END IF;
    SELECT * INTO v_old FROM sokhach.trip_price_rev WHERE trip_price_rev.trip_id=edit_trip_price.trip_id
        ORDER BY id DESC LIMIT 1;
    IF (v_old.unit_price_vnd,v_old.other_fee_vnd) IS NOT DISTINCT FROM
       (unit_price_vnd,other_fee_vnd) THEN RAISE EXCEPTION 'NO_CHANGE'; END IF;
    v_rev := nextval(pg_get_serial_sequence('sokhach.trip_price_rev','id'));
    INSERT INTO sokhach.event(customer_id,kind,actor,"before","after",idempotency_key)
    VALUES (customer_id,'price_edit',sokhach._actor(),
        jsonb_build_object('price',jsonb_build_object('trip_id',trip_id,'revision_id',v_old.id,
            'unit_price_vnd',v_old.unit_price_vnd,'other_fee_vnd',v_old.other_fee_vnd)),
        jsonb_build_object('price',jsonb_build_object('trip_id',trip_id,
            'unit_price_vnd',unit_price_vnd,'other_fee_vnd',other_fee_vnd)),idempotency_key)
    RETURNING id INTO v_event;
    INSERT INTO sokhach.trip_price_rev(id,trip_id,customer_id,unit_price_vnd,created_by_event)
    OVERRIDING SYSTEM VALUE VALUES (v_rev,trip_id,customer_id,unit_price_vnd,v_event);
    PERFORM sokhach._compat_trip_fee(customer_id,trip_id,other_fee_vnd,v_event);
    SELECT p.id INTO v_rev FROM sokhach.trip_price_rev p WHERE p.trip_id=edit_trip_price.trip_id ORDER BY p.id DESC LIMIT 1;
    v_changes := sokhach.reallocate(customer_id,idempotency_key);
    RETURN sokhach._finish_command(customer_id,idempotency_key,v_payload,
        jsonb_build_object('trip_id',trip_id,'revision_id',v_rev,'reallocated',v_changes));
END $$;

CREATE OR REPLACE FUNCTION sokhach.adjust_trip(customer_id bigint, expected_version bigint,
    idempotency_key text, trip_id bigint, new_amount_vnd bigint, note text,
    field text DEFAULT NULL, new_value_vnd bigint DEFAULT NULL)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, sokhach, pg_temp AS $$
DECLARE v_payload jsonb := jsonb_build_object('command','adjust_trip','trip_id',trip_id,
        'new_amount_vnd',new_amount_vnd,'note',note) ||
        CASE WHEN field IS NULL AND new_value_vnd IS NULL THEN '{}'::jsonb
        ELSE jsonb_build_object('field',field,'new_value_vnd',new_value_vnd) END;
        v_retry jsonb; v_trip sokhach.v_trip_current%ROWTYPE; v_base bigint; v_old bigint;
        v_delta bigint; v_id bigint; v_event bigint; v_changes jsonb;
        v_price sokhach.trip_price_rev%ROWTYPE; v_fee bigint; v_field_old bigint;
BEGIN
    v_retry := sokhach._begin_command(customer_id,expected_version,idempotency_key,v_payload);
    IF v_retry IS NOT NULL THEN RETURN v_retry; END IF;
    PERFORM sokhach._baseline(customer_id);
    SELECT * INTO v_trip FROM sokhach.v_trip_current v WHERE v.id=trip_id AND v.customer_id=adjust_trip.customer_id AND NOT v.deleted;
    IF v_trip.status<>'confirmed' THEN RAISE EXCEPTION 'TRIP_PENDING_REVIEW'; END IF;
    IF NOT FOUND THEN RAISE EXCEPTION 'TRIP_NOT_FOUND'; END IF;
    PERFORM sokhach._month_open(customer_id,v_trip.debt_month,clock_timestamp());
    SELECT * INTO v_price FROM sokhach.trip_price_rev p
    WHERE p.trip_id=adjust_trip.trip_id ORDER BY p.id DESC LIMIT 1;
    v_base := CASE WHEN v_price.unit_price_vnd IS NOT NULL
        THEN v_price.unit_price_vnd+coalesce(v_price.other_fee_vnd,0)
        WHEN v_trip.container IS NULL OR v_trip.container='' THEN v_price.other_fee_vnd END;
    IF v_base IS NULL THEN RAISE EXCEPTION 'TRIP_HAS_NO_PRICE'; END IF;
    SELECT v_base+coalesce(sum(amount_vnd),0)::bigint INTO v_old
    FROM sokhach.v_adjustment_current a WHERE a.customer_id=adjust_trip.customer_id
      AND a.trip_id=adjust_trip.trip_id;
    IF field IS NOT NULL OR new_value_vnd IS NOT NULL THEN
        IF field='other_fee_vnd' AND EXISTS (SELECT 1 FROM sokhach.trip_fee_line l JOIN sokhach.fee_type f ON f.id=l.fee_type_id
            WHERE l.trip_id=adjust_trip.trip_id AND l.voided_by_event IS NULL
              AND coalesce(f.system_key,'') NOT IN ('other','discount','initial'))
        THEN RAISE EXCEPTION 'FEE_LINES_TYPED'; END IF;
        IF field IS NULL OR field NOT IN ('unit_price_vnd','other_fee_vnd')
           OR new_value_vnd IS NULL OR (field='unit_price_vnd' AND new_value_vnd<0) OR new_amount_vnd IS NOT NULL
        THEN RAISE EXCEPTION 'INVALID_ADJUSTMENT'; END IF;
        -- Effective fee = latest price revision fee plus every fee delta. A price edit
        -- never absorbs older deltas, so a typed intent lands on the displayed value.
        SELECT coalesce(v_price.other_fee_vnd,0)
            +coalesce(sum(a.amount_vnd) FILTER (WHERE a.field='other_fee_vnd'),0)
        INTO v_fee
        FROM sokhach.v_adjustment_current a WHERE a.customer_id=adjust_trip.customer_id
          AND a.trip_id=adjust_trip.trip_id;
        v_field_old := CASE field WHEN 'unit_price_vnd' THEN v_old-v_fee ELSE v_fee END;
        new_amount_vnd := CASE field WHEN 'unit_price_vnd' THEN new_value_vnd+v_fee
            ELSE v_old-v_fee+new_value_vnd END;
    END IF;
    IF new_amount_vnd IS NULL OR (field IS DISTINCT FROM 'other_fee_vnd' AND new_amount_vnd < 0)
    THEN RAISE EXCEPTION 'INVALID_VND'; END IF;
    v_delta := new_amount_vnd-v_old;
    IF v_delta=0 THEN RAISE EXCEPTION 'NO_CHANGE'; END IF;
    v_id := CASE WHEN field='other_fee_vnd' THEN NULL
        ELSE nextval(pg_get_serial_sequence('sokhach.adjustment','id')) END;
    INSERT INTO sokhach.event(customer_id,kind,actor,"before","after",idempotency_key)
    VALUES (customer_id,'adjust_trip',sokhach._actor(),
        jsonb_build_object('trip',trip_id,'amount_vnd',v_old::text,'field',field,'new_value_vnd',v_field_old::text),
        jsonb_build_object('adjustment',CASE WHEN field='other_fee_vnd' THEN NULL ELSE v_id END,'trip_id',trip_id,'old_amount_vnd',v_old::text,
            'new_amount_vnd',new_amount_vnd::text,'delta_vnd',v_delta::text,'note',note,
            'field',field,'new_value_vnd',new_value_vnd::text),idempotency_key)
    RETURNING id INTO v_event;
    IF field='other_fee_vnd' THEN
        PERFORM sokhach._compat_trip_fee(customer_id,trip_id,new_value_vnd,v_event);
        v_changes := sokhach.reallocate(customer_id,idempotency_key);
        RETURN sokhach._finish_command(customer_id,idempotency_key,v_payload,
            jsonb_build_object('trip_id',trip_id,'fee_vnd',new_value_vnd::text,'delta_vnd',v_delta::text,'reallocated',v_changes));
    END IF;
    INSERT INTO sokhach.adjustment(id,customer_id,debt_month,trip_id,amount_vnd,note,actor,created_by_event,field,new_value_vnd)
    OVERRIDING SYSTEM VALUE VALUES (v_id,customer_id,v_trip.origin_month,trip_id,v_delta,note,
        sokhach._actor(),v_event,field,new_value_vnd);
    v_changes := sokhach.reallocate(customer_id,idempotency_key);
    RETURN sokhach._finish_command(customer_id,idempotency_key,v_payload,
        jsonb_build_object('adjustment_id',v_id,'delta_vnd',v_delta::text,'reallocated',v_changes));
EXCEPTION WHEN numeric_value_out_of_range THEN RAISE EXCEPTION 'INVALID_VND';
    END $$;

CREATE FUNCTION sokhach.adjust_month(customer_id bigint, expected_version bigint,
    idempotency_key text, debt_month date, amount_vnd bigint, note text)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, sokhach, pg_temp AS $$
DECLARE v_payload jsonb := jsonb_build_object('command','adjust_month','month',debt_month,
        'amount_vnd',amount_vnd,'note',note);
        v_retry jsonb; v_id bigint; v_event bigint; v_changes jsonb;
BEGIN
    v_retry := sokhach._begin_command(customer_id,expected_version,idempotency_key,v_payload);
    IF v_retry IS NOT NULL THEN RETURN v_retry; END IF;
    PERFORM sokhach._baseline(customer_id);
    IF debt_month IS NULL OR extract(day FROM debt_month) <> 1 OR amount_vnd IS NULL OR amount_vnd=0
    THEN RAISE EXCEPTION 'INVALID_ADJUSTMENT'; END IF;
    IF NOT EXISTS (SELECT 1 FROM sokhach.opening_balance o
        JOIN sokhach.cutover_customer cc USING (customer_id,cutover_id)
        JOIN sokhach.cutover c ON c.id=cc.cutover_id
        WHERE o.customer_id=adjust_month.customer_id AND o.debt_month=adjust_month.debt_month
          AND cc.status='active' AND c.status='active')
       AND NOT EXISTS (SELECT 1 FROM sokhach.v_trip_current t
           WHERE t.customer_id=adjust_month.customer_id AND t.debt_month=adjust_month.debt_month AND NOT t.deleted AND t.status='confirmed')
       AND NOT EXISTS (SELECT 1 FROM sokhach.v_adjustment_current a
           WHERE a.customer_id=adjust_month.customer_id AND a.debt_month=adjust_month.debt_month)
    THEN RAISE EXCEPTION 'MONTH_NOT_FOUND'; END IF;
    PERFORM sokhach._month_open(customer_id,debt_month,clock_timestamp());
    v_id := nextval(pg_get_serial_sequence('sokhach.adjustment','id'));
    INSERT INTO sokhach.event(customer_id,kind,actor,"before","after",idempotency_key)
    VALUES (customer_id,'adjust_month',sokhach._actor(),
        jsonb_build_object('month',debt_month,'amount_vnd','0'),
        jsonb_build_object('adjustment',v_id,'month',debt_month,'amount_vnd',amount_vnd::text,'note',note),idempotency_key)
    RETURNING id INTO v_event;
    INSERT INTO sokhach.adjustment(id,customer_id,debt_month,trip_id,amount_vnd,note,actor,created_by_event)
    OVERRIDING SYSTEM VALUE VALUES (v_id,customer_id,debt_month,NULL,amount_vnd,note,sokhach._actor(),v_event);
    v_changes := sokhach.reallocate(customer_id,idempotency_key);
    RETURN sokhach._finish_command(customer_id,idempotency_key,v_payload,
        jsonb_build_object('adjustment_id',v_id,'reallocated',v_changes));
EXCEPTION WHEN numeric_value_out_of_range THEN RAISE EXCEPTION 'INVALID_VND';
END $$;

-- XOA-DC-THANG-01: xóa điều chỉnh cả tháng bằng một dòng đảo dấu trỏ về dòng gốc; tháng phải đang mở.
CREATE OR REPLACE FUNCTION sokhach.delete_month_adjustment(customer_id bigint, expected_version bigint,
    idempotency_key text, adjustment_id bigint)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, sokhach, pg_temp AS $$
DECLARE v_payload jsonb := jsonb_build_object('command','delete_month_adjustment','adjustment_id',adjustment_id);
        v_retry jsonb; a sokhach.adjustment%ROWTYPE; v_id bigint; v_event bigint; v_changes jsonb;
BEGIN
    v_retry := sokhach._begin_command(customer_id,expected_version,idempotency_key,v_payload);
    IF v_retry IS NOT NULL THEN RETURN v_retry; END IF;
    PERFORM sokhach._baseline(customer_id);
    SELECT a0.* INTO a FROM sokhach.adjustment a0
    WHERE a0.id=delete_month_adjustment.adjustment_id AND a0.customer_id=delete_month_adjustment.customer_id
      AND a0.trip_id IS NULL AND a0.legacy_row_id IS NULL AND a0.field IS NULL AND NOT a0.fee_absorbed
      AND a0.reverses_adjustment_id IS NULL
      AND NOT EXISTS (SELECT 1 FROM sokhach.adjustment r WHERE r.reverses_adjustment_id=a0.id);
    IF NOT FOUND THEN RAISE EXCEPTION 'ADJUSTMENT_NOT_FOUND'; END IF;
    PERFORM sokhach._month_open(customer_id,a.debt_month,clock_timestamp());
    v_id := nextval(pg_get_serial_sequence('sokhach.adjustment','id'));
    INSERT INTO sokhach.event(customer_id,kind,actor,"before","after",idempotency_key)
    VALUES (customer_id,'adjust_month_delete',sokhach._actor(),
        jsonb_build_object('adjustment',jsonb_build_object('id',a.id,'month',a.debt_month,
            'amount_vnd',a.amount_vnd::text,'note',a.note,'actor',a.actor,'at',a.at)),
        jsonb_build_object('adjustment',jsonb_build_object('id',a.id,'month',a.debt_month,
            'amount_vnd','0','deleted',true,'reversal',v_id)),idempotency_key)
    RETURNING id INTO v_event;
    INSERT INTO sokhach.adjustment(id,customer_id,debt_month,trip_id,amount_vnd,note,actor,created_by_event,reverses_adjustment_id)
    OVERRIDING SYSTEM VALUE VALUES (v_id,customer_id,a.debt_month,NULL,-a.amount_vnd,a.note,sokhach._actor(),v_event,a.id);
    v_changes := sokhach.reallocate(customer_id,idempotency_key);
    RETURN sokhach._finish_command(customer_id,idempotency_key,v_payload,
        jsonb_build_object('adjustment_id',a.id,'reversal_id',v_id,'reallocated',v_changes));
END $$;

-- Caller holds customer lock after this returns. NULL means a new command.
CREATE FUNCTION sokhach._begin_command(p_customer bigint, p_version bigint, p_key text, p_payload jsonb)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, sokhach, pg_temp AS $$
DECLARE v_version bigint; v_saved sokhach.idempotency%ROWTYPE;
        v_hash text := encode(sha256(convert_to(p_payload::text, 'UTF8')), 'hex');
BEGIN
    PERFORM sokhach._actor();
    IF p_key IS NULL OR btrim(p_key) = '' OR left(p_key, 9) = chr(31) || 'cutover:'
       OR p_payload IS NULL THEN
        RAISE EXCEPTION 'INVALID_COMMAND';
    END IF;
    SELECT version INTO v_version FROM sokhach.customer WHERE id = p_customer FOR UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION 'CUSTOMER_NOT_FOUND'; END IF;
    SELECT * INTO v_saved FROM sokhach.idempotency WHERE customer_id = p_customer AND key = p_key;
    IF FOUND THEN
        IF v_saved.request_hash <> v_hash THEN RAISE EXCEPTION 'IDEMPOTENCY_CONFLICT'; END IF;
        RETURN v_saved.result;
    END IF;
    IF p_version IS DISTINCT FROM v_version THEN RAISE EXCEPTION 'STALE_LEDGER'; END IF;
    RETURN NULL;
END $$;

CREATE FUNCTION sokhach._finish_command(p_customer bigint, p_key text, p_payload jsonb, p_result jsonb)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, sokhach, pg_temp AS $$
DECLARE v_version bigint; v_result jsonb;
BEGIN
    UPDATE sokhach.customer SET version = version + 1 WHERE id = p_customer
        RETURNING version INTO v_version;
    v_result := p_result || jsonb_build_object('version', v_version);
    INSERT INTO sokhach.idempotency(customer_id, key, request_hash, result)
    VALUES (p_customer, p_key, encode(sha256(convert_to(p_payload::text, 'UTF8')), 'hex'), v_result);
    RETURN v_result;
END $$;

CREATE FUNCTION sokhach._baseline(p_customer bigint) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, sokhach, pg_temp AS $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM sokhach.cutover_customer cc
        JOIN sokhach.cutover c ON c.id = cc.cutover_id
        WHERE cc.customer_id = p_customer AND cc.status = 'active' AND c.status = 'active'
    ) THEN RAISE EXCEPTION 'NO_BASELINE'; END IF;
END $$;

CREATE FUNCTION sokhach._month_open(p_customer bigint, p_month date, p_now timestamptz)
RETURNS void LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, sokhach, pg_temp AS $$
DECLARE v_locked boolean;
BEGIN
    IF p_month IS NULL OR extract(day FROM p_month) <> 1 THEN RAISE EXCEPTION 'INVALID_MONTH'; END IF;
    SELECT locked INTO v_locked FROM sokhach.month_state
    WHERE customer_id = p_customer AND month = p_month;
    IF coalesce(v_locked, p_month <> date_trunc('month', p_now AT TIME ZONE 'Asia/Ho_Chi_Minh')::date)
    THEN RAISE EXCEPTION 'MONTH_LOCKED'; END IF;
END $$;

CREATE FUNCTION sokhach._lines(p_receipt bigint) RETURNS jsonb
LANGUAGE sql SECURITY DEFINER SET search_path = pg_catalog, sokhach, pg_temp AS $$
    SELECT coalesce(jsonb_agg(jsonb_build_object('id', id, 'month', debt_month,
        'kind', kind, 'amount_vnd', amount_vnd::text)
        ORDER BY debt_month, CASE kind WHEN 'debt' THEN 0 ELSE 1 END, id), '[]'::jsonb)
    FROM sokhach.receipt_line
    WHERE receipt_id = p_receipt AND superseded_by_event IS NULL
$$;

CREATE FUNCTION sokhach._check_allocations(p_customer bigint) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, sokhach, pg_temp AS $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM sokhach.receipt r LEFT JOIN sokhach.receipt_line l
          ON l.receipt_id = r.id AND l.customer_id = r.customer_id
             AND l.superseded_by_event IS NULL
        WHERE r.customer_id = p_customer
        GROUP BY r.id, r.amount_vnd, r.voided_on
        HAVING (r.voided_on IS NULL AND (count(l.id) = 0 OR sum(l.amount_vnd) <> r.amount_vnd))
            OR (r.voided_on IS NOT NULL AND count(l.id) <> 0)
    ) THEN RAISE EXCEPTION 'ALLOCATION_INVARIANT'; END IF;
    IF EXISTS (
        SELECT 1 FROM sokhach.receipt_line l JOIN sokhach.receipt r ON r.id = l.receipt_id
        WHERE l.customer_id = p_customer AND l.kind = 'advance'
          AND l.superseded_by_event IS NULL AND r.voided_on IS NULL
          AND l.debt_month <> coalesce((SELECT max(debt_month) FROM (
              SELECT debt_month FROM sokhach.opening_balance WHERE customer_id = p_customer
              UNION ALL SELECT debt_month FROM sokhach.v_trip_current WHERE NOT deleted AND customer_id = p_customer AND status='confirmed'
              UNION ALL SELECT debt_month FROM sokhach.v_adjustment_current WHERE customer_id = p_customer
              UNION ALL SELECT debt_month FROM sokhach.v_offset_outgoing WHERE customer_id = p_customer
          ) m),(SELECT max(x.debt_month) FROM sokhach.receipt_line x JOIN sokhach.receipt r0 ON r0.id=x.receipt_id
            WHERE r0.customer_id=p_customer AND r0.voided_on IS NULL AND x.superseded_by_event IS NULL))
    ) THEN RAISE EXCEPTION 'ADVANCE_MONTH_INVARIANT'; END IF;
    IF EXISTS (
        SELECT 1 FROM sokhach.receipt_line l
        JOIN sokhach.receipt r ON (r.id, r.customer_id) = (l.receipt_id, l.customer_id)
        JOIN sokhach.event e ON (e.id, e.customer_id) = (l.created_by_event, l.customer_id)
        WHERE l.customer_id = p_customer AND (
            e.kind NOT IN ('receipt', 'reallocation') OR
            e."after"->>'receipt' IS DISTINCT FROM r.id::text OR
            (e."after"->'allocations' @> jsonb_build_array(jsonb_build_object(
                'id',l.id,'month',l.debt_month,'kind',l.kind,'amount_vnd',l.amount_vnd::text))) IS NOT TRUE OR
            (l.superseded_by_event IS NOT NULL AND NOT EXISTS (
                SELECT 1 FROM sokhach.event s WHERE (s.id, s.customer_id) =
                  (l.superseded_by_event, l.customer_id) AND s.kind IN ('reallocation', 'void')
                  AND s."before"->>'receipt' = r.id::text
                  AND s."before"->'allocations' @> jsonb_build_array(jsonb_build_object(
                    'id',l.id,'month',l.debt_month,'kind',l.kind,'amount_vnd',l.amount_vnd::text))
            ))
        )
    ) THEN RAISE EXCEPTION 'ALLOCATION_EVENT_INVARIANT'; END IF;
END $$;

-- Recompute live receipts in (date,pid) order from active opening plus new movements.
-- Negative monthly buckets stay negative. Only positive buckets receive payments.
CREATE FUNCTION sokhach.reallocate(p_customer bigint, p_key text) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, sokhach, pg_temp AS $$
DECLARE v_months date[] := ARRAY[]::date[]; v_left bigint[] := ARRAY[]::bigint[];
        v_month date; v_amount bigint; v_last date; v_receipt sokhach.receipt%ROWTYPE;
        v_due bigint; v_remaining bigint; v_take bigint; v_new jsonb; v_old jsonb;
        v_old_snapshot jsonb; v_new_snapshot jsonb;
        v_event bigint; v_actor text; v_changes jsonb := '[]'::jsonb; i integer;
        v_row jsonb;
BEGIN
    SELECT version INTO v_amount FROM sokhach.customer WHERE id = p_customer FOR UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION 'CUSTOMER_NOT_FOUND'; END IF;
    v_actor := sokhach._actor();
    PERFORM sokhach._baseline(p_customer);
    FOR v_month, v_due IN
        WITH charges AS (
            SELECT o.debt_month, o.amount_vnd FROM sokhach.opening_balance o
            JOIN sokhach.cutover_customer cc ON (cc.customer_id,cc.cutover_id)=(o.customer_id,o.cutover_id)
            JOIN sokhach.cutover c ON c.id=cc.cutover_id
            WHERE o.customer_id=p_customer AND cc.status='active' AND c.status='active'
            UNION ALL
            SELECT t.debt_month,
                CASE WHEN p.unit_price_vnd IS NOT NULL
                     THEN p.unit_price_vnd + coalesce(p.other_fee_vnd,0)
                     WHEN t.container IS NULL OR t.container='' THEN p.other_fee_vnd END
            FROM sokhach.v_trip_current t LEFT JOIN LATERAL (
                SELECT unit_price_vnd,other_fee_vnd FROM sokhach.trip_price_rev
                WHERE trip_id=t.id ORDER BY id DESC LIMIT 1) p ON true
            WHERE t.customer_id=p_customer AND NOT t.deleted AND t.status='confirmed'
            UNION ALL
            SELECT debt_month,amount_vnd FROM sokhach.v_adjustment_current WHERE customer_id=p_customer
            UNION ALL SELECT debt_month,amount_vnd FROM sokhach.v_offset_outgoing WHERE customer_id=p_customer
        ) SELECT debt_month, sum(amount_vnd)::bigint FROM charges
          GROUP BY debt_month ORDER BY debt_month
    LOOP
        v_months := array_append(v_months,v_month);
        v_left := array_append(v_left,v_due);
        v_last := v_month;
    END LOOP;
    IF v_last IS NULL THEN
        SELECT max(l.debt_month) INTO v_last FROM sokhach.receipt_line l JOIN sokhach.receipt r ON r.id=l.receipt_id
          WHERE r.customer_id=p_customer AND r.voided_on IS NULL AND l.superseded_by_event IS NULL;
    END IF;
    IF v_last IS NULL AND EXISTS (SELECT 1 FROM sokhach.receipt WHERE customer_id=p_customer AND voided_on IS NULL)
    THEN RAISE EXCEPTION 'NO_MONTH_FOR_RECEIPT'; END IF;
    FOR v_receipt IN SELECT * FROM sokhach.receipt
        WHERE customer_id=p_customer AND voided_on IS NULL ORDER BY date,pid COLLATE "C"
    LOOP
        v_remaining := v_receipt.amount_vnd;
        v_new := '[]'::jsonb;
        FOR i IN 1..coalesce(array_length(v_months,1),0) LOOP
            EXIT WHEN v_remaining=0;
            IF v_left[i] > 0 THEN
                v_take := least(v_remaining,v_left[i]);
                v_new := v_new || jsonb_build_array(jsonb_build_object(
                    'month',v_months[i],'kind','debt','amount_vnd',v_take::text));
                v_left[i] := v_left[i]-v_take;
                v_remaining := v_remaining-v_take;
            END IF;
        END LOOP;
        IF v_remaining > 0 THEN
            v_new := v_new || jsonb_build_array(jsonb_build_object(
                'month',v_last,'kind','advance','amount_vnd',v_remaining::text));
        END IF;
        SELECT coalesce(jsonb_agg(jsonb_build_object('month',debt_month,
                   'kind',kind,'amount_vnd',amount_vnd::text)
                   ORDER BY debt_month,CASE kind WHEN 'debt' THEN 0 ELSE 1 END,id),'[]'::jsonb) INTO v_old
        FROM sokhach.receipt_line WHERE receipt_id=v_receipt.id AND superseded_by_event IS NULL;
        IF v_old IS DISTINCT FROM v_new THEN
            v_old_snapshot := sokhach._lines(v_receipt.id);
            v_new_snapshot := '[]'::jsonb;
            FOR v_row IN SELECT value FROM jsonb_array_elements(v_new) LOOP
                v_new_snapshot := v_new_snapshot || jsonb_build_array(v_row ||
                    jsonb_build_object('id',nextval(pg_get_serial_sequence('sokhach.receipt_line','id'))));
            END LOOP;
            INSERT INTO sokhach.event(customer_id,kind,actor,"before","after",idempotency_key)
            VALUES (p_customer,'reallocation',v_actor,
                jsonb_build_object('receipt',v_receipt.id,'allocations',v_old_snapshot),
                jsonb_build_object('receipt',v_receipt.id,'allocations',v_new_snapshot),p_key)
            RETURNING id INTO v_event;
            UPDATE sokhach.receipt_line SET superseded_by_event=v_event
            WHERE receipt_id=v_receipt.id AND superseded_by_event IS NULL;
            FOR v_row IN SELECT value FROM jsonb_array_elements(v_new_snapshot) LOOP
                INSERT INTO sokhach.receipt_line(id,receipt_id,customer_id,debt_month,kind,amount_vnd,created_by_event)
                OVERRIDING SYSTEM VALUE VALUES ((v_row->>'id')::bigint,v_receipt.id,p_customer,
                        (v_row->>'month')::date,v_row->>'kind',(v_row->>'amount_vnd')::bigint,v_event);
            END LOOP;
            v_changes := v_changes || jsonb_build_array(jsonb_build_object(
                'pid',v_receipt.pid,'before',v_old_snapshot,'after',v_new_snapshot,'event_id',v_event));
        END IF;
    END LOOP;
    PERFORM sokhach._check_allocations(p_customer);
    RETURN v_changes;
EXCEPTION WHEN numeric_value_out_of_range THEN RAISE EXCEPTION 'INVALID_VND';
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

CREATE FUNCTION sokhach.record_receipt(customer_id bigint, expected_version bigint,
    idempotency_key text, date date, method text, amount_vnd bigint, reference text DEFAULT NULL)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, sokhach, pg_temp AS $$
DECLARE v_payload jsonb := jsonb_build_object('command','record_receipt','date',date,
        'method',method,'amount_vnd',amount_vnd)
        || CASE WHEN reference IS NULL THEN '{}'::jsonb ELSE jsonb_build_object('reference',reference) END;
        v_retry jsonb; v_id bigint; v_pid text; v_event bigint; v_left bigint;
        v_last date; v_month date; v_due bigint; v_take bigint; v_plan jsonb := '[]'::jsonb;
        v_line jsonb; v_result jsonb; v_plan_ids jsonb := '[]'::jsonb;
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
    PERFORM sokhach._check_allocations(customer_id);
    v_result := jsonb_build_object('receipt_id',v_id,'pid',v_pid,'allocations',v_plan_ids,
                                  'overpayment_vnd',v_left::text,
        'duplicate_reference',EXISTS (SELECT 1 FROM sokhach.receipt r
            WHERE r.customer_id=record_receipt.customer_id AND r.id<>v_id
              AND r.reference=nullif(btrim(record_receipt.reference),'')));
    RETURN sokhach._finish_command(customer_id,idempotency_key,v_payload,v_result);
END $$;

CREATE FUNCTION sokhach.edit_receipt_meta(customer_id bigint, expected_version bigint,
    idempotency_key text, pid text, date date, method text, reference text DEFAULT NULL)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, sokhach, pg_temp AS $$
DECLARE v_payload jsonb := jsonb_build_object('command','edit_receipt_meta','pid',pid,
        'date',date,'method',method)
        || CASE WHEN reference IS NULL THEN '{}'::jsonb ELSE jsonb_build_object('reference',reference) END;
        v_retry jsonb; v_receipt sokhach.receipt%ROWTYPE; v_date date; v_method text; v_reference text;
        v_event bigint; v_changes jsonb := '[]'::jsonb; v_before jsonb;
BEGIN
    IF (date IS NOT NULL OR method IS NOT NULL OR reference IS NULL) AND EXISTS (
        SELECT 1 FROM sokhach.offset_pair p JOIN sokhach.receipt r ON r.id=p.target_receipt_id
        WHERE r.customer_id=edit_receipt_meta.customer_id AND r.pid=edit_receipt_meta.pid)
    THEN RAISE EXCEPTION 'OFFSET_PAIR_REQUIRED'; END IF;
    v_retry := sokhach._begin_command(customer_id,expected_version,idempotency_key,v_payload);
    IF v_retry IS NOT NULL THEN RETURN v_retry; END IF;
    PERFORM sokhach._baseline(customer_id);
    SELECT * INTO v_receipt FROM sokhach.receipt
     WHERE receipt.customer_id=edit_receipt_meta.customer_id AND receipt.pid=edit_receipt_meta.pid;
    IF NOT FOUND OR v_receipt.voided_on IS NOT NULL THEN RAISE EXCEPTION 'RECEIPT_NOT_FOUND'; END IF;
    v_date := coalesce(date,v_receipt.date);
    IF v_date > (clock_timestamp() AT TIME ZONE 'Asia/Ho_Chi_Minh')::date
       THEN RAISE EXCEPTION 'FUTURE_RECEIPT_DATE'; END IF;
    v_method := coalesce(method,v_receipt.method);
    IF v_method NOT IN ('THU TIỀN','CẤN TRỪ','ỨNG TRƯỚC','KHÁC')
       THEN RAISE EXCEPTION 'INVALID_METHOD'; END IF;
    v_reference := CASE WHEN reference IS NULL THEN v_receipt.reference ELSE nullif(btrim(reference),'') END;
    IF (v_date,v_method,v_reference) IS NOT DISTINCT FROM (v_receipt.date,v_receipt.method,v_receipt.reference)
       THEN RAISE EXCEPTION 'NO_CHANGE'; END IF;
    v_before := sokhach._lines(v_receipt.id);
    INSERT INTO sokhach.event(customer_id,kind,actor,"before","after",idempotency_key)
    VALUES (customer_id,'receipt_edit',sokhach._actor(),
        jsonb_build_object('receipt',v_receipt.id,'pid',pid,'date',v_receipt.date,
            'method',v_receipt.method,'reference',v_receipt.reference,'allocations',v_before),
        jsonb_build_object('receipt',v_receipt.id,'pid',pid,'date',v_date,
            'method',v_method,'reference',v_reference,'allocations',v_before),idempotency_key)
    RETURNING id INTO v_event;
    UPDATE sokhach.receipt SET date=v_date,method=v_method,reference=v_reference,meta_changed_by_event=v_event
    WHERE id=v_receipt.id;
    IF v_date IS DISTINCT FROM v_receipt.date THEN
        v_changes := sokhach.reallocate(customer_id,idempotency_key);
    ELSE
        PERFORM sokhach._check_allocations(customer_id);
    END IF;
    RETURN sokhach._finish_command(customer_id,idempotency_key,v_payload,
        jsonb_build_object('receipt_id',v_receipt.id,'pid',pid,'reallocated',v_changes,
            'duplicate_reference',EXISTS (SELECT 1 FROM sokhach.receipt r
                WHERE r.customer_id=edit_receipt_meta.customer_id AND r.id<>v_receipt.id
                  AND r.reference=v_reference)));
END $$;

CREATE FUNCTION sokhach.void_receipt(customer_id bigint, expected_version bigint,
    idempotency_key text, pid text, reason text)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, sokhach, pg_temp AS $$
DECLARE v_payload jsonb := jsonb_build_object('command','void_receipt','pid',pid,'reason',reason);
        v_retry jsonb; v_receipt sokhach.receipt%ROWTYPE; v_before jsonb;
        v_event bigint; v_count bigint;
BEGIN
    IF EXISTS (SELECT 1 FROM sokhach.offset_pair p JOIN sokhach.receipt r ON r.id=p.target_receipt_id
        WHERE r.customer_id=void_receipt.customer_id AND r.pid=void_receipt.pid)
    THEN RAISE EXCEPTION 'OFFSET_PAIR_REQUIRED'; END IF;
    v_retry := sokhach._begin_command(customer_id,expected_version,idempotency_key,v_payload);
    IF v_retry IS NOT NULL THEN RETURN v_retry; END IF;
    PERFORM sokhach._baseline(customer_id);
    IF reason IS NULL OR btrim(reason)='' THEN RAISE EXCEPTION 'VOID_REASON_REQUIRED'; END IF;
    SELECT * INTO v_receipt FROM sokhach.receipt
     WHERE receipt.customer_id=void_receipt.customer_id AND receipt.pid=void_receipt.pid;
    IF NOT FOUND THEN RAISE EXCEPTION 'RECEIPT_NOT_FOUND'; END IF;
    IF v_receipt.voided_on IS NOT NULL THEN RAISE EXCEPTION 'RECEIPT_ALREADY_VOID'; END IF;
    v_before := sokhach._lines(v_receipt.id);
    INSERT INTO sokhach.event(customer_id,kind,actor,"before","after",idempotency_key)
    VALUES (customer_id,'void',sokhach._actor(),
        jsonb_build_object('receipt',v_receipt.id,'pid',pid,'amount_vnd',v_receipt.amount_vnd::text,
            'allocations',v_before),
        jsonb_build_object('receipt',v_receipt.id,'pid',pid,'void_reason',btrim(reason),
            'allocations','[]'::jsonb),idempotency_key)
    RETURNING id INTO v_event;
    UPDATE sokhach.receipt_line SET superseded_by_event=v_event
    WHERE receipt_id=v_receipt.id AND superseded_by_event IS NULL;
    GET DIAGNOSTICS v_count = ROW_COUNT;
    IF v_count <> jsonb_array_length(v_before) THEN RAISE EXCEPTION 'VOID_LINE_MISMATCH'; END IF;
    UPDATE sokhach.receipt SET void_reason=btrim(reason),
        voided_on=(clock_timestamp() AT TIME ZONE 'Asia/Ho_Chi_Minh')::date,
        voided_by=sokhach._actor(),voided_by_event=v_event WHERE id=v_receipt.id;
    PERFORM sokhach._check_allocations(customer_id);
    RETURN sokhach._finish_command(customer_id,idempotency_key,v_payload,
        jsonb_build_object('receipt_id',v_receipt.id,'pid',pid,'voided_lines',v_count));
END $$;

CREATE FUNCTION sokhach.set_month_lock(customer_id bigint, expected_version bigint,
    idempotency_key text, month date, locked boolean)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, sokhach, pg_temp AS $$
DECLARE v_payload jsonb := jsonb_build_object('command','set_month_lock','month',month,'locked',locked);
        v_retry jsonb; v_before boolean;
BEGIN
    v_retry := sokhach._begin_command(customer_id,expected_version,idempotency_key,v_payload);
    IF v_retry IS NOT NULL THEN RETURN v_retry; END IF;
    IF month IS NULL OR extract(day FROM month) <> 1 OR locked IS NULL
       THEN RAISE EXCEPTION 'INVALID_MONTH_LOCK'; END IF;
    SELECT coalesce((SELECT ms.locked FROM sokhach.month_state ms
        WHERE ms.customer_id=set_month_lock.customer_id AND ms.month=set_month_lock.month),
        month<>date_trunc('month',clock_timestamp() AT TIME ZONE 'Asia/Ho_Chi_Minh')::date)
    INTO v_before;
    INSERT INTO sokhach.event(customer_id,kind,actor,at,"before","after",idempotency_key)
    VALUES (customer_id,'month_lock',sokhach._actor(),clock_timestamp(),
        jsonb_build_object('month',month,'locked',v_before),
        jsonb_build_object('month',month,'locked',locked),idempotency_key);
    INSERT INTO sokhach.month_state(customer_id,month,locked,changed_by,changed_at)
    VALUES (customer_id,month,locked,sokhach._actor(),clock_timestamp())
    ON CONFLICT ON CONSTRAINT month_state_pkey DO UPDATE SET locked=excluded.locked,
        changed_by=excluded.changed_by,changed_at=excluded.changed_at;
    RETURN sokhach._finish_command(customer_id,idempotency_key,v_payload,
        jsonb_build_object('month',month,'locked',locked));
END $$;

-- NEWTRIP-01: kết luận một chuyến CHỜ KIỂM, bắt buộc lý do, chỉ kết luận một lần.
-- Tháng khóa chặn kết luận theo mục "Cập nhật khóa tháng 24/10/2026" của
-- docs/decisions.md: muốn sửa, xóa chuyến hoặc kết luận CHỜ KIỂM thì mở khóa trước
-- (vế "tháng khóa không chặn" trong dòng NEWTRIP-01 đã hết hiệu lực).
CREATE FUNCTION sokhach.review_trip(customer_id bigint, expected_version bigint,
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

-- Same customer lock is held by caller. This checks source evidence, never
-- derives standard_bucket_vnd from the opening being checked.
CREATE FUNCTION sokhach._check_cutover_customer(p_customer bigint, p_cutover bigint)
RETURNS void LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, sokhach, pg_temp AS $$
DECLARE v_cc sokhach.cutover_customer%ROWTYPE; v_bad boolean;
        v_open_count bigint; v_check_count bigint; v_total numeric;
        v_anchor numeric; v_initial numeric; v_balances numeric[] := ARRAY[]::numeric[];
        v_months date[] := ARRAY[]::date[]; v_row record; v_due numeric;
        v_left numeric; v_take numeric; v_i integer; v_n integer;
BEGIN
    SELECT * INTO v_cc FROM sokhach.cutover_customer
        WHERE customer_id=p_customer AND cutover_id=p_cutover;
    IF NOT FOUND THEN RAISE EXCEPTION 'CUTOVER_CUSTOMER_NOT_FOUND'; END IF;
    SELECT count(*),sum(amount_vnd)::numeric INTO v_open_count,v_total
        FROM sokhach.opening_balance
        WHERE customer_id=p_customer AND cutover_id=p_cutover;
    IF coalesce(v_total,0) <> v_cc.expected_control_total_vnd THEN
        RAISE EXCEPTION 'CUTOVER_CUSTOMER_TOTAL_MISMATCH';
    END IF;
    SELECT count(*) INTO v_check_count FROM sokhach.cutover_month_check
        WHERE customer_id=p_customer AND cutover_id=p_cutover;
    IF v_check_count=0 OR v_check_count<>v_open_count
       OR v_cc.source_rows<>v_cc.imported_rows+v_cc.quarantined_rows+v_cc.skipped_with_reason_rows THEN
        RAISE EXCEPTION 'CUTOVER_SOURCE_INCOMPLETE';
    END IF;
    SELECT EXISTS (
      SELECT 1 FROM sokhach.cutover_month_check m
      FULL JOIN sokhach.opening_balance o USING(customer_id,cutover_id,debt_month)
      WHERE coalesce(m.customer_id,o.customer_id)=p_customer
        AND coalesce(m.cutover_id,o.cutover_id)=p_cutover
        AND (m.customer_id IS NULL OR o.id IS NULL
         OR m.opening_anchor_vnd IS NULL
         OR m.bucket_vnd IS NULL OR m.standard_bucket_vnd IS NULL
         OR m.source_charge_vnd IS NULL OR m.source_receipt_vnd IS NULL
         OR m.source_cumulative_vnd IS NULL
         OR nullif(btrim(m.standard_source_ref),'') IS NULL
         OR m.standard_source_sha256 IS NULL OR m.source_evidence_sha256 IS NULL
         OR m.bucket_vnd IS DISTINCT FROM m.standard_bucket_vnd
         OR m.bucket_vnd IS DISTINCT FROM o.amount_vnd)
    ) INTO v_bad;
    IF v_bad THEN RAISE EXCEPTION 'CUTOVER_MONTH_MISMATCH'; END IF;
    -- Source charges/receipts determine FIFO independently of imported buckets.
    FOR v_row IN SELECT * FROM sokhach.cutover_month_check
        WHERE customer_id=p_customer AND cutover_id=p_cutover ORDER BY debt_month LOOP
        IF v_initial IS NULL THEN
            v_initial := v_row.opening_anchor_vnd;
            v_anchor := v_initial;
        END IF;
        IF v_row.opening_anchor_vnd::numeric <> v_initial
        THEN RAISE EXCEPTION 'CUTOVER_ANCHOR_MISMATCH'; END IF;
        v_due := v_row.source_charge_vnd::numeric;
        IF cardinality(v_months)=0 THEN v_due := v_due+v_anchor; END IF;
        v_months := array_append(v_months,v_row.debt_month);
        v_balances := array_append(v_balances,v_due);
        v_n := cardinality(v_balances);
        v_left := v_row.source_receipt_vnd;
        FOR v_i IN 1..v_n LOOP
            v_take := least(greatest(v_balances[v_i],0),v_left);
            v_balances[v_i] := v_balances[v_i]-v_take;
            v_left := v_left-v_take;
        END LOOP;
        IF v_left>0 THEN v_balances[v_n] := v_balances[v_n]-v_left; END IF;
        v_anchor := v_anchor+v_row.source_charge_vnd-v_row.source_receipt_vnd;
        IF v_anchor<>v_row.source_cumulative_vnd::numeric
        THEN RAISE EXCEPTION 'CUTOVER_ANCHOR_MISMATCH'; END IF;
    END LOOP;
    FOR v_i IN 1..cardinality(v_months) LOOP
        IF v_balances[v_i] IS DISTINCT FROM (SELECT standard_bucket_vnd::numeric
            FROM sokhach.cutover_month_check WHERE customer_id=p_customer
              AND cutover_id=p_cutover AND debt_month=v_months[v_i])
        THEN RAISE EXCEPTION 'CUTOVER_FIFO_MISMATCH'; END IF;
    END LOOP;
    IF v_anchor IS DISTINCT FROM v_cc.expected_control_total_vnd::numeric
       OR (SELECT sum(x)::numeric FROM unnest(v_balances) x) IS DISTINCT FROM v_anchor
    THEN RAISE EXCEPTION 'CUTOVER_ANCHOR_MISMATCH'; END IF;
END $$;

-- ponytail: idempotency toàn mốc dùng khóa namespace trong bảng theo khách;
-- đổi sang bảng vết riêng khi cần vết toàn mốc.
-- Mốc luôn khóa trước khách; khách nhỏ nhất ổn định sau khi cả mốc verified.
CREATE FUNCTION sokhach._begin_cutover(p_cutover bigint, p_key text, p_payload jsonb)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, sokhach, pg_temp AS $$
DECLARE v_customer bigint; v_saved sokhach.idempotency%ROWTYPE;
        v_storage_key text; v_hash text;
BEGIN
    PERFORM sokhach._actor();
    IF p_key IS NULL OR btrim(p_key)='' OR p_payload IS NULL THEN
        RAISE EXCEPTION 'INVALID_COMMAND'; END IF;
    PERFORM 1 FROM sokhach.cutover WHERE id=p_cutover FOR UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION 'CUTOVER_NOT_FOUND'; END IF;
    FOR v_customer IN SELECT customer_id FROM sokhach.cutover_customer
        WHERE cutover_id=p_cutover ORDER BY customer_id LOOP
        PERFORM 1 FROM sokhach.customer WHERE id=v_customer FOR UPDATE;
    END LOOP;
    SELECT min(customer_id) INTO v_customer FROM sokhach.cutover_customer
        WHERE cutover_id=p_cutover;
    IF v_customer IS NULL THEN RAISE EXCEPTION 'CUTOVER_SOURCE_INCOMPLETE'; END IF;
    v_storage_key := chr(31)||'cutover:'||p_cutover||':'||p_key;
    v_hash := encode(sha256(convert_to(p_payload::text,'UTF8')),'hex');
    SELECT * INTO v_saved FROM sokhach.idempotency
        WHERE customer_id=v_customer AND key=v_storage_key;
    IF FOUND THEN
        IF v_saved.request_hash<>v_hash THEN RAISE EXCEPTION 'IDEMPOTENCY_CONFLICT'; END IF;
        RETURN v_saved.result;
    END IF;
    RETURN NULL;
END $$;

CREATE FUNCTION sokhach._finish_cutover(p_cutover bigint, p_key text,
    p_payload jsonb, p_result jsonb) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, sokhach, pg_temp AS $$
DECLARE v_customer bigint;
BEGIN
    SELECT min(customer_id) INTO v_customer FROM sokhach.cutover_customer
        WHERE cutover_id=p_cutover;
    INSERT INTO sokhach.idempotency(customer_id,key,request_hash,result)
    VALUES(v_customer,chr(31)||'cutover:'||p_cutover||':'||p_key,
        encode(sha256(convert_to(p_payload::text,'UTF8')),'hex'),p_result);
    RETURN p_result;
END $$;

CREATE FUNCTION sokhach.import_cutover(customer_id bigint, expected_version bigint,
    idempotency_key text, cutover_id bigint, openings jsonb, legacy jsonb,
    month_checks jsonb, expected_control_total bigint, report_sha256 text)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, sokhach, pg_temp AS $$
DECLARE v_payload jsonb := jsonb_build_object('command','import_cutover',
        'cutover_id',cutover_id,'openings',openings,'legacy',legacy,
        'month_checks',month_checks,'expected_control_total',expected_control_total,
        'report_sha256',report_sha256);
        v_retry jsonb; v_item jsonb; v_event bigint; v_total numeric;
        v_status text; v_result jsonb;
BEGIN
    PERFORM 1 FROM sokhach.cutover WHERE id=import_cutover.cutover_id FOR UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION 'CUTOVER_NOT_FOUND'; END IF;
    v_retry := sokhach._begin_command(customer_id,expected_version,idempotency_key,v_payload);
    IF v_retry IS NOT NULL THEN RETURN v_retry; END IF;
    SELECT status INTO v_status FROM sokhach.cutover WHERE id=import_cutover.cutover_id;
    IF v_status<>'draft' THEN RAISE EXCEPTION 'CUTOVER_NOT_DRAFT'; END IF;
    IF EXISTS(SELECT 1 FROM sokhach.cutover_customer WHERE cutover_customer.customer_id=import_cutover.customer_id)
       OR EXISTS(SELECT 1 FROM sokhach.trip WHERE trip.customer_id=import_cutover.customer_id)
       OR EXISTS(SELECT 1 FROM sokhach.adjustment WHERE adjustment.customer_id=import_cutover.customer_id)
       OR EXISTS(SELECT 1 FROM sokhach.receipt WHERE receipt.customer_id=import_cutover.customer_id)
       OR EXISTS(SELECT 1 FROM sokhach.event WHERE event.customer_id=import_cutover.customer_id
                 AND event.kind<>'import')
    THEN RAISE EXCEPTION 'CUTOVER_IMPORT_CONFLICT'; END IF;
    IF jsonb_typeof(openings) IS DISTINCT FROM 'array'
       OR jsonb_typeof(legacy) IS DISTINCT FROM 'array'
       OR jsonb_typeof(month_checks) IS DISTINCT FROM 'array'
       OR report_sha256 !~ '^[0-9a-fA-F]{64}$'
       OR expected_control_total IS NULL THEN RAISE EXCEPTION 'INVALID_CUTOVER_INPUT'; END IF;
    IF EXISTS(SELECT 1 FROM jsonb_array_elements(openings) AS x(value)
              WHERE jsonb_typeof(x.value) <> 'object' OR x.value->>'amount_vnd' IS NULL
                 OR x.value->>'debt_month' IS NULL OR x.value->>'source_tab' IS NULL
                 OR x.value->>'source_row' IS NULL)
       OR EXISTS(SELECT 1 FROM jsonb_array_elements(legacy) AS x(value)
              WHERE jsonb_typeof(x.value) <> 'object' OR x.value->>'debt_month' IS NULL
                 OR x.value->>'kind' IS NULL OR x.value->>'source_tab' IS NULL
                 OR x.value->>'source_row' IS NULL OR jsonb_typeof(x.value->'display') <> 'object')
       OR EXISTS(SELECT 1 FROM jsonb_array_elements(month_checks) AS x(value)
              WHERE jsonb_typeof(x.value) <> 'object' OR x.value->>'debt_month' IS NULL
                 OR jsonb_typeof(x.value->'exception_codes') IS DISTINCT FROM 'array')
    THEN RAISE EXCEPTION 'INVALID_CUTOVER_INPUT'; END IF;
    SELECT coalesce(sum((x.value->>'amount_vnd')::numeric),0) INTO v_total
      FROM jsonb_array_elements(openings) AS x(value);
    IF v_total<>expected_control_total THEN RAISE EXCEPTION 'CUTOVER_CUSTOMER_TOTAL_MISMATCH'; END IF;
    INSERT INTO sokhach.cutover_customer(customer_id,cutover_id,expected_control_total_vnd,
        report_sha256,source_rows,imported_rows,quarantined_rows,
        skipped_with_reason_rows,unresolved_exceptions)
    VALUES(customer_id,cutover_id,expected_control_total,report_sha256,
        jsonb_array_length(openings)+jsonb_array_length(legacy),
        jsonb_array_length(openings)+jsonb_array_length(legacy),0,0,
        (SELECT count(*) FROM jsonb_array_elements(month_checks) AS x(value)
         WHERE jsonb_array_length(x.value->'exception_codes')>0));
    INSERT INTO sokhach.event(customer_id,kind,actor,"before","after",idempotency_key,cutover_id)
    VALUES(customer_id,'import',sokhach._actor(),'{}',
        jsonb_build_object('cutover',cutover_id,'openings',jsonb_array_length(openings),
            'legacy',jsonb_array_length(legacy),'report_sha256',report_sha256),
        idempotency_key,cutover_id) RETURNING id INTO v_event;
    FOR v_item IN SELECT value FROM jsonb_array_elements(openings) LOOP
        INSERT INTO sokhach.opening_balance(customer_id,cutover_id,debt_month,
            amount_vnd,source_tab,source_row,created_by_event)
        VALUES(customer_id,cutover_id,(v_item->>'debt_month')::date,
            (v_item->>'amount_vnd')::bigint,v_item->>'source_tab',
            (v_item->>'source_row')::bigint,v_event);
    END LOOP;
    FOR v_item IN SELECT value FROM jsonb_array_elements(legacy) LOOP
        INSERT INTO sokhach.legacy_row(customer_id,cutover_id,debt_month,kind,
            display,source_total_vnd,source_tab,source_row,created_by_event)
        VALUES(customer_id,cutover_id,(v_item->>'debt_month')::date,
            v_item->>'kind',v_item->'display',(v_item->>'source_total_vnd')::bigint,
            v_item->>'source_tab',(v_item->>'source_row')::bigint,v_event);
    END LOOP;
    FOR v_item IN SELECT value FROM jsonb_array_elements(month_checks) LOOP
        INSERT INTO sokhach.cutover_month_check(customer_id,cutover_id,debt_month,
            opening_anchor_vnd,source_cumulative_vnd,replay_cumulative_vnd,bucket_vnd,
            standard_bucket_vnd,standard_source_ref,standard_source_sha256,
            source_evidence_sha256,exception_codes,source_charge_vnd,source_receipt_vnd)
        VALUES(customer_id,cutover_id,(v_item->>'debt_month')::date,
            (v_item->>'opening_anchor_vnd')::bigint,(v_item->>'source_cumulative_vnd')::bigint,
            (v_item->>'replay_cumulative_vnd')::bigint,(v_item->>'bucket_vnd')::bigint,
            (v_item->>'standard_bucket_vnd')::bigint,v_item->>'standard_source_ref',
            v_item->>'standard_source_sha256',v_item->>'source_evidence_sha256',
            ARRAY(SELECT jsonb_array_elements_text(v_item->'exception_codes')),
            (v_item->>'source_charge_vnd')::bigint,(v_item->>'source_receipt_vnd')::bigint);
    END LOOP;
    v_result := jsonb_build_object('cutover_id',cutover_id,'customer_id',customer_id,
        'status','draft','event_id',v_event);
    RETURN sokhach._finish_command(customer_id,idempotency_key,v_payload,v_result);
END $$;

CREATE FUNCTION sokhach.verify_cutover_customer(customer_id bigint, cutover_id bigint,
    expected_version bigint, idempotency_key text, signoff_ref text)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, sokhach, pg_temp AS $$
DECLARE v_payload jsonb := jsonb_build_object('command','verify_cutover_customer',
        'cutover_id',cutover_id,'signoff_ref',signoff_ref);
        v_retry jsonb; v_result jsonb;
BEGIN
    PERFORM 1 FROM sokhach.cutover WHERE id=verify_cutover_customer.cutover_id FOR UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION 'CUTOVER_NOT_FOUND'; END IF;
    v_retry := sokhach._begin_command(customer_id,expected_version,idempotency_key,v_payload);
    IF v_retry IS NOT NULL THEN RETURN v_retry; END IF;
    IF NOT EXISTS(SELECT 1 FROM sokhach.cutover_customer cc
      JOIN sokhach.cutover c ON c.id=cc.cutover_id
      WHERE cc.customer_id=verify_cutover_customer.customer_id
        AND cc.cutover_id=verify_cutover_customer.cutover_id
        AND cc.status='draft' AND c.status='draft')
    THEN RAISE EXCEPTION 'CUTOVER_TRANSITION_ORDER'; END IF;
    PERFORM sokhach._check_cutover_customer(customer_id,cutover_id);
    UPDATE sokhach.cutover_customer SET status='verified'
      WHERE cutover_customer.customer_id=verify_cutover_customer.customer_id
        AND cutover_customer.cutover_id=verify_cutover_customer.cutover_id;
    v_result:=jsonb_build_object('cutover_id',cutover_id,'customer_id',customer_id,
        'status','verified');
    RETURN sokhach._finish_command(customer_id,idempotency_key,v_payload,v_result);
END $$;

CREATE FUNCTION sokhach._check_cutover(p_cutover bigint) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, sokhach, pg_temp AS $$
DECLARE v_customer bigint; v_total numeric;
BEGIN
    FOR v_customer IN SELECT customer_id FROM sokhach.cutover_customer
        WHERE cutover_id=p_cutover ORDER BY customer_id LOOP
        IF (SELECT status FROM sokhach.cutover_customer
            WHERE customer_id=v_customer AND cutover_id=p_cutover)<>'verified'
        THEN RAISE EXCEPTION 'CUTOVER_CUSTOMERS_NOT_VERIFIED'; END IF;
        PERFORM sokhach._check_cutover_customer(v_customer,p_cutover);
    END LOOP;
    SELECT sum(expected_control_total_vnd)::numeric INTO v_total
      FROM sokhach.cutover_customer WHERE cutover_id=p_cutover;
    IF v_total IS NULL OR v_total IS DISTINCT FROM
       (SELECT control_total_vnd FROM sokhach.cutover WHERE id=p_cutover) THEN
        RAISE EXCEPTION 'CUTOVER_TOTAL_MISMATCH';
    END IF;
END $$;

CREATE FUNCTION sokhach.verify_cutover(cutover_id bigint, idempotency_key text,
    signoff_ref text) RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, sokhach, pg_temp AS $$
DECLARE v_payload jsonb:=jsonb_build_object('command','verify_cutover','signoff_ref',signoff_ref);
        v_retry jsonb; v_result jsonb;
BEGIN
    v_retry:=sokhach._begin_cutover(cutover_id,idempotency_key,v_payload);
    IF v_retry IS NOT NULL THEN RETURN v_retry; END IF;
    IF (SELECT status FROM sokhach.cutover WHERE id=verify_cutover.cutover_id)<>'draft'
    THEN RAISE EXCEPTION 'CUTOVER_TRANSITION_ORDER'; END IF;
    PERFORM sokhach._check_cutover(cutover_id);
    UPDATE sokhach.cutover SET status='verified' WHERE id=verify_cutover.cutover_id;
    v_result:=jsonb_build_object('cutover_id',cutover_id,'status','verified');
    RETURN sokhach._finish_cutover(cutover_id,idempotency_key,v_payload,v_result);
END $$;

CREATE FUNCTION sokhach.activate_cutover(cutover_id bigint, idempotency_key text,
    signoff_ref text) RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, sokhach, pg_temp AS $$
DECLARE v_payload jsonb:=jsonb_build_object('command','activate_cutover','signoff_ref',signoff_ref);
        v_retry jsonb; v_result jsonb;
BEGIN
    v_retry:=sokhach._begin_cutover(cutover_id,idempotency_key,v_payload);
    IF v_retry IS NOT NULL THEN RETURN v_retry; END IF;
    IF (SELECT status FROM sokhach.cutover WHERE id=activate_cutover.cutover_id)<>'verified'
    THEN RAISE EXCEPTION 'CUTOVER_TRANSITION_ORDER'; END IF;
    PERFORM sokhach._check_cutover(cutover_id);
    UPDATE sokhach.cutover SET status='active' WHERE id=activate_cutover.cutover_id;
    v_result:=jsonb_build_object('cutover_id',cutover_id,'status','active');
    RETURN sokhach._finish_cutover(cutover_id,idempotency_key,v_payload,v_result);
END $$;

CREATE FUNCTION sokhach.activate_cutover_customer(customer_id bigint, cutover_id bigint,
    expected_version bigint, idempotency_key text, signoff_ref text)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, sokhach, pg_temp AS $$
DECLARE v_payload jsonb:=jsonb_build_object('command','activate_cutover_customer',
        'cutover_id',cutover_id,'signoff_ref',signoff_ref);
        v_retry jsonb; v_result jsonb;
BEGIN
    PERFORM 1 FROM sokhach.cutover WHERE id=activate_cutover_customer.cutover_id FOR UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION 'CUTOVER_NOT_FOUND'; END IF;
    v_retry:=sokhach._begin_command(customer_id,expected_version,idempotency_key,v_payload);
    IF v_retry IS NOT NULL THEN RETURN v_retry; END IF;
    IF NOT EXISTS(SELECT 1 FROM sokhach.cutover_customer cc
      JOIN sokhach.cutover c ON c.id=cc.cutover_id
      WHERE cc.customer_id=activate_cutover_customer.customer_id
        AND cc.cutover_id=activate_cutover_customer.cutover_id
        AND cc.status='verified' AND c.status='active')
    THEN RAISE EXCEPTION 'CUTOVER_TRANSITION_ORDER'; END IF;
    PERFORM sokhach._check_cutover_customer(customer_id,cutover_id);
    UPDATE sokhach.cutover_customer SET status='active'
      WHERE cutover_customer.customer_id=activate_cutover_customer.customer_id
        AND cutover_customer.cutover_id=activate_cutover_customer.cutover_id;
    v_result:=jsonb_build_object('cutover_id',cutover_id,'customer_id',customer_id,
        'status','active');
    RETURN sokhach._finish_command(customer_id,idempotency_key,v_payload,v_result);
END $$;

CREATE FUNCTION sokhach._edit_receipt_meta(customer_id bigint, expected_version bigint,
    idempotency_key text, pid text, date date, method text)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, sokhach, pg_temp AS $$
DECLARE v_payload jsonb := jsonb_build_object('command','_edit_receipt_meta','pid',pid,
        'date',date,'method',method);
        v_retry jsonb; v_receipt sokhach.receipt%ROWTYPE; v_date date; v_method text;
        v_event bigint; v_changes jsonb := '[]'::jsonb; v_before jsonb;
BEGIN
    v_retry := sokhach._begin_command(customer_id,expected_version,idempotency_key,v_payload);
    IF v_retry IS NOT NULL THEN RETURN v_retry; END IF;
    PERFORM sokhach._baseline(customer_id);
    SELECT * INTO v_receipt FROM sokhach.receipt
     WHERE receipt.customer_id=_edit_receipt_meta.customer_id AND receipt.pid=_edit_receipt_meta.pid;
    IF NOT FOUND OR v_receipt.voided_on IS NOT NULL THEN RAISE EXCEPTION 'RECEIPT_NOT_FOUND'; END IF;
    v_date := coalesce(date,v_receipt.date);
    IF v_date > (clock_timestamp() AT TIME ZONE 'Asia/Ho_Chi_Minh')::date
       THEN RAISE EXCEPTION 'FUTURE_RECEIPT_DATE'; END IF;
    v_method := coalesce(method,v_receipt.method);
    IF v_method NOT IN ('THU TIỀN','CẤN TRỪ','ỨNG TRƯỚC','KHÁC')
       THEN RAISE EXCEPTION 'INVALID_METHOD'; END IF;
    IF (v_date,v_method) IS NOT DISTINCT FROM (v_receipt.date,v_receipt.method)
       THEN RAISE EXCEPTION 'NO_CHANGE'; END IF;
    v_before := sokhach._lines(v_receipt.id);
    INSERT INTO sokhach.event(customer_id,kind,actor,"before","after",idempotency_key)
    VALUES (customer_id,'receipt_edit',sokhach._actor(),
        jsonb_build_object('receipt',v_receipt.id,'pid',pid,'date',v_receipt.date,
            'method',v_receipt.method,'allocations',v_before),
        jsonb_build_object('receipt',v_receipt.id,'pid',pid,'date',v_date,
            'method',v_method,'allocations',v_before),idempotency_key)
    RETURNING id INTO v_event;
    UPDATE sokhach.receipt SET date=v_date,method=v_method,meta_changed_by_event=v_event
    WHERE id=v_receipt.id;
    IF v_date IS DISTINCT FROM v_receipt.date THEN
        v_changes := sokhach.reallocate(customer_id,idempotency_key);
    ELSE
        PERFORM sokhach._check_allocations(customer_id);
    END IF;
    RETURN sokhach._finish_command(customer_id,idempotency_key,v_payload,
        jsonb_build_object('receipt_id',v_receipt.id,'pid',pid,'reallocated',v_changes));
END $$;

CREATE FUNCTION sokhach._void_receipt(customer_id bigint, expected_version bigint,
    idempotency_key text, pid text, reason text)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, sokhach, pg_temp AS $$
DECLARE v_payload jsonb := jsonb_build_object('command','_void_receipt','pid',pid,'reason',reason);
        v_retry jsonb; v_receipt sokhach.receipt%ROWTYPE; v_before jsonb;
        v_event bigint; v_count bigint;
BEGIN
    v_retry := sokhach._begin_command(customer_id,expected_version,idempotency_key,v_payload);
    IF v_retry IS NOT NULL THEN RETURN v_retry; END IF;
    PERFORM sokhach._baseline(customer_id);
    IF reason IS NULL OR btrim(reason)='' THEN RAISE EXCEPTION 'VOID_REASON_REQUIRED'; END IF;
    SELECT * INTO v_receipt FROM sokhach.receipt
     WHERE receipt.customer_id=_void_receipt.customer_id AND receipt.pid=_void_receipt.pid;
    IF NOT FOUND THEN RAISE EXCEPTION 'RECEIPT_NOT_FOUND'; END IF;
    IF v_receipt.voided_on IS NOT NULL THEN RAISE EXCEPTION 'RECEIPT_ALREADY_VOID'; END IF;
    v_before := sokhach._lines(v_receipt.id);
    INSERT INTO sokhach.event(customer_id,kind,actor,"before","after",idempotency_key)
    VALUES (customer_id,'void',sokhach._actor(),
        jsonb_build_object('receipt',v_receipt.id,'pid',pid,'amount_vnd',v_receipt.amount_vnd::text,
            'allocations',v_before),
        jsonb_build_object('receipt',v_receipt.id,'pid',pid,'void_reason',btrim(reason),
            'allocations','[]'::jsonb),idempotency_key)
    RETURNING id INTO v_event;
    UPDATE sokhach.receipt_line SET superseded_by_event=v_event
    WHERE receipt_id=v_receipt.id AND superseded_by_event IS NULL;
    GET DIAGNOSTICS v_count = ROW_COUNT;
    IF v_count <> jsonb_array_length(v_before) THEN RAISE EXCEPTION 'VOID_LINE_MISMATCH'; END IF;
    UPDATE sokhach.receipt SET void_reason=btrim(reason),
        voided_on=(clock_timestamp() AT TIME ZONE 'Asia/Ho_Chi_Minh')::date,
        voided_by=sokhach._actor(),voided_by_event=v_event WHERE id=v_receipt.id;
    PERFORM sokhach._check_allocations(customer_id);
    RETURN sokhach._finish_command(customer_id,idempotency_key,v_payload,
        jsonb_build_object('receipt_id',v_receipt.id,'pid',pid,'voided_lines',v_count));
END $$;


-- CT-2SO. All writers share customer locks; pair commands always lock ascending IDs.
CREATE FUNCTION sokhach._next_pid(p_customer bigint) RETURNS text
LANGUAGE sql SECURITY DEFINER SET search_path = pg_catalog, sokhach, pg_temp AS $$
    SELECT 'PH-' || lpad(n::text,greatest(3,length(n::text)),'0') FROM (
        SELECT coalesce(max(substring(pid FROM 4)::bigint),0)+1 AS n FROM (
            SELECT pid FROM sokhach.receipt WHERE customer_id=p_customer
            UNION ALL SELECT source_pid FROM sokhach.offset_pair WHERE source_customer_id=p_customer
            UNION ALL SELECT display->>'pid' FROM sokhach.legacy_row
                WHERE customer_id=p_customer AND kind='receipt'
        ) codes WHERE pid ~ '^PH-[0-9]+$'
    ) seq
$$;

CREATE FUNCTION sokhach._begin_offset(p_target bigint,p_target_version bigint,
    p_source bigint,p_source_version bigint,p_key text,p_payload jsonb) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, sokhach, pg_temp AS $$
DECLARE v_saved sokhach.offset_command%ROWTYPE; v_count integer;
BEGIN
    PERFORM sokhach._actor();
    IF p_target=p_source THEN RAISE EXCEPTION 'OFFSET_SAME_BOOK'; END IF;
    IF p_key IS NULL OR btrim(p_key)='' OR p_source IS NULL OR p_target IS NULL
    THEN RAISE EXCEPTION 'INVALID_COMMAND'; END IF;
    PERFORM id FROM sokhach.customer WHERE id IN (p_source,p_target) ORDER BY id FOR UPDATE;
    GET DIAGNOSTICS v_count=ROW_COUNT;
    IF v_count<>2 THEN RAISE EXCEPTION 'CUSTOMER_NOT_FOUND'; END IF;
    SELECT * INTO v_saved FROM sokhach.offset_command
      WHERE low_customer_id=least(p_source,p_target) AND high_customer_id=greatest(p_source,p_target)
        AND key=p_key;
    IF FOUND THEN
        IF v_saved.payload IS DISTINCT FROM p_payload THEN RAISE EXCEPTION 'IDEMPOTENCY_CONFLICT'; END IF;
        RETURN v_saved.result;
    END IF;
    IF p_source_version IS DISTINCT FROM (SELECT version FROM sokhach.customer WHERE id=p_source)
       OR p_target_version IS DISTINCT FROM (SELECT version FROM sokhach.customer WHERE id=p_target)
    THEN RAISE EXCEPTION 'STALE_LEDGER'; END IF;
    PERFORM sokhach._baseline(p_source);
    PERFORM sokhach._baseline(p_target);
    RETURN NULL;
END $$;

-- Target core already increments its version; finish increments source exactly once.
CREATE FUNCTION sokhach._finish_offset(p_pair sokhach.offset_pair,p_key text,
    p_payload jsonb,p_result jsonb) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, sokhach, pg_temp AS $$
DECLARE v_source_version bigint; v_result jsonb;
BEGIN
    UPDATE sokhach.customer SET version=version+1 WHERE id=p_pair.source_customer_id
        RETURNING version INTO v_source_version;
    v_result:=p_result || jsonb_build_object('offset_pair_id',p_pair.id,
        'source_customer_id',p_pair.source_customer_id,'target_customer_id',p_pair.target_customer_id,
        'source_version',v_source_version,
        'target_version',(SELECT version FROM sokhach.customer WHERE id=p_pair.target_customer_id),
        'source_pid',p_pair.source_pid,
        'target_pid',(SELECT pid FROM sokhach.receipt WHERE id=p_pair.target_receipt_id));
    INSERT INTO sokhach.offset_command(low_customer_id,high_customer_id,key,payload,result)
    VALUES (least(p_pair.source_customer_id,p_pair.target_customer_id),
        greatest(p_pair.source_customer_id,p_pair.target_customer_id),p_key,p_payload,v_result);
    RETURN v_result;
END $$;

CREATE FUNCTION sokhach.record_offset(target_customer_id bigint,target_version bigint,
    source_customer_id bigint,source_version bigint,idempotency_key text,date date,amount_vnd bigint,
    reference text DEFAULT NULL)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, sokhach, pg_temp AS $$
DECLARE v_payload jsonb:=jsonb_build_object('command','record_offset','target',target_customer_id,
        'source',source_customer_id,'date',date,'amount_vnd',amount_vnd)
        || CASE WHEN reference IS NULL THEN '{}'::jsonb ELSE jsonb_build_object('reference',reference) END;
    v_retry jsonb; v_credit numeric; v_receipt jsonb; v_pair sokhach.offset_pair%ROWTYPE;
    v_event bigint; v_id bigint; v_pid text; v_changes jsonb;
BEGIN
    v_retry:=sokhach._begin_offset(target_customer_id,target_version,source_customer_id,
        source_version,idempotency_key,v_payload);
    IF v_retry IS NOT NULL THEN RETURN v_retry; END IF;
    IF amount_vnd IS NULL OR amount_vnd<=0 THEN RAISE EXCEPTION 'INVALID_VND'; END IF;
    IF date IS NULL THEN RAISE EXCEPTION 'INVALID_DATE'; END IF;
    IF date>(clock_timestamp() AT TIME ZONE 'Asia/Ho_Chi_Minh')::date
    THEN RAISE EXCEPTION 'FUTURE_DATE'; END IF;
    IF EXISTS (SELECT 1 FROM sokhach.customer WHERE id=source_customer_id AND archived)
    THEN RAISE EXCEPTION 'OFFSET_SOURCE_ARCHIVED'; END IF;
    SELECT greatest(-sum(outstanding_vnd),0) INTO v_credit FROM sokhach.v_outstanding_month
        WHERE customer_id=source_customer_id;
    IF v_credit IS NULL OR amount_vnd>v_credit THEN
        RAISE EXCEPTION 'OFFSET_EXCEEDS_CREDIT'
            USING DETAIL=jsonb_build_object('available_credit_vnd',v_credit::text)::text;
    END IF;
    v_id:=nextval(pg_get_serial_sequence('sokhach.offset_pair','id'));
    v_pid:=sokhach._next_pid(source_customer_id);
    v_receipt:=sokhach.record_receipt(target_customer_id,target_version,
        chr(31)||'offset:'||v_id||':record',date,'CẤN TRỪ',amount_vnd,reference);
    INSERT INTO sokhach.event(customer_id,kind,actor,"before","after",idempotency_key)
    VALUES (source_customer_id,'receipt',sokhach._actor(),'{}',jsonb_build_object(
        'receipt',v_pid,'offset_pair_id',v_id,'pid',v_pid,'date',date,
        'amount_vnd',(-amount_vnd)::text,'counterparty_customer_id',target_customer_id,
        'counterparty_name',(SELECT name FROM sokhach.customer WHERE id=target_customer_id)),idempotency_key)
    RETURNING id INTO v_event;
    INSERT INTO sokhach.offset_pair(id,source_customer_id,target_customer_id,target_receipt_id,
        source_pid,date,amount_vnd,created_by_event) OVERRIDING SYSTEM VALUE
    VALUES(v_id,source_customer_id,target_customer_id,(v_receipt->>'receipt_id')::bigint,
        v_pid,date,amount_vnd,v_event) RETURNING * INTO v_pair;
    v_changes:=sokhach.reallocate(source_customer_id,idempotency_key);
    RETURN sokhach._finish_offset(v_pair,idempotency_key,v_payload,jsonb_build_object(
        'target_receipt',v_receipt,'source_reallocated',v_changes));
EXCEPTION WHEN numeric_value_out_of_range THEN RAISE EXCEPTION 'INVALID_VND';
END $$;

-- Caller may be either participant. Versions bind that caller and the other book.
CREATE FUNCTION sokhach._change_offset(customer_id bigint,expected_version bigint,
    other_version bigint,idempotency_key text,offset_pair_id bigint,new_date date,reason text,
    is_void boolean) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, sokhach, pg_temp AS $$
DECLARE v_pair sokhach.offset_pair%ROWTYPE; v_payload jsonb; v_retry jsonb;
    v_target_version bigint; v_source_version bigint; v_target jsonb; v_changes jsonb;
    v_event bigint; v_pid text; v_before jsonb; v_after jsonb; v_internal_key text;
BEGIN
    SELECT * INTO v_pair FROM sokhach.offset_pair WHERE id=offset_pair_id;
    IF NOT FOUND OR customer_id NOT IN (v_pair.source_customer_id,v_pair.target_customer_id)
    THEN RAISE EXCEPTION 'OFFSET_NOT_FOUND'; END IF;
    v_source_version:=CASE WHEN customer_id=v_pair.source_customer_id THEN expected_version ELSE other_version END;
    v_target_version:=CASE WHEN customer_id=v_pair.target_customer_id THEN expected_version ELSE other_version END;
    v_payload:=jsonb_build_object('command',CASE WHEN is_void THEN 'void_offset' ELSE 'edit_offset_date' END,
        'offset_pair_id',offset_pair_id,'date',new_date,'reason',reason);
    v_retry:=sokhach._begin_offset(v_pair.target_customer_id,v_target_version,
        v_pair.source_customer_id,v_source_version,idempotency_key,v_payload);
    IF v_retry IS NOT NULL THEN RETURN v_retry; END IF;
    -- Refresh after waiting for customer locks, never lock pair before customers.
    SELECT * INTO v_pair FROM sokhach.offset_pair WHERE id=offset_pair_id;
    IF v_pair.voided_by_event IS NOT NULL THEN RAISE EXCEPTION 'OFFSET_ALREADY_VOID'; END IF;
    IF is_void THEN
        IF reason IS NULL OR btrim(reason)='' THEN RAISE EXCEPTION 'VOID_REASON_REQUIRED'; END IF;
    ELSE
        IF new_date IS NULL THEN RAISE EXCEPTION 'INVALID_DATE'; END IF;
        IF new_date>(clock_timestamp() AT TIME ZONE 'Asia/Ho_Chi_Minh')::date
        THEN RAISE EXCEPTION 'FUTURE_DATE'; END IF;
        IF new_date=v_pair.date THEN RAISE EXCEPTION 'NO_CHANGE'; END IF;
    END IF;
    SELECT pid INTO v_pid FROM sokhach.receipt WHERE id=v_pair.target_receipt_id;
    v_internal_key:=chr(31)||'offset:'||v_pair.id||':'||idempotency_key;
    IF is_void THEN
        v_target:=sokhach._void_receipt(v_pair.target_customer_id,v_target_version,v_internal_key,v_pid,reason);
    ELSE
        v_target:=sokhach._edit_receipt_meta(v_pair.target_customer_id,v_target_version,
            v_internal_key,v_pid,new_date,'CẤN TRỪ');
    END IF;
    v_before:=jsonb_build_object('receipt',v_pair.source_pid,'offset_pair_id',v_pair.id,
        'date',v_pair.date,'amount_vnd',(-v_pair.amount_vnd)::text,
        'counterparty_customer_id',v_pair.target_customer_id,
        'counterparty_name',(SELECT name FROM sokhach.customer WHERE id=v_pair.target_customer_id));
    v_after:=v_before || CASE WHEN is_void THEN jsonb_build_object('void_reason',btrim(reason))
        ELSE jsonb_build_object('date',new_date) END;
    INSERT INTO sokhach.event(customer_id,kind,actor,"before","after",idempotency_key)
    VALUES(v_pair.source_customer_id,CASE WHEN is_void THEN 'void' ELSE 'receipt_edit' END,
        sokhach._actor(),v_before,v_after,idempotency_key) RETURNING id INTO v_event;
    IF is_void THEN
        UPDATE sokhach.offset_pair SET void_reason=btrim(reason),voided_by_event=v_event WHERE id=v_pair.id;
    ELSE
        UPDATE sokhach.offset_pair SET date=new_date,changed_by_event=v_event WHERE id=v_pair.id;
    END IF;
    v_changes:=sokhach.reallocate(v_pair.source_customer_id,idempotency_key);
    RETURN sokhach._finish_offset(v_pair,idempotency_key,v_payload,jsonb_build_object(
        'target_receipt',v_target,'source_reallocated',v_changes));
EXCEPTION WHEN numeric_value_out_of_range THEN RAISE EXCEPTION 'INVALID_VND';
END $$;

CREATE FUNCTION sokhach.void_offset(customer_id bigint,expected_version bigint,other_version bigint,
    idempotency_key text,offset_pair_id bigint,reason text) RETURNS jsonb
LANGUAGE sql SECURITY DEFINER SET search_path = pg_catalog, sokhach, pg_temp AS $$
    SELECT sokhach._change_offset(customer_id,expected_version,other_version,idempotency_key,
        offset_pair_id,NULL,reason,true)
$$;
CREATE FUNCTION sokhach.edit_offset_date(customer_id bigint,expected_version bigint,other_version bigint,
    idempotency_key text,offset_pair_id bigint,date date) RETURNS jsonb
LANGUAGE sql SECURITY DEFINER SET search_path = pg_catalog, sokhach, pg_temp AS $$
    SELECT sokhach._change_offset(customer_id,expected_version,other_version,idempotency_key,
        offset_pair_id,date,NULL,false)
$$;

CREATE FUNCTION sokhach.list_offset_sources(target_customer_id bigint) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, sokhach, pg_temp AS $$
BEGIN
    PERFORM sokhach._actor();
    IF NOT EXISTS (SELECT 1 FROM sokhach.customer WHERE id=target_customer_id)
    THEN RAISE EXCEPTION 'CUSTOMER_NOT_FOUND'; END IF;
    -- ponytail: no customer-group key; sort every eligible book by name until group key is approved.
    RETURN coalesce((SELECT jsonb_agg(jsonb_build_object('customer_id',c.id,'name',c.name,
        'commodity',m.name,'version',c.version,'outstanding_vnd',b.total::text,
        'available_credit_vnd',(-b.total)::text) ORDER BY c.name COLLATE "C",c.id)
      FROM sokhach.customer c LEFT JOIN sokhach.commodity m ON m.id=c.commodity_id
      JOIN (SELECT customer_id,sum(outstanding_vnd) AS total FROM sokhach.v_outstanding_month
            GROUP BY customer_id HAVING sum(outstanding_vnd)<0) b ON b.customer_id=c.id
      WHERE c.id<>target_customer_id AND NOT c.archived),'[]'::jsonb);
END $$;

CREATE FUNCTION sokhach.list_customers() RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, sokhach, pg_temp AS $$
BEGIN
    PERFORM sokhach._actor();
    RETURN (SELECT jsonb_build_object('customers',coalesce(jsonb_agg(
        jsonb_build_object('id',id,'name',name,'status',status,
                           'commodity',commodity,'transport_mode',transport_mode)
        ORDER BY name COLLATE "C",id),'[]'::jsonb))
      FROM (SELECT c.id,c.name,
                   CASE WHEN cc.status='active' AND co.status='active'
                        THEN 'active' ELSE 'NO_BASELINE' END AS status,
                   m.name AS commodity,c.transport_mode
              FROM sokhach.customer c
              LEFT JOIN sokhach.commodity m ON m.id=c.commodity_id
              LEFT JOIN sokhach.cutover_customer cc ON cc.customer_id=c.id
              LEFT JOIN sokhach.cutover co ON co.id=cc.cutover_id) q);
END $$;

CREATE FUNCTION sokhach.get_dashboard() RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, sokhach, pg_temp AS $$
DECLARE d date := (now() AT TIME ZONE 'Asia/Ho_Chi_Minh')::date; m date := date_trunc('month', d)::date;
BEGIN
  PERFORM sokhach._actor();
  RETURN (WITH a AS (SELECT c.id,c.name,c.commodity_id,c.transport_mode,coalesce(sum(v.outstanding_vnd),0)::bigint total
    FROM sokhach.customer c JOIN sokhach.cutover_customer cc ON cc.customer_id=c.id AND cc.status='active'
    JOIN sokhach.cutover x ON x.id=cc.cutover_id AND x.status='active' LEFT JOIN sokhach.v_outstanding_month v ON v.customer_id=c.id
    WHERE NOT c.archived GROUP BY c.id,c.name,c.commodity_id,c.transport_mode),
  p AS (SELECT t.customer_id,count(*)::int n FROM sokhach.v_trip_current t JOIN a ON a.id=t.customer_id
    LEFT JOIN LATERAL (SELECT unit_price_vnd,other_fee_vnd FROM sokhach.trip_price_rev z WHERE z.trip_id=t.id ORDER BY z.id DESC LIMIT 1) z ON true
    WHERE NOT t.deleted AND t.status='confirmed' AND z.unit_price_vnd IS NULL AND NOT ((t.container IS NULL OR t.container='') AND z.other_fee_vnd IS NOT NULL) GROUP BY t.customer_id),
  r AS (SELECT customer_id,count(*)::int n FROM sokhach.v_trip_current t JOIN a ON a.id=t.customer_id WHERE NOT t.deleted AND t.status='pending_review' GROUP BY customer_id),
  e AS (SELECT actor,coalesce(sum(jsonb_array_length(e."after"->'trips')) FILTER (WHERE kind='paste'),0)::int trips,count(*) FILTER (WHERE kind='receipt')::int receipts,
    coalesce(sum((e."after"->>'amount_vnd')::bigint) FILTER (WHERE kind='receipt'),0)::bigint received,
    count(*) FILTER (WHERE kind='void' AND EXISTS (SELECT 1 FROM sokhach.receipt z WHERE z.voided_by_event=e.id))::int voids
    FROM sokhach.event e WHERE (e.at AT TIME ZONE 'Asia/Ho_Chi_Minh')::date=d
      AND (kind IN ('paste','receipt') OR (kind='void' AND EXISTS (SELECT 1 FROM sokhach.receipt z WHERE z.voided_by_event=e.id))) GROUP BY actor),
  t AS (SELECT coalesce(sum(total) FILTER (WHERE total>0),0)::bigint recv,count(*) FILTER (WHERE total>0)::int recv_n,
    coalesce(sum(total) FILTER (WHERE total<0),0)::bigint cred,count(*) FILTER (WHERE total<0)::int cred_n FROM a),
  aging AS (SELECT b.bucket,b.ord,coalesce(sum(v.outstanding_vnd),0)::bigint amount FROM (VALUES ('current',0),('1-2',1),('3-6',2),('over-6',3)) b(bucket,ord)
    LEFT JOIN sokhach.v_outstanding_month v ON v.customer_id IN (SELECT id FROM a WHERE total>0)
    AND CASE WHEN ((extract(year FROM m)-extract(year FROM v.debt_month))*12+extract(month FROM m)-extract(month FROM v.debt_month))<=0 THEN 0 WHEN ((extract(year FROM m)-extract(year FROM v.debt_month))*12+extract(month FROM m)-extract(month FROM v.debt_month))<=2 THEN 1 WHEN ((extract(year FROM m)-extract(year FROM v.debt_month))*12+extract(month FROM m)-extract(month FROM v.debt_month))<=6 THEN 2 ELSE 3 END=b.ord GROUP BY b.bucket,b.ord)
  SELECT jsonb_build_object('as_of',d::text,'receivable',jsonb_build_object('total_vnd',t.recv::text,'customers',t.recv_n),'credit',jsonb_build_object('total_vnd',t.cred::text,'customers',t.cred_n),
    'by_commodity',coalesce((SELECT jsonb_agg(jsonb_build_object('commodity',q.commodity,'transport_mode',q.transport_mode,'customers',q.n,'receivable_vnd',q.amount::text) ORDER BY q.commodity IS NULL,q.commodity COLLATE "C",q.transport_mode NULLS LAST) FROM (SELECT c.commodity_id,m.name commodity,c.transport_mode,count(*)::int n,sum(c.total)::bigint amount FROM a c LEFT JOIN sokhach.commodity m ON m.id=c.commodity_id WHERE c.total>0 GROUP BY c.commodity_id,m.name,c.transport_mode) q),'[]'::jsonb),
    'aging',(SELECT jsonb_agg(jsonb_build_object('bucket',bucket,'receivable_vnd',amount::text) ORDER BY ord) FROM aging),
    'top_debtors',coalesce((SELECT jsonb_agg(jsonb_build_object('customer_id',q.id,'name',q.name,'commodity',q.commodity,'transport_mode',q.transport_mode,'outstanding_vnd',q.total::text,'oldest_open_month',q.oldest::text) ORDER BY q.total DESC,q.name COLLATE "C",q.id) FROM (SELECT a.*,m.name commodity,min(v.debt_month) FILTER (WHERE v.outstanding_vnd>0) oldest FROM a LEFT JOIN sokhach.commodity m ON m.id=a.commodity_id LEFT JOIN sokhach.v_outstanding_month v ON v.customer_id=a.id WHERE a.total>0 GROUP BY a.id,a.name,a.commodity_id,a.transport_mode,a.total,m.name ORDER BY a.total DESC,a.name COLLATE "C",a.id LIMIT 10) q),'[]'::jsonb),
    'todo',jsonb_build_object('missing_price',coalesce((SELECT jsonb_agg(jsonb_build_object('customer_id',a.id,'name',a.name,'count',p.n) ORDER BY a.name COLLATE "C",a.id) FROM p JOIN a ON a.id=p.customer_id),'[]'::jsonb),'pending_review',coalesce((SELECT jsonb_agg(jsonb_build_object('customer_id',a.id,'name',a.name,'count',r.n) ORDER BY a.name COLLATE "C",a.id) FROM r JOIN a ON a.id=r.customer_id),'[]'::jsonb),'no_baseline',coalesce((SELECT jsonb_agg(jsonb_build_object('customer_id',c.id,'name',c.name) ORDER BY c.name COLLATE "C",c.id) FROM sokhach.customer c WHERE NOT c.archived AND NOT EXISTS (SELECT 1 FROM a WHERE a.id=c.id)),'[]'::jsonb),'credit',coalesce((SELECT jsonb_agg(jsonb_build_object('customer_id',id,'name',name,'credit_vnd',total::text) ORDER BY name COLLATE "C",id) FROM a WHERE total<0),'[]'::jsonb)),
    'today',jsonb_build_object('trips',coalesce((SELECT sum(trips) FROM e),0),'receipts',coalesce((SELECT sum(receipts) FROM e),0),'received_vnd',coalesce((SELECT sum(received) FROM e),0)::text,'voids',coalesce((SELECT sum(voids) FROM e),0),'by_actor',coalesce((SELECT jsonb_agg(jsonb_build_object('actor',actor,'trips',trips,'receipts',receipts,'received_vnd',received::text,'voids',voids) ORDER BY actor COLLATE "C") FROM e),'[]'::jsonb))) FROM t);
END $$;

CREATE FUNCTION sokhach.get_receivables_matrix(p_year int) RETURNS jsonb
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



-- PR-A cache contract; reader definitions above remain unchanged.
CREATE OR REPLACE FUNCTION sokhach._fee_cache_check() RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog,sokhach,pg_temp AS $$
DECLARE v_trip bigint; v_cache bigint; v_total bigint; v_count bigint;
BEGIN IF TG_OP='DELETE' THEN v_trip:=OLD.trip_id; ELSE v_trip:=NEW.trip_id; END IF; IF v_trip IS NULL THEN IF TG_OP='DELETE' THEN RETURN OLD; ELSE RETURN NEW; END IF; END IF;
 SELECT p.other_fee_vnd INTO v_cache FROM sokhach.trip_price_rev p WHERE p.trip_id=v_trip ORDER BY p.id DESC LIMIT 1;
 SELECT count(*),sum(amount_vnd) INTO v_count,v_total FROM sokhach.trip_fee_line WHERE trip_id=v_trip AND voided_by_event IS NULL;
 IF (v_count=0 AND v_cache IS NOT NULL) OR (v_count>0 AND v_cache IS DISTINCT FROM v_total) THEN RAISE EXCEPTION 'FEE_CACHE_MISMATCH'; END IF;
 IF TG_OP='DELETE' THEN RETURN OLD; ELSE RETURN NEW; END IF; END $$;
CREATE OR REPLACE FUNCTION sokhach._sync_trip_fee(p_trip_id bigint,p_event_id bigint) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,sokhach,pg_temp AS $$
DECLARE v_unit bigint; v_old bigint; v_total bigint; v_count bigint;
BEGIN SELECT unit_price_vnd,other_fee_vnd INTO v_unit,v_old FROM sokhach.trip_price_rev WHERE trip_id=p_trip_id ORDER BY id DESC LIMIT 1;
 SELECT count(*),sum(amount_vnd) INTO v_count,v_total FROM sokhach.trip_fee_line WHERE trip_id=p_trip_id AND voided_by_event IS NULL;
 IF v_count=0 THEN v_total:=NULL; END IF; IF v_old IS NOT DISTINCT FROM v_total THEN RETURN; END IF;
 INSERT INTO sokhach.trip_price_rev(trip_id,customer_id,unit_price_vnd,other_fee_vnd,created_by_event) SELECT p_trip_id,t.customer_id,v_unit,v_total,p_event_id FROM sokhach.trip t WHERE t.id=p_trip_id;
END $$;

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
DO $$ BEGIN IF NOT EXISTS(SELECT 1 FROM pg_trigger WHERE tgrelid='sokhach.trip_fee_line'::regclass AND tgname='trip_fee_cache_check') THEN CREATE CONSTRAINT TRIGGER trip_fee_cache_check AFTER INSERT OR UPDATE OR DELETE ON sokhach.trip_fee_line DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION sokhach._fee_cache_check(); END IF; END $$;
DO $$ BEGIN IF NOT EXISTS(SELECT 1 FROM pg_trigger WHERE tgrelid='sokhach.trip_price_rev'::regclass AND tgname='trip_price_cache_check') THEN CREATE CONSTRAINT TRIGGER trip_price_cache_check AFTER INSERT OR UPDATE ON sokhach.trip_price_rev DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION sokhach._fee_cache_check(); END IF; END $$;
DO $$ BEGIN IF NOT EXISTS(SELECT 1 FROM pg_trigger WHERE tgrelid='sokhach.trip_fee_line'::regclass AND tgname='fee_line_guard')
 THEN CREATE TRIGGER fee_line_guard BEFORE INSERT OR UPDATE OR DELETE ON sokhach.trip_fee_line FOR EACH ROW EXECUTE FUNCTION sokhach._guard_fee_line(); END IF; END $$;
CREATE OR REPLACE FUNCTION sokhach.v7_fee_migration_dry_run() RETURNS TABLE(orphan_zero_fee bigint,null_price_with_adjustment bigint) LANGUAGE sql SECURITY DEFINER SET search_path=pg_catalog,sokhach,pg_temp AS $$
 SELECT (SELECT count(*) FROM sokhach.trip t JOIN LATERAL
   (SELECT unit_price_vnd,other_fee_vnd FROM sokhach.trip_price_rev p WHERE p.trip_id=t.id ORDER BY p.id DESC LIMIT 1)p ON true
   WHERE coalesce(t.container,'')='' AND p.unit_price_vnd IS NULL
     AND (p.other_fee_vnd IS NOT NULL OR EXISTS(SELECT 1 FROM sokhach.adjustment a
       WHERE a.trip_id=t.id AND a.field='other_fee_vnd' AND NOT a.fee_absorbed))
     AND coalesce(p.other_fee_vnd,0)+coalesce((SELECT sum(a.amount_vnd) FROM sokhach.adjustment a
       WHERE a.trip_id=t.id AND a.field='other_fee_vnd' AND NOT a.fee_absorbed),0)=0
     AND NOT EXISTS(SELECT 1 FROM sokhach.trip_fee_line l WHERE l.trip_id=t.id)),
   (SELECT count(DISTINCT t.id) FROM sokhach.adjustment a JOIN sokhach.trip t ON t.id=a.trip_id
     JOIN LATERAL(SELECT unit_price_vnd FROM sokhach.trip_price_rev p WHERE p.trip_id=t.id ORDER BY p.id DESC LIMIT 1)p ON true
     WHERE a.field='other_fee_vnd' AND NOT a.fee_absorbed AND p.unit_price_vnd IS NULL
       AND coalesce(t.container,'')<>'' AND NOT EXISTS(SELECT 1 FROM sokhach.trip_fee_line l WHERE l.trip_id=t.id));
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
 IF l IS NOT NULL AND l->>'unit_price_vnd' IS NULL THEN RAISE EXCEPTION 'LEGACY_NO_UNIT_PRICE'; END IF;
 RETURN p_target||jsonb_build_object('fee_lines',sokhach._fee_lines(t.id,CASE WHEN l IS NOT NULL THEN v_id END),
   'counted_vnd',l->>'counted_vnd');
EXCEPTION WHEN invalid_text_representation OR numeric_value_out_of_range THEN RAISE EXCEPTION 'INVALID_TRIP';
END $$;

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

-- CHUNG-TU-01: ảnh chứng từ gắn phiếu thu. Không đổi tiền, phân bổ hay khóa tháng.
CREATE OR REPLACE FUNCTION sokhach._guard_receipt_image() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog,sokhach,pg_temp AS $$
BEGIN
 IF TG_OP='DELETE' THEN RAISE EXCEPTION 'RECEIPT_IMAGE_IMMUTABLE'; END IF;
 IF OLD.removed_by_event IS NOT NULL OR NEW.removed_by_event IS NULL
    OR (to_jsonb(NEW)-'removed_by_event'-'removed_reason') IS DISTINCT FROM (to_jsonb(OLD)-'removed_by_event'-'removed_reason')
 THEN RAISE EXCEPTION 'RECEIPT_IMAGE_IMMUTABLE'; END IF;
 RETURN NEW;
END $$;
DO $$ BEGIN IF NOT EXISTS(SELECT 1 FROM pg_trigger WHERE tgrelid='sokhach.receipt_image'::regclass AND tgname='receipt_image_guard')
 THEN CREATE TRIGGER receipt_image_guard BEFORE UPDATE OR DELETE ON sokhach.receipt_image FOR EACH ROW EXECUTE FUNCTION sokhach._guard_receipt_image(); END IF; END $$;
CREATE OR REPLACE FUNCTION sokhach._receipt_image_matches(p_sha256 text,p_exclude bigint) RETURNS jsonb
LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog,sokhach,pg_temp AS $$
 SELECT coalesce(jsonb_agg(jsonb_build_object('image_id',i.id,'customer_id',r.customer_id,'customer_name',c.name,
   'pid',r.pid,'date',r.date,'voided',r.voided_by_event IS NOT NULL) ORDER BY r.date,c.name COLLATE "C",r.pid COLLATE "C"),'[]'::jsonb)
 FROM sokhach.receipt_image i JOIN sokhach.receipt r ON r.id=i.receipt_id JOIN sokhach.customer c ON c.id=r.customer_id
 WHERE i.sha256=p_sha256 AND i.removed_by_event IS NULL AND i.id IS DISTINCT FROM p_exclude;
$$;
CREATE OR REPLACE FUNCTION sokhach.attach_receipt_image(customer_id bigint,expected_version bigint,idempotency_key text,
    pid text,content_type text,data bytea) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,sokhach,pg_temp AS $$
DECLARE v_sha text:=CASE WHEN data IS NULL THEN NULL ELSE encode(sha256(data),'hex') END;
 v_payload jsonb:=jsonb_build_object('command','attach_receipt_image','pid',pid,'content_type',content_type,'sha256',v_sha);
 v_retry jsonb; r sokhach.receipt%ROWTYPE; v_id bigint; v_event bigint; v_image jsonb; v_ok boolean;
BEGIN
 v_retry:=sokhach._begin_command(customer_id,expected_version,idempotency_key,v_payload);
 IF v_retry IS NOT NULL THEN RETURN v_retry; END IF;
 -- plpgsql đọc điều kiện IF tới chữ THEN đầu tiên, nên CASE kiểm đầu file tính riêng.
 v_ok:=data IS NOT NULL AND CASE content_type
     WHEN 'image/png' THEN substring(data FROM 1 FOR 8)='\x89504e470d0a1a0a'::bytea
     WHEN 'image/jpeg' THEN substring(data FROM 1 FOR 3)='\xffd8ff'::bytea
     WHEN 'image/webp' THEN substring(data FROM 1 FOR 4)='\x52494646'::bytea AND substring(data FROM 9 FOR 4)='\x57454250'::bytea
     ELSE false END;
 IF NOT coalesce(v_ok,false) THEN RAISE EXCEPTION 'IMAGE_INVALID'; END IF;
 IF octet_length(data)>2097152 THEN RAISE EXCEPTION 'IMAGE_TOO_LARGE'; END IF;
 SELECT * INTO r FROM sokhach.receipt WHERE receipt.customer_id=attach_receipt_image.customer_id
   AND receipt.pid=attach_receipt_image.pid FOR UPDATE;
 IF NOT FOUND THEN RAISE EXCEPTION 'RECEIPT_NOT_FOUND'; END IF;
 IF r.voided_by_event IS NOT NULL OR r.void_reason IS NOT NULL THEN RAISE EXCEPTION 'RECEIPT_ALREADY_VOID'; END IF;
 IF EXISTS(SELECT 1 FROM sokhach.receipt_image i WHERE i.receipt_id=r.id AND i.sha256=v_sha AND i.removed_by_event IS NULL)
 THEN RAISE EXCEPTION 'IMAGE_DUPLICATE'; END IF;
 IF (SELECT count(*) FROM sokhach.receipt_image i WHERE i.receipt_id=r.id AND i.removed_by_event IS NULL)>=5
 THEN RAISE EXCEPTION 'IMAGE_LIMIT'; END IF;
 v_id:=nextval(pg_get_serial_sequence('sokhach.receipt_image','id'));
 v_image:=jsonb_build_object('id',v_id,'receipt_id',r.id,'pid',r.pid,'sha256',v_sha,'content_type',content_type,
   'byte_size',octet_length(data));
 INSERT INTO sokhach.event(customer_id,kind,actor,"before","after",idempotency_key)
   VALUES(customer_id,'receipt_image',sokhach._actor(),'{}',jsonb_build_object('image',v_image),idempotency_key)
   RETURNING id INTO v_event;
 INSERT INTO sokhach.receipt_image(id,customer_id,receipt_id,sha256,content_type,data,created_by_event)
   OVERRIDING SYSTEM VALUE VALUES(v_id,customer_id,r.id,v_sha,content_type,data,v_event);
 RETURN sokhach._finish_command(customer_id,idempotency_key,v_payload,
   jsonb_build_object('image',v_image,'duplicates',sokhach._receipt_image_matches(v_sha,v_id)));
END $$;
CREATE OR REPLACE FUNCTION sokhach.remove_receipt_image(customer_id bigint,expected_version bigint,idempotency_key text,
    image_id bigint,reason text) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,sokhach,pg_temp AS $$
DECLARE v_payload jsonb:=jsonb_build_object('command','remove_receipt_image','image_id',image_id,'reason',reason);
 v_retry jsonb; i sokhach.receipt_image%ROWTYPE; r sokhach.receipt%ROWTYPE; v_event bigint; v_image jsonb;
BEGIN
 v_retry:=sokhach._begin_command(customer_id,expected_version,idempotency_key,v_payload);
 IF v_retry IS NOT NULL THEN RETURN v_retry; END IF;
 IF reason IS NULL OR btrim(reason)='' THEN RAISE EXCEPTION 'IMAGE_REMOVE_REASON_REQUIRED'; END IF;
 SELECT * INTO i FROM sokhach.receipt_image WHERE receipt_image.id=remove_receipt_image.image_id
   AND receipt_image.customer_id=remove_receipt_image.customer_id FOR UPDATE;
 IF NOT FOUND THEN RAISE EXCEPTION 'IMAGE_NOT_FOUND'; END IF;
 IF i.removed_by_event IS NOT NULL THEN RAISE EXCEPTION 'IMAGE_ALREADY_REMOVED'; END IF;
 SELECT * INTO r FROM sokhach.receipt WHERE receipt.id=i.receipt_id;
 IF r.voided_by_event IS NOT NULL OR r.void_reason IS NOT NULL THEN RAISE EXCEPTION 'RECEIPT_ALREADY_VOID'; END IF;
 v_image:=jsonb_build_object('id',i.id,'receipt_id',r.id,'pid',r.pid,'sha256',i.sha256,'content_type',i.content_type,
   'byte_size',octet_length(i.data));
 INSERT INTO sokhach.event(customer_id,kind,actor,"before","after",idempotency_key)
   VALUES(customer_id,'receipt_image_remove',sokhach._actor(),jsonb_build_object('image',v_image),
     jsonb_build_object('image',v_image||jsonb_build_object('removed',true,'reason',btrim(reason))),idempotency_key)
   RETURNING id INTO v_event;
 UPDATE sokhach.receipt_image SET removed_reason=btrim(reason),removed_by_event=v_event WHERE receipt_image.id=i.id;
 RETURN sokhach._finish_command(customer_id,idempotency_key,v_payload,jsonb_build_object('image_id',i.id,'removed',true));
END $$;
CREATE OR REPLACE FUNCTION sokhach.list_receipt_images(customer_id bigint) RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path=pg_catalog,sokhach,pg_temp AS $$
BEGIN
 IF NOT EXISTS(SELECT 1 FROM sokhach.customer c WHERE c.id=list_receipt_images.customer_id) THEN RAISE EXCEPTION 'CUSTOMER_NOT_FOUND'; END IF;
 RETURN jsonb_build_object('images',(SELECT coalesce(jsonb_agg(jsonb_build_object('id',i.id,'receipt_id',i.receipt_id,'pid',r.pid,
   'sha256',i.sha256,'content_type',i.content_type,'byte_size',octet_length(i.data),'at',e.at,'actor',e.actor) ORDER BY i.receipt_id,i.id),'[]'::jsonb)
  FROM sokhach.receipt_image i JOIN sokhach.receipt r ON r.id=i.receipt_id JOIN sokhach.event e ON e.id=i.created_by_event
  WHERE i.customer_id=list_receipt_images.customer_id AND i.removed_by_event IS NULL));
END $$;
CREATE OR REPLACE FUNCTION sokhach.get_receipt_image(customer_id bigint,image_id bigint) RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path=pg_catalog,sokhach,pg_temp AS $$
DECLARE v jsonb;
BEGIN
 SELECT jsonb_build_object('id',i.id,'content_type',i.content_type,'sha256',i.sha256,'removed',i.removed_by_event IS NOT NULL,
   'data_base64',translate(encode(i.data,'base64'),E'\n',''))
 INTO v FROM sokhach.receipt_image i WHERE i.id=get_receipt_image.image_id AND i.customer_id=get_receipt_image.customer_id;
 IF v IS NULL THEN RAISE EXCEPTION 'IMAGE_NOT_FOUND'; END IF;
 RETURN v;
END $$;
CREATE OR REPLACE FUNCTION sokhach.find_receipt_image(sha256 text) RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path=pg_catalog,sokhach,pg_temp AS $$
BEGIN
 IF find_receipt_image.sha256 IS NULL OR find_receipt_image.sha256 !~ '^[0-9a-f]{64}$' THEN RAISE EXCEPTION 'IMAGE_INVALID'; END IF;
 RETURN jsonb_build_object('matches',sokhach._receipt_image_matches(find_receipt_image.sha256,NULL));
END $$;

-- BANG-GIA-01: tra giá theo sổ, ngày xe nhập kho, kho đi và nhóm shipper. Không tra được thì trả lý do, không đoán giá.
CREATE OR REPLACE FUNCTION sokhach._price_key(p_value text) RETURNS text
LANGUAGE sql IMMUTABLE SET search_path=pg_catalog,sokhach,pg_temp AS $$
 SELECT nullif(btrim(regexp_replace(upper(coalesce(p_value,'')),
   U&'[\0009-\000D\0020\0085\00A0\1680\2000-\200A\2028\2029\202F\205F\3000]+',' ','g')),'')
$$;

CREATE OR REPLACE FUNCTION sokhach._price_table(p_customer bigint) RETURNS jsonb
LANGUAGE sql STABLE SET search_path=pg_catalog,sokhach,pg_temp AS $$
 SELECT jsonb_build_object(
  'tt_shippers',(SELECT coalesce(jsonb_agg(s.name ORDER BY s.shipper_key),'[]') FROM sokhach.price_tt_shipper s
     WHERE s.customer_id=p_customer),
  'locations',(SELECT coalesce(jsonb_agg(jsonb_build_object('name',l.name,'aliases',
       (SELECT coalesce(jsonb_agg(a.alias ORDER BY a.alias_key),'[]') FROM sokhach.price_location_alias a
        WHERE a.location_id=l.id)) ORDER BY l.name_key),'[]') FROM sokhach.price_location l WHERE l.customer_id=p_customer),
  'periods',(SELECT coalesce(jsonb_agg(jsonb_build_object('valid_from',p.valid_from,'valid_to',p.valid_to,'rates',
       (SELECT coalesce(jsonb_agg(jsonb_build_object('location',l.name,'tier',r.tier,'unit_price_vnd',r.unit_price_vnd::text)
          ORDER BY l.name_key,r.tier),'[]') FROM sokhach.price_rate r JOIN sokhach.price_location l ON l.id=r.location_id
        WHERE r.period_id=p.id)) ORDER BY p.valid_from,p.valid_to NULLS LAST,p.id),'[]')
     FROM sokhach.price_period p WHERE p.customer_id=p_customer))
$$;

CREATE OR REPLACE FUNCTION sokhach._lookup_price(p_customer bigint,p_date date,p_origin text,p_shipper text) RETURNS jsonb
LANGUAGE plpgsql STABLE SET search_path=pg_catalog,sokhach,pg_temp AS $$
DECLARE v_key text:=sokhach._price_key(p_origin); v_loc sokhach.price_location%ROWTYPE; v_tier text; v_rate record;
BEGIN
 IF NOT EXISTS (SELECT 1 FROM sokhach.price_period WHERE customer_id=p_customer) THEN
   RETURN jsonb_build_object('reason','NO_TABLE'); END IF;
 IF p_date IS NULL THEN RETURN jsonb_build_object('reason','NO_DATE'); END IF;
 IF v_key IS NULL THEN RETURN jsonb_build_object('reason','NO_ORIGIN'); END IF;
 SELECT l.* INTO v_loc FROM sokhach.price_location l WHERE l.customer_id=p_customer AND (l.name_key=v_key
   OR EXISTS (SELECT 1 FROM sokhach.price_location_alias a WHERE a.location_id=l.id AND a.alias_key=v_key));
 IF NOT FOUND THEN RETURN jsonb_build_object('reason','UNKNOWN_LOCATION'); END IF;
 -- Q3: shipper trong danh sách TT lấy giá TT; mọi shipper khác, kể cả trống, lấy giá khách.
 v_tier:=CASE WHEN EXISTS (SELECT 1 FROM sokhach.price_tt_shipper s WHERE s.customer_id=p_customer
   AND s.shipper_key=sokhach._price_key(p_shipper)) THEN 'tt' ELSE 'khach' END;
 SELECT p.valid_from,p.valid_to,r.unit_price_vnd INTO v_rate FROM sokhach.price_rate r
   JOIN sokhach.price_period p ON p.id=r.period_id
   WHERE r.location_id=v_loc.id AND r.tier=v_tier AND p.valid_from<=p_date AND (p.valid_to IS NULL OR p_date<=p.valid_to);
 IF FOUND THEN
   RETURN jsonb_build_object('unit_price_vnd',v_rate.unit_price_vnd::text,'tier',v_tier,'location',v_loc.name,
     'valid_from',v_rate.valid_from,'valid_to',v_rate.valid_to);
 END IF;
 -- Có đợt phủ ngày cho kho này nhưng thiếu ô của nhóm cần dùng: không lấy giá nhóm kia thay.
 RETURN jsonb_build_object('reason',CASE WHEN EXISTS (SELECT 1 FROM sokhach.price_rate r
     JOIN sokhach.price_period p ON p.id=r.period_id WHERE r.location_id=v_loc.id
       AND p.valid_from<=p_date AND (p.valid_to IS NULL OR p_date<=p.valid_to)) THEN 'NO_RATE' ELSE 'NO_PERIOD' END,
   'tier',v_tier,'location',v_loc.name);
END $$;

-- Giá theo bảng của từng chuyến có container; from_table = đơn giá hiện tại do bảng giá ghi.
CREATE OR REPLACE FUNCTION sokhach._price_trip_rows(p_customer bigint)
RETURNS TABLE(trip_id bigint,debt_month date,status text,unit_price_vnd bigint,other_fee_vnd bigint,
 from_table boolean,lookup jsonb,month_open boolean)
LANGUAGE sql STABLE SET search_path=pg_catalog,sokhach,pg_temp AS $$
 SELECT t.id,t.debt_month,t.status,p.unit_price_vnd,p.other_fee_vnd,
  EXISTS (SELECT 1 FROM sokhach.trip_price_source s JOIN sokhach.trip_price_rev sr ON sr.id=s.price_rev_id
    WHERE sr.trip_id=t.id AND sr.unit_price_vnd IS NOT DISTINCT FROM p.unit_price_vnd
      AND NOT EXISTS (SELECT 1 FROM sokhach.trip_price_rev x WHERE x.trip_id=t.id AND x.id>sr.id
        AND x.unit_price_vnd IS DISTINCT FROM sr.unit_price_vnd)),
  sokhach._lookup_price(p_customer,t.event_date,t.origin,t.shipper),
  NOT coalesce(ms.locked,t.debt_month<>date_trunc('month',clock_timestamp() AT TIME ZONE 'Asia/Ho_Chi_Minh')::date)
 FROM sokhach.v_trip_current t
 LEFT JOIN LATERAL (SELECT r.unit_price_vnd,r.other_fee_vnd FROM sokhach.trip_price_rev r
   WHERE r.trip_id=t.id ORDER BY r.id DESC LIMIT 1) p ON true
 LEFT JOIN sokhach.month_state ms ON (ms.customer_id,ms.month)=(t.customer_id,t.debt_month)
 WHERE t.customer_id=p_customer AND NOT t.deleted AND coalesce(t.container,'')<>''
$$;

CREATE OR REPLACE FUNCTION sokhach.get_price_table(customer_id bigint) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,sokhach,pg_temp AS $$
DECLARE v_version bigint;
BEGIN
 PERFORM sokhach._actor();
 SELECT c.version INTO v_version FROM sokhach.customer c WHERE c.id=get_price_table.customer_id;
 IF NOT FOUND THEN RAISE EXCEPTION 'CUSTOMER_NOT_FOUND'; END IF;
 -- Shipper đang có trong sổ và nhóm giá đang áp: để soát tên viết lệch so với danh sách TT.
 RETURN jsonb_build_object('customer_id',customer_id,'version',v_version,
  'price_table',sokhach._price_table(customer_id),
  'book_shippers',(SELECT coalesce(jsonb_agg(jsonb_build_object('name',x.name,'tier',x.tier,'trip_count',x.n)
      ORDER BY x.tier,x.name),'[]') FROM (
    SELECT min(btrim(t.shipper)) AS name,count(*) AS n,
      CASE WHEN EXISTS (SELECT 1 FROM sokhach.price_tt_shipper s WHERE s.customer_id=get_price_table.customer_id
        AND s.shipper_key=sokhach._price_key(t.shipper)) THEN 'tt' ELSE 'khach' END AS tier
    FROM sokhach.v_trip_current t WHERE t.customer_id=get_price_table.customer_id AND NOT t.deleted
      AND sokhach._price_key(t.shipper) IS NOT NULL GROUP BY sokhach._price_key(t.shipper),3) x));
END $$;

CREATE OR REPLACE FUNCTION sokhach.get_price_status(customer_id bigint) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,sokhach,pg_temp AS $$
DECLARE v_version bigint;
BEGIN
 PERFORM sokhach._actor();
 SELECT c.version INTO v_version FROM sokhach.customer c WHERE c.id=get_price_status.customer_id;
 IF NOT FOUND THEN RAISE EXCEPTION 'CUSTOMER_NOT_FOUND'; END IF;
 RETURN (WITH r AS (
   SELECT x.*,x.lookup->>'unit_price_vnd' AS table_price,
     x.status='confirmed' AND x.month_open AND x.unit_price_vnd IS NULL AND x.lookup ? 'unit_price_vnd' AS ready,
     x.unit_price_vnd IS NOT NULL AND x.lookup ? 'unit_price_vnd'
       AND x.unit_price_vnd::text<>x.lookup->>'unit_price_vnd' AS differs
   FROM sokhach._price_trip_rows(get_price_status.customer_id) x)
  SELECT jsonb_build_object('customer_id',get_price_status.customer_id,'version',v_version,
   'has_table',EXISTS (SELECT 1 FROM sokhach.price_period p WHERE p.customer_id=get_price_status.customer_id),
   'trips',coalesce(jsonb_agg(jsonb_build_object('trip_id',r.trip_id,'unit_price_vnd',r.unit_price_vnd::text,
       'from_table',r.from_table,'lookup',r.lookup,'ready',r.ready,'differs',r.differs) ORDER BY r.trip_id),'[]'),
   'ready_count',count(*) FILTER (WHERE r.ready),
   -- Chuyến chưa có giá chưa tính tiền; ghi đơn giá thì cộng thêm đơn giá + phụ phí (trống = 0 theo V7-BE).
   'ready_total_vnd',coalesce(sum(r.table_price::bigint+coalesce(r.other_fee_vnd,0)) FILTER (WHERE r.ready),0)::text,
   'ready_months',coalesce(jsonb_agg(DISTINCT r.debt_month) FILTER (WHERE r.ready),'[]'),
   'reapply_count',count(*) FILTER (WHERE r.differs AND r.from_table AND r.status='confirmed' AND r.month_open))
  FROM r);
END $$;

CREATE OR REPLACE FUNCTION sokhach._price_text(p_value jsonb) RETURNS text
LANGUAGE plpgsql IMMUTABLE SET search_path=pg_catalog,sokhach,pg_temp AS $$
BEGIN
 IF jsonb_typeof(p_value) IS DISTINCT FROM 'string' OR btrim(p_value#>>'{}')='' OR length(p_value#>>'{}')>200
 THEN RAISE EXCEPTION 'INVALID_PRICE_TABLE'; END IF;
 RETURN btrim(p_value#>>'{}');
END $$;

CREATE OR REPLACE FUNCTION sokhach._price_date(p_value jsonb) RETURNS date
LANGUAGE plpgsql IMMUTABLE SET search_path=pg_catalog,sokhach,pg_temp AS $$
DECLARE v date;
BEGIN
 IF jsonb_typeof(p_value) IS DISTINCT FROM 'string' OR p_value#>>'{}' !~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$'
 THEN RAISE EXCEPTION 'PRICE_INVALID_PERIOD'; END IF;
 BEGIN v:=(p_value#>>'{}')::date;
 EXCEPTION WHEN invalid_datetime_format OR datetime_field_overflow THEN RAISE EXCEPTION 'PRICE_INVALID_PERIOD'; END;
 IF to_char(v,'YYYY-MM-DD')<>p_value#>>'{}' THEN RAISE EXCEPTION 'PRICE_INVALID_PERIOD'; END IF;
 RETURN v;
END $$;

-- Thay cả bảng giá của sổ trong một lệnh; không đổi giá chuyến nào đã ghi (affected_trips chỉ đếm để mời áp lại).
CREATE OR REPLACE FUNCTION sokhach.save_price_table(customer_id bigint,expected_version bigint,idempotency_key text,
 price_table jsonb) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,sokhach,pg_temp AS $$
DECLARE v_payload jsonb:=jsonb_build_object('command','save_price_table','price_table',price_table);
 v_retry jsonb; v_before jsonb; v_after jsonb; v_item jsonb; v_alias jsonb; v_rate jsonb;
 v_name text; v_key text; v_loc bigint; v_period bigint; v_from date; v_to date; v_amount bigint; v_affected bigint;
BEGIN
 v_retry:=sokhach._begin_command(customer_id,expected_version,idempotency_key,v_payload);
 IF v_retry IS NOT NULL THEN RETURN v_retry; END IF;
 IF jsonb_typeof(price_table) IS DISTINCT FROM 'object'
   OR EXISTS (SELECT 1 FROM jsonb_object_keys(price_table) k WHERE k NOT IN ('tt_shippers','locations','periods'))
   OR jsonb_typeof(price_table->'tt_shippers') IS DISTINCT FROM 'array'
   OR jsonb_typeof(price_table->'locations') IS DISTINCT FROM 'array'
   OR jsonb_typeof(price_table->'periods') IS DISTINCT FROM 'array'
 THEN RAISE EXCEPTION 'INVALID_PRICE_TABLE'; END IF;
 v_before:=sokhach._price_table(customer_id);
 DELETE FROM sokhach.price_rate r WHERE r.customer_id=save_price_table.customer_id;
 DELETE FROM sokhach.price_period p WHERE p.customer_id=save_price_table.customer_id;
 DELETE FROM sokhach.price_location_alias a WHERE a.customer_id=save_price_table.customer_id;
 DELETE FROM sokhach.price_location l WHERE l.customer_id=save_price_table.customer_id;
 DELETE FROM sokhach.price_tt_shipper s WHERE s.customer_id=save_price_table.customer_id;
 FOR v_item IN SELECT x FROM jsonb_array_elements(price_table->'tt_shippers') x LOOP
   v_name:=sokhach._price_text(v_item); v_key:=sokhach._price_key(v_name);
   IF EXISTS (SELECT 1 FROM sokhach.price_tt_shipper s WHERE s.customer_id=save_price_table.customer_id AND s.shipper_key=v_key)
   THEN RAISE EXCEPTION 'PRICE_DUPLICATE_SHIPPER'; END IF;
   INSERT INTO sokhach.price_tt_shipper(customer_id,name,shipper_key) VALUES(customer_id,v_name,v_key);
 END LOOP;
 -- Tên kho và tên khác dùng chung một không gian khóa trong sổ: một cách viết chỉ trỏ một kho.
 FOR v_item IN SELECT x FROM jsonb_array_elements(price_table->'locations') x LOOP
   IF jsonb_typeof(v_item) IS DISTINCT FROM 'object'
     OR EXISTS (SELECT 1 FROM jsonb_object_keys(v_item) k WHERE k NOT IN ('name','aliases'))
     OR jsonb_typeof(coalesce(v_item->'aliases','[]')) IS DISTINCT FROM 'array'
   THEN RAISE EXCEPTION 'INVALID_PRICE_TABLE'; END IF;
   v_name:=sokhach._price_text(v_item->'name'); v_key:=sokhach._price_key(v_name);
   IF EXISTS (SELECT 1 FROM sokhach.price_location l WHERE l.customer_id=save_price_table.customer_id AND l.name_key=v_key)
     OR EXISTS (SELECT 1 FROM sokhach.price_location_alias a WHERE a.customer_id=save_price_table.customer_id AND a.alias_key=v_key)
   THEN RAISE EXCEPTION 'PRICE_DUPLICATE_ALIAS'; END IF;
   INSERT INTO sokhach.price_location(customer_id,name,name_key) VALUES(customer_id,v_name,v_key) RETURNING id INTO v_loc;
   FOR v_alias IN SELECT x FROM jsonb_array_elements(coalesce(v_item->'aliases','[]')) x LOOP
     v_name:=sokhach._price_text(v_alias); v_key:=sokhach._price_key(v_name);
     IF EXISTS (SELECT 1 FROM sokhach.price_location l WHERE l.customer_id=save_price_table.customer_id AND l.name_key=v_key)
       OR EXISTS (SELECT 1 FROM sokhach.price_location_alias a WHERE a.customer_id=save_price_table.customer_id AND a.alias_key=v_key)
     THEN RAISE EXCEPTION 'PRICE_DUPLICATE_ALIAS'; END IF;
     INSERT INTO sokhach.price_location_alias(customer_id,location_id,alias,alias_key) VALUES(customer_id,v_loc,v_name,v_key);
   END LOOP;
 END LOOP;
 FOR v_item IN SELECT x FROM jsonb_array_elements(price_table->'periods') x LOOP
   IF jsonb_typeof(v_item) IS DISTINCT FROM 'object'
     OR EXISTS (SELECT 1 FROM jsonb_object_keys(v_item) k WHERE k NOT IN ('valid_from','valid_to','rates'))
     OR jsonb_typeof(v_item->'rates') IS DISTINCT FROM 'array'
   THEN RAISE EXCEPTION 'INVALID_PRICE_TABLE'; END IF;
   v_from:=sokhach._price_date(v_item->'valid_from');
   v_to:=CASE WHEN jsonb_typeof(coalesce(v_item->'valid_to','null'))='null' THEN NULL ELSE sokhach._price_date(v_item->'valid_to') END;
   IF v_to<v_from THEN RAISE EXCEPTION 'PRICE_INVALID_PERIOD'; END IF;
   INSERT INTO sokhach.price_period(customer_id,valid_from,valid_to) VALUES(customer_id,v_from,v_to) RETURNING id INTO v_period;
   FOR v_rate IN SELECT x FROM jsonb_array_elements(v_item->'rates') x LOOP
     IF jsonb_typeof(v_rate) IS DISTINCT FROM 'object'
       OR (SELECT count(*) FROM jsonb_object_keys(v_rate) k WHERE k IN ('location','tier','unit_price_vnd'))<>3
       OR (SELECT count(*) FROM jsonb_object_keys(v_rate))<>3
       OR v_rate->>'tier' IS NULL OR v_rate->>'tier' NOT IN ('khach','tt')
     THEN RAISE EXCEPTION 'INVALID_PRICE_TABLE'; END IF;
     IF jsonb_typeof(v_rate->'unit_price_vnd') IS DISTINCT FROM 'string' OR v_rate->>'unit_price_vnd' !~ '^(0|[1-9][0-9]{0,18})$'
     THEN RAISE EXCEPTION 'PRICE_INVALID_AMOUNT'; END IF;
     v_amount:=(v_rate->>'unit_price_vnd')::bigint;
     SELECT l.id INTO v_loc FROM sokhach.price_location l WHERE l.customer_id=save_price_table.customer_id
       AND l.name_key=sokhach._price_key(sokhach._price_text(v_rate->'location'));
     IF NOT FOUND THEN RAISE EXCEPTION 'PRICE_UNKNOWN_LOCATION'; END IF;
     IF EXISTS (SELECT 1 FROM sokhach.price_rate r WHERE r.period_id=v_period AND r.location_id=v_loc AND r.tier=v_rate->>'tier')
     THEN RAISE EXCEPTION 'PRICE_DUPLICATE_RATE'; END IF;
     INSERT INTO sokhach.price_rate(period_id,location_id,customer_id,tier,unit_price_vnd)
     VALUES(v_period,v_loc,customer_id,v_rate->>'tier',v_amount);
   END LOOP;
 END LOOP;
 -- Hai đợt có cùng kho và cùng nhóm giá không được chồng ngày (hai đầu đều tính).
 IF EXISTS (SELECT 1 FROM sokhach.price_rate r1 JOIN sokhach.price_period p1 ON p1.id=r1.period_id
     JOIN sokhach.price_rate r2 ON r2.location_id=r1.location_id AND r2.tier=r1.tier AND r2.period_id>r1.period_id
     JOIN sokhach.price_period p2 ON p2.id=r2.period_id
     WHERE r1.customer_id=save_price_table.customer_id
       AND daterange(p1.valid_from,p1.valid_to,'[]') && daterange(p2.valid_from,p2.valid_to,'[]'))
 THEN RAISE EXCEPTION 'PRICE_PERIOD_OVERLAP'; END IF;
 v_after:=sokhach._price_table(customer_id);
 IF v_after=v_before THEN RAISE EXCEPTION 'NO_CHANGE'; END IF;
 INSERT INTO sokhach.event(customer_id,kind,actor,"before","after",idempotency_key)
 VALUES(customer_id,'price_table_edit',sokhach._actor(),jsonb_build_object('price_table',v_before),
   jsonb_build_object('price_table',v_after),idempotency_key);
 SELECT count(*) INTO v_affected FROM sokhach._price_trip_rows(save_price_table.customer_id) x
   WHERE x.from_table AND x.unit_price_vnd::text IS DISTINCT FROM x.lookup->>'unit_price_vnd';
 RETURN sokhach._finish_command(customer_id,idempotency_key,v_payload,
   jsonb_build_object('price_table',v_after,'affected_trips',v_affected));
EXCEPTION WHEN numeric_value_out_of_range THEN RAISE EXCEPTION 'PRICE_INVALID_AMOUNT';
END $$;

-- Ghi đơn giá theo bảng cho các chuyến chọn: server tra lại, một event, phân bổ lại một lần; giữ nguyên phụ phí.
CREATE OR REPLACE FUNCTION sokhach.apply_price_table(customer_id bigint,expected_version bigint,idempotency_key text,
 trip_ids jsonb) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,sokhach,pg_temp AS $$
DECLARE v_payload jsonb:=jsonb_build_object('command','apply_price_table','trip_ids',trip_ids);
 v_retry jsonb; v_id bigint; t sokhach.v_trip_current%ROWTYPE; v_old sokhach.trip_price_rev%ROWTYPE;
 v_lookup jsonb; v_before jsonb:='[]'; v_after jsonb:='[]'; v_item jsonb; v_event bigint; v_rev bigint; v_changes jsonb;
BEGIN
 v_retry:=sokhach._begin_command(customer_id,expected_version,idempotency_key,v_payload);
 IF v_retry IS NOT NULL THEN RETURN v_retry; END IF;
 PERFORM sokhach._baseline(customer_id);
 IF jsonb_typeof(trip_ids) IS DISTINCT FROM 'array' OR jsonb_array_length(trip_ids) NOT BETWEEN 1 AND 500
   OR EXISTS (SELECT 1 FROM jsonb_array_elements(trip_ids) x WHERE jsonb_typeof(x)<>'number' OR x::text !~ '^[1-9][0-9]{0,18}$')
   OR (SELECT count(*)<>count(DISTINCT x::text) FROM jsonb_array_elements(trip_ids) x)
 THEN RAISE EXCEPTION 'INVALID_TRIPS'; END IF;
 FOR v_id IN SELECT x::text::bigint FROM jsonb_array_elements(trip_ids) x ORDER BY 1 LOOP
   SELECT * INTO t FROM sokhach.v_trip_current v WHERE v.id=v_id AND v.customer_id=apply_price_table.customer_id AND NOT v.deleted;
   IF NOT FOUND OR coalesce(t.container,'')='' THEN RAISE EXCEPTION 'TRIP_NOT_FOUND'; END IF;
   IF t.status<>'confirmed' THEN RAISE EXCEPTION 'TRIP_PENDING_REVIEW'; END IF;
   PERFORM sokhach._month_open(customer_id,t.debt_month,clock_timestamp());
   v_lookup:=sokhach._lookup_price(customer_id,t.event_date,t.origin,t.shipper);
   IF NOT v_lookup ? 'unit_price_vnd' THEN RAISE EXCEPTION 'PRICE_NOT_FOUND'; END IF;
   SELECT * INTO v_old FROM sokhach.trip_price_rev r WHERE r.trip_id=v_id ORDER BY r.id DESC LIMIT 1;
   IF v_old.unit_price_vnd::text IS NOT DISTINCT FROM v_lookup->>'unit_price_vnd' THEN RAISE EXCEPTION 'NO_CHANGE'; END IF;
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

REVOKE ALL ON ALL FUNCTIONS IN SCHEMA sokhach FROM PUBLIC, sokhach_app, sokhach_reader;
GRANT EXECUTE ON FUNCTION sokhach.edit_trip_info(bigint,bigint,text,bigint,text,text) TO sokhach_app;
GRANT EXECUTE ON FUNCTION sokhach.delete_trip(bigint,bigint,text,bigint) TO sokhach_app;
GRANT EXECUTE ON FUNCTION sokhach.edit_legacy_trip(bigint,bigint,text,bigint,text,text) TO sokhach_app;
GRANT EXECUTE ON FUNCTION sokhach.delete_legacy_trip(bigint,bigint,text,bigint) TO sokhach_app;
GRANT EXECUTE ON FUNCTION sokhach.paste_trips(bigint,bigint,text,date,jsonb) TO sokhach_app;
GRANT EXECUTE ON FUNCTION sokhach.edit_trip_price(bigint,bigint,text,bigint,bigint,bigint) TO sokhach_app;
GRANT EXECUTE ON FUNCTION sokhach.adjust_trip(bigint,bigint,text,bigint,bigint,text,text,bigint) TO sokhach_app;
GRANT EXECUTE ON FUNCTION sokhach.adjust_month(bigint,bigint,text,date,bigint,text) TO sokhach_app;
GRANT EXECUTE ON FUNCTION sokhach.delete_month_adjustment(bigint,bigint,text,bigint) TO sokhach_app;
GRANT EXECUTE ON FUNCTION sokhach.record_receipt(bigint,bigint,text,date,text,bigint,text) TO sokhach_app;
GRANT EXECUTE ON FUNCTION sokhach.edit_receipt_meta(bigint,bigint,text,text,date,text,text) TO sokhach_app;
GRANT EXECUTE ON FUNCTION sokhach.void_receipt(bigint,bigint,text,text,text) TO sokhach_app;
GRANT EXECUTE ON FUNCTION sokhach.set_month_lock(bigint,bigint,text,date,boolean) TO sokhach_app;
GRANT EXECUTE ON FUNCTION sokhach.review_trip(bigint,bigint,text,bigint,text,text) TO sokhach_app;
GRANT EXECUTE ON FUNCTION sokhach.record_offset(bigint,bigint,bigint,bigint,text,date,bigint,text) TO sokhach_app;
GRANT EXECUTE ON FUNCTION sokhach.void_offset(bigint,bigint,bigint,text,bigint,text) TO sokhach_app;
GRANT EXECUTE ON FUNCTION sokhach.edit_offset_date(bigint,bigint,bigint,text,bigint,date) TO sokhach_app;
GRANT EXECUTE ON FUNCTION sokhach.get_ledger(bigint) TO sokhach_app, sokhach_reader;
GRANT EXECUTE ON FUNCTION sokhach.list_offset_sources(bigint) TO sokhach_app, sokhach_reader;
GRANT EXECUTE ON FUNCTION sokhach.list_customers() TO sokhach_app, sokhach_reader;
GRANT EXECUTE ON FUNCTION sokhach.get_dashboard() TO sokhach_app, sokhach_reader;
GRANT EXECUTE ON FUNCTION sokhach.get_receivables_matrix(int) TO sokhach_app, sokhach_reader;
GRANT EXECUTE ON FUNCTION sokhach.get_receivables_detail(bigint,date) TO sokhach_app, sokhach_reader;
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
GRANT EXECUTE ON FUNCTION sokhach.attach_receipt_image(bigint,bigint,text,text,text,bytea) TO sokhach_app;
GRANT EXECUTE ON FUNCTION sokhach.remove_receipt_image(bigint,bigint,text,bigint,text) TO sokhach_app;
GRANT EXECUTE ON FUNCTION sokhach.list_receipt_images(bigint) TO sokhach_app,sokhach_reader;
GRANT EXECUTE ON FUNCTION sokhach.get_receipt_image(bigint,bigint) TO sokhach_app,sokhach_reader;
GRANT EXECUTE ON FUNCTION sokhach.find_receipt_image(text) TO sokhach_app,sokhach_reader;
GRANT EXECUTE ON FUNCTION sokhach.save_price_table(bigint,bigint,text,jsonb) TO sokhach_app;
GRANT EXECUTE ON FUNCTION sokhach.apply_price_table(bigint,bigint,text,jsonb) TO sokhach_app;
GRANT EXECUTE ON FUNCTION sokhach.get_price_table(bigint) TO sokhach_app,sokhach_reader;
GRANT EXECUTE ON FUNCTION sokhach.get_price_status(bigint) TO sokhach_app,sokhach_reader;
RESET ROLE;
-- Access for trial remains scoped to app server; actor comes from server session.

-- Câu hỏi mở:
-- 1. source_charge_vnd/source_receipt_vnd và mỏ neo do client nhập;
--    DB kiểm FIFO nhưng hash/ref chưa chứng minh tổng được tính từ mọi dòng
--    nguồn đóng băng. ĐỀ XUẤT bảng source_movement(customer,month,kind,amount,
--    source_ref,source_hash) và đối chiếu tổng độc lập trước khi dùng nguồn thật.
-- 2. import_cutover không nhận số dòng cách ly/bỏ qua hay tập khách nguồn;
--    source_rows hiện chỉ đếm các phần tử gửi vào, không chứng minh đủ 100%
--    nguồn. Cần chứng cứ số dòng/tập khách trước khi dùng nguồn thật.
-- 3. Tháng âm, hoàn tiền/chuyển sổ còn mở; không suy từ cờ ngoại lệ.
-- 4. Nếu không dùng namespace idempotency theo khách nhỏ nhất, cần bảng
--    cutover_command(cutover_id, key, request_hash, result, signoff evidence).
