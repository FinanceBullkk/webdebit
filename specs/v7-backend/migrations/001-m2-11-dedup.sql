-- Part B. psql -X -v ON_ERROR_STOP=1 -f this-file. Backup/restore gate required.
\set ON_ERROR_STOP on
BEGIN;
SET LOCAL lock_timeout = '10s';
SET LOCAL statement_timeout = '120s';
SET LOCAL ROLE sokhach_owner;
LOCK TABLE sokhach.customer IN ACCESS EXCLUSIVE MODE;
CREATE TEMP TABLE m211_before ON COMMIT DROP AS
 SELECT customer_id, sum(outstanding_vnd)::numeric AS total
 FROM sokhach.v_outstanding_month GROUP BY customer_id;
ALTER TABLE sokhach.trip ADD COLUMN IF NOT EXISTS booking text;
ALTER TABLE sokhach.trip ADD COLUMN IF NOT EXISTS status text NOT NULL DEFAULT 'confirmed'
 CHECK (status IN ('confirmed','pending_review'));
CREATE TABLE IF NOT EXISTS sokhach.baseline_trip_ref (
 cutover_id bigint NOT NULL REFERENCES sokhach.cutover(id),
 booking_norm text NOT NULL, container_norm text NOT NULL, event_date date
);
CREATE INDEX IF NOT EXISTS baseline_trip_ref_code ON sokhach.baseline_trip_ref(cutover_id,booking_norm,container_norm);
CREATE INDEX IF NOT EXISTS baseline_trip_ref_date ON sokhach.baseline_trip_ref(cutover_id,container_norm,event_date);
DO $$ BEGIN
 IF NOT EXISTS (SELECT FROM pg_trigger WHERE tgrelid='sokhach.baseline_trip_ref'::regclass
                AND tgname='baseline_trip_ref_immutable') THEN
  CREATE TRIGGER baseline_trip_ref_immutable BEFORE UPDATE OR DELETE ON sokhach.baseline_trip_ref
   FOR EACH ROW EXECUTE FUNCTION sokhach.reject_immutable_change();
 END IF;
END $$;
-- Generated from authoritative functions; tested for exact definition parity.
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
    FROM sokhach.trip t JOIN active_customer ac ON ac.customer_id=t.customer_id
    LEFT JOIN LATERAL (SELECT unit_price_vnd,other_fee_vnd FROM sokhach.trip_price_rev
        WHERE trip_id=t.id ORDER BY id DESC LIMIT 1) p ON true
    WHERE t.status='confirmed'
), movements AS (
    SELECT o.customer_id,o.debt_month,o.amount_vnd FROM sokhach.opening_balance o
    JOIN active_customer ac ON (ac.customer_id,ac.cutover_id)=(o.customer_id,o.cutover_id)
    UNION ALL SELECT customer_id,debt_month,amount_vnd FROM latest_price WHERE amount_vnd IS NOT NULL
    UNION ALL SELECT a.customer_id,a.debt_month,a.amount_vnd FROM sokhach.adjustment a
        JOIN active_customer ac ON ac.customer_id=a.customer_id
    UNION ALL SELECT o.customer_id,o.debt_month,o.amount_vnd FROM sokhach.v_offset_outgoing o
        JOIN active_customer ac ON ac.customer_id=o.customer_id
    UNION ALL SELECT l.customer_id,l.debt_month,-l.amount_vnd FROM sokhach.v_receipt_line_active l
        JOIN active_customer ac ON ac.customer_id=l.customer_id
)
SELECT customer_id,debt_month,sum(amount_vnd)::bigint AS outstanding_vnd
FROM movements GROUP BY customer_id,debt_month;


CREATE OR REPLACE FUNCTION sokhach._normalize_key(p_value text) RETURNS text
LANGUAGE sql IMMUTABLE SET search_path = pg_catalog, sokhach, pg_temp AS $$
    SELECT upper(regexp_replace(coalesce(p_value,''),
        U&'[\0009-\000D\0020\0085\00A0\1680\2000-\200A\2028\2029\202F\205F\3000]', '', 'g'))
$$;

CREATE OR REPLACE FUNCTION sokhach._booking_key(p_booking text,p_container text,p_date date) RETURNS text
LANGUAGE sql IMMUTABLE SET search_path = pg_catalog, sokhach, pg_temp AS $$
    SELECT CASE WHEN sokhach._normalize_key(p_booking) ~ '[[:alnum:]]'
        THEN sokhach._normalize_key(p_booking)
        ELSE 'ALT:' || sokhach._normalize_key(p_container) || ':' || coalesce(to_char(p_date,'YYYYMMDD'),'UNKNOWN') END
$$;

CREATE OR REPLACE FUNCTION sokhach.paste_trips(customer_id bigint, expected_version bigint,
    idempotency_key text, debt_month date, trips jsonb) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, sokhach, pg_temp AS $$
DECLARE v_payload jsonb := jsonb_build_object('command','paste_trips','month',debt_month,'trips',trips);
        v_retry jsonb; v_actor text; v_now timestamptz; v_ids jsonb := '[]'::jsonb;
        v_item jsonb; v_id bigint; v_event bigint; v_rows jsonb := '[]'::jsonb;
        v_changes jsonb; v_date date; v_unit bigint; v_fee bigint; v_date_text text;
        v_fee_only boolean; v_cutover bigint; v_booking text; v_container text;
        v_code text; v_seen text[] := '{}'; v_reason text; v_pending jsonb := '[]';
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
            v_code := v_booking || '|' || v_container;
            IF EXISTS (SELECT 1 FROM sokhach.baseline_trip_ref r WHERE r.cutover_id=v_cutover
                AND r.booking_norm=v_booking AND r.container_norm=v_container)
            THEN v_reason := 'BASELINE_CODE_MATCH';
            ELSIF EXISTS (SELECT 1 FROM sokhach.baseline_trip_ref r WHERE r.cutover_id=v_cutover
                AND r.container_norm=v_container AND abs(r.event_date-v_date)<=3)
            THEN v_reason := 'BASELINE_DATE_WINDOW';
            ELSIF EXISTS (SELECT 1 FROM sokhach.trip t WHERE t.customer_id=paste_trips.customer_id
                AND sokhach._normalize_key(t.container)=v_container
                AND sokhach._booking_key(t.booking,t.container,t.event_date)=v_booking)
            THEN v_reason := 'WEB_DUPLICATE';
            ELSIF v_code=ANY(v_seen) THEN v_reason := 'BATCH_DUPLICATE'; END IF;
            v_seen := array_append(v_seen,v_code);
        END IF;
        v_id := nextval(pg_get_serial_sequence('sokhach.trip','id'));
        IF v_reason IS NOT NULL THEN
            v_pending := v_pending || jsonb_build_array(jsonb_build_object('trip_id',v_id,'reason',v_reason));
        END IF;
        v_ids := v_ids || jsonb_build_array(v_id);
        v_rows := v_rows || jsonb_build_array(v_item || jsonb_build_object(
            'trip_id',v_id,'debt_month',debt_month,'event_date',v_date,
            'status',CASE WHEN v_reason IS NULL THEN 'confirmed' ELSE 'pending_review' END));
    END LOOP;
    v_actor := sokhach._actor();
    INSERT INTO sokhach.event(customer_id,kind,actor,"before","after",idempotency_key)
    VALUES (customer_id,'paste',v_actor,'{}',jsonb_build_object('trips',v_rows),idempotency_key)
    RETURNING id INTO v_event;
    FOR v_item IN SELECT value FROM jsonb_array_elements(v_rows) LOOP
        INSERT INTO sokhach.trip(id,customer_id,debt_month,event_date,container,carrier,
            origin,destination,note,source_ref,created_by_event,booking,status) OVERRIDING SYSTEM VALUE
        VALUES ((v_item->>'trip_id')::bigint,customer_id,debt_month,(v_item->>'event_date')::date,
            v_item->>'container',v_item->>'carrier',v_item->>'from',v_item->>'to',
            v_item->>'note',v_item->>'src',v_event,v_item->>'booking',v_item->>'status');
        INSERT INTO sokhach.trip_price_rev(trip_id,customer_id,unit_price_vnd,other_fee_vnd,created_by_event)
        VALUES ((v_item->>'trip_id')::bigint,customer_id,
            (v_item->>'unitPriceVnd')::bigint,(v_item->>'otherFeeVnd')::bigint,v_event);
    END LOOP;
    v_changes := sokhach.reallocate(customer_id,idempotency_key);
    RETURN sokhach._finish_command(customer_id,idempotency_key,v_payload,
        jsonb_build_object('trip_ids',v_ids,'reallocated',v_changes,'pending_review',v_pending));
END $$;

CREATE OR REPLACE FUNCTION sokhach.edit_trip_price(customer_id bigint, expected_version bigint,
    idempotency_key text, trip_id bigint, unit_price_vnd bigint, other_fee_vnd bigint)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, sokhach, pg_temp AS $$
DECLARE v_payload jsonb := jsonb_build_object('command','edit_trip_price','trip_id',trip_id,
        'unit_price_vnd',unit_price_vnd,'other_fee_vnd',other_fee_vnd);
        v_retry jsonb; v_trip sokhach.trip%ROWTYPE; v_old sokhach.trip_price_rev%ROWTYPE;
        v_now timestamptz; v_event bigint; v_rev bigint; v_changes jsonb;
BEGIN
    v_retry := sokhach._begin_command(customer_id,expected_version,idempotency_key,v_payload);
    IF v_retry IS NOT NULL THEN RETURN v_retry; END IF;
    PERFORM sokhach._baseline(customer_id);
    v_now := clock_timestamp();
    SELECT * INTO v_trip FROM sokhach.trip WHERE id=trip_id AND trip.customer_id=edit_trip_price.customer_id;
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
        v_retry jsonb; v_trip sokhach.trip%ROWTYPE; v_base bigint; v_old bigint;
        v_delta bigint; v_id bigint; v_event bigint; v_changes jsonb;
        v_price sokhach.trip_price_rev%ROWTYPE; v_fee bigint; v_field_old bigint;
BEGIN
    v_retry := sokhach._begin_command(customer_id,expected_version,idempotency_key,v_payload);
    IF v_retry IS NOT NULL THEN RETURN v_retry; END IF;
    PERFORM sokhach._baseline(customer_id);
    SELECT * INTO v_trip FROM sokhach.trip WHERE id=trip_id AND trip.customer_id=adjust_trip.customer_id;
    IF v_trip.status<>'confirmed' THEN RAISE EXCEPTION 'TRIP_PENDING_REVIEW'; END IF;
    IF NOT FOUND THEN RAISE EXCEPTION 'TRIP_NOT_FOUND'; END IF;
    SELECT * INTO v_price FROM sokhach.trip_price_rev p
    WHERE p.trip_id=adjust_trip.trip_id ORDER BY p.id DESC LIMIT 1;
    v_base := CASE WHEN v_price.unit_price_vnd IS NOT NULL
        THEN v_price.unit_price_vnd+coalesce(v_price.other_fee_vnd,0)
        WHEN v_trip.container IS NULL OR v_trip.container='' THEN v_price.other_fee_vnd END;
    IF v_base IS NULL THEN RAISE EXCEPTION 'TRIP_HAS_NO_PRICE'; END IF;
    SELECT v_base+coalesce(sum(amount_vnd),0)::bigint INTO v_old
    FROM sokhach.adjustment WHERE adjustment.customer_id=adjust_trip.customer_id
      AND adjustment.trip_id=adjust_trip.trip_id;
    IF field IS NOT NULL OR new_value_vnd IS NOT NULL THEN
        IF field IS NULL OR field NOT IN ('unit_price_vnd','other_fee_vnd')
           OR new_value_vnd IS NULL OR new_value_vnd<0 OR new_amount_vnd IS NOT NULL
        THEN RAISE EXCEPTION 'INVALID_ADJUSTMENT'; END IF;
        -- Current field values come from adjustments; original price cells stay intact.
        SELECT a.new_value_vnd INTO v_fee
        FROM sokhach.adjustment a WHERE a.customer_id=adjust_trip.customer_id
          AND a.trip_id=adjust_trip.trip_id
          AND a.field='other_fee_vnd' AND a.created_by_event>v_price.created_by_event
        ORDER BY a.created_by_event DESC LIMIT 1;
        v_fee := coalesce(v_fee,v_price.other_fee_vnd,0);
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
    OVERRIDING SYSTEM VALUE VALUES (v_id,customer_id,v_trip.debt_month,trip_id,v_delta,note,
        sokhach._actor(),v_event,field,new_value_vnd);
    v_changes := sokhach.reallocate(customer_id,idempotency_key);
    RETURN sokhach._finish_command(customer_id,idempotency_key,v_payload,
        jsonb_build_object('adjustment_id',v_id,'delta_vnd',v_delta::text,'reallocated',v_changes));
EXCEPTION WHEN numeric_value_out_of_range THEN RAISE EXCEPTION 'INVALID_VND';
    END $$;

CREATE OR REPLACE FUNCTION sokhach.adjust_month(customer_id bigint, expected_version bigint,
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
       AND NOT EXISTS (SELECT 1 FROM sokhach.trip t
           WHERE t.customer_id=adjust_month.customer_id AND t.debt_month=adjust_month.debt_month AND t.status='confirmed')
       AND NOT EXISTS (SELECT 1 FROM sokhach.adjustment a
           WHERE a.customer_id=adjust_month.customer_id AND a.debt_month=adjust_month.debt_month)
    THEN RAISE EXCEPTION 'MONTH_NOT_FOUND'; END IF;
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

CREATE OR REPLACE FUNCTION sokhach._check_allocations(p_customer bigint) RETURNS void
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
          AND l.debt_month <> (SELECT max(debt_month) FROM (
              SELECT debt_month FROM sokhach.opening_balance WHERE customer_id = p_customer
              UNION ALL SELECT debt_month FROM sokhach.trip WHERE customer_id = p_customer AND status='confirmed'
              UNION ALL SELECT debt_month FROM sokhach.adjustment WHERE customer_id = p_customer
              UNION ALL SELECT debt_month FROM sokhach.v_offset_outgoing WHERE customer_id = p_customer
          ) m)
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

CREATE OR REPLACE FUNCTION sokhach.reallocate(p_customer bigint, p_key text) RETURNS jsonb
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
            FROM sokhach.trip t LEFT JOIN LATERAL (
                SELECT unit_price_vnd,other_fee_vnd FROM sokhach.trip_price_rev
                WHERE trip_id=t.id ORDER BY id DESC LIMIT 1) p ON true
            WHERE t.customer_id=p_customer AND t.status='confirmed'
            UNION ALL
            SELECT debt_month,amount_vnd FROM sokhach.adjustment WHERE customer_id=p_customer
            UNION ALL SELECT debt_month,amount_vnd FROM sokhach.v_offset_outgoing WHERE customer_id=p_customer
        ) SELECT debt_month, sum(amount_vnd)::bigint FROM charges
          GROUP BY debt_month ORDER BY debt_month
    LOOP
        v_months := array_append(v_months,v_month);
        v_left := array_append(v_left,v_due);
        v_last := v_month;
    END LOOP;
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
      FROM sokhach.trip t WHERE t.customer_id=get_ledger.customer_id
        AND NOT EXISTS (SELECT 1 FROM sokhach.v_month_chain v
            WHERE v.customer_id=t.customer_id AND v.debt_month=t.debt_month)
    )
    SELECT coalesce(jsonb_agg(jsonb_build_object('month',debt_month,
        'outstanding_vnd',outstanding_vnd::text,'end_of_month_vnd',end_of_month_vnd::text,
        'prior_months_vnd',(end_of_month_vnd-outstanding_vnd)::text,
        'charges_vnd',(coalesce((SELECT sum(CASE WHEN p.unit_price_vnd IS NOT NULL
            THEN p.unit_price_vnd+coalesce(p.other_fee_vnd,0)
            WHEN t.container IS NULL OR t.container='' THEN p.other_fee_vnd END)
            FROM sokhach.trip t LEFT JOIN LATERAL
              (SELECT unit_price_vnd,other_fee_vnd FROM sokhach.trip_price_rev
               WHERE trip_id=t.id ORDER BY id DESC LIMIT 1) p ON true
            WHERE t.customer_id=get_ledger.customer_id AND t.debt_month=visible_months.debt_month AND t.status='confirmed'),0)
            +coalesce((SELECT sum(a.amount_vnd) FROM sokhach.adjustment a
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
        'event_date',t.event_date,'container',t.container,'carrier',t.carrier,'status',t.status,'booking',t.booking,
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
            date_trunc('month',clock_timestamp() AT TIME ZONE 'Asia/Ho_Chi_Minh')::date))
        ORDER BY t.debt_month,t.id),'[]'::jsonb),
        count(*) FILTER (WHERE t.status='pending_review' OR p.unit_price_vnd IS NULL AND NOT
            (p.other_fee_vnd IS NOT NULL AND (t.container IS NULL OR t.container='')))
    INTO v_trips,v_pending FROM sokhach.trip t
    LEFT JOIN LATERAL (SELECT unit_price_vnd,other_fee_vnd FROM sokhach.trip_price_rev
        WHERE trip_id=t.id ORDER BY id DESC LIMIT 1) p ON true
    LEFT JOIN sokhach.month_state ms ON (ms.customer_id,ms.month)=(t.customer_id,t.debt_month)
    WHERE t.customer_id=get_ledger.customer_id;
    SELECT coalesce(jsonb_agg(jsonb_build_object('id',id,'month',debt_month,
        'trip_id',trip_id,'amount_vnd',amount_vnd::text,'note',note,'at',at)
        ORDER BY debt_month,id),'[]'::jsonb) INTO v_adjustments
    FROM sokhach.adjustment WHERE adjustment.customer_id=get_ledger.customer_id;
    SELECT coalesce(jsonb_agg(jsonb_build_object('id',r.id,'pid',r.pid,'date',r.date,
        'method',r.method,'amount_vnd',r.amount_vnd::text,'void_reason',r.void_reason,
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
    SELECT coalesce(jsonb_agg(jsonb_build_object('id',l.id,'month',l.debt_month,
        'kind',l.kind,'display',l.display,'source_total_vnd',l.source_total_vnd::text,
        'historical',true,'editable',false) ORDER BY l.debt_month,l.id),'[]'::jsonb)
    INTO v_legacy FROM sokhach.legacy_row l
    JOIN sokhach.cutover_customer cc ON (cc.customer_id,cc.cutover_id)=(l.customer_id,l.cutover_id)
    JOIN sokhach.cutover c ON c.id=cc.cutover_id
    WHERE l.customer_id=get_ledger.customer_id AND cc.status='active' AND c.status='active';
    SELECT coalesce(jsonb_agg(jsonb_build_object('id',id,'kind',kind,'actor',actor,
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

CREATE OR REPLACE FUNCTION sokhach.record_receipt(customer_id bigint, expected_version bigint,
    idempotency_key text, date date, method text, amount_vnd bigint)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, sokhach, pg_temp AS $$
DECLARE v_payload jsonb := jsonb_build_object('command','record_receipt','date',date,
        'method',method,'amount_vnd',amount_vnd);
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
        UNION ALL SELECT debt_month FROM sokhach.trip WHERE trip.customer_id=record_receipt.customer_id AND status='confirmed'
        UNION ALL SELECT debt_month FROM sokhach.adjustment WHERE adjustment.customer_id=record_receipt.customer_id
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
                           'amount_vnd',amount_vnd::text,'allocations',v_plan_ids),idempotency_key)
    RETURNING id INTO v_event;
    INSERT INTO sokhach.receipt(id,customer_id,pid,date,method,amount_vnd,created_by_event)
    OVERRIDING SYSTEM VALUE VALUES (v_id,customer_id,v_pid,date,method,amount_vnd,v_event);
    FOR v_line IN SELECT value FROM jsonb_array_elements(v_plan_ids) LOOP
        INSERT INTO sokhach.receipt_line(id,receipt_id,customer_id,debt_month,kind,amount_vnd,created_by_event)
        OVERRIDING SYSTEM VALUE VALUES ((v_line->>'id')::bigint,v_id,customer_id,(v_line->>'month')::date,v_line->>'kind',
                (v_line->>'amount_vnd')::bigint,v_event);
    END LOOP;
    PERFORM sokhach._check_allocations(customer_id);
    v_result := jsonb_build_object('receipt_id',v_id,'pid',v_pid,'allocations',v_plan_ids,
                                  'overpayment_vnd',v_left::text);
    RETURN sokhach._finish_command(customer_id,idempotency_key,v_payload,v_result);
END $$;
REVOKE ALL ON FUNCTION sokhach._normalize_key(text),sokhach._booking_key(text,text,date) FROM PUBLIC,sokhach_app,sokhach_reader;
SET LOCAL ROLE sokhach_owner;
DO $$ BEGIN
 IF EXISTS ((SELECT * FROM m211_before EXCEPT SELECT customer_id,sum(outstanding_vnd)::numeric
             FROM sokhach.v_outstanding_month GROUP BY customer_id)
 UNION ALL (SELECT customer_id,sum(outstanding_vnd)::numeric FROM sokhach.v_outstanding_month GROUP BY customer_id
             EXCEPT SELECT * FROM m211_before)) THEN RAISE EXCEPTION 'M211_BALANCE_CHANGED'; END IF;
 IF (SELECT count(*) FROM pg_proc WHERE pronamespace='sokhach'::regnamespace
     AND has_function_privilege('sokhach_app',oid,'EXECUTE')) <> 14
 THEN RAISE EXCEPTION 'M211_GRANTS'; END IF;
END $$;
COMMIT;
RESET ROLE;
