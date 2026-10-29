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
