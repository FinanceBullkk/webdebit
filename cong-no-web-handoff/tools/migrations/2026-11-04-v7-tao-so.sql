-- MAY-TAO-SO-01: máy tự tạo sổ cho khách mới, 2026-11-04.
-- Chỉ thêm một hàm ghi, cấp cho app; không đổi bảng, view, hàm cũ, quyền cũ hay dữ liệu. Chạy lại được.
-- psql -X -v ON_ERROR_STOP=1 -f this-file với quyền quản trị schema, sau khi backup.
BEGIN;
SET LOCAL ROLE sokhach_owner;
-- MAY-TAO-SO-01: sổ cho khách mới theo đúng đường nạp mốc: một mốc riêng, đủ cổng kiểm từng tháng, trong một giao dịch.
-- Mốc đã active không nhận thêm khách (guard_cutover_customer_status), nên mỗi sổ mới một mốc. Chỉ máy đối soát gọi, không có route.
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
REVOKE ALL ON FUNCTION sokhach.create_book_from_sheet(text,text,text,jsonb,jsonb,jsonb,bigint,text) FROM PUBLIC,sokhach_reader;
GRANT EXECUTE ON FUNCTION sokhach.create_book_from_sheet(text,text,text,jsonb,jsonb,jsonb,bigint,text) TO sokhach_app;
COMMIT;
