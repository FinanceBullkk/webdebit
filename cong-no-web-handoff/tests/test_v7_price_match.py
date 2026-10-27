"""Read-only price match: Sheet tab rows to one web trip or original-book row, fake data only."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tests"))
import v7_price_match as pm  # noqa: E402
from test_v7_load_real_copy import FAKE_AMOUNT, FAKE_NAME, fixture  # noqa: E402


def sheet(row=5, container="FAKEU0000001", date="2026-10-03", price=50000000, fee=None, tab="Khach gia A"):
    return {"customer_tab": tab, "source_row": row, "debt_month": "2026-10", "container": container,
            "date": date, "sheet_unit_price_vnd": price, "sheet_other_fee_vnd": fee}


def trip(trip_id=11, container="FAKEU 0000001", date="2026-10-03", price=None, fee=None, status="confirmed"):
    return {"id": trip_id, "container": container, "event_date": date, "unit_price_vnd": price,
            "other_fee_vnd": fee, "status": status, "month": date[:7] + "-01", "deleted": False}


def book(trips=(), legacy=(), locked=False):
    return {"today_month": "2026-10-01", "month_locks": [{"month": "2026-10-01", "locked": locked}],
            "trips": list(trips), "legacy_rows": list(legacy)}


def status(rows, ledgers):
    return [r["status"] for r in pm.match(rows, ledgers)]


class PriceMatchTest(unittest.TestCase):
    def test_statuses_for_one_unique_target(self):
        self.assertEqual(status([sheet()], {"Khach gia A": book([trip()])}), ["READY"])
        self.assertEqual(status([sheet()], {"Khach gia A": book([trip()], locked=True)}), ["MONTH_LOCKED"])
        self.assertEqual(status([sheet()], {"Khach gia A": book([trip(price="50000000")])}), ["PRICE_UNCHANGED"])
        self.assertEqual(status([sheet(fee=0)], {"Khach gia A": book([trip(price="50000000")])}), ["PRICE_UNCHANGED"])
        self.assertEqual(status([sheet(fee=300)], {"Khach gia A": book([trip(price="50000000")])}), ["CONFLICT"])
        self.assertEqual(status([sheet()], {"Khach gia A": book([trip(price="49000000")])}), ["CONFLICT"])
        self.assertEqual(status([sheet()], {"Khach gia A": book([trip(status="pending_review")])}), ["PENDING_REVIEW"])
        self.assertEqual(status([sheet(price=None)], {"Khach gia A": book([trip()])}), ["SHEET_NO_PRICE"])

    def test_unmatched_and_ambiguous_rows_are_never_ready(self):
        self.assertEqual(status([sheet(container="")], {"Khach gia A": book([trip()])}), ["NO_CONTAINER"])
        self.assertEqual(status([sheet(tab="Khach khac")], {"Khach gia A": book([trip()])}), ["NO_CUSTOMER"])
        self.assertEqual(status([sheet(date="2026-09-01")], {"Khach gia A": book([trip()])}), ["NOT_FOUND"])
        self.assertEqual(status([sheet()], {"Khach gia A": book([trip(), trip(12)])}), ["AMBIGUOUS"])
        self.assertEqual(status([sheet(), sheet(6)], {"Khach gia A": book([trip()])}), ["AMBIGUOUS", "AMBIGUOUS"])
        self.assertEqual(status([sheet()], {"Khach gia A": book([trip(status="rejected")])}), ["NOT_FOUND"])

    def test_exact_date_wins_and_near_date_is_labelled(self):
        rows = pm.match([sheet()], {"Khach gia A": book([trip(), trip(12, date="2026-10-05")])})
        self.assertEqual((rows[0]["status"], rows[0]["match_basis"], rows[0]["target_id"]), ("READY", "exact_date", 11))
        rows = pm.match([sheet(date="2026-10-01")], {"Khach gia A": book([trip()])})
        self.assertEqual((rows[0]["status"], rows[0]["match_basis"]), ("READY", "near_date"))

    def test_original_book_rows_are_targets(self):
        legacy = {"id": 21, "kind": "trip", "month": "2026-10-01", "current": {
            "container": "FAKEU0000001", "event_date": "2026-10-03", "unit_price_vnd": None,
            "other_fee_vnd": None, "month": "2026-10-01", "deleted": False}}
        rows = pm.match([sheet()], {"Khach gia A": book(legacy=[legacy])})
        self.assertEqual((rows[0]["status"], rows[0]["target_kind"], rows[0]["target_id"]), ("READY", "legacy", 21))

    def test_alias_names_find_the_book_unless_shared(self):
        named = book([trip()]) | {"_display_name": "Khach gia A tren Sheet", "_aliases": ["KHACH A CU"]}
        rows = pm.match([sheet(tab="KHACH A CU")], {"Khach V7": named})
        self.assertEqual((rows[0]["status"], rows[0]["customer_basis"]), ("READY", "alias"))
        other = book([trip(21)]) | {"_aliases": ["KHACH A CU"]}
        self.assertEqual(status([sheet(tab="KHACH A CU")], {"Khach V7": named, "Khach khac": other}), ["NO_CUSTOMER"])
        self.assertEqual(status([sheet(tab="Khach V7")], {"Khach V7": named, "Khach khac": other}), ["READY"])

    def test_undated_sheet_row_uses_container_only_when_unique(self):
        rows = pm.match([sheet(date=None)], {"Khach gia A": book([trip(date="2026-10-03")])})
        self.assertEqual((rows[0]["status"], rows[0]["match_basis"]), ("READY", "container_only"))
        self.assertEqual(status([sheet(date=None)], {"Khach gia A": book([trip(), trip(12, date="2026-07-01")])}),
                         ["AMBIGUOUS"])
        priced = [trip(price="1"), trip(12, date="2026-07-01", price="2")]
        self.assertEqual(status([sheet(date=None)], {"Khach gia A": book(priced)}), ["AMBIGUOUS_PRICED"])
        # A dated Sheet row never falls back to container alone.
        self.assertEqual(status([sheet(date="2026-01-01")], {"Khach gia A": book([trip()])}), ["NOT_FOUND"])

    def test_original_book_row_compares_charged_total_not_fee(self):
        legacy = {"id": 21, "kind": "trip", "month": "2026-10-01", "current": {
            "container": "FAKEU0000001", "event_date": "2026-10-03", "unit_price_vnd": "50000000",
            "other_fee_vnd": None, "counted_vnd": "49500000", "month": "2026-10-01", "deleted": False}}
        discounted = sheet(fee=-500000) | {"sheet_total_vnd": 49500000}
        self.assertEqual(status([discounted], {"Khach gia A": book(legacy=[legacy])}), ["PRICE_UNCHANGED"])
        self.assertEqual(status([discounted | {"sheet_total_vnd": 49000000}], {"Khach gia A": book(legacy=[legacy])}),
                         ["CONFLICT"])
        # Web trips still compare the fee itself.
        self.assertEqual(status([discounted], {"Khach gia A": book([trip(price="50000000")])}), ["CONFLICT"])

    def test_cli_reads_xlsx_and_writes_outside_repo_only(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source"
            source.mkdir()
            fixture(source)
            web = root / "web"
            web.mkdir()
            (web / f"{FAKE_NAME}.json").write_text(json.dumps(book([trip(container="FAKE-CONT-XY")])), encoding="utf-8")
            out = root / "out"
            code = pm.main(["--xlsx", str(source / "source-google-export.xlsx"), "--ledger-json", str(web), "--out", str(out)])
            self.assertEqual(code, 0)
            summary = json.loads((out / "summary.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["counts"]["READY"], 1)
            self.assertIn(str(FAKE_AMOUNT), (out / "price_match_rows.csv").read_text(encoding="utf-8-sig"))
            self.assertIn("Ghi được", (out / "price_match_report.html").read_text(encoding="utf-8"))
            self.assertEqual(pm.main(["--xlsx", str(source / "source-google-export.xlsx"),
                                      "--ledger-json", str(web), "--out", str(out)]), 2)
            self.assertEqual(pm.main(["--xlsx", str(source / "source-google-export.xlsx"),
                                      "--ledger-json", str(web), "--out", str(ROOT / "price-out")]), 2)


if __name__ == "__main__":
    unittest.main()
