const { test } = require('node:test');
const assert = require('node:assert/strict');
const http = require('node:http');
const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require('playwright');

const dashboard = { as_of: '2026-10-23', demo: true, receivable: { total_vnd: '2480000000', customers: 18 }, credit: { total_vnd: '-125000000', customers: 3 }, by_commodity: [{ commodity: 'Sầu riêng', transport_mode: 'CẢNG', customers: 8, receivable_vnd: '1200000000' }, { commodity: null, transport_mode: null, customers: 2, receivable_vnd: '150000000' }], aging: [{ bucket: 'current', receivable_vnd: '680000000' }, { bucket: '1-2', receivable_vnd: '950000000' }, { bucket: '3-6', receivable_vnd: '600000000' }, { bucket: 'over-6', receivable_vnd: '250000000' }], top_debtors: [{ customer_id: 1, name: 'Khách A', commodity: 'Sầu riêng', outstanding_vnd: '380000000', oldest_open_month: '2026-03-01' }], todo: { missing_price: [{ customer_id: 2, name: 'Khách C', count: 3 }], pending_review: [], no_baseline: [], credit: [{ customer_id: 3, name: 'Khách K', credit_vnd: '-45000000' }] }, today: { trips: 12, receipts: 4, received_vnd: '186000000', voids: 1, by_actor: [{ actor: 'Người nhập 1', trips: 7, receipts: 3, received_vnd: '120000000', voids: 1 }] } };

test('dashboard B renders read-only summary and customer links', async () => {
  const server = http.createServer((req, res) => {
    const route = req.url.split('?')[0];
    const file = path.join(__dirname, route.replace(/^\//, ''));
    const send = (status, type, body) => { res.writeHead(status, { 'Content-Type': type }); res.end(body); };
    if (route === '/api/v7/dashboard') return send(200, 'application/json', JSON.stringify(dashboard));
    if (route === '/api/v7/customers') return send(200, 'application/json', JSON.stringify({ customers: [{ id: 1, name: 'Khách A' }, { id: 2, name: 'Khách C' }] }));
    if (!file.startsWith(__dirname) || !fs.existsSync(file)) return send(404, 'text/plain', 'not found');
    const type = file.endsWith('.html') ? 'text/html' : file.endsWith('.css') ? 'text/css' : 'text/javascript';
    return send(200, type, fs.readFileSync(file));
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const browser = await chromium.launch({ headless: true });
  try {
    const page = await browser.newPage({ viewport: { width: 1280, height: 720 } });
    await page.goto(`http://127.0.0.1:${server.address().port}/dashboard-v7.html`);
    await page.locator('.receivable .big-money').waitFor();
    assert.match(await page.locator('h1').innerText(), /Tổng quan công nợ/);
    assert.match(await page.locator('.receivable').innerText(), /2\.480\.000\.000/);
    assert.equal(await page.locator('.top-debtors a').getAttribute('href'), '/so-khach-v7-live.html?customer=1');
    await page.locator('#customer-search').fill('Khách C');
    assert.equal(await page.locator('#customer-results a').getAttribute('href'), '/so-khach-v7-live.html?customer=2');
    if (process.env.SHOTS_DIR) {
      fs.mkdirSync(process.env.SHOTS_DIR, { recursive: true });
      await page.screenshot({ path: path.join(process.env.SHOTS_DIR, 'dashboard-v7-b.png'), fullPage: true });
    }
  } finally {
    await browser.close();
    server.close();
  }
});
