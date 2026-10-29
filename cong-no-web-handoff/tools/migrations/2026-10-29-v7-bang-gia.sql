-- BANG-GIA-01 (29/10/2026): bảng giá theo ngày hiệu lực. Chỉ thêm bảng cấu hình, nguồn giá và hàm;
-- không đổi tiền chuyến nào, không chuyển dữ liệu. Ràng buộc event có sẵn loại của CHUNG-TU-01 để áp hai migration theo thứ tự nào cũng không làm mất loại sự kiện. Áp sau 2026-10-29-v7-phu-phi-b-p2.sql; chạy lại được.
BEGIN;
SET LOCAL ROLE sokhach_owner;
ALTER TABLE sokhach.event DROP CONSTRAINT event_kind_check;
ALTER TABLE sokhach.event ADD CONSTRAINT event_kind_check CHECK (kind IN ('paste', 'price_edit', 'adjust_trip',
        'adjust_month', 'receipt', 'receipt_edit', 'void', 'reallocation', 'month_lock', 'import',
        'customer_attr', 'trip_review', 'trip_edit', 'trip_delete', 'legacy_edit', 'legacy_delete',
        'sheet_conflict_resolved', 'fee_migration', 'add_trip_fees', 'set_trip_fee_type', 'replace_trip_fee', 'void_trip_fee', 'set_book_fee_columns',
        'price_table_edit', 'price_table_apply', 'receipt_image', 'receipt_image_remove'));
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
        WHEN 'fee_migration' THEN "before" = '{}'::jsonb AND "after" ? 'trip_count' AND "after" ? 'legacy_count'
        WHEN 'add_trip_fees' THEN "before" ? 'targets' AND "after" ? 'targets'
        WHEN 'set_trip_fee_type' THEN "before" ? 'targets' AND "after" ? 'targets'
        WHEN 'replace_trip_fee' THEN "before" ? 'targets' AND "after" ? 'targets'
        WHEN 'void_trip_fee' THEN "before" ? 'targets' AND "after" ? 'targets'
        WHEN 'set_book_fee_columns' THEN "before" ? 'fee_columns' AND "after" ? 'fee_columns'
        WHEN 'price_table_edit' THEN "before" ? 'price_table' AND "after" ? 'price_table'
        WHEN 'price_table_apply' THEN "before" ? 'trips' AND "after" ? 'trips'
        WHEN 'receipt_image' THEN "before" = '{}'::jsonb AND "after" ? 'image'
        WHEN 'receipt_image_remove' THEN "before" ? 'image' AND "after" ? 'image'
        ELSE false END);

-- BANG-GIA-01 (29/10/2026): mỗi sổ một bảng giá theo ngày hiệu lực; giá TT cho shipper của TT, còn lại giá khách.
-- Bảng cấu hình thay cả bảng mỗi lần lưu (vết trước → sau nằm ở event price_table_edit); không phải dữ liệu tiền.
CREATE TABLE IF NOT EXISTS sokhach.price_tt_shipper(
 customer_id bigint NOT NULL REFERENCES sokhach.customer(id),
 name text NOT NULL CHECK(btrim(name)<>'' AND length(name)<=200),shipper_key text NOT NULL,
 PRIMARY KEY(customer_id,shipper_key));
CREATE TABLE IF NOT EXISTS sokhach.price_location(
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,customer_id bigint NOT NULL REFERENCES sokhach.customer(id),
 name text NOT NULL CHECK(btrim(name)<>'' AND length(name)<=200),name_key text NOT NULL,
 UNIQUE(customer_id,name_key),UNIQUE(id,customer_id));
CREATE TABLE IF NOT EXISTS sokhach.price_location_alias(
 customer_id bigint NOT NULL,location_id bigint NOT NULL,
 alias text NOT NULL CHECK(btrim(alias)<>'' AND length(alias)<=200),alias_key text NOT NULL,
 PRIMARY KEY(customer_id,alias_key),
 FOREIGN KEY(location_id,customer_id) REFERENCES sokhach.price_location(id,customer_id) ON DELETE CASCADE);
CREATE TABLE IF NOT EXISTS sokhach.price_period(
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,customer_id bigint NOT NULL REFERENCES sokhach.customer(id),
 valid_from date NOT NULL,valid_to date,CHECK(valid_to IS NULL OR valid_to>=valid_from),UNIQUE(id,customer_id));
CREATE TABLE IF NOT EXISTS sokhach.price_rate(
 period_id bigint NOT NULL,location_id bigint NOT NULL,customer_id bigint NOT NULL,
 tier text NOT NULL CHECK(tier IN('khach','tt')),unit_price_vnd bigint NOT NULL CHECK(unit_price_vnd>=0),
 PRIMARY KEY(period_id,location_id,tier),
 FOREIGN KEY(period_id,customer_id) REFERENCES sokhach.price_period(id,customer_id) ON DELETE CASCADE,
 FOREIGN KEY(location_id,customer_id) REFERENCES sokhach.price_location(id,customer_id) ON DELETE CASCADE);
-- Revision giá ghi từ bảng giá; dòng gõ tay/dán/Sheet không có hàng ở đây.
CREATE TABLE IF NOT EXISTS sokhach.trip_price_source(
 price_rev_id bigint PRIMARY KEY REFERENCES sokhach.trip_price_rev(id),
 customer_id bigint NOT NULL REFERENCES sokhach.customer(id),
 rate jsonb NOT NULL CHECK(jsonb_typeof(rate)='object'),
 created_by_event bigint NOT NULL REFERENCES sokhach.event(id));
DO $$ BEGIN IF NOT EXISTS(SELECT 1 FROM pg_trigger WHERE tgrelid='sokhach.trip_price_source'::regclass AND tgname='trip_price_source_immutable')
 THEN CREATE TRIGGER trip_price_source_immutable BEFORE UPDATE OR DELETE ON sokhach.trip_price_source FOR EACH ROW EXECUTE FUNCTION sokhach.reject_immutable_change(); END IF; END $$;

-- BANG-GIA-01: tra giá theo sổ, ngày xe nhập kho, kho đi và nhóm shipper. Không tra được thì trả lý do, không đoán giá.
CREATE OR REPLACE FUNCTION sokhach._price_key(p_value text) RETURNS text
LANGUAGE sql IMMUTABLE SET search_path=pg_catalog,sokhach,pg_temp AS $$
 SELECT nullif(btrim(regexp_replace(upper(coalesce(p_value,'')),
   U&'[\0009-\000D\0020\0085\00A0\1680\2000-\200A\2028\2029\202F\205F\3000]+',' ','g')),'')
$$;

CREATE OR REPLACE FUNCTION sokhach._price_table(p_customer bigint) RETURNS jsonb
LANGUAGE sql STABLE SET search_path=pg_catalog,sokhach,pg_temp AS $$
 SELECT jsonb_build_object(
  'tt_shippers',(SELECT coalesce(jsonb_agg(s.name ORDER BY s.shipper_key),'[]') FROM sokhach.price_tt_shipper s
     WHERE s.customer_id=p_customer),
  'locations',(SELECT coalesce(jsonb_agg(jsonb_build_object('name',l.name,'aliases',
       (SELECT coalesce(jsonb_agg(a.alias ORDER BY a.alias_key),'[]') FROM sokhach.price_location_alias a
        WHERE a.location_id=l.id)) ORDER BY l.name_key),'[]') FROM sokhach.price_location l WHERE l.customer_id=p_customer),
  'periods',(SELECT coalesce(jsonb_agg(jsonb_build_object('valid_from',p.valid_from,'valid_to',p.valid_to,'rates',
       (SELECT coalesce(jsonb_agg(jsonb_build_object('location',l.name,'tier',r.tier,'unit_price_vnd',r.unit_price_vnd::text)
          ORDER BY l.name_key,r.tier),'[]') FROM sokhach.price_rate r JOIN sokhach.price_location l ON l.id=r.location_id
        WHERE r.period_id=p.id)) ORDER BY p.valid_from,p.valid_to NULLS LAST,p.id),'[]')
     FROM sokhach.price_period p WHERE p.customer_id=p_customer))
$$;

CREATE OR REPLACE FUNCTION sokhach._lookup_price(p_customer bigint,p_date date,p_origin text,p_shipper text) RETURNS jsonb
LANGUAGE plpgsql STABLE SET search_path=pg_catalog,sokhach,pg_temp AS $$
DECLARE v_key text:=sokhach._price_key(p_origin); v_loc sokhach.price_location%ROWTYPE; v_tier text; v_rate record;
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
 SELECT p.valid_from,p.valid_to,r.unit_price_vnd INTO v_rate FROM sokhach.price_rate r
   JOIN sokhach.price_period p ON p.id=r.period_id
   WHERE r.location_id=v_loc.id AND r.tier=v_tier AND p.valid_from<=p_date AND (p.valid_to IS NULL OR p_date<=p.valid_to);
 IF FOUND THEN
   RETURN jsonb_build_object('unit_price_vnd',v_rate.unit_price_vnd::text,'tier',v_tier,'location',v_loc.name,
     'valid_from',v_rate.valid_from,'valid_to',v_rate.valid_to);
 END IF;
 -- Có đợt phủ ngày cho kho này nhưng thiếu ô của nhóm cần dùng: không lấy giá nhóm kia thay.
 RETURN jsonb_build_object('reason',CASE WHEN EXISTS (SELECT 1 FROM sokhach.price_rate r
     JOIN sokhach.price_period p ON p.id=r.period_id WHERE r.location_id=v_loc.id
       AND p.valid_from<=p_date AND (p.valid_to IS NULL OR p_date<=p.valid_to)) THEN 'NO_RATE' ELSE 'NO_PERIOD' END,
   'tier',v_tier,'location',v_loc.name);
END $$;

-- Giá theo bảng của từng chuyến có container; from_table = đơn giá hiện tại do bảng giá ghi.
CREATE OR REPLACE FUNCTION sokhach._price_trip_rows(p_customer bigint)
RETURNS TABLE(trip_id bigint,debt_month date,status text,unit_price_vnd bigint,other_fee_vnd bigint,
 from_table boolean,lookup jsonb,month_open boolean)
LANGUAGE sql STABLE SET search_path=pg_catalog,sokhach,pg_temp AS $$
 SELECT t.id,t.debt_month,t.status,p.unit_price_vnd,p.other_fee_vnd,
  EXISTS (SELECT 1 FROM sokhach.trip_price_source s JOIN sokhach.trip_price_rev sr ON sr.id=s.price_rev_id
    WHERE sr.trip_id=t.id AND sr.unit_price_vnd IS NOT DISTINCT FROM p.unit_price_vnd
      AND NOT EXISTS (SELECT 1 FROM sokhach.trip_price_rev x WHERE x.trip_id=t.id AND x.id>sr.id
        AND x.unit_price_vnd IS DISTINCT FROM sr.unit_price_vnd)),
  sokhach._lookup_price(p_customer,t.event_date,t.origin,t.shipper),
  NOT coalesce(ms.locked,t.debt_month<>date_trunc('month',clock_timestamp() AT TIME ZONE 'Asia/Ho_Chi_Minh')::date)
 FROM sokhach.v_trip_current t
 LEFT JOIN LATERAL (SELECT r.unit_price_vnd,r.other_fee_vnd FROM sokhach.trip_price_rev r
   WHERE r.trip_id=t.id ORDER BY r.id DESC LIMIT 1) p ON true
 LEFT JOIN sokhach.month_state ms ON (ms.customer_id,ms.month)=(t.customer_id,t.debt_month)
 WHERE t.customer_id=p_customer AND NOT t.deleted AND coalesce(t.container,'')<>''
$$;

CREATE OR REPLACE FUNCTION sokhach.get_price_table(customer_id bigint) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,sokhach,pg_temp AS $$
DECLARE v_version bigint;
BEGIN
 PERFORM sokhach._actor();
 SELECT c.version INTO v_version FROM sokhach.customer c WHERE c.id=get_price_table.customer_id;
 IF NOT FOUND THEN RAISE EXCEPTION 'CUSTOMER_NOT_FOUND'; END IF;
 -- Shipper đang có trong sổ và nhóm giá đang áp: để soát tên viết lệch so với danh sách TT.
 RETURN jsonb_build_object('customer_id',customer_id,'version',v_version,
  'price_table',sokhach._price_table(customer_id),
  'book_shippers',(SELECT coalesce(jsonb_agg(jsonb_build_object('name',x.name,'tier',x.tier,'trip_count',x.n)
      ORDER BY x.tier,x.name),'[]') FROM (
    SELECT min(btrim(t.shipper)) AS name,count(*) AS n,
      CASE WHEN EXISTS (SELECT 1 FROM sokhach.price_tt_shipper s WHERE s.customer_id=get_price_table.customer_id
        AND s.shipper_key=sokhach._price_key(t.shipper)) THEN 'tt' ELSE 'khach' END AS tier
    FROM sokhach.v_trip_current t WHERE t.customer_id=get_price_table.customer_id AND NOT t.deleted
      AND sokhach._price_key(t.shipper) IS NOT NULL GROUP BY sokhach._price_key(t.shipper),3) x));
END $$;

CREATE OR REPLACE FUNCTION sokhach.get_price_status(customer_id bigint) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,sokhach,pg_temp AS $$
DECLARE v_version bigint;
BEGIN
 PERFORM sokhach._actor();
 SELECT c.version INTO v_version FROM sokhach.customer c WHERE c.id=get_price_status.customer_id;
 IF NOT FOUND THEN RAISE EXCEPTION 'CUSTOMER_NOT_FOUND'; END IF;
 RETURN (WITH r AS (
   SELECT x.*,x.lookup->>'unit_price_vnd' AS table_price,
     x.status='confirmed' AND x.month_open AND x.unit_price_vnd IS NULL AND x.lookup ? 'unit_price_vnd' AS ready,
     x.unit_price_vnd IS NOT NULL AND x.lookup ? 'unit_price_vnd'
       AND x.unit_price_vnd::text<>x.lookup->>'unit_price_vnd' AS differs
   FROM sokhach._price_trip_rows(get_price_status.customer_id) x)
  SELECT jsonb_build_object('customer_id',get_price_status.customer_id,'version',v_version,
   'has_table',EXISTS (SELECT 1 FROM sokhach.price_period p WHERE p.customer_id=get_price_status.customer_id),
   'trips',coalesce(jsonb_agg(jsonb_build_object('trip_id',r.trip_id,'unit_price_vnd',r.unit_price_vnd::text,
       'from_table',r.from_table,'lookup',r.lookup,'ready',r.ready,'differs',r.differs) ORDER BY r.trip_id),'[]'),
   'ready_count',count(*) FILTER (WHERE r.ready),
   -- Chuyến chưa có giá chưa tính tiền; ghi đơn giá thì cộng thêm đơn giá + phụ phí (trống = 0 theo V7-BE).
   'ready_total_vnd',coalesce(sum(r.table_price::bigint+coalesce(r.other_fee_vnd,0)) FILTER (WHERE r.ready),0)::text,
   'ready_months',coalesce(jsonb_agg(DISTINCT r.debt_month) FILTER (WHERE r.ready),'[]'),
   'reapply_count',count(*) FILTER (WHERE r.differs AND r.from_table AND r.status='confirmed' AND r.month_open))
  FROM r);
END $$;

CREATE OR REPLACE FUNCTION sokhach._price_text(p_value jsonb) RETURNS text
LANGUAGE plpgsql IMMUTABLE SET search_path=pg_catalog,sokhach,pg_temp AS $$
BEGIN
 IF jsonb_typeof(p_value) IS DISTINCT FROM 'string' OR btrim(p_value#>>'{}')='' OR length(p_value#>>'{}')>200
 THEN RAISE EXCEPTION 'INVALID_PRICE_TABLE'; END IF;
 RETURN btrim(p_value#>>'{}');
END $$;

CREATE OR REPLACE FUNCTION sokhach._price_date(p_value jsonb) RETURNS date
LANGUAGE plpgsql IMMUTABLE SET search_path=pg_catalog,sokhach,pg_temp AS $$
DECLARE v date;
BEGIN
 IF jsonb_typeof(p_value) IS DISTINCT FROM 'string' OR p_value#>>'{}' !~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$'
 THEN RAISE EXCEPTION 'PRICE_INVALID_PERIOD'; END IF;
 BEGIN v:=(p_value#>>'{}')::date;
 EXCEPTION WHEN invalid_datetime_format OR datetime_field_overflow THEN RAISE EXCEPTION 'PRICE_INVALID_PERIOD'; END;
 IF to_char(v,'YYYY-MM-DD')<>p_value#>>'{}' THEN RAISE EXCEPTION 'PRICE_INVALID_PERIOD'; END IF;
 RETURN v;
END $$;

-- Thay cả bảng giá của sổ trong một lệnh; không đổi giá chuyến nào đã ghi (affected_trips chỉ đếm để mời áp lại).
CREATE OR REPLACE FUNCTION sokhach.save_price_table(customer_id bigint,expected_version bigint,idempotency_key text,
 price_table jsonb) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,sokhach,pg_temp AS $$
DECLARE v_payload jsonb:=jsonb_build_object('command','save_price_table','price_table',price_table);
 v_retry jsonb; v_before jsonb; v_after jsonb; v_item jsonb; v_alias jsonb; v_rate jsonb;
 v_name text; v_key text; v_loc bigint; v_period bigint; v_from date; v_to date; v_amount bigint; v_affected bigint;
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
       OR (SELECT count(*) FROM jsonb_object_keys(v_rate) k WHERE k IN ('location','tier','unit_price_vnd'))<>3
       OR (SELECT count(*) FROM jsonb_object_keys(v_rate))<>3
       OR v_rate->>'tier' IS NULL OR v_rate->>'tier' NOT IN ('khach','tt')
     THEN RAISE EXCEPTION 'INVALID_PRICE_TABLE'; END IF;
     IF jsonb_typeof(v_rate->'unit_price_vnd') IS DISTINCT FROM 'string' OR v_rate->>'unit_price_vnd' !~ '^(0|[1-9][0-9]{0,18})$'
     THEN RAISE EXCEPTION 'PRICE_INVALID_AMOUNT'; END IF;
     v_amount:=(v_rate->>'unit_price_vnd')::bigint;
     SELECT l.id INTO v_loc FROM sokhach.price_location l WHERE l.customer_id=save_price_table.customer_id
       AND l.name_key=sokhach._price_key(sokhach._price_text(v_rate->'location'));
     IF NOT FOUND THEN RAISE EXCEPTION 'PRICE_UNKNOWN_LOCATION'; END IF;
     IF EXISTS (SELECT 1 FROM sokhach.price_rate r WHERE r.period_id=v_period AND r.location_id=v_loc AND r.tier=v_rate->>'tier')
     THEN RAISE EXCEPTION 'PRICE_DUPLICATE_RATE'; END IF;
     INSERT INTO sokhach.price_rate(period_id,location_id,customer_id,tier,unit_price_vnd)
     VALUES(v_period,v_loc,customer_id,v_rate->>'tier',v_amount);
   END LOOP;
 END LOOP;
 -- Hai đợt có cùng kho và cùng nhóm giá không được chồng ngày (hai đầu đều tính).
 IF EXISTS (SELECT 1 FROM sokhach.price_rate r1 JOIN sokhach.price_period p1 ON p1.id=r1.period_id
     JOIN sokhach.price_rate r2 ON r2.location_id=r1.location_id AND r2.tier=r1.tier AND r2.period_id>r1.period_id
     JOIN sokhach.price_period p2 ON p2.id=r2.period_id
     WHERE r1.customer_id=save_price_table.customer_id
       AND daterange(p1.valid_from,p1.valid_to,'[]') && daterange(p2.valid_from,p2.valid_to,'[]'))
 THEN RAISE EXCEPTION 'PRICE_PERIOD_OVERLAP'; END IF;
 v_after:=sokhach._price_table(customer_id);
 IF v_after=v_before THEN RAISE EXCEPTION 'NO_CHANGE'; END IF;
 INSERT INTO sokhach.event(customer_id,kind,actor,"before","after",idempotency_key)
 VALUES(customer_id,'price_table_edit',sokhach._actor(),jsonb_build_object('price_table',v_before),
   jsonb_build_object('price_table',v_after),idempotency_key);
 SELECT count(*) INTO v_affected FROM sokhach._price_trip_rows(save_price_table.customer_id) x
   WHERE x.from_table AND x.unit_price_vnd::text IS DISTINCT FROM x.lookup->>'unit_price_vnd';
 RETURN sokhach._finish_command(customer_id,idempotency_key,v_payload,
   jsonb_build_object('price_table',v_after,'affected_trips',v_affected));
EXCEPTION WHEN numeric_value_out_of_range THEN RAISE EXCEPTION 'PRICE_INVALID_AMOUNT';
END $$;

-- Ghi đơn giá theo bảng cho các chuyến chọn: server tra lại, một event, phân bổ lại một lần; giữ nguyên phụ phí.
CREATE OR REPLACE FUNCTION sokhach.apply_price_table(customer_id bigint,expected_version bigint,idempotency_key text,
 trip_ids jsonb) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,sokhach,pg_temp AS $$
DECLARE v_payload jsonb:=jsonb_build_object('command','apply_price_table','trip_ids',trip_ids);
 v_retry jsonb; v_id bigint; t sokhach.v_trip_current%ROWTYPE; v_old sokhach.trip_price_rev%ROWTYPE;
 v_lookup jsonb; v_before jsonb:='[]'; v_after jsonb:='[]'; v_item jsonb; v_event bigint; v_rev bigint; v_changes jsonb;
BEGIN
 v_retry:=sokhach._begin_command(customer_id,expected_version,idempotency_key,v_payload);
 IF v_retry IS NOT NULL THEN RETURN v_retry; END IF;
 PERFORM sokhach._baseline(customer_id);
 IF jsonb_typeof(trip_ids) IS DISTINCT FROM 'array' OR jsonb_array_length(trip_ids) NOT BETWEEN 1 AND 500
   OR EXISTS (SELECT 1 FROM jsonb_array_elements(trip_ids) x WHERE jsonb_typeof(x)<>'number' OR x::text !~ '^[1-9][0-9]{0,18}$')
   OR (SELECT count(*)<>count(DISTINCT x::text) FROM jsonb_array_elements(trip_ids) x)
 THEN RAISE EXCEPTION 'INVALID_TRIPS'; END IF;
 FOR v_id IN SELECT x::text::bigint FROM jsonb_array_elements(trip_ids) x ORDER BY 1 LOOP
   SELECT * INTO t FROM sokhach.v_trip_current v WHERE v.id=v_id AND v.customer_id=apply_price_table.customer_id AND NOT v.deleted;
   IF NOT FOUND OR coalesce(t.container,'')='' THEN RAISE EXCEPTION 'TRIP_NOT_FOUND'; END IF;
   IF t.status<>'confirmed' THEN RAISE EXCEPTION 'TRIP_PENDING_REVIEW'; END IF;
   PERFORM sokhach._month_open(customer_id,t.debt_month,clock_timestamp());
   v_lookup:=sokhach._lookup_price(customer_id,t.event_date,t.origin,t.shipper);
   IF NOT v_lookup ? 'unit_price_vnd' THEN RAISE EXCEPTION 'PRICE_NOT_FOUND'; END IF;
   SELECT * INTO v_old FROM sokhach.trip_price_rev r WHERE r.trip_id=v_id ORDER BY r.id DESC LIMIT 1;
   IF v_old.unit_price_vnd::text IS NOT DISTINCT FROM v_lookup->>'unit_price_vnd' THEN RAISE EXCEPTION 'NO_CHANGE'; END IF;
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

REVOKE ALL ON ALL FUNCTIONS IN SCHEMA sokhach FROM PUBLIC;
REVOKE ALL ON FUNCTION sokhach._price_key(text),sokhach._price_table(bigint),sokhach._lookup_price(bigint,date,text,text),
 sokhach._price_trip_rows(bigint),sokhach._price_text(jsonb),sokhach._price_date(jsonb) FROM PUBLIC,sokhach_app,sokhach_reader;
GRANT EXECUTE ON FUNCTION sokhach.save_price_table(bigint,bigint,text,jsonb) TO sokhach_app;
GRANT EXECUTE ON FUNCTION sokhach.apply_price_table(bigint,bigint,text,jsonb) TO sokhach_app;
GRANT EXECUTE ON FUNCTION sokhach.get_price_table(bigint) TO sokhach_app,sokhach_reader;
GRANT EXECUTE ON FUNCTION sokhach.get_price_status(bigint) TO sokhach_app,sokhach_reader;
COMMIT;
