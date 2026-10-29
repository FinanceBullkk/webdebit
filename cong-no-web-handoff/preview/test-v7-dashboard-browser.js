const { test } = require('node:test');
const assert = require('node:assert/strict');
const http = require('node:http');
const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require('playwright');

const dashboard = { as_of: '2026-10-29', demo: true, receivable: { total_vnd: '2480000000', customers: 4 }, credit: { total_vnd: '-125000000', customers: 3 }, by_commodity: [], aging: [], top_debtors: [], todo: { missing_price: [{ customer_id: 2, name: 'Khách C', count: 3 }], pending_review: [], no_baseline: [], credit: [{ customer_id: 3, name: 'Khách K', credit_vnd: '-45000000' }] }, today: { trips: 12, receipts: 4, received_vnd: '186000000', voids: 1, by_actor: [{ actor: 'Người nhập 1', trips: 7, receipts: 3, received_vnd: '120000000', voids: 1 }] } };

// Bốn khách giả: A trong hạn, C quá hạn 1–2 tháng (theo dõi), D quá hạn 3–6 tháng chưa trả lần nào, E nợ 2024 (rủi ro cao).
const rule = { due_after_months: 1, long_overdue_months: 3, no_pay_days: 60, no_trip_days: 90, active_trip_days: 30 };
const row = (id, name, tiers, extra) => ({ customer_id: id, name, commodity: null, transport_mode: null, tiers_vnd: tiers,
  outstanding_vnd: String(tiers.reduce((s, v) => s + BigInt(v), 0n)), overdue_vnd: String(tiers.slice(2).reduce((s, v) => s + BigInt(v), 0n)),
  long_overdue_vnd: String(tiers.slice(3).reduce((s, v) => s + BigInt(v), 0n)), last_receipt_date: null, last_receipt_exact: null, pay_days: null,
  last_trip_date: null, last_trip_exact: null, trip_days: null, ...extra });
const debt = { as_of: '2026-10-29', month: '2026-10-01', rule, receivable_vnd: '2480000000',
  due_tiers: [['not_due', '680000000'], ['due_this_month', '0'], ['late_1_2', '950000000'], ['late_3_6', '600000000'], ['late_over_6', '250000000']]
    .map(([tier, value]) => ({ tier, receivable_vnd: value })),
  summary: { overdue_vnd: '1800000000', long_overdue_vnd: '850000000', overdue_customers: 3, high_customers: 2, high_overdue_vnd: '850000000' },
  this_month: { month: '2026-10-01', charges_vnd: '700000000', received_vnd: '186000000' },
  customers: [
    row(2, 'Khách C', ['300000000', '0', '950000000', '0', '0'], { commodity: 'Chuối', risk: 'watch', oldest_open_month: '2026-08-01',
      last_receipt_date: '2026-10-02', last_receipt_exact: true, pay_days: 27, last_trip_date: '2026-10-26', last_trip_exact: true, trip_days: 3,
      months: [{ month: '2026-08-01', outstanding_vnd: '950000000' }, { month: '2026-10-01', outstanding_vnd: '300000000' }] }),
    row(4, 'Khách D', ['0', '0', '0', '600000000', '0'], { risk: 'high', oldest_open_month: '2026-05-01',
      last_trip_date: '2026-05-20', last_trip_exact: true, trip_days: 162, months: [{ month: '2026-05-01', outstanding_vnd: '600000000' }] }),
    row(5, 'Khách E', ['0', '0', '0', '0', '250000000'], { commodity: 'Sầu riêng', risk: 'high', oldest_open_month: '2024-02-01',
      last_receipt_date: '2024-03-10', last_receipt_exact: true, pay_days: 963, months: [{ month: '2024-02-01', outstanding_vnd: '250000000' }] }),
    row(1, 'Khách A', ['380000000', '0', '0', '0', '0'], { commodity: 'Sầu riêng', transport_mode: 'CANG', risk: 'ok', oldest_open_month: '2026-10-01',
      last_receipt_date: '2026-10-20', last_receipt_exact: true, pay_days: 9, last_trip_date: '2026-10-25', last_trip_exact: true, trip_days: 4,
      months: [{ month: '2026-10-01', outstanding_vnd: '380000000' }] }),
  ] };

function makeServer({ payload = dashboard, debtPayload = debt, dashboardStatus = 200, debtStatus = 200, customerStatus = 200, customers = [{ id: 1, name: 'Khách A' }, { id: 2, name: 'Khách C' }], people = [] } = {}) {
  return http.createServer((req, res) => {
    const route = req.url.split('?')[0];
    const file = path.join(__dirname, route.replace(/^\//, ''));
    const send = (status, type, body) => { res.writeHead(status, { 'Content-Type': type }); res.end(body); };
    const value = item => JSON.stringify(typeof item === 'function' ? item() : item);
    if (route === '/api/v7/dashboard') return send(dashboardStatus, 'application/json', value(payload));
    if (route === '/api/v7/dashboard/debt') return send(debtStatus, 'application/json', value(debtPayload));
    if (route.startsWith('/api/v7/presence')) return send(200, 'application/json', JSON.stringify({ people }));   // PRESENCE-01
    if (route === '/api/v7/customers') return send(customerStatus, 'application/json', JSON.stringify({ customers }));
    if (!file.startsWith(__dirname) || !fs.existsSync(file)) return send(404, 'text/plain', 'not found');
    const type = file.endsWith('.html') ? 'text/html' : file.endsWith('.css') ? 'text/css' : 'text/javascript';
    return send(200, type, fs.readFileSync(file));
  });
}

async function withPage(options, fn, page = '/dashboard-v7.html') {
  const server = makeServer(options);
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const browser = await chromium.launch({ headless: true });
  try {
    const tab = await browser.newPage({ viewport: options?.viewport ?? { width: 1280, height: 720 } });
    await tab.goto(`http://127.0.0.1:${server.address().port}${page}`);
    await fn(tab);
  } finally {
    await browser.close();
    server.close();
  }
}
const withDashboard = (options, fn, query = '') => withPage(options, fn, `/dashboard-v7.html${query}`);

test('Tổng quan chỉ còn bốn khối về công nợ; số chính, hạn trả, khách cần đòi, phân loại; màn đầu và điện thoại', async () => withDashboard({}, async page => {
  await page.locator('.receivable .big-money').waitFor();
  await page.locator('#list .drow').first().waitFor();
  for (const heading of ['Còn phải thu', 'Nợ theo hạn trả', 'Khách cần đòi trước', 'Phân loại khách đang nợ'])
    assert.equal(await page.getByRole('heading', { name: heading }).count(), 1);
  for (const heading of ['Việc cần làm', 'Hôm nay', 'Theo mặt hàng', 'Khách nợ nhiều nhất'])
    assert.equal(await page.getByRole('heading', { name: heading }).count(), 0);
  assert.equal(await page.locator('.receivable .big-money').innerText(), '2,48tỷ');
  assert.match(await page.locator('.receivable').innerText(), /2\.480\.000\.000 đ · 4 khách đang nợ/);
  assert.match(await page.locator('.receivable .minis').innerText(), /Đã thu tháng 10\s+186 triệu\s+phát sinh 700 triệu[\s\S]*Khách rủi ro cao\s+2 khách\s+quá hạn 850 triệu/);
  assert.equal(await page.locator('.hero-foot').innerText(), 'Chưa tính 3 chuyến thiếu đơn giá · 3 khách đang dư 125 triệu, tính riêng');
  // Năm nhóm hạn trả: nhóm trống không vẽ đoạn; chú giải ghi tháng nợ; vạch tách trong hạn / quá hạn.
  assert.equal(await page.locator('.age-bar span').count(), 4);
  assert.match(await page.locator('.due .age-note').innerText(), /^1,8 tỷ \(72,6%\) đã quá hạn, trong đó 850 triệu quá hạn từ 3 tháng trở lên\.$/);
  assert.deepEqual(await page.locator('.age-legend .m').allInnerTexts(), ['nợ T10', 'nợ T9', 'nợ T7–T8', 'nợ T3–T6', 'nợ T2 trở về trước']);
  assert.equal(await page.locator('.due-mark').evaluate(el => el.style.left), '27.4%');
  // Khách cần đòi: xếp theo tiền quá hạn; nhãn rủi ro và một câu lý do.
  assert.deepEqual(await page.locator('#list .nm').allInnerTexts(), ['Khách C', 'Khách D', 'Khách E', 'Khách A']);
  assert.deepEqual(await page.locator('#list .num.od').allInnerTexts(), ['0,95', '0,60', '0,25', '0,00']);
  assert.deepEqual(await page.locator('#list .why').allInnerTexts(), ['Nợ T8/2026 quá hạn · có trả 02/10',
    'Nợ từ T5/2026 · chưa trả lần nào · ngừng đi hàng', 'Nợ từ T2/2024 · 32 tháng chưa trả · chưa có chuyến', 'Trong hạn · có trả 20/10']);
  assert.equal(await page.locator('#list .tag.critical').count(), 2);
  assert.equal(await page.locator('#list-aside').innerText(), '3/4 khách có nợ quá hạn · tỷ đồng');
  // Phân loại: mặc định theo rủi ro; đổi tiêu chí.
  assert.match(await page.locator('#cls-lead').innerText(), /2 khách rủi ro cao đang nợ 850 triệu, trong đó quá hạn 850 triệu\./);
  assert.deepEqual(await page.locator('#cls-bars .nm').allInnerTexts(), ['Rủi ro cao', 'Cần theo dõi', 'Trong hạn']);
  await page.locator('[data-dim="com"]').click();
  assert.deepEqual(await page.locator('#cls-bars .nm').allInnerTexts(), ['Chuối', 'Sầu riêng cảng', 'Chưa phân loại']);
  assert.equal(await page.locator('#cls-bars .bar-row.grey').count(), 1);
  assert.equal(await page.locator('#todo-badge').innerText(), '3');
  assert.equal(await page.locator('nav a[href="/viec-can-lam.html"]').count(), 1);
  const layout = await page.evaluate(() => ({ scrollX: document.documentElement.scrollWidth > innerWidth,
    firstRowBottom: Math.max(...[...document.querySelectorAll('.receivable,.due')].map(el => el.getBoundingClientRect().bottom)) }));
  assert.equal(!layout.scrollX && layout.firstRowBottom <= 720, true, JSON.stringify(layout));
  await page.locator('#customer-search').fill('Khách C');
  await page.locator('#customer-search').press('Tab');
  assert.equal(await page.locator('#customer-results a').getAttribute('href'), '/so-khach-v7-live.html?customer=2');
  await page.setViewportSize({ width: 390, height: 844 });
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
  if (process.env.SHOTS_DIR) {
    fs.mkdirSync(process.env.SHOTS_DIR, { recursive: true });
    await page.setViewportSize({ width: 1280, height: 720 });
    await page.screenshot({ path: path.join(process.env.SHOTS_DIR, 'dashboard-v7-quan-ly-no.png'), fullPage: true });
  }
}));

test('Tổng quan không có khách đang nợ: không bịa số', async () => withDashboard({
  payload: { ...dashboard, receivable: { total_vnd: '0', customers: 0 }, credit: { total_vnd: '0', customers: 0 }, todo: { missing_price: [], pending_review: [], no_baseline: [], credit: [] } },
  debtPayload: { ...debt, receivable_vnd: '0', customers: [], due_tiers: debt.due_tiers.map(t => ({ ...t, receivable_vnd: '0' })),
    summary: { overdue_vnd: '0', long_overdue_vnd: '0', overdue_customers: 0, high_customers: 0, high_overdue_vnd: '0' },
    this_month: { month: '2026-10-01', charges_vnd: '0', received_vnd: '0' } },
}, async page => {
  await page.locator('.receivable .big-money').waitFor();
  assert.match(await page.locator('.receivable').innerText(), /0 đ/);
  assert.equal(await page.locator('.hero-foot').count(), 0);
  assert.equal(await page.locator('.age-bar span').count(), 0);
  assert.match(await page.locator('#list').innerText(), /Không có khách đang nợ/);
  assert.match(await page.locator('#cls-bars').innerText(), /Chưa có khách đang nợ/);
  assert.equal(await page.locator('#todo-badge').isHidden(), true);
}));

test('Làm mới đọc số mới và ghi giờ cập nhật', async () => {
  let amount = '2480000000';
  await withDashboard({ payload: () => ({ ...dashboard, receivable: { ...dashboard.receivable, total_vnd: amount } }) }, async page => {
    await page.locator('.receivable .big-money').waitFor();
    amount = '2480000001';
    await page.locator('#refresh-data').click();
    await page.getByText('2.480.000.001 đ').waitFor();
    assert.match(await page.locator('#updated-at').innerText(), /Cập nhật .* tự tải mỗi 60 giây/);
  });
});

test('lỗi API tổng quan: báo lỗi, không để chữ đang tải', async () => withDashboard({ dashboardStatus: 503 }, async page => {
  await page.locator('#error').waitFor({ state: 'visible' });
  assert.match(await page.locator('#error').innerText(), /Không tải được tổng quan công nợ/);
  assert.equal(await page.locator('#dashboard').innerText(), '');
}));

test('chưa có phần quá hạn (API debt lỗi) hay tìm khách lỗi: số tổng vẫn đọc được', async () => {
  await withDashboard({ debtStatus: 503 }, async page => {
    await page.locator('.receivable .big-money').waitFor();
    assert.match(await page.locator('.receivable').innerText(), /2\.480\.000\.000/);
    assert.equal(await page.locator('.receivable .minis').count(), 0);
    assert.match(await page.locator('.due').innerText(), /Chưa tải được phần quá hạn/);
    assert.match(await page.locator('#list').innerText(), /Chưa tải được danh sách khách quá hạn/);
    assert.match(await page.locator('.classify').innerText(), /Chưa tải được phân loại khách/);
    assert.equal(await page.locator('#error').isHidden(), true);
  });
  await withDashboard({ customerStatus: 503 }, async page => {
    await page.locator('#list .drow').first().waitFor();
    assert.deepEqual(await page.locator('#list .nm').allInnerTexts(), ['Khách C', 'Khách D', 'Khách E', 'Khách A']);
    assert.equal(await page.locator('#error').isHidden(), true);
  });
});

test('tên Sheet trên danh sách, ô thông tin, ngăn kéo mở sổ gốc', async () => withDashboard({
  customers: [
    { id: 1, name: 'AG -DỪA', display_name: 'AG LOGISTIC', commodity: 'Dừa', aliases: ['AG DU A'] },
    { id: 2, name: 'Khách C', display_name: 'CHAU HAI THINH', commodity: 'Chuối', aliases: [] },
    { id: 3, name: 'Khách K', display_name: 'CHAU HAI THINH', commodity: 'Chuối', aliases: [] },
  ],
}, async page => {
  await page.locator('#list .nm').getByText('AG LOGISTIC', { exact: true }).waitFor();
  assert.equal(await page.locator('#list .nm').first().innerText(), 'CHAU HAI THINH · Chuối · sổ 2');
  await page.locator('#list .drow').first().focus();
  // Đọc từng dòng của ô thông tin: innerText không có xuống dòng nếu ô vừa ẩn (CI Linux).
  const tip = await page.locator('#tip > *').allTextContents();
  assert.deepEqual([tip[0], tip[1], tip[3]], ['CHAU HAI THINH · Chuối · sổ 2', 'Quá hạn 950 triệu', 'Bấm để xem nhanh']);
  assert.match(tip[2], /còn nợ 1,25 tỷ/);
  await page.locator('#list .drow').first().click();
  assert.equal(await page.locator('#d-open').getAttribute('href'), '/so-khach-v7-live.html?customer=2');
  assert.match(await page.locator('#d-body').innerText(), /3 chuyến thiếu đơn giá — chưa tính vào số trên/);
  await page.keyboard.press('Escape');
  await page.locator('#drawer').waitFor({ state: 'hidden' });
  await page.locator('#customer-search').fill('AG DU A');
  assert.equal(await page.locator('#customer-results a').innerText(), 'AG LOGISTIC · Dừa');
}));

test('lọc tại chỗ: nhóm hạn trả + nhóm phân loại kết hợp, số tổng giữ nguyên, ngăn kéo và địa chỉ trang', async () => withDashboard({}, async page => {
  await page.locator('#list .drow').first().waitFor();
  const receivable = await page.locator('.receivable').innerText();
  await page.locator('.age-legend [data-tier="3"]').click();
  assert.equal(await page.locator('#h-list').innerText(), '1 khách theo lọc');
  assert.deepEqual(await page.locator('#list .nm').allInnerTexts(), ['Khách D']);
  assert.equal(await page.locator('#col-first').innerText(), 'Nợ nhóm này');
  assert.match(await page.locator('#filterbar').innerText(), /Nợ quá hạn 3–6 tháng/);
  assert.match(await page.evaluate(() => location.search), /han=3/);
  await page.locator('.age-bar [data-tier="2"]').click();
  assert.deepEqual(await page.locator('#list .nm').allInnerTexts(), ['Khách C']);
  await page.locator('[data-dim="trip"]').click();
  await page.locator('[data-cls="trip:t91"]').click();
  assert.equal(await page.locator('#h-list').innerText(), '0 khách theo lọc');
  assert.match(await page.locator('#list').innerText(), /Không có khách nào khớp lọc này/);
  await page.locator('[data-clear="tier"]').click();
  assert.deepEqual(await page.locator('#list .nm').allInnerTexts(), ['Khách D', 'Khách E']);
  assert.match(await page.locator('#filterbar').innerText(), /Đi hàng gần nhất: ngừng đi hàng \(trên 90 ngày\)/);
  assert.equal(await page.locator('.receivable').innerText(), receivable);
  await page.locator('[data-sort="total"]').click();
  assert.match(await page.evaluate(() => location.search), /xep=tong/);
  await page.locator('#list .drow').first().click();
  assert.match(await page.locator('#drawer').innerText(), /Khách D[\s\S]*Rủi ro cao — vì sao[\s\S]*Còn 600 triệu quá hạn từ 3 tháng trở lên \(nợ từ tháng 5\/2026\)[\s\S]*Chưa trả lần nào[\s\S]*Đi hàng gần nhất 20\/05\/2026 — đã ngừng đi hàng[\s\S]*Tháng 05\/2026[\s\S]*Quá hạn 3–6 tháng[\s\S]*600 triệu/);
  assert.match(await page.evaluate(() => location.search), /khach=4/);
  // Mở bằng bấm thì ESC gọi history.back(): ngăn kéo đóng ở popstate, sau khi phím đã trả về.
  await page.keyboard.press('Escape');
  await page.locator('#drawer').waitFor({ state: 'hidden' });
  assert.doesNotMatch(await page.evaluate(() => location.search), /khach=/);
  assert.equal(await page.evaluate(() => document.activeElement.dataset.khach), '4');
  await page.locator('.mini.risk').click();
  assert.deepEqual(await page.locator('#list .nm').allInnerTexts(), ['Khách D', 'Khách E']);
  assert.equal(await page.locator('[data-dim="risk"]').getAttribute('aria-selected'), 'true');
  await page.locator('[data-clear="all"]').click();
  assert.equal(await page.locator('#h-list').innerText(), 'Khách cần đòi trước');
  assert.equal(await page.locator('#filterbar').isHidden(), true);
  await page.locator('.age-legend [data-tier="4"]').hover();
  assert.deepEqual((await page.locator('#tip > *').allTextContents()).slice(0, 3), ['Quá hạn trên 6 tháng', '250 triệu', '10,1% còn phải thu · 1 khách · nợ T2 trở về trước']);
  await page.setViewportSize({ width: 390, height: 844 });
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
}));

test('link có sẵn ?han=&nhom=&khach= mở đúng trạng thái; ESC đóng tại chỗ', async () => withDashboard({}, async page => {
  await page.locator('#drawer:not([hidden])').waitFor();
  assert.equal(await page.locator('#d-name').innerText(), 'Khách D');
  assert.equal(await page.locator('.age-legend [data-tier="3"]').getAttribute('aria-pressed'), 'true');
  assert.equal(await page.locator('[data-cls="risk:high"].bar-row').getAttribute('aria-pressed'), 'true');
  await page.keyboard.press('Escape');
  assert.equal(await page.locator('#drawer').isHidden(), true);
  assert.equal(await page.evaluate(() => location.search), '?han=3&nhom=risk%3Ahigh');
}, '?han=3&nhom=risk%3Ahigh&khach=4'));

test('số từng khách lệch tổng server: không lọc tại chỗ, bấm nhóm hạn trả sang Công nợ theo tháng', async () => withDashboard({
  debtPayload: { ...debt, due_tiers: debt.due_tiers.map(t => (t.tier === 'not_due' ? { ...t, receivable_vnd: '680000001' } : t)) },
}, async page => {
  await page.locator('#list .drow').first().waitFor();
  assert.equal(await page.locator('#cls-bars .bar-row').first().isDisabled(), true);
  assert.equal(await page.locator('.mini.risk').isDisabled(), true);
  await page.locator('.age-legend [data-tier="2"]').click();
  await page.waitForURL(/cong-no-theo-thang\.html\?con-no=1/);
}, '?han=2'));

test('PRESENCE-01: chấm màu cạnh khách đang có người mở sổ, vòng tròn người online', async () => withDashboard({ people: [
  { id: 'p1', name: 'Lan', color: 0, page: 'so-khach', customer_id: 1, month: '2026-10', cell: null, pointer: null },
  { id: 'p2', name: 'Tuấn', color: 3, page: 'so-khach', customer_id: 2, month: '2026-09', cell: null, pointer: null },
] }, async page => {
  await page.locator('#list [data-khach="1"] .presence-dot').waitFor();
  assert.equal(await page.locator('#list [data-khach="1"] .presence-dot').getAttribute('aria-label'), 'Lan đang mở sổ này');
  const labels = await page.locator('.presence-avatar').evaluateAll(nodes => nodes.map(node => node.getAttribute('aria-label')));
  assert.deepEqual(labels, ['Lan · đang mở sổ Khách A, tháng 10/2026', 'Tuấn · đang mở sổ Khách C, tháng 9/2026']);
}));

test('tab Việc cần làm: nhóm việc mở đúng dòng trong sổ, hôm nay, sổ đang dư, số trên thanh điều hướng', async () => withPage({}, async page => {
  await page.locator('.todo .todo-group').first().waitFor();
  assert.match(await page.locator('nav a.active').innerText(), /^Việc cần làm\s*3$/);
  assert.equal(await page.locator('.todo a', { hasText: 'Khách C' }).getAttribute('href'), '/so-khach-v7-live.html?customer=2&loc=thieu-gia');
  assert.match(await page.locator('.todo').innerText(), /Chuyến thiếu đơn giá\s+3 chuyến[\s\S]*Cần gán mặt hàng \/ cảng-bộ\s+2 khách[\s\S]*Khách D[\s\S]*chưa có mặt hàng[\s\S]*Khách E[\s\S]*chưa rõ cảng\/bộ/);
  assert.match(await page.locator('.today').innerText(), /12\s+chuyến nhập[\s\S]*Người nhập 1/);
  assert.match(await page.locator('.credit').innerText(), /Khách K\s+dư 45 triệu/);
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
}, '/viec-can-lam.html'));

test('tab Việc cần làm: không có việc thì nói rõ; API debt lỗi chỉ bỏ nhóm gán mặt hàng', async () => {
  await withPage({ payload: { ...dashboard, todo: { missing_price: [], pending_review: [], no_baseline: [], credit: [] }, today: { trips: 0, receipts: 0, received_vnd: '0', voids: 0, by_actor: [] } }, debtPayload: { ...debt, customers: [] } }, async page => {
    await page.locator('.todo').waitFor();
    assert.match(await page.locator('.todo').innerText(), /Không có việc cần làm/);
    assert.match(await page.locator('.today').innerText(), /Chưa có giao dịch nào hôm nay/);
    assert.match(await page.locator('.credit').innerText(), /Không có sổ nào đang dư/);
    assert.equal(await page.locator('#todo-badge').isHidden(), true);
  }, '/viec-can-lam.html');
  await withPage({ debtStatus: 503 }, async page => {
    await page.locator('.todo .todo-group').first().waitFor();
    assert.doesNotMatch(await page.locator('.todo').innerText(), /Cần gán mặt hàng/);
    assert.equal(await page.locator('#todo-badge').innerText(), '1');
  }, '/viec-can-lam.html');
  await withPage({ dashboardStatus: 503 }, async page => {
    await page.locator('#error').waitFor({ state: 'visible' });
    assert.match(await page.locator('#error').innerText(), /Không tải được việc cần làm/);
  }, '/viec-can-lam.html');
});
