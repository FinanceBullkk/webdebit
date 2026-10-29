const { test } = require('node:test');
const assert = require('node:assert/strict');
const M = require('./dashboard-v7-model.js');
const F = require('./cong-no-format.js');

const months = values => Object.fromEntries(Array.from({ length: 12 }, (_, i) => [String(i + 1), values[i + 1] ?? '0']));
const current = { year: 2026, customers: [
  { customer_id: 1, name: 'Khách A', commodity: 'Sầu riêng', transport_mode: 'CANG', months: months({ 10: '300', 8: '200', 5: '100' }), total_all_vnd: '1100' },
  { customer_id: 2, name: 'Khách B', commodity: 'Sầu riêng', transport_mode: null, months: months({ 9: '50' }), total_all_vnd: '50' },
  { customer_id: 3, name: 'Khách C', commodity: null, transport_mode: null, months: months({ 10: '-70' }), total_all_vnd: '-70' },
  { customer_id: 4, name: 'Khách D', commodity: 'Chuối', transport_mode: 'BO', months: months({ 1: '40' }), total_all_vnd: '40' },
] };
const previous = { year: 2025, customers: [
  { customer_id: 1, name: 'Khách A', months: months({ 12: '400', 2: '60' }), total_all_vnd: '1100' },
] };

test('ageIndex matches get_dashboard buckets across years', () => {
  assert.equal(M.ageIndex(2026, 10, '2026-10-29'), 0);
  assert.equal(M.ageIndex(2026, 11, '2026-10-29'), 0);
  assert.equal(M.ageIndex(2026, 8, '2026-10-29'), 1);
  assert.equal(M.ageIndex(2026, 4, '2026-10-29'), 2);
  assert.equal(M.ageIndex(2026, 3, '2026-10-29'), 3);
  assert.equal(M.ageIndex(2025, 12, '2026-02-10'), 1);
  assert.equal(M.ageIndex(2025, 8, '2026-02-10'), 2);
});

test('commodityKey splits only durian by transport', () => {
  assert.equal(M.commodityKey('Sầu riêng', 'CANG'), 'Sầu riêng cảng');
  assert.equal(M.commodityKey('Sầu riêng', 'BỘ'), 'Sầu riêng bộ');
  assert.equal(M.commodityKey('Sầu riêng', null), M.UNSORTED);
  assert.equal(M.commodityKey('Chuối', 'BO'), 'Chuối');
  assert.equal(M.commodityKey(null, null), M.UNSORTED);
});

test('debtors bucket each month and put the rest before last year into over-6', () => {
  const list = M.debtors(current, previous, '2026-10-29');
  assert.deepEqual(list.map(row => row.id), [1, 2, 4]);
  const a = list[0];
  assert.deepEqual(a.buckets, [300n, 200n, 100n, 500n]);
  assert.equal(a.older, 40n);
  assert.deepEqual(a.months.map(item => item.key), ['2026-10', '2026-08', '2026-05', '2025-12', '2025-02']);
  assert.deepEqual(M.bucketTotals(list), [300n, 250n, 100n, 540n]);
  const aging = [['current', '300'], ['1-2', '250'], ['3-6', '100'], ['over-6', '540']].map(([bucket, v]) => ({ bucket, receivable_vnd: v }));
  assert.equal(M.agingMatches(list, aging), true);
  aging[3].receivable_vnd = '541';
  assert.equal(M.agingMatches(list, aging), false);
});

test('commodityGroups sorts, folds under 1% into Khác and keeps unsorted last', () => {
  const groups = M.commodityGroups([
    { commodity: 'Chuối', transport_mode: null, customers: 2, receivable_vnd: '600' },
    { commodity: 'Chuối', transport_mode: 'BO', customers: 1, receivable_vnd: '100' },
    { commodity: 'Sầu riêng', transport_mode: 'CANG', customers: 3, receivable_vnd: '3000' },
    { commodity: 'Sầu riêng', transport_mode: null, customers: 1, receivable_vnd: '5' },
    { commodity: 'Mít', transport_mode: null, customers: 1, receivable_vnd: '9' },
    { commodity: null, transport_mode: null, customers: 1, receivable_vnd: '286' },
  ], '4000');
  assert.deepEqual(groups.map(g => [g.key, g.total, g.customers]), [
    ['Sầu riêng cảng', 3000n, 3], ['Chuối', 700n, 3], ['Khác', 9n, 1], [M.UNSORTED, 291n, 2]]);
  assert.deepEqual(groups[2].members, ['Mít']);
  assert.equal(groups[3].grey, true);
});

test('majorCount takes rows until 60% and filterDebtors filters by age and group', () => {
  assert.equal(M.majorCount(['2179', '1180', '903', '560']), 2);
  assert.equal(M.majorCount(['100']), 1);
  assert.equal(M.majorCount([]), 0);
  const list = M.debtors(current, previous, '2026-10-29');
  assert.deepEqual(M.filterDebtors(list).map(item => [item.row.id, item.value]), [[1, 1100n], [2, 50n], [4, 40n]]);
  assert.deepEqual(M.filterDebtors(list, { age: 1 }).map(item => [item.row.id, item.value]), [[1, 200n], [2, 50n]]);
  const unsorted = { key: M.UNSORTED, members: [M.UNSORTED] };
  assert.deepEqual(M.filterDebtors(list, { age: 1, group: unsorted }).map(item => item.row.id), [2]);
  assert.equal(F.billions('970000000'), '0,97');
  assert.equal(F.billions('21794999999'), '21,79');
  assert.equal(F.billions('21795000000'), '21,80');
});
