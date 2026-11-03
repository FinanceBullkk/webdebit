-- Apply one verified Sheet price through existing financial commands, atomically.
BEGIN;
SET LOCAL ROLE sokhach_owner;
CREATE OR REPLACE FUNCTION sokhach.apply_sheet_price(
 customer_id bigint, expected_version bigint, idempotency_key text,
 target_kind text, target_id bigint, source_fingerprint text, web_value jsonb, sheet_price jsonb
) RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,sokhach,pg_temp AS $$
DECLARE v_payload jsonb:=jsonb_build_object('command','apply_sheet_price','target_kind',target_kind,
 'target_id',target_id,'source_fingerprint',source_fingerprint,'web_value',web_value,'sheet_price',sheet_price);
 v_retry jsonb; v_current jsonb; v_result jsonb; v_version bigint; v_key text;
BEGIN
 v_retry:=sokhach._begin_command(customer_id,expected_version,idempotency_key,v_payload);
 IF v_retry IS NOT NULL THEN RETURN v_retry; END IF;
 PERFORM sokhach._baseline(customer_id);
 IF target_kind IS NULL OR target_kind NOT IN ('trip','legacy') OR target_id IS NULL OR target_id<=0
  OR source_fingerprint IS NULL OR source_fingerprint !~ '^[0-9a-f]{64}$'
  OR jsonb_typeof(sheet_price) IS DISTINCT FROM 'object' OR web_value IS NULL
  OR sheet_price->>'unit_price_vnd' IS NULL OR sheet_price->>'unit_price_vnd' !~ '^[0-9]+$'
  OR (sheet_price->>'other_fee_vnd' IS NOT NULL AND sheet_price->>'other_fee_vnd' !~ '^-?[0-9]+$')
 THEN RAISE EXCEPTION 'INVALID_SHEET_RESOLUTION'; END IF;
 IF target_kind='trip' THEN
  SELECT jsonb_build_object('unit_price_vnd',t.value->>'unit_price_vnd','other_fee_vnd',t.value->>'other_fee_vnd')
   INTO v_current FROM jsonb_array_elements(sokhach.get_ledger(customer_id)->'trips') t
   WHERE (t.value->>'id')::bigint=target_id AND NOT coalesce((t.value->>'deleted')::boolean,false);
 ELSE
  SELECT jsonb_build_object('unit_price_vnd',l.value->'current'->>'unit_price_vnd','other_fee_vnd',l.value->'current'->>'other_fee_vnd')
   INTO v_current FROM jsonb_array_elements(sokhach.get_ledger(customer_id)->'legacy_rows') l
   WHERE (l.value->>'id')::bigint=target_id AND l.value->>'kind'='trip' AND NOT coalesce((l.value->'current'->>'deleted')::boolean,false);
 END IF;
 IF v_current IS NULL THEN RAISE EXCEPTION 'TRIP_NOT_FOUND'; END IF;
 IF v_current IS DISTINCT FROM web_value THEN RAISE EXCEPTION 'STALE_LEDGER'; END IF;
 v_key:=encode(sha256(convert_to(idempotency_key||':sheet-price','UTF8')),'hex');
 IF target_kind='trip' THEN
  v_result:=sokhach.edit_trip_price(customer_id,expected_version,v_key,target_id,
   (sheet_price->>'unit_price_vnd')::bigint,(sheet_price->>'other_fee_vnd')::bigint);
 ELSE
  v_version:=expected_version;
  IF v_current->>'unit_price_vnd' IS DISTINCT FROM sheet_price->>'unit_price_vnd' THEN
   v_result:=sokhach.edit_legacy_trip(customer_id,v_version,v_key,target_id,'unit_price_vnd',sheet_price->>'unit_price_vnd');
   v_version:=(v_result->>'version')::bigint;
  END IF;
  IF nullif(v_current->>'other_fee_vnd','0') IS DISTINCT FROM nullif(sheet_price->>'other_fee_vnd','0') THEN
   v_result:=sokhach.edit_legacy_trip(customer_id,v_version,v_key||':fee',target_id,'other_fee_vnd',sheet_price->>'other_fee_vnd');
  END IF;
  IF v_result IS NULL THEN RAISE EXCEPTION 'NO_CHANGE'; END IF;
 END IF;
 INSERT INTO sokhach.event(customer_id,kind,actor,"before","after",idempotency_key)
 VALUES(customer_id,'sheet_conflict_resolved',sokhach._actor(),
  jsonb_build_object('target',jsonb_build_object('kind',target_kind,'id',target_id),'field','task_price','value',v_current),
  jsonb_build_object('target',jsonb_build_object('kind',target_kind,'id',target_id),'field','task_price','source_row',0,
   'sheet_value',source_fingerprint,'target_value',sheet_price,'decision','use_sheet','requested_price',sheet_price,
   'web_value',web_value,'request_key',idempotency_key),idempotency_key);
 RETURN sokhach._finish_command(customer_id,idempotency_key,v_payload,jsonb_build_object('written',1,'complete',true));
END $$;
REVOKE ALL ON FUNCTION sokhach.apply_sheet_price(bigint,bigint,text,text,bigint,text,jsonb,jsonb) FROM PUBLIC,sokhach_reader;
GRANT EXECUTE ON FUNCTION sokhach.apply_sheet_price(bigint,bigint,text,text,bigint,text,jsonb,jsonb) TO sokhach_app;
COMMIT;
