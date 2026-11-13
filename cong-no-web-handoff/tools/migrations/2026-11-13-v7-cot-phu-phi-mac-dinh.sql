-- COT-PHU-PHI-01 (13/11/2026): bỏ giới hạn 3 cột phụ phí riêng mỗi sổ; bảy cột theo debit note là mặc định cho mọi sổ.
-- Thứ tự theo chứng từ: Lưu bãi (Storage), Ghép (Trucking), Điện (Generator), Neo (Overstay), Health + KĐ (HC fee),
-- Phí hủy (Cancellation), Sửa bill (AMD). Chỉ đổi cấu hình hiển thị: không đổi dòng phụ phí, tiền, số dư hay version sổ.
BEGIN;
SET LOCAL ROLE sokhach_owner;
ALTER TABLE sokhach.book_fee_column DROP CONSTRAINT IF EXISTS book_fee_column_position_check;
ALTER TABLE sokhach.book_fee_column ADD CONSTRAINT book_fee_column_position_check CHECK(position>0);
ALTER TABLE sokhach.fee_type ADD COLUMN IF NOT EXISTS default_position integer UNIQUE CHECK(default_position>0);
INSERT INTO sokhach.fee_type(name,kind,sign,system_key,sort) VALUES
 ('Lưu bãi','service','positive',NULL,8),('Phí hủy','service','positive',NULL,9),('Sửa bill','service','positive',NULL,10)
 ON CONFLICT(name_key) DO NOTHING;
UPDATE sokhach.fee_type SET default_position=NULL WHERE default_position IS NOT NULL;
UPDATE sokhach.fee_type f SET default_position=d.n
  FROM (VALUES('lưu bãi',1),('ghép',2),('điện',3),('neo',4),('health + kđ',5),('phí hủy',6),('sửa bill',7)) d(k,n)
 WHERE f.name_key=d.k AND f.active AND f.system_key IS NULL;

CREATE OR REPLACE FUNCTION sokhach.set_book_fee_columns(customer_id bigint,expected_version bigint,idempotency_key text,
 fee_type_ids jsonb) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,sokhach,pg_temp AS $$
DECLARE v_payload jsonb:=jsonb_build_object('command','set_book_fee_columns','fee_type_ids',fee_type_ids);
 v_retry jsonb; v_before jsonb; v_type jsonb; v_seen bigint[]:='{}';
BEGIN
 BEGIN v_retry:=sokhach._begin_command(customer_id,expected_version,idempotency_key,v_payload);
 EXCEPTION WHEN raise_exception THEN
   IF SQLERRM='STALE_LEDGER' THEN RAISE EXCEPTION 'VERSION_CONFLICT'; ELSE RAISE; END IF;
 END;
 IF v_retry IS NOT NULL THEN RETURN v_retry; END IF;
 IF jsonb_typeof(fee_type_ids) IS DISTINCT FROM 'array' THEN RAISE EXCEPTION 'INVALID_COMMAND'; END IF;
 -- COT-PHU-PHI-01: không giới hạn số cột riêng.
 FOR v_type IN SELECT x FROM jsonb_array_elements(fee_type_ids) x LOOP
   IF jsonb_typeof(v_type)<>'number' OR v_type::text !~ '^[1-9][0-9]*$' OR v_type::text::bigint=ANY(v_seen)
   THEN RAISE EXCEPTION 'INVALID_COMMAND'; END IF;
   PERFORM 1 FROM sokhach.fee_type WHERE id=v_type::text::bigint AND active AND system_key IS DISTINCT FROM 'initial' FOR SHARE;
   IF NOT FOUND THEN RAISE EXCEPTION 'FEE_TYPE_INACTIVE'; END IF;
   v_seen:=array_append(v_seen,v_type::text::bigint);
 END LOOP;
 SELECT coalesce(jsonb_agg(fee_type_id ORDER BY position),'[]') INTO v_before FROM sokhach.book_fee_column b
   WHERE b.customer_id=set_book_fee_columns.customer_id;
 INSERT INTO sokhach.event(customer_id,kind,actor,"before","after",idempotency_key)
 VALUES(customer_id,'set_book_fee_columns',sokhach._actor(),jsonb_build_object('fee_columns',v_before),
   jsonb_build_object('fee_columns',fee_type_ids),idempotency_key);
 DELETE FROM sokhach.book_fee_column b WHERE b.customer_id=set_book_fee_columns.customer_id;
 INSERT INTO sokhach.book_fee_column(customer_id,fee_type_id,position)
 SELECT customer_id,x::text::bigint,n FROM jsonb_array_elements(fee_type_ids) WITH ORDINALITY a(x,n);
 RETURN sokhach._finish_command(customer_id,idempotency_key,v_payload,jsonb_build_object('fee_columns',fee_type_ids));
EXCEPTION WHEN numeric_value_out_of_range THEN RAISE EXCEPTION 'INVALID_COMMAND';
END $$;

-- MAY-TAO-SO-01 + COT-PHU-PHI-01: sổ mới có sẵn các cột mặc định.
CREATE OR REPLACE FUNCTION sokhach.create_book_from_sheet(
 book_name text, commodity_name text, book_mode text, openings jsonb, legacy jsonb, month_checks jsonb,
 control_total bigint, report_sha256 text
) RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,sokhach,pg_temp AS $$
DECLARE v_actor text:=sokhach._actor(); v_commodity bigint; v_customer bigint; v_cutover bigint;
BEGIN
 IF book_name IS NULL OR btrim(book_name)='' OR book_name<>btrim(book_name) OR length(book_name)>200
 THEN RAISE EXCEPTION 'INVALID_BOOK_NAME'; END IF;
 IF report_sha256 IS NULL OR report_sha256 !~ '^[0-9a-fA-F]{64}$' OR control_total IS NULL
 THEN RAISE EXCEPTION 'INVALID_CUTOVER_INPUT'; END IF;
 -- Bảng khách không có ràng buộc tên duy nhất: khóa để hai lượt cùng lúc không tạo trùng.
 PERFORM pg_advisory_xact_lock(hashtext('sokhach.create_book_from_sheet'));
 IF EXISTS(SELECT 1 FROM sokhach.customer c WHERE lower(c.name)=lower(book_name))
 THEN RAISE EXCEPTION 'BOOK_EXISTS'; END IF;
 IF commodity_name IS NOT NULL THEN
  INSERT INTO sokhach.commodity(name) VALUES(commodity_name) ON CONFLICT (name) DO NOTHING;
  SELECT m.id INTO v_commodity FROM sokhach.commodity m WHERE m.name=commodity_name;
 END IF;
 INSERT INTO sokhach.customer(name,commodity_id,transport_mode) VALUES(book_name,v_commodity,book_mode)
 RETURNING id INTO v_customer;
 INSERT INTO sokhach.book_fee_column(customer_id,fee_type_id,position)
 SELECT v_customer,f.id,row_number() OVER (ORDER BY f.default_position)
   FROM sokhach.fee_type f WHERE f.default_position IS NOT NULL AND f.active;
 INSERT INTO sokhach.cutover(name,source,source_sha256,frozen_at,control_total_vnd,created_by)
 VALUES('Sổ mới theo Sheet','Sheet, máy tạo sổ (MAY-TAO-SO-01)',report_sha256,now(),control_total,v_actor)
 RETURNING id INTO v_cutover;
 PERFORM sokhach.import_cutover(v_customer,0,'tao-so-import',v_cutover,openings,legacy,month_checks,control_total,report_sha256);
 PERFORM sokhach.verify_cutover_customer(v_customer,v_cutover,1,'tao-so-verify',NULL);
 PERFORM sokhach.verify_cutover(v_cutover,'tao-so-verify-moc',NULL);
 PERFORM sokhach.activate_cutover(v_cutover,'tao-so-activate-moc',NULL);
 PERFORM sokhach.activate_cutover_customer(v_customer,v_cutover,2,'tao-so-activate',NULL);
 INSERT INTO sokhach.baseline_trip_ref(cutover_id,booking_norm,container_norm,event_date)
 SELECT v_cutover,sokhach._booking_key(NULL,l.display->>'container',nullif(l.display->>'date','')::date),
  sokhach._normalize_key(l.display->>'container'),nullif(l.display->>'date','')::date
 FROM sokhach.legacy_row l
 WHERE l.cutover_id=v_cutover AND l.kind='trip' AND sokhach._normalize_key(l.display->>'container')<>'';
 -- paste_trips đòi mốc có tham chiếu; tab không có container thì một dòng đánh dấu, không trùng container thật nào.
 IF NOT FOUND THEN
  INSERT INTO sokhach.baseline_trip_ref(cutover_id,booking_norm,container_norm,event_date)
  VALUES(v_cutover,'SO-MOI','SO-MOI',NULL);
 END IF;
 RETURN jsonb_build_object('customer_id',v_customer,'cutover_id',v_cutover,
  'version',(SELECT c.version FROM sokhach.customer c WHERE c.id=v_customer));
END $$;

-- Mọi sổ hiện có nhận đủ bảy cột mặc định theo thứ tự chứng từ; cột riêng khác mặc định (nếu có) giữ lại, xếp sau.
CREATE TEMP TABLE cot_moi ON COMMIT DROP AS
SELECT customer_id,fee_type_id,row_number() OVER (PARTITION BY customer_id ORDER BY k1,k2) AS position FROM (
  SELECT c.id customer_id,f.id fee_type_id,f.default_position k1,0 k2
    FROM sokhach.customer c CROSS JOIN sokhach.fee_type f WHERE f.default_position IS NOT NULL AND f.active
  UNION ALL
  SELECT b.customer_id,b.fee_type_id,1000000,b.position FROM sokhach.book_fee_column b
    JOIN sokhach.fee_type f ON f.id=b.fee_type_id WHERE f.default_position IS NULL OR NOT f.active) s;
DELETE FROM sokhach.book_fee_column;
INSERT INTO sokhach.book_fee_column(customer_id,fee_type_id,position) SELECT customer_id,fee_type_id,position FROM cot_moi;
COMMIT;
