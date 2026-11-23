-- Audit SQL lõi tiền 23/11/2026 (D:\webdebit\audits\2026-11-23-web-audit\sql-findings.md, ngoài repo). Chạy lại được; không đổi bảng,
-- cột, loại event, dữ liệu hay quyền của hàm cũ. Chạy sau 2026-11-21-v7-cash-report-review.sql.
-- F1  schema_level() (mức lược đồ, app EXECUTE được), _catalog_manifest() (bảng băm hàm/view/trigger+tgenabled/index/ràng buộc) và
--     get_safety_net trả thêm khối `catalog`; v7_post_deploy_check.sql và lưới an toàn so với tools/v7_catalog_manifest.json.
-- F2  paste_trips: dòng phí lẻ không ngày vào tháng nợ của lệnh chỉ khi tháng đó mở và không sau tháng hiện tại giờ VN
--     (MONTH_LOCKED / FUTURE_DATE), như adjust_month. Dòng có ngày giữ ngoại lệ nhập bù NHAP-SHEET-01 (7).
-- F5  bốn index (event theo giờ, event theo khóa lệnh, điều chỉnh theo chuyến, phiếu theo event hủy); get_dashboard lọc event theo
--     khoảng giờ thay cho ép ngày từng dòng.
-- F8  _trip_dup_reason: một hàm tính lý do CHỜ KIỂM cho paste_trips, edit_trip_info, _change_legacy; thêm luật dòng sổ gốc đã sửa có
--     ngày (_legacy_edited_date_match). Sửa container/ngày dòng sổ gốc thành trùng chuyến web đang tính thì chuyến đó vào CHỜ KIỂM.
-- F9  paste_trips lấy khóa container của dòng Sheet trước, theo thứ tự khóa; _begin_command, _begin_offset, reallocate khóa sổ bằng
--     FOR NO KEY UPDATE.
-- F10 set_customer_archived: cờ lưu trữ qua đường lệnh có Lịch sử, chặn khi số dư khác 0 (chỉ chủ schema gọi).
-- adjust_month: thân như cũ, viết lại để bỏ ký tự CR còn trong bản trên hao (chạy từ file CRLF), cho bảng băm khớp repo.
BEGIN;
SET LOCAL ROLE sokhach_owner;
CREATE INDEX IF NOT EXISTS event_at ON sokhach.event (at);
CREATE INDEX IF NOT EXISTS event_customer_key ON sokhach.event (customer_id, idempotency_key);
CREATE INDEX IF NOT EXISTS adjustment_trip ON sokhach.adjustment (trip_id) WHERE trip_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS receipt_voided_by_event ON sokhach.receipt (voided_by_event) WHERE voided_by_event IS NOT NULL;

CREATE OR REPLACE FUNCTION sokhach._legacy_edited_date_match(p_container text, p_date date) RETURNS boolean
LANGUAGE plpgsql STABLE SET search_path = pg_catalog, sokhach, pg_temp AS $$
BEGIN
    IF coalesce(p_container,'')='' OR p_date IS NULL THEN RETURN false; END IF;
    RETURN EXISTS (SELECT 1 FROM (SELECT DISTINCT y.legacy_row_id FROM sokhach.legacy_trip_rev y
            WHERE sokhach._normalize_key(y.container)=p_container) c
        JOIN sokhach.legacy_row l ON l.id=c.legacy_row_id AND l.kind='trip'
        JOIN sokhach.cutover_customer cc ON (cc.customer_id,cc.cutover_id)=(l.customer_id,l.cutover_id) AND cc.status='active'
        CROSS JOIN LATERAL (SELECT x.event_date,x.container,x.deleted FROM sokhach.legacy_trip_rev x
            WHERE x.legacy_row_id=l.id ORDER BY x.id DESC LIMIT 1) r
        WHERE NOT r.deleted AND sokhach._normalize_key(r.container)=p_container
          AND r.event_date IS NOT NULL AND abs(r.event_date-p_date)<=3);
END $$;

CREATE OR REPLACE FUNCTION sokhach._trip_dup_reason(p_customer bigint, p_cutover bigint, p_container text, p_booking text,
    p_date date, p_exclude_trip bigint, p_batch jsonb) RETURNS text
LANGUAGE plpgsql STABLE SET search_path = pg_catalog, sokhach, pg_temp AS $$
BEGIN
    IF EXISTS (SELECT 1 FROM sokhach.baseline_trip_ref r WHERE r.cutover_id=p_cutover
        AND r.booking_norm=p_booking AND r.container_norm=p_container)
    THEN RETURN 'BASELINE_CODE_MATCH'; END IF;
    IF EXISTS (SELECT 1 FROM sokhach.baseline_trip_ref r WHERE r.cutover_id=p_cutover
        AND r.container_norm=p_container AND abs(r.event_date-p_date)<=3)
       OR sokhach._legacy_edited_date_match(p_container,p_date)
    THEN RETURN 'BASELINE_DATE_WINDOW'; END IF;
    IF sokhach._legacy_undated_match(p_container,p_date) THEN RETURN 'BASELINE_UNDATED_MONTH'; END IF;
    IF EXISTS (SELECT 1 FROM sokhach.v_trip_current t WHERE NOT t.deleted AND t.customer_id=p_customer
        AND t.id IS DISTINCT FROM p_exclude_trip
        AND sokhach._normalize_key(t.container)=p_container
        AND (sokhach._booking_key(t.booking,t.container,t.event_date)=p_booking OR abs(t.event_date-p_date)<=3))
    THEN RETURN 'WEB_DUPLICATE'; END IF;
    IF EXISTS (SELECT 1 FROM jsonb_array_elements(coalesce(p_batch,'[]'::jsonb)) r
        WHERE sokhach._normalize_key(r->>'container')=p_container
        AND (sokhach._booking_key(r->>'booking',r->>'container',(r->>'event_date')::date)=p_booking
            OR abs((r->>'event_date')::date-p_date)<=3))
    THEN RETURN 'BATCH_DUPLICATE'; END IF;
    RETURN NULL;
END $$;

CREATE OR REPLACE FUNCTION sokhach.paste_trips(customer_id bigint, expected_version bigint,
    idempotency_key text, debt_month date, trips jsonb) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, sokhach, pg_temp AS $$
DECLARE v_payload jsonb := jsonb_build_object('command','paste_trips','month',debt_month,'trips',trips);
        v_retry jsonb; v_actor text; v_ids jsonb := '[]'::jsonb;
        v_item jsonb; v_fee_item jsonb; v_id bigint; v_event bigint; v_rows jsonb := '[]'::jsonb;
        v_changes jsonb; v_date date; v_unit bigint; v_fee bigint; v_fee_total numeric; v_date_text text;
        v_fee_only boolean; v_cutover bigint; v_booking text; v_container text;
        v_reason text; v_pending jsonb := '[]'; v_lock integer;
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
    -- Audit SQL 23/11/2026 (F9): khóa container của dòng Sheet lấy trước, theo thứ tự khóa, thay vì từng dòng theo thứ tự lô trong
    -- trigger guard_sheet_cross_customer (trigger lấy lại cùng khóa, không chờ). Hai lô cùng container khác thứ tự hết kẹt chéo.
    FOR v_lock IN SELECT DISTINCT hashtext(sokhach._normalize_key(x->>'container')) FROM jsonb_array_elements(trips) x
        WHERE jsonb_typeof(x)='object' AND x->>'src' ~ '^sheet:[0-9a-f]{64}:[0-9]+$' AND nullif(x->>'container','') IS NOT NULL
        ORDER BY 1 LOOP
        PERFORM pg_advisory_xact_lock(746193,v_lock);
    END LOOP;
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
        -- FUTURE-01 áp vào V7 (29/10/2026): ngày xe nhập kho khi dán không được sau hôm nay giờ VN,
        -- cùng luật với sửa ngày tại ô (_trip_date); chuyến đồng bộ từ Sheet cũng đi qua đây.
        IF v_date > (clock_timestamp() AT TIME ZONE 'Asia/Ho_Chi_Minh')::date
        THEN RAISE EXCEPTION 'FUTURE_DATE'; END IF;
        -- Audit SQL 23/11/2026 (F2): dòng phí lẻ không ngày vào tháng nợ của lệnh, nên theo luật của adjust_month: không sau tháng
        -- hiện tại giờ VN và tháng phải mở (khóa tháng 24/10/2026). Dòng có ngày giữ ngoại lệ nhập bù NHAP-SHEET-01 (7).
        IF v_date IS NULL THEN
            IF debt_month > date_trunc('month',clock_timestamp() AT TIME ZONE 'Asia/Ho_Chi_Minh')::date
            THEN RAISE EXCEPTION 'FUTURE_DATE'; END IF;
            PERFORM sokhach._month_open(customer_id,debt_month,clock_timestamp());
        END IF;
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
            v_reason := sokhach._trip_dup_reason(paste_trips.customer_id,v_cutover,v_container,v_booking,v_date,NULL,v_rows);
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
      -- Audit 19/11/2026 (A12), 23/11/2026 (F8): cùng một hàm tính lý do như paste_trips, trừ chính chuyến đang sửa.
      v_reason:=sokhach._trip_dup_reason(edit_trip_info.customer_id,v_cutover,v_container,v_booking,t.event_date,t.id,NULL);
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
    v_fee bigint; v_cutover bigint; v_trip sokhach.v_trip_current%ROWTYPE; v_review jsonb := '[]'; v_review_reason text;
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
    -- Audit SQL 23/11/2026 (F8): sửa container/ngày của dòng sổ gốc thành trùng một chuyến web đang tính (cùng sổ, cùng container;
    -- dòng không ngày cùng tháng nợ, hoặc có ngày cách tối đa 3 ngày) thì chuyến đó vào CHỜ KIỂM, như chiều ngược lại ở edit_trip_info.
    -- Chỉ xét chuyến chưa có lý do trùng nào trước lần sửa này (cùng hàm _trip_dup_reason): chuyến người đã duyệt giữ không bị đẩy lại.
    IF NOT p_delete AND p_fee_event IS NULL AND l.kind='trip' AND field IN ('container','event_date')
       AND nullif(v_new->>'container','') IS NOT NULL THEN
      SELECT cc.cutover_id INTO v_cutover FROM sokhach.cutover_customer cc JOIN sokhach.cutover c ON c.id=cc.cutover_id
        WHERE cc.customer_id=_change_legacy.customer_id AND cc.status='active' AND c.status='active';
      v_review_reason:=CASE WHEN v_new->>'event_date' IS NULL THEN 'BASELINE_UNDATED_MONTH' ELSE 'BASELINE_DATE_WINDOW' END;
      FOR v_trip IN SELECT t.* FROM sokhach.v_trip_current t
          WHERE t.customer_id=_change_legacy.customer_id AND NOT t.deleted AND t.status='confirmed'
            AND sokhach._normalize_key(t.container)=sokhach._normalize_key(v_new->>'container')
            AND CASE WHEN v_new->>'event_date' IS NULL THEN t.debt_month=v_month
                     ELSE abs(t.event_date-(v_new->>'event_date')::date)<=3 END
          ORDER BY t.id LOOP
        IF sokhach._trip_dup_reason(v_trip.customer_id,v_cutover,sokhach._normalize_key(v_trip.container),
             sokhach._booking_key(v_trip.booking,v_trip.container,v_trip.event_date),v_trip.event_date,v_trip.id,NULL) IS NULL THEN
          PERFORM sokhach._month_open(v_trip.customer_id,v_trip.debt_month,clock_timestamp());
          v_review:=v_review||jsonb_build_array(v_trip.id);
        END IF;
      END LOOP;
    END IF;
    IF p_fee_event IS NULL THEN
    INSERT INTO sokhach.event(customer_id,kind,actor,"before","after",idempotency_key)
      VALUES(customer_id,CASE WHEN p_delete THEN 'legacy_delete' ELSE 'legacy_edit' END,sokhach._actor(),
        jsonb_build_object('legacy',v_old||jsonb_build_object('field',field,'value',v_old->field)),jsonb_build_object('legacy',v_new)
          ||CASE WHEN jsonb_array_length(v_review)>0 THEN jsonb_build_object('review_trips',v_review,'review_reason',v_review_reason)
                 ELSE '{}'::jsonb END,idempotency_key) RETURNING id INTO v_event;
    ELSE v_event:=p_fee_event; END IF;
    IF jsonb_array_length(v_review)>0 THEN
      INSERT INTO sokhach.trip_info_rev(trip_id,customer_id,debt_month,event_date,container,carrier,shipper,origin,destination,status,created_by_event)
      SELECT t.id,t.customer_id,t.debt_month,t.event_date,t.container,t.carrier,t.shipper,t.origin,t.destination,'pending_review',v_event
        FROM sokhach.v_trip_current t WHERE t.id IN (SELECT (x#>>'{}')::bigint FROM jsonb_array_elements(v_review) x);
    END IF;
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
    RETURN sokhach._finish_command(customer_id,idempotency_key,v_payload,jsonb_build_object('legacy_row_id',l.id,'deleted',p_delete,
      'review_trips',v_review,'reallocated',v_changes));
EXCEPTION WHEN numeric_value_out_of_range THEN
    IF p_fee_event IS NOT NULL THEN RAISE EXCEPTION 'FEE_AMOUNT_INVALID'; END IF;
    RAISE EXCEPTION 'INVALID_VND';
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
       AND NOT EXISTS (SELECT 1 FROM sokhach.v_trip_current t
           WHERE t.customer_id=adjust_month.customer_id AND t.debt_month=adjust_month.debt_month AND NOT t.deleted AND t.status='confirmed')
       AND NOT EXISTS (SELECT 1 FROM sokhach.v_adjustment_current a
           WHERE a.customer_id=adjust_month.customer_id AND a.debt_month=adjust_month.debt_month)
    THEN RAISE EXCEPTION 'MONTH_NOT_FOUND'; END IF;
    PERFORM sokhach._month_open(customer_id,debt_month,clock_timestamp());
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

CREATE OR REPLACE FUNCTION sokhach._begin_command(p_customer bigint, p_version bigint, p_key text, p_payload jsonb)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, sokhach, pg_temp AS $$
DECLARE v_version bigint; v_saved sokhach.idempotency%ROWTYPE;
        v_hash text := encode(sha256(convert_to(p_payload::text, 'UTF8')), 'hex');
BEGIN
    PERFORM sokhach._actor();
    IF p_key IS NULL OR btrim(p_key) = '' OR left(p_key, 9) = chr(31) || 'cutover:'
       OR p_payload IS NULL THEN
        RAISE EXCEPTION 'INVALID_COMMAND';
    END IF;
    -- Audit SQL 23/11/2026 (F9): NO KEY UPDATE đủ chặn lệnh tiền khác trên sổ, không chặn dòng con (zalo_link, contact_mark…).
    SELECT version INTO v_version FROM sokhach.customer WHERE id = p_customer FOR NO KEY UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION 'CUSTOMER_NOT_FOUND'; END IF;
    SELECT * INTO v_saved FROM sokhach.idempotency WHERE customer_id = p_customer AND key = p_key;
    IF FOUND THEN
        IF v_saved.request_hash <> v_hash THEN RAISE EXCEPTION 'IDEMPOTENCY_CONFLICT'; END IF;
        RETURN v_saved.result;
    END IF;
    IF p_version IS DISTINCT FROM v_version THEN RAISE EXCEPTION 'STALE_LEDGER'; END IF;
    RETURN NULL;
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
    SELECT version INTO v_amount FROM sokhach.customer WHERE id = p_customer FOR NO KEY UPDATE;
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
            FROM sokhach.v_trip_current t LEFT JOIN LATERAL (
                SELECT unit_price_vnd,other_fee_vnd FROM sokhach.trip_price_rev
                WHERE trip_id=t.id ORDER BY id DESC LIMIT 1) p ON true
            WHERE t.customer_id=p_customer AND NOT t.deleted AND t.status='confirmed'
            UNION ALL
            SELECT debt_month,amount_vnd FROM sokhach.v_adjustment_current WHERE customer_id=p_customer
            UNION ALL SELECT debt_month,amount_vnd FROM sokhach.v_offset_outgoing WHERE customer_id=p_customer
        ) SELECT debt_month, sum(amount_vnd)::bigint FROM charges
          GROUP BY debt_month ORDER BY debt_month
    LOOP
        v_months := array_append(v_months,v_month);
        v_left := array_append(v_left,v_due);
        v_last := v_month;
    END LOOP;
    IF v_last IS NULL THEN
        SELECT max(l.debt_month) INTO v_last FROM sokhach.receipt_line l JOIN sokhach.receipt r ON r.id=l.receipt_id
          WHERE r.customer_id=p_customer AND r.voided_on IS NULL AND l.superseded_by_event IS NULL;
    END IF;
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

CREATE OR REPLACE FUNCTION sokhach._begin_offset(p_target bigint,p_target_version bigint,
    p_source bigint,p_source_version bigint,p_key text,p_payload jsonb) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, sokhach, pg_temp AS $$
DECLARE v_saved sokhach.offset_command%ROWTYPE; v_count integer;
BEGIN
    PERFORM sokhach._actor();
    IF p_target=p_source THEN RAISE EXCEPTION 'OFFSET_SAME_BOOK'; END IF;
    IF p_key IS NULL OR btrim(p_key)='' OR p_source IS NULL OR p_target IS NULL
    THEN RAISE EXCEPTION 'INVALID_COMMAND'; END IF;
    PERFORM id FROM sokhach.customer WHERE id IN (p_source,p_target) ORDER BY id FOR NO KEY UPDATE;
    GET DIAGNOSTICS v_count=ROW_COUNT;
    IF v_count<>2 THEN RAISE EXCEPTION 'CUSTOMER_NOT_FOUND'; END IF;
    SELECT * INTO v_saved FROM sokhach.offset_command
      WHERE low_customer_id=least(p_source,p_target) AND high_customer_id=greatest(p_source,p_target)
        AND key=p_key;
    IF FOUND THEN
        IF v_saved.payload IS DISTINCT FROM p_payload THEN RAISE EXCEPTION 'IDEMPOTENCY_CONFLICT'; END IF;
        RETURN v_saved.result;
    END IF;
    IF p_source_version IS DISTINCT FROM (SELECT version FROM sokhach.customer WHERE id=p_source)
       OR p_target_version IS DISTINCT FROM (SELECT version FROM sokhach.customer WHERE id=p_target)
    THEN RAISE EXCEPTION 'STALE_LEDGER'; END IF;
    PERFORM sokhach._baseline(p_source);
    PERFORM sokhach._baseline(p_target);
    RETURN NULL;
END $$;

CREATE OR REPLACE FUNCTION sokhach.get_dashboard() RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, sokhach, pg_temp AS $$
DECLARE d date := (now() AT TIME ZONE 'Asia/Ho_Chi_Minh')::date; m date := date_trunc('month', d)::date;
BEGIN
  PERFORM sokhach._actor();
  RETURN (WITH a AS (SELECT c.id,c.name,c.commodity_id,c.transport_mode,coalesce(sum(v.outstanding_vnd),0)::bigint total
    FROM sokhach.customer c JOIN sokhach.cutover_customer cc ON cc.customer_id=c.id AND cc.status='active'
    JOIN sokhach.cutover x ON x.id=cc.cutover_id AND x.status='active' LEFT JOIN sokhach.v_outstanding_month v ON v.customer_id=c.id
    WHERE NOT c.archived GROUP BY c.id,c.name,c.commodity_id,c.transport_mode),
  p AS (SELECT t.customer_id,count(*)::int n FROM sokhach.v_trip_current t JOIN a ON a.id=t.customer_id
    LEFT JOIN LATERAL (SELECT unit_price_vnd,other_fee_vnd FROM sokhach.trip_price_rev z WHERE z.trip_id=t.id ORDER BY z.id DESC LIMIT 1) z ON true
    WHERE NOT t.deleted AND t.status='confirmed' AND z.unit_price_vnd IS NULL AND NOT ((t.container IS NULL OR t.container='') AND z.other_fee_vnd IS NOT NULL) GROUP BY t.customer_id),
  r AS (SELECT customer_id,count(*)::int n FROM sokhach.v_trip_current t JOIN a ON a.id=t.customer_id WHERE NOT t.deleted AND t.status='pending_review' GROUP BY customer_id),
  e AS (SELECT actor,coalesce(sum(jsonb_array_length(e."after"->'trips')) FILTER (WHERE kind='paste'),0)::int trips,count(*) FILTER (WHERE kind='receipt')::int receipts,
    coalesce(sum((e."after"->>'amount_vnd')::bigint) FILTER (WHERE kind='receipt'),0)::bigint received,
    count(*) FILTER (WHERE kind='void' AND EXISTS (SELECT 1 FROM sokhach.receipt z WHERE z.voided_by_event=e.id))::int voids
    FROM sokhach.event e WHERE e.at>=(d::timestamp AT TIME ZONE 'Asia/Ho_Chi_Minh') AND e.at<((d+1)::timestamp AT TIME ZONE 'Asia/Ho_Chi_Minh')
      AND (kind IN ('paste','receipt') OR (kind='void' AND EXISTS (SELECT 1 FROM sokhach.receipt z WHERE z.voided_by_event=e.id))) GROUP BY actor),
  t AS (SELECT coalesce(sum(total) FILTER (WHERE total>0),0)::bigint recv,count(*) FILTER (WHERE total>0)::int recv_n,
    coalesce(sum(total) FILTER (WHERE total<0),0)::bigint cred,count(*) FILTER (WHERE total<0)::int cred_n FROM a),
  aging AS (SELECT b.bucket,b.ord,coalesce(sum(v.outstanding_vnd),0)::bigint amount FROM (VALUES ('current',0),('1-2',1),('3-6',2),('over-6',3)) b(bucket,ord)
    LEFT JOIN sokhach.v_outstanding_month v ON v.customer_id IN (SELECT id FROM a WHERE total>0)
    AND CASE WHEN ((extract(year FROM m)-extract(year FROM v.debt_month))*12+extract(month FROM m)-extract(month FROM v.debt_month))<=0 THEN 0 WHEN ((extract(year FROM m)-extract(year FROM v.debt_month))*12+extract(month FROM m)-extract(month FROM v.debt_month))<=2 THEN 1 WHEN ((extract(year FROM m)-extract(year FROM v.debt_month))*12+extract(month FROM m)-extract(month FROM v.debt_month))<=6 THEN 2 ELSE 3 END=b.ord GROUP BY b.bucket,b.ord)
  SELECT jsonb_build_object('as_of',d::text,'receivable',jsonb_build_object('total_vnd',t.recv::text,'customers',t.recv_n),'credit',jsonb_build_object('total_vnd',t.cred::text,'customers',t.cred_n),
    'by_commodity',coalesce((SELECT jsonb_agg(jsonb_build_object('commodity',q.commodity,'transport_mode',q.transport_mode,'customers',q.n,'receivable_vnd',q.amount::text) ORDER BY q.commodity IS NULL,q.commodity COLLATE "C",q.transport_mode NULLS LAST) FROM (SELECT c.commodity_id,m.name commodity,c.transport_mode,count(*)::int n,sum(c.total)::bigint amount FROM a c LEFT JOIN sokhach.commodity m ON m.id=c.commodity_id WHERE c.total>0 GROUP BY c.commodity_id,m.name,c.transport_mode) q),'[]'::jsonb),
    'aging',(SELECT jsonb_agg(jsonb_build_object('bucket',bucket,'receivable_vnd',amount::text) ORDER BY ord) FROM aging),
    'top_debtors',coalesce((SELECT jsonb_agg(jsonb_build_object('customer_id',q.id,'name',q.name,'commodity',q.commodity,'transport_mode',q.transport_mode,'outstanding_vnd',q.total::text,'oldest_open_month',q.oldest::text) ORDER BY q.total DESC,q.name COLLATE "C",q.id) FROM (SELECT a.*,m.name commodity,min(v.debt_month) FILTER (WHERE v.outstanding_vnd>0) oldest FROM a LEFT JOIN sokhach.commodity m ON m.id=a.commodity_id LEFT JOIN sokhach.v_outstanding_month v ON v.customer_id=a.id WHERE a.total>0 GROUP BY a.id,a.name,a.commodity_id,a.transport_mode,a.total,m.name ORDER BY a.total DESC,a.name COLLATE "C",a.id LIMIT 10) q),'[]'::jsonb),
    'todo',jsonb_build_object('missing_price',coalesce((SELECT jsonb_agg(jsonb_build_object('customer_id',a.id,'name',a.name,'count',p.n) ORDER BY a.name COLLATE "C",a.id) FROM p JOIN a ON a.id=p.customer_id),'[]'::jsonb),'pending_review',coalesce((SELECT jsonb_agg(jsonb_build_object('customer_id',a.id,'name',a.name,'count',r.n) ORDER BY a.name COLLATE "C",a.id) FROM r JOIN a ON a.id=r.customer_id),'[]'::jsonb),'no_baseline',coalesce((SELECT jsonb_agg(jsonb_build_object('customer_id',c.id,'name',c.name) ORDER BY c.name COLLATE "C",c.id) FROM sokhach.customer c WHERE NOT c.archived AND NOT EXISTS (SELECT 1 FROM a WHERE a.id=c.id)),'[]'::jsonb),'credit',coalesce((SELECT jsonb_agg(jsonb_build_object('customer_id',id,'name',name,'credit_vnd',total::text) ORDER BY name COLLATE "C",id) FROM a WHERE total<0),'[]'::jsonb)),
    'today',jsonb_build_object('trips',coalesce((SELECT sum(trips) FROM e),0),'receipts',coalesce((SELECT sum(receipts) FROM e),0),'received_vnd',coalesce((SELECT sum(received) FROM e),0)::text,'voids',coalesce((SELECT sum(voids) FROM e),0),'by_actor',coalesce((SELECT jsonb_agg(jsonb_build_object('actor',actor,'trips',trips,'receipts',receipts,'received_vnd',received::text,'voids',voids) ORDER BY actor COLLATE "C") FROM e),'[]'::jsonb))) FROM t);
END $$;

CREATE OR REPLACE FUNCTION sokhach.get_safety_net(p_options jsonb) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, sokhach, pg_temp AS $$
-- LUOI-AN-TOAN-01. Chỉ chạy trong giao dịch REPEATABLE READ READ ONLY (adapter read_only=True): mọi phần thấy cùng một lúc của sổ và
-- không ghi được gì. Trả mã sổ, mã lỗi, số đếm, phiên bản, dấu vân md5; không tên khách, không số tiền.
-- p_options: event_upto (mốc kiểm 4 lượt trước), ledger_slice/ledger_slices (phần sổ so get_ledger lượt này; 0 phần là bỏ qua),
-- settle_seconds (mặc định 600).
DECLARE v_id bigint; v_total numeric; v_alloc jsonb := '[]'::jsonb; v_dash jsonb; v_debt jsonb; v_codes text[]; v_bad bigint[];
    v_archived bigint[];
    v_slice int; v_slices int; v_settle int; v_upto bigint; v_ledger jsonb; v_checked int := 0; v_wrong bigint[] := '{}';
BEGIN
    PERFORM sokhach._actor();
    IF current_setting('transaction_read_only') <> 'on'
       OR current_setting('transaction_isolation') NOT IN ('repeatable read', 'serializable') THEN
        RAISE EXCEPTION 'SNAPSHOT_REQUIRED';
    END IF;
    IF jsonb_typeof(p_options) IS DISTINCT FROM 'object' THEN RAISE EXCEPTION 'INVALID_OPTIONS'; END IF;
    v_slices := coalesce((p_options->>'ledger_slices')::int, 0);
    v_slice := coalesce((p_options->>'ledger_slice')::int, 0);
    v_settle := coalesce((p_options->>'settle_seconds')::int, 600);
    v_upto := (p_options->>'event_upto')::bigint;
    IF v_slices < 0 OR v_slice < 0 OR (v_slices > 0 AND v_slice >= v_slices) OR v_settle NOT BETWEEN 0 AND 86400 OR v_upto < 0 THEN
        RAISE EXCEPTION 'INVALID_OPTIONS';
    END IF;
    -- Kiểm 1: ba luật của _check_allocations cho mọi sổ có phiếu (dòng chia chỉ có ở sổ có phiếu).
    FOR v_id IN SELECT DISTINCT customer_id FROM sokhach.receipt ORDER BY 1 LOOP
        BEGIN
            PERFORM sokhach._check_allocations(v_id);
        EXCEPTION WHEN raise_exception THEN
            v_alloc := v_alloc || jsonb_build_array(jsonb_build_object('customer_id', v_id, 'code', SQLERRM));
        END;
    END LOOP;
    -- Kiểm 2: con số Tổng quan hiển thị so với tổng các sổ có mốc nạp đang hiệu lực (v_outstanding_month).
    v_dash := sokhach.get_dashboard();
    v_debt := sokhach.get_dashboard_debt();
    WITH books AS (
        SELECT c.id, c.archived, coalesce(sum(v.outstanding_vnd), 0)::numeric AS total
          FROM sokhach.customer c
          JOIN sokhach.cutover_customer cc ON cc.customer_id = c.id AND cc.status = 'active'
          JOIN sokhach.cutover x ON x.id = cc.cutover_id AND x.status = 'active'
          LEFT JOIN sokhach.v_outstanding_month v ON v.customer_id = c.id
         GROUP BY c.id, c.archived),
      live AS (SELECT id, total FROM books WHERE NOT archived),
      pos AS (SELECT id, total FROM live WHERE total > 0),
      listed AS (SELECT (e->>'customer_id')::bigint AS id, (e->>'outstanding_vnd')::numeric AS total
          FROM jsonb_array_elements(v_debt->'customers') e),
      list_wrong AS (SELECT coalesce(pos.id, listed.id) AS id FROM pos FULL JOIN listed ON listed.id = pos.id
          WHERE pos.total IS DISTINCT FROM listed.total),
      sums AS (SELECT (SELECT coalesce(sum(total), 0) FROM pos) AS pos_sum, (SELECT count(*) FROM pos) AS pos_n,
          (SELECT coalesce(sum(total), 0) FROM live WHERE total < 0) AS neg_sum, (SELECT count(*) FROM live WHERE total < 0) AS neg_n)
    SELECT array_remove(ARRAY[
            CASE WHEN (v_dash->'receivable'->>'total_vnd')::numeric IS DISTINCT FROM s.pos_sum THEN 'RECEIVABLE_TOTAL' END,
            CASE WHEN (v_dash->'receivable'->>'customers')::bigint IS DISTINCT FROM s.pos_n THEN 'RECEIVABLE_COUNT' END,
            CASE WHEN (v_dash->'credit'->>'total_vnd')::numeric IS DISTINCT FROM s.neg_sum THEN 'CREDIT_TOTAL' END,
            CASE WHEN (v_dash->'credit'->>'customers')::bigint IS DISTINCT FROM s.neg_n THEN 'CREDIT_COUNT' END,
            CASE WHEN (SELECT coalesce(sum((e->>'receivable_vnd')::numeric), 0) FROM jsonb_array_elements(v_dash->'by_commodity') e)
                IS DISTINCT FROM s.pos_sum THEN 'COMMODITY_TOTAL' END,
            CASE WHEN (v_debt->>'receivable_vnd')::numeric IS DISTINCT FROM s.pos_sum THEN 'DEBT_TOTAL' END,
            CASE WHEN (SELECT coalesce(sum((e->>'receivable_vnd')::numeric), 0) FROM jsonb_array_elements(v_debt->'due_tiers') e)
                IS DISTINCT FROM s.pos_sum THEN 'DEBT_TIERS' END,
            CASE WHEN EXISTS (SELECT 1 FROM list_wrong) THEN 'DEBT_LIST' END,
            CASE WHEN EXISTS (SELECT 1 FROM books WHERE archived AND total <> 0) THEN 'ARCHIVED_BALANCE' END], NULL),
        ARRAY(SELECT id FROM list_wrong ORDER BY 1), ARRAY(SELECT id FROM books WHERE archived AND total <> 0 ORDER BY 1)
      INTO v_codes, v_bad, v_archived FROM sums s;
    -- Kiểm 2, phần get_ledger: mở cả sổ tốn ~0,1 giây mỗi sổ nên mỗi lượt chỉ so một phần (mã sổ mod ledger_slices).
    IF v_slices > 0 THEN
        FOR v_id, v_total IN
            SELECT c.id, coalesce(sum(v.outstanding_vnd), 0)::numeric
              FROM sokhach.customer c
              JOIN sokhach.cutover_customer cc ON cc.customer_id = c.id AND cc.status = 'active'
              JOIN sokhach.cutover x ON x.id = cc.cutover_id AND x.status = 'active'
              LEFT JOIN sokhach.v_outstanding_month v ON v.customer_id = c.id
             WHERE c.id % v_slices = v_slice
             GROUP BY c.id ORDER BY c.id
        LOOP
            v_checked := v_checked + 1;
            IF (sokhach.get_ledger(v_id)->>'total_outstanding_vnd')::numeric IS DISTINCT FROM v_total THEN
                v_wrong := v_wrong || v_id;
            END IF;
        END LOOP;
        v_ledger := jsonb_build_object('slice', v_slice, 'slices', v_slices, 'checked', v_checked, 'customers', to_jsonb(v_wrong));
    END IF;
    RETURN jsonb_build_object('books', (SELECT count(*) FROM sokhach.customer), 'allocations', v_alloc,
        'totals', jsonb_build_object('codes', to_jsonb(v_codes), 'customers', to_jsonb(v_bad), 'archived', to_jsonb(v_archived)),
        'ledger', v_ledger,
        'fingerprints', sokhach._safety_fingerprints(), 'events', sokhach._safety_events(v_upto, make_interval(secs => v_settle)),
        -- Audit SQL 23/11/2026 (F1): bảng băm định nghĩa để v7_safety_net.py so với tools/v7_catalog_manifest.json của release.
        'catalog', sokhach._catalog_manifest());
END $$;

CREATE OR REPLACE FUNCTION sokhach.set_customer_archived(customer_id bigint, expected_version bigint, idempotency_key text,
    archived boolean) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, sokhach, pg_temp AS $$
DECLARE v_payload jsonb := jsonb_build_object('command','set_customer_archived','archived',archived);
    v_retry jsonb; v_before jsonb; v_after jsonb; v_balance numeric;
BEGIN
    v_retry := sokhach._begin_command(customer_id,expected_version,idempotency_key,v_payload);
    IF v_retry IS NOT NULL THEN RETURN v_retry; END IF;
    IF archived IS NULL THEN RAISE EXCEPTION 'INVALID_COMMAND'; END IF;
    SELECT to_jsonb(c) INTO v_before FROM sokhach.customer c WHERE c.id=set_customer_archived.customer_id;
    IF (v_before->>'archived')::boolean = archived THEN RAISE EXCEPTION 'NO_CHANGE'; END IF;
    IF archived THEN
        SELECT coalesce(sum(v.outstanding_vnd),0) INTO v_balance FROM sokhach.v_outstanding_month v
         WHERE v.customer_id=set_customer_archived.customer_id;
        IF v_balance <> 0 THEN RAISE EXCEPTION 'ARCHIVE_BALANCE_NOT_ZERO'; END IF;
    END IF;
    UPDATE sokhach.customer c SET archived=set_customer_archived.archived WHERE c.id=set_customer_archived.customer_id
        RETURNING to_jsonb(c) INTO v_after;
    INSERT INTO sokhach.event(customer_id,kind,actor,"before","after",idempotency_key)
    VALUES (customer_id,'customer_attr',sokhach._actor(),jsonb_build_object('customer',v_before),
        jsonb_build_object('customer',v_after,'archived',archived),idempotency_key);
    RETURN sokhach._finish_command(customer_id,idempotency_key,v_payload,jsonb_build_object('archived',archived));
END $$;
REVOKE ALL ON FUNCTION sokhach.set_customer_archived(bigint,bigint,text,boolean) FROM PUBLIC, sokhach_app, sokhach_reader;

CREATE OR REPLACE FUNCTION sokhach.schema_level() RETURNS integer
LANGUAGE sql IMMUTABLE SET search_path = pg_catalog, sokhach, pg_temp AS $$ SELECT 2026112301 $$;
REVOKE ALL ON FUNCTION sokhach.schema_level() FROM PUBLIC, sokhach_app, sokhach_reader;
GRANT EXECUTE ON FUNCTION sokhach.schema_level() TO sokhach_app;

CREATE OR REPLACE FUNCTION sokhach._catalog_view_text(p_def text) RETURNS text
LANGUAGE plpgsql IMMUTABLE SET search_path = pg_catalog, sokhach, pg_temp AS $$
DECLARE v_list text; v_out text := p_def;
BEGIN
    FOR v_list IN SELECT m[1] FROM regexp_matches(p_def, '(SELECT (?:x\.\w+,\s+)+x\.\w+)', 'g') m LOOP
        v_out := replace(v_out, v_list, 'SELECT ' || (SELECT string_agg(c[1], ',' ORDER BY c[1] COLLATE "C")
                                                      FROM regexp_matches(substr(v_list, 8), '(x\.\w+)', 'g') c));
    END LOOP;
    RETURN v_out;
END $$;
REVOKE ALL ON FUNCTION sokhach._catalog_view_text(text) FROM PUBLIC, sokhach_app, sokhach_reader;

CREATE OR REPLACE FUNCTION sokhach._catalog_manifest() RETURNS jsonb
LANGUAGE sql STABLE SET search_path = pg_catalog, sokhach, pg_temp AS $$
SELECT jsonb_build_object(
    'level', sokhach.schema_level(),
    'functions', (SELECT coalesce(jsonb_object_agg(p.oid::regprocedure::text,
                    md5(CASE WHEN p.prokind = 'a' THEN p.proname::text ELSE pg_get_functiondef(p.oid) END)), '{}'::jsonb)
                  FROM pg_proc p WHERE p.pronamespace = 'sokhach'::regnamespace),
    'views', (SELECT coalesce(jsonb_object_agg(c.relname, md5(sokhach._catalog_view_text(pg_get_viewdef(c.oid)))), '{}'::jsonb)
              FROM pg_class c WHERE c.relnamespace = 'sokhach'::regnamespace AND c.relkind IN ('v', 'm')),
    'triggers', (SELECT coalesce(jsonb_object_agg(c.relname || '.' || t.tgname,
                   md5(pg_get_triggerdef(t.oid)) || ':' || t.tgenabled::text), '{}'::jsonb)
                 FROM pg_trigger t JOIN pg_class c ON c.oid = t.tgrelid
                 WHERE c.relnamespace = 'sokhach'::regnamespace AND NOT t.tgisinternal),
    'indexes', (SELECT coalesce(jsonb_object_agg(ic.relname, md5(pg_get_indexdef(i.indexrelid))), '{}'::jsonb)
                FROM pg_index i JOIN pg_class c ON c.oid = i.indrelid JOIN pg_class ic ON ic.oid = i.indexrelid
                WHERE c.relnamespace = 'sokhach'::regnamespace),
    'constraints', (SELECT coalesce(jsonb_object_agg(c.relname || '.' || k.conname, md5(pg_get_constraintdef(k.oid))), '{}'::jsonb)
                    FROM pg_constraint k JOIN pg_class c ON c.oid = k.conrelid
                    WHERE k.connamespace = 'sokhach'::regnamespace AND k.contype <> 'n'))
$$;
REVOKE ALL ON FUNCTION sokhach._catalog_manifest() FROM PUBLIC, sokhach_app, sokhach_reader;

REVOKE ALL ON FUNCTION sokhach._legacy_edited_date_match(text,date) FROM PUBLIC, sokhach_app, sokhach_reader;
REVOKE ALL ON FUNCTION sokhach._trip_dup_reason(bigint,bigint,text,text,date,bigint,jsonb) FROM PUBLIC, sokhach_app, sokhach_reader;
RESET ROLE;
COMMIT;
