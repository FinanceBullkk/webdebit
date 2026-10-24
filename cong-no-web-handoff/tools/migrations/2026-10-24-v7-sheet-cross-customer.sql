-- Review/test only. Run after 2026-10-22-v7-nhap-sheet.sql.
BEGIN;
SET LOCAL ROLE sokhach_owner;

CREATE OR REPLACE FUNCTION sokhach.list_sheet_trip_refs() RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, sokhach, pg_temp AS $$
BEGIN
    PERFORM sokhach._actor();
    RETURN (SELECT jsonb_build_object('items',coalesce(jsonb_agg(
        jsonb_build_object('customer_id',customer_id,'container',container)
        ORDER BY customer_id,id),'[]'::jsonb))
    FROM sokhach.v_trip_current WHERE NOT deleted AND container IS NOT NULL);
END;
$$;
REVOKE ALL ON FUNCTION sokhach.list_sheet_trip_refs() FROM PUBLIC,sokhach_reader;
GRANT EXECUTE ON FUNCTION sokhach.list_sheet_trip_refs() TO sokhach_app;

CREATE OR REPLACE FUNCTION sokhach.guard_sheet_cross_customer() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, sokhach, pg_temp AS $$
DECLARE v_container text;
BEGIN
    IF NEW.source_ref IS NULL OR NEW.source_ref !~ '^sheet:[0-9a-f]{64}:[0-9]+$' THEN RETURN NEW; END IF;
    v_container := sokhach._normalize_key(NEW.container);
    PERFORM pg_advisory_xact_lock(746193,hashtext(v_container));
    IF EXISTS (SELECT 1 FROM sokhach.v_trip_current t WHERE NOT t.deleted
        AND t.customer_id<>NEW.customer_id
        AND sokhach._normalize_key(t.container)=v_container
        AND (sokhach._booking_key(t.booking,t.container,t.event_date)=
             sokhach._booking_key(NEW.booking,NEW.container,NEW.event_date)
             OR abs(t.event_date-NEW.event_date)<=3))
    THEN RAISE EXCEPTION 'SHEET_CROSS_CUSTOMER_MATCH'; END IF;
    RETURN NEW;
END $$;
REVOKE ALL ON FUNCTION sokhach.guard_sheet_cross_customer() FROM PUBLIC,sokhach_app,sokhach_reader;
DROP TRIGGER IF EXISTS trip_sheet_cross_customer ON sokhach.trip;
CREATE TRIGGER trip_sheet_cross_customer BEFORE INSERT ON sokhach.trip
FOR EACH ROW EXECUTE FUNCTION sokhach.guard_sheet_cross_customer();
COMMIT;
