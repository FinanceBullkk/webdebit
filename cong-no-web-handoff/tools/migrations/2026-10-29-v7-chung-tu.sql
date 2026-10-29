-- CHUNG-TU-01: ảnh chứng từ gắn phiếu thu. Chỉ thêm bảng/hàm, không đổi tiền, phân bổ hay hàm cũ.
-- Áp sau 2026-10-29-v7-phu-phi-b-p2.sql và 2026-10-29-v7-bang-gia.sql (ràng buộc event gồm cả loại của bảng giá). Chạy lại được. Không chạy trên hao khi chưa có lệnh người dùng.
BEGIN;
SET LOCAL ROLE sokhach_owner;
-- CHUNG-TU-01: ảnh chứng từ gắn phiếu thu; chỉ thêm, gỡ có lý do, không xóa hẳn.
CREATE TABLE IF NOT EXISTS sokhach.receipt_image(
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,customer_id bigint NOT NULL REFERENCES sokhach.customer(id),receipt_id bigint NOT NULL,
 sha256 text NOT NULL CHECK(sha256 ~ '^[0-9a-f]{64}$'),content_type text NOT NULL CHECK(content_type IN('image/png','image/jpeg','image/webp')),
 data bytea NOT NULL CHECK(octet_length(data) BETWEEN 1 AND 2097152),created_by_event bigint NOT NULL,
 removed_reason text CHECK(removed_reason IS NULL OR btrim(removed_reason)<>''),removed_by_event bigint,
 CHECK((removed_reason IS NULL)=(removed_by_event IS NULL)),
 FOREIGN KEY(receipt_id,customer_id) REFERENCES sokhach.receipt(id,customer_id),
 FOREIGN KEY(created_by_event,customer_id) REFERENCES sokhach.event(id,customer_id),
 FOREIGN KEY(removed_by_event,customer_id) REFERENCES sokhach.event(id,customer_id));
ALTER TABLE sokhach.receipt_image ALTER COLUMN data SET STORAGE EXTERNAL;
CREATE UNIQUE INDEX IF NOT EXISTS receipt_image_active_unique ON sokhach.receipt_image(receipt_id,sha256) WHERE removed_by_event IS NULL;
CREATE INDEX IF NOT EXISTS receipt_image_sha256 ON sokhach.receipt_image(sha256) WHERE removed_by_event IS NULL;
CREATE INDEX IF NOT EXISTS receipt_image_customer ON sokhach.receipt_image(customer_id,receipt_id);
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
-- CHUNG-TU-01: ảnh chứng từ gắn phiếu thu. Không đổi tiền, phân bổ hay khóa tháng.
CREATE OR REPLACE FUNCTION sokhach._guard_receipt_image() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog,sokhach,pg_temp AS $$
BEGIN
 IF TG_OP='DELETE' THEN RAISE EXCEPTION 'RECEIPT_IMAGE_IMMUTABLE'; END IF;
 IF OLD.removed_by_event IS NOT NULL OR NEW.removed_by_event IS NULL
    OR (to_jsonb(NEW)-'removed_by_event'-'removed_reason') IS DISTINCT FROM (to_jsonb(OLD)-'removed_by_event'-'removed_reason')
 THEN RAISE EXCEPTION 'RECEIPT_IMAGE_IMMUTABLE'; END IF;
 RETURN NEW;
END $$;
DO $$ BEGIN IF NOT EXISTS(SELECT 1 FROM pg_trigger WHERE tgrelid='sokhach.receipt_image'::regclass AND tgname='receipt_image_guard')
 THEN CREATE TRIGGER receipt_image_guard BEFORE UPDATE OR DELETE ON sokhach.receipt_image FOR EACH ROW EXECUTE FUNCTION sokhach._guard_receipt_image(); END IF; END $$;
CREATE OR REPLACE FUNCTION sokhach._receipt_image_matches(p_sha256 text,p_exclude bigint) RETURNS jsonb
LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog,sokhach,pg_temp AS $$
 SELECT coalesce(jsonb_agg(jsonb_build_object('image_id',i.id,'customer_id',r.customer_id,'customer_name',c.name,
   'pid',r.pid,'date',r.date,'voided',r.voided_by_event IS NOT NULL) ORDER BY r.date,c.name COLLATE "C",r.pid COLLATE "C"),'[]'::jsonb)
 FROM sokhach.receipt_image i JOIN sokhach.receipt r ON r.id=i.receipt_id JOIN sokhach.customer c ON c.id=r.customer_id
 WHERE i.sha256=p_sha256 AND i.removed_by_event IS NULL AND i.id IS DISTINCT FROM p_exclude;
$$;
CREATE OR REPLACE FUNCTION sokhach.attach_receipt_image(customer_id bigint,expected_version bigint,idempotency_key text,
    pid text,content_type text,data bytea) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,sokhach,pg_temp AS $$
DECLARE v_sha text:=CASE WHEN data IS NULL THEN NULL ELSE encode(sha256(data),'hex') END;
 v_payload jsonb:=jsonb_build_object('command','attach_receipt_image','pid',pid,'content_type',content_type,'sha256',v_sha);
 v_retry jsonb; r sokhach.receipt%ROWTYPE; v_id bigint; v_event bigint; v_image jsonb; v_ok boolean;
BEGIN
 v_retry:=sokhach._begin_command(customer_id,expected_version,idempotency_key,v_payload);
 IF v_retry IS NOT NULL THEN RETURN v_retry; END IF;
 -- plpgsql đọc điều kiện IF tới chữ THEN đầu tiên, nên CASE kiểm đầu file tính riêng.
 v_ok:=data IS NOT NULL AND CASE content_type
     WHEN 'image/png' THEN substring(data FROM 1 FOR 8)='\x89504e470d0a1a0a'::bytea
     WHEN 'image/jpeg' THEN substring(data FROM 1 FOR 3)='\xffd8ff'::bytea
     WHEN 'image/webp' THEN substring(data FROM 1 FOR 4)='\x52494646'::bytea AND substring(data FROM 9 FOR 4)='\x57454250'::bytea
     ELSE false END;
 IF NOT coalesce(v_ok,false) THEN RAISE EXCEPTION 'IMAGE_INVALID'; END IF;
 IF octet_length(data)>2097152 THEN RAISE EXCEPTION 'IMAGE_TOO_LARGE'; END IF;
 SELECT * INTO r FROM sokhach.receipt WHERE receipt.customer_id=attach_receipt_image.customer_id
   AND receipt.pid=attach_receipt_image.pid FOR UPDATE;
 IF NOT FOUND THEN RAISE EXCEPTION 'RECEIPT_NOT_FOUND'; END IF;
 IF r.voided_by_event IS NOT NULL OR r.void_reason IS NOT NULL THEN RAISE EXCEPTION 'RECEIPT_ALREADY_VOID'; END IF;
 IF EXISTS(SELECT 1 FROM sokhach.receipt_image i WHERE i.receipt_id=r.id AND i.sha256=v_sha AND i.removed_by_event IS NULL)
 THEN RAISE EXCEPTION 'IMAGE_DUPLICATE'; END IF;
 IF (SELECT count(*) FROM sokhach.receipt_image i WHERE i.receipt_id=r.id AND i.removed_by_event IS NULL)>=5
 THEN RAISE EXCEPTION 'IMAGE_LIMIT'; END IF;
 v_id:=nextval(pg_get_serial_sequence('sokhach.receipt_image','id'));
 v_image:=jsonb_build_object('id',v_id,'receipt_id',r.id,'pid',r.pid,'sha256',v_sha,'content_type',content_type,
   'byte_size',octet_length(data));
 INSERT INTO sokhach.event(customer_id,kind,actor,"before","after",idempotency_key)
   VALUES(customer_id,'receipt_image',sokhach._actor(),'{}',jsonb_build_object('image',v_image),idempotency_key)
   RETURNING id INTO v_event;
 INSERT INTO sokhach.receipt_image(id,customer_id,receipt_id,sha256,content_type,data,created_by_event)
   OVERRIDING SYSTEM VALUE VALUES(v_id,customer_id,r.id,v_sha,content_type,data,v_event);
 RETURN sokhach._finish_command(customer_id,idempotency_key,v_payload,
   jsonb_build_object('image',v_image,'duplicates',sokhach._receipt_image_matches(v_sha,v_id)));
END $$;
CREATE OR REPLACE FUNCTION sokhach.remove_receipt_image(customer_id bigint,expected_version bigint,idempotency_key text,
    image_id bigint,reason text) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,sokhach,pg_temp AS $$
DECLARE v_payload jsonb:=jsonb_build_object('command','remove_receipt_image','image_id',image_id,'reason',reason);
 v_retry jsonb; i sokhach.receipt_image%ROWTYPE; r sokhach.receipt%ROWTYPE; v_event bigint; v_image jsonb;
BEGIN
 v_retry:=sokhach._begin_command(customer_id,expected_version,idempotency_key,v_payload);
 IF v_retry IS NOT NULL THEN RETURN v_retry; END IF;
 IF reason IS NULL OR btrim(reason)='' THEN RAISE EXCEPTION 'IMAGE_REMOVE_REASON_REQUIRED'; END IF;
 SELECT * INTO i FROM sokhach.receipt_image WHERE receipt_image.id=remove_receipt_image.image_id
   AND receipt_image.customer_id=remove_receipt_image.customer_id FOR UPDATE;
 IF NOT FOUND THEN RAISE EXCEPTION 'IMAGE_NOT_FOUND'; END IF;
 IF i.removed_by_event IS NOT NULL THEN RAISE EXCEPTION 'IMAGE_ALREADY_REMOVED'; END IF;
 SELECT * INTO r FROM sokhach.receipt WHERE receipt.id=i.receipt_id;
 IF r.voided_by_event IS NOT NULL OR r.void_reason IS NOT NULL THEN RAISE EXCEPTION 'RECEIPT_ALREADY_VOID'; END IF;
 v_image:=jsonb_build_object('id',i.id,'receipt_id',r.id,'pid',r.pid,'sha256',i.sha256,'content_type',i.content_type,
   'byte_size',octet_length(i.data));
 INSERT INTO sokhach.event(customer_id,kind,actor,"before","after",idempotency_key)
   VALUES(customer_id,'receipt_image_remove',sokhach._actor(),jsonb_build_object('image',v_image),
     jsonb_build_object('image',v_image||jsonb_build_object('removed',true,'reason',btrim(reason))),idempotency_key)
   RETURNING id INTO v_event;
 UPDATE sokhach.receipt_image SET removed_reason=btrim(reason),removed_by_event=v_event WHERE receipt_image.id=i.id;
 RETURN sokhach._finish_command(customer_id,idempotency_key,v_payload,jsonb_build_object('image_id',i.id,'removed',true));
END $$;
CREATE OR REPLACE FUNCTION sokhach.list_receipt_images(customer_id bigint) RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path=pg_catalog,sokhach,pg_temp AS $$
BEGIN
 IF NOT EXISTS(SELECT 1 FROM sokhach.customer c WHERE c.id=list_receipt_images.customer_id) THEN RAISE EXCEPTION 'CUSTOMER_NOT_FOUND'; END IF;
 RETURN jsonb_build_object('images',(SELECT coalesce(jsonb_agg(jsonb_build_object('id',i.id,'receipt_id',i.receipt_id,'pid',r.pid,
   'sha256',i.sha256,'content_type',i.content_type,'byte_size',octet_length(i.data),'at',e.at,'actor',e.actor) ORDER BY i.receipt_id,i.id),'[]'::jsonb)
  FROM sokhach.receipt_image i JOIN sokhach.receipt r ON r.id=i.receipt_id JOIN sokhach.event e ON e.id=i.created_by_event
  WHERE i.customer_id=list_receipt_images.customer_id AND i.removed_by_event IS NULL));
END $$;
CREATE OR REPLACE FUNCTION sokhach.get_receipt_image(customer_id bigint,image_id bigint) RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path=pg_catalog,sokhach,pg_temp AS $$
DECLARE v jsonb;
BEGIN
 SELECT jsonb_build_object('id',i.id,'content_type',i.content_type,'sha256',i.sha256,'removed',i.removed_by_event IS NOT NULL,
   'data_base64',translate(encode(i.data,'base64'),E'\n',''))
 INTO v FROM sokhach.receipt_image i WHERE i.id=get_receipt_image.image_id AND i.customer_id=get_receipt_image.customer_id;
 IF v IS NULL THEN RAISE EXCEPTION 'IMAGE_NOT_FOUND'; END IF;
 RETURN v;
END $$;
CREATE OR REPLACE FUNCTION sokhach.find_receipt_image(sha256 text) RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path=pg_catalog,sokhach,pg_temp AS $$
BEGIN
 IF find_receipt_image.sha256 IS NULL OR find_receipt_image.sha256 !~ '^[0-9a-f]{64}$' THEN RAISE EXCEPTION 'IMAGE_INVALID'; END IF;
 RETURN jsonb_build_object('matches',sokhach._receipt_image_matches(find_receipt_image.sha256,NULL));
END $$;

REVOKE ALL ON TABLE sokhach.receipt_image FROM PUBLIC,sokhach_app,sokhach_reader;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA sokhach FROM PUBLIC;
REVOKE ALL ON FUNCTION sokhach._guard_receipt_image() FROM PUBLIC,sokhach_app,sokhach_reader;
REVOKE ALL ON FUNCTION sokhach._receipt_image_matches(text,bigint) FROM PUBLIC,sokhach_app,sokhach_reader;
GRANT EXECUTE ON FUNCTION sokhach.attach_receipt_image(bigint,bigint,text,text,text,bytea) TO sokhach_app;
GRANT EXECUTE ON FUNCTION sokhach.remove_receipt_image(bigint,bigint,text,bigint,text) TO sokhach_app;
GRANT EXECUTE ON FUNCTION sokhach.list_receipt_images(bigint) TO sokhach_app,sokhach_reader;
GRANT EXECUTE ON FUNCTION sokhach.get_receipt_image(bigint,bigint) TO sokhach_app,sokhach_reader;
GRANT EXECUTE ON FUNCTION sokhach.find_receipt_image(text) TO sokhach_app,sokhach_reader;
COMMIT;
