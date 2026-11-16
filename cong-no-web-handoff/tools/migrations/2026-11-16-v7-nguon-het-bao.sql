-- K3 (KIEM-TAB-01 đợt 4, specs/v7-kiem-tab-truoc-khi-ghi.md): "Đã xem, hết báo" cho một dòng Sheet theo dấu vân nội dung, không cần chuyến đích.
-- keep_sheet_task nhận thêm task_kind 'source' (target_kind, target_id phải NULL; web_value = {"scope": price|ps|trip}).
-- Chỉ ghi Lịch sử (sheet_conflict_resolved, field task_source), không đổi tiền, chuyến, phân bổ hay số dư. Dòng Sheet đổi thì dấu vân đổi, việc hiện lại.
-- Đảo lại: áp 2026-11-09-v7-ps-khong-thu.sql (các event task_source đã ghi vẫn nằm trong Lịch sử, không ảnh hưởng tiền).
BEGIN;
SET LOCAL ROLE sokhach_owner;
CREATE OR REPLACE FUNCTION sokhach.keep_sheet_task(
 customer_id bigint, expected_version bigint, idempotency_key text,
 task_kind text, target_kind text, target_id bigint, source_fingerprint text, web_value jsonb
) RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,sokhach,pg_temp AS $$
DECLARE v_payload jsonb:=jsonb_build_object('command','keep_sheet_task','task_kind',task_kind,
 'target_kind',target_kind,'target_id',target_id,'source_fingerprint',source_fingerprint,'web_value',web_value);
 v_retry jsonb; v_current jsonb; v_row jsonb;
BEGIN
 v_retry:=sokhach._begin_command(customer_id,expected_version,idempotency_key,v_payload);
 IF v_retry IS NOT NULL THEN RETURN v_retry; END IF;
 PERFORM sokhach._baseline(customer_id);
 IF task_kind IS NULL OR task_kind NOT IN ('price','removed','ps','source')
  OR source_fingerprint IS NULL OR source_fingerprint !~ '^[0-9a-f]{64}$' OR web_value IS NULL
 THEN RAISE EXCEPTION 'INVALID_SHEET_RESOLUTION'; END IF;
 IF task_kind='source' THEN
  -- K3: đóng một dòng Sheet theo dấu vân nội dung của nó, không gắn chuyến. web_value chỉ là {"scope": ...}.
  IF target_kind IS NOT NULL OR target_id IS NOT NULL OR jsonb_typeof(web_value)<>'object'
   OR web_value-'scope'<>'{}'::jsonb OR web_value->>'scope' IS NULL OR web_value->>'scope' NOT IN ('price','ps','trip')
  THEN RAISE EXCEPTION 'INVALID_SHEET_RESOLUTION'; END IF;
  INSERT INTO sokhach.event(customer_id,kind,actor,"before","after",idempotency_key)
  VALUES(customer_id,'sheet_conflict_resolved',sokhach._actor(),
   jsonb_build_object('target',jsonb_build_object('kind','source','scope',web_value->>'scope'),'field','task_source','value',web_value),
   jsonb_build_object('target',jsonb_build_object('kind','source','scope',web_value->>'scope'),'field','task_source',
    'source_row',0,'sheet_value',source_fingerprint,'target_value',web_value,'decision','keep_web','request_key',idempotency_key),idempotency_key);
  RETURN sokhach._finish_command(customer_id,idempotency_key,v_payload,jsonb_build_object('kept',true));
 END IF;
 IF target_kind IS NULL OR target_kind NOT IN ('trip','legacy') OR target_id IS NULL OR target_id<=0
  OR (task_kind='removed' AND target_kind<>'trip')
 THEN RAISE EXCEPTION 'INVALID_SHEET_RESOLUTION'; END IF;
 IF target_kind='trip' THEN
  SELECT t.value INTO v_row FROM jsonb_array_elements(sokhach.get_ledger(customer_id)->'trips') t
   WHERE (t.value->>'id')::bigint=target_id AND NOT coalesce((t.value->>'deleted')::boolean,false);
 ELSE
  SELECT sokhach._legacy_current(l.id) INTO v_row FROM sokhach.legacy_row l
   JOIN sokhach.cutover_customer cc USING(customer_id,cutover_id)
   JOIN sokhach.cutover c ON c.id=cc.cutover_id
   WHERE l.customer_id=keep_sheet_task.customer_id AND l.id=target_id AND l.kind='trip'
     AND cc.status='active' AND c.status='active';
 END IF;
 IF v_row IS NULL OR coalesce((v_row->>'deleted')::boolean,false) THEN RAISE EXCEPTION 'TRIP_NOT_FOUND'; END IF;
 v_current:=CASE WHEN task_kind IN ('price','ps') THEN jsonb_build_object(
  'unit_price_vnd',v_row->>'unit_price_vnd','other_fee_vnd',v_row->>'other_fee_vnd')
 ELSE jsonb_build_object('container',v_row->>'container','event_date',v_row->>'event_date',
  'status',v_row->>'status','booking',v_row->>'booking') END;
 IF v_current IS DISTINCT FROM web_value THEN RAISE EXCEPTION 'STALE_LEDGER'; END IF;
 INSERT INTO sokhach.event(customer_id,kind,actor,"before","after",idempotency_key)
 VALUES(customer_id,'sheet_conflict_resolved',sokhach._actor(),
  jsonb_build_object('target',jsonb_build_object('kind',target_kind,'id',target_id),'field','task_'||task_kind,'value',v_current),
  jsonb_build_object('target',jsonb_build_object('kind',target_kind,'id',target_id),'field','task_'||task_kind,
   'source_row',0,'sheet_value',source_fingerprint,'target_value',v_current,'decision','keep_web','request_key',idempotency_key),idempotency_key);
 RETURN sokhach._finish_command(customer_id,idempotency_key,v_payload,jsonb_build_object('kept',true));
END $$;
REVOKE ALL ON FUNCTION sokhach.keep_sheet_task(bigint,bigint,text,text,text,bigint,text,jsonb) FROM PUBLIC,sokhach_reader;
GRANT EXECUTE ON FUNCTION sokhach.keep_sheet_task(bigint,bigint,text,text,text,bigint,text,jsonb) TO sokhach_app;
COMMIT;
