const { test } = require('node:test');
const assert = require('node:assert/strict');
const F = require('./cong-no-format.js');
const M = require('./bang-thu-model.js');

// BANG-THU-02: dữ liệu giả cùng dạng GET /api/v7/receipt-book.
const web = (id, customer, date, amount, allocations) => ({ source: 'web', id, pid: `PH-${id}`, customer_id: customer, name: `SỔ ${customer}`, date,
  book_month: `${(date ?? '2026-10-31').slice(0, 7)}-01`, amount_vnd: amount, method: 'THU TIỀN', note: null, allocations });
const sheet = (id, customer, date, amount, block) => ({ source: 'sheet', id, pid: null, customer_id: customer, name: `SỔ ${customer}`, date,
  book_month: block, amount_vnd: amount, method: null, note: null, allocations: [] });
const debt = (month, amount) => ({ month, kind: 'debt', amount_vnd: amount });
const advance = (month, amount) => ({ month, kind: 'advance', amount_vnd: amount });

const customersFixture = [
  { id: 1, name: 'SỔ 1', commodity: 'Sầu riêng', transport_mode: 'CANG' },
  { id: 2, name: 'SỔ 2', commodity: 'Sầu riêng', transport_mode: 'BO' },
  { id: 3, name: 'SỔ 3', commodity: 'Chuối', transport_mode: null },
  { id: 4, name: 'SỔ 4', commodity: null, transport_mode: null },
  { id: 5, name: 'SỔ 5', commodity: 'Sầu riêng', transport_mode: null },
];
const coms = M.commodityMap(customersFixture);

const book = () => {
  const rows = {
    r30: web(1, 1, '2026-10-30', '420000000', [debt('2026-07-01', '300000000'), debt('2026-08-01', '120000000')]),
    r30b: web(2, 3, '2026-10-30', '180000000', [debt('2026-09-01', '180000000')]),
    r16: web(3, 2, '2026-10-16', '20700000', [debt('2026-09-01', '15000000'), advance('2026-09-01', '5700000')]),
    r14: sheet(4, 1, '2026-10-14', '112600000', '2026-09-01'),
    r09: sheet(5, 4, '2026-10-09', '5500000', '2026-03-01'),
    u1: sheet(6, 2, null, '39000000', '2026-10-01'),
    u2: sheet(7, 5, null, '30000000', '2026-10-01'),
  };
  return { month: '2026-10-01', as_of: '2026-10-30', today_month: '2026-10-01',
    months: [{ month: '2026-10-01', total_vnd: '738800000', count: 5, undated_vnd: '69000000', undated_count: 2 },
      { month: '2026-08-01', total_vnd: '100000000', count: 2, undated_vnd: '0', undated_count: 0 },
      { month: '2025-12-01', total_vnd: '200000000', count: 1, undated_vnd: '300000000', undated_count: 3 }],
    summary: { total_vnd: '738800000', count: 5, customers: 4, undated_vnd: '69000000', undated_count: 2, today_vnd: '600000000', today_count: 2, has_sheet: true },
    days: [
      { date: '2026-10-30', total_vnd: '600000000', count: 2, rows: [rows.r30, rows.r30b] },
      { date: '2026-10-16', total_vnd: '20700000', count: 1, rows: [rows.r16] },
      { date: '2026-10-14', total_vnd: '112600000', count: 1, rows: [rows.r14] },
      { date: '2026-10-09', total_vnd: '5500000', count: 1, rows: [rows.r09] },
    ],
    undated: [rows.u1, rows.u2],
    customers: [
      { customer_id: 1, name: 'SỔ 1', total_vnd: '532600000', count: 2, undated_vnd: '0', undated_count: 0, last_date: '2026-10-30', book_month: '2026-10-01' },
      { customer_id: 3, name: 'SỔ 3', total_vnd: '180000000', count: 1, undated_vnd: '0', undated_count: 0, last_date: '2026-10-30', book_month: '2026-10-01' },
      { customer_id: 2, name: 'SỔ 2', total_vnd: '20700000', count: 1, undated_vnd: '39000000', undated_count: 1, last_date: '2026-10-16', book_month: '2026-10-01' },
      { customer_id: 4, name: 'SỔ 4', total_vnd: '5500000', count: 1, undated_vnd: '0', undated_count: 0, last_date: '2026-10-09', book_month: '2026-03-01' },
      { customer_id: 5, name: 'SỔ 5', total_vnd: '0', count: 0, undated_vnd: '30000000', undated_count: 1, last_date: null, book_month: '2026-10-01' },
    ],
    offsets: [{ id: 1, date: '2026-10-20', amount_vnd: '5000000', source_customer_id: 1, source_name: 'SỔ 1', target_customer_id: 3, target_name: 'SỔ 3' }],
    voided: [{ pid: 'PH-9', customer_id: 4, name: 'SỔ 4', date: '2026-10-02', amount_vnd: '77000000', voided_on: '2026-10-03', void_reason: 'nhập trùng' }] };
};
const total = groups => F.sum(groups.map(group => group.total));
const undated = groups => F.sum(groups.map(group => group.undated));

test('Mặt hàng: cùng nhóm với bộ lọc Tổng quan, "Chưa phân loại" cuối danh sách', () => {
  assert.equal(coms.get('1'), 'Sầu riêng cảng');
  assert.equal(coms.get('2'), 'Sầu riêng bộ');
  assert.equal(coms.get('3'), 'Chuối');
  assert.equal(coms.get('4'), F.UNSORTED);
  assert.equal(coms.get('5'), F.UNSORTED, 'sầu riêng chưa ghi cảng/bộ');
  assert.deepEqual(M.commodityOptions(coms), ['Chuối', 'Sầu riêng bộ', 'Sầu riêng cảng', F.UNSORTED]);
});

test('Không lọc: trả nguyên dữ liệu server, không cộng lại', () => {
  const data = book();
  assert.equal(M.scope(data, null, coms), data);
});

test('Lọc mặt hàng: cộng lại tổng tháng, hôm nay, số khách, không rõ ngày; bỏ ngày không còn phiếu', () => {
  const cang = M.scope(book(), 'Sầu riêng cảng', coms);
  assert.deepEqual(cang.summary, { total_vnd: '532600000', count: 2, customers: 1, undated_vnd: '0', undated_count: 0, today_vnd: '420000000', today_count: 1, has_sheet: true });
  assert.deepEqual(cang.days.map(day => [day.date, day.total_vnd, day.count]), [['2026-10-30', '420000000', 1], ['2026-10-14', '112600000', 1]]);
  assert.deepEqual(cang.customers.map(row => row.customer_id), [1]);
  assert.equal(cang.offsets.length, 1, 'cấn trừ có một đầu thuộc mặt hàng');
  assert.equal(cang.voided.length, 0);

  const unsorted = M.scope(book(), F.UNSORTED, coms);
  assert.deepEqual(unsorted.summary, { total_vnd: '5500000', count: 1, customers: 1, undated_vnd: '30000000', undated_count: 1, today_vnd: '0', today_count: 0, has_sheet: true });
  assert.equal(unsorted.voided.length, 1);
  assert.equal(unsorted.offsets.length, 0);

  const none = M.scope(book(), 'Mít', coms);
  assert.deepEqual(none.summary, { total_vnd: '0', count: 0, customers: 0, undated_vnd: '0', undated_count: 0, today_vnd: '0', today_count: 0, has_sheet: false });
  assert.deepEqual(none.days, []);
});

test('Sổ không có trong danh sách khách tính vào "Chưa phân loại", tiền không rơi mất', () => {
  const partial = M.commodityMap(customersFixture.slice(0, 3));
  const groups = M.byCommodity(book(), partial);
  assert.equal(total(groups), 738800000n);
  assert.equal(groups.find(group => group.key === F.UNSORTED).total, 5500000n);
});

test('Theo khách: giữ thứ tự server, thanh so với sổ nhiều tiền nhất', () => {
  const rows = M.byCustomer(book());
  assert.deepEqual(rows.map(row => row.id), [1, 3, 2, 4, 5]);
  assert.equal(rows[0].pct, 100);
  assert.equal(rows[1].pct, 33.8);
  assert.equal(rows[4].pct, 0);
  assert.equal(rows[4].undated, 30000000n);
  assert.equal(rows[3].month, '2026-03-01', 'mở sổ ở tháng của khối');
});

test('Theo mặt hàng: nhóm nhiều tiền trước; tổng nhóm bằng tổng tháng; nhóm và sổ chung một thước', () => {
  const groups = M.byCommodity(book(), coms);
  assert.deepEqual(groups.map(group => [group.key, group.total, group.count, group.undated, group.undatedCount]), [
    ['Sầu riêng cảng', 532600000n, 2, 0n, 0],
    ['Chuối', 180000000n, 1, 0n, 0],
    ['Sầu riêng bộ', 20700000n, 1, 39000000n, 1],
    [F.UNSORTED, 5500000n, 1, 30000000n, 1],
  ]);
  assert.equal(total(groups), 738800000n);
  assert.equal(undated(groups), 69000000n);
  assert.equal(groups[0].pct, 100);
  assert.equal(groups[3].rows.find(row => row.id === 4).pct, F.barWidth('5500000', '532600000'));
  assert.deepEqual(groups[3].rows.map(row => row.id), [4, 5], 'trong nhóm giữ thứ tự server');
});

test('Phần tiền của một dòng: Sheet theo tháng của khối, web theo phân bổ, phân bổ thiếu thì phần còn lại đứng riêng', () => {
  assert.deepEqual(M.receiptParts(sheet(1, 1, '2026-10-14', '100', '2026-09-01')), [{ kind: 'debt', month: '2026-09-01', amount: 100n }]);
  assert.deepEqual(M.receiptParts(web(2, 1, '2026-10-14', '100', [debt('2026-07-01', '60'), advance('2026-08-01', '40')])),
    [{ kind: 'debt', month: '2026-07-01', amount: 60n }, { kind: 'advance', month: '2026-08-01', amount: 40n }]);
  assert.deepEqual(M.receiptParts(web(3, 1, '2026-10-14', '100', [debt('2026-07-01', '60')])),
    [{ kind: 'debt', month: '2026-07-01', amount: 60n }, { kind: 'none', month: '2026-10-01', amount: 40n }]);
  assert.deepEqual(M.receiptParts(web(4, 1, '2026-10-14', '100', [])), [{ kind: 'none', month: '2026-10-01', amount: 100n }]);
});

test('Theo tháng nợ: tách đúng phần tiền, nợ cũ trước, Ứng trước sau; không rõ ngày tính riêng; tổng nhóm bằng tổng tháng', () => {
  const groups = M.byDebtMonth(book());
  assert.deepEqual(groups.map(group => [group.key, group.total, group.count, group.undated]), [
    ['2026-03-01', 5500000n, 1, 0n],
    ['2026-07-01', 300000000n, 1, 0n],
    ['2026-08-01', 120000000n, 1, 0n],
    ['2026-09-01', 307600000n, 3, 0n],
    ['2026-10-01', 0n, 0, 69000000n],
    ['advance', 5700000n, 1, 0n],
  ]);
  assert.equal(total(groups), 738800000n);
  assert.equal(undated(groups), 69000000n);
  const september = groups[3];
  assert.deepEqual(september.rows.map(row => [row.id, row.total, row.lastDate, row.month]), [
    [3, 180000000n, '2026-10-30', '2026-09-01'],
    [1, 112600000n, '2026-10-14', '2026-09-01'],
    [2, 15000000n, '2026-10-16', '2026-09-01'],
  ]);
  assert.equal(groups[4].rows[0].lastDate, null);
  assert.equal(groups[5].kind, 'advance');
  assert.equal(groups[5].month, null);
  assert.equal(groups[5].rows[0].month, '2026-09-01', 'phần ứng trước mở sổ ở tháng có dòng đó');
  assert.equal(groups[1].pct, F.barWidth('300000000', '307600000'));
  assert.equal(groups[3].pct, 100);
});

test('Theo tháng nợ theo bộ lọc vẫn khớp tổng đang hiện', () => {
  for (const key of M.commodityOptions(coms)) {
    const scoped = M.scope(book(), key, coms);
    const groups = M.byDebtMonth(scoped);
    assert.equal(total(groups), F.toBig(scoped.summary.total_vnd), key);
    assert.equal(undated(groups), F.toBig(scoped.summary.undated_vnd), key);
    const byCom = M.byCommodity(scoped, coms);
    assert.equal(total(byCom), F.toBig(scoped.summary.total_vnd), key);
    assert.equal(undated(byCom), F.toBig(scoped.summary.undated_vnd), key);
  }
});

test('12 tháng: đủ 12 tháng liền, tháng không có phiếu vẫn có dòng, qua năm đúng, chung một thước', () => {
  const rows = M.lastYear(book());
  assert.equal(rows.length, 12);
  assert.equal(rows[0].month, '2026-10-01');
  assert.equal(rows[11].month, '2025-11-01');
  assert.equal(rows[2].month, '2026-08-01');
  assert.equal(rows[1].has, false);
  assert.equal(rows[1].total, 0n);
  assert.equal(rows[10].month, '2025-12-01');
  assert.equal(rows[10].undated, 300000000n);
  assert.equal(rows[0].pct, F.barWidth('738800000', '807800000'));
  assert.equal(rows[0].undatedPct, F.barWidth('69000000', '807800000'));
  assert.equal(rows[11].has, false);
});

test('12 tháng: tháng hiện tại chưa có phiếu vẫn là mốc; tháng khối đi trước hôm nay thì lấy tháng mới nhất', () => {
  const data = { ...book(), today_month: '2026-11-01' };
  assert.equal(M.lastYear(data)[0].month, '2026-11-01');
  assert.equal(M.lastYear(data)[0].has, false);
  const ahead = { ...book(), months: [{ month: '2027-01-01', total_vnd: '0', count: 0, undated_vnd: '5', undated_count: 1 }, ...book().months] };
  assert.equal(M.lastYear(ahead)[0].month, '2027-01-01');
  assert.equal(M.lastYear(ahead)[0].has, true);
});

test('Dải ngày: đủ ngày của tháng, cột theo ngày nhiều tiền nhất, đánh dấu hôm nay và ngày chưa tới', () => {
  const data = book();
  const strip = M.dayStrip(data, data);
  assert.equal(strip.length, 31);
  const plain = ({ customers: _customers, shares: _shares, ...cell }) => cell;
  assert.deepEqual(plain(strip[29]), { day: 30, date: '2026-10-30', total: '600000000', count: 2, pct: 100, today: true, future: false });
  assert.deepEqual(plain(strip[30]), { day: 31, date: '2026-10-31', total: null, count: 0, pct: 0, today: false, future: true });
  assert.equal(strip[15].pct, F.barWidth('20700000', '600000000'));
  const february = { ...data, month: '2028-02-01', days: [] };
  assert.equal(M.dayStrip(february, february).length, 29);
});

test('Phiếu Sheet chờ: bỏ sổ đã khớp, lọc theo mặt hàng; đang tính và không đọc được phân biệt rõ', () => {
  const box = (id, ready, review, amount, extra) => ({ customer_id: id, receipts: { ready, review, amount_vnd: amount }, ...extra });
  const inbox = { state: 'ready', books: [box(1, 2, 0, '50000000'), box(3, 0, 1, '35000000'), box(4, 5, 0, '1000', { sheet_matched: true }), box(2, 0, 0, '0')] };
  assert.deepEqual(M.pending(inbox), { count: 3, amount: '85000000' });
  assert.deepEqual(M.pending(inbox, 'Chuối', coms), { count: 1, amount: '35000000' });
  assert.equal(M.pending(inbox, 'Mít', coms), null);
  assert.equal(M.pending({ state: 'ready', books: [] }), null);
  assert.equal(M.pending({ state: 'computing', books: [] }), 'computing');
  assert.equal(M.pending({ state: 'unavailable' }), 'unknown');
  assert.equal(M.pending(null), 'unknown');
});

test('Số tiền sai dạng từ API thì báo lỗi, không cộng bừa', () => {
  const data = book();
  data.days[0].rows[0].allocations = [{ month: '2026-07-01', kind: 'debt', amount_vnd: 'abc' }];
  assert.throws(() => M.byDebtMonth(data), /không hợp lệ/);
});

// ---- TUONG-TAC-01 ----
test('scopeDay: không lọc trả nguyên; lọc thì số cộng lại từ dòng trong ngày, bỏ phần thuộc cả tháng', () => {
  const whole = book();
  assert.equal(M.scopeDay(whole, null), whole);
  const day = M.scopeDay(whole, '2026-10-30');
  assert.deepEqual(day.days.map(item => item.date), ['2026-10-30']);
  assert.equal(day.summary.total_vnd, '600000000');
  assert.equal(day.summary.count, 2);
  assert.equal(day.summary.customers, 2);
  assert.equal(day.summary.undated_count, 0);
  assert.equal(day.summary.has_sheet, false);
  assert.deepEqual([day.undated, day.offsets, day.voided], [[], [], []]);
  assert.deepEqual(day.customers.map(row => [row.customer_id, row.total_vnd, row.count, row.last_date]), [[1, '420000000', 1, '2026-10-30'], [3, '180000000', 1, '2026-10-30']]);
  assert.equal(M.scopeDay(whole, '2026-10-14').summary.has_sheet, true);
});

test('scopeDay: ngày không có phiếu thì mọi số bằng 0, không lỗi; gom theo khách và tháng nợ giữ đẳng thức', () => {
  const none = M.scopeDay(book(), '2026-10-02');
  assert.deepEqual([none.days, none.customers, none.summary.total_vnd, none.summary.count], [[], [], '0', 0]);
  const day = M.scopeDay(book(), '2026-10-30');
  const shown = F.sum(M.byDebtMonth(day).map(group => group.total));
  assert.equal(String(shown), day.summary.total_vnd);
  assert.equal(String(F.sum(M.byCustomer(day).map(row => row.total))), day.summary.total_vnd);
});

test('receiptsOf: có ngày trước, không rõ ngày sau; nhóm tháng nợ chỉ lấy phần của nhóm', () => {
  const whole = book();
  const items = M.receiptsOf(whole, 2);
  assert.deepEqual(items.map(item => [item.dated, String(item.amount)]), [[true, '20700000'], [false, '39000000']]);
  assert.deepEqual(M.receiptsOf(whole, 2, '2026-09-01').map(item => String(item.amount)), ['15000000'], 'chỉ phần trừ nợ T9');
  assert.deepEqual(M.receiptsOf(whole, 2, 'advance').map(item => String(item.amount)), ['5700000']);
  assert.deepEqual(M.receiptsOf(whole, 2, '2026-01-01'), []);
  assert.deepEqual(M.receiptsOf(whole, 999), []);
});

test('dayStrip: phần trăm của từng khách trong cột, số khách trong ngày', () => {
  const cell = M.dayStrip(book(), book()).find(item => item.date === '2026-10-30');
  assert.equal(cell.customers, 2);
  assert.deepEqual(cell.shares, { 1: 70, 3: 30 });
  const none = M.dayStrip(book(), book()).find(item => item.date === '2026-10-02');
  assert.deepEqual([none.customers, none.shares], [0, {}]);
});
