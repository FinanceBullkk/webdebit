\set ON_ERROR_STOP on
BEGIN;

CREATE OR REPLACE FUNCTION ledger.first_posting_date() RETURNS date
LANGUAGE plpgsql STABLE SET search_path = pg_catalog, ledger AS $$
DECLARE v_first date;
BEGIN
    SELECT first_posting_date INTO v_first FROM ledger.cutover WHERE singleton;
    IF v_first IS NULL THEN
        RAISE EXCEPTION 'ledger cutover missing';
    END IF;
    RETURN v_first;
END $$;

CREATE OR REPLACE FUNCTION ledger.business_today() RETURNS date
LANGUAGE sql STABLE SET search_path = pg_catalog AS $$
    SELECT (now() AT TIME ZONE 'Asia/Ho_Chi_Minh')::date
$$;

CREATE OR REPLACE FUNCTION ledger.cutover_as_of() RETURNS date
LANGUAGE plpgsql STABLE SET search_path = pg_catalog, ledger AS $$
DECLARE v_as_of date;
BEGIN
    SELECT as_of INTO v_as_of FROM ledger.cutover WHERE singleton;
    IF v_as_of IS NULL THEN
        RAISE EXCEPTION 'ledger cutover missing';
    END IF;
    RETURN v_as_of;
END $$;

CREATE OR REPLACE FUNCTION ledger.submit_entry(
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

CREATE OR REPLACE FUNCTION ledger.approve_entry(p_proposal_id bigint) RETURNS integer
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

CREATE OR REPLACE FUNCTION ledger.request_reversal(
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

CREATE OR REPLACE FUNCTION ledger.balance_as_of(p_date date)
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

REVOKE ALL ON FUNCTION
    ledger.first_posting_date(), ledger.business_today(), ledger.cutover_as_of(),
    ledger.submit_entry(text,text,numeric,date,date,text,text,text,jsonb),
    ledger.approve_entry(bigint), ledger.request_reversal(text,bigint,date,text,text),
    ledger.balance_as_of(date) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION ledger.balance_as_of(date) TO ledger_maker, ledger_checker, ledger_reader;
GRANT EXECUTE ON FUNCTION ledger.cutover_as_of() TO ledger_maker, ledger_checker, ledger_reader;
GRANT EXECUTE ON FUNCTION ledger.submit_entry(text,text,numeric,date,date,text,text,text,jsonb)
    TO ledger_maker;
GRANT EXECUTE ON FUNCTION ledger.request_reversal(text,bigint,date,text,text)
    TO ledger_maker;
GRANT EXECUTE ON FUNCTION ledger.approve_entry(bigint)
    TO ledger_checker;

COMMIT;
