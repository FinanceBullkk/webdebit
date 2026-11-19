-- Audit kiến trúc 19/11/2026 (commit 0a2eaad), hai lệnh ghi thiếu kiểm so với hợp đồng của chính chúng. Chỉ thay thân hai hàm;
-- không đổi bảng, ràng buộc, loại event, quyền, dữ liệu hay luật tiền. Chạy sau 2026-11-16-v7-chuan-hoa-chu.sql (bản trước của
-- edit_trip_info) và 2026-11-01-v7-zalo-group.sql (bản trước của record_mark); chạy lại được.
-- A12 edit_trip_info: đổi container hoặc ngày của chuyến confirmed chạy lại kiểm trùng "như paste_trips" (specs/v7-sua-xoa-chuyen.md
--     mục 2) nhưng thiếu luật dòng sổ gốc không ngày (BASELINE_UNDATED_MONTH, 2026-11-01-v7-chan-trung-hang-cho.sql). Thêm đúng luật
--     đó, đúng thứ tự như paste_trips. Chuyến đã confirmed từ trước không bị quét lại; chỉ lần sửa container/ngày sau này mới xét.
-- A08 record_mark: gửi lại cùng idempotency_key nhưng tiền/ngày/ghi chú/tin gắn khác thì trả IDEMPOTENCY_CONFLICT thay vì trả dấu cũ
--     như đã lưu nội dung mới. Gửi lại đúng nội dung cũ vẫn trả dấu cũ (replayed=true).
BEGIN;
SET LOCAL ROLE sokhach_owner;
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
    -- KHOA-CHU-01 (1/11/2026): bốn ô chữ mô tả sửa được cả ở tháng khóa; container và ngày vẫn theo khóa tháng.
    IF field NOT IN ('carrier','shipper','origin','destination') THEN
      PERFORM sokhach._month_open(customer_id,t.debt_month,clock_timestamp());
    END IF;
    v_value := nullif(btrim(value),'');
    IF field='container' THEN v_value := nullif(sokhach._normalize_key(value),''); END IF;
    IF field='event_date' THEN v_date := sokhach._trip_date(value); v_value := v_date::text;
    ELSIF v_value IS NULL AND field<>'shipper' AND (coalesce(t.container,'')<>'' OR field='container' AND t.container IS NOT NULL)
    THEN RAISE EXCEPTION 'INVALID_TRIP_INPUT'; END IF;
    -- KIEM-TAB-01 (K4): chuỗi rỗng và NULL là cùng một giá trị "chưa có" ở ô chữ, nên không phải thay đổi.
    IF nullif(btrim(to_jsonb(t)->>field),'') IS NOT DISTINCT FROM v_value THEN RAISE EXCEPTION 'NO_CHANGE'; END IF;
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
      -- Audit 19/11/2026 (A12): cùng thứ tự kiểm như paste_trips; dòng sổ gốc không ngày cùng container, cùng tháng nợ thì vào chờ kiểm.
      ELSIF sokhach._legacy_undated_match(v_container,t.event_date)
      THEN v_reason:='BASELINE_UNDATED_MONTH';
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
CREATE OR REPLACE FUNCTION sokhach.record_mark(p jsonb) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,sokhach,pg_temp AS $$
DECLARE
 v_today date := (clock_timestamp() AT TIME ZONE 'Asia/Ho_Chi_Minh')::date;
 v_kind text := p->>'kind'; v_customer bigint; v_amount bigint; v_on date; v_key text := p->>'idempotency_key';
 v_old sokhach.contact_mark; v_row sokhach.contact_mark;
BEGIN
 IF jsonb_typeof(p)<>'object' OR v_kind IS NULL OR v_kind NOT IN ('promise','paid_claim','note')
    OR jsonb_typeof(p->'customer_id')<>'number' OR v_key IS NULL OR btrim(v_key)='' THEN RAISE EXCEPTION 'INVALID_MARK'; END IF;
 v_customer:=(p->>'customer_id')::bigint;
 -- VND là chuỗi số nguyên dương như mọi lệnh tiền (số JSON cũng nhận); chữ lạ là INVALID_MARK, không lỗi ép kiểu.
 IF p->>'amount_vnd' IS NOT NULL THEN
   IF p->>'amount_vnd' !~ '^[1-9][0-9]{0,17}$' THEN RAISE EXCEPTION 'INVALID_MARK'; END IF;
   v_amount:=(p->>'amount_vnd')::bigint;
 END IF;
 IF p->>'on_date' IS NOT NULL AND p->>'on_date' !~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$' THEN RAISE EXCEPTION 'INVALID_MARK'; END IF;
 IF p->>'on_date' IS NOT NULL THEN v_on:=(p->>'on_date')::date; END IF;
 SELECT * INTO v_old FROM sokhach.contact_mark m WHERE m.idempotency_key=v_key;
 IF FOUND THEN
   -- Bấm Lưu lặp (mất mạng rồi gửi lại): trả dấu đã ghi, không thêm dòng. Khóa dùng cho nội dung khác (khách, loại, tiền,
   -- ngày, ghi chú, tin gắn) thì từ chối, kể cả khi người dùng sửa ô sau lần gửi chưa rõ kết quả (audit 19/11/2026, A08).
   IF v_old.customer_id<>v_customer OR v_old.kind<>v_kind
      OR v_old.amount_vnd IS DISTINCT FROM v_amount OR v_old.on_date IS DISTINCT FROM v_on
      OR v_old.note IS DISTINCT FROM nullif(btrim(p->>'note'),'')
      OR v_old.conversation_id IS DISTINCT FROM p->>'conversation_id' OR v_old.message_id IS DISTINCT FROM p->>'message_id'
   THEN RAISE EXCEPTION 'IDEMPOTENCY_CONFLICT'; END IF;
   RETURN sokhach._mark_json(v_old,v_today)||jsonb_build_object('replayed',true);
 END IF;
 IF NOT EXISTS(SELECT 1 FROM sokhach.customer c WHERE c.id=v_customer) THEN RAISE EXCEPTION 'CUSTOMER_NOT_FOUND'; END IF;
 IF v_kind='note' AND (v_amount IS NOT NULL OR v_on IS NOT NULL OR p->>'note' IS NULL OR btrim(p->>'note')='') THEN
   RAISE EXCEPTION 'INVALID_MARK'; END IF;
 IF v_kind<>'note' AND (v_amount IS NULL OR v_amount<=0 OR v_on IS NULL) THEN RAISE EXCEPTION 'INVALID_MARK'; END IF;
 -- Hứa trả hẹn từ hôm nay tới một năm; khách báo đã chuyển là chuyện đã xảy ra, không sau hôm nay (giờ VN).
 IF v_kind='promise' AND (v_on<v_today OR v_on>v_today+366) THEN RAISE EXCEPTION 'INVALID_MARK_DATE'; END IF;
 IF v_kind='paid_claim' AND (v_on>v_today OR v_on<v_today-366) THEN RAISE EXCEPTION 'INVALID_MARK_DATE'; END IF;
 IF p->>'message_id' IS NOT NULL AND p->>'conversation_id' IS NULL THEN RAISE EXCEPTION 'INVALID_MARK'; END IF;
 INSERT INTO sokhach.contact_mark(customer_id,kind,amount_vnd,on_date,note,conversation_id,message_id,message_at,
     message_sender,message_excerpt,idempotency_key,created_by,created_on)
   VALUES(v_customer,v_kind,v_amount,v_on,nullif(btrim(p->>'note'),''),p->>'conversation_id',p->>'message_id',
     (p->>'message_at')::timestamptz,p->>'message_sender',p->>'message_excerpt',v_key,sokhach._actor(),v_today)
   RETURNING * INTO v_row;
 RETURN sokhach._mark_json(v_row,v_today);
END $$;
COMMIT;
