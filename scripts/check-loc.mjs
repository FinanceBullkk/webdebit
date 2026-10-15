import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';

const defaultRoot = resolve(fileURLToPath(new URL('..', import.meta.url)));
const sourcePath = /^(cong-no-web-handoff|scripts)\/.+\.(py|js|mjs|css|sql|html)$/;

export function countLines(content) {
  if (content.length === 0) return 0;
  const lines = content.split(/\r\n|\n|\r/).length;
  return /\r\n$|\n$|\r$/.test(content) ? lines - 1 : lines;
}

export function loadPolicy(path) {
  const policy = JSON.parse(readFileSync(path, 'utf8'));
  if (!Number.isInteger(policy.limit) || policy.limit < 1 ||
      !policy.grandfathered || typeof policy.grandfathered !== 'object') {
    throw new Error('LOC policy thiếu limit hoặc grandfathered hợp lệ');
  }
  for (const [file, exception] of Object.entries(policy.grandfathered)) {
    if (!sourcePath.test(file) || !Number.isInteger(exception.maxLines) ||
        exception.maxLines < policy.limit || !exception.reason?.trim()) {
      throw new Error(`LOC exception không hợp lệ: ${file}`);
    }
  }
  return policy;
}

export function checkFiles(root, files, policy) {
  const violations = [];
  for (const file of files) {
    if (!sourcePath.test(file)) continue;
    const lines = countLines(readFileSync(resolve(root, file), 'utf8'));
    const ceiling = policy.grandfathered[file]?.maxLines ?? policy.limit;
    if (lines > ceiling) violations.push(`${file}: ${lines} dòng > ${ceiling}`);
  }
  return violations;
}

function trackedFiles(root) {
  const result = spawnSync('git', ['ls-files', '-z', '--cached', '--others', '--exclude-standard'], {
    cwd: root, encoding: 'utf8', shell: false,
  });
  if (result.status !== 0) throw new Error(result.stderr || 'git ls-files thất bại');
  return [...new Set(result.stdout.split('\0').filter(Boolean))];
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  try {
    const policy = loadPolicy(resolve(defaultRoot, 'scripts/loc-baseline.json'));
    const violations = checkFiles(defaultRoot, trackedFiles(defaultRoot), policy);
    if (violations.length) {
      for (const message of violations) process.stderr.write(`${message}\n`);
      process.exitCode = 1;
    } else {
      process.stdout.write(`LOC đạt: file mới <= ${policy.limit} dòng; file cũ không vượt baseline.\n`);
    }
  } catch (error) {
    process.stderr.write(`Không kiểm được LOC: ${error.message}\n`);
    process.exitCode = 1;
  }
}
