import assert from 'node:assert/strict';
import { mkdtempSync, mkdirSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import test from 'node:test';
import { checkFiles, countLines, loadPolicy } from './check-loc.mjs';

test('đếm dòng LF và CRLF, không tính newline cuối thành dòng rỗng', () => {
  assert.equal(countLines('a\nb\n'), 2);
  assert.equal(countLines('a\r\nb\r\n'), 2);
  assert.equal(countLines(''), 0);
});

test('nhận file hợp lệ và từ chối file quá ngưỡng hoặc exception tăng thêm', () => {
  const root = mkdtempSync(join(tmpdir(), 'webdebit-loc-'));
  try {
    mkdirSync(join(root, 'scripts'));
    writeFileSync(join(root, 'scripts/valid.js'), 'a\nb\n');
    writeFileSync(join(root, 'scripts/new.js'), 'a\nb\nc\nd\n');
    const policy = { limit: 3, grandfathered: { 'scripts/new.js': { maxLines: 4, reason: 'baseline' } } };
    assert.deepEqual(checkFiles(root, ['scripts/valid.js', 'scripts/new.js'], policy), []);
    policy.grandfathered = {};
    assert.deepEqual(checkFiles(root, ['scripts/new.js'], policy), ['scripts/new.js: 4 dòng > 3']);
    policy.grandfathered = { 'scripts/new.js': { maxLines: 3, reason: 'baseline' } };
    assert.equal(checkFiles(root, ['scripts/new.js'], policy).length, 1);
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});

test('thiếu hoặc sai policy thì fail closed', () => {
  const root = mkdtempSync(join(tmpdir(), 'webdebit-loc-policy-'));
  try {
    assert.throws(() => loadPolicy(join(root, 'missing.json')));
    const path = join(root, 'policy.json');
    writeFileSync(path, '{"limit":300,"grandfathered":{"scripts/old.js":{"maxLines":350}}}');
    assert.throws(() => loadPolicy(path), /exception không hợp lệ/);
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});
