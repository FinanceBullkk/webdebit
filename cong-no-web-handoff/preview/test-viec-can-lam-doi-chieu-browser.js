// Việc cần làm (VIEC-DOI-CHIEU-01): dòng đầu trang, ba tab, bảng khách lệch, bảng đối chiếu. Dữ liệu giả.
const assert = require('node:assert/strict');
const http = require('node:http');
const fs = require('node:fs');
const path = require('node:path');
const { launchShared, test } = require('./shared-browser.js');

const sha = 'c'.repeat(64);
const customers = [['Mẫu Đông Á', 7], ['Mẫu An Phát', 1], ['Mẫu Phú Gia', 3], ['Mẫu Lộc Phát', 8], ['Mẫu Kim Long', 9]].map(([name, id]) => ({ id, name, commodity: 'Chuối', transport_mode: 'CANG' }));
const book = (id, extra = {}) => ({ customer_id: id, version: 3, outstanding_vnd: '100000000', receipts: { ready: 0, review: 0, amount_vnd: '0', items: [] }, prices: { ready: 0, review: 0 },
  removed: { count: 0, amount_vnd: '0' }, trips_new: 0, trips_check: { count: 0, reasons: {} }, ps: { ready: 0, review: 0 }, text_diff: 0, ...extra });
const dashboard = { as_of: '2026-11-06', todo: { missing_price: [{ customer_id: 7, count: 2 }], pending_review: [], no_baseline: [], credit: [] },
  today: { trips: 0, receipts: 0, voids: 0, received_vnd: '0', by_actor: [{ actor: 'Người nhập mẫu', trips: 2, receipts: 1, voids: 0, received_vnd: '5000000' }] } };
const lech = { customer: 'Mẫu Đông Á', customer_id: 7, status: 'LECH_TONG', reason: 'NO_EXACT_FIX', difference_vnd: '-64200000', web_total_vnd: '5210000000', sheet_total_vnd: '5274200000', web_ahead_vnd: '0',
  sheet_editing: true, sheet_last_edit_at: '2026-11-06T10:00:00+07:00', groups: [{ kind: 'prices', month: '2026-10', count: 18, delta_vnd: '58400000', chosen: false }] };
const reconcile = { version: 1, checked_at: '2026-11-06T10:12:00+07:00', mode: 'fix', counts: { KHOP: 238, LECH_TONG: 1 }, total: 239, matched_web_vnd: '88', all_web_vnd: '100', months_differ: [], outside_tabs: [], matched_ids: [1, 3], customers: [lech] };
const inbox = (extra = {}) => ({ state: 'ready', sheet_at: '2026-11-06T03:15:00Z', computed_at: '2026-11-06T03:16:00Z', failed: [], reconcile,
  auto: { today_count: 1, today_trips: 1, today_prices: 1, today_ps: 0,
    items: [{ customer_id: 1, field: 'origin', before: null, after: 'KHO MẪU', at: '2026-11-06T02:05:00+00:00' }],
    trip_items: [{ customer_id: 1, container: 'MAUU0000002', event_date: '2026-11-05', at: '2026-11-06T03:05:00+00:00' }],
    price_items: [{ customer_id: 3, container: 'MAUU0000003', date: '2026-11-04', before_unit_price_vnd: null, unit_price_vnd: '42000000', at: '2026-11-06T02:50:00+00:00' }] },
  books: [book(7, { prices: { ready: 0, review: 18 }, receipts: { ready: 0, review: 1, amount_vnd: '6100000', items: [] }, ps: { ready: 0, review: 1 } }), book(1, { sheet_matched: true, trips_check: { count: 3, reasons: {} } }), book(3, { sheet_matched: true, ps: { ready: 0, review: 6 } })], ...extra });
// HOAT-DONG-01: việc đã ghi theo ngày (GET /api/v7/activity), cùng hình dạng với Lịch sử của sổ.
const activityDays = {
  '2026-11-06': { day: '2026-11-06', today: '2026-11-06', prev_day: '2026-11-03', next_day: null, total: 3,
    events: [
      { id: 30, customer_id: 1, customer: 'Mẫu An Phát', kind: 'receipt', actor: 'thu.ke@example.test', actor_name: 'Thu', at: '2026-11-06T03:20:00+00:00', before: {},
        after: { pid: 'PH-007', date: '2026-11-05', method: 'CK', amount_vnd: '5000000', allocations: [] } },
      { id: 29, customer_id: 3, customer: 'Mẫu Phú Gia', kind: 'price_edit', actor: 'may-theo-sheet', actor_name: 'Máy (theo Sheet)', at: '2026-11-06T02:50:00+00:00',
        before: { price: { trip_id: 41, unit_price_vnd: null, other_fee_vnd: null } }, after: { price: { trip_id: 41, unit_price_vnd: '42000000', other_fee_vnd: null } } },
      { id: 28, customer_id: 1, customer: 'Mẫu An Phát', kind: 'paste', actor: 'may-theo-sheet', actor_name: 'Máy (theo Sheet)', at: '2026-11-06T02:05:00+00:00', before: {},
        after: { trips: [{ trip_id: 40, container: 'MAUU0000002', event_date: '2026-11-05', unitPriceVnd: null, status: 'confirmed', note: 'Chuyến đồng bộ' }, { trip_id: 42, container: 'MAUU0000004', event_date: '2026-11-05', unitPriceVnd: null, status: 'confirmed', note: 'Chuyến đồng bộ' }] } }],
    trips: [{ id: 40, container: 'MAUU0000002' }, { id: 42, container: 'MAUU0000004' }, { id: 41, container: 'MAUU0000003' }], receipts: [], legacy_rows: [], fee_types: [] },
  '2026-11-03': { day: '2026-11-03', today: '2026-11-06', prev_day: null, next_day: '2026-11-06', total: 1,
    events: [{ id: 5, customer_id: 7, customer: 'Mẫu Đông Á', kind: 'void', actor: 'ke.toan@example.test', actor_name: 'Kế toán', at: '2026-11-03T08:00:00+00:00',
      before: { pid: 'PH-002', amount_vnd: '1000000' }, after: { pid: 'PH-002', void_reason: 'ghi trùng' } }],
    trips: [], receipts: [], legacy_rows: [], fee_types: [] },
};
const fees = [[34, 95], [32, 20], [29, 135], [21, 60], [null, 40], [18, 32], [25, 10], [null, 24], [31, 8], [14, 15], [22, 21], [40, 12], [null, 26], [27, 14], [19, 19], [33, 9], [12, 20], [26, 24]];
const priceRows = fees.map(([web, delta], i) => ({ key: `legacy:${i + 1}`, status: 'CONFLICT', container: `MAUU ${100101 + i * 37}-${i % 9}`, date: `2026-10-${String(3 + i).padStart(2, '0')}`, source_row: 412 + i * 3,
  web_unit_price_vnd: '60000000', sheet_unit_price_vnd: '60000000', web_other_fee_vnd: web === null ? null : String(web * 100000), sheet_other_fee_vnd: String(((web ?? 0) + delta) * 100000), delta_vnd: String(delta * 100000), source_fingerprint: sha }));
const statement = (extra = {}) => ({ customer_id: 7, version: 12, web_vnd: '5210000000', sheet_total_vnd: '5274200000', checked_at: reconcile.checked_at, reason: 'NO_EXACT_FIX', sheet_editing: true, sheet_last_edit_at: lech.sheet_last_edit_at,
  web_ahead_vnd: '0', shuffled_months: [], prices_sha256: sha, receipts_sha256: 'd'.repeat(64),
  groups: [{ id: 'prices:2026-10', kind: 'prices', month: '2026-10', count: 18, delta_vnd: '58400000', locked: true, undoable: true, replaces: 0, rows: priceRows },
    { id: 'receipts_no_date:2026-09', kind: 'receipts_no_date', month: '2026-09', count: 1, delta_vnd: '-6100000', locked: false, undoable: true, replaces: 0, rows: [{ status: 'NO_DATE', source_row: 30, debt_month: '2026-09-01', amount_vnd: '6100000', note: 'trừ phí khác', date: null }] }], ...extra });

function serverFor(opts = {}) {
  const value = x => typeof x === 'function' ? x() : x;
  return http.createServer((req, res) => {
    const route = req.url.split('?')[0];
    const send = (status, body) => { res.writeHead(status, { 'Content-Type': 'application/json' }); res.end(JSON.stringify(body)); };
    if (route.startsWith('/api/v7/presence')) return send(200, { people: [] });
    if (req.method === 'POST') {
      let raw = '';
      req.on('data', part => { raw += part; });
      req.on('end', () => {
        const body = JSON.parse(raw);
        opts.posted?.push({ route, body });
        const out = opts.post?.(route, body) ?? { status: 200, json: { complete: true, version: 20, before_vnd: '5210000000', after_vnd: '5268400000', undo: { command_keys: ['e'.repeat(64)], months: ['2026-10'] } } };
        send(out.status, out.json);
      });
      return;
    }
    if (route === '/api/v7/inbox') return send(200, value(opts.inbox ?? inbox()));
    if (route === '/api/v7/activity') {
      const day = new URL(req.url, 'http://x').searchParams.get('day') ?? '2026-11-06';
      opts.activityAsked?.push(day);
      return opts.activityStatus ? send(opts.activityStatus, {}) : send(200, activityDays[day] ?? { day, today: '2026-11-06', prev_day: '2026-11-03', next_day: '2026-11-06', total: 0, events: [], trips: [], receipts: [], legacy_rows: [], fee_types: [] });
    }
    if (route === '/api/v7/sheet/doi-chieu') return send(opts.statementStatus ?? 200, value(opts.statement ?? statement()));
    if (route === '/api/v7/ai/preview') return send(200, opts.aiPreview ?? { enabled: true, fingerprint: 'f'.repeat(64), packet: { customer_id: 7, customer: 'Mẫu Đông Á', checked_at: reconcile.checked_at, groups: [], partial: false } });
    if (route === '/api/v7/dashboard') return send(200, opts.dashboard ?? dashboard);
    if (route === '/api/v7/dashboard/debt') return send(200, { customers: [] });
    if (route === '/api/v7/customers') return send(200, { customers });
    if (route === '/api/v7/ledger') return send(200, { version: 12, total_outstanding_vnd: '100000000', trips: [], sheet_sync: { items: [], removed_items: [] }, sheet_prices: { ready: [], review: priceRows }, sheet_receipts: { review: [{ status: 'NO_DATE', amount_vnd: '6100000', note: 'x', source_fingerprint: sha, debt_month: '2026-09-01' }] } });
    if (route === '/api/v7/price-table/status') return send(200, { trips: [] });
    if (route.startsWith('/api/')) return send(404, {});
    const file = path.join(__dirname, path.basename(route));
    if (!fs.existsSync(file)) return send(404, {});
    res.writeHead(200, { 'Content-Type': file.endsWith('.html') ? 'text/html; charset=utf-8' : file.endsWith('.css') ? 'text/css' : 'text/javascript' });
    res.end(fs.readFileSync(file));
  });
}
async function withPage(opts, fn, { width = 1280, height = 560 } = {}) {
  const server = serverFor(opts);
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const browser = await launchShared();
  try {
    const page = await browser.newPage({ viewport: { width, height } });
    await page.clock.setFixedTime(new Date(opts.now ?? '2026-11-06T10:15:00+07:00'));
    await page.goto(`http://127.0.0.1:${server.address().port}/viec-can-lam.html`);
    await page.locator('.viec-status').waitFor();
    await fn(page);
  } finally { await browser.close(); server.close(); }
}
const statusLine = page => page.locator('.status-line').innerText();
const opened = page => page.locator('.dc-table').waitFor();

if (process.argv.includes('--preview')) {
  const port = Number(process.env.UX_PREVIEW_PORT ?? 18768);
  serverFor({}).listen(port, '127.0.0.1', () => process.stdout.write(`Fixture preview: http://127.0.0.1:${port}/viec-can-lam.html\n`));
} else {
  test('AI: chỉ gửi sau khi xem trước và đồng ý; câu trả lời không ghi sổ', async () => {
    const posted = [];
    await withPage({ posted, post: route => route === '/api/v7/ai/explain'
      ? { status: 200, json: { text: 'Cần kiểm dòng Sheet.', usage: { input_tokens: 10, output_tokens: 5 } } }
      : { status: 400, json: { message: 'Không được ghi.' } } }, async page => {
      await opened(page);
      await page.locator('[data-ai-preview="7"]').click();
      await page.locator('[data-ai-send="7"]').waitFor();
      assert.equal(posted.length, 0, 'xem trước không gọi Claude');
      assert.match(await page.locator('.dc-ai-preview').innerText(), /Dữ liệu sẽ gửi Anthropic/);
      await page.locator('[data-ai-send="7"]').click();
      await page.getByText('Cần kiểm dòng Sheet.').waitFor();
      assert.equal(posted.length, 1);
      assert.equal(posted[0].route, '/api/v7/ai/explain');
      assert.deepEqual(posted[0].body, { customer_id: 7, fingerprint: 'f'.repeat(64), consent: true });
      assert.equal(await page.locator('.dc-ai-preview pre').evaluate(node => node.scrollWidth <= node.clientWidth + 1), true, 'bản xem trước tự xuống dòng');
    }, { width: 390, height: 720 });
  });
  test('mở trang: trả lời số nợ có đúng không, khách lệch mở sẵn, đọc phụ phí thay vì hai số bằng nhau', async () => withPage({}, async page => {
    await opened(page);
    const line = await statusLine(page);
    assert.match(line, /238\/239 khách khớp Sheet/);
    assert.match(line, /88% số nợ · 1 khách lệch/);
    assert.match(line, /Đối soát lúc 10:12 · lần tới 11:05/);
    assert.ok(await page.locator('.viec-status.warn').count());
    assert.deepEqual(await page.locator('[data-tab]').allInnerTexts(), ['Số nợ lệch 1', 'Dọn chi tiết 3', 'Đã làm 3']);
    assert.equal(await page.locator('[data-tab="lech"]').getAttribute('aria-selected'), 'true');
    const row = await page.locator('.dc-customer').innerText();
    assert.match(row, /Mẫu Đông Á[\s\S]*5\.210[\s\S]*5\.274,2[\s\S]*−64,2[\s\S]*Sheet vừa sửa lúc 10:00, máy xem lại ở lượt sau/);
    const table = await page.locator('.dc-table').innerText();
    assert.match(table, /Số nợ trên web[\s\S]*5\.210/);
    assert.match(table, /Phụ phí 18 chuyến tháng 10[\s\S]*Sheet cao hơn web[\s\S]*tháng khóa[\s\S]*\+58,4/);
    assert.match(table, /1 phiếu thu không ngày tháng 9[\s\S]*ngày lấy cuối tháng[\s\S]*−6,1/);
    assert.match(table, /Số nợ trên Sheet[\s\S]*lúc 10:12[\s\S]*5\.274,2/);
    assert.match(table, /Còn lệch[\s\S]*−64,2/);
    assert.equal(await page.locator('[data-dc-ghi]').isDisabled(), true, 'chưa chọn thì không ghi được');
    await page.locator('[data-dc-xem="prices:2026-10"]').click();
    const rows = await page.locator('.dc-rows').innerText();
    assert.match(rows, /Phụ phí web → Sheet/);
    assert.match(rows, /MAUU 100101-0[\s\S]*3,4 →\s*12,9[\s\S]*\+9,5[\s\S]*412/);
    assert.match(rows, /trống →\s*4/);
    assert.doesNotMatch(rows, /60 · trên Sheet 60/);
  }));

  test('màn thấy 1280×560: đủ dòng đầu, tab, khách, các khoản, Còn lệch và nút Ghi; không tràn ngang', async () => withPage({}, async page => {
    await opened(page);
    for (const selector of ['.viec-status', '.viec-tabs', '.dc-customer', '.dc-item >> nth=1', '.dc-left', '[data-dc-ghi]']) {
      const box = await page.locator(selector).boundingBox();
      assert.ok(box && box.y + box.height <= 560, `${selector} nằm trong màn: ${box?.y}+${box?.height}`);
    }
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
    if (process.env.UX_SCREENSHOTS) await page.screenshot({ path: path.join(process.env.UX_SCREENSHOTS, 'viec-doi-chieu-1280.png') });
  }));

  test('màn hẹp: không tràn ngang, bảng cuộn trong khung', async () => withPage({}, async page => {
    await opened(page);
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
    assert.equal(await page.locator('.dc-scroll').evaluate(e => e.scrollWidth > e.clientWidth), true);
  }, { width: 390, height: 844 }));

  test('chọn khoản: số còn lệch đổi ngay, xác nhận nêu nợ trước → sau và tháng khóa, ghi đúng khoản, có hoàn tác', async () => {
    const posted = [];
    await withPage({ posted, post: route => route.endsWith('/hoan-tac') ? { status: 200, json: { complete: true, undone: 1, version: 21 } } : undefined }, async page => {
      await opened(page);
      await page.locator('[data-dc-pick="prices:2026-10"]').check();
      assert.match(await page.locator('.dc-left').innerText(), /Còn lệch[\s\S]*−5,8/);
      assert.match(await page.locator('.dc-sub').innerText(), /Số nợ web sau khi ghi[\s\S]*5\.268,4/);
      assert.match(await page.locator('[data-dc-ghi]').innerText(), /Ghi 1 khoản đã chọn/);
      await page.locator('[data-dc-pick="receipts_no_date:2026-09"]').check();
      assert.match(await page.locator('.dc-left').innerText(), /−11,9/);
      await page.locator('[data-dc-pick="receipts_no_date:2026-09"]').uncheck();
      await page.locator('[data-dc-ghi]').click();
      const text = await page.locator('.dc-confirm').innerText();
      assert.match(text, /Ghi 1 khoản\. Còn nợ 5\.210 triệu → 5\.268,4 triệu|Ghi 1 khoản\. Còn nợ .*5\.210.* → .*5\.268/);
      assert.match(text, /vẫn lệch Sheet −5,8 tr/);
      assert.match(text, /Tháng đang khóa \(T10\): web mở, ghi, rồi khóa lại/);
      assert.match(text, /Có ghi Lịch sử/);
      assert.equal(await page.locator('[data-action-cancel]').evaluate(e => e === document.activeElement), true);
      assert.equal(await page.locator('[data-dc-pick="prices:2026-10"]').isDisabled(), true, 'đang xác nhận thì không đổi khoản');
      await page.locator('[data-action-write]').click();
      await page.locator('.dc-done').waitFor();
      assert.equal(posted[0].route, '/api/v7/sheet/doi-chieu/ghi');
      assert.deepEqual(posted[0].body, { customer_id: 7, expected_version: 12, prices_sha256: sha, receipts_sha256: 'd'.repeat(64), items: [{ id: 'prices:2026-10', delta_vnd: '58400000', rows: null }] });
      assert.match(await page.locator('.dc-done').innerText(), /Đã ghi 1 khoản/);
      assert.equal(await page.locator('[data-dc-pick="prices:2026-10"]').isChecked(), false, 'ghi xong bỏ chọn');
      await page.locator('[data-dc-undo="7"]').click();
      assert.match(await page.locator('.dc-confirm').innerText(), /Hoàn tác lần vừa ghi/);
      await page.locator('[data-action-write]').click();
      await page.waitForFunction(() => document.querySelector('.dc-done')?.textContent.includes('Đã hoàn tác'));
      assert.deepEqual(posted[1].body.command_keys, ['e'.repeat(64)]);
      assert.deepEqual(posted[1].body.months, ['2026-10']);
      assert.equal(posted[1].body.expected_version, 20);
      assert.equal(await page.locator('[data-dc-undo]').count(), 0);
    });
  });

  test('bỏ bớt chuyến: gửi đúng chuyến còn chọn và đúng số tiền; hai khoản khớp đúng thì báo khớp', async () => {
    const posted = [];
    const exact = statement({ sheet_total_vnd: '5268400000' });
    await withPage({ posted, statement: exact }, async page => {
      await opened(page);
      await page.locator('[data-dc-pick="prices:2026-10"]').check();
      assert.match(await page.locator('.dc-left').innerText(), /Khớp[\s\S]*tới từng đồng sau khi ghi[\s\S]*0/);
      await page.locator('[data-dc-xem="prices:2026-10"]').click();
      await page.locator('[data-dc-row="legacy:1"]').uncheck();
      assert.match(await page.locator('[data-dc-group="prices:2026-10"]').innerText(), /đã chọn 17\/18 chuyến[\s\S]*\+48,9/);
      await page.locator('[data-dc-ghi]').click();
      await page.locator('[data-action-write]').click();
      await page.locator('.dc-done').waitFor();
      assert.equal(posted[0].body.items[0].delta_vnd, '48900000');
      assert.equal(posted[0].body.items[0].rows.length, 17);
      assert.equal(posted[0].body.items[0].rows.includes('legacy:1'), false);
    });
  });

  test('giữ số web: cả nhóm và từng chuyến, nói rõ vẫn lệch, nợ không đổi', async () => {
    const posted = [];
    await withPage({ posted, post: () => ({ status: 200, json: { complete: true, kept: 18, version: 30 } }) }, async page => {
      await opened(page);
      await page.locator('[data-dc-giu="prices:2026-10"]').click();
      assert.match(await page.locator('.dc-confirm').innerText(), /Giữ số web cho 18 chuyến\. Nợ không đổi, vẫn lệch Sheet/);
      await page.locator('[data-action-write]').click();
      await page.waitForFunction(() => !document.querySelector('.dc-confirm'));
      assert.equal(posted[0].route, '/api/v7/sheet/doi-chieu/giu');
      assert.equal(posted[0].body.rows.length, 18);
      assert.deepEqual(posted[0].body.rows[0], { target_kind: 'legacy', target_id: 1, source_fingerprint: sha });
      await page.locator('[data-dc-xem="prices:2026-10"]').click();
      await page.locator('[data-dc-giu-row="legacy:2"]').click();
      assert.match(await page.locator('.dc-confirm').innerText(), /Giữ số web cho 1 chuyến/);
    });
  });

  test('mất mạng khi ghi: thử lại đúng yêu cầu, không bấm khác được; server báo sổ đã đổi thì hiện tại chỗ', async () => {
    const posted = [], lost = [];
    await withPage({ posted, post: () => ({ status: 409, json: { message: 'Sổ vừa thay đổi. Tải lại rồi xem lại.' } }) }, async page => {
      await opened(page);
      await page.locator('[data-dc-pick="prices:2026-10"]').check();
      await page.locator('[data-dc-ghi]').click();
      await page.route('**/api/v7/sheet/doi-chieu/ghi', route => { lost.push(route.request().postDataJSON()); return route.abort(); }, { times: 1 });
      await page.locator('[data-action-write]').click();
      await page.locator('[data-action-write]', { hasText: 'Thử lại' }).waitFor();
      assert.match(await page.locator('.dc-confirm').innerText(), /chưa rõ kết quả/);
      await page.locator('[data-action-write]').click();
      await page.waitForFunction(() => document.querySelector('.dc-confirm [role=alert]')?.textContent.includes('Sổ vừa thay đổi'));
      assert.deepEqual(posted[0].body, lost[0]);
      assert.equal(await page.locator('[data-action-write]').count(), 0, 'lỗi rồi thì không ghi lại được nữa');
      await page.locator('[data-action-cancel]').click();
      await page.locator('.dc-confirm').waitFor({ state: 'detached' });
    });
  });

  test('đọc khoản lỗi: báo và thử lại; đang đọc nền thì không mất khoản đang chọn', async () => {
    const opts = { statementStatus: 503, statement: { message: 'x' } };
    await withPage(opts, async page => {
      await page.locator('.dc-failed').waitFor();
      opts.statementStatus = 200; opts.statement = statement();
      await page.locator('[data-dc-retry]').click();
      await opened(page);
      await page.locator('[data-dc-pick="prices:2026-10"]').check();
      await page.locator('[data-dc-pick="receipts_no_date:2026-09"]').check();
      opts.statement = statement({ groups: statement().groups.slice(0, 1) });
      await page.evaluate(() => document.dispatchEvent(new Event('visibilitychange')));
      await page.locator('[data-dc-pick="receipts_no_date:2026-09"]').waitFor({ state: 'detached' });
      assert.equal(await page.locator('[data-dc-pick="prices:2026-10"]').isChecked(), true, 'khoản còn thì giữ lựa chọn');
      assert.match(await page.locator('[data-dc-ghi]').innerText(), /Ghi 1 khoản/, 'khoản không còn thì bỏ khỏi lựa chọn');
    });
  });

  test('khoản nhỏ không làm tròn thành 0; tổng Sheet chưa biết hiện dấu gạch; không có khoản thì không có nút Ghi', async () => {
    await withPage({ statement: statement({ sheet_total_vnd: '5210040000', groups: [] }) }, async page => {
      await opened(page);
      assert.match(await page.locator('.dc-left').innerText(), /Còn lệch[\s\S]*Không có khoản nào giải thích được[\s\S]*40\.000/);
      assert.equal(await page.locator('[data-dc-ghi]').count(), 0);
    });
    await withPage({ statement: statement({ sheet_total_vnd: null, groups: [], sheet_editing: false }) }, async page => {
      await opened(page);
      assert.match(await page.locator('.dc-left').innerText(), /Chưa so được[\s\S]*—/);
      assert.match(await page.locator('.dc-sheet-total').innerText(), /—/);
    });
  });

  test('máy đoán chỗ lệch: câu ở cột Vì sao, đủ danh sách khi mở; khách bị giữ nói khối tháng (CHAN-DOAN-LECH-01)', async () => {
    const hints = [
      { kind: 'receipt_twice', date: '2026-10-31', amount_vnd: '8300000', pids: ['PH-001', 'PH-002'], delta_vnd: '8300000' },
      { kind: 'sheet_row_missing', row: 284, container: 'MAUU0000284 取消', sheet_vnd: '7700000', delta_vnd: '7700000' },
      { kind: 'price_review', status: 'MANUAL', row: 231, container: 'MAUU0000231', sheet_vnd: '101500000', web_vnd: '98000000', delta_vnd: '3500000' },
    ];
    const guess = { ...lech, reason: 'NOTHING_TO_WRITE', sheet_editing: false, difference_vnd: '-16000000', groups: [], hints, hints_explain: true };
    const held = { customer: 'Mẫu Kim Long', customer_id: 9, status: 'CHI_CO_WEB', reason: 'HELD', difference_vnd: null, web_total_vnd: '95000500', sheet_total_vnd: null,
      held_reasons: { ANCHOR_CHAIN_MISMATCH: 2 }, hints: [{ kind: 'chain_break', month: '2026-10', sheet_end_vnd: '95000000', expected_end_vnd: '95000500', delta_vnd: '-500' }] };
    await withPage({ inbox: inbox({ reconcile: { ...reconcile, customers: [guess, held] } }), statement: statement({ sheet_total_vnd: '5226033039', groups: [], reason: 'NOTHING_TO_WRITE', sheet_editing: false }) }, async page => {
      await opened(page);
      const why = await page.locator('.dc-customer', { hasText: 'Đông Á' }).locator('.dc-why').innerText();
      assert.match(why, /^Máy tìm ra chỗ lệch, cộng lại đúng bằng số lệch: Phiếu PH-001 và PH-002 cùng ngày 31\/10, cùng 8,3 tr: có thể ghi trùng\./);
      assert.match(why, /Còn 1 chỗ nữa, mở để xem\./);
      assert.doesNotMatch(why, /không có việc nào giải thích/);
      assert.match(await page.locator('.dc-left').innerText(), /Các chỗ máy tìm ra ở dưới/);
      const items = await page.locator('.dc-hints li').allInnerTexts();
      assert.equal(items.length, 3);
      assert.match(items[2], /Dòng 231 \(MAUU0000231\): Sheet 101,5 tr, web 98 tr\. Máy không tự sửa vì dòng có phụ phí chia theo loại, sửa trên Sổ\./);
      const kept = await page.locator('.dc-customer', { hasText: 'Kim Long' }).locator('.dc-why').innerText();
      assert.match(kept, /^Sheet có chỗ máy chưa đọc được, chưa so được\. Khối tháng 10 trên Sheet: số cuối tháng thiếu 500 đ so với/);
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true, 'không tràn ngang ở 1280');
    });
  });

  test('web đi trước có chuyến để lâu hoặc nằm ở tab sổ khác: khách thành phải xem, câu nói rõ chuyến nào', async () => {
    const hints = [
      { kind: 'ahead_other_book', container: 'MAUU0000002', date: '2026-11-04', amount_vnd: '41000000', other: 'Mẫu An Phát' },
      { kind: 'ahead_old', container: 'MAUU0000001', date: '2026-09-29', amount_vnd: '70000000', days: 38 },
    ];
    const check = { ...lech, reason: 'WEB_AHEAD', sheet_editing: false, sheet_last_edit_at: null, difference_vnd: '111000000', web_ahead_vnd: '111000000', sheet_total_vnd: '5099000000', groups: [], hints };
    const fine = { customer: 'Mẫu Phú Gia', customer_id: 3, status: 'LECH_TONG', reason: 'WEB_AHEAD', difference_vnd: '600000000', web_ahead_vnd: '600000000', groups: [] };
    await withPage({ inbox: inbox({ reconcile: { ...reconcile, counts: { KHOP: 237, LECH_TONG: 2 }, customers: [check, fine] } }),
      statement: statement({ sheet_total_vnd: '5099000000', web_ahead_vnd: '111000000', groups: [], reason: 'WEB_AHEAD', sheet_editing: false, sheet_last_edit_at: null }) }, async page => {
      await opened(page);
      assert.match(await statusLine(page), /1 khách lệch/);
      const why = await page.locator('.dc-customer', { hasText: 'Đông Á' }).locator('.dc-why').innerText();
      assert.match(why, /^Web đi trước Sheet, có chuyến cần xem: Chuyến MAUU0000002 ngày 04\/11 \(41 tr\) web ghi ở sổ này, còn Sheet ghi ở tab Mẫu An Phát\. Xem chuyến thuộc khách nào\./);
      assert.match(why, /Chuyến MAUU0000001 ngày 29\/09 \(70 tr\) có giá trên web đã 38 ngày mà tab Sheet chưa có\. Xem Sheet đã bỏ chuyến này chưa\./);
      assert.doesNotMatch(why, /Không cần làm gì/);
      const panel = await page.locator('.dc-sheet').innerText();
      assert.match(panel, /Web đi trước Sheet\s*· có chuyến cần xem ở dưới/);
      assert.doesNotMatch(panel, /không phải lệch/);
      assert.match(await page.locator('.dc-left').innerText(), /^Cần xem\s+Số khớp nếu tính phần web đi trước\. Xem các chuyến ở dưới\./);
      assert.equal(await page.locator('.dc-left.ok').count(), 0);   // không tô xanh "Khớp" ở khách phải xem
      assert.match(await page.locator('.dc-customer', { hasText: 'Đông Á' }).locator('.dc-gap').innerText(), /^\+111$/);   // web − Sheet, không trừ phần đi trước
      assert.equal(await page.locator('.dc-hints li').count(), 2);
      assert.match(await page.locator('.dc-side summary').innerText(), /1 khách web đi trước Sheet, không cần làm gì/);   // khách không có gì phải xem vẫn ở đây
      if (process.env.UX_SCREENSHOTS) await page.screenshot({ path: path.join(process.env.UX_SCREENSHOTS, 'viec-web-di-truoc-can-xem-1280.png') });
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true, 'không tràn ngang ở 1280');
    });
  });

  test('nhiều khách: lệch lớn mở sẵn, đổi khách một bấm, đóng tay thì để đóng; tab chưa có sổ và web đi trước tính riêng', async () => {
    const rec = { ...reconcile, counts: { KHOP: 234, LECH_TONG: 3, CHI_CO_SHEET: 1 }, outside_tabs: [{ customer: 'TAB MẪU <101>', sheet_total_vnd: '120500000', last_month: '2026-10', reason: 'NOT_ON_TONG' }], customers: [
      { customer: 'Mẫu Lộc Phát', customer_id: 8, status: 'LECH_TONG', reason: 'SHEET_SHUFFLED', difference_vnd: '5000000', web_total_vnd: '100', sheet_total_vnd: '95', shuffled_months: ['2026-10'], groups: [] }, lech,
      { customer: 'Mẫu Phú Gia', customer_id: 3, status: 'LECH_TONG', reason: 'WEB_AHEAD', difference_vnd: '600000000', web_ahead_vnd: '600000000', groups: [] },
      { customer: 'Mẫu An Phát', customer_id: 1, status: 'KHOP', reason: 'FIXED', difference_vnd: '0', fixed_at: '2026-11-06T10:05:00+07:00', written: { receipts: 2, prices: 1 } },
      { customer: 'Tab mới chưa có sổ', customer_id: null, status: 'CHI_CO_SHEET', reason: 'BOOK_OVERLAP', difference_vnd: null }] };
    await withPage({ inbox: inbox({ reconcile: rec }) }, async page => {
      await opened(page);
      const names = await page.locator('.dc-customer th').allInnerTexts();
      assert.deepEqual(names, ['Mẫu Đông Á', 'Mẫu Lộc Phát', 'Tab mới chưa có sổ', 'TAB MẪU <101>']);
      assert.match(await statusLine(page), /3 khách lệch · 1 tab chưa có sổ/);
      assert.match(await page.locator('.dc-customer', { hasText: 'TAB MẪU' }).innerText(), /120,5[\s\S]*chưa có trên TONG/);
      assert.match(await page.locator('.dc-customer', { hasText: 'Lộc Phát' }).innerText(), /đổi chỗ[\s\S]*T10/);
      assert.equal(await page.locator('.dc-customer', { hasText: 'Tab mới' }).locator('button').count(), 0, 'chưa có sổ thì không có đường mở');
      assert.match(await page.locator('.dc-side summary').innerText(), /1 khách web đi trước Sheet, không cần làm gì/);
      assert.equal(await page.locator('[data-dc-open="7"].row-toggle').getAttribute('aria-expanded'), 'true');
      await page.locator('[data-dc-open="8"].row-toggle').click();
      assert.equal(await page.locator('[data-dc-open="8"].row-toggle').getAttribute('aria-expanded'), 'true');
      assert.equal(await page.locator('.dc-detail').count(), 1, 'mỗi lúc mở một khách');
      await page.locator('[data-dc-open="8"].row-toggle').click();
      await page.locator('.dc-detail').waitFor({ state: 'detached' });
      const reread = page.waitForResponse(/\/api\/v7\/inbox$/);
      await page.evaluate(() => document.dispatchEvent(new Event('visibilitychange')));
      await reread;
      await page.evaluate(() => new Promise(resolve => setTimeout(resolve, 80)));
      assert.equal(await page.locator('.dc-detail').count(), 0, 'đóng tay thì tải nền không mở lại');
    });
  });

  test('dòng đầu theo trạng thái: khớp hết xanh, máy lỗi, kết quả cũ, ghi xong không khớp đỏ, chưa có lượt nào', async () => {
    const all = { ...reconcile, counts: { KHOP: 239 }, matched_web_vnd: '100', customers: [] };
    await withPage({ inbox: inbox({ reconcile: all }) }, async page => {
      assert.equal(await page.locator('.viec-status.warn,.viec-status.danger').count(), 0);
      assert.match(await statusLine(page), /239\/239 khách khớp Sheet[\s\S]*100% số nợ/);
      assert.match(await page.locator('.dc-empty').innerText(), /Không có khách nào lệch\. Chưa cần làm gì\.[\s\S]*Máy kiểm lại lúc 11:05\. Email chỉ gửi khi máy lỗi hoặc dừng; khách lệch hiện ở đây\./);   // CANH-BAO-01 không email khách lệch
    });
    await withPage({ inbox: inbox({ reconcile: { ...all, last_error: { at: '2026-11-06T10:05:00+07:00', reason: 'HTTPError' } } }) }, async page => {
      assert.match(await page.locator('.status-error').innerText(), /Lần đối soát lúc 10:05 chưa chạy được \(HTTPError\)\. Số dưới đây là của lần trước\./);
      assert.ok(await page.locator('.viec-status.warn').count());
    });
    await withPage({ now: '2026-11-06T16:00:00+07:00', inbox: inbox({ reconcile: all }) }, async page => {
      assert.match(await statusLine(page), /có thể cũ/);
      assert.ok(await page.locator('.viec-status.warn').count());
    });
    await withPage({ now: '2026-11-07T06:30:00+07:00', inbox: inbox({ reconcile: all }) }, async page => {
      const text = await statusLine(page);
      assert.match(text, /lúc 10:12 ngày 06\/11 · lần tới 07:05/);
      assert.doesNotMatch(text, /có thể cũ/);
    });
    await withPage({ inbox: inbox({ reconcile: { ...reconcile, customers: [{ ...lech, reason: 'VERIFY_FAILED', sheet_editing: false }] } }) }, async page => {
      assert.ok(await page.locator('.viec-status.danger').count());
      assert.match(await page.locator('.dc-why').innerText(), /Máy đã ghi nhưng tổng chưa khớp\. Cần xem ngay\./);
    });
    await withPage({ inbox: inbox({ reconcile: undefined }) }, async page => {
      assert.match(await statusLine(page), /Chưa có lượt đối soát/);
      assert.match(await page.locator('.dc-empty').innerText(), /Chưa có kết quả đối soát/);
    });
  });

  test('dọn chi tiết: hiện cả sổ đã khớp, khoản của khách lệch không hiện lại, bảng ít sổ không có Cộng và chip', async () => withPage({}, async page => {
    await page.locator('[data-tab="don"]').click();
    await page.locator('.work-row').first().waitFor();
    assert.deepEqual((await page.locator('.work-row').evaluateAll(rows => rows.map(row => Number(row.dataset.book)))).sort(), [1, 3, 7]);
    const row = await page.locator('[data-book="7"]').innerText();
    assert.match(row, /2\s*chưa giá/);
    assert.match(row, /1\s*PS/);
    assert.doesNotMatch(row, /giá khác|cần xem/);
    await page.locator('[data-book="7"] .book-name').click();
    await page.locator('.work-detail .open-book').waitFor();
    await page.locator('.work-detail .loading').waitFor({ state: 'hidden' });
    const detail = await page.locator('.work-detail').innerText();
    assert.doesNotMatch(detail, /Phiếu cần xem|Giá khác/);
    assert.equal(await page.locator('.work-table tfoot').count(), 0);
    assert.equal(await page.locator('[data-filter]').count(), 0);
    assert.match(await page.locator('.band-count').innerText(), /3\s*sổ còn việc/);
  }));

  test('dòng giá chỉ khác phụ phí ở Dọn chi tiết cũng ghi đúng là phụ phí', async () => {
    const rec = { ...reconcile, customers: [], counts: { KHOP: 239 } };
    await withPage({ inbox: inbox({ reconcile: rec }) }, async page => {
      await page.locator('[data-tab="don"]').click();
      await page.locator('[data-book="7"] .book-name').click();
      await page.locator('.detail-group').first().waitFor();
      const text = await page.locator('.detail-group', { hasText: 'Giá khác' }).locator('li').first().innerText();
      assert.match(text, /Đơn giá 60 · phụ phí web 3,4 → Sheet 12,9/);
      assert.doesNotMatch(text, /Trên web 60/);
    });
  });

  test('đã làm: hôm nay cả máy lẫn người, mới nhất trước, câu như Lịch sử, lọc máy/người; nhớ tab khi tải lại', async () => withPage({}, async page => {
    await page.locator('[data-tab="may"]').click();
    await page.locator('.act-table').waitFor();
    // Bảng có cột, chia nhóm theo loại việc (Chuyến · Thu tiền · Giá và phụ phí …), mỗi nhóm có tiêu đề kèm số việc.
    assert.deepEqual((await page.locator('.act-table thead th').allInnerTexts()).slice(0, 6), ['Giờ', 'Người làm', 'Sổ', 'Việc', 'Chi tiết', 'Ghi chú']);
    assert.deepEqual((await page.locator('.act-group-title').allInnerTexts()).map(text => text.replace(/\s+/g, ' ')), ['Chuyến 1', 'Thu tiền 1', 'Giá và phụ phí 1']);
    const cells = async group => page.locator(`[data-act-group="${group}"] tr:not(.act-group-head)`).first().locator('td,th').allInnerTexts();
    assert.deepEqual((await cells('chuyen')).slice(0, 6), ['09:05', 'Máy', 'Mẫu An Phát', 'Dán lô chuyến', '2 chuyến: MAUU0000002 (05/11/2026) · MAUU0000004 (05/11/2026)', 'Chuyến đồng bộ']);
    assert.deepEqual((await cells('thu')).slice(0, 4), ['10:20', 'Thu', 'Mẫu An Phát', 'Ghi phiếu thu']);
    assert.match((await cells('thu'))[4], /^PH-007: 5\.000\.000 đ ngày 05\/11\/2026/);
    assert.deepEqual((await cells('gia')).slice(0, 5), ['09:50', 'Máy', 'Mẫu Phú Gia', 'Sửa giá', 'Chuyến MAUU0000003 · Đơn giá: – → 42.000.000']);
    assert.equal(await page.locator('.act-table a').first().getAttribute('href'), '/so-khach-v7-live.html?customer=1');
    assert.match(await page.locator('.today-inline').innerText(), /Người nhập mẫu/);
    assert.deepEqual((await page.locator('[data-act-filter]').allInnerTexts()).map(text => text.replace(/\s+/g, ' ')), ['Tất cả 3', 'Máy 2', 'Người 1']);
    await page.locator('[data-act-filter="nguoi"]').click();
    assert.equal(await page.locator('.act-table tbody tr:not(.act-group-head)').count(), 1);
    await page.locator('[data-act-filter="may"]').click();
    assert.equal(await page.locator('.act-table tbody tr:not(.act-group-head)').count(), 2);
    assert.equal(await page.locator('[data-act-day]', { hasText: 'Sau' }).isDisabled(), true, 'hôm nay không có ngày sau');
    await page.reload();
    await page.locator('.act-table').waitFor();
    assert.equal(await page.locator('[data-tab="may"]').getAttribute('aria-selected'), 'true');
  }));

  test('đã làm: lùi về ngày gần nhất có việc, chọn ngày bằng ô ngày, ngày trống nói rõ, lỗi có Thử lại', async () => {
    const opts = { activityAsked: [] };
    await withPage(opts, async page => {
      await page.locator('[data-tab="may"]').click();
      await page.locator('.act-table').waitFor();
      await page.locator('[data-act-day="2026-11-03"]').click();
      await page.waitForFunction(() => document.querySelector('[data-act-date]')?.value === '2026-11-03' && document.querySelector('.act-table'));
      const item = await page.locator('.act-table tbody tr:not(.act-group-head)').innerText();
      assert.match(item, /15:00[\s\S]*Kế toán[\s\S]*Mẫu Đông Á[\s\S]*Hủy phiếu\tPH-002: 1\.000\.000 đ\tLý do hủy: ghi trùng/);
      assert.equal(await page.locator('.today-inline').count(), 0, 'ngày cũ không có dòng Đã ghi hôm nay');
      assert.ok(opts.activityAsked.includes('2026-11-03'));
      await page.locator('[data-act-date]').fill('2026-11-04');
      await page.locator('.dc-empty', { hasText: 'Ngày 04/11/2026 không ai ghi gì.' }).waitFor();
      await page.locator('[data-act-day="today"]').click();
      await page.locator('.today-inline').waitFor();
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
      opts.activityStatus = 503;
      await page.locator('[data-act-date]').fill('2026-11-01');
      await page.locator('[data-act-retry]').waitFor();
      opts.activityStatus = 0;
      await page.locator('[data-act-retry]').click();
      await page.locator('.dc-empty', { hasText: 'Ngày 01/11/2026 không ai ghi gì.' }).waitFor();
    });
  });

  test('bản gần nhất của tab: xem và đổi tab được, ô chọn và nút ghi khóa tới khi có bản mới', async () => withPage({}, async page => {
    await opened(page);
    await page.waitForFunction(() => sessionStorage.getItem('webdebit.todoSnapshot.v1'));
    let release = () => {};
    const gate = new Promise(resolve => { release = resolve; });
    await page.route(/\/api\/v7\/(inbox|dashboard|dashboard\/debt|customers)$/, async route => { await gate; await route.continue(); });
    await page.reload();
    await page.locator('.refreshing').waitFor();
    assert.equal(await page.locator('[data-tab="don"]').isDisabled(), false);
    assert.equal(await page.locator('[data-dc-open="7"].row-toggle').isDisabled(), false);
    release();
    await page.locator('.refreshing').waitFor({ state: 'detached' });
    await opened(page);
    assert.equal(await page.locator('[data-dc-pick="prices:2026-10"]').isDisabled(), false);
  }));
}
