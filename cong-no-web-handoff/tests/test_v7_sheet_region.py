"""KIEM-TAB-01 3c: vùng ô của Sheet dựng lại cho màn "Sheet cần sửa". Sheets API giả, tên và số bịa; không gọi mạng, không openssl."""
import base64
import io
import json
import shutil
import subprocess
import sys
import tempfile
import unicodedata
import unittest
import urllib.parse
from datetime import date
from pathlib import Path
from typing import ClassVar
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parents[1] / "web"))
import v7_api_doi_chieu as api
import v7_sheet_region as region
from v7_api_validate import ApiError

SHEET = "S" * 30


def base64_decode(part):
    return base64.urlsafe_b64decode(part + "=" * (-len(part) % 4))


def base64_encode(raw_bytes):
    return base64.urlsafe_b64encode(raw_bytes).rstrip(b"=").decode()
GID = 777


def serial(year, month, day):
    return (date(year, month, day) - region.EPOCH).days


def cell(text="", formula=None, bg=None, bold=False, kind=None, number=None):
    value = {"formattedValue": text} if text else {}
    if formula:
        value["userEnteredValue"] = {"formulaValue": formula}
    fmt = {}
    if bg:
        fmt["backgroundColor"] = {"red": bg[0], "green": bg[1], "blue": bg[2]}
    if bold:
        fmt["textFormat"] = {"bold": True}
    if kind:
        fmt["numberFormat"] = {"type": kind}
    if fmt:
        value["effectiveFormat"] = fmt
    if number is not None:
        value["effectiveValue"] = {"numberValue": number}
    return value


def raw(first=8, cols=18, rows=15, cells=None, merges=(), extra=()):
    """Phản hồi spreadsheets.get cho một vùng: cells {(dòng, cột 1-based): ô}."""
    cells = cells or {}
    data = [{"startRow": first - 1, "columnMetadata": [{"pixelSize": 80}] * cols, "rowMetadata": [{"pixelSize": 21}] * rows,
             "rowData": [{"values": [cells.get((first + r, c + 1), {}) for c in range(cols)]} for r in range(rows)]}]
    for text, formula in extra:
        data.append({"rowData": [{"values": [cell(text, formula)]}]})
    return {"sheets": [{"properties": {"sheetId": GID, "title": "T"}, "merges": list(merges), "data": data}]}


class Opener:
    """Mở được ba địa chỉ: token, tên tab (`sheets.properties`) và spreadsheets.get; đếm số lần gọi."""
    TITLES = ("T", "Tab A", "Tab B", "KHACH A")

    def __init__(self, payload, fail=False, titles=None):
        self.payload, self.fail, self.calls, self.timeouts, self.requests = payload, fail, [], [], []
        self.titles = list(self.TITLES if titles is None else titles)

    def __call__(self, request, timeout=0):
        self.calls.append(request.full_url)
        self.timeouts.append(timeout)
        self.requests.append(request)
        if self.fail:
            raise OSError("mạng giả hỏng")
        if request.full_url == region.TOKEN_URL:
            body = {"access_token": "tok"}
        elif "includeGridData" not in request.full_url:
            body = {"sheets": [{"properties": {"title": title, "sheetId": GID}} for title in self.titles]}
        else:
            body = self.payload

        class Response:
            def __enter__(self_):
                return self_

            def __exit__(self_, *_):
                return False

            def read(self_):
                return json.dumps(body).encode()
        return Response()


class Env(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.keys_path = Path(folder.name) / "reader.json"
        self.keys_path.write_text(json.dumps({"type": "service_account", "client_email": "x@example.test",
                                              "private_key": "-----BEGIN-----\nk\n-----END-----"}), encoding="utf-8")
        env = patch.dict("os.environ", {"WEBDEBIT_SHEET_ID": SHEET, "WEBDEBIT_GOOGLE_CREDENTIALS": str(self.keys_path)})
        env.start()
        self.addCleanup(env.stop)
        self.signer = patch.object(region.subprocess, "run", return_value=type("R", (), {"stdout": b"sig"})())
        self.signer.start()
        self.addCleanup(self.signer.stop)
        region._cache.clear()
        region._titles.clear()
        region._token.update(value=None, until=0.0)


class PureTests(unittest.TestCase):
    def test_column_letters_both_ways(self):
        for number, letters in ((1, "A"), (26, "Z"), (27, "AA"), (45, "AS")):
            self.assertEqual((region.column_letter(number), region.column_index(letters)), (letters, number))
        self.assertEqual(region.split_cell("N45"), (45, 14))
        with self.assertRaises(ValueError):
            region.split_cell("n45")

    def test_bounds_are_a_small_window_around_the_cell(self):
        self.assertEqual(region.region_bounds([45], ["N45"]), (38, 1, 52, 18))
        self.assertEqual(region.region_bounds([3], ["B3"]), (1, 1, 15, 18))
        self.assertEqual(region.region_bounds([20], ["T20"])[3], 20)   # cột xa thì mở rộng, không quá 20
        with self.assertRaises(ValueError):
            region.region_bounds([], [])

    def test_date_flag_only_when_stored_is_outside_the_block_and_swapping_lands_in_it(self):
        molly = {"kind": "DATE", "v": "11/10/2025", "serial": serial(2025, 11, 10)}   # hiện 11/10, Sheet hiểu 10 tháng 11; khối là tháng 10
        self.assertTrue(region.date_swap(molly, "2025-10"))
        self.assertIn("Ô hiện 11/10/2025 nhưng Sheet hiểu là ngày 10/11/2025, ngoài tháng 10 của khối", region.date_swap_text(molly, "2025-10"))
        d17 = {"kind": "DATE", "v": "10/26/2026", "serial": serial(2026, 10, 26)}    # ngày 26 > 12, đúng tháng khối: chỉ hiển thị kiểu tháng/ngày
        self.assertFalse(region.date_swap(d17, "2026-10"))
        self.assertFalse(region.date_swap({"kind": "DATE", "v": "11/10/2025", "serial": serial(2025, 10, 11)}, "2025-10"))   # lưu trong khối
        self.assertFalse(region.date_swap(molly, "2025-09"))   # đảo ra tháng 10, không phải tháng 9 của khối
        self.assertFalse(region.date_swap({"kind": "DATE", "v": "26/11/2025", "serial": serial(2025, 11, 26)}, "2025-10"))   # ngày > 12 không đảo được
        self.assertFalse(region.date_swap({"kind": "DATE", "v": "11/10/2024", "serial": serial(2024, 11, 10)}, "2025-10"))   # khác năm
        self.assertFalse(region.date_swap(molly, None))     # không biết tháng khối thì không đoán
        self.assertFalse(region.date_swap({"kind": "DATE", "v": "11/10/2025"}, "2025-10"))   # không đọc được ngày lưu thì bỏ cờ
        self.assertFalse(region.date_swap({"kind": "NUMBER", "v": "x", "serial": serial(2025, 11, 10)}, "2025-10"))

    def test_shape_ignores_row_numbers_only(self):
        self.assertEqual(region.shape("=SUM(M692:M847)"), region.shape("=sum( M10:M99 )"))
        self.assertNotEqual(region.shape("=SUM(M692:M847)"), region.shape("=SUM(N692:N847)"))
        self.assertIsNone(region.shape(None))

    def test_sample_for_a_typed_zero_a_blank_and_a_different_formula(self):
        others = [{"f": "=N40+K45-M45"}, {"f": "=N90+K95-M95"}, {"f": None, "v": "5"}]
        self.assertEqual(region.chain_sample({"f": None, "v": "0"}, others), {"sample": "=N40+K45-M45", "current": "0", "has_formula": False})
        self.assertIsNone(region.chain_sample({"f": None, "v": ""}, others)["current"])
        self.assertEqual(region.chain_sample({"f": "=N45+K45", "v": "1"}, others)["current"], "=N45+K45")
        self.assertIsNone(region.chain_sample({"f": "=N200+K205-M205", "v": "1"}, others))   # cùng dáng mẫu
        self.assertIsNone(region.chain_sample({"f": None, "v": "0"}, [{"f": None, "v": "1"}]))   # không có mẫu thì không nói


class BuildTests(unittest.TestCase):
    def test_values_background_merges_widths_and_collapsed_empty_columns(self):
        cells = {(8, 1): cell("Ô A8", bg=(1, 0.9, 0.9), bold=True), (8, 2): cell("B8"), (9, 2): cell("", formula="=B8*2"), (10, 8): cell("H10")}
        merges = [{"startRowIndex": 7, "endRowIndex": 8, "startColumnIndex": 0, "endColumnIndex": 2},   # trong vùng
                  {"startRowIndex": 300, "endRowIndex": 301, "startColumnIndex": 0, "endColumnIndex": 2}]   # ngoài vùng
        built = region.build_region(raw(cells=cells, merges=merges), 8, 1, 22, 18, [])
        self.assertEqual((built["sheet_id"], built["first_row"], built["col_letters"][:3]), (GID, 8, ["A", "B", "C"]))
        self.assertEqual((built["cells"][0][0]["v"], built["cells"][0][0]["bg"], built["cells"][0][0]["b"]), ("Ô A8", "#ffe6e6", True))
        self.assertEqual(built["cells"][1][1]["f"], "=B8*2")
        self.assertEqual(built["merges"], [{"r1": 0, "c1": 0, "r2": 1, "c2": 2}])
        self.assertEqual(built["widths"][0], 80)
        collapsed = [g["cols"] for g in built["column_groups"] if g["collapsed"]]
        self.assertEqual(collapsed, [[2, 3, 4, 5, 6], [8, 9, 10, 11, 12, 13, 14, 15, 16, 17]])   # C–G và I–R: cột trống liên tiếp thành "…"
        self.assertTrue(all(not g["collapsed"] for g in built["column_groups"] if g["cols"] in ([0], [1], [7])))

    def test_marked_cells_stay_visible_even_in_an_empty_column(self):
        built = region.build_region(raw(), 8, 1, 22, 18, [{"cell": "D10", "level": "error", "text": "sai"}])
        self.assertEqual([(m["row"], m["col"], m["level"]) for m in built["marks"]], [(2, 3, "error")])
        self.assertIn([3], [g["cols"] for g in built["column_groups"] if not g["collapsed"]])

    def test_swapped_date_becomes_a_suspect_mark_without_help_from_findings(self):
        cells = {(42, 4): cell("11/10/2025", kind="DATE", number=serial(2025, 11, 10)), (43, 4): cell("10/26/2025", kind="DATE", number=serial(2025, 10, 26))}
        built = region.build_region(raw(first=36, cells=cells), 36, 1, 50, 18, [], "2025-10")
        self.assertEqual([(m["cell"], m["level"]) for m in built["marks"]], [("D42", "suspect")])   # D42 kiểu MOLLY có cờ, D43 kiểu 10/26 không
        self.assertIn("ngoài tháng 10 của khối", built["marks"][0]["text"])
        self.assertEqual(region.build_region(raw(first=36, cells=cells), 36, 1, 50, 18, [])["marks"], [])   # không có tháng khối thì không cờ


class FetchTests(Env):
    def test_reads_once_per_minute_with_the_fields_asked_for_and_read_at(self):
        opener = Opener(raw())
        first = region.fetch_region("Tab A", 8, 1, 22, 18, opener=opener, now=1_800_000_000)
        again = region.fetch_region("Tab A", 8, 1, 22, 18, opener=opener, now=1_800_000_030)
        self.assertIs(first, again)
        self.assertEqual(len(opener.calls), 3)   # một lần token, một lần tên tab, một lần dữ liệu
        url = opener.calls[2]
        self.assertIn("includeGridData=true", url)
        self.assertIn("formattedValue", url)
        self.assertIn("A8%3AR22", url)
        self.assertRegex(first["read_at"], r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\+07:00$")
        region.fetch_region("Tab A", 8, 1, 22, 18, opener=opener, now=1_800_000_100)   # quá 60 giây: đọc lại
        self.assertEqual(len(opener.calls), 4)   # token và tên tab còn hạn nên chỉ đọc lại dữ liệu

    def test_extra_ranges_come_back_apart(self):
        opener = Opener(raw(extra=[("5", "=N1+K1"), ("7", None)]))
        got = region.fetch_region("T", 8, 1, 22, 18, ["N40:N40", "N90:N90"], opener=opener, now=1_800_000_000)
        self.assertEqual(len(got["extra"]), 2)
        self.assertIn("N40%3AN40", opener.calls[2])

    def test_failures_are_503_never_a_stack_trace(self):
        with self.assertRaises(ApiError) as caught:
            region.fetch_region("T", 8, 1, 22, 18, opener=Opener(raw(), fail=True), now=1_800_000_000)
        self.assertEqual((caught.exception.status, caught.exception.code), (503, "SHEET_REGION_UNAVAILABLE"))
        with patch.dict("os.environ", {"WEBDEBIT_SHEET_ID": ""}), self.assertRaises(ApiError) as missing:
            region.fetch_region("T", 8, 1, 22, 18, opener=Opener(raw()), now=1_800_000_000)
        self.assertEqual(missing.exception.status, 503)


def ranges_of(url):
    return urllib.parse.parse_qs(urllib.parse.urlparse(url).query)["ranges"]


class TabTitleTests(Env):
    """Tên tab trong phát hiện bị cắt dấu cách (và có thể khác dạng Unicode) so với tên thật; range phải dùng tên thật (sự cố 16/11)."""

    def read(self, tab, titles, **kwargs):
        opener = Opener(raw(), titles=titles)
        out = region.fetch_region(tab, 38, 1, 52, 18, opener=opener, now=1_800_000_000, **kwargs)
        return opener, out

    def test_trailing_space_in_the_real_title_is_kept_in_the_range(self):
        opener, _ = self.read("MOLLY TÂN TỶ-", ["KK - A TANK 402- SR", "MOLLY TÂN TỶ- "])
        self.assertEqual(ranges_of(opener.calls[2]), ["'MOLLY TÂN TỶ- '!A38:R52"])

    def test_nfd_and_nfc_spellings_both_reach_the_real_title(self):
        nfc, nfd = (unicodedata.normalize(form, "MOLLY TÂN TỶ- ") for form in ("NFC", "NFD"))
        self.assertNotEqual(nfc, nfd)
        for asked, real in ((nfd.strip(), nfc), (nfc.strip(), nfd)):
            with self.subTest(real=real == nfd):
                region._cache.clear()
                region._titles.clear()
                opener, _ = self.read(asked, [real])
                self.assertEqual(ranges_of(opener.calls[-1]), [f"'{real}'!A38:R52"])

    def test_extra_ranges_use_the_real_title_and_a_quote_in_it_is_doubled(self):
        opener = Opener(raw(extra=[("5", "=N1")]), titles=["O'HARA "])
        region.fetch_region("O'HARA", 8, 1, 22, 18, ["N40:N40"], opener=opener, now=1_800_000_000)
        self.assertEqual(ranges_of(opener.calls[2]), ["'O''HARA '!A8:R22", "'O''HARA '!N40:N40"])

    def test_exact_title_wins_over_a_look_alike_and_an_ambiguous_one_is_refused(self):
        opener, _ = self.read("MOLLY", ["MOLLY ", "MOLLY"])
        self.assertEqual(ranges_of(opener.calls[2]), ["'MOLLY'!A38:R52"])
        region._cache.clear()
        region._titles.clear()
        with self.assertRaises(ApiError) as caught:
            self.read("MOLLY  ", ["MOLLY ", " MOLLY"])
        self.assertEqual((caught.exception.status, caught.exception.code), (503, "SHEET_REGION_UNAVAILABLE"))

    def test_unknown_tab_is_503_and_reads_no_cells(self):
        opener = Opener(raw(), titles=["KHAC"])
        with self.assertRaises(ApiError) as caught:
            region.fetch_region("TAB MOI", 8, 1, 22, 18, opener=opener, now=1_800_000_000)
        self.assertEqual(caught.exception.status, 503)
        self.assertFalse(any("includeGridData" in url for url in opener.calls))

    def test_titles_are_read_once_and_a_new_tab_triggers_one_more_read(self):
        opener = Opener(raw(), titles=["T", "KHACH A"])
        region.fetch_region("T", 8, 1, 22, 18, opener=opener, now=1_800_000_000)
        region.fetch_region("KHACH A", 8, 1, 22, 18, opener=opener, now=1_800_000_010)
        self.assertEqual(sum("includeGridData" not in url and url != region.TOKEN_URL for url in opener.calls), 1)
        opener.titles.append("MOI ")
        region.fetch_region("MOI", 8, 1, 22, 18, opener=opener, now=1_800_000_020)   # chưa có trong danh sách nhớ: đọc lại một lần
        self.assertEqual(sum("includeGridData" not in url and url != region.TOKEN_URL for url in opener.calls), 2)
        self.assertEqual(ranges_of(opener.calls[-1]), ["'MOI '!A8:R22"])

    def test_endpoint_opens_the_right_gid_for_a_tab_with_a_trailing_space(self):
        finding = {"tab": "MOLLY TÂN TỶ-", "kind": "row_shift", "level": "error", "month": "2026-10", "rows": [45], "cells": ["B45"],
                   "message": "x", "fix": "y"}
        health = {"status": "broken", "findings": [finding]}
        opener = Opener(raw(), titles=["MOLLY TÂN TỶ- "])
        with patch.object(api, "_read", return_value=({}, {}, {}, [], 0, [], health)):
            out = api.region("customer=162&finding=0", object(), "t", opener=opener, now=1_800_000_000)
        self.assertEqual(ranges_of(opener.calls[2])[0], "'MOLLY TÂN TỶ- '!A38:R52")
        self.assertTrue(out["open_url"].endswith(f"#gid={GID}&range=B45"))


class SigningAndLogTests(Env):
    def test_the_jwt_is_built_and_signed_with_the_key_and_the_token_is_kept_until_it_expires(self):
        seen = {}

        def fake_run(argv, input=None, **kwargs):
            seen.update(argv=argv, signing_input=input, kwargs=kwargs)
            return type("R", (), {"stdout": b"sig"})()
        opener = Opener(raw())
        with patch.object(region.subprocess, "run", fake_run):
            token = region._access_token(str(self.keys_path), opener, 1_800_000_000)
            again = region._access_token(str(self.keys_path), opener, 1_800_000_500)
            later = region._access_token(str(self.keys_path), opener, 1_800_000_000 + region.TOKEN_SECONDS + 1)
        self.assertEqual((token, again, later), ("tok", "tok", "tok"))
        self.assertEqual(len(opener.calls), 2)   # lần hai dùng lại token, quá hạn mới xin lại
        self.assertEqual(seen["argv"][:4], ["openssl", "dgst", "-sha256", "-sign"])
        header, claims = (json.loads(base64_decode(part)) for part in seen["signing_input"].decode().split("."))
        self.assertEqual(header, {"alg": "RS256", "typ": "JWT"})
        self.assertEqual((claims["iss"], claims["scope"], claims["aud"], claims["exp"] - claims["iat"]),
                         ("x@example.test", region.SCOPE, region.TOKEN_URL, 3600))
        self.assertTrue(region.SCOPE.endswith("spreadsheets.readonly"))   # chỉ đọc
        body = opener.requests[0].data.decode()
        self.assertIn("grant_type=urn%3Aietf%3Aparams%3Aoauth%3Agrant-type%3Ajwt-bearer", body)
        self.assertTrue(body.split("assertion=")[1].endswith("." + base64_encode(b"sig")))

    @unittest.skipUnless(shutil.which("openssl"), "openssl không có trên máy này")
    def test_the_signature_verifies_against_the_public_key_of_a_throwaway_key(self):
        self.signer.stop()   # dùng openssl thật; subprocess.run đang bị thay trong setUp
        self.signer.start()
        self.signer.stop()
        folder = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, folder, True)
        key, public = folder / "k.pem", folder / "p.pem"
        subprocess.run(["openssl", "genrsa", "-out", str(key), "2048"], check=True, capture_output=True)
        subprocess.run(["openssl", "rsa", "-in", str(key), "-pubout", "-out", str(public)], check=True, capture_output=True)
        data = b"header.claims"
        signature = region._sign(data, key.read_text(encoding="utf-8"))
        (folder / "s.bin").write_bytes(signature)
        (folder / "d.bin").write_bytes(data)
        checked = subprocess.run(["openssl", "dgst", "-sha256", "-verify", str(public), "-signature", str(folder / "s.bin"), str(folder / "d.bin")],
                                 capture_output=True, text=True, check=False)
        self.assertIn("Verified OK", checked.stdout)

    def test_google_calls_time_out_in_8_seconds(self):
        opener = Opener(raw())
        region.fetch_region("T", 8, 1, 22, 18, opener=opener, now=1_800_000_000)
        self.assertEqual(set(opener.timeouts), {8})

    def test_the_log_has_tab_range_and_codes_but_never_cell_text(self):
        hidden_text = "NOI-DUNG-O-BI-MAT"
        opener = Opener(raw(cells={(8, 1): cell(hidden_text, formula="=SECRET(A1)")}))
        stderr = io.StringIO()
        with patch.object(region.sys, "stderr", stderr):
            region.fetch_region("Tab A", 8, 1, 22, 18, opener=opener, now=1_800_000_000)
            with self.assertRaises(ApiError):
                region.fetch_region("Tab B", 8, 1, 22, 18, opener=Opener(raw(), fail=True), now=1_800_000_000 + 10_000)
        text = stderr.getvalue()
        self.assertIn("Tab A", text)
        self.assertIn("A8:R22", text)
        self.assertIn("lỗi", text)
        self.assertNotIn(hidden_text, text)
        self.assertNotIn("SECRET", text)
        self.assertNotIn("PRIVATE", text.upper().replace("PRIVATE_KEY_ID", ""))


class EndpointTests(Env):
    FINDINGS: ClassVar[list] = [
        {"tab": "KHACH A", "kind": "row_shift", "level": "error", "month": "2026-10", "rows": [15, 16], "cells": ["B15", "F16"],
         "message": "Tiền lệch một dòng.", "fix": "Đưa tiền lên."},
        {"tab": "KHACH A", "kind": "chain_break", "level": "error", "month": "2026-10", "rows": [45], "cells": ["N45"],
         "other_cells": ["N10", "N90"], "message": "Số cuối tháng 10 lệch.", "fix": "Điền công thức."},
        {"tab": "KHACH A", "kind": "MISSING_MONTH", "level": "error", "count": 1},
    ]

    def call(self, query, payload=None, findings=None):
        health = {"status": "broken", "findings": list(self.FINDINGS if findings is None else findings)}
        with patch.object(api, "_read", return_value=({}, {}, {}, [], 0, [], health)):
            return api.region(query, object(), "tester", opener=Opener(payload or raw()), now=1_800_000_000)

    def test_row_shift_region_marks_both_cells_and_opens_the_right_cell(self):
        out = self.call("customer=7&finding=0")
        self.assertEqual((out["kind"], out["finding"], out["region"]["sheet_id"]), ("row_shift", 0, GID))
        self.assertEqual(sorted(m["cell"] for m in out["region"]["marks"]), ["B15", "F16"])
        self.assertEqual(out["open_url"], f"https://docs.google.com/spreadsheets/d/{SHEET}/edit#gid={GID}&range=B15")
        self.assertIsNone(out["sample"])
        self.assertTrue(out["read_at"])

    def test_chain_break_shows_the_sample_formula_of_the_other_blocks(self):
        out = self.call("customer=7&finding=1", raw(first=38, cells={(45, 14): cell("0")}, extra=[("5", "=N5+K10-M10"), ("6", "=N85+K90-M90")]))
        self.assertEqual(out["sample"], {"sample": "=N5+K10-M10", "current": "0", "has_formula": False})
        self.assertEqual(out["region"]["first_row"], 38)

    def test_query_must_be_exactly_customer_and_finding_numbers(self):
        for query in ("", "customer=7", "finding=0", "customer=7&finding=0&a1=B2", "customer=x&finding=0", "customer=7&finding=-1",
                      "customer=7&finding=0&finding=1", "customer=0&finding=0"):
            with self.subTest(query=query), self.assertRaises(ApiError) as caught:
                self.call(query)
            self.assertEqual(caught.exception.status, 422)

    def test_unknown_finding_and_finding_without_a_cell_are_404(self):
        for query, code in (("customer=7&finding=9", "FINDING_NOT_FOUND"), ("customer=7&finding=2", "NO_REGION")):
            with self.subTest(query=query), self.assertRaises(ApiError) as caught:
                self.call(query)
            self.assertEqual((caught.exception.status, caught.exception.code), (404, code))

    def test_fresh_skips_the_cache_and_only_the_value_one_is_allowed(self):
        opener = Opener(raw())
        health = {"status": "broken", "findings": list(self.FINDINGS)}
        with patch.object(api, "_read", return_value=({}, {}, {}, [], 0, [], health)):
            api.region("customer=7&finding=0", object(), "t", opener=opener, now=1_800_000_000)
            api.region("customer=7&finding=0", object(), "t", opener=opener, now=1_800_000_010)
            self.assertEqual(len(opener.calls), 3)   # token + tên tab + dữ liệu, lần hai từ cache
            api.region("customer=7&finding=0&fresh=1", object(), "t", opener=opener, now=1_800_000_020)
            self.assertEqual(len(opener.calls), 4)   # đọc lại dữ liệu, token và tên tab còn hạn
            for query in ("customer=7&finding=0&fresh=0", "customer=7&finding=0&fresh="):
                with self.assertRaises(ApiError):
                    api.region(query, object(), "t", opener=opener, now=1_800_000_030)

    def test_the_sheet_id_only_leaves_inside_the_open_link(self):
        self.assertEqual(json.dumps(self.call("customer=7&finding=0")).count(SHEET), 1)


if __name__ == "__main__":
    unittest.main()
