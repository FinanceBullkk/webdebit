-- XOA-DC-THANG-01 (29/10/2026): xóa dòng điều chỉnh cả tháng.
-- Xóa = thêm một dòng đảo dấu trỏ về dòng gốc (reverses_adjustment_id); bảng adjustment vẫn chỉ thêm.
-- Cặp gốc + đảo cùng tháng, tổng 0, nên mọi vế tiền đọc bảng thô không đổi; v_adjustment_current ẩn cả cặp khỏi sổ.
-- Áp sau 2026-10-29-v7-chung-tu.sql (ràng buộc event gồm loại của chứng từ). Chạy lại được. Không chạy trên hao khi chưa có lệnh người dùng.
BEGIN;
SET LOCAL ROLE sokhach_owner;
ALTER TABLE sokhach.adjustment ADD COLUMN IF NOT EXISTS reverses_adjustment_id bigint UNIQUE REFERENCES sokhach.adjustment(id);
DO $$ BEGIN
  IF NOT EXISTS(SELECT 1 FROM pg_constraint WHERE conrelid='sokhach.adjustment'::regclass AND conname='adjustment_reversal_month_only') THEN
    ALTER TABLE sokhach.adjustment ADD CONSTRAINT adjustment_reversal_month_only CHECK (reverses_adjustment_id IS NULL
        OR (trip_id IS NULL AND legacy_row_id IS NULL AND field IS NULL));
  END IF;
END $$;
ALTER TABLE sokhach.event DROP CONSTRAINT event_kind_check;
ALTER TABLE sokhach.event ADD CONSTRAINT event_kind_check CHECK (kind IN ('paste', 'price_edit', 'adjust_trip',
        'adjust_month', 'receipt', 'receipt_edit', 'void', 'reallocation', 'month_lock', 'import',
        'customer_attr', 'trip_review', 'trip_edit', 'trip_delete', 'legacy_edit', 'legacy_delete',
        'sheet_conflict_resolved', 'fee_migration', 'add_trip_fees', 'set_trip_fee_type', 'replace_trip_fee', 'void_trip_fee', 'set_book_fee_columns',
        'price_table_edit', 'price_table_apply', 'receipt_image', 'receipt_image_remove', 'adjust_month_delete'));
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
        WHEN 'adjust_month_delete' THEN "before" ? 'adjustment' AND coalesce("after"->'adjustment'->'deleted'='true'::jsonb,false)
        ELSE false END);
-- Trip adjustments follow current information; pending/deleted trips contribute nothing.
-- A deleted month adjustment and its reversal sum to 0 in the same month, so both are hidden (XOA-DC-THANG-01).
CREATE OR REPLACE VIEW sokhach.v_adjustment_current AS
SELECT a.id,a.customer_id,coalesce(t.debt_month,a.debt_month) AS debt_month,
       a.trip_id,a.legacy_row_id,a.amount_vnd,a.field,a.new_value_vnd,a.note,a.actor,a.at,a.created_by_event
FROM sokhach.adjustment a LEFT JOIN sokhach.v_trip_current t ON t.id=a.trip_id
WHERE NOT a.fee_absorbed AND (a.trip_id IS NULL OR (NOT t.deleted AND t.status='confirmed'))
  AND a.reverses_adjustment_id IS NULL
  AND NOT EXISTS (SELECT 1 FROM sokhach.adjustment r WHERE r.reverses_adjustment_id=a.id);
-- XOA-DC-THANG-01: xóa điều chỉnh cả tháng bằng một dòng đảo dấu trỏ về dòng gốc; tháng phải đang mở.
CREATE OR REPLACE FUNCTION sokhach.delete_month_adjustment(customer_id bigint, expected_version bigint,
    idempotency_key text, adjustment_id bigint)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, sokhach, pg_temp AS $$
DECLARE v_payload jsonb := jsonb_build_object('command','delete_month_adjustment','adjustment_id',adjustment_id);
        v_retry jsonb; a sokhach.adjustment%ROWTYPE; v_id bigint; v_event bigint; v_changes jsonb;
BEGIN
    v_retry := sokhach._begin_command(customer_id,expected_version,idempotency_key,v_payload);
    IF v_retry IS NOT NULL THEN RETURN v_retry; END IF;
    PERFORM sokhach._baseline(customer_id);
    SELECT a0.* INTO a FROM sokhach.adjustment a0
    WHERE a0.id=delete_month_adjustment.adjustment_id AND a0.customer_id=delete_month_adjustment.customer_id
      AND a0.trip_id IS NULL AND a0.legacy_row_id IS NULL AND a0.field IS NULL AND NOT a0.fee_absorbed
      AND a0.reverses_adjustment_id IS NULL
      AND NOT EXISTS (SELECT 1 FROM sokhach.adjustment r WHERE r.reverses_adjustment_id=a0.id);
    IF NOT FOUND THEN RAISE EXCEPTION 'ADJUSTMENT_NOT_FOUND'; END IF;
    PERFORM sokhach._month_open(customer_id,a.debt_month,clock_timestamp());
    v_id := nextval(pg_get_serial_sequence('sokhach.adjustment','id'));
    INSERT INTO sokhach.event(customer_id,kind,actor,"before","after",idempotency_key)
    VALUES (customer_id,'adjust_month_delete',sokhach._actor(),
        jsonb_build_object('adjustment',jsonb_build_object('id',a.id,'month',a.debt_month,
            'amount_vnd',a.amount_vnd::text,'note',a.note,'actor',a.actor,'at',a.at)),
        jsonb_build_object('adjustment',jsonb_build_object('id',a.id,'month',a.debt_month,
            'amount_vnd','0','deleted',true,'reversal',v_id)),idempotency_key)
    RETURNING id INTO v_event;
    INSERT INTO sokhach.adjustment(id,customer_id,debt_month,trip_id,amount_vnd,note,actor,created_by_event,reverses_adjustment_id)
    OVERRIDING SYSTEM VALUE VALUES (v_id,customer_id,a.debt_month,NULL,-a.amount_vnd,a.note,sokhach._actor(),v_event,a.id);
    v_changes := sokhach.reallocate(customer_id,idempotency_key);
    RETURN sokhach._finish_command(customer_id,idempotency_key,v_payload,
        jsonb_build_object('adjustment_id',a.id,'reversal_id',v_id,'reallocated',v_changes));
END $$;
GRANT EXECUTE ON FUNCTION sokhach.delete_month_adjustment(bigint,bigint,text,bigint) TO sokhach_app;
COMMIT;
