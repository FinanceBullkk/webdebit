-- Independent AR ledger. Run in a new, empty webdebit_ledger database.
-- Historical replay belongs only in the opening import, never in new postings.
\set ON_ERROR_STOP on
BEGIN;

CREATE SCHEMA ledger;
REVOKE ALL ON SCHEMA public FROM PUBLIC;
REVOKE ALL ON DATABASE webdebit_ledger FROM PUBLIC;

CREATE ROLE ledger_maker NOLOGIN;
CREATE ROLE ledger_checker NOLOGIN;
CREATE ROLE ledger_reader NOLOGIN;
GRANT CONNECT ON DATABASE webdebit_ledger TO ledger_maker, ledger_checker, ledger_reader;
GRANT USAGE ON SCHEMA ledger TO ledger_maker, ledger_checker, ledger_reader;

CREATE TABLE ledger.cutover (
    singleton boolean PRIMARY KEY DEFAULT true CHECK (singleton),
    capture_id text NOT NULL,
    as_of date NOT NULL,
    captured_at_utc timestamptz NOT NULL,
    source_spreadsheet_id text NOT NULL,
    source_workbook_sha256 text NOT NULL CHECK (source_workbook_sha256 ~ '^[0-9a-f]{64}$'),
    engine_sha256 text NOT NULL CHECK (engine_sha256 ~ '^[0-9a-f]{64}$'),
    period_report_sha256 text NOT NULL CHECK (period_report_sha256 ~ '^[0-9a-f]{64}$'),
    opening_decision text NOT NULL,
    first_posting_date date NOT NULL,
    imported_at timestamptz NOT NULL DEFAULT now(),
    CHECK (first_posting_date > as_of)
);

CREATE TABLE ledger.customer (
    customer text PRIMARY KEY CHECK (length(btrim(customer)) > 0),
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE ledger.opening (
    customer text NOT NULL REFERENCES ledger.customer,
    debt_period text NOT NULL CHECK (debt_period ~ '^\d{4}-(0[1-9]|1[0-2])$'),
    balance_vnd numeric(20,0) NOT NULL,
    replay_event_count integer NOT NULL CHECK (replay_event_count > 0),
    comparison_status text NOT NULL CHECK (comparison_status IN ('MATCH', 'NO_BASELINE')),
    PRIMARY KEY (customer, debt_period)
);

CREATE TABLE ledger.proposal (
    proposal_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    request_key text NOT NULL UNIQUE CHECK (length(request_key) BETWEEN 16 AND 128),
    kind text NOT NULL CHECK (kind IN ('charge', 'receipt', 'offset', 'adjustment_plus', 'adjustment_minus', 'reversal')),
    total_vnd numeric(20,0) NOT NULL CHECK (total_vnd > 0),
    event_date date NOT NULL,
    posting_date date NOT NULL,
    source_ref text NOT NULL CHECK (length(btrim(source_ref)) >= 5),
    evidence_ref text NOT NULL CHECK (length(btrim(evidence_ref)) >= 5),
    reason text NOT NULL CHECK (length(btrim(reason)) >= 5),
    maker name NOT NULL,
    checker name,
    status text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'rejected', 'posted')),
    created_at timestamptz NOT NULL DEFAULT now(),
    decided_at timestamptz,
    original_posting_id bigint,
    CHECK ((kind = 'reversal') = (original_posting_id IS NOT NULL)),
    CHECK ((status = 'pending' AND checker IS NULL AND decided_at IS NULL)
        OR (status <> 'pending' AND checker IS NOT NULL AND decided_at IS NOT NULL))
);

CREATE UNIQUE INDEX proposal_receipt_source_once
    ON ledger.proposal (source_ref) WHERE kind = 'receipt' AND status <> 'rejected';

CREATE TABLE ledger.proposal_line (
    proposal_id bigint NOT NULL REFERENCES ledger.proposal,
    line_no integer NOT NULL CHECK (line_no > 0),
    customer text NOT NULL REFERENCES ledger.customer,
    debt_period text NOT NULL CHECK (debt_period ~ '^\d{4}-(0[1-9]|1[0-2])$'),
    amount_vnd numeric(20,0) NOT NULL CHECK (amount_vnd > 0),
    PRIMARY KEY (proposal_id, line_no),
    UNIQUE (proposal_id, customer, debt_period)
);

CREATE TABLE ledger.posting (
    posting_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    proposal_id bigint NOT NULL REFERENCES ledger.proposal,
    line_no integer NOT NULL,
    customer text NOT NULL REFERENCES ledger.customer,
    debt_period text NOT NULL CHECK (debt_period ~ '^\d{4}-(0[1-9]|1[0-2])$'),
    kind text NOT NULL,
    signed_amount_vnd numeric(20,0) NOT NULL CHECK (signed_amount_vnd <> 0),
    posting_date date NOT NULL,
    event_date date NOT NULL,
    source_ref text NOT NULL,
    evidence_ref text NOT NULL,
    reason text NOT NULL,
    maker name NOT NULL,
    checker name NOT NULL CHECK (checker <> maker),
    original_posting_id bigint REFERENCES ledger.posting,
    posted_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (proposal_id, line_no),
    FOREIGN KEY (proposal_id, line_no) REFERENCES ledger.proposal_line
);
CREATE UNIQUE INDEX posting_one_reversal ON ledger.posting (original_posting_id)
    WHERE original_posting_id IS NOT NULL;
CREATE INDEX posting_customer_period_date ON ledger.posting (customer, debt_period, posting_date);

CREATE TABLE ledger.audit (
    audit_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    proposal_id bigint REFERENCES ledger.proposal,
    actor name NOT NULL,
    action text NOT NULL CHECK (action IN ('submit', 'approve', 'reject', 'request_reversal')),
    at timestamptz NOT NULL DEFAULT now(),
    detail jsonb NOT NULL DEFAULT '{}'::jsonb
);

CREATE FUNCTION ledger.no_change() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'posted or opening ledger rows are immutable';
END $$;
CREATE TRIGGER opening_immutable BEFORE UPDATE OR DELETE ON ledger.opening
    FOR EACH ROW EXECUTE FUNCTION ledger.no_change();
CREATE TRIGGER posting_immutable BEFORE UPDATE OR DELETE ON ledger.posting
    FOR EACH ROW EXECUTE FUNCTION ledger.no_change();

-- Posting-date window for every write function: a missing cutover row is an error,
-- never an absent bound; posting dates after today (Vietnam business day) are rejected.
CREATE FUNCTION ledger.first_posting_date() RETURNS date
LANGUAGE plpgsql STABLE SET search_path = pg_catalog, ledger AS $$
DECLARE v_first date;
BEGIN
    SELECT first_posting_date INTO v_first FROM ledger.cutover WHERE singleton;
    IF v_first IS NULL THEN
        RAISE EXCEPTION 'ledger cutover missing';
    END IF;
    RETURN v_first;
END $$;

CREATE FUNCTION ledger.business_today() RETURNS date
LANGUAGE sql STABLE SET search_path = pg_catalog AS $$
    SELECT (now() AT TIME ZONE 'Asia/Ho_Chi_Minh')::date
$$;

CREATE FUNCTION ledger.cutover_as_of() RETURNS date
LANGUAGE plpgsql STABLE SET search_path = pg_catalog, ledger AS $$
DECLARE v_as_of date;
BEGIN
    SELECT as_of INTO v_as_of FROM ledger.cutover WHERE singleton;
    IF v_as_of IS NULL THEN
        RAISE EXCEPTION 'ledger cutover missing';
    END IF;
    RETURN v_as_of;
END $$;

CREATE FUNCTION ledger.submit_entry(
    p_request_key text, p_kind text, p_total_vnd numeric,
    p_event_date date, p_posting_date date, p_source_ref text,
    p_evidence_ref text, p_reason text, p_lines jsonb
) RETURNS bigint LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, ledger AS $$
DECLARE
    v_id bigint;
    v_line_count integer;
    v_line_total numeric;
BEGIN
    IF NOT pg_has_role(session_user, 'ledger_maker', 'member') THEN
        RAISE EXCEPTION 'maker role required';
    END IF;
    IF p_kind NOT IN ('charge', 'receipt', 'offset', 'adjustment_plus', 'adjustment_minus')
       OR p_total_vnd IS NULL OR p_total_vnd <= 0 OR p_total_vnd <> trunc(p_total_vnd)
       OR p_total_vnd > 99999999999999999999::numeric THEN
        RAISE EXCEPTION 'invalid kind or amount';
    END IF;
    IF p_request_key IS NULL OR length(p_request_key) NOT BETWEEN 16 AND 128
       OR p_event_date IS NULL OR p_posting_date IS NULL
       OR p_posting_date < ledger.first_posting_date()
       OR p_posting_date > ledger.business_today()
       OR p_source_ref IS NULL OR length(btrim(p_source_ref)) < 5
       OR p_evidence_ref IS NULL OR length(btrim(p_evidence_ref)) < 5
       OR p_reason IS NULL OR length(btrim(p_reason)) < 5
       OR jsonb_typeof(p_lines) IS DISTINCT FROM 'array' THEN
        RAISE EXCEPTION 'missing or invalid posting evidence/date/lines';
    END IF;
    SELECT count(*), sum(x.amount_vnd) INTO v_line_count, v_line_total
    FROM jsonb_to_recordset(p_lines) AS x(customer text, debt_period text, amount_vnd numeric);
    IF EXISTS (
        SELECT 1 FROM jsonb_to_recordset(p_lines)
            AS x(customer text, debt_period text, amount_vnd numeric)
        WHERE x.customer IS NULL OR length(btrim(x.customer)) = 0
           OR x.debt_period IS NULL OR x.debt_period !~ '^\d{4}-(0[1-9]|1[0-2])$'
           OR x.amount_vnd IS NULL OR x.amount_vnd <= 0
           OR x.amount_vnd <> trunc(x.amount_vnd)
           OR x.amount_vnd > 99999999999999999999::numeric
    ) THEN
        RAISE EXCEPTION 'invalid allocation line';
    END IF;
    IF v_line_count < 1 OR (p_kind <> 'receipt' AND v_line_count <> 1)
       OR v_line_total IS DISTINCT FROM p_total_vnd THEN
        RAISE EXCEPTION 'allocation count or sum differs from total';
    END IF;
    INSERT INTO ledger.proposal(request_key, kind, total_vnd, event_date, posting_date,
                                source_ref, evidence_ref, reason, maker)
    VALUES (p_request_key, p_kind, p_total_vnd, p_event_date, p_posting_date,
            p_source_ref, p_evidence_ref, p_reason, session_user)
    RETURNING proposal_id INTO v_id;
    INSERT INTO ledger.proposal_line(proposal_id, line_no, customer, debt_period, amount_vnd)
    SELECT v_id, x.line_no, x.customer, x.debt_period, x.amount_vnd
    FROM ROWS FROM (jsonb_to_recordset(p_lines)
        AS (customer text, debt_period text, amount_vnd numeric))
        WITH ORDINALITY AS x(customer, debt_period, amount_vnd, line_no);
    INSERT INTO ledger.audit(proposal_id, actor, action, detail)
    VALUES (v_id, session_user, 'submit', jsonb_build_object('request_key', p_request_key));
    RETURN v_id;
END $$;

CREATE FUNCTION ledger.approve_entry(p_proposal_id bigint) RETURNS integer
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, ledger AS $$
DECLARE
    v ledger.proposal%ROWTYPE;
    v_count integer;
BEGIN
    IF NOT pg_has_role(session_user, 'ledger_checker', 'member') THEN
        RAISE EXCEPTION 'checker role required';
    END IF;
    SELECT * INTO v FROM ledger.proposal WHERE proposal_id = p_proposal_id FOR UPDATE;
    IF NOT FOUND OR v.status <> 'pending' OR v.maker = session_user THEN
        RAISE EXCEPTION 'proposal absent, decided, or self approval';
    END IF;
    IF v.posting_date < ledger.first_posting_date() THEN
        RAISE EXCEPTION 'posting date precedes cutover';
    END IF;
    IF v.posting_date > ledger.business_today() THEN
        RAISE EXCEPTION 'posting date is in the future';
    END IF;
    IF v.kind = 'reversal' AND EXISTS (
        SELECT 1 FROM ledger.posting WHERE original_posting_id = v.original_posting_id) THEN
        RAISE EXCEPTION 'original posting already reversed';
    END IF;
    INSERT INTO ledger.posting(proposal_id, line_no, customer, debt_period, kind,
                               signed_amount_vnd, posting_date, event_date, source_ref,
                               evidence_ref, reason, maker, checker, original_posting_id)
    SELECT v.proposal_id, l.line_no, l.customer, l.debt_period, v.kind,
           CASE WHEN v.kind = 'reversal' THEN -original.signed_amount_vnd
                WHEN v.kind IN ('receipt', 'offset', 'adjustment_minus') THEN -l.amount_vnd
                ELSE l.amount_vnd END,
           v.posting_date, v.event_date, v.source_ref, v.evidence_ref, v.reason,
           v.maker, session_user, v.original_posting_id
    FROM ledger.proposal_line l
    LEFT JOIN ledger.posting original ON original.posting_id = v.original_posting_id
    WHERE l.proposal_id = v.proposal_id;
    GET DIAGNOSTICS v_count = ROW_COUNT;
    IF v_count = 0 THEN RAISE EXCEPTION 'proposal has no allocation lines'; END IF;
    UPDATE ledger.proposal SET status = 'posted', checker = session_user, decided_at = now()
    WHERE proposal_id = v.proposal_id;
    INSERT INTO ledger.audit(proposal_id, actor, action, detail)
    VALUES (v.proposal_id, session_user, 'approve', jsonb_build_object('posting_lines', v_count));
    RETURN v_count;
END $$;

CREATE FUNCTION ledger.reject_entry(p_proposal_id bigint, p_reason text) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, ledger AS $$
DECLARE v ledger.proposal%ROWTYPE;
BEGIN
    IF NOT pg_has_role(session_user, 'ledger_checker', 'member') OR
       p_reason IS NULL OR length(btrim(p_reason)) < 5 THEN
        RAISE EXCEPTION 'checker and rejection reason required';
    END IF;
    SELECT * INTO v FROM ledger.proposal WHERE proposal_id = p_proposal_id FOR UPDATE;
    IF NOT FOUND OR v.status <> 'pending' OR v.maker = session_user THEN
        RAISE EXCEPTION 'proposal absent, decided, or self rejection';
    END IF;
    UPDATE ledger.proposal SET status = 'rejected', checker = session_user, decided_at = now()
    WHERE proposal_id = v.proposal_id;
    INSERT INTO ledger.audit(proposal_id, actor, action, detail)
    VALUES (v.proposal_id, session_user, 'reject', jsonb_build_object('reason', p_reason));
END $$;

CREATE FUNCTION ledger.request_reversal(
    p_request_key text, p_original_posting_id bigint, p_posting_date date,
    p_evidence_ref text, p_reason text
) RETURNS bigint LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, ledger AS $$
DECLARE v ledger.posting%ROWTYPE; v_id bigint;
BEGIN
    IF NOT pg_has_role(session_user, 'ledger_maker', 'member') THEN
        RAISE EXCEPTION 'maker role required';
    END IF;
    SELECT * INTO v FROM ledger.posting WHERE posting_id = p_original_posting_id;
    IF NOT FOUND OR v.kind = 'reversal' OR EXISTS
       (SELECT 1 FROM ledger.posting WHERE original_posting_id = p_original_posting_id)
       OR p_request_key IS NULL OR length(p_request_key) NOT BETWEEN 16 AND 128
       OR p_posting_date IS NULL OR p_posting_date < ledger.first_posting_date()
       OR p_posting_date > ledger.business_today()
       OR p_evidence_ref IS NULL OR length(btrim(p_evidence_ref)) < 5
       OR p_reason IS NULL OR length(btrim(p_reason)) < 5 THEN
        RAISE EXCEPTION 'invalid reversal request';
    END IF;
    INSERT INTO ledger.proposal(request_key, kind, total_vnd, event_date, posting_date,
                                source_ref, evidence_ref, reason, maker, original_posting_id)
    VALUES (p_request_key, 'reversal', abs(v.signed_amount_vnd), ledger.business_today(),
            p_posting_date, 'reversal:' || p_original_posting_id,
            p_evidence_ref, p_reason, session_user, p_original_posting_id)
    RETURNING proposal_id INTO v_id;
    INSERT INTO ledger.proposal_line(proposal_id, line_no, customer, debt_period, amount_vnd)
    VALUES (v_id, 1, v.customer, v.debt_period, abs(v.signed_amount_vnd));
    INSERT INTO ledger.audit(proposal_id, actor, action, detail)
    VALUES (v_id, session_user, 'request_reversal',
            jsonb_build_object('original_posting_id', p_original_posting_id));
    RETURN v_id;
END $$;

CREATE VIEW ledger.balance AS
SELECT o.customer, o.debt_period, o.balance_vnd AS opening_vnd,
       coalesce(sum(p.signed_amount_vnd), 0)::numeric(20,0) AS movement_vnd,
       (o.balance_vnd + coalesce(sum(p.signed_amount_vnd), 0))::numeric(20,0) AS balance_vnd
FROM ledger.opening o
LEFT JOIN ledger.posting p ON p.customer = o.customer AND p.debt_period = o.debt_period
GROUP BY o.customer, o.debt_period, o.balance_vnd
UNION ALL
SELECT p.customer, p.debt_period, 0::numeric(20,0) AS opening_vnd,
       sum(p.signed_amount_vnd)::numeric(20,0) AS movement_vnd,
       sum(p.signed_amount_vnd)::numeric(20,0) AS balance_vnd
FROM ledger.posting p
WHERE NOT EXISTS (SELECT 1 FROM ledger.opening o
                  WHERE o.customer = p.customer AND o.debt_period = p.debt_period)
GROUP BY p.customer, p.debt_period;

CREATE FUNCTION ledger.balance_as_of(p_date date)
RETURNS TABLE(customer text, debt_period text, opening_vnd numeric,
              movement_vnd numeric, balance_vnd numeric)
LANGUAGE sql STABLE AS $$
    WITH rows AS (
        SELECT o.customer, o.debt_period, o.balance_vnd AS amount, true AS opening
        FROM ledger.opening o
        WHERE p_date >= ledger.cutover_as_of()
        UNION ALL
        SELECT p.customer, p.debt_period, p.signed_amount_vnd, false
        FROM ledger.posting p WHERE p.posting_date <= p_date
    )
    SELECT customer, debt_period,
           sum(amount) FILTER (WHERE opening),
           coalesce(sum(amount) FILTER (WHERE NOT opening), 0),
           sum(amount)
    FROM rows GROUP BY customer, debt_period
$$;

REVOKE ALL ON ALL TABLES IN SCHEMA ledger FROM PUBLIC;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA ledger FROM PUBLIC;
GRANT SELECT ON ledger.cutover, ledger.customer, ledger.opening,
    ledger.proposal, ledger.proposal_line, ledger.posting, ledger.audit,
    ledger.balance TO ledger_maker, ledger_checker, ledger_reader;
GRANT EXECUTE ON FUNCTION ledger.balance_as_of(date) TO ledger_maker, ledger_checker, ledger_reader;
GRANT EXECUTE ON FUNCTION ledger.cutover_as_of() TO ledger_maker, ledger_checker, ledger_reader;
GRANT EXECUTE ON FUNCTION ledger.submit_entry(text,text,numeric,date,date,text,text,text,jsonb)
    TO ledger_maker;
GRANT EXECUTE ON FUNCTION ledger.request_reversal(text,bigint,date,text,text)
    TO ledger_maker;
GRANT EXECUTE ON FUNCTION ledger.approve_entry(bigint), ledger.reject_entry(bigint,text)
    TO ledger_checker;

COMMIT;
