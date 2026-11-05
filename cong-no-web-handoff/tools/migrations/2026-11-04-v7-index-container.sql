-- Đọc dòng sổ gốc theo container nhanh hơn (4/11/2026): list_legacy_trip_refs chạy mỗi lần mở sổ có dòng chờ, quét tuần tự
-- hai bảng và chạy regex từng dòng. Thêm hai index biểu thức và viết lại điều kiện lọc để planner dùng chúng.
-- Kết quả hàm giữ nguyên từng byte. Không đổi cột, ràng buộc, loại event, dữ liệu hay quyền. Chạy sau 2026-11-01-v7-chan-trung-hang-cho.sql;
-- chạy lại migration đó thì phải chạy lại file này. Chạy lại được.
-- CREATE INDEX thường, không CONCURRENTLY: migration chạy trong một transaction và trong cửa sổ dừng ghi; hai bảng nhỏ (dưới 0,2 giây mỗi bảng),
-- chỉ chặn ghi, không chặn đọc. ANALYZE để planner có thống kê của biểu thức: thiếu nó thì ước lượng lệch, autovacuum không tự chạy vì bảng ít đổi.
BEGIN;
SET LOCAL ROLE sokhach_owner;
CREATE INDEX IF NOT EXISTS legacy_row_container_key ON sokhach.legacy_row (sokhach._normalize_key(display->>'container'));
CREATE INDEX IF NOT EXISTS legacy_trip_rev_container_key ON sokhach.legacy_trip_rev (sokhach._normalize_key(container));
ANALYZE sokhach.legacy_row;
ANALYZE sokhach.legacy_trip_rev;

CREATE OR REPLACE FUNCTION sokhach.list_legacy_trip_refs(containers jsonb) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, sokhach, pg_temp AS $$
DECLARE v_keys text[];
BEGIN
    PERFORM sokhach._actor();
    IF jsonb_typeof(containers) IS DISTINCT FROM 'array' OR jsonb_array_length(containers)>2000
       OR EXISTS (SELECT 1 FROM jsonb_array_elements(containers) c WHERE jsonb_typeof(c)<>'string')
    THEN RAISE EXCEPTION 'INVALID_COMMAND'; END IF;
    SELECT coalesce(array_agg(DISTINCT sokhach._normalize_key(c#>>'{}')),'{}') INTO v_keys FROM jsonb_array_elements(containers) c;
    -- Lọc theo container trước (dòng gốc hoặc bản sửa), rồi mới đọc bản sửa mới nhất của dòng ứng viên.
    -- Giữ = ANY(mảng), đừng đổi về IN (SELECT ...): với hash semi join planner gần như không tính chi phí _normalize_key
    -- nên quét tuần tự cả hai bảng và bỏ qua index container_key (đo trên bản sao thật 4/11/2026: 169 ms so với 9 ms).
    RETURN (WITH cand AS (SELECT l.id FROM sokhach.legacy_row l WHERE l.kind='trip'
                   AND sokhach._normalize_key(l.display->>'container') = ANY(v_keys)
                 UNION
                 SELECT y.legacy_row_id FROM sokhach.legacy_trip_rev y
                  WHERE sokhach._normalize_key(y.container) = ANY(v_keys)),
        x AS (SELECT l.id,l.customer_id,
                CASE WHEN r.id IS NULL THEN l.display->>'container' ELSE r.container END AS container,
                CASE WHEN r.id IS NULL THEN sokhach._legacy_date(l.display->>'date') ELSE r.event_date END AS event_date,
                coalesce(r.debt_month,l.debt_month) AS debt_month
            FROM cand JOIN sokhach.legacy_row l ON l.id=cand.id
            JOIN sokhach.cutover_customer cc ON (cc.customer_id,cc.cutover_id)=(l.customer_id,l.cutover_id) AND cc.status='active'
            LEFT JOIN LATERAL (SELECT y.id,y.debt_month,y.event_date,y.container,y.deleted FROM sokhach.legacy_trip_rev y
                WHERE y.legacy_row_id=l.id ORDER BY y.id DESC LIMIT 1) r ON true
            WHERE NOT coalesce(r.deleted,false))
        SELECT jsonb_build_object('items',coalesce(jsonb_agg(jsonb_build_object(
            'customer_id',x.customer_id,'container',x.container,'event_date',x.event_date,'debt_month',x.debt_month)
            ORDER BY x.customer_id,x.id),'[]'::jsonb))
        FROM x WHERE sokhach._normalize_key(x.container) = ANY(v_keys) AND sokhach._normalize_key(x.container)<>'');
END;
$$;
COMMIT;
