-- Read-only, fail closed. Required: -v db_v7=... -v loader_role=...
-- Optional: -v expect_customers=N -v expect_openings=N
\set ON_ERROR_STOP on
\if :{?db_v7}
\else
\echo ERROR missing db_v7
SELECT 1/0;
\endif
\if :{?loader_role}
\else
\echo ERROR missing loader_role
SELECT 1/0;
\endif
\if :{?expect_customers}
\else
\set expect_customers ''
\endif
\if :{?expect_openings}
\else
\set expect_openings ''
\endif
BEGIN READ ONLY;
-- psql variables are quoted as literals before being passed into DO blocks.
SELECT set_config('v7check.database', :'db_v7', true) AS check_database,
       set_config('v7check.loader', :'loader_role', true) AS check_loader,
       set_config('v7check.customers', :'expect_customers', true) AS check_customers,
       set_config('v7check.openings', :'expect_openings', true) AS check_openings \gset
DO $$
DECLARE
    r text;
    x record;
    privilege text;
    expected text[] := ARRAY[
      'edit_trip_info(bigint,bigint,text,bigint,text,text)',
      'delete_trip(bigint,bigint,text,bigint)',
      'edit_legacy_trip(bigint,bigint,text,bigint,text,text)',
      'delete_legacy_trip(bigint,bigint,text,bigint)',
      'get_ledger(bigint)', 'list_offset_sources(bigint)', 'list_customers()', 'get_dashboard()', 'get_receivables_matrix(integer)', 'list_sheet_trip_refs()',
      'paste_trips(bigint,bigint,text,date,jsonb)',
      'edit_trip_price(bigint,bigint,text,bigint,bigint,bigint)',
      'adjust_trip(bigint,bigint,text,bigint,bigint,text,text,bigint)',
      'adjust_month(bigint,bigint,text,date,bigint,text)',
      'record_receipt(bigint,bigint,text,date,text,bigint,text)',
      'edit_receipt_meta(bigint,bigint,text,text,date,text,text)',
      'void_receipt(bigint,bigint,text,text,text)',
      'set_month_lock(bigint,bigint,text,date,boolean)',
      'review_trip(bigint,bigint,text,bigint,text,text)',
      'record_offset(bigint,bigint,bigint,bigint,text,date,bigint,text)',
      'void_offset(bigint,bigint,bigint,text,bigint,text)',
      'edit_offset_date(bigint,bigint,bigint,text,bigint,date)'];
    actual text[];
    wanted text;
    n bigint;
BEGIN
    IF current_database() = 'webdebit_ledger'
       OR current_database() <> current_setting('v7check.database') THEN
        RAISE EXCEPTION 'wrong database';
    END IF;
    IF NOT EXISTS (SELECT FROM pg_namespace WHERE nspname='sokhach') THEN
        RAISE EXCEPTION 'schema missing';
    END IF;
    RAISE NOTICE 'OK database_schema';
    IF NOT EXISTS(SELECT FROM pg_constraint WHERE conrelid='sokhach.adjustment'::regclass
        AND conname='adjustment_one_target' AND convalidated)
       OR EXISTS(SELECT FROM sokhach.adjustment WHERE trip_id IS NOT NULL AND legacy_row_id IS NOT NULL)
    THEN RAISE EXCEPTION 'adjustment_one_target missing or violated'; END IF;
    IF EXISTS(SELECT FROM sokhach.legacy_row l JOIN LATERAL
        (SELECT * FROM sokhach.legacy_trip_rev r WHERE r.legacy_row_id=l.id ORDER BY r.id DESC LIMIT 1) r ON true
        WHERE r.counted_vnd<>coalesce(l.source_total_vnd,0)+coalesce(
            (SELECT sum(a.amount_vnd) FROM sokhach.adjustment a WHERE a.legacy_row_id=l.id),0))
    THEN RAISE EXCEPTION 'legacy counted amount mismatch'; END IF;
    IF EXISTS(SELECT FROM sokhach.trip_info_rev r LEFT JOIN sokhach.event e
        ON (e.id,e.customer_id)=(r.created_by_event,r.customer_id) WHERE e.id IS NULL)
       OR EXISTS(SELECT FROM sokhach.legacy_trip_rev r LEFT JOIN sokhach.event e
        ON (e.id,e.customer_id)=(r.created_by_event,r.customer_id) WHERE e.id IS NULL)
    THEN RAISE EXCEPTION 'revision event missing'; END IF;
    RAISE NOTICE 'OK nhap_sheet_revisions';

    FOREACH r IN ARRAY ARRAY['v7_app',current_setting('v7check.loader')] LOOP
        IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname=r AND rolcanlogin
            AND NOT (rolsuper OR rolcreaterole OR rolcreatedb OR rolreplication OR rolbypassrls)) THEN
            RAISE EXCEPTION 'role missing or elevated';
        END IF;
        IF EXISTS (SELECT FROM pg_roles g WHERE
            (g.rolsuper OR g.rolcreaterole OR g.rolcreatedb OR g.rolreplication OR g.rolbypassrls)
            AND pg_has_role(r,g.oid,'MEMBER')) THEN
            RAISE EXCEPTION 'elevated role membership';
        END IF;
    END LOOP;
    IF NOT pg_has_role('v7_app','sokhach_app','USAGE') OR
       NOT pg_has_role(current_setting('v7check.loader'),'sokhach_owner','USAGE') THEN
        RAISE EXCEPTION 'required membership missing';
    END IF;
    RAISE NOTICE 'OK login_roles';
    IF to_regprocedure('sokhach.resolve_sheet_conflict(bigint,bigint,text,text,bigint,text,bigint,text,text,text,text)') IS NOT NULL THEN
        expected := array_append(expected,
            'resolve_sheet_conflict(bigint,bigint,text,text,bigint,text,bigint,text,text,text,text)');
    END IF;
    SELECT array_agg(s ORDER BY s) INTO expected FROM unnest(expected) s;
    SELECT array_agg(p.proname||'('||replace(oidvectortypes(p.proargtypes),', ', ',')||')'
      ORDER BY p.proname||'('||replace(oidvectortypes(p.proargtypes),', ', ',')||')')
      INTO actual FROM pg_proc p WHERE p.pronamespace='sokhach'::regnamespace
      AND has_function_privilege('v7_app',p.oid,'EXECUTE');
    IF actual IS DISTINCT FROM expected THEN RAISE EXCEPTION 'function allowlist mismatch'; END IF;
    RAISE NOTICE 'OK app_execute_allowlist';
    FOREACH r IN ARRAY ARRAY['sokhach_app','sokhach_reader','v7_app'] LOOP
        FOR x IN SELECT oid,relkind FROM pg_class WHERE relnamespace='sokhach'::regnamespace
            AND relkind IN ('r','p','v','m','f','S') LOOP
            IF x.relkind='S' THEN
                IF has_sequence_privilege(r,x.oid,'USAGE,SELECT,UPDATE') THEN
                    RAISE EXCEPTION 'sequence privilege present';
                END IF;
            ELSE
                IF has_table_privilege(r,x.oid,'SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER,MAINTAIN') THEN
                    RAISE EXCEPTION 'relation privilege present';
                END IF;
                FOREACH privilege IN ARRAY ARRAY['SELECT','INSERT','UPDATE','REFERENCES'] LOOP
                    IF has_any_column_privilege(r,x.oid,privilege) THEN
                        RAISE EXCEPTION 'column privilege present';
                    END IF;
                END LOOP;
            END IF;
        END LOOP;
    END LOOP;
    RAISE NOTICE 'OK no_relation_privileges';
    IF EXISTS (SELECT FROM pg_proc p CROSS JOIN LATERAL
        aclexplode(coalesce(p.proacl,acldefault('f',p.proowner))) a
        WHERE p.pronamespace='sokhach'::regnamespace AND a.grantee=0
        AND a.privilege_type='EXECUTE') THEN RAISE EXCEPTION 'PUBLIC EXECUTE'; END IF;
    RAISE NOTICE 'OK public_execute_denied';
    IF EXISTS (SELECT FROM pg_database d CROSS JOIN LATERAL
        aclexplode(coalesce(d.datacl,acldefault('d',d.datdba))) a
        WHERE d.datname=current_database() AND a.grantee=0
        AND a.privilege_type='CONNECT') THEN RAISE EXCEPTION 'PUBLIC CONNECT'; END IF;
    RAISE NOTICE 'OK public_connect_denied';
    FOREACH r IN ARRAY ARRAY['customers','openings'] LOOP
        wanted := current_setting('v7check.'||r);
        IF wanted <> '' THEN
            IF wanted !~ '^(0|[1-9][0-9]*)$' THEN RAISE EXCEPTION 'invalid expected count'; END IF;
            IF r='customers' THEN
                SELECT count(*) INTO n FROM sokhach.customer;
            ELSE
                SELECT count(*) INTO n FROM sokhach.opening_balance o
                  JOIN sokhach.cutover_customer cc ON cc.customer_id=o.customer_id AND cc.cutover_id=o.cutover_id
                  JOIN sokhach.cutover c ON c.id=cc.cutover_id
                  WHERE cc.status='active' AND c.status='active';
            END IF;
            IF n <> wanted::bigint THEN RAISE EXCEPTION 'count mismatch'; END IF;
            RAISE NOTICE 'OK expected_%',r;
        ELSE
            RAISE NOTICE 'OK optional_%_not_requested',r;
        END IF;
    END LOOP;
END $$;
ROLLBACK;
