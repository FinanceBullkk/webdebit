// Thử lại khi Chromium báo ERR_NO_BUFFER_SPACE: chỉ đúng lỗi này, một lần, không nuốt lỗi khác. Dữ liệu giả, không chạm DB hay Sheet.
const { test } = require('node:test');
const assert = require('node:assert/strict');
const { EventEmitter } = require('node:events');
const fs = require('node:fs');
const http = require('node:http');
const path = require('node:path');
const { launchShared, runWithRetry, watchNetwork } = require('./shared-browser.js');

const NO_BUFFER = 'net::ERR_NO_BUFFER_SPACE';
const failedRequest = (url, errorText) => ({ url: () => url, failure: () => ({ errorText }) });

// Một context giả: phát sự kiện như Playwright khi một request hỏng.
function fakeContext() {
  return watchNetwork(new EventEmitter());
}

test('ca đỏ kèm ERR_NO_BUFFER_SPACE ở tài nguyên con: chạy lại một lần, xanh, có ghi chú để còn đếm được', async () => {
  const context = fakeContext();
  const notes = [];
  let runs = 0;
  await runWithRetry(async () => {
    runs += 1;
    if (runs === 1) {
      context.emit('requestfailed', failedRequest('http://127.0.0.1:1/a.css', NO_BUFFER));
      assert.fail('nút cao 27px');
    }
  }, note => notes.push(note));
  assert.equal(runs, 2);
  assert.equal(notes.length, 1);
  assert.match(notes[0], /ERR_NO_BUFFER_SPACE/);
  assert.match(notes[0], /a\.css/);
});

test('page.goto ném ERR_NO_BUFFER_SPACE: chạy lại dù chưa nhận sự kiện requestfailed', async () => {
  let runs = 0;
  await runWithRetry(async () => {
    runs += 1;
    if (runs === 1) throw new Error(`page.goto: ${NO_BUFFER} at http://127.0.0.1:1/`);
  }, () => {});
  assert.equal(runs, 2);
});

test('ca xanh nhưng có ERR_NO_BUFFER_SPACE (đo trên trang thiếu CSS): vẫn chạy lại, kết quả xanh đó không đáng tin', async () => {
  const context = fakeContext();
  let runs = 0;
  await runWithRetry(async () => {
    runs += 1;
    if (runs === 1) context.emit('requestfailed', failedRequest('http://127.0.0.1:1/a.css', NO_BUFFER));
  }, () => {});
  assert.equal(runs, 2);
});

test('ca đỏ vì lý do khác: không chạy lại, giữ nguyên lỗi', async () => {
  const context = fakeContext();
  const notes = [];
  let runs = 0;
  await assert.rejects(runWithRetry(async () => {
    runs += 1;
    context.emit('requestfailed', failedRequest('http://127.0.0.1:1/api', 'net::ERR_FAILED'));
    assert.equal(1, 2, 'lỗi thật của code');
  }, note => notes.push(note)), /lỗi thật của code/);
  assert.equal(runs, 1);
  assert.deepEqual(notes, []);
});

test('lượt chạy lại vẫn đỏ: báo lỗi của lượt đó, không chạy thêm', async () => {
  let runs = 0;
  await assert.rejects(runWithRetry(async () => {
    runs += 1;
    throw new Error(`page.goto: ${NO_BUFFER} lượt ${runs}`);
  }, () => {}), /lượt 2/);
  assert.equal(runs, 2);
});

test('lỗi mạng ở lượt trước không tính sang ca sau', async () => {
  const context = fakeContext();
  await runWithRetry(async () => { context.emit('requestfailed', failedRequest('http://127.0.0.1:1/a.css', NO_BUFFER)); }, () => {});
  let runs = 0;
  await runWithRetry(async () => { runs += 1; }, () => {});
  assert.equal(runs, 1);
});

test('Chromium thật: launchShared gắn sẵn theo dõi; request bị cắt kiểu khác không được chạy lại', async () => {
  const server = http.createServer((req, res) => res.end('<!doctype html><title>x</title><p>ok</p>'));
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const url = `http://127.0.0.1:${server.address().port}/`;
  const browser = await launchShared();
  try {
    // Không ép được Chromium sinh lỗi -176 nên phát sự kiện giả lên context thật, chứng minh launchShared đã gắn theo dõi.
    let runs = 0;
    await runWithRetry(async () => {
      runs += 1;
      const context = await browser.newContext();
      if (runs === 1) context.emit('requestfailed', failedRequest(url, NO_BUFFER));
    }, () => {});
    assert.equal(runs, 2);
    // Lỗi mạng thật của Chromium, khác mã: giữ nguyên lỗi, một lượt.
    runs = 0;
    await assert.rejects(runWithRetry(async () => {
      runs += 1;
      const page = await browser.newPage();
      await page.route('**/*', route => route.abort('failed'));
      await page.goto(url);
    }, () => {}), /net::ERR_FAILED/);
    assert.equal(runs, 1);
  } finally {
    await browser.close();
    server.close();
  }
});

test('mọi file test trình duyệt lấy `test` từ shared-browser.js để được thử lại đúng lỗi này', () => {
  const files = [
    ...fs.readdirSync(__dirname).filter(name => /^test-.+-browser\.js$/.test(name) && name !== path.basename(__filename)).map(name => path.join(__dirname, name)),
    path.join(__dirname, '..', 'tests', 'test-viewer-browser.js'),
  ];
  assert.ok(files.length > 20);
  const direct = files.filter(file => /\btest\b[^;\n]*=\s*require\(['"]node:test['"]\)/.test(fs.readFileSync(file, 'utf8'))).map(file => path.basename(file));
  assert.deepEqual(direct, []);
});
