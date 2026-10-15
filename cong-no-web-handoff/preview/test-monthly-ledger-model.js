const assert = require("node:assert/strict");
const { snapshot, planReceipt } = require("./monthly-ledger-model.js");

const all = snapshot();
assert.equal(all.months.length, 3);
assert.deepEqual(all.months.map(month => month.balance), [0n, 48000000n, 60000000n]);
assert.deepEqual([all.allBalance, all.visibleBalance, all.waitingPrice, all.waitingConfirmation], [108000000n, 108000000n, 1, 1]);
assert.deepEqual(all.months[1].shipments.length, 4);
assert.deepEqual(all.months[1].payments.length, 2);
assert.equal(all.months[0].payments[0].date, "2026-02-10");
assert.equal(all.months[2].payments[1].status, "waiting_confirmation");

const january = snapshot({ period: "2026-01" });
assert.deepEqual([january.months.length, january.visibleBalance, january.allBalance], [1, 48000000n, 108000000n]);

const jan31 = snapshot({ asOf: "2026-01-31" });
assert.deepEqual(jan31.months.map(month => month.balance), [441500000n, 98000000n]);
assert.equal(jan31.allBalance, 539500000n);
const feb9 = snapshot({ asOf: "2026-02-09" });
assert.deepEqual(feb9.months.map(month => month.balance), [441500000n, 98000000n, 90000000n]);
assert.equal(feb9.allBalance, 629500000n);
assert.equal(feb9.waitingPrice, 0);
assert.deepEqual(planReceipt("70000000"), {
  allocations: [{ period: "2026-01", amount: 48000000n }, { period: "2026-02", amount: 22000000n }],
  unallocated: 0n,
});
assert.deepEqual(planReceipt("130000000"), {
  allocations: [{ period: "2026-01", amount: 48000000n }, { period: "2026-02", amount: 60000000n }],
  unallocated: 22000000n,
});
assert.throws(() => planReceipt("-1"));
assert.throws(() => snapshot({ asOf: "2026-02-30" }));
console.log("Monthly fixture dates, period, pending and oldest-first allocation: PASS");
