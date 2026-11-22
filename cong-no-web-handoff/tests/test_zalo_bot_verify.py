"""Bộ kiểm số của bot Zalo (ZALO-BOT-01 Phần 4): điền chỗ trống từ kết quả công cụ, chặn số gõ tay không có nguồn."""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from zalo_bot import verify  # noqa: E402

RESULTS = [
    {"trang": "Tổng quan", "tong_no_vnd": "1234567890", "so_khach": 42},
    {"rows": [{"ten": "Khách A", "no_vnd": "350000000", "qua_han_vnd": "120500000", "so_chuyen": 1200},
              {"ten": "Khách B", "no_vnd": "45000", "booking": "123456789"}]},
]


def run(draft):
    text, spans = verify.fill(draft, RESULTS)
    money, numbers = verify.collect_values(RESULTS)
    return text, verify.check(text, spans, money, numbers)


class FillTests(unittest.TestCase):
    def test_money_fields_are_formatted_like_the_web(self):
        text, spans = verify.fill("Tổng nợ {t1.tong_no_vnd}, khách {t2.rows.0.ten} nợ {t2.rows.0.no_vnd}.", RESULTS)
        self.assertEqual(text, "Tổng nợ 1.234.567.890 đ, khách Khách A nợ 350.000.000 đ.")
        self.assertEqual([text[a:b] for a, b in spans], ["1.234.567.890 đ", "Khách A", "350.000.000 đ"])
        self.assertEqual(verify.format_vnd(-5000), "-5.000 đ")

    def test_placeholder_to_a_missing_field_is_refused(self):
        for draft in ("{t3.tong_no_vnd}", "{t1.khong_co_vnd}", "{t2.rows.9.no_vnd}", "{t2.rows}", "{t1.trang_vnd}"):
            with self.subTest(draft=draft), self.assertRaises(verify.FillError):
                verify.fill(draft, RESULTS)


class CheckTests(unittest.TestCase):
    def test_filled_answer_passes(self):
        _text, problems = run("Tổng nợ {t1.tong_no_vnd} của {t1.so_khach} khách. Khách A quá hạn {t2.rows.0.qua_han_vnd}.")
        self.assertEqual(problems, [])

    def test_typed_amounts_must_exist_in_tool_results(self):
        self.assertEqual(run("Khách A nợ 350.000.000 đ.")[1], [])
        self.assertEqual(run("Khách B nợ 45000đ.")[1], [])
        self.assertEqual([p.code for p in run("Khách A nợ 351.000.000 đ.")[1]], ["unknown_amount"])
        self.assertEqual([p.code for p in run("Khách A nợ 350000001 đồng.")[1]], ["unknown_amount"])

    def test_amount_without_currency_sign_is_still_checked(self):
        self.assertEqual([p.code for p in run("Khách A còn 350000002.")[1]], ["unknown_number"])
        self.assertEqual(run("Booking 123456789 của khách B, 1200 chuyến.")[1], [])

    def test_units_exact_value_needs_no_khoang(self):
        self.assertEqual(run("Khách A nợ 350 triệu.")[1], [])
        self.assertEqual(run("Khách B nợ 45k.")[1], [])

    def test_rounded_amount_must_round_from_a_real_value_and_say_khoang(self):
        self.assertEqual(run("Tổng nợ khoảng 1,2 tỷ.")[1], [])
        self.assertEqual(run("Quá hạn gần 120,5 triệu.")[1], [])
        self.assertEqual([p.code for p in run("Tổng nợ 1,2 tỷ.")[1]], ["rounded_without_approx"])
        self.assertEqual([p.code for p in run("Tổng nợ khoảng 1,3 tỷ.")[1]], ["unknown_amount"])
        self.assertEqual([p.code for p in run("Tổng nợ khoảng 2 tỷ.")[1]], ["unknown_amount"])

    def test_dates_times_years_and_small_counts_are_not_checked(self):
        self.assertEqual(run("Dữ liệu lúc 10:05 ngày 22/11/2026, tháng 10/2026, năm 2026, 3 chuyến, 12 khách.")[1], [])

    def test_words_that_start_like_units_are_not_amounts(self):
        self.assertEqual(run("5 trả rồi, 10 khách, 2 trong số đó.")[1], [])

    def test_every_bad_number_is_reported_with_its_text(self):
        _text, problems = run("Khách A nợ 999.999 đ và khách B nợ 7 triệu.")
        self.assertEqual([(p.code, p.text) for p in problems],
                         [("unknown_amount", "khách B nợ 7 triệu"), ("unknown_amount", "999.999 đ")])


if __name__ == "__main__":
    unittest.main()
