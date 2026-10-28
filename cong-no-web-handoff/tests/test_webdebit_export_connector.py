import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "tools"))
import webdebit_export_connector as connector


class WebdebitExportConnectorTests(unittest.TestCase):
    def test_parse_normalizes_date_and_container(self):
        rows = connector.parse_values([
            list(connector.HEADERS),
            [" ab c u 1234567 ", " WH ", "01/10/2026", "Kho", "Port"],
        ])
        self.assertEqual(rows[0]["container"], "ABCU1234567")
        self.assertEqual(rows[0]["event_date"], "2026-10-01")
        self.assertEqual(rows[0]["status"], "READY")

    def test_missing_field_and_duplicate_are_retained(self):
        values = [list(connector.HEADERS),
                  ["ABCU1234567", "WH", "01/10/2026", "", "Port"],
                  ["ABCU1234567", "WH", "01/10/2026", "Kho", "Port"]]
        rows = connector.parse_values(values)
        self.assertEqual([row["status"] for row in rows], ["INVALID", "READY"])
        values.append(["ABCU1234567", "WH", "01/10/2026", "Kho", "Port"])
        self.assertEqual(connector.parse_values(values)[2]["status"], "DUPLICATE")

    def test_read_export_uses_authorization_and_returns_hash(self):
        captured = {}

        class Response:
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def read(self): return json.dumps({"values": [list(connector.HEADERS), ["ABCU1234567", "WH", "01/10/2026", "Kho", "Port"]]}).encode()

        def opener(request, timeout):
            captured["authorization"] = request.get_header("Authorization")
            captured["url"] = request.full_url
            self.assertEqual(timeout, 20)
            return Response()

        result = connector.read_export("sheet-id", "token", opener)
        self.assertEqual(captured["authorization"], "Bearer token")
        self.assertIn("WEBDEBIT_EXPORT!A1:E20000", captured["url"])
        self.assertEqual(result["row_count"], 1)
        self.assertEqual(len(result["sha256"]), 64)

    def test_snapshot_hash_detects_distinct_invalid_source_dates(self):
        class Response:
            def __init__(self, values): self.values = values
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def read(self): return json.dumps({"values": self.values}).encode()

        def read(date_text):
            values = [list(connector.HEADERS), ["ABCU1234567", "WH", date_text, "Kho", "Port"]]
            return connector.read_export("sheet-id", "token", lambda *_args, **_kwargs: Response(values))

        first, second = read("31/02/2026"), read("32/02/2026")
        self.assertIsNone(first["rows"][0]["event_date"])
        self.assertEqual(first["rows"][0]["source_date"], "31/02/2026")
        self.assertNotEqual(first["sha256"], second["sha256"])

    def test_ready_row_maps_to_paste_shape_and_review_rows_do_not(self):
        rows = connector.parse_values([
            list(connector.HEADERS),
            ["ABCU1234567", "WH", "01/10/2026", "Kho", "Port"],
            ["", "WH", "01/10/2026", "Kho", "Port"],
            ["ABCU1234567", "WH", "01/10/2026", "Kho", "Port"],
            ["WXYZ7654321", "WH", "02/10/2026", "Kho", "Port"],
        ])
        self.assertEqual([row["status"] for row in rows], ["DUPLICATE", "INVALID", "DUPLICATE", "READY"])
        with self.assertRaisesRegex(ValueError, "READY"):
            connector.to_paste_trip(rows[0])
        self.assertEqual(connector.to_paste_trip(rows[3]), {
            "container": "WXYZ7654321",
            "carrier": "WH",
            "from": "Kho",
            "to": "Port",
            "date": "02/10/2026",
            "src": "WEBDEBIT_EXPORT",
            "note": "WEBDEBIT_EXPORT row 5",
        })
        with self.assertRaisesRegex(ValueError, "READY"):
            connector.to_paste_trip(rows[1])
        preview = connector.paste_preview({"sha256": "fixed", "rows": rows, "row_count": 4})
        self.assertEqual(preview["sha256"], "fixed")
        self.assertTrue(all(row["candidate"] is None for row in preview["rows"][:3]))
        self.assertEqual(preview["rows"][3]["candidate"]["container"], "WXYZ7654321")

    def test_booking_join_adds_customer_and_booking_but_keeps_unmatched_for_review(self):
        exports = connector.parse_values([
            list(connector.HEADERS),
            ["ABCU1234567", "WH", "01/10/2026", "Kho", "Port"],
            ["WXYZ7654321", "WH", "02/10/2026", "Kho", "Port"],
        ])
        bookings = connector.parse_booking_values([
            list(connector.BOOKING_HEADERS),
            ["ABCU1234567", "Khách A", "01/10/2026", "BK001", "TAB", "7", "Gốc", "Ship", "WH", "Kho", "Port"],
        ])
        rows = connector.merge_booking_rows(exports, bookings)
        self.assertEqual((rows[0]["status"], rows[0]["booking"], rows[0]["customer_name"]), ("READY", "BK001", "Khách A"))
        self.assertEqual(rows[0]["shipper"], "Ship")
        self.assertEqual(connector.to_paste_trip(rows[0])["booking"], "BK001")
        self.assertEqual(rows[1]["status"], "NO_BOOKING_MATCH")
        with self.assertRaisesRegex(ValueError, "READY"):
            connector.to_paste_trip(rows[1])
        self.assertEqual(connector.merge_booking_rows(exports, bookings + bookings)[0]["status"], "AMBIGUOUS_BOOKING")

    def test_durian_type_comes_only_from_unique_booking_match(self):
        exports = connector.parse_values([
            list(connector.HEADERS),
            ["ABCU1234567", "WH", "01/10/2026", "Kho", "Port"],
            ["WXYZ7654321", "WH", "02/10/2026", "Kho", "Port"],
        ])
        header = list(connector.BOOKING_HEADERS + connector.BOOKING_PRODUCT_HEADERS)
        def booking(container, day, name, commodity):
            return [container, "Khách A", day, "BK001", "TAB", "7", "Gốc", "Ship", "WH", "Kho", "Port", "", name, commodity, ""]
        bookings = connector.parse_booking_values([
            header,
            booking("ABCU1234567", "01/10/2026", "FROZEN DURIAN MEAT", "SẦU RIÊNG"),
            booking("WXYZ7654321", "02/10/2026", "FRESH DURIAN", "SẦU RIÊNG"),
        ])
        self.assertEqual([row["durian_type"] for row in connector.merge_booking_rows(exports, bookings)], ["frozen", "fresh"])
        self.assertNotIn("durian_type", connector.merge_booking_rows(exports, bookings + bookings)[0])
        self.assertIsNone(connector.durian_type("FRESH DURIAN", "THANH LONG"))
        self.assertIsNone(connector.durian_type("FRESH + FROZEN DURIAN", "SẦU RIÊNG"))

    def test_read_export_with_booking_hashes_both_tabs(self):
        export = [list(connector.HEADERS), ["ABCU1234567", "WH", "01/10/2026", "Kho", "Port"]]
        booking = [list(connector.BOOKING_HEADERS),
                   ["ABCU1234567", "Khách A", "01/10/2026", "BK001", "TAB", "7", "Gốc", "Ship", "WH", "Kho", "Port"]]
        requested = []

        class Response:
            def __init__(self, values): self.values = values
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def read(self): return json.dumps({"values": self.values}).encode()

        def opener(request, timeout):
            requested.append(request.full_url)
            return Response(booking if "BOOKING_DATA" in request.full_url else export)

        first = connector.read_export("sheet-id", "token", opener, include_booking=True)
        self.assertEqual(len(requested), 2)
        self.assertEqual(first["rows"][0]["customer_name"], "Khách A")
        self.assertEqual(first["rows"][0]["booking"], "BK001")
        self.assertEqual(first["source"]["booking_range"], connector.BOOKING_RANGE)
        booking[1][1] = "Khách B"
        second = connector.read_export("sheet-id", "token", opener, include_booking=True)
        self.assertNotEqual(first["sha256"], second["sha256"])

    def test_customer_mapping_requires_unique_active_exact_name(self):
        row = {"status": "READY", "customer_name": "Khách A", "source_row": 2}
        customers = {"customers": [{"id": 7, "name": "Khách A", "status": "active"}]}
        self.assertEqual(connector.merge_customers([row], customers)[0]["customer_id"], 7)
        self.assertEqual(connector.merge_customers([row | {"customer_name": "KHÁCH   A"}], customers)[0]["customer_id"], 7)
        self.assertEqual(connector.merge_customers([row | {"customer_name": "Khach A"}], customers)[0]["status"], "NO_CUSTOMER_MATCH")
        self.assertEqual(connector.merge_customers([row], {"customers": []})[0]["status"], "NO_CUSTOMER_MATCH")
        self.assertEqual(connector.merge_customers([row], {"customers": customers["customers"] * 2})[0]["status"], "AMBIGUOUS_CUSTOMER")
        self.assertEqual(connector.merge_customers([row], {"customers": [{"id": 7, "name": "Khách A", "status": "NO_BASELINE"}]})[0]["status"], "NO_BASELINE_CUSTOMER")
        self.assertEqual(connector.merge_customers([row | {"status": "INVALID"}], customers)[0]["status"], "INVALID")
        with self.assertRaisesRegex(ValueError, "customer list"):
            connector.merge_customers([row], {})

    def test_customer_review_mapping_overrides_sheet_alias_only_when_filled(self):
        values = [
            ["Chủ hàng từ BOOKING_DATA", "Số chuyến", "Gợi ý trong Sheet (chưa chốt)",
             "Tên gần giống trên hao (chưa chốt)", "Trạng thái", "Khách chuẩn trên hao (bạn điền)"],
            ["Sheet alias", "2", "", "", "REVIEW", "Hao canonical"],
            ["Blank choice", "1", "", "", "REVIEW", ""],
        ]
        aliases = connector.parse_review_mapping(values)
        self.assertEqual(aliases, {"SHEET ALIAS": "Hao canonical"})
        row = {"status": "READY", "customer_name": "Sheet alias", "source_row": 2}
        customers = {"customers": [{"id": 7, "name": "Hao canonical", "status": "active"}]}
        self.assertEqual(connector.merge_customers([row], customers, aliases)[0]["customer_id"], 7)

    def test_build_review_queue_blocks_customer_price_and_baseline_before_write(self):
        rows = [
            {"status": "READY", "container": "A", "event_date": "2026-01-01", "reviewed_new_trip": True},
            {"status": "READY", "container": "B", "event_date": "2026-01-02", "customer_id": 7, "reviewed_new_trip": True},
            {"status": "READY", "container": "C", "event_date": "2026-01-03", "customer_id": 7, "unit_price_vnd": 20},
            {"status": "DUPLICATE", "container": "D", "event_date": "2026-01-04"},
            {"status": "READY", "container": "E", "event_date": "2026-01-05", "customer_id": 7, "unit_price_vnd": 20},
            {"status": "READY", "container": "F", "event_date": "2026-01-06", "customer_id": 7, "unit_price_vnd": 20, "reviewed_new_trip": True},
        ]
        queue = connector.build_review_queue(rows, [{"container_norm": "C", "booking_norm": "", "event_date": "2026-01-05"}])
        self.assertEqual([row["review_status"] for row in queue], ["NEEDS_CUSTOMER", "NEEDS_PRICE", "BASELINE_REVIEW", "DUPLICATE", "NEW_TRIP_REVIEW", "READY_TO_PREVIEW"])
        self.assertEqual(queue[2]["review_reasons"], ["BASELINE_MATCH"])
        with self.assertRaisesRegex(ValueError, "READY"):
            connector.to_paste_trip(queue[2])
        self.assertTrue(all(row["candidate"] is None for row in connector.paste_preview({"rows": queue[:-1]})["rows"]))
        with self.assertRaisesRegex(ValueError, "baseline references"):
            connector.build_review_queue(rows, [])


if __name__ == "__main__":
    unittest.main()
