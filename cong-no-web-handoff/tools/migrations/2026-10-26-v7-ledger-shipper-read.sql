BEGIN;

DO $$
DECLARE
    definition text := pg_get_functiondef('sokhach.get_ledger(bigint)'::regprocedure);
    before_field constant text := '''carrier'',t.carrier,''status'',t.status';
    after_field constant text := '''carrier'',t.carrier,''shipper'',t.shipper,''status'',t.status';
BEGIN
    IF to_regclass('sokhach.v_trip_current') IS NULL
       OR NOT EXISTS (SELECT 1 FROM information_schema.columns
           WHERE table_schema='sokhach' AND table_name='v_trip_current' AND column_name='shipper')
    THEN RAISE EXCEPTION 'SHIPPER_VIEW_MISSING'; END IF;
    IF position(after_field IN definition) > 0 THEN RETURN; END IF;
    IF length(definition)-length(replace(definition,before_field,'')) <> length(before_field)
    THEN RAISE EXCEPTION 'GET_LEDGER_DEFINITION_CHANGED'; END IF;
    EXECUTE replace(definition,before_field,after_field);
END $$;

COMMIT;
