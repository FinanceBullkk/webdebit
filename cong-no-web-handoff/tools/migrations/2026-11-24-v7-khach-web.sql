-- KHACH-WEB-01 (24/11/2026, người dùng chọn "Quản lý tạo, lưu trên web"): quản lý tạo sổ khách mới trên web và gán tên chủ hàng
-- trên booking vào sổ, để chuyến booking của khách đó tự vào đúng sổ mà không cần tab Sheet. Thêm bảng booking_name, hai lệnh
-- set_booking_name và create_customer, hàm phụ _booking_names; list_customers trả thêm booking_names và archived. Không đổi tiền, phân bổ, khóa
-- tháng, hàm ghi tiền hay dữ liệu cũ. Không tăng schema_level: chỉ thêm bảng và hàm, bảng băm hàm của release đã bắt được DB thiếu
-- bản này. Chạy lại được. Chạy sau 2026-11-23-v7-so-gon.sql.
BEGIN;
SET LOCAL ROLE sokhach_owner;
CREATE TABLE IF NOT EXISTS sokhach.booking_name (
    name text PRIMARY KEY CHECK (name = btrim(name) AND name <> '' AND char_length(name) <= 200 AND position('  ' IN name) = 0
                                 AND name !~ '[[:cntrl:]]' AND name !~ U&'[\0080-\009F\00A0\00AD\1680\180E\2000-\200F\2028-\202F\205F-\206F\3000\FEFF]'
                                 AND name = normalize(name, NFC) AND name = upper(name)),
    customer_id bigint NOT NULL REFERENCES sokhach.customer(id),
    created_by text NOT NULL CHECK (btrim(created_by) <> ''),
    created_at timestamp with time zone NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS booking_name_customer ON sokhach.booking_name (customer_id);
COMMENT ON TABLE sokhach.booking_name IS 'KHACH-WEB-01: tên chủ hàng trên booking (cột "Chủ hàng (chuẩn)" của CONT_NGUON, "CHỦ HÀNG" của CONT_BO) ứng với một sổ; một tên chỉ một sổ. Web viết hoa, bỏ khoảng trắng thừa trước khi ghi; không nhận ký tự điều khiển hay khoảng trắng lạ (NBSP, ký tự vô hình). Không tham gia tính tiền.';
REVOKE ALL ON TABLE sokhach.booking_name FROM PUBLIC, sokhach_app, sokhach_reader;

CREATE OR REPLACE FUNCTION sokhach._booking_names(p_customer bigint) RETURNS jsonb
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, sokhach, pg_temp AS $$
    SELECT coalesce(jsonb_agg(b.name ORDER BY b.name COLLATE "C"), '[]'::jsonb) FROM sokhach.booking_name b WHERE b.customer_id = p_customer
$$;
REVOKE ALL ON FUNCTION sokhach._booking_names(bigint) FROM PUBLIC, sokhach_app, sokhach_reader;

-- KHACH-WEB-01: gán (remove=false) hay bỏ (remove=true) một tên chủ hàng booking của một sổ. Một tên chỉ ứng một sổ
-- (BOOKING_NAME_TAKEN); gán lại tên đã có hay bỏ tên sổ không có là NO_CHANGE. Lịch sử: customer_attr với danh sách tên trước → sau.
-- Không đổi tiền; phiên bản sổ tăng như mọi lệnh để lệnh khác đang mở trên sổ biết sổ vừa đổi.
CREATE OR REPLACE FUNCTION sokhach.set_booking_name(customer_id bigint, expected_version bigint, idempotency_key text, name text, remove boolean)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, sokhach, pg_temp AS $$
DECLARE v_payload jsonb := jsonb_build_object('command','set_booking_name','name',name,'remove',remove);
 v_retry jsonb; v_owner bigint; v_customer jsonb; v_before jsonb; v_after jsonb;
BEGIN
 v_retry := sokhach._begin_command(customer_id, expected_version, idempotency_key, v_payload);
 IF v_retry IS NOT NULL THEN RETURN v_retry; END IF;
 IF remove IS NULL OR name IS NULL OR name <> btrim(name) OR name = '' OR char_length(name) > 200 OR position('  ' IN name) > 0
    OR name ~ '[[:cntrl:]]' OR name ~ U&'[\0080-\009F\00A0\00AD\1680\180E\2000-\200F\2028-\202F\205F-\206F\3000\FEFF]' OR name <> normalize(name, NFC) OR name <> upper(name)
 THEN RAISE EXCEPTION 'INVALID_BOOKING_NAME'; END IF;
 -- Khóa sổ của _begin_command chỉ chặn trong một sổ: hai sổ cùng gán một tên cùng lúc thì khóa theo tên.
 PERFORM pg_advisory_xact_lock(hashtextextended('booking_name:' || set_booking_name.name, 0));
 SELECT b.customer_id INTO v_owner FROM sokhach.booking_name b WHERE b.name = set_booking_name.name;
 SELECT to_jsonb(c) INTO v_customer FROM sokhach.customer c WHERE c.id = set_booking_name.customer_id;
 -- Sổ đã lưu trữ không nhận chuyến mới nên không gán thêm tên; bỏ tên vẫn được để dọn.
 IF NOT remove AND (v_customer->>'archived')::boolean THEN RAISE EXCEPTION 'CUSTOMER_ARCHIVED'; END IF;
 v_before := sokhach._booking_names(set_booking_name.customer_id);
 IF remove THEN
  IF v_owner IS DISTINCT FROM set_booking_name.customer_id THEN RAISE EXCEPTION 'NO_CHANGE'; END IF;
  DELETE FROM sokhach.booking_name b WHERE b.name = set_booking_name.name;
 ELSE
  IF v_owner = set_booking_name.customer_id THEN RAISE EXCEPTION 'NO_CHANGE'; END IF;
  IF v_owner IS NOT NULL THEN RAISE EXCEPTION 'BOOKING_NAME_TAKEN'; END IF;
  INSERT INTO sokhach.booking_name(name, customer_id, created_by)
  VALUES (set_booking_name.name, set_booking_name.customer_id, sokhach._actor());
 END IF;
 v_after := sokhach._booking_names(set_booking_name.customer_id);
 INSERT INTO sokhach.event(customer_id, kind, actor, "before", "after", idempotency_key)
 VALUES (set_booking_name.customer_id, 'customer_attr', sokhach._actor(),
  jsonb_build_object('customer', v_customer, 'booking_names', v_before),
  jsonb_build_object('customer', v_customer, 'booking_names', v_after,
   CASE WHEN remove THEN 'booking_name_removed' ELSE 'booking_name_added' END, set_booking_name.name),
  idempotency_key);
 RETURN sokhach._finish_command(set_booking_name.customer_id, idempotency_key, v_payload, jsonb_build_object('booking_names', v_after));
END $$;
REVOKE ALL ON FUNCTION sokhach.set_booking_name(bigint,bigint,text,text,boolean) FROM PUBLIC, sokhach_reader;
GRANT EXECUTE ON FUNCTION sokhach.set_booking_name(bigint,bigint,text,text,boolean) TO sokhach_app;

-- KHACH-WEB-01: quản lý tạo sổ khách mới trên web. Khách mới chưa có nợ: mốc riêng với một số dư đầu 0 của tháng tạo (giờ VN) và
-- một dòng kiểm tháng toàn 0, qua đủ chuỗi cổng import → verify → activate như create_book_from_sheet (MAY-TAO-SO-01), cùng khóa
-- tư vấn với hàm đó nên máy và người không tạo trùng tên. Rồi gán từng tên booking bằng set_booking_name (mỗi tên một dòng Lịch sử).
-- Bấm lại cùng idempotency_key với cùng nội dung trả kết quả lần đầu; khác nội dung là IDEMPOTENCY_CONFLICT. Tên sổ phải sạch như tên
-- tab Sheet xuất ra file (NFC, không khoảng trắng đôi hay lạ, không / \ ? * [ ] : '), không thì INVALID_BOOK_NAME. Tên sổ trùng một sổ có
-- sẵn theo khóa gộp mọi khóa tên của các máy (bỏ các dấu đó, gộp khoảng trắng, không phân biệt hoa thường) là BOOK_EXISTS, để máy đối
-- soát, bảng ghép giá và hàng chờ không gặp hai sổ một tên. Mặt hàng phải có trong danh mục (INVALID_COMMODITY). Tên booking đã ở sổ
-- khác là BOOKING_NAME_TAKEN; lỗi nào cũng không tạo gì.
CREATE OR REPLACE FUNCTION sokhach.create_customer(book_name text, commodity_name text, book_mode text, booking_names jsonb, idempotency_key text)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, sokhach, pg_temp AS $$
DECLARE v_actor text := sokhach._actor(); v_commodity bigint; v_customer bigint; v_cutover bigint;
 v_month date := date_trunc('month', clock_timestamp() AT TIME ZONE 'Asia/Ho_Chi_Minh')::date;
 v_key text; v_hash text; v_sha text; v_saved sokhach.idempotency%ROWTYPE; v_name text; v_n int := 0; v_result jsonb; v_book_key text;
BEGIN
 IF idempotency_key IS NULL OR btrim(idempotency_key) = '' OR char_length(idempotency_key) > 200 THEN RAISE EXCEPTION 'INVALID_COMMAND'; END IF;
 v_key := 'create_customer:' || idempotency_key;
 v_hash := encode(sha256(convert_to(jsonb_build_object('command','create_customer','book_name',book_name,'commodity_name',commodity_name,
   'book_mode',book_mode,'booking_names',booking_names)::text, 'UTF8')), 'hex');
 PERFORM pg_advisory_xact_lock(hashtext('sokhach.create_book_from_sheet'));
 SELECT * INTO v_saved FROM sokhach.idempotency i WHERE i.key = v_key ORDER BY i.customer_id LIMIT 1;
 IF FOUND THEN
  IF v_saved.request_hash <> v_hash THEN RAISE EXCEPTION 'IDEMPOTENCY_CONFLICT'; END IF;
  RETURN v_saved.result;
 END IF;
 IF book_name IS NULL OR btrim(book_name) = '' OR book_name <> btrim(book_name) OR char_length(book_name) > 200
    OR position('  ' IN book_name) > 0 OR book_name ~ '[[:cntrl:]]' OR book_name ~ U&'[\0080-\009F\00A0\00AD\1680\180E\2000-\200F\2028-\202F\205F-\206F\3000\FEFF]'
    OR book_name <> normalize(book_name, NFC) OR translate(book_name, '/\?*[]:''', '') <> book_name
 THEN RAISE EXCEPTION 'INVALID_BOOK_NAME'; END IF;
 IF book_mode IS NULL OR book_mode NOT IN ('CANG','BO')
    OR (commodity_name IS NOT NULL AND (btrim(commodity_name) = '' OR commodity_name <> btrim(commodity_name) OR length(commodity_name) > 80))
    OR jsonb_typeof(booking_names) IS DISTINCT FROM 'array'
 THEN RAISE EXCEPTION 'INVALID_COMMAND'; END IF;
 -- Tách khỏi điều kiện trên: OR không hứa thứ tự, hàm mảng gặp giá trị không phải mảng thì lỗi.
 IF jsonb_array_length(booking_names) > 20
    OR EXISTS (SELECT 1 FROM jsonb_array_elements(booking_names) x(v) WHERE jsonb_typeof(x.v) <> 'string')
 THEN RAISE EXCEPTION 'INVALID_COMMAND'; END IF;
 IF (SELECT count(DISTINCT x.v) <> count(*) FROM jsonb_array_elements_text(booking_names) x(v))
 THEN RAISE EXCEPTION 'INVALID_COMMAND'; END IF;
 v_book_key := lower(btrim(regexp_replace(translate(normalize(book_name, NFC), '/\?*[]:''', ''), U&'[\0009-\000D\0020\0085\00A0\1680\2000-\200A\2028\2029\202F\205F\3000]+', ' ', 'g')) COLLATE "pg_c_utf8");
 IF EXISTS (SELECT 1 FROM sokhach.customer c WHERE lower(btrim(regexp_replace(translate(normalize(c.name, NFC), '/\?*[]:''', ''), U&'[\0009-\000D\0020\0085\00A0\1680\2000-\200A\2028\2029\202F\205F\3000]+', ' ', 'g')) COLLATE "pg_c_utf8") = v_book_key)
 THEN RAISE EXCEPTION 'BOOK_EXISTS'; END IF;
 IF EXISTS (SELECT 1 FROM sokhach.booking_name b WHERE b.name IN (SELECT jsonb_array_elements_text(booking_names)))
 THEN RAISE EXCEPTION 'BOOKING_NAME_TAKEN'; END IF;
 -- Chỉ mặt hàng có sẵn trong danh mục: gõ tự do thì danh mục thêm nhóm lạ và sổ không bao giờ trùng mặt hàng booking để tự dán.
 IF commodity_name IS NOT NULL THEN
  SELECT m.id INTO v_commodity FROM sokhach.commodity m WHERE m.name = commodity_name;
  IF NOT FOUND THEN RAISE EXCEPTION 'INVALID_COMMODITY'; END IF;
 END IF;
 INSERT INTO sokhach.customer(name, commodity_id, transport_mode) VALUES (book_name, v_commodity, book_mode) RETURNING id INTO v_customer;
 INSERT INTO sokhach.book_fee_column(customer_id, fee_type_id, position)
 SELECT v_customer, f.id, row_number() OVER (ORDER BY f.default_position)
   FROM sokhach.fee_type f WHERE f.default_position IS NOT NULL AND f.active;
 v_sha := encode(sha256(convert_to(v_key, 'UTF8')), 'hex');
 INSERT INTO sokhach.cutover(name, source, source_sha256, frozen_at, control_total_vnd, created_by)
 VALUES ('Sổ mới tạo trên web', 'Web, quản lý tạo sổ (KHACH-WEB-01)', v_sha, now(), 0, v_actor)
 RETURNING id INTO v_cutover;
 PERFORM sokhach.import_cutover(v_customer, 0, 'khach-web-import', v_cutover,
  jsonb_build_array(jsonb_build_object('debt_month', v_month, 'amount_vnd', 0, 'source_tab', 'WEB', 'source_row', 1)), '[]'::jsonb,
  jsonb_build_array(jsonb_build_object('debt_month', v_month, 'opening_anchor_vnd', 0, 'source_cumulative_vnd', 0,
   'replay_cumulative_vnd', 0, 'bucket_vnd', 0, 'standard_bucket_vnd', 0, 'standard_source_ref', 'Khách mới tạo trên web, chưa có nợ',
   'standard_source_sha256', v_sha, 'source_evidence_sha256', v_sha, 'exception_codes', '[]'::jsonb,
   'source_charge_vnd', 0, 'source_receipt_vnd', 0)),
  0, v_sha);
 PERFORM sokhach.verify_cutover_customer(v_customer, v_cutover, 1, 'khach-web-verify', NULL);
 PERFORM sokhach.verify_cutover(v_cutover, 'khach-web-verify-moc', NULL);
 PERFORM sokhach.activate_cutover(v_cutover, 'khach-web-activate-moc', NULL);
 PERFORM sokhach.activate_cutover_customer(v_customer, v_cutover, 2, 'khach-web-activate', NULL);
 -- paste_trips đòi mốc có tham chiếu chuyến; sổ mới không có chuyến cũ nên một dòng đánh dấu, như sổ máy tạo không có container.
 INSERT INTO sokhach.baseline_trip_ref(cutover_id, booking_norm, container_norm, event_date) VALUES (v_cutover, 'SO-MOI', 'SO-MOI', NULL);
 FOR v_name IN SELECT x.v FROM jsonb_array_elements_text(booking_names) WITH ORDINALITY x(v, n) ORDER BY x.n LOOP
  v_n := v_n + 1;
  PERFORM sokhach.set_booking_name(v_customer, (SELECT c.version FROM sokhach.customer c WHERE c.id = v_customer),
   'khach-web-ten-' || v_n, v_name, false);
 END LOOP;
 v_result := jsonb_build_object('customer_id', v_customer, 'cutover_id', v_cutover, 'booking_names', sokhach._booking_names(v_customer),
  'version', (SELECT c.version FROM sokhach.customer c WHERE c.id = v_customer));
 INSERT INTO sokhach.idempotency(customer_id, key, request_hash, result) VALUES (v_customer, v_key, v_hash, v_result);
 RETURN v_result;
END $$;
REVOKE ALL ON FUNCTION sokhach.create_customer(text,text,text,jsonb,text) FROM PUBLIC, sokhach_reader;
GRANT EXECUTE ON FUNCTION sokhach.create_customer(text,text,text,jsonb,text) TO sokhach_app;

-- list_customers (MH-01 23/10/2026) trả thêm booking_names của mỗi sổ (KHACH-WEB-01); các trường cũ giữ nguyên.
CREATE OR REPLACE FUNCTION sokhach.list_customers() RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, sokhach, pg_temp AS $$
BEGIN
    PERFORM sokhach._actor();
    RETURN (SELECT jsonb_build_object('customers',coalesce(jsonb_agg(
        jsonb_build_object('id',id,'name',name,'status',status,
                           'commodity',commodity,'transport_mode',transport_mode,'booking_names',booking_names,'archived',archived)
        ORDER BY name COLLATE "C",id),'[]'::jsonb))
      FROM (SELECT c.id,c.name,
                   CASE WHEN cc.status='active' AND co.status='active'
                        THEN 'active' ELSE 'NO_BASELINE' END AS status,
                   m.name AS commodity,c.transport_mode,sokhach._booking_names(c.id) AS booking_names,c.archived
              FROM sokhach.customer c
              LEFT JOIN sokhach.commodity m ON m.id=c.commodity_id
              LEFT JOIN sokhach.cutover_customer cc ON cc.customer_id=c.id
              LEFT JOIN sokhach.cutover co ON co.id=cc.cutover_id) q);
END $$;
RESET ROLE;
COMMIT;
