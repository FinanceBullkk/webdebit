// GIA-O-01 (B): đọc chữ dán thành giá và lập kế hoạch ghi (so-khach-v7-model.js). Dữ liệu giả.
const assert = require('node:assert/strict');
const { test } = require('node:test');
const M = require('./so-khach-v7-model.js');

test('một cột: theo thứ tự, dòng trống là bỏ qua, dòng trống cuối của Sheet bị bỏ, nhận dấu nghìn và chữ đ', () => {
  const parsed = M.parsePricePaste('45000000\r\n45.000.000\n\n47,000,000\n50.000.000 đ\n');
  assert.equal(parsed.mode, 'order');
  assert.deepEqual(parsed.errors, []);
  assert.deepEqual(parsed.rows.map(row => [row.line, row.priceVnd]), [[1, '45000000'], [2, '45000000'], [3, null], [4, '47000000'], [5, '50000000']]);
});

test('hai cột có container: ghép theo container, cột nào trước cũng được, chữ thường thành chữ hoa', () => {
  const parsed = M.parsePricePaste('DEMU1234567\t45000000\n90.000.000\toldu0000002');
  assert.equal(parsed.mode, 'container');
  assert.deepEqual(parsed.rows.map(row => [row.container, row.priceVnd]), [['DEMU1234567', '45000000'], ['OLDU0000002', '90000000']]);
});

test('chặn cả lần dán và nêu số dòng: số tiền sai, giá 0, nhiều cột, lẫn dòng có và không có container', () => {
  assert.match(M.parsePricePaste('45000000\nabc').errors.join(' '), /Dòng 2: “abc” không đọc được/);
  assert.match(M.parsePricePaste('0').errors.join(' '), /Dòng 1/);
  assert.match(M.parsePricePaste('45 000 000').errors.join(' '), /Dòng 1/);
  assert.match(M.parsePricePaste('DEMU1234567\t02/11\t45000000').errors.join(' '), /Dòng 1: có nhiều cột/);
  assert.match(M.parsePricePaste('45000000\t47000000').errors.join(' '), /có nhiều cột/);
  assert.match(M.parsePricePaste('DEMU1234567\t45000000\n47000000').errors.join(' '), /Có dòng có số container, có dòng không/);
});

const trip = (id, extra) => ({ id, container: `DEMU000000${id}`, event_date: '2026-11-03', status: 'confirmed', unit_price_vnd: null,
  other_fee_vnd: null, amount_vnd: null, is_fee_only: false, editable: true, deleted: false, ...extra });
const snapshot = {
  total_outstanding_vnd: '100000000',
  trips: [trip(1, { other_fee_vnd: '500000' }), trip(2, { unit_price_vnd: '40000000', amount_vnd: '40000000' }),
    trip(3, { status: 'pending_review' }), trip(4, { status: 'rejected' }), trip(5, { editable: false }),
    trip(6, { container: null, is_fee_only: true, other_fee_vnd: '300000', amount_vnd: '300000' }),
    trip(7, { unit_price_vnd: '45000000', amount_vnd: '45000000' })],
  legacy_rows: [{ id: 21, kind: 'trip', current: { container: 'OLDU0000001', event_date: '2026-11-01', unit_price_vnd: null } }],
};

test('theo thứ tự: chỉ ghi chuyến web sửa được; lý do không ghi; nợ trước → sau đúng tiền từng chuyến', () => {
  const parsed = M.parsePricePaste(['45000000', '99000000', '47000000', '1', '1', '1', '1', '45000000', '', '500000', '1'].join('\n'));
  const order = ['trip-1', 'legacy-21', 'trip-2', 'trip-3', 'trip-4', 'trip-5', 'trip-6', 'trip-7', 'trip-8', 'trip-9'];
  const plan = M.planPricePaste(parsed, { ...snapshot, trips: [...snapshot.trips, trip(8), trip(9)] }, order);
  assert.deepEqual(plan.items.map(item => item.status === 'skip' ? `skip:${item.reason}` : item.status), [
    'write', 'skip:dòng sổ gốc: sửa từng ô', 'write', 'skip:chờ kiểm', 'skip:đã loại', 'skip:tháng khóa', 'skip:dòng phí lẻ', 'same', 'empty', 'write',
    'skip:thừa, hết chuyến trong bảng tháng']);
  assert.deepEqual(plan.writes.map(item => [item.tripId, item.priceVnd, item.otherFeeVnd, item.oldPriceVnd]),
    [[1, '45000000', '500000', null], [2, '47000000', null, '40000000'], [9, '500000', null, null]]);
  // 45.500.000 (đơn giá + phụ phí đang có) + 7.000.000 (40 → 47 triệu) + 500.000
  assert.equal(plan.deltaVnd, 53000000n);
  assert.equal(plan.afterVnd, 153000000n);
  assert.deepEqual(plan.writes.map(item => [item.overwrite, item.small]), [[false, false], [true, false], [false, true]]);
});

test('ghép container: không có trong sổ, có nhiều dòng, dán hai lần cho một chuyến thì không ghi', () => {
  const twin = { ...snapshot, trips: [...snapshot.trips, trip(10, { container: 'DEMU0000002' })] };
  const parsed = M.parsePricePaste(['DEMU0000001\t45000000', 'XXXU9999999\t45000000', 'DEMU0000002\t45000000', 'OLDU0000001\t45000000'].join('\n'));
  const plan = M.planPricePaste(parsed, twin, []);
  assert.deepEqual(plan.items.map(item => item.status === 'skip' ? item.reason : item.status),
    ['write', 'không có trong sổ', 'container có nhiều dòng trong sổ', 'dòng sổ gốc: sửa từng ô']);
  const again = M.planPricePaste(M.parsePricePaste('DEMU0000001\t45000000\nDEMU0000001\t46000000'), snapshot, []);
  assert.deepEqual(again.items.map(item => item.reason), ['dán hai lần cho cùng chuyến', 'dán hai lần cho cùng chuyến']);
  assert.equal(again.writes.length, 0);
  assert.equal(again.afterVnd, again.beforeVnd);
});

test('sau review: dòng trống sau chuyến cuối là trống; trùng giá đang có vẫn tính là dán hai lần; container sổ có khoảng trắng; số quá lớn bị chặn', () => {
  const tail = M.planPricePaste(M.parsePricePaste('45000000\n\n46000000'), snapshot, ['trip-1']);
  assert.deepEqual(tail.items.map(item => item.status === 'skip' ? item.reason : item.status), ['write', 'empty', 'thừa, hết chuyến trong bảng tháng']);
  const twice = M.planPricePaste(M.parsePricePaste('DEMU0000002\t40000000\nDEMU0000002\t41000000'), snapshot, []);
  assert.deepEqual(twice.items.map(item => item.reason), ['dán hai lần cho cùng chuyến', 'dán hai lần cho cùng chuyến']);
  const spaced = { ...snapshot, trips: [...snapshot.trips, trip(11, { container: 'DEMU 0000011' }), trip(12, { container: 'demu0000011' })] };
  assert.equal(M.planPricePaste(M.parsePricePaste('DEMU0000011\t45000000'), spaced, []).items[0].reason, 'container có nhiều dòng trong sổ');
  assert.match(M.parsePricePaste('99999999999999999999').errors.join(' '), /Dòng 1/);
});
