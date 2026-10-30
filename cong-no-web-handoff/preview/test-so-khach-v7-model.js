const test = require("node:test");
const assert = require("node:assert/strict");
const model = require("./so-khach-v7-model.js");
const fixture = require("./so-khach-v7-fixture.js");

const copy = () => structuredClone(fixture);
const month = (book, key) => book.months.find(item => item.key === key);

test("NEWTRIP-01 keys normalize Unicode whitespace, booking symbols and ALT dates", () => {
  const row = { container: " a\u0085b\u00a0c ", date: "10/01/2026", booking: " b\u202fk 1" };
  assert.equal(model.tripKey(row), "BK1|ABC");
  assert.equal(model.tripKey({ ...row, booking: "/" }), "ALT:ABC:20260110|ABC");
  assert.equal(model.tripKey({ ...row, booking: null, date: null }), "ALT:ABC:UNKNOWN|ABC");
  assert.equal(model.tripKey({ ...row, container: " " }), null);
  assert.equal(model.sameTrip(row, { ...row, date: "20/01/2026" }), true);
  for (const [date, expected] of [["07/01/2026", true], ["13/01/2026", true], ["06/01/2026", false], ["14/01/2026", false]]) {
    assert.equal(model.sameTrip(row, { ...row, booking: "other", date }), expected);
  }
  assert.equal(model.sameTrip(row, { ...row, container: "different" }), false);
  assert.equal(model.sameTrip({ ...row, booking: null, date: null }, { ...row, booking: "/" }), false);
});

test("NEWTRIP-01 mixed paste keeps pending rows outside money and allocation", () => {
  const row = (container, date = "10/01/2026") => `${container}\tSHIP\t${date}\tA\tB\t100\t`;
  const parsed = model.parsePastedTrips([row("WEB"), row("BASE"), row("NEW"), row(" n e w", "13/01/2026"), row("SAFE")].join("\n"));
  const trips = model.classifyPastedTrips(parsed.trips, [{ container: "WEB", date: "07/01/2026" }], [{ container: "BASE", date: "10/01/2026" }]);
  assert.deepEqual(trips.map(t => t.reviewReason), ["WEB_DUPLICATE", "BASELINE_DUPLICATE", null, "BATCH_DUPLICATE", null]);
  assert.equal(trips[0].otherFeeVnd, null);
  const book = { months: [{ key: "2026-01", trips, receipts: [] }] };
  assert.equal(model.monthChain(book).totalOutstandingVnd, 200n);
  assert.equal(model.outstandingByMonth(book)[0].outstandingVnd, 200n);
  assert.equal(model.planReceipt(book, { pid: "PH-FAKE", date: "10/01/2026", method: "THU TIỀN", amountVnd: "250" }).overpaymentVnd, 50n);
  assert.equal(model.tripAmount(trips[0]).amountVnd, null);
  assert.throws(() => model.amountWith(trips[0], { unitPriceVnd: "200" }));
  assert.equal(model.classifyPastedTrips([parsed.trips[0]], [trips[0]])[0].status, "pending_review");
  assert.equal(model.classifyPastedTrips([parsed.trips[2]])[0].status, "confirmed");
});

function applyReallocation(book) {
  const plan = model.planReallocation(book);
  for (const item of book.months) item.receipts = item.receipts.filter(receipt => receipt.voided !== null);
  for (const line of plan.lines) month(book, line.monthKey).receipts.push(line.receipt);
  return plan;
}

test("reference edit keeps money, survives reallocation, clears to null", () => {
  const book = copy();
  const pid = book.months.flatMap(item => item.receipts).find(item => item.voided === null).pid;
  const total = model.monthChain(book).totalOutstandingVnd;
  const edited = model.planReceiptEdit(book, pid, { reference: " FAKE USD/rate text " });
  assert.equal(edited.reallocation, null);
  for (const line of edited.lines) month(book, line.monthKey).receipts[line.index] = line.receipt;
  assert.ok(edited.lines.every(line => line.receipt.reference === "FAKE USD/rate text"));
  const plan = applyReallocation(book);
  assert.ok(plan.lines.filter(line => line.receipt.pid === pid).every(line => line.receipt.reference === "FAKE USD/rate text"));
  assert.equal(model.monthChain(book).totalOutstandingVnd, total);
  assert.ok(model.planReceiptEdit(book, pid, { reference: " " }).lines.every(line => line.receipt.reference === null));
  assert.throws(() => model.planReceiptEdit(book, pid, { reference: 10 }));
  assert.throws(() => model.planReceiptEdit(book, pid, { reference: "x".repeat(501) }));
});

test("monthly adjustment reallocates one receipt to oldest debt", () => {
  const small = delta => ({ months: [
    { key: "2026-01", trips: [{ container: "A", unitPriceVnd: "100000000", otherFeeVnd: null }],
      adjustments: [{ amountVnd: delta, reason: "Sửa giá", counted: true }],
      receipts: [{ pid: "PH-1", date: "10/02/2026", method: "THU TIỀN", amountVnd: "100000000", voided: null }] },
    { key: "2026-02", trips: [{ container: "B", unitPriceVnd: "100000000", otherFeeVnd: null }],
      receipts: [{ pid: "PH-1", date: "10/02/2026", method: "THU TIỀN", amountVnd: "20000000", voided: null }] },
  ] });
  for (const [delta, amounts, debts, total, changed] of [
    ["30000000", ["120000000", null], [10000000n, 100000000n], 110000000n, ["PH-1"]],
    ["-30000000", ["70000000", "50000000"], [0n, 50000000n], 50000000n, []],
  ]) {
    const book = small(delta);
    const plan = applyReallocation(book);
    assert.deepEqual(book.months.map(item => item.receipts[0]?.amountVnd ?? null), amounts);
    assert.deepEqual(model.outstandingByMonth(book).map(item => item.outstandingVnd), debts);
    assert.deepEqual(plan.changedPids, changed);
    assert.equal(model.monthChain(book).totalOutstandingVnd, total);
  }
});

test("fixture chronology conflicts with saved allocations", () => {
  const plan = model.planReallocation(copy());
  assert.deepEqual(plan.changedPids, ["PH-009", "PH-008", "PH-012", "PH-011", "PH-015", "PH-014"]);
});

test("March adjustment preserves receipts and debt total, including voided lines", () => {
  const book = copy();
  const before = book.months.flatMap(item => item.receipts.filter(receipt => receipt.voided === null))
    .reduce((sum, receipt) => sum + BigInt(receipt.amountVnd), 0n);
  const cancelled = { pid: "PH-VOID", date: "01/01/2026", method: "ĐÃ HỦY", amountVnd: "42",
    voided: "Sai", voidedOn: "19/10/2026" };
  month(book, "2026-03").receipts.push(cancelled);
  month(book, "2026-03").adjustments = [{ amountVnd: "1000000", reason: "Sửa giá", counted: true }];
  const plan = applyReallocation(book);
  assert.equal(model.monthChain(book).totalOutstandingVnd, 2412645000n);
  assert.equal(book.months.flatMap(item => item.receipts.filter(receipt => receipt.voided === null))
    .reduce((sum, receipt) => sum + BigInt(receipt.amountVnd), 0n), before);
  assert.ok(model.outstandingByMonth(book).every(item => item.outstandingVnd >= 0n));
  assert.equal(plan.changedPids.length, 7);
  assert.strictEqual(month(book, "2026-03").receipts[0], cancelled);
});

test("two counted adjustments on one trip reallocate to final price", () => {
  const book = copy();
  const march = month(book, "2026-03");
  const old = model.tripAmount(march.trips[0]).amountVnd;
  const request = { monthKey: "2026-03", lineId: "2026-03#0" };
  march.adjustments = [model.planAdjustment(book, { "2026-03": true, "2026-10": false },
    { ...request, newAmountVnd: (old - 2000000n).toString(), reason: "Lần một" })];
  applyReallocation(book);
  march.adjustments.push(model.planAdjustment(book, { "2026-03": true, "2026-10": false },
    { ...request, newAmountVnd: (old + 1000000n).toString(), reason: "Lần hai" }));
  applyReallocation(book);
  assert.deepEqual(march.adjustments.map(item => item.amountVnd), ["-2000000", "3000000"]);
  assert.equal(model.monthChain(book).months.find(item => item.key === "2026-03").totalChargesVnd, 1780900000n);
  assert.equal(model.monthChain(book).totalOutstandingVnd, 2412645000n);
});

test("month locks alone control direct edits", () => {
  const locks = { "2026-09": true, "2026-10": false };
  assert.equal(model.isMonthOpen(locks, "2026-09"), false);
  locks["2026-09"] = false;
  assert.equal(model.isMonthOpen(locks, "2026-09"), true);
  assert.equal(model.isMonthOpen(locks, "2026-10"), true);
  assert.throws(() => model.isMonthOpen(locks, "2026-03"), /Missing month lock/);
  const book = copy();
  const old = model.tripAmount(month(book, "2026-09").trips[0]).amountVnd;
  const request = { monthKey: "2026-09", lineId: "2026-09#0", newAmountVnd: (old + 1000000n).toString() };
  assert.throws(() => model.planAdjustment(book, locks, request), /Open month/);
  locks["2026-09"] = true;
  assert.equal(model.planAdjustment(book, locks, request).amountVnd, "1000000");
});

test("signed whole-month adjustments change only March charges and total debt", () => {
  const book = copy();
  const before = model.monthChain(book);
  const receivedBefore = book.months.flatMap(item => item.receipts).filter(item => item.voided === null)
    .reduce((sum, item) => sum + BigInt(item.amountVnd), 0n);
  const march = month(book, "2026-03");
  for (const [input, delta] of [["+5.000.000", 5000000n], ["-3,000,000", -3000000n]]) {
    const planned = model.planMonthAdjustment(book, { monthKey: "2026-03", amount: input, reason: "  thử  " });
    march.adjustments ??= [];
    march.adjustments.push(planned);
    assert.equal(planned.reason, "thử");
    assert.equal(model.adjustmentAmount(planned), delta);
    applyReallocation(book);
  }
  const after = model.monthChain(book);
  assert.equal(after.months.find(item => item.key === "2026-03").totalChargesVnd,
    before.months.find(item => item.key === "2026-03").totalChargesVnd + 2000000n);
  assert.equal(after.totalOutstandingVnd, before.totalOutstandingVnd + 2000000n);
  assert.deepEqual(after.months.filter(item => item.key !== "2026-03").map(item => item.totalChargesVnd),
    before.months.filter(item => item.key !== "2026-03").map(item => item.totalChargesVnd));
  assert.equal(book.months.flatMap(item => item.receipts).filter(item => item.voided === null)
    .reduce((sum, item) => sum + BigInt(item.amountVnd), 0n), receivedBefore);
  for (const invalid of ["0", "-0", "+0", "abc", "1.2", "1,00,000", "5.000,000"])
    assert.throws(() => model.planMonthAdjustment(book, { monthKey: "2026-03", amount: invalid }), /Invalid VND|nonzero/);
  const negative = { months: [{ key: "2026-03", trips: [], receipts: [], adjustments: [] }] };
  negative.months[0].adjustments.push(model.planMonthAdjustment(negative, { monthKey: "2026-03", amount: "-3.000.000" }));
  assert.equal(model.monthChain(negative).months[0].endOfMonthVnd, -3000000n);
});
test("11 fixture months match charges, receipts, and running balance", () => {
  const expected = [
    ["2025-12", 441500000n, 441500000n, 0n],
    ["2026-01", 913900000n, 913900000n, 0n],
    ["2026-02", 826600000n, 826600000n, 0n],
    ["2026-03", 1779900000n, 1779900000n, 0n],
    ["2026-04", 2275800000n, 2275800000n, 0n],
    ["2026-05", 1625800000n, 1625800000n, 0n],
    ["2026-06", 1381510000n, 1381510000n, 0n],
    ["2026-07", 946500000n, 946500000n, 0n],
    ["2026-08", 1521500000n, 562955000n, 958545000n],
    ["2026-09", 1332100000n, 0n, 2290645000n],
    ["2026-10", 121000000n, 0n, 2411645000n],
  ];
  const result = model.monthChain(fixture);
  assert.deepEqual(result.months.map(row => [row.key, row.chargesVnd, row.receivedVnd, row.endOfMonthVnd]), expected);
  assert.equal(result.totalOutstandingVnd, 2411645000n);
});

test("June fee-only line counts as money, not a trip or missing price", () => {
  const june = month(fixture, "2026-06");
  const fee = june.trips.find(trip => trip.container === null && trip.otherFeeVnd === "1310000");
  assert.deepEqual(model.tripAmount(fee), { amountVnd: 1310000n, isFeeOnly: true, isMissingPrice: false });
  const row = model.monthChain(fixture).months.find(item => item.key === "2026-06");
  assert.equal(row.chargesVnd, 1381510000n);
  assert.equal(row.tripCount, 26);
  assert.equal(row.lineCount, 27);
  assert.deepEqual(row.missingPriceIds, []);
});

test("missing price with container excludes even a known fee", () => {
  assert.deepEqual(model.tripAmount({ container: "X", unitPriceVnd: null, otherFeeVnd: "100" }),
    { amountVnd: null, isFeeOnly: false, isMissingPrice: true });
  assert.deepEqual(model.tripAmount({ container: "X", unitPriceVnd: null, otherFeeVnd: null }),
    { amountVnd: null, isFeeOnly: false, isMissingPrice: true });
});

test("void full PH-101 in its original months; other receipts stay put", () => {
  const book = copy();
  const before = book.months.map(item => item.receipts.filter(receipt => receipt.pid !== "PH-101"));
  const plan = model.planVoid(book, "PH-101", "  nhập sai  ", "19/10/2026");
  assert.deepEqual(model.receiptDetails(book, "PH-101"),
    { totalVnd: 600694000n, monthKeys: ["2026-06", "2026-07"] });
  assert.equal(plan.totalVnd, 600694000n);
  assert.deepEqual(plan.monthKeys, ["2026-06", "2026-07"]);
  assert.deepEqual(plan.lines.map(line => [line.monthKey, line.receipt.amountVnd]),
    [["2026-06", "524974000"], ["2026-07", "75720000"]]);
  assert.deepEqual(plan.lines.map(line => [line.receipt.voided, line.receipt.voidedOn]),
    [["nhập sai", "19/10/2026"], ["nhập sai", "19/10/2026"]]);
  for (const line of plan.lines) month(book, line.monthKey).receipts[line.index] = line.receipt;
  assert.deepEqual(book.months.map(item => item.receipts.filter(receipt => receipt.pid !== "PH-101")), before);
  assert.equal(model.monthChain(book).totalOutstandingVnd, 2411645000n + 600694000n);
  assert.deepEqual(model.outstandingByMonth(book).filter(row => ["2026-06", "2026-07"].includes(row.monthKey)),
    [{ monthKey: "2026-06", outstandingVnd: 524974000n },
      { monthKey: "2026-07", outstandingVnd: 75720000n }]);
  assert.deepEqual(model.voidedLines(book, "2026-06").map(line => [line.amountVnd, line.voidedOn, line.reason]),
    [[524974000n, "19/10/2026", "nhập sai"]]);
  const replacement = model.planReceipt(book,
    { pid: "PH-NEW", date: "19/10/2026", method: "THU TIỀN", amountVnd: "600694000" });
  assert.deepEqual(replacement.lines, [
    { monthKey: "2026-06", amountVnd: "524974000", kind: "debt" },
    { monthKey: "2026-07", amountVnd: "75720000", kind: "debt" },
  ]);
  for (const line of replacement.lines) month(book, line.monthKey).receipts.push({
    pid: "PH-NEW", date: "19/10/2026", method: "THU TIỀN", amountVnd: line.amountVnd, voided: null,
  });
  assert.equal(model.monthChain(book).totalOutstandingVnd, 2411645000n);
});

test("void requires reason and active pid", () => {
  assert.throws(() => model.planVoid(fixture, "PH-101", "  ", "19/10/2026"));
  assert.throws(() => model.planVoid(fixture, "missing", "reason", "19/10/2026"));
  assert.throws(() => model.planVoid(fixture, "PH-101", "reason", "31/02/2026"));
  const book = copy();
  month(book, "2026-06").receipts.find(item => item.pid === "PH-101").voided = "reason";
  assert.throws(() => model.planVoid(book, "PH-101", "reason", "19/10/2026"));
});

test("new receipt clears August then part of September", () => {
  const book = copy();
  const plan = model.planReceipt(book,
    { pid: "PH-NEW", date: "19/10/2026", method: "THU TIỀN", amountVnd: "1000000000" });
  assert.deepEqual(plan.lines, [
    { monthKey: "2026-08", amountVnd: "958545000", kind: "debt" },
    { monthKey: "2026-09", amountVnd: "41455000", kind: "debt" },
  ]);
  assert.equal(model.nextReceiptPid(book), "PH-102");
  month(book, "2026-10").receipts.push({ pid: "PH-120", date: "19/10/2026", method: "KHÁC", amountVnd: "1", voided: "sai" });
  assert.equal(model.nextReceiptPid(book), "PH-121");
  month(book, "2026-10").receipts.pop();
  assert.equal(model.receiptNotice("PH-102", plan), "PH-102 đã trừ: tháng 8/2026 958.545.000 · tháng 9/2026 41.455.000");
  assert.equal(plan.overpaymentVnd, 0n);
  for (const line of plan.lines) month(book, line.monthKey).receipts.push({
    pid: "PH-NEW", date: "19/10/2026", method: "THU TIỀN", amountVnd: line.amountVnd, voided: null,
  });
  assert.equal(model.monthChain(book).totalOutstandingVnd, 1411645000n);
});

test("receipt over total debt becomes advance in final month", () => {
  const book = copy();
  const plan = model.planReceipt(book,
    { pid: "PH-BIG", date: "19/10/2026", method: "THU TIỀN", amountVnd: "3000000000" });
  assert.equal(plan.overpaymentVnd, 588355000n);
  assert.deepEqual(plan.lines.slice(-2), [
    { monthKey: "2026-10", amountVnd: "121000000", kind: "debt" },
    { monthKey: "2026-10", amountVnd: "588355000", kind: "advance" },
  ]);
  assert.match(model.receiptNotice("PH-102", plan), /tháng 10\/2026 121.000.000 · ỨNG TRƯỚC 588.355.000$/);
  for (const line of plan.lines) month(book, line.monthKey).receipts.push({
    pid: "PH-BIG", date: "19/10/2026", method: "THU TIỀN", amountVnd: line.amountVnd, voided: null,
  });
  assert.equal(model.monthChain(book).totalOutstandingVnd, -588355000n);
});

test("missing October price preserves fee but excludes entire trip", () => {
  const book = copy();
  const trip = month(book, "2026-10").trips[0];
  const removed = model.tripAmount(trip).amountVnd;
  trip.unitPriceVnd = null;
  assert.equal(model.tripAmount(trip).amountVnd, null);
  assert.deepEqual(model.monthChain(book).months.at(-1).missingPriceIds, ["2026-10#0"]);
  assert.equal(model.pendingCounts(book).missingPrice, 1);
  assert.equal(model.monthChain(book).totalOutstandingVnd, 2411645000n - removed);
});

test("locked March edit counts immediately without reason", () => {
  const book = copy();
  const trip = month(book, "2026-03").trips[0];
  const original = structuredClone(trip);
  const oldAmount = model.tripAmount(trip).amountVnd;
  const request = { monthKey: "2026-03", lineId: "2026-03#0", newAmountVnd: (oldAmount + 1000000n).toString() };
  assert.equal(model.isMonthOpen({ "2026-03": true }, "2026-03"), false);
  assert.equal(model.isMonthOpen({ "2026-10": false }, "2026-10"), true);
  const adjustment = model.planAdjustment(book, { "2026-03": true, "2026-10": false }, request);
  assert.equal(adjustment.counted, true);
  assert.equal(adjustment.reason, "");
  month(book, "2026-03").adjustments = [adjustment];
  assert.deepEqual(trip, original);
  assert.equal(model.monthChain(book).totalOutstandingVnd, 2412645000n);
  assert.equal(model.pendingCounts(book).adjustmentsAwaitingReason, undefined);
  assert.deepEqual(trip, original);
  assert.throws(() => model.planAdjustment(book, { "2026-03": true, "2026-10": false }, { ...request, monthKey: "2026-10" }));
});

test("two locked-month edits count immediately, keep two lines, and use current price", () => {
  const book = copy();
  const march = month(book, "2026-03");
  const original = structuredClone(march.trips[0]);
  const request = { monthKey: "2026-03", lineId: "2026-03#0" };
  const proposed = unitPriceVnd => model.amountWith(original, { unitPriceVnd }).toString();
  assert.equal(original.unitPriceVnd, "52000000");
  assert.equal(model.tripAmount(original).amountVnd, 53600000n);
  const first = model.planAdjustment(book, { "2026-03": true, "2026-10": false }, { ...request, newAmountVnd: proposed("50000000") });
  march.adjustments = [first];
  assert.equal(first.amountVnd, "-2000000");
  assert.equal(model.monthChain(book).totalOutstandingVnd, 2409645000n);
  const second = model.planAdjustment(book, { "2026-03": true, "2026-10": false }, { ...request, newAmountVnd: proposed("53000000") });
  assert.equal(second.oldAmountVnd, 51600000n);
  assert.equal(second.amountVnd, "3000000");
  assert.notEqual(second.adjId, first.adjId);
  march.adjustments.push(second);
  assert.equal(model.monthChain(book).totalOutstandingVnd, 2412645000n);
  assert.deepEqual(march.adjustments.map(item => [item.reason, item.amountVnd]),
    [["", "-2000000"], ["", "3000000"]]);
  const chain = model.monthChain(book);
  assert.equal(chain.months.find(item => item.key === "2026-03").totalChargesVnd, 1780900000n);
  assert.equal(chain.totalOutstandingVnd, 2411645000n + 1000000n);
  assert.equal(model.planAdjustment(book, { "2026-03": true, "2026-10": false }, { ...request, newAmountVnd: proposed("53000000") }), null);
  assert.deepEqual(march.trips[0], original);
});

test("receipt date edit reallocates all pid lines by date and reports month changes", () => {
  const book = { months: [
    { key: "2026-01", trips: [{ container: "A", unitPriceVnd: "100", otherFeeVnd: null }], receipts: [
      { pid: "PH-1", date: "01/02/2026", method: "THU TIỀN", amountVnd: "100", kind: "debt", voided: null }] },
    { key: "2026-02", trips: [{ container: "B", unitPriceVnd: "100", otherFeeVnd: null }], receipts: [
      { pid: "PH-2", date: "02/02/2026", method: "CẤN TRỪ", amountVnd: "100", kind: "debt", voided: null }] },
  ] };
  const plan = model.planReceiptEdit(book, "PH-2", { date: "31/01/2026" });
  assert.deepEqual(plan.reallocation.changedPids, ["PH-2", "PH-1"]);
  for (const line of plan.lines) month(book, line.monthKey).receipts[line.index] = line.receipt;
  const reallocated = applyReallocation(book);
  assert.deepEqual(reallocated.lines.map(line => [line.monthKey, line.receipt.pid, line.receipt.date]),
    [["2026-01", "PH-2", "31/01/2026"], ["2026-02", "PH-1", "01/02/2026"]]);
  assert.equal(model.monthChain(book).totalOutstandingVnd, 0n);
  assert.throws(() => model.planReceiptEdit(book, "PH-2", { date: "31/02/2026" }), /Invalid receipt/);
});

test("receipt method edit keeps totals and advance line kind", () => {
  const book = { months: [{ key: "2026-01", trips: [{ container: "A", unitPriceVnd: "100", otherFeeVnd: null }], receipts: [
    { pid: "PH-1", date: "01/02/2026", method: "THU TIỀN", amountVnd: "100", kind: "debt", voided: null },
    { pid: "PH-1", date: "01/02/2026", method: "ỨNG TRƯỚC", receiptMethod: "THU TIỀN", amountVnd: "50", kind: "advance", voided: null },
  ] }] };
  const before = model.monthChain(book).totalOutstandingVnd;
  const plan = model.planReceiptEdit(book, "PH-1", { method: "CẤN TRỪ" });
  assert.equal(plan.reallocation, null);
  for (const line of plan.lines) month(book, line.monthKey).receipts[line.index] = line.receipt;
  assert.deepEqual(book.months[0].receipts.map(item => [item.method, item.kind]),
    [["CẤN TRỪ", "debt"], ["ỨNG TRƯỚC", "advance"]]);
  assert.equal(book.months[0].receipts[1].receiptMethod, "CẤN TRỪ");
  assert.equal(model.monthChain(book).totalOutstandingVnd, before);
  assert.throws(() => model.planReceiptEdit(book, "PH-1", { method: "CHUYỂN KHOẢN" }), /Invalid receipt/);
  const voided = model.planVoid(book, "PH-1", "sai", "19/10/2026");
  for (const line of voided.lines) month(book, line.monthKey).receipts[line.index] = line.receipt;
  assert.throws(() => model.planReceiptEdit(book, "PH-1", { date: "03/02/2026" }), /already voided/);
});

test("negative adjustment month still permits receipt reallocation", () => {
  const book = { months: [
    { key: "2026-01", trips: [{ container: "A", unitPriceVnd: "100", otherFeeVnd: null }],
      adjustments: [{ lineId: "2026-01#0", amountVnd: "-150", reason: "", counted: true }], receipts: [] },
    { key: "2026-02", trips: [{ container: "B", unitPriceVnd: "100", otherFeeVnd: null }],
      receipts: [{ pid: "PH-1", date: "01/03/2026", method: "THU TIỀN", amountVnd: "50", voided: null }] },
  ] };
  const plan = applyReallocation(book);
  assert.deepEqual(plan.lines.map(line => line.monthKey), ["2026-02"]);
  assert.deepEqual(model.outstandingByMonth(book).map(row => row.outstandingVnd), [-50n, 50n]);
  assert.equal(model.monthChain(book).totalOutstandingVnd, 0n);
});

test("parse and format VND without Number", () => {
  for (const input of ["46,000,000", "46.000.000", " 46000000 "]) {
    assert.equal(model.parseVnd(input), 46000000n);
  }
  for (const invalid of ["", " ", "46,00,000", "46.000,000", "-100", "abc", "1.2", "1 000"]) {
    assert.throws(() => model.parseVnd(invalid));
  }
  assert.equal(model.formatVnd(2411645000n), "2.411.645.000");
  assert.equal(model.formatVnd(-1000000n), "-1.000.000");
  assert.throws(() => model.formatVnd(1000));
  assert.equal(model.pendingCounts(fixture).uncertainReceipts, 0);
});

test("amountWith calculates proposed amount without changing original trip", () => {
  const trip = month(fixture, "2026-03").trips[0];
  const original = structuredClone(trip);
  assert.equal(model.amountWith(trip, { unitPriceVnd: "46000000", otherFeeVnd: null }), 46000000n);
  assert.deepEqual(trip, original);
  assert.throws(() => model.amountWith(trip, { unitPriceVnd: null }));
});

test("paste accepts three VND forms, blanks, and rejects whole invalid batch", () => {
  const row = (price, fee = "") => `BOX\tHTA\t19/10/2026\tKHO\tCANG\t${price}\t${fee}`;
  const result = model.parsePastedTrips(`\n${row("46,000,000")}\n${row("46.000.000", "1,000")}\n${row("46000000")}\n${row("")}\n`);
  assert.deepEqual(result.trips.map(trip => [trip.unitPriceVnd, trip.otherFeeVnd, trip.src]),
    [["46000000", null, ""], ["46000000", "1000", ""], ["46000000", null, ""], [null, null, ""]]);
  assert.deepEqual(model.parsePastedTrips(`${row("46,000,000")}\n${row("46,00,000")}\n${row("46000000")}`),
    { errors: ["Dòng 2: đơn giá không hợp lệ"] });
  assert.deepEqual(model.parsePastedTrips(`${row("46000000")}\n\nBOX\tHTA\t31/02/2026\tKHO\tCANG\t1\t`),
    { errors: ["Dòng 3: ngày chuyến không hợp lệ"] });
});

const offsetSources = () => model.parseOffsetSources([
  { customer_id: 11, name: "Khách A", commodity: "sầu riêng", version: 3, outstanding_vnd: "-100000000", available_credit_vnd: "100000000" },
  { customer_id: "12", name: "Khách C", commodity: null, version: "1", outstanding_vnd: "-8500000", available_credit_vnd: "8500000" },
]);

test("offset sources keep server order, read money as BigInt, and filter without diacritics", () => {
  const sources = offsetSources();
  assert.deepEqual(sources.map(source => [source.customerId, source.label, source.availableCreditVnd, source.version]),
    [["11", "Khách A · sầu riêng", 100000000n, "3"], ["12", "Khách C", 8500000n, "1"]]);
  assert.deepEqual(model.filterOffsetSources(sources, "khach a").map(source => source.customerId), ["11"]);
  assert.equal(model.filterOffsetSources(sources, "").length, 2);
  const bad = patch => [{ customer_id: 1, name: "X", commodity: null, version: 1, outstanding_vnd: "-5", available_credit_vnd: "5", ...patch }];
  for (const patch of [{ outstanding_vnd: "5" }, { available_credit_vnd: "4" }, { outstanding_vnd: -5 }, { name: " " }, { version: 0 }])
    assert.throws(() => model.parseOffsetSources(bad(patch)));
  assert.throws(() => model.parseOffsetSources({}));
});

test("offset entry: missing source, bad amount, over credit, outside, and typed money forms", () => {
  const [a] = offsetSources();
  assert.equal(model.planOffsetEntry({ source: null, amountText: "1" }).message, "Chọn sổ lấy tiền, hoặc chọn Ngoài sổ");
  for (const text of ["", "0", "-5.000.000", "−5.000.000", "5.000.000đ", "1,00"])
    assert.equal(model.planOffsetEntry({ source: a, amountText: text }).code, "INVALID_VND", text);
  const over = model.planOffsetEntry({ source: a, amountText: "120.000.000" });
  assert.equal(over.code, "OFFSET_EXCEEDS_CREDIT");
  assert.equal(over.message, "Sổ Khách A · sầu riêng chỉ còn dư 100.000.000");
  for (const text of ["50.000.000", "50,000,000", "50000000"])
    assert.deepEqual(model.planOffsetEntry({ source: a, amountText: text }), { ok: true, outside: false, amountVnd: 50000000n });
  assert.equal(model.planOffsetEntry({ source: a, amountText: "100.000.000" }).ok, true);
  assert.deepEqual(model.planOffsetEntry({ source: model.OFFSET_OUTSIDE, amountText: "50.000.000" }),
    { ok: true, outside: true, amountVnd: 50000000n });
});

test("offset preview shows both balances and flags a negative receiving book", () => {
  const [a] = offsetSources();
  const same = model.planOffsetPreview({ source: a, targetOutstandingVnd: 50000000n, amountVnd: 50000000n });
  assert.deepEqual([same.source.afterVnd, same.target.afterVnd, same.targetNegativeVnd], [-50000000n, 0n, null]);
  const over = model.planOffsetPreview({ source: a, targetOutstandingVnd: 50000000n, amountVnd: 70000000n });
  assert.deepEqual([over.source.afterVnd, over.target.afterVnd, over.targetNegativeVnd], [-30000000n, -20000000n, -20000000n]);
  assert.throws(() => model.planOffsetPreview({ source: a, targetOutstandingVnd: 1, amountVnd: 1n }));
});

test("offset errors, command result, and ledger links parse the backend contract", () => {
  assert.equal(model.offsetErrorMessage("OFFSET_EXCEEDS_CREDIT", { available_credit_vnd: "30000000" }), "Sổ lấy tiền chỉ còn dư 30.000.000");
  assert.equal(model.offsetErrorMessage("STALE_LEDGER"), "Số dư đã đổi, tải lại số rồi xác nhận lại");
  assert.equal(model.offsetErrorMessage("SOMETHING_ELSE"), "Không ghi được cấn trừ");
  const result = model.parseOffsetResult({ offset_pair_id: 5, source_customer_id: 11, target_customer_id: 12, source_version: 4,
    target_version: 7, source_pid: "PH-013", target_pid: "PH-021", target_receipt: { overpayment_vnd: "20000000" } });
  assert.deepEqual(result, { pairId: "5", sourceCustomerId: "11", targetCustomerId: "12", sourceVersion: "4", targetVersion: "7",
    sourcePid: "PH-013", targetPid: "PH-021", overpaymentVnd: 20000000n });
  assert.equal(model.parseOffsetLink({ offset_pair_id: null, counterparty_customer_id: null, counterparty_name: null }), null);
  assert.deepEqual(model.parseOffsetLink({ offset_pair_id: 5, counterparty_customer_id: 11, counterparty_name: "Khách A" }),
    { pairId: "5", counterpartyCustomerId: "11", counterpartyName: "Khách A" });
  const row = patch => ({ offset_pair_id: 5, pid: "PH-013", date: "2026-10-20", amount_vnd: "-50000000", void_reason: null,
    voided_by_event: null, counterparty_customer_id: 12, counterparty_name: "Khách B", ...patch });
  const [out] = model.parseOutgoingOffsets([row({})]);
  assert.deepEqual([out.pid, out.amountVnd, out.voided, out.counterpartyName], ["PH-013", -50000000n, false, "Khách B"]);
  assert.equal(model.parseOutgoingOffsets([row({ void_reason: "sai" })])[0].voided, true);
  assert.throws(() => model.parseOutgoingOffsets([row({ amount_vnd: "50000000" })]));
});

test("NHAP-SHEET-01 cell edit: Sheet dates, money blank is unknown, container normalized, bad input named", () => {
  const today = "2026-10-22";
  assert.equal(model.parseCellEdit("event_date", " 5/9/2026 ", today), "2026-09-05");
  assert.equal(model.parseCellEdit("event_date", "22/10/2026", today), "2026-10-22");
  assert.throws(() => model.parseCellEdit("event_date", "23/10/2026", today), /sau hôm nay/);
  for (const bad of ["31/02/2026", "2026-09-05", "", "5/9/26"]) assert.throws(() => model.parseCellEdit("event_date", bad, today), /dd\/mm\/yyyy/);
  assert.equal(model.parseCellEdit("unit_price_vnd", "75.000.000"), "75000000");
  assert.equal(model.parseCellEdit("other_fee_vnd", "4,500,000"), "4500000");
  assert.equal(model.parseCellEdit("unit_price_vnd", "  "), "");
  assert.equal(model.parseCellEdit("other_fee_vnd", "0"), "0");
  assert.throws(() => model.parseCellEdit("unit_price_vnd", "chưa có giá"), /Số tiền không hợp lệ/);
  assert.throws(() => model.parseCellEdit("unit_price_vnd", "-5"), /Số tiền không hợp lệ/);
  assert.equal(model.parseCellEdit("container", " abcu 123 4567 "), "ABCU1234567");
  assert.equal(model.parseCellEdit("origin", "  Tiền Giang "), "Tiền Giang");
  assert.equal(model.parseCellEdit("carrier", ""), "");
  assert.equal(model.parseCellEdit("shipper", "  TRUONG THINH PHAT "), "TRUONG THINH PHAT");
  assert.equal(model.parseCellEdit("shipper", ""), "");
  assert.throws(() => model.parseCellEdit("amount_vnd", "1"), /không được sửa/);
});

test("legacy edit adjustments sum signed digit strings exactly; none is null, not 0", () => {
  assert.equal(model.sumAdjustments([]), null);
  assert.equal(model.sumAdjustments([{ amount_vnd: "5000000" }, { amount_vnd: "-65000000" }]), -60000000n);
  assert.equal(model.sumAdjustments([{ amount_vnd: "9007199254740993" }, { amount_vnd: "1" }]), 9007199254740994n);
  assert.throws(() => model.sumAdjustments([{ amount_vnd: "1.5" }]));
});

test('Ghi giá từ Sheet: tổng tăng tính bằng BigInt, phụ phí null là 0, tổng âm vẫn đọc được', () => {
  const ready = [{ sheet_unit_price_vnd: '12500000', sheet_other_fee_vnd: '300000' }, { sheet_unit_price_vnd: '13000000', sheet_other_fee_vnd: null }];
  assert.equal(model.sheetPriceAmount(ready[0]), 12800000n);
  assert.deepEqual(model.planSheetPrices(ready, '-1000000'), { count: 2, increaseVnd: 25800000n, beforeVnd: -1000000n, afterVnd: 24800000n });
  assert.equal(model.sheetVnd('-500000'), -500000n);
  assert.equal(model.sheetVnd(null), null);
  assert.throws(() => model.planSheetPrices([{ sheet_unit_price_vnd: 12500000 }], '0'));   // tiền phải là chuỗi
});

test('PHU-PHI-01: cụm cột phụ phí, tổng tháng, số gõ tay theo dấu loại, Thành tiền trước → sau khi tính lại', () => {
  const lines = [{ id: 1, fee_type_id: 1, amount_vnd: '1200000' }, { id: 2, fee_type_id: 1, amount_vnd: '300000' },
    { id: 3, fee_type_id: 7, amount_vnd: '800000' }, { id: 4, fee_type_id: 8, amount_vnd: '-500000' }];
  assert.deepEqual(model.feeCells(lines, [1, 2]), { own: [1500000n, null], otherVnd: 300000n, otherCount: 2, totalVnd: 1800000n });
  assert.deepEqual(model.feeCells([], [1]), { own: [null], otherVnd: null, otherCount: 0, totalVnd: null });   // trống không phải 0
  assert.deepEqual(model.feeColumnTotals([lines, [], [{ id: 9, fee_type_id: 2, amount_vnd: '50' }]], [1, 2]),
    { own: [1500000n, 50n], otherVnd: 300000n });
  assert.deepEqual(model.feeColumnTotals([[]], [1]), { own: [null], otherVnd: null });
  assert.equal(model.parseFeeInput('1.200.000', 'positive'), 1200000n);
  assert.equal(model.parseFeeInput('-200.000', 'negative'), -200000n);
  assert.equal(model.parseFeeInput('  ', 'positive', { allowBlank: true }), null);
  assert.throws(() => model.parseFeeInput('', 'positive'), /khác 0/);
  assert.throws(() => model.parseFeeInput('0', 'any'), /khác 0/);
  assert.throws(() => model.parseFeeInput('200000', 'negative'), /Giảm trừ nhập số âm/);
  assert.throws(() => model.parseFeeInput('-1', 'positive'), /số dương/);
  assert.throws(() => model.parseFeeInput('1,2', 'positive'), /không đọc được/);
  // Dòng sổ gốc 75.000.000 + khoản 5.000.000, Thành tiền đang là 80.500.000: đặt Neo 1.000.000 → 81.000.000.
  const legacy = [{ id: 7, fee_type_id: 9, amount_vnd: '5000000' }];
  assert.deepEqual(model.recountPreview('80500000', '75000000', legacy, { set: { typeId: 1, amountVnd: 1000000n } }),
    { beforeVnd: 80500000n, afterVnd: 81000000n, deltaVnd: 500000n });
  assert.equal(model.feeTotalAfter('75000000', legacy, { void: { lineId: '7' } }), 75000000n);
  assert.equal(model.feeTotalAfter('75000000', legacy, { replace: { lineId: 7, amountVnd: 2000000n } }), 77000000n);
  assert.equal(model.feeTotalAfter('75000000', legacy, { add: { typeId: 8, amountVnd: -1000000n } }), 79000000n);
  assert.equal(model.feeTotalAfter('75000000', legacy, { set: { typeId: 9, amountVnd: null } }), 75000000n);
});

// DEBIT-NOTE-02 (mẫu v3): số container giả nhưng đúng chữ số kiểm tra ISO 6346; số tiền theo các trường hợp kiểm thử của đặc tả.
const dnFeeTypes = [{ id: 1, name: "Neo" }, { id: 2, name: "Điện" }, { id: 3, name: "Ghép" }, { id: 4, name: "Bảo hiểm" }, { id: 5, name: "Kiểm định" },
  { id: 6, name: "Health cert" }, { id: 7, name: "Khác" }, { id: 8, name: "Giảm trừ" }, { id: 9, name: "Phụ phí ban đầu" }, { id: 10, name: "Lưu kho" }, { id: 11, name: "Phí hủy cont" }];
const dnContainer = serial => { for (let digit = 0; digit < 10; digit++) { const id = `TSTU${String(serial).padStart(6, "0")}${digit}`; if (model.containerCheck(id).valid) return id; } return null; };
let dnSerial = 0;
const dnTrip = (month, day, port, price, lines = [], extra = {}) => ({ id: ++dnSerial, month: `${month}-01`, container: dnContainer(dnSerial), carrier: "IAL", shipper: "SHIPPER",
  event_date: `${month}-${day}`, origin: "DAKLAK", destination: port, unit_price_vnd: String(price), status: "confirmed", is_missing_price: false, is_fee_only: false,
  fee_lines: lines.map(([type, amount, note]) => ({ fee_type_id: type, amount_vnd: String(amount), note: note ?? null })),
  amount_vnd: String(price + lines.reduce((sum, [, amount]) => sum + amount, 0)), ...extra });
const dnDoc = (extra = {}) => ({ number: "HTH-2512-001", issueDate: "2026-10-30", paymentDays: 15, service: "Sea freight 海运", vatNo: "",
  issuer: { name: "ISSUER CO., LTD", taxId: "0000000001" }, buyer: { display: "BUYER", legal: "BUYER LEGAL CO., LTD", address: "Address" },
  payment: { beneficiary: "ISSUER CO., LTD", bank: "Bank", account: "000111", swift: "BANKXXXX", currency: "USD" }, usd: { on: false }, ...extra });

test("DEBIT-NOTE-02 tháng 12/2025: 5 container, tóm tắt theo cảng, TOTAL DUE 409,500,000, chỉ chuyến đã xác nhận của tháng", () => {
  const ledger = {
    trips: [
      dnTrip("2025-12", "01", "XIAMEN", 70000000, [[7, 4500000]]), dnTrip("2025-12", "06", "NANSHA", 80000000, [[7, 4500000]]),
      dnTrip("2025-12", "28", "XIAMEN", 80000000, [[7, 3000000]]), dnTrip("2025-12", "31", "XIAMEN ", 80000000, [[7, 4500000]]),
      dnTrip("2025-12", "05", "QINGDAO", 1, [], { status: "pending_review" }), dnTrip("2025-12", "05", "QINGDAO", 1, [], { status: "rejected" }),
      dnTrip("2025-12", "05", "QINGDAO", 1, [], { deleted: true }), dnTrip("2026-01", "02", "QINGDAO", 1),
    ],
    legacy_rows: [
      { id: 21, month: "2025-12-01", kind: "trip", editable: true, fee_lines: [{ fee_type_id: 9, amount_vnd: "3000000" }], display: { row: 4 },
        current: { container: dnContainer(900), carrier: "YM", shipper: "SHIPPER", event_date: "2025-12-28", origin: "Dak Lak", destination: "Xiamen",
          unit_price_vnd: "80000000", counted_vnd: "83000000", deleted: false } },
      { id: 22, month: "2025-12-01", kind: "receipt", display: { row: 5 } },
    ],
    adjustments: [{ month: "2025-12-01", legacy_row_id: null, amount_vnd: "5" }, { month: "2025-12-01", legacy_row_id: 21, amount_vnd: "30" }],
  };
  const note = model.debitNote(ledger, "2025-12", dnFeeTypes);
  assert.deepEqual(note.rows.map(row => [row.no, model.dnDate(row.date), row.port.text]),
    [[1, "01 Dec 2025", "Xiamen"], [2, "06 Dec 2025", "Nansha"], [3, "28 Dec 2025", "Xiamen"], [4, "28 Dec 2025", "Xiamen"], [5, "31 Dec 2025", "Xiamen"]]);
  assert.equal(note.rows[3].place.text, "Dak Lak");
  assert.equal(note.rows[0].place.text, "Dak Lak");   // DAKLAK chuẩn thành "Dak Lak"
  assert.equal(note.totalVnd, 409500000n);
  assert.equal(note.subtotalVnd, note.totalVnd);
  assert.deepEqual(note.summary, [{ port: "Xiamen", containers: 4, lumpSumVnd: 310000000n, otherVnd: 15000000n },
    { port: "Nansha", containers: 1, lumpSumVnd: 80000000n, otherVnd: 4500000n }]);
  assert.deepEqual([note.lumpSumVnd, note.otherVnd, note.additionalVnd, note.containerCount], [390000000n, 19500000n, null, 5]);
  assert.deepEqual(note.feeColumns.map(fee => [fee.code, fee.totalVnd]), [["LUMP_SUM", 390000000n], ["OTHER", 19500000n]]);
  assert.deepEqual(note.excelColumns.map(fee => fee.code), ["LUMP_SUM", "STORAGE", "TRUCKING", "GENSET", "OVERSTAY", "HC_FEE", "CANCELLATION", "AMENDMENT", "OTHER"]);
  assert.deepEqual([note.pendingCount, note.adjustmentCount, note.complete, note.period, note.lastLoadingDate], [1, 1, true, "Dec 2025", "2025-12-31"]);
  assert.equal(model.vndInWords(note.totalVnd), "SAY VIETNAM DONG FOUR HUNDRED NINE MILLION FIVE HUNDRED THOUSAND ONLY");
  assert.equal(model.addDays("2026-10-30", 15), "2026-11-14");
  assert.equal(model.dnDate(model.addDays("2026-10-30", 15)), "14 Nov 2026");
  assert.deepEqual(model.debitNoteChecks(note, dnDoc()).map(item => item.level), ["info", "info"]);
});

test("DEBIT-NOTE-02 tháng 8/2026: 99 container + 1 dòng phí hủy không đánh số, tổng từng loại phí và USD quy đổi một lần", () => {
  const trips = [];
  for (let index = 0; index < 99; index++) trips.push(dnTrip("2026-08", String(1 + (index % 28)).padStart(2, "0"), index % 3 ? "XIAMEN" : "QINGDAO",
    index < 98 ? 82000000 : 8150000000 - 98 * 82000000));
  trips[3].fee_lines = [{ fee_type_id: 10, amount_vnd: "57500000" }];
  trips[7].fee_lines = [{ fee_type_id: 3, amount_vnd: "13000000" }];
  trips[11].fee_lines = [{ fee_type_id: 2, amount_vnd: "3600000" }];
  trips[15].fee_lines = [{ fee_type_id: 1, amount_vnd: "60000000" }];
  for (const index of [3, 7, 11, 15]) trips[index].amount_vnd = String(BigInt(trips[index].unit_price_vnd) + BigInt(trips[index].fee_lines[0].amount_vnd));
  trips.push({ id: ++dnSerial, month: "2026-08-01", container: null, event_date: "2026-08-20", status: "confirmed", is_fee_only: true, is_missing_price: false,
    unit_price_vnd: null, amount_vnd: "25000000", fee_lines: [{ fee_type_id: 11, amount_vnd: "25000000", note: "Booking BK1" }] });
  const note = model.debitNote({ trips, legacy_rows: [] }, "2026-08", dnFeeTypes);
  assert.equal(note.containerCount, 99);
  assert.equal(note.rows.at(-1).no, 99);
  assert.deepEqual(note.charges, [{ date: "2026-08-20", code: "CANCELLATION", note: "Booking BK1", amountVnd: 25000000n }]);
  assert.deepEqual(note.feeColumns.map(fee => [fee.code, fee.totalVnd]), [["LUMP_SUM", 8150000000n], ["STORAGE", 57500000n], ["TRUCKING", 13000000n],
    ["GENSET", 3600000n], ["OVERSTAY", 60000000n], ["CANCELLATION", 25000000n]]);
  assert.equal(note.totalVnd, 8309100000n);
  assert.deepEqual([note.additionalVnd, note.otherVnd, note.subtotalVnd], [25000000n, 159100000n, 8309100000n]);
  assert.equal(note.summary.reduce((sum, item) => sum + item.containers, 0), 99);
  assert.equal(model.usdText(model.usdCents(note.totalVnd, model.parseRate("25,950"))), "320,196.53");
  assert.equal(model.usdText(model.usdCents(note.totalVnd, model.parseRate("25750"))), "322,683.50");
  assert.equal(model.vndInWords(note.totalVnd), "SAY VIETNAM DONG EIGHT BILLION THREE HUNDRED NINE MILLION ONE HUNDRED THOUSAND ONLY");
});

test("DEBIT-NOTE-02 số container ISO 6346, số bằng chữ, mã loại phí, chuẩn tên nơi, tỷ giá", () => {
  assert.deepEqual(model.containerCheck("csqu 3054383"), { id: "CSQU3054383", valid: true, reason: null, expected: 3 });
  assert.equal(model.containerCheck("CSQU3054384").reason, "check");
  assert.equal(model.containerCheck("BM0U9231830").reason, "format");
  assert.equal(model.containerCheck("35C-10331").valid, false);
  assert.equal(model.vndInWords(12019000001n), "SAY VIETNAM DONG TWELVE BILLION NINETEEN MILLION ONE ONLY");
  assert.equal(model.vndInWords(21n), "SAY VIETNAM DONG TWENTY-ONE ONLY");
  assert.equal(model.vndInWords(0n), "SAY VIETNAM DONG ZERO ONLY");
  assert.equal(model.vndInWords(-1n), null);
  assert.deepEqual(dnFeeTypes.map(type => model.dnFeeCode(type.name)), ["OVERSTAY", "GENSET", "TRUCKING", "INSURANCE", "INSPECTION", "HC_FEE", "OTHER", "DISCOUNT",
    "OTHER", "STORAGE", "CANCELLATION"]);
  assert.equal(model.dnFeeCode("Nâng hạ"), "OTHER");
  assert.deepEqual(model.dnPlace("GIA LAI + DAKLAK", model.DN_PLACES), { text: "Gia Lai + Dak Lak", known: true });
  assert.deepEqual(model.dnPlace("KHO MOI", model.DN_PLACES), { text: "Kho Moi", known: false });
  assert.deepEqual(["25,950", "25950", "25.950", "0", ""].map(model.parseRate), [25950n, 25950n, null, null, null]);
  assert.equal(model.usdCents(1n, 3n), 33n);   // 1 VND ÷ 3 = 0.33 USD
  assert.equal(model.usdCents(5n, 1000n), 1n);   // 0.005 làm tròn lên 0.01
  assert.equal(model.dnDate("2025-02-30"), "");
  assert.equal(model.suggestNumber("HTH", "2025-12"), "HTH-2512-001");
});

test("DEBIT-NOTE-02 kiểm tra trước khi phát hành: chặn lỗi chắc chắn, cảnh báo điểm bất thường", () => {
  const dup = dnTrip("2026-09", "02", "XIAMEN", 80000000);
  const trips = [dup, { ...dup, id: ++dnSerial }, dnTrip("2026-09", "10", "XIAMEN", 0), dnTrip("2026-09", "11", "LAO CAI", 1, [], { origin: "KHO MOI" }),
    dnTrip("2026-09", "12", "XIAMEN", 1, [], { container: "BM0U9231830" }), dnTrip("2026-09", "13", "XIAMEN", 1, [], { unit_price_vnd: null, amount_vnd: null, is_missing_price: true }),
    { id: ++dnSerial, month: "2026-09-01", container: null, event_date: "2026-09-14", status: "confirmed", is_fee_only: true, unit_price_vnd: null, amount_vnd: "100",
      fee_lines: [{ fee_type_id: 7, amount_vnd: "100", note: "Gọi 0912 345 678" }] }];
  const note = model.debitNote({ trips }, "2026-09", dnFeeTypes);
  const checks = model.debitNoteChecks(note, dnDoc({ issueDate: "2026-09-05", buyer: { display: "B" }, payment: { beneficiary: "OTHER CO", bank: "B", account: "1", swift: "S" },
    usd: { on: true, rate: "25,950", source: "", date: "2026-09-05" } }));
  const texts = checks.map(item => `${item.level}: ${item.text}`);
  for (const pattern of [/^block: 1 dòng chưa có giá/, /^block: Số container sai theo ISO 6346: BM0U9231830/, new RegExp(`^block: Container trùng trong chứng từ: ${dup.container}`),
    /^block: Còn thiếu: Tên pháp lý của khách, Địa chỉ của khách\.$/, /^block: Bật quy đổi USD nhưng thiếu/, /^block: Mô tả hoặc ghi chú có chuỗi giống số điện thoại/,
    /^warn: Chủ tài khoản nhận tiền khác bên phát hành/, /^warn: Ngày phát hành sớm hơn ngày đóng hàng cuối cùng \(13 Sep 2026\)/,
    /^warn: Nơi đóng hàng ngoài danh mục: Kho Moi/, /^warn: Cảng đến ngoài danh mục: Lao Cai/, /^warn: 1 container có LUMP-SUM bằng 0/])
    assert.ok(texts.some(text => pattern.test(text)), `${pattern} trong\n${texts.join("\n")}`);
  // Tổng thiếu giá thì để trống, không coi là 0.
  assert.deepEqual([note.totalVnd, note.subtotalVnd, note.complete], [null, null, false]);
  // Thành tiền dòng khác số trên sổ thì chặn (kiểm tra chéo cách cộng).
  const off = model.debitNote({ trips: [dnTrip("2026-09", "02", "XIAMEN", 100, [], { amount_vnd: "101" })] }, "2026-09", dnFeeTypes);
  assert.match(model.debitNoteChecks(off, dnDoc()).map(item => item.text).join(" "), /Thành tiền LUMP-SUM \+ phí khác số trên sổ/);
});

test("DEBIT-NOTE-02 dòng sổ gốc không có bản sửa đọc theo Sheet; dòng không container thành ADDITIONAL CHARGES", () => {
  const ledger = { legacy_rows: [
    { month: "2026-10-01", kind: "trip", editable: false, source_total_vnd: "900", fee_lines: [],
      display: { container: "CSQU3054383", carrier: "C", date: "2026-10-02", from: "A", to: "B", unit_price: "900", flags: [] } },
    { month: "2026-10-01", kind: "trip", editable: false, source_total_vnd: "0", fee_lines: [],
      display: { container: dnContainer(77), date: "2026-10-01", unit_price: "", flags: ["MISSING_PRICE"] } },
    { month: "2026-10-01", kind: "trip", editable: false, source_total_vnd: "70", fee_lines: [{ fee_type_id: 1, amount_vnd: "70" }],
      display: { container: "", date: null, unit_price: "", flags: [] } },
  ] };
  const note = model.debitNote(ledger, "2026-10", [{ id: 1, name: "Neo" }]);
  assert.deepEqual(note.rows.map(row => [row.container, row.lumpSumVnd, row.amountVnd]), [[dnContainer(77), null, null], ["CSQU3054383", 900n, 900n]]);
  assert.deepEqual(note.charges, [{ date: null, code: "OVERSTAY", note: "", amountVnd: 70n }]);
  assert.deepEqual([note.missingCount, note.totalVnd, note.lumpSumVnd], [1, null, null]);
});

test("tách phụ phí theo bảng PS: chỉ ghi 'Tổng tiền không đổi' khi mọi chuyến giữ tổng", () => {
  const ready = [
    { before: [{ fee_type_id: 9, amount_vnd: "2000000" }], after: [{ fee_type_id: 1, amount_vnd: "1500000" }, { fee_type_id: 2, amount_vnd: "500000" }] },
    { before: [{ fee_type_id: 7, amount_vnd: "800000" }], after: [{ fee_type_id: 3, amount_vnd: "800000" }] }];
  assert.deepEqual(model.planPsFees(ready), { count: 2, totalVnd: 2800000n, same: true });
  const changed = [...ready, { before: [{ fee_type_id: 7, amount_vnd: "100" }], after: [{ fee_type_id: 1, amount_vnd: "101" }] }];
  assert.deepEqual(model.planPsFees(changed), { count: 3, totalVnd: null, same: false });
  assert.deepEqual(model.planPsFees([{ before: [], after: [] }]), { count: 1, totalVnd: null, same: false });
  assert.deepEqual(model.planPsFees([]), { count: 0, totalVnd: 0n, same: false });
  const names = { 1: "Neo", 2: "Điện" };
  assert.equal(model.feeLinesText(ready[0].after, id => names[id]), "Neo 1.500.000 + Điện 500.000");
});
