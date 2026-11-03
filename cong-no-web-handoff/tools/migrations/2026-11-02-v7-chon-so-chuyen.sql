-- One source trip, explicit destination book, no price; both books retain audit.
BEGIN;
SET LOCAL ROLE sokhach_owner;
CREATE OR REPLACE FUNCTION sokhach.assign_sheet_trip(
 customer_id bigint, expected_version bigint, idempotency_key text,
 target_customer_id bigint, target_version bigint, source_fingerprint text, source_row jsonb
) RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,sokhach,pg_temp AS $$
DECLARE v_payload jsonb:=jsonb_build_object('command','assign_sheet_trip','target_customer_id',target_customer_id,
 'source_fingerprint',source_fingerprint,'source_row',source_row);
 v_retry jsonb; v_result jsonb; v_trip bigint; v_after jsonb; v_date date; v_key text;
BEGIN
 PERFORM id FROM sokhach.customer c WHERE c.id IN (customer_id,target_customer_id) ORDER BY id FOR UPDATE;
 v_retry:=sokhach._begin_command(customer_id,expected_version,idempotency_key,v_payload);
 IF v_retry IS NOT NULL THEN RETURN v_retry; END IF;
 IF target_customer_id IS NULL OR target_customer_id<=0 OR source_fingerprint IS NULL
  OR source_fingerprint !~ '^[0-9a-f]{64}$' OR jsonb_typeof(source_row) IS DISTINCT FROM 'object'
 THEN RAISE EXCEPTION 'INVALID_COMMAND'; END IF;
 v_date:=(source_row->>'event_date')::date;
 IF v_date IS NULL THEN RAISE EXCEPTION 'INVALID_DATE'; END IF;
 v_key:=encode(sha256(convert_to(idempotency_key||':assign','UTF8')),'hex');
 v_result:=sokhach.paste_trips(target_customer_id,target_version,v_key,date_trunc('month',v_date)::date,
  jsonb_build_array(jsonb_build_object('date',to_char(v_date,'DD/MM/YYYY'),'container',source_row->>'container',
   'carrier',source_row->>'carrier','shipper',source_row->>'shipper','from',source_row->>'origin','to',source_row->>'destination',
   'booking',coalesce(source_row->>'booking',''),'unitPriceVnd',NULL,'otherFeeVnd',NULL,
   'note','Chuyến đồng bộ','src','sheet-choice:'||source_fingerprint)));
 v_trip:=(v_result->'trip_ids'->>0)::bigint;
 v_after:=jsonb_build_object('target',jsonb_build_object('kind','trip','id',v_trip),'field','task_assignment',
  'source_row',source_row->'source_row','sheet_value',source_fingerprint,'target_value',target_customer_id,
  'decision','use_sheet','target_customer_id',target_customer_id,'request_key',idempotency_key,
  'arguments',jsonb_build_object('customer_id',customer_id,'expected_version',expected_version,'idempotency_key',idempotency_key,
   'target_customer_id',target_customer_id,'target_version',target_version,'source_fingerprint',source_fingerprint,'source_row',source_row));
 INSERT INTO sokhach.event(customer_id,kind,actor,"before","after",idempotency_key)
 VALUES(customer_id,'sheet_conflict_resolved',sokhach._actor(),jsonb_build_object('target',v_after->'target','field','task_assignment'),v_after,idempotency_key);
 IF target_customer_id<>customer_id THEN
  INSERT INTO sokhach.event(customer_id,kind,actor,"before","after",idempotency_key)
  VALUES(target_customer_id,'sheet_conflict_resolved',sokhach._actor(),jsonb_build_object('target',v_after->'target','field','task_assignment'),v_after,v_key);
 END IF;
 RETURN sokhach._finish_command(customer_id,idempotency_key,v_payload,jsonb_build_object('approved',1,'trip_id',v_trip,
  'target_customer_id',target_customer_id,'pending_review',v_result->'pending_review','complete',true));
END $$;
REVOKE ALL ON FUNCTION sokhach.assign_sheet_trip(bigint,bigint,text,bigint,bigint,text,jsonb) FROM PUBLIC,sokhach_reader;
GRANT EXECUTE ON FUNCTION sokhach.assign_sheet_trip(bigint,bigint,text,bigint,bigint,text,jsonb) TO sokhach_app;
COMMIT;
