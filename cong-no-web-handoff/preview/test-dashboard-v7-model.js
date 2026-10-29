const { test } = require('node:test');
const assert = require('node:assert/strict');
const M = require('./dashboard-v7-model.js');
const F = require('./cong-no-format.js');

const rule = { due_after_months: 1, long_overdue_months: 3, no_pay_days: 60, no_trip_days: 90, active_trip_days: 30 };
const customer = (id, name, tiers, extra = {}) => {
  const total = tiers.reduce((sum, value) => sum + BigInt(value), 0n);
  const overdue = tiers.slice(2).reduce((sum, value) => sum + BigInt(value), 0n);
  const long = tiers.slice(3).reduce((sum, value) => sum + BigInt(value), 0n);
  return { customer_id: id, name, commodity: null, transport_mode: null, outstanding_vnd: String(total), tiers_vnd: tiers,
    overdue_vnd: String(overdue), long_overdue_vnd: String(long), oldest_open_month: null, last_receipt_date: null,
    last_receipt_exact: null, pay_days: null, last_trip_date: null, last_trip_exact: null, trip_days: null,
    risk: overdue > 0n ? 'watch' : 'ok', months: [], ...extra };
};
const debt = {
  as_of: '2026-10-29', month: '2026-10-01', rule, receivable_vnd: '1600',
  due_tiers: [['not_due', '300'], ['due_this_month', '200'], ['late_1_2', '600'], ['late_3_6', '400'], ['late_over_6', '100']]
    .map(([tier, value]) => ({ tier, receivable_vnd: value })),
  summary: { overdue_vnd: '1100', long_overdue_vnd: '500', overdue_customers: 3, high_customers: 2, high_overdue_vnd: '700' },
  this_month: { month: '2026-10-01', charges_vnd: '0', received_vnd: '0' },
  customers: [
    customer(1, 'Khách A', ['100', '0', '200', '0', '100'], { risk: 'high', commodity: 'Sầu riêng', transport_mode: 'CANG',
      oldest_open_month: '2025-12-01', last_receipt_date: '2026-10-15', last_receipt_exact: true, pay_days: 14,
      last_trip_date: '2026-10-27', last_trip_exact: true, trip_days: 2,
      months: [{ month: '2025-12-01', outstanding_vnd: '100' }, { month: '2026-08-01', outstanding_vnd: '200' }, { month: '2026-10-01', outstanding_vnd: '100' }] }),
    customer(2, 'Khách B', ['0', '0', '0', '400', '0'], { risk: 'high', commodity: 'Chuối', oldest_open_month: '2026-05-01',
      last_receipt_date: '2026-04-02', last_receipt_exact: true, pay_days: 210, last_trip_date: '2026-03-31', last_trip_exact: false, trip_days: 212,
      months: [{ month: '2026-05-01', outstanding_vnd: '400' }] }),
    customer(3, 'Khách C', ['0', '100', '400', '0', '0'], { commodity: 'Sầu riêng', last_receipt_date: '2026-09-30', last_receipt_exact: false,
      pay_days: 29, last_trip_date: '2026-09-20', last_trip_exact: true, trip_days: 39, months: [{ month: '2026-08-01', outstanding_vnd: '400' }, { month: '2026-09-01', outstanding_vnd: '100' }] }),
    customer(4, 'Khách D', ['200', '100', '0', '0', '0'], { commodity: 'Mít', last_trip_date: '2026-10-20', last_trip_exact: true, trip_days: 9 }),
  ],
};

test('tierLabels names each due tier with its debt months, across a year boundary', () => {
  assert.deepEqual(M.tierLabels('2026-10-29', rule).map(t => [t.label, t.span]), [
    ['Chưa đến hạn', 'nợ T10'], ['Đến hạn 31/10', 'nợ T9'], ['Quá hạn 1–2 tháng', 'nợ T7–T8'],
    ['Quá hạn 3–6 tháng', 'nợ T3–T6'], ['Quá hạn trên 6 tháng', 'nợ T2 trở về trước']]);
  assert.deepEqual(M.tierLabels('2027-02-10', rule).map(t => t.span), [
    'nợ T2', 'nợ T1', 'nợ T11/2026–T12/2026', 'nợ T7/2026–T10/2026', 'nợ T6/2026 trở về trước']);
  assert.equal(M.tierLabels('2026-02-03', rule)[1].label, 'Đến hạn 28/2');
});

test('tierOfMonth matches the server rule: due end of next month', () => {
  assert.deepEqual(['2026-10-01', '2026-09-01', '2026-08-01', '2026-07-01', '2026-06-01', '2026-03-01', '2026-02-01', '2025-12-01']
    .map(month => M.tierOfMonth(month, '2026-10-29', rule)), [0, 1, 2, 2, 3, 3, 4, 4]);
  assert.equal(M.tierOfMonth('2026-11-01', '2026-10-29', rule), 0);
});

test('debtors keep server money as BigInt and add classes for every dimension', () => {
  const rows = M.debtors(debt);
  assert.deepEqual(rows.map(r => [r.id, r.total, r.overdue, r.pay, r.trip, r.size, r.com]), [
    [1, 400n, 300n, 'p30', 't30', 'top5', 'Sầu riêng cảng'],
    [2, 400n, 400n, 'p61', 't91', 'top5', 'Chuối'],
    [3, 500n, 400n, 'p30', 't90', 'top5', M.UNSORTED],
    [4, 300n, 0n, 'never', 't30', 'top5', 'Mít']]);
  assert.deepEqual(rows[0].months.map(m => [m.key, m.value, m.tier]), [['2025-12-01', 100n, 4], ['2026-08-01', 200n, 2], ['2026-10-01', 100n, 0]]);
  assert.equal(M.totalsMatch(rows, debt), true);
  assert.equal(M.totalsMatch(rows, { ...debt, receivable_vnd: '1601' }), false);
  assert.equal(M.totalsMatch(rows, { ...debt, due_tiers: debt.due_tiers.map(t => (t.tier === 'late_3_6' ? { ...t, receivable_vnd: '399' } : t)) }), false);
});

test('reason lines say why: risk signals first, otherwise which month is late and the last payment', () => {
  const rows = M.debtors(debt);
  assert.equal(rows[0].why, 'Nợ từ T12/2025 · vẫn đi hàng');
  assert.equal(rows[1].why, 'Nợ từ T5/2026 · 7 tháng chưa trả · ngừng đi hàng');
  assert.equal(rows[2].why, 'Nợ T8/2026 quá hạn · có trả khoảng T9/2026');
  assert.equal(rows[3].why, 'Trong hạn · chưa trả lần nào');
  assert.deepEqual(M.reasons(rows[1], rule), ['Còn 400 đ quá hạn từ 3 tháng trở lên (nợ từ tháng 5/2026)',
    'Trả gần nhất 02/04/2026 — 7 tháng trước', 'Đi hàng gần nhất trong tháng 3/2026 — đã ngừng đi hàng']);
  assert.deepEqual(M.reasons(rows[3], rule), ['Chưa có nợ quá hạn', 'Chưa trả lần nào', 'Đi hàng gần nhất 20/10/2026 — vẫn đi hàng']);
});

test('dimensions group customers; under 1% folds into Khác, unsorted last; empty groups dropped', () => {
  const big = { ...debt, receivable_vnd: '100000',
    customers: [...debt.customers, customer(5, 'Khách E', ['98400', '0', '0', '0', '0'], { commodity: 'Dừa' })] };
  big.due_tiers = big.due_tiers.map(t => (t.tier === 'not_due' ? { ...t, receivable_vnd: '98700' } : t));
  const rows = M.debtors(big);
  const dims = M.dimensions(rows, big.receivable_vnd);
  assert.deepEqual(dims.map(d => d.key), ['risk', 'pay', 'trip', 'size', 'com']);
  const com = dims.find(d => d.key === 'com');
  assert.deepEqual(com.groups.map(g => [g.key, g.count, g.total]), [['Dừa', 1, 98400n], [M.OTHER, 3, 1100n], [M.UNSORTED, 1, 500n]]);
  const risk = dims.find(d => d.key === 'risk');
  assert.deepEqual(risk.groups.map(g => [g.key, g.count, g.total, g.overdue]), [['high', 2, 800n, 700n], ['watch', 1, 500n, 400n], ['ok', 2, 98700n, 0n]]);
  assert.deepEqual(risk.lead(risk.groups), [['b', '2 khách rủi ro cao'], ' đang nợ ', ['b', '800 đ'], ', trong đó quá hạn 700 đ.']);
  const pay = dims.find(d => d.key === 'pay');
  assert.deepEqual(pay.groups.map(g => g.key), ['p30', 'p61', 'never']);
  assert.equal(F.sum(dims.find(d => d.key === 'size').groups.map(g => g.total)), 100000n);
});

test('filterRows filters by due tier and class, sorts by first column or by total', () => {
  const rows = M.debtors(debt);
  assert.deepEqual(M.filterRows(rows).map(x => [x.row.id, x.first]), [[3, 400n], [2, 400n], [1, 300n], [4, 0n]]);
  assert.deepEqual(M.filterRows(rows, { sort: 'total' }).map(x => x.row.id), [3, 2, 1, 4]);
  assert.deepEqual(M.filterRows(rows, { tier: 2 }).map(x => [x.row.id, x.first]), [[3, 400n], [1, 200n]]);
  assert.deepEqual(M.filterRows(rows, { tier: 2, cls: { dim: 'risk', key: 'high' } }).map(x => x.row.id), [1]);
  assert.deepEqual(M.filterRows(rows, { cls: { dim: 'trip', key: 't91' } }).map(x => x.row.id), [2]);
  assert.equal(M.commodityKey('Sầu riêng', 'BỘ'), 'Sầu riêng bộ');
  assert.equal(M.commodityKey('Sầu riêng', null), M.UNSORTED);
});
