"""BANG-GIA-01 behavior; run only through disposable test_pg_v7_backend.py harness."""
import json
import re

from pg_v7_harness import (
    ROOT,
    call,
    fixture_open_month,
    new_book,
    reject_call,
    require,
    run,
    version,
)

PRICE_MIGRATION = ROOT / "cong-no-web-handoff/tools/migrations/2026-10-29-v7-bang-gia.sql"
# main right before BANG-GIA-01; CI checks out full history (fetch-depth: 0).
PRE_PRICE_REF = "58c43dd89178bed75434978f031152ffacc64d61"


def _table(p1_tt_daklak="95", p2_khach_daklak="75"):
    return {
        "tt_shippers": ["FAKE  TT  SHIP"],
        "locations": [{"name": "DAK LAK", "aliases": ["DAKLAK"]}, {"name": "LAM DONG", "aliases": []},
                      {"name": "VINH LONG"}],
        "periods": [
            {"valid_from": "2026-01-02", "valid_to": "2026-01-09", "rates": [
                {"location": "DAK LAK", "tier": "khach", "unit_price_vnd": "75"},
                {"location": "DAK LAK", "tier": "tt", "unit_price_vnd": p1_tt_daklak},
                {"location": "LAM DONG", "tier": "khach", "unit_price_vnd": "70"},
                {"location": "LAM DONG", "tier": "tt", "unit_price_vnd": "90"}]},
            {"valid_from": "2026-01-10", "valid_to": None, "rates": [
                {"location": "dak lak", "tier": "khach", "unit_price_vnd": p2_khach_daklak},
                {"location": "DAK LAK", "tier": "tt", "unit_price_vnd": "85"},
                {"location": "LAM DONG", "tier": "khach", "unit_price_vnd": "70"},
                {"location": "LAM DONG", "tier": "tt", "unit_price_vnd": "80"},
                {"location": "VINH LONG", "tier": "tt", "unit_price_vnd": "75"}]},
        ],
    }


def _row(container, day, origin, shipper, price=None):
    return {"container": container, "booking": container, "carrier": "FAKE", "date": f"{day:02d}/01/2026",
            "from": origin, "to": "FAKE-B", "unitPriceVnd": price, "otherFeeVnd": None, "note": "",
            "src": "FAKE", "shipper": shipper}


def check_price_table(pg):
    c = new_book(pg, ("2026-01-01", 100))
    fixture_open_month(pg, c, "2026-01-01")
    rows = [_row("PRICE-A", 9, "DAK LAK", "fake tt ship"),     # tt, last day of period 1
            _row("PRICE-B", 10, "DAKLAK", "FAKE TT SHIP"),     # alias, first day of period 2
            _row("PRICE-C", 10, "DAK LAK", "OTHER"),           # not TT -> customer price
            _row("PRICE-D", 10, "DAK LAK", None),              # blank shipper -> customer price
            _row("PRICE-E", 10, "VINH LONG", "OTHER"),         # only TT price exists
            _row("PRICE-F", 10, "CAN THO", "OTHER"),           # location missing
            _row("PRICE-G", 5, "DAK LAK", "OTHER", "100"),     # typed price differs from table
            _row("PRICE-I", 1, "LAM DONG", "OTHER")]           # before first period
    ids = dict(zip("ABCDEFGI", call(pg, "paste_trips", c, version(pg, c), "price-paste", "2026-01-01",
                                     json.dumps(rows))["trip_ids"], strict=True))
    status = call(pg, "get_price_status", c)
    require(not status["has_table"] and status["ready_count"] == 0
            and all(t["lookup"] == {"reason": "NO_TABLE"} for t in status["trips"]), "status before table")

    bad_cases = [
        ("overlap", {**_table(), "periods": _table()["periods"] + [
            {"valid_from": "2026-01-09", "valid_to": "2026-01-10",
             "rates": [{"location": "LAM DONG", "tier": "tt", "unit_price_vnd": "1"}]}]}, "PRICE_PERIOD_OVERLAP"),
        ("reverse", {**_table(), "periods": [{"valid_from": "2026-01-05", "valid_to": "2026-01-04", "rates": []}]},
         "PRICE_INVALID_PERIOD"),
        ("calendar", {**_table(), "periods": [{"valid_from": "2026-02-30", "valid_to": None, "rates": []}]},
         "PRICE_INVALID_PERIOD"),
        ("unknown", {**_table(), "periods": [{"valid_from": "2026-01-01", "valid_to": None,
                     "rates": [{"location": "CAN THO", "tier": "khach", "unit_price_vnd": "1"}]}]}, "PRICE_UNKNOWN_LOCATION"),
        ("alias", {**_table(), "locations": [{"name": "DAK LAK"}, {"name": "LAM DONG", "aliases": ["dak  lak"]}]},
         "PRICE_DUPLICATE_ALIAS"),
        ("shipper", {**_table(), "tt_shippers": ["FAKE TT SHIP", "fake tt ship"]}, "PRICE_DUPLICATE_SHIPPER"),
        ("rate", {**_table(), "periods": [{"valid_from": "2026-01-01", "valid_to": None, "rates": [
            {"location": "DAK LAK", "tier": "tt", "unit_price_vnd": "1"},
            {"location": "DAKLAK", "tier": "tt", "unit_price_vnd": "2"}]}]}, "PRICE_UNKNOWN_LOCATION"),
        ("rate-twice", {**_table(), "periods": [{"valid_from": "2026-01-01", "valid_to": None, "rates": [
            {"location": "DAK LAK", "tier": "tt", "unit_price_vnd": "1"},
            {"location": "dak lak", "tier": "tt", "unit_price_vnd": "2"}]}]}, "PRICE_DUPLICATE_RATE"),
        ("tier", {**_table(), "periods": [{"valid_from": "2026-01-01", "valid_to": None, "rates": [
            {"location": "DAK LAK", "tier": "vip", "unit_price_vnd": "1"}]}]}, "INVALID_PRICE_TABLE"),
        ("extra", {**_table(), "note": "x"}, "INVALID_PRICE_TABLE"),
    ]
    for amount in ("-1", "1.5", "01", "9223372036854775808", 5):
        bad_cases.append((f"amount-{amount}", {**_table(), "periods": [{"valid_from": "2026-01-01", "valid_to": None,
                          "rates": [{"location": "DAK LAK", "tier": "khach", "unit_price_vnd": amount}]}]},
                          "PRICE_INVALID_AMOUNT"))
    for key, table, error in bad_cases:
        reject_call(pg, "save_price_table", c, version(pg, c), "price-bad-" + key, json.dumps(table), error=error)
    require(call(pg, "get_price_table", c)["price_table"] == {"tt_shippers": [], "locations": [], "periods": []},
            "rejected save left rows")
    reject_call(pg, "save_price_table", c, version(pg, c) - 1, "price-stale", json.dumps(_table()), error="STALE_LEDGER")

    v = version(pg, c)
    saved = call(pg, "save_price_table", c, v, "price-save", json.dumps(_table()))
    require(call(pg, "save_price_table", c, v, "price-save", json.dumps(_table())) == saved, "save retry changed")
    reject_call(pg, "save_price_table", c, v, "price-save", json.dumps(_table("96")), error="IDEMPOTENCY_CONFLICT")
    require(saved["affected_trips"] == 0 and saved["version"] == v + 1, "first save result")
    reject_call(pg, "save_price_table", c, version(pg, c), "price-same", json.dumps(_table()), error="NO_CHANGE")
    table = call(pg, "get_price_table", c)
    require(table["price_table"]["tt_shippers"] == ["FAKE  TT  SHIP"]
            and table["price_table"]["locations"][0] == {"name": "DAK LAK", "aliases": ["DAKLAK"]}
            and table["price_table"]["periods"][1]["valid_to"] is None, "stored table differs")
    shippers = {s["name"]: s["tier"] for s in table["book_shippers"]}
    require(shippers.get("OTHER") == "khach" and "tt" in shippers.values(), f"book shippers wrong: {shippers}")

    status = {t["trip_id"]: t for t in call(pg, "get_price_status", c)["trips"]}
    def price(letter):
        return status[ids[letter]]["lookup"].get("unit_price_vnd")
    def reason(letter):
        return status[ids[letter]]["lookup"].get("reason")
    require((price("A"), price("B"), price("C"), price("D"), price("G")) == ("95", "85", "75", "75", "75"),
            f"lookup prices wrong: {[status[ids[k]]['lookup'] for k in 'ABCDG']}")
    require(status[ids["A"]]["lookup"]["tier"] == "tt" and status[ids["C"]]["lookup"]["tier"] == "khach",
            "tier wrong")
    require((reason("E"), reason("F"), reason("I")) == ("NO_RATE", "UNKNOWN_LOCATION", "NO_PERIOD"),
            "lookup reasons wrong")
    require({k for k in ids if status[ids[k]]["ready"]} == set("ABCD"), "ready set wrong")
    require(status[ids["G"]]["differs"] and not status[ids["G"]]["from_table"], "typed price differs flag")
    summary = call(pg, "get_price_status", c)
    require(summary["ready_count"] == 4 and summary["ready_total_vnd"] == "330"
            and summary["ready_months"] == ["2026-01-01"], f"ready summary wrong: {summary['ready_total_vnd']}")

    other = int(pg.value("SELECT id FROM sokhach.fee_type WHERE system_key='other'"))
    call(pg, "add_trip_fees", c, version(pg, c), "price-fee-c", json.dumps([{"trip_id": ids["C"]}]), other, 5, None)
    before_total = int(call(pg, "get_ledger", c)["total_outstanding_vnd"])
    pg.sql(f"UPDATE sokhach.month_state SET locked=true WHERE customer_id={c} AND month='2026-01-01'")
    reject_call(pg, "apply_price_table", c, version(pg, c), "price-locked", json.dumps([ids["A"]]), error="MONTH_LOCKED")
    fixture_open_month(pg, c, "2026-01-01")
    for key, chosen, error in (("price-none", [ids["E"]], "PRICE_NOT_FOUND"), ("price-empty", [], "INVALID_TRIPS"),
                               ("price-dup", [ids["A"], ids["A"]], "INVALID_TRIPS"),
                               ("price-batch-fail", [ids["A"], ids["F"]], "PRICE_NOT_FOUND"),
                               ("price-stranger", [10 ** 12], "TRIP_NOT_FOUND")):
        reject_call(pg, "apply_price_table", c, version(pg, c), key, json.dumps(chosen), error=error)
    require(pg.value(f"SELECT count(*) FROM sokhach.trip_price_source WHERE customer_id={c}") == "0",
            "failed batch wrote a price")
    events = int(pg.value(f"SELECT count(*) FROM sokhach.event WHERE customer_id={c}"))
    v = version(pg, c)
    chosen = json.dumps([ids[k] for k in "DCBA"])
    applied = call(pg, "apply_price_table", c, v, "price-apply", chosen)
    require(call(pg, "apply_price_table", c, v, "price-apply", chosen) == applied, "apply retry changed")
    require(int(pg.value(f"SELECT count(*) FROM sokhach.event WHERE customer_id={c}")) == events + 1,
            "apply must write exactly one event")
    require(pg.value(f"SELECT kind FROM sokhach.event WHERE id={applied['event_id']}") == "price_table_apply",
            "apply event kind")
    ledger = {t["id"]: t for t in call(pg, "get_ledger", c)["trips"]}
    require([(ledger[ids[k]]["unit_price_vnd"], ledger[ids[k]]["other_fee_vnd"]) for k in "ABCD"]
            == [("95", None), ("85", None), ("75", "5"), ("75", None)], "applied prices or kept fee wrong")
    require(int(call(pg, "get_ledger", c)["total_outstanding_vnd"]) == before_total + 335,
            "balance did not add price plus kept fee")
    reject_call(pg, "apply_price_table", c, version(pg, c), "price-again", json.dumps([ids["A"]]), error="NO_CHANGE")

    # A later fee edit writes a new revision with the same unit price: still a table price.
    call(pg, "add_trip_fees", c, version(pg, c), "price-fee-d", json.dumps([{"trip_id": ids["D"]}]), other, 7, None)
    call(pg, "edit_trip_price", c, version(pg, c), "price-manual-b", ids["B"], 86, None)
    status = {t["trip_id"]: t for t in call(pg, "get_price_status", c)["trips"]}
    require(status[ids["D"]]["from_table"] and not status[ids["B"]]["from_table"] and status[ids["B"]]["differs"],
            "price source after fee/manual edit wrong")

    # Editing the table never rewrites a recorded trip; it only counts table-priced trips to re-apply.
    saved = call(pg, "save_price_table", c, version(pg, c), "price-save-2", json.dumps(_table(p2_khach_daklak="76")))
    require(saved["affected_trips"] == 2, f"affected trips wrong: {saved['affected_trips']}")
    ledger = {t["id"]: t for t in call(pg, "get_ledger", c)["trips"]}
    require(ledger[ids["C"]]["unit_price_vnd"] == "75", "table edit rewrote a trip")
    require(call(pg, "get_price_status", c)["reapply_count"] == 2, "reapply count wrong")
    edit = pg.value(f"SELECT (\"before\"->'price_table'->'periods'->1->'rates'->0->>'unit_price_vnd') || '>' || "
                    f"(\"after\"->'price_table'->'periods'->1->'rates'->0->>'unit_price_vnd') FROM sokhach.event "
                    f"WHERE customer_id={c} AND kind='price_table_edit' ORDER BY id DESC LIMIT 1")
    require(edit == "75>76", f"price table event before/after wrong: {edit}")
    pg.rejects(f"DELETE FROM sokhach.trip_price_source WHERE customer_id={c}", message="immutable row")

    # An empty table removes the book's table; lookups say so instead of guessing.
    call(pg, "save_price_table", c, version(pg, c), "price-clear",
         json.dumps({"tt_shippers": [], "locations": [], "periods": []}))
    require(all(t["lookup"] == {"reason": "NO_TABLE"} for t in call(pg, "get_price_status", c)["trips"]),
            "cleared table still prices")
    reject_call(pg, "get_price_status", 10 ** 12, error="CUSTOMER_NOT_FOUND")
    check_price_migration(pg)
    return "price table lookup, save guards, batch apply, source tracking and migration passed"


def check_price_migration(pg):
    migration = PRICE_MIGRATION.read_text(encoding="utf-8")
    catalog = ("SELECT jsonb_object_agg(p.oid::regprocedure::text,pg_get_functiondef(p.oid)) FROM pg_proc p "
               "WHERE p.pronamespace='sokhach'::regnamespace")
    cols = ("SELECT jsonb_agg(row_to_json(s)) FROM (SELECT table_name,column_name,data_type,is_nullable,column_default "
            "FROM information_schema.columns WHERE table_schema='sokhach' ORDER BY table_name,column_name) s")
    constraints = ("SELECT jsonb_object_agg(conrelid::regclass::text||'.'||conname,pg_get_constraintdef(oid)) "
                   "FROM pg_constraint WHERE connamespace='sokhach'::regnamespace")
    fresh = [pg.value(q) for q in (catalog, cols, constraints)]
    pg.sql(migration)  # rerun on the canonical schema changes nothing
    # XOA-DC-THANG-01 dựng lại ràng buộc event sau bảng giá; chạy lại nó như khi triển khai theo thứ tự.
    pg.sql((ROOT / "cong-no-web-handoff/tools/migrations/2026-10-29-v7-xoa-dieu-chinh-thang.sql").read_text(encoding="utf-8"))
    require([pg.value(q) for q in (catalog, cols, constraints)] == fresh, "price migration rerun changed schema")
    db = "webdebit_v7_price_migration"
    pg.sql(f"CREATE DATABASE {db}", database="postgres")
    old_schema = run(["git", "show", PRE_PRICE_REF + ":specs/v7-backend/schema-draft.sql"], cwd=ROOT).stdout
    old_functions = run(["git", "show", PRE_PRICE_REF + ":cong-no-web-handoff/tools/v7_backend_functions.sql"], cwd=ROOT).stdout
    old_schema = re.sub(r"^CREATE ROLE .*;\n", "", old_schema, flags=re.M)
    sheet = (ROOT / "cong-no-web-handoff/tools/migrations/2026-10-24-v7-sheet-cross-customer.sql").read_text(encoding="utf-8")
    for sql in (old_schema, old_functions, sheet):
        pg.sql(sql, database=db)
    require(pg.sql("SELECT to_regclass('sokhach.price_rate') IS NULL", database=db).stdout.strip() == "t",
            "old schema already has price tables")
    faulty = migration.replace("COMMIT;", "DO $$ BEGIN RAISE EXCEPTION 'PRICE_MIGRATION_FAULT'; END $$; COMMIT;")
    p = pg.sql(faulty, database=db, check=False)
    require(p.returncode != 0 and "PRICE_MIGRATION_FAULT" in p.stderr, "faulty migration accepted")
    require(pg.sql("SELECT to_regclass('sokhach.price_rate') IS NULL", database=db).stdout.strip() == "t",
            "failed price migration did not roll back")
    pg.sql(migration, database=db)
    pg.sql(migration, database=db)
    # Later migrations (CHUNG-TU-01) are part of the canonical schema the fresh snapshot was taken from.
    pg.sql((ROOT / "cong-no-web-handoff/tools/migrations/2026-10-29-v7-chung-tu.sql").read_text(encoding="utf-8"), database=db)
    pg.sql((ROOT / "cong-no-web-handoff/tools/migrations/2026-10-29-v7-xoa-dieu-chinh-thang.sql").read_text(encoding="utf-8"), database=db)
    for query, expected in zip((catalog, cols, constraints), fresh, strict=True):
        require(pg.sql(query, database=db).stdout.strip() == expected, "migrated schema differs from fresh schema")
