#!/usr/bin/env python3
"""DỮ LIỆU GIẢ: V7 live demo on localhost with disposable, networkless PostgreSQL."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
import uuid
from datetime import date as Date
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

from test_pg_v7_backend import (DATABASE, FUNCTIONS, IMAGE, LABEL_RUN, LABEL_TEST,
                                LABEL_VALUE, SCHEMA, Pg, HarnessError, call, import_book,
                                inspect_owned, inspect_volume, require, run, version)

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "web"))
import v7_ledger_api as api


def seed(pg: Pg) -> dict[str, int]:
    today = Date.fromisoformat(pg.value("SELECT (clock_timestamp() AT TIME ZONE 'Asia/Ho_Chi_Minh')::date"))
    month = today.replace(day=1).isoformat()
    date = today.isoformat()
    fake_hash = "a" * 64

    def book(name: str, amounts: list[int], flags: list[list[str]] | None = None) -> int:
        customer = int(pg.value(f"INSERT INTO sokhach.customer(name) VALUES ('{name}') RETURNING id"))
        total = sum(amounts)
        cutover = int(pg.value("INSERT INTO sokhach.cutover(name,source,source_sha256,frozen_at,"
            "control_total_vnd,created_by) VALUES ('DỮ LIỆU GIẢ','fake demo',"
            f"'{fake_hash}',now(),{total},'demo') RETURNING id"))
        import_book(pg, customer, cutover, amounts, f"demo-import-{customer}", flags=flags)
        require(call(pg, "verify_cutover_customer", customer, cutover, version(pg, customer),
                     f"demo-verify-customer-{customer}", None)["status"] == "verified", "customer verify failed")
        require(call(pg, "verify_cutover", cutover, f"demo-verify-{cutover}", None)["status"] == "verified",
                "cutover verify failed")
        require(call(pg, "activate_cutover", cutover, f"demo-activate-{cutover}", None)["status"] == "active",
                "cutover activate failed")
        require(call(pg, "activate_cutover_customer", customer, cutover, version(pg, customer),
                     f"demo-activate-customer-{customer}", None)["status"] == "active",
                "customer activate failed")
        require(call(pg, "get_ledger", customer)["status"] == "active", "opening not active")
        return customer

    normal = book("GIẢ - nhiều kỳ và phiếu thu", [1_200_000, 800_000, 600_000])
    call(pg, "paste_trips", normal, version(pg, normal), "demo-current-trip", month,
         json.dumps([{"container": "FAKE-CURRENT", "carrier": "FAKE",
                      "date": today.strftime("%d/%m/%Y"), "from": "Kho giả", "to": "Bãi giả",
                      "unitPriceVnd": "300000", "otherFeeVnd": None,
                      "note": "Chuyến tháng hiện tại", "src": "DỮ LIỆU GIẢ"}], ensure_ascii=False))
    for number, amount in enumerate((350_000, 175_000), 1):
        call(pg, "record_receipt", normal, version(pg, normal), f"demo-receipt-{number}",
             date, "THU TIỀN", amount)
    require(len(call(pg, "get_ledger", normal)["receipts"]) == 2, "demo receipts absent")
    no_baseline = int(pg.value("INSERT INTO sokhach.customer(name) "
                               "VALUES ('GIẢ - chưa có số dư đầu') RETURNING id"))
    require(call(pg, "get_ledger", no_baseline)["status"] == "NO_BASELINE", "NO_BASELINE lost")
    flagged = book("GIẢ - thiếu giá và phí lẻ", [500_000, 200_000], [[], ["MISSING_PRICE"]])
    trips = [
        {"container": "FAKE-CONTAINER-01", "carrier": "FAKE", "date": today.strftime("%d/%m/%Y"),
         "from": "Kho giả", "to": "Bãi giả", "unitPriceVnd": None, "otherFeeVnd": None,
         "note": "Chờ giá giả", "src": "DỮ LIỆU GIẢ"},
        {"container": None, "carrier": None, "date": None, "from": None, "to": None,
         "unitPriceVnd": None, "otherFeeVnd": "45000",
         "note": "Phí lẻ giả không ngày", "src": "DỮ LIỆU GIẢ"},
    ]
    call(pg, "paste_trips", flagged, version(pg, flagged), "demo-trips", month,
         json.dumps(trips, ensure_ascii=False))
    snapshot = call(pg, "get_ledger", flagged)
    require(snapshot["pending_count"] == 1 and
            any(row["is_fee_only"] and row["event_date"] is None for row in snapshot["trips"]),
            "missing price or undated fee absent")
    return {"Nhiều kỳ + phiếu thu": normal, "NO_BASELINE": no_baseline,
            "Thiếu giá + phí lẻ": flagged}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once-seed-only", action="store_true", help="seed, check, then remove run resources")
    args = parser.parse_args()
    run_id = uuid.uuid4().hex
    name = volume = f"webdebit-v7-demo-{run_id}"
    volume_created = False
    container_id = None
    server = None
    exit_code = 0
    try:
        require(shutil.which("docker") is not None, "Docker CLI unavailable")
        run(["docker", "volume", "create", "--label", f"{LABEL_TEST}={LABEL_VALUE}",
             "--label", f"{LABEL_RUN}={run_id}", volume])
        volume_created = True
        inspect_volume(volume, run_id)
        run(["docker", "run", "--detach", "--name", name,
             "--label", f"{LABEL_TEST}={LABEL_VALUE}", "--label", f"{LABEL_RUN}={run_id}",
             "--network", "none", "--volume", f"{volume}:/var/lib/postgresql",
             "--env", "POSTGRES_HOST_AUTH_METHOD=trust", IMAGE], timeout=240)
        container_id = inspect_owned(name, volume, run_id)
        require(container_id is not None, "demo container absent")
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            logs = run(["docker", "logs", name], check=False, timeout=10)
            if "PostgreSQL init process complete; ready for start up." in logs.stdout + logs.stderr:
                break
            time.sleep(0.25)
        else:
            raise HarnessError("PostgreSQL init marker timed out")
        pg = Pg(name, run_id)
        require(pg.sql("SELECT current_database()", database="postgres").stdout.strip() == "postgres",
                "unexpected initial database")
        inspect_owned(name, volume, run_id, container_id)
        pg.sql(f"CREATE DATABASE {DATABASE}", database="postgres")
        for source in (SCHEMA, FUNCTIONS):
            run(["docker", "exec", "-i", *pg.env, name, "psql", "-X", "-v",
                 "ON_ERROR_STOP=1", "-U", "postgres", "-d", DATABASE],
                input_text=source.read_text(encoding="utf-8"))
        customers = seed(pg)
        print("DỮ LIỆU GIẢ — không phải sổ thật", flush=True)
        print(f"Docker run: {run_id}; --network none; không publish cổng", flush=True)
        for label, customer in customers.items():
            print(f"{label}: http://127.0.0.1:8780/so-khach-v7-live.html?customer={customer}", flush=True)
        if args.once_seed_only:
            print("Seed đã kiểm; sẽ xóa container và volume. URL sẽ không hoạt động.", flush=True)
        else:
            class DemoHandler(api.Handler):
                runner = api.Psql(name, DATABASE, "postgres")
                demo = True
                default_actor = "fake-demo"

            server = api.ThreadingHTTPServer(("127.0.0.1", 8780), DemoHandler)
            print("API demo đang chạy trên 127.0.0.1:8780. Ctrl+C để dừng và dọn run.", flush=True)
            server.serve_forever()
    except KeyboardInterrupt:
        print("Dừng demo; dọn đúng container/volume của run.", flush=True)
    except (HarnessError, OSError, ValueError, KeyError) as exc:
        print(f"Demo lỗi: {exc}", file=sys.stderr)
        exit_code = 1
    finally:
        if server is not None:
            server.server_close()
        if volume_created:
            try:
                owned = inspect_owned(name, volume, run_id, container_id)
                if owned:
                    run(["docker", "rm", "--force", owned])
                inspect_volume(volume, run_id)
                run(["docker", "volume", "rm", volume])
                print("Đã dọn container/volume của run.", flush=True)
            except (HarnessError, OSError, ValueError) as exc:
                print(f"Dọn run chưa xong: {exc}; run_id={run_id}", file=sys.stderr)
                exit_code = 1
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
