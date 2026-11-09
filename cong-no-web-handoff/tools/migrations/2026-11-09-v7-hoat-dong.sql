-- HOAT-DONG-01 (9/11/2026): xem lại việc đã ghi của một ngày bất kỳ, mọi sổ, cả máy lẫn người (tab Đã làm của Việc cần làm).
-- Chỉ THÊM một hàm đọc get_activity(date) cấp cho app (như get_ledger_events: Lịch sử có trước → sau nên không cấp reader).
-- Không đổi bảng, view, hàm ghi, loại event, phân bổ, dữ liệu hay quyền cũ. Chạy lại được. Chạy sau 2026-11-09-v7-thu-thang-theo-so.sql.
BEGIN;
SET LOCAL ROLE sokhach_owner;
CREATE OR REPLACE FUNCTION sokhach.get_activity(p_day date) RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = pg_catalog, sokhach, pg_temp AS $$
-- Ngày theo giờ VN. Mỗi event cùng hình dạng với Lịch sử của sổ (_ledger_events) để giao diện dùng chung câu chữ, thêm tên sổ.
-- Lô dán chỉ giữ các ô giao diện đọc. Kèm container của chuyến/dòng sổ gốc và số phiếu mà event nhắc tới bằng id (mọi số nguyên
-- trong trước/sau, lọc theo sổ của event), để câu "Sửa giá chuyến X" không phải mở từng sổ. prev_day/next_day: ngày gần nhất có việc.
DECLARE d date := (now() AT TIME ZONE 'Asia/Ho_Chi_Minh')::date; v_day date := coalesce(p_day, d);
        v_from timestamptz; v_to timestamptz;
BEGIN
  PERFORM sokhach._actor();
  IF v_day > d THEN RAISE EXCEPTION 'INVALID_DAY'; END IF;
  v_from := v_day::timestamp AT TIME ZONE 'Asia/Ho_Chi_Minh';
  v_to := (v_day + 1)::timestamp AT TIME ZONE 'Asia/Ho_Chi_Minh';
  RETURN (WITH ev AS (
      SELECT e.id,e.customer_id,e.kind,e.actor,e.at,e."before",
        CASE WHEN e.kind='paste' THEN jsonb_build_object('trips',(SELECT coalesce(jsonb_agg(jsonb_strip_nulls(jsonb_build_object(
            'trip_id',t->'trip_id','container',t->'container','event_date',t->'event_date','date',t->'date',
            'unitPriceVnd',t->'unitPriceVnd','status',t->'status','note',t->'note')) ORDER BY n),'[]'::jsonb)
            FROM jsonb_array_elements(e."after"->'trips') WITH ORDINALITY x(t,n))) ELSE e."after" END AS "after"
        FROM sokhach.event e WHERE e.at>=v_from AND e.at<v_to),
    ids AS (
      SELECT DISTINCT ev.customer_id,(v #>> '{}')::bigint AS id
        FROM ev CROSS JOIN LATERAL jsonb_path_query(jsonb_build_array(ev."before",ev."after"),'strict $.** ? (@.type() == "number")') v
       WHERE (v #>> '{}') ~ '^[0-9]{1,18}$'),
    total AS (SELECT count(*) AS n FROM ev),
    shown AS (SELECT * FROM ev ORDER BY at DESC,id DESC LIMIT 2000)
    SELECT jsonb_build_object('day',v_day,'today',d,
      'prev_day',(SELECT (max(e.at) AT TIME ZONE 'Asia/Ho_Chi_Minh')::date FROM sokhach.event e WHERE e.at<v_from),
      'next_day',(SELECT (min(e.at) AT TIME ZONE 'Asia/Ho_Chi_Minh')::date FROM sokhach.event e WHERE e.at>=v_to),
      'total',(SELECT n FROM total),
      'events',(SELECT coalesce(jsonb_agg(jsonb_build_object('id',s.id,'customer_id',s.customer_id,'customer',c.name,
          'kind',s.kind,'actor',s.actor,'at',s.at,
          'counterparty_name',(SELECT o.name FROM sokhach.offset_pair p JOIN sokhach.customer o
              ON o.id=CASE WHEN p.source_customer_id=s.customer_id THEN p.target_customer_id ELSE p.source_customer_id END
              WHERE (p.source_customer_id=s.customer_id AND p.source_pid=s."after"->>'receipt')
                 OR (p.target_customer_id=s.customer_id AND p.target_receipt_id::text=s."after"->>'receipt')),
          'before',CASE WHEN s.kind='price_edit' THEN s."before" || jsonb_build_object('price',s."before"->'price' || jsonb_build_object(
              'unit_price_vnd',s."before"->'price'->>'unit_price_vnd','other_fee_vnd',s."before"->'price'->>'other_fee_vnd')) ELSE s."before" END,
          'after',CASE WHEN s.kind='price_edit' THEN s."after" || jsonb_build_object('price',s."after"->'price' || jsonb_build_object(
              'unit_price_vnd',s."after"->'price'->>'unit_price_vnd','other_fee_vnd',s."after"->'price'->>'other_fee_vnd')) ELSE s."after" END)
          ORDER BY s.at DESC,s.id DESC),'[]'::jsonb) FROM shown s JOIN sokhach.customer c ON c.id=s.customer_id),
      'trips',(SELECT coalesce(jsonb_agg(jsonb_build_object('id',t.id,'container',t.container) ORDER BY t.id),'[]'::jsonb)
        FROM sokhach.trip t JOIN ids ON (ids.customer_id,ids.id)=(t.customer_id,t.id)),
      'legacy_rows',(SELECT coalesce(jsonb_agg(jsonb_build_object('id',l.id,'current',jsonb_build_object('container',
          coalesce(sokhach._legacy_current(l.id)->>'container',l.display->>'container'))) ORDER BY l.id),'[]'::jsonb)
        FROM sokhach.legacy_row l JOIN ids ON (ids.customer_id,ids.id)=(l.customer_id,l.id)),
      'receipts',(SELECT coalesce(jsonb_agg(jsonb_build_object('id',r.id,'pid',r.pid,'date',r.date) ORDER BY r.id),'[]'::jsonb)
        FROM sokhach.receipt r JOIN ids ON (ids.customer_id,ids.id)=(r.customer_id,r.id)),
      'fee_types',(SELECT coalesce(jsonb_agg(jsonb_build_object('id',f.id,'name',f.name) ORDER BY f.sort,f.id),'[]'::jsonb)
        FROM sokhach.fee_type f)));
END $$;
REVOKE ALL ON FUNCTION sokhach.get_activity(date) FROM PUBLIC, sokhach_app, sokhach_reader;
GRANT EXECUTE ON FUNCTION sokhach.get_activity(date) TO sokhach_app;
RESET ROLE;
COMMIT;
