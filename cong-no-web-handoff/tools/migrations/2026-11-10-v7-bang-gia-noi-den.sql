-- BANG-GIA-03: add destination to price rates; old rows stay blank and never match trips.
-- Migration changes no trip price. Later user save can reprice open-month table prices.
BEGIN;
SET LOCAL ROLE sokhach_owner;
ALTER TABLE sokhach.price_rate ADD COLUMN IF NOT EXISTS destination text NOT NULL DEFAULT '';
ALTER TABLE sokhach.price_rate ADD COLUMN IF NOT EXISTS destination_key text NOT NULL DEFAULT '';
ALTER TABLE sokhach.price_rate DROP CONSTRAINT IF EXISTS price_rate_pkey;
ALTER TABLE sokhach.price_rate ADD CONSTRAINT price_rate_pkey PRIMARY KEY(period_id,location_id,destination_key,tier);
CREATE OR REPLACE FUNCTION sokhach._price_table(p_customer bigint) RETURNS jsonb
LANGUAGE sql STABLE SET search_path=pg_catalog,sokhach,pg_temp AS $$
 SELECT jsonb_build_object(
  'tt_shippers',(SELECT coalesce(jsonb_agg(s.name ORDER BY s.shipper_key),'[]') FROM sokhach.price_tt_shipper s
     WHERE s.customer_id=p_customer),
  'locations',(SELECT coalesce(jsonb_agg(jsonb_build_object('name',l.name,'aliases',
       (SELECT coalesce(jsonb_agg(a.alias ORDER BY a.alias_key),'[]') FROM sokhach.price_location_alias a
        WHERE a.location_id=l.id)) ORDER BY l.name_key),'[]') FROM sokhach.price_location l WHERE l.customer_id=p_customer),
  'periods',(SELECT coalesce(jsonb_agg(jsonb_build_object('valid_from',p.valid_from,'valid_to',p.valid_to,'rates',
       (SELECT coalesce(jsonb_agg(jsonb_build_object('location',l.name,'destination',r.destination,'tier',r.tier,'unit_price_vnd',r.unit_price_vnd::text)
          ORDER BY l.name_key,r.destination_key,r.tier),'[]') FROM sokhach.price_rate r JOIN sokhach.price_location l ON l.id=r.location_id
        WHERE r.period_id=p.id)) ORDER BY p.valid_from,p.valid_to NULLS LAST,p.id),'[]')
     FROM sokhach.price_period p WHERE p.customer_id=p_customer))
$$;

CREATE OR REPLACE FUNCTION sokhach._lookup_price(p_customer bigint,p_date date,p_origin text,p_destination text,p_shipper text) RETURNS jsonb
LANGUAGE plpgsql STABLE SET search_path=pg_catalog,sokhach,pg_temp AS $$
DECLARE v_key text:=sokhach._price_key(p_origin); v_dest text:=sokhach._price_key(p_destination); v_loc sokhach.price_location%ROWTYPE; v_tier text; v_rate record;
BEGIN
 IF NOT EXISTS (SELECT 1 FROM sokhach.price_period WHERE customer_id=p_customer) THEN
   RETURN jsonb_build_object('reason','NO_TABLE'); END IF;
 IF p_date IS NULL THEN RETURN jsonb_build_object('reason','NO_DATE'); END IF;
 IF v_key IS NULL THEN RETURN jsonb_build_object('reason','NO_ORIGIN'); END IF;
 IF v_dest IS NULL THEN RETURN jsonb_build_object('reason','NO_DESTINATION'); END IF;
 SELECT l.* INTO v_loc FROM sokhach.price_location l WHERE l.customer_id=p_customer AND (l.name_key=v_key
   OR EXISTS (SELECT 1 FROM sokhach.price_location_alias a WHERE a.location_id=l.id AND a.alias_key=v_key));
 IF NOT FOUND THEN RETURN jsonb_build_object('reason','UNKNOWN_LOCATION'); END IF;
 -- Q3: shipper trong danh sách TT lấy giá TT; mọi shipper khác, kể cả trống, lấy giá khách.
 v_tier:=CASE WHEN EXISTS (SELECT 1 FROM sokhach.price_tt_shipper s WHERE s.customer_id=p_customer
   AND s.shipper_key=sokhach._price_key(p_shipper)) THEN 'tt' ELSE 'khach' END;
 SELECT p.valid_from,p.valid_to,r.unit_price_vnd INTO v_rate FROM sokhach.price_rate r
   JOIN sokhach.price_period p ON p.id=r.period_id
   WHERE r.location_id=v_loc.id AND r.destination_key=v_dest AND r.tier=v_tier AND p.valid_from<=p_date AND (p.valid_to IS NULL OR p_date<=p.valid_to);
 IF FOUND THEN
   RETURN jsonb_build_object('unit_price_vnd',v_rate.unit_price_vnd::text,'tier',v_tier,'location',v_loc.name,'destination',p_destination,
     'valid_from',v_rate.valid_from,'valid_to',v_rate.valid_to);
 END IF;
 -- Có đợt phủ ngày cho kho này nhưng thiếu ô của nhóm cần dùng: không lấy giá nhóm kia thay.
 RETURN jsonb_build_object('reason',CASE WHEN NOT EXISTS (SELECT 1 FROM sokhach.price_rate r
     WHERE r.location_id=v_loc.id AND r.destination_key=v_dest) THEN 'UNKNOWN_DESTINATION'
   WHEN EXISTS (SELECT 1 FROM sokhach.price_rate r
     JOIN sokhach.price_period p ON p.id=r.period_id WHERE r.location_id=v_loc.id
       AND r.destination_key=v_dest
       AND p.valid_from<=p_date AND (p.valid_to IS NULL OR p_date<=p.valid_to)) THEN 'NO_RATE' ELSE 'NO_PERIOD' END,
   'tier',v_tier,'location',v_loc.name,'destination',p_destination);
END $$;

CREATE OR REPLACE FUNCTION sokhach._price_trip_rows(p_customer bigint)
RETURNS TABLE(trip_id bigint,debt_month date,status text,unit_price_vnd bigint,other_fee_vnd bigint,
 from_table boolean,lookup jsonb,month_open boolean)
LANGUAGE sql STABLE SET search_path=pg_catalog,sokhach,pg_temp AS $$
 SELECT t.id,t.debt_month,t.status,p.unit_price_vnd,p.other_fee_vnd,
  EXISTS (SELECT 1 FROM sokhach.trip_price_source s JOIN sokhach.trip_price_rev sr ON sr.id=s.price_rev_id
    WHERE sr.trip_id=t.id AND sr.unit_price_vnd IS NOT DISTINCT FROM p.unit_price_vnd
      AND NOT EXISTS (SELECT 1 FROM sokhach.trip_price_rev x WHERE x.trip_id=t.id AND x.id>sr.id
        AND x.unit_price_vnd IS DISTINCT FROM sr.unit_price_vnd)),
  sokhach._lookup_price(p_customer,t.event_date,t.origin,t.destination,t.shipper),
  NOT coalesce(ms.locked,t.debt_month<>date_trunc('month',clock_timestamp() AT TIME ZONE 'Asia/Ho_Chi_Minh')::date)
 FROM sokhach.v_trip_current t
 LEFT JOIN LATERAL (SELECT r.unit_price_vnd,r.other_fee_vnd FROM sokhach.trip_price_rev r
   WHERE r.trip_id=t.id ORDER BY r.id DESC LIMIT 1) p ON true
 LEFT JOIN sokhach.month_state ms ON (ms.customer_id,ms.month)=(t.customer_id,t.debt_month)
 WHERE t.customer_id=p_customer AND NOT t.deleted AND coalesce(t.container,'')<>''
$$;

CREATE OR REPLACE FUNCTION sokhach.save_price_table(customer_id bigint,expected_version bigint,idempotency_key text,
 price_table jsonb) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,sokhach,pg_temp AS $$
DECLARE v_payload jsonb:=jsonb_build_object('command','save_price_table','price_table',price_table);
 v_retry jsonb; v_before jsonb; v_after jsonb; v_item jsonb; v_alias jsonb; v_rate jsonb;
 v_name text; v_key text; v_dest text; v_dest_key text; v_loc bigint; v_period bigint; v_from date; v_to date; v_amount bigint; v_repriced jsonb;
 v_locked bigint; v_no_price bigint;
BEGIN
 v_retry:=sokhach._begin_command(customer_id,expected_version,idempotency_key,v_payload);
 IF v_retry IS NOT NULL THEN RETURN v_retry; END IF;
 IF jsonb_typeof(price_table) IS DISTINCT FROM 'object'
   OR EXISTS (SELECT 1 FROM jsonb_object_keys(price_table) k WHERE k NOT IN ('tt_shippers','locations','periods'))
   OR jsonb_typeof(price_table->'tt_shippers') IS DISTINCT FROM 'array'
   OR jsonb_typeof(price_table->'locations') IS DISTINCT FROM 'array'
   OR jsonb_typeof(price_table->'periods') IS DISTINCT FROM 'array'
 THEN RAISE EXCEPTION 'INVALID_PRICE_TABLE'; END IF;
 v_before:=sokhach._price_table(customer_id);
 DELETE FROM sokhach.price_rate r WHERE r.customer_id=save_price_table.customer_id;
 DELETE FROM sokhach.price_period p WHERE p.customer_id=save_price_table.customer_id;
 DELETE FROM sokhach.price_location_alias a WHERE a.customer_id=save_price_table.customer_id;
 DELETE FROM sokhach.price_location l WHERE l.customer_id=save_price_table.customer_id;
 DELETE FROM sokhach.price_tt_shipper s WHERE s.customer_id=save_price_table.customer_id;
 FOR v_item IN SELECT x FROM jsonb_array_elements(price_table->'tt_shippers') x LOOP
   v_name:=sokhach._price_text(v_item); v_key:=sokhach._price_key(v_name);
   IF EXISTS (SELECT 1 FROM sokhach.price_tt_shipper s WHERE s.customer_id=save_price_table.customer_id AND s.shipper_key=v_key)
   THEN RAISE EXCEPTION 'PRICE_DUPLICATE_SHIPPER'; END IF;
   INSERT INTO sokhach.price_tt_shipper(customer_id,name,shipper_key) VALUES(customer_id,v_name,v_key);
 END LOOP;
 -- Tên kho và tên khác dùng chung một không gian khóa trong sổ: một cách viết chỉ trỏ một kho.
 FOR v_item IN SELECT x FROM jsonb_array_elements(price_table->'locations') x LOOP
   IF jsonb_typeof(v_item) IS DISTINCT FROM 'object'
     OR EXISTS (SELECT 1 FROM jsonb_object_keys(v_item) k WHERE k NOT IN ('name','aliases'))
     OR jsonb_typeof(coalesce(v_item->'aliases','[]')) IS DISTINCT FROM 'array'
   THEN RAISE EXCEPTION 'INVALID_PRICE_TABLE'; END IF;
   v_name:=sokhach._price_text(v_item->'name'); v_key:=sokhach._price_key(v_name);
   IF EXISTS (SELECT 1 FROM sokhach.price_location l WHERE l.customer_id=save_price_table.customer_id AND l.name_key=v_key)
     OR EXISTS (SELECT 1 FROM sokhach.price_location_alias a WHERE a.customer_id=save_price_table.customer_id AND a.alias_key=v_key)
   THEN RAISE EXCEPTION 'PRICE_DUPLICATE_ALIAS'; END IF;
   INSERT INTO sokhach.price_location(customer_id,name,name_key) VALUES(customer_id,v_name,v_key) RETURNING id INTO v_loc;
   FOR v_alias IN SELECT x FROM jsonb_array_elements(coalesce(v_item->'aliases','[]')) x LOOP
     v_name:=sokhach._price_text(v_alias); v_key:=sokhach._price_key(v_name);
     IF EXISTS (SELECT 1 FROM sokhach.price_location l WHERE l.customer_id=save_price_table.customer_id AND l.name_key=v_key)
       OR EXISTS (SELECT 1 FROM sokhach.price_location_alias a WHERE a.customer_id=save_price_table.customer_id AND a.alias_key=v_key)
     THEN RAISE EXCEPTION 'PRICE_DUPLICATE_ALIAS'; END IF;
     INSERT INTO sokhach.price_location_alias(customer_id,location_id,alias,alias_key) VALUES(customer_id,v_loc,v_name,v_key);
   END LOOP;
 END LOOP;
 FOR v_item IN SELECT x FROM jsonb_array_elements(price_table->'periods') x LOOP
   IF jsonb_typeof(v_item) IS DISTINCT FROM 'object'
     OR EXISTS (SELECT 1 FROM jsonb_object_keys(v_item) k WHERE k NOT IN ('valid_from','valid_to','rates'))
     OR jsonb_typeof(v_item->'rates') IS DISTINCT FROM 'array'
   THEN RAISE EXCEPTION 'INVALID_PRICE_TABLE'; END IF;
   v_from:=sokhach._price_date(v_item->'valid_from');
   v_to:=CASE WHEN jsonb_typeof(coalesce(v_item->'valid_to','null'))='null' THEN NULL ELSE sokhach._price_date(v_item->'valid_to') END;
   IF v_to<v_from THEN RAISE EXCEPTION 'PRICE_INVALID_PERIOD'; END IF;
   INSERT INTO sokhach.price_period(customer_id,valid_from,valid_to) VALUES(customer_id,v_from,v_to) RETURNING id INTO v_period;
   FOR v_rate IN SELECT x FROM jsonb_array_elements(v_item->'rates') x LOOP
     IF jsonb_typeof(v_rate) IS DISTINCT FROM 'object'
       OR (SELECT count(*) FROM jsonb_object_keys(v_rate) k WHERE k IN ('location','destination','tier','unit_price_vnd'))<>4
       OR (SELECT count(*) FROM jsonb_object_keys(v_rate))<>4
       OR v_rate->>'tier' IS NULL OR v_rate->>'tier' NOT IN ('khach','tt')
     THEN RAISE EXCEPTION 'INVALID_PRICE_TABLE'; END IF;
     IF jsonb_typeof(v_rate->'unit_price_vnd') IS DISTINCT FROM 'string' OR v_rate->>'unit_price_vnd' !~ '^(0|[1-9][0-9]{0,18})$'
     THEN RAISE EXCEPTION 'PRICE_INVALID_AMOUNT'; END IF;
     v_amount:=(v_rate->>'unit_price_vnd')::bigint;
     SELECT l.id INTO v_loc FROM sokhach.price_location l WHERE l.customer_id=save_price_table.customer_id
       AND l.name_key=sokhach._price_key(sokhach._price_text(v_rate->'location'));
     IF NOT FOUND THEN RAISE EXCEPTION 'PRICE_UNKNOWN_LOCATION'; END IF;
     v_dest:=sokhach._price_text(v_rate->'destination'); v_dest_key:=sokhach._price_key(v_dest);
     IF EXISTS (SELECT 1 FROM sokhach.price_rate r WHERE r.period_id=v_period AND r.location_id=v_loc AND r.destination_key=v_dest_key AND r.tier=v_rate->>'tier')
     THEN RAISE EXCEPTION 'PRICE_DUPLICATE_RATE'; END IF;
     INSERT INTO sokhach.price_rate(period_id,location_id,customer_id,destination,destination_key,tier,unit_price_vnd)
     VALUES(v_period,v_loc,customer_id,v_dest,v_dest_key,v_rate->>'tier',v_amount);
   END LOOP;
 END LOOP;
 -- Hai đợt có cùng kho và cùng nhóm giá không được chồng ngày (hai đầu đều tính).
 IF EXISTS (SELECT 1 FROM sokhach.price_rate r1 JOIN sokhach.price_period p1 ON p1.id=r1.period_id
     JOIN sokhach.price_rate r2 ON r2.location_id=r1.location_id AND r2.destination_key=r1.destination_key AND r2.tier=r1.tier AND r2.period_id>r1.period_id
     JOIN sokhach.price_period p2 ON p2.id=r2.period_id
     WHERE r1.customer_id=save_price_table.customer_id
       AND daterange(p1.valid_from,p1.valid_to,'[]') && daterange(p2.valid_from,p2.valid_to,'[]'))
 THEN RAISE EXCEPTION 'PRICE_PERIOD_OVERLAP'; END IF;
 v_after:=sokhach._price_table(customer_id);
 IF v_after=v_before THEN RAISE EXCEPTION 'NO_CHANGE'; END IF;
 INSERT INTO sokhach.event(customer_id,kind,actor,"before","after",idempotency_key)
 VALUES(customer_id,'price_table_edit',sokhach._actor(),jsonb_build_object('price_table',v_before),
   jsonb_build_object('price_table',v_after),idempotency_key);
 v_repriced:=sokhach._reprice_from_table(customer_id,idempotency_key);
 SELECT count(*) FILTER (WHERE x.lookup ? 'unit_price_vnd'),count(*) FILTER (WHERE NOT x.lookup ? 'unit_price_vnd')
   INTO v_locked,v_no_price FROM sokhach._price_trip_rows(save_price_table.customer_id) x
   WHERE x.from_table AND x.unit_price_vnd::text IS DISTINCT FROM x.lookup->>'unit_price_vnd';
 RETURN sokhach._finish_command(customer_id,idempotency_key,v_payload,
   jsonb_build_object('price_table',v_after,'affected_trips',v_locked+v_no_price,'repriced_trips',v_repriced->'trips',
     'repriced_delta_vnd',v_repriced->'delta_vnd','locked_trips',v_locked,'no_price_trips',v_no_price,
     'reallocated',v_repriced->'reallocated'));
EXCEPTION WHEN numeric_value_out_of_range THEN RAISE EXCEPTION 'PRICE_INVALID_AMOUNT';
END $$;

CREATE OR REPLACE FUNCTION sokhach.apply_price_table(customer_id bigint,expected_version bigint,idempotency_key text,
 trip_ids jsonb) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,sokhach,pg_temp AS $$
DECLARE v_payload jsonb:=jsonb_build_object('command','apply_price_table','trip_ids',trip_ids);
 v_retry jsonb; v_id bigint; t sokhach.v_trip_current%ROWTYPE; v_old sokhach.trip_price_rev%ROWTYPE;
 v_lookup jsonb; v_before jsonb:='[]'; v_after jsonb:='[]'; v_item jsonb; v_event bigint; v_rev bigint; v_changes jsonb;
 v_from jsonb;
BEGIN
 v_retry:=sokhach._begin_command(customer_id,expected_version,idempotency_key,v_payload);
 IF v_retry IS NOT NULL THEN RETURN v_retry; END IF;
 PERFORM sokhach._baseline(customer_id);
 IF jsonb_typeof(trip_ids) IS DISTINCT FROM 'array' OR jsonb_array_length(trip_ids) NOT BETWEEN 1 AND 500
   OR EXISTS (SELECT 1 FROM jsonb_array_elements(trip_ids) x WHERE jsonb_typeof(x)<>'number' OR x::text !~ '^[1-9][0-9]{0,18}$')
   OR (SELECT count(*)<>count(DISTINCT x::text) FROM jsonb_array_elements(trip_ids) x)
 THEN RAISE EXCEPTION 'INVALID_TRIPS'; END IF;
 -- BANG-GIA-01 (29/10/2026): gõ tay thắng bảng giá. Chỉ ghi chuyến chưa có đơn giá hoặc đang mang đơn giá do
 -- bảng ghi (áp lại); đơn giá gõ tay không bị bảng ghi đè, kể cả khi client gửi nhầm.
 SELECT coalesce(jsonb_object_agg(x.trip_id::text,x.from_table),'{}') INTO v_from
   FROM sokhach._price_trip_rows(apply_price_table.customer_id) x;
 FOR v_id IN SELECT x::text::bigint FROM jsonb_array_elements(trip_ids) x ORDER BY 1 LOOP
   SELECT * INTO t FROM sokhach.v_trip_current v WHERE v.id=v_id AND v.customer_id=apply_price_table.customer_id AND NOT v.deleted;
   IF NOT FOUND OR coalesce(t.container,'')='' THEN RAISE EXCEPTION 'TRIP_NOT_FOUND'; END IF;
   IF t.status<>'confirmed' THEN RAISE EXCEPTION 'TRIP_PENDING_REVIEW'; END IF;
   PERFORM sokhach._month_open(customer_id,t.debt_month,clock_timestamp());
   v_lookup:=sokhach._lookup_price(customer_id,t.event_date,t.origin,t.destination,t.shipper);
   IF NOT v_lookup ? 'unit_price_vnd' THEN RAISE EXCEPTION 'PRICE_NOT_FOUND'; END IF;
   SELECT * INTO v_old FROM sokhach.trip_price_rev r WHERE r.trip_id=v_id ORDER BY r.id DESC LIMIT 1;
   IF v_old.unit_price_vnd::text IS NOT DISTINCT FROM v_lookup->>'unit_price_vnd' THEN RAISE EXCEPTION 'NO_CHANGE'; END IF;
   IF v_old.unit_price_vnd IS NOT NULL AND NOT coalesce((v_from->>v_id::text)::boolean,false)
   THEN RAISE EXCEPTION 'PRICE_TYPED_PRICE'; END IF;
   v_before:=v_before||jsonb_build_array(jsonb_build_object('trip_id',v_id,'container',t.container,
     'unit_price_vnd',v_old.unit_price_vnd::text,'other_fee_vnd',v_old.other_fee_vnd::text));
   v_after:=v_after||jsonb_build_array(jsonb_build_object('trip_id',v_id,'container',t.container,
     'unit_price_vnd',v_lookup->>'unit_price_vnd','other_fee_vnd',v_old.other_fee_vnd::text,'rate',v_lookup));
 END LOOP;
 INSERT INTO sokhach.event(customer_id,kind,actor,"before","after",idempotency_key)
 VALUES(customer_id,'price_table_apply',sokhach._actor(),jsonb_build_object('trips',v_before),
   jsonb_build_object('trips',v_after),idempotency_key) RETURNING id INTO v_event;
 FOR v_item IN SELECT x FROM jsonb_array_elements(v_after) x LOOP
   INSERT INTO sokhach.trip_price_rev(trip_id,customer_id,unit_price_vnd,created_by_event)
   VALUES((v_item->>'trip_id')::bigint,customer_id,(v_item->>'unit_price_vnd')::bigint,v_event)
   RETURNING id INTO v_rev;
   INSERT INTO sokhach.trip_price_source(price_rev_id,customer_id,rate,created_by_event)
   VALUES(v_rev,customer_id,v_item->'rate',v_event);
   -- Phụ phí chỉ do _sync_trip_fee ghi lại từ dòng phụ phí (PHU-PHI-01), như edit_trip_price.
   PERFORM sokhach._sync_trip_fee((v_item->>'trip_id')::bigint,v_event);
 END LOOP;
 v_changes:=sokhach.reallocate(customer_id,idempotency_key);
 RETURN sokhach._finish_command(customer_id,idempotency_key,v_payload,
   jsonb_build_object('event_id',v_event,'trips',v_after,'reallocated',v_changes));
END $$;
DROP FUNCTION IF EXISTS sokhach._lookup_price(bigint,date,text,text);
REVOKE ALL ON FUNCTION sokhach._lookup_price(bigint,date,text,text,text) FROM PUBLIC,sokhach_app,sokhach_reader;
RESET ROLE;
COMMIT;
