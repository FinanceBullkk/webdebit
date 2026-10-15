const test = require('node:test');
const assert = require('node:assert/strict');
const { createWorkbench } = require('./customer-ledger-workbench.js');

test('fee estimate sums price and all three fees, while blank fee is unknown', () => {
  const w=createWorkbench();
  const [r]=w.paste('2026-03','2026-03-04\tDEMO-X\tTàu A\tShipper A\tA\tB\t2000000\t100000\t200000\t300000');
  assert.equal(w.estimate(r),2600000n);
  const [incomplete]=w.paste('2026-03','2026-03-05\tDEMO-Y\tTàu B\tShipper B\tA\tB\t2000000\t\t200000\t300000');
  assert.equal(w.estimate(incomplete),null);
});

test('receipt submit remains pending, repeated request does not change posted balance', () => {
  const w=createWorkbench();
  const input={date:'2026-03-20',amount:'60000000',requestId:'demo-1',unconfirmed:true};
  assert.equal(w.saveReceipt(input).ok,true);
  assert.equal(w.snapshot().allBalance,95000000n);
  assert.equal(w.saveReceipt(input).duplicate,true);
  assert.equal(w.snapshot().allBalance,95000000n);
});

test('UI labels pending-only workflow and does not offer fixture posting', () => {
  const fs=require('node:fs'), path=require('node:path');
  const html=fs.readFileSync(path.join(__dirname,'customer-ledger-workbench.html'),'utf8');
  const ui=fs.readFileSync(path.join(__dirname,'customer-ledger-workbench-ui.js'),'utf8');
  assert.match(html,/id="overpay-period"/);
  assert.match(html,/Lưu nháp khoản thu/);
  assert.doesNotMatch(html,/Ghi vào fixture tạm/);
  assert.match(ui,/Chờ duyệt/);
  assert.doesNotMatch(ui,/status posted/);
});

test('overpay period must be selected and stays pending until separate approval', () => {
  const w=createWorkbench();
  assert.throws(()=>w.planReceipt('110000000','2026-04-01',{overpayPeriod:'auto'}));
  const plan=w.planReceipt('110000000','2026-04-01',{overpayPeriod:'2026-03'});
  assert.deepEqual(plan.overpayment,{period:'2026-03',amount:15000000n});
  assert.equal(w.snapshot().allBalance,95000000n);
});
