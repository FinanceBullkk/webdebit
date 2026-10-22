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
  assert.throws(() => model.parseCellEdit("amount_vnd", "1"), /không được sửa/);
});

test("legacy edit adjustments sum signed digit strings exactly; none is null, not 0", () => {
  assert.equal(model.sumAdjustments([]), null);
  assert.equal(model.sumAdjustments([{ amount_vnd: "5000000" }, { amount_vnd: "-65000000" }]), -60000000n);
  assert.equal(model.sumAdjustments([{ amount_vnd: "9007199254740993" }, { amount_vnd: "1" }]), 9007199254740994n);
  assert.throws(() => model.sumAdjustments([{ amount_vnd: "1.5" }]));
});
