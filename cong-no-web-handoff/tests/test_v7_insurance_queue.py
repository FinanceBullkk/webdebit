"""Giấy bảo hiểm Zalo (BAO-HIEM-ZALO-01, PR-1): bản chụp, ghép, Việc cần làm, Mở giấy. Dữ liệu giả."""
import copy
import hashlib
import http.client
import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "web"))
import v7_api_sheet  # noqa: E402
import v7_inbox  # noqa: E402
import v7_ledger_api as api  # noqa: E402
from v7_insurance_queue import (  # noqa: E402
    ContainerIndex,
    book_entries,
    cert_pdf,
    load_insurance_snapshot,
    orphan_items,
    project_insurance,
    rows_hash,
)

TYPES = [{"id": 1, "name": "Khác", "system_key": "other", "active": True},
         {"id": 2, "name": "Giảm trừ", "system_key": "discount", "active": True},
         {"id": 3, "name": "Phụ phí ban đầu", "system_key": "initial", "active": True},
         {"id": 7, "name": "Bảo hiểm", "system_key": None, "active": True}]
KHAC, BH = 1, 7
SOLD = "FAKEU0000001"


def line(line_id, type_id, amount):
    return {"id": line_id, "fee_type_id": type_id, "amount_vnd": str(amount), "note": None}


def trip(trip_id, container, booking="BKG001", lines=(), month="2026-11-01"):
    return {"id": trip_id, "container": container, "event_date": "2026-11-03", "unit_price_vnd": "1000000",
            "other_fee_vnd": None, "status": "confirmed", "month": month, "deleted": False,
            "booking": booking, "fee_lines": list(lines)}


def legacy(row_id, container, lines=(), counted="1500000", month="2026-10-01"):
    return {"id": row_id, "kind": "trip", "month": month, "fee_lines": list(lines),
            "current": {"container": container, "event_date": "2026-10-03", "unit_price_vnd": "1000000", "booking": "",
                        "counted_vnd": counted, "month": month, "deleted": False}}


def ledger(customer=7, trips=(), legacy_rows=()):
    return {"customer_id": customer, "version": 3, "today_month": "2026-11-01",
            "month_locks": [{"month": "2026-11-01", "locked": False}, {"month": "2026-10-01", "locked": True}],
            "trips": list(trips), "legacy_rows": list(legacy_rows)}


def cert(sha_char="a", container=SOLD, bookings=("BKG001",), amount=1234567, **extra):
    row = {"cert_no": f"GIAY-{sha_char}", "sha256": sha_char * 64, "container": container, "bookings": list(bookings),
           "amount_vnd": amount, "cert_premium_vnd": 1, "cert_vat_vnd": 1, "cert_total_vnd": amount,
           "containers_on_cert": 1, "depart_date": "2026-11-20", "issue_date": "2026-11-18", "status": "ok", "warnings": []}
    return row | extra


def snapshot(*rows):
    rows = sorted(rows, key=lambda r: (r["sha256"], r["cert_no"]))
    return {"schema_version": 1, "created_at": "2026-11-19T10:00:00+07:00", "amount_basis": "certificate total incl. VAT",
            "row_count": len(rows), "sha256": rows_hash(rows), "rows": rows}


def project(rows, *books, complete=True):
    index = ContainerIndex()
    results = [project_insurance(snapshot(*rows), book, TYPES, index) for book in books]
    if complete:
        index.mark_complete({book["customer_id"] for book in books})
        results = [project_insurance(snapshot(*rows), book, TYPES, index) for book in books]
    return index, results


def statuses(result):
    return [(i["cert_no"], i["status"]) for i in result["review"] + result["done"]]


class MatchTest(unittest.TestCase):
    def test_done_when_insurance_equals_certificate(self):
        book = ledger(trips=[trip(11, SOLD, lines=[line(1, BH, 1234567)])])
        _, (result,) = project([cert(bookings=(" bkg 001 ",))], book)   # booking viết thường, có khoảng trắng
        self.assertEqual(result["review"], [])
        self.assertEqual([(i["status"], i["match"], i["web_vnd"], i["cert_vnd"]) for i in result["done"]],
                         [("DONE", "booking", "1234567", "1234567")])
        self.assertEqual((result["done"][0]["target_kind"], result["done"][0]["target_id"]), ("trip", 11))

    def test_amount_diff_and_sum_of_several_insurance_lines(self):
        book = ledger(trips=[trip(11, SOLD, lines=[line(1, BH, 1000000)])])
        _, (result,) = project([cert()], book)
        self.assertEqual(statuses(result), [("GIAY-a", "AMOUNT_DIFF")])
        self.assertIn("1.000.000 đ", result["review"][0]["message"])
        book = ledger(trips=[trip(11, SOLD, lines=[line(1, BH, 1000000), line(2, BH, 234567)])])
        _, (result,) = project([cert()], book)
        self.assertEqual(statuses(result), [("GIAY-a", "DONE")])

    def test_classify_and_month_locked_show_in_review_with_hint(self):
        book = ledger(trips=[trip(11, SOLD, lines=[line(1, KHAC, 1234567), line(2, KHAC, 500000)])])
        _, (result,) = project([cert()], book)
        self.assertEqual(statuses(result), [("GIAY-a", "CLASSIFY")])
        self.assertIn("đổi loại thành Bảo hiểm bằng nút sửa loại phí, tổng không đổi", result["review"][0]["message"])
        locked = ledger(trips=[trip(11, SOLD, lines=[line(1, 3, 1234567)], month="2026-10-01")])   # Phụ phí ban đầu, tháng khóa
        _, (result,) = project([cert()], locked)
        self.assertEqual(statuses(result), [("GIAY-a", "MONTH_LOCKED")])
        self.assertIn("Tháng 10/2026 đang khóa", result["review"][0]["message"])
        self.assertEqual(result["review_count"], 1)

    def test_sheet_missing_and_two_equal_other_lines(self):
        book = ledger(trips=[trip(11, SOLD, lines=[line(1, KHAC, 999)])])
        _, (result,) = project([cert()], book)
        self.assertEqual(statuses(result), [("GIAY-a", "SHEET_MISSING")])
        self.assertIsNone(result["review"][0]["web_vnd"])
        book = ledger(trips=[trip(11, SOLD, lines=[line(1, KHAC, 1234567), line(2, KHAC, 1234567)])])
        _, (result,) = project([cert()], book)
        self.assertEqual(statuses(result), [("GIAY-a", "SHEET_MISSING")])
        self.assertIn("hai khoản cùng số", result["review"][0]["message"])

    def test_ambiguous_two_trips_or_two_certificates_one_trip(self):
        book = ledger(trips=[trip(11, SOLD), trip(12, SOLD)])
        _, (result,) = project([cert()], book)
        self.assertEqual(statuses(result), [("GIAY-a", "AMBIGUOUS")])
        book = ledger(trips=[trip(11, SOLD, lines=[line(1, BH, 1234567)])])
        _, (result,) = project([cert("a"), cert("b")], book)
        self.assertEqual(sorted(statuses(result)), [("GIAY-a", "AMBIGUOUS"), ("GIAY-b", "AMBIGUOUS")])

    def test_same_booking_in_two_books_is_ambiguous_in_each(self):
        _, results = project([cert()], ledger(7, [trip(11, SOLD)]), ledger(8, [trip(21, SOLD)]))
        self.assertEqual([statuses(r) for r in results], [[("GIAY-a", "AMBIGUOUS")]] * 2)

    def test_no_booking_and_not_found_go_to_work_list(self):
        book = ledger(trips=[trip(11, SOLD, booking="OTHER")])
        index, (result,) = project([cert("a", bookings=()), cert("b", container="FAKEU0000002"), cert("c")], book)
        self.assertEqual(statuses(result), [])
        items = orphan_items(snapshot(cert("a", bookings=()), cert("b", container="FAKEU0000002"), cert("c")), index)
        self.assertEqual([(i["cert_no"], i["status"]) for i in items["items"]],
                         [("GIAY-a", "NO_BOOKING"), ("GIAY-b", "NOT_FOUND"), ("GIAY-c", "NOT_FOUND")])
        self.assertEqual((items["count"], items["items"][0]["target_id"]), (3, ""))

    def test_cert_review_rules_and_info_warnings(self):
        book = ledger(trips=[trip(11, SOLD, lines=[line(1, BH, 1234567)])])
        rows = [cert("a", amount=None), cert("b", warnings=["totals differ"]), cert("c", status="review"),
                cert("d", warnings=["info: scan"])]
        index, (result,) = project(rows, book)
        self.assertEqual(statuses(result), [("GIAY-d", "DONE")])   # `info:` không chặn, vẫn hiện để xem
        self.assertEqual(result["done"][0]["warnings_info"], ["info: scan"])
        items = orphan_items(snapshot(*rows), index)["items"]
        self.assertEqual([(i["cert_no"], i["status"]) for i in items],
                         [("GIAY-a", "CERT_REVIEW"), ("GIAY-b", "CERT_REVIEW"), ("GIAY-c", "CERT_REVIEW")])
        self.assertIsNone(items[0]["cert_vnd"])
        self.assertEqual(items[1]["warnings"], ["totals differ"])

    def test_container_match_only_to_show(self):
        legacy_book = ledger(8, legacy_rows=[legacy(21, SOLD, lines=[line(5, BH, 1234567)])])
        no_booking = cert("a", bookings=())
        index, (result,) = project([no_booking, cert("b", bookings=("NOPE",))], legacy_book)
        self.assertEqual([(i["cert_no"], i["status"], i["match"], i["target_kind"]) for i in result["done"]],
                         [("GIAY-a", "DONE", "container", "legacy"), ("GIAY-b", "DONE", "container", "legacy")])
        self.assertEqual(orphan_items(snapshot(no_booking), index)["items"], [])
        # hai chuyến cùng container (hai sổ), một giấy khác số, Khác bằng số: giữ trạng thái cũ, không sinh CLASSIFY
        two = [ledger(7, [trip(11, SOLD, booking="X", lines=[line(1, BH, 1234567)])]),
               ledger(8, legacy_rows=[legacy(21, SOLD, lines=[line(5, BH, 1234567)])])]
        index, results = project([no_booking], *two)
        self.assertEqual([statuses(r) for r in results], [[], []])
        self.assertEqual(orphan_items(snapshot(no_booking), index)["items"][0]["status"], "NO_BOOKING")
        for lines in ([line(1, BH, 1)], [line(1, KHAC, 1234567)], []):
            index, (result,) = project([no_booking], ledger(trips=[trip(11, SOLD, booking="X", lines=lines)]))
            self.assertEqual(statuses(result), [])
            self.assertEqual(orphan_items(snapshot(no_booking), index)["items"][0]["status"], "NO_BOOKING")

    def test_container_match_waits_for_every_book_to_be_read(self):
        book = ledger(trips=[trip(11, SOLD, booking="X", lines=[line(1, BH, 1234567)])])
        index, (result,) = project([cert(bookings=())], book, complete=False)
        self.assertEqual(statuses(result), [])
        with self.assertRaises(ValueError):
            orphan_items(snapshot(cert(bookings=())), index)
        index.mark_complete({7, 8})   # sổ 8 chưa đọc
        self.assertFalse(index.complete)

    def test_legacy_row_keeps_counted_vnd_and_ledger_is_untouched(self):
        book = ledger(legacy_rows=[legacy(21, SOLD, lines=[line(5, BH, 1234567)], counted="2234567")])
        before = copy.deepcopy(book)
        (entry,) = book_entries(book, TYPES)
        self.assertEqual((entry["kind"], entry["counted_vnd"], entry["insured"], entry["booking"]), ("legacy", 2234567, 1234567, ""))
        project([cert(bookings=())], book)
        self.assertEqual(book, before)

    def test_replacing_a_book_drops_its_old_trips(self):
        index = ContainerIndex()
        index.replace(7, book_entries(ledger(trips=[trip(11, SOLD)]), TYPES))
        index.replace(7, book_entries(ledger(trips=[]), TYPES))
        self.assertEqual(index.lookup(SOLD), [])


class SnapshotTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "insurance-web.json"

    def write(self, data):
        self.path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    def test_valid_and_hash_is_stable(self):
        data = snapshot(cert("a"), cert("b"))
        self.write(data)
        self.assertEqual(load_insurance_snapshot(self.path)["sha256"], data["sha256"])
        self.assertEqual(load_insurance_snapshot(self.path)["sha256"], data["sha256"])
        self.assertEqual(rows_hash([{"b": "é", "a": 1}]), hashlib.sha256('[{"a":1,"b":"é"}]'.encode()).hexdigest())

    def test_wrong_version_hash_count_or_missing_file(self):
        good = snapshot(cert("a"))
        for name, bad in {"version": good | {"schema_version": 2}, "bool version": good | {"schema_version": True},
                          "hash": good | {"sha256": "0" * 64}, "count": good | {"row_count": 5},
                          "row": snapshot(cert("a") | {"sha256": "xyz"}), "rows": good | {"rows": [1], "row_count": 1}}.items():
            with self.subTest(name):
                self.write(bad)
                with self.assertRaises(ValueError):
                    load_insurance_snapshot(self.path)
        with self.assertRaises(ValueError):
            load_insurance_snapshot(Path(self.tmp.name) / "none.json")

    def test_ledger_read_attaches_insurance_or_marks_it_unavailable(self):
        class Runner:
            def run(self, function, payload, actor):
                if function == "get_fee_types":
                    return {"fee_types": TYPES}
                raise AssertionError(function)
        book = ledger(trips=[trip(11, SOLD)])
        self.write(snapshot(cert()))
        with patch.object(v7_api_sheet, "INSURANCE_SNAPSHOT_PATH", str(self.path)), patch.object(v7_api_sheet, "INSURANCE_INDEX", ContainerIndex()):
            result = v7_api_sheet.insurance_projection(Runner(), book, "fake")
        self.assertEqual((result["snapshot_sha256"], result["review_count"]), (snapshot(cert())["sha256"], 1))
        with patch.object(v7_api_sheet, "INSURANCE_SNAPSHOT_PATH", str(self.path.with_name("missing.json"))), \
                patch.object(v7_api_sheet, "sheet_projection", return_value={"items": []}), \
                patch.object(v7_api_sheet, "price_projection", return_value={"ready": []}):
            parts = v7_api_sheet.ledger_projections(Runner(), book, "fake")
        self.assertEqual(parts["insurance"], {"unavailable": True, "review": [], "done": [], "review_count": 0})


class OpenCertificateTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)
        self.pdf = b"%PDF-1.4 fake"
        self.sha = hashlib.sha256(self.pdf).hexdigest()
        (self.dir / "pdf").mkdir()
        (self.dir / "pdf" / f"{self.sha}.pdf").write_bytes(self.pdf)
        self.snap = snapshot(cert("a") | {"sha256": self.sha}, cert("b") | {"sha256": "b" * 64})
        (self.dir / "insurance-web.json").write_text(json.dumps(self.snap), encoding="utf-8")
        (self.dir / "pdf" / f"{'b' * 64}.pdf").write_bytes(b"other bytes")   # có trong bản chụp nhưng file băm sai

    def test_only_known_hash_with_matching_file(self):
        directory = self.dir / "pdf"
        self.assertEqual(cert_pdf(self.snap, self.sha, directory), self.pdf)
        for sha in ("c" * 64, "b" * 64, "../" + self.sha, self.sha.upper(), "", self.sha[:-1], "d" * 64):
            with self.subTest(sha=sha), self.assertRaises(FileNotFoundError):
                cert_pdf(self.snap, sha, directory)

    def test_route_headers_and_refusals(self):
        class Trial(api.Handler):
            default_actor = "insurance-test"
            dev_actor_mode = True
        Trial.runner = object()
        server = api.ThreadingHTTPServer(("127.0.0.1", 0), Trial)
        Trial.port = server.server_port
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        self.addCleanup(lambda: (server.shutdown(), worker.join(timeout=3), server.server_close()))

        def get(path):
            conn = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=10)
            conn.request("GET", path)
            response = conn.getresponse()
            body = response.read()
            conn.close()
            return response, body
        with patch.object(v7_api_sheet, "INSURANCE_SNAPSHOT_PATH", str(self.dir / "insurance-web.json")):
            response, body = get(api.v7_insurance_queue.CERT_PREFIX + self.sha)
            self.assertEqual((response.status, body), (200, self.pdf))
            self.assertEqual(response.getheader("Content-Type"), "application/pdf")
            self.assertEqual(response.getheader("X-Content-Type-Options"), "nosniff")
            self.assertTrue(response.getheader("Content-Disposition").startswith("inline"))
            for path in ("c" * 64, "b" * 64, "..%2F" + self.sha, "xyz", self.sha + "?x=1"):
                with self.subTest(path=path):
                    refused, _ = get(api.v7_insurance_queue.CERT_PREFIX + path)
                    self.assertIn(refused.status, (404, 422))   # 422: có query; 404: sha256 lạ, hỏng hoặc không phải hex
        with patch.object(v7_api_sheet, "INSURANCE_SNAPSHOT_PATH", str(self.dir / "missing.json")):
            self.assertEqual(get(api.v7_insurance_queue.CERT_PREFIX + self.sha)[0].status, 404)


class WorkListTest(unittest.TestCase):
    def test_inbox_view_carries_the_group_or_marks_it_unavailable(self):
        def view(insurance):
            box = v7_inbox.Inbox(lambda runner, book, actor: book, lambda: (), insurance=insurance)
            box.computed_at = 1.0
            with patch.object(box, "tick", return_value=True):
                return box.view(object())["insurance"]
        group = {"snapshot_sha256": "a" * 64, "items": [{"cert_no": "G"}], "count": 1}
        self.assertEqual(view(lambda: group), group)

        def broken():
            raise ValueError("Insurance container index incomplete")
        self.assertEqual(view(broken), {"unavailable": True, "items": [], "count": 0})
        self.assertEqual(view(None), {"unavailable": True, "items": [], "count": 0})


if __name__ == "__main__":
    unittest.main()
