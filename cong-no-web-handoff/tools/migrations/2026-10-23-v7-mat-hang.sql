-- MH-01: list_customers trả mặt hàng và phương thức vận chuyển, 2026-10-23.
-- Review/test only; never auto-deploy. Run after 2026-10-22-v7-trip-review.sql with
-- psql -X -v ON_ERROR_STOP=1 -f this-file as schema administrator, after backup.
-- Atomic and repeatable; same signature so grants stay; no table or financial row change.
BEGIN;
SET LOCAL ROLE sokhach_owner;
CREATE OR REPLACE FUNCTION sokhach.list_customers() RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, sokhach, pg_temp AS $$
BEGIN
    PERFORM sokhach._actor();
    RETURN (SELECT jsonb_build_object('customers',coalesce(jsonb_agg(
        jsonb_build_object('id',id,'name',name,'status',status,
                           'commodity',commodity,'transport_mode',transport_mode)
        ORDER BY name COLLATE "C",id),'[]'::jsonb))
      FROM (SELECT c.id,c.name,
                   CASE WHEN cc.status='active' AND co.status='active'
                        THEN 'active' ELSE 'NO_BASELINE' END AS status,
                   m.name AS commodity,c.transport_mode
              FROM sokhach.customer c
              LEFT JOIN sokhach.commodity m ON m.id=c.commodity_id
              LEFT JOIN sokhach.cutover_customer cc ON cc.customer_id=c.id
              LEFT JOIN sokhach.cutover co ON co.id=cc.cutover_id) q);
END $$;
COMMIT;
