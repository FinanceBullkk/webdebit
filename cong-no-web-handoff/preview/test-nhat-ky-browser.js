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

test('Nhật ký công việc: tuần, bảng mảng × tuần, từng ngày lời thường, lọc chéo, bỏ PR nhật ký triển khai', () => withPage({}, async page => {
  await page.locator('body[data-loaded]').waitFor({ state: 'attached' });
  assert.equal(await page.locator('#weekTitle').innerText(), 'Tuần 16/11 – 22/11');
  assert.equal(await page.locator('#weekNum').innerText(), '4');   // PR "Nhật ký triển khai" không đếm
  assert.match(await page.locator('#liveTxt').innerText(), /Trực tiếp · GitHub lúc 20\/11\/2026 09:30/);
  assert.equal(await page.locator('nav.admin-tabs a.active').innerText(), 'Nhật ký');   // QUYEN-02: thẻ trong dải Quản trị
  assert.equal(await page.locator('.app-nav nav a').count(), 6, 'năm trang làm sổ + Quản trị');
  assert.equal(await page.locator('#matrix tbody tr').count(), 6, 'sáu mảng');
  assert.match(await page.locator('#matrix').innerText(), /Chi phí, thu cước\./, 'mô tả việc lớn nằm dưới tên mảng');
  assert.match(await page.locator('#next').innerText(), /Đội xe: điều độ/);

  // Từng ngày: mới nhất trước, câu lời thường hiện sẵn, danh sách kỹ thuật thu gọn
  assert.deepEqual(await page.locator('.nk-day').evaluateAll(ns => ns.map(n => n.dataset.day)), ['2026-11-20', '2026-11-18']);
  const first = page.locator('.nk-day').first();
  assert.match(await first.locator('h3').innerText(), /^Điều độ xe$/);
  assert.match(await first.locator('.items').innerText(), /Phân công xe theo booking\./);
  assert.equal(await first.locator('details.tech').evaluate(d => d.open), false);
  assert.match(await first.locator('.count').innerText(), /^2 thay đổi/);

  // Bấm tên mảng Đội xe: cả trang lọc theo
  await page.locator('#matrix .lane', { hasText: 'Đội xe' }).click();
  assert.match(await page.locator('#fbar').innerText(), /Đội xe/);
  assert.match(await page.locator('#feedTitle').innerText(), /2 thay đổi khớp lọc/);
  assert.equal(await page.locator('#weekNum').innerText(), '2');
  assert.doesNotMatch(await page.locator('.nk-day').first().innerText(), /Khách mới có nhãn Mới/);

  // Thêm lọc giờ bằng cột 22h của biểu đồ giờ: chỉ ngày 18/11 còn, danh sách kỹ thuật mở sẵn
  await page.locator('#matrix .lane', { hasText: 'Đội xe' }).click();   // bấm lại là bỏ lọc mảng
  assert.equal(await page.locator('#fbar .fchip').count(), 0);
  await page.locator('.hist rect.pick').nth(2).click();   // các cột có dữ liệu: 8h, 9h, 10h, 22h
  assert.match(await page.locator('#fbar').innerText(), /10h–11h/);
  await page.locator('#fbar .link', { hasText: 'Xóa lọc' }).click();
  await page.locator('.hist rect.pick').nth(3).click();
  assert.match(await page.locator('#fbar').innerText(), /22h–23h/);
  assert.deepEqual(await page.locator('.nk-day').evaluateAll(ns => ns.map(n => n.dataset.day)), ['2026-11-18']);
  assert.equal(await page.locator('.nk-day details.tech').evaluate(d => d.open), true);
  assert.match(await page.locator('.nk-day .tech').innerText(), /Sổ khách: phiếu thu gọn/);
  await page.keyboard.press('Escape');
  assert.equal(await page.locator('#fbar .fchip').count(), 0);

  // Giờ làm: 1/4 thay đổi ngoài giờ (22:30)
  assert.equal(await page.locator('#offPct').innerText(), '25%');
}));

test('Nhật ký công việc: Sáng / Tối / Theo máy, nhớ lựa chọn sau khi tải lại', () => withPage({}, async page => {
  await page.locator('body[data-loaded]').waitFor({ state: 'attached' });
  const theme = () => page.evaluate(() => document.documentElement.dataset.nkTheme);
  const bg = () => page.evaluate(() => getComputedStyle(document.body).backgroundColor);
  await page.emulateMedia({ colorScheme: 'light' });
  assert.equal(await theme(), 'light');
  assert.equal(await page.locator('#mode button[aria-pressed="true"]').innerText(), 'Theo máy');
  await page.emulateMedia({ colorScheme: 'dark' });   // Theo máy: máy đổi sang tối thì trang đổi theo
  await page.waitForFunction(() => document.documentElement.dataset.nkTheme === 'dark', null, { timeout: 3000 });
  assert.equal(await bg(), 'rgb(13, 17, 23)');
  await page.emulateMedia({ colorScheme: 'light' });
  await page.locator('#mode button', { hasText: /^Tối$/ }).click();
  assert.equal(await theme(), 'dark');
  await page.reload();
  await page.locator('body[data-loaded]').waitFor({ state: 'attached' });
  assert.equal(await theme(), 'dark', 'lựa chọn Tối còn sau khi tải lại dù máy đang sáng');
  assert.equal(await page.locator('#mode button[aria-pressed="true"]').innerText(), 'Tối');
  await page.locator('#mode button', { hasText: 'Sáng' }).click();
  assert.equal(await theme(), 'light');
  assert.equal(await bg(), 'rgb(233, 236, 240)');
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
