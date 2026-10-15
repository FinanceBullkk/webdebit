-- Isolated, read-only replay store. These are not approved ledger postings.
CREATE SCHEMA pilot;

CREATE TABLE pilot.capture (
    capture_id text PRIMARY KEY,
    source_spreadsheet_id text NOT NULL,
    source_title text NOT NULL,
    captured_at_utc timestamptz NOT NULL,
    source_workbook_sha256 text NOT NULL CHECK (source_workbook_sha256 ~ '^[0-9a-f]{64}$'),
    manifest jsonb NOT NULL
);

CREATE TABLE pilot.raw_row (
    capture_id text NOT NULL REFERENCES pilot.capture,
    sheet_gid bigint NOT NULL,
    source_row integer NOT NULL CHECK (source_row > 0),
    tab_title text NOT NULL,
    record jsonb NOT NULL,
    row_sha256 text NOT NULL CHECK (row_sha256 ~ '^[0-9a-f]{64}$'),
    PRIMARY KEY (capture_id, sheet_gid, source_row),
    CHECK ((record ->> 'capture_id') = capture_id),
    CHECK ((record ->> 'sheet_gid')::bigint = sheet_gid),
    CHECK ((record ->> 'source_row')::integer = source_row)
);

CREATE TABLE pilot.replay_run (
    capture_id text NOT NULL REFERENCES pilot.capture,
    as_of date NOT NULL,
    engine_sha256 text NOT NULL CHECK (engine_sha256 ~ '^[0-9a-f]{64}$'),
    summary jsonb NOT NULL,
    PRIMARY KEY (capture_id, as_of)
);

CREATE TABLE pilot.replay_event (
    capture_id text NOT NULL,
    as_of date NOT NULL,
    event_no integer NOT NULL,
    customer text NOT NULL,
    debt_period text NOT NULL CHECK (debt_period ~ '^\d{4}-(0[1-9]|1[0-2])$'),
    posting_date date NOT NULL,
    kind text NOT NULL,
    amount_vnd numeric(20,0) NOT NULL,
    signed_amount_vnd numeric(20,0) NOT NULL,
    sheet_gid bigint NOT NULL,
    source_row integer NOT NULL,
    PRIMARY KEY (capture_id, as_of, event_no),
    FOREIGN KEY (capture_id, as_of) REFERENCES pilot.replay_run,
    FOREIGN KEY (capture_id, sheet_gid, source_row) REFERENCES pilot.raw_row
);

CREATE INDEX replay_event_customer_period_idx
    ON pilot.replay_event (capture_id, as_of, customer, debt_period);

COMMENT ON SCHEMA pilot IS 'Historical source snapshot and calculated replay only; no production postings or approvals.';
