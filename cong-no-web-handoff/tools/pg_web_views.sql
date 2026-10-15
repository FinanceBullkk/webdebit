-- Read-only web projection over the fixed M1 pilot. No posting or approval API.
BEGIN;

CREATE OR REPLACE VIEW pilot.web_period_event AS
SELECT e.capture_id, e.as_of, e.event_no, e.customer,
       e.debt_period, e.posting_date, e.kind, e.amount_vnd,
       e.signed_amount_vnd, e.sheet_gid, e.source_row,
       r.tab_title, r.row_sha256,
       'https://docs.google.com/spreadsheets/d/' || c.source_spreadsheet_id
       || '/edit#gid=' || e.sheet_gid || '&range=A' || e.source_row AS source_url
FROM pilot.replay_event e
JOIN pilot.raw_row r ON r.capture_id = e.capture_id
    AND r.sheet_gid = e.sheet_gid AND r.source_row = e.source_row
JOIN pilot.capture c ON c.capture_id = e.capture_id;

CREATE OR REPLACE VIEW pilot.web_source_row AS
SELECT r.capture_id, r.sheet_gid, r.source_row, r.tab_title,
       r.row_sha256, r.record -> 'values' AS source_values,
       'https://docs.google.com/spreadsheets/d/' || c.source_spreadsheet_id
       || '/edit#gid=' || r.sheet_gid || '&range=A' || r.source_row AS source_url
FROM pilot.raw_row r
JOIN pilot.capture c ON c.capture_id = r.capture_id
WHERE r.tab_title IN ('Khách hàng', 'Số dư đầu', 'Chuyến hàng',
                      'Thu & cấn trừ', '07 Đối soát', '17 Đối soát theo khách');

DO $role$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'webdebit_view') THEN
        CREATE ROLE webdebit_view LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE
            NOREPLICATION CONNECTION LIMIT 12;
    END IF;
END $role$;

ALTER ROLE webdebit_view NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION LOGIN;
ALTER ROLE webdebit_view SET default_transaction_read_only = on;
ALTER ROLE webdebit_view SET statement_timeout = '4s';
GRANT CONNECT ON DATABASE :"dbname" TO webdebit_view;
GRANT USAGE ON SCHEMA pilot TO webdebit_view;
REVOKE ALL ON ALL TABLES IN SCHEMA pilot FROM webdebit_view;
GRANT SELECT ON pilot.m1_provenance, pilot.m1_coverage,
    pilot.m1_period_balance, pilot.m1_customer_balance,
    pilot.m1_period_diff, pilot.m1_customer_diff,
    pilot.m1_exception_detail, pilot.web_period_event,
    pilot.web_source_row TO webdebit_view;

COMMIT;
