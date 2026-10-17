const assert = require("node:assert/strict");
const model = require("./so-cong-no-v5-model.js");
const { lineAmount, monthTotals, allocateReceipt, allocateReceipts, ledgerBalance, canClose } = model;

assert.deepEqual(Object.keys(model), ["lineAmount", "monthTotals", "allocateReceipt", "allocateReceipts", "ledgerBalance", "canClose"]);
const lines = Object.freeze([
  ["DEMO-105", "40000000"], ["DEMO-106", "30000000"],
  ["DEMO-107", "20000000"], ["DEMO-103", null],
].map(([id, unitPriceVnd]) => Object.freeze({
  id, unitPriceVnd, otherFeeVnd: null, plugFeeVnd: null, escortFeeVnd: null,
})));
assert.equal(lineAmount(lines[0]), 40000000n);
assert.equal(lineAmount(lines[3]), null);
assert.equal(lineAmount({ ...lines[0], otherFeeVnd: "1000000" }), 41000000n);
assert.equal(lineAmount({ ...lines[0], plugFeeVnd: "1000000", escortFeeVnd: "1000000" }), 42000000n);
assert.equal(lineAmount({ ...lines[0], unitPriceVnd: "0" }), 0n);
assert.equal(lineAmount({ ...lines[3], otherFeeVnd: "1000000" }), null);
const totals = { pricedCount: 3, pricedTotalVnd: 90000000n, missingPriceIds: ["DEMO-103"] };
assert.deepEqual(monthTotals(lines), totals);
assert.deepEqual(monthTotals([]), { pricedCount: 0, pricedTotalVnd: 0n, missingPriceIds: [] });
assert.deepEqual(monthTotals([lines[3], { ...lines[3], id: "second-missing" }]).missingPriceIds,
  ["DEMO-103", "second-missing"]);

const buckets = Object.freeze([
  { key: "before-T01", kind: "closed", balanceVnd: "20000000" },
  { key: "T01", kind: "closed", balanceVnd: "20000000" },
  { key: "T02", kind: "closed", balanceVnd: "30000000" },
  { key: "T03", kind: "closed", balanceVnd: "25000000" },
  { key: "T04", kind: "open", balanceVnd: "90000000" },
].map(Object.freeze));
for (const [receipt, amounts, overpayment] of [
  ["120000000", [20000000n, 20000000n, 30000000n, 25000000n, 25000000n], 0n],
  ["200000000", [20000000n, 20000000n, 30000000n, 25000000n, 90000000n], 15000000n],
]) {
  const expected = {
    allocations: amounts.map((amountVnd, i) => ({ key: buckets[i].key, kind: buckets[i].kind, amountVnd })),
    overpaymentVnd: overpayment,
  };
  assert.deepEqual(allocateReceipt(receipt, buckets), expected);
  assert.equal(expected.allocations.reduce((sum, item) => sum + item.amountVnd, expected.overpaymentVnd), BigInt(receipt));
}
assert.deepEqual(allocateReceipt("0", buckets), { allocations: [], overpaymentVnd: 0n });
assert.deepEqual(allocateReceipt("120000000", []), { allocations: [], overpaymentVnd: 120000000n });
const skipped = [{ key: "zero", kind: "closed", balanceVnd: 0n },
  { key: "credit", kind: "closed", balanceVnd: -1n }];
assert.deepEqual(allocateReceipt("120000000", [...skipped, ...buckets]), allocateReceipt("120000000", buckets));
// Caller owns priority, even when deliberately different from the usual debt order.
assert.deepEqual(allocateReceipt("120000000", [buckets[4], buckets[3], buckets[0]]).allocations,
  [{ key: "T04", kind: "open", amountVnd: 90000000n },
    { key: "T03", kind: "closed", amountVnd: 25000000n },
    { key: "before-T01", kind: "closed", amountVnd: 5000000n }]);

const ledger = { closedVnd: "95000000", openVnd: "90000000", buckets };
const receipt120 = Object.freeze({ amountVnd: "120000000", receivedOn: "2026-04-20" });
const pending = Object.freeze({ amountVnd: "5000000", receivedOn: null });
const result120 = { closedRemainingVnd: 0n, openRemainingVnd: 65000000n,
  overpaymentVnd: 0n, receivedVnd: 120000000n, endOfMonthVnd: 0n };
const result200 = { closedRemainingVnd: 0n, openRemainingVnd: 0n,
  overpaymentVnd: 15000000n, receivedVnd: 200000000n, endOfMonthVnd: -15000000n };
const cases = [
  [[], { closedRemainingVnd: 95000000n, openRemainingVnd: 90000000n,
    overpaymentVnd: 0n, receivedVnd: 0n, endOfMonthVnd: 95000000n }],
  [[receipt120], result120],
  [[{ amountVnd: "200000000", receivedOn: "2026-04-22" }], result200],
  [[receipt120, { amountVnd: "80000000", receivedOn: "2026-04-22" }], result200],
  [[{ amountVnd: "20000000", receivedOn: "2026-04-20" }],
    { closedRemainingVnd: 75000000n, openRemainingVnd: 90000000n,
      overpaymentVnd: 0n, receivedVnd: 20000000n, endOfMonthVnd: 75000000n }],
];
for (const [receipts, expected] of cases) {
  const result = ledgerBalance({ ...ledger, receipts });
  assert.deepEqual(result, expected);
  assert.deepEqual(ledgerBalance({ ...ledger, receipts: [...receipts, pending] }), result);
  assert.ok(result.closedRemainingVnd >= 0n && result.openRemainingVnd >= 0n);
  assert.equal(Object.values(result).includes(185000000n), false);
  assert.deepEqual(Object.keys(result), Object.keys(result120));
}
// An unconfirmed receipt is ignored completely, including its unknown amount.
assert.deepEqual(ledgerBalance({ ...ledger, receipts: [receipt120, { amountVnd: null, receivedOn: null }] }), result120);

// Each tuple states one receipt's allocations in bucket order, then its surplus.
for (const [amounts, expected] of [
  [[], []],
  [["20000000"], [[[20000000n], 0n]]],
  [["25000000"], [[[20000000n, 5000000n], 0n]]],
  [["25000000", null, "20000000"],
    [[[20000000n, 5000000n], 0n], [[0n, 15000000n, 5000000n], 0n]]],
  [["120000000", "80000000", "1"],
    [[[20000000n, 20000000n, 30000000n, 25000000n, 25000000n], 0n],
      [[0n, 0n, 0n, 0n, 65000000n], 15000000n], [[], 1n]]],
  [["0"], [[[], 0n]]],
]) {
  const receipts = Object.freeze(amounts.map((amountVnd, id) => Object.freeze({
    id, amountVnd, receivedOn: amountVnd === null ? null : "2026-04-20",
  })));
  const before = structuredClone({ receipts, buckets });
  const result = allocateReceipts(receipts, buckets);
  const confirmed = receipts.filter(receipt => receipt.receivedOn !== null);
  assert.deepEqual(result.perReceipt, expected.map(([values, overpaymentVnd], i) => ({
    id: confirmed[i].id, overpaymentVnd,
    allocations: values.flatMap((amountVnd, j) => amountVnd === 0n ? [] :
      [{ key: buckets[j].key, kind: buckets[j].kind, amountVnd }]),
  })));
  const balance = ledgerBalance({ ...ledger, receipts });
  const aggregate = allocateReceipt(balance.receivedVnd, buckets);
  const allocations = result.perReceipt.flatMap(receipt => receipt.allocations);
  for (const bucket of buckets) {
    assert.equal(allocations.filter(item => item.key === bucket.key).reduce((sum, item) => sum + item.amountVnd, 0n),
      aggregate.allocations.find(item => item.key === bucket.key)?.amountVnd ?? 0n);
  }
  for (const kind of ["closed", "open"]) {
    assert.equal(BigInt(ledger[`${kind}Vnd`]) - allocations.filter(item => item.kind === kind)
      .reduce((sum, item) => sum + item.amountVnd, 0n), balance[`${kind}RemainingVnd`]);
  }
  assert.equal(result.overpaymentVnd, balance.overpaymentVnd);
  assert.equal(result.overpaymentVnd, result.perReceipt.reduce((sum, item) => sum + item.overpaymentVnd, 0n));
  assert.ok(allocations.every(item => item.amountVnd > 0n));
  assert.deepEqual(allocateReceipts(receipts, buckets), result);
  assert.deepEqual({ receipts, buckets }, before);
}
assert.deepEqual(allocateReceipts([{ ...receipt120, id: "no-debt" }], []), {
  perReceipt: [{ id: "no-debt", allocations: [], overpaymentVnd: 120000000n }], overpaymentVnd: 120000000n,
});
assert.deepEqual(allocateReceipts([receipt120], [...skipped, ...buckets]), allocateReceipts([receipt120], buckets));

const closeInput = Object.freeze({ lines, enteredBy: "Nguyễn Văn A", closedBy: "Nguyễn Văn A" });
const blocked = canClose(closeInput);
assert.equal(blocked.ok, false);
assert.equal(blocked.reasons.length, 2);
assert.match(blocked.reasons[1], /DEMO-103/);
assert.deepEqual(canClose({ ...closeInput, lines: lines.slice(0, 3), closedBy: "Lê Văn C" }), { ok: true, reasons: [] });
assert.equal(canClose({ ...closeInput, closedBy: "Lê Văn C" }).reasons.length, 1);
assert.equal(canClose({ ...closeInput, lines: lines.slice(0, 3) }).reasons.length, 1);

for (const invalid of ["40.000.000", "abc", "-1", -1n, 12.5, 12, "", " 12", "12\n", undefined]) {
  for (const field of ["unitPriceVnd", "otherFeeVnd", "plugFeeVnd", "escortFeeVnd"]) {
    assert.throws(() => lineAmount({ ...lines[0], [field]: invalid }));
  }
  assert.throws(() => allocateReceipt(invalid, buckets));
  assert.throws(() => allocateReceipts([{ ...receipt120, amountVnd: invalid }], buckets));
  assert.throws(() => ledgerBalance({ ...ledger, closedVnd: invalid, receipts: [] }));
  assert.throws(() => ledgerBalance({ ...ledger, openVnd: invalid, receipts: [] }));
  assert.throws(() => ledgerBalance({ ...ledger, receipts: [{ ...receipt120, amountVnd: invalid }] }));
}
for (const invalid of [null, "40.000.000", "abc", 12.5, undefined]) {
  assert.throws(() => allocateReceipt("0", [{ ...buckets[0], balanceVnd: invalid }]));
  assert.throws(() => allocateReceipts([], [{ ...buckets[0], balanceVnd: invalid }]));
}
assert.throws(() => allocateReceipt(null, buckets));
assert.throws(() => allocateReceipts([{ ...receipt120, amountVnd: null }], buckets));
assert.throws(() => allocateReceipts([], [{ ...buckets[0], kind: "unknown" }]));
assert.throws(() => ledgerBalance({ ...ledger, closedVnd: null, receipts: [] }));
assert.throws(() => ledgerBalance({ ...ledger, openVnd: null, receipts: [] }));
assert.throws(() => ledgerBalance({ ...ledger, receipts: [{ ...receipt120, amountVnd: null }] }));
assert.throws(() => allocateReceipt("0", [{ ...buckets[0], kind: "unknown" }]));
assert.throws(() => ledgerBalance({ ...ledger, closedVnd: "0", receipts: [] }));
for (const receivedOn of [undefined, "", " ", 0]) {
  assert.throws(() => ledgerBalance({ ...ledger, receipts: [{ ...receipt120, receivedOn }] }));
  assert.throws(() => allocateReceipts([{ ...receipt120, receivedOn }], buckets));
}
assert.throws(() => canClose({ ...closeInput, enteredBy: null }));
assert.throws(() => canClose({ ...closeInput, closedBy: "" }));

const huge = "900719925474099312345";
assert.deepEqual(allocateReceipts([{ id: "huge", receivedOn: "2026-04-20", amountVnd: huge },
  { id: "next", receivedOn: "2026-04-21", amountVnd: 1n }],
[{ key: "large", kind: "closed", balanceVnd: huge }]), {
  perReceipt: [{ id: "huge", allocations: [{ key: "large", kind: "closed", amountVnd: BigInt(huge) }], overpaymentVnd: 0n },
    { id: "next", allocations: [], overpaymentVnd: 1n }], overpaymentVnd: 1n,
});
assert.equal(lineAmount({ ...lines[0], unitPriceVnd: huge, otherFeeVnd: "1" }), BigInt(huge) + 1n);
assert.deepEqual(allocateReceipt(huge, [{ key: "large", kind: "closed", balanceVnd: huge }]),
  { allocations: [{ key: "large", kind: "closed", amountVnd: BigInt(huge) }], overpaymentVnd: 0n });
for (const [fn, input] of [
  [lineAmount, lines[0]], [monthTotals, lines], [canClose, closeInput],
  [ledgerBalance, Object.freeze({ ...ledger, receipts: Object.freeze([receipt120, pending]) })],
]) {
  const before = structuredClone(input);
  assert.deepEqual(fn(input), fn(input));
  assert.deepEqual(input, before);
}
const beforeBuckets = structuredClone(buckets);
assert.deepEqual(allocateReceipt("120000000", buckets), allocateReceipt("120000000", buckets));
assert.deepEqual(buckets, beforeBuckets);
console.log("V5 exact money, ordered allocation, pending exclusion and close guards: PASS");
