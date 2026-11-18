// XUAT-SO-01 (specs/v7-xuat-ca-so.md): nút "Tải cả sổ" ở Tổng quan. Máy chủ giả trả file và header X-Xuat-So như API thật;
// file và phép tự kiểm thật được test ở tests/test_v7_xuat_so.py. Dữ liệu giả.
const assert = require('node:assert/strict');
const http = require('node:http');
const fs = require('node:fs');
const path = require('node:path');
const { launchShared, test } = require('./shared-browser.js');

const JSON_TYPE = { 'Content-Type': 'application/json' };
const XLSX = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet';
const dashboard = { as_of: '2026-11-18', receivable: { total_vnd: '350000', customers: 1 }, credit: { total_vnd: '0', customers: 0 },
  by_commodity: [], aging: [], top_debtors: [], todo: { missing_price: [], pending_review: [], no_baseline: [], credit: [] },
  today: { trips: 0, receipts: 0, received_vnd: '0', voids: 0, by_actor: [] } };
const debt = { as_of: '2026-11-18', month: '2026-11-01', receivable_vnd: '350000',
  rule: { due_after_months: 1, long_overdue_months: 3, no_pay_days: 60, no_trip_days: 90, active_trip_days: 30 },
  due_tiers: ['not_due', 'due_this_month', 'late_1_2', 'late_3_6', 'late_over_6'].map((tier, i) => ({ tier, receivable_vnd: i ? '0' : '350000' })),
  summary: { overdue_vnd: '0', long_overdue_vnd: '0', overdue_customers: 0, high_customers: 0, high_overdue_vnd: '0' },
  this_month: { month: '2026-11-01', charges_vnd: '0', received_vnd: '0', customers: [] }, customers: [] };

// Các kiểu trả lời của GET /api/v7/xuat-so.xlsx.
const file = (name, check, delay = 0) => (req, res) => setTimeout(() => {
  res.writeHead(200, { 'Content-Type': XLSX, 'Content-Disposition': `attachment; filename="${name}"`, 'X-Xuat-So': JSON.stringify(check) });
  res.end(Buffer.from('PK giả'));
}, delay);
const fail = (status, body) => (req, res) => { res.writeHead(status, JSON_TYPE); res.end(JSON.stringify(body)); };
const drop = req => req.socket.destroy();

async function withDashboard(reply, fn, viewport = { width: 1280, height: 720 }) {
  const state = { reply, hits: 0 };
  const server = http.createServer((req, res) => {
    const route = req.url.split('?')[0];
    if (route === '/api/v7/xuat-so.xlsx') { state.hits += 1; return state.reply(req, res); }
    if (route === '/api/v7/dashboard') return fail(200, dashboard)(req, res);
    if (route === '/api/v7/dashboard/debt') return fail(200, debt)(req, res);
    if (route === '/api/v7/customers') return fail(200, { customers: [] })(req, res);
    if (route.startsWith('/api/v7/')) return fail(404, { error: 'NOT_FOUND' })(req, res);
    const local = path.join(__dirname, route.replace(/^\//, ''));
    if (!local.startsWith(__dirname) || !fs.existsSync(local)) { res.writeHead(404); return res.end(); }
    res.writeHead(200, { 'Content-Type': local.endsWith('.html') ? 'text/html' : local.endsWith('.css') ? 'text/css' : 'text/javascript' });
    return res.end(fs.readFileSync(local));
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const browser = await launchShared();
  try {
    const page = await browser.newPage({ viewport, acceptDownloads: true });
    await page.goto(`http://127.0.0.1:${server.address().port}/dashboard-v7.html`);
    await page.locator('.strip').waitFor();
    await fn(page, state);
  } finally {
    await browser.close();
    server.close();
  }
}

const status = page => page.locator('#export-status');
const button = page => page.getByRole('button', { name: 'Tải cả sổ' });

test('XUAT-SO-01: bấm Tải cả sổ thì đang xuất, khóa bấm lặp, tải file, báo tự kiểm khớp', async () => withDashboard(
  file('so-web-20261118-1030.xlsx', { ok: true, books: 4, problems: [] }, 600), async (page, state) => {
    const go = button(page);
    assert.equal(await go.isVisible(), true);
    assert.equal(await status(page).isHidden(), true);
    // Nằm trên thanh đầu, trước đồng hồ và nút làm mới; thanh đầu không tràn ở 1280.
    assert.deepEqual(await page.locator('.live-controls > *').evaluateAll(nodes => nodes.map(node => node.id)),
      ['export-books', 'as-of', 'updated-at', 'refresh-data']);
    assert.equal(await page.locator('.page-head').evaluate(node => node.scrollWidth <= node.clientWidth), true);
    const download = page.waitForEvent('download');
    await go.dblclick();   // lần bấm thứ hai rơi vào lúc nút đã khóa
    assert.equal(await page.locator('#export-books').isDisabled(), true);
    assert.equal(await page.locator('#export-books span').innerText(), 'Đang xuất…');
    assert.match(await status(page).innerText(), /^Đang xuất cả sổ… thường mất dưới một phút/);
    assert.equal(await status(page).getAttribute('class'), 'export-status is-busy');
    assert.equal((await download).suggestedFilename(), 'so-web-20261118-1030.xlsx');
    await page.locator('#export-status.is-ok').waitFor();
    assert.equal(await status(page).innerText(), 'Đã tải so-web-20261118-1030.xlsx: 4 sổ, tự kiểm khớp (tổng các sổ bằng Còn phải thu '
      + 'trên Tổng quan). Cất file vào thư mục dự phòng.');
    assert.equal(await go.isEnabled(), true);
    assert.equal(state.hits, 1);
  }));

test('XUAT-SO-01: tự kiểm lệch thì file vẫn tải, tên có CO-LECH, trang báo đỏ từng chỗ lệch', async () => withDashboard(
  file('so-web-20261118-1030-CO-LECH.xlsx', { ok: false, books: 4, problems: [{ code: 'TONG_QUAN_PHAI_THU', count: 1, books: [] },
    { code: 'SO_LECH_TONG_QUAN', count: 7, books: [12, 40, 41, 42, 43] }] }), async page => {
    const download = page.waitForEvent('download');
    await button(page).click();
    assert.equal((await download).suggestedFilename(), 'so-web-20261118-1030-CO-LECH.xlsx');
    await page.locator('#export-status.is-bad').waitFor();
    assert.equal(await status(page).innerText(), 'Bản xuất có chỗ lệch: Còn phải thu trên Tổng quan khác tổng các sổ; 7 sổ lệch số Tổng '
      + 'quan (sổ 12, 40, 41, 42, 43…). File so-web-20261118-1030-CO-LECH.xlsx vẫn tải về và đã đánh dấu CO-LECH; báo quản trị kiểm '
      + 'trước khi dùng.');
  }));

test('XUAT-SO-01: đang có lượt khác, máy chủ lỗi, mất mạng: câu báo, không tải gì', async () => withDashboard(
  fail(429, { error: 'EXPORT_BUSY', message: 'x' }), async (page, state) => {
    let downloads = 0;
    page.on('download', () => { downloads += 1; });
    await button(page).click();
    await page.locator('#export-status.is-wait').waitFor();
    assert.equal(await status(page).innerText(), 'Đang có một lượt xuất khác. Chờ khoảng một phút rồi bấm lại.');
    state.reply = fail(503, { error: 'DB_UNAVAILABLE', message: 'Sổ tạm thời không truy cập được.' });
    await button(page).click();
    await page.locator('#export-status.is-bad').waitFor();
    assert.equal(await status(page).innerText(), 'Chưa xuất được cả sổ. Sổ tạm thời không truy cập được.');
    state.reply = drop;
    await button(page).click();
    await page.waitForFunction(() => document.querySelector('#export-status').textContent.endsWith('Thử lại sau ít phút.'));
    assert.equal(await status(page).innerText(), 'Chưa xuất được cả sổ. Thử lại sau ít phút.');
    assert.equal(await button(page).isEnabled(), true);
    assert.equal(downloads, 0);
  }));

test('XUAT-SO-01: bàn phím bấm được, chú thích nút nói rõ việc', async () => withDashboard(
  file('so-web-20261118-1030.xlsx', { ok: true, books: 4, problems: [] }), async page => {
    assert.deepEqual((await page.locator('#export-books').getAttribute('data-tip')).split('\n'),
      ['Tải cả sổ', 'Mọi sổ khách ra một file Excel, cất làm bản dự phòng khi web hỏng']);
    await page.locator('#export-books').focus();
    const download = page.waitForEvent('download');
    await page.keyboard.press('Enter');
    await download;
    await page.locator('#export-status.is-ok').waitFor();
  }));

test('XUAT-SO-01: điện thoại còn biểu tượng, tên nút vẫn đọc được, dòng báo không làm cuộn ngang', async () => withDashboard(
  file('so-web-20261118-1030-CO-LECH.xlsx', { ok: false, books: 4, problems: [{ code: 'FILE_LECH', count: 1, books: [7] }] }),
  async page => {
    const box = await page.locator('#export-books').boundingBox();
    assert.equal(Math.round(box.width), 40);
    assert.equal(await button(page).count(), 1);   // tên "Tải cả sổ" vẫn trong cây trợ năng
    const download = page.waitForEvent('download');
    await button(page).click();
    await download;
    await page.locator('#export-status.is-bad').waitFor();
    // Chỉ đo phần nút này thêm: khối Quá hạn của dải đầu tự tràn ở màn hẹp với vài con số, là lỗi có từ trước.
    const line = await page.locator('#export-status').boundingBox();
    assert.ok(line.x >= 0 && line.x + line.width <= 390, JSON.stringify(line));
    assert.equal(await page.locator('#export-status').evaluate(node => node.scrollWidth <= node.clientWidth), true);
    assert.equal(await page.locator('.page-head').evaluate(node => node.scrollWidth <= node.clientWidth), true);
  }, { width: 390, height: 800 }));
