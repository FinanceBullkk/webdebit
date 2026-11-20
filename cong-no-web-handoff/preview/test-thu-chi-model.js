const assert = require('node:assert/strict');
const test = require('node:test');
const M = require('./thu-chi-model.js');

// ZALO-THU-CHI-01 PR-2: phép tính của trang Thu chi. Dữ liệu giả.
const item = (day, direction, amount, status, extra = {}) => ({ source: 'chat', message_id: `m-${day}-${direction}-${amount}-${status}`, conversation_id: 'c', sent_at: 1, day, direction,
  amount_vnd: amount, status, shared: false, ledger_vnd: null, ledger_ref: null, target: { kind: null, id: null, label: null }, ambiguous: false, media: [], text: '', ...extra });

test('Tổng thu, chi, ứng cộng BigInt; khoản không có số chỉ đếm riêng, không vào tổng', () => {
  const sum = M.summarize([item('2026-11-20', 'thu', 50_000_000, 'RECORDED'), item('2026-11-20', 'thu', 1_200_000, 'MISSING'), item('2026-11-20', 'chi', 2_500_000, 'WAITING'),
    item('2026-11-20', 'ung', 3_000_000, 'AMOUNT_DIFF'), item('2026-11-20', 'thu', null, 'NO_AMOUNT')]);
  assert.deepEqual([sum.thu, sum.chi, sum.ung], [{ n: 2, vnd: '51200000' }, { n: 1, vnd: '2500000' }, { n: 1, vnd: '3000000' }]);
  assert.deepEqual([sum.missing, sum.diff, sum.noAmount], [1, 1, 1]);
});

test('Tổng lớn không mất đồng nào (vượt 2^53)', () => {
  const big = [item('2026-11-20', 'thu', 9_007_199_254_740_991, 'RECORDED'), item('2026-11-20', 'thu', 2, 'RECORDED')];
  assert.equal(M.summarize(big).thu.vnd, '9007199254740993');
});

test('Bộ lọc: số đếm khớp danh sách sau khi lọc', () => {
  const items = [item('d', 'thu', 1, 'MISSING'), item('d', 'thu', 2, 'MISSING'), item('d', 'thu', 3, 'AMOUNT_DIFF'), item('d', 'thu', 4, 'SUGGEST'), item('d', 'chi', 5, 'UNKNOWN_TARGET'),
    item('d', 'thu', null, 'NO_AMOUNT'), item('d', 'thu', 6, 'RECORDED')];
  const counts = M.counts(items);
  assert.deepEqual(counts, { all: 7, missing: 2, diff: 1, unknown: 2, noamount: 1 });
  for (const filter of M.FILTERS) assert.equal(M.filterItems(items, filter.id).length, counts[filter.id]);
  assert.equal(M.filterItems(items, 'khong-co').length, 7);
});

test('Gom theo ngày: ngày mới trên cùng, mỗi ngày có tổng riêng', () => {
  const groups = M.groupByDay([item('2026-11-19', 'thu', 5, 'RECORDED'), item('2026-11-20', 'chi', 7, 'WAITING'), item('2026-11-19', 'thu', 6, 'RECORDED')]);
  assert.deepEqual(groups.map(group => [group.day, group.rows.length, group.sum.thu.vnd, group.sum.chi.vnd]), [['2026-11-20', 1, '0', '7'], ['2026-11-19', 2, '11', '0']]);
});

test('Khoảng ngày đếm lùi theo lịch, qua tháng và năm', () => {
  assert.deepEqual(M.range('2026-11-20', 7), { from: '2026-11-14', to: '2026-11-20' });
  assert.deepEqual(M.range('2026-01-03', 7), { from: '2025-12-28', to: '2026-01-03' });
  assert.deepEqual(M.range('2026-03-01', 30), { from: '2026-01-31', to: '2026-03-01' });
});

test('Nhận ra khoản mới theo mã tin, dấu của sổ không có mã thì theo giờ và số tiền', () => {
  const old = [item('d', 'thu', 1, 'WAITING'), item('d', 'thu', 2, 'WAITING', { source: 'mark', message_id: null, sent_at: 5 })];
  const next = [...old, item('d', 'chi', 3, 'WAITING')];
  assert.deepEqual(M.newKeys(old, next), [M.keyOf(next[2])]);
  assert.deepEqual(M.newKeys(old, old), []);
});

test('Câu trạng thái đúng bảng của spec; lệch số ghi cả hai số, NULL không hiện 0', () => {
  assert.equal(M.statusText(item('d', 'thu', 1, 'RECORDED')).text, 'Đã vào sổ');
  assert.equal(M.statusText(item('d', 'thu', 1, 'WAITING')).text, 'Chờ vào sổ');
  assert.equal(M.statusText(item('d', 'thu', 1, 'MISSING')).tone, 'warn');
  assert.equal(M.statusText(item('d', 'thu', 5_000_000, 'AMOUNT_DIFF', { ledger_vnd: 4_500_000 })).text, 'Lệch: báo 5.000.000 đ, sổ 4.500.000 đ');
  assert.match(M.statusText(item('d', 'thu', 1, 'AMOUNT_DIFF', { shared: true, ledger_vnd: 1 })).note, /hai khoản báo/);
  assert.match(M.statusText(item('d', 'thu', 1, 'SUGGEST', { ledger_ref: { name: 'SỔ A' } })).text, /^Có thể là phiếu của sổ SỔ A$/);
  assert.equal(M.statusText(item('d', 'chi', 1, 'UNKNOWN_TARGET')).text, 'Chưa rõ của ai');
  assert.equal(M.statusText(item('d', 'chi', 1, 'NO_LEDGER')).text, 'Web chưa có sổ chi này');
  assert.equal(M.statusText(item('d', 'thu', null, 'NO_AMOUNT')).text, 'Không đọc được số');
  assert.equal(M.money(null), '—');
});

test('Khoản chưa đối chiếu được (nguồn sổ lỗi) không bị ghi là chưa vào sổ', () => {
  const text = M.statusText(item('d', 'thu', 5, 'WAITING', { unchecked: true }));
  assert.deepEqual([text.tone, text.text], ['info', 'Chưa đối chiếu được']);
  assert.match(M.statusText(item('d', 'thu', 5, 'UNKNOWN_TARGET', { unchecked: true })).note, /danh sách khách và xe/);
  assert.equal(M.statusText(item('d', 'thu', 5, 'WAITING')).text, 'Chờ vào sổ');
});
