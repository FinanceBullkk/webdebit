-- Restore exactly the price/receipt commands returned by the last inbox batch.
BEGIN;
SET LOCAL ROLE sokhach_owner;
CREATE OR REPLACE FUNCTION sokhach.undo_sheet_batch(
 customer_id bigint, expected_version bigint, idempotency_key text, command_keys jsonb
) RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,sokhach,pg_temp AS $$
DECLARE v_payload jsonb:=jsonb_build_object('command','undo_sheet_batch','command_keys',command_keys);
 v_retry jsonb; v_key text; v_undo_key text; e sokhach.event%ROWTYPE; v_version bigint;
 v_result jsonb; v_before jsonb; v_after jsonb; v_current jsonb; v_id bigint; v_event bigint; v_count bigint;
BEGIN
 v_retry:=sokhach._begin_command(customer_id,expected_version,idempotency_key,v_payload);
 IF v_retry IS NOT NULL THEN RETURN v_retry; END IF;
 PERFORM sokhach._baseline(customer_id);
 IF jsonb_typeof(command_keys) IS DISTINCT FROM 'array' OR jsonb_array_length(command_keys) NOT BETWEEN 1 AND 1000
  OR EXISTS(SELECT 1 FROM jsonb_array_elements(command_keys) k WHERE jsonb_typeof(k)<>'string' OR k#>>'{}' !~ '^[0-9a-f]{64}$')
  OR (SELECT count(DISTINCT k) FROM jsonb_array_elements_text(command_keys) k)<>jsonb_array_length(command_keys)
 THEN RAISE EXCEPTION 'INVALID_COMMAND'; END IF;
 v_version:=expected_version;
 FOR v_key IN SELECT k FROM jsonb_array_elements_text(command_keys) WITH ORDINALITY x(k,n) ORDER BY n DESC LOOP
  SELECT * INTO e FROM sokhach.event ev WHERE ev.customer_id=undo_sheet_batch.customer_id AND ev.idempotency_key=v_key
   AND ev.kind IN ('price_edit','receipt','legacy_edit') ORDER BY ev.id DESC LIMIT 1;
  IF NOT FOUND THEN RAISE EXCEPTION 'INVALID_COMMAND'; END IF;
  v_undo_key:=encode(sha256(convert_to(idempotency_key||':'||v_key,'UTF8')),'hex');
  IF e.kind='receipt' THEN
   v_result:=sokhach.void_receipt(customer_id,v_version,v_undo_key,e."after"->>'pid','Hoàn tác lần ghi từ Việc cần làm');
  ELSIF e.kind='price_edit' THEN
   v_before:=e."before"->'price'; v_after:=e."after"->'price'; v_id:=(v_after->>'trip_id')::bigint;
   SELECT t.value INTO v_current FROM jsonb_array_elements(sokhach.get_ledger(customer_id)->'trips') t
    WHERE (t.value->>'id')::bigint=v_id AND NOT coalesce((t.value->>'deleted')::boolean,false);
   IF v_current IS NULL OR v_current->>'unit_price_vnd' IS DISTINCT FROM v_after->>'unit_price_vnd'
    OR v_current->>'other_fee_vnd' IS DISTINCT FROM v_after->>'other_fee_vnd' THEN RAISE EXCEPTION 'STALE_LEDGER'; END IF;
   v_result:=sokhach.edit_trip_price(customer_id,v_version,v_undo_key,v_id,
     (v_before->>'unit_price_vnd')::bigint,(v_before->>'other_fee_vnd')::bigint);
  ELSE
   v_before:=e."before"->'legacy'; v_after:=e."after"->'legacy'; v_id:=(v_before->>'legacy_row_id')::bigint;
   IF v_before->>'kind'<>'trip' OR v_before->>'field' NOT IN ('unit_price_vnd','other_fee_vnd') THEN RAISE EXCEPTION 'INVALID_COMMAND'; END IF;
   v_current:=sokhach._legacy_current(v_id);
   IF v_current->>'unit_price_vnd' IS DISTINCT FROM v_after->>'unit_price_vnd'
    OR v_current->>'counted_vnd' IS DISTINCT FROM v_after->>'counted_vnd' THEN RAISE EXCEPTION 'STALE_LEDGER'; END IF;
   v_result:=sokhach.edit_legacy_trip(customer_id,v_version,v_undo_key,v_id,v_before->>'field',v_before->>'value');
   v_current:=sokhach._legacy_current(v_id);
   v_count:=(v_before->>'counted_vnd')::bigint;
   IF (v_current->>'counted_vnd')::bigint<>v_count THEN
    -- Restoring an original-book price must also restore its original TOTAL, which may differ from price + fees.
    v_after:=v_current||jsonb_build_object('counted_vnd',v_count::text,'field','unit_price_vnd','value',v_current->'unit_price_vnd');
    INSERT INTO sokhach.event(customer_id,kind,actor,"before","after",idempotency_key)
    VALUES(customer_id,'legacy_edit',sokhach._actor(),jsonb_build_object('legacy',v_current),jsonb_build_object('legacy',v_after),v_undo_key) RETURNING id INTO v_event;
    INSERT INTO sokhach.legacy_trip_rev(legacy_row_id,customer_id,debt_month,event_date,container,carrier,shipper,origin,destination,unit_price_vnd,other_fee_vnd,deleted,counted_vnd,created_by_event)
    VALUES(v_id,customer_id,(v_current->>'month')::date,(v_current->>'event_date')::date,v_current->>'container',v_current->>'carrier',v_current->>'shipper',v_current->>'origin',v_current->>'destination',
     (v_current->>'unit_price_vnd')::bigint,(v_current->>'other_fee_vnd')::bigint,false,v_count,v_event);
    INSERT INTO sokhach.adjustment(customer_id,debt_month,legacy_row_id,amount_vnd,actor,created_by_event)
    VALUES(customer_id,(v_current->>'month')::date,v_id,v_count-(v_current->>'counted_vnd')::bigint,sokhach._actor(),v_event);
   END IF;
  END IF;
  v_version:=(v_result->>'version')::bigint;
 END LOOP;
 PERFORM sokhach.reallocate(customer_id,idempotency_key);
 RETURN sokhach._finish_command(customer_id,idempotency_key,v_payload,jsonb_build_object('undone',jsonb_array_length(command_keys),'complete',true));
END $$;
REVOKE ALL ON FUNCTION sokhach.undo_sheet_batch(bigint,bigint,text,jsonb) FROM PUBLIC,sokhach_reader;
GRANT EXECUTE ON FUNCTION sokhach.undo_sheet_batch(bigint,bigint,text,jsonb) TO sokhach_app;
COMMIT;
