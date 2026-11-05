/* TUONG-TAC-01: phép tính của thẻ Tình hình. Dữ liệu giả cùng dạng GET /api/v7/ledger và dashboard/debt. */
const { test } = require('node:test');
const assert = require('node:assert/strict');
const M = require('./so-khach-v7-tinh-hinh-model.js');

const M1 = millions => String(millions * 1000000);
const row = (months, tiers) => ({ months: Object.entries(months).map(([month, value]) => ({ month: `${month}-01`, outstanding_vnd: M1(value) })), tiers_vnd: tiers.map(M1) });

test('Tháng nợ xếp theo hạn như tier của Tổng quan, cộng lại bằng tiers_vnd', () => {
  const debt = row({ '2026-07': 8, '2026-08': 140, '2026-09': 93, '2026-10': 200, '2026-11': 50 }, [50, 200, 233, 8, 0]);
  const { groups, matches } = M.debtTiers(debt, '2026-11-15');
  assert.equal(matches, true);
  assert.deepEqual(groups.late.map(item => item.key), ['2026-07', '2026-08', '2026-09']);
  assert.deepEqual(groups.due.map(item => item.key), ['2026-10']);
  assert.deepEqual(groups.future.map(item => item.key), ['2026-11']);
  // Nợ T7 đến hạn cuối T8; nợ T9 đến hạn 31/10; nợ T10 đến hạn 30/11, còn 15 ngày.
  assert.deepEqual([groups.late[0].dueDate, groups.late[0].days], ['2026-08-31', 76]);
  assert.deepEqual([groups.late[2].dueDate, groups.late[2].days], ['2026-10-31', 15]);
  assert.deepEqual([groups.due[0].dueDate, groups.due[0].days], ['2026-11-30', -15]);
  assert.equal(groups.future[0].dueDate, '2026-12-31');
});

test('Tháng nợ qua năm vẫn đúng hạn; lệch tiers_vnd thì báo không khớp, thiếu months cũng vậy', () => {
  const { groups, matches } = M.debtTiers(row({ '2025-12': 10 }, [0, 10, 0, 0, 0]), '2026-01-20');
  assert.equal(matches, true);
  assert.equal(groups.due[0].dueDate, '2026-01-31');
  assert.equal(M.debtTiers(row({ '2026-07': 8 }, [0, 0, 9, 0, 0]), '2026-11-15').matches, false, 'lệch một đồng cũng không hiện từng tháng');
  assert.equal(M.debtTiers({ tiers_vnd: [M1(1), '0', '0', '0', '0'] }, '2026-11-15').matches, false);
});

test('Tháng âm (dư) vẫn cộng vào tier, không bị bỏ', () => {
  const { groups, matches } = M.debtTiers(row({ '2026-07': -5, '2026-08': 20 }, [0, 0, 15, 0, 0]), '2026-11-15');
  assert.equal(matches, true);
  assert.equal(groups.late.length, 2);
});

test('Dữ kiện ngày: đúng ngày ghi ngày, chỉ biết tháng nói rõ, chưa có nói chưa có; quá 90 ngày đếm tháng', () => {
  assert.equal(M.factDate('2026-10-18', true), '18/10/2026');
  assert.match(M.factDate('2026-10-31', false), /^trong tháng 10\/2026$/);
  assert.equal(M.factDate(null, false), 'Chưa có');
  assert.equal(M.ago(90), '90 ngày');
  assert.equal(M.ago(186), '6 tháng');
});

const LEDGER = () => ({
  receipts: [
    { id: 1, date: '2026-10-18', amount_vnd: M1(15), method: 'CK', voided_by_event: null, allocations: [{ month: '2026-07-01', kind: 'debt', amount_vnd: M1(10) }, { month: '2026-07-01', kind: 'advance', amount_vnd: M1(5) }] },
    { id: 2, date: '2026-10-19', amount_vnd: M1(99), method: 'CK', voided_by_event: 7, allocations: [] },
  ],
  trips: [
    { id: 11, month: '2026-11-01', event_date: '2026-11-04', container: 'AAAU1', destination: 'Ea Súp', amount_vnd: null, status: 'confirmed', deleted: false, is_fee_only: false },
    { id: 12, month: '2026-11-01', event_date: '2026-11-04', container: 'AAAU2', destination: 'Ea Súp', amount_vnd: M1(8), status: 'confirmed', deleted: false, is_fee_only: false },
    { id: 13, month: '2026-11-01', event_date: '2026-11-05', container: 'AAAU3', destination: 'Cát Lái', amount_vnd: M1(8), status: 'pending_review', deleted: false, is_fee_only: false },
    { id: 14, month: '2026-11-01', event_date: '2026-11-05', container: null, destination: '', amount_vnd: M1(1), status: 'confirmed', deleted: false, is_fee_only: true },
    { id: 15, month: '2026-11-01', event_date: '2026-11-05', container: 'AAAU5', destination: 'Cát Lái', amount_vnd: M1(8), status: 'rejected', deleted: false, is_fee_only: false },
  ],
  legacy_rows: [
    // Đúng dạng API thật trên hao 5/11/2026: khoản thu sổ gốc chưa sửa có current null, số ở source_total_vnd.
    { id: 21, kind: 'receipt', month: '2026-09-01', source_total_vnd: M1(20), display: { date: null, raw_date: 'da tt' }, current: null },
    { id: 22, kind: 'trip', month: '2026-09-01', display: { date: '2026-09-03' }, current: { month: '2026-09-01', event_date: '2026-09-03', container: 'OLDU1', destination: 'Nơi D', unit_price_vnd: M1(9), counted_vnd: M1(9), deleted: false } },
    { id: 23, kind: 'trip', month: '2026-09-01', display: { date: '2026-09-03' }, current: { month: '2026-09-01', event_date: '2026-09-03', container: 'OLDU2', destination: 'Nơi D', unit_price_vnd: null, counted_vnd: '0', deleted: false } },
    { id: 24, kind: 'receipt', month: '2026-08-01', display: {}, current: { month: '2026-08-01', counted_vnd: M1(5), deleted: true } },
    { id: 25, kind: 'receipt', month: '2026-08-01', source_total_vnd: '0', display: {}, current: null },
    { id: 27, kind: 'receipt', month: '2026-08-01', display: {}, current: null },
    { id: 26, kind: 'trip', month: '2026-08-01', display: {}, current: { month: '2026-08-01', container: 'OLDU3', destination: 'Nơi E', unit_price_vnd: M1(9), counted_vnd: M1(9), deleted: true } },
  ],
});

test('Hoạt động có cả dòng sổ gốc, mới nhất trước; phiếu hủy, dòng đã xóa, khoản 0 đồng không lên', () => {
  const rows = M.activity(LEDGER(), { today: '2026-11-15' });
  assert.deepEqual(rows.map(row => [row.kind, row.key, row.date, row.title]), [
    ['trip', '2026-11', '2026-11-04', '2 chuyến đi hàng'],
    ['paid', '2026-10', '2026-10-18', 'Khách trả 15.000.000 đ'],
    ['paid', '2026-09', null, 'Khách trả 20.000.000 đ'],
    ['trip', '2026-09', '2026-09-03', '2 chuyến đi hàng'],
  ]);
});

test('Hoạt động: khoản sổ gốc không có ngày không bị gán ngày, xếp ở cuối tháng của khối; chi tiết đúng từng dòng', () => {
  const rows = M.activity(LEDGER(), { today: '2026-11-15' });
  const [webTrip, webPay, sheetPay, sheetTrip] = rows;
  assert.equal(sheetPay.date, null);
  assert.equal(sheetPay.sort, '2026-09-30');
  assert.equal(sheetPay.sub, 'theo sổ gốc');
  assert.deepEqual(sheetPay.lines, [['Ghi ở khối', 'T9/2026']]);
  assert.deepEqual(webTrip.lines, [['AAAU1', 'chưa giá'], ['AAAU2', '8.000.000 đ']]);
  assert.deepEqual(sheetTrip.lines, [['OLDU1', '9.000.000 đ'], ['OLDU2', 'chưa giá']]);
  assert.deepEqual(webPay.lines, [['Trừ nợ T7/2026', '10.000.000 đ'], ['Ứng trước', '5.000.000 đ']]);
  assert.equal(webPay.go, 'thang:2026-10');
});

test('Hoạt động: khoản không ngày của tháng đang chạy không xếp vượt hôm nay; hứa trả và Zalo mở Trao đổi; lọc theo loại', () => {
  const data = { legacy_rows: [{ id: 1, kind: 'receipt', month: '2026-11-01', display: {}, current: { month: '2026-11-01', counted_vnd: M1(1), deleted: false } }] };
  const marks = [{ id: 1, kind: 'promise', amount_vnd: M1(44), on_date: '2026-11-20', created_on: '2026-10-30', status: 'pending' },
    { id: 2, kind: 'promise', amount_vnd: M1(1), on_date: '2026-11-20', created_on: '2026-10-29', status: 'cancelled' }];
  const chats = [{ display_name: 'Nhóm thử', last_message_at: Date.UTC(2026, 9, 28, 3) }, { display_name: 'Không tin', last_message_at: null }];
  const rows = M.activity(data, { marks, chats, today: '2026-11-15' });
  assert.deepEqual(rows.map(row => [row.kind, row.sort]), [['paid', '2026-11-15'], ['mark', '2026-10-30'], ['remind', '2026-10-28']]);
  assert.equal(rows[1].go, 'trao-doi');
  assert.deepEqual(rows[1].lines, [['Số tiền', '44.000.000 đ'], ['Hẹn trả', '20/11/2026'], ['Trạng thái', 'đang chờ']]);
  assert.equal(rows.filter(M.KINDS.talk).length, 2);
  assert.equal(rows.filter(M.KINDS.paid).length, 1);
  assert.equal(rows.filter(M.KINDS.trip).length, 0);
  assert.equal(rows.filter(M.KINDS.all).length, 3);
});

test('Hoạt động: dòng sổ gốc đã sửa lấy số đã sửa; dòng chuyến không có current đọc display, không thành chưa giá', () => {
  const rows = M.activity({ legacy_rows: [
    { id: 1, kind: 'receipt', month: '2026-09-01', source_total_vnd: M1(20), display: {}, current: { month: '2026-09-01', counted_vnd: M1(25), deleted: false } },
    { id: 2, kind: 'trip', month: '2026-08-01', source_total_vnd: M1(9), display: { date: '2026-08-03', container: 'SHTU1', to: 'Nơi F', unit_price: M1(9) }, current: null },
    { id: 3, kind: 'trip', month: '2026-07-01', source_total_vnd: '0', display: { date: '2026-07-03', container: 'SHTU2', to: 'Nơi G', unit_price: null }, current: null },
  ] }, { today: '2026-11-15' });
  assert.deepEqual(rows.map(row => row.title), ['Khách trả 25.000.000 đ', '1 chuyến đi hàng', '1 chuyến đi hàng']);
  assert.equal(rows[1].sub, 'Nơi F');
  assert.deepEqual(rows[1].lines, [['SHTU1', '9.000.000 đ']]);
  assert.deepEqual(rows[2].lines, [['SHTU2', 'chưa giá']]);
});

test('Đếm chuyến: bỏ đã xóa, đã loại, phí lẻ; tính dòng chuyến sổ gốc chưa xóa', () => {
  const data = LEDGER();
  assert.equal(M.tripCount(data, '2026-11'), 3, 'cả chờ kiểm và thiếu giá, như thẻ Đi hàng');
  assert.equal(M.tripCount(data, '2026-09'), 2);
  assert.equal(M.tripCount(data, '2026-08'), 0);
  assert.equal(M.tripCount(data, '2026-01'), 0);
});

test('Thước của hình gồm số 0; toàn số 0 hoặc không có gì thì không chia cho 0', () => {
  const a = M.scale([10n, 5n, null]);
  assert.equal(a.at(10n), 1);
  assert.equal(a.at(5n), 0.5);
  assert.equal(a.zeroAt, 0);
  assert.equal(a.at(null), null);
  const b = M.scale([-5n, 15n]);
  assert.equal(b.zeroAt, 0.25);
  assert.equal(M.scale([3, 6]).at(3), 0.5, 'nhận cả số đếm');
  assert.equal(M.scale([0, null]).at(0), 0);
  assert.equal(M.scale([]).zeroAt, 0);
});
