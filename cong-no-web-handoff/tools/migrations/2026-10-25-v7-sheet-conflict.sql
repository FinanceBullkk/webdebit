-- SHEET-CONFLICT-01: remember field-level review without changing money.
-- Apply only after restored-copy rehearsal.
BEGIN;
SET LOCAL ROLE sokhach_owner;

ALTER TABLE sokhach.event DROP CONSTRAINT event_kind_check;
ALTER TABLE sokhach.event ADD CONSTRAINT event_kind_check CHECK (kind IN ('paste', 'price_edit', 'adjust_trip',
    'adjust_month', 'receipt', 'receipt_edit', 'void', 'reallocation', 'month_lock', 'import',
    'customer_attr', 'trip_review', 'trip_edit', 'trip_delete', 'legacy_edit', 'legacy_delete',
    'sheet_conflict_resolved'));
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
    ELSE false END);

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
       OR field NOT IN ('carrier','shipper','origin','destination')
       OR decision NOT IN ('keep_web','use_sheet') OR sheet_value IS NULL THEN
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

REVOKE ALL ON FUNCTION sokhach.resolve_sheet_conflict(bigint,bigint,text,text,bigint,text,bigint,text,text,text,text) FROM PUBLIC,sokhach_reader;
GRANT EXECUTE ON FUNCTION sokhach.resolve_sheet_conflict(bigint,bigint,text,text,bigint,text,bigint,text,text,text,text) TO sokhach_app;
COMMIT;
