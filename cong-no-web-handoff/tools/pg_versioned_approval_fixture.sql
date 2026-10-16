-- Acceptance fixture only. Never deploy or apply to hao/production.
-- Charge-only fixture (schema v3). One API role; actor identity comes from the server-side session.
\set ON_ERROR_STOP on

CREATE ROLE p0_fixture_owner NOLOGIN;
CREATE ROLE p0_fixture_api NOLOGIN;
GRANT CONNECT ON DATABASE webdebit_ledger TO p0_fixture_api;
CREATE SCHEMA p0_fixture AUTHORIZATION p0_fixture_owner;
REVOKE ALL ON SCHEMA p0_fixture FROM PUBLIC;
GRANT USAGE ON SCHEMA p0_fixture TO p0_fixture_api;

SET ROLE p0_fixture_owner;

-- Whitespace that must not survive in a trip key: ASCII/locale spaces plus the Unicode spaces and
-- zero-width characters that commonly arrive when text is pasted from a Sheet (NBSP, ZWSP, BOM, ...).
CREATE FUNCTION p0_fixture.strip_trip_whitespace(p_value text) RETURNS text
LANGUAGE sql IMMUTABLE
SET search_path = pg_catalog AS $$
    SELECT regexp_replace(coalesce(p_value, ''),
        '[\s\u00a0\u1680\u2000-\u200f\u2028\u2029\u202f\u205f\u2060\u3000\ufeff]', '', 'g')
$$;

CREATE FUNCTION p0_fixture.is_blank(p_value text) RETURNS boolean
LANGUAGE sql IMMUTABLE
SET search_path = pg_catalog AS $$
    -- Unicode White_Space, independent of the database locale; never changes the input.
    SELECT coalesce(p_value, '') COLLATE "C" !~
        '[^\u0009-\u000d\u0020\u0085\u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000]'
$$;

CREATE TABLE p0_fixture.app_actor (
    actor_id uuid PRIMARY KEY,
    active boolean NOT NULL DEFAULT true
);

CREATE TABLE p0_fixture.app_actor_role (
    actor_id uuid NOT NULL REFERENCES p0_fixture.app_actor,
    app_role text NOT NULL CHECK (app_role IN ('maker', 'checker', 'price_owner', 'admin')),
    PRIMARY KEY (actor_id, app_role)
);

CREATE TABLE p0_fixture.debt_period_state (
    debt_period text PRIMARY KEY CHECK (debt_period ~ '^\d{4}-(0[1-9]|1[0-2])$'),
    state text NOT NULL CHECK (state IN ('open', 'closed'))
);

-- Owner-only. Empty outside tests, so every charge stays blocked by default (CHỜ KIỂM).
-- A row ABSENT_FROM_OPENING_APPROVED stands for an approved "trip is not in the opening" decision.
CREATE TABLE p0_fixture.trip_opening_resolution (
    trip_key text PRIMARY KEY CHECK (trip_key <> '' AND trip_key = upper(trip_key)
        AND trip_key = p0_fixture.strip_trip_whitespace(trip_key)),
    status text NOT NULL CHECK (status IN ('ABSENT_FROM_OPENING_APPROVED', 'IN_OPENING', 'UNRESOLVED')),
    evidence_ref text NOT NULL CHECK (NOT p0_fixture.is_blank(evidence_ref)),
    approved_by text NOT NULL CHECK (NOT p0_fixture.is_blank(approved_by)),
    approved_at timestamptz NOT NULL DEFAULT clock_timestamp()
);

CREATE TABLE p0_fixture.proposal (
    proposal_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    maker_actor_id uuid NOT NULL REFERENCES p0_fixture.app_actor,
    current_revision_id bigint,
    revision_no integer NOT NULL DEFAULT 0 CHECK (revision_no >= 0),
    state text NOT NULL DEFAULT 'review_needed' CHECK (state IN ('review_needed', 'approved', 'posted')),
    presentation_title text NOT NULL DEFAULT '',
    created_at timestamptz NOT NULL DEFAULT clock_timestamp()
);

CREATE TABLE p0_fixture.business_revision (
    revision_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    proposal_id bigint NOT NULL REFERENCES p0_fixture.proposal,
    revision_no integer NOT NULL CHECK (revision_no > 0),
    canonical_payload jsonb NOT NULL,
    content_sha256 text NOT NULL CHECK (content_sha256 ~ '^[0-9a-f]{64}$'),
    trip_key text,
    review_reason_codes text[] NOT NULL DEFAULT ARRAY[]::text[],
    created_by_actor uuid NOT NULL REFERENCES p0_fixture.app_actor,
    created_in_session uuid NOT NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    UNIQUE (proposal_id, revision_no),
    UNIQUE (proposal_id, revision_id),
    UNIQUE (proposal_id, revision_id, content_sha256)
);
CREATE INDEX business_revision_trip_key_idx ON p0_fixture.business_revision (trip_key);

ALTER TABLE p0_fixture.proposal
    ADD CONSTRAINT current_revision_belongs_to_proposal
    FOREIGN KEY (proposal_id, current_revision_id)
    REFERENCES p0_fixture.business_revision (proposal_id, revision_id)
    DEFERRABLE INITIALLY DEFERRED;

CREATE TABLE p0_fixture.period_confirmation (
    confirmation_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    proposal_id bigint NOT NULL,
    revision_id bigint NOT NULL,
    content_sha256 text NOT NULL,
    maker_actor_id uuid NOT NULL REFERENCES p0_fixture.app_actor,
    maker_session_id uuid NOT NULL,
    database_session_user name NOT NULL,
    confirmed_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    FOREIGN KEY (proposal_id, revision_id, content_sha256)
        REFERENCES p0_fixture.business_revision (proposal_id, revision_id, content_sha256),
    UNIQUE (revision_id)
);

-- The price confirmer holds the price_owner role (business owner). A maker may also hold it and confirm
-- the price of their own charge (PRICE-MAKER); the confirmer may not be the checker of the same revision.
CREATE TABLE p0_fixture.price_confirmation (
    confirmation_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    proposal_id bigint NOT NULL,
    revision_id bigint NOT NULL,
    content_sha256 text NOT NULL,
    confirmer_actor_id uuid NOT NULL REFERENCES p0_fixture.app_actor,
    confirmer_session_id uuid NOT NULL,
    database_session_user name NOT NULL,
    confirmed_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    FOREIGN KEY (proposal_id, revision_id, content_sha256)
        REFERENCES p0_fixture.business_revision (proposal_id, revision_id, content_sha256),
    UNIQUE (revision_id)
);

CREATE TABLE p0_fixture.approval (
    approval_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    proposal_id bigint NOT NULL,
    revision_id bigint NOT NULL,
    content_sha256 text NOT NULL,
    checker_actor_id uuid NOT NULL REFERENCES p0_fixture.app_actor,
    checker_session_id uuid NOT NULL,
    database_session_user name NOT NULL,
    approved_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    FOREIGN KEY (proposal_id, revision_id, content_sha256)
        REFERENCES p0_fixture.business_revision (proposal_id, revision_id, content_sha256),
    UNIQUE (revision_id)
);

CREATE TABLE p0_fixture.posting (
    posting_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    proposal_id bigint NOT NULL UNIQUE,
    revision_id bigint NOT NULL UNIQUE,
    approval_id bigint NOT NULL REFERENCES p0_fixture.approval,
    content_sha256 text NOT NULL,
    -- Conservative rule until the business owner decides "per trip" vs "per trip + fee type": one posting
    -- per key. Also the backstop for the advisory-lock check, which a REPEATABLE READ/SERIALIZABLE
    -- snapshot can miss.
    trip_key text NOT NULL UNIQUE,
    canonical_payload jsonb NOT NULL,
    maker_actor_id uuid NOT NULL REFERENCES p0_fixture.app_actor,
    checker_actor_id uuid NOT NULL REFERENCES p0_fixture.app_actor,
    posted_in_session uuid NOT NULL,
    database_session_user name NOT NULL,
    posted_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    FOREIGN KEY (proposal_id, revision_id, content_sha256)
        REFERENCES p0_fixture.business_revision (proposal_id, revision_id, content_sha256),
    CHECK (maker_actor_id <> checker_actor_id)
);

CREATE VIEW p0_fixture.posted_balance AS
SELECT x.line->>'customer_id' AS customer_id,
       x.line->>'debt_period' AS debt_period,
       sum((x.line->>'amount_vnd')::numeric) AS posted_balance_vnd
FROM p0_fixture.posting p
CROSS JOIN LATERAL jsonb_array_elements(p.canonical_payload->'lines') AS x(line)
GROUP BY x.line->>'customer_id', x.line->>'debt_period';

CREATE TABLE p0_fixture.audit (
    audit_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    proposal_id bigint NOT NULL REFERENCES p0_fixture.proposal,
    revision_id bigint,
    content_sha256 text,
    app_actor_id uuid NOT NULL REFERENCES p0_fixture.app_actor,
    app_session_id uuid NOT NULL,
    database_session_user name NOT NULL,
    action text NOT NULL CHECK (action IN ('submit', 'submit_noop', 'presentation',
        'confirm_price', 'confirm_period', 'approve', 'post')),
    occurred_at timestamptz NOT NULL DEFAULT clock_timestamp()
);

CREATE FUNCTION p0_fixture.reject_immutable_change() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog, p0_fixture AS $$
BEGIN
    RAISE EXCEPTION 'append-only fixture row';
END $$;

CREATE TRIGGER business_revision_append_only
    BEFORE UPDATE OR DELETE ON p0_fixture.business_revision
    FOR EACH ROW EXECUTE FUNCTION p0_fixture.reject_immutable_change();
CREATE TRIGGER approval_append_only
    BEFORE UPDATE OR DELETE ON p0_fixture.approval
    FOR EACH ROW EXECUTE FUNCTION p0_fixture.reject_immutable_change();
CREATE TRIGGER price_confirmation_append_only
    BEFORE UPDATE OR DELETE ON p0_fixture.price_confirmation
    FOR EACH ROW EXECUTE FUNCTION p0_fixture.reject_immutable_change();
CREATE TRIGGER period_confirmation_append_only
    BEFORE UPDATE OR DELETE ON p0_fixture.period_confirmation
    FOR EACH ROW EXECUTE FUNCTION p0_fixture.reject_immutable_change();
CREATE TRIGGER posting_append_only
    BEFORE UPDATE OR DELETE ON p0_fixture.posting
    FOR EACH ROW EXECUTE FUNCTION p0_fixture.reject_immutable_change();
CREATE TRIGGER audit_append_only
    BEFORE UPDATE OR DELETE ON p0_fixture.audit
    FOR EACH ROW EXECUTE FUNCTION p0_fixture.reject_immutable_change();

-- Actor identity is supplied by the server-side session (Q01); the DB checks the actor is active,
-- holds the role, and that the connecting login belongs to the single API role.
CREATE FUNCTION p0_fixture.require_actor(p_actor_id uuid, p_session_id uuid, p_role text) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, p0_fixture AS $$
BEGIN
    IF p_actor_id IS NULL OR p_session_id IS NULL OR p_role IS NULL THEN
        RAISE EXCEPTION 'actor and session are required' USING ERRCODE = 'P0001';
    END IF;
    IF NOT pg_has_role(session_user, 'p0_fixture_api', 'member') THEN
        RAISE EXCEPTION 'untrusted database principal' USING ERRCODE = 'P0001';
    END IF;
    PERFORM 1 FROM p0_fixture.app_actor a WHERE a.actor_id = p_actor_id AND a.active FOR SHARE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'inactive actor' USING ERRCODE = 'P0001';
    END IF;
    PERFORM 1 FROM p0_fixture.app_actor_role r
    WHERE r.actor_id = p_actor_id AND r.app_role = p_role FOR SHARE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'actor role required' USING ERRCODE = 'P0001';
    END IF;
END $$;

CREATE FUNCTION p0_fixture.parse_iso_date(p_value text) RETURNS date
LANGUAGE plpgsql IMMUTABLE STRICT
SET search_path = pg_catalog AS $$
DECLARE
    v_year integer;
    v_month integer;
    v_day integer;
BEGIN
    IF octet_length(p_value) <> 10
       OR (p_value COLLATE "C") !~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$' THEN
        RAISE EXCEPTION 'invalid fixture date' USING ERRCODE = 'P0001';
    END IF;
    v_year := substr(p_value, 1, 4)::integer;
    v_month := substr(p_value, 6, 2)::integer;
    v_day := substr(p_value, 9, 2)::integer;
    IF v_year < 1 OR v_year > 9999 THEN
        RAISE EXCEPTION 'invalid fixture date' USING ERRCODE = 'P0001';
    END IF;
    BEGIN
        RETURN make_date(v_year, v_month, v_day);
    EXCEPTION WHEN datetime_field_overflow THEN
        RAISE EXCEPTION 'invalid fixture date' USING ERRCODE = 'P0001';
    END;
END $$;

-- Money is a canonical nonnegative JSON integer. NULL/absent stays NULL (not 0); 0 stays 0.
-- Exponent and decimal spellings (1e2, 100.0) are rejected before parsing, see submit_revision.
CREATE FUNCTION p0_fixture.canonical_vnd(p_value jsonb) RETURNS numeric
LANGUAGE plpgsql IMMUTABLE
SET search_path = pg_catalog AS $$
BEGIN
    IF p_value IS NULL OR jsonb_typeof(p_value) = 'null' THEN
        RETURN NULL;
    END IF;
    IF jsonb_typeof(p_value) <> 'number'
       OR (p_value::text COLLATE "C") !~ '^(0|[1-9][0-9]{0,14})$' THEN
        RAISE EXCEPTION 'fixture VND value must be a canonical nonnegative JSON integer'
            USING ERRCODE = 'P0001';
    END IF;
    RETURN p_value::text::numeric;
END $$;

-- trip_key = upper(booking || container) with every (Unicode) whitespace removed; NULL when either part is blank.
CREATE FUNCTION p0_fixture.compute_trip_key(p_booking text, p_container text) RETURNS text
LANGUAGE plpgsql IMMUTABLE
SET search_path = pg_catalog AS $$
DECLARE
    v_booking text := upper(p0_fixture.strip_trip_whitespace(p_booking));
    v_container text := upper(p0_fixture.strip_trip_whitespace(p_container));
BEGIN
    IF v_booking = '' OR v_container = '' THEN
        RETURN NULL;
    END IF;
    RETURN v_booking || v_container;
END $$;

CREATE FUNCTION p0_fixture.canonicalize_payload(p_payload jsonb) RETURNS jsonb
LANGUAGE plpgsql IMMUTABLE
SET search_path = pg_catalog AS $$
DECLARE
    v_line jsonb;
    v_components jsonb;
    v_component jsonb;
    v_total numeric;
    v_warehouse_in date;
    v_field text;
    v_trip_key text;
BEGIN
    IF jsonb_typeof(p_payload) IS DISTINCT FROM 'object'
       OR EXISTS (SELECT 1 FROM jsonb_object_keys(p_payload) AS ak(key)
            WHERE ak.key <> ALL (ARRAY['schema_version','customer_id','debt_period',
                'total_vnd','warehouse_in_date','posting_date','source_ref','evidence_ref',
                'evidence_sha256','reason','lines','booking_no','container_no',
                'price_components','period_override_reason','period_override_evidence_ref',
                'period_override_evidence_sha256']))
       OR NOT p_payload ?& ARRAY['schema_version','customer_id','debt_period',
                'warehouse_in_date','posting_date','reason','lines'] THEN
        RAISE EXCEPTION 'payload has missing or unknown business fields' USING ERRCODE = 'P0001';
    END IF;
    IF jsonb_typeof(p_payload->'schema_version') IS DISTINCT FROM 'number'
       OR (p_payload->>'schema_version') <> '3' THEN
        RAISE EXCEPTION 'unsupported fixture schema version; expected version 3' USING ERRCODE = 'P0001';
    END IF;
    IF jsonb_typeof(p_payload->'customer_id') IS DISTINCT FROM 'string'
       OR jsonb_typeof(p_payload->'debt_period') IS DISTINCT FROM 'string'
       OR jsonb_typeof(p_payload->'warehouse_in_date') IS DISTINCT FROM 'string'
       OR jsonb_typeof(p_payload->'posting_date') IS DISTINCT FROM 'string'
       OR jsonb_typeof(p_payload->'reason') IS DISTINCT FROM 'string'
       OR jsonb_typeof(p_payload->'lines') IS DISTINCT FROM 'array' THEN
        RAISE EXCEPTION 'invalid fixture payload fields' USING ERRCODE = 'P0001';
    END IF;
    IF p0_fixture.is_blank(p_payload->>'customer_id')
       OR (p_payload->>'debt_period') COLLATE "C" !~ '^[0-9]{4}-(0[1-9]|1[0-2])$'
       OR p0_fixture.is_blank(p_payload->>'reason') THEN
        RAISE EXCEPTION 'invalid fixture payload fields' USING ERRCODE = 'P0001';
    END IF;
    PERFORM p0_fixture.parse_iso_date((p_payload->>'debt_period') || '-01');

    FOREACH v_field IN ARRAY ARRAY['source_ref','evidence_ref','evidence_sha256','booking_no',
        'container_no','period_override_reason','period_override_evidence_ref',
        'period_override_evidence_sha256'] LOOP
        IF p_payload ? v_field AND jsonb_typeof(p_payload->v_field) NOT IN ('null', 'string') THEN
            RAISE EXCEPTION 'invalid fixture optional field: %', v_field USING ERRCODE = 'P0001';
        END IF;
    END LOOP;
    IF jsonb_typeof(p_payload->'evidence_sha256') = 'string'
       AND (p_payload->>'evidence_sha256' COLLATE "C") !~ '^[0-9a-f]{64}$' THEN
        RAISE EXCEPTION 'invalid evidence hash' USING ERRCODE = 'P0001';
    END IF;
    IF jsonb_typeof(p_payload->'period_override_evidence_sha256') = 'string'
       AND (p_payload->>'period_override_evidence_sha256' COLLATE "C") !~ '^[0-9a-f]{64}$' THEN
        RAISE EXCEPTION 'invalid period override evidence hash' USING ERRCODE = 'P0001';
    END IF;

    v_total := p0_fixture.canonical_vnd(p_payload->'total_vnd');
    v_warehouse_in := p0_fixture.parse_iso_date(p_payload->>'warehouse_in_date');
    PERFORM p0_fixture.parse_iso_date(p_payload->>'posting_date');
    IF v_warehouse_in < DATE '2026-10-14' THEN
        RAISE EXCEPTION 'chuyến cũ, nợ thuộc opening 13/10: ngày xe nhập kho trước 2026-10-14'
            USING ERRCODE = 'P0001';
    END IF;

    IF jsonb_array_length(p_payload->'lines') <> 1 THEN
        RAISE EXCEPTION 'charge must have exactly one debt line' USING ERRCODE = 'P0001';
    END IF;
    v_line := p_payload->'lines'->0;
    IF jsonb_typeof(v_line) IS DISTINCT FROM 'object'
       OR EXISTS (SELECT 1 FROM jsonb_object_keys(v_line) AS lk(key)
            WHERE lk.key <> ALL (ARRAY['line_no','customer_id','debt_period','amount_vnd']))
       OR NOT v_line ?& ARRAY['line_no','customer_id','debt_period']
       OR jsonb_typeof(v_line->'line_no') IS DISTINCT FROM 'number'
       OR jsonb_typeof(v_line->'customer_id') IS DISTINCT FROM 'string'
       OR jsonb_typeof(v_line->'debt_period') IS DISTINCT FROM 'string'
       OR (v_line->>'line_no') COLLATE "C" !~ '^[1-9][0-9]{0,8}$'
       OR v_line->>'customer_id' <> p_payload->>'customer_id'
       OR v_line->>'debt_period' <> p_payload->>'debt_period' THEN
        RAISE EXCEPTION 'invalid fixture line' USING ERRCODE = 'P0001';
    END IF;

    IF p_payload->'price_components' IS NULL OR jsonb_typeof(p_payload->'price_components') = 'null' THEN
        v_components := 'null'::jsonb;
    ELSE
        IF jsonb_typeof(p_payload->'price_components') IS DISTINCT FROM 'array' THEN
            RAISE EXCEPTION 'invalid per-trip price component list' USING ERRCODE = 'P0001';
        END IF;
        FOR v_component IN
            SELECT x.component FROM jsonb_array_elements(p_payload->'price_components') AS x(component)
        LOOP
            IF jsonb_typeof(v_component) IS DISTINCT FROM 'object'
               OR EXISTS (SELECT 1 FROM jsonb_object_keys(v_component) AS ck(key)
                    WHERE ck.key <> ALL (ARRAY['label', 'amount_vnd']))
               OR jsonb_typeof(v_component->'label') IS DISTINCT FROM 'string'
               OR p0_fixture.is_blank(v_component->>'label') THEN
                RAISE EXCEPTION 'invalid per-trip price component' USING ERRCODE = 'P0001';
            END IF;
            PERFORM p0_fixture.canonical_vnd(v_component->'amount_vnd');
        END LOOP;
        SELECT CASE WHEN jsonb_array_length(p_payload->'price_components') = 0 THEN '[]'::jsonb
                    ELSE jsonb_agg(jsonb_build_object(
                        'label', x.component->>'label',
                        'amount_vnd', p0_fixture.canonical_vnd(x.component->'amount_vnd')
                    ) ORDER BY x.ordinality) END
        INTO v_components
        FROM jsonb_array_elements(p_payload->'price_components')
            WITH ORDINALITY AS x(component, ordinality);
    END IF;

    v_trip_key := p0_fixture.compute_trip_key(p_payload->>'booking_no', p_payload->>'container_no');
    RETURN jsonb_build_object(
        'schema_version', 3,
        'customer_id', p_payload->>'customer_id',
        'debt_period', p_payload->>'debt_period',
        'total_vnd', v_total,
        'warehouse_in_date', p_payload->>'warehouse_in_date',
        'posting_date', p_payload->>'posting_date',
        'source_ref', p_payload->'source_ref',
        'evidence_ref', p_payload->'evidence_ref',
        'evidence_sha256', p_payload->'evidence_sha256',
        'reason', p_payload->>'reason',
        'lines', jsonb_build_array(jsonb_build_object(
            'line_no', (v_line->>'line_no')::integer,
            'customer_id', v_line->>'customer_id',
            'debt_period', v_line->>'debt_period',
            'amount_vnd', p0_fixture.canonical_vnd(v_line->'amount_vnd'))),
        'booking_no', p_payload->'booking_no',
        'container_no', p_payload->'container_no',
        'trip_key', v_trip_key,
        'price_components', v_components,
        'period_override_reason', p_payload->'period_override_reason',
        'period_override_evidence_ref', p_payload->'period_override_evidence_ref',
        'period_override_evidence_sha256', p_payload->'period_override_evidence_sha256');
END $$;

-- Reasons computable from the canonical payload alone. Codes ending in _WARNING never block.
-- DUPLICATE_TRIP_KEY and OPENING_RESOLUTION_MISSING depend on other rows that change after submit, so
-- the projection computes them live instead of freezing them in the snapshot.
CREATE FUNCTION p0_fixture.charge_review_reason_codes(p_payload jsonb) RETURNS text[]
LANGUAGE plpgsql IMMUTABLE
SET search_path = pg_catalog AS $$
DECLARE
    v_codes text[] := ARRAY[]::text[];
    v_total numeric;
    v_component_total numeric;
    v_components jsonb;
BEGIN
    IF jsonb_typeof(p_payload->'total_vnd') = 'null' THEN
        v_codes := array_append(v_codes, 'TOTAL_MISSING');
    ELSE
        v_total := (p_payload->>'total_vnd')::numeric;
        IF v_total = 0 THEN
            v_codes := array_append(v_codes, 'TOTAL_ZERO');
        END IF;
    END IF;

    v_components := p_payload->'price_components';
    IF v_components IS NULL OR jsonb_typeof(v_components) = 'null' THEN
        v_codes := array_append(v_codes, 'PRICE_COMPONENTS_MISSING');
    ELSIF jsonb_array_length(v_components) = 0 THEN
        v_codes := array_append(v_codes, 'PRICE_COMPONENTS_MISSING');
    ELSE
        IF EXISTS (SELECT 1 FROM jsonb_array_elements(v_components) AS x(component)
                   WHERE jsonb_typeof(x.component->'amount_vnd') = 'null') THEN
            v_codes := array_append(v_codes, 'COMPONENT_AMOUNT_MISSING');
        ELSIF v_total IS NOT NULL THEN
            SELECT sum((x.component->>'amount_vnd')::numeric) INTO v_component_total
            FROM jsonb_array_elements(v_components) AS x(component);
            IF v_component_total <> v_total THEN
                v_codes := array_append(v_codes, 'COMPONENT_TOTAL_MISMATCH');
            END IF;
        END IF;
        IF EXISTS (SELECT 1 FROM jsonb_array_elements(v_components) AS x(component)
                   WHERE x.component->>'amount_vnd' = '0') THEN
            v_codes := array_append(v_codes, 'COMPONENT_AMOUNT_ZERO_WARNING');
        END IF;
    END IF;

    IF jsonb_typeof(p_payload->'lines'->0->'amount_vnd') = 'null' THEN
        v_codes := array_append(v_codes, 'LINE_AMOUNT_MISSING');
    ELSIF v_total IS NOT NULL
          AND (p_payload->'lines'->0->>'amount_vnd')::numeric <> v_total THEN
        v_codes := array_append(v_codes, 'LINE_TOTAL_MISMATCH');
    END IF;

    IF p0_fixture.is_blank(p_payload->>'source_ref')
       OR p0_fixture.is_blank(p_payload->>'evidence_ref')
       OR jsonb_typeof(p_payload->'evidence_sha256') = 'null' THEN
        v_codes := array_append(v_codes, 'SOURCE_EVIDENCE_MISSING');
    END IF;
    IF left(p_payload->>'debt_period', 7) <> left(p_payload->>'warehouse_in_date', 7)
       AND (p0_fixture.is_blank(p_payload->>'period_override_reason')
            OR p0_fixture.is_blank(p_payload->>'period_override_evidence_ref')
            OR jsonb_typeof(p_payload->'period_override_evidence_sha256') = 'null') THEN
        v_codes := array_append(v_codes, 'PERIOD_OVERRIDE_EVIDENCE_MISSING');
    END IF;
    IF jsonb_typeof(p_payload->'trip_key') = 'null' THEN
        v_codes := array_append(v_codes, 'TRIP_KEY_MISSING');
    END IF;
    IF p0_fixture.strip_trip_whitespace(p_payload->>'booking_no') = '/' THEN
        v_codes := array_append(v_codes, 'BOOKING_PLACEHOLDER');
    END IF;
    SELECT array_agg(code ORDER BY code COLLATE "C") INTO v_codes FROM unnest(v_codes) AS x(code);
    RETURN coalesce(v_codes, ARRAY[]::text[]);
END $$;

-- Every period the revision touches must be open; rows are locked in a stable order.
CREATE FUNCTION p0_fixture.assert_periods_open(p_payload jsonb, p_stage text) RETURNS void
LANGUAGE plpgsql
SET search_path = pg_catalog, p0_fixture AS $$
DECLARE
    v_period text;
BEGIN
    FOR v_period IN
        SELECT required_period.debt_period
        FROM (
            SELECT p_payload->>'debt_period' AS debt_period
            UNION
            SELECT x.line->>'debt_period'
            FROM jsonb_array_elements(p_payload->'lines') AS x(line)
        ) AS required_period
        ORDER BY required_period.debt_period COLLATE "C"
    LOOP
        PERFORM 1 FROM p0_fixture.debt_period_state s
        WHERE s.debt_period = v_period AND s.state = 'open' FOR SHARE;
        IF NOT FOUND THEN
            RAISE EXCEPTION 'debt period is not open at %: %', p_stage, v_period USING ERRCODE = 'P0001';
        END IF;
    END LOOP;
END $$;

CREATE FUNCTION p0_fixture.assert_posting_date_not_future(p_payload jsonb, p_stage text) RETURNS void
LANGUAGE plpgsql
SET search_path = pg_catalog, p0_fixture AS $$
BEGIN
    IF (p_payload->>'posting_date')::date > (now() AT TIME ZONE 'Asia/Ho_Chi_Minh')::date THEN
        RAISE EXCEPTION 'posting date is in the future (%)', p_stage USING ERRCODE = 'P0001';
    END IF;
END $$;

CREATE FUNCTION p0_fixture.assert_opening_resolution(p_trip_key text, p_stage text) RETURNS void
LANGUAGE plpgsql
SET search_path = pg_catalog, p0_fixture AS $$
BEGIN
    PERFORM 1 FROM p0_fixture.trip_opening_resolution t
    WHERE t.trip_key = p_trip_key AND t.status = 'ABSENT_FROM_OPENING_APPROVED' FOR SHARE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'opening resolution is not ABSENT_FROM_OPENING_APPROVED at %; charge remains CHỜ KIỂM',
            p_stage USING ERRCODE = 'P0001';
    END IF;
END $$;

-- Approve: serializes per trip key and refuses a key another proposal already holds (approved or posted).
CREATE FUNCTION p0_fixture.assert_trip_not_claimed(p_trip_key text, p_proposal_id bigint) RETURNS void
LANGUAGE plpgsql
SET search_path = pg_catalog, p0_fixture AS $$
BEGIN
    PERFORM pg_advisory_xact_lock(hashtextextended('p0_fixture.trip_key:' || p_trip_key, 0));
    IF EXISTS (SELECT 1
               FROM p0_fixture.proposal o
               JOIN p0_fixture.business_revision orev ON orev.revision_id = o.current_revision_id
               WHERE orev.trip_key = p_trip_key AND o.proposal_id <> p_proposal_id
                 AND o.state IN ('approved', 'posted')) THEN
        RAISE EXCEPTION 'trip key already approved or posted by another proposal; charge remains CHỜ KIỂM'
            USING ERRCODE = 'P0001';
    END IF;
END $$;

-- Post: same serialization, refuses a key another proposal already posted. posting.trip_key UNIQUE is the
-- backstop when a REPEATABLE READ/SERIALIZABLE snapshot cannot see the other posting.
CREATE FUNCTION p0_fixture.assert_trip_not_posted(p_trip_key text, p_proposal_id bigint) RETURNS void
LANGUAGE plpgsql
SET search_path = pg_catalog, p0_fixture AS $$
BEGIN
    PERFORM pg_advisory_xact_lock(hashtextextended('p0_fixture.trip_key:' || p_trip_key, 0));
    IF EXISTS (SELECT 1 FROM p0_fixture.posting po
               WHERE po.trip_key = p_trip_key AND po.proposal_id <> p_proposal_id) THEN
        RAISE EXCEPTION 'trip key already posted by another proposal; charge remains CHỜ KIỂM'
            USING ERRCODE = 'P0001';
    END IF;
END $$;

CREATE FUNCTION p0_fixture.submit_revision(
    p_proposal_id bigint,
    p_payload_text text,
    p_actor_id uuid,
    p_session_id uuid
) RETURNS TABLE (
    proposal_id bigint,
    revision_id bigint,
    revision_no integer,
    content_sha256 text,
    revision_created boolean
)
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, p0_fixture AS $$
DECLARE
    v_canonical jsonb;
    v_hash text;
    v_codes text[];
    v_trip_key text;
    v_proposal_id bigint;
    v_revision_id bigint;
    v_revision_no integer;
    v_proposal p0_fixture.proposal%ROWTYPE;
    v_current_hash text;
BEGIN
    PERFORM p0_fixture.require_actor(p_actor_id, p_session_id, 'maker');
    IF p_payload_text IS NULL OR length(p_payload_text) > 65536 THEN
        RAISE EXCEPTION 'invalid fixture payload length' USING ERRCODE = 'P0001';
    END IF;
    -- jsonb normalizes 1e2 and -0 and keeps 100.0, so number spelling is checked on the raw text
    -- with string contents removed.
    IF regexp_replace(p_payload_text, '"(?:[^"\\]|\\.)*"', '""', 'g') ~ '[0-9][.eE]|-0([^0-9]|$)' THEN
        RAISE EXCEPTION 'fixture numbers must be canonical JSON integers' USING ERRCODE = 'P0001';
    END IF;
    v_canonical := p0_fixture.canonicalize_payload(p_payload_text::jsonb);
    PERFORM p0_fixture.assert_posting_date_not_future(v_canonical, 'submission');
    v_codes := p0_fixture.charge_review_reason_codes(v_canonical);
    v_trip_key := v_canonical->>'trip_key';
    v_hash := encode(sha256(convert_to(
        'webdebit.business-payload.v3' || E'\n' || v_canonical::text, 'UTF8')), 'hex');

    IF p_proposal_id IS NOT NULL THEN
        SELECT p.* INTO v_proposal
        FROM p0_fixture.proposal p WHERE p.proposal_id = p_proposal_id FOR UPDATE;
        IF NOT FOUND OR v_proposal.maker_actor_id <> p_actor_id OR v_proposal.state = 'posted' THEN
            RAISE EXCEPTION 'proposal unavailable to this maker' USING ERRCODE = 'P0001';
        END IF;
    END IF;

    IF p_proposal_id IS NULL THEN
        INSERT INTO p0_fixture.proposal(maker_actor_id) VALUES (p_actor_id)
        RETURNING p0_fixture.proposal.proposal_id INTO v_proposal_id;
        v_revision_no := 1;
    ELSE
        SELECT r.content_sha256 INTO v_current_hash
        FROM p0_fixture.business_revision r
        WHERE r.proposal_id = p_proposal_id AND r.revision_id = v_proposal.current_revision_id;
        IF v_current_hash = v_hash THEN
            INSERT INTO p0_fixture.audit(proposal_id, revision_id, content_sha256,
                app_actor_id, app_session_id, database_session_user, action)
            VALUES (p_proposal_id, v_proposal.current_revision_id, v_current_hash,
                p_actor_id, p_session_id, session_user, 'submit_noop');
            RETURN QUERY SELECT p_proposal_id, v_proposal.current_revision_id,
                v_proposal.revision_no, v_current_hash, false;
            RETURN;
        END IF;
        v_proposal_id := p_proposal_id;
        v_revision_no := v_proposal.revision_no + 1;
    END IF;

    INSERT INTO p0_fixture.business_revision(proposal_id, revision_no, canonical_payload,
        content_sha256, trip_key, review_reason_codes, created_by_actor, created_in_session)
    VALUES (v_proposal_id, v_revision_no, v_canonical, v_hash, v_trip_key, v_codes,
        p_actor_id, p_session_id)
    RETURNING p0_fixture.business_revision.revision_id INTO v_revision_id;
    UPDATE p0_fixture.proposal
    SET current_revision_id = v_revision_id, revision_no = v_revision_no, state = 'review_needed'
    WHERE p0_fixture.proposal.proposal_id = v_proposal_id;
    INSERT INTO p0_fixture.audit(proposal_id, revision_id, content_sha256,
        app_actor_id, app_session_id, database_session_user, action)
    VALUES (v_proposal_id, v_revision_id, v_hash, p_actor_id, p_session_id, session_user, 'submit');
    RETURN QUERY SELECT v_proposal_id, v_revision_id, v_revision_no, v_hash, true;
END $$;

CREATE FUNCTION p0_fixture.fixture_review_projection(p_proposal_id bigint) RETURNS jsonb
LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = pg_catalog, p0_fixture AS $$
    SELECT jsonb_build_object(
        'proposal_id', p.proposal_id,
        'state', p.state,
        'revision_no', p.revision_no,
        'current_revision_id', p.current_revision_id,
        'revisions', coalesce((
            SELECT jsonb_agg(jsonb_build_object(
                'revision_id', r.revision_id,
                'revision_no', r.revision_no,
                'payload', r.canonical_payload,
                'content_sha256', r.content_sha256,
                'is_current_revision', r.revision_id = p.current_revision_id,
                'submit_time_reasons', to_jsonb(r.review_reason_codes),
                'warnings', (
                    SELECT coalesce(to_jsonb(array_agg(w.code ORDER BY w.code COLLATE "C")), '[]'::jsonb)
                    FROM (
                        SELECT c.code FROM unnest(r.review_reason_codes) AS c(code)
                        WHERE c.code LIKE '%\_WARNING'
                        UNION
                        SELECT 'DUPLICATE_TRIP_KEY_PENDING_WARNING'
                        WHERE r.revision_id = p.current_revision_id
                          AND r.trip_key IS NOT NULL
                          AND NOT ('BOOKING_PLACEHOLDER' = ANY(r.review_reason_codes))
                          AND EXISTS (
                            SELECT 1 FROM p0_fixture.proposal o
                            JOIN p0_fixture.business_revision orev ON orev.revision_id = o.current_revision_id
                            WHERE orev.trip_key = r.trip_key AND o.proposal_id <> p.proposal_id
                              AND o.state = 'review_needed'
                          )
                    ) AS w
                ),
                'current_blockers', CASE WHEN r.revision_id <> p.current_revision_id
                    THEN '[]'::jsonb
                    ELSE coalesce((
                        SELECT to_jsonb(array_agg(b.blocker ORDER BY b.blocker COLLATE "C"))
                        FROM (
                            SELECT c.code AS blocker
                            FROM unnest(r.review_reason_codes) AS c(code)
                            WHERE c.code NOT LIKE '%\_WARNING'
                            UNION
                            SELECT 'DEBT_PERIOD_NOT_OPEN'
                            WHERE EXISTS (
                                SELECT 1
                                FROM (
                                    SELECT r.canonical_payload->>'debt_period' AS debt_period
                                    UNION
                                    SELECT x.line->>'debt_period'
                                    FROM jsonb_array_elements(r.canonical_payload->'lines') AS x(line)
                                ) AS required_periods
                                LEFT JOIN p0_fixture.debt_period_state s
                                  ON s.debt_period = required_periods.debt_period
                                WHERE s.state IS DISTINCT FROM 'open'
                            )
                            UNION
                            SELECT 'PERIOD_CONFIRMATION_MISSING'
                            WHERE NOT EXISTS (
                                SELECT 1 FROM p0_fixture.period_confirmation c
                                WHERE c.proposal_id = p.proposal_id
                                  AND c.revision_id = r.revision_id
                                  AND c.content_sha256 = r.content_sha256
                                  AND c.maker_actor_id = p.maker_actor_id
                            )
                            UNION
                            SELECT 'PRICE_CONFIRMATION_MISSING'
                            WHERE NOT EXISTS (
                                SELECT 1 FROM p0_fixture.price_confirmation c
                                WHERE c.proposal_id = p.proposal_id
                                  AND c.revision_id = r.revision_id
                                  AND c.content_sha256 = r.content_sha256
                            )
                            UNION
                            SELECT 'OPENING_RESOLUTION_MISSING'
                            WHERE NOT EXISTS (
                                SELECT 1 FROM p0_fixture.trip_opening_resolution t
                                WHERE t.trip_key = r.trip_key
                                  AND t.status = 'ABSENT_FROM_OPENING_APPROVED'
                            )
                            UNION
                            SELECT 'DUPLICATE_TRIP_KEY'
                            WHERE r.trip_key IS NOT NULL
                              AND NOT ('BOOKING_PLACEHOLDER' = ANY(r.review_reason_codes))
                              AND EXISTS (
                                SELECT 1 FROM p0_fixture.proposal o
                                JOIN p0_fixture.business_revision orev ON orev.revision_id = o.current_revision_id
                                WHERE orev.trip_key = r.trip_key AND o.proposal_id <> p.proposal_id
                                  AND o.state IN ('approved', 'posted')
                              )
                        ) AS b
                    ), '[]'::jsonb)
                END
            ) ORDER BY r.revision_no)
            FROM p0_fixture.business_revision r
            WHERE r.proposal_id = p.proposal_id
        ), '[]'::jsonb)
    )
    FROM p0_fixture.proposal p
    WHERE p.proposal_id = p_proposal_id
$$;

CREATE FUNCTION p0_fixture.confirm_price_revision(
    p_proposal_id bigint,
    p_revision_id bigint,
    p_content_sha256 text,
    p_actor_id uuid,
    p_session_id uuid
) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, p0_fixture AS $$
DECLARE
    v_proposal p0_fixture.proposal%ROWTYPE;
    v_revision p0_fixture.business_revision%ROWTYPE;
BEGIN
    PERFORM p0_fixture.require_actor(p_actor_id, p_session_id, 'price_owner');
    IF p_proposal_id IS NULL OR p_revision_id IS NULL OR p_content_sha256 IS NULL THEN
        RAISE EXCEPTION 'proposal, revision and content hash are required' USING ERRCODE = 'P0001';
    END IF;
    SELECT * INTO v_proposal FROM p0_fixture.proposal
    WHERE proposal_id = p_proposal_id FOR UPDATE;
    IF v_proposal.proposal_id IS NULL THEN
        RAISE EXCEPTION 'proposal unavailable to price confirmation' USING ERRCODE = 'P0001';
    END IF;
    SELECT * INTO v_revision FROM p0_fixture.business_revision
    WHERE proposal_id = p_proposal_id AND revision_id = p_revision_id;
    IF v_proposal.state <> 'review_needed'
       OR v_proposal.current_revision_id IS DISTINCT FROM p_revision_id
       OR v_revision.content_sha256 IS DISTINCT FROM p_content_sha256 THEN
        RAISE EXCEPTION 'price confirmation requires the current charge revision' USING ERRCODE = 'P0001';
    END IF;
    -- Zero components are a warning only (PRICE-ZERO); everything else below blocks.
    IF v_revision.review_reason_codes && ARRAY[
        'TOTAL_MISSING', 'TOTAL_ZERO', 'PRICE_COMPONENTS_MISSING',
        'COMPONENT_AMOUNT_MISSING', 'COMPONENT_TOTAL_MISMATCH',
        'LINE_AMOUNT_MISSING', 'LINE_TOTAL_MISMATCH', 'SOURCE_EVIDENCE_MISSING'
    ] THEN
        RAISE EXCEPTION 'price confirmation requires complete positive matching price and source evidence'
            USING ERRCODE = 'P0001';
    END IF;
    INSERT INTO p0_fixture.price_confirmation(proposal_id, revision_id, content_sha256,
        confirmer_actor_id, confirmer_session_id, database_session_user)
    VALUES (p_proposal_id, p_revision_id, p_content_sha256, p_actor_id, p_session_id, session_user);
    INSERT INTO p0_fixture.audit(proposal_id, revision_id, content_sha256,
        app_actor_id, app_session_id, database_session_user, action)
    VALUES (p_proposal_id, p_revision_id, p_content_sha256, p_actor_id, p_session_id,
        session_user, 'confirm_price');
END $$;

CREATE FUNCTION p0_fixture.confirm_period_revision(
    p_proposal_id bigint,
    p_revision_id bigint,
    p_content_sha256 text,
    p_actor_id uuid,
    p_session_id uuid
) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, p0_fixture AS $$
DECLARE
    v_proposal p0_fixture.proposal%ROWTYPE;
    v_revision p0_fixture.business_revision%ROWTYPE;
BEGIN
    PERFORM p0_fixture.require_actor(p_actor_id, p_session_id, 'maker');
    IF p_proposal_id IS NULL OR p_revision_id IS NULL OR p_content_sha256 IS NULL THEN
        RAISE EXCEPTION 'proposal, revision and content hash are required' USING ERRCODE = 'P0001';
    END IF;
    SELECT * INTO v_proposal FROM p0_fixture.proposal
    WHERE proposal_id = p_proposal_id FOR UPDATE;
    IF v_proposal.proposal_id IS NULL THEN
        RAISE EXCEPTION 'proposal unavailable to period confirmation' USING ERRCODE = 'P0001';
    END IF;
    SELECT * INTO v_revision FROM p0_fixture.business_revision
    WHERE proposal_id = p_proposal_id AND revision_id = p_revision_id;
    IF v_proposal.state <> 'review_needed'
       OR v_proposal.maker_actor_id <> p_actor_id
       OR v_proposal.current_revision_id IS DISTINCT FROM p_revision_id
       OR v_revision.content_sha256 IS DISTINCT FROM p_content_sha256 THEN
        RAISE EXCEPTION 'period confirmation requires current charge revision from its maker'
            USING ERRCODE = 'P0001';
    END IF;
    IF 'PERIOD_OVERRIDE_EVIDENCE_MISSING' = ANY(v_revision.review_reason_codes) THEN
        RAISE EXCEPTION 'period override evidence is required for cross-month charge confirmation'
            USING ERRCODE = 'P0001';
    END IF;
    PERFORM 1 FROM p0_fixture.debt_period_state s
        WHERE s.debt_period = v_revision.canonical_payload->>'debt_period'
          AND s.state = 'open' FOR SHARE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'debt period is not open for maker confirmation' USING ERRCODE = 'P0001';
    END IF;
    INSERT INTO p0_fixture.period_confirmation(proposal_id, revision_id, content_sha256,
        maker_actor_id, maker_session_id, database_session_user)
    VALUES (p_proposal_id, p_revision_id, p_content_sha256, p_actor_id, p_session_id, session_user);
    INSERT INTO p0_fixture.audit(proposal_id, revision_id, content_sha256,
        app_actor_id, app_session_id, database_session_user, action)
    VALUES (p_proposal_id, p_revision_id, p_content_sha256, p_actor_id, p_session_id,
        session_user, 'confirm_period');
END $$;

CREATE FUNCTION p0_fixture.set_presentation_title(
    p_proposal_id bigint,
    p_title text,
    p_actor_id uuid,
    p_session_id uuid
) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, p0_fixture AS $$
DECLARE
    v_maker uuid;
BEGIN
    IF p_title IS NULL OR length(p_title) > 160 THEN
        RAISE EXCEPTION 'invalid presentation title' USING ERRCODE = 'P0001';
    END IF;
    PERFORM p0_fixture.require_actor(p_actor_id, p_session_id, 'maker');
    SELECT p.maker_actor_id INTO v_maker FROM p0_fixture.proposal p
    WHERE p.proposal_id = p_proposal_id FOR UPDATE;
    IF NOT FOUND OR v_maker <> p_actor_id THEN
        RAISE EXCEPTION 'proposal unavailable to this maker' USING ERRCODE = 'P0001';
    END IF;
    UPDATE p0_fixture.proposal SET presentation_title = p_title
    WHERE p0_fixture.proposal.proposal_id = p_proposal_id;
    INSERT INTO p0_fixture.audit(proposal_id, revision_id, content_sha256,
        app_actor_id, app_session_id, database_session_user, action)
    SELECT p.proposal_id, p.current_revision_id, r.content_sha256, p_actor_id, p_session_id,
        session_user, 'presentation'
    FROM p0_fixture.proposal p
    JOIN p0_fixture.business_revision r ON r.revision_id = p.current_revision_id
    WHERE p.proposal_id = p_proposal_id;
END $$;

CREATE FUNCTION p0_fixture.approve_revision(
    p_proposal_id bigint,
    p_revision_id bigint,
    p_content_sha256 text,
    p_actor_id uuid,
    p_session_id uuid
) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, p0_fixture AS $$
DECLARE
    v_proposal p0_fixture.proposal%ROWTYPE;
    v_revision p0_fixture.business_revision%ROWTYPE;
BEGIN
    PERFORM p0_fixture.require_actor(p_actor_id, p_session_id, 'checker');
    IF p_proposal_id IS NULL OR p_revision_id IS NULL OR p_content_sha256 IS NULL THEN
        RAISE EXCEPTION 'proposal, revision and content hash are required' USING ERRCODE = 'P0001';
    END IF;
    SELECT * INTO v_proposal FROM p0_fixture.proposal
    WHERE proposal_id = p_proposal_id FOR UPDATE;
    IF v_proposal.proposal_id IS NULL THEN
        RAISE EXCEPTION 'proposal unavailable for approval' USING ERRCODE = 'P0001';
    END IF;
    SELECT r.* INTO v_revision FROM p0_fixture.business_revision r
    WHERE r.proposal_id = p_proposal_id AND r.revision_id = p_revision_id;
    IF NOT FOUND
       OR v_proposal.state <> 'review_needed'
       OR v_proposal.current_revision_id IS DISTINCT FROM p_revision_id
       OR v_revision.content_sha256 IS DISTINCT FROM p_content_sha256
       OR v_proposal.maker_actor_id = p_actor_id THEN
        RAISE EXCEPTION 'stale, unavailable, or self-approved revision' USING ERRCODE = 'P0001';
    END IF;
    PERFORM p0_fixture.assert_periods_open(v_revision.canonical_payload, 'approval');
    PERFORM p0_fixture.assert_posting_date_not_future(v_revision.canonical_payload, 'approval');
    IF NOT EXISTS (SELECT 1 FROM p0_fixture.period_confirmation c
        WHERE c.proposal_id = p_proposal_id AND c.revision_id = p_revision_id
          AND c.content_sha256 = p_content_sha256
          AND c.maker_actor_id = v_proposal.maker_actor_id) THEN
        RAISE EXCEPTION 'maker confirmation required for this debt period revision' USING ERRCODE = 'P0001';
    END IF;
    IF v_revision.trip_key IS NULL OR 'BOOKING_PLACEHOLDER' = ANY(v_revision.review_reason_codes) THEN
        RAISE EXCEPTION 'trip key missing or placeholder booking; charge remains CHỜ KIỂM' USING ERRCODE = 'P0001';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM p0_fixture.price_confirmation c
        WHERE c.proposal_id = p_proposal_id AND c.revision_id = p_revision_id
          AND c.content_sha256 = p_content_sha256) THEN
        RAISE EXCEPTION 'per-trip price confirmation required for this revision' USING ERRCODE = 'P0001';
    END IF;
    IF EXISTS (SELECT 1 FROM p0_fixture.price_confirmation c
        WHERE c.proposal_id = p_proposal_id AND c.revision_id = p_revision_id
          AND c.content_sha256 = p_content_sha256 AND c.confirmer_actor_id = p_actor_id) THEN
        RAISE EXCEPTION 'price confirmer cannot checker-approve the same revision' USING ERRCODE = 'P0001';
    END IF;
    PERFORM p0_fixture.assert_opening_resolution(v_revision.trip_key, 'approval');
    PERFORM p0_fixture.assert_trip_not_claimed(v_revision.trip_key, p_proposal_id);
    INSERT INTO p0_fixture.approval(proposal_id, revision_id, content_sha256,
        checker_actor_id, checker_session_id, database_session_user)
    VALUES (p_proposal_id, p_revision_id, p_content_sha256, p_actor_id, p_session_id, session_user);
    UPDATE p0_fixture.proposal SET state = 'approved'
    WHERE p0_fixture.proposal.proposal_id = p_proposal_id;
    INSERT INTO p0_fixture.audit(proposal_id, revision_id, content_sha256,
        app_actor_id, app_session_id, database_session_user, action)
    VALUES (p_proposal_id, p_revision_id, p_content_sha256, p_actor_id, p_session_id,
        session_user, 'approve');
END $$;

CREATE FUNCTION p0_fixture.post_revision(
    p_proposal_id bigint,
    p_revision_id bigint,
    p_content_sha256 text,
    p_actor_id uuid,
    p_session_id uuid
) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, p0_fixture AS $$
DECLARE
    v_proposal p0_fixture.proposal%ROWTYPE;
    v_approval p0_fixture.approval%ROWTYPE;
    v_revision p0_fixture.business_revision%ROWTYPE;
BEGIN
    PERFORM p0_fixture.require_actor(p_actor_id, p_session_id, 'checker');
    IF p_proposal_id IS NULL OR p_revision_id IS NULL OR p_content_sha256 IS NULL THEN
        RAISE EXCEPTION 'proposal, revision and content hash are required' USING ERRCODE = 'P0001';
    END IF;
    SELECT * INTO v_proposal FROM p0_fixture.proposal
    WHERE proposal_id = p_proposal_id FOR UPDATE;
    IF v_proposal.proposal_id IS NULL THEN
        RAISE EXCEPTION 'proposal unavailable for posting' USING ERRCODE = 'P0001';
    END IF;
    SELECT * INTO v_revision FROM p0_fixture.business_revision
    WHERE proposal_id = p_proposal_id AND revision_id = p_revision_id;
    SELECT * INTO v_approval FROM p0_fixture.approval
    WHERE proposal_id = p_proposal_id AND revision_id = p_revision_id
      AND content_sha256 = p_content_sha256;
    IF NOT FOUND
       OR v_proposal.state <> 'approved'
       OR v_proposal.current_revision_id IS DISTINCT FROM p_revision_id
       OR v_revision.content_sha256 IS DISTINCT FROM p_content_sha256
       OR v_approval.checker_actor_id IS DISTINCT FROM p_actor_id
       OR v_proposal.maker_actor_id = p_actor_id THEN
        RAISE EXCEPTION 'current approved revision required for posting' USING ERRCODE = 'P0001';
    END IF;
    PERFORM p0_fixture.assert_periods_open(v_revision.canonical_payload, 'posting');
    PERFORM p0_fixture.assert_posting_date_not_future(v_revision.canonical_payload, 'posting');
    IF NOT EXISTS (SELECT 1 FROM p0_fixture.period_confirmation c
        WHERE c.proposal_id = p_proposal_id AND c.revision_id = p_revision_id
          AND c.content_sha256 = p_content_sha256
          AND c.maker_actor_id = v_proposal.maker_actor_id)
       OR NOT EXISTS (SELECT 1 FROM p0_fixture.price_confirmation c
        WHERE c.proposal_id = p_proposal_id AND c.revision_id = p_revision_id
          AND c.content_sha256 = p_content_sha256) THEN
        RAISE EXCEPTION 'period and price confirmations are required at posting' USING ERRCODE = 'P0001';
    END IF;
    IF EXISTS (SELECT 1 FROM p0_fixture.price_confirmation c
        WHERE c.proposal_id = p_proposal_id AND c.revision_id = p_revision_id
          AND c.content_sha256 = p_content_sha256 AND c.confirmer_actor_id = p_actor_id) THEN
        RAISE EXCEPTION 'price confirmer cannot post as checker of the same revision' USING ERRCODE = 'P0001';
    END IF;
    PERFORM p0_fixture.assert_opening_resolution(v_revision.trip_key, 'posting');
    PERFORM p0_fixture.assert_trip_not_posted(v_revision.trip_key, p_proposal_id);
    INSERT INTO p0_fixture.posting(proposal_id, revision_id, approval_id, content_sha256, trip_key,
        canonical_payload, maker_actor_id, checker_actor_id, posted_in_session, database_session_user)
    VALUES (p_proposal_id, p_revision_id, v_approval.approval_id, p_content_sha256,
        v_revision.trip_key, v_revision.canonical_payload, v_proposal.maker_actor_id, p_actor_id,
        p_session_id, session_user);
    UPDATE p0_fixture.proposal SET state = 'posted'
    WHERE p0_fixture.proposal.proposal_id = p_proposal_id;
    INSERT INTO p0_fixture.audit(proposal_id, revision_id, content_sha256,
        app_actor_id, app_session_id, database_session_user, action)
    VALUES (p_proposal_id, p_revision_id, p_content_sha256, p_actor_id, p_session_id,
        session_user, 'post');
END $$;

CREATE FUNCTION p0_fixture.inject_post_failure() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog, p0_fixture AS $$
BEGIN
    IF current_setting('p0_fixture.fail_post', true) = 'on' THEN
        RAISE EXCEPTION 'injected deferred fixture failure' USING ERRCODE = 'P0001';
    END IF;
    RETURN NEW;
END $$;

CREATE CONSTRAINT TRIGGER fixture_post_failure
    AFTER INSERT ON p0_fixture.posting
    DEFERRABLE INITIALLY DEFERRED
    FOR EACH ROW EXECUTE FUNCTION p0_fixture.inject_post_failure();

INSERT INTO p0_fixture.app_actor(actor_id, active) VALUES
    ('11111111-1111-4111-8111-111111111111', true),
    ('22222222-2222-4222-8222-222222222222', true),
    ('33333333-3333-4333-8333-333333333333', false),
    ('44444444-4444-4444-8444-444444444444', true),
    ('55555555-5555-4555-8555-555555555555', true);
INSERT INTO p0_fixture.app_actor_role(actor_id, app_role) VALUES
    ('11111111-1111-4111-8111-111111111111', 'maker'),
    ('11111111-1111-4111-8111-111111111111', 'checker'),
    ('11111111-1111-4111-8111-111111111111', 'price_owner'),
    ('22222222-2222-4222-8222-222222222222', 'checker'),
    ('33333333-3333-4333-8333-333333333333', 'maker'),
    ('33333333-3333-4333-8333-333333333333', 'price_owner'),
    ('44444444-4444-4444-8444-444444444444', 'maker'),
    ('55555555-5555-4555-8555-555555555555', 'price_owner'),
    ('55555555-5555-4555-8555-555555555555', 'checker');
INSERT INTO p0_fixture.debt_period_state(debt_period, state) VALUES
    ('2026-08', 'closed'),
    ('2026-09', 'open'),
    ('2026-10', 'open'),
    ('2026-11', 'open');

RESET ROLE;

REVOKE ALL ON ALL TABLES IN SCHEMA p0_fixture FROM PUBLIC, p0_fixture_api;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA p0_fixture FROM PUBLIC, p0_fixture_api;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA p0_fixture FROM PUBLIC;
GRANT EXECUTE ON FUNCTION p0_fixture.submit_revision(bigint,text,uuid,uuid) TO p0_fixture_api;
GRANT EXECUTE ON FUNCTION p0_fixture.set_presentation_title(bigint,text,uuid,uuid) TO p0_fixture_api;
GRANT EXECUTE ON FUNCTION p0_fixture.confirm_price_revision(bigint,bigint,text,uuid,uuid) TO p0_fixture_api;
GRANT EXECUTE ON FUNCTION p0_fixture.confirm_period_revision(bigint,bigint,text,uuid,uuid) TO p0_fixture_api;
GRANT EXECUTE ON FUNCTION p0_fixture.approve_revision(bigint,bigint,text,uuid,uuid) TO p0_fixture_api;
GRANT EXECUTE ON FUNCTION p0_fixture.post_revision(bigint,bigint,text,uuid,uuid) TO p0_fixture_api;
