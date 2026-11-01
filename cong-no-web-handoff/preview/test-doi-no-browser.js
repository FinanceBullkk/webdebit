const { test } = require('node:test');
const assert = require('node:assert/strict');
const http = require('node:http');
const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require('playwright');

// NHAC-NO-01: tab Đòi nợ — khách quá hạn + mốc "đã nhắc", nút Copy tin nhắc ghi reminder_log.
const rule = { due_after_months: 1, long_overdue_months: 3, no_pay_days: 60, no_trip_days: 90, active_trip_days: 30 };
const row = (id, name, tiers, extra) => ({ customer_id: id, name, commodity: null, transport_mode: null, tiers_vnd: tiers,
  outstanding_vnd: String(tiers.reduce((s, v) => s + BigInt(v), 0n)), overdue_vnd: String(tiers.slice(2).reduce((s, v) => s + BigInt(v), 0n)),
  long_overdue_vnd: String(tiers.slice(3).reduce((s, v) => s + BigInt(v), 0n)), last_receipt_date: null, pay_days: null,
  last_trip_date: null, trip_days: null, risk: 'high', ...extra });
const debt = () => ({ as_of: '2026-10-29', month: '2026-10-01', rule, receivable_vnd: '1800000000',
  due_tiers: [], summary: { overdue_vnd: '1800000000', long_overdue_vnd: '850000000', overdue_customers: 3, high_customers: 2, high_overdue_vnd: '850000000' },
  this_month: { month: '2026-10-01', charges_vnd: '0', received_vnd: '0' },
  customers: [
    row(2, 'Khách C', ['0', '0', '950000000', '0', '0'], { risk: 'watch', oldest_open_month: '2026-08-01',
      months: [{ month: '2026-08-01', outstanding_vnd: '950000000' }] }),
    row(4, 'Khách D', ['0', '0', '0', '600000000', '0'], { oldest_open_month: '2026-05-01',
      months: [{ month: '2026-05-01', outstanding_vnd: '600000000' }] }),
    row(5, 'Khách E', ['0', '0', '0', '0', '250000000'], { oldest_open_month: '2024-02-01', last_receipt_date: '2024-03-10',
      months: [{ month: '2024-02-01', outstanding_vnd: '250000000' }] }),
    row(1, 'Khách A', ['380000000', '0', '0', '0', '0'], { risk: 'ok', oldest_open_month: '2026-10-01' }),  // trong hạn: bị loại
  ] });

function makeServer({ debtPayload = debt(), debtStatus = 200,
  reminders = [{ customer_id: 2, last_reminded: '2026-10-20', reminder_count: 1, last_source: 'copy-button' }],
  customers = [{ id: 1, name: 'Khách A' }, { id: 2, name: 'Khách C' }, { id: 4, name: 'Khách D' }, { id: 5, name: 'Khách E' }],
  posted = [], inbox = null } = {}) {
  return http.createServer((req, res) => {
    const route = req.url.split('?')[0];
    const send = (status, type, body) => { res.writeHead(status, { 'Content-Type': type }); res.end(body); };
    if (req.method === 'POST' && route === '/api/v7/reminders') {
      let raw = '';
      req.on('data', chunk => { raw += chunk; });
      req.on('end', () => { const body = JSON.parse(raw); posted.push(body);
        send(200, 'application/json', JSON.stringify({ customer_id: body.customer_id, source: body.source, reminded_at: '2026-10-29' })); });
      return;
    }
    if (route === '/api/v7/dashboard/debt') return send(debtStatus, 'application/json', JSON.stringify(debtPayload));
    if (route === '/api/v7/reminders') return send(200, 'application/json', JSON.stringify({ reminders }));
    if (route === '/api/v7/customers') return send(200, 'application/json', JSON.stringify({ customers }));
    if (route.startsWith('/api/v7/presence')) return send(200, 'application/json', JSON.stringify({ people: [] }));
    if (route === '/api/v7/inbox') return inbox ? send(200, 'application/json', JSON.stringify(inbox)) : send(503, 'application/json', '{}');
    const file = path.join(__dirname, route.replace(/^\//, ''));
    if (!file.startsWith(__dirname) || !fs.existsSync(file)) return send(404, 'text/plain', 'not found');
    const type = file.endsWith('.html') ? 'text/html' : file.endsWith('.css') ? 'text/css' : 'text/javascript';
    return send(200, type, fs.readFileSync(file));
  });
}

async function withPage(options, fn) {
  const server = makeServer(options);
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const browser = await chromium.launch({ headless: true });
  try {
    const context = await browser.newContext({ viewport: { width: 1280, height: 720 }, permissions: ['clipboard-read', 'clipboard-write'] });
    const tab = await context.newPage();
    await tab.goto(`http://127.0.0.1:${server.address().port}/doi-no.html`);
    await fn(tab);
  } finally {
    await browser.close();
    server.close();
  }
}

test('Đòi nợ: liệt kê khách quá hạn, trạng thái nhắc, lọc chưa nhắc; khách trong hạn bị loại', async () => withPage({}, async page => {
  await page.locator('.rrow').first().waitFor();
  assert.deepEqual(await page.locator('.rrow .nm').allInnerTexts(), ['Khách C', 'Khách D', 'Khách E']);
  assert.match(await page.getByRole('heading', { name: /Khách quá hạn cần đòi/ }).innerText(), /3 khách · 2 chưa nhắc/);
  assert.deepEqual(await page.locator('.rrow .st').allInnerTexts(), ['Đã nhắc 9 ngày, chưa trả', 'Chưa nhắc', 'Chưa nhắc']);
  assert.equal(await page.locator('nav a.active').innerText(), 'Đòi nợ');
  // Lọc "Chưa nhắc" còn 2 khách.
  await page.locator('[data-filter="chua-nhac"]').click();
  assert.deepEqual(await page.locator('.rrow .nm').allInnerTexts(), ['Khách D', 'Khách E']);
}));

// Audit UX 31/10/2026 (đợt 1, P0-6/P1-2): ngày dd/mm/yyyy, tên khách là liên kết, tiêu đề cột cùng lưới với các dòng.
test('Đòi nợ: ngày dd/mm/yyyy, tên khách mở thẻ Trao đổi, số quá hạn mở sổ, tiêu đề cột thẳng với số bên dưới', async () => withPage({}, async page => {
  await page.locator('.rrow').first().waitFor();
  const cRow = page.locator('.rrow').filter({ hasText: 'Khách C' });
  assert.deepEqual(await cRow.locator('.when').allInnerTexts(), ['chưa có', '20/10/2026 · 9 ngày trước']);
  assert.equal(await page.locator('.rrow').filter({ hasText: 'Khách E' }).locator('.when').first().innerText(), '10/03/2024');
  for (const text of await page.locator('.rrow .when').allInnerTexts()) assert.doesNotMatch(text, /\d{4}-\d{2}-\d{2}/);
  // TRANG-KHACH-01 (PR A4): tên khách mở thẻ Trao đổi; SO-GON-04: số quá hạn mở sổ ở tháng nợ cũ nhất còn nợ.
  assert.equal(await cRow.locator('a.nm').getAttribute('href'), '/so-khach-v7-live.html?customer=2&the=trao-doi');
  assert.equal(await cRow.locator('a.num.od').getAttribute('href'), '/so-khach-v7-live.html?customer=2&month=2026-08');
  assert.equal(await cRow.locator('a.num.od').getAttribute('title'), '950.000.000 đ · mở sổ tháng 8/2026');
  assert.deepEqual(await page.locator('.rrow a.num.od').evaluateAll(links => links.map(link => link.getBoundingClientRect().height >= 40)), [true, true, true]);
  assert.equal(await page.locator('.rrow a.chat').first().getAttribute('href'), '/zalo-chat.html?q=Kh%C3%A1ch%20C');
  // Mỗi ô của từng dòng thẳng mép trái/phải với ô tiêu đề cùng cột (lệch tối đa 1px).
  const aligned = await page.evaluate(() => {
    const edges = el => { const box = el.getBoundingClientRect(); return [box.left, box.right]; };
    const head = [...document.querySelector('.rhead').children].map(edges);
    return [...document.querySelectorAll('.rrow')].map(row => [...row.children].map(edges)
      .every(([left, right], index) => Math.abs(left - head[index][0]) <= 1 && Math.abs(right - head[index][1]) <= 1));
  });
  assert.deepEqual(aligned, [true, true, true]);
}));

test('Copy tin nhắc: ghi mốc đã nhắc (POST reminder) và cập nhật dòng ngay', async () => {
  const posted = [];
  await withPage({ posted }, async page => {
    await page.locator('.rrow').first().waitFor();
    const dRow = page.locator('.rrow').filter({ hasText: 'Khách D' });
    assert.equal(await dRow.locator('.st').innerText(), 'Chưa nhắc');
    await dRow.locator('[data-copy]').click();
    await assert.doesNotReject(async () => dRow.locator('.st', { hasText: /Đã nhắc/ }).waitFor({ timeout: 4000 }));
    assert.match(await dRow.locator('.st').innerText(), /Đã nhắc hôm nay/);
    assert.match(await page.getByRole('heading', { name: /Khách quá hạn cần đòi/ }).innerText(), /3 khách · 1 chưa nhắc/);
  });
  assert.deepEqual(posted, [{ customer_id: 4, source: 'copy-button' }]);
});

test('Đòi nợ: API debt lỗi thì báo lỗi, không để chữ đang tải', async () => withPage({ debtStatus: 503 }, async page => {
  await page.locator('#error').waitFor({ state: 'visible' });
  assert.match(await page.locator('#error').innerText(), /Không tải được số liệu đòi nợ/);
}));

// Hộp ngoại lệ P2 (specs/v7-hop-ngoai-le-p2.md): khách còn phiếu thu từ Sheet chưa ghi thì có nhãn, Copy tin nhắc hỏi lại trước.
const inboxBook = (id, receipts) => ({ customer_id: id, version: 3, outstanding_vnd: '950000000', receipts: { ready: 0, review: 0, amount_vnd: '0', ready_amount_vnd: '0', items: [], locked_months: [], ...receipts },
  removed: { count: 0, amount_vnd: '0' }, trips_new: 0, trips_check: { count: 0, reasons: {} }, text_diff: 0, prices: { ready: 0, review: 0 }, ps: { ready: 0, review: 0 } });
const INBOX = { state: 'ready', computed_at: '2026-10-29T08:00:00+00:00', sheet_at: null, refreshing: false, books_total: 4, books_done: 4, failed: [],
  books: [inboxBook(2, { ready: 1, amount_vnd: '50000000', ready_amount_vnd: '50000000' }), inboxBook(4, { ready: 0, review: 0 })] };

test('Đòi nợ: khách còn phiếu thu chưa ghi có nhãn; Copy tin nhắc hỏi lại, Vẫn copy thì copy và ghi đã nhắc', async () => {
  const posted = [];
  await withPage({ inbox: INBOX, posted }, async page => {
    await page.locator('.rrow').first().waitFor();
    assert.match(await page.locator('.rrow', { hasText: 'Khách C' }).innerText(), /còn 1 phiếu chưa ghi · 50 triệu/);
    assert.equal(await page.locator('.rrow', { hasText: 'Khách D' }).locator('.pend').count(), 0);
    assert.equal(await page.locator('.tiny.warn').count(), 0);
    await page.locator('[data-copy="2"]').click();
    const dialog = page.locator('#pending-ask');
    await dialog.waitFor({ state: 'visible' });
    assert.match(await dialog.innerText(), /Khách còn 1 phiếu thu 50\.000\.000 đ trên Sheet chưa ghi vào web\. Tin nhắc sẽ ghi nợ cao hơn thực tế\./);
    assert.equal(await page.evaluate(() => document.activeElement?.id), 'pending-write');
    await page.locator('#pending-copy').click();
    await page.locator('#toast:not([hidden])').waitFor();
    assert.deepEqual(posted, [{ customer_id: 2, source: 'copy-button' }]);
    assert.match(await page.evaluate(() => navigator.clipboard.readText()), /Tổng công nợ còn lại/);
    // Khách không có phiếu chờ: copy thẳng, không hỏi.
    await page.locator('[data-copy="4"]').click();
    await page.waitForFunction(() => document.querySelector('#toast')?.textContent.includes('Khách D'));
    assert.equal(posted.length, 2);
  });
});

test('Đòi nợ: Ghi phiếu trước mở Việc cần làm, Thôi không copy; không đọc được việc chờ thì ghi rõ và không hỏi', async () => {
  const posted = [];
  await withPage({ inbox: INBOX, posted }, async page => {
    await page.locator('[data-copy="2"]').click();
    await page.locator('#pending-ask').waitFor({ state: 'visible' });
    await page.keyboard.press('Escape');
    await page.locator('#pending-ask').waitFor({ state: 'hidden' });
    assert.equal(posted.length, 0);
    await page.locator('[data-copy="2"]').click();
    await Promise.all([page.waitForURL(/\/viec-can-lam\.html$/), page.locator('#pending-write').click()]);
    assert.equal(posted.length, 0);
  });
  await withPage({ inbox: null, posted: [] }, async page => {
    await page.locator('.rrow').first().waitFor();
    assert.match(await page.locator('.tiny.warn').innerText(), /Chưa kiểm được phiếu thu từ Sheet chờ ghi/);
    assert.equal(await page.locator('.pend').count(), 0);
  });
});
