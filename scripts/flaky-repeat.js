#!/usr/bin/env node
// Chạy một bộ test JS nhiều lượt để bắt test chập chờn, rồi gom bảng "ca nào đỏ mấy lần" (CHAP-CHON-01).
//
//   node scripts/flaky-repeat.js                          bộ browser, 10 lượt, log ở .flaky/
//   node scripts/flaky-repeat.js --rounds 3 --out <thư mục>
//   node scripts/flaky-repeat.js --rounds 5 cong-no-web-handoff/preview/test-may-chay-browser.js
//   node scripts/flaky-repeat.js --merge <thư mục 1> <thư mục 2>   gộp bảng của nhiều máy (job đêm dùng)
//
// Mỗi lượt gọi `node --test` y như scripts/run-tests.js (các file chạy song song), kèm reporter
// scripts/flaky-reporter.js ghi từng ca ra <out>/round-<i>.jsonl; log đọc được ở <out>/round-<i>.log.
// Xong in bảng Markdown ra stdout và <out>/summary.md, ghi <out>/summary.json. Có ca đỏ, hay một lượt
// thoát mã khác 0 (treo quá --round-minutes, file hỏng) thì thoát mã 1. Không chạy lại ca đỏ: mục đích là
// đếm, không che. Biến WEBDEBIT_TEST_CPU_SLOWDOWN (shared-browser.js) làm trang chậm đi để lộ ca chờ sai.
// Cách đọc kết quả: docs/development.md, mục "Job đêm tìm test chập chờn".

const { spawnSync } = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');

const ROOT = path.resolve(__dirname, '..');

function parseArgs(argv) {
  const options = { rounds: 10, roundMinutes: 20, out: path.join(ROOT, '.flaky'), files: [], merge: null };
  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    if (arg === '--rounds') options.rounds = Number(argv[++i]);
    else if (arg === '--round-minutes') options.roundMinutes = Number(argv[++i]);
    else if (arg === '--out') options.out = path.resolve(argv[++i]);
    else if (arg === '--merge') options.merge = [];
    else if (arg.startsWith('--')) throw new Error(`Không hiểu tham số ${arg}`);
    else (options.merge ?? options.files).push(arg);
  }
  if (!Number.isInteger(options.rounds) || options.rounds < 1) throw new Error('--rounds phải là số nguyên ≥ 1');
  if (!(options.roundMinutes > 0)) throw new Error('--round-minutes phải lớn hơn 0');
  return options;
}

function browserSuite() {
  const listed = spawnSync(process.execPath, [path.join(ROOT, 'scripts/run-tests.js'), 'browser', '--list'], { cwd: ROOT, encoding: 'utf8' });
  if (listed.status !== 0) throw new Error(`Không lấy được danh sách test browser: ${listed.stderr}`);
  return listed.stdout.split('\n').map(line => line.trim()).filter(Boolean);
}

// Tên file tương đối, dấu "/" để bảng của Windows và Ubuntu gộp được với nhau.
function shortFile(file) {
  if (!file) return '(không rõ file)';
  const relative = path.isAbsolute(file) ? path.relative(ROOT, file) : file;
  return relative.split(path.sep).join('/').replace(/^cong-no-web-handoff\/preview\//, '');
}

function readRound(jsonl) {
  if (!fs.existsSync(jsonl)) return [];
  return fs.readFileSync(jsonl, 'utf8').split('\n').filter(Boolean).map(line => JSON.parse(line));
}

// Gom các dòng của một lượt: ca lá đỏ (bỏ dòng cha chỉ báo "subtest failed"), ca chạy lại vì ERR_NO_BUFFER_SPACE.
function summarizeRound(rows) {
  const fails = [];
  const retries = [];
  let tests = 0;
  let previous = null;
  for (const row of rows) {
    if (row.kind === 'retry') {
      // Chẩn đoán của một ca đến ngay sau dòng pass/fail của chính ca đó.
      if (previous) retries.push(previous);
      continue;
    }
    previous = { file: shortFile(row.file), name: row.name };
    if (row.type === 'suite' || row.failureType === 'subtestsFailed') continue;
    tests += 1;
    if (row.kind === 'fail') fails.push({ ...previous, error: row.error, failureType: row.failureType });
  }
  return { tests, fails, retries };
}

function escapeCell(text) {
  return String(text ?? '').replace(/\|/g, '\\|').replace(/\s+/g, ' ').trim();
}

function tally(list) {
  const map = new Map();
  for (const item of list) {
    const key = `${item.file}\u0000${item.name}`;
    const row = map.get(key) ?? { file: item.file, name: item.name, count: 0, error: item.error };
    row.count += 1;
    map.set(key, row);
  }
  return [...map.values()].sort((a, b) => b.count - a.count || a.file.localeCompare(b.file) || a.name.localeCompare(b.name));
}

// Lượt không chạy ca nào cũng tính là hỏng: thà báo nhầm còn hơn xanh vì không kiểm gì.
const brokenRound = round => round.exit !== 0 || round.tests === 0;
const redRounds = result => result.perRound.filter(round => round.fails.length || brokenRound(round));

function renderMarkdown(result) {
  const { label, rounds, perRound, table, retryTable } = result;
  const lines = [
    `### Test chập chờn — ${label}`,
    '',
    `${rounds} lượt, ${redRounds(result).length} lượt đỏ. Số ca mỗi lượt: ${perRound.map(round => round.tests).join('/')}.`,
    '',
  ];
  const silent = perRound.filter(round => brokenRound(round) && !round.fails.length);
  if (!table.length && !silent.length) {
    lines.push('Không ca nào đỏ.');
  } else {
    if (table.length) {
      lines.push('| Ca | File | Đỏ | Lỗi đầu tiên |', '|---|---|---|---|');
      for (const row of table) lines.push(`| ${escapeCell(row.name)} | ${escapeCell(row.file)} | ${row.count}/${rounds} | ${escapeCell(row.error)} |`);
    }
    const why = round => (round.exit === 0 ? 'không chạy ca nào' : `mã ${round.exit}${round.timedOut ? ', quá giờ' : ''}`);
    if (silent.length) lines.push('', `Lượt ${silent.map(round => `${round.round} (${why(round)})`).join(', ')} hỏng mà không có ca đỏ: xem round-<lượt>.log.`);
  }
  if (retryTable.length) {
    lines.push('', 'Chạy lại một lần vì ERR_NO_BUFFER_SPACE (shared-browser.js), không tính là đỏ:', '');
    for (const row of retryTable) lines.push(`- ${escapeCell(row.name)} (${escapeCell(row.file)}): ${row.count} lần`);
  }
  return `${lines.join('\n')}\n`;
}

// Gộp summary.json của nhiều máy thành một bảng: mỗi máy một cột "đỏ/lượt".
function renderMerged(results) {
  const labels = results.map(result => result.label);
  const rows = new Map();
  results.forEach((result, index) => {
    for (const row of result.table) {
      const key = `${row.file}\u0000${row.name}`;
      const merged = rows.get(key) ?? { file: row.file, name: row.name, error: row.error, counts: labels.map(() => 0) };
      merged.counts[index] = row.count;
      rows.set(key, merged);
    }
  });
  const sorted = [...rows.values()].sort((a, b) => b.counts.reduce((x, y) => x + y) - a.counts.reduce((x, y) => x + y) || a.file.localeCompare(b.file));
  const lines = ['## Test chập chờn — gộp các máy', '', '| Máy | Lượt | Lượt đỏ | Ca mỗi lượt |', '|---|---|---|---|'];
  for (const result of results) lines.push(`| ${escapeCell(result.label)} | ${result.rounds} | ${redRounds(result).length} | ${Math.max(0, ...result.perRound.map(round => round.tests))} |`);
  lines.push('');
  if (!sorted.length) {
    lines.push(results.some(result => redRounds(result).length) ? 'Không ca nào đỏ, nhưng có lượt hỏng: xem bảng từng máy.' : 'Không ca nào đỏ ở máy nào.');
  } else {
    lines.push(`| Ca | File | ${labels.map(escapeCell).join(' | ')} | Lỗi đầu tiên |`, `|---|---|${labels.map(() => '---|').join('')}---|`);
    for (const row of sorted) {
      lines.push(`| ${escapeCell(row.name)} | ${escapeCell(row.file)} | ${row.counts.map((count, index) => `${count}/${results[index].rounds}`).join(' | ')} | ${escapeCell(row.error)} |`);
    }
  }
  return `${lines.join('\n')}\n`;
}

function runRounds(options) {
  const files = options.files.length ? options.files : browserSuite();
  const label = process.env.FLAKY_LABEL || `${process.platform} node ${process.version}`;
  fs.mkdirSync(options.out, { recursive: true });
  const perRound = [];
  for (let round = 1; round <= options.rounds; round += 1) {
    const jsonl = path.join(options.out, `round-${round}.jsonl`);
    const log = path.join(options.out, `round-${round}.log`);
    fs.rmSync(jsonl, { force: true });
    const started = Date.now();
    // Reporter phải là đường dẫn tương đối: trên Windows "D:\…" bị hiểu nhầm là URL có scheme "d:".
    const run = spawnSync(process.execPath, [
      '--test',
      // Ca treo thì đỏ với tên của nó sau 3 phút, không giữ cả lượt tới --round-minutes. Ca chậm nhất đo được
      // khoảng 15 giây (CPU trang chậm 4 lần, 18/11/2026), nên 3 phút chỉ bắt ca treo thật.
      `--test-timeout=${3 * 60_000}`,
      '--test-reporter=spec', `--test-reporter-destination=${log}`,
      '--test-reporter=./scripts/flaky-reporter.js', `--test-reporter-destination=${jsonl}`,
      ...files,
    ], { cwd: ROOT, stdio: ['ignore', 'inherit', 'inherit'], timeout: options.roundMinutes * 60_000, killSignal: 'SIGKILL' });
    const summary = {
      round,
      exit: run.status ?? 1,
      timedOut: run.error?.code === 'ETIMEDOUT',
      seconds: Math.round((Date.now() - started) / 1000),
      ...summarizeRound(readRound(jsonl)),
    };
    perRound.push(summary);
    const names = summary.fails.map(fail => `\n    ✖ ${fail.file} › ${fail.name}: ${fail.error}`).join('');
    console.log(`Lượt ${round}/${options.rounds}: ${summary.tests} ca, ${summary.fails.length} đỏ, ${summary.retries.length} chạy lại, ${summary.seconds} giây`
      + `${summary.exit !== 0 && !summary.fails.length ? `, thoát mã ${summary.exit}${summary.timedOut ? ' (quá giờ)' : ''}` : ''}${names}`);
  }
  const result = {
    label,
    rounds: options.rounds,
    perRound,
    table: tally(perRound.flatMap(round => round.fails)),
    retryTable: tally(perRound.flatMap(round => round.retries)),
  };
  const markdown = renderMarkdown(result);
  fs.writeFileSync(path.join(options.out, 'summary.json'), `${JSON.stringify(result, null, 2)}\n`);
  fs.writeFileSync(path.join(options.out, 'summary.md'), markdown);
  console.log(`\n${markdown}`);
  return redRounds(result).length ? 1 : 0;
}

function merge(dirs) {
  const results = dirs.map(dir => JSON.parse(fs.readFileSync(path.join(dir, 'summary.json'), 'utf8')));
  if (!results.length) throw new Error('--merge cần ít nhất một thư mục có summary.json');
  process.stdout.write(renderMerged(results));
  return results.some(result => redRounds(result).length) ? 1 : 0;
}

function main() {
  const options = parseArgs(process.argv.slice(2));
  process.exit(options.merge ? merge(options.merge) : runRounds(options));
}

if (require.main === module) main();

module.exports = { renderMarkdown, renderMerged, summarizeRound, tally };
