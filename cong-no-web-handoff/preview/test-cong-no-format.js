const { test } = require('node:test');
const assert = require('node:assert/strict');
const F = require('./cong-no-format.js');

test('full keeps exact VND with Vietnamese grouping and minus sign', () => {
  assert.equal(F.full('21790000000'), '21.790.000.000 đ');
  assert.equal(F.full('-350000000'), '−350.000.000 đ');
  assert.equal(F.full('0'), '0 đ');
  assert.throws(() => F.full('1.5'), /không hợp lệ/);
  assert.throws(() => F.full(12), /không hợp lệ/);
});

test('short rounds half up to tỷ/triệu and trims zeros', () => {
  assert.equal(F.short('63911000000'), '63,91 tỷ');
  assert.equal(F.short('11800000000'), '11,8 tỷ');
  assert.equal(F.short('9000000000'), '9 tỷ');
  assert.equal(F.short('9004999999'), '9 tỷ');
  assert.equal(F.short('9005000000'), '9,01 tỷ');
  assert.equal(F.short('412500000'), '412,5 triệu');
  assert.equal(F.short('950000000', 'tr'), '950 tr');
  assert.equal(F.short('999950000'), '1 tỷ');
  assert.equal(F.short('-350000000'), '−350 triệu');
  assert.equal(F.short('950000'), '950.000 đ');
  assert.equal(F.short('1234567890123'), '1.234,57 tỷ');
});

test('percent uses exact integers and handles empty totals', () => {
  assert.equal(F.percent('21790000000', '63911000000'), '34,1%');
  assert.equal(F.percent('1', '3'), '33,3%');
  assert.equal(F.percent('2', '3'), '66,7%');
  assert.equal(F.percent('5', '5'), '100%');
  assert.equal(F.percent('5', '0'), '—');
  assert.equal(F.percent('-1', '4'), '−25%');
});

test('barWidth gives a clamped CSS percentage', () => {
  assert.equal(F.barWidth('21790000000', '63911000000'), 34.1);
  assert.equal(F.barWidth('5', '5'), 100);
  assert.equal(F.barWidth('6', '5'), 100);
  assert.equal(F.barWidth('-1', '5'), 0);
  assert.equal(F.barWidth('1', '0'), 0);
});

test('sum is exact beyond Number precision', () => {
  assert.equal(F.sum(['9007199254740993', '1', 2n]), 9007199254740996n);
  assert.equal(F.sum([]), 0n);
});

test('heatStep bins by absolute amount', () => {
  assert.deepEqual(['1', '199999999', '200000000', '500000000', '1000000000', '2000000000', '4000000000', '9000000000'].map(F.heatStep), [1, 1, 2, 3, 4, 5, 6, 6]);
});

test('esc escapes the five HTML characters and blanks null', () => {
  assert.equal(F.esc(`<a href="x">Tom & Jerry's</a>`), '&lt;a href=&quot;x&quot;&gt;Tom &amp; Jerry&#39;s&lt;/a&gt;');
  assert.equal(F.esc(null), '');
  assert.equal(F.esc(0), '0');
});

test('foldText keeps length and punctuation; fold collapses to search words', () => {
  assert.equal(F.foldText('Nguyễn Hoàng Vũ · Đà Lạt'), 'nguyen hoang vu · da lat');
  assert.equal(F.foldText('Hoàng').length, 'Hoàng'.length);
  assert.equal(F.fold('  Sầu riêng · BỘ  '), 'sau rieng bo');
  assert.equal(F.fold(null), '');
});

test('transportText and commodityText follow the DB codes CANG/BO', () => {
  assert.deepEqual(['CANG', 'BO', 'CẢNG', 'BỘ', null, undefined, ''].map(F.transportText), ['cảng', 'bộ', 'cảng', 'bộ', '', '', '']);
  assert.equal(F.commodityText('Sầu riêng', 'BO'), 'Sầu riêng · bộ');
  assert.equal(F.commodityText('Chuối', null), 'Chuối');
  assert.equal(F.commodityText(null, 'BO'), F.UNSORTED);
});

test('customerLabels keys by String(id) and disambiguates duplicates with sổ id', () => {
  const rows = [
    { id: 7, name: 'OLD A', display_name: 'SHEET', commodity: 'Chuối' },
    { id: 8, name: 'OLD B', display_name: 'SHEET', commodity: 'Chuối' },
    { id: 9, name: 'UNMAPPED', commodity: null },
    { id: 10, name: 'X', label: 'Đặt sẵn' },
  ];
  assert.equal(F.customerLabel(rows[0]), 'SHEET · Chuối');
  assert.equal(F.customerLabel(rows[2]), 'UNMAPPED');
  assert.equal(F.customerLabel(rows[3]), 'Đặt sẵn');
  assert.deepEqual([...F.customerLabels(rows)], [['7', 'SHEET · Chuối · sổ 7'], ['8', 'SHEET · Chuối · sổ 8'], ['9', 'UNMAPPED'], ['10', 'Đặt sẵn']]);
});

test('month labels accept YYYY-MM and YYYY-MM-DD', () => {
  assert.equal(F.monthLabel('2026-07'), '7/2026');
  assert.equal(F.monthLabel('2026-07-19'), '7/2026');
  assert.equal(F.monthTitle('2026-07-01'), 'Tháng 07/2026');
  assert.equal(F.monthTag('2026-07-01', 2026), 'T7');
  assert.equal(F.monthTag('2025-12-01', 2026), 'T12/2025');
});

// Audit UX 31/10/2026 (đợt 1): số triệu không đơn vị cho ma trận, một kiểu ngày dd/mm/yyyy, câu lỗi tải trang.
test('millions writes triệu without unit for tables that state "triệu đồng" once', () => {
  assert.equal(F.millions('412500000'), '412,5');
  assert.equal(F.millions('380000000'), '380');
  assert.equal(F.millions('1249600000'), '1.250');
  assert.equal(F.millions('999999999'), '1.000');
  assert.equal(F.millions('950000'), '0,95');
  assert.equal(F.millions('50000'), '0,05');
  assert.equal(F.millions('5000'), '0,01');
  assert.equal(F.millions('4999'), '<0,01');
  assert.equal(F.millions('-15500000'), '−15,5');
  assert.equal(F.millions(-20000n), '−0,02');
  assert.equal(F.millions('0'), '0');
  assert.throws(() => F.millions('1.5'), /không hợp lệ/);
});

test('dateText writes dd/mm/yyyy from ISO dates and keeps any other text', () => {
  assert.equal(F.dateText('2026-10-22'), '22/10/2026');
  assert.equal(F.dateText('2026-10-22 08:15:00'), '22/10/2026');
  assert.equal(F.dateText('2026-10-22T08:15:00+07:00'), '22/10/2026');
  assert.equal(F.dateText(null), '');
  assert.equal(F.dateText(''), '');
  assert.equal(F.dateText('2026-10-2'), '2026-10-2');
  assert.equal(F.dateText('đã tt'), 'đã tt');
});

test('loadError says what failed and what to do, never a browser string', () => {
  assert.equal(F.loadError('ma trận công nợ'), 'Không tải được ma trận công nợ. Kiểm tra mạng rồi bấm Thử lại.');
});
