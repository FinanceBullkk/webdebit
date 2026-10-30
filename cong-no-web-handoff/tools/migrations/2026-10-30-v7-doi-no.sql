-- NHAC-NO-01 (2026-10-30): nhật ký "đã nhắc" đòi nợ (tab Đòi nợ). Chỉ thêm bảng/hàm ghi chú,
-- NGOÀI đường tiền: không VND, không khóa tháng, không phân bổ, không bump version, không đổi hàm cũ.
-- Chạy lại được. Áp sau 2026-10-29-v7-chung-tu.sql. Không chạy trên hao khi chưa có lệnh người dùng.
BEGIN;
SET LOCAL ROLE sokhach_owner;
CREATE TABLE IF NOT EXISTS sokhach.reminder_log(
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 customer_id bigint NOT NULL REFERENCES sokhach.customer(id),
 source text NOT NULL CHECK(source IN('zalo','copy-button','manual')),
 reminded_at date NOT NULL,
 actor text NOT NULL CHECK(btrim(actor)<>''),
 created_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(customer_id,source,reminded_at));
CREATE INDEX IF NOT EXISTS reminder_log_customer ON sokhach.reminder_log(customer_id,reminded_at DESC);
CREATE OR REPLACE FUNCTION sokhach.record_reminder(p_customer bigint, p_source text) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,sokhach,pg_temp AS $$
DECLARE v_at date := (clock_timestamp() AT TIME ZONE 'Asia/Ho_Chi_Minh')::date;
BEGIN
 IF p_source IS NULL OR p_source NOT IN ('zalo','copy-button','manual') THEN RAISE EXCEPTION 'INVALID_REMINDER'; END IF;
 IF NOT EXISTS(SELECT 1 FROM sokhach.customer c WHERE c.id=p_customer) THEN RAISE EXCEPTION 'CUSTOMER_NOT_FOUND'; END IF;
 INSERT INTO sokhach.reminder_log(customer_id,source,reminded_at,actor)
   VALUES(p_customer,p_source,v_at,sokhach._actor())
   ON CONFLICT(customer_id,source,reminded_at) DO NOTHING;
 RETURN jsonb_build_object('customer_id',p_customer,'source',p_source,'reminded_at',v_at);
END $$;
CREATE OR REPLACE FUNCTION sokhach.get_reminders() RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path=pg_catalog,sokhach,pg_temp AS $$
BEGIN
 RETURN jsonb_build_object('reminders',(SELECT coalesce(jsonb_agg(jsonb_build_object(
    'customer_id',t.customer_id,'last_reminded',t.last_reminded,'reminder_count',t.reminder_count,'last_source',t.last_source)
    ORDER BY t.last_reminded DESC),'[]'::jsonb)
  FROM (SELECT customer_id,max(reminded_at) AS last_reminded,count(*) AS reminder_count,
          (array_agg(source ORDER BY reminded_at DESC,id DESC))[1] AS last_source
        FROM sokhach.reminder_log GROUP BY customer_id) t));
END $$;
REVOKE ALL ON TABLE sokhach.reminder_log FROM PUBLIC,sokhach_app,sokhach_reader;
GRANT EXECUTE ON FUNCTION sokhach.record_reminder(bigint,text) TO sokhach_app;
GRANT EXECUTE ON FUNCTION sokhach.get_reminders() TO sokhach_app,sokhach_reader;
COMMIT;
