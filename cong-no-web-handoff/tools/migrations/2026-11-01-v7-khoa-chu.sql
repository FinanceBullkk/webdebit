-- KHOA-CHU-01 (1/11/2026): tháng khóa vẫn sửa được bốn ô chữ mô tả (nơi đi, nơi đến, shipper, hãng tàu), có Lịch sử.
-- Chỉ thay thân ba hàm: edit_trip_info, _change_legacy (bản 8 tham số), resolve_sheet_conflict. Tiền, ngày, container và xóa
-- vẫn kiểm khóa tháng như cũ. Không đổi bảng, ràng buộc, loại event, dữ liệu hay quyền. Chạy sau
-- 2026-11-01-v7-chan-trung-hang-cho.sql; độc lập với 2026-11-01-v7-zalo-group.sql (không đụng các hàm này). Chạy lại được.
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
    -- KHOA-CHU-01 (1/11/2026): sửa một trong bốn ô chữ mô tả không cần tháng mở; xóa, tiền, ngày, container vẫn theo khóa.
    IF p_delete OR p_fee_event IS NOT NULL OR field IS NULL OR field NOT IN ('carrier','shipper','origin','destination') THEN
      PERFORM sokhach._month_open(customer_id,v_old_month,clock_timestamp());
    END IF;
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
       OR field NOT IN ('carrier','shipper','origin','destination','event_date','booking')
       OR decision NOT IN ('keep_web','use_sheet') OR sheet_value IS NULL
       -- Date edits must use the normal edit path; posted booking never changes.
       OR (field IN ('event_date','booking') AND decision<>'keep_web')
       OR (field='booking' AND target_kind<>'trip') THEN
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
    -- KHOA-CHU-01 (1/11/2026): lấy theo Sheet cho bốn ô chữ mô tả không cần tháng mở.
    IF decision='use_sheet' AND field NOT IN ('carrier','shipper','origin','destination') THEN
        PERFORM sokhach._month_open(customer_id,CASE WHEN target_kind='trip' THEN v_trip.debt_month
          ELSE (v_legacy->>'debt_month')::date END,clock_timestamp());
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
COMMIT;
