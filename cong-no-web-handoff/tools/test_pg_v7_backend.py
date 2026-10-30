#!/usr/bin/env python3
"""V7 contract checks in one disposable PostgreSQL container with fake rows."""

# Cases live in test_pg_v7_backend_<group>.py; disposable PostgreSQL setup in pg_v7_harness.py.

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import time
import uuid
from pathlib import Path

from pg_v7_harness import (
    DATABASE,
    FUNCTIONS,
    IMAGE,
    LABEL_RUN,
    LABEL_TEST,
    LABEL_VALUE,
    LOCKED_TRIP_MIGRATION,
    MATRIX_MIGRATION,
    MH_MIGRATION,
    NHAP_MIGRATION,
    REVIEW_MIGRATION,
    ROOT,
    SCHEMA,
    SHEET_MIGRATION,
    SYNC_MIGRATION,
    HarnessError,
    Pg,
    PsqlSession,
    actor_sql,
    allocations,
    assert_allocations,
    call,
    case,
    import_book,
    inspect_owned,
    inspect_volume,
    lit,
    months,
    new_book,
    reject_call,
    require,
    run,
    seed,
    trip_json,
    version,
)
from test_pg_v7_backend_can_du import check_can_du
from test_pg_v7_backend_dashboard_debt import check_dashboard_debt
from test_pg_v7_backend_fee_commands import check_fee_catalog, check_fee_commands
from test_pg_v7_backend_locks import (
    check_csm_locks,
    check_csm_migration,
    check_locks,
)
from test_pg_v7_backend_offset import (
    check_ct_01,  # noqa: F401  (CHECKS.update looks it up in globals())
    check_ct_02,  # noqa: F401  (CHECKS.update looks it up in globals())
    check_ct_03,  # noqa: F401  (CHECKS.update looks it up in globals())
    check_ct_04,  # noqa: F401  (CHECKS.update looks it up in globals())
    check_ct_05,  # noqa: F401  (CHECKS.update looks it up in globals())
    check_ct_06,  # noqa: F401  (CHECKS.update looks it up in globals())
    check_ct_07,  # noqa: F401  (CHECKS.update looks it up in globals())
    check_ct_08,  # noqa: F401  (CHECKS.update looks it up in globals())
    check_ct_09,  # noqa: F401  (CHECKS.update looks it up in globals())
    check_ct_10,  # noqa: F401  (CHECKS.update looks it up in globals())
    check_ct_11,  # noqa: F401  (CHECKS.update looks it up in globals())
    check_ct_12,  # noqa: F401  (CHECKS.update looks it up in globals())
    check_ct_13,  # noqa: F401  (CHECKS.update looks it up in globals())
    check_ct_14,  # noqa: F401  (CHECKS.update looks it up in globals())
    check_ct_15,  # noqa: F401  (CHECKS.update looks it up in globals())
)
from test_pg_v7_backend_opening import (
    check_cutover_gate,
    check_dashboard,
    check_golden,
    check_import_behavior,
    check_model,
    check_model_edges,
    check_monthly_identity,
    check_opening_fifo,
    check_opening_import,
)
from test_pg_v7_backend_price import check_price_table
from test_pg_v7_backend_ps_fee import check_ps_fee
from test_pg_v7_backend_ra_ghi_tien import check_ra_ghi_tien
from test_pg_v7_backend_receipt_images import check_receipt_images
from test_pg_v7_backend_receipts import (
    check_atomic,
    check_concurrent,
    check_csm_reference,
    check_da_thu,
    check_delete_month_adjustment,
    check_future_receipt,
    check_idempotency,
    check_invariant_rejections,
    check_negative_receipt,
    check_pid_order,
    check_snapshots,
    check_void,
    check_void_get,
)
from test_pg_v7_backend_schema import (
    check_actor,
    check_events,
    check_evidence,
    check_fee,
    check_gate_view,
    check_immutable,
    check_import_guard,
    check_legacy,
    check_negative,
    check_numbers,
    check_roles,
)
from test_pg_v7_backend_sheet_fee import (
    check_fee_intent_after_price,
    check_ledger_fee,
    check_sheet_cross_customer,
)
from test_pg_v7_backend_trips import (
    check_adjustment_source,
    check_dedup,
    check_field_adjustment,
    check_input,
    check_nhap_sheet,
    check_shipper_write_sync,
    check_trip_review,
)

# Other V7 tools import these from here.
__all__ = ['DATABASE', 'FUNCTIONS', 'IMAGE', 'LABEL_RUN', 'LABEL_TEST', 'LABEL_VALUE', 'ROOT', 'SCHEMA', 'SHEET_MIGRATION', 'HarnessError', 'Pg', 'PsqlSession', 'actor_sql', 'allocations', 'assert_allocations', 'call', 'case', 'import_book', 'inspect_owned', 'inspect_volume', 'lit', 'months', 'new_book', 'reject_call', 'require', 'run', 'trip_json', 'version']


# IDs retain section 7 numbering; suffixes split schema checks from missing commands.
CASES = [
    case("DASH.01", "BEHAVIOR", "Dashboard returns stable empty contract", check="dashboard", functions=("get_dashboard",)),
    # Ngay sau DASH.01, trước case trips tạo sổ giả MAX_BIGINT làm get_dashboard tràn số khi cộng tổng.
    case("DASH.03", "BEHAVIOR", "Debt overview: due tiers, risk, last receipt/trip, month flow equals get_ledger",
         check="dashboard_debt", functions=("get_dashboard_debt",)),
    case("CSM.01", "BEHAVIOR", "Optional reference, edit, duplicate warning and idempotency", check="csm_reference", functions=("record_receipt", "edit_receipt_meta")),
    case("CSM.02", "BEHAVIOR", "Every month lock command has one atomic audit event", check="csm_locks", functions=("set_month_lock", "get_ledger")),
    case("CSM.03", "BEHAVIOR", "Atomic CSM migration preserves old rows and retries", check="csm_migration", functions=("record_receipt", "set_month_lock")),
    case("7.24", "BEHAVIOR", "M2-11 duplicate quarantine and money guards", check="dedup", functions=("paste_trips",)),
    case("7.25", "BEHAVIOR", "NEWTRIP-01 review: confirm/reject pending trip with reason", check="trip_review",
         functions=("review_trip", "get_ledger", "paste_trips")),
    case("7.01", "BEHAVIOR", "Import 11 opening months and historical PH-101", check="opening_import", functions=("get_ledger", "import_cutover")),
    case("7.02", "BEHAVIOR", "JS model operation parity and monthly tuples", check="model", functions=("paste_trips", "record_receipt", "reallocate")),
    case("7.02b", "BEHAVIOR", "Advance, price edit, paste after receipt, missing price, adjustment after void", check="model_edges", functions=("paste_trips", "edit_trip_price", "adjust_month", "void_receipt")),
    case("7.sheet", "BEHAVIOR", "Sheet cross-customer duplicate and NULL price", check="sheet_cross_customer", functions=("paste_trips", "list_sheet_trip_refs")),
    case("7.03", "BEHAVIOR", "Atomic failure after allocation write", check="atomic", functions=("record_receipt",)),
    case("7.03b", "BEHAVIOR", "Reject allocation, advance and event invariant corruption", check="invariant_rejections", functions=("record_receipt", "_check_allocations")),
    case("7.04", "BEHAVIOR", "Idempotency before stale version", check="idempotency", functions=("record_receipt",)),
    case("7.05", "BEHAVIOR", "Concurrent receipts and stale version", check="concurrent", functions=("record_receipt",)),
    case("7.05b", "BEHAVIOR", "Same-date mixed-case pid uses JS/C order", check="pid_order", functions=("reallocate",)),
    case("7.06", "SCHEMA", "Immutable money rows and role DML denial", check="immutable"),
    case("7.07", "BEHAVIOR", "Void every original line, snapshots, rollback", check="void", functions=("void_receipt",)),
    case("7.08", "BEHAVIOR", "VN month lock after customer lock", check="locks", functions=("set_month_lock", "edit_trip_price", "paste_trips")),
    case("7.09a", "SCHEMA", "App and reader DB role boundaries", check="roles"),
    case("7.09b", "BEHAVIOR", "Actor, hostile search_path, allowed EXECUTE", check="actor", functions=("get_ledger", "record_receipt")),
    case("7.09c", "BEHAVIOR", "Trial actor comes from session; no per-person ACL", check="actor", functions=("get_ledger",)),
    case("7.10a", "SCHEMA", "Bigint, NULL and integer constraints", check="numbers"),
    case("7.10b", "BEHAVIOR", "Reject -0 and oversized user input", check="input", functions=("paste_trips",)),
    case("7.11a", "SCHEMA", "Draft/one-sided active view gate, monthly buckets", check="gate_view"),
    case("7.11b", "BEHAVIOR", "FIFO monthly gate and nonzero opening anchor", check="cutover_gate", functions=("import_cutover", "verify_cutover_customer", "verify_cutover", "activate_cutover", "activate_cutover_customer")),
    case("7.11c", "SKIPPED_OPEN", "Complete source population evidence", open_reason="frozen source row and customer completeness cannot be proven by submitted aggregates and hashes"),
    case("7.12", "BEHAVIOR", "FIFO through opening and adjustment", check="opening_fifo", functions=("record_receipt", "adjust_month", "reallocate")),
    case("7.13", "SCHEMA", "Legacy rows excluded and immutable", check="legacy"),
    case("7.14a", "SCHEMA", "Import-once indexes and customer uniqueness", check="import_guard"),
    case("7.14b", "BEHAVIOR", "Retry import, totals, NO_BASELINE, concurrent import/verify", check="import_behavior", functions=("import_cutover", "verify_cutover_customer")),
    case("7.15a", "SCHEMA", "Negative opening remains signed in active view", check="negative"),
    case("7.15b", "BEHAVIOR", "Receipt lines skip negative bucket, months net its credit (CAN-DU-01); void preserves other receipts", check="negative_receipt", functions=("record_receipt", "void_receipt")),
    case("7.15c", "SKIPPED_OPEN", "Cross-ledger negative transfer and refund", open_reason="cross-ledger transfer and refund policy remain open"),
    case("7.16a", "SCHEMA", "Event snapshot and same-customer FK checks", check="events"),
    case("7.16b", "BEHAVIOR", "Reallocation snapshots and rollback of seven commands", check="snapshots", functions=("record_receipt", "edit_receipt_meta", "void_receipt", "adjust_trip", "adjust_month", "edit_trip_price", "paste_trips")),
    case("7.17", "SCHEMA", "Evidence freeze by trigger and concurrent direct DML", check="evidence"),
    case("7.18a", "SCHEMA", "NULL fee storage and three SQL view amount cases", check="fee"),
    case("7.18b", "BEHAVIOR", "get_ledger missing-price flag and JS tripAmount parity", check="ledger_fee", functions=("get_ledger",)),
    case("7.xx", "BEHAVIOR", "Golden anonymous V7 fixture", check="golden", functions=("get_ledger",)),
    case("7.19", "BEHAVIOR", "Monthly identity includes active signed opening and adjustments", check="monthly_identity", functions=("get_ledger",)),
    case("7.20", "BEHAVIOR", "Locked field edits use current price; NULL fee; legacy amount; retry", check="field_adjustment", functions=("adjust_trip",)),
    case("7.21", "BEHAVIOR", "VN receipt today accepted; tomorrow rejected without version change", check="future_receipt", functions=("record_receipt", "edit_receipt_meta")),
    case("7.22", "BEHAVIOR", "Void GET identifies only allocations current at void time", check="void_get", functions=("get_ledger", "void_receipt", "reallocate")),
    case("7.23", "BEHAVIOR", "Typed adjustment values survive audit tampering and latest price revision", check="adjustment_source", functions=("adjust_trip",)),
    case("7.26", "BEHAVIOR", "Shipper survives paste, review and edits in the ledger reader", check="shipper_write_sync", functions=("paste_trips", "edit_trip_info", "review_trip")),
    case("7.27", "BEHAVIOR", "Typed fee intent lands on the effective fee after a price revision", check="fee_intent_after_price", functions=("adjust_trip", "edit_trip_price")),
    case("PRB.01", "BEHAVIOR", "PR-B fee commands atomic batch, signs, locks, legacy delta and cache", check="fee_commands", functions=("add_trip_fees", "set_trip_fee_type", "replace_trip_fee", "void_trip_fee")),
    case("PRB.02", "BEHAVIOR", "PR-B catalog audit, columns, idempotency and grants", check="fee_catalog", functions=("add_fee_type", "rename_fee_type", "set_fee_type_kind", "set_fee_type_active", "set_book_fee_columns", "get_fee_types")),
    case("BANG-GIA.01", "BEHAVIOR", "Price table by effective date: lookup, save guards, batch apply, source, migration",
         check="price_table", functions=("save_price_table", "apply_price_table", "get_price_table", "get_price_status")),
    case("DA-THU.01", "BEHAVIOR", "Month totals like the Sheet: received by receipt date, cumulative not rewritten", check="da_thu",
         functions=("get_ledger", "record_receipt", "void_receipt")),
]


# CT-2SO acceptance map. Detailed Docker scenarios stay isolated from legacy fixture cases.
for _n, _title in [
    (1, "pair write preserves total and audit"), (2, "source credit overflow"),
    (3, "pair write rollback"), (4, "same source contention"),
    (5, "cross pair lock ordering"), (6, "pair idempotency"),
    (7, "void from either side"), (8, "date edit both sides"),
    (9, "paired method immutable"), (10, "outside ledger remains single receipt"),
    (11, "source list filters and A-Z order"), (12, "Vietnam future date"),
    (13, "legacy CẤN TRỪ remains unlinked"), (14, "per-book PH sequence"),
    (15, "target overpayment becomes advance"),
]:
    CASES.append(case(f"CT-2SO.{_n:02d}", "BEHAVIOR", _title, check=f"ct_{_n:02d}",
                      functions=("record_offset", "void_offset", "edit_offset_date",
                                 "list_offset_sources")))


CASES.append(case("CHUNG-TU.01", "BEHAVIOR", "Receipt images: attach, warn, remove with reason, void keeps, money unchanged",
                  check="receipt_images", functions=("attach_receipt_image", "remove_receipt_image", "list_receipt_images",
                                                     "get_receipt_image", "find_receipt_image")))
CASES.append(case("NHAP-SHEET.01", "BEHAVIOR", "Append-only edits, deletion, exact legacy examples, moved debt and FIFO",
                  check="nhap_sheet", functions=("edit_trip_info", "delete_trip", "edit_legacy_trip", "delete_legacy_trip")))
# Chạy sau CHUNG-TU.01: case đó chạy lại migration chứng từ, ràng buộc event cũ không nhận event adjust_month_delete đã ghi.
CASES.append(case("XOA-DC-THANG.01", "BEHAVIOR", "Delete month adjustment: reversal pair hidden, FIFO restored, audit, locked month",
                  check="delete_month_adjustment", functions=("delete_month_adjustment", "adjust_month", "get_ledger")))
# Chạy cuối: migration PS là bản mới nhất dựng lại ràng buộc event, gồm cả adjust_month_delete lẫn rewrite_trip_fees.
CASES.append(case("PS-FEE.01", "BEHAVIOR", "PS fee split keeps totals, legacy TOTAL, no reallocation; stale lines and locks rejected",
                  check="ps_fee", functions=("rewrite_trip_fees",)))
# Rà đường ghi tiền 29/10/2026: chạy cuối, migration của nó là bản mới nhất của paste_trips/record_receipt/apply_price_table.
CASES.append(case("RA-GHI-TIEN.01", "BEHAVIOR", "Audit 29/10: future paste date, receipt FIFO by date, typed price kept, Sheet functions canonical",
                  check="ra_ghi_tien", functions=("paste_trips", "record_receipt", "apply_price_table",
                                                  "list_sheet_trip_refs", "resolve_sheet_conflict")))
# CAN-DU-01 30/10/2026: chạy sau RA-GHI-TIEN.01, migration của nó là bản mới nhất của record_receipt.
CASES.append(case("CAN-DU.01", "BEHAVIOR", "Credit of negative months applied to oldest debt; totals and receipt lines unchanged",
                  check="can_du", functions=("record_receipt", "get_receivables_detail")))

CHECKS = {"can_du": check_can_du, "dashboard": check_dashboard, "dashboard_debt": check_dashboard_debt, "ps_fee": check_ps_fee, "ra_ghi_tien": check_ra_ghi_tien, "receipt_images": check_receipt_images, "price_table": check_price_table, "nhap_sheet": check_nhap_sheet, "csm_reference": check_csm_reference, "csm_locks": check_csm_locks, "csm_migration": check_csm_migration,
          "fee_commands": check_fee_commands, "fee_catalog": check_fee_catalog,
          "dedup": check_dedup, "trip_review": check_trip_review, "monthly_identity": check_monthly_identity, "da_thu": check_da_thu, "delete_month_adjustment": check_delete_month_adjustment, "field_adjustment": check_field_adjustment,
          "adjustment_source": check_adjustment_source, "shipper_write_sync": check_shipper_write_sync,
          "fee_intent_after_price": check_fee_intent_after_price,
          "future_receipt": check_future_receipt, "void_get": check_void_get,
          "immutable": check_immutable, "roles": check_roles, "numbers": check_numbers,
          "gate_view": check_gate_view, "legacy": check_legacy, "import_guard": check_import_guard,
          "negative": check_negative, "events": check_events, "evidence": check_evidence,
           "fee": check_fee, "model": check_model, "model_edges": check_model_edges,
           "sheet_cross_customer": check_sheet_cross_customer,
           "atomic": check_atomic,
           "invariant_rejections": check_invariant_rejections,
           "idempotency": check_idempotency, "concurrent": check_concurrent,
           "pid_order": check_pid_order,
          "void": check_void, "locks": check_locks, "actor": check_actor,
          "input": check_input, "opening_fifo": check_opening_fifo,
          "negative_receipt": check_negative_receipt, "snapshots": check_snapshots,
          "ledger_fee": check_ledger_fee, "golden": check_golden,
          "opening_import": check_opening_import, "cutover_gate": check_cutover_gate,
          "import_behavior": check_import_behavior}


CHECKS.update({f"ct_{n:02d}": globals()[f"check_ct_{n:02d}"] for n in range(1, 16)})


def check_migration(pg: Pg) -> None:
    from v7_load_baseline_refs import apply
    from v7_load_real_copy import LoadError
    old_ref = "460882d9d5d60c3fc8eeac5161a0058219dc09d4"
    # Dedicated database; shared roles already exist in this disposable cluster.
    old_schema = run(["git", "show", old_ref + ":specs/v7-backend/schema-draft.sql"], cwd=ROOT).stdout
    old_functions = run(["git", "show", old_ref + ":cong-no-web-handoff/tools/v7_backend_functions.sql"], cwd=ROOT).stdout
    old_schema = re.sub(r"^CREATE ROLE .*;\n", "", old_schema, flags=re.M)
    db = "webdebit_v7_migration_test"
    pg.sql(f"CREATE DATABASE {db}", database="postgres")
    class CopyPg(Pg):
        def sql(self, sql, **kwargs):
            return super().sql(sql, **{**kwargs, "database": db})
    copy = CopyPg(pg.name, pg.run_id)
    copy.sql(old_schema)
    copy.sql(old_functions)
    # Real old fixture, with 236 fake customer identities; no financial source data.
    seed(copy, references=False)
    copy.sql("INSERT INTO sokhach.customer(name) SELECT 'FAKE '||g FROM generate_series(2,236) g")
    copy.sql("UPDATE sokhach.cutover_customer SET status='verified' WHERE customer_id=1; "
             "UPDATE sokhach.cutover SET status='verified' WHERE id=1; "
             "UPDATE sokhach.cutover SET status='active' WHERE id=1; "
             "UPDATE sokhach.cutover_customer SET status='active' WHERE customer_id=1")
    snapshot = copy.value("SELECT jsonb_agg(row_to_json(s)) FROM (SELECT c.id,v.debt_month,v.outstanding_vnd "
                          "FROM sokhach.customer c LEFT JOIN sokhach.v_outstanding_month v ON v.customer_id=c.id ORDER BY c.id,v.debt_month) s")
    migration = (ROOT / "specs/v7-backend/migrations/001-m2-11-dedup.sql").read_text(encoding="utf-8")
    copy.rejects(migration.replace("COMMIT;", "DO $$ BEGIN RAISE EXCEPTION 'FAKE_MIGRATION_FAULT'; END $$; COMMIT;"),
                 message="FAKE_MIGRATION_FAULT")
    copy.true("NOT EXISTS (SELECT FROM information_schema.columns WHERE table_schema='sokhach' AND table_name='trip' AND column_name='status')",
              "failed migration did not roll back")
    copy.sql(migration)
    copy.sql(migration)  # idempotent
    copy.sql((ROOT / "cong-no-web-handoff/tools/migrations/2026-10-21-v7-csm.sql").read_text(encoding="utf-8"))
    review = REVIEW_MIGRATION.read_text(encoding="utf-8")
    copy.rejects(review.replace("COMMIT;", "DO $$ BEGIN RAISE EXCEPTION 'REVIEW_MIGRATION_FAULT'; END $$; COMMIT;"),
                 message="REVIEW_MIGRATION_FAULT")
    copy.true("NOT EXISTS (SELECT FROM information_schema.columns WHERE table_schema='sokhach' "
              "AND table_name='trip' AND column_name='reviewed_by_event')", "failed review migration did not roll back")
    copy.sql(review)
    nhap = NHAP_MIGRATION.read_text(encoding="utf-8")
    copy.rejects(nhap.replace("COMMIT;", "DO $$ BEGIN RAISE EXCEPTION 'NHAP_FAULT'; END $$; COMMIT;"), message="NHAP_FAULT")
    copy.true("to_regclass('sokhach.trip_info_rev') IS NULL", "failed NHAP migration left revision table")
    drift = """WITH e AS (INSERT INTO sokhach.event(customer_id,kind,actor,"before","after")
        VALUES(1,'adjust_month','fake','{"month":"2026-01-01"}','{"adjustment":1}') RETURNING id)
        INSERT INTO sokhach.adjustment(customer_id,debt_month,amount_vnd,actor,created_by_event)
        SELECT 1,'2026-01-01',1,'fake',id FROM e;
"""
    balance_check = "DO $$ BEGIN\n IF EXISTS(SELECT 1 FROM nhap_sheet_before"
    require(balance_check in nhap, "migration balance checker marker missing")
    copy.rejects(nhap.replace(balance_check, drift+balance_check), message="NHAP_SHEET_BALANCE_CHANGED")
    copy.true("to_regclass('sokhach.trip_info_rev') IS NULL", "balance mismatch did not rollback schema")
    copy.sql(nhap)
    copy.sql(nhap)
    mh = MH_MIGRATION.read_text(encoding="utf-8")
    copy.rejects(mh.replace("COMMIT;", "DO $$ BEGIN RAISE EXCEPTION 'MH_FAULT'; END $$; COMMIT;"), message="MH_FAULT")
    copy.true("position('commodity' in pg_get_functiondef('sokhach.list_customers()'::regprocedure))=0",
              "failed MH migration left new list_customers")
    copy.sql(mh)
    copy.sql(mh)
    dashboard = (ROOT / "cong-no-web-handoff/tools/migrations/2026-10-24-v7-dashboard.sql").read_text(encoding="utf-8")
    copy.rejects(dashboard.replace("COMMIT;", "DO $$ BEGIN RAISE EXCEPTION 'DASHBOARD_FAULT'; END $$; COMMIT;"),
                 message="DASHBOARD_FAULT")
    copy.sql(dashboard)
    copy.sql(dashboard)
    copy.sql(LOCKED_TRIP_MIGRATION.read_text(encoding="utf-8"))
    copy.sql(LOCKED_TRIP_MIGRATION.read_text(encoding="utf-8"))
    sheet = SHEET_MIGRATION.read_text(encoding="utf-8")
    copy.sql(sheet)
    copy.sql(sheet)
    matrix = MATRIX_MIGRATION.read_text(encoding="utf-8")
    copy.sql(matrix)
    copy.sql(matrix)
    require(copy.value("SELECT jsonb_agg(row_to_json(s)) FROM (SELECT c.id,v.debt_month,v.outstanding_vnd "
                       "FROM sokhach.customer c LEFT JOIN sokhach.v_outstanding_month v ON v.customer_id=c.id ORDER BY c.id,v.debt_month) s") == snapshot,
            "migration changed fake 236-customer balances")
    catalog = "SELECT jsonb_object_agg(proname,pg_get_functiondef(oid)) FROM pg_proc WHERE pronamespace='sokhach'::regnamespace"
    require(copy.value(catalog) == pg.value(catalog), "migration function definitions differ from fresh schema")
    cols = "SELECT jsonb_agg(row_to_json(s)) FROM (SELECT table_name,column_name,data_type,is_nullable,column_default "
    cols += "FROM information_schema.columns WHERE table_schema='sokhach' ORDER BY table_name,column_name) s"
    require(copy.value(cols) == pg.value(cols), "migration columns differ")
    views = "SELECT jsonb_object_agg(viewname,definition) FROM pg_views WHERE schemaname='sokhach'"
    require(copy.value(views) == pg.value(views), "migration views differ")
    copy.sql("CREATE ROLE v7_loader LOGIN IN ROLE sokhach_owner; "
             f"REVOKE CONNECT ON DATABASE {db} FROM PUBLIC; GRANT CONNECT ON DATABASE {db} TO v7_loader,v7_app")
    checker = (ROOT / "cong-no-web-handoff/tools/v7_post_deploy_check.sql").read_text(encoding="utf-8")
    copy.sql(f"\\set db_v7 {db}\n\\set loader_role v7_loader\n\\set expect_customers 236\n" + checker)
    # Loader conflict/retry and balance checks use isolated reference-only cutover.
    copy.sql("ALTER TABLE sokhach.baseline_trip_ref DISABLE TRIGGER baseline_trip_ref_immutable; "
             "DELETE FROM sokhach.baseline_trip_ref; "
             "ALTER TABLE sokhach.baseline_trip_ref ENABLE TRIGGER baseline_trip_ref_immutable; "
             "SELECT 1")
    from v7_load_direct import DirectPg
    refs = [("ALT:FAKE:20260101", "FAKE", "2026-01-01")]
    direct = DirectPg("/var/run/postgresql", db, "v7_loader", psql_command=pg.psql_command())
    try:
        require(apply(direct, refs, "a" * 64, 1) == "LOADED", "loader failed")
        # Temp table is per-call; drop before exercising idempotent retry in same transaction.
        direct.sql("DROP TABLE incoming_refs")
        require(apply(direct, refs, "a" * 64, 1) == "UNCHANGED", "loader retry duplicated")
        direct.close(commit=True)
    except Exception:
        direct.close()
        raise
    rejected = DirectPg("/var/run/postgresql", db, "v7_loader", psql_command=pg.psql_command())
    try:
        try:
            apply(rejected, refs, "b" * 64, 1)
        except LoadError:
            pass
        else:
            raise HarnessError("wrong manifest accepted")
    finally:
        rejected.close()
    require(copy.value("SELECT count(*) FROM sokhach.baseline_trip_ref") == "1", "loader failure changed references")
    # A legacy trip without container gets no reference: counted via skipped, never silently dropped.
    copy.sql("ALTER TABLE sokhach.legacy_row DISABLE TRIGGER legacy_row_insert_guard; "
             "INSERT INTO sokhach.legacy_row(customer_id,cutover_id,debt_month,kind,display,source_tab,source_row,created_by_event) "
             "VALUES (1,1,'2026-01-01','trip','{\"fake\":true,\"container\":\"\",\"date\":null}','FAKE',9,1); "
             "ALTER TABLE sokhach.legacy_row ENABLE TRIGGER legacy_row_insert_guard")
    for skipped, expect in ((0, None), (1, "UNCHANGED")):
        nocontainer = DirectPg("/var/run/postgresql", db, "v7_loader", psql_command=pg.psql_command())
        try:
            try:
                got = apply(nocontainer, refs, "a" * 64, 1, skipped)
            except LoadError:
                got = None
        finally:
            nocontainer.close()
        require(got == expect, f"no-container legacy trip handling wrong for skipped={skipped}")
    require(copy.value("SELECT count(*) FROM sokhach.baseline_trip_ref") == "1", "no-container trip got a reference")
    check_dedup(copy)
    # Reproduce deployment order: the locked-trip migration replaced the earlier shipper reader.
    shipper = (ROOT / "cong-no-web-handoff/tools/migrations/2026-10-24-v7-shipper.sql").read_text(encoding="utf-8")
    ledger_shipper = (ROOT / "cong-no-web-handoff/tools/migrations/2026-10-26-v7-ledger-shipper-read.sql").read_text(encoding="utf-8")
    reader = "pg_get_functiondef('sokhach.get_ledger(bigint)'::regprocedure)"
    balances = "SELECT jsonb_agg(row_to_json(s)) FROM (SELECT c.id,v.debt_month,v.outstanding_vnd "
    balances += "FROM sokhach.customer c LEFT JOIN sokhach.v_outstanding_month v ON v.customer_id=c.id ORDER BY c.id,v.debt_month) s"
    before_repair = copy.value(balances)
    copy.sql(shipper)
    copy.sql(LOCKED_TRIP_MIGRATION.read_text(encoding="utf-8"))
    copy.true(f"position('shipper' in {reader})=0", "locked-trip migration did not reproduce missing shipper")
    copy.sql(ledger_shipper)
    copy.sql(ledger_shipper)  # read-only function repair is idempotent
    copy.true(f"position('shipper' in {reader})>0", "ledger reader still omits shipper")
    copy.sql(SYNC_MIGRATION.read_text(encoding="utf-8"))
    copy.true(f"position('shipper' in {reader})>0", "write sync migration lost shipper reader")
    require(copy.value(balances) == before_repair,
            "shipper reader repair changed fake balances")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--list", action="store_true", help="list cases without Docker")
    ap.add_argument("--report", type=Path, help="write JSON report")
    ap.add_argument("--migration-test", action="store_true")
    ap.add_argument("--m2-11-only", action="store_true", help="focused development checks")
    ap.add_argument("--fee-migration-only", action="store_true", help="focused PR-A migration checks")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--expect-red", action="store_true", default=True,
                      help="default: missing command functions may fail")
    mode.add_argument("--strict", action="store_true", help="require every case to pass")
    args = ap.parse_args()
    selected = [c for c in CASES if (not args.m2_11_only or c["id"] == "7.24")
                and (not args.fee_migration_only or c["id"] == "CSM.03")]
    if args.list:
        for c in CASES:
            print(f"{c['id']}\t{c['label']}\t{c['title']}")
        return 0
    run_id = uuid.uuid4().hex
    name = f"webdebit-v7-test-{run_id}"
    volume = name
    report = {"run_id": run_id, "image": IMAGE, "schema": str(SCHEMA),
              "schema_sha256": hashlib.sha256(SCHEMA.read_bytes().replace(b"\r\n", b"\n")).hexdigest(),
              "functions": str(FUNCTIONS),
              "functions_sha256": hashlib.sha256(FUNCTIONS.read_bytes().replace(b"\r\n", b"\n")).hexdigest(),
              "sql_hash_normalization": "CRLF to LF",
              "cases": [], "cleanup": "not_started"}
    volume_created = False
    container_id = None
    fatal = None
    try:
        require(shutil.which("docker") is not None, "Docker CLI unavailable")
        run(["docker", "volume", "create", "--label", f"{LABEL_TEST}={LABEL_VALUE}",
             "--label", f"{LABEL_RUN}={run_id}", volume])
        volume_created = True
        inspect_volume(volume, run_id)
        run(["docker", "run", "--detach", "--name", name, "--label", f"{LABEL_TEST}={LABEL_VALUE}",
             "--label", f"{LABEL_RUN}={run_id}", "--network", "none", "--volume",
             f"{volume}:/var/lib/postgresql", "--env", "POSTGRES_HOST_AUTH_METHOD=trust", IMAGE], timeout=240)
        container_id = inspect_owned(name, volume, run_id)
        require(container_id is not None, "container absent after Docker run")
        report["container_id"] = container_id
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            logs = run(["docker", "logs", name], check=False, timeout=10)
            if "PostgreSQL init process complete; ready for start up." in logs.stdout + logs.stderr:
                break
            time.sleep(0.25)  # readiness polling only; never contention evidence
        else:
            raise HarnessError("PostgreSQL init marker timed out")
        # The init marker precedes the final restart; wait until the server accepts connections.
        while time.monotonic() < deadline:
            if run(["docker", "exec", name, "pg_isready", "-U", "postgres"], check=False, timeout=10).returncode == 0:
                break
            time.sleep(0.25)  # readiness polling only; never contention evidence
        else:
            raise HarnessError("PostgreSQL readiness timed out")
        pg = Pg(name, run_id)
        require(pg.sql("SELECT current_database()", database="postgres").stdout.strip() == "postgres",
                "unexpected initial database")
        inspect_owned(name, volume, run_id, container_id)
        inspect_volume(volume, run_id)
        pg.sql(f"CREATE DATABASE {DATABASE}", database="postgres")
        marker = f"codex_v7_run_id={run_id}"
        pg.sql(f"COMMENT ON DATABASE {DATABASE} IS '{marker}'")
        require(pg.value("SELECT shobj_description(oid,'pg_database') FROM pg_database WHERE datname=current_database()") == marker,
                "database marker mismatch")
        inspect_owned(name, volume, run_id, container_id)
        inspect_volume(volume, run_id)
        run(["docker", "exec", "-i", *pg.env, name, "psql", "-X", "-v", "ON_ERROR_STOP=1",
             "-U", "postgres", "-d", DATABASE], input_text=SCHEMA.read_text(encoding="utf-8"))
        run(["docker", "exec", "-i", *pg.env, name, "psql", "-X", "-v", "ON_ERROR_STOP=1",
             "-U", "postgres", "-d", DATABASE], input_text=FUNCTIONS.read_text(encoding="utf-8"))
        pg.sql(SHEET_MIGRATION.read_text(encoding="utf-8"))
        report["postgres_version"] = pg.value("SHOW server_version")
        pg.sql("CREATE ROLE v7_app LOGIN IN ROLE sokhach_app; CREATE ROLE v7_reader LOGIN IN ROLE sokhach_reader")
        if args.migration_test:
            check_migration(pg)
            report["migration"] = "pass"
        seed(pg)
        # Existing schema checks share customer 1; run before isolated behavioral books.
        ordered = sorted(selected, key=lambda c: 0 if c["label"] == "SCHEMA" else 1)
        for c in ordered:
            row = {"id": c["id"], "label": c["label"], "result": "fail", "reason": ""}
            try:
                if c["label"] == "SKIPPED_OPEN":
                    row.update(result="skipped", reason=c["open_reason"])
                elif c["label"] in ("NEEDS_FUNCTION", "BEHAVIOR"):
                    missing = [f for f in c["functions"] if pg.value(
                        f"SELECT count(*) FROM pg_proc WHERE pronamespace='sokhach'::regnamespace AND proname='{f}'") == "0"]
                    if missing:
                        row["reason"] = "function does not exist: " + ", ".join(missing)
                    else:
                        require(c["check"] in CHECKS, "function present but no behavioral assertion")
                        row["executed"] = True
                        evidence = CHECKS[c["check"]](pg)
                        row.update(result="pass", reason=evidence or "PostgreSQL behavioral assertion passed")
                else:
                    evidence = CHECKS[c["check"]](pg)
                    row.update(result="pass", reason=evidence or "PostgreSQL schema assertion passed")
            except (HarnessError, OSError, ValueError, KeyError, TypeError, AssertionError,
                    subprocess.TimeoutExpired) as exc:
                row["reason"] = str(exc)
            report["cases"].append(row)
        position = {c["id"]: i for i, c in enumerate(CASES)}
        report["cases"].sort(key=lambda row: position[row["id"]])
    except (HarnessError, OSError, ValueError) as exc:
        fatal = str(exc)
        report["error"] = fatal
    finally:
        try:
            owned = inspect_owned(name, volume, run_id, container_id) if volume_created else None
            if owned:
                run(["docker", "rm", "--force", owned])
            if volume_created:
                inspect_volume(volume, run_id)
                run(["docker", "volume", "rm", volume])
            report["cleanup"] = "verified_and_removed" if volume_created else "nothing_created"
        except (HarnessError, OSError, ValueError) as exc:
            report["cleanup"] = "failed: " + str(exc)
            fatal = str(exc)
        if len(report["cases"]) < len(selected):
            done = {c["id"] for c in report["cases"]}
            for c in selected:
                if c["id"] not in done:
                    report["cases"].append({
                        "id": c["id"], "label": c["label"],
                        "result": "skipped" if c["label"] == "SKIPPED_OPEN" else "fail",
                        "reason": c["open_reason"] if c["label"] == "SKIPPED_OPEN"
                        else "harness did not reach case: " + (fatal or "unknown setup failure")})
        counts = {label: {result: sum(c["label"] == label and c["result"] == result for c in report["cases"])
                          for result in ("pass", "fail", "skipped")}
                  for label in ("SCHEMA", "BEHAVIOR", "NEEDS_FUNCTION", "SKIPPED_OPEN")}
        report["summary"] = counts
        report["exit_code"] = int(bool(fatal) or len(report["cases"]) != len(selected)
                                  or any(c["result"] != "pass" for c in report["cases"]
                                         if args.strict or c["label"] in ("SCHEMA", "BEHAVIOR")
                                         or c.get("executed")))
        if args.report:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return report["exit_code"]


if __name__ == "__main__":
    sys.exit(main())
