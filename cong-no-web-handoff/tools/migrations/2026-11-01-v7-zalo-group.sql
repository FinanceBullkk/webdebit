-- ZALO-GROUP-01 (2026-11-01): gắn group Zalo ↔ sổ (zalo_link) và dấu tin hứa trả / khách báo đã chuyển / ghi chú
-- (contact_mark, cũng là B2 Hứa trả của TRANG-KHACH-01). Chỉ THÊM bảng/hàm ghi chú, NGOÀI đường tiền: không VND vào
-- số dư, không khóa tháng, không phân bổ, không bump version, không đổi hàm hay bảng cũ. Chạy lại được.
-- Áp sau 2026-11-01-v7-chan-trung-hang-cho.sql.
BEGIN;
SET LOCAL ROLE sokhach_owner;
CREATE TABLE IF NOT EXISTS sokhach.zalo_link (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    conversation_id text NOT NULL CHECK (conversation_id ~ '^[0-9a-f]{64}$'),
    customer_id bigint NOT NULL REFERENCES sokhach.customer(id),
    linked_by text NOT NULL CHECK (btrim(linked_by) <> ''),
    linked_at timestamptz NOT NULL DEFAULT now(),
    unlinked_by text CHECK (unlinked_by IS NULL OR btrim(unlinked_by) <> ''),
    unlinked_at timestamptz,
    unlink_reason text CHECK (unlink_reason IS NULL OR btrim(unlink_reason) <> ''),
    CHECK ((unlinked_at IS NULL) = (unlinked_by IS NULL) AND (unlinked_at IS NULL) = (unlink_reason IS NULL))
);
CREATE UNIQUE INDEX IF NOT EXISTS zalo_link_active ON sokhach.zalo_link (conversation_id, customer_id) WHERE unlinked_at IS NULL;
CREATE INDEX IF NOT EXISTS zalo_link_customer ON sokhach.zalo_link (customer_id) WHERE unlinked_at IS NULL;
COMMENT ON TABLE sokhach.zalo_link IS 'ZALO-GROUP-01: group Zalo (id băm của gói web) gắn với sổ; nhiều–nhiều, bỏ gắn giữ vết; không tham gia tính tiền.';

CREATE TABLE IF NOT EXISTS sokhach.contact_mark (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id bigint NOT NULL REFERENCES sokhach.customer(id),
    kind text NOT NULL CHECK (kind IN ('promise', 'paid_claim', 'note')),
    amount_vnd bigint CHECK (amount_vnd IS NULL OR amount_vnd > 0),
    on_date date,
    note text CHECK (note IS NULL OR (btrim(note) <> '' AND char_length(note) <= 500)),
    conversation_id text CHECK (conversation_id IS NULL OR conversation_id ~ '^[0-9a-f]{64}$'),
    message_id text CHECK (message_id IS NULL OR message_id ~ '^[0-9A-Za-z_-]{1,128}$'),
    message_at timestamptz,
    message_sender text CHECK (message_sender IS NULL OR char_length(message_sender) <= 200),
    message_excerpt text CHECK (message_excerpt IS NULL OR char_length(message_excerpt) <= 300),
    idempotency_key text NOT NULL UNIQUE CHECK (btrim(idempotency_key) <> '' AND char_length(idempotency_key) <= 200),
    created_by text NOT NULL CHECK (btrim(created_by) <> ''),
    created_at timestamptz NOT NULL DEFAULT now(),
    created_on date NOT NULL,
    cancelled_by text CHECK (cancelled_by IS NULL OR btrim(cancelled_by) <> ''),
    cancelled_at timestamptz,
    cancel_reason text CHECK (cancel_reason IS NULL OR btrim(cancel_reason) <> ''),
    CHECK ((kind = 'note' AND amount_vnd IS NULL AND on_date IS NULL AND note IS NOT NULL)
        OR (kind <> 'note' AND amount_vnd IS NOT NULL AND on_date IS NOT NULL)),
    CHECK (message_id IS NULL OR conversation_id IS NOT NULL),
    CHECK ((cancelled_at IS NULL) = (cancelled_by IS NULL) AND (cancelled_at IS NULL) = (cancel_reason IS NULL))
);
CREATE INDEX IF NOT EXISTS contact_mark_customer ON sokhach.contact_mark (customer_id, created_at DESC);
CREATE INDEX IF NOT EXISTS contact_mark_conversation ON sokhach.contact_mark (conversation_id) WHERE conversation_id IS NOT NULL;
COMMENT ON TABLE sokhach.contact_mark IS 'ZALO-GROUP-01/TRANG-KHACH-01 B2: dấu hứa trả, khách báo đã chuyển, ghi chú (có thể gắn một tin Zalo); trạng thái tính khi đọc; không tham gia tính tiền.';
-- ZALO-GROUP-01: gắn group Zalo ↔ sổ, dấu tin (hứa trả, khách báo đã chuyển, ghi chú). Ghi chú ngoài đường tiền:
-- không VND vào số dư, không khóa tháng, không phân bổ, không bump version. Trạng thái dấu tính khi đọc từ phiếu thu chưa hủy.
CREATE OR REPLACE FUNCTION sokhach.link_zalo(p_conversation text, p_customer bigint) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,sokhach,pg_temp AS $$
DECLARE v sokhach.zalo_link;
BEGIN
 IF p_conversation IS NULL OR p_conversation !~ '^[0-9a-f]{64}$' THEN RAISE EXCEPTION 'INVALID_LINK'; END IF;
 IF NOT EXISTS(SELECT 1 FROM sokhach.customer c WHERE c.id=p_customer) THEN RAISE EXCEPTION 'CUSTOMER_NOT_FOUND'; END IF;
 INSERT INTO sokhach.zalo_link(conversation_id,customer_id,linked_by)
   VALUES(p_conversation,p_customer,sokhach._actor())
   ON CONFLICT (conversation_id,customer_id) WHERE unlinked_at IS NULL DO NOTHING;
 SELECT * INTO v FROM sokhach.zalo_link l WHERE l.conversation_id=p_conversation AND l.customer_id=p_customer AND l.unlinked_at IS NULL;
 RETURN jsonb_build_object('conversation_id',v.conversation_id,'customer_id',v.customer_id,
   'customer_name',(SELECT c.name FROM sokhach.customer c WHERE c.id=v.customer_id),'linked_by',v.linked_by,'linked_at',v.linked_at);
END $$;
CREATE OR REPLACE FUNCTION sokhach.unlink_zalo(p_conversation text, p_customer bigint, p_reason text) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,sokhach,pg_temp AS $$
BEGIN
 IF p_reason IS NULL OR btrim(p_reason)='' THEN RAISE EXCEPTION 'REASON_REQUIRED'; END IF;
 UPDATE sokhach.zalo_link l SET unlinked_by=sokhach._actor(),unlinked_at=now(),unlink_reason=btrim(p_reason)
   WHERE l.conversation_id=p_conversation AND l.customer_id=p_customer AND l.unlinked_at IS NULL;
 IF NOT FOUND THEN RAISE EXCEPTION 'LINK_NOT_FOUND'; END IF;
 RETURN jsonb_build_object('conversation_id',p_conversation,'customer_id',p_customer,'unlinked',true);
END $$;
CREATE OR REPLACE FUNCTION sokhach.get_zalo_links() RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path=pg_catalog,sokhach,pg_temp AS $$
BEGIN
 RETURN jsonb_build_object('links',(SELECT coalesce(jsonb_agg(jsonb_build_object(
    'conversation_id',l.conversation_id,'customer_id',l.customer_id,'customer_name',c.name,
    'linked_by',l.linked_by,'linked_at',l.linked_at) ORDER BY l.conversation_id,c.name,l.customer_id),'[]'::jsonb)
  FROM sokhach.zalo_link l JOIN sokhach.customer c ON c.id=l.customer_id WHERE l.unlinked_at IS NULL));
END $$;
-- Trạng thái một dấu, chỉ đọc phiếu thu chưa hủy của đúng sổ:
--  hứa trả: kept (phiếu từ ngày ghi tới hẹn đủ số hứa), missed (quá hẹn chưa đủ), pending;
--  khách báo đã chuyển: received (có phiếu đúng số, ngày trong [báo − 3, báo + 7]), not_seen (quá báo + 3), waiting.
CREATE OR REPLACE FUNCTION sokhach._mark_json(m sokhach.contact_mark, p_today date) RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path=pg_catalog,sokhach,pg_temp AS $$
DECLARE v_status text; v_paid bigint; v_pid text;
BEGIN
 IF m.cancelled_at IS NOT NULL THEN v_status:='cancelled';
 ELSIF m.kind='promise' THEN
   SELECT coalesce(sum(r.amount_vnd),0) INTO v_paid FROM sokhach.receipt r
     WHERE r.customer_id=m.customer_id AND r.voided_on IS NULL AND r.date BETWEEN m.created_on AND m.on_date;
   v_status:=CASE WHEN v_paid>=m.amount_vnd THEN 'kept' WHEN p_today>m.on_date THEN 'missed' ELSE 'pending' END;
 ELSIF m.kind='paid_claim' THEN
   SELECT r.pid INTO v_pid FROM sokhach.receipt r
     WHERE r.customer_id=m.customer_id AND r.voided_on IS NULL AND r.amount_vnd=m.amount_vnd
       AND r.date BETWEEN m.on_date-3 AND m.on_date+7 ORDER BY r.date,r.pid LIMIT 1;
   v_status:=CASE WHEN v_pid IS NOT NULL THEN 'received' WHEN p_today>m.on_date+3 THEN 'not_seen' ELSE 'waiting' END;
 END IF;
 RETURN jsonb_build_object('id',m.id,'customer_id',m.customer_id,'kind',m.kind,'amount_vnd',m.amount_vnd::text,'on_date',m.on_date,
   'note',m.note,'conversation_id',m.conversation_id,'message_id',m.message_id,'message_at',m.message_at,
   'message_sender',m.message_sender,'message_excerpt',m.message_excerpt,'created_by',m.created_by,'created_at',m.created_at,
   'created_on',m.created_on,'cancelled_by',m.cancelled_by,'cancelled_at',m.cancelled_at,'cancel_reason',m.cancel_reason,
   'status',v_status,'paid_vnd',v_paid::text,'receipt_pid',v_pid);
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
   -- Bấm Lưu lặp (mất mạng rồi gửi lại): trả dấu đã ghi, không thêm dòng; khóa dùng cho dấu khác thì từ chối.
   IF v_old.customer_id<>v_customer OR v_old.kind<>v_kind THEN RAISE EXCEPTION 'IDEMPOTENCY_CONFLICT'; END IF;
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
CREATE OR REPLACE FUNCTION sokhach.cancel_mark(p_id bigint, p_reason text) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,sokhach,pg_temp AS $$
DECLARE v_row sokhach.contact_mark;
BEGIN
 IF p_reason IS NULL OR btrim(p_reason)='' THEN RAISE EXCEPTION 'REASON_REQUIRED'; END IF;
 SELECT * INTO v_row FROM sokhach.contact_mark m WHERE m.id=p_id FOR UPDATE;
 IF NOT FOUND THEN RAISE EXCEPTION 'MARK_NOT_FOUND'; END IF;
 IF v_row.cancelled_at IS NOT NULL THEN RAISE EXCEPTION 'MARK_ALREADY_CANCELLED'; END IF;
 UPDATE sokhach.contact_mark m SET cancelled_by=sokhach._actor(),cancelled_at=now(),cancel_reason=btrim(p_reason)
   WHERE m.id=p_id RETURNING * INTO v_row;
 RETURN sokhach._mark_json(v_row,(clock_timestamp() AT TIME ZONE 'Asia/Ho_Chi_Minh')::date);
END $$;
-- Đúng một trong hai: dấu của một sổ (thẻ Trao đổi) hoặc của một group (nhãn trong chat). Mới nhất trước.
CREATE OR REPLACE FUNCTION sokhach.get_marks(p_customer bigint, p_conversation text) RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path=pg_catalog,sokhach,pg_temp AS $$
DECLARE v_today date := (clock_timestamp() AT TIME ZONE 'Asia/Ho_Chi_Minh')::date;
BEGIN
 IF (p_customer IS NULL) = (p_conversation IS NULL) THEN RAISE EXCEPTION 'INVALID_MARK'; END IF;
 RETURN jsonb_build_object('marks',(SELECT coalesce(jsonb_agg(sokhach._mark_json(m,v_today) ORDER BY m.created_at DESC,m.id DESC),'[]'::jsonb)
   FROM sokhach.contact_mark m
   WHERE (p_customer IS NOT NULL AND m.customer_id=p_customer) OR (p_conversation IS NOT NULL AND m.conversation_id=p_conversation)));
END $$;
REVOKE ALL ON TABLE sokhach.zalo_link, sokhach.contact_mark FROM PUBLIC,sokhach_app,sokhach_reader;
REVOKE ALL ON FUNCTION sokhach._mark_json(sokhach.contact_mark,date) FROM PUBLIC,sokhach_app,sokhach_reader;
GRANT EXECUTE ON FUNCTION sokhach.link_zalo(text,bigint), sokhach.unlink_zalo(text,bigint,text),
  sokhach.record_mark(jsonb), sokhach.cancel_mark(bigint,text) TO sokhach_app;
GRANT EXECUTE ON FUNCTION sokhach.get_zalo_links(), sokhach.get_marks(bigint,text) TO sokhach_app,sokhach_reader;
COMMIT;
