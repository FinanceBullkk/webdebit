"""Serve the real ledger viewer (LedgerHandler) over HTTP with fake data for browser tests.

Not a unittest module. Starts one loopback server per scenario, prints one JSON line
{"scenario": port, ...} and stops when stdin closes or on SIGTERM. Fake data only; no database.
"""

from __future__ import annotations

import json
import sys
import threading
from datetime import date
from http.server import ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "web"))
sys.path.insert(0, str(HERE))
import ledger_app  # noqa: E402
from test_ledger_web import FakeHistory, FakeLedger  # noqa: E402


class NullOpeningLedger(FakeLedger):
    """A new period without historical opening (NULL) next to a true zero opening."""

    def customers(self, as_of, search=""):
        return [{"customer": "A & B", "opening_vnd": None, "movement_vnd": 50,
                 "balance_vnd": 50, "periods": 2, "no_baseline": 0}]

    def periods(self, as_of, customer):
        return [
            {"customer": customer, "debt_period": "2026-11", "opening_vnd": None,
             "movement_vnd": 50, "balance_vnd": 50, "comparison_status": None,
             "replay_event_count": None},
            {"customer": customer, "debt_period": "2026-10", "opening_vnd": 0,
             "movement_vnd": 0, "balance_vnd": 0, "comparison_status": "MATCH",
             "replay_event_count": 0},
        ]

    def period(self, as_of, customer, period):
        return [row for row in self.periods(as_of, customer) if row["debt_period"] == period]


class HistoryFailsHistory(FakeHistory):
    fail_summary = True


class HistoryFailsLedger(FakeLedger):
    pass


SCENARIOS = {
    "default": (FakeLedger, FakeHistory),
    "null_opening": (NullOpeningLedger, FakeHistory),
    "history_error": (HistoryFailsLedger, HistoryFailsHistory),
}


def start(ledger_cls, history_cls) -> ThreadingHTTPServer:
    handler = type("FixtureHandler", (ledger_app.LedgerHandler,),
                   {"db": ledger_cls(), "history": history_cls(), "port": 0})
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    handler.port = server.server_port
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def use_history_fixture_mode() -> None:
    """The fixtures model the history-attached (13/10 replay) mode, like LedgerWebTest."""
    ledger_app.HISTORY_ENABLED = True
    ledger_app.OPENING_DATE = date(2026, 10, 13)
    ledger_app.OPENING_INVARIANTS = {"opening_periods": FakeLedger.opening_periods,
                                     "opening_vnd": FakeLedger.opening_vnd,
                                     "no_baseline": FakeLedger.no_baseline}


def main() -> None:
    use_history_fixture_mode()
    servers ={name: start(*classes) for name, classes in SCENARIOS.items()}
    print(json.dumps({name: server.server_port for name, server in servers.items()}), flush=True)
    try:
        sys.stdin.read()  # parent closes the pipe (or dies) -> stop
    finally:
        for server in servers.values():
            server.shutdown()
            server.server_close()


if __name__ == "__main__":
    main()
