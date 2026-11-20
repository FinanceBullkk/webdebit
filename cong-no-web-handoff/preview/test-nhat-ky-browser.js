const assert = require('node:assert/strict');
const http = require('node:http');
const fs = require('node:fs');
const path = require('node:path');
const { launchShared, test } = require('./shared-browser.js');

// NHAT-KY-01: trang Nhật ký công việc, chỉ đọc GET /api/v7/nhat-ky. Dữ liệu giả.
const change = (n, title, lane, hhmm, add = 10, del = 2) => [`#${n}`, title, lane, add, del, 1, hhmm];
const BODY = {
  available: true, repo: 'x/y', checked_at: '20/11/2026 09:30', error: null, from: '2026-11-18', to: '2026-11-20',
  highlights: [{ area: 'doi-xe', title: 'Đội xe', text: 'Chi phí, thu cước.' }, { area: 'so-khach', title: 'Sổ khách trên web', text: 'Chuyến, phiếu thu.' }],
  next: ['Đội xe: điều độ'],
  days: {
    '2026-11-18': { headline: 'Module Đội xe', items: [['doi-xe', 'Ghi chi phí xe trên web.']],
      changes: [change(1, 'Đội xe: phiếu chi', 'doi-xe', '09:00'), change(2, 'Sổ khách: phiếu thu gọn', 'so-khach', '22:30')] },
    '2026-11-20': { headline: 'Điều độ xe', items: [['doi-xe', 'Phân công xe theo booking.'], ['quan-ly', 'Khách mới có nhãn Mới.']],
      changes: [change(3, 'Đội xe: phân công', 'doi-xe', '08:10'), change(4, 'Khách mới: nhãn Mới', 'quan-ly', '10:20'),
        change(5, 'Nhật ký triển khai: x lên hao', 'an-toan', '10:30')] },
  },
};

function makeServer(state) {
  return http.createServer((request, response) => {
    const url = new URL(request.url, 'http://x'), route = url.pathname;
    const send = (status, type, body) => { response.writeHead(status, { 'Content-Type': type }); response.end(body); };
    const out = (body, status = 200) => send(status, 'application/json', JSON.stringify(body));
    state.calls.push(`${request.method} ${route}`);
    if (route === '/api/v7/nhat-ky') return state.down ? out({ error: 'X', message: 'lỗi' }, 503) : out(state.body);
    if (route === '/api/v7/customers') return out({ customers: [] });
    if (route.startsWith('/api/')) return out({}, 503);
    const file = path.join(__dirname, route.replace(/^\//, ''));
    if (!file.startsWith(__dirname) || !fs.existsSync(file)) return send(404, 'text/plain', 'not found');
    const type = file.endsWith('.html') ? 'text/html' : file.endsWith('.css') ? 'text/css' : 'text/javascript';
    return send(200, type, fs.readFileSync(file));
  });
}

async function withPage(state, fn, { viewport = { width: 1280, height: 800 } } = {}) {
  const shared = { calls: [], down: false, body: BODY, ...state };
  const server = makeServer(shared);
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const browser = await launchShared();
  try {
    const page = await (await browser.newContext({ viewport })).newPage();
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.goto(`http://127.0.0.1:${server.address().port}/nhat-ky-cong-viec.html`);
    await fn(page, shared);
    assert.deepEqual(errors, []);
    assert.deepEqual(shared.calls.filter(call => call.startsWith('POST')), [], 'trang chỉ xem không gửi lệnh ghi');
  } finally {
    await browser.close();
    server.close();
  }
}

test('Nhật ký công việc: hôm nay, thẻ ghim, lịch, lọc chéo theo mảng, bỏ PR nhật ký triển khai, mở chi tiết ngày', () => withPage({}, async page => {
  await page.locator('body[data-loaded]').waitFor({ state: 'attached' });
  assert.match(await page.locator('#todayHead').innerText(), /20\/11 · Điều độ xe$/);
  assert.equal(await page.locator('#todayNum').innerText(), '2');   // PR "Nhật ký triển khai" không đếm
  assert.match(await page.locator('#liveTxt').innerText(), /Trực tiếp · GitHub lúc 20\/11\/2026 09:30/);
  assert.equal(await page.locator('#pins .pin').count(), 2);
  assert.match(await page.locator('#pmeta').innerText(), /4 thay đổi/);
  assert.equal(await page.locator('#cg button.sq').count(), 2);
  assert.equal(await page.locator('.app-nav .nav-extra a.active').innerText(), 'Nhật ký công việc');
  assert.equal(await page.locator('.app-nav nav a').count(), 9, 'khối chín mục giữ nguyên');

  await page.locator('#pins .pin').first().click();   // thẻ Đội xe: lọc cả trang
  assert.match(await page.locator('#fbar').innerText(), /Đang xem 2 thay đổi/);
  assert.match(await page.locator('#fbar').innerText(), /Đội xe/);
  await page.locator('#fbar .link', { hasText: 'Xóa lọc' }).click();
  assert.equal(await page.locator('#fbar').isHidden(), true);

  await page.locator('#todayLink .link').click();
  await page.locator('#detail.open').waitFor();
  assert.match(await page.locator('#detail').innerText(), /Phân công xe theo booking\./);
  await page.keyboard.press('Escape');
  await page.locator('.tab', { hasText: 'Cây công việc' }).click();
  assert.equal(await page.locator('#tree .row').count(), 2);
}));

test('Nhật ký công việc: máy chủ lỗi thì báo, tự đọc lại khi tab quay lại; không cuộn ngang ở 1280 và 390', async () => {
  await withPage({ down: true }, async (page, shared) => {
    await page.locator('#error:not([hidden])').waitFor();
    assert.match(await page.locator('#error').innerText(), /Chưa đọc được Nhật ký công việc/);
    shared.down = false;
    await page.evaluate(() => document.dispatchEvent(new Event('visibilitychange')));
    await page.locator('body[data-loaded]').waitFor({ state: 'attached' });
    assert.equal(await page.locator('#error').isHidden(), true);
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth));
  });
  await withPage({}, async page => {
    await page.locator('body[data-loaded]').waitFor({ state: 'attached' });
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth));
  }, { viewport: { width: 390, height: 844 } });
});
