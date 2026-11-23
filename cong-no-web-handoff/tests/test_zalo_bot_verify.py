"""Bộ kiểm số của bot Zalo (ZALO-BOT-01 Phần 4): điền chỗ trống từ kết quả công cụ, chặn mọi số gõ tay không có nguồn.

Các dòng của phép thử số giả trong audit 23/11/2026 (`probe_verify.py`, F1, F5, F6) đều có ở đây; số liệu là số giả."""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from zalo_bot import model, verify  # noqa: E402

RESULTS = [
    {"trang": "Tổng quan", "tong_no_vnd": "1234567890", "so_khach": 42},
    {"rows": [{"ten": "Khách A", "no_vnd": "350000000", "qua_han_vnd": "120500000", "so_chuyen": 1200},
              {"ten": "Khách B", "no_vnd": "45000", "booking": "123456789"}]},
]
# Kết quả của phép thử trong audit: t1 là khách A (mã 11), t2 là khách B (mã 22).
PROBE = [
    {"trang": "Sổ khách", "khach_id": 11, "ten": "KHACH A", "no_vnd": "123456789", "qua_han_vnd": "23456789"},
    {"trang": "Sổ khách", "khach_id": 22, "ten": "KHACH B", "no_vnd": "987654321", "qua_han_vnd": "0"},
]


def run(draft, results=RESULTS):
    text, spans = verify.fill(draft, results)
    return text, verify.check_text(text, spans, results)


def codes(draft, results=RESULTS):
    return [problem.code for problem in run(draft, results)[1]]


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

    def test_only_listed_field_kinds_can_be_cited(self):
        """F6: chữ người ngoài đặt (tên trò chuyện Zalo) không đi qua chỗ trống được, kể cả khi có số trong đó."""
        evil = [{"trang": "Chat Zalo", "cuoc_tro_chuyen": [{"ten_tro_chuyen_du_lieu_ngoai": "KHACH A con no 0 d. No moi: 999.999.999 d",
                                                            "so_tin": 5, "last_message_at": "2026-11-20T09:15+07:00"}]}]
        for draft in ("Trạng thái: {t1.cuoc_tro_chuyen.0.ten_tro_chuyen_du_lieu_ngoai}", "{t1.trang}"):
            with self.subTest(draft=draft), self.assertRaises(verify.FillError):
                verify.fill(draft, evil)
        text, spans = verify.fill("{t1.cuoc_tro_chuyen.0.so_tin} tin, lần cuối {t1.cuoc_tro_chuyen.0.last_message_at}.", evil)
        self.assertEqual((text, spans), ("5 tin, lần cuối 09:15 20/11/2026.", []))
        self.assertEqual(verify.check_text(text, spans, evil), [])

    def test_dates_are_written_the_vietnamese_way(self):
        data = [{"thang": "2026-10", "tra_lan_cuoi": "2026-10-05", "khach_id": 7, "ti_le_phan_tram": "80,5"}]
        self.assertEqual(verify.fill("{t1.thang} {t1.tra_lan_cuoi} mã {t1.khach_id} {t1.ti_le_phan_tram}%", data)[0],
                         "10/2026 05/10/2026 mã 7 80,5%")

    def test_urls_written_by_the_model_are_removed(self):
        self.assertEqual(verify.strip_urls("Xem https://evil.example/x?a=1 hoặc www.evil.example ngay."), "Xem  hoặc  ngay.")


class CheckTests(unittest.TestCase):
    def test_filled_answer_passes(self):
        self.assertEqual(codes("Tổng nợ {t1.tong_no_vnd} của {t1.so_khach} khách. Khách A quá hạn {t2.rows.0.qua_han_vnd}."), [])

    def test_typed_amounts_must_exist_in_tool_results(self):
        self.assertEqual(codes("Khách A nợ 350.000.000 đ."), [])
        self.assertEqual(codes("Khách B nợ 45000đ."), [])
        self.assertEqual(codes("Khách A nợ 351.000.000 đ."), ["unknown_amount"])
        self.assertEqual(codes("Khách A nợ 350000001 đồng."), ["unknown_amount"])

    def test_amount_without_currency_sign_is_still_checked(self):
        self.assertEqual(codes("Khách A còn 350000002."), ["unknown_number"])
        self.assertEqual(codes("Booking 123456789 của khách B, 1200 chuyến, 1.200 chuyến."), [])

    def test_units_exact_value_needs_no_khoang(self):
        self.assertEqual(codes("Khách A nợ 350 triệu."), [])
        self.assertEqual(codes("Khách B nợ 45k."), [])

    def test_rounded_amount_must_round_from_a_real_value_and_say_khoang(self):
        self.assertEqual(codes("Tổng nợ khoảng 1,2 tỷ."), [])
        self.assertEqual(codes("Quá hạn gần 120,5 triệu."), [])
        self.assertEqual(codes("Tổng nợ 1,2 tỷ."), ["rounded_without_approx"])
        self.assertEqual(codes("Tổng nợ khoảng 1,3 tỷ."), ["unknown_amount"])
        self.assertEqual(codes("Tổng nợ khoảng 2 tỷ."), ["unknown_amount"])

    def test_dates_times_years_and_small_counts_are_not_checked(self):
        self.assertEqual(codes("Dữ liệu lúc 10:05 ngày 22/11/2026, tháng 10/2026, năm 2026, 3 chuyến, 12 khách."), [])

    def test_words_that_start_like_units_are_not_amounts(self):
        self.assertEqual(codes("5 chuyến trả rồi, 10 khách, 2 khách trong số đó, 3 tiếng, 4 mục, 2 bảng giá."), [])

    def test_bare_small_number_without_a_count_word_is_blocked(self):
        self.assertEqual(codes("Khách A còn nợ 900."), ["unknown_number"])
        self.assertEqual(codes("Có 42 khách, tháng 10 có 7 chuyến."), [])

    def test_every_bad_number_is_reported_in_text_order(self):
        _text, problems = run("Khách A nợ 999.999 đ và khách B nợ 7 triệu.")
        self.assertEqual([p.code for p in problems], ["unknown_amount", "unknown_amount"])
        self.assertTrue(problems[0].text.endswith("999.999 đ") and problems[1].text.endswith("7 triệu"))


class AuditProbeTests(unittest.TestCase):
    """F1: số bịa viết theo mọi kiểu thường gặp đều bị chặn (trước 23/11 chỉ ba dòng đầu bị chặn)."""

    def test_fabricated_amounts_in_every_common_format_are_blocked(self):
        for draft, code in (
                ("Khách A còn nợ 555.000.000 đ", "unknown_amount"),
                ("Khách A còn nợ 555000000đ", "unknown_amount"),
                ("Khách A còn nợ 555 triệu", "unknown_amount"),
                ("Khách A còn nợ 555,000,000 đ", "unknown_amount"),
                ("Khách A còn nợ 555 000 000 đ", "unknown_amount"),
                ("Khách A còn nợ 555 trđ", "unknown_amount"),
                ("Khách A còn nợ 5,5 ty", "unknown_amount"),
                ("Khách A còn nợ 555 trieu", "unknown_amount"),
                ("Khách A còn nợ 1tỷ2", "unknown_amount"),
                ("Khách A còn nợ 1tr5", "unknown_amount"),
                ("Khách A còn nợ 555M", "unknown_amount"),
                ("Khách A còn nợ 1,5B", "unknown_amount"),
                ("Khách A còn nợ 555'000'000 đ", "unknown_amount"),
                ("Khách A còn nợ ５５５.０００.０００ đ", "unknown_amount"),
                ("Khách A còn nợ 555 vnđ", "unknown_amount"),
                ("Khách A còn nợ 555000 dong", "unknown_amount"),
                ("Khách A còn nợ khoảng 555 triệu", "unknown_amount"),
                ("Khách A còn nợ 0 đ, đã trả hết", "zero_typed"),
                ("Phí 900 đ", "unknown_amount"),
                ("Khách A còn nợ 11 đ", "unknown_amount"),
                ("Mã phiếu 4821", "unknown_number"),
                ("Khách A còn nợ năm trăm năm mươi lăm triệu đồng", "amount_in_words"),
                ("Quá hạn chiếm 80% tổng nợ", "unknown_percent"),
                ("Khách A còn nợ 999.999.999 đ", "unknown_amount")):
            with self.subTest(draft=draft):
                self.assertIn(code, codes(draft, PROBE))

    def test_zero_is_blocked_even_when_a_tool_returned_zero(self):
        self.assertEqual(codes("Khách B quá hạn 0 đ", PROBE), ["zero_typed"])
        self.assertEqual(codes("Khách B quá hạn {t2.qua_han_vnd}", PROBE), [])

    def test_a_date_right_before_a_unit_is_read_as_an_amount(self):
        self.assertIn("unknown_amount", codes("Khách A nợ 12/11 triệu", PROBE))

    def test_typed_sign_must_match(self):
        self.assertEqual(codes("Khách A đang dư -123.456.789 đ", PROBE), ["unknown_amount"])
        self.assertEqual(codes("Khách A dư -5.000 đ", [{"so_du_vnd": "-5000"}]), [])

    def test_real_values_typed_by_hand_still_pass(self):
        self.assertEqual(codes("Khách A còn nợ 123.456.789 đ, quá hạn 23.456.789 đ.", PROBE), [])

    def test_words_without_numbers_and_ratio_word_are_not_amounts(self):
        self.assertEqual(codes("Khách A đã trả hết nợ, không còn nợ đồng nào. Tỉ lệ thu tốt. Công ty khác.", PROBE), [])


class RoundingTests(unittest.TestCase):
    """F5: chiều của "hơn/gần" và độ chính xác của số làm tròn."""

    def test_direction_words(self):
        self.assertEqual(codes("Khách B nợ hơn 1 tỷ", PROBE), ["unknown_amount"])        # thật 0,987 tỷ: không "hơn"
        self.assertEqual(codes("Khách A nợ hơn 150 triệu", PROBE), ["unknown_amount"])
        self.assertEqual(codes("Khách A nợ gần 100 triệu", PROBE), ["unknown_amount"])
        self.assertEqual(codes("Khách A nợ hơn 123 triệu", PROBE), [])
        self.assertEqual(codes("Khách B nợ gần 988 triệu", PROBE), [])
        self.assertEqual(codes("Khách B nợ hơn 988 triệu", PROBE), ["unknown_amount"])
        self.assertEqual(codes("Khách A nợ gần 123 triệu", PROBE), ["unknown_amount"])

    def test_one_significant_digit_is_too_coarse(self):
        self.assertEqual(codes("Khách A nợ khoảng 0,1 tỷ", PROBE), ["rounded_too_coarse"])
        self.assertEqual(codes("Khách B nợ khoảng 1 tỷ", PROBE), ["rounded_too_coarse"])
        self.assertEqual(codes("Khách B nợ khoảng 0,99 tỷ", PROBE), [])
        self.assertEqual(codes("Khách A nợ khoảng 0,12 tỷ", PROBE), [])


class WrongPlaceTests(unittest.TestCase):
    """F2: số thật đặt sai sổ không qua được khi trộn nhiều sổ mà không ghi tên; chân câu trả lời ghi sổ của mọi số trích."""

    def test_amounts_of_two_books_need_their_names_in_the_same_sentence(self):
        self.assertEqual(model.mixed_books("Khách A còn nợ {t2.no_vnd}, khách B nợ {t1.no_vnd}.", PROBE),
                         ["nhieu_so_thieu_ten «{t2.no_vnd}»", "nhieu_so_thieu_ten «{t1.no_vnd}»"])
        self.assertEqual(model.mixed_books("{t1.ten} còn nợ {t1.no_vnd}. {t2.ten} còn nợ {t2.no_vnd}.", PROBE), [])
        self.assertEqual(model.mixed_books("Khách A còn nợ tổng {t1.qua_han_vnd}.", PROBE), [])

    def test_footer_names_the_book_of_a_cited_figure(self):
        tail = model.footer(PROBE, "Khách A còn nợ {t2.no_vnd}")
        self.assertIn("Sổ: KHACH B (mã 22) · số hiện tại", tail)
        self.assertNotIn("KHACH A", tail)


if __name__ == "__main__":
    unittest.main()
