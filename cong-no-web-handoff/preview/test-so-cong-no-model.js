const assert = require("node:assert/strict");
const { snapshot, allocateOldestFirst } = require("./so-cong-no-model.js");

const a = snapshot();
assert.deepEqual([a.previous, a.selected, a.all, a.opening], [2800000000n, 300000000n, 3100000000n, 0n]);
assert.deepEqual(a.rows.map(row => row.running), [500000000n, 300000000n]);
assert.equal(a.pending.length, 2);

const early = snapshot({ asOf: "2026-10-10" });
assert.deepEqual([early.selected, early.all], [500000000n, 3300000000n]);
assert.deepEqual(early.rows.map(row => row.id), ["CH-001"]);
assert.equal(early.pending.length, 0);

const september = snapshot({ fixture: "B", period: "2026-09" });
assert.deepEqual([september.previous, september.selected, september.later, september.all, september.opening],
  [2800000000n, 0n, 250000000n, 3050000000n, 100000000n]);
assert.deepEqual(september.rows.map(row => row.id), ["PT-003/A1"]);
assert.equal(september.rows[0].running, 0n);

const october = snapshot({ fixture: "B", pageSize: 2 });
assert.deepEqual([october.selected, october.all, october.pageCount], [250000000n, 3050000000n, 2]);
assert.deepEqual(october.rows.map(row => row.running), [500000000n, 300000000n]);
const next = snapshot({ fixture: "B", page: 2, pageSize: 2 });
assert.deepEqual(next.rows.map(row => [row.id, row.running]), [["PT-003/A2", 250000000n]]);
assert.equal(next.rows[0].signed, "-50000000");
const allocation = allocateOldestFirst("150000000", [
  { period: "2026-10", balanceVnd: "300000000" },
  { period: "2026-09", balanceVnd: "100000000" },
]);
assert.deepEqual(allocation.allocations, [
  { period: "2026-09", amountVnd: 100000000n },
  { period: "2026-10", amountVnd: 50000000n },
]);
assert.equal(allocation.unallocatedVnd, 0n);
assert.deepEqual(allocateOldestFirst("400000000", [{ period: "2026-10", balanceVnd: "300000000" }]),
  { allocations: [{ period: "2026-10", amountVnd: 300000000n }], unallocatedVnd: 100000000n });
assert.throws(() => allocateOldestFirst("-1", []));
assert.throws(() => allocateOldestFirst("100", [{ period: "2026-09", balanceVnd: "10" }, { period: "2026-09", balanceVnd: "20" }]));
assert.deepEqual(allocateOldestFirst("100", [
  { period: "2026-08", balanceVnd: "0" },
  { period: "2026-09", balanceVnd: "-50" },
  { period: "2026-10", balanceVnd: "150" },
]), { allocations: [{ period: "2026-10", amountVnd: 100n }], unallocatedVnd: 0n });
for (const receiptVnd of ["0", null, ""]) {
  assert.throws(() => allocateOldestFirst(receiptVnd, []), /Invalid receipt amount/);
}
for (const balanceVnd of [null, ""]) {
  assert.throws(() => allocateOldestFirst("100", [{ period: "2026-10", balanceVnd }]), /Invalid period balance/);
}
assert.throws(() => allocateOldestFirst("100", [{ period: "2026-10" }]), /Invalid period balance/);
for (const periodBalances of [null, {}, ""]) {
  assert.throws(() => allocateOldestFirst("100", periodBalances), /Invalid period balances/);
}
assert.throws(() => allocateOldestFirst("100", [{ period: "2026-13", balanceVnd: "100" }]), /Invalid period balance/);
assert.deepEqual(allocateOldestFirst("9007199254740995", [{ period: "2026-10", balanceVnd: "9007199254740993" }]),
  { allocations: [{ period: "2026-10", amountVnd: 9007199254740993n }], unallocatedVnd: 2n });
assert.throws(() => snapshot({ asOf: "2026-10-15" }));
console.log("Fixture A/B, as-of date, oldest-first allocation and page continuation: PASS");
