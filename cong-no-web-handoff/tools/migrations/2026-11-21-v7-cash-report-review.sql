-- ZALO-THU-CHI-01 PR-3 (2026-11-21): xác nhận, sửa số, gắn đối tượng, loại khoản thu chi báo trong nhóm Zalo (cash_report_review).
-- Chỉ THÊM bảng/hàm ghi chú, NGOÀI đường tiền như contact_mark: không VND vào số dư, không khóa tháng, không phân bổ, không bump
-- customer.version, không đổi hàm hay bảng cũ. Chỉ thêm dòng: các dòng của một tin gộp theo thứ tự thành trạng thái hiệu lực, giữ vết;
-- mỗi dòng ghi trạng thái ngay trước nó (`before`, {} = giá trị đọc từ tin). Chạy lại được. Áp sau 2026-11-19-v7-tach-phi-loai-moi.sql.
BEGIN;
SET LOCAL ROLE sokhach_owner;
CREATE TABLE IF NOT EXISTS sokhach.cash_report_review (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    conversation_id text NOT NULL CHECK (conversation_id ~ '^[0-9a-f]{64}$'),
    message_id text NOT NULL CHECK (message_id ~ '^[0-9A-Za-z_-]{1,128}$'),
    action text NOT NULL CHECK (action IN ('confirm', 'target', 'amount', 'not_cash')),
    target_kind text CHECK (target_kind IS NULL OR target_kind IN ('so', 'xe', 'tai_xe')),
    target_id bigint CHECK (target_id IS NULL OR target_id > 0),
    amount_vnd bigint CHECK (amount_vnd IS NULL OR amount_vnd > 0),
    before jsonb NOT NULL CHECK (jsonb_typeof(before) = 'object' AND octet_length(before::text) <= 10000),
    reason text CHECK (reason IS NULL OR (btrim(reason) <> '' AND char_length(reason) <= 500)),
    request_id text NOT NULL UNIQUE CHECK (btrim(request_id) <> '' AND char_length(request_id) <= 200),
    created_by text NOT NULL CHECK (btrim(created_by) <> ''),
    created_at timestamptz NOT NULL DEFAULT now(),
    CHECK ((action = 'target') = (target_kind IS NOT NULL) AND (target_kind IS NULL) = (target_id IS NULL)),
    CHECK ((action = 'amount') = (amount_vnd IS NOT NULL)),
    CHECK (action <> 'not_cash' OR reason IS NOT NULL)
);
CREATE INDEX IF NOT EXISTS cash_report_review_message ON sokhach.cash_report_review (message_id, id);
COMMENT ON TABLE sokhach.cash_report_review IS 'ZALO-THU-CHI-01 PR-3: xác nhận/sửa số/gắn đối tượng/loại một khoản thu chi báo trong nhóm Zalo; chỉ thêm dòng, gộp theo thứ tự; không tham gia tính tiền.';

-- Trạng thái hiệu lực của một tin, gộp các dòng có id < p_before (NULL: mọi dòng). Sửa số hay gắn đối tượng thì bỏ quyết định cũ
-- (xác nhận cũ là cho số/đối tượng cũ); xác nhận và loại thay nhau. Chưa có dòng nào: {} (giá trị đọc từ tin).
CREATE OR REPLACE FUNCTION sokhach._cash_review_state(p_message text, p_before bigint) RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path=pg_catalog,sokhach,pg_temp AS $$
DECLARE r sokhach.cash_report_review; v_last sokhach.cash_report_review; v_amount bigint; v_kind text; v_id bigint;
 v_decision text; v_reason text; v_count int := 0;
BEGIN
 FOR r IN SELECT * FROM sokhach.cash_report_review c WHERE c.message_id=p_message AND (p_before IS NULL OR c.id<p_before) ORDER BY c.id LOOP
   v_count:=v_count+1; v_last:=r;
   IF r.action='amount' THEN v_amount:=r.amount_vnd; v_decision:=NULL; v_reason:=NULL;
   ELSIF r.action='target' THEN v_kind:=r.target_kind; v_id:=r.target_id; v_decision:=NULL; v_reason:=NULL;
   ELSE v_decision:=r.action; v_reason:=r.reason; END IF;
 END LOOP;
 IF v_count=0 THEN RETURN '{}'::jsonb; END IF;
 RETURN jsonb_build_object('amount_vnd',v_amount::text,
   'target',CASE WHEN v_kind IS NULL THEN NULL ELSE jsonb_build_object('kind',v_kind,'id',v_id) END,
   'decision',v_decision,'reason',v_reason,'reviews',v_count,'last_action',v_last.action,'last_by',v_last.created_by,'last_at',v_last.created_at);
END $$;

CREATE OR REPLACE FUNCTION sokhach._cash_review_json(r sokhach.cash_report_review) RETURNS jsonb
LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog,sokhach,pg_temp AS $$
 SELECT jsonb_build_object('id',r.id,'conversation_id',r.conversation_id,'message_id',r.message_id,'action',r.action,
   'target',CASE WHEN r.target_kind IS NULL THEN NULL ELSE jsonb_build_object('kind',r.target_kind,'id',r.target_id) END,
   'amount_vnd',r.amount_vnd::text,'before',r.before,'reason',r.reason,'request_id',r.request_id,'created_by',r.created_by,
   'created_at',r.created_at,'state',sokhach._cash_review_state(r.message_id,r.id+1))
$$;

-- p: {conversation_id, message_id, action, request_id, amount_vnd (chuỗi số nguyên dương, chỉ khi sửa số), target {kind, id} (chỉ khi
-- gắn đối tượng), reason (bắt buộc khi loại)}. Bấm lặp cùng request_id trả dòng đã ghi, không thêm dòng; request_id của việc khác thì từ chối.
CREATE OR REPLACE FUNCTION sokhach.record_cash_review(p jsonb) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,sokhach,pg_temp AS $$
DECLARE
 v_action text := p->>'action'; v_message text := p->>'message_id'; v_key text := p->>'request_id';
 v_conversation text := p->>'conversation_id'; v_reason text := nullif(btrim(p->>'reason'),''); v_amount bigint; v_kind text; v_id bigint;
 v_old sokhach.cash_report_review; v_row sokhach.cash_report_review; v_found boolean;
BEGIN
 IF jsonb_typeof(p)<>'object' OR v_action IS NULL OR v_action NOT IN ('confirm','target','amount','not_cash')
    OR coalesce(v_conversation,'') !~ '^[0-9a-f]{64}$' OR coalesce(v_message,'') !~ '^[0-9A-Za-z_-]{1,128}$'
    OR v_key IS NULL OR btrim(v_key)='' OR char_length(v_key)>200 OR char_length(coalesce(v_reason,''))>500 THEN
   RAISE EXCEPTION 'INVALID_CASH_REVIEW'; END IF;
 IF v_action='amount' THEN
   IF coalesce(p->>'amount_vnd','') !~ '^[1-9][0-9]{0,17}$' THEN RAISE EXCEPTION 'INVALID_CASH_REVIEW'; END IF;
   v_amount:=(p->>'amount_vnd')::bigint;
 ELSIF p ? 'amount_vnd' AND p->'amount_vnd'<>'null'::jsonb THEN RAISE EXCEPTION 'INVALID_CASH_REVIEW';
 END IF;
 IF v_action='target' THEN
   v_kind:=p->'target'->>'kind';
   IF jsonb_typeof(p->'target')<>'object' OR v_kind IS NULL OR v_kind NOT IN ('so','xe','tai_xe')
      OR coalesce(p->'target'->>'id','') !~ '^[1-9][0-9]{0,17}$' THEN RAISE EXCEPTION 'INVALID_CASH_REVIEW'; END IF;
   v_id:=(p->'target'->>'id')::bigint;
 ELSIF p ? 'target' AND p->'target'<>'null'::jsonb THEN RAISE EXCEPTION 'INVALID_CASH_REVIEW';
 END IF;
 IF v_action='not_cash' AND v_reason IS NULL THEN RAISE EXCEPTION 'REASON_REQUIRED'; END IF;
 -- Bấm lặp (mất mạng rồi gửi lại cùng mã): đúng nội dung cũ thì trả dòng đã ghi; khác bất kỳ trường nào thì từ chối, như record_mark.
 SELECT * INTO v_old FROM sokhach.cash_report_review c WHERE c.request_id=v_key;
 IF FOUND THEN
   IF (v_old.conversation_id,v_old.message_id,v_old.action,v_old.amount_vnd,v_old.target_kind,v_old.target_id,v_old.reason)
      IS DISTINCT FROM (v_conversation,v_message,v_action,v_amount,v_kind,v_id,v_reason) THEN RAISE EXCEPTION 'IDEMPOTENCY_CONFLICT'; END IF;
   RETURN sokhach._cash_review_json(v_old)||jsonb_build_object('replayed',true);
 END IF;
 IF v_action='target' THEN
   -- Mỗi bảng một câu: PL/pgSQL chỉ lập kế hoạch câu khi chạy tới, nên DB chưa có Đội xe vẫn gắn được sổ.
   IF v_kind='so' THEN v_found:=EXISTS(SELECT 1 FROM sokhach.customer c WHERE c.id=v_id);
   ELSIF v_kind='xe' AND to_regclass('doixe.xe') IS NOT NULL THEN v_found:=EXISTS(SELECT 1 FROM doixe.xe x WHERE x.id=v_id);
   ELSIF v_kind='tai_xe' AND to_regclass('doixe.nguoi') IS NOT NULL THEN v_found:=EXISTS(SELECT 1 FROM doixe.nguoi n WHERE n.id=v_id);
   END IF;
   IF NOT coalesce(v_found,false) THEN RAISE EXCEPTION 'TARGET_NOT_FOUND'; END IF;
 END IF;
 -- Hai người bấm cùng lúc trên một tin: xếp hàng theo tin, để `before` của người sau là trạng thái sau lượt của người trước.
 PERFORM pg_advisory_xact_lock(hashtextextended('cash_report_review:'||v_message,0));
 INSERT INTO sokhach.cash_report_review(conversation_id,message_id,action,target_kind,target_id,amount_vnd,before,reason,request_id,created_by)
   VALUES(v_conversation,v_message,v_action,v_kind,v_id,v_amount,
          sokhach._cash_review_state(v_message,NULL)-'last_by'-'last_at'-'last_action'-'reviews',v_reason,v_key,sokhach._actor())
   ON CONFLICT (request_id) DO NOTHING
   RETURNING * INTO v_row;
 IF v_row.id IS NULL THEN   -- cùng request_id vừa được người khác ghi giữa lúc kiểm và lúc ghi
   SELECT * INTO v_old FROM sokhach.cash_report_review c WHERE c.request_id=v_key;
   IF (v_old.conversation_id,v_old.message_id,v_old.action,v_old.amount_vnd,v_old.target_kind,v_old.target_id,v_old.reason)
      IS DISTINCT FROM (v_conversation,v_message,v_action,v_amount,v_kind,v_id,v_reason) THEN RAISE EXCEPTION 'IDEMPOTENCY_CONFLICT'; END IF;
   RETURN sokhach._cash_review_json(v_old)||jsonb_build_object('replayed',true);
 END IF;
 RETURN sokhach._cash_review_json(v_row);
END $$;

-- p: {message_ids: [...]} (tối đa 5000) → {reviews: {message_id: trạng thái hiệu lực}}, chỉ tin đã có dòng.
CREATE OR REPLACE FUNCTION sokhach.get_cash_reviews(p jsonb) RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path=pg_catalog,sokhach,pg_temp AS $$
DECLARE v_ids text[];
BEGIN
 IF jsonb_typeof(p)<>'object' OR jsonb_typeof(p->'message_ids')<>'array' OR jsonb_array_length(p->'message_ids')>5000
    OR EXISTS(SELECT 1 FROM jsonb_array_elements(p->'message_ids') e WHERE jsonb_typeof(e)<>'string' OR e#>>'{}' !~ '^[0-9A-Za-z_-]{1,128}$') THEN
   RAISE EXCEPTION 'INVALID_CASH_REVIEW'; END IF;
 v_ids:=ARRAY(SELECT jsonb_array_elements_text(p->'message_ids'));
 RETURN jsonb_build_object('reviews',(SELECT coalesce(jsonb_object_agg(m.message_id,sokhach._cash_review_state(m.message_id,NULL)),'{}'::jsonb)
   FROM (SELECT DISTINCT c.message_id FROM sokhach.cash_report_review c WHERE c.message_id=ANY(v_ids)) m));
END $$;

REVOKE ALL ON TABLE sokhach.cash_report_review FROM PUBLIC,sokhach_app,sokhach_reader;
REVOKE ALL ON FUNCTION sokhach._cash_review_state(text,bigint), sokhach._cash_review_json(sokhach.cash_report_review),
  sokhach.record_cash_review(jsonb), sokhach.get_cash_reviews(jsonb) FROM PUBLIC,sokhach_app,sokhach_reader;
GRANT EXECUTE ON FUNCTION sokhach.record_cash_review(jsonb) TO sokhach_app;
GRANT EXECUTE ON FUNCTION sokhach.get_cash_reviews(jsonb) TO sokhach_app,sokhach_reader;
COMMIT;
