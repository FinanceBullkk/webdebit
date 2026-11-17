-- Lưới an toàn (LUOI-AN-TOAN-01, 18/11/2026): hàm đọc get_safety_net cho máy canh và hai hàm phụ tính dấu vân. Chỉ thêm hàm đọc
-- và quyền EXECUTE cho sokhach_app: không đổi bảng, view, hàm ghi, phân bổ, dữ liệu hay quyền cũ. Chạy lại được.
BEGIN;
SET LOCAL ROLE sokhach_owner;
-- LUOI-AN-TOAN-01 (18/11/2026): lưới an toàn của máy canh (specs/v7-luoi-an-toan.md). Ba hàm chỉ đọc; chỉ get_safety_net cấp cho app.
CREATE OR REPLACE FUNCTION sokhach._safety_fingerprints() RETURNS jsonb
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, sokhach, pg_temp SET timezone = 'UTC' SET datestyle = 'ISO, YMD' AS $$
-- LUOI-AN-TOAN-01 kiểm 3. Mỗi sổ: version và md5 từng phần dữ liệu tiền. md5 một phần nối md5 từng dòng theo khóa dòng (thứ tự byte);
-- bỏ khóa NULL nên thêm cột cho phép NULL không đổi dấu vân. Giờ UTC, ngày ISO cố định để dấu vân không theo cài đặt của phiên.
WITH r AS (
    SELECT customer_id, 'opening_balance'::text AS part, id::text AS k, md5(jsonb_strip_nulls(to_jsonb(x))::text) AS h FROM sokhach.opening_balance x
    UNION ALL SELECT customer_id, 'legacy_row', id::text, md5(jsonb_strip_nulls(to_jsonb(x))::text) FROM sokhach.legacy_row x
    UNION ALL SELECT customer_id, 'legacy_trip_rev', id::text, md5(jsonb_strip_nulls(to_jsonb(x))::text) FROM sokhach.legacy_trip_rev x
    UNION ALL SELECT customer_id, 'trip', id::text, md5(jsonb_strip_nulls(to_jsonb(x))::text) FROM sokhach.trip x
    UNION ALL SELECT customer_id, 'trip_info_rev', id::text, md5(jsonb_strip_nulls(to_jsonb(x))::text) FROM sokhach.trip_info_rev x
    UNION ALL SELECT customer_id, 'trip_price_rev', id::text, md5(jsonb_strip_nulls(to_jsonb(x))::text) FROM sokhach.trip_price_rev x
    UNION ALL SELECT customer_id, 'trip_fee_line', id::text, md5(jsonb_strip_nulls(to_jsonb(x))::text) FROM sokhach.trip_fee_line x
    UNION ALL SELECT customer_id, 'adjustment', id::text, md5(jsonb_strip_nulls(to_jsonb(x))::text) FROM sokhach.adjustment x
    UNION ALL SELECT customer_id, 'receipt', id::text, md5(jsonb_strip_nulls(to_jsonb(x))::text) FROM sokhach.receipt x
    UNION ALL SELECT customer_id, 'receipt_line', id::text, md5(jsonb_strip_nulls(to_jsonb(x))::text) FROM sokhach.receipt_line x
    UNION ALL SELECT source_customer_id, 'offset_pair', id::text, md5(jsonb_strip_nulls(to_jsonb(x))::text) FROM sokhach.offset_pair x
    UNION ALL SELECT customer_id, 'month_state', month::text, md5(jsonb_strip_nulls(to_jsonb(x))::text) FROM sokhach.month_state x
    UNION ALL SELECT customer_id, 'cutover_customer', cutover_id::text, md5(jsonb_strip_nulls(to_jsonb(x))::text) FROM sokhach.cutover_customer x
), p AS (
    SELECT customer_id, jsonb_object_agg(part, h) AS parts FROM (
        SELECT customer_id, part, md5(string_agg(h, '' ORDER BY k COLLATE "C")) AS h FROM r GROUP BY customer_id, part) s
    GROUP BY customer_id
)
SELECT coalesce(jsonb_object_agg(c.id::text, jsonb_build_object('version', c.version, 'parts', coalesce(p.parts, '{}'::jsonb))), '{}'::jsonb)
FROM sokhach.customer c LEFT JOIN p ON p.customer_id = c.id
$$;

CREATE OR REPLACE FUNCTION sokhach._safety_events(p_upto bigint, p_settle interval) RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = pg_catalog, sokhach, pg_temp SET timezone = 'UTC' SET datestyle = 'ISO, YMD' AS $$
-- LUOI-AN-TOAN-01 kiểm 4. Khối 1000 id của sokhach.event: [số dòng, md5 nối md5 từng dòng theo id]. `store`: mọi dòng id <= settled,
-- với settled là id lớn nhất trong các dòng cũ hơn p_settle (id cấp lúc chèn, dòng hiện lúc commit: giao dịch còn chạy có thể giữ id
-- nhỏ hơn dòng đã thấy). `check`: tính lại trên dòng id <= p_upto (mốc lượt trước) để so với khối đã giữ.
DECLARE v_settled bigint;
BEGIN
    SELECT max(id) INTO v_settled FROM sokhach.event WHERE at < statement_timestamp() - p_settle;
    RETURN (WITH e AS MATERIALIZED (
        SELECT id, id / 1000 AS b, md5(jsonb_strip_nulls(to_jsonb(x))::text) AS h FROM sokhach.event x
         WHERE id <= greatest(coalesce(v_settled, 0), coalesce(p_upto, 0)))
    SELECT jsonb_build_object('settled', v_settled,
        'store', (SELECT coalesce(jsonb_object_agg(b::text, jsonb_build_array(n, h)), '{}'::jsonb) FROM (
            SELECT b, count(*) AS n, md5(string_agg(h, '' ORDER BY id)) AS h FROM e WHERE id <= v_settled GROUP BY b) s),
        'check', CASE WHEN p_upto IS NOT NULL THEN (SELECT coalesce(jsonb_object_agg(b::text, jsonb_build_array(n, h)), '{}'::jsonb) FROM (
            SELECT b, count(*) AS n, md5(string_agg(h, '' ORDER BY id)) AS h FROM e WHERE id <= p_upto GROUP BY b) s) END));
END $$;

CREATE OR REPLACE FUNCTION sokhach.get_safety_net(p_options jsonb) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, sokhach, pg_temp AS $$
-- LUOI-AN-TOAN-01. Chỉ chạy trong giao dịch REPEATABLE READ READ ONLY (adapter read_only=True): mọi phần thấy cùng một lúc của sổ và
-- không ghi được gì. Trả mã sổ, mã lỗi, số đếm, phiên bản, dấu vân md5; không tên khách, không số tiền.
-- p_options: event_upto (mốc kiểm 4 lượt trước), ledger_slice/ledger_slices (phần sổ so get_ledger lượt này; 0 phần là bỏ qua),
-- settle_seconds (mặc định 600).
DECLARE v_id bigint; v_total numeric; v_alloc jsonb := '[]'::jsonb; v_dash jsonb; v_debt jsonb; v_codes text[]; v_bad bigint[];
    v_archived bigint[];
    v_slice int; v_slices int; v_settle int; v_upto bigint; v_ledger jsonb; v_checked int := 0; v_wrong bigint[] := '{}';
BEGIN
    PERFORM sokhach._actor();
    IF current_setting('transaction_read_only') <> 'on'
       OR current_setting('transaction_isolation') NOT IN ('repeatable read', 'serializable') THEN
        RAISE EXCEPTION 'SNAPSHOT_REQUIRED';
    END IF;
    IF jsonb_typeof(p_options) IS DISTINCT FROM 'object' THEN RAISE EXCEPTION 'INVALID_OPTIONS'; END IF;
    v_slices := coalesce((p_options->>'ledger_slices')::int, 0);
    v_slice := coalesce((p_options->>'ledger_slice')::int, 0);
    v_settle := coalesce((p_options->>'settle_seconds')::int, 600);
    v_upto := (p_options->>'event_upto')::bigint;
    IF v_slices < 0 OR v_slice < 0 OR (v_slices > 0 AND v_slice >= v_slices) OR v_settle NOT BETWEEN 0 AND 86400 OR v_upto < 0 THEN
        RAISE EXCEPTION 'INVALID_OPTIONS';
    END IF;
    -- Kiểm 1: ba luật của _check_allocations cho mọi sổ có phiếu (dòng chia chỉ có ở sổ có phiếu).
    FOR v_id IN SELECT DISTINCT customer_id FROM sokhach.receipt ORDER BY 1 LOOP
        BEGIN
            PERFORM sokhach._check_allocations(v_id);
        EXCEPTION WHEN raise_exception THEN
            v_alloc := v_alloc || jsonb_build_array(jsonb_build_object('customer_id', v_id, 'code', SQLERRM));
        END;
    END LOOP;
    -- Kiểm 2: con số Tổng quan hiển thị so với tổng các sổ có mốc nạp đang hiệu lực (v_outstanding_month).
    v_dash := sokhach.get_dashboard();
    v_debt := sokhach.get_dashboard_debt();
    WITH books AS (
        SELECT c.id, c.archived, coalesce(sum(v.outstanding_vnd), 0)::numeric AS total
          FROM sokhach.customer c
          JOIN sokhach.cutover_customer cc ON cc.customer_id = c.id AND cc.status = 'active'
          JOIN sokhach.cutover x ON x.id = cc.cutover_id AND x.status = 'active'
          LEFT JOIN sokhach.v_outstanding_month v ON v.customer_id = c.id
         GROUP BY c.id, c.archived),
      live AS (SELECT id, total FROM books WHERE NOT archived),
      pos AS (SELECT id, total FROM live WHERE total > 0),
      listed AS (SELECT (e->>'customer_id')::bigint AS id, (e->>'outstanding_vnd')::numeric AS total
          FROM jsonb_array_elements(v_debt->'customers') e),
      list_wrong AS (SELECT coalesce(pos.id, listed.id) AS id FROM pos FULL JOIN listed ON listed.id = pos.id
          WHERE pos.total IS DISTINCT FROM listed.total),
      sums AS (SELECT (SELECT coalesce(sum(total), 0) FROM pos) AS pos_sum, (SELECT count(*) FROM pos) AS pos_n,
          (SELECT coalesce(sum(total), 0) FROM live WHERE total < 0) AS neg_sum, (SELECT count(*) FROM live WHERE total < 0) AS neg_n)
    SELECT array_remove(ARRAY[
            CASE WHEN (v_dash->'receivable'->>'total_vnd')::numeric IS DISTINCT FROM s.pos_sum THEN 'RECEIVABLE_TOTAL' END,
            CASE WHEN (v_dash->'receivable'->>'customers')::bigint IS DISTINCT FROM s.pos_n THEN 'RECEIVABLE_COUNT' END,
            CASE WHEN (v_dash->'credit'->>'total_vnd')::numeric IS DISTINCT FROM s.neg_sum THEN 'CREDIT_TOTAL' END,
            CASE WHEN (v_dash->'credit'->>'customers')::bigint IS DISTINCT FROM s.neg_n THEN 'CREDIT_COUNT' END,
            CASE WHEN (SELECT coalesce(sum((e->>'receivable_vnd')::numeric), 0) FROM jsonb_array_elements(v_dash->'by_commodity') e)
                IS DISTINCT FROM s.pos_sum THEN 'COMMODITY_TOTAL' END,
            CASE WHEN (v_debt->>'receivable_vnd')::numeric IS DISTINCT FROM s.pos_sum THEN 'DEBT_TOTAL' END,
            CASE WHEN (SELECT coalesce(sum((e->>'receivable_vnd')::numeric), 0) FROM jsonb_array_elements(v_debt->'due_tiers') e)
                IS DISTINCT FROM s.pos_sum THEN 'DEBT_TIERS' END,
            CASE WHEN EXISTS (SELECT 1 FROM list_wrong) THEN 'DEBT_LIST' END,
            CASE WHEN EXISTS (SELECT 1 FROM books WHERE archived AND total <> 0) THEN 'ARCHIVED_BALANCE' END], NULL),
        ARRAY(SELECT id FROM list_wrong ORDER BY 1), ARRAY(SELECT id FROM books WHERE archived AND total <> 0 ORDER BY 1)
      INTO v_codes, v_bad, v_archived FROM sums s;
    -- Kiểm 2, phần get_ledger: mở cả sổ tốn ~0,1 giây mỗi sổ nên mỗi lượt chỉ so một phần (mã sổ mod ledger_slices).
    IF v_slices > 0 THEN
        FOR v_id, v_total IN
            SELECT c.id, coalesce(sum(v.outstanding_vnd), 0)::numeric
              FROM sokhach.customer c
              JOIN sokhach.cutover_customer cc ON cc.customer_id = c.id AND cc.status = 'active'
              JOIN sokhach.cutover x ON x.id = cc.cutover_id AND x.status = 'active'
              LEFT JOIN sokhach.v_outstanding_month v ON v.customer_id = c.id
             WHERE c.id % v_slices = v_slice
             GROUP BY c.id ORDER BY c.id
        LOOP
            v_checked := v_checked + 1;
            IF (sokhach.get_ledger(v_id)->>'total_outstanding_vnd')::numeric IS DISTINCT FROM v_total THEN
                v_wrong := v_wrong || v_id;
            END IF;
        END LOOP;
        v_ledger := jsonb_build_object('slice', v_slice, 'slices', v_slices, 'checked', v_checked, 'customers', to_jsonb(v_wrong));
    END IF;
    RETURN jsonb_build_object('books', (SELECT count(*) FROM sokhach.customer), 'allocations', v_alloc,
        'totals', jsonb_build_object('codes', to_jsonb(v_codes), 'customers', to_jsonb(v_bad), 'archived', to_jsonb(v_archived)),
        'ledger', v_ledger,
        'fingerprints', sokhach._safety_fingerprints(), 'events', sokhach._safety_events(v_upto, make_interval(secs => v_settle)));
END $$;

REVOKE ALL ON FUNCTION sokhach._safety_fingerprints() FROM PUBLIC, sokhach_app, sokhach_reader;
REVOKE ALL ON FUNCTION sokhach._safety_events(bigint, interval) FROM PUBLIC, sokhach_app, sokhach_reader;
REVOKE ALL ON FUNCTION sokhach.get_safety_net(jsonb) FROM PUBLIC, sokhach_app, sokhach_reader;
GRANT EXECUTE ON FUNCTION sokhach.get_safety_net(jsonb) TO sokhach_app;
COMMIT;
