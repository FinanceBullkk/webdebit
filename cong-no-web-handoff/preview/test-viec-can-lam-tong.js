// Tab TONG ở Việc cần làm (KIEM-TONG-01): phần tính của dòng TONG, không DOM. Dữ liệu giả.
const assert = require('node:assert/strict');
const { test } = require('node:test');
const M = require('./viec-can-lam-doi-chieu-model.js');

const tong = (extra = {}) => ({ month: '2026-10', matched: 64, differs: [], unknown_names: [], blank_on_tong: [],
  tong_sum_vnd: '1000', expected_sum_vnd: '1000', gap_vnd: '0', ...extra });

test('không có kết quả TONG, hoặc lượt có quá nhiều khách lệch: không nói gì về TONG', () => {
  assert.equal(M.tongView(null), null);
  assert.equal(M.tongView({ customers: [] }), null);
  assert.equal(M.tongView({ tong: { month: null, skipped: 'TOO_MANY_DIFFERENT' } }), null);
});

test('không đọc được tab TONG hoặc lỗi: chỉ báo là chưa kiểm được, không có dòng nào', () => {
  assert.deepEqual(M.tongView({ tong: { month: null, skipped: 'TONG_KHONG_DOC_DUOC' } }), { skipped: 'TONG_KHONG_DOC_DUOC' });
  assert.deepEqual(M.tongView({ tong: { month: null, skipped: 'ERROR', error: 'KeyError' } }), { skipped: 'ERROR' });
});

test('khớp đủ: không có chỗ phải sửa', () => {
  const view = M.tongView({ tong: tong() });
  assert.equal(view.problems, 0);
  assert.deepEqual(view.rows, []);
  assert.equal(view.gap_sign, 0);
});

test('thứ tự: dòng TONG khác sổ, rồi sổ để trống, rồi tên lạ; mỗi nhóm số lớn trước, kể cả số âm', () => {
  const view = M.tongView({ tong: tong({
    differs: [{ name: 'Mẫu Lệch Nhỏ', book: 4, tong_vnd: '100', expected_vnd: '90' }, { name: 'Mẫu Lệch Lớn', book: 5, tong_vnd: '100', expected_vnd: '300' }],
    blank_on_tong: [{ book: 1, name: 'Mẫu Nợ Nhỏ', expected_vnd: '50' }, { book: 2, name: 'Mẫu Dư Lớn', expected_vnd: '-700' }, { book: 3, name: 'Mẫu Nợ Lớn', expected_vnd: '600' }],
    unknown_names: [{ name: 'MẪU TÊN LẠ', end_vnd: '8' }], gap_vnd: '-1352' }) });
  assert.deepEqual(view.rows.map(row => [row.kind, row.book ?? row.name]), [
    ['differs', 5], ['differs', 4], ['blank', 2], ['blank', 3], ['blank', 1], ['unknown', 'MẪU TÊN LẠ']]);
  assert.equal(view.rows[0].gap_vnd, '-200');
  assert.deepEqual(view.counts, { differs: 2, blank: 3, unknown: 1, renamed: 0 });
  assert.equal(view.problems, 6);
  assert.equal(view.gap_sign, -1);
});

test('tên trên TONG khác tên sổ mà số khớp tới từng đồng với đúng một sổ để trống: gộp thành một dòng "chỉ khác tên"', () => {
  const view = M.tongView({ tong: tong({
    blank_on_tong: [{ book: 9, name: 'KK - MẪU 402', expected_vnd: '123456789' }, { book: 1, name: 'Mẫu Khác', expected_vnd: '5' }],
    unknown_names: [{ name: 'MẪU - DỪA', end_vnd: '123456789' }] }) });
  assert.deepEqual(view.rows.map(row => [row.kind, row.book]), [['blank', 1], ['renamed', 9]]);
  assert.equal(view.rows[1].tong_name, 'MẪU - DỪA');
  assert.deepEqual(view.counts, { differs: 0, blank: 1, unknown: 0, renamed: 1 });
  assert.equal(view.problems, 1);
});

test('chỉ gộp khi không nhập nhằng: lệch một đồng, hai sổ cùng số, hai tên cùng số thì giữ nguyên hai dòng', () => {
  const pairs = blanks => unknown => M.tongView({ tong: tong({ blank_on_tong: blanks, unknown_names: unknown }) }).counts.renamed;
  const one = [{ book: 9, name: 'Mẫu A', expected_vnd: '1000' }];
  assert.equal(pairs(one)([{ name: 'Tên A', end_vnd: '1001' }]), 0);
  assert.equal(pairs([...one, { book: 8, name: 'Mẫu B', expected_vnd: '1000' }])([{ name: 'Tên A', end_vnd: '1000' }]), 0);
  assert.equal(pairs(one)([{ name: 'Tên A', end_vnd: '1000' }, { name: 'Tên B', end_vnd: '1000' }]), 0);
  assert.equal(pairs(one)([{ name: 'Tên A', end_vnd: '1000' }]), 1);
});

test('sổ đang lệch Sheet: dòng TONG của sổ đó được đánh dấu, vì số theo sổ tính từ web', () => {
  const reconcile = { customers: [{ customer: 'Mẫu Lệch', customer_id: 4, status: 'LECH_TONG', reason: 'NO_EXACT_FIX', difference_vnd: '10' },
    { customer: 'Mẫu Đi Trước', customer_id: 6, status: 'LECH_TONG', reason: 'WEB_AHEAD', difference_vnd: '5', web_ahead_vnd: '5' }],
  tong: tong({ differs: [{ name: 'Mẫu Lệch', book: 4, tong_vnd: '100', expected_vnd: '110' }], blank_on_tong: [{ book: 6, name: 'Mẫu Đi Trước', expected_vnd: '7' }] }) };
  assert.deepEqual(M.tongView(reconcile).rows.map(row => [row.book, row.book_differs]), [[4, true], [6, false]]);
});
