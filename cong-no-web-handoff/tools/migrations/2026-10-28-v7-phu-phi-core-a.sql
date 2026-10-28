-- PR-A schema/data. Run only in disposable PostgreSQL harness.
BEGIN;
SET LOCAL ROLE sokhach_owner;
SET LOCAL sokhach.actor='fee-migration';
CREATE TEMP TABLE fee_before_month ON COMMIT DROP AS SELECT customer_id,debt_month,outstanding_vnd FROM sokhach.v_outstanding_month;
CREATE TEMP TABLE fee_before_ledger ON COMMIT DROP AS
 SELECT c.id customer_id,sokhach.get_ledger(c.id)->>'total_outstanding_vnd' total_vnd,
   sokhach.get_ledger(c.id)->'months' months FROM sokhach.customer c;
ALTER TABLE sokhach.adjustment ADD COLUMN IF NOT EXISTS fee_absorbed boolean NOT NULL DEFAULT false;
ALTER TABLE sokhach.trip_price_rev DROP CONSTRAINT IF EXISTS trip_price_rev_other_fee_vnd_check;
ALTER TABLE sokhach.legacy_trip_rev DROP CONSTRAINT IF EXISTS legacy_trip_rev_other_fee_vnd_check;
CREATE TABLE IF NOT EXISTS sokhach.fee_type(
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,name text NOT NULL,
 kind text NOT NULL CHECK(kind IN('service','pass_through')),sign text NOT NULL CHECK(sign IN('positive','negative','any')),
 system_key text UNIQUE,active boolean NOT NULL DEFAULT true,sort integer NOT NULL CHECK(sort>0),
 name_key text GENERATED ALWAYS AS(lower(btrim(name))) STORED,UNIQUE(name_key));
CREATE TABLE IF NOT EXISTS sokhach.book_fee_column(
 customer_id bigint NOT NULL REFERENCES sokhach.customer(id),fee_type_id bigint NOT NULL REFERENCES sokhach.fee_type(id),
 position integer NOT NULL CHECK(position BETWEEN 1 AND 3),PRIMARY KEY(customer_id,fee_type_id),UNIQUE(customer_id,position));
CREATE TABLE IF NOT EXISTS sokhach.trip_fee_line(
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,customer_id bigint NOT NULL REFERENCES sokhach.customer(id),trip_id bigint,legacy_row_id bigint,
 fee_type_id bigint NOT NULL REFERENCES sokhach.fee_type(id),amount_vnd bigint NOT NULL CHECK(amount_vnd<>0),note text,created_by_event bigint NOT NULL,voided_by_event bigint,
 CHECK((trip_id IS NOT NULL)<>(legacy_row_id IS NOT NULL)));
CREATE TABLE IF NOT EXISTS sokhach.fee_type_audit(
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,fee_type_id bigint REFERENCES sokhach.fee_type(id),actor text NOT NULL,payload jsonb NOT NULL,before_value jsonb NOT NULL,after_value jsonb NOT NULL,idempotency_key text NOT NULL UNIQUE,at timestamptz NOT NULL DEFAULT now());
DO $$ BEGIN IF NOT EXISTS(SELECT 1 FROM pg_constraint WHERE conrelid='sokhach.legacy_row'::regclass AND conname='legacy_row_customer_unique')
 THEN ALTER TABLE sokhach.legacy_row ADD CONSTRAINT legacy_row_customer_unique UNIQUE(id,customer_id); END IF; END $$;
DO $$ BEGIN ALTER TABLE sokhach.trip_fee_line ADD CONSTRAINT fee_line_trip_customer_fk FOREIGN KEY(trip_id,customer_id) REFERENCES sokhach.trip(id,customer_id); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN ALTER TABLE sokhach.trip_fee_line ADD CONSTRAINT fee_line_legacy_customer_fk FOREIGN KEY(legacy_row_id,customer_id) REFERENCES sokhach.legacy_row(id,customer_id); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN ALTER TABLE sokhach.trip_fee_line ADD CONSTRAINT fee_line_created_event_fk FOREIGN KEY(created_by_event,customer_id) REFERENCES sokhach.event(id,customer_id); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN ALTER TABLE sokhach.trip_fee_line ADD CONSTRAINT fee_line_voided_event_fk FOREIGN KEY(voided_by_event,customer_id) REFERENCES sokhach.event(id,customer_id); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
CREATE INDEX IF NOT EXISTS trip_fee_line_trip_active ON sokhach.trip_fee_line(trip_id) WHERE voided_by_event IS NULL;
CREATE INDEX IF NOT EXISTS trip_fee_line_legacy_active ON sokhach.trip_fee_line(legacy_row_id) WHERE voided_by_event IS NULL;
CREATE INDEX IF NOT EXISTS trip_fee_line_customer ON sokhach.trip_fee_line(customer_id,id);
INSERT INTO sokhach.fee_type(name,kind,sign,system_key,sort) VALUES
 ('Neo','service','positive',NULL,1),('Điện','service','positive',NULL,2),('Ghép','service','positive',NULL,3),('Bảo hiểm','service','positive',NULL,4),('Kiểm định','service','positive',NULL,5),('Health cert','service','positive',NULL,6),('Khác','service','positive','other',100),('Giảm trừ','service','negative','discount',101),('Phụ phí ban đầu','service','any','initial',102) ON CONFLICT(name_key) DO NOTHING;
CREATE OR REPLACE FUNCTION sokhach._fee_cache_check() RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog,sokhach,pg_temp AS $$
DECLARE v_trip bigint; v_cache bigint; v_total bigint; v_count bigint;
BEGIN IF TG_OP='DELETE' THEN v_trip:=OLD.trip_id; ELSE v_trip:=NEW.trip_id; END IF; IF v_trip IS NULL THEN IF TG_OP='DELETE' THEN RETURN OLD; ELSE RETURN NEW; END IF; END IF;
 SELECT p.other_fee_vnd INTO v_cache FROM sokhach.trip_price_rev p WHERE p.trip_id=v_trip ORDER BY p.id DESC LIMIT 1;
 SELECT count(*),sum(amount_vnd) INTO v_count,v_total FROM sokhach.trip_fee_line WHERE trip_id=v_trip AND voided_by_event IS NULL;
 IF (v_count=0 AND v_cache IS NOT NULL) OR (v_count>0 AND v_cache IS DISTINCT FROM v_total) THEN RAISE EXCEPTION 'FEE_CACHE_MISMATCH'; END IF;
 IF TG_OP='DELETE' THEN RETURN OLD; ELSE RETURN NEW; END IF; END $$;
DO $$ BEGIN IF NOT EXISTS(SELECT 1 FROM pg_trigger WHERE tgrelid='sokhach.trip_fee_line'::regclass AND tgname='trip_fee_cache_check') THEN CREATE CONSTRAINT TRIGGER trip_fee_cache_check AFTER INSERT OR UPDATE OR DELETE ON sokhach.trip_fee_line DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION sokhach._fee_cache_check(); END IF; END $$;
DO $$ BEGIN IF NOT EXISTS(SELECT 1 FROM pg_trigger WHERE tgrelid='sokhach.trip_price_rev'::regclass AND tgname='trip_price_cache_check') THEN CREATE CONSTRAINT TRIGGER trip_price_cache_check AFTER INSERT OR UPDATE ON sokhach.trip_price_rev DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION sokhach._fee_cache_check(); END IF; END $$;
CREATE OR REPLACE FUNCTION sokhach._sync_trip_fee(p_trip_id bigint,p_event_id bigint) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,sokhach,pg_temp AS $$
DECLARE v_unit bigint; v_old bigint; v_total bigint; v_count bigint;
BEGIN SELECT unit_price_vnd,other_fee_vnd INTO v_unit,v_old FROM sokhach.trip_price_rev WHERE trip_id=p_trip_id ORDER BY id DESC LIMIT 1;
 SELECT count(*),sum(amount_vnd) INTO v_count,v_total FROM sokhach.trip_fee_line WHERE trip_id=p_trip_id AND voided_by_event IS NULL;
 IF v_count=0 THEN v_total:=NULL; END IF; IF v_old IS NOT DISTINCT FROM v_total THEN RETURN; END IF;
 INSERT INTO sokhach.trip_price_rev(trip_id,customer_id,unit_price_vnd,other_fee_vnd,created_by_event) SELECT p_trip_id,t.customer_id,v_unit,v_total,p_event_id FROM sokhach.trip t WHERE t.id=p_trip_id;
END $$;
CREATE OR REPLACE VIEW sokhach.v_adjustment_current AS
SELECT a.id,a.customer_id,coalesce(t.debt_month,a.debt_month) AS debt_month,
       a.trip_id,a.legacy_row_id,a.amount_vnd,a.field,a.new_value_vnd,a.note,a.actor,a.at,a.created_by_event
FROM sokhach.adjustment a LEFT JOIN sokhach.v_trip_current t ON t.id=a.trip_id
WHERE NOT a.fee_absorbed AND (a.trip_id IS NULL OR (NOT t.deleted AND t.status='confirmed'));
-- Stop before conversion when ambiguous source rows need business review.
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
DO $$ DECLARE r record; BEGIN SELECT * INTO r FROM sokhach.v7_fee_migration_dry_run(); IF r.orphan_zero_fee>0 OR r.null_price_with_adjustment>0 THEN RAISE EXCEPTION 'FEE_MIGRATION_REVIEW_REQUIRED orphan_zero_fee=% null_price_with_adjustment=%',r.orphan_zero_fee,r.null_price_with_adjustment; END IF; END $$;
-- Snapshot targets before writes; rerun sees neither old adjustments nor unconverted fees.
CREATE TEMP TABLE fee_targets ON COMMIT DROP AS
 SELECT p.trip_id,p.customer_id,p.unit_price_vnd,p.created_by_event,
   CASE WHEN p.other_fee_vnd IS NULL AND NOT EXISTS(SELECT 1 FROM sokhach.adjustment a
       WHERE a.trip_id=p.trip_id AND a.field='other_fee_vnd' AND NOT a.fee_absorbed)
     THEN NULL ELSE coalesce(p.other_fee_vnd,0)+coalesce((SELECT sum(a.amount_vnd)
       FROM sokhach.adjustment a WHERE a.trip_id=p.trip_id AND a.field='other_fee_vnd' AND NOT a.fee_absorbed),0) END AS fee_vnd
 FROM(SELECT DISTINCT ON(trip_id)* FROM sokhach.trip_price_rev ORDER BY trip_id,id DESC)p
 WHERE NOT EXISTS(SELECT 1 FROM sokhach.trip_fee_line l WHERE l.trip_id=p.trip_id)
   AND (p.other_fee_vnd IS NOT NULL OR EXISTS(SELECT 1 FROM sokhach.adjustment a
       WHERE a.trip_id=p.trip_id AND a.field='other_fee_vnd' AND NOT a.fee_absorbed));
-- Web conversion: create source line, then cache revision, then absorb old fee adjustments.
INSERT INTO sokhach.trip_fee_line(customer_id,trip_id,fee_type_id,amount_vnd,note,created_by_event)
SELECT q.customer_id,q.trip_id,(SELECT id FROM sokhach.fee_type WHERE system_key='initial'),q.fee_vnd,
 'migration: initial fee',q.created_by_event FROM fee_targets q WHERE q.fee_vnd<>0;
INSERT INTO sokhach.trip_price_rev(trip_id,customer_id,unit_price_vnd,other_fee_vnd,created_by_event)
SELECT q.trip_id,q.customer_id,q.unit_price_vnd,NULLIF(q.fee_vnd,0),q.created_by_event FROM fee_targets q;
ALTER TABLE sokhach.adjustment DISABLE TRIGGER adjustment_immutable;
UPDATE sokhach.adjustment a SET fee_absorbed=true
 WHERE a.field='other_fee_vnd' AND NOT a.fee_absorbed AND EXISTS(SELECT 1 FROM fee_targets q WHERE q.trip_id=a.trip_id);
ALTER TABLE sokhach.adjustment ENABLE TRIGGER adjustment_immutable;
-- Legacy conversion is display-only; source TOTAL and current revisions remain untouched.
INSERT INTO sokhach.trip_fee_line(customer_id,legacy_row_id,fee_type_id,amount_vnd,note,created_by_event)
SELECT r.customer_id,r.id,(SELECT id FROM sokhach.fee_type WHERE system_key='initial'),x.fee,'migration: legacy fee',r.created_by_event FROM sokhach.legacy_row r CROSS JOIN LATERAL(SELECT (sokhach._legacy_current(r.id)->>'other_fee_vnd')::bigint fee)x WHERE r.kind='trip' AND x.fee IS NOT NULL AND x.fee<>0 AND NOT EXISTS(SELECT 1 FROM sokhach.trip_fee_line l WHERE l.legacy_row_id=r.id);
DO $$ BEGIN
 IF EXISTS(SELECT 1 FROM fee_targets q JOIN LATERAL
   (SELECT unit_price_vnd,other_fee_vnd FROM sokhach.trip_price_rev p WHERE p.trip_id=q.trip_id ORDER BY p.id DESC LIMIT 1)p ON true
   WHERE p.unit_price_vnd IS DISTINCT FROM q.unit_price_vnd
      OR p.other_fee_vnd IS DISTINCT FROM nullif(q.fee_vnd,0)
      OR EXISTS(SELECT 1 FROM sokhach.adjustment a WHERE a.trip_id=q.trip_id
          AND a.field='other_fee_vnd' AND NOT a.fee_absorbed))
 THEN RAISE EXCEPTION 'FEE_MIGRATION_TARGET_MISMATCH'; END IF;
 IF EXISTS(SELECT * FROM fee_before_month b FULL JOIN sokhach.v_outstanding_month a USING(customer_id,debt_month)
   WHERE b.outstanding_vnd IS DISTINCT FROM a.outstanding_vnd)
 OR EXISTS(SELECT * FROM fee_before_ledger b JOIN sokhach.customer c ON c.id=b.customer_id
   WHERE b.total_vnd IS DISTINCT FROM sokhach.get_ledger(c.id)->>'total_outstanding_vnd'
      OR b.months IS DISTINCT FROM sokhach.get_ledger(c.id)->'months')
 THEN RAISE EXCEPTION 'FEE_MIGRATION_TOTAL_MISMATCH'; END IF;
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
 IF t.system_key='initial' THEN RAISE EXCEPTION 'FEE_TYPE_SYSTEM'; END IF;
 IF (t.sign='positive' AND NEW.amount_vnd<0) OR (t.sign='negative' AND NEW.amount_vnd>0)
 THEN RAISE EXCEPTION 'FEE_SIGN_INVALID'; END IF;
 RETURN NEW;
END $$;
DO $$ BEGIN IF NOT EXISTS(SELECT 1 FROM pg_trigger WHERE tgrelid='sokhach.trip_fee_line'::regclass AND tgname='fee_line_guard')
 THEN CREATE TRIGGER fee_line_guard BEFORE INSERT OR UPDATE OR DELETE ON sokhach.trip_fee_line FOR EACH ROW EXECUTE FUNCTION sokhach._guard_fee_line(); END IF; END $$;
REVOKE ALL ON sokhach.fee_type,sokhach.book_fee_column,sokhach.trip_fee_line,sokhach.fee_type_audit FROM PUBLIC,sokhach_app,sokhach_reader;

-- Final command definitions copied verbatim from v7_backend_functions.sql.
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

CREATE OR REPLACE FUNCTION sokhach._change_legacy(customer_id bigint,expected_version bigint,idempotency_key text,
    legacy_row_id bigint,field text,value text,p_delete boolean) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,sokhach,pg_temp AS $$
DECLARE v_payload jsonb:=jsonb_build_object('command',CASE WHEN p_delete THEN 'delete_legacy_trip' ELSE 'edit_legacy_trip' END,
      'legacy_row_id',legacy_row_id,'field',field,'value',value);
    v_retry jsonb; l sokhach.legacy_row%ROWTYPE; v_old jsonb; v_new jsonb; v_value text;
    v_month date; v_old_month date; v_count bigint; v_old_count bigint; v_event bigint; v_changes jsonb;
    v_fee bigint;
BEGIN
    v_retry:=sokhach._begin_command(customer_id,expected_version,idempotency_key,v_payload);
    IF v_retry IS NOT NULL THEN RETURN v_retry; END IF;
    PERFORM sokhach._baseline(customer_id);
    SELECT l0.* INTO l FROM sokhach.legacy_row l0 JOIN sokhach.cutover_customer cc USING(customer_id,cutover_id)
      JOIN sokhach.cutover c ON c.id=cc.cutover_id WHERE l0.id=legacy_row_id AND l0.customer_id=_change_legacy.customer_id AND cc.status='active' AND c.status='active';
    IF NOT FOUND THEN RAISE EXCEPTION 'LEGACY_NOT_FOUND'; END IF;
    IF l.kind<>'trip' THEN RAISE EXCEPTION 'LEGACY_NOT_TRIP'; END IF;
    v_old:=sokhach._legacy_current(l.id);
    SELECT sum(amount_vnd)::bigint INTO v_fee FROM sokhach.trip_fee_line
      WHERE trip_fee_line.legacy_row_id=l.id AND voided_by_event IS NULL;
    v_old:=v_old||jsonb_build_object('other_fee_vnd',v_fee::text);
    v_new:=v_old;
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
      IF field='other_fee_vnd' AND EXISTS (SELECT 1 FROM sokhach.trip_fee_line fl JOIN sokhach.fee_type ft ON ft.id=fl.fee_type_id
          WHERE fl.legacy_row_id=l.id AND fl.voided_by_event IS NULL
            AND coalesce(ft.system_key,'') NOT IN ('other','discount','initial'))
      THEN RAISE EXCEPTION 'FEE_LINES_TYPED'; END IF;
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
    IF field='other_fee_vnd' AND NOT p_delete THEN
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
    INSERT INTO sokhach.adjustment(customer_id,debt_month,legacy_row_id,amount_vnd,actor,created_by_event)
      SELECT customer_id,m,l.id,delta,sokhach._actor(),v_event FROM (
        SELECT v_old_month AS m,CASE WHEN v_month=v_old_month THEN v_count-v_old_count ELSE -v_old_count END AS delta
        UNION ALL SELECT v_month,v_count WHERE v_month<>v_old_month) d WHERE delta<>0;
    v_changes:=sokhach.reallocate(customer_id,idempotency_key);
    RETURN sokhach._finish_command(customer_id,idempotency_key,v_payload,jsonb_build_object('legacy_row_id',l.id,'deleted',p_delete,'reallocated',v_changes));
EXCEPTION WHEN numeric_value_out_of_range THEN RAISE EXCEPTION 'INVALID_VND';
END $$;

CREATE OR REPLACE FUNCTION sokhach._compat_trip_fee(p_customer bigint,p_trip bigint,p_fee bigint,p_event bigint) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,sokhach,pg_temp AS $$
DECLARE v_type bigint; v_old bigint; v_count bigint; v_existing_type bigint;
BEGIN
    IF EXISTS (SELECT 1 FROM sokhach.trip_fee_line l JOIN sokhach.fee_type f ON f.id=l.fee_type_id
        WHERE l.trip_id=p_trip AND l.voided_by_event IS NULL
          AND coalesce(f.system_key,'') NOT IN ('other','discount','initial'))
    THEN RAISE EXCEPTION 'FEE_LINES_TYPED'; END IF;
    SELECT sum(amount_vnd)::bigint,count(*),min(fee_type_id) INTO v_old,v_count,v_existing_type FROM sokhach.trip_fee_line
      WHERE trip_id=p_trip AND voided_by_event IS NULL;
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
REVOKE ALL ON FUNCTION sokhach.v7_fee_migration_dry_run(),sokhach._fee_cache_check(),
 sokhach._sync_trip_fee(bigint,bigint),sokhach._guard_fee_line(),
 sokhach._compat_trip_fee(bigint,bigint,bigint,bigint) FROM PUBLIC,sokhach_app,sokhach_reader;
COMMIT;
