const { test } = require('node:test');
const assert = require('node:assert/strict');
const http = require('node:http');
const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require('playwright');

const dashboard = { as_of: '2026-10-23', demo: true, receivable: { total_vnd: '2480000000', customers: 18 }, credit: { total_vnd: '-125000000', customers: 3 }, by_commodity: [{ commodity: 'Sầu riêng', transport_mode: 'CẢNG', customers: 8, receivable_vnd: '1200000000' }, { commodity: null, transport_mode: null, customers: 2, receivable_vnd: '150000000' }], aging: [{ bucket: 'current', receivable_vnd: '680000000' }, { bucket: '1-2', receivable_vnd: '950000000' }, { bucket: '3-6', receivable_vnd: '600000000' }, { bucket: 'over-6', receivable_vnd: '250000000' }], top_debtors: [{ customer_id: 1, name: 'Khách A', commodity: 'Sầu riêng', outstanding_vnd: '380000000', oldest_open_month: '2026-03-01' }], todo: { missing_price: [{ customer_id: 2, name: 'Khách C', count: 3 }], pending_review: [], no_baseline: [], credit: [{ customer_id: 3, name: 'Khách K', credit_vnd: '-45000000' }] }, today: { trips: 12, receipts: 4, received_vnd: '186000000', voids: 1, by_actor: [{ actor: 'Người nhập 1', trips: 7, receipts: 3, received_vnd: '120000000', voids: 1 }] } };

// Ma trận giả khớp aging của dashboard: A, C tháng này; C 1–2 tháng; D 3–6 tháng; E trên 6 tháng (nợ trước năm ngoái).
const months = values => Object.fromEntries(Array.from({ length: 12 }, (_, i) => [String(i + 1), values[i + 1] ?? '0']));
const matrix = year => ({ as_of: '2026-10-23', year, customers: year !== 2026 ? [] : [
  { customer_id: 1, name: 'Khách A', commodity: 'Sầu riêng', transport_mode: 'CANG', months: months({ 10: '380000000' }), total_year_vnd: '380000000', total_all_vnd: '380000000', oldest_open_month: '2026-10-01' },
  { customer_id: 2, name: 'Khách C', commodity: 'Chuối', transport_mode: null, months: months({ 10: '300000000', 9: '950000000' }), total_year_vnd: '1250000000', total_all_vnd: '1250000000', oldest_open_month: '2026-09-01' },
  { customer_id: 4, name: 'Khách D', commodity: null, transport_mode: null, months: months({ 5: '600000000' }), total_year_vnd: '600000000', total_all_vnd: '600000000', oldest_open_month: '2026-05-01' },
  { customer_id: 5, name: 'Khách E', commodity: 'Sầu riêng', transport_mode: null, months: months({}), total_year_vnd: '0', total_all_vnd: '250000000', oldest_open_month: '2024-02-01' },
  { customer_id: 3, name: 'Khách K', commodity: null, transport_mode: null, months: months({ 10: '-45000000' }), total_year_vnd: '-45000000', total_all_vnd: '-45000000', oldest_open_month: null },
], grand_total_year_vnd: '0', grand_total_all_vnd: '0' });

function makeServer({ payload = dashboard, dashboardStatus = 200, customerStatus = 200, matrixStatus = 200, matrixFor = matrix, customers = [{ id: 1, name: 'Khách A' }, { id: 2, name: 'Khách C' }], people = [] } = {}) {
  const server = http.createServer((req, res) => {
    const route = req.url.split('?')[0];
    const file = path.join(__dirname, route.replace(/^\//, ''));
    const send = (status, type, body) => { res.writeHead(status, { 'Content-Type': type }); res.end(body); };
    if (route === '/api/v7/dashboard') return send(dashboardStatus, 'application/json', JSON.stringify(typeof payload === 'function' ? payload() : payload));
    if (route.startsWith('/api/v7/presence')) return send(200, 'application/json', JSON.stringify({ people }));   // PRESENCE-01
    if (route === '/api/v7/customers') return send(customerStatus, 'application/json', JSON.stringify({ customers }));
    if (route === '/api/v7/receivables/matrix') return send(matrixStatus, 'application/json', JSON.stringify(matrixFor(Number(new URL(req.url, 'http://x').searchParams.get('year')))));
    if (!file.startsWith(__dirname) || !fs.existsSync(file)) return send(404, 'text/plain', 'not found');
    const type = file.endsWith('.html') ? 'text/html' : file.endsWith('.css') ? 'text/css' : 'text/javascript';
    return send(200, type, fs.readFileSync(file));
  });
  return server;
}

async function withDashboard(options, fn, query = '') {
  const server = makeServer(options);
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const browser = await chromium.launch({ headless: true });
  try {
    const page = await browser.newPage({ viewport: options?.viewport ?? { width: 1280, height: 720 } });
    await page.goto(`http://127.0.0.1:${server.address().port}/dashboard-v7.html${query}`);
    await fn(page);
  } finally {
    await browser.close();
    server.close();
  }
}

test('dashboard renders six blocks, links, keyboard navigation, and mobile layout', async () => withDashboard({}, async page => {
  await page.locator('.receivable .big-money').waitFor();
  for (const heading of ['Còn phải thu', 'Theo mặt hàng', 'Nợ theo tháng phát sinh', 'Khách nợ nhiều nhất', 'Việc cần làm', 'Hôm nay'])
    assert.equal(await page.getByRole('heading', { name: heading }).count(), 1);
  assert.match(await page.locator('.receivable').innerText(), /2\.480\.000\.000/);
  assert.equal(await page.locator('.top-debtors .bar-row').first().getAttribute('data-khach'), '1');
  // Mockup v4.1: số chính rút gọn, số đồng đủ ở dòng phụ và khi rê chuột; tuổi nợ một thanh chia đoạn.
  assert.equal(await page.locator('.receivable .big-money').innerText(), '2,48tỷ');
  assert.equal(await page.locator('.age-bar span').count(), 4);
  assert.match(await page.locator('.age-note').innerText(), /850 triệu \(34,3%\)/);
  // Mockup v5.3: mặt hàng chỉ tên + số tỷ 2 số lẻ; chỉ sầu riêng tách cảng/bộ; chưa phân loại xám ở cuối.
  assert.deepEqual(await page.locator('.commodity .bar-row .nm').allInnerTexts(), ['Sầu riêng cảng', 'Chưa phân loại']);
  assert.equal(await page.locator('.commodity .bar-row').first().locator('.val').innerText(), '1,20');
  assert.equal(await page.locator('.commodity .bar-row.grey').count(), 1);
  assert.match(await page.locator('.todo').innerText(), /Cần gán mặt hàng \/ cảng-bộ[\s\S]*Khách D[\s\S]*chưa có mặt hàng[\s\S]*Khách E[\s\S]*chưa rõ cảng\/bộ/);
  assert.equal(await page.locator('.todo a', { hasText: 'Khách C' }).getAttribute('href'), '/so-khach-v7-live.html?customer=2&loc=thieu-gia');
  assert.match(await page.locator('.todo').innerText(), /3 chuyến/);
  const layout = await page.evaluate(() => ({ scrollX: document.documentElement.scrollWidth > innerWidth,
    firstRowBottom: Math.max(...[...document.querySelectorAll('.receivable,.aging')].map(el => el.getBoundingClientRect().bottom)) }));
  assert.equal(!layout.scrollX && layout.firstRowBottom <= 720, true, JSON.stringify(layout));
  await page.locator('#customer-search').fill('Khách C');
  await page.locator('#customer-search').press('Tab');
  assert.equal(await page.locator('#customer-results a').getAttribute('href'), '/so-khach-v7-live.html?customer=2');
  assert.equal(await page.locator('#customer-results a').evaluate(el => el === document.activeElement), true);
  await page.setViewportSize({ width: 390, height: 844 });
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
  if (process.env.SHOTS_DIR) {
    fs.mkdirSync(process.env.SHOTS_DIR, { recursive: true });
    await page.screenshot({ path: path.join(process.env.SHOTS_DIR, 'dashboard-v7-b.png'), fullPage: true });
  }
}));

test('dashboard handles empty data without fake values', async () => withDashboard({ matrixFor: year => ({ as_of: '2026-10-23', year, customers: [], grand_total_year_vnd: '0', grand_total_all_vnd: '0' }), payload: { as_of: '2026-10-23', receivable: { total_vnd: '0', customers: 0 }, credit: { total_vnd: '0', customers: 0 }, by_commodity: [], aging: [{ bucket: 'current', receivable_vnd: '0' }, { bucket: '1-2', receivable_vnd: '0' }, { bucket: '3-6', receivable_vnd: '0' }, { bucket: 'over-6', receivable_vnd: '0' }], top_debtors: [], todo: { missing_price: [], pending_review: [], no_baseline: [], credit: [] }, today: { trips: 0, receipts: 0, received_vnd: '0', voids: 0, by_actor: [] } } }, async page => {
  await page.locator('.receivable .big-money').waitFor();
  assert.match(await page.locator('.receivable').innerText(), /0 đ/);
  assert.match(await page.locator('.todo').innerText(), /Không có việc cần làm/);
  assert.equal(await page.locator('.top-debtors .bar-row').count(), 0);
  assert.equal(await page.locator('.commodity .bar-row').count(), 0);
  assert.match(await page.locator('.today').innerText(), /Chưa có giao dịch nào hôm nay/);
}));

test('dashboard refresh reads new data and shows update time', async () => {
  let amount = '2480000000';
  await withDashboard({ payload: () => ({ ...dashboard, receivable: { ...dashboard.receivable, total_vnd: amount } }) }, async page => {
    await page.locator('.receivable .big-money').waitFor();
    amount = '2480000001';
    await page.locator('#refresh-data').click();
    await page.getByText('2.480.000.001 đ').waitFor();
    assert.match(await page.locator('#updated-at').innerText(), /Cập nhật .* tự tải mỗi 60 giây/);
  });
});

test('dashboard shows API failure and does not leave loading content', async () => withDashboard({ dashboardStatus: 503 }, async page => {
  await page.locator('#error').waitFor({ state: 'visible' });
  assert.match(await page.locator('#error').innerText(), /Không tải được tổng quan công nợ/);
  assert.equal(await page.locator('#dashboard').innerText(), '');
}));

test('customer search failure does not erase loaded dashboard', async () => withDashboard({ customerStatus: 503 }, async page => {
  await page.locator('.receivable .big-money').waitFor();
  assert.match(await page.locator('.receivable').innerText(), /2\.480\.000\.000/);
  assert.equal(await page.locator('#error').isHidden(), true);
}));

test('dashboard uses Sheet labels and commodity while links and money stay on original books', async () => withDashboard({
  customers: [
    { id: 1, name: 'AG -DỪA', display_name: 'AG LOGISTIC', commodity: 'Dừa', aliases: ['AG DU A'] },
    { id: 2, name: 'Khách C', display_name: 'CHAU HAI THINH', commodity: 'Chuối', aliases: [] },
    { id: 3, name: 'Khách K', display_name: 'CHAU HAI THINH', commodity: 'Chuối', aliases: [] },
  ],
}, async page => {
  await page.locator('.top-debtors .bar-row .nm').getByText('AG LOGISTIC', { exact: true }).waitFor();
  await page.locator('.top-debtors .bar-row').first().focus();
  // Đọc từng dòng của ô thông tin: innerText không có xuống dòng nếu ô vừa ẩn (CI Linux).
  const tip = await page.locator('#tip > *').allTextContents();
  assert.deepEqual([tip[0], tip[1], tip[3]], ['AG LOGISTIC', '380 triệu', '380.000.000 đ']);
  assert.match(tip[2], /nợ từ 03\/2026/);
  await page.locator('.top-debtors .bar-row').first().click();
  assert.equal(await page.locator('#d-open').getAttribute('href'), '/so-khach-v7-live.html?customer=1');
  await page.keyboard.press('Escape');
  await page.locator('#drawer').waitFor({ state: 'hidden' });
  assert.match(await page.locator('.todo').innerText(), /CHAU HAI THINH · Chuối · sổ 2/);
  await page.locator('#customer-search').fill('AG DU A');
  assert.equal(await page.locator('#customer-results a').innerText(), 'AG LOGISTIC · Dừa');
  await page.locator('#customer-search').fill('dua');
  assert.equal(await page.locator('#customer-results a').count(), 1);
}));

test('lọc tại Tổng quan: nhóm tuổi nợ + mặt hàng lọc danh sách khách, số tổng giữ nguyên, ngăn kéo và địa chỉ trang', async () => withDashboard({}, async page => {
  await page.locator('.top-debtors .bar-row').first().waitFor();
  const receivable = await page.locator('.receivable').innerText();
  await page.locator('[data-tuoi="1"]').click();
  assert.equal(await page.locator('#h-top').innerText(), '1 khách theo lọc');
  assert.deepEqual(await page.locator('#top .nm').allInnerTexts(), ['Khách C']);
  assert.equal(await page.locator('#top .val').innerText(), '0,95');
  assert.match(await page.locator('#filterbar').innerText(), /Phần nợ 1–2 tháng trước/);
  assert.match(await page.evaluate(() => location.search), /tuoi=1/);
  await page.locator('.age-bar [data-i="2"]').click();
  assert.deepEqual(await page.locator('#top .nm').allInnerTexts(), ['Khách D']);
  await page.locator('[data-mh="Chưa phân loại"]').click();
  assert.equal(await page.locator('#h-top').innerText(), '1 khách theo lọc');
  await page.locator('[data-clear="age"]').click();
  assert.deepEqual(await page.locator('#top .nm').allInnerTexts(), ['Khách D', 'Khách E']);
  assert.equal(await page.locator('.receivable').innerText(), receivable);
  await page.locator('#top .bar-row').first().click();
  assert.match(await page.locator('#drawer').innerText(), /Khách D[\s\S]*Tháng 05\/2026[\s\S]*600 triệu/);
  assert.match(await page.evaluate(() => location.search), /khach=4/);
  // Mở bằng bấm thì ESC gọi history.back(): ngăn kéo đóng ở popstate, sau khi phím đã trả về.
  await page.keyboard.press('Escape');
  await page.locator('#drawer').waitFor({ state: 'hidden' });
  assert.doesNotMatch(await page.evaluate(() => location.search), /khach=/);
  assert.equal(await page.evaluate(() => document.activeElement.dataset.khach), '4');
  await page.locator('[data-clear="all"]').click();
  assert.equal(await page.locator('#h-top').innerText(), 'Khách nợ nhiều nhất');
  assert.equal(await page.locator('#filterbar').isHidden(), true);
  await page.locator('.age-legend [data-tuoi="3"]').hover();
  assert.deepEqual((await page.locator('#tip > *').allTextContents()).slice(0, 3), ['Trên 6 tháng', '250 triệu', '10,1% còn phải thu · 1 khách']);
  await page.setViewportSize({ width: 390, height: 844 });
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
}));

test('link có sẵn ?tuoi=&mh=&khach= mở đúng trạng thái; ESC đóng tại chỗ', async () => withDashboard({}, async page => {
  await page.locator('#drawer:not([hidden])').waitFor();
  assert.equal(await page.locator('#d-name').innerText(), 'Khách D');
  assert.equal(await page.locator('[data-tuoi="2"]').getAttribute('aria-pressed'), 'true');
  await page.keyboard.press('Escape');
  assert.equal(await page.locator('#drawer').isHidden(), true);
  assert.equal(await page.evaluate(() => location.search), '?tuoi=2&mh=Ch%C6%B0a+ph%C3%A2n+lo%E1%BA%A1i');
}, '?tuoi=2&mh=Ch%C6%B0a+ph%C3%A2n+lo%E1%BA%A1i&khach=4'));

test('ma trận lỗi hoặc lệch tổng tuổi nợ: trang vẫn đọc được, bấm nhóm tuổi sang Công nợ theo tháng', async () => {
  await withDashboard({ matrixStatus: 503 }, async page => {
    await page.locator('.top-debtors .bar-row').first().waitFor();
    assert.equal(await page.locator('.commodity .bar-row').first().isDisabled(), true);
    await page.locator('[data-tuoi="2"]').click();
    await page.waitForURL(/cong-no-theo-thang\.html\?tuoi=2&con-no=1/);
  });
  await withDashboard({ payload: { ...dashboard, aging: dashboard.aging.map(item => item.bucket === 'current' ? { ...item, receivable_vnd: '680000001' } : item) } }, async page => {
    await page.locator('.top-debtors .bar-row').first().waitFor();
    await page.locator('[data-tuoi="0"]').click();
    await page.waitForURL(/cong-no-theo-thang\.html\?tuoi=0&con-no=1/);
  });
});

test('PRESENCE-01: chấm màu cạnh khách đang có người mở sổ, vòng tròn người online', async () => withDashboard({ people: [
  { id: 'p1', name: 'Lan', color: 0, page: 'so-khach', customer_id: 1, month: '2026-10', cell: null, pointer: null },
  { id: 'p2', name: 'Tuấn', color: 3, page: 'so-khach', customer_id: 2, month: '2026-09', cell: null, pointer: null },
] }, async page => {
  await page.locator('.top-debtors [data-khach="1"] .presence-dot').waitFor();
  assert.equal(await page.locator('.top-debtors [data-khach="1"] .presence-dot').getAttribute('aria-label'), 'Lan đang mở sổ này');
  await page.locator('a[href*="customer=2"] .presence-dot').first().waitFor();
  const labels = await page.locator('.presence-avatar').evaluateAll(nodes => nodes.map(node => node.getAttribute('aria-label')));
  assert.deepEqual(labels, ['Lan · đang mở sổ Khách A, tháng 10/2026', 'Tuấn · đang mở sổ Khách C, tháng 9/2026']);
}));
