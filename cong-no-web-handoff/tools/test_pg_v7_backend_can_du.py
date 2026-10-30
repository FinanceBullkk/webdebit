"""CAN-DU-01 (30/10/2026): khoản dư kỳ âm cấn vào kỳ còn nợ cũ nhất; dòng phân bổ phiếu không đổi.

Run only through disposable test_pg_v7_backend.py harness."""
import json

from pg_v7_harness import (
    CAN_DU_MIGRATION,
    actor_sql,
    allocations,
    call,
    months,
    new_book,
    require,
)

CATALOG = ("SELECT jsonb_object_agg(p.oid::regprocedure::text,pg_get_functiondef(p.oid)) FROM pg_proc p "
           "WHERE p.pronamespace='sokhach'::regnamespace")
VIEWS = ("SELECT jsonb_object_agg(c.relname,pg_get_viewdef(c.oid)) FROM pg_class c "
         "WHERE c.relnamespace='sokhach'::regnamespace AND c.relkind='v'")


def _view(pg, view: str, customer: int) -> list[str]:
    return pg.value(f"SELECT string_agg(outstanding_vnd::text,',' ORDER BY debt_month) FROM sokhach.{view} "
                    f"WHERE customer_id={customer}").split(",")


def _detail(pg, customer: int, month: str) -> dict:
    return json.loads(pg.value(actor_sql(f"SELECT sokhach.get_receivables_detail({customer},'{month}')")))


def check_can_du(pg) -> str:
    # Migration chỉ thay view đọc và hai hàm: chạy hai lượt trên lược đồ chuẩn không đổi catalog.
    fresh = (pg.value(CATALOG), pg.value(VIEWS))
    migration = CAN_DU_MIGRATION.read_text(encoding="utf-8")
    pg.sql(migration)
    pg.sql(migration)
    require((pg.value(CATALOG), pg.value(VIEWS)) == fresh, "can-du migration rerun changed catalog or views")
    for role in ("v7_app", "v7_reader"):
        pg.rejects("SELECT * FROM sokhach.v_outstanding_month_raw", user=role)

    # 1. Khoản dư kỳ đầu cấn vào kỳ còn nợ cũ nhất trước, tổng khách giữ nguyên.
    c = new_book(pg, ("2026-01-01", 100), ("2026-02-01", -271), ("2026-03-01", 300), ("2026-04-01", 50))
    require(_view(pg, "v_outstanding_month_raw", c) == ["100", "-271", "300", "50"], "raw view changed")
    require(_view(pg, "v_outstanding_month", c) == ["0", "0", "129", "50"], "credit not applied oldest debt first")
    ledger = call(pg, "get_ledger", c)
    require(ledger["total_outstanding_vnd"] == "179" and [m[1] for m in months(pg, c)] == ["0", "0", "129", "50"],
            "get_ledger months or total wrong")
    # Ngăn kéo: số thô − khoản dư đã cấn = ô ma trận.
    applied = [_detail(pg, c, f"2026-0{n}-01")["credit_applied_vnd"] for n in range(1, 5)]
    require(applied == ["100", "-271", "171", "0"], f"credit_applied_vnd wrong: {applied}")
    # Ma trận đọc cùng view; kiểm riêng ở test_pg_v7_matrix.py (DB dùng chung có sổ gần trần bigint).

    # 2. Cấn hết nợ mà vẫn dư: phần dư (khách trả trước) nằm ở kỳ cuối, các kỳ khác về 0.
    c2 = new_book(pg, ("2026-01-01", -500), ("2026-02-01", 100), ("2026-03-01", 50))
    require(_view(pg, "v_outstanding_month", c2) == ["0", "0", "-350"], "leftover credit not on last month")
    pg.true("NOT EXISTS (SELECT 1 FROM sokhach.v_outstanding_month GROUP BY customer_id "
            "HAVING bool_or(outstanding_vnd>0) AND bool_or(outstanding_vnd<0))", "a book shows debt and credit together")

    # 3. Phiếu thu vẫn phân bổ theo số thô (V7-SO), nên không sinh event phân bổ lại thừa.
    c3 = new_book(pg, ("2026-01-01", -50), ("2026-02-01", 100), ("2026-03-01", 20))
    result = call(pg, "record_receipt", c3, 0, "can-du-r1", "2026-04-01", "THU TIỀN", 100)
    require(allocations(pg, c3, result["pid"]) == [("2026-02-01", "debt", "100")] and result["reallocated"] == [],
            "receipt allocation moved off raw buckets")
    require(pg.value(f"SELECT count(*) FROM sokhach.event WHERE customer_id={c3} AND kind='reallocation'") == "0",
            "receipt wrote a reallocation event")
    require(_view(pg, "v_outstanding_month", c3) == ["0", "0", "-30"], "credit after receipt wrong")
    return "credit applied to oldest debt; leftover on last month; totals and receipt allocations unchanged"
