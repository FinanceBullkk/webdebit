"""Regression: receipt multiplicity, dated evidence, known zero and visible explanations."""

import unittest

from test_v7_reconcile_hints import hints, ledger, legacy_row, receipt, sheet_row


class HintRegressionTest(unittest.TestCase):
    def test_three_web_two_sheet_only_one_is_extra(self):
        web = ledger([receipt(f"PH-{n}", "2026-10-31", 100) for n in range(3)])
        for note in ("31/10/2026", "da tt"):
            with self.subTest(note=note):
                sheet = [{"amount_vnd": 100, "note": note} for _ in range(2)]
                found = hints.receipt_twice(web, sheet)
                self.assertEqual([row["delta_vnd"] for row in found], [100])

    def test_other_date_does_not_hide_duplicate(self):
        web = ledger([receipt("PH-1", "2026-10-30", 100), receipt("PH-2", "2026-10-31", 100),
                      receipt("PH-3", "2026-10-31", 100)])
        sheet = [{"amount_vnd": 100, "note": "30/10/2026"}, {"amount_vnd": 100, "note": "DA TT 31/10/2026"}]
        self.assertEqual([(row["date"], row["delta_vnd"]) for row in hints.receipt_twice(web, sheet)], [("2026-10-31", 100)])

    def test_unknown_dates_are_conservative_and_unknown_amounts_do_not_count(self):
        web = ledger([receipt(f"PH-{n}", "2026-10-31", 100) for n in range(2)])
        self.assertEqual(hints.receipt_twice(web, [{"amount_vnd": 100}, {"amount_vnd": 100}]), [])
        self.assertEqual(len(hints.receipt_twice(web, [{"amount_vnd": 100}, {"amount_vnd": None}])), 1)

    def test_known_zero_is_compared_but_missing_zero_row_is_not_a_hint(self):
        web = ledger(legacy=[legacy_row(1, "AAAU1234567", "2026-10-03", 100, 0, 100)])
        rows = [sheet_row(10, "AAAU1234567", "2026-10-03", 0, 0, 0),
                sheet_row(11, "BBBU1234567", None, 0, 0, 0)]
        self.assertEqual([row["delta_vnd"] for row in hints.price_rows(rows, web)], [-100])

    def test_explanation_uses_only_returned_hints(self):
        rows = [sheet_row(n, f"TEST-{n}", None, amount, 0, amount) for n, amount in enumerate([90] * 8 + [10], 1)]
        visible, explained = hints.for_book(ledger(), rows, 100)
        self.assertEqual(len(visible), 8)
        self.assertFalse(explained)
        self.assertEqual(explained, hints.explains(visible, 100))
        visible, explained = hints.for_book(ledger(), rows[-2:], 100)
        self.assertTrue(explained)
        self.assertEqual(sum(row["delta_vnd"] for row in visible), 100)


if __name__ == "__main__":
    unittest.main()
