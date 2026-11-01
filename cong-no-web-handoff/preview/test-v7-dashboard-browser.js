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
// Audit UX 31/10/2026 P0-3: ở 1280×720 mỗi mục điều hướng một dòng — chữ của mục (không tính huy hiệu) cao ≤ 24px.
const navLineHeights = page => page.locator('.topbar nav a').evaluateAll(links => links.map(link => {
  const range = document.createRange();
  range.selectNodeContents(link.firstChild);
  return Math.round(range.getBoundingClientRect().height);
}));
const assertNavOneLine = async page => {
  const heights = await navLineHeights(page);
  assert.equal(heights.length === 5 && heights.every(height => height <= 24), true, JSON.stringify(heights));
};

test('Tổng quan chỉ còn bốn khối về công nợ; số chính, hạn trả, khách cần đòi, ma trận; màn đầu và điện thoại', async () => withDashboard({}, async page => {
  await page.locator('.due .big-money').waitFor();
  await page.locator('#list .drow').first().waitFor();
  for (const heading of [/^Còn phải thu/, 'Thu tháng 10', 'Khách cần đòi trước', 'Khách quá hạn đang ở đâu'])
    assert.equal(await page.getByRole('heading', { name: heading }).count(), 1);
  for (const heading of ['Việc cần làm', 'Hôm nay', 'Theo mặt hàng', 'Khách nợ nhiều nhất', 'Nợ theo hạn trả', 'Phân loại khách đang nợ'])
    assert.equal(await page.getByRole('heading', { name: heading }).count(), 0);
  // 1. Số headline trên tiêu đề, số đồng đầy đủ chỉ ở tooltip (DASH-04: số nằm trong hình, không câu kết luận).
  assert.equal(await page.locator('.due .big-money').innerText(), '2,48 tỷ');
  assert.equal(await page.locator('.due .big-money').getAttribute('title'), '2.480.000.000 đ');
  assert.match(await page.locator('.due h2').innerText(), /4 khách đang nợ/);
  assert.equal(await page.locator('.age-note, .minis, .age-legend .p').count(), 0);
  // Thanh hạn trả: nhóm trống không vẽ; số ghi trong đoạn rộng; ngoặc trong hạn / quá hạn; nhãn + tháng nợ thẳng hàng dưới đoạn.
  assert.deepEqual(await page.locator('.age-bar span').allInnerTexts(), ['680 triệu', '950 triệu', '600 triệu', '250 triệu']);
  assert.match(await page.locator('.brk').innerText(), /Trong hạn\s+680 triệu[\s\S]*Quá hạn\s+1,8 tỷ\s+· 72,6% · 3 khách/);
  assert.deepEqual(await page.locator('.age-legend .lab button').allInnerTexts(), ['Chưa đến hạn\nnợ T10', '1–2 tháng\nnợ T7–T8', '3–6 tháng\nnợ T3–T6', 'Trên 6 tháng\nnợ T2 trở về trước']);
  assert.equal(await page.locator('.age-legend .tiny').count(), 0);
  // 2. Thu tháng này: thước đo đã thu / phát sinh, vạch hôm nay 29/31; chú thích thiếu giá, khách dư giữ nguyên.
  assert.match(await page.locator('.month .mrow').innerText(), /186 triệu\s+đã thu · 26,6%\s+700 triệu\s+phát sinh tháng này/);
  assert.equal(await page.locator('.meter .fill').evaluate(el => el.style.width), '26.6%');
  assert.equal(await page.locator('.meter .today').evaluate(el => el.style.left), '94%');
  assert.equal(await page.locator('.hero-foot').innerText(), 'Chưa tính 3 chuyến thiếu đơn giá · 3 khách đang dư 125 triệu, tính riêng');
  // 3. Khách cần đòi: xếp theo tiền quá hạn; chấm màu mức rủi ro, hai cột số ngày tô theo ngưỡng; lý do bằng chữ ở title.
  assert.deepEqual(await page.locator('#list .nm').allInnerTexts(), ['Khách C', 'Khách D', 'Khách E', 'Khách A']);
  assert.deepEqual(await page.locator('#list .num.od').allInnerTexts(), ['0,95', '0,60', '0,25', '0,00']);
  assert.deepEqual(await page.locator('#list .days').allInnerTexts(), ['27 ngày', '3 ngày', 'chưa trả', '5 tháng', '32 tháng', 'chưa có', '9 ngày', '4 ngày']);
  assert.deepEqual(await page.locator('#list .days.bad').allInnerTexts(), ['chưa trả', '5 tháng', '32 tháng', 'chưa có']);
  assert.equal(await page.locator('#list .dot.r-high').count(), 2);
  assert.equal(await page.locator('#list .drow').nth(1).getAttribute('title'), 'Rủi ro cao — Nợ từ T5/2026 · chưa trả lần nào · ngừng đi hàng');
  assert.equal(await page.locator('#list-aside').innerText(), '3/4 khách có nợ quá hạn · tỷ đồng');
  assert.match(await page.locator('#list-legend').innerText(), /Rủi ro cao\s+Theo dõi\s+ngày đỏ: chưa trả > 60 · không đi hàng > 90/);
  assert.deepEqual(await page.locator('#com-filter option').allInnerTexts(), ['Mặt hàng: tất cả', 'Chuối · 1', 'Sầu riêng cảng · 1', 'Chưa phân loại · 2']);
  // 4. Ma trận 2×2: chỉ khách có nợ quá hạn; chưa trả lần nào / chưa có chuyến vào ô xấu; tổng = 3 khách quá hạn.
  assert.deepEqual(await page.locator('#mx .h').allInnerTexts(), ['Có trả trong 60 ngày', 'Trên 60 ngày chưa trả']);
  assert.deepEqual(await page.locator('#mx .c').allInnerTexts(), ['1 khách\nquá hạn 950 triệu', '0 khách\n—', '0 khách\n—', '2 khách\nquá hạn 850 triệu']);
  assert.equal(await page.locator('#mx .c.h2').count(), 1);
  assert.equal(await page.locator('#todo-badge').innerText(), '3');
  assert.equal(await page.locator('nav a[href="/viec-can-lam.html"]').count(), 1);
  const layout = await page.evaluate(() => ({ scrollX: document.documentElement.scrollWidth > innerWidth,
    firstRowBottom: Math.max(...[...document.querySelectorAll('.due,.month')].map(el => el.getBoundingClientRect().bottom)) }));
  assert.equal(!layout.scrollX && layout.firstRowBottom <= 720, true, JSON.stringify(layout));
  await assertNavOneLine(page);
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
  await page.locator('.due .big-money').waitFor();
  assert.match(await page.locator('.due').innerText(), /0 đ[\s\S]*Chưa có khách đang nợ/);
  assert.equal(await page.locator('.hero-foot').count(), 0);
  assert.equal(await page.locator('.age-bar span').count(), 0);
  assert.match(await page.locator('.month').innerText(), /0 đ\s+đã thu\s+0 đ\s+chưa phát sinh/);
  assert.equal(await page.locator('.meter .fill').evaluate(el => el.style.width), '0%');
  assert.match(await page.locator('#list').innerText(), /Không có khách đang nợ/);
  assert.deepEqual(await page.locator('#mx .c b').allInnerTexts(), ['0 khách', '0 khách', '0 khách', '0 khách']);
  assert.equal(await page.locator('#todo-badge').isHidden(), true);
}));

test('Làm mới đọc số mới và ghi giờ cập nhật', async () => {
  let amount = '2480000000';
  await withDashboard({ payload: () => ({ ...dashboard, receivable: { ...dashboard.receivable, total_vnd: amount } }) }, async page => {
    await page.locator('.due .big-money').waitFor();
    amount = '2480000001';
    await page.locator('#refresh-data').click();
    await page.locator('.due .big-money[title="2.480.000.001 đ"]').waitFor();
    assert.match(await page.locator('#updated-at').innerText(), /Cập nhật .* tự tải mỗi 60 giây/);
  });
});

test('lỗi API tổng quan: báo lỗi, không để chữ đang tải', async () => withDashboard({ dashboardStatus: 503 }, async page => {
  await page.locator('#error').waitFor({ state: 'visible' });
  assert.match(await page.locator('#error').innerText(), /Không tải được tổng quan công nợ/);
  assert.equal(await page.locator('#dashboard').innerText(), '');
}));

// Audit UX 31/10/2026 (P1-6): mất mạng khi tải trang chỉ hiện một câu tiếng Việt và nút Thử lại; không bao giờ hiện chữ của trình duyệt.
test('mất mạng khi tải Tổng quan và Việc cần làm: câu tiếng Việt, nút Thử lại tải lại', async () => {
  for (const [page, sentence, ready] of [['/dashboard-v7.html', 'Không tải được tổng quan công nợ', '.due .big-money'],
    ['/viec-can-lam.html', 'Không tải được việc cần làm', '.todo .todo-group']]) {
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
    await page.locator('.due .big-money').waitFor();
    assert.match(await page.locator('.due').innerText(), /2,48 tỷ\s*4 khách đang nợ[\s\S]*Chưa tải được phần quá hạn/);
    assert.equal(await page.locator('.meter').count(), 0);
    assert.match(await page.locator('.month').innerText(), /Chưa tải được số thu tháng này[\s\S]*Chưa tính 3 chuyến thiếu đơn giá/);
    assert.match(await page.locator('#list').innerText(), /Chưa tải được danh sách khách quá hạn/);
    assert.equal(await page.locator('#com-filter').isHidden(), true);
    assert.match(await page.locator('.matrix').innerText(), /Chưa tải được phân loại khách/);
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
  // TRANG-KHACH-01 (PR A4): "Trang khách" cạnh "Mở sổ khách", mở thẻ Tình hình; ba nút một dòng, cao ≥ 40px.
  assert.equal(await page.locator('#d-page').getAttribute('href'), '/so-khach-v7-live.html?customer=2&the=tinh-hinh');
  assert.equal(await page.locator('#d-matrix').getAttribute('href'), '/cong-no-theo-thang.html?con-no=1&xep=con-no&khach=2');
  const footer = await page.locator('#drawer footer').evaluate(node => [...node.querySelectorAll('a')].map(link => {
    const box = link.getBoundingClientRect(), range = document.createRange();
    range.selectNodeContents(link);
    return { text: link.textContent, top: box.top, tall: box.height >= 40, inside: box.right <= node.getBoundingClientRect().right,
      oneLine: range.getClientRects().length === 1, fits: link.scrollWidth <= link.clientWidth + 1 };
  }));
  assert.deepEqual(footer.map(link => link.text), ['Mở sổ khách', 'Trang khách', 'Xem ở ma trận']);
  assert.equal(footer.every(link => link.top === footer[0].top && link.tall && link.inside && link.oneLine && link.fits), true, JSON.stringify(footer));
  assert.match(await page.locator('#d-body').innerText(), /3 chuyến thiếu đơn giá — chưa tính vào số trên/);
  await page.keyboard.press('Escape');
  await page.locator('#drawer').waitFor({ state: 'hidden' });
  await page.locator('#customer-search').fill('AG DU A');
  assert.equal(await page.locator('#customer-results a').innerText(), 'AG LOGISTIC · Dừa');
}));

test('lọc tại chỗ: nhóm hạn trả + ô ma trận + mặt hàng kết hợp, số tổng giữ nguyên, ngăn kéo và địa chỉ trang', async () => withDashboard({}, async page => {
  await page.locator('#list .drow').first().waitFor();
  const receivable = await page.locator('.due').innerText();
  await page.locator('.age-legend [data-tier="3"]').click();
  assert.equal(await page.locator('#h-list').innerText(), '1 khách theo lọc');
  assert.deepEqual(await page.locator('#list .nm').allInnerTexts(), ['Khách D']);
  assert.equal(await page.locator('#col-first').innerText(), 'Nợ nhóm này');
  assert.match(await page.locator('#filterbar').innerText(), /Nợ quá hạn 3–6 tháng/);
  assert.match(await page.evaluate(() => location.search), /han=3/);
  await page.locator('.age-bar [data-tier="2"]').click();
  assert.deepEqual(await page.locator('#list .nm').allInnerTexts(), ['Khách C']);
  await page.locator('[data-cls="mx:p1t1"]').click();
  assert.equal(await page.locator('#h-list').innerText(), '0 khách theo lọc');
  assert.match(await page.locator('#list').innerText(), /Không có khách nào khớp lọc này/);
  await page.locator('[data-clear="tier"]').click();
  assert.deepEqual(await page.locator('#list .nm').allInnerTexts(), ['Khách D', 'Khách E']);
  assert.match(await page.locator('#filterbar').innerText(), /Khách: trên 60 ngày chưa trả · ngừng đi hàng > 90 ngày/);
  assert.match(await page.evaluate(() => location.search), /nhom=mx%3Ap1t1/);
  assert.equal(await page.locator('.due').innerText(), receivable);
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
  // Lọc mặt hàng cộng thêm vào ô ma trận đang chọn; xếp theo cột ngày: chưa trả lần nào coi là lâu nhất.
  await page.locator('#com-filter').selectOption('Chưa phân loại');
  assert.deepEqual(await page.locator('#list .nm').allInnerTexts(), ['Khách D', 'Khách E']);
  assert.match(await page.locator('#filterbar').innerText(), /Mặt hàng: Chưa phân loại/);
  assert.match(await page.evaluate(() => location.search), /mh=Ch/);
  await page.locator('[data-sort="pay"]').click();
  assert.deepEqual(await page.locator('#list .nm').allInnerTexts(), ['Khách D', 'Khách E']);
  await page.locator('[data-sort="trip"]').click();
  assert.deepEqual(await page.locator('#list .nm').allInnerTexts(), ['Khách E', 'Khách D']);
  assert.match(await page.evaluate(() => location.search), /xep=di-hang/);
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
  assert.equal(await page.locator('[data-cls="mx:p1t1"]').getAttribute('aria-pressed'), 'true');
  await page.keyboard.press('Escape');
  assert.equal(await page.locator('#drawer').isHidden(), true);
  assert.equal(await page.evaluate(() => location.search), '?han=3&nhom=mx%3Ap1t1');
}, '?han=3&nhom=mx%3Ap1t1&khach=4'));

test('số từng khách lệch tổng server: không lọc tại chỗ, bấm nhóm hạn trả sang Công nợ theo tháng', async () => withDashboard({
  debtPayload: { ...debt, due_tiers: debt.due_tiers.map(t => (t.tier === 'not_due' ? { ...t, receivable_vnd: '680000001' } : t)) },
}, async page => {
  await page.locator('#list .drow').first().waitFor();
  assert.equal(await page.locator('#mx .c').first().isDisabled(), true);
  assert.equal(await page.locator('#com-filter').isDisabled(), true);
  assert.equal(await page.locator('#mx .mx-note').innerText(), 'Số từng khách chưa khớp tổng; xem chi tiết ở Công nợ theo tháng.');
  await page.locator('.age-legend [data-tier="2"]').click();
  await page.waitForURL(/cong-no-theo-thang\.html\?con-no=1&xep=con-no$/);
}, '?han=2'));

test('ma trận không cộng ra ngoặc Quá hạn (quá hạn âm ở server): không lọc tại chỗ, có dòng giải thích', async () => withDashboard({
  debtPayload: { ...debt, summary: { ...debt.summary, overdue_vnd: '1799999900' } },
}, async page => {
  await page.locator('#mx .c').first().waitFor();
  assert.equal(await page.locator('#mx .c').first().isDisabled(), true);
  assert.equal(await page.locator('#mx .mx-note').count(), 1);
}));

test('khách quá hạn âm (dư ở nợ cũ) được trừ đúng vào summary: vẫn lọc tại chỗ, ma trận ghi phần chưa trừ', async () => withDashboard({
  // Khách F: dư 30 triệu ở nợ 3–6 tháng, còn nợ mới 200 triệu; server trừ −30 triệu vào ngoặc Quá hạn.
  debtPayload: { ...debt, receivable_vnd: '2650000000',
    due_tiers: debt.due_tiers.map(t => (t.tier === 'not_due' ? { ...t, receivable_vnd: '880000000' } : t.tier === 'late_3_6' ? { ...t, receivable_vnd: '570000000' } : t)),
    summary: { ...debt.summary, overdue_vnd: '1770000000' },
    customers: [...debt.customers, row(6, 'Khách F', ['200000000', '0', '0', '-30000000', '0'], { risk: 'ok', pay_days: 5, trip_days: 2 })] },
}, async page => {
  await page.locator('#mx .c').first().waitFor();
  assert.equal(await page.locator('#mx .mx-note').count(), 0);
  assert.equal(await page.locator('#mx .mx-credit').innerText(), 'Tổng ô 1,8 tỷ: chưa trừ 1 khách dư ở nợ cũ 30 triệu.');
  assert.equal(await page.locator('#com-filter').isDisabled(), false);
  await page.locator('[data-cls="mx:p1t1"]').click();
  assert.equal(await page.locator('#list .drow').count(), 2);
  await page.locator('.age-legend [data-tier="2"]').click();
  assert.match(await page.evaluate(() => location.search), /han=2/);
  assert.equal(await page.locator('#filterbar').isHidden(), false);
}));

test('link cũ ?nhom=com: mở lọc mặt hàng, ?xem= cũ bị xóa khỏi địa chỉ', async () => withDashboard({}, async page => {
  await page.locator('#list .drow').first().waitFor();
  assert.equal(await page.locator('#com-filter').inputValue(), 'Chuối');
  assert.equal(await page.locator('#list .drow').count(), 1);
  assert.equal(await page.locator('#mx .mx-note').count(), 0);
  await page.locator('[data-sort="total"]').click();
  assert.doesNotMatch(await page.evaluate(() => location.search), /xem=/);
}, '?nhom=com%3AChu%E1%BB%91i&xem=pay'));

test('đoạn hẹp dưới 7% không ghi số trong thanh, liệt kê một dòng dưới thanh', async () => withDashboard({
  debtPayload: { ...debt, receivable_vnd: '2330000000',
    due_tiers: debt.due_tiers.map(t => (t.tier === 'late_over_6' ? { ...t, receivable_vnd: '100000000' } : t)) },
}, async page => {
  await page.locator('.age-legend .tiny').waitFor();
  assert.deepEqual(await page.locator('.age-bar span').allInnerTexts(), ['680 triệu', '950 triệu', '600 triệu', '']);
  assert.match(await page.locator('.age-legend .tiny').innerText(), /^Đoạn hẹp: .*trên 6 tháng.*100 triệu/i);
}));

test('đầu tháng: nhãn hôm nay nằm bên phải vạch, không tràn khỏi thước', async () => withDashboard({
  debtPayload: { ...debt, as_of: '2026-11-02', month: '2026-11-01', this_month: { month: '2026-11-01', charges_vnd: '0', received_vnd: '0' } },
}, async page => {
  await page.locator('.meter .today.early').waitFor();
  const [meter, label] = await Promise.all([page.locator('.meter').boundingBox(), page.locator('.meter .today span').boundingBox()]);
  assert.ok(label.x >= meter.x, `nhãn ${label.x} tràn trái thước ${meter.x}`);
  assert.match(await page.locator('.meter .today').innerText(), /hôm nay 2\/11/);
}));

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
  await assertNavOneLine(page);
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

test('Việc cần làm: khối "Từ Sheet chờ đưa vào sổ" gom việc mọi sổ, xếp theo tiền, mở đúng sổ', async () => withPage({
  viewport: { width: 1280, height: 560 },
  inbox: { ...INBOX_EMPTY, failed: [9], books: [
    inboxBook(1, { receipts: { ready: 1, review: 0, amount_vnd: '50000000' }, trips_new: 3, text_diff: 4 }),
    inboxBook(2, { receipts: { ready: 1, review: 1, amount_vnd: '150000000' }, trips_check: { count: 2, reasons: { OTHER_BOOK_LEGACY: 2 } },
      ps: { ready: 0, review: 2 }, text_diff: 1 }),
    inboxBook(7, { removed: { count: 1, amount_vnd: '30000000' }, prices: { ready: 1, review: 1 } }),
  ] },
}, async page => {
  const card = page.locator('.inbox');
  await card.locator('.todo-group').first().waitFor();
  const text = await card.innerText();
  assert.match(text, /Tính lúc 15:02 · Sheet lúc 14:45/);
  assert.match(text, /Còn 13 việc ở 3 sổ · phiếu thu chờ ghi 200 triệu/);
  assert.match(text, /1 sổ chưa tính được/);
  // Nhóm theo thứ tự đụng tiền; trong nhóm phiếu thu, sổ nhiều tiền đứng trước.
  const titles = await card.locator('.todo-title > span:first-child').allInnerTexts();
  assert.deepEqual(titles, ['Phiếu thu từ Sheet chờ ghi', 'Chuyến đang tính nợ nhưng không còn trên Sheet', 'Chuyến mới từ Sheet chờ duyệt',
    'Chuyến cần người xem', 'Giá từ Sheet', 'Phụ phí PS cần xem']);
  assert.deepEqual(await card.locator('[data-group="receipts"] .who').allInnerTexts(), ['Khách C', 'Khách A']);
  assert.match(await card.locator('[data-group="receipts"]').innerText(), /2 phiếu · 150 triệu \(1 cần xem\)/);
  assert.match(await card.locator('[data-group="trips_check"]').innerText(), /2 chuyến · 2 đã có ở sổ khác/);
  assert.match(await card.locator('[data-group="removed"]').innerText(), /Sổ #7\s+1 chuyến · 30 triệu/);
  assert.match(text, /Lệch chữ nơi đi, nơi đến, shipper: 5 chỗ ở 2 sổ/);
  assert.equal(await card.locator('[data-group="trips_new"] a').getAttribute('href'), '/so-khach-v7-live.html?customer=1');
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
}, '/viec-can-lam.html'));

test('Việc cần làm: khối Sheet đang tính, không đọc được Sheet, trống, lỗi tải có Thử lại', async () => {
  let calls = 0;
  await withPage({ inbox: () => (++calls === 1 ? { ...INBOX_EMPTY, state: 'computing', computed_at: null, books_done: 120, books_total: 236 }
    : { ...INBOX_EMPTY, books: [inboxBook(1, { trips_new: 2 })] }) }, async page => {
    await page.locator('.inbox .loading').waitFor();
    assert.match(await page.locator('.inbox').innerText(), /Đang tính việc của mọi sổ \(đã xong 120\/236 sổ\)/);
    await page.locator('.inbox [data-group="trips_new"]').waitFor({ timeout: 8000 });   // tự hỏi lại sau 5 giây
  }, '/viec-can-lam.html');
  await withPage({ inbox: { ...INBOX_EMPTY, state: 'unavailable', computed_at: null } }, async page => {
    await page.locator('.inbox .empty').waitFor();
    assert.match(await page.locator('.inbox').innerText(), /Chưa đọc được bản lấy từ Sheet/);
  }, '/viec-can-lam.html');
  await withPage({}, async page => {
    await page.locator('.inbox .empty').waitFor();
    assert.match(await page.locator('.inbox').innerText(), /Không còn việc từ Sheet/);
  }, '/viec-can-lam.html');
  const drop = new Set(['/api/v7/inbox']);
  await withPage({ drop }, async page => {
    await page.locator('.inbox-error').waitFor();
    assert.match(await page.locator('.inbox').innerText(), /Không tải được việc từ Sheet/);
    await page.locator('.todo .todo-group').first().waitFor();   // các nhóm cũ vẫn hiện
    drop.delete('/api/v7/inbox');
    await page.locator('[data-inbox-retry]').click();
    await page.locator('.inbox .empty:not(.inbox-error)').waitFor();
  }, '/viec-can-lam.html');
});

// Hộp P2: sổ ghi được có phiên bản, bản chụp và phiếu sẵn sàng.
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
    const group = page.locator('.inbox [data-group="receipts"]');
    await group.locator('.receipt-book').first().waitFor();
    assert.equal(await group.locator('[data-book="7"] input').count(), 0);   // phiếu cần xem: không chọn được
    await group.locator('[data-book="7"] summary').click();
    assert.match(await group.locator('[data-book="7"] .receipt-items').innerText(), /cần xem: không rõ ngày/);
    assert.equal(await group.locator('[data-review]').isDisabled(), true);
    await group.locator('[data-pick-all]').check();
    assert.match(await group.locator('[data-review]').innerText(), /Xem lại 2 sổ \(tổng 450 triệu\)/);
    await group.locator('[data-review]').click();
    const review = group.locator('.receipt-review');
    const text = await review.innerText();
    assert.match(text, /Xem lại trước khi ghi 3 phiếu ở 2 sổ · tổng 450\.000\.000/);
    assert.match(text, /1\.000\.000\.000 đ → 600\.000\.000 đ/);
    assert.match(text, /có phiếu ngày trong tháng đang khóa \(T9\): vẫn ghi được/);
    assert.match(text, /khách sẽ dư 20 triệu/);
    assert.equal(await page.evaluate(() => document.activeElement?.hasAttribute('data-write')), true);
    await review.locator('[data-write]').click();
    await page.locator('.inbox-result').waitFor();
    assert.match(await page.locator('.inbox-result').innerText(), /Đã ghi 2 phiếu ở 1 sổ, tổng 400 triệu[\s\S]*1 sổ chưa ghi xong/);
    assert.match(await group.locator('[data-book="2"] .row-error').innerText(), /Sổ đã thay đổi\. Tải lại rồi thử tiếp\./);
    assert.equal(await group.locator('[data-book="1"]').count(), 0);
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
    const group = page.locator('.inbox [data-group="receipts"]');
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
    const done = page.locator('.inbox .auto-done');
    await done.waitFor();
    assert.match(await done.locator('summary').innerText(), /Máy đã tự lấy theo Sheet hôm nay: 2 ô chữ ở 1 sổ/);
    await done.locator('summary').click();
    assert.match(await done.innerText(), /Khách C · MAUU0000001 · nơi đến: CANG C → CANG D[\s\S]*nơi đi: — → KHO B/);
    assert.equal(await done.locator('a').first().getAttribute('href'), '/so-khach-v7-live.html?customer=2');
    assert.match(await page.locator('.inbox .inbox-note').innerText(), /3 chỗ ở 1 sổ\. Không đụng tiền; máy lấy theo Sheet ở lượt tính tới/);
  }, '/viec-can-lam.html');
  await withPage({ inbox: { ...INBOX_EMPTY, auto: { ...auto, text_enabled: false, today_count: 0, items: [] }, books: [inboxBook(1, { text_diff: 3 })] } }, async page => {
    await page.locator('.inbox .inbox-note').waitFor();
    assert.match(await page.locator('.inbox .inbox-note').innerText(), /máy chưa bật tự lấy theo Sheet/);
    assert.equal(await page.locator('.inbox .auto-done').count(), 0);
  }, '/viec-can-lam.html');
});

test('Việc cần làm P3b: "Máy đã đưa vào sổ hôm nay" liệt kê chuyến mới, đánh dấu chuyến chờ kiểm, mở đúng sổ', async () => {
  const auto = { text_enabled: true, trips_enabled: true, last_run: '2026-11-01T12:00:00+00:00', errors: 0, today_count: 0, today_books: 0,
    items: [], today_trips: 2, today_trip_books: 1, today_trips_pending: 1,
    trip_items: [{ at: '2026-11-01T12:00:00+00:00', kind: 'trip', customer_id: 2, container: 'MAUU0000002', event_date: '2026-11-01', trip_id: 9, pending: false },
      { at: '2026-11-01T12:00:00+00:00', kind: 'trip', customer_id: 2, container: 'MAUU0000003', event_date: '2026-10-31', trip_id: 10, pending: true }] };
  await withPage({ inbox: { ...INBOX_EMPTY, auto, books: [] } }, async page => {
    const done = page.locator('.inbox .auto-done');
    await done.waitFor();
    assert.equal(await done.count(), 1);   // không có ô chữ thì chỉ một khối
    assert.match(await done.locator('summary').innerText(), /Máy đã đưa vào sổ hôm nay: 2 chuyến mới ở 1 sổ, 1 chuyến vào chờ kiểm/);
    await done.locator('summary').click();
    assert.match(await done.innerText(), /Khách C · MAUU0000002 · 01\/11\/2026\n[\s\S]*MAUU0000003 · 31\/10\/2026 · chờ kiểm/);
    assert.equal(await done.locator('a').first().getAttribute('href'), '/so-khach-v7-live.html?customer=2');
    assert.match(await done.innerText(), /chưa cộng vào nợ/);
  }, '/viec-can-lam.html');
});
