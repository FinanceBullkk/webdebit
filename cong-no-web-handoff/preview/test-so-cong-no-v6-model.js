const assert = require("node:assert/strict");
const model = require("./so-cong-no-v6-model.js");
const { lineAmount, monthTotals, isDirectEditable, monthChain, allocate, validateAdjustment } = model;

assert.deepEqual(Object.keys(model), ["lineAmount", "monthTotals", "isDirectEditable", "monthChain", "allocate", "validateAdjustment"]);
const line = (id, unitPriceVnd, pastedAmountVnd = null) => ({
  id, unitPriceVnd, otherFeeVnd: null, plugFeeVnd: null, escortFeeVnd: null, pastedAmountVnd,
});
const lines = [line("DEMO-105", "40000000"), line("DEMO-106", "30000000"),
  line("DEMO-107", "20000000"), line("DEMO-103", null)];
const pending = { id: "CT-CHO-05", monthKey: "2026-04", receivedOn: null,
  method: null, ref: "CT-CHO-05", amountVnd: "5000000" };
const receipt = amountVnd => ({ id: "UNC-0420", monthKey: "2026-04", receivedOn: "2026-04-20",
  method: "Chuyển khoản", ref: "UNC-0420", amountVnd });
const adjustment = { id: "ADJ-1", monthKey: "2026-03", lineId: "DEMO-104",
  amountVnd: "5000000", reason: "Thiếu phí áp tải chuyến DEMO-104" };
const book = {
  opening: { beforeKey: "before-2026-01", beforeBalanceVnd: "20000000", months: [
    { key: "2026-01", endOfMonthVnd: "40000000", remainingVnd: "20000000", lines: [line("DEMO-101", "20000000")] },
    { key: "2026-02", endOfMonthVnd: "70000000", remainingVnd: "30000000", lines: [line("DEMO-102", "30000000")] },
    { key: "2026-03", endOfMonthVnd: "95000000", remainingVnd: "25000000", lines: [line("DEMO-104", "25000000")] },
  ] },
  months: [{ key: "2026-04", lines }], adjustments: [], receipts: [pending],
};
const withReceipt = amount => ({ ...book, receipts: [pending, receipt(amount)] });
const withAdjustment = receipts => ({ ...book, adjustments: [adjustment], receipts });

assert.equal(lineAmount(lines[0]), 40000000n);
assert.equal(lineAmount(lines[3]), null);
assert.equal(lineAmount({ ...lines[0], otherFeeVnd: "1000000", plugFeeVnd: 2000000n,
  escortFeeVnd: "3000000" }), 46000000n);
assert.equal(lineAmount({ ...lines[3], otherFeeVnd: "1000000" }), null);
assert.deepEqual(monthTotals(lines), { pricedCount: 3, pricedTotalVnd: 90000000n,
  missingPriceIds: ["DEMO-103"], mismatches: [] });

function checkAllocation(input, expected, excess) {
  const result = allocate(input);
  assert.deepEqual(result.receipts.map(item => item.allocations.map(row => row.amountVnd)), expected);
  assert.equal(result.overpaymentVnd, excess);
  for (const item of result.receipts) {
    const amount = input.receipts.find(row => row.id === item.id).amountVnd;
    assert.equal(item.allocations.reduce((sum, row) => sum + row.amountVnd, item.overpaymentVnd), BigInt(amount));
  }
  assert.equal(result.remaining.reduce((sum, row) => sum + row.balanceVnd, 0n) - result.overpaymentVnd,
    monthChain(input).at(-1).endOfMonthVnd);
  return result;
}

const base = monthChain(book);
assert.deepEqual(base.map(row => row.endOfMonthVnd), [40000000n, 70000000n, 95000000n, 185000000n]);
assert.deepEqual(base.map(row => row.source), ["opening", "opening", "opening", "web"]);
assert.equal(base[3].carryVnd, 95000000n);
assert.equal(base[3].chargesVnd, 90000000n);
assert.equal(base[3].receivedVnd, 0n);
assert.equal(base[0].chargesVnd, null);
assert.equal(base[0].receivedVnd, null);
assert.deepEqual(base.map(row => row.lineCount), [1, 1, 1, 4]);
assert.deepEqual(base.map(row => row.pricedCount), [1, 1, 1, 3]);
assert.deepEqual(base.map(row => row.monthTotalVnd), [20000000n, 30000000n, 25000000n, 90000000n]);
assert.deepEqual(monthChain({ ...book, receipts: [] }), base);
assert.deepEqual(allocate({ ...book, receipts: [] }), allocate(book));
checkAllocation(book, [], 0n);

const paid120 = withReceipt("120000000");
assert.equal(monthChain(paid120)[3].endOfMonthVnd, 65000000n);
const allocated120 = checkAllocation(paid120,
  [[20000000n, 20000000n, 30000000n, 25000000n, 25000000n]], 0n);
assert.deepEqual(allocated120.receipts[0].allocations.map(row => row.key),
  ["before-2026-01", "2026-01", "2026-02", "2026-03", "2026-04"]);
assert.equal(allocated120.receipts[0].overpaymentVnd, 0n);

const paid200 = withReceipt("200000000");
assert.equal(monthChain(paid200)[3].endOfMonthVnd, -15000000n);
const allocated200 = checkAllocation(paid200,
  [[20000000n, 20000000n, 30000000n, 25000000n, 90000000n]], 15000000n);
assert.equal(allocated200.receipts[0].overpaymentVnd, 15000000n);

const adjusted = withAdjustment([pending]);
const adjustedChain = monthChain(adjusted);
assert.deepEqual(adjustedChain.map(row => row.endOfMonthVnd),
  [40000000n, 70000000n, 100000000n, 190000000n]);
assert.equal(adjustedChain[3].carryVnd, 100000000n);
assert.equal(adjustedChain[2].monthTotalVnd, 30000000n);
assert.equal(adjustedChain[2].pricedCount, 1);
assert.deepEqual(adjustedChain.map(row => row.carryVnd), base.map(row =>
  row.key === "2026-04" ? 100000000n : row.carryVnd));
checkAllocation(adjusted, [], 0n);
const adjustedPaid = withAdjustment([pending, receipt("120000000")]);
assert.equal(monthChain(adjustedPaid)[3].endOfMonthVnd, 70000000n);
checkAllocation(adjustedPaid, [[20000000n, 20000000n, 30000000n, 30000000n, 20000000n]], 0n);

const pasted = { ...book, months: [{ key: "2026-04", lines: [...lines,
  line("DEMO-108", "12000000"), line("DEMO-109", "10000000", "99000000")] }] };
const pastedMonth = monthChain(pasted)[3];
assert.equal(pastedMonth.lineCount, 6);
assert.equal(pastedMonth.pricedCount, 5);
assert.equal(pastedMonth.chargesVnd, 112000000n);
assert.equal(pastedMonth.endOfMonthVnd, 207000000n);
assert.deepEqual(pastedMonth.mismatches, [{ id: "DEMO-109", pastedVnd: 99000000n,
  computedVnd: 10000000n, diffVnd: 89000000n }]);
checkAllocation(pasted, [], 0n);

for (const [key, today, expected] of [
  ["2026-04", "2026-05-05", true], ["2026-04", "2026-05-06", false],
  ["2026-12", "2027-01-05", true], ["2026-12", "2027-01-06", false],
  ["2026-04", "2026-04-30", true], ["2026-04", "2026-03-01", true],
]) assert.equal(isDirectEditable(key, today), expected);
const badAdjustment = validateAdjustment({ monthKey: "2026-04", lineId: null,
  reason: "  ", amountVnd: "0" }, book);
assert.equal(badAdjustment.ok, false);
assert.equal(badAdjustment.reasons.length, 2);
assert.deepEqual(validateAdjustment({ monthKey: "2026-04", lineId: "DEMO-105",
  reason: "Sửa phí", amountVnd: "-1" }, book), { ok: true, reasons: [] });
assert.equal(validateAdjustment({ monthKey: "2026-99", lineId: "missing",
  reason: "", amountVnd: "abc" }, book).reasons.length, 3);
assert.deepEqual(validateAdjustment(adjustment, book), { ok: true, reasons: [] });
const unknownLine = validateAdjustment({ ...adjustment, lineId: "DEMO-999" }, book);
assert.equal(unknownLine.ok, false);
assert.deepEqual(unknownLine.reasons, ["Dòng không có trong tháng."]);
assert.deepEqual(validateAdjustment({ ...adjustment, lineId: null }, book), { ok: true, reasons: [] });
const missingMonth = validateAdjustment({ ...adjustment, monthKey: "2026-09" }, book);
assert.equal(missingMonth.ok, false);
assert.deepEqual(missingMonth.reasons, ["Tháng không có trong sổ."]);
const extraOpeningLines = { ...book, opening: { ...book.opening,
  months: book.opening.months.map(month => ({ ...month,
    lines: [...month.lines, line(`${month.key}-X`, "1000000")] })) } };
const extraChain = monthChain(extraOpeningLines);
assert.deepEqual(extraChain.map(row => row.lineCount), [2, 2, 2, 4]);
assert.deepEqual(extraChain.map(row => row.pricedCount), [2, 2, 2, 3]);
assert.deepEqual(extraChain.map(row => row.monthTotalVnd),
  [21000000n, 31000000n, 26000000n, 90000000n]);
assert.deepEqual(extraChain.map(row => row.endOfMonthVnd), base.map(row => row.endOfMonthVnd));
assert.deepEqual(extraChain.map(row => row.carryVnd), base.map(row => row.carryVnd));
assert.deepEqual(allocate(extraOpeningLines), allocate(book));

for (const invalid of ["40.000.000", "abc", 12.5, "-1", -1n, undefined]) {
  assert.throws(() => lineAmount({ ...lines[0], unitPriceVnd: invalid }));
  assert.throws(() => lineAmount({ ...lines[0], otherFeeVnd: invalid }));
  assert.throws(() => monthChain({ ...book, opening: { ...book.opening, beforeBalanceVnd: invalid } }));
}
assert.throws(() => monthChain({ ...book, opening: { ...book.opening, beforeBalanceVnd: null } }));
assert.throws(() => monthChain({ ...book, opening: { ...book.opening, beforeBalanceVnd: "21000000" } }));
for (const badLines of [undefined, null, "DEMO-101", [{ id: "" }], [{ id: "DEMO-101" }, { id: "DEMO-101" }]]) {
  assert.throws(() => monthChain({ ...book, opening: { ...book.opening,
    months: [{ ...book.opening.months[0], lines: badLines }, ...book.opening.months.slice(1)] } }));
}
assert.throws(() => monthChain({ ...book, adjustments: [{ ...adjustment, amountVnd: "abc" }] }));
assert.throws(() => monthChain({ ...book, adjustments: [{ ...adjustment, reason: " " }] }));
assert.throws(() => monthChain({ ...book, months: [{ key: "2026-03", lines }] }));
assert.throws(() => monthChain({ ...book, months: [{ key: "2026-04", lines }, { key: "2026-04", lines }] }));
assert.throws(() => allocate({ ...book, adjustments: [{ ...adjustment, amountVnd: "-25000001" }] }));
assert.equal(lineAmount({ ...lines[0], unitPriceVnd: "900719925474099312345", otherFeeVnd: "1" }),
  900719925474099312346n);
const gap = { ...book, months: [...book.months, { key: "2026-06", lines: [] }] };
assert.equal(monthChain(gap)[4].endOfMonthVnd, 185000000n);

function freezeDeep(value) {
  if (value && typeof value === "object") {
    Object.values(value).forEach(freezeDeep);
    Object.freeze(value);
  }
  return value;
}
for (const input of [book, paid120, paid200, adjustedPaid, pasted]) {
  const frozen = freezeDeep(structuredClone(input));
  assert.deepEqual(monthChain(frozen), monthChain(frozen));
  assert.deepEqual(allocate(frozen), allocate(frozen));
}
console.log("V6 exact money, opening, reallocation, adjustment and edit window: PASS");
