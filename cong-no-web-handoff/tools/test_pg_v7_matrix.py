#!/usr/bin/env python3
"""SQL review package for sokhach.get_receivables_matrix — disposable container, no production DDL.

Runs in the same one-off PostgreSQL container pattern as test_pg_v7_backend.py:
loads schema + existing functions, creates the DRAFT get_receivables_matrix, then
collects evidence: (1) reconciliation vs v_outstanding_month and get_ledger,
(2) SECURITY DEFINER privilege checks, (3) negative/cross-year/unclassified/opening cases,
(4) 250-customer benchmark (query time + payload size). Nothing is merged; the container
is destroyed at the end. Output: console + test-results/matrix-review.json."""

from __future__ import annotations

import json
import re
import subprocess
import sys
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = ROOT / "specs" / "v7-backend" / "schema-draft.sql"
FUNCTIONS = ROOT / "cong-no-web-handoff" / "tools" / "v7_backend_functions.sql"
IMAGE = "postgres:18.6@sha256:74935e72241653ca55e0414067e6d8763aceb8a810eb51b452253ec3dcfc4336"
LABEL_TEST, LABEL_RUN, LABEL_VALUE = "codex.test", "codex.run", "webdebit-v7-backend"

MATRIX_SQL = ""  # function is loaded from v7_backend_functions.sql under test



def run(args, *, input_text=None, check=True, timeout=60):
    p = subprocess.run(args, input=input_text, text=True, encoding="utf-8",
                       errors="replace", capture_output=True, timeout=timeout, check=False)
    if check and p.returncode:
        raise RuntimeError(f"command failed {args[:3]}: {p.stdout}\n{p.stderr[-800:]}")
    return p


class Pg:
    def __init__(self, name, run_id):
        self.name, self.run_id = name, run_id
        self.env = ["--env", "PGOPTIONS=-c statement_timeout=30000"]

    def sql(self, sql, *, user="postgres", check=True):
        return run(["docker", "exec", "-i", *self.env, self.name, "psql", "-X", "-qAt",
                    "-v", "ON_ERROR_STOP=1", "-U", user, "-d", "webdebit_v7_test"],
                   input_text=sql.rstrip().rstrip(";") + ";\n", check=check)

    def value(self, sql, *, user="postgres"):
        return self.sql(sql, user=user).stdout.strip()


def actor(sql: str, who="harness") -> str:
    return "BEGIN; SET LOCAL sokhach.actor = '" + who + "'; " + sql + "; COMMIT"


def new_book(pg: Pg, *amounts: tuple[str, int]) -> int:
    sha = "b" * 64
    total = sum(a for _, a in amounts)
    cid = int(pg.value(f"INSERT INTO sokhach.customer(name) VALUES ('MATRIX {uuid.uuid4().hex[:6]}') RETURNING id"))
    cut = int(pg.value("INSERT INTO sokhach.cutover(name,source,source_sha256,frozen_at,control_total_vnd,created_by) "
                       f"VALUES ('MATRIX','review','{sha}',now(),{total},'review') RETURNING id"))
    pg.sql(f"""INSERT INTO sokhach.cutover_customer(customer_id,cutover_id,expected_control_total_vnd,report_sha256,
     source_rows,imported_rows,quarantined_rows,skipped_with_reason_rows,unresolved_exceptions)
     VALUES ({cid},{cut},{total},'{sha}',1,1,0,0,0)""")
    ev = int(pg.value(f"INSERT INTO sokhach.event(customer_id,kind,actor,\"before\",\"after\",cutover_id) "
                      f"VALUES ({cid},'import','review','{{}}','{{\"cutover\":{cut}}}',{cut}) RETURNING id"))
    rows = ",".join(f"({cid},{cut},'{m}'::date,{a},'MATRIX',1,{ev})" for m, a in amounts)
    pg.sql("INSERT INTO sokhach.opening_balance(customer_id,cutover_id,debt_month,amount_vnd,source_tab,source_row,created_by_event) "
           f"VALUES {rows}")
    pg.sql(f"UPDATE sokhach.cutover_customer SET status='verified' WHERE customer_id={cid}")
    pg.sql(f"UPDATE sokhach.cutover SET status='verified' WHERE id={cut}")
    pg.sql(f"UPDATE sokhach.cutover SET status='active' WHERE id={cut}")
    pg.sql(f"UPDATE sokhach.cutover_customer SET status='active' WHERE customer_id={cid}")
    return cid


def main() -> int:
    report = {"image": IMAGE, "sql": "draft-v1 (spec §8.1)", "checks": {}, "benchmark": {}}
    run_id = uuid.uuid4().hex
    name = f"webdebit-matrix-review-{run_id}"
    def ok(label, cond, detail=""):
        report["checks"][label] = {"ok": bool(cond), "detail": str(detail)}
        print(("PASS " if cond else "FAIL ") + label + (f" — {detail}" if detail else ""))
    try:
        run(["docker", "volume", "create", "--label", f"{LABEL_TEST}={LABEL_VALUE}",
             "--label", f"{LABEL_RUN}={run_id}", name])
        run(["docker", "run", "--detach", "--name", name, "--label", f"{LABEL_TEST}={LABEL_VALUE}",
             "--label", f"{LABEL_RUN}={run_id}", "--network", "none", "--volume",
             f"{name}:/var/lib/postgresql", "--env", "POSTGRES_HOST_AUTH_METHOD=trust", IMAGE], timeout=240)
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            logs = run(["docker", "logs", name], check=False, timeout=10)
            if "PostgreSQL init process complete; ready for start up." in logs.stdout + logs.stderr:
                break
            time.sleep(1)
        pg = Pg(name, run_id)
        for _ in range(60):
            if run(["docker", "exec", name, "pg_isready", "-U", "postgres"], check=False).returncode == 0:
                break
            time.sleep(1)
        run(["docker", "exec", name, "psql", "-X", "-qAt", "-U", "postgres", "-d", "postgres",
             "-c", "CREATE DATABASE webdebit_v7_test"], timeout=30)
        def norm(p):
            return p.read_bytes().replace(bytes([13,10]), bytes([10])).decode()

        pg.sql(norm(SCHEMA))
        pg.sql(norm(FUNCTIONS))
        print("== container ready, function loaded from backend SQL ==")

        # ---- Fixtures: 4 tình huống đặc biệt + 2 loại bị loại ----
        a = new_book(pg, ("2026-03-01", 180000), ("2026-05-01", 120000), ("2026-06-01", 80000))     # thường 2026
        b = new_book(pg, ("2025-12-01", 500000))                                                     # CHỈ nợ năm cũ
        c = new_book(pg, ("2026-09-01", 150000), ("2026-10-01", -20000))                             # có tháng ÂM
        pg.sql("INSERT INTO sokhach.commodity(name) VALUES ('Sầu riêng') RETURNING id")
        pg.sql(f"UPDATE sokhach.customer SET commodity_id=(SELECT min(id) FROM sokhach.commodity) WHERE id={a}")
        d = new_book(pg, ("2026-01-01", 30000))                                                      # sẽ archive
        pg.sql(f"UPDATE sokhach.customer SET archived=true WHERE id={d}")
        f = new_book(pg, ("2026-03-01", 100000), ("2026-04-01", -100000))                           # tổng ròng 0
        e = int(pg.value("INSERT INTO sokhach.customer(name) VALUES ('MATRIX NOBASE') RETURNING id"))  # không cutover

        m2026 = json.loads(pg.value(actor("SELECT sokhach.get_receivables_matrix(2026)")))
        m2025 = json.loads(pg.value(actor("SELECT sokhach.get_receivables_matrix(2025)")))
        m2027 = json.loads(pg.value(actor("SELECT sokhach.get_receivables_matrix(2027)")))
        def by_id(m):
            return {x["customer_id"]: x for x in m["customers"]}

        ok("T1 tổng_all = get_ledger.total_outstanding_vnd (mọi khách)",
           all(by_id(m2026)[cid]["total_all_vnd"] == json.loads(
               pg.value(actor(f"SELECT sokhach.get_ledger({cid})")))["total_outstanding_vnd"]
               for cid in (a, b, c, f)))
        mm = by_id(m2026)[a]["months"]
        ok("T2 ô tháng = v_outstanding_month đúng tháng",
           mm["3"] == "180000" and mm["5"] == "120000" and mm["6"] == "80000" and mm["1"] == "0",
           json.dumps(mm))
        ok("T3 total_year = Σ 12 ô",
           all(int(v["total_year_vnd"]) == sum(int(x) for x in v["months"].values())
               for v in m2026["customers"]))
        ok("T4 khách CHỈ nợ năm cũ: năm 2027 vẫn hiện, 12 ô 0, total_all giữ",
           b in by_id(m2027) and all(x == "0" for x in by_id(m2027)[b]["months"].values())
           and by_id(m2027)[b]["total_all_vnd"] == "500000")
        ok("T5 đổi năm không đổi tổng mọi năm",
           m2026["grand_total_all_vnd"] == m2025["grand_total_all_vnd"] == m2027["grand_total_all_vnd"]
           == m2026["grand_total_all_vnd"])
        ok("T6 tháng ÂM giữ nguyên dấu (không về 0)",
           by_id(m2026)[c]["months"]["10"] == "-20000")
        ok("T7 khách chưa phân loại: commodity null, vẫn trong ma trận",
           by_id(m2026)[b]["commodity"] is None)
        ok("T8 số dư đầu nằm đúng tháng gốc (2025-12 trong ma trận 2025)",
           by_id(m2025)[b]["months"]["12"] == "500000")
        ok("T9 archived + NO_BASELINE bị loại",
           d not in by_id(m2026) and e not in by_id(m2026))
        ok("T10 grand_year(2026) + grand_year(2025) = grand_all",
           int(m2026["grand_total_year_vnd"]) + int(m2025["grand_total_year_vnd"]) == int(m2026["grand_total_all_vnd"]),
           f"{m2026['grand_total_year_vnd']} + {m2025['grand_total_year_vnd']} = {m2026['grand_total_all_vnd']}")
        cur_year = m2026["as_of"][:4]
        expect_years = sorted({2025, int(cur_year)})
        ok("T11 years_available từ data + năm hiện tại",
           m2026["years_available"] == expect_years, f"{m2026['years_available']} (hiện tại {cur_year})")
        ok("T12 năm sai bị từ chối (INVALID_YEAR)",
           pg.sql(actor("SELECT sokhach.get_receivables_matrix(1999)"), check=False).returncode != 0)
        ok("T13 P0: khách tổng ròng 0 (tháng +100000/−100000) VẪN hiện, giữ đủ 2 tháng",
           f in by_id(m2026) and by_id(m2026)[f]["months"]["3"] == "100000"
           and by_id(m2026)[f]["months"]["4"] == "-100000" and by_id(m2026)[f]["total_all_vnd"] == "0"
           and by_id(m2026)[f]["total_year_vnd"] == "0")
        ok("T14 P0: năm 2027 ngoài years_available vẫn truy vấn được, giữ khách nợ cũ",
           2027 not in m2026["years_available"] and b in by_id(m2027))
        ok("T14b P0: năm ngoài phạm vi [2000, hiện_tại+1] bị từ chối (2028)",
           pg.sql(actor("SELECT sokhach.get_receivables_matrix(2028)"), check=False).returncode != 0)

        # ---- Quyền ----
        ok("P1 reader/app được EXECUTE, PUBLIC không",
           pg.value("SELECT has_function_privilege('sokhach_reader','sokhach.get_receivables_matrix(int)','EXECUTE')") == "t"
           and pg.value("SELECT has_function_privilege('sokhach_app','sokhach.get_receivables_matrix(int)','EXECUTE')") == "t"
           and pg.value("SELECT count(*) = 0 FROM aclexplode((SELECT proacl FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='sokhach' AND p.proname='get_receivables_matrix')) a WHERE a.grantee = 0") == "t")
        pro = pg.value("SELECT prosecdef::text || '|' || coalesce(proconfig::text,'') FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='sokhach' AND p.proname='get_receivables_matrix'")
        ok("P2 hàm là SECURITY DEFINER, search_path khóa", pro.startswith("true|") and "pg_catalog,sokhach,pg_temp" in pro.replace(" ", ""), pro)
        ok("P3 reader KHÔNG select trực tiếp view nguồn",
           pg.sql("SELECT count(*) FROM sokhach.v_outstanding_month", user="sokhach_reader", check=False).returncode != 0)
        ok("P4 reader gọi được hàm qua SET ROLE (role NOLOGIN đúng chính sách)",
           pg.sql("BEGIN; SET LOCAL sokhach.actor = 'reader'; SET ROLE sokhach_reader; SELECT sokhach.get_receivables_matrix(2026) IS NOT NULL; COMMIT").returncode == 0)

        detail = json.loads(pg.value(actor(f"SELECT sokhach.get_receivables_detail({a},'2026-03-01')")))
        ledger = json.loads(pg.value(actor(f"SELECT sokhach.get_ledger({a})")))
        ledger_month = next(row for row in ledger["months"] if row["month"] == "2026-03-01")
        ok("D1 chi tiết tháng khớp sổ và ô ma trận",
           all(detail[key] == ledger_month[key] for key in ("outstanding_vnd", "charges_vnd", "received_vnd"))
           and detail["outstanding_vnd"] == by_id(m2026)[a]["months"]["3"]
           and detail["opening"] is True and detail["trips"] == [])
        empty = json.loads(pg.value(actor(f"SELECT sokhach.get_receivables_detail({a},'2026-07-01')")))
        ok("D2 tháng trống giữ 0 và không bịa chuyến", empty["outstanding_vnd"] == empty["charges_vnd"] == empty["received_vnd"] == "0"
           and empty["opening"] is False and empty["trips"] == [])
        ok("D3 quyền detail và tháng sai bị từ chối",
           pg.value("SELECT has_function_privilege('sokhach_reader','sokhach.get_receivables_detail(bigint,date)','EXECUTE')") == "t"
           and pg.value("SELECT count(*)=0 FROM aclexplode((SELECT proacl FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='sokhach' AND p.proname='get_receivables_detail')) a WHERE a.grantee=0") == "t"
           and pg.sql(actor(f"SELECT sokhach.get_receivables_detail({a},'2026-03-02')"), check=False).returncode != 0)

        # ---- Benchmark 250 khách (tổng control tính trước bằng SELECT, không UPDATE cutover) ----
        pg.sql("""
        CREATE UNLOGGED TABLE bench_c AS
        WITH c AS (INSERT INTO sokhach.customer(name) SELECT 'BENCH '||lpad(g::text,4,'0') FROM generate_series(1,250) g RETURNING id, name),
             t AS (SELECT coalesce(sum(((g*13+m*29)%40+5)*1000000),0)::bigint AS total
                     FROM generate_series(1,250) g CROSS JOIN generate_series(1,12) m WHERE (g+m)%4<>0),
             x AS (INSERT INTO sokhach.cutover(name,source,source_sha256,frozen_at,control_total_vnd,created_by)
                   SELECT 'BENCH','bench',repeat('c',64),now(),(SELECT total FROM t),'review' RETURNING id)
        SELECT c.id AS cid, (SELECT id FROM x) AS cut, substring(c.name from 6)::int AS g FROM c;
        """)
        pg.sql("""
        INSERT INTO sokhach.cutover_customer(customer_id,cutover_id,expected_control_total_vnd,report_sha256,
         source_rows,imported_rows,quarantined_rows,skipped_with_reason_rows,unresolved_exceptions)
        SELECT cid, cut,
               coalesce(sum(((g*13+m*29)%40+5)*1000000) FILTER (WHERE (g+m)%4<>0),0)::bigint,
               repeat('c',64), 1, 1, 0, 0, 0
        FROM bench_c CROSS JOIN generate_series(1,12) m GROUP BY cid, cut;
        """)
        pg.sql("""
        INSERT INTO sokhach.event(customer_id,kind,actor,"before","after",cutover_id)
        SELECT cid,'import','review','{}',jsonb_build_object('cutover',cut),cut FROM bench_c;
        """)
        pg.sql("""
        INSERT INTO sokhach.opening_balance(customer_id,cutover_id,debt_month,amount_vnd,source_tab,source_row,created_by_event)
        SELECT b.cid, b.cut, make_date(2026,m,1), ((b.g*13+m*29)%40+5)*1000000, 'BENCH', 1,
               (SELECT id FROM sokhach.event e WHERE e.customer_id=b.cid LIMIT 1)
        FROM bench_c b CROSS JOIN generate_series(1,12) m WHERE (b.g+m)%4<>0;
        """)
        pg.sql("UPDATE sokhach.cutover_customer SET status='verified' WHERE cutover_id=(SELECT min(cut) FROM bench_c)")
        pg.sql("UPDATE sokhach.cutover SET status='verified' WHERE id=(SELECT min(cut) FROM bench_c)")
        pg.sql("UPDATE sokhach.cutover SET status='active' WHERE id=(SELECT min(cut) FROM bench_c)")
        pg.sql("UPDATE sokhach.cutover_customer SET status='active' WHERE cutover_id=(SELECT min(cut) FROM bench_c)")
        n = int(pg.value("SELECT count(*) FROM sokhach.customer c JOIN sokhach.cutover_customer cc ON cc.customer_id=c.id AND cc.status='active' JOIN sokhach.cutover x ON x.id=cc.cutover_id AND x.status='active' WHERE NOT c.archived AND c.name LIKE 'BENCH%'"))
        size = int(pg.value(actor("SELECT octet_length(sokhach.get_receivables_matrix(2026)::text)")))
        plan = pg.sql(actor("EXPLAIN (ANALYZE, COSTS OFF, TIMING OFF) SELECT sokhach.get_receivables_matrix(2026)")).stdout
        ms = re.search(r"Execution Time: ([\d.]+) ms", plan)
        t0 = time.time()
        pg.value(actor("SELECT sokhach.get_receivables_matrix(2026)"))
        wall_ms = round((time.time() - t0) * 1000)
        report["benchmark"] = {"customers": n, "payload_bytes": size, "exec_ms": float(ms.group(1)) if ms else None, "wall_ms": wall_ms}
        ok(f"B1 benchmark {n} khách: payload {size/1024:.0f}KB < 200KB, exec {ms.group(1) if ms else '?'}ms < 500ms",
           n >= 250 and size < 200 * 1024 and ms and float(ms.group(1)) < 500)
        recon = pg.value(actor("SELECT count(*) FROM sokhach.v_outstanding_month v JOIN bench_c b ON b.cid=v.customer_id"))
        ok("B2 250 khách đối chiếu trực tiếp view: 0 lệch tổng",
           pg.value(actor("SELECT count(*) FROM (SELECT customer_id, sum(outstanding_vnd) s FROM sokhach.v_outstanding_month WHERE customer_id IN (SELECT cid FROM bench_c) GROUP BY 1) g JOIN sokhach.cutover_customer cc ON cc.customer_id=g.customer_id AND cc.status='active' WHERE g.s <> cc.expected_control_total_vnd")) == "0",
           f"{recon} rows view")
    finally:
        run(["docker", "rm", "-f", name], check=False)
        run(["docker", "volume", "rm", name], check=False)

    out = ROOT / "test-results" / "matrix-review.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    failed = [k for k, v in report["checks"].items() if not v["ok"]]
    print(f"\n{'ALL PASS' if not failed else 'FAILED: ' + ', '.join(failed)} — report: {out}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
