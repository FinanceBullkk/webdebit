"""GET sổ luôn có dòng tháng hiện tại (SK-C1, specs/v7-thang-hien-tai.md). Chạy qua harness V7 dùng một lần, dữ liệu giả."""
from pg_v7_harness import (
    call,
    new_book,
    require,
    version,
)

TODAY = "SELECT (clock_timestamp() AT TIME ZONE 'Asia/Ho_Chi_Minh')::date"


def _rows(ledger):
    return [(row["month"][:7], row["prior_months_vnd"], row["charges_vnd"], row["received_vnd"],
             row["outstanding_vnd"], row["end_of_month_vnd"]) for row in ledger["months"]]


def check_thang_hien_tai(pg):
    today = pg.value(TODAY)
    this = today[:7]
    # Nợ ở hai tháng cũ, tháng hiện tại chưa có chuyến, phiếu hay dòng sổ gốc.
    c = new_book(pg, ("2026-01-01", 100), ("2026-02-01", 50))
    ledger = call(pg, "get_ledger", c)
    require(ledger["today_month"][:7] == this, f"today_month: {ledger['today_month']}")
    require(_rows(ledger) == [("2026-01", "0", "100", "0", "100", "100"), ("2026-02", "100", "50", "0", "50", "150"),
                              (this, "150", "0", "0", "0", "150")], f"months without current-month rows: {_rows(ledger)}")
    require(ledger["total_outstanding_vnd"] == "150", f"total: {ledger['total_outstanding_vnd']}")
    # Dòng thêm không đổi phân bổ: nợ còn lại theo kỳ vẫn chỉ ở hai tháng cũ.
    require(pg.value("SELECT string_agg(debt_month::text||'='||outstanding_vnd,',' ORDER BY debt_month) "
                     f"FROM sokhach.v_outstanding_month WHERE customer_id={c}") == "2026-01-01=100,2026-02-01=50",
            "outstanding buckets changed")
    # Phiếu thu trong tháng hiện tại: vẫn đúng một dòng tháng hiện tại, Nợ đầu tháng giữ nguyên, nợ cũ trước.
    call(pg, "record_receipt", c, version(pg, c), "sk-c1-thu", today, "THU TIỀN", 120)
    ledger = call(pg, "get_ledger", c)
    require([row[0] for row in _rows(ledger)].count(this) == 1, f"current month twice: {_rows(ledger)}")
    require(_rows(ledger)[-1] == (this, "150", "0", "120", "0", "30"), f"current month after receipt: {_rows(ledger)[-1]}")
    require(_rows(ledger)[:2] == [("2026-01", "0", "100", "0", "0", "100"), ("2026-02", "100", "50", "0", "30", "150")],
            f"old months after receipt: {_rows(ledger)[:2]}")
    require(ledger["total_outstanding_vnd"] == "30", f"total after receipt: {ledger['total_outstanding_vnd']}")
    # Sổ hết nợ: dòng tháng hiện tại có số 0, không phải trống.
    paid = new_book(pg, ("2026-01-01", 0))
    require(_rows(call(pg, "get_ledger", paid))[-1] == (this, "0", "0", "0", "0", "0"), "zero book current month")
    # Sổ chưa có mốc nạp: months vẫn rỗng.
    blank = int(pg.value("INSERT INTO sokhach.customer(name) VALUES ('FAKE NO BASELINE') RETURNING id"))
    ledger = call(pg, "get_ledger", blank)
    require(ledger["status"] == "NO_BASELINE" and ledger["months"] == [], f"no baseline: {ledger['status']} {ledger['months']}")
