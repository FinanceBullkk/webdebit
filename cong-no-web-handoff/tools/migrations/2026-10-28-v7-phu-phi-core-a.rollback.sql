-- Run only before any post-migration command; all checks run in one transaction.
BEGIN;
SET LOCAL ROLE sokhach_owner;
SET LOCAL sokhach.actor='fee-migration-rollback';
CREATE TEMP TABLE fee_rollback_month ON COMMIT DROP AS
 SELECT customer_id,debt_month,outstanding_vnd FROM sokhach.v_outstanding_month;
CREATE TEMP TABLE fee_rollback_ledger ON COMMIT DROP AS
 SELECT c.id customer_id,sokhach.get_ledger(c.id)->>'total_outstanding_vnd' total_vnd,
   sokhach.get_ledger(c.id)->'months' months FROM sokhach.customer c;
CREATE TEMP TABLE fee_rollback_target ON COMMIT DROP AS
 SELECT t.id trip_id,p.id latest_rev,prior.id prior_rev,
   p.unit_price_vnd,p.other_fee_vnd,
   (SELECT count(*) FROM sokhach.trip_fee_line l WHERE l.trip_id=t.id) line_count,
   (SELECT sum(l.amount_vnd) FROM sokhach.trip_fee_line l WHERE l.trip_id=t.id) line_total
 FROM sokhach.trip t
 JOIN LATERAL(SELECT * FROM sokhach.trip_price_rev p WHERE p.trip_id=t.id ORDER BY p.id DESC LIMIT 1)p ON true
 LEFT JOIN LATERAL(SELECT * FROM sokhach.trip_price_rev q WHERE q.trip_id=t.id AND q.id<p.id ORDER BY q.id DESC LIMIT 1)prior ON true
 WHERE EXISTS(SELECT 1 FROM sokhach.trip_fee_line l WHERE l.trip_id=t.id)
    OR EXISTS(SELECT 1 FROM sokhach.adjustment a WHERE a.trip_id=t.id AND a.fee_absorbed)
    OR (p.other_fee_vnd IS NULL AND prior.other_fee_vnd=0
        AND p.created_by_event=prior.created_by_event
        AND p.unit_price_vnd IS NOT DISTINCT FROM prior.unit_price_vnd);
DO $$ BEGIN
 IF EXISTS(SELECT 1 FROM sokhach.trip_fee_line l WHERE l.note NOT IN ('migration: initial fee','migration: legacy fee')
     OR l.note IS NULL OR l.voided_by_event IS NOT NULL)
 THEN RAISE EXCEPTION 'ROLLBACK_CLASSIFIED_LINES'; END IF;
 IF EXISTS(SELECT 1 FROM fee_rollback_target q JOIN sokhach.trip_price_rev p ON p.id=q.latest_rev
     JOIN sokhach.trip_price_rev prior ON prior.id=q.prior_rev
     WHERE p.created_by_event<>prior.created_by_event
        OR p.unit_price_vnd IS DISTINCT FROM prior.unit_price_vnd
        OR p.other_fee_vnd IS DISTINCT FROM q.line_total)
    OR EXISTS(SELECT 1 FROM fee_rollback_target WHERE prior_rev IS NULL)
 THEN RAISE EXCEPTION 'ROLLBACK_PRICE_CHANGED'; END IF;
END $$;
DROP TRIGGER trip_fee_cache_check ON sokhach.trip_fee_line;
DROP TRIGGER trip_price_cache_check ON sokhach.trip_price_rev;
DROP TRIGGER fee_line_guard ON sokhach.trip_fee_line;
ALTER TABLE sokhach.trip_price_rev DISABLE TRIGGER trip_price_rev_immutable;
ALTER TABLE sokhach.adjustment DISABLE TRIGGER adjustment_immutable;
DELETE FROM sokhach.trip_price_rev p USING fee_rollback_target q WHERE p.id=q.latest_rev;
UPDATE sokhach.adjustment SET fee_absorbed=false WHERE fee_absorbed;
ALTER TABLE sokhach.trip_price_rev ENABLE TRIGGER trip_price_rev_immutable;
ALTER TABLE sokhach.adjustment ENABLE TRIGGER adjustment_immutable;
DROP FUNCTION sokhach._compat_trip_fee(bigint,bigint,bigint,bigint);
DROP FUNCTION sokhach._sync_trip_fee(bigint,bigint);
DROP FUNCTION sokhach._guard_fee_line();
DROP FUNCTION sokhach._fee_cache_check();
DROP FUNCTION sokhach.v7_fee_migration_dry_run();
DROP TABLE sokhach.trip_fee_line,sokhach.book_fee_column,sokhach.fee_type_audit,sokhach.fee_type;
-- Original definitions from 7f2dcb9.
CREATE OR REPLACE VIEW sokhach.v_adjustment_current AS
SELECT a.id,a.customer_id,coalesce(t.debt_month,a.debt_month) AS debt_month,
       a.trip_id,a.legacy_row_id,a.amount_vnd,a.field,a.new_value_vnd,a.note,a.actor,a.at,a.created_by_event
FROM sokhach.adjustment a LEFT JOIN sokhach.v_trip_current t ON t.id=a.trip_id
WHERE a.trip_id IS NULL OR (NOT t.deleted AND t.status='confirmed');
CREATE OR REPLACE FUNCTION sokhach.paste_trips(customer_id bigint, expected_version bigint,
    idempotency_key text, debt_month date, trips jsonb) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, sokhach, pg_temp AS $$
DECLARE v_payload jsonb := jsonb_build_object('command','paste_trips','month',debt_month,'trips',trips);
        v_retry jsonb; v_actor text; v_ids jsonb := '[]'::jsonb;
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
    IF debt_month IS NULL OR extract(day FROM debt_month)<>1 THEN RAISE EXCEPTION 'INVALID_COMMAND'; END IF;
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
        INSERT INTO sokhach.trip_price_rev(trip_id,customer_id,unit_price_vnd,other_fee_vnd,created_by_event)
        VALUES ((v_item->>'trip_id')::bigint,customer_id,
            (v_item->>'unitPriceVnd')::bigint,(v_item->>'otherFeeVnd')::bigint,v_event);
    END LOOP;
    v_changes := sokhach.reallocate(customer_id,idempotency_key);
    RETURN sokhach._finish_command(customer_id,idempotency_key,v_payload,
        jsonb_build_object('trip_ids',v_ids,'reallocated',v_changes,'pending_review',v_pending));
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
    IF v_trip.status<>'confirmed' THEN RAISE EXCEPTION 'TRIP_PENDING_REVIEW'; END IF;
    IF NOT FOUND THEN RAISE EXCEPTION 'TRIP_NOT_FOUND'; END IF;
    PERFORM sokhach._month_open(customer_id,v_trip.debt_month,v_now);
    IF unit_price_vnd < 0 OR other_fee_vnd < 0 OR
       coalesce(unit_price_vnd,0)::numeric+coalesce(other_fee_vnd,0)::numeric>9223372036854775807
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
        jsonb_build_object('price',jsonb_build_object('trip_id',trip_id,'revision_id',v_rev,
            'unit_price_vnd',unit_price_vnd,'other_fee_vnd',other_fee_vnd)),idempotency_key)
    RETURNING id INTO v_event;
    INSERT INTO sokhach.trip_price_rev(id,trip_id,customer_id,unit_price_vnd,other_fee_vnd,created_by_event)
    OVERRIDING SYSTEM VALUE VALUES (v_rev,trip_id,customer_id,unit_price_vnd,other_fee_vnd,v_event);
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
        IF field IS NULL OR field NOT IN ('unit_price_vnd','other_fee_vnd')
           OR new_value_vnd IS NULL OR new_value_vnd<0 OR new_amount_vnd IS NOT NULL
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
    IF new_amount_vnd IS NULL OR new_amount_vnd < 0 THEN RAISE EXCEPTION 'INVALID_VND'; END IF;
    v_delta := new_amount_vnd-v_old;
    IF v_delta=0 THEN RAISE EXCEPTION 'NO_CHANGE'; END IF;
    v_id := nextval(pg_get_serial_sequence('sokhach.adjustment','id'));
    INSERT INTO sokhach.event(customer_id,kind,actor,"before","after",idempotency_key)
    VALUES (customer_id,'adjust_trip',sokhach._actor(),
        jsonb_build_object('trip',trip_id,'amount_vnd',v_old::text,'field',field,'new_value_vnd',v_field_old::text),
        jsonb_build_object('adjustment',v_id,'trip_id',trip_id,'old_amount_vnd',v_old::text,
            'new_amount_vnd',new_amount_vnd::text,'delta_vnd',v_delta::text,'note',note,
            'field',field,'new_value_vnd',new_value_vnd::text),idempotency_key)
    RETURNING id INTO v_event;
    INSERT INTO sokhach.adjustment(id,customer_id,debt_month,trip_id,amount_vnd,note,actor,created_by_event,field,new_value_vnd)
    OVERRIDING SYSTEM VALUE VALUES (v_id,customer_id,v_trip.origin_month,trip_id,v_delta,note,
        sokhach._actor(),v_event,field,new_value_vnd);
    v_changes := sokhach.reallocate(customer_id,idempotency_key);
    RETURN sokhach._finish_command(customer_id,idempotency_key,v_payload,
        jsonb_build_object('adjustment_id',v_id,'delta_vnd',v_delta::text,'reallocated',v_changes));
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
ALTER TABLE sokhach.adjustment DROP COLUMN fee_absorbed;
ALTER TABLE sokhach.trip_price_rev ADD CONSTRAINT trip_price_rev_other_fee_vnd_check CHECK (other_fee_vnd>=0);
ALTER TABLE sokhach.legacy_trip_rev ADD CONSTRAINT legacy_trip_rev_other_fee_vnd_check CHECK (other_fee_vnd>=0);
DO $$ BEGIN
 IF EXISTS(SELECT * FROM fee_rollback_month b FULL JOIN sokhach.v_outstanding_month a USING(customer_id,debt_month)
   WHERE b.outstanding_vnd IS DISTINCT FROM a.outstanding_vnd)
 OR EXISTS(SELECT * FROM fee_rollback_ledger b JOIN sokhach.customer c ON c.id=b.customer_id
   WHERE b.total_vnd IS DISTINCT FROM sokhach.get_ledger(c.id)->>'total_outstanding_vnd'
      OR b.months IS DISTINCT FROM sokhach.get_ledger(c.id)->'months')
 THEN RAISE EXCEPTION 'FEE_ROLLBACK_TOTAL_MISMATCH'; END IF;
END $$;
COMMIT;
