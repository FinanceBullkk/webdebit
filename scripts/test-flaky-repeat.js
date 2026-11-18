// Kiểm scripts/flaky-repeat.js và scripts/flaky-reporter.js (CHAP-CHON-01): đếm đúng ca đỏ, không đếm dòng cha,
// gán lần chạy lại ERR_NO_BUFFER_SPACE cho đúng ca, gộp bảng nhiều máy, và chạy thật một lượt trên file mẫu.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { spawnSync } = require('node:child_process');
const { renderMarkdown, renderMerged, summarizeRound, tally } = require('./flaky-repeat.js');

const ROOT = path.resolve(__dirname, '..');

test('một lượt: chỉ đếm ca lá; dòng cha "subtest failed" không thành ca đỏ thứ hai; chạy lại gán cho ca ngay trước', () => {
  const file = path.join(ROOT, 'cong-no-web-handoff', 'preview', 'test-mau-browser.js');
  const rows = [
    { kind: 'pass', file, name: 'xanh', type: 'test' },
    { kind: 'retry', file, name: 'Thử lại ca này vì ERR_NO_BUFFER_SPACE (x)' },
    { kind: 'fail', file, name: 'con đỏ', type: 'test', failureType: 'testCodeFailure', error: 'hỏng' },
    { kind: 'fail', file, name: 'cha', type: 'test', failureType: 'subtestsFailed', error: '1 subtest failed' },
  ];
  assert.deepEqual(summarizeRound(rows), {
    tests: 2,
    fails: [{ file: 'test-mau-browser.js', name: 'con đỏ', error: 'hỏng', failureType: 'testCodeFailure' }],
    retries: [{ file: 'test-mau-browser.js', name: 'xanh' }],
  });
});

test('bảng: ca đỏ nhiều lần lên trước, giữ lỗi lần đầu; không ca nào đỏ thì nói rõ', () => {
  const fails = [{ file: 'b.js', name: 'B', error: 'e1' }, { file: 'a.js', name: 'A', error: 'e2' }, { file: 'b.js', name: 'B', error: 'e3' }];
  assert.deepEqual(tally(fails), [{ file: 'b.js', name: 'B', count: 2, error: 'e1' }, { file: 'a.js', name: 'A', count: 1, error: 'e2' }]);
  const green = { label: 'máy', rounds: 2, perRound: [{ round: 1, exit: 0, tests: 3, fails: [] }, { round: 2, exit: 0, tests: 3, fails: [] }], table: [], retryTable: [] };
  assert.match(renderMarkdown(green), /2 lượt, 0 lượt đỏ[\s\S]*Không ca nào đỏ\./);
  const hung = { ...green, perRound: [green.perRound[0], { round: 2, exit: 1, timedOut: true, tests: 1, fails: [] }] };
  assert.match(renderMarkdown(hung), /1 lượt đỏ[\s\S]*Lượt 2 \(mã 1, quá giờ\) hỏng mà không có ca đỏ/);
  const empty = { ...green, perRound: [green.perRound[0], { round: 2, exit: 0, tests: 0, fails: [] }] };
  assert.match(renderMarkdown(empty), /1 lượt đỏ[\s\S]*Lượt 2 \(không chạy ca nào\)/);
});

test('gộp hai máy: mỗi máy một cột đỏ/lượt, ô có dấu | không vỡ bảng', () => {
  const one = (label, count) => ({ label, rounds: 10, perRound: [{ round: 1, exit: count ? 1 : 0, tests: 5, fails: [] }],
    table: count ? [{ file: 'x.js', name: 'ca | có gạch', count, error: 'lỗi' }] : [], retryTable: [] });
  const text = renderMerged([one('ubuntu', 2), one('windows', 0)]);
  assert.match(text, /\| ubuntu \| 10 \| 1 \| 5 \|/);
  assert.match(text, /\| ca \\\| có gạch \| x\.js \| 2\/10 \| 0\/10 \| lỗi \|/);
  assert.match(renderMerged([one('ubuntu', 0)]), /Không ca nào đỏ ở máy nào\./);
});

test('chạy thật một lượt trên file mẫu: thoát mã 1, summary.json có đúng ca đỏ', () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'flaky-repeat-'));
  try {
    const sample = path.join(dir, 'test-mau.js');
    fs.writeFileSync(sample, [
      "const { test } = require('node:test');",
      "test('xanh', () => {});",
      "test('đỏ', () => { throw new Error('hỏng thật'); });",
      "test('bỏ qua', { skip: true }, () => {});",
    ].join('\n'));
    const out = path.join(dir, 'out');
    // Bỏ NODE_TEST_CONTEXT: còn biến này thì `node --test` con tưởng mình nằm trong test khác và không chạy file nào.
    const { NODE_TEST_CONTEXT: _inTest, ...env } = process.env;
    const run = spawnSync(process.execPath, [path.join(__dirname, 'flaky-repeat.js'), '--rounds', '1', '--out', out, sample],
      { cwd: ROOT, encoding: 'utf8', env: { ...env, FLAKY_LABEL: 'mẫu' } });
    assert.equal(run.status, 1, run.stdout + run.stderr);
    const summary = JSON.parse(fs.readFileSync(path.join(out, 'summary.json'), 'utf8'));
    assert.equal(summary.label, 'mẫu');
    assert.equal(summary.perRound[0].tests, 2);
    assert.deepEqual(summary.table.map(row => [row.name, row.count, row.error]), [['đỏ', 1, 'hỏng thật']]);
    assert.ok(fs.existsSync(path.join(out, 'round-1.log')));
  } finally {
    fs.rmSync(dir, { recursive: true, force: true });
  }
});
