const { test } = require('node:test');
const assert = require('node:assert/strict');
const http = require('node:http');
const fs = require('node:fs');
const path = require('node:path');
const { launchShared } = require('./shared-browser.js');

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

// Hộp ngoại lệ P1: kết quả GET /api/v7/inbox giả (specs/v7-hop-ngoai-le-p1.md).
const INBOX_EMPTY = { state: 'ready', computed_at: '2026-11-01T08:02:00+00:00', sheet_at: '2026-11-01T07:45:00+00:00', refreshing: false, books_total: 3, books_done: 3, failed: [], books: [] };
const inboxBook = (id, extra = {}) => ({ customer_id: id, receipts: { ready: 0, review: 0, amount_vnd: '0' }, removed: { count: 0, amount_vnd: '0' },
  trips_new: 0, trips_check: { count: 0, reasons: {} }, text_diff: 0, prices: { ready: 0, review: 0 }, ps: { ready: 0, review: 0 }, ...extra });

// `drop`: tập đường API mà máy chủ cắt kết nối (giả mất mạng); test xóa khỏi tập để lần sau tải được.
function makeServer({ payload = dashboard, debtPayload = debt, dashboardStatus = 200, debtStatus = 200, customerStatus = 200, customers = [{ id: 1, name: 'Khách A' }, { id: 2, name: 'Khách C' }], people = [], drop = new Set(), inbox = INBOX_EMPTY, inboxStatus = 200, receiptPost = null, posted = [] } = {}) {
  return http.createServer((req, res) => {
    const route = req.url.split('?')[0];
    const file = path.join(__dirname, route.replace(/^\//, ''));
    const send = (status, type, body) => { res.writeHead(status, { 'Content-Type': type }); res.end(body); };
    const value = item => JSON.stringify(typeof item === 'function' ? item() : item);
    if (drop.has(route)) { req.socket.destroy(); return; }
    if (req.method === 'POST' && route === '/api/v7/sheet/receipts') {   // hộp P2: ghi phiếu thu từ Sheet của một sổ
      let raw = '';
      req.on('data', chunk => { raw += chunk; });
      req.on('end', () => {
        const body = JSON.parse(raw);
        posted.push(body);
        const reply = receiptPost(body, posted.length);
        if (reply === 'drop') { req.socket.destroy(); return; }
        send(reply.status, 'application/json', JSON.stringify(reply.json));
      });
      return;
    }
    if (route === '/api/v7/dashboard') return send(dashboardStatus, 'application/json', value(payload));
    if (route === '/api/v7/dashboard/debt') return send(debtStatus, 'application/json', value(debtPayload));
    if (route.startsWith('/api/v7/presence')) return send(200, 'application/json', JSON.stringify({ people }));   // PRESENCE-01
    if (route === '/api/v7/customers') return send(customerStatus, 'application/json', JSON.stringify({ customers }));
    if (route === '/api/v7/inbox') return send(inboxStatus, 'application/json', value(inbox));   // hộp ngoại lệ P1
    if (!file.startsWith(__dirname) || !fs.existsSync(file)) return send(404, 'text/plain', 'not found');
    const type = file.endsWith('.html') ? 'text/html' : file.endsWith('.css') ? 'text/css' : 'text/javascript';
    return send(200, type, fs.readFileSync(file));
  });
}

async function withPage(options, fn, page = '/dashboard-v7.html') {
  const server = makeServer(options);
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const browser = await launchShared();
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
// DASH-05: dòng ô chú thích (data-tip) tách theo xuống dòng; dòng đầu là tên, sau là chi tiết.
const tipLines = async locator => (await locator.getAttribute('data-tip')).split('\n');
// Chữ người nhìn thấy: từng mẩu chữ nối bằng dấu cách, bỏ phần chỉ dành cho trình đọc màn hình (.sr-only).
const seen = locator => locator.evaluateAll(nodes => nodes.map(node => {
  const copy = node.cloneNode(true);
  copy.querySelectorAll('.sr-only').forEach(item => item.remove());
  const walker = document.createTreeWalker(copy, NodeFilter.SHOW_TEXT);
  const parts = [];
  while (walker.nextNode()) if (walker.currentNode.textContent.trim()) parts.push(walker.currentNode.textContent.trim());
  return parts.join(' ');
}));
const noSideScroll = page => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth);

test('Tổng quan DASH-05: dải đầu, 5 ô hạn trả, thu tháng, chip mức rủi ro, bảng triệu; số bằng API; 1280×720 và điện thoại', async () => withDashboard({}, async page => {
  await page.locator('#list tr').first().waitFor();
  assert.equal(await page.getByRole('heading', { level: 1 }).innerText(), 'Tổng quan công nợ');
  for (const heading of ['Thu tháng 10', 'Khách cần đòi trước']) assert.equal(await page.getByRole('heading', { name: heading }).count(), 1);
  for (const gone of ['Khách quá hạn đang ở đâu', 'Việc cần làm', 'Hôm nay', 'Phân loại khách đang nợ'])
    assert.equal(await page.getByRole('heading', { name: gone }).count(), 0);
  assert.equal(await page.locator('#drawer, #mx, .filterbar, .hero-foot').count(), 0);
  // Dải đầu: Còn phải thu (API dashboard), số khách, chuyến chưa giá, khách trả thừa; số đồng đầy đủ ở chú thích.
  const strip = page.locator('.strip');
  assert.equal(await strip.locator('.big-money').innerText(), '2,48 tỷ');
  assert.deepEqual(await tipLines(strip.locator('.big-money')), ['Còn phải thu', '2.480.000.000 đ']);
  assert.deepEqual(await seen(strip.locator('.owe-row .pill')), ['4', '3', '125 tr']);
  assert.equal(await strip.locator('.pill').first().getAttribute('data-tip'), '4 khách đang nợ');
  assert.equal(await page.locator('#missing-price').getAttribute('href'), '/viec-can-lam.html');
  assert.match(await page.locator('#credit').getAttribute('data-tip'), /^3 khách trả thừa 125 tr\nTính riêng/);
  // Ngoặc là tổng phụ; thanh chỉ là hình (không số); số mỗi nhóm ở đúng một chỗ: 5 ô.
  assert.match(await strip.locator('.brk').innerText(), /Trong hạn\s+680 tr\s+Quá hạn\s+1,8 tỷ/);
  assert.deepEqual(await strip.locator('.age-bar button').allInnerTexts(), ['', '', '', '']);
  assert.deepEqual((await strip.locator('.tile').allInnerTexts()).map(text => text.replace(/\s+/g, ' ')),
    ['Chưa đến hạn 680 tr', 'Hạn 31/10 0 đ', '1–2 tháng 950 tr', '3–6 tháng 600 tr', '> 6 tháng 250 tr']);
  assert.equal(await strip.locator('.tile').nth(1).isDisabled(), true);
  assert.deepEqual(await strip.locator('.tile b.red').allInnerTexts(), ['600 tr', '250 tr']);
  assert.deepEqual(await strip.locator('.tile b.amber').allInnerTexts(), ['950 tr']);
  // Thu tháng: đã thu / phát sinh, vạch hôm nay 29/31, còn 2 ngày.
  const month = page.locator('.month-card');
  assert.match(await month.locator('.m-nums').innerText(), /186 tr\s+đã thu\s+700 tr\s+phát sinh/);
  assert.equal(await month.locator('.meter .fill').evaluate(el => el.style.width), '26.6%');
  assert.equal(await month.locator('.meter .today').evaluate(el => el.style.left), '94%');
  assert.equal(await month.locator('.left').innerText(), 'còn 2 ngày');
  assert.match(await month.locator('.meter').getAttribute('data-tip'), /^Đã thu 26,6% phát sinh tháng 10/);
  // Chip: số khách + tiền quá hạn của mỗi mức; ba chip cộng lại = 4 khách đang nợ; Rủi ro cao = summary của server.
  assert.deepEqual(await seen(page.locator('#chips .rchip')),
    ['Tất cả', 'Rủi ro cao 2 850 tr', 'Theo dõi 1 950 tr', 'Không quá hạn 1']);
  assert.equal(await page.locator('#chips .rchip.all').getAttribute('aria-pressed'), 'true');
  // Bảng: xếp theo tiền quá hạn; tiền triệu không đơn vị (đơn vị ở đầu cột); quá hạn 0 là "–"; ô ngày là số, null là "chưa".
  assert.deepEqual(await page.locator('#list .nm').allInnerTexts(), ['Khách C', 'Khách D', 'Khách E', 'Khách A']);
  assert.deepEqual(await page.locator('#list .num.od').allInnerTexts(), ['950', '600', '250', '–']);
  assert.deepEqual(await page.locator('#list .num.tot').allInnerTexts(), ['1.250', '600', '250', '380']);
  assert.deepEqual(await page.locator('#list .days').allInnerTexts(), ['27', '3', 'chưa', '162', '963', 'chưa', '9', '4']);
  assert.deepEqual(await page.locator('#list .days.bad').allInnerTexts(), ['chưa', '162', '963', 'chưa']);
  assert.deepEqual(await seen(page.locator('.dtable thead th')), ['Khách', 'Theo hạn trả', 'Quá hạn tr', 'Còn nợ tr', 'Trả ngày', 'Đi hàng ngày', '']);
  assert.equal(await page.locator('#list .rdot.r-high').count(), 2);
  assert.deepEqual(await tipLines(page.locator('#list tr').nth(1)), ['Khách D', 'Rủi ro cao — Nợ từ T5/2026 · chưa trả lần nào · ngừng đi hàng',
    'Còn nợ 600.000.000 đ', 'Bấm để mở Tình hình']);
  assert.deepEqual(await page.locator('#com-filter option').allInnerTexts(), ['Mọi mặt hàng', 'Chuối', 'Sầu riêng cảng', 'Chưa phân loại']);
  assert.equal(await page.locator('#list-more').innerText(), '');
  assert.equal(await page.locator('#todo-badge').innerText(), '3');
  // 1280×720 (thấy ~1280×560): dải đầu và dòng khách đầu nằm trong màn; không cuộn ngang; nút bấm cao ≥ 40px.
  const layout = await page.evaluate(() => ({ stripBottom: document.querySelector('.strip').getBoundingClientRect().bottom,
    firstRow: document.querySelector('#list tr').getBoundingClientRect().bottom,
    small: [...document.querySelectorAll('#refresh-data, .tile, .rchip, .com-pick, .list-head .icon-btn, .who a')]
      .filter(el => el.getBoundingClientRect().height < 40).map(el => el.className || el.id) }));
  assert.equal(layout.stripBottom <= 560 && layout.firstRow <= 560 && layout.small.length === 0, true, JSON.stringify(layout));
  assert.equal(await noSideScroll(page), true);
  await page.locator('#customer-search').fill('Khách C');
  assert.equal(await page.locator('#customer-results a').getAttribute('href'), '/so-khach-v7-live.html?customer=2');
  await page.locator('#customer-search').fill('');
  await page.setViewportSize({ width: 390, height: 844 });
  assert.equal(await noSideScroll(page), true);
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
  await page.locator('.strip .big-money').waitFor();
  assert.match(await page.locator('.owe').innerText(), /0 đ[\s\S]*Chưa có khách đang nợ/);
  assert.deepEqual(await seen(page.locator('.owe-row .pill')), ['0']);
  assert.equal(await page.locator('.tile').count(), 0);
  assert.match(await page.locator('.m-nums').innerText(), /0 đ\s+đã thu\s+0 đ\s+phát sinh/);
  assert.equal(await page.locator('.meter .fill').evaluate(el => el.style.width), '0%');
  assert.equal(await page.locator('#list-empty').innerText(), 'Không có khách đang nợ.');
  assert.deepEqual(await seen(page.locator('#chips .rchip')),
    ['Tất cả', 'Rủi ro cao 0', 'Theo dõi 0', 'Không quá hạn 0']);
  assert.equal(await page.locator('#todo-badge').isHidden(), true);
}));

test('Làm mới đọc số mới và ghi giờ cập nhật', async () => {
  let amount = '2480000000';
  await withDashboard({ payload: () => ({ ...dashboard, receivable: { ...dashboard.receivable, total_vnd: amount } }) }, async page => {
    await page.locator('.strip .big-money').waitFor();
    amount = '2480000001';
    await page.locator('#refresh-data').click();
    await page.waitForFunction(() => document.querySelector('.big-money')?.dataset.tip.endsWith('2.480.000.001 đ'));
    assert.match(await page.locator('#as-of').innerText(), /^\d{2}:\d{2}$/);
    assert.match(await page.locator('#as-of').getAttribute('data-tip'), /^Số liệu đến 29\/10\/2026\nCập nhật .* tự tải mỗi 60 giây$/);
    assert.match(await page.locator('#updated-at').textContent(), /Cập nhật .* tự tải mỗi 60 giây/);
  });
});

test('lỗi API tổng quan: báo lỗi, không để chữ đang tải', async () => withDashboard({ dashboardStatus: 503 }, async page => {
  await page.locator('#error').waitFor({ state: 'visible' });
  assert.match(await page.locator('#error').innerText(), /Không tải được tổng quan công nợ/);
  assert.equal(await page.locator('#dashboard').innerText(), '');
}));

// Audit UX 31/10/2026 (P1-6): mất mạng khi tải trang chỉ hiện một câu tiếng Việt và nút Thử lại; không bao giờ hiện chữ của trình duyệt.
test('mất mạng khi tải Tổng quan và Việc cần làm: câu tiếng Việt, nút Thử lại tải lại', async () => {
  for (const [page, sentence, ready] of [['/dashboard-v7.html', 'Không tải được tổng quan công nợ', '.strip .big-money'],
    ['/viec-can-lam.html', 'Không tải được việc cần làm', '.work-row']]) {
    const drop = new Set(['/api/v7/dashboard']);
    await withPage({ drop }, async tab => {
      await tab.locator('#error').waitFor({ state: 'visible' });
      const text = await tab.locator('#error').innerText();
      assert.match(text, new RegExp(`^${sentence}\\. Kiểm tra mạng rồi bấm Thử lại\\.\\s*Thử lại$`));
      assert.doesNotMatch(text, /fetch|TypeError|HTTP/i);
      drop.clear();
      await tab.locator('#error').getByRole('button', { name: 'Thử lại' }).click();
      await tab.locator(ready).first().waitFor();
      assert.equal(await tab.locator('#error').isHidden(), true);
    }, page);
  }
});

test('chưa có phần quá hạn (API debt lỗi) hay tìm khách lỗi: số tổng vẫn đọc được', async () => {
  await withDashboard({ debtStatus: 503 }, async page => {
    await page.locator('.strip .big-money').waitFor();
    assert.match(await page.locator('.owe').innerText(), /2,48 tỷ[\s\S]*Chưa tải được phần quá hạn/);
    assert.equal(await page.locator('.meter').count(), 0);
    assert.match(await page.locator('.month-card').innerText(), /Thu tháng 10[\s\S]*Chưa tải được số thu tháng này/);
    assert.equal(await page.locator('#list-empty').innerText(), 'Chưa tải được danh sách khách. Bấm Làm mới để thử lại.');
    assert.equal(await page.locator('#chips').isHidden(), true);
    assert.equal(await page.locator('#com-pick').isHidden(), true);
    assert.equal(await page.locator('#error').isHidden(), true);
  });
  await withDashboard({ customerStatus: 503 }, async page => {
    await page.locator('#list tr').first().waitFor();
    assert.deepEqual(await page.locator('#list .nm').allInnerTexts(), ['Khách C', 'Khách D', 'Khách E', 'Khách A']);
    assert.equal(await page.locator('#error').isHidden(), true);
  });
});

test('tên Sheet trên bảng; bấm tên hoặc dòng khách mở trang khách thẻ Tình hình (DASH-05)', async () => withDashboard({
  customers: [
    { id: 1, name: 'AG -DỪA', display_name: 'AG LOGISTIC', commodity: 'Dừa', aliases: ['AG DU A'] },
    { id: 2, name: 'Khách C', display_name: 'CHAU HAI THINH', commodity: 'Chuối', aliases: [] },
    { id: 3, name: 'Khách K', display_name: 'CHAU HAI THINH', commodity: 'Chuối', aliases: [] },
  ],
}, async page => {
  await page.locator('#list .nm').getByText('AG LOGISTIC', { exact: true }).waitFor();
  assert.equal(await page.locator('#list .nm').first().innerText(), 'CHAU HAI THINH · Chuối · sổ 2');
  assert.deepEqual(await page.locator('#list .who a').evaluateAll(links => links.map(link => link.getAttribute('href'))), [
    '/so-khach-v7-live.html?customer=2&the=tinh-hinh', '/so-khach-v7-live.html?customer=4&the=tinh-hinh',
    '/so-khach-v7-live.html?customer=5&the=tinh-hinh', '/so-khach-v7-live.html?customer=1&the=tinh-hinh']);
  // Ô chú thích khi focus bằng bàn phím: tên, mức rủi ro — lý do, số đồng còn nợ.
  await page.locator('#list .who a').first().focus();
  const tip = await page.locator('#tip > *').allTextContents();
  assert.deepEqual(tip, ['CHAU HAI THINH · Chuối · sổ 2', 'Theo dõi — Nợ T8/2026 quá hạn · có trả 02/10', 'Còn nợ 1.250.000.000 đ', 'Bấm để mở Tình hình']);
  await page.locator('#customer-search').fill('AG DU A');
  assert.equal(await page.locator('#customer-results a').innerText(), 'AG LOGISTIC · Dừa');
  await page.locator('#customer-search').fill('');
  await page.locator('#list tr').nth(1).locator('.num.tot').click();
  await page.waitForURL(/\/so-khach-v7-live\.html\?customer=4&the=tinh-hinh$/);
}));

test('lọc tại chỗ: nhóm hạn trả + mức rủi ro + mặt hàng kết hợp, dải đầu giữ nguyên, địa chỉ trang', async () => withDashboard({}, async page => {
  await page.locator('#list tr').first().waitFor();
  const owe = await page.locator('.owe-row').innerText();
  await page.locator('.tile[data-tier="3"]').click();
  assert.deepEqual(await page.locator('#list .nm').allInnerTexts(), ['Khách D']);
  assert.equal(await page.locator('#col-first').innerText(), 'Nhóm này');
  assert.equal(await page.locator('.tile[data-tier="3"]').getAttribute('aria-pressed'), 'true');
  assert.equal(await page.locator('.age-bar .dim').count(), 3);
  assert.equal((await page.locator('#chips .tier-x').innerText()).trim(), '3–6 tháng');
  assert.equal(await page.locator('#chips .tier-x').getAttribute('aria-label'), 'Bỏ lọc Quá hạn 3–6 tháng');
  assert.match(await page.evaluate(() => location.search), /han=3/);
  await page.locator('.age-bar [data-tier="2"]').click();
  assert.deepEqual(await page.locator('#list .nm').allInnerTexts(), ['Khách C']);
  await page.locator('#chips [data-risk="high"]').click();
  assert.equal(await page.locator('#list tr').count(), 0);
  assert.equal(await page.locator('#list-empty').innerText(), 'Không có khách nào khớp bộ lọc.');
  await page.locator('#chips .tier-x').click();
  assert.deepEqual(await page.locator('#list .nm').allInnerTexts(), ['Khách D', 'Khách E']);
  assert.equal(await page.locator('#col-first').innerText(), 'Quá hạn');
  assert.equal(await page.locator('#chips [data-risk="high"]').getAttribute('aria-pressed'), 'true');
  assert.equal(await page.evaluate(() => location.search), '?muc=cao');
  assert.equal(await page.locator('.owe-row').innerText(), owe);
  await page.locator('[data-sort="total"]').click();
  assert.equal(await page.locator('th[data-col="total"]').getAttribute('aria-sort'), 'descending');
  assert.match(await page.evaluate(() => location.search), /xep=tong/);
  // Lọc mặt hàng cộng thêm vào mức rủi ro; xếp theo cột ngày: chưa trả / chưa có chuyến coi là lâu nhất.
  await page.locator('#com-filter').selectOption('Chưa phân loại');
  assert.deepEqual(await page.locator('#list .nm').allInnerTexts(), ['Khách D', 'Khách E']);
  assert.match(await page.evaluate(() => location.search), /mh=Ch/);
  await page.locator('[data-sort="pay"]').click();
  assert.deepEqual(await page.locator('#list .nm').allInnerTexts(), ['Khách D', 'Khách E']);
  await page.locator('[data-sort="trip"]').click();
  assert.deepEqual(await page.locator('#list .nm').allInnerTexts(), ['Khách E', 'Khách D']);
  assert.match(await page.evaluate(() => location.search), /xep=di-hang/);
  await page.locator('#chips [data-risk="ok"]').click();
  assert.equal(await page.locator('#list tr').count(), 0);
  await page.locator('#com-filter').selectOption('');
  assert.deepEqual(await page.locator('#list .nm').allInnerTexts(), ['Khách A']);
  await page.locator('#chips .rchip.all').click();
  assert.equal(await page.locator('#list tr').count(), 4);
  assert.equal(await page.evaluate(() => location.search), '?xep=di-hang');
  // Chú thích ô hạn trả: tên đủ + tháng nợ, tiền · số khách · %, số đồng.
  await page.locator('.tile[data-tier="4"]').hover();
  assert.deepEqual((await page.locator('#tip > *').allTextContents()).slice(0, 3), ['Quá hạn trên 6 tháng (nợ T2 trở về trước)', '250 tr · 1 khách · 10,1% còn phải thu', '250.000.000 đ']);
  await page.setViewportSize({ width: 390, height: 844 });
  assert.equal(await noSideScroll(page), true);
}));

test('link có sẵn ?han=&muc= mở đúng lọc; tham số cũ (ô ma trận, ngăn kéo) bị bỏ qua và xóa khỏi địa chỉ', async () => withDashboard({}, async page => {
  await page.locator('#list tr').first().waitFor();
  assert.equal(await page.locator('.tile[data-tier="3"]').getAttribute('aria-pressed'), 'true');
  assert.equal(await page.locator('#chips [data-risk="high"]').getAttribute('aria-pressed'), 'true');
  assert.deepEqual(await page.locator('#list .nm').allInnerTexts(), ['Khách D']);
  await page.locator('#chips [data-risk="high"]').click();
  assert.equal(await page.evaluate(() => location.search), '?han=3');
}, '?han=3&muc=cao&nhom=mx%3Ap1t1&khach=4'));

test('số từng khách lệch tổng server: không lọc tại chỗ, bấm nhóm hạn trả sang Công nợ theo tháng', async () => withDashboard({
  debtPayload: { ...debt, due_tiers: debt.due_tiers.map(t => (t.tier === 'not_due' ? { ...t, receivable_vnd: '680000001' } : t)) },
}, async page => {
  await page.locator('#list tr').first().waitFor();
  assert.equal(await page.locator('#chips [data-risk="high"]').isDisabled(), true);
  assert.equal(await page.locator('#com-filter').isDisabled(), true);
  assert.equal(await page.locator('#list-note').innerText(), 'Số từng khách chưa khớp tổng; xem chi tiết ở Công nợ theo tháng.');
  await page.locator('.tile[data-tier="2"]').click();
  await page.waitForURL(/cong-no-theo-thang\.html\?con-no=1&xep=con-no$/);
}, '?han=2'));

test('chip không cộng ra summary của server: khóa lọc tại chỗ, có dòng giải thích', async () => withDashboard({
  debtPayload: { ...debt, summary: { ...debt.summary, high_overdue_vnd: '849999999' } },
}, async page => {
  await page.locator('#list tr').first().waitFor();
  assert.equal(await page.locator('#chips .rchip.all').isDisabled(), true);
  assert.equal(await page.locator('#list-note').isHidden(), false);
}));

test('khách quá hạn âm (dư ở nợ cũ) được trừ đúng vào summary: vẫn lọc tại chỗ, ngoặc Quá hạn ghi phần đã trừ', async () => withDashboard({
  // Khách F: dư 30 triệu ở nợ 3–6 tháng, còn nợ mới 200 triệu; server trừ −30 triệu vào ngoặc Quá hạn.
  debtPayload: { ...debt, receivable_vnd: '2650000000',
    due_tiers: debt.due_tiers.map(t => (t.tier === 'not_due' ? { ...t, receivable_vnd: '880000000' } : t.tier === 'late_3_6' ? { ...t, receivable_vnd: '570000000' } : t)),
    summary: { ...debt.summary, overdue_vnd: '1770000000' },
    customers: [...debt.customers, row(6, 'Khách F', ['200000000', '0', '0', '-30000000', '0'], { risk: 'ok', pay_days: 5, trip_days: 2 })] },
}, async page => {
  await page.locator('#list tr').first().waitFor();
  assert.equal(await page.locator('#list-note').isHidden(), true);
  assert.match(await page.locator('.brk .late').getAttribute('data-tip'), /Đã trừ 1 khách dư ở nợ cũ 30 tr/);
  assert.equal(await page.locator('#com-filter').isDisabled(), false);
  await page.locator('#chips [data-risk="ok"]').click();
  assert.deepEqual(await page.locator('#list .nm').allInnerTexts(), ['Khách A', 'Khách F']);
  assert.deepEqual(await page.locator('#list .num.od').allInnerTexts(), ['–', '−30']);
}));

test('link cũ ?nhom=com: mở lọc mặt hàng, ?xem= cũ bị xóa khỏi địa chỉ', async () => withDashboard({}, async page => {
  await page.locator('#list tr').first().waitFor();
  assert.equal(await page.locator('#com-filter').inputValue(), 'Chuối');
  assert.equal(await page.locator('#list tr').count(), 1);
  await page.locator('[data-sort="total"]').click();
  assert.doesNotMatch(await page.evaluate(() => location.search), /xem=|nhom=/);
}, '?nhom=com%3AChu%E1%BB%91i&xem=pay'));

test('hơn 10 khách: hiện 10 dòng, nút "Hiện cả N khách" mở hết tại chỗ', async () => withDashboard({
  debtPayload: { ...debt, customers: [...debt.customers, ...Array.from({ length: 8 }, (_, i) => row(20 + i, `Khách N${i}`, ['10000000', '0', '0', '0', '0'], { risk: 'ok', pay_days: 3, trip_days: 3 }))] },
}, async page => {
  await page.locator('#list tr').first().waitFor();
  assert.equal(await page.locator('#list tr').count(), 10);
  const more = page.locator('#list-more button');
  assert.equal(await more.innerText(), 'Hiện cả 12 khách');
  assert.ok((await more.boundingBox()).height >= 40);
  await more.click();
  assert.equal(await page.locator('#list tr').count(), 12);
  assert.equal(await page.locator('#list-more').innerText(), '');
}));

test('đầu tháng: còn 28 ngày, vạch hôm nay gần đầu thước, tháng chưa phát sinh không có tỉ lệ', async () => withDashboard({
  debtPayload: { ...debt, as_of: '2026-11-02', month: '2026-11-01', this_month: { month: '2026-11-01', charges_vnd: '0', received_vnd: '0' } },
}, async page => {
  await page.locator('.meter .today').waitFor();
  assert.equal(await page.locator('.month-card h2').innerText(), 'Thu tháng 11');
  assert.equal(await page.locator('.month-card .left').innerText(), 'còn 28 ngày');
  assert.equal(await page.locator('.meter .today').evaluate(el => el.style.left), '7%');
  assert.match(await page.locator('.meter').getAttribute('data-tip'), /^Tháng 11 chưa phát sinh\nVạch đen: hôm nay 2\/11$/);
  assert.equal(await page.locator('.tile[data-tier="1"] .tl').innerText(), 'Hạn 30/11');
}));

test('PRESENCE-01: chấm màu cạnh khách đang có người mở sổ, vòng tròn người online', async () => withDashboard({ people: [
  { id: 'p1', name: 'Lan', color: 0, page: 'so-khach', customer_id: 1, month: '2026-10', cell: null, pointer: null },
  { id: 'p2', name: 'Tuấn', color: 3, page: 'so-khach', customer_id: 2, month: '2026-09', cell: null, pointer: null },
] }, async page => {
  await page.locator('#list a[href*="customer=1&"] .presence-dot').waitFor();
  assert.equal(await page.locator('#list a[href*="customer=1&"] .presence-dot').getAttribute('aria-label'), 'Lan đang mở sổ này');
  const labels = await page.locator('.presence-avatar').evaluateAll(nodes => nodes.map(node => node.getAttribute('aria-label')));
  assert.deepEqual(labels, ['Lan · đang mở sổ Khách A, tháng 10/2026', 'Tuấn · đang mở sổ Khách C, tháng 9/2026']);
}));

// Bố cục nhóm cũ thay bằng bảng bốn cột; các ca tải/lọc/trống/lỗi/mở sổ nằm trong test-viec-can-lam-table-browser.js.
const writable = (id, extra = {}) => inboxBook(id, { version: 3, outstanding_vnd: '1000000000', ...extra,
  receipts: { ready: 1, review: 0, amount_vnd: '50000000', ready_amount_vnd: '50000000', snapshot_sha256: 'c'.repeat(64), locked_months: [],
    items: [{ status: 'READY', date: '2026-10-30', amount_vnd: '50000000', debt_month: '2026-09-01', note: '30/10 tt' }], ...(extra.receipts ?? {}) } });

test('Việc cần làm P2: chọn sổ, xem lại nợ trước → sau, ghi; sổ lỗi ở lại với câu của server', async () => {
  const posted = [];
  let written = false;
  const books = () => [
    ...(written ? [] : [writable(1, { receipts: { ready: 2, amount_vnd: '400000000', ready_amount_vnd: '400000000', locked_months: ['2026-09'],
      items: [{ status: 'READY', date: '2026-09-28', amount_vnd: '300000000', debt_month: '2026-08-01', note: '' },
        { status: 'READY', date: '2026-10-02', amount_vnd: '100000000', debt_month: '2026-09-01', note: 'ck' }] } })]),
    writable(2, { outstanding_vnd: '30000000' }),
    inboxBook(7, { receipts: { ready: 0, review: 1, amount_vnd: '9000000', items: [{ status: 'NO_DATE', date: null, amount_vnd: '9000000', debt_month: '2026-08-01', note: '?' }] } }),
  ];
  await withPage({ viewport: { width: 1280, height: 560 }, posted, inbox: () => ({ ...INBOX_EMPTY, books: books() }),
    receiptPost: body => (body.customer_id === 1 ? (written = true, { status: 200, json: { written: 2, remaining: 0, complete: true, version: 5 } })
      : { status: 409, json: { error: 'STALE_LEDGER', message: 'Sổ đã thay đổi. Tải lại rồi thử tiếp.' } }) }, async page => {
    const group = page.locator('.inbox');
    await group.locator('.work-row').first().waitFor();
    assert.equal(await group.locator('[data-book="7"] input').count(), 0);   // phiếu cần xem: không chọn được
    await group.locator('[data-book="7"] .book-name').click();
    assert.match(await group.locator('.work-detail').innerText(), /Phiếu cần xem[\s\S]*máy không ghi phiếu thiếu ngày/i);
    assert.equal(await group.locator('[data-review]').count(), 0);
    await page.locator('[data-pick-ready]').click();
    // Chọn hết mở ngay bước xem lại như bản thiết kế đã chọn.
    const review = group.locator('.receipt-review');
    const text = await review.innerText();
    assert.match(text, /Xem lại trước khi ghi · 3 phiếu thu ở 2 sổ/);
    assert.match(text, /1\.000 → 600/);
    assert.match(text, /có phiếu ngày trong tháng đang khóa \(T9\): vẫn ghi được/);
    assert.match(text, /khách sẽ dư 20 triệu/);
    assert.equal(await page.evaluate(() => document.activeElement?.hasAttribute('data-write')), true);
    await review.locator('[data-write]').click();
    await page.locator('.inbox-result').waitFor();
    assert.match(await page.locator('.inbox-result').innerText(), /Đã ghi 2 phiếu ở 1 sổ, tổng 400 triệu[\s\S]*1 sổ chưa ghi xong/);
    assert.match(await group.locator('[data-book="2"] .row-error').innerText(), /Sổ đã thay đổi\. Tải lại rồi thử tiếp\./);
    await page.waitForFunction(() => !document.querySelector('[data-book="1"]'));
    assert.deepEqual(posted.map(body => [body.customer_id, body.expected_version, body.snapshot_sha256.length, typeof body.idempotency_key]),
      [[1, 3, 64, 'string'], [2, 3, 64, 'string']]);
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
  }, '/viec-can-lam.html');
});

test('Việc cần làm P2: mất kết nối khi ghi thì Thử lại gửi đúng khóa cũ, không ghi trùng; Thôi đóng khung xem lại', async () => {
  const posted = [];
  await withPage({ posted, inbox: () => ({ ...INBOX_EMPTY, books: [writable(1)] }),
    receiptPost: () => ({ status: 200, json: { written: 1, remaining: 0, complete: true, version: 4 } }) }, async page => {
    // Cắt ngay trong trình duyệt (cắt socket ở server thì Chrome tự gửi lại): lần gửi đầu mất kết nối, ghi lại khóa đã gửi.
    const lost = [];
    await page.route('**/api/v7/sheet/receipts', route => { lost.push(route.request().postDataJSON()); return route.abort(); }, { times: 1 });
    const group = page.locator('.inbox');
    await group.locator('[data-pick="1"]').check();
    await group.locator('[data-review]').click();
    await group.locator('[data-review-cancel]').click();
    assert.equal(await group.locator('.receipt-review').count(), 0);
    await group.locator('[data-review]').click();
    await group.locator('[data-write]').click();
    await page.locator('[data-write-retry]').waitFor();
    assert.match(await group.locator('[data-book="1"] .row-error').innerText(), /Mất kết nối khi ghi: chưa rõ sổ này đã ghi chưa/);
    await page.locator('[data-write-retry]').click();
    await page.waitForFunction(() => document.querySelector('.inbox-result')?.textContent.includes('Đã ghi 1 phiếu'));
    assert.equal(lost.length, 1);
    assert.equal(posted.length, 1);
    assert.equal(posted[0].idempotency_key, lost[0].idempotency_key);
  }, '/viec-can-lam.html');
});

test('Việc cần làm P3a: "Máy đã tự lấy theo Sheet hôm nay" liệt kê ô đã đổi, mở đúng sổ; lệch chữ còn lại ghi rõ máy bật hay chưa', async () => {
  const auto = { text_enabled: true, last_run: '2026-11-01T12:00:00+00:00', errors: 0, today_count: 2, today_books: 1,
    items: [{ at: '2026-11-01T12:00:00+00:00', customer_id: 2, container: 'MAUU0000001', field: 'destination', before: 'CANG C', after: 'CANG D' },
      { at: '2026-11-01T12:00:00+00:00', customer_id: 2, container: 'MAUU0000001', field: 'origin', before: null, after: 'KHO B' }] };
  await withPage({ inbox: { ...INBOX_EMPTY, auto, books: [inboxBook(1, { text_diff: 3 })] } }, async page => {
    await page.locator('[data-auto]').click();
    const done = page.locator('.auto-list');
    await done.waitFor();
    assert.match(await done.innerText(), /Khách C[\s\S]*nơi đến: CANG C → CANG D[\s\S]*nơi đi: — → KHO B/);
    assert.equal(await done.locator('a').first().getAttribute('href'), '/so-khach-v7-live.html?customer=2');
    assert.match(await page.locator('.inbox .inbox-note').innerText(), /3 chỗ ở 1 sổ\. Không đụng tiền; máy lấy theo Sheet ở lượt tính tới/);
  }, '/viec-can-lam.html');
  await withPage({ inbox: { ...INBOX_EMPTY, auto: { ...auto, text_enabled: false, today_count: 0, items: [] }, books: [inboxBook(1, { text_diff: 3 })] } }, async page => {
    await page.locator('.inbox .inbox-note').waitFor();
    assert.match(await page.locator('.inbox .inbox-note').innerText(), /máy chưa bật tự lấy theo Sheet/);
    assert.equal(await page.locator('.auto-list').count(), 0);
  }, '/viec-can-lam.html');
});

test('Việc cần làm P3b: "Máy đã đưa vào sổ hôm nay" liệt kê chuyến mới, đánh dấu chuyến chờ kiểm, mở đúng sổ', async () => {
  const auto = { text_enabled: true, trips_enabled: true, last_run: '2026-11-01T12:00:00+00:00', errors: 0, today_count: 0, today_books: 0,
    items: [], today_trips: 2, today_trip_books: 1, today_trips_pending: 1,
    trip_items: [{ at: '2026-11-01T12:00:00+00:00', kind: 'trip', customer_id: 2, container: 'MAUU0000002', event_date: '2026-11-01', trip_id: 9, pending: false },
      { at: '2026-11-01T12:00:00+00:00', kind: 'trip', customer_id: 2, container: 'MAUU0000003', event_date: '2026-10-31', trip_id: 10, pending: true }] };
  await withPage({ inbox: { ...INBOX_EMPTY, auto, books: [] } }, async page => {
    await page.locator('[data-auto]').click();
    const done = page.locator('.auto-list');
    await done.waitFor();
    assert.equal(await done.count(), 1);   // không có ô chữ thì chỉ một khối
    assert.match(await done.innerText(), /Khách C[\s\S]*MAUU0000002 · 01\/11\/2026[\s\S]*MAUU0000003 · 31\/10\/2026 · chờ kiểm/);
    assert.equal(await done.locator('a').first().getAttribute('href'), '/so-khach-v7-live.html?customer=2');
    assert.equal(await done.locator('li').count(), 2);
  }, '/viec-can-lam.html');
});

test('Việc cần làm MAY-GIA-01: "Máy đã tự làm" liệt kê giá Sheet máy đã ghi, ghi rõ tháng khóa; chip Máy đếm giá riêng', async () => {
  const auto = { text_enabled: true, trips_enabled: true, prices_enabled: true, last_run: '2026-11-01T12:00:00+00:00', errors: 0,
    today_count: 0, today_books: 0, items: [], today_trips: 0, today_trip_books: 0, today_trips_pending: 0, trip_items: [],
    today_prices: 3, today_price_books: 1,
    price_items: [{ at: '2026-11-01T12:00:00+00:00', kind: 'price', customer_id: 2, container: 'MAUU0000004', date: '2026-10-28', month: '2026-10',
      unit_price_vnd: '52500000', other_fee_vnd: '300000', before_unit_price_vnd: null, before_other_fee_vnd: null, locked: true },
    { at: '2026-11-01T12:00:00+00:00', kind: 'price', customer_id: 2, container: 'MAUU0000005', date: '2026-11-01', month: '2026-11',
      unit_price_vnd: '50000000', other_fee_vnd: null, before_unit_price_vnd: null, before_other_fee_vnd: null, locked: false },
    { at: '2026-11-01T12:00:00+00:00', kind: 'price', customer_id: 2, container: 'MAUU0000006', date: '2026-11-01', month: '2026-11',
      unit_price_vnd: '50000000', other_fee_vnd: '-500000', before_unit_price_vnd: '50000000', before_other_fee_vnd: '-300000', locked: false }] };
  await withPage({ inbox: { ...INBOX_EMPTY, auto, books: [] } }, async page => {
    const chip = page.locator('.actor-chip', { hasText: 'Máy' });
    assert.equal(await chip.getAttribute('title'), 'Máy theo Sheet hôm nay: 0 chuyến mới, 0 ô chữ, 3 giá');
    await page.locator('[data-auto]').click();
    const done = page.locator('.auto-list');
    await done.waitFor();
    assert.equal(await done.locator('li').count(), 3);
    // Đụng tiền nên ghi trước → sau: chuyến chưa giá nhận giá Sheet; chuyến đã có giá chỉ đổi giảm trừ.
    assert.match(await done.locator('li').nth(0).innerText(), /Khách C[\s\S]*MAUU0000004 · 28\/10\/2026 · chưa giá → 52,5 tr, phụ phí 0,3 tr · tháng khóa/);
    const open = await done.locator('li').nth(1).innerText();
    assert.match(open, /MAUU0000005 · 01\/11\/2026 · chưa giá → 50 tr/);
    assert.doesNotMatch(open, /phụ phí|tháng khóa/);
    assert.match(await done.locator('li').nth(2).innerText(), /MAUU0000006 · 01\/11\/2026 · 50 tr, phụ phí −0,3 → −0,5 tr/);
    if (process.env.SHOTS_DIR) {
      fs.mkdirSync(process.env.SHOTS_DIR, { recursive: true });
      await page.screenshot({ path: path.join(process.env.SHOTS_DIR, 'viec-can-lam-may-ghi-gia.png') });
    }
    assert.equal(await done.locator('a').first().getAttribute('href'), '/so-khach-v7-live.html?customer=2');
  }, '/viec-can-lam.html');
});
