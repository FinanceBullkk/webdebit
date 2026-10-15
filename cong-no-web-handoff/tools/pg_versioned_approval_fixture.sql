-- Acceptance fixture only. Never deploy or apply to hao/production.
\set ON_ERROR_STOP on

CREATE EXTENSION IF NOT EXISTS pgcrypto WITH SCHEMA public;
CREATE ROLE p0_fixture_owner NOLOGIN;
CREATE ROLE p0_fixture_api NOLOGIN;
CREATE ROLE p0_fixture_identity_test_api NOLOGIN;
GRANT CONNECT ON DATABASE webdebit_ledger TO p0_fixture_api, p0_fixture_identity_test_api;
CREATE SCHEMA p0_fixture AUTHORIZATION p0_fixture_owner;
REVOKE ALL ON SCHEMA p0_fixture FROM PUBLIC;
GRANT USAGE ON SCHEMA p0_fixture TO p0_fixture_api, p0_fixture_identity_test_api;

SET ROLE p0_fixture_owner;

CREATE TABLE p0_fixture.app_actor (
    actor_id uuid PRIMARY KEY,
    active boolean NOT NULL DEFAULT true
);

CREATE TABLE p0_fixture.app_actor_role (
    actor_id uuid NOT NULL REFERENCES p0_fixture.app_actor,
    app_role text NOT NULL CHECK (app_role IN ('maker', 'checker', 'price_owner', 'admin')),
    PRIMARY KEY (actor_id, app_role)
);

CREATE TABLE p0_fixture.actor_signing_key (
    key_id text PRIMARY KEY,
    secret bytea NOT NULL CHECK (octet_length(secret) >= 32),
    active boolean NOT NULL DEFAULT true
);

CREATE TABLE p0_fixture.debt_period_state (
    debt_period text PRIMARY KEY CHECK (debt_period ~ '^\d{4}-(0[1-9]|1[0-2])$'),
    state text NOT NULL CHECK (state IN ('open', 'closed'))
);

CREATE TABLE p0_fixture.used_assertion_nonce (
    nonce uuid PRIMARY KEY,
    actor_id uuid NOT NULL REFERENCES p0_fixture.app_actor,
    session_id uuid NOT NULL,
    used_at timestamptz NOT NULL DEFAULT clock_timestamp()
);

CREATE TABLE p0_fixture.proposal (
    proposal_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    maker_actor_id uuid NOT NULL REFERENCES p0_fixture.app_actor,
    kind text NOT NULL CHECK (kind IN ('revision_fixture', 'charge_fixture')),
    current_revision_id bigint,
    revision_no integer NOT NULL DEFAULT 0 CHECK (revision_no >= 0),
    state text NOT NULL DEFAULT 'pending' CHECK (state IN ('pending', 'review_needed', 'approved', 'posted')),
    presentation_title text NOT NULL DEFAULT '',
    created_at timestamptz NOT NULL DEFAULT clock_timestamp()
);

CREATE TABLE p0_fixture.business_revision (
    revision_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    proposal_id bigint NOT NULL REFERENCES p0_fixture.proposal,
    revision_no integer NOT NULL CHECK (revision_no > 0),
    canonical_payload jsonb NOT NULL,
    content_sha256 text NOT NULL CHECK (content_sha256 ~ '^[0-9a-f]{64}$'),
    review_reason_codes text[] NOT NULL DEFAULT ARRAY[]::text[],
    created_by_actor uuid NOT NULL REFERENCES p0_fixture.app_actor,
    created_in_session uuid NOT NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    UNIQUE (proposal_id, revision_no),
    UNIQUE (proposal_id, revision_id),
    UNIQUE (proposal_id, revision_id, content_sha256)
);

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

ALTER TABLE p0_fixture.proposal
    ADD CONSTRAINT current_revision_belongs_to_proposal
    FOREIGN KEY (proposal_id, current_revision_id)
    REFERENCES p0_fixture.business_revision (proposal_id, revision_id)
    DEFERRABLE INITIALLY DEFERRED;

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

CREATE TABLE p0_fixture.price_confirmation (
    confirmation_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    proposal_id bigint NOT NULL,
    revision_id bigint NOT NULL,
    content_sha256 text NOT NULL,
    owner_actor_id uuid NOT NULL REFERENCES p0_fixture.app_actor,
    owner_session_id uuid NOT NULL,
    database_session_user name NOT NULL,
    confirmed_at timestamptz NOT NULL DEFAULT clock_timestamp(),
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

CREATE TABLE p0_fixture.audit (
    audit_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    proposal_id bigint NOT NULL REFERENCES p0_fixture.proposal,
    revision_id bigint,
    content_sha256 text,
    app_actor_id uuid NOT NULL REFERENCES p0_fixture.app_actor,
    app_session_id uuid NOT NULL,
    assertion_nonce uuid NOT NULL REFERENCES p0_fixture.used_assertion_nonce,
    key_id text NOT NULL,
    database_session_user name NOT NULL,
    action text NOT NULL CHECK (action IN ('submit', 'submit_noop', 'presentation',
        'confirm_price', 'confirm_period', 'approve', 'post')),
    request_scope text NOT NULL,
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

CREATE FUNCTION p0_fixture.reject_proposal_kind_change() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog AS $$
BEGIN
    IF NEW.kind IS DISTINCT FROM OLD.kind THEN
        RAISE EXCEPTION 'proposal kind is immutable' USING ERRCODE = 'P0001';
    END IF;
    RETURN NEW;
END $$;

CREATE TRIGGER proposal_kind_immutable
    BEFORE UPDATE OF kind ON p0_fixture.proposal
    FOR EACH ROW EXECUTE FUNCTION p0_fixture.reject_proposal_kind_change();

CREATE FUNCTION p0_fixture.assert_fixture_kind_access(p_kind text) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog AS $$
BEGIN
    IF p_kind = 'charge_fixture' THEN
        IF NOT pg_has_role(session_user, 'p0_fixture_api', 'member') THEN
            RAISE EXCEPTION 'database principal cannot use charge_fixture' USING ERRCODE = 'P0001';
        END IF;
    ELSIF p_kind = 'revision_fixture' THEN
        IF NOT pg_has_role(session_user, 'p0_fixture_identity_test_api', 'member') THEN
            RAISE EXCEPTION 'database principal cannot use revision_fixture' USING ERRCODE = 'P0001';
        END IF;
    ELSE
        RAISE EXCEPTION 'unknown fixture kind' USING ERRCODE = 'P0001';
    END IF;
END $$;

CREATE FUNCTION p0_fixture.verify_actor_assertion(
    p_actor_id uuid,
    p_session_id uuid,
    p_action text,
    p_nonce uuid,
    p_issued_epoch bigint,
    p_key_id text,
    p_scope text,
    p_signature text
) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, p0_fixture, public AS $$
DECLARE
    v_secret bytea;
    v_expected bytea;
    v_message text;
    v_rows integer;
    v_role text;
    v_actor uuid;
BEGIN
    IF p_action IS NULL OR p_issued_epoch IS NULL
       OR p_action NOT IN ('submit', 'presentation', 'confirm_price', 'confirm_period', 'approve', 'post')
       OR p_actor_id IS NULL OR p_session_id IS NULL OR p_nonce IS NULL
       OR p_key_id IS NULL OR btrim(p_key_id) = '' OR p_scope IS NULL
       OR btrim(p_scope) = '' OR length(p_scope) > 512
       OR p_issued_epoch < floor(extract(epoch FROM clock_timestamp()))::bigint - 120
       OR p_issued_epoch > floor(extract(epoch FROM clock_timestamp()))::bigint + 30
       OR p_signature IS NULL OR p_signature !~ '^[0-9a-f]{64}$' THEN
        RAISE EXCEPTION 'invalid actor assertion' USING ERRCODE = 'P0001';
    END IF;
    IF NOT (pg_has_role(session_user, 'p0_fixture_api', 'member')
            OR pg_has_role(session_user, 'p0_fixture_identity_test_api', 'member')) THEN
        RAISE EXCEPTION 'untrusted database principal' USING ERRCODE = 'P0001';
    END IF;
    SELECT a.actor_id INTO v_actor FROM p0_fixture.app_actor a
    WHERE a.actor_id = p_actor_id AND a.active FOR SHARE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'inactive actor' USING ERRCODE = 'P0001';
    END IF;
    v_role := CASE p_action
        WHEN 'submit' THEN 'maker'
        WHEN 'presentation' THEN 'maker'
        WHEN 'confirm_price' THEN 'price_owner'
        WHEN 'confirm_period' THEN 'maker'
        ELSE 'checker'
    END;
    PERFORM 1 FROM p0_fixture.app_actor_role r
    WHERE r.actor_id = p_actor_id AND r.app_role = v_role FOR SHARE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'actor role required' USING ERRCODE = 'P0001';
    END IF;
    SELECT k.secret INTO v_secret
    FROM p0_fixture.actor_signing_key k
    WHERE k.key_id = p_key_id AND k.active;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'unknown signing key' USING ERRCODE = 'P0001';
    END IF;
    v_message := concat_ws(E'\n', 'webdebit-actor-assertion-v1', p_actor_id::text,
        p_session_id::text, p_action, p_nonce::text, p_issued_epoch::text, p_scope);
    v_expected := public.hmac(convert_to(v_message, 'UTF8'), v_secret, 'sha256');
    IF decode(p_signature, 'hex') IS DISTINCT FROM v_expected THEN
        RAISE EXCEPTION 'actor assertion signature or scope mismatch' USING ERRCODE = 'P0001';
    END IF;
    INSERT INTO p0_fixture.used_assertion_nonce(nonce, actor_id, session_id)
    VALUES (p_nonce, p_actor_id, p_session_id)
    ON CONFLICT (nonce) DO NOTHING;
    GET DIAGNOSTICS v_rows = ROW_COUNT;
    IF v_rows <> 1 THEN
        RAISE EXCEPTION 'actor assertion replay' USING ERRCODE = 'P0001';
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

CREATE FUNCTION p0_fixture.canonical_vnd(p_value jsonb, p_allow_pending boolean DEFAULT false) RETURNS numeric
LANGUAGE plpgsql IMMUTABLE
SET search_path = pg_catalog AS $$
DECLARE
    v_amount numeric;
BEGIN
    IF p_allow_pending AND (p_value IS NULL OR jsonb_typeof(p_value) = 'null') THEN
        RETURN NULL;
    END IF;
    IF jsonb_typeof(p_value) IS DISTINCT FROM 'number' THEN
        RAISE EXCEPTION 'fixture VND value must be a JSON number' USING ERRCODE = 'P0001';
    END IF;
    v_amount := p_value::text::numeric;
    IF v_amount::text IN ('NaN', 'Infinity', '-Infinity') THEN
        RAISE EXCEPTION 'fixture VND value must be finite' USING ERRCODE = 'P0001';
    END IF;
    IF v_amount < 0 OR (NOT p_allow_pending AND v_amount = 0)
       OR v_amount <> trunc(v_amount) THEN
        IF p_allow_pending THEN
            RAISE EXCEPTION 'fixture amount must be a nonnegative integer' USING ERRCODE = 'P0001';
        END IF;
        RAISE EXCEPTION 'fixture amount must be a positive integer' USING ERRCODE = 'P0001';
    END IF;
    RETURN trim_scale(v_amount);
END $$;

CREATE FUNCTION p0_fixture.canonicalize_payload(p_payload jsonb) RETURNS jsonb
LANGUAGE plpgsql IMMUTABLE
SET search_path = pg_catalog AS $$
DECLARE
    v_line jsonb;
    v_lines jsonb;
    v_components jsonb;
    v_component jsonb;
    v_line_count integer;
    v_unique_line_count integer;
    v_total numeric;
    v_kind text;
    v_event_date date;
BEGIN
    IF jsonb_typeof(p_payload) IS DISTINCT FROM 'object'
       OR jsonb_typeof(p_payload->'kind') IS DISTINCT FROM 'string' THEN
        RAISE EXCEPTION 'payload has missing or unknown business fields' USING ERRCODE = 'P0001';
    END IF;
    v_kind := p_payload->>'kind';
    IF v_kind NOT IN ('revision_fixture', 'charge_fixture') THEN
        RAISE EXCEPTION 'payload has missing or unknown business fields' USING ERRCODE = 'P0001';
    END IF;
    IF (v_kind = 'revision_fixture'
        AND ((SELECT count(*) FROM jsonb_object_keys(p_payload)) <> 12
            OR NOT p_payload ?& ARRAY['schema_version','kind','customer_id','debt_period',
                'total_vnd','event_date','posting_date','source_ref','evidence_ref',
                'evidence_sha256','reason','lines']))
       OR (v_kind = 'charge_fixture'
        AND (EXISTS (SELECT 1 FROM jsonb_object_keys(p_payload) AS k(key)
                WHERE k.key <> ALL (ARRAY['schema_version','kind','customer_id','debt_period',
                    'total_vnd','event_date','posting_date','source_ref','evidence_ref',
                    'evidence_sha256','reason','lines','trip_code','opening_snapshot_ref',
                    'opening_absence_evidence_ref','price_components','period_override_reason',
                    'period_override_evidence_ref','period_override_evidence_sha256']))
            OR NOT p_payload ?& ARRAY['schema_version','kind','customer_id','debt_period',
                'event_date','posting_date','reason','lines'])) THEN
        RAISE EXCEPTION 'payload has missing or unknown business fields' USING ERRCODE = 'P0001';
    END IF;
    IF jsonb_typeof(p_payload->'schema_version') IS DISTINCT FROM 'number' THEN
        RAISE EXCEPTION 'invalid fixture schema version' USING ERRCODE = 'P0001';
    END IF;
    IF (p_payload->>'schema_version')::numeric = 1 THEN
        RAISE EXCEPTION 'schema version 1 is unsupported; expected version 2' USING ERRCODE = 'P0001';
    END IF;
    IF (p_payload->>'schema_version')::numeric <> 2 THEN
        RAISE EXCEPTION 'unsupported fixture schema version; expected version 2' USING ERRCODE = 'P0001';
    END IF;
    IF jsonb_typeof(p_payload->'customer_id') IS DISTINCT FROM 'string'
       OR jsonb_typeof(p_payload->'debt_period') IS DISTINCT FROM 'string'
       OR jsonb_typeof(p_payload->'event_date') IS DISTINCT FROM 'string'
       OR jsonb_typeof(p_payload->'posting_date') IS DISTINCT FROM 'string'
       OR jsonb_typeof(p_payload->'reason') IS DISTINCT FROM 'string'
       OR jsonb_typeof(p_payload->'lines') IS DISTINCT FROM 'array' THEN
        RAISE EXCEPTION 'invalid fixture payload fields' USING ERRCODE = 'P0001';
    END IF;
    IF length(btrim(p_payload->>'customer_id')) = 0
       OR (p_payload->>'debt_period') COLLATE "C" !~ '^[0-9]{4}-(0[1-9]|1[0-2])$'
       OR length(btrim(p_payload->>'reason')) = 0 THEN
        RAISE EXCEPTION 'invalid fixture payload fields' USING ERRCODE = 'P0001';
    END IF;
    PERFORM p0_fixture.parse_iso_date((p_payload->>'debt_period') || '-01');
    IF v_kind = 'revision_fixture' THEN
        IF jsonb_typeof(p_payload->'source_ref') IS DISTINCT FROM 'string'
           OR jsonb_typeof(p_payload->'evidence_ref') IS DISTINCT FROM 'string'
           OR jsonb_typeof(p_payload->'evidence_sha256') IS DISTINCT FROM 'string' THEN
            RAISE EXCEPTION 'invalid fixture payload fields' USING ERRCODE = 'P0001';
        END IF;
        IF length(btrim(p_payload->>'source_ref')) = 0
           OR length(btrim(p_payload->>'evidence_ref')) = 0
           OR (p_payload->>'evidence_sha256') !~ '^[0-9a-f]{64}$' THEN
            RAISE EXCEPTION 'invalid fixture payload fields' USING ERRCODE = 'P0001';
        END IF;
    ELSE
        IF (p_payload->'source_ref' IS NOT NULL
                AND jsonb_typeof(p_payload->'source_ref') NOT IN ('null', 'string'))
           OR (p_payload->'evidence_ref' IS NOT NULL
                AND jsonb_typeof(p_payload->'evidence_ref') NOT IN ('null', 'string'))
           OR (p_payload->'evidence_sha256' IS NOT NULL
                AND jsonb_typeof(p_payload->'evidence_sha256') NOT IN ('null', 'string')) THEN
            RAISE EXCEPTION 'invalid fixture source/evidence fields' USING ERRCODE = 'P0001';
        END IF;
        IF jsonb_typeof(p_payload->'evidence_sha256') = 'string' THEN
            IF (p_payload->>'evidence_sha256') !~ '^[0-9a-f]{64}$' THEN
                RAISE EXCEPTION 'invalid fixture source/evidence fields' USING ERRCODE = 'P0001';
            END IF;
        END IF;
    END IF;

    v_total := p0_fixture.canonical_vnd(p_payload->'total_vnd', v_kind = 'charge_fixture');
    v_event_date := p0_fixture.parse_iso_date(p_payload->>'event_date');
    PERFORM p0_fixture.parse_iso_date(p_payload->>'posting_date');
    IF v_kind = 'charge_fixture' AND v_event_date < DATE '2026-10-14' THEN
        RAISE EXCEPTION 'charge event date before 2026-10-14' USING ERRCODE = 'P0001';
    END IF;

    SELECT count(*) INTO v_line_count
    FROM jsonb_array_elements(p_payload->'lines') AS x(line);
    IF v_line_count < 1 THEN
        RAISE EXCEPTION 'fixture line numbers must be unique' USING ERRCODE = 'P0001';
    END IF;
    IF v_kind = 'charge_fixture' AND v_line_count <> 1 THEN
        RAISE EXCEPTION 'charge must have exactly one debt line' USING ERRCODE = 'P0001';
    END IF;
    FOR v_line IN SELECT x.line FROM jsonb_array_elements(p_payload->'lines') AS x(line) LOOP
        IF jsonb_typeof(v_line) IS DISTINCT FROM 'object'
           OR (SELECT count(*) FROM jsonb_object_keys(v_line)) < 3
           OR EXISTS (SELECT 1 FROM jsonb_object_keys(v_line) AS k(key)
                WHERE k.key <> ALL (ARRAY['line_no','customer_id','debt_period','amount_vnd']))
           OR NOT v_line ?& ARRAY['line_no','customer_id','debt_period']
           OR (v_kind = 'revision_fixture' AND NOT v_line ? 'amount_vnd')
           OR jsonb_typeof(v_line->'line_no') IS DISTINCT FROM 'number'
           OR jsonb_typeof(v_line->'customer_id') IS DISTINCT FROM 'string'
           OR jsonb_typeof(v_line->'debt_period') IS DISTINCT FROM 'string' THEN
            RAISE EXCEPTION 'invalid fixture line' USING ERRCODE = 'P0001';
        END IF;
        IF (v_line->>'line_no')::integer < 1
           OR (v_line->>'line_no')::numeric <> trunc((v_line->>'line_no')::numeric)
           OR length(btrim(v_line->>'customer_id')) = 0
           OR (v_line->>'debt_period') COLLATE "C" !~ '^[0-9]{4}-(0[1-9]|1[0-2])$' THEN
            RAISE EXCEPTION 'invalid fixture line' USING ERRCODE = 'P0001';
        END IF;
        PERFORM p0_fixture.parse_iso_date((v_line->>'debt_period') || '-01');
        PERFORM p0_fixture.canonical_vnd(v_line->'amount_vnd', v_kind = 'charge_fixture');
    END LOOP;
    SELECT count(DISTINCT (x.line->>'line_no')::integer)
      INTO v_unique_line_count
    FROM jsonb_array_elements(p_payload->'lines') AS x(line);
    IF v_unique_line_count <> v_line_count THEN
        RAISE EXCEPTION 'fixture line numbers must be unique' USING ERRCODE = 'P0001';
    END IF;
    SELECT jsonb_agg(jsonb_build_object(
        'line_no', (x.line->>'line_no')::integer,
        'customer_id', x.line->>'customer_id',
        'debt_period', x.line->>'debt_period',
        'amount_vnd', p0_fixture.canonical_vnd(x.line->'amount_vnd', v_kind = 'charge_fixture')
    ) ORDER BY (x.line->>'line_no')::integer)
    INTO v_lines
    FROM jsonb_array_elements(p_payload->'lines') AS x(line);
    IF v_kind = 'revision_fixture' AND (SELECT sum((x.line->>'amount_vnd')::numeric)
        FROM jsonb_array_elements(v_lines) AS x(line)) <> v_total THEN
        RAISE EXCEPTION 'fixture line sum differs from total' USING ERRCODE = 'P0001';
    END IF;
    IF EXISTS (SELECT 1 FROM jsonb_array_elements(v_lines) AS x(line)
        WHERE x.line->>'customer_id' <> p_payload->>'customer_id'
           OR x.line->>'debt_period' <> p_payload->>'debt_period') THEN
        RAISE EXCEPTION 'fixture lines must match document customer and period' USING ERRCODE = 'P0001';
    END IF;

    v_lines := jsonb_build_object(
        'schema_version', 2,
        'kind', p_payload->>'kind',
        'customer_id', p_payload->>'customer_id',
        'debt_period', p_payload->>'debt_period',
        'total_vnd', v_total,
        'event_date', p_payload->>'event_date',
        'posting_date', p_payload->>'posting_date',
        'source_ref', CASE WHEN v_kind = 'charge_fixture' THEN p_payload->'source_ref'
                           ELSE to_jsonb(p_payload->>'source_ref') END,
        'evidence_ref', CASE WHEN v_kind = 'charge_fixture' THEN p_payload->'evidence_ref'
                             ELSE to_jsonb(p_payload->>'evidence_ref') END,
        'evidence_sha256', CASE WHEN v_kind = 'charge_fixture' THEN p_payload->'evidence_sha256'
                                ELSE to_jsonb(p_payload->>'evidence_sha256') END,
        'reason', p_payload->>'reason',
        'lines', v_lines
    );
    IF v_kind = 'charge_fixture' THEN
        IF (p_payload->'trip_code' IS NOT NULL
                AND jsonb_typeof(p_payload->'trip_code') NOT IN ('null', 'string'))
           OR (p_payload->'opening_snapshot_ref' IS NOT NULL
                AND jsonb_typeof(p_payload->'opening_snapshot_ref') NOT IN ('null', 'string'))
           OR (p_payload->'opening_absence_evidence_ref' IS NOT NULL
                AND jsonb_typeof(p_payload->'opening_absence_evidence_ref') NOT IN ('null', 'string'))
           OR (p_payload ? 'period_override_reason'
                AND jsonb_typeof(p_payload->'period_override_reason') NOT IN ('null', 'string'))
           OR (p_payload ? 'period_override_evidence_ref'
                AND jsonb_typeof(p_payload->'period_override_evidence_ref') NOT IN ('null', 'string'))
           OR (p_payload ? 'period_override_evidence_sha256'
                AND jsonb_typeof(p_payload->'period_override_evidence_sha256') NOT IN ('null', 'string')) THEN
            RAISE EXCEPTION 'invalid charge references' USING ERRCODE = 'P0001';
        END IF;
        IF jsonb_typeof(p_payload->'period_override_evidence_sha256') = 'string'
           AND (p_payload->>'period_override_evidence_sha256' COLLATE "C") !~ '^[0-9a-f]{64}$' THEN
            RAISE EXCEPTION 'invalid period override evidence hash' USING ERRCODE = 'P0001';
        END IF;
        IF p_payload->'price_components' IS NULL
           OR jsonb_typeof(p_payload->'price_components') = 'null' THEN
            v_components := 'null'::jsonb;
        ELSE
            IF jsonb_typeof(p_payload->'price_components') IS DISTINCT FROM 'array' THEN
                RAISE EXCEPTION 'invalid per-trip price component list' USING ERRCODE = 'P0001';
            END IF;
            FOR v_component IN
                SELECT x.component FROM jsonb_array_elements(p_payload->'price_components')
                    AS x(component)
            LOOP
                IF jsonb_typeof(v_component) IS DISTINCT FROM 'object'
                   OR EXISTS (SELECT 1 FROM jsonb_object_keys(v_component) AS k(key)
                        WHERE k.key <> ALL (ARRAY['label', 'amount_vnd']))
                   OR NOT v_component ? 'label'
                   OR jsonb_typeof(v_component->'label') IS DISTINCT FROM 'string' THEN
                    RAISE EXCEPTION 'invalid per-trip price component' USING ERRCODE = 'P0001';
                END IF;
                IF length(btrim(v_component->>'label')) = 0 THEN
                    RAISE EXCEPTION 'invalid per-trip price component' USING ERRCODE = 'P0001';
                END IF;
                PERFORM p0_fixture.canonical_vnd(v_component->'amount_vnd', true);
            END LOOP;
            SELECT CASE WHEN jsonb_array_length(p_payload->'price_components') = 0
                        THEN '[]'::jsonb
                        ELSE jsonb_agg(jsonb_build_object(
                            'label', x.component->>'label',
                            'amount_vnd', p0_fixture.canonical_vnd(x.component->'amount_vnd', true)
                        ) ORDER BY x.ordinality) END
            INTO v_components
            FROM jsonb_array_elements(p_payload->'price_components')
                WITH ORDINALITY AS x(component, ordinality);
        END IF;
        RETURN v_lines || jsonb_build_object(
            'trip_code', p_payload->'trip_code',
            'opening_snapshot_ref', p_payload->'opening_snapshot_ref',
            'opening_absence_evidence_ref', p_payload->'opening_absence_evidence_ref',
            'price_components', v_components,
            'period_override_reason', p_payload->'period_override_reason',
            'period_override_evidence_ref', p_payload->'period_override_evidence_ref',
            'period_override_evidence_sha256', p_payload->'period_override_evidence_sha256');
    END IF;
    RETURN v_lines;
END $$;

CREATE FUNCTION p0_fixture.charge_review_reason_codes(p_payload jsonb) RETURNS text[]
LANGUAGE plpgsql IMMUTABLE
SET search_path = pg_catalog AS $$
DECLARE
    v_codes text[] := ARRAY[]::text[];
    v_total numeric;
    v_line_amount numeric;
    v_component_total numeric;
    v_components jsonb;
BEGIN
    IF p_payload->>'kind' <> 'charge_fixture' THEN
        RETURN v_codes;
    END IF;
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
        END IF;
        IF EXISTS (SELECT 1 FROM jsonb_array_elements(v_components) AS x(component)
                   WHERE x.component->>'amount_vnd' = '0') THEN
            v_codes := array_append(v_codes, 'COMPONENT_AMOUNT_ZERO');
        END IF;
        IF v_total IS NOT NULL AND NOT EXISTS (
                SELECT 1 FROM jsonb_array_elements(v_components) AS x(component)
                WHERE jsonb_typeof(x.component->'amount_vnd') = 'null') THEN
            SELECT sum((x.component->>'amount_vnd')::numeric) INTO v_component_total
            FROM jsonb_array_elements(v_components) AS x(component);
            IF v_component_total IS NOT NULL AND v_component_total <> v_total THEN
                v_codes := array_append(v_codes, 'COMPONENT_TOTAL_MISMATCH');
            END IF;
        END IF;
    END IF;

    v_line_amount := (p_payload->'lines'->0->>'amount_vnd')::numeric;
    IF jsonb_typeof(p_payload->'lines'->0->'amount_vnd') = 'null' THEN
        v_codes := array_append(v_codes, 'LINE_AMOUNT_MISSING');
    ELSIF v_total IS NOT NULL AND v_line_amount <> v_total THEN
        v_codes := array_append(v_codes, 'LINE_TOTAL_MISMATCH');
    END IF;

    IF nullif(btrim(p_payload->>'source_ref'), '') IS NULL
       OR nullif(btrim(p_payload->>'evidence_ref'), '') IS NULL
       OR jsonb_typeof(p_payload->'evidence_sha256') = 'null' THEN
        v_codes := array_append(v_codes, 'SOURCE_EVIDENCE_MISSING');
    END IF;
    IF left(p_payload->>'debt_period', 7) <> left(p_payload->>'event_date', 7)
       AND (nullif(btrim(p_payload->>'period_override_reason'), '') IS NULL
            OR nullif(btrim(p_payload->>'period_override_evidence_ref'), '') IS NULL
            OR jsonb_typeof(p_payload->'period_override_evidence_sha256') = 'null') THEN
        v_codes := array_append(v_codes, 'PERIOD_OVERRIDE_EVIDENCE_MISSING');
    END IF;
    IF nullif(btrim(p_payload->>'trip_code'), '') IS NULL THEN
        v_codes := array_append(v_codes, 'TRIP_CODE_MISSING');
    END IF;
    IF nullif(btrim(p_payload->>'opening_snapshot_ref'), '') IS NULL
       OR nullif(btrim(p_payload->>'opening_absence_evidence_ref'), '') IS NULL THEN
        v_codes := array_append(v_codes, 'OPENING_EVIDENCE_MISSING');
    END IF;
    v_codes := array_append(v_codes, 'SOURCE_RESOLVER_UNAVAILABLE');
    SELECT array_agg(code ORDER BY code COLLATE "C") INTO v_codes FROM unnest(v_codes) AS x(code);
    RETURN coalesce(v_codes, ARRAY[]::text[]);
END $$;

CREATE FUNCTION p0_fixture.submit_revision(
    p_proposal_id bigint,
    p_payload_text text,
    p_actor_id uuid,
    p_session_id uuid,
    p_nonce uuid,
    p_issued_epoch bigint,
    p_key_id text,
    p_signature text
) RETURNS TABLE (
    proposal_id bigint,
    revision_id bigint,
    revision_no integer,
    content_sha256 text,
    revision_created boolean
)
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, p0_fixture, public AS $$
DECLARE
    v_payload jsonb;
    v_canonical jsonb;
    v_body_sha text;
    v_hash text;
    v_review_reason_codes text[];
    v_scope text;
    v_proposal_id bigint;
    v_revision_id bigint;
    v_revision_no integer;
    v_created boolean := false;
    v_proposal p0_fixture.proposal%ROWTYPE;
    v_current_hash text;
BEGIN
    IF NOT EXISTS (SELECT 1 FROM p0_fixture.app_actor_role
                   WHERE actor_id = p_actor_id AND app_role = 'maker') THEN
        RAISE EXCEPTION 'maker role required' USING ERRCODE = 'P0001';
    END IF;
    IF p_payload_text IS NULL OR length(p_payload_text) > 65536 THEN
        RAISE EXCEPTION 'invalid fixture payload length' USING ERRCODE = 'P0001';
    END IF;
    v_body_sha := encode(public.digest(convert_to(p_payload_text, 'UTF8'), 'sha256'), 'hex');
    v_scope := CASE WHEN p_proposal_id IS NULL THEN 'submit:new:'
                    ELSE 'submit:' || p_proposal_id::text || ':' END || v_body_sha;
    PERFORM p0_fixture.verify_actor_assertion(p_actor_id, p_session_id, 'submit',
        p_nonce, p_issued_epoch, p_key_id, v_scope, p_signature);
    v_payload := p_payload_text::jsonb;
    v_canonical := p0_fixture.canonicalize_payload(v_payload);
    v_review_reason_codes := p0_fixture.charge_review_reason_codes(v_canonical);
    v_hash := encode(public.digest(convert_to(
        'webdebit.business-payload.v2' || E'\n' || v_canonical::text, 'UTF8'), 'sha256'), 'hex');

    IF p_proposal_id IS NULL THEN
        PERFORM p0_fixture.assert_fixture_kind_access(v_canonical->>'kind');
        INSERT INTO p0_fixture.proposal(maker_actor_id, kind)
        VALUES (p_actor_id, v_canonical->>'kind')
        RETURNING p0_fixture.proposal.proposal_id INTO v_proposal_id;
        v_revision_no := 1;
        v_created := true;
    ELSE
        SELECT p.* INTO v_proposal
        FROM p0_fixture.proposal p WHERE p.proposal_id = p_proposal_id FOR UPDATE;
        IF NOT FOUND OR v_proposal.maker_actor_id <> p_actor_id OR v_proposal.state = 'posted' THEN
            RAISE EXCEPTION 'proposal unavailable to this maker' USING ERRCODE = 'P0001';
        END IF;
        PERFORM p0_fixture.assert_fixture_kind_access(v_proposal.kind);
        IF v_proposal.kind <> v_canonical->>'kind' THEN
            RAISE EXCEPTION 'proposal kind is immutable' USING ERRCODE = 'P0001';
        END IF;
        SELECT r.content_sha256 INTO v_current_hash
        FROM p0_fixture.business_revision r
        WHERE r.proposal_id = p_proposal_id AND r.revision_id = v_proposal.current_revision_id;
        IF v_current_hash = v_hash THEN
            INSERT INTO p0_fixture.audit(proposal_id, revision_id, content_sha256,
                app_actor_id, app_session_id, assertion_nonce, key_id, database_session_user,
                action, request_scope)
            VALUES (p_proposal_id, v_proposal.current_revision_id, v_current_hash, p_actor_id, p_session_id,
                p_nonce, p_key_id, session_user, 'submit_noop', v_scope);
            RETURN QUERY SELECT p_proposal_id, v_proposal.current_revision_id,
                v_proposal.revision_no, v_current_hash, false;
            RETURN;
        END IF;
        v_revision_no := v_proposal.revision_no + 1;
        v_revision_id := v_proposal.current_revision_id;
        v_proposal_id := p_proposal_id;
        v_created := true;
    END IF;

    INSERT INTO p0_fixture.business_revision(proposal_id, revision_no, canonical_payload,
        content_sha256, review_reason_codes, created_by_actor, created_in_session)
    VALUES (v_proposal_id, v_revision_no, v_canonical, v_hash, v_review_reason_codes,
        p_actor_id, p_session_id)
    RETURNING p0_fixture.business_revision.revision_id INTO v_revision_id;
    UPDATE p0_fixture.proposal
    SET current_revision_id = v_revision_id, revision_no = v_revision_no,
        state = CASE WHEN v_canonical->>'kind' = 'charge_fixture'
            THEN 'review_needed' ELSE 'pending' END
    WHERE p0_fixture.proposal.proposal_id = v_proposal_id;
    INSERT INTO p0_fixture.audit(proposal_id, revision_id, content_sha256,
        app_actor_id, app_session_id, assertion_nonce, key_id, database_session_user,
        action, request_scope)
    VALUES (v_proposal_id, v_revision_id, v_hash, p_actor_id, p_session_id,
        p_nonce, p_key_id, session_user, 'submit', v_scope);
    RETURN QUERY SELECT v_proposal_id, v_revision_id, v_revision_no, v_hash, v_created;
END $$;

CREATE FUNCTION p0_fixture.fixture_review_projection(p_proposal_id bigint) RETURNS jsonb
LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = pg_catalog, p0_fixture AS $$
    SELECT jsonb_build_object(
        'proposal_id', p.proposal_id,
        'kind', p.kind,
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
                'current_blockers', CASE WHEN r.revision_id <> p.current_revision_id
                    THEN '[]'::jsonb
                    ELSE coalesce((
                        SELECT to_jsonb(array_agg(blocker ORDER BY blocker COLLATE "C"))
                        FROM (
                            SELECT unnest(r.review_reason_codes) AS blocker
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
                            WHERE p.kind = 'charge_fixture' AND NOT EXISTS (
                                SELECT 1 FROM p0_fixture.period_confirmation c
                                WHERE c.proposal_id = p.proposal_id
                                  AND c.revision_id = r.revision_id
                                  AND c.content_sha256 = r.content_sha256
                                  AND c.maker_actor_id = p.maker_actor_id
                            )
                            UNION
                            SELECT 'PRICE_CONFIRMATION_MISSING'
                            WHERE p.kind = 'charge_fixture' AND NOT EXISTS (
                                SELECT 1 FROM p0_fixture.price_confirmation c
                                WHERE c.proposal_id = p.proposal_id
                                  AND c.revision_id = r.revision_id
                                  AND c.content_sha256 = r.content_sha256
                            )
                        ) AS blockers
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
    p_session_id uuid,
    p_nonce uuid,
    p_issued_epoch bigint,
    p_key_id text,
    p_signature text
) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, p0_fixture AS $$
DECLARE
    v_proposal p0_fixture.proposal%ROWTYPE;
    v_revision p0_fixture.business_revision%ROWTYPE;
    v_price_blockers text[];
    v_scope text := 'confirm_price:' || p_proposal_id::text || ':' ||
        p_revision_id::text || ':' || p_content_sha256;
BEGIN
    PERFORM p0_fixture.verify_actor_assertion(p_actor_id, p_session_id, 'confirm_price',
        p_nonce, p_issued_epoch, p_key_id, v_scope, p_signature);
    SELECT * INTO v_proposal FROM p0_fixture.proposal
    WHERE proposal_id = p_proposal_id FOR UPDATE;
    IF v_proposal.proposal_id IS NULL THEN
        RAISE EXCEPTION 'proposal unavailable to price confirmation' USING ERRCODE = 'P0001';
    END IF;
    PERFORM p0_fixture.assert_fixture_kind_access(v_proposal.kind);
    SELECT * INTO v_revision FROM p0_fixture.business_revision
    WHERE proposal_id = p_proposal_id AND revision_id = p_revision_id;
    IF v_proposal.proposal_id IS NULL OR v_proposal.state NOT IN ('pending', 'review_needed')
       OR v_proposal.current_revision_id <> p_revision_id
       OR v_revision.content_sha256 <> p_content_sha256
       OR v_revision.canonical_payload->>'kind' <> 'charge_fixture' THEN
        RAISE EXCEPTION 'price confirmation requires the current charge revision' USING ERRCODE = 'P0001';
    END IF;
    v_price_blockers := p0_fixture.charge_review_reason_codes(v_revision.canonical_payload);
    IF v_price_blockers && ARRAY[
        'TOTAL_MISSING', 'TOTAL_ZERO', 'PRICE_COMPONENTS_MISSING',
        'COMPONENT_AMOUNT_MISSING', 'COMPONENT_AMOUNT_ZERO', 'COMPONENT_TOTAL_MISMATCH',
        'LINE_AMOUNT_MISSING', 'LINE_TOTAL_MISMATCH', 'SOURCE_EVIDENCE_MISSING'
    ] THEN
        RAISE EXCEPTION 'price confirmation requires complete positive matching price and source evidence'
            USING ERRCODE = 'P0001';
    END IF;
    INSERT INTO p0_fixture.price_confirmation(proposal_id, revision_id, content_sha256,
        owner_actor_id, owner_session_id, database_session_user)
    VALUES (p_proposal_id, p_revision_id, p_content_sha256,
        p_actor_id, p_session_id, session_user);
    INSERT INTO p0_fixture.audit(proposal_id, revision_id, content_sha256,
        app_actor_id, app_session_id, assertion_nonce, key_id, database_session_user,
        action, request_scope)
    VALUES (p_proposal_id, p_revision_id, p_content_sha256, p_actor_id, p_session_id,
        p_nonce, p_key_id, session_user, 'confirm_price', v_scope);
END $$;

CREATE FUNCTION p0_fixture.confirm_period_revision(
    p_proposal_id bigint,
    p_revision_id bigint,
    p_content_sha256 text,
    p_actor_id uuid,
    p_session_id uuid,
    p_nonce uuid,
    p_issued_epoch bigint,
    p_key_id text,
    p_signature text
) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, p0_fixture AS $$
DECLARE
    v_proposal p0_fixture.proposal%ROWTYPE;
    v_revision p0_fixture.business_revision%ROWTYPE;
    v_scope text := 'confirm_period:' || p_proposal_id::text || ':' ||
        p_revision_id::text || ':' || p_content_sha256;
BEGIN
    PERFORM p0_fixture.verify_actor_assertion(p_actor_id, p_session_id, 'confirm_period',
        p_nonce, p_issued_epoch, p_key_id, v_scope, p_signature);
    SELECT * INTO v_proposal FROM p0_fixture.proposal
    WHERE proposal_id = p_proposal_id FOR UPDATE;
    IF v_proposal.proposal_id IS NULL THEN
        RAISE EXCEPTION 'proposal unavailable to period confirmation' USING ERRCODE = 'P0001';
    END IF;
    PERFORM p0_fixture.assert_fixture_kind_access(v_proposal.kind);
    SELECT * INTO v_revision FROM p0_fixture.business_revision
    WHERE proposal_id = p_proposal_id AND revision_id = p_revision_id;
    IF v_proposal.proposal_id IS NULL OR v_proposal.state NOT IN ('pending', 'review_needed')
       OR v_proposal.maker_actor_id <> p_actor_id
       OR v_proposal.current_revision_id <> p_revision_id
       OR v_revision.content_sha256 <> p_content_sha256
       OR v_revision.canonical_payload->>'kind' <> 'charge_fixture' THEN
        RAISE EXCEPTION 'period confirmation requires current charge revision from its maker' USING ERRCODE = 'P0001';
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
    VALUES (p_proposal_id, p_revision_id, p_content_sha256,
        p_actor_id, p_session_id, session_user);
    INSERT INTO p0_fixture.audit(proposal_id, revision_id, content_sha256,
        app_actor_id, app_session_id, assertion_nonce, key_id, database_session_user,
        action, request_scope)
    VALUES (p_proposal_id, p_revision_id, p_content_sha256, p_actor_id, p_session_id,
        p_nonce, p_key_id, session_user, 'confirm_period', v_scope);
END $$;

CREATE FUNCTION p0_fixture.set_presentation_title(
    p_proposal_id bigint,
    p_title text,
    p_actor_id uuid,
    p_session_id uuid,
    p_nonce uuid,
    p_issued_epoch bigint,
    p_key_id text,
    p_signature text
) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, p0_fixture, public AS $$
DECLARE v_scope text; v_maker uuid; v_kind text;
BEGIN
    IF p_title IS NULL OR length(p_title) > 160 THEN
        RAISE EXCEPTION 'invalid presentation title' USING ERRCODE = 'P0001';
    END IF;
    v_scope := 'presentation:' || p_proposal_id::text || ':' ||
        encode(public.digest(convert_to(p_title, 'UTF8'), 'sha256'), 'hex');
    PERFORM p0_fixture.verify_actor_assertion(p_actor_id, p_session_id, 'presentation',
        p_nonce, p_issued_epoch, p_key_id, v_scope, p_signature);
    IF NOT EXISTS (SELECT 1 FROM p0_fixture.app_actor_role
                   WHERE actor_id = p_actor_id AND app_role = 'maker') THEN
        RAISE EXCEPTION 'maker role required' USING ERRCODE = 'P0001';
    END IF;
    SELECT p.maker_actor_id, p.kind INTO v_maker, v_kind FROM p0_fixture.proposal p
    WHERE p.proposal_id = p_proposal_id FOR UPDATE;
    IF NOT FOUND OR v_maker <> p_actor_id THEN
        RAISE EXCEPTION 'proposal unavailable to this maker' USING ERRCODE = 'P0001';
    END IF;
    PERFORM p0_fixture.assert_fixture_kind_access(v_kind);
    UPDATE p0_fixture.proposal SET presentation_title = p_title
    WHERE p0_fixture.proposal.proposal_id = p_proposal_id;
    INSERT INTO p0_fixture.audit(proposal_id, revision_id, content_sha256,
        app_actor_id, app_session_id, assertion_nonce, key_id, database_session_user,
        action, request_scope)
    SELECT p.proposal_id, p.current_revision_id, r.content_sha256, p_actor_id, p_session_id,
        p_nonce, p_key_id, session_user, 'presentation', v_scope
    FROM p0_fixture.proposal p
    JOIN p0_fixture.business_revision r ON r.revision_id = p.current_revision_id
    WHERE p.proposal_id = p_proposal_id;
END $$;

CREATE FUNCTION p0_fixture.approve_revision(
    p_proposal_id bigint,
    p_revision_id bigint,
    p_content_sha256 text,
    p_actor_id uuid,
    p_session_id uuid,
    p_nonce uuid,
    p_issued_epoch bigint,
    p_key_id text,
    p_signature text
) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, p0_fixture AS $$
DECLARE v_proposal p0_fixture.proposal%ROWTYPE; v_revision p0_fixture.business_revision%ROWTYPE;
    v_scope text := 'approve:' || p_proposal_id::text || ':' ||
        p_revision_id::text || ':' || p_content_sha256;
    v_open_period text;
BEGIN
    PERFORM p0_fixture.verify_actor_assertion(p_actor_id, p_session_id, 'approve',
        p_nonce, p_issued_epoch, p_key_id, v_scope, p_signature);
    IF NOT EXISTS (SELECT 1 FROM p0_fixture.app_actor_role
                   WHERE actor_id = p_actor_id AND app_role = 'checker') THEN
        RAISE EXCEPTION 'checker role required' USING ERRCODE = 'P0001';
    END IF;
    SELECT * INTO v_proposal FROM p0_fixture.proposal
    WHERE proposal_id = p_proposal_id FOR UPDATE;
    IF v_proposal.proposal_id IS NULL THEN
        RAISE EXCEPTION 'proposal unavailable for approval' USING ERRCODE = 'P0001';
    END IF;
    PERFORM p0_fixture.assert_fixture_kind_access(v_proposal.kind);
    SELECT r.* INTO v_revision FROM p0_fixture.business_revision r
    WHERE r.proposal_id = p_proposal_id AND r.revision_id = p_revision_id;
    IF NOT FOUND OR v_proposal.proposal_id IS NULL
       OR v_proposal.state NOT IN ('pending', 'review_needed')
       OR v_proposal.current_revision_id <> p_revision_id OR v_revision.content_sha256 <> p_content_sha256
       OR v_proposal.maker_actor_id = p_actor_id THEN
        RAISE EXCEPTION 'stale, unavailable, or self-approved revision' USING ERRCODE = 'P0001';
    END IF;
    FOR v_open_period IN
        SELECT required_period.debt_period
        FROM (
            SELECT v_revision.canonical_payload->>'debt_period' AS debt_period
            UNION
            SELECT x.line->>'debt_period'
            FROM jsonb_array_elements(v_revision.canonical_payload->'lines') AS x(line)
        ) AS required_period
        ORDER BY required_period.debt_period COLLATE "C"
    LOOP
        PERFORM 1 FROM p0_fixture.debt_period_state s
        WHERE s.debt_period = v_open_period AND s.state = 'open' FOR SHARE;
        IF NOT FOUND THEN
            RAISE EXCEPTION 'debt period is not open at approval: %', v_open_period
                USING ERRCODE = 'P0001';
        END IF;
    END LOOP;
    IF v_revision.canonical_payload->>'kind' = 'charge_fixture' THEN
        IF NOT EXISTS (SELECT 1 FROM p0_fixture.period_confirmation c
            WHERE c.proposal_id = p_proposal_id AND c.revision_id = p_revision_id
              AND c.content_sha256 = p_content_sha256
              AND c.maker_actor_id = v_proposal.maker_actor_id) THEN
            RAISE EXCEPTION 'maker confirmation required for this debt period revision' USING ERRCODE = 'P0001';
        END IF;
        IF nullif(btrim(v_revision.canonical_payload->>'trip_code'), '') IS NULL THEN
            RAISE EXCEPTION 'stable trip code missing; charge remains CHỜ KIỂM' USING ERRCODE = 'P0001';
        END IF;
        IF nullif(btrim(v_revision.canonical_payload->>'opening_snapshot_ref'), '') IS NULL
           OR nullif(btrim(v_revision.canonical_payload->>'opening_absence_evidence_ref'), '') IS NULL THEN
            RAISE EXCEPTION 'opening comparison evidence missing; charge remains CHỜ KIỂM' USING ERRCODE = 'P0001';
        END IF;
        IF NOT EXISTS (SELECT 1 FROM p0_fixture.price_confirmation c
            WHERE c.proposal_id = p_proposal_id AND c.revision_id = p_revision_id
              AND c.content_sha256 = p_content_sha256) THEN
            RAISE EXCEPTION 'per-trip price owner confirmation required for this revision' USING ERRCODE = 'P0001';
        END IF;
        IF EXISTS (SELECT 1 FROM p0_fixture.price_confirmation c
            WHERE c.proposal_id = p_proposal_id AND c.revision_id = p_revision_id
              AND c.content_sha256 = p_content_sha256 AND c.owner_actor_id = p_actor_id) THEN
            RAISE EXCEPTION 'price owner cannot checker-approve the same revision' USING ERRCODE = 'P0001';
        END IF;
        -- ponytail: Keep charges blocked until approved TRIP-KEY mapping and opening absence proof exist; add resolver after those gates close.
        RAISE EXCEPTION 'charge blocked: source key and opening reconciliation are unresolved' USING ERRCODE = 'P0001';
    END IF;
    INSERT INTO p0_fixture.approval(proposal_id, revision_id, content_sha256,
        checker_actor_id, checker_session_id, database_session_user)
    VALUES (p_proposal_id, p_revision_id, p_content_sha256, p_actor_id, p_session_id, session_user);
    UPDATE p0_fixture.proposal SET state = 'approved'
    WHERE p0_fixture.proposal.proposal_id = p_proposal_id;
    INSERT INTO p0_fixture.audit(proposal_id, revision_id, content_sha256,
        app_actor_id, app_session_id, assertion_nonce, key_id, database_session_user,
        action, request_scope)
    VALUES (p_proposal_id, p_revision_id, p_content_sha256, p_actor_id, p_session_id,
        p_nonce, p_key_id, session_user, 'approve', v_scope);
END $$;

CREATE FUNCTION p0_fixture.post_revision(
    p_proposal_id bigint,
    p_revision_id bigint,
    p_content_sha256 text,
    p_actor_id uuid,
    p_session_id uuid,
    p_nonce uuid,
    p_issued_epoch bigint,
    p_key_id text,
    p_signature text
) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, p0_fixture AS $$
DECLARE v_proposal p0_fixture.proposal%ROWTYPE; v_approval p0_fixture.approval%ROWTYPE;
    v_revision p0_fixture.business_revision%ROWTYPE;
    v_scope text := 'post:' || p_proposal_id::text || ':' ||
        p_revision_id::text || ':' || p_content_sha256;
    v_open_period text;
BEGIN
    PERFORM p0_fixture.verify_actor_assertion(p_actor_id, p_session_id, 'post',
        p_nonce, p_issued_epoch, p_key_id, v_scope, p_signature);
    IF NOT EXISTS (SELECT 1 FROM p0_fixture.app_actor_role
                   WHERE actor_id = p_actor_id AND app_role = 'checker') THEN
        RAISE EXCEPTION 'checker role required' USING ERRCODE = 'P0001';
    END IF;
    SELECT * INTO v_proposal FROM p0_fixture.proposal
    WHERE proposal_id = p_proposal_id FOR UPDATE;
    IF v_proposal.proposal_id IS NULL THEN
        RAISE EXCEPTION 'proposal unavailable for posting' USING ERRCODE = 'P0001';
    END IF;
    PERFORM p0_fixture.assert_fixture_kind_access(v_proposal.kind);
    SELECT * INTO v_revision FROM p0_fixture.business_revision
    WHERE proposal_id = p_proposal_id AND revision_id = p_revision_id;
    SELECT * INTO v_approval FROM p0_fixture.approval
    WHERE proposal_id = p_proposal_id AND revision_id = p_revision_id
      AND content_sha256 = p_content_sha256;
    IF NOT FOUND OR v_proposal.proposal_id IS NULL OR v_proposal.state <> 'approved'
       OR v_proposal.current_revision_id <> p_revision_id
       OR v_revision.content_sha256 <> p_content_sha256
       OR v_approval.revision_id IS NULL OR v_approval.checker_actor_id <> p_actor_id
       OR v_proposal.maker_actor_id = p_actor_id THEN
        RAISE EXCEPTION 'current approved revision required for posting' USING ERRCODE = 'P0001';
    END IF;
    FOR v_open_period IN
        SELECT required_period.debt_period
        FROM (
            SELECT v_revision.canonical_payload->>'debt_period' AS debt_period
            UNION
            SELECT x.line->>'debt_period'
            FROM jsonb_array_elements(v_revision.canonical_payload->'lines') AS x(line)
        ) AS required_period
        ORDER BY required_period.debt_period COLLATE "C"
    LOOP
        PERFORM 1 FROM p0_fixture.debt_period_state s
        WHERE s.debt_period = v_open_period AND s.state = 'open' FOR SHARE;
        IF NOT FOUND THEN
            RAISE EXCEPTION 'debt period is not open at posting: %', v_open_period
                USING ERRCODE = 'P0001';
        END IF;
    END LOOP;
    INSERT INTO p0_fixture.posting(proposal_id, revision_id, approval_id, content_sha256, canonical_payload,
        maker_actor_id, checker_actor_id, posted_in_session, database_session_user)
    VALUES (p_proposal_id, p_revision_id, v_approval.approval_id, p_content_sha256, v_revision.canonical_payload,
        v_proposal.maker_actor_id, p_actor_id, p_session_id, session_user);
    UPDATE p0_fixture.proposal SET state = 'posted'
    WHERE p0_fixture.proposal.proposal_id = p_proposal_id;
    INSERT INTO p0_fixture.audit(proposal_id, revision_id, content_sha256,
        app_actor_id, app_session_id, assertion_nonce, key_id, database_session_user,
        action, request_scope)
    VALUES (p_proposal_id, p_revision_id, p_content_sha256, p_actor_id, p_session_id,
        p_nonce, p_key_id, session_user, 'post', v_scope);
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
    ('22222222-2222-4222-8222-222222222222', 'checker'),
    ('33333333-3333-4333-8333-333333333333', 'maker'),
    ('44444444-4444-4444-8444-444444444444', 'maker'),
    ('55555555-5555-4555-8555-555555555555', 'price_owner'),
    ('55555555-5555-4555-8555-555555555555', 'checker');
INSERT INTO p0_fixture.actor_signing_key(key_id, secret)
VALUES ('fixture-key-v1', decode(repeat('11', 32), 'hex'));
INSERT INTO p0_fixture.debt_period_state(debt_period, state) VALUES
    ('2026-01', 'open'),
    ('2026-02', 'open'),
    ('2026-08', 'closed'),
    ('2026-09', 'open'),
    ('2026-10', 'open');

RESET ROLE;

REVOKE ALL ON ALL TABLES IN SCHEMA p0_fixture FROM PUBLIC, p0_fixture_api,
    p0_fixture_identity_test_api;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA p0_fixture FROM PUBLIC, p0_fixture_api,
    p0_fixture_identity_test_api;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA p0_fixture FROM PUBLIC;
GRANT EXECUTE ON FUNCTION p0_fixture.submit_revision(bigint,text,uuid,uuid,uuid,bigint,text,text)
    TO p0_fixture_api;
GRANT EXECUTE ON FUNCTION p0_fixture.set_presentation_title(bigint,text,uuid,uuid,uuid,bigint,text,text)
    TO p0_fixture_api;
GRANT EXECUTE ON FUNCTION p0_fixture.confirm_price_revision(bigint,bigint,text,uuid,uuid,uuid,bigint,text,text)
    TO p0_fixture_api;
GRANT EXECUTE ON FUNCTION p0_fixture.confirm_period_revision(bigint,bigint,text,uuid,uuid,uuid,bigint,text,text)
    TO p0_fixture_api;
GRANT EXECUTE ON FUNCTION p0_fixture.approve_revision(bigint,bigint,text,uuid,uuid,uuid,bigint,text,text)
    TO p0_fixture_api;
GRANT EXECUTE ON FUNCTION p0_fixture.post_revision(bigint,bigint,text,uuid,uuid,uuid,bigint,text,text)
    TO p0_fixture_api;
GRANT EXECUTE ON FUNCTION p0_fixture.submit_revision(bigint,text,uuid,uuid,uuid,bigint,text,text)
    TO p0_fixture_identity_test_api;
GRANT EXECUTE ON FUNCTION p0_fixture.set_presentation_title(bigint,text,uuid,uuid,uuid,bigint,text,text)
    TO p0_fixture_identity_test_api;
GRANT EXECUTE ON FUNCTION p0_fixture.confirm_price_revision(bigint,bigint,text,uuid,uuid,uuid,bigint,text,text)
    TO p0_fixture_identity_test_api;
GRANT EXECUTE ON FUNCTION p0_fixture.confirm_period_revision(bigint,bigint,text,uuid,uuid,uuid,bigint,text,text)
    TO p0_fixture_identity_test_api;
GRANT EXECUTE ON FUNCTION p0_fixture.approve_revision(bigint,bigint,text,uuid,uuid,uuid,bigint,text,text)
    TO p0_fixture_identity_test_api;
GRANT EXECUTE ON FUNCTION p0_fixture.post_revision(bigint,bigint,text,uuid,uuid,uuid,bigint,text,text)
    TO p0_fixture_identity_test_api;
