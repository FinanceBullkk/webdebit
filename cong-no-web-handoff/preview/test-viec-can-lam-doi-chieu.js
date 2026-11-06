const assert = require('node:assert/strict');
const { test } = require('node:test');
const M = require('./viec-can-lam-doi-chieu-model.js');

const statement = {
  web_vnd: '5210000000', sheet_total_vnd: '5274200000', web_ahead_vnd: '0',
  groups: [
    { id: 'prices:2026-10', kind: 'prices', month: '2026-10', count: 2, delta_vnd: '58400000', locked: true,
      rows: [{ key: 'legacy:1', delta_vnd: '50000000', web_unit_price_vnd: '60', sheet_unit_price_vnd: '60' }, { key: 'legacy:2', delta_vnd: '8400000', web_unit_price_vnd: '60', sheet_unit_price_vnd: '60' }] },
    { id: 'receipts_no_date:2026-10', kind: 'receipts_no_date', month: '2026-10', count: 1, delta_vnd: '-6100000', locked: false, rows: [{ amount_vnd: '6100000' }] },
  ],
};

test('chưa chọn gì: số web và số lệch hiện tại, không có khoản để ghi', () => {
  const sum = M.summarize(statement);
  assert.equal(sum.after, sum.web);
  assert.equal(sum.remaining, '-64200000');
  assert.deepEqual(sum.items, []);
});

test('chọn khoản: cộng đúng từng đồng, tháng khóa theo khoản đã chọn', () => {
  const one = M.summarize(statement, new Set(['prices:2026-10']));
  assert.equal(one.after, '5268400000');
  assert.equal(one.remaining, '-5800000');
  assert.deepEqual(one.items, [{ id: 'prices:2026-10', delta_vnd: '58400000', rows: null }]);
  assert.deepEqual(one.lockedMonths, ['2026-10']);
  const two = M.summarize(statement, new Set(['prices:2026-10', 'receipts_no_date:2026-10']));
  assert.equal(two.remaining, '-11900000');
  assert.deepEqual(M.summarize(statement, new Set(['receipts_no_date:2026-10'])).lockedMonths, []);
});

test('bỏ bớt chuyến: chỉ gửi chuyến còn chọn, bỏ hết thì như không chọn', () => {
  const part = M.summarize(statement, new Set(['prices:2026-10']), new Set(['legacy:1']));
  assert.deepEqual(part.items, [{ id: 'prices:2026-10', delta_vnd: '8400000', rows: ['legacy:2'] }]);
  assert.equal(part.remaining, '-55800000');
  assert.deepEqual(M.summarize(statement, new Set(['prices:2026-10']), new Set(['legacy:1', 'legacy:2'])).items, []);
});

test('tổng Sheet chưa biết là null, không phải 0; web đi trước được trừ khỏi số lệch', () => {
  const unknown = M.summarize({ ...statement, sheet_total_vnd: null });
  assert.equal(unknown.sheet, null);
  assert.equal(unknown.remaining, null);
  assert.equal(M.summarize({ ...statement, sheet_total_vnd: '5200000000', web_ahead_vnd: '10000000', groups: [] }).remaining, '0');
});

test('số lớn hơn giới hạn số thực vẫn đúng từng đồng', () => {
  const sum = M.summarize({ web_vnd: '9007199254740993', sheet_total_vnd: '9007199254740994', groups: [{ id: 'a', kind: 'receipts', delta_vnd: '1', rows: [{}] }] }, new Set(['a']));
  assert.equal(sum.after, '9007199254740994');
  assert.equal(sum.remaining, '0');
});

test('khách phải xem: bỏ máy đã sửa và web đi trước, máy ghi sai đứng đầu, lệch lớn trước, chưa biết số xếp cuối', () => {
  const rows = M.openRows({ customers: [
    { customer_id: 1, reason: 'NO_EXACT_FIX', status: 'LECH_TONG', difference_vnd: '-5' },
    { customer_id: 2, reason: 'FIXED', status: 'KHOP', difference_vnd: '0' },
    { customer_id: 3, reason: 'WEB_AHEAD', status: 'LECH_TONG', difference_vnd: '600' },
    { customer_id: 4, reason: 'FIXED', status: 'LECH_TONG', difference_vnd: '10' },
    { customer_id: 5, reason: 'NOTHING_TO_WRITE', status: 'LECH_TONG', difference_vnd: '90' },
    { customer_id: 6, reason: 'HELD', status: 'CHI_CO_WEB', difference_vnd: null },
    { customer_id: 7, reason: 'VERIFY_FAILED', status: 'LECH_TONG', difference_vnd: '1' },
    { customer_id: 8, reason: 'BOOK_CREATED', status: 'KHOP', difference_vnd: '0' },
  ] });
  assert.deepEqual(rows.map(row => row.customer_id), [7, 5, 1, 6]);
  assert.deepEqual([...M.openIds({ customers: [{ customer_id: null, reason: 'CHI_CO_SHEET' }, { customer_id: 9, reason: 'HELD' }] })], [9]);
});

test('tỷ lệ số nợ: còn khách lệch thì không ghi tròn 100; chưa có tổng thì không có tỷ lệ', () => {
  assert.equal(M.share({ all_web_vnd: '100', matched_web_vnd: '88', counts: { KHOP: 1 }, total: 2 }), '88');
  assert.equal(M.share({ all_web_vnd: '100', matched_web_vnd: '100', counts: { KHOP: 1 }, total: 2 }), 'gần 100');
  assert.equal(M.share({ all_web_vnd: '100', matched_web_vnd: '100', counts: { KHOP: 2 }, total: 2 }), '100');
  assert.equal(M.share({ all_web_vnd: '0' }), null);
});

test('lần đối soát tới theo giờ VN, kết quả cũ chỉ trong khung chạy', () => {
  const at = text => Date.parse(`2026-11-06T${text}:00+07:00`);
  assert.equal(M.nextCheck(at('06:30')), '07:05');
  assert.equal(M.nextCheck(at('10:01')), '10:05');
  assert.equal(M.nextCheck(at('10:15')), '11:05');
  assert.equal(M.nextCheck(at('22:01')), '22:05');
  assert.equal(M.nextCheck(at('22:30')), '07:05 sáng mai');
  assert.equal(M.isOld('2026-11-06T08:05:00+07:00', at('15:00')), true);
  assert.equal(M.isOld('2026-11-06T14:05:00+07:00', at('15:00')), false);
  assert.equal(M.isOld('2026-11-05T22:05:00+07:00', at('06:30')), false);
});

test('chỉ khác phụ phí khi mọi dòng cùng đơn giá; web chưa có giá là giá', () => {
  assert.equal(M.isFeeOnly(statement.groups[0]), true);
  assert.equal(M.isFeeOnly({ kind: 'prices', rows: [{ web_unit_price_vnd: '60', sheet_unit_price_vnd: '65' }] }), false);
  assert.equal(M.isFeeOnly({ kind: 'prices', rows: [{ web_unit_price_vnd: null, sheet_unit_price_vnd: '65' }] }), false);
  assert.equal(M.isFeeOnly(statement.groups[1]), false);
});
