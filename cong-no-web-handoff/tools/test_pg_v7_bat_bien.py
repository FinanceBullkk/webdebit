#!/usr/bin/env python3
"""Kiểm bất biến tiền bằng chuỗi lệnh ngẫu nhiên có seed trên PostgreSQL dùng một lần (specs/v7-bat-bien-tien.md).

Mỗi chuỗi dựng vài sổ giả rồi chạy các lệnh ghi tiền qua đúng hàm `sokhach.*` API gọi: dán lô, sửa giá, đổi ngày
chuyến, xóa chuyến, điều chỉnh chuyến/tháng, xóa điều chỉnh, duyệt chuyến chờ kiểm, ghi/sửa/hủy phiếu, khóa/mở
tháng, cấn trừ hai sổ, sửa/hủy cấn trừ, gửi lặp. Sau MỖI lệnh kiểm các bất biến trong `BAT_BIEN`.

Python chỉ giữ "bóng sổ" (những gì đã ghi: opening, chuyến, điều chỉnh, phiếu, cấn trừ, khóa) để biết luật chờ lệnh
được nhận hay bị từ chối và số dư phải bằng bao nhiêu; không có mô hình phân bổ: FIFO được kiểm bằng tính chất. Cả
chuỗi chạy trong một lượt psql (`bat_bien.run`: mỗi lệnh một subtransaction như một lần gọi API, chụp ảnh sổ sau mỗi
lệnh), rồi Python đi lại từng bước để kiểm. Bộ sinh tự viết trên `random.Random`, không cần thư viện ngoài. Đỏ thì
rút gọn chuỗi lệnh và in từng bước. Cần Docker:

    python cong-no-web-handoff/tools/test_pg_v7_bat_bien.py                       # bản CI
    python cong-no-web-handoff/tools/test_pg_v7_bat_bien.py --sequences 1000      # bản dài
    python cong-no-web-handoff/tools/test_pg_v7_bat_bien.py --seed 7 --sequence 12 --steps 30   # chạy lại một chuỗi
    python cong-no-web-handoff/tools/test_pg_v7_bat_bien.py --mutant fifo-dao     # chứng minh bắt được lỗi
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import random
import re
import sys
import time
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

from pg_v7_harness import (
    FUNCTIONS,
    IMAGE,
    SCHEMA,
    HarnessError,
    Pg,
    disposable_database,
    lit,
    require,
)

DEFAULT_SEED = 20261118  # CI cố định seed để PR không đỏ vì chuỗi mới; tìm rộng hơn thì đổi --seed
BAT_BIEN = {
    "so-du": "Số dư sổ = opening + phát sinh có giá − thu ± điều chỉnh ± cấn trừ, VND nguyên; bảng tháng tự khớp",
    "fifo": "Phân bổ thu theo nợ cũ trước, đủ đúng số phiếu, không trả quá nợ tháng, ứng trước ở tháng cuối",
    "opening": "Opening và lịch sử trong opening không đổi, không phân bổ lại, không cộng lại",
    "huy-phieu": "Hủy phiếu bắt buộc lý do và không đổi phân bổ của phiếu khác",
    "pending": "Chuyến thiếu giá và chuyến chờ kiểm nằm ngoài số dư",
    "null": "Đơn giá/phụ phí trống giữ NULL, không thành 0; chỉ phụ phí trống của chuyến có đơn giá tính 0",
    "thang-khoa": "Tháng khóa không bị sửa đè: mọi sửa vào tháng khóa bị chặn MONTH_LOCKED",
    "lich-su": "Mỗi lệnh tiền tăng version đúng một, có dòng Lịch sử ghi người làm và trước → sau; Lịch sử chỉ thêm",
    "can-tru": "Cấn trừ không làm đổi tổng hai sổ; vượt số dư có thì bị chặn",
    "tuong-lai": "Ngày phiếu, ngày chuyến, ngày cấn trừ ở tương lai (giờ VN) bị chặn",
    "nguyen-tu": "Lệnh bị từ chối không để lại gì; gửi lặp trả đúng kết quả cũ và không ghi thêm",
    "ket-qua": "Lệnh được nhận hay bị từ chối đúng mã như luật",
}
# Lỗi cố ý, chỉ sửa trong container dùng một lần, để chứng minh test bắt được lỗi: (loại, tên, đoạn gốc, đoạn thay).
MUTANTS = {
    "fifo-dao": ("function", "reallocate", "FOR i IN 1..coalesce(array_length(v_months,1),0) LOOP",
                 "FOR i IN REVERSE coalesce(array_length(v_months,1),0)..1 LOOP"),
    "huy-phan-bo-lai": ("function", "void_receipt", "PERFORM sokhach._check_allocations(customer_id);",
                        "PERFORM sokhach.reallocate(customer_id,idempotency_key);"),
    "tuong-lai": ("function", "record_receipt", "IF date > (clock_timestamp()", "IF false AND date > (clock_timestamp()"),
    "khoa-thang": ("function", "_month_open", "THEN RAISE EXCEPTION 'MONTH_LOCKED'; END IF;", "THEN NULL; END IF;"),
    "lich-su": ("function", "adjust_month", "VALUES (customer_id,'adjust_month',sokhach._actor(),",
                "VALUES (customer_id,'adjust_month','may',"),
    "null-0": ("function", "paste_trips", "(v_item->>'unitPriceVnd')::bigint,v_event);",
               "coalesce((v_item->>'unitPriceVnd')::bigint,0),v_event);"),
    "can-tru": ("view", "v_offset_outgoing", "amount_vnd\n", "amount_vnd * 2 AS amount_vnd\n"),
}
METHODS = ("THU TIỀN", "CẤN TRỪ", "ỨNG TRƯỚC", "KHÁC")
MONEY = re.compile(r"^-?[0-9]+$")
WINDOW = 6  # tháng hiện tại và 5 tháng trước có dòng month_state mở; tháng cũ hơn mặc định khóa

HELPERS = r"""
CREATE SCHEMA bat_bien;
-- Một lệnh như một lần gọi API: lỗi thì cả lệnh lùi (subtransaction); ràng buộc hoãn kiểm ngay như lúc COMMIT.
CREATE FUNCTION bat_bien.try(p_sql text) RETURNS jsonb LANGUAGE plpgsql AS $f$
DECLARE v jsonb;
BEGIN
    SET CONSTRAINTS ALL DEFERRED;
    EXECUTE p_sql INTO v;
    SET CONSTRAINTS ALL IMMEDIATE;
    RETURN jsonb_build_object('ok', v);
EXCEPTION WHEN OTHERS THEN
    RETURN jsonb_build_object('error', SQLERRM);
END $f$;
-- Sổ giả: opening theo tháng lùi từ hôm nay (giờ VN), dòng lịch sử trong opening (chỉ hiển thị), p_window tháng mở.
CREATE FUNCTION bat_bien.new_books(p_label text, p_setup jsonb, p_window int) RETURNS jsonb LANGUAGE plpgsql AS $f$
DECLARE v_today date := (clock_timestamp() AT TIME ZONE 'Asia/Ho_Chi_Minh')::date;
        v_ids jsonb := '[]'; v_book jsonb; v_customer bigint; v_cutover bigint; v_event bigint; v_total bigint;
        v_n int; v_row jsonb; i int; b int := 0;
BEGIN
    FOR v_book IN SELECT value FROM jsonb_array_elements(p_setup) LOOP
        b := b+1; i := 0;
        SELECT coalesce(sum((x->>1)::bigint),0), count(*) INTO v_total, v_n FROM jsonb_array_elements(v_book->'openings') x;
        INSERT INTO sokhach.customer(name) VALUES ('FAKE BAT BIEN '||p_label||'-'||b) RETURNING id INTO v_customer;
        INSERT INTO sokhach.cutover(name,source,source_sha256,frozen_at,control_total_vnd,created_by)
            VALUES ('FAKE BAT BIEN','anonymous',repeat('a',64),now(),v_total,'bat-bien') RETURNING id INTO v_cutover;
        INSERT INTO sokhach.cutover_customer(customer_id,cutover_id,expected_control_total_vnd,report_sha256,
            source_rows,imported_rows,quarantined_rows,skipped_with_reason_rows,unresolved_exceptions)
            VALUES (v_customer,v_cutover,v_total,repeat('a',64),v_n,v_n,0,0,0);
        INSERT INTO sokhach.event(customer_id,kind,actor,"before","after",cutover_id)
            VALUES (v_customer,'import','bat-bien','{}',jsonb_build_object('cutover',v_cutover),v_cutover)
            RETURNING id INTO v_event;
        FOR v_row IN SELECT value FROM jsonb_array_elements(v_book->'openings') LOOP
            i := i+1;
            INSERT INTO sokhach.opening_balance(customer_id,cutover_id,debt_month,amount_vnd,source_tab,source_row,
                created_by_event) VALUES (v_customer,v_cutover,
                (date_trunc('month',v_today)-make_interval(months=>(v_row->>0)::int))::date,(v_row->>1)::bigint,'FAKE',i,v_event);
        END LOOP;
        FOR v_row IN SELECT value FROM jsonb_array_elements(v_book->'legacy') LOOP
            i := i+1;
            INSERT INTO sokhach.legacy_row(customer_id,cutover_id,debt_month,kind,display,source_total_vnd,source_tab,
                source_row,created_by_event) VALUES (v_customer,v_cutover,
                (date_trunc('month',v_today)-make_interval(months=>(v_row->>0)::int))::date,v_row->>1,
                CASE v_row->>1 WHEN 'trip' THEN '{"fake":true,"container":"FAKEOLD","date":"01/01/2020"}'::jsonb
                ELSE jsonb_build_object('fake',true,'pid','PH-00'||(v_row->>0),'date','01/01/2020') END,
                (v_row->>2)::bigint,'FAKE',i,v_event);
        END LOOP;
        UPDATE sokhach.cutover_customer SET status='verified' WHERE customer_id=v_customer;
        UPDATE sokhach.cutover SET status='verified' WHERE id=v_cutover;
        UPDATE sokhach.cutover SET status='active' WHERE id=v_cutover;
        UPDATE sokhach.cutover_customer SET status='active' WHERE customer_id=v_customer;
        INSERT INTO sokhach.baseline_trip_ref VALUES (v_cutover,'FAKE-REF','FAKE-REF',NULL);
        INSERT INTO sokhach.month_state(customer_id,month,locked,changed_by)
            SELECT v_customer,(date_trunc('month',v_today)-make_interval(months=>n))::date,false,'bat-bien'
            FROM generate_series(0,p_window-1) n;
        v_ids := v_ids || to_jsonb(v_customer);
    END LOOP;
    RETURN jsonb_build_object('today',v_today,'ids',v_ids);
END $f$;
-- Ảnh các sổ: get_ledger như trang sổ đọc, cộng bảng gốc cho phần get_ledger không trả.
CREATE FUNCTION bat_bien.state(p_ids bigint[], p_after bigint) RETURNS jsonb LANGUAGE plpgsql AS $f$
DECLARE v_books jsonb := '{}'; v_id bigint; v_l jsonb;
        v_today date := (clock_timestamp() AT TIME ZONE 'Asia/Ho_Chi_Minh')::date;
BEGIN
    PERFORM set_config('sokhach.actor','bat-bien-doc',true);
    FOREACH v_id IN ARRAY p_ids LOOP
        v_l := sokhach.get_ledger(v_id);
        v_books := v_books || jsonb_build_object(v_id::text, jsonb_build_object(
          'version', (SELECT version FROM sokhach.customer WHERE id=v_id),
          'ledger_version', v_l->'version',
          'total', v_l->'total_outstanding_vnd',
          'pending_count', v_l->'pending_count',
          'months', (SELECT coalesce(jsonb_agg(jsonb_build_array(m->>'month',m->>'outstanding_vnd',m->>'charges_vnd',
                m->>'received_vnd',m->>'prior_months_vnd',m->>'end_of_month_vnd') ORDER BY m->>'month'),'[]')
                FROM jsonb_array_elements(v_l->'months') m),
          'ltrips', (SELECT coalesce(jsonb_object_agg(t->>'note',jsonb_build_array(t->>'status',t->>'unit_price_vnd',
                t->>'other_fee_vnd',t->>'amount_vnd',t->'is_missing_price',t->>'month')),'{}')
                FROM jsonb_array_elements(v_l->'trips') t),
          'raw', (SELECT coalesce(sum(r.outstanding_vnd),0)::text FROM sokhach.v_outstanding_month_raw r
                WHERE r.customer_id=v_id),
          'trips', (SELECT coalesce(jsonb_object_agg(t.id::text,jsonb_build_array(t.debt_month,t.status,t.deleted,
                t.event_date,(SELECT max(p.id) FROM sokhach.trip_price_rev p WHERE p.trip_id=t.id),
                (SELECT max(r.id) FROM sokhach.trip_info_rev r WHERE r.trip_id=t.id),
                (SELECT max(f.id) FROM sokhach.trip_fee_line f WHERE f.trip_id=t.id))),'{}')
                FROM sokhach.v_trip_current t WHERE t.customer_id=v_id),
          'adjs', (SELECT coalesce(jsonb_object_agg(a.id::text,jsonb_build_array(coalesce(t.debt_month,a.debt_month),
                a.amount_vnd::text,a.trip_id,a.reverses_adjustment_id)),'{}')
                FROM sokhach.adjustment a LEFT JOIN sokhach.v_trip_current t ON t.id=a.trip_id WHERE a.customer_id=v_id),
          'receipts', (SELECT coalesce(jsonb_object_agg(r.pid,jsonb_build_array(r.id,r.date,r.amount_vnd::text,r.method,
                r.voided_on IS NOT NULL,(SELECT coalesce(jsonb_agg(jsonb_build_array(l.debt_month,l.kind,l.amount_vnd::text)
                ORDER BY l.debt_month,CASE l.kind WHEN 'debt' THEN 0 ELSE 1 END,l.id),'[]')
                FROM sokhach.receipt_line l WHERE l.receipt_id=r.id AND l.superseded_by_event IS NULL),
                r.void_reason,r.reference)),'{}')
                FROM sokhach.receipt r WHERE r.customer_id=v_id),
          'opening', (SELECT md5(coalesce(string_agg(o::text,'|' ORDER BY o.id),'')) FROM sokhach.opening_balance o
                WHERE o.customer_id=v_id),
          'legacy', (SELECT md5(coalesce(string_agg(l::text,'|' ORDER BY l.id),'')) FROM sokhach.legacy_row l
                WHERE l.customer_id=v_id),
          'locks', (SELECT coalesce(jsonb_object_agg(s.month::text,s.locked),'{}') FROM sokhach.month_state s
                WHERE s.customer_id=v_id),
          'events_all', (SELECT md5(coalesce(string_agg(e::text,'|' ORDER BY e.id),'')) FROM sokhach.event e
                WHERE e.customer_id=v_id),
          'events_old', (SELECT md5(coalesce(string_agg(e::text,'|' ORDER BY e.id),'')) FROM sokhach.event e
                WHERE e.customer_id=v_id AND e.id<=p_after),
          'events_new', (SELECT coalesce(jsonb_agg(jsonb_build_array(e.id,e.kind,e.actor,e."before",e."after")
                ORDER BY e.id),'[]') FROM sokhach.event e WHERE e.customer_id=v_id AND e.id>p_after),
          'future', (SELECT count(*) FROM sokhach.receipt r WHERE r.customer_id=v_id AND r.date>v_today)
                + (SELECT count(*) FROM sokhach.v_trip_current t WHERE t.customer_id=v_id AND t.event_date>v_today)
                + (SELECT count(*) FROM sokhach.offset_pair p WHERE p.source_customer_id=v_id AND p.date>v_today)));
    END LOOP;
    RETURN jsonb_build_object('today',v_today,'max_event',(SELECT coalesce(max(id),0) FROM sokhach.event),'books',v_books);
END $f$;
-- Cả chuỗi trong một lượt: ảnh đầu, rồi mỗi lệnh (người làm riêng) kèm ảnh sau lệnh.
CREATE FUNCTION bat_bien.run(p_ids bigint[], p_steps jsonb) RETURNS jsonb LANGUAGE plpgsql AS $f$
DECLARE v_state jsonb := bat_bien.state(p_ids, 0); v_out jsonb; v_step jsonb; v_res jsonb;
BEGIN
    v_out := jsonb_build_array(v_state);
    FOR v_step IN SELECT value FROM jsonb_array_elements(p_steps) LOOP
        PERFORM set_config('sokhach.actor', v_step->>'actor', true);
        v_res := bat_bien.try(v_step->>'sql');
        v_state := bat_bien.state(p_ids, (v_state->>'max_event')::bigint);
        v_out := v_out || jsonb_build_array(jsonb_build_array(v_res, v_state));
    END LOOP;
    RETURN v_out;
END $f$;
"""


class Violation(Exception):
    def __init__(self, code: str, detail: str):
        super().__init__(f"[{code}] {detail}")
        self.code = code
        self.detail = detail


def violate(condition: bool, code: str, detail: str) -> None:
    if not condition:
        raise Violation(code, detail)


class Raw(str):
    """Đoạn SQL chèn nguyên vào đối số (truy id/mã phiếu theo ghi chú/tham chiếu giả)."""

    __slots__ = ()


def sql_value(value) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, Raw):
        return str(value)
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    return lit(value)


def month_of(day: str) -> str:
    return day[:8] + "01"


def months_back(today: date, n: int) -> str:
    y, m = today.year, today.month - n
    while m <= 0:
        y, m = y - 1, m + 12
    return f"{y:04d}-{m:02d}-01"


def dmy(day: str | None) -> str | None:
    return None if day is None else f"{day[8:10]}/{day[5:7]}/{day[:4]}"


def norm_lines(items) -> list[tuple[str, str, int]]:
    """Dòng phân bổ (tháng, loại, tiền) theo thứ tự cố định, từ ảnh DB hoặc snapshot trong Lịch sử."""
    out = []
    for item in items:
        if isinstance(item, dict):
            out.append((str(item["month"])[:10], item["kind"], int(item["amount_vnd"])))
        else:
            out.append((str(item[0])[:10], item[1], int(item[2])))
    return sorted(out, key=lambda x: (x[0], 0 if x[1] == "debt" else 1, x[2]))


# ---------------------------------------------------------------- bóng sổ: chỉ giữ thứ đã ghi, không tính FIFO
@dataclass
class Trip:
    note: str  # ghi chú giả duy nhất, dùng để tìm id chuyến trong DB
    month: str
    day: str | None
    container: str  # "" là dòng chỉ phụ phí
    unit: int | None
    fee: int | None
    status: str = "confirmed"
    deleted: bool = False
    delta: int = 0  # tổng điều chỉnh chuyến (adjust_trip)
    adj_rows: int = 0

    def base(self) -> int | None:
        """V7-BE: có đơn giá thì đơn giá + phụ phí (trống tính 0); dòng chỉ phụ phí là phụ phí; còn lại NULL."""
        if self.unit is not None:
            return self.unit + (self.fee or 0)
        return self.fee if self.container == "" else None

    def counted(self) -> bool:
        return not self.deleted and self.status == "confirmed"


@dataclass
class Adj:
    note: str
    month: str
    amount: int
    deleted: bool = False


@dataclass
class Receipt:
    ref: str  # tham chiếu giả duy nhất, dùng để tìm mã phiếu trong DB
    day: str
    amount: int
    method: str
    voided: bool = False
    pair: int | None = None  # chỉ mục cấn trừ nếu là phiếu đích của cấn trừ


@dataclass
class Offset:
    ref: str  # tham chiếu của phiếu đích
    source: int  # chỉ mục sổ
    target: int
    amount: int
    day: str
    voided: bool = False


@dataclass
class Book:
    idx: int
    id: int
    openings: dict[str, int]
    trips: list[Trip] = field(default_factory=list)
    adjs: list[Adj] = field(default_factory=list)
    receipts: list[Receipt] = field(default_factory=list)
    locks: dict[str, bool] = field(default_factory=dict)
    version: int = 0

    @property
    def name(self) -> str:
        return "ABCDEFGH"[self.idx]


class Shadow:
    """Bóng sổ của một chuỗi: lập câu lệnh, luật chờ (nhận hay mã từ chối) và cập nhật khi luật chờ được nhận."""

    def __init__(self, label: str, setup: list[dict], ids: list[int], today: date):
        self.label = label
        self.today = today
        self.books = [Book(i, ids[i], {months_back(today, n): amount for n, amount in spec["openings"]},
                           locks={months_back(today, n): False for n in range(WINDOW)})
                      for i, spec in enumerate(setup)]
        self.offsets: list[Offset] = []
        self.initial = copy.deepcopy((self.books, self.offsets))
        self.plans: list[dict] = []
        self.serial = 0

    def locked(self, book: Book, month: str) -> bool:
        """Thiếu dòng month_state thì chỉ tháng hiện tại (giờ VN) mở (V7-SO)."""
        return book.locks.get(month, month != months_back(self.today, 0))

    def day(self, k: int) -> str:
        return (self.today - timedelta(days=k)).isoformat()

    def charges(self, book: Book) -> tuple[dict[str, int], set[str]]:
        """Phát sinh có số theo tháng và tập tháng phát sinh (kể cả tháng chỉ có chuyến chưa giá) của sổ."""
        total: dict[str, int] = {}
        months: set[str] = set()

        def add(month: str, amount: int | None) -> None:
            months.add(month)
            if amount is not None:
                total[month] = total.get(month, 0) + amount

        for month, amount in book.openings.items():
            add(month, amount)
        for trip in book.trips:
            if trip.counted():
                add(trip.month, trip.base())
                if trip.adj_rows:
                    add(trip.month, trip.delta)
        for adj in book.adjs:
            if not adj.deleted:
                add(adj.month, adj.amount)
        for off in self.offsets:
            if off.source == book.idx and not off.voided:
                add(month_of(off.day), off.amount)
        return total, months

    def expected_total(self, book: Book) -> int:
        return sum(self.charges(book)[0].values()) - sum(r.amount for r in book.receipts if not r.voided)

    def has_charge_row(self, book: Book, month: str) -> bool:
        """Điều kiện MONTH_NOT_FOUND của adjust_month: opening, chuyến đã duyệt còn hiệu lực, điều chỉnh còn hiệu lực."""
        return (month in book.openings or any(t.counted() and t.month == month for t in book.trips)
                or any(not a.deleted and a.month == month for a in book.adjs))

    @staticmethod
    def duplicate(container: str, day: str, others) -> bool:
        """WEB_DUPLICATE/BATCH_DUPLICATE: cùng container và ngày lệch không quá 3 ngày (booking trống)."""
        d = date.fromisoformat(day)
        return any(c == container and o is not None and abs((date.fromisoformat(o) - d).days) <= 3 for c, o in others)

    # ---- truy id trong DB theo ghi chú/tham chiếu giả ----
    @staticmethod
    def trip_id(book: Book, trip: Trip) -> Raw:
        return Raw(f"(SELECT id FROM sokhach.trip WHERE customer_id={book.id} AND note={lit(trip.note)})")

    @staticmethod
    def pid(book: Book, rec: Receipt) -> Raw:
        return Raw(f"(SELECT pid FROM sokhach.receipt WHERE customer_id={book.id} AND reference={lit(rec.ref)})")

    @staticmethod
    def adj_id(book: Book, adj: Adj) -> Raw:
        return Raw(f"(SELECT id FROM sokhach.adjustment WHERE customer_id={book.id} AND note={lit(adj.note)}"
                   " AND trip_id IS NULL AND reverses_adjustment_id IS NULL)")

    @staticmethod
    def pair_id(off: Offset) -> Raw:
        return Raw("(SELECT p.id FROM sokhach.offset_pair p JOIN sokhach.receipt r ON r.id=p.target_receipt_id"
                   f" WHERE r.reference={lit(off.ref)})")

    def tag(self, kind: str) -> str:
        self.serial += 1
        return f"bb-{self.label}-{kind}{self.serial}"

    @staticmethod
    def call(fn: str, *args) -> str:
        return f"SELECT sokhach.{fn}({','.join(sql_value(a) for a in args)})"

    # ---- một lệnh ----
    def step(self, op: dict) -> dict | None:
        """Lập lệnh; luật chờ được nhận thì cập nhật bóng sổ. None nếu lệnh trỏ tới thứ không có (sau rút gọn)."""
        plan = self.plan(op)
        if plan is None:
            return None
        plan["actor"] = f"bat-bien {self.label}.{len(self.plans) + 1}"
        if plan["expect"] is None and plan.get("replay_of") is None:
            plan["apply"]()
            for idx in plan["touch"]:
                self.books[idx].version += 1
        plan.pop("apply", None)
        plan["after"] = copy.deepcopy((self.books, self.offsets))
        self.plans.append(plan)
        return plan

    def plan(self, op: dict) -> dict | None:
        kind = op["op"]
        cm = months_back(self.today, 0)
        plan: dict = {"touch": {}, "event_check": {}, "freeze": [], "unfreeze": [],
                      "locks_before": [(lambda m, lk=dict(b.locks): lk.get(m, m != cm)) for b in self.books]}
        if kind == "replay":
            done = [i for i, p in enumerate(self.plans) if p["expect"] is None and p.get("replay_of") is None]
            if not done:
                return None
            first = self.plans[done[-1]]
            plan.update(sql=first["sql"], text=f"gửi lặp lệnh {done[-1] + 1} ({first['text']})", expect=None,
                        replay_of=done[-1])
            return plan
        book = self.books[op["b"]]
        today = self.today.isoformat()

        def touch(idx: int, ev_kind: str, check=None, *, realloc=True):
            plan["touch"][idx] = ev_kind
            if check is not None:
                plan["event_check"][idx] = check
            if realloc:
                plan["unfreeze"].append(idx)

        if kind == "paste":
            month = months_back(self.today, op["month"])
            rows, payload, desc = [], [], []
            seen = [(t.container, t.day) for t in book.trips if not t.deleted and t.container]
            for row in op["rows"]:
                note = self.tag("t")
                if row.get("fee_only"):
                    day = None if row["k"] is None else self.day(row["k"])
                    rows.append(Trip(note, month_of(day) if day else month, day, "", None, row["fee"]))
                    payload.append({"container": "", "date": dmy(day), "note": note, "src": "FAKE",
                                    "unitPriceVnd": None, "otherFeeVnd": str(row["fee"])})
                    desc.append(f"phụ phí {row['fee']} ngày {day or 'trống'}")
                    continue
                source = book.trips[row["dup"][0]] if row.get("dup") and row["dup"][0] < len(book.trips) else None
                if source is not None and source.container and source.day:
                    container = source.container
                    day = (date.fromisoformat(source.day) + timedelta(days=row["dup"][1])).isoformat()
                else:
                    container = f"FAKE{self.label.upper()}C{self.serial}"
                    day = self.day(row["k"])
                status = "pending_review" if self.duplicate(container, day, seen) else "confirmed"
                seen.append((container, day))
                rows.append(Trip(note, month_of(day), day, container, row["unit"], row["fee"], status))
                payload.append({"container": container, "carrier": "FAKE", "date": dmy(day), "from": "FAKE-A",
                                "to": "FAKE-B", "note": note, "src": "FAKE",
                                "unitPriceVnd": None if row["unit"] is None else str(row["unit"]),
                                "otherFeeVnd": None if row["fee"] is None else str(row["fee"])})
                desc.append(f"{container} ngày {day} giá {row['unit']} phụ phí {row['fee']}"
                            + (" (trùng → chờ kiểm)" if status != "confirmed" else ""))
            future = any(t.day is not None and t.day > today for t in rows)
            count = len(rows)
            touch(book.idx, "paste", lambda b, a: None if len(a.get("trips", [])) == count
                  else f"{len(a.get('trips', []))} chuyến, chờ {count}")
            plan.update(sql=self.call("paste_trips", book.id, book.version, self.tag("k"), month,
                                      json.dumps(payload, ensure_ascii=False)),
                        expect="FUTURE_DATE" if future else None, apply=lambda: book.trips.extend(rows),
                        text=f"sổ {book.name}: dán lô tháng {month[:7]}: " + "; ".join(desc))
            return plan

        if kind in ("price", "move", "delete_trip", "adjust_trip", "review"):
            if op["trip"] >= len(book.trips):
                return None
            trip = book.trips[op["trip"]]
            tid = self.trip_id(book, trip)
            name = (f"sổ {book.name}: chuyến {op['trip'] + 1} ({trip.container or 'phụ phí'} {trip.day or 'không ngày'},"
                    f" {trip.status}{', đã xóa' if trip.deleted else ''})")
            locked = self.locked(book, trip.month)
            if kind == "price":
                unit, fee = op["unit"], op["fee"]
                expect = ("TRIP_NOT_FOUND" if trip.deleted else "TRIP_PENDING_REVIEW" if trip.status != "confirmed"
                          else "MONTH_LOCKED" if locked else "NO_CHANGE" if (trip.unit, trip.fee) == (unit, fee)
                          else "INVALID_FEE_ONLY_DATE" if trip.day is None and (unit is not None or fee is None) else None)
                old, new = (trip.unit, trip.fee), (unit, fee)

                def apply():
                    trip.unit, trip.fee = unit, fee

                def check(b, a):
                    got = ((b["price"].get("unit_price_vnd"), b["price"].get("other_fee_vnd")),
                           (a["price"].get("unit_price_vnd"), a["price"].get("other_fee_vnd")))
                    return None if got == (old, new) else f"ghi {got}, chờ {(old, new)}"

                touch(book.idx, "price_edit", check)
                plan.update(sql=self.call("edit_trip_price", book.id, book.version, self.tag("k"), tid, unit, fee),
                            expect=expect, apply=apply, text=f"{name}: sửa giá/phụ phí {old} → {new}")
            elif kind == "move":
                day = self.day(op["k"])
                new_month = month_of(day)
                expect = ("TRIP_NOT_FOUND" if trip.deleted else "MONTH_LOCKED" if locked
                          else "FUTURE_DATE" if day > today else "NO_CHANGE" if trip.day == day
                          else "MONTH_LOCKED" if new_month != trip.month and self.locked(book, new_month) else None)
                others = [(t.container, t.day) for t in book.trips if t is not trip and not t.deleted and t.container]
                to_pending = trip.status == "confirmed" and trip.container != "" and self.duplicate(trip.container, day, others)
                old_day = trip.day

                def apply():
                    trip.day, trip.month = day, new_month
                    if to_pending:
                        trip.status = "pending_review"

                touch(book.idx, "trip_edit", lambda b, a: None if (b["trip"].get("value"), a["trip"].get("value"))
                      == (old_day, day) else f"ghi {b['trip'].get('value')} → {a['trip'].get('value')}")
                plan.update(sql=self.call("edit_trip_info", book.id, book.version, self.tag("k"), tid, "event_date", day),
                            expect=expect, apply=apply,
                            text=f"{name}: đổi ngày {old_day} → {day}" + (" (trùng → chờ kiểm)" if to_pending else ""))
            elif kind == "delete_trip":
                expect = "TRIP_NOT_FOUND" if trip.deleted else "MONTH_LOCKED" if locked else None

                def apply():
                    trip.deleted = True

                touch(book.idx, "trip_delete")
                plan.update(sql=self.call("delete_trip", book.id, book.version, self.tag("k"), tid),
                            expect=expect, apply=apply, text=f"{name}: xóa chuyến")
            elif kind == "adjust_trip":
                base = trip.base()
                current = None if base is None else base + trip.delta
                new_amount = max(0, (current or 0) + op["delta"])
                expect = ("TRIP_NOT_FOUND" if trip.deleted else "TRIP_PENDING_REVIEW" if trip.status != "confirmed"
                          else "MONTH_LOCKED" if locked else "TRIP_HAS_NO_PRICE" if base is None
                          else "NO_CHANGE" if new_amount == current else None)

                def apply():
                    trip.delta += new_amount - current
                    trip.adj_rows += 1

                touch(book.idx, "adjust_trip", lambda b, a: None if (b.get("amount_vnd"), a.get("new_amount_vnd"))
                      == (str(current), str(new_amount)) else f"ghi {b.get('amount_vnd')} → {a.get('new_amount_vnd')}")
                plan.update(sql=self.call("adjust_trip", book.id, book.version, self.tag("k"), tid, new_amount, "bat bien"),
                            expect=expect, apply=apply, text=f"{name}: điều chỉnh thành tiền {current} → {new_amount}")
            else:  # review
                decision = op["decision"]
                expect = ("TRIP_NOT_FOUND" if trip.deleted else "TRIP_NOT_PENDING" if trip.status != "pending_review"
                          else "MONTH_LOCKED" if locked else None)

                def apply():
                    trip.status = "confirmed" if decision == "confirm" else "rejected"

                touch(book.idx, "trip_review", realloc=decision == "confirm")
                plan.update(sql=self.call("review_trip", book.id, book.version, self.tag("k"), tid, decision, "bat bien"),
                            expect=expect, apply=apply, text=f"{name}: duyệt chờ kiểm '{decision}'")
            return plan

        if kind == "adjust_month":
            month = months_back(self.today, op["month"])
            amount = op["amount"]
            note = self.tag("a")
            expect = ("MONTH_NOT_FOUND" if not self.has_charge_row(book, month)
                      else "MONTH_LOCKED" if self.locked(book, month) else None)
            touch(book.idx, "adjust_month", lambda b, a: None if (b.get("amount_vnd"), a.get("amount_vnd"))
                  == ("0", str(amount)) else f"ghi {b.get('amount_vnd')} → {a.get('amount_vnd')}")
            plan.update(sql=self.call("adjust_month", book.id, book.version, self.tag("k"), month, amount, note),
                        expect=expect, apply=lambda: book.adjs.append(Adj(note, month, amount)),
                        text=f"sổ {book.name}: điều chỉnh tháng {month[:7]} {amount:+d}")
            return plan

        if kind == "delete_adjustment":
            if op["adj"] >= len(book.adjs):
                return None
            adj = book.adjs[op["adj"]]
            expect = "ADJUSTMENT_NOT_FOUND" if adj.deleted else "MONTH_LOCKED" if self.locked(book, adj.month) else None

            def apply():
                adj.deleted = True

            touch(book.idx, "adjust_month_delete",
                  lambda b, a: None if (b["adjustment"].get("amount_vnd"), a["adjustment"].get("amount_vnd"))
                  == (str(adj.amount), "0") else f"ghi {b['adjustment'].get('amount_vnd')} → {a['adjustment'].get('amount_vnd')}")
            plan.update(sql=self.call("delete_month_adjustment", book.id, book.version, self.tag("k"),
                                      self.adj_id(book, adj)),
                        expect=expect, apply=apply,
                        text=f"sổ {book.name}: xóa điều chỉnh {op['adj'] + 1} ({adj.month[:7]} {adj.amount:+d})")
            return plan

        if kind == "receipt":
            day, amount, method = self.day(op["k"]), op["amount"], op["method"]
            ref = self.tag("r")
            expect = "FUTURE_RECEIPT_DATE" if day > today else None
            touch(book.idx, "receipt", lambda b, a: None if a.get("amount_vnd") == str(amount)
                  else f"ghi {a.get('amount_vnd')}, chờ {amount}")
            plan.update(sql=self.call("record_receipt", book.id, book.version, self.tag("k"), day, method, amount, ref),
                        expect=expect, apply=lambda: book.receipts.append(Receipt(ref, day, amount, method)),
                        text=f"sổ {book.name}: ghi thu {amount} ngày {day} ({method})")
            return plan

        if kind in ("edit_receipt", "void"):
            if op["receipt"] >= len(book.receipts):
                return None
            rec = book.receipts[op["receipt"]]
            pid = self.pid(book, rec)
            name = f"sổ {book.name}: phiếu {op['receipt'] + 1} ({rec.day}, {rec.amount}{', đã hủy' if rec.voided else ''})"
            if kind == "edit_receipt":
                day = None if op["k"] is None else self.day(op["k"])
                method = op["method"]
                new = (day or rec.day, method or rec.method)
                old = (rec.day, rec.method)
                expect = ("OFFSET_PAIR_REQUIRED" if rec.pair is not None else "RECEIPT_NOT_FOUND" if rec.voided
                          else "FUTURE_RECEIPT_DATE" if new[0] > today else "NO_CHANGE" if new == old else None)

                def apply():
                    rec.day, rec.method = new

                touch(book.idx, "receipt_edit", lambda b, a: None if ((b.get("date"), b.get("method")),
                                                                     (a.get("date"), a.get("method"))) == (old, new)
                      else f"ghi {(b.get('date'), b.get('method'))} → {(a.get('date'), a.get('method'))}",
                      realloc=new[0] != old[0])
                plan.update(sql=self.call("edit_receipt_meta", book.id, book.version, self.tag("k"), pid, day, method),
                            expect=expect, apply=apply, text=f"{name}: sửa ngày {day} hình thức {method}")
            else:
                reason = op["reason"]
                expect = ("OFFSET_PAIR_REQUIRED" if rec.pair is not None else "VOID_REASON_REQUIRED" if not reason.strip()
                          else "RECEIPT_ALREADY_VOID" if rec.voided else None)

                def apply():
                    rec.voided = True

                touch(book.idx, "void", lambda b, a: None if (b.get("amount_vnd"), a.get("void_reason"))
                      == (str(rec.amount), reason.strip()) else f"ghi {b.get('amount_vnd')} lý do {a.get('void_reason')!r}",
                      realloc=False)
                plan["freeze"].append(book.idx)
                plan.update(sql=self.call("void_receipt", book.id, book.version, self.tag("k"), pid, reason),
                            expect=expect, apply=apply, void=(book.idx, rec.ref), text=f"{name}: hủy, lý do {reason!r}")
            return plan

        if kind == "lock":
            month = months_back(self.today, op["month"])
            old, new = self.locked(book, month), op["locked"]

            def apply():
                book.locks[month] = new

            touch(book.idx, "month_lock", lambda b, a: None if (b.get("locked"), a.get("locked")) == (old, new)
                  else f"ghi {b.get('locked')} → {a.get('locked')}, chờ {old} → {new}", realloc=False)
            plan.update(sql=self.call("set_month_lock", book.id, book.version, self.tag("k"), month, new),
                        expect=None, apply=apply, text=f"sổ {book.name}: {'khóa' if new else 'mở'} tháng {month[:7]}")
            return plan

        if kind == "offset":
            target = self.books[op["t"]]
            day = self.day(op["k"])
            credit = max(-self.expected_total(book), 0)
            amount = max(1, credit * op["share"] // 100) if op["share"] else op["amount"]
            ref = self.tag("o")
            expect = "FUTURE_DATE" if day > today else "OFFSET_EXCEEDS_CREDIT" if amount > credit else None

            def apply():
                self.offsets.append(Offset(ref, book.idx, target.idx, amount, day))
                target.receipts.append(Receipt(ref, day, amount, "CẤN TRỪ", pair=len(self.offsets) - 1))

            touch(book.idx, "receipt", lambda b, a: None if a.get("amount_vnd") == str(-amount)
                  else f"sổ nguồn ghi {a.get('amount_vnd')}, chờ {-amount}")
            touch(target.idx, "receipt", lambda b, a: None if a.get("amount_vnd") == str(amount)
                  else f"sổ đích ghi {a.get('amount_vnd')}, chờ {amount}")
            plan.update(sql=self.call("record_offset", target.id, target.version, book.id, book.version, self.tag("k"),
                                      day, amount, ref),
                        expect=expect, apply=apply, offset=(book.idx, target.idx, amount),
                        text=f"cấn trừ {amount} từ sổ {book.name} (dư có {credit}) sang sổ {target.name} ngày {day}")
            return plan

        if kind in ("void_offset", "edit_offset"):
            if op["pair"] >= len(self.offsets):
                return None
            off = self.offsets[op["pair"]]
            src, tgt = self.books[off.source], self.books[off.target]
            caller, other = (src, tgt) if op["side"] == 0 else (tgt, src)
            rec = next(r for r in tgt.receipts if r.ref == off.ref)
            name = (f"cấn trừ {op['pair'] + 1} ({off.amount}, {src.name} → {tgt.name}, {off.day}"
                    f"{', đã hủy' if off.voided else ''}, gọi từ sổ {caller.name})")
            if kind == "void_offset":
                reason = op["reason"]
                expect = "OFFSET_ALREADY_VOID" if off.voided else "VOID_REASON_REQUIRED" if not reason.strip() else None

                def apply():
                    off.voided = rec.voided = True

                touch(src.idx, "void", lambda b, a: None if a.get("void_reason") == reason.strip()
                      else f"lý do {a.get('void_reason')!r}")
                touch(tgt.idx, "void", realloc=False)
                plan["freeze"].append(tgt.idx)
                plan.update(sql=self.call("void_offset", caller.id, caller.version, other.version, self.tag("k"),
                                          self.pair_id(off), reason),
                            expect=expect, apply=apply, offset=(src.idx, tgt.idx, -off.amount), void=(tgt.idx, off.ref),
                            text=f"{name}: hủy, lý do {reason!r}")
            else:
                day = self.day(op["k"])
                expect = ("OFFSET_ALREADY_VOID" if off.voided else "FUTURE_DATE" if day > today
                          else "NO_CHANGE" if day == off.day else None)
                old_day = off.day

                def apply():
                    off.day = rec.day = day

                touch(src.idx, "receipt_edit", lambda b, a: None if (b.get("date"), a.get("date")) == (old_day, day)
                      else f"ghi {b.get('date')} → {a.get('date')}, chờ {old_day} → {day}")
                touch(tgt.idx, "receipt_edit")
                plan.update(sql=self.call("edit_offset_date", caller.id, caller.version, other.version, self.tag("k"),
                                          self.pair_id(off), day),
                            expect=expect, apply=apply, offset=(src.idx, tgt.idx, 0),
                            text=f"{name}: đổi ngày {old_day} → {day}")
            return plan
        raise HarnessError(f"lệnh lạ {kind}")


# ---------------------------------------------------------------- kiểm từng bước trên ảnh DB
class Verifier:
    def __init__(self, shadow: Shadow, states: list[dict], outcomes: list[dict]):
        self.s = shadow
        self.states = states
        self.outcomes = outcomes
        self.frozen: dict[int, dict | None] = dict.fromkeys(range(len(shadow.books)))

    def run(self) -> None:
        """Kiểm lần lượt từng bước; vi phạm thì ném Violation."""
        books, offsets = self.s.initial
        self.check_static(books, offsets, self.states[0], "mở sổ")
        for i, plan in enumerate(self.s.plans):
            p, n, outcome = self.states[i], self.states[i + 1], self.outcomes[i]
            error = outcome.get("error")
            self.check_outcome(plan, outcome)
            self.check_step(plan, error, p, n)
            if error is None and plan.get("replay_of") is None:
                for idx in plan["unfreeze"]:
                    self.frozen[idx] = None
                for idx in plan["freeze"]:
                    if self.frozen[idx] is None:
                        snap = p["books"][str(self.s.books[idx].id)]["receipts"]
                        self.frozen[idx] = {pid: norm_lines(v[5]) for pid, v in snap.items() if not v[4]}
                self.check_void(plan, p, n)
            books, offsets = plan["after"]
            self.check_static(books, offsets, n, f"bước {i + 1}")

    def check_outcome(self, plan, outcome) -> None:
        error = outcome.get("error")
        if plan.get("replay_of") is not None:
            first = self.outcomes[plan["replay_of"]]
            violate(outcome == first, "nguyen-tu", f"{plan['text']}: trả khác lần đầu\n  lần đầu: {first}\n  gửi lặp: {outcome}")
            return
        expect = plan["expect"]
        if (expect is None and error is None) or (expect is not None and error is not None and expect in error):
            return
        code = {"FUTURE_DATE": "tuong-lai", "FUTURE_RECEIPT_DATE": "tuong-lai", "MONTH_LOCKED": "thang-khoa",
                "VOID_REASON_REQUIRED": "huy-phieu", "OFFSET_EXCEEDS_CREDIT": "can-tru"}.get(expect or "", "ket-qua")
        if expect is None and error and "MONTH_LOCKED" in error:
            code = "thang-khoa"
        raise Violation(code, f"{plan['text']}: luật chờ {'được nhận' if expect is None else 'bị từ chối ' + expect},"
                              f" DB {'được nhận' if error is None else 'từ chối ' + error}")

    def check_step(self, plan, error, p, n) -> None:
        quiet = error is not None or plan.get("replay_of") is not None
        touched = {} if quiet else plan["touch"]
        for book in self.s.books:
            pb, nb = p["books"][str(book.id)], n["books"][str(book.id)]
            violate(nb["events_old"] == pb["events_all"], "lich-su", f"sổ {book.name}: dòng Lịch sử cũ bị sửa hoặc xóa")
            new = nb["events_new"]
            if book.idx not in touched:
                code = "nguyen-tu" if quiet else "lich-su"
                violate(nb["version"] == pb["version"], code,
                        f"{plan['text']}: sổ {book.name} version {pb['version']} → {nb['version']} dù lệnh không ghi sổ này")
                violate(not new, code, f"{plan['text']}: sổ {book.name} có Lịch sử mới {[(e[1], e[2]) for e in new]}"
                                       " dù lệnh không ghi sổ này")
                if quiet:
                    for key in ("receipts", "trips", "adjs", "total", "locks"):
                        violate(nb[key] == pb[key], "nguyen-tu",
                                f"{plan['text']}: sổ {book.name} {'bị từ chối' if error else 'gửi lặp'} mà '{key}' đổi")
                continue
            violate(nb["version"] == pb["version"] + 1, "lich-su",
                    f"{plan['text']}: sổ {book.name} version {pb['version']} → {nb['version']} (chờ +1)")
            violate(bool(new), "lich-su", f"{plan['text']}: sổ {book.name} được nhận mà không có dòng Lịch sử")
            for event_id, kind, who, ev_before, ev_after in new:
                violate(who == plan["actor"], "lich-su",
                        f"{plan['text']}: Lịch sử {event_id} ({kind}) ghi người '{who}', chờ '{plan['actor']}'")
                violate(isinstance(ev_before, dict) and isinstance(ev_after, dict), "lich-su",
                        f"{plan['text']}: Lịch sử {event_id} thiếu trước/sau")
            main = [e for e in new if e[1] != "reallocation"]
            want = plan["touch"][book.idx]
            violate([e[1] for e in main] == [want], "lich-su",
                    f"{plan['text']}: sổ {book.name} Lịch sử chính {[e[1] for e in main]}, chờ ['{want}']")
            check = plan["event_check"].get(book.idx)
            if check:
                problem = check(main[0][3], main[0][4])
                violate(problem is None, "lich-su", f"{plan['text']}: sổ {book.name} trước → sau của '{want}' sai: {problem}")
            self.check_reallocation_events(plan, book, pb, nb, new)
        self.check_locked_months(plan, p, n)
        if not quiet and plan.get("offset"):
            src, tgt, d_src = plan["offset"]
            tot = {i: (int(p["books"][str(b.id)]["total"]), int(n["books"][str(b.id)]["total"]))
                   for i, b in enumerate(self.s.books)}
            violate(tot[src][0] + tot[tgt][0] == tot[src][1] + tot[tgt][1], "can-tru",
                    f"{plan['text']}: tổng hai sổ đổi {tot[src][0]}+{tot[tgt][0]} → {tot[src][1]}+{tot[tgt][1]}")
            violate(tot[src][1] - tot[src][0] == d_src, "can-tru",
                    f"{plan['text']}: sổ nguồn đổi {tot[src][1] - tot[src][0]}, chờ {d_src}")

    @staticmethod
    def check_reallocation_events(plan, book: Book, pb, nb, new) -> None:
        """Dòng phân bổ đổi đều có Lịch sử ghi đúng trước → sau; không đổi lặng lẽ."""
        by_id = {v[0]: pid for pid, v in nb["receipts"].items()}
        current = {pid: norm_lines(v[5]) for pid, v in pb["receipts"].items()}
        for _event_id, kind, _who, ev_before, ev_after in new:
            if kind == "receipt" and "allocations" in ev_after and "pid" in ev_after:
                current[ev_after["pid"]] = norm_lines(ev_after["allocations"])
            elif kind == "reallocation":
                pid = by_id.get(int(ev_after["receipt"]))
                violate(pid is not None, "lich-su", f"{plan['text']}: phân bổ lại cho phiếu lạ {ev_after['receipt']}")
                violate(norm_lines(ev_before["allocations"]) == current.get(pid, []), "lich-su",
                        f"{plan['text']}: Lịch sử phân bổ lại {pid} ghi trước {norm_lines(ev_before['allocations'])},"
                        f" thật là {current.get(pid, [])}")
                current[pid] = norm_lines(ev_after["allocations"])
            elif kind == "void" and "pid" in ev_after:
                current[ev_after["pid"]] = []
        for pid, v in nb["receipts"].items():
            want = [] if v[4] else norm_lines(v[5])
            violate(current.get(pid, []) == want, "lich-su",
                    f"{plan['text']}: sổ {book.name} phiếu {pid} đổi dòng phân bổ mà Lịch sử không ghi:"
                    f" Lịch sử {current.get(pid)}, DB {want}")

    def check_void(self, plan, p, n) -> None:
        """Hủy phiếu (kể cả phiếu đích của cấn trừ) không đổi dòng phân bổ của phiếu khác trong sổ đó."""
        if plan.get("void") is None:
            return
        idx, ref = plan["void"]
        book = self.s.books[idx]
        pr, nr = p["books"][str(book.id)]["receipts"], n["books"][str(book.id)]["receipts"]
        pid = next(k for k, v in nr.items() if v[7] == ref)
        for other, v in pr.items():
            if other != pid and not v[4]:
                violate(norm_lines(nr[other][5]) == norm_lines(v[5]), "huy-phieu",
                        f"{plan['text']}: phiếu {other} đổi phân bổ {norm_lines(v[5])} → {norm_lines(nr[other][5])}")
        violate(nr[pid][4] and nr[pid][5] == [], "huy-phieu", f"{plan['text']}: phiếu {pid} hủy mà còn dòng phân bổ")
        violate(bool((nr[pid][6] or "").strip()), "huy-phieu", f"{plan['text']}: phiếu {pid} hủy mà không có lý do")

    def check_locked_months(self, plan, p, n) -> None:
        """Tháng khóa (trước bước này) không đổi chuyến/điều chỉnh có sẵn; chỉ được thêm chuyến dán mới."""
        for book in self.s.books:
            locked = plan["locks_before"][book.idx]
            pb, nb = p["books"][str(book.id)], n["books"][str(book.id)]
            months = {v[0] for v in pb["trips"].values()} | {v[0] for v in nb["trips"].values()}
            months |= {v[0] for v in pb["adjs"].values()} | {v[0] for v in nb["adjs"].values()}
            for month in sorted(m for m in months if locked(m)):
                old = {k: v for k, v in pb["trips"].items() if v[0] == month}
                for trip_id, row in old.items():
                    violate(nb["trips"].get(trip_id) == row, "thang-khoa",
                            f"{plan['text']}: sổ {book.name} chuyến {trip_id} của tháng khóa {month[:7]} bị đổi"
                            f" {row} → {nb['trips'].get(trip_id)}")
                for trip_id, row in nb["trips"].items():
                    if row[0] == month and trip_id not in old:
                        violate(trip_id not in pb["trips"], "thang-khoa",
                                f"{plan['text']}: sổ {book.name} chuyến {trip_id} được chuyển vào tháng khóa {month[:7]}")
                old_adj = sorted(k for k, v in pb["adjs"].items() if v[0] == month)
                new_adj = sorted(k for k, v in nb["adjs"].items() if v[0] == month)
                violate(old_adj == new_adj, "thang-khoa",
                        f"{plan['text']}: sổ {book.name} điều chỉnh tháng khóa {month[:7]} đổi {old_adj} → {new_adj}")

    def check_static(self, books: list[Book], offsets: list[Offset], n: dict, label: str) -> None:
        """Bất biến của từng sổ ở trạng thái sau bước (không cần biết lệnh)."""
        shadow = copy.copy(self.s)
        shadow.books, shadow.offsets = books, offsets
        first = self.states[0]
        for book in books:
            nb = n["books"][str(book.id)]
            where = f"sau {label}, sổ {book.name}"
            violate(nb["version"] == book.version and nb["ledger_version"] == book.version, "lich-su",
                    f"{where}: version {nb['version']}, chờ {book.version}")
            violate(nb["future"] == 0, "tuong-lai", f"{where}: có {nb['future']} ngày ở tương lai trong sổ")
            numbers = [nb["total"], nb["raw"]] + [x for m in nb["months"] for x in m[1:]]
            numbers += [x for t in nb["ltrips"].values() for x in (t[1], t[2], t[3]) if x is not None]
            for x in numbers:
                violate(isinstance(x, str) and bool(MONEY.match(x)), "so-du", f"{where}: số tiền không phải VND nguyên: {x!r}")
            total, want = int(nb["total"]), shadow.expected_total(book)
            violate(total == want, "so-du", f"{where}: tổng còn phải thu {total}, theo bút toán đã ghi là {want}")
            violate(int(nb["raw"]) == total, "so-du", f"{where}: tổng nợ thô {nb['raw']} khác tổng {total}")
            months = nb["months"]
            violate(sum(int(m[1]) for m in months) == total, "so-du", f"{where}: cộng nợ các tháng khác tổng")
            for m in months:
                violate(int(m[4]) + int(m[2]) - int(m[3]) == int(m[5]), "so-du",
                        f"{where}: tháng {m[0][:7]} đầu {m[4]} + phát sinh {m[2]} − thu {m[3]} ≠ cuối {m[5]}")
            if months:
                violate(int(months[-1][5]) == total, "so-du", f"{where}: số cuối tháng cuối {months[-1][5]} ≠ tổng {total}")
            fb = first["books"][str(book.id)]
            violate(nb["opening"] == fb["opening"], "opening", f"{where}: dòng opening bị đổi")
            violate(nb["legacy"] == fb["legacy"], "opening", f"{where}: dòng lịch sử trong opening bị đổi")
            violate(nb["locks"] == book.locks, "thang-khoa", f"{where}: khóa tháng DB {nb['locks']}, chờ {book.locks}")
            self.check_trips(book, nb, where)
            self.check_fifo(shadow, book, nb, where)

    @staticmethod
    def check_trips(book: Book, nb, where: str) -> None:
        live = [t for t in book.trips if not t.deleted]
        violate(set(nb["ltrips"]) == {t.note for t in live}, "so-du", f"{where}: danh sách chuyến khác bút toán đã ghi")
        pending = 0
        for i, trip in enumerate(live):
            status, unit, fee, amount, missing, month = nb["ltrips"][trip.note]
            name = f"chuyến {i + 1} ({trip.container or 'phụ phí'})"
            violate(status == trip.status, "pending", f"{where}: {name} trạng thái {status}, chờ {trip.status}")
            violate(month == trip.month, "so-du", f"{where}: {name} ở tháng {month}, chờ {trip.month}")
            violate((None if unit is None else int(unit)) == trip.unit, "null",
                    f"{where}: {name} đơn giá {unit!r}, đã ghi {trip.unit!r}")
            violate((None if fee is None else int(fee)) == trip.fee, "null",
                    f"{where}: {name} phụ phí {fee!r}, đã ghi {trip.fee!r}")
            want = trip.base() if trip.status == "confirmed" else None
            violate((None if amount is None else int(amount)) == want, "pending" if want is None else "null",
                    f"{where}: {name} ({trip.status}, đơn giá {trip.unit}, phụ phí {trip.fee}) thành tiền {amount!r},"
                    f" chờ {want!r}")
            no_price = trip.unit is None and not (trip.fee is not None and trip.container == "")
            violate(missing is no_price, "null", f"{where}: {name} cờ thiếu giá {missing}, chờ {no_price}")
            pending += trip.status == "pending_review" or no_price
        violate(nb["pending_count"] == pending, "pending", f"{where}: đếm chuyến chờ {nb['pending_count']}, chờ {pending}")

    def check_fifo(self, shadow: Shadow, book: Book, nb, where: str) -> None:
        charges, months = shadow.charges(book)
        last = max(months) if months else None
        live = sorted(((v[1], pid, int(v[2]), norm_lines(v[5])) for pid, v in nb["receipts"].items() if not v[4]),
                      key=lambda x: (x[0], x[1].encode()))
        for pid, v in nb["receipts"].items():
            if v[4]:
                violate(v[5] == [], "fifo", f"{where}: phiếu hủy {pid} còn dòng phân bổ")
        frozen = self.frozen[book.idx]
        if frozen is not None:
            for _, pid, _, lines in live:
                violate(lines == frozen.get(pid), "huy-phieu",
                        f"{where}: từ lần hủy phiếu gần nhất chưa có lệnh phân bổ lại mà phiếu {pid} đổi"
                        f" {frozen.get(pid)} → {lines}")
        remaining = {m: charges.get(m, 0) for m in sorted(months)}
        for day, pid, amount, lines in live:
            violate(sum(x[2] for x in lines) == amount, "fifo",
                    f"{where}: phiếu {pid} số {amount} mà phân bổ {sum(x[2] for x in lines)}: {lines}")
            violate(len({(x[0], x[1]) for x in lines}) == len(lines), "fifo", f"{where}: phiếu {pid} lặp dòng {lines}")
            for month, kind, value in lines:
                violate(value > 0, "fifo", f"{where}: phiếu {pid} có dòng không dương {lines}")
                if kind == "advance":
                    violate(month == last, "fifo", f"{where}: phiếu {pid} ứng trước ở {month}, tháng phát sinh cuối là {last}")
                    continue
                left = remaining.get(month, 0)
                violate(left > 0 and value <= left, "fifo",
                        f"{where}: phiếu {pid} ({day}) trả {value} vào tháng {month[:7]} chỉ còn nợ {left}")
                remaining[month] = left - value
            if frozen is None:  # kể từ lần phân bổ lại gần nhất: đúng nợ cũ trước
                paid = [x[0] for x in lines if x[1] == "debt"]
                advance = any(x[1] == "advance" for x in lines)
                newest = "9999-12-31" if advance else max(paid) if paid else None
                if newest:
                    older = [m[:7] for m, left in remaining.items() if m < newest and left > 0]
                    violate(not older, "fifo", f"{where}: phiếu {pid} ({day}) trả "
                            f"{'ứng trước' if advance else 'tháng ' + newest[:7]} khi tháng cũ hơn {older} còn nợ")


# ---------------------------------------------------------------- bộ sinh lệnh
OPS = (("paste", 4), ("receipt", 4), ("price", 2), ("move", 1), ("delete_trip", 1), ("adjust_trip", 1),
       ("adjust_month", 2), ("delete_adjustment", 1), ("edit_receipt", 2), ("void", 2), ("lock", 2),
       ("offset", 2), ("void_offset", 1), ("edit_offset", 1), ("review", 1), ("replay", 1))
OP_NAMES = [name for name, weight in OPS for _ in range(weight)]


def day_k(rng: random.Random) -> int:
    """Số ngày lùi từ hôm nay (giờ VN); âm là ngày tương lai (~4%)."""
    return rng.randint(-7, 180)


def gen_setup(rng: random.Random, books: int) -> list[dict]:
    setup = []
    for _ in range(books):
        months = sorted(rng.sample(range(2, WINDOW + 2), rng.randint(1, 3)), reverse=True)
        openings = [(n, rng.choice([rng.randint(1, 40) * 500, rng.randint(1, 40) * 500, -rng.randint(1, 20) * 500]))
                    for n in months]
        legacy = [(months[0], "trip", rng.randint(1, 30) * 500), (months[0], "receipt", rng.randint(1, 30) * 500)]
        setup.append({"openings": openings, "legacy": legacy})
    return setup


def gen_op(rng: random.Random, shadow: Shadow) -> dict:
    name = rng.choice(OP_NAMES)
    b = rng.randrange(len(shadow.books))
    book = shadow.books[b]

    def fee():
        return None if rng.random() < 0.55 else rng.choice([rng.randint(1, 30) * 50, -rng.randint(1, 10) * 50])

    def unit():
        return None if rng.random() < 0.2 else rng.randint(1, 40) * 250

    trip_ops = ("price", "move", "delete_trip", "adjust_trip", "review")
    if name == "paste" or (name in trip_ops and not book.trips):
        rows = []
        with_container = [i for i, t in enumerate(book.trips) if t.container and t.day]
        for _ in range(rng.randint(1, 3)):
            r = rng.random()
            if r < 0.15:
                rows.append({"fee_only": True, "k": None if rng.random() < 0.4 else day_k(rng),
                             "fee": rng.choice([rng.randint(1, 30) * 50, -rng.randint(1, 10) * 50])})
            elif r < 0.3 and with_container:
                rows.append({"dup": (rng.choice(with_container), rng.randint(-3, 3)), "k": day_k(rng),
                             "unit": unit(), "fee": fee()})
            else:
                rows.append({"k": day_k(rng), "unit": unit(), "fee": fee()})
        return {"op": "paste", "b": b, "month": rng.randrange(WINDOW + 1), "rows": rows}
    if name in trip_ops:
        pending = [i for i, t in enumerate(book.trips) if t.status == "pending_review" and not t.deleted]
        live = [i for i, t in enumerate(book.trips) if not t.deleted]
        pool = pending if name == "review" and pending else live if live and rng.random() < 0.9 else range(len(book.trips))
        trip = rng.choice(list(pool))
        t = book.trips[trip]
        if name == "price":
            u, f = (t.unit, t.fee) if rng.random() < 0.05 else (unit(), fee())
            return {"op": "price", "b": b, "trip": trip, "unit": u, "fee": f}
        if name == "move":
            k = day_k(rng)
            others = [x for x in book.trips if x is not t and x.container and x.day]
            if others and rng.random() < 0.2:  # dời sát một chuyến cùng container để thử chuyển sang chờ kiểm
                k = (shadow.today - date.fromisoformat(rng.choice(others).day)).days + rng.randint(-2, 2)
            return {"op": "move", "b": b, "trip": trip, "k": k}
        if name == "adjust_trip":
            return {"op": "adjust_trip", "b": b, "trip": trip, "delta": rng.choice([0, rng.randint(-20, 30) * 100])}
        if name == "review":
            return {"op": "review", "b": b, "trip": trip, "decision": rng.choice(["confirm", "confirm", "reject"])}
        return {"op": "delete_trip", "b": b, "trip": trip}
    if name == "adjust_month":
        return {"op": "adjust_month", "b": b, "month": rng.randrange(WINDOW + 1),
                "amount": rng.choice([1, -1]) * rng.randint(1, 30) * 100}
    if name == "delete_adjustment" and book.adjs:
        return {"op": "delete_adjustment", "b": b, "adj": rng.randrange(len(book.adjs))}
    if name in ("edit_receipt", "void") and book.receipts:
        ref = rng.randrange(len(book.receipts))
        if name == "void":
            reason = rng.choice([" bat bien ", "", "  "]) if rng.random() < 0.15 else "khách chuyển nhầm"
            return {"op": "void", "b": b, "receipt": ref, "reason": reason}
        k = None if rng.random() < 0.3 else day_k(rng)
        return {"op": "edit_receipt", "b": b, "receipt": ref, "k": k,
                "method": rng.choice(METHODS) if k is None or rng.random() < 0.3 else None}
    if name == "lock":
        return {"op": "lock", "b": b, "month": rng.randrange(WINDOW + 1), "locked": rng.random() < 0.55}
    if name == "offset" and len(shadow.books) > 1:
        creditors = [i for i, x in enumerate(shadow.books) if shadow.expected_total(x) < 0]
        src = rng.choice(creditors) if creditors and rng.random() < 0.8 else b
        tgt = rng.choice([i for i in range(len(shadow.books)) if i != src])
        share = rng.choice([30, 50, 100, 100]) if rng.random() < 0.85 else 0
        return {"op": "offset", "b": src, "t": tgt, "k": day_k(rng), "share": share, "amount": rng.randint(1, 40) * 250}
    if name in ("void_offset", "edit_offset") and shadow.offsets:
        pair = rng.randrange(len(shadow.offsets))
        if name == "void_offset":
            return {"op": "void_offset", "b": 0, "pair": pair, "side": rng.randrange(2),
                    "reason": "" if rng.random() < 0.15 else "cấn nhầm"}
        return {"op": "edit_offset", "b": 0, "pair": pair, "side": rng.randrange(2), "k": day_k(rng)}
    if name == "replay":
        return {"op": "replay"}
    return {"op": "receipt", "b": b, "k": day_k(rng), "amount": rng.randint(1, 60) * 250, "method": rng.choice(METHODS)}


# ---------------------------------------------------------------- chạy
class Runner:
    def __init__(self, pg: Pg):
        self.pg = pg
        self.round_trips = 0

    def query(self, sql: str) -> str:
        """Một lượt psql qua `Pg` của harness; bỏ statement_timeout 15 giây của harness cho cả chuỗi (giới hạn
        30 giây của một lượt vẫn còn: một chuỗi 25 lệnh mất dưới 2 giây)."""
        self.round_trips += 1
        return self.pg.value(f"BEGIN; SET LOCAL statement_timeout = 0; {sql}; COMMIT")

    def sequence(self, label: str, setup: list[dict], ops: list[dict] | None, rng: random.Random | None,
                 steps: int, retry: bool = True) -> tuple[Shadow, list[dict], Violation | None]:
        """Chạy một chuỗi. ops=None: sinh mới bằng rng; có ops: chạy lại đúng các lệnh đó (khi rút gọn)."""
        saved = rng.getstate() if rng is not None else None
        made = json.loads(self.query(f"SELECT bat_bien.new_books({lit(label)},{lit(json.dumps(setup))}::jsonb,{WINDOW})"))
        shadow = Shadow(label, setup, made["ids"], date.fromisoformat(made["today"]))
        done: list[dict] = []
        while (len(done) < steps) if ops is None else (len(done) < len(ops)):
            op = gen_op(rng, shadow) if ops is None else ops[len(done)]
            done.append(op)
            shadow.step(op)
        batch = [{"actor": p["actor"], "sql": p["sql"]} for p in shadow.plans]
        out = json.loads(self.query(f"SELECT bat_bien.run(ARRAY[{','.join(map(str, made['ids']))}]::bigint[],"
                                    f"{lit(json.dumps(batch, ensure_ascii=False))}::jsonb)"))
        states = [out[0]] + [x[1] for x in out[1:]]
        if any(s["today"] != made["today"] for s in states):
            require(retry, "ngày VN đổi giữa chuỗi hai lần liên tiếp")
            if rng is not None:
                rng.setstate(saved)
            return self.sequence(label + "b", setup, ops, rng, steps, retry=False)  # qua nửa đêm VN: chạy lại
        try:
            Verifier(shadow, states, [x[0] for x in out[1:]]).run()
        except Violation as exc:
            return shadow, done, exc
        return shadow, done, None


def shrink(runner: Runner, setup: list[dict], ops: list[dict], code: str, label: str, budget: float) -> list[dict]:
    """Rút gọn kiểu ddmin: bỏ từng khúc lệnh, giữ khi vẫn đỏ đúng bất biến đó."""
    deadline = time.monotonic() + budget
    chunks, tries = 2, 0
    while len(ops) >= 2 and time.monotonic() < deadline:
        size = max(1, len(ops) // chunks)
        removed = False
        for start in range(0, len(ops), size):
            cand = ops[:start] + ops[start + size:]
            tries += 1
            _, _, v = runner.sequence(f"{label}r{tries}", setup, cand, None, 0)
            if v is not None and v.code == code:
                ops, chunks, removed = cand, max(chunks - 1, 2), True
                break
            if time.monotonic() >= deadline:
                break
        if not removed:
            if size == 1:
                break
            chunks = min(len(ops), chunks * 2)
    return ops


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def apply_mutant(pg: Pg, name: str) -> None:
    kind, target, old, new = MUTANTS[name]
    if kind == "function":
        source = pg.value(f"SELECT pg_get_functiondef('sokhach.{target}'::regproc)")
        require(source.count(old) == 1, f"mutant {name}: không thấy đúng một chỗ {old!r} trong sokhach.{target}")
        pg.sql(source.replace(old, new))
    else:
        source = pg.value(f"SELECT pg_get_viewdef('sokhach.{target}'::regclass)") + "\n"
        require(source.count(old) == 1, f"mutant {name}: không thấy đúng một chỗ {old!r} trong view sokhach.{target}")
        pg.sql(f"CREATE OR REPLACE VIEW sokhach.{target} AS {source.replace(old, new)}")


def report_violation(args, i: int, setup, ops, violation: Violation, runner: Runner, report: dict) -> None:
    print(f"\nĐỎ ở chuỗi {i}: {violation}", flush=True)
    small = shrink(runner, setup, ops, violation.code, f"s{i}m", args.shrink_seconds)
    shadow, _, again = runner.sequence(f"s{i}min", setup, small, None, 0)
    final = again or violation
    lines = [f"{n + 1}. {p['text']}" + ("" if p["expect"] is None else f" → luật chờ bị từ chối {p['expect']}")
             for n, p in enumerate(shadow.plans)]
    rerun = f"--seed {args.seed} --sequence {i} --steps {args.steps}" + (f" --books {args.books}" if args.books != 3 else "")
    report["violation"] = {"code": final.code, "rule": BAT_BIEN[final.code], "sequence": i, "detail": final.detail,
                           "setup": setup, "minimal_steps": lines, "minimal_ops": small, "rerun": rerun}
    print(f"Bất biến bị vi phạm: {final.code} — {BAT_BIEN[final.code]}")
    print(f"Sổ mở đầu (tháng lùi từ hôm nay, tiền opening): {[s['openings'] for s in setup]}")
    print(f"Chuỗi lệnh tối giản còn đỏ ({len(lines)} lệnh, từ {len(ops)}):")
    print("\n".join("  " + line for line in lines))
    print(f"Chi tiết: {final.detail}")
    print(f"Chạy lại: python cong-no-web-handoff/tools/test_pg_v7_bat_bien.py {rerun}"
          + (f" --mutant {args.mutant}" if args.mutant else ""))


def main() -> int:
    for stream in (sys.stdout, sys.stderr):  # Windows chuyển hướng ra file thì mặc định cp1252, không in được tiếng Việt
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure:
            reconfigure(encoding="utf-8", errors="backslashreplace")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--seed", type=int, default=DEFAULT_SEED, help=f"seed (mặc định {DEFAULT_SEED})")
    ap.add_argument("--sequences", type=int, default=120, help="số chuỗi (mặc định 120, bản CI)")
    ap.add_argument("--steps", type=int, default=25, help="số lệnh mỗi chuỗi (mặc định 25)")
    ap.add_argument("--books", type=int, default=3, help="số sổ giả mỗi chuỗi (mặc định 3)")
    ap.add_argument("--sequence", type=int, help="chỉ chạy chuỗi số này (chạy lại chuỗi đỏ)")
    ap.add_argument("--mutant", choices=sorted(MUTANTS),
                    help="cố ý làm sai một hàm/view SQL trong container; lệnh đạt (mã 0) khi test bắt được lỗi")
    ap.add_argument("--shrink-seconds", type=float, default=120, help="thời gian tối đa để rút gọn chuỗi đỏ")
    ap.add_argument("--report", type=Path, help="ghi báo cáo JSON")
    args = ap.parse_args()
    which = [args.sequence] if args.sequence is not None else list(range(args.sequences))
    print(f"seed={args.seed} sequences={len(which)} steps={args.steps} books={args.books}"
          + (f" mutant={args.mutant}" if args.mutant else ""), flush=True)
    stats: dict = {"sequences": 0, "commands": 0, "accepted": 0, "rejected": {}}
    report = {"spec": "specs/v7-bat-bien-tien.md", "image": IMAGE, "schema_sha256": sha(SCHEMA),
              "functions_sha256": sha(FUNCTIONS), "seed": args.seed, "steps": args.steps, "books": args.books,
              "invariants": BAT_BIEN, "mutant": args.mutant, "stats": stats, "result": "fail", "cleanup": "not_started"}
    started = time.monotonic()
    try:
        with disposable_database(report) as pg:
            report["db_ready_seconds"] = round(time.monotonic() - started, 1)
            pg.sql(HELPERS)
            if args.mutant:
                apply_mutant(pg, args.mutant)
            runner = Runner(pg)
            for i in which:
                rng = random.Random(f"{args.seed}:{i}")
                setup = gen_setup(rng, args.books)
                shadow, ops, violation = runner.sequence(f"s{i}", setup, None, rng, args.steps)
                stats["sequences"] += 1
                stats["commands"] += len(shadow.plans)
                for p in shadow.plans:
                    if p["expect"] is None:
                        stats["accepted"] += 1
                    else:
                        stats["rejected"][p["expect"]] = stats["rejected"].get(p["expect"], 0) + 1
                if violation is not None:
                    report_violation(args, i, setup, ops, violation, runner, report)
                    break
                if (i + 1) % 100 == 0:
                    print(f"  {i + 1} chuỗi, {stats['commands']} lệnh, {round(time.monotonic() - started)} s", flush=True)
            report["round_trips"] = runner.round_trips
        if "violation" not in report:
            report["result"] = "pass"
    except (HarnessError, KeyError, TypeError, OSError, ValueError, StopIteration) as exc:
        report["error"] = f"{type(exc).__name__}: {str(exc)[-4000:]}"
        print(f"LỖI HẠ TẦNG: {report['error']}")
    report["seconds"] = round(time.monotonic() - started, 1)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: report.get(k) for k in ("result", "seconds", "db_ready_seconds", "stats", "cleanup")},
                     ensure_ascii=False, indent=2))
    # Với --mutant, đạt nghĩa là test đã đỏ vì vi phạm bất biến (không phải lỗi hạ tầng).
    passed = ("violation" in report and "error" not in report) if args.mutant else report["result"] == "pass"
    return int(not passed or report["cleanup"] != "verified_and_removed")


if __name__ == "__main__":
    sys.exit(main())
