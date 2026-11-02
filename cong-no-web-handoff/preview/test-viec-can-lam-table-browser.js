const { test } = require('node:test');
const assert = require('node:assert/strict');
const http = require('node:http');
const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require('playwright');

const sha = 'c'.repeat(64);
const book = (id, extra = {}) => ({ customer_id: id, version: 3, outstanding_vnd: '1000000000',
  receipts: { ready: 0, review: 0, amount_vnd: '0', items: [] }, prices: { ready: 0, review: 0 },
  removed: { count: 0, amount_vnd: '0' }, trips_new: 0, trips_check: { count: 0, reasons: {} }, ps: { ready: 0, review: 0 }, text_diff: 0, ...extra });
const writable = (id, extra = {}) => book(id, { receipts: { ready: 1, review: 1, amount_vnd: '50000000', ready_amount_vnd: '50000000', snapshot_sha256: sha,
  locked_months: ['2026-09'], items: [{ status: 'READY', date: '2026-10-30', amount_vnd: '50000000', note: 'Chuyển khoản' },
    { status: 'NO_DATE', date: null, amount_vnd: null, note: 'Thiếu ngày' }] }, ...extra });
const names = ['Công ty Mẫu An Phát', 'Mẫu Minh Châu 明珠 · tên khách dài để kiểm bố cục', 'Công ty Mẫu Phú Gia', 'Công ty Mẫu Hoa Nam', 'Công ty Mẫu Cửu Long', 'Công ty Mẫu Gia Lai', 'Công ty Mẫu Lộc Phát', 'Công ty Mẫu Bình An'];
const customers = names.map((name, i) => ({ id: i + 1, name, commodity: 'Chuối', transport_mode: 'CANG' }));
const dashboard = { as_of: '2026-11-02', demo: true,
  todo: { missing_price: [{ customer_id: 2, count: 3 }], pending_review: [{ customer_id: 2, count: 1 }], no_baseline: [{ customer_id: 8 }], credit: [] },
  today: { trips: 9, receipts: 2, voids: 1, received_vnd: '70000000', by_actor: [{ actor: 'Người nhập mẫu', trips: 9, receipts: 2, voids: 1, received_vnd: '70000000' }] } };
const emptyDash = { ...dashboard, todo: { missing_price: [], pending_review: [], no_baseline: [], credit: [] }, today: { trips: 0, receipts: 0, voids: 0, received_vnd: '0', by_actor: [] } };
const sample = { state: 'ready', sheet_at: '2026-11-02T09:15:00Z', computed_at: '2026-11-02T09:32:00Z', failed: [],
  books: [writable(1), writable(3), book(2, { prices: { ready: 1, review: 1 }, trips_check: { count: 2, reasons: { OTHER_BOOK_LEGACY: 2 } } }),
    book(4, { trips_new: 3 }), book(5, { ps: { ready: 2, review: 0 } }), book(6, { text_diff: 3 }), book(7, { removed: { count: 1, amount_vnd: '12500000' } })],
  auto: { today_count: 2, today_books: 1, items: [{ customer_id: 2, container: 'MAUU0000001', field: 'origin', before: null, after: 'KHO MẪU' }],
    today_trips: 2, today_trip_books: 1, today_trips_pending: 1, trip_items: [{ customer_id: 1, container: 'MAUU0000002', event_date: '2026-11-02', pending: true }] } };
const ledger = { version: 7, total_outstanding_vnd: '100000000', trips: [], sheet_sync: { items: [], removed_items: [] },
  sheet_prices: { ready: [{ container: 'MAUU0000001', date: '2026-11-02', sheet_unit_price_vnd: '9200000', sheet_other_fee_vnd: null }], review: [], snapshot_sha256: sha } };
function serverFor(opts = {}) {
  const value = x => typeof x === 'function' ? x() : x;
  return http.createServer((req, res) => {
    const route = req.url.split('?')[0];
    const send = (status, body, type = 'application/json') => { res.writeHead(status, { 'Content-Type': type }); res.end(type === 'application/json' ? JSON.stringify(body) : body); };
    if (opts.drop?.has(route)) { req.socket.destroy(); return; }
    if (route.startsWith('/api/v7/presence')) return send(200, { people: [] });
    if (req.method === 'POST') {
      let raw = '';
      req.on('data', part => { raw += part; });
      req.on('end', () => {
        const body = JSON.parse(raw);
        opts.posted?.push({ route, body });
        const response = opts.post?.(route, body) ?? { status: 200, json: { complete: true, written: 1 } };
        send(response.status, response.json);
      });
      return;
    }
    if (route === '/api/v7/inbox') return send(200, value(opts.inbox ?? sample));
    if (route === '/api/v7/dashboard') return send(opts.dashboardStatus ?? 200, opts.dashboard ?? dashboard);
    if (route === '/api/v7/dashboard/debt') return send(opts.debtStatus ?? 200, { customers: opts.unsorted ?? [] });
    if (route === '/api/v7/customers') return send(200, { customers });
    if (route === '/api/v7/ledger') return send(opts.ledgerStatus ?? 200, value(opts.ledger ?? ledger));
    if (route.startsWith('/api/v7/presence')) return send(200, { people: [] });
    if (route.startsWith('/api/')) return send(404, {});
    const file = path.join(__dirname, path.basename(route));
    if (!fs.existsSync(file)) return send(404, {});
    send(200, fs.readFileSync(file), file.endsWith('.html') ? 'text/html; charset=utf-8' : file.endsWith('.css') ? 'text/css' : 'text/javascript');
  });
}
async function withPage(opts, fn) {
  const server = serverFor(opts);
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const browser = await chromium.launch();
  try {
    const page = await browser.newPage({ viewport: { width: 1280, height: 560 } });
    await page.goto(`http://127.0.0.1:${server.address().port}/viec-can-lam.html`);
    await page.locator('.work-band').waitFor();
    await fn(page);
  } finally { await browser.close(); server.close(); }
}
if (process.argv.includes('--preview')) {
  const port = Number(process.env.UX_PREVIEW_PORT ?? 18765);
  serverFor().listen(port, '127.0.0.1', () => process.stdout.write(`Fixture preview: http://127.0.0.1:${port}/viec-can-lam.html\n`));
} else {
  test('bảng bốn cột: gộp đúng ID, lọc sổ, chữ Hán/tên dài, 1280 có scrollbar và màn hẹp', async () => withPage({}, async page => {
    await page.waitForFunction(() => document.querySelectorAll('.work-row').length === 8);
    assert.deepEqual(await page.locator('.work-table thead th').allTextContents(), ['Khách', 'Phiếu thu tr', 'Giá chuyến', 'Chuyến cần xử lý', 'Thiết lập sổ', 'Mở']);
    assert.equal(await page.locator('#todo-badge').innerText(), '8');
    assert.match(await page.locator('.today-inline').innerText(), /Người nhập mẫu[\s\S]*9 chuyến · 2 phiếu/);
    await page.locator('[data-filter="trips"]').click();
    assert.equal(await page.locator('.work-row').count(), 2);
    await page.locator('[data-filter="setup"]').click();
    assert.equal(await page.locator('.work-row').count(), 3);
    await page.locator('[data-filter=""]').click();
    await page.locator('[data-book="2"] .book-name').click();
    await page.locator('[data-price-review]').waitFor();
    assert.equal(await page.locator('.work-detail .open-book').getAttribute('href'), '/so-khach-v7-live.html?customer=2');
    await page.locator('[data-book="2"] .book-name').click();
    assert.equal(await page.locator('.work-detail').count(), 0);
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
    if (process.env.UX_SCREENSHOTS) { await page.evaluate(() => scrollTo(0, 0)); await page.screenshot({ path: path.join(process.env.UX_SCREENSHOTS, 'viec-can-lam-1280.png'), fullPage: true }); }
    await page.setViewportSize({ width: 390, height: 844 });
    await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
    assert.equal(await page.locator('.work-scroll').evaluate(e => e.scrollWidth > e.clientWidth), true);
  }));
  test('phiếu: chỉ mục READY được chọn, xem lại nợ trước/sau, tháng khóa và khách dư, hủy không ghi', async () => withPage({ inbox: { ...sample, books: [writable(1, { outstanding_vnd: '30000000' }), book(2, { receipts: { ready: 0, review: 1, amount_vnd: '9000000', items: [{ status: 'NO_DATE', date: null, amount_vnd: null }] } })] } }, async page => {
    assert.equal(await page.locator('[data-book="2"] input').count(), 0);
    await page.locator('[data-book="2"] .book-name').click();
    assert.match(await page.locator('.work-detail').innerText(), /Không rõ ngày[\s\S]*—[\s\S]*Cần xem/);
    await page.locator('[data-pick="1"]').check();
    assert.equal(await page.locator('[data-pick="1"]').evaluate(e => e === document.activeElement), true);
    await page.locator('[data-review]').click();
    const text = await page.locator('.receipt-review').innerText();
    assert.match(text, /30\.000\.000 đ →.*20\.000\.000 đ/);
    assert.match(text, /khách sẽ dư 20 triệu/);
    assert.match(text, /T9/);
    assert.equal(await page.locator('[data-write]').evaluate(e => e === document.activeElement), true);
    await page.locator('[data-review-cancel]').click();
    assert.equal(await page.locator('.receipt-review').count(), 0);
  }));
  test('phiếu: thành công từng sổ, lỗi STALE_LEDGER giữ nguyên tại dòng', async () => {
    const posted = []; let done = false;
    await withPage({ posted, inbox: () => ({ ...sample, books: [...(done ? [] : [writable(1)]), writable(3)] }), post: (_route, b) => b.customer_id === 1 ? (done = true, { status: 200, json: { complete: true, written: 1 } }) : { status: 409, json: { message: 'Sổ đã thay đổi. Tải lại rồi thử tiếp.' } } }, async page => {
      await page.locator('[data-pick-ready]').click();
      await page.locator('[data-write]').click();
      await page.waitForFunction(() => document.querySelector('.inbox-result')?.textContent.includes('Đã ghi 1 phiếu'));
      assert.match(await page.locator('[data-book="3"] .row-error').innerText(), /Sổ đã thay đổi/);
      await page.waitForFunction(() => !document.querySelector('[data-book="1"]'));
      assert.deepEqual(posted.map(p => [p.body.customer_id, p.body.expected_version, p.body.snapshot_sha256]), [[1, 3, sha], [3, 3, sha]]);
    });
  });
  test('phiếu mất mạng: khóa và payload giữ nguyên, chặn thao tác khác khi chưa rõ kết quả', async () => {
    const posted = []; const lost = [];
    await withPage({ posted }, async page => {
      await page.route('**/api/v7/sheet/receipts', route => { lost.push(route.request().postDataJSON()); return route.abort(); }, { times: 1 });
      await page.locator('[data-pick="1"]').check(); await page.locator('[data-review]').click(); await page.locator('[data-write]').click();
      await page.locator('[data-write-retry]').waitFor();
      await page.keyboard.press('Escape');
      await page.locator('[data-filter="setup"]').click();
      assert.equal(await page.locator('[data-filter="setup"]').getAttribute('aria-pressed'), 'false');
      await page.locator('[data-write-retry]').click();
      await page.waitForFunction(() => document.querySelector('.inbox-result')?.textContent.includes('Đã ghi 1 phiếu'));
      assert.deepEqual(posted[0].body, lost[0]);
    });
  });
  test('giá: đọc phiên bản mới, nợ trước/sau đúng, mất mạng gửi lại nguyên yêu cầu', async () => {
    const posted = []; const lost = [];
    await withPage({ posted }, async page => {
      await page.locator('[data-book="2"] .book-name').click(); await page.locator('[data-price-review]').click();
      assert.match(await page.locator('#h-action').innerText(), /Ghi 1 giá từ Sheet/);
      assert.match(await page.locator('.receipt-review').innerText(), /100\.000\.000 đ → 109\.200\.000 đ/);
      await page.route('**/api/v7/sheet/prices', route => { lost.push(route.request().postDataJSON()); return route.abort(); }, { times: 1 });
      await page.locator('[data-action-write]').click(); await page.locator('[data-action-write]', { hasText: 'Thử lại' }).waitFor();
      await page.locator('[data-action-write]').click();
      await page.waitForFunction(() => !document.querySelector('#h-action'));
      assert.deepEqual(posted[0].body, lost[0]); assert.equal(posted[0].body.expected_version, 7);
    });
  });
  test('chọn chung giá + phiếu: nợ cuối đúng, phiên bản nối tiếp, lô xong không bị gửi lại', async () => {
    const posted = [];
    const mixed = { ...ledger, sheet_receipts: { ready: [{ amount_vnd: '50000000' }], snapshot_sha256: sha } };
    await withPage({ posted, ledger: mixed, inbox: { ...sample, books: [writable(1, { prices: { ready: 1, review: 0 } })] },
      post: (route, body) => ({ status: 200, json: { complete: true, written: 1, version: body.expected_version + 1 } }) }, async page => {
      const lost = [];
      await page.route('**/api/v7/sheet/receipts', route => { lost.push(route.request().postDataJSON()); return route.abort(); }, { times: 1 });
      await page.locator('[data-pick-ready]').click();
      assert.match(await page.locator('.action-description').innerText(), /100\.000\.000 đ → 59\.200\.000 đ/);
      await page.locator('[data-action-write]').click();
      await page.locator('[data-action-write]', { hasText: 'Thử lại' }).waitFor();
      assert.equal(posted.length, 1);
      await page.locator('[data-action-write]').click();
      await page.waitForFunction(() => document.querySelector('#h-action')?.textContent.includes('Đã ghi các mục'));
      assert.deepEqual(posted.map(p => [p.route, p.body.expected_version]), [['/api/v7/sheet/prices', 7], ['/api/v7/sheet/receipts', 8]]);
      assert.deepEqual(posted[1].body, lost[0]);
    });
  });
  test('chi tiết: nhập giá nguyên đồng, kết luận cần lý do, PS giữ tổng, xóa có xem lại; không ghi tháng khóa', async () => {
    const posted = [];
    const detail = { ...ledger,
      trips: [{ id: 11, container: 'MAUU0000011', status: 'confirmed', unit_price_vnd: null, other_fee_vnd: '100000', editable: true },
        { id: 12, container: 'MAUU0000012', status: 'pending_review', unit_price_vnd: '9000000', other_fee_vnd: null, editable: true }],
      sheet_sync: { snapshot_sha256: sha, items: [], removed_items: [{ trip_id: 13, container: 'MAUU0000013', status: 'confirmed', amount_vnd: '12500000', month_locked: false },
        { trip_id: 14, container: 'MAUU0000014', amount_vnd: '9000000', month_locked: true }] },
      ps_fees: { snapshot_sha256: sha, ready: [{ container: 'MAUU0000011', before: [{ amount_vnd: '100000' }], after: [{ amount_vnd: '100000' }] }], review: [] } };
    await withPage({ posted, ledger: detail }, async page => {
      await page.locator('[data-book="2"] .book-name').click(); await page.locator('[data-manual-price]').waitFor();
      await page.locator('[data-manual-price]').fill('9.200.000');
      await page.locator('[data-filter="trips"]').click(); await page.locator('[data-filter=""]').click();
      assert.equal(await page.locator('[data-manual-price]').inputValue(), '9.200.000');
      await page.locator('[data-command="price"]').click();
      assert.match(await page.locator('.action-description').innerText(), /100\.000\.000 đ → 109\.300\.000 đ/);
      await page.locator('[data-action-write]').click(); await page.waitForFunction(() => !document.querySelector('#h-action'));
      assert.equal(posted[0].body.unit_price_vnd, '9200000'); assert.equal(posted[0].body.other_fee_vnd, '100000');
      await page.locator('[data-detail-retry]').count();
      await page.locator('[data-book="2"] .book-name').click(); await page.locator('[data-book="2"] .book-name').click();
      await page.locator('[data-command="confirm"]').waitFor();
      await page.locator('[data-command="confirm"]').click(); assert.equal(await page.locator('#h-action').count(), 0);
      await page.locator('[data-reason="12"]').fill('Đã đối chiếu, chuyến riêng'); await page.locator('[data-command="confirm"]').click();
      assert.match(await page.locator('.action-description').innerText(), /109\.000\.000 đ/);
      await page.locator('[data-action-cancel]').click();
      await page.locator('[data-book="2"] .book-name').click(); await page.locator('[data-book="2"] .book-name').click();
      await page.locator('[data-command="ps"]').click(); assert.match(await page.locator('.action-description').innerText(), /giữ nguyên/);
      await page.locator('[data-action-cancel]').click();
      await page.locator('[data-book="2"] .book-name').click(); await page.locator('[data-book="2"] .book-name').click();
      assert.equal(await page.locator('[data-remove-trip="14"]').count(), 0);
      await page.locator('[data-remove-trip="13"]').click();
      assert.match(await page.locator('.action-description').innerText(), /100\.000\.000 đ → 87\.500\.000 đ/);
      assert.equal(await page.locator('[data-action-cancel]').evaluate(e => e === document.activeElement), true);
      await page.keyboard.press('Escape'); assert.equal(await page.locator('#h-action').count(), 0);
    });
  });
  test('lỗi nguồn/đang tính/thiếu baseline không kết luận hết việc; retry tải được', async () => {
    const drop = new Set(['/api/v7/inbox']);
    await withPage({ drop, dashboard: emptyDash }, async page => {
      await page.locator('.inbox-error').waitFor(); assert.match(await page.locator('.band-count').innerText(), /Chưa đủ dữ liệu/);
      drop.clear(); await page.locator('[data-inbox-retry]').click(); await page.locator('.work-row').first().waitFor();
    });
    await withPage({ dashboard: emptyDash, inbox: { state: 'computing', books_done: 120, books_total: 236, books: [] } }, async page => {
      assert.match(await page.locator('.computing').innerText(), /120\/236/); assert.doesNotMatch(await page.locator('.band-count').innerText(), /Hết việc/);
    });
    await withPage({ dashboard: emptyDash, inbox: { state: 'unavailable', books: [] } }, async page => assert.match(await page.locator('.inbox-note').innerText(), /Chưa đọc được/));
    await withPage({ dashboard: emptyDash, debtStatus: 503, inbox: { state: 'ready', books: [] } }, async page => {
      await page.locator('#error').waitFor({ state: 'visible' }); assert.doesNotMatch(await page.locator('.band-count').innerText(), /Hết việc/);
    });
    await withPage({ dashboard: emptyDash, inbox: { state: 'ready', books: [] } }, async page => {
      await page.waitForFunction(() => document.querySelector('.band-count')?.textContent.includes('Hết việc'));
      assert.equal(await page.locator('#todo-badge').isHidden(), true);
    });
  });
  test('soát máy: chữ trước/sau, chuyến chờ kiểm, đường mở đúng sổ; tìm khách và bàn phím', async () => withPage({}, async page => {
    await page.locator('[data-auto]').click();
    const summaries = page.locator('.auto-done summary');
    await summaries.nth(0).click(); await summaries.nth(1).click();
    assert.match(await page.locator('.auto-list').innerText(), /nơi đi: — → KHO MẪU[\s\S]*chờ kiểm/);
    assert.equal(await page.locator('.auto-list a').first().getAttribute('href'), '/so-khach-v7-live.html?customer=2');
    await page.locator('#customer-search').fill('明珠'); await page.locator('#customer-results a').waitFor();
    assert.equal(await page.locator('#customer-results a').getAttribute('href'), '/so-khach-v7-live.html?customer=2');
  }));
}
