-- DIEU-CHINH-THEO-GIA-01 (audit SQL 23/11/2026, F6; người dùng chọn cách A 23/11/2026): điều chỉnh của chuyến chỉ tính khi chuyến
-- còn số tiền gốc. Chỉ thay view v_adjustment_current (cùng cột) và tăng schema_level; không đổi bảng, dữ liệu hay quyền.
-- Trên hao 23/11/2026 không có điều chỉnh chuyến nào đang tính nên số dư không đổi lúc nâng. Chạy sau 2026-11-23-v7-audit-sql.sql;
-- chạy lại được.
BEGIN;
SET LOCAL ROLE sokhach_owner;
-- DIEU-CHINH-THEO-GIA-01 (người dùng chọn 23/11/2026, audit SQL F6): điều chỉnh của chuyến chỉ tính khi chuyến còn số tiền gốc
-- (có đơn giá, hoặc dòng chỉ phụ phí có phụ phí), cùng điều kiện chuyến được cộng vào nợ ở v_outstanding_month_raw. Xóa đơn giá
-- thì cả chuyến lẫn điều chỉnh của nó ra khỏi số dư; nhập lại đơn giá thì điều chỉnh tính lại. Dòng điều chỉnh không bị xóa.
CREATE OR REPLACE VIEW sokhach.v_adjustment_current AS
SELECT a.id,a.customer_id,coalesce(t.debt_month,a.debt_month) AS debt_month,
       a.trip_id,a.legacy_row_id,a.amount_vnd,a.field,a.new_value_vnd,a.note,a.actor,a.at,a.created_by_event
FROM sokhach.adjustment a LEFT JOIN sokhach.v_trip_current t ON t.id=a.trip_id
LEFT JOIN LATERAL (SELECT unit_price_vnd,other_fee_vnd FROM sokhach.trip_price_rev
    WHERE trip_id=a.trip_id ORDER BY id DESC LIMIT 1) p ON a.trip_id IS NOT NULL
WHERE NOT a.fee_absorbed AND (a.trip_id IS NULL OR (NOT t.deleted AND t.status='confirmed'
      AND (p.unit_price_vnd IS NOT NULL OR ((t.container IS NULL OR t.container='') AND p.other_fee_vnd IS NOT NULL))))
  AND a.reverses_adjustment_id IS NULL
  AND NOT EXISTS (SELECT 1 FROM sokhach.adjustment r WHERE r.reverses_adjustment_id=a.id);
CREATE OR REPLACE FUNCTION sokhach.schema_level() RETURNS integer
LANGUAGE sql IMMUTABLE SET search_path = pg_catalog, sokhach, pg_temp AS $$ SELECT 2026112302 $$;
REVOKE ALL ON FUNCTION sokhach.schema_level() FROM PUBLIC, sokhach_app, sokhach_reader;
GRANT EXECUTE ON FUNCTION sokhach.schema_level() TO sokhach_app;
COMMIT;
