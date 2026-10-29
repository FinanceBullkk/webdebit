"""PRESENCE-01: who is online — RAM only, actor from server, SSE stream."""

import http.client
import json
import sys
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "web"))
import v7_ledger_api as api  # noqa: E402
import v7_presence as presence  # noqa: E402

TAB_A, TAB_B, TAB_C = "tab-aaaaaaaa", "tab-bbbbbbbb", "tab-cccccccc"


def body(tab, **fields):
    return json.dumps({"tab": tab, **fields}).encode()


def book(tab, customer=12, cell=None, pointer=None, page="so-khach"):
    return presence.parse(body(tab, page=page, customer_id=customer, month="2026-09", cell=cell, pointer=pointer))


CELL = {"row": "trip:4812", "col": "unit_price", "editing": True}
POINTER = {"row": "trip:4812", "col": "unit_price", "fx": 420, "fy": 600}


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


class ParseTest(unittest.TestCase):
    def test_accepts_full_report(self):
        report = book(TAB_A, cell=CELL, pointer=POINTER)
        self.assertEqual(report["cell"], CELL)
        self.assertEqual(report["pointer"], POINTER)
        self.assertEqual(presence.parse(body(TAB_A))["page"], None)

    def test_rejects_bad_reports(self):
        bad = [
            b"[]", b"not json", body("short"), body(TAB_A, actor="someone@example.test"),
            body(TAB_A, page="admin"), body(TAB_A, customer_id=0), body(TAB_A, customer_id="12"),
            body(TAB_A, month="2026-13"), body(TAB_A, cell={"row": "trip:1", "col": "x"}),
            body(TAB_A, cell={**CELL, "editing": 1}), body(TAB_A, cell={**CELL, "row": "<script>"}),
            body(TAB_A, pointer={**POINTER, "fx": 0.5}), body(TAB_A, pointer={**POINTER, "fy": 1001}),
            body(TAB_A, pointer={**POINTER, "fx": True}),
        ]
        for raw in bad:
            with self.subTest(raw=raw), self.assertRaises(presence.PresenceError):
                presence.parse(raw)
        with self.assertRaisesRegex(presence.PresenceError, "BODY_TOO_LARGE"):
            presence.parse(b" " * (presence.MAX_BODY + 1))


class PresenceTest(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.p = presence.Presence(clock=self.clock)

    def test_same_book_sees_cell_and_pointer_other_book_does_not(self):
        self.p.report("lan@example.test", book(TAB_A, cell=CELL, pointer=POINTER))
        self.p.report("minh@example.test", book(TAB_B))
        self.p.report("hoa@example.test", book(TAB_C, customer=99))
        same = self.p.view("minh@example.test", TAB_B)
        lan = next(person for person in same if person["name"] == "lan")
        self.assertEqual((lan["cell"], lan["pointer"], lan["customer_id"], lan["month"]), (CELL, POINTER, 12, "2026-09"))
        other = next(person for person in self.p.view("hoa@example.test", TAB_C) if person["name"] == "lan")
        self.assertEqual((other["cell"], other["pointer"], other["customer_id"]), (None, None, 12))
        self.p.report("hoa@example.test", book(TAB_C, page="dashboard", customer=None))
        self.assertEqual(next(person for person in self.p.view("hoa@example.test", TAB_C) if person["name"] == "lan")["cell"], None)

    def test_excludes_own_tab_and_hides_login(self):
        self.p.report("lan@example.test", book(TAB_A))
        self.p.report("lan@example.test", book(TAB_B))
        people = self.p.view("lan@example.test", TAB_A)
        self.assertEqual(len(people), 1)
        self.assertEqual(people[0]["name"], "lan")
        self.assertNotIn("example.test", json.dumps(people))
        self.assertEqual(people[0]["color"], next(iter(self.p.view("lan@example.test", TAB_B)))["color"])

    def test_pointer_and_entry_expire(self):
        self.p.report("lan@example.test", book(TAB_A, cell=CELL, pointer=POINTER))
        self.p.report("minh@example.test", book(TAB_B))
        self.clock.now += presence.POINTER_TTL + 0.1
        self.p.report("minh@example.test", book(TAB_B))
        lan = self.p.view("minh@example.test", TAB_B)[0]
        self.assertEqual((lan["cell"], lan["pointer"]), (CELL, None))
        self.clock.now += presence.TTL
        self.p.report("minh@example.test", book(TAB_B))
        self.assertEqual(self.p.view("minh@example.test", TAB_B), [])

    def test_leaving_removes_entry(self):
        self.p.report("lan@example.test", book(TAB_A))
        self.p.report("lan@example.test", presence.parse(body(TAB_A, page=None)))
        self.assertEqual(self.p.view("minh@example.test", TAB_B), [])

    def test_dev_actor_tabs_are_numbered(self):
        self.p.report("dev:local", book(TAB_A))
        self.p.report("dev:local", book(TAB_B))
        self.assertEqual(self.p.view("dev:local", TAB_A)[0]["name"], "Người dùng 2")
        self.assertEqual(self.p.view("dev:local", TAB_B)[0]["name"], "Người dùng 1")

    def test_limits(self):
        with patch.object(presence, "MAX_TABS_PER_ACTOR", 2):
            self.p.report("lan@example.test", book(TAB_A))
            self.p.report("lan@example.test", book(TAB_B))
            self.p.report("lan@example.test", book(TAB_B))
            with self.assertRaisesRegex(presence.PresenceError, "TOO_MANY_TABS"):
                self.p.report("lan@example.test", book(TAB_C))
        with patch.object(presence, "MAX_STREAMS_PER_ACTOR", 1):
            self.assertTrue(self.p.open_stream("lan"))
            self.assertFalse(self.p.open_stream("lan"))
            self.assertTrue(self.p.open_stream("minh"))
            self.p.close_stream("lan")
            self.assertTrue(self.p.open_stream("lan"))


HEADERS = {"Host": "127.0.0.1:8780", "Origin": "http://127.0.0.1:8780", "Content-Type": "application/json"}


class PresenceApiTest(unittest.TestCase):
    headers = HEADERS

    def call(self, method, path, raw=b"", actor="server@example.test", headers=None):
        return api.handle(method, path, headers or self.headers, raw, None, port=8780, host="127.0.0.1", actor=actor)

    def test_post_and_get_use_server_actor(self):
        with patch.object(api, "PRESENCE", presence.Presence()):
            self.assertEqual(self.call("POST", "/api/v7/presence", body(TAB_A, page="so-khach", customer_id=1)),
                             (200, {"people": []}))
            status, value = self.call("GET", f"/api/v7/presence?tab={TAB_B}", actor="other@example.test")
            self.assertEqual(status, 200)
            self.assertEqual([person["name"] for person in value["people"]], ["server"])

    def test_rejects_bad_requests(self):
        with patch.object(api, "PRESENCE", presence.Presence()):
            cases = [
                ("POST", "/api/v7/presence", body(TAB_A, actor="x"), None, 422),
                ("POST", "/api/v7/presence", b" " * 3000, None, 413),
                ("POST", "/api/v7/presence", body(TAB_A, page="so-khach"), {**self.headers, "Origin": "http://evil.test"}, 403),
                ("GET", "/api/v7/presence", b"", None, 422),
                ("GET", "/api/v7/presence?tab=short", b"", None, 422),
            ]
            for method, path, raw, headers, status in cases:
                with self.subTest(path=path, status=status), self.assertRaises(api.ApiError) as caught:
                    self.call(method, path, raw, headers=headers)
                self.assertEqual(caught.exception.status, status)


class PresenceStreamTest(unittest.TestCase):
    def test_stream_pushes_reports_from_other_tab(self):
        class TrialHandler(api.Handler):
            runner = None
            default_actor = "presence-test"
            dev_actor_mode = True

        with patch.object(api, "PRESENCE", presence.Presence()), \
                api.ThreadingHTTPServer(("127.0.0.1", 0), TrialHandler) as server:
            TrialHandler.port = server.server_port
            worker = threading.Thread(target=server.serve_forever, daemon=True)
            worker.start()
            origin = f"http://127.0.0.1:{server.server_port}"
            try:
                stream = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=3)
                stream.request("GET", f"/api/v7/presence/stream?tab={TAB_A}")
                response = stream.getresponse()
                self.assertEqual(response.status, 200)
                self.assertEqual(response.getheader("Content-Type"), "text/event-stream; charset=utf-8")

                def next_event():
                    lines = []
                    while True:
                        line = response.fp.readline().decode().rstrip("\n")
                        if not line and lines:
                            return lines
                        if line:
                            lines.append(line)

                self.assertEqual(next_event(), ["event: presence", 'data: {"people":[]}'])
                started = time.monotonic()
                post = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=3)
                post.request("POST", "/api/v7/presence", body(TAB_B, page="so-khach", customer_id=5),
                             {"Origin": origin, "Content-Type": "application/json"})
                self.assertEqual(post.getresponse().status, 200)
                post.close()
                event = next_event()
                self.assertLess(time.monotonic() - started, 1.0)
                people = json.loads(event[1].removeprefix("data: "))["people"]
                self.assertEqual([(person["name"], person["customer_id"]) for person in people], [("Người dùng 1", 5)])
                stream.close()
                with patch.object(presence, "MAX_STREAMS", 0):
                    busy = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=3)
                    busy.request("GET", f"/api/v7/presence/stream?tab={TAB_C}")
                    reply = busy.getresponse()
                    self.assertEqual((reply.status, json.loads(reply.read())["error"]), (503, "PRESENCE_BUSY"))
                    busy.close()
            finally:
                server.shutdown()
                worker.join(timeout=3)


if __name__ == "__main__":
    unittest.main()
