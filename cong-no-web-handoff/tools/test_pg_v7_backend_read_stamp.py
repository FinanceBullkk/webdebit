"""HIEU-NANG-01: get_read_stamp đổi sau mọi lệnh ghi đã commit ở bất kỳ bảng sokhach nào, đứng yên khi chỉ đọc."""

from __future__ import annotations

import json
import re

from pg_v7_harness import Pg, actor_sql, call, new_book, require, version


def stamp(pg: Pg) -> str:
    body = call(pg, "get_read_stamp")
    require(set(body) == {"as_of", "stamp"}, f"unexpected keys: {sorted(body)}")
    require(re.fullmatch(r"[0-9a-f]{32}", body["stamp"] or ""), f"stamp is not md5: {body}")
    require(body["as_of"] == pg.value("SELECT ((now() AT TIME ZONE 'Asia/Ho_Chi_Minh')::date)::text"), f"as_of not VN date: {body}")
    return body["stamp"]


def check_read_stamp(pg: Pg) -> None:
    customer = new_book(pg, ("2026-01-01", 1000))
    first, at = stamp(pg), version(pg, customer)

    # Chỉ đọc (cả các hàm API giữ kết quả) và khóa dòng: dấu đứng yên, version không đổi.
    call(pg, "get_ledger", customer)
    call(pg, "get_dashboard_debt")   # get_dashboard tràn bigint với số tiền thử dồn của các case trước trong harness
    pg.sql(f"BEGIN; SELECT 1 FROM sokhach.customer WHERE id={customer} FOR UPDATE; COMMIT")
    require(stamp(pg) == first, "reads or row locks changed the stamp")
    require(version(pg, customer) == at, "reading must not bump customer.version")

    # Lệnh ghi tiền qua _begin_command.
    call(pg, "record_receipt", customer, version(pg, customer), "stamp-receipt", "2026-02-01", "THU TIỀN", 300, None)
    second = stamp(pg)
    require(second != first, "receipt did not change the stamp")

    # Lệnh dùng chung không tăng version của sổ nào: đổi tên loại phí.
    fee = call(pg, "add_fee_type", "stamp-fee", "FAKE STAMP FEE", "service")["id"]
    third = stamp(pg)
    require(third != second, "new fee type did not change the stamp")
    before = pg.value("SELECT sum(version) FROM sokhach.customer")
    call(pg, "rename_fee_type", "stamp-rename", fee, "FAKE STAMP RENAMED")
    require(pg.value("SELECT sum(version) FROM sokhach.customer") == before, "fixture: rename must not bump any version")
    fourth = stamp(pg)
    require(fourth != third, "fee type rename did not change the stamp")

    # UPDATE tại chỗ không đổi số dòng, DELETE không đổi xmin dòng còn lại: cả hai đổi dấu.
    pg.sql(f"UPDATE sokhach.fee_type SET name='FAKE STAMP RAW' WHERE id={fee}")
    fifth = stamp(pg)
    require(fifth != fourth, "in-place update did not change the stamp")
    pg.sql(f"DELETE FROM sokhach.fee_type_audit WHERE fee_type_id={fee}")
    require(stamp(pg) != fifth, "delete did not change the stamp")

    # Giao dịch hoàn tác không đổi dấu.
    settled = stamp(pg)
    pg.sql(f"BEGIN; UPDATE sokhach.fee_type SET name='FAKE STAMP ROLLED BACK' WHERE id={fee}; ROLLBACK")
    require(stamp(pg) == settled, "rolled back write changed the stamp")

    # Quyền: thiếu người làm bị chặn; app và reader gọi được, cùng dấu.
    pg.rejects("SELECT sokhach.get_read_stamp()", message="ACTOR_REQUIRED")
    for user in ("v7_app", "v7_reader"):
        body = json.loads(pg.value(actor_sql("SELECT sokhach.get_read_stamp()", "harness"), user=user))
        require(body["stamp"] == settled, f"{user} sees another stamp: {body}")
