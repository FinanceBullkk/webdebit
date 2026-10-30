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

test('debtors keep server money as BigInt and add the matrix cell and commodity of each customer', () => {
  const rows = M.debtors(debt);
  assert.deepEqual(rows.map(r => [r.id, r.total, r.overdue, r.mx, r.com]), [
    [1, 400n, 300n, 'p0t0', 'Sầu riêng cảng'],
    [2, 400n, 400n, 'p1t1', 'Chuối'],
    [3, 500n, 400n, 'p0t0', M.UNSORTED],
    [4, 300n, 0n, 'p1t0', 'Mít']]);
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

test('matrix splits only overdue customers by pay × trip thresholds; null days count as the bad side; totals match', () => {
  const rows = M.debtors(debt);
  const mx = M.matrix(rows, rule);
  assert.deepEqual(mx.cols, ['Có trả trong 60 ngày', 'Trên 60 ngày chưa trả']);
  assert.deepEqual(mx.lines, ['Còn đi hàng', 'Ngừng đi hàng > 90 ngày']);
  // Khách D chưa trả lần nào nhưng không có nợ quá hạn: không vào ma trận.
  assert.deepEqual(mx.cells.map(c => [c.key, c.bad, c.count, c.overdue, c.total]), [
    ['p0t0', 0, 2, 700n, 900n], ['p1t0', 1, 0, 0n, 0n], ['p0t1', 1, 0, 0n, 0n], ['p1t1', 2, 1, 400n, 400n]]);
  assert.equal(mx.cells[3].label, 'Trên 60 ngày chưa trả · ngừng đi hàng > 90 ngày');
  assert.equal(mx.count, 3);
  assert.equal(mx.overdue, F.toBig(debt.summary.overdue_vnd));
  assert.equal(F.sum(mx.cells.map(c => c.overdue)), mx.overdue);
});

test('matrixMatches: matrix totals must equal summary (server sums negative overdue too)', () => {
  const mx = M.matrix(M.debtors(debt), rule);
  assert.equal(M.matrixMatches(mx, debt.summary), true);
  assert.equal(M.matrixMatches(mx, { ...debt.summary, overdue_vnd: String(F.toBig(debt.summary.overdue_vnd) - 100n) }), false);
  assert.equal(M.matrixMatches(mx, { ...debt.summary, overdue_customers: debt.summary.overdue_customers + 1 }), false);
  assert.equal(M.matrixMatches(null, debt.summary), false);
});

test('commodities: under 1% folds into Khác, unsorted last, bigger first', () => {
  const big = { ...debt, receivable_vnd: '100000',
    customers: [...debt.customers, customer(5, 'Khách E', ['98400', '0', '0', '0', '0'], { commodity: 'Dừa' })] };
  big.due_tiers = big.due_tiers.map(t => (t.tier === 'not_due' ? { ...t, receivable_vnd: '98700' } : t));
  const coms = M.commodities(M.debtors(big));
  assert.deepEqual(coms.map(g => [g.key, g.count, g.total, g.tone]), [['Dừa', 1, 98400n, ''], [M.OTHER, 3, 1100n, 'grey'], [M.UNSORTED, 1, 500n, 'grey']]);
  assert.deepEqual(M.commodities(M.debtors(debt)).map(g => g.key), ['Chuối', 'Sầu riêng cảng', 'Mít', M.UNSORTED]);
});

test('monthProgress: received over charges, today within the month; charges 0 has no ratio; over 100% caps the fill', () => {
  const p = M.monthProgress('2026-10-29', { charges_vnd: '700000000', received_vnd: '186000000' });
  assert.deepEqual([p.month, p.day, p.days, p.dayPct, p.fill, p.percent], [10, 29, 31, 94, 26.6, '26,6%']);
  const none = M.monthProgress('2026-02-01', { charges_vnd: '0', received_vnd: '5' });
  assert.deepEqual([none.days, none.dayPct, none.fill, none.percent, none.received], [28, 4, 0, null, 5n]);
  const over = M.monthProgress('2026-10-31', { charges_vnd: '100', received_vnd: '250' });
  assert.deepEqual([over.dayPct, over.fill, over.percent], [100, 100, '250%']);
  assert.deepEqual(M.monthProgress('2026-10-29', undefined).charges, 0n);
});

test('dayCell: short text and tone by threshold; null is "chưa …", never 0', () => {
  assert.deepEqual(M.dayCell(27, 60, 30, 'chưa trả'), { text: '27 ngày', tone: '' });
  assert.deepEqual(M.dayCell(45, 60, 30, 'chưa trả'), { text: '45 ngày', tone: 'warn' });
  assert.deepEqual(M.dayCell(92, 60, 30, 'chưa trả'), { text: '3 tháng', tone: 'bad' });
  assert.deepEqual(M.dayCell(61, 60, 30, 'chưa trả'), { text: '61 ngày', tone: 'bad' });
  assert.deepEqual(M.dayCell(null, 90, 30, 'chưa có'), { text: 'chưa có', tone: 'bad' });
  assert.deepEqual(M.dayCell(0, 90, 30, 'chưa có'), { text: '0 ngày', tone: '' });
});

test('filterRows filters by due tier, matrix cell and commodity; sorts by first column, total, or days with null first', () => {
  const rows = M.debtors(debt);
  assert.deepEqual(M.filterRows(rows).map(x => [x.row.id, x.first]), [[3, 400n], [2, 400n], [1, 300n], [4, 0n]]);
  assert.deepEqual(M.filterRows(rows, { sort: 'total' }).map(x => x.row.id), [3, 2, 1, 4]);
  assert.deepEqual(M.filterRows(rows, { tier: 2 }).map(x => [x.row.id, x.first]), [[3, 400n], [1, 200n]]);
  assert.deepEqual(M.filterRows(rows, { tier: 2, cls: { dim: 'mx', key: 'p0t0' } }).map(x => x.row.id), [3, 1]);
  assert.deepEqual(M.filterRows(rows, { cls: { dim: 'mx', key: 'p1t1' } }).map(x => x.row.id), [2]);
  // Khách D nằm ở p1t0 theo ngày nhưng không có nợ quá hạn: ô ma trận không lọc ra.
  assert.deepEqual(M.filterRows(rows, { cls: { dim: 'mx', key: 'p1t0' } }).map(x => x.row.id), []);
  assert.deepEqual(M.filterRows(rows, { com: M.UNSORTED }).map(x => x.row.id), [3]);
  assert.deepEqual(M.filterRows(rows, { sort: 'pay' }).map(x => x.row.id), [4, 2, 3, 1]);
  assert.deepEqual(M.filterRows(rows, { sort: 'trip' }).map(x => x.row.id), [2, 3, 4, 1]);
  assert.equal(M.commodityKey('Sầu riêng', 'BỘ'), 'Sầu riêng bộ');
  assert.equal(M.commodityKey('Sầu riêng', null), M.UNSORTED);
});
