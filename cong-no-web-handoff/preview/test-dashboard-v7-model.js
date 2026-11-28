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

test('tierLabels names each due tier with a short tile label and its debt months, across a year boundary', () => {
  assert.deepEqual(M.tierLabels('2026-10-29', rule).map(t => [t.label, t.tile, t.span]), [
    ['Chưa đến hạn', 'Chưa đến hạn', 'nợ T10'], ['Đến hạn 31/10', 'Hạn 31/10', 'nợ T9'], ['Quá hạn 1–2 tháng', '1–2 tháng', 'nợ T7–T8'],
    ['Quá hạn 3–6 tháng', '3–6 tháng', 'nợ T3–T6'], ['Quá hạn trên 6 tháng', '> 6 tháng', 'nợ T2 trở về trước']]);
  assert.deepEqual(M.tierLabels('2027-02-10', rule).map(t => t.span), [
    'nợ T2', 'nợ T1', 'nợ T11/2026–T12/2026', 'nợ T7/2026–T10/2026', 'nợ T6/2026 trở về trước']);
  assert.equal(M.tierLabels('2026-02-03', rule)[1].tile, 'Hạn 28/2');
});

test('tierOfMonth matches the server rule: due end of next month', () => {
  assert.deepEqual(['2026-10-01', '2026-09-01', '2026-08-01', '2026-07-01', '2026-06-01', '2026-03-01', '2026-02-01', '2025-12-01']
    .map(month => M.tierOfMonth(month, '2026-10-29', rule)), [0, 1, 2, 2, 3, 3, 4, 4]);
  assert.equal(M.tierOfMonth('2026-11-01', '2026-10-29', rule), 0);
});

test('debtors keep server money as BigInt, the server risk level and the commodity of each customer', () => {
  const rows = M.debtors(debt);
  assert.deepEqual(rows.map(r => [r.id, r.total, r.overdue, r.risk, r.com]), [
    [1, 400n, 300n, 'high', 'Sầu riêng cảng'],
    [2, 400n, 400n, 'high', 'Chuối'],
    [3, 500n, 400n, 'watch', M.UNSORTED],
    [4, 300n, 0n, 'ok', 'Mít']]);
  assert.equal(M.totalsMatch(rows, debt), true);
  assert.equal(M.totalsMatch(rows, { ...debt, receivable_vnd: '1601' }), false);
  assert.equal(M.totalsMatch(rows, { ...debt, due_tiers: debt.due_tiers.map(t => (t.tier === 'late_3_6' ? { ...t, receivable_vnd: '399' } : t)) }), false);
});

test('reason lines say why: risk signals first, otherwise which month is late and the last payment; customers without overdue are "Không quá hạn"', () => {
  const rows = M.debtors(debt);
  assert.equal(rows[0].why, 'Nợ từ T12/2025 · vẫn đi hàng');
  assert.equal(rows[1].why, 'Nợ từ T5/2026 · 7 tháng chưa trả · ngừng đi hàng');
  assert.equal(rows[2].why, 'Nợ T8/2026 quá hạn · có trả khoảng T9/2026');
  assert.equal(rows[3].why, 'Không quá hạn · chưa trả lần nào');
  assert.deepEqual(M.RISK, { high: 'Rủi ro cao', watch: 'Theo dõi', ok: 'Không quá hạn' });
});

test('risks: three chips count every debtor once and sum overdue per level; they match the server summary', () => {
  const rows = M.debtors(debt);
  const rk = M.risks(rows);
  assert.deepEqual(rk.groups.map(g => [g.key, g.label, g.count, g.overdue]), [
    ['high', 'Rủi ro cao', 2, 700n], ['watch', 'Theo dõi', 1, 400n], ['ok', 'Không quá hạn', 1, 0n]]);
  assert.equal(rk.groups.reduce((n, g) => n + g.count, 0), rows.length);
  assert.deepEqual(rk.credit, { count: 0, overdue: 0n });
  assert.equal(M.riskMatches(rk, debt.summary), true);
  assert.equal(M.riskMatches(rk, { ...debt.summary, high_customers: 3 }), false);
  assert.equal(M.riskMatches(rk, { ...debt.summary, high_overdue_vnd: '699' }), false);
  assert.equal(M.riskMatches(rk, { ...debt.summary, overdue_customers: 4 }), false);
  assert.equal(M.riskMatches(rk, { ...debt.summary, overdue_vnd: '1101' }), false);
  assert.equal(M.riskMatches(null, debt.summary), false);
});

test('risks: khách quá hạn âm (dư ở nợ cũ) là Không quá hạn; phần âm cộng vào chip đó nên ba chip vẫn bằng summary', () => {
  // Khách F: dư 50 ở nợ 3–6 tháng, còn nợ mới 250 → quá hạn −50, còn nợ 200; server cộng −50 vào overdue_vnd.
  const withCredit = { ...debt, receivable_vnd: '1800',
    due_tiers: debt.due_tiers.map(t => (t.tier === 'not_due' ? { ...t, receivable_vnd: '550' } : t.tier === 'late_3_6' ? { ...t, receivable_vnd: '350' } : t)),
    summary: { ...debt.summary, overdue_vnd: '1050' },
    customers: [...debt.customers, customer(6, 'Khách F', ['250', '0', '0', '-50', '0'], { risk: 'ok' })] };
  const rows = M.debtors(withCredit);
  assert.equal(M.totalsMatch(rows, withCredit), true);
  const rk = M.risks(rows);
  assert.deepEqual(rk.groups.map(g => [g.count, g.overdue]), [[2, 700n], [1, 400n], [2, -50n]]);
  assert.deepEqual(rk.credit, { count: 1, overdue: -50n });
  assert.equal(M.riskMatches(rk, withCredit.summary), true);
  assert.equal(M.riskMatches(rk, { ...withCredit.summary, overdue_vnd: '1100' }), false);
});

test('commodities: under 1% folds into Khác, unsorted last, bigger first', () => {
  const big = { ...debt, receivable_vnd: '100000',
    customers: [...debt.customers, customer(5, 'Khách E', ['98400', '0', '0', '0', '0'], { commodity: 'Dừa' })] };
  big.due_tiers = big.due_tiers.map(t => (t.tier === 'not_due' ? { ...t, receivable_vnd: '98700' } : t));
  const coms = M.commodities(M.debtors(big));
  assert.deepEqual(coms.map(g => [g.key, g.count, g.total, g.tone]), [['Dừa', 1, 98400n, ''], [M.OTHER, 3, 1100n, 'grey'], [M.UNSORTED, 1, 500n, 'grey']]);
  assert.deepEqual(M.commodities(M.debtors(debt)).map(g => g.key), ['Chuối', 'Sầu riêng cảng', 'Mít', M.UNSORTED]);
  // DASH-07: "Khác" kể tên các mặt hàng đã gộp (chú thích dòng); nhóm khác không có danh sách.
  const other = coms.find(g => g.key === M.OTHER);
  const names = M.debtors(big).filter(row => row.com === M.OTHER).map(row => F.commodityText(row.commodity, row.transportMode));
  assert.deepEqual(other.members, [...new Set(names)].sort((a, b) => a.localeCompare(b, 'vi')));
  assert.equal(other.members.length, 3);
  assert.deepEqual(coms.find(g => g.key === 'Dừa').members, []);
});

test('commodities: late is the positive overdue, so a credit in old debt never makes the bar longer than the total', () => {
  const credit = { ...debt, customers: [customer(1, 'Khách A', ['500', '0', '0', '-50', '0'], { commodity: 'Mít' }),
    customer(2, 'Khách B', ['100', '0', '300', '0', '0'], { commodity: 'Chuối' })] };
  const coms = M.commodities(M.debtors(credit));
  assert.deepEqual(coms.map(g => [g.key, g.total, g.overdue, g.late]), [['Mít', 450n, -50n, 0n], ['Chuối', 400n, 300n, 300n]]);
});

test('lọc chéo (DASH-08): scope bỏ chiều của chính khối; totals/riskView/comView tính lại trong phạm vi', () => {
  const rows = M.debtors(debt);
  const f = { tier: 3, risk: 'high', com: 'Chuối' };
  // Khách A: Sầu riêng cảng, rủi ro cao, có nợ trên 6 tháng nhưng không có nợ 3–6 tháng; Khách B: Chuối, rủi ro cao, 3–6 tháng.
  assert.deepEqual(M.scope(rows, f).map(row => row.id), [2]);
  assert.deepEqual(M.scope(rows, f, 'com').map(row => row.id), [2]);
  assert.deepEqual(M.scope(rows, { ...f, tier: null }, 'com').map(row => row.id).sort(), [1, 2]);
  assert.equal(M.scope(rows, f, 'tier').length, M.scope(rows, { com: 'Chuối', risk: 'high' }).length);
  // Không lọc gì: totals = tổng server.
  const all = M.totals(M.scope(rows, {}));
  assert.equal(all.total, 1600n);
  assert.deepEqual(all.tiers, [300n, 200n, 600n, 400n, 100n]);
  assert.equal(all.overdue, 1100n);
  // Chip trong nhóm 3–6 tháng: tiền là tiền nhóm đó.
  assert.deepEqual(M.riskView(M.scope(rows, { tier: 3 }, 'risk'), 3).map(g => [g.key, g.count, g.amount]),
    [['high', 1, 400n], ['watch', 0, 0n], ['ok', 0, 0n]]);
  assert.deepEqual(M.riskView(rows).map(g => g.amount), M.risks(rows).groups.map(g => g.overdue));
  // Khối mặt hàng giữ thứ tự nhóm; nhóm không còn khách là 0; lọc nhóm chưa quá hạn thì không có phần quá hạn.
  const coms = M.commodities(rows);
  const notDue = M.comView(M.scope(rows, { tier: 0 }, 'com'), coms, 0);
  assert.deepEqual(notDue.map(g => g.key), coms.map(g => g.key));
  assert.ok(notDue.every(g => g.late === 0n));
  assert.equal(F.sum(notDue.map(g => g.total)), 300n);
  const late = M.comView(M.scope(rows, { tier: 3 }, 'com'), coms, 3);
  assert.deepEqual(late.filter(g => g.count).map(g => [g.key, g.total, g.late]), [['Chuối', 400n, 400n]]);
});

test('monthFlow (DASH-08): cộng sổ trong phạm vi; sổ hết nợ chỉ khớp lọc mặt hàng; API cũ hay không lọc thì null', () => {
  const rows = M.debtors(debt);
  const coms = M.commodities(rows);
  const book = (id, commodity, mode, charges, received) => ({ customer_id: id, commodity, transport_mode: mode, charges_vnd: charges, received_vnd: received });
  const month = { charges_vnd: '0', received_vnd: '0', customers: [book(1, 'Sầu riêng', 'CANG', '10', '1'), book(2, 'Chuối', null, '20', '2'),
    book(8, 'Chuối', null, '30', '3'), book(9, 'Bơ', null, '40', '4'), book(10, null, null, '50', '5')] };
  assert.equal(M.monthFlow({ charges_vnd: '1', received_vnd: '1' }, rows, coms, { com: 'Chuối' }), null);
  assert.equal(M.monthFlow(month, rows, coms, {}), null);
  const pick = filter => { const f = M.monthFlow(month, rows, coms, filter); return [f.charges_vnd, f.received_vnd, f.books]; };
  assert.deepEqual(pick({ com: 'Chuối' }), [50n, 5n, 2]);
  assert.deepEqual(pick({ com: M.UNSORTED }), [50n, 5n, 1]);
  assert.deepEqual(pick({ risk: 'high' }), [30n, 3n, 2]);
  assert.deepEqual(pick({ tier: 3, com: 'Chuối' }), [20n, 2n, 1]);
  // Mặt hàng không có sổ đang nợ (Bơ) không có dòng riêng: chỉ khớp "Khác".
  assert.deepEqual(pick({ com: 'Bơ' }), [0n, 0n, 0]);
});

test('monthProgress: received over charges, today and days left in the month; charges 0 has no ratio; over 100% caps the fill', () => {
  const p = M.monthProgress('2026-10-29', { charges_vnd: '700000000', received_vnd: '186000000' });
  assert.deepEqual([p.month, p.day, p.days, p.left, p.dayPct, p.fill, p.percent], [10, 29, 31, 2, 94, 26.6, '26,6%']);
  const none = M.monthProgress('2026-02-01', { charges_vnd: '0', received_vnd: '5' });
  assert.deepEqual([none.days, none.left, none.dayPct, none.fill, none.percent, none.received], [28, 27, 4, 0, null, 5n]);
  const over = M.monthProgress('2026-10-31', { charges_vnd: '100', received_vnd: '250' });
  assert.deepEqual([over.left, over.dayPct, over.fill, over.percent], [0, 100, 100, '250%']);
  assert.deepEqual(M.monthProgress('2026-10-29', undefined).charges, 0n);
});

test('dayCell (KHACH-THANG-02): "… trước", tới 90 ngày đếm ngày rồi đếm tháng; sắc thái theo ngưỡng; null là "chưa có", không phải 0', () => {
  assert.deepEqual(M.dayCell(27, 60, 30), { text: '27 ngày trước', tone: '' });
  assert.deepEqual(M.dayCell(30, 60, 30), { text: '30 ngày trước', tone: '' });
  assert.deepEqual(M.dayCell(45, 60, 30), { text: '45 ngày trước', tone: 'warn' });
  assert.deepEqual(M.dayCell(61, 60, 30), { text: '61 ngày trước', tone: 'bad' });
  assert.deepEqual(M.dayCell(90, 90, 30), { text: '90 ngày trước', tone: 'warn' });
  assert.deepEqual(M.dayCell(963, 90, 30), { text: '32 tháng trước', tone: 'bad' });
  assert.deepEqual(M.dayCell(null, 90, 30), { text: 'chưa có', tone: 'bad' });
  assert.deepEqual(M.dayCell(0, 90, 30), { text: 'hôm nay', tone: '' });
});

test('filterRows filters by due tier, risk level and commodity; sorts by first column, total, or days with null first', () => {
  const rows = M.debtors(debt);
  assert.deepEqual(M.filterRows(rows).map(x => [x.row.id, x.first]), [[3, 400n], [2, 400n], [1, 300n], [4, 0n]]);
  assert.deepEqual(M.filterRows(rows, { sort: 'total' }).map(x => x.row.id), [3, 2, 1, 4]);
  assert.deepEqual(M.filterRows(rows, { tier: 2 }).map(x => [x.row.id, x.first]), [[3, 400n], [1, 200n]]);
  assert.deepEqual(M.filterRows(rows, { tier: 2, risk: 'high' }).map(x => x.row.id), [1]);
  assert.deepEqual(M.filterRows(rows, { risk: 'high' }).map(x => x.row.id), [2, 1]);
  assert.deepEqual(M.filterRows(rows, { risk: 'ok' }).map(x => x.row.id), [4]);
  assert.deepEqual(M.filterRows(rows, { risk: 'high', com: 'Chuối' }).map(x => x.row.id), [2]);
  assert.deepEqual(M.filterRows(rows, { com: M.UNSORTED }).map(x => x.row.id), [3]);
  assert.deepEqual(M.filterRows(rows, { sort: 'pay' }).map(x => x.row.id), [4, 2, 3, 1]);
  assert.deepEqual(M.filterRows(rows, { sort: 'trip' }).map(x => x.row.id), [2, 3, 4, 1]);
  assert.equal(M.commodityKey('Sầu riêng', 'BỘ'), 'Sầu riêng bộ');
  assert.equal(M.commodityKey('Sầu riêng', null), M.UNSORTED);
});

test('newCustomer (KHACH-MOI-01): câu dữ kiện của sổ mới theo cờ; không mới hoặc API cũ thì null', () => {
  const at = '2026-11-19';
  assert.equal(F.newCustomer({ is_new: false, first_trip_day: '2026-10-01' }, at), null);
  assert.equal(F.newCustomer({ risk: 'ok' }, at), null);
  assert.deepEqual(F.newCustomer({ is_new: true, first_trip_day: '2026-09-30', first_trip_exact: true, new_flag: 'no_pay',
    oldest_unpaid_trip_day: '2026-09-30' }, at), { flag: 'no_pay', text: 'Chưa trả lần nào · chuyến đầu 50 ngày trước',
    brief: 'chưa trả lần nào', first: '30/09/2026' });
  assert.deepEqual(F.newCustomer({ is_new: true, first_trip_day: '2026-09-10', first_trip_exact: true, new_flag: 'slow',
    oldest_unpaid_trip_day: '2026-10-02' }, at), { flag: 'slow', text: 'Chuyến 02/10 chưa trả đủ · 48 ngày',
    brief: 'chuyến 02/10 chưa trả đủ · 48 ngày', first: '10/09/2026' });
  assert.deepEqual(F.newCustomer({ is_new: true, first_trip_day: '2026-10-31', first_trip_exact: false, new_flag: null,
    oldest_unpaid_trip_day: '2026-10-31' }, at), { flag: null, text: 'Khách mới · chuyến đầu 19 ngày trước', brief: '', first: 'khoảng T10/2026' });
});

test('lọc khách mới (KHACH-MOI-01): scope/filterRows/monthFlow giữ mọi sổ mới, sổ cần để ý lên đầu; skip "fresh" bỏ chiều này', () => {
  const fresh = { ...debt, customers: debt.customers.map(item => (item.customer_id === 3
    ? { ...item, is_new: true, first_trip_day: '2026-09-01', first_trip_exact: true, new_flag: 'slow', oldest_unpaid_trip_day: '2026-09-05' }
    : item.customer_id === 4 ? { ...item, is_new: true, first_trip_day: '2026-10-20', first_trip_exact: true, new_flag: null } : item)),
  this_month: { ...debt.this_month, customers: [{ customer_id: 3, charges_vnd: '7', received_vnd: '2' },
    { customer_id: 4, charges_vnd: '5', received_vnd: '0' }, { customer_id: 9, charges_vnd: '1', received_vnd: '1' }] } };
  const rows = M.debtors(fresh);
  assert.deepEqual(rows.filter(M.watchNew).map(r => r.id), [3]);
  assert.deepEqual(rows.filter(M.isNew).map(r => r.id), [3, 4]);
  assert.equal(rows.find(r => r.id === 4).fresh.flag, null);
  assert.equal(rows.find(r => r.id === 1).fresh, null);
  assert.deepEqual(M.scope(rows, { fresh: true }).map(r => r.id), [3, 4]);
  assert.deepEqual(M.scope(rows, { fresh: true, risk: 'high' }).map(r => r.id), []);
  assert.deepEqual(M.scope(rows, { fresh: true, risk: 'watch' }, 'fresh').map(r => r.id), [3]);
  // Sổ cần để ý lên đầu dù cột xếp đặt sổ khác trước: xếp "Trả" thì 4 (chưa trả lần nào) đứng trước 3, trừ khi đang lọc khách mới.
  assert.deepEqual(M.filterRows(rows, { fresh: true }).map(item => item.row.id), [3, 4]);
  assert.deepEqual(M.filterRows(rows, { sort: 'pay' }).map(item => item.row.id).filter(id => id > 2), [4, 3]);
  assert.deepEqual(M.filterRows(rows, { fresh: true, sort: 'pay' }).map(item => item.row.id), [3, 4]);
  const flow = M.monthFlow(fresh.this_month, rows, M.commodities(rows), { fresh: true });
  assert.deepEqual([flow.charges_vnd, flow.received_vnd, flow.books], [12n, 2n, 2]);
});

// KHACH-THANG-01 (28/11/2026): tháng là một chiều lọc như hạn trả, mức rủi ro, mặt hàng.
test('scope lọc theo tập sổ của tháng; skip month bỏ chiều đó; null là không lọc tháng', () => {
  const rows = M.debtors(debt);
  const month = new Set([2, 4, 9]);
  assert.deepEqual(M.scope(rows, { month }).map(r => r.id), [2, 4]);
  assert.deepEqual(M.scope(rows, { month, risk: 'high' }).map(r => r.id), [2]);
  assert.deepEqual(M.scope(rows, { month }, 'month').map(r => r.id), [1, 2, 3, 4]);
  assert.deepEqual(M.scope(rows, { month: null }).map(r => r.id), [1, 2, 3, 4]);
});

// KHACH-THANG-02: dòng của GET /api/v7/month-customers có nợ đầu tháng và còn nợ cuối tháng (máy chủ tính như thanh tháng của sổ).
const book = (id, prior, charges, received, end) => ({ customer_id: id, prior_months_vnd: prior, charges_vnd: charges, received_vnd: received,
  end_of_month_vnd: end, outstanding_vnd: '0' });

test('monthRows gắn sổ tháng (đầu + phát sinh − đã thu = cuối); sổ đã hết nợ có dòng còn nợ 0, không mức rủi ro, mặt hàng lấy từ danh sách sổ', () => {
  const rows = M.debtors(debt);
  const coms = M.commodities(rows);
  const books = [book(2, '350', '50', '0', '400'), book(9, '30', '70', '100', '0'), book(8, '0', '10', '0', '10')];
  const list = [{ id: 9, name: 'Khách P', commodity: 'Chuối' }, { id: 8, name: 'Khách Q', commodity: 'Dừa' }];
  const out = M.monthRows(rows, books, list, coms);
  assert.deepEqual(out.map(r => [r.id, r.mon.prior, r.mon.charges, r.mon.received, r.mon.end, r.total, r.risk, r.com, Boolean(r.paid)]), [
    [2, 350n, 50n, 0n, 400n, 400n, 'high', 'Chuối', false],
    [9, 30n, 70n, 100n, 0n, 0n, null, 'Chuối', true],
    [8, 0n, 10n, 0n, 10n, 0n, null, M.OTHER, true]]);
  // Máy chủ cũ (chưa có nợ đầu/cuối tháng): hai số là null, không đoán thành 0.
  const old = M.monthRows(rows, [{ customer_id: 2, charges_vnd: '50', received_vnd: '0', outstanding_vnd: '50' }], list, coms);
  assert.deepEqual([old[0].mon.prior, old[0].mon.end], [null, null]);
  // Lọc mặt hàng vẫn khớp sổ đã hết nợ; lọc mức rủi ro hay hạn trả bỏ chúng.
  const ids = new Set(books.map(b => b.customer_id));
  assert.deepEqual(M.filterRows(out, { month: ids, com: 'Chuối', sort: 'charges' }).map(x => x.row.id), [9, 2]);
  assert.deepEqual(M.filterRows(out, { month: ids, risk: 'high' }).map(x => x.row.id), [2]);
  assert.deepEqual(M.filterRows(out, { month: ids, tier: 3 }).map(x => x.row.id), [2]);
  // Bốn cột tiền của tháng là bốn cách xếp, nhiều trước.
  assert.deepEqual(M.MONTH_SORTS, ['prior', 'charges', 'received', 'end']);
  assert.deepEqual(M.filterRows(out, { month: ids, sort: 'prior' }).map(x => x.row.id), [2, 9, 8]);
  assert.deepEqual(M.filterRows(out, { month: ids, sort: 'received' }).map(x => x.row.id), [9, 2, 8]);
  assert.deepEqual(M.filterRows(out, { month: ids, sort: 'end' }).map(x => x.row.id), [2, 8, 9]);
});

test('monthProgress của tháng đã qua: xem như ngày cuối tháng, cờ past; tháng hiện tại giữ như cũ', () => {
  const past = M.monthProgress('2026-10-29', { charges_vnd: '100', received_vnd: '40' }, '2026-02');
  assert.deepEqual([past.past, past.month, past.day, past.days, past.left, past.percent], [true, 2, 28, 28, 0, F.percent(40n, 100n)]);
  const now = M.monthProgress('2026-10-29', { charges_vnd: '100', received_vnd: '40' }, '2026-10');
  assert.deepEqual([now.past, now.day, now.left], [undefined, 29, 2]);
});
