-- BANG-GIA-04 (13/11/2026): Nơi đến trong bảng giá không bắt buộc. Dòng Nơi đến trống là giá chung của nơi đi;
-- dòng có đúng nơi đến phủ ngày chuyến thì thắng. Chỉ thay thân hai hàm, không đổi bảng, giá chuyến hay số dư.
-- Dòng cũ còn Nơi đến trống từ 10/11 thành giá chung; giá chuyến chỉ đổi khi người dùng lưu bảng hoặc bấm điền giá.
BEGIN;
SET LOCAL ROLE sokhach_owner;
CREATE OR REPLACE FUNCTION sokhach._lookup_price(p_customer bigint,p_date date,p_origin text,p_destination text,p_shipper text) RETURNS jsonb
LANGUAGE plpgsql STABLE SET search_path=pg_catalog,sokhach,pg_temp AS $$
DECLARE v_key text:=sokhach._price_key(p_origin); v_dest text:=coalesce(sokhach._price_key(p_destination),'');
 v_use text:=''; v_loc sokhach.price_location%ROWTYPE; v_tier text; v_rate record;
BEGIN
 IF NOT EXISTS (SELECT 1 FROM sokhach.price_period WHERE customer_id=p_customer) THEN
   RETURN jsonb_build_object('reason','NO_TABLE'); END IF;
 IF p_date IS NULL THEN RETURN jsonb_build_object('reason','NO_DATE'); END IF;
 IF v_key IS NULL THEN RETURN jsonb_build_object('reason','NO_ORIGIN'); END IF;
 SELECT l.* INTO v_loc FROM sokhach.price_location l WHERE l.customer_id=p_customer AND (l.name_key=v_key
   OR EXISTS (SELECT 1 FROM sokhach.price_location_alias a WHERE a.location_id=l.id AND a.alias_key=v_key));
 IF NOT FOUND THEN RETURN jsonb_build_object('reason','UNKNOWN_LOCATION'); END IF;
 -- Q3: shipper trong danh sách TT lấy giá TT; mọi shipper khác, kể cả trống, lấy giá khách.
 v_tier:=CASE WHEN EXISTS (SELECT 1 FROM sokhach.price_tt_shipper s WHERE s.customer_id=p_customer
   AND s.shipper_key=sokhach._price_key(p_shipper)) THEN 'tt' ELSE 'khach' END;
 -- BANG-GIA-04: dòng Nơi đến trống là giá chung của nơi đi. Đợt có đúng nơi đến phủ ngày chuyến thì dùng
 -- đợt đó (thiếu nhóm giá cũng không lấy giá chung thay); không có thì dùng giá chung.
 IF v_dest<>'' AND EXISTS (SELECT 1 FROM sokhach.price_rate r JOIN sokhach.price_period p ON p.id=r.period_id
     WHERE r.location_id=v_loc.id AND r.destination_key=v_dest
       AND p.valid_from<=p_date AND (p.valid_to IS NULL OR p_date<=p.valid_to)) THEN v_use:=v_dest; END IF;
 SELECT p.valid_from,p.valid_to,r.unit_price_vnd INTO v_rate FROM sokhach.price_rate r
   JOIN sokhach.price_period p ON p.id=r.period_id
   WHERE r.location_id=v_loc.id AND r.destination_key=v_use AND r.tier=v_tier AND p.valid_from<=p_date AND (p.valid_to IS NULL OR p_date<=p.valid_to);
 IF FOUND THEN
   RETURN jsonb_build_object('unit_price_vnd',v_rate.unit_price_vnd::text,'tier',v_tier,'location',v_loc.name,'destination',p_destination,
     'any_destination',v_use='','valid_from',v_rate.valid_from,'valid_to',v_rate.valid_to);
 END IF;
 -- Có đợt phủ ngày cho kho này nhưng thiếu ô của nhóm cần dùng: không lấy giá nhóm kia thay.
 RETURN jsonb_build_object('reason',CASE WHEN NOT EXISTS (SELECT 1 FROM sokhach.price_rate r
     WHERE r.location_id=v_loc.id AND r.destination_key IN (v_dest,''))
     THEN CASE WHEN v_dest='' THEN 'NO_DESTINATION' ELSE 'UNKNOWN_DESTINATION' END
   WHEN EXISTS (SELECT 1 FROM sokhach.price_rate r
     JOIN sokhach.price_period p ON p.id=r.period_id WHERE r.location_id=v_loc.id
       AND r.destination_key=v_use
       AND p.valid_from<=p_date AND (p.valid_to IS NULL OR p_date<=p.valid_to)) THEN 'NO_RATE' ELSE 'NO_PERIOD' END,
   'tier',v_tier,'location',v_loc.name,'destination',p_destination);
END $$;

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
     -- BANG-GIA-04: Nơi đến trống (chuỗi rỗng) là giá chung của nơi đi.
     v_dest:=CASE WHEN jsonb_typeof(v_rate->'destination')='string' AND sokhach._price_key(v_rate->>'destination') IS NULL
       THEN '' ELSE sokhach._price_text(v_rate->'destination') END;
     v_dest_key:=coalesce(sokhach._price_key(v_dest),'');
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

REVOKE ALL ON FUNCTION sokhach._lookup_price(bigint,date,text,text,text) FROM PUBLIC,sokhach_app,sokhach_reader;
RESET ROLE;
COMMIT;
