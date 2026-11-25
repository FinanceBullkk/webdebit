const assert = require('node:assert/strict');
const http = require('node:http');
const fs = require('node:fs');
const path = require('node:path');
const { launchShared, test } = require('./shared-browser.js');

// BAO-CAO-THANG-01: tab Báo cáo tháng, chỉ xem. Dữ liệu giả cùng dạng GET /api/v7/report/month.
const counts = extra => ({ booking: 2, sheet: 2, web: 2, thieu: 0, khong_booking: 0, lech_ngay: 0, khong_ngay: 0, chep: 0, ngoai: 0,
  chi_web: 0, web_thieu: 0, web_chua: 0, thieu_web: 0, issues: 0, amount_vnd: '170000000', ...extra });
const trip = (cont, status, extra = {}) => ({ tab: 'KHACH GIA A', row: 5, block: '2026-10', cont, family: 'BIEN', amount_vnd: '85000000',
  date: '2026-10-03', status, booking: { date: '2026-10-03', owner: 'CHU HANG GIA', ref: 'BKGIA1' }, web: { date: '2026-10-03', source: 'web' }, ...extra });
const REPORT = month => ({
  month, state: 'ok', checked_at: '2026-11-16T10:09:00+07:00', now: '2026-11-16T10:30:00+07:00', start: '2025-12', end: '2026-11',
  current: month === '2026-11', before_book: 0,
  totals: { BIEN: counts({ booking: 263, sheet: 261, web: 260, thieu: 2, web_thieu: 1, web_chua: 3 }), BO: counts({ booking: 201, sheet: 201, web: 201 }),
    ALL: counts({ booking: 464, sheet: 462, web: 461, thieu: 2, web_thieu: 1, web_chua: 3 }) },
  customers: [
    { name: 'KHACH GIA A', owner: null, book_id: 7, commodity: 'Dừa', families: ['BIEN'], ...counts({ booking: 3, thieu: 1, chep: 1, issues: 1 }),
      rows: [trip('GIAU1000001', 'khop'), trip('GIAU1000002', 'khop', { web: null }),
        trip('GIAU1000003', 'thieu', { row: null, block: null, amount_vnd: null, date: null, web: null, booking: { date: '2026-10-29', owner: 'CHU HANG GIA', ref: 'BKGIA2' } }),
        trip('GIAU1000001', 'chep', { tab: 'KHACH GIA COPY', amount_vnd: null, booking: undefined, web: null })] },
    { name: 'KHACH GIA BO 样本', owner: null, book_id: 8, commodity: null, families: ['BO'], ...counts(), rows: [trip('GIAU2000001', 'khop', { family: 'BO' })] },
    { name: null, owner: 'CHU HANG LA', book_id: null, commodity: null, families: ['BIEN'], ...counts({ booking: 1, sheet: 0, web: 0, thieu: 1, issues: 1, amount_vnd: '0' }),
      rows: [trip('GIAU3000001', 'thieu', { tab: null, row: null, amount_vnd: null, date: null, web: null })] },
  ],
});

// BAO-CAO-THANG-02: dạng GET /api/v7/report/month/missing.
const MISSING = [
  { name: 'KHACH GIA A', owner: 'CHU HANG GIA', book_id: 7, machine_book: 7, cont: 'GIAU1000002', family: 'BIEN', date: '2026-10-03', ref: 'BKGIA1', status: 'khop', reason: 'CONTAINER_REUSED_OR_CHANGED' },
  { name: 'KHACH GIA A', owner: 'CHU HANG GIA', book_id: 7, machine_book: 7, cont: 'GIAU1000003', family: 'BIEN', date: '2026-10-29', ref: 'BKGIA2', status: 'thieu', reason: 'COMMODITY_MISMATCH' },
  { name: null, owner: 'CHU HANG LA', book_id: null, machine_book: null, cont: 'GIAU3000001', family: 'BIEN', date: '2026-10-03', ref: 'BKGIA1', status: 'thieu', reason: 'NO_BOOK' },
];

function makeServer(state) {
  return http.createServer((request, response) => {
    const url = new URL(request.url, 'http://x'), route = url.pathname;
    const send = (status, type, body) => { response.writeHead(status, { 'Content-Type': type }); response.end(body); };
    const out = (body, status = 200) => send(status, 'application/json', JSON.stringify(body));
    state.calls.push(`${request.method} ${route}${url.search}`);
    if (route === '/api/v7/report/month') {
      if (state.down) return out({ error: 'X', message: 'x' }, 503);
      return out(REPORT(url.searchParams.get('month') ?? '2026-11'));
    }
    if (route === '/api/v7/report/month/missing') {
      if (state.missingDown) return out({ error: 'X', message: 'x' }, 503);
      return out({ month: url.searchParams.get('month'), state: 'ok', rows: MISSING });
    }
    if (route === '/api/v7/customers') return out({ customers: [] });
    if (route.startsWith('/api/v7/presence')) return out({ people: [] });
    if (route.startsWith('/api/')) return out({}, 503);
    const file = path.join(__dirname, route.replace(/^\//, ''));
    if (!file.startsWith(__dirname) || !fs.existsSync(file)) return send(404, 'text/plain', 'not found');
    const type = file.endsWith('.html') ? 'text/html' : file.endsWith('.css') ? 'text/css' : 'text/javascript';
    return send(200, type, fs.readFileSync(file));
  });
}

async function withPage(state, fn, { viewport = { width: 1265, height: 560 }, query = '?month=2026-10' } = {}) {
  const shared = { calls: [], down: false, ...state };
  const server = makeServer(shared);
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const browser = await launchShared();
  try {
    const page = await (await browser.newContext({ viewport })).newPage();
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.goto(`http://127.0.0.1:${server.address().port}/bao-cao-thang.html${query}`);
    await page.locator('body[data-loaded]').waitFor({ state: 'attached' });
    await fn(page, shared);
    assert.deepEqual(errors, []);
    assert.deepEqual(shared.calls.filter(call => call.startsWith('POST') && !call.includes('presence')), [], 'trang chỉ xem không gửi lệnh ghi');
  } finally {
    await browser.close();
    await new Promise(resolve => server.close(resolve));
  }
}

test('Báo cáo tháng: bảng tổng biển/bộ, khách lệch lên đầu, bấm khách thấy danh sách cont và link mở sổ', async () => {
  await withPage({}, async page => {
    const sum = await page.locator('.sum-table').innerText();
    assert.match(sum, /Tháng 10\/2026/);
    assert.match(sum, /Booking có\s+263\s+201\s+464/);
    assert.match(sum, /Booking có, Sheet chưa ghi\s+2\s+0\s+2/);
    assert.equal(await page.locator('.sum-table td.flag').count(), 6, 'ba hàng lệch khác 0 tô màu');
    assert.match(sum, /Booking có, web chưa có\s+3\s+0\s+3/);
    assert.match(await page.locator('.sum-notes').innerText(), /lượt máy lúc 10:09 16\/11/);
    const first = page.locator('tr.cust').first();
    assert.match(await first.innerText(), /KHACH GIA A\s+Dừa\s+Biển\s+3\s+2\s+2\s+Sheet chưa ghi 1\s+Chép 0đ 1\s+170 tr/);
    assert.match(await page.locator('tr.cust').nth(1).innerText(), /KHACH GIA BO 样本[\s\S]*Khớp/);
    assert.match(await page.locator('tr.cust').nth(2).innerText(), /Chưa rõ sổ · CHU HANG LA[\s\S]*—$/);
    await first.locator('.cust-btn').click();
    assert.equal(await first.locator('.cust-btn').getAttribute('aria-expanded'), 'true');
    const trips = await page.locator('tr.trips').innerText();
    assert.match(trips, /GIAU1000001\s+03\/10\/2026\s+03\/10 · BKGIA1\s+dòng 5 · 85 tr\s+03\/10\s+Khớp/);
    assert.match(trips, /GIAU1000002[\s\S]*Web chưa có/);
    assert.match(trips, /GIAU1000003\s+29\/10\/2026\s+29\/10 · BKGIA2\s+—\s+—\s+Sheet chưa ghi, web chưa có/);
    assert.match(trips, /Dòng chép 0đ/);
    assert.equal(await page.locator('a.open-book').getAttribute('href'), '/so-khach-v7-live.html?customer=7&month=2026-10');
    await page.keyboard.press('Enter');   // tiêu điểm vẫn ở nút khách: Enter thu lại
    assert.equal(await page.locator('tr.trips').count(), 0);
  });
});

test('Báo cáo tháng: lọc khách cần xem, biển/bộ, đổi tháng giữ trên địa chỉ; tháng đang chạy nói nhẹ hơn', async () => {
  await withPage({}, async (page, shared) => {
    await page.locator('#only-issues').check();
    assert.equal(await page.locator('tr.cust').count(), 2);
    assert.match(page.url(), /lech=1/);
    await page.locator('#only-issues').uncheck();
    await page.locator('.seg[data-family="BO"]').click();
    assert.equal(await page.locator('tr.cust').count(), 1);
    assert.match(page.url(), /loai=BO/);
    await page.locator('#month-newer').click();
    await page.locator('.sum-table thead', { hasText: 'Tháng 11/2026' }).waitFor();
    assert.ok(shared.calls.includes('GET /api/v7/report/month?month=2026-11'));
    assert.match(await page.locator('.sum-table').innerText(), /Booking có, chưa lên Sheet/);
    assert.equal(await page.locator('#month-newer').isDisabled(), true, 'tháng hiện tại là mới nhất');
    assert.match(page.url(), /month=2026-11/);
  });
});

test('Báo cáo tháng: lỗi tải có nút Thử lại; số cũ báo rõ; khung 1265×560 lọt menu, không cuộn ngang', async () => {
  await withPage({ down: true }, async (page, shared) => {
    assert.match(await page.locator('#error').innerText(), /Không tải được báo cáo tháng/);
    shared.down = false;
    await page.locator('#retry').click();
    await page.locator('.sum-table').waitFor();
    assert.equal(await page.locator('#error').isHidden(), true);
  });
  await withPage({}, async page => {
    const items = await page.locator('.app-nav nav a').allInnerTexts();
    assert.equal(items.length, 6);   // QUYEN-02: năm trang làm sổ + Quản trị
    assert.ok(items.some(text => text.includes('Báo cáo tháng')));
    const last = await page.locator('.app-nav nav a').last().boundingBox();
    assert.ok(last.y + last.height <= 560, `mục cuối menu lọt khung: ${last.y + last.height}`);
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth));
    const firstCustomer = await page.locator('tr.cust').first().boundingBox();
    assert.ok(firstCustomer.y + firstCustomer.height <= 560, `khách đầu tiên thấy ngay: ${firstCustomer.y}`);
  });
});

test('Báo cáo tháng: bấm "Booking có, web chưa có" mới tải lý do; mỗi chuyến nói máy giữ vì sao và ai làm (BAO-CAO-THANG-02)', async () => {
  await withPage({}, async (page, shared) => {
    assert.equal(shared.calls.filter(call => call.includes('/missing')).length, 0, 'mở trang không đọc lý do');
    const button = page.locator('#show-missing');
    assert.equal(await button.getAttribute('aria-expanded'), 'false');
    await button.click();
    await page.locator('.miss-table').waitFor();
    assert.ok(shared.calls.includes('GET /api/v7/report/month/missing?month=2026-10'));
    assert.equal(await page.locator('#show-missing').getAttribute('aria-expanded'), 'true');
    assert.match(page.url(), /webchua=1/);
    const text = await page.locator('#missing').innerText();
    assert.match(text, /Chuyến booking có, web chưa có \(3\)/);
    assert.match(text, /03\/10\/2026\s+GIAU1000002\s+Biển\s+CHU HANG GIA · sổ KHACH GIA A\s+Sổ đã có container này ở ngày khác[^\n]*\s+Xem trong sổ · Mở sổ/);
    assert.ok(await page.evaluate(() => document.getElementById('missing').getBoundingClientRect().top < 560), 'bấm mở thì danh sách vào khung');
    assert.match(text, /GIAU1000003[\s\S]*Mặt hàng trên booking khác mặt hàng của sổ\s+Cần người · Việc cần làm/);
    assert.match(text, /GIAU3000001\s+Biển\s+CHU HANG LA\s+Tên chủ hàng chưa gắn sổ web[^\n]*\s+Cần người$/m);
    assert.equal(await page.locator('#missing a', { hasText: 'Mở sổ' }).getAttribute('href'), '/so-khach-v7-live.html?customer=7&month=2026-10');
    await page.locator('#show-missing').click();
    assert.equal(await page.locator('#missing').count(), 0);
    await page.locator('#show-missing').click();
    assert.equal(shared.calls.filter(call => call.includes('/missing')).length, 1, 'mở lại không đọc lại');
  });
  await withPage({ missingDown: true }, async (page, shared) => {   // link gửi kèm webchua=1: mở trang là đọc lý do luôn
    await page.locator('#retry-missing').waitFor();
    assert.match(await page.locator('#missing').innerText(), /Không tải được lý do/);
    shared.missingDown = false;
    await page.locator('#retry-missing').click();
    await page.locator('.miss-table').waitFor();
  }, { query: '?month=2026-10&webchua=1' });
});
