const test = require('node:test');
const assert = require('node:assert/strict');
const { createWorkbench } = require('./customer-ledger-workbench.js');
const fs=require('node:fs');
const path=require('node:path');

test('standalone UI exposes month filter, local scroll, inline editor, and receipt confirmation',()=>{
  const html=fs.readFileSync(path.join(__dirname,'customer-ledger-workbench.html'),'utf8');
  const css=fs.readFileSync(path.join(__dirname,'customer-ledger-workbench.css'),'utf8');
  const ui=fs.readFileSync(path.join(__dirname,'customer-ledger-workbench-ui.js'),'utf8');
  for(const token of ['Sổ công nợ — KHACH_MAU','value="all"','id="as-of"','id="receipt-confirmed"','type="checkbox"','customer-ledger-workbench.js']) assert.ok(html.includes(token),token);
  assert.match(css,/\.table-scroll\s*\{[^}]*overflow-x:\s*auto/);
  assert.match(css,/thead th\s*\{[^}]*font-size:\s*12px/);
  for(const token of ['addDraft','paste','fillSelected','saveShipments','planReceipt','saveReceipt','data-detail','aria-live']) assert.ok(ui.includes(token),token);
});



test('fixture snapshot separates all-period balance from filtered balance and excludes pending', () => {
  const w = createWorkbench();
  const all = w.snapshot({ asOf: '2026-04-30' });
  assert.equal(all.period, 'all');
  assert.deepEqual(all.months.map(m => m.period), ['2026-01', '2026-02', '2026-03']);
  assert.equal(all.allBalance, 95000000n);
  const one = w.snapshot({ asOf: '2026-04-30', period: '2026-02' });
  assert.equal(one.allBalance, 95000000n);
  assert.equal(one.visibleBalance, 30000000n);
  assert.equal(one.months.length, 1);
  assert.equal(one.months[0].waitingPrice, 1);
  assert.equal(w.snapshot({ asOf: '2026-01-31' }).allBalance, 50000000n);
});

test('TSV paste retains empty cells across 50 rows and selected bulk fill does not touch unselected rows', () => {
  const w=createWorkbench();
  const lines=Array.from({length:50},(_,i)=>`2026-02-11\tDEMO-${i}\t\t\t\t\t\t\t\t\t`);
  const rows=w.paste('2026-02',lines.join('\n'));
  assert.equal(rows.length,50);
  assert.equal(rows[0].carrier,'');
  assert.equal(rows[0].approvedTotal,'');
  w.fillSelected('2026-02',[rows[0].id,rows[2].id],{price:'1200000',otherFee:'50000'});
  assert.equal(rows[0].price,'1200000');
  assert.equal(rows[1].price,'');
  assert.equal(rows[2].otherFee,'50000');
  assert.equal(w.snapshot().months[1].balance,30000000n);
});

test('invalid draft remains editable with errors; duplicate warns but does not merge; pending price never posts', () => {
  const w=createWorkbench();
  const rows=w.paste('2026-02','2026-02-06\tDEMO-102\t\t\t\t\t\t\t\t\t\nnot-a-date\tDEMO-X\t\t\t\t\t\t\t\t\t');
  assert.equal(w.saveShipments('2026-02').ok,false);
  assert.equal(w.snapshot().months[1].drafts.length,2);
  assert.ok(rows[0].warnings.some(x=>x.includes('Trùng')));
  assert.ok(rows[1].errors.some(x=>x.includes('ngày')));
  w.updateDraft('2026-02',rows[1].id,{date:'2026-02-12'});
  assert.equal(w.saveShipments('2026-02').ok,true);
  assert.equal(w.snapshot().months[1].balance,30000000n);
  assert.equal(w.snapshot().months[1].waitingPrice,3);
});

test('approved total is explicit and fee mismatch blocks posting; no automatic fee sum', () => {
  const w=createWorkbench();
  const [row]=w.paste('2026-03','2026-03-04\tDEMO-X\t\t\t\t\t\t2000000\t100000\t\t2000000');
  assert.equal(w.saveShipments('2026-03').ok,false);
  assert.ok(row.errors.some(x=>x.includes('tổng')));
  assert.equal(w.snapshot().allBalance,95000000n);
});

test('receipt saves pending allocation oldest-first without touching posted balance', () => {
  const w=createWorkbench();
  const preview=w.planReceipt('60000000','2026-03-20');
  assert.deepEqual(preview.allocations.map(a=>[a.period,a.amount]),[['2026-01',40000000n],['2026-02',20000000n]]);
  const input={date:'2026-03-20',amount:'60000000',unconfirmed:true,requestId:'demo-r1'};
  assert.equal(w.saveReceipt(input).ok,true);
  assert.equal(w.snapshot().allBalance,95000000n);
  assert.equal(w.snapshot({asOf:'2026-03-19'}).allBalance,95000000n);
  assert.equal(w.snapshot({period:'2026-01'}).months[0].payments.at(-1).date,'2026-03-20');
  assert.equal(w.snapshot({period:'2026-01'}).months[0].payments.at(-1).period,'2026-01');
  assert.equal(w.snapshot({period:'2026-01'}).months[0].payments.at(-1).status,'pending');
  assert.equal(w.saveReceipt(input).duplicate,true);
  assert.equal(w.snapshot().allBalance,95000000n);
});

test('15-row paste preserves trailing blanks and divergent repeat request cannot double debit', () => {
  const w=createWorkbench();
  const rows=w.paste('2026-03',Array.from({length:15},(_,i)=>`2026-03-05\tTEST-${i}\t\t`).join('\n'));
  assert.equal(rows.length,15);
  assert.equal(rows[14].carrier,'');
  assert.equal(rows[14].price,'');
  const input={date:'2026-04-01',amount:'10000000',confirmed:true,requestId:'repeat-1'};
  assert.equal(w.saveReceipt(input).ok,true);
  assert.equal(w.saveReceipt({...input,amount:'20000000'}).ok,false);
  assert.equal(w.snapshot().allBalance,95000000n);
});

test('overpayment proposal targets selected period but cannot alter balance before approval', () => {
  const w=createWorkbench();
  const pending=w.saveReceipt({date:'2026-04-01',amount:'110000000',requestId:'overpay',overpayPeriod:'2026-03'});
  assert.equal(pending.ok,true);
  assert.deepEqual(pending.receipt.overpayment,{period:'2026-03',amount:15000000n});
  assert.equal(w.snapshot().allBalance,95000000n);
});

test('overpayment stays unallocated and an invalid receipt is rejected without losing entered fields', () => {
  const w=createWorkbench();
  const plan=w.planReceipt('110000000','2026-04-01');
  assert.equal(plan.unallocated,15000000n);
  const failed=w.saveReceipt({date:'2026-02-30',amount:'123',confirmed:true,requestId:'x'});
  assert.equal(failed.ok,false);
  assert.equal(failed.input.amount,'123');
  assert.equal(w.snapshot().allBalance,95000000n);
});
