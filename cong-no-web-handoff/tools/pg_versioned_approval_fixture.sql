-- Acceptance fixture only. Never deploy or apply to hao/production.
\set ON_ERROR_STOP on

CREATE EXTENSION IF NOT EXISTS pgcrypto WITH SCHEMA public;
CREATE ROLE p0_fixture_owner NOLOGIN;
CREATE ROLE p0_fixture_api NOLOGIN;
GRANT CONNECT ON DATABASE webdebit_ledger TO p0_fixture_api;
CREATE SCHEMA p0_fixture AUTHORIZATION p0_fixture_owner;
REVOKE ALL ON SCHEMA p0_fixture FROM PUBLIC;
GRANT USAGE ON SCHEMA p0_fixture TO p0_fixture_api;

SET ROLE p0_fixture_owner;

CREATE TABLE p0_fixture.app_actor (
    actor_id uuid PRIMARY KEY,
    active boolean NOT NULL DEFAULT true
);

CREATE TABLE p0_fixture.app_actor_role (
    actor_id uuid NOT NULL REFERENCES p0_fixture.app_actor,
    app_role text NOT NULL CHECK (app_role IN ('maker', 'checker', 'admin')),
    PRIMARY KEY (actor_id, app_role)
);

CREATE TABLE p0_fixture.actor_signing_key (
    key_id text PRIMARY KEY,
    secret bytea NOT NULL CHECK (octet_length(secret) >= 32),
    active boolean NOT NULL DEFAULT true
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
    current_revision_id bigint,
    revision_no integer NOT NULL DEFAULT 0 CHECK (revision_no >= 0),
    state text NOT NULL DEFAULT 'pending' CHECK (state IN ('pending', 'approved', 'posted')),
    presentation_title text NOT NULL DEFAULT '',
    created_at timestamptz NOT NULL DEFAULT clock_timestamp()
);

CREATE TABLE p0_fixture.business_revision (
    revision_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    proposal_id bigint NOT NULL REFERENCES p0_fixture.proposal,
    revision_no integer NOT NULL CHECK (revision_no > 0),
    canonical_payload jsonb NOT NULL,
    content_sha256 text NOT NULL CHECK (content_sha256 ~ '^[0-9a-f]{64}$'),
    created_by_actor uuid NOT NULL REFERENCES p0_fixture.app_actor,
    created_in_session uuid NOT NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    UNIQUE (proposal_id, revision_no),
    UNIQUE (proposal_id, revision_id),
    UNIQUE (proposal_id, revision_id, content_sha256)
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
    action text NOT NULL CHECK (action IN ('submit', 'submit_noop', 'presentation', 'approve', 'post')),
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
CREATE TRIGGER posting_append_only
    BEFORE UPDATE OR DELETE ON p0_fixture.posting
    FOR EACH ROW EXECUTE FUNCTION p0_fixture.reject_immutable_change();
CREATE TRIGGER audit_append_only
    BEFORE UPDATE OR DELETE ON p0_fixture.audit
    FOR EACH ROW EXECUTE FUNCTION p0_fixture.reject_immutable_change();

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
    IF NOT pg_has_role(session_user, 'p0_fixture_api', 'member') THEN
        RAISE EXCEPTION 'untrusted database principal' USING ERRCODE = 'P0001';
    END IF;
    IF p_action NOT IN ('submit', 'presentation', 'approve', 'post')
       OR p_actor_id IS NULL OR p_session_id IS NULL OR p_nonce IS NULL
       OR p_key_id IS NULL OR p_scope IS NULL OR length(p_scope) > 512
       OR p_issued_epoch < floor(extract(epoch FROM clock_timestamp()))::bigint - 120
       OR p_issued_epoch > floor(extract(epoch FROM clock_timestamp()))::bigint + 30
       OR p_signature IS NULL OR p_signature !~ '^[0-9a-f]{64}$' THEN
        RAISE EXCEPTION 'invalid actor assertion' USING ERRCODE = 'P0001';
    END IF;
    SELECT a.actor_id INTO v_actor FROM p0_fixture.app_actor a
    WHERE a.actor_id = p_actor_id AND a.active FOR SHARE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'inactive actor' USING ERRCODE = 'P0001';
    END IF;
    v_role := CASE WHEN p_action IN ('submit', 'presentation') THEN 'maker' ELSE 'checker' END;
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

CREATE FUNCTION p0_fixture.canonicalize_payload(p_payload jsonb) RETURNS jsonb
LANGUAGE plpgsql IMMUTABLE
SET search_path = pg_catalog AS $$
DECLARE
    v_line jsonb;
    v_lines jsonb;
    v_line_count integer;
    v_unique_line_count integer;
    v_total numeric;
BEGIN
    IF jsonb_typeof(p_payload) IS DISTINCT FROM 'object'
       OR (SELECT count(*) FROM jsonb_object_keys(p_payload)) <> 12
       OR NOT p_payload ?& ARRAY['schema_version','kind','customer_id','debt_period',
            'total_vnd','event_date','posting_date','source_ref','evidence_ref',
            'evidence_sha256','reason','lines'] THEN
        RAISE EXCEPTION 'payload has missing or unknown business fields' USING ERRCODE = 'P0001';
    END IF;
    IF jsonb_typeof(p_payload->'schema_version') IS DISTINCT FROM 'number'
       OR (p_payload->>'schema_version')::numeric <> 1
       OR p_payload->>'kind' IS DISTINCT FROM 'charge_fixture'
       OR jsonb_typeof(p_payload->'total_vnd') IS DISTINCT FROM 'number'
       OR jsonb_typeof(p_payload->'lines') IS DISTINCT FROM 'array'
       OR (p_payload->>'debt_period') IS NULL
       OR (p_payload->>'debt_period') !~ '^\d{4}-(0[1-9]|1[0-2])$'
       OR (p_payload->>'customer_id') IS NULL OR length(btrim(p_payload->>'customer_id')) = 0
       OR (p_payload->>'source_ref') IS NULL OR length(btrim(p_payload->>'source_ref')) = 0
       OR (p_payload->>'evidence_ref') IS NULL OR length(btrim(p_payload->>'evidence_ref')) = 0
       OR (p_payload->>'evidence_sha256') IS NULL
       OR (p_payload->>'evidence_sha256') !~ '^[0-9a-f]{64}$'
       OR (p_payload->>'reason') IS NULL OR length(btrim(p_payload->>'reason')) = 0 THEN
        RAISE EXCEPTION 'invalid fixture payload fields' USING ERRCODE = 'P0001';
    END IF;
    v_total := (p_payload->>'total_vnd')::numeric;
    IF v_total <= 0 OR v_total <> trunc(v_total) THEN
        RAISE EXCEPTION 'fixture amount must be a positive integer' USING ERRCODE = 'P0001';
    END IF;
    IF (p_payload->>'event_date') IS NULL OR (p_payload->>'posting_date') IS NULL
       OR (p_payload->>'event_date')::date IS NULL OR (p_payload->>'posting_date')::date IS NULL THEN
        RAISE EXCEPTION 'invalid fixture date' USING ERRCODE = 'P0001';
    END IF;

    SELECT count(*), count(DISTINCT (x.line->>'line_no')::integer)
      INTO v_line_count, v_unique_line_count
    FROM jsonb_array_elements(p_payload->'lines') AS x(line);
    IF v_line_count < 1 OR v_unique_line_count <> v_line_count THEN
        RAISE EXCEPTION 'fixture line numbers must be unique' USING ERRCODE = 'P0001';
    END IF;
    FOR v_line IN SELECT x.line FROM jsonb_array_elements(p_payload->'lines') AS x(line) LOOP
        IF jsonb_typeof(v_line) IS DISTINCT FROM 'object'
           OR (SELECT count(*) FROM jsonb_object_keys(v_line)) <> 4
           OR NOT v_line ?& ARRAY['line_no','customer_id','debt_period','amount_vnd']
           OR jsonb_typeof(v_line->'line_no') IS DISTINCT FROM 'number'
           OR jsonb_typeof(v_line->'amount_vnd') IS DISTINCT FROM 'number'
           OR (v_line->>'line_no')::integer < 1
           OR (v_line->>'line_no')::numeric <> trunc((v_line->>'line_no')::numeric)
           OR (v_line->>'amount_vnd')::numeric <= 0
           OR (v_line->>'amount_vnd')::numeric <> trunc((v_line->>'amount_vnd')::numeric)
           OR (v_line->>'customer_id') IS NULL OR length(btrim(v_line->>'customer_id')) = 0
           OR (v_line->>'debt_period') IS NULL
           OR (v_line->>'debt_period') !~ '^\d{4}-(0[1-9]|1[0-2])$' THEN
            RAISE EXCEPTION 'invalid fixture line' USING ERRCODE = 'P0001';
        END IF;
    END LOOP;
    SELECT jsonb_agg(jsonb_build_object(
        'line_no', (x.line->>'line_no')::integer,
        'customer_id', x.line->>'customer_id',
        'debt_period', x.line->>'debt_period',
        'amount_vnd', (x.line->>'amount_vnd')::numeric
    ) ORDER BY (x.line->>'line_no')::integer)
    INTO v_lines
    FROM jsonb_array_elements(p_payload->'lines') AS x(line);
    IF (SELECT sum((x.line->>'amount_vnd')::numeric)
        FROM jsonb_array_elements(v_lines) AS x(line)) <> v_total THEN
        RAISE EXCEPTION 'fixture line sum differs from total' USING ERRCODE = 'P0001';
    END IF;
    IF EXISTS (SELECT 1 FROM jsonb_array_elements(v_lines) AS x(line)
        WHERE x.line->>'customer_id' <> p_payload->>'customer_id'
           OR x.line->>'debt_period' <> p_payload->>'debt_period') THEN
        RAISE EXCEPTION 'fixture lines must match document customer and period' USING ERRCODE = 'P0001';
    END IF;

    RETURN jsonb_build_object(
        'schema_version', 1,
        'kind', p_payload->>'kind',
        'customer_id', p_payload->>'customer_id',
        'debt_period', p_payload->>'debt_period',
        'total_vnd', v_total,
        'event_date', to_char((p_payload->>'event_date')::date, 'YYYY-MM-DD'),
        'posting_date', to_char((p_payload->>'posting_date')::date, 'YYYY-MM-DD'),
        'source_ref', p_payload->>'source_ref',
        'evidence_ref', p_payload->>'evidence_ref',
        'evidence_sha256', p_payload->>'evidence_sha256',
        'reason', p_payload->>'reason',
        'lines', v_lines
    );
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
    v_scope text;
    v_proposal_id bigint;
    v_revision_id bigint;
    v_revision_no integer;
    v_created boolean := false;
    v_maker uuid;
    v_state text;
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
    v_hash := encode(public.digest(convert_to(
        'webdebit.business-payload.v1' || E'\n' || v_canonical::text, 'UTF8'), 'sha256'), 'hex');

    IF p_proposal_id IS NULL THEN
        INSERT INTO p0_fixture.proposal(maker_actor_id)
        VALUES (p_actor_id) RETURNING p0_fixture.proposal.proposal_id INTO v_proposal_id;
        v_revision_no := 1;
        v_created := true;
    ELSE
        SELECT p.maker_actor_id, p.state, p.revision_no, p.current_revision_id
          INTO v_maker, v_state, v_revision_no, v_revision_id
        FROM p0_fixture.proposal p WHERE p.proposal_id = p_proposal_id FOR UPDATE;
        IF NOT FOUND OR v_maker <> p_actor_id OR v_state = 'posted' THEN
            RAISE EXCEPTION 'proposal unavailable to this maker' USING ERRCODE = 'P0001';
        END IF;
        SELECT r.content_sha256 INTO v_current_hash
        FROM p0_fixture.business_revision r
        WHERE r.proposal_id = p_proposal_id AND r.revision_id = v_revision_id;
        IF v_current_hash = v_hash THEN
            INSERT INTO p0_fixture.audit(proposal_id, revision_id, content_sha256,
                app_actor_id, app_session_id, assertion_nonce, key_id, database_session_user,
                action, request_scope)
            VALUES (p_proposal_id, v_revision_id, v_current_hash, p_actor_id, p_session_id,
                p_nonce, p_key_id, session_user, 'submit_noop', v_scope);
            RETURN QUERY SELECT p_proposal_id, v_revision_id, v_revision_no, v_current_hash, false;
            RETURN;
        END IF;
        v_revision_no := v_revision_no + 1;
        v_proposal_id := p_proposal_id;
        v_created := true;
    END IF;

    INSERT INTO p0_fixture.business_revision(proposal_id, revision_no, canonical_payload,
        content_sha256, created_by_actor, created_in_session)
    VALUES (v_proposal_id, v_revision_no, v_canonical, v_hash, p_actor_id, p_session_id)
    RETURNING p0_fixture.business_revision.revision_id INTO v_revision_id;
    UPDATE p0_fixture.proposal
    SET current_revision_id = v_revision_id, revision_no = v_revision_no, state = 'pending'
    WHERE p0_fixture.proposal.proposal_id = v_proposal_id;
    INSERT INTO p0_fixture.audit(proposal_id, revision_id, content_sha256,
        app_actor_id, app_session_id, assertion_nonce, key_id, database_session_user,
        action, request_scope)
    VALUES (v_proposal_id, v_revision_id, v_hash, p_actor_id, p_session_id,
        p_nonce, p_key_id, session_user, 'submit', v_scope);
    RETURN QUERY SELECT v_proposal_id, v_revision_id, v_revision_no, v_hash, v_created;
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
DECLARE v_scope text; v_maker uuid;
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
    SELECT p.maker_actor_id INTO v_maker FROM p0_fixture.proposal p
    WHERE p.proposal_id = p_proposal_id FOR UPDATE;
    IF NOT FOUND OR v_maker <> p_actor_id THEN
        RAISE EXCEPTION 'proposal unavailable to this maker' USING ERRCODE = 'P0001';
    END IF;
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
DECLARE v_proposal p0_fixture.proposal%ROWTYPE; v_hash text;
    v_scope text := 'approve:' || p_proposal_id::text || ':' ||
        p_revision_id::text || ':' || p_content_sha256;
BEGIN
    PERFORM p0_fixture.verify_actor_assertion(p_actor_id, p_session_id, 'approve',
        p_nonce, p_issued_epoch, p_key_id, v_scope, p_signature);
    IF NOT EXISTS (SELECT 1 FROM p0_fixture.app_actor_role
                   WHERE actor_id = p_actor_id AND app_role = 'checker') THEN
        RAISE EXCEPTION 'checker role required' USING ERRCODE = 'P0001';
    END IF;
    SELECT * INTO v_proposal FROM p0_fixture.proposal
    WHERE proposal_id = p_proposal_id FOR UPDATE;
    SELECT r.content_sha256 INTO v_hash FROM p0_fixture.business_revision r
    WHERE r.proposal_id = p_proposal_id AND r.revision_id = p_revision_id;
    IF NOT FOUND OR v_proposal.proposal_id IS NULL OR v_proposal.state <> 'pending'
       OR v_proposal.current_revision_id <> p_revision_id OR v_hash <> p_content_sha256
       OR v_proposal.maker_actor_id = p_actor_id THEN
        RAISE EXCEPTION 'stale, unavailable, or self-approved revision' USING ERRCODE = 'P0001';
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
BEGIN
    PERFORM p0_fixture.verify_actor_assertion(p_actor_id, p_session_id, 'post',
        p_nonce, p_issued_epoch, p_key_id, v_scope, p_signature);
    IF NOT EXISTS (SELECT 1 FROM p0_fixture.app_actor_role
                   WHERE actor_id = p_actor_id AND app_role = 'checker') THEN
        RAISE EXCEPTION 'checker role required' USING ERRCODE = 'P0001';
    END IF;
    SELECT * INTO v_proposal FROM p0_fixture.proposal
    WHERE proposal_id = p_proposal_id FOR UPDATE;
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
    ('44444444-4444-4444-8444-444444444444', true);
INSERT INTO p0_fixture.app_actor_role(actor_id, app_role) VALUES
    ('11111111-1111-4111-8111-111111111111', 'maker'),
    ('11111111-1111-4111-8111-111111111111', 'checker'),
    ('22222222-2222-4222-8222-222222222222', 'checker'),
    ('33333333-3333-4333-8333-333333333333', 'maker'),
    ('44444444-4444-4444-8444-444444444444', 'maker');
INSERT INTO p0_fixture.actor_signing_key(key_id, secret)
VALUES ('fixture-key-v1', decode(repeat('11', 32), 'hex'));

RESET ROLE;

REVOKE ALL ON ALL TABLES IN SCHEMA p0_fixture FROM PUBLIC, p0_fixture_api;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA p0_fixture FROM PUBLIC, p0_fixture_api;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA p0_fixture FROM PUBLIC;
GRANT EXECUTE ON FUNCTION p0_fixture.submit_revision(bigint,text,uuid,uuid,uuid,bigint,text,text)
    TO p0_fixture_api;
GRANT EXECUTE ON FUNCTION p0_fixture.set_presentation_title(bigint,text,uuid,uuid,uuid,bigint,text,text)
    TO p0_fixture_api;
GRANT EXECUTE ON FUNCTION p0_fixture.approve_revision(bigint,bigint,text,uuid,uuid,uuid,bigint,text,text)
    TO p0_fixture_api;
GRANT EXECUTE ON FUNCTION p0_fixture.post_revision(bigint,bigint,text,uuid,uuid,uuid,bigint,text,text)
    TO p0_fixture_api;
