-- M1 pilot only: classifications and exceptions are observations of a Sheet
-- snapshot, never approvals or production ledger entries.
CREATE TABLE IF NOT EXISTS pilot.source_decision (
    capture_id text NOT NULL,
    as_of date NOT NULL,
    sheet_gid bigint NOT NULL,
    source_row integer NOT NULL,
    result text NOT NULL CHECK (result IN ('accepted', 'replayed', 'quarantined', 'excluded_as_of')),
    reason text,
    PRIMARY KEY (capture_id, as_of, sheet_gid, source_row),
    FOREIGN KEY (capture_id, as_of) REFERENCES pilot.replay_run,
    FOREIGN KEY (capture_id, sheet_gid, source_row) REFERENCES pilot.raw_row
);

CREATE TABLE IF NOT EXISTS pilot.source_exception (
    capture_id text NOT NULL,
    as_of date NOT NULL,
    exception_no integer NOT NULL CHECK (exception_no > 0),
    sheet_gid bigint NOT NULL,
    source_row integer NOT NULL,
    payload jsonb NOT NULL,
    PRIMARY KEY (capture_id, as_of, exception_no),
    FOREIGN KEY (capture_id, as_of) REFERENCES pilot.replay_run,
    FOREIGN KEY (capture_id, sheet_gid, source_row) REFERENCES pilot.raw_row,
    CHECK ((payload ->> 'sheet_gid')::bigint = sheet_gid),
    CHECK ((payload ->> 'source_row')::integer = source_row)
);

CREATE OR REPLACE VIEW pilot.m1_provenance AS
SELECT c.capture_id, r.as_of, c.source_spreadsheet_id, c.source_title,
       c.source_workbook_sha256, c.captured_at_utc, r.engine_sha256,
       (SELECT left(x.record -> 'values' ->> 1, 10)
        FROM pilot.raw_row x
        WHERE x.capture_id = c.capture_id
          AND x.tab_title = '17 Đối soát theo khách' AND x.source_row = 4) AS baseline_date
FROM pilot.capture c JOIN pilot.replay_run r USING (capture_id);

CREATE OR REPLACE VIEW pilot.m1_period_balance AS
SELECT capture_id, as_of, customer, debt_period,
       sum(amount_vnd) FILTER (WHERE kind = 'opening') AS opening_vnd,
       sum(amount_vnd) FILTER (WHERE kind = 'charge') AS charge_vnd,
       sum(amount_vnd) FILTER (WHERE kind = 'receipt') AS receipt_vnd,
       sum(amount_vnd) FILTER (WHERE kind = 'offset') AS offset_vnd,
       sum(amount_vnd) FILTER (WHERE kind = 'adjustment_plus') AS adjustment_plus_vnd,
       sum(amount_vnd) FILTER (WHERE kind = 'adjustment_minus') AS adjustment_minus_vnd,
       count(*) AS event_count,
       sum(signed_amount_vnd) AS balance_vnd
FROM pilot.replay_event
GROUP BY capture_id, as_of, customer, debt_period;

CREATE OR REPLACE VIEW pilot.m1_customer_balance AS
SELECT capture_id, as_of, customer, count(*) AS period_count,
       sum(balance_vnd) AS balance_vnd
FROM pilot.m1_period_balance
GROUP BY capture_id, as_of, customer;

CREATE OR REPLACE VIEW pilot.m1_coverage AS
WITH expected AS (
    SELECT r.capture_id, r.as_of, x.sheet_gid, x.source_row, x.tab_title,
           d.result
    FROM pilot.replay_run r
    JOIN pilot.capture c USING (capture_id)
    CROSS JOIN LATERAL jsonb_array_elements(c.manifest -> 'tabs') AS t(meta)
    JOIN pilot.raw_row x ON x.capture_id = c.capture_id
        AND x.sheet_gid = (t.meta ->> 'gid')::bigint
        AND x.source_row > (t.meta ->> 'header_row')::integer
    LEFT JOIN pilot.source_decision d ON d.capture_id = r.capture_id
        AND d.as_of = r.as_of AND d.sheet_gid = x.sheet_gid
        AND d.source_row = x.source_row
    WHERE t.meta ->> 'title' IN ('Khách hàng', 'Số dư đầu', 'Chuyến hàng', 'Thu & cấn trừ')
)
SELECT capture_id, as_of, sheet_gid, tab_title,
       count(*) AS source_rows,
       count(result) AS decided_rows,
       count(*) FILTER (WHERE result IS NULL) AS missing_rows,
       count(*) FILTER (WHERE result = 'accepted') AS accepted_rows,
       count(*) FILTER (WHERE result = 'replayed') AS replayed_rows,
       count(*) FILTER (WHERE result = 'quarantined') AS quarantined_rows,
       count(*) FILTER (WHERE result = 'excluded_as_of') AS excluded_as_of_rows
FROM expected
GROUP BY capture_id, as_of, sheet_gid, tab_title;

-- The historical baselines are only comparable to their own snapshot date.
-- A missing/invalid cached amount stays NULL; it is never silently zero.
CREATE OR REPLACE VIEW pilot.m1_baseline_date AS
SELECT c.capture_id,
       CASE WHEN left(r.record -> 'values' ->> 1, 10) ~ '^\d{4}-\d{2}-\d{2}$'
            THEN left(r.record -> 'values' ->> 1, 10)::date ELSE NULL END AS baseline_date
FROM pilot.capture c
JOIN pilot.raw_row r ON r.capture_id = c.capture_id
WHERE r.tab_title = '17 Đối soát theo khách' AND r.source_row = 4;

CREATE OR REPLACE VIEW pilot.m1_period_baseline AS
SELECT capture_id, sheet_gid, source_row,
       record -> 'values' ->> 0 AS customer,
       record -> 'values' ->> 1 AS debt_period,
       CASE WHEN (record -> 'values' ->> 9) ~ '^-?\d+$'
            THEN (record -> 'values' ->> 9)::numeric(20,0) ELSE NULL END AS balance_vnd,
       record -> 'values' ->> 11 AS source_label
FROM pilot.raw_row
WHERE tab_title = '07 Đối soát'
  AND source_row > 6
  AND (record -> 'values' ->> 0) IS NOT NULL
  AND (record -> 'values' ->> 1) ~ '^\d{4}-(0[1-9]|1[0-2])$';

CREATE OR REPLACE VIEW pilot.m1_customer_baseline AS
SELECT capture_id, sheet_gid, source_row,
       record -> 'values' ->> 0 AS customer,
       CASE WHEN (record -> 'values' ->> 5) ~ '^-?\d+$'
            THEN (record -> 'values' ->> 5)::numeric(20,0) ELSE NULL END AS balance_vnd,
       CASE WHEN (record -> 'values' ->> 7) ~ '^-?\d+$'
            THEN (record -> 'values' ->> 7)::numeric(20,0) ELSE NULL END AS old_book_delta_vnd
FROM pilot.raw_row
WHERE tab_title = '17 Đối soát theo khách'
  AND source_row > 6
  AND (record -> 'values' ->> 0) IS NOT NULL;

CREATE OR REPLACE VIEW pilot.m1_period_diff AS
WITH scoped AS (
    SELECT r.capture_id, r.as_of FROM pilot.replay_run r
    JOIN pilot.m1_baseline_date d ON d.capture_id = r.capture_id
        AND d.baseline_date = r.as_of
), baseline AS (
    SELECT capture_id, customer, debt_period, min(balance_vnd) AS balance_vnd,
           min(sheet_gid) AS sheet_gid, min(source_row) AS source_row,
           min(source_label) AS source_label, count(*) AS row_count
    FROM pilot.m1_period_baseline
    GROUP BY capture_id, customer, debt_period
), keys AS (
    SELECT s.capture_id, s.as_of, p.customer, p.debt_period
    FROM scoped s JOIN pilot.m1_period_balance p USING (capture_id, as_of)
    UNION
    SELECT s.capture_id, s.as_of, b.customer, b.debt_period
    FROM scoped s JOIN baseline b USING (capture_id)
)
SELECT k.capture_id, k.as_of, k.customer, k.debt_period,
       b.balance_vnd AS sheet_balance_vnd,
       p.balance_vnd AS db_balance_vnd,
       CASE WHEN b.balance_vnd IS NOT NULL THEN coalesce(p.balance_vnd, 0) - b.balance_vnd END AS delta_vnd,
       b.sheet_gid AS baseline_gid, b.source_row AS baseline_row, b.source_label,
       CASE WHEN b.source_row IS NULL THEN 'NO_BASELINE'
            WHEN b.row_count > 1 THEN 'DUPLICATE_BASELINE'
            WHEN b.balance_vnd IS NULL THEN 'INVALID_BASELINE'
            WHEN p.customer IS NULL THEN 'NO_DB_EVENTS'
            WHEN p.balance_vnd <> b.balance_vnd THEN 'MISMATCH'
            ELSE 'MATCH' END AS result
FROM keys k
LEFT JOIN baseline b ON b.capture_id = k.capture_id
    AND b.customer = k.customer AND b.debt_period = k.debt_period
LEFT JOIN pilot.m1_period_balance p ON p.capture_id = k.capture_id
    AND p.as_of = k.as_of AND p.customer = k.customer
    AND p.debt_period = k.debt_period;

CREATE OR REPLACE VIEW pilot.m1_customer_diff AS
WITH scoped AS (
    SELECT r.capture_id, r.as_of FROM pilot.replay_run r
    JOIN pilot.m1_baseline_date d ON d.capture_id = r.capture_id
        AND d.baseline_date = r.as_of
), baseline AS (
    SELECT capture_id, customer, min(balance_vnd) AS balance_vnd,
           min(sheet_gid) AS sheet_gid, min(source_row) AS source_row,
           min(old_book_delta_vnd) AS old_book_delta_vnd, count(*) AS row_count
    FROM pilot.m1_customer_baseline
    GROUP BY capture_id, customer
), keys AS (
    SELECT s.capture_id, s.as_of, p.customer
    FROM scoped s JOIN pilot.m1_customer_balance p USING (capture_id, as_of)
    UNION
    SELECT s.capture_id, s.as_of, b.customer
    FROM scoped s JOIN baseline b USING (capture_id)
)
SELECT k.capture_id, k.as_of, k.customer,
       b.balance_vnd AS sheet_balance_vnd,
       p.balance_vnd AS db_balance_vnd,
       CASE WHEN b.balance_vnd IS NOT NULL THEN coalesce(p.balance_vnd, 0) - b.balance_vnd END AS delta_vnd,
       b.sheet_gid AS baseline_gid, b.source_row AS baseline_row,
       b.old_book_delta_vnd,
       CASE WHEN b.source_row IS NULL THEN 'NO_BASELINE'
            WHEN b.row_count > 1 THEN 'DUPLICATE_BASELINE'
            WHEN b.balance_vnd IS NULL THEN 'INVALID_BASELINE'
            WHEN p.customer IS NULL THEN 'NO_DB_EVENTS'
            WHEN p.balance_vnd <> b.balance_vnd THEN 'MISMATCH'
            ELSE 'MATCH' END AS result
FROM keys k
LEFT JOIN baseline b ON b.capture_id = k.capture_id AND b.customer = k.customer
LEFT JOIN pilot.m1_customer_balance p ON p.capture_id = k.capture_id
    AND p.as_of = k.as_of AND p.customer = k.customer;

CREATE OR REPLACE VIEW pilot.m1_exception_detail AS
SELECT e.capture_id, e.as_of, e.exception_no,
       e.payload ->> 'code' AS code,
       e.payload ->> 'status' AS status,
       e.payload ->> 'resolution_status' AS resolution_status,
       e.payload ->> 'customer' AS customer,
       e.payload ->> 'period' AS debt_period,
       e.payload ->> 'detail' AS detail,
       r.tab_title, e.sheet_gid, e.source_row, r.row_sha256,
       'https://docs.google.com/spreadsheets/d/' || c.source_spreadsheet_id
       || '/edit#gid=' || e.sheet_gid || '&range=A' || e.source_row AS source_url
FROM pilot.source_exception e
JOIN pilot.raw_row r ON r.capture_id = e.capture_id
    AND r.sheet_gid = e.sheet_gid AND r.source_row = e.source_row
JOIN pilot.capture c ON c.capture_id = e.capture_id;
