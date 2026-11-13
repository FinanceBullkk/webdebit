-- BANG-GIA-05 (13/11/2026): bước "Xem lại trước khi lưu" của khung Bảng giá. Chỉ thêm hàm preview_price_table: gọi đúng
-- save_price_table trong khối con rồi hoàn tác, trả số chuyến tự đổi, tổng đổi, tháng khóa, giá gõ tay. Không đổi bảng,
-- hàm có sẵn, giá chuyến hay số dư. Chạy sau 2026-11-13-v7-noi-den-tuy-chon.sql; chạy lại được.
BEGIN;
SET LOCAL ROLE sokhach_owner;
-- BANG-GIA-05: xem trước lệnh lưu bảng giá. Gọi đúng save_price_table trong một khối con, đọc trạng thái giá sau khi lưu,
-- rồi ném lỗi để PostgreSQL hoàn tác khối con: số chuyến tự đổi, tổng đổi, tháng khóa, giá gõ tay là số của chính hàm sẽ ghi,
-- mà không ghi gì (không event, không version, không phân bổ lại). Lỗi bảng (trùng ngày, sổ đã đổi…) trả như lệnh lưu.
CREATE OR REPLACE FUNCTION sokhach.preview_price_table(customer_id bigint,expected_version bigint,idempotency_key text,
 price_table jsonb) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,sokhach,pg_temp AS $$
DECLARE v_saved jsonb; v_status jsonb; v_message text; v_detail text;
BEGIN
 BEGIN
   v_saved:=sokhach.save_price_table(customer_id,expected_version,idempotency_key,price_table);
   v_status:=sokhach.get_price_status(customer_id);
   RAISE EXCEPTION 'PRICE_PREVIEW_ROLLBACK' USING DETAIL=jsonb_build_object(
     'price_table',v_saved->'price_table','version',expected_version,
     'repriced_trips',(SELECT coalesce(jsonb_agg(r.x||jsonb_build_object('tier',s.x->'lookup'->>'tier')
         ORDER BY (r.x->>'trip_id')::bigint),'[]'::jsonb)
       FROM jsonb_array_elements(v_saved->'repriced_trips') r(x)
       LEFT JOIN jsonb_array_elements(v_status->'trips') s(x) ON s.x->>'trip_id'=r.x->>'trip_id'),
     'repriced_delta_vnd',v_saved->'repriced_delta_vnd','locked_trips',v_saved->'locked_trips',
     'no_price_trips',v_saved->'no_price_trips',
     -- Giá gõ tay hoặc lấy từ Sheet khác bảng mới: không đổi (gõ tay thắng bảng), chỉ đếm để người dùng biết.
     'typed_trips',(SELECT count(*) FROM jsonb_array_elements(v_status->'trips') s(x)
       WHERE (s.x->>'differs')::boolean AND NOT (s.x->>'from_table')::boolean),
     -- Chuyến chưa có giá mà bảng mới điền được: vẫn phải bấm "Điền giá theo bảng" (BANG-GIA-02), không đổi khi lưu.
     'ready_count',v_status->'ready_count','ready_total_vnd',v_status->'ready_total_vnd')::text;
 EXCEPTION WHEN raise_exception THEN
   GET STACKED DIAGNOSTICS v_message=MESSAGE_TEXT,v_detail=PG_EXCEPTION_DETAIL;
   IF v_message IS DISTINCT FROM 'PRICE_PREVIEW_ROLLBACK' THEN RAISE; END IF;
 END;
 RETURN v_detail::jsonb;
END $$;

REVOKE ALL ON FUNCTION sokhach.preview_price_table(bigint,bigint,text,jsonb) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION sokhach.preview_price_table(bigint,bigint,text,jsonb) TO sokhach_app;
RESET ROLE;
COMMIT;
